# UE 5.8 port contract

The accepted upstream snapshot is Arrietty-UP commit
`b1a82dfc3624ec3dbb71bec088289b6fcec1a03c` (2026-09-06 bank-display correction).
`arrietty_up` retains its tested model, control/protocol parsers and workers.
UPBGE-specific presentation functions in that package are not invoked by UE.
Only device-ID configuration and automatic steering selection differ from
the copied package. No original UPBGE source or flight log was modified.

`arrietty_ue.bridge.Simulation` drives that state machine. BLE, serial, OpenVR,
fan and voice methods never run on the UE rendering thread. In Offline mode
all five are replaced before initialization by implementations without I/O.
OpenXR presents the HMD through UE; the background OpenVR client reads the
stem-mounted VIVE controller, preserving the accepted mounting calibration.

## Frames and lifetime

UE sends authenticated JSON to exclusive loopback UDP port 19858; the reply
goes only to the first authenticated client address. Each datagram includes
protocol version 1, an increasing sequence and a per-launch random token.
Malformed, reordered and other-client packets are discarded. Token/config
files live in ignored `.runtime/ue`, and tokens are not printed.

The bridge waits without opening hardware until `play=true`. Button 1 creates
an alignment request. UE rotates the tracking origin by inverse current HMD
yaw and removes the initial horizontal room offset, retaining floor height.
Alignment now runs in `CalcCamera`, where UE consumes the HMD pose. It is
acknowledged only after `UCameraComponent::GetCameraView` produces a forward
direction within one degree of the bicycle's local forward plane. This
validates the final camera transform, including its parent, rather than
accepting tracking-space pose validity as proof of visual alignment. Invalid
or unavailable cameras leave the request pending and retry on the next view.
The bridge allows movement only after the matching alignment ID, current HMD
validity and VIVE tracking are present. The initial aircraft heading remains
the Secret World runway heading. Subsequent Button 1 retains the 2m recovery.
R requests fresh HMD/handle alignment with an increasing `recenter_id`, without
changing the position, course direction or ride start time. Motion is suspended
until the new alignment is acknowledged. Earlier replies cannot acknowledge a
new R request. Head turning after alignment remains independent of steering.
Final view, vehicle and raw HMD yaw are logged once per second for diagnosis;
their difference during normal head turning is expected, not an error.

Esc sends `play=false`; window close sends three quit datagrams. One second
without an authenticated frame stops airflow/PTT, requests grade zero and
joins device workers. After a previously connected UE disappears for 30s,
the service exits. Initial UE shader compilation has no startup timeout that
could leave an otherwise valid simulator without a bridge. The launcher owns
both process lifetimes.

## Coordinates

| Value | Mapping |
|---|---|
| Blender/runtime ENU metres | UE `(north*100, east*100, altitude*100)` |
| Internal heading, zero toward south | UE yaw / geographic bearing = `(180-heading)%360` |
| Nose-up pitch | UE positive pitch |
| Internal positive bank (left turn) | UE negative roll; left wing moves downward |
| Logged roll | Right wing down positive, matching UE roll |

The native `Arrietty.Coordinates.Attitude` test transforms real forward/left/
right basis vectors. It catches sign errors that comparing two copies of one
quaternion formula cannot detect. Vehicle attitude is level on the ground,
while the PFD still shows commanded flight surface response before takeoff.
Flight calculations preserve the accepted runway-relative zero-altitude
model; this port does not introduce arbitrary elevated-terrain flight physics.
`Arrietty.Coordinates.HmdAlignment` supplies simulated poses to UE's real
`FDefaultXRCamera`, exercising the Pawn/Tracking/Camera hierarchy and final
view for multiple room headings and the runway bearing. It checks forward
translation, eye height, free head turning and rejection of a valid raw pose
when the rendered camera is unavailable or still backwards. It opens no XR
session or hardware service.

## Scenery and rendering

`tools/export_secret_world_ue.py` selects the highest valid 17-digit Runtime
build number, verifies the corresponding blend digest, and opens it in a
background process. It exports only `Secret World` meshes explicitly marked
`persistent_non_google`, rejects unbaked modifiers, and requires exactly five
ride surfaces. The source blend is hashed again and is never saved.

The world stream is little-endian `ARRW0001`, a uint32 section count, then each
section's uint32 vertex count, uint32 flags (bit0 collision, bit1 water), four
float32 material values (RGB and roughness), and vertices as eight float32
values (XYZ, normal XYZ, UV). Triangles are independent triples in UE's
clockwise winding after the ENU axis exchange. Draw batches use material and
1km spatial cells. Collision roles and the original reef colour lookup are
retained. `world.json` records build/source/export hashes and attribution.

UE constructs procedural mesh components, native material instances, an
atmosphere and sun. Deferred shading with TAA and instanced stereo supports
the atmosphere; Lumen, virtual shadow maps and motion blur are disabled.
The instrument material compensates for exposure, and a circular PFD
aperture is drawn in Slate. The panel is attached to the bicycle at 1.3m
forward / 1.0m high. HMD readability and stereo comfort require live acceptance.

The local-time editor uses Secret World's own `solar.py`, and sends the result
to the UE directional light. Invalid or unapplied edits cannot start play.
Applied local time is frozen in the session and included in CSV metadata.

Relevant engine references:
[OpenXR](https://dev.epicgames.com/documentation/unreal-engine/developing-for-head-mounted-experiences-with-openxr-in-unreal-engine),
[Sky Atmosphere](https://dev.epicgames.com/documentation/en-us/unreal-engine/sky-atmosphere-component-in-unreal-engine),
[exposure](https://dev.epicgames.com/documentation/en-us/unreal-engine/auto-exposure-in-unreal-engine).

## Public repository boundary

Git contains application code, bundled redistributable Python wheels, tests
and reconstruction scripts. UE binaries, engine assets, generated maps,
production world geometry, `.blend` files, personal device IDs, credentials,
session tokens and logs remain local. `../Secret-World` supplies the world
and solar authoring system; `../Arrietty-UP` is not a runtime dependency.
