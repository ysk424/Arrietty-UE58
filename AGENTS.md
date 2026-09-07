# Project memory

Before changing this project, read [docs/HANDOFF.md](docs/HANDOFF.md) for the
agreed behavior and retained project decisions. [docs/VALIDATION.md](docs/VALIDATION.md)
records the operational baseline, evidence and remaining device checks.

- This is the separate public **Arrietty-UE58** repository requested by the user.
  Keep its changes and pushes separate from `../Arrietty-UP` and `../Secret-World`.
- Button 1 at ride start latches the current HMD view's horizontal forward.
  Preserve that view when calibrating; the handle steers afterward. Do not
  replace this with a fixed runway heading, fixed yaw correction or gaze steering.
- R selects a new forward. Subsequent Button 1 retains the approximately 2m recovery.
- Keep generated scenery, binaries, logs, session tokens and personal device
  settings outside Git. Check staged public content with `tools/check_public_tree.py`.
- Record user-reported operation, automated tests and individual hardware
  measurements separately. Update the handoff when a lasting decision changes.
