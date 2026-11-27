# 땅 잡동사니 묶음 (clutter) — 지형 detail 메쉬 6종 (k9, 2단계 C)
#   pebbles_a 반쯤 묻힌 작은 돌 무리 / twigs_a 마른 잔가지·껍질 조각 / bones_bits 흙빛 작은 뼈 조각
#   leaf_litter 마른 잎·이끼 낀 흙 얼룩 / shrub_dry 마른 가시덤불 / mushrooms_glow 갓 밑이 청록으로 희미하게 빛나는 작은 버섯 무리
#
# 왜: 눈높이(1.7 m)에서 앞 0~30 m 가 '풀만 깔린 둔덕'으로 보인다 (direction.md 2단계 C 결정 2).
#   큰 소품을 더 뿌리지 않고, 풀처럼 지형이 인스턴싱으로 그리는 작은 메쉬로 풀 사이 땅을 깬다 (그리는 물체 예산을 쓰지 않는다).
#
# Unity 로 가는 길: META kind 'detail' → NecroProps.BuildDetailRoot 가 프리팹 뿌리에 LOD0 메쉬 하나(MeshFilter·MeshRenderer)만 둔다
#   → NecroWorldBuilder 가 DetailPrototype(usePrototypeMesh, useInstancing) 으로 지형에 깐다.
#   풀(foliage 묶음)과 다른 점: 재질이 Foliage(아틀라스) 가 아니라 Main(굽기 텍스처, URP Lit, 인스턴싱 켬) 이다
#   (mushrooms_glow 만 Main + Glow_Spirit). 그래서 Foliage_Detail 의 거리 축소(70 m 앞에서 오그라듦)가 없다 — 지형 detail 거리에서 끊긴다.
#
# 규칙 (모두): 프리팹 뿌리에 메쉬 하나 = LOD 없음 (finish3 lod1=None), collider none, shadows false, 삼각형 400 이하, 텍스처 1024 이하.
#   지형 detail 은 META.sink 를 쓰지 않는다 (인스턴스가 땅 높이에 바로 놓인다) → 묻힌 모양을 메쉬 자체에 넣는다:
#   z<0 부분은 땅속, 저폴리는 z = GROUND_CUT 아래를 잘라 버린다 (보이지 않는 밑면에 삼각형을 쓰지 않는다).
#   비탈에서 지형 detail 은 경사의 절반만 기운다 (alignToGround 0.5) → 넓고 납작한 것(leaf_litter)은 가장자리를 땅속으로 내리고,
#   META max_slope(권장 최대 경사) 를 적는다.
#
# 만드는 방식 (v3 와 같은 흐름, 작은 것에 맞춰 단순하게):
#   깨끗한 저폴리를 먼저 직접 만든다 (볼록 껍질 돌, 3~4각 관, 원판) → 같은 모양의 고폴리(관은 면을 늘리고, 돌은 carve)
#   → paint3 손칠 (회갈·올리브, 이끼는 최종 명도 0.2 이하) → finish3(lod1=None) 로 우리 굽기.
#   색은 지형 텍스처(ground_dirt·ground_leaves·ground_grass) 와 섞이게 회갈색 쪽, 파랑을 섞지 않는다 (밤 보라 조명이 이미 더한다).
import math, random, os
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
from mathutils import noise as mnoise
import kit
from kit import *
import assets_graves as G
import assets_bones as B

if kit.sc is not None:
    foliage_mat()
    for _g in GLOW:
        glow_mat(_g)

R = math.radians
GROUND_CUT = -0.035          # 저폴리는 이 높이 아래를 지운다 (지형이 덮는다)
MAX_TRIS = 400

# 색 묶음 (어두운, 밝은, 닳은 모서리) — 선형 값. 땅(ground_dirt sRGB 평균 0.31·0.28·0.29) 보다 조금 밝거나 비슷하게
PEBBLE = ((0.05, 0.046, 0.042), (0.24, 0.222, 0.2), (0.33, 0.31, 0.285))       # 회갈 자갈
DRYWOOD = ((0.032, 0.027, 0.023), (0.19, 0.163, 0.135), (0.3, 0.27, 0.235))    # 마른 잔가지 (바랜 회갈)
BARKCHIP = ((0.022, 0.018, 0.016), (0.12, 0.1, 0.085), (0.22, 0.2, 0.18))      # 떨어진 껍질 (더 짙다)
OLDBONE = ((0.06, 0.052, 0.04), (0.3, 0.27, 0.21), (0.4, 0.37, 0.31))          # 흙빛 오래된 뼈 (상아색 아님)
SHRUB = ((0.022, 0.019, 0.018), (0.13, 0.112, 0.1), (0.23, 0.21, 0.19))        # 마른 가시덤불 (짙은 회갈)
CAP = ((0.03, 0.024, 0.02), (0.15, 0.12, 0.09), (0.24, 0.21, 0.17))            # 버섯 갓 (짙은 갈색)
STEM = ((0.08, 0.075, 0.068), (0.3, 0.29, 0.27), (0.36, 0.35, 0.33))          # 버섯 대 (바랜 회백, 흰색 아님)
MOSS_DARK = (0.02, 0.032, 0.015)       # 짙은 올리브 이끼 (최종 sRGB 명도 0.2 이하, hue 95~110°)
SHADOW_EARTH = (0.11, 0.095, 0.1)      # paint3 틈 그늘 (보라 대신 흙빛)


def lerp(a, b, t):
    return a + (b - a) * t


def obj(bm, name, recalc=False):
    """bmesh → 장면 객체. 관·원판·잎은 감는 방향을 직접 맞춰 만들었으므로 법선을 다시 계산하지 않는다
    (열린 껍질(버섯 갓·원판)은 recalc 가 아래로 뒤집을 수 있다). 볼록 껍질 돌 등 닫힌 것만 recalc=True"""
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    kit.sc.collection.objects.link(o)
    return o


def cut_below(o, z=GROUND_CUT):
    """z 아래 면을 평면으로 잘라 버린다 (막지 않는다 — 땅속 밑면)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector((0, 0, z)), plane_no=Vector((0, 0, 1)), clear_inner=True)
    bm.to_mesh(o.data); bm.free(); o.data.update()
    return o


def drop_down_faces(o, nz=-0.55, zmax=0.02):
    """아래를 보는 면 중 땅 가까이 있는 것 (누운 가지의 밑면) 을 지운다"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    kill = [f for f in bm.faces if f.normal.z < nz and f.calc_center_median().z < zmax]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data); bm.free(); o.data.update()
    return o


def rmf(pts, up=None):
    """경로 점마다 (접선 t, 옆 b, 위 u) 틀 (오른손: b × u = t → tube 의 면이 바깥을 본다).
    up 을 주면 그 방향을 기준으로 (누운 가지: 단면의 한 면이 늘 아래), 없으면 평행 이동 틀"""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    T = []
    for i in range(n):
        t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        T.append(t.normalized() if t.length > 1e-9 else Vector((1, 0, 0)))
    F = []
    if up is not None:
        up = Vector(up)
        for t in T:
            b = up.cross(t)
            if b.length < 1e-6:
                b = t.orthogonal()
            b.normalize()
            F.append((t, b, t.cross(b).normalized()))      # u = t × b 는 up 쪽을 본다
        return F
    b = T[0].orthogonal().normalized()
    for t in T:
        b = (b - t * b.dot(t))
        if b.length < 1e-6:
            b = t.orthogonal()
        b.normalize()
        F.append((t, b, t.cross(b).normalized()))
    return F


