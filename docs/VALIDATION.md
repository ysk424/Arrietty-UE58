# Validation / next hardware session

Date: 2026-09-07 (Asia/Tokyo).

## Verified offline

- UE 5.8.2, engine changelist 56702186, Win64 Development Editor target built
  successfully using the installed toolchain.
- 78 Python tests pass: accepted model/protocol/control regressions plus UE
  coordinate mapping, alignment gating, complete flight/landing/restart,
  authenticated packet validation and an actual loopback watchdog test.
  The five original UPBGE-launcher-only tests are outside this UE repository.
- Native automation `Arrietty.Coordinates.Attitude` passes. Tests independently
  establish nose-up pitch and inside-wing-down bank in UE transforms.
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
- No hardware services were started during this work. The user's existing
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

## Evening hardware acceptance

1. Start SteamVR, close the UPBGE simulator, and run `./start-ue.ps1` from this
   repository. The user's ignored `settings.local.json` is already configured.
2. In setup, select/apply the desired Tuvalu local date/time, then press P.
   Confirm the scene appears in the HMD and the three-part panel is readable.
3. Face the physical bicycle direction with the handle centered and press
   Button 1. Confirm alignment, straight-ahead pedalling, elapsed time from
   zero, and correct left/right steering. HR may remain disconnected.
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

Pending outcomes should be recorded here after that session. Do not label
hardware or HMD acceptance PASS based only on the offline results above.
