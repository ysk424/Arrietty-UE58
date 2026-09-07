"""Explicit Editor export. Staging/Cook never writes into the source project."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shutil
import subprocess
import uuid

import unreal as u
import arrietty_world_core as core


def _package_files(root, package):
    relative = package.split('/', 2)[2]
    stem = root / relative
    files = [Path(str(stem) + suffix) for suffix in ('.umap', '.uasset', '.uexp', '.ubulk', '.uptnl')]
    return [path for path in files if path.is_file()]


def _mounts(project, engine):
    result = {'Game': project.parent/'Content', 'Engine': engine/'Engine/Content'}
    for root in (engine/'Engine/Plugins', project.parent/'Plugins'):
        if root.exists():
            for descriptor in root.rglob('*.uplugin'):
                content = descriptor.parent/'Content'
                if content.exists():
                    result[descriptor.stem] = content
    return result


def _collect(project, engine, map_name, profile):
    registry = u.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(True)
    # Cook removes Editor-only import metadata; it is not runtime code.
    options = u.AssetRegistryDependencyOptions(
        include_hard_package_references=True, include_soft_package_references=True,
        include_game_package_references=True, include_editor_only_package_references=False,
        include_searchable_names=False, include_soft_management_references=False,
        include_hard_management_references=False)
    mounts = _mounts(project, engine)
    pending = [map_name]
    # WP external packages are saved outside the .umap; include the selected
    # map's external actors/objects and their dependencies explicitly.
    for category in ('__ExternalActors__', '__ExternalObjects__'):
        external = project.parent/'Content'/category/map_name.removeprefix('/Game/')
        if external.exists():
            pending.extend('/Game/'+p.relative_to(project.parent/'Content').with_suffix('').as_posix()
                           for p in external.rglob('*.uasset'))
    visited, files, plugin_mounts = set(), {}, set()
    while pending:
        package = str(pending.pop())
        if package in visited:
            continue
        visited.add(package)
        if package.startswith('/Script/'):
            if package.rsplit('/', 1)[1] not in profile['script_modules']:
                raise core.WorldError(f'Unsupported runtime code dependency: {package}. Bake/remove that dependency before export.')
            continue
        if not package.startswith('/') or package.count('/') < 2:
            continue
        mount = package.split('/')[1]
        if mount not in mounts:
            raise core.WorldError(f'Cannot resolve required asset mount: {package}')
        # Engine data is available to the staging cooker, which includes any
        # additional engine assets needed by the world in the output package.
        found = _package_files(mounts[mount], package)
        if not found:
            raise core.WorldError(f'Missing saved dependency: {package}. Save all assets before export.')
        if mount != 'Engine' and not (mounts[mount].is_relative_to(engine) and mount == 'Niagara'):
            for source in found:
                relative = source.relative_to(mounts[mount])
                destination = (Path('Content')/relative if mount == 'Game'
                               else Path('Plugins')/mount/'Content'/relative)
                reserved = {'Maps/Funafuti.umap', 'Maps/ArriettyEntry.umap', 'Materials/M_Instruments.uasset',
                            'Materials/M_World.uasset', 'Materials/M_Water.uasset', 'Materials/T_Reef.uasset'}
                if mount == 'Game' and relative.as_posix() in reserved:
                    raise core.WorldError(f'Asset uses an Arrietty-reserved path: {package}. Use a world-specific folder.')
                files[str(source)] = destination
            if mount not in ('Game', 'Engine'):
                plugin_mounts.add(mount)
        pending.extend(str(x) for x in registry.get_dependencies(package, options))
    return files, plugin_mounts


def _run(arguments, log):
    with log.open('w', encoding='utf-8') as stream:
        process = subprocess.run([str(x) for x in arguments], stdout=stream, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if process.returncode:
        raise core.WorldError(f'World preparation failed ({process.returncode}). See {log}')


def export_current_world(destination=None):
    if u.EditorLoadingAndSavingUtils.get_dirty_map_packages() or u.EditorLoadingAndSavingUtils.get_dirty_content_packages():
        raise core.WorldError('Unsaved changes. Save all changes, then export again.')
    project = Path(u.Paths.get_project_file_path()).resolve()
    engine = Path(u.Paths.engine_dir()).resolve().parent
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    map_name = world.get_path_name().split('.')[0]
    if not map_name.startswith('/Game/'):
        raise core.WorldError('Open a saved map under this project\'s Content folder.')
    core.validate_map_package(map_name)
    profile = core.read_json(Path(__file__).resolve().parents[2]/'Resources/runtime-profile.json')
    if core.engine_identity(engine) != profile['engine']:
        raise core.WorldError('This exporter targets a different UE build. Install the matching Arrietty Exporter.')
    destination = Path(destination or core.output_dir(project)).resolve()
    if destination.is_relative_to(project.parent) or destination.is_relative_to(engine):
        raise core.WorldError('Export destination must be outside the source project and Engine.')
    destination.mkdir(parents=True, exist_ok=True)
    existing = destination/core.MANIFEST_NAME
    if existing.exists() and Path(core.read_json(existing).get('source_project', '')).resolve() != project:
        raise core.WorldError('This output folder belongs to a different source project.')
    source_files = core.source_inventory(project)
    files, plugin_mounts = _collect(project, engine, map_name, profile)
    starts = [a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors() if isinstance(a, u.PlayerStart)]
    starts.sort(key=lambda a: a.get_path_name())
    if len(starts) > 1:
        tagged = [a for a in starts if 'ArriettyStart' in [str(t) for t in a.tags]]
        if len(tagged) != 1:
            raise core.WorldError('Multiple PlayerStarts: tag exactly one ArriettyStart.')
        starts = tagged
    location = starts[0].get_actor_location() if starts else u.Vector(0, 0, 0)
    yaw = starts[0].get_actor_rotation().yaw if starts else 0.0
    export_id = uuid.uuid4().hex
    work = destination/('.work-'+export_id)
    staging = work/'ArriettyUE'
    staging.mkdir(parents=True)
    # Only needed saved packages are temporary inputs. Never copy the entire
    # authoring project or its executable/editor plugins to the simulator.
    for source, relative in files.items():
        target = staging/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    plugins = [{'Name': 'Niagara', 'Enabled': True}]
    for mount in sorted(plugin_mounts):
        descriptor = staging/'Plugins'/mount/(mount+'.uplugin')
        core.atomic_json(descriptor, {'FileVersion': 3, 'Version': 1, 'CanContainContent': True})
        plugins.append({'Name': mount, 'Enabled': True})
    stage_project = staging/'ArriettyUE.uproject'
    core.atomic_json(stage_project, {'FileVersion': 3, 'EngineAssociation': '5.8',
                                    'DisableEnginePluginsByDefault': True, 'Plugins': plugins})
    config = staging/'Config'
    config.mkdir()
    engine_ini = '\n'.join('['+s+']\n'+'\n'.join(k+'='+v for k, v in values.items())
                           for s, values in profile['settings'].items())
    engine_ini += '\n[/Script/EngineSettings.GameMapsSettings]\nGameDefaultMap='+map_name+'\n'
    (config/'DefaultEngine.ini').write_text(engine_ini, encoding='utf-8')
    (config/'DefaultGame.ini').write_text(
        '[/Script/UnrealEd.ProjectPackagingSettings]\nbUseIoStore=False\nbShareMaterialShaderCode=False\n'
        'bSharedMaterialNativeLibraries=False\nbSkipEditorContent=True\n', encoding='utf-8')
    cook_log = destination/'export-cook.log'
    _run([engine/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe', stage_project,
          '-run=Cook', '-TargetPlatform=Windows', '-Map='+map_name,
          '-OutputDir='+str(work/'Cooked/[Platform]'), '-unattended', '-nop4', '-nosplash', '-NoSound',
          '-NoDefaultMaps', '-SKIPEDITORCONTENT', '-UTF8Output'], cook_log)
    cooked = work/'Cooked/Windows'
    packed = []
    for path in sorted(cooked.rglob('*')):
        if path.is_file() and path.suffix in ('.umap', '.uasset', '.uexp', '.ubulk', '.uptnl'):
            relative = path.relative_to(cooked).as_posix()
            if not relative.startswith(('ArriettyUE/', 'Engine/')):
                raise core.WorldError(f'Unexpected cook output layout: {relative}')
            packed.append('"'+str(path)+'" "../../../'+relative+'"')
    if not any('/Content/'+map_name.removeprefix('/Game/')+'.umap"' in line for line in packed):
        raise core.WorldError(f'Cook did not produce the selected map. See {cook_log}')
    response = work/'pak-files.txt'
    response.write_text('\n'.join(packed), encoding='utf-8')
    package = destination/('world-'+export_id+'.pak')
    _run([engine/'Engine/Binaries/Win64/UnrealPak.exe', package, '-Create='+str(response), '-compress'], destination/'export-pak.log')
    if core.source_inventory(project) != source_files:
        raise core.WorldError('Source changed during export. ' + core.REEXPORT)
    manifest = {'format': core.FORMAT, 'version': core.VERSION, 'name': project.parent.name,
                'world_id': export_id, 'exported_at': datetime.now(timezone.utc).isoformat(),
                'source_project': str(project), 'source_files': source_files, 'map': map_name,
                'profile': profile, 'mounts': sorted(plugin_mounts),
                'start': {'location_cm': [location.x, location.y, location.z], 'yaw_degrees': yaw},
                'files': [{'path': package.name, 'size': package.stat().st_size, 'sha256': core.digest(package)}]}
    # Publish only after a complete successful export. An old manifest remains
    # invalid after a source edit; there is no silent fallback or re-export.
    core.atomic_json(existing, manifest)
    # Verify the fully resolved temporary root before recursive removal.
    resolved_work = work.resolve()
    if resolved_work.parent == destination and resolved_work.name == '.work-'+export_id:
        shutil.rmtree(resolved_work)
    u.log('ARRIETTY_WORLD_EXPORTED '+str(existing))
    return existing


def export_with_dialog():
    try:
        with u.ScopedSlowTask(1, 'Exporting saved world for Arrietty') as task:
            task.make_dialog(False)
            path = export_current_world()
        u.EditorDialog.show_message('Arrietty Exporter', 'Export complete:\n'+str(path), u.AppMsgType.OK)
    except Exception as error:
        u.log_error(str(error))
        u.EditorDialog.show_message('Arrietty Exporter', str(error), u.AppMsgType.OK)
