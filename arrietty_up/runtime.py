"""UPBGE game-loop entry point.

This module deliberately imports :mod:`bge` only inside the controller entry
point so the rest of the package remains testable in normal Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

from . import constants as c
from .bluetooth import BluetoothEvent, BluetoothEventType, BluetoothManager
from .controls import (
    DigitalFlightControls,
    FlightButtonAction,
    FlightButtonChord,
    FlightTuningControls,
)
from .controller_protocol import ButtonEdgeLatch, ButtonTransition, ControllerSample
from .flight import initialize_human_powered_flight, step_human_powered_flight
from .fan import FanController
from .flight_log import FlightLog
from .instruments import update_upbge_panel
from .models import CscSample, FlightState
from .serial_controller import ControllerEventType, SerialController
from .steering import SteeringController
from .trainer_protocol import effective_speed_kmh
from .voice import VoiceBridge


@dataclass(slots=True)
class RuntimeState:
    started_at: float = field(default_factory=time.monotonic)
    previous_tick_at: float = field(default_factory=time.monotonic)
    frame_count: int = 0
    flight_enabled: bool = False
    flight: FlightState = field(default_factory=initialize_human_powered_flight)
    digital_controls: DigitalFlightControls = field(default_factory=DigitalFlightControls)
    flight_button_chord: FlightButtonChord = field(default_factory=FlightButtonChord)
    tuning_controls: FlightTuningControls = field(default_factory=FlightTuningControls)
    serial: SerialController = field(default_factory=SerialController)
    bluetooth: BluetoothManager = field(default_factory=BluetoothManager)
    steering: SteeringController = field(default_factory=SteeringController)
    fan: FanController = field(default_factory=FanController)
    voice: VoiceBridge = field(default_factory=VoiceBridge)
    button_edges: ButtonEdgeLatch = field(default_factory=ButtonEdgeLatch)
    button_history: list[str] = field(default_factory=list)
    controller_sample_count: int = 0
    controller_nonzero_samples: int = 0
    controller_button_mask: int = 0
    joystick1_axes: tuple[float, float] = (0.0, 0.0)
    joystick2_axes: tuple[float, float] = (0.0, 0.0)
    ride_active: bool = False
    connection_started_at_seconds: float = 0.0
    ride_started_at_seconds: float = 0.0
    ride_elapsed_seconds: float = 0.0
    first_motion_after_seconds: float = 0.0
    trainer_found_after_seconds: float = 0.0
    gatt_connected_after_seconds: float = 0.0
    trainer_ready_after_seconds: float = 0.0
    control_ready_after_seconds: float = 0.0
    first_ftms_after_seconds: float = 0.0
    heart_rate_connected_after_seconds: float = 0.0
    first_heart_rate_after_seconds: float = 0.0
    bluetooth_generation: int = 0
    bluetooth_status: str = "IDLE"
    bluetooth_message: str = ""
    selected_preset: int = 5
    applied_preset: int | None = None
    applied_grade_percent: float = 0.0
    brake_button_held: bool = False
    position_x_meters: float = 0.0
    position_y_meters: float = 0.0
    start_position_x_meters: float = 0.0
    start_position_y_meters: float = 0.0
    heading_degrees: float = 0.0
    navigation_heading_degrees: float = 0.0
    home_bearing_degrees: float = 0.0
    home_relative_degrees: float = 0.0
    home_distance_meters: float = 0.0
    steering_tracking: bool = False
    steering_status: str = "IDLE"
    steering_message: str = "VIVE steering is stopped"
    raw_steering_degrees: float = 0.0
    effective_steering_degrees: float = 0.0
    distance_meters: float = 0.0
    laps_completed: int = 0
    recovery_trail: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )
    recovery_path_distance_meters: float = 0.0
    last_recovery_sample_meters: float = 0.0
    last_recovered_meters: float = 0.0
    last_start_action: str = "IDLE"
    hmd_aligned: bool = False
    hmd_alignment_degrees: float = 0.0
    hmd_alignment_message: str = "WAITING FOR BUTTON 1"
    xr_bridge_status: str = "NOT CHECKED"
    xr_navigation_synced: bool = False
    last_mode_action: str = "GROUND"
    last_flight_event: str = ""
    last_control_message: str = ""
    propulsion_power_watts: float = 0.0
    speed_kmh: float = 0.0
    ground_speed_kmh: float = 0.0
    ftms_speed_kmh: float = 0.0
    cadence_rpm: float = 0.0
    power_watts: int = 0
    last_ftms_sample_seconds: float = 0.0
    wheel_signal_received: bool = False
    wheel_revolutions: int | None = None
    wheel_event_time_ticks: int | None = None
    last_wheel_motion_seconds: float = 0.0
    wheel_period_seconds: float = 0.0
    heart_rate_bpm: int | None = None
    heart_rate_status: str = "DISCONNECTED"
    last_heart_rate_sample_seconds: float = 0.0
    ptt_held: bool = False
    voice_status: str = "IDLE"
    ending: bool = False
    flight_log: FlightLog | None = None

    def prepare_devices(self) -> bool:
        if self.bluetooth.running:
            self.bluetooth_generation = self.bluetooth.generation
            return False

        self.speed_kmh = 0.0
        self.ground_speed_kmh = 0.0
        self.ftms_speed_kmh = 0.0
        self.cadence_rpm = 0.0
        self.power_watts = 0
        self.last_ftms_sample_seconds = 0.0
        self.wheel_signal_received = False
        self.wheel_revolutions = None
        self.wheel_event_time_ticks = None
        self.last_wheel_motion_seconds = 0.0
        self.wheel_period_seconds = 0.0
        self.heart_rate_bpm = None
        self.heart_rate_status = "SEARCHING"
        self.applied_preset = None
        self.applied_grade_percent = 0.0
        self.bluetooth_status = "SEARCHING"
        self.bluetooth_message = "Searching for CYCPLUS T2"
        self.connection_started_at_seconds = time.monotonic()
        self.bluetooth_generation = self.bluetooth.start(
            self.selected_preset,
            c.BRAKE_GRADE_PERCENT if self.brake_button_held else 0.0,
        )
        self.trainer_found_after_seconds = 0.0
        self.gatt_connected_after_seconds = 0.0
        self.trainer_ready_after_seconds = 0.0
        self.control_ready_after_seconds = 0.0
        self.first_ftms_after_seconds = 0.0
        self.heart_rate_connected_after_seconds = 0.0
        self.first_heart_rate_after_seconds = 0.0
        return True

    def start_ride(self) -> bool:
        if self.ride_active:
            self.last_recovered_meters = self.recover_two_meters()
            self.last_start_action = "SAFETY_RETURN"
            return False
        self.prepare_devices()
        self.flight_enabled = False
        self.flight = initialize_human_powered_flight()
        self.digital_controls.reset(self.joystick2_axes)
        self.flight_button_chord.reset()
        self.tuning_controls.reset(self.joystick1_axes)
        self.propulsion_power_watts = 0.0
        self.steering.recenter()
        self.ride_started_at_seconds = time.monotonic()
        self.ride_elapsed_seconds = 0.0
        self.hmd_aligned = False
        self.hmd_alignment_message = "ALIGNING HMD TO BICYCLE FORWARD"
        self.first_motion_after_seconds = 0.0
        if self.brake_button_held and self.bluetooth.running:
            self.bluetooth.request_grade(c.BRAKE_GRADE_PERCENT)
        self.reset_recovery_trail()
        self.last_recovered_meters = 0.0
        self.last_start_action = "STARTED"
        self.ride_active = True
        return True

    def update_ride_elapsed(self, now_seconds: float) -> None:
        """Advance the displayed clock from the first Button 1 start."""
        if not self.ride_active or self.ride_started_at_seconds <= 0.0:
            return
        self.ride_elapsed_seconds = max(
            self.ride_elapsed_seconds,
            now_seconds - self.ride_started_at_seconds,
        )

    def toggle_flight(self) -> bool:
        if not self.ride_active:
            self.last_mode_action = "START RIDE BEFORE FLIGHT"
            return False
        if self.flight_enabled:
            if self.flight.airborne or self.flight.altitude_meters > 0.05:
                self.last_mode_action = "LAND BEFORE GROUND MODE"
                return False
            self.flight_enabled = False
            self.flight = initialize_human_powered_flight()
            self.digital_controls.reset(self.joystick2_axes)
            self.flight_button_chord.reset()
            self.tuning_controls.reset(self.joystick1_axes)
            self.propulsion_power_watts = 0.0
            self.last_mode_action = "GROUND"
            return True
        self.flight_enabled = True
        self.flight = initialize_human_powered_flight(self.ground_speed_kmh)
        self.digital_controls.reset(self.joystick2_axes)
        self.flight_button_chord.reset()
        self.tuning_controls.reset(self.joystick1_axes)
        self.last_mode_action = "FLIGHT"
        return True

    def _apply_flight_button_action(self, action: FlightButtonAction) -> None:
        if action.pitch_step:
            self.digital_controls.step_pitch(action.pitch_step)
            self.last_control_message = "BUTTON 3+4 PITCH UP"
        if action.roll_right_step:
            self.digital_controls.step_roll_right(action.roll_right_step)
            self.last_control_message = (
                "BUTTON 4 ROLL RIGHT"
                if action.roll_right_step > 0
                else "BUTTON 3 ROLL LEFT"
            )
        if action.pitch_step or action.roll_right_step:
            print(
                "ARRIETTY_FLIGHT_COMMAND "
                f"pitch={self.digital_controls.pitch_degrees:+.1f} "
                f"bank={self.digital_controls.bank_degrees:+.1f} "
                f"source={self.last_control_message}",
                flush=True,
            )

    def flush_flight_button(self, now_seconds: float) -> None:
        action = self.flight_button_chord.flush(now_seconds)
        if action is not None and self.flight_enabled:
            self._apply_flight_button_action(action)

    def handle_controller_input(
        self,
        sample: ControllerSample,
        transition: ButtonTransition | None,
        now_seconds: float,
    ) -> None:
        self.controller_button_mask = sample.button_mask
        self.joystick1_axes = sample.joystick1
        self.joystick2_axes = sample.joystick2
        self.set_brake_button_held(bool(sample.button_mask & 0x20))
        pressed = 0 if transition is None else transition.pressed
        changed = 0 if transition is None else transition.pressed | transition.released

        if pressed & 0x02:
            self.toggle_flight()
        current_ptt = bool(sample.button_mask & 0x10)
        if changed & 0x10 or self.ptt_held != current_ptt:
            self.ptt_held = current_ptt
            self.voice.set_ptt_held(self.ptt_held)
            self.voice_status = self.voice.status

        if not self.flight_enabled:
            if pressed & 0x40:
                self.last_control_message = "ENABLE FLIGHT BEFORE TUNING"
            return
        if pressed & 0x40:
            self.tuning_controls.press_switch(self.joystick1_axes)
            self.last_control_message = self.tuning_controls.compact_status()
        tuning_change = self.tuning_controls.update_joystick(self.joystick1_axes)
        if tuning_change.value_changed:
            self.last_control_message = self.tuning_controls.compact_status()
        if pressed & 0x80:
            self.flight_button_chord.reset()
            self.digital_controls.reset_commands(self.joystick2_axes)
            self.last_control_message = "J2 SW FLIGHT COMMAND RESET"
        else:
            control_change = self.digital_controls.update_joystick(
                self.joystick2_axes
            )
            if control_change.pitch_changed or control_change.roll_changed:
                self.last_control_message = "J2 FLIGHT COMMAND"
        for action in self.flight_button_chord.update(
            pressed,
            sample.button_mask,
            now_seconds,
        ):
            self._apply_flight_button_action(action)

    def connection_elapsed(self, received_at: float) -> float:
        baseline = self.connection_started_at_seconds or self.ride_started_at_seconds
        return max(0.0, received_at - baseline)

    def set_brake_button_held(self, held: bool) -> None:
        if self.brake_button_held == held:
            return
        self.brake_button_held = held
        if self.ride_active and self.bluetooth.running:
            self.bluetooth.request_grade(c.BRAKE_GRADE_PERCENT if held else 0.0)
            self.bluetooth_status = "SETTING BRAKE" if held else "RELEASING BRAKE"

    def handle_csc_sample(self, received_at: float, sample: CscSample) -> None:
        if sample.wheel_revolutions is None or sample.wheel_event_time_ticks is None:
            return
        previous_revolutions = self.wheel_revolutions
        previous_ticks = self.wheel_event_time_ticks
        self.wheel_signal_received = True
        self.wheel_revolutions = sample.wheel_revolutions
        self.wheel_event_time_ticks = sample.wheel_event_time_ticks
        if previous_revolutions is None or previous_ticks is None:
            self.last_wheel_motion_seconds = received_at
            return

        revolution_delta = (sample.wheel_revolutions - previous_revolutions) & 0xFFFFFFFF
        if revolution_delta == 0:
            return
        tick_delta = (sample.wheel_event_time_ticks - previous_ticks) & 0xFFFF
        if tick_delta > 0 and revolution_delta < 1000:
            period = tick_delta / 1024.0 / revolution_delta
            if 0.01 <= period <= 30.0:
                self.wheel_period_seconds = period
        self.last_wheel_motion_seconds = received_at

    def handle_bluetooth_event(self, event: BluetoothEvent) -> None:
        if event.generation != self.bluetooth_generation:
            return
        if event.type is BluetoothEventType.STATUS:
            self.bluetooth_status = (
                "CONNECTING" if event.message.startswith("CONNECTING:") else "SEARCHING"
            )
            self.bluetooth_message = event.message
            if (
                self.bluetooth_status == "CONNECTING"
                and self.trainer_found_after_seconds <= 0.0
            ):
                self.trainer_found_after_seconds = max(
                    0.0, self.connection_elapsed(event.received_at)
                )
        elif event.type is BluetoothEventType.GATT_CONNECTED:
            self.bluetooth_status = "GATT CONNECTED"
            self.bluetooth_message = event.message
            self.gatt_connected_after_seconds = self.connection_elapsed(
                event.received_at
            )
        elif event.type is BluetoothEventType.TRAINER_READY:
            self.bluetooth_status = "DATA READY"
            self.bluetooth_message = event.message
            self.trainer_ready_after_seconds = self.connection_elapsed(event.received_at)
        elif event.type is BluetoothEventType.CONNECTED:
            self.bluetooth_status = "CONNECTED"
            self.bluetooth_message = "T2 speed data active"
        elif event.type is BluetoothEventType.CONTROL_READY:
            self.applied_preset = event.preset_index
            self.applied_grade_percent = event.grade_percent or 0.0
            self.bluetooth_status = (
                f"BRAKE {self.applied_grade_percent:.1f}% P{event.preset_index}"
                if self.applied_grade_percent > 0.0
                else f"FLAT P{event.preset_index}"
            )
            self.control_ready_after_seconds = self.connection_elapsed(event.received_at)
        elif event.type is BluetoothEventType.CONTROL_UNAVAILABLE:
            self.bluetooth_status = "DATA ONLY"
            self.bluetooth_message = event.message
        elif event.type is BluetoothEventType.TRAINER_SAMPLE:
            sample = event.trainer_sample
            if sample is not None:
                if self.first_ftms_after_seconds <= 0.0:
                    self.first_ftms_after_seconds = self.connection_elapsed(
                        event.received_at
                    )
                if sample.speed_kmh is not None:
                    self.ftms_speed_kmh = max(0.0, sample.speed_kmh)
                if sample.cadence_rpm is not None:
                    self.cadence_rpm = max(0.0, sample.cadence_rpm)
                if sample.power_watts is not None:
                    self.power_watts = max(0, sample.power_watts)
                self.last_ftms_sample_seconds = event.received_at
        elif event.type is BluetoothEventType.CSC_SAMPLE:
            if event.csc_sample is not None:
                self.handle_csc_sample(event.received_at, event.csc_sample)
        elif event.type is BluetoothEventType.CSC_UNAVAILABLE:
            self.bluetooth_message = event.message
        elif event.type is BluetoothEventType.HEART_RATE_CONNECTED:
            self.heart_rate_status = event.message
            self.heart_rate_connected_after_seconds = self.connection_elapsed(
                event.received_at
            )
        elif event.type is BluetoothEventType.HEART_RATE_SAMPLE:
            self.heart_rate_bpm = event.heart_rate_bpm
            self.heart_rate_status = "CONNECTED"
            self.last_heart_rate_sample_seconds = event.received_at
            if self.first_heart_rate_after_seconds <= 0.0:
                self.first_heart_rate_after_seconds = self.connection_elapsed(
                    event.received_at
                )
        elif event.type is BluetoothEventType.HEART_RATE_UNAVAILABLE:
            self.heart_rate_bpm = None
            self.heart_rate_status = event.message
            self.last_heart_rate_sample_seconds = 0.0
        elif event.type is BluetoothEventType.ERROR:
            self.bluetooth_status = "ERROR"
            self.bluetooth_message = event.message
            self.speed_kmh = 0.0
            self.ftms_speed_kmh = 0.0
            self.applied_preset = None
            self.applied_grade_percent = 0.0
            self.ride_active = False
            self.flight_enabled = False
        elif event.type is BluetoothEventType.WORKER_STOPPED:
            if self.bluetooth_status != "ERROR":
                self.bluetooth_status = "IDLE"
                self.bluetooth_message = "Trainer stopped"
            self.ride_active = False

    def update_sensor_state(self, now: float) -> None:
        self.ground_speed_kmh = effective_speed_kmh(
            now,
            self.last_ftms_sample_seconds,
            self.ftms_speed_kmh,
            self.cadence_rpm,
            self.wheel_signal_received,
            self.last_wheel_motion_seconds,
            self.wheel_period_seconds,
        )
        if not self.flight_enabled:
            self.speed_kmh = self.ground_speed_kmh
        if (
            self.heart_rate_bpm is not None
            and now - self.last_heart_rate_sample_seconds > c.HEART_RATE_STALE_SECONDS
        ):
            self.heart_rate_bpm = None
            self.heart_rate_status = "STALE - SEARCHING"

    def advance_ground(self, delta_seconds: float) -> float:
        if not self.ride_active:
            return 0.0
        advance = self.speed_kmh / 3.6 * max(0.0, min(0.25, delta_seconds))
        if advance <= 0.0:
            return 0.0
        steering = math.radians(self.effective_steering_degrees)
        turn = advance / c.WHEELBASE_METERS * math.tan(steering)
        midpoint_heading = math.radians(self.heading_degrees) + turn * 0.5
        # OpenXR's calibrated forward direction in this scene is Blender Y-.
        self.position_x_meters += math.sin(midpoint_heading) * advance
        self.position_y_meters -= math.cos(midpoint_heading) * advance
        self.heading_degrees = _unwind_degrees(
            self.heading_degrees + math.degrees(turn)
        )
        self.distance_meters += advance
        self.laps_completed = int(
            self.distance_meters // max(1.0, c.DEFAULT_LAP_LENGTH_METERS)
        )
        self.record_recovery_pose(advance)
        return advance

    def advance_flight(self, delta_seconds: float, now_seconds: float) -> float:
        if not self.ride_active or not self.flight_enabled:
            return 0.0
        rider_power = (
            float(self.power_watts)
            if now_seconds - self.last_ftms_sample_seconds <= c.SAMPLE_STALE_SECONDS
            else 0.0
        )
        self.propulsion_power_watts = (
            self.tuning_controls.values.test_propulsion_power_watts
            if self.tuning_controls.active
            else rider_power
        )
        result = step_human_powered_flight(
            self.flight,
            self.propulsion_power_watts,
            self.digital_controls.pitch_degrees,
            self.digital_controls.bank_degrees,
            self.effective_steering_degrees,
            delta_seconds,
            True,
            self.tuning_controls.values,
        )
        if result.took_off:
            self.last_flight_event = "TAKEOFF"
        elif result.stall_started:
            self.last_flight_event = "STALL - NOSE DOWN"
        elif result.stall_recovered:
            self.last_flight_event = "STALL RECOVERED"
        elif result.landed:
            self.last_flight_event = "LANDED"
        elif result.landing_blocked:
            self.last_flight_event = "LANDING REQUIRES COURSE"
        if (
            result.took_off
            or result.stall_started
            or result.stall_recovered
            or result.landed
            or result.landing_blocked
        ):
            print(
                "ARRIETTY_FLIGHT_EVENT "
                f"{self.last_flight_event} "
                f"speed={self.flight.airspeed_meters_per_second * 3.6:.1f}km/h "
                f"alt={self.flight.altitude_meters:.1f}m "
                f"pitch={self.flight.pitch_degrees:+.1f} "
                f"bank={self.flight.bank_degrees:+.1f}",
                flush=True,
            )

        delta = max(0.0, min(0.25, delta_seconds))
        turn_degrees = self.flight.heading_rate_degrees_per_second * delta
        midpoint_heading = math.radians(
            self.heading_degrees + turn_degrees * 0.5
        )
        horizontal_speed = math.sqrt(
            max(
                0.0,
                self.flight.airspeed_meters_per_second**2
                - self.flight.vertical_speed_meters_per_second**2,
            )
        )
        advance = horizontal_speed * delta
        self.position_x_meters += math.sin(midpoint_heading) * advance
        self.position_y_meters -= math.cos(midpoint_heading) * advance
        self.heading_degrees = _unwind_degrees(
            self.heading_degrees + turn_degrees
        )
        self.speed_kmh = self.flight.airspeed_meters_per_second * 3.6
        self.distance_meters += advance
        self.laps_completed = int(
            self.distance_meters // max(1.0, c.DEFAULT_LAP_LENGTH_METERS)
        )
        self.record_recovery_pose(advance)
        return advance

    def fan_apparent_speed_kmh(self) -> float:
        """Return rider-relative airflow for the physical fan.

        Ground mode follows bicycle ground speed. In flight it follows the
        simulated glider airspeed, so airflow continues while gliding even
        when T2 cadence or wheel speed falls.
        """
        if not self.ride_active:
            return 0.0
        if self.flight_enabled:
            return max(0.0, self.flight.airspeed_meters_per_second * 3.6)
        return max(0.0, self.ground_speed_kmh)

    def update_steering_state(self) -> None:
        snapshot = self.steering.snapshot()
        self.steering_tracking = snapshot.tracking
        self.steering_status = snapshot.status
        self.steering_message = snapshot.message
        self.raw_steering_degrees = snapshot.raw_angle_degrees
        self.effective_steering_degrees = snapshot.effective_angle_degrees

    def reset_recovery_trail(self) -> None:
        self.recovery_path_distance_meters = 0.0
        self.last_recovery_sample_meters = 0.0
        self.recovery_trail = [
            (
                0.0,
                self.position_x_meters,
                self.position_y_meters,
                self.heading_degrees,
            )
        ]

    def record_recovery_pose(self, advance_meters: float) -> None:
        self.recovery_path_distance_meters += max(0.0, advance_meters)
        if (
            self.recovery_path_distance_meters - self.last_recovery_sample_meters
            < 0.1
        ):
            return
        self.recovery_trail.append(
            (
                self.recovery_path_distance_meters,
                self.position_x_meters,
                self.position_y_meters,
                self.heading_degrees,
            )
        )
        self.last_recovery_sample_meters = self.recovery_path_distance_meters
        del self.recovery_trail[:-256]

    def recover_two_meters(self) -> float:
        if not self.recovery_trail:
            self.reset_recovery_trail()
        target_distance = max(0.0, self.recovery_path_distance_meters - 2.0)
        target_pose = self.recovery_trail[0]
        for pose in self.recovery_trail:
            if pose[0] > target_distance:
                break
            target_pose = pose
        recovered = max(0.0, self.recovery_path_distance_meters - target_pose[0])
        _, self.position_x_meters, self.position_y_meters, self.heading_degrees = (
            target_pose
        )
        self.reset_recovery_trail()
        return recovered

    def move_manual(self, direction: float) -> None:
        heading = math.radians(self.heading_degrees)
        distance = direction * c.DEFAULT_MOVE_STEP_METERS
        self.position_x_meters += math.sin(heading) * distance
        self.position_y_meters -= math.cos(heading) * distance

    def turn_manual(self, direction: float) -> None:
        self.heading_degrees = _unwind_degrees(
            self.heading_degrees + direction * c.DEFAULT_TURN_STEP_DEGREES
        )

    def stop_services(self) -> None:
        if self.flight_log is not None:
            self.flight_log.sample(self, time.monotonic(), force=True)
            if not self.flight_log.close():
                print("ARRIETTY_FLIGHT_LOG_STOP_TIMEOUT", flush=True)
            self.flight_log = None
        if not self.bluetooth.stop():
            print("ARRIETTY_BLUETOOTH_STOP_TIMEOUT", flush=True)
        self.ride_active = False
        self.speed_kmh = 0.0
        self.ground_speed_kmh = 0.0
        self.flight_enabled = False
        self.voice.close()
        if not self.steering.stop():
            print("ARRIETTY_STEERING_STOP_TIMEOUT", flush=True)
        self.fan.stop()
        if not self.serial.stop():
            print("ARRIETTY_CONTROLLER_STOP_TIMEOUT", flush=True)


_state: RuntimeState | None = None


def _unwind_degrees(value: float) -> float:
    result = math.fmod(value, 360.0)
    if result > 180.0:
        result -= 360.0
    elif result < -180.0:
        result += 360.0
    return result


def _initial_heading_degrees(game_object) -> float:
    try:
        heading = float(game_object.get("initial_heading_degrees", 0.0))
    except (AttributeError, TypeError, ValueError):
        return 0.0
    return _unwind_degrees(heading) if math.isfinite(heading) else 0.0


def _update_navigation(runtime: RuntimeState) -> None:
    """Update the no-bpy heading tape and bearing back to the ride start."""
    # Secret World uses a local East-North-Up plane (X east, Y north), while
    # the accepted OpenXR vehicle forward axis is local/world Y-. Convert the
    # simulation yaw to the conventional clockwise bearing from true north.
    runtime.navigation_heading_degrees = (
        180.0 - runtime.heading_degrees
    ) % 360.0
    home_dx = runtime.start_position_x_meters - runtime.position_x_meters
    home_dy = runtime.start_position_y_meters - runtime.position_y_meters
    runtime.home_distance_meters = math.hypot(home_dx, home_dy)
    runtime.home_bearing_degrees = (
        runtime.navigation_heading_degrees
        if runtime.home_distance_meters < 1.0e-6
        else math.degrees(math.atan2(home_dx, home_dy)) % 360.0
    )
    runtime.home_relative_degrees = _unwind_degrees(
        runtime.home_bearing_degrees - runtime.navigation_heading_degrees
    )


def _sync_xr_navigation(runtime: RuntimeState, game_object, logic) -> bool:
    """Ask UPBGE's C++ bridge to copy the game-object pose into OpenXR."""
    previous_status = runtime.xr_bridge_status
    try:
        synced = bool(
            logic.syncOpenXRNavigation(
                game_object,
                runtime.hmd_alignment_degrees,
            )
        )
    except (AttributeError, RuntimeError):
        runtime.xr_bridge_status = "C++ BRIDGE MISSING"
        runtime.xr_navigation_synced = False
        if runtime.xr_bridge_status != previous_status:
            print(f"ARRIETTY_OPENXR_BRIDGE {runtime.xr_bridge_status}", flush=True)
        return False

    runtime.xr_navigation_synced = synced
    runtime.xr_bridge_status = "SYNCED" if synced else "WAITING FOR OPENXR"
    if runtime.xr_bridge_status != previous_status:
        print(f"ARRIETTY_OPENXR_BRIDGE {runtime.xr_bridge_status}", flush=True)
    return synced