def tube(pts, radii, sides=4, roll=45.0, up=None, cap0=True, cap1=True, tip=False, squash=1.0, bm=None, wob=None):
    """경로를 따라 다각 관. radii: 점마다 반지름, tip: 끝을 한 점으로 모은다 (가시·가지 끝), squash: 위 방향 단면 배율.
    wob(i, k) → 반지름 배율 (껍질 울퉁불퉁). 돌려주는 bm 에 덧붙인다"""
    bm = bm or bmesh.new()
    pts = [Vector(p) for p in pts]
    F = rmf(pts, up)
    rings = []
    n = len(pts)
    for i, (p, (t, b, u)) in enumerate(zip(pts, F)):
        if tip and i == n - 1:
            rings.append([bm.verts.new(p)])
            continue
        r = radii[i]
        ring = []
        for k in range(sides):
            a = R(roll) + 2 * math.pi * k / sides
            w = wob(i, k) if wob else 1.0
            ring.append(bm.verts.new(p + (b * math.cos(a) + u * math.sin(a) * squash) * r * w))
        rings.append(ring)
    for i in range(n - 1):
        r0, r1 = rings[i], rings[i + 1]
        for k in range(sides):
            j = (k + 1) % sides
            if len(r1) == 1:
                bm.faces.new((r0[k], r0[j], r1[0]))
            else:
                bm.faces.new((r0[k], r0[j], r1[j], r1[k]))
    if cap0 and len(rings[0]) > 2:
        bm.faces.new(rings[0][::-1])
    if cap1 and len(rings[-1]) > 2:
        bm.faces.new(rings[-1])
    return bm


def resample(pts, step):
    """꺾인 선을 step 간격으로 다시 나눈다 (고폴리 관용)"""
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        L = (b - a).length
        k = max(1, int(math.ceil(L / step)))
        for i in range(1, k + 1):
            out.append(a.lerp(b, i / k))
    return out


def smooth_path(pts, n=2):
    """체이킨 꺾인 선 다듬기 (끝점은 그대로)"""
    pts = [Vector(p) for p in pts]
    for _ in range(n):
        q = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            q += [a.lerp(b, 0.25), a.lerp(b, 0.75)]
        q.append(pts[-1])
        pts = q
    return pts


def interp_r(radii, m):
    """점 개수가 바뀐 경로에 반지름을 늘려 맞춘다"""
    n = len(radii)
    out = []
    for i in range(m):
        s = i / max(1, m - 1) * (n - 1)
        a = int(math.floor(s)); b = min(n - 1, a + 1)
        out.append(lerp(radii[a], radii[b], s - a))
    return out


def tri_total(objs):
    return sum(tri_count(o) for o in objs)


def report(name, low):
    n = tri_count(low)
    print("CLUTTER", name, "tris", n, "dims", tuple(round(v, 3) for v in low.dimensions), "zmin", round(min((low.matrix_world @ v.co).z for v in low.data.vertices), 3))
    if n > MAX_TRIS:
        raise RuntimeError("%s: 삼각형 %d > %d" % (name, n, MAX_TRIS))


def set_group(o, g):
    """저폴리 면 속성 'bgrp' = g (finish 의 bake_groups: 그 면은 g 번 원본에만 굽는다 — 가지가 만나는 곳에서 광선이 이웃 가지를 맞지 않게)"""
    me = o.data
    a = me.attributes.get('bgrp') or me.attributes.new('bgrp', 'INT', 'FACE')
    for i in range(len(me.polygons)):
        a.data[i].value = g
    return o


def tag_verts(o, g, name='hg'):
    """고폴리 정점 속성 (합쳐서 조각한 뒤 split_by 로 다시 나눈다)"""
    me = o.data
    a = me.attributes.get(name) or me.attributes.new(name, 'INT', 'POINT')
    for i in range(len(me.vertices)):
        a.data[i].value = g
    return o


def split_by(o, n, name='hg'):
    """정점 속성 name 값마다 사본 하나 → [무리 0, …, 무리 n-1] (원본은 지운다)"""
    outs = []
    for g in range(n):
        c = copy(o)
        bm = bmesh.new(); bm.from_mesh(c.data)
        lay = bm.verts.layers.int.get(name)
        kill = [v for v in bm.verts if v[lay] != g]
        if kill:
            bmesh.ops.delete(bm, geom=kill, context='VERTS')
        bm.to_mesh(c.data); bm.free(); c.data.update()
        outs.append(c)
    delete(o)
    return outs


def group_by_nearest(o, srcs, name='hg'):
    """리메시(carve)로 속성이 사라진 고폴리 정점마다 가장 가까운 원래 조각 번호 → 정점 속성 name (split_by 로 나눈다)"""
    from mathutils.bvhtree import BVHTree
    trees = []
    for s_ in srcs:
        bm = bmesh.new(); bm.from_mesh(s_.data); bm.transform(s_.matrix_world)
        trees.append(BVHTree.FromBMesh(bm)); bm.free()
    me = o.data
    a = me.attributes.get(name) or me.attributes.new(name, 'INT', 'POINT')
    vals = []
    mw = o.matrix_world
    for v in me.vertices:
        p = mw @ v.co
        best, bi = 1e9, 0
        for i, t in enumerate(trees):
            h = t.find_nearest(p)
            if h[0] is not None and h[3] < best:
                best, bi = h[3], i
        vals.append(bi)
    a.data.foreach_set('value', vals)
    return o


def repad(name, lod0):
    """굽은 뒤 UV 섬 바깥 여백을 섬 안쪽 값으로 다시 넓힌다 (assets_scenes.repad_textures — 각진 돌의 섬 테두리 빗살 방지)"""
    import assets_scenes as SCN
    return SCN.repad_textures(name, lod0)


# ═════════════════════════ 1. 반쯤 묻힌 작은 돌 무리 ═════════════════════════
def pebble_bm(rng, sx, sy, sz):
    """납작하고 각진 자갈: 둘레 고리 점 + 윗면 점 몇 개 + 밑 점의 볼록 껍질 (넓은 윗면이 평평하게 깨진 면)"""
    pts = []
    nr = rng.randint(6, 8)
    a0 = rng.uniform(0, 6.28)
    for i in range(nr):
        a = a0 + 2 * math.pi * (i + rng.uniform(-0.25, 0.25)) / nr
        k = rng.uniform(0.78, 1.0)
        pts.append(Vector((math.cos(a) * sx * k, math.sin(a) * sy * k, sz * rng.uniform(-0.1, 0.25))))
    for i in range(rng.randint(3, 4)):
        a = rng.uniform(0, 6.28); r_ = rng.uniform(0.2, 0.6)
        pts.append(Vector((math.cos(a) * sx * r_, math.sin(a) * sy * r_, sz * rng.uniform(0.75, 1.0))))
    for i in range(2):
        a = rng.uniform(0, 6.28); r_ = rng.uniform(0.1, 0.5)
        pts.append(Vector((math.cos(a) * sx * r_, math.sin(a) * sy * r_, -sz * rng.uniform(0.7, 1.0))))
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in pts]
    r = bmesh.ops.convex_hull(bm, input=vs)
    inner = [g for g in r.get('geom_interior', []) if isinstance(g, bmesh.types.BMVert)]
    if inner:
        bmesh.ops.delete(bm, geom=inner, context='VERTS')
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    # 볼록 껍질이라 '가운데에서 바깥' 이 곧 바깥 법선이다 (recalc 는 납작한 껍질 하나를 통째로 뒤집었다 — FAST 시험 steep 6%)
    cen = sum((v.co for v in bm.verts), Vector()) / max(1, len(bm.verts))
    for f in bm.faces:
        f.normal_update()
        if (f.calc_center_median() - cen).dot(f.normal) < 0:
            f.normal_flip()
    return bm


