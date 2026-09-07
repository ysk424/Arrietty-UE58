"""Record expected runtime files after successful packaging."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arrietty_ue.worlds import atomic_json, digest, runtime_profile


def write_receipt(directory, engine):
    directory = Path(directory).resolve()
    executable = 'ArriettyUE/Binaries/Win64/ArriettyUE.exe'
    if not (directory/executable).is_file():
        raise ValueError('Packaged executable is missing.')
    files = [{'path': p.relative_to(directory).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(directory.rglob('*')) if p.is_file() and p.suffix in ('.exe', '.dll', '.pak')]
    atomic_json(directory/'arrietty-runtime.json', {'profile': runtime_profile(ROOT, engine),
                'executable': executable, 'files': files})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('directory', type=Path)
    p.add_argument('--engine', type=Path, required=True)
    args = p.parse_args()
    write_receipt(args.directory, args.engine)
