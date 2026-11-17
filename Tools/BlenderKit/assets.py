# 묘지 소품 정의
import math, random
from mathutils import Vector
import bpy
from kit import *
R = math.radians

STONE = dict(dark=(0.07, 0.07, 0.115), light=(0.3, 0.3, 0.41), edge=(0.62, 0.64, 0.82))
STONE_PALE = dict(dark=(0.1, 0.1, 0.15), light=(0.38, 0.38, 0.48), edge=(0.72, 0.74, 0.9))
IRON = dict(dark=(0.02, 0.02, 0.03), light=(0.065, 0.06, 0.08), edge=(0.14, 0.14, 0.19))
BARK = dict(dark=(0.035, 0.028, 0.04), light=(0.12, 0.095, 0.11), edge=(0.26, 0.22, 0.27))

def stone(name, moss=0.75, pale=False, dirt=0.6, ao=0.3):
    return surface_mat(name, moss=moss, dirt=dirt, ao_dist=ao, **(STONE_PALE if pale else STONE))

def iron(name):
    return surface_mat(name, dirt=0.0, ao_dist=0.08, cracks=0.0, **IRON)

def stone_asset(name, parts, voxel, big, bigs, small, smalls, tris, seed, mat=None, hard=(), glows=(), size=1024, extr=0.03, carve=()):
    s = join(parts)
    sculpt(s, voxel, big, bigs, small, smalls, seed, carve)
    s.data.materials.clear()
    s.data.materials.append(mat or stone(name + "_src"))
    low_parts = [decimated(s, tris)]
    highs = [s]
    for h in hard:
        origin0(h)
        flat_shade(h)
        low_parts.append(copy(h))
        highs.append(h)
    return finish(name, highs, low_parts, glows, size, extr)

# ───────────── 묘비 ─────────────
def grave_slab_a():
    rng = random.Random(11)
    body = box(0.62, 0.15, 0.72, (0, 0, 0.56))
    top = cyl(0.31, 0.15, (0, 0, 0.92), 32, rot=(R(90), 0, 0))
    plinth = box(0.84, 0.34, 0.2, (0, 0, 0.1))
    carve = [box(0.055, 0.08, 0.34, (0, -0.075, 0.86)), box(0.22, 0.08, 0.055, (0, -0.075, 0.93))]
    for i, w in enumerate((0.38, 0.3, 0.34)):
        carve.append(box(w, 0.05, 0.02, (0, -0.075, 0.58 - i * 0.075)))
    for p in [(-0.3, -0.06, 0.95), (0.31, 0.05, 0.62), (0.2, -0.07, 1.2), (-0.31, 0.06, 0.3), (0.42, -0.17, 0.2), (-0.4, 0.17, 0.18)]:
        r = rng.uniform(0.05, 0.09)
        carve.append(sphere(r, loc=p, scale=(rng.uniform(0.7, 1.3), rng.uniform(0.7, 1.3), rng.uniform(0.7, 1.3)), sub=1))
    return stone_asset("grave_slab_a", [body, top, plinth], 0.011, 0.03, 0.5, 0.008, 0.05, 2600, 1, carve=carve)

def grave_slab_b():
    rng = random.Random(23)
    body = box(0.7, 0.16, 1.0, (0, 0, 0.66), rot=(R(-5), R(4), 0))
    cut(body, box(1.4, 0.6, 0.7, (0.12, 0, 1.38), rot=(0, R(24), R(8))))
    cut(body, torus(0.16, 0.022, (0, -0.085, 0.72), rot=(R(90), 0, 0)))
    for i, w in enumerate((0.42, 0.36)):
        cut(body, box(w, 0.05, 0.02, (0, -0.09, 0.44 - i * 0.08), rot=(R(-5), R(4), 0)))
    chips(body, [(-0.34, -0.06, 0.9), (0.33, 0.02, 0.5), (-0.1, -0.07, 1.1), (0.34, -0.06, 0.25)], rng, 0.05, 0.11)
    plinth = box(0.9, 0.36, 0.18, (0, 0, 0.09), rot=(0, 0, R(3)))
    frag = box(0.36, 0.16, 0.26, (0.62, -0.3, 0.07), rot=(R(78), R(12), R(34)))
    chips(frag, [(0.7, -0.3, 0.15)], rng, 0.06, 0.1)
    return stone_asset("grave_slab_b", [body, plinth, frag], 0.011, 0.035, 0.5, 0.009, 0.05, 2800, 2, stone("slab_b", 0.9))

