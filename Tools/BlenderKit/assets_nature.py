# 자연 소품 묶음 (nature): 바위·판석·절벽·죽은 나무·거대 고목·그루터기·쓰러진 통나무·드러난 뿌리
#
# 만드는 방식
#   - 바위: 상자나 구를 여러 평면으로 깎아(slice_rock) 각진 덩어리를 만들고, 모서리를 쳐내고(chip),
#     얇게 떨어져 나간 자국(spall)을 판 뒤 겹겹이 떨어진 턱·금·구멍을 새긴다.
#   - 절벽(block_stack): 둘레를 부채꼴 바위 기둥으로 나누고(세로 절리) 층마다 끊어 쌓는다(가로 층리).
#     기둥마다 튀어나온 정도·꼭대기 높이가 달라 윗선이 들쭉날쭉하고, 블록 바깥면은 비스듬한 평면으로 쳐서
#     벽돌이 아니라 깨진 바위처럼 보이게 한다. 가운데 심 위에 흙을 얹고 풀·이끼·늘어진 이끼를 단다.
#   - 나무(Tree): 직접 짠 성장 알고리즘으로 뼈대(가지마다 점·반지름)를 만들고 관(tube)으로 감싼다.
#     굵은 부분(줄기·큰 가지·뿌리)은 리메시로 한 덩어리로 합친 뒤 bark 층(뼈대 방향을 따르는 껍질 균열)으로 조각하고,
#     가는 잔가지와 굵은 가지의 가는 끝은 관 그대로 쓴다 (저폴리도 같은 꺾은선 위의 관이라 끝이 바늘처럼 뾰족하다).
#   - 늘어진 이끼·풀·덩굴은 굽지 않는 Foliage 카드 (아틀라스 moss_hang, grass_card, kit.ivy 덩굴).
#
# 굽기 요령 (이 묶음에서 겪은 문제)
#   - 저폴리는 잔 조각을 새기기 전의 사본에서 줄인다 (sculpt2). 다 새긴 원본에서 줄이면 면이 구겨져 UV 가 잘게 쪼개진다.
#   - 저폴리의 직각 모서리는 soften 으로 살짝 굴린다 (모서리마다 검은 줄 방지). 굽기 거리(extr)는 좁은 틈 폭의 절반보다 작게.
#   - ColorRamp 의 위치는 0~1 로 잘리므로 미터 단위 높이·거리는 _unit 으로 맞춰 넣는다.
#   - kit.surface 의 bark 층은 뼈대 방향이 점마다 조금만 달라도 무늬가 가로 띠로 어긋난다 → 가지마다 한 방향, 작은 씨앗(BARK_SEEDS).
#
# 미리보기: NATURE_PV="rock_a,all" 처럼 환경 변수로 다시 찍을 것만 고른다 (없으면 전부).
import math, random, os
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
from mathutils import noise as mnoise
from mathutils.bvhtree import BVHTree
import kit
from kit import *

# kit.load_fbx 는 FBX 에서 함께 들어온 "Foliage"·"Glow_*" 재질을 진짜 재질로 착각해 미리보기에서 잎이 하얗게,
# 발광이 꺼져 보인다. 묶음을 읽을 때 진짜 재질을 먼저 만들어 두어 피한다 (내보내는 파일에는 영향 없음).
if kit.sc is not None:
    foliage_mat()
    for _g in GLOW:
        glow_mat(_g)

R = math.radians
SPIRIT = (0.45, 0.85, 1.0)
TOXIC = (0.45, 1.0, 0.35)


# ───────────────────────── 기본 도우미 ─────────────────────────
class Acc:
    """정점·면 모음 (여러 관을 한 메쉬로)"""
    def __init__(self):
        self.v, self.f = [], []

    def add(self, verts, faces):
        o = len(self.v)
        self.v += verts
        self.f += [tuple(i + o for i in f) for f in faces]

    def obj(self, name):
        return mesh_from(name, self.v, self.f) if self.f else None


def drop_below(o, z=-0.05):
    """땅속에 묻혀 보이지 않는 면을 지운다 (텍스처 공간·삼각형 낭비 방지)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    kill = [f for f in bm.faces if all(v.co.z < z for v in f.verts)]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o


def low_from(high, tris, z=-0.05):
    """저폴리: 땅속 면을 먼저 지우고 줄인다"""
    c = copy(high)
    c.modifiers.clear()
    drop_below(c, z)
    n = tri_count(c)
    if n > tris:
        m = c.modifiers.new('dec', 'DECIMATE')
        m.ratio = tris / n
        m.use_collapse_triangulate = True
        apply_all(c)
    for p in c.data.polygons:
        p.use_smooth = True
    return c


def soften(o, iters=6, factor=0.6):
    """저폴리의 직각 모서리를 살짝 굴린다. 모두 부드럽게 칠한(smooth) 저폴리에 90도 모서리가 남으면
    정점 법선이 크게 꺾여 노멀맵이 그 자리에서 급하게 휘고, UV 이음매가 그 모서리에 겹쳐 검은 줄이 생긴다."""
    m = o.modifiers.new('soft', 'LAPLACIANSMOOTH')
    m.iterations = iters
    m.lambda_factor = factor
    m.lambda_border = 0.0
    m.use_volume_preserve = True
    m.use_normalized = True
    apply_all(o)
    return o


def bvh_of(o):
    return BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get())


def surf_points(o, rng, n, zdir=(-0.25, 0.85), center=None, tries=6, cond=None):
    """바깥에서 중심을 향해 광선을 쏴 표면 점과 법선을 고른다. cond(p, nrm) 로 거른다"""
    bvh = bvh_of(o)
    if center is None:
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        center = sum(bb, Vector()) / 8
    center = Vector(center)
    out = []
    for _ in range(n * tries):
        if len(out) >= n:
            break
        a = rng.uniform(0, 6.283)
        z = rng.uniform(*zdir)
        d = Vector((math.cos(a), math.sin(a), z)).normalized()
        loc, nrm, idx, dist = bvh.ray_cast(center + d * 60, -d)
        if loc is None:
            continue
        if cond is not None and not cond(loc, nrm):
            continue
        out.append((loc, nrm))
    return out


def spall(p, n, size, depth, rng):
    """표면이 얇게 떨어져 나간 자국 커터: p 표면 점, n 바깥 방향, size (가로, 세로), depth 파낼 깊이"""
    s = sphere(1.0, (0, 0, 0), (size[0], size[1], depth * 2.0), 2)
    slice_rock(s, rng, 7, (0.1, 0.32))
    n = Vector(n).normalized()
    q = n.to_track_quat('Z', 'Y').to_matrix().to_4x4() @ Matrix.Rotation(rng.uniform(0, 6.28), 4, 'Z')
    s.data.transform(Matrix.Translation(Vector(p) + n * depth * 0.9) @ q)
    s.data.update()
    return s


def spalls_on(o, rng, n, size=(0.2, 0.4), depth=(0.03, 0.07), zdir=(-0.2, 0.7), center=None):
    pts = surf_points(o, rng, n, zdir, center)
    cs = []
    for p, nr in pts:
        s = rng.uniform(*size)
        cs.append(spall(p, nr, (s, s * rng.uniform(0.5, 0.9)), rng.uniform(*depth), rng))
    if cs:
        cut(o, cs)
    return o


def facet(o, rng, planes, depth=(0.04, 0.2), nz=(-0.25, 0.35), keep_bottom=True):
    """옆면 위주로 평면을 쳐서 각진 면을 만든다 (slice_rock 과 같지만 기울기 범위를 정한다)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    for _ in range(planes):
        a = rng.uniform(0, 6.283)
        z = rng.uniform(*nz)
        nrm = Vector((math.cos(a), math.sin(a), z)).normalized()
        if keep_bottom and nrm.z < -0.5:
            continue
        proj = [v.co.dot(nrm) for v in bm.verts]
        mx, mn = max(proj), min(proj)
        co = nrm * (mx - (mx - mn) * rng.uniform(*depth))
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        r = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=nrm, clear_outer=True)
        edges = [g for g in r['geom_cut'] if isinstance(g, bmesh.types.BMEdge)]
        if edges:
            bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o


def rock_mass(rng, dims, center=(0, 0, 0), planes=16, depth=(0.04, 0.22), rz=None, base='box'):
    """평면으로 깎은 각진 바위 덩어리 (변환 적용, 월드 좌표)"""
    rot = (rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12), rng.uniform(0, 6.28) if rz is None else rz)
    if base == 'box':
        o = box(dims[0], dims[1], dims[2], center, rot=rot)
    else:
        o = sphere(0.5, center, dims, 2, rot=rot)
    xf_all(o)
    slice_rock(o, rng, planes, depth)
    return o


def sculpt2(o, voxel, coarse, fine, seed=0):
    """리메시 → 큰 굴곡(coarse) → 사본(저폴리용 바탕) → 잔 조각(fine).
    저폴리를 잔 조각까지 들어간 원본에서 줄이면 면이 구겨져 UV 가 잘게 쪼개지고 굽기 이음매가 검게 남는다.
    큰 형태까지만 들어간 사본에서 줄이고, 잔 조각은 노멀맵으로만 옮긴다."""
    origin0(o)
    remesh(o, voxel)
    if coarse:
        surface(o, coarse, seed)
    base = copy(o)
    if fine:
        surface(o, fine, seed + 1)
    return base


def rock_split(k=1.0, cracks=0.6):
    L = ROCK_LAYERS(k, cracks)
    return L[:2], L[2:]


# ───────────────────────── 재질 덧칠 ─────────────────────────
def _final(mat):
    b = mat.node_tree.nodes["Principled BSDF"]
    return b, b.inputs['Base Color'].links[0].from_socket


def _P(mat, k=1.0):
    nt = mat.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    if k == 1.0:
        return tc.outputs['Object']
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1 / k, 1 / k, 1 / k)
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    return mp.outputs['Vector']


def paint_k(name, pal, k=1.0, **kw):
    """kit.paint 의 무늬 크기를 k 배로 키운다 (큰 바위·절벽: 얼룩·이끼 반점·빗물 자국이 물체 크기에 맞게).
    흙물(dirt) 높이도 k 배가 된다."""
    m = paint(name, pal, **kw)
    if k == 1.0:
        return m
    nt = m.node_tree
    for tc in [n for n in nt.nodes if n.bl_idname == 'ShaderNodeTexCoord']:
        links = [l for l in nt.links if l.from_socket == tc.outputs['Object']]
        if not links:
            continue
        mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1 / k, 1 / k, 1 / k)
        nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
        for l in links:
            dst = l.to_socket
            nt.links.remove(l)
            nt.links.new(mp.outputs['Vector'], dst)
    return m


def _unit(nt, v, a, b):
    """a~b 를 0~1 로 (ColorRamp 의 위치는 0~1 로 잘리므로 미터 단위 높이는 먼저 맞춰 넣는다)"""
    m = nt.nodes.new('ShaderNodeMapRange'); m.clamp = True
    nt.links.new(v, m.inputs['Value'])
    m.inputs['From Min'].default_value = a; m.inputs['From Max'].default_value = b
    m.inputs['To Min'].default_value = 0.0; m.inputs['To Max'].default_value = 1.0
    return m.outputs['Result']


def grad_dark(mat, z0, z1, amount=0.6, color=(0.18, 0.13, 0.24), wob=1.0):
    """아래로 갈수록 어둡고 보랏빛 (z0 에서 가장 어둡고 z1 위로는 그대로)"""
    nt = mat.node_tree
    b, col = _final(mat)
    P = _P(mat)
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(P, sep.inputs[0])
    w = kit._mul(nt, kit._mul(nt, kit._noise(nt, P, 0.5 / max(wob, 0.01), 3), 0.5, 'SUBTRACT'), (z1 - z0) * 0.5 * wob)
    zz = kit._mul(nt, sep.outputs['Z'], w, 'ADD')
    g = kit._ramp(nt, _unit(nt, zz, z0, z1), 0.0, W(color), 1.0, W((1, 1, 1)))
    mixed = kit._mix(nt, 'MULTIPLY', amount, col, g)
    nt.links.new(mixed, b.inputs['Base Color'])
    return mat


def blotch(mat, color, scale=1.0, amount=0.5, lo=0.48, hi=0.62, mode='MIX', k=1.0, up_only=False):
    """잡음 얼룩 (벗겨져 하얗게 바랜 나무, 물때 등)"""
    nt = mat.node_tree
    b, col = _final(mat)
    P = _P(mat, k)
    m = kit._ramp(nt, kit._noise(nt, P, scale, 6, 0.6), lo, W((0, 0, 0)), hi, W((1, 1, 1)))
    if up_only:
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(geo.outputs['Normal'], sep.inputs[0])
        m = kit._mul(nt, m, kit._ramp(nt, sep.outputs['Z'], 0.45, W((0, 0, 0)), 0.8, W((1, 1, 1))))
    out = kit._mix(nt, mode, kit._mul(nt, m, amount), col, W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat


def top_cover(mat, color=MOSS, z0=-1e3, amount=0.9, scale=0.8, k=1.0, nz=(0.55, 0.85), lo=0.4, hi=0.55):
    """윗면(법선이 위)을 덮는 이끼·흙. z0 보다 높은 곳만"""
    nt = mat.node_tree
    b, col = _final(mat)
    P = _P(mat, k)
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(geo.outputs['Normal'], sep.inputs[0])
    up = kit._ramp(nt, sep.outputs['Z'], nz[0], W((0, 0, 0)), nz[1], W((1, 1, 1)))
    patch = kit._ramp(nt, kit._noise(nt, P, scale, 6, 0.6), lo, W((0, 0, 0)), hi, W((1, 1, 1)))
    m = kit._mul(nt, up, patch)
    if z0 > -1e2:
        sp = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(_P(mat), sp.inputs[0])
        m = kit._mul(nt, m, _unit(nt, sp.outputs['Z'], z0, z0 + 0.4))
    mc = kit._ramp(nt, kit._noise(nt, P, 14, 5), 0.3, W(tuple(c * 0.55 for c in color)), 0.72, W(tuple(c * 1.5 for c in color)))
    out = kit._mix(nt, 'MIX', kit._mul(nt, m, amount), col, mc)
    nt.links.new(out, b.inputs['Base Color'])
    return mat


def tint_near(mat, center, radius, color, amount=0.5, mode='MIX'):
    """한 점 근처를 물들인다 (영혼 빛이 스민 나무 속 등)"""
    nt = mat.node_tree
    b, col = _final(mat)
    P = _P(mat)
    vm = nt.nodes.new('ShaderNodeVectorMath'); vm.operation = 'DISTANCE'
    nt.links.new(P, vm.inputs[0]); vm.inputs[1].default_value = center
    d = kit._ramp(nt, _unit(nt, vm.outputs['Value'], 0.0, radius), 0.0, W((1, 1, 1)), 1.0, W((0, 0, 0)))
    m = kit._mul(nt, kit._mul(nt, d, kit._ramp(nt, kit._noise(nt, P, 6, 3), 0.35, W((0.5, 0.5, 0.5)), 0.65, W((1, 1, 1)))), amount)
    out = kit._mix(nt, mode, m, col, W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat


ROCK_PAL = ((0.04, 0.043, 0.066), (0.2, 0.2, 0.28), (0.6, 0.62, 0.8))


def rock_paint(name, k=1.0, pal=ROCK_PAL, moss=0.85, **kw):
    args = dict(moss=moss, ao=0.5 * k, streaks=0.35, dirt=0.6, edge=0.9)
    args.update(kw)
    return paint_k(name, pal, k, **args)


# 나무 색: 어둡고 보랏빛 도는 껍질, 벗겨져 하얗게 바랜 나무
BARK_DEAD = ((0.026, 0.021, 0.03), (0.12, 0.1, 0.115), (0.36, 0.34, 0.4))
BARK_OLD = ((0.024, 0.02, 0.026), (0.11, 0.085, 0.085), (0.3, 0.26, 0.28))
WOOD_PALE = (0.3, 0.29, 0.33)
BARK_GREY = ((0.06, 0.052, 0.066), (0.27, 0.24, 0.27), (0.5, 0.47, 0.53))   # (v3b) 판 위가 밝은 회갈색, 골은 어둡게 (BARK_DEAD 보다 밝고 덜 파랗다)


def bark_paint(name, pal=BARK_DEAD, moss=0.4, moss_color=MOSS_DEAD, pale=0.45, pale_scale=0.9, **kw):
    args = dict(moss=moss, moss_color=moss_color, dirt=0.5, streaks=0.0, streak_dir='grain', cracks=0.0, edge=0.75, ao=0.3,
                hue_var=0.35)
    args.update(kw)
    m = paint(name, pal, **args)
    if pale > 0:
        blotch(m, WOOD_PALE, pale_scale, pale, 0.5, 0.6)
    return m


# ───────────────────────── 관 (가지·뿌리) ─────────────────────────
def frames(path):
    """평행 이동 틀: 각 점의 접선 T, 법선 N, 종법선 B"""
    n = len(path)
    T = []
    for i in range(n):
        d = path[min(i + 1, n - 1)] - path[max(i - 1, 0)]
        T.append(d.normalized() if d.length > 1e-9 else Vector((0, 0, 1)))
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = [(ref - T[0] * ref.dot(T[0])).normalized()]
    for i in range(1, n):
        q = T[i - 1].rotation_difference(T[i])
        v = q @ N[i - 1]
        v = v - T[i] * v.dot(T[i])
        N.append(v.normalized() if v.length > 1e-9 else N[i - 1])
    B = [T[i].cross(N[i]) for i in range(n)]
    return T, N, B


def _catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)


def resample(pts, rads, step):
    """제어점을 부드러운 곡선(Catmull-Rom)으로 이어 step 간격으로 다시 찍는다"""
    n = len(pts)
    op, orr = [], []
    for i in range(n - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n - 1)]
        k = max(1, int(math.ceil((p2 - p1).length / step)))
        for j in range(k):
            t = j / k
            op.append(_catmull(p0, p1, p2, p3, t))
            orr.append(rads[i] + (rads[i + 1] - rads[i]) * t)
    op.append(pts[-1].copy()); orr.append(rads[-1])
    return op, orr


def tube(path, rads, sides, lobes=0, lobe_amp=0.0, twist=0.0, bumps=0.0, seed=0, ell=1.0, cap=True, tip=True, phase=0.0, s0=0.0):
    """path 를 따라 고리를 이어 관을 만든다. 끝 반지름이 작으면 한 점으로 모아 바늘처럼 뾰족하게.
    lobes: 단면의 골 개수 (비틀린 줄기), twist: 길이 1m 당 골이 도는 각도(라디안), bumps: 혹 크기 비율"""
    T, N, B = frames(path)
    verts, faces, rings = [], [], []
    s = s0
    off = Vector((seed * 7.13 + 3.1, seed * 3.71 - 1.7, seed * 1.37 + 0.4))
    n = len(path)
    for i, p in enumerate(path):
        if i:
            s += (path[i] - path[i - 1]).length
        r = rads[i]
        if tip and i == n - 1:
            verts.append(p.copy()); rings.append([len(verts) - 1])
            continue
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides
            f = 1.0
            if lobes:
                f += lobe_amp * math.sin(lobes * a + twist * s + phase)
            if bumps:
                q = Vector((math.cos(a) * 0.9, math.sin(a) * 0.9, s / max(r * 3.0, 0.03))) + off
                f += bumps * mnoise.noise(q)
            d = N[i] * (math.cos(a) * ell) + B[i] * math.sin(a)
            verts.append(p + d * (r * f))
            ring.append(len(verts) - 1)
        rings.append(ring)
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        if len(r1) == 1:
            for k in range(sides):
                faces.append((r0[k], r0[(k + 1) % sides], r1[0]))
        else:
            for k in range(sides):
                faces.append((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k]))
    if cap:
        c = len(verts); verts.append(path[0].copy())
        for k in range(sides):
            faces.append((rings[0][(k + 1) % sides], rings[0][k], c))
    if not tip:                       # 끝을 평평하게 막는다
        c = len(verts); verts.append(path[-1].copy())
        for k in range(sides):
            faces.append((rings[-1][k], rings[-1][(k + 1) % sides], c))
    return verts, faces


