import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from arrietty_up.flight_log import FlightLog
from arrietty_up.runtime import RuntimeState


class FlightLogTests(unittest.TestCase):
    def test_route_sampling_and_next_session_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs" / "latest-flight.csv"
            state = RuntimeState(started_at=100)
            log = FlightLog(path, {"world_file": "Funafuti.blend", "origin_latitude": -8.5239843})
            log.sample(state, 100)
            state.position_x_meters = 20
            log.sample(state, 100.05)  # No extra frame-rate-dependent writes.
            state.position_x_meters = 30
            state.position_y_meters = -40
            state.flight.altitude_meters = 12
            state.navigation_heading_degrees = 210
            state.flight.airborne = True
            state.flight.pitch_degrees = 7.25
            state.flight.bank_degrees = -12.5
            state.digital_controls.pitch_degrees = 15  # Commands are not pose.
            log.sample(state, 100.11)
            self.assertTrue(log.close())
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual(float(rows[1]["east_m"]), 30)
            self.assertEqual(float(rows[1]["north_m"]), -40)
            self.assertEqual(float(rows[1]["altitude_m"]), 12)
            self.assertEqual(float(rows[1]["bearing_deg"]), 210)
            self.assertEqual(float(rows[1]["pitch_deg"]), 7.25)
            self.assertEqual(float(rows[1]["roll_deg"]), 12.5)
            self.assertEqual(float(rows[0]["pitch_deg"]), 0)
            self.assertEqual(rows[0]["world_file"], "Funafuti.blend")
            self.assertTrue(rows[0]["recorded_utc"].endswith("+00:00"))
            log = FlightLog(path)
            state.position_x_meters = 999
            state.flight.airborne = False
            log.sample(state, 200)
            self.assertTrue(log.close())
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(float(rows[0]["east_m"]), 999)
            self.assertEqual(float(rows[0]["pitch_deg"]), 0)
            self.assertEqual(float(rows[0]["roll_deg"]), 0)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_stop_records_last_position_before_resetting_flight(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest-flight.csv"
            state = RuntimeState()
            state.flight_log = FlightLog(path)
            state.ride_active = state.flight_enabled = True
            state.flight.altitude_meters = 18
            state.flight.airborne = True
            state.flight.pitch_degrees = -3.5
            state.flight.bank_degrees = 9
            state.position_x_meters = 321
            for name in ("bluetooth", "voice", "steering", "fan", "serial"):
                setattr(state, name, Mock())
            state.stop_services()
            state.stop_services()  # Repeated shutdown must not truncate the file.
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["flight_enabled"], "1")
            self.assertEqual(float(rows[0]["altitude_m"]), 18)
            self.assertEqual(float(rows[0]["east_m"]), 321)
            self.assertEqual(float(rows[0]["pitch_deg"]), -3.5)
            self.assertEqual(float(rows[0]["roll_deg"]), -9)

    def test_unwritable_path_does_not_stop_simulation(self):
        with tempfile.TemporaryDirectory() as directory:
            log = FlightLog(Path(directory))  # A directory cannot be opened as CSV.
            self.assertTrue(log.close())
            self.assertTrue(log.error)
            log.sample(RuntimeState(), 1)


if __name__ == "__main__":
    unittest.main()
