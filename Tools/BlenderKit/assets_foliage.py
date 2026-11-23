# 풀·꽃·버섯·덤불 묶음 (foliage)
#   지형 풀(detail): grass_a, grass_b, grass_dead, fern_a, weeds, reed        — Foliage 재질 하나만
#   흩뿌리는 장식(scatter): flower_lily, mushroom_glow, mushroom_toxic, lotus_glow — Foliage + Glow_*
#   지형 나무(tree): bramble, bush_dead                                       — Foliage 하나만
#
# 만드는 방식
#   - 굽지 않는다. 정점을 직접 만든다 (Geo): 곡선(curve) 을 따라 V자로 접힌 띠(strip), 가는 원통(tube), 회전체(lathe).
#     색 = 정점 색(선형 값을 넣으면 FBX 에 sRGB 로 나간다) × 잎 아틀라스 칸. 정점 알파 = 바람에 흔들리는 정도 (0 뿌리 ~ 1 끝).
#   - 풀잎은 'stem' 칸(가운데가 밝은 가로 그러데이션)을 쓰고 가운데 접힌 선을 밝게, 가장자리를 어둡게 해 입체감을 낸다.
#     접힌 선의 정점은 둘로 나눠 날카롭게 꺾여 보이게 하고, 길이 방향으로는 부드럽게 음영한다.
#   - 고사리·갈대·꽃잎·잎은 아틀라스 칸(fern, reed, petal, thorn_leaf, ivy_b ...)을 휘어진 카드에 붙인다.
#   - 발광 부품(꽃술, 버섯 점, 연꽃 속잎, 독버섯 주름면)은 텍스처가 없으므로 모양을 정점으로 직접 만든다.
#   - mushroom_toxic 만 썩은 그루터기를 kit 방식(조각 + 굽기)으로 만들고 버섯은 extras 로 붙인다.
#   - 지형 나무(bramble, bush_dead)와 큰 장식은 같은 씨앗으로 개수를 줄여 LOD1 을 따로 만든다.
import math, random, os
import bpy, bmesh
from mathutils import Vector, Matrix, Euler, Quaternion
import kit
from kit import *

# kit.load_fbx 가 FBX 에서 함께 들어온 "Foliage"·"Glow_*" 재질을 진짜로 착각하지 않게 진짜 재질을 먼저 만든다 (미리보기용)
if kit.sc is not None:
    foliage_mat()
    for _g in GLOW:
        glow_mat(_g)

R = math.radians
UP = Vector((0, 0, 1))
GOLD = math.pi * (3 - math.sqrt(5))          # 황금각: 잎을 겹치지 않게 돌려 놓는다


# ───────────────────────── 기본 도우미 ─────────────────────────
def lerp(a, b, t):
    return a + (b - a) * t

def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))

def scl(c, k):
    return tuple(max(0.0, min(1.0, x * k)) for x in c)

def grad(c0, c1, c2, mid=0.5):
    """s(0~1)에 따른 세 색 그러데이션"""
    def f(s):
        return mix(c0, c1, s / mid) if s < mid else mix(c1, c2, (s - mid) / (1 - mid))
    return f

def smooth01(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class Geo:
    """정점·면·UV·정점 색을 모아 메쉬 하나로 만든다 (정점마다 UV 하나, 면마다 재질 칸·부드러움)"""
    def __init__(self):
        self.v, self.uv, self.c, self.f = [], [], [], []

    def vert(self, p, uv, col):
        self.v.append(Vector(p)); self.uv.append(tuple(uv)); self.c.append(tuple(col))
        return len(self.v) - 1

    def face(self, idx, mat=0, smooth=True):
        self.f.append((tuple(idx), mat, smooth))

    def tris(self):
        return sum(len(f[0]) - 2 for f in self.f)

    def normalize_alpha(self, top=1.0, lo=0.0):
        """알파를 lo~top 범위로 다시 맞춘다 (가장 높은 끝 = top)"""
        m = max(c[3] for c in self.c) if self.c else 1.0
        if m <= 1e-6:
            return
        self.c = [(c[0], c[1], c[2], lo + (top - lo) * c[3] / m) for c in self.c]

    def build(self, name, mats):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in self.v], [], [f[0] for f in self.f])
        me.update(calc_edges=True)
        o = bpy.data.objects.new(name, me)
        kit.sc.collection.objects.link(o)
        # 층을 모두 만든 뒤에 이름으로 다시 가져온다 (속성을 더하면 앞서 받은 층 참조가 무효가 된다)
        me.uv_layers.new(name="UVMap")
        me.color_attributes.new("Col", 'BYTE_COLOR', 'CORNER')
        uvl = me.uv_layers["UVMap"]
        col = me.color_attributes["Col"]
        for lp in me.loops:
            uvl.data[lp.index].uv = self.uv[lp.vertex_index]
            col.data[lp.index].color = self.c[lp.vertex_index]
        for m in mats:
            me.materials.append(m)
        for p, f in zip(me.polygons, self.f):
            p.material_index = f[1]
            p.use_smooth = f[2]
        return o


def curve(root, L, th0, th1, az, p=1.6, n=24, kink=None, swirl=0.0, floor=None, wobble=0.0, rng=None):
    """뿌리에서 길이 L 인 곡선 (같은 간격 n+1 점). 연직에서 기운 각 th(s) = th0 + (th1-th0)·s^p, 방위 az (+ swirl·s).
    kink=(s, 각): s 에서 갑자기 꺾인다. floor: 이 높이 아래로 내려가지 않는다 (땅에 닿은 잎이 눕는다)."""
    pts = [Vector(root)]
    ds = L / n
    ph = rng.uniform(0, 6.28) if rng else 0.0
    for i in range(n):
        s = (i + 0.5) / n
        th = th0 + (th1 - th0) * s ** p
        if kink and s > kink[0]:
            th += kink[1]
        a = az + swirl * s + (wobble * math.sin(ph + s * 9.0) if wobble else 0.0)
        d = Vector((math.cos(a) * math.sin(th), math.sin(a) * math.sin(th), math.cos(th)))
        q = pts[-1] + d * ds
        if floor is not None and q.z < floor and i > 0:
            q.z = floor
        pts.append(q)
    return pts

def at(pts, s):
    f = max(0.0, min(1.0, s)) * (len(pts) - 1)
    i = min(int(f), len(pts) - 2)
    return pts[i].lerp(pts[i + 1], f - i)

def tangent(pts, s, h=0.02):
    t = at(pts, min(1.0, s + h)) - at(pts, max(0.0, s - h))
    return t.normalized() if t.length > 1e-9 else Vector((0, 0, 1))

def dir_angles(d):
    """방향 벡터 → (연직에서 기운 각, 방위)"""
    d = d.normalized()
    return math.acos(max(-1.0, min(1.0, d.z))), math.atan2(d.y, d.x)

def frames(P, side0, twist=0.0, svals=None):
    """점 목록을 따라 접선 T, 옆 S (평행 이동 + 비틀림), 면 법선 N = T×S"""
    n = len(P)
    T = []
    for i in range(n):
        t = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        T.append(t.normalized() if t.length > 1e-9 else Vector((0, 0, 1)))
    S = []
    sv = Vector(side0)
    for i in range(n):
        sv = sv - T[i] * sv.dot(T[i])
        if sv.length < 1e-6:
            sv = T[i].orthogonal()
        sv.normalize()
        if twist and i > 0:
            ds = (svals[i] - svals[i - 1]) if svals else 1.0 / (n - 1)
            sv = Quaternion(T[i], twist * ds) @ sv
        S.append(sv.copy())
    N = [T[i].cross(S[i]).normalized() for i in range(n)]
    return T, S, N

def strip_rows(G, P, svals, side0, widths, cell, cols, alphas, fold=0.0, mat=0, smooth=True, twist=0.0,
               uspan=None, flipu=False, crease_toward=None, vrange=(0.0, 1.0), offs=None):
    """점 P 를 따라 가는 띠. widths: 반폭 (마지막이 0 이면 뾰족한 끝).
    fold: 가운데 접힘 (반폭 대비 접힌 선이 면 법선 쪽으로 나온 정도). crease_toward 를 주면 접힌 선이 그쪽으로 나오게 부호를 정한다.
    uspan: 줄마다 칸 너비 중 쓰는 비율 (끝이 좁아지는 카드에서 그림이 찌그러지지 않게)."""
    n = len(P)
    T, S, N = frames(P, side0, twist, svals)
    if fold and crease_toward is not None and N[0].dot(Vector(crease_toward)) * fold < 0:
        fold = -fold
    rows = []
    for i in range(n):
        s = svals[i]
        v = vrange[0] + (vrange[1] - vrange[0]) * s
        w = widths[i]
        c = cols[i]
        c4 = (c[0], c[1], c[2], alphas[i])
        us = uspan[i] if uspan else 1.0
        ul, ur = 0.5 - 0.5 * us, 0.5 + 0.5 * us
        if flipu:
            ul, ur = ur, ul
        p = P[i] + (offs[i] if offs else Vector())
        if i == n - 1 and w < 1e-7:
            rows.append(('t', G.vert(p, atlas_uv(cell, 0.5, v), c4)))
        elif fold:
            cp = p + N[i] * (fold * w)
            rows.append(('f', G.vert(p - S[i] * w, atlas_uv(cell, ul, v), c4),
                         G.vert(cp, atlas_uv(cell, 0.5, v), c4), G.vert(cp, atlas_uv(cell, 0.5, v), c4),
                         G.vert(p + S[i] * w, atlas_uv(cell, ur, v), c4)))
        else:
            rows.append(('q', G.vert(p - S[i] * w, atlas_uv(cell, ul, v), c4), G.vert(p + S[i] * w, atlas_uv(cell, ur, v), c4)))
    for i in range(n - 1):
        a, b = rows[i], rows[i + 1]
        if b[0] == 't':
            if a[0] == 'f':
                G.face((a[1], a[2], b[1]), mat, smooth); G.face((a[3], a[4], b[1]), mat, smooth)
            else:
                G.face((a[1], a[2], b[1]), mat, smooth)
        elif a[0] == 'f':
            G.face((a[1], a[2], b[2], b[1]), mat, smooth); G.face((a[3], a[4], b[4], b[3]), mat, smooth)
        else:
            G.face((a[1], a[2], b[2], b[1]), mat, smooth)
    return S, N

def strip(G, pts, svals, side0, wfn, cell, colfn, alfn, **kw):
    """곡선 pts 위 svals 자리마다 줄을 놓는 띠 (wfn, colfn, alfn: s → 반폭, 색, 알파)"""
    P = [at(pts, s) for s in svals]
    ufn = kw.pop('ufn', None)
    if ufn is not None:
        kw['uspan'] = [ufn(s) for s in svals]
    return strip_rows(G, P, svals, side0, [wfn(s) for s in svals], cell, [colfn(s) for s in svals],
                      [alfn(s) for s in svals], **kw)

