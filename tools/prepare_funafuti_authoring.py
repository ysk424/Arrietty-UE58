"""Create a separate editable Funafuti project from the current verified terrain.

Refuses an existing destination. The fitness checkout is read only. No export,
game, device connection, or CinderLink model request is started here.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools'))
from arrietty_ue.worlds import atomic_json, digest, runtime_profile
from install_world_exporter import install
from verify_ue_world import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Current Content/SecretWorld directory')
    parser.add_argument('--project', type=Path, default=Path.home()/'Documents/Unreal Projects/Funafuti/Funafuti.uproject')
    parser.add_argument('--engine', type=Path, default=Path('C:/Program Files/Epic Games/UE_5.8'))
    args = parser.parse_args()
    project, source, engine = args.project.resolve(), args.source.resolve(), args.engine.resolve()
    if project.stem != 'Funafuti' or project.suffix != '.uproject' or project.parent.exists():
        raise ValueError('Select a new Funafuti/Funafuti.uproject destination; existing projects are never overwritten.')
    verify(source)
    project.parent.mkdir(parents=True)
    atomic_json(project, {'FileVersion': 3, 'EngineAssociation': '5.8',
                         'Category': 'World Authoring', 'Description': 'Editable Funafuti for Arrietty',
                         'Plugins': [{'Name': name, 'Enabled': True, 'TargetAllowList': ['Editor']}
                                     for name in ('GeometryScripting', 'ModelingToolsEditorMode')]
                                    + [{'Name': 'CinderLink', 'Enabled': True, 'TargetAllowList': ['Editor'],
                                        'SupportedTargetPlatforms': ['Win64']}]})
    profile = runtime_profile(ROOT, engine)
    config = project.parent/'Config'
    config.mkdir()
    settings = '\n'.join('['+section+']\n'+'\n'.join(key+'='+value for key, value in values.items())
                         for section, values in profile['settings'].items())
    settings += ('\n[/Script/EngineSettings.GameMapsSettings]\n'
                 'EditorStartupMap=/Game/Worlds/Funafuti/Maps/Funafuti\n'
                 'GameDefaultMap=/Game/Worlds/Funafuti/Maps/Funafuti\n'
                 '\n[/Script/Engine.Engine]\nNearClipPlane=5.0\n')
    (config/'DefaultEngine.ini').write_text(settings, encoding='utf-8')
    (config/'DefaultGame.ini').write_text(
        '[/Script/EngineSettings.GeneralProjectSettings]\nProjectName=Funafuti\n', encoding='utf-8')
    snapshot = ROOT/'build/funafuti-authoring-input'
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in ('world.json', 'world.bin', 'reef.bgra', 'reef.tga'):
        shutil.copy2(source/name, snapshot/name)
        if digest(source/name) != digest(snapshot/name):
            raise ValueError('Current terrain changed while taking the conversion snapshot.')
    source_art = project.parent/'SourceArt'
    source_art.mkdir()
    shutil.copy2(snapshot/'reef.tga', source_art/'reef.tga')
    install(project, engine)
    environment = os.environ.copy()
    environment['ARRIETTY_AUTHORING_INPUT'] = str(snapshot)
    log = ROOT/'logs/funafuti-authoring.log'
    log.parent.mkdir(exist_ok=True)
    with log.with_suffix('.console.log').open('w', encoding='utf-8') as output:
        subprocess.run([str(engine/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'), str(project),
                        '-run=pythonscript', '-script='+str(ROOT/'tools/build_funafuti_authoring.py'),
                        '-unattended', '-nop4', '-nosplash', '-nosound', '-nohmd', '-NullRHI',
                        '-abslog='+str(log)], env=environment, stdout=output, stderr=subprocess.STDOUT,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
    if 'ARRIETTY_FUNAFUTI_AUTHORING_READY' not in log.read_text(encoding='utf-8', errors='replace'):
        raise RuntimeError('Authoring conversion did not finish. See '+str(log))
    print('Editable project ready: '+str(project))


if __name__ == '__main__':
    main()