def grave_cross():
    rng = random.Random(5)
    v = box(0.17, 0.14, 1.3, (0, 0, 1.03))
    arm = box(0.7, 0.14, 0.17, (0, 0, 1.25))
    ring = torus(0.27, 0.05, (0, 0, 1.25), rot=(R(90), 0, 0))
    chips(arm, [(0.35, -0.06, 1.3), (-0.33, 0.06, 1.2)], rng, 0.04, 0.07)
    chips(v, [(0.08, -0.07, 1.66), (-0.08, 0.06, 0.6)], rng, 0.04, 0.07)
    b1 = box(0.66, 0.52, 0.2, (0, 0, 0.1))
    b2 = box(0.44, 0.36, 0.2, (0, 0, 0.3))
    chips(b1, [(0.33, -0.26, 0.2), (-0.3, 0.26, 0.12)], rng, 0.05, 0.09)
    return stone_asset("grave_cross", [v, arm, ring, b1, b2], 0.011, 0.028, 0.5, 0.008, 0.05, 3200, 3, stone("cross", 0.6, pale=True))

def grave_obelisk():
    rng = random.Random(8)
    shaft = cyl(0.3, 1.55, (0, 0, 1.12), 4, r2=0.2, rot=(0, 0, R(45)))
    tip = cyl(0.2, 0.3, (0, 0, 2.04), 4, r2=0.0, rot=(0, 0, R(45)))
    base = box(0.64, 0.64, 0.24, (0, 0, 0.12))
    base2 = box(0.5, 0.5, 0.14, (0, 0, 0.3))
    cut(shaft, box(0.14, 0.08, 0.14, (0, -0.2, 1.3), rot=(0, R(45), 0)))
    for i in range(3):
        cut(shaft, box(0.24, 0.06, 0.018, (0, -0.2, 1.02 - i * 0.07)))
    chips(shaft, [(0.2, -0.2, 0.6), (-0.17, -0.17, 1.6), (0.16, 0.16, 1.2)], rng, 0.04, 0.08)
    chips(base, [(0.32, -0.32, 0.24), (-0.32, 0.3, 0.1)], rng, 0.05, 0.1)
    return stone_asset("grave_obelisk", [shaft, tip, base, base2], 0.012, 0.03, 0.6, 0.008, 0.05, 2400, 4)

# ───────────── 바위 ─────────────
def rock(name, scale, seed, tris):
    s = sphere(1.0, (0, 0, scale[2] * 0.35), scale, 4)
    k = max(scale)
    return stone_asset(name, [s], 0.03 * k, 0.5 * k, 0.75 * k, 0.07 * k, 0.16 * k, tris, seed, stone(name, 0.9, dirt=0.8, ao=0.5), size=1024, extr=0.05 * k)

