"""Human-powered flight model ported from Arrietty-UE 0.13.1."""

from __future__ import annotations

from dataclasses import replace
import math

from . import constants as c
from .models import FlightState, FlightStepResult, FlightTuningValues

STANDARD_GRAVITY = 9.80665


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _interp_constant(current: float, target: float, delta: float, speed: float) -> float:
    distance = target - current
    step = max(0.0, speed) * max(0.0, delta)
    if abs(distance) <= step:
        return target
    return current + math.copysign(step, distance)


def aircraft_weight_newtons() -> float:
    return c.FLIGHT_EFFECTIVE_MASS_KG * STANDARD_GRAVITY


def dynamic_pressure(airspeed_mps: float) -> float:
    return 0.5 * c.FLIGHT_AIR_DENSITY_KG_PER_CUBIC_METER * max(0.0, airspeed_mps) ** 2


def maximum_lift_coefficient() -> float:
    stall_speed = c.FLIGHT_STALL_SPEED_KMH / 3.6
    return aircraft_weight_newtons() / (dynamic_pressure(stall_speed) * c.FLIGHT_WING_AREA_SQUARE_METERS)


def trim_lift_coefficient() -> float:
    best_glide_speed = c.FLIGHT_BEST_GLIDE_SPEED_KMH / 3.6
    return aircraft_weight_newtons() / (dynamic_pressure(best_glide_speed) * c.FLIGHT_WING_AREA_SQUARE_METERS)


def wing_incidence_degrees() -> float:
    return trim_lift_coefficient() / c.FLIGHT_LIFT_CURVE_SLOPE_PER_DEGREE


def parasite_drag_coefficient() -> float:
    return trim_lift_coefficient() / (2.0 * c.FLIGHT_GLIDE_RATIO)


def induced_drag_factor() -> float:
    trim = trim_lift_coefficient()
    return parasite_drag_coefficient() / (trim * trim)


def _lift_coefficient(angle_of_attack_degrees: float, stalled: bool) -> float:
    attached = _clamp(
        angle_of_attack_degrees * c.FLIGHT_LIFT_CURVE_SLOPE_PER_DEGREE,
        -maximum_lift_coefficient(),
        maximum_lift_coefficient(),
    )
    return attached * c.FLIGHT_POST_STALL_LIFT_FACTOR if stalled else attached


def _drag_coefficient(lift_coefficient: float, stalled: bool) -> float:
    return (
        parasite_drag_coefficient()
        + induced_drag_factor() * lift_coefficient**2
        + (c.FLIGHT_POST_STALL_DRAG_COEFFICIENT if stalled else 0.0)
    )


def aerodynamic_forces(
    airspeed_mps: float,
    pitch_degrees: float,
    flight_path_angle_degrees: float,
    stalled: bool,
) -> tuple[float, float, float]:
    angle_of_attack = _clamp(
        wing_incidence_degrees() + pitch_degrees - flight_path_angle_degrees,
        -45.0,
        45.0,
    )
    lift_coefficient = _lift_coefficient(angle_of_attack, stalled)
    pressure_area = dynamic_pressure(airspeed_mps) * c.FLIGHT_WING_AREA_SQUARE_METERS
    lift = pressure_area * lift_coefficient
    drag = pressure_area * _drag_coefficient(lift_coefficient, stalled)
    return lift, drag, angle_of_attack


def initialize_human_powered_flight(initial_airspeed_kmh: float = 0.0) -> FlightState:
    return FlightState(airspeed_meters_per_second=max(0.0, initial_airspeed_kmh / 3.6))


def human_powered_flight_drag_newtons(airspeed_mps: float) -> float:
    pressure_area = dynamic_pressure(airspeed_mps) * c.FLIGHT_WING_AREA_SQUARE_METERS
    if pressure_area <= 1.0e-8:
        return 0.0
    required_lift = _clamp(aircraft_weight_newtons() / pressure_area, 0.0, maximum_lift_coefficient())
    return pressure_area * _drag_coefficient(required_lift, False)


def human_powered_flight_lift_newtons(
    airspeed_mps: float,
    pitch_degrees: float,
    flight_path_angle_degrees: float,
    stalled: bool = False,
) -> float:
    return aerodynamic_forces(airspeed_mps, pitch_degrees, flight_path_angle_degrees, stalled)[0]


def human_powered_level_flight_power_watts(airspeed_kmh: float) -> float:
    airspeed = max(0.0, airspeed_kmh / 3.6)
    return human_powered_flight_drag_newtons(airspeed) * airspeed / c.FLIGHT_PROPELLER_EFFICIENCY


