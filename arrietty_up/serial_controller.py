"""Background connection to the wired Arrietty ESP32 controller.

The game thread only drains :class:`ControllerEvent` objects.  All blocking
Win32 serial work stays on the worker thread, matching the UE implementation.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
import os
from queue import Empty, SimpleQueue
import sys
import threading
import time
from typing import Callable, Protocol

from .controller_protocol import ControllerSample, parse_state_line


class ControllerEventType(str, Enum):
    STATUS = "status"
    CONNECTED = "connected"
    SAMPLE = "sample"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class ControllerEvent:
    type: ControllerEventType
    message: str = ""
    sample: ControllerSample | None = None
    port: str = ""


class SerialPort(Protocol):
    name: str

    def purge(self, *, transmit: bool) -> None: ...
    def send_line(self, line: str) -> None: ...
    def read_line(self, timeout: float, stop: threading.Event) -> str | None: ...
    def close(self) -> None: ...


def _pop_received_line(buffer: bytearray) -> str | None:
    newline = buffer.find(b"\n")
    if newline < 0:
        return None
    raw = bytes(buffer[:newline]).rstrip(b"\r")
    del buffer[: newline + 1]
    return raw.decode("ascii", errors="replace")


class _DCB(ctypes.Structure):
    _fields_ = [
        ("DCBlength", wintypes.DWORD),
        ("BaudRate", wintypes.DWORD),
        ("fBinary", wintypes.DWORD, 1),
        ("fParity", wintypes.DWORD, 1),
        ("fOutxCtsFlow", wintypes.DWORD, 1),
        ("fOutxDsrFlow", wintypes.DWORD, 1),
        ("fDtrControl", wintypes.DWORD, 2),
        ("fDsrSensitivity", wintypes.DWORD, 1),
        ("fTXContinueOnXoff", wintypes.DWORD, 1),
        ("fOutX", wintypes.DWORD, 1),
        ("fInX", wintypes.DWORD, 1),
        ("fErrorChar", wintypes.DWORD, 1),
        ("fNull", wintypes.DWORD, 1),
        ("fRtsControl", wintypes.DWORD, 2),
        ("fAbortOnError", wintypes.DWORD, 1),
        ("fDummy2", wintypes.DWORD, 17),
        ("wReserved", wintypes.WORD),
        ("XonLim", wintypes.WORD),
        ("XoffLim", wintypes.WORD),
        ("ByteSize", wintypes.BYTE),
        ("Parity", wintypes.BYTE),
        ("StopBits", wintypes.BYTE),
        ("XonChar", ctypes.c_char),
        ("XoffChar", ctypes.c_char),
        ("ErrorChar", ctypes.c_char),
        ("EofChar", ctypes.c_char),
        ("EvtChar", ctypes.c_char),
        ("wReserved1", wintypes.WORD),
    ]


class _COMMTIMEOUTS(ctypes.Structure):
    _fields_ = [
        ("ReadIntervalTimeout", wintypes.DWORD),
        ("ReadTotalTimeoutMultiplier", wintypes.DWORD),
        ("ReadTotalTimeoutConstant", wintypes.DWORD),
        ("WriteTotalTimeoutMultiplier", wintypes.DWORD),
        ("WriteTotalTimeoutConstant", wintypes.DWORD),
    ]


class Win32SerialPort:
    """Minimal Win32 serial transport, intentionally independent of pyserial."""

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    PURGE_TXCLEAR = 0x0004
    PURGE_RXCLEAR = 0x0008
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self, name: str) -> None:
        if sys.platform != "win32":
            raise OSError("Win32 serial ports are only available on Windows")
        self.name = name
        self._receive_buffer = bytearray()
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_api()
        handle = self._kernel32.CreateFileW(
            rf"\\.\{name}",
            self.GENERIC_READ | self.GENERIC_WRITE,
            0,
            None,
            self.OPEN_EXISTING,
            0,
            None,
        )
        if handle == self.INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = handle
        try:
            self._configure_port()
        except Exception:
            self.close()
            raise

    def _configure_api(self) -> None:
        api = self._kernel32
        api.CreateFileW.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        api.CreateFileW.restype = wintypes.HANDLE
        api.GetCommState.argtypes = (wintypes.HANDLE, ctypes.POINTER(_DCB))
        api.SetCommState.argtypes = (wintypes.HANDLE, ctypes.POINTER(_DCB))
        api.SetCommTimeouts.argtypes = (wintypes.HANDLE, ctypes.POINTER(_COMMTIMEOUTS))
        api.SetupComm.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)
        api.PurgeComm.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        api.ReadFile.argtypes = (
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        )
        api.WriteFile.argtypes = api.ReadFile.argtypes
        api.CloseHandle.argtypes = (wintypes.HANDLE,)

    def _checked(self, result: int) -> None:
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    def _configure_port(self) -> None:
        self._checked(self._kernel32.SetupComm(self._handle, 4096, 4096))
        state = _DCB()
        state.DCBlength = ctypes.sizeof(_DCB)
        self._checked(self._kernel32.GetCommState(self._handle, ctypes.byref(state)))
        state.BaudRate = 115200
        state.ByteSize = 8
        state.Parity = 0
        state.StopBits = 0
        state.fBinary = 1
        state.fParity = 0
        state.fDtrControl = 0
        state.fRtsControl = 0
        self._checked(self._kernel32.SetCommState(self._handle, ctypes.byref(state)))
        timeouts = _COMMTIMEOUTS(20, 0, 50, 0, 500)
        self._checked(self._kernel32.SetCommTimeouts(self._handle, ctypes.byref(timeouts)))

    def purge(self, *, transmit: bool) -> None:
        flags = self.PURGE_RXCLEAR | (self.PURGE_TXCLEAR if transmit else 0)
        self._checked(self._kernel32.PurgeComm(self._handle, flags))
        self._receive_buffer.clear()

    def send_line(self, line: str) -> None:
        data = line.encode("ascii")
        buffer = ctypes.create_string_buffer(data)
        written = wintypes.DWORD()
        self._checked(
            self._kernel32.WriteFile(
                self._handle, buffer, len(data), ctypes.byref(written), None
            )
        )
        if written.value != len(data):
            raise OSError(f"short serial write: {written.value}/{len(data)}")

    def read_line(self, timeout: float, stop: threading.Event) -> str | None:
        deadline = time.monotonic() + timeout
        while not stop.is_set() and time.monotonic() < deadline:
            line = _pop_received_line(self._receive_buffer)
            if line is not None:
                return line
            chunk = (ctypes.c_char * 64)()
            received = wintypes.DWORD()
            self._checked(
                self._kernel32.ReadFile(
                    self._handle, chunk, len(chunk), ctypes.byref(received), None
                )
            )
            if received.value == 0:
                continue
            self._receive_buffer.extend(bytes(chunk[: received.value]))
            if len(self._receive_buffer) > 4096 and b"\n" not in self._receive_buffer:
                self._receive_buffer.clear()
        return _pop_received_line(self._receive_buffer)

    def close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle is not None and handle != self.INVALID_HANDLE_VALUE:
            self._kernel32.CloseHandle(handle)
            self._handle = None


def _port_number(name: str) -> int:
    return int(name[3:]) if name.startswith("COM") and name[3:].isdigit() else 0


def order_candidate_ports(present: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Try currently present Windows ports before the full fallback scan."""
    ordered_present = sorted(
        {name.upper() for name in present if _port_number(name.upper()) > 0},
        key=_port_number,
        reverse=True,
    )
    fallback = (f"COM{number}" for number in range(64, 0, -1))
    return tuple(ordered_present) + tuple(
        name for name in fallback if name not in ordered_present
    )