# ───────────── 죽은 나무 ─────────────
def dead_tree(name, seed, height, tris):
    rng = random.Random(seed)
    verts, edges, radii = [], [], []

    def add(p, r):
        verts.append(tuple(p)); radii.append(r)
        return len(verts) - 1

    def grow(start_i, p, d, length, r, depth):
        n = 5 if depth == 0 else 4
        prev = start_i
        for i in range(n):
            jitter = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.4, 0.6))) * (0.22 if depth == 0 else 0.42)
            d = (d + jitter).normalized()
            p = p + d * (length / n)
            r = r * (0.86 if depth == 0 else 0.78)
            cur = add(p, max(r, 0.022))
            edges.append((prev, cur))
            prev = cur
            if depth < 3 and i >= 1 and rng.random() < (0.75 if depth == 0 else 0.5):
                side = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.0, 0.7))).normalized()
                grow(cur, p, (d * 0.35 + side).normalized(), length * rng.uniform(0.5, 0.7), r * 0.62, depth + 1)
        if depth < 3:
            for _ in range(2):
                side = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.1, 0.8))).normalized()
                grow(prev, p, (d * 0.5 + side).normalized(), length * 0.5, r * 0.7, depth + 1)

    root = add((0, 0, -0.25), 0.3)
    base = add((0, 0, 0.25), 0.25)
    edges.append((root, base))
    for a in range(5):   # 뿌리
        ang = a * 2 * math.pi / 5 + rng.uniform(-0.3, 0.3)
        r1 = add((math.cos(ang) * 0.45, math.sin(ang) * 0.45, 0.02), 0.1)
        r2 = add((math.cos(ang) * 0.95, math.sin(ang) * 0.95, -0.12), 0.045)
        edges.append((base, r1)); edges.append((r1, r2))
    grow(base, Vector((0, 0, 0.25)), Vector((rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), 1)).normalized(), height * 0.6, 0.24, 0)

    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    o.modifiers.new('skin', 'SKIN')
    for i, r in enumerate(radii):
        me.skin_vertices[0].data[i].radius = (r, r)
        me.skin_vertices[0].data[i].use_root = (i == 0)
    sub = o.modifiers.new('sub', 'SUBSURF'); sub.levels = 2
    apply_all(o)
    bark = surface_mat(name + "_bark", moss=0.35, moss_color=(0.09, 0.13, 0.1), dirt=0.3, streak=True, ao_dist=0.25, cracks=0.0, **BARK)
    return stone_asset(name, [o], 0.016, 0.05, 0.35, 0.012, 0.05, tris, seed, bark, size=1024, extr=0.03)

# ───────────── 영혼 등불 ─────────────
def lantern():
    base = join([cyl(0.2, 0.22, (0, 0, 0.11), 12, r2=0.16), cyl(0.12, 0.2, (0, 0, 0.3), 12, r2=0.09)])
    im = iron("lantern_iron")
    hard = [cyl(0.04, 2.5, (0, 0, 1.55), 8, r2=0.03), box(0.56, 0.035, 0.04, (0.26, 0, 2.72)),
            box(0.42, 0.028, 0.03, (0.14, 0, 2.52), rot=(0, R(-38), 0)), cyl(0.05, 0.1, (0, 0, 2.84), 8, r2=0.0),
            cyl(0.007, 0.2, (0.5, 0, 2.62), 6), cyl(0.13, 0.1, (0.5, 0, 2.49), 8, r2=0.03), cyl(0.11, 0.02, (0.5, 0, 2.14), 8)]
    for a in range(4):
        ang = a * math.pi / 2 + math.pi / 4
        hard.append(cyl(0.008, 0.32, (0.5 + math.cos(ang) * 0.095, math.sin(ang) * 0.095, 2.29), 6))
    h = join(hard)
    h.data.materials.clear(); h.data.materials.append(im)
    crystal = sphere(0.062, (0.5, 0, 2.28), (1, 1, 1.75), 1)
    return stone_asset("lantern", [base], 0.008, 0.02, 0.3, 0.006, 0.04, 500, 6, hard=[h], glows=[crystal], size=1024, extr=0.015)