def human_powered_flight_power_climb_rate_mps(
    propulsion_power_watts: float,
    energy_airspeed_kmh: float,
    positive_climb_multiplier: float,
) -> float:
    airspeed = max(0.0, energy_airspeed_kmh / 3.6)
    effective_power = max(0.0, propulsion_power_watts) * c.FLIGHT_PROPELLER_EFFICIENCY
    power_balance = effective_power - human_powered_flight_drag_newtons(airspeed) * airspeed
    virtual_balance = power_balance * max(1.0, positive_climb_multiplier) if power_balance > 0.0 else power_balance
    return virtual_balance / aircraft_weight_newtons()


def human_powered_flight_control_authority(airspeed_mps: float, stalled: bool) -> float:
    reference_speed = c.FLIGHT_CONTROL_REFERENCE_SPEED_KMH / 3.6
    ratio = (max(0.0, airspeed_mps) / reference_speed) ** 2
    normal = _clamp(ratio, c.FLIGHT_MIN_CONTROL_AUTHORITY, c.FLIGHT_MAX_CONTROL_AUTHORITY)
    return normal * (0.25 if stalled else 1.0)


def human_powered_flight_propulsion_power_watts(rider_power_watts: float) -> float:
    return max(0.0, rider_power_watts)


def _update_attitude_metrics(state: FlightState) -> None:
    if not state.airborne:
        state.vertical_speed_meters_per_second = 0.0
        state.flight_path_angle_degrees = 0.0
        state.angle_of_attack_degrees = 0.0
        return
    path_radians = math.radians(state.flight_path_angle_degrees)
    state.vertical_speed_meters_per_second = state.airspeed_meters_per_second * math.sin(path_radians)
    state.angle_of_attack_degrees = _clamp(
        wing_incidence_degrees() + state.pitch_degrees - state.flight_path_angle_degrees,
        -45.0,
        45.0,
    )


