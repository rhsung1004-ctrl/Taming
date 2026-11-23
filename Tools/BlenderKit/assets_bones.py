# 용의 무덤 뼈 묶음 (bones)
#   용 두개골, 갈비뼈 아치, 가시 척추, 땅에서 솟은 발톱, 뼈 가시, 흩어진 뼈
#
# 만드는 방식
#   - 뼈는 경로를 따라 겹친 타원구(구슬)를 리메시로 녹여 만든다 (bone_tube). 단면 방향을 경로마다 직접 정해서
#     갈비뼈는 납작한 띠, 턱뼈는 높고 얇은 판이 된다. 관절 끝에는 혹(관절 머리·두 갈래 관절구)을 붙인다.
#   - 녹인 뒤 살짝 다듬어(soften) 이음매를 부드럽게 하고, 창(두개골의 뚫린 곳)·부러진 단면·금을 판다.
#     부러진 단면 = 울퉁불퉁한 단면 커터 + 골수 구멍 + 해면처럼 숭숭 뚫린 잔구멍 (break_cutters)
#     금 = 표면을 따라 구불구불 이어지는 V자 홈 (crack_cutters)
#   - 다시 리메시한 뒤 kit.surface 로 겹겹이 벗겨진 겉뼈, 자연스러운 금, 잔구멍을 새기고,
#     뼈 결 방향(Guide)으로 길게 갈라진 금(bark 층)을 낸다. 뿔·발톱은 성장 고리(ring_ridges)를 더한다.
#   - 칠: 'bone' 팔레트 + 누렇게 밴 얼룩 + 보랏빛 그늘 얼룩 + 긴 빗물 자국 + 아래쪽 흙물 + 약간의 이끼.
#     뿔·발톱은 어두운 각질색 (HORN). 눈구멍 깊은 곳의 불씨는 Glow_Soul.
#   - 도우미 일부는 assets_graves.py·assets_landmarks.py·assets_nature.py 에서 가져와 이 묶음 안에 둔다
#     (다른 묶음 파일이 바뀌어도 영향이 없게).
import math, random, os
import bpy, bmesh
from mathutils import Vector, Matrix, Euler, Quaternion
from mathutils import noise as mnoise
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
import kit
from kit import *

# kit.load_fbx 는 FBX 에서 함께 들어온 "Foliage"·"Glow_*" 재질을 진짜 재질로 착각해 미리보기에서 잎이 하얗게,
# 발광이 꺼져 보인다 (kit 버그). 묶음을 읽을 때 진짜 재질을 먼저 만들어 두어 피한다 (내보내는 파일에는 영향 없음).
if kit.sc is not None:
    foliage_mat()
    for _g in GLOW:
        glow_mat(_g)

R = math.radians
SOUL = [0.62, 0.35, 1.0]
IVY_COL = (0.09, 0.2, 0.15)
BONE = PAL['bone']
HORN = ((0.028, 0.024, 0.032), (0.16, 0.14, 0.145), (0.4, 0.37, 0.36))      # 뿔·발톱 각질 (어둡게, 닳은 끝은 밝게)


# ───────────────────────── bmesh·객체 도우미 ─────────────────────────
def TR(loc=(0, 0, 0), rot=(0, 0, 0), s=None):
    M = Matrix.Translation(Vector(loc)) @ Euler(rot, 'XYZ').to_matrix().to_4x4()
    if s is not None:
        if not isinstance(s, (tuple, list)):
            s = (s, s, s)
        M = M @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))
    return M

def obj_bm(bm, name="part", M=None):
    if M is not None:
        bm.transform(M)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    kit.sc.collection.objects.link(o)
    return o

def _rotm(rot):
    if isinstance(rot, Quaternion):
        return rot.to_matrix()
    if isinstance(rot, Matrix):
        return rot.to_3x3()
    return Euler(rot, 'XYZ').to_matrix()

def blobs(items, sub=2, name="blobs"):
    """겹친 타원구들 (리메시하면 한 덩어리로 녹는다). items: [(중심, (rx,ry,rz) 또는 r, 회전(오일러·행렬·쿼터니언)), ...]"""
    bm = bmesh.new()
    for it in items:
        c, r = it[0], it[1]
        rot = it[2] if len(it) > 2 else (0, 0, 0)
        if not isinstance(r, (tuple, list)):
            r = (r, r, r)
        g = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
        M = Matrix.Translation(Vector(c)) @ _rotm(rot).to_4x4() @ Matrix.Diagonal((r[0], r[1], r[2], 1.0))
        bmesh.ops.transform(bm, matrix=M, verts=g['verts'])
    return obj_bm(bm, name)

def ell(c, radii, axis=(0, 0, 1), spin=0.0, sub=2, name="ell"):
    """긴 축(z 반지름)이 axis 를 향한 타원구 객체 (커터용)"""
    q = Vector(axis).normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4() @ Matrix.Rotation(spin, 4, 'Z')
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    M = Matrix.Translation(Vector(c)) @ q @ Matrix.Diagonal((radii[0], radii[1], radii[2], 1.0))
    bm.transform(M)
    return obj_bm(bm, name)

def xform(o, M):
    o.data.transform(M)
    o.data.update()
    return o

def soften(o, factor=0.5, repeat=3):
    """리메시로 녹인 이음매의 날카로운 골을 살짝 다듬는다"""
    m = o.modifiers.new('sm', 'SMOOTH')
    m.factor = factor
    m.iterations = repeat
    apply_all(o)
    return o

def open_edges(o):
    bm = bmesh.new(); bm.from_mesh(o.data)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n

def cut_safe(a, cutters, voxel=0.02):
    """kit.cut 이 닫히지 않은 메쉬를 돌려주면 원본을 리메시해 닫은 뒤 다시 판다 (assets_landmarks.py 와 같은 방식)"""
    flat = [c for c in cutters if c is not None]
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
    print("CUT retry", a.name, "열린 모서리", bad)
    old = a.data
    a.data = backup.data
    delete(backup)
    bpy.data.meshes.remove(old)
    remesh(a, voxel)
    kit.cut(a, spare)
    print("CUT retry result", a.name, open_edges(a))
    return a

def drop_below(o, z=-0.03):
    bm = bmesh.new(); bm.from_mesh(o.data)
    kill = [f for f in bm.faces if all(v.co.z < z for v in f.verts)]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o