# ───────────── 봉인의 제단 ─────────────
def altar():
    rng = random.Random(31)
    d1 = cyl(3.0, 0.3, (0, 0, 0.15), 48)
    for i in range(12):
        a = i * math.pi / 6
        cut(d1, box(0.05, 1.0, 0.16, (math.cos(a) * 2.6, math.sin(a) * 2.6, 0.27), rot=(0, 0, a + math.pi / 2)))
    chips(d1, [(math.cos(a) * 3.0, math.sin(a) * 3.0, 0.28) for a in (0.4, 1.9, 3.3, 4.6, 5.5)], rng, 0.12, 0.25)
    d2 = cyl(2.15, 0.26, (0, 0, 0.43), 40)
    chips(d2, [(math.cos(a) * 2.15, math.sin(a) * 2.15, 0.54) for a in (1.0, 2.8, 4.9)], rng, 0.1, 0.2)
    d3 = cyl(1.2, 0.2, (0, 0, 0.66), 32)
    ped = cyl(0.46, 0.95, (0, 0, 1.23), 8, r2=0.34)
    top = box(0.98, 0.98, 0.15, (0, 0, 1.78), rot=(0, 0, R(45)))
    chips(top, [(0.6, 0.1, 1.82), (-0.3, -0.55, 1.75)], rng, 0.07, 0.12)
    glows = [torus(1.68, 0.03, (0, 0, 0.565), seg=64), torus(0.62, 0.02, (0, 0, 0.762), seg=48)]
    for i, (x, y, h, tilt) in enumerate([(0, 0, 0.75, 0), (0.17, 0.08, 0.5, 18), (-0.16, 0.1, 0.42, -22), (0.02, -0.19, 0.46, 15), (-0.1, -0.12, 0.3, -30)]):
        c = join([cyl(0.1, h * 0.75, (0, 0, h * 0.375), 6, r2=0.085), cyl(0.085, h * 0.25, (0, 0, h * 0.875), 6, r2=0.0)])
        origin0(c)
        c.rotation_euler = (R(tilt * 0.6), R(tilt), i * 1.1)
        c.location = (x, y, 1.84)
        glows.append(xf_loc(c))
    return stone_asset("altar", [d1, d2, d3, ped, top], 0.03, 0.05, 1.3, 0.014, 0.12, 9000, 7, stone("altar", 0.7, ao=0.5), glows=glows, size=2048, extr=0.06)

def xf_loc(o):
    act(o)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o

# ───────────── 기둥 ─────────────
def pillar(name, broken, seed):
    rng = random.Random(seed)
    base = join([box(0.74, 0.74, 0.24, (0, 0, 0.12)), cyl(0.33, 0.14, (0, 0, 0.31), 16, r2=0.29)])
    chips(base, [(0.37, -0.37, 0.22), (-0.37, 0.3, 0.1)], rng, 0.07, 0.12)
    h = 1.7 if broken else 3.1
    shaft = cyl(0.27, h, (0, 0, 0.38 + h / 2), 14, r2=0.27 - 0.016 * h)
    parts = [base, shaft]
    if broken:
        cut(shaft, box(1.2, 1.2, 0.7, (0.1, 0, 0.38 + h + 0.12), rot=(R(14), R(-22), 0)))
        chips(shaft, [(0.25, 0.05, 1.3), (-0.2, -0.16, 0.9)], rng, 0.08, 0.14)
        parts.append(cyl(0.25, 0.75, (0.95, -0.35, 0.25), 14, r2=0.24, rot=(R(90), 0, R(63))))
        parts.append(cyl(0.24, 0.42, (-0.7, 0.75, 0.2), 14, r2=0.235, rot=(R(84), 0, R(-20))))
    else:
        chips(shaft, [(0.26, 0, 1.5), (-0.18, 0.18, 2.4), (0, -0.25, 0.8)], rng, 0.06, 0.11)
        parts += [cyl(0.25, 0.12, (0, 0, 3.52), 16, r2=0.34), box(0.72, 0.72, 0.2, (0, 0, 3.68))]
    return stone_asset(name, parts, 0.016, 0.035, 0.7, 0.01, 0.07, 3500, seed, stone(name, 0.5, pale=True))