def tube_rows(G, P, radii, sides, cols, alphas, mat=0, cell='stem', side0=None, smooth=True, u=0.5):
    """점 P 를 따라 가는 가는 원통 (마지막 반지름이 0 이면 뾰족한 끝)"""
    n = len(P)
    T, S, N = frames(P, side0 if side0 is not None else (P[-1] - P[0]).orthogonal())
    rings = []
    for i in range(n):
        c = cols[i]
        c4 = (c[0], c[1], c[2], alphas[i])
        uv = atlas_uv(cell, u, 0.1 + 0.8 * i / max(1, n - 1))
        if i == n - 1 and radii[i] < 1e-7:
            rings.append([G.vert(P[i], uv, c4)])
            continue
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides
            d = S[i] * math.cos(a) + N[i] * math.sin(a)
            ring.append(G.vert(P[i] + d * radii[i], uv, c4))
        rings.append(ring)
    for i in range(n - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(sides):
            k2 = (k + 1) % sides
            if len(B) == 1:
                G.face((A[k], A[k2], B[0]), mat, smooth)
            else:
                G.face((A[k], A[k2], B[k2], B[k]), mat, smooth)
    return rings

def tube(G, pts, svals, rfn, sides, colfn, alfn, **kw):
    P = [at(pts, s) for s in svals]
    return tube_rows(G, P, [rfn(s) for s in svals], sides, [colfn(s) for s in svals], [alfn(s) for s in svals], **kw)

def octa(G, c, r, col, mat=0, cell='solid', squash=1.0, axis=None):
    """작은 팔면체 (열매, 꽃밥)"""
    c = Vector(c)
    ax = Vector(axis).normalized() if axis is not None else UP
    a = ax.orthogonal().normalized(); b = ax.cross(a)
    uv = atlas_uv(cell, 0.5, 0.5)
    top = G.vert(c + ax * r * squash, uv, col); bot = G.vert(c - ax * r * squash, uv, col)
    ring = [G.vert(c + (a * math.cos(k * math.pi / 2) + b * math.sin(k * math.pi / 2)) * r, uv, col) for k in range(4)]
    for k in range(4):
        G.face((ring[k], ring[(k + 1) % 4], top), mat)
        G.face((ring[(k + 1) % 4], ring[k], bot), mat)

def finish_lods(name, lods):
    """lods: [LOD0 부품 목록, LOD1 부품 목록, ...] 을 각각 합쳐 이름_LODn 으로 내보낸다 (kit.finish_foliage 와 같은 설정)"""
    objs = []
    for i, parts in enumerate(lods):
        o = join(parts)
        origin0(o)
        o.name = name + "_LOD%d" % i
        o.data.name = o.name
        objs.append(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(filepath=os.path.join(kit.OUT, name + ".fbx"), use_selection=True, object_types={'MESH'},
                             apply_scale_options='FBX_SCALE_UNITS', bake_space_transform=True, axis_forward='-Z', axis_up='Y',
                             use_mesh_modifiers=True, mesh_smooth_type='OFF', add_leaf_bones=False, bake_anim=False,
                             colors_type='SRGB')
    print("ASSET", {'name': name, 'tris': [tri_count(o) for o in objs], 'size': [round(v, 2) for v in objs[0].dimensions], 'tex': 0})
    for i, o in enumerate(objs):
        o.location = (1000 + len(kit.LOWS) * 40, 1000 + i * 40, 0)
        o.hide_render = True
    kit.LOWS[name] = objs[0]
    return objs[0]


# ───────────────────────── 색 ─────────────────────────
# 정점 색은 선형 값. 'stem' 칸(밝기 0.26~0.79)과 곱해지므로 실제 반사율은 대략 이 값의 절반쯤이다.
TEAL = [(0.07, 0.17, 0.155), (0.05, 0.145, 0.16), (0.08, 0.18, 0.125), (0.06, 0.13, 0.14), (0.045, 0.12, 0.11)]
OLIVE = [(0.15, 0.17, 0.065), (0.12, 0.15, 0.075), (0.17, 0.16, 0.08)]
STRAW = [(0.42, 0.33, 0.17), (0.34, 0.27, 0.14), (0.46, 0.39, 0.23), (0.3, 0.27, 0.21), (0.38, 0.3, 0.2)]
DRY_TIP = (0.32, 0.27, 0.13)


def blade(G, rng, root, L, th0, th1, az, w0, cols, alpha_k, rows=None, fold=0.6, swirl=0.0, twist=0.0, p=1.8,
          kink=None, blunt=False, floor=0.004, side_turn=None, cell='stem'):
    """풀잎 하나: 곡선 + V자 단면. cols=(뿌리, 가운데, 끝) 색, alpha_k = 끝 알파 (길이 비례)"""
    pts = curve(root, L, th0, th1, az, p=p, kink=kink, swirl=swirl, floor=floor)
    if rows is None:
        rows = [0.0, 0.4, 0.75, 1.0] if L > 0.24 else [0.0, 0.55, 1.0]
    side0 = Vector((-math.sin(az), math.cos(az), 0))
    side0 = Quaternion(UP, side_turn if side_turn is not None else rng.uniform(-0.7, 0.7)) @ side0
    if blunt:
        wfn = lambda s: w0 * (0.7 + 0.3 * min(1.0, s / 0.25)) * (1 - 0.45 * s)
    else:
        wfn = lambda s: w0 * (0.45 + 0.55 * min(1.0, s / 0.3)) * max(0.0, 1 - s ** 2.2) ** 0.55
    cf = grad(*cols, mid=0.45)
    strip(G, pts, rows, side0, wfn, cell, cf, lambda s: s * alpha_k, fold=fold, twist=twist)
    return pts


def spikelets(G, rng, pts, s0, s1, n, length, width, colfn, alfn, spread=R(28), droop=0.0, mat=0):
    """줄기 끝의 이삭: 작은 마름모 낟알을 줄기 둘레에 엇갈려 붙인다"""
    for i in range(n):
        f = (i + rng.uniform(0.0, 0.6)) / n
        s = s0 + (s1 - s0) * f
        p = at(pts, s)
        t = tangent(pts, s)
        o = Quaternion(t, i * 2.4 + rng.uniform(-0.4, 0.4)) @ t.orthogonal().normalized()
        d = (t * math.cos(spread) + o * math.sin(spread) - UP * droop).normalized()
        sd = d.cross(o).normalized()
        l = length * (0.55 + 0.45 * math.sin(math.pi * min(1.0, 0.15 + f * 0.9))) * rng.uniform(0.8, 1.15)
        w = width * rng.uniform(0.8, 1.2)
        c = colfn(f)
        a = alfn(s)
        c0 = (c[0] * 0.7, c[1] * 0.7, c[2] * 0.7, a)
        c1 = (c[0], c[1], c[2], a)
        v0 = G.vert(p, atlas_uv('stem', 0.5, 0.05), c0)
        v1 = G.vert(p + d * l * 0.45 + sd * w, atlas_uv('stem', 0.0, 0.45), c1)
        v2 = G.vert(p + d * l, atlas_uv('stem', 0.5, 0.95), c1)
        v3 = G.vert(p + d * l * 0.45 - sd * w, atlas_uv('stem', 1.0, 0.45), c1)
        G.face((v0, v1, v2, v3), mat, True)


# ───────────────────────── 지형 풀 ─────────────────────────
def grass_a():
    """짧고 빽빽한 풀 덤불 (~0.35m, 잎 78장, V자 접힘). 어두운 청록, 끝 몇 장은 마름.
    여럿이 모였을 때 땅이 덜 비치도록 바깥 잎은 낮게 누워 넓게 퍼지고, 한쪽으로 살짝 빗긴 듯 비대칭"""
    rng = random.Random(101)
    G = Geo()
    N, R0, Lmax = 78, 0.11, 0.42
    comb = rng.uniform(0, 6.28)                         # 바람에 빗긴 방향
    for i in range(N):
        k = rng.random() ** 0.65
        a = rng.uniform(0, 2 * math.pi)
        root = Vector((math.cos(a) * R0 * k, math.sin(a) * R0 * k, -0.015))
        L = Lmax * (0.95 - 0.3 * k) * rng.uniform(0.72, 1.05)
        if rng.random() < 0.2:
            L *= rng.uniform(0.35, 0.55)                # 아래를 채우는 짧은 잎
        th0 = R(4 + 24 * k ** 1.5 + rng.uniform(-4, 6))      # 바깥 잎도 서서 오르다가
        th1 = th0 + R((28 + 72 * k) * rng.uniform(0.6, 1.25))  # 끝이 둥글게 늘어진다 (분수 모양)
        if rng.random() < 0.07:
            th1 = R(rng.uniform(100, 135))             # 고개 숙인 잎
        az = a + rng.uniform(-0.6, 0.6)
        if rng.random() < 0.35:                         # 일부는 한쪽으로 빗겨 둥근 성게 모양을 깬다
            d = (comb - az + math.pi) % (2 * math.pi) - math.pi
            az += d * 0.5
        base = rng.choice(TEAL) if rng.random() > 0.14 else rng.choice(OLIVE)
        j = rng.uniform(0.75, 1.22)
        tip = scl(base, 1.05 * j)
        if rng.random() < 0.12:
            tip = DRY_TIP
        cols = (scl(base, 0.22), scl(base, 0.62 * j), tip)
        blade(G, rng, root, L, th0, th1, az, rng.uniform(0.006, 0.0098), cols, L / Lmax, fold=0.6, p=1.5 + 0.8 * k,
              rows=[0.0, 0.38, 0.7, 1.0] if L > 0.26 else [0.0, 0.55, 1.0],
              swirl=rng.uniform(-0.4, 0.4), twist=rng.uniform(-1.0, 1.0))
    G.normalize_alpha()
    print("TRIS grass_a", G.tris())
    return finish_foliage("grass_a", [G.build("grass_a", [foliage_mat()])])


def grass_b():
    """키 큰 들풀 (~0.7m): 휘어진 긴 잎 + 이삭 달린 줄기. 청록과 올리브가 섞임"""
    rng = random.Random(202)
    G = Geo()
    Hmax = 0.78
    for i in range(24):
        k = rng.random() ** 0.7
        a = rng.uniform(0, 2 * math.pi)
        root = Vector((math.cos(a) * 0.14 * k, math.sin(a) * 0.14 * k, -0.015))
        L = rng.uniform(0.32, 0.6) * (1.0 - 0.3 * k)
        th0 = R(4 + 20 * k + rng.uniform(-3, 6))
        th1 = th0 + R(rng.uniform(30, 75))
        az = a + rng.uniform(-0.5, 0.5)
        olive = rng.random() < 0.45
        base = rng.choice(OLIVE if olive else TEAL)
        j = rng.uniform(0.8, 1.2)
        tip = scl(base, 1.1 * j) if rng.random() > 0.15 else DRY_TIP
        blade(G, rng, root, L, th0, th1, az, rng.uniform(0.006, 0.0105), (scl(base, 0.22), scl(base, 0.65 * j), tip),
              L / Hmax, rows=[0.0, 0.33, 0.66, 1.0], fold=0.6, p=1.4, swirl=rng.uniform(-0.5, 0.5), twist=rng.uniform(-1.2, 1.2))
    # 이삭 달린 줄기 (끝이 고개를 숙인다)
    for i in range(6):
        a = i * GOLD * 2.0 + rng.uniform(-0.3, 0.3)
        root = Vector((math.cos(a) * 0.05, math.sin(a) * 0.05, -0.01))
        L = rng.uniform(0.6, 0.82)
        th0 = R(rng.uniform(2, 10))
        th1 = th0 + R(rng.uniform(25, 70))
        pts = curve(root, L, th0, th1, a + rng.uniform(-0.4, 0.4), p=3.0, swirl=rng.uniform(-0.3, 0.3))
        sc_ = rng.choice([(0.14, 0.16, 0.08), (0.11, 0.14, 0.1)])
        top = rng.choice([(0.34, 0.33, 0.22), (0.3, 0.32, 0.26), (0.38, 0.34, 0.2)])
        tube(G, pts, [0.0, 0.3, 0.6, 0.8, 1.0], lambda s: 0.0024 * (1 - 0.45 * s), 3,
             grad(scl(sc_, 0.3), sc_, mix(sc_, top, 0.6)), lambda s, L=L: s * L / Hmax)
        spikelets(G, rng, pts, 0.72, 0.995, 20, 0.026, 0.0055, grad(scl(top, 0.7), top, scl(top, 1.25)),
                  lambda s, L=L: s * L / Hmax, spread=R(rng.uniform(14, 24)), droop=0.1)
    G.normalize_alpha()
    print("TRIS grass_b", G.tris())
    return finish_foliage("grass_b", [G.build("grass_b", [foliage_mat()])])


def grass_dead():
    """마른 풀 (지푸라기색): 꺾이고 부러지고 눕고 휜 잎 + 마른 이삭 몇 개"""
    rng = random.Random(303)
    G = Geo()
    Lmax = 0.44
    for i in range(52):
        k = rng.random() ** 0.8
        a = rng.uniform(0, 2 * math.pi)
        root = Vector((math.cos(a) * 0.18 * k, math.sin(a) * 0.18 * k, -0.012))
        L = Lmax * (0.95 - 0.42 * k) * rng.uniform(0.62, 1.05)
        th0 = R(5 + 26 * k + rng.uniform(-4, 9))
        th1 = th0 + R((25 + 60 * k) * rng.uniform(0.6, 1.4))
        az = a + rng.uniform(-0.7, 0.7)
        roll = rng.random()
        kink, blunt, rows = None, False, None
        if roll < 0.34:                                  # 중간에서 꺾여 꺾인 끝이 늘어진다
            sk = rng.uniform(0.3, 0.65)
            kink = (sk, R(rng.uniform(55, 115)))
            rows = sorted({0.0, round(sk, 3), round((sk + 1) / 2, 3), 1.0})
        elif roll < 0.5:                                 # 부러져 뭉툭한 잎
            L *= rng.uniform(0.35, 0.65); blunt = True
            rows = [0.0, 0.5, 1.0]
        elif roll < 0.62:                                # 땅에 누운 잎
            th0 = R(rng.uniform(55, 75)); th1 = R(rng.uniform(88, 96))
            root.z = -0.004
        base = rng.choice(STRAW)
        j = rng.uniform(0.75, 1.15)
        rootc = (0.07, 0.055, 0.04) if rng.random() > 0.25 else (0.06, 0.07, 0.035)
        blade(G, rng, root, L, th0, th1, az, rng.uniform(0.005, 0.009), (rootc, scl(base, 0.75 * j), scl(base, 1.15 * j)),
              L / Lmax, rows=rows, fold=0.5, swirl=rng.uniform(-0.8, 0.8), twist=rng.uniform(-2.0, 2.0), kink=kink, blunt=blunt)
    # 마른 이삭 줄기
    for i in range(3):
        a = i * 2.1 + rng.uniform(-0.3, 0.3)
        root = Vector((math.cos(a) * 0.04, math.sin(a) * 0.04, -0.01))
        L = rng.uniform(0.4, 0.55)
        pts = curve(root, L, R(rng.uniform(4, 14)), R(rng.uniform(30, 80)), a, p=2.5, swirl=rng.uniform(-0.3, 0.3))
        top = rng.choice(STRAW)
        tube(G, pts, [0.0, 0.4, 0.75, 1.0], lambda s: 0.0021 * (1 - 0.4 * s), 3,
             grad((0.08, 0.06, 0.04), scl(top, 0.7), top), lambda s, L=L: s * L / Lmax)
        spikelets(G, rng, pts, 0.78, 0.99, 8, 0.02, 0.004, grad(scl(top, 0.8), scl(top, 1.1), scl(top, 1.3)),
                  lambda s, L=L: s * L / Lmax, spread=R(35), droop=0.1)
    G.normalize_alpha()
    print("TRIS grass_dead", G.tris())
    return finish_foliage("grass_dead", [G.build("grass_dead", [foliage_mat()])])


def fiddlehead(G, rng, root, az, h, r0, col, alpha_k, sides=3):
    """어린 고사리 순: 곧게 올라간 줄기 끝이 앞으로 둥글게 말려 있다"""
    pts = curve(root, h, R(rng.uniform(2, 10)), R(rng.uniform(10, 25)), az, p=2.0, n=8)
    top = pts[-1]
    d = Vector((math.cos(az), math.sin(az), 0))
    c = top + d * r0
    turns = 1.35
    m = 12
    for i in range(1, m + 1):
        u = i / m
        ph = math.pi - u * turns * 2 * math.pi
        rr = r0 * (1 - 0.72 * u)
        pts.append(c + d * (math.cos(ph) * rr) + UP * (math.sin(ph) * rr))
    n = len(pts)
    radii = [0.0055 * (1 - 0.35 * i / n) if i < n - 1 else 0.0 for i in range(n)]
    cols = [mix(scl(col, 0.35), col, i / (n - 1)) for i in range(n)]
    alphas = [alpha_k * min(1.0, i / 8) for i in range(n)]
    tube_rows(G, pts, radii, sides, cols, alphas)


def fern_a():
    """고사리 무리 (~0.6m): 휘어 늘어진 잎 카드 8장을 둥글게 + 말린 어린 순 2개 + 시든 잎 1장"""
    rng = random.Random(404)
    G = Geo()
    Hn = 0.95
    for i in range(9):
        az = i * 2 * math.pi / 9 + rng.uniform(-0.25, 0.25)
        if i < 7:
            L = rng.uniform(0.62, 0.86)
            th0 = R(rng.uniform(16, 34))
            th1 = th0 + R(rng.uniform(55, 80))
        else:                                            # 가운데 어린 잎
            L = rng.uniform(0.4, 0.5)
            th0 = R(rng.uniform(4, 10))
            th1 = th0 + R(rng.uniform(30, 45))
        root = Vector((math.cos(az) * 0.025, math.sin(az) * 0.025, -0.02))
        pts = curve(root, L, th0, th1, az, p=1.4, swirl=rng.uniform(-0.25, 0.25), floor=0.01)
        side0 = Vector((-math.sin(az), math.cos(az), 0))
        W = 0.25 * L
        u_at = lambda s: 0.22 if s <= 0.0 else (0.3 if s >= 1.0 else 1.0)
        base = rng.choice([(0.05, 0.13, 0.06), (0.04, 0.12, 0.075), (0.06, 0.14, 0.055)])
        j = rng.uniform(0.85, 1.2)
        tip = scl(base, 1.35 * j) if rng.random() > 0.25 else (0.17, 0.15, 0.06)
        strip(G, pts, [0.0, 0.1, 0.3, 0.52, 0.74, 0.9, 1.0], side0, lambda s, W=W: W * u_at(s), 'fern',
              grad(scl(base, 0.3), scl(base, 0.9 * j), tip, mid=0.4), lambda s, L=L: s * L / Hn,
              fold=0.32, crease_toward=UP, ufn=u_at, twist=rng.uniform(-0.35, 0.35))
    # 시든 잎: 낮게 누운 갈색 잎
    az = rng.uniform(0, 6.28)
    L = 0.7
    pts = curve(Vector((0, 0, -0.01)), L, R(62), R(96), az, p=1.2, floor=0.012)
    strip(G, pts, [0.0, 0.15, 0.45, 0.75, 1.0], Vector((-math.sin(az), math.cos(az), 0)),
          lambda s: 0.25 * L * (0.22 if s <= 0 else (0.3 if s >= 1 else 1.0)), 'fern',
          grad((0.06, 0.04, 0.02), (0.2, 0.12, 0.05), (0.26, 0.17, 0.07)), lambda s: s * 0.35,
          fold=0.25, crease_toward=UP, ufn=lambda s: 0.22 if s <= 0 else (0.3 if s >= 1 else 1.0), twist=0.6)
    # 어린 순
    for i in range(2):
        az = rng.uniform(0, 6.28)
        fiddlehead(G, rng, Vector((math.cos(az) * 0.02, math.sin(az) * 0.02, -0.01)), az + rng.uniform(-0.5, 0.5),
                   rng.uniform(0.16, 0.26), rng.uniform(0.024, 0.032), (0.11, 0.12, 0.05), 0.3)
    G.normalize_alpha()
    print("TRIS fern_a", G.tris())
    return finish_foliage("fern_a", [G.build("fern_a", [foliage_mat()])])


def leaf_card(G, rng, root, L, th0, th1, az, cell, cols, alpha_k, fold=-0.3, rows=(0.0, 0.5, 1.0), twist=0.0,
              swirl=0.0, wk=0.5, floor=0.006, a0=0.0, amax=1.0):
    """넓은 잎 카드 하나 (칸 비율 그대로, 가운데 잎맥에서 접힘)"""
    pts = curve(root, L, th0, th1, az, p=1.3, swirl=swirl, floor=floor)
    side0 = Vector((-math.sin(az), math.cos(az), 0))
    strip(G, pts, list(rows), side0, lambda s: L * wk, cell, grad(*cols, mid=0.5), lambda s: min(amax, a0 + s * alpha_k),
          fold=fold, crease_toward=-UP if fold < 0 else UP, twist=twist)
    return pts


def weeds():
    """넓은 잎 잡초 낮은 무리: 바깥 잎은 크고 눕고 안쪽 잎은 작고 선다. 녹슨 빛 씨앗 줄기 둘"""
    rng = random.Random(505)
    G = Geo()
    n = 20
    for i in range(n):
        az = i * GOLD + rng.uniform(-0.2, 0.2)
        inner = i / (n - 1)
        L = lerp(0.22, 0.09, inner) * rng.uniform(0.8, 1.2)
        th0 = R(lerp(66, 20, inner) + rng.uniform(-10, 10))
        if inner < 0.3 and rng.random() < 0.4:
            th0 = R(rng.uniform(78, 86))                 # 땅에 눕다시피 한 잎
        th1 = th0 + R(lerp(38, 30, inner) + rng.uniform(-10, 15))
        root = Vector((math.cos(az) * 0.012, math.sin(az) * 0.012, 0.0))
        roll = rng.random()
        cell = 'thorn_leaf' if roll < 0.55 else 'ivy_b'
        if inner < 0.2 and rng.random() < 0.6:
            cols = ((0.05, 0.04, 0.02), (0.15, 0.12, 0.05), (0.18, 0.14, 0.06))      # 누렇게 시든 바깥 잎
            cell = 'leaf_dead' if rng.random() < 0.5 else cell
        elif rng.random() < 0.3:
            cols = ((0.025, 0.02, 0.025), (0.07, 0.045, 0.06), (0.1, 0.07, 0.08))  # 검붉게 물든 잎
        else:
            b = rng.choice([(0.07, 0.13, 0.06), (0.06, 0.12, 0.08), (0.08, 0.14, 0.05)])
            cols = (scl(b, 0.3), b, scl(b, 1.3))
        leaf_card(G, rng, root, L, th0, th1, az, cell, cols, 0.35 + 0.4 * inner, fold=-0.16,
                  rows=(0.0, 0.35, 0.7, 1.0), twist=rng.uniform(-0.5, 0.5), swirl=rng.uniform(-0.3, 0.3), wk=0.34)
    a0 = rng.uniform(0, 6.28)
    for i, L in enumerate((0.34, 0.24)):              # 녹슨 빛 씨앗 줄기 둘: 서로 다른 쪽으로 기울고 끝에 씨앗이 뭉쳐 늘어진다
        a = a0 + i * 2.6
        th0 = R(rng.uniform(12, 22))
        pts = curve(Vector((math.cos(a) * 0.015, math.sin(a) * 0.015, 0)), L, th0, th0 + R(rng.uniform(18, 32)), a, p=1.3,
                    swirl=rng.uniform(-0.5, 0.5))
        tube(G, pts, [0.0, 0.35, 0.7, 1.0], lambda s: 0.0025 * (1 - 0.5 * s), 3, grad((0.05, 0.04, 0.03), (0.14, 0.06, 0.04), (0.2, 0.08, 0.05)),
             lambda s, L=L: s * L / 0.34)
        spikelets(G, rng, pts, 0.45, 0.99, 34, 0.01, 0.0048, grad((0.12, 0.035, 0.02), (0.24, 0.075, 0.035), (0.3, 0.11, 0.05)),
                  lambda s, L=L: s * L / 0.34, spread=R(58), droop=0.18)
    G.normalize_alpha(1.0)
    print("TRIS weeds", G.tris())
    return finish_foliage("weeds", [G.build("weeds", [foliage_mat()])])


def reed():
    """늪 갈대·부들 (~1.3m): 갈대 카드 + 긴 잎 + 부들 이삭 (갈색 원통 + 가는 끝)"""
    rng = random.Random(606)
    G = Geo()
    Hmax = 1.45
    for i in range(7):
        a = i * math.pi / 7 + rng.uniform(-0.2, 0.2)
        rr = rng.uniform(0.0, 0.1); ra = rng.uniform(0, 6.28)
        root = Vector((math.cos(ra) * rr, math.sin(ra) * rr, -0.06))
        H = rng.uniform(0.8, 1.25)
        W = rng.uniform(0.3, 0.4)
        la = rng.uniform(0, 6.28)
        pts = curve(root, H, R(rng.uniform(0, 7)), R(rng.uniform(8, 26)), la, p=2.0)
        b = rng.choice([(0.08, 0.13, 0.08), (0.1, 0.14, 0.07), (0.07, 0.12, 0.1)])
        tip = rng.choice([(0.25, 0.23, 0.12), scl(b, 1.4), (0.2, 0.2, 0.1)])
        uf = lambda s: 0.78 + 0.22 * min(1.0, s / 0.2)
        strip(G, pts, [0.0, 0.2, 0.5, 0.75, 1.0], Vector((math.cos(a), math.sin(a), 0)), lambda s, W=W, uf=uf: W / 2 * uf(s), 'reed',
              grad(scl(b, 0.3), b, tip), lambda s, H=H: max(0.0, s * H - 0.04) / Hmax, fold=0.12, twist=rng.uniform(-0.3, 0.3), ufn=uf)
    for i in range(10):
        a = rng.uniform(0, 6.28)
        root = Vector((math.cos(a) * rng.uniform(0, 0.08), math.sin(a) * rng.uniform(0, 0.08), -0.02))
        L = rng.uniform(0.7, 1.25)
        th0 = R(rng.uniform(2, 12)); th1 = th0 + R(rng.uniform(15, 55))
        kink, rows = None, [0.0, 0.3, 0.6, 0.82, 1.0]
        if rng.random() < 0.3:
            sk = rng.uniform(0.5, 0.72); kink = (sk, R(rng.uniform(70, 120)))
            rows = sorted({0.0, 0.3, round(sk, 3), round((sk + 1) / 2, 3), 1.0})
        b = rng.choice([(0.08, 0.14, 0.09), (0.11, 0.15, 0.07), (0.07, 0.13, 0.11)])
        tip = rng.choice([scl(b, 1.3), (0.28, 0.24, 0.12)])
        blade(G, rng, root, L, th0, th1, a, rng.uniform(0.009, 0.013), (scl(b, 0.3), b, tip), L / Hmax, rows=rows,
              fold=0.55, kink=kink, twist=rng.uniform(-1.0, 1.0), swirl=rng.uniform(-0.3, 0.3))
    for i in range(4):
        a = i * 1.7 + rng.uniform(-0.3, 0.3)
        root = Vector((math.cos(a) * rng.uniform(0.02, 0.07), math.sin(a) * rng.uniform(0.02, 0.07), -0.02))
        H = rng.uniform(1.05, 1.42)
        pts = curve(root, H, R(rng.uniform(0, 5)), R(rng.uniform(5, 14)), rng.uniform(0, 6.28), p=2.0, n=40)
        h0 = (H - 0.29) / H; h1 = (H - 0.12) / H
        stem_c = (0.07, 0.1, 0.05)
        tube(G, pts, [0.0, 0.3, 0.6, h0 + 0.004], lambda s: 0.0045 * (1 - 0.3 * s), 3,
             grad(scl(stem_c, 0.4), stem_c, (0.12, 0.13, 0.06)), lambda s, H=H: s * H / Hmax)
        hs = [h0 + (h1 - h0) * t for t in (0.0, 0.06, 0.2, 0.5, 0.8, 0.94, 1.0)]
        prof = lambda s: 0.0055 + 0.0145 * math.sin(math.pi * min(1.0, max(0.0, (s - h0) / (h1 - h0)))) ** 0.35
        headc = rng.choice([(0.11, 0.06, 0.035), (0.09, 0.05, 0.03), (0.13, 0.075, 0.04)])
        tube(G, pts, hs, prof, 6, grad(scl(headc, 0.8), headc, scl(headc, 0.85)), lambda s, H=H: s * H / Hmax)
        tube(G, pts, [h1 - 0.004, h1 + (1 - h1) * 0.5, 1.0], lambda s: 0.0022 if s < 0.999 else 0.0, 3,
             grad((0.14, 0.12, 0.07), (0.22, 0.18, 0.1), (0.3, 0.25, 0.15)), lambda s, H=H: s * H / Hmax)
    G.normalize_alpha()
    print("TRIS reed", G.tris())
    return finish_foliage("reed", [G.build("reed", [foliage_mat()])])


# ───────────────────────── 흩뿌리는 장식 ─────────────────────────
PETAL_BASE = (0.32, 0.46, 0.46)
PETAL_MID = (0.74, 0.84, 0.9)
PETAL_TIP = (0.9, 0.94, 1.0)

def bell(G, rng, E, A, plen, mats, bud=False, petals=6, segs=3, stamens=True, alpha=1.0):
    """고개 숙인 종 모양 꽃: E 에서 A 방향(꽃 입이 향하는 쪽)으로 꽃잎 카드가 퍼진다. 꽃술은 Glow_Spirit"""
    A = A.normalized()
    X = A.orthogonal().normalized(); Y = A.cross(X)
    rot0 = rng.uniform(0, 6.28)
    rows = [0.0, 0.34, 0.68, 1.0] if segs == 3 else [0.0, 0.5, 1.0]
    for j in range(petals):
        inner = j % 2 == 1
        ang = rot0 + j * 2 * math.pi / petals + rng.uniform(-0.12, 0.12)
        Rj = X * math.cos(ang) + Y * math.sin(ang)
        l = plen * (0.9 if inner else 1.0) * rng.uniform(0.94, 1.05)
        rk = 0.86 if inner else 1.0
        P = []
        for s in rows:
            if bud:
                r = 0.003 + l * 0.3 * math.sin(math.pi * min(1.0, s * 0.92)) ** 0.9
            else:
                r = 0.003 + l * (0.07 + 0.27 * (1 - (1 - s) ** 2.5)) * rk + l * 0.2 * max(0.0, s - 0.68) ** 2 / 0.1
            z = l * s * (1.0 - (0.1 * max(0.0, s - 0.6) / 0.4 if not bud else 0.0))
            P.append(E + A * z + Rj * r)
        side0 = A.cross(Rj)
        hw = [l * 0.56 * (0.45 + 0.55 * min(1.0, s * 2.2)) for s in rows]
        us = [0.45 + 0.55 * min(1.0, s * 2.2) for s in rows]
        cols = [grad(PETAL_BASE, PETAL_MID, PETAL_TIP, mid=0.5)(s) for s in rows]
        if inner:
            cols = [scl(c, 0.92) for c in cols]
        strip_rows(G, P, rows, side0, hw, 'petal', cols, [alpha] * len(rows), fold=0.12, crease_toward=Rj, uspan=us,
                   mat=0, smooth=True)
    # 꽃받침: 꽃 위의 작은 초록 혹
    calyx = [E - A * 0.012, E - A * 0.004, E + A * 0.004]
    tube_rows(G, calyx, [0.0032, 0.0062, 0.0055], 5, [(0.05, 0.1, 0.07), (0.1, 0.16, 0.11), (0.2, 0.28, 0.25)], [alpha] * 3)
    if bud or not stamens:
        return
    gi = mats.index('Glow_Spirit')
    gl = (1, 1, 1, alpha)
    for k in range(5):
        ang = rot0 + k * 2 * math.pi / 5 + 0.4
        Rk = X * math.cos(ang) + Y * math.sin(ang)
        tipp = E + A * plen * rng.uniform(0.48, 0.58) + Rk * plen * 0.06
        mid = E.lerp(tipp, 0.5) + Rk * plen * 0.025
        tube_rows(G, [E + A * 0.004, mid, tipp], [0.0007, 0.0006, 0.0005], 3, [(1, 1, 1)] * 3, [alpha] * 3, mat=gi)
        octa(G, tipp + A * 0.0015, 0.0018, gl, mat=gi, squash=1.6, axis=A)
    # 꽃 속의 빛나는 심 (종 안쪽을 밝힌다)
    octa(G, E + A * plen * 0.3, 0.0065, gl, mat=gi, squash=1.8, axis=A)
    pist = E + A * plen * 0.68
    tube_rows(G, [E + A * 0.004, E + A * plen * 0.4, pist], [0.001, 0.0009, 0.0008], 3, [(1, 1, 1)] * 3, [alpha] * 3, mat=gi)
    octa(G, pist + A * 0.0015, 0.0022, gl, mat=gi, squash=1.0, axis=A)


def flower_lily(lod=0):
    rng = random.Random(707)
    G = Geo()
    names = ['Foliage', 'Glow_Spirit']
    Hmax = 0.66
    # 뿌리 잎: 길고 좁은 띠 잎이 휘어 늘어진다
    for i in range(8 if lod == 0 else 5):
        az = i * GOLD + rng.uniform(-0.2, 0.2)
        L = rng.uniform(0.2, 0.34)
        b = rng.choice([(0.05, 0.12, 0.09), (0.06, 0.13, 0.08), (0.04, 0.11, 0.1)])
        blade(G, rng, Vector((math.cos(az) * 0.02, math.sin(az) * 0.02, -0.01)), L, R(rng.uniform(22, 42)),
              R(rng.uniform(75, 110)), az, rng.uniform(0.011, 0.015), (scl(b, 0.3), b, scl(b, 1.3)), 0.4 * L / 0.34,
              rows=[0.0, 0.35, 0.7, 1.0] if lod == 0 else [0.0, 0.5, 1.0], fold=0.5, twist=rng.uniform(-0.6, 0.6))
    # 꽃대: 곧게 오르다 끝이 갈고리처럼 휘어 꽃이 고개를 숙인다
    nfl = 5
    for i in range(nfl):
        az = i * 2 * math.pi / nfl + rng.uniform(-0.4, 0.4)
        H = rng.uniform(0.38, 0.6)
        root = Vector((math.cos(az) * 0.03, math.sin(az) * 0.03, -0.01))
        th1 = R(rng.uniform(135, 165))
        pts = curve(root, H, R(rng.uniform(4, 12)), th1, az, p=3.6, n=48, swirl=rng.uniform(-0.3, 0.3))
        sc_ = (0.06, 0.12, 0.08)
        srows = [0.0, 0.3, 0.55, 0.72, 0.83, 0.9, 0.945, 0.975, 1.0] if lod == 0 else [0.0, 0.5, 0.8, 0.93, 1.0]
        tube(G, pts, srows, lambda s: 0.0038 * (1 - 0.3 * s), 3 if lod == 0 else 3, grad(scl(sc_, 0.35), sc_, scl(sc_, 1.3)),
             lambda s, H=H: s * H / Hmax)
        E = pts[-1]
        A = (tangent(pts, 1.0, 0.03) * 1.0 - UP * 0.35).normalized()
        bud = (i == 3)
        plen = rng.uniform(0.07, 0.085) * (0.8 if bud else 1.0)
        bell(G, rng, E, A, plen, names, bud=bud, petals=6 if lod == 0 else 4, segs=3 if lod == 0 else 2, stamens=(lod == 0),
             alpha=H / Hmax)
    G.normalize_alpha()
    print("TRIS flower_lily lod%d" % lod, G.tris())
    return G.build("flower_lily_%d" % lod, [foliage_mat(), glow_mat('Glow_Spirit')])

def build_flower_lily():
    return finish_lods("flower_lily", [[flower_lily(0)], [flower_lily(1)]])


def cap_profile(style, Rc, rs, small=False):
    """버섯 갓 단면 (가장자리 → 꼭대기), 아랫면 (가장자리 → 대). small: 줄 수를 줄인 작은 갓"""
    if small:
        if style == 'bell':
            top = [(1.0, -0.22), (0.8, 0.42), (0.45, 0.86), (0.0, 1.02)]
            under = [(1.0, -0.22), (rs / Rc, 0.26)]
        else:
            top = [(1.0, -0.12), (0.82, 0.28), (0.45, 0.5), (0.0, 0.56)]
            under = [(1.0, -0.12), (rs / Rc, 0.0)]
    elif style == 'bell':
        top = [(1.0, -0.22), (0.92, 0.12), (0.76, 0.48), (0.52, 0.78), (0.26, 0.96), (0.0, 1.0)]
        under = [(1.0, -0.22), (0.72, -0.02), (0.45, 0.14), (rs / Rc, 0.24)]
    elif style == 'flat':       # 넓게 펴지고 가장자리가 살짝 들린 갓, 가운데 작은 돌기
        top = [(1.0, 0.0), (0.95, -0.01), (0.82, 0.08), (0.6, 0.19), (0.36, 0.26), (0.14, 0.33), (0.0, 0.37)]
        under = [(1.0, 0.0), (0.72, -0.08), (0.42, -0.06), (rs / Rc, -0.02)]
    else:                       # 가운데가 살짝 솟은 둥근 갓
        top = [(1.0, -0.14), (0.97, 0.04), (0.85, 0.24), (0.64, 0.4), (0.38, 0.5), (0.16, 0.6), (0.0, 0.64)]
        under = [(1.0, -0.14), (0.72, -0.1), (0.42, -0.04), (rs / Rc, 0.0)]
    return [(r * Rc, z * Rc) for r, z in top], [(r * Rc, z * Rc) for r, z in under]

def mushroom(G, rng, base, H, Rc, style, lean_az, lean, cap_cols, stem_col, gill_col, glow_cap=False, spots=0,
             segs=12, stem_sides=6, glow_mat_i=1, gill_glow=False, alpha=0.12, ring=False, stripes=True):
    """버섯 하나: 휜 대 + 회전체 갓(가장자리를 불규칙하게, 윗면에 방사형 결) + 주름 아랫면 + 발광 점"""
    small = Rc < 0.03
    rs = max(0.0028, Rc * 0.17)
    pts = curve(base, H, R(lean * 0.4), R(lean), lean_az, p=1.5, n=16)
    srows = [0.0, 0.35, 1.0] if small else [0.0, 0.1, 0.35, 0.7, 1.0]
    tube(G, pts, srows, lambda s: rs * (1.35 - 0.6 * min(1.0, s / 0.12) * 0.55 - 0.15 * s), 4 if small else stem_sides,
         grad(scl(stem_col, 0.25), stem_col, scl(stem_col, 1.15), mid=0.35), lambda s: alpha * s)
    if ring:
        # 대에 걸친 턱받이 (찢어진 치마처럼 아래로 처진 고리)
        q = at(pts, 0.74); t = tangent(pts, 0.74)
        u = t.orthogonal().normalized(); v = t.cross(u)
        inner, outer = [], []
        rc = scl(stem_col, 1.1)
        for k in range(segs):
            aa = 2 * math.pi * k / segs
            dd = u * math.cos(aa) + v * math.sin(aa)
            inner.append(G.vert(q + dd * rs * 1.02, atlas_uv('solid', 0.5, 0.5), (*rc, alpha * 0.74)))
            outer.append(G.vert(q + dd * rs * rng.uniform(2.0, 2.6) - t * rng.uniform(0.008, 0.016), atlas_uv('solid', 0.5, 0.5),
                                (*scl(rc, 0.7), alpha * 0.74)))
        for k in range(segs):
            k2 = (k + 1) % segs
            G.face((inner[k], inner[k2], outer[k2], outer[k]), 0, True)
    Ptop = pts[-1]
    A = (tangent(pts, 1.0, 0.05) + UP * 1.6).normalized()
    X = A.orthogonal().normalized(); Y = A.cross(X)
    top, under = cap_profile(style, Rc, rs, small)
    ph = [rng.uniform(0, 6.28) for _ in range(4)]
    notch = rng.uniform(0, 6.28) if Rc > 0.035 else None
    def rmod(a):
        m = 1 + 0.07 * math.sin(3 * a + ph[0]) + 0.04 * math.sin(7 * a + ph[1])
        if notch is not None:
            d = abs((a - notch + math.pi) % (2 * math.pi) - math.pi)
            m -= 0.2 * max(0.0, 1 - d / 0.32)
        return m
    def zmod(a):
        return Rc * (0.06 * math.sin(2 * a + ph[2]) + 0.035 * math.sin(5 * a + ph[3]))
    def lathe(prof, colfn, mat, uvfn, flip=False):
        rings = []
        n = len(prof)
        for j, (r, z) in enumerate(prof):
            rimk = (1 - j / (n - 1)) ** 2
            if r < 1e-7:
                c = colfn(j, 0.0)
                rings.append([G.vert(Ptop + A * z, uvfn(0.0, 0.0), (c[0], c[1], c[2], alpha))])
                continue
            ring_ = []
            for k in range(segs):
                a = 2 * math.pi * k / segs
                rr = r * (1 + (rmod(a) - 1) * (rimk if j < n - 1 else 0.3))
                zz = z + zmod(a) * rimk
                p = Ptop + A * zz + (X * math.cos(a) + Y * math.sin(a)) * rr
                c = colfn(j, a)
                ring_.append(G.vert(p, uvfn(a, r), (c[0], c[1], c[2], alpha)))
            rings.append(ring_)
        for j in range(n - 1):
            P0, P1 = rings[j], rings[j + 1]
            for k in range(segs):
                k2 = (k + 1) % segs
                f = (P0[k], P0[k2], P1[0]) if len(P1) == 1 else (P0[k], P0[k2], P1[k2], P1[k])
                G.face(f[::-1] if flip else f, mat, True)
        return rings
    ctop = lambda j, a: mix(cap_cols[1], cap_cols[0], (j / (len(top) - 1)) ** 0.8) if j > 0 else cap_cols[2]
    radial = lambda a, r: atlas_uv('mushroom_gill', 0.5 + 0.48 * (r / Rc) * math.cos(a), 0.5 + 0.48 * (r / Rc) * math.sin(a))
    if glow_cap:
        rings = lathe(top, ctop, glow_mat_i, lambda a, r: atlas_uv('solid', 0.5, 0.5))
        # 가장 바깥 띠(테두리 → 첫 줄)는 어두운 갓 색으로: 빛나는 덩어리가 아니라 버섯 갓으로 보이게
        nb = segs
        for fi in range(len(G.f) - 1, -1, -1):
            idx, m_, sm = G.f[fi]
            if m_ == glow_mat_i and len(idx) == 4 and all(v in rings[0] or v in rings[1] for v in idx):
                G.f[fi] = (idx, 0, sm)
                nb -= 1
                if nb == 0:
                    break
    else:
        lathe(top, ctop, 0, radial if stripes else (lambda a, r: atlas_uv('solid', 0.5, 0.5)))
    lathe(under, lambda j, a: gill_col, glow_mat_i if gill_glow else 0, radial, flip=True)
    # 발광 점: 갓 윗면에 박힌 작고 불규칙한 혹 (가운데 쪽에 많이)
    for i in range(spots):
        a = rng.uniform(0, 2 * math.pi)
        f = rng.uniform(0.25, 0.97) ** 0.7
        jf = f * (len(top) - 1)
        j0 = min(int(jf), len(top) - 2)
        t = jf - j0
        r = lerp(top[j0][0], top[j0 + 1][0], t)
        z = lerp(top[j0][1], top[j0 + 1][1], t)
        rimk = (1 - jf / (len(top) - 1)) ** 2
        rr = r * (1 + (rmod(a) - 1) * rimk)
        zz = z + zmod(a) * rimk
        rad = X * math.cos(a) + Y * math.sin(a)
        c = Ptop + A * zz + rad * rr
        dr = top[j0 + 1][0] - top[j0][0]; dz = top[j0 + 1][1] - top[j0][1]
        nrm = (A * (-dr) + rad * dz).normalized()
        if nrm.dot(A) < 0:
            nrm = -nrm
        sz = Rc * rng.uniform(0.035, 0.085)
        u = nrm.orthogonal().normalized(); v = nrm.cross(u)
        el = rng.uniform(1.0, 1.7)
        cc = (1, 1, 1, alpha)
        uv = atlas_uv('solid', 0.5, 0.5)
        apex = G.vert(c + nrm * sz * 0.4, uv, cc)
        ring_ = [G.vert(c - nrm * sz * 0.2 + (u * math.cos(q * math.pi / 2) * el + v * math.sin(q * math.pi / 2)) * sz *
                        rng.uniform(0.8, 1.2), uv, cc) for q in range(4)]
        for q in range(4):
            G.face((ring_[q], ring_[(q + 1) % 4], apex), glow_mat_i, True)


def mushroom_glow(lod=0):
    """보라 발광 버섯 무리 (9개): 큰 것은 결이 있는 어두운 보라 갓에 빛나는 점, 작은 종 모양은 갓 전체가 빛난다"""
    rng = random.Random(1101)
    G = Geo()
    CAP_DARK = ((0.03, 0.012, 0.05), (0.14, 0.055, 0.21), (0.24, 0.11, 0.33))      # (가운데, 가장자리, 테두리)
    CAP_MID = ((0.045, 0.016, 0.065), (0.19, 0.08, 0.27), (0.3, 0.14, 0.4))
    STEM = (0.36, 0.3, 0.42)
    GILL = (0.42, 0.25, 0.55)
    seg = 13 if lod == 0 else 8
    specs = [  # (x, y, 대 높이, 갓 반지름, 모양, 빛나는 갓, 점 수, 턱받이)
        (0.015, 0.02, 0.16, 0.074, 'flat', False, 16, True),
        (-0.06, -0.025, 0.105, 0.046, 'convex', False, 10, False),
        (0.068, -0.038, 0.13, 0.04, 'bell', False, 7, False),
        (-0.022, -0.075, 0.075, 0.02, 'bell', True, 0, False),
        (0.088, 0.045, 0.062, 0.017, 'bell', True, 0, False),
        (-0.082, 0.05, 0.088, 0.024, 'bell', False, 3, False),
        (0.035, -0.092, 0.042, 0.013, 'convex', True, 0, False),
        (-0.098, -0.062, 0.03, 0.011, 'bell', True, 0, False),
        (0.11, -0.01, 0.036, 0.012, 'convex', True, 0, False),
    ]
    if lod > 0:
        specs = specs[:6]
    for (x, y, H, Rc, style, gc, sp, ring) in specs:
        lean_az = math.atan2(y, x) + rng.uniform(-0.5, 0.5)
        lean = rng.uniform(8, 24) + (10 if Rc < 0.03 else 0)
        cols = CAP_DARK if rng.random() < 0.6 else CAP_MID
        mushroom(G, rng, Vector((x, y, -0.012)), H, Rc, style, lean_az, lean, cols, STEM, GILL, glow_cap=gc,
                 spots=sp if lod == 0 else sp // 2, segs=seg if Rc > 0.03 else (7 if lod == 0 else 5), stem_sides=6 if lod == 0 else 4,
                 glow_mat_i=1, alpha=0.12, ring=ring and lod == 0)
    print("TRIS mushroom_glow lod%d" % lod, G.tris())
    return G.build("mushroom_glow_%d" % lod, [foliage_mat(), glow_mat('Glow_Soul')])

def build_mushroom_glow():
    return finish_lods("mushroom_glow", [[mushroom_glow(0)], [mushroom_glow(1)]])


def bracket(G, rng, P, out, Rb, thick, mats, segs=7):
    """선반 버섯 하나: 그루터기 표면 P 에 붙어 out 쪽으로 반달 모양으로 뻗는다.
    윗면은 볼록하고 동심원 띠무늬(검은 초록 → 올리브 → 창백한 연두 가장자리), 아랫면은 Glow_Toxic"""
    out = Vector((out.x, out.y, 0)).normalized()
    tan = UP.cross(out).normalized()
    gi = mats.index('Glow_Toxic')
    ph = [rng.uniform(0, 6.28) for _ in range(3)]
    def rim(a):
        return Rb * (1 - 0.1 * math.cos(2 * a) + 0.07 * math.sin(4 * a + ph[0]) + 0.04 * math.sin(7 * a + ph[1])) * \
            (0.55 + 0.45 * math.cos(a * 0.5) ** 0.5)
    angs = [R(-96 + 192 * k / (segs - 1)) for k in range(segs)]
    tops = [0.06, 0.3, 0.52, 0.7, 0.86, 1.0]
    bands = [(0.015, 0.018, 0.008), (0.05, 0.055, 0.02), (0.022, 0.026, 0.01), (0.08, 0.088, 0.028), (0.03, 0.036, 0.012),
             (0.17, 0.2, 0.06)]
    steps = [0.0, 0.18, 0.0, 0.16, 0.0, 0.1]
    uv = atlas_uv('solid', 0.5, 0.5)
    def pos(a, f, z):
        rr = rim(a) * f
        return P + out * (math.cos(a) * rr) + tan * (math.sin(a) * rr) + UP * z
    T = []
    for j, f in enumerate(tops):
        T.append([G.vert(pos(a, f, thick * (1.0 - 0.9 * f ** 1.2 + steps[j]) - Rb * 0.12 * f * f + 0.005 * math.sin(3 * a + ph[2]) * f),
                         uv, (*bands[j], 0.1)) for a in angs])
    U = []
    for f in (1.0, 0.06):
        U.append([G.vert(pos(a, f * 0.97, thick * 0.04 - Rb * 0.15 * f * f - thick * 0.35 * (1 - f) + 0.005 * math.sin(3 * a + ph[2]) * f),
                         uv, (1, 1, 1, 0.1)) for a in angs])
    for j in range(len(T) - 1):
        for k in range(segs - 1):
            G.face((T[j][k], T[j][k + 1], T[j + 1][k + 1], T[j + 1][k]), 0, True)
    rimrow = [G.vert(G.v[U[0][k]], uv, (0.26, 0.3, 0.09, 0.1)) for k in range(segs)]
    for k in range(segs - 1):
        G.face((T[-1][k], T[-1][k + 1], rimrow[k + 1], rimrow[k]), 0, True)
        G.face((U[0][k + 1], U[0][k], U[1][k], U[1][k + 1]), gi, True)


def mushroom_toxic():
    """초록 독기 버섯: 썩은 그루터기(조각·굽기) 옆구리에 층층이 붙은 선반 버섯(아랫면 Glow_Toxic) + 발치의 작은 독버섯"""
    rng = random.Random(1201)
    # 그루터기 몸통 + 뿌리
    body = cyl(0.125, 0.36, (0, 0, 0.14), 32, r2=0.108)
    parts = [body]
    gv, ge, gd = [(0, 0, -0.1), (0, 0, 0.5)], [(0, 1)], [(0, 0, 1), (0, 0, 1)]
    for i in range(4):
        a = i * 2 * math.pi / 4 + rng.uniform(-0.45, 0.45)
        L = rng.uniform(0.13, 0.19)
        tilt = R(180 - rng.uniform(66, 80))           # 굵은 쪽이 몸통 안, 가는 끝이 바깥 아래로
        c = cyl(rng.uniform(0.04, 0.05), L, (0, 0, 0), 12, r2=0.012)
        c.rotation_euler = (0, tilt, a)
        d = Vector((math.cos(a) * math.sin(tilt), math.sin(a) * math.sin(tilt), math.cos(tilt)))
        st = Vector((math.cos(a) * 0.075, math.sin(a) * 0.075, 0.06))
        c.location = st + d * (L / 2)
        xf_all(c)
        parts.append(c)
        d = tuple(d)
        k = len(gv)
        gv += [(math.cos(a) * 0.1, math.sin(a) * 0.1, 0.05), (math.cos(a) * 0.32, math.sin(a) * 0.32, -0.05)]
        ge.append((k, k + 1)); gd += [d, d]
    body = join(parts)
    remesh(body, 0.01)
    # 부러진 윗면: 기운 평면 두 개로 쳐내 뾰족한 등성이를 남긴다
    cut(body, [box(0.6, 0.6, 0.4, (0.16, 0.02, 0.48), rot=(R(8), R(-24), R(10))),
               box(0.6, 0.6, 0.4, (-0.17, -0.03, 0.5), rot=(R(-6), R(28), R(-15))),
               box(0.12, 0.6, 0.3, (0.02, 0.0, 0.43), rot=(R(20), 0, R(70)))])
    # 썩어 파인 속
    cut(body, [cyl(0.062, 0.3, (0.012, 0.006, 0.36), 18, r2=0.045), sphere(0.05, (0.03, -0.02, 0.24), (1, 0.8, 0.9), 2)])
    chip(body, rng, 14, (0.02, 0.05), sharp_deg=30, bite=0.4)
    origin0(body)
    remesh(body, 0.0055)
    me = bpy.data.meshes.new("guide"); me.from_pydata(gv, ge, [])
    at_ = me.attributes.new("dir", 'FLOAT_VECTOR', 'POINT')
    for i, d in enumerate(gd):
        at_.data[i].vector = d
    guide = link(bpy.data.objects.new("guide", me))
    surface(body, [{'t': 'lumps', 'scale': 4.0, 'amp': 0.006},
                   {'t': 'bark', 'scale': 18, 'width': 0.11, 'depth': 0.009, 'stretch': 0.1},
                   {'t': 'fissure', 'scale': 5.0, 'width': 0.012, 'depth': 0.006, 'cover': 0.55},
                   {'t': 'pits', 'scale': 30, 'depth': 0.002, 'cover': 0.5},
                   {'t': 'grain', 'scale': 140, 'amp': 0.0007}], seed=5, guide=guide)
    delete(guide)
    set_mat(body, paint("stump", 'bark', moss=0.85, moss_color=(0.06, 0.11, 0.07), dirt=0.45, streaks=0.0, streak_dir='grain',
                        cracks=0.0, edge=0.75, ao=0.2))
    low = decimated(body, 1700)
    # 버섯 (Foliage + Glow_Toxic)
    G = Geo()
    mats = ['Foliage', 'Glow_Toxic']
    def surf_r(z):
        return lerp(0.125, 0.108, max(0.0, min(1.0, (z + 0.04) / 0.36)))
    shelves = [(R(-102), 0.075, 0.07, 0.04), (R(-82), 0.14, 0.058, 0.034), (R(-122), 0.19, 0.046, 0.028),
               (R(32), 0.1, 0.052, 0.032), (R(56), 0.165, 0.04, 0.026)]
    for a, z, Rb, th in shelves:
        out = Vector((math.cos(a), math.sin(a), 0))
        P = out * (surf_r(z) - 0.012) + UP * z
        bracket(G, rng, P, out, Rb, th, mats)
    # 발치의 작은 독버섯 (어두운 올리브 갓 + 빛나는 주름)
    TOX_CAP = ((0.02, 0.025, 0.008), (0.08, 0.1, 0.03), (0.16, 0.2, 0.05))
    for (x, y, H, Rc, style) in [(0.06, -0.19, 0.075, 0.026, 'bell'), (-0.03, -0.2, 0.048, 0.019, 'bell'),
                                 (0.19, 0.03, 0.058, 0.022, 'bell')]:
        mushroom(G, rng, Vector((x, y, -0.005)), H, Rc, style, math.atan2(y, x), rng.uniform(10, 22), TOX_CAP, (0.2, 0.22, 0.13),
                 (1, 1, 1), glow_cap=False, spots=0, segs=8, stem_sides=5, glow_mat_i=1, gill_glow=True, alpha=0.1)
    fung = G.build("toxic_fungi", [foliage_mat(), glow_mat('Glow_Toxic')])
    print("TRIS mushroom_toxic fungi", G.tris())
    return finish("mushroom_toxic", [body], [low], extras=[fung], size=1024, extr=0.025, lod1=0.4)


def lotus_glow():
    """물 위에 뜬 영혼 연꽃: 갈라진 둥근 잎 3장 + 꽃 1 (바깥 꽃잎은 창백한 보라, 속꽃잎·씨방은 Glow_Soul) + 봉오리 1. z=0 이 수면"""
    rng = random.Random(1301)
    G = Geo()
    mats = ['Foliage', 'Glow_Soul']
    gi = 1
    # 잎
    pads = [((0.0, 0.0), 0.17, R(200)), ((0.27, 0.1), 0.13, R(330)), ((-0.12, 0.26), 0.11, R(60))]
    for (cx, cy), Rp, notch in pads:
        segs = 22
        nw = R(rng.uniform(16, 26))
        rings = [0.0, 0.33, 0.68, 0.9, 1.0]
        ph = [rng.uniform(0, 6.28) for _ in range(3)]
        lift_a = rng.uniform(0, 6.28)
        C = Vector((cx, cy, 0.004))
        grid = []
        for j, f in enumerate(rings):
            row = []
            if f == 0.0:
                row = [G.vert(C + UP * -0.002, atlas_uv('mushroom_gill', 0.5, 0.5), (0.03, 0.06, 0.04, 0.05))]
                grid.append(row)
                continue
            for k in range(segs + 1):
                a = notch + nw / 2 + (2 * math.pi - nw) * k / segs
                rr = Rp * f * (1 + 0.035 * math.sin(4 * a + ph[0]) + 0.02 * math.sin(9 * a + ph[1]))
                d = abs((a - lift_a + math.pi) % (2 * math.pi) - math.pi)
                lift = 0.022 * max(0.0, 1 - d / 1.1) ** 1.5 * f ** 5 + 0.004 * f ** 6 * (1 + math.sin(6 * a + ph[2]))
                p = C + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.002 * (1 - f) + lift))
                edge = f ** 4
                col = mix((0.035, 0.075, 0.05), (0.07, 0.13, 0.075), f)
                col = mix(col, (0.17, 0.06, 0.13), edge * min(1.0, lift / 0.008) * 0.8 + 0.15 * edge)
                fr = 0.06 + 0.5 * f
                row.append(G.vert(p, atlas_uv('mushroom_gill', 0.5 + 0.48 * fr * math.cos(a), 0.5 + 0.48 * fr * math.sin(a)),
                                  (col[0], col[1], col[2], 0.05 + 0.1 * f)))
            grid.append(row)
        for j in range(len(rings) - 1):
            for k in range(segs):
                if j == 0:
                    G.face((grid[0][0], grid[1][k], grid[1][k + 1]), 0, True)
                else:
                    G.face((grid[j][k], grid[j + 1][k], grid[j + 1][k + 1], grid[j][k + 1]), 0, True)
    # 꽃
    F = Vector((0.06, 0.07, 0.012))
    rot0 = rng.uniform(0, 6.28)
    whorls = [(9, 0.088, 70, 'card'), (8, 0.076, 44, 'card'), (7, 0.052, 22, 'glow')]
    for wi, (n, plen, tilt, kind) in enumerate(whorls):
        for j in range(n):
            ang = rot0 + j * 2 * math.pi / n + wi * 0.35 + rng.uniform(-0.1, 0.1)
            Rj = Vector((math.cos(ang), math.sin(ang), 0))
            th0 = R(tilt + rng.uniform(-6, 6))
            th1 = th0 - R(rng.uniform(22, 34))
            l = plen * rng.uniform(0.9, 1.08)
            pts = curve(F + Rj * 0.006 * (3 - wi), l, th0, th1, ang, p=1.4, n=12)
            side0 = Vector((-math.sin(ang), math.cos(ang), 0))
            ct = Rj * math.cos(th0) - UP * math.sin(th0)
            if kind == 'card':
                rows = [0.0, 0.33, 0.66, 1.0]
                base = (0.2, 0.1, 0.3) if wi == 0 else (0.3, 0.16, 0.42)
                mid = (0.62, 0.5, 0.86) if wi == 0 else (0.72, 0.62, 0.94)
                tip = (0.88, 0.84, 1.0)
                us = [0.45 + 0.55 * min(1.0, s * 2.2) for s in rows]
                strip(G, pts, rows, side0, lambda s, l=l: l * 0.5 * (0.45 + 0.55 * min(1.0, s * 2.2)), 'petal',
                      grad(base, mid, tip), lambda s: 0.2 + 0.1 * s, fold=0.25, crease_toward=ct,
                      ufn=lambda s: 0.45 + 0.55 * min(1.0, s * 2.2))
            else:
                # 발광 속꽃잎: 텍스처가 없으므로 뾰족한 잎 모양을 정점으로
                rows = [0.0, 0.45, 0.8, 1.0]
                wf = lambda s, l=l: l * (0.1 + 0.32 * math.sin(math.pi * min(1.0, s * 0.85 + 0.08))) if s < 1 else 0.0
                strip(G, pts, rows, side0, wf, 'solid', lambda s: (1, 1, 1), lambda s: 0.2 + 0.05 * s, fold=0.3, crease_toward=ct, mat=gi)
    # 씨방 (빛나는 작은 원통)
    pod = [F + UP * 0.0, F + UP * 0.016, F + UP * 0.019]
    tube_rows(G, pod, [0.011, 0.013, 0.0], 8, [(1, 1, 1)] * 3, [0.2] * 3, mat=gi)
    # 봉오리
    B0 = Vector((-0.16, -0.08, 0.0))
    stalk = curve(B0, 0.07, R(25), R(5), R(40), p=1.5, n=6)
    tube(G, stalk, [0.0, 0.5, 1.0], lambda s: 0.0042, 4, lambda s: (0.06, 0.1, 0.06), lambda s: 0.1 + 0.15 * s)
    Bt = stalk[-1]
    for j in range(5):
        ang = j * 2 * math.pi / 5 + 0.3
        Rj = Vector((math.cos(ang), math.sin(ang), 0))
        pts = curve(Bt + Rj * 0.003, 0.06, R(32), R(-12), ang, p=1.2, n=10)
        side0 = Vector((-math.sin(ang), math.cos(ang), 0))
        strip(G, pts, [0.0, 0.4, 0.75, 1.0], side0, lambda s: 0.026 * (0.45 + 0.55 * min(1.0, s * 2.2)), 'petal',
              grad((0.15, 0.08, 0.22), (0.45, 0.3, 0.68), (0.78, 0.62, 0.98)), lambda s: 0.3, fold=0.25, crease_toward=Rj,
              ufn=lambda s: 0.45 + 0.55 * min(1.0, s * 2.2))
    print("TRIS lotus_glow", G.tris())
    o = G.build("lotus_glow", [foliage_mat(), glow_mat('Glow_Soul')])
    return finish_foliage("lotus_glow", [o])


