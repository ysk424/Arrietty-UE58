"""Non-blocking UDP controller for the ESP32 fan."""

from collections.abc import Callable
from dataclasses import dataclass
import math
import socket
import time

from . import constants as c


@dataclass(frozen=True, slots=True)
class FanResponse:
    """Validated response returned by the ESP32-IR controller."""

    command: str
    level: int
    target_level: int | None = None


def level_for_speed(speed_kmh: float) -> int:
    if not math.isfinite(speed_kmh):
        return 0
    if speed_kmh <= c.FAN_STOPPED_THRESHOLD_KMH:
        return 0
    fraction = max(0.0, min(1.0, speed_kmh / c.FAN_MAXIMUM_SPEED_KMH))
    return max(1, min(c.FAN_LEVEL_COUNT, math.ceil(fraction * c.FAN_LEVEL_COUNT)))


def level_for_speed_with_hysteresis(speed_kmh: float, previous_level: int) -> int:
    """Map speed while keeping a stable level near each 5 km/h boundary."""
    level = level_for_speed(speed_kmh)
    if (
        level == previous_level
        or level == 0
        or previous_level == 0
        or not 0 <= previous_level <= c.FAN_LEVEL_COUNT
    ):
        return level

    speed_per_level = c.FAN_MAXIMUM_SPEED_KMH / c.FAN_LEVEL_COUNT
    if level > previous_level:
        boundary = previous_level * speed_per_level
        if speed_kmh < boundary + c.FAN_LEVEL_HYSTERESIS_KMH:
            return previous_level
    else:
        boundary = (previous_level - 1) * speed_per_level
        if speed_kmh > boundary - c.FAN_LEVEL_HYSTERESIS_KMH:
            return previous_level
    return level


def parse_response(response: str) -> FanResponse | None:
    fields = response.strip().split()
    if len(fields) < 3 or fields[0].upper() != "OK":
        return None
    command = fields[1].upper()
    if command not in {"LEVEL", "SYNC"} or not fields[2].isdecimal():
        return None
    level = int(fields[2])
    if not 0 <= level <= c.FAN_LEVEL_COUNT:
        return None

    target_level = None
    if len(fields) >= 5 and fields[3].upper() == "TARGET":
        if not fields[4].isdecimal():
            return None
        target_level = int(fields[4])
        if not 0 <= target_level <= c.FAN_LEVEL_COUNT:
            return None
    return FanResponse(command, level, target_level)


def parse_response_level(response: str) -> int | None:
    parsed = parse_response(response)
    return None if parsed is None else parsed.level


