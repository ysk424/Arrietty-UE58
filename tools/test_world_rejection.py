"""Verify real launcher rejection before any session/game/device starts.

Mutates only disposable fixture inputs and restores their exact bytes.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arrietty_ue.worlds import read_json, contained, validate


def main():
    manifest = ROOT/'build/world-fixtures/exports/City/world.json'
    data = validate(manifest)
    source = Path(data['source_project']).parent/'Content/Worlds/City/Map.umap'
    package = contained(manifest.parent, data['files'][0]['path'])
    sessions = ROOT/'.runtime/world-sessions'
    for path, message in ((source, 'Saved source data changed'), (package, 'Converted world data is damaged')):
        assert path.resolve().is_relative_to((ROOT/'build/world-fixtures').resolve())
        before = set(sessions.iterdir()) if sessions.exists() else set()
        with path.open('r+b') as stream:
            first = stream.read(1)
            assert first
            try:
                stream.seek(0)
                stream.write(bytes([first[0] ^ 255]))
                stream.flush()
                result = subprocess.run([sys.executable, str(ROOT/'tools/start_world.py'), '--world', str(manifest),
                                         '--offline', '--smoke', '--port', '29859'],
                                        capture_output=True, text=True, errors='replace', timeout=30)
                assert result.returncode != 0 and message in result.stderr, result.stdout+result.stderr
                assert (set(sessions.iterdir()) if sessions.exists() else set()) == before
            finally:
                stream.seek(0)
                stream.write(first)
                stream.flush()
        validate(manifest)
    print('ARRIETTY_WORLD_REJECTION_OK source_changed=1 corrupt_output=1 sessions_started=0')


if __name__ == '__main__':
    main()
