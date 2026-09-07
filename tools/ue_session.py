"""Prepare launch metadata using Secret World's own solar calculation."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--date', default='')
    p.add_argument('--time', default='17:45')
    p.add_argument('--world-root', type=Path, default=ROOT.parent/'Secret-World')
    p.add_argument('--hardware', action='store_true')
    args = p.parse_args()
    directory = ROOT/'unreal/ArriettyUE/Content/SecretWorld'
    world = json.loads((directory/'world.json').read_text(encoding='utf-8'))
    for name, field in [('world.bin','geometry_sha256'),('reef.bgra','reef_sha256')]:
        with (directory/name).open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest() != world[field]:
                raise ValueError('Prepared world hash mismatch: '+name)
    latest = max(json.loads(path.read_text(encoding='utf-8-sig'))['build_number']
                 for path in (args.world_root/'build/runtime').glob('*.runtime.json'))
    if world['build_number'] != latest:
        raise ValueError('A newer Secret World exists. Run tools/prepare_ue.ps1 first.')
    spec=importlib.util.spec_from_file_location('secret_world_solar',args.world_root/'solar.py')
    solar=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(solar)
    date=args.date or datetime.now(timezone(timedelta(hours=12))).date().isoformat()
    instant=solar.parse_local(date,args.time,12)
    result=solar.position(instant,world['origin_latitude'],world['origin_longitude'])
    world.update(local_time=result['local'],sun_azimuth=result['azimuth_degrees'],sun_elevation=result['elevation_degrees'],solar_module_path=str((args.world_root/'solar.py').resolve()))
    runtime=ROOT/'.runtime/ue'
    runtime.mkdir(parents=True,exist_ok=True)
    (runtime/'world-session.json').write_text(json.dumps(world,ensure_ascii=False),encoding='utf-8')
    config={'token':secrets.token_hex(32),'port':19858,'hardware':args.hardware}
    (runtime/'session.json').write_text(json.dumps(config),encoding='utf-8')
    print(f"Secret World {world['build_number']} | Tuvalu {result['local']}")


if __name__=='__main__': main()