def keep_above(o, z):
    """z 아래를 잘라 버린다 (땅속 부분 정리, 열린 메쉬가 된다 — 굽기 원본용)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, z), plane_no=(0, 0, -1), clear_outer=True)
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o

def low_of(high, tris, z=-0.05, floor=28):
    """저폴리: 땅속 면을 지우고, 떨어진 조각마다 보이는 넓이에 비례해 삼각형을 나눠 준다 (작은 조각이 뭉개지지 않게)"""
    c = copy(high)
    drop_below(c, z)
    drop_specks(c, 60)
    _t("low_of %s: %d tris" % (high.name, tri_count(c)))
    act(c)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    parts = list(bpy.context.selected_objects)
    keep = []
    for o in parts:
        a = sum(p.area for p in o.data.polygons)
        if a > 3e-4:
            keep.append((o, a))
        else:
            delete(o)
    A = sum(a for _, a in keep) or 1.0
    for o, a in keep:
        t = max(floor, int(tris * a / A))
        n = tri_count(o)
        if n > t:
            m = o.modifiers.new('dec', 'DECIMATE')
            m.ratio = t / n
            m.use_collapse_triangulate = True
            apply_all(o)
    low = join([o for o, _ in keep])
    for p in low.data.polygons:
        p.use_smooth = True
    _t("low_of %s: 조각 %d → %d tris" % (high.name, len(keep), tri_count(low)))
    return low


# ───────────────────────── 경로·뼈 관 ─────────────────────────
def spline(ctrl, n=24):
    """Catmull-Rom 곡선으로 매끈하게 다시 뽑는다"""
    P = [Vector(p) for p in ctrl]
    m = len(P) - 1
    out = []
    for i in range(n + 1):
        u = i / n * m
        k = min(int(u), m - 1)
        t = u - k
        p0, p1, p2, p3 = P[max(k - 1, 0)], P[k], P[k + 1], P[min(k + 2, m)]
        t2, t3 = t * t, t * t * t
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    return out

def resample(vals, n):
    m = len(vals) - 1
    out = []
    for i in range(n + 1):
        u = i / n * m
        k = min(int(u), m - 1)
        t = u - k
        out.append(vals[k] * (1 - t) + vals[k + 1] * t)
    return out

def bezier(p0, p1, p2, p3, n=30):
    P = [Vector(p) for p in (p0, p1, p2, p3)]
    out = []
    for i in range(n + 1):
        t = i / n
        a = 1 - t
        out.append(P[0] * a * a * a + P[1] * 3 * a * a * t + P[2] * 3 * a * t * t + P[3] * t * t * t)
    return out

def frames(pts, ref=(1, 0, 0)):
    """경로 각 점의 방향 (Z = 진행 방향, X = ref 쪽). 이어지게 ref 를 넘겨 가며 뒤집힘을 막는다"""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    out = []
    ref = Vector(ref)
    for i in range(n):
        t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        t = t.normalized() if t.length > 1e-9 else Vector((0, 0, 1))
        x = ref - t * ref.dot(t)
        if x.length < 1e-4:
            x = t.orthogonal()
        x.normalize()
        y = t.cross(x)
        out.append(Matrix((x, y, t)).transposed().to_quaternion())
        ref = x
    return out

def bone_tube(pts, radii, squash=(1.0, 1.0), step=0.45, ref=(1, 0, 0), wobble=0.0, seed=0):
    """경로를 따라 겹친 타원구 (뼈대). radii: 점마다 반지름(진행 방향), squash: 단면 (X 쪽, Y 쪽) 배율 — 점마다 줄 수도 있다"""
    pts = [Vector(p) for p in pts]
    n_ = len(pts)
    if not isinstance(radii, (list, tuple)):
        radii = [radii] * n_
    if not isinstance(squash[0], (list, tuple)):
        squash = [squash] * n_
    Q = frames(pts, ref)
    out = []
    for i in range(n_ - 1):
        a, b = pts[i], pts[i + 1]
        ra, rb = radii[i], radii[i + 1]
        L = (b - a).length
        n = max(1, int(math.ceil(L / max(1e-3, min(ra, rb) * step))))
        for k in range(n + (1 if i == n_ - 2 else 0)):
            t = k / n
            r = ra + (rb - ra) * t
            sx = squash[i][0] + (squash[i + 1][0] - squash[i][0]) * t
            sy = squash[i][1] + (squash[i + 1][1] - squash[i][1]) * t
            q = Q[i].slerp(Q[i + 1], t)
            w = 1.0
            p = a.lerp(b, t)
            if wobble > 0:
                w = 1.0 + wobble * mnoise.noise(p * 2.5 + Vector((seed * 3.1, 0, 0)))
            out.append((p, (r * sx * w, r * sy * w, r), q))
    return out

def spike(base, direction, length, r0, bend=(0, 0, 0), tip=0.1, n=8, squash=(1.0, 1.0)):
    """가시·뿔 하나 (기울어 휘는 원뿔). 돌아오는 것: (구슬 목록, 경로 점)"""
    base = Vector(base); d = Vector(direction).normalized(); bend = Vector(bend)
    pts = [base + d * (length * i / n) + bend * (length * (i / n) ** 2) for i in range(n + 1)]
    rad = [max(r0 * tip, r0 * (1 - i / n) ** 0.85) for i in range(n + 1)]
    return bone_tube(pts, rad, squash, 0.4), pts

class Guide:
    """뼈 결 방향 안내 (kit.surface 의 bark 층이 가장 가까운 점의 'dir' 방향으로 금을 길게 늘인다)"""
    def __init__(self):
        self.p, self.d = [], []

    def add(self, pts, M=None):
        pts = [Vector(p) for p in pts]
        if M is not None:
            pts = [M @ p for p in pts]
        n = len(pts)
        for i in range(n):
            t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
            if t.length < 1e-9:
                continue
            self.p.append(pts[i].copy())
            self.d.append(t.normalized())

    def obj(self):
        me = bpy.data.meshes.new("guide")
        me.from_pydata([tuple(p) for p in self.p], [], [])
        a = me.attributes.new("dir", 'FLOAT_VECTOR', 'POINT')
        for i, d in enumerate(self.d):
            a.data[i].vector = d
        return link(bpy.data.objects.new("guide", me))


# ───────────────────────── 커터 (부러진 단면, 금, 구멍) ─────────────────────────
def rough_cutter(co, no, w=2.0, h=2.0, amp=0.03, freq=5.0, res=26, depth=3.0, seed=0, steps=3.0):
    """울퉁불퉁한(계단진) 단면 커터: co 를 지나는 면에서 no 쪽 depth 만큼 (assets_graves.py 와 같다)"""
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

def break_cutters(p, n, r, rng, seed=0, pores=24, cavity=0.45, amp=0.32, span=4.0, depth=6.0):
    """부러진 뼈 단면: p 를 지나는 면에서 n 쪽을 떼어 내고, 가운데 골수 구멍과 둘레의 해면 같은 잔구멍을 판다 (r: 뼈 반지름)"""
    p = Vector(p); n = Vector(n).normalized()
    t1 = n.orthogonal().normalized(); t2 = n.cross(t1)
    cs = [rough_cutter(p, n, r * span, r * span, r * amp, 1.7 / r, 22, r * depth, seed, 3.0)]
    if cavity > 0:
        cs.append(ell(p - n * (r * 0.15), (r * cavity, r * cavity * 0.8, r * 0.85), n, rng.uniform(0, 6.28), 2, "marrow"))
    for i in range(pores):
        a = rng.uniform(0, 6.28)
        rr = r * (0.25 + 0.55 * math.sqrt(rng.random()))
        c = p + t1 * (math.cos(a) * rr) + t2 * (math.sin(a) * rr) - n * rng.uniform(-0.05, 0.12) * r
        s = r * rng.uniform(0.07, 0.15)
        ax = (n + t1 * rng.uniform(-0.4, 0.4) + t2 * rng.uniform(-0.4, 0.4)).normalized()
        cs.append(ell(c, (s, s * rng.uniform(0.6, 1.0), s * rng.uniform(1.6, 3.0)), ax, rng.uniform(0, 6.28), 1, "pore"))
    return cs

def surf_bvh(o):
    bm = bmesh.new(); bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t

def vgroove(a, b, nrm, w, dep):
    """두 점 사이를 잇는 V자 홈 커터 (마름모 단면)"""
    a, b = Vector(a), Vector(b)
    x = (b - a).normalized()
    z = Vector(nrm)
    z = (z - x * z.dot(x))
    z = z.normalized() if z.length > 1e-6 else x.orthogonal().normalized()
    y = z.cross(x)
    A, B = a - x * (w * 0.6), b + x * (w * 0.6)
    top = max(dep * 0.5, w)
    verts = []
    for P in (A, B):
        verts += [P + z * top, P + y * (w / 2), P - z * dep, P - y * (w / 2)]
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return mesh_from("crack", verts, faces)

def crack_cutters(bvh, start, direction, length, width, depth, rng, segs=8, wander=0.5, branch=0.35):
    """표면을 따라 구불구불 이어지는 금 (V자 홈). 가운데가 넓고 깊다. 가끔 곁가지"""
    hit = bvh.find_nearest(Vector(start))
    if hit[0] is None:
        return []
    p, nr = hit[0], hit[1]
    d = Vector(direction)
    pts = [(p, nr)]
    step = length / segs
    for i in range(segs):
        dt = d - nr * d.dot(nr)
        if dt.length < 1e-5:
            break
        dt.normalize()
        dt = Matrix.Rotation(rng.uniform(-wander, wander), 3, nr) @ dt
        q = p + dt * step * rng.uniform(0.75, 1.25)
        h2 = bvh.find_nearest(q)
        if h2[0] is None:
            break
        d = (h2[0] - p).normalized() * 0.6 + d.normalized() * 0.4
        p, nr = h2[0], h2[1]
        pts.append((p, nr))
    cs = []
    L = len(pts)
    for i in range(L - 1):
        k = math.sin(math.pi * (i + 0.5) / (L - 1))
        (a, na), (b, nb) = pts[i], pts[i + 1]
        cs.append(vgroove(a, b, (na + nb), width * (0.3 + 0.7 * k), depth * (0.35 + 0.65 * k)))
        if branch > 0 and 0 < i < L - 2 and rng.random() < branch:
            side = (na.cross(b - a)).normalized() * (1 if rng.random() < 0.5 else -1)
            cs += crack_cutters(bvh, a, (b - a).normalized() * 0.5 + side, length * 0.3, width * 0.6, depth * 0.6, rng, 3, wander, 0.0)
    return cs

def surf_pores(bvh, center, radius, n, size, rng, depth=2.2):
    """한 점 둘레 표면에 숭숭 뚫린 구멍 (깨진 구멍 가장자리의 해면뼈)"""
    cs = []
    center = Vector(center)
    for i in range(n):
        v = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if v.length < 1e-3:
            continue
        q = center + v.normalized() * radius * rng.uniform(0.8, 1.15)
        h = bvh.find_nearest(q)
        if h[0] is None:
            continue
        s = size * rng.uniform(0.6, 1.3)
        cs.append(ell(h[0] - h[1] * s * 0.3, (s, s * rng.uniform(0.6, 1.0), s * depth), h[1], rng.uniform(0, 6.28), 1, "pore"))
    return cs


# ───────────────────────── 표면 조각 ─────────────────────────
def BONE_BIG(k=1.0, crack=0.55, flake=0.5, wear=1.0):
    """큰 뼈의 풍화 (k: 크기 배율, 1 = 지름 0.5m 안팎의 뼈, wear: 깊이 배율). 겹겹이 벗겨진 겉뼈, 자연스러운 금, 숭숭한 잔구멍"""
    w = wear
    return [
        {'t': 'lumps', 'scale': 0.8 / k, 'amp': 0.025 * k},
        {'t': 'lumps', 'scale': 2.6 / k, 'amp': 0.007 * k * w},
        {'t': 'terrace', 'scale': 1.5 / k, 'steps': 3, 'amp': 0.014 * k * w, 'cover': flake, 'cover_scale': 0.9 / k},
        {'t': 'terrace', 'scale': 4.2 / k, 'steps': 3, 'amp': 0.005 * k * w, 'cover': 0.6},
        {'t': 'fissure', 'scale': 1.0 / k, 'width': 0.012, 'depth': 0.03 * k * w, 'cover': crack, 'cover_scale': 0.8 / k},
        {'t': 'fissure', 'scale': 3.0 / k, 'width': 0.01, 'depth': 0.01 * k * w, 'cover': crack},
        {'t': 'pits', 'scale': 11.0 / k, 'depth': 0.011 * k * w, 'cover': 0.5},
        {'t': 'pits', 'scale': 32.0 / k, 'depth': 0.004 * k * w, 'cover': 0.65},
        {'t': 'grain', 'scale': 70.0 / k, 'amp': 0.0012 * k},
    ]

def BONE_SPLIT(k=1.0):
    """뼈 결을 따라 길게 갈라진 금 (guide 필요)"""
    return {'t': 'bark', 'scale': 2.2 / k, 'width': 0.045, 'depth': 0.018 * k, 'stretch': 0.1}

def ring_ridges(o, paths, period, amp, seed=0, fade_tip=0.15, sharp=True, jitter=0.35):
    """뿔·발톱의 성장 고리: 경로를 따라 일정한 간격으로 턱진 고리 (천천히 솟고 뚝 떨어지는 톱니 모양).
    paths: 경로 목록 (각 정점은 가장 가까운 경로를 따른다). 경로 끝(뾰족한 쪽)으로 갈수록 옅어진다."""
    if paths and not isinstance(paths[0], (list, tuple)):
        paths = [paths]
    dense, s_of, tot_of = [], [], []
    for path in paths:
        pts = [Vector(p) for p in path]
        acc = 0.0
        start = len(dense)
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L = (b - a).length
            n = max(1, int(L / 0.01))
            for k in range(n):
                dense.append(a.lerp(b, k / n)); s_of.append(acc + L * k / n)
            acc += L
        dense.append(pts[-1]); s_of.append(acc)
        tot_of += [acc] * (len(dense) - start)
    kd = KDTree(len(dense))
    for i, p in enumerate(dense):
        kd.insert(p, i)
    kd.balance()
    me = o.data
    me.update()
    _t("성장 고리 %d 정점" % len(me.vertices))
    off = Vector((seed * 7.3, seed * 1.9, seed * 4.1))
    for v in me.vertices:
        co, idx, dist = kd.find(v.co)
        s = s_of[idx]
        f = s / max(1e-6, tot_of[idx])
        ph = s / period + jitter * mnoise.noise(v.co * (0.8 / period) + off)
        amp_k = 0.6 + 0.4 * mnoise.noise(v.co * (0.3 / period) + off * 2.0)
        fr = ph - math.floor(ph)
        prof = (fr ** 2.2 - 0.3) if sharp else math.sin(fr * 6.283) * 0.5
        fade = min(1.0, (1.0 - f) / max(1e-3, fade_tip)) ** 1.5
        v.co += v.normal * (amp * amp_k * prof * fade)
    me.update()
    return o


# ───────────────────────── 칠 (kit.paint 뒤에 얹는다) ─────────────────────────
def _final_color(mat):
    b = mat.node_tree.nodes["Principled BSDF"]
    return b, b.inputs['Base Color'].links[0].from_socket

def moss_low(mat, z0=0.0, z1=0.3, amount=0.8, color=MOSS, scale=3.5):
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(P, sep.inputs[0])
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
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    m = kit._mul(nt, kit._ramp(nt, kit._noise(nt, P, scale, 6, 0.6), lo, W((0, 0, 0)), hi, W((1, 1, 1))), amount)
    out = kit._mix(nt, mode, m, col, W(tuple(min(1.0, c * 2.2) for c in color)) if mode == 'MULTIPLY' else W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat

def streaks_big(mat, scale=1.2, length=0.12, amount=0.55, color=(0.3, 0.28, 0.4)):
    """세로로 길게 늘인 빗물 자국 (큰 물체용)"""
    nt = mat.node_tree
    b, col = _final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (scale * 8, scale * 8, length)
    nt.links.new(P, mp.inputs['Vector'])
    st = kit._ramp(nt, kit._noise(nt, mp.outputs['Vector'], 3.0, 4), 0.48, W((0, 0, 0)), 0.72, W((1, 1, 1)))
    m = kit._mul(nt, st, amount)
    out = kit._mix(nt, 'MULTIPLY', m, col, W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat

def bone_mat(name, k=1.0, moss=0.2, pal=None, stain=0.6, dirt_h=0.45, moss_h=0.5, streak=0.4, ao=None, edge=0.75, cracks=0.4):
    """오래된 뼈: 상아색 바탕 + 누렇게 밴 얼룩 + 보랏빛 그늘 얼룩 + 빗물 자국 + 아래쪽 흙물·이끼"""
    m = paint(name, pal or BONE, moss=moss, moss_color=MOSS, dirt=0.0, streaks=0.0, ao=ao if ao is not None else 0.22 * k,
              edge=edge, cavity=1.0, grain_bump=0.7, cracks=cracks, hue_var=0.45)
    blotch(m, (0.37, 0.29, 0.16), 1.6 / k, stain, 0.45, 0.63)
    blotch(m, (0.3, 0.28, 0.42), 0.9 / k, 0.45, 0.5, 0.66)
    if streak > 0:
        streaks_big(m, 1.0 / k, 0.12 / k, streak, (0.36, 0.33, 0.4))
    if dirt_h > 0:
        dirt_low(m, -0.3, dirt_h, 0.85, (0.05, 0.042, 0.05))
    if moss_h > 0:
        moss_low(m, 0.0, moss_h, 0.6, scale=1.4 / k)
    return m

def horn_mat(name, k=1.0, moss=0.1, dirt_h=0.3):
    m = paint(name, HORN, moss=moss, moss_color=MOSS, dirt=0.0, streaks=0.0, ao=0.15 * k, edge=0.7, cavity=1.0,
              grain_bump=0.8, cracks=0.3, hue_var=0.35)
    blotch(m, (0.28, 0.24, 0.3), 1.2 / k, 0.4, 0.45, 0.65, 'MIX')
    if dirt_h > 0:
        dirt_low(m, -0.3, dirt_h, 0.8, (0.04, 0.035, 0.04))
    return m


# ───────────────────────── 발광·덩굴 ─────────────────────────
def ember(c, r, rng, name='Glow_Soul', squash=(1.0, 0.8, 1.15)):
    """불씨 (울퉁불퉁한 작은 덩어리)"""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    off = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
    for v in bm.verts:
        k = 1.0 + 0.35 * mnoise.noise(v.co * 1.8 + off)
        v.co = Vector((v.co.x * squash[0], v.co.y * squash[1], v.co.z * squash[2])) * (r * k)
    o = obj_bm(bm, "ember", Matrix.Translation(Vector(c)))
    return glow(o, name)

def ivy_light(target, start, seed, length, max_leaves=200, max_stem=450, **kw):
    """kit.ivy 로 자라게 한 뒤 가볍게 줄인다 (assets_nature.py 와 같은 방식: 갈래·잎 확률을 낮추고 잎 수·줄기 삼각형에 상한)"""
    args = dict(length=length, leaf=0.09, leaf_prob=0.3, branch=0.006, gravity=0.6, adhesion=0.8, color=IVY_COL, dead=0.35,
                stem_radius=0.01, size=0.05)
    args.update(kw)
    parts = ivy(target, start, seed=seed, **args)
    rng = random.Random(seed)
    out = []
    for o in parts:
        if "Leaf" in o.name or "leaf" in o.name:
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

def ivy_on(lows, starts, **kw):
    """저폴리 복사본 위에 덩굴. starts: [(점, 씨앗, 길이), ...]"""
    tgt = join([copy(l) for l in lows])
    tgt.location = (0, 0, 0)
    parts = []
    for p, seed, length in starts:
        _t("덩굴 %d" % seed)
        parts += ivy_light(tgt, p, seed, length, **kw)
    delete(tgt)
    print("IVY tris", sum(tri_count(o) for o in parts))
    return parts

def recenter(objs, extras=()):
    """모든 부품을 바닥 중심이 (0,0) 이 되게 옮긴다"""
    xs, ys = [], []
    for o in objs:
        for v in o.data.vertices:
            if v.co.z > -0.05:
                xs.append(v.co.x); ys.append(v.co.y)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    M = Matrix.Translation((-cx, -cy, 0))
    for o in list(objs) + list(extras):
        xform(o, M)
    return Vector((-cx, -cy, 0))

def drop_specks(o, min_faces=150):
    """리메시·파내기 뒤에 떨어져 떠 있는 부스러기(얇은 끝이 끊긴 조각 등)를 지운다"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    seen = set()
    kill = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]; comp = []; seen.add(f.index)
        while stack:
            g = stack.pop(); comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); stack.append(h)
        if len(comp) < min_faces:
            kill += comp
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data); bm.free(); o.data.update()
    return o

