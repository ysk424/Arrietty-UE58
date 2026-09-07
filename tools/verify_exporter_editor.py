"""UE fixture-only check for the menu and the unsaved-map boundary."""
from pathlib import Path
import unreal as u
import init_unreal
import arrietty_exporter
import arrietty_world_core as core

project = Path(u.Paths.get_project_file_path()).resolve()
assert 'world-fixtures' in project.parts
init_unreal.register_arrietty_menu()
menu = u.ToolMenus.get().find_menu('LevelEditor.MainMenu.Tools')
assert menu is not None
# UE does not expose ToolMenu.Sections to Python. This checks registration
# through the real API; it does not claim a graphical menu-click test.
u.EditorLoadingAndSavingUtils.new_blank_map(False)
try:
    arrietty_exporter.export_current_world()
except core.WorldError as error:
    assert 'Save' in str(error) or 'saved map' in str(error), str(error)
else:
    raise AssertionError('An unsaved map must not export.')
print('ARRIETTY_EDITOR_EXPORT_BOUNDARY_OK menu_api=1 unsaved_rejected=1')
