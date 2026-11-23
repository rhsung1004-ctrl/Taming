import math, random, os
import bpy
from mathutils import Vector
import kit
from kit import *

def grave_slab():
    rng = random.Random(11)
    body = join([box(0.62, 0.15, 0.72, (0, 0, 0.56)), cyl(0.31, 0.15, (0, 0, 0.92), 40, rot=(R(90), 0, 0))])
    remesh(body, 0.01)
    chip(body, rng, 16, (0.04, 0.1), sharp_deg=35, bite=0.35)       # 새기기 전에 모서리를 친다
    plinth = box(0.84, 0.34, 0.2, (0, 0, 0.1))
    chip(plinth, rng, 9, (0.05, 0.11), bite=0.35)
    body = join([body, plinth])
    cut(body, [box(0.06, 0.06, 0.34, (0, -0.075, 0.86)), box(0.22, 0.06, 0.06, (0, -0.075, 0.93))] +
        [box(w, 0.04, 0.022, (0, -0.075, 0.58 - i * 0.075)) for i, w in enumerate((0.38, 0.3, 0.34))])
    sculpt(body, 0.005, STONE_LAYERS(1.0), seed=1)
    set_mat(body, paint("slab", 'stone', moss=0.7))
    low = decimated(body, 3200)
    return finish("t_slab", [body], [low], size=1024, extr=0.03)

def rock():
    rng = random.Random(5)
    s = sphere(1.0, (0, 0, 0.45), (1.1, 0.85, 0.7), 3)
    slice_rock(s, rng, 22, (0.03, 0.22))
    chip(s, rng, 10, (0.15, 0.35), sharp_deg=15, bite=0.3)
    sculpt(s, 0.012, ROCK_LAYERS(1.2), seed=3)
    set_mat(s, paint("rock", 'stone', moss=0.9, ao=0.6, streaks=0.3))
    low = decimated(s, 2400)
    return finish("t_rock", [s], [low], size=1024, extr=0.05)

def tree():
    rng = random.Random(4)
    verts, edges, radii, dirs = [], [], [], []
    def add(p, r, d):
        verts.append(tuple(p)); radii.append(r); dirs.append(tuple(d))
        return len(verts) - 1
    def grow(si, p, d, length, r, depth):
        n = 6 if depth == 0 else 4
        prev = si
        for i in range(n):
            j = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.3, 0.6))) * (0.25 if depth == 0 else 0.45)
            d = (d + j).normalized()
            p = p + d * (length / n)
            r = r * (0.86 if depth == 0 else 0.76)
            cur = add(p, max(r, 0.018), d)
            edges.append((prev, cur)); prev = cur
            if depth < 3 and i >= 1 and rng.random() < (0.7 if depth == 0 else 0.45):
                side = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.0, 0.7))).normalized()
                grow(cur, p, (d * 0.35 + side).normalized(), length * rng.uniform(0.5, 0.7), r * 0.62, depth + 1)
        if depth < 3:
            for _ in range(2):
                side = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.1, 0.8))).normalized()
                grow(prev, p, (d * 0.5 + side).normalized(), length * 0.45, r * 0.7, depth + 1)
    root = add((0, 0, -0.3), 0.34, (0, 0, 1)); base = add((0, 0, 0.3), 0.27, (0, 0, 1)); edges.append((root, base))
    for a in range(6):
        ang = a * 2 * math.pi / 6 + rng.uniform(-0.3, 0.3)
        dd = Vector((math.cos(ang), math.sin(ang), -0.15)).normalized()
        r1 = add((math.cos(ang) * 0.5, math.sin(ang) * 0.5, 0.05), 0.12, dd)
        r2 = add((math.cos(ang) * 1.1, math.sin(ang) * 1.1, -0.12), 0.05, dd)
        edges.append((base, r1)); edges.append((r1, r2))
    grow(base, Vector((0, 0, 0.3)), Vector((0.1, 0.05, 1)).normalized(), 3.4, 0.26, 0)
    me = bpy.data.meshes.new("skel"); me.from_pydata(verts, edges, [])
    a = me.attributes.new("dir", 'FLOAT_VECTOR', 'POINT')
    for i, d in enumerate(dirs):
        a.data[i].vector = d
    guide = link(bpy.data.objects.new("skel", me))
    t = copy(guide)
    t.modifiers.new('skin', 'SKIN')
    for i, r in enumerate(radii):
        t.data.skin_vertices[0].data[i].radius = (r, r)
        t.data.skin_vertices[0].data[i].use_root = (i == 0)
    sub = t.modifiers.new('sub', 'SUBSURF'); sub.levels = 2
    apply_all(t)
    origin0(t)
    remesh(t, 0.012)
    surface(t, [{'t': 'lumps', 'scale': 1.2, 'amp': 0.03}, {'t': 'bark', 'scale': 9, 'width': 0.1, 'depth': 0.02, 'stretch': 0.1},
                {'t': 'grain', 'scale': 80, 'amp': 0.001}], seed=2, guide=guide)
    delete(guide)
    set_mat(t, paint("bark", 'bark', moss=0.45, moss_color=MOSS_DEAD, dirt=0.3, streaks=0.0, streak_dir='grain', cracks=0.0, edge=0.6))
    low = decimated(t, 7000)
    return finish("t_tree", [t], [low], size=1024, extr=0.03)

