"""UE commandlet: reproducible content for the packaged simulator."""
import unreal as u

mel = u.MaterialEditingLibrary
path = '/Game/Materials/M_Instruments'
if u.EditorAssetLibrary.does_asset_exist(path):
    u.EditorAssetLibrary.delete_asset(path)
panel = u.EditorAssetLibrary.duplicate_asset('/Engine/EngineMaterials/Widget3DPassThrough', path)
panel.set_editor_property('blend_mode', u.BlendMode.BLEND_OPAQUE)
panel.set_editor_property('two_sided', True)
panel.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
source = mel.get_material_property_input_node(panel, u.MaterialProperty.MP_EMISSIVE_COLOR)
output = mel.get_material_property_input_node_output_name(panel, u.MaterialProperty.MP_EMISSIVE_COLOR)
inverse = mel.create_material_expression(panel, u.MaterialExpressionEyeAdaptationInverse, 500, 0)
inputs = mel.get_material_expression_input_names(inverse)
assert mel.connect_material_expressions(source, output, inverse, inputs[0])
assert mel.connect_material_property(inverse, '', u.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(panel)
u.EditorAssetLibrary.save_loaded_asset(panel)
world = u.EditorLoadingAndSavingUtils.new_blank_map(False)
assert u.EditorLoadingAndSavingUtils.save_map(world, '/Game/Maps/ArriettyEntry')
print('ARRIETTY_RUNTIME_CONTENT_READY')