def _vehicle_orientation(runtime: RuntimeState):
    from mathutils import Quaternion

    heading = Quaternion(
        (0.0, 0.0, 1.0), math.radians(runtime.heading_degrees)
    )
    if not runtime.flight.airborne:
        return heading.to_matrix()
    pitch = Quaternion(
        (1.0, 0.0, 0.0), math.radians(-runtime.flight.pitch_degrees)
    )
    bank = Quaternion(
        # Local forward is -Y, so the left wing is +X. Positive internal
        # bank turns left and must lower +X, which requires positive Y rotation.
        (0.0, 1.0, 0.0), math.radians(runtime.flight.bank_degrees)
    )
    return (heading @ pitch @ bank).to_matrix()


def _quaternion_forward_heading_degrees(rotation) -> float | None:
    """Return the horizontal heading of an XR viewer's local -Z axis."""
    w, x, y, z = (float(value) for value in rotation)
    forward_x = -2.0 * (x * z + w * y)
    forward_y = 2.0 * (w * x - y * z)
    if math.hypot(forward_x, forward_y) < 0.1:
        return None
    # Heading zero follows this scene's accepted OpenXR forward axis, Y-.
    return math.degrees(math.atan2(forward_x, -forward_y))


def _quaternion_z_rotation_degrees(rotation) -> float:
    w, x, y, z = (float(value) for value in rotation)
    return math.degrees(
        math.atan2(
            2.0 * (w * z + x * y),
            1.0 - 2.0 * (y * y + z * z),
        )
    )


