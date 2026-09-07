"""Editor menu only. Opening an editor never performs an export."""
import unreal


def register_arrietty_menu():
    menus = unreal.ToolMenus.get()
    menu = menus.extend_menu('LevelEditor.MainMenu.Tools')
    entry = unreal.ToolMenuEntry(name='Arrietty.ExportSavedWorld', type=unreal.MultiBlockType.MENU_ENTRY)
    entry.set_label('Export saved world to Arrietty')
    entry.set_tool_tip('Save all changes first. Export to Documents/Arrietty Projects.')
    entry.set_string_command(unreal.ToolMenuStringCommandType.PYTHON, '',
                             'import arrietty_exporter; arrietty_exporter.export_with_dialog()')
    menu.add_menu_entry('Arrietty', entry)
    menus.refresh_all_widgets()


if '-run=' not in unreal.SystemLibrary.get_command_line().lower():
    register_arrietty_menu()
