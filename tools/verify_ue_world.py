"""Validate exported geometry, attribution, collision roles and source hashes."""
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def verify(directory=None):
    directory = directory or ROOT/'unreal/ArriettyUE/Content/SecretWorld'
    meta=json.loads((directory/'world.json').read_text(encoding='utf-8'))
    data=(directory/'world.bin').read_bytes()
    assert hashlib.sha256(data).hexdigest()==meta['geometry_sha256']
    assert hashlib.sha256((directory/'reef.bgra').read_bytes()).hexdigest()==meta['reef_sha256']
    assert data[:8]==b'ARRW0001'
    count,=struct.unpack_from('<I',data,8)
    assert count==len(meta['sections'])
    offset=12
    total=0
    collision=0
    for desc in meta['sections']:
        n,flags,r,g,b,rough=struct.unpack_from('<II4f',data,offset)
        offset+=24
        assert n==desc['vertices'] and n%3==0 and n>0
        assert bool(flags&1)==desc['collision'] and bool(flags&2)==desc['water']
        collision+=bool(flags&1)
        length=n*32
        vertices=memoryview(data)[offset:offset+length]
        assert len(vertices)==length
        for v in struct.iter_unpack('<8f',vertices):
            assert all(math.isfinite(x) for x in v)
            assert .99<sum(x*x for x in v[3:6])<1.01
        offset+=length
        total+=n//3
    assert offset==len(data)
    assert total==meta['triangles']==sum(s['triangles'] for s in meta['sources'])
    assert sum(s['collision'] for s in meta['sources'])==meta['ride_surfaces']==5
    assert meta['attributions'] and meta['source_meshes']==len(meta['sources'])
    source=ROOT.parent/'Secret-World/build/runtime'/meta['output_name']
    with source.open('rb') as stream:
        assert hashlib.file_digest(stream,'sha256').hexdigest()==meta['output_sha256']
    print(f"ARRIETTY_UE_WORLD_VERIFIED build={meta['build_number']} triangles={total} sections={count} collision_sections={collision}")


if __name__=='__main__': verify()