def _t(msg, t0=[None]):
    import time
    now = time.time()
    if t0[0] is None:
        t0[0] = now
    print("T %7.1f  %s" % (now - t0[0], msg), flush=True)

def bone_high(items, M, voxel0, voxel, cut_fn=None, layers=None, guide=None, seed=0, sub=2, smooth=(0.5, 3), name="bone", specks=150):
    """구슬 → 변환 → 거칠게 녹임 → 다듬기 → 파내기(cut_fn 이 커터 목록을 돌려준다) → 고운 리메시 → 조각"""
    _t("%s: 구슬 %d" % (name, len(items)))
    o = blobs(items, sub, name)
    if M is not None:
        xform(o, M)
    remesh(o, voxel0)
    soften(o, *smooth)
    _t("%s: 녹임 %d tris" % (name, tri_count(o)))
    if cut_fn is not None:
        cs = cut_fn(o)
        if cs:
            _t("%s: 커터 %d" % (name, len(cs)))
            cut_safe(o, cs, voxel0)
            _t("%s: 파냄" % name)
    remesh(o, voxel)
    drop_specks(o, specks)
    soften(o, 0.4, 1)
    if layers:
        lay = list(layers)
        g = None
        if guide is not None and any(L['t'] == 'bark' for L in lay):
            g = guide.obj()
        elif any(L['t'] == 'bark' for L in lay):
            lay = [L for L in lay if L['t'] != 'bark']
        kit.surface(o, lay, seed, guide=g)
        if g is not None:
            delete(g)
    _t("%s: 조각 %d tris" % (name, tri_count(o)))
    return o


# ───────────────────────── 굽기·내보내기 (kit.finish 를 이 묶음에 맞게 조금 바꾼 것) ─────────────────────────
# kit.finish 는 줄인 저폴리를 그대로 smart_project 한다. 뼈처럼 가는 관이 많은 유기적인 저폴리는 면 방향이 제각각이라
# 삼각형 두세 장짜리 UV 섬 수천 개로 쪼개져 텍스처 대부분이 빈칸·이음매가 된다 (첫 굽기에서 확인).
# assets_landmarks.py 와 같은 방법으로 피한다: 위상이 같은 복사본을 매끈하게 다듬어 그 위에서 펴고 UV 만 옮긴다.
def unwrap_smoothed(low, uv_angle=70, iters=24, factor=0.5, margin=0.004):
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

def _bake_b(low, highs, kind, extr, margin):
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

DRAFT = os.environ.get("BONES_DRAFT", "") != ""

def _draft(name, objs, views=None, samples=24):
    """초안 확인: 굽지 않고 고폴리(절차 재질 그대로)를 바로 찍는다 (BONES_DRAFT=1 일 때만. 내보내지 않는다)"""
    import preview
    views = (views or os.environ.get("BONES_VIEWS", "fr,side")).split(",")
    sc = kit.sc
    xs, ys, zs = [], [], []
    for o in objs:
        vs = o.data.vertices
        for vi in range(0, len(vs), 7):
            w = o.matrix_world @ vs[vi].co
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs))
    h = max(zs)
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
    g = bpy.context.object
    gm = bpy.data.materials.new("_d_g"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.022, 0.022, 0.03, 1)
    g.data.materials.append(gm)
    wd = bpy.data.worlds.new("_d_w"); sc.world = wd; wd.use_nodes = True
    wd.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.035, 0.07, 1)
    c = Vector((cx, cy, h * 0.4))
    L = [preview._light('SUN', (c.x - 5, c.y - 6, 8), 3.2, (0.78, 0.84, 1.0), c),
         preview._light('AREA', (c.x + span * 0.8 + 2, c.y + span * 0.6 + 2, h * 1.2 + 1), 400 + span * 60, (0.6, 0.35, 1.0), c, size=3),
         preview._light('AREA', (c.x + 2, c.y - span * 0.9 - 4, 1.0), 120 + span * 20, (0.4, 0.55, 0.8), c, size=4)]
    cd = bpy.data.cameras.new("_d_c"); cam = bpy.data.objects.new("_d_cam", cd); sc.collection.objects.link(cam); sc.camera = cam
    sc.cycles.samples = samples
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.view_settings.view_transform = 'Filmic'
    sc.view_settings.look = 'Medium High Contrast'
    sc.render.image_settings.file_format = 'PNG'
    for o in objs:
        o.hide_render = False
    dirs = {'fr': (0.45, -0.9, 0.3), 'fl': (-0.6, -0.8, 0.28), 'side': (-1.0, -0.05, 0.18), 'back': (0.4, 0.9, 0.35), 'top': (0.15, -0.5, 1.0)}
    for v in views:
        if v.startswith('near'):
            px, py, pz = [float(t) for t in v.split(':')[1].split('/')]
            tgt = Vector((px, py, pz)); d = span * 0.33 + 0.4; dv = Vector((0.5, -0.85, 0.3)); cd.lens = 50
        else:
            tgt = Vector((cx, cy, h * 0.45)); d = max(span * 1.25, h * 2.4) + 0.6; dv = Vector(dirs[v]); cd.lens = 40
        cam.location = tgt + dv.normalized() * d
        cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(kit.OUT, "_rv_bones_%s_draft_%s.png" % (name, v.split(':')[0]))
        bpy.ops.render.render(write_still=True)
        print("DRAFT", sc.render.filepath)
    for o in L + [cam, g]:
        delete(o)


def finish_b(name, highs, low_parts, extras=(), size=1024, extr=0.03, lod1=0.35, lod2=None, uv_angle=70, far_extras=None, smooth_uv=24):
    """kit.finish 와 같다. 다른 점: UV 를 매끈한 복사본에서 편다 (unwrap_smoothed),
    마지막 LOD 에는 far_extras(없으면 extras 전부)만 붙인다 (덩굴 잎이 먼 LOD 를 차지하지 않게)."""
    if DRAFT:
        _draft(name, list(highs) + [e for e in extras if e is not None])
        for o in list(highs) + list(low_parts) + [e for e in extras if e is not None]:
            delete(o)
        raise RuntimeError("초안 모드: 내보내지 않음")
    _t("%s: 굽기 시작" % name)
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
    mg = 16 if size <= 1024 else 24
    nt.nodes.active = ta
    _bake_b(low, highs, 'DIFFUSE', extr, mg)
    nt.nodes.active = tn
    _bake_b(low, highs, 'NORMAL', extr, mg)
    _t("%s: 굽기 끝" % name)
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
        L.location = (1000 + len(kit.LOWS) * 40, 1000 + i * 40, 0)
        L.hide_render = True
    kit.LOWS[name] = lods[0]
    return lods[0]


# ───────────────────────── 용 두개골 ─────────────────────────
def _teeth_row(ctrl, rad, side, down, fr, rng, fang_at, fang_L, fang_r, L0, L1, r0, r1, miss_n, out_items, alveoli, sockets, lean_out=0.12):
    """이빨 한 줄: ctrl 경로(턱 가장자리)를 따라 fr 비율 자리마다. down = 이빨이 향하는 쪽 (+1 위, -1 아래)"""
    mp = spline(ctrl, 60); mr = resample(rad, 60)
    miss = set(rng.sample(range(len(fr)), miss_n))
    for j, f in enumerate(fr):
        i = min(60, int(f * 60))
        p, r = mp[i], mr[i]
        root = p + Vector((side * 0.03, 0, down * r * 0.5))
        sockets.append((p + Vector((side * r * 0.42, 0, down * r * 0.62)), r * 0.42))
        if j in miss:
            alveoli.append((root + Vector((0, 0, down * r * 0.3)), r * 0.36))
            continue
        fang = abs(f - fang_at) < 0.045
        L = (fang_L if fang else L0 + (L1 - L0) * rng.random()) * rng.uniform(0.9, 1.1)
        rb = fang_r if fang else r0 + (r1 - r0) * rng.random()
        if not fang and rng.random() < 0.2:
            L *= rng.uniform(0.4, 0.6)                         # 부러진 이
        tilt = Matrix.Rotation(R(rng.uniform(-9, 9)), 3, 'Y') @ Matrix.Rotation(R(rng.uniform(-6, 6)), 3, 'X')
        d = tilt @ Vector((side * lean_out, 0.0, down)).normalized()
        pts = [root + d * (L * t) + Vector((0, 0.2 * L * t * t, 0)) for t in (0, 0.3, 0.6, 0.85, 1.0)]
        out_items += bone_tube(pts, [rb, rb * 0.9, rb * 0.62, rb * 0.32, max(0.012, rb * 0.1)], (1.0, 0.82), 0.4)

