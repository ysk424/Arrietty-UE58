"""Manifest failures must be caught before the simulator/device boundary."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from arrietty_ue.worlds import (FORMAT, VERSION, RUNTIME_ABI, WorldError, atomic_json,
                               contained, digest, source_inventory, validate, world_session)


class WorldManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='arrietty worlds ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root/'Unreal Projects/City/City.uproject'
        atomic_json(self.project, {'FileVersion': 3})
        self.map = self.project.parent/'Content/Worlds/City/Map.umap'
        self.map.parent.mkdir(parents=True)
        self.map.write_bytes(b'saved map')
        self.directory = self.root/'Arrietty Projects/City'
        self.directory.mkdir(parents=True)
        self.pak = self.directory/'world-test.pak'
        self.pak.write_bytes(b'converted world')
        self.path = self.directory/'world.json'
        self.profile = {'abi': RUNTIME_ABI, 'engine': {'MajorVersion': 5, 'MinorVersion': 8}}
        self.data = {'format': FORMAT, 'version': VERSION, 'name': 'City', 'world_id': 'test',
                     'source_project': str(self.project), 'source_files': source_inventory(self.project),
                     'profile': self.profile, 'map': '/Game/Worlds/City/Map', 'mounts': [],
                     'start': {'location_cm': [1234, 5678, 500], 'yaw_degrees': 45},
                     'files': [{'path': self.pak.name, 'size': self.pak.stat().st_size, 'sha256': digest(self.pak)}]}
        self.save()

    def save(self):
        atomic_json(self.path, self.data)

    def test_saved_world_and_nonzero_start_are_resolved(self):
        result = validate(self.path, self.profile)
        session = world_session(self.path, result)
        self.assertEqual(session['spawn_location_cm'], [1234, 5678, 500])
        self.assertEqual(session['initial_heading_degrees'], 135)
        self.assertEqual(session['world_pak'], str(self.pak.resolve()))
        self.assertEqual(session['solar_mode'], 'authored')

    def test_changed_source_even_same_size_is_an_error(self):
        self.map.write_bytes(b'SAVED MAP')
        with self.assertRaisesRegex(WorldError, 'export it again'):
            validate(self.path, self.profile)

    def test_added_external_actor_is_an_error(self):
        actor = self.project.parent/'Content/__ExternalActors__/Worlds/City/Map/AA/Actor.uasset'
        actor.parent.mkdir(parents=True)
        actor.write_bytes(b'new actor')
        with self.assertRaisesRegex(WorldError, 'added or removed'):
            validate(self.path, self.profile)

    def test_deleted_source_is_an_error(self):
        self.map.unlink()
        with self.assertRaises(WorldError):
            validate(self.path)

    def test_editor_cache_and_logs_do_not_invalidate_export(self):
        saved = self.project.parent/'Saved/Logs/editor.log'
        saved.parent.mkdir(parents=True)
        saved.write_text('cache changed')
        validate(self.path, self.profile)

    def test_runtime_compatibility_is_checked(self):
        profile = copy.deepcopy(self.profile)
        profile['engine']['MinorVersion'] = 9
        with self.assertRaisesRegex(WorldError, 'settings differ'):
            validate(self.path, profile)

    def test_corrupt_output_is_an_error(self):
        self.pak.write_bytes(b'corrupted world')
        with self.assertRaisesRegex(WorldError, 'damaged or differs'):
            validate(self.path)

    def test_manifest_cannot_escape_output_folder(self):
        self.data['files'][0]['path'] = '../outside.pak'
        self.save()
        with self.assertRaisesRegex(WorldError, 'leaves'):
            validate(self.path)

    def test_absolute_output_path_is_rejected(self):
        self.data['files'][0]['path'] = self.pak.resolve().as_posix()
        self.save()
        with self.assertRaises(WorldError):
            validate(self.path)

    def test_unknown_schema_does_not_launch(self):
        self.data['version'] = 100
        self.save()
        with self.assertRaisesRegex(WorldError, 'version'):
            validate(self.path)

    def test_malformed_fields_fail_before_session_metadata(self):
        for field, value in (('name', None), ('world_id', ''), ('source_project', 42),
                             ('map', '/Game/Worlds//Map'), ('map', '/Game/Map?game=Other'),
                             ('start', {'location_cm': [True, 0, 0], 'yaw_degrees': 0})):
            with self.subTest(field=field):
                broken = copy.deepcopy(self.data)
                broken[field] = value
                atomic_json(self.path, broken)
                with self.assertRaises(WorldError):
                    validate(self.path, self.profile)

    def test_unicode_map_package_name_is_not_restricted_to_ascii(self):
        self.data['map'] = '/Game/世界/東京/マップ'
        self.save()
        self.assertEqual(validate(self.path, self.profile)['map'], self.data['map'])

    def test_nonfinite_start_is_rejected(self):
        self.data['start']['yaw_degrees'] = float('nan')
        self.path.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(WorldError, 'yaw'):
            validate(self.path)

    def test_reserved_mount_is_rejected(self):
        self.data['mounts'] = ['Game']
        self.save()
        with self.assertRaisesRegex(WorldError, 'mount'):
            validate(self.path)

    def test_project_settings_changes_require_export(self):
        settings = self.project.parent/'Config/DefaultEngine.ini'
        settings.parent.mkdir()
        settings.write_text('[Settings]\nchanged=True\n')
        with self.assertRaisesRegex(WorldError, 'source data changed'):
            validate(self.path)

    def test_missing_source_project_never_uses_old_output(self):
        self.project.unlink()
        with self.assertRaisesRegex(WorldError, 'Missing source'):
            validate(self.path)
