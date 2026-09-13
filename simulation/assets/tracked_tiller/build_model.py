#!/usr/bin/env python3
"""Build a small, editable display model; no CAD or simulation dependency.

Python's standard library writes GLB. Optional ``--preview`` uses numpy and
Pillow. Author coordinates: x forward, y left, z up; output: x forward,
y up, z right. Lengths are metres. This geometry never configures dynamics.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import struct


@dataclass(frozen=True)
class Dimensions:
    # Only width and length are user-provided; other dimensions are illustrative.
    chassis_length_m: float = 1.6
    chassis_width_m: float = 1.2
    track_width_m: float = 0.22
    cover_top_m: float = 0.96
    rear_deck_top_m: float = 0.55
    implement_width_m: float = 1.2
    implement_rear_x_m: float = -1.43
    antenna_top_m: float = 1.15


DIMS = Dimensions()
MATERIALS = {
    "cover": ((0.86, 0.89, 0.87, 1), 0.05, 0.68),
    "deck": ((0.35, 0.40, 0.40, 1), 0.15, 0.65),
    "rubber": ((0.060, 0.080, 0.085, 1), 0.0, 0.94),
    "wheel": ((0.26, 0.31, 0.31, 1), 0.25, 0.62),
    "hub": ((0.52, 0.58, 0.56, 1), 0.50, 0.40),
    "orange": ((0.95, 0.30, 0.075, 1), 0.05, 0.55),
    "dark": ((0.095, 0.12, 0.13, 1), 0.1, 0.80),
    "antenna": ((0.94, 0.94, 0.89, 1), 0.0, 0.55),
}


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, factor):
    return tuple(x * factor for x in a)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def unit(a):
    length = math.sqrt(sum(v * v for v in a))
    return mul(a, 1 / length) if length else (0, 0, 1)


def to_view(point):
    return (point[0], point[2], -point[1])


class Model:
    def __init__(self):
        self.groups = {}
        self.parts = defaultdict(lambda: {"vertices": [], "faces": [], "names": []})

    def group(self, name, origin=(0, 0, 0), **extras):
        self.groups[name] = {"origin": origin, "extras": extras}

    def mesh(self, name, vertices, faces, material, group):
        part = self.parts[(group, material)]
        offset = len(part["vertices"])
        part["vertices"].extend(vertices)
        part["faces"].extend(tuple(index + offset for index in f) for f in faces)
        part["names"].append(name)

    def box(self, name, center, size, material, group):
        x, y, z = center
        a, b, c = (v / 2 for v in size)
        vertices = [(x + dx, y + dy, z + dz) for dz in (-c, c)
                    for dy in (-b, b) for dx in (-a, a)]
        faces = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6),
                 (0, 1, 4), (1, 5, 4), (2, 6, 3), (3, 6, 7),
                 (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]
        self.mesh(name, vertices, faces, material, group)

    def rod(self, name, start, end, radius, material, group, segments=24):
        axis = unit(sub(end, start))
        reference = (0, 0, 1) if abs(axis[2]) < 0.9 else (1, 0, 0)
        u = unit(cross(axis, reference))
        v = cross(axis, u)
        vertices = []
        for center in (start, end):
            for i in range(segments):
                angle = i * math.tau / segments
                delta = add(mul(u, radius * math.cos(angle)), mul(v, radius * math.sin(angle)))
                vertices.append(add(center, delta))
        vertices.extend((start, end))
        faces = []
        for i in range(segments):
            j = (i + 1) % segments
            faces.extend(((i, j, segments + i), (j, segments + j, segments + i),
                          (2 * segments, j, i),
                          (2 * segments + 1, segments + i, segments + j)))
        self.mesh(name, vertices, faces, material, group)

    def loft(self, name, rings, material, group):
        """Rectangular horizontal rings: (x_min, x_max, half_width, z)."""
        vertices = []
        for xmin, xmax, halfwidth, z in rings:
            vertices.extend(((xmin, -halfwidth, z), (xmax, -halfwidth, z),
                             (xmax, halfwidth, z), (xmin, halfwidth, z)))
        faces = [(0, 2, 1), (0, 3, 2)]
        for k in range(len(rings) - 1):
            for i in range(4):
                a, b = k * 4 + i, k * 4 + (i + 1) % 4
                faces.extend(((a, b, a + 4), (b, b + 4, a + 4)))
        end = 4 * (len(rings) - 1)
        faces.extend(((end, end + 1, end + 2), (end, end + 2, end + 3)))
        self.mesh(name, vertices, faces, material, group)


def hull(points):
    points = sorted(set(points))
    def turn(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    chains = []
    for sequence in (points, list(reversed(points))):
        chain = []
        for p in sequence:
            while len(chain) >= 2 and turn(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
        chains.append(chain[:-1])
    return chains[0] + chains[1]


def build_tracks(model, dims):
    end_x = dims.chassis_length_m / 2 - 0.205
    circles = [(-end_x, 0.31, 0.20), (end_x, 0.31, 0.20),
               (-0.42, 0.13, 0.125), (0.42, 0.13, 0.125)]
    outline = hull([(x + radius * math.cos(i * math.tau / 32),
                     z + radius * math.sin(i * math.tau / 32))
                    for x, z, radius in circles for i in range(32)])
    # A scaled inner contour creates an actual open belt, not a solid side panel.
    inside = [(x * 0.953, 0.262 + (z - 0.262) * 0.90) for x, z in outline]
    n = len(outline)
    for side, sign in (("left", 1), ("right", -1)):
        group = f"track_{side}"
        model.group(group)
        cy = sign * (dims.chassis_width_m - dims.track_width_m) / 2
        vertices = [(x, y, z) for y in (cy - dims.track_width_m / 2, cy + dims.track_width_m / 2)
                    for contour in (outline, inside) for x, z in contour]
        faces = []
        for i in range(n):
            j = (i + 1) % n
            for a, b, c, d in ((i, j, 2*n+j, 2*n+i),
                               (n+i, 3*n+i, 3*n+j, n+j),
                               (i, n+i, n+j, j),
                               (2*n+i, 2*n+j, 3*n+j, 3*n+i)):
                faces.extend(((a, b, c), (a, c, d)))
        model.mesh("continuous_open_belt", vertices, [tuple(reversed(f)) for f in faces], "rubber", group)
        # Ribs follow the complete perimeter and leave the side openings visible.
        lengths = [math.dist(outline[i], outline[(i+1) % n]) for i in range(n)]
        total = sum(lengths)
        for rib in range(48):
            s = total * rib / 48
            i = 0
            while s > lengths[i] and i < n - 1:
                s -= lengths[i]
                i += 1
            x0, z0 = outline[i]
            x1, z1 = outline[(i + 1) % n]
            t = s / lengths[i]
            x, z = x0 + t * (x1 - x0), z0 + t * (z1 - z0)
            tangent = unit((x1 - x0, 0, z1 - z0))
            normal = (tangent[2], 0, -tangent[0])
            center = (x + .0025 * normal[0], cy, z + .0025 * normal[2])
            verts = [add(center, add(mul(tangent, dx), add((0, dy, 0), mul(normal, dz))))
                     for dz in (-.0025, .0025) for dy in (-dims.track_width_m/2, dims.track_width_m/2)
                     for dx in (-.008, .008)]
            faces_box = [(0,2,1),(1,2,3),(4,5,6),(5,7,6),(0,1,4),(1,5,4),
                         (2,6,3),(3,6,7),(0,4,2),(2,4,6),(1,3,5),(3,7,5)]
            model.mesh(f"rib_{rib:02d}", verts, [tuple(reversed(f)) for f in faces_box], "dark", group)
        for wheel_i, (x, z, radius) in enumerate(
                [(-end_x, .31, .181), (end_x, .31, .181)] +
                [(x, .13, .103) for x in (-.42, -.21, 0, .21, .42)]):
            # Wheels sit within the belt width; hubs remain visible on the outside.
            y0, y1 = cy - .082, cy + .082
            model.rod(f"wheel_{wheel_i}", (x,y0,z),(x,y1,z),radius,"wheel",group,24)
            outer_y = cy + sign * .086
            model.rod(f"hub_{wheel_i}", (x,outer_y,z),(x,outer_y+sign*.01,z),
                      radius*.34,"hub",group,16)
            for hole in range(5):
                angle = hole * math.tau / 5
                hx, hz = x + radius*.65*math.cos(angle), z + radius*.65*math.sin(angle)
                model.rod(f"wheel_recess_{wheel_i}_{hole}", (hx,outer_y,hz),
                          (hx,outer_y+sign*.001,hz),radius*.13,"dark",group,8)
        # Suggest the support structure without hiding the road wheels.
        model.box("support_rail", (0,cy-sign*.055,.36), (1.04,.04,.06), "deck",group)


def build_model(dims=DIMS):
    model = Model()
    model.group("chassis")
    model.box("frame", (0,0,.40), (1.39,.75,.13), "dark", "chassis")
    model.box("lower_front", (.64,0,.455), (.18,.83,.085), "deck", "chassis")
    build_tracks(model, dims)
    model.group("rear_deck")
    model.box("low_rear_deck", (-.425,0,dims.rear_deck_top_m-.04),
              (.59,.80,.08), "deck", "rear_deck")
    for y in (-.39,.39):
        model.box("deck_edge", (-.43,y,.565), (.60,.018,.025), "cover", "rear_deck")
    model.group("front_battery_cover", purpose="Illustrative shell enclosing the front battery")
    model.loft("folded_plastic_cover", [(-.16,.755,.415,.49),(-.13,.74,.40,.57),
               (-.11,.685,.375,dims.cover_top_m-.07),(.015,.60,.325,dims.cover_top_m)],
               "cover", "front_battery_cover")
    # Simple face markings help read the vehicle's front from above.
    model.box("front_identification_strip", (.748,0,.615), (.011,.60,.026), "orange", "front_battery_cover")
    for y in (-.36,.36):
        model.box("side_identification_strip", (.16,y,.889), (.36,.008,.028), "orange", "front_battery_cover")
    model.box("front_lower_grille", (.759,0,.528), (.013,.51,.026), "dark", "front_battery_cover")
    for name, x, base_z in (("antenna_front",.43,.955),("antenna_rear",-.44,.55)):
        model.group(name, purpose="Position is illustrative; main/slave assignment is unspecified")
        model.rod("mast", (x,0,base_z),(x,0,dims.antenna_top_m-.025),.012,"dark",name,12)
        model.rod("disc", (x,0,dims.antenna_top_m-.026),(x,0,dims.antenna_top_m),
                  .055,"antenna",name,24)
    pivot=(-.80,0,.43)
    model.group("implement_lift", pivot, purpose="Move this node to illustrate lifting; display only",
                rotation_axis_view=[0,0,-1], rotation_axis_author=[0,1,0])
    group="implement_lift"
    for y in (-.30,.30):
        model.rod("lower_link",(-.73,y,.42),(-1.075,y,.30),.018,"deck",group,12)
    model.rod("upper_link",(-.67,0,.55),(-1.06,0,.46),.015,"hub",group,12)
    model.rod("crossbar",(-1.075,-.36,.39),(-1.075,.36,.39),.032,"dark",group,16)
    model.loft("rotary_tiller_cover", [(dims.implement_rear_x_m,-1.02,dims.implement_width_m/2-.013,.18),
               (dims.implement_rear_x_m+.015,-1.035,dims.implement_width_m/2-.013,.36),
               (dims.implement_rear_x_m+.07,-1.09,dims.implement_width_m/2-.025,.43)], "cover",group)
    model.box("rear_rubber_flap", (dims.implement_rear_x_m-.012,0,.195), (.028,1.13,.18), "rubber",group)
    model.box("rear_orange_strip", (dims.implement_rear_x_m-.028,0,.322), (.01,.88,.025), "orange",group)
    for y in (-.59,.59):
        model.box("side_guard", (-1.23,y,.22), (.44,.020,.25), "deck",group)
    model.rod("rotor",(-1.22,-.53,.13),(-1.22,.53,.13),.035,"dark",group,16)
    for i in range(9):
        y=-.48+i*.12
        model.box("cutter_hint",(-1.22,y,.081),(.034,.025,.084),"deck",group)
    return model


def write_glb(model, destination):
    """Minimal glTF 2.0 exporter with flat normals and few material draw calls."""
    data = bytearray()
    document = {"asset":{"version":"2.0","generator":"NodeFlow editable display model"},
                "scene":0,"scenes":[{"nodes":[0]}],
                "nodes":[{"name":"tracked_tiller","children":[],
                          "extras":{"units":"metres","forward":"+X","up":"+Y","right":"+Z"}}],
                "meshes":[],"materials":[],"accessors":[],"bufferViews":[],"buffers":[]}
    for name, (rgba, metallic, roughness) in MATERIALS.items():
        document["materials"].append({"name":name,"pbrMetallicRoughness":{
            "baseColorFactor":rgba,"metallicFactor":metallic,"roughnessFactor":roughness}})
    material_ids={name:i for i,name in enumerate(MATERIALS)}
    group_ids={}
    for name, group in model.groups.items():
        group_ids[name]=len(document["nodes"])
        document["nodes"][0]["children"].append(group_ids[name])
        document["nodes"].append({"name":name,"translation":to_view(group["origin"]),
                                  "children":[],"extras":group["extras"]})

    def accessor(values, component_type, kind, target, bounds=False):
        flat=[x for v in values for x in v] if kind=="VEC3" else values
        offset=len(data)
        fmt="f" if component_type==5126 else "I"
        data.extend(struct.pack("<"+fmt*len(flat),*flat))
        document["bufferViews"].append({"buffer":0,"byteOffset":offset,"byteLength":len(data)-offset,"target":target})
        obj={"bufferView":len(document["bufferViews"])-1,"componentType":component_type,
             "count":len(values),"type":kind}
        if bounds:
            obj.update(min=[min(p[i] for p in values) for i in range(3)],
                       max=[max(p[i] for p in values) for i in range(3)])
        document["accessors"].append(obj)
        return len(document["accessors"])-1

    for (group_name, material), part in model.parts.items():
        origin=model.groups[group_name]["origin"]
        vertices=[to_view(sub(p,origin)) for p in part["vertices"]]
        positions=[]
        normals=[]
        for face in part["faces"]:
            points=[vertices[i] for i in face]
            normal=unit(cross(sub(points[1],points[0]),sub(points[2],points[0])))
            positions.extend(points)
            normals.extend([normal]*3)
        pos=accessor(positions,5126,"VEC3",34962,True)
        norm=accessor(normals,5126,"VEC3",34962)
        indices=accessor(list(range(len(positions))),5125,"SCALAR",34963)
        mesh_id=len(document["meshes"])
        mesh_name=f"{group_name}_{material}"
        document["meshes"].append({"name":mesh_name,"primitives":[{
            "attributes":{"POSITION":pos,"NORMAL":norm},"indices":indices,"material":material_ids[material]}],
            "extras":{"parts":part["names"]}})
        node_id=len(document["nodes"])
        document["nodes"].append({"name":mesh_name,"mesh":mesh_id})
        document["nodes"][group_ids[group_name]]["children"].append(node_id)
    document["buffers"]=[{"byteLength":len(data)}]
    encoded=json.dumps(document,ensure_ascii=False,separators=(",",":")).encode()
    encoded+=b" "*((-len(encoded))%4)
    data.extend(b"\0"*((-len(data))%4))
    total=12+8+len(encoded)+8+len(data)
    destination.write_bytes(struct.pack("<4sII",b"glTF",2,total)+struct.pack("<I4s",len(encoded),b"JSON")+
                            encoded+struct.pack("<I4s",len(data),b"BIN\0")+data)
    return document


def bounds_of(model, include_implement=True):
    vertices=[v for (group,_),part in model.parts.items() if include_implement or group!="implement_lift"
              for v in part["vertices"]]
    return {"min":[min(v[i] for v in vertices) for i in range(3)],
            "max":[max(v[i] for v in vertices) for i in range(3)]}


def verify_glb(destination, model):
    """Check real serialized geometry, hierarchy, bounds, and accessor sizes."""
    raw=destination.read_bytes()
    magic,version,total=struct.unpack_from("<4sII",raw)
    assert (magic,version,total)==(b"glTF",2,len(raw))
    length,kind=struct.unpack_from("<I4s",raw,12)
    assert kind==b"JSON"
    doc=json.loads(raw[20:20+length])
    binary_header=20+length
    binary_length,kind=struct.unpack_from("<I4s",raw,binary_header)
    assert kind==b"BIN\0" and binary_header+8+binary_length==len(raw)
    binary=raw[binary_header+8:]
    triangle_count=0
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            pos=doc["accessors"][primitive["attributes"]["POSITION"]]
            view=doc["bufferViews"][pos["bufferView"]]
            values=struct.unpack_from("<"+"f"*pos["count"]*3,binary,view["byteOffset"])
            assert all(math.isfinite(v) for v in values)
            for axis in range(3):
                assert abs(min(values[axis::3])-pos["min"][axis])<1e-6
                assert abs(max(values[axis::3])-pos["max"][axis])<1e-6
            index=doc["accessors"][primitive["indices"]]
            index_view=doc["bufferViews"][index["bufferView"]]
            indices=struct.unpack_from("<"+"I"*index["count"],binary,index_view["byteOffset"])
            assert max(indices)<pos["count"] and len(indices)%3==0
            triangle_count+=len(indices)//3
    for part in model.parts.values():
        volume = sum(sum(a[i]*cross(b,c)[i] for i in range(3))/6
                     for face in part["faces"]
                     for a,b,c in [[part["vertices"][index] for index in face]])
        assert volume > 0, "Closed parts must have outward-facing triangles"
    vehicle_bounds = bounds_of(model, False)
    assert abs(vehicle_bounds["max"][0]-vehicle_bounds["min"][0]-DIMS.chassis_length_m) < .01
    assert abs(vehicle_bounds["max"][1]-vehicle_bounds["min"][1]-DIMS.chassis_width_m) < 1e-6
    assert vehicle_bounds["min"][2] >= -1e-6
    assert any(n.get("name")=="implement_lift" for n in doc["nodes"])
    assert all(v["byteOffset"]+v["byteLength"]<=len(binary) for v in doc["bufferViews"])
    return {"triangles":triangle_count,"meshes":len(doc["meshes"]),"bytes":len(raw),
            "whole_model_bounds_author_m":bounds_of(model),
            "vehicle_bounds_author_m":bounds_of(model,False)}


def render_preview(model, destination):
    """Orthographic preview with a depth buffer, using numpy and Pillow only."""
    import numpy as np
    from PIL import Image

    width, height = 1500, 1100
    background = np.array([233, 237, 232], dtype=np.uint8)
    pixels = np.empty((height, width, 3), dtype=np.uint8)
    pixels[:] = background
    depth = np.full((height, width), -np.inf)
    elevation, azimuth = math.radians(24), math.radians(-53)
    eye = np.array([math.cos(elevation)*math.cos(azimuth),
                    math.cos(elevation)*math.sin(azimuth), math.sin(elevation)])
    right = np.array([-math.sin(azimuth), math.cos(azimuth), 0])
    up = np.cross(eye, right)
    camera = np.stack((right, up, eye))
    all_vertices = np.array([v for part in model.parts.values() for v in part["vertices"]])
    projected = all_vertices @ camera.T
    pmin, pmax = projected[:, :2].min(axis=0), projected[:, :2].max(axis=0)
    scale = min((width-120)/(pmax[0]-pmin[0]), (height-120)/(pmax[1]-pmin[1]))
    midpoint = (pmin+pmax)/2
    light = np.array([.5,-.7,1.2]); light /= np.linalg.norm(light)
    for (_, material), part in model.parts.items():
        vertices = np.asarray(part["vertices"])
        screen = vertices @ camera.T
        screen[:, 0] = (screen[:, 0]-midpoint[0])*scale+width/2
        screen[:, 1] = height/2-(screen[:, 1]-midpoint[1])*scale
        base = np.asarray(MATERIALS[material][0][:3])
        for face in part["faces"]:
            points = screen[list(face)]
            xmin = max(0, int(np.floor(points[:, 0].min())))
            xmax = min(width-1, int(np.ceil(points[:, 0].max())))
            ymin = max(0, int(np.floor(points[:, 1].min())))
            ymax = min(height-1, int(np.ceil(points[:, 1].max())))
            if xmax < xmin or ymax < ymin:
                continue
            (x0,y0,z0),(x1,y1,z1),(x2,y2,z2) = points
            denominator = (y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
            if abs(denominator) < 1e-10:
                continue
            yy, xx = np.mgrid[ymin:ymax+1, xmin:xmax+1]
            xx = xx+.5; yy = yy+.5
            a = ((y1-y2)*(xx-x2)+(x2-x1)*(yy-y2))/denominator
            b = ((y2-y0)*(xx-x2)+(x0-x2)*(yy-y2))/denominator
            c = 1-a-b
            z = a*z0+b*z1+c*z2
            local_depth = depth[ymin:ymax+1, xmin:xmax+1]
            mask = (a >= -1e-8)&(b >= -1e-8)&(c >= -1e-8)&(z > local_depth)
            if not mask.any():
                continue
            world = vertices[list(face)]
            normal = np.cross(world[1]-world[0], world[2]-world[0])
            normal /= max(np.linalg.norm(normal), 1e-12)
            shade = .62+.38*max(0, float(normal@light))
            color = np.clip(base*shade*255, 0, 255).astype(np.uint8)
            local_depth[mask] = z[mask]
            pixels[ymin:ymax+1, xmin:xmax+1][mask] = color
    Image.fromarray(pixels).save(destination)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview",action="store_true",help="Render preview.png with numpy and Pillow")
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    model=build_model()
    destination=args.output/"tracked_tiller.glb"
    write_glb(model,destination)
    result=verify_glb(destination,model)
    spec={"purpose":"简化三维显示占位模型，不参与车辆运动或控制计算", "version":1,
          "dimensions":asdict(DIMS),"confirmed_dimensions":["chassis_length_m","chassis_width_m"],
          "illustrative_dimensions":"除底盘长1.6米、宽1.2米外，高度、轮径、电池包络、机具和天线位置均为示意。",
          "reference":"用户提供的履带底盘四视图；前部高电池，后部低甲板和机具连杆。",
          "coordinates":{"units":"m","author":{"x":"forward","y":"left","z":"up"},
                         "gltf":{"x":"forward","y":"up","z":"right"},
                         "author_to_gltf":"(x, y, z) -> (x, z, -y)",
                         "enu_world_to_view":"(east, north, up) -> (east, up, -north)",
                         "enu_yaw_to_gltf_rotation":"rotation about +Y by the ENU yaw angle; model forward is +X"},
          "groups":{name:{"origin_author_m":group["origin"],**group["extras"]} for name,group in model.groups.items()},
          "antenna_note":"前后天线仅为显示提示，不定义主从关系，不能从模型推导UM982安装偏移。",
          "palette_note":"浅灰塑料盖、深色底盘、少量橙色标识为暂定显示配色。",
          "validation":result}
    (args.output/"model_spec.json").write_text(json.dumps(spec,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if args.preview:
        render_preview(model,args.output/"preview.png")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
