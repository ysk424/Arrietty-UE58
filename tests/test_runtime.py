import unittest

from arrietty_up.bluetooth import BluetoothEvent, BluetoothEventType
from arrietty_up.controller_protocol import ButtonTransition, ControllerSample
from arrietty_up.models import CscSample, TrainerSample
from arrietty_up.runtime import (
    RuntimeState,
    _initial_heading_degrees,
    _quaternion_forward_heading_degrees,
    _quaternion_z_rotation_degrees,
    _reset_xr_navigation,
    _sync_xr_navigation,
    _try_align_hmd_to_bike,
    _update_navigation,
)


class FakeBluetooth:
    def __init__(self):
        self.running = False
        self.generation = 0
        self.start_args = None
        self.grade_requests = []

    def start(self, preset, grade):
        self.running = True
        self.generation += 1
        self.start_args = (preset, grade)
        return self.generation

    def request_grade(self, grade):
        self.grade_requests.append(grade)

    def stop(self, _timeout=5.0):
        self.running = False
        return True


class FakeVoice:
    def __init__(self):
        self.ptt_held = False
        self.status = "IDLE"
        self.edges = []

    def set_ptt_held(self, held):
        self.ptt_held = held
        self.edges.append(held)
        self.status = "PTT" if held else "SENT"
        return True

    def poll(self):
        return None

    def close(self):
        pass


class FakeOpenXRLogic:
    def __init__(self):
        self.sync_args = None
        self.reset_count = 0

    def syncOpenXRNavigation(self, game_object, alignment_degrees):
        self.sync_args = (game_object, alignment_degrees)
        return True

    def getOpenXRViewerRotation(self):
        return (0.5, -0.5, -0.5, 0.5)

    def getOpenXRNavigationRotation(self):
        return (1.0, 0.0, 0.0, 0.0)

    def resetOpenXRNavigation(self):
        self.reset_count += 1
        return True


