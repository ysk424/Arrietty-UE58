import unittest

from arrietty_up import constants as c
from arrietty_up.flight import (
    aircraft_weight_newtons,
    human_powered_flight_control_authority,
    human_powered_flight_drag_newtons,
    human_powered_flight_lift_newtons,
    human_powered_flight_power_climb_rate_mps,
    human_powered_flight_propulsion_power_watts,
    human_powered_level_flight_power_watts,
    initialize_human_powered_flight,
    step_human_powered_flight,
)
from arrietty_up.models import FlightTuningValues


class HumanPoweredFlightTests(unittest.TestCase):
    def test_reference_values(self):
        best_mps = c.FLIGHT_BEST_GLIDE_SPEED_KMH / 3.6
        self.assertAlmostEqual(
            human_powered_flight_drag_newtons(best_mps),
            aircraft_weight_newtons() / c.FLIGHT_GLIDE_RATIO,
            delta=0.001,
        )
        self.assertAlmostEqual(human_powered_level_flight_power_watts(24.0), 95.3, delta=0.2)
        self.assertEqual(human_powered_flight_propulsion_power_watts(150), 150)
        self.assertEqual(human_powered_flight_propulsion_power_watts(-10), 0)
        self.assertAlmostEqual(human_powered_flight_power_climb_rate_mps(140, 24, 10), 1.04, delta=0.02)
        self.assertAlmostEqual(
            human_powered_flight_power_climb_rate_mps(0, 24, 10),
            -24.0 / 3.6 / c.FLIGHT_GLIDE_RATIO,
            delta=0.001,
        )
        trim = human_powered_flight_lift_newtons(best_mps, 0, 0)
        pitched = human_powered_flight_lift_newtons(best_mps, 5, 0)
        self.assertAlmostEqual(trim, aircraft_weight_newtons(), delta=0.1)
        self.assertGreater(pitched, trim * 1.5)

    def test_control_authority(self):
        low = human_powered_flight_control_authority(18.5 / 3.6, False)
        reference = human_powered_flight_control_authority(24 / 3.6, False)
        high = human_powered_flight_control_authority(36 / 3.6, False)
        self.assertLess(low, reference)
        self.assertLess(reference, high)
        self.assertAlmostEqual(reference, 1.0)
        self.assertAlmostEqual(human_powered_flight_control_authority(24 / 3.6, True), 0.25)

    def test_takeoff_and_controls(self):
        state = initialize_human_powered_flight(21)
        for _ in range(10):
            result = step_human_powered_flight(state, 180, 6, 0, 0, 0.1, True)
            if result.took_off:
                break
        self.assertTrue(state.airborne)

        one_degree = initialize_human_powered_flight(24)
        result = step_human_powered_flight(one_degree, 95, 1, 0, 0, 0.1, True)
        self.assertTrue(result.took_off)
        self.assertAlmostEqual(one_degree.pitch_degrees, 1.0, delta=0.001)

        controls = initialize_human_powered_flight(24)
        controls.airborne = True
        controls.altitude_meters = 100
        for _ in range(20):
            step_human_powered_flight(controls, 140, 4, 5, 0, 0.05, True)
        self.assertAlmostEqual(controls.pitch_degrees, 4, delta=0.001)
        self.assertAlmostEqual(controls.bank_degrees, 5, delta=0.001)
        self.assertGreater(controls.vertical_speed_meters_per_second, 0)
        self.assertGreater(controls.heading_rate_degrees_per_second, 0)

    def test_flight_armed_aileron_command_is_visible_before_takeoff(self):
        state = initialize_human_powered_flight(0)

        result = step_human_powered_flight(state, 0, 0, 5, 0, 0.1, True)

        self.assertFalse(result.took_off)
        self.assertFalse(state.airborne)
        self.assertGreater(state.bank_degrees, 0.0)
        self.assertEqual(state.heading_rate_degrees_per_second, 0.0)

    def test_stall_recovery_and_glide(self):
        stall = initialize_human_powered_flight(17)
        stall.airborne = True
        stall.altitude_meters = 100
        result = step_human_powered_flight(stall, 0, 6, 0, 0, 0.1, True)
        self.assertTrue(result.stall_started)
        self.assertLess(stall.vertical_speed_meters_per_second, 0)

        recovery = initialize_human_powered_flight(21)
        recovery.airborne = True
        recovery.stalled = True
        recovery.altitude_meters = 100
        recovery.flight_path_angle_degrees = -5
        result = step_human_powered_flight(recovery, 100, -6, 0, 0, 0.1, True)
        self.assertTrue(result.stall_recovered)

        boosted = initialize_human_powered_flight(24)
        unboosted = initialize_human_powered_flight(24)
        for state in (boosted, unboosted):
            state.airborne = True
            state.altitude_meters = 100
        no_boost = FlightTuningValues(positive_climb_multiplier=1.0)
        for _ in range(100):
            step_human_powered_flight(boosted, 140, 5, 0, 0, 0.05, True)
            step_human_powered_flight(unboosted, 140, 5, 0, 0, 0.05, True, no_boost)
        self.assertGreater(boosted.altitude_meters, unboosted.altitude_meters + 1.0)


if __name__ == "__main__":
    unittest.main()