def dragon_skull():
    """거대한 용 두개골 (~6.5m): 뒤로 솟아 휜 큰 뿔 둘(오른쪽은 부러져 끝이 옆 땅에 떨어짐), 들쭉날쭉한 볏과 볏 가시,
    무거운 눈썹뼈 아래 깊은 눈구멍(가장 깊은 곳에 보랏빛 불씨), 눈 앞의 큰 창·관자 창, 콧등 용골과 혹, 정수리의 깨진 구멍,
    살짝 벌어진 아래턱(따로 놓인 덩어리), 크고 들쭉날쭉한 이빨(빠지고 부러진 것 몇 개), 뼈 봉합선과 금"""
    rng = random.Random(1201)
    S = 0.86
    it = []
    B = it.append
    # ── 단단한 덩어리 (두개골 좌표: 주둥이 -Y, 이빨 줄 z≈0.55) — 나중에 창·눈구멍을 판다
    B(((0, 1.0, 1.45), (0.8, 0.9, 0.72)))                     # 머리뼈 통
    B(((0, 1.0, 1.9), (0.6, 0.8, 0.4)))                       # 정수리
    B(((0, 0.05, 1.8), (0.78, 0.78, 0.4)))                    # 이마
    B(((0, 1.75, 1.55), (1.18, 0.22, 0.82), (R(-28), 0, 0)))  # 뒤로 젖혀진 볏 판
    B(((0, 1.85, 0.95), (0.24, 0.24, 0.24)))                  # 뒤통수 관절구
    sn_c = [(0, -0.35, 1.25), (0, -1.3, 1.12), (0, -2.2, 0.98), (0, -2.85, 0.86), (0, -3.1, 0.78)]
    sn_r = [0.62, 0.55, 0.45, 0.36, 0.28]
    it += bone_tube(sn_c, sn_r, [(1.38, 1.0), (1.38, 1.0), (1.32, 1.0), (1.2, 1.0), (1.1, 1.0)])     # 주둥이 (속이 찬 쐐기)
    B(((0, -3.14, 0.7), (0.2, 0.18, 0.28)))                   # 아래로 굽은 부리
    # 콧등 용골 + 혹
    keel = [(0, -0.55, 1.86), (0, -1.5, 1.7), (0, -2.35, 1.46), (0, -2.9, 1.18)]
    it += bone_tube(keel, [0.1, 0.09, 0.075, 0.06], (0.55, 1.5))
    kp = spline(keel, 12)
    for j in (2, 5, 8):
        B((kp[j] + Vector((0, 0, 0.06)), (0.08, 0.13, 0.1)))
    # 정수리 용골 (시상 볏)
    it += bone_tube([(0, 0.35, 2.12), (0, 1.1, 2.36), (0, 1.8, 2.34)], [0.09, 0.11, 0.09], (0.5, 1.6))
    max_c, den_c = {}, {}
    for s in (-1, 1):
        B(((s * 0.86, -0.12, 1.86), (0.42, 0.64, 0.22), (0, R(-s * 14), R(s * 10))))   # 무거운 눈썹뼈 (바깥으로 처진 차양)
        B(((s * 0.82, -0.15, 1.3), (0.36, 0.62, 0.56)))                                 # 눈 둘레 덩어리 (눈구멍을 판다)
        B(((s * 0.95, 0.78, 1.08), (0.32, 0.85, 0.5)))                                  # 관자 옆벽 (관자 창을 판다)
        B(((s * 1.1, 0.95, 0.72), (0.24, 0.8, 0.24), (0, 0, R(-s * 4))))                # 광대 판
        B(((s * 1.1, 1.48, 0.62), (0.25, 0.25, 0.3)))                                   # 턱관절
        mc = [(s * 0.86, -0.35, 0.74), (s * 0.76, -1.2, 0.66), (s * 0.58, -2.0, 0.62), (s * 0.36, -2.7, 0.62), (s * 0.14, -3.05, 0.68)]
        max_c[s] = mc
        it += bone_tube(mc, [0.17, 0.16, 0.14, 0.12, 0.1], (0.7, 1.0))                  # 위턱 잇몸 둑 (이빨 줄 가장자리)
        for base, d, L, r0, bend in (((s * 0.25, 2.02, 2.12), (s * 0.15, 0.75, 0.65), 0.7, 0.12, (0, 0.1, -0.15)),    # 볏 가시
                                     ((s * 0.62, 1.98, 2.0), (s * 0.4, 0.75, 0.5), 0.62, 0.11, (0, 0.1, -0.15)),
                                     ((s * 0.98, 1.88, 1.72), (s * 0.7, 0.7, 0.25), 0.5, 0.1, (0, 0.1, -0.1)),
                                     ((s * 1.15, 1.75, 1.3), (s * 0.85, 0.5, -0.05), 0.42, 0.09, (0, 0.1, -0.05)),
                                     ((s * 1.25, 1.25, 0.66), (s * 0.7, 0.55, -0.45), 0.55, 0.12, (0, 0.15, 0)),        # 뺨 가시 (아래로)
                                     ((s * 1.05, 0.25, 1.98), (s * 0.7, 0.6, 0.35), 0.45, 0.1, (0, 0.12, -0.05))):      # 눈썹 가시
            its, _ = spike(base, d, L, r0, bend, 0.12)
            it += its
    # ── 아래턱 (턱 좌표, 관절 (0, 1.45, 0.6))
    jt = []
    for s in (-1, 1):
        dc = [(s * 1.03, 1.55, 0.42), (s * 0.98, 0.8, 0.45), (s * 0.85, -0.2, 0.43), (s * 0.62, -1.2, 0.39), (s * 0.36, -2.15, 0.37), (s * 0.12, -2.85, 0.38)]
        den_c[s] = dc
        jt += bone_tube(dc, [0.34, 0.36, 0.3, 0.25, 0.21, 0.18], (0.42, 1.0))
        jt += bone_tube([(p[0] * 0.97, p[1], p[2] + r * 0.82) for p, r in zip(dc[1:], (0.36, 0.3, 0.25, 0.21, 0.18))], [0.09, 0.085, 0.08, 0.07, 0.06], (0.8, 1.0))   # 잇몸 둑
        jt.append(((s * 0.98, 0.72, 0.8), (0.12, 0.34, 0.28)))                    # 갈고리 돌기
        jt += bone_tube([(s * 1.04, 1.55, 0.45), (s * 1.1, 2.05, 0.52)], [0.18, 0.12])   # 관절 뒤 돌기
        jt.append(((s * 1.06, 1.45, 0.62), (0.21, 0.21, 0.19)))                    # 관절 머리
    jt.append(((0, -2.82, 0.36), (0.32, 0.24, 0.22)))                             # 턱끝
    # ── 자세: 아래턱은 땅에 반쯤 묻혀 살짝 돌아가 있고, 위 두개골은 관절에서 13° 벌어져 조금 비껴 얹혀 있다
    Msc = Matrix.Scale(S, 4)
    Mj = Msc @ Matrix.Translation((0.1, 0.0, -0.2)) @ Matrix.Rotation(R(-4), 4, 'Z') @ Matrix.Rotation(R(4), 4, 'Y')
    hj, hs = Vector((0, 1.45, 0.6)), Vector((0, 1.48, 0.55))
    Ms = Mj @ Matrix.Translation(hj + Vector((0.06, 0.06, 0.05))) @ Matrix.Rotation(R(5), 4, 'Z') @ Matrix.Rotation(R(-3), 4, 'Y') \
        @ Matrix.Rotation(R(-13), 4, 'X') @ Matrix.Translation(-hs)
    # ── 이빨 (따로: 끝이 날카롭게 고운 리메시)
    tt, ltt, alveoli, jalv, sockets, jsockets = [], [], [], [], [], []
    for s in (-1, 1):
        _teeth_row(max_c[s], [0.17, 0.16, 0.14, 0.12, 0.1], s, -1, [0.05 + 0.88 * i / 10 for i in range(11)], rng, 0.8, 0.62, 0.13,
                   0.26, 0.42, 0.075, 0.1, 2, tt, alveoli, sockets)
        dcr = [(p[0] * 0.97, p[1], p[2] + r * 0.82) for p, r in zip(den_c[s], (0.34, 0.36, 0.3, 0.25, 0.21, 0.18))]
        _teeth_row(dcr, [0.09, 0.09, 0.085, 0.08, 0.07, 0.06], s, 1, [0.3 + 0.64 * i / 9 for i in range(10)], rng, 0.9, 0.45, 0.11,
                   0.2, 0.34, 0.065, 0.09, 2, ltt, jalv, jsockets, 0.08)
    for p, r in sockets:
        B((p, (r * 0.8, r * 1.1, r)))                       # 이뿌리 불룩한 자리 (잇몸 둑이 물결진다)
    for p, r in jsockets:
        jt.append((p, (r * 0.8, r * 1.1, r)))
    # ── 뿔 (두개골 좌표). 오른쪽(+X) 뿔은 중간에서 부러졌다
    hi = []
    hguide = Guide()
    hpaths = []
    horn_break = None
    for s in (-1, 1):
        hc = [(s * 0.7, 1.4, 2.05), (s * 0.95, 1.95, 2.62), (s * 1.22, 2.55, 3.05), (s * 1.52, 3.2, 3.25), (s * 1.8, 3.75, 3.15), (s * 1.95, 4.05, 2.95)]
        hr = [0.38, 0.31, 0.24, 0.17, 0.1, 0.04]
        pts = spline(hc, 40); rr = resample(hr, 40)
        if s == 1:
            k = 23
            horn_break = (pts[k - 2], (pts[k - 1] - pts[k - 3]).normalized(), rr[k - 2])
            pts, rr = pts[:k + 1], rr[:k + 1]
        hi += bone_tube(pts, rr, (1.0, 0.85), 0.4, wobble=0.04, seed=s + 5)
        hguide.add(pts, Ms)
        hpaths.append([Ms @ p for p in pts])
    # 부러진 뿔 끝: 두개골 오른쪽 옆 땅에 누워 있다 (월드 좌표). 휘어 끝이 뾰족하다
    fc = [(2.0, 0.55, 0.15), (2.4, 1.15, 0.2), (2.55, 1.8, 0.2), (2.4, 2.35, 0.16), (2.1, 2.7, 0.1)]
    fr_ = [0.16, 0.13, 0.095, 0.055, 0.02]
    fpts = spline(fc, 20); frr = resample(fr_, 20)
    frag_items = bone_tube(fpts, frr, (0.85, 1.0), 0.4, ref=(0, 0, 1))
    hguide.add(fpts)
    hpaths.append(fpts)

    def skull_cuts(o):
        bvh = surf_bvh(o)
        cs = []
        L3 = Ms.to_3x3()

        def E(c, r, axis=(0, 0, 1), spin=0.0, sub=2):
            return ell(Ms @ Vector(c), tuple(v * S for v in r), L3 @ Vector(axis), spin, sub, "c")
        for s in (-1, 1):
            cs.append(E((s * 0.98, -0.16, 1.32), (0.42, 0.52, 0.52), (s * 1, -0.35, 0.1), R(90)))    # 눈구멍 (깊은 사발)
            cs.append(E((s * 0.78, -1.35, 1.0), (0.2, 0.52, 0.42), (s * 1, 0, 0.12), 0))             # 눈 앞 큰 창
            cs.append(E((s * 0.62, -2.2, 0.9), (0.13, 0.24, 0.34), (s * 1, 0, 0.1), 0))              # 작은 창
            cs.append(E((s * 0.2, -2.92, 1.02), (0.11, 0.2, 0.22), (s * 0.3, -0.6, 0.75), 0))         # 콧구멍
            cs.append(E((s * 1.1, 0.98, 1.2), (0.2, 0.24, 0.42), (s * 1, 0.1, 0.05), R(20)))          # 관자 창 (눈보다 작은 비스듬한 틈)
            cs.append(E((s * 0.4, 1.05, 2.18), (0.18, 0.34, 0.3), (s * 0.25, 0.1, 1.0), 0))          # 정수리 창
            for j in range(3):                                                                    # 볏 가장자리가 깨져 나간 자리
                a = R(25 + 55 * j + rng.uniform(-10, 10))
                p = Vector((s * 1.18 * math.sin(a), 1.75 + 0.82 * math.cos(a) * 0.47, 1.55 + 0.82 * math.cos(a) * 0.88))
                g = sphere(1.0, Ms @ p, (0.16 * S, 0.2 * S, 0.14 * S), 2, rot=(rng.uniform(0, 3), rng.uniform(0, 3), rng.uniform(0, 3)))
                slice_rock(g, rng, 7, (0.1, 0.3))
                cs.append(g)
        # 정수리 왼쪽이 깨져 뚫린 구멍 + 가장자리의 해면뼈
        hc_ = Ms @ Vector((-0.55, 0.72, 2.05))
        g = sphere(1.0, hc_, (0.3 * S, 0.36 * S, 0.26 * S), 2, rot=(0.4, 0.2, 0.9))
        slice_rock(g, rng, 9, (0.08, 0.28))
        cs.append(g)
        cs += surf_pores(bvh, hc_, 0.34 * S, 18, 0.035, rng)
        # 부리 끝이 떨어져 나감
        bp = Ms @ Vector((0.1, -3.28, 0.86))
        g2 = sphere(1.0, bp, (0.2, 0.17, 0.2), 2, rot=(0.3, 0.7, 0.1))
        slice_rock(g2, rng, 7, (0.1, 0.3))
        cs.append(g2)
        cs += surf_pores(bvh, bp, 0.17, 7, 0.028, rng)
        for p, r in alveoli:                                                                       # 빠진 이 자리
            cs.append(ell(Ms @ p, (r * S, r * S, 0.18 * S), L3 @ Vector((0, 0, 1)), 0, 2, "alv"))
        # 금
        for st, d, L, w, dep in (((0.25, -1.0, 2.0), (-0.3, -1, 0), 1.7, 0.05, 0.08), ((0.85, 1.2, 1.9), (0.1, 0.3, -1), 1.1, 0.045, 0.07),
                                 ((0.35, 0.05, 2.15), (1, 0.3, 0.1), 1.0, 0.04, 0.06), ((-0.95, -0.9, 1.1), (0, -1, -0.2), 1.2, 0.04, 0.06),
                                 ((0.3, 1.95, 2.05), (1, 0.1, -0.4), 1.0, 0.04, 0.06), ((-1.1, 1.6, 1.5), (0, 0.3, -1), 0.8, 0.04, 0.06)):
            cs += crack_cutters(bvh, Ms @ Vector(st), L3 @ Vector(d), L * S, w, dep, rng, 8)
        # 봉합선 (구불구불한 얕은 홈): 콧등과 이마 사이, 정수리 가운데, 광대 판 위
        for st, d, L in (((-0.7, -0.55, 1.7), (1, 0, 0.05), 1.5), ((0.0, 0.3, 2.2), (0, 1, 0.1), 1.4), ((1.15, 0.2, 0.85), (0, 1, 0), 1.0),
                         ((-1.15, 0.2, 0.85), (0, 1, 0), 1.0)):
            cs += crack_cutters(bvh, Ms @ Vector(st), L3 @ Vector(d), L * S, 0.022, 0.025, rng, 16, 1.1, 0.0)
        return cs
    sk = bone_high(it, Ms, 0.026, 0.012, skull_cuts, BONE_BIG(1.6, 0.6, 0.6, 1.5), None, seed=11, sub=2, smooth=(0.5, 2), name="skull")

    def jaw_cuts(o):
        bvh = surf_bvh(o)
        cs = []
        for s in (-1, 1):
            cs.append(ell(Mj @ Vector((s * 0.95, 0.2, 0.47)), (0.42 * S, 0.13 * S, 0.55 * S), Mj.to_3x3() @ Vector((0, 1, 0)), 0, 2, "jfen"))
        for p, r in jalv:
            cs.append(ell(Mj @ p, (r * S, r * S, 0.16 * S), Mj.to_3x3() @ Vector((0, 0, 1)), 0, 2, "alv"))
        for st, d, L in (((0.9, -0.6, 0.6), (0, -1, 0.1), 1.3), ((-0.75, -1.2, 0.55), (0.1, -1, -0.1), 1.1), ((0.6, -2.0, 0.4), (0, -1, 0), 0.7)):
            cs += crack_cutters(bvh, Mj @ Vector(st), Mj.to_3x3() @ Vector(d), L * S, 0.04, 0.06, rng, 7)
        g = sphere(1.0, Mj @ Vector((-0.2, -2.95, 0.48)), (0.16, 0.14, 0.14), 2, rot=(0.5, 0.2, 0.8))      # 턱끝 위가 깨짐
        slice_rock(g, rng, 7, (0.1, 0.3))
        cs.append(g)
        cs += surf_pores(bvh, Mj @ Vector((-0.2, -2.95, 0.48)), 0.14, 6, 0.025, rng)
        return cs
    jaw = bone_high(jt, Mj, 0.024, 0.011, jaw_cuts, BONE_BIG(1.3, 0.55, 0.6, 1.4), None, seed=12, name="jaw")
    TL = [{'t': 'lumps', 'scale': 6, 'amp': 0.006}, {'t': 'fissure', 'scale': 5, 'width': 0.014, 'depth': 0.008, 'cover': 0.65},
          {'t': 'terrace', 'scale': 9, 'steps': 3, 'amp': 0.004, 'cover': 0.5}, {'t': 'pits', 'scale': 50, 'depth': 0.002, 'cover': 0.6}]
    teeth = bone_high(tt, Ms, 0.011, 0.0065, None, TL, None, seed=13, smooth=(0.3, 1), name="teeth")
    lteeth = bone_high(ltt, Mj, 0.011, 0.0065, None, TL, None, seed=14, smooth=(0.3, 1), name="lteeth")
    teeth = join([teeth, lteeth])

    def horn_cuts(o):
        p, n, r = horn_break
        cs = break_cutters(Ms @ p, Ms.to_3x3() @ n, r * S, rng, seed=3, pores=24, cavity=0.4)
        d = (fpts[2] - fpts[0]).normalized()
        cs += break_cutters(fpts[1] - d * 0.05, -d, frr[1], rng, seed=4, pores=12, cavity=0.35)
        return cs
    horn_items = [(Ms @ Vector(c), tuple(v * S for v in r), (Ms.to_3x3().normalized() @ q.to_matrix())) for c, r, q in hi]
    horns = bone_high(horn_items + frag_items, None, 0.018, 0.009, horn_cuts,
                      [{'t': 'lumps', 'scale': 1.6, 'amp': 0.012}, {'t': 'bark', 'scale': 4.5, 'width': 0.07, 'depth': 0.022, 'stretch': 0.06},
                       {'t': 'fissure', 'scale': 2.0, 'width': 0.012, 'depth': 0.018, 'cover': 0.55},
                       {'t': 'terrace', 'scale': 5, 'steps': 3, 'amp': 0.006, 'cover': 0.5},
                       {'t': 'pits', 'scale': 30, 'depth': 0.004, 'cover': 0.6}, {'t': 'grain', 'scale': 90, 'amp': 0.001}],
                      hguide, seed=15, name="horns")
    ring_ridges(horns, hpaths, 0.15, 0.01, seed=1, fade_tip=0.5, jitter=0.7)   # 성장 고리 (밑동에서 뚜렷하고 끝으로 옅어짐)

    # 눈구멍 깊은 곳의 불씨 (뒷벽에 반쯤 묻힌 작은 덩어리 — 흐릿하게 새어 나오는 빛)
    embers = []
    for s in (-1, 1):
        embers.append(ember(Ms @ Vector((s * 0.52, -0.16, 1.3)), 0.06, rng))
        embers.append(ember(Ms @ Vector((s * 0.55, -0.3, 1.2)), 0.025, rng))
    highs = [sk, jaw, teeth, horns]
    off = recenter(highs, embers)
    # 칠 (가운데 맞춘 뒤: 재질이 물체 좌표를 쓴다)
    eyes = [tuple(Ms @ Vector((s * 0.55, -0.16, 1.3)) + off) for s in (-1, 1)]
    skm = bone_mat("dskull", 1.6, moss=0.22, stain=0.7, dirt_h=0.6, moss_h=0.5, streak=0.5, ao=0.5)
    for e in eyes:
        tint_near(skm, e, 0.42, (0.2, 0.1, 0.32), 0.5)                       # 눈구멍 안쪽에 스민 영혼 빛 (어두운 보라)
    set_mat(sk, skm)
    set_mat(jaw, bone_mat("djaw", 1.3, moss=0.25, stain=0.7, dirt_h=0.55, moss_h=0.55, streak=0.35, ao=0.4))
    tm = paint("dteeth", ((0.14, 0.12, 0.1), (0.6, 0.55, 0.44), (0.88, 0.85, 0.76)), moss=0.0, dirt=0.0, streaks=0.0, ao=0.12, edge=0.8, cavity=1.0, cracks=0.35)
    blotch(tm, (0.4, 0.3, 0.15), 6, 0.7)
    dirt_low(tm, -0.3, 0.35, 0.8, (0.05, 0.042, 0.05))
    set_mat(teeth, tm)
    set_mat(horns, horn_mat("dhorn", 1.4))
    lows = [low_of(sk, 13000, -0.06), low_of(jaw, 5200, -0.06), low_of(teeth, 2200, -0.06), low_of(horns, 2800, -0.06)]
    jl = Mj @ Vector((-0.98, -0.4, 0.12)) + off
    bk = Ms @ Vector((0.35, 1.95, 0.9)) + off
    ivys = ivy_on(lows, [(jl, 5, 3.2), (bk, 9, 2.0)])
    return finish_b("dragon_skull", highs, lows, extras=embers + ivys, far_extras=embers, size=2048, extr=0.09, lod1=0.35, lod2=0.12)


