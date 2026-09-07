import math
import unittest
from types import SimpleNamespace

from arrietty_up.instruments import (
    attitude_transform,
    build_readout,
    update_upbge_panel,
)
from arrietty_up.runtime import RuntimeState


class InstrumentTests(unittest.TestCase):
    def test_ground_panel_formats_live_and_unavailable_values(self):
        state = RuntimeState()
        state.ride_active = True
        state.heart_rate_bpm = 87
        state.power_watts = 214
        state.speed_kmh = 23.45
        state.ground_speed_kmh = 23.45
        state.applied_preset = 5
        state.applied_grade_percent = 3.0
        state.cadence_rpm = 81.25
        state.ride_elapsed_seconds = 65.9

        panel = build_readout(state, 1.0 / 60.0)

        self.assertEqual(panel.heart_rate, "87")
        self.assertEqual(panel.trainer_power, "214")
        self.assertEqual(panel.ground_speed, "23.4 km/h")
        self.assertEqual(panel.trainer_grade, " 3.0 %")
        self.assertEqual(panel.mode, "RIDE")
        self.assertEqual(panel.elapsed_time, "0:01:05")
        self.assertIn("ALT      0.0 m", panel.physics)
        self.assertIn("CAD     81.2 rpm", panel.physics)
        self.assertIn("STR IDLE +0.0", panel.debug)
        self.assertIn("CMD P+0 R+0", panel.debug)
        self.assertIn("FAN 0/-- WAIT", panel.debug)
        self.assertIn("XR NOT CHECKED HMD WAIT", panel.debug)
        self.assertIn("FRAME 16.7 ms", panel.debug)

    def test_unavailable_grade_and_heart_rate_are_not_shown_as_zero(self):
        panel = build_readout(RuntimeState(), 0.0)

        self.assertEqual(panel.heart_rate, "---")
        self.assertEqual(panel.trainer_grade, "--.- %")
        self.assertEqual(panel.mode, "STANDBY")
        self.assertEqual(panel.elapsed_time, "0:00:00")
        self.assertEqual(panel.heading, "000")
        self.assertEqual(panel.heading_ticks, ("340", "350", "010", "020"))
        self.assertEqual(panel.home_marker, "HOME")

    def test_elapsed_time_supports_long_rides_and_invalid_values(self):
        state = RuntimeState()
        state.ride_elapsed_seconds = 3661.9
        self.assertEqual(build_readout(state, 0.0).elapsed_time, "1:01:01")

        state.ride_elapsed_seconds = float("nan")
        self.assertEqual(build_readout(state, 0.0).elapsed_time, "0:00:00")

    def test_flight_tapes_and_mode_use_flight_state(self):
        state = RuntimeState()
        state.flight_enabled = True
        state.flight.airborne = True
        state.flight.airspeed_meters_per_second = 12.5
        state.flight.altitude_meters = 123.0
        state.navigation_heading_degrees = 356.6
        state.home_relative_degrees = 30.0
        state.home_distance_meters = 1200.0

        panel = build_readout(state, 0.01)

        self.assertEqual(panel.mode, "FLIGHT")
        self.assertEqual(panel.airspeed, "45")
        self.assertEqual(panel.airspeed_ticks, ("20", "30", "50", "60"))
        self.assertEqual(panel.stall_speed, "STALL 18")
        self.assertEqual(panel.altitude, "123")
        self.assertEqual(panel.altitude_ticks, ("0", "50", "150", "200"))
        self.assertEqual(panel.heading, "357")
        self.assertEqual(panel.heading_ticks, ("340", "350", "010", "020"))
        self.assertEqual(panel.home_marker, "H>")
        self.assertAlmostEqual(panel.home_marker_x, -0.122)
        self.assertEqual(panel.pfd_status, "PFD / AIRBORNE")
        self.assertEqual(panel.pfd_state, "P +0.0  B +0.0  ALT 123.0 m")
        self.assertIn("ALT    123.0 m", panel.physics)

    def test_low_altitude_keeps_tenths_visible(self):
        state = RuntimeState()
        state.flight.altitude_meters = 0.4

        self.assertEqual(build_readout(state, 0.01).altitude, "0.4")

    def test_pitch_ladder_translation_rotates_with_horizon(self):
        x, z, roll = attitude_transform(10.0, 0.0)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(z, -0.04)
        self.assertEqual(roll, 0.0)

        x, z, roll = attitude_transform(10.0, 90.0)
        self.assertAlmostEqual(x, 0.04)
        self.assertAlmostEqual(z, 0.0, places=7)
        self.assertEqual(roll, -90.0)

    def test_pfd_pitch_translation_is_bounded(self):
        self.assertEqual(attitude_transform(1000.0, 0.0), (0.0, -0.048, 0.0))

    def test_scene_update_moves_masked_pfd_geometry(self):
        class FakeObject(dict):
            localPosition = None
            localOrientation = None

        class FakeMatrix:
            @staticmethod
            def Rotation(angle, size, axis):
                return (angle, size, axis)

        attitude = FakeObject(panel_base_y=0.013)
        altitude = FakeObject(Text="0")
        heading = FakeObject(Text="000")
        stall_speed = FakeObject(Text="STALL 18")
        home_marker = FakeObject(
            Text="HOME",
            panel_base_y=0.038,
            panel_base_z=0.136,
        )
        scene = SimpleNamespace(
            objects={
                "Instrument_PFD_Attitude": attitude,
                "Instrument_AltitudeValue": altitude,
                "Instrument_HeadingValue": heading,
                "Instrument_StallSpeedValue": stall_speed,
                "Instrument_CompassHomeMarker": home_marker,
            }
        )
        state = RuntimeState()
        state.flight.pitch_degrees = 10.0
        state.flight.bank_degrees = 90.0
        state.flight.altitude_meters = 0.4
        state.navigation_heading_degrees = 91.2
        state.home_relative_degrees = -12.5
        state.home_distance_meters = 200.0
        from unittest.mock import patch

        with patch.dict(
            "sys.modules",
            {"mathutils": SimpleNamespace(Matrix=FakeMatrix)},
        ):
            update_upbge_panel(scene, state, 0.01)

        self.assertAlmostEqual(attitude.localPosition[0], 0.04)
        self.assertAlmostEqual(attitude.localPosition[1], 0.013)
        self.assertAlmostEqual(attitude.localPosition[2], 0.0, places=7)
        self.assertAlmostEqual(attitude.localOrientation[0], -math.pi / 2.0)
        self.assertEqual(altitude["Text"], "0.4")
        self.assertEqual(heading["Text"], "091")
        self.assertEqual(stall_speed["Text"], "STALL 18")
        self.assertEqual(home_marker["Text"], "H")
        self.assertAlmostEqual(home_marker.localPosition[0], 0.061)
        self.assertEqual(home_marker.localPosition[1:], (0.038, 0.136))


if __name__ == "__main__":
    unittest.main()