def pebbles_a():
    """반쯤 묻힌 작은 돌 7개: 납작하고 각진 회갈색 돌 (큰 것 둘, 작은 것 다섯). 비탈·바위 둘레·길가"""
    rng = random.Random(9101)
    # (x, y, 길이, 너비비, 두께비, 묻힘) — 0.6 m 안에 큰 것 둘, 작은 것 다섯
    spec = [(-0.12, 0.04, 0.24, 0.72, 0.48, 0.36), (0.14, -0.08, 0.18, 0.8, 0.52, 0.34), (0.03, 0.18, 0.13, 0.7, 0.55, 0.32),
            (-0.23, -0.15, 0.11, 0.75, 0.58, 0.3), (0.26, 0.13, 0.09, 0.68, 0.6, 0.3), (0.06, -0.22, 0.08, 0.8, 0.55, 0.28),
            (-0.28, 0.18, 0.07, 0.8, 0.6, 0.28)]
    # (field 렌더 1) 납작하고 깊이 묻힌 돌(두께비 0.36~0.5, 묻힘 0.45)은 눈높이 2~8 m 에서 땅 무늬에 묻혀 안 보였다 → 두껍게, 덜 묻게
    # (FAST 시험) 4 cm 아래 부스러기는 carve 복셀(2.2 mm)에 무너져 섬 전체가 누운 노멀이 됐다 → 6 cm 이상만
    lows, highs = [], []
    for i, (x, y, L, wr, tr, bury) in enumerate(spec):
        sx, sy, sz = L / 2, L / 2 * wr, L / 2 * tr
        bm = pebble_bm(rng, sx, sy, sz)
        M = Matrix.Translation((x, y, sz * (0.55 - 2 * bury))) @ Euler((R(rng.uniform(-9, 9)), R(rng.uniform(-9, 9)), rng.uniform(0, 6.28)), 'XYZ').to_matrix().to_4x4()
        bm.transform(M)
        o = obj(bm, "peb%d" % i)
        highs.append(copy(o))
        lows.append(set_group(o, i))             # 돌마다 굽기 무리 (땅속에서 겹친 이웃 돌을 맞지 않게)
    low = join(lows)
    cut_below(low)
    for p in low.data.polygons:
        p.use_smooth = True          # 굽기 때 법선 = 내보낼 법선 (단단한 모서리 38° 만 끊긴다)
    report("pebbles_a(low)", low)
    srcs = [copy(h) for h in highs]
    high = join(highs)
    co, fi = ROCK3(k=0.12, cracks=0.22, chisel=0.3)      # (FAST 시험) 금 0.45 는 4 cm 돌에 벽이 가파른 골 → steep 5%
    carve(high, 0.0022, co, fi, seed=91, snap=True, pieces=True, edges=True)
    m = paint3("pebbles_src", PEBBLE, h=0.09, k=0.14, moss=0.25, moss_color=MOSS_DARK, moss_patch=3.0, moss_low=0.0,
               dirt=0.55, dirt_h=0.012, edge=0.28, edge_mode='attr', edge_w=0.004, edge_gain=0.95, edge_break=0.4,
               piece_var=0.3, piece_val=0.22, cavity=0.8, ao=0.04, stains=0.25, lichen=0.0, strokes=0.25, speckle=0.35,
               grit=0.25, contrast=0.1, gain=1.1, hue_var=0.06, shadow=SHADOW_EARTH, splash=0.35, splash_z=0.0, splash_h=0.02,
               light=0.55, facet_var=0.08, facet_hue=0.0, tooling=0.0, streaks=0.0)
    # (field 렌더 2) gain 1.45 는 앞빛 2 m 에서 돌이 땅(p90 0.30)보다 훨씬 밝은 조각(p90 0.44)으로 떴다 → 1.1.
    # 저장된 pebbles_a_albedo.jpg 는 빌드 2 결과를 선형 1.1/1.45 배로 고쳐 저장한 것 (gain 은 마지막 곱이라 같다, 빌드 횟수 상한 때문에 다시 굽지 않음)
    set_mat(high, m)
    group_by_nearest(high, srcs)
    for o_ in srcs:
        delete(o_)
    hg = split_by(high, len(spec))
    lod0 = finish3("pebbles_a", hg, [low], size=1024, cage=0.004, cage_reach=0.05, hard=38, lod1=None, lod2=None, flat_hard=3,
                   bake_groups=[[h] for h in hg])
    return repad("pebbles_a", lod0)


# ═════════════════════════ 2. 마른 잔가지·껍질 조각 ═════════════════════════
def twig_path(rng, start, ang, L, n, bend=0.25):
    """땅에 누운 잔가지 길 (XY 평면, 조금씩 꺾임)"""
    pts = [Vector(start)]
    a = ang
    for i in range(n):
        a += rng.uniform(-bend, bend)
        pts.append(pts[-1] + Vector((math.cos(a), math.sin(a), 0)) * (L / n))
    return pts


def bark_chip_bm(rng, cx, cy, L, W, T, yaw, curl, segs=(3, 2)):
    """떨어진 껍질 조각: 위로 볼록하게 말린 두꺼운 판 (가장자리가 땅에 닿는다). 밑면 없음 (땅이 덮는다)"""
    nu, nv = segs
    bm = bmesh.new()
    top, bot = [], []
    for i in range(nu + 1):
        rt, rb = [], []
        for j in range(nv + 1):
            u = (i / nu - 0.5) * L
            v = (j / nv - 0.5) * W
            ang = (j / nv - 0.5) * curl
            rr = W / max(0.2, curl) if curl > 0.05 else 1e3
            z = (math.cos(ang) - math.cos(curl / 2)) * rr * 0.8 + rng.uniform(-0.002, 0.002)
            taper = 1.0 - 0.25 * abs(i / nu - 0.5) * 2
            rt.append(bm.verts.new((u, v * taper, z + T)))
            rb.append(bm.verts.new((u, v * taper, z - 0.004)))
        top.append(rt); bot.append(rb)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]))
    ring = [(i, 0) for i in range(nu)] + [(nu, j) for j in range(nv)] + [(i, nv) for i in range(nu, 0, -1)] + [(0, j) for j in range(nv, 0, -1)]
    for k in range(len(ring)):
        a = ring[k]; b = ring[(k + 1) % len(ring)]
        bm.faces.new((top[b[0]][b[1]], top[a[0]][a[1]], bot[a[0]][a[1]], bot[b[0]][b[1]]))
    bm.transform(Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(yaw, 4, 'Z'))
    return bm


