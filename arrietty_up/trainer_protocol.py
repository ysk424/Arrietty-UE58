"""FTMS, CSC, heart-rate, movement, and steering protocol helpers."""

from __future__ import annotations

import math

from . import constants as c
from .models import ControlPreset, CscSample, TrainerSample

FTMS_SET_INDOOR_BIKE_SIMULATION = 0x11
FTMS_RESPONSE_CODE = 0x80

CONTROL_PRESETS = (
    ControlPreset(1, "Race", 0.0040),
    ControlPreset(2, "Road", 0.0080),
    ControlPreset(3, "Firm", 0.0120),
    ControlPreset(4, "Strong", 0.0160),
    ControlPreset(5, "Road Default", 0.0200),
    ControlPreset(6, "Bicycle", 0.0240),
    ControlPreset(7, "FTMS Limit", 0.0255),
)


def _take_unsigned(data: bytes | bytearray, offset: int, size: int) -> tuple[int, int] | None:
    end = offset + size
    if offset < 0 or size <= 0 or end > len(data):
        return None
    return int.from_bytes(data[offset:end], "little", signed=False), end


def parse_indoor_bike_data(data: bytes | bytearray) -> TrainerSample | None:
    if len(data) < 2:
        return None
    flags = int.from_bytes(data[:2], "little")
    offset = 2
    speed = cadence = None
    power = None

    def take(size: int) -> int | None:
        nonlocal offset
        result = _take_unsigned(data, offset, size)
        if result is None:
            offset = len(data) + 1
            return None
        value, offset = result
        return value

    if not flags & 0x0001:
        value = take(2)
        if value is None:
            return None
        speed = value * 0.01
    if flags & 0x0002 and take(2) is None:
        return None
    if flags & 0x0004:
        value = take(2)
        if value is None:
            return None
        cadence = value * 0.5
    if flags & 0x0008 and take(2) is None:
        return None
    if flags & 0x0010 and take(3) is None:
        return None
    if flags & 0x0020 and take(2) is None:
        return None
    if flags & 0x0040:
        value = take(2)
        if value is None:
            return None
        power = int.from_bytes(value.to_bytes(2, "little"), "little", signed=True)
    return TrainerSample(speed, cadence, power)


def parse_csc_measurement(data: bytes | bytearray) -> CscSample | None:
    if not data:
        return None
    flags = data[0]
    offset = 1
    wheel_revolutions = wheel_ticks = crank_revolutions = crank_ticks = None

    def take(size: int) -> int | None:
        nonlocal offset
        result = _take_unsigned(data, offset, size)
        if result is None:
            offset = len(data) + 1
            return None
        value, offset = result
        return value

    if flags & 0x01:
        wheel_revolutions = take(4)
        wheel_ticks = take(2)
        if wheel_revolutions is None or wheel_ticks is None:
            return None
    if flags & 0x02:
        crank_revolutions = take(2)
        crank_ticks = take(2)
        if crank_revolutions is None or crank_ticks is None:
            return None
    return CscSample(wheel_revolutions, wheel_ticks, crank_revolutions, crank_ticks)


def parse_heart_rate_measurement(data: bytes | bytearray) -> int | None:
    if len(data) < 2:
        return None
    if not data[0] & 0x01:
        return data[1]
    if len(data) < 3:
        return None
    return int.from_bytes(data[1:3], "little")


def find_preset(index: int) -> ControlPreset | None:
    return next((preset for preset in CONTROL_PRESETS if preset.index == index), None)


def build_simulation_control_command(preset_index: int, grade_percent: float) -> bytes:
    preset = find_preset(preset_index)
    if preset is None:
        return b""
    grade = max(-32768, min(32767, round(grade_percent * 100.0)))
    rolling = round(preset.rolling_resistance / 0.0001)
    return bytes((
        FTMS_SET_INDOOR_BIKE_SIMULATION,
        0,
        0,
        grade & 0xFF,
        (grade >> 8) & 0xFF,
        rolling,
        51,
    ))


def build_flat_road_control_command(preset_index: int) -> bytes:
    return build_simulation_control_command(preset_index, 0.0)


def parse_control_response(data: bytes | bytearray, requested_opcode: int) -> int | None:
    if len(data) < 3 or data[0] != FTMS_RESPONSE_CODE or data[1] != requested_opcode:
        return None
    return data[2]


def control_result_name(result_code: int) -> str:
    return {
        0x01: "success",
        0x02: "not supported",
        0x03: "invalid parameter",
        0x04: "operation failed",
        0x05: "control not permitted",
    }.get(result_code, f"unknown result 0x{result_code:02x}")


def wheel_stop_timeout_seconds(wheel_period_seconds: float) -> float:
    if wheel_period_seconds <= 0.0:
        return c.DEFAULT_WHEEL_STOP_SECONDS
    return max(c.MIN_WHEEL_STOP_SECONDS, min(c.MAX_WHEEL_STOP_SECONDS, wheel_period_seconds * 1.5 + 0.25))


def effective_speed_kmh(
    now_seconds: float,
    last_ftms_sample_seconds: float,
    ftms_speed_kmh: float,
    cadence_rpm: float,
    wheel_signal_received: bool,
    last_wheel_motion_seconds: float,
    wheel_period_seconds: float,
) -> float:
    if now_seconds - last_ftms_sample_seconds > c.SAMPLE_STALE_SECONDS:
        return 0.0
    if wheel_signal_received and now_seconds - last_wheel_motion_seconds > wheel_stop_timeout_seconds(wheel_period_seconds):
        return 0.0
    if 0.0 < ftms_speed_kmh <= c.COAST_STOP_SPEED_KMH and cadence_rpm <= 0.0:
        return 0.0
    return max(0.0, ftms_speed_kmh)


def requires_ride_surface(flight_enabled: bool) -> bool:
    return not flight_enabled


def completed_laps(distance_meters: float, lap_length_meters: float) -> int:
    return max(0, math.floor(distance_meters / max(1.0, lap_length_meters)))


def effective_steering_degrees(filtered_raw_degrees: float) -> float:
    magnitude = max(0.0, abs(filtered_raw_degrees) - c.STEERING_DEADZONE_DEGREES)
    effective = math.copysign(magnitude * c.STEERING_GAIN, filtered_raw_degrees)
    return max(-c.MAX_EFFECTIVE_STEERING_DEGREES, min(c.MAX_EFFECTIVE_STEERING_DEGREES, effective))


def heading_degrees_for_world_forward(world_forward: tuple[float, float]) -> float:
    x, y = world_forward
    if math.hypot(x, y) <= 1.0e-9:
        return 0.0
    return _unwind_degrees(-math.degrees(math.atan2(y, x)))


def yaw_correction_degrees(
    current_world_forward: tuple[float, float],
    target_world_forward: tuple[float, float],
) -> float:
    current = _normalized(current_world_forward)
    target = _normalized(target_world_forward)
    if current is None or target is None:
        return 0.0
    cx, cy = current
    tx, ty = target
    return math.degrees(math.atan2(cx * ty - cy * tx, cx * tx + cy * ty))


def hmd_origin_yaw_degrees(hmd_tracking_forward: tuple[float, float]) -> float:
    return yaw_correction_degrees(hmd_tracking_forward, (1.0, 0.0))


def _normalized(value: tuple[float, float]) -> tuple[float, float] | None:
    length = math.hypot(*value)
    if length <= 1.0e-9:
        return None
    return value[0] / length, value[1] / length


def _unwind_degrees(value: float) -> float:
    result = math.fmod(value, 360.0)
    if result > 180.0:
        result -= 360.0
    elif result < -180.0:
        result += 360.0
    return result
