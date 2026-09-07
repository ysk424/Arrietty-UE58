"""Real PowerShell wrappers, with the simulator replaced before its boundary."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows launcher')
class WorldLauncherTests(unittest.TestCase):
    def test_both_entry_points_preserve_world_paths_and_offline_switches(self):
        for shell in ('powershell.exe', 'pwsh.exe'):
            executable = shutil.which(shell)
            if not executable:
                continue
            for script in ('start.ps1', 'start-ue.ps1'):
                with self.subTest(shell=shell, script=script), tempfile.TemporaryDirectory(prefix='world launch ') as directory:
                    root = Path(directory)
                    (root/'tools').mkdir()
                    for name in ('start.ps1', 'start-ue.ps1'):
                        shutil.copy2(ROOT/name, root/name)
                    (root/'tools/start_world.py').write_text(
                        'import argparse,json\n'
                        'p=argparse.ArgumentParser()\n'
                        'p.add_argument("--world")\np.add_argument("--runtime")\n'
                        'p.add_argument("--port",type=int)\n'
                        'p.add_argument("--offline",action="store_true")\n'
                        'p.add_argument("--smoke",action="store_true")\n'
                        'p.add_argument("--headless",action="store_true")\n'
                        'print("ARGV="+json.dumps(vars(p.parse_args())))\n', encoding='utf-8')
                    world = str(root/'Arrietty Projects/City with spaces/world.json')
                    runtime = str(root/'runtime with spaces')
                    result = subprocess.run([executable, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(root/script),
                                             '-WorldManifest', world, '-RuntimeRoot', runtime, '-WorldPort', '29859',
                                             '-Offline', '-SmokeTest', '-Headless'],
                                            capture_output=True, text=True, errors='replace', timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                    values = json.loads(next(line[5:] for line in result.stdout.splitlines() if line.startswith('ARGV=')))
                    self.assertEqual(values, dict(world=world, runtime=runtime, port=29859, offline=True, smoke=True, headless=True))