class RuntimeStateTests(unittest.TestCase):
    def make_state(self):
        state = RuntimeState()
        state.bluetooth = FakeBluetooth()
        state.voice = FakeVoice()
        return state

    @staticmethod
    def sample(sequence=1, j1=(0, 0), j2=(0, 0), buttons=0):
        return ControllerSample(sequence, j1[0], j1[1], j2[0], j2[1], buttons)

    @staticmethod
    def transition(previous, current, sequence=1):
        return ButtonTransition(
            sequence,
            previous,
            current,
            current & ~previous,
            previous & ~current,
        )

    def test_start_ride_and_brake_requests(self):
        state = self.make_state()
        state.ride_elapsed_seconds = 99.0
        self.assertTrue(state.start_ride())
        self.assertEqual(state.bluetooth_generation, 1)
        self.assertEqual(state.bluetooth.start_args, (5, 0.0))
        self.assertTrue(state.ride_active)
        self.assertEqual(state.ride_elapsed_seconds, 0.0)

        state.ride_started_at_seconds = 100.0
        state.update_ride_elapsed(161.75)
        self.assertEqual(state.ride_elapsed_seconds, 61.75)
        state.update_ride_elapsed(150.0)
        self.assertEqual(state.ride_elapsed_seconds, 61.75)

        state.set_brake_button_held(True)
        state.set_brake_button_held(True)
        state.set_brake_button_held(False)
        self.assertEqual(state.bluetooth.grade_requests, [3.0, 0.0])

    def test_devices_can_prepare_before_the_ride(self):
        state = self.make_state()
        self.assertTrue(state.prepare_devices())
        self.assertFalse(state.ride_active)
        self.assertEqual(state.bluetooth_generation, 1)
        self.assertFalse(state.prepare_devices())
        self.assertTrue(state.start_ride())
        self.assertTrue(state.ride_active)
        self.assertEqual(state.bluetooth.generation, 1)

    def test_brake_held_during_prepare_is_applied_at_ride_start(self):
        state = self.make_state()
        state.prepare_devices()
        state.set_brake_button_held(True)
        self.assertEqual(state.bluetooth.grade_requests, [])
        state.start_ride()
        self.assertEqual(state.bluetooth.grade_requests, [3.0])

    def test_repeated_start_does_not_claim_connection_is_ready(self):
        state = self.make_state()
        state.start_ride()
        state.bluetooth_status = "CONNECTING"
        state.bluetooth_message = "Connecting to T2"
        self.assertFalse(state.start_ride())
        self.assertEqual(state.bluetooth_status, "CONNECTING")
        self.assertEqual(state.bluetooth_message, "Connecting to T2")

    def test_connection_phase_timings(self):
        state = self.make_state()
        state.start_ride()
        state.connection_started_at_seconds = 90.0
        state.ride_started_at_seconds = 90.0
        state.handle_bluetooth_event(
            BluetoothEvent(
                1,
                BluetoothEventType.GATT_CONNECTED,
                "GATT connected",
                received_at=100.0,
            )
        )
        state.handle_bluetooth_event(
            BluetoothEvent(
                1,
                BluetoothEventType.TRAINER_READY,
                "T2 speed notifications active",
                received_at=101.5,
            )
        )
        self.assertEqual(state.gatt_connected_after_seconds, 10.0)
        self.assertEqual(state.trainer_ready_after_seconds, 11.5)
        self.assertEqual(state.bluetooth_status, "DATA READY")

    def test_ftms_and_heart_rate_events(self):
        state = self.make_state()
        state.start_ride()
        state.handle_bluetooth_event(
            BluetoothEvent(
                1,
                BluetoothEventType.TRAINER_SAMPLE,
                trainer_sample=TrainerSample(21.5, 82.0, 103),
                received_at=100.0,
            )
        )
        state.handle_bluetooth_event(
            BluetoothEvent(
                1,
                BluetoothEventType.HEART_RATE_SAMPLE,
                heart_rate_bpm=76,
                received_at=100.0,
            )
        )
        state.update_sensor_state(100.1)
        self.assertEqual((state.speed_kmh, state.cadence_rpm, state.power_watts), (21.5, 82.0, 103))
        self.assertEqual(state.heart_rate_bpm, 76)

        state.update_sensor_state(106.0)
        self.assertEqual(state.speed_kmh, 0.0)
        self.assertIsNone(state.heart_rate_bpm)
        self.assertEqual(state.heart_rate_status, "STALE - SEARCHING")

    def test_csc_motion_and_stop_timing(self):
        state = self.make_state()
        state.handle_csc_sample(10.0, CscSample(100, 1000, None, None))
        state.handle_csc_sample(11.0, CscSample(101, 2024, None, None))
        self.assertTrue(state.wheel_signal_received)
        self.assertEqual(state.last_wheel_motion_seconds, 11.0)
        self.assertAlmostEqual(state.wheel_period_seconds, 1.0)

        state.ftms_speed_kmh = 12.0
        state.cadence_rpm = 0.0
        state.last_ftms_sample_seconds = 13.0
        state.update_sensor_state(13.0)
        self.assertEqual(state.speed_kmh, 0.0)

    def test_stale_generation_is_ignored(self):
        state = self.make_state()
        state.start_ride()
        state.handle_bluetooth_event(
            BluetoothEvent(
                0,
                BluetoothEventType.HEART_RATE_SAMPLE,
                heart_rate_bpm=200,
                received_at=100.0,
            )
        )
        self.assertIsNone(state.heart_rate_bpm)

    def test_ground_and_manual_movement_use_openxr_forward(self):
        state = self.make_state()
        state.ride_active = True
        state.speed_kmh = 18.0
        self.assertAlmostEqual(state.advance_ground(0.2), 1.0)
        self.assertAlmostEqual(state.position_x_meters, 0.0)
        self.assertAlmostEqual(state.position_y_meters, -1.0)
        self.assertAlmostEqual(state.distance_meters, 1.0)

        state.move_manual(1.0)
        self.assertAlmostEqual(state.position_y_meters, -1.5)
        state.turn_manual(1.0)
        self.assertAlmostEqual(state.heading_degrees, 5.0)

    def test_second_start_returns_about_two_meters_on_ridden_path(self):
        state = self.make_state()
        state.start_ride()
        state.speed_kmh = 3.6
        for _ in range(30):
            state.advance_ground(0.1)
        distance_before = state.distance_meters

        self.assertFalse(state.start_ride())
        self.assertEqual(state.last_start_action, "SAFETY_RETURN")
        self.assertAlmostEqual(state.last_recovered_meters, 2.0, delta=0.11)
        self.assertAlmostEqual(state.position_y_meters, -1.0, delta=0.11)
        self.assertAlmostEqual(state.distance_meters, distance_before)

    def test_button_two_toggles_flight_and_airborne_blocks_ground_mode(self):
        state = self.make_state()
        state.start_ride()
        state.ground_speed_kmh = 24.0
        sample = self.sample(buttons=0x02)
        state.handle_controller_input(
            sample,
            self.transition(0, 0x02),
            1.0,
        )
        self.assertTrue(state.flight_enabled)
        self.assertAlmostEqual(state.flight.airspeed_meters_per_second, 24.0 / 3.6)

        state.flight.airborne = True
        state.handle_controller_input(
            self.sample(sequence=2, buttons=0x02),
            self.transition(0, 0x02, 2),
            2.0,
        )
        self.assertTrue(state.flight_enabled)
        self.assertEqual(state.last_mode_action, "LAND BEFORE GROUND MODE")

    def test_joystick_two_controls_and_reset_are_flight_only(self):
        state = self.make_state()
        axis = 26214
        state.handle_controller_input(self.sample(j2=(axis, 0)), None, 1.0)
        self.assertEqual(state.digital_controls.pitch_degrees, 0.0)

        state.start_ride()
        state.toggle_flight()
        state.handle_controller_input(self.sample(j2=(0, 0)), None, 1.9)
        state.handle_controller_input(self.sample(j2=(axis, 0)), None, 2.0)
        state.handle_controller_input(self.sample(j2=(axis, 0)), None, 2.1)
        self.assertEqual(state.digital_controls.pitch_degrees, 1.0)
        state.handle_controller_input(self.sample(j2=(0, 0)), None, 2.2)
        state.handle_controller_input(self.sample(j2=(0, -axis)), None, 2.3)
        self.assertEqual(state.digital_controls.roll_right_degrees, 1.0)

        state.handle_controller_input(
            self.sample(buttons=0x80),
            self.transition(0, 0x80),
            2.4,
        )
        self.assertEqual(state.digital_controls.pitch_degrees, 0.0)
        self.assertEqual(state.digital_controls.roll_right_degrees, 0.0)

    def test_button_three_four_chord_and_single_roll(self):
        state = self.make_state()
        state.start_ride()
        state.toggle_flight()
        state.handle_controller_input(
            self.sample(buttons=0x04),
            self.transition(0, 0x04),
            1.0,
        )
        state.handle_controller_input(
            self.sample(sequence=2, buttons=0x0C),
            self.transition(0x04, 0x0C, 2),
            1.05,
        )
        self.assertEqual(state.digital_controls.pitch_degrees, 1.0)
        self.assertEqual(state.digital_controls.roll_right_degrees, 0.0)

        state.handle_controller_input(
            self.sample(sequence=3, buttons=0x04),
            self.transition(0, 0x04, 3),
            2.0,
        )
        state.flush_flight_button(2.081)
        self.assertEqual(state.digital_controls.roll_right_degrees, -1.0)

    def test_joystick_one_tuning_and_button_five_ptt(self):
        state = self.make_state()
        state.start_ride()
        state.toggle_flight()
        state.handle_controller_input(
            self.sample(buttons=0x40),
            self.transition(0, 0x40),
            1.0,
        )
        self.assertTrue(state.tuning_controls.active)
        state.handle_controller_input(self.sample(j1=(26214, 0)), None, 1.1)
        self.assertEqual(
            state.tuning_controls.values.test_propulsion_power_watts,
            100.0,
        )

        state.handle_controller_input(
            self.sample(sequence=2, buttons=0x10),
            self.transition(0, 0x10, 2),
            2.0,
        )
        state.handle_controller_input(
            self.sample(sequence=3),
            self.transition(0x10, 0, 3),
            2.1,
        )
        self.assertEqual(state.voice.edges, [True, False])

    def test_flight_step_uses_rider_power_and_advances_in_openxr_forward(self):
        state = self.make_state()
        state.start_ride()
        state.ground_speed_kmh = 24.0
        state.toggle_flight()
        state.power_watts = 140
        state.last_ftms_sample_seconds = 100.0
        state.digital_controls.pitch_degrees = 1.0
        total = 0.0
        for index in range(20):
            now = 100.0 + index * 0.1
            state.last_ftms_sample_seconds = now
            total += state.advance_flight(0.1, now)
        self.assertTrue(state.flight.airborne)
        self.assertGreater(total, 0.0)
        self.assertAlmostEqual(state.position_x_meters, 0.0)
        self.assertLess(state.position_y_meters, 0.0)
        self.assertGreater(state.flight.altitude_meters, 0.0)
        self.assertEqual(state.propulsion_power_watts, 140.0)

    def test_fan_uses_ground_speed_then_glider_airspeed(self):
        state = self.make_state()
        state.ground_speed_kmh = 18.0
        self.assertEqual(state.fan_apparent_speed_kmh(), 0.0)

        state.ride_active = True
        self.assertEqual(state.fan_apparent_speed_kmh(), 18.0)

        state.flight_enabled = True
        state.flight.airspeed_meters_per_second = 10.0
        state.ground_speed_kmh = 0.0
        self.assertEqual(state.fan_apparent_speed_kmh(), 36.0)

    def test_xr_quaternion_heading_helpers_follow_scene_forward(self):
        self.assertAlmostEqual(
            _quaternion_forward_heading_degrees((0.5, -0.5, -0.5, 0.5)),
            90.0,
        )
        root_half = 2.0**-0.5
        self.assertAlmostEqual(
            _quaternion_z_rotation_degrees((root_half, 0, 0, root_half)),
            90.0,
        )

    def test_scene_initial_heading_is_validated_and_unwound(self):
        self.assertEqual(_initial_heading_degrees({}), 0.0)
        self.assertEqual(
            _initial_heading_degrees({"initial_heading_degrees": 315.0}),
            -45.0,
        )
        self.assertEqual(
            _initial_heading_degrees({"initial_heading_degrees": "invalid"}),
            0.0,
        )

    def test_cpp_openxr_bridge_sync_alignment_and_reset(self):
        state = self.make_state()
        state.hmd_alignment_degrees = -12.5
        state.ride_active = True
        owner = object()
        logic = FakeOpenXRLogic()

        self.assertTrue(_sync_xr_navigation(state, owner, logic))
        self.assertEqual(logic.sync_args, (owner, -12.5))
        self.assertTrue(state.xr_navigation_synced)
        self.assertEqual(state.xr_bridge_status, "SYNCED")

        self.assertTrue(_try_align_hmd_to_bike(state, 1000.0, logic))
        self.assertAlmostEqual(state.hmd_alignment_degrees, -90.0)
        self.assertTrue(_reset_xr_navigation(logic))
        self.assertEqual(logic.reset_count, 1)

    def test_navigation_points_back_to_the_ride_start(self):
        state = self.make_state()
        state.start_position_x_meters = 10.0
        state.start_position_y_meters = 20.0
        state.position_x_meters = 10.0
        state.position_y_meters = 10.0
        state.heading_degrees = 90.0

        _update_navigation(state)

        self.assertEqual(state.navigation_heading_degrees, 90.0)
        self.assertEqual(state.home_bearing_degrees, 0.0)
        self.assertEqual(state.home_relative_degrees, -90.0)
        self.assertEqual(state.home_distance_meters, 10.0)

    def test_hmd_alignment_waits_for_a_valid_rendered_pose(self):
        class DelayedOpenXRLogic(FakeOpenXRLogic):
            def __init__(self):
                super().__init__()
                self.pose_ready = False

            def getOpenXRViewerRotation(self):
                return (
                    super().getOpenXRViewerRotation()
                    if self.pose_ready
                    else None
                )

        state = self.make_state()
        state.ride_active = True
        logic = DelayedOpenXRLogic()

        self.assertFalse(_try_align_hmd_to_bike(state, 1.0, logic))
        self.assertEqual(
            state.hmd_alignment_message,
            "WAITING FOR VALID OPENXR HMD POSE",
        )

        logic.pose_ready = True
        self.assertTrue(_try_align_hmd_to_bike(state, 10.0, logic))
        self.assertTrue(state.hmd_aligned)


if __name__ == "__main__":
    unittest.main()