# ───────────── 납골당 ─────────────
def crypt():
    rng = random.Random(77)
    plat = box(10.6, 7.0, 0.6, (0, 0.2, 0.3))
    chips(plat, [(5.3, -3.3, 0.5), (-5.3, -3.0, 0.6), (-2.0, -3.3, 0.6), (5.3, 2.0, 0.5)], rng, 0.2, 0.4)
    steps = [box(4.4, 1.3, 0.2, (0, -3.7, 0.1)), box(3.8, 0.8, 0.2, (0, -3.55, 0.3)), box(3.2, 0.5, 0.2, (0, -3.45, 0.5))]
    body = box(8.8, 4.6, 4.2, (0, 0.6, 2.7))
    cut(body, box(1.9, 1.2, 2.5, (0, -1.7, 1.85)))
    cut(body, cyl(0.95, 1.2, (0, -1.7, 3.1), 32, rot=(R(90), 0, 0)))
    for sx in (-1, 1):   # 옆 벽감
        cut(body, box(1.1, 0.5, 2.0, (sx * 3.0, -1.7, 2.4)))
        cut(body, cyl(0.55, 0.5, (sx * 3.0, -1.7, 3.4), 24, rot=(R(90), 0, 0)))
    chips(body, [(4.4, -1.7, 1.2), (-4.4, -1.7, 3.9), (4.4, 2.9, 4.0), (-2.2, -1.7, 4.6)], rng, 0.2, 0.4)
    cornice = box(9.7, 6.3, 0.34, (0, 0.0, 4.97))
    roof = prism([(-5.0, 5.14), (5.0, 5.14), (0, 6.9)], -3.3, 3.2)
    cut(roof, prism([(-3.5, 5.36), (3.5, 5.36), (0, 6.5)], -3.6, -3.1))      # 박공의 움푹한 삼각면
    parts = [plat, body, cornice, roof] + steps
    for x in (-3.9, -1.55, 1.55, 3.9):
        parts += [box(0.86, 0.86, 0.26, (x, -2.7, 0.73)), cyl(0.33, 3.7, (x, -2.7, 2.7), 14, r2=0.28),
                  cyl(0.28, 0.14, (x, -2.7, 4.6), 14, r2=0.4), box(0.86, 0.86, 0.16, (x, -2.7, 4.74))]
    for sx in (-1, 1):
        parts.append(box(0.7, 1.0, 3.9, (sx * 4.55, 0.6, 2.55)))
        parts.append(box(0.8, 1.1, 0.3, (sx * 4.55, 0.6, 4.55)))
    # 박공 위의 해골 장식
    skull = sphere(0.36, (0, -3.12, 5.95), (1, 0.85, 1.05), 3)
    cut(skull, sphere(0.1, (-0.14, -3.4, 5.98), sub=2))
    cut(skull, sphere(0.1, (0.14, -3.4, 5.98), sub=2))
    parts += [skull, box(0.3, 0.3, 0.22, (0, -3.2, 5.66))]
    door = join([box(1.86, 0.12, 3.3, (0, -1.25, 2.25)), box(0.06, 0.16, 3.3, (0, -1.3, 2.25)),
                 box(1.86, 0.16, 0.08, (0, -1.3, 1.5)), box(1.86, 0.16, 0.08, (0, -1.3, 2.8)),
                 torus(0.1, 0.02, (-0.3, -1.34, 2.1), rot=(R(90), 0, 0), seg=16), torus(0.1, 0.02, (0.3, -1.34, 2.1), rot=(R(90), 0, 0), seg=16)])
    door.data.materials.clear(); door.data.materials.append(iron("crypt_door"))
    glow = [sphere(0.075, (-0.14, -3.33, 5.98), sub=1), sphere(0.075, (0.14, -3.33, 5.98), sub=1)]
    return stone_asset("crypt", parts, 0.045, 0.06, 1.6, 0.02, 0.16, 16000, 9, stone("crypt", 0.8, ao=0.7), hard=[door], glows=glow, size=2048, extr=0.1)