def respace(pts, rads, step):
    """촘촘한 선을 길이 기준 step 간격으로 다시 찍는다 (점을 줄일 때)"""
    L = [0.0]
    for i in range(1, len(pts)):
        L.append(L[-1] + (pts[i] - pts[i - 1]).length)
    tot = L[-1]
    n = max(2, int(math.ceil(tot / step)))
    op, orr = [], []
    j = 0
    for k in range(n + 1):
        s = tot * k / n
        while j < len(L) - 2 and L[j + 1] < s:
            j += 1
        f = min(max((s - L[j]) / max(L[j + 1] - L[j], 1e-9), 0.0), 1.0)
        op.append(pts[j].lerp(pts[j + 1], f))
        orr.append(rads[j] + (rads[j + 1] - rads[j]) * f)
    return op, orr


# ───────────────────────── 나무 뼈대 ─────────────────────────
def path_grow(rng, start, d, length, seg, gnarl, up=0.0, droop=0.0, kink=0.0):
    """방향을 조금씩 틀며 자라는 가지 경로 (kink: 갑자기 꺾일 확률)"""
    n = max(2, int(round(length / seg)))
    pts = [Vector(start)]
    d = Vector(d).normalized()
    step = length / n
    for i in range(n):
        t = (i + 1) / n
        j = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
        j -= d * j.dot(d)
        g = gnarl * (2.4 if rng.random() < kink else 1.0)
        d = (d + j * g + Vector((0, 0, up)) - Vector((0, 0, droop * t))).normalized()
        pts.append(pts[-1] + d * step)
    return pts


class Tree:
    """가지 목록: 각 가지 = 제어점·반지름·깊이. 굵기로 리메시할 부분(A)과 관 그대로 쓸 잔가지(B)를 나눈다"""
    def __init__(self, rng):
        self.rng = rng
        self.br = []

    def branch(self, pts, r0, r1=0.003, taper=1.0, depth=0, collar=1.0, lobes=0, lobe_amp=0.0, twist=0.0, bumps=0.05,
               ell=1.0, flare=None, tip=True, cap=True, parent=None):
        n = len(pts)
        L = [0.0]
        for i in range(1, n):
            L.append(L[-1] + (pts[i] - pts[i - 1]).length)
        tot = max(L[-1], 1e-6)
        rads = [r1 + (r0 - r1) * (1 - L[i] / tot) ** taper for i in range(n)]
        if flare:
            # 밑동이 넓게 퍼지게: flare = (높이, 배율) — 시작점에서 멀어질수록 줄어든다
            h, k = flare
            rads = [r * (1 + (k - 1) * math.exp(-L[i] / h)) for i, r in enumerate(rads)]
        if collar > 1:
            rads[0] *= collar
            if n > 2:
                rads[1] *= 1 + (collar - 1) * 0.35
        b = dict(pts=pts, rads=rads, r0=r0, depth=depth, len=tot, L=L, lobes=lobes, lobe_amp=lobe_amp, twist=twist,
                 bumps=bumps, ell=ell, seed=len(self.br), tip=tip, cap=cap, fr=frames(pts), parent=parent)
        self.br.append(b)
        return b

    def at(self, b, t):
        """가지 위 길이 비율 t 지점: (점, 반지름, T, N, B)"""
        L, tot = b['L'], b['len']
        s = t * tot
        i = 0
        while i < len(L) - 2 and L[i + 1] < s:
            i += 1
        f = (s - L[i]) / max(L[i + 1] - L[i], 1e-6)
        f = min(max(f, 0.0), 1.0)
        p = b['pts'][i].lerp(b['pts'][i + 1], f)
        r = b['rads'][i] + (b['rads'][i + 1] - b['rads'][i]) * f
        T, N, B = b['fr']
        return p, r, T[i], N[i], B[i]

    def grow(self, parent, levels, lvl=0):
        """levels[lvl] 규칙으로 parent 에서 곁가지를 낸다 (재귀)"""
        if lvl >= len(levels):
            return
        P = levels[lvl]
        rng = self.rng
        k = rng.randint(*P['kids'])
        phi = rng.uniform(0, 6.283)
        ts = sorted(rng.uniform(*P['t']) for _ in range(k))
        for t in ts:
            p, r, T, N, B = self.at(parent, t)
            phi += 2.39996 + rng.uniform(-0.6, 0.6)
            u = N * math.cos(phi) + B * math.sin(phi)
            th = R(rng.uniform(*P['angle']))
            d = T * math.cos(th) + u * math.sin(th)
            d = (d + Vector((0, 0, P.get('kid_up', 0.0)))).normalized()
            length = parent['len'] * rng.uniform(*P['len']) * (1 - P.get('len_t', 0.4) * t)
            r0 = r * rng.uniform(*P['r'])
            if r0 < P.get('rmin', 0.004) or length < P.get('lmin', 0.08):
                continue
            start = p - u * (r * 0.35)
            pts = path_grow(rng, start, d, length, P['seg'], P['gnarl'], P.get('up', 0.0), P.get('droop', 0.0), P.get('kink', 0.0))
            b = self.branch(pts, r0, P.get('tip', 0.003), P.get('taper', 1.0), parent['depth'] + 1, collar=P.get('collar', 1.3),
                            lobes=P.get('lobes', 0), lobe_amp=P.get('lobe_amp', 0.0), twist=P.get('twist', 0.0),
                            bumps=P.get('bumps', 0.06), parent=parent)
            self.grow(b, levels, lvl + 1)

    def pieces(self, split_r, r_cut):
        """(촘촘한 점, 반지름, 'A'|'B', 가지, 시작 거리, 끝 뾰족) 조각. 굵은 가지의 가는 끝(r < r_cut)은
        잔가지(B)로 떼어 내 관 그대로 쓴다 → 리메시가 가는 끝을 뭉개 숟가락처럼 만들지 않는다"""
        out = []
        for b in self.br:
            pts, rads = resample(b['pts'], b['rads'], 0.02)
            if b['r0'] < split_r:
                out.append((pts, rads, 'B', b, 0.0, b['tip']))
                continue
            j = next((i for i, r in enumerate(rads) if i > 0 and r < r_cut), None)
            if j is None or not b['tip'] or j >= len(pts) - 4:
                out.append((pts, rads, 'A', b, 0.0, b['tip']))
                continue
            out.append((pts[:j + 1], rads[:j + 1], 'A', b, 0.0, False))
            s0 = sum((pts[i] - pts[i - 1]).length for i in range(1, j))
            out.append((pts[j - 1:], rads[j - 1:], 'B', b, s0, True))
        return out

    def meshes(self, split_r, hi=True, low_sides=5, low_step=(0.08, 0.3), r_cut=0.03):
        """A: 굵은 부분, B: 잔가지·가는 끝. hi=True 면 촘촘한 관(굽기 원본), False 면 B 의 저폴리 관.
        B 는 원본과 저폴리가 같은 꺾은선 위에 있어야 굽기 광선이 빗나가지 않는다 (원본은 면만 더 촘촘하게)."""
        A, Bc = Acc(), Acc()
        for pts, rads, kind, b, s0, tip in self.pieces(split_r, r_cut):
            r0 = max(rads)
            ln = sum((pts[i] - pts[i - 1]).length for i in range(1, len(pts)))
            if kind == 'A':
                if not hi:
                    continue
                step = min(max(r0 * 0.25, 0.012), 0.06)
                sides = int(min(max(2 * math.pi * r0 / 0.025, 10), 40))
                pp, rr = respace(pts, rads, step)
            else:
                step = min(max(ln / 4, low_step[0]), low_step[1])
                pp, rr = respace(pts, rads, step)
                if hi:
                    sides = 8
                    fp, fr = [], []
                    for i in range(len(pp) - 1):
                        k = max(1, int(math.ceil((pp[i + 1] - pp[i]).length / 0.02)))
                        for j in range(k):
                            fp.append(pp[i].lerp(pp[i + 1], j / k)); fr.append(rr[i] + (rr[i + 1] - rr[i]) * j / k)
                    fp.append(pp[-1]); fr.append(rr[-1])
                    pp, rr = fp, fr
                else:
                    sides = low_sides if r0 > 0.02 else (4 if r0 > 0.009 else 3)
            v, f = tube(pp, rr, sides, b['lobes'], b['lobe_amp'], b['twist'], b['bumps'] if kind == 'A' else 0.0,
                        b['seed'], b['ell'], cap=b['cap'] or kind == 'B', tip=tip, s0=s0)
            (A if kind == 'A' else Bc).add(v, f)
        return A, Bc

    def piece_meshes(self, split_r, r_cut=0.03, low_step=(0.08, 0.3)):
        """(v3b) 원본 관을 조각마다 따로: [(조각 번호, 'A', 가지, Acc), ...] + 잔가지 전부 Acc 하나 (meshes(hi=True) 와 같은 관)"""
        outA, Bc = [], Acc()
        for pi, (pts, rads, kind, b, s0, tip) in enumerate(self.pieces(split_r, r_cut)):
            r0 = max(rads)
            ln = sum((pts[i] - pts[i - 1]).length for i in range(1, len(pts)))
            if kind == 'A':
                step = min(max(r0 * 0.25, 0.012), 0.06)
                sides = int(min(max(2 * math.pi * r0 / 0.025, 10), 40))
                pp, rr = respace(pts, rads, step)
            else:
                step = min(max(ln / 4, low_step[0]), low_step[1])
                pp, rr = respace(pts, rads, step)
                sides = 8
                fp, fr = [], []
                for i in range(len(pp) - 1):
                    k = max(1, int(math.ceil((pp[i + 1] - pp[i]).length / 0.02)))
                    for j in range(k):
                        fp.append(pp[i].lerp(pp[i + 1], j / k)); fr.append(rr[i] + (rr[i + 1] - rr[i]) * j / k)
                fp.append(pp[-1]); fr.append(rr[-1])
                pp, rr = fp, fr
            v, f = tube(pp, rr, sides, b['lobes'], b['lobe_amp'], b['twist'], b['bumps'] if kind == 'A' else 0.0,
                        b['seed'], b['ell'], cap=b['cap'] or kind == 'B', tip=tip, s0=s0)
            if kind == 'A':
                a = Acc(); a.add(v, f)
                outA.append((pi, b, a))
            else:
                Bc.add(v, f)
        return outA, Bc

    def guide_for(self, b, step=0.05):
        """(v3b) 가지 하나만의 껍질 결 뼈대 (조각마다 따로 깎을 때: 이웃 가지 점을 집어 결이 옆으로 눕지 않게)"""
        pts, rads = resample(b['pts'], b['rads'], step)
        chord = pts[-1] - pts[0]
        chord = chord.normalized() if chord.length > 1e-6 else Vector((0, 0, 1))
        me = bpy.data.meshes.new("skel")
        me.from_pydata([tuple(p) for p in pts], [], [])
        a = me.attributes.new("dir", 'FLOAT_VECTOR', 'POINT')
        for i in range(len(pts)):
            a.data[i].vector = chord
        return link(bpy.data.objects.new("skel", me))

    def guide(self, step=0.05, only=None):
        """bark 층용 뼈대 점 (각 점에 'dir' = 가지 방향).
        곁가지·뿌리가 부모 줄기 속을 지나는 부분은 뺀다 (안 그러면 줄기 겉면이 그 가로 방향을 집어 껍질 결이 옆으로 눕는다)
        only: 이 가지들만 (v3b, 줄기+뿌리 한 덩어리 원본용)"""
        verts, dirs = [], []
        dense = {}
        for b in self.br:
            dense[id(b)] = resample(b['pts'], b['rads'], step)
        for b in self.br:
            if only is not None and id(b) not in only:
                continue
            pts, rads = dense[id(b)]
            # 가지마다 한 방향(시작→끝)만 쓴다. kit.surface 의 bark 층은 절대 위치를 방향에 투영하므로
            # 이웃한 뼈대 점의 방향이 조금만 달라도 무늬가 점 경계(5cm 간격)마다 어긋나 가로 띠가 생긴다.
            chord = pts[-1] - pts[0]
            chord = chord.normalized() if chord.length > 1e-6 else Vector((0, 0, 1))
            T = [chord] * len(pts)
            par = b.get('parent')
            for p, t in zip(pts, T):
                if par is not None:
                    pp, pr = dense[id(par)]
                    inside = False
                    for q, r in zip(pp, pr):
                        if (p - q).length < r * 1.05:
                            inside = True
                            break
                    if inside:
                        continue
                verts.append(tuple(p)); dirs.append(tuple(t))
        me = bpy.data.meshes.new("skel")
        me.from_pydata(verts, [], [])
        a = me.attributes.new("dir", 'FLOAT_VECTOR', 'POINT')
        for i, d in enumerate(dirs):
            a.data[i].vector = d
        return link(bpy.data.objects.new("skel", me))

    def tris_low(self, split_r, **kw):
        _, Bc = self.meshes(split_r, hi=False, **kw)
        return sum(len(f) - 2 for f in Bc.f)


def root_path(rng, ang, r_trunk, z_start, reach, dip=0.3, wander=0.18):
    """줄기 속에서 시작해 바깥·아래로 뻗어 땅속으로 들어가는 뿌리 경로 (밑동에서 솟았다가 땅을 움켜쥐며 파고든다)"""
    c, s = math.cos(ang), math.sin(ang)
    side = Vector((-s, c, 0))
    pts = []
    keys = [(0.15, z_start), (0.75, z_start * 0.55), (1.25, z_start * 0.22), (1.9, 0.04), (2.6, -dip * 0.6), (3.3, -dip * 1.4)]
    for i, (rk, z) in enumerate(keys):
        rr = r_trunk * rk if i < 2 else r_trunk * 1.25 + (reach - r_trunk * 1.25) * (rk - 1.25) / 2.05
        w = side * (rng.uniform(-wander, wander) * rr if i > 1 else 0.0)
        pts.append(Vector((c * rr, s * rr, z)) + w + Vector((0, 0, rng.uniform(-0.04, 0.04) * reach if i > 2 else 0)))
    return pts


def axis_at(b, z):
    """가지(줄기) 축이 높이 z 를 지나는 점 (기운 줄기에서 뿌리를 줄기 속에서 시작하게)"""
    pts = b['pts']
    for p, q in zip(pts, pts[1:]):
        if p.z <= z <= q.z and q.z > p.z:
            return p.lerp(q, (z - p.z) / (q.z - p.z))
    return pts[0] if z < pts[0].z else pts[-1]


def trunk_roots(tree, rng, n, r_trunk, z_start=(0.5, 0.9), reach=(1.0, 1.6), r_k=(0.45, 0.6), dip=0.3, lobes=2, ang0=None):
    a0 = rng.uniform(0, 6.283) if ang0 is None else ang0
    trunk = tree.br[0] if tree.br else None
    for i in range(n):
        ang = a0 + i * 2 * math.pi / n + rng.uniform(-0.35, 0.35)
        rch = rng.uniform(*reach)
        zs = rng.uniform(*z_start)
        pts = root_path(rng, ang, r_trunk, zs, rch, dip)
        if trunk is not None:
            ax = axis_at(trunk, zs); ax.z = 0
            ax0 = axis_at(trunk, 0.0); ax0.z = 0
            for i in range(len(pts)):
                w = 1.0 if i < 2 else (0.5 if i == 2 else 0.0)
                pts[i] = pts[i] + ax * w + ax0 * (1 - w)
        tree.branch(pts, r_trunk * rng.uniform(*r_k), 0.015, 0.7, depth=9, lobes=lobes, lobe_amp=0.1, bumps=0.1, ell=0.85,
                    parent=trunk)


# ───────────────────────── Foliage 카드 (늘어진 이끼·풀) ─────────────────────────
class Cards:
    def __init__(self):
        self.v, self.f, self.uv, self.col = [], [], [], []

    def quad_strip(self, rows, cell, cols):
        """rows: [(왼쪽 점, 오른쪽 점, v), ...] 아래→위 또는 위→아래 순서. cols: 줄마다 (r,g,b,a)"""
        base = len(self.v)
        for (pl, pr, v), c in zip(rows, cols):
            self.v += [pl, pr]
            self.uv += [atlas_uv(cell, 0.0, v), atlas_uv(cell, 1.0, v)]
            self.col += [c, c]
        for i in range(len(rows) - 1):
            k = base + i * 2
            self.f.append((k, k + 1, k + 3, k + 2))

    def obj(self, name="cards"):
        if not self.f:
            return None
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in self.v], [], self.f)
        me.update(calc_edges=True)
        o = bpy.data.objects.new(name, me)
        link(o)
        uvl = me.uv_layers.new(name="UVMap")
        for lp in me.loops:
            uvl.data[lp.index].uv = self.uv[lp.vertex_index]
        vcolor(o, lambda p, n, i: self.col[i])
        set_mat(o, foliage_mat())
        return o

    def tris(self):
        return 2 * len(self.f)


MOSS_HANG_COL = (0.5, 0.58, 0.47)


def moss_hang(cards, rng, top, length, width, n=3, color=MOSS_HANG_COL, segs=3, face=None, along=None):
    """가지에서 늘어진 이끼 한 뭉치: 세로 카드 n 장.
    along(가지 방향)을 주면 카드 폭을 가지를 따라 눕혀 윗변이 가지 밑에 숨는다 (허공에 막대처럼 뜬 윗변 방지)"""
    a0 = rng.uniform(0, 3.14) if face is None else face
    j = rng.uniform(0.75, 1.2)
    base_c = (min(1, color[0] * j), min(1, color[1] * j), min(1, color[2] * j * rng.uniform(0.95, 1.1)))
    for k in range(n):
        if along is not None:
            T = Vector(along).normalized()
            side = (Matrix.Rotation(rng.uniform(-0.3, 0.3), 3, 'Z') @ T).normalized()
            out = Vector((-side.y, side.x, 0)).normalized() * rng.choice((-1, 1))
        else:
            a = a0 + k * math.pi / n + rng.uniform(-0.25, 0.25)
            side = Vector((math.cos(a), math.sin(a), 0))
            out = Vector((-side.y, side.x, 0)) * rng.choice((-1, 1))
        L = length * rng.uniform(0.6, 1.0)
        w = width * rng.uniform(0.7, 1.1)
        sway = rng.uniform(0.02, 0.08) * L
        p0 = Vector(top) + side * rng.uniform(-0.3, 0.3) * width + Vector((0, 0, 0.02))
        rows, cols = [], []
        for i in range(segs + 1):
            t = i / segs
            c = p0 + Vector((0, 0, -L * t)) + out * (sway * t * t)
            ww = w * (1 - 0.35 * t)
            # 아래로 갈수록 가지 기울기를 덜 따른다 (늘어진 이끼는 수직으로 처진다)
            sd = side.lerp(Vector((side.x, side.y, 0)), t).normalized()
            rows.append((c - sd * ww / 2, c + sd * ww / 2, 0.84 - 0.82 * t))
            sh = 0.6 + 0.4 * t
            cols.append((base_c[0] * sh, base_c[1] * sh, base_c[2] * sh, t))
        cards.quad_strip(rows, 'moss_hang', cols)


GRASS_COL = (0.2, 0.3, 0.24)
GRASS_DEAD = (0.4, 0.37, 0.24)


def grass_tuft(cards, rng, p, h, w, n=3, dead=0.3, color=GRASS_COL, nrm=(0, 0, 1)):
    """풀 한 포기: 엇갈린 카드 n 장"""
    up = Vector(nrm).normalized().lerp(Vector((0, 0, 1)), 0.6).normalized()
    a0 = rng.uniform(0, 3.14)
    for k in range(n):
        a = a0 + k * math.pi / n + rng.uniform(-0.3, 0.3)
        side = Vector((math.cos(a), math.sin(a), 0))
        side = (side - up * side.dot(up)).normalized()
        lean = up.cross(side) * rng.uniform(-0.25, 0.25)
        hh = h * rng.uniform(0.7, 1.1)
        isdead = rng.random() < dead
        c = GRASS_DEAD if isdead else color
        j = rng.uniform(0.8, 1.2)
        base = Vector(p) - up * 0.03
        rows, cols = [], []
        for i, t in enumerate((0.0, 0.5, 1.0)):
            q = base + up * (hh * t) + lean * (hh * t * t)
            ww = w * (1 + 0.25 * t)
            rows.append((q - side * ww / 2, q + side * ww / 2, 0.02 + 0.96 * t))
            sh = 0.45 + 0.55 * t
            cols.append((c[0] * j * sh, c[1] * j * sh, c[2] * j * sh, t))
        cards.quad_strip(rows, 'grass_card', cols)