# ───────────────────────── 지형 나무 (덤불) ─────────────────────────
def thorn(G, p, t, o, length, rb, col, alpha):
    """가시 하나: 뿌리 쪽으로 젖혀진 납작한 세모 (줄기 옆면에서 보이게 줄기 방향과 나란히)"""
    d = (o * 0.85 - t * 0.5).normalized()
    uv = atlas_uv('stem', 0.5, 0.5)
    c0 = (col[0] * 0.6, col[1] * 0.6, col[2] * 0.6, alpha)
    a = G.vert(p - d * rb * 0.5 - t * rb * 1.6, uv, c0)
    b = G.vert(p - d * rb * 0.5 + t * rb * 1.6, uv, c0)
    apex = G.vert(p + d * length, uv, (col[0], col[1], col[2], alpha))
    G.face((a, b, apex), 0, False)


def bramble(lod=0):
    """가시덤불 (~1.2m): 둥글게 휘어 땅으로 늘어지는 가시 줄기(검붉은 갈색) 여러 개 + 세 갈래 겹잎 + 검은 열매.
    잎은 가운데 잎맥 없이 납작한 카드(삼각형 2개)로 아껴 잎 수를 늘린다"""
    rng = random.Random(909)
    G = Geo()
    canes = 13 if lod == 0 else 8
    CANE = [(0.075, 0.03, 0.045), (0.09, 0.04, 0.05), (0.07, 0.035, 0.06)]
    LEAF = [((0.02, 0.04, 0.025), (0.05, 0.11, 0.06), (0.08, 0.15, 0.08)),
            ((0.02, 0.04, 0.03), (0.04, 0.1, 0.075), (0.07, 0.14, 0.1)),
            ((0.04, 0.015, 0.03), (0.13, 0.04, 0.09), (0.18, 0.06, 0.12)),
            ((0.04, 0.03, 0.015), (0.15, 0.09, 0.035), (0.2, 0.12, 0.04)),
            ((0.06, 0.04, 0.02), (0.22, 0.15, 0.07), (0.26, 0.18, 0.08))]
    LEAF_W = [0.34, 0.26, 0.24, 0.1, 0.06]
    Hn = 1.15
    tips = []

    def leaf_node(p, t, size_k=1.0):
        o = Quaternion(t, rng.uniform(0, 6.28)) @ t.orthogonal().normalized()
        d = (o + UP * 0.8 + t * 0.3).normalized()
        q = p + d * 0.02 * size_k
        th, az = dir_angles(d)
        cols = rng.choices(LEAF, LEAF_W)[0]
        for m, da in enumerate([0.0, R(62), R(-62)]):
            l = rng.uniform(0.07, 0.1) * size_k * (1.12 if m == 0 else 0.9)
            th_l = max(R(35), min(R(115), th + R(rng.uniform(20, 45))))
            leaf_card(G, rng, q, l, th_l, th_l + R(rng.uniform(10, 25)), az + da + rng.uniform(-0.2, 0.2), 'thorn_leaf', cols, 0.03,
                      fold=0.0, rows=(0.0, 1.0), twist=rng.uniform(-0.6, 0.6), wk=0.5, floor=0.02,
                      a0=min(0.2, 0.2 * q.z / Hn), amax=0.2)

    def cane(root, L, th0, th1, az, r0, depth, p=1.2):
        pts = curve(root, L, th0, th1, az, p=p, n=40, swirl=rng.uniform(-0.6, 0.6), floor=0.015,
                    wobble=0.35 if depth == 0 else 0.2, rng=rng)
        if depth == 0:
            srows = [0.0, 0.3, 0.55, 0.72, 0.85, 0.94, 1.0] if lod == 0 else [0.0, 0.5, 0.8, 1.0]
        else:
            srows = [0.0, 0.5, 1.0]
        c = rng.choice(CANE)
        tube(G, pts, srows, lambda s: r0 * (1 - 0.62 * s), 3, grad(scl(c, 0.6), c, scl(c, 1.5), mid=0.5),
             lambda s: min(0.2, 0.2 * at(pts, s).z / Hn))
        step = 0.11 if lod == 0 else 0.25
        s = rng.uniform(0.02, 0.06)
        while s < 0.97:
            p = at(pts, s); t = tangent(pts, s)
            o = Quaternion(t, rng.uniform(0, 6.28)) @ t.orthogonal().normalized()
            thorn(G, p + o * r0 * (1 - 0.62 * s) * 0.6, t, o, 0.015 * (1 - 0.4 * s) + 0.005, 0.0028 * (1 - 0.4 * s),
                  (0.46, 0.3, 0.24), min(0.2, 0.2 * p.z / Hn))
            s += step / L * rng.uniform(0.7, 1.3)
        s = rng.uniform(0.12, 0.22)
        lstep = 0.2 if lod == 0 else 0.32
        while s < 0.98:
            leaf_node(at(pts, s), tangent(pts, s), 0.85 + 0.25 * s)
            s += lstep / L * rng.uniform(0.75, 1.25)
        return pts

    for i in range(canes):
        az = i * GOLD * 2 + rng.uniform(-0.3, 0.3)
        root = Vector((math.cos(az) * 0.09, math.sin(az) * 0.09, -0.03))
        if rng.random() < 0.82:                         # 높이 솟았다가 둥글게 휘어 내려오는 줄기
            L = rng.uniform(1.0, 1.45); th0 = R(rng.uniform(8, 26)); th1 = R(rng.uniform(100, 145)); pp = 2.0
        else:
            L = rng.uniform(0.95, 1.2); th0 = R(rng.uniform(4, 14)); th1 = R(rng.uniform(45, 75)); pp = 1.4
        pts = cane(root, L, th0, th1, az, 0.0085, 0, pp)
        if lod == 0:
            s = rng.uniform(0.3, 0.6)
            p = at(pts, s); t = tangent(pts, s)
            th, a2 = dir_angles(t)
            sp = cane(p, rng.uniform(0.25, 0.4), max(R(10), th - R(rng.uniform(25, 50))), th + R(rng.uniform(20, 60)),
                      a2 + rng.choice([-1, 1]) * rng.uniform(0.5, 1.2), 0.0045, 1)
            tips.append(sp[-1])
        else:
            tips.append(pts[-1])
    for k, tp in enumerate(tips[:4 if lod == 0 else 2]):
        for m in range(3 if lod == 0 else 1):
            ripe = rng.random() < 0.7
            col = (0.035, 0.012, 0.045, 0.15) if ripe else (0.2, 0.025, 0.035, 0.15)
            octa(G, tp + Vector((rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02), rng.uniform(-0.025, 0.0))),
                 rng.uniform(0.007, 0.0095), col, squash=1.25)
    print("TRIS bramble lod%d" % lod, G.tris())
    return G.build("bramble_%d" % lod, [foliage_mat()])