# ───────────────────────── 갈비뼈 아치 ─────────────────────────
def _rib_curve(x, dx, H, yc, y1, rng, n=48):
    """갈비뼈 곡선: 척추 쪽 머리에서 목을 지나 가파르게 솟고(갈비뼈 각), 꼭대기를 넘어 길게 비탈져 내려가 땅에 꽂힌다"""
    ctrl = [(x, yc - 0.35, 0.95),
            (x + dx * 0.03, yc - 0.12, 1.95),
            (x + dx * 0.15, yc - 0.75, H * 0.86),
            (x + dx * 0.38, -0.2 + rng.uniform(-0.25, 0.25), H),
            (x + dx * 0.7, -2.45, H * 0.63),
            (x + dx * 0.92, y1 + 0.18, 0.95),
            (x + dx, y1, -0.45)]
    return spline(ctrl, n)

def vertebra(c, t, up, k, rng, spine_len=1.3, spine_dir=None, spine_break=None, tp_len=0.6, tp_down=0.25, spurs=False, items=None, guide=None,
             bend=0.08, blade=(1.5, 0.55)):
    """척추뼈 한 마디. c 중심, t 진행 방향, up 등쪽, k 크기. 돌아오는 것: 신경가시 경로(부러뜨릴 자리 계산용)"""
    t = Vector(t).normalized(); up = Vector(up); up = (up - t * up.dot(t)).normalized(); side = up.cross(t)
    c = Vector(c)
    L = 0.8 * k
    cen = [c - t * (L / 2), c - t * (L * 0.2), c + t * (L * 0.2), c + t * (L / 2)]
    items += bone_tube(cen, [0.37 * k, 0.3 * k, 0.3 * k, 0.37 * k], (1.0, 1.0), 0.35, ref=up)          # 몸통 (가운데가 잘록)
    for e in (-1, 1):
        items.append((c + t * (e * L * 0.47), (0.36 * k, 0.36 * k, 0.07 * k), t.to_track_quat('Z', 'Y')))   # 끝 테두리
    items.append((c + up * (0.36 * k), (0.2 * k, 0.24 * k, 0.32 * k), Matrix((side, up, t)).transposed()))   # 신경궁
    for e in (-1, 1):
        for sd in (-1, 1):
            items.append((c + up * (0.42 * k) + t * (e * 0.42 * k) + side * (sd * 0.13 * k), 0.09 * k))      # 앞뒤 관절 돌기
    sd_ = Vector(spine_dir).normalized() if spine_dir is not None else (up - t * 0.35).normalized()
    sp_pts = None
    if spine_len > 0:
        its, sp_pts = spike(c + up * (0.42 * k), sd_, spine_len, 0.17 * k, -t * bend + up * 0.0, 0.1, 9, blade)
        # spike() 의 단면 X 는 ref(1,0,0) 기준이라 따로 다시 만든다 (날을 사슬 방향으로 넓게)
        rad = [max(0.017 * k, 0.17 * k * (1 - i / 9) ** 0.85) for i in range(10)]
        its = bone_tube(sp_pts, rad, blade, 0.4, ref=t)
        if spine_break is not None:
            kk = max(2, int(9 * spine_break))
            its = bone_tube(sp_pts[:kk + 1], rad[:kk + 1], blade, 0.4, ref=t)
        items += its
        if guide is not None:
            guide.add(sp_pts)
    for sd in (-1, 1):
        a = c + side * (sd * 0.28 * k) + up * (0.05 * k)
        b = a + side * (sd * tp_len * k) - up * (tp_down * k) - t * (0.08 * k)
        items += bone_tube([a, a.lerp(b, 0.5) + up * (0.04 * k), b], [0.13 * k, 0.11 * k, 0.08 * k], (1.4, 0.6), 0.4, ref=t)   # 가로돌기
        if spurs:
            its, pts = spike(b, (side * sd * 0.4 + up).normalized(), 0.35 * k, 0.07 * k, -t * 0.05, 0.15, 6)
            items += its
        if guide is not None:
            guide.add([a, b])
    if guide is not None:
        guide.add(cen)
    return sp_pts

