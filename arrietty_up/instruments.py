"""Instrument-panel formatting and UPBGE display updates.

The formatting and attitude calculations stay Blender-independent so that the
panel can be exercised without the bicycle, HMD, or UPBGE runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from . import constants as c


PITCH_METERS_PER_DEGREE = 0.004
PFD_DISPLAY_PITCH_LIMIT_DEGREES = 12.0
COMPASS_TICK_STEP_DEGREES = 10.0
COMPASS_HOME_SPAN_DEGREES = 25.0
COMPASS_HOME_HALF_WIDTH_METERS = 0.122


@dataclass(frozen=True, slots=True)
class InstrumentReadout:
    heart_rate: str
    trainer_power: str
    ground_speed: str
    trainer_grade: str
    mode: str
    elapsed_time: str
    airspeed: str
    airspeed_ticks: tuple[str, str, str, str]
    stall_speed: str
    altitude: str
    altitude_ticks: tuple[str, str, str, str]
    heading: str
    heading_ticks: tuple[str, str, str, str]
    home_marker: str
    home_marker_x: float
    pfd_status: str
    pfd_state: str
    physics: str
    debug: str


def _mode(runtime) -> str:
    if runtime.flight_enabled:
        return "FLIGHT" if runtime.flight.airborne else "FLIGHT ARMED"
    if runtime.ride_active:
        return "RIDE"
    return "STANDBY"


def _pfd_status(runtime) -> str:
    if runtime.flight.stalled:
        return "PFD / STALL - NOSE DOWN"
    if runtime.flight.airborne:
        return "PFD / AIRBORNE"
    if runtime.flight_enabled:
        return "PFD / TAKEOFF ARMED - PITCH UP"
    if runtime.ride_active:
        return "PFD / GROUND"
    return "PRIMARY FLIGHT DISPLAY"


def _tape_ticks(value: float, step: float, *, decimals: int = 0) -> tuple[str, ...]:
    center = round(value / step) * step
    formatter = f"{{:.{decimals}f}}"
    values = (center - 2 * step, center - step, center + step, center + 2 * step)
    return tuple("" if item < 0.0 else formatter.format(item) for item in values)


def _normalize_heading_degrees(value: float) -> float:
    try:
        heading = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(heading):
        return 0.0
    return heading % 360.0


def _format_heading(value: float) -> str:
    return f"{int(math.floor(_normalize_heading_degrees(value) + 0.5)) % 360:03d}"


def _heading_tape_ticks(value: float) -> tuple[str, str, str, str]:
    center = math.floor(
        _normalize_heading_degrees(value) / COMPASS_TICK_STEP_DEGREES + 0.5
    ) * COMPASS_TICK_STEP_DEGREES
    values = (
        center - 2.0 * COMPASS_TICK_STEP_DEGREES,
        center - COMPASS_TICK_STEP_DEGREES,
        center + COMPASS_TICK_STEP_DEGREES,
        center + 2.0 * COMPASS_TICK_STEP_DEGREES,
    )
    cardinal = {0: "N", 90: "E", 180: "S", 270: "W"}
    return tuple(
        cardinal.get(int(item) % 360, f"{int(item) % 360:03d}")
        for item in values
    )


def _home_marker(relative_degrees: float, distance_meters: float) -> tuple[str, float]:
    try:
        relative = float(relative_degrees)
        distance = float(distance_meters)
    except (TypeError, ValueError):
        return "H", 0.0
    if not math.isfinite(relative) or not math.isfinite(distance):
        return "H", 0.0
    if distance <= 0.5:
        return "HOME", 0.0

    clamped = max(
        -COMPASS_HOME_SPAN_DEGREES,
        min(COMPASS_HOME_SPAN_DEGREES, relative),
    )
    # Panel-local X+ is rider-left. A positive relative bearing is to the
    # rider's right, so its authored object moves in the negative X direction.
    position_x = (
        -clamped
        / COMPASS_HOME_SPAN_DEGREES
        * COMPASS_HOME_HALF_WIDTH_METERS
    )
    if relative < -COMPASS_HOME_SPAN_DEGREES:
        return "<H", position_x
    if relative > COMPASS_HOME_SPAN_DEGREES:
        return "H>", position_x
    return "H", position_x


def _format_elapsed_time(elapsed_seconds: float) -> str:
    try:
        elapsed = float(elapsed_seconds)
    except (TypeError, ValueError):
        elapsed = 0.0
    if not math.isfinite(elapsed):
        elapsed = 0.0
    total_seconds = int(max(0.0, elapsed))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def build_readout(runtime, delta_seconds: float) -> InstrumentReadout:
    """Create all changing panel strings from a runtime-like object."""
    flight = runtime.flight
    airspeed_kmh = max(0.0, flight.airspeed_meters_per_second * 3.6)
    altitude_meters = max(0.0, flight.altitude_meters)
    heading_degrees = _normalize_heading_degrees(
        getattr(runtime, "navigation_heading_degrees", runtime.heading_degrees)
    )
    home_marker, home_marker_x = _home_marker(
        getattr(runtime, "home_relative_degrees", 0.0),
        getattr(runtime, "home_distance_meters", 0.0),
    )
    heart_rate = "---" if runtime.heart_rate_bpm is None else str(runtime.heart_rate_bpm)
    grade = (
        "--.- %"
        if runtime.applied_preset is None
        else f"{runtime.applied_grade_percent:4.1f} %"
    )
    reported_fan = "--" if runtime.fan.reported_level is None else str(runtime.fan.reported_level)
    ground_speed = getattr(runtime, "ground_speed_kmh", runtime.speed_kmh)
    steering_status = getattr(runtime, "steering_status", "IDLE")
    steering_degrees = getattr(runtime, "effective_steering_degrees", 0.0)
    command_pitch = getattr(runtime.digital_controls, "pitch_degrees", 0.0)
    command_roll = getattr(runtime.digital_controls, "roll_right_degrees", 0.0)
    tuning_status = runtime.tuning_controls.compact_status()
    if runtime.tuning_controls.active:
        tuning_status = tuning_status.replace("TUNE ", "T", 1)
    pfd_state = (
        f"P {flight.pitch_degrees:+.1f}  B {flight.bank_degrees:+.1f}  "
        f"ALT {altitude_meters:.1f} m"
    )
    physics = "\n".join(
        (
            f"ALT    {altitude_meters:5.1f} m",
            f"V/S    {flight.vertical_speed_meters_per_second:+5.1f} m/s",
            f"PITCH  {flight.pitch_degrees:+5.1f} deg",
            f"BANK   {flight.bank_degrees:+5.1f} deg",
            f"AOA    {flight.angle_of_attack_degrees:+5.1f} deg",
            f"CAD    {runtime.cadence_rpm:5.1f} rpm",
            f"HEAD   {heading_degrees:05.1f} deg",
        )
    )
    debug = "\n".join(
        (
            f"T2  {runtime.bluetooth_status}",
            f"HR  {runtime.heart_rate_status}",
            f"STR {steering_status} {steering_degrees:+.1f}",
            f"CMD P{command_pitch:+.0f} R{command_roll:+.0f}",
            tuning_status,
            (
                f"FAN {runtime.fan.requested_level}/{reported_fan} "
                f"{runtime.fan.short_status}"
            ),
            f"VOICE {getattr(runtime, 'voice_status', 'IDLE')}",
            (
                f"XR {getattr(runtime, 'xr_bridge_status', 'UNKNOWN')} "
                f"HMD {'OK' if getattr(runtime, 'hmd_aligned', False) else 'WAIT'}"
            ),
            f"FRAME {max(0.0, delta_seconds) * 1000.0:4.1f} ms",
        )
    )
    return InstrumentReadout(
        heart_rate=heart_rate,
        trainer_power=str(max(0, runtime.power_watts)),
        ground_speed=f"{max(0.0, ground_speed):4.1f} km/h",
        trainer_grade=grade,
        mode=_mode(runtime),
        elapsed_time=_format_elapsed_time(
            getattr(runtime, "ride_elapsed_seconds", 0.0)
        ),
        airspeed=f"{airspeed_kmh:.0f}",
        airspeed_ticks=_tape_ticks(airspeed_kmh, 10.0),
        stall_speed=f"STALL {c.FLIGHT_STALL_SPEED_KMH:.0f}",
        altitude=(
            f"{altitude_meters:.1f}"
            if altitude_meters < 100.0
            else f"{altitude_meters:.0f}"
        ),
        altitude_ticks=_tape_ticks(altitude_meters, 50.0),
        heading=_format_heading(heading_degrees),
        heading_ticks=_heading_tape_ticks(heading_degrees),
        home_marker=home_marker,
        home_marker_x=home_marker_x,
        pfd_status=_pfd_status(runtime),
        pfd_state=pfd_state,
        physics=physics,
        debug=debug,
    )


def attitude_transform(
    pitch_degrees: float,
    bank_degrees: float,
    pitch_scale: float = PITCH_METERS_PER_DEGREE,
) -> tuple[float, float, float]:
    """Return horizon X/Z shift and in-panel rotation in degrees.

    Pitch translation is rotated with the horizon so the pitch ladder remains
    rigidly attached to it during a bank.
    """
    pitch = max(
        -PFD_DISPLAY_PITCH_LIMIT_DEGREES,
        min(PFD_DISPLAY_PITCH_LIMIT_DEGREES, pitch_degrees),
    )
    rotation_degrees = -bank_degrees
    rotation = math.radians(rotation_degrees)
    unbanked_z = -pitch * pitch_scale
    return (
        math.sin(rotation) * unbanked_z,
        math.cos(rotation) * unbanked_z,
        rotation_degrees,
    )


def _scene_object(scene, name: str):
    try:
        return scene.objects[name]
    except (KeyError, SystemError):
        return None


def _set_text(scene, name: str, value: str) -> None:
    obj = _scene_object(scene, name)
    if obj is not None and obj.get("Text") != value:
        obj["Text"] = value


def update_upbge_panel(scene, runtime, delta_seconds: float) -> None:
    """Update authored text and the physically masked PFD geometry."""
    readout = build_readout(runtime, delta_seconds)
    fields = {
        "Instrument_HeartRateValue": readout.heart_rate,
        "Instrument_PowerValue": readout.trainer_power,
        "Instrument_GroundSpeedValue": readout.ground_speed,
        "Instrument_GradeValue": readout.trainer_grade,
        "Instrument_ModeValue": readout.mode,
        "Instrument_ElapsedValue": readout.elapsed_time,
        "Instrument_AirspeedValue": readout.airspeed,
        "Instrument_StallSpeedValue": readout.stall_speed,
        "Instrument_AltitudeValue": readout.altitude,
        "Instrument_HeadingValue": readout.heading,
        "Instrument_CompassHomeMarker": readout.home_marker,
        "Instrument_PFDHeading": readout.pfd_status,
        "Instrument_PFDState": readout.pfd_state,
        "Instrument_PhysicsText": readout.physics,
        "Instrument_DebugText": readout.debug,
    }
    for name, value in fields.items():
        _set_text(scene, name, value)

    for suffix, value in zip(("M2", "M1", "P1", "P2"), readout.airspeed_ticks):
        _set_text(scene, f"Instrument_AirspeedTick_{suffix}", value)
    for suffix, value in zip(("M2", "M1", "P1", "P2"), readout.altitude_ticks):
        _set_text(scene, f"Instrument_AltitudeTick_{suffix}", value)
    for suffix, value in zip(("M2", "M1", "P1", "P2"), readout.heading_ticks):
        _set_text(scene, f"Instrument_HeadingTick_{suffix}", value)

    home_marker = _scene_object(scene, "Instrument_CompassHomeMarker")
    if home_marker is not None:
        home_marker.localPosition = (
            readout.home_marker_x,
            home_marker.get("panel_base_y", 0.038),
            home_marker.get("panel_base_z", 0.136),
        )

    attitude = _scene_object(scene, "Instrument_PFD_Attitude")
    if attitude is not None:
        from mathutils import Matrix

        # The sky, earth and pitch marks move together behind a fixed opaque
        # annulus. The annulus—not a renderer-specific shader—keeps every
        # moving part inside the circular aperture.
        shift_x, shift_z, rotation = attitude_transform(
            runtime.flight.pitch_degrees,
            runtime.flight.bank_degrees,
        )
        attitude.localPosition = (
            shift_x,
            attitude.get("panel_base_y", 0.013),
            shift_z,
        )
        attitude.localOrientation = Matrix.Rotation(
            math.radians(rotation), 3, "Y"
        )