def step_human_powered_flight(
    state: FlightState,
    rider_power_watts: float,
    target_pitch_degrees: float,
    target_bank_degrees: float,
    rudder_degrees: float,
    delta_seconds: float,
    can_land: bool,
    tuning: FlightTuningValues | None = None,
) -> FlightStepResult:
    tuning = tuning or FlightTuningValues()
    delta = _clamp(delta_seconds, 0.0, 0.25)
    if delta <= 0.0:
        return FlightStepResult()

    power = max(0.0, rider_power_watts)
    airspeed = max(0.0, state.airspeed_meters_per_second)
    effective_power = power * c.FLIGHT_PROPELLER_EFFICIENCY
    state.control_authority = human_powered_flight_control_authority(airspeed, state.stalled)
    commanded_pitch = _clamp(target_pitch_degrees, -c.FLIGHT_MAX_PITCH_DEGREES, c.FLIGHT_MAX_PITCH_DEGREES)
    commanded_bank = _clamp(target_bank_degrees, -c.FLIGHT_MAX_BANK_DEGREES, c.FLIGHT_MAX_BANK_DEGREES)
    target_pitch = min(commanded_pitch, -10.0) if state.stalled else commanded_pitch
    # Keep the aileron/bank response visible while flight is armed on the
    # runway. Previously the ground branch forced bank back to zero, which
    # made both Button 3/4 and Joystick 2 appear broken until takeoff.
    target_bank = commanded_bank
    pitch_authority = max(0.75, state.control_authority) if state.stalled else state.control_authority
    state.pitch_degrees = _interp_constant(
        state.pitch_degrees,
        target_pitch,
        delta,
        max(0.1, tuning.pitch_rate_degrees_per_second) * pitch_authority,
    )
    state.bank_degrees = _interp_constant(
        state.bank_degrees,
        target_bank,
        delta,
        max(0.1, tuning.bank_rate_degrees_per_second) * state.control_authority,
    )
    rudder_input = _clamp(rudder_degrees / c.MAX_EFFECTIVE_STEERING_DEGREES, -1.0, 1.0)
    lift, drag, angle_of_attack = aerodynamic_forces(
        airspeed,
        state.pitch_degrees,
        state.flight_path_angle_degrees,
        state.stalled,
    )

    if not state.airborne:
        state.altitude_meters = 0.0
        state.vertical_speed_meters_per_second = 0.0
        state.flight_path_angle_degrees = 0.0
        state.stalled = False
        thrust = 0.0 if power <= 0.0 else min(c.FLIGHT_MAX_PROPELLER_THRUST_NEWTONS, effective_power / max(2.0, airspeed))
        wheel_load = max(0.0, aircraft_weight_newtons() - lift)
        ground_drag = drag + wheel_load * c.FLIGHT_GROUND_ROLLING_RESISTANCE
        acceleration = (thrust - ground_drag) / c.FLIGHT_EFFECTIVE_MASS_KG
        if airspeed <= 0.05 and thrust <= ground_drag:
            acceleration = 0.0
        airspeed = max(0.0, airspeed + acceleration * delta)
        takeoff_fraction = _clamp(airspeed / (c.TAKEOFF_SPEED_KMH / 3.6), 0.0, 1.0)
        state.heading_rate_degrees_per_second = rudder_input * c.FLIGHT_MAX_RUDDER_TURN_RATE_DEGREES * takeoff_fraction
        took_off = airspeed * 3.6 >= c.TAKEOFF_SPEED_KMH and commanded_pitch > 0.0 and lift >= aircraft_weight_newtons()
        state.airborne = took_off
        state.airspeed_meters_per_second = airspeed
        state.control_authority = human_powered_flight_control_authority(airspeed, state.stalled)
        _update_attitude_metrics(state)
        return FlightStepResult(took_off=took_off)

    was_stalled = state.stalled
    stall_angle = maximum_lift_coefficient() / c.FLIGHT_LIFT_CURVE_SLOPE_PER_DEGREE
    if not state.stalled and (airspeed * 3.6 < c.FLIGHT_STALL_SPEED_KMH or angle_of_attack >= stall_angle):
        state.stalled = True
    elif (
        state.stalled
        and airspeed * 3.6 >= c.FLIGHT_STALL_RECOVERY_SPEED_KMH
        and angle_of_attack <= stall_angle * 0.80
        and commanded_pitch <= 0.0
    ):
        state.stalled = False
    stall_started = not was_stalled and state.stalled
    stall_recovered = was_stalled and not state.stalled
    lift, drag, _ = aerodynamic_forces(
        airspeed,
        state.pitch_degrees,
        state.flight_path_angle_degrees,
        state.stalled,
    )

    aerodynamic_power_required = drag * airspeed
    raw_surplus_power = effective_power - aerodynamic_power_required
    simulated_effective_power = effective_power + max(0.0, raw_surplus_power) * (max(1.0, tuning.positive_climb_multiplier) - 1.0)
    path_radians = math.radians(state.flight_path_angle_degrees)
    propulsive_force = simulated_effective_power / max(3.0, airspeed)
    along_path_acceleration = _clamp(
        (propulsive_force - drag - aircraft_weight_newtons() * math.sin(path_radians)) / c.FLIGHT_EFFECTIVE_MASS_KG,
        -3.0,
        3.0,
    )
    airspeed = max(0.0, airspeed + along_path_acceleration * delta)

    bank_radians = math.radians(state.bank_degrees)
    normal_force = lift * math.cos(bank_radians) - aircraft_weight_newtons() * math.cos(path_radians)
    path_rate = _clamp(
        normal_force / (c.FLIGHT_EFFECTIVE_MASS_KG * max(3.0, airspeed)),
        math.radians(-45.0),
        math.radians(45.0),
    )
    state.flight_path_angle_degrees = _clamp(
        state.flight_path_angle_degrees + math.degrees(path_rate) * delta,
        -45.0,
        45.0,
    )
    state.airspeed_meters_per_second = airspeed
    state.control_authority = human_powered_flight_control_authority(airspeed, state.stalled)
    updated_path_radians = math.radians(state.flight_path_angle_degrees)
    bank_turn_rate = math.degrees(
        lift * math.sin(bank_radians)
        / (c.FLIGHT_EFFECTIVE_MASS_KG * max(3.0, airspeed) * max(0.2, math.cos(updated_path_radians)))
    )
    state.heading_rate_degrees_per_second = _clamp(
        bank_turn_rate + rudder_input * c.FLIGHT_MAX_RUDDER_TURN_RATE_DEGREES * state.control_authority,
        -60.0,
        60.0,
    )
    _update_attitude_metrics(state)
    state.altitude_meters += state.vertical_speed_meters_per_second * delta

    landed = landing_blocked = False
    if state.altitude_meters <= 0.0 and state.vertical_speed_meters_per_second <= 0.0:
        if can_land:
            state.altitude_meters = 0.0
            state.vertical_speed_meters_per_second = 0.0
            state.flight_path_angle_degrees = 0.0
            state.bank_degrees = 0.0
            state.pitch_degrees = 0.0
            state.heading_rate_degrees_per_second = 0.0
            state.airborne = False
            state.stalled = False
            landed = True
        else:
            state.altitude_meters = 0.5
            state.vertical_speed_meters_per_second = 0.0
            state.flight_path_angle_degrees = 0.0
            landing_blocked = True
    _update_attitude_metrics(state)
    return FlightStepResult(
        landed=landed,
        stall_started=stall_started,
        stall_recovered=stall_recovered,
        landing_blocked=landing_blocked,
    )


def copy_state(state: FlightState) -> FlightState:
    return replace(state)
