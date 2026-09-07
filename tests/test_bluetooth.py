import asyncio
import sys
import time
import types
import unittest
from unittest.mock import patch

from types import SimpleNamespace

from arrietty_up.bluetooth import (
    BluetoothEvent,
    BluetoothEventType,
    BluetoothManager,
    CSC_MEASUREMENT,
    FTMS_CONTROL_POINT,
    FTMS_INDOOR_BIKE_DATA,
    FTMS_SERVICE,
    _ble_session,
    _is_t2,
)


class BluetoothManagerTests(unittest.TestCase):
    def test_t2_filter_accepts_name_or_ftms_service(self):
        unnamed = SimpleNamespace(name=None)
        no_name_ftms = SimpleNamespace(local_name=None, service_uuids=[FTMS_SERVICE])
        named = SimpleNamespace(name="T2 14000")
        no_services = SimpleNamespace(local_name=None, service_uuids=[])
        self.assertTrue(_is_t2(unnamed, no_name_ftms))
        self.assertTrue(_is_t2(named, no_services))
        self.assertFalse(_is_t2(unnamed, no_services))

    def test_worker_lifecycle_and_generation(self):
        async def session(manager, generation, preset, grade):
            manager._queue(
                BluetoothEvent(
                    generation,
                    BluetoothEventType.CONTROL_READY,
                    preset_index=preset,
                    grade_percent=grade,
                )
            )
            while not manager._stop.is_set():
                await asyncio.sleep(0.001)

        manager = BluetoothManager(session)
        self.assertEqual(manager.start(5, 0.0), 1)
        with self.assertRaises(RuntimeError):
            manager.start()
        deadline = time.monotonic() + 0.5
        events = []
        while time.monotonic() < deadline and not events:
            events.extend(manager.drain_events())
            time.sleep(0.001)
        self.assertTrue(manager.stop())
        events.extend(manager.drain_events())
        self.assertFalse(manager.running)
        self.assertTrue(
            any(event.type is BluetoothEventType.CONTROL_READY for event in events)
        )
        self.assertTrue(
            any(event.type is BluetoothEventType.WORKER_STOPPED for event in events)
        )

    def test_control_requests_keep_generation(self):
        manager = BluetoothManager()
        manager.generation = 7
        manager.request_preset(6)
        manager.request_grade(3.0)
        preset = manager._control_requests.get_nowait()
        grade = manager._control_requests.get_nowait()
        self.assertEqual((preset.generation, preset.preset_index), (7, 6))
        self.assertEqual((grade.generation, grade.grade_percent), (7, 3.0))

    def test_speed_notification_precedes_control_and_optional_devices(self):
        manager = BluetoothManager()

        class FakeClient:
            def __init__(self):
                self.is_connected = False
                self.operations = []
                self.control_callback = None

            async def connect(self):
                self.operations.append("connect")
                self.is_connected = True

            async def disconnect(self):
                self.operations.append("disconnect")
                self.is_connected = False

            async def start_notify(self, characteristic, callback):
                self.operations.append(("start_notify", characteristic))
                if characteristic == FTMS_INDOOR_BIKE_DATA:
                    callback(
                        None,
                        bytearray((0x44, 0x00, 0xE0, 0x07, 0xB8, 0x00, 0xB0, 0x00)),
                    )
                elif characteristic == FTMS_CONTROL_POINT:
                    self.control_callback = callback
                elif characteristic == CSC_MEASUREMENT:
                    manager._stop.set()

            async def stop_notify(self, characteristic):
                self.operations.append(("stop_notify", characteristic))

            async def write_gatt_char(self, _characteristic, command, response):
                self.operations.append(("write", command[0], response))
                self.control_callback(None, bytearray((0x80, command[0], 0x01)))

        fake_client = FakeClient()

        async def no_heart_rate(_manager, _generation):
            return

        fake_bleak = types.ModuleType("bleak")
        fake_exc = types.ModuleType("bleak.exc")

        class FakeDeviceNotFoundError(Exception):
            pass

        fake_exc.BleakDeviceNotFoundError = FakeDeviceNotFoundError
        with (
            patch.dict(sys.modules, {"bleak": fake_bleak, "bleak.exc": fake_exc}),
            patch("arrietty_up.bluetooth.T2_BLUETOOTH_ADDRESS", "test-device"),
            patch("arrietty_up.bluetooth._known_t2_device", return_value=object()),
            patch("arrietty_up.bluetooth._new_t2_client", return_value=fake_client),
            patch("arrietty_up.bluetooth._heart_rate_session", no_heart_rate),
        ):
            asyncio.run(_ble_session(manager, 1, 5, 0.0))

        self.assertEqual(fake_client.operations[0], "connect")
        self.assertEqual(
            fake_client.operations[1],
            ("start_notify", FTMS_INDOOR_BIKE_DATA),
        )
        events = manager.drain_events()
        event_types = [event.type for event in events]
        self.assertLess(
            event_types.index(BluetoothEventType.TRAINER_SAMPLE),
            event_types.index(BluetoothEventType.CONTROL_READY),
        )
        self.assertIn(BluetoothEventType.TRAINER_READY, event_types)


if __name__ == "__main__":
    unittest.main()
