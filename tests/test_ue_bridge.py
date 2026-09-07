import json
import math
from pathlib import Path
import tempfile
import time
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

from arrietty_ue.bridge import Simulation, ue_pose, valid_packet
from arrietty_up.runtime import RuntimeState

WORLD=dict(initial_heading_degrees=0., output_name='fixture.blend', origin_latitude=-8.5, origin_longitude=179.2)


class UEBridgeTests(unittest.TestCase):
    def test_loopback_watchdog_and_reordered_packets(self):
        with tempfile.TemporaryDirectory() as td, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client:
            root=Path(td)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
                probe.bind(('127.0.0.1',0))
                port=probe.getsockname()[1]
            token='t'*64
            (root/'world.json').write_text(json.dumps(WORLD))
            (root/'session.json').write_text(json.dumps(dict(token=token,port=port)))
            process=subprocess.Popen([sys.executable,'-u','-m','arrietty_ue.bridge','--world',str(root/'world.json'),'--session',str(root/'session.json'),'--log-path',str(root/'flight.csv')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            client.settimeout(.1)
            seq=0
            def exchange(**values):
                nonlocal seq
                seq+=1
                packet=dict(protocol=1,token=token,seq=seq,play=True,hmd_valid=True,aligned=0,buttons=0)
                packet.update(values)
                client.sendto(json.dumps(packet).encode(),('127.0.0.1',port))
                return json.loads(client.recv(8192))
            try:
                for _ in range(50):
                    try:
                        out=exchange(play=False)
                        break
                    except (TimeoutError,ConnectionResetError):
                        time.sleep(.02)
                else: self.fail('Bridge failed to start')
                client.settimeout(2)
                exchange()
                out=exchange(buttons=1)
                self.assertTrue(out['ride'])
                aligned=out['align_request']
                exchange(aligned=aligned,speed=27)
                time.sleep(1.3)
                out=exchange(aligned=aligned,speed=27)
                self.assertFalse(out['ride'])
                self.assertEqual(out['pose'][0:3],[0,0,0])
                client.settimeout(.15)
                with self.assertRaises(TimeoutError): exchange(seq=1)
                client.sendto(json.dumps(dict(protocol=1,token=token,seq=seq+1,play=False,quit=True)).encode(),('127.0.0.1',port))
                stdout,stderr=process.communicate(timeout=5)
                self.assertEqual(process.returncode,0,stderr)
                self.assertIn('ARRIETTY_UE_WATCHDOG_STOP',stdout)
                self.assertIn('ARRIETTY_UE_BRIDGE_STOPPED',stdout)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)

    def test_coordinate_bearings_and_attitude(self):
        s=RuntimeState(position_x_meters=2,position_y_meters=3)
        self.assertEqual(ue_pose(s),[300,200,0,0,180,0])
        for heading,bearing in [(0,180),(90,90),(180,0),(-90,270)]:
            s.heading_degrees=heading
            self.assertEqual(ue_pose(s)[4],bearing)
        s.flight.airborne=True
        s.flight.pitch_degrees=6
        s.flight.bank_degrees=10
        s.flight.altitude_meters=2
        self.assertEqual(ue_pose(s)[2:4],[200,6])
        self.assertEqual(ue_pose(s)[5],-10)

    def test_pedalling_matches_ue_forward_for_every_bearing(self):
        for heading in [*range(-180,181,15), -43.075]:
            with self.subTest(heading=heading):
                s=RuntimeState(heading_degrees=heading,ride_active=True,speed_kmh=18)
                s.advance_ground(.1)
                pose=ue_pose(s)
                yaw=math.radians(pose[4])
                # UE's actual +X-forward basis is also checked by native tests.
                self.assertAlmostEqual(pose[0],50*math.cos(yaw))
                self.assertAlmostEqual(pose[1],50*math.sin(yaw))

    def test_recenter_stops_motion_until_new_camera_ack_without_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            sim=Simulation(WORLD,log_path=Path(td)/'flight.csv')
            p=dict(play=True,buttons=0,aligned=0,hmd_valid=True,speed=27)
            try:
                sim.step(p,.02)
                out=sim.step(dict(p,buttons=1),.02)
                p['aligned']=out['align_request']
                sim.step(p,.05)
                position=ue_pose(sim.state)[:3]
                started=sim.state.ride_started_at_seconds
                p['recenter_id']=1
                with patch.object(sim.state.steering,'recenter') as center:
                    out=sim.step(p,.05)
                    self.assertEqual(out['recenter_id'],1)
                    self.assertNotEqual(out['align_request'],p['aligned'])
                    self.assertEqual(ue_pose(sim.state)[:3],position)
                    self.assertEqual(sim.state.ride_started_at_seconds,started)
                    sim.step(p,.05)  # repeated UDP frames must not recenter again
                    center.assert_called_once()
                    self.assertEqual(ue_pose(sim.state)[:3],position)
                p['aligned']=out['align_request']
                sim.step(p,.05)
                self.assertNotEqual(ue_pose(sim.state)[:3],position)
            finally:
                sim.stop()

    def test_untrusted_packets(self):
        p=dict(protocol=1,token='t',seq=1,play=True)
        self.assertIsNotNone(valid_packet(json.dumps(p),'t'))
        self.assertIsNone(valid_packet(json.dumps(p),'wrong'))
        self.assertIsNone(valid_packet(b'[]','t'))
        self.assertIsNone(valid_packet(json.dumps(dict(p,power=float('nan'))),'t'))
        self.assertIsNone(valid_packet(json.dumps(dict(p,seq=True)),'t'))
        self.assertIsNone(valid_packet(json.dumps(dict(p,alignment_bearing=float('nan'))),'t'))
        self.assertIsNone(valid_packet(json.dumps(dict(p,alignment_bearing=True)),'t'))

    def test_hmd_bearing_is_latched_before_first_motion(self):
        with tempfile.TemporaryDirectory() as td:
            for bearing in (0,90,180,270,201.385):
                with self.subTest(bearing=bearing):
                    sim=Simulation(WORLD,log_path=Path(td)/'flight.csv')
                    p=dict(play=True,buttons=0,aligned=0,hmd_valid=True,speed=18)
                    try:
                        sim.step(p,.02)
                        out=sim.step(dict(p,buttons=1),.02)
                        p.update(aligned=out['align_request'],alignment_bearing=bearing)
                        out=sim.step(p,.05)
                        self.assertEqual(out['alignment_applied'],p['aligned'])
                        self.assertAlmostEqual(out['pose'][4],bearing)
                        yaw=math.radians(bearing)
                        self.assertAlmostEqual(out['pose'][0],25*math.cos(yaw))
                        self.assertAlmostEqual(out['pose'][1],25*math.sin(yaw))
                        self.assertAlmostEqual((180-sim.state.recovery_trail[0][3])%360,bearing)
                        # Neither a new gaze value nor stale alignment frames
                        # may keep steering the bicycle after Button 1.
                        out=sim.step(dict(p,alignment_bearing=bearing+45),.05)
                        self.assertAlmostEqual(out['pose'][4],bearing)
                        position=out['pose'][:3]
                        out=sim.step(dict(p,aligned=0,alignment_bearing=bearing+90),.05)
                        self.assertEqual(out['pose'][:3],position)
                        self.assertAlmostEqual(out['pose'][4],bearing)
                    finally:
                        sim.stop()

    def test_live_alignment_requires_a_confirmed_bearing(self):
        with tempfile.TemporaryDirectory() as td:
            sim=Simulation(WORLD,log_path=Path(td)/'flight.csv')
            p=dict(play=True,buttons=0,aligned=0,hmd_valid=True,speed=18)
            try:
                sim.step(p,.02)
                out=sim.step(dict(p,buttons=1),.02)
                # All device instances were installed offline; only exercise
                # live protocol requirements, never open actual hardware.
                sim.hardware=True
                p['aligned']=out['align_request']
                for value in (None,float('nan'),True):
                    out=sim.step(dict(p,alignment_bearing=value),.05)
                    self.assertEqual(sim.state.distance_meters,0)
                    self.assertEqual(out['alignment_applied'],0)
                out=sim.step(dict(p,alignment_bearing=201.385),.05)
                self.assertAlmostEqual(out['pose'][4],201.385)
                self.assertGreater(sim.state.distance_meters,0)
            finally:
                sim.stop()

    def test_offline_never_opens_hardware_and_waits_for_alignment(self):
        with tempfile.TemporaryDirectory() as td, patch('arrietty_up.bluetooth.BluetoothManager.start',side_effect=AssertionError('BLE')), patch('arrietty_up.serial_controller.SerialController.start',side_effect=AssertionError('Serial')), patch('arrietty_up.steering.SteeringController.start',side_effect=AssertionError('VR')), patch('arrietty_up.fan.FanController.start',side_effect=AssertionError('Fan')):
            sim=Simulation(WORLD,log_path=Path(td)/'flight.csv')
            p=dict(play=False,buttons=0,aligned=0,hmd_valid=True,speed=27,power=250)
            sim.step(p,.01)
            self.assertIsNone(sim.state)
            p['play']=True
            sim.step(p,.01)
            p['buttons']=1
            out=sim.step(p,.01)
            self.assertTrue(out['ride'])
            self.assertEqual(sim.state.distance_meters,0)
            p.update(buttons=0,aligned=out['align_request'])
            out=sim.step(p,.05)
            self.assertGreater(sim.state.distance_meters,0)
            sim.step(dict(p,play=False),.01)
            self.assertIsNone(sim.state)
            text=(Path(td)/'flight.csv').read_text()
            self.assertIn('pitch_deg,roll_deg',text)

    def test_complete_flight_and_restart(self):
        with tempfile.TemporaryDirectory() as td, self.subTest('complete flight'):
            sim=Simulation(WORLD,log_path=Path(td)/'flight.csv')
            p=dict(play=True,buttons=0,aligned=0,hmd_valid=True,speed=27,power=250)
            try:
                sim.step(p,.02)
                out=sim.step(dict(p,buttons=1),.02)
                p['aligned']=out['align_request']
                sim.step(p,.02)
                sim.step(dict(p,buttons=2),.02)
                sim.step(p,.02)
                sim.step(dict(p,buttons=12),.02)  # physical Button 3+4 chord
                for _ in range(1600): out=sim.step(p,.02)
                self.assertTrue(out['airborne'])
                self.assertGreater(out['altitude'],0)
                before=sim.state.distance_meters
                for _ in range(10): sim.step(dict(p,hmd_valid=False),.02)
                self.assertEqual(sim.state.distance_meters,before)
                for _ in range(25000):
                    out=sim.step(dict(p,power=0,speed=0),.02)
                    if not out['airborne']: break
                self.assertFalse(out['airborne'])
                sim.stop()
                out=sim.step(p,.02)
                self.assertFalse(sim.state.ride_active)
                self.assertEqual(sim.state.distance_meters,0)
                self.assertEqual(out['align_request'],0)
                self.assertEqual(out['alignment_applied'],0)
            finally:
                sim.stop()


if __name__=='__main__': unittest.main()
