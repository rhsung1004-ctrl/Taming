# 폐허 석조물 묶음 (ruins)
#   기둥, 부러진 기둥, 무너진 벽, ㄱ자 벽 모서리, 뾰족 아치 문, 무너진 계단, 철 울타리, 철문, 영혼 등불, 봉인의 제단, 돌무더기
#
# 만드는 방식
#   - 돌은 "한 장씩" 만든다: 블록마다 상자(또는 다각형 기둥)를 만들고, 모서리를 평면으로 쳐낸 뒤(bm_chip) 살짝 모를 깎는다(bm_bevel).
#     블록 사이는 2~3cm 띄워 둔다 → 리메시 뒤에도 줄눈이 실제 홈으로 남고, 뒤쪽 심(core)이 구멍을 막는다.
#   - 크게 깨진 곳은 평면 몇 장(bm_break) 또는 울퉁불퉁한 단면 커터(rough_cutter), 각진 덩어리 커터(chunk)로 파낸다.
#   - 그 다음 kit.sculpt 로 겹겹이 떨어진 턱·금·구멍을 새기고 kit.paint 로 칠해 굽는다.
import math, random, os
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
from mathutils import noise as mnoise
import kit
from kit import *

# kit.load_fbx 는 FBX 에서 함께 들어온 "Foliage"·"Glow_*" 재질을 진짜 재질로 착각해 미리보기에서 잎이 하얗게,
# 발광이 꺼져 보인다 (kit 버그). 묶음을 읽을 때 진짜 재질을 먼저 만들어 두어 피한다 (내보내는 파일에는 영향 없음).
if kit.sc is not None:
    foliage_mat()
    for _g in GLOW:
        glow_mat(_g)

R = math.radians
IVY_COL = (0.1, 0.21, 0.16)          # 덩굴 잎: 어둡고 차가운 초록


# ───────────────────────── 안전한 파내기 ─────────────────────────
# kit.cut(EXACT 불리언)은 bm_bevel·bm_chip 이 만든 미세한 자기 교차가 있는 블록에 획 커터(서로 겹침)를 쓰면
# 닫히지 않은(구멍 난) 메쉬를 돌려줄 때가 있다. 그대로 리메시하면 그 조각이 껍데기만 남거나 통째로 사라진다
# (제단 선돌 둘이 사라지고 룬 발광만 허공에 떠 있던 원인). 결과가 열려 있으면 원본을 먼저 리메시해 닫은 뒤 다시 판다.
def open_edges(o):
    bm = bmesh.new(); bm.from_mesh(o.data)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n

def cut_safe(a, *cutters, voxel=0.008):
    flat = []
    for c in cutters:
        flat += list(c) if isinstance(c, (list, tuple)) else [c]
    if not flat:
        return a
    before = open_edges(a)
    backup = copy(a)
    spare = [copy(c) for c in flat]
    kit.cut(a, flat)
    bad = open_edges(a)
    if bad <= before:
        delete(backup)
        for c in spare:
            delete(c)
        return a
    print("CUT retry", a.name, "열린 모서리", bad, "→ 리메시 후 다시 판다")
    old = a.data
    a.data = backup.data
    delete(backup)
    bpy.data.meshes.remove(old)
    remesh(a, voxel)
    kit.cut(a, spare)
    print("CUT retry result", a.name, "열린 모서리", open_edges(a))
    return a

cut = cut_safe          # 이 묶음 안의 cut(...) 은 모두 안전한 파내기를 쓴다 (kit.chip 안쪽의 kit.cut 은 그대로)
SOUL = (0.62, 0.35, 1.0)              # 영혼 등불 빛 색


# ───────────────────────── 블록 도우미 (bmesh) ─────────────────────────
def lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)] if n > 1 else [a]

class Acc:
    """여러 bmesh 조각을 행렬로 옮겨 하나의 메쉬로 모은다"""
    def __init__(self):
        self.v, self.f = [], []

    def add(self, bm, M=None):
        bm.verts.index_update()
        off = len(self.v)
        for v in bm.verts:
            self.v.append((M @ v.co) if M is not None else v.co.copy())
        for f in bm.faces:
            self.f.append(tuple(off + v.index for v in f.verts))
        bm.free()

    def add_raw(self, verts, faces, M=None):
        off = len(self.v)
        for p in verts:
            self.v.append((M @ Vector(p)) if M is not None else Vector(p))
        for f in faces:
            self.f.append(tuple(off + i for i in f))

    def empty(self):
        return not self.f

    def obj(self, name):
        return mesh_from(name, self.v, self.f)

def TR(loc=(0, 0, 0), rot=(0, 0, 0)):
    """위치 + 회전(XYZ 오일러, 라디안) 행렬"""
    return Matrix.Translation(Vector(loc)) @ Euler(rot, 'XYZ').to_matrix().to_4x4()

def bm_box(sx, sy, sz):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
    return bm

def bm_poly(poly, a0, a1, axis='z'):
    """2D 다각형을 늘인 기둥. axis='z': poly 는 XY, z 방향으로 a0~a1 / axis='y': poly 는 XZ, y 방향으로 a0~a1"""
    bm = bmesh.new()
    mk = (lambda p, w: (p[0], p[1], w)) if axis == 'z' else (lambda p, w: (p[0], w, p[1]))
    A = [bm.verts.new(mk(p, a0)) for p in poly]
    B = [bm.verts.new(mk(p, a1)) for p in poly]
    bm.faces.new(A)
    bm.faces.new(B[::-1])
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((A[i], A[j], B[j], B[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm

def bm_sector(r0, r1, a0, a1, z0, z1):
    """원형 단의 부채꼴 블록 (XY 에서 반지름 r0~r1, 각도 a0~a1)"""
    n = max(2, int(abs(a1 - a0) / R(5)) + 2)
    outer = [(r1 * math.cos(a), r1 * math.sin(a)) for a in lin(a0, a1, n)]
    inner = [(r0 * math.cos(a), r0 * math.sin(a)) for a in lin(a1, a0, n)]
    return bm_poly(outer + inner, z0, z1, 'z')

def bm_cut(bm, co, no):
    """평면 바깥쪽을 잘라 버리고 구멍을 막는다 (볼록한 조각용)"""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    r = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector(co), plane_no=Vector(no).normalized(), clear_outer=True)
    es = [g for g in r['geom_cut'] if isinstance(g, bmesh.types.BMEdge)]
    if es:
        bmesh.ops.holes_fill(bm, edges=es, sides=0)
    return bm

def _corners(bm, ang=28):
    out = []
    for v in bm.verts:
        k = sum(1 for e in v.link_edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > R(ang))
        if k >= 3:
            out.append(v.co.copy())
    return out

def bm_center(bm):
    return sum((v.co for v in bm.verts), Vector()) / max(1, len(bm.verts))

def bm_chip(bm, rng, n, depth=(0.02, 0.07), zmin=-1e9, zmax=1e9):
    """블록 꼭짓점을 정으로 친 것처럼 평평한 면으로 쳐낸다 (기울기를 제각각 주어 모서리를 따라 비스듬히 떨어져 나간 자국)"""
    cs = [c for c in _corners(bm) if zmin <= c.z <= zmax]
    if not cs or n <= 0:
        return bm
    cen = bm_center(bm)
    for _ in range(n):
        if len(bm.verts) < 4:
            return bm
        p = rng.choice(cs)
        d = p - cen
        nrm = Vector((math.copysign(rng.uniform(0.25, 1.4), d.x), math.copysign(rng.uniform(0.25, 1.4), d.y),
                      math.copysign(rng.uniform(0.25, 1.4), d.z))).normalized()
        bm_cut(bm, p - nrm * rng.uniform(*depth), nrm)
    return bm

def bm_break(bm, rng, co, no, facets=3, spread=0.35, jitter=0.04):
    """크게 깨진 면: 방향이 조금씩 다른 평면 몇 장으로 잘라 조개껍질처럼 각진 단면을 만든다"""
    no = Vector(no).normalized()
    for i in range(facets):
        n2 = (no + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * spread).normalized()
        c2 = Vector(co) + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * jitter
        bm_cut(bm, c2, n2)
    return bm

def bm_bevel(bm, w=0.012, ang=28):
    """날카로운 모서리를 살짝 깎는다 (닳은 모서리가 빛을 받게)"""
    es = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > R(ang) and e.calc_length() > w * 2.5]
    if es and w > 0:
        try:
            bmesh.ops.bevel(bm, geom=es, offset=w, offset_type='OFFSET', segments=1, profile=0.5, affect='EDGES', clamp_overlap=True)
        except Exception as ex:   # 잘린 자리의 짧은 모서리 때문에 실패하면 깎지 않는다
            print("bevel skip", ex)
    return bm

def bm_flake(bm, rng, n, depth=(0.012, 0.035), axes=((0, 1, 0), (0, -1, 0), (0, 0, 1), (1, 0, 0), (-1, 0, 0))):
    """면이 모서리 쪽으로 얇게 떨어져 나간 자국: 면과 거의 나란한 비스듬한 평면으로 모서리 한쪽을 깎는다
    (모서리를 따라 한쪽 끝은 깊고 다른 끝은 사라지게 기울여, 매끈한 상자 면이 남지 않게)"""
    if n <= 0 or not bm.verts:
        return bm
    for _ in range(n):
        if len(bm.verts) < 4:          # 앞의 자르기로 조각이 다 없어졌으면 그만
            return bm
        cen = bm_center(bm)
        f = Vector(rng.choice(axes))
        others = [Vector(a) for a in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)) if abs(Vector(a).dot(f)) < 0.5]
        t = rng.choice(others)
        e = f.cross(t)
        hf = max((v.co - cen).dot(f) for v in bm.verts)
        ht = max((v.co - cen).dot(t) for v in bm.verts)
        a = R(rng.uniform(10, 26))
        nrm = (f * math.cos(a) + t * math.sin(a) + e * rng.uniform(-0.35, 0.35)).normalized()
        edge = cen + f * hf + t * ht + e * rng.uniform(-0.2, 0.2) * max(0.05, max((v.co - cen).dot(e) for v in bm.verts))
        bm_cut(bm, edge - nrm * rng.uniform(*depth), nrm)
    return bm

def stone_blk(bm, rng, chips=(1, 3), depth=(0.02, 0.07), bevel=0.012, zmin=-1e9, flakes=(0, 2)):
    """블록 마무리: 꼭짓점 쳐내기 → 면 떨어짐 → 모 깎기"""
    bm_chip(bm, rng, rng.randint(*chips), depth, zmin=zmin)
    bm_flake(bm, rng, rng.randint(*flakes))
    bm_bevel(bm, bevel)
    return bm

# ───────────────────────── 커터 ─────────────────────────
def chunk(center, size, rng, planes=10, depth=(0.08, 0.3), sub=2):
    """평면으로 깎은 각진 덩어리 (떨어진 조각, 또는 파낸 자국 커터)"""
    s = sphere(1.0, center, size, sub, rot=(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)))
    slice_rock(s, rng, planes, depth)
    return s

def rough_cutter(co, no, w=2.0, h=2.0, amp=0.04, freq=4.0, res=22, depth=3.0, seed=0):
    """울퉁불퉁한 단면으로 자르는 커터: co 를 지나는 면(no 방향 쪽을 파낸다), 면은 잡음으로 들쭉날쭉"""
    no = Vector(no).normalized()
    t1 = no.orthogonal().normalized()
    t2 = no.cross(t1)
    co = Vector(co)
    off = Vector((seed * 17.31, seed * 5.13, seed * 9.71))

    def hgt(u, v):
        p = Vector((u * freq, v * freq, 0.0)) + off
        n = mnoise.noise(p) + 0.5 * mnoise.noise(p * 2.13) + 0.25 * mnoise.noise(p * 4.37)
        # 조개껍질처럼 계단진 단면
        q = math.floor(n * 3.0) / 3.0
        return (n * 0.6 + q * 0.4) * amp

    N = res + 1
    B, T = [], []
    for j in range(N):
        for i in range(N):
            u = (i / res - 0.5) * w
            v = (j / res - 0.5) * h
            base = co + t1 * u + t2 * v
            B.append(base + no * hgt(u, v))
            T.append(base + no * depth)
    verts = B + T
    faces = []
    M = N * N
    for j in range(res):
        for i in range(res):
            a = j * N + i
            faces.append((a, a + 1, a + N + 1, a + N))
            faces.append((M + a, M + a + N, M + a + N + 1, M + a + 1))

    def side(idx):
        for k in range(len(idx) - 1):
            a, b = idx[k], idx[k + 1]
            faces.append((a, b, M + b, M + a))
    side(list(range(N)))
    side([res * N + i for i in range(N)][::-1])
    side([j * N for j in range(N)][::-1])
    side([j * N + res for j in range(N)])
    return mesh_from("rcut", verts, faces)

def ring_mesh(r0, r1, z0, z1, n=96, cx=0.0, cy=0.0):
    """닫힌 고리 (사각 단면) — 홈 파기 커터"""
    verts = []
    for z in (z0, z1):
        for r in (r0, r1):
            for i in range(n):
                a = 2 * math.pi * i / n
                verts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    faces = []
    def q(a, b, c, d):
        faces.append((a, b, c, d))
    for i in range(n):
        j = (i + 1) % n
        bi, bo, ti, to = i, n + i, 2 * n + i, 3 * n + i
        bj, boj, tj, toj = j, n + j, 2 * n + j, 3 * n + j
        q(bi, bj, boj, bo)        # 아래
        q(ti, to, toj, tj)        # 위
        q(bo, boj, toj, to)       # 바깥
        q(bi, ti, tj, bj)         # 안
    return mesh_from("ring", verts, faces)

def flat_ring(r0, r1, z, n=128, cx=0.0, cy=0.0):
    """납작한 고리 띠 (발광 룬 고리)"""
    verts, faces = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        verts += [(cx + r0 * math.cos(a), cy + r0 * math.sin(a), z), (cx + r1 * math.cos(a), cy + r1 * math.sin(a), z)]
    for i in range(n):
        j = (i + 1) % n
        faces.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    return mesh_from("glow_ring", verts, faces)

# 룬 글자: (u, v) -1~1 안의 획 목록. 이 게임만의 문양 (실제 문자를 옮기지 않았다)
GLYPHS = [
    # 마름모 눈 + 가운데 획
    [((0, 1), (0.6, 0)), ((0.6, 0), (0, -1)), ((0, -1), (-0.6, 0)), ((-0.6, 0), (0, 1)), ((0, -0.35), (0, 0.35))],
    # 아래로 갈라진 세 갈래 + 위 가로획
    [((0, 1), (0, -0.2)), ((0, -0.2), (-0.6, -1)), ((0, -0.2), (0.6, -1)), ((-0.35, 0.65), (0.35, 0.65))],
    # 삼각 머리 + 기둥
    [((-0.6, -0.15), (0.6, -0.15)), ((0.6, -0.15), (0, 0.95)), ((0, 0.95), (-0.6, -0.15)), ((0, -0.15), (0, -1))],
    # 번개 등뼈
    [((0, 1), (0, -1)), ((-0.55, 0.8), (0.5, 0.25)), ((0.5, 0.25), (-0.5, -0.25)), ((-0.5, -0.25), (0.55, -0.8))],
    # 모래시계
    [((-0.55, 1), (0.55, 1)), ((0.55, 1), (-0.55, -1)), ((-0.55, -1), (0.55, -1)), ((0.55, -1), (-0.55, 1))],
    # 겹 갈매기 (전나무)
    [((0, -1), (0, 1)), ((-0.55, 0.25), (0, 0.75)), ((0, 0.75), (0.55, 0.25)), ((-0.55, -0.5), (0, -0.05)), ((0, -0.05), (0.55, -0.5))],
    # 열쇠 (작은 마름모 + 기둥 + 받침)
    [((0, 1), (0.4, 0.5)), ((0.4, 0.5), (0, 0.05)), ((0, 0.05), (-0.4, 0.5)), ((-0.4, 0.5), (0, 1)), ((0, 0.05), (0, -1)), ((-0.35, -1), (0.35, -1))],
    # 초승달 갈고리 + 기둥
    [((0, -1), (0, 0.8)), ((0, 0.8), (0.5, 1)), ((0.5, 1), (0.62, 0.45)), ((0.62, 0.45), (0.25, 0.1)), ((-0.5, -0.35), (0, -0.7))],
    # 두 눈 (마름모 둘이 기둥에 꿰임)
    [((0, -1), (0, 1)), ((0, 0.55), (0.4, 0.25)), ((0.4, 0.25), (0, -0.05)), ((0, -0.05), (-0.4, -0.35)), ((-0.4, -0.35), (0, -0.65))],
]

