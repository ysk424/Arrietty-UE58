"""Loopback-only UE transport. Hardware stays in the existing worker threads.

The service is inert until a UE client sends play=true. Without --hardware all
device implementations are replaced before any service can be started.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
import math
from pathlib import Path
import socket
import time

from arrietty_up.runtime import RuntimeState, _update_navigation
from arrietty_up.controller_protocol import ControllerSample
from arrietty_up.serial_controller import ControllerEventType
from arrietty_up.steering import SteeringSnapshot
from arrietty_up.flight_log import FlightLog
from arrietty_up.instruments import build_readout

PROTOCOL = 1
WATCHDOG_SECONDS = 1.0
ROOT = Path(__file__).resolve().parents[1]


class OfflineDevice:
    """No socket, serial, BLE or OpenVR calls, including cleanup."""
    running = False
    generation = 0
    status = short_status = "OFFLINE"
    requested_level = 0
    reported_level = None

    def start(self, *args):
        self.running = True
        self.generation += 1
        return self.generation

    def stop(self, *args):
        self.running = False
        return True

    def close(self):
        self.stop()

    def request_grade(self, *args):
        pass

    def recenter(self):
        pass

    def set_ptt_held(self, *args):
        return True

    def poll(self):
        return None

    def snapshot(self):
        return SteeringSnapshot(status="OFFLINE", tracking=True)

    def drain_events(self):
        return []

    def tick(self, *args):
        pass


def ue_pose(state):
    """UE centimetres: X north, Y east, Z up. UE roll is right-wing-down."""
    return [state.position_y_meters * 100, state.position_x_meters * 100,
            state.flight.altitude_meters * 100,
            state.flight.pitch_degrees if state.flight.airborne else 0,
            (180 - state.heading_degrees) % 360,
            -state.flight.bank_degrees if state.flight.airborne else 0]


class Simulation:
    def __init__(self, world: dict, hardware=False, log_path=None):
        self.world = world
        self.hardware = hardware
        self.log_path = Path(log_path or ROOT / "logs" /
                             ("latest-ue-flight.csv" if hardware else "latest-ue-offline.csv"))
        self.state = None
        self.alignment_id = 0
        self.recenter_id = 0
        self.input_sequence = 0
        self.controller_status = "WAITING"
        self.apply_id = 0
        self.apply_error = ""

    def setup(self, packet):
        request = int(packet.get("apply_id", 0))
        if request > self.apply_id:
            self.apply_id = request
            try:
                path = Path(self.world.get('solar_module_path') or ROOT.parent / 'Secret-World/solar.py')
                spec = importlib.util.spec_from_file_location('arrietty_world_solar', path)
                solar = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(solar)
                instant = solar.parse_local(packet.get('local_date', ''), packet.get('local_time', ''), 12)
                result = solar.position(instant, self.world['origin_latitude'], self.world['origin_longitude'])
                self.world.update(local_time=result['local'], sun_azimuth=result['azimuth_degrees'],
                                  sun_elevation=result['elevation_degrees'])
                self.apply_error = ""
            except (OSError, ValueError, TypeError) as error:
                self.apply_error = str(error)
        return {"playing": False, "status": "P: START | ESC: SETUP",
                "apply_id": self.apply_id, "apply_error": self.apply_error,
                "local_time": self.world.get('local_time',''),
                "sun_azimuth": self.world.get('sun_azimuth',277.36),
                "sun_elevation": self.world.get('sun_elevation',3.39)}

    def begin(self):
        if self.state is not None:
            return
        s = RuntimeState()
        if not self.hardware:
            for name in ("bluetooth", "serial", "steering", "fan", "voice"):
                setattr(s, name, OfflineDevice())
        s.heading_degrees = self.world["initial_heading_degrees"]
        self.state = s
        s.serial.start()
        s.steering.start()
        s.fan.start()
        s.prepare_devices()
        metadata = {"world_file": self.world["output_name"],
                    "world_local_time": self.world.get("local_time", ""),
                    "origin_latitude": self.world["origin_latitude"],
                    "origin_longitude": self.world["origin_longitude"]}
        s.flight_log = FlightLog(self.log_path, metadata)
        _update_navigation(s)

    def stop(self):
        if self.state is not None:
            # Stop airflow/PTT before joining a potentially slow BLE worker.
            self.state.fan.stop()
            self.state.voice.close()
            if self.state.bluetooth.running:
                self.state.bluetooth.request_grade(0)
            self.state.stop_services()
            self.state = None

    def controller(self, sample, now):
        s = self.state
        edge = s.button_edges.update(sample)
        s.controller_sample_count += 1
        if edge is not None and edge.pressed & 1:
            if s.start_ride():
                self.alignment_id += 1
        s.handle_controller_input(sample, edge, now)

    def step(self, packet, delta, now=None):
        now = time.monotonic() if now is None else now
        if not packet.get("play", False):
            self.stop()
            return self.setup(packet)
        self.begin()
        s = self.state
        request = int(packet.get("recenter_id", 0))
        if request > self.recenter_id:
            self.recenter_id = request
            if s.ride_active:
                # R repeats the facing/handle calibration without a recovery
                # jump, resetting the course, or restarting the ride clock.
                self.alignment_id += 1
                s.hmd_aligned = False
                s.steering.recenter()
        for event in s.serial.drain_events():
            if event.message:
                self.controller_status = event.message
            if event.type is ControllerEventType.SAMPLE and event.sample is not None:
                self.controller(event.sample, now)
            elif event.type is ControllerEventType.DISCONNECTED:
                s.set_brake_button_held(False)
                s.voice.set_ptt_held(False)
                s.ptt_held = False
        for event in s.bluetooth.drain_events():
            s.handle_bluetooth_event(event)
        if not self.hardware:
            self.input_sequence += 1
            mask = int(packet.get("buttons", 0)) & 255
            self.controller(ControllerSample(self.input_sequence, 0, 0, 0, 0, mask), now)
            s.ftms_speed_kmh = max(0, min(80, float(packet.get("speed", 0))))
            s.cadence_rpm = 70 if s.ftms_speed_kmh > 0 else 0
            s.power_watts = int(max(0, min(1000, float(packet.get("power", 0)))))
            s.last_ftms_sample_seconds = now
            s.bluetooth_status = "OFFLINE SIMULATION"
            s.heart_rate_status = "NOT CONNECTED"
        s.update_sensor_state(now)
        s.update_ride_elapsed(now)
        s.update_steering_state()
        if not self.hardware:
            s.effective_steering_degrees = max(-35, min(35, float(packet.get("steer", 0))))
        s.hmd_aligned = (s.ride_active and self.alignment_id > 0 and
                         packet.get("aligned") == self.alignment_id and
                         bool(packet.get("hmd_valid", False)))
        s.xr_bridge_status = "UE OPENXR" if self.hardware else "UE OFFLINE"
        s.flush_flight_button(now)
        result = s.voice.poll()
        if result:
            s.voice_status = result[0]
        delta = max(0, min(.05, delta))
        if s.ride_active and s.steering_tracking and s.hmd_aligned:
            moved = s.advance_flight(delta, now) if s.flight_enabled else s.advance_ground(delta)
            if moved > 0 and s.first_motion_after_seconds <= 0:
                s.first_motion_after_seconds = max(.000001, now - s.ride_started_at_seconds)
        s.fan.tick(s.fan_apparent_speed_kmh() if s.hmd_aligned and s.steering_tracking else 0, now)
        _update_navigation(s)
        s.flight_log.sample(s, now)
        s.frame_count += 1
        return {"playing": True, "pose": ue_pose(s), "align_request": self.alignment_id,
                "recenter_id": self.recenter_id,
                "ride": s.ride_active, "airborne": s.flight.airborne,
                "pitch": s.flight.pitch_degrees, "bank": s.flight.bank_degrees,
                "heading": s.navigation_heading_degrees,
                "home_relative": s.home_relative_degrees,
                "airspeed": s.flight.airspeed_meters_per_second * 3.6,
                "altitude": s.flight.altitude_meters,
                "readout": asdict(build_readout(s, delta)),
                "controller": self.controller_status, "frames": s.frame_count,
                "flight_event": s.last_flight_event,
                "log_error": s.flight_log.error}


def valid_packet(raw, token):
    try:
        p = json.loads(raw)
        if not isinstance(p, dict) or p.get("protocol") != PROTOCOL or p.get("token") != token:
            return None
        if type(p.get("seq")) is not int or type(p.get("play")) is not bool:
            return None
        for key in ("speed", "power", "steer", "buttons", "aligned", "apply_id", "recenter_id"):
            if key in p and (type(p[key]) not in (int, float) or not math.isfinite(p[key])):
                return None
        return p
    except (ValueError, TypeError, UnicodeError):
        return None


def serve(args):
    world = json.loads(args.world.read_text(encoding="utf-8-sig"))
    config = json.loads(args.session.read_text(encoding="utf-8-sig"))
    token = config["token"]
    if len(token) < 32:
        raise ValueError("Session token is too short")
    sim = Simulation(world, hardware=args.hardware, log_path=args.log_path)
    # Exclusive loopback bind before initializing any devices.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", config["port"]))
        sock.settimeout(.05)
        last_received = time.monotonic()
        previous = last_received
        peer = None
        seq = -1
        print("ARRIETTY_UE_BRIDGE_READY hardware=" + str(args.hardware), flush=True)
        try:
            while True:
                now = time.monotonic()
                if now - last_received > WATCHDOG_SECONDS:
                    if sim.state is not None:
                        print("ARRIETTY_UE_WATCHDOG_STOP", flush=True)
                        sim.stop()
                    if peer is not None and now - last_received > 30:
                        return
                try:
                    raw, address = sock.recvfrom(8192)
                except socket.timeout:
                    continue
                if address[0] != "127.0.0.1" or (peer and address != peer):
                    continue
                p = valid_packet(raw, token)
                if p is None or p["seq"] <= seq:
                    continue
                peer, seq = address, p["seq"]
                last_received = now = time.monotonic()
                if p.get("quit"):
                    return
                response = sim.step(p, now - previous, now)
                previous = now
                response.update(protocol=PROTOCOL, seq=seq, token=token)
                sock.sendto(json.dumps(response, allow_nan=False).encode(), peer)
        finally:
            sim.stop()
            print("ARRIETTY_UE_BRIDGE_STOPPED", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--log-path", type=Path)
    serve(parser.parse_args())


if __name__ == "__main__":
    main()
