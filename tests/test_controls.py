import unittest

from arrietty_up import constants as c
from arrietty_up.controls import (
    DigitalFlightControls,
    FlightButtonChord,
    FlightTuningControls,
    TuningParameter,
)


class DigitalControlsTests(unittest.TestCase):
    def test_edges_and_limits(self):
        controls = DigitalFlightControls()
        controls.update_joystick((0.8, 0.0))
        self.assertEqual(controls.pitch_degrees, 1.0)
        controls.update_joystick((1.0, 0.0))
        self.assertEqual(controls.pitch_degrees, 1.0)
        controls.update_joystick((0.0, 0.0))
        controls.update_joystick((0.46, 0.0))
        self.assertEqual(controls.pitch_degrees, 2.0)
        controls.update_joystick((0.0, 0.0))
        controls.update_joystick((0.0, -0.8))
        self.assertEqual(controls.roll_right_degrees, 1.0)
        self.assertEqual(controls.bank_degrees, -1.0)
        controls.reset_commands()
        self.assertEqual((controls.pitch_degrees, controls.roll_right_degrees), (0.0, 0.0))
        for _ in range(100):
            controls.step_pitch(1)
            controls.step_roll_right(1)
        self.assertEqual(controls.pitch_degrees, c.FLIGHT_MAX_PITCH_DEGREES)
        self.assertEqual(controls.roll_right_degrees, c.FLIGHT_MAX_BANK_DEGREES)

    def test_button_and_joystick_conventions_match(self):
        buttons = DigitalFlightControls()
        buttons.step_pitch(1)
        buttons.step_roll_right(1)
        joystick = DigitalFlightControls()
        joystick.update_joystick((0.8, -0.8))
        self.assertEqual(buttons.pitch_degrees, joystick.pitch_degrees)
        self.assertEqual(buttons.bank_degrees, joystick.bank_degrees)


class TuningControlsTests(unittest.TestCase):
    def test_tuning_cycle(self):
        controls = FlightTuningControls()
        self.assertEqual(controls.values.test_propulsion_power_watts, 95.0)
        self.assertEqual(controls.values.positive_climb_multiplier, 10.0)
        self.assertTrue(controls.press_switch().entered)
        controls.update_joystick((0.8, 0.0))
        self.assertEqual(controls.values.test_propulsion_power_watts, 100.0)
        controls.update_joystick((0.0, 0.0))
        controls.update_joystick((-0.8, 0.0))
        self.assertEqual(controls.values.test_propulsion_power_watts, 95.0)
        controls.press_switch()
        self.assertEqual(controls.parameter, TuningParameter.POSITIVE_CLIMB_MULTIPLIER)
        controls.update_joystick((0.0, 0.0))
        controls.update_joystick((0.8, 0.0))
        self.assertEqual(controls.values.positive_climb_multiplier, 11.0)
        controls.press_switch()
        controls.press_switch()
        self.assertTrue(controls.press_switch().completed)
        self.assertFalse(controls.active)


class FlightButtonChordTests(unittest.TestCase):
    def test_single_buttons_are_delayed_then_resolved_as_roll(self):
        chord = FlightButtonChord()
        self.assertEqual(chord.update(0x04, 0x04, 1.0), ())
        action = chord.flush(1.081)
        self.assertEqual(action.roll_right_step, -1)

    def test_two_buttons_within_window_resolve_as_pitch(self):
        chord = FlightButtonChord()
        chord.update(0x04, 0x04, 1.0)
        actions = chord.update(0x08, 0x0C, 1.05)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].pitch_step, 1)
        self.assertIsNone(chord.flush(2.0))


if __name__ == "__main__":
    unittest.main()