def twigs_a():
    """마른 잔가지 다섯(하나는 두 갈래) + 떨어진 껍질 조각 셋. 땅에 붙어 눕고 반쯤 묻힌다. 나무 밑·숲 가장자리"""
    rng = random.Random(9202)
    # 잔가지: (시작, 방향, 길이, 마디 수, 굵기 반지름)
    twigs = [((-0.36, -0.05, 0), R(8), 0.68, 6, 0.024), ((-0.12, -0.3, 0), R(62), 0.5, 5, 0.016),
             ((0.05, 0.12, 0), R(-25), 0.38, 4, 0.013), ((-0.25, 0.22, 0), R(-12), 0.32, 4, 0.011),
             ((0.14, -0.22, 0), R(118), 0.28, 3, 0.01)]
    # (field 렌더 1) 굵기 0.7~1.6 cm 는 8 m 에서 한두 화소 선이라 안 보였다 → 1~2.4 cm
    paths, rads = [], []
    for st, a, L, n, r in twigs:
        p = twig_path(rng, st, a, L, n, 0.22)
        rr = [r * lerp(1.0, 0.55, i / n) for i in range(n + 1)]
        paths.append(p); rads.append(rr)
    # 첫 가지의 갈래
    base = paths[0][3]
    p = twig_path(rng, base, R(8) + R(38), 0.2, 3, 0.2)
    paths.append(p); rads.append([0.013, 0.01, 0.008, 0.006])
    base = paths[1][2]
    p = twig_path(rng, base, R(62) - R(42), 0.14, 2, 0.2)
    paths.append(p); rads.append([0.009, 0.007, 0.005])
    chips = [(0.22, 0.05, 0.15, 0.065, 0.012, R(35), 1.1), (-0.05, -0.12, 0.11, 0.05, 0.01, R(-50), 0.9),
             (0.3, -0.12, 0.08, 0.045, 0.009, R(80), 1.3)]
    # 저폴리: 4각 관 (한 면이 늘 아래 → 지운다), 땅에 반쯤 묻힘 (중심 높이 = 반지름 × 0.45). 조각마다 굽기 무리 (갈래가 붙은 곳)
    lows = []
    for gi, (pts, rr) in enumerate(zip(paths, rads)):
        q = [v + Vector((0, 0, rr[i] * 0.45)) for i, v in enumerate(pts)]
        lb = tube(q, [r * 1.15 for r in rr], sides=4, roll=45, up=(0, 0, 1), cap0=True, cap1=True, squash=0.85)   # 4각 면 가운데 = 0.71r → 굵기를 맞춘다
        lows.append(set_group(obj(lb, "twig_low"), gi))
    for ci, c in enumerate(chips):
        lows.append(set_group(obj(bark_chip_bm(rng, *c), "chip_low"), len(paths) + ci))
    low = join(lows)
    drop_down_faces(low, -0.55, 0.012)
    cut_below(low, -0.006)
    for p_ in low.data.polygons:
        p_.use_smooth = True
    report("twigs_a(low)", low)
    # 고폴리: 저폴리와 같은 꺾인 길(다듬지 않는다 — 다듬으면 꺾인 곳에서 저폴리와 어긋나 가파른 노멀) 의 14각 관 + 껍질 결
    hs = []
    guide = B.Guide()
    for gi, (pts, rr) in enumerate(zip(paths, rads)):
        q = [v + Vector((0, 0, rr[i] * 0.45)) for i, v in enumerate(pts)]
        s = resample(q, 0.004)
        r2 = interp_r(rr, len(s))
        hb = tube(s, r2, sides=14, roll=0, up=(0, 0, 1), cap0=True, cap1=True, squash=0.85,
                  wob=lambda i, k, _s=s: 1.0 + 0.06 * mnoise.noise(_s[i] * 40 + Vector((k * 0.7, 0, 0))))
        hs.append(tag_verts(obj(hb, "twig_high"), gi))
        guide.add(s)
    sticks = join(hs)
    g = guide.obj()
    co, fi = BARK3(k=0.045, depth=0.8)
    kit.surface(sticks, co + fi + [{'t': 'grain', 'scale': 500, 'amp': 0.00012}], 92, guide=g)
    delete(g)
    m = paint3("twigs_src", DRYWOOD, h=0.03, k=0.08, moss=0.2, moss_color=MOSS_DARK, moss_patch=4.0, dirt=0.5, dirt_h=0.006,
               edge=0.22, edge_w=0.002, edge_break=0.5, piece_var=0.0, cavity=0.85, ao=0.01, stains=0.4, strokes=0.3, speckle=0.3,
               contrast=0.1, gain=1.3, hue_var=0.05, shadow=SHADOW_EARTH, light=0.45, tooling=0.0, streaks=0.0, grain=0.6)
    set_mat(sticks, m)
    stick_g = split_by(sticks, len(paths))
    cbs = []
    crng = random.Random(9203)
    for ci, c in enumerate(chips):
        cb = bark_chip_bm(crng, *c, segs=(16, 8))
        cbs.append(tag_verts(obj(cb, "chip"), ci))
    chip = join(cbs)
    kit.surface(chip, [{'t': 'cracks', 'scale': 60, 'width': 0.06, 'depth': 0.0015, 'warp': 0.1, 'cover': 0.5},
                       {'t': 'grain', 'scale': 300, 'amp': 0.0002}], 93)
    mc = paint3("chips_src", BARKCHIP, h=0.03, k=0.08, moss=0.35, moss_color=MOSS_DARK, moss_patch=5.0, dirt=0.6, dirt_h=0.008,
                edge=0.2, edge_w=0.002, edge_break=0.5, piece_var=0.0, cavity=0.9, ao=0.01, stains=0.5, strokes=0.3,
                contrast=0.1, gain=1.2, hue_var=0.05, shadow=SHADOW_EARTH, light=0.45, tooling=0.0, streaks=0.0)
    set_mat(chip, mc)
    chip_g = split_by(chip, len(chips))
    groups = [[h] for h in stick_g + chip_g]
    lod0 = finish3("twigs_a", stick_g + chip_g, [low], size=1024, cage=0.003, cage_reach=0.03, lod1=None, lod2=None, uv_angle=60,
                   bake_groups=groups)
    return lod0


# ═════════════════════════ 3. 흙빛 작은 뼈 조각 ═════════════════════════
def bones_bits():
    """부러진 갈비뼈 토막 셋, 손가락뼈 넷, 부러진 긴 뼈 끝 하나, 뼈 부스러기 둘. 오래되어 흙빛. 무덤·전장·처형장 둘레"""
    rng = random.Random(9303)
    it = []
    guide = B.Guide()
    breaks = []

    def arc(cx, cy, Rr, a0, sweep, n=7, z=0.006, lift=0.012):
        pts = []
        for k in range(n):
            a = R(a0 + sweep * k / (n - 1))
            pts.append(Vector((cx + Rr * math.cos(a), cy + Rr * math.sin(a) * 0.85, z + lift * math.sin(math.pi * k / (n - 1)))))
        return pts
    for cx, cy, Rr, a0, sw, r in ((-0.06, 0.02, 0.16, 95, 70, 0.0095), (0.03, -0.06, 0.14, 120, 55, 0.0085), (0.12, 0.1, 0.1, 30, 48, 0.008)):
        pts = arc(cx, cy, Rr, a0, sw)
        it += B.bone_tube(pts, [r] * len(pts), (0.7, 1.45), 0.45, ref=(0, 0, 1))
        guide.add(pts)
        breaks.append((pts[0], (pts[0] - pts[1]).normalized(), r * 1.2))
        breaks.append((pts[-1], (pts[-1] - pts[-2]).normalized(), r * 1.2))
    # 손가락뼈 (마디 양 끝이 조금 굵다)
    for c, yaw, L, r in (((-0.17, -0.12, 0.007), 20, 0.042, 0.0072), ((-0.12, -0.18, 0.007), -35, 0.036, 0.0065),
                         ((0.2, -0.08, 0.007), 75, 0.03, 0.006), ((-0.21, 0.12, 0.007), 140, 0.026, 0.0055)):
        c = Vector(c); d = Vector((math.cos(R(yaw)), math.sin(R(yaw)), 0))
        pts = [c - d * L / 2, c, c + d * L / 2]
        it += B.bone_tube(pts, [r * 1.2, r * 0.8, r * 1.1], (1.0, 0.85), 0.45)
        guide.add(pts)
    # 부러진 긴 뼈 끝 (관절 머리 + 부러진 대롱)
    a, b = Vector((0.16, 0.2, 0.014)), Vector((0.02, 0.24, 0.012))
    pts = [a, a.lerp(b, 0.5), b]
    it += B.bone_tube(pts, [0.016, 0.012, 0.0125], (1.0, 0.9), 0.45)
    d = (a - b).normalized(); sd = d.cross(Vector((0, 0, 1))).normalized()
    it.append((a + d * 0.006 + sd * 0.01, 0.019))
    it.append((a + d * 0.004 - sd * 0.011, 0.017))
    guide.add(pts)
    breaks.append((b - d * 0.004, -d, 0.015))
    shards = []
    for k, (x, y) in enumerate(((0.08, -0.17), (-0.2, 0.0))):
        g = sphere(1.0, (x, y, 0.004), (rng.uniform(0.018, 0.026), rng.uniform(0.011, 0.015), 0.008), 2, rot=(0, 0, rng.uniform(0, 6.28)))
        slice_rock(g, rng, 6, (0.1, 0.3))
        xf_all(g)
        shards.append(g)

    def cuts(o):
        cs = []
        for j, (p, n, r) in enumerate(breaks):
            cs += B.break_cutters(p, n, r, rng, seed=200 + j, pores=6, cavity=0.4)
        return cs
    lay = [{'t': 'lumps', 'scale': 30, 'amp': 0.0008}, {'t': 'fissure', 'scale': 22, 'width': 0.015, 'depth': 0.0012, 'cover': 0.5},
           {'t': 'pits', 'scale': 160, 'depth': 0.0004, 'cover': 0.6}, {'t': 'bark', 'scale': 60, 'width': 0.06, 'depth': 0.0008, 'stretch': 0.1},
           {'t': 'grain', 'scale': 600, 'amp': 0.0001}]
    bones = B.bone_high(it, None, 0.0024, 0.0016, cuts, lay, guide, seed=94, smooth=(0.4, 2), name="bits", specks=60)
    sh = join(shards)
    remesh(sh, 0.0016)
    kit.surface(sh, [{'t': 'lumps', 'scale': 40, 'amp': 0.0008}, {'t': 'pits', 'scale': 160, 'depth': 0.0004, 'cover': 0.6}], 95)
    bones = join([bones, sh])
    m = paint3("bits_src", OLDBONE, h=0.03, k=0.08, moss=0.15, moss_color=MOSS_DARK, moss_patch=5.0, moss_low=0.0,
               dirt=0.95, dirt_h=0.012, edge=0.25, edge_w=0.0015, edge_break=0.5, piece_var=0.0, cavity=1.0, ao=0.012,
               stains=0.65, strokes=0.25, speckle=0.3, contrast=0.12, gain=1.0, hue_var=0.04, shadow=SHADOW_EARTH, light=0.4,
               tooling=0.0, streaks=0.0, splash=0.6, splash_z=0.0, splash_h=0.01, grain=0.4)
    G.blotch(m, (0.36, 0.3, 0.2), 9.0, 0.6, 0.45, 0.63)       # 흙물이 밴 누런 얼룩 (뼈마다 고르지 않게)
    set_mat(bones, m)
    low = B.low_of(bones, 330, -0.012, 18)
    if low.matrix_world != Matrix.Identity(4):
        xf_all(low)
    cut_below(low, -0.006)
    report("bones_bits(low)", low)
    B.unwrap_smoothed(low, 70, 12)
    lod0 = finish3("bones_bits", [bones], [low], size=1024, cage=0.002, cage_reach=0.02, lod1=None, lod2=None, uv='keep')
    return lod0