def dragon_ribs():
    """반쯤 묻힌 척추에서 솟아 아치를 이루는 거대한 갈비뼈 여섯 (~12.5m 길이, ~6m 높이). 옆으로 누운 용의 몸통이라
    척추는 +Y 쪽 땅에 반쯤 묻혀 신경가시가 뒤로 눕고, 갈비뼈는 위로 솟아 -Y 쪽 땅에 꽂힌다 (아래로 걸어 지나갈 수 있다).
    둘째 갈비뼈는 위쪽이 부러져 그 조각이 아래 땅에 떨어져 있고, 다섯째는 끝이 부러졌다. 신경가시 몇 개와 끝 척추뼈도 부러짐."""
    rng = random.Random(1301)
    guide = Guide()
    sp = []
    yc, zc = 2.7, 0.12
    nv = 8
    xs = [-6.1 + i * (12.2 / (nv - 1)) for i in range(nv)]
    spine_tips = []
    for i, x in enumerate(xs):
        k = 1.0 - 0.12 * abs(i - 3.5) / 3.5
        c = Vector((x + rng.uniform(-0.08, 0.08), yc + rng.uniform(-0.1, 0.1), zc + rng.uniform(-0.04, 0.04)))
        t = Matrix.Rotation(R(rng.uniform(-6, 6)), 3, 'Z') @ Vector((1, 0, 0))
        up = Matrix.Rotation(R(rng.uniform(-8, 8)), 3, t) @ Vector((0, 0.82, 0.57)).normalized()
        brk = {2: 0.55, 5: 0.45, 7: 0.3}.get(i)
        pts = vertebra(c, t, up, k * 1.2, rng, spine_len=rng.uniform(1.3, 1.7), spine_break=brk, tp_len=0.55, tp_down=-0.25,
                       items=sp, guide=guide)
        if brk is not None:
            kk = max(2, int(9 * brk))
            spine_tips.append((pts[kk - 1], (pts[kk] - pts[kk - 2]).normalized(), 0.17 * k * 1.2 * (1 - (kk - 1) / 9) ** 0.85))
    # 갈비뼈
    rb = []
    Hs = [4.5, 5.3, 5.9, 6.0, 5.45, 4.6]
    dxs = [-0.35, 0.25, -0.15, 0.3, -0.2, 0.5]
    breaks = []
    frags = []
    for j in range(6):
        x = xs[j + 1] + rng.uniform(-0.12, 0.12)
        y1 = -3.55 + rng.uniform(-0.25, 0.25)
        pts = _rib_curve(x, dxs[j], Hs[j], yc, y1, rng, 44)
        rad = resample([0.17, 0.2, 0.22, 0.21, 0.18, 0.14, 0.11], 44)
        sq = (1.6, 0.62)
        cut_at = None
        if j == 1:
            cut_at = 0.6
        elif j == 4:
            cut_at = 0.83
        if cut_at is not None:
            kk = int(44 * cut_at)
            breaks.append((pts[kk - 1], (pts[kk] - pts[kk - 2]).normalized(), rad[kk - 1]))
            fr_pts, fr_rad = pts[kk + 1:], rad[kk + 1:]
            frags.append((fr_pts, fr_rad))
            pts, rad = pts[:kk + 1], rad[:kk + 1]
        rb += bone_tube(pts, rad, sq, 0.45, ref=(1, 0, 0), wobble=0.06, seed=j)
        guide.add(pts)
        # 갈비뼈 머리: 척추뼈 가로돌기에 걸친 두 혹
        rb.append(((x, yc - 0.35, 0.78), 0.21))
        rb.append(((x + 0.1, yc - 0.12, 0.98), (0.17, 0.2, 0.15)))
    # 떨어진 조각: 땅에 납작하게 누운 갈비뼈 토막 (양 끝이 부러짐)
    frag_breaks = []
    placed = [((xs[2] + 0.5, -0.9, 0.11), R(-25)), ((xs[5] + 0.3, -2.4, 0.09), R(70))]
    for (fp, frad), (pos, yaw) in zip(frags, placed):
        fp = [Vector(p) for p in fp]
        if len(fp) < 4:
            continue
        cen = sum(fp, Vector()) / len(fp)
        # 곡선 평면 (갈비뼈는 YZ 평면에 가깝다) → 땅(XY) 평면으로 눕힌다: X 축으로 90° 돌린 뒤 yaw
        M = Matrix.Translation(pos) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(R(90), 4, 'X') @ Matrix.Translation(-cen)
        q = [M @ p for p in fp]
        zmin = min(p.z for p in q)
        q = [p + Vector((0, 0, pos[2] - zmin - 0.08)) for p in q]
        rb += bone_tube(q, frad, (0.62, 1.6), 0.45, ref=(0, 0, 1))
        guide.add(q)
        frag_breaks.append((q[0], (q[0] - q[2]).normalized(), frad[0]))
        frag_breaks.append((q[-1], (q[-1] - q[-3]).normalized(), frad[-1]))

    def rib_cuts(o):
        bvh = surf_bvh(o)
        cs = []
        for i, (p, n, r) in enumerate(breaks):
            cs += break_cutters(p, n, r * 1.45, rng, seed=20 + i, pores=26, cavity=0.42)
        for i, (p, n, r) in enumerate(frag_breaks):
            cs += break_cutters(p - n * (r * 0.4), n, r * 1.45, rng, seed=30 + i, pores=14, cavity=0.4)
        for j in (0, 2, 3, 5):
            x = xs[j + 1]
            st = Vector((x, -0.5 + rng.uniform(-1, 1), Hs[j] * 0.9))
            cs += crack_cutters(bvh, st, (0, -0.3, -1) if rng.random() < 0.5 else (0, 1, -0.3), 2.0, 0.05, 0.06, rng, 9, 0.35, 0.3)
        return cs

    def spine_cuts(o):
        bvh = surf_bvh(o)
        cs = []
        for i, (p, n, r) in enumerate(spine_tips):
            cs += break_cutters(p, n, r * 1.5, rng, seed=40 + i, pores=12, cavity=0.3)
        # 맨 끝 척추뼈 몸통이 반으로 부러짐
        cs += break_cutters(Vector((xs[-1] + 0.05, yc, zc)), (1, 0, 0), 0.42, rng, seed=50, pores=30, cavity=0.45)
        for x in (xs[1], xs[4]):
            cs += crack_cutters(bvh, Vector((x, yc - 0.3, 0.3)), (1, 0.1, 0.2), 0.8, 0.04, 0.05, rng, 6)
        return cs
    lay = BONE_BIG(1.3, 0.5, 0.5) + [BONE_SPLIT(1.3)]
    ribs = bone_high(rb, None, 0.03, 0.015, rib_cuts, lay, guide, seed=21, name="ribs")
    spine = bone_high(sp, None, 0.028, 0.014, spine_cuts, lay, guide, seed=22, name="spine")
    set_mat(ribs, bone_mat("dribs", 1.4, moss=0.15, stain=0.65, dirt_h=0.7, moss_h=0.6, streak=0.5, ao=0.4))
    set_mat(spine, bone_mat("dspine", 1.3, moss=0.12, stain=0.65, dirt_h=0.35, moss_h=0.25, streak=0.3, ao=0.35))
    highs = [ribs, spine]
    off = recenter(highs)
    lows = [low_of(ribs, 17500, -0.06), low_of(spine, 7500, -0.06)]
    ivys = ivy_on(lows, [(Vector((xs[1] - 0.35, -3.3, 0.05)) + off, 21, 4.0), (Vector((xs[4] + 0.3, yc - 0.6, 0.3)) + off, 23, 3.0),
                         (Vector((xs[6], -3.2, 0.05)) + off, 25, 3.0)], leaf=0.13, size=0.07, max_leaves=260)
    return finish_b("dragon_ribs", highs, lows, extras=ivys, far_extras=[], size=2048, extr=0.1, lod1=0.35, lod2=0.12)


# ───────────────────────── 가시 척추 ─────────────────────────
def dragon_spine():
    """가시 돋은 척추뼈 사슬 (~10m): 땅 위에 S자로 누운 꼬리뼈 14마디가 반쯤 묻혀 있다. 마디마다 높이 솟은 신경가시
    (꼬리 쪽으로 작아짐, 몇 개는 부러짐), 옆으로 뻗은 가로돌기와 그 끝의 작은 가시. 마디 사이가 벌어지고 몇 마디는 비틀려 쓰러졌다.
    큰 쪽 첫 마디는 몸통이 반으로 부러져 해면 같은 속이 드러난다."""
    rng = random.Random(1401)
    guide = Guide()
    path = spline([(-5.0, -0.7, 0), (-2.6, 0.55, 0), (0.0, -0.25, 0), (2.5, -0.85, 0), (5.0, 0.35, 0)], 400)
    acc = [0.0]
    for a, b in zip(path, path[1:]):
        acc.append(acc[-1] + (b - a).length)
    total = acc[-1]

    def at(sv):
        sv = max(0.0, min(total, sv))
        for j in range(1, len(acc)):
            if acc[j] >= sv:
                t = (sv - acc[j - 1]) / max(1e-9, acc[j] - acc[j - 1])
                return path[j - 1].lerp(path[j], t), (path[j] - path[j - 1]).normalized()
        return path[-1], (path[-1] - path[-2]).normalized()
    n = 14
    ks = [1.0 - 0.55 * (i / (n - 1)) ** 1.1 for i in range(n)]
    lens = [0.8 * k + 0.16 * k for k in ks]
    scale_s = total / sum(lens)
    items = []
    tips = []
    sv = 0.0
    fallen = {5: 70, 9: -55}
    spine_breaks = {1: 0.5, 6: 0.55, 11: 0.4}
    first = None
    for i in range(n):
        k = ks[i]
        Lh = lens[i] * scale_s
        c, t = at(sv + Lh / 2)
        sv += Lh
        t = Matrix.Rotation(R(rng.uniform(-9, 9)), 3, 'Z') @ t
        roll = fallen.get(i, rng.uniform(-10, 10))
        up = Matrix.Rotation(R(roll), 3, t) @ Vector((0, 0, 1))
        c = c + Vector((0, 0, 0.17 * k - (0.08 if i in fallen else 0.0)))
        if i in fallen:
            c += t.cross(Vector((0, 0, 1))).normalized() * (0.25 if roll > 0 else -0.25)
        sl = (1.75 - 0.2 * (i % 2)) * k ** 1.25 * rng.uniform(0.82, 1.18) + 0.15
        sd = (up - t * (0.42 + 0.1 * rng.uniform(-1, 1))).normalized()
        brk = spine_breaks.get(i)
        pts = vertebra(c, t, up, k, rng, spine_len=sl, spine_dir=sd, spine_break=brk, tp_len=0.62, tp_down=0.32,
                       spurs=(i < 9), items=items, guide=guide, bend=0.22 * sl, blade=(1.9, 0.5))
        if brk is not None:
            kk = max(2, int(9 * brk))
            tips.append((pts[kk - 1], (pts[kk] - pts[kk - 2]).normalized(), 0.17 * k * (1 - (kk - 1) / 9) ** 0.85))
        if i == 0:
            first = (c, t, k)
    c0, t0, k0 = first

    def cuts(o):
        bvh = surf_bvh(o)
        cs = []
        for j, (p, nn, r) in enumerate(tips):
            cs += break_cutters(p, nn, r * 1.5, rng, seed=60 + j, pores=10, cavity=0.3)
        cs += break_cutters(c0 - t0 * (0.05 * k0), -t0, 0.37 * k0, rng, seed=70, pores=34, cavity=0.45)
        for j in (2, 4, 8):
            cc, tt_ = at(sum(lens[:j]) * scale_s + lens[j] * scale_s * 0.5)
            cs += crack_cutters(bvh, cc + Vector((0, 0, 0.35 * ks[j])), tt_ + Vector((0, 0, 0.3)), 0.7 * ks[j], 0.035, 0.045, rng, 6)
        return cs
    lay = BONE_BIG(1.1, 0.5, 0.5) + [BONE_SPLIT(1.1)]
    sp = bone_high(items, None, 0.024, 0.011, cuts, lay, guide, seed=31, name="spine")
    set_mat(sp, bone_mat("dspine2", 1.1, moss=0.12, stain=0.65, dirt_h=0.35, moss_h=0.25, streak=0.3, ao=0.3))
    recenter([sp])
    low = low_of(sp, 12000, -0.06)
    ivys = ivy_on([low], [(Vector((-1.2, 0.9, 0.03)), 31, 2.4)], leaf=0.1, size=0.06)
    return finish_b("dragon_spine", [sp], [low], extras=ivys, far_extras=[], size=2048, extr=0.07, lod1=0.35, lod2=0.12)