def _windows_present_port_names() -> tuple[str, ...]:
    if sys.platform != "win32":
        return ()
    try:
        import winreg

        ports: list[str] = []
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DEVICEMAP\SERIALCOMM",
        ) as key:
            index = 0
            while True:
                try:
                    value_name, value, _value_type = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                # Opening Bluetooth RFCOMM ports can block for many seconds
                # while Windows attempts a radio connection.  They can never
                # be the CH340 wired controller, so exclude them explicitly.
                if isinstance(value, str) and "BTH" not in value_name.upper():
                    ports.append(value)
        return tuple(ports)
    except OSError:
        return ()


def candidate_port_names() -> tuple[str, ...]:
    preferred = os.environ.get("ARRIETTY_CONTROLLER_PORT", "").strip().upper()
    if preferred:
        return (preferred,)
    present = _windows_present_port_names()
    if sys.platform == "win32" and present:
        return tuple(sorted(set(present), key=_port_number, reverse=True))
    return order_candidate_ports()


class SerialController:
    def __init__(
        self,
        port_factory: Callable[[str], SerialPort] = Win32SerialPort,
        *,
        ports: Callable[[], tuple[str, ...]] = candidate_port_names,
        reset_delay: float = 1.2,
        retry_delay: float = 1.0,
        sample_timeout: float = 2.0,
    ) -> None:
        self._port_factory = port_factory
        self._ports = ports
        self._reset_delay = reset_delay
        self._retry_delay = retry_delay
        self._sample_timeout = sample_timeout
        self._events: SimpleQueue[ControllerEvent] = SimpleQueue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            raise RuntimeError("serial controller worker is already running")
        self._thread = None
        self.drain_events()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker_main,
            name="ArriettySerialController",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        if thread is not None and thread.is_alive():
            self._queue(
                ControllerEvent(
                    ControllerEventType.STATUS,
                    "STOPPING: serial worker has not exited yet",
                )
            )
            return False
        self._thread = None
        return True

    def drain_events(self) -> list[ControllerEvent]:
        events: list[ControllerEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events

    def _queue(self, event: ControllerEvent) -> None:
        self._events.put(event)

    def _identify(self, port: SerialPort) -> bool:
        port.purge(transmit=True)
        if self._stop.wait(self._reset_delay):
            return False
        port.purge(transmit=False)
        port.send_line("PING\n")
        deadline = time.monotonic() + 1.5
        while not self._stop.is_set() and time.monotonic() < deadline:
            line = port.read_line(min(0.25, max(0.0, deadline - time.monotonic())), self._stop)
            if line == "PONG ARRIETTY-CONTROLLER/1":
                return True
        return False

    def _stream(self, port: SerialPort) -> None:
        port.send_line("STREAM ON\n")
        last_sample_at = time.monotonic()
        try:
            while not self._stop.is_set():
                line = port.read_line(0.5, self._stop)
                if line is not None:
                    sample = parse_state_line(line)
                    if sample is not None:
                        last_sample_at = time.monotonic()
                        self._queue(
                            ControllerEvent(
                                ControllerEventType.SAMPLE,
                                sample=sample,
                                port=port.name,
                            )
                        )
                if time.monotonic() - last_sample_at > self._sample_timeout:
                    return
        finally:
            try:
                port.send_line("STREAM OFF\n")
            except OSError:
                pass

    def _worker_main(self) -> None:
        if sys.platform != "win32" and self._port_factory is Win32SerialPort:
            self._queue(
                ControllerEvent(
                    ControllerEventType.STATUS,
                    "UNAVAILABLE: ESP32 controller currently requires Windows",
                )
            )
            return

        self._queue(
            ControllerEvent(
                ControllerEventType.STATUS,
                "SEARCHING: USB-SERIAL CH340 controller",
            )
        )
        while not self._stop.is_set():
            connected_this_pass = False
            for port_name in self._ports():
                if self._stop.is_set():
                    break
                try:
                    port = self._port_factory(port_name)
                except OSError:
                    continue
                try:
                    if not self._identify(port):
                        continue
                    connected_this_pass = True
                    message = f"CONNECTED: {port_name} at 115200 bps"
                    self._queue(
                        ControllerEvent(
                            ControllerEventType.CONNECTED, message, port=port_name
                        )
                    )
                    self._stream(port)
                except OSError as error:
                    if connected_this_pass and not self._stop.is_set():
                        self._queue(
                            ControllerEvent(
                                ControllerEventType.STATUS,
                                f"SERIAL ERROR: {port_name}: {error}",
                                port=port_name,
                            )
                        )
                finally:
                    port.close()

                if connected_this_pass:
                    if not self._stop.is_set():
                        self._queue(
                            ControllerEvent(
                                ControllerEventType.DISCONNECTED,
                                f"DISCONNECTED: {port_name}; reconnecting",
                                port=port_name,
                            )
                        )
                    break

            if self._stop.is_set():
                return
            if not connected_this_pass:
                self._queue(
                    ControllerEvent(
                        ControllerEventType.STATUS,
                        "SEARCHING: connect the ESP32 USB cable",
                    )
                )
            self._stop.wait(self._retry_delay)
