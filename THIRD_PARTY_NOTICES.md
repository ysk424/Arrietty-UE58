# Third-party notices

Arrietty-UE58 redistributes the following Python wheels for Windows BLE and
SteamVR controller-pose support. Each wheel retains its package metadata,
license file, and original license terms.

- openvr 2.12.1401 — BSD License — https://github.com/cmbruns/pyopenvr
- Bleak 3.0.2 — MIT License — https://github.com/hbldh/bleak
- PyWinRT runtime and Windows projections 3.2.1 — MIT License — https://github.com/pywinrt/pywinrt
- typing_extensions 4.16.0 — PSF-2.0 License — https://github.com/python/typing_extensions

These components are independent libraries and are not relicensed under the
Arrietty-UE58 MIT License.

The `arrietty_up` package and its regression tests originate from
[Arrietty-UP](https://github.com/ysk424/Arrietty-UP), commit
`b1a82dfc3624ec3dbb71bec088289b6fcec1a03c`, under the MIT License,
copyright (c) 2026 ysk424. Its license is retained as this repository's LICENSE.

Unreal Engine and its engine content are installed separately and are not
redistributed in this repository. The generated materials reference local
engine assets and remain excluded from Git.

Secret World source files and exported production geometry/textures are also
excluded from Git. When prepared locally, the Funafuti world includes
OpenStreetMap-derived geography (© OpenStreetMap contributors, ODbL 1.0,
https://www.openstreetmap.org/copyright) and an Allen Coral Atlas Reef Extent
derivative (CC BY 4.0). The export retains these attributions and source hashes
in `Content/SecretWorld/world.json`; setup instruments display both credits.
The exporter accepts only persistent non-Google meshes. Secret World's own
code and source-data terms continue to apply separately.
