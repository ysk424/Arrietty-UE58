"""Validate an exported world, initialize a session, run packaged UE.

No source export, editor launch, fallback or rebuild occurs here.
"""
import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arrietty_ue.worlds import WorldError, atomic_json, contained, digest, read_json, validate, world_session


def runtime_files(root):
    root = Path(root).resolve()
    receipt = read_json(root/'arrietty-runtime.json')
    for entry in receipt['files']:
        path = contained(root, entry['path'])
        if not path.is_file() or path.stat().st_size != entry['size'] or digest(path) != entry['sha256']:
            raise WorldError('Runtime changed or is missing. Rebuild/restore it: '+entry['path'])
    executable = contained(root, receipt['executable'])
    if not any(e['path'] == receipt['executable'] for e in receipt['files']):
        raise WorldError('Runtime executable is absent from the receipt.')
    return receipt, executable


def run(args):
    if (args.smoke or args.headless) and not args.offline:
        raise WorldError('Smoke/offscreen verification requires --offline.')
    if not 1024 <= args.port <= 65535:
        raise WorldError('Invalid loopback port.')
    receipt, executable = runtime_files(args.runtime)
    world = validate(args.world, receipt['profile'])
    if not (ROOT/'.runtime/current.txt').is_file():
        subprocess.run([sys.executable, str(ROOT/'tools/install_runtime_dependencies.py')], check=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(('127.0.0.1', args.port))
    if not args.offline:
        # The fitness checkout still owns its original 19858 endpoint. Do not
        # let a new world runtime compete for the same physical devices.
        for other_port in {19858, 19859} - {args.port}:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
                    other.bind(('127.0.0.1', other_port))
            except OSError as error:
                raise WorldError('Another Arrietty simulator is running. Close it before live use.') from error
        processes = subprocess.check_output(['tasklist', '/FO', 'CSV'], text=True, errors='replace').lower()
        if 'vrserver.exe' not in processes:
            raise WorldError('Start SteamVR before live use.')
        if 'blender.exe' in processes:
            raise WorldError('Close the Blender/UPBGE simulator before live use.')
        if 'arriettyue.exe' in processes:
            raise WorldError('Another packaged Arrietty simulator is running. Close it before live use.')
    session = ROOT/'.runtime/world-sessions'/uuid.uuid4().hex
    session.mkdir(parents=True)
    atomic_json(session/'world-session.json', world_session(args.world, world))
    atomic_json(session/'session.json', {'token': secrets.token_hex(32), 'port': args.port, 'hardware': not args.offline})
    environment = os.environ.copy()
    environment['ARRIETTY_UE_SESSION'] = str(session/'session.json')
    environment['ARRIETTY_UE_SOLAR'] = str(session/'world-session.json')
    bridge_args = [sys.executable, '-u', str(ROOT/'tools/ue_bridge.py'), '--world', str(session/'world-session.json'),
                   '--session', str(session/'session.json'), '--log-path', str(session/'flight.csv')]
    if not args.offline:
        bridge_args.append('--hardware')
    print('World: '+world['name']+' | session: '+str(session), flush=True)
    bridge = None
    with (session/'bridge.log').open('w', encoding='utf-8') as log, (session/'bridge.err.log').open('w', encoding='utf-8') as err:
        try:
            bridge = subprocess.Popen(bridge_args, cwd=ROOT, env=environment, stdout=log, stderr=err,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                if bridge.poll() is not None:
                    raise WorldError('Bridge startup failed. See '+str(session/'bridge.err.log'))
                if 'ARRIETTY_UE_BRIDGE_READY' in (session/'bridge.log').read_text(encoding='utf-8', errors='replace'):
                    break
                time.sleep(.1)
            else:
                raise WorldError('Bridge startup timed out.')
            game_args = [str(executable), world['map']+'?game=/Script/ArriettyUE.ArriettyGameMode',
                         '-pak', '-nosplash', '-nop4', '-windowed', '-ResX=1600', '-ResY=900',
                         '-UserDir='+str(session/'user')+'/', '-abslog='+str(session/'ue.log')]
            game_args.append('-nohmd' if args.offline else '-vr')
            if args.smoke:
                game_args += ['-ArriettySmoke', '-unattended']
            if args.smoke or args.headless:
                game_args += ['-RenderOffscreen', '-nosound']
            result = subprocess.run(game_args, cwd=executable.parent, env=environment,
                                    timeout=180 if args.smoke else None,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if args.smoke or args.headless else 0)
            if result.returncode:
                raise WorldError('Simulator failed. See '+str(session/'ue.log'))
            if args.smoke:
                output = (session/'ue.log').read_text(encoding='utf-8', errors='replace')
                if 'ARRIETTY_WORLD_MAP_READY '+world['map'] not in output or 'ARRIETTY_UE_SMOKE_DONE' not in output:
                    raise WorldError('Packaged world smoke failed. See '+str(session/'ue.log'))
                print('ARRIETTY_PACKAGED_WORLD_SMOKE_OK', flush=True)
        finally:
            if bridge is not None and bridge.poll() is None:
                try:
                    bridge.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    bridge.terminate()
                    bridge.wait(timeout=10)
    return session


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, default=ROOT/'build/runtime/Windows')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--port', type=int, default=19859)
    arguments = parser.parse_args()
    try:
        run(arguments)
    except (WorldError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
