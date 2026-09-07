"""Digital flight and in-flight tuning controls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from . import constants as c
from .models import FlightTuningValues

GESTURE_TRIGGER = 0.45
GESTURE_RELEASE = 0.20


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class DigitalControlChange:
    pitch_changed: bool = False
    roll_changed: bool = False
    reset: bool = False


class DigitalFlightControls:
    def __init__(self) -> None:
        self.pitch_degrees = 0.0
        self.roll_right_degrees = 0.0
        self._pitch_armed = True
        self._roll_armed = True

    @property
    def bank_degrees(self) -> float:
        return -self.roll_right_degrees

    def reset(self, axes: tuple[float, float] = (0.0, 0.0)) -> None:
        self.pitch_degrees = 0.0
        self.roll_right_degrees = 0.0
        self._pitch_armed = abs(axes[0]) <= GESTURE_RELEASE
        self._roll_armed = abs(axes[1]) <= GESTURE_RELEASE

    def reset_commands(self, axes: tuple[float, float] = (0.0, 0.0)) -> DigitalControlChange:
        had_pitch = abs(self.pitch_degrees) > 1.0e-9
        had_roll = abs(self.roll_right_degrees) > 1.0e-9
        self.reset(axes)
        return DigitalControlChange(had_pitch, had_roll, True)

    def update_joystick(self, axes: tuple[float, float]) -> DigitalControlChange:
        pitch_step, self._pitch_armed = self._consume_gesture(axes[0], self._pitch_armed)
        roll_step, self._roll_armed = self._consume_gesture(axes[1], self._roll_armed)
        pitch_changed = self.step_pitch(pitch_step).pitch_changed if pitch_step else False
        roll_changed = self.step_roll_right(-roll_step).roll_changed if roll_step else False
        return DigitalControlChange(pitch_changed, roll_changed, False)

    def step_pitch(self, direction: int) -> DigitalControlChange:
        previous = self.pitch_degrees
        if direction:
            self.pitch_degrees = _clamp(
                previous + (c.FLIGHT_CONTROL_STEP_DEGREES if direction > 0 else -c.FLIGHT_CONTROL_STEP_DEGREES),
                -c.FLIGHT_MAX_PITCH_DEGREES,
                c.FLIGHT_MAX_PITCH_DEGREES,
            )
        return DigitalControlChange(abs(previous - self.pitch_degrees) > 1.0e-9)

    def step_roll_right(self, direction: int) -> DigitalControlChange:
        previous = self.roll_right_degrees
        if direction:
            self.roll_right_degrees = _clamp(
                previous + (c.FLIGHT_CONTROL_STEP_DEGREES if direction > 0 else -c.FLIGHT_CONTROL_STEP_DEGREES),
                -c.FLIGHT_MAX_BANK_DEGREES,
                c.FLIGHT_MAX_BANK_DEGREES,
            )
        return DigitalControlChange(roll_changed=abs(previous - self.roll_right_degrees) > 1.0e-9)

    @staticmethod
    def _consume_gesture(value: float, armed: bool) -> tuple[int, bool]:
        if not armed:
            return (0, True) if abs(value) <= GESTURE_RELEASE else (0, False)
        if abs(value) < GESTURE_TRIGGER:
            return 0, True
        return (1 if value > 0.0 else -1), False


@dataclass(frozen=True, slots=True)
class FlightButtonAction:
    pitch_step: int = 0
    roll_right_step: int = 0


class FlightButtonChord:
    """Resolve Button 3/4 singles versus the 80 ms pitch-up chord."""

    def __init__(self, window_seconds: float = 0.080) -> None:
        self.window_seconds = window_seconds
        self.pending_roll_right_step = 0
        self.pending_since_seconds = 0.0

    def reset(self) -> None:
        self.pending_roll_right_step = 0
        self.pending_since_seconds = 0.0

    def flush(self, now_seconds: float) -> FlightButtonAction | None:
        if (
            self.pending_roll_right_step == 0
            or now_seconds - self.pending_since_seconds < self.window_seconds
        ):
            return None
        action = FlightButtonAction(
            roll_right_step=self.pending_roll_right_step
        )
        self.pending_roll_right_step = 0
        return action

    def update(
        self,
        pressed_edges: int,
        current_buttons: int,
        now_seconds: float,
    ) -> tuple[FlightButtonAction, ...]:
        actions: list[FlightButtonAction] = []
        expired = self.flush(now_seconds)
        if expired is not None:
            actions.append(expired)
        left_edge = bool(pressed_edges & 0x04)
        right_edge = bool(pressed_edges & 0x08)
        if not left_edge and not right_edge:
            return tuple(actions)
        both_held = current_buttons & 0x0C == 0x0C
        if (left_edge and right_edge) or (
            both_held
            and self.pending_roll_right_step != 0
            and now_seconds - self.pending_since_seconds <= self.window_seconds
        ):
            self.pending_roll_right_step = 0
            actions.append(FlightButtonAction(pitch_step=1))
            return tuple(actions)
        self.pending_roll_right_step = -1 if left_edge else 1
        self.pending_since_seconds = now_seconds
        return tuple(actions)


class TuningParameter(IntEnum):
    TEST_PROPULSION_POWER = 0
    POSITIVE_CLIMB_MULTIPLIER = 1
    PITCH_RESPONSE_RATE = 2
    BANK_RESPONSE_RATE = 3


@dataclass(frozen=True, slots=True)
class FlightTuningChange:
    entered: bool = False
    value_changed: bool = False
    advanced: bool = False
    completed: bool = False


class FlightTuningControls:
    def __init__(self) -> None:
        self.values = FlightTuningValues()
        self.active = False
        self.parameter = TuningParameter.TEST_PROPULSION_POWER
        self._horizontal_armed = True

    def reset(self, axes: tuple[float, float] = (0.0, 0.0)) -> None:
        self.active = False
        self.parameter = TuningParameter.TEST_PROPULSION_POWER
        self._horizontal_armed = abs(axes[0]) <= GESTURE_RELEASE

    def press_switch(self, axes: tuple[float, float] = (0.0, 0.0)) -> FlightTuningChange:
        self._horizontal_armed = abs(axes[0]) <= GESTURE_RELEASE
        if not self.active:
            self.active = True
            self.parameter = TuningParameter.TEST_PROPULSION_POWER
            return FlightTuningChange(entered=True)
        if self.parameter < TuningParameter.BANK_RESPONSE_RATE:
            self.parameter = TuningParameter(self.parameter + 1)
            return FlightTuningChange(advanced=True)
        self.active = False
        self.parameter = TuningParameter.TEST_PROPULSION_POWER
        return FlightTuningChange(completed=True)

    def update_joystick(self, axes: tuple[float, float]) -> FlightTuningChange:
        if not self.active:
            return FlightTuningChange()
        if not self._horizontal_armed:
            if abs(axes[0]) <= GESTURE_RELEASE:
                self._horizontal_armed = True
            return FlightTuningChange()
        if abs(axes[0]) < GESTURE_TRIGGER:
            return FlightTuningChange()
        self._horizontal_armed = False
        return FlightTuningChange(value_changed=self._step(1 if axes[0] > 0.0 else -1))

    def _step(self, direction: int) -> bool:
        sign = 1.0 if direction >= 0 else -1.0
        values = self.values
        if self.parameter == TuningParameter.TEST_PROPULSION_POWER:
            before = values.test_propulsion_power_watts
            values.test_propulsion_power_watts = _clamp(
                before + sign * c.FLIGHT_TEST_PROPULSION_POWER_STEP_WATTS,
                c.FLIGHT_MIN_TEST_PROPULSION_POWER_WATTS,
                c.FLIGHT_MAX_TEST_PROPULSION_POWER_WATTS,
            )
            return before != values.test_propulsion_power_watts
        if self.parameter == TuningParameter.POSITIVE_CLIMB_MULTIPLIER:
            before = values.positive_climb_multiplier
            values.positive_climb_multiplier = _clamp(
                before + sign * c.FLIGHT_POSITIVE_CLIMB_MULTIPLIER_STEP,
                c.FLIGHT_MIN_POSITIVE_CLIMB_MULTIPLIER,
                c.FLIGHT_MAX_POSITIVE_CLIMB_MULTIPLIER,
            )
            return before != values.positive_climb_multiplier
        if self.parameter == TuningParameter.PITCH_RESPONSE_RATE:
            before = values.pitch_rate_degrees_per_second
            values.pitch_rate_degrees_per_second = _clamp(
                before + sign * c.FLIGHT_PITCH_RATE_STEP_DEGREES_PER_SECOND,
                c.FLIGHT_MIN_PITCH_RATE_DEGREES_PER_SECOND,
                c.FLIGHT_MAX_PITCH_RATE_TUNING_DEGREES_PER_SECOND,
            )
            return before != values.pitch_rate_degrees_per_second
        before = values.bank_rate_degrees_per_second
        values.bank_rate_degrees_per_second = _clamp(
            before + sign * c.FLIGHT_BANK_RATE_STEP_DEGREES_PER_SECOND,
            c.FLIGHT_MIN_BANK_RATE_DEGREES_PER_SECOND,
            c.FLIGHT_MAX_BANK_RATE_TUNING_DEGREES_PER_SECOND,
        )
        return before != values.bank_rate_degrees_per_second

    def compact_status(self) -> str:
        if not self.active:
            return "TUNE OFF"
        labels = ("TEST PROP", "POWER BOOST", "PITCH RATE", "ROLL RATE")
        value = self.values
        formatted = (
            f"{value.test_propulsion_power_watts:.0f} W",
            f"x{value.positive_climb_multiplier:.0f}",
            f"{value.pitch_rate_degrees_per_second:.0f} DEG/S",
            f"{value.bank_rate_degrees_per_second:.0f} DEG/S",
        )[int(self.parameter)]
        return f"TUNE {int(self.parameter) + 1}/4 {labels[int(self.parameter)]} {formatted}"