def _try_align_hmd_to_bike(runtime: RuntimeState, now: float, logic) -> bool:
    # Rendered OpenXR scenes can take longer than a second to publish their
    # first valid viewer pose. Keep trying after Button 1 instead of silently
    # leaving all ground and flight movement locked behind a missed deadline.
    if runtime.hmd_aligned or not runtime.ride_active:
        return runtime.hmd_aligned
    try:
        viewer_rotation = logic.getOpenXRViewerRotation()
        navigation_rotation = logic.getOpenXRNavigationRotation()
        if viewer_rotation is None or navigation_rotation is None:
            runtime.hmd_alignment_message = "WAITING FOR VALID OPENXR HMD POSE"
            return False
        viewer_heading = _quaternion_forward_heading_degrees(
            viewer_rotation
        )
        if viewer_heading is None:
            runtime.hmd_alignment_message = "HMD FORWARD POSE IS NOT VALID"
            return False
        navigation_heading = _quaternion_z_rotation_degrees(
            navigation_rotation
        )
        correction = _unwind_degrees(
            runtime.heading_degrees - viewer_heading
        )
        corrected_navigation = _unwind_degrees(
            navigation_heading + correction
        )
        runtime.hmd_alignment_degrees = _unwind_degrees(
            corrected_navigation - runtime.heading_degrees
        )
        runtime.hmd_aligned = True
        runtime.hmd_alignment_message = (
            f"HMD ALIGNED {runtime.hmd_alignment_degrees:+.1f} DEG"
        )
        return True
    except (AttributeError, RuntimeError, TypeError, ValueError):
        runtime.hmd_alignment_message = "WAITING FOR VALID OPENXR HMD POSE"
        return False


