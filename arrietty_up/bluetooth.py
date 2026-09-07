"""CYCPLUS T2 and BLE heart-rate worker built on bundled Bleak wheels."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from enum import Enum
from queue import Empty, SimpleQueue
import threading
import time

from .models import CscSample, TrainerSample
from .trainer_protocol import (
    build_simulation_control_command,
    control_result_name,
    parse_control_response,
    parse_csc_measurement,
    parse_heart_rate_measurement,
    parse_indoor_bike_data,
)


FTMS_SERVICE = "00001826-0000-1000-8000-00805f9b34fb"
CSC_SERVICE = "00001816-0000-1000-8000-00805f9b34fb"
FTMS_INDOOR_BIKE_DATA = "00002ad2-0000-1000-8000-00805f9b34fb"
FTMS_CONTROL_POINT = "00002ad9-0000-1000-8000-00805f9b34fb"
CSC_MEASUREMENT = "00002a5b-0000-1000-8000-00805f9b34fb"
HEART_RATE_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
FTMS_REQUEST_CONTROL = 0x00
FTMS_RESULT_SUCCESS = 0x01
FTMS_CONTROL_TIMEOUT_SECONDS = 5.0
T2_BLUETOOTH_ADDRESS = os.environ.get("ARRIETTY_TRAINER_ADDRESS", "")


class BluetoothEventType(str, Enum):
    STATUS = "status"
    GATT_CONNECTED = "gatt_connected"
    TRAINER_READY = "trainer_ready"
    CONNECTED = "connected"
    TRAINER_SAMPLE = "trainer_sample"
    CSC_SAMPLE = "csc_sample"
    HEART_RATE_CONNECTED = "heart_rate_connected"
    HEART_RATE_SAMPLE = "heart_rate_sample"
    HEART_RATE_UNAVAILABLE = "heart_rate_unavailable"
    CONTROL_READY = "control_ready"
    CONTROL_UNAVAILABLE = "control_unavailable"
    CSC_UNAVAILABLE = "csc_unavailable"
    ERROR = "error"
    WORKER_STOPPED = "worker_stopped"


@dataclass(frozen=True, slots=True)
class BluetoothEvent:
    generation: int
    type: BluetoothEventType
    message: str = ""
    trainer_sample: TrainerSample | None = None
    csc_sample: CscSample | None = None
    heart_rate_bpm: int | None = None
    preset_index: int | None = None
    grade_percent: float | None = None
    received_at: float = 0.0


@dataclass(frozen=True, slots=True)
class _ControlRequest:
    generation: int
    preset_index: int | None = None
    grade_percent: float | None = None


SessionRunner = Callable[
    ["BluetoothManager", int, int, float], Awaitable[None]
]


class BluetoothManager:
    def __init__(self, session_runner: SessionRunner | None = None) -> None:
        self._session_runner = session_runner or _ble_session
        self._events: SimpleQueue[BluetoothEvent] = SimpleQueue()
        self._control_requests: SimpleQueue[_ControlRequest] = SimpleQueue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self.generation = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, initial_preset_index: int = 5, initial_grade_percent: float = 0.0) -> int:
        if self.running:
            raise RuntimeError("Bluetooth worker is already running")
        self._thread = None
        self.drain_events()
        while True:
            try:
                self._control_requests.get_nowait()
            except Empty:
                break
        self.generation += 1
        generation = self.generation
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker_main,
            args=(generation, initial_preset_index, initial_grade_percent),
            name="ArriettyBluetooth",
            daemon=True,
        )
        self._thread.start()
        return generation

    def stop(self, timeout: float = 5.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        # Prefer cooperative shutdown so WinRT notification handlers are
        # removed before the asyncio loop closes.  Cancellation is only a
        # fallback for a Windows connect operation that did not return.
        if thread is not None and thread.is_alive():
            loop = self._loop
            task = self._task
            if loop is not None and task is not None and loop.is_running():
                loop.call_soon_threadsafe(task.cancel)
            if thread is not threading.current_thread():
                thread.join(min(1.0, max(0.0, timeout)))
        if thread is not None and thread.is_alive():
            return False
        self._thread = None
        return True

    def request_preset(self, preset_index: int) -> None:
        self._control_requests.put(
            _ControlRequest(self.generation, preset_index=preset_index)
        )

    def request_grade(self, grade_percent: float) -> None:
        self._control_requests.put(
            _ControlRequest(self.generation, grade_percent=grade_percent)
        )

    def drain_events(self) -> list[BluetoothEvent]:
        events: list[BluetoothEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events

    def _queue(self, event: BluetoothEvent) -> None:
        if event.received_at <= 0.0:
            event = replace(event, received_at=time.monotonic())
        self._events.put(event)

    def _worker_main(
        self,
        generation: int,
        initial_preset_index: int,
        initial_grade_percent: float,
    ) -> None:
        try:
            asyncio.run(
                self._run_session(
                    generation, initial_preset_index, initial_grade_percent
                )
            )
        except asyncio.CancelledError:
            pass
        except Exception as error:
            if not self._stop.is_set():
                self._queue(
                    BluetoothEvent(
                        generation,
                        BluetoothEventType.ERROR,
                        str(error),
                    )
                )
        finally:
            self._loop = None
            self._task = None
            self._queue(
                BluetoothEvent(generation, BluetoothEventType.WORKER_STOPPED)
            )

    async def _run_session(
        self,
        generation: int,
        initial_preset_index: int,
        initial_grade_percent: float,
    ) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        try:
            await self._session_runner(
                self, generation, initial_preset_index, initial_grade_percent
            )
        finally:
            # WinRT can have one native notification already in flight after
            # handlers are removed.  Keep the loop available long enough for
            # that callback to be harmlessly delivered before asyncio closes.
            await asyncio.sleep(0.5)


def _advertised_name(device, advertisement) -> str:
    return device.name or advertisement.local_name or ""


def _advertises_heart_rate(advertisement) -> bool:
    return HEART_RATE_SERVICE in (
        uuid.lower() for uuid in (advertisement.service_uuids or ())
    )


def _is_t2(device, advertisement) -> bool:
    if "t2" in _advertised_name(device, advertisement).lower():
        return True
    return FTMS_SERVICE in (
        uuid.lower() for uuid in (advertisement.service_uuids or ())
    )


async def _find_t2(stop: threading.Event):
    from bleak import BleakScanner

    found = None
    found_event = asyncio.Event()

    def on_advertisement(device, advertisement) -> None:
        nonlocal found
        if found is None and _is_t2(device, advertisement):
            found = device
            found_event.set()

    # Keep one Windows advertisement watcher alive. Recreating it every two
    # seconds can miss the scan-response packet and impose a full 20 s delay.
    async with BleakScanner(detection_callback=on_advertisement):
        while not stop.is_set() and found is None:
            try:
                await asyncio.wait_for(found_event.wait(), timeout=0.25)
            except TimeoutError:
                pass
    return found


def _known_t2_device():
    """Build a Windows BLE device handle without waiting for advertisements."""
    from bleak.backends.device import BLEDevice

    # The WinRT backend only needs the Bluetooth address from this object.  If
    # Windows no longer knows this T2, _ble_session falls back to a real scan.
    return BLEDevice(T2_BLUETOOTH_ADDRESS, "CYCPLUS T2", None)


def _new_t2_client(device, disconnected_callback):
    from bleak import BleakClient

    return BleakClient(
        device,
        disconnected_callback=disconnected_callback,
        services=(FTMS_SERVICE, CSC_SERVICE),
        timeout=12.0,
        winrt={"use_cached_services": True},
    )


async def _send_control_command(client, responses: asyncio.Queue, command: bytes) -> None:
    if not command:
        raise RuntimeError("Invalid T2 control preset")
    requested_opcode = command[0]
    await client.write_gatt_char(FTMS_CONTROL_POINT, command, response=True)
    deadline = asyncio.get_running_loop().time() + FTMS_CONTROL_TIMEOUT_SECONDS
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0.0:
            raise RuntimeError(
                f"T2 did not answer FTMS control opcode 0x{requested_opcode:02x}"
            )
        try:
            response = await asyncio.wait_for(responses.get(), timeout=remaining)
        except TimeoutError as error:
            raise RuntimeError(
                f"T2 did not answer FTMS control opcode 0x{requested_opcode:02x}"
            ) from error
        result = parse_control_response(response, requested_opcode)
        if result is None:
            continue
        if result != FTMS_RESULT_SUCCESS:
            raise RuntimeError(
                f"T2 rejected FTMS opcode 0x{requested_opcode:02x}: "
                f"{control_result_name(result)}"
            )
        return


async def _heart_rate_session(
    manager: BluetoothManager,
    generation: int,
) -> None:
    from bleak import BleakClient, BleakScanner

    while not manager._stop.is_set():
        manager._queue(
            BluetoothEvent(
                generation,
                BluetoothEventType.HEART_RATE_UNAVAILABLE,
                "SEARCHING: enable Garmin Broadcast Heart Rate (BLE)",
            )
        )
        device = await BleakScanner.find_device_by_filter(
            lambda _dev, adv: _advertises_heart_rate(adv),
            timeout=5.0,
        )
        if device is None:
            continue

        disconnected = asyncio.Event()
        loop = asyncio.get_running_loop()

        def on_disconnect(_client) -> None:
            loop.call_soon_threadsafe(disconnected.set)

        try:
            async with BleakClient(
                device,
                disconnected_callback=on_disconnect,
                services=(HEART_RATE_SERVICE,),
                timeout=10.0,
                winrt={"use_cached_services": True},
            ) as client:
                def on_heart_rate(_sender, data: bytearray) -> None:
                    heart_rate = parse_heart_rate_measurement(data)
                    if heart_rate is not None:
                        manager._queue(
                            BluetoothEvent(
                                generation,
                                BluetoothEventType.HEART_RATE_SAMPLE,
                                heart_rate_bpm=heart_rate,
                                received_at=time.monotonic(),
                            )
                        )

                await client.start_notify(HEART_RATE_MEASUREMENT, on_heart_rate)
                manager._queue(
                    BluetoothEvent(
                        generation,
                        BluetoothEventType.HEART_RATE_CONNECTED,
                        f"CONNECTED: {device.name or 'BLE heart-rate sensor'}",
                    )
                )
                while not manager._stop.is_set() and not disconnected.is_set():
                    await asyncio.sleep(0.1)
                if client.is_connected:
                    await client.stop_notify(HEART_RATE_MEASUREMENT)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not manager._stop.is_set():
                manager._queue(
                    BluetoothEvent(
                        generation,
                        BluetoothEventType.HEART_RATE_UNAVAILABLE,
                        f"UNAVAILABLE: {error}",
                    )
                )
        if not manager._stop.is_set():
            manager._queue(
                BluetoothEvent(
                    generation,
                    BluetoothEventType.HEART_RATE_UNAVAILABLE,
                    "DISCONNECTED - SEARCHING",
                )
            )
            await asyncio.sleep(1.0)


async def _ble_session(
    manager: BluetoothManager,
    generation: int,
    initial_preset_index: int,
    initial_grade_percent: float,
) -> None:
    from bleak.exc import BleakDeviceNotFoundError

    disconnected = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_disconnect(_client) -> None:
        loop.call_soon_threadsafe(disconnected.set)

    # This installation has one dedicated T2.  Connecting through its known
    # address avoids waiting for a sparse advertisement (30.8 s in the first
    # live timing run).  A scan remains as recovery if Windows forgot it.
    device = _known_t2_device() if T2_BLUETOOTH_ADDRESS else await _find_t2(manager._stop)
    if manager._stop.is_set() or device is None:
        return
    manager._queue(
        BluetoothEvent(
            generation,
            BluetoothEventType.STATUS,
            "CONNECTING: CYCPLUS T2 (configured address)" if T2_BLUETOOTH_ADDRESS else "CONNECTING: CYCPLUS T2 (discovered)",
        )
    )
    client = _new_t2_client(device, on_disconnect)
    try:
        await client.connect()
    except (BleakDeviceNotFoundError, TimeoutError, OSError) as direct_error:
        if manager._stop.is_set():
            return
        manager._queue(
            BluetoothEvent(
                generation,
                BluetoothEventType.STATUS,
                f"SEARCHING: direct T2 connection failed ({direct_error})",
            )
        )
        device = await _find_t2(manager._stop)
        if manager._stop.is_set() or device is None:
            return
        manager._queue(
            BluetoothEvent(
                generation,
                BluetoothEventType.STATUS,
                f"CONNECTING: {device.name or 'CYCPLUS T2'} (scan fallback)",
            )
        )
        disconnected.clear()
        client = _new_t2_client(device, on_disconnect)
        await client.connect()

    manager._queue(
        BluetoothEvent(
            generation,
            BluetoothEventType.GATT_CONNECTED,
            "GATT connected",
        )
    )

    control_notify_enabled = False
    trainer_notify_enabled = False
    csc_enabled = False
    heart_rate_task: asyncio.Task | None = None
    try:
        control_responses: asyncio.Queue[bytes] = asyncio.Queue()

        def on_control(_sender, data: bytearray) -> None:
            control_responses.put_nowait(bytes(data))

        def on_trainer(_sender, data: bytearray) -> None:
            sample = parse_indoor_bike_data(data)
            if sample is not None:
                manager._queue(
                    BluetoothEvent(
                        generation,
                        BluetoothEventType.TRAINER_SAMPLE,
                        trainer_sample=sample,
                        received_at=time.monotonic(),
                    )
                )

        def on_csc(_sender, data: bytearray) -> None:
            sample = parse_csc_measurement(data)
            if sample is not None:
                manager._queue(
                    BluetoothEvent(
                        generation,
                        BluetoothEventType.CSC_SAMPLE,
                        csc_sample=sample,
                        received_at=time.monotonic(),
                    )
                )

        # Speed is the critical path.  Subscribe before control-point writes or
        # optional CSC discovery; WinRT GATT operations can each block for many
        # seconds while T2 data notifications could already be moving the HMD.
        await client.start_notify(FTMS_INDOOR_BIKE_DATA, on_trainer)
        trainer_notify_enabled = True
        manager._queue(
            BluetoothEvent(
                generation,
                BluetoothEventType.TRAINER_READY,
                "T2 speed notifications active",
            )
        )
        manager._queue(
            BluetoothEvent(
                generation,
                BluetoothEventType.CONNECTED,
                "CONNECTED: T2 speed data",
            )
        )

        # Garmin discovery runs in parallel as soon as the critical T2 speed
        # path is ready, so its temporary broadcast window is not lost while
        # resistance control and CSC are initialized.
        heart_rate_task = asyncio.create_task(
            _heart_rate_session(manager, generation), name="ArriettyHeartRate"
        )

        control_enabled = False
        try:
            await client.start_notify(FTMS_CONTROL_POINT, on_control)
            control_notify_enabled = True
            await _send_control_command(
                client, control_responses, bytes((FTMS_REQUEST_CONTROL,))
            )
            await _send_control_command(
                client,
                control_responses,
                build_simulation_control_command(
                    initial_preset_index, initial_grade_percent
                ),
            )
            control_enabled = True
            manager._queue(
                BluetoothEvent(
                    generation,
                    BluetoothEventType.CONTROL_READY,
                    preset_index=initial_preset_index,
                    grade_percent=initial_grade_percent,
                )
            )
        except Exception as error:
            manager._queue(
                BluetoothEvent(
                    generation,
                    BluetoothEventType.CONTROL_UNAVAILABLE,
                    f"T2 speed data active; resistance control unavailable: {error}",
                )
            )

        try:
            await client.start_notify(CSC_MEASUREMENT, on_csc)
            csc_enabled = True
        except Exception as error:
            manager._queue(
                BluetoothEvent(
                    generation,
                    BluetoothEventType.CSC_UNAVAILABLE,
                    f"CSC wheel rotation unavailable: {error}",
                )
            )

        current_preset = initial_preset_index
        current_grade = initial_grade_percent
        try:
            while not manager._stop.is_set() and not disconnected.is_set():
                requested = False
                while True:
                    try:
                        request = manager._control_requests.get_nowait()
                    except Empty:
                        break
                    if request.generation != generation:
                        continue
                    if request.preset_index is not None:
                        current_preset = request.preset_index
                        requested = True
                    if request.grade_percent is not None:
                        current_grade = request.grade_percent
                        requested = True
                if requested and control_enabled:
                    try:
                        await _send_control_command(
                            client,
                            control_responses,
                            build_simulation_control_command(
                                current_preset, current_grade
                            ),
                        )
                        manager._queue(
                            BluetoothEvent(
                                generation,
                                BluetoothEventType.CONTROL_READY,
                                preset_index=current_preset,
                                grade_percent=current_grade,
                            )
                        )
                    except Exception as error:
                        control_enabled = False
                        manager._queue(
                            BluetoothEvent(
                                generation,
                                BluetoothEventType.CONTROL_UNAVAILABLE,
                                f"T2 speed data active; resistance control lost: {error}",
                            )
                        )
                await asyncio.sleep(0.1)
        finally:
            if heart_rate_task is not None:
                heart_rate_task.cancel()
                await asyncio.gather(heart_rate_task, return_exceptions=True)
    finally:
        if client.is_connected:
            if csc_enabled:
                try:
                    await client.stop_notify(CSC_MEASUREMENT)
                except Exception:
                    pass
            if trainer_notify_enabled:
                try:
                    await client.stop_notify(FTMS_INDOOR_BIKE_DATA)
                except Exception:
                    pass
            if control_notify_enabled:
                try:
                    await client.stop_notify(FTMS_CONTROL_POINT)
                except Exception:
                    pass
            try:
                await client.disconnect()
            except Exception:
                if not manager._stop.is_set():
                    raise

    if disconnected.is_set() and not manager._stop.is_set():
        raise RuntimeError("The T2 Bluetooth connection was lost")
