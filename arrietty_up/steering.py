"""Background OpenVR pose source for bicycle steering.

OpenVR is used only for the stem-mounted VIVE controller.  UPBGE/OpenXR owns
the HMD presentation; the OpenVR client is deliberately retained for the
Blender process lifetime because shutting it down can also tear down SteamVR.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time

from . import constants as c


POLL_RATE_HZ = 60.0
TRACKING_STALE_SECONDS = 0.5
_openvr_init_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class SteeringSnapshot:
    status: str = "IDLE"
    message: str = "VIVE steering is stopped"
    tracking: bool = False
    serial: str = c.STEERING_CONTROLLER_SERIAL
    model: str = ""
    raw_angle_degrees: float = 0.0
    effective_angle_degrees: float = 0.0
    sample_count: int = 0
    last_pose_seconds: float = 0.0


def _get_openvr_system(openvr):
    with _openvr_init_lock:
        system = getattr(openvr, "_arrietty_vr_system", None)
        if system is None:
            system = openvr.init(openvr.VRApplication_Background)
            openvr._arrietty_vr_system = system
        return system


def _rotation_tuple(matrix) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        tuple(float(matrix[row][column]) for column in range(3))
        for row in range(3)
    )


def world_yaw_degrees(current, baseline) -> float:
    """Return signed world-Y rotation after removing mounting orientation."""
    delta_00 = sum(current[0][index] * baseline[0][index] for index in range(3))
    delta_02 = sum(current[0][index] * baseline[2][index] for index in range(3))
    return math.degrees(math.atan2(delta_02, delta_00))


def effective_steering_degrees(raw_degrees: float) -> float:
    magnitude = max(0.0, abs(raw_degrees) - c.STEERING_DEADZONE_DEGREES)
    effective = math.copysign(magnitude * c.STEERING_GAIN, raw_degrees)
    return max(
        -c.MAX_EFFECTIVE_STEERING_DEGREES,
        min(c.MAX_EFFECTIVE_STEERING_DEGREES, effective),
    )


class SteeringController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = "IDLE"
        self._message = "VIVE steering is stopped"
        self._tracking = False
        self._model = ""
        self._raw_angle_degrees = 0.0
        self._effective_angle_degrees = 0.0
        self._sample_count = 0
        self._last_pose_seconds = 0.0
        self._recenter_generation = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.running:
            return False
        self._stop.clear()
        with self._lock:
            self._status = "STARTING"
            self._message = "Starting VIVE steering; keep the handle centered"
            self._tracking = False
            self._model = ""
            self._raw_angle_degrees = 0.0
            self._effective_angle_degrees = 0.0
            self._sample_count = 0
            self._last_pose_seconds = 0.0
            self._recenter_generation += 1
        self._thread = threading.Thread(
            target=self._worker_main,
            name="ArriettyOpenVRSteering",
            daemon=True,
        )
        self._thread.start()
        return True

    def recenter(self) -> None:
        with self._lock:
            self._recenter_generation += 1
            self._status = "CALIBRATING"
            self._message = "Calibrating centered VIVE handle pose"
            self._tracking = False
            self._raw_angle_degrees = 0.0
            self._effective_angle_degrees = 0.0

    def stop(self, timeout: float = 1.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        if thread is not None and thread.is_alive():
            return False
        self._thread = None
        with self._lock:
            self._status = "IDLE"
            self._message = "VIVE steering is stopped"
            self._tracking = False
            self._raw_angle_degrees = 0.0
            self._effective_angle_degrees = 0.0
        return True

    def snapshot(self) -> SteeringSnapshot:
        with self._lock:
            tracking = self._tracking
            last_pose = self._last_pose_seconds
            if tracking and time.monotonic() - last_pose > TRACKING_STALE_SECONDS:
                tracking = False
            return SteeringSnapshot(
                status=self._status,
                message=self._message,
                tracking=tracking,
                model=self._model,
                raw_angle_degrees=self._raw_angle_degrees,
                effective_angle_degrees=(
                    self._effective_angle_degrees if tracking else 0.0
                ),
                sample_count=self._sample_count,
                last_pose_seconds=last_pose,
            )

    def _publish(
        self,
        *,
        status: str,
        message: str,
        tracking: bool,
        raw_degrees: float = 0.0,
        effective_degrees: float = 0.0,
        model: str | None = None,
        sample: bool = False,
    ) -> None:
        with self._lock:
            self._status = status
            self._message = message
            self._tracking = tracking
            self._raw_angle_degrees = raw_degrees
            self._effective_angle_degrees = effective_degrees
            if model is not None:
                self._model = model
            if sample:
                self._sample_count += 1
                self._last_pose_seconds = time.monotonic()

    def _worker_main(self) -> None:
        try:
            import openvr

            system = _get_openvr_system(openvr)
            self._publish(
                status="SEARCHING",
                message=f"Searching for VIVE {c.STEERING_CONTROLLER_SERIAL}",
                tracking=False,
            )
            device_index = None
            baseline = None
            filtered = 0.0
            applied_recenter = -1
            period = 1.0 / POLL_RATE_HZ
            while not self._stop.is_set():
                started = time.perf_counter()
                poses = system.getDeviceToAbsoluteTrackingPose(
                    openvr.TrackingUniverseStanding,
                    0.0,
                    openvr.k_unMaxTrackedDeviceCount,
                )
                if device_index is not None and not poses[device_index].bDeviceIsConnected:
                    device_index = None
                    baseline = None
                if device_index is None:
                    for index, pose in enumerate(poses):
                        if not pose.bDeviceIsConnected:
                            continue
                        try:
                            serial = system.getStringTrackedDeviceProperty(
                                index, openvr.Prop_SerialNumber_String
                            )
                        except Exception:
                            continue
                        if (serial == c.STEERING_CONTROLLER_SERIAL or
                            (not c.STEERING_CONTROLLER_SERIAL and
                             system.getTrackedDeviceClass(index) == openvr.TrackedDeviceClass_Controller)):
                            device_index = index
                            baseline = None
                            try:
                                model = system.getStringTrackedDeviceProperty(
                                    index, openvr.Prop_ModelNumber_String
                                )
                            except Exception:
                                model = "VIVE Controller"
                            self._publish(
                                status="CALIBRATING",
                                message="Keep the VIVE handle centered",
                                tracking=False,
                                model=model,
                            )
                            break

                valid = device_index is not None and bool(
                    poses[device_index].bDeviceIsConnected
                    and poses[device_index].bPoseIsValid
                )
                if valid:
                    current = _rotation_tuple(
                        poses[device_index].mDeviceToAbsoluteTracking
                    )
                    with self._lock:
                        recenter_generation = self._recenter_generation
                    if baseline is None or applied_recenter != recenter_generation:
                        baseline = current
                        filtered = 0.0
                        applied_recenter = recenter_generation
                        raw = 0.0
                    else:
                        raw = world_yaw_degrees(current, baseline)
                        filtered += 0.25 * (raw - filtered)
                    effective = effective_steering_degrees(filtered)
                    self._publish(
                        status="TRACKING",
                        message="VIVE steering is ready",
                        tracking=True,
                        raw_degrees=filtered,
                        effective_degrees=effective,
                        sample=True,
                    )
                else:
                    self._publish(
                        status="LOST" if baseline is not None else "SEARCHING",
                        message=(
                            "VIVE steering tracking was lost"
                            if baseline is not None
                            else f"Searching for VIVE {c.STEERING_CONTROLLER_SERIAL}"
                        ),
                        tracking=False,
                    )
                elapsed = time.perf_counter() - started
                if elapsed < period:
                    self._stop.wait(period - elapsed)
        except Exception as error:
            self._publish(
                status="ERROR",
                message=f"VIVE steering error: {error}",
                tracking=False,
            )
