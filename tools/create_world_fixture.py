"""UE-only integration fixture. Run only in a disposable test project."""
import os
from pathlib import Path
import struct
import unreal as u

project = Path(u.Paths.get_project_file_path()).resolve()
assert 'world-fixtures' in project.parts, 'Fixture creation requires the dedicated test directory.'
name = project.stem
map_path = '/Game/Worlds/'+name+'/Map'
actors = u.get_editor_subsystem(u.EditorActorSubsystem)
world = u.EditorLoadingAndSavingUtils.new_blank_map(False)
start = actors.spawn_actor_from_class(u.PlayerStart, u.Vector(1000, 2000, 500))
start.set_actor_rotation(u.Rotator(pitch=0, yaw=45 if name == 'City' else 135, roll=0), False)
material_path = '/Game/Worlds/'+name+'/M_Fixture'
texture_path = '/Game/Worlds/'+name+'/T_ImportedFixture'
if not u.EditorAssetLibrary.does_asset_exist(texture_path):
    # Imported textures carry Editor-only Interchange metadata. That metadata
    # must not become an unsupported runtime-code dependency during export.
    source_texture = project.parent/'Saved/fixture-white.tga'
    source_texture.parent.mkdir(parents=True, exist_ok=True)
    source_texture.write_bytes(struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, 2, 2, 32, 0x28)+bytes([255]*16))
    task = u.AssetImportTask()
    task.set_editor_property('filename', str(source_texture))
    task.set_editor_property('destination_path', '/Game/Worlds/'+name)
    task.set_editor_property('destination_name', 'T_ImportedFixture')
    task.set_editor_property('automated', True)
    task.set_editor_property('save', True)
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
texture = u.load_asset(texture_path)
assert texture
material = u.load_asset(material_path)
if material is None:
    material = u.AssetToolsHelpers.get_asset_tools().create_asset('M_Fixture', '/Game/Worlds/'+name, u.Material, u.MaterialFactoryNew())
mel = u.MaterialEditingLibrary
mel.delete_all_material_expressions(material)
color = mel.create_material_expression(material, u.MaterialExpressionConstant3Vector, 0, 0)
color.set_editor_property('constant', u.LinearColor(.12, .35, .6, 1) if name == 'City' else u.LinearColor(.1, .5, .16, 1))
sample = mel.create_material_expression(material, u.MaterialExpressionTextureSample, 0, 200)
sample.set_editor_property('texture', texture)
multiply = mel.create_material_expression(material, u.MaterialExpressionMultiply, 250, 0)
mel.connect_material_expressions(color, '', multiply, 'A')
mel.connect_material_expressions(sample, 'RGB', multiply, 'B')
mel.connect_material_property(multiply, '', u.MaterialProperty.MP_BASE_COLOR)
mel.recompile_material(material)
u.EditorAssetLibrary.save_loaded_asset(material)
floor = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector(1000, 2000, 450))
floor.static_mesh_component.set_static_mesh(u.load_asset('/Engine/BasicShapes/Cube'))
floor.static_mesh_component.set_material(0, material)
floor.set_actor_scale3d(u.Vector(100, 100, 1))
for index in range(4):
    tower = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector((5000+index*500) if name == 'City' else (-3000-index*500), 6000+index*500, 1000))
    tower.static_mesh_component.set_static_mesh(u.load_asset('/Engine/BasicShapes/Cube'))
    tower.static_mesh_component.set_material(0, material)
    tower.set_actor_scale3d(u.Vector(2, 2, 8))
sun = actors.spawn_actor_from_class(u.DirectionalLight, u.Vector(0, 0, 500))
sun.set_actor_rotation(u.Rotator(pitch=-35, yaw=45, roll=0), False)
sun.light_component.set_editor_property('mobility', u.ComponentMobility.MOVABLE)
sun.light_component.set_editor_property('atmosphere_sun_light', True)
sun.light_component.set_editor_property('intensity', 50000.0)
actors.spawn_actor_from_class(u.SkyAtmosphere, u.Vector(0, 0, 0))
light = actors.spawn_actor_from_class(u.SkyLight, u.Vector(0, 0, 0))
light.light_component.set_editor_property('mobility', u.ComponentMobility.MOVABLE)
light.light_component.set_editor_property('real_time_capture', True)
post = actors.spawn_actor_from_class(u.PostProcessVolume, u.Vector(0, 0, 0))
post.set_editor_property('unbound', True)
settings = post.get_editor_property('settings')
for key, value in {'auto_exposure_method': u.AutoExposureMethod.AEM_MANUAL,
                   'auto_exposure_bias': 0.0, 'auto_exposure_apply_physical_camera_exposure': True,
                   'camera_iso': 100.0, 'camera_shutter_speed': 125.0, 'depth_of_field_fstop': 4.0}.items():
    settings.set_editor_property('override_'+key, True)
    settings.set_editor_property(key, value)
post.set_editor_property('settings', settings)
assert u.EditorLoadingAndSavingUtils.save_map(world, map_path)
u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(map_path)
u.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
import arrietty_exporter
destination = Path(os.environ['ARRIETTY_TEST_EXPORT_DIR'])
arrietty_exporter.export_current_world(destination)
print('ARRIETTY_FIXTURE_EXPORT_OK')
