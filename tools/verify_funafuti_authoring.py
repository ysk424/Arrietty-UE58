"""Reload and inspect saved authoring assets; optionally capture an Editor view.

Does not export a world. Screenshot mode uses a temporary camera and closes
the Editor after capture; it never starts PIE. ARRIETTY_INITIALIZE_EDITOR_VIEW
explicitly saves only the initial viewport before adding that temporary camera.
"""
import json
import os
from pathlib import Path
import struct
import time

import unreal as u
import arrietty_exporter
import arrietty_world_core as core

project = Path(u.Paths.get_project_file_path()).resolve()
assert project.stem == 'Funafuti'
receipt = json.loads((project.parent/'ArriettyBaseline.json').read_text(encoding='utf-8'))
source = Path(os.environ['ARRIETTY_AUTHORING_INPUT'])
data = (source/'world.bin').read_bytes()
assert core.digest(source/'world.bin') == receipt['geometry_sha256']
assert u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(receipt['map'])
actors = u.get_editor_subsystem(u.EditorActorSubsystem)
all_actors = actors.get_all_level_actors()
meshes = [a for a in all_actors if isinstance(a, u.StaticMeshActor)]
assert len(meshes) == len(receipt['sections'])
by_asset = {a.static_mesh_component.static_mesh.get_path_name().split('.')[0]: a for a in meshes}
offset, total, max_error = 12, 0, 0.
for record in receipt['sections']:
    count, flags, r, g, b, rough = struct.unpack_from('<II4f', data, offset)
    offset += 24
    values = list(struct.iter_unpack('<8f', memoryview(data)[offset:offset+count*32]))
    offset += count*32
    actor = by_asset[record['asset']]
    mesh = actor.static_mesh_component.static_mesh
    triangles = mesh.get_num_triangles(0)
    assert triangles == record['triangles'], (record['asset'], triangles, record['triangles'])
    assert actor.static_mesh_component.get_material(0) is not None
    box, position = mesh.get_bounding_box(), actor.get_actor_location()
    for axis, component in enumerate(('x', 'y', 'z')):
        for bound, compare in ((box.min, min), (box.max, max)):
            error = abs(getattr(bound, component)+getattr(position, component)-compare(v[axis] for v in values))
            max_error = max(max_error, error)
    total += triangles
assert total == receipt['triangles'] and offset == len(data)
assert max_error < .2, max_error
assert len([a for a in all_actors if isinstance(a, u.PlayerStart)]) == 1
assert not any('/Script/ArriettyUE' in a.get_class().get_path_name() for a in all_actors)
engine = Path(u.Paths.engine_dir()).resolve().parent
profile = core.read_json(project.parent/'Plugins/ArriettyExporter/Resources/runtime-profile.json')
files, mounts = arrietty_exporter._collect(project, engine, receipt['map'], profile)
assert not mounts, mounts
print(f'ARRIETTY_FUNAFUTI_RELOAD_OK meshes={len(meshes)} triangles={total} max_bounds_error_cm={max_error} runtime_plugin_mounts={len(mounts)}')

if os.environ.get('ARRIETTY_AUTHORING_SCREENSHOT'):
    view_position, view_rotation = u.Vector(120000, -120000, 130000), u.Rotator(pitch=-37.45, yaw=135, roll=0)
    if os.environ.get('ARRIETTY_INITIALIZE_EDITOR_VIEW'):
        assert u.get_editor_subsystem(u.UnrealEditorSubsystem).set_level_viewport_camera_info(view_position, view_rotation) is None
        assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    if os.environ.get('ARRIETTY_AUTHORING_VIEW') == 'runway':
        view_position = u.Vector(0, 0, 160)
        view_rotation = u.Rotator(pitch=-5, yaw=(180-receipt['initial_heading_degrees']) % 360, roll=0)
    camera = actors.spawn_actor_from_class(u.CameraActor, view_position)
    camera.set_actor_rotation(view_rotation, False)
    camera.camera_component.set_field_of_view(70.)
    screenshot = str(Path(os.environ['ARRIETTY_AUTHORING_SCREENSHOT']).resolve())
    task = u.AutomationLibrary.take_high_res_screenshot(1600, 1000, screenshot, camera=camera, delay=4.)
    assert task.is_valid_task()
    began = time.monotonic()

    def finish(delta):
        if task.is_task_done() or time.monotonic()-began > 90:
            u.unregister_slate_post_tick_callback(handle)
            print('ARRIETTY_AUTHORING_SCREENSHOT_DONE '+str(task.is_task_done()))
            u.SystemLibrary.quit_editor()

    handle = u.register_slate_post_tick_callback(finish)