def _reset_xr_navigation(logic) -> bool:
    try:
        return bool(logic.resetOpenXRNavigation())
    except (AttributeError, RuntimeError):
        return False


def reset() -> RuntimeState:
    global _state
    _state = RuntimeState()
    return _state


def state() -> RuntimeState:
    return _state if _state is not None else reset()


def tick(controller) -> None:
    """Logic-brick module function called once per game tick."""
    runtime = state()
    owner = controller.owner
    now = time.monotonic()
    delta = max(0.0, min(0.25, now - runtime.previous_tick_at))
    runtime.previous_tick_at = now
    runtime.frame_count += 1

    if runtime.frame_count == 1:
        runtime.heading_degrees = _initial_heading_degrees(owner)
        runtime.navigation_heading_degrees = (
            180.0 - runtime.heading_degrees
        ) % 360.0
        try:
            initial_position = owner.worldPosition
            runtime.position_x_meters = float(initial_position[0])
            runtime.position_y_meters = float(initial_position[1])
        except (AttributeError, TypeError, ValueError):
            runtime.position_x_meters = 0.0
            runtime.position_y_meters = 0.0
        runtime.start_position_x_meters = runtime.position_x_meters
        runtime.start_position_y_meters = runtime.position_y_meters
        runtime.flight_log = FlightLog.for_session()
        owner["arrietty_status"] = "RUNNING"
        owner["arrietty_version"] = c.VERSION
        owner["controller_status"] = "STARTING"
        owner["controller_pressed_latch"] = 0
        owner["controller_released_latch"] = 0
        owner["controller_transition_count"] = 0
        owner["controller_last_transition"] = ""
        owner["controller_history"] = ""
        owner["ride_active"] = False
        owner["bluetooth_status"] = "IDLE"
        owner["heart_rate_status"] = "DISCONNECTED"
        owner["xr_bridge_status"] = "NOT CHECKED"
        runtime.fan.start()
        runtime.serial.start()
        runtime.steering.start()
        if runtime.prepare_devices():
            print("ARRIETTY_BLUETOOTH_PREPARING", flush=True)
        print("ARRIETTY_UP_RUNTIME_READY", flush=True)

    owner["controller_pressed"] = 0
    owner["controller_released"] = 0
    for event in runtime.serial.drain_events():
        if event.message:
            owner["controller_status"] = event.message
            print(f"ARRIETTY_CONTROLLER {event.message}", flush=True)
        if event.type is ControllerEventType.CONNECTED:
            owner["controller_port"] = event.port
        elif event.type is ControllerEventType.DISCONNECTED:
            owner["controller_port"] = ""
        elif event.type is ControllerEventType.SAMPLE and event.sample is not None:
            sample = event.sample
            runtime.controller_sample_count += 1
            if sample.button_mask:
                runtime.controller_nonzero_samples += 1
            owner["controller_sequence"] = sample.sequence
            owner["controller_j1_x"] = sample.joystick1[0]
            owner["controller_j1_y"] = sample.joystick1[1]
            owner["controller_j2_x"] = sample.joystick2[0]
            owner["controller_j2_y"] = sample.joystick2[1]
            owner["controller_buttons"] = sample.button_mask
            transition = runtime.button_edges.update(sample)
            if transition is not None:
                owner["controller_pressed"] |= transition.pressed
                owner["controller_released"] |= transition.released
                entry = (
                    f"seq={transition.sequence} "
                    f"0x{transition.previous:02X}->0x{transition.current:02X} "
                    f"pressed=0x{transition.pressed:02X} "
                    f"released=0x{transition.released:02X}"
                )
                runtime.button_history.append(entry)
                del runtime.button_history[:-16]
                owner["controller_last_transition"] = entry
                owner["controller_history"] = " | ".join(runtime.button_history)
                print(
                    f"ARRIETTY_CONTROLLER_BUTTONS {entry}",
                    flush=True,
                )
                if transition.pressed & 0x01:
                    if runtime.start_ride():
                        print("ARRIETTY_RIDE_START BUTTON1", flush=True)
                    elif runtime.last_start_action == "SAFETY_RETURN":
                        print(
                            "ARRIETTY_SAFETY_RETURN "
                            f"{runtime.last_recovered_meters:.3f}m BUTTON1",
                            flush=True,
                        )
                if (transition.pressed | transition.released) & 0x20:
                    runtime.set_brake_button_held(bool(transition.current & 0x20))
            runtime.handle_controller_input(sample, transition, now)

    import bge

    if runtime.bluetooth_generation > 0:
        for event in runtime.bluetooth.drain_events():
            had_ftms = runtime.first_ftms_after_seconds > 0.0
            had_heart_rate = runtime.first_heart_rate_after_seconds > 0.0
            runtime.handle_bluetooth_event(event)
            if (
                event.type is BluetoothEventType.TRAINER_SAMPLE
                and not had_ftms
                and runtime.first_ftms_after_seconds > 0.0
            ):
                print(
                    "ARRIETTY_FIRST_FTMS "
                    f"t={runtime.first_ftms_after_seconds:.3f}s",
                    flush=True,
                )
            if (
                event.type is BluetoothEventType.HEART_RATE_SAMPLE
                and not had_heart_rate
                and runtime.first_heart_rate_after_seconds > 0.0
            ):
                print(
                    "ARRIETTY_FIRST_HEART_RATE "
                    f"t={runtime.first_heart_rate_after_seconds:.3f}s",
                    flush=True,
                )
            if event.message:
                print(
                    "ARRIETTY_BLUETOOTH "
                    f"{event.type.value} "
                    f"t={runtime.connection_elapsed(event.received_at):.3f}s: "
                    f"{event.message}",
                    flush=True,
                )
    runtime.flush_flight_button(now)
    runtime.update_sensor_state(now)
    runtime.update_ride_elapsed(now)
    runtime.update_steering_state()
    _try_align_hmd_to_bike(runtime, now, bge.logic)
    voice_status = runtime.voice.poll()
    if voice_status is not None:
        runtime.voice_status = voice_status[0]
    advanced = 0.0
    if runtime.ride_active and runtime.steering_tracking and runtime.hmd_aligned:
        advanced = (
            runtime.advance_flight(delta, now)
            if runtime.flight_enabled
            else runtime.advance_ground(delta)
        )
    if (
        advanced > 0.0
        and runtime.first_motion_after_seconds <= 0.0
        and runtime.ride_started_at_seconds > 0.0
    ):
        runtime.first_motion_after_seconds = max(
            0.0, now - runtime.ride_started_at_seconds
        )
        print(
            "ARRIETTY_FIRST_MOTION "
            f"t={runtime.first_motion_after_seconds:.3f}s",
            flush=True,
        )

    owner["controller_sample_count"] = runtime.controller_sample_count
    owner["controller_nonzero_samples"] = runtime.controller_nonzero_samples
    owner["controller_pressed_latch"] = runtime.button_edges.pressed_latch
    owner["controller_released_latch"] = runtime.button_edges.released_latch
    owner["controller_transition_count"] = runtime.button_edges.transition_count
    owner["ride_active"] = runtime.ride_active
    owner["ride_elapsed_seconds"] = runtime.ride_elapsed_seconds
    owner["hmd_aligned"] = runtime.hmd_aligned
    owner["hmd_alignment_degrees"] = runtime.hmd_alignment_degrees
    owner["hmd_alignment_message"] = runtime.hmd_alignment_message
    owner["flight_enabled"] = runtime.flight_enabled
    owner["flight_airborne"] = runtime.flight.airborne
    owner["flight_stalled"] = runtime.flight.stalled
    owner["flight_event"] = runtime.last_flight_event
    owner["flight_command_pitch_degrees"] = runtime.digital_controls.pitch_degrees
    owner["flight_command_bank_degrees"] = runtime.digital_controls.bank_degrees
    owner["flight_tuning"] = runtime.tuning_controls.compact_status()
    owner["propulsion_power_watts"] = runtime.propulsion_power_watts
    owner["bluetooth_status"] = runtime.bluetooth_status
    owner["bluetooth_message"] = runtime.bluetooth_message
    owner["trainer_found_after_seconds"] = runtime.trainer_found_after_seconds
    owner["gatt_connected_after_seconds"] = runtime.gatt_connected_after_seconds
    owner["trainer_ready_after_seconds"] = runtime.trainer_ready_after_seconds
    owner["control_ready_after_seconds"] = runtime.control_ready_after_seconds
    owner["first_ftms_after_seconds"] = runtime.first_ftms_after_seconds
    owner["first_motion_after_seconds"] = runtime.first_motion_after_seconds
    owner["heart_rate_connected_after_seconds"] = (
        runtime.heart_rate_connected_after_seconds
    )
    owner["first_heart_rate_after_seconds"] = runtime.first_heart_rate_after_seconds
    owner["selected_preset"] = runtime.selected_preset
    owner["applied_preset"] = -1 if runtime.applied_preset is None else runtime.applied_preset
    owner["applied_grade_percent"] = runtime.applied_grade_percent
    owner["speed_kmh"] = runtime.speed_kmh
    owner["ground_speed_kmh"] = runtime.ground_speed_kmh
    owner["ftms_speed_kmh"] = runtime.ftms_speed_kmh
    owner["cadence_rpm"] = runtime.cadence_rpm
    owner["power_watts"] = runtime.power_watts
    owner["heart_rate_bpm"] = -1 if runtime.heart_rate_bpm is None else runtime.heart_rate_bpm
    owner["heart_rate_status"] = runtime.heart_rate_status
    owner["position_x_meters"] = runtime.position_x_meters
    owner["position_y_meters"] = runtime.position_y_meters
    owner["heading_degrees"] = runtime.heading_degrees
    owner["steering_tracking"] = runtime.steering_tracking
    owner["steering_status"] = runtime.steering_status
    owner["steering_message"] = runtime.steering_message
    owner["raw_steering_degrees"] = runtime.raw_steering_degrees
    owner["effective_steering_degrees"] = runtime.effective_steering_degrees
    owner["voice_status"] = runtime.voice_status
    owner["ptt_held"] = runtime.ptt_held
    owner["distance_meters"] = runtime.distance_meters
    owner["laps_completed"] = runtime.laps_completed
    owner["last_recovered_meters"] = runtime.last_recovered_meters
    owner.worldPosition = (
        runtime.position_x_meters,
        runtime.position_y_meters,
        runtime.flight.altitude_meters,
    )
    owner.worldOrientation = _vehicle_orientation(runtime)
    _update_navigation(runtime)
    if runtime.flight_log is not None:
        runtime.flight_log.sample(runtime, now)
        owner["flight_log_status"] = runtime.flight_log.error or "RECORDING"
        owner["flight_log_dropped_samples"] = runtime.flight_log.dropped_samples
    _sync_xr_navigation(runtime, owner, bge.logic)
    owner["xr_bridge_status"] = runtime.xr_bridge_status
    owner["navigation_heading_degrees"] = runtime.navigation_heading_degrees
    owner["home_bearing_degrees"] = runtime.home_bearing_degrees
    owner["home_relative_degrees"] = runtime.home_relative_degrees
    owner["home_distance_meters"] = runtime.home_distance_meters
    fan_before = (
        runtime.fan.status,
        runtime.fan.requested_level,
        runtime.fan.reported_level,
    )
    fan_speed_kmh = runtime.fan_apparent_speed_kmh()
    runtime.fan.tick(fan_speed_kmh, now)
    fan_after = (
        runtime.fan.status,
        runtime.fan.requested_level,
        runtime.fan.reported_level,
    )
    if fan_after != fan_before:
        print(
            "ARRIETTY_FAN "
            f"speed={fan_speed_kmh:.1f}km/h "
            f"requested={runtime.fan.requested_level} "
            f"reported={runtime.fan.reported_level} "
            f"status={runtime.fan.status}",
            flush=True,
        )
    owner["fan_status"] = runtime.fan.status
    owner["fan_connected"] = runtime.fan.connected
    owner["fan_speed_kmh"] = fan_speed_kmh
    owner["fan_requested_level"] = runtime.fan.requested_level
    owner["fan_reported_level"] = (
        -1 if runtime.fan.reported_level is None else runtime.fan.reported_level
    )
    fan_response_age = runtime.fan.response_age_seconds(now)
    owner["fan_response_age_seconds"] = (
        -1.0 if fan_response_age is None else fan_response_age
    )
    owner["fan_packets_sent"] = runtime.fan.packets_sent
    owner["fan_packets_received"] = runtime.fan.packets_received
    owner["fan_invalid_responses"] = runtime.fan.invalid_responses

    owner["arrietty_frames"] = runtime.frame_count
    owner["arrietty_delta_ms"] = round(delta * 1000.0, 3)
    update_upbge_panel(bge.logic.getCurrentScene(), runtime, delta)

    # The scene disables UPBGE's immediate exit key so worker threads can stop
    # before the engine tears down the Python runtime.
    if (
        not runtime.ending
        and bge.logic.keyboard.inputs[bge.events.ESCKEY].activated
    ):
        runtime.ending = True
        owner["arrietty_status"] = "STOPPING"
        runtime.stop_services()
        _reset_xr_navigation(bge.logic)
        print("ARRIETTY_UP_RUNTIME_STOPPED", flush=True)
        bge.logic.endGame()


def shutdown() -> None:
    """Release runtime services before a game session is restarted."""
    global _state
    if _state is not None:
        _state.stop_services()
    _state = None