# ═════════════════════════ 4. 마른 잎·이끼 낀 흙 얼룩 ═════════════════════════
LEAF_COLS = [(0.16, 0.1, 0.055), (0.2, 0.13, 0.06), (0.12, 0.085, 0.05), (0.22, 0.16, 0.085), (0.1, 0.075, 0.055),
             (0.15, 0.12, 0.07), (0.075, 0.06, 0.045), (0.18, 0.11, 0.07)]    # 선형: 바랜 갈색·황토·짙은 회갈 (빨강·주황 없음)


def litter_radius(a, seed=0.0):
    return 0.4 * (1.0 + 0.14 * math.sin(3 * a + 0.7) + 0.09 * math.sin(5 * a + 2.1) + 0.05 * math.sin(9 * a + seed))


def litter_height(x, y):
    """얼룩 겉 높이 (작은 흙덩이·잎 더미 굴곡)"""
    p = Vector((x, y, 0.0))
    return 0.006 * mnoise.noise(p * 7.0) + 0.003 * mnoise.noise(p * 19.0 + Vector((3, 1, 0)))


def litter_disc(rings, segs, edge_z=-0.022):
    """둘레가 들쭉날쭉한 원판 (가운데 → 가장자리 고리). 가장자리 고리는 땅속으로 내려간다"""
    bm = bmesh.new()
    c = bm.verts.new((0, 0, litter_height(0, 0) + 0.004))
    rows = []
    for fi, f in enumerate(rings):
        row = []
        for k in range(segs):
            a = 2 * math.pi * (k + (0.5 if fi % 2 else 0.0)) / segs
            r = litter_radius(a) * f
            x, y = math.cos(a) * r, math.sin(a) * r
            if fi == len(rings) - 1:
                z = edge_z
            else:
                z = litter_height(x, y) + 0.004 * (1 - f) - 0.004 * f * f
            row.append(bm.verts.new((x, y, z)))
        rows.append(row)
    for k in range(segs):
        bm.faces.new((c, rows[0][k], rows[0][(k + 1) % segs]))
    for i in range(len(rows) - 1):
        a_, b_ = rows[i], rows[i + 1]
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new((a_[k], b_[k], b_[j], a_[j]))
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    return bm


def leaf_bm(rng, L, Wd, curl, lobes=0):
    """마른 잎 하나 (X 축이 잎맥, 끝이 뾰족한 타원 + 잎맥에서 접히고 말림, 두께 1.5 mm)"""
    nu, nv = 8, 4
    bm = bmesh.new()
    top, bot = [], []
    for i in range(nu + 1):
        u = i / nu
        w = math.sin(math.pi * min(1.0, u * 1.05)) ** 0.8 * (1.0 - 0.35 * u)
        if lobes:
            w *= 1.0 + 0.18 * math.sin(u * math.pi * lobes * 2)
        rt, rb = [], []
        for j in range(nv + 1):
            v = (j / nv - 0.5) * 2
            y = v * Wd / 2 * max(w, 0.04)
            z = abs(v) * Wd * 0.12 * curl + (u - 0.5) ** 2 * L * 0.25 * curl      # 잎맥에서 접히고 끝이 들림
            x = (u - 0.5) * L
            rt.append(bm.verts.new((x, y, z + 0.0008)))
            rb.append(bm.verts.new((x, y, z - 0.0008)))
        top.append(rt); bot.append(rb)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]))
            bm.faces.new((bot[i][j + 1], bot[i + 1][j + 1], bot[i + 1][j], bot[i][j]))
    ring = [(i, 0) for i in range(nu)] + [(nu, j) for j in range(nv)] + [(i, nv) for i in range(nu, 0, -1)] + [(0, j) for j in range(nv, 0, -1)]
    for k in range(len(ring)):
        a = ring[k]; b = ring[(k + 1) % len(ring)]
        bm.faces.new((top[b[0]][b[1]], top[a[0]][a[1]], bot[a[0]][a[1]], bot[b[0]][b[1]]))
    return bm


def vcol_mat(name, rough=1.0, vein=0.0, noise_amt=0.35, scale=60.0):
    """정점 색(Col) × 잔 잡음 재질 (굽기 원본용, 잎마다 다른 색)"""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bs = nt.nodes["Principled BSDF"]; bs.inputs["Roughness"].default_value = rough
    at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_name = "Col"
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = kit._noise(nt, tc.outputs['Object'], scale, 3, 0.55)
    tint = kit._ramp_n(nt, nz, [(0.3, (0.38, 0.38, 0.38)), (0.7, (0.62, 0.62, 0.62))])
    col = kit._mix(nt, 'OVERLAY', noise_amt, at.outputs['Color'], tint)
    nt.links.new(col, bs.inputs['Base Color'])
    return m


