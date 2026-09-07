"""Local world manifest contract; also shipped inside the Editor exporter.

No Unreal, device, network, or editor imports. Export is an explicit user action.
Paths in a manifest are references, never permission to overwrite those paths.
"""
from __future__ import annotations

import configparser
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid

FORMAT = 'arrietty.world'
VERSION = 1
RUNTIME_ABI = 'ue58-worlds-1'
MANIFEST_NAME = 'world.json'
# UE 5.8 NameTypes.h: INVALID_LONGPACKAGE_CHARACTERS. Unicode is valid.
INVALID_PACKAGE_CHARACTERS = set('\\:*?"<>|\' ,.&!~\n\r\t@#\0')
REEXPORT = 'Save the source project and export it again with Arrietty Exporter.'
SUPPORTED_MODULES = {
    'CoreUObject', 'Engine', 'PhysicsCore', 'InputCore', 'UMG', 'SlateCore',
    'Landscape', 'Foliage', 'NavigationSystem', 'AIModule', 'GameplayTags',
    'MovieScene', 'MovieSceneTracks', 'LevelSequence', 'CinematicCamera',
    'Niagara', 'NiagaraCore', 'NiagaraShader', 'AudioExtensions',
    'SignalProcessing', 'AudioMixer', 'DeveloperSettings',
}


class WorldError(ValueError):
    pass


def documents_dir():
    if os.name == 'nt':
        # CSIDL_PERSONAL resolves redirected/OneDrive Documents as well.
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) != 0:
            raise WorldError('Cannot locate Windows Documents.')
        return Path(buffer.value)
    return Path.home() / 'Documents'


