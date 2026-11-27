# 랜드마크 건축 묶음 (landmarks)
#   납골당, 무너진 대성당, 돌 망루, 우는 천사 석상, 사신 석상, 돌 우물, 무너진 아치 다리, 2장으로 가는 거대한 관문
#
# 만드는 방식 (assets_ruins.py 의 블록 방식을 큰 구조물에 맞게 키웠다)
#   - 돌은 한 장씩: 블록마다 상자를 만들고 모서리를 평면으로 쳐낸 뒤(bm_chip·bm_flake) 모를 깎는다(bm_bevel).
#     블록 사이를 띄워 두면 리메시 뒤에도 줄눈이 실제 홈으로 남고, 뒤쪽 심(core)이 구멍을 막는다.
#   - 크게 깨진 곳은 평면 몇 장(bm_break), 울퉁불퉁한 단면 커터(rough_cutter), 각진 덩어리 커터(chunk)로 판다.
#   - 큰 구조물은 부분마다 따로 리메시·조각해(voxel 을 부분 크기에 맞게) 한 저폴리로 굽는다 (finish 의 highs 목록).
#   - 석상은 겹친 타원구(blobs)를 리메시로 녹여 몸을 만들고, 평면으로 쳐낸 옷 주름·깃털 판을 덧붙인다.
#   - 아래 도우미 대부분은 assets_ruins.py·assets_graves.py 에서 가져와 이 묶음 안에 둔다 (다른 묶음 파일이 바뀌어도 영향이 없게).
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
    n = tri_count(low)
    if n > tris * 1.3:
        # 잘게 떨어진 조각이 아주 많으면 조각마다 최소 개수만 남겨도 예산을 크게 넘는다 → 전체를 한 번 더 줄인다
        print("LOW_OF 예산 초과", n, "→", tris, "(떨어진 조각", len(keep), "개)")
        m = low.modifiers.new('dec', 'DECIMATE')
        m.ratio = tris / n
        m.use_collapse_triangulate = True
        apply_all(low)
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
           missing=0.025, chips=(1, 3), M=None, plinth=0.0, keep=None, broken_top=True, k=1.0, rot=1.0):
    """x0~x1 구간에 줄눈이 보이는 돌 블록을 앞·뒤 두 겹으로 쌓는다 (가운데는 심이 채운다).
    zs: 켜 경계 높이, top(x): 무너진 윗선, y0·y1: 벽 앞면·뒷면, ragged: 양 끝이 들쭉날쭉 무너진 정도 (왼, 오른)
    plinth: 맨 아래 켜가 앞뒤로 튀어나온 정도, keep(xa, xb, za, zb): False 면 그 블록은 놓지 않는다
    k: 블록 크기 배율 (1 = 사람 키 벽의 블록. 큰 구조물은 깨짐·모깎기·문턱 값을 함께 키운다), rot: 블록 비뚤어짐 배율"""
    n = 0
    ks = k
    for k in range(len(zs) - 1):
        za, zb = zs[k], zs[k + 1] - gap
        if za >= top(x0) and za >= top(x1) and za >= top((x0 + x1) / 2):
            # 이 켜 전체가 무너졌어도 중간에 높은 곳이 있을 수 있으니 블록마다 다시 본다
            pass
        for face in (0, 1):
            xa = x0 + rng.uniform(0, ragged[0]) * (k / max(1, len(zs) - 2))
            xend = x1 - rng.uniform(0, ragged[1]) * (k / max(1, len(zs) - 2))
            first = True
            while xa < xend - 0.12 * ks:
                L = rng.uniform(*blen)
                if first:
                    L *= rng.uniform(0.35, 1.0)      # 켜마다 이음매가 엇갈리게
                    first = False
                xb = min(xend, xa + L)
                if xend - xb < 0.18 * ks:
                    xb = xend
                xm = (xa + xb) / 2
                t_here = top(xm)
                ok = za < t_here - 0.06 * ks and (keep is None or keep(xa, xb, za, zb))
                if ok and k > 0 and rng.random() < missing:
                    ok = False
                if ok:
                    d = rng.uniform(*skin)
                    pr = plinth if k == 0 else 0.0
                    if face == 0:
                        ya, yb = y0 - pr + rng.uniform(-0.012, 0.01) * ks, y0 + d
                    else:
                        ya, yb = y1 - d, y1 + pr + rng.uniform(-0.01, 0.012) * ks
                    bm = bm_box(xb - xa - gap, yb - ya, zb - za)
                    cx, cy, cz = xm, (ya + yb) / 2, (za + zb) / 2
                    # 무너진 윗선에 걸친 블록은 비스듬히 깨진 채로 남긴다
                    if broken_top and zb > t_here + 0.04 * ks:
                        # 윗선에 걸친 블록: 절반쯤은 통째로 빠지고(계단처럼 무너진 윤곽), 나머지는 제각각 비스듬히 깨진다
                        # (모두 같은 경사로 자르면 매끈한 비탈 하나로 이어져 보인다)
                        sl = (top(xb) - top(xa)) / max(0.05, xb - xa) * rng.uniform(-0.6, 1.6)
                        h_loc = t_here - cz + rng.uniform(-0.12, 0.1) * ks
                        if h_loc < -(zb - za) * 0.25 or rng.random() < 0.4:
                            bm.free()
                            xa = xb
                            continue
                        bm_break(bm, rng, (rng.uniform(-0.15, 0.15) * ks, 0, h_loc), (-sl + rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 1), facets=rng.randint(2, 4), spread=0.6, jitter=0.05 * ks)
                    stone_blk(bm, rng, chips, (0.02 * ks, 0.07 * ks), 0.014 * ks)
                    R_ = TR((cx, cy, cz), (R(rng.uniform(-0.7, 0.7) * rot), R(rng.uniform(-0.5, 0.5) * rot), R(rng.uniform(-0.6, 0.6) * rot)))
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

def arch_stones(rng, w, h_s, rise, T, n_side, y0, y1, gap=0.026, skip=(), slip=(), chips=(1, 2), k=1.0):
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
            bm = bm_poly(poly, y0 + rng.uniform(-0.01, 0.01) * k, y1 + rng.uniform(-0.01, 0.01) * k, 'y')
            stone_blk(bm, rng, chips, (0.02 * k, 0.06 * k), 0.014 * k)
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
    bm = bm_poly(poly, y0 - 0.02 * k, y1 + 0.02 * k, 'y')
    stone_blk(bm, rng, chips, (0.02 * k, 0.05 * k), 0.014 * k)
    out.append((999, bm, Vector((0, (y0 + y1) / 2, h_s + rise + T / 2))))
    res = []
    for tag, bm, c in out:
        if tag in skip:
            bm.free()
            continue
        res.append((tag, bm, c))
    return res

def jamb_stones(acc, rng, w, z0, z1, T, y0, y1, gap=0.026, hr=(0.26, 0.36), M=None, k=1.0):
    """창·문 옆 기둥돌 (양쪽, 길고 짧게 번갈아)"""
    for side in (1, -1):
        z = z0
        k = 0
        while z < z1 - 0.08 * k:
            h = min(rng.uniform(*hr), z1 - z)
            if z1 - (z + h) < 0.12 * k:
                h = z1 - z
            tw = T * (1.0 if k % 2 == 0 else 0.72) + gap
            x_in = w / 2 + gap / 2
            bm = bm_box(tw - gap, y1 - y0 + rng.uniform(0, 0.02) * k, h - gap)
            stone_blk(bm, rng, (1, 2), (0.02 * k, 0.06 * k), 0.014 * k)
            c = (side * (x_in + (tw - gap) / 2), (y0 + y1) / 2, z + h / 2 - gap / 2)
            R_ = TR(c, (0, 0, R(rng.uniform(-0.5, 0.5))))
            acc.add(bm, (M @ R_) if M is not None else R_)
            z += h
            k += 1

def zone_prism(outline, y0, y1, M=None):
    a = Acc()
    a.add(bm_poly(outline, y0 - 0.3, y1 + 0.3, 'y'), M)
    return a.obj("zone")

def rubble_pile(acc, rng, center, radius, n, size=(0.18, 0.4), height=0.5, M=None, extra=None, k=1.0):
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
            g = rng.uniform(0.045, 0.11) * k
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
        stone_blk(bm, rng, (2, 5), (0.025 * k, 0.08 * k), 0.012 * k)
        z = mound_h(rr) + height * 0.45 * t * rng.random() + sx * 0.12 - 0.03 * k
        p = c + Vector((math.cos(a) * rr, math.sin(a) * rr, z))
        R_ = TR(p, (R(rng.uniform(-40, 40)), R(rng.uniform(-40, 40)), rng.uniform(0, 6.28)))
        acc.add(bm, Mx @ R_)

def fallen_block(acc, rng, p, size, rot_z=None, tilt=(5, 25), broken=True, M=None, k=1.0, z=None):
    """땅에 떨어진 블록: 크게 깨지고 모서리가 많이 떨어져 나간 채 반쯤 묻혀 있다"""
    bm = bm_box(*size)
    if broken:
        bm_break(bm, rng, (size[0] * rng.uniform(0.05, 0.3), 0, 0), (1, rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)), facets=3, spread=0.45)
        if rng.random() < 0.6:
            bm_break(bm, rng, (0, size[1] * rng.uniform(0.15, 0.35), size[2] * 0.2), (rng.uniform(-0.4, 0.4), 1, 0.7), facets=2, spread=0.4)
    stone_blk(bm, rng, (3, 6), (0.03 * k, 0.1 * k), 0.014 * k)
    rz = rng.uniform(0, 6.28) if rot_z is None else rot_z
    tx, ty = R(rng.uniform(-tilt[1], tilt[1])), R(rng.uniform(-tilt[1], tilt[1]))
    p = Vector(p)
    p.z = (size[2] * 0.36 - 0.05 * k) + (0.0 if z is None else z)
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

# ───────────────────────── 덧칠 (kit.paint 뒤에 얹는다, assets_graves.py 에서) ─────────────────────────
def _final_color(mat):
    b = mat.node_tree.nodes["Principled BSDF"]
    return b, b.inputs['Base Color'].links[0].from_socket

def moss_low(mat, z0=0.0, z1=0.3, amount=0.8, color=MOSS, scale=3.5):
    """아래쪽에서 기어오르는 이끼 (얼룩진 경계)"""
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(P, sep.inputs[0])
    # 높이 경계를 잡음으로 흔든다
    wob = kit._mul(nt, kit._noise(nt, P, scale, 4), (z1 - z0) * 0.9)
    zz = kit._mul(nt, sep.outputs['Z'], wob, 'SUBTRACT')
    low = kit._ramp(nt, zz, z0 - (z1 - z0) * 0.45, W((1, 1, 1)), z1 - (z1 - z0) * 0.45, W((0, 0, 0)))
    patch = kit._ramp(nt, kit._noise(nt, P, scale * 2.2, 6), 0.38, W((0, 0, 0)), 0.52, W((1, 1, 1)))
    mask = kit._mul(nt, kit._mul(nt, low, patch), amount)
    mc = kit._ramp(nt, kit._noise(nt, P, 26, 5), 0.3, W(tuple(c * 0.5 for c in color)), 0.72, W(tuple(c * 1.7 for c in color)))
    out = kit._mix(nt, 'MIX', mask, col, mc)
    nt.links.new(out, b.inputs['Base Color'])
    return mat

