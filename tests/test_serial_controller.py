import os
import threading
import time
import unittest
from unittest.mock import patch

from arrietty_up.serial_controller import (
    ControllerEventType,
    SerialController,
    _pop_received_line,
    candidate_port_names,
    order_candidate_ports,
)


class FakePort:
    def __init__(self, name, lines):
        self.name = name
        self.lines = list(lines)
        self.sent = []
        self.purges = []
        self.closed = False

    def purge(self, *, transmit):
        self.purges.append(transmit)

    def send_line(self, line):
        self.sent.append(line)

    def read_line(self, timeout, stop):
        if self.lines:
            return self.lines.pop(0)
        stop.wait(min(timeout, 0.002))
        return None

    def close(self):
        self.closed = True


class BlockingPort(FakePort):
    def __init__(self, name, entered, release):
        super().__init__(name, [])
        self.entered = entered
        self.release = release

    def read_line(self, timeout, stop):
        self.entered.set()
        self.release.wait()
        return None


class SerialControllerTests(unittest.TestCase):
    def test_partial_serial_line_is_retained_until_newline(self):
        buffer = bytearray(b"PONG ARRIETTY-CONT")
        self.assertIsNone(_pop_received_line(buffer))
        self.assertEqual(buffer, b"PONG ARRIETTY-CONT")
        buffer.extend(b"ROLLER/1\r\nA1,42,0,0,0,0,1\n")
        self.assertEqual(_pop_received_line(buffer), "PONG ARRIETTY-CONTROLLER/1")
        self.assertEqual(_pop_received_line(buffer), "A1,42,0,0,0,0,1")
        self.assertEqual(buffer, b"")

    def test_candidate_ports(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "arrietty_up.serial_controller._windows_present_port_names",
            return_value=(),
        ):
            ports = candidate_port_names()
            self.assertEqual((ports[0], ports[-1]), ("COM64", "COM1"))
        with patch.dict(os.environ, {"ARRIETTY_CONTROLLER_PORT": "com7"}):
            self.assertEqual(candidate_port_names(), ("COM7",))

    def test_present_ports_are_tried_before_fallback_scan(self):
        ports = order_candidate_ports(("COM1", "com7", "COM4", "invalid"))
        self.assertEqual(ports[:4], ("COM7", "COM4", "COM1", "COM64"))
        self.assertEqual(len(ports), 64)
        self.assertEqual(len(set(ports)), 64)

    def test_identify_and_stream(self):
        fake = FakePort(
            "COM7",
            [
                "boot message",
                "PONG ARRIETTY-CONTROLLER/1",
                "A1,42,-32767,0,32767,1234,137",
            ],
        )
        controller = SerialController(
            lambda _name: fake,
            ports=lambda: ("COM7",),
            reset_delay=0,
            retry_delay=0.01,
            sample_timeout=0.01,
        )
        controller.start()
        deadline = time.monotonic() + 0.5
        events = []
        while time.monotonic() < deadline:
            events.extend(controller.drain_events())
            if any(event.type is ControllerEventType.SAMPLE for event in events):
                break
            time.sleep(0.002)
        controller.stop()
        events.extend(controller.drain_events())

        self.assertIn("PING\n", fake.sent)
        self.assertIn("STREAM ON\n", fake.sent)
        self.assertIn("STREAM OFF\n", fake.sent)
        sample_events = [event for event in events if event.sample is not None]
        self.assertTrue(sample_events)
        self.assertEqual(sample_events[0].sample.sequence, 42)
        self.assertTrue(fake.closed)

    def test_timed_out_worker_stays_tracked_and_cannot_double_start(self):
        entered = threading.Event()
        release = threading.Event()
        fake = BlockingPort("COM7", entered, release)
        controller = SerialController(
            lambda _name: fake,
            ports=lambda: ("COM7",),
            reset_delay=0,
            retry_delay=0.01,
        )
        controller.start()
        self.assertTrue(entered.wait(0.5))
        self.assertFalse(controller.stop(timeout=0.001))
        self.assertTrue(controller.running)
        with self.assertRaises(RuntimeError):
            controller.start()
        release.set()
        self.assertTrue(controller.stop(timeout=0.5))
        self.assertFalse(controller.running)


if __name__ == "__main__":
    unittest.main()