# ───────────── 철 울타리 ─────────────
def fence():
    rng = random.Random(13)
    posts = []
    for x in (-1.5, 1.5):
        p = box(0.34, 0.34, 1.35, (x, 0, 0.675))
        chips(p, [(x + 0.17, -0.17, 1.1), (x - 0.17, 0.17, 0.5)], rng, 0.05, 0.09)
        posts += [p, box(0.42, 0.42, 0.1, (x, 0, 1.4)), cyl(0.26, 0.24, (x, 0, 1.57), 4, r2=0.0, rot=(0, 0, R(45)))]
    hard = [box(2.7, 0.03, 0.045, (0, 0, 0.32)), box(2.7, 0.03, 0.045, (0, 0, 1.08))]
    for i in range(11):
        if i == 7:
            continue                                   # 빠진 창살
        x = -1.2 + i * 0.24
        lean = R(14) if i == 3 else R(rng.uniform(-2, 2))
        hh = 1.3 if i % 2 == 0 else 1.18
        hard.append(cyl(0.014, hh, (x, 0, hh / 2 + 0.06), 6, rot=(0, lean, 0)))
        hard.append(cyl(0.032, 0.14, (x + math.sin(lean) * hh / 2, 0, hh + 0.12), 4, r2=0.0, rot=(0, lean, R(45))))
    h = join(hard)
    h.data.materials.clear(); h.data.materials.append(iron("fence_iron"))
    return stone_asset("fence", posts, 0.012, 0.03, 0.5, 0.008, 0.05, 1500, 14, hard=[h], size=1024, extr=0.015)

# ───────────── 무너진 아치 ─────────────
def arch_ruin():
    rng = random.Random(41)
    parts = []
    def brick(w, d, h, loc, rot=(0, 0, 0)):
        j = lambda a: a * rng.uniform(0.965, 1.0)
        b = box(j(w) - 0.012, j(d), h - 0.008, loc, (rot[0] + R(rng.uniform(-2, 2)), rot[1] + R(rng.uniform(-2, 2)), rot[2] + R(rng.uniform(-3, 3))))
        parts.append(b)
    for sx in (-1, 1):
        for row in range(9):
            z = 0.16 + row * 0.32
            if row % 2 == 0:
                brick(0.84, 0.56, 0.32, (sx * 1.75, 0, z))
            else:
                brick(0.44, 0.56, 0.32, (sx * 1.55, 0, z)); brick(0.44, 0.56, 0.32, (sx * 1.97, 0, z))
    n = 13
    for i in range(n):
        if i in (8, 9):
            continue                                   # 무너진 구간
        a = math.pi * (i + 0.5) / n
        brick(0.435, 0.56, 0.56, (math.cos(a) * 1.72, 0, 2.9 + math.sin(a) * 1.72), rot=(0, -(a - math.pi / 2), 0))
    for (x, y, rz) in [(-0.6, -0.7, 20), (-1.1, -1.2, 70), (-0.2, 0.9, 40), (-2.6, -0.6, 10), (0.5, -1.0, 55)]:
        brick(0.46, 0.56, 0.5, (x, y, 0.2), rot=(R(rng.uniform(-25, 25)), R(rng.uniform(-20, 20)), R(rz)))
    return stone_asset("arch_ruin", parts, 0.018, 0.03, 0.6, 0.012, 0.07, 9000, 15, stone("arch", 0.85, ao=0.2), size=2048, extr=0.03)

BUILDERS = [
    ("grave_slab_a", grave_slab_a), ("grave_slab_b", grave_slab_b), ("grave_cross", grave_cross), ("grave_obelisk", grave_obelisk),
    ("rock_a", lambda: rock("rock_a", (0.9, 0.7, 0.55), 21, 1400)), ("rock_b", lambda: rock("rock_b", (1.7, 1.3, 1.0), 22, 2200)),
    ("rock_c", lambda: rock("rock_c", (0.55, 0.5, 0.3), 23, 800)),
    ("dead_tree_a", lambda: dead_tree("dead_tree_a", 4, 5.5, 7000)), ("dead_tree_b", lambda: dead_tree("dead_tree_b", 9, 4.2, 6000)),
    ("lantern", lantern), ("altar", altar), ("pillar_a", lambda: pillar("pillar_a", False, 51)), ("pillar_b", lambda: pillar("pillar_b", True, 52)),
    ("crypt", crypt), ("fence", fence), ("arch_ruin", arch_ruin),
]