def build_bramble():
    return finish_lods("bramble", [[bramble(0)], [bramble(1)]])


def bush_dead(lod=0):
    """잎 없는 잔가지 덤불 (~1.1m): 밑동에서 바깥으로 벌어지며 뒤틀려 갈라지는 가지, 끝은 바랜 회색.
    시든 잎 몇 장과 작은 거미줄 하나 (버려진 느낌)"""
    rng = random.Random(1001)
    G = Geo()
    Hn = 1.2
    BARK = ((0.05, 0.04, 0.045), (0.12, 0.1, 0.1), (0.25, 0.22, 0.23))
    maxd = 3 if lod == 0 else 2
    NSEG = [4, 3, 2, 2] if lod == 0 else [3, 2, 2]
    KIDS = [3, 2, 1, 0] if lod == 0 else [2, 2, 0]
    twig_tips = []

    def branch(p, d, L, r, depth):
        nseg = NSEG[depth]
        P = [Vector(p)]
        dd = Vector(d)
        for i in range(nseg):
            dd = (dd + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.5, 1.0))) * 0.3 + UP * 0.1).normalized()
            q = P[-1] + dd * (L / nseg)
            if q.z < 0.02 and i > 0:
                q.z = 0.02
            P.append(q)
        n = len(P)
        radii = [r * (1 - 0.55 * i / (n - 1)) for i in range(n)]
        radii[-1] = 0.0
        g = lambda i: min(1.0, (depth + i / (n - 1)) / (maxd + 1))
        cols = [mix(BARK[0], BARK[1], g(i) * 2) if g(i) < 0.5 else mix(BARK[1], BARK[2], (g(i) - 0.5) * 2) for i in range(n)]
        tube_rows(G, P, radii, 4 if (depth == 0 and lod == 0) else 3, cols, [min(0.2, 0.2 * q.z / Hn) for q in P])
        if depth >= maxd:
            twig_tips.append((P[-1], (P[-1] - P[-2]).normalized()))
            return
        for k in range(KIDS[depth]):
            i = rng.randint(1, n - 2)
            base_d = (P[i + 1] - P[i - 1]).normalized()
            ax = Quaternion(base_d, rng.uniform(0, 6.28)) @ base_d.orthogonal().normalized()
            nd = (Quaternion(ax, R(rng.uniform(22, 48))) @ base_d + UP * 0.15).normalized()
            branch(P[i], nd, L * rng.uniform(0.6, 0.8), radii[i] * 0.7, depth + 1)

    ns = 6 if lod == 0 else 5
    for i in range(ns):
        az = i * 2 * math.pi / ns + rng.uniform(-0.35, 0.35)
        tilt = R(rng.uniform(18, 40))
        d = Vector((math.cos(az) * math.sin(tilt), math.sin(az) * math.sin(tilt), math.cos(tilt)))
        branch(Vector((math.cos(az) * 0.03, math.sin(az) * 0.03, -0.04)), d, rng.uniform(0.52, 0.7), 0.014, 0)
    if lod == 0:
        for k in range(5):
            p, d = twig_tips[rng.randrange(len(twig_tips))]
            th, az = dir_angles(d)
            leaf_card(G, rng, p, rng.uniform(0.04, 0.06), R(rng.uniform(100, 150)), R(rng.uniform(150, 175)), az + rng.uniform(-1, 1),
                      'leaf_dead', ((0.05, 0.035, 0.02), (0.16, 0.1, 0.05), (0.2, 0.13, 0.06)), 0.03, fold=-0.3,
                      rows=(0.0, 0.5, 1.0), twist=rng.uniform(-1, 1), wk=0.5, floor=0.02, a0=min(0.2, 0.2 * p.z / Hn), amax=0.2)
        pairs = [(a[0], b[0]) for i, a in enumerate(twig_tips) for b in twig_tips[i + 1:]
                 if 0.12 < (a[0] - b[0]).length < 0.22 and 0.35 < min(a[0].z, b[0].z) < 0.75]
        if pairs:
            a, b = pairs[len(pairs) // 2]
            mid = (a + b) * 0.5 - UP * 0.08
            u = (a - mid) * 0.85; v = (b - mid) * 0.85
            k0 = G.vert(mid, atlas_uv('web_corner', 0, 0), (0.75, 0.77, 0.88, min(0.2, 0.2 * mid.z / Hn)))
            k1 = G.vert(mid + u, atlas_uv('web_corner', 1, 0), (0.75, 0.77, 0.88, min(0.2, 0.2 * a.z / Hn)))
            k2 = G.vert(mid + u + v, atlas_uv('web_corner', 1, 1), (0.75, 0.77, 0.88, 0.2))
            k3 = G.vert(mid + v, atlas_uv('web_corner', 0, 1), (0.75, 0.77, 0.88, min(0.2, 0.2 * b.z / Hn)))
            G.face((k0, k1, k2, k3), 0, False)
    print("TRIS bush_dead lod%d" % lod, G.tris())
    return G.build("bush_dead_%d" % lod, [foliage_mat()])

def build_bush_dead():
    return finish_lods("bush_dead", [[bush_dead(0)], [bush_dead(1)]])


BUILDERS = [
    ("grass_a", grass_a), ("grass_b", grass_b), ("grass_dead", grass_dead), ("fern_a", fern_a), ("weeds", weeds), ("reed", reed),
    ("flower_lily", build_flower_lily), ("mushroom_glow", build_mushroom_glow), ("mushroom_toxic", mushroom_toxic),
    ("lotus_glow", lotus_glow), ("bramble", build_bramble), ("bush_dead", build_bush_dead),
]

_DETAIL = {"kind": "detail", "collider": "none", "sink": 0.0, "tilt": 6, "align": True, "cull": 0.0, "shadows": False}
META = {
    "grass_a":    dict(_DETAIL, tags=["foliage", "nature"], footprint=0.2, scale=[0.8, 1.3]),
    "grass_b":    dict(_DETAIL, tags=["foliage", "nature"], footprint=0.25, scale=[0.8, 1.25]),
    "grass_dead": dict(_DETAIL, tags=["foliage", "nature", "grave"], footprint=0.22, scale=[0.8, 1.3]),
    "fern_a":     dict(_DETAIL, tags=["foliage", "nature"], footprint=0.4, scale=[0.75, 1.3]),
    "weeds":      dict(_DETAIL, tags=["foliage", "nature", "ruin", "path"], footprint=0.22, scale=[0.8, 1.35]),
    "reed":       dict(_DETAIL, tags=["foliage", "swamp"], footprint=0.3, scale=[0.85, 1.25], tilt=4, align=False),
    "flower_lily": {"kind": "scatter", "tags": ["foliage", "nature", "grave"], "collider": "none", "footprint": 0.3, "sink": 0.01,
                    "tilt": 6, "align": True, "scale": [0.85, 1.2], "cull": 0.02, "shadows": True},
    "mushroom_glow": {"kind": "scatter", "tags": ["foliage", "nature", "light"], "collider": "none", "footprint": 0.25, "sink": 0.01,
                      "tilt": 5, "align": True, "scale": [0.8, 1.4], "cull": 0.02, "shadows": True,
                      "light": {"offset": [0.0, -0.02, 0.12], "color": [0.62, 0.35, 1.0], "intensity": 1.2, "range": 2.2}},
    "mushroom_toxic": {"kind": "scatter", "tags": ["foliage", "nature", "swamp"], "collider": "none", "footprint": 0.4, "sink": 0.03,
                       "tilt": 4, "align": True, "scale": [0.85, 1.25], "cull": 0.015, "shadows": True,
                       "light": {"offset": [-0.03, -0.2, 0.12], "color": [0.45, 1.0, 0.35], "intensity": 1.0, "range": 2.0}},
    "lotus_glow": {"kind": "scatter", "tags": ["swamp"], "collider": "none", "footprint": 0.45, "sink": 0.0, "tilt": 0,
                   "align": False, "scale": [0.8, 1.3], "cull": 0.015, "shadows": False,
                   "light": {"offset": [0.06, 0.07, 0.06], "color": [0.62, 0.35, 1.0], "intensity": 2.0, "range": 3.0}},
    "bramble":   {"kind": "tree", "tags": ["foliage", "nature", "grave", "ruin"], "collider": "none", "footprint": 0.8, "sink": 0.03,
                  "tilt": 0, "align": False, "scale": [0.8, 1.3], "cull": 0.006, "shadows": True},
    "bush_dead": {"kind": "tree", "tags": ["foliage", "nature", "grave"], "collider": "none", "footprint": 0.6, "sink": 0.03,
                  "tilt": 0, "align": False, "scale": [0.8, 1.3], "cull": 0.006, "shadows": True},
}

_NAMES = [n for n, _ in BUILDERS]
PREVIEWS = [("all", _NAMES, False)] + [(n, [n], True) for n in _NAMES]