class FanController:
    def __init__(
        self,
        socket_factory: Callable[..., socket.socket] = socket.socket,
        *,
        host: str = c.FAN_UDP_HOST,
        port: int = c.FAN_UDP_PORT,
    ) -> None:
        self._socket_factory = socket_factory
        self.destination = (host, port)
        self.socket: socket.socket | None = None
        self.last_requested_level: int | None = None
        self.requested_level = 0
        self.reported_level: int | None = None
        self.reported_target_level: int | None = None
        self.last_send_at: float | None = None
        self.last_response_at: float | None = None
        self.first_unanswered_send_at: float | None = None
        self.packets_sent = 0
        self.packets_received = 0
        self.invalid_responses = 0
        self.last_command = ""
        self.last_error = ""
        self.status = "NOT STARTED"

    @property
    def running(self) -> bool:
        return self.socket is not None

    @property
    def connected(self) -> bool:
        return (
            self.socket is not None
            and self.last_response_at is not None
            and not self.status.startswith(
                ("NO RESPONSE", "SOCKET ERROR", "SEND ERROR", "RECEIVE ERROR")
            )
        )

    @property
    def short_status(self) -> str:
        if self.status.startswith("CONNECTED"):
            return "OK"
        if self.status.startswith(("SETTING", "CONFIRMING")):
            return "SET"
        if self.status.startswith("NO RESPONSE"):
            return "NO ACK"
        if "ERROR" in self.status:
            return "ERROR"
        if self.status == "STOPPED":
            return "OFF"
        return "WAIT"

    def response_age_seconds(self, now: float | None = None) -> float | None:
        if self.last_response_at is None:
            return None
        current = time.monotonic() if now is None else now
        return max(0.0, current - self.last_response_at)

    def start(self) -> bool:
        self.stop()
        try:
            udp = self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
            udp.setblocking(False)
            udp.bind(("0.0.0.0", 0))
        except OSError as error:
            try:
                udp.close()
            except (OSError, UnboundLocalError):
                pass
            self.status = f"SOCKET ERROR: {error}"
            return False

        self.socket = udp
        self.last_requested_level = None
        self.requested_level = 0
        self.reported_level = None
        self.reported_target_level = None
        self.last_send_at = None
        self.last_response_at = None
        self.first_unanswered_send_at = None
        self.packets_sent = 0
        self.packets_received = 0
        self.invalid_responses = 0
        self.last_command = ""
        self.last_error = ""
        self.status = "WAITING FOR ESP32"
        return True

    def stop(self) -> None:
        udp = self.socket
        if udp is None:
            return
        self.requested_level = 0
        # UDP has no delivery guarantee. A short burst makes the safety stop
        # resilient to one lost datagram; duplicate LEVEL 0 commands are
        # idempotent in the ESP32 firmware.
        for _attempt in range(c.FAN_STOP_SEND_COUNT):
            self._send_command("LEVEL 0")
        try:
            udp.close()
        except OSError as error:
            self.last_error = str(error)
        finally:
            self.socket = None
            self.last_requested_level = 0
            self.status = "STOPPED"

    def tick(self, speed_kmh: float, now: float | None = None) -> None:
        self.set_level(
            level_for_speed_with_hysteresis(speed_kmh, self.requested_level),
            now,
        )

    def set_level(self, level: int, now: float | None = None) -> None:
        """Request an exact level without blocking the game/render tick."""
        if self.socket is None:
            return
        if not 0 <= level <= c.FAN_LEVEL_COUNT:
            raise ValueError(f"fan level must be 0..{c.FAN_LEVEL_COUNT}: {level}")
        now = time.monotonic() if now is None else now
        self.requested_level = level
        target_changed = self.requested_level != self.last_requested_level
        awaiting_response = self.last_send_at is not None and (
            self.last_response_at is None or self.last_response_at < self.last_send_at
        )
        resend_interval = (
            c.FAN_RESPONSE_TIMEOUT_SECONDS
            if awaiting_response
            else c.FAN_RESEND_SECONDS
        )
        resend_due = (
            self.last_send_at is None
            or now - self.last_send_at >= resend_interval
        )
        if target_changed or resend_due:
            if self._send_command(f"LEVEL {self.requested_level}"):
                self.last_requested_level = self.requested_level
                self.last_send_at = now
                if self.first_unanswered_send_at is None:
                    self.first_unanswered_send_at = now
                if self.last_response_at is None:
                    self.status = "WAITING FOR ESP32"
                elif self.reported_level == self.requested_level:
                    self.status = f"CONFIRMING LEVEL {self.requested_level}"
                else:
                    self.status = (
                        f"SETTING LEVEL {self.reported_level} -> "
                        f"{self.requested_level}"
                    )
        self._poll_responses(now)

    def correct_reported_level(
        self,
        delta: int,
        now: float | None = None,
    ) -> None:
        base = self.requested_level if self.reported_level is None else self.reported_level
        corrected = max(0, min(c.FAN_LEVEL_COUNT, base + delta))
        if self._send_command(f"SYNC {corrected}"):
            now = time.monotonic() if now is None else now
            self.requested_level = corrected
            self.last_requested_level = corrected
            self.last_send_at = now
            if self.first_unanswered_send_at is None:
                self.first_unanswered_send_at = now
            self.status = "WAITING FOR SYNC ACK"

    def _send_command(self, command: str) -> bool:
        if self.socket is None:
            return False
        payload = command.encode("utf-8")
        try:
            sent = self.socket.sendto(payload, self.destination) == len(payload)
        except OSError as error:
            self.last_error = str(error)
            self.status = f"SEND ERROR: {error}"
            return False
        if sent:
            self.packets_sent += 1
            self.last_command = command
        return sent

    def _poll_responses(self, now: float) -> None:
        udp = self.socket
        if udp is None:
            return
        # Bound work per frame even if stale/duplicate UDP packets have queued
        # while the ESP32 was performing its slow IR transition.
        for _response_index in range(c.FAN_MAX_RESPONSES_PER_TICK):
            try:
                payload, sender = udp.recvfrom(1024)
            except BlockingIOError:
                break
            except OSError as error:
                self.last_error = str(error)
                self.status = f"RECEIVE ERROR: {error}"
                break
            self.packets_received += 1
            if sender[0] != self.destination[0] or sender[1] != self.destination[1]:
                self.invalid_responses += 1
                continue
            response = parse_response(payload.decode("utf-8", errors="replace"))
            if response is None:
                self.invalid_responses += 1
                continue
            self.reported_level = response.level
            self.reported_target_level = response.target_level
            self.last_response_at = now
            self.first_unanswered_send_at = None
            self.status = (
                f"CONNECTED LEVEL {response.level}"
                if response.level == self.requested_level
                else f"SETTING LEVEL {response.level} -> {self.requested_level}"
            )

        if (
            self.first_unanswered_send_at is not None
            and now - self.first_unanswered_send_at
            >= c.FAN_RESPONSE_TIMEOUT_SECONDS
        ):
            self.status = "NO RESPONSE - CONNECT WI-FI Arrietty-Fan"