def leaf_litter():
    """마른 잎과 이끼 낀 흙덩이가 땅을 덮은 납작한 얼룩 (지름 0.85 m). 둘레가 들쭉날쭉하고 땅속으로 내려가 경계가 안 보인다.
    고폴리 = 흙 바탕 + 마른 잎 140 장 + 이끼 덩이 + 잔가지 몇 개 → 저폴리 원판 하나에 굽는다. 숲·들판 낮은 곳"""
    rng = random.Random(9404)
    rings = [0.22, 0.45, 0.66, 0.84, 1.0]
    lb = litter_disc(rings, 22)
    low = obj(lb, "litter_low")
    report("leaf_litter(low)", low)
    # 고폴리 바탕: 같은 원판을 잘게 나눈 흙 (가장자리 넘어 조금 더 넓게)
    hb = litter_disc([0.1 * i for i in range(1, 11)] + [1.08], 96, edge_z=-0.024)
    base = obj(hb, "litter_base")
    sub = base.modifiers.new('sub', 'SUBSURF'); sub.levels = 2; sub.subdivision_type = 'SIMPLE'
    apply_all(base)
    kit.surface(base, [{'t': 'lumps', 'scale': 30, 'amp': 0.0025}, {'t': 'pits', 'scale': 90, 'depth': 0.0012, 'cover': 0.5},
                       {'t': 'grain', 'scale': 400, 'amp': 0.0003}], 96)
    # 흙 색: 가운데 낙엽 밑 갈색 흙 → 가장자리는 땅(ground_grass·dirt 평균) 쪽 짙은 회녹색 (field 렌더 1: 둘레 경계가 붙인 원판처럼 보였다)
    def soil_col(p, nn, i):
        a = math.atan2(p.y, p.x)
        f = math.hypot(p.x, p.y) / litter_radius(a)
        t = max(0.0, min(1.0, (f - 0.5) / 0.48)); t = t * t * (3 - 2 * t)
        return (lerp(0.07, 0.045, t), lerp(0.056, 0.056, t), lerp(0.048, 0.047, t), 1.0)
    vcolor(base, soil_col)
    set_mat(base, vcol_mat("litter_soil", noise_amt=0.45, scale=70.0))
    # 잎: 겹겹이 (가운데 많이, 가장자리로 갈수록 성기게). 잎마다 정점 색
    leaves, cols = [], []
    n_leaf = 0
    for k in range(150):
        a = rng.uniform(0, 6.28)
        rr = litter_radius(a) * math.sqrt(rng.uniform(0.0, 1.0)) * 0.96
        x, y = math.cos(a) * rr, math.sin(a) * rr
        f = rr / litter_radius(a)
        if f > 0.8 and rng.random() < 0.45:
            continue
        L = rng.uniform(0.035, 0.075); Wd = L * rng.uniform(0.4, 0.62)
        lb2 = leaf_bm(rng, L, Wd, rng.uniform(0.3, 1.0), lobes=rng.choice((0, 0, 3, 4)))
        z = litter_height(x, y) + 0.004 * (1 - f) - 0.004 * f * f + rng.uniform(0.0015, 0.006) * (1.0 - 0.7 * f)
        M = Matrix.Translation((x, y, z)) @ Euler((R(rng.uniform(-12, 12)), R(rng.uniform(-12, 12)), rng.uniform(0, 6.28)), 'XYZ').to_matrix().to_4x4()
        lb2.transform(M)
        o = obj(lb2, "leaf")
        c = rng.choice(LEAF_COLS)
        v = rng.uniform(0.8, 1.15) * (1.0 - 0.3 * max(0.0, f - 0.5) * 2)        # 가장자리 잎은 더 어둡게 (땅에 묻혀 든다)
        col = (c[0] * v, c[1] * v, c[2] * v, 1.0)
        vcolor(o, lambda p, nn, i, _c=col: _c)
        leaves.append(o)
        n_leaf += 1
    lv = join(leaves)
    set_mat(lv, vcol_mat("litter_leaf", noise_amt=0.4, scale=90.0))
    # 이끼 덩이 (짙은 올리브, 낮게 솟은 둔덕)
    moss = []
    for k in range(9):
        a = rng.uniform(0, 6.28); rr = litter_radius(a) * rng.uniform(0.15, 0.8)
        x, y = math.cos(a) * rr, math.sin(a) * rr
        s = rng.uniform(0.035, 0.08)
        g = sphere(1.0, (x, y, litter_height(x, y) - 0.002), (s, s * rng.uniform(0.6, 1.0), s * 0.18), 2, rot=(0, 0, rng.uniform(0, 6.28)))
        moss.append(g)
    mo = join(moss)
    remesh(mo, 0.003)
    kit.surface(mo, [{'t': 'lumps', 'scale': 90, 'amp': 0.0015}, {'t': 'grain', 'scale': 300, 'amp': 0.0006}], 97)
    mm = vcol_mat("litter_moss", noise_amt=0.3, scale=160.0)
    vcolor(mo, lambda p, nn, i: (MOSS_DARK[0], MOSS_DARK[1], MOSS_DARK[2], 1.0))
    set_mat(mo, mm)
    # 잔가지 몇 개 (잎 위·사이)
    tb = bmesh.new()
    for k in range(4):
        a = rng.uniform(0, 6.28); rr = 0.4 * rng.uniform(0.1, 0.6)
        st = Vector((math.cos(a) * rr, math.sin(a) * rr, 0))
        p = twig_path(rng, st, rng.uniform(0, 6.28), rng.uniform(0.1, 0.22), 3, 0.3)
        p = [v + Vector((0, 0, litter_height(v.x, v.y) + 0.007)) for v in p]
        s = resample(smooth_path(p, 1), 0.006)
        tube(s, interp_r([0.0035, 0.003, 0.0025, 0.002], len(s)), sides=8, roll=0, up=(0, 0, 1), bm=tb)
    tw = obj(tb, "litter_twig")
    vcolor(tw, lambda p, nn, i: (0.13, 0.11, 0.09, 1.0))
    set_mat(tw, vcol_mat("litter_twigm", noise_amt=0.3, scale=200.0))
    print("LITTER leaves", n_leaf)
    # 우리: 광선이 가장 먼저 맞는 흙 바탕까지만 재므로 그 위 잎(바탕 위 0.8 cm 까지)을 덮게 여유를 크게
    lod0 = finish3("leaf_litter", [base, lv, mo, tw], [low], size=1024, cage=0.013, cage_reach=0.05, lod1=None, lod2=None, uv_angle=80)
    return lod0


# ═════════════════════════ 5. 마른 가시덤불 ═════════════════════════
def shrub_skeleton(rng, budget=392):
    """뿌리 둘레에서 바깥·위로 뻗는 굵은 줄기 7 (3 마디 + 끝, 지그재그로 꺾임) + 줄기와 큰 잔가지에서 비스듬히 돋은 가는 잔가지 (끝이 한 점인
    원뿔 하나 = 삼각형 3). 줄기 둘레를 잔가지로 촘촘히 채워 눈높이에서 덩어리 실루엣이 읽히게 한다 (첫 빌드: 가지 23 개는 몇 가닥 선으로만 보였다).
    [(점들, 반지름들, 끝 모음), ...] — 삼각형이 budget 을 넘지 않게 잔가지를 더한다"""
    items = []
    mains = []
    n_main = 7
    for i in range(n_main):
        az = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / n_main
        tilt = R(rng.uniform(18, 55))
        L = rng.uniform(0.62, 0.95) * (1.0 - 0.22 * (tilt - R(18)) / R(37))
        d = Vector((math.sin(tilt) * math.cos(az), math.sin(tilt) * math.sin(az), math.cos(tilt)))
        p = Vector((math.cos(az) * 0.025, math.sin(az) * 0.025, -0.03))
        pts = [p.copy()]
        nseg = 3
        for k in range(nseg):
            kink = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.2, 0.4))) * 0.42
            dd = (d + kink).normalized()
            dd.z -= 0.08 * k
            p = p + dd.normalized() * (L / nseg)
            pts.append(p.copy())
        r0 = rng.uniform(0.013, 0.017)
        radii = [r0 * lerp(1.0, 0.25, k / nseg) for k in range(nseg + 1)]
        items.append((pts, radii, True))
        mains.append((pts, radii))
    used = n_main * ((4 - 2) * 6 + 3) + 5          # 줄기 15 + 뿌리 그루 5

    def at(pts, radii, t):
        """꺾인 선 위 비율 t 의 점·방향·반지름"""
        n = len(pts) - 1
        s_ = t * n
        k = min(n - 1, int(s_)); f = s_ - k
        return pts[k].lerp(pts[k + 1], f), (pts[k + 1] - pts[k]).normalized(), lerp(radii[k], radii[k + 1], f)
    parents = list(mains)
    k = 0
    while used + 3 <= budget and k < 400:
        k += 1
        pts, radii = parents[rng.randrange(len(parents))] if (len(parents) > n_main and rng.random() < 0.35) else mains[rng.randrange(n_main)]
        t = rng.uniform(0.2, 0.92)
        base, tdir, rp = at(pts, radii, t)
        side = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.15, 0.8))).normalized()
        side = (side - tdir * side.dot(tdir)).normalized()
        ang = R(rng.uniform(30, 70))
        sd = (tdir * math.cos(ang) + side * math.sin(ang)).normalized()
        L = rng.uniform(0.07, 0.26) * (1.15 - 0.5 * t) * (1.0 if len(pts) > 2 else 0.6)
        tipp = base + sd * L
        if tipp.z < 0.02:
            continue
        rb = max(0.0022, rp * rng.uniform(0.45, 0.6))
        items.append(([base, tipp], [rb, 0.0], True))
        used += 3
        if L > 0.16 and len(parents) < 60:
            parents.append(([base, tipp], [rb, rb * 0.2]))
    return items


