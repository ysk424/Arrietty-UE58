#!/usr/bin/env python3
"""Install bundled wheels into an isolated, generated runtime directory."""

from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
WHEELS = ROOT / "wheels"
RUNTIME = ROOT / ".runtime"
REQUIRED_WHEELS = (
    "bleak-3.0.2-py3-none-any.whl",
    "openvr-2.12.1401-py3-none-any.whl",
    "typing_extensions-4.16.0-py3-none-any.whl",
    "winrt_runtime-3.2.1-cp313-cp313-win_amd64.whl",
    "winrt_windows_devices_bluetooth-3.2.1-cp313-cp313-win_amd64.whl",
    "winrt_windows_devices_bluetooth_advertisement-3.2.1-cp313-cp313-win_amd64.whl",
    "winrt_windows_devices_bluetooth_genericattributeprofile-3.2.1-cp313-cp313-win_amd64.whl",
    "winrt_windows_devices_enumeration-3.2.1-cp313-cp313-win_amd64.whl",
    "winrt_windows_devices_radios-3.2.1-cp313-cp313-win_amd64.whl",
    "winrt_windows_foundation-3.2.1-cp313-cp313-win_amd64.whl",
    "winrt_windows_foundation_collections-3.2.1-cp313-cp313-win_amd64.whl",
    "winrt_windows_storage_streams-3.2.1-cp313-cp313-win_amd64.whl",
)


def wheel_set_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def safe_extract(wheel: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination_resolved):
                raise RuntimeError(f"unsafe wheel member: {member.filename}")
        archive.extractall(destination)


def main() -> int:
    paths = [WHEELS / name for name in REQUIRED_WHEELS]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing bundled wheels: " + ", ".join(missing))

    digest = wheel_set_digest(paths)
    destination = RUNTIME / "site-packages" / digest
    if not destination.is_dir():
        destination.mkdir(parents=True)
        for wheel in paths:
            safe_extract(wheel, destination)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "current.txt").write_text(digest + "\n", encoding="ascii")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
