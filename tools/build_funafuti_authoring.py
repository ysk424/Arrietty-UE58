"""UE Editor commandlet: bake the verified mesh stream to native editable assets."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct

import unreal as u

PROJECT = Path(u.Paths.get_project_file_path()).resolve()
assert PROJECT.stem == 'Funafuti'
SOURCE = Path(os.environ['ARRIETTY_AUTHORING_INPUT']).resolve()
BASE = '/Game/Worlds/Funafuti'
MAP = BASE+'/Maps/Funafuti'
assert not u.EditorAssetLibrary.does_asset_exist(MAP), 'Never overwrite the authored map.'
meta = json.loads((SOURCE/'world.json').read_text(encoding='utf-8'))
data = (SOURCE/'world.bin').read_bytes()
assert hashlib.sha256(data).hexdigest() == meta['geometry_sha256']
assert data[:8] == b'ARRW0001'
assert struct.unpack_from('<I', data, 8)[0] == len(meta['sections'])
assets = u.AssetToolsHelpers.get_asset_tools()
actors = u.get_editor_subsystem(u.EditorActorSubsystem)
mel = u.MaterialEditingLibrary
world = u.EditorLoadingAndSavingUtils.new_blank_map(False)

texture_path = BASE+'/Materials/T_Reef'
reef = u.load_asset(texture_path) if u.EditorAssetLibrary.does_asset_exist(texture_path) else None
if reef is None:
    task = u.AssetImportTask()
    task.set_editor_property('filename', str(PROJECT.parent/'SourceArt/reef.tga'))
    task.set_editor_property('destination_path', BASE+'/Materials')
    task.set_editor_property('destination_name', 'T_Reef')
    task.set_editor_property('automated', True)
    task.set_editor_property('save', True)
    assets.import_asset_tasks([task])
    reef = u.load_asset(texture_path)
assert reef
reef.set_editor_property('srgb', False)
reef.set_editor_property('address_x', u.TextureAddress.TA_CLAMP)
reef.set_editor_property('address_y', u.TextureAddress.TA_CLAMP)
u.EditorAssetLibrary.save_loaded_asset(reef)


def base_material(water):
    name = 'M_Reef' if water else 'M_Surface'
    path = BASE+'/Materials/'+name
    if u.EditorAssetLibrary.does_asset_exist(path):
        return u.load_asset(path)
    mat = assets.create_asset(name, BASE+'/Materials', u.Material, u.MaterialFactoryNew())
    mat.set_editor_property('two_sided', True)
    if water:
        color = mel.create_material_expression(mat, u.MaterialExpressionTextureSampleParameter2D, -300, 0)
        color.set_editor_property('parameter_name', 'Reef')
        color.set_editor_property('texture', reef)
        color.set_editor_property('sampler_type', u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    else:
        color = mel.create_material_expression(mat, u.MaterialExpressionVectorParameter, -300, 0)
        color.set_editor_property('parameter_name', 'Tint')
    mel.connect_material_property(color, '', u.MaterialProperty.MP_BASE_COLOR)
    rough = mel.create_material_expression(mat, u.MaterialExpressionScalarParameter, -300, 200)
    rough.set_editor_property('parameter_name', 'Roughness')
    mel.connect_material_property(rough, '', u.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(mat)
    u.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


bases = {False: base_material(False), True: base_material(True)}
materials = {}
offset, total, records = 12, 0, []
for index, section in enumerate(meta['sections']):
    count, flags, r, g, b, rough = struct.unpack_from('<II4f', data, offset)
    offset += 24
    assert count == section['vertices'] and count % 3 == 0
    values = list(struct.iter_unpack('<8f', memoryview(data)[offset:offset+count*32]))
    offset += count*32
    # Local mesh pivots make selecting and moving chunks practical in Editor.
    origin = [(min(v[axis] for v in values)+max(v[axis] for v in values))*.5 for axis in range(3)]
    name = f'SM_{index:04d}_'+re.sub(r'[^A-Za-z0-9_]', '_', section['material'])
    path = BASE+'/Meshes/'+name
    material_key = (section['material'], r, g, b, rough, bool(flags & 2))
    if material_key not in materials:
        instance_name = f'MI_{len(materials):03d}_'+re.sub(r'[^A-Za-z0-9_]', '_', section['material'])
        instance_path = BASE+'/Materials/'+instance_name
        instance = (u.load_asset(instance_path) if u.EditorAssetLibrary.does_asset_exist(instance_path)
                    else assets.create_asset(instance_name, BASE+'/Materials', u.MaterialInstanceConstant, u.MaterialInstanceConstantFactoryNew()))
        mel.set_material_instance_parent(instance, bases[bool(flags & 2)])
        mel.set_material_instance_vector_parameter_value(instance, 'Tint', u.LinearColor(r, g, b, 1))
        mel.set_material_instance_scalar_parameter_value(instance, 'Roughness', rough)
        u.EditorAssetLibrary.save_loaded_asset(instance)
        materials[material_key] = instance
    material = materials[material_key]
    if u.EditorAssetLibrary.does_asset_exist(path):
        mesh = u.load_asset(path)
    else:
        dynamic = u.DynamicMesh()
        buffers = u.GeometryScriptSimpleMeshBuffers(
            vertices=[u.Vector(*(v[axis]-origin[axis] for axis in range(3))) for v in values],
            normals=[u.Vector(*v[3:6]) for v in values],
            uv0=[u.Vector2D(*v[6:8]) for v in values],
            triangles=[u.IntVector(i, i+1, i+2) for i in range(0, count, 3)])
        u.GeometryScript_MeshEdits.append_buffers_to_mesh(dynamic, buffers)
        assert dynamic.get_triangle_count() == count//3
        options = u.GeometryScriptCreateNewStaticMeshAssetOptions(
            enable_recompute_normals=False, enable_recompute_tangents=True,
            enable_nanite=False, enable_collision=bool(flags & 1),
            collision_mode=u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        mesh, outcome = u.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dynamic, path, options)
        assert mesh and outcome == u.GeometryScriptOutcomePins.SUCCESS, (path, outcome)
        mesh.set_material(0, material)
        assert u.EditorAssetLibrary.save_loaded_asset(mesh)
    actor = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector(*origin))
    actor.static_mesh_component.set_static_mesh(mesh)
    actor.static_mesh_component.set_material(0, material)
    actor.static_mesh_component.set_collision_enabled(u.CollisionEnabled.QUERY_ONLY if flags & 1 else u.CollisionEnabled.NO_COLLISION)
    actor.static_mesh_component.set_cast_shadow(bool(flags & 1))
    actor.set_actor_label(f'{index:04d} {section["material"]} {section["chunk"]}')
    actor.set_folder_path('Funafuti/'+('Water' if flags & 2 else 'Surfaces' if flags & 1 else 'Scenery'))
    actor.set_editor_property('tags', ['ArriettyBaseline', f'Section{index:04d}'])
    total += count//3
    records.append({'asset': path, 'triangles': count//3, 'origin_cm': origin, 'material': section['material']})
    if index % 40 == 0:
        print(f'ARRIETTY_AUTHORING_PROGRESS sections={index+1}/{len(meta["sections"])} triangles={total}', flush=True)
assert offset == len(data) and total == meta['triangles']

start = actors.spawn_actor_from_class(u.PlayerStart, u.Vector(0, 0, 0))
start.set_actor_label('ArriettyStart - runway origin')
start.set_editor_property('tags', ['ArriettyStart'])
start.set_actor_rotation(u.Rotator(pitch=0, yaw=(180-meta['initial_heading_degrees']) % 360, roll=0), False)
start.set_folder_path('Funafuti/Setup')
sun = actors.spawn_actor_from_class(u.DirectionalLight, u.Vector(0, 0, 1000))
sun.set_actor_label('Funafuti Sun - baseline sunset')
sun.set_actor_rotation(u.Rotator(pitch=-meta['sun_elevation'], yaw=meta['sun_azimuth']+180, roll=0), False)
sun.light_component.set_editor_property('mobility', u.ComponentMobility.MOVABLE)
sun.light_component.set_editor_property('atmosphere_sun_light', True)
sun.light_component.set_editor_property('light_source_angle', .533)
sun.light_component.set_editor_property('intensity', 50000*max(0, min(1, (meta['sun_elevation']+.3)/8)))
sun.set_folder_path('Funafuti/Lighting')
sky = actors.spawn_actor_from_class(u.SkyAtmosphere, u.Vector(0, 0, 0))
sky.set_folder_path('Funafuti/Lighting')
light = actors.spawn_actor_from_class(u.SkyLight, u.Vector(0, 0, 200))
light.light_component.set_editor_property('mobility', u.ComponentMobility.MOVABLE)
light.light_component.set_editor_property('real_time_capture', True)
light.light_component.set_editor_property('intensity', 1.)
light.set_folder_path('Funafuti/Lighting')
post = actors.spawn_actor_from_class(u.PostProcessVolume, u.Vector(0, 0, 0))
post.set_editor_property('unbound', True)
settings = post.get_editor_property('settings')
for key, value in {
    'auto_exposure_method': u.AutoExposureMethod.AEM_MANUAL,
    'auto_exposure_bias': 0., 'auto_exposure_apply_physical_camera_exposure': True,
    'camera_iso': 100., 'camera_shutter_speed': 125., 'depth_of_field_fstop': 4.,
}.items():
    settings.set_editor_property('override_'+key, True)
    settings.set_editor_property(key, value)
post.set_editor_property('settings', settings)
post.set_folder_path('Funafuti/Lighting')
u.get_editor_subsystem(u.UnrealEditorSubsystem).set_level_viewport_camera_info(
    u.Vector(15000, -35000, 22000), u.Rotator(pitch=-30, yaw=113, roll=0))
assert u.EditorLoadingAndSavingUtils.save_map(world, MAP)
assert u.EditorAssetLibrary.save_directory(BASE)
receipt = {'source_build': meta['build_number'], 'geometry_sha256': meta['geometry_sha256'],
           'reef_sha256': meta['reef_sha256'], 'triangles': total, 'sections': records,
           'map': MAP, 'attributions': meta['attributions'], 'initial_heading_degrees': meta['initial_heading_degrees'],
           'origin_latitude': meta['origin_latitude'], 'origin_longitude': meta['origin_longitude']}
(PROJECT.parent/'ArriettyBaseline.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'ARRIETTY_FUNAFUTI_AUTHORING_READY sections={len(records)} triangles={total} materials={len(materials)} map={MAP}')