def shrub_dry():
    """마른 가시덤불 (키 0.8 m 안팎, 폭 1 m): 뿌리 둘레에서 바깥·위로 뻗어 지그재그로 꺾인 굵은 줄기 일곱 + 비스듬히 돋은 가는 잔가지 ~90.
    잎 없음. 저폴리 = 3각 관 (끝은 한 점, 잔가지는 원뿔 하나). 원본 = 저폴리 사본 (둥근 원본에 구우면 한 점으로 모인 끝에서 노멀이 누워
    steep 4.8% — 쇠 울타리처럼 잔 결은 칠 bump 가 맡고, 둥근 느낌은 부드러운 정점 법선이 맡는다).
    들판·언덕 마루 (눈높이에서 지평선을 깨는 실루엣)"""
    rng = random.Random(9505)
    items = shrub_skeleton(rng, budget=380)        # 땅 높이로 자를 때 줄기 밑동 면이 쪼개져 10여 개 는다
    lb = bmesh.new()
    for pts, rr, tip in items:
        tube(pts, [r * 1.2 for r in rr], sides=3, roll=rng.uniform(0, 120), up=None, cap0=False, cap1=False, tip=tip, bm=lb)
    ring = [lb.verts.new((math.cos(a) * 0.05, math.sin(a) * 0.05, -0.02)) for a in [2 * math.pi * k / 5 for k in range(5)]]
    top = lb.verts.new((0, 0, 0.05))
    for k in range(5):
        lb.faces.new((ring[k], ring[(k + 1) % 5], top))         # 뿌리 그루 (낮은 각뿔)
    low = obj(lb, "shrub_low")
    cut_below(low, -0.02)
    for p_ in low.data.polygons:
        p_.use_smooth = True
    report("shrub_dry(low)", low)
    print("SHRUB branches", len(items))
    high = copy(low)
    m = paint3("shrub_src", SHRUB, h=0.85, k=0.2, moss=0.12, moss_color=MOSS_DARK, moss_patch=4.0, moss_low=0.5, moss_low_h=0.12,
               dirt=0.7, dirt_h=0.08, edge=0.0, piece_var=0.0, cavity=0.5, ao=0.03, stains=0.4, strokes=0.35, speckle=0.3,
               contrast=0.1, gain=1.25, hue_var=0.04, shadow=SHADOW_EARTH, light=0.5, tooling=0.0, streaks=0.0, grain=0.8, bump=0.5)
    set_mat(high, m)
    lod0 = finish3("shrub_dry", [high], [low], size=1024, cage=0.002, cage_reach=0.01, lod1=None, lod2=None, uv_angle=55)
    return lod0


# ═════════════════════════ 6. 갓 밑이 빛나는 작은 버섯 무리 ═════════════════════════
def mushroom_parts(rng, base, H, Rc, upturn=0.0, lean=(0.0, 0.0), segs=7):
    """버섯 하나: (Main bm, Glow bm). 대 = 5각 관 두 마디, 갓 = 7각 회전체 (윗면 + 둥근 테),
    갓 밑 주름면 = Glow. upturn > 0 이면 테가 위로 젖혀져 주름이 위에서도 조금 보인다"""
    bmM, bmG = bmesh.new(), bmesh.new()
    base = Vector(base)
    top = base + Vector((lean[0], lean[1], H))
    rs = Rc * rng.uniform(0.18, 0.24)
    mid = base.lerp(top, 0.55) + Vector((lean[0], lean[1], 0)) * -0.3
    under = top - Vector((0, 0, Rc * 0.18))
    tube([base - Vector((0, 0, 0.02)), mid], [rs * 1.25, rs * 1.0], sides=5, roll=rng.uniform(0, 72), up=None, cap0=False, cap1=False, bm=bmM)
    tube([mid, under], [rs * 1.0, rs * 0.9], sides=5, roll=rng.uniform(0, 72), up=None, cap0=False, cap1=False, bm=bmM)
    # (field 렌더 1) 대 윗마디까지 Glow 면 사방에서 보이는 빛나는 막대가 됐다 → 발광은 갓 밑 주름면만 (테가 젖혀진 둘은 옆에서 조금 보인다)
    # 갓 윤곽 (반지름 비, 높이) — 위 가운데 → 둘레 → 테 아래 (주름면 시작)
    rim_z = -Rc * 0.05 + upturn * Rc * 0.35
    prof_top = [(0.0, Rc * 0.62), (0.55, Rc * 0.5), (1.0, rim_z)]
    a0 = rng.uniform(0, 6.28)
    sq = rng.uniform(0.85, 1.0)
    def ring(rf, z, wav=0.0):
        out = []
        for k in range(segs):
            a = a0 + 2 * math.pi * k / segs
            w = 1.0 + wav * math.sin(3 * a + a0)
            out.append(top + Vector((math.cos(a) * Rc * rf * w, math.sin(a) * Rc * rf * w * sq, z + wav * Rc * 0.15 * math.sin(3 * a + a0))))
        return out
    c = bmM.verts.new(top + Vector((0, 0, prof_top[0][1])))
    r1 = [bmM.verts.new(p) for p in ring(prof_top[1][0], prof_top[1][1])]
    r2 = [bmM.verts.new(p) for p in ring(prof_top[2][0], prof_top[2][1], 0.08)]
    r3 = [bmM.verts.new(p) for p in ring(0.9, rim_z - Rc * 0.16, 0.08)]
    for k in range(segs):
        j = (k + 1) % segs
        bmM.faces.new((c, r1[k], r1[j]))
        bmM.faces.new((r1[k], r2[k], r2[j], r1[j]))
        bmM.faces.new((r2[k], r3[k], r3[j], r2[j]))
    # 주름면 (Glow): 테 아래 고리 → 대 둘레
    g3 = [bmG.verts.new(p) for p in ring(0.9, rim_z - Rc * 0.16, 0.08)]
    g4 = [bmG.verts.new(under + (p - top) * (rs * 1.1 / (Rc * 0.9))) for p in ring(0.9, 0.0)]
    for k in range(segs):
        j = (k + 1) % segs
        bmG.faces.new((g3[j], g3[k], g4[k], g4[j]))
    # 감는 방향: 갓 윗면·테는 바깥, 주름면은 아래, 대는 바깥 (recalc 하지 않는다 — 열린 껍질이라 뒤집힐 수 있다)
    return bmM, bmG


