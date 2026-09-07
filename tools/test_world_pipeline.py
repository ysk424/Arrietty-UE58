"""Real saved UE projects -> installed exporter -> cooked packages -> runtime.

Only disposable projects under this worktree's ignored build directory; no
devices and no modifications to Documents/Unreal Projects or the fitness tree.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arrietty_ue.worlds import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, default=Path('C:/Program Files/Epic Games/UE_5.8'))
    parser.add_argument('--export-only', action='store_true')
    parser.add_argument('--name', choices=('City', 'Island'), default='City')
    args = parser.parse_args()
    fixtures = ROOT/'build/world-fixtures'
    project = fixtures/args.name/(args.name+'.uproject')
    if not project.exists():
        atomic_json(project, {'FileVersion': 3, 'EngineAssociation': '5.8', 'Plugins': []})
    subprocess.run([sys.executable, str(ROOT/'tools/install_world_exporter.py'), str(project), '--engine', str(args.engine)], check=True)
    output = fixtures/'exports'/args.name
    environment = os.environ.copy()
    environment['ARRIETTY_TEST_EXPORT_DIR'] = str(output)
    log_path = ROOT/'logs'/('world-fixture-'+args.name+'.log')
    full_log = log_path.with_suffix('.full.log')
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open('w', encoding='utf-8') as log:
        subprocess.run([str(args.engine/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'), str(project),
                        '-run=pythonscript', '-script='+str(ROOT/'tools/create_world_fixture.py'),
                        '-unattended', '-nop4', '-nosplash', '-nosound', '-nohmd', '-NullRHI', '-UTF8Output',
                        '-abslog='+str(full_log)],
                       stdout=log, stderr=subprocess.STDOUT, env=environment, check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if 'ARRIETTY_FIXTURE_EXPORT_OK' not in full_log.read_text(encoding='utf-8', errors='replace'):
        raise RuntimeError('Fixture export did not finish; see '+str(log_path))
    if not args.export_only:
        subprocess.run([sys.executable, str(ROOT/'tools/start_world.py'), '--world', str(output/'world.json'),
                        '--offline', '--smoke', '--port', '29859'], check=True)
    print('ARRIETTY_WORLD_PIPELINE_OK '+args.name)


if __name__ == '__main__':
    main()