def grass_on_top(cards, target, rng, n, area, zmin=-1e9, h=(0.25, 0.5), w=(0.25, 0.45), dead=0.35, nz=0.65, center=(0, 0)):
    """target 위에서 아래로 광선을 쏴 윗면(법선이 위)에 풀을 심는다. area = (x반폭, y반폭)"""
    bvh = bvh_of(target)
    placed = 0
    for _ in range(n * 8):
        if placed >= n:
            break
        x = center[0] + rng.uniform(-area[0], area[0])
        y = center[1] + rng.uniform(-area[1], area[1])
        loc, nr, idx, dist = bvh.ray_cast(Vector((x, y, 200)), Vector((0, 0, -1)))
        if loc is None or nr.z < nz or loc.z < zmin:
            continue
        grass_tuft(cards, rng, loc, rng.uniform(*h), rng.uniform(*w), 3, dead, nrm=nr)
        placed += 1
    return placed


# ───────────────────────── 덩굴 (kit.ivy 결과를 가볍게) ─────────────────────────
IVY_COL = (0.1, 0.21, 0.16)


def ivy_light(target, start, seed, length, max_leaves=220, max_stem=500, **kw):
    """kit.ivy 로 자라게 한 뒤 가볍게 줄인다. IvyGen 은 자랄 때마다 뿌리가 하나씩 늘고 마디마다 잎을 열 번 시도해
    그대로 두면 덩굴 하나가 수만 삼각형이 된다 → 갈래·잎 확률을 낮추고, 잎 수와 줄기 삼각형에 상한을 둔다."""
    args = dict(length=length, leaf=0.075, leaf_prob=0.3, branch=0.006, gravity=0.6, adhesion=0.8, color=IVY_COL, dead=0.3,
                stem_radius=0.007, size=0.04)
    args.update(kw)
    parts = ivy(target, start, seed=seed, **args)
    rng = random.Random(seed)
    out = []
    for o in parts:
        if o.name.startswith("IvyLeaf") or "Leaf" in o.name:
            bm = bmesh.new(); bm.from_mesh(o.data)
            faces = list(bm.faces)
            if len(faces) > max_leaves:
                rng.shuffle(faces)
                bmesh.ops.delete(bm, geom=faces[max_leaves:], context='FACES')
            bm.to_mesh(o.data); bm.free(); o.data.update()
        else:
            n = tri_count(o)
            if n > max_stem:
                m = o.modifiers.new('dec', 'DECIMATE'); m.ratio = max_stem / n
                apply_all(o)
        out.append(o)
    return out


# ───────────────────────── 바위 ─────────────────────────
def rock_a():
    """바위 ~1.5m: 각진 덩어리, 윗면 이끼 (지형 나무 인스턴스로 대량 배치)"""
    rng = random.Random(21)
    o = rock_mass(rng, (1.75, 1.3, 1.15), (0, 0, 0.36), planes=15, depth=(0.05, 0.24))
    # 옆에 붙은 작은 덩어리 → 한 덩어리가 아니라 금 간 바위처럼
    o2 = rock_mass(rng, (0.8, 0.7, 0.6), (0.62, -0.28, 0.12), planes=10, depth=(0.05, 0.25))
    o = join([o, o2])
    remesh(o, 0.012)
    chip(o, rng, 10, (0.14, 0.3), sharp_deg=25, bite=0.32)
    spalls_on(o, rng, 5, (0.25, 0.42), (0.035, 0.07), center=(0, 0, 0.4))
    base = sculpt2(o, 0.0095, *rock_split(1.1, 0.65), seed=3)
    m = rock_paint("rock_a", 1.0, moss=0.9)
    top_cover(m, MOSS, amount=0.7, scale=1.3, nz=(0.6, 0.9))
    set_mat(o, m)
    low = low_from(base, 3600); delete(base)
    return finish("rock_a", [o], [low], size=1024, extr=0.1, uv_angle=75)


def facet_mass(rng, dims, center=(0, 0, 0), planes=16, depth=(0.1, 0.26), rz=None, chamfer=0, chamfer_depth=(0.015, 0.05)):
    """(v3b) 각진 바위 덩어리: 20면체(구 1단계)를 늘여 깊은 평면으로 깎는다. 상자는 깎아도 상자처럼, 잘게 나눈 구는
    둥근 덩어리로 읽힌다 — 면이 적은 20면체에서 출발하면 큰 평면이 비스듬히 만나는 깨진 돌이 된다.
    chamfer: 얕은 평면을 더 쳐서 모서리·꼭짓점을 작은 면으로 깨뜨린다 (큰 면 하나가 통째로 남으면 보석·장난감처럼 보인다)"""
    rot = (rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), rng.uniform(0, 6.28) if rz is None else rz)
    o = sphere(0.5, center, dims, 1, rot=rot)
    xf_all(o)
    slice_rock(o, rng, planes, depth)
    if chamfer:
        slice_rock(o, rng, chamfer, chamfer_depth)
    return o


def step_spalls(o, rng, n, size=(0.45, 0.8), depth=(0.05, 0.09), wall=40.0, zmin=0.3):
    """(v3b) 모서리에서 떨어져 나간 계단 자국: 평면 spall 을 날카로운 모서리 위에 걸쳐 놓아 한쪽이 모서리로 열린 턱이 된다
    (면 한가운데 닫힌 구덩이는 창문처럼 보인다)"""
    cs = []
    for p, out in edge_points(o, n, rng, 30.0, zmin):
        sz = rng.uniform(*size)
        # 모서리 바깥 방향(out)과 가까운 면 법선 사이: 모서리를 비스듬히 깎는다
        cs.append(spall_flat(p - out * sz * 0.15, out, (sz, sz * rng.uniform(0.5, 0.8)), rng.uniform(*depth), rng, wall=wall, tilt=12.0))
    if cs:
        cut(o, cs)
    return o


def chip_convex(o, rng, n, size=(0.2, 0.4), zmin=-1e9, sharp_deg=25):
    """(v3b) 모서리 깨짐: 볼록한 다면체 커터 (상자 커터는 직각으로 파인 계단 이가 생겨 성벽 톱니처럼 보였다)"""
    cs = []
    for p, out in edge_points(o, n, rng, sharp_deg, zmin):
        s_ = rng.uniform(*size)
        c = sphere(1.0, (0, 0, 0), (s_, s_ * rng.uniform(0.6, 0.9), s_ * rng.uniform(0.5, 0.8)), 1,
                   rot=(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)))
        slice_rock(c, rng, 5, (0.1, 0.3))
        c.data.transform(Matrix.Translation(p + out * s_ * 0.35))
        c.data.update()
        cs.append(c)
    if cs:
        cut(o, cs)
    return o


def spall_flat(p, n, size, depth, rng, wall=45.0, sides=7, tilt=8.0, margin=0.06):
    """(v3b) 평면으로 떨어져 나간 자국 커터: 바닥은 평평하고(조금 기운 평면), 벽은 wall 도 경사의 각뿔대.
    구(타원체) 커터는 테두리에서 벽이 수직이라 굽기 광선이 비스듬히 스쳐 흰 보풀·검은 톱니 테두리가 생겼다.
    p 표면 점, n 바깥 방향, size (가로, 세로 반지름), depth 깊이"""
    n = Vector(n).normalized()
    q = n.to_track_quat('Z', 'Y').to_matrix().to_4x4() @ Matrix.Rotation(rng.uniform(0, 6.28), 4, 'Z')
    angs = sorted(rng.uniform(0, 6.283) for _ in range(sides))
    top = []
    for a in angs:
        r = rng.uniform(0.75, 1.0)
        top.append(Vector((math.cos(a) * size[0] * r, math.sin(a) * size[1] * r, 0.0)))
    cen = sum(top, Vector()) / len(top)
    rmin = min((v - cen).length for v in top)
    t = 1.0 / math.tan(math.radians(wall))
    s_bot = max(0.15, 1.0 - depth * t / max(rmin, 1e-4))
    s_top = 1.0 + margin * t / max(rmin, 1e-4)
    ta, tb = math.radians(rng.uniform(-tilt, tilt)), math.radians(rng.uniform(-tilt, tilt))
    vs = []
    for v in top:                                     # 바닥 (기운 평면)
        b = cen + (v - cen) * s_bot
        vs.append(Vector((b.x, b.y, -depth + math.tan(ta) * b.x + math.tan(tb) * b.y)))
    for v in top:                                     # 겉면 위로 margin 만큼
        u = cen + (v - cen) * s_top
        vs.append(Vector((u.x, u.y, margin)))
    m = len(top)
    faces = [tuple(range(m - 1, -1, -1)), tuple(range(m, 2 * m))]
    for i in range(m):
        j = (i + 1) % m
        faces.append((i, j, m + j, m + i))
    M = Matrix.Translation(Vector(p)) @ q
    return mesh_from("spall", [M @ v for v in vs], faces)


def rock_b():
    """큰 바위 ~3.5m: 정으로 쳐서 깨진 듯 각진 큰 바위, 위에서 쐐기처럼 갈라진 틈, 평평하게 떨어져 나간 자국, 윗면 이끼, 발치에 풀.
    v3b: 상자에서 깊은 평면으로 깎은 덩어리(둥근 구 바탕을 쓰지 않는다) + 불리언 합치기(리메시 없이 깨끗한 평면) →
    쐐기 틈·모서리 깨짐(chip)·평면 spall(벽 45도) 까지 들어간 깨끗한 형태에서 저폴리 (큰 면을 저폴리가 그대로 따라가
    굽기 광선이 스치지 않는다) + 단단한 모서리·이음매. 원본은 되붙인 리메시 + ROCK3(큰 평면 끌 면 + 굵은 금 몇 줄)"""
    rng = random.Random(33)
    main = facet_mass(rng, (4.3, 3.4, 3.1), (0, 0, 0.8), planes=16, depth=(0.1, 0.24), rz=R(8), chamfer=22)
    side = facet_mass(rng, (2.0, 1.8, 1.6), (1.75, 0.75, 0.3), planes=10, depth=(0.1, 0.24), chamfer=10)
    union(main, [side])
    o = main
    # 위에서 아래로 좁아지는 쐐기 틈 (바닥까지는 가지 않는다)
    wedge_ = prism([(-0.05, 0.85), (0.05, 0.85), (0.42, 2.9), (-0.38, 2.9)], -2.0, 2.0)
    wedge_.rotation_euler = (R(3), R(-10), R(26)); wedge_.location = (0.2, 0, 0.0)
    xf_all(wedge_)
    cut(o, [wedge_])
    chip_convex(o, rng, 6, (0.22, 0.4), zmin=0.3)
    # 모서리에서 평면으로 떨어져 나간 계단 자국 (바닥 평면 + 40도 벽) → 저폴리에도 넣는다
    step_spalls(o, rng, 6, (0.45, 0.8), (0.05, 0.09))
    origin0(o)
    low = lowpoly(o, z=-0.05)
    co, fi = ROCK3(1.8, 0.7, chisel=0.25)     # 큰 평면 끌 면 (칸 75 cm, 깊이 1 cm 안팎) — 넓은 면이 비닐처럼 비지 않게
    carve(o, 0.005, co, fi, seed=5, pieces=False, mode='octree')
    m = paint3("rock_b", ROCK_PAL, h=2.3, k=1.8, cells=0.7, piece_var=0.4, piece_val=0.08, facet_var=0.3, light=1.2, moss=1.0, moss_low=0.5,
               moss_low_h=0.35, dirt=0.6, dirt_h=0.3, edge=0.0, edge_w=0.014, edge_gain=0.95, streaks=0.55, ao=0.5, grain=0.12, tooling=0.0,
               speckle=0.4, strokes=0.8, stains=0.55, edge_mode="attr", lichen=0.0, contrast=0.28, strata=1.0, strata_scale=2.0,
               moss_patch=1.5)
    # v3c: 지의류 반점(lichen 0.55)이 온 면에 고르게 찍혀 위장무늬처럼 읽혔다 → 없애고, 이끼는 윗면·틈에 큰 덩어리로(moss_patch 2.4 → 1.5),
    # 넓은 옆면은 돌 결 줄무늬(strata)와 삭은 얼룩으로. 모서리 빛(edge)은 끄고 굽기에서 단단한 모서리 띠를 섬 안쪽 값으로 메운다(flat_hard)
    #  — 모서리를 따라 생기던 얇은 밝은 보풀 줄 (칠한 빛 띠 + 둥근 원본 모서리를 스친 광선의 빗살)
    set_mat(o, m)
    print("LOW rock_b", tri_count(low))
    cards = Cards()
    grass_on_top(cards, low, rng, 9, (1.6, 1.2), zmin=0.9, h=(0.2, 0.4), w=(0.2, 0.35), nz=0.75)
    # 바닥 둘레 풀
    for _ in range(10):
        a = rng.uniform(0, 6.28)
        p = Vector((math.cos(a) * 1.75, math.sin(a) * 1.3, 0.0))
        grass_tuft(cards, rng, p, rng.uniform(0.25, 0.45), rng.uniform(0.25, 0.4), 3, 0.4)
    down = lambda c, n: 0.55 if n.z < -0.3 else 1.0
    return finish3("rock_b", [o], [low], extras=[cards.obj("grass")], cage=0.012, cage_reach=0.1, uv_angle=40, hard=38,
                   uv_margin=0.002, uv_weight=down, flat_hard=6)


def low_parts(high, tris, z=-0.05, floor=60):
    """저폴리: 떨어진 조각마다 보이는 넓이에 비례해 삼각형을 나눠 준다 (작은 돌이 납작하게 뭉개지지 않게)"""
    c = copy(high)
    c.modifiers.clear()
    drop_below(c, z)
    act(c)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    parts = list(bpy.context.selected_objects)
    areas = [sum(p.area for p in o.data.polygons) for o in parts]
    keep = []
    for o, a in zip(parts, areas):
        if a < 2e-3:
            delete(o)
        else:
            keep.append((o, a))
    A = sum(a for _, a in keep) or 1.0
    for o, a in keep:
        t = max(floor, int(tris * a / A))
        n = tri_count(o)
        if n > t:
            m = o.modifiers.new('dec', 'DECIMATE'); m.ratio = t / n; m.use_collapse_triangulate = True
            apply_all(o)
    low = join([o for o, _ in keep])
    for p in low.data.polygons:
        p.use_smooth = True
    return low


def rock_c():
    """작은 돌 ~0.7m 와 조약돌 둘 (흩뿌리기)"""
    rng = random.Random(77)
    a = rock_mass(rng, (0.8, 0.62, 0.52), (0, 0, 0.14), planes=18, depth=(0.03, 0.17), base='sphere')
    b = rock_mass(rng, (0.32, 0.26, 0.2), (0.48, -0.24, 0.04), planes=11, depth=(0.04, 0.2), base='sphere')
    c = rock_mass(rng, (0.24, 0.2, 0.15), (-0.44, 0.26, 0.03), planes=10, depth=(0.04, 0.2), base='sphere')
    for o in (a, b, c):
        chip(o, rng, 5, (0.05, 0.13), sharp_deg=25, bite=0.32)
    spalls_on(a, rng, 3, (0.14, 0.24), (0.018, 0.035), center=(0, 0, 0.15))
    o = join([a, b, c])
    base = sculpt2(o, 0.0045, *rock_split(0.55, 0.6), seed=9)
    m = rock_paint("rock_c", 0.6, moss=0.75, dirt=0.7)
    set_mat(o, m)
    low = low_parts(base, 2400, floor=200); delete(base)
    soften(low, 4)
    return finish("rock_c", [o], [low], size=1024, extr=0.03, uv_angle=75)


def rock_flat():
    """납작한 판석 노두 ~3x2x0.7m: 층층이 쌓여 어긋난 판, 틈에 이끼와 풀"""
    rng = random.Random(55)
    specs = [((3.2, 2.15, 0.36), (0.0, 0.0, 0.0), 0.0, (0.02, 0.0)),
             ((2.55, 1.75, 0.26), (0.2, 0.12, 0.3), 6.0, (0.0, -0.025)),
             ((1.65, 1.15, 0.2), (-0.32, 0.2, 0.52), -11.0, (0.03, 0.02))]
    parts = []
    for dims, c, rz, tl in specs:
        o = box(*dims, c, rot=(tl[0], tl[1], R(rz)))
        xf_all(o)
        facet(o, rng, 10, (0.04, 0.2), nz=(-0.3, 0.25))
        chip(o, rng, 9, (0.12, 0.3), sharp_deg=25, bite=0.34)
        parts.append(o)
    # 위 판에서 떨어져 나와 비스듬히 기댄 조각
    f = box(0.7, 0.5, 0.16, (1.35, -0.75, 0.3), rot=(R(14), R(-22), R(30)))
    xf_all(f); facet(f, rng, 7, (0.05, 0.25)); chip(f, rng, 4, (0.08, 0.16), bite=0.32)
    parts.append(f)
    o = join(parts)
    remesh(o, 0.012)
    spalls_on(o, rng, 6, (0.25, 0.45), (0.03, 0.06), zdir=(-0.1, 0.4), center=(0, 0, 0.25))
    co, fi = rock_split(1.4, 0.6)
    base = sculpt2(o, 0.0105, co, fi + [{'t': 'strata', 'freq': 16.0, 'amp': 0.007, 'warp': 0.15}], seed=12)
    m = rock_paint("rock_flat", 1.5, moss=0.9)
    top_cover(m, MOSS, amount=0.6, scale=1.1, k=1.5, nz=(0.7, 0.92), lo=0.45, hi=0.58)
    set_mat(o, m)
    low = low_parts(base, 6000, floor=300); delete(base)
    soften(low)
    cards = Cards()
    for _ in range(14):
        a = rng.uniform(0, 6.28)
        rr = rng.uniform(0.85, 1.05)
        p = Vector((math.cos(a) * 1.6 * rr, math.sin(a) * 1.1 * rr, 0.0))
        grass_tuft(cards, rng, p, rng.uniform(0.22, 0.42), rng.uniform(0.25, 0.4), 3, 0.4)
    grass_on_top(cards, low, rng, 5, (1.2, 0.8), zmin=0.15, h=(0.14, 0.26), w=(0.16, 0.26), nz=0.8)
    return finish("rock_flat", [o], [low], extras=[cards.obj("grass")], size=1024, extr=0.05, uv_angle=75)


# ───────────────────────── 절벽 ─────────────────────────
def blob_poly(rng, rx, ry, n=11, jit=0.16):
    a0 = rng.uniform(0, 6.28)
    pts = []
    for i in range(n):
        a = a0 + 2 * math.pi * (i + rng.uniform(-0.25, 0.25)) / n
        r = 1 + rng.uniform(-jit, jit)
        pts.append(Vector((math.cos(a) * rx * r, math.sin(a) * ry * r)))
    return pts


def slab_obj(top, bot, z0, z1, ztop=None):
    """두 다각형(같은 점 개수) 사이의 판. ztop: 윗면 점마다 높이 (기울고 울퉁불퉁한 윗면)"""
    n = len(top)
    zt = ztop or [z1] * n
    verts = [(p.x, p.y, z0) for p in bot] + [(p.x, p.y, zt[i]) for i, p in enumerate(top)]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    o = mesh_from("slab", verts, faces)
    # 윗면 다각형을 삼각형으로 (볼록하지 않아도 불리언이 안전하게)
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bm.to_mesh(o.data); bm.free()
    return o


def poly_radius(poly, ang):
    """다각형 중심에서 ang 방향 경계까지 거리 (대략)"""
    d = Vector((math.cos(ang), math.sin(ang)))
    best = 0.0
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        # 선분 a-b 와 반직선 교차
        e = b - a
        den = d.x * e.y - d.y * e.x
        if abs(den) < 1e-9:
            continue
        t = (a.x * e.y - a.y * e.x) / den
        u = (a.x * d.y - a.y * d.x) / den
        if t > 0 and 0 <= u <= 1:
            best = max(best, t)
    return best