# ───────────────────────── 땅에서 솟은 발톱 ─────────────────────────
def _curl_chain(start, base_dir, lat, segs, rng):
    """손가락 마디 사슬. base_dir 에서 시작해 lat(옆 축) 둘레로 마디마다 굽는다. segs: [(길이, 반지름, 누적 굽힘°)]
    돌아오는 것: [(시작, 끝, 반지름)]"""
    out = []
    p = Vector(start)
    d0 = Vector(base_dir).normalized()
    lat = Vector(lat).normalized()
    for L, r, ang in segs:
        d = Matrix.Rotation(R(ang), 3, lat) @ d0
        q = p + d * L
        out.append((p.copy(), q.copy(), r))
        p = q
    return out

def dragon_claw():
    """땅에서 솟은 거대한 앞발·날개뼈 (~5m): 팔꿈치가 땅에 반쯤 묻히고 아래팔 두 뼈가 비스듬히 솟아, 손목뼈 무더기 위로
    발톱 셋이 앞(-Y)으로 움켜쥐듯 굽었다. 뒤로는 긴 날개 손가락이 하늘로 뻗다 끝이 부러졌다. 발톱 끝은 어둡고 휜 각질(성장 고리).
    오른쪽 손가락 하나는 끝마디가 부러져 그 발톱이 밑동 땅에 떨어져 있다."""
    rng = random.Random(1501)
    guide = Guide()
    it = []
    tal = []
    tpaths = []
    elbow = Vector((0.2, 0.75, 0.08))
    it.append((elbow, (0.44, 0.4, 0.36)))
    it.append((elbow + Vector((0.18, 0.22, -0.05)), (0.3, 0.3, 0.3)))
    hum = [elbow + Vector((0.35, 1.0, -0.55)), elbow + Vector((0.15, 0.4, -0.1)), elbow]
    it += bone_tube(hum, [0.3, 0.33, 0.36], (1.0, 0.9), 0.45)
    guide.add(hum)
    wrist = Vector((-0.12, -0.3, 2.85))
    for sd, r0 in ((-1, 0.2), (1, 0.16)):
        a = elbow + Vector((sd * 0.17, -0.05, 0.2))
        b = wrist + Vector((sd * 0.2, 0.05, -0.18))
        mid = a.lerp(b, 0.5) + Vector((sd * 0.09, 0.08, 0))
        pts = spline([a, mid, b], 18)
        rad = resample([r0 * 1.45, r0 * 1.05, r0 * 0.85, r0 * 0.95, r0 * 1.35], 18)
        it += bone_tube(pts, rad, (1.0, 0.85), 0.45)
        guide.add(pts)
    for j in range(8):
        p = wrist + Vector((rng.uniform(-0.32, 0.32), rng.uniform(-0.18, 0.18), rng.uniform(-0.05, 0.28)))
        it.append((p, (rng.uniform(0.13, 0.19), rng.uniform(0.12, 0.17), rng.uniform(0.11, 0.16)), (rng.uniform(0, 3), rng.uniform(0, 3), rng.uniform(0, 3))))
    # 발톱 손가락 셋 + 엄지
    fingers = [(-0.5, 0.92, [8, 42, 78, 118], False), (0.0, 1.0, [6, 38, 72, 112], False), (0.48, 0.94, [10, 45, 80, 120], True)]
    breaks = []
    for xo, ks, curl, broken in fingers:
        st = wrist + Vector((xo * 0.55, -0.05, 0.25))
        d0 = Vector((xo * 0.35, 0.05, 1.0))
        lat = Vector((1, 0, 0)) + Vector((0, 0, 0)) 
        segs = [(1.0 * ks, 0.13, curl[0]), (0.72 * ks, 0.12, curl[1]), (0.56 * ks, 0.1, curl[2])]
        ch = _curl_chain(st, d0, lat, segs, rng)
        if broken:
            ch = ch[:2]
        for a, b, r in ch:
            pts = [a, a.lerp(b, 0.5), b]
            it += bone_tube(pts, [r * 1.25, r * 0.9, r * 1.2], (1.0, 0.9), 0.45)
            guide.add(pts)
            side = Vector((1, 0, 0))
            for e in (-1, 1):
                it.append((b + side * (e * r * 0.55), r * 0.95))           # 두 갈래 관절
        tip = ch[-1][1]
        if broken:
            a, b, r = ch[-1]
            breaks.append((b + (b - a).normalized() * r * 0.6, (b - a).normalized(), r))
            continue
        a, b, r = ch[-1]
        dlast = (b - a).normalized()
        dt = Matrix.Rotation(R(curl[3] - curl[2]), 3, lat) @ dlast
        L = 1.0 * ks
        tp = [b + dlast * (r * 0.3)]
        for k in range(1, 9):
            u = k / 8
            ang = R((curl[3] - curl[2]) * u * 1.25)
            dd = Matrix.Rotation(ang, 3, lat) @ dlast
            tp.append(tp[-1] + dd * (L / 8))
        trad = [max(0.014, 0.16 * ks * (1 - k / 8) ** 0.9) for k in range(9)]
        tal += bone_tube(tp, trad, (0.62, 1.0), 0.4, ref=(1, 0, 0))
        tpaths.append(tp)
        guide.add(tp)
    # 엄지 (짧고 바깥으로)
    st = wrist + Vector((-0.42, -0.12, 0.05))
    ch = _curl_chain(st, (-0.8, -0.3, 0.55), (0.3, -1, 0), [(0.55, 0.11, 0), (0.38, 0.1, -30)], rng)
    for a, b, r in ch:
        pts = [a, a.lerp(b, 0.5), b]
        it += bone_tube(pts, [r * 1.25, r * 0.9, r * 1.2], (1.0, 0.9), 0.45)
        it.append((b, r * 1.2))
        guide.add(pts)
    a, b, r = ch[-1]
    dl = (b - a).normalized()
    tp = [b]
    for k in range(1, 7):
        dd = Matrix.Rotation(R(-14 * k), 3, Vector((0.3, -1, 0)).normalized()) @ dl
        tp.append(tp[-1] + dd * 0.1)
    tal += bone_tube(tp, [max(0.012, 0.12 * (1 - k / 6) ** 0.9) for k in range(7)], (0.62, 1.0), 0.4)
    tpaths.append(tp)
    # 날개 손가락: 뒤(+Y)로 길게 뻗어 하늘로, 끝이 부러짐
    st = wrist + Vector((0.3, 0.2, 0.2))
    wing = [st, st + Vector((0.25, 0.45, 1.05)), st + Vector((0.55, 1.15, 2.05)), st + Vector((0.75, 2.0, 2.55))]
    wp = spline(wing, 24)
    wr = resample([0.17, 0.15, 0.135, 0.11], 24)
    it += bone_tube(wp, wr, (1.0, 0.85), 0.45)
    for j in (8, 16):
        it.append((wp[j], wr[j] * 1.45))                                     # 날개 손가락 마디
    guide.add(wp)
    breaks.append((wp[-2], (wp[-1] - wp[-3]).normalized(), wr[-2]))
    # 떨어진 발톱 하나 (밑동 앞 땅 위)
    fp = [Vector((0.75, -0.75, 0.1)), Vector((0.95, -1.05, 0.13)), Vector((1.08, -1.4, 0.12)), Vector((1.1, -1.7, 0.08))]
    fpts = spline(fp, 10)
    tal += bone_tube(fpts, [max(0.014, 0.13 * (1 - k / 10) ** 0.9) for k in range(11)], (0.62, 1.0), 0.4, ref=(0, 0, 1))
    tpaths.append(fpts)

    def cuts(o):
        bvh = surf_bvh(o)
        cs = []
        for j, (p, n, r) in enumerate(breaks):
            cs += break_cutters(p, n, r * 1.2, rng, seed=80 + j, pores=18, cavity=0.4)
        for st, d, L in (((0.0, -0.1, 1.4), (0.1, 0, 1), 1.3), ((0.6, 0.9, 3.9), (0.2, 0.5, 0.6), 1.0), ((0.35, 0.75, 0.3), (1, 0.3, 0), 0.7)):
            cs += crack_cutters(bvh, Vector(st), Vector(d), L, 0.035, 0.045, rng, 7)
        return cs
    lay = BONE_BIG(0.8, 0.5, 0.5) + [BONE_SPLIT(0.8)]
    bones = bone_high(it, None, 0.02, 0.0095, cuts, lay, guide, seed=41, name="claw")

    def tcuts(o):
        p0, p1 = fpts[0], fpts[2]
        n = (p0 - p1).normalized()
        return break_cutters(p0 + n * 0.02, n, 0.13, rng, seed=90, pores=8, cavity=0.3)
    talons = bone_high(tal, None, 0.014, 0.007, tcuts,
                       [{'t': 'lumps', 'scale': 3, 'amp': 0.006}, {'t': 'bark', 'scale': 6, 'width': 0.06, 'depth': 0.006, 'stretch': 0.08},
                        {'t': 'pits', 'scale': 40, 'depth': 0.002, 'cover': 0.6}], guide, seed=42, smooth=(0.3, 1), name="talons")
    ring_ridges(talons, tpaths, 0.09, 0.012, seed=3, fade_tip=0.25)
    set_mat(bones, bone_mat("dclaw", 0.9, moss=0.25, stain=0.6, dirt_h=0.6, moss_h=0.7, streak=0.4, ao=0.3))
    set_mat(talons, horn_mat("dtalon", 0.6, moss=0.05, dirt_h=0.25))
    highs = [bones, talons]
    off = recenter(highs)
    lows = [low_of(bones, 7200, -0.06), low_of(talons, 1800, -0.06)]
    ivys = ivy_on(lows, [(elbow + off + Vector((-0.4, -0.2, -0.05)), 41, 2.0)], leaf=0.075)
    return finish_b("dragon_claw", highs, lows, extras=ivys, far_extras=[], size=2048, extr=0.06, lod1=0.35, lod2=0.12)