def glyph_strokes(gi, center, t_dir, v_dir, n_dir, su, sv):
    """글자 gi 의 획을 (시작, 끝) 3D 점 목록으로. t_dir: 글자 가로, v_dir: 글자 세로, n_dir: 면의 바깥 방향"""
    out = []
    for (a, b) in GLYPHS[gi % len(GLYPHS)]:
        pa = Vector(center) + t_dir * (a[0] * su) + v_dir * (a[1] * sv)
        pb = Vector(center) + t_dir * (b[0] * su) + v_dir * (b[1] * sv)
        out.append((pa, pb))
    return out

def stroke_cutter(pa, pb, n_dir, width, depth):
    """획 모양 홈 커터 (면에 수직으로 파고든다)"""
    d = (pb - pa)
    L = d.length + width
    x = d.normalized()
    z = Vector(n_dir).normalized()
    y = z.cross(x).normalized()
    M = Matrix((x, y, z)).transposed().to_4x4()
    M.translation = (pa + pb) / 2
    bm = bm_box(L, width, depth * 2)
    a = Acc(); a.add(bm, M)
    return a.obj("stroke")

def stroke_glow(strokes, n_dir, width, lift=0.003):
    """획 모양 발광 띠 (면 위에 얇게)"""
    verts, faces = [], []
    z = Vector(n_dir).normalized()
    for pa, pb in strokes:
        x = (pb - pa).normalized()
        y = z.cross(x).normalized()
        e = x * (width * 0.5)
        k = len(verts)
        for p in (pa - e - y * width / 2, pb + e - y * width / 2, pb + e + y * width / 2, pa - e + y * width / 2):
            verts.append(p + z * lift)
        faces.append((k, k + 1, k + 2, k + 3))
    return mesh_from("glyph_glow", verts, faces) if faces else None

def crystal(base, direction, length, radius, rng, sides=6):
    """끝이 뾰족한 육각 수정 (면이 조금씩 고르지 않게)"""
    d = Vector(direction).normalized()
    t1 = d.orthogonal().normalized()
    t2 = d.cross(t1)
    r0 = rng.uniform(0, 6.28)
    rad = [radius * rng.uniform(0.82, 1.15) for _ in range(sides)]
    base = Vector(base)
    verts = []
    for k, (h, sc_) in enumerate(((-0.08 * length, 0.8), (0.0, 1.0))):
        for i in range(sides):
            a = r0 + 2 * math.pi * i / sides
            verts.append(base + d * h + (t1 * math.cos(a) + t2 * math.sin(a)) * rad[i] * sc_)
    for i in range(sides):
        a = r0 + 2 * math.pi * i / sides
        hh = length * rng.uniform(0.62, 0.76)
        verts.append(base + d * hh + (t1 * math.cos(a) + t2 * math.sin(a)) * rad[i] * rng.uniform(0.92, 1.05))
    tip = base + d * length + (t1 * rng.uniform(-1, 1) + t2 * rng.uniform(-1, 1)) * radius * 0.2
    verts.append(tip)
    faces = [tuple(range(sides))[::-1]]
    for ring in range(2):
        for i in range(sides):
            j = (i + 1) % sides
            a, b = ring * sides + i, ring * sides + j
            faces.append((a, b, b + sides, a + sides))
    T = 3 * sides
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((2 * sides + i, 2 * sides + j, T))
    return verts, faces

