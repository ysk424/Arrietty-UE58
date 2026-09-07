"""Blender-independent Arrietty state values."""

from dataclasses import dataclass

from . import constants as c


@dataclass(frozen=True, slots=True)
class TrainerSample:
    speed_kmh: float | None = None
    cadence_rpm: float | None = None
    power_watts: int | None = None


@dataclass(frozen=True, slots=True)
class CscSample:
    wheel_revolutions: int | None = None
    wheel_event_time_ticks: int | None = None
    crank_revolutions: int | None = None
    crank_event_time_ticks: int | None = None


@dataclass(frozen=True, slots=True)
class ControlPreset:
    index: int
    label: str
    rolling_resistance: float


@dataclass(slots=True)
class FlightTuningValues:
    test_propulsion_power_watts: float = c.FLIGHT_TEST_PROPULSION_POWER_WATTS
    positive_climb_multiplier: float = c.FLIGHT_POSITIVE_CLIMB_MULTIPLIER
    pitch_rate_degrees_per_second: float = c.FLIGHT_PITCH_RATE_DEGREES_PER_SECOND
    bank_rate_degrees_per_second: float = c.FLIGHT_BANK_RATE_DEGREES_PER_SECOND


@dataclass(slots=True)
class FlightState:
    airspeed_meters_per_second: float = 0.0
    altitude_meters: float = 0.0
    vertical_speed_meters_per_second: float = 0.0
    bank_degrees: float = 0.0
    pitch_degrees: float = 0.0
    flight_path_angle_degrees: float = 0.0
    angle_of_attack_degrees: float = 0.0
    control_authority: float = c.FLIGHT_MIN_CONTROL_AUTHORITY
    heading_rate_degrees_per_second: float = 0.0
    airborne: bool = False
    stalled: bool = False


@dataclass(frozen=True, slots=True)
class FlightStepResult:
    took_off: bool = False
    landed: bool = False
    stall_started: bool = False
    stall_recovered: bool = False
    landing_blocked: bool = False
