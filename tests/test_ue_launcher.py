"""Exercise the real launcher/native argv boundary without starting devices/UE."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell integration')
class LauncherArgumentTests(unittest.TestCase):
    def run_launcher(self, date):
        for shell in ('powershell.exe', 'pwsh.exe'):
            executable = shutil.which(shell)
            if executable is None:
                if shell == 'powershell.exe':
                    self.fail('Windows PowerShell 5.1 is required for this regression')
                continue
            with self.subTest(shell=shell, date=date), tempfile.TemporaryDirectory(prefix='ue launcher ') as td:
                root = Path(td)
                shutil.copy2(ROOT/'start-ue.ps1', root/'start-ue.ps1')
                for folder in ('tools', '.runtime', 'unreal/ArriettyUE/Content/Maps', 'engine/Engine/Build'):
                    (root/folder).mkdir(parents=True, exist_ok=True)
                (root/'.runtime/current.txt').write_text('fixture')
                (root/'unreal/ArriettyUE/Content/Maps/Funafuti.umap').touch()
                (root/'engine/Engine/Build/Build.version').write_text(json.dumps(dict(MajorVersion=5, MinorVersion=8)))
                # A real Python executable parses the argv supplied by the real
                # launcher. This fixture records only the non-sensitive options.
                (root/'tools/ue_session.py').write_text(
                    'import argparse, json\n'
                    'p=argparse.ArgumentParser()\n'
                    'p.add_argument("--date",default="auto")\n'
                    'p.add_argument("--time")\n'
                    'p.add_argument("--world-root")\n'
                    'p.add_argument("--hardware",action="store_true")\n'
                    'print("ARGV="+json.dumps(vars(p.parse_args())))\n'
                )
                quoted_python = sys.executable.replace("'", "''")
                date_argument = '' if date is None else f" -LocalDate '{date}'"
                # Intercept Start-Process only after the native Python call.
                # No bridge, OpenXR, BLE, serial or fan process can be started.
                (root/'harness.ps1').write_text(
                    "$ErrorActionPreference='Stop'\n"
                    f"function py {{ '{quoted_python}' }}\n"
                    "function Get-NetUDPEndpoint {}\n"
                    "function Start-Process { throw 'LAUNCH_INTERCEPTED' }\n"
                    "try {\n"
                    "  & (Join-Path $PSScriptRoot 'start-ue.ps1') -Offline "
                    "-EngineRoot (Join-Path $PSScriptRoot 'engine')" + date_argument + "\n"
                    "  throw 'Expected process boundary'\n"
                    "} catch {\n"
                    "  if ($_.Exception.Message -ne 'LAUNCH_INTERCEPTED') { throw }\n"
                    "  Write-Output 'LAUNCHER_ARGUMENTS_OK'\n"
                    "}\n",
                    encoding='utf-8-sig',
                )
                result = subprocess.run(
                    [executable, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(root/'harness.ps1')],
                    capture_output=True, text=True, errors='replace', timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertIn('LAUNCHER_ARGUMENTS_OK', result.stdout)
                parsed = json.loads(next(line[5:] for line in result.stdout.splitlines() if line.startswith('ARGV=')))
                self.assertEqual(parsed['date'], date or 'auto')
                self.assertEqual(parsed['time'], '17:45')
                self.assertFalse(parsed['hardware'])
                self.assertTrue(parsed['world_root'].endswith('Secret-World'))

    def test_unspecified_date_uses_python_default(self):
        self.run_launcher(None)

    def test_explicit_date_is_preserved(self):
        self.run_launcher('2026-09-07')