def mushrooms_glow():
    """작은 버섯 다섯 + 갓 하나만 솟은 어린 것 (낮음, 가장 큰 것 키 0.15 m, 무리 지름 0.3 m). 갓은 짙은 갈색, 대는 바랜 회백,
    갓 밑 주름면만 청록 영혼빛(Glow_Spirit)으로 희미하게. 숲·축축한 곳"""
    rng = random.Random(9606)
    spec = [((0.0, 0.0, 0.0), 0.15, 0.042, 0.0, (0.01, 0.004)), ((0.07, 0.04, 0.0), 0.11, 0.034, 0.5, (0.012, 0.006)),
            ((-0.06, 0.05, 0.0), 0.085, 0.03, 0.0, (-0.012, 0.008)), ((0.04, -0.07, 0.0), 0.07, 0.026, 0.7, (0.006, -0.01)),
            ((-0.09, -0.04, 0.0), 0.05, 0.022, 0.0, (-0.01, -0.004))]
    mains, glows = [], []
    for base, H, Rc, up, lean in spec:
        bmM, bmG = mushroom_parts(rng, base, H, Rc, up, lean)
        mains.append(obj(bmM, "mush")); glows.append(obj(bmG, "mush_glow"))
    # 어린 것: 땅에서 갓만 반쯤 솟음
    bb = bmesh.new()
    c0 = Vector((0.11, -0.02, 0.0))
    seg = 6
    ring1 = [bb.verts.new(c0 + Vector((math.cos(2 * math.pi * k / seg) * 0.017, math.sin(2 * math.pi * k / seg) * 0.017, -0.004))) for k in range(seg)]
    ring2 = [bb.verts.new(c0 + Vector((math.cos(2 * math.pi * (k + 0.5) / seg) * 0.011, math.sin(2 * math.pi * (k + 0.5) / seg) * 0.011, 0.014))) for k in range(seg)]
    tp = bb.verts.new(c0 + Vector((0, 0, 0.021)))
    for k in range(seg):
        j = (k + 1) % seg
        bb.faces.new((ring1[k], ring1[j], ring2[k]))
        bb.faces.new((ring1[j], ring2[j], ring2[k]))
        bb.faces.new((ring2[k], ring2[j], tp))
    mains.append(obj(bb, "button", recalc=True))
    low = join(mains)
    cut_below(low, -0.015)
    for p_ in low.data.polygons:
        p_.use_smooth = True
    glow_o = join(glows)
    for p_ in glow_o.data.polygons:
        p_.use_smooth = True
    n = tri_count(low) + tri_count(glow_o)
    print("CLUTTER mushrooms_glow main", tri_count(low), "glow", tri_count(glow_o), "total", n)
    if n > MAX_TRIS:
        raise RuntimeError("mushrooms_glow: 삼각형 %d > %d" % (n, MAX_TRIS))
    glow(glow_o, 'Glow_Spirit')
    # 고폴리: 저폴리를 매끈하게 나눈 뒤 잔 굴곡 (갓 윗면 잔주름, 대 세로 결)
    high = copy(low)
    sub = high.modifiers.new('sub', 'SUBSURF'); sub.levels = 3
    apply_all(high)
    kit.surface(high, [{'t': 'lumps', 'scale': 60, 'amp': 0.0008}, {'t': 'pits', 'scale': 220, 'depth': 0.0003, 'cover': 0.5},
                       {'t': 'grain', 'scale': 700, 'amp': 0.0001}], 99)
    # 갓 / 대 색을 높이·법선으로 나눈다: 갓 윗면 = CAP, 그 밖 = STEM (paint3 하나로: 위를 향한 면 = 짙은 갈색)
    m = paint3("mush_src", STEM, h=0.15, k=0.05, moss=0.0, dirt=0.9, dirt_h=0.02, edge=0.0, piece_var=0.0, cavity=0.8, ao=0.006,
               stains=0.3, strokes=0.2, speckle=0.3, contrast=0.1, gain=1.0, hue_var=0.0, shadow=SHADOW_EARTH, light=0.3,
               tooling=0.0, streaks=0.0, grain=0.4)
    nt = m.node_tree
    b, col = G._final_color(m)
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sN = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(geo.outputs['Normal'], sN.inputs[0])
    capm = kit._maprange(nt, sN.outputs['Z'], 0.05, 0.4)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    capc = kit._ramp_n(nt, kit._noise(nt, tc.outputs['Object'], 70.0, 4, 0.55), [(0.3, CAP[0]), (0.55, CAP[1]), (0.75, lerp_c(CAP[1], CAP[2], 0.5))])
    col = kit._mix(nt, 'MIX', capm, col, capc)
    # 갓 밑 둘레·대 윗마디: 빛을 받은 듯 옅은 청록 (발광이 아닌 칠, 아주 약하게)
    zc = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Object'], zc.inputs[0])
    under = kit._mul(nt, kit._maprange(nt, sN.outputs['Z'], 0.0, -0.5), 0.35)
    col = kit._mix(nt, 'MIX', under, col, W((0.09, 0.2, 0.19)))
    nt.links.new(col, b.inputs['Base Color'])
    set_mat(high, m)
    lod0 = finish3("mushrooms_glow", [high], [low], extras=[glow_o], size=512, cage=0.002, cage_reach=0.02, lod1=None, lod2=None, uv_angle=60)
    return lod0


def lerp_c(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


BUILDERS = [
    ("pebbles_a", pebbles_a), ("twigs_a", twigs_a), ("bones_bits", bones_bits),
    ("leaf_litter", leaf_litter), ("shrub_dry", shrub_dry), ("mushrooms_glow", mushrooms_glow),
]

# META: kind detail (지형 detail 프로토타입). 그 밖에 월드 생성기용 권장값 (Unity 도구는 모르는 키를 무시한다):
#   place: 놓을 곳 열쇠말 (slope 비탈, rock_ring 바위 둘레, path_edge 길가, ruin 폐허 발치, tree_base 나무 밑, forest_edge 숲 가장자리,
#          forest 숲, grave 무덤 둘레, battlefield 전장, execution 처형장, field_low 들판 낮은 곳, field 들판, ridge 언덕 마루, damp 축축한 곳)
#   density: 0~1 상대값 (1 = 그 자리에서 가장 많이. 확인 렌더에서 1 ≈ 0.5 개/m² — 월드 detail 칸 1 m² 의 maxPerCell ≈ 0.5 × density)
#   max_slope: 권장 최대 경사 (도). 지형 detail 은 경사의 절반만 기울어서 넓고 납작한 것은 비탈에서 한쪽이 뜬다
#   ground_align: 권장 alignToGround (지금 Unity 월드 빌더는 align true 면 0.5). 납작한 것은 1.0 이 맞다
_CL = {"kind": "detail", "collider": "none", "sink": 0.0, "tilt": 4, "align": True, "cull": 0.0, "shadows": False}
META = {
    "pebbles_a":      dict(_CL, tags=["rock", "path", "nature", "clutter"], footprint=0.35, scale=[0.75, 1.35],
                           place=["slope", "rock_ring", "path_edge", "ruin"], density=0.6, max_slope=35, ground_align=0.8),
    "twigs_a":        dict(_CL, tags=["nature", "forest", "clutter"], footprint=0.4, scale=[0.8, 1.25],
                           place=["tree_base", "forest_edge", "forest"], density=0.7, max_slope=25, ground_align=1.0),
    "bones_bits":     dict(_CL, tags=["bone", "grave", "clutter"], footprint=0.3, scale=[0.8, 1.25],
                           place=["grave", "battlefield", "execution"], density=0.45, max_slope=25, ground_align=1.0),
    "leaf_litter":    dict(_CL, tags=["nature", "forest", "clutter"], footprint=0.45, scale=[0.85, 1.3], tilt=2,
                           place=["forest", "field_low", "tree_base"], density=0.8, max_slope=12, ground_align=1.0),
    "shrub_dry":      dict(_CL, tags=["nature", "field", "clutter"], footprint=0.55, scale=[0.75, 1.3], tilt=6, align=False,
                           place=["field", "ridge", "forest_edge"], density=0.35, max_slope=30, ground_align=0.0),
    "mushrooms_glow": dict(_CL, tags=["nature", "forest", "swamp", "light", "clutter"], footprint=0.2, scale=[0.8, 1.4],
                           place=["forest", "damp", "tree_base"], density=0.3, max_slope=20, ground_align=0.8),
}

_NAMES = [n for n, _ in BUILDERS]
PREVIEWS = [("all", _NAMES, False)]