def grass():
    rng = random.Random(9)
    verts, faces, cols = [], [], []
    for b in range(34):
        ang = rng.uniform(0, 6.28); rr = rng.uniform(0, 0.22)
        x0, y0 = math.cos(ang) * rr, math.sin(ang) * rr
        h = rng.uniform(0.25, 0.65); w = rng.uniform(0.012, 0.022)
        lean = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)).normalized() * rng.uniform(0.05, 0.25)
        face = rng.uniform(0, 6.28); fx, fy = math.cos(face), math.sin(face)
        dead = rng.random() < 0.25
        segs = 4
        base = len(verts)
        for k in range(segs + 1):
            t = k / segs
            cx = x0 + lean.x * t * t * h; cy = y0 + lean.y * t * t * h; cz = h * t
            ww = w * (1 - t) ** 0.9 + 0.001
            verts += [(cx - fy * ww, cy + fx * ww, cz), (cx + fy * ww, cy - fx * ww, cz)]
            if dead:
                c = (0.32 + 0.25 * t, 0.3 + 0.2 * t, 0.17 + 0.08 * t)
            else:
                c = (0.07 + 0.12 * t, 0.13 + 0.2 * t, 0.12 + 0.12 * t)
            cols += [(c[0], c[1], c[2], t), (c[0], c[1], c[2], t)]
        for k in range(segs):
            i = base + k * 2
            faces.append((i, i + 1, i + 3, i + 2))
    o = mesh_from("grass", verts, faces)
    vcolor(o, lambda p, n, i: cols[i])
    set_uv(o, lambda fi, k, co: atlas_uv('solid', 0.5, 0.5))
    set_mat(o, foliage_mat())
    return finish_foliage("t_grass", [o])

def ivy_slab():
    slab = kit.load_fbx("t_slab") if os.path.exists(os.path.join(kit.OUT, "t_slab.fbx")) else grave_slab()
    tgt = copy(slab); tgt.location = (0, 0, 0); tgt.hide_render = False
    parts = ivy(tgt, (0.25, -0.1, 0.02), seed=3, length=1.6, leaf=0.045, leaf_prob=0.25, gravity=0.6, adhesion=0.6)
    parts += ivy(tgt, (-0.3, 0.1, 0.02), seed=7, length=1.0, leaf=0.04, leaf_prob=0.25, gravity=0.6, adhesion=0.6)
    delete(tgt)
    base = copy(slab); base.location = (0, 0, 0)
    o = join([base] + parts)
    origin0(o)
    o.name = "t_ivyslab_LOD0"; o.hide_render = True
    kit.LOWS["t_ivyslab"] = o
    return o


BUILDERS = [("t_slab", grave_slab), ("t_rock", rock), ("t_grass", grass)]
META = {"t_slab": {"kind": "prop"}, "t_rock": {"kind": "tree"}, "t_grass": {"kind": "detail"}}