# ───────────────────────── 뼈 가시 ─────────────────────────
def bone_spike():
    """크고 휜 뼈 가시 (~3m): 땅에서 비스듬히 솟아 앞(-Y)으로 휘었다. 밑동은 굵고 성장 고리가 겹겹이, 위로 갈수록 결 따라
    갈라지고 겉뼈가 벗겨졌다. 중간에 겉이 크게 떨어져 나가 해면 같은 속이 보이는 곳, 끝은 어둡게 삭았다.
    밑동 옆에 작은 곁가시 하나. 원점 = 밑동 (지형 나무 인스턴스로 무리 지어 놓는다)"""
    rng = random.Random(1601)
    guide = Guide()
    ctrl = [(0, 0.12, -0.5), (0, 0.05, 0.45), (0.05, -0.1, 1.35), (0.12, -0.5, 2.15), (0.2, -1.05, 2.72), (0.27, -1.6, 2.98)]
    pts = spline(ctrl, 40)
    rad = resample([0.36, 0.33, 0.25, 0.17, 0.095, 0.022], 40)
    it = bone_tube(pts, rad, (1.0, 0.86), 0.4, wobble=0.05, seed=3)
    guide.add(pts)
    paths = [pts]
    its, sp = spike((0.22, 0.12, 0.05), (0.75, 0.25, 0.65), 0.75, 0.12, (0, -0.1, 0.12), 0.12)
    it += its
    guide.add(sp)
    paths.append(sp)

    def cuts(o):
        bvh = surf_bvh(o)
        cs = []
        # 겉이 크게 떨어져 나간 자리 (평면으로 쳐낸 덩어리 + 해면 구멍)
        for f, sz in ((0.42, 0.2), (0.66, 0.13)):
            i = int(f * 40)
            p = pts[i]
            h = bvh.find_nearest(p + Vector((0.6, -0.3, 0.2)))
            g = sphere(1.0, h[0] + h[1] * (sz * 0.25), (sz, sz * 0.8, sz * 0.7), 2, rot=(rng.uniform(0, 3), rng.uniform(0, 3), rng.uniform(0, 3)))
            slice_rock(g, rng, 8, (0.1, 0.3))
            cs.append(g)
            cs += surf_pores(bvh, h[0], sz * 0.6, 9, 0.022, rng)
        cs += crack_cutters(bvh, pts[10] + Vector((0, -0.4, 0)), (0, -0.2, 1), 1.1, 0.03, 0.04, rng, 8)
        cs += crack_cutters(bvh, pts[18] + Vector((-0.3, 0.2, 0)), (0.1, -0.5, 0.8), 0.9, 0.025, 0.03, rng, 7)
        return cs
    lay = BONE_BIG(0.7, 0.55, 0.55) + [BONE_SPLIT(0.7)]
    o = bone_high(it, None, 0.014, 0.0065, cuts, lay, guide, seed=51, name="spike")
    ring_ridges(o, paths, 0.11, 0.012, seed=5, fade_tip=0.6)
    m = bone_mat("dspike", 0.7, moss=0.25, stain=0.6, dirt_h=0.45, moss_h=0.5, streak=0.35, ao=0.2)
    tint_near(m, tuple(pts[-1]), 1.1, (0.32, 0.28, 0.32), 0.7, 'MULTIPLY')    # 끝이 어둡게 삭았다
    set_mat(o, m)
    low = low_of(o, 4200, -0.06)
    return finish_b("bone_spike", [o], [low], size=1024, extr=0.04, lod1=0.35)


# ───────────────────────── 흩어진 뼈 ─────────────────────────
def bones_scatter():
    """땅에 흩어진 작은 뼈 무리 (~1.5m 범위, 납작): 양 끝이 부러진 갈비뼈 토막, 옆으로 누운 꼬리뼈 마디, 부러진 긴 뼈 둘
    (골수 구멍), 큰 이빨 하나, 떨어진 발톱 하나, 발가락뼈 몇 개, 뼈 부스러기"""
    rng = random.Random(1701)
    guide = Guide()
    it = []
    tal = []
    tpaths = []
    breaks = []
    # 갈비뼈 토막 (땅에 납작하게)
    arc = [Vector((0.55 * math.cos(a) - 0.25, 0.55 * math.sin(a) - 0.15, 0.045)) for a in [R(100 + 14 * k) for k in range(9)]]
    it += bone_tube(arc, resample([0.055, 0.052, 0.045], 8), (0.75, 1.4), 0.45, ref=(0, 0, 1))
    guide.add(arc)
    breaks.append((arc[0], (arc[0] - arc[2]).normalized(), 0.06))
    breaks.append((arc[-1], (arc[-1] - arc[-3]).normalized(), 0.05))
    # 꼬리뼈 마디 하나 (옆으로 누움)
    vertebra(Vector((0.35, 0.3, 0.07)), (0.8, 0.5, 0), Vector((0.3, -0.5, 0.8)), 0.28, rng, spine_len=0.32, tp_len=0.5, tp_down=0.1,
             items=it, guide=guide)
    # 부러진 긴 뼈 둘 (한쪽 관절 혹, 다른 쪽 부러짐)
    for a, b, r, yaw in (((-0.62, 0.35, 0.06), (-0.05, 0.52, 0.05), 0.055, 0), ((0.1, -0.5, 0.05), (0.62, -0.3, 0.045), 0.045, 0)):
        a, b = Vector(a), Vector(b)
        pts = [a, a.lerp(b, 0.5) + Vector((0, 0, 0.01)), b]
        it += bone_tube(pts, [r * 1.05, r * 0.85, r], (1.0, 0.9), 0.45)
        d = (a - b).normalized()
        sd = d.cross(Vector((0, 0, 1))).normalized()
        it.append((a + d * r * 0.3 + sd * r * 0.6, r * 1.35))                # 두 갈래 관절
        it.append((a + d * r * 0.3 - sd * r * 0.6, r * 1.25))
        guide.add(pts)
        breaks.append((b - d * r * 0.4, -d, r))
    # 발가락뼈 셋
    for c, yaw in (((-0.35, -0.35, 0.03), 30), ((-0.15, -0.6, 0.03), -50), ((0.62, 0.05, 0.03), 80)):
        c = Vector(c); d = Vector((math.cos(R(yaw)), math.sin(R(yaw)), 0))
        pts = [c - d * 0.08, c, c + d * 0.08]
        it += bone_tube(pts, [0.035, 0.026, 0.033], (1.0, 0.9), 0.45)
        guide.add(pts)
    # 부스러기
    shards = []
    for k in range(5):
        a = rng.uniform(0, 6.28); r_ = rng.uniform(0.2, 0.68)
        g = sphere(1.0, (math.cos(a) * r_, math.sin(a) * r_ * 0.8, 0.015), (rng.uniform(0.04, 0.08), rng.uniform(0.02, 0.035), rng.uniform(0.015, 0.025)), 2,
                   rot=(0, 0, rng.uniform(0, 6.28)))
        slice_rock(g, rng, 7, (0.1, 0.3))
        xf_all(g)
        shards.append(g)
    # 큰 이빨 (누운), 떨어진 발톱
    tp = [Vector((-0.05, 0.05, 0.035)) + Vector((0.1, -0.06, 0)) * k + Vector((0, 0.015 * k * k, 0.006 * k)) for k in range(4)]
    tooth = bone_tube(tp, [0.042, 0.035, 0.02, 0.008], (1.0, 0.85), 0.4)
    fp = [Vector((-0.7, -0.2, 0.04)), Vector((-0.6, -0.36, 0.05)), Vector((-0.45, -0.46, 0.045)), Vector((-0.3, -0.48, 0.025))]
    fpts = spline(fp, 10)
    tal += bone_tube(fpts, [max(0.007, 0.06 * (1 - k / 10) ** 0.9) for k in range(11)], (0.62, 1.0), 0.4, ref=(0, 0, 1))
    tpaths.append(fpts)

    def cuts(o):
        cs = []
        for j, (p, n, r) in enumerate(breaks):
            cs += break_cutters(p, n, r * 1.2, rng, seed=100 + j, pores=10, cavity=0.45)
        return cs
    lay = [{'t': 'lumps', 'scale': 4, 'amp': 0.004}, {'t': 'terrace', 'scale': 9, 'steps': 3, 'amp': 0.002, 'cover': 0.5},
           {'t': 'fissure', 'scale': 5, 'width': 0.012, 'depth': 0.005, 'cover': 0.55}, {'t': 'pits', 'scale': 60, 'depth': 0.0015, 'cover': 0.6},
           {'t': 'bark', 'scale': 14, 'width': 0.05, 'depth': 0.003, 'stretch': 0.1}, {'t': 'grain', 'scale': 250, 'amp': 0.0003}]
    bones = bone_high(it + tooth, None, 0.006, 0.0035, cuts, lay, guide, seed=61, smooth=(0.4, 2), name="scatter")
    sh = join(shards)
    remesh(sh, 0.004)
    kit.surface(sh, [{'t': 'lumps', 'scale': 12, 'amp': 0.003}, {'t': 'pits', 'scale': 70, 'depth': 0.0015, 'cover': 0.6}], 62)
    bones = join([bones, sh])
    talon = bone_high(tal, None, 0.006, 0.0035, None, [{'t': 'lumps', 'scale': 8, 'amp': 0.002}], None, seed=63, smooth=(0.3, 1), name="stalon")
    ring_ridges(talon, tpaths, 0.035, 0.004, seed=6, fade_tip=0.3)
    set_mat(bones, bone_mat("dscatter", 0.25, moss=0.2, stain=0.65, dirt_h=0.06, moss_h=0.0, streak=0.0, ao=0.06, cracks=0.3))
    set_mat(talon, horn_mat("dstalon", 0.25, moss=0.0, dirt_h=0.04))
    highs = [bones, talon]
    recenter(highs)
    lows = [low_of(bones, 3000, -0.02, 20), low_of(talon, 260, -0.02)]
    return finish_b("bones_scatter", highs, lows, size=1024, extr=0.015, lod1=0.35)

BUILDERS = [
    ("dragon_skull", dragon_skull),
    ("dragon_ribs", dragon_ribs),
    ("dragon_spine", dragon_spine),
    ("dragon_claw", dragon_claw),
    ("bone_spike", bone_spike),
    ("bones_scatter", bones_scatter),
]

META = {
    "dragon_skull": {"kind": "landmark", "tags": ["bone", "landmark", "light"], "collider": "mesh", "footprint": 4.2, "sink": 0.12,
                     "tilt": 3, "align": True, "scale": [0.9, 1.15], "cull": 0.003, "shadows": True,
                     "light": {"offset": [0.0, -0.4, 1.6], "color": SOUL, "intensity": 2.5, "range": 5}},
    "dragon_ribs": {"kind": "landmark", "tags": ["bone", "landmark"], "collider": "mesh", "footprint": 6.8, "sink": 0.2,
                    "tilt": 2, "align": False, "scale": [0.9, 1.12], "cull": 0.003, "shadows": True},
    "dragon_spine": {"kind": "prop", "tags": ["bone", "landmark"], "collider": "mesh", "footprint": 5.0, "sink": 0.1,
                     "tilt": 3, "align": True, "scale": [0.85, 1.2], "cull": 0.005, "shadows": True},
    "dragon_claw": {"kind": "prop", "tags": ["bone"], "collider": "mesh", "footprint": 2.2, "sink": 0.15,
                    "tilt": 6, "align": False, "scale": [0.85, 1.2], "cull": 0.006, "shadows": True},
    "bone_spike": {"kind": "tree", "tags": ["bone"], "collider": "capsule", "footprint": 0.9, "sink": 0.15,
                   "tilt": 0, "align": False, "scale": [0.7, 1.3], "cull": 0.008, "shadows": True},
    "bones_scatter": {"kind": "scatter", "tags": ["bone"], "collider": "none", "footprint": 0.8, "sink": 0.02,
                      "tilt": 4, "align": True, "scale": [0.8, 1.3], "cull": 0.02, "shadows": True},
}

PREVIEWS = [("dragon_skull", ["dragon_skull"], True), ("dragon_ribs", ["dragon_ribs"], True), ("dragon_spine", ["dragon_spine"], True),
            ("dragon_claw", ["dragon_claw"], True), ("bone_spike", ["bone_spike"], True), ("bones_scatter", ["bones_scatter"], True)]
