import unittest

from arrietty_up.controller_protocol import ButtonEdgeLatch, is_pressed, parse_state_line
from arrietty_up.trainer_protocol import (
    build_flat_road_control_command,
    build_simulation_control_command,
    completed_laps,
    control_result_name,
    effective_speed_kmh,
    effective_steering_degrees,
    heading_degrees_for_world_forward,
    parse_control_response,
    parse_csc_measurement,
    parse_heart_rate_measurement,
    parse_indoor_bike_data,
    requires_ride_surface,
    wheel_stop_timeout_seconds,
)


class ControllerProtocolTests(unittest.TestCase):
    def test_valid_state(self):
        sample = parse_state_line("A1,42,-32767,0,32767,1234,137")
        self.assertIsNotNone(sample)
        self.assertEqual((sample.sequence, sample.joystick1_x, sample.joystick2_x), (42, -32767, 32767))
        self.assertTrue(sample.is_pressed(0))
        self.assertTrue(sample.is_pressed(3))
        self.assertTrue(sample.is_pressed(7))
        self.assertFalse(sample.is_pressed(1))
        self.assertTrue(is_pressed(0x10, 4))
        self.assertTrue(is_pressed(0x20, 5))

    def test_invalid_states(self):
        for line in (
            "A2,42,0,0,0,0,0",
            "A1,42,0,0,0,0",
            "A1,42,32768,0,0,0,0",
            "A1,42,0,0,0,0,256",
            "A1,not-a-number,0,0,0,0,0",
        ):
            self.assertIsNone(parse_state_line(line), line)

    def test_button_edges_remain_latched_after_release(self):
        latch = ButtonEdgeLatch()
        baseline = parse_state_line("A1,100,0,0,0,0,0")
        pressed = parse_state_line("A1,101,0,0,0,0,1")
        released = parse_state_line("A1,102,0,0,0,0,0")

        self.assertIsNone(latch.update(baseline))
        press_transition = latch.update(pressed)
        release_transition = latch.update(released)

        self.assertEqual(press_transition.pressed, 1)
        self.assertEqual(release_transition.released, 1)
        self.assertEqual(latch.pressed_latch, 1)
        self.assertEqual(latch.released_latch, 1)
        self.assertEqual(latch.transition_count, 2)
        self.assertEqual(latch.last_sequence, 102)


class TrainerProtocolTests(unittest.TestCase):
    def test_ftms(self):
        sample = parse_indoor_bike_data(bytes((0x44, 0x00, 0xE0, 0x07, 0xB8, 0x00, 0xB0, 0x00)))
        self.assertIsNotNone(sample)
        self.assertAlmostEqual(sample.speed_kmh, 20.16)
        self.assertAlmostEqual(sample.cadence_rpm, 92.0)
        self.assertEqual(sample.power_watts, 176)

    def test_csc(self):
        sample = parse_csc_measurement(bytes((0x03, 0x7D, 0x2A, 0x00, 0x00, 0xCA, 0xA8, 0x59, 0x0C, 0xCB, 0x3A)))
        self.assertEqual(sample.wheel_revolutions, 10877)
        self.assertEqual(sample.wheel_event_time_ticks, 0xA8CA)
        self.assertEqual(sample.crank_revolutions, 0x0C59)
        self.assertEqual(sample.crank_event_time_ticks, 0x3ACB)

    def test_heart_rate(self):
        self.assertEqual(parse_heart_rate_measurement(bytes((0, 72))), 72)
        self.assertEqual(parse_heart_rate_measurement(bytes((1, 0x2C, 1))), 300)
        self.assertIsNone(parse_heart_rate_measurement(bytes((1, 0x2C))))
        self.assertIsNone(parse_heart_rate_measurement(b""))

    def test_control_commands(self):
        rolling = (0x28, 0x50, 0x78, 0xA0, 0xC8, 0xF0, 0xFF)
        for index, value in enumerate(rolling, 1):
            self.assertEqual(build_flat_road_control_command(index), bytes((0x11, 0, 0, 0, 0, value, 0x33)))
        self.assertEqual(build_simulation_control_command(5, 3.0), bytes((0x11, 0, 0, 0x2C, 1, 0xC8, 0x33)))
        self.assertEqual(parse_control_response(bytes((0x80, 0, 1)), 0), 1)
        self.assertIsNone(parse_control_response(bytes((0x80, 0x11, 1)), 0))
        self.assertEqual(control_result_name(5), "control not permitted")

    def test_movement_rules(self):
        self.assertAlmostEqual(wheel_stop_timeout_seconds(1.0), 1.75)
        self.assertEqual(effective_speed_kmh(101.3, 100, 20, 80, False, 0, 0), 0)
        self.assertEqual(effective_speed_kmh(100.1, 100, 5, 0, False, 0, 0), 0)
        self.assertEqual(effective_speed_kmh(100.1, 100, 5, 12, False, 0, 0), 5)
        self.assertEqual(effective_speed_kmh(101.751, 100.8, 15, 80, True, 100, 1), 0)
        self.assertTrue(requires_ride_surface(False))
        self.assertFalse(requires_ride_surface(True))
        self.assertEqual(completed_laps(572, 143), 4)
        self.assertAlmostEqual(effective_steering_degrees(20), 9.25)
        self.assertEqual(effective_steering_degrees(60), 15)
        self.assertEqual(heading_degrees_for_world_forward((1, 0)), 0)
        self.assertEqual(heading_degrees_for_world_forward((0, 1)), -90)


if __name__ == "__main__":
    unittest.main()