def dirt_low(mat, z0=0.0, z1=0.1, amount=0.7, color=(0.035, 0.03, 0.045)):
    """땅에 닿는 곳 흙물 (kit.paint 의 dirt 는 0~0.35m 고정이라 작은 소품용)"""
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(P, sep.inputs[0])
    low = kit._ramp(nt, sep.outputs['Z'], z0, W((1, 1, 1)), z1, W((0, 0, 0)))
    m = kit._mul(nt, kit._mul(nt, low, kit._ramp(nt, kit._noise(nt, P, 9, 3), 0.3, W((0.5, 0.5, 0.5)), 0.7, W((1, 1, 1)))), amount)
    out = kit._mix(nt, 'MIX', m, col, W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat

def tint_near(mat, center, radius, color, amount=0.5, mode='MIX'):
    """한 점 근처를 물들인다 (영혼 빛이 스민 돌, 촛농에 그을린 자국 등)"""
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    vm = nt.nodes.new('ShaderNodeVectorMath'); vm.operation = 'DISTANCE'
    nt.links.new(P, vm.inputs[0]); vm.inputs[1].default_value = center
    d = kit._ramp(nt, vm.outputs['Value'], 0.0, W((1, 1, 1)), radius, W((0, 0, 0)))
    m = kit._mul(nt, kit._mul(nt, d, kit._ramp(nt, kit._noise(nt, P, 12, 3), 0.35, W((0.4, 0.4, 0.4)), 0.65, W((1, 1, 1)))), amount)
    out = kit._mix(nt, mode, m, col, W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat

def blotch(mat, color, scale=6.0, amount=0.5, lo=0.48, hi=0.62, mode='MULTIPLY'):
    """잡음 얼룩 (누렇게 밴 뼈, 물때 등)"""
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    m = kit._mul(nt, kit._ramp(nt, kit._noise(nt, P, scale, 6, 0.6), lo, W((0, 0, 0)), hi, W((1, 1, 1))), amount)
    out = kit._mix(nt, mode, m, col, W(tuple(min(1.0, c * 2.2) for c in color)) if mode == 'MULTIPLY' else W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat



# ═════════════════════════ 랜드마크용 도우미 ═════════════════════════
def ccw(poly):
    """다각형을 반시계 방향으로 (XZ: x 오른쪽, z 위)"""
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return list(poly) if a > 0 else list(reversed(poly))

def poly_inside(poly, x, z):
    ins = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            xi = x1 + (z - z1) * (x2 - x1) / (z2 - z1)
            if x < xi:
                ins = not ins
    return ins

def poly_nearest(poly, x, z):
    """다각형(반시계) 경계에서 가장 가까운 점과 그 자리의 안쪽 법선"""
    best = None
    n = len(poly)
    for i in range(n):
        ax, az = poly[i]
        bx, bz = poly[(i + 1) % n]
        dx, dz = bx - ax, bz - az
        L2 = dx * dx + dz * dz
        if L2 < 1e-12:
            continue
        t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L2))
        px, pz = ax + dx * t, az + dz * t
        d2 = (x - px) ** 2 + (z - pz) ** 2
        if best is None or d2 < best[0]:
            L = math.sqrt(L2)
            best = (d2, (px, pz), (-dz / L, dx / L))
    return best[1], best[2]

def rect_vs_poly(poly, xa, xb, za, zb, n=5):
    """사각형 안 표본점 중 다각형 안에 든 비율, 다각형 꼭짓점이 사각형 안에 있는지"""
    k = 0
    for i in range(n):
        for j in range(n):
            if poly_inside(poly, xa + (xb - xa) * (i + 0.5) / n, za + (zb - za) * (j + 0.5) / n):
                k += 1
    pin = any(xa < px < xb and za < pz < zb for px, pz in poly)
    return k / (n * n), pin

class Wall:
    """돌 블록 벽 (벽 좌표: x 벽 길이 방향, y 두께 (y0 = 바깥면), z 위). M 으로 월드에 놓는다.
    holes: 블록을 비워 둘 구멍 윤곽 (XZ 다각형 목록) — 테두리 돌(홍예석·문설주)이 들어갈 띠까지 포함해 준다
    clip: 잘라 낼 반공간 [(점, 법선)] (법선 쪽을 버린다) — 박공 경사 등"""
    def __init__(self, rng, M=None, k=1.0, gap=0.03, blen=(0.5, 1.0), skin=(0.3, 0.4), hr=(0.3, 0.4), chips=(1, 3), rot=1.0):
        self.rng, self.M, self.k, self.gap, self.blen, self.skin, self.hr, self.chips, self.rot = rng, (M if M is not None else Matrix.Identity(4)), k, gap, blen, skin, hr, chips, rot
        self.acc = Acc()
        self.cracks = []        # [(XZ 꺾은선, 틈 폭)] 이 벽을 지나는 금

    def add_bm(self, bm, Mloc):
        self.acc.add(bm, self.M @ Mloc)

    def block(self, xa, xb, ya, yb, za, zb, holes=(), clip=(), chips=None, flakes=(0, 2), drop_inside=0.5):
        """블록 하나: 구멍과 겹치면 구멍 쪽을 평면으로 잘라 내고, 거의 다 들어가면 놓지 않는다.
        self.cracks 의 금이 지나가면 블록을 둘로 쪼개 틈을 벌린다 (금 오른쪽/위쪽 조각은 살짝 내려앉는다)"""
        rng, k = self.rng, self.k
        cx, cy, cz = (xa + xb) / 2, (ya + yb) / 2, (za + zb) / 2
        cuts = []
        for h in holes:
            fr, pin = rect_vs_poly(h, xa, xb, za, zb)
            if fr == 0 and not pin:
                continue
            if fr >= drop_inside or poly_inside(h, cx, cz):
                return False
            (px, pz), (nx, nz) = poly_nearest(h, cx, cz)
            cuts.append(((px - cx, 0, pz - cz), (nx, 0, nz)))
        for co, no in clip:
            co = Vector(co); no = Vector(no).normalized()
            ds = [((Vector((x, y, z)) - co).dot(no)) for x in (xa, xb) for y in (ya, yb) for z in (za, zb)]
            if min(ds) > -0.02 * k:
                return False
            if max(ds) > 0:
                cuts.append(((co.x - cx, co.y - cy, co.z - cz), tuple(no)))
        bm = bm_box(xb - xa, yb - ya, zb - za)
        for co, no in cuts:
            bm_cut(bm, co, no)
            if len(bm.verts) < 4:
                bm.free()
                return False
        pieces = [(bm, 0.0)]
        for pts, width in self.cracks:
            hit = None
            for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                # 선분이 블록 사각형을 지나는지 (표본점으로)
                for i in range(9):
                    t = i / 8
                    px, pz = ax + (bx - ax) * t, az + (bz - az) * t
                    if xa - 0.02 < px < xb + 0.02 and za - 0.02 < pz < zb + 0.02:
                        hit = ((ax, az), (bx, bz))
                        break
                if hit:
                    break
            if not hit:
                continue
            (ax, az), (bx, bz) = hit
            dx, dz = bx - ax, bz - az
            L = math.hypot(dx, dz) or 1.0
            nrm = Vector((dz / L, rng.uniform(-0.25, 0.25), -dx / L)).normalized()
            t = max(0.0, min(1.0, ((cx - ax) * dx + (cz - az) * dz) / (L * L)))
            p = Vector((ax + dx * t - cx, 0, az + dz * t - cz)) + Vector((dx, 0, dz)).normalized() * 0.0
            p += Vector((rng.uniform(-0.03, 0.03), 0, rng.uniform(-0.03, 0.03))) * k
            new = []
            for b, drop in pieces:
                b2 = b.copy()
                w = width * rng.uniform(0.7, 1.3)
                bm_cut(b, p - nrm * (w / 2), nrm)
                bm_cut(b2, p + nrm * (w / 2), -nrm)
                for bb, dd in ((b, drop), (b2, drop - 0.012 * k)):
                    if len(bb.verts) >= 4:
                        new.append((bb, dd))
                    else:
                        bb.free()
            pieces = new
        r = self.rot
        rot = (R(rng.uniform(-0.6, 0.6) * r), R(rng.uniform(-0.4, 0.4) * r), R(rng.uniform(-0.5, 0.5) * r))
        for b, drop in pieces:
            stone_blk(b, rng, chips or self.chips, (0.02 * k, 0.07 * k), 0.014 * k, flakes=flakes)
            self.add_bm(b, TR((cx, cy, cz + drop), rot))
        return bool(pieces)

    def courses(self, z0, z1):
        zs = [z0]
        while zs[-1] < z1 - self.hr[0] * 0.5:
            zs.append(zs[-1] + self.rng.uniform(*self.hr))
        zs[-1] = z1
        return zs

    def face(self, x0, x1, zs, y0, depth=None, top=None, holes=(), clip=(), outward=-1, missing=0.0, plinth=0.0, ragged=(0, 0),
             broken=0.4):
        """한쪽 면 블록 켜. y0: 면 위치, outward=-1 이면 면이 -y 를 향한다 (블록은 +y 쪽으로 depth 두께)
        top(x): 무너진 윗선 (None 이면 zs 끝까지). 윗선에 걸친 블록은 비스듬히 깨지거나(broken 확률로) 빠진다"""
        rng, k, gap = self.rng, self.k, self.gap
        holes = [ccw(h) for h in holes]
        n = 0
        for i in range(len(zs) - 1):
            za, zb = zs[i], zs[i + 1] - gap
            xa = x0 + rng.uniform(0, ragged[0]) * (i / max(1, len(zs) - 2))
            xend = x1 - rng.uniform(0, ragged[1]) * (i / max(1, len(zs) - 2))
            first = True
            while xa < xend - 0.1 * k:
                L = rng.uniform(*self.blen)
                if first:
                    L *= rng.uniform(0.35, 1.0)
                    first = False
                xb = min(xend, xa + L)
                if xend - xb < self.blen[0] * 0.4:
                    xb = xend
                xm = (xa + xb) / 2
                d = rng.uniform(*self.skin) if depth is None else depth
                pr = plinth if i == 0 else 0.0
                jit = rng.uniform(-0.01, 0.01) * k
                if outward < 0:
                    ya, yb = y0 - pr + jit, y0 + d
                else:
                    ya, yb = y0 - d, y0 + pr + jit
                ok = not (i > 0 and rng.random() < missing)
                cl = list(clip)
                if ok and top is not None:
                    t_here = top(xm)
                    if za > t_here - 0.06 * k:
                        ok = False
                    elif zb > t_here + 0.04 * k:
                        h_loc = t_here + rng.uniform(-0.12, 0.1) * k
                        if h_loc < za + (zb - za) * 0.3 or rng.random() > broken:
                            ok = False
                        else:
                            sl = (top(xb) - top(xa)) / max(0.05, xb - xa) * rng.uniform(-0.6, 1.6)
                            nn = Vector((-sl + rng.uniform(-0.6, 0.6), rng.uniform(-0.5, 0.5), 1)).normalized()
                            for f in range(rng.randint(2, 3)):
                                n2 = (nn + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * 0.45).normalized()
                                cl.append(((xm + rng.uniform(-0.15, 0.15) * k, (ya + yb) / 2, h_loc + rng.uniform(-0.05, 0.05) * k), tuple(n2)))
                if ok and self.block(xa + gap / 2, xb - gap / 2, ya, yb, za, zb, holes, cl):
                    n += 1
                xa = xb
        return n

def gable_clip(xl, xr, z_e, xa, z_a):
    """박공 경사 두 면 (왼쪽 처마 (xl, z_e) → 꼭대기 (xa, z_a) → 오른쪽 처마 (xr, z_e)) 위를 버리는 반공간"""
    dl = Vector((xa - xl, 0, z_a - z_e)).normalized()
    dr = Vector((xr - xa, 0, z_e - z_a)).normalized()
    return [((xl, 0, z_e), (-dl.z, 0, dl.x)), ((xr, 0, z_e), (-dr.z, 0, dr.x))]

def bm_wedge(w, d, h):
    """경사진 물끊기 (앞이 낮은 쐐기): x 폭 w, y 깊이 d (앞 = -y), z 높이 h, 바닥 z=0"""
    poly = [(-d / 2, 0), (d / 2, 0), (d / 2, h), (-d / 2, h * 0.18)]
    bm = bmesh.new()
    A = [bm.verts.new((-w / 2, y, z)) for y, z in poly]
    B = [bm.verts.new((w / 2, y, z)) for y, z in poly]
    bm.faces.new(A[::-1]); bm.faces.new(B)
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((A[i], A[j], B[j], B[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm

def bm_pyramid(w, h, d=None, sides=4, rot=45.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=sides, radius1=w * 0.7071 if sides == 4 else w / 2, radius2=0.0, depth=h)
    for v in bm.verts:
        v.co.z += h / 2
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(R(rot), 3, 'Z'))
    if d is not None:
        for v in bm.verts:
            v.co.y *= d / w
    return bm

def bm_cyl(r, h, seg=16, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=h)
    for v in bm.verts:
        v.co.z += h / 2
    return bm

def acc_obj(acc, name):
    return acc.obj(name) if not acc.empty() else None

def blobs(items, sub=2, name="blobs"):
    """겹친 타원구들 (리메시하면 한 덩어리로 녹는다). items: [(중심, (rx,ry,rz), 회전), ...]"""
    a = Acc()
    for it in items:
        c, r = it[0], it[1]
        rot = it[2] if len(it) > 2 else (0, 0, 0)
        if not isinstance(r, (tuple, list)):
            r = (r, r, r)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
        M = Matrix.Translation(Vector(c)) @ Euler(rot, 'XYZ').to_matrix().to_4x4() @ Matrix.Diagonal((r[0], r[1], r[2], 1.0))
        a.add(bm, M)
    return a.obj(name)

def tube_items(pts, radii, step=0.5, squash=(1.0, 1.0)):
    """점을 이은 관을 구슬로 채운다 (반지름 radii, 구슬 간격 = 반지름 × step)"""
    out = []
    for i in range(len(pts) - 1):
        a, b = Vector(pts[i]), Vector(pts[i + 1])
        ra, rb = radii[i], radii[i + 1]
        L = (b - a).length
        n = max(1, int(L / (min(ra, rb) * step)))
        d = (b - a).normalized() if L > 1e-6 else Vector((0, 0, 1))
        q = d.to_track_quat('Z', 'Y').to_euler()
        for kk in range(n + (1 if i == len(pts) - 2 else 0)):
            t = kk / n
            r = ra + (rb - ra) * t
            out.append((a.lerp(b, t), (r * squash[0], r * squash[1], r), tuple(q)))
    return out

def streaks_big(mat, scale=1.2, length=0.12, amount=0.55, color=(0.3, 0.28, 0.4), z0=-1e3, z1=1e3):
    """큰 건물용 빗물 자국: 세로로 길게 늘인 얼룩 (kit.paint 의 자국은 1.6m 길이라 큰 벽에서는 짧다)"""
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (scale * 8, scale * 8, length)
    nt.links.new(P, mp.inputs['Vector'])
    st = kit._ramp(nt, kit._noise(nt, mp.outputs['Vector'], 3.0, 4), 0.48, W((0, 0, 0)), 0.72, W((1, 1, 1)))
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(P, sep.inputs[0])
    band = kit._mul(nt, kit._ramp(nt, sep.outputs['Z'], z0, W((0, 0, 0)), z0 + 0.3, W((1, 1, 1))),
                    kit._ramp(nt, sep.outputs['Z'], z1 - 0.3, W((1, 1, 1)), z1, W((0, 0, 0))))
    m = kit._mul(nt, kit._mul(nt, st, band), amount)
    out = kit._mix(nt, 'MULTIPLY', m, col, W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat

def big_stone_mat(name, pal='stone', moss=0.7, k=1.0, ao=0.5, streak=0.5, dirt_h=1.0, moss_h=1.4, **kw):
    """큰 석조물 칠: kit.paint + 아래쪽 흙물·이끼 띠 + 긴 빗물 자국"""
    m = paint(name, pal, moss=moss, ao=ao, **kw)
    streaks_big(m, 1.0 / k, 0.12 / k, streak)
    if dirt_h > 0:
        dirt_low(m, -0.1, dirt_h, 0.75)
    if moss_h > 0:
        moss_low(m, 0.0, moss_h, 0.75, scale=1.6 / k)
    return m

def keep_mats_live():
    """kit.load_fbx 가 FBX 의 재질 이름을 보고 Foliage·Glow_* 를 찾을 수 있게 진짜 재질을 먼저 만든다"""
    foliage_mat()
    for g in GLOW:
        glow_mat(g)

def low_parts(high, tris, z=-0.03, floor=28):
    """low_of 와 같지만 z 아래를 지우지 않으려면 z 를 아주 낮게 준다 (다리처럼 땅 아래도 보이는 것)"""
    return low_of(high, tris, z, floor)

def ivy_on(low, starts, rng_seed, leaf=(0.06, 0.1), leaf_p=0.42, hangs=(), **kw):
    """저폴리 복사본 위에 덩굴. starts: [(점, 씨앗, 길이, 뿌리 수)], hangs: [(위 점, 길이, 바깥 방향)]"""
    tgt = copy(low)
    tgt.location = (0, 0, 0)
    v = Vine(random.Random(rng_seed), leaf=leaf, leaf_p=leaf_p)
    for p, seed, length, roots in starts:
        ivy_grow(v, tgt, p, seed=seed, length=length, max_roots=roots, **kw)
    delete(tgt)
    rr = random.Random(rng_seed + 1)
    for top, ln, face in hangs:
        hang_strand(v, top, ln, rr, face=face)
    print("IVY tris", v.tris())
    return v.objects()

def crack_line(rng, p0, d, length, segs=6, wander=0.35):
    """구불구불한 금의 꺾은선 (XZ)"""
    d = Vector((d[0], d[1])).normalized()
    side = Vector((-d.y, d.x))
    pts = [tuple(p0)]
    p = Vector(p0)
    for i in range(segs):
        p = p + d * (length / segs) + side * rng.uniform(-wander, wander) * (length / segs)
        pts.append((p.x, p.y))
    return pts

def arch_grow(w, h_s, rise, g):
    """같은 중심으로 g 만큼 키운 뾰족 아치의 (폭, 솟음)"""
    cx, r, _ = arch_geo(w, h_s, rise)
    return w + 2 * g, math.sqrt(max(0.0, (r + g) ** 2 - cx * cx))

def tears(mat, pts, length, width=0.035, amount=0.8, color=(0.045, 0.035, 0.07), axis='x'):
    """(가로, 높이) 점들에서 아래로 흘러내린 눈물 같은 빗물 자국 (위가 진하고 아래로 갈수록 옅고 가늘다).
    axis: 가로 좌표 축 ('x' = 앞이 -Y 인 면, 'y' = 옆면)"""
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(P, sep.inputs[0])
    H = sep.outputs['X'] if axis == 'x' else sep.outputs['Y']
    Z = sep.outputs['Z']
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (0.0, 0.0, 5.0)
    nt.links.new(P, mp.inputs['Vector'])
    wob = kit._mul(nt, kit._mul(nt, kit._noise(nt, mp.outputs['Vector'], 1.0, 3), 0.5, 'SUBTRACT'), width * 1.6)
    total = None
    for (x0, z0) in pts:
        dx = kit._mul(nt, kit._mul(nt, kit._mul(nt, H, x0, 'SUBTRACT'), wob, 'ADD'), 0.0, 'ABSOLUTE')
        # 아래로 갈수록 가늘게: 폭 = width * (0.4 + 0.6 * (z - (z0-length)) / length)
        fall = kit._mul(nt, kit._mul(nt, Z, z0 - length, 'SUBTRACT'), 1.0 / length)
        wz = kit._mul(nt, kit._mul(nt, kit._mul(nt, fall, 0.6), 0.4, 'ADD'), width)
        band = kit._ramp(nt, kit._mul(nt, dx, wz, 'DIVIDE'), 0.45, W((1, 1, 1)), 1.0, W((0, 0, 0)))
        vert = kit._mul(nt, kit._ramp(nt, fall, 0.0, W((0, 0, 0)), 0.55, W((1, 1, 1))), kit._ramp(nt, Z, z0 - 0.01, W((1, 1, 1)), z0 + 0.03, W((0, 0, 0))))
        m_ = kit._mul(nt, band, vert)
        total = m_ if total is None else kit._mul(nt, total, m_, 'MAXIMUM')
    out = kit._mix(nt, 'MIX', kit._mul(nt, total, amount), col, W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat

def iron_mat(name, seed=0, pal=None):
    """검은 쇠 + 녹 (큰 문짝용, 녹을 조금 줄였다)"""
    return paint(name, pal or ((0.008, 0.008, 0.012), (0.045, 0.032, 0.034), (0.24, 0.22, 0.27)), moss=0.0, dirt=0.4, streaks=0.6, ao=0.12,
                 edge=0.6, cavity=0.85, cracks=0.0, hue_var=0.2, grain_bump=0.6)


# ───────────────────────── 굽기·내보내기 (kit.finish 를 이 묶음에 맞게 조금 바꾼 것) ─────────────────────────
def unwrap_smoothed(low, uv_angle=66, iters=8, factor=0.5, margin=0.006):
    """UV 펴기: 거친 저폴리(깨진 돌·줄인 리메시)를 그대로 smart_project 하면 면 방향이 제각각이라 삼각형 몇 장짜리 섬 수천 개로
    쪼개진다 (텍스처 낭비 + 이음매마다 검은 점). 모양이 같은(위상이 같은) 복사본을 매끈하게 다듬어 그 위에서 펴고 UV 만 옮긴다."""
    sm = copy(low)
    m = sm.modifiers.new('sm', 'SMOOTH'); m.factor = factor; m.iterations = iters
    apply_all(sm)
    act(sm)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=R(uv_angle), island_margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')
    if not low.data.uv_layers:
        low.data.uv_layers.new(name="UVMap")
    src, dst = sm.data.uv_layers[0].data, low.data.uv_layers[0].data
    for i in range(len(dst)):
        dst[i].uv = src[i].uv
    low.data.uv_layers[0].name = "UVMap"
    delete(sm)

def _bake_lm(low, highs, kind, extr, margin=24):
    bpy.ops.object.select_all(action='DESELECT')
    for h in highs:
        h.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    if kind == 'DIFFUSE':
        bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, use_selected_to_active=True, cage_extrusion=extr,
                            max_ray_distance=0.0, margin=margin, use_clear=True)
    else:
        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=extr, max_ray_distance=0.0, margin=margin, use_clear=True)

def finish_lm(name, highs, low_parts, extras=(), size=1024, extr=0.03, lod1=0.35, lod2=None, uv_angle=66, far_extras=None, smooth_uv=24):
    """kit.finish 와 같다. 다른 점: 마지막 LOD 에는 far_extras(없으면 extras 전부)만 붙인다 —
    덩굴 잎 카드가 멀리서도 그대로 남아 LOD2 삼각형 대부분을 차지하던 것을 막는다 (발광 부품은 far_extras 로 넘겨 남긴다).
    highs: 굽기 원본 / low_parts: 저폴리 조각 (하나로 합쳐 UV를 펴고 Main 재질)
    extras: 굽지 않고 그대로 붙이는 부품 (Glow_* 재질, Foliage 재질을 미리 입힌 것)
    lod1, lod2: LOD 비율 (Main 부분만 줄인다). None 이면 만들지 않는다."""
    print("HIGH tris", [tri_count(h) for h in highs], "LOW tris", [tri_count(l) for l in low_parts])
    low = join(low_parts)
    origin0(low)
    low.name = name + "_LOD0"
    low.data.name = name + "_LOD0"
    low.data.materials.clear()
    unwrap_smoothed(low, uv_angle, smooth_uv)

    img_a = bpy.data.images.new(name + "_albedo", size, size, alpha=False)
    img_n = bpy.data.images.new(name + "_normal", size, size, alpha=False)
    img_n.colorspace_settings.name = 'Non-Color'
    mat = bpy.data.materials.new("Main")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    ta = nt.nodes.new('ShaderNodeTexImage'); ta.image = img_a
    tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = img_n
    low.data.materials.append(mat)
    nt.nodes.active = ta
    _bake_lm(low, highs, 'DIFFUSE', extr, 16 if size <= 1024 else 24)
    nt.nodes.active = tn
    _bake_lm(low, highs, 'NORMAL', extr, 16 if size <= 1024 else 24)
    kit._save_jpg(img_a, os.path.join(kit.OUT, name + "_albedo.jpg"))
    img_n.filepath_raw = os.path.join(kit.OUT, name + "_normal.png")
    img_n.file_format = 'PNG'
    img_n.save()
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(ta.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    for h in highs:
        delete(h)

    lods = [low]
    for i, ratio in enumerate([r for r in (lod1, lod2) if r]):
        c = copy(low)
        c.name = name + "_LOD%d" % (i + 1)
        c.data.name = c.name
        m = c.modifiers.new('dec', 'DECIMATE'); m.ratio = ratio; m.use_collapse_triangulate = True
        apply_all(c)
        lods.append(c)
    extra_list = [e for e in extras if e is not None]
    far_list = extra_list if far_extras is None else [e for e in far_extras if e is not None]
    for i, L in enumerate(lods):
        use = far_list if (i == len(lods) - 1 and i > 0) else extra_list
        if use:
            ex = [copy(e) for e in use]
            joined = join([L] + ex)
            joined.name = name + "_LOD%d" % i
            lods[i] = joined
    for e in set(extra_list) | set(far_list):
        delete(e)
    for L in lods:
        for p in L.data.polygons:
            p.use_smooth = True
    info = {'name': name, 'tris': [tri_count(L) for L in lods], 'size': [round(v, 2) for v in lods[0].dimensions], 'tex': size}
    bpy.ops.object.select_all(action='DESELECT')
    for L in lods:
        L.select_set(True)
    bpy.context.view_layer.objects.active = lods[0]
    bpy.ops.export_scene.fbx(filepath=os.path.join(kit.OUT, name + ".fbx"), use_selection=True, object_types={'MESH'},
                             apply_scale_options='FBX_SCALE_UNITS', bake_space_transform=True, axis_forward='-Z', axis_up='Y',
                             use_mesh_modifiers=True, mesh_smooth_type='OFF', add_leaf_bones=False, bake_anim=False,
                             colors_type='SRGB')
    print("ASSET", info)
    for i, L in enumerate(lods):
        L.location = (1000 + len(kit.LOWS) * 40, 1000 + i * 40, 0)   # 미리보기 장면에서 복제해 쓸 원본은 멀리 치워 둔다
        L.hide_render = True
    kit.LOWS[name] = lods[0]
    return lods[0]


def web_dim(p, u_dir, v_dir, size, flip=False, col=(0.42, 0.44, 0.52)):
    """거미줄 (web_card 와 같지만 덜 하얗게: 밤 장면에서 하얀 격자가 튀지 않게)"""
    o = web_card(p, u_dir, v_dir, size, flip)
    vcolor(o, lambda q, n, i: (col[0], col[1], col[2], 0.08))
    return o

class Sub:
    """다른 Acc 에 행렬 M 을 곱해 넣는다 (벽 좌표로 부품을 놓을 때)"""
    def __init__(self, acc, M):
        self.acc, self.M = acc, M

    def add(self, bm, M=None):
        self.acc.add(bm, self.M @ (M if M is not None else Matrix.Identity(4)))

    def add_raw(self, verts, faces, M=None):
        self.acc.add_raw(verts, faces, self.M @ (M if M is not None else Matrix.Identity(4)))

def jambs_top(acc, rng, w, z0, z1, T, y0, y1, gap, hr, M, k, top=None, cx=0.0):
    """문설주 (jamb_stones 와 같지만 무너진 윗선 top(x) 위로는 쌓지 않는다). cx: 창 가운데 (벽 좌표, top 을 볼 때)"""
    for side in (1, -1):
        zt = z1 if top is None else min(z1, top(cx + side * (w / 2 + T / 2)) - 0.3 * k)
        z = z0
        i = 0
        while z < zt - 0.08 * k:
            h = min(rng.uniform(*hr), zt - z)
            if zt - (z + h) < 0.12 * k:
                h = zt - z
            tw = T * (1.0 if i % 2 == 0 else 0.72) + gap
            x_in = w / 2 + gap / 2
            bm = bm_box(tw - gap, y1 - y0 + rng.uniform(0, 0.02) * k, h - gap)
            stone_blk(bm, rng, (1, 2), (0.02 * k, 0.06 * k), 0.014 * k)
            c = (side * (x_in + (tw - gap) / 2), (y0 + y1) / 2, z + h / 2 - gap / 2)
            R_ = TR(c, (0, 0, R(rng.uniform(-0.5, 0.5))))
            acc.add(bm, (M @ R_) if M is not None else R_)
            z += h
            i += 1

VOX = float(os.environ.get("LM_VOX", "1.0"))      # 빠른 형태 확인용 (1보다 크면 리메시를 거칠게)

def low_coarse(src, voxel, tris, z=-0.03, floor=20, min_area=0.3):
    """큰 구조물 저폴리: 조각하기 전 조립품을 거칠게(voxel) 리메시한 뒤 줄인다.
    고폴리를 곧바로 0.5% 아래로 줄이면 블록 모서리가 저폴리 밖으로 크게 튀어나와 굽기에 검은 얼룩이 생긴다.
    거친 리메시는 표면을 고르게 따라가므로 차이가 voxel 정도로 묶인다 (굽기 거리 extr 는 voxel × 1.5 정도로)"""
    c = copy(src)
    origin0(c)
    remesh(c, voxel)
    # 거친 리메시에서 생긴 자잘한 조각(자갈 등)은 버린다 — 고폴리 자갈은 그 아래 바닥 면에 그림으로 구워진다
    bm = bmesh.new(); bm.from_mesh(c.data)
    seen = set(); kill = []
    for f in bm.faces:
        if f.index in seen:
            continue
        isl = []; stack = [f]; seen.add(f.index)
        while stack:
            g = stack.pop(); isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); stack.append(h)
        if sum(x.calc_area() for x in isl) < min_area:
            kill += isl
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(c.data); bm.free()
    lo = low_of(c, tris, z, floor)
    delete(c)
    return lo

def low_weighted(high, tris, hot, z=-0.03, factor=20.0):
    """저폴리: 작은 중요한 곳(손·얼굴·눈 등)을 덜 줄인다. hot: [(중심, 반지름)] — 그 안의 정점에 무게를 주어 줄일 때 지킨다"""
    c = copy(high)
    drop_below(c, z)
    vg = c.vertex_groups.new(name="imp")
    hot = [(Vector(p), r) for p, r in hot]
    for v in c.data.vertices:
        w = 0.0
        for p, r in hot:
            d = (v.co - p).length
            if d < r:
                w = max(w, 1.0 - d / r)
        if w > 0:
            vg.add([v.index], min(1.0, w * 1.5), 'REPLACE')
    n = tri_count(c)
    if n > tris:
        m = c.modifiers.new('dec', 'DECIMATE')
        m.ratio = tris / n
        m.use_collapse_triangulate = True
        m.vertex_group = "imp"
        m.vertex_group_factor = factor
        apply_all(c)
    c.vertex_groups.clear()
    for p in c.data.polygons:
        p.use_smooth = True
    return c

def memlog(tag):
    """진단: 지금까지 최대 메모리"""
    import resource
    print("MEM", tag, "%.0f MB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024))


# ═════════════════════════ 공통 부품 ═════════════════════════
def skull_relief(c, s=1.0, wings=True, rng=None, glow_r=0.055):
    """날개 달린 해골 부조 (앞 = -Y, c = 해골 중심, s = 배율, 해골 높이 약 0.9 s). 돌아오는 것: (돌 객체, 눈 발광 객체)"""
    rng = rng or random.Random(5)
    c = Vector(c)
    it = [((0, 0.06, 0.14), (0.34, 0.22, 0.34)),            # 머리뼈
          ((0, -0.1, 0.12), (0.3, 0.12, 0.26)),             # 이마
          ((0, -0.16, -0.02), (0.31, 0.07, 0.07)),          # 눈썹뼈
          ((0, -0.13, -0.16), (0.26, 0.1, 0.13)),           # 눈 둘레·광대 판
          ((0, -0.12, -0.33), (0.18, 0.1, 0.1)),            # 위턱
          ((0, -0.08, -0.5), (0.16, 0.09, 0.07))]           # 아래턱
    for sx in (-1, 1):
        it.append(((sx * 0.22, -0.1, -0.2), (0.09, 0.09, 0.08)))       # 광대뼈
        it.append(((sx * 0.13, -0.08, -0.47), (0.07, 0.08, 0.09)))     # 턱 모서리
    it += tube_items([(-0.15, -0.16, -0.4), (0, -0.2, -0.41), (0.15, -0.16, -0.4)], [0.05] * 3, 0.5)
    sk = blobs(it, 3, "skull")
    sk.data.transform(Matrix.Translation(c) @ Matrix.Diagonal((s, s, s, 1)))
    remesh(sk, 0.012 * s)
    cs = []
    for sx in (-1, 1):
        cs.append(sphere(1.0, c + Vector((sx * 0.13, -0.27, -0.1)) * s, (0.1 * s, 0.16 * s, 0.095 * s), 3, rot=(0, sx * R(14), 0)))
    nose = [(0, -0.17), (0.055, -0.3), (0.0, -0.33), (-0.055, -0.3)]
    nb = bm_poly([(x * s + c.x, z * s + c.z) for x, z in nose], c.y - 0.4 * s, c.y - 0.12 * s, 'y')
    a = Acc(); a.add(nb); cs.append(a.obj("nose"))
    for i in range(6):                    # 이 사이 홈
        x = -0.15 + 0.3 * (i + 0.5) / 6
        a = Acc(); a.add(bm_box(0.03 * s, 0.3 * s, 0.13 * s), TR(c + Vector((x, -0.26, -0.43)) * s))
        cs.append(a.obj("tg"))
    a = Acc(); a.add(bm_box(0.34 * s, 0.3 * s, 0.028 * s), TR(c + Vector((0, -0.26, -0.45)) * s))
    cs.append(a.obj("bite"))
    cut(sk, cs, voxel=0.012 * s)
    parts = [sk]
    if wings:
        # 날개: 앞쪽 뼈대(팔) 아래로 깃털이 부채처럼 늘어진다. 세 겹 (뒤 긴 깃 → 가운데 → 앞 짧은 덮깃)
        wa = Acc()
        layers = ((11, 0.0, 1.0, (0.34, 0.66), 0.04, 0.12), (9, 0.0, 0.85, (0.24, 0.4), -0.02, 0.11), (7, 0.04, 0.62, (0.13, 0.22), -0.075, 0.1))
        for sx in (-1, 1):
            arm = [Vector((sx * (0.26 + 0.64 * t), -0.07, 0.04 + 0.2 * math.sin(math.pi * t * 0.8))) for t in lin(0, 1, 8)]
            v, f = bar_path(arm, 0.1, 0.09)
            wa.add_raw(v, f, Matrix.Translation(c) @ Matrix.Diagonal((s, s, s, 1)))
            for li, (n, t0, t1, Lr, yoff, w_) in enumerate(layers):
                for i in range(n):
                    t = t0 + (t1 - t0) * i / (n - 1)
                    E = Vector((sx * (0.26 + 0.64 * t), 0, 0.04 + 0.2 * math.sin(math.pi * t * 0.8)))
                    a = R(-98 + 66 * t + rng.uniform(-3, 3) + li * 6)
                    d = Vector((sx * math.cos(a), 0, math.sin(a)))
                    L = (Lr[0] + (Lr[1] - Lr[0]) * t) * rng.uniform(0.93, 1.05)
                    th = 0.055 - 0.008 * li
                    bm = bm_box(L, th, w_)
                    bm_cut(bm, (L / 2 - w_ * 0.95, 0, w_ / 2), (0.5, 0, 1))         # 깃 끝을 뾰족하게
                    bm_cut(bm, (L / 2 - w_ * 0.95, 0, -w_ / 2), (0.5, 0, -1))
                    bm_cut(bm, (0, -th / 2 + 0.012, w_ / 2), (0, -0.35, 1))            # 깃대 쪽으로 비스듬한 면 (겹이 보이게)
                    bm_chip(bm, rng, 1 if rng.random() < 0.5 else 0, (0.008, 0.02))
                    M = Matrix.Translation(c + (E + d * (L * 0.5 - 0.04)) * s + Vector((0, yoff * s, 0))) @ \
                        Matrix.Rotation(-math.atan2(d.z, d.x), 4, 'Y') @ Matrix.Rotation(R(sx * rng.uniform(4, 10)), 4, 'X') @ \
                        Matrix.Diagonal((s, s, s, 1))
                    wa.add(bm, M)
        parts.append(wa.obj("wings"))
    eyes = []
    for sx in (-1, 1):
        e = sphere(glow_r * s, c + Vector((sx * 0.13, -0.17, -0.1)) * s, (1, 0.8, 1), 2)
        eyes.append(e)
    ge = glow(join(eyes), 'Glow_Soul')
    return join(parts), ge

def pinnacle(acc, rng, x, y, z0, w=0.5, h_shaft=0.7, h_top=1.0, broken=False, k=1.0):
    """작은 뾰족탑: 네모 몸 + 사방 박공 + 뾰족 지붕 + 꼭지. broken 이면 몸 위가 부러져 있다. 돌아오는 것: 떨어진 머리 bm (없으면 None)"""
    bm = bm_box(w, w, h_shaft)
    stone_blk(bm, rng, (1, 3), (0.02 * k, 0.05 * k), 0.012 * k)
    acc.add(bm, TR((x, y, z0 + h_shaft / 2)))
    top = bm_pyramid(w * 1.1, h_top)
    bm_chip(top, rng, 2, (0.02 * k, 0.05 * k))
    knob = bm_cyl(0.06 * k, 0.16 * k, 8)
    if broken:
        knob.free()
        return top
    acc.add(top, TR((x, y, z0 + h_shaft)))
    acc.add(knob, TR((x, y, z0 + h_shaft + h_top - 0.05 * k)))
    return None

def buttress(acc, rng, x, y, w, d, stages, out=(0, -1), k=1.0):
    """단이 진 버팀벽: stages = [(z0, z1, w, d)] 아래부터, 단마다 앞으로 기운 물끊기 돌. out: 바깥 방향 (x, y)"""
    ang = math.atan2(out[1], out[0]) + math.pi / 2       # 쐐기 앞(-y)이 out 을 향하게
    for (z0, z1, ww, dd) in stages:
        hc = rng.uniform(0.34, 0.44) * k
        z = z0
        while z < z1 - hc * 0.5:
            h = min(hc * rng.uniform(0.9, 1.1), z1 - z)
            bm = bm_box(ww - 0.03 * k, dd - 0.03 * k, h - 0.03 * k)
            stone_blk(bm, rng, (1, 3), (0.02 * k, 0.06 * k), 0.014 * k)
            off = Vector((out[0], out[1], 0)) * ((dd - d) / 2)
            acc.add(bm, TR((x + off.x, y + off.y, z + h / 2), (0, 0, ang)))
            z += h
        bm = bm_wedge(ww + 0.06 * k, dd + 0.06 * k, 0.32 * k)
        bm_chip(bm, rng, 2, (0.02 * k, 0.05 * k))
        off = Vector((out[0], out[1], 0)) * ((dd - d) / 2)
        acc.add(bm, TR((x + off.x, y + off.y, z1 - 0.02 * k), (0, 0, ang)))

def iron_door_leaf(acc, w, h_s, arch_w, arch_hs, arch_rise, x_hinge, side, t=0.09):
    """뾰족 아치 문짝 한 장 (경첩 x_hinge 에서 side 방향으로 w). 띠쇠·징·문고리"""
    cx, r, a_end = arch_geo(arch_w, arch_hs, arch_rise)
    # 문짝 윤곽: 아치 안쪽 절반 (경첩 쪽이 바깥)
    pts = []
    for i in range(13):
        u = i / 12
        xx = arch_w / 2 * (1 - u)                 # 바깥 → 가운데
        if xx > cx + r:
            zz = arch_hs
        else:
            zz = arch_hs + math.sqrt(max(0.0, r * r - (xx - cx) ** 2))
        pts.append((xx, zz))
    base = 0.5
    poly = [(0.0, base), (arch_w / 2, base)] + [(x, z - 0.02) for x, z in pts]
    poly = [(x_hinge + side * (arch_w / 2 - x) * (w / (arch_w / 2)), z) for x, z in poly]
    acc.add(bm_poly(ccw(poly), -t / 2, t / 2, 'y'))
    # 띠쇠 (가로)
    for z in (base + 0.3, base + 1.05, base + 1.8, arch_hs + 0.4):
        v, f = bar_path([(x_hinge - side * 0.08, -t / 2 - 0.012, z), (x_hinge + side * (w - 0.04), -t / 2 - 0.012, z)], 0.1, 0.03)
        acc.add_raw(v, f)
        for i in range(7):             # 징
            xx = x_hinge + side * (0.08 + (w - 0.16) * i / 6)
            acc.add(bm_pyramid(0.05, 0.035), TR((xx, -t / 2 - 0.027, z), (R(90), 0, 0)))
    # 세로 띠
    v, f = bar_path([(x_hinge + side * (w - 0.07), -t / 2 - 0.01, base + 0.1), (x_hinge + side * (w - 0.07), -t / 2 - 0.01, arch_hs + 0.1)], 0.07, 0.025)
    acc.add_raw(v, f)
    # 문고리
    v, f = torus_raw(0.11, 0.018, TR((x_hinge + side * (w - 0.22), -t / 2 - 0.05, base + 1.55), (R(90), 0, 0)), 14, 5)
    acc.add_raw(v, f)
    acc.add(bm_cyl(0.07, 0.04, 8), TR((x_hinge + side * (w - 0.22), -t / 2 - 0.02, base + 1.66), (R(90), 0, 0)))


# ═════════════════════════ 납골당 ═════════════════════════
def crypt():
    rng = random.Random(1101)
    k = 1.25
    gap = 0.04
    ZP = 0.5                                     # 기단 윗면
    XW, YF, YB = 3.3, -3.6, 4.6                   # 벽 바깥면: 옆 ±XW, 앞 YF, 뒤 YB
    PX, PYF, PYB = 4.05, -4.35, 5.2                # 기단 가장자리
    ZE, ZA = 4.8, 7.8                            # 처마, 박공 꼭대기
    TW = 0.7                                     # 앞벽 두께
    # 문: 바깥 겹 / 안 겹 뾰족 아치
    WO, WI, HS, RO, RI, TV = 2.5, 1.7, 2.65, 1.9, 1.35, 0.36
    walls = []

    # ── 앞벽 (박공) ──
    Wf = Wall(rng, TR((0, YF, 0)), k=k, gap=gap, blen=(0.5, 1.35), skin=(0.32, 0.42), hr=(0.34, 0.56))
    portal_zone = arch_outline(WO, HS, RO, grow=TV + gap, z_bottom=ZP - 0.05)
    zs = Wf.courses(ZP, ZA + 0.3)
    # 금: 문 아치 꼭대기에서 해골 쪽으로, 왼쪽 아래에서 비스듬히 (블록을 쪼개 틈을 벌린다)
    Wf.cracks = [(crack_line(rng, (0.3, HS + RO + TV), (0.45, 1.0), 1.5, 7), 0.05),
                 (crack_line(rng, (-1.9, ZP + 0.4), (-0.35, 1.0), 2.4, 8), 0.04)]
    Wf.face(-XW, XW, zs, 0.0, holes=[portal_zone], clip=gable_clip(-XW, XW, ZE, 0.0, ZA), plinth=0.05, missing=0.02)
    # 문 둘레: 바깥 겹, 안 겹 홍예석 + 문설주
    for (w_, rise, y0_, y1_) in ((WO, RO, 0.0, 0.32), (WI, RI, 0.32, TW + 0.02)):
        for tag, bm, c in arch_stones(rng, w_, HS, rise, TV, 5, y0_, y1_, gap, chips=(1, 2), k=k):
            Wf.add_bm(bm, Matrix.Identity(4))
        jamb_stones(Wf.acc, rng, w_, ZP, HS, TV, y0_, y1_, gap, hr=(0.4, 0.5), M=Wf.M, k=k)
    wh, rh = arch_grow(WO, HS, RO, TV + gap)
    for tag, bm, c in arch_stones(rng, wh, HS, rh, 0.15, 7, -0.13, 0.06, 0.02, chips=(0, 1), k=0.8):
        Wf.add_bm(bm, Matrix.Identity(4))
    for sx in (-1, 1):                                   # 돌림띠 끝 받침 (작은 까치발)
        bm = bm_box(0.24, 0.2, 0.26); bm_chip(bm, rng, 2, (0.015, 0.04))
        Wf.add_bm(bm, TR((sx * (wh / 2 + 0.07), -0.04, HS - 0.12)))
    # 기둥 (문 양옆 모서리의 가는 기둥: 받침·몸·머리)
    for sx in (-1, 1):
        x = sx * (WO / 2 - 0.04)
        Wf.add_bm(bm_box(0.36, 0.36, 0.24), TR((x, 0.3, ZP + 0.12)))
        Wf.add_bm(bm_cyl(0.13, HS - ZP - 0.5, 14), TR((x, 0.3, ZP + 0.24)))
        Wf.add_bm(bm_cyl(0.13, 0.22, 14, r2=0.22), TR((x, 0.3, HS - 0.28)))
        bm = bm_box(0.46, 0.46, 0.12); bm_chip(bm, rng, 2, (0.02, 0.05))
        Wf.add_bm(bm, TR((x, 0.3, HS - 0.04)))
    # 박공 갓돌 (경사를 따라)
    L = math.hypot(XW, ZA - ZE)
    th = math.atan2(ZA - ZE, XW)
    for sx in (-1, 1):
        s = 0.55
        while s < L - 0.15:
            ln = min(rng.uniform(0.55, 0.75), L - 0.12 - s)
            sm = s + ln / 2
            p = Vector((sx * (XW - sm * math.cos(th)), 0, ZE + sm * math.sin(th)))
            nrm = Vector((sx * math.sin(th), 0, math.cos(th)))
            bm = bm_box(ln - 0.03, TW + 0.18, 0.3)
            stone_blk(bm, rng, (1, 3), (0.02, 0.06), 0.014)
            Wf.add_bm(bm, Matrix.Translation(p + nrm * 0.12 + Vector((0, TW / 2, 0))) @ Matrix.Rotation(sx * th, 4, 'Y'))
            s += ln
        # 처마 끝 받침돌
        bm = bm_box(0.95, TW + 0.24, 0.6)
        stone_blk(bm, rng, (2, 4), (0.03, 0.07), 0.016)
        Wf.add_bm(bm, TR((sx * (XW - 0.3), TW / 2, ZE - 0.05)))
    # 꼭대기 십자가 (오른팔이 부러졌다)
    bm = bm_box(0.7, TW + 0.2, 0.36); stone_blk(bm, rng, (2, 3), (0.02, 0.05), 0.014)
    Wf.add_bm(bm, TR((0, TW / 2, ZA + 0.12)))
    Mc = TR((0, TW / 2, ZA + 0.28), (R(-4), R(7), 0))
    bm = bm_box(0.2, 0.2, 0.95); stone_blk(bm, rng, (1, 2), (0.015, 0.035), 0.01)
    Wf.add_bm(bm, Mc @ TR((0, 0, 0.47)))
    bm = bm_box(0.6, 0.19, 0.19); stone_blk(bm, rng, (1, 2), (0.015, 0.035), 0.01)
    Wf.add_bm(bm, Mc @ TR((0, 0, 0.66)))
    walls.append(Wf.acc.obj("crypt_front"))

    # ── 뒷벽 (박공, 갓돌 낮게) ──
    Wb = Wall(rng, TR((0, YB, 0)) @ Matrix.Rotation(R(180), 4, 'Z'), k=k, gap=gap, blen=(0.6, 1.15), skin=(0.32, 0.42), hr=(0.38, 0.48))
    Wb.face(-XW, XW, Wb.courses(ZP, ZA), 0.0, clip=gable_clip(-XW, XW, ZE, 0.0, ZA - 0.2), plinth=0.05)
    L2 = math.hypot(XW, ZA - 0.2 - ZE); th2 = math.atan2(ZA - 0.2 - ZE, XW)
    for sx in (-1, 1):
        s = 0.1
        while s < L2 - 0.1:
            ln = min(rng.uniform(0.55, 0.75), L2 - s)
            sm = s + ln / 2
            p = Vector((sx * (XW - sm * math.cos(th2)), 0, ZE + sm * math.sin(th2)))
            nrm = Vector((sx * math.sin(th2), 0, math.cos(th2)))
            bm = bm_box(ln - 0.03, 0.62, 0.22)
            stone_blk(bm, rng, (1, 3), (0.02, 0.06), 0.014)
            Wb.add_bm(bm, Matrix.Translation(p + nrm * 0.08 + Vector((0, 0.3, 0))) @ Matrix.Rotation(sx * th2, 4, 'Y'))
            s += ln
    walls.append(Wb.acc.obj("crypt_back"))

    # ── 옆벽 (벽감 둘씩, 처마 돌림띠와 까치발) ──
    niche_x = (-2.1, 2.2)                     # 옆벽 좌표 (벽 가운데 = 월드 y 0.5)
    NW, NHS, NR, NS, NT = 0.72, 2.25, 0.62, 1.25, 0.2
    for side in (-1, 1):
        M = TR((side * XW, 0.5, 0)) @ Matrix.Rotation(R(-90 if side < 0 else 90), 4, 'Z')
        Ws = Wall(rng, M, k=k, gap=gap, blen=(0.6, 1.15), skin=(0.32, 0.42), hr=(0.38, 0.48))
        holes = [[(x + nx, z) for x, z in arch_outline(NW, NHS, NR, grow=NT + gap, z_bottom=NS - 0.2, steps=8)] for nx in niche_x]
        Ws.face(-4.1, 4.1, Ws.courses(ZP, ZE - 0.26), 0.0, holes=holes, plinth=0.05, missing=0.03 if side < 0 else 0.015)
        for nx in niche_x:
            Mn = TR((nx, 0, 0))
            for tag, bm, c in arch_stones(rng, NW, NHS, NR, NT, 3, -0.03, 0.4, gap, chips=(1, 2), k=1.0):
                Ws.add_bm(bm, Mn)
            jamb_stones(Ws.acc, rng, NW, NS, NHS, NT, -0.03, 0.4, gap, hr=(0.3, 0.4), M=Ws.M @ Mn, k=1.0)
            bm = bm_box(NW + 2 * NT + 0.1, 0.5, 0.16); stone_blk(bm, rng, (2, 3), (0.02, 0.05), 0.012)
            Ws.add_bm(bm, TR((nx, 0.17, NS - 0.12)))
        # 처마 돌림띠 + 까치발
        x = -4.1
        while x < 4.1 - 0.2:
            ln = min(rng.uniform(0.7, 1.1), 4.1 - x)
            bm = bm_box(ln - 0.03, 0.62, 0.28); stone_blk(bm, rng, (1, 3), (0.02, 0.06), 0.014)
            Ws.add_bm(bm, TR((x + ln / 2, 0.16, ZE - 0.12)))
            x += ln
        for i in range(12):
            xx = -3.85 + 7.7 * i / 11
            if abs(xx + 0.1) < 0.6:
                continue
            bm = bm_wedge(0.2, 0.16, 0.24); bm_chip(bm, rng, 1, (0.015, 0.03))
            Ws.add_bm(bm, TR((xx, -0.06, ZE - 0.5)) @ Matrix.Rotation(R(180), 4, 'X') @ TR((0, 0, -0.24)))
        walls.append(Ws.acc.obj("crypt_side"))

    # ── 기단과 계단 ──
    Pl = Acc()
    plat = Wall(rng, None, k=k, gap=gap, blen=(0.7, 1.3), skin=(0.4, 0.5), hr=(0.3, 0.36))
    ym, yh = (PYF + PYB) / 2, (PYB - PYF) / 2
    for (M, x0, x1) in ((TR((0, PYF, 0)), -PX, PX), (TR((0, PYB, 0)) @ Matrix.Rotation(R(180), 4, 'Z'), -PX, PX),
                        (TR((-PX, ym, 0)) @ Matrix.Rotation(R(-90), 4, 'Z'), -yh, yh), (TR((PX, ym, 0)) @ Matrix.Rotation(R(90), 4, 'Z'), -yh, yh)):
        plat.M = M
        plat.face(x0, x1, [-0.2, 0.17, ZP - 0.13], 0.0, plinth=0.06)
    # 윗면 판석 (가장자리, 몇 장은 들리고 깨지고 빠졌다)
    def pave(x0, x1, y0, y1):
        y = y0
        while y < y1 - 0.15:
            dy = min(rng.uniform(0.5, 0.75), y1 - y)
            x = x0 + rng.uniform(-0.2, 0)
            while x < x1 - 0.15:
                dx = min(rng.uniform(0.55, 0.9), x1 - x)
                if rng.random() > 0.05:
                    bm = bm_box(dx - 0.035, dy - 0.035, 0.14)
                    if rng.random() < 0.18:
                        bm_break(bm, rng, (rng.uniform(-0.1, 0.1), 0, 0), (rng.choice((-1, 1)), rng.uniform(-0.8, 0.8), 0.2), facets=2)
                    stone_blk(bm, rng, (1, 3), (0.02, 0.05), 0.012, flakes=(0, 1))
                    tl = 2.5 if rng.random() < 0.2 else 0.6
                    plat.acc.add(bm, TR((x + dx / 2, y + dy / 2, ZP - 0.06 + rng.uniform(-0.03, 0.02)),
                                        (R(rng.uniform(-tl, tl)), R(rng.uniform(-tl, tl)), R(rng.uniform(-1.5, 1.5)))))
                x += dx
            y += dy
    pave(-PX, PX, PYF, YF + 0.05)
    pave(-PX, -XW + 0.05, YF, YB + 0.05)
    pave(XW - 0.05, PX, YF, YB + 0.05)
    pave(-PX, PX, YB - 0.05, PYB)
    pave(-WI / 2, WI / 2, YF, YF + TW + 0.3)                     # 문턱 안쪽
    # 계단 3단
    for i in range(3):
        y0_, y1_ = PYF - 0.45 * (3 - i), PYF - 0.45 * (2 - i)
        ztop = ZP * (i + 1) / 3
        x = -1.95
        while x < 1.95 - 0.2:
            ln = min(rng.uniform(0.8, 1.4), 1.95 - x)
            bm = bm_box(ln - 0.035, (y1_ - y0_) + (0.3 if i < 2 else 0.0), ztop + 0.15)
            if i == 0 and x + ln > 1.5:
                bm_break(bm, rng, (ln * 0.2, -0.1, 0.05), (1, -0.6, 0.5), facets=3, spread=0.5)
            stone_blk(bm, rng, (2, 4), (0.025, 0.07), 0.014)
            sink = -0.06 if (i == 0 and x > 0.5) else 0.0
            plat.acc.add(bm, TR((x + ln / 2, (y0_ + y1_) / 2 + (0.15 if i < 2 else 0), (ztop - 0.15) / 2 + sink),
                                (R(rng.uniform(-0.8, 0.8)) + (R(-2.5) if sink else 0), R(rng.uniform(-0.8, 0.8)), R(rng.uniform(-1, 1)))))
            x += ln
    walls.append(plat.acc.obj("crypt_plinth"))

    # ── 버팀벽과 뾰족탑 ──
    Bt = Acc()
    fallen_top = None
    for sx in (-1, 1):
        buttress(Bt, rng, sx * (XW + 0.1), YF - 0.1, 0.9, 0.9, [(ZP - 0.05, 3.2, 0.9, 0.9), (3.2, 4.75, 0.72, 0.72)], out=(0, -1), k=1.0)
        t = pinnacle(Bt, rng, sx * (XW + 0.1), YF, 4.95, 0.5, 0.75, 1.1, broken=(sx > 0))
        if t is not None:
            fallen_top = t
        buttress(Bt, rng, sx * (XW + 0.3), 0.5, 0.8, 0.6, [(ZP - 0.05, 2.6, 0.8, 0.6), (2.6, 3.7, 0.7, 0.42)], out=(sx, 0), k=1.0)
        buttress(Bt, rng, sx * (XW + 0.15), YB + 0.1, 0.85, 0.85, [(ZP - 0.05, 3.6, 0.85, 0.85), (3.6, 4.7, 0.66, 0.66)], out=(0, 1), k=1.0)
        pinnacle(Bt, rng, sx * (XW + 0.15), YB + 0.1, 4.95, 0.44, 0.55, 0.85, broken=False)
    # 떨어진 뾰족탑 머리 (오른쪽 앞 땅에 누웠다) + 부러진 몸 토막
    if fallen_top is not None:
        bm_break(fallen_top, rng, (0, 0, 0.75), (0.3, 0.4, 1), facets=2, spread=0.4)
        Bt.add(fallen_top, TR((4.75, -4.55, 0.32), (R(78), R(12), R(35))))
    bm = bm_box(0.5, 0.5, 0.62)
    bm_break(bm, rng, (0.05, 0, 0.12), (0.7, -0.5, 1), facets=3, spread=0.6, jitter=0.06)
    bm_break(bm, rng, (-0.12, 0.05, 0.25), (-0.4, 0.3, 1), facets=2, spread=0.5)
    stone_blk(bm, rng, (2, 4), (0.03, 0.06), 0.014)
    Bt.add(bm, TR((XW + 0.1, YF, 4.95 + 0.27)))
    walls.append(Bt.obj("crypt_buttress"))

    # ── 지붕 판석 (박공 두 면, 뒤쪽 오른편이 꺼졌다) ──
    Rf = Acc()
    ZR = ZA - 0.32                                # 용마루 높이
    XE = XW + 0.18                                # 처마 끝
    ZEE = ZE + 0.02
    Ls = math.hypot(XE, ZR - ZEE)
    pitch = math.atan2(ZR - ZEE, XE)
    hole_c = Vector((1.6, 2.4))
    for sx in (-1, 1):
        s = 0.0
        row = 0
        while s < Ls - 0.2:
            y = YF + TW - 0.12 + rng.uniform(-0.1, 0.0)
            while y < YB - 0.5:
                w_ = min(rng.uniform(0.5, 0.75), YB - 0.38 - y)
                sm = s + 0.33
                p = Vector((sx * (XE - sm * math.cos(pitch)), y + w_ / 2, ZEE + sm * math.sin(pitch)))
                inhole = (Vector((p.x, p.y)) - hole_c).length < 1.05 + rng.uniform(-0.25, 0.25) and sx > 0
                if not inhole and rng.random() > 0.015:
                    bm = bm_box(0.68, w_ - 0.04, 0.085)
                    if rng.random() < 0.12:
                        bm_break(bm, rng, (rng.uniform(-0.2, 0.0), 0, 0), (-1, rng.uniform(-0.7, 0.7), 0.3), facets=2, spread=0.4)
                    bm_chip(bm, rng, rng.randint(1, 3), (0.015, 0.045))
                    bm_bevel(bm, 0.01)
                    slip = rng.uniform(-0.03, 0.03) + (0.12 if rng.random() < 0.04 else 0.0)
                    nrm = Vector((sx * math.sin(pitch), 0, math.cos(pitch)))
                    M = Matrix.Translation(p + nrm * 0.05 + Vector((sx * slip * math.cos(pitch), 0, -slip * math.sin(pitch)))) @ \
                        Matrix.Rotation(sx * (pitch - R(3.0)), 4, 'Y') @ Matrix.Rotation(R(rng.uniform(-1.5, 1.5)), 4, 'Z')
                    Rf.add(bm, M)
                y += w_
            s += 0.48
            row += 1
    # 용마루 돌
    y = YF + TW - 0.1
    while y < YB - 0.5:
        ln = min(rng.uniform(0.6, 0.8), YB - 0.38 - y)
        poly = [(-0.3, -0.12), (0.3, -0.12), (0.0, 0.2)]
        bm = bm_poly(poly, -ln / 2 + 0.02, ln / 2 - 0.02, 'y')
        bm_chip(bm, rng, 2, (0.02, 0.05))
        if not ((Vector((0.0, y)) - hole_c).length < 1.2):
            Rf.add(bm, TR((0, y + ln / 2, ZR + 0.08), (0, R(rng.uniform(-2, 2)), 0)))
        y += ln
    walls.append(Rf.obj("crypt_roof"))

    # ── 속 (건물 몸통) : 문 안쪽 어둠, 벽감, 지붕 구멍을 판다 ──
    core = Acc()
    zr_edge = ZEE + (XE - (XW - 0.2)) * math.tan(pitch) + 0.025 / math.cos(pitch)       # 판석 밑면과 겹치게 (얇은 틈이 굽기에서 검은 얼룩이 된다)
    poly = [(-XW + 0.2, ZP - 0.2), (XW - 0.2, ZP - 0.2), (XW - 0.2, zr_edge), (0.0, ZR + 0.025 / math.cos(pitch)), (-XW + 0.2, zr_edge)]
    core.add(bm_poly(poly, YF + 0.25, YB - 0.25, 'y'))
    core.add(bm_box(2 * PX - 0.3, PYB - PYF - 0.3, ZP + 0.1), TR((0, (PYF + PYB) / 2, (ZP - 0.25) / 2 - 0.05)))
    co = core.obj("crypt_core")
    cutters = [zone_prism(arch_outline(WO, HS, RO, grow=0.0, z_bottom=ZP), YF - 0.1, YF + 0.32),
               zone_prism(arch_outline(WI, HS, RI, grow=0.0, z_bottom=ZP), YF + 0.3, YF + 2.2),
               chunk((hole_c.x, hole_c.y, ZR - 1.7), (1.05, 0.95, 1.5), rng, 10, (0.05, 0.2))]
    for side in (-1, 1):
        for nx in niche_x:
            wy = 0.5 - nx if side < 0 else 0.5 + nx
            a = Acc()
            a.add(bm_poly(arch_outline(NW, NHS, NR, grow=0.0, z_bottom=NS), -0.35, 0.35, 'y'),
                  TR((side * XW, wy, 0)) @ Matrix.Rotation(R(90), 4, 'Z'))
            cutters.append(a.obj("niche_cut"))
    cut(co, cutters, voxel=0.03)
    walls.append(co)

    # ── 앞벽 금 (문 아치 꼭대기에서 해골 아래로) + 떨어진 블록 ──
    fallen = Acc()
    ext = []
    fallen_block(fallen, rng, (4.3, -1.4, 0), (0.7, 0.45, 0.4), k=k)
    fallen_block(fallen, rng, (-4.4, 2.6, 0), (0.8, 0.5, 0.38), k=k)
    fallen_block(fallen, rng, (4.5, 3.4, 0), (0.62, 0.5, 0.36), k=k)
    rubble_pile(fallen, rng, (4.75, -3.6, 0), 0.85, 10, (0.2, 0.42), 0.5, extra=ext, k=k)
    walls.append(fallen.obj("crypt_fallen"))

    # ── 해골 부조 (날개) ──
    SKZ, SKS = 5.92, 1.28
    sk, eyes = skull_relief((0, YF - 0.1, SKZ), SKS, wings=True, rng=rng)
    # ── 벽감 안: 항아리, 해골 ──
    urns = []
    a = Acc()
    v, f = lathe([(0.0, 0.0), (0.12, 0.0), (0.13, 0.03), (0.08, 0.06), (0.08, 0.1), (0.15, 0.18), (0.19, 0.3), (0.17, 0.4),
                  (0.1, 0.47), (0.08, 0.5), (0.11, 0.54), (0.11, 0.57), (0.0, 0.58)], 20, (-XW + 0.15, 0.5 - niche_x[1], NS - 0.01))
    a.add_raw(v, f)
    urns.append(a.obj("urn"))
    sk2 = blobs([((0, 0, 0.12), (0.12, 0.14, 0.11)), ((0, -0.08, 0.06), (0.09, 0.07, 0.07)), ((0, -0.06, 0.0), (0.07, 0.06, 0.05))], 2, "nskull")
    sk2.data.transform(TR((XW - 0.15, 0.5 + niche_x[0], NS - 0.02), (0, 0, R(100))))
    urns.append(sk2)

    body = join(walls + ext + [sk] + urns)
    # v3 (k7b): wall_ruin_a 레시피 — carve+STONE3 (저폴리는 되붙이지 않은 바탕에서), paint_block3 (회갈색 때, 군데군데 빗물, 짙은 올리브 이끼),
    # finish3 cage 굽기. 쇠문은 이전 칠 그대로
    base = carve(body, 0.017 * VOX, *STONE3(1.4, wear=1.2, cracks=0.6), seed=111, base=True)
    m = paint_block3("crypt_src", h=7.8, k=1.4, ao=0.6, dirt_h=1.0, moss_low_h=1.4, grime_h=0.22)
    tint_near(m, (0, YF + 1.3, 2.2), 1.5, (0.012, 0.008, 0.02), 0.95)          # 문 안쪽 어둠
    tint_near(m, (hole_c.x, hole_c.y, ZR - 1.9), 1.5, (0.015, 0.01, 0.025), 0.95)   # 꺼진 지붕 속 어둠
    tint_near(m, (0, YF - 0.3, SKZ), 0.75, (0.3, 0.12, 0.5), 0.35)            # 눈빛에 물든 돌
    tears(m, [(-0.13 * SKS, SKZ - 0.16 * SKS), (0.13 * SKS, SKZ - 0.16 * SKS)], 1.3, 0.05, 0.85)
    set_mat(body, m)

    # ── 철문 (왼쪽 닫힘, 오른쪽이 안으로 살짝 열려 어둠이 보인다) ──
    iron = Acc()
    iron_door_leaf(iron, WI / 2, HS, WI, HS, RI, -WI / 2, 1)
    left = iron.obj("door_l"); left.data.transform(TR((0, YF + TW - 0.02, 0)))
    iron2 = Acc()
    iron_door_leaf(iron2, WI / 2, HS, WI, HS, RI, WI / 2, -1)
    right = iron2.obj("door_r")
    right.data.transform(TR((WI / 2, YF + TW - 0.02, 0)) @ Matrix.Rotation(R(-40), 4, 'Z') @ TR((-WI / 2, 0, 0)))
    io = join([left, right])
    ih = iron_high(io, 0.007, 112)
    ih.data.materials[0] = iron_mat("crypt_iron_src", 112)

    low = low_of(base, 17000)
    delete(base)
    vines = ivy_on(low, [((-XW - 0.6, YF - 0.55, ZP + 0.05), 3, 7.5, 9), ((-XW - 0.05, -1.4, ZP + 0.05), 5, 5.0, 6),
                         ((-PX - 0.1, YF - 0.9, 0.05), 9, 3.0, 4)], 31, leaf=(0.07, 0.12), leaf_p=0.34,
                   hangs=[((-2.4, YF - 0.12, ZE + 0.7), 1.6, (0, -1, 0)), ((-1.5, YF - 0.12, ZE + 1.55), 1.1, (0, -1, 0)),
                          ((-XW - 0.1, -2.0, ZE - 0.3), 1.4, (-1, 0, 0)), ((-XW - 0.1, 1.6, ZE - 0.3), 0.9, (-1, 0, 0))])
    webs = [web_dim((-WI / 2 - 0.02, YF + 0.36, HS + 0.15), (1, 0, 0), (0, 0, -1), 0.42)]
    return finish3("crypt", [body, ih], [low, io], extras=[eyes] + vines + webs, far_extras=[eyes], size=2048, cage=0.012, cage_reach=0.12,
                   lod1=0.35, lod2=0.12, uv_margin=0.001)


# ═════════════════════════ 큰 구조물 부품 ═════════════════════════
def circle_poly(cx, cz, r, n=28):
    return [(cx + r * math.cos(2 * math.pi * i / n), cz + r * math.sin(2 * math.pi * i / n)) for i in range(n)]

def ring_stones(acc, rng, cx, cz, r0, r1, n, y0, y1, gap, M=None, skip=(), k=1.0, drop=()):
    """XZ 평면의 둥근 고리를 n 개 돌로 (장미창 테·둥근 창). skip: 빠진 돌 번호, drop: 조금 내려앉은 돌 번호"""
    for i in range(n):
        if i in skip:
            continue
        a0 = 2 * math.pi * i / n + gap / (2 * r0)
        a1 = 2 * math.pi * (i + 1) / n - gap / (2 * r0)
        m = 4
        outer = [(cx + r1 * math.cos(a0 + (a1 - a0) * t / m), cz + r1 * math.sin(a0 + (a1 - a0) * t / m)) for t in range(m + 1)]
        inner = [(cx + r0 * math.cos(a1 - (a1 - a0) * t / m), cz + r0 * math.sin(a1 - (a1 - a0) * t / m)) for t in range(m + 1)]
        bm = bm_poly(ccw(outer + inner), y0 + rng.uniform(-0.01, 0.01) * k, y1 + rng.uniform(-0.01, 0.01) * k, 'y')
        stone_blk(bm, rng, (1, 2), (0.02 * k, 0.05 * k), 0.012 * k, flakes=(0, 1))
        D = TR((0, 0, -0.04 * k)) if i in drop else Matrix.Identity(4)
        acc.add(bm, (M @ D) if M is not None else D)

def top_rubble(rng, top, x0, x1, y0, y1, n, M=None, keep=None, k=1.0, drop=0.13):
    """무너진 윗면(심) 위에 얹힌 잔돌 덩어리"""
    out = []
    for i in range(n):
        x = x0 + (x1 - x0) * (i + rng.random()) / n
        s_ = rng.uniform(0.1, 0.22) * k
        if keep is not None and not keep(x, top(x) - drop * k):
            continue
        p = Vector((x, rng.uniform(y0 + 0.14 * k, y1 - 0.14 * k), top(x) - drop * k + s_ * 0.25))
        c = chunk((0, 0, 0), (s_, s_ * rng.uniform(0.6, 0.9), s_ * 0.6), rng, 8)
        c.data.transform((M if M is not None else Matrix.Identity(4)) @ Matrix.Translation(p))
        c.data.update()
        out.append(c)
    return out

def core_poly(x0, x1, top, z0, step=0.3, drop=0.2, jag=0.15, rng=None):
    """벽 심 윤곽 (XZ): 윗선보다 조금 낮고 들쭉날쭉하게"""
    rng = rng or random.Random(0)
    xs = lin(x0, x1, max(2, int((x1 - x0) / step) + 1))
    tops = [max(z0 + 0.1, top(x) - drop - rng.uniform(0, jag)) for x in xs]
    return [(xs[0], z0), (xs[-1], z0)] + [(x, z) for x, z in reversed(list(zip(xs, tops)))]

def tracery(rng, W, sill, h_s, rise, y0, y1, M, mull=0.3, frame=0.14, broken=(), k=1.0):
    """창 안 돌 창살: 가운데 기둥 + 작은 뾰족 아치 둘 + 위 둥근 창. 창 모양 판에서 빛 칸을 파낸다.
    broken: [(점(x,z), 크기)] 깨져 떨어져 나간 자리. 돌아오는 것: (객체, 빛 칸 윤곽 목록)"""
    a = Acc()
    a.add(bm_poly(ccw(arch_outline(W, h_s, rise, grow=0.03, z_bottom=sill)), y0, y1, 'y'))
    slab = a.obj("tracery")
    wl = (W - 2 * frame - mull) / 2
    cl = mull / 2 + wl / 2
    hl = h_s - 0.15 * k
    lights = []
    cuts = []
    for sx in (-1, 1):
        ol = [(x + sx * cl, z) for x, z in arch_outline(wl, hl, wl * 0.95, z_bottom=sill + 0.1 * k)]
        lights.append(ol)
        cuts.append(zone_prism(ol, y0, y1, M=None))
    zl = hl + wl * 0.95
    za = h_s + rise
    cx_, r_, _ = arch_geo(W, h_s, rise)
    zo = (zl + za) / 2 - 0.05 * k
    half = cx_ + math.sqrt(max(0.0, r_ * r_ - (zo - h_s) ** 2))
    ro = max(0.15, min((za - zl) / 2 - 0.16 * k, half - 0.22 * k))
    oc = circle_poly(0, zo, ro, 24)
    lights.append(oc)
    cuts.append(zone_prism(oc, y0, y1))
    for (bx, bz), bs in broken:
        cuts.append(chunk((bx, (y0 + y1) / 2, bz), (bs, bs, bs), rng, 9, (0.05, 0.25)))
    kit.cut(slab, cuts)
    slab.data.transform(M)
    return slab, [[(M @ Vector((x, 0, z))) for x, z in L] for L in lights]

def glass_shards(rng, light_pts, n, y, size=(0.15, 0.4), name='Glow_Soul', normal=(0, -1, 0)):
    """빛 칸 가장자리에 남은 깨진 유리 조각 (발광). light_pts: 월드 좌표 점 목록 (윤곽)"""
    verts, faces = [], []
    cen = sum(light_pts, Vector()) / len(light_pts)
    for _ in range(n):
        p = rng.choice(light_pts)
        q = p.lerp(cen, rng.uniform(0.05, 0.25))
        s_ = rng.uniform(*size)
        nn = Vector(normal).normalized()
        u = nn.orthogonal().normalized()
        v = nn.cross(u)
        base = len(verts)
        pts = []
        m = rng.randint(3, 5)
        for j in range(m):
            a = 2 * math.pi * j / m + rng.uniform(-0.4, 0.4)
            rr = s_ * rng.uniform(0.4, 1.0)
            pts.append(q + (u * math.cos(a) + v * math.sin(a)) * rr * 0.5)
        # 윤곽 쪽으로 붙인다 (가운데로 뻗지 않게)
        verts += pts
        faces.append(tuple(range(base, base + m)))
    if not faces:
        return None
    o = mesh_from("shards", verts, faces)
    return glow(o, name)

def flyer(acc, rng, x_wall, x_pier, z_wall_top, z_pier_top, z_wall_low, z_pier_low, y0, y1, n=7, gap=0.06, k=1.0):
    """플라잉 버트레스 다리: 벽(x_wall) 높은 쪽 → 기둥(x_pier) 낮은 쪽. 아랫면은 1/4 타원 (벽에서 수평, 기둥에서 수직), 윗면은 곧은 경사"""
    a_ = x_pier - x_wall
    b_ = z_wall_low - z_pier_low
    def under(x):
        u = min(1.0, max(0.0, (x - x_wall) / a_))
        return z_pier_low + b_ * math.sqrt(max(0.0, 1 - u * u))
    def topz(x):
        u = (x - x_wall) / a_
        return z_wall_top + (z_pier_top - z_wall_top) * u
    for i in range(n):
        xa = x_wall + a_ * i / n + gap / 2
        xb = x_wall + a_ * (i + 1) / n - gap / 2
        xs = lin(xa, xb, 6)
        poly = [(x, under(x)) for x in xs] + [(x, topz(x)) for x in reversed(xs)]
        bm = bm_poly(ccw(poly), y0 + rng.uniform(-0.02, 0.02), y1 + rng.uniform(-0.02, 0.02), 'y')
        stone_blk(bm, rng, (1, 2), (0.03 * k, 0.07 * k), 0.016 * k, flakes=(0, 1))
        acc.add(bm)
    # 윗면 갓돌 (경사를 따라)
    L = math.hypot(x_pier - x_wall, z_pier_top - z_wall_top)
    th = math.atan2(z_pier_top - z_wall_top, x_pier - x_wall)
    m = max(2, int(L / 1.1))
    for i in range(m):
        s0 = L * i / m
        p = Vector((x_wall, 0, z_wall_top)) + Vector((math.cos(th), 0, math.sin(th))) * (s0 + L / m / 2)
        bm = bm_box(L / m - gap, (y1 - y0) + 0.2 * k, 0.32 * k)
        stone_blk(bm, rng, (1, 2), (0.03 * k, 0.06 * k), 0.014 * k)
        acc.add(bm, Matrix.Translation(p + Vector((0, (y0 + y1) / 2, 0.08 * k))) @ Matrix.Rotation(-th, 4, 'Y'))

def pier_stack(acc, rng, x, y, w, d, z0, z1, k=1.0, hr=(0.55, 0.75), gap=0.06):
    """네모 돌기둥 (켜마다 한 덩이 또는 둘)"""
    z = z0
    i = 0
    while z < z1 - hr[0] * 0.4:
        h = min(rng.uniform(*hr), z1 - z)
        if i % 2 == 0:
            pcs = [(x, y, w, d)]
        else:
            pcs = [(x - w / 4, y, w / 2 - gap / 2, d), (x + w / 4, y, w / 2 - gap / 2, d)]
        for (px, py, pw, pd) in pcs:
            bm = bm_box(pw - gap, pd - gap, h - gap)
            stone_blk(bm, rng, (1, 3), (0.03 * k, 0.08 * k), 0.016 * k)
            acc.add(bm, TR((px, py, z + h / 2), (0, 0, R(rng.uniform(-0.5, 0.5)))))
        z += h
        i += 1
    return z

def half_column(acc, rng, x, y, r, z0, z1, axis_out=(0, -1), k=1.0, seg=12, cap=True):
    """벽에 붙은 둥근 기둥 (북 여러 토막 + 받침 + 머리)"""
    z = z0
    while z < z1 - 0.3 * k:
        h = min(rng.uniform(0.6, 0.9) * k, z1 - z)
        acc.add(bm_cyl(r, h - 0.04 * k, seg), TR((x, y, z)))
        z += h
    b = bm_box(r * 2.6, r * 2.6, 0.4 * k); bm_chip(b, rng, 2, (0.03 * k, 0.07 * k))
    acc.add(b, TR((x, y, z0 + 0.2 * k)))
    if cap:
        c = bm_cyl(r, 0.45 * k, seg, r2=r * 1.7)
        acc.add(c, TR((x, y, z1 - 0.45 * k)))
        b = bm_box(r * 3.6, r * 3.6, 0.22 * k); bm_chip(b, rng, 2, (0.03 * k, 0.06 * k))
        acc.add(b, TR((x, y, z1 + 0.11 * k)))


# ═════════════════════════ 무너진 대성당 ═════════════════════════
def cathedral_ruin():
    rng = random.Random(2202)
    k = 2.2
    gap = 0.11
    XI, XO = 5.0, 6.1                 # 신랑 안쪽·바깥 벽면 (±x)
    YF, YE = -16.0, 17.0              # 정면 바깥면, 동쪽 끝 바깥면
    TF = 1.2                          # 정면 벽 두께
    ZE = 15.0                         # 벽 높이 (처마)
    hr, blen, skin = (0.55, 0.78), (0.9, 1.9), (0.42, 0.55)
    bays = [YF + TF + 6.16 * i for i in range(6)]           # 칸 경계 (안쪽 기준)
    centers = [(bays[i] + bays[i + 1]) / 2 for i in range(5)]
    WW, WS, WH, WR, WT = 2.5, 4.4, 10.6, 2.7, 0.55          # 옆벽 창: 폭, 창턱, 아치 시작, 솟음, 홍예석 두께
    hi_parts = []
    glows = []
    ym = (YF + YE) / 2
    hl = (YE - YF) / 2

    # ── 옆벽 둘 ──
    side_tops = {
        1: profile([(-hl, 14.6), (-12, 15.0), (-6, 14.4), (-2.0, 13.2), (0.5, 15.0), (6, 14.7), (9.5, 12.6), (12, 10.8), (14.5, 12.4), (hl, 11.0)]),
        -1: profile([(-hl, 13.6), (-12, 14.2), (-7.5, 13.8), (-3.0, 12.9), (-1.0, 8.5), (0.6, 5.2), (2.5, 3.6), (5.0, 6.0), (7.0, 11.5), (9.0, 13.6), (12.5, 14.4), (hl, 13.0)]),
    }
    win_tracery = {1: (0, 2, 4), -1: (4,)}
    for side in (1, -1):
        M = TR((side * XO, ym, 0)) @ Matrix.Rotation(R(90 if side > 0 else -90), 4, 'Z')
        Ws = Wall(rng, M, k=k, gap=gap, blen=blen, skin=skin, hr=hr, rot=0.6)
        top = side_tops[side]
        # 벽 좌표 x: 오른쪽 벽(side=1)은 월드 y 방향, 왼쪽 벽은 -y 방향
        wx = [(c - ym) * side for c in centers]
        holes = [[(x + cx, z) for x, z in arch_outline(WW, WH, WR, grow=WT + gap, z_bottom=WS - 0.3, steps=10)] for cx in wx]
        zs = Ws.courses(-0.2, ZE + 0.6)
        if side < 0:
            Ws.cracks = [(crack_line(rng, ((bays[4] - ym) * side, 0.5), (0.2, 1.0), 9.0, 10), 0.09)]
        Ws.face(-hl, hl, zs, 0.0, top=top, holes=holes, outward=-1, plinth=0.12, missing=0.02, broken=0.45)
        ia, ib = sorted(((YF + TF - ym) * side, (YE - (XO - XI) - ym) * side))
        Ws.face(ia, ib, zs, XO - XI, top=top, holes=holes, outward=1, missing=0.02, broken=0.45)
        for i, cx in enumerate(wx):
            Mw = TR((cx, 0, 0))
            if top(cx) < WS + 1.0:
                continue
            for tag, bm, c in arch_stones(rng, WW, WH, WR, WT, 7, -0.04, XO - XI + 0.04, gap, chips=(1, 2), k=k):
                if c.z > top(cx + c.x) - 0.2:
                    bm.free(); continue
                Ws.add_bm(bm, Mw)
            jambs_top(Ws.acc, rng, WW, WS, WH, WT, -0.04, XO - XI + 0.04, gap, hr, Ws.M @ Mw, k, top=top, cx=cx)
            bm = bm_box(WW + 2 * WT + 0.3, XO - XI + 0.3, 0.3); stone_blk(bm, rng, (2, 3), (0.04, 0.09), 0.02)
            Ws.add_bm(bm, TR((cx, (XO - XI) / 2, WS - 0.2)))
            if i in win_tracery[side] and top(cx) > WH + WR:
                br = [((rng.uniform(-0.6, 0.6), WH + rng.uniform(0.5, 2.0)), 0.5)] if rng.random() < 0.6 else []
                tr, lights = tracery(rng, WW, WS, WH, WR, (XO - XI) / 2 - 0.22, (XO - XI) / 2 + 0.22, Ws.M @ Mw, broken=br, k=k)
                hi_parts.append(tr)
                if side > 0:
                    for L in lights[2:]:
                        g = glass_shards(rng, L, 5, 0, (0.18, 0.35), normal=(1, 0, 0))
                        if g:
                            glows.append(g)
        # 바깥 버팀벽 (칸 경계, 오른쪽은 플라잉 버트레스가 대신한다)
        bo = Sub(Ws.acc, Ws.M)
        for j, by in enumerate(bays[1:-1]):
            bx = (by - ym) * side
            tb = top(bx)
            if side > 0:
                bo.add(bm_box(1.3, 0.7, min(tb, 13.5)), TR((bx, -0.3, min(tb, 13.5) / 2)))     # 벽에 붙은 얕은 기둥 (날개 다리가 닿는 곳)
                continue
            hb = min(tb + 0.5, 12.5)
            if hb < 3:
                continue
            stages = [(-0.2, hb * 0.45, 1.4, 1.9), (hb * 0.45, hb * 0.8, 1.25, 1.4), (hb * 0.8, hb, 1.1, 0.9)]
            for (z0, z1, ww, dd) in stages:
                pier_stack(bo, rng, bx, -dd / 2 + 0.2, ww, dd, z0, z1, k=k * 0.9, hr=hr, gap=gap)
                bm = bm_wedge(ww + 0.15, dd + 0.15, 0.6); bm_chip(bm, rng, 2, (0.04, 0.09))
                bo.add(bm, TR((bx, -dd / 2 + 0.2, z1 - 0.04)))
        # 안쪽 벽기둥 (칸 경계, 늑골 아치가 시작되는 곳)
        for by in bays[1:-1]:
            bx = (by - ym) * side
            zt = min(top(bx) - 0.3, 13.0)
            if zt > 2.5:
                half_column(bo, rng, bx, XO - XI + 0.12, 0.36, 0.0, zt, k=k * 0.8, cap=zt > 12.5)
        hi_parts.append(Ws.acc.obj("cath_side"))
        # 심
        cp = core_poly(-hl + 0.3, hl - 0.3, top, -0.3, step=0.4, drop=0.3, jag=0.25, rng=rng)
        a = Acc(); a.add(bm_poly(ccw(cp), 0.3, XO - XI - 0.3, 'y'), M)
        co = a.obj("cath_core")
        kit.cut(co, [zone_prism(arch_outline(WW, WH, WR, grow=0.0, z_bottom=WS), -0.5, 2.0, M @ TR((cx, 0, 0))) for cx in wx])
        hi_parts.append(co)
        hi_parts += top_rubble(rng, top, -hl + 0.6, hl - 0.6, 0.0, XO - XI, 70, M, k=k * 0.8, drop=0.2)

    # ── 정면 (박공, 장미창, 정문) ──
    Mf = TR((0, YF, 0))
    Wf = Wall(rng, Mf, k=k, gap=gap, blen=blen, skin=skin, hr=hr, rot=0.6)
    ZA = 22.5
    ftop = profile([(-XO, 30), (-2.4, 30), (-1.2, 21.0), (0.4, 19.6), (1.6, 20.4), (3.2, 19.0), (XO, 30)])
    fclip = gable_clip(-XO - 0.6, XO + 0.6, ZE, 0.0, ZA)
    PW, PH, PR, PT = 3.4, 4.8, 3.0, 0.62               # 정문 안쪽 겹
    PWO = PW + 2 * PT + 0.1
    pw2, pr2 = arch_grow(PW, PH, PR, PT + gap)
    RC, RR, RT = 13.3, 3.0, 0.62                        # 장미창 중심 높이, 반지름, 테 두께
    holes = [arch_outline(pw2, PH, pr2, grow=PT + gap, z_bottom=-0.3), circle_poly(0, RC, RR + RT + gap, 32)]
    zs = Wf.courses(-0.2, ZA + 0.5)
    Wf.cracks = [(crack_line(rng, (1.2, PH + PR + 1.5), (0.25, 1.0), 3.0, 6), 0.08)]
    Wf.face(-XO - 0.6, XO + 0.6, zs, 0.0, top=ftop, holes=holes, clip=fclip, plinth=0.12, missing=0.015)
    Wf.face(-XI, XI, zs, TF, top=ftop, holes=holes, clip=fclip, outward=1, missing=0.02)
    for (w_, rise, T_, y0_, y1_) in ((PW, PR, PT, 0.55, TF + 0.04), (pw2, pr2, PT, -0.06, 0.6)):
        for tag, bm, c in arch_stones(rng, w_, PH, rise, T_, 7, y0_, y1_, gap, chips=(1, 2), k=k):
            Wf.add_bm(bm, Matrix.Identity(4))
        jamb_stones(Wf.acc, rng, w_, 0.0, PH, T_, y0_, y1_, gap, hr=hr, M=Wf.M, k=k)
    wh, rh = arch_grow(pw2, PH, pr2, PT + gap)
    for tag, bm, c in arch_stones(rng, wh, PH, rh, 0.26, 9, -0.25, 0.05, 0.04, chips=(0, 1), k=1.4):
        Wf.add_bm(bm, Matrix.Identity(4))
    for sx in (-1, 1):
        x = sx * (pw2 / 2 - 0.05)
        half_column(Sub(Wf.acc, Mf), rng, x, 0.55, 0.24, 0.0, PH - 0.45, k=k * 0.7)
    # 장미창: 바깥 테 (돌 한 바퀴) + 바퀴살 창살 + 가운데 고리
    ring_stones(Wf.acc, rng, 0, RC, RR, RR + RT, 20, -0.05, TF + 0.05, gap, Mf, skip=(3,), k=k, drop=(4,))
    ring_stones(Wf.acc, rng, 0, RC, RR + RT + 0.02, RR + RT + 0.3, 24, -0.25, 0.05, 0.05, Mf, skip=(2, 3, 4), k=1.3)
    ring_stones(Wf.acc, rng, 0, RC, 0.55, 0.95, 8, TF / 2 - 0.25, TF / 2 + 0.25, 0.05, Mf, k=1.4)
    ring_stones(Wf.acc, rng, 0, RC, 1.85, 2.1, 16, TF / 2 - 0.2, TF / 2 + 0.2, 0.05, Mf, skip=(5, 6, 7), k=1.2)
    spokes_missing = (2, 3, 4, 9)
    for i in range(12):
        if i in spokes_missing:
            continue
        a_ = 2 * math.pi * (i + 0.5) / 12
        L = RR + 0.1 - 0.9
        bm = bm_box(L, 0.4, 0.24)
        if i == 5:
            bm_break(bm, rng, (L * 0.15, 0, 0), (1, 0.3, 0.2), facets=3, spread=0.4)
        stone_blk(bm, rng, (1, 1), (0.02, 0.05), 0.012)
        Wf.add_bm(bm, TR((math.cos(a_) * (0.9 + L / 2), TF / 2, RC + math.sin(a_) * (0.9 + L / 2)), (0, -a_, 0)))
    # 장미창 안 희미한 영혼 빛: 가운데 고리 안 원판 + 바깥 칸에 남은 유리 조각
    gd = mesh_from("rose_core", [Mvec for Mvec in [Mf @ Vector((0.5 * math.cos(2 * math.pi * i / 16), TF / 2, RC + 0.5 * math.sin(2 * math.pi * i / 16))) for i in range(16)]], [tuple(range(16))])
    glows.append(glow(gd, 'Glow_Soul'))
    for i in range(12):
        if i in spokes_missing or rng.random() < 0.35:
            continue
        a_ = 2 * math.pi * i / 12
        pts = [Mf @ Vector((math.cos(a_ + d) * rr, TF / 2 + 0.03, RC + math.sin(a_ + d) * rr)) for d, rr in ((-0.18, 2.2), (0.18, 2.2), (0.16, 2.95), (-0.16, 2.95))]
        g = glass_shards(rng, pts, 3, 0, (0.25, 0.5), normal=(0, -1, 0))
        if g:
            glows.append(g)
    # 정면 오른쪽 모서리 큰 버팀벽 (꼭대기 뾰족탑은 부러졌다)
    bf = Sub(Wf.acc, Mf)
    for (z0, z1, ww, dd) in ((-0.2, 7.0, 2.2, 2.2), (7.0, 13.5, 1.8, 1.8), (13.5, 18.5, 1.45, 1.45)):
        pier_stack(bf, rng, XO + 0.3, -0.2 - (dd - 2.2) * 0.0, ww, dd, z0, z1, k=k * 0.9, hr=hr, gap=gap)
        bm = bm_wedge(ww + 0.15, dd + 0.15, 0.7); bm_chip(bm, rng, 2, (0.04, 0.09))
        bf.add(bm, TR((XO + 0.3, -0.2, z1 - 0.05)))
    bm = bm_box(1.0, 1.0, 1.6)
    bm_break(bm, rng, (0.1, 0, 0.3), (0.6, -0.5, 1), facets=3, spread=0.6, jitter=0.1)
    stone_blk(bm, rng, (2, 4), (0.05, 0.12), 0.02)
    bf.add(bm, TR((XO + 0.3, -0.2, 19.3)))
    hi_parts.append(Wf.acc.obj("cath_front"))
    fcore = core_poly(-XO + 0.3, XO - 0.3, lambda x: min(ftop(x), ZE + (ZA - ZE) * (1 - abs(x) / (XO + 0.6))), -0.3, 0.4, 0.3, 0.25, rng)
    a = Acc(); a.add(bm_poly(ccw(fcore), 0.35, TF - 0.35, 'y'), Mf)
    co = a.obj("front_core")
    kit.cut(co, [zone_prism(arch_outline(pw2, PH, pr2, grow=0.0, z_bottom=-0.5), -0.5, 2.0, Mf),
                 zone_prism(arch_outline(PW, PH, PR, grow=0.0, z_bottom=-0.5), -0.5, 2.0, Mf),
                 zone_prism(circle_poly(0, RC, RR, 32), -0.5, 2.0, Mf)])
    hi_parts.append(co)

    # ── 동쪽 끝 벽 (큰 창, 오른쪽이 무너졌다) ──
    Me = TR((0, YE, 0)) @ Matrix.Rotation(R(180), 4, 'Z')
    We = Wall(rng, Me, k=k, gap=gap, blen=blen, skin=skin, hr=hr, rot=0.6)
    etop = profile([(-XO, 16.5), (-3.0, 18.5), (-1.0, 16.0), (0.8, 9.5), (2.5, 6.0), (4.5, 4.2), (XO, 5.0)])
    EW, EH, ER = 4.4, 10.5, 4.0
    eholes = [arch_outline(EW, EH, ER, grow=WT + gap, z_bottom=3.6)]
    zs = We.courses(-0.2, 19)
    We.face(-XO, XO, zs, 0.0, top=etop, holes=eholes, plinth=0.12, missing=0.02)
    We.face(-XI, XI, zs, XO - XI, top=etop, holes=eholes, outward=1, missing=0.02)
    for tag, bm, c in arch_stones(rng, EW, EH, ER, WT, 9, -0.04, XO - XI + 0.04, gap, chips=(1, 2), k=k):
        if c.z > etop(c.x) - 0.3:
            bm.free(); continue
        We.add_bm(bm, Matrix.Identity(4))
    jambs_top(We.acc, rng, EW, 4.0, EH, WT, -0.04, XO - XI + 0.04, gap, hr, We.M, k, top=etop)
    hi_parts.append(We.acc.obj("cath_east"))
    a = Acc(); a.add(bm_poly(ccw(core_poly(-XO + 0.3, XO - 0.3, etop, -0.3, 0.4, 0.3, 0.25, rng)), 0.3, XO - XI - 0.3, 'y'), Me)
    co = a.obj("east_core")
    kit.cut(co, [zone_prism(arch_outline(EW, EH, ER, grow=0.0, z_bottom=4.0), -0.5, 2.0, Me)])
    hi_parts.append(co)
    hi_parts += top_rubble(rng, etop, -XO + 0.5, XO - 0.5, 0.0, XO - XI, 14, Me, k=k * 0.8, drop=0.2)

    # ── 종탑 (앞 왼쪽, 위가 반쯤 무너졌다) ──
    TX0, TX1, TY0, TY1, TT = -11.8, -XO, YF - 0.4, YF - 0.4 + 5.7, 1.25
    tcx, tcy = (TX0 + TX1) / 2, (TY0 + TY1) / 2
    tw = TX1 - TX0
    ttops = [profile([(-tw / 2, 30.5), (-1.2, 29.6), (0.2, 27.0), (1.4, 25.2), (tw / 2, 24.0)]),       # 앞
             profile([(-tw / 2, 24.0), (-0.5, 23.2), (1.0, 25.5), (tw / 2, 26.8)]),                     # 오른쪽 (신랑 쪽)
             profile([(-tw / 2, 26.8), (0.0, 25.0), (tw / 2, 27.6)]),                                  # 뒤
             profile([(-tw / 2, 27.6), (0.5, 29.2), (tw / 2, 30.5)])]                                  # 왼쪽 (바깥)
    # 각 면: 바깥면 위치와 회전 (면 좌표 x 는 바깥에서 볼 때 왼→오)
    tfaces = [TR((tcx, TY0, 0)), TR((TX1, tcy, 0)) @ Matrix.Rotation(R(90), 4, 'Z'),
              TR((tcx, TY1, 0)) @ Matrix.Rotation(R(180), 4, 'Z'), TR((TX0, tcy, 0)) @ Matrix.Rotation(R(-90), 4, 'Z')]
    BW, BS, BH, BR = 1.35, 20.6, 23.6, 1.55          # 종 칸 창
    for fi, (Mt, ttop) in enumerate(zip(tfaces, ttops)):
        Wt = Wall(rng, Mt, k=k, gap=gap, blen=blen, skin=skin, hr=hr, rot=0.6)
        holes = [[(x + bx, z) for x, z in arch_outline(BW, BH, BR, grow=0.45 + gap, z_bottom=BS - 0.3)] for bx in (-1.2, 1.2)]
        if fi == 0:
            holes.append(arch_outline(1.7, 3.2, 1.6, grow=0.5 + gap, z_bottom=-0.3))         # 아래 작은 문
            holes.append([(x, z) for x, z in arch_outline(0.8, 11.5, 0.9, grow=0.4 + gap, z_bottom=9.2)])   # 가는 창
        zs = Wt.courses(-0.2, 31.5)
        Wt.face(-tw / 2, tw / 2, zs, 0.0, top=ttop, holes=holes, plinth=0.12, missing=0.015)
        Wt.face(-tw / 2 + TT, tw / 2 - TT, zs, TT, top=ttop, holes=holes, outward=1, missing=0.02)
        for bx in (-1.2, 1.2):
            if ttop(bx) < BH + 0.5:
                continue
            Mw = TR((bx, 0, 0))
            for tag, bm, c in arch_stones(rng, BW, BH, BR, 0.45, 4, -0.04, TT + 0.04, gap, chips=(1, 2), k=k * 0.8):
                if c.z > ttop(bx + c.x) - 0.25:
                    bm.free(); continue
                Wt.add_bm(bm, Mw)
            jambs_top(Wt.acc, rng, BW, BS, BH, 0.45, -0.04, TT + 0.04, gap, hr, Wt.M @ Mw, k * 0.8, top=ttop, cx=bx)
            bm = bm_box(BW + 1.1, TT + 0.3, 0.32); stone_blk(bm, rng, (2, 3), (0.04, 0.08), 0.02)
            Wt.add_bm(bm, TR((bx, TT / 2, BS - 0.2)))
        if fi == 0:
            for tag, bm, c in arch_stones(rng, 1.7, 3.2, 1.6, 0.5, 4, -0.04, TT + 0.04, gap, chips=(1, 2), k=k * 0.8):
                Wt.add_bm(bm, Matrix.Identity(4))
            jamb_stones(Wt.acc, rng, 1.7, 0.0, 3.2, 0.5, -0.04, TT + 0.04, gap, hr=hr, M=Wt.M, k=k * 0.8)
            for tag, bm, c in arch_stones(rng, 0.8, 11.5, 0.9, 0.4, 3, -0.04, TT + 0.04, gap, chips=(1, 2), k=k * 0.7):
                Wt.add_bm(bm, Matrix.Identity(4))
            jamb_stones(Wt.acc, rng, 0.8, 9.2, 11.5, 0.4, -0.04, TT + 0.04, gap, hr=hr, M=Wt.M, k=k * 0.7)
        # 돌림띠 (층 경계)
        for zb in (10.2, 20.2):
            if ttop(0) < zb + 0.5:
                continue
            x = -tw / 2 - 0.25
            while x < tw / 2 + 0.2:
                ln = min(rng.uniform(1.0, 1.6), tw / 2 + 0.25 - x)
                bm = bm_box(ln - gap, 0.75, 0.42); stone_blk(bm, rng, (1, 3), (0.04, 0.08), 0.02)
                Wt.add_bm(bm, TR((x + ln / 2, 0.15, zb)))
                x += ln
        hi_parts.append(Wt.acc.obj("tower_wall"))
        a = Acc()
        cp = core_poly(-tw / 2 + 0.3, tw / 2 - 0.3, ttop, -0.3, 0.4, 0.3, 0.25, rng)
        a.add(bm_poly(ccw(cp), 0.35, TT - 0.35, 'y'), Mt)
        co = a.obj("tower_core")
        cz = [zone_prism(arch_outline(BW, BH, BR, z_bottom=BS), -0.5, 2.0, Mt @ TR((bx, 0, 0))) for bx in (-1.2, 1.2)]
        if fi == 0:
            cz += [zone_prism(arch_outline(1.7, 3.2, 1.6, z_bottom=-0.5), -0.5, 2.0, Mt), zone_prism(arch_outline(0.8, 11.5, 0.9, z_bottom=9.2), -0.5, 2.0, Mt)]
        kit.cut(co, cz)
        hi_parts.append(co)
        hi_parts += top_rubble(rng, ttop, -tw / 2 + 0.5, tw / 2 - 0.5, 0.0, TT, 10, Mt, k=k * 0.8, drop=0.2)
    # 탑 모서리 버팀벽 (앞 두 모서리, 바깥 뒤 모서리)
    tb = Acc()
    for (cx_, cy_, out) in ((TX0, TY0, (-1, -1)), (TX1, TY0, (1, -1)), (TX0, TY1, (-1, 1))):
        for (z0, z1, ww) in ((-0.2, 8.0, 1.5), (8.0, 15.5, 1.25), (15.5, 21.0, 1.0)):
            for d in ((out[0], 0), (0, out[1])):
                if out[0] > 0 and d[0] > 0:
                    continue                       # 신랑 벽 쪽으로는 내지 않는다
                px = cx_ + d[0] * 0.6 - (0 if d[0] else out[0] * (ww / 2 - 0.35))
                py = cy_ + d[1] * 0.6 - (0 if d[1] else out[1] * (ww / 2 - 0.35))
                w1, d1 = (1.2, ww) if d[0] else (ww, 1.2)
                pier_stack(tb, rng, px, py, w1, d1, z0, z1, k=k * 0.85, hr=hr, gap=gap)
                bm = bm_wedge(ww + 0.1, 1.3, 0.55); bm_chip(bm, rng, 2, (0.04, 0.08))
                ang = math.atan2(d[1], d[0]) + math.pi / 2
                tb.add(bm, TR((px, py, z1 - 0.04), (0, 0, ang)))
    hi_parts.append(tb.obj("tower_buttress"))

    # ── 플라잉 버트레스 (오른쪽 셋) + 독립 기둥 ──
    fb = Acc()
    for j, by in enumerate(bays[1:5]):
        PX = XO + 4.1
        if j == 3:
            # 마지막 것은 날개 다리가 무너지고 기둥만 남았다
            pier_stack(fb, rng, PX, by, 1.6, 1.9, -0.2, 8.5, k=k * 0.9, hr=hr, gap=gap)
            top_b = bm_box(1.6, 1.9, 0.8)
            bm_break(top_b, rng, (0.1, 0, 0.1), (0.5, 0.4, 1), facets=3, spread=0.6)
            stone_blk(top_b, rng, (2, 4), (0.05, 0.1), 0.02)
            fb.add(top_b, TR((PX, by, 8.9)))
            continue
        zt = pier_stack(fb, rng, PX, by, 1.6, 1.9, -0.2, 12.8, k=k * 0.9, hr=hr, gap=gap)
        bm = bm_wedge(1.75, 2.05, 0.6); bm_chip(bm, rng, 2, (0.04, 0.08))
        fb.add(bm, TR((PX, by, zt - 0.05), (0, 0, R(90))))
        t = pinnacle(fb, rng, PX, by, zt + 0.4, 0.95, 1.4, 2.6, broken=(j == 1), k=k * 0.8)
        if t is not None:
            bm_break(t, rng, (0, 0, 1.6), (0.3, 0.4, 1), facets=2, spread=0.4)
            fb.add(t, TR((PX + 2.2, by - 1.0, 0.55), (R(84), R(10), R(-30))))
            bm = bm_box(0.95, 0.95, 0.9)
            bm_break(bm, rng, (0.1, 0, 0.2), (0.6, -0.5, 1), facets=3, spread=0.6)
            stone_blk(bm, rng, (2, 3), (0.04, 0.09), 0.02)
            fb.add(bm, TR((PX, by, zt + 0.4 + 0.45)))
        flyer(Sub(fb, TR((0, by, 0))), rng, XO - 0.2, PX - 0.75, 14.2, 12.3, 11.4, 8.9, -0.5, 0.5, n=7, gap=gap, k=k * 0.8)
    hi_parts.append(fb.obj("cath_flyers"))

    # ── 남은 늑골 아치 (신랑을 가로지른다) ──
    rb = Acc()
    for j, by in enumerate(bays[1:5]):
        if j == 1:
            continue                      # 무너진 벽과 함께 떨어졌다
        skip = ()
        if j == 3:
            skip = tuple(range(4, 9)) + (999,) + tuple(100 + i for i in range(6, 9))      # 반쯤 무너진 늑골
        lt = side_tops[-1]((by - ym) * -1)
        rt = side_tops[1]((by - ym))
        if lt < 12.5:
            skip = skip + tuple(100 + i for i in range(9))
        if rt < 12.5:
            skip = skip + tuple(range(9))
        if len(skip) >= 18:
            continue
        for tag, bm, c in arch_stones(rng, 2 * XI - 0.3, 13.2, 5.8, 0.85, 9, -0.38, 0.38, gap, skip=skip, chips=(1, 2), k=k):
            rb.add(bm, TR((0, by, 0)))
    hi_parts.append(rb.obj("cath_ribs"))

    # ── 바닥 판석, 정문 계단, 무너진 돌 ──
    fl = Acc()
    y = YF + TF + 0.05
    while y < YE - (XO - XI) - 0.3:
        dy = min(rng.uniform(1.0, 1.4), YE - (XO - XI) - y)
        x = -XI + rng.uniform(-0.3, 0.0)
        while x < XI - 0.2:
            dx = min(rng.uniform(1.0, 1.6), XI - x)
            if rng.random() > 0.12:
                bm = bm_box(dx - 0.07, dy - 0.07, 0.25)
                if rng.random() < 0.2:
                    bm_break(bm, rng, (rng.uniform(-0.2, 0.2), 0, 0), (rng.choice((-1, 1)), rng.uniform(-0.8, 0.8), 0.25), facets=2)
                stone_blk(bm, rng, (1, 3), (0.03, 0.07), 0.015, flakes=(0, 1))
                tl = 2.5 if rng.random() < 0.25 else 0.7
                fl.add(bm, TR((x + dx / 2, y + dy / 2, -0.06 + rng.uniform(-0.04, 0.03)), (R(rng.uniform(-tl, tl)), R(rng.uniform(-tl, tl)), R(rng.uniform(-1.5, 1.5)))))
            x += dx
        y += dy
    for i in range(2):
        x = -3.6
        while x < 3.6 - 0.3:
            ln = min(rng.uniform(1.1, 1.8), 3.6 - x)
            bm = bm_box(ln - 0.07, 0.9 + (0.5 if i == 0 else 0), 0.25 + 0.22 * (2 - i))
            stone_blk(bm, rng, (2, 4), (0.04, 0.09), 0.018)
            fl.add(bm, TR((x + ln / 2, YF - 0.45 - 0.85 * i - (0.25 if i == 0 else 0), (0.22 * (2 - i) - 0.25) / 2 + 0.06)))
            x += ln
    ext = []
    for (cx_, cy_, r_, n_, h_) in ((-7.6, -3.0, 3.2, 22, 2.2), (-3.2, -1.5, 2.6, 16, 1.4), (2.5, 13.0, 2.2, 12, 1.2),
                                   (4.8, 15.5, 2.6, 14, 1.6), (-1.0, 8.0, 1.6, 8, 0.8), (8.0, 15.0, 2.0, 10, 1.1),
                                   (0.5, -9.0, 1.4, 7, 0.7), (-8.8, 4.0, 1.8, 9, 0.9)):
        rubble_pile(fl, rng, (cx_, cy_, 0), r_, n_, (0.45, 1.0), h_, extra=ext, k=k)
    for (x, y, sz, rz) in ((-2.0, 3.0, (1.2, 0.8, 0.75), 0.4), (1.5, -2.5, (1.0, 0.75, 0.7), 1.2), (3.6, 9.0, (1.3, 0.85, 0.7), 2.0),
                           (-7.4, -8.5, (1.1, 0.8, 0.7), 0.7), (-9.6, 1.5, (1.0, 0.8, 0.65), 2.4), (8.5, 6.0, (1.2, 0.85, 0.7), 0.2),
                           (-2.8, -11.5, (0.9, 0.7, 0.6), 1.7), (6.9, -18.0, (1.0, 0.7, 0.6), 0.9)):
        fallen_block(fl, rng, (x, y, 0), sz, rot_z=rz, k=k)
    # 무너진 늑골 토막 (바닥에)
    for (x, y, rz) in ((0.8, 10.6, 0.3), (-1.4, 11.4, 1.1), (2.2, 12.0, 2.0)):
        bm = bm_box(1.3, 0.8, 0.85)
        bm_break(bm, rng, (0.4, 0, 0), (1, 0.3, 0.2), facets=3, spread=0.5)
        stone_blk(bm, rng, (2, 4), (0.05, 0.1), 0.02)
        fl.add(bm, TR((x, y, 0.3), (R(rng.uniform(-20, 20)), R(rng.uniform(-15, 15)), rz)))
    hi_parts.append(fl.obj("cath_floor"))
    hi_parts += ext

    # 조각 (부분이 많아 한 번에 리메시)
    tot_area = sum(sum(p.area for p in o.data.polygons) for o in hi_parts)
    print("CATH parts", len(hi_parts), "area %.0f m2" % tot_area)
    body = join(hi_parts)
    pre = copy(body)
    # v3 (k7b): wall_ruin_a 레시피 (블록부): carve+STONE3, paint_block3, finish3 cage 굽기. 저폴리는 이전처럼 조각 전 조립품을 거칠게 리메시
    carve(body, 0.055 * VOX, *STONE3(2.6, wear=1.2, cracks=0.65), seed=221)
    m = paint_block3("cathedral_src", h=26.0, k=2.2, ao=1.0, dirt_h=1.8, moss_low_h=2.6, grime_h=0.3, edge_w=0.04, moss_patch=2.4)
    tint_near(m, (0, YF + 0.5, RC), 3.2, (0.32, 0.14, 0.5), 0.3)          # 장미창 둘레 영혼 빛에 물든 돌
    set_mat(body, m)
    low = low_coarse(pre, 0.16, 24000, floor=20)
    delete(pre)
    vines = ivy_on(low, [((-XO - 0.3, -6.0, 0.05), 4, 9.0, 7), ((-XO - 0.3, 6.0, 0.05), 6, 6.0, 5),
                         ((TX0 - 0.3, TY0 + 2.0, 0.05), 8, 8.0, 6), ((XO + 0.3, 12.5, 0.05), 10, 5.0, 5),
                         ((-XI + 0.3, 10.0, 0.1), 12, 4.0, 4)], 41, leaf=(0.1, 0.16), leaf_p=0.24,
                   hangs=[((-2.0, YF - 0.3, 18.0), 3.5, (0, -1, 0)), ((3.0, YF - 0.3, 16.5), 2.4, (0, -1, 0)),
                          ((XO + 0.2, -5.0, 14.0), 3.0, (1, 0, 0)), ((XO + 0.2, 6.0, 14.0), 2.2, (1, 0, 0))], step=0.06)
    return finish3("cathedral_ruin", [body], [low], extras=glows + vines, far_extras=glows, size=2048, cage=0.02, cage_reach=0.35,
                   lod1=0.35, lod2=0.12, uv_margin=0.001)


# ═════════════════════════ 석상 부품 ═════════════════════════
FIG_LAYERS = [{'t': 'lumps', 'scale': 6, 'amp': 0.0012}, {'t': 'fissure', 'scale': 3.5, 'width': 0.012, 'depth': 0.0028, 'cover': 0.5},
              {'t': 'terrace', 'scale': 9, 'steps': 3, 'amp': 0.0012, 'cover': 0.5}, {'t': 'fissure', 'scale': 11, 'width': 0.01, 'depth': 0.0012, 'cover': 0.5},
              {'t': 'grain', 'scale': 140, 'amp': 0.00025}]       # 석상 몸: 점 구멍 없이 (작은 둥근 면에서 구슬 무늬가 된다)
def robe_mesh(name, rings, folds=13, seg=96, rng=None, amp=lambda z: 0.02, sharp=0.7, wob=0.25, hem=None, cap_top=True):
    """세로 주름 진 옷자락. rings: [(z, rx, ry, cy)] 아래부터. 주름 = |sin| 모양 (둥근 마루, 날카로운 골).
    amp(z): 높이별 주름 깊이, hem(θ): 맨 아래 단의 높이 변화 (찢어진 옷자락 등)"""
    rng = rng or random.Random(0)
    ph = [rng.uniform(0, 6.28) for _ in range(4)]
    fk = [rng.uniform(0.7, 1.3) for _ in range(folds)]
    verts, faces = [], []
    n = len(rings)
    for i, (z, rx, ry, cy) in enumerate(rings):
        for j in range(seg):
            th = 2 * math.pi * j / seg
            w = wob * math.sin(z * 4.0 + ph[0]) + 0.15 * math.sin(z * 9.0 + ph[1] + th)
            q = folds * th / 2 + w
            kk = fk[int((folds * th / (2 * math.pi)) % folds)]
            f = (abs(math.sin(q)) ** sharp - 0.55) * amp(z) * kk
            r = 1.0 + f / max(0.05, (rx + ry) / 2)
            zz = z
            if i == 0 and hem is not None:
                zz = z + hem(th)
            verts.append((rx * math.cos(th) * r, cy + ry * math.sin(th) * r, zz))
    for i in range(n - 1):
        for j in range(seg):
            a = i * seg + j
            b = i * seg + (j + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    c0 = len(verts); verts.append((0, rings[0][3], rings[0][0] + (0.0 if hem is None else min(hem(2 * math.pi * j / seg) for j in range(seg)))))
    for j in range(seg):
        faces.append((c0, (j + 1) % seg, j))
    if cap_top:
        c1 = len(verts); verts.append((0, rings[-1][3], rings[-1][0]))
        L = (n - 1) * seg
        for j in range(seg):
            faces.append((c1, L + j, L + (j + 1) % seg))
    return mesh_from(name, verts, faces)

def feather(acc, rng, base, d, L, w, th, normal, tip=0.95, M=None):
    """깃털 한 장: base 에서 d 방향으로 L, 폭 w, 두께 th. normal: 깃털 면의 바깥 방향"""
    d = Vector(d).normalized()
    nrm = Vector(normal)
    nrm = (nrm - d * nrm.dot(d)).normalized()
    side = nrm.cross(d).normalized()
    bm = bm_box(L, w, th)                                   # x = 길이, y = 폭, z = 두께
    bm_cut(bm, (L / 2 - w * tip, w / 2, 0), (0.55, 1, 0))
    bm_cut(bm, (L / 2 - w * tip, -w / 2, 0), (0.55, -1, 0))
    bm_cut(bm, (0, 0, th / 2 - th * 0.35), (0, 0.55, 1))      # 깃대 한쪽으로 비스듬히 (겹이 보이게)
    if rng.random() < 0.3:
        bm_chip(bm, rng, 1, (w * 0.15, w * 0.4))
    Mx = Matrix((d, side, nrm)).transposed().to_4x4()
    Mx.translation = Vector(base) + d * (L / 2)
    acc.add(bm, (M @ Mx) if M is not None else Mx)

def folded_wing(acc, rng, sx, root, phi=38.0, top=2.2, s=1.0, broken=(), blob_items=None):
    """접힌 날개 (몸 뒤). 위가 둥근 어깨(손목 관절)로 머리 위까지 솟고, 긴 깃이 모여 발치 쪽 끝으로 좁아지는 물방울 모양.
    root: 어깨뼈 자리. broken: [(깃 번호, 남은 길이 비율)]. blob_items: 날개 몸통 타원구를 넣을 목록 (리메시로 녹인다)"""
    brk = dict(broken)
    root = Vector(root)
    a = Vector((sx * math.cos(R(phi)), math.sin(R(phi)), 0))       # 날개 면의 바깥 (뒤쪽으로 비스듬히)
    up = Vector((0, 0, 1))
    nrm = a.cross(up)
    if nrm.y < 0:
        nrm = -nrm                                                    # 날개 바깥면 (대략 뒤)
    def P(u, v):          # u: 날개 면 위 바깥 방향 거리, v: 절대 높이
        return root + a * (u * s) + up * ((v - root.z) * s)
    vt = top
    # 윗선 (안쪽 뿌리 → 둥근 손목 → 바깥 앞전)
    arc = [(0.0, root.z + 0.25), (0.03, vt - 0.2), (0.1, vt - 0.03), (0.19, vt), (0.28, vt - 0.08), (0.36, vt - 0.3), (0.4, vt - 0.6)]
    tip = (0.2, 0.28)
    # 날개 몸통 (두께): 윗선을 따라 굵게, 아래로 갈수록 가늘게
    if blob_items is not None:
        blob_items += tube_items([P(*q) - nrm * 0.01 for q in arc[1:]], [0.062 * s] * (len(arc) - 1), 0.45)     # 둥글고 두툼한 앞전
        for t in lin(0.0, 1.0, 9):
            u = 0.2 + (tip[0] - 0.2) * t
            v = (vt - 0.45) + (tip[1] + 0.15 - (vt - 0.45)) * t
            w_ = (0.2 * (1 - t) + 0.04) * s
            c = P(u, v)
            M = Matrix((a, up, a.cross(up))).transposed()        # 오른손 좌표계 (타원구는 두께 방향 대칭)
            blob_items.append((c - nrm * (0.02 * (1 - t)), (w_, (0.3 - 0.15 * t) * s, (0.095 - 0.06 * t) * s), M.to_euler()))     # 위가 두툼하고 아래로 얇아진다
    # 첫째 깃: 윗선 여러 점에서 끝점(아래)으로 모이며 부채꼴로 겹친다
    nf = 8
    for i in range(nf):
        t = i / (nf - 1)
        j = 1 + t * (len(arc) - 2.2)
        ja = int(j); jb = min(ja + 1, len(arc) - 1); f = j - ja
        bu = arc[ja][0] + (arc[jb][0] - arc[ja][0]) * f
        bv = arc[ja][1] + (arc[jb][1] - arc[ja][1]) * f - 0.08
        tu = tip[0] + (t - 0.5) * 0.22
        tv = tip[1] + abs(t - 0.45) * 0.55
        b = P(bu, bv)
        e = P(tu, tv)
        d = e - b
        L = d.length * brk.get(i, 1.0)
        off = nrm * ((0.045 + 0.008 * (i % 2)) * s)                     # 몸통에 반쯤 묻혀 겹친 비늘처럼 (지느러미처럼 튀지 않게)
        feather(acc, rng, b + off, d, L, (0.135 - 0.02 * abs(t - 0.5)) * s, 0.03 * s, nrm, tip=(0.95 if i not in brk else 0.2))
    # 덮깃: 윗부분에 짧고 둥근 깃이 비늘처럼 두세 줄
    for row in range(3):
        n_ = 7 - row
        for i in range(n_):
            t = (i + 0.5 * (row % 2)) / (n_ - 0.5)
            j = 0.6 + t * (len(arc) - 1.8)
            ja = int(j); jb = min(ja + 1, len(arc) - 1); f = j - ja
            bu = arc[ja][0] + (arc[jb][0] - arc[ja][0]) * f
            bv = arc[ja][1] + (arc[jb][1] - arc[ja][1]) * f - 0.04 - 0.16 * row
            b = P(bu * (1 - 0.12 * row) + 0.02 * row, bv)
            d = (P(bu * 0.9 + 0.02, bv - 0.5) - b)
            L = (0.3 - 0.05 * row) * s
            feather(acc, rng, b + nrm * ((0.06 + 0.008 * row) * s), d, L, 0.11 * s, 0.03 * s, nrm, tip=0.55)

def pedestal(acc, rng, w=0.8, h=0.9, k=1.0, panel=True, broken_corner=True):
    """받침대: 굽돌 + 몸돌(앞면 판) + 갓돌. 돌아오는 것: 윗면 높이, 판 커터 목록"""
    z = 0.0
    parts = [(w + 0.26, 0.2), (w + 0.12, 0.08), (w, h - 0.48), (w + 0.1, 0.07), (w + 0.18, 0.13)]
    cutters = []
    for i, (ww, hh) in enumerate(parts):
        bm = bm_box(ww, ww, hh)
        if i == 0:
            stone_blk(bm, rng, (2, 4), (0.03 * k, 0.07 * k), 0.012 * k, zmin=0.02)
        elif i == 4 and broken_corner:
            bm_break(bm, rng, (ww * 0.38, -ww * 0.38, 0), (1, -1, 0.4), facets=3, spread=0.4, jitter=0.02)
            stone_blk(bm, rng, (1, 3), (0.02 * k, 0.05 * k), 0.01 * k)
        else:
            stone_blk(bm, rng, (1, 3), (0.02 * k, 0.05 * k), 0.01 * k)
        acc.add(bm, TR((0, 0, z + hh / 2 - (0.06 if i == 0 else 0)), (0, 0, R(rng.uniform(-1.2, 1.2)))))
        if i == 2 and panel:
            for (pw, ph, dep) in ((w * 0.72, (h - 0.48) * 0.72, 0.03),):
                a = Acc(); a.add(bm_box(pw, 0.1, ph), TR((0, -w / 2 - 0.05 + dep, z + hh / 2)))
                cutters.append(a.obj("panel"))
        z += hh - (0.06 if i == 0 else 0)
    return z, cutters


# ═════════════════════════ 우는 천사 석상 ═════════════════════════
def statue_angel():
    rng = random.Random(3303)
    ped = Acc()
    zt, pcut = pedestal(ped, rng, 0.82, 0.92)
    po = ped.obj("angel_ped")
    remesh(po, 0.006)                 # 깎기 전에 한 덩어리로 닫는다 (모 깎은 블록의 자기 교차 때문에 불리언이 몸돌을 날려 먹는다)
    # 판 안의 글자 획 (닳아서 읽을 수 없는 비문)
    strokes = []
    for row in range(3):
        x = -0.24
        while x < 0.22:
            ln = rng.uniform(0.02, 0.06)
            a = Acc(); a.add(bm_box(ln, 0.03, 0.018), TR((x + ln / 2, -0.376, 0.52 - row * 0.07)))
            strokes.append(a.obj("st"))
            x += ln + rng.uniform(0.012, 0.03)
    cut(po, pcut + strokes, voxel=0.006)
    Z = zt - 0.02                                         # 몸 바닥 (받침 윗면)
    M = TR((0, 0, Z))
    parts = []
    # 옷 (아래로 넓게 퍼져 받침에 고인 자락)
    rings = [(0.0, 0.36, 0.33, 0.03), (0.06, 0.34, 0.3, 0.025), (0.3, 0.3, 0.25, 0.015), (0.65, 0.25, 0.2, 0.0),
             (1.0, 0.205, 0.155, 0.0), (1.22, 0.22, 0.16, -0.005), (1.42, 0.235, 0.155, 0.0), (1.55, 0.2, 0.13, 0.0), (1.62, 0.08, 0.07, 0.0)]
    rb = robe_mesh("robe", rings, folds=15, seg=120, rng=rng, amp=lambda z: 0.035 * max(0.25, 1 - z / 1.3) + 0.008)
    rb.data.transform(M); parts.append(rb)
    # 두건에서 이어진 어깨 망토 (주름)
    cape = [(1.12, 0.3, 0.245, 0.015), (1.3, 0.3, 0.23, 0.01), (1.45, 0.28, 0.2, 0.0), (1.56, 0.22, 0.17, -0.005), (1.66, 0.13, 0.13, -0.02)]
    cp = robe_mesh("cape", cape, folds=11, seg=96, rng=rng, amp=lambda z: 0.03 * max(0.2, (1.6 - z) / 0.5), hem=lambda th: 0.05 * math.sin(3 * th) - 0.05 * max(0, -math.sin(th)))
    cp.data.transform(M); parts.append(cp)
    # 머리 (숙였다) + 두건
    head_c = Vector((0, -0.1, 1.73))
    hood = blobs([((0, -0.045, 1.78), (0.155, 0.175, 0.17)), ((0, 0.04, 1.85), (0.11, 0.12, 0.12)), ((0, 0.09, 1.9), (0.05, 0.06, 0.06))], 3, "hood")
    hood.data.transform(M)
    remesh(hood, 0.005)
    op = sphere(1.0, (0, -0.225, 1.71 + Z), (0.105, 0.14, 0.125), 3, rot=(R(28), 0, 0))
    cut(hood, [op], voxel=0.005)
    parts.append(hood)
    hd = blobs([(head_c, (0.095, 0.105, 0.115)), ((0, -0.16, 1.685), (0.05, 0.05, 0.06))], 3, "head")
    hd.data.transform(M); parts.append(hd)
    # 팔: 어깨 → 팔꿈치 (가슴 앞) → 손목 (얼굴 앞), 넓은 소매가 아래로 늘어진다
    arm_items = []
    for sx in (-1, 1):
        sh = Vector((sx * 0.22, -0.02, 1.48)); el = Vector((sx * 0.21, -0.3, 1.32)); wr = Vector((sx * 0.075, -0.255, 1.6))
        arm_items += tube_items([sh, el], [0.065, 0.062], 0.3)
        arm_items += tube_items([el, wr - (wr - el).normalized() * 0.03], [0.062, 0.072], 0.3)    # 손목 쪽으로 넓어지는 소매
        for t in lin(0.1, 0.95, 7):                       # 소매 아래로 처진 자락 (이어진 주머니 모양)
            p = el.lerp(wr, t)
            arm_items.append((p + Vector((sx * 0.006, 0.012, -0.05 - 0.06 * t)), (0.055 + 0.012 * t, 0.055, 0.06 + 0.04 * t)))
    arms = blobs(arm_items, 2, "arms"); arms.data.transform(M); parts.append(arms)
    # 손: 얼굴을 가린 두 손 (둥근 손바닥 + 위로 뻗어 이마에 닿은 손가락 넷 + 엄지)
    hit = []
    for sx in (-1, 1):
        Mh = TR((sx * 0.05, -0.236, 1.712), (R(22), sx * R(-8), sx * R(-6)))
        hit.append((Mh @ Vector((0, 0, -0.008)), (0.04, 0.017, 0.046)))                         # 손바닥
        for fi in range(4):
            fl = (0.075, 0.088, 0.083, 0.066)[fi]
            x0 = -sx * 0.03 + sx * fi * 0.02
            pts = [Mh @ Vector((x0, -0.004, 0.03)), Mh @ Vector((x0 + sx * 0.002 * (fi - 1.5), -0.002, 0.03 + fl * 0.55)),
                   Mh @ Vector((x0 + sx * 0.004 * (fi - 1.5), 0.008, 0.03 + fl))]                 # 끝이 이마 쪽으로 조금 굽는다
            hit += tube_items(pts, [0.0105, 0.0095, 0.008], 0.45)
        hit += tube_items([Mh @ Vector((sx * 0.035, 0.0, -0.03)), Mh @ Vector((sx * 0.05, -0.006, 0.0)), Mh @ Vector((sx * 0.052, 0.0, 0.03))],
                          [0.013, 0.011, 0.009], 0.45)                                           # 엄지 (볼 옆)
    hands = blobs(hit, 2, "hands"); hands.data.transform(M); remesh(hands, 0.0025)       # 손은 따로 (작아서 함께 줄이면 뭉개진다)
    # 날개
    wa = Acc()
    wblob = []
    for sx in (-1, 1):
        folded_wing(wa, rng, sx, (sx * 0.1, 0.13, 1.42), phi=32, top=2.24, s=1.0, broken=((7, 0.55),) if sx < 0 else (), blob_items=wblob)
    wings = wa.obj("wings"); wings.data.transform(M); parts.append(wings)
    wb = blobs(wblob, 2, "wing_body"); wb.data.transform(M); parts.append(wb)
    fig = join(parts)
    origin0(fig)
    remesh(fig, 0.0055)
    surface(fig, FIG_LAYERS, seed=33)
    surface(hands, [{'t': 'lumps', 'scale': 30, 'amp': 0.0006}, {'t': 'grain', 'scale': 200, 'amp': 0.0002}], seed=35)
    sculpt(po, 0.0065, STONE_LAYERS(0.9, wear=1.4, cracks=0.6), seed=34)
    body = join([fig, po])
    m = paint("angel_src", 'stone_pale', moss=0.75, ao=0.12, dirt=0.7, streaks=0.7, edge=0.7, cavity=1.0)
    tears(m, [(-0.05, Z + 1.66), (0.06, Z + 1.66), (-0.12, Z + 1.24), (0.13, Z + 1.24)], 1.2, 0.03, 0.8)
    moss_low(m, 0.0, 0.5, 0.85, scale=4.0)
    set_mat(body, m)
    set_mat(hands, m)
    low = low_of(body, 7300)
    hl = low_of(hands, 900, floor=200)
    vines = ivy_on(low, [((-0.55, -0.3, 0.02), 5, 1.6, 4), ((0.5, 0.5, 0.02), 7, 1.0, 3)], 51, leaf=(0.035, 0.06), leaf_p=0.4)
    return finish_lm("statue_angel", [body, hands], [low, hl], extras=vines, far_extras=[], size=2048, extr=0.03, lod1=0.35, lod2=0.12)


# ═════════════════════════ 사신 석상 ═════════════════════════
def statue_reaper():
    rng = random.Random(4404)
    ped = Acc()
    zt, pcut = pedestal(ped, rng, 0.86, 0.86, panel=True, broken_corner=False)
    po = ped.obj("reaper_ped")
    remesh(po, 0.006)                 # 깎기 전에 닫는다 (안 그러면 불리언 뒤 몸돌이 사라진다)
    # 받침 앞 판에 해골 하나 (작은 부조)
    sk, eyes0 = skull_relief((0, -0.43 - 0.02, 0.5), 0.22, wings=False, rng=rng)
    delete(eyes0)
    cut(po, pcut, voxel=0.006)
    Z = zt - 0.02
    M = TR((0, 0, Z))
    parts = []
    # 찢어진 옷자락 (아래 끝이 들쭉날쭉)
    jag = [rng.uniform(0.0, 0.12) for _ in range(19)]
    def hem(th):
        u = th / (2 * math.pi) * 19
        i = int(u) % 19
        f = u - int(u)
        return jag[i] * (1 - abs(f - 0.5) * 2) ** 0.6
    rings = [(0.02, 0.4, 0.36, 0.04), (0.12, 0.36, 0.32, 0.03), (0.45, 0.3, 0.25, 0.02), (0.85, 0.25, 0.2, 0.0),
             (1.2, 0.235, 0.18, 0.0), (1.45, 0.26, 0.19, 0.0), (1.68, 0.29, 0.2, 0.02), (1.82, 0.24, 0.17, 0.03), (1.9, 0.1, 0.08, 0.02)]
    rb = robe_mesh("robe", rings, folds=13, seg=120, rng=rng, amp=lambda z: 0.04 * max(0.3, 1 - z / 1.6) + 0.008, hem=hem)
    rb.data.transform(M); parts.append(rb)
    cape = [(1.25, 0.36, 0.28, 0.03), (1.5, 0.36, 0.26, 0.025), (1.7, 0.33, 0.23, 0.02), (1.84, 0.25, 0.19, 0.02), (1.94, 0.15, 0.15, 0.0)]
    jag2 = [rng.uniform(0.0, 0.1) for _ in range(13)]
    def hem2(th):
        u = th / (2 * math.pi) * 13
        f = u - int(u)
        return -jag2[int(u) % 13] * (1 - abs(f - 0.5) * 2) ** 0.6
    cp = robe_mesh("cape", cape, folds=9, seg=96, rng=rng, amp=lambda z: 0.035, hem=hem2)
    cp.data.transform(M); parts.append(cp)
    # 깊은 두건 (앞으로 뾰족, 안이 어둡다)
    hood = blobs([((0, -0.03, 2.08), (0.19, 0.21, 0.2)), ((0, 0.07, 2.17), (0.13, 0.14, 0.14)), ((0, 0.15, 2.24), (0.06, 0.07, 0.08)),
                  ((0, -0.16, 2.12), (0.13, 0.08, 0.15))], 3, "hood")
    hood.data.transform(M)
    remesh(hood, 0.005)
    op = sphere(1.0, (0, -0.24, 2.03 + Z), (0.12, 0.2, 0.15), 3, rot=(R(12), 0, 0))
    cut(hood, [op], voxel=0.005)
    parts.append(hood)
    # 두건 속 어둠 안쪽 면 (해골 얼굴은 보이지 않고 눈만)
    inner = blobs([((0, -0.02, 2.03), (0.1, 0.09, 0.12))], 2, "face"); inner.data.transform(M); parts.append(inner)
    # 팔: 오른손은 낫자루를 가슴 높이에서 쥐고, 왼손은 아래로 늘어뜨려 뼈 손가락을 편다
    snath_x, snath_y = 0.38, -0.12
    it = []
    sh_r, el_r, wr_r = Vector((0.27, 0.0, 1.8)), Vector((0.36, -0.05, 1.5)), Vector((snath_x - 0.03, snath_y, 1.6))
    it += tube_items([sh_r, el_r], [0.075, 0.065], 0.5) + tube_items([el_r, wr_r], [0.065, 0.05], 0.5)
    it.append((el_r.lerp(wr_r, 0.5) + Vector((0.02, 0.02, -0.08)), (0.08, 0.075, 0.12)))
    sh_l, el_l, wr_l = Vector((-0.27, 0.0, 1.8)), Vector((-0.33, -0.02, 1.42)), Vector((-0.3, -0.1, 1.1))
    it += tube_items([sh_l, el_l], [0.075, 0.065], 0.5) + tube_items([el_l, wr_l], [0.065, 0.05], 0.5)
    it.append((el_l.lerp(wr_l, 0.6) + Vector((-0.02, 0.02, -0.04)), (0.085, 0.08, 0.14)))
    arms = blobs(it, 2, "arms"); arms.data.transform(M); parts.append(arms)
    # 뼈 손
    hb = Acc()
    for (wr, dirs, curl) in ((wr_r, Vector((0.25, 0, -1)), 70), (wr_l, Vector((0.1, -0.25, -1)), 18)):
        hb.add(bm_box(0.06, 0.035, 0.07), TR(wr + Vector((0, 0, -0.04))))
        for fi in range(4):
            x0 = -0.022 + fi * 0.015
            base = wr + Vector((x0, -0.01, -0.08))
            pts = [base]
            d = dirs.normalized()
            for s_ in range(3):
                ang = R(curl * (s_ + 1) / 3)
                dd = Vector((d.x, d.y * math.cos(ang) - math.sin(ang) * 0.8, d.z * math.cos(ang)))
                pts.append(pts[-1] + dd.normalized() * (0.035 - 0.006 * s_))
            v, f = bar_path(pts, 0.011, 0.011)
            hb.add_raw(v, f)
    hands = hb.obj("bonehands"); hands.data.transform(M); remesh(hands, 0.003)            # 뼈 손은 따로 줄인다
    # 낫: 자루 (조금 휜) + 날 (머리 위로 앞·왼쪽을 향해 굽은 초승달)
    sc_ = Acc()
    snath = [Vector((snath_x + 0.02 * math.sin(t * 3), snath_y + 0.03 * t, -0.0 + 2.75 * t)) for t in lin(0, 1, 9)]
    v, f = bar_path(snath, 0.045, 0.045)
    sc_.add_raw(v, f)
    grip = snath[0].lerp(snath[-1], 0.62)
    v, f = bar_path([grip + Vector((0, 0, 0)), grip + Vector((-0.16, -0.02, 0.04)), grip + Vector((-0.2, -0.03, 0.06))], 0.035, 0.035)
    sc_.add_raw(v, f)
    top = snath[-1]
    blade = []
    for i in range(14):
        t = i / 13 * 0.94                         # 끝이 조금 부러져 뭉툭하다
        ang = R(200 - 95 * t)                     # 자루 끝에서 앞·왼쪽으로 휘어 나간다
        rad = 0.55
        c = top + Vector((-0.05, -0.55, -0.05))
        p_out = c + Vector((math.cos(ang) * 0.0, 0, 0))
        x = top.x - 1.05 * t
        y = top.y - 0.55 * math.sin(math.pi * t * 0.55) - 0.05
        z = top.z - 0.05 - 0.28 * t * t
        wdt = 0.13 * (1 - t) ** 0.8 + 0.008
        blade.append((Vector((x, y, z)), wdt))
    bv, bf = [], []
    for i, (p, wdt) in enumerate(blade):
        for (dz, dy) in ((0.0, -0.012), (-wdt, -0.004), (-wdt, 0.004), (0.0, 0.012)):
            bv.append(p + Vector((0, dy, dz)))
    for i in range(len(blade) - 1):
        for kq in range(4):
            a = i * 4 + kq; b = i * 4 + (kq + 1) % 4
            bf.append((a, b, b + 4, a + 4))
    bf.append((3, 2, 1, 0)); L4 = (len(blade) - 1) * 4; bf.append((L4, L4 + 1, L4 + 2, L4 + 3))
    sc_.add_raw(bv, bf)
    sc_.add(bm_box(0.09, 0.07, 0.16), TR(top + Vector((-0.02, -0.01, -0.06))))
    scy = sc_.obj("scythe"); scy.data.transform(M); parts.append(scy)
    fig = join(parts)
    origin0(fig)
    remesh(fig, 0.0055)
    surface(fig, FIG_LAYERS, seed=44)
    sculpt(po, 0.0065, STONE_LAYERS(0.9, wear=1.4, cracks=0.6), seed=45)
    remesh(sk, 0.004)
    body = join([fig, po, sk])
    m = paint("reaper_src", 'stone', moss=0.6, moss_color=MOSS, ao=0.14, dirt=0.75, streaks=0.75, edge=0.75, cavity=1.0)
    tint_near(m, (0, -0.06, Z + 2.05), 0.2, (0.01, 0.006, 0.02), 0.95)          # 두건 속 어둠
    tint_near(m, (0, -0.2, Z + 2.03), 0.32, (0.3, 0.12, 0.5), 0.3)              # 눈빛
    moss_low(m, 0.0, 0.5, 0.85, scale=4.0)
    set_mat(body, m)
    set_mat(hands, m)
    eyes = []
    for sx in (-1, 1):
        eyes.append(sphere(0.017, (sx * 0.042, -0.11, Z + 2.03), (1.2, 0.6, 0.8), 2))
    ge = glow(join(eyes), 'Glow_Soul')
    low = low_of(body, 7600)
    hl = low_of(hands, 700, floor=120)
    return finish_lm("statue_reaper", [body, hands], [low, hl], extras=[ge], far_extras=[ge], size=2048, extr=0.03, lod1=0.35, lod2=0.12)


# ═════════════════════════ 나무·밧줄 ═════════════════════════
WOOD_LAYERS = [{'t': 'lumps', 'scale': 4.0, 'amp': 0.002}, {'t': 'fissure', 'scale': 7.0, 'width': 0.02, 'depth': 0.004, 'cover': 0.8},
               {'t': 'fissure', 'scale': 18.0, 'width': 0.015, 'depth': 0.0015, 'cover': 0.9}, {'t': 'pits', 'scale': 40, 'depth': 0.0012, 'cover': 0.5},
               {'t': 'grain', 'scale': 90, 'amp': 0.0004}]

def beam(acc, rng, p0, p1, w, h=None, ref=(0, 0, 1), rot_end=0.0, split=0.0, rotten=True):
    """각진 나무 들보 (p0→p1). 끝은 비스듬히 썩어 부서지고 모서리가 문드러졌다"""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    h = h or w
    x = d.normalized()
    z0 = Vector(ref)
    y = z0.cross(x)
    if y.length < 1e-4:
        y = x.orthogonal()
    y.normalize()
    z = x.cross(y).normalized()
    bm = bm_box(L, w, h)
    # 썩어 부서진 끝 (비스듬한 면 몇 장)
    for end in (-1, 1):
        if rotten and rng.random() < 0.7:
            for _ in range(rng.randint(2, 3)):
                n = Vector((end, rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8))).normalized()
                bm_cut(bm, (end * (L / 2 - rng.uniform(0.02, 0.12)), 0, 0), n)
    bm_chip(bm, rng, rng.randint(2, 5), (w * 0.1, w * 0.35))
    if split > 0:
        bm_cut(bm, (0, 0, h * 0.5 - split), (0, 0.3, 1))
    Mx = Matrix((x, y, z)).transposed().to_4x4()
    Mx.translation = (p0 + p1) / 2
    Mx = Mx @ Matrix.Rotation(rot_end, 4, 'X')
    acc.add(bm, Mx)

def wood_high(low_obj, voxel, seed, name, pal='wood'):
    h = copy(low_obj)
    origin0(h)
    remesh(h, voxel)
    surface(h, WOOD_LAYERS, seed)
    set_mat(h, paint(name, pal, moss=0.35, moss_color=MOSS_DEAD, dirt=0.4, streaks=0.3, streak_dir='grain', ao=0.08, edge=0.5, cracks=0.0, hue_var=0.3))
    return h

def rope_path(pts, r=0.018, seg=6):
    """밧줄: 꺾은선을 따라 가는 관 (저폴리) — verts, faces"""
    pts = [Vector(p) for p in pts]
    verts, faces = [], []
    n = len(pts)
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        u = d.orthogonal().normalized(); v = d.cross(u)
        for j in range(seg):
            a = 2 * math.pi * j / seg
            verts.append(p + (u * math.cos(a) + v * math.sin(a)) * r)
    for i in range(n - 1):
        for j in range(seg):
            a = i * seg + j; b = i * seg + (j + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    faces.append(tuple(range(seg))[::-1]); L = (n - 1) * seg; faces.append(tuple(range(L, L + seg)))
    return verts, faces


# ═════════════════════════ 돌 우물 ═════════════════════════
def well():
    rng = random.Random(5505)
    RO, RI = 0.82, 0.56
    st = Acc()
    zs = [-0.15, 0.17, 0.45, 0.7]
    for k_, (za, zb) in enumerate(zip(zs, zs[1:])):
        n = 9 + k_ % 2
        off = rng.uniform(0, 6.28)
        for i in range(n):
            a0 = off + 2 * math.pi * i / n + 0.03
            a1 = off + 2 * math.pi * (i + 1) / n - 0.03
            if k_ == 2 and i == 3:
                continue                              # 빠진 돌
            bm = bm_sector(RI + rng.uniform(-0.02, 0.0), RO + rng.uniform(-0.02, 0.02), a0, a1, za, zb - 0.025)
            stone_blk(bm, rng, (1, 3), (0.02, 0.05), 0.01)
            st.add(bm)
    # 갓돌 (넓고 납작한 돌 고리, 하나는 비뚤어졌다)
    n = 8
    for i in range(n):
        a0 = 2 * math.pi * i / n + 0.025
        a1 = 2 * math.pi * (i + 1) / n - 0.025
        bm = bm_sector(RI - 0.04, RO + 0.06, a0, a1, 0.0, 0.13)
        if i == 5:
            bm_break(bm, rng, (math.cos(a0 + 0.3) * 0.75, math.sin(a0 + 0.3) * 0.75, 0.05), (math.cos(a0 + 0.3), math.sin(a0 + 0.3), 0.3), facets=3, spread=0.4)
        stone_blk(bm, rng, (2, 3), (0.02, 0.05), 0.01)
        M = TR((0, 0, 0.7))
        if i == 2:
            M = TR((0.03, -0.02, 0.72), (R(4), R(-3), R(2)))
        st.add(bm, M)
    # 기둥 받침돌 둘
    for sx in (-1, 1):
        bm = bm_box(0.3, 0.3, 0.3); stone_blk(bm, rng, (2, 3), (0.02, 0.05), 0.01)
        st.add(bm, TR((sx * 0.95, 0, 0.05)))
    so = st.obj("well_stone")
    # 속: 안쪽 우물 벽 (어두운 통) + 깊은 물
    inner = Acc()
    for k_ in range(5):
        za = -0.15 - 0.32 * (k_ + 1)
        n = 9
        off = rng.uniform(0, 6.28)
        for i in range(n):
            a0 = off + 2 * math.pi * i / n + 0.03; a1 = off + 2 * math.pi * (i + 1) / n - 0.03
            bm = bm_sector(RI, RI + 0.22, a0, a1, za, za + 0.3); stone_blk(bm, rng, (1, 2), (0.02, 0.04), 0.008)
            inner.add(bm)
    inner.add(bm_cyl(RI + 0.05, 0.08, 24), TR((0, 0, -1.75)))
    io_ = inner.obj("well_inner")
    hs = join([so, io_])
    # v3 (k7b): 돌 부분만 wall_ruin_a 레시피 (carve+STONE3, paint_block3, finish3 cage 굽기). 나무·밧줄·두레박·쇠는 이전 칠 그대로
    hbase = carve(hs, 0.006, *STONE3(0.9, wear=1.2, cracks=0.6), seed=55, base=True)
    m = paint_block3("well_src", h=0.85, k=0.9, moss=0.85, ao=0.2, moss_low_h=0.45, dirt_h=0.25, grime_h=0.1, edge_w=0.014)
    tint_near(m, (0, 0, -1.2), 1.0, (0.01, 0.012, 0.02), 0.95)                 # 우물 속 어둠
    set_mat(hs, m)
    # 나무: 기둥 둘, 도르래 축(감긴 밧줄), 손잡이, 지붕 틀 (서까래 하나 부러짐), 남은 널빤지 몇 장
    wd = Acc()
    H = 2.05
    for sx in (-1, 1):
        beam(wd, rng, (sx * 0.95, 0.0, 0.15), (sx * 0.95 + rng.uniform(-0.02, 0.02), 0.0, H), 0.13, ref=(0, 1, 0))
    beam(wd, rng, (-1.08, 0, 1.25), (1.26, 0, 1.25), 0.1, ref=(0, 0, 1), rotten=False)       # 축 (네모, 밧줄이 감긴다)
    beam(wd, rng, (1.21, 0, 1.29), (1.21, -0.01, 0.95), 0.055, ref=(0, 1, 0), rotten=False)  # 손잡이 팔
    beam(wd, rng, (1.19, -0.01, 0.98), (1.36, -0.02, 0.98), 0.045, rotten=False)             # 손잡이
    ZR = 2.55
    for sx in (-1, 1):
        beam(wd, rng, (sx * 0.95, -0.7, H - 0.05), (sx * 0.95, 0.0, ZR), 0.09, ref=(1, 0, 0))   # 서까래 (앞)
        if sx < 0:
            beam(wd, rng, (sx * 0.95, 0.7, H - 0.05), (sx * 0.95, 0.32, H + 0.27), 0.09, ref=(1, 0, 0))   # 부러진 서까래 (뒤 왼쪽)
            beam(wd, rng, (sx * 0.95 + 0.2, 0.95, 0.05), (sx * 0.95 + 0.05, 0.38, 0.62), 0.085, ref=(1, 0, 0))   # 떨어져 기댄 토막
        else:
            beam(wd, rng, (sx * 0.95, 0.7, H - 0.05), (sx * 0.95, 0.0, ZR), 0.09, ref=(1, 0, 0))
        beam(wd, rng, (sx * 0.95, -0.72, H - 0.04), (sx * 0.95, 0.72, H - 0.04), 0.08, ref=(0, 0, 1))   # 도리
    beam(wd, rng, (-1.15, 0, ZR + 0.02), (1.1, 0, ZR + 0.02), 0.1, ref=(0, 0, 1))                       # 용마루
    # 남은 지붕 널 (앞쪽 경사 몇 장, 하나는 미끄러져 매달림)
    for i, x in enumerate((-0.85, -0.6, -0.36, 0.55, 0.78)):
        t0 = 0.0 if i != 2 else 0.25
        p0 = Vector((x, -0.75 + t0 * 0.7, H - 0.02 + t0 * 0.5))
        p1 = Vector((x + rng.uniform(-0.03, 0.03), -0.04, ZR + 0.06))
        beam(wd, rng, p0 + Vector((0, 0, 0.07)), p1 + Vector((0, 0, 0.07)), 0.22, 0.03, ref=(0.0, -0.8, 1.0))
    wo = wd.obj("well_wood")
    wh = wood_high(wo, 0.004, 56, "well_wood_src")
    # 밧줄: 축에 감긴 고리 + 늘어져 두레박 손잡이까지
    rp = Acc()
    for i in range(9):
        x = -0.35 + i * 0.045
        v, f = torus_raw(0.075, 0.017, TR((x, 0, 1.25), (0, R(90), 0)) @ TR((0, 0, 0), (0, 0, R(rng.uniform(0, 90)))), 12, 6)
        rp.add_raw(v, f)
    bx, by, bz = 0.32, -0.62, 0.84                        # 두레박 (테두리에 걸쳐 기울었다)
    v, f = rope_path([(0.02, -0.07, 1.24), (0.06, -0.25, 1.02), (0.16, -0.45, 1.0), (0.26, -0.58, 1.08), (bx - 0.02, by, bz + 0.33)], 0.016)
    rp.add_raw(v, f)
    ro = rp.obj("rope")
    rh = copy(ro); origin0(rh); remesh(rh, 0.003)
    surface(rh, [{'t': 'fissure', 'scale': 60, 'width': 0.08, 'depth': 0.003, 'cover': 1.0}, {'t': 'grain', 'scale': 200, 'amp': 0.0006}], 57)
    set_mat(rh, paint("rope_src", ((0.05, 0.04, 0.035), (0.2, 0.17, 0.13), (0.34, 0.3, 0.25)), moss=0.2, moss_color=MOSS_DEAD, dirt=0.2, streaks=0.2, ao=0.02, cracks=0.0))
    # 두레박: 나무 통 + 쇠 테 둘 + 손잡이
    bk = Acc()
    v, f = lathe([(0.0, 0.0), (0.12, 0.0), (0.13, 0.01), (0.15, 0.26), (0.13, 0.26), (0.115, 0.02), (0.0, 0.02)], 16)
    bk.add_raw(v, f)
    bko = bk.obj("bucket")
    bir = Acc()
    for z in (0.05, 0.21):
        v, f = torus_raw(0.125 + z * 0.08, 0.008, TR((0, 0, z)), 16, 4); bir.add_raw(v, f)
    v, f = bar_path([(-0.15, 0, 0.24)] + [(-0.15 * math.cos(a), 0, 0.24 + 0.16 * math.sin(a)) for a in lin(0.2, math.pi - 0.2, 7)] + [(0.15, 0, 0.24)], 0.012)
    bir.add_raw(v, f)
    bio = bir.obj("bucket_iron")
    Mb = TR((bx, by, bz), (R(-28), R(10), R(20)))
    bko.data.transform(Mb); bio.data.transform(Mb)
    bkh = wood_high(bko, 0.0035, 58, "bucket_src")
    bih = iron_high(bio, 0.003, 59)
    lo = low_of(hbase, 3000)
    delete(hbase)
    webs = [web_dim((-0.95 + 0.07, -0.05, H - 0.1), (1, 0, 0), (0, 0, -1), 0.28)]
    tgt = copy(lo)
    v = Vine(random.Random(61), leaf=(0.03, 0.05), leaf_p=0.45)
    ivy_grow(v, tgt, (0.9, 0.3, 0.02), seed=61, length=1.2, max_roots=4)
    delete(tgt)
    hang_strand(v, (-0.6, -0.73, 0.78), 0.45, rng)
    hang_strand(v, (0.7, 0.42, 0.8), 0.35, rng, face=(0.8, 0.6, 0))
    return finish3("well", [hs, wh, rh, bkh, bih], [lo, wo, ro, bko, bio], extras=v.objects() + webs, far_extras=[], size='auto', cage=0.006,
                   cage_reach=0.04, lod1=0.35, lod2=0.12, uv_margin=0.002)


# ═════════════════════════ 무너진 아치 다리 ═════════════════════════
def bridge_ruin():
    rng = random.Random(6606)
    k = 1.4
    gap = 0.045
    SP, ZS, ZT, T = 4.6, -1.6, 1.0, 0.62           # 반 경간, 아치 시작 높이, 아치 꼭대기 아랫면, 홍예석 두께
    YW = 2.0                                       # 반 폭
    r = (SP * SP + (ZT - ZS) ** 2) / (2 * (ZT - ZS))
    zc = ZT - r
    a0 = math.atan2(ZS - zc, SP)                   # 오른쪽 시작 각
    XL = 7.0
    ZB = -2.3                                      # 개울 바닥 아래까지
    deck = lambda x: 0.12 + 1.78 * max(0.0, 1 - (x / XL) ** 2) ** 1.0
    def arch_hole(grow):
        """아치 구멍 (벽 좌표 XZ): 시작 높이 아래는 경간 폭으로 곧게, 위는 반지름 r+grow 원호"""
        rr = r + grow
        xr = math.sqrt(max(0.0, rr * rr - (ZS - zc) ** 2))
        ar = math.atan2(ZS - zc, xr)
        pts = [(rr * math.cos(a), zc + rr * math.sin(a)) for a in lin(ar, math.pi - ar, 26)]       # 오른쪽 → 왼쪽
        return [(-SP, ZB - 0.5), (SP, ZB - 0.5), (SP, ZS)] + pts + [(-SP, ZS)]
    hole = arch_hole(T + gap)
    walls = []
    for sy in (-1, 1):
        M = TR((0, sy * YW, 0)) @ (Matrix.Rotation(R(180), 4, 'Z') if sy > 0 else Matrix.Identity(4))
        Wb = Wall(rng, M, k=k, gap=gap, blen=(0.55, 1.15), skin=(0.35, 0.45), hr=(0.32, 0.44), rot=0.8)
        if sy < 0:
            top = lambda x: deck(x) + (0.86 if not (-1.6 < x < 2.6) else (0.86 - 1.3 * max(0, 1 - abs(x - 0.5) / 2.1) ** 0.7))
        else:
            top = lambda x: deck(-x) + 0.86
        zs = Wb.courses(ZB, 3.0)
        Wb.face(-XL, XL, zs, 0.0, top=top, holes=[ccw(hole)], plinth=0.06, missing=0.02, broken=0.5)
        # 홍예석 (면마다). 줄눈을 벽보다 넓게 (좁으면 리메시·굽기에서 매끈한 띠 하나로 뭉개진다)
        n = 15
        vg = 0.085
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            # 각은 왼쪽(π-a0)에서 오른쪽(a0)으로 줄어든다 → 줄눈은 양쪽 끝을 안쪽으로 당겨서 낸다
            aa = (math.pi - a0) + (a0 - (math.pi - a0)) * t0 - vg / (2 * r)
            ab = (math.pi - a0) + (a0 - (math.pi - a0)) * t1 + vg / (2 * r)
            m = 3
            outer = [(math.cos(aa + (ab - aa) * q / m) * (r + T), zc + math.sin(aa + (ab - aa) * q / m) * (r + T)) for q in range(m + 1)]
            inner = [(math.cos(ab - (ab - aa) * q / m) * r, zc + math.sin(ab - (ab - aa) * q / m) * r) for q in range(m + 1)]
            bm = bm_poly(ccw(outer + inner), -0.04 * k, 0.55, 'y')
            stone_blk(bm, rng, (1, 2), (0.025 * k, 0.06 * k), 0.014 * k)
            sx = -1 if sy > 0 else 1
            c = Vector((sum(p[0] for p in outer) / len(outer), 0, sum(p[1] for p in outer) / len(outer)))
            Mv = Matrix.Identity(4)
            if sy < 0 and i == 8:
                Mv = TR(c + Vector((0, 0, -0.05))) @ Matrix.Rotation(R(2), 4, 'Y') @ TR(-c)     # 조금 내려앉은 홍예석
            Wb.add_bm(bm, Mv)
        walls.append(Wb.acc.obj("bridge_face"))
    # 아치 안쪽 (둥근 천장): 엇갈린 돌 줄
    vb = Acc()
    n = 15
    for i in range(n):
        t0, t1 = i / n, (i + 1) / n
        aa = (math.pi - a0) + (a0 - (math.pi - a0)) * t0 - 0.06 / (2 * r)
        ab = (math.pi - a0) + (a0 - (math.pi - a0)) * t1 + 0.06 / (2 * r)
        y = -YW + 0.5
        first = True
        while y < YW - 0.55:
            ln = rng.uniform(0.6, 1.1) * (rng.uniform(0.4, 1.0) if first else 1.0)
            first = False
            y1 = min(YW - 0.5, y + ln)
            m = 2
            outer = [(math.cos(aa + (ab - aa) * q / m) * (r + 0.4), zc + math.sin(aa + (ab - aa) * q / m) * (r + 0.4)) for q in range(m + 1)]
            inner = [(math.cos(ab - (ab - aa) * q / m) * r, zc + math.sin(ab - (ab - aa) * q / m) * r) for q in range(m + 1)]
            bm = bm_poly(ccw(outer + inner), y + gap / 2, y1 - gap / 2, 'y')
            stone_blk(bm, rng, (0, 2), (0.02 * k, 0.05 * k), 0.012 * k, flakes=(0, 1))
            vb.add(bm)
            y = y1
    walls.append(vb.obj("bridge_vault"))
    # 속 (채움)
    core = Acc()
    poly = [(-XL + 0.25, ZB)] + [(-XL + 0.25, deck(-XL + 0.25) - 0.18)] + [(x, deck(x) - 0.18) for x in lin(-XL + 0.6, XL - 0.6, 30)] + \
           [(XL - 0.25, deck(XL - 0.25) - 0.18), (XL - 0.25, ZB)]
    core.add(bm_poly(ccw(poly), -YW + 0.3, YW - 0.3, 'y'))
    co = core.obj("bridge_core")
    kit.cut(co, [zone_prism(arch_hole(0.05), -YW - 1, YW + 1)])
    walls.append(co)
    # 물가름 (아치 발치 양쪽, 위·아래 물쪽)
    cw = Acc()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0 = sx * (SP + 0.35)
            poly = [(-0.75, 0.0), (0.75, 0.0), (0.0, -1.0)]
            z = ZB
            while z < ZS + 0.6:
                h = min(rng.uniform(0.32, 0.42), ZS + 0.7 - z)
                bm = bm_poly(poly, z, z + h - gap, 'z')
                stone_blk(bm, rng, (1, 3), (0.03, 0.07), 0.014)
                cw.add(bm, TR((x0, sy * YW, 0)) @ Matrix.Rotation(R(0 if sy < 0 else 180), 4, 'Z'))
                z += h
            bm = bm_pyramid(1.5, 0.6, d=1.0, sides=4, rot=45)
            bm_chip(bm, rng, 2, (0.03, 0.06))
            cw.add(bm, TR((x0, sy * (YW + 0.45), ZS + 0.65)))
    walls.append(cw.obj("cutwater"))
    # 난간 갓돌 + 다리 위 포장
    tp = Acc()
    for sy in (-1, 1):
        x = -XL
        while x < XL - 0.2:
            ln = min(rng.uniform(0.7, 1.1), XL - x)
            xm = x + ln / 2
            if sy < 0 and -1.9 < xm < 2.9:
                x += ln; continue
            th = math.atan(-3.56 * xm / (XL * XL))
            bm = bm_box(ln - 0.035, 0.62, 0.2); stone_blk(bm, rng, (1, 3), (0.02, 0.06), 0.014)
            tp.add(bm, TR((xm, sy * (YW - 0.22), deck(xm) + 0.96), (0, -th, 0)))
            x += ln
    x = -XL + 0.1
    while x < XL - 0.2:
        ln = min(rng.uniform(0.55, 0.85), XL - 0.1 - x)
        y = -YW + 0.45
        while y < YW - 0.5:
            wy = min(rng.uniform(0.5, 0.9), YW - 0.45 - y)
            xm = x + ln / 2
            th = math.atan(-3.56 * xm / (XL * XL))
            if rng.random() > 0.05:
                bm = bm_box(ln - 0.04, wy - 0.04, 0.16)
                if rng.random() < 0.15:
                    bm_break(bm, rng, (0, 0, 0), (rng.choice((-1, 1)), rng.uniform(-0.6, 0.6), 0.3), facets=2)
                stone_blk(bm, rng, (1, 2), (0.02, 0.05), 0.012, flakes=(0, 1))
                tp.add(bm, TR((xm, y + wy / 2, deck(xm) - 0.06 + rng.uniform(-0.02, 0.015)), (R(rng.uniform(-1.2, 1.2)), -th + R(rng.uniform(-1, 1)), 0)))
            y += wy
        x += ln
    walls.append(tp.obj("bridge_top"))
    # 무너진 난간 돌 (개울 바닥에), 잔돌
    fl = Acc()
    ext = []
    for (x, y, sz) in ((0.2, -3.0, (0.7, 0.45, 0.42)), (1.4, -3.6, (0.62, 0.42, 0.4)), (-0.9, -3.3, (0.66, 0.44, 0.4)), (2.3, -2.8, (0.5, 0.4, 0.36))):
        fallen_block(fl, rng, (x, y, 0), sz, k=k, z=-2.0)
    rubble_pile(fl, rng, (0.6, -3.2, -2.05), 1.1, 9, (0.22, 0.45), 0.5, extra=ext, k=k)
    walls.append(fl.obj("bridge_fallen"))
    body = join(walls + ext)
    # v3 (k7b): wall_ruin_a 레시피 — carve+STONE3 (저폴리는 바탕에서: 걷는 면 높이는 조립품 그대로), paint_block3, finish3 cage 굽기.
    # 땅이 z=0 이 아니라 개울 바닥이라 paint3 의 흙물·아래 이끼는 끄고, 물에 잠겼던 띠는 이전처럼 따로 (짙은 올리브)
    base = carve(body, 0.02 * VOX, *STONE3(1.5, wear=1.2, cracks=0.6), seed=66, base=True)
    m = paint_block3("bridge_src", h=2.9, k=1.4, ao=0.6, dirt=0.0, moss_low=0.0, grime_h=0.2)
    moss_low(m, ZB, -0.9, 0.95, color=BLOCK3_MOSS_LATE, scale=1.6)   # 물에 잠겼던 아래쪽: 진한 이끼 띠
    dirt_low(m, ZB, -1.6, 0.8, (0.03, 0.028, 0.024))
    set_mat(body, m)
    low = low_of(base, 12500, z=-9.0)
    delete(base)
    vines = ivy_on(low, [((-XL + 0.3, -YW - 0.2, 0.05), 3, 4.0, 5), ((XL - 0.5, YW + 0.2, 0.05), 5, 3.0, 4)], 67, leaf=(0.06, 0.1), leaf_p=0.4,
                   hangs=[((x, -YW - 0.05, deck(x) + 0.3), ln, (0, -1, 0)) for x, ln in ((-3.2, 1.6), (-2.4, 2.4), (3.4, 1.3))] +
                         [((x, YW + 0.05, deck(x) + 0.9), ln, (0, 1, 0)) for x, ln in ((-1.0, 2.2), (0.6, 1.5), (2.0, 2.6))])
    return finish3("bridge_ruin", [body], [low], extras=vines, far_extras=[], size=2048, cage=0.012, cage_reach=0.1, lod1=0.35, lod2=0.12,
                   uv_margin=0.001)


# ═════════════════════════ 둥근 돌 망루 ═════════════════════════
def wrap_pi(a):
    return (a + math.pi) % (2 * math.pi) - math.pi

def round_wall(acc, rng, r_face, depth, outward, zs, top, holes, k=1.0, gap=0.04, blen=(0.6, 1.1), missing=0.0, broken=0.45, plinth=0.0):
    """둥근 벽 한 면의 블록 켜. outward=+1 바깥면 (블록은 안쪽으로 depth), -1 안쪽면 (블록은 바깥쪽으로).
    holes: [(중심각, (u,z) 다각형)] u = 면 위 호 길이 (구멍 가운데 0). top(θ): 무너진 윗선"""
    hl = [(th0, ccw(poly)) for th0, poly in holes]
    for i in range(len(zs) - 1):
        za, zb = zs[i], zs[i + 1] - gap
        a = rng.uniform(0, 2 * math.pi)
        a_end = a + 2 * math.pi
        first = True
        while a < a_end - 0.05:
            L = rng.uniform(*blen) * (rng.uniform(0.4, 1.0) if first else 1.0)
            first = False
            da = L / r_face
            b = min(a_end, a + da)
            if a_end - b < blen[0] * 0.4 / r_face:
                b = a_end
            am = (a + b) / 2
            if i > 0 and rng.random() < missing:
                a = b; continue
            t_here = top(am)
            r0, r1 = (r_face - depth, r_face + (plinth if i == 0 else 0.0)) if outward > 0 else (r_face - (plinth if i == 0 else 0.0), r_face + depth)
            if za > t_here - 0.06 * k:
                a = b; continue
            ga = gap / (2 * r_face)
            bm = bm_sector(r0, r1, a + ga, b - ga, za, zb)
            ok = True
            cuts = []
            if zb > t_here + 0.04 * k:
                h_loc = t_here + rng.uniform(-0.12, 0.1) * k
                if h_loc < za + (zb - za) * 0.3 or rng.random() > broken:
                    ok = False
                else:
                    rad = Vector((math.cos(am), math.sin(am), 0))
                    tan = Vector((-math.sin(am), math.cos(am), 0))
                    sl = (top(b) - top(a)) / max(0.05, (b - a) * r_face) * rng.uniform(-0.6, 1.6)
                    nn = (Vector((0, 0, 1)) - tan * sl + rad * rng.uniform(-0.5, 0.5) + tan * rng.uniform(-0.6, 0.6)).normalized()
                    for f in range(rng.randint(2, 3)):
                        n2 = (nn + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * 0.45).normalized()
                        cuts.append((rad * (r0 + r1) / 2 + tan * rng.uniform(-0.15, 0.15) * k + Vector((0, 0, h_loc + rng.uniform(-0.05, 0.05) * k)), n2))
            if ok:
                for th0, poly in hl:
                    ua = wrap_pi(a - th0) * r_face
                    ub = wrap_pi(b - th0) * r_face
                    if ub < ua:
                        continue
                    fr, pin = rect_vs_poly(poly, ua, ub, za, zb)
                    if fr == 0 and not pin:
                        continue
                    if fr >= 0.45 or poly_inside(poly, (ua + ub) / 2, (za + zb) / 2):
                        ok = False
                        break
                    (pu, pz), (nu, nz) = poly_nearest(poly, (ua + ub) / 2, (za + zb) / 2)
                    thp = th0 + pu / r_face
                    tan = Vector((-math.sin(thp), math.cos(thp), 0))
                    co = Vector((math.cos(thp), math.sin(thp), 0)) * ((r0 + r1) / 2) + Vector((0, 0, pz))
                    cuts.append((co, (tan * nu + Vector((0, 0, nz))).normalized()))
            if not ok:
                bm.free(); a = b; continue
            for co, no in cuts:
                bm_cut(bm, co, no)
                if len(bm.verts) < 4:
                    break
            if len(bm.verts) >= 4:
                stone_blk(bm, rng, (1, 3), (0.02 * k, 0.06 * k), 0.014 * k, flakes=(0, 1))
                acc.add(bm, TR((0, 0, 0), (0, 0, R(rng.uniform(-0.3, 0.3)))))
            else:
                bm.free()
            a = b

def ring_core(r0, r1, z0, top, n=96, drop=0.25, jag=0.15, rng=None):
    rng = rng or random.Random(0)
    verts, faces = [], []
    tops = [max(z0 + 0.2, top(2 * math.pi * i / n) - drop - rng.uniform(0, jag)) for i in range(n)]
    for i in range(n):
        a = 2 * math.pi * i / n
        c, s_ = math.cos(a), math.sin(a)
        verts += [(r0 * c, r0 * s_, z0), (r1 * c, r1 * s_, z0), (r1 * c, r1 * s_, tops[i]), (r0 * c, r0 * s_, tops[i])]
    for i in range(n):
        j = (i + 1) % n
        A, B = 4 * i, 4 * j
        faces += [(A, B, B + 1, A + 1), (A + 1, B + 1, B + 2, A + 2), (A + 2, B + 2, B + 3, A + 3), (A + 3, B + 3, B, A)]
    return mesh_from("ring_core", verts, faces)

def watchtower_ruin():
    rng = random.Random(7707)
    k = 1.25
    gap = 0.045
    RO, RI = 2.85, 1.95
    TH = 0.9
    def top(th):
        return 9.0 + 2.9 * math.cos(th - R(125)) + 0.45 * math.sin(5 * th + 0.7) + 0.3 * math.sin(11 * th + 2.0) + 0.2 * math.sin(17 * th)
    FRONT = R(270)
    door = (FRONT, arch_outline(1.25, 2.15, 0.85, grow=0.4 + gap, z_bottom=-0.3, steps=8))
    slits = [(R(205), 3.0, 4.3), (R(335), 4.1, 5.4), (R(55), 3.4, 4.7), (R(150), 7.4, 8.7), (R(15), 6.9, 8.0)]
    holes = [door] + [(th, [(-0.28, z0 - 0.12), (0.28, z0 - 0.12), (0.28, z1 + 0.12), (-0.28, z1 + 0.12)]) for th, z0, z1 in slits]
    win = (R(100), arch_outline(0.85, 9.6, 0.6, grow=0.32 + gap, z_bottom=8.2, steps=6))
    holes.append(win)
    st = Acc()
    zs_o = [-0.2, 0.35] + [z for z in lin(0.35, 13.0, 31)][1:]
    zs_o = [-0.2, 0.35]
    while zs_o[-1] < 13:
        zs_o.append(zs_o[-1] + rng.uniform(0.34, 0.46))
    round_wall(st, rng, RO, 0.42, 1, zs_o, top, holes, k=k, gap=gap, missing=0.015, plinth=0.08)
    round_wall(st, rng, RI, 0.4, -1, zs_o, top, holes, k=k, gap=gap, missing=0.02)
    # 기울어진 굽 (밑동을 감싼 경사진 돌)
    n = 22
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n + 0.012, 2 * math.pi * (i + 1) / n - 0.012
        if abs(wrap_pi((a0 + a1) / 2 - FRONT)) < 0.3:
            continue
        bm = bm_sector(RO - 0.3, RO + 0.42, a0, a1, -0.2, 0.62)
        am = (a0 + a1) / 2
        bm_cut(bm, Vector((math.cos(am), math.sin(am), 0)) * (RO + 0.05) + Vector((0, 0, 0.62)), (math.cos(am), math.sin(am), 0.9))
        stone_blk(bm, rng, (1, 3), (0.03, 0.07), 0.014)
        st.add(bm)
    # 문 둘레 (홍예석 + 문설주), 위 창
    Md = TR((math.cos(FRONT) * (RO - TH / 2), math.sin(FRONT) * (RO - TH / 2), 0)) @ Matrix.Rotation(FRONT + math.pi / 2, 4, 'Z')
    for tag, bm, c in arch_stones(rng, 1.25, 2.15, 0.85, 0.4, 4, -TH / 2 - 0.08, TH / 2 + 0.08, gap, chips=(1, 2), k=k):
        st.add(bm, Md)
    jamb_stones(st, rng, 1.25, 0.0, 2.15, 0.4, -TH / 2 - 0.08, TH / 2 + 0.08, gap, hr=(0.34, 0.46), M=Md, k=k)
    th_w = win[0]
    Mw = TR((math.cos(th_w) * (RO - TH / 2), math.sin(th_w) * (RO - TH / 2), 0)) @ Matrix.Rotation(th_w + math.pi / 2, 4, 'Z')
    for tag, bm, c in arch_stones(rng, 0.85, 9.6, 0.6, 0.32, 3, -TH / 2 - 0.06, TH / 2 + 0.06, gap, chips=(1, 2), k=1.0):
        if c.z > top(th_w + c.x / RO) - 0.2:
            bm.free(); continue
        st.add(bm, Mw)
    jambs_top(st, rng, 0.85, 8.2, 9.6, 0.32, -TH / 2 - 0.06, TH / 2 + 0.06, gap, (0.3, 0.42), Mw, 1.0, top=lambda x: top(th_w + x / RO))
    bm = bm_box(1.6, TH + 0.2, 0.2); stone_blk(bm, rng, (2, 3), (0.02, 0.05), 0.012)
    st.add(bm, Mw @ TR((0, 0, 8.1)))
    so = st.obj("tower_stone")
    core = ring_core(RI + 0.22, RO - 0.24, -0.2, top, 120, 0.28, 0.2, rng)
    cz = []
    a = Acc(); a.add(bm_poly(ccw(arch_outline(1.25, 2.15, 0.85, z_bottom=-0.5)), -1.5, 1.5, 'y'), Md); cz.append(a.obj("dz"))
    a = Acc(); a.add(bm_poly(ccw(arch_outline(0.85, 9.6, 0.6, z_bottom=8.2)), -1.5, 1.5, 'y'), Mw); cz.append(a.obj("wz"))
    for th, z0, z1 in slits:
        Ms = TR((math.cos(th) * (RO - TH / 2), math.sin(th) * (RO - TH / 2), (z0 + z1) / 2)) @ Matrix.Rotation(th + math.pi / 2, 4, 'Z')
        a = Acc(); a.add(bm_box(0.16, 3.0, z1 - z0), Ms); cz.append(a.obj("sz"))
        a = Acc(); a.add(bm_box(0.6, 0.6, z1 - z0 + 0.1), Ms @ TR((0, 0.45, 0)), ); cz.append(a.obj("sz2"))     # 안쪽으로 벌어진 틈
    kit.cut(core, cz)
    # 무너진 돌: 낮은 쪽(앞 오른쪽) 바깥 더미, 안쪽 바닥
    fl = Acc()
    ext = []
    rubble_pile(fl, rng, (2.6, -3.4, 0), 1.6, 16, (0.25, 0.55), 0.9, extra=ext, k=k)
    rubble_pile(fl, rng, (0.4, 0.3, 0), 1.3, 12, (0.22, 0.45), 0.7, extra=ext, k=k)
    for (x, y, sz) in ((4.2, -1.6, (0.6, 0.4, 0.38)), (3.5, -4.9, (0.55, 0.42, 0.36)), (-0.6, -4.4, (0.5, 0.38, 0.34)), (4.6, 0.8, (0.5, 0.4, 0.36))):
        fallen_block(fl, rng, (x, y, 0), sz, k=k)
    fo = fl.obj("tower_fallen")
    rub = []
    for i in range(70):
        th = 2 * math.pi * (i + rng.random()) / 70
        s_ = rng.uniform(0.12, 0.25)
        p = Vector((math.cos(th) * (RO + RI) / 2, math.sin(th) * (RO + RI) / 2, top(th) - 0.2 + s_ * 0.2))
        c = chunk((0, 0, 0), (s_, s_ * 0.8, s_ * 0.6), rng, 8)
        c.data.transform(Matrix.Translation(p)); rub.append(c)
    body = join([so, core, fo] + ext + rub)
    pre = copy(body)
    # v3 (k7b): wall_ruin_a 레시피 (돌 부분). 나무 들보는 이전 칠 그대로. 저폴리는 이전처럼 조각 전 조립품에서
    carve(body, 0.018 * VOX, *STONE3(1.4, wear=1.2, cracks=0.6), seed=77)
    m = paint_block3("watchtower_src", h=12.0, k=1.4, ao=0.6, dirt_h=1.0, moss_low_h=1.5, grime_h=0.22)
    set_mat(body, m)
    # 썩은 나무 들보: 1층 마루 (가운데 하나 부러져 처짐), 바깥으로 삐져나온 토막, 쓰러져 기댄 들보
    wd = Acc()
    for y in (-0.9, 0.95):
        x = math.sqrt(RI * RI - y * y) + 0.25
        beam(wd, rng, (-x, y, 4.55), (x, y + rng.uniform(-0.05, 0.05), 4.55), 0.24, 0.28, ref=(0, 0, 1))
    xm = math.sqrt(RI * RI) + 0.25
    beam(wd, rng, (-xm, 0.05, 4.55), (0.15, 0.08, 4.35), 0.24, 0.28, ref=(0, 0, 1))           # 부러져 처진 들보
    beam(wd, rng, (0.25, 0.12, 4.2), (1.05, 0.3, 2.3), 0.22, 0.26, ref=(0, 0, 1))
    beam(wd, rng, (-1.2, -1.3, 0.05), (-0.2, -1.62, 3.4), 0.22, 0.26, ref=(0, 0, 1))            # 쓰러져 벽에 기댄 들보
    for th, z in ((R(110), 9.2), (R(160), 9.0)):
        p0 = Vector((math.cos(th) * (RI - 0.3), math.sin(th) * (RI - 0.3), z))
        p1 = Vector((math.cos(th) * (RO + 0.75), math.sin(th) * (RO + 0.75), z - 0.08))
        if top(th) > z + 0.4:
            beam(wd, rng, p0, p1, 0.2, 0.22, ref=(0, 0, 1))
    for i in range(6):                                                                         # 바닥 널 몇 장 (들보 위에 남은)
        x = -1.2 + i * 0.27 + rng.uniform(-0.03, 0.03)
        if i in (3,):
            continue
        y0_, y1_ = -1.25 + rng.uniform(0, 0.3), 1.2 - rng.uniform(0, 0.5)
        beam(wd, rng, (x, y0_, 4.72), (x + rng.uniform(-0.04, 0.04), y1_, 4.72 + rng.uniform(-0.03, 0.03)), 0.24, 0.04, ref=(0, 0, 1))
    wo = wd.obj("tower_wood")
    wh = wood_high(wo, 0.006, 78, "tower_wood_src", pal=((0.02, 0.016, 0.018), (0.1, 0.075, 0.065), (0.24, 0.2, 0.18)))
    low = low_coarse(pre, 0.06, 11000)
    delete(pre)
    vines = ivy_on(low, [((math.cos(R(140)) * (RO + 0.3), math.sin(R(140)) * (RO + 0.3), 0.05), 3, 7.0, 7),
                         ((math.cos(R(60)) * (RO + 0.3), math.sin(R(60)) * (RO + 0.3), 0.05), 5, 3.5, 4)], 71, leaf=(0.06, 0.1), leaf_p=0.36,
                   hangs=[((math.cos(R(120)) * (RO + 0.06), math.sin(R(120)) * (RO + 0.06), top(R(120)) - 0.3), 2.4, (math.cos(R(120)), math.sin(R(120)), 0)),
                          ((math.cos(R(175)) * (RO + 0.06), math.sin(R(175)) * (RO + 0.06), top(R(175)) - 0.3), 1.6, (math.cos(R(175)), math.sin(R(175)), 0))])
    return finish3("watchtower_ruin", [body, wh], [low, wo], extras=vines, far_extras=[], size=2048, cage=0.012, cage_reach=0.15,
                   lod1=0.35, lod2=0.12, uv_margin=0.001)


# ═════════════════════════ 2장으로 가는 거대한 관문 ═════════════════════════
def rune_band(stone_obj, rng, centers, size, n_dir, up_dirs, width=0.05, lift=0.015, glyph0=0):
    """돌 면 위에 룬 획을 발광 띠로 얹는다 (면에서 lift 만큼 띄워 조각 굴곡에 묻히지 않게).
    처음에는 불리언으로 홈을 팠으나, 겹치는 획 커터 수십 개의 EXACT 불리언이 메모리를 10GB 넘게 써서 뺐다.
    centers: 글자 가운데 점들 (면 위), up_dirs: 글자 위 방향"""
    strokes_all = []
    n = Vector(n_dir).normalized()
    for i, (c, up) in enumerate(zip(centers, up_dirs)):
        v = Vector(up).normalized()
        t = v.cross(n).normalized()
        strokes_all += glyph_strokes(glyph0 + i, Vector(c), t, v, n, size * 0.42, size * 0.5)
    g = stroke_glow(strokes_all, n, width, lift=lift)
    return glow(g, 'Glow_Spirit') if g else None

def gate_great():
    rng = random.Random(8808)
    k = 1.7
    gap = 0.085
    hr, blen, skin = (0.46, 0.62), (0.8, 1.6), (0.4, 0.5)
    runes = []                                  # 룬을 새긴 돌: 따로 곱게 조각한다 (거친 리메시가 홈을 메워 발광이 묻힌다)
    TX0, TX1, TY = 3.5, 8.0, 2.6               # 탑: x 3.5~8.0 (양쪽), y ±2.6
    ZT = 13.0                                  # 탑 벽 높이 (흉벽 아래)
    GY = 1.25                                  # 문 벽 반두께
    ZG = 11.0                                  # 문 벽 높이
    AW, AH, AR, AT = 5.0, 5.4, 3.6, 0.85       # 문 아치
    parts = []
    glows = []
    # ── 탑 둘 ──
    for sx in (-1, 1):
        xc = sx * (TX0 + TX1) / 2
        tw = TX1 - TX0
        ttop = profile([(-3, ZT), (3, ZT)])
        faces = [(TR((xc, -TY, 0)), tw, ttop), (TR((xc, TY, 0)) @ Matrix.Rotation(R(180), 4, 'Z'), tw, ttop),
                 (TR((sx * TX1, 0, 0)) @ Matrix.Rotation(R(90 * sx), 4, 'Z'), 2 * TY, ttop),
                 (TR((sx * TX0, 0, 0)) @ Matrix.Rotation(R(-90 * sx), 4, 'Z'), 2 * TY, ttop)]
        for fi, (M, w_, tp) in enumerate(faces):
            W_ = Wall(rng, M, k=k, gap=gap, blen=blen, skin=skin, hr=hr, rot=0.6)
            if fi == 0 and sx < 0:
                W_.cracks = [(crack_line(rng, (0.9, 0.3), (0.3, 1.0), 6.5, 9), 0.07)]
            if fi == 2:
                W_.cracks = [(crack_line(rng, (-0.6, 5.0), (-0.2, 1.0), 6.0, 8), 0.06)]
            holes = []
            if fi == 0:
                holes = [[(-0.32, 8.0), (0.32, 8.0), (0.32, 9.6), (-0.32, 9.6)]]
            if fi == 3:
                # 문 벽이 붙는 안쪽 면: 문 벽 높이까지는 비워 둔다
                holes = [[(-GY - 0.05, -0.5), (GY + 0.05, -0.5), (GY + 0.05, ZG - 0.2), (-GY - 0.05, ZG - 0.2)]]
            W_.face(-w_ / 2 - 0.3, w_ / 2 + 0.3, W_.courses(-0.2, ZT), 0.0, holes=holes, plinth=0.1, missing=0.015)
            # 흉벽 (총안 사이 돌)
            x = -w_ / 2
            i = 0
            while x < w_ / 2 - 0.3:
                mw = 0.95 if i % 2 == 0 else 0.6
                if i % 2 == 0 and not (sx > 0 and fi in (0, 2) and x > 0.2 and rng.random() < 0.6):
                    hh = 1.05 if rng.random() > 0.2 else rng.uniform(0.4, 0.7)
                    bm = bm_box(min(mw, w_ / 2 - x) - gap, 0.62, hh)
                    if hh > 0.9 and rng.random() < 0.35:
                        bm_break(bm, rng, (0.1, 0, 0.3), (rng.uniform(-1, 1), -0.3, 1), facets=3, spread=0.5)
                    stone_blk(bm, rng, (2, 4), (0.03 * k, 0.07 * k), 0.016 * k)
                    W_.add_bm(bm, TR((x + mw / 2, 0.31, ZT + 0.22 + hh / 2)))
                x += mw
                i += 1
            # 흉벽 아래 돌림띠 (내민 띠)
            x = -w_ / 2 - 0.35
            while x < w_ / 2 + 0.3:
                ln = min(rng.uniform(0.9, 1.4), w_ / 2 + 0.35 - x)
                bm = bm_box(ln - gap, 0.75, 0.32); stone_blk(bm, rng, (1, 3), (0.03, 0.07), 0.016)
                W_.add_bm(bm, TR((x + ln / 2, 0.22, ZT + 0.06)))
                x += ln
            parts.append(W_.acc.obj("gate_tower"))
        core = Acc()
        core.add(bm_box(tw - 0.5, 2 * TY - 0.5, ZT + 0.4), TR((xc, 0, (ZT + 0.4) / 2 - 0.2)))
        co = core.obj("tower_core")
        kit.cut(co, [zone_prism([(-0.2, 8.1), (0.2, 8.1), (0.2, 9.5), (-0.2, 9.5)], -0.5, 1.0, TR((xc, -TY, 0)))])
        parts.append(co)
        # 굽 (밑동 경사돌)
        bt = Acc()
        for (M, w_) in ((TR((xc, -TY, 0)), tw), (TR((sx * TX1, 0, 0)) @ Matrix.Rotation(R(90 * sx), 4, 'Z'), 2 * TY),
                        (TR((xc, TY, 0)) @ Matrix.Rotation(R(180), 4, 'Z'), tw)):
            x = -w_ / 2 - 0.45
            while x < w_ / 2 + 0.4:
                ln = min(rng.uniform(0.9, 1.5), w_ / 2 + 0.45 - x)
                bm = bm_wedge(ln - gap, 0.95, 1.25)
                bm_chip(bm, rng, 2, (0.04, 0.08)); bm_bevel(bm, 0.02)
                bt.add(bm, M @ TR((x + ln / 2, -0.2, -0.2)))
                x += ln
        parts.append(bt.obj("tower_batter"))
    # ── 문 벽 (가운데, 아치) ──
    arch = Acc()
    for sy, M in ((-1, TR((0, -GY, 0))), (1, TR((0, GY, 0)) @ Matrix.Rotation(R(180), 4, 'Z'))):
        W_ = Wall(rng, M, k=k, gap=gap, blen=blen, skin=skin, hr=hr, rot=0.6)
        if sy < 0:
            W_.cracks = [(crack_line(rng, (1.8, AH + AR + 0.9), (0.35, 1.0), 2.2, 5), 0.06)]
        W_.face(-TX0 - 0.2, TX0 + 0.2, W_.courses(-0.2, ZG), 0.0, holes=[ccw(arch_outline(AW, AH, AR, grow=AT + gap, z_bottom=-0.5))], plinth=0.08)
        # 홍예석: 앞면 것은 따로 모아 룬을 새긴다
        for tag, bm, c in arch_stones(rng, AW, AH, AR, AT, 8, -0.06, 0.62, gap, chips=(1, 2), k=k):
            if sy < 0:
                arch.add(bm, M)
            else:
                W_.add_bm(bm, Matrix.Identity(4))
        jamb_stones(W_.acc, rng, AW, 0.0, AH, AT, -0.06, 0.62, gap, hr=hr, M=W_.M, k=k)
        if sy < 0:
            # 내민 흉벽을 받치는 까치발 줄 (석루조)
            for i in range(9):
                x = -3.2 + 6.4 * i / 8
                for lvl in range(3):
                    bm = bm_box(0.42 - 0.04 * lvl, 0.25 + 0.17 * lvl, 0.3)
                    bm_chip(bm, rng, 1, (0.02, 0.05))
                    W_.add_bm(bm, TR((x, -(0.12 + 0.085 * lvl) + 0.12, ZG - 1.0 + 0.3 * lvl)))
            x = -TX0 - 0.1
            while x < TX0 + 0.1:
                ln = min(rng.uniform(0.9, 1.4), TX0 + 0.1 - x)
                bm = bm_box(ln - gap, 0.6, 1.25); stone_blk(bm, rng, (1, 3), (0.03, 0.07), 0.016)
                W_.add_bm(bm, TR((x + ln / 2, -0.38, ZG + 0.38)))
                x += ln
        else:
            x = -TX0 + 0.2
            while x < TX0 - 0.3:
                bm = bm_box(0.85 - gap, 0.6, 0.95); stone_blk(bm, rng, (2, 3), (0.03, 0.07), 0.016)
                W_.add_bm(bm, TR((x + 0.42, 0.3, ZG + 0.45)))
                x += 1.45
        parts.append(W_.acc.obj("gate_wall"))
    ao = arch.obj("gate_arch_front")
    remesh(ao, 0.016)
    # 앞 홍예석마다 룬 하나 (아치를 따라 위를 향해)
    cx_, r_, a_end = arch_geo(AW, AH, AR)
    cs, ups = [], []
    for i in range(8):
        for sxx in (-1, 1):
            a = (i + 0.5) * a_end / 8.5
            rr = r_ + AT / 2
            p = Vector((sxx * (cx_ + rr * math.cos(a)), -GY - 0.065, AH + rr * math.sin(a)))
            cs.append(p)
            ups.append(Vector((sxx * math.cos(a), 0, math.sin(a))))
    g = rune_band(ao, rng, cs, 0.56, (0, -1, 0), ups, width=0.075, lift=0.02)
    if g:
        glows.append(g)
    runes.append(ao)
    # 탑 앞 룬 판석 (세로로 넷)
    for sx in (-1, 1):
        a = Acc()
        bm = bm_box(1.05, 0.34, 4.8); bm_chip(bm, rng, 3, (0.03, 0.08)); bm_bevel(bm, 0.03)
        a.add(bm, TR((sx * 5.75, -TY - 0.1, 4.8)))
        pl = a.obj("rune_plaque")
        remesh(pl, 0.014)
        g = rune_band(pl, rng, [Vector((sx * 5.75, -TY - 0.27, z)) for z in (3.15, 4.25, 5.35, 6.45)], 0.7, (0, -1, 0), [Vector((0, 0, 1))] * 4, width=0.08, lift=0.02, glyph0=3 if sx > 0 else 0)
        if g:
            glows.append(g)
        runes.append(pl)
    # 속: 문 벽 (아치 통로)
    core = Acc()
    core.add(bm_box(2 * TX0 + 0.4, 2 * GY - 0.5, ZG + 0.5), TR((0, 0, (ZG + 0.5) / 2 - 0.2)))
    co = core.obj("gate_core")
    kit.cut(co, [zone_prism(arch_outline(AW, AH, AR, z_bottom=-0.5), -GY - 1, GY + 1)])
    parts.append(co)
    # 떨어진 흉벽 돌, 잔돌
    fl = Acc()
    ext = []
    for (x, y, sz) in ((7.3, -4.0, (0.95, 0.6, 0.55)), (5.6, -4.6, (0.9, 0.6, 0.5)), (8.9, -2.2, (0.8, 0.6, 0.5)), (-8.7, -3.6, (0.9, 0.6, 0.5))):
        fallen_block(fl, rng, (x, y, 0), sz, k=k)
    rubble_pile(fl, rng, (7.0, -4.2, 0), 1.3, 9, (0.3, 0.6), 0.6, extra=ext, k=k)
    parts.append(fl.obj("gate_fallen"))
    body = join(parts + ext)
    pre = copy(body)
    # v3 (k7b): wall_ruin_a 레시피 (돌 부분): carve+STONE3, paint_block3, finish3 cage 굽기. 쇠창살·룬돌 조각은 이전 그대로
    carve(body, 0.033 * VOX, *STONE3(1.9, wear=1.2, cracks=0.6), seed=88)
    rh = join(runes)
    surface(rh, [{'t': 'lumps', 'scale': 2.5, 'amp': 0.006}, {'t': 'terrace', 'scale': 4, 'steps': 3, 'amp': 0.005, 'cover': 0.5},
                 {'t': 'pits', 'scale': 30, 'depth': 0.003, 'cover': 0.5}, {'t': 'grain', 'scale': 80, 'amp': 0.0008}], seed=87)
    m = paint_block3("gate_src", h=14.0, k=1.7, moss=0.7, ao=0.8, dirt_h=1.3, moss_low_h=1.7, grime_h=0.26, edge_w=0.03)
    tint_near(m, (0, -GY - 0.3, AH + AR * 0.5), 4.5, (0.22, 0.45, 0.55), 0.22)        # 룬 빛에 물든 돌
    set_mat(body, m)
    # 룬돌은 carve 를 거치지 않아 블록 번호(piece·ptop)가 없다 → 줄눈 때(grime)가 온 옆면에 깔리지 않게 끈 같은 칠
    mr = paint_block3("gate_rune_src", h=14.0, k=1.7, moss=0.7, ao=0.8, dirt_h=1.3, moss_low_h=1.7, grime=0.0, edge_w=0.03)
    tint_near(mr, (0, -GY - 0.3, AH + AR * 0.5), 4.5, (0.22, 0.45, 0.55), 0.22)
    set_mat(rh, mr)
    rl = low_of(rh, 2600)
    # ── 내리닫이 쇠창살 (닫힘) + 봉인 고리 ──
    ir = Acc()
    def arch_z(x):
        ax = abs(x)
        if ax >= AW / 2:
            return AH
        return AH + math.sqrt(max(0.0, r_ * r_ - (ax - cx_) ** 2))
    nb = 12
    for i in range(nb):
        x = -AW / 2 + 0.28 + (AW - 0.56) * i / (nb - 1)
        zt = arch_z(x) + 0.35
        v, f = bar_path([(x, 0, 0.12), (x, 0, zt)], 0.11, 0.09); ir.add_raw(v, f)
        v, f = spear((x, 0, 0.14), (0, 0, -1), 0.26, 0.09, 0.03, 0.035); ir.add_raw(v, f)
    z = 0.75
    while z < AH + AR - 0.4:
        xs = [x for x in lin(-AW / 2, AW / 2, 200) if arch_z(x) > z + 0.1]
        if xs:
            v, f = bar_path([(xs[0] - 0.05, -0.08, z), (xs[-1] + 0.05, -0.08, z)], 0.1, 0.06); ir.add_raw(v, f)
            for i in range(nb):
                x = -AW / 2 + 0.28 + (AW - 0.56) * i / (nb - 1)
                if xs[0] < x < xs[-1]:
                    ir.add(bm_pyramid(0.07, 0.05), TR((x, -0.11, z), (R(90), 0, 0)))
        z += 0.88
    # 봉인: 쇠 고리 둘 + 가운데 원판
    SZ = 3.9
    v, f = torus_raw(1.05, 0.07, TR((0, -0.16, SZ), (R(90), 0, 0)), 48, 6); ir.add_raw(v, f)
    v, f = torus_raw(0.55, 0.05, TR((0, -0.16, SZ), (R(90), 0, 0)), 36, 6); ir.add_raw(v, f)
    ir.add(bm_cyl(0.32, 0.08, 24), TR((0, -0.12, SZ), (R(90), 0, 0)))
    for i in range(8):
        a = 2 * math.pi * i / 8
        v, f = bar_path([(math.cos(a) * 0.55, -0.16, SZ + math.sin(a) * 0.55), (math.cos(a) * 1.05, -0.16, SZ + math.sin(a) * 1.05)], 0.06, 0.05)
        ir.add_raw(v, f)
    io = ir.obj("portcullis")
    io.data.transform(TR((0, 0.0, 0)))
    ih = iron_high(io, 0.014, 89)
    ih.data.materials[0] = iron_mat("gate_iron_src", 89)
    # 봉인 룬 발광: 바깥 고리 사이 여덟 글자 + 가운데 글자 (창백한 청록)
    strokes = []
    for i in range(8):
        a = 2 * math.pi * (i + 0.5) / 8
        c = Vector((math.cos(a) * 0.8, -0.24, SZ + math.sin(a) * 0.8))
        up = Vector((math.cos(a), 0, math.sin(a)))
        t = up.cross(Vector((0, -1, 0))).normalized()
        strokes += glyph_strokes(i, c, t, up, Vector((0, -1, 0)), 0.1, 0.13)
    strokes += glyph_strokes(6, Vector((0, -0.21, SZ)), Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0)), 0.17, 0.22)
    g = stroke_glow(strokes, (0, -1, 0), 0.035, lift=0.0)
    glows.append(glow(g, 'Glow_Spirit'))
    ring = flat_ring(1.12, 1.17, 0.0, 96)
    ring.data.transform(TR((0, -0.24, SZ), (R(90), 0, 0)))
    glows.append(glow(ring, 'Glow_Spirit'))
    low = low_coarse(pre, 0.1, 18500)
    delete(pre)
    vines = ivy_on(low, [((-TX1 - 0.4, -1.5, 0.05), 3, 9.0, 8), ((-TX1 - 0.4, 1.0, 0.05), 5, 5.0, 5), ((TX0 + 0.3, -TY - 0.4, 0.05), 7, 3.0, 4)], 81,
                   leaf=(0.08, 0.13), leaf_p=0.3, hangs=[((-2.4, -GY - 0.7, ZG + 1.1), 2.6, (0, -1, 0)), ((1.9, -GY - 0.7, ZG + 1.1), 1.8, (0, -1, 0)),
                                                           ((-6.6, -TY - 0.45, ZT + 0.1), 2.2, (0, -1, 0))], step=0.05)
    return finish3("gate_great", [body, ih, rh], [low, io, rl], extras=glows + vines, far_extras=glows, size=2048, cage=0.015, cage_reach=0.22,
                   lod1=0.35, lod2=0.12, uv_margin=0.001)


# ═════════════════════════ 목록 ═════════════════════════
BUILDERS = [
    ("crypt", crypt),
    ("cathedral_ruin", cathedral_ruin),
    ("statue_angel", statue_angel),
    ("statue_reaper", statue_reaper),
    ("well", well),
    ("bridge_ruin", bridge_ruin),
    ("watchtower_ruin", watchtower_ruin),
    ("gate_great", gate_great),
]

META = {
    # 납골당: 앞(-Y)에 계단과 철문. 문 안쪽은 막혀 있다 (들어갈 수 없음). 박공 해골 눈에 보랏빛
    "crypt": {"kind": "landmark", "tags": ["landmark", "grave", "ruin"], "collider": "mesh", "footprint": 6.5, "sink": 0.06,
              "tilt": 0, "align": False, "scale": [0.95, 1.05], "cull": 0.004, "shadows": True,
              "light": {"offset": [0, -4.3, 5.8], "color": [0.62, 0.35, 1.0], "intensity": 7, "range": 8}},
    # 무너진 대성당: 이 지역의 대표 랜드마크. 앞(-Y) 정문으로 신랑 안에 들어갈 수 있다 (지붕 없음). 왼쪽 앞에 종탑 (~31m)
    "cathedral_ruin": {"kind": "landmark", "tags": ["landmark", "ruin"], "collider": "mesh", "footprint": 20.0, "sink": 0.1,
                       "tilt": 0, "align": False, "scale": [1.0, 1.0], "cull": 0.002, "shadows": True,
                       "light": {"offset": [0, -15.4, 13.3], "color": [0.62, 0.35, 1.0], "intensity": 14, "range": 16}},
    # 우는 천사 석상: 받침 위, 두건을 쓰고 두 손으로 얼굴을 가렸다. 날개를 접었다
    "statue_angel": {"kind": "prop", "tags": ["grave", "landmark"], "collider": "box", "footprint": 1.2, "sink": 0.05,
                     "tilt": 2, "align": False, "scale": [0.95, 1.1], "cull": 0.008, "shadows": True},
    # 사신 석상: 낫을 든 두건 쓴 석상, 두건 안 눈에 보랏빛
    "statue_reaper": {"kind": "prop", "tags": ["grave", "landmark"], "collider": "box", "footprint": 1.4, "sink": 0.05,
                      "tilt": 2, "align": False, "scale": [0.95, 1.1], "cull": 0.008, "shadows": True,
                      "light": {"offset": [0, -0.3, 2.81], "color": [0.62, 0.35, 1.0], "intensity": 2.5, "range": 3}},
    # 돌 우물: 무너진 나무 지붕 틀, 밧줄, 두레박
    "well": {"kind": "prop", "tags": ["ruin", "path"], "collider": "capsule", "footprint": 1.6, "sink": 0.05,
             "tilt": 1, "align": False, "scale": [0.95, 1.05], "cull": 0.01, "shadows": True},
    # 아치 다리: 길이 방향 = X (14m), 폭 4m. 원점 z=0 = 양쪽 둑 높이, 개울 바닥은 z≈-2 (아치 아래 높이 약 3m).
    # 다리 위 길은 양 끝 z≈0.1 에서 가운데 z≈1.9 로 솟는다. 앞(-Y) 쪽 난간 가운데가 무너졌다
    "bridge_ruin": {"kind": "landmark", "tags": ["landmark", "ruin", "path"], "collider": "mesh", "footprint": 7.5, "sink": 0.0,
                    "tilt": 0, "align": False, "scale": [1.0, 1.0], "cull": 0.004, "shadows": True},
    # 둥근 돌 망루 (~12m): 위가 무너졌다. 앞(-Y)에 출입구, 안에 썩은 들보
    "watchtower_ruin": {"kind": "landmark", "tags": ["landmark", "ruin"], "collider": "mesh", "footprint": 4.5, "sink": 0.08,
                        "tilt": 0, "align": False, "scale": [0.95, 1.1], "cull": 0.004, "shadows": True},
    # 2장으로 가는 거대한 관문: 쇠창살이 내려 닫혔고 창백한 청록 룬으로 봉인되어 있다 (지나갈 수 없음)
    "gate_great": {"kind": "landmark", "tags": ["landmark", "ruin", "light"], "collider": "mesh", "footprint": 9.5, "sink": 0.08,
                   "tilt": 0, "align": False, "scale": [1.0, 1.0], "cull": 0.003, "shadows": True,
                   "light": {"offset": [0, -1.0, 3.9], "color": [0.45, 0.85, 1.0], "intensity": 14, "range": 14}},
}

PREVIEWS = [
    ("all", [n for n, _ in BUILDERS], False),
    ("big", ["cathedral_ruin", "gate_great", "crypt", "watchtower_ruin", "bridge_ruin"], False),
    ("small", ["statue_angel", "statue_reaper", "well"], False),
] + [(n, [n], True) for n, _ in BUILDERS]