def sector_block(rng, base, angs, z0, z1, kt, kb, inner, center, ztop=None):
    """다각형 base 의 각 구간(angs) 부채꼴 블록: 바깥 호(경계) + 안쪽 호(inner 비율)를 z0~z1 로 세운다.
    kt, kb: 각도별 윗면·아랫면 배율 함수"""
    c = Vector(center)
    outer_t, outer_b, inner_t, inner_b = [], [], [], []
    for a in angs:
        d = Vector((math.cos(a), math.sin(a)))
        r = poly_radius(base, a)
        outer_t.append(c + d * r * kt(a)); outer_b.append(c + d * r * kb(a))
        inner_t.append(c + d * r * inner); inner_b.append(c + d * r * inner)
    top = outer_t + inner_t[::-1]
    bot = outer_b + inner_b[::-1]
    zt = None
    if ztop is not None:
        zt = [ztop(q) for q in top]
    return slab_obj(top, bot, z0, z1, zt)


def block_stack(rng, base, z0, H, thick=(1.0, 2.0), soft=0.25, taper=(0.1, 0.35), lean=(0.0, 0.0), sectors=8,
                gap=0.14, push=(-0.1, 0.07), lip=0.04, inset=0.06, facets=4, chips=2, chip_size=(0.25, 0.55),
                top_tilt=(0.0, 0.0), top_bump=0.2, center=(0.0, 0.0), stagger=0.25, core=0.6, foot=0.1, top_drop=1.6,
                facet_depth=0.12, bulge=0.0):
    """기둥 모양 블록으로 쌓은 절벽.
    둘레를 부채꼴 기둥으로 나누고(세로 절리), 기둥마다 튀어나온 정도와 꼭대기 높이가 달라 윗선이 들쭉날쭉하다.
    기둥은 층마다 끊기고(가로 층리), 단단한 층은 아래가 살짝 들어가 턱이 지며, 무른 층은 얇고 들어간다.
    블록 바깥면은 여러 평면으로 비스듬히 쳐서 벽돌이 아니라 깨진 바위처럼 보이게 한다. 가운데는 심(core)으로 채우고
    심 윗면은 가장 낮은 기둥보다 낮게 두어 흙이 고일 자리를 만든다. 돌려주는 값: (조각 목록, 심 윗면 높이)"""
    parts = []
    R0 = sum(poly_radius(base, 2 * math.pi * i / 16) for i in range(16)) / 16
    gap_ang = gap / R0
    a_base = [rng.uniform(0, 6.283)]
    for i in range(1, sectors):
        a_base.append(a_base[0] + 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / sectors)
    col_push = [rng.uniform(*push) for _ in range(sectors)]
    col_top = [H - rng.uniform(0.0, top_drop) for _ in range(sectors)]
    col_top[rng.randrange(sectors)] = H
    core_top = H - top_drop * 0.75
    z = z0
    off = Vector((0, 0))
    while z < H - 0.05:
        hard = rng.random() > soft
        t = rng.uniform(*thick) * (1.0 if hard else 0.3)
        z1 = min(z + t, H)
        if H - z1 < 0.4:
            z1 = H
        h0 = (z - z0) / max(H - z0, 1e-6); h1 = (z1 - z0) / max(H - z0, 1e-6)
        off = off * 0.6 + Vector((rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05)))
        cen = Vector(center) + off + Vector((lean[0], lean[1])) * h0
        lk = 1 + rng.uniform(-bulge, bulge)        # 층마다 부풀거나 잘록하게

        def tp(a):
            fy = (math.sin(a) + 1) / 2          # 0 앞(-Y) ~ 1 뒤(+Y)
            return taper[0] + (taper[1] - taper[0]) * fy
        shift = rng.uniform(-0.3, 0.3) * 2 * math.pi / sectors if rng.random() < stagger else 0.0
        order = sorted(range(sectors), key=lambda i: a_base[i])
        bounds = [a_base[i] + shift + rng.uniform(-0.04, 0.04) for i in order]
        for k in range(sectors):
            ci = order[k]
            zt_col = col_top[ci]
            if z >= zt_col - 0.25:
                continue
            zz1 = min(z1, zt_col)
            is_top = zz1 >= zt_col - 1e-6
            a0 = bounds[k] + gap_ang / 2
            a1 = (bounds[(k + 1) % sectors] + (2 * math.pi if k == sectors - 1 else 0)) - gap_ang / 2
            if a1 - a0 < 0.05:
                continue
            m = max(2, int((a1 - a0) / 0.12))
            angs = [a0 + (a1 - a0) * j / m for j in range(m + 1)]
            p = col_push[ci] + rng.uniform(-0.03, 0.03) - (0.0 if hard else inset)
            hh1 = (zz1 - z0) / max(H - z0, 1e-6)
            ft1 = foot * max(0.0, 1 - hh1 / 0.22); ft0 = foot * max(0.0, 1 - h0 / 0.22)
            kt = lambda a, p=p, h1=hh1, ft1=ft1, lk=lk: (1 - tp(a) * h1) * (1 + p + ft1) * lk
            kb = lambda a, p=p, h0=h0, hard=hard, ft0=ft0, lk=lk: (1 - tp(a) * h0) * (1 + p + ft0) * ((1 - lip) if hard else 1.0) * lk
            ztf = None
            if is_top:
                ph = rng.uniform(0, 6.28)
                ztf = lambda q, ph=ph, zc=zz1: zc + top_tilt[0] * (q.x - center[0]) + top_tilt[1] * (q.y - center[1]) + \
                    top_bump * (math.sin(q.x * 0.9 + ph) * math.cos(q.y * 1.3 - ph) + rng.uniform(-0.5, 0.5))
            s = sector_block(rng, base, angs, z - 0.03, zz1 + (0.0 if is_top else 0.03), kt, kb, core * 0.95, cen, ztf)
            mid = (a0 + a1) / 2
            for _ in range(facets):
                aa = mid + rng.uniform(-0.6, 0.6) * (a1 - a0)
                nrm = Vector((math.cos(aa), math.sin(aa), rng.uniform(-0.4, 0.45))).normalized()
                bm = bmesh.new(); bm.from_mesh(s.data)
                proj = [v.co.dot(nrm) for v in bm.verts]
                mx, mn = max(proj), min(proj)
                co = nrm * (mx - min(0.45, (mx - mn) * rng.uniform(0.03, facet_depth)))
                geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
                r_ = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=nrm, clear_outer=True)
                edges = [g for g in r_['geom_cut'] if isinstance(g, bmesh.types.BMEdge)]
                if edges:
                    bmesh.ops.holes_fill(bm, edges=edges, sides=0)
                bm.to_mesh(s.data); bm.free(); s.data.update()
            if chips:
                chip(s, rng, chips, chip_size, sharp_deg=30, bite=0.3)
            parts.append(s)
        # 심: 가운데를 채운다 (윗면은 core_top)
        if z < core_top:
            zc1 = min(z1, core_top)
            cp = [cen + Vector((q.x, q.y)) * core * lk * (1 - tp(math.atan2(q.y, q.x)) * h0) for q in base]
            parts.append(slab_obj(cp, cp, z - 0.03, zc1 + (0.0 if zc1 >= core_top else 0.03)))
        z = z1
    return parts, core_top


def bites(o, rng, base, n, z_range, size=(2.0,3.5), center=(0, 0), out=0.45, ang=None):
    """윗가장자리를 크게 무너뜨린다: 각진 덩어리 커터를 둘레에 박아 계단처럼 깨진 윤곽을 만든다"""
    cs = []
    for i in range(n):
        a = rng.uniform(0, 6.283) if ang is None else ang[i]
        r = poly_radius(base, a)
        s = rng.uniform(*size)
        p = (center[0] + math.cos(a) * (r + s * out), center[1] + math.sin(a) * (r + s * out), rng.uniform(*z_range) + s * 0.45)
        cs.append(rock_mass(rng, (s, s * rng.uniform(0.7, 1.0), s * rng.uniform(0.8, 1.2)), p, planes=9, depth=(0.05, 0.2)))
    if cs:
        cut(o, cs)
    return o


