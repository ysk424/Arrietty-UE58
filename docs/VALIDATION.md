# Validation and operational baseline

Date: 2026-09-07 (Asia/Tokyo).

## Operational handoff

After the forward-direction revision, the user stated
「今晩から本気でつかえます」 (ready for serious use starting this evening)
and requested documentation, persistent project notes and a push to the
separate public repository. The implementation baseline for this handoff is
[`b3b0cc1`](https://github.com/ysk424/Arrietty-UE58/commit/b3b0cc1).
This records the user's decision to begin using the simulator; it is not a
claim that every device and every item in the reference checklist was tested.

The agreed operating sequence is **P, look straight ahead with the handle
centered, then Button 1**. The initial HMD view defines forward once. The
handle steers afterward; turning the head does not steer. R selects a new
forward from the current view, while subsequent Button 1 is the 2m recovery.
The heart-rate transmitter was not connected during this work and its live
acceptance remains open. Its absence does not block riding.

Project decisions and continuation notes are preserved in
[HANDOFF.md](HANDOFF.md), with [AGENTS.md](../AGENTS.md) as the entry point for
future coding sessions.

## Verified offline

- UE 5.8.2, engine changelist 56702186, Win64 Development Editor target built
  successfully using the installed toolchain.
- 84 Python tests pass: accepted model/protocol/control regressions plus UE
  coordinate mapping, alignment gating, complete flight/landing/restart,
  authenticated packet validation and an actual loopback watchdog test.
  Added checks exercise ground movement across bearings and R realignment
  without movement, a recovery jump, or a ride-clock reset before a fresh ack.
  HMD bearing is latched before first motion, including the measured diagonal
  case; later gaze values and stale IDs cannot steer the bicycle. Live motion
  requires a finite camera-confirmed bearing.
  The five original UPBGE-launcher-only tests are outside this UE repository.
- Windows PowerShell 5.1 and PowerShell 7 both pass real native-argument
  launcher regressions with an omitted or explicit local date. An omitted
  date leaves Python's Tuvalu-date default in effect; no empty native argument
  is required. A full offline launch/flight/exit also passed in PowerShell 5.1.
- Native automation `Arrietty.Coordinates.Attitude` passes. Tests independently
  establish nose-up pitch and inside-wing-down bank in UE transforms.
- `Arrietty.Coordinates.HmdAlignment` passes with the real UE camera path and
  simulated HMD poses: 15 combinations of bicycle/room yaw, including reversed
  and diagonal room headings. Pre-button view preservation, first movement
  along that view, eye height, free head turning, recalibration with flight
  pitch/bank, buffered old poses, invalid tracking and unavailable-camera gating
  are checked. No live HMD pose is used by this test.
- Latest Secret World Runtime: **20260905102318005**, SHA-256
  `e4bd10cdea5b936e5f73e6e30b8eef34424c55253571b8ef30b04eb56540be41`.
  1,409 source meshes, 428,029 triangles, 664 draw sections; exactly five
  original collision surfaces become 205 spatial/material collision sections.
  Stream length, finite positions/normals, section counts, attributions and
  geometry/reef/source digests pass independent validation.
- A real UE process with `-nohmd -RenderOffscreen` drives the Python bridge,
  starts via simulated Button 1, arms flight via Button 2 and pitches up via
  Button 3+4. It moves, takes off, returns to setup and exits normally. The
  test requires actual received telemetry, movement and an airborne sample.
- A captured UE frame was inspected: sunset sky, runway, houses/vegetation,
  readable three-part instrument panel, circular PFD and live values are
  present. The screenshot is local under
  `unreal/ArriettyUE/Saved/Screenshots/ue-offline.png`.
- Automated verification did not start hardware services. The user's existing
  UPBGE source, flight logs and Secret World source remain unchanged.

Commands:

```powershell
.\tools\prepare_ue.ps1
.\tools\test_ue.ps1 -Smoke
```

The native test and offline screenshot are not substitutes for HMD acceptance.
No live VR frame-rate or comfort claim has been established. The application
currently launches through the installed UE Editor's standalone game mode;
a packaged Windows distribution is not part of this source release.

## Direction reports and final behavior

The user confirmed pedalling moves the scene, but reported apparent backward
or diagonally backward movement. The recorded ground track agrees with its
logged bicycle heading (apart from one recovery operation); the original log
did not include rendered-camera yaw, so it cannot establish the HMD's facing
direction or the root cause of that report. Revision `5bf08bd` added final
camera confirmation, R realignment and view/vehicle/raw-pose yaw logging.

The next live report described forward-right movement and clarified that
Button 1 should latch the initial HMD-forward direction, with handle steering
afterward. The view log showed zero residual at alignment, followed by roughly
10-20 degrees of view/course difference during initial riding. The revised
calibration now preserves the pre-button view and sends its horizontal bearing
to the simulation instead of rotating the camera to the preset runway course.
This behavior is implemented in `b3b0cc1`; offline tests pass and the subsequent
user decision to begin operation is recorded above. No fixed 15-, 45- or
180-degree offset was introduced to compensate for one observed pose.

## Reference checklist for ongoing use

Use this checklist when validating changes or recording additional device
results. The operational handoff does not imply a separate PASS for every
item below.

1. Start SteamVR, close the UPBGE simulator, and run `./start-ue.ps1` from this
   repository. The user's ignored `settings.local.json` is already configured.
2. In setup, select/apply the desired Tuvalu local date/time, then press P.
   Confirm the scene appears in the HMD and the three-part panel is readable.
3. Face the physical bicycle direction with the handle centered and press
   Button 1. Confirm alignment, straight-ahead pedalling, elapsed time from
   zero, and correct left/right steering. HR may remain disconnected.
   If facing is offset, stop pedalling, face along the bicycle with the handle
   centered, and press R. Confirm the panel is ahead and the next pedal motion
   moves forward; position and ride time should be preserved.
4. Check Button 6 held/released grade, flight mode, pitch-up takeoff, both banks,
   landing, and the return-to-ground restriction while airborne. Check the
   approximately 2m Button 1 recovery at low speed.
5. Confirm fan airflow follows bicycle speed on the ground and airspeed in
   flight. Check Joystick 2 reset and Joystick 1 tuning. PTT requires the
   pre-existing voice bridge to be running.
6. Press Esc. Confirm fan stops, T2 releases, final CSV exists and setup becomes
   usable. Apply a different local time and start again. Close the window and
   confirm both UE and bridge processes exit.
7. When the heart-rate transmitter is available, verify discovery, live BPM,
   stale indication and reconnection separately.

Record further device results here with the date and implementation revision.
Keep user-reported operation, automated verification and individual hardware
measurements distinct.

## Evening report: apparent invisible wall / VIVE occlusion

During the 2026-09-07 evening session, the user reported an apparent transparent
wall when flying south and places where the flight log seemed to stop.
The CSV remained continuous (no sampling gaps over 0.5s), while position and
altitude froze despite a nonzero displayed airspeed. Four pauses longer than
0.5s occurred around 20:14-20:15 JST, lasting approximately 14.0, 7.0, 4.8 and
5.9 seconds. The first was at east -883.734m, north -788.172m, altitude 10.656m,
with displayed speed 21.108km/h. UE continued to report valid HMD tracking.

These positions are inside the scenery coverage. The existing bridge requires
valid handle-VIVE tracking as well as HMD alignment before advancing the flight
model. A handle tracking loss therefore freezes motion and flight state while
CSV sampling continues; it can feel like an invisible wall.

The user identified the physical cause: only one of the four installed
Lighthouses was visible to the handle-mounted VIVE, and the rider's body could
occlude it. The user chose to arrange visibility to two Lighthouses. This
records the user's diagnosis and planned placement change; the post-adjustment
flight result has not yet been reported.

The user also suspected reflections from the Surface Studio screen in front
of the handle and proposed covering the screen with cloth. Covering reflective
surfaces is consistent with [VIVE's Lighthouse guidance](https://blog.vive.com/us/roomscale-101/).
Reflection suppression should be evaluated alongside unobstructed direct
visibility to two base stations; a cover does not remove physical occlusion.
The screen's contribution and the result of the cloth test remain unconfirmed.

The proposed alternative of continuing flight with neutral steering during a
VIVE tracking loss was not implemented. Keep the current tracking-loss stop
behavior while evaluating the placement correction. No running session was
restarted or changed during this diagnosis. The diagnostic logs were preserved
locally under the ignored `logs/vive-occlusion-20260907-2014/` directory.