def output_dir(project):
    return documents_dir() / 'Arrietty Projects' / Path(project).resolve().parent.name


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise WorldError(f'Cannot read {path}: {exc}') from exc


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def contained(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise WorldError('Invalid relative artifact path.')
    result = (root / relative).resolve()
    if Path(relative).is_absolute() or '..' in Path(relative).parts or not result.is_relative_to(root) or result == root:
        raise WorldError('Artifact path leaves the world directory.')
    return result


def fingerprint(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise WorldError(f'Missing source: {path}. {REEXPORT}')
    return {'path': str(path), 'size': path.stat().st_size, 'sha256': digest(path)}


def source_inventory(project):
    """Saved inputs only, not Saved/Intermediate/DDC or arbitrary plugin binaries.

Includes additions/removals and World Partition external actor packages. This
is deliberately strict: any saved Content/Config/Source change requires export.
It does not duplicate the files or inspect editor memory.
"""
    project = Path(project).resolve()
    paths = {project}
    for folder in ('Content', 'Config', 'Source'):
        root = project.parent / folder
        if root.exists():
            paths.update(p for p in root.rglob('*') if p.is_file())
    plugins = project.parent / 'Plugins'
    if plugins.exists():
        for descriptor in plugins.rglob('*.uplugin'):
            if descriptor.stem == 'ArriettyExporter':
                continue
            paths.add(descriptor)
            for folder in ('Content', 'Config', 'Source'):
                root = descriptor.parent / folder
                if root.exists():
                    paths.update(p for p in root.rglob('*') if p.is_file())
    paths = {p for p in paths if '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    return [fingerprint(p) for p in sorted(paths, key=lambda p: str(p).casefold())]


def engine_identity(engine):
    data = read_json(Path(engine) / 'Engine/Build/Build.version')
    return {key: data[key] for key in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')}


def runtime_profile(repo, engine):
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.optionxform = str
    ini.read(Path(repo) / 'unreal/ArriettyUE/Config/DefaultEngine.ini', encoding='utf-8-sig')
    sections = {s: dict(ini[s]) for s in ('/Script/Engine.RendererSettings', '/Script/WindowsTargetPlatform.WindowsTargetSettings')}
    return {'abi': RUNTIME_ABI, 'engine': engine_identity(engine), 'platform': 'Windows',
            'container': 'pak', 'settings': sections, 'script_modules': sorted(SUPPORTED_MODULES)}


def validate_map_package(name):
    if (not isinstance(name, str) or not name.startswith('/Game/')
            or any(not part for part in name.split('/')[1:])
            or any(character in INVALID_PACKAGE_CHARACTERS for character in name)):
        raise WorldError('Invalid world map package name.')
    if name in ('/Game/Maps/Funafuti', '/Game/Maps/ArriettyEntry'):
        raise WorldError('World map conflicts with reserved Arrietty content.')


def validate(manifest, profile=None):
    manifest = Path(manifest).resolve()
    if manifest.name != MANIFEST_NAME:
        raise WorldError(f'Select the fixed manifest name {MANIFEST_NAME}.')
    data = read_json(manifest)
    if not isinstance(data, dict) or data.get('format') != FORMAT or data.get('version') != VERSION:
        raise WorldError('Unsupported world manifest format/version.')
    for field in ('name', 'world_id'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise WorldError(f'Missing or invalid world {field}.')
    validate_map_package(data.get('map'))
    if not isinstance(data.get('profile'), dict) or data['profile'].get('abi') != RUNTIME_ABI:
        raise WorldError('World requires a different Arrietty runtime. ' + REEXPORT)
    if profile is not None and data.get('profile') != profile:
        raise WorldError('UE version or runtime export settings differ. ' + REEXPORT)
    if not isinstance(data.get('source_project'), str):
        raise WorldError('Source project must be an absolute .uproject path.')
    project = Path(data['source_project'])
    if not project.is_absolute() or project.suffix != '.uproject':
        raise WorldError('Source project must be an absolute .uproject path.')
    recorded = data.get('source_files')
    if not isinstance(recorded, list) or not recorded:
        raise WorldError('Missing source fingerprints.')
    actual = source_inventory(project)
    if actual != recorded:
        raise WorldError('Saved source data changed, was added or removed. ' + REEXPORT)
    files = data.get('files')
    mounts = data.get('mounts', [])
    if not isinstance(mounts, list) or any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', x) or x in ('Game', 'Engine', 'ArriettyUE') for x in mounts):
        raise WorldError('Invalid content mount names.')
    if not isinstance(files, list) or len(files) != 1:
        raise WorldError('This world format requires one cooked .pak.')
    for entry in files:
        if not isinstance(entry, dict):
            raise WorldError('Invalid artifact entry.')
        path = contained(manifest.parent, entry.get('path'))
        if path.suffix != '.pak' or not path.is_file():
            raise WorldError('Missing cooked world package. ' + REEXPORT)
        if path.stat().st_size != entry.get('size') or digest(path) != entry.get('sha256'):
            raise WorldError('Converted world data is damaged or differs. ' + REEXPORT)
    start = data.get('start', {})
    if not isinstance(start, dict):
        raise WorldError('Invalid start information.')
    location = start.get('location_cm')
    if not isinstance(location, list) or len(location) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in location):
        raise WorldError('Invalid start location.')
    yaw = start.get('yaw_degrees')
    if type(yaw) not in (int, float) or not math.isfinite(yaw):
        raise WorldError('Invalid start yaw.')
    return data


def world_session(manifest, data):
    """Bridge metadata for native worlds; authored lighting needs no Secret-World."""
    return {'output_name': data['name'], 'world_id': data['world_id'],
            'world_manifest': str(Path(manifest).resolve()), 'map': data['map'],
            'world_pak': str(contained(Path(manifest).parent, data['files'][0]['path'])),
            'content_mounts': data.get('mounts', []),
            'initial_heading_degrees': (180 - data['start']['yaw_degrees']) % 360,
            'origin_latitude': 0.0, 'origin_longitude': 0.0,
            'spawn_location_cm': data['start']['location_cm'],
            'solar_mode': 'authored', 'local_time': '', 'sun_azimuth': 0.0, 'sun_elevation': 0.0}