def soil_cap(rng, base, z, k=0.7, h=0.35, center=(0, 0)):
    """윗면 가운데 고인 흙더미 (이끼·풀이 덮는다). 가장자리는 낮고 가운데가 볼록"""
    c = Vector(center)
    out = [c + q * k * rng.uniform(0.95, 1.05) for q in base]
    inn = [c + q * k * 0.55 for q in base]
    n = len(base)
    verts = [(p.x, p.y, z - 0.5) for p in out] + [(p.x, p.y, z + h * rng.uniform(0.15, 0.35)) for p in out] + \
            [(p.x, p.y, z + h * rng.uniform(0.75, 1.0)) for p in inn] + [(c.x, c.y, z + h)]
    faces = [tuple(range(n - 1, -1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
        faces.append((n + i, n + j, 2 * n + j, 2 * n + i))
        faces.append((2 * n + i, 2 * n + j, 3 * n))
    return mesh_from("soil", verts, faces)


def talus(rng, n, ring, size=(0.5, 1.4), z=(-0.15, 0.1)):
    """절벽 발치에 떨어져 쌓인 바위"""
    out = []
    for _ in range(n):
        a = rng.uniform(0, 6.283)
        rr = rng.uniform(0.9, 1.1)
        s = rng.uniform(*size)
        p = (math.cos(a) * ring[0] * rr, math.sin(a) * ring[1] * rr, rng.uniform(*z) + s * 0.25)
        b = rock_mass(rng, (s, s * rng.uniform(0.6, 0.9), s * rng.uniform(0.5, 0.8)), p, planes=11, depth=(0.05, 0.25))
        chip(b, rng, 3, (s * 0.12, s * 0.25), sharp_deg=25, bite=0.3)
        out.append(b)
    return out


def CLIFF_LAYERS(k=4.0, fis=0.45):
    return [
        {'t': 'lumps', 'scale': 0.55 / k, 'amp': 0.012 * k},
        {'t': 'strata', 'freq': 3.0, 'amp': 0.03, 'warp': 0.35},
        {'t': 'strata', 'freq': 1.1, 'amp': 0.03, 'warp': 0.6},
        {'t': 'terrace', 'scale': 1.0 / k, 'steps': 5, 'amp': 0.028 * k, 'cover': 0.75, 'cover_scale': 0.8 / k},
        {'t': 'fissure', 'scale': 0.8 / k, 'width': 0.013, 'depth': 0.03 * k, 'cover': fis},
        {'t': 'fissure', 'scale': 2.6 / k, 'width': 0.011, 'depth': 0.009 * k, 'cover': fis * 0.7},
        {'t': 'pits', 'scale': 14.0 / k, 'depth': 0.0025 * k, 'cover': 0.35},
        {'t': 'grain', 'scale': 45.0 / k, 'amp': 0.001 * k},
    ]


EARTH_MOSS = (0.05, 0.075, 0.055)


CLIFF_PAL = ((0.032, 0.034, 0.055), (0.165, 0.165, 0.235), (0.56, 0.58, 0.76))


def cliff_paint(name, H, k=4.0, pal=CLIFF_PAL, top_z=None):
    m = rock_paint(name, k, pal, moss=0.85, streaks=0.6, dirt=0.5, ao=1.2, edge=0.6, cracks=0.25)
    grad_dark(m, -0.2, H * 0.6, 0.85, wob=1.0)
    top_cover(m, MOSS, amount=0.75, scale=0.55, k=1.0, nz=(0.62, 0.88), lo=0.42, hi=0.56)      # 턱마다 이끼
    top_cover(m, EARTH_MOSS, z0=(H - 1.0) if top_z is None else top_z, amount=0.95, scale=0.35, k=1.0, nz=(0.5, 0.8),
              lo=0.3, hi=0.42)
    return m


def hang_over_edge(cards, target, rng, n, z_band, center, length=(0.6, 1.8), width=(0.3, 0.6)):
    """절벽 윗가장자리에서 늘어진 이끼·뿌리"""
    pts = surf_points(target, rng, n, (-0.05, 0.05), center=Vector((center[0], center[1], z_band)),
                      cond=lambda p, nr: abs(nr.z) < 0.5)
    for p, nr in pts:
        out = Vector((nr.x, nr.y, 0)).normalized()
        moss_hang(cards, rng, p + out * 0.06 + Vector((0, 0, 0.05)), rng.uniform(*length), rng.uniform(*width), 2,
                  color=(0.3, 0.38, 0.3), face=math.atan2(out.y, out.x) + math.pi / 2)
    return len(pts)


def cliff_finish(name, rng, slabs, extra, H, voxel, tris, k, area, grass_n, hang_n, extr=0.14, top_z=None, seed=4):
    o = join(slabs + extra)
    remesh(o, voxel * 1.6)
    spalls_on(o, rng, 10, (0.6, 1.3), (0.08, 0.18), zdir=(-0.15, 0.35), center=(0, 0, H * 0.5))
    L = CLIFF_LAYERS(k)
    base = sculpt2(o, voxel, [L[0], L[3]], L[1:3] + L[4:], seed=seed)
    m = cliff_paint(name, H, k, top_z=top_z)
    set_mat(o, m)
    low = low_from(base, tris, z=-0.1); delete(base)
    soften(low, 4)
    cards = Cards()
    grass_on_top(cards, low, rng, grass_n, area, zmin=(H - 1.5) if top_z is None else top_z, h=(0.35, 0.65), w=(0.4, 0.7),
                 nz=0.65)
    hang_over_edge(cards, low, rng, hang_n, H - 0.45, (0, 0))
    print("CLIFF", name, "low", tri_count(low), "cards", cards.tris())
    return finish(name, [o], [low], extras=[cards.obj("cards")], size=2048, extr=extr, lod1=0.35, lod2=0.12, uv_angle=72)


def cliff_a():
    """절벽 덩어리 ~10x6x8m: 앞(-Y)은 가파르고 뒤는 층계처럼 물러난다. 세로 절리로 갈라진 바위 기둥,
    들쭉날쭉한 윗선 사이에 흙과 풀, 턱마다 이끼, 발치에 떨어진 바위"""
    rng = random.Random(101)
    H = 8.0
    base = blob_poly(rng, 4.9, 2.9, 12, 0.12)
    parts, ctop = block_stack(rng, base, -0.5, H, thick=(1.1, 2.2), soft=0.3, taper=(0.04, 0.45), lean=(0.3, -0.25),
                              sectors=10, gap=0.18, push=(-0.13, 0.08), lip=0.05, inset=0.08, facets=4, chips=2,
                              chip_size=(0.3, 0.7), top_tilt=(0.02, 0.05), top_bump=0.15, foot=0.12, top_drop=1.8)
    o = join(parts)
    remesh(o, 0.064)
    bites(o, rng, base, 1, (4.4, 4.4), (3.6, 3.6), ang=[R(205)], out=0.12)
    extra = talus(rng, 7, (5.1, 3.2), (0.6, 1.5)) + [soil_cap(rng, base, ctop, 0.7, 0.55, (0.3, -0.1))]
    return cliff_finish("cliff_a", rng, [o], extra, H, 0.04, 24000, 4.0, (4.2, 2.5), 40, 9, top_z=ctop - 0.2)


def cliff_b():
    """바위 첨탑 ~5x5x12m: 기울며 가늘어지는 바위 기둥 (층마다 부풀고 잘록하다), 뾰족하게 부서진 꼭대기"""
    rng = random.Random(202)
    H = 10.6
    base = blob_poly(rng, 2.6, 2.4, 10, 0.14)
    parts, ctop = block_stack(rng, base, -0.5, H, thick=(1.2, 3.0), soft=0.2, taper=(0.38, 0.5), lean=(1.1, 0.45), sectors=6,
                              gap=0.15, push=(-0.1, 0.07), lip=0.06, inset=0.08, facets=5, chips=2, chip_size=(0.25, 0.55),
                              top_tilt=(0.12, -0.06), top_bump=0.2, core=0.84, top_drop=0.6, foot=0.2, facet_depth=0.2,
                              stagger=0.2, bulge=0.1)
    tops = []
    for i, (dx, dy, s, hk) in enumerate(((0.2, 0.1, 1.15, 2.3), (-0.45, 0.35, 0.8, 1.7), (0.55, -0.4, 0.7, 1.4))):
        p = (1.1 + dx, 0.45 + dy, H - 0.35 + s * hk * 0.45)
        tops.append(rock_mass(rng, (s, s * 0.8, s * hk), p, planes=11, depth=(0.08, 0.32)))
    extra = tops + talus(rng, 6, (3.0, 2.8), (0.5, 1.2))
    # 위쪽 기둥 사이 절리 틈이 좁아 굽기 거리를 작게 (크면 틈 벽의 광선이 맞은편 벽 속에서 출발해 검게 굽힌다)
    return cliff_finish("cliff_b", rng, parts, extra, H + 1.6, 0.035, 20000, 3.5, (1.3, 1.3), 6, 5, top_z=H - 0.8, extr=0.07)


def cliff_c():
    """넓고 낮은 절벽 ~14x6x5m: 두 단으로 물러나는 단층애"""
    rng = random.Random(303)
    base = blob_poly(rng, 7.0, 2.9, 15, 0.1)
    low_tier, c1 = block_stack(rng, base, -0.5, 2.8, thick=(0.9, 1.6), soft=0.3, taper=(0.05, 0.2), sectors=12, gap=0.17,
                               push=(-0.1, 0.07), lip=0.04, inset=0.06, facets=4, chips=2, chip_size=(0.25, 0.55),
                               top_tilt=(0.0, 0.03), top_bump=0.12, top_drop=0.7)
    base2 = [Vector((p.x * 0.78, p.y * 0.62)) for p in blob_poly(rng, 6.8, 2.8, 14, 0.12)]
    up_tier, c2 = block_stack(rng, base2, 2.2, 5.2, thick=(0.9, 1.5), soft=0.3, taper=(0.1, 0.3), sectors=10, gap=0.16,
                              push=(-0.1, 0.07), lip=0.04, inset=0.06, facets=4, chips=2, chip_size=(0.25, 0.5),
                              top_tilt=(0.01, 0.06), top_bump=0.15, center=(0.4, 0.75), top_drop=1.2)
    extra = talus(rng, 8, (7.4, 3.2), (0.5, 1.3)) + [soil_cap(rng, base2, c2, 0.7, 0.4, (0.4, 0.75))]
    return cliff_finish("cliff_c", rng, low_tier + up_tier, extra, 5.2, 0.04, 26000, 4.0, (6.5, 2.7), 45, 10, top_z=2.0)


# ───────────────────────── 죽은 나무 ─────────────────────────
# 큰 가지에서 나는 곁가지들 (바깥쪽 절반에 몰려 발톱 같은 손을 이룬다)
CLAW_LEVELS = [
    dict(kids=(4, 6), t=(0.25, 0.95), angle=(25, 58), len=(0.32, 0.55), r=(0.5, 0.7), seg=0.18, gnarl=0.36, up=0.07, kink=0.35,
         taper=1.3, bumps=0.07, kid_up=0.08, len_t=0.45, lmin=0.25),
    dict(kids=(3, 5), t=(0.25, 0.92), angle=(25, 55), len=(0.32, 0.55), r=(0.5, 0.75), seg=0.1, gnarl=0.42, up=0.05, kink=0.3,
         taper=1.3, bumps=0.04, rmin=0.004, lmin=0.12, len_t=0.4),
    dict(kids=(1, 3), t=(0.35, 0.9), angle=(25, 50), len=(0.3, 0.5), r=(0.5, 0.75), seg=0.06, gnarl=0.4, up=0.04,
         taper=1.3, bumps=0.0, rmin=0.0035, lmin=0.08),
]
DEAD_LEVELS = CLAW_LEVELS


def limb(tr, parent, t, az, elev, length, r_k=0.75, taper=1.4, gnarl=0.25, up=0.06, seg=0.3, kink=0.3, levels=CLAW_LEVELS,
         lobes=3, lobe_amp=0.08, droop=0.0):
    """줄기의 t 지점에서 방위 az·앙각 elev(도)로 큰 가지를 내고 곁가지를 키운다"""
    rng = tr.rng
    p, r, T, N, B = tr.at(parent, t)
    d = Vector((math.cos(R(az)) * math.cos(R(elev)), math.sin(R(az)) * math.cos(R(elev)), math.sin(R(elev))))
    side = Vector((d.x, d.y, 0)).normalized()
    pts = path_grow(rng, p - side * r * 0.35, d, length, seg, gnarl, up, droop, kink)
    b = tr.branch(pts, r * r_k, 0.003, taper, parent['depth'] + 1, collar=1.3, lobes=lobes, lobe_amp=lobe_amp, twist=0.8,
                  bumps=0.08, parent=parent)
    tr.grow(b, levels)
    return b


def _ring_dir(T, N, B, want):
    """고리 시작 각 a0: 방향 N·cos a0 + B·sin a0 이 want(고리 평면에 투영)와 가장 가깝게 (UV 이음매를 덜 보이는 쪽으로)"""
    w = Vector(want) - T * Vector(want).dot(T)
    if w.length < 1e-6:
        return 0.0
    return math.atan2(w.dot(B), w.dot(N))


def tree_low_uv(tree, split_r, r_cut=0.03, low_step=(0.08, 0.3), rho=None, seam=None, z_cut=-0.06, name="tree", groups=None):
    """(v3b) 원통 전개 저폴리: 가지마다 관 하나 + 이음매 하나 (UV 섬 = 가지 하나). 굵은 부분(A)은 원본 관과 같은 고리 틀·골(lobes)을
    따라 성기게 다시 찍고, 부모 속에 묻힌 시작 부분과 땅속(z_cut 아래) 고리는 버린다. 잔가지(B)는 예전 저폴리 관에 UV 만 붙인다.
    rho(가지, 점, 'A'|'B') → 텍셀 배율 (줄기 밑동 1.0 … 잔가지 0.25): 섬 크기를 이것으로 정해 pack 이 같은 비율로 키운다.
    seam(가지) → 이음매가 향할 방향 (가지 위쪽 +Z: 땅에서 올려다보면 안 보인다)
    돌려주는 값: (A 객체, B 객체) — UV 층 'UVMap'"""
    from mathutils.kdtree import KDTree
    rho = rho or (lambda b, p, kind: 1.0)
    seam = seam or (lambda b: (0, 0, 1))
    groups = groups or {}               # 조각 번호 → 굽기 무리 ('bgrp' 면 속성, kit.finish(bake_groups))
    dense, kds = {}, {}

    def par_kd(par):
        if id(par) not in kds:
            pp, pr = resample(par['pts'], par['rads'], 0.02)
            kd = KDTree(len(pp))
            for i, q in enumerate(pp):
                kd.insert(q, i)
            kd.balance()
            kds[id(par)] = (kd, pr)
        return kds[id(par)]

    accs = {'A': ([], [], [], []), 'B': ([], [], [], [])}      # verts, faces, face_uvs, face groups

    def emit(kind, ring_pts, ring_uv, tip_pt, tip_uv, cap_end, grp=0, split=0.6):
        """고리들을 관으로. 둘레(UV 폭)가 구간 시작의 split 배 아래로 줄면 거기서 UV 섬을 끊는다 (정점은 그대로 이어져 음영은 매끈하다).
        한 섬이 뾰족한 세모(밑동이 넓게 퍼진 줄기)가 되면 배치가 성겨 텍셀이 크게 준다 (v3b 첫 판: uv_fill 0.43)"""
        V, F, U, G = accs[kind]
        f0 = len(F)
        base = len(V)
        nring = len(ring_pts)
        sides = len(ring_pts[0])
        for ring in ring_pts:
            V.extend(ring)
        width = [ring_uv[i][-1][0] - ring_uv[i][0][0] for i in range(nring)]
        seg_v0, seg_of = [], []
        v0, w0 = ring_uv[0][0][1], width[0]
        for i in range(nring - 1):
            if split and width[i] < w0 * split and i > 0:
                v0, w0 = ring_uv[i][0][1], width[i]
            seg_of.append(v0)
        if not seg_of:
            seg_of = [ring_uv[0][0][1]]
        sh = lambda uv, off: (uv[0], uv[1] - off)
        for i in range(nring - 1):
            off = seg_of[i]
            for k in range(sides):
                k1 = (k + 1) % sides
                a, b_, c, d = base + i * sides + k, base + i * sides + k1, base + (i + 1) * sides + k1, base + (i + 1) * sides + k
                F.append((a, b_, c, d))
                U.append((sh(ring_uv[i][k], off), sh(ring_uv[i][k + 1], off), sh(ring_uv[i + 1][k + 1], off), sh(ring_uv[i + 1][k], off)))
        last = base + (nring - 1) * sides
        off = seg_of[-1]
        if tip_pt is not None:
            t = len(V); V.append(tip_pt)
            for k in range(sides):
                F.append((last + k, last + (k + 1) % sides, t))
                U.append((sh(ring_uv[-1][k], off), sh(ring_uv[-1][k + 1], off), sh(tip_uv, off)))
        elif cap_end:
            t = len(V); V.append(sum(ring_pts[-1], Vector()) / sides)
            cu = (sum(u for u, v in ring_uv[-1][:-1]) / sides, ring_uv[-1][0][1])
            for k in range(sides):
                F.append((last + k, last + (k + 1) % sides, t))
                U.append((sh(ring_uv[-1][k], off), sh(ring_uv[-1][k + 1], off), sh(cu, off)))
        G.extend([grp] * (len(F) - f0))

    nA = nB = 0
    for pi, (pts, rads, kind, b, s0, tip) in enumerate(tree.pieces(split_r, r_cut)):
        r0 = max(rads)
        if kind == 'A':
            step_hi = min(max(r0 * 0.25, 0.012), 0.06)            # 원본 관(Tree.meshes)과 같은 점·틀
            pp, rr = respace(pts, rads, step_hi)
            T, N, B = frames(pp)
            sides = int(min(max(2 * math.pi * r0 / 0.11, 6), 22))
            if b['lobes']:
                sides = max(sides, 3 * b['lobes'] + 1)
            step_lo = min(max(r0 * 0.9, 0.1), 0.3)
            bumps = b['bumps']
        else:
            step = min(max(sum((pts[i] - pts[i - 1]).length for i in range(1, len(pts))) / 4, low_step[0]), low_step[1])
            pp, rr = respace(pts, rads, step)
            T, N, B = frames(pp)
            sides = 5 if r0 > 0.02 else (4 if r0 > 0.009 else 3)
            step_lo = 0.0
            bumps = 0.0
        n = len(pp)
        S = [s0]
        for i in range(1, n):
            S.append(S[-1] + (pp[i] - pp[i - 1]).length)
        # 고리 고르기: step_lo 마다 + 굵기가 15% 넘게 변하거나 10도 넘게 꺾인 곳
        idx = [0]
        for i in range(1, n - 1):
            j = idx[-1]
            if (S[i] - S[j] >= step_lo or abs(rr[i] - rr[j]) > 0.15 * max(rr[j], 1e-3) or T[i].angle(T[j], 0.0) > R(10)):
                idx.append(i)
        idx.append(n - 1)
        # 부모 속에 묻힌 시작 고리 버리기 (하나는 남겨 틈이 없게)
        par = b.get('parent')
        if par is not None and kind == 'A':
            kd, pr = par_kd(par)
            first = 0
            for m_, i in enumerate(idx):
                q, qi, dist = kd.find(pp[i])
                if dist > pr[qi] * 0.9:
                    first = max(0, m_ - 1)
                    break
            else:
                first = len(idx) - 2
            idx = idx[first:]
        off = Vector((b['seed'] * 7.13 + 3.1, b['seed'] * 3.71 - 1.7, b['seed'] * 1.37 + 0.4))
        want = Vector(seam(b))
        a0 = _ring_dir(T[idx[0]], N[idx[0]], B[idx[0]], want)
        ring_pts, ring_uv = [], []
        vcoord = 0.0
        tip_pt = tip_uv = None
        prev = None
        for m_, i in enumerate(idx):
            p, r = pp[i], rr[i]
            w = rho(b, p, kind)
            if prev is not None:
                ds = S[i] - S[prev]
                vcoord += ds * 0.5 * (w + rho(b, pp[prev], kind))
            prev = i
            if tip and i == n - 1:
                tip_pt = p.copy(); tip_uv = (0.0, vcoord)
                continue
            # 이음매 방향을 고리마다 다시 맞춘다 (가지가 굽어도 이음매가 늘 want 쪽: 뿌리 아래·가지 위·줄기 뒤).
            # 가지가 want 와 거의 나란하면(수직 뿌리 시작부) 앞 고리 값을 이어 쓴다. 한 번에 크게 돌지 않게 30도까지만
            wv = want - T[i] * want.dot(T[i])
            if wv.length > 0.35:
                an = _ring_dir(T[i], N[i], B[i], want)
                da = (an - a0 + math.pi) % (2 * math.pi) - math.pi
                a0 += max(-R(30), min(R(30), da))
            ring = []
            for k in range(sides):
                a = 2 * math.pi * k / sides + a0
                f = 1.0
                if b['lobes']:
                    f += b['lobe_amp'] * math.sin(b['lobes'] * a + b['twist'] * S[i] + 0.0)
                if bumps:
                    q = Vector((math.cos(a) * 0.9, math.sin(a) * 0.9, S[i] / max(r * 3.0, 0.03))) + off
                    f += bumps * mnoise.noise(q)
                d = N[i] * (math.cos(a) * b['ell']) + B[i] * math.sin(a)
                ring.append(p + d * (r * f))
            circ = 2 * math.pi * r * w
            ring_pts.append(ring)
            ring_uv.append([((k / sides - 0.5) * circ, vcoord) for k in range(sides + 1)])
        # 땅속 고리 버리기 (줄기 아래·뿌리 끝): 처음/끝에서 모든 점이 z_cut 아래인 고리
        while len(ring_pts) > 2 and all(v.z < z_cut for v in ring_pts[0]) and all(v.z < z_cut for v in ring_pts[1]):
            ring_pts.pop(0); ring_uv.pop(0)
        cut_end = False
        while len(ring_pts) > 2 and all(v.z < z_cut for v in ring_pts[-1]) and all(v.z < z_cut for v in ring_pts[-2]):
            ring_pts.pop(); ring_uv.pop(); cut_end = True
        if cut_end:
            tip_pt = None
        if len(ring_pts) < 2 and tip_pt is None:
            continue
        if len(ring_pts) < 1:
            continue
        emit(kind, ring_pts, ring_uv, tip_pt, tip_uv, cap_end=(tip_pt is None and not cut_end and kind == 'A'),
             grp=groups.get(pi, groups.get('B', 0)) if kind == 'A' else groups.get('B', 0))
        if kind == 'A':
            nA += 1
        else:
            nB += 1
    out = []
    for kind in ('A', 'B'):
        V, F, U, G = accs[kind]
        if not F:
            out.append(None)
            continue
        me = bpy.data.meshes.new(name + "_low" + kind)
        me.from_pydata([tuple(v) for v in V], [], F)
        me.update(calc_edges=True)
        uvl = me.uv_layers.new(name="UVMap")
        for poly, fu in zip(me.polygons, U):
            for li, uv in zip(poly.loop_indices, fu):
                uvl.data[li].uv = uv
        me.attributes.new('bgrp', 'INT', 'FACE').data.foreach_set('value', G)
        o = bpy.data.objects.new(name + "_low" + kind, me)
        link(o)
        for poly in me.polygons:
            poly.use_smooth = True
        out.append(o)
    print("TREELOW", name, "A tubes", nA, "B tubes", nB, "tris A", tri_count(out[0]) if out[0] else 0, "B", tri_count(out[1]) if out[1] else 0)
    return out[0], out[1]


def tree_rho(b, p, kind, base=1.0, top=0.45, z0=1.2, z1=3.5, root=(0.6, 0.32), root_r=(0.6, 1.4), d1=0.42, d2=0.32, d3=0.26, twig=0.22):
    """(v3b) 나무 텍셀 배율: 줄기 밑동(사람 눈높이까지) 1.0 → 위로 갈수록, 뿌리(줄기 가까이 → 끝), 굵은 가지·잔가지 순으로 낮게.
    뿌리는 겉넓이가 줄기만큼 커서(죽은 나무 a: 8.8 m²) 그대로 두면 텍스처의 40% 를 먹는다"""
    if kind == 'B':
        return twig
    d = b['depth']
    if d == 0:
        t = min(max((p.z - z0) / (z1 - z0), 0.0), 1.0)
        return base + (top - base) * t
    if d >= 9:
        r = math.hypot(p.x, p.y)
        t = min(max((r - root_r[0]) / (root_r[1] - root_r[0]), 0.0), 1.0)
        return root[0] + (root[1] - root[0]) * t
    return d1 if d == 1 else (d2 if d == 2 else d3)


def tree_seam(b):
    """이음매 방향: 줄기는 뒤(+Y), 뿌리는 아래, 가지는 위 (땅에서 올려다보는 쪽의 반대)"""
    d = b['depth']
    return (0, 1, 0) if d == 0 else ((0, 0, -1) if d >= 9 else (0, 0, 1))


def tree_build(name, tree, split_r, voxel, layers_a, layers_b, mat, low_a, size, extr, extras=(), guide_step=0.05,
               lod2=None, low_sides=5, extra_highs=(), extra_lows=(), post_a=None, r_cut=0.03, mat_b=None,
               low_step=(0.08, 0.3), uv_angle=66, extra_a=None, ivy_starts=(), fin=None, low_mode='remesh', rho=None):
    """뼈대 → 굵은 부분 리메시·조각, 잔가지 관 → 굽기. post_a(굵은 부분): 리메시 뒤 구멍 파기 등.
    fin: kit.finish 에 더 넘길 v3 인자 (cage, pack, margin=0 …). 없으면 예전과 같다.
    저폴리 굵은 부분은 껍질 조각 전의 매끈한 사본에서 줄인다 (껍질은 노멀맵으로).
    (v3b) low_mode='tube': 저폴리를 가지마다 관 하나로 다시 찍고 원통으로 편다 (tree_low_uv, 이음매 하나·섬 = 가지 하나).
      리메시 저폴리 + smart_project 는 섬이 수천 개로 쪼개져 텍셀이 낮고 껍질 결이 섬마다 끊겼다. rho: 텍셀 배율 (tree_rho)
      원본도 굵은 가지마다 따로 깎고(가지 하나만의 결 뼈대), 서로 닿지 않는 가지끼리 묶어 무리마다 따로 굽는다 (bake_groups)
      → 원본이 합쳐진 가지 이음매에서 생기던 극단 법선·검은 점이 없다. post_a·extra_a 는 이 방식에서 쓰지 않는다"""
    if low_mode == 'tube':
        return _tree_build_tube(name, tree, split_r, voxel, layers_a, layers_b, mat, size, extr, extras, guide_step, lod2,
                                r_cut, mat_b, low_step, extra_highs, extra_lows, ivy_starts, fin, rho or tree_rho)
    guide = tree.guide(guide_step)
    A, Bh = tree.meshes(split_r, hi=True, r_cut=r_cut, low_step=low_step)
    if extra_a is not None:
        A.add(extra_a.v, extra_a.f)
    ha = A.obj(name + "_hA")
    remesh(ha, voxel)
    if post_a is not None:
        post_a(ha)
        remesh(ha, voxel)
    base = copy(ha)
    surface(ha, layers_a, seed=BARK_SEEDS[0], guide=guide)
    set_mat(ha, mat)
    highs = [ha]
    hb = Bh.obj(name + "_hB")
    if hb is not None:
        surface(hb, layers_b, seed=BARK_SEEDS[1], guide=guide)
        set_mat(hb, mat_b or mat)
        highs.append(hb)
    delete(guide)
    la = low_from(base, low_a)
    delete(base)
    lows = [la]
    _, Bl = tree.meshes(split_r, hi=False, low_sides=low_sides, r_cut=r_cut, low_step=low_step)
    lb = Bl.obj(name + "_lB")
    if lb is not None:
        lows.append(lb)
    extras = list(extras)
    for p, sd, ln in ivy_starts:                  # 밑동을 타고 오르는 덩굴 (버려진 곳에만 조금)
        extras += ivy_light(la, p, sd, ln, leaf=0.06, gravity=-0.2, adhesion=0.9)
    print("TREE", name, "branches", len(tree.br), "lowA", tri_count(la), "lowB", tri_count(lb) if lb else 0)
    return finish(name, highs + list(extra_highs), lows + list(extra_lows), extras=extras, size=size, extr=extr, lod2=lod2,
                  uv_angle=uv_angle, **(fin or {}))


MERGE_ROOTS = False


def _base_piece(b):
    """MERGE_ROOTS 이면 줄기와 뿌리를 한 덩어리 원본(리메시로 합침)으로 함께 굽는다. 기본은 끔: 시험해 보니 줄기 저폴리 위를
    뿌리 원본이 덮어 광선이 비스듬히 스쳐 steep 이 1.6% → 11.8% 로 늘었다. 가지·뿌리는 따로 깎고 따로 굽는다"""
    return MERGE_ROOTS and (b['depth'] == 0 or b['depth'] >= 9)


def _tree_groups(tree, split_r, r_cut):
    """굵은 조각(A)을 서로 닿지 않는 무리로 나눈다 (부모·자식이거나 축 사이가 두 반지름 + 5cm 안이면 같은 무리 금지).
    줄기·뿌리 조각은 모두 무리 0 (한 덩어리 원본)"""
    from mathutils.kdtree import KDTree
    info = []
    for pi, (pts, rads, kind, b, s0, tip) in enumerate(tree.pieces(split_r, r_cut)):
        if kind != 'A':
            continue
        pp, rr = respace(pts, rads, 0.05)
        kd = KDTree(len(pp))
        for i, q in enumerate(pp):
            kd.insert(q, i)
        kd.balance()
        info.append((pi, b, pp, rr, kd))
    clash = {x[0]: set() for x in info}
    for i, (pa, ba, ppa, rra, kda) in enumerate(info):
        for pb, bb, ppb, rrb, kdb in info[i + 1:]:
            hit = ba.get('parent') is bb or bb.get('parent') is ba
            if not hit:
                for q, r in zip(ppb, rrb):
                    c, ci, d = kda.find(q)
                    if d < r + rra[ci] + 0.05:
                        hit = True
                        break
            if hit:
                clash[pa].add(pb); clash[pb].add(pa)
    base = {x[0] for x in info if _base_piece(x[1])}
    grp = {pi: 0 for pi in base}
    for pi, *_ in info:
        if pi in base:
            continue
        used = {grp[o] for o in clash[pi] if o in grp}
        if clash[pi] & base:
            used.add(0)
        g = 0
        while g in used:
            g += 1
        grp[pi] = g
    ng = max(grp.values()) + 1 if grp else 0
    grp['B'] = ng
    return grp, ng + 1


def _tree_build_tube(name, tree, split_r, voxel, layers_a, layers_b, mat, size, extr, extras, guide_step, lod2,
                     r_cut, mat_b, low_step, extra_highs, extra_lows, ivy_starts, fin, rho):
    """tree_build(low_mode='tube') 본체: 가지마다 원본·저폴리 관, 무리별 굽기"""
    grp, ng = _tree_groups(tree, split_r, r_cut)
    pieces = list(tree.pieces(split_r, r_cut))
    highsA, Bh = tree.piece_meshes(split_r, r_cut, low_step)
    bake_groups = [[] for _ in range(ng)]
    highs = []
    base_acc, base_ids = Acc(), set()
    for pi, b, acc in highsA:
        if _base_piece(b):                   # 줄기 + 뿌리: 한 덩어리로 리메시 (만나는 곳이 매끈하게)
            base_acc.add(acc.v, acc.f)
            base_ids.add(id(b))
            continue
        h = acc.obj("%s_hA%d" % (name, pi))
        remesh(h, voxel)
        gd = tree.guide_for(b, guide_step)
        surface(h, layers_a, seed=BARK_SEEDS[0], guide=gd)
        delete(gd)
        set_mat(h, mat)
        bake_groups[grp[pi]].append(h)
        highs.append(h)
    if base_acc.f:
        h = base_acc.obj("%s_hBase" % name)
        remesh(h, voxel)
        gd = tree.guide(guide_step, only=base_ids)
        surface(h, layers_a, seed=BARK_SEEDS[0], guide=gd)
        delete(gd)
        set_mat(h, mat)
        bake_groups[0].append(h)
        highs.append(h)
    hb = Bh.obj(name + "_hB")
    if hb is not None:
        gd = tree.guide(guide_step)
        surface(hb, layers_b, seed=BARK_SEEDS[1], guide=gd)
        delete(gd)
        set_mat(hb, mat_b or mat)
        bake_groups[grp['B']].append(hb)
        highs.append(hb)
    la, lb = tree_low_uv(tree, split_r, r_cut, low_step, rho, tree_seam, name=name, groups=grp)
    lows = [x for x in (la, lb) if x is not None]
    extras = list(extras)
    for p, sd, ln in ivy_starts:
        extras += ivy_light(la, p, sd, ln, leaf=0.06, gravity=-0.2, adhesion=0.9)
    trunk_pi = next((pi for pi, (pts, rads, kind, b, s0, tip) in enumerate(pieces) if kind == 'A' and b['depth'] == 0), None)

    def probe(low, size_):
        # 줄기 밑동(높이 1.5 m 아래, 줄기 조각) 텍셀
        me = low.data
        at = me.attributes.get('bgrp')
        if at is None or trunk_pi is None:
            return
        g = grp[trunk_pi]
        uv = me.uv_layers.active.data
        a2 = a3 = 0.0
        for p in me.polygons:
            if at.data[p.index].value != g or p.center.z > 1.5:
                continue
            pts = [uv[i].uv for i in p.loop_indices]
            ss = 0.0
            for i in range(len(pts)):
                x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % len(pts)]
                ss += x0 * y1 - x1 * y0
            a2 += abs(ss) * 0.5; a3 += p.area
        print("TEXEL_TRUNK", name, "base px/m", round(size_ * math.sqrt(a2 / max(a3, 1e-9))), "(무리 %d, 같은 무리 다른 가지 포함)" % g)

    print("TREE", name, "branches", len(tree.br), "lowA", tri_count(la) if la else 0, "lowB", tri_count(lb) if lb else 0,
          "bake_groups", ng, "highs", len(highs))
    fin = dict(fin or {}); fin['uv'] = 'keep'; fin.setdefault('pack', True)
    return finish(name, highs + list(extra_highs), lows + list(extra_lows), extras=extras, size=size, extr=extr, lod2=lod2,
                  bake_groups=bake_groups if not extra_highs else None, probe=probe, **fin)


def bcut(o, cutters, solver='EXACT'):
    """불리언 빼기 (solver 를 고를 수 있는 kit.cut)"""
    col = bpy.data.collections.new("cutters")
    kit.sc.collection.children.link(col)
    for c in cutters:
        for uc in list(c.users_collection):
            uc.objects.unlink(c)
        col.objects.link(c)
    m = o.modifiers.new('bool', 'BOOLEAN'); m.operation = 'DIFFERENCE'; m.operand_type = 'COLLECTION'
    m.collection = col; m.solver = solver
    act(o)
    bpy.ops.object.modifier_apply(modifier=m.name)
    for c in list(col.objects):
        bpy.data.objects.remove(c, do_unlink=True)
    bpy.data.collections.remove(col)
    return o


def jagged_cutter(origin, axis, radius, rng, slope=0.25, rough=0.05, shards=9, shard_h=(0.08, 0.32), res=64, far=3.0,
                  shard_w=(0.02, 0.05)):
    """부러진 나무 끝 커터: origin 에서 axis 방향 바깥을 지운다. 경계면은 비스듬하고 거칠며,
    가늘고 뾰족한 나뭇결 조각(shard)이 바깥으로 남는다"""
    ax = Vector(axis).normalized()
    U = ax.orthogonal().normalized(); V = ax.cross(U)
    ext = radius * 1.4
    shs = []
    for _ in range(shards):
        a = rng.uniform(0, 6.283); rr = radius * rng.uniform(0.25, 0.95)
        c = Vector((math.cos(a) * rr, math.sin(a) * rr))
        tdir = Vector((-math.sin(a), math.cos(a))) if rng.random() < 0.6 else Vector((math.cos(a), math.sin(a)))
        shs.append((c, tdir, rng.uniform(*shard_w), rng.uniform(radius * 0.25, radius * 0.7), rng.uniform(*shard_h)))
    off = Vector((rng.uniform(-9, 9), rng.uniform(-9, 9), rng.uniform(-9, 9)))
    sd = Vector((math.cos(rng.uniform(0, 6.28)), math.sin(rng.uniform(0, 6.28))))

    def h(u, v):
        q = Vector((u, v))
        z = slope * q.dot(sd) + rough * mnoise.noise(Vector((u * 5, v * 5, 0)) + off) \
            + rough * 0.5 * mnoise.noise(Vector((u * 17, v * 17, 3)) + off)
        best = 0.0
        for c, t, w, l, hh in shs:
            d = q - c
            da = abs(d.dot(t)); dp = abs(d.x * t.y - d.y * t.x)
            if da < l and dp < w:
                best = max(best, hh * (1 - dp / w) ** 0.7 * (1 - da / l) ** 1.3)
        return z + best

    verts, faces = [], []
    n = res
    for j in range(n + 1):
        for i in range(n + 1):
            u = -ext + 2 * ext * i / n; v = -ext + 2 * ext * j / n
            verts.append(Vector(origin) + ax * h(u, v) + U * u + V * v)
    for j in range(n + 1):
        for i in range(n + 1):
            u = -ext + 2 * ext * i / n; v = -ext + 2 * ext * j / n
            verts.append(Vector(origin) + ax * far + U * u + V * v)
    k = (n + 1) * (n + 1)
    idx = lambda i, j: j * (n + 1) + i
    for j in range(n):
        for i in range(n):
            faces.append((idx(i, j), idx(i, j + 1), idx(i + 1, j + 1), idx(i + 1, j)))
            faces.append((k + idx(i, j), k + idx(i + 1, j), k + idx(i + 1, j + 1), k + idx(i, j + 1)))
    ring = [idx(i, 0) for i in range(n)] + [idx(n, j) for j in range(n)] + [idx(i, n) for i in range(n, 0, -1)] + \
           [idx(0, j) for j in range(n, 0, -1)]
    for a, b in zip(ring, ring[1:] + ring[:1]):
        faces.append((a, b, k + b, k + a))
    return mesh_from("jag", verts, faces)


def wood_mix(mat, axis_pt, axis_dir, mask_fn, ring_freq=55.0, color=(0.36, 0.3, 0.28), dark=(0.12, 0.08, 0.08)):
    """드러난 속나무: 나이테 색. mask_fn(nt, P, N) → 0~1 소켓 (어디에 칠할지)"""
    nt = mat.node_tree
    b, col = _final(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    # 축에서의 거리 → 나이테
    sub = nt.nodes.new('ShaderNodeVectorMath'); sub.operation = 'SUBTRACT'
    nt.links.new(P, sub.inputs[0]); sub.inputs[1].default_value = axis_pt
    ax = Vector(axis_dir).normalized()
    dt = nt.nodes.new('ShaderNodeVectorMath'); dt.operation = 'DOT_PRODUCT'
    nt.links.new(sub.outputs[0], dt.inputs[0]); dt.inputs[1].default_value = ax
    pr = nt.nodes.new('ShaderNodeVectorMath'); pr.operation = 'SCALE'
    pr.inputs[0].default_value = ax; nt.links.new(dt.outputs['Value'], pr.inputs['Scale'])
    perp = nt.nodes.new('ShaderNodeVectorMath'); perp.operation = 'SUBTRACT'
    nt.links.new(sub.outputs[0], perp.inputs[0]); nt.links.new(pr.outputs[0], perp.inputs[1])
    ln = nt.nodes.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'; nt.links.new(perp.outputs[0], ln.inputs[0])
    wob = kit._mul(nt, kit._noise(nt, P, 6, 3), 0.025)
    rr = kit._mul(nt, ln.outputs['Value'], wob, 'ADD')
    rings = kit._mul(nt, kit._mul(nt, rr, ring_freq), 1.0, 'SINE')
    rc = kit._ramp(nt, rings, -0.2, W(dark), 0.9, W(color))
    rc = kit._mix(nt, 'MULTIPLY', 0.5, rc, kit._ramp(nt, kit._noise(nt, P, 3, 4), 0.35, W((0.55, 0.5, 0.6)), 0.7, W((1, 1, 1))))
    m = mask_fn(nt, P, geo.outputs['Normal'])
    out = kit._mix(nt, 'MIX', m, col, rc)
    nt.links.new(out, b.inputs['Base Color'])
    return mat


def mask_axis_end(axis, x0, nk=0.55):
    """축 방향 끝면(법선이 축과 나란함) 또는 축 좌표가 x0 너머인 곳"""
    ax = Vector(axis).normalized()

    def fn(nt, P, Nrm):
        d = nt.nodes.new('ShaderNodeVectorMath'); d.operation = 'DOT_PRODUCT'
        nt.links.new(Nrm, d.inputs[0]); d.inputs[1].default_value = ax
        a = kit._mul(nt, d.outputs['Value'], 0.0, 'ABSOLUTE')
        m1 = kit._ramp(nt, a, nk, W((0, 0, 0)), nk + 0.15, W((1, 1, 1)))
        dp = nt.nodes.new('ShaderNodeVectorMath'); dp.operation = 'DOT_PRODUCT'
        nt.links.new(P, dp.inputs[0]); dp.inputs[1].default_value = ax
        m2 = _unit(nt, kit._mul(nt, dp.outputs['Value'], 0.0, 'ABSOLUTE'), x0, x0 + 0.04)
        return kit._mul(nt, m1, m2, 'MAXIMUM') if x0 > 0 else m1
    return fn


def lathe_mesh(profile, seg, M):
    """(반지름, 높이) 윤곽을 Z 축으로 돌린 메쉬 정점·면 (M: 변환 행렬). 첫·끝 점 반지름 0 이면 한 점으로"""
    verts, faces, rows = [], [], []
    for r, z in profile:
        if r < 1e-5:
            verts.append(M @ Vector((0, 0, z))); rows.append([len(verts) - 1])
        else:
            row = []
            for k in range(seg):
                a = 2 * math.pi * k / seg
                verts.append(M @ Vector((math.cos(a) * r, math.sin(a) * r, z))); row.append(len(verts) - 1)
            rows.append(row)
    for a, b in zip(rows, rows[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for k in range(seg):
                faces.append((a[0], b[k], b[(k + 1) % seg]))
        elif len(b) == 1:
            for k in range(seg):
                faces.append((a[k], b[0], a[(k + 1) % seg]))
        else:
            for k in range(seg):
                faces.append((a[k], b[k], b[(k + 1) % seg], a[(k + 1) % seg]))
    return verts, faces


def toadstool(acc_stem, acc_cap, rng, p, h, r, nrm=(0, 0, 1), seg=12, lean=0.15, gill=None):
    """독버섯 하나: 휜 대 + 둥근 갓. acc_*: (Acc) 굽기 원본 또는 저폴리. gill: 갓 아래 발광 링 Acc"""
    up = Vector(nrm).normalized().lerp(Vector((0, 0, 1)), 0.5).normalized()
    side = up.orthogonal().normalized()
    rot = Matrix.Rotation(rng.uniform(0, 6.28), 3, up)
    side = rot @ side
    pts = []
    for i in range(5):
        t = i / 4
        pts.append(Vector(p) - up * 0.01 + up * (h * t) + side * (lean * h * t * t))
    rs = [r * 0.28, r * 0.22, r * 0.2, r * 0.19, r * 0.18]
    v, f = tube(pts, rs, max(5, seg // 2), cap=True, tip=False)
    acc_stem.add(v, f)
    top = pts[-1]
    tdir = (pts[-1] - pts[-2]).normalized().lerp(up, 0.5).normalized()
    M = Matrix.Translation(top) @ tdir.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    prof = [(0.0, -0.05 * r), (r * 0.3, -0.12 * r), (r * 0.95, -0.15 * r), (r * 1.02, 0.0), (r * 0.92, 0.32 * r),
            (r * 0.62, 0.58 * r), (r * 0.28, 0.72 * r), (0.0, 0.75 * r)]
    v, f = lathe_mesh(prof, seg, M)
    acc_cap.add(v, f)
    if gill is not None:
        prof2 = [(r * 0.25, -0.13 * r), (r * 0.9, -0.16 * r), (r * 0.9, -0.12 * r), (r * 0.25, -0.09 * r)]
        v, f = lathe_mesh(prof2, seg, M)
        gill.add(v, f)
    return top


def bracket(acc, rng, p, nrm, r, seg=12):
    """선반버섯: 표면에서 바깥으로 튀어나온 반달 판"""
    out = Vector((nrm[0], nrm[1], 0))
    if out.length < 1e-3:
        out = Vector((1, 0, 0))
    out.normalize()
    side = Vector((-out.y, out.x, 0))
    M = Matrix((side, out, Vector((0, 0, 1)))).transposed().to_4x4()
    M = Matrix.Translation(Vector(p) - out * r * 0.25) @ M
    verts, faces, rows = [], [], []
    prof = [(0.0, 0.0), (0.55, 0.06), (0.9, 0.05), (1.0, 0.0), (0.92, -0.05), (0.6, -0.07), (0.0, -0.03)]
    for rr, z in prof:
        row = []
        for k in range(seg + 1):
            a = math.pi * k / seg
            wob = 1 + 0.08 * math.sin(a * 5 + rng.uniform(0, 3))
            verts.append(M @ Vector((math.cos(a) * rr * r * wob, math.sin(a) * rr * r * wob * 0.9, z * r)))
            row.append(len(verts) - 1)
        rows.append(row)
    for a, b in zip(rows, rows[1:]):
        for k in range(seg):
            faces.append((a[k], b[k], b[k + 1], a[k + 1]))
    # 벽에 붙는 면 닫기
    for a, b in zip(rows, rows[1:]):
        pass
    faces.append(tuple(r[0] for r in rows))
    faces.append(tuple(r[-1] for r in reversed(rows)))
    acc.add(verts, faces)


def shroom_mats():
    cap = paint("toad_cap", ((0.06, 0.012, 0.04), (0.24, 0.035, 0.11), (0.5, 0.2, 0.3)), moss=0.0, dirt=0.0, streaks=0.0,
                cracks=0.0, ao=0.03, edge=0.4, hue_var=0.2)
    # 갓의 흰 점
    nt = cap.node_tree
    b, col = _final(cap)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    vo = nt.nodes.new('ShaderNodeTexVoronoi'); vo.inputs['Scale'].default_value = 140
    nt.links.new(tc.outputs['Object'], vo.inputs['Vector'])
    spot = kit._ramp(nt, vo.outputs['Distance'], 0.14, W((1, 1, 1)), 0.2, W((0, 0, 0)))
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(geo.outputs['Normal'], sep.inputs[0])
    upm = kit._ramp(nt, sep.outputs['Z'], 0.1, W((0, 0, 0)), 0.4, W((1, 1, 1)))
    gill = kit._ramp(nt, sep.outputs['Z'], -0.6, W((1, 1, 1)), -0.2, W((0, 0, 0)))
    out = kit._mix(nt, 'MIX', kit._mul(nt, spot, upm), col, W((0.6, 0.55, 0.5)))
    out = kit._mix(nt, 'MIX', gill, out, W((0.42, 0.36, 0.3)))
    nt.links.new(out, b.inputs['Base Color'])
    stem = paint("toad_stem", 'bone', moss=0.0, dirt=0.4, streaks=0.0, cracks=0.0, ao=0.03, edge=0.3)
    brk = paint("bracket", ((0.06, 0.04, 0.05), (0.3, 0.22, 0.2), (0.62, 0.55, 0.48)), moss=0.25, dirt=0.0, streaks=0.0,
                cracks=0.0, ao=0.05, edge=0.8, hue_var=0.3)
    return cap, stem, brk


# kit.surface 의 씨앗별 좌표 이동이 거의 0 인 씨앗 (bark 층의 어긋남을 줄인다, 위 Tree.guide 설명)
BARK_SEEDS = (83900, 105652, 7659, 174741, 121176)


def bark_layers(k=1.0, depth=1.0):
    """껍질: 가지 방향으로 길게 갈라진 깊은 골 + 잔 골"""
    return [{'t': 'lumps', 'scale': 1.2 / k, 'amp': 0.02 * k},
            {'t': 'bark', 'scale': 3.4 / k, 'width': 0.12, 'depth': 0.04 * k * depth, 'stretch': 0.2},
            {'t': 'bark', 'scale': 8.0 / k, 'width': 0.1, 'depth': 0.016 * k * depth, 'stretch': 0.26},
            {'t': 'grain', 'scale': 40.0 / k, 'amp': 0.0015 * k}]


def twig_layers():
    return [{'t': 'lumps', 'scale': 5.0, 'amp': 0.004},
            {'t': 'bark', 'scale': 18.0, 'width': 0.12, 'depth': 0.004, 'stretch': 0.15},
            {'t': 'grain', 'scale': 90.0, 'amp': 0.0006}]


def hang_moss_on(tree, cards, rng, n, depths=(1, 2), r_min=0.03, length=(0.35, 1.0), width=(0.16, 0.3), t=(0.2, 0.85)):
    cands = [b for b in tree.br if b['depth'] in depths and b['r0'] >= r_min]
    placed = 0
    for _ in range(n * 6):
        if placed >= n or not cands:
            break
        b = rng.choice(cands)
        p, r, T, N, B = tree.at(b, rng.uniform(*t))
        if abs(T.z) > 0.8:          # 거의 수직인 곳에는 걸리지 않는다
            continue
        moss_hang(cards, rng, p - Vector((0, 0, r * 0.8)), rng.uniform(*length), rng.uniform(*width), 2, along=T)
        placed += 1
    return placed


def dead_tree_a():
    """뒤틀린 죽은 나무 ~7m: 비틀린 줄기에서 팔처럼 뻗은 큰 가지 넷, 끝은 발톱처럼 가늘고 날카롭다. 몇 곳에 늘어진 이끼.
    v3: BARK3(깊은 골 사이 판을 평평하게 깎은 껍질), paint3 껍질(위 밝고 아래·골 보라, 판 모서리 밝게), cage 굽기 2048"""
    rng = random.Random(1234)
    tr = Tree(rng)
    trunk = path_grow(rng, (0, 0, -0.35), (0.06, -0.04, 1), 6.9, 0.45, 0.14, up=0.04, kink=0.3)
    tk = tr.branch(trunk, 0.38, 0.004, 1.0, depth=0, lobes=5, lobe_amp=0.14, twist=0.6, bumps=0.09, flare=(0.6, 1.6))
    trunk_roots(tr, rng, 6, 0.38, (0.7, 1.1), (1.0, 1.5), r_k=(0.5, 0.65), dip=0.3)
    a0 = rng.uniform(0, 360)
    for i, (t, el, ln) in enumerate(((0.38, 24, 3.5), (0.49, 33, 3.3), (0.6, 28, 3.1), (0.71, 42, 2.7))):
        limb(tr, tk, t, a0 + i * 97 + rng.uniform(-18, 18), el, ln, r_k=0.78, taper=1.35, gnarl=0.24, up=0.07)
    tr.grow(tk, [dict(CLAW_LEVELS[0], kids=(2, 3), t=(0.86, 0.97), len=(0.4, 0.6), r=(0.6, 0.8))] + CLAW_LEVELS[1:])
    cards = Cards()
    hang_moss_on(tr, cards, rng, 6, length=(0.4, 0.95), width=(0.16, 0.26))
    # v3b: 껍질판 사이 골이 어둡고(좁은 AO) 판 가장자리는 밝게(베벨), 껍질이 벗겨진 맨나무는 작고 경계가 또렷한 조각,
    # 이끼·지의류도 작게 (v3 의 회색 솜뭉치 얼룩 blotch(0.9, 0.5~0.6) 은 뺐다)
    # i8: 골 그늘을 덜 검게(가장자리에서 검은 구멍처럼 보였다), 판 모서리 빛을 줄여(뿌리 판이 수정 조각처럼 보였다),
    # 밑동 흙물·이끼를 높이 올려 줄기와 뿌리 퍼짐이 만나는 고리를 덮는다
    m = paint3("dead_tree_a", BARK_GREY, h=2.5, k=1.0, moss=0.3, moss_color=MOSS_DEAD, moss_patch=5.5, moss_low=0.5, moss_low_h=0.95,
               piece_var=0.0, hue_var=0.2, edge=0.0, edge_w=0.012, edge_gain=1.0, cavity=0.55, cavity_s=0.2, ao=0.16, strokes=0.15,
               tooling=0.0, streaks=0.2, stains=0.25, dirt=0.6, dirt_h=0.85, light=1.1, lichen=0.0, grain=0.25,
               contrast=0.2, pivot=0.06, gain=0.85)       # gain: 게임 시점 6 m 밝기가 이전보다 14% 밝았다 → ±10%
    # v3c: 골을 따라 흰 보풀 줄(베벨 노드로 찾은 판 모서리 빛 edge 0.65 — 표본 8 개라 들쭉날쭉) 과 검은 점(좁은 AO 표본 잡음이
    # 골 입술에 찍힘)이 생겼다 → 모서리 빛 끄고, 좁은 AO 그늘은 약하게(cavity_s 0.2, 골은 넓은 AO 로 어둡다), 지의류 반점도 뺐다
    blotch(m, (0.2, 0.19, 0.22), 2.6, 0.45, 0.62, 0.63)   # 껍질이 벗겨진 맨나무 (작고 또렷하게, 흰 물감 같지 않게 어둡게)
    grad_dark(m, 0.0, 1.0, 0.45)
    # 잔가지는 밝게 (어두운 하늘에 실루엣이 읽히게)
    mb = paint3("dead_tree_a_tw", 'bark_pale', h=6.6, k=0.5, moss=0.1, moss_color=MOSS_DEAD, piece_var=0.0, edge=0.3,
                cavity=0.5, ao=0.1, strokes=0.2, tooling=0.0, streaks=0.0, stains=0.0, dirt=0.0, light=0.8)
    # v3c despeck_n: 깊은 골 바닥의 1~2 화소 포화 점·줄(노멀맵)을 중앙값으로 — 렌더에서 골을 따라 생기던 흰 보풀 줄·검은 점
    co, fi = BARK3(1.0, depth=0.8)         # 골 벽이 조금 덜 가파르게 (depth 1.0: steep 3.0% → 0.85: 2.4%)
    return tree_build("dead_tree_a", tr, 0.045, 0.006, co + fi, twig_layers(), m, 5000, 2048, 0.06,
                      extras=[cards.obj("moss")], mat_b=mb, low_mode='tube', rho=tree_rho,
                      fin=dict(cage=0.006, cage_reach=0.06, samples=8, margin=0, uv_margin=0.002, despeck=True, despeck_n=0.18))


def arch_root(rng, ang, r_trunk, reach, height):
    """땅 위로 들린 뿌리 (기운 나무의 반대쪽): 줄기에서 나와 아치를 그리며 땅으로 들어간다"""
    c, s = math.cos(ang), math.sin(ang)
    side = Vector((-s, c, 0))
    pts = []
    for i, (rk, zk) in enumerate(((0.2, 0.55), (0.8, 0.5), (1.3, 0.75), (1.8, 0.8), (2.4, 0.45), (3.0, 0.0), (3.4, -0.6))):
        rr = r_trunk * rk if i < 2 else r_trunk + (reach - r_trunk) * (rk - 1.0) / 2.4
        z = height * zk if i >= 2 else r_trunk * zk * 1.6
        pts.append(Vector((c * rr, s * rr, z)) + side * (rng.uniform(-0.12, 0.12) * rr if i > 1 else 0.0))
    return pts


def dead_tree_b():
    """한쪽(+X)으로 기운 죽은 나무 ~5m: 기운 반대쪽 뿌리가 땅에서 들렸고, 가지는 위로 휘어 오른다"""
    rng = random.Random(4321)
    tr = Tree(rng)
    trunk = path_grow(rng, (0, 0, -0.3), (0.66, 0.1, 1), 5.4, 0.42, 0.12, up=0.1, kink=0.25)
    tk = tr.branch(trunk, 0.27, 0.004, 1.0, depth=0, lobes=4, lobe_amp=0.14, twist=0.7, bumps=0.09, flare=(0.45, 1.55))
    trunk_roots(tr, rng, 4, 0.27, (0.45, 0.8), (0.9, 1.4), r_k=(0.5, 0.62), dip=0.3, ang0=R(-40))
    for a in (R(150), R(195), R(240)):
        pts = arch_root(rng, a + rng.uniform(-0.15, 0.15), 0.27, rng.uniform(1.3, 1.8), rng.uniform(0.24, 0.36))
        ax = axis_at(tk, pts[0].z); ax.z = 0
        pts = [p + ax * (1.0 if i < 2 else 0.4) for i, p in enumerate(pts)]
        tr.branch(pts, 0.11, 0.02, 0.6, depth=9, lobes=2, lobe_amp=0.1, bumps=0.08, ell=0.8, parent=tk)
    a0 = rng.uniform(0, 360)
    for i, (t, el, ln) in enumerate(((0.42, 52, 2.4), (0.58, 38, 2.6), (0.72, 60, 2.0))):
        limb(tr, tk, t, a0 + i * 125 + rng.uniform(-20, 20), el, ln, r_k=0.75, taper=1.35, gnarl=0.24, up=0.12)
    tr.grow(tk, [dict(CLAW_LEVELS[0], kids=(2, 3), t=(0.82, 0.96), len=(0.4, 0.6), r=(0.6, 0.8), up=0.12)] + CLAW_LEVELS[1:])
    cards = Cards()
    hang_moss_on(tr, cards, rng, 3, length=(0.35, 0.7), width=(0.14, 0.22))
    m = bark_paint("dead_tree_b", BARK_DEAD, moss=0.45, pale=0.55, pale_scale=1.1)
    grad_dark(m, 0.0, 1.0, 0.55)
    mb = bark_paint("dead_tree_b_tw", BARK_DEAD, moss=0.15, pale=0.3, edge=0.3)
    return tree_build("dead_tree_b", tr, 0.04, 0.008, bark_layers(0.9), twig_layers(), m, 4200, 1024, 0.06,
                      extras=[cards.obj("moss")], mat_b=mb)


def burl(acc, rng, center, r, nrm):
    """줄기에 붙은 혹(옹이): 법선 쪽으로 납작하게 부푼 울퉁불퉁한 덩어리"""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    n = Vector(nrm).normalized()
    q = n.to_track_quat('Z', 'Y')
    off = Vector((rng.uniform(-9, 9), rng.uniform(-9, 9), rng.uniform(-9, 9)))
    verts = []
    for v in bm.verts:
        p = Vector(v.co)
        k = 1 + 0.25 * mnoise.noise(p * 1.8 + off)
        p = Vector((p.x * r * k, p.y * r * k, p.z * r * 0.6 * k))
        verts.append(Vector(center) + q @ p)
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    acc.add(verts, faces)


def hollow(o, rng, center, axis_up, radius, height, open_dir, open_w, open_h, solver='FAST'):
    """줄기 속을 파내고 open_dir 쪽으로 아몬드 모양 구멍을 낸다"""
    cav = sphere(1.0, center, (radius, radius * 0.9, height / 2), 3)
    slice_rock(cav, rng, 8, (0.02, 0.1))
    d = Vector(open_dir).normalized()
    side = Vector((0, 0, 1)).cross(d).normalized()
    pts = []
    n = 14
    for i in range(n):
        a = 2 * math.pi * i / n
        x = math.sin(a) * open_w / 2 * (abs(math.sin(a)) ** 0.15)
        z = -math.cos(a) * open_h / 2
        x *= (1 - (abs(z) / (open_h / 2)) ** 2.2) ** 0.5 + 0.05
        pts.append((x * rng.uniform(0.85, 1.1), z + rng.uniform(-0.03, 0.03) * open_h))
    verts = [Vector(center) + side * x + Vector((0, 0, z)) for x, z in pts]
    far = [v + d * 3.0 for v in verts]
    nv = len(verts)
    faces = [tuple(range(nv)), tuple(range(2 * nv - 1, nv - 1, -1))]
    for i in range(nv):
        j = (i + 1) % nv
        faces.append((i, nv + i, nv + j, j))
    op = mesh_from("open", verts + far, faces)
    bcut(o, [cav, op], solver)
    return o


def dead_tree_c():
    """옹이진 죽은 나무 ~6m: 굵고 짧은 줄기가 비틀린 두 갈래로 갈라지고 꼭대기는 부러졌다.
    줄기 앞(-Y)에 속이 빈 구멍, 혹(옹이), 부러진 가지 토막, 밑동을 타고 오른 덩굴 조금"""
    rng = random.Random(777)
    tr = Tree(rng)
    trunk = [Vector((0, 0, -0.4)), Vector((0.05, 0.0, 0.5)), Vector((0.14, 0.06, 1.3)), Vector((0.1, 0.14, 2.0)),
             Vector((0.0, 0.1, 2.7))]
    tk = tr.branch(trunk, 0.52, 0.36, 0.7, depth=0, lobes=6, lobe_amp=0.16, twist=0.7, bumps=0.13, flare=(0.6, 1.5))
    tk['tip'] = False
    trunk_roots(tr, rng, 6, 0.46, (0.6, 1.0), (1.1, 1.7), r_k=(0.5, 0.62), dip=0.32)
    # 두 갈래 큰 줄기 (비틀리며 위로) + 부러진 가운데 토막
    limb(tr, tk, 0.88, 160, 42, 3.4, r_k=0.7, taper=1.25, gnarl=0.26, up=0.12, seg=0.35, lobes=4, lobe_amp=0.12)
    limb(tr, tk, 0.84, -15, 38, 3.1, r_k=0.64, taper=1.25, gnarl=0.28, up=0.12, seg=0.35, lobes=4, lobe_amp=0.12)
    limb(tr, tk, 0.6, 75, 22, 2.3, r_k=0.45, taper=1.3, gnarl=0.3, up=0.12)
    p, r, T, N, B = tr.at(tk, 0.97)
    top = path_grow(rng, p - Vector((0, 0, 0.2)), (0.1, 0.15, 1), 1.0, 0.25, 0.12)
    st = tr.branch(top, r * 0.7, r * 0.3, 0.9, depth=1, collar=1.1, bumps=0.12, lobes=3, lobe_amp=0.12, parent=tk)
    st['tip'] = False
    # 부러진 가지 토막: 짧고 뭉툭하게 가늘어진다
    for az, t, L in ((20, 0.45, 0.55), (230, 0.68, 0.45)):
        p, r, T, N, B = tr.at(tk, t)
        d = Vector((math.cos(R(az)), math.sin(R(az)), 0.4)).normalized()
        pts = path_grow(rng, p - d * r * 0.3, d, L + r * 0.3, 0.15, 0.2)
        st = tr.branch(pts, r * 0.4, r * 0.12, 0.8, depth=1, collar=1.35, bumps=0.14, parent=tk)
        st['tip'] = False
    extra = Acc()
    for az, t, s in ((120, 0.3, 0.3), (300, 0.5, 0.27), (60, 0.72, 0.22), (235, 0.18, 0.34), (10, 0.85, 0.2), (190, 0.6, 0.24)):
        p, r, T, N, B = tr.at(tk, t)
        d = Vector((math.cos(R(az)), math.sin(R(az)), 0))
        burl(extra, rng, p + d * r * 0.95, s, d)
    cards = Cards()
    hang_moss_on(tr, cards, rng, 4, length=(0.35, 0.8), width=(0.15, 0.24))
    m = bark_paint("dead_tree_c", BARK_OLD, moss=0.6, moss_color=MOSS, pale=0.3)
    grad_dark(m, 0.0, 1.0, 0.5)
    tint_near(m, (0, -0.3, 1.05), 0.5, (0.015, 0.01, 0.02), 0.9)
    mb = bark_paint("dead_tree_c_tw", BARK_OLD, moss=0.2, pale=0.25, edge=0.3)

    def post(ha):
        hollow(ha, rng, (0.02, 0.0, 1.05), (0, 0, 1), 0.32, 1.5, (0, -1, 0), 0.46, 1.2)
    return tree_build("dead_tree_c", tr, 0.04, 0.0085, bark_layers(1.1), twig_layers(), m, 5600, 2048, 0.06,
                      extras=[cards.obj("moss")], mat_b=mb, post_a=post, extra_a=extra,
                      ivy_starts=[((0.55, -0.3, 0.03), 5, 1.4), ((-0.5, 0.35, 0.03), 9, 1.0)])


# ───────────────────────── 거대 고목 ─────────────────────────
GIANT_LEVELS = [
    dict(kids=(6, 8), t=(0.2, 0.95), angle=(25, 58), len=(0.3, 0.5), r=(0.42, 0.62), seg=0.5, gnarl=0.28, up=0.06, kink=0.25,
         taper=1.15, lobes=3, lobe_amp=0.06, twist=0.4, bumps=0.08, kid_up=0.1, len_t=0.45, lmin=0.6),
    dict(kids=(3, 5), t=(0.25, 0.92), angle=(25, 60), len=(0.32, 0.55), r=(0.45, 0.65), seg=0.25, gnarl=0.36, up=0.06, kink=0.3,
         taper=1.2, bumps=0.06, kid_up=0.06, len_t=0.45, lmin=0.3),
    dict(kids=(2, 4), t=(0.3, 0.92), angle=(25, 55), len=(0.32, 0.55), r=(0.5, 0.72), seg=0.12, gnarl=0.42, up=0.05, kink=0.3,
         taper=1.3, bumps=0.0, rmin=0.006, lmin=0.15),
    dict(kids=(0, 2), t=(0.4, 0.9), angle=(25, 50), len=(0.3, 0.5), r=(0.5, 0.75), seg=0.07, gnarl=0.4, up=0.04,
         taper=1.3, bumps=0.0, rmin=0.004, lmin=0.1),
]


def spirit_glow(rng, center, depth_dir, n_orbs=9, r=(0.025, 0.08)):
    """속 빈 줄기 안의 희미한 영혼 빛: 구멍 안쪽 깊숙이 떠 있는 크고 작은 구슬 (도깨비불)"""
    acc = Acc()
    c = Vector(center)
    dd = Vector(depth_dir).normalized()
    for i in range(n_orbs):
        p = c + Vector((rng.uniform(-0.3, 0.3), 0, rng.uniform(-0.7, 0.8))) + dd * rng.uniform(0.15, 0.5)
        rr = rng.uniform(*r) * (1.6 if i == 0 else 1.0)
        bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=2 if rr > 0.05 else 1, radius=rr)
        acc.add([p + Vector((v.co.x, v.co.y, v.co.z * 1.25)) for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces])
        bm.free()
    o = acc.obj("spirit")
    return glow(o, 'Glow_Spirit')


def giant_roots(tr, rng, trunk, n, R_, reach=(4.5, 6.5), r_k=(0.42, 0.58)):
    """거대 고목의 뿌리: 줄기에서 내려와 땅 위를 뱀처럼 기어가다 땅속으로 들어간다"""
    a0 = rng.uniform(0, 6.283)
    for i in range(n):
        ang = a0 + i * 2 * math.pi / n + rng.uniform(-0.25, 0.25)
        c, s = math.cos(ang), math.sin(ang)
        side = Vector((-s, c, 0))
        rch = rng.uniform(*reach)
        zs = rng.uniform(1.3, 2.2)
        ph = rng.uniform(0, 6.28)
        keys = [(0.15 * R_, zs), (0.85 * R_, zs * 0.62), (1.35 * R_, zs * 0.32)]
        for k in range(1, 6):
            t = k / 5
            rr = 1.35 * R_ + (rch - 1.35 * R_) * t
            keys.append((rr, 0.32 * R_ * (1 - t) ** 1.3 + 0.05 + 0.08 * math.sin(t * 5 + ph) - 0.7 * max(0.0, t - 0.65) / 0.35))
        pts = [Vector((c * rr, s * rr, z)) + side * (math.sin(rr * 0.9 + ph) * 0.35 * min(1.0, rr / (2 * R_)))
               for rr, z in keys]
        tr.branch(pts, R_ * rng.uniform(*r_k), 0.03, 0.75, depth=9, lobes=3, lobe_amp=0.12, bumps=0.1, ell=0.8, parent=trunk)


def tree_giant():
    """숲의 랜드마크 거대 고목 ~18m: 줄기 지름 ~2.5m, 땅 위를 기는 거대한 뿌리, 굵게 펼친 가지, 늘어진 이끼,
    앞(-Y) 줄기 구멍 속에 희미한 영혼 빛(Glow_Spirit)"""
    rng = random.Random(9001)
    tr = Tree(rng)
    trunk = [Vector((0, 0, -0.8)), Vector((0.05, 0.0, 1.0)), Vector((0.25, 0.1, 3.0)), Vector((0.2, 0.35, 5.2)),
             Vector((-0.1, 0.4, 7.4)), Vector((-0.25, 0.2, 9.6)), Vector((-0.2, 0.1, 11.0))]
    tk = tr.branch(trunk, 1.25, 0.32, 0.7, depth=0, lobes=7, lobe_amp=0.14, twist=0.3, bumps=0.12, flare=(1.4, 1.6))
    tk['tip'] = False
    giant_roots(tr, rng, tk, 9, 1.25)
    a0 = rng.uniform(0, 360)
    specs = ((0.42, 18, 9.5), (0.52, 30, 9.0), (0.62, 14, 10.0), (0.72, 38, 8.0), (0.82, 26, 8.5), (0.96, 72, 7.0))
    for i, (t, el, ln) in enumerate(specs):
        limb(tr, tk, t, a0 + i * 63 + rng.uniform(-12, 12), el, ln, r_k=0.74, taper=1.05, gnarl=0.2, up=0.06, seg=0.6,
             kink=0.2, levels=GIANT_LEVELS, lobes=4, lobe_amp=0.1, droop=0.05)
    extra = Acc()
    for az, t, s in ((140, 0.25, 0.5), (320, 0.42, 0.42), (40, 0.6, 0.34), (220, 0.15, 0.55), (100, 0.5, 0.38)):
        p, r, T, N, B = tr.at(tk, t)
        d = Vector((math.cos(R(az)), math.sin(R(az)), 0))
        burl(extra, rng, p + d * r * 0.9, s, d)
    cards = Cards()
    hang_moss_on(tr, cards, rng, 70, depths=(1, 2), r_min=0.06, length=(0.9, 3.0), width=(0.3, 0.65))
    m = bark_paint("tree_giant", BARK_OLD, moss=0.75, moss_color=MOSS, pale=0.25, pale_scale=0.5, ao=0.8)
    grad_dark(m, -0.3, 2.5, 0.6)
    tint_near(m, (0.0, -0.5, 1.9), 1.0, (0.02, 0.05, 0.06), 0.85)
    tint_near(m, (0.0, -0.2, 1.9), 0.7, SPIRIT, 0.25)
    mb = bark_paint("tree_giant_tw", BARK_OLD, moss=0.3, pale=0.25, edge=0.3)
    glow_o = spirit_glow(rng, (0.0, -0.45, 1.8), (0, 1, 0))

    def post(ha):
        hollow(ha, rng, (0.05, -0.15, 1.8), (0, 0, 1), 0.75, 2.6, (0, -1, 0), 1.05, 2.2)
    return tree_build("tree_giant", tr, 0.08, 0.022, bark_layers(2.2, 1.1), twig_layers(), m, 16000, 2048, 0.12,
                      extras=[cards.obj("moss"), glow_o], mat_b=mb, post_a=post, extra_a=extra, r_cut=0.06, lod2=0.12,
                      low_step=(0.2, 0.7), guide_step=0.12, low_sides=4)


# ───────────────────────── 그루터기·통나무·뿌리 ─────────────────────────
def shroom_parts(rng, spots, glow_spots=(), brackets=()):
    """독버섯·선반버섯 굽기 원본과 저폴리 (같은 메쉬) + 아주 작은 Glow_Toxic 버섯 (굽지 않음)"""
    cap_m, stem_m, brk_m = shroom_mats()
    hs, hc, hb = Acc(), Acc(), Acc()
    for p, h, r, nrm in spots:
        toadstool(hs, hc, rng, p, h, r, nrm, seg=10)
    for p, nrm, r in brackets:
        bracket(hb, rng, p, nrm, r, seg=10)
    highs, lows = [], []
    for acc, mat, nm in ((hs, stem_m, "stem"), (hc, cap_m, "cap"), (hb, brk_m, "brk")):
        o = acc.obj(nm)
        if o is None:
            continue
        set_mat(o, mat)
        for pg in o.data.polygons:
            pg.use_smooth = True
        highs.append(o)
        lows.append(copy(o))
    glow_o = None
    if glow_spots:
        gs, gc = Acc(), Acc()
        for p, h, r, nrm in glow_spots:
            toadstool(gs, gc, rng, p, h, r, nrm, seg=6)
        gs.add(gc.v, gc.f)
        glow_o = glow(gs.obj("toxic"), 'Glow_Toxic')
    return highs, lows, glow_o


def stump():
    """그루터기 ~0.8m: 부러져 삐죽한 윗면(나이테), 땅을 움켜쥔 뿌리, 위와 밑동의 독버섯, 옆의 선반버섯"""
    rng = random.Random(606)
    tr = Tree(rng)
    trunk = [Vector((0, 0, -0.3)), Vector((0.02, 0.01, 0.3)), Vector((0.03, 0.0, 0.8)), Vector((0.02, -0.02, 1.2))]
    tk = tr.branch(trunk, 0.32, 0.26, 1.0, depth=0, lobes=5, lobe_amp=0.1, twist=0.8, bumps=0.08, flare=(0.25, 1.45))
    tk['tip'] = False
    trunk_roots(tr, rng, 5, 0.32, (0.3, 0.45), (0.8, 1.15), r_k=(0.38, 0.5), dip=0.22)
    A, _ = tr.meshes(0.0, hi=True)
    o = A.obj("stump_h")
    remesh(o, 0.007)
    jag = jagged_cutter((0, 0, 0.6), (0, 0, 1), 0.36, rng, slope=0.22, rough=0.035, shards=11, shard_h=(0.08, 0.3),
                        res=72, shard_w=(0.025, 0.06))
    bowl = sphere(1.0, (0.03, 0.0, 0.62), (0.17, 0.15, 0.12), 3)
    bcut(o, [jag, bowl], 'FAST')
    remesh(o, 0.0055)
    guide = tr.guide(0.03)
    base = copy(o)
    surface(o, bark_layers(0.45), seed=BARK_SEEDS[2], guide=guide)
    delete(guide)
    m = bark_paint("stump", BARK_OLD, moss=0.7, moss_color=MOSS, pale=0.2)
    wood_mix(m, (0, 0, 0), (0, 0, 1), lambda nt, P, Nrm: kit._mul(nt, kit._ramp(nt, _sep(nt, Nrm, 'Z'), 0.35, W((0, 0, 0)),
                                                                                  0.6, W((1, 1, 1))),
                                                                 kit._ramp(nt, _sep(nt, P, 'Z'), 0.45, W((0, 0, 0)), 0.52,
                                                                           W((1, 1, 1)))),
             ring_freq=110.0)
    grad_dark(m, -0.1, 0.35, 0.5)
    set_mat(o, m)
    low = low_from(base, 2600, z=-0.04); delete(base)
    # 버섯 자리: 윗면 구덩이, 밑동 뿌리 사이, 옆면
    spots = [((0.05, 0.03, 0.56), 0.09, 0.045, (0, 0, 1)), ((-0.06, -0.04, 0.57), 0.06, 0.03, (0, 0, 1)),
             ((0.1, -0.08, 0.6), 0.05, 0.022, (0.3, -0.3, 1))]
    for k in range(4):
        a = R(200 + k * 22 + rng.uniform(-6, 6)); rr = 0.43 + rng.uniform(0, 0.08)
        spots.append(((math.cos(a) * rr, math.sin(a) * rr, 0.0), rng.uniform(0.06, 0.11), rng.uniform(0.025, 0.045),
                      (math.cos(a) * 0.3, math.sin(a) * 0.3, 1)))
    brk = []
    for az, z, r in ((60, 0.3, 0.09), (85, 0.38, 0.07), (75, 0.22, 0.06)):
        d = Vector((math.cos(R(az)), math.sin(R(az)), 0))
        brk.append((d * 0.36 + Vector((0, 0, z)), d, r))
    gl = []
    for k in range(3):
        a = R(300 + k * 15); rr = 0.45
        gl.append(((math.cos(a) * rr, math.sin(a) * rr, 0.0), rng.uniform(0.03, 0.05), rng.uniform(0.012, 0.018), (0, 0, 1)))
    hs, ls, glow_o = shroom_parts(rng, spots, gl, brk)
    cards = Cards()
    for _ in range(7):
        a = rng.uniform(0, 6.28); rr = rng.uniform(0.5, 0.75)
        grass_tuft(cards, rng, (math.cos(a) * rr, math.sin(a) * rr, 0.0), rng.uniform(0.18, 0.32), rng.uniform(0.18, 0.3), 3, 0.45)
    return finish("stump", [o] + hs, [low] + ls, extras=[cards.obj("grass"), glow_o], size=1024, extr=0.045, uv_angle=70)


def _sep(nt, vec, axis):
    s = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(vec, s.inputs[0])
    return s.outputs[axis]


def log_fallen():
    """쓰러진 통나무 ~5m: 양끝이 부러져 삐죽하고, 한쪽 끝은 속이 썩어 비었다. 윗면 이끼, 선반버섯, 부러진 가지 토막"""
    rng = random.Random(505)
    tr = Tree(rng)
    pts = [Vector((-2.6, 0.05, 0.27)), Vector((-1.3, -0.04, 0.29)), Vector((0.0, 0.03, 0.3)), Vector((1.3, 0.1, 0.27)),
           Vector((2.6, 0.02, 0.24))]
    lg = tr.branch(pts, 0.34, 0.27, 1.0, depth=0, lobes=3, lobe_amp=0.06, twist=0.3, bumps=0.07)
    lg['tip'] = False
    for x, az, el, L in ((-1.0, 80, 35, 0.55), (0.6, -100, 20, 0.45), (1.5, 90, 55, 0.35)):
        p, r, T, N, B = tr.at(lg, (x + 2.6) / 5.2)
        d = Vector((0.2, math.cos(R(az)) * math.cos(R(el)), math.sin(R(el)))).normalized()
        d = Vector((math.sin(R(15)), math.sin(R(az)) * math.cos(R(el)), math.sin(R(el)))).normalized()
        st = tr.branch(path_grow(rng, p - d * r * 0.4, d, L + r, 0.2, 0.1), r * 0.3, r * 0.22, 1.0, depth=1, collar=1.4,
                       bumps=0.08, parent=lg)
        st['tip'] = False
    A, _ = tr.meshes(0.0, hi=True)
    o = A.obj("log_h")
    remesh(o, 0.0085)
    j1 = jagged_cutter((2.42, 0.02, 0.24), (1, 0, 0), 0.4, rng, slope=0.35, rough=0.04, shards=10, shard_h=(0.1, 0.35), res=64)
    j2 = jagged_cutter((-2.42, 0.05, 0.27), (-1, 0, 0), 0.42, rng, slope=0.25, rough=0.04, shards=9, shard_h=(0.08, 0.28), res=64)
    bore = cyl(0.16, 1.6, (-2.4, 0.05, 0.3), 16, rot=(0, R(90), 0))
    bore2 = sphere(1.0, (-1.65, 0.05, 0.3), (0.3, 0.15, 0.14), 2)
    bcut(o, [j1, j2, bore, bore2], 'FAST')
    remesh(o, 0.0075)
    guide = tr.guide(0.04)
    base = copy(o)
    surface(o, bark_layers(0.65), seed=BARK_SEEDS[3], guide=guide)
    delete(guide)
    m = bark_paint("log_fallen", BARK_OLD, moss=0.8, moss_color=MOSS, pale=0.4, pale_scale=1.6)
    top_cover(m, MOSS, amount=0.7, scale=2.2, nz=(0.55, 0.88), lo=0.45, hi=0.58)
    wood_mix(m, (0, 0.03, 0.27), (1, 0, 0), mask_axis_end((1, 0, 0), 2.28), ring_freq=95.0)
    grad_dark(m, -0.05, 0.25, 0.45)
    set_mat(o, m)
    low = low_from(base, 5200, z=-0.04); delete(base)
    brk = []
    for x, side, z, r in ((-0.6, -1, 0.3, 0.1), (-0.45, -1, 0.2, 0.08), (-0.75, -1, 0.17, 0.07), (1.0, 1, 0.33, 0.09),
                          (1.15, 1, 0.22, 0.07)):
        brk.append((Vector((x, side * 0.31, z)), Vector((0, side, 0)), r))
    spots = [((x, y, 0.58), rng.uniform(0.05, 0.08), rng.uniform(0.02, 0.035), (0, y * 2, 1))
             for x, y in ((0.18, 0.06), (0.27, -0.05), (0.31, 0.1), (-1.2, 0.0), (-1.12, 0.1))]
    spots += [((-2.0, -0.38, 0.0), 0.08, 0.035, (0, -0.4, 1)), ((-1.92, -0.42, 0.0), 0.05, 0.022, (0, -0.4, 1))]
    hs, ls, glow_o = shroom_parts(rng, spots, (), brk)
    cards = Cards()
    for _ in range(14):
        x = rng.uniform(-2.6, 2.6); side = rng.choice((-1, 1))
        grass_tuft(cards, rng, (x, side * rng.uniform(0.3, 0.5), 0.0), rng.uniform(0.2, 0.38), rng.uniform(0.22, 0.34), 3, 0.4)
    ivy_p = ivy_light(low, (0.4, -0.36, 0.03), 11, 1.3, leaf=0.055, gravity=0.3, adhesion=0.8)
    return finish("log_fallen", [o] + hs, [low] + ls, extras=[cards.obj("grass")] + ivy_p, size=1024, extr=0.05, uv_angle=70)


def roots():
    """땅 위로 드러난 뿌리 엉킴 ~3m: 뒤쪽(+Y) 땅속 한 곳에서 부채꼴로 뻗어 나온 굵은 뿌리들이
    땅 위로 솟아 물결치며 서로 엇갈리다가 앞쪽에서 다시 땅속으로 파고든다 (보이지 않는 큰 나무의 뿌리)"""
    rng = random.Random(808)
    tr = Tree(rng)
    src_c = Vector((0.15, 1.45, 0.0))
    specs = []
    for i in range(6):                     # 굵은 뿌리: 뒤에서 앞으로 부채꼴
        specs.append((R(-90 + (i - 2.5) * 16 + rng.uniform(-8, 8)),
                      src_c + Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.15, 0.15), 0)), rng.uniform(1.6, 2.9), 1.0))
    for i in range(3):                     # 가는 뿌리: 비스듬히 가로질러 굵은 뿌리 위를 넘는다
        a = R(rng.choice((-20, 200)) + rng.uniform(-25, 25))
        specs.append((a, Vector((-math.cos(a) * 1.2, -math.sin(a) * 1.2 + rng.uniform(-0.6, 0.3), 0)), rng.uniform(1.6, 2.4), 0.55))
    for a, start, L, thick in specs:
        d = Vector((math.cos(a), math.sin(a), 0))
        sd = Vector((-d.y, d.x, 0))
        n = 12
        ph = rng.uniform(0, 6.28); fr = rng.uniform(1.1, 3.0); amp = rng.uniform(0.03, 0.16)
        lift = rng.uniform(0.0, 0.12) + (0.06 if thick < 1 else 0.0)
        wig = rng.uniform(0.2, 0.45)
        pts = []
        for k in range(n + 1):
            t = k / n
            z = -0.3 + (0.3 + lift) * min(1.0, t * 5) + amp * math.sin(t * math.pi * fr + ph) \
                - (0.5 + lift) * max(0.0, (t - 0.8) / 0.2)
            pts.append(start + d * (L * t) + sd * (wig * math.sin(t * 3.7 + ph)) + Vector((0, 0, z)))
        r0 = rng.uniform(0.07, 0.15) * thick
        b = tr.branch(pts, r0, r0 * 0.3, 0.9, depth=1, lobes=2, lobe_amp=0.1, twist=0.6, bumps=0.1, ell=0.9)
        for _ in range(rng.randint(0, 2)):
            p, r, T, N, B = tr.at(b, rng.uniform(0.3, 0.75))
            if p.z < 0.05:
                continue
            s2 = Vector((-T.y, T.x, 0)).normalized() * rng.choice((-1, 1))
            dd = (s2 + T * rng.uniform(-0.3, 0.6) + Vector((0, 0, -0.9))).normalized()
            q = path_grow(rng, p, dd, rng.uniform(0.35, 0.6), 0.12, 0.2, droop=0.4)
            tr.branch(q, r * 0.6, 0.012, 0.9, depth=2, collar=1.25, bumps=0.08, parent=b)
    A, Bh = tr.meshes(0.03, hi=True, r_cut=0.02)
    o = A.obj("roots_h")
    remesh(o, 0.006)
    guide = tr.guide(0.03)
    base = copy(o)
    surface(o, bark_layers(0.45), seed=BARK_SEEDS[4], guide=guide)
    hb = Bh.obj("roots_hb")
    m = bark_paint("roots", BARK_OLD, moss=0.45, moss_color=MOSS, pale=0.3)
    top_cover(m, MOSS, amount=0.4, scale=2.4, nz=(0.65, 0.92), lo=0.48, hi=0.6)
    grad_dark(m, -0.1, 0.14, 0.7)
    set_mat(o, m)
    highs = [o]
    if hb is not None:
        surface(hb, twig_layers(), seed=BARK_SEEDS[1], guide=guide)
        set_mat(hb, m)
        highs.append(hb)
    delete(guide)
    low = low_from(base, 3600, z=-0.03); delete(base)
    _, Bl = tr.meshes(0.03, hi=False, r_cut=0.02)
    lows = [low]
    lb = Bl.obj("roots_lb")
    if lb is not None:
        drop_below(lb, -0.03)
        lows.append(lb)
    cards = Cards()
    for _ in range(12):
        p = Vector((rng.uniform(-1.4, 1.4), rng.uniform(-1.3, 1.4), 0.0))
        grass_tuft(cards, rng, p, rng.uniform(0.2, 0.38), rng.uniform(0.2, 0.32), 3, 0.45)
    spots = [((0.25, 0.75, 0.0), 0.08, 0.035, (0, 0, 1)), ((0.33, 0.8, 0.0), 0.05, 0.022, (0, 0, 1)),
             ((-0.5, -0.6, 0.0), 0.06, 0.028, (0, 0, 1))]
    hs, ls, _ = shroom_parts(rng, spots)
    return finish("roots", highs + hs, lows + ls, extras=[cards.obj("grass")], size=1024, extr=0.04, uv_angle=66)


# ───────────────────────── 목록 ─────────────────────────
BUILDERS = [
    ("rock_a", rock_a),
    ("rock_b", rock_b),
    ("rock_c", rock_c),
    ("rock_flat", rock_flat),
    ("cliff_a", cliff_a),
    ("cliff_b", cliff_b),
    ("cliff_c", cliff_c),
    ("dead_tree_a", dead_tree_a),
    ("dead_tree_b", dead_tree_b),
    ("dead_tree_c", dead_tree_c),
    ("tree_giant", tree_giant),
    ("stump", stump),
    ("log_fallen", log_fallen),
    ("roots", roots),
]

META = {
    # 바위 ~1.5m: 지형 나무 인스턴스로 대량 배치 (Y 회전만)
    "rock_a": {"kind": "tree", "tags": ["rock", "nature"], "collider": "capsule", "footprint": 0.9, "sink": 0.12, "tilt": 0,
               "align": False, "scale": [0.6, 1.5], "cull": 0.01, "shadows": True},
    # 큰 바위 ~3.6m (위에서 갈라진 틈, 윗면 이끼·풀): 경사에 맞춰 눕힌다
    "rock_b": {"kind": "prop", "tags": ["rock", "nature"], "collider": "mesh", "footprint": 2.0, "sink": 0.15, "tilt": 6,
               "align": True, "scale": [0.8, 1.3], "cull": 0.006, "shadows": True},
    # 작은 돌 ~0.7m + 조약돌 둘: 흩뿌리기
    "rock_c": {"kind": "tree", "tags": ["rock", "nature"], "collider": "none", "footprint": 0.5, "sink": 0.05, "tilt": 0,
               "align": False, "scale": [0.6, 1.6], "cull": 0.02, "shadows": True},
    # 납작한 판석 노두 ~3x2x0.7m (층층이 어긋난 판)
    "rock_flat": {"kind": "prop", "tags": ["rock", "nature"], "collider": "mesh", "footprint": 1.8, "sink": 0.12, "tilt": 4,
                  "align": True, "scale": [0.8, 1.4], "cull": 0.008, "shadows": True},
    # 절벽 덩어리 ~10x6x8m: 앞(-Y)이 가파른 면
    "cliff_a": {"kind": "prop", "tags": ["cliff", "rock", "nature"], "collider": "mesh", "footprint": 5.5, "sink": 0.4, "tilt": 2,
                "align": False, "scale": [0.8, 1.6], "cull": 0.003, "shadows": True},
    # 바위 첨탑 ~6x6x12m (+X 로 기운다)
    "cliff_b": {"kind": "prop", "tags": ["cliff", "rock", "nature"], "collider": "mesh", "footprint": 3.2, "sink": 0.4, "tilt": 3,
                "align": False, "scale": [0.8, 1.5], "cull": 0.003, "shadows": True},
    # 넓고 낮은 두 단 절벽 ~15x7x5m
    "cliff_c": {"kind": "prop", "tags": ["cliff", "rock", "nature"], "collider": "mesh", "footprint": 7.5, "sink": 0.4, "tilt": 1,
                "align": False, "scale": [0.8, 1.6], "cull": 0.003, "shadows": True},
    # 뒤틀린 죽은 나무 ~6.3m: 콜라이더는 줄기 캡슐
    "dead_tree_a": {"kind": "tree", "tags": ["nature"], "collider": "capsule", "footprint": 1.6, "sink": 0.05, "tilt": 0,
                    "align": False, "scale": [0.85, 1.25], "cull": 0.006, "shadows": True},
    # 기운 죽은 나무 ~5m (+X 로 기운다, 캡슐은 밑동 기준)
    "dead_tree_b": {"kind": "tree", "tags": ["nature"], "collider": "capsule", "footprint": 1.4, "sink": 0.05, "tilt": 0,
                    "align": False, "scale": [0.85, 1.3], "cull": 0.006, "shadows": True},
    # 속 빈 옹이 나무 ~5m: 구멍은 앞(-Y)
    "dead_tree_c": {"kind": "tree", "tags": ["nature"], "collider": "capsule", "footprint": 1.6, "sink": 0.05, "tilt": 0,
                    "align": False, "scale": [0.9, 1.3], "cull": 0.006, "shadows": True},
    # 거대 고목 ~17m: 앞(-Y) 줄기 구멍 속 영혼 빛 자리에 희미한 청록 점광원
    "tree_giant": {"kind": "landmark", "tags": ["landmark", "nature", "light"], "collider": "mesh", "footprint": 7.0,
                   "sink": 0.3, "tilt": 0, "align": False, "scale": [0.9, 1.15], "cull": 0.002, "shadows": True,
                   "light": {"offset": [0.0, -0.5, 1.8], "color": list(SPIRIT), "intensity": 6, "range": 8}},
    # 그루터기 ~0.85m (독버섯, 아주 작은 독기 발광)
    "stump": {"kind": "prop", "tags": ["nature"], "collider": "capsule", "footprint": 0.8, "sink": 0.04, "tilt": 3,
              "align": False, "scale": [0.8, 1.3], "cull": 0.015, "shadows": True},
    # 쓰러진 통나무 ~5.4m (X 방향으로 누움, 속 빈 끝은 -X)
    "log_fallen": {"kind": "prop", "tags": ["nature"], "collider": "mesh", "footprint": 2.7, "sink": 0.06, "tilt": 3,
                   "align": True, "scale": [0.85, 1.2], "cull": 0.008, "shadows": True},
    # 드러난 뿌리 엉킴 ~3m (뿌리가 +Y 쪽 땅속에서 나와 -Y 쪽으로 뻗는다): 밟고 지나간다
    "roots": {"kind": "prop", "tags": ["nature"], "collider": "none", "footprint": 1.6, "sink": 0.04, "tilt": 2,
              "align": True, "scale": [0.8, 1.4], "cull": 0.012, "shadows": True},
}

# NATURE_PV="rock_a,all" 처럼 환경 변수로 다시 찍을 미리보기만 고른다 (없으면 전부)
PREVIEWS = [("all", [n for n, _ in BUILDERS], False),
            ("rocks", ["rock_a", "rock_b", "rock_c", "rock_flat"], False),
            ("cliffs", ["cliff_a", "cliff_b", "cliff_c"], False),
            ("trees", ["dead_tree_a", "dead_tree_b", "dead_tree_c", "tree_giant"], False),
            ("wood", ["stump", "log_fallen", "roots"], False)] + [(n, [n], True) for n, _ in BUILDERS]
_pv = os.environ.get("NATURE_PV")
if _pv:
    _want = set(_pv.split(","))
    PREVIEWS = [p for p in PREVIEWS if p[0] in _want] or [("none", [], False)]
