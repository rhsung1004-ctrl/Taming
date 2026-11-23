# 묘지 석물 묶음 (graves)
#   둥근 묘비, 부러진 묘비, 고딕 뾰족 묘비, 고리 십자가, 오벨리스크, 석관 무덤, 묻힌 묘비, 나무 관, 뼈 무더기, 양초, 해골
#
# 만드는 방식
#   - 큰 덩어리는 bmesh 로 직접 만든 볼록한 조각(윤곽을 늘인 기둥, 상자)을 쓰고, 모서리는 평면으로 쳐내거나(bm_chip, bm_flake)
#     kit.chip 으로 정 자국을 낸다. 크게 깨진 곳은 울퉁불퉁한 단면 커터(rough_cutter)나 각진 덩어리(chunk)로 파낸다.
#     부러져 떨어진 조각은 같은 단면 커터의 반대쪽(INTERSECT)이라 깨진 면이 서로 맞는다.
#   - 새김(글줄, 십자가, 원형 문양)은 획 모양 상자 커터로 판다. 글자는 이 게임용으로 지어낸 비문 글자다.
#   - 뼈·해골·촛농처럼 둥근 것은 작은 구를 여러 개 겹쳐(blobs) 복셀 리메시로 한 덩어리로 녹인 뒤 구멍을 판다.
#   - 그 다음 kit.surface 로 겹겹이 떨어진 턱·금·구멍을 새기고 kit.paint 로 칠해 굽는다.
#     paint 뒤에 덧칠(moss_low, dirt_low, tint_near)을 얹어 아래쪽 이끼·흙물을 더한다.
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
IVY_COL = (0.09, 0.2, 0.15)           # 덩굴 잎: 어둡고 차가운 초록
SOUL = (0.62, 0.35, 1.0)              # 영혼 빛 색 (점광원)
WAX = ((0.16, 0.13, 0.12), (0.6, 0.55, 0.45), (0.86, 0.82, 0.72))
BONE_DARK = ((0.13, 0.1, 0.08), (0.58, 0.5, 0.37), (0.88, 0.82, 0.68))


# ───────────────────────── bmesh 도우미 ─────────────────────────
def TR(loc=(0, 0, 0), rot=(0, 0, 0), s=None):
    """위치 + 회전(XYZ 오일러, 라디안) [+ 크기] 행렬"""
    M = Matrix.Translation(Vector(loc)) @ Euler(rot, 'XYZ').to_matrix().to_4x4()
    if s is not None:
        if not isinstance(s, (tuple, list)):
            s = (s, s, s)
        M = M @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))
    return M

def obj_bm(bm, name="part", M=None):
    """bmesh → 장면 객체 (원점 = 월드 0)"""
    if M is not None:
        bm.transform(M)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    kit.sc.collection.objects.link(o)
    return o

def bm_box(sx, sy, sz, M=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
    if M is not None:
        bm.transform(M)
    return bm

def bm_merge(dst, src):
    """src bmesh 를 dst 에 더하고 src 를 버린다"""
    me = bpy.data.meshes.new("_m")
    src.to_mesh(me); src.free()
    dst.from_mesh(me)
    bpy.data.meshes.remove(me)
    return dst

def bm_poly(poly, a0, a1, axis='y'):
    """2D 다각형을 늘인 기둥. axis='y': poly 는 XZ, y 방향으로 a0~a1 / axis='z': poly 는 XY, z 방향"""
    bm = bmesh.new()
    mk = (lambda p, w: (p[0], w, p[1])) if axis == 'y' else (lambda p, w: (p[0], p[1], w))
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

def bm_frustum(w0, d0, w1, d1, z0, z1):
    """아래 (w0×d0), 위 (w1×d1) 인 사각뿔대"""
    bm = bmesh.new()
    vs = []
    for (w, d, z) in ((w0, d0, z0), (w1, d1, z1)):
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vs.append(bm.verts.new((sx * w / 2, sy * d / 2, z)))
    bm.faces.new(vs[0:4][::-1])
    bm.faces.new(vs[4:8])
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((vs[i], vs[j], vs[4 + j], vs[4 + i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm

def bm_cut(bm, co, no):
    """평면 바깥쪽(no 쪽)을 잘라 버리고 구멍을 막는다 (볼록한 조각용)"""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    r = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector(co), plane_no=Vector(no).normalized(), clear_outer=True)
    es = [g for g in r['geom_cut'] if isinstance(g, bmesh.types.BMEdge)]
    if es:
        bmesh.ops.holes_fill(bm, edges=es, sides=0)
    return bm

def bm_center(bm):
    return sum((v.co for v in bm.verts), Vector()) / max(1, len(bm.verts))

def _corners(bm, ang=28):
    out = []
    for v in bm.verts:
        k = sum(1 for e in v.link_edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > R(ang))
        if k >= 3:
            out.append(v.co.copy())
    return out

def bm_chip(bm, rng, n, depth=(0.02, 0.06), zmin=-1e9, zmax=1e9):
    """꼭짓점을 정으로 친 것처럼 평평한 면으로 쳐낸다 (기울기를 제각각)"""
    cs = [c for c in _corners(bm) if zmin <= c.z <= zmax]
    if not cs or n <= 0:
        return bm
    cen = bm_center(bm)
    for _ in range(n):
        p = rng.choice(cs)
        d = p - cen
        nrm = Vector((math.copysign(rng.uniform(0.25, 1.4), d.x), math.copysign(rng.uniform(0.25, 1.4), d.y),
                      math.copysign(rng.uniform(0.25, 1.4), d.z))).normalized()
        bm_cut(bm, p - nrm * rng.uniform(*depth), nrm)
    return bm

def bm_flake(bm, rng, n, depth=(0.01, 0.03), axes=((0, -1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0), (-1, 0, 0))):
    """면이 모서리 쪽으로 얇게 떨어져 나간 자국: 면과 거의 나란한 비스듬한 평면으로 모서리 한쪽을 깎는다"""
    if n <= 0 or not bm.verts:
        return bm
    cen = bm_center(bm)
    for _ in range(n):
        f = Vector(rng.choice(axes))
        others = [Vector(a) for a in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)) if abs(Vector(a).dot(f)) < 0.5]
        t = rng.choice(others)
        e = f.cross(t)
        hf = max((v.co - cen).dot(f) for v in bm.verts)
        ht = max((v.co - cen).dot(t) for v in bm.verts)
        he = max(0.05, max((v.co - cen).dot(e) for v in bm.verts))
        a = R(rng.uniform(12, 30))
        nrm = (f * math.cos(a) + t * math.sin(a) + e * rng.uniform(-0.35, 0.35)).normalized()
        edge = cen + f * hf + t * ht + e * rng.uniform(-0.3, 0.3) * he
        bm_cut(bm, edge - nrm * rng.uniform(*depth), nrm)
    return bm

def bm_bevel(bm, w=0.01, ang=28):
    """날카로운 모서리를 살짝 깎는다 (닳은 모서리가 빛을 받게)"""
    es = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > R(ang) and e.calc_length() > w * 2.5]
    if es and w > 0:
        try:
            bmesh.ops.bevel(bm, geom=es, offset=w, offset_type='OFFSET', segments=1, profile=0.5, affect='EDGES', clamp_overlap=True)
        except Exception as ex:
            print("bevel skip", ex)
    return bm

def stone_blk(bm, rng, chips=(1, 3), depth=(0.02, 0.06), flakes=(1, 2), bevel=0.008, zmin=-1e9):
    bm_chip(bm, rng, rng.randint(*chips), depth, zmin=zmin)
    bm_flake(bm, rng, rng.randint(*flakes))
    bm_bevel(bm, bevel)
    return bm

def blobs(items, sub=2, name="blobs"):
    """겹친 타원구들 (리메시하면 한 덩어리로 녹는다). items: [(중심, (rx,ry,rz), 회전), ...]"""
    bm = bmesh.new()
    for it in items:
        c, r = it[0], it[1]
        rot = it[2] if len(it) > 2 else (0, 0, 0)
        g = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
        if not isinstance(r, (tuple, list)):
            r = (r, r, r)
        M = Matrix.Translation(Vector(c)) @ Euler(rot, 'XYZ').to_matrix().to_4x4() @ Matrix.Diagonal((r[0], r[1], r[2], 1.0))
        bmesh.ops.transform(bm, matrix=M, verts=g['verts'])
    return obj_bm(bm, name)

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
        for k in range(n + (1 if i == len(pts) - 2 else 0)):
            t = k / n
            r = ra + (rb - ra) * t
            out.append((a.lerp(b, t), (r * squash[0], r * squash[1], r), tuple(q)))
    return out

def lathe(profile, seg=16, M=None, cap=True):
    """(반지름, 높이) 윤곽을 Z 축으로 돌린 회전체"""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r < 1e-5:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z)) for i in range(seg)])
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for i in range(seg):
                bm.faces.new((a[0], b[i], b[(i + 1) % seg]))
        elif len(b) == 1:
            for i in range(seg):
                bm.faces.new((a[i], b[0], a[(i + 1) % seg]))
        else:
            for i in range(seg):
                j = (i + 1) % seg
                bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap:
        if len(rings[0]) > 1:
            bm.faces.new(rings[0][::-1])
        if len(rings[-1]) > 1:
            bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if M is not None:
        bm.transform(M)
    return bm

