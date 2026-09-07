"""Install the Editor extension into an explicitly selected authoring project."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arrietty_ue.worlds import atomic_json, runtime_profile, WorldError


def install(project, engine):
    project = Path(project).resolve()
    if not project.is_file() or project.suffix != '.uproject':
        raise WorldError('Select an existing .uproject.')
    data = json.loads(project.read_text(encoding='utf-8-sig'))
    destination = project.parent / 'Plugins/ArriettyExporter'
    python = destination / 'Content/Python'
    python.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT/'exporter/ArriettyExporter.uplugin', destination/'ArriettyExporter.uplugin')
    for name in ('init_unreal.py', 'arrietty_exporter.py'):
        shutil.copy2(ROOT/'exporter'/name, python/name)
    shutil.copy2(ROOT/'arrietty_ue/worlds.py', python/'arrietty_world_core.py')
    atomic_json(destination/'Resources/runtime-profile.json', runtime_profile(ROOT, engine))
    entries = data.setdefault('Plugins', [])
    entry = next((p for p in entries if p['Name'] == 'ArriettyExporter'), None)
    if entry is None:
        entries.append({'Name': 'ArriettyExporter', 'Enabled': True, 'TargetAllowList': ['Editor']})
    else:
        entry.update(Enabled=True, TargetAllowList=['Editor'])
    backup = project.with_suffix('.uproject.before-arrietty')
    if not backup.exists():
        shutil.copy2(project, backup)
    atomic_json(project, data)
    print('Installed Arrietty Exporter. Open the project, save it, then use Tools > Export saved world to Arrietty.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('project', type=Path)
    p.add_argument('--engine', type=Path, default=Path('C:/Program Files/Epic Games/UE_5.8'))
    args = p.parse_args()
    install(args.project, args.engine)
