"""Export the latest verified world to an engine-neutral mesh stream in a copy.

Run in background UPBGE. Never saves a blend, and exports only the persistent
Secret World collection. UE axes are north/east/up in centimetres.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b"ARRW0001"


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=ROOT.parent / "Secret-World")
    parser.add_argument("--output", type=Path, default=ROOT / "unreal/ArriettyUE/Content/SecretWorld")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    records = []
    for p in (args.source_root / "build/runtime").glob("*.runtime.json"):
        r = json.loads(p.read_text(encoding="utf-8-sig"))
        if r.get("schema_version") == 1 and len(str(r.get("build_number", ""))) == 17:
            records.append(r)
    record = max(records, key=lambda r: r["build_number"])
    name = record["output_name"]
    if Path(name).name != name:
        raise ValueError("Invalid Runtime filename")
    source = args.source_root / "build/runtime" / name
    if digest(source) != record["output_sha256"]:
        raise ValueError("Latest Secret World Runtime hash mismatch")
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    scene = bpy.context.scene
    world = bpy.data.collections.get("Secret World")
    if world is None:
        raise ValueError("Secret World collection missing")
    objects = sorted(world.all_objects, key=lambda o:o.name)
    if str(scene.get("secret_world_runtime_build_number")) != record["build_number"]:
        raise ValueError("Embedded build identity mismatch")
    runway = bpy.data.objects["Funafuti Runway 03-21"]
    points = [runway.matrix_world @ v.co for v in runway.data.vertices]
    assert len(points) == 4
    elevation = sum(p.z for p in points)/4
    forward = min(((points[0]+points[1])*.5,(points[2]+points[3])*.5), key=lambda p:p.y)
    heading = math.degrees(math.atan2(forward.x,-forward.y))
    args.output.mkdir(parents=True, exist_ok=True)
    water = bpy.data.materials["Funafuti Seamless Atoll Water"]
    nodes = water.node_tree.nodes
    tex = next(n for n in nodes if n.type == "TEX_IMAGE")
    ramp = next(n for n in nodes if n.type == "VALTORGB").color_ramp
    sub = next(n for n in nodes if n.type == "VECT_MATH" and n.operation == "SUBTRACT")
    mul = next(n for n in nodes if n.type == "VECT_MATH" and n.operation == "MULTIPLY")
    offset, scale = tuple(sub.inputs[1].default_value), tuple(mul.inputs[1].default_value)
    image = tex.image
    pixels = list(image.pixels)
    width,height = image.size
    out_pixels = bytearray()
    for y in range(height-1,-1,-1):
        for x in range(width):
            c = ramp.evaluate(pixels[(y*width+x)*4])
            # Linear BGRA8, paired with SRGB=false in UE.
            out_pixels.extend(round(max(0,min(1,c[i]))*255) for i in (2,1,0,3))
    (args.output / "reef.bgra").write_bytes(out_pixels)
    # Uncompressed top-left BGRA TGA for the editor's default material texture.
    header = struct.pack('<BBBHHBHHHHBB',0,0,2,0,0,0,0,0,width,height,32,0x28)
    (args.output / 'reef.tga').write_bytes(header + out_pixels)

    groups = defaultdict(bytearray)
    descriptors = {}
    sources = []
    triangles = 0
    rides = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        if obj.get("secret_world_save_policy") != "persistent_non_google":
            raise ValueError("Non-persistent/unknown mesh blocked: " + obj.name)
        if len(obj.modifiers):
            raise ValueError("Unfrozen Runtime modifier: " + obj.name)
        collision = obj.get("secret_world_runtime_collision") == "static_triangle_mesh"
        rides += int(collision)
        mesh = obj.data
        mesh.calc_loop_triangles()
        matrix = obj.matrix_world
        normal_matrix = matrix.to_3x3().inverted().transposed()
        sources.append({"name": obj.name, "triangles":len(mesh.loop_triangles),"collision":collision})
        for tri in mesh.loop_triangles:
            mat = mesh.materials[tri.material_index] if mesh.materials else None
            if mat is None:
                raise ValueError("Missing material: " + obj.name)
            is_water = mat == water
            center = matrix @ tri.center if hasattr(tri,"center") else matrix @ mesh.vertices[tri.vertices[0]].co
            key = (mat.name,collision,math.floor(center.x/1000),math.floor(center.y/1000))
            shader = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"),None) if mat.node_tree else None
            color = list(shader.inputs['Base Color'].default_value if shader and not shader.inputs['Base Color'].is_linked else mat.diffuse_color)
            rough = float(shader.inputs['Roughness'].default_value) if shader else .8
            descriptors[key] = {"material":mat.name,"collision":collision,"water":is_water,
                                "color":color,"roughness":rough}
            buf = groups[key]
            for loop in tri.loops:
                vertex = mesh.vertices[mesh.loops[loop].vertex_index]
                p = matrix @ vertex.co
                normal = (normal_matrix @ mesh.corner_normals[loop].vector).normalized()
                uv = (((vertex.co.x-offset[0])*scale[0], 1-(vertex.co.y-offset[1])*scale[1])
                      if is_water else (0,0))
                buf.extend(struct.pack("<8f",p.y*100,p.x*100,(p.z-elevation)*100,
                                       normal.y,normal.x,normal.z,*uv))
            triangles += 1
    if rides != 5:
        raise ValueError(f"Expected five accepted ride surfaces, got {rides}")
    sections = []
    with (args.output / "world.bin").open("wb") as out:
        out.write(MAGIC)
        out.write(struct.pack("<I",len(groups)))
        for key in sorted(groups):
            desc = descriptors[key]
            data = groups[key]
            count = len(data)//32
            flags = int(desc['collision']) | int(desc['water'])<<1
            out.write(struct.pack("<II4f",count,flags,*desc['color'][:3],desc['roughness']))
            out.write(data)
            sections.append(dict(desc,vertices=count,chunk=list(key[2:])))
    metadata = dict(record, format_version=1, axes="UE X=north,Y=east,Z=up; centimetres",
                    initial_heading_degrees=heading, runway_source_elevation_m=elevation,
                    origin_latitude=float(scene['secret_world_origin_latitude_exact']),
                    origin_longitude=float(scene['secret_world_origin_longitude_exact']),
                    local_time=scene.get('secret_world_solar_local',''),
                    sun_azimuth=float(scene.get('secret_world_solar_azimuth_degrees',277.36)),
                    sun_elevation=float(scene.get('secret_world_solar_elevation_degrees',3.39)),
                    water_width=width,water_height=height,triangles=triangles,
                    ride_surfaces=rides,source_meshes=len(sources),sections=sections,sources=sources,
                    geometry_sha256=digest(args.output/'world.bin'),
                    reef_sha256=digest(args.output/'reef.bgra'),
                    exporter_sha256=digest(__file__),
                    attributions=["OpenStreetMap contributors / ODbL-1.0","Allen Coral Atlas / CC BY 4.0"])
    if digest(source) != record['output_sha256']:
        raise RuntimeError("Source changed during export")
    (args.output/'world.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f"ARRIETTY_UE_WORLD_EXPORTED build={record['build_number']} meshes={len(sources)} triangles={triangles} sections={len(sections)} ride_surfaces={rides}",flush=True)


if __name__ == '__main__':
    main()
