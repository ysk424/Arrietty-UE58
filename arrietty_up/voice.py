"""Nonblocking UDP client for the existing Arrietty voice/PTT bridge."""

from __future__ import annotations

import socket
import time

from . import constants as c


PROTOCOL = "ARRIETTY_VOICE/1"
ACK_TIMEOUT_SECONDS = 1.5


class VoiceBridge:
    def __init__(self) -> None:
        self._socket: socket.socket | None = None
        self.status = "IDLE"
        self.detail = ""
        self.ptt_held = False
        self.ack_pending = False
        self.ack_deadline_seconds = 0.0

    def _ensure_socket(self) -> socket.socket:
        if self._socket is None:
            value = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            value.setblocking(False)
            self._socket = value
        return self._socket

    def send(self, command: str) -> bool:
        try:
            payload = f"{PROTOCOL} {command}".encode("ascii")
            sent = self._ensure_socket().sendto(
                payload,
                (c.VOICE_BRIDGE_HOST, c.VOICE_BRIDGE_PORT),
            )
            return sent == len(payload)
        except OSError as error:
            self.status = "ERROR"
            self.detail = str(error)
            return False

    def set_ptt_held(self, held: bool) -> bool:
        if self.ptt_held == held:
            return True
        self.ptt_held = held
        sent = self.send("PTT_DOWN" if held else "PTT_UP")
        self.status = (
            ("PTT START REQUESTED" if held else "PTT TRANSCRIPTION REQUESTED")
            if sent
            else "PTT BRIDGE SEND ERROR"
        )
        self.ack_pending = sent
        self.ack_deadline_seconds = (
            time.monotonic() + ACK_TIMEOUT_SECONDS if sent else 0.0
        )
        return sent

    def poll(self, now_seconds: float | None = None) -> tuple[str, str] | None:
        if self._socket is None:
            return None
        found = None
        while True:
            try:
                payload = self._socket.recv(2048).decode("utf-8", errors="replace")
            except BlockingIOError:
                break
            except OSError as error:
                self.status = "ERROR"
                self.detail = str(error)
                break
            prefix = f"{PROTOCOL} STATUS "
            if not payload.startswith(prefix):
                continue
            value = payload[len(prefix) :].strip()
            status, _, detail = value.partition(" ")
            if status:
                self.status = status
                self.detail = detail.strip()
                self.ack_pending = False
                self.ack_deadline_seconds = 0.0
                found = (self.status, self.detail)
        now = time.monotonic() if now_seconds is None else now_seconds
        if self.ack_pending and now >= self.ack_deadline_seconds:
            self.ack_pending = False
            self.ack_deadline_seconds = 0.0
            self.status = "PTT BRIDGE NO RESPONSE"
            self.detail = "Voice bridge did not acknowledge the PTT request"
            found = (self.status, self.detail)
        return found

    def close(self) -> None:
        if self.ptt_held:
            self.send("PTT_CANCEL")
        self.ptt_held = False
        self.ack_pending = False
        self.ack_deadline_seconds = 0.0
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self.status = "IDLE"
        self.detail = ""