def annulus_y(cx, cz, r0, r1, y0, y1, n=64, a0=0.0, a1=2 * math.pi):
    """Y 축 방향 고리 (앞면에 원을 새기는 커터). a0~a1 로 일부만 (부채꼴 고리)"""
    full = abs(a1 - a0 - 2 * math.pi) < 1e-6
    m = n if full else n + 1
    bm = bmesh.new()
    def ring(r, y):
        return [bm.verts.new((cx + r * math.cos(a0 + (a1 - a0) * i / n), y, cz + r * math.sin(a0 + (a1 - a0) * i / n))) for i in range(m)]
    i0, i1, o0, o1 = ring(r0, y0), ring(r0, y1), ring(r1, y0), ring(r1, y1)
    for i in range(n):
        j = (i + 1) % m
        bm.faces.new((i0[i], i0[j], o0[j], o0[i]))
        bm.faces.new((i1[i], o1[i], o1[j], i1[j]))
        bm.faces.new((o0[i], o0[j], o1[j], o1[i]))
        bm.faces.new((i0[i], i1[i], i1[j], i0[j]))
    if not full:
        bm.faces.new((i0[0], o0[0], o1[0], i1[0]))
        bm.faces.new((i0[n], i1[n], o1[n], o0[n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm

def drop_below(o, z=-0.03):
    """땅속에 묻혀 보이지 않는 면을 지운다"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    kill = [f for f in bm.faces if all(v.co.z < z for v in f.verts)]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o

def low_of(high, tris, z=-0.03):
    """저폴리: 줄이고 땅속 면을 지운다 (객체 변환을 먼저 적용)"""
    low = decimated(high, tris)
    if low.matrix_world != Matrix.Identity(4):
        xf_all(low)
    return drop_below(low, z)

def bake_obj(o):
    """객체 변환을 메쉬에 적용한다 (원점은 월드 0)"""
    xf_all(o)
    return o

def keep_side(o, co, no):
    """객체를 평면으로 잘라 no 반대쪽만 남긴다 (리메시 뒤 열린 메쉬 정리용)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    bm_cut(bm, co, no)
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o


# ───────────────────────── 커터 ─────────────────────────
def chunk(center, size, rng, planes=9, depth=(0.08, 0.3), sub=2):
    """평면으로 깎은 각진 덩어리 (떨어진 조각, 또는 파낸 자국 커터)"""
    s = sphere(1.0, center, size, sub, rot=(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)))
    slice_rock(s, rng, planes, depth)
    return s

def spall(p, n, size, depth, rng):
    """표면이 얇게 떨어져 나간 자국 커터: p 표면 점, n 바깥 방향, size (가로, 세로), depth 파낼 깊이"""
    s = sphere(1.0, (0, 0, 0), (size[0], size[1], depth * 2.0), 2)
    slice_rock(s, rng, 7, (0.1, 0.32))
    n = Vector(n).normalized()
    q = n.to_track_quat('Z', 'Y').to_matrix().to_4x4() @ Matrix.Rotation(rng.uniform(0, 6.28), 4, 'Z')
    s.data.transform(Matrix.Translation(Vector(p) + n * depth) @ q)
    s.data.update()
    return s

def rough_cutter(co, no, w=2.0, h=2.0, amp=0.03, freq=5.0, res=26, depth=3.0, seed=0, steps=3.0):
    """울퉁불퉁한(계단진) 단면 커터: co 를 지나는 면에서 no 쪽 depth 만큼. DIFFERENCE 면 no 쪽을 파내고,
    INTERSECT 면 no 쪽만 남는다 (부러져 떨어진 조각)."""
    no = Vector(no).normalized()
    t1 = no.orthogonal().normalized()
    t2 = no.cross(t1)
    co = Vector(co)
    off = Vector((seed * 17.31, seed * 5.13, seed * 9.71))

    def hgt(u, v):
        p = Vector((u * freq, v * freq, 0.0)) + off
        n = mnoise.noise(p) + 0.5 * mnoise.noise(p * 2.13) + 0.25 * mnoise.noise(p * 4.37)
        q = math.floor(n * steps) / steps
        return (n * 0.55 + q * 0.45) * amp

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

def intersect(a, *others):
    flat = []
    for c in others:
        flat += list(c) if isinstance(c, (list, tuple)) else [c]
    return kit._bool(a, flat, 'INTERSECT')

def stroke_box(pa, pb, nrm, width, depth):
    """획 모양 홈 커터 (면에 수직으로 파고든다)"""
    pa, pb = Vector(pa), Vector(pb)
    d = pb - pa
    x = d.normalized() if d.length > 1e-6 else Vector((1, 0, 0))
    z = Vector(nrm).normalized()
    y = z.cross(x).normalized()
    M = Matrix((x, y, z)).transposed().to_4x4()
    M.translation = (pa + pb) / 2
    return obj_bm(bm_box(d.length + width * 0.9, width, depth * 2), "stroke", M)

# 비문 글자: 이 게임용으로 지어낸 각진 글자 (획 목록, 칸 -0.5~0.5)
GLYPHS = [
    [((-.3, -.5), (-.3, .5)), ((-.3, .5), (.3, .5)), ((-.3, 0), (.15, 0))],
    [((-.3, -.5), (0, .5)), ((0, .5), (.3, -.5)), ((-.15, -.1), (.15, -.1))],
    [((-.3, .5), (-.3, -.5)), ((-.3, -.5), (.3, -.5))],
    [((-.3, -.5), (-.3, .5)), ((.3, -.5), (.3, .5)), ((-.3, 0), (.3, 0))],
    [((-.3, .5), (.3, .5)), ((0, .5), (0, -.5))],
    [((-.3, -.5), (-.3, .5)), ((-.3, .5), (.3, -.5)), ((.3, -.5), (.3, .5))],
    [((-.3, .5), (.3, .5)), ((.3, .5), (-.3, -.5)), ((-.3, -.5), (.3, -.5))],
    [((0, -.5), (0, .5))],
    [((-.3, .5), (-.3, -.5)), ((-.3, .5), (.25, .25)), ((.25, .25), (-.3, 0)), ((-.3, 0), (.3, -.5))],
    [((-.3, -.5), (.3, .5)), ((-.3, .5), (.3, -.5))],
    [((-.3, .5), (-.3, -.5)), ((-.3, -.5), (.3, -.5)), ((.3, -.5), (.3, .5))],
    [((-.3, -.5), (0, .5)), ((0, .5), (.3, -.5))],
]

def text_strokes(rng, cx, zc, width, h, y, words=(2, 4), jitter=0.0):
    """한 줄 글자 획 (y 평면 위, XZ). 가운데 정렬"""
    lw = h * 0.62
    gap = h * 0.28
    wgap = h * 0.7
    letters = []
    x = 0.0
    first = True
    while True:
        n = rng.randint(2, 6)
        need = n * lw + (n - 1) * gap + (0 if first else wgap)
        if x + need > width and not first:
            break
        if not first:
            x += wgap
        for k in range(n):
            if x + lw > width:
                break
            letters.append((x + lw / 2, rng.randrange(len(GLYPHS))))
            x += lw + gap
        x -= gap
        first = False
    total = x
    out = []
    for lx, gi in letters:
        px = cx - total / 2 + lx
        pz = zc + rng.uniform(-jitter, jitter)
        for (a, b) in GLYPHS[gi]:
            out.append((Vector((px + a[0] * lw, y, pz + a[1] * h)), Vector((px + b[0] * lw, y, pz + b[1] * h))))
    return out

def engrave(o, strokes, nrm, width, depth):
    """획들을 면에 판다"""
    cs = [stroke_box(a, b, nrm, width, depth) for a, b in strokes]
    if cs:
        cut(o, cs)
    return o

def arc_strokes(cx, cz, r, a0, a1, y, n=10):
    pts = [Vector((cx + r * math.cos(a0 + (a1 - a0) * i / n), y, cz + r * math.sin(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    return list(zip(pts, pts[1:]))

def crack_strokes(rng, p0, direction, length, segs=6, wander=0.35, y=None):
    """구불구불한 금 (XZ 평면 위 획 목록)"""
    out = []
    p = Vector(p0)
    d = Vector(direction).normalized()
    for i in range(segs):
        ang = rng.uniform(-wander, wander)
        c, s = math.cos(ang), math.sin(ang)
        d = Vector((d.x * c - d.z * s, 0, d.x * s + d.z * c)).normalized()
        q = p + d * (length / segs) * rng.uniform(0.7, 1.3)
        if y is not None:
            q.y = y
        out.append((p.copy(), q.copy()))
        p = q
    return out


# ───────────────────────── 덧칠 (kit.paint 뒤에 얹는다) ─────────────────────────
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

def stone_mat(name, pal='stone', moss=0.7, low_moss=0.8, mz=0.35, **kw):
    m = paint(name, pal, moss=moss, **kw)
    if low_moss > 0:
        moss_low(m, 0.0, mz, low_moss)
    return m


# ───────────────────────── 덩굴·풀·거미줄 (Foliage) ─────────────────────────
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

def foliage_obj(name, verts, faces, uvs, cols):
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
    """덩굴 줄기(표면에 붙은 납작한 띠)와 잎 카드를 모은다 (삼각형 수를 아끼는 가벼운 덩굴)"""
    def __init__(self, rng, col=IVY_COL, dead=0.18, leaf=(0.035, 0.06), leaf_p=0.5, stem_w=0.011, bare=0.25, wine=0.05):
        self.rng = rng; self.col = col; self.dead = dead; self.leaf = leaf; self.leaf_p = leaf_p
        self.stem_w = stem_w; self.bare = bare; self.wine = wine
        self.sv, self.sf, self.suv, self.scol = [], [], [], []
        self.lv, self.lf, self.luv, self.lcol = [], [], [], []

    def strand(self, pts, nrms, width_k=1.0, leaf_k=1.0):
        rng = self.rng
        L = len(pts)
        if L < 2:
            return
        sides = []
        for i in range(L):
            d = pts[min(i + 1, L - 1)] - pts[max(i - 1, 0)]
            if d.length < 1e-6:
                d = Vector((0, 0, 1))
            sd = d.cross(nrms[i])
            if sd.length < 1e-6:
                sd = d.orthogonal()
            sides.append(sd.normalized())
        w0 = self.stem_w * width_k
        for i in range(L - 1):
            k = len(self.sv)
            for ii, u in ((i, 0), (i, 1), (i + 1, 1), (i + 1, 0)):
                w = w0 * (1 - 0.7 * ii / (L - 1))
                self.sv.append(pts[ii] + nrms[ii] * 0.004 + sides[ii] * (w * (u - 0.5)))
                self.suv.append(atlas_uv('stem', u, 0.1 + 0.8 * (ii % 2)))
                self.scol.append((0.07, 0.055, 0.05, 0.05 + 0.15 * ii / (L - 1)))
            self.sf.append((k, k + 1, k + 2, k + 3))
        acc = [0.0]
        for i in range(1, L):
            acc.append(acc[-1] + (pts[i] - pts[i - 1]).length)
        tot = max(1e-6, acc[-1])
        for i in range(L):
            t = acc[i] / tot
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
        tip = (r_t.normalized() if r_t.length > 1e-4 else nrm.orthogonal()) + (g_t.normalized() * 0.8 if g_t.length > 1e-3 else Vector())
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
        cell = 'leaf_dead' if roll < self.dead * 0.5 else ('ivy_a' if rng.random() < 0.6 else 'ivy_b')
        self.luv += [atlas_uv(cell, 0, 0), atlas_uv(cell, 1, 0), atlas_uv(cell, 1, 1), atlas_uv(cell, 0, 1)]
        if roll < self.dead:
            base_c = (0.34, 0.28, 0.16)
        elif roll < self.dead + self.wine:
            base_c = (0.2, 0.06, 0.13)            # 검붉은 잎 몇 장
        else:
            base_c = self.col
        j = rng.uniform(0.7, 1.25)
        c = (min(1, base_c[0] * j), min(1, base_c[1] * j), min(1, (base_c[2] + rng.uniform(-0.02, 0.03)) * j))
        dk = (c[0] * 0.65, c[1] * 0.65, c[2] * 0.65)
        self.lcol += [(*dk, 0.25), (*dk, 0.25), (*c, 0.55), (*c, 0.55)]

    def objects(self):
        out = [foliage_obj("ivy_stem", self.sv, self.sf, self.suv, self.scol),
               foliage_obj("ivy_leaf", self.lv, self.lf, self.luv, self.lcol)]
        return [o for o in out if o is not None]

def ivy_grow(vine, target, start, seed=0, length=1.5, step=0.03, max_roots=10, branch=0.1, gravity=0.5, adhesion=0.7,
             float_len=0.2, width_k=1.0, zmax=1e9):
    """IvyGen 으로 target 표면을 따라 자라게 한 뒤 vine 에 줄기·잎을 더한다"""
    ig = _ivygen()
    ig.rand_seed(seed)
    act(target)
    bvh = ig.bvhtree_from_object(target)
    IVY = ig.Ivy(primaryWeight=0.5, randomWeight=0.25, gravityWeight=gravity, adhesionWeight=adhesion,
                 branchingProbability=branch, leafProbability=0.3, ivySize=step, ivyLeafSize=0.05,
                 ivyBranchSize=0.001, maxFloatLength=float_len, maxAdhesionDistance=0.5)
    IVY.seed(Vector(start))
    guard = 0
    while any(r.alive for r in IVY.ivyRoots) and IVY.maxLength < length and guard < 2500:
        IVY.grow(target, bvh)
        while len(IVY.ivyRoots) > max_roots:
            IVY.ivyRoots.pop()
        for r in IVY.ivyRoots:
            if r.ivyNodes and r.ivyNodes[-1].pos.z > zmax:
                r.alive = False
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

def hang_strand(vine, top, length, rng, face=(0, -1, 0), sway=0.05):
    """위에서 아래로 늘어진 덩굴 한 가닥"""
    n = max(3, int(length / 0.05))
    face = Vector(face).normalized()
    side = face.cross(Vector((0, 0, 1))).normalized()
    ph = rng.uniform(0, 6.28)
    pts, nrms = [], []
    for i in range(n + 1):
        t = i / n
        pts.append(Vector(top) + Vector((0, 0, -length * t)) + side * (math.sin(ph + t * 5.0) * sway * t) + face * (0.02 * t * t))
        nrms.append(face)
    vine.strand(pts, nrms, 0.6, 1.2)

def web_card(p, u_dir, v_dir, size, flip=False):
    """거미줄 구석 카드 (web_corner 칸). p: 구석 모서리 점, u_dir·v_dir: 두 변 방향"""
    u = Vector(u_dir).normalized() * size
    v = Vector(v_dir).normalized() * size
    p = Vector(p)
    o = raw_mesh("web", [p, p + u, p + u + v, p + v], [(0, 1, 2, 3)])
    uvl = o.data.uv_layers.new(name="UVMap")
    corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for lp in o.data.loops:
        u_, v_ = corners[lp.vertex_index]
        uvl.data[lp.index].uv = atlas_uv('web_corner', 1 - u_ if flip else u_, v_)
    vcolor(o, lambda q, n, i: (0.75, 0.77, 0.88, 0.08))
    set_mat(o, foliage_mat())
    return o

class Grass:
    """마른 풀 포기 (휘어진 잎 띠, 정점 알파 = 흔들림)"""
    def __init__(self, rng):
        self.rng = rng
        self.v, self.f, self.uv, self.c = [], [], [], []

    def tuft(self, p, n=8, h=(0.12, 0.3), spread=0.05, dead=0.6, w=(0.008, 0.016)):
        rng = self.rng
        for _ in range(n):
            ang = rng.uniform(0, 6.28); rr = rng.uniform(0, spread)
            x0, y0 = p[0] + math.cos(ang) * rr, p[1] + math.sin(ang) * rr
            hh = rng.uniform(*h); ww = rng.uniform(*w)
            lean = Vector((math.cos(ang), math.sin(ang), 0)) * rng.uniform(0.1, 0.45) + Vector((rng.uniform(-.15, .15), rng.uniform(-.15, .15), 0))
            face = rng.uniform(0, 6.28); fx, fy = math.cos(face), math.sin(face)
            d = rng.random() < dead
            segs = 3
            base = len(self.v)
            for k in range(segs + 1):
                t = k / segs
                cx = x0 + lean.x * t * t * hh; cy = y0 + lean.y * t * t * hh; cz = p[2] + hh * t * (1 - 0.25 * t * t)
                wk = ww * (1 - t) ** 0.8 + 0.0008
                self.v += [(cx - fy * wk, cy + fx * wk, cz), (cx + fy * wk, cy - fx * wk, cz)]
                if d:
                    c = (0.2 + 0.2 * t, 0.17 + 0.15 * t, 0.1 + 0.06 * t)
                else:
                    c = (0.05 + 0.07 * t, 0.09 + 0.12 * t, 0.08 + 0.08 * t)
                self.c += [(c[0], c[1], c[2], t), (c[0], c[1], c[2], t)]
                self.uv += [atlas_uv('solid', 0.5, 0.5)] * 2
            for k in range(segs):
                i = base + k * 2
                self.f.append((i, i + 1, i + 3, i + 2))

    def objects(self):
        o = foliage_obj("grass", self.v, self.f, self.uv, self.c)
        return [o] if o else []

def glow_obj(verts, faces, name='Glow_Soul'):
    o = mesh_from("glow", verts, faces)
    return glow(o, name)

def flame(base, h=0.05, r=0.011, lean=(0.0, 0.0), seg=8):
    """물방울 모양 영혼 불꽃 (Glow_Soul)"""
    prof = [(0.0, -0.002), (r * 0.7, 0.002), (r, 0.01), (r * 0.85, h * 0.42), (r * 0.45, h * 0.72), (0.0, h)]
    bm = lathe(prof, seg)
    for v in bm.verts:
        t = max(0.0, v.co.z / h)
        v.co.x += lean[0] * t * t
        v.co.y += lean[1] * t * t
    o = obj_bm(bm, "flame", Matrix.Translation(Vector(base)))
    return glow(o, 'Glow_Soul')


# ───────────────────────── 해골·뼈 ─────────────────────────
def skull_high(rng, jaw_open=6.0, voxel=0.0016, seed=0, moss=0.15, dirt=0.5, pal=None, jaw=True, hole=False):
    """해골 (앞 = -Y, 아래턱 바닥 ≈ z 0, 길이 약 0.2m). 구를 겹쳐 녹인 뒤 눈구멍·코구멍·관자놀이를 판다."""
    it = []
    it.append(((0, 0.016, 0.118), (0.064, 0.088, 0.072)))          # 머리뼈 둥근 통
    it.append(((0, -0.045, 0.118), (0.056, 0.04, 0.054)))          # 이마 (곧게 선 앞이마)
    it.append(((0, 0.06, 0.09), (0.054, 0.044, 0.05)))             # 뒤통수
    it.append(((0, -0.066, 0.098), (0.058, 0.02, 0.017)))          # 눈썹뼈
    it.append(((0, -0.058, 0.078), (0.054, 0.026, 0.03)))          # 눈 둘레 판
    it.append(((0, -0.05, 0.06), (0.042, 0.034, 0.03)))            # 위턱
    for sx in (-1, 1):
        it.append(((sx * 0.047, -0.05, 0.063), (0.018, 0.024, 0.016), (0, 0, sx * R(-18))))   # 광대뼈
        it.append(((sx * 0.054, -0.022, 0.062), (0.012, 0.03, 0.012)))                       # 광대활 (머리뼈에 붙게)
        it.append(((sx * 0.055, 0.004, 0.07), (0.012, 0.03, 0.022)))                         # 관자 판
        it.append(((sx * 0.05, 0.036, 0.05), (0.011, 0.013, 0.018)))                         # 귀 뒤 꼭지
    it += tube_items([(-0.031, -0.046, 0.04), (-0.022, -0.066, 0.04), (0, -0.074, 0.04), (0.022, -0.066, 0.04), (0.031, -0.046, 0.04)],
                     [0.009] * 5, 0.5)                                                       # 잇몸 둑
    sk = blobs(it, 3, "skull")
    parts = [sk]
    # 윗니: 촘촘한 네모 이 (사이 홈은 나중에 판다)
    bm = bmesh.new()
    for i in range(9):
        a = R(-64 + 128 * i / 8)
        x = 0.034 * math.sin(a); y = -0.041 - 0.034 * math.cos(a)
        bm_merge(bm, bm_box(0.0074, 0.0078, 0.016, TR((x, y, 0.027), (0, 0, a))))
    parts.append(obj_bm(bm, "teeth"))
    if jaw:
        jt = []
        arc = []
        for i in range(11):
            a = R(-90 + 180 * i / 10)
            arc.append((0.041 * math.sin(a), -0.033 - 0.036 * math.cos(a), -0.006))
        jt += tube_items(arc, [0.011] * 11, 0.45, squash=(0.6, 1.25))                     # 아래턱 몸통 (높고 얇게)
        jt.append(((0, -0.066, -0.012), (0.017, 0.011, 0.012)))                               # 턱끝
        for sx in (-1, 1):
            for k in range(5):
                t = k / 4
                jt.append(((sx * (0.043 + 0.008 * t), -0.022 + 0.044 * t, -0.004 + 0.052 * t), (0.006, 0.017 - 0.006 * t, 0.014)))   # 턱뼈 가지 (넓은 판)
        bm = bmesh.new()
        for i in range(9):
            a = R(-60 + 120 * i / 8)
            x = 0.032 * math.sin(a); y = -0.039 - 0.03 * math.cos(a)
            bm_merge(bm, bm_box(0.007, 0.0074, 0.016, TR((x, y, 0.011), (0, 0, a))))
        mj = blobs(jt, 2, "jaw")
        lt = obj_bm(bm, "lteeth")
        hinge = Vector((0, 0.024, 0.054))
        Mj = Matrix.Translation(hinge) @ Matrix.Rotation(R(jaw_open), 4, 'X') @ Matrix.Translation(-hinge)
        for o in (mj, lt):
            o.data.transform(Mj)
        parts += [mj, lt]
    s = join(parts)
    origin0(s)
    remesh(s, voxel)
    cs = []
    for sx in (-1, 1):
        cs.append(sphere(1.0, (sx * 0.026, -0.09, 0.079), (0.0195, 0.042, 0.018), 3, rot=(0, sx * R(12), 0)))   # 눈구멍 (깊게)
    nose = [(0, 0.071), (0.0105, 0.053), (0.009, 0.043), (0.003, 0.04), (0, 0.043), (-0.003, 0.04), (-0.009, 0.043), (-0.0105, 0.053)]
    cs.append(obj_bm(bm_poly(nose, -0.12, -0.05, 'y'), "nose"))
    # 이 사이 홈
    for i in range(8):
        a = R(-64 + 128 * (i + 0.5) / 8)
        x = 0.034 * math.sin(a); y = -0.041 - 0.034 * math.cos(a)
        cs.append(obj_bm(bm_box(0.0024, 0.03, 0.013, TR((x, y, 0.026), (0, 0, a))), "tg"))
    if hole:   # 깨져 뚫린 머리뼈
        cs.append(chunk((0.04, 0.03, 0.17), (0.03, 0.026, 0.022), rng, 8, (0.1, 0.3)))
        cs.append(chunk((0.052, 0.045, 0.152), (0.02, 0.018, 0.02), rng, 7, (0.1, 0.3)))
    # 떨어져 나간 자국 몇 군데
    cs.append(spall((-0.05, 0.03, 0.15), (-0.6, 0.2, 0.8), (0.02, 0.016), 0.0025, rng))
    cs.append(spall((0.0, 0.09, 0.13), (0, 1, 0.3), (0.025, 0.018), 0.0025, rng))
    cut(s, cs)
    remesh(s, voxel)
    layers = [{'t': 'lumps', 'scale': 14, 'amp': 0.0012},
              {'t': 'fissure', 'scale': 8, 'width': 0.014, 'depth': 0.0028, 'cover': 0.6},           # 봉합선·금
              {'t': 'fissure', 'scale': 20, 'width': 0.01, 'depth': 0.0012, 'cover': 0.5},
              {'t': 'terrace', 'scale': 18, 'steps': 3, 'amp': 0.0012, 'cover': 0.55},               # 얇게 벗겨진 뼈
              {'t': 'pits', 'scale': 120, 'depth': 0.0008, 'cover': 0.65},
              {'t': 'grain', 'scale': 300, 'amp': 0.00015}]
    surface(s, layers, seed)
    m = paint("bone_%d" % seed, pal or BONE_DARK, moss=moss, moss_color=MOSS_DEAD, dirt=0.0, streaks=0.35, ao=0.045, edge=0.6,
              cavity=1.0, grain_bump=0.6, cracks=0.35, hue_var=0.5)
    blotch(m, (0.36, 0.27, 0.13), 11, 0.75, 0.42, 0.6)        # 누렇게 밴 얼룩
    dirt_low(m, -0.005, 0.07, dirt)
    set_mat(s, m)
    return s

def long_bone(L, r, rng, bump=True):
    """긴 뼈 (X 축). 한쪽 끝은 두 갈래 관절 혹, 다른 끝은 둥근 머리"""
    it = []
    n = 6
    pts = [(-L / 2 + L * i / n, 0, 0) for i in range(n + 1)]
    rad = [r * (1.05 - 0.22 * math.sin(math.pi * i / n)) for i in range(n + 1)]
    it += tube_items(pts, rad, 0.6)
    e = L / 2
    for sy in (-1, 1):
        it.append(((e - r * 0.5, sy * r * 0.7, -r * 0.1), (r * 1.3, r * 1.0, r * 1.15)))      # 두 갈래 관절
    it.append(((-e - r * 0.15, 0, r * 0.75), (r * 1.35, r * 1.3, r * 1.3)))                 # 둥근 머리
    it.append(((-e + r * 0.9, 0, -r * 0.55), (r * 1.1, r * 0.9, r * 0.9)))                 # 머리 아래 혹
    return it

def rib(rng, R_=0.13, sweep=110, r=0.008):
    pts = []
    for i in range(9):
        a = R(sweep) * i / 8
        pts.append((R_ * math.cos(a), R_ * math.sin(a) * 0.8, 0.02 * math.sin(a * 2)))
    return tube_items(pts, [r] * 9, 0.6, squash=(1.0, 0.55))

BONE_LAYERS = [{'t': 'lumps', 'scale': 9, 'amp': 0.0015},
               {'t': 'fissure', 'scale': 6, 'width': 0.012, 'depth': 0.002, 'cover': 0.45},
               {'t': 'pits', 'scale': 110, 'depth': 0.0007, 'cover': 0.6},
               {'t': 'grain', 'scale': 260, 'amp': 0.0002}]


# ───────────────────────── 묘비 윤곽 ─────────────────────────
def round_top(w, z0, h_side, steps=22, lop=0.0):
    """위가 둥근 윤곽 (XZ). 바닥 z0, 옆선 높이 h_side, 반원 반지름 w/2. lop: 한쪽 어깨가 처진 정도"""
    r = w / 2
    pts = [(-r, z0), (r, z0)]
    for i in range(steps + 1):
        a = math.pi * i / steps
        pts.append((r * math.cos(a), z0 + h_side + r * math.sin(a) * (1 - lop * (1 - i / steps))))
    return pts


# ───────────────────────── 소품 ─────────────────────────
def grave_slab_a():
    """위가 둥근 묘비: 액자처럼 판 면, 십자가와 비문, 깨진 어깨, 겹겹이 떨어진 풍화, 아래쪽 이끼, 작은 덩굴"""
    rng = random.Random(101)
    W_, T_ = 0.65, 0.16
    z0, hs = 0.12, 0.63                    # 옆선 끝 0.75 → 꼭대기 0.75 + 0.325 = 1.075
    y0 = -T_ / 2
    slab = obj_bm(bm_poly(round_top(W_, z0, hs, 24), y0, T_ / 2), "slab")
    chip(slab, rng, 14, (0.03, 0.08), sharp_deg=35, bite=0.38, zmin=0.3)
    # 오른쪽 어깨가 크게 깨져 나감 + 왼쪽 아래 모서리
    cut(slab, [chunk((0.3, -0.02, 1.0), (0.13, 0.16, 0.11), rng, 9, (0.1, 0.3)),
               chunk((-0.335, -0.075, 0.45), (0.035, 0.045, 0.07), rng, 8, (0.1, 0.3))])
    # 앞면 테두리 안쪽을 얕게 판 면 (액자)
    inner = round_top(W_ - 0.1, z0 + 0.1, hs - 0.1, 22)
    cut(slab, [obj_bm(bm_poly(inner, y0 - 0.05, y0 + 0.009), "panel")])
    # 십자가 (끝이 살짝 벌어진 모양) + 비문
    yf = y0 + 0.009
    cx, cz = 0.0, 0.86
    cross = [(-0.022, -0.13), (0.022, -0.13), (0.018, 0.02), (0.075, 0.025), (0.08, 0.065), (0.018, 0.06), (0.022, 0.13),
             (-0.022, 0.13), (-0.018, 0.06), (-0.08, 0.065), (-0.075, 0.025), (-0.018, 0.02)]
    cut(slab, [obj_bm(bm_poly([(cx + x, cz + z) for x, z in cross], yf - 0.05, yf + 0.013), "cross")])
    st = text_strokes(rng, 0.0, 0.61, 0.4, 0.046, yf, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.52, 0.34, 0.034, yf, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.445, 0.3, 0.03, yf, jitter=0.002)
    st += crack_strokes(rng, (0.27, yf, 0.32), (-1, 0, 0.4), 0.22, 5, 0.5, yf)     # 아래 오른쪽에서 들어온 금
    engrave(slab, st, (0, -1, 0), 0.0085, 0.007)
    # 앞·옆면이 얇게 떨어져 나간 자국
    cut(slab, [spall((0.2, y0, 0.3), (0, -1, 0), (0.09, 0.06), 0.01, rng),
               spall((-0.24, y0, 0.98), (0, -1, 0.2), (0.07, 0.05), 0.008, rng),
               spall((0.325, 0.0, 0.55), (1, 0, 0), (0.06, 0.09), 0.012, rng)])
    # 뒤로 살짝 눕고 옆으로 기운다
    slab.data.transform(Matrix.Translation((0, 0, 0.14)) @ Matrix.Rotation(R(-2.5), 4, 'X') @ Matrix.Rotation(R(2.0), 4, 'Y') @ Matrix.Translation((0, 0, -0.14)))
    pl = bm_box(0.86, 0.34, 0.17, TR((0, 0.005, 0.065)))
    stone_blk(pl, rng, (2, 4), (0.03, 0.07), (2, 3), 0.01, zmin=0.0)
    plinth = obj_bm(pl, "plinth")
    chip(plinth, rng, 7, (0.04, 0.08), bite=0.35, zmin=0.08)
    cut(plinth, [chunk((0.42, -0.17, 0.15), (0.08, 0.07, 0.06), rng, 8)])
    body = join([slab, plinth])
    sculpt(body, 0.0035, STONE_LAYERS(1.0, wear=1.15, cracks=0.55), seed=11)
    m = stone_mat("slab_a", 'stone', moss=0.65, low_moss=0.85, mz=0.42)
    set_mat(body, m)
    low = low_of(body, 3700)
    # 왼쪽 뒤 받침에서 기어오르는 덩굴 (조금)
    v = Vine(rng, leaf=(0.032, 0.052), leaf_p=0.42)
    tgt = copy(low)
    ivy_grow(v, tgt, (-0.36, 0.12, 0.02), seed=4, length=1.0, step=0.025, max_roots=6, gravity=0.4, adhesion=0.8, zmax=0.85)
    ivy_grow(v, tgt, (0.3, 0.17, 0.02), seed=9, length=0.5, step=0.025, max_roots=4, gravity=0.4, adhesion=0.8, zmax=0.45)
    delete(tgt)
    return finish("grave_slab_a", [body], [low], extras=v.objects(), size=1024, extr=0.03)

def daisy_strokes(cx, cz, r, y, n=8):
    """여섯 꽃잎 원 문양 (컴퍼스로 그린 옛 묘비 장식): 바깥 원 위 여섯 점을 중심으로 한 호"""
    out = []
    for k in range(6):
        th = R(90 + 60 * k)
        c = (cx + r * math.cos(th), cz + r * math.sin(th))
        out += arc_strokes(c[0], c[1], r, th + R(120), th + R(240), y, n)
    return out

def place_on_ground(o, sink=0.02):
    """가장 낮은 점이 z = -sink 가 되게 내린다"""
    zmin = min((o.matrix_world @ v.co).z for v in o.data.vertices)
    o.data.transform(Matrix.Translation((0, 0, -zmin - sink)))
    return o

def grave_slab_b():
    """윗부분이 사선으로 부러진 묘비 + 옆에 누운 조각. 여섯 꽃잎 원 문양과 테두리 선"""
    rng = random.Random(202)
    T_ = 0.15
    y0 = -T_ / 2
    outline = [(-0.3, 0.1), (0.3, 0.1), (0.3, 0.98), (0.23, 1.05), (0.08, 1.05), (0.0, 1.11), (-0.08, 1.05), (-0.23, 1.05), (-0.3, 0.98)]
    slab = obj_bm(bm_poly(outline, y0, T_ / 2), "slab")
    chip(slab, rng, 10, (0.03, 0.07), sharp_deg=35, bite=0.38, zmin=0.3)
    yf = y0
    # 테두리 선 (안쪽으로 4cm)
    border = [(-0.25, 0.2), (0.25, 0.2), (0.25, 0.96), (0.2, 1.0), (0.07, 1.0), (0.0, 1.05), (-0.07, 1.0), (-0.2, 1.0), (-0.25, 0.96)]
    st = list(zip([Vector((x, yf, z)) for x, z in border], [Vector((x, yf, z)) for x, z in border[1:] + border[:1]]))
    engrave(slab, st, (0, -1, 0), 0.01, 0.008)
    # 원 문양: 바깥 고리 + 여섯 꽃잎
    cx, cz, r = 0.0, 0.73, 0.14
    cut(slab, [obj_bm(annulus_y(cx, cz, r + 0.004, r + 0.017, yf - 0.05, yf + 0.009, 72), "ring")])
    engrave(slab, daisy_strokes(cx, cz, r, yf, 12), (0, -1, 0), 0.0075, 0.006)
    st = text_strokes(rng, 0.0, 0.5, 0.38, 0.04, yf, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.42, 0.32, 0.032, yf, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.35, 0.26, 0.03, yf, jitter=0.002)
    engrave(slab, st, (0, -1, 0), 0.0085, 0.007)
    cut(slab, [spall((-0.18, y0, 0.27), (0, -1, 0), (0.08, 0.05), 0.009, rng), spall((0.3, 0.0, 0.4), (1, 0, 0), (0.05, 0.08), 0.01, rng)])
    # 사선으로 부러짐: 같은 단면 커터로 위(조각)와 아래(서 있는 몸)를 나눈다
    n = Vector((0.27, 0.12, 0.6)).normalized()
    co = Vector((0.0, 0.0, 0.815))
    piece = copy(slab)
    cut(slab, [rough_cutter(co, n, 1.6, 1.6, 0.035, 7.0, 30, 2.0, seed=5)])
    intersect(piece, [rough_cutter(co, n, 1.6, 1.6, 0.035, 7.0, 30, 2.0, seed=5)])
    chip(slab, rng, 5, (0.02, 0.05), sharp_deg=40, bite=0.4, zmin=0.6)
    # 서 있는 몸: 앞으로 조금 기운다
    slab.data.transform(Matrix.Translation((0, 0, 0.12)) @ Matrix.Rotation(R(4.5), 4, 'X') @ Matrix.Rotation(R(-2.5), 4, 'Y') @ Matrix.Translation((0, 0, -0.12)))
    # 떨어진 조각: 앞면이 하늘을 보게 눕혀 오른쪽 땅에 둔다
    c = sum((v.co for v in piece.data.vertices), Vector()) / len(piece.data.vertices)
    piece.data.transform(Matrix.Translation((0.69, -0.2, 0.0)) @ Matrix.Rotation(R(28), 4, 'Z') @ Matrix.Rotation(R(7), 4, 'Y') @
                         Matrix.Rotation(R(-86), 4, 'X') @ Matrix.Translation(-c))
    place_on_ground(piece, 0.025)
    # 받침돌
    pl = bm_box(0.8, 0.3, 0.15, TR((0, 0.0, 0.055)))
    stone_blk(pl, rng, (2, 4), (0.03, 0.06), (2, 3), 0.01, zmin=0.0)
    plinth = obj_bm(pl, "plinth")
    chip(plinth, rng, 6, (0.035, 0.07), bite=0.35, zmin=0.06)
    # 부서진 부스러기
    bits = [chunk((0.45 + rng.uniform(-0.08, 0.1), -0.32 + rng.uniform(-0.1, 0.1), 0.0), (s, s * 0.8, s * 0.6), rng, 8, (0.1, 0.35))
            for s in (0.035, 0.028, 0.045, 0.022)]
    body = join([slab, plinth, piece] + bits)
    sculpt(body, 0.0035, STONE_LAYERS(1.0, wear=1.2, cracks=0.6), seed=21)
    m = stone_mat("slab_b", 'stone_pale', moss=0.8, low_moss=0.8, mz=0.35)
    set_mat(body, m)
    low = low_of(body, 3600)
    return finish("grave_slab_b", [body], [low], size=1024, extr=0.03)

def grave_slab_c():
    """키 큰 고딕 뾰족 아치 묘비: 뚫린 사엽(四葉) 창과 고리, 판 면 비문, 가장자리 꽃봉오리 장식, 2단 받침"""
    rng = random.Random(303)
    T_ = 0.17
    y0 = -T_ / 2
    z0, w, hsp, rise = 0.21, 0.6, 0.84, 0.44            # 꼭대기 z0 + hsp + rise = 1.49
    out = [(x, z + z0) for x, z in pointed_arch(w, hsp, rise, 16)]
    slab = obj_bm(bm_poly(out, y0, T_ / 2), "slab")
    chip(slab, rng, 12, (0.03, 0.07), sharp_deg=35, bite=0.38, zmin=0.35)
    yf = y0 + 0.012
    inner = [(x, z + z0 + 0.06) for x, z in pointed_arch(w - 0.11, hsp - 0.06, rise - 0.07, 16)]
    cut(slab, [obj_bm(bm_poly(inner, y0 - 0.05, yf), "panel")])
    # 뚫린 사엽 창 (+ 둘레 고리 홈)
    qx, qz, lr, off = 0.0, z0 + hsp + 0.07, 0.042, 0.038
    qc = [cyl(lr, 0.5, (qx + dx, 0, qz + dz), 28, rot=(R(90), 0, 0)) for dx, dz in ((off, 0), (-off, 0), (0, off), (0, -off))]
    qc.append(box(0.07, 0.5, 0.07, (qx, 0, qz), rot=(0, R(45), 0)))
    cut(slab, qc)
    cut(slab, [obj_bm(annulus_y(qx, qz, 0.1, 0.112, yf - 0.05, yf + 0.008, 64), "ring")])
    # 비문 + 금
    st = text_strokes(rng, 0.0, 0.8, 0.36, 0.042, yf, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.72, 0.32, 0.032, yf, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.65, 0.3, 0.03, yf, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.58, 0.22, 0.03, yf, jitter=0.002)
    engrave(slab, st, (0, -1, 0), 0.0085, 0.007)
    cr = crack_strokes(rng, (0.3, y0, 1.02), (-1, 0, -0.5), 0.34, 7, 0.45, y0)
    engrave(slab, cr, (0, -1, 0), 0.011, 0.04)
    cut(slab, [chunk((-0.31, -0.05, 0.42), (0.06, 0.07, 0.1), rng, 8), chunk((0.04, -0.09, z0 + hsp + rise - 0.02), (0.05, 0.05, 0.05), rng, 8),
               spall((0.12, y0, 0.35), (0, -1, 0), (0.08, 0.06), 0.01, rng)])
    slab.data.transform(Matrix.Translation((0, 0, 0.2)) @ Matrix.Rotation(R(-3), 4, 'Y') @ Matrix.Rotation(R(-1.5), 4, 'X') @ Matrix.Translation((0, 0, -0.2)))
    # 가장자리 꽃봉오리 장식(crocket) — 아치 두 변을 따라 위로 말린 혹 + 꼭대기 장식의 부러진 밑동
    knobs = []
    for side in (-1, 1):
        for t in (0.28, 0.55, 0.8):
            zz = z0 + hsp + rise * t
            pts = [p for p in out if (p[0] * side) > 0 and abs(p[1] - zz) < rise * 0.08]
            if not pts:
                continue
            px, pz = pts[0]
            knobs.append(((px + side * 0.022, 0.0, pz + 0.01), (0.03, 0.05, 0.022), (0, side * R(-35), 0)))
            knobs.append(((px + side * 0.03, 0.0, pz + 0.035), (0.016, 0.04, 0.02), (0, side * R(-10), 0)))
    knobs.append(((0, 0, z0 + hsp + rise + 0.02), (0.035, 0.045, 0.04)))
    kb = blobs(knobs, 2, "knobs")
    kb.data.transform(Matrix.Translation((0, 0, 0.2)) @ Matrix.Rotation(R(-3), 4, 'Y') @ Matrix.Rotation(R(-1.5), 4, 'X') @ Matrix.Translation((0, 0, -0.2)))
    # 2단 받침
    p1 = bm_box(0.9, 0.46, 0.14, TR((0, 0, 0.05)))
    stone_blk(p1, rng, (2, 4), (0.03, 0.07), (2, 3), 0.012, zmin=0.0)
    p2 = bm_frustum(0.76, 0.36, 0.7, 0.31, 0.12, 0.23)
    stone_blk(p2, rng, (1, 3), (0.02, 0.05), (1, 2), 0.01)
    b1, b2 = obj_bm(p1, "p1"), obj_bm(p2, "p2")
    chip(b1, rng, 6, (0.04, 0.08), bite=0.35, zmin=0.06)
    body = join([slab, kb, b1, b2])
    sculpt(body, 0.0035, STONE_LAYERS(1.0, wear=1.2, cracks=0.6), seed=31)
    m = stone_mat("slab_c", 'stone_dark', moss=0.75, low_moss=0.9, mz=0.5, edge=0.95)
    set_mat(body, m)
    low = low_of(body, 3800)
    return finish("grave_slab_c", [body], [low], size=1024, extr=0.03)

def grave_cross():
    """켈트식 고리 십자가: 겨드랑이가 둥글게 파인 십자 + 고리 + 가운데 둥근 돋을새김, 줄기에 마름모 새김, 계단형 받침"""
    rng = random.Random(404)
    T_ = 0.15
    y0 = -T_ / 2
    zc = 1.33
    outline = [(-0.13, 0.46), (0.13, 0.46), (0.1, zc - 0.095), (0.36, zc - 0.115), (0.36, zc + 0.115), (0.1, zc + 0.095),
               (0.112, 1.72), (-0.112, 1.72), (-0.1, zc + 0.095), (-0.36, zc + 0.115), (-0.36, zc - 0.115), (-0.1, zc - 0.095)]
    cr = obj_bm(bm_poly(outline, y0, T_ / 2), "cross")
    chip(cr, rng, 12, (0.025, 0.06), sharp_deg=35, bite=0.38, zmin=0.6)
    pits = [cyl(0.046, 0.5, (sx * 0.1, 0, zc + sz * 0.095), 28, rot=(R(90), 0, 0)) for sx in (-1, 1) for sz in (-1, 1)]
    cut(cr, pits)
    yf = y0
    # 줄기 테두리 선 + 마름모 새김, 팔 끝 테두리
    st = []
    xs, zb, zt = 0.085, 0.62, zc - 0.16
    for a, b in (((-xs, zb), (xs, zb)), ((xs, zb), (xs * 0.95, zt)), ((xs * 0.95, zt), (-xs * 0.95, zt)), ((-xs * 0.95, zt), (-xs, zb))):
        st.append((Vector((a[0], yf, a[1])), Vector((b[0], yf, b[1]))))
    n_d = 5
    hgt = (zt - zb) / n_d
    for i in range(n_d):
        za, zm, zb_ = zb + hgt * i, zb + hgt * (i + 0.5), zb + hgt * (i + 1)
        w_ = xs * 0.8
        pts = [(0, za + 0.01), (w_, zm), (0, zb_ - 0.01), (-w_, zm)]
        for k in range(4):
            a, b = pts[k], pts[(k + 1) % 4]
            st.append((Vector((a[0], yf, a[1])), Vector((b[0], yf, b[1]))))
    for sx in (-1, 1):
        x0_ = sx * 0.2
        x1_ = sx * 0.33
        for a, b in (((x0_, zc - 0.065), (x1_, zc - 0.08)), ((x1_, zc - 0.08), (x1_, zc + 0.08)), ((x1_, zc + 0.08), (x0_, zc + 0.065))):
            st.append((Vector((a[0], yf, a[1])), Vector((b[0], yf, b[1]))))
    for a, b in (((-0.065, zc + 0.2), (-0.08, 1.68)), ((-0.08, 1.68), (0.08, 1.68)), ((0.08, 1.68), (0.065, zc + 0.2))):
        st.append((Vector((a[0], yf, a[1])), Vector((b[0], yf, b[1]))))
    engrave(cr, st, (0, -1, 0), 0.0095, 0.008)
    # 오른팔 끝이 부러짐
    cut(cr, [rough_cutter((0.27, 0, zc), (1, -0.15, 0.25), 0.8, 0.8, 0.03, 9.0, 24, 1.0, seed=3)])
    # 고리 (십자보다 얇게) + 가운데 돋을새김
    ring = obj_bm(annulus_y(0, zc, 0.2, 0.268, -0.052, 0.052, 72), "ring")
    chip(ring, rng, 8, (0.02, 0.05), sharp_deg=40, bite=0.38)
    boss = cyl(0.056, 0.1, (0, -0.05, zc), 32, rot=(R(90), 0, 0))
    cut(boss, [obj_bm(annulus_y(0, zc, 0.03, 0.039, -0.2, -0.094, 48), "bg")])
    top = join([cr, ring, boss])
    remesh(top, 0.004)
    # 고리의 금: 바깥에서 안쪽으로 파고든 갈라짐
    cs = [stroke_box(a, b, (0, -1, 0), 0.008, 0.2) for a, b in crack_strokes(rng, (math.cos(R(132)) * 0.285, 0.0, zc + math.sin(R(132)) * 0.285),
                                                                             (math.cos(R(132 + 180)), 0, math.sin(R(132 + 180))), 0.085, 4, 0.45, 0.0)]
    cut(top, cs)
    top.data.transform(Matrix.Translation((0, 0, 0.5)) @ Matrix.Rotation(R(2.5), 4, 'Y') @ Matrix.Rotation(R(-1.5), 4, 'X') @ Matrix.Translation((0, 0, -0.5)))
    # 계단형 받침 + 사각뿔대 받침돌
    s1 = bm_box(0.76, 0.6, 0.17, TR((0, 0, 0.065)))
    stone_blk(s1, rng, (2, 4), (0.03, 0.07), (2, 3), 0.012, zmin=0.0)
    s2 = bm_box(0.56, 0.44, 0.14, TR((0, 0, 0.215)))
    stone_blk(s2, rng, (1, 3), (0.025, 0.06), (1, 3), 0.01)
    s3 = bm_frustum(0.4, 0.3, 0.31, 0.23, 0.28, 0.52)
    stone_blk(s3, rng, (1, 2), (0.02, 0.04), (1, 2), 0.008)
    b1, b2, b3 = obj_bm(s1, "s1"), obj_bm(s2, "s2"), obj_bm(s3, "s3")
    chip(b1, rng, 6, (0.04, 0.08), bite=0.35, zmin=0.08)
    chip(b2, rng, 4, (0.03, 0.06), bite=0.35)
    body = join([top, b1, b2, b3])
    sculpt(body, 0.004, STONE_LAYERS(1.1, wear=1.2, cracks=0.6), seed=41)
    m = stone_mat("cross", 'stone', moss=0.7, low_moss=0.9, mz=0.6)
    set_mat(body, m)
    low = low_of(body, 4200)
    v = Vine(rng, leaf=(0.035, 0.058), leaf_p=0.55)
    tgt = copy(low)
    ivy_grow(v, tgt, (-0.3, -0.29, 0.02), seed=12, length=1.6, step=0.03, max_roots=8, gravity=0.35, adhesion=0.85, zmax=1.25)
    ivy_grow(v, tgt, (0.36, 0.2, 0.02), seed=17, length=0.7, step=0.03, max_roots=5, gravity=0.4, adhesion=0.85, zmax=0.6)
    delete(tgt)
    return finish("grave_cross", [body], [low], extras=v.objects(), size=1024, extr=0.03)

def grave_obelisk():
    """오벨리스크: 3단 받침, 비문 명판, 처마돌, 가늘어지는 기둥, 부러진 꼭대기(조각이 받침에 떨어져 있음)"""
    rng = random.Random(505)
    s1 = bm_box(0.94, 0.94, 0.17, TR((0, 0, 0.055)))
    stone_blk(s1, rng, (3, 5), (0.03, 0.08), (2, 4), 0.012, zmin=0.0)
    s2 = bm_box(0.75, 0.75, 0.14, TR((0, 0, 0.21)))
    stone_blk(s2, rng, (2, 4), (0.03, 0.06), (2, 3), 0.01)
    die = bm_box(0.56, 0.56, 0.5, TR((0, 0, 0.53)))
    bm_chip(die, rng, 3, (0.02, 0.05))
    bm_bevel(die, 0.01)
    cor = bm_frustum(0.58, 0.58, 0.68, 0.68, 0.78, 0.84)
    bm_chip(cor, rng, 2, (0.02, 0.04))
    cap = bm_frustum(0.68, 0.68, 0.46, 0.46, 0.84, 0.94)
    bm_chip(cap, rng, 3, (0.02, 0.04))
    shaft = bm_frustum(0.36, 0.36, 0.245, 0.245, 0.93, 2.03)
    bm_bevel(shaft, 0.008)
    pyr = bm_frustum(0.245, 0.245, 0.004, 0.004, 2.03, 2.25)
    ob = {k: obj_bm(b, k) for k, b in (("s1", s1), ("s2", s2), ("die", die), ("cor", cor), ("cap", cap), ("shaft", shaft), ("pyr", pyr))}
    chip(ob["s1"], rng, 8, (0.04, 0.09), bite=0.35, zmin=0.08)
    chip(ob["s2"], rng, 6, (0.03, 0.07), bite=0.35)
    chip(ob["die"], rng, 8, (0.03, 0.06), bite=0.38)
    chip(ob["cor"], rng, 6, (0.03, 0.06), bite=0.38)
    chip(ob["shaft"], rng, 12, (0.025, 0.06), bite=0.38)
    # 명판: 판 면 + 비문 + 위쪽 작은 고리
    yf = -0.28
    cut(ob["die"], [box(0.4, 0.1, 0.34, (0, yf - 0.05 + 0.012, 0.52))])
    yp = yf + 0.012
    st = text_strokes(rng, 0.0, 0.57, 0.32, 0.042, yp, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.5, 0.3, 0.034, yp, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.44, 0.28, 0.032, yp, jitter=0.002)
    st += text_strokes(rng, 0.0, 0.385, 0.18, 0.032, yp, jitter=0.002)
    engrave(ob["die"], st, (0, -1, 0), 0.0095, 0.008)
    cut(ob["die"], [obj_bm(annulus_y(0, 0.64, 0.02, 0.03, yp - 0.05, yp + 0.007, 40), "r")])
    cut(ob["die"], [chunk((0.28, -0.28, 0.32), (0.07, 0.07, 0.1), rng, 9), spall((-0.28, 0.1, 0.6), (-1, 0, 0), (0.08, 0.1), 0.012, rng)])
    # 기둥 앞면: 고리 안의 모래시계 새김
    def yface(z):
        return -(0.18 - 0.0575 * (z - 0.93) / 1.1)
    zc = 1.7
    yfc = yface(zc)
    nf = Vector((0, -1, 0.052)).normalized()
    st = arc_strokes(0, zc, 0.07, 0, 2 * math.pi, yfc, 16)
    hg = [((-0.035, 0.045), (0.035, 0.045)), ((0.035, 0.045), (-0.035, -0.045)), ((-0.035, -0.045), (0.035, -0.045)), ((0.035, -0.045), (-0.035, 0.045))]
    st += [(Vector((a[0], yface(zc + a[1]), zc + a[1])), Vector((b[0], yface(zc + b[1]), zc + b[1]))) for a, b in hg]
    engrave(ob["shaft"], st, nf, 0.009, 0.008)
    cut(ob["shaft"], [spall((0.16, -0.05, 1.3), (1, 0, 0.05), (0.06, 0.1), 0.01, rng), spall((-0.1, 0.14, 1.55), (0, 1, 0.05), (0.07, 0.12), 0.01, rng)])
    # 꼭대기가 부러짐: 조각은 받침 모서리에 떨어져 있다
    upper = join([ob["shaft"], ob["pyr"]])
    remesh(upper, 0.006)
    tip = copy(upper)
    n = Vector((0.45, -0.25, 1.0)).normalized()
    co = Vector((0, 0, 2.1))
    cut(upper, [rough_cutter(co, n, 0.8, 0.8, 0.03, 9.0, 24, 1.0, seed=6)])
    intersect(tip, [rough_cutter(co, n, 0.8, 0.8, 0.03, 9.0, 24, 1.0, seed=6)])
    c = sum((v.co for v in tip.data.vertices), Vector()) / max(1, len(tip.data.vertices))
    tip.data.transform(Matrix.Translation((0.66, -0.52, 0.0)) @ Matrix.Rotation(R(35), 4, 'Z') @ Matrix.Rotation(R(100), 4, 'Y') @ Matrix.Translation(-c))
    place_on_ground(tip, 0.02)
    body = join([ob["s1"], ob["s2"], ob["die"], ob["cor"], ob["cap"], upper, tip])
    sculpt(body, 0.0045, STONE_LAYERS(1.3, wear=1.2, cracks=0.6), seed=51)
    m = stone_mat("obelisk", 'stone', moss=0.8, low_moss=0.9, mz=0.5)
    set_mat(body, m)
    low = low_of(body, 5600)
    v = Vine(rng, leaf=(0.04, 0.065), leaf_p=0.55)
    tgt = copy(low)
    ivy_grow(v, tgt, (-0.42, 0.3, 0.02), seed=21, length=2.0, step=0.03, max_roots=9, gravity=0.35, adhesion=0.85, zmax=1.5)
    for x, y in ((-0.3, 0.33), (-0.33, 0.15)):
        hang_strand(v, (x, y + 0.02, 0.85), rng.uniform(0.18, 0.3), rng, face=(0, 1, 0) if y > 0.3 else (-1, 0, 0))
    delete(tgt)
    return finish("grave_obelisk", [body], [low], extras=v.objects(), size=2048, extr=0.04, lod2=0.12)

def offset_poly(pts, d):
    """볼록 다각형(XY, 반시계)을 d 만큼 안쪽(+)/바깥(-)으로 옮긴 다각형"""
    n = len(pts)
    lines = []
    for i in range(n):
        a, b = Vector((*pts[i], 0)), Vector((*pts[(i + 1) % n], 0))
        e = (b - a).normalized()
        nl = Vector((-e.y, e.x, 0))
        lines.append((a + nl * d, e))
    out = []
    for i in range(n):
        p1, e1 = lines[i - 1]
        p2, e2 = lines[i]
        den = e1.x * e2.y - e1.y * e2.x
        t = ((p2.x - p1.x) * e2.y - (p2.y - p1.y) * e2.x) / den
        q = p1 + e1 * t
        out.append((q.x, q.y))
    return out

def poly_ring(outer, inner, z0, z1):
    """같은 꼭짓점 수의 두 다각형(XY) 사이 띠 (홈 파기 커터)"""
    bm = bmesh.new()
    n = len(outer)
    o0 = [bm.verts.new((x, y, z0)) for x, y in outer]
    o1 = [bm.verts.new((x, y, z1)) for x, y in outer]
    i0 = [bm.verts.new((x, y, z0)) for x, y in inner]
    i1 = [bm.verts.new((x, y, z1)) for x, y in inner]
    for k in range(n):
        j = (k + 1) % n
        bm.faces.new((o0[k], o0[j], o1[j], o1[k]))
        bm.faces.new((i0[k], i1[k], i1[j], i0[j]))
        bm.faces.new((o0[k], i0[k], i0[j], o0[j]))
        bm.faces.new((o1[k], o1[j], i1[j], i1[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm

def grain_guide(points, d=(1, 0, 0)):
    """나뭇결 방향 안내 (kit.surface 의 bark 층이 'dir' 속성을 따라 결을 늘인다)"""
    me = bpy.data.meshes.new("gguide")
    me.from_pydata([tuple(p) for p in points], [], [])
    a = me.attributes.new("dir", 'FLOAT_VECTOR', 'POINT')
    for i in range(len(points)):
        a.data[i].vector = d
    return link(bpy.data.objects.new("gguide", me))

WOOD_LAYERS = [{'t': 'lumps', 'scale': 2.5, 'amp': 0.002},
               {'t': 'bark', 'scale': 14, 'width': 0.06, 'depth': 0.004, 'stretch': 0.06},
               {'t': 'bark', 'scale': 40, 'width': 0.08, 'depth': 0.0015, 'stretch': 0.08},
               {'t': 'pits', 'scale': 60, 'depth': 0.001, 'cover': 0.5},
               {'t': 'grain', 'scale': 200, 'amp': 0.0003}]
WOOD_OLD = ((0.03, 0.025, 0.028), (0.15, 0.11, 0.1), (0.33, 0.28, 0.27))

def iron_mat(name, rust=0.6):
    m = paint(name, 'iron', moss=0.0, dirt=0.3, streaks=0.3, ao=0.08, edge=0.9, cavity=0.9, grain_bump=0.8, cracks=0.0, hue_var=0.2)
    blotch(m, (0.2, 0.075, 0.04), 7, rust, 0.45, 0.6, mode='MIX')
    return m

def soul_pool(cx, cy, z, rx, ry, rng, n=20):
    """울퉁불퉁한 가장자리의 납작한 영혼 빛 웅덩이 (Glow_Soul)"""
    verts = [(cx, cy, z)]
    for i in range(n):
        a = 2 * math.pi * i / n
        k = rng.uniform(0.75, 1.1)
        verts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k, z + rng.uniform(-0.004, 0.004)))
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    return glow_obj(verts, faces)

def grave_tomb():
    """상자형 석관 무덤: 판넬 장식, 모서리 기둥 위 해골 장식, 십자 돋을새김 뚜껑이 비스듬히 밀려 틈에서 보랏빛이 샌다"""
    rng = random.Random(606)
    L, D = 1.96, 0.86
    parts = []
    pl = bm_box(2.26, 1.16, 0.15, TR((0, 0, 0.045)))
    stone_blk(pl, rng, (3, 5), (0.04, 0.09), (2, 4), 0.012, zmin=0.0)
    parts.append(obj_bm(pl, "plinth"))
    chip(parts[-1], rng, 10, (0.05, 0.1), bite=0.35, zmin=0.06)
    core = obj_bm(bm_box(L, D, 0.62, TR((0, 0, 0.42))), "core")
    pil = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            b = bm_box(0.14, 0.14, 0.6, TR((sx * (L / 2 - 0.035), sy * (D / 2 - 0.035), 0.42)))
            bm_chip(b, rng, 1, (0.015, 0.035), zmin=0.5)
            bm_bevel(b, 0.008)
            pil.append(obj_bm(b, "pil"))
    band = bm_box(L + 0.1, D + 0.1, 0.07, TR((0, 0, 0.7)))
    bm_flake(band, rng, 3)
    bm_bevel(band, 0.01)
    foot = bm_box(L + 0.08, D + 0.08, 0.05, TR((0, 0, 0.145)))
    bm_bevel(foot, 0.008)
    body = join([core, obj_bm(band, "band"), obj_bm(foot, "foot")] + pil)
    remesh(body, 0.008)
    chip(body, rng, 14, (0.03, 0.07), sharp_deg=40, bite=0.38, zmin=0.3)
    # 판넬 (앞뒤 두 칸씩, 양 끝 한 칸) + 속 빈 곳
    yf, yb, xe = -D / 2, D / 2, L / 2
    cs = []
    for x in (-0.44, 0.44):
        cs.append(box(0.74, 0.1, 0.38, (x, yf - 0.05 + 0.02, 0.43)))
        cs.append(box(0.74, 0.1, 0.38, (x, yb + 0.05 - 0.02, 0.43)))
    for sx in (-1, 1):
        cs.append(box(0.1, 0.54, 0.38, (sx * (xe + 0.05 - 0.02), 0, 0.43)))
    cs.append(box(1.62, 0.56, 0.6, (0, 0, 0.58)))
    cut(body, cs)
    # 앞 왼쪽 판넬: 여섯 꽃잎 원, 오른쪽: 비문, 뒤: 고리 + 금
    yp = yf + 0.02
    st = daisy_strokes(-0.44, 0.43, 0.11, yp, 8)
    cut(body, [obj_bm(annulus_y(-0.44, 0.43, 0.114, 0.127, yp - 0.05, yp + 0.008, 64), "r")])
    st += text_strokes(rng, 0.44, 0.53, 0.56, 0.045, yp, jitter=0.002)
    st += text_strokes(rng, 0.44, 0.45, 0.5, 0.035, yp, jitter=0.002)
    st += text_strokes(rng, 0.44, 0.38, 0.52, 0.035, yp, jitter=0.002)
    st += text_strokes(rng, 0.44, 0.31, 0.3, 0.035, yp, jitter=0.002)
    engrave(body, st, (0, -1, 0), 0.01, 0.008)
    cr = crack_strokes(rng, (-0.08, yf, 0.73), (-0.3, 0, -1), 0.32, 6, 0.5, yf)
    engrave(body, cr, (0, -1, 0), 0.012, 0.05)
    cut(body, [chunk((0.99, -0.44, 0.7), (0.08, 0.08, 0.06), rng, 8), spall((0.8, yf - 0.02, 0.22), (0, -1, 0), (0.1, 0.06), 0.012, rng),
               spall((-xe - 0.03, 0.25, 0.55), (-1, 0, 0), (0.08, 0.1), 0.012, rng)])
    # 뚜껑: 위 모서리를 깎은 판 + 긴 십자 돋을새김. 밀려나 비스듬히 놓였고 한쪽 모서리가 깨졌다
    lb = bm_box(2.14, 1.04, 0.13, TR((0, 0, 0.065)))
    bm_bevel(lb, 0.03)
    bm_flake(lb, rng, 3, axes=((0, 0, 1), (0, -1, 0), (1, 0, 0)))
    lid = obj_bm(lb, "lid")
    crs = [obj_bm(bm_box(1.5, 0.11, 0.05, TR((0.05, 0, 0.14))), "cs"), obj_bm(bm_box(0.11, 0.62, 0.05, TR((-0.38, 0, 0.14))), "ca")]
    lid = join([lid] + crs)
    remesh(lid, 0.008)
    chip(lid, rng, 12, (0.03, 0.07), sharp_deg=40, bite=0.38)
    cut(lid, [chunk((-1.07, -0.52, 0.1), (0.13, 0.12, 0.1), rng, 9), chunk((1.05, 0.5, 0.08), (0.07, 0.08, 0.08), rng, 8)])
    engrave(lid, [(Vector((a.x, a.z, 0.13)), Vector((b.x, b.z, 0.13))) for a, b in crack_strokes(rng, (-1.0, 0, 0.1), (1, 0, 0.6), 0.4, 6, 0.5)],
            (0, 0, 1), 0.012, 0.03)
    Ml = Matrix.Translation((0.33, 0.03, 0.735)) @ Matrix.Rotation(R(7), 4, 'Z') @ Matrix.Rotation(R(1.2), 4, 'Y')
    lid.data.transform(Ml)
    body = join([body, lid] + parts)
    sculpt(body, 0.005, STONE_LAYERS(1.3, wear=1.2, cracks=0.6), seed=61)
    m = stone_mat("tomb", 'stone', moss=0.85, low_moss=0.85, mz=0.45)
    tint_near(m, (-0.85, 0.0, 0.62), 0.45, (0.16, 0.08, 0.3), 0.6)    # 틈 둘레에 스민 보랏빛
    set_mat(body, m)
    # 앞 모서리 기둥 위의 해골 장식
    sk = skull_high(rng, jaw_open=4, seed=6, moss=0.3, dirt=0.0, pal='stone')
    sk_low = low_of(sk, 650, -1)
    highs, lows = [body], []
    for sx in (-1, 1):
        M = Matrix.Translation((sx * (L / 2 - 0.035), -D / 2 - 0.065, 0.5)) @ Matrix.Rotation(R(sx * 20), 4, 'Z') @ Matrix.Rotation(R(-8), 4, 'X') @ Matrix.Diagonal((0.62, 0.62, 0.62, 1))
        h = copy(sk); h.data.transform(M); highs.append(h)
        l_ = copy(sk_low); l_.data.transform(M); lows.append(l_)
    delete(sk); delete(sk_low)
    low = low_of(body, 6800)
    # 틈 안쪽에 고인 영혼 빛 + 거미줄 + 덩굴
    extras = [soul_pool(-0.6, 0.0, 0.33, 0.22, 0.27, rng)]
    extras.append(web_card((-0.81, -0.28, 0.58), (0, 1, 0.15), (1, 0, 0.1), 0.2))
    extras.append(web_card((1.03, 0.25, 0.74), (0, 0, -1), (1, 0, 0), 0.18, flip=True))
    v = Vine(rng, leaf=(0.04, 0.065), leaf_p=0.55)
    tgt = copy(low)
    ivy_grow(v, tgt, (1.08, 0.55, 0.02), seed=31, length=2.2, step=0.03, max_roots=10, gravity=0.3, adhesion=0.85, zmax=1.0)
    ivy_grow(v, tgt, (-0.4, 0.58, 0.02), seed=33, length=0.9, step=0.03, max_roots=5, gravity=0.35, adhesion=0.85, zmax=0.9)
    for x, y in ((1.3, -0.2), (1.32, 0.1), (1.25, 0.35)):
        hang_strand(v, (x, y, 0.73), rng.uniform(0.2, 0.42), rng, face=(1, 0, 0))
    delete(tgt)
    extras += v.objects()
    return finish("grave_tomb", highs, [low] + lows, extras=extras, size=2048, extr=0.04, lod2=0.12)

def grave_sunken():
    """땅에 깊이 박히고 기운 오래된 묘비 + 봉분 흙더미 (거의 묻혀 반쯤만 보인다)"""
    rng = random.Random(707)
    out = round_top(0.56, 0.0, 0.58, 20, lop=0.15)
    slab = obj_bm(bm_poly(out, -0.075, 0.075), "slab")
    chip(slab, rng, 14, (0.04, 0.09), sharp_deg=35, bite=0.42)
    cut(slab, [chunk((-0.24, -0.02, 0.8), (0.11, 0.14, 0.1), rng, 9), spall((0.1, -0.075, 0.6), (0, -1, 0), (0.12, 0.08), 0.014, rng)])
    yf = -0.075
    st = [(Vector((0, yf, 0.6)), Vector((0, yf, 0.82))), (Vector((-0.07, yf, 0.75)), Vector((0.07, yf, 0.75)))]
    st += text_strokes(rng, 0.0, 0.52, 0.34, 0.04, yf, jitter=0.003)
    engrave(slab, st, (0, -1, 0), 0.012, 0.006)
    slab.data.transform(Matrix.Translation((0.02, 0.14, -0.4)) @ Matrix.Rotation(R(4), 4, 'Z') @ Matrix.Rotation(R(10), 4, 'Y') @ Matrix.Rotation(R(-17), 4, 'X'))
    sculpt(slab, 0.0035, STONE_LAYERS(1.0, wear=1.7, cracks=0.7), seed=71)
    keep_side(slab, (0, 0, -0.08), (0, 0, -1))
    m = stone_mat("sunken", 'stone_dark', moss=1.0, low_moss=1.0, mz=0.3, edge=0.95)
    set_mat(slab, m)
    # 봉분: 앞(-Y)으로 길게, 묘비 밑동을 감싸는 흙 + 박힌 돌멩이
    md = [((0, -0.5, -0.2), (0.48, 0.92, 0.38)), ((0, 0.12, -0.14), (0.42, 0.3, 0.27)), ((0.18, -0.2, -0.12), (0.25, 0.4, 0.22))]
    mound = blobs(md, 4, "mound")
    remesh(mound, 0.008)
    surface(mound, [{'t': 'lumps', 'scale': 2.2, 'amp': 0.03}, {'t': 'lumps', 'scale': 7, 'amp': 0.01},
                    {'t': 'terrace', 'scale': 5, 'steps': 4, 'amp': 0.012, 'cover': 0.7}, {'t': 'pits', 'scale': 30, 'depth': 0.006, 'cover': 0.6},
                    {'t': 'grain', 'scale': 90, 'amp': 0.0015}], seed=72)
    keep_side(mound, (0, 0, -0.08), (0, 0, -1))
    me = paint("earth_s", 'earth', moss=0.6, moss_color=MOSS_DEAD, dirt=0.0, streaks=0.0, ao=0.12, edge=0.35, cavity=0.95, cracks=0.0, hue_var=0.3)
    moss_low(me, 0.0, 0.12, 0.7, MOSS)
    set_mat(mound, me)
    bvh_src = copy(mound)
    pebbles = []
    for i in range(14):
        a = rng.uniform(0, 6.28); r_ = rng.uniform(0.15, 0.95)
        x, y = math.cos(a) * 0.45 * r_, -0.45 + math.sin(a) * 0.9 * r_
        hit, loc, nrm, idx = bvh_src.ray_cast((x, y, 1.0), (0, 0, -1))
        if not hit:
            continue
        s = rng.uniform(0.025, 0.06)
        pebbles.append(chunk(loc + nrm * s * 0.15, (s, s * 0.8, s * 0.6), rng, 8, (0.1, 0.35)))
    pb = join(pebbles)
    remesh(pb, 0.003)
    surface(pb, STONE_LAYERS(0.3), seed=73)
    set_mat(pb, paint("pebble_s", 'stone', moss=0.5, dirt=0.4, ao=0.05))
    lows = [low_of(slab, 2000, -0.06), low_of(mound, 1300, -0.06), low_of(pb, 500, -0.06)]
    gr = Grass(rng)
    for i in range(16):
        a = rng.uniform(0, 6.28); r_ = rng.uniform(0.55, 1.05)
        x, y = math.cos(a) * 0.5 * r_, -0.45 + math.sin(a) * 0.95 * r_
        hit, loc, nrm, idx = bvh_src.ray_cast((x, y, 1.0), (0, 0, -1))
        z = loc.z if hit else 0.0
        gr.tuft((x, y, z - 0.01), rng.randint(5, 9), (0.1, 0.28), 0.05, 0.65)
    delete(bvh_src)
    return finish("grave_sunken", [slab, mound, pb], lows, extras=gr.objects(), size=1024, extr=0.03)

def coffin():
    """육각 나무 관: 판자 이음 홈, 쇠 띠와 징, 고리 손잡이. 뚜껑이 발치 쪽으로 밀려 비스듬히 걸쳐 있고 안에 해골이 보인다"""
    rng = random.Random(808)
    out = [(-0.98, -0.2), (-0.42, -0.31), (0.98, -0.17), (0.98, 0.17), (-0.42, 0.31), (-0.98, 0.2)]
    H = 0.42
    box_ = obj_bm(bm_poly(out, 0.0, H, 'z'), "coffin")
    inner = offset_poly(out, 0.035)
    cut(box_, [obj_bm(bm_poly(inner, 0.05, H + 0.2, 'z'), "in")])
    # 판자 이음 홈 (옆면 둘레)
    grooves = [obj_bm(poly_ring(offset_poly(out, -0.03), offset_poly(out, 0.006), z - 0.004, z + 0.004), "g") for z in (0.145, 0.285)]
    cut(box_, grooves)
    chip(box_, rng, 10, (0.015, 0.04), sharp_deg=40, bite=0.4)
    cut(box_, [chunk((0.98, 0.17, 0.42), (0.04, 0.05, 0.05), rng, 7), chunk((-0.42, -0.31, 0.42), (0.03, 0.04, 0.04), rng, 7)])
    g1 = grain_guide([(x * 0.25, y * 0.1, z * 0.2) for x in range(-4, 5) for y in range(-3, 4) for z in range(0, 3)])
    origin0(box_)
    remesh(box_, 0.004)
    surface(box_, WOOD_LAYERS, seed=81, guide=g1)
    wm = paint("wood_c", WOOD_OLD, moss=0.3, moss_color=MOSS_DEAD, dirt=0.0, streaks=0.4, streak_dir='grain', ao=0.15, edge=0.7, cavity=0.95, cracks=0.0)
    dirt_low(wm, 0.0, 0.12, 0.8)
    moss_low(wm, 0.0, 0.1, 0.6, MOSS)
    set_mat(box_, wm)
    # 뚜껑: 바깥 판 + 가운데 돋운 판, 판자 이음 홈
    lo = offset_poly(out, -0.015)
    lidb = obj_bm(bm_poly(lo, 0.0, 0.045, 'z'), "lid")
    lt = obj_bm(bm_poly(offset_poly(out, 0.06), 0.04, 0.07, 'z'), "lidtop")
    lid = join([lidb, lt])
    remesh(lid, 0.006)
    cut(lid, [box(2.4, 0.008, 0.03, (0, y, 0.075)) for y in (-0.09, 0.09)])
    chip(lid, rng, 8, (0.015, 0.035), sharp_deg=40, bite=0.4)
    remesh(lid, 0.0035)
    surface(lid, WOOD_LAYERS, seed=82, guide=g1)
    set_mat(lid, wm)
    delete(g1)
    # 쇠 띠·징·모서리 쇠·고리 손잡이
    ir = []
    def wall_y(x, side):
        pts = out[:3] if side < 0 else [out[5], out[4], out[3]]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                t = (x - x0) / (x1 - x0)
                return y0 + (y1 - y0) * t, math.atan2(y1 - y0, x1 - x0)
        return pts[-1][1], 0.0
    bands = (-0.7, 0.05, 0.72)
    for x in bands:
        for side in (-1, 1):
            y, ang = wall_y(x, side)
            ir.append(obj_bm(bm_box(0.055, 0.008, H + 0.01, TR((x, y + side * 0.004, H / 2), (0, 0, ang))), "band"))
            ir.append(obj_bm(bm_box(0.055, 0.05, 0.008, TR((x, y - side * 0.016, H + 0.002), (0, 0, ang))), "fold"))
            for z in (0.07, 0.21, 0.35):
                ir.append(blobs([((x, y + side * 0.009, z), (0.008, 0.006, 0.008))], 2, "rivet"))
    for sy in (-1, 1):
        ir.append(obj_bm(bm_box(0.012, 0.09, H * 0.8, TR((-0.984, sy * 0.16, H * 0.5))), "corner"))
    for x in (-0.25, 0.45):
        y, ang = wall_y(x, -1)
        ir.append(obj_bm(bm_box(0.05, 0.016, 0.022, TR((x, y - 0.01, 0.31), (0, 0, ang))), "staple"))
        ir.append(torus(0.042, 0.0075, (x, y - 0.018, 0.27), (R(78), 0, ang), 24, 8))
    body_iron = list(ir)
    lid_iron = []
    for x in (-0.5, 0.2, 0.8):      # 뚜껑 띠: 돋운 판 위 + 양쪽 아래 판 가장자리 (계단 따라 감싼다)
        y0_, _ = wall_y(x, -1)
        y1_, _ = wall_y(x, 1)
        hw = (y1_ - y0_) / 2 + 0.015
        lid_iron.append(obj_bm(bm_box(0.05, 2 * (hw - 0.075) + 0.012, 0.008, TR((x, 0, 0.073))), "lband"))
        for sy in (-1, 1):
            lid_iron.append(obj_bm(bm_box(0.05, 0.08, 0.008, TR((x, sy * (hw - 0.035), 0.048))), "lb2"))
            lid_iron.append(obj_bm(bm_box(0.05, 0.008, 0.05, TR((x, sy * (hw + 0.004), 0.024))), "lb3"))
            lid_iron.append(blobs([((x, sy * (hw - 0.03), 0.054), (0.008, 0.008, 0.006))], 2, "rv"))
    iron = join(body_iron)
    remesh(iron, 0.0025)
    surface(iron, [{'t': 'lumps', 'scale': 30, 'amp': 0.0008}, {'t': 'pits', 'scale': 90, 'depth': 0.0012, 'cover': 0.7}], seed=83)
    im = iron_mat("iron_c", 0.65)
    set_mat(iron, im)
    li = join(lid_iron)
    remesh(li, 0.0025)
    surface(li, [{'t': 'lumps', 'scale': 30, 'amp': 0.0008}, {'t': 'pits', 'scale': 90, 'depth': 0.0012, 'cover': 0.7}], seed=84)
    set_mat(li, im)
    lid = join([lid, li])
    # 뚜껑은 발치 쪽으로 밀려 비스듬히 놓였다
    lid.data.transform(Matrix.Translation((0.5, 0.06, H + 0.004)) @ Matrix.Rotation(R(13), 4, 'Z') @ Matrix.Rotation(R(-2.5), 4, 'X'))
    # 머리 쪽 안에 해골
    sk = skull_high(rng, jaw_open=12, seed=8, moss=0.2, dirt=0.3)
    sk.data.transform(Matrix.Rotation(R(-70), 4, 'X') @ Matrix.Rotation(R(25), 4, 'Y') @ Matrix.Translation((0, 0, -0.08)))
    sk.data.transform(Matrix.Translation((-0.7, 0.03, 0.0)))
    place_on_ground(sk, -0.05)      # 바닥판(z 0.05) 위에 눕힌다
    lows = [low_of(box_, 2600, -1), low_of(lid, 1600, -1), low_of(iron, 1800, -1), low_of(sk, 600, -1)]
    return finish("coffin", [box_, lid, iron, sk], lows, size=1024, extr=0.02)

def bone_pile():
    """해골과 뼈 무더기 (폭 ~1.2m, 높이 ~0.6m): 흙 둔덕 위로 긴 뼈·갈비뼈가 얽히고 해골 넷"""
    rng = random.Random(909)
    mound = blobs([((0, 0, -0.16), (0.56, 0.46, 0.38)), ((0.18, 0.08, -0.08), (0.3, 0.26, 0.22)), ((-0.2, -0.06, -0.1), (0.26, 0.28, 0.2))], 4, "mound")
    remesh(mound, 0.008)
    surface(mound, [{'t': 'lumps', 'scale': 3, 'amp': 0.02}, {'t': 'terrace', 'scale': 6, 'steps': 4, 'amp': 0.01, 'cover': 0.7},
                    {'t': 'pits', 'scale': 30, 'depth': 0.005, 'cover': 0.6}], seed=91)
    keep_side(mound, (0, 0, -0.06), (0, 0, -1))
    me = paint("earth_b", 'earth', moss=0.4, moss_color=MOSS_DEAD, dirt=0.0, streaks=0.0, ao=0.12, edge=0.35, cavity=1.0, cracks=0.0)
    set_mat(mound, me)
    src = copy(mound)

    def surf(x, y):
        hit, loc, nrm, idx = src.ray_cast((x, y, 2.0), (0, 0, -1))
        return (loc, nrm) if hit else (Vector((x, y, 0)), Vector((0, 0, 1)))
    items = []
    for i in range(22):
        a = rng.uniform(0, 6.28); r_ = math.sqrt(rng.uniform(0.0, 1.0))
        x, y = math.cos(a) * 0.5 * r_, math.sin(a) * 0.42 * r_
        loc, nrm = surf(x, y)
        L_ = rng.uniform(0.24, 0.44); rr = rng.uniform(0.013, 0.02)
        z = loc.z + rr * 0.4 + (rng.uniform(0.0, 0.09) if r_ < 0.6 else 0.0)
        yaw = rng.uniform(0, 6.28)
        pitch = rng.uniform(-0.35, 0.35) + (nrm.x * math.cos(yaw) + nrm.y * math.sin(yaw)) * -0.8
        roll = rng.uniform(0, 6.28)
        M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(pitch, 4, 'Y') @ Matrix.Rotation(roll, 4, 'X')
        for c, r, rot in long_bone(L_, rr, rng):
            p = M @ Vector(c)
            q = (M.to_3x3() @ Euler(rot).to_matrix()).to_euler()
            items.append((p, r, tuple(q)))
    for i in range(8):
        a = rng.uniform(0, 6.28); r_ = rng.uniform(0.2, 0.9)
        x, y = math.cos(a) * 0.5 * r_, math.sin(a) * 0.42 * r_
        loc, nrm = surf(x, y)
        M = Matrix.Translation((x, y, loc.z + 0.01)) @ Matrix.Rotation(rng.uniform(0, 6.28), 4, 'Z') @ Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, 'X')
        for c, r, rot in rib(rng, rng.uniform(0.1, 0.15), rng.uniform(90, 130), 0.009):
            p = M @ Vector(c)
            q = (M.to_3x3() @ Euler(rot).to_matrix()).to_euler()
            items.append((p, r, tuple(q)))
    bones = blobs(items, 2, "bones")
    remesh(bones, 0.0035)
    surface(bones, BONE_LAYERS, seed=92)
    keep_side(bones, (0, 0, -0.04), (0, 0, -1))
    bm_ = paint("bones_b", BONE_DARK, moss=0.2, moss_color=MOSS_DEAD, dirt=0.0, streaks=0.3, ao=0.1, edge=0.6, cavity=1.0, cracks=0.3, hue_var=0.5)
    blotch(bm_, (0.32, 0.24, 0.13), 6, 0.5)
    dirt_low(bm_, 0.0, 0.16, 0.7)
    set_mat(bones, bm_)
    # 해골 넷 (하나를 만들어 돌려 놓는다)
    sk = skull_high(rng, jaw_open=8, seed=9, moss=0.15, dirt=0.4)
    sk_low = low_of(sk, 620, -1)
    highs, lows = [mound, bones], [low_of(mound, 700, -0.05), low_of(bones, 3600, -0.04)]
    poses = [((0.04, 0.02), 0.0, -8, 4, 1.05), ((-0.33, -0.2), 35, 10, -25, 0.95), ((0.36, -0.18), -40, -15, 12, 1.0), ((0.12, 0.3), 160, 20, 40, 0.95)]
    for (x, y), yaw, pit, rol, s in poses:
        hit, loc2, n2, i2 = bones.ray_cast((x, y, 2.0), (0, 0, -1))
        loc, nrm = surf(x, y)
        z = max(loc.z, loc2.z if hit else -1.0) + (0.0 if (x, y) == (0.04, 0.02) else -0.02)
        M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(R(yaw), 4, 'Z') @ Matrix.Rotation(R(pit), 4, 'X') @ Matrix.Rotation(R(rol), 4, 'Y') @ Matrix.Diagonal((s, s, s, 1))
        h = copy(sk); h.data.transform(M); highs.append(h)
        l_ = copy(sk_low); l_.data.transform(M); lows.append(l_)
    delete(sk); delete(sk_low); delete(src)
    return finish("bone_pile", highs, lows, size=1024, extr=0.025)

def candles():
    """녹아내린 양초 무리가 놓인 돌 (~0.5m): 촛농이 흘러 돌 가장자리까지 넘치고, 불꽃은 보랏빛 영혼 불꽃"""
    rng = random.Random(1010)
    st = bm_box(0.48, 0.36, 0.14, TR((0, 0, 0.055)))
    stone_blk(st, rng, (3, 5), (0.02, 0.05), (2, 3), 0.006)
    stone = obj_bm(st, "stone")
    chip(stone, rng, 10, (0.02, 0.045), bite=0.38)
    cut(stone, [chunk((0.24, -0.18, 0.13), (0.05, 0.05, 0.04), rng, 7)])
    sculpt(stone, 0.003, STONE_LAYERS(0.6, wear=1.2), seed=101)
    sm = stone_mat("cstone", 'stone', moss=0.6, low_moss=0.7, mz=0.08)
    set_mat(stone, sm)
    top = 0.125
    cdl = [(-0.12, 0.05, 0.034, 0.3), (0.0, 0.09, 0.03, 0.22), (0.1, -0.01, 0.038, 0.16), (-0.03, -0.07, 0.026, 0.12),
           (0.17, 0.09, 0.022, 0.09), (-0.19, -0.07, 0.028, 0.075)]
    items = []
    bodies = []
    wicks = []
    flames = []
    for i, (x, y, r, h) in enumerate(cdl):
        zt = top + h
        prof = [(r * 1.02, top - 0.01)]
        for k in range(1, 6):
            prof.append((r * rng.uniform(0.95, 1.05), top + h * k / 6))
        prof += [(r * 1.04, zt), (r * 0.98, zt + 0.004), (r * 0.65, zt - 0.006), (r * 0.25, zt - 0.012), (0.0, zt - 0.013)]
        bm = lathe(prof, 16, Matrix.Translation((x, y, 0)))
        for v in bm.verts:     # 들쭉날쭉 녹은 테두리
            if v.co.z > zt - 0.001:
                v.co.z += rng.uniform(-0.008, 0.012)
        bodies.append(obj_bm(bm, "candle"))
        for k in range(rng.randint(3, 5)):
            a = rng.uniform(0, 6.28)
            Ld = rng.uniform(0.25, 0.8) * h
            n = 6
            pts, rad = [], []
            for j in range(n + 1):
                t = j / n
                rr = r + 0.003 + 0.002 * math.sin(t * 9 + k)
                pts.append((x + math.cos(a + 0.05 * math.sin(t * 6)) * rr, y + math.sin(a + 0.05 * math.sin(t * 6)) * rr, zt + 0.004 - Ld * t))
                rad.append(0.0045 + 0.002 * t + (0.0035 if j == n else 0))
            items += tube_items(pts, rad, 0.5)
        items.append(((x, y, top + 0.004), (r * 1.7, r * 1.6, 0.009)))      # 밑동에 고인 촛농
        wk = []
        for j in range(4):
            t = j / 3
            wk.append((x + 0.004 * t * t, y, zt - 0.01 + 0.022 * t))
        wicks += tube_items(wk, [0.0022] * 4, 0.6)
        if i != 5:   # 가장 짧은 초 하나는 꺼져 있다
            flames.append(flame((x + 0.004, y, zt + 0.012), 0.05 + 0.015 * (h > 0.15), 0.011, (rng.uniform(-0.006, 0.006), rng.uniform(-0.004, 0.004))))
    # 돌 가장자리로 흘러넘친 촛농 두 줄기
    for (x0, y0), (x1, y1) in (((-0.12, 0.05), (-0.235, 0.08)), ((0.1, -0.01), (0.12, -0.175))):
        pts = [(x0, y0, top + 0.004), ((x0 + x1) / 2, (y0 + y1) / 2, top + 0.002), (x1, y1, top - 0.004)]
        dvec = Vector((x1 - x0, y1 - y0, 0)).normalized()
        pts += [(x1 + dvec.x * 0.008, y1 + dvec.y * 0.008, top - 0.04), (x1 + dvec.x * 0.01, y1 + dvec.y * 0.01, top - 0.075)]
        items += tube_items(pts, [0.008, 0.007, 0.006, 0.005, 0.0075], 0.5, squash=(1.0, 0.6))
    # 쓰러진 토막 초
    fb = lathe([(0.02, 0.0), (0.021, 0.05), (0.0, 0.052)], 14, Matrix.Translation((0.13, 0.12, top + 0.02)) @ Matrix.Rotation(R(84), 4, 'Y') @ Matrix.Rotation(R(30), 4, 'X'))
    bodies.append(obj_bm(fb, "fallen"))
    drips = blobs(items, 2, "drips")
    wax = join(bodies + [drips])
    remesh(wax, 0.002)
    surface(wax, [{'t': 'lumps', 'scale': 30, 'amp': 0.0012}, {'t': 'lumps', 'scale': 90, 'amp': 0.0004}], seed=102)
    wm = paint("wax", WAX, moss=0.0, dirt=0.0, streaks=0.15, ao=0.03, edge=0.5, cavity=0.7, cracks=0.0, hue_var=0.3, grain_bump=0.3)
    dirt_low(wm, top - 0.01, top + 0.03, 0.35, (0.08, 0.06, 0.07))
    set_mat(wax, wm)
    wick = blobs(wicks, 2, "wick")
    remesh(wick, 0.0012)
    set_mat(wick, paint("wick", ((0.01, 0.008, 0.01), (0.03, 0.025, 0.03), (0.08, 0.06, 0.07)), moss=0, dirt=0, streaks=0, cracks=0))
    lows = [low_of(stone, 1000, -0.02), low_of(wax, 1900, -1), low_of(wick, 120, -1)]
    return finish("candles", [stone, wax, wick], lows, extras=flames, size=1024, extr=0.012)

def skull():
    """해골 하나 (흩뿌리기용)"""
    rng = random.Random(77)
    s = skull_high(rng, jaw_open=7, seed=3, moss=0.25, dirt=0.6, hole=True)
    # 땅에 살짝 기울어 앉은 자세 + 크기 (길이 ~0.23m)
    s.data.transform(Matrix.Rotation(R(-6), 4, 'X') @ Matrix.Rotation(R(8), 4, 'Y') @ Matrix.Diagonal((1.15, 1.15, 1.15, 1)))
    zmin = min(v.co.z for v in s.data.vertices)
    s.data.transform(Matrix.Translation((0, 0, -zmin - 0.006)))
    low = low_of(s, 2600, -0.004)
    return finish("skull", [s], [low], size=1024, extr=0.02)


BUILDERS = [
    ("grave_slab_a", grave_slab_a),
    ("grave_slab_b", grave_slab_b),
    ("grave_slab_c", grave_slab_c),
    ("grave_cross", grave_cross),
    ("grave_obelisk", grave_obelisk),
    ("grave_tomb", grave_tomb),
    ("grave_sunken", grave_sunken),
    ("coffin", coffin),
    ("bone_pile", bone_pile),
    ("candles", candles),
    ("skull", skull),
]

_SOUL = [0.62, 0.35, 1.0]
META = {
    "grave_slab_a": {"kind": "prop", "tags": ["grave"], "collider": "box", "footprint": 0.6, "sink": 0.03, "tilt": 8,
                     "align": False, "scale": [0.9, 1.2], "cull": 0.015, "shadows": True},
    "grave_slab_b": {"kind": "prop", "tags": ["grave"], "collider": "box", "footprint": 0.75, "sink": 0.03, "tilt": 6,
                     "align": False, "scale": [0.9, 1.15], "cull": 0.015, "shadows": True},
    "grave_slab_c": {"kind": "prop", "tags": ["grave"], "collider": "box", "footprint": 0.6, "sink": 0.03, "tilt": 6,
                     "align": False, "scale": [0.9, 1.15], "cull": 0.012, "shadows": True},
    "grave_cross": {"kind": "prop", "tags": ["grave"], "collider": "box", "footprint": 0.6, "sink": 0.03, "tilt": 5,
                    "align": False, "scale": [0.9, 1.15], "cull": 0.012, "shadows": True},
    "grave_obelisk": {"kind": "prop", "tags": ["grave"], "collider": "box", "footprint": 0.8, "sink": 0.04, "tilt": 3,
                      "align": False, "scale": [0.9, 1.2], "cull": 0.008, "shadows": True},
    "grave_tomb": {"kind": "prop", "tags": ["grave", "light"], "collider": "box", "footprint": 1.3, "sink": 0.04, "tilt": 2,
                   "align": False, "scale": [0.95, 1.1], "cull": 0.008, "shadows": True,
                   "light": {"offset": [-0.72, 0.0, 0.82], "color": _SOUL, "intensity": 3, "range": 4}},
    "grave_sunken": {"kind": "prop", "tags": ["grave"], "collider": "box", "footprint": 0.75, "sink": 0.0, "tilt": 4,
                     "align": True, "scale": [0.85, 1.2], "cull": 0.015, "shadows": True},
    "coffin": {"kind": "prop", "tags": ["grave"], "collider": "box", "footprint": 1.1, "sink": 0.02, "tilt": 3,
               "align": True, "scale": [0.95, 1.1], "cull": 0.012, "shadows": True},
    "bone_pile": {"kind": "prop", "tags": ["bone"], "collider": "mesh", "footprint": 0.65, "sink": 0.03, "tilt": 5,
                  "align": True, "scale": [0.8, 1.25], "cull": 0.012, "shadows": True},
    "candles": {"kind": "scatter", "tags": ["light", "grave"], "collider": "none", "footprint": 0.3, "sink": 0.02, "tilt": 4,
                "align": True, "scale": [0.85, 1.2], "cull": 0.03, "shadows": True,
                "light": {"offset": [0.0, 0.02, 0.42], "color": _SOUL, "intensity": 2.5, "range": 4}},
    "skull": {"kind": "scatter", "tags": ["bone"], "collider": "none", "footprint": 0.2, "sink": 0.01, "tilt": 15,
              "align": True, "scale": [0.85, 1.15], "cull": 0.04, "shadows": True},
}

PREVIEWS = [("all", [n for n, _ in BUILDERS], False)] + [(n, [n], True) for n, _ in BUILDERS]