def drop_below(o, z=-0.03):
    """땅속에 묻혀 보이지 않는 면을 지운다 (텍스처 공간·삼각형 낭비 방지)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    kill = [f for f in bm.faces if all(v.co.z < z for v in f.verts)]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o

def low_of(high, tris, z=-0.03, floor=28):
    """저폴리 만들기. 한꺼번에 줄이면(비율 0.5% 안팎) 떨어진 작은 조각(선돌·잔돌·떨어진 블록)이 납작하게 뭉개져
    사라지므로, 땅속 면을 먼저 지우고 떨어진 조각마다 보이는 넓이에 비례해 삼각형을 나눠 준다 (작은 조각은 최소 floor 개)."""
    c = copy(high)
    drop_below(c, z)
    act(c)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    parts = list(bpy.context.selected_objects)
    areas = []
    for o in parts:
        areas.append(sum(p.area for p in o.data.polygons))
    keep = [(o, a) for o, a in zip(parts, areas) if a > 3e-4]
    for o, a in zip(parts, areas):
        if a <= 3e-4:
            delete(o)
    A = sum(a for _, a in keep) or 1.0
    small = [(o, a) for o, a in keep if tris * a / A < floor]
    big = [(o, a) for o, a in keep if tris * a / A >= floor]
    rest = max(tris * 0.3, tris - floor * len(small))
    Ab = sum(a for _, a in big) or 1.0
    for o, a in keep:
        t = floor if (o, a) in small else max(floor, int(rest * a / Ab))
        n = tri_count(o)
        if n > t:
            m = o.modifiers.new('dec', 'DECIMATE')
            m.ratio = t / n
            m.use_collapse_triangulate = True
            apply_all(o)
    low = join([o for o, _ in keep])
    for p in low.data.polygons:
        p.use_smooth = True
    return low

def grow_ivy(low, starts, **kw):
    """저폴리 복사본을 대상으로 덩굴을 키운다. starts: [(점, 씨앗, 길이), ...]"""
    tgt = copy(low)
    tgt.location = (0, 0, 0)
    parts = []
    for p, seed, length in starts:
        args = dict(length=length, leaf=0.05, leaf_prob=0.3, gravity=0.6, adhesion=0.6, color=IVY_COL, dead=0.3, stem_radius=0.007)
        args.update(kw)
        parts += ivy(tgt, p, seed=seed, **args)
    delete(tgt)
    return parts

# ───────────────────────── 덩굴 (직접 만든 가벼운 버전) ─────────────────────────
# kit.ivy 는 줄기를 굵은 관으로 만들어 소품 하나에 수십만 삼각형이 된다. 여기서는 IvyGen 의 자라는 계산만 빌리고
# 줄기는 표면에 붙은 납작한 띠, 잎은 처지며 바깥으로 들린 카드로 직접 만든다 (삼각형 수를 정해 둘 수 있다).
def _ivygen():
    try:
        import add_curve_ivygen as ig
    except ImportError:
        import sys, addon_utils
        for p in addon_utils.paths():
            if p not in sys.path:
                sys.path.append(p)
        import add_curve_ivygen as ig
    return ig

def raw_mesh(name, verts, faces):
    """면 방향을 다시 계산하지 않는 메쉬 (정점 순서대로 UV·색을 붙이기 위해)"""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update(calc_edges=True)
    o = bpy.data.objects.new(name, me)
    kit.sc.collection.objects.link(o)
    return o

def _foliage_obj(name, verts, faces, uvs, cols):
    if not faces:
        return None
    o = raw_mesh(name, verts, faces)
    me = o.data
    uvl = me.uv_layers.new(name="UVMap")
    for lp in me.loops:
        uvl.data[lp.index].uv = uvs[lp.vertex_index]
    vcolor(o, lambda p, n, i: cols[i])
    set_mat(o, foliage_mat())
    return o

class Vine:
    """덩굴 줄기 띠와 잎 카드를 모은다"""
    def __init__(self, rng, col=IVY_COL, dead=0.14, leaf=(0.035, 0.06), leaf_p=0.5, stem_w=0.012, bare=0.2, wine=0.035):
        self.rng = rng; self.col = col; self.dead = dead; self.leaf = leaf; self.leaf_p = leaf_p
        self.stem_w = stem_w; self.bare = bare; self.wine = wine
        self.sv, self.sf, self.suv, self.scol = [], [], [], []
        self.lv, self.lf, self.luv, self.lcol = [], [], [], []

    def strand(self, pts, nrms, width_k=1.0, leaf_k=1.0):
        """pts: 줄기 점 목록, nrms: 각 점에서 붙어 있는 면의 바깥 방향"""
        rng = self.rng
        L = len(pts)
        if L < 2:
            return
        sides = []
        for i, p in enumerate(pts):
            d = pts[min(i + 1, L - 1)] - pts[max(i - 1, 0)]
            if d.length < 1e-6:
                d = Vector((0, 0, 1))
            sd = d.cross(nrms[i])
            if sd.length < 1e-6:
                sd = d.orthogonal()
            sides.append(sd.normalized())
        w0 = self.stem_w * width_k
        sc_ = (0.07, 0.06, 0.05)
        for i in range(L - 1):
            k = len(self.sv)
            for j, (ii, u) in enumerate(((i, 0), (i, 1), (i + 1, 1), (i + 1, 0))):
                w = w0 * (1 - 0.7 * ii / (L - 1))
                q = pts[ii] + nrms[ii] * 0.004 + sides[ii] * (w * (u - 0.5))
                self.sv.append(q)
                self.suv.append(atlas_uv('stem', u, 0.1 + 0.8 * (ii % 2)))
                self.scol.append((sc_[0], sc_[1], sc_[2], 0.05 + 0.15 * ii / (L - 1)))
            self.sf.append((k, k + 1, k + 2, k + 3))
        # 잎: 오래된 밑동은 드문드문, 끝으로 갈수록 무성하게
        acc_len = [0.0]
        for i in range(1, L):
            acc_len.append(acc_len[-1] + (pts[i] - pts[i - 1]).length)
        tot = max(1e-6, acc_len[-1])
        for i in range(L):
            t = acc_len[i] / tot
            pr = self.leaf_p * leaf_k * (self.bare + (1 - self.bare) * min(1.0, t * 1.5))
            for _ in range(2):
                if rng.random() > pr:
                    continue
                self.leaf_at(pts[i] + (pts[min(i + 1, L - 1)] - pts[i]) * rng.random(), nrms[i], 0.75 + 0.5 * t)

    def leaf_at(self, p, nrm, k=1.0):
        rng = self.rng
        g = Vector((0, 0, -1))
        g_t = g - nrm * g.dot(nrm)
        r_t = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        r_t -= nrm * r_t.dot(nrm)
        tip = r_t.normalized() + (g_t.normalized() * 0.8 if g_t.length > 1e-3 else Vector())
        if tip.length < 1e-4:
            tip = nrm.orthogonal()
        tip.normalize()
        a = R(rng.uniform(12, 55))
        tip2 = (tip * math.cos(a) + nrm * math.sin(a)).normalized()
        b = tip2.cross(nrm)
        if b.length < 1e-4:
            b = tip2.orthogonal()
        b.normalize()
        size = rng.uniform(*self.leaf) * k
        base = p + nrm * 0.006
        ks = len(self.lv)
        self.lv += [base - b * size / 2 - tip2 * size * 0.08, base + b * size / 2 - tip2 * size * 0.08,
                    base + b * size / 2 + tip2 * size, base - b * size / 2 + tip2 * size]
        self.lf.append((ks, ks + 1, ks + 2, ks + 3))
        roll = rng.random()
        if roll < self.dead * 0.5:
            cell = 'leaf_dead'
        else:
            cell = 'ivy_a' if rng.random() < 0.6 else 'ivy_b'
        self.luv += [atlas_uv(cell, 0, 0), atlas_uv(cell, 1, 0), atlas_uv(cell, 1, 1), atlas_uv(cell, 0, 1)]
        if roll < self.dead:
            base_c = (0.36, 0.3, 0.17)
        elif roll < self.dead + self.wine:
            base_c = (0.2, 0.07, 0.13)            # 검붉은 잎 몇 장 (음산한 기운)
        else:
            base_c = self.col
        j = rng.uniform(0.7, 1.25)
        tint = rng.uniform(-0.02, 0.03)
        c = (min(1, base_c[0] * j), min(1, base_c[1] * j), min(1, (base_c[2] + tint) * j))
        self.lcol += [(c[0] * 0.7, c[1] * 0.7, c[2] * 0.7, 0.25), (c[0] * 0.7, c[1] * 0.7, c[2] * 0.7, 0.25),
                      (c[0], c[1], c[2], 0.55), (c[0], c[1], c[2], 0.55)]

    def objects(self):
        out = [_foliage_obj("ivy_stem", self.sv, self.sf, self.suv, self.scol),
               _foliage_obj("ivy_leaf", self.lv, self.lf, self.luv, self.lcol)]
        return [o for o in out if o is not None]

    def tris(self):
        return 2 * (len(self.sf) + len(self.lf))

def ivy_grow(vine, target, start, seed=0, length=2.0, step=0.03, max_roots=16, branch=0.1, gravity=0.5, adhesion=0.7,
             float_len=0.25, width_k=1.0):
    """IvyGen 으로 target 표면을 따라 자라게 한 뒤 vine 에 줄기·잎을 더한다"""
    ig = _ivygen()
    ig.rand_seed(seed)
    act(target)
    bvh = ig.bvhtree_from_object(target)
    IVY = ig.Ivy(primaryWeight=0.5, randomWeight=0.25, gravityWeight=gravity, adhesionWeight=adhesion,
                 branchingProbability=branch, leafProbability=0.3, ivySize=step, ivyLeafSize=0.05,
                 ivyBranchSize=0.001, maxFloatLength=float_len, maxAdhesionDistance=0.6)
    IVY.seed(Vector(start))
    guard = 0
    while any(r.alive for r in IVY.ivyRoots) and IVY.maxLength < length and guard < 2500:
        IVY.grow(target, bvh)
        while len(IVY.ivyRoots) > max_roots:
            IVY.ivyRoots.pop()
        guard += 1
    for root in IVY.ivyRoots:
        nodes = list(root.ivyNodes)
        if len(nodes) < 4:
            continue
        pts = [n.pos.copy() for n in nodes[::2]]
        nrms = []
        for p in pts:
            loc, nr, idx, dist = bvh.find_nearest(p)
            if nr is None or dist is None or dist > 0.2:
                nr = Vector((0, -1, 0.2))
            nrms.append(Vector(nr).normalized())
        vine.strand(pts, nrms, width_k * (1.0 if root.parents == 0 else 0.6))
    return vine

def hang_strand(vine, top, length, rng, face=(0, -1, 0), sway=0.06):
    """위에서 아래로 늘어진 덩굴 한 가닥"""
    n = max(3, int(length / 0.05))
    face = Vector(face).normalized()
    side = face.cross(Vector((0, 0, 1))).normalized()
    ph = rng.uniform(0, 6.28)
    pts, nrms = [], []
    for i in range(n + 1):
        t = i / n
        p = Vector(top) + Vector((0, 0, -length * t)) + side * (math.sin(ph + t * 5.0) * sway * t) + face * (0.03 * t * t)
        pts.append(p)
        nrms.append(face)
    vine.strand(pts, nrms, 0.6, 1.2)

def spall_cutter(p, n, size, depth, rng):
    """표면이 얇게 떨어져 나간 자국 커터: p 표면 점, n 바깥 방향, size (가로, 세로), depth 파낼 깊이"""
    s = sphere(1.0, (0, 0, 0), (size[0], size[1], depth * 2.0), 2)
    slice_rock(s, rng, 7, (0.1, 0.32))
    n = Vector(n).normalized()
    q = n.to_track_quat('Z', 'Y').to_matrix().to_4x4() @ Matrix.Rotation(rng.uniform(0, 6.28), 4, 'Z')
    s.data.transform(Matrix.Translation(Vector(p) + n * depth) @ q)
    s.data.update()
    return s

def web_card(p, u_dir, v_dir, size, flip=False):
    """거미줄 구석 카드 (web_corner 칸). p: 구석 모서리 점, u_dir·v_dir: 두 변 방향"""
    u = Vector(u_dir).normalized() * size
    v = Vector(v_dir).normalized() * size
    p = Vector(p)
    o = mesh_from("web", [p, p + u, p + u + v, p + v], [(0, 1, 2, 3)])
    set_uv(o, card_uv('web_corner', flip))
    vcolor(o, lambda q, n, i: (0.78, 0.8, 0.9, 0.08))
    set_mat(o, foliage_mat())
    return o

def glow_obj(verts, faces, name='Glow_Soul'):
    o = mesh_from("glow", verts, faces)
    return glow(o, name)


# ───────────────────────── 쌓은 돌벽 ─────────────────────────
def profile(pts):
    """(x, 높이) 점들을 이은 무너진 윗선 함수"""
    pts = sorted(pts)
    def f(x):
        if x <= pts[0][0]:
            return pts[0][1]
        for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
            if x <= x1:
                t = (x - x0) / max(1e-6, x1 - x0)
                return z0 + (z1 - z0) * t
        return pts[-1][1]
    return f

def courses(rng, z0, z1, hr=(0.27, 0.36)):
    zs = [z0]
    while zs[-1] < z1:
        zs.append(zs[-1] + rng.uniform(*hr))
    return zs

def ashlar(acc, rng, x0, x1, zs, top, y0, y1, gap=0.028, blen=(0.42, 0.82), skin=(0.3, 0.38), ragged=(0.0, 0.0),
           missing=0.025, chips=(1, 3), M=None, plinth=0.0, keep=None, broken_top=True, damage=None):
    """x0~x1 구간에 줄눈이 보이는 돌 블록을 앞·뒤 두 겹으로 쌓는다 (가운데는 심이 채운다).
    zs: 켜 경계 높이, top(x): 무너진 윗선, y0·y1: 벽 앞면·뒷면, ragged: 양 끝이 들쭉날쭉 무너진 정도 (왼, 오른)
    plinth: 맨 아래 켜가 앞뒤로 튀어나온 정도, keep(xa, xb, za, zb): False 면 그 블록은 놓지 않는다
    damage: (v3b) (확률, random.Random) — 그 확률로 블록 하나가 크게 깨지고(모서리가 비스듬히 떨어져 나감) 이가 빠진다.
      따로 받은 난수를 써서 블록 배치(rng 순서)는 그대로다"""
    n = 0
    for k in range(len(zs) - 1):
        za, zb = zs[k], zs[k + 1] - gap
        if za >= top(x0) and za >= top(x1) and za >= top((x0 + x1) / 2):
            # 이 켜 전체가 무너졌어도 중간에 높은 곳이 있을 수 있으니 블록마다 다시 본다
            pass
        for face in (0, 1):
            xa = x0 + rng.uniform(0, ragged[0]) * (k / max(1, len(zs) - 2))
            xend = x1 - rng.uniform(0, ragged[1]) * (k / max(1, len(zs) - 2))
            first = True
            while xa < xend - 0.12:
                L = rng.uniform(*blen)
                if first:
                    L *= rng.uniform(0.35, 1.0)      # 켜마다 이음매가 엇갈리게
                    first = False
                xb = min(xend, xa + L)
                if xend - xb < 0.18:
                    xb = xend
                xm = (xa + xb) / 2
                t_here = top(xm)
                ok = za < t_here - 0.06 and (keep is None or keep(xa, xb, za, zb))
                if ok and k > 0 and rng.random() < missing:
                    ok = False
                if ok:
                    d = rng.uniform(*skin)
                    pr = plinth if k == 0 else 0.0
                    if face == 0:
                        ya, yb = y0 - pr + rng.uniform(-0.012, 0.01), y0 + d
                    else:
                        ya, yb = y1 - d, y1 + pr + rng.uniform(-0.01, 0.012)
                    bm = bm_box(xb - xa - gap, yb - ya, zb - za)
                    cx, cy, cz = xm, (ya + yb) / 2, (za + zb) / 2
                    # 무너진 윗선에 걸친 블록은 비스듬히 깨진 채로 남긴다
                    if broken_top and zb > t_here + 0.04:
                        # 윗선에 걸친 블록: 절반쯤은 통째로 빠지고(계단처럼 무너진 윤곽), 나머지는 제각각 비스듬히 깨진다
                        # (모두 같은 경사로 자르면 매끈한 비탈 하나로 이어져 보인다)
                        sl = (top(xb) - top(xa)) / max(0.05, xb - xa) * rng.uniform(-0.6, 1.6)
                        h_loc = t_here - cz + rng.uniform(-0.12, 0.1)
                        if h_loc < -(zb - za) * 0.25 or rng.random() < 0.4:
                            bm.free()
                            xa = xb
                            continue
                        bm_break(bm, rng, (rng.uniform(-0.15, 0.15), 0, h_loc), (-sl + rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 1), facets=rng.randint(2, 4), spread=0.6, jitter=0.05)
                    if damage is not None and damage[1].random() < damage[0]:
                        drng = damage[1]
                        hx, hy, hz = (xb - xa - gap) / 2, (yb - ya) / 2, (zb - za) / 2
                        out_y = -1 if face == 0 else 1
                        # 겉면 모서리 하나가 비스듬히 크게 떨어져 나감 + 깊은 이 빠짐
                        sx, sz = drng.choice((-1, 1)), drng.choice((-1, 1))
                        co = Vector((sx * hx * drng.uniform(0.45, 0.75), out_y * hy, sz * hz * drng.uniform(0.3, 0.7)))
                        bm_break(bm, drng, co, (sx * drng.uniform(0.4, 1.0), out_y * drng.uniform(0.6, 1.2), sz * drng.uniform(0.3, 1.0)),
                                 facets=drng.randint(2, 3), spread=0.45, jitter=0.03)
                        bm_chip(bm, drng, drng.randint(1, 2), (0.05, 0.1))
                    stone_blk(bm, rng, chips, (0.02, 0.07), 0.014)
                    R_ = TR((cx, cy, cz), (R(rng.uniform(-0.7, 0.7)), R(rng.uniform(-0.5, 0.5)), R(rng.uniform(-0.6, 0.6))))
                    acc.add(bm, (M @ R_) if M is not None else R_)
                    n += 1
                xa = xb
    return n

def core_prism(x0, x1, top, y0, y1, z0, inset=0.05, drop=0.1, step=0.09, jag=0.07, seed=0):
    """블록 뒤 심: 윗선보다 낮고 들쭉날쭉한 다각형 기둥 (XZ). 무너진 곳에서는 위에 얹는 잔돌(top_rubble)이 덮는다"""
    rr = random.Random(seed)
    xs = lin(x0 + inset, x1 - inset, max(2, int((x1 - x0) / step) + 1))
    tops = [max(z0 + 0.05, top(x) - drop - rr.uniform(0, jag)) for x in xs]
    poly = [(xs[0], z0), (xs[-1], z0)] + [(x, z) for x, z in reversed(list(zip(xs, tops)))]
    return bm_poly(poly, y0 + inset, y1 - inset, 'y')

def arch_geo(w, h_s, rise):
    """뾰족 아치 원호: 오른쪽 원호 중심 x, 반지름, 꼭대기 각"""
    r = (w * w / 4 + rise * rise) / w
    cx = w / 2 - r
    return cx, r, math.asin(min(1.0, rise / r))

def arch_outline(w, h_s, rise, grow=0.0, z_bottom=0.0, steps=10):
    """아치 구멍 윤곽 (XZ). grow 만큼 바깥으로 키운 윤곽 (같은 중심, 반지름 + grow)"""
    cx, r, a_end = arch_geo(w, h_s, rise)
    rr = r + grow
    a_top = math.acos(max(-1.0, min(1.0, -cx / rr)))
    right = [(cx + rr * math.cos(a), h_s + rr * math.sin(a)) for a in lin(0, a_top, steps)]
    right[-1] = (0.0, right[-1][1])
    left = [(-x, z) for x, z in reversed(right[:-1])]
    xr = w / 2 + grow
    return [(-xr, z_bottom), (xr, z_bottom)] + right + left

def arch_stones(rng, w, h_s, rise, T, n_side, y0, y1, gap=0.026, skip=(), slip=(), chips=(1, 2)):
    """뾰족 아치 홍예석 (한 장씩). 돌아오는 것: [(이름, bm, 중심점)] — skip: 빠진 돌 번호, slip: 조금 내려앉은 돌 번호
    번호: 오른쪽 0..n-1 (아래부터), 왼쪽 100..100+n-1, 이맛돌 999"""
    cx, r, a_end = arch_geo(w, h_s, rise)
    ro = r + T
    a_end_o = math.acos(max(-1.0, min(1.0, -cx / ro)))
    seg = a_end / (n_side + 0.5)
    out = []
    def P(rad, a, side):
        x, z = cx + rad * math.cos(a), h_s + rad * math.sin(a)
        return (x * side, z)
    for side in (1, -1):
        for i in range(n_side):
            a0 = i * seg + gap / (2 * r)
            a1 = (i + 1) * seg - gap / (2 * r)
            if i == 0:
                a0 = 0.0
            am = (a0 + a1) / 2
            poly = [P(r, a0, side), P(r, am, side), P(r, a1, side), P(ro, a1, side), P(ro, am, side), P(ro, a0, side)]
            if side < 0:
                poly = poly[::-1]
            bm = bm_poly(poly, y0 + rng.uniform(-0.01, 0.01), y1 + rng.uniform(-0.01, 0.01), 'y')
            stone_blk(bm, rng, chips, (0.02, 0.06), 0.014)
            tag = i if side > 0 else 100 + i
            c = Vector((P((r + ro) / 2, am, side)[0], (y0 + y1) / 2, P((r + ro) / 2, am, side)[1]))
            out.append((tag, bm, c))
    # 이맛돌 (꼭대기)
    a0 = n_side * seg + gap / (2 * r)
    inner_r = [P(r, a, 1) for a in lin(a0, a_end, 4)]
    inner_r[-1] = (0.0, inner_r[-1][1])
    inner_l = [(-x, z) for x, z in reversed(inner_r[:-1])]
    a0o = a0
    outer_l = [(-x, z) for x, z in (P(ro, a, 1) for a in lin(a0o, a_end_o, 4))]
    outer_l[-1] = (0.0, outer_l[-1][1])
    outer_r = [P(ro, a, 1) for a in lin(a_end_o, a0o, 4)][1:]
    poly = inner_r + inner_l + outer_l + outer_r
    bm = bm_poly(poly, y0 - 0.02, y1 + 0.02, 'y')
    stone_blk(bm, rng, chips, (0.02, 0.05), 0.014)
    out.append((999, bm, Vector((0, (y0 + y1) / 2, h_s + rise + T / 2))))
    res = []
    for tag, bm, c in out:
        if tag in skip:
            bm.free()
            continue
        res.append((tag, bm, c))
    return res

def jamb_stones(acc, rng, w, z0, z1, T, y0, y1, gap=0.026, hr=(0.26, 0.36), M=None):
    """창·문 옆 기둥돌 (양쪽, 길고 짧게 번갈아)"""
    for side in (1, -1):
        z = z0
        k = 0
        while z < z1 - 0.08:
            h = min(rng.uniform(*hr), z1 - z)
            if z1 - (z + h) < 0.12:
                h = z1 - z
            tw = T * (1.0 if k % 2 == 0 else 0.72) + gap
            x_in = w / 2 + gap / 2
            bm = bm_box(tw - gap, y1 - y0 + rng.uniform(0, 0.02), h - gap)
            stone_blk(bm, rng, (1, 2), (0.02, 0.06), 0.014)
            c = (side * (x_in + (tw - gap) / 2), (y0 + y1) / 2, z + h / 2 - gap / 2)
            R_ = TR(c, (0, 0, R(rng.uniform(-0.5, 0.5))))
            acc.add(bm, (M @ R_) if M is not None else R_)
            z += h
            k += 1

def zone_prism(outline, y0, y1, M=None):
    a = Acc()
    a.add(bm_poly(outline, y0 - 0.3, y1 + 0.3, 'y'), M)
    return a.obj("zone")

def rubble_pile(acc, rng, center, radius, n, size=(0.18, 0.4), height=0.5, M=None, extra=None):
    """무너진 돌무더기: 낮은 흙·자갈 더미 위에 깨진 블록이 비스듬히 얹혀 있다 (가운데가 높게).
    extra 목록을 주면 더미 몸통(각진 덩어리)과 자갈 객체를 거기에 넣는다"""
    c = Vector(center)
    Mx = M if M is not None else Matrix.Identity(4)
    def mound_h(rr):
        return height * 0.32 * max(0.0, 1 - (rr / (radius * 0.95)) ** 2)
    if extra is not None:
        # 낮고 울퉁불퉁한 흙·자갈 더미 (돌이 그 위에 얹힌다)
        for k in range(3):
            a = rng.uniform(0, 6.28); o_ = radius * 0.25 * k
            m = chunk((0, 0, 0), (radius * rng.uniform(0.6, 0.85), radius * rng.uniform(0.5, 0.7), height * 0.3), rng, 13, (0.08, 0.3), sub=3)
            m.data.transform(Mx @ Matrix.Translation(c + Vector((math.cos(a) * o_, math.sin(a) * o_, -height * 0.06))))
            extra.append(m)
        for _ in range(int(n * 1.6)):
            a = rng.uniform(0, 6.28)
            rr = radius * math.sqrt(rng.random()) * 1.2
            g = rng.uniform(0.045, 0.11)
            q = chunk((0, 0, 0), (g, g * 0.8, g * 0.6), rng, 8)
            q.data.transform(Mx @ Matrix.Translation(c + Vector((math.cos(a) * rr, math.sin(a) * rr, mound_h(rr) + g * 0.2))))
            extra.append(q)
    for i in range(n):
        a = rng.uniform(0, 6.28)
        rr = radius * 0.9 * math.sqrt(rng.random())
        t = max(0.0, 1 - (rr / radius) ** 2)
        sx = rng.uniform(*size)
        bm = bm_box(sx, sx * rng.uniform(0.5, 0.85), sx * rng.uniform(0.38, 0.65))
        for _ in range(rng.randint(1, 2)):
            bm_break(bm, rng, (sx * rng.uniform(-0.1, 0.3) * rng.choice((-1, 1)), 0, 0),
                     (rng.choice((-1, 1)), rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6)), facets=rng.randint(2, 3), spread=0.45)
        stone_blk(bm, rng, (2, 5), (0.025, 0.08), 0.012)
        z = mound_h(rr) + height * 0.45 * t * rng.random() + sx * 0.12 - 0.03
        p = c + Vector((math.cos(a) * rr, math.sin(a) * rr, z))
        R_ = TR(p, (R(rng.uniform(-40, 40)), R(rng.uniform(-40, 40)), rng.uniform(0, 6.28)))
        acc.add(bm, Mx @ R_)

def fallen_block(acc, rng, p, size, rot_z=None, tilt=(5, 25), broken=True, M=None):
    """땅에 떨어진 블록: 크게 깨지고 모서리가 많이 떨어져 나간 채 반쯤 묻혀 있다"""
    bm = bm_box(*size)
    if broken:
        bm_break(bm, rng, (size[0] * rng.uniform(0.05, 0.3), 0, 0), (1, rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)), facets=3, spread=0.45)
        if rng.random() < 0.6:
            bm_break(bm, rng, (0, size[1] * rng.uniform(0.15, 0.35), size[2] * 0.2), (rng.uniform(-0.4, 0.4), 1, 0.7), facets=2, spread=0.4)
    stone_blk(bm, rng, (3, 6), (0.03, 0.1), 0.014)
    rz = rng.uniform(0, 6.28) if rot_z is None else rot_z
    tx, ty = R(rng.uniform(-tilt[1], tilt[1])), R(rng.uniform(-tilt[1], tilt[1]))
    p = Vector(p)
    p.z = size[2] * 0.36 - 0.05
    R_ = TR(p, (tx * 0.5, ty * 0.5, rz))
    acc.add(bm, (M @ R_) if M is not None else R_)


# ───────────────────────── 기둥 ─────────────────────────
def _rf(z):
    """기둥 몸통 반지름 (아래가 조금 굵은 엔타시스)"""
    t = max(0.0, min(1.0, (z - 0.5) / 2.86))
    return 0.285 - 0.038 * t ** 1.5

def fluted_drum(z0, z1, rf=_rf, flutes=18, depth=0.02, samp=6, ch=0.02, rot=0.0):
    """세로 홈(fluting)이 파인 기둥 북 한 토막. 위아래 끝은 모를 죽여 이음매가 V 홈으로 보이게"""
    inner = z1 - z0 - 2 * ch
    k = max(1, int(inner / 0.22))
    zs = [z0, z0 + ch] + [z0 + ch + inner * i / k for i in range(1, k)] + [z1 - ch, z1]
    verts, faces = [], []
    N = flutes * samp
    for zi, z in enumerate(zs):
        r = rf(z) - (ch if zi in (0, len(zs) - 1) else 0.0)
        for kk in range(flutes):
            for s in range(samp):
                u = s / samp
                f = math.sin(math.pi * u) ** 0.65 if s else 0.0
                th = rot + 2 * math.pi * (kk + u) / flutes
                rr = r - depth * f
                verts.append((rr * math.cos(th), rr * math.sin(th), z))
    for zi in range(len(zs) - 1):
        for i in range(N):
            a = zi * N + i
            b = zi * N + (i + 1) % N
            faces.append((a, b, b + N, a + N))
    c0 = len(verts); verts.append((0, 0, zs[0]))
    c1 = len(verts); verts.append((0, 0, zs[-1]))
    L = (len(zs) - 1) * N
    for i in range(N):
        faces.append((c0, (i + 1) % N, i))
        faces.append((c1, L + i, L + (i + 1) % N))
    return verts, faces

def column_base(rng, acc_extra):
    """받침: 네모 주춧돌 + 둥근 쇠시리 두 겹. 돌아오는 것: (블록 메쉬 bm 목록은 acc 에 넣고) 원형 부품 객체 목록"""
    bm = bm_box(0.86, 0.86, 0.36)
    stone_blk(bm, rng, (2, 4), (0.03, 0.09), 0.016, zmin=0.0)
    acc_extra.add(bm, TR((0, 0, 0.08)))
    parts = [torus(0.315, 0.06, (0, 0, 0.31), seg=56, minor=12),
             cyl(0.292, 0.09, (0, 0, 0.395), 56),
             torus(0.3, 0.042, (0, 0, 0.462), seg=56, minor=10)]
    return parts

def column_capital(rng, acc_extra, z0, breaks=((0.41, -0.41),)):
    """기둥머리: 고리띠 + 사발 모양 + 네모 판석 (모서리 깨짐)"""
    parts = [torus(0.252, 0.03, (0, 0, z0 + 0.02), seg=56, minor=10),
             cyl(0.255, 0.09, (0, 0, z0 + 0.075), 56),
             cyl(0.255, 0.17, (0, 0, z0 + 0.205), 56, r2=0.37)]
    bm = bm_box(0.82, 0.82, 0.22)
    bm_chip(bm, rng, 4, (0.03, 0.08))
    for cx, cy in breaks:
        bm_break(bm, rng, (cx * 0.5, cy * 0.5, rng.uniform(-0.03, 0.03)), (cx, cy, rng.uniform(-0.12, 0.12)), facets=3, spread=0.3, jitter=0.03)
    bm_bevel(bm, 0.016)
    acc_extra.add(bm, TR((0, 0, z0 + 0.4)))
    return parts

def shaft_spalls(rng, n, z0, z1, size=(0.06, 0.16), depth=(0.012, 0.03), avoid=None):
    """기둥 몸통 표면이 얇게 떨어져 나간 자국 커터 목록"""
    out = []
    for _ in range(n):
        th = rng.uniform(0, 6.28)
        if avoid is not None and abs(((th - avoid[0] + math.pi) % (2 * math.pi)) - math.pi) < avoid[1]:
            th += math.pi
        z = rng.uniform(z0, z1)
        r = _rf(z)
        nn = Vector((math.cos(th), math.sin(th), 0))
        a = rng.uniform(*size)
        out.append(spall_cutter(nn * r + Vector((0, 0, z)), nn, (a * rng.uniform(0.6, 0.9), a * rng.uniform(1.1, 1.8)), rng.uniform(*depth), rng))
    return out

def box_spalls(rng, n, half, zr, depth=(0.012, 0.03), size=(0.07, 0.16)):
    """네모 블록 옆면의 떨어져 나간 자국 (half: 반폭, zr: 높이 범위)"""
    out = []
    for _ in range(n):
        side = rng.randrange(4)
        nn = [Vector((1, 0, 0)), Vector((-1, 0, 0)), Vector((0, 1, 0)), Vector((0, -1, 0))][side]
        t = nn.cross(Vector((0, 0, 1)))
        p = nn * half + t * rng.uniform(-half * 0.85, half * 0.85) + Vector((0, 0, rng.uniform(*zr)))
        a = rng.uniform(*size)
        out.append(spall_cutter(p, nn, (a, a * rng.uniform(0.6, 1.2)), rng.uniform(*depth), rng))
    return out

def pillar_a():
    rng = random.Random(31)
    blocks = Acc()
    rings = column_base(rng, blocks)
    zs = [0.5, 1.22, 1.95, 2.66, 3.36]
    drums = []
    for i in range(4):
        v, f = fluted_drum(zs[i] + 0.002, zs[i + 1] - 0.002, rot=R(rng.uniform(-2.5, 2.5)))
        a = Acc()
        a.add_raw(v, f, TR((rng.uniform(-0.006, 0.006), rng.uniform(-0.006, 0.006), 0), (R(rng.uniform(-0.4, 0.4)), R(rng.uniform(-0.4, 0.4)), 0)))
        d = a.obj("drum")
        chip(d, rng, 4, (0.025, 0.05), sharp_deg=32, bite=0.3)
        drums.append(d)
    rings += column_capital(rng, blocks, 3.36, breaks=((0.41, -0.41), (-0.41, 0.41)))
    shaft = join(drums)
    # 몸통: 크게 떨어져 나간 자리 하나 + 얇게 벗겨진 자국 여럿
    th = R(-35)
    big = spall_cutter(Vector((math.cos(th), math.sin(th), 0)) * _rf(2.25) + Vector((0, 0, 2.25)), (math.cos(th), math.sin(th), 0), (0.2, 0.34), 0.065, rng)
    cut(shaft, [big] + shaft_spalls(rng, 9, 0.6, 3.3))
    blk = blocks.obj("pillar_blocks")
    cut(blk, box_spalls(rng, 6, 0.43, (-0.02, 0.2)) + box_spalls(rng, 4, 0.41, (3.79, 3.92), size=(0.06, 0.12)))
    for r_ in rings:
        chip(r_, rng, 4, (0.04, 0.08), sharp_deg=25, bite=0.35)
    body = join([shaft, blk] + rings)
    sculpt(body, 0.007, STONE_LAYERS(1.2, wear=1.4, cracks=0.7), seed=3)
    set_mat(body, paint("pillar_a_src", 'stone', moss=0.7, streaks=0.7, dirt=0.75, edge=0.6))
    low = low_of(body, 6000)
    tgt = copy(low)
    v = Vine(random.Random(5), leaf=(0.05, 0.08), leaf_p=0.34)
    ivy_grow(v, tgt, (-0.3, -0.1, 0.56), seed=5, length=2.8, max_roots=6, gravity=0.15, adhesion=0.9)   # 몸통 한쪽을 타고 오른다
    ivy_grow(v, tgt, (-0.45, 0.2, 0.04), seed=9, length=1.3, max_roots=4)
    delete(tgt)
    print("IVY tris", v.tris())
    return finish("pillar_a", [body], [low], extras=v.objects(), size=1024, extr=0.035)


# ───────────────────────── 봉인의 제단 ─────────────────────────
def altar():
    rng = random.Random(77)
    # 단 높이 / 반지름: (바깥 r, 블록 안쪽 r, 아래 z, 위 z, 블록 수)
    tiers = [(3.0, 2.05, -0.14, 0.32, 22), (2.3, 1.35, 0.322, 0.62, 18), (1.6, 0.95, 0.622, 0.92, 14)]
    blocks = Acc()
    loose = []                      # 떨어져 나간 블록 (따로 조각)
    gap = 0.03
    for ti, (r1, r0, z0, z1, n) in enumerate(tiers):
        a_off = rng.uniform(0, 6.28)
        for i in range(n):
            a0 = a_off + 2 * math.pi * i / n + gap / (2 * r1)
            a1 = a_off + 2 * math.pi * (i + 1) / n - gap / (2 * r1)
            am = (a0 + a1) / 2
            zz1 = z1 + rng.uniform(-0.014, 0.0)
            bm = bm_sector(r0, r1 + rng.uniform(-0.015, 0.015), a0, a1, z0, zz1)
            stone_blk(bm, rng, (1, 3), (0.025, 0.08), 0.014, zmin=z0 + 0.05)
            dx, dy = math.cos(am), math.sin(am)
            # 맨 아래 단 앞왼쪽(약 215도): 블록 둘이 밀려나 기울고, 하나는 빠져 깨진 채 땅에 굴렀다
            deg = math.degrees(am) % 360
            if ti == 0 and 196 < deg < 214:
                loose.append(("missing", am, r1, z1))
                bm.free()
                continue
            if ti == 0 and (214 <= deg < 232 or 180 < deg <= 196):
                # 안쪽 아래 모서리를 축으로 바깥쪽이 가라앉게 기울인다 (안쪽이 위 단으로 파고들지 않게)
                push = rng.uniform(0.06, 0.12)
                c = Vector((dx * r0, dy * r0, z0))
                M = TR(c + Vector((dx * push, dy * push, -0.02))) @ Matrix.Rotation(R(rng.uniform(5, 8)), 4, Vector((-dy, dx, 0))) @ TR(-c)
                blocks.add(bm, M)
                continue
            M = Matrix.Rotation(R(rng.uniform(-0.5, 0.5)), 4, 'Z') @ TR((dx * rng.uniform(-0.008, 0.008), dy * rng.uniform(-0.008, 0.008), 0))
            blocks.add(bm, M)
    # 맨 위 단 안쪽 판석 (받침 둘레)
    for i in range(8):
        a0 = 2 * math.pi * i / 8 + 0.03
        a1 = 2 * math.pi * (i + 1) / 8 - 0.03
        bm = bm_sector(0.42, 0.95 - 0.015, a0, a1, 0.622, 0.915 + rng.uniform(-0.01, 0.004))
        stone_blk(bm, rng, (0, 2), (0.02, 0.05), 0.012, zmin=0.8)
        blocks.add(bm)
    tier_obj = blocks.obj("altar_tiers")
    chip(tier_obj, rng, 46, (0.04, 0.1), sharp_deg=35, bite=0.36, zmin=0.0)

    # 룬 고리 (맨 위 단: 두 겹 고리 사이에 글자 16개, 가운데 단: 고리 하나 + 눈금)
    cutters, glows = [], []
    for rr in (1.08, 1.47):
        cutters.append(ring_mesh(rr - 0.022, rr + 0.022, 0.89, 0.96, 128))
        glows.append(flat_ring(rr - 0.011, rr + 0.011, 0.92 + 0.004, 160))
    cutters.append(ring_mesh(1.95 - 0.02, 1.95 + 0.02, 0.59, 0.66, 144))
    glows.append(flat_ring(1.95 - 0.01, 1.95 + 0.01, 0.62 + 0.004, 192))
    gstrokes = []
    for k in range(16):
        th = 2 * math.pi * k / 16 + 0.1
        cen = Vector((1.275 * math.cos(th), 1.275 * math.sin(th), 0.92))
        t_dir = Vector((-math.sin(th), math.cos(th), 0)); v_dir = Vector((math.cos(th), math.sin(th), 0))
        st = glyph_strokes(rng.randrange(len(GLYPHS)), cen, t_dir, v_dir, Vector((0, 0, 1)), 0.065, 0.1)
        gstrokes += st
        for pa, pb in st:
            cutters.append(stroke_cutter(pa, pb, (0, 0, 1), 0.026, 0.022))
    for k in range(24):           # 가운데 단 고리의 눈금
        th = 2 * math.pi * k / 24
        pa = Vector((1.84 * math.cos(th), 1.84 * math.sin(th), 0.62)); pb = Vector((1.9 * math.cos(th), 1.9 * math.sin(th), 0.62))
        if k % 3 == 0:
            pa = Vector((1.76 * math.cos(th), 1.76 * math.sin(th), 0.62))
        gstrokes.append((pa, pb))
        cutters.append(stroke_cutter(pa, pb, (0, 0, 1), 0.022, 0.02))
    # 받침 둘레에서 마법진 안쪽 고리까지 뻗은 빛나는 봉인 금 (봉인이 깨지고 있다)
    crack_strokes = []
    for k in range(6):
        th = 2 * math.pi * k / 6 + rng.uniform(-0.35, 0.35)
        d = Vector((math.cos(th), math.sin(th), 0))
        pts = [d * 0.63 + Vector((0, 0, 0.92))]
        for j in range(5):
            d2 = (d + Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 0))).normalized()
            pts.append(pts[-1] + d2 * rng.uniform(0.07, 0.095))
        if k % 2 == 0:                       # 갈래
            q = pts[2]
            d3 = (d + Vector((-d.y, d.x, 0)) * rng.choice((-0.9, 0.9))).normalized()
            crack_strokes.append((q, q + d3 * 0.12))
        crack_strokes += list(zip(pts, pts[1:]))
    for a_, b_ in crack_strokes:
        cutters.append(stroke_cutter(a_, b_, (0, 0, 1), 0.024, 0.03))
    glows.append(stroke_glow(crack_strokes, (0, 0, 1), 0.011, lift=0.004))
    # 단 옆면·윗면이 얇게 떨어져 나간 자국
    for (rr, za, zb, cnt) in ((3.0, 0.04, 0.26, 12), (2.3, 0.38, 0.56, 7), (1.6, 0.68, 0.86, 5)):
        for _ in range(cnt):
            th = rng.uniform(0, 6.28)
            nn = Vector((math.cos(th), math.sin(th), 0))
            a = rng.uniform(0.1, 0.22)
            cutters.append(spall_cutter(nn * rr + Vector((0, 0, rng.uniform(za, zb))), nn, (a * 1.4, a), rng.uniform(0.015, 0.035), rng))
    for (r_a, r_b, z, cnt) in ((2.35, 2.95, 0.32, 7), (1.65, 1.85, 0.62, 3), (2.05, 2.25, 0.62, 3)):
        for _ in range(cnt):
            th = rng.uniform(0, 6.28)
            rr = rng.uniform(r_a, r_b)
            a = rng.uniform(0.1, 0.2)
            cutters.append(spall_cutter(Vector((rr * math.cos(th), rr * math.sin(th), z)), (0, 0, 1), (a * 1.3, a), rng.uniform(0.01, 0.022), rng))
    cut(tier_obj, cutters, voxel=0.011)
    glows.append(stroke_glow(gstrokes, (0, 0, 1), 0.012, lift=0.004))

    # 심 (블록 사이 줄눈 뒤를 막는다)
    cores = [cyl(2.95, 0.42, (0, 0, 0.06), 96), cyl(2.24, 0.34, (0, 0, 0.40), 80), cyl(1.54, 0.32, (0, 0, 0.73), 64)]

    # 빠진 블록 자리의 조각들과 주변 잔돌
    debris = Acc()
    for tag, am, r1, z1 in loose:
        dx, dy = math.cos(am), math.sin(am)
        for j in range(2):
            bm = bm_box(rng.uniform(0.35, 0.5), rng.uniform(0.3, 0.42), rng.uniform(0.22, 0.3))
            bm_break(bm, rng, (rng.uniform(0.1, 0.18), 0, 0), (1, rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3)), facets=3, spread=0.4)
            stone_blk(bm, rng, (2, 4), (0.03, 0.08), 0.014)
            p = Vector((dx * (r1 + 0.45 + j * 0.42), dy * (r1 + 0.45 + j * 0.42), 0.08)) + Vector((-dy, dx, 0)) * rng.uniform(-0.35, 0.35)
            debris.add(bm, TR(p, (R(rng.uniform(-25, 25)), R(rng.uniform(-25, 25)), rng.uniform(0, 6.28))))
    deb = debris.obj("altar_debris")
    pebbles = []
    for k in range(9):
        th = R(rng.uniform(170, 250)) if k < 6 else rng.uniform(0, 6.28)
        rr = rng.uniform(3.1, 3.7)
        s = rng.uniform(0.08, 0.18)
        pebbles.append(chunk((rr * math.cos(th), rr * math.sin(th), s * 0.3), (s, s * rng.uniform(0.7, 1.0), s * 0.7), rng, 9))
    tiers_hp = join([tier_obj, deb] + cores + pebbles)
    sculpt(tiers_hp, 0.011, STONE_LAYERS(1.3, wear=1.1, cracks=0.55), seed=7)
    set_mat(tiers_hp, paint("altar_tiers_src", 'stone', moss=0.8, streaks=0.5, ao=0.5, dirt=0.7))

    # ── 가운데 받침 (팔각) + 선돌 넷 ──
    ped = Acc()
    def octa(r, z0, z1, r_top=None):
        rt = r if r_top is None else r_top
        pts0 = [(r * math.cos(R(22.5 + 45 * i)), r * math.sin(R(22.5 + 45 * i))) for i in range(8)]
        bm = bm_poly(pts0, z0, z1, 'z')
        if r_top is not None:
            for v in bm.verts:
                if abs(v.co.z - z1) < 1e-6:
                    v.co.x *= rt / r; v.co.y *= rt / r
        return bm
    bm = octa(0.62, 0.917, 1.117); stone_blk(bm, rng, (2, 3), (0.03, 0.06), 0.014, zmin=1.0); ped.add(bm)
    bm = octa(0.5, 1.12, 1.217, 0.42); bm_bevel(bm, 0.01); ped.add(bm)
    bm = octa(0.36, 1.22, 1.857, 0.33); stone_blk(bm, rng, (1, 2), (0.02, 0.05), 0.012); ped.add(bm)
    bm = octa(0.4, 1.86, 1.937); bm_bevel(bm, 0.01); ped.add(bm)
    bm = octa(0.42, 1.94, 2.16, 0.58); stone_blk(bm, rng, (2, 3), (0.03, 0.07), 0.014, zmin=2.1); ped.add(bm)
    ped_obj = ped.obj("pedestal")
    pcut = [cyl(0.4, 0.3, (0, 0, 2.2), 32)]
    pstrokes = []
    for k in (6, 2, 0, 4):           # 앞(-Y), 뒤, 오른쪽, 왼쪽 면에 세로 룬
        th = R(45 * k)
        nrm = Vector((math.cos(th), math.sin(th), 0))
        apo = (0.36 + 0.33) / 2 * math.cos(R(22.5))
        cen = nrm * apo + Vector((0, 0, 1.54))
        st = glyph_strokes(rng.randrange(len(GLYPHS)), cen, Vector((-math.sin(th), math.cos(th), 0)), Vector((0, 0, 1)), nrm, 0.07, 0.17)
        pstrokes.append((st, nrm))
        for pa, pb in st:
            pcut.append(stroke_cutter(pa, pb, nrm, 0.026, 0.022))
    cut(ped_obj, pcut)
    for st, nrm in pstrokes:
        glows.append(stroke_glow(st, nrm, 0.012, lift=0.006))

    # 선돌: 45, 135, 315 도는 서 있고 225 도(앞왼쪽)는 부러져 땅에 누웠다
    stones = Acc()
    def standing(h=1.2):
        poly = [(-0.22, 0), (0.22, 0), (0.19, h * 0.78), (0.0, h), (-0.19, h * 0.78)]
        return bm_poly(poly, -0.13, 0.13, 'y')
    for deg in (45, 135, 315, 225):
        th = R(deg)
        p = Vector((2.66 * math.cos(th), 2.66 * math.sin(th), 0.312))
        M = TR(p, (0, 0, th + R(90)))
        if deg == 225:
            stub = standing()
            bm_break(stub, rng, (0, 0, 0.42), (0.3, 0.1, 1), facets=3, spread=0.35)
            stone_blk(stub, rng, (1, 2), (0.03, 0.06), 0.012)
            stones.add(stub, M)
            top = standing()
            bm_break(top, rng, (0, 0, 0.5), (-0.3, -0.1, -1), facets=3, spread=0.35)
            stone_blk(top, rng, (2, 3), (0.03, 0.07), 0.012)
            # 바깥쪽 땅에 눕힌다 (글자 면이 위로)
            q = Vector((3.45 * math.cos(th + 0.12), 3.45 * math.sin(th + 0.12), 0.1))
            stones.add(top, TR(q, (0, 0, th + R(90))) @ Matrix.Rotation(R(84), 4, 'X') @ TR((0, 0, -0.85)))
            continue
        bm = standing(rng.uniform(1.12, 1.28))
        if deg == 315:
            bm_break(bm, rng, (0.1, 0, 0.98), (0.6, 0.1, 1), facets=2, spread=0.3)
        stone_blk(bm, rng, (2, 4), (0.03, 0.07), 0.012, zmin=0.3)
        stones.add(bm, M)
        st = glyph_strokes(rng.randrange(len(GLYPHS)), (0, -0.13, 0.62), Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0)), 0.08, 0.2)
        # 획을 선돌 자리로 옮긴다 (바깥을 향하는 면)
        st = [(M @ pa, M @ pb) for pa, pb in st]
        nrm = (M.to_3x3() @ Vector((0, -1, 0))).normalized()
        pstrokes.append((st, nrm))
        glows.append(stroke_glow(st, nrm, 0.014, lift=0.006))
        stones_cut = [stroke_cutter(pa, pb, nrm, 0.028, 0.024) for pa, pb in st]
        loose.append(("cut", stones_cut))
    st_obj = stones.obj("stones")
    cut(st_obj, [c for t in loose if t[0] == "cut" for c in t[1]])
    deco = join([ped_obj, st_obj])
    sculpt(deco, 0.007, STONE_LAYERS(1.0, wear=1.0, cracks=0.5), seed=11)
    set_mat(deco, paint("altar_deco_src", 'stone_pale', moss=0.45, streaks=0.5))

    # 영혼 수정 다발 (받침 위) + 틈에서 돋은 작은 수정
    cv, cf = [], []
    def add_crystal(base, dirv, length, radius):
        v, f = crystal(base, dirv, length, radius, rng)
        off = len(cv); cv.extend(v); cf.extend(tuple(off + i for i in fc) for fc in f)
    add_crystal((0, 0, 2.0), (0.03, -0.02, 1), 1.35, 0.13)
    add_crystal((0.06, 0.05, 2.0), (0.25, 0.2, 1), 0.95, 0.1)
    for k in range(6):
        th = 2 * math.pi * k / 5 + rng.uniform(-0.3, 0.3)
        out = Vector((math.cos(th), math.sin(th), 0))
        add_crystal(Vector((0, 0, 2.02)) + out * rng.uniform(0.1, 0.17), out * rng.uniform(0.35, 0.6) + Vector((0, 0, 1)), rng.uniform(0.45, 0.78), rng.uniform(0.06, 0.085))
    for k in range(9):
        th = 2 * math.pi * k / 9 + rng.uniform(-0.3, 0.3)
        out = Vector((math.cos(th), math.sin(th), 0))
        add_crystal(Vector((0, 0, 2.08)) + out * rng.uniform(0.22, 0.34), out * rng.uniform(0.9, 1.5) + Vector((0, 0, 1)), rng.uniform(0.2, 0.42), rng.uniform(0.035, 0.055))
    for (deg, rr, z) in ((205, 2.55, 0.3), (231, 2.5, 0.3), (120, 1.9, 0.6), (300, 1.25, 0.9)):
        th = R(deg)
        b = Vector((rr * math.cos(th), rr * math.sin(th), z))
        for k in range(rng.randint(3, 4)):
            dv = Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 1))
            add_crystal(b + Vector((rng.uniform(-0.06, 0.06), rng.uniform(-0.06, 0.06), -0.02)), dv, rng.uniform(0.12, 0.3), rng.uniform(0.025, 0.04))
    glows.append(glow_obj(cv, cf))
    for g in glows:
        if g is not None and not g.data.materials:
            glow(g, 'Glow_Soul')

    low_t = low_of(tiers_hp, 15500, z=-0.04)
    low_d = low_of(deco, 5500, z=-0.04)
    return finish("altar", [tiers_hp, deco], [low_t, low_d], extras=glows, size=2048, extr=0.05, lod1=0.35, lod2=0.12)


# ───────────────────────── 무너진 벽 ─────────────────────────
def top_rubble(rng, top, x0, x1, y0, y1, n, M=None, keep=None):
    """무너진 윗면(심) 위에 얹힌 잔돌 덩어리 (심이 매끈한 경사로 보이지 않게 촘촘히).
    keep(x, z): False 면 그 자리는 건너뛴다 (아래에 받쳐 줄 심이 없는 곳)"""
    out = []
    for i in range(n):
        x = x0 + (x1 - x0) * (i + rng.random()) / n
        s_ = rng.uniform(0.1, 0.22)
        if keep is not None and not keep(x, top(x) - 0.13):
            continue
        p = Vector((x, rng.uniform(y0 + 0.14, y1 - 0.14), top(x) - 0.13 + s_ * 0.25))
        c = chunk((0, 0, 0), (s_, s_ * rng.uniform(0.6, 0.9), s_ * 0.6), rng, 8)
        c.data.transform((M if M is not None else Matrix.Identity(4)) @ Matrix.Translation(p))
        c.data.update()
        out.append(c)
    return out

def wall_ruin_a():
    """무너진 벽 (뾰족 창). v3: 블록마다 색조, 평면 끌 자국, 잔 조각 전 바탕에서 저폴리, paint3, cage 굽기 2048"""
    rng = random.Random(101)
    y0, y1 = -0.4, 0.4
    top = profile([(-2.25, 1.95), (-1.95, 2.5), (-1.5, 2.9), (-1.0, 3.18), (-0.4, 3.22), (0.05, 2.98), (0.35, 2.5),
                   (0.7, 2.25), (1.0, 1.6), (1.4, 1.35), (1.8, 0.95), (2.25, 0.72)])
    zs = [-0.14, 0.3] + courses(rng, 0.3, 3.4)[1:]
    # 고딕 뾰족 창
    wx, W, sill, h_s, rise, T, gap = -0.8, 0.8, 1.0, 1.72, 0.92, 0.3, 0.026      # 폭보다 높이 솟은 뾰족(랜싯) 창
    Mw = TR((wx, 0, 0))
    blocks = Acc()
    ashlar(blocks, rng, -2.25, 2.25, zs, top, y0, y1, gap=gap, ragged=(0.28, 0.22), plinth=0.045, missing=0.03,
           damage=(0.14, random.Random(707)))       # v3b: 깨지고 이 빠진 블록 (v3 에서 너무 깨끗해 새 벽돌 같았다)
    bo = blocks.obj("wall_blocks")
    cut(bo, zone_prism(arch_outline(W, h_s, rise, grow=T + gap, z_bottom=sill - 0.16 - gap), y0, y1, Mw), voxel=0.011)
    frame = Acc()
    jamb_stones(frame, rng, W, sill, h_s, T, y0 - 0.01, y1 + 0.01, gap, M=Mw)
    for tag, bm, c in arch_stones(rng, W, h_s, rise, T, 4, y0 - 0.01, y1 + 0.01, gap, chips=(1, 2)):
        Mv = Mw
        if tag == 101:                                   # 왼쪽 홍예석 하나가 조금 내려앉았다
            Mv = Mw @ TR(c + Vector((0, 0, -0.035))) @ Matrix.Rotation(R(-3), 4, 'Y') @ TR(-c)
        frame.add(bm, Mv)
    bm = bm_box(W + 2 * T + 0.06, (y1 - y0) + 0.08, 0.16)
    stone_blk(bm, rng, (2, 3), (0.03, 0.07), 0.014)
    frame.add(bm, TR((wx, -0.03, sill - 0.08 - 0.004)))
    fo = frame.obj("wall_frame")
    core = Acc()
    core.add(core_prism(-2.25, 2.25, top, y0, y1, -0.14))
    co = core.obj("wall_core")
    cut(co, zone_prism(arch_outline(W, h_s, rise, grow=0.012, z_bottom=sill - 0.004), y0, y1, Mw), voxel=0.011)
    # 무너져 내린 블록들 (오른쪽 앞뒤) + 윗면 잔돌
    fallen = Acc()
    for (x, y, sz) in ((1.2, -0.85, (0.62, 0.36, 0.3)), (1.85, -0.75, (0.5, 0.34, 0.3)), (0.6, -0.7, (0.4, 0.32, 0.28)),
                       (1.5, 0.85, (0.58, 0.35, 0.3)), (2.05, 0.7, (0.45, 0.3, 0.28)), (0.95, -1.25, (0.32, 0.26, 0.22))):
        fallen_block(fallen, rng, (x, y, 0), sz)
    ext = []
    rubble_pile(fallen, rng, (1.5, -0.68, 0), 0.6, 12, (0.14, 0.32), 0.42, extra=ext)
    fa = fallen.obj("wall_fallen")
    rub = top_rubble(rng, top, -2.05, 2.1, y0, y1, 34)
    body = join([bo, fo, co, fa] + rub + ext)
    # v3: 블록마다 번호(색조) → 되붙인 리메시 → STONE3(평면 끌 자국·곧은 금) / 저폴리는 잔 조각 전 바탕에서 / paint3 / cage 굽기
    base = carve(body, 0.009, *STONE3(1.25, wear=1.2, cracks=0.6), seed=21, base=True)
    # v3b 칠: 블록마다 밝기 ±15%·따뜻한/차가운 색조, 닳은 모서리 더 밝고 넓게, 줄눈 아래 흙물·그을음, 오목한 곳 AO, 이끼 포인트
    set_mat(body, paint3("wall_ruin_a_src", 'stone', h=3.2, k=1.25, moss=0.75, moss_patch=3.2, moss_low=0.7, moss_low_h=0.7, dirt=0.75,
                         dirt_h=0.4, streaks=0.7, edge=1.0, edge_w=0.022, edge_gain=1.35, piece_var=1.0, piece_val=0.15, grime=0.85,
                         grime_h=0.16, cavity=1.0, ao=0.45, stains=0.5, lichen=0.4, contrast=0.2, gain=1.2))   # gain: 게임 시점 밝기 이전 ±10%
    low = low_of(base, 11500)
    delete(base)
    tgt = copy(low)
    v = Vine(random.Random(8), leaf=(0.05, 0.08), leaf_p=0.42)
    ivy_grow(v, tgt, (-1.95, y0 - 0.03, 0.05), seed=8, length=3.0, max_roots=9)
    ivy_grow(v, tgt, (0.55, y0 - 0.03, 0.05), seed=12, length=1.5, max_roots=5)
    ivy_grow(v, tgt, (-1.2, y1 + 0.03, 0.05), seed=14, length=2.0, max_roots=5)
    delete(tgt)
    for x, ln in ((-1.62, 1.1), (-0.15, 0.9), (0.2, 0.55)):
        hang_strand(v, (x, y0 - 0.02, top(x) - 0.06), ln, rng)
    print("IVY tris", v.tris())
    return finish3("wall_ruin_a", [body], [low], extras=v.objects(), size=2048, cage=0.01, cage_reach=0.1, lod1=0.35, lod2=0.12,
                   uv_margin=0.001)

def wall_ruin_b():
    rng = random.Random(202)
    gap = 0.028
    # 벽 A: 뒤쪽 (x 방향), 벽 B: 왼쪽 (y 방향, 안쪽 면이 +x)
    MA = TR((0, 1.15, 0))
    MB = TR((-1.15, -0.35, 0)) @ Matrix.Rotation(R(90), 4, 'Z')
    topA = profile([(-1.5, 1.85), (-1.15, 2.05), (-0.75, 1.75), (-0.35, 1.45), (0.1, 1.05), (0.6, 0.85), (1.0, 0.6), (1.5, 0.42)])
    topB = profile([(-1.15, 0.38), (-0.7, 0.62), (-0.25, 0.95), (0.25, 1.15), (0.7, 1.55), (1.13, 1.8)])
    blocks = Acc()
    zsA = [-0.14, 0.26] + courses(rng, 0.26, 2.2)[1:]
    zsB = [-0.14, 0.26] + courses(rng, 0.26, 2.0)[1:]
    ashlar(blocks, rng, -1.5, 1.5, zsA, topA, -0.35, 0.35, gap=gap, ragged=(0.0, 0.25), plinth=0.04, M=MA)
    ashlar(blocks, rng, -1.15, 1.13, zsB, topB, -0.35, 0.35, gap=gap, ragged=(0.25, 0.0), plinth=0.04, M=MB)
    bo = blocks.obj("wallb_blocks")
    core = Acc()
    core.add(core_prism(-1.5, 1.5, topA, -0.35, 0.35, -0.14), MA)
    core.add(core_prism(-1.15, 1.2, topB, -0.35, 0.35, -0.14), MB)
    co = core.obj("wallb_core")
    pile = Acc()
    ext = []
    rubble_pile(pile, rng, (-0.45, 0.3, 0), 0.8, 22, (0.14, 0.36), 0.75, extra=ext)
    for (x, y, sz) in ((0.35, -0.2, (0.5, 0.34, 0.28)), (-0.2, -0.7, (0.42, 0.32, 0.26)), (0.9, 0.3, (0.46, 0.33, 0.27))):
        fallen_block(pile, rng, (x, y, 0), sz)
    po = pile.obj("wallb_pile")
    rub = top_rubble(rng, topA, -1.35, 1.4, -0.35, 0.35, 20, MA) + top_rubble(rng, topB, -1.05, 1.05, -0.35, 0.35, 16, MB)
    body = join([bo, co, po] + rub + ext)
    sculpt(body, 0.01, STONE_LAYERS(1.2, wear=1.35, cracks=0.6), seed=23)
    set_mat(body, paint("wall_ruin_b_src", 'stone', moss=0.85, dirt=0.75, streaks=0.7, ao=0.45))
    low = low_of(body, 6600)
    tgt = copy(low)
    v = Vine(random.Random(4), leaf=(0.05, 0.08), leaf_p=0.4)
    ivy_grow(v, tgt, (-0.85, 0.7, 0.05), seed=4, length=2.2, max_roots=7)
    ivy_grow(v, tgt, (1.1, 0.75, 0.05), seed=6, length=1.2, max_roots=4)
    delete(tgt)
    print("IVY tris", v.tris())
    return finish("wall_ruin_b", [body], [low], extras=v.objects(), size=2048, extr=0.05, lod1=0.35, lod2=0.12)


# ───────────────────────── 부서진 뾰족 아치 문 ─────────────────────────
def pier(acc, rng, x0, x1, y0, y1, zs, gap=0.026, plinth=0.06, skip_top=None):
    """아치 다리 (켜마다 통돌 하나 또는 둘로 번갈아)"""
    for k in range(len(zs) - 1):
        za, zb = zs[k], zs[k + 1] - gap
        pr = plinth if k == 0 else 0.0
        if skip_top is not None and za > skip_top:
            continue
        if k % 2 == 0:
            pieces = [(x0 - pr, x1 + pr, y0 - pr, y1 + pr)]
        else:
            ym = (y0 + y1) / 2 + rng.uniform(-0.1, 0.1)
            pieces = [(x0, x1, y0, ym - gap / 2), (x0, x1, ym + gap / 2, y1)]
        for (xa, xb, ya, yb) in pieces:
            bm = bm_box(xb - xa - gap, yb - ya, zb - za)
            stone_blk(bm, rng, (1, 3), (0.02, 0.07), 0.014)
            acc.add(bm, TR(((xa + xb) / 2 + rng.uniform(-0.006, 0.006), (ya + yb) / 2 + rng.uniform(-0.008, 0.008), (za + zb) / 2),
                            (0, 0, R(rng.uniform(-0.6, 0.6)))))

def arch_ruin():
    rng = random.Random(303)
    y0, y1 = -0.45, 0.45
    W, h_s, rise, T, gap = 2.4, 2.6, 2.0, 0.38, 0.026          # 폭 2.4 에 2.0 솟은 뾰족 아치 (꼭대기 바깥 약 5m)
    blocks = Acc()
    zs = [-0.14, 0.3] + courses(rng, 0.3, 2.42, (0.3, 0.4))[1:]
    zs[-1] = 2.42
    pier(blocks, rng, -2.0, -1.2, y0, y1, zs)
    pier(blocks, rng, 1.2, 2.0, y0, y1, zs)
    # 아치가 시작되는 곳의 띠돌 (튀어나온 받침)
    for sx in (-1, 1):
        bm = bm_box(0.96, 1.02, 0.18)
        stone_blk(bm, rng, (2, 4), (0.03, 0.07), 0.014)
        blocks.add(bm, TR((sx * 1.6 + sx * 0.04, 0, 2.42 + 0.09)))
    # 홍예석: 오른쪽 위에서 하나가 빠졌고, 그 위의 것은 조금 내려앉았다
    for tag, bm, c in arch_stones(rng, W, h_s, rise, T, 7, y0 + 0.03, y1 - 0.03, gap, skip=(5,), chips=(1, 3)):
        M = Matrix.Identity(4)
        if tag == 6:
            M = TR(c + Vector((0, 0, -0.06))) @ Matrix.Rotation(R(4), 4, 'Y') @ TR(-c)
        blocks.add(bm, M)
    # 아치 위 벽(스팬드럴): 왼쪽은 높게 남고 오른쪽은 무너졌다
    top = profile([(-2.0, 5.12), (-1.4, 5.18), (-0.8, 5.08), (-0.3, 4.95), (0.15, 4.55), (0.6, 3.95), (1.2, 3.35), (2.0, 2.95)])
    zs2 = [2.6] + courses(rng, 2.6, 5.3, (0.28, 0.36))[1:]
    # 홍예석 사이 줄눈 뒤를 막는 얇은 심 (빠진 돌 자리는 비워 둔다)
    for tag, bm, c in arch_stones(random.Random(1), W, h_s, rise, T - 0.06, 7, -0.16, 0.16, 0.0, skip=(5,), chips=(0, 0)):
        blocks.add(bm, TR((0, 0, 0)) @ Matrix.Identity(4))
    span = Acc()
    ashlar(span, rng, -2.0, 2.0, zs2, top, y0 + 0.03, y1 - 0.03, gap=gap, ragged=(0.0, 0.0), missing=0.02, skin=(0.32, 0.4))
    so = span.obj("arch_span")
    cut(so, zone_prism(arch_outline(W, h_s, rise, grow=T + gap, z_bottom=-0.5), y0, y1), voxel=0.012)
    core = Acc()
    core.add(core_prism(-2.0, 2.0, top, y0 + 0.03, y1 - 0.03, 2.6))
    core.add(bm_box(0.7, 0.8, 2.5), TR((-1.6, 0, 1.17)))
    core.add(bm_box(0.7, 0.8, 2.5), TR((1.6, 0, 1.17)))
    co = core.obj("arch_core")
    cut(co, zone_prism(arch_outline(W, h_s, rise, grow=T + gap, z_bottom=-0.5), y0, y1), voxel=0.012)
    # 떨어진 홍예석 (둘로 깨져 아치 아래 땅에), 잔돌
    fallen = Acc()
    fallen_block(fallen, rng, (0.45, -0.4, 0), (0.4, 0.62, 0.34), rot_z=R(70))
    fallen_block(fallen, rng, (0.95, 0.2, 0), (0.32, 0.5, 0.3), rot_z=R(20))
    fallen_block(fallen, rng, (-0.4, -0.95, 0), (0.36, 0.3, 0.26))
    ext = []
    rubble_pile(fallen, rng, (0.8, -0.1, 0), 0.65, 12, (0.12, 0.28), 0.35, extra=ext)
    fa = fallen.obj("arch_fallen")
    bo = blocks.obj("arch_blocks")
    cx_, r_, _ = arch_geo(W, h_s, rise)
    def outside_arch(x, z):
        if z < h_s:
            return abs(x) > W / 2 + T + 0.08
        return (Vector((abs(x), z)) - Vector((cx_, h_s))).length > r_ + T + 0.08
    rub = top_rubble(rng, top, -1.95, 1.95, y0, y1, 26, keep=outside_arch)
    body = join([bo, so, co, fa] + rub + ext)
    sculpt(body, 0.012, STONE_LAYERS(1.3, wear=1.3, cracks=0.6), seed=31)
    set_mat(body, paint("arch_ruin_src", 'stone', moss=0.8, dirt=0.7, streaks=0.8, ao=0.5))
    low = low_of(body, 15000)
    tgt = copy(low)
    v = Vine(random.Random(3), leaf=(0.05, 0.085), leaf_p=0.42)
    ivy_grow(v, tgt, (-2.05, -0.2, 0.05), seed=3, length=3.6, max_roots=9)
    ivy_grow(v, tgt, (-1.15, -0.47, 0.05), seed=7, length=1.8, max_roots=5)
    delete(tgt)
    # 아치 안쪽 아래면에서 늘어진 덩굴
    cx, r, a_end = arch_geo(W, h_s, rise)
    for deg, ln in ((-30, 1.2), (-48, 0.9), (-62, 1.1), (22, 0.7)):
        a = R(abs(deg))
        sx = -1 if deg < 0 else 1
        x, z = sx * (cx + r * math.cos(a)), h_s + r * math.sin(a)
        for yy in (y0 + 0.08,):
            hang_strand(v, (x * 0.98, yy, z - 0.02), ln * rng.uniform(0.7, 1.1), rng, face=(-sx * 0.3, -1, 0))
    print("IVY tris", v.tris())
    return finish("arch_ruin", [body], [low], extras=v.objects(), size=2048, extr=0.06, lod1=0.35, lod2=0.12)


# ───────────────────────── 무너진 돌계단 ─────────────────────────
def crack_cutters(rng, p0, direction, length, normal=(0, 0, 1), width=0.014, depth=0.025, segs=5):
    """구불구불한 금 하나 (짧은 획을 이어 붙인다)"""
    out = []
    d = Vector(direction).normalized()
    n = Vector(normal).normalized()
    side = n.cross(d).normalized()
    p = Vector(p0)
    for i in range(segs):
        q = p + d * (length / segs) + side * rng.uniform(-0.04, 0.04)
        out.append(stroke_cutter(p, q, n, width * rng.uniform(0.7, 1.2), depth))
        p = q
    return out

def stair_ruin():
    rng = random.Random(404)
    n_st, rise_, tread = 8, 0.1875, 0.32
    y_front = -1.32
    xs_in = (-1.2, 1.2)
    steps = Acc()
    crack_list = []
    for i in range(n_st):
        z1 = (i + 1) * rise_
        ya = y_front + i * tread
        yb = ya + (tread + 0.06 if i < n_st - 1 else 0.6)
        x = xs_in[0]
        first = True
        while x < xs_in[1] - 0.1:
            L = rng.uniform(0.62, 1.15) * (rng.uniform(0.5, 1.0) if first else 1.0)
            first = False
            xb = min(xs_in[1], x + L)
            if xs_in[1] - xb < 0.3:
                xb = xs_in[1]
            xm = (x + xb) / 2
            # 오른쪽 위 계단 덩어리가 떨어져 나갔다
            if i >= 5 and xm > 0.25:
                x = xb
                continue
            bm = bm_box(xb - x - 0.026, yb - ya, 0.22)
            if i == 4 and xm > 0.25:
                bm_break(bm, rng, (-(xb - x) * 0.1, 0.02, 0), (1, 0.6, 0.3), facets=3, spread=0.4)
            if i == 3 and xm > 0.4:
                bm_break(bm, rng, ((xb - x) * 0.25, 0.08, 0), (1, 0.8, 0.2), facets=2, spread=0.35)
            # 앞 모서리(디딤판 코)가 많이 닳고 깨졌다
            bm_chip(bm, rng, rng.randint(2, 4), (0.025, 0.07), zmin=0.0)
            bm_bevel(bm, 0.016)
            steps.add(bm, TR((xm, (ya + yb) / 2, z1 - 0.11 + rng.uniform(-0.012, 0.0)), (R(rng.uniform(-0.8, 0.8)), R(rng.uniform(-0.8, 0.8)), R(rng.uniform(-0.5, 0.5)))))
            if rng.random() < 0.35:
                crack_list += crack_cutters(rng, (rng.uniform(x + 0.1, xb - 0.1), ya + 0.01, z1), (rng.uniform(-0.4, 0.4), 1, 0), tread * rng.uniform(0.6, 1.0), segs=4)
            x = xb
    so = steps.obj("stair_steps")
    # 디딤판 앞 모서리를 따라 얇게 떨어져 나간 자국
    sp = []
    for i in range(n_st):
        for _ in range(2):
            x = rng.uniform(-1.1, 1.1)
            if i >= 5 and x > 0.25:
                continue
            p = Vector((x, y_front + i * tread, (i + 1) * rise_ - 0.03))
            sp.append(spall_cutter(p, (0, -1, 0.6), (rng.uniform(0.12, 0.24), 0.08), 0.025, rng))
    cut(so, sp + crack_list, voxel=0.01)
    # 양옆 난간벽 (계단 경사를 따라, 오른쪽은 위쪽이 무너졌다)
    side = Acc()
    for sx in (-1, 1):
        M = TR((sx * 1.36, 0, 0)) @ Matrix.Rotation(R(90), 4, 'Z')
        if sx < 0:
            topf = profile([(-1.4, 0.55), (-0.6, 0.95), (0.2, 1.55), (0.9, 2.0), (1.35, 2.1), (1.6, 1.85)])
        else:
            topf = profile([(-1.4, 0.5), (-0.7, 0.9), (-0.2, 1.15), (0.2, 0.75), (0.8, 0.55), (1.6, 0.4)])
        zs = [-0.12, 0.28] + courses(rng, 0.28, 2.3, (0.26, 0.34))[1:]
        ashlar(side, rng, -1.4, 1.6, zs, topf, -0.14, 0.14, gap=0.026, blen=(0.4, 0.7), skin=(0.12, 0.13), ragged=(0.0, 0.1), missing=0.0, M=M)
        side.add(core_prism(-1.4, 1.6, topf, -0.14, 0.14, -0.12, inset=0.035), M)
    so2 = side.obj("stair_sides")
    # 계단 밑 심: 왼쪽은 계단 모양, 오른쪽 위는 무너진 경사
    core = Acc()
    prof = [(y_front + 0.04, -0.12)]
    for i in range(n_st):
        prof += [(y_front + i * tread + 0.04, (i + 1) * rise_ - 0.06), (y_front + (i + 1) * tread + 0.04, (i + 1) * rise_ - 0.06)]
    prof += [(1.48, n_st * rise_ - 0.06), (1.48, -0.12)]
    # 단면(YZ)을 XZ 다각형으로 만든 뒤 Z 축으로 90도 돌린다: 월드 y = 다각형 x, 월드 x = -(늘인 방향)
    Rz = Matrix.Rotation(R(90), 4, 'Z')
    core.add(bm_poly(prof, -0.24, 1.22, 'y'), Rz)                       # 왼쪽 (월드 x -1.22 ~ 0.24): 계단 모양
    y4 = y_front + 4 * tread
    profR = [(y, z if y < y4 else min(z, 0.66 + (y - y4) * 0.15)) for y, z in prof]
    core.add(bm_poly(profR, -1.22, -0.24, 'y'), Rz)                      # 오른쪽 (월드 x 0.24 ~ 1.22): 무너진 경사
    co = core.obj("stair_core")
    fallen = Acc()
    fallen_block(fallen, rng, (1.0, -1.85, 0), (0.75, 0.36, 0.22), rot_z=R(12))
    fallen_block(fallen, rng, (1.85, -1.2, 0), (0.6, 0.34, 0.22), rot_z=R(75))
    ext = []
    # 무너진 오른쪽 위: 심이 매끈한 경사로 보이지 않게 깨진 판석 조각과 잔돌로 덮는다
    def slope_z(y):
        return min((min(n_st, max(1, int((y - y_front) / tread) + 1))) * rise_, 0.72 + max(0.0, y - y4) * 0.15) - 0.06
    for k in range(30):
        x = rng.uniform(0.32, 1.15)
        y = rng.uniform(y4 - 0.05, 1.42)
        g = rng.uniform(0.08, 0.17)
        q = chunk((0, 0, 0), (g, g * 0.8, g * 0.55), rng, 8)
        q.data.transform(Matrix.Translation((x, y, slope_z(y) + g * 0.2)))
        ext.append(q)
    for k in range(5):
        x = rng.uniform(0.45, 1.0)
        y = y4 + 0.15 + k * 0.28 + rng.uniform(-0.05, 0.05)
        bm = bm_box(rng.uniform(0.4, 0.7), rng.uniform(0.25, 0.36), 0.18)
        bm_break(bm, rng, (rng.uniform(0.05, 0.15), 0, 0), (1, rng.uniform(-0.5, 0.5), rng.uniform(-0.4, 0.4)), facets=3, spread=0.45)
        stone_blk(bm, rng, (2, 4), (0.03, 0.07), 0.014)
        fallen.add(bm, TR((x, y, slope_z(y) + 0.06), (R(rng.uniform(-25, 25)), R(rng.uniform(-25, 25)), rng.uniform(0, 6.28))))
    rubble_pile(fallen, rng, (0.72, 0.65, 0.62), 0.48, 12, (0.12, 0.28), 0.3, extra=ext)
    rubble_pile(fallen, rng, (1.05, -1.55, 0), 0.4, 6, (0.12, 0.24), 0.25, extra=ext)
    fa = fallen.obj("stair_fallen")
    body = join([so, so2, co, fa] + ext)
    sculpt(body, 0.01, STONE_LAYERS(1.2, wear=1.3, cracks=0.65), seed=41)
    set_mat(body, paint("stair_ruin_src", 'stone', moss=0.85, dirt=0.7, streaks=0.6, ao=0.45))
    low = low_of(body, 10000)
    tgt = copy(low)
    v = Vine(random.Random(2), leaf=(0.045, 0.07), leaf_p=0.5)
    ivy_grow(v, tgt, (-1.52, -1.0, 0.05), seed=2, length=2.0, max_roots=10)
    ivy_grow(v, tgt, (1.0, 0.2, 0.6), seed=5, length=1.2, max_roots=6)
    delete(tgt)
    print("IVY tris", v.tris())
    return finish("stair_ruin", [body], [low], extras=v.objects(), size=2048, extr=0.05, lod1=0.35, lod2=0.12)


# ───────────────────────── 쇠붙이 (울타리·문·등불) ─────────────────────────
RUST = ((0.016, 0.012, 0.014), (0.085, 0.047, 0.038), (0.24, 0.19, 0.19))     # 검게 삭은 쇠 + 녹 얼룩: 어두운, 밝은(녹), 닳은 모서리

def _frame(d, ref=(0, 1, 0)):
    d = Vector(d).normalized()
    s1 = d.cross(Vector(ref))
    if s1.length < 1e-4:
        s1 = d.orthogonal()
    s1.normalize()
    return d, s1, d.cross(s1).normalized()

def bar_path(pts, w, dep=None, ref=(0, 1, 0)):
    """경로를 따라가는 사각 쇠막대 (저폴리). 돌아오는 것: verts, faces"""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    hw, hd = w / 2, (dep if dep is not None else w) / 2
    verts, faces = [], []
    for i, p in enumerate(pts):
        d, s1, s2 = _frame(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)], ref)
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(p + s1 * (a * hw) + s2 * (b * hd))
    for i in range(n - 1):
        for k in range(4):
            a = i * 4 + k
            b = i * 4 + (k + 1) % 4
            faces.append((a, b, b + 4, a + 4))
    faces.append((3, 2, 1, 0))
    L = (n - 1) * 4
    faces.append((L, L + 1, L + 2, L + 3))
    return verts, faces

def spear(base, direction, h=0.14, w=0.055, t=0.014, neck=0.012, ref=(0, 1, 0)):
    """창끝 (넓적한 마름모 촉)"""
    d, s1, s2 = _frame(direction, ref)
    b = Vector(base)
    verts = [b + s1 * (a * neck) + s2 * (c * neck) for a, c in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    m = b + d * (h * 0.38)
    verts += [m - s1 * (w / 2), m - s2 * (t / 2), m + s1 * (w / 2), m + s2 * (t / 2)]
    verts.append(b + d * h)
    faces = [(3, 2, 1, 0)]
    for k in range(4):
        faces.append((k, (k + 1) % 4, 4 + (k + 1) % 4, 4 + k))
        faces.append((4 + k, 4 + (k + 1) % 4, 8))
    return verts, faces

def lathe(profile, seg=20, center=(0, 0, 0)):
    """(반지름, 높이) 윤곽을 돌려 만든 회전체 (항아리 등)"""
    c = Vector(center)
    verts, faces = [], []
    rows = []
    for r, z in profile:
        if r < 1e-5:
            rows.append([len(verts)])
            verts.append(c + Vector((0, 0, z)))
        else:
            row = []
            for i in range(seg):
                a = 2 * math.pi * i / seg
                row.append(len(verts))
                verts.append(c + Vector((r * math.cos(a), r * math.sin(a), z)))
            rows.append(row)
    for ra, rb in zip(rows, rows[1:]):
        if len(ra) == 1 and len(rb) > 1:
            for i in range(seg):
                faces.append((ra[0], rb[(i + 1) % seg], rb[i]))
        elif len(rb) == 1 and len(ra) > 1:
            for i in range(seg):
                faces.append((ra[i], ra[(i + 1) % seg], rb[0]))
        elif len(ra) > 1 and len(rb) > 1:
            for i in range(seg):
                faces.append((ra[i], ra[(i + 1) % seg], rb[(i + 1) % seg], rb[i]))
    return verts, faces

def torus_raw(R_, r, M, seg=10, minor=4):
    verts, faces = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(minor):
            b = 2 * math.pi * j / minor
            rr = R_ + r * math.cos(b)
            verts.append(M @ Vector((rr * math.cos(a), rr * math.sin(a), r * math.sin(b))))
    for i in range(seg):
        for j in range(minor):
            a = i * minor + j
            b = i * minor + (j + 1) % minor
            c = ((i + 1) % seg) * minor + (j + 1) % minor
            d = ((i + 1) % seg) * minor + j
            faces.append((a, b, c, d))
    return verts, faces

def iron_high(low_obj, voxel=0.0035, seed=0):
    """쇠 부품 고폴리: 저폴리를 복사해 리메시하고 두들긴 자국·녹 구멍을 새긴다"""
    h = copy(low_obj)
    origin0(h)
    remesh(h, voxel)
    surface(h, [{'t': 'lumps', 'scale': 9.0, 'amp': 0.0012}, {'t': 'pits', 'scale': 70.0, 'depth': 0.0012, 'cover': 0.7},
                {'t': 'grain', 'scale': 160.0, 'amp': 0.0003}], seed)
    set_mat(h, paint("iron_src_%d" % seed, RUST, moss=0.0, dirt=0.35, streaks=0.5, ao=0.06, edge=0.55, cavity=0.8, cracks=0.0, hue_var=0.25, grain_bump=0.6))
    return h

def stone_post(acc, rng, x, y, w, h, base=(0.14, 0.06), cap=True, broken=None):
    """네모 돌기둥 (받침돌 + 몸 + 갓돌). broken: None / 'tip' / 'cap'"""
    bw = w + base[1] * 2
    bm = bm_box(bw, bw, base[0] + 0.08)
    stone_blk(bm, rng, (2, 3), (0.025, 0.06), 0.014, zmin=0.0)
    acc.add(bm, TR((x, y, (base[0] - 0.08) / 2)))
    z = base[0]
    # 몸은 두세 덩이로 (이음매)
    n = 2 if h < 1.6 else 3
    hs = [h / n * rng.uniform(0.85, 1.15) for _ in range(n)]
    k = h / sum(hs)
    for hh in hs:
        hh *= k
        bm = bm_box(w + rng.uniform(-0.01, 0.01), w + rng.uniform(-0.01, 0.01), hh - 0.022)
        stone_blk(bm, rng, (1, 3), (0.02, 0.06), 0.012)
        acc.add(bm, TR((x, y, z + hh / 2), (0, 0, R(rng.uniform(-1, 1)))))
        z += hh
    if not cap:
        return z
    cw = w + 0.1
    bm = bm_box(cw, cw, 0.12)
    bm_chip(bm, rng, 3, (0.03, 0.07))
    if broken == 'cap':
        bm_break(bm, rng, (cw * 0.22, -cw * 0.2, 0.0), (1, -0.8, 0.6), facets=3, spread=0.4)
    bm_bevel(bm, 0.014)
    acc.add(bm, TR((x, y, z + 0.06)))
    z += 0.12
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=4, radius1=(w * 0.62), radius2=0.0, depth=0.24)
    for v in bm.verts:
        v.co.z += 0.12
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(R(45), 3, 'Z'))
    if broken == 'tip':
        bm_break(bm, rng, (0.03, 0, 0.1), (0.5, -0.3, 1), facets=2, spread=0.3)
    bm_chip(bm, rng, 2, (0.02, 0.05))
    bm_bevel(bm, 0.01)
    if broken == 'cap':
        # 뾰족 머리는 떨어져 기둥 발치에 굴렀다
        acc.add(bm, TR((x + 0.32, y - 0.36, w * 0.25), (R(105), R(15), R(30))))
        return z
    acc.add(bm, TR((x, y, z)))
    return z + 0.24

def pillar_b():
    rng = random.Random(55)
    sx, sy = -0.55, 0.35
    blocks = Acc()
    rings = column_base(rng, blocks)
    drums = []
    for z0, z1 in ((0.5, 1.22), (1.22, 1.95)):
        v, f = fluted_drum(z0 + 0.002, z1 - 0.002, rot=R(rng.uniform(-3, 3)))
        a = Acc(); a.add_raw(v, f)
        drums.append(a.obj("drum"))
    shaft = join(drums)
    # 부러진 윗단: 울퉁불퉁한 비스듬한 단면
    cut(shaft, rough_cutter((0, 0, 1.7), (0.45, -0.25, 1), w=1.2, h=1.2, amp=0.07, freq=5.5, seed=4))
    cut(shaft, [chunk((0.2, -0.2, 1.6), (0.14, 0.1, 0.12), rng), chunk((-0.24, 0.1, 1.78), (0.1, 0.08, 0.1), rng)] + shaft_spalls(rng, 6, 0.6, 1.5))
    st = join([shaft, blocks.obj("pb_blocks")] + rings)
    st.data.transform(Matrix.Translation((sx, sy, 0)))
    # 굴러떨어진 기둥 토막
    lying = []
    specs = [((0.7, -0.55), R(18), (2.0, 2.72), None), ((-0.2, -1.05), R(-62), (2.72, 3.36), 'end'), ((1.15, 0.55), R(100), (1.95, 2.4), 'both')]
    for (px, py), rz, (z0, z1), brk in specs:
        v, f = fluted_drum(z0, z1, rot=rng.uniform(0, 1))
        a = Acc(); a.add_raw(v, f)
        d = a.obj("lying")
        chip(d, rng, 4, (0.03, 0.06), sharp_deg=32, bite=0.3)
        if brk:
            cut(d, rough_cutter((0, 0, z1 - 0.12), (0.3, 0.2, 1), w=1, h=1, amp=0.05, freq=6, seed=rng.randrange(99)))
        if brk == 'both':
            cut(d, rough_cutter((0, 0, z0 + 0.1), (-0.25, 0.1, -1), w=1, h=1, amp=0.05, freq=6, seed=rng.randrange(99)))
        cut(d, shaft_spalls(rng, 3, z0 + 0.1, z1 - 0.1))
        r_ = _rf((z0 + z1) / 2)
        if brk == 'both':        # 짧은 토막은 굴러가다 선 채로 기울어 반쯤 묻혔다 (눕히면 바퀴처럼 보인다)
            M = TR((px, py, (z1 - z0) / 2 - 0.08)) @ Matrix.Rotation(R(14), 4, 'X') @ Matrix.Rotation(rz, 4, 'Z') @ TR((0, 0, -(z0 + z1) / 2))
        else:
            M = TR((px, py, r_ - 0.035)) @ Matrix.Rotation(rz, 4, 'Z') @ Matrix.Rotation(R(90), 4, 'Y') @ Matrix.Rotation(rng.uniform(0, 6.28), 4, 'Z') @ TR((0, 0, -(z0 + z1) / 2))
        d.data.transform(M)
        lying.append(d)
    peb = [chunk((rng.uniform(-0.3, 1.4), rng.uniform(-1.3, 0.8), 0.03), (s_, s_ * 0.8, s_ * 0.6), rng, 8) for s_ in [rng.uniform(0.06, 0.14) for _ in range(7)]]
    body = join([st] + lying + peb)
    sculpt(body, 0.007, STONE_LAYERS(1.2, wear=1.4, cracks=0.7), seed=5)
    set_mat(body, paint("pillar_b_src", 'stone', moss=0.85, streaks=0.65, dirt=0.8, edge=0.6))
    low = low_of(body, 7000)
    tgt = copy(low)
    v = Vine(random.Random(6), leaf=(0.045, 0.07), leaf_p=0.4)
    ivy_grow(v, tgt, (sx - 0.44, sy + 0.1, 0.04), seed=6, length=1.8, max_roots=8)
    ivy_grow(v, tgt, (0.7, -0.25, 0.03), seed=3, length=1.0, max_roots=5)
    delete(tgt)
    print("IVY tris", v.tris())
    return finish("pillar_b", [body], [low], extras=v.objects(), size=1024, extr=0.035)


def fence():
    rng = random.Random(606)
    stone = Acc()
    stone_post(stone, rng, -1.5, 0, 0.36, 1.32, broken='cap')
    stone_post(stone, rng, 1.5, 0, 0.36, 1.32, broken='tip')
    so = stone.obj("fence_posts")
    cut(so, box_spalls_at(rng, [(-1.5, 0), (1.5, 0)], 0.18, (0.3, 1.5), 6, depth=(0.007, 0.016)))
    sculpt(so, 0.006, STONE_LAYERS(0.9, wear=1.4, cracks=0.6), seed=61)
    set_mat(so, paint("fence_posts_src", 'stone', moss=0.85, dirt=0.8, streaks=0.7))
    iron = Acc()
    for z in (0.32, 1.3):                                  # 가로대 (납작한 쇠)
        v, f = bar_path([(-1.4, 0, z), (1.4, 0, z)], 0.05, 0.016, ref=(0, 1, 0))
        iron.add_raw(v, f)
    xs = [-1.1 + i * 0.22 for i in range(11)]
    for i, x in enumerate(xs):
        if i == 3:                                         # 빠진 쇠살: 밑동만 부러져 남았다
            v, f = bar_path([(x, 0, -0.04), (x, 0, 0.2), (x + 0.01, -0.004, 0.27)], 0.022)
            iron.add_raw(v, f)
            continue
        if i == 7:                                         # 휜 쇠살: 가운데가 앞으로 불룩
            pts = [(x, 0, -0.04), (x, 0, 0.32), (x + 0.015, -0.06, 0.62), (x + 0.02, -0.11, 0.82), (x + 0.01, -0.05, 1.08), (x, 0, 1.3), (x, 0, 1.52)]
            tip_d = (0, 0, 1)
        elif i == 9:                                       # 윗부분이 옆으로 꺾였다
            pts = [(x, 0, -0.04), (x, 0, 1.3), (x + 0.03, -0.01, 1.4), (x + 0.11, -0.03, 1.5)]
            tip_d = (0.75, -0.25, 0.6)
        else:
            lean = rng.uniform(-0.012, 0.012)
            pts = [(x, 0, -0.04), (x, 0, 1.3), (x + lean, 0, 1.52)]
            tip_d = (lean * 3, 0, 1)
        v, f = bar_path(pts, 0.022)
        iron.add_raw(v, f)
        if not (i == 5):                                   # 촉 하나는 떨어져 나갔다
            v, f = spear(pts[-1], tip_d, 0.15, 0.058, 0.014)
            iron.add_raw(v, f)
        v, f = bar_path([(pts[-1][0], 0, pts[-1][2] - 0.05), (pts[-1][0], 0, pts[-1][2] - 0.02)], 0.036) if i not in (9,) else ([], [])
        if v:
            iron.add_raw(v, f)
    io = iron.obj("fence_iron")
    ih = iron_high(io, 0.0035, 62)
    webs = [web_card((1.31, -0.03, 1.33), (-1, 0, 0), (0, 0, 1), 0.34),
            web_card((-1.31, -0.03, 0.33), (1, 0, 0), (0, 0, -1), 0.26, flip=True)]
    low_s = low_of(so, 2400)
    return finish("fence", [so, ih], [low_s, io], extras=webs, size=1024, extr=0.02)

def box_spalls_at(rng, centers, half, zr, n, depth=(0.01, 0.025), size=(0.06, 0.13)):
    out = []
    for _ in range(n):
        cx, cy = rng.choice(centers)
        side = rng.randrange(4)
        nn = [Vector((1, 0, 0)), Vector((-1, 0, 0)), Vector((0, 1, 0)), Vector((0, -1, 0))][side]
        t = nn.cross(Vector((0, 0, 1)))
        p = Vector((cx, cy, 0)) + nn * half + t * rng.uniform(-half * 0.8, half * 0.8) + Vector((0, 0, rng.uniform(*zr)))
        a = rng.uniform(*size)
        out.append(spall_cutter(p, nn, (a, a * rng.uniform(0.6, 1.3)), rng.uniform(*depth), rng))
    return out

URN = [(0.0, 0.0), (0.13, 0.0), (0.14, 0.03), (0.085, 0.06), (0.08, 0.1), (0.15, 0.17), (0.19, 0.27), (0.18, 0.35),
       (0.12, 0.42), (0.09, 0.46), (0.125, 0.5), (0.125, 0.54), (0.06, 0.56), (0.05, 0.6), (0.0, 0.62)]

def gate_leaf(acc, rng, width, x_dir, z_top_hinge=1.95, z_top_mid=2.25):
    """문짝 한 장 (경첩 x=0 에서 x_dir 방향으로 width). 위가 가운데로 갈수록 솟는다"""
    def arc_z(t):
        return z_top_hinge + (z_top_mid - z_top_hinge) * math.sin(t * math.pi / 2)
    X = lambda u: u * x_dir
    for v, f in (bar_path([(X(0.0), 0, 0.08), (X(0.0), 0, z_top_hinge + 0.06)], 0.04),
                 bar_path([(X(width), 0, 0.08), (X(width), 0, z_top_mid + 0.03)], 0.04),
                 bar_path([(X(0), 0, 0.14), (X(width), 0, 0.14)], 0.05, 0.016),
                 bar_path([(X(0), 0, 0.62), (X(width), 0, 0.62)], 0.05, 0.016),
                 bar_path([(X(0), 0, 1.72), (X(width), 0, 1.72)], 0.04, 0.014),
                 bar_path([(X(width * t), 0, arc_z(t)) for t in lin(0, 1, 8)], 0.045, 0.016)):
        acc.add_raw(v, f)
    n = int(width / 0.135)
    for i in range(1, n + 1):
        u = width * i / (n + 1)
        zt = arc_z(u / width)
        v, f = bar_path([(X(u), 0, 0.14), (X(u), 0, zt + 0.08)], 0.02)
        acc.add_raw(v, f)
        v, f = spear((X(u), 0, zt + 0.08), (0, 0, 1), 0.13, 0.05, 0.012)
        acc.add_raw(v, f)
        if i < n + 1:                               # 아래 칸의 고리 장식
            uu = width * (i - 0.5) / (n + 1)
            v, f = torus_raw(0.05, 0.008, TR((X(uu), 0, 0.38), (R(90), 0, 0)), 10, 4)
            acc.add_raw(v, f)
    for z in (0.35, 1.6):                           # 경첩
        v, f = bar_path([(X(-0.06), 0, z), (X(0.22), 0, z)], 0.035, 0.03)
        acc.add_raw(v, f)

def fence_gate():
    rng = random.Random(707)
    stone = Acc()
    ztop = []
    for x, br in ((-1.72, None), (1.72, None)):
        ztop.append(stone_post(stone, rng, x, 0, 0.54, 2.0, base=(0.3, 0.08), cap=False))
    # 갓돌 (두 겹) 
    for x in (-1.72, 1.72):
        for (w_, h_, z_) in ((0.7, 0.12, 2.36), (0.6, 0.07, 2.455)):
            bm = bm_box(w_, w_, h_)
            stone_blk(bm, rng, (2, 3), (0.02, 0.05), 0.012)
            stone.add(bm, TR((x, 0, z_)))
    so = stone.obj("gate_posts")
    cut(so, box_spalls_at(rng, [(-1.72, 0), (1.72, 0)], 0.27, (0.4, 2.2), 8))
    # 항아리 장식: 왼쪽은 온전, 오른쪽은 위가 깨져 떨어져 앞에 굴렀다
    urns = []
    for x in (-1.72, 1.72):
        a = Acc(); v, f = lathe(URN, 24, (x, 0, 2.49)); a.add_raw(v, f)
        u = a.obj("urn")
        if x > 0:
            cut(u, rough_cutter((x, 0, 2.82), (0.3, -0.4, 1), w=0.8, h=0.8, amp=0.03, freq=9, seed=7))
        urns.append(u)
    frag = Acc(); v, f = lathe(URN[6:], 24, (0, 0, -0.27)); frag.add_raw(v, f)
    fr = frag.obj("urn_frag")
    cut(fr, rough_cutter((0, 0, 0.04), (-0.3, 0.4, -1), w=0.8, h=0.8, amp=0.03, freq=9, seed=8))
    fr.data.transform(TR((1.45, -0.62, 0.13)) @ Matrix.Rotation(R(100), 4, 'X') @ Matrix.Rotation(R(30), 4, 'Y'))
    for u in urns + [fr]:
        chip(u, rng, 3, (0.03, 0.05), sharp_deg=25, bite=0.3)
    stones_hp = join([so] + urns + [fr])
    sculpt(stones_hp, 0.007, STONE_LAYERS(1.0, wear=1.4, cracks=0.6), seed=71)
    set_mat(stones_hp, paint("gate_posts_src", 'stone', moss=0.85, dirt=0.8, streaks=0.75))
    # 문짝: 왼쪽은 닫힘, 오른쪽은 경첩 하나가 빠져 비스듬히 열렸다
    iron = Acc()
    gate_leaf(iron, rng, 1.4, 1)
    left = iron.obj("leaf_l"); left.data.transform(TR((-1.43, 0, 0)))
    iron2 = Acc()
    gate_leaf(iron2, rng, 1.4, -1)
    right = iron2.obj("leaf_r")
    right.data.transform(TR((1.43, 0, 0.0)) @ Matrix.Rotation(R(40), 4, 'Z') @ Matrix.Rotation(R(-2.5), 4, 'Y'))
    io = join([left, right])
    ih = iron_high(io, 0.0035, 72)
    webs = [web_card((-1.42, -0.04, 1.72), (1, 0, 0), (0, 0, 1), 0.3),
            web_card((-0.2, -0.03, 0.14), (1, 0, 0), (0, 0, 1), 0.22, flip=True)]
    low_s = low_of(stones_hp, 5200)
    return finish("fence_gate", [stones_hp, ih], [low_s, io], extras=webs, size=2048, extr=0.02)


def lantern():
    rng = random.Random(808)
    stone = Acc()
    for (w_, z0, z1) in ((0.62, -0.06, 0.22), (0.46, 0.225, 0.5)):
        bm = bm_box(w_, w_, z1 - z0)
        stone_blk(bm, rng, (2, 4), (0.025, 0.07), 0.014, zmin=0.0)
        stone.add(bm, TR((0, 0, (z0 + z1) / 2), (0, 0, R(rng.uniform(-3, 3)))))
    so = stone.obj("lantern_base")
    cut(so, box_spalls_at(rng, [(0, 0)], 0.31, (0.0, 0.18), 3) + box_spalls_at(rng, [(0, 0)], 0.23, (0.27, 0.46), 3))
    sculpt(so, 0.006, STONE_LAYERS(0.9, wear=1.4, cracks=0.6), seed=81)
    set_mat(so, paint("lantern_base_src", 'stone', moss=0.85, dirt=0.75))
    iron = Acc()
    ax = 0.52
    parts = [bar_path([(0, 0, 0.46), (0.004, 0, 1.5), (0.008, 0.003, 2.62)], 0.07),
             spear((0.008, 0.003, 2.62), (0.01, 0, 1), 0.24, 0.08, 0.02, 0.03),
             bar_path([(0, 0, 2.42), (ax, 0, 2.42), (ax + 0.05, 0, 2.39), (ax + 0.06, 0, 2.34)], 0.038),
             bar_path([(0.03, 0, 2.02)] + [(ax - 0.15 - 0.34 * math.cos(a), 0, 2.02 + 0.37 * math.sin(a)) for a in lin(R(5), R(88), 7)], 0.026)]
    for z, w_ in ((0.52, 0.12), (1.5, 0.1), (2.5, 0.1), (2.6, 0.085)):
        parts.append(bar_path([(0, 0, z - 0.025), (0, 0, z + 0.025)], w_))
    for v, f in parts:
        iron.add_raw(v, f)
    # 사슬 고리 둘
    for k, z in enumerate((2.33, 2.29)):
        v, f = torus_raw(0.022, 0.006, TR((ax + 0.06, 0, z), (R(90), 0, R(90 * k))), 10, 4)
        iron.add_raw(v, f)
    # 새장 등
    zc0, zc1 = 1.86, 2.26
    v, f = lathe([(0.0, zc1 + 0.07), (0.035, zc1 + 0.05), (0.13, zc1 + 0.005), (0.13, zc1 - 0.015), (0.0, zc1 - 0.015)], 6, (ax + 0.06, 0, 0))
    iron.add_raw(v, f)
    v, f = lathe([(0.0, zc0 - 0.08), (0.02, zc0 - 0.06), (0.06, zc0 - 0.02), (0.12, zc0 + 0.005), (0.12, zc0 + 0.02), (0.0, zc0 + 0.02)], 6, (ax + 0.06, 0, 0))
    iron.add_raw(v, f)
    for i in range(6):
        a = 2 * math.pi * i / 6 + math.pi / 6
        pts = [(ax + 0.06 + rr * math.cos(a), rr * math.sin(a), z) for rr, z in ((0.105, zc0 + 0.01), (0.125, (zc0 + zc1) / 2), (0.105, zc1 - 0.01))]
        v, f = bar_path(pts, 0.014, ref=(0, 0, 1))
        iron.add_raw(v, f)
    v, f = torus_raw(0.118, 0.007, TR((ax + 0.06, 0, (zc0 + zc1) / 2)), 12, 4)
    iron.add_raw(v, f)
    io = iron.obj("lantern_iron")
    ih = iron_high(io, 0.0035, 82)
    # 영혼 수정 (새장 안)
    cv, cf = [], []
    for k, (dx, dy, ln, rr) in enumerate(((0, 0, 0.3, 0.045), (0.035, 0.02, 0.2, 0.03), (-0.03, -0.025, 0.18, 0.028), (0.01, -0.04, 0.14, 0.022))):
        v, f = crystal((ax + 0.06 + dx, dy, zc0 + 0.02), (dx * 4, dy * 4, 1), ln, rr, rng)
        off = len(cv); cv += v; cf += [tuple(off + i for i in fc) for fc in f]
    gl = glow_obj(cv, cf)
    web = web_card((0.045, -0.012, 2.395), (1, 0, 0), (0, 0, -1), 0.26)     # 팔과 받침 사이 구석의 거미줄
    low_s = low_of(so, 1600)
    return finish("lantern", [so, ih], [low_s, io], extras=[gl, web], size=1024, extr=0.02)


def rubble():
    rng = random.Random(909)
    acc = Acc()
    ext = []
    rubble_pile(acc, rng, (0, 0, 0), 0.62, 17, (0.16, 0.38), 0.62, extra=ext)
    fallen_block(acc, rng, (0.55, -0.45, 0), (0.55, 0.34, 0.3))
    fallen_block(acc, rng, (-0.62, 0.22, 0), (0.48, 0.32, 0.28))
    o = acc.obj("rubble")
    body = join([o] + ext)
    sculpt(body, 0.007, STONE_LAYERS(1.0, wear=1.4, cracks=0.6), seed=91)
    set_mat(body, paint("rubble_src", 'stone', moss=0.9, dirt=0.8, streaks=0.5, ao=0.4))
    low = low_of(body, 3600)
    return finish("rubble", [body], [low], size=1024, extr=0.03)


BUILDERS = [
    ("pillar_a", pillar_a),
    ("pillar_b", pillar_b),
    ("wall_ruin_a", wall_ruin_a),
    ("wall_ruin_b", wall_ruin_b),
    ("arch_ruin", arch_ruin),
    ("stair_ruin", stair_ruin),
    ("fence", fence),
    ("fence_gate", fence_gate),
    ("lantern", lantern),
    ("altar", altar),
    ("rubble", rubble),
]

META = {
    # 온전한 기둥: 홀로 서 있거나 줄지어 놓는다
    "pillar_a": {"kind": "prop", "tags": ["ruin"], "collider": "capsule", "footprint": 0.6, "sink": 0.04, "tilt": 3,
                 "align": False, "scale": [0.9, 1.1], "cull": 0.008, "shadows": True},
    # 부러진 기둥 밑동 + 굴러떨어진 토막 (원점 = 무리 가운데, 밑동은 (-0.55, 0.35))
    "pillar_b": {"kind": "prop", "tags": ["ruin"], "collider": "mesh", "footprint": 1.4, "sink": 0.04, "tilt": 2,
                 "align": False, "scale": [0.9, 1.1], "cull": 0.01, "shadows": True},
    "wall_ruin_a": {"kind": "prop", "tags": ["ruin"], "collider": "mesh", "footprint": 2.6, "sink": 0.05, "tilt": 1,
                    "align": False, "scale": [0.9, 1.1], "cull": 0.005, "shadows": True},
    "wall_ruin_b": {"kind": "prop", "tags": ["ruin"], "collider": "mesh", "footprint": 2.0, "sink": 0.05, "tilt": 1,
                    "align": False, "scale": [0.9, 1.15], "cull": 0.006, "shadows": True},
    # 지나갈 수 있는 아치 문 (구멍 폭 2.4m, 높이 약 5m)
    "arch_ruin": {"kind": "prop", "tags": ["ruin"], "collider": "mesh", "footprint": 2.5, "sink": 0.05, "tilt": 0,
                  "align": False, "scale": [0.95, 1.1], "cull": 0.004, "shadows": True},
    # 오를 수 있는 계단 (앞 -Y 에서 +Y 로 1.5m 오른다)
    "stair_ruin": {"kind": "prop", "tags": ["ruin"], "collider": "mesh", "footprint": 2.0, "sink": 0.05, "tilt": 0,
                   "align": False, "scale": [0.95, 1.05], "cull": 0.006, "shadows": True},
    # 울타리 한 칸 (3.4m): 길가에 이어 놓는다
    "fence": {"kind": "prop", "tags": ["ruin", "path"], "collider": "box", "footprint": 1.8, "sink": 0.04, "tilt": 2,
              "align": False, "scale": [0.95, 1.05], "cull": 0.008, "shadows": True},
    # 철문 (구멍 폭 2.9m, 오른쪽 문짝이 열려 지나갈 수 있다)
    "fence_gate": {"kind": "prop", "tags": ["ruin", "path"], "collider": "mesh", "footprint": 2.2, "sink": 0.04, "tilt": 0,
                   "align": False, "scale": [1.0, 1.0], "cull": 0.006, "shadows": True},
    # 영혼 등불: 새장 안 수정 자리에 보랏빛 점광원
    "lantern": {"kind": "prop", "tags": ["light", "path"], "collider": "capsule", "footprint": 0.6, "sink": 0.04, "tilt": 2,
                "align": False, "scale": [0.95, 1.05], "cull": 0.01, "shadows": True, "detail": "stone",   # 돌 받침이 겉넓이 약 68%
                "light": {"offset": [0.58, 0, 2.03], "color": list(SOUL), "intensity": 9, "range": 9}},
    # 봉인의 제단: 게임 시작 지점
    "altar": {"kind": "landmark", "tags": ["landmark", "ruin", "light"], "collider": "mesh", "footprint": 4.0, "sink": 0.02,
              "tilt": 0, "align": False, "scale": [1.0, 1.0], "cull": 0.003, "shadows": True,
              "light": {"offset": [0, 0, 2.5], "color": list(SOUL), "intensity": 30, "range": 18}},
    # 흩뿌리는 돌무더기 (경사에 맞춰 눕힌다)
    "rubble": {"kind": "prop", "tags": ["ruin"], "collider": "box", "footprint": 0.9, "sink": 0.05, "tilt": 6,
               "align": True, "scale": [0.7, 1.3], "cull": 0.015, "shadows": True},
}

PREVIEWS = [
    ("all", [n for n, _ in BUILDERS], False),
] + [(n, [n], True) for n, _ in BUILDERS]
