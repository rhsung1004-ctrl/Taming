# 장면용 새 소품 묶음 (scenes) — 1차 9종
#   낮은 돌담(stone_wall_low), 선돌(standing_stone), 쇠 울타리(iron_fence), 찢긴 깃발(banner_torn), 영혼 수정 노두(soul_crystal),
#   화로(brazier), 꺼져 가는 모닥불(campfire), 석관(sarcophagus), 해골 유해(skeleton_remains)
#
# 월드 생성기(Tools/WorldGen/worldgen.py 의 NEW_PROPS)가 이 이름·크기·META 를 기다린다. 크기는 그 표 ±15% 안.
# 만드는 방식은 v3 (README '만드는 과정'): 깨끗한 형태 → 저폴리 사본 → 새김 → carve(조각) → paint3(손칠) → finish3(우리 굽기).
#   - 이어 놓는 것(stone_wall_low, iron_fence): 긴 축 = 로컬 X, 양 끝이 서로 다르게 무너지거나 끝나서 4칸을 이어도 반복이 덜 보인다.
#     비탈에서 기울이지 않고 세운 채 놓이므로 밑동이 땅속으로 0.25 m 이어진다 (묻힐 여유, 그 부분은 텍셀을 덜 준다).
#   - 키 큰 것(standing_stone, banner_torn, soul_crystal): 멀리서 무엇인지 읽히게 실루엣을 과감하게 (기울기·비대칭·찢긴 띠).
#   - 발광 부품은 Glow_* 재질 슬롯 (굽지 않고 extras 로 붙는다). 점광원은 META.light (far = LightCuller 끄는 거리).
# 공통 도우미는 다른 묶음에서 가져온다 (assets_graves: bmesh·뼈·새김·덧칠, assets_nature: 바위 덩어리·관·풀 카드, assets_ruins: 쇠막대).
import math, random, os
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
from mathutils import noise as mnoise
import kit
from kit import *
import assets_graves as G
import assets_nature as N
import assets_ruins as RU

R = math.radians
SOUL = [0.62, 0.35, 1.0]
SPIRIT = [0.45, 0.95, 0.9]
EMBER = [1.0, 0.5, 0.28]
FAR = 140.0

# 색 묶음 (어두운, 밝은, 닳은 모서리). k1r 검토: 월드 조명이 이미 보라·파랑을 더하므로 알베도는 회색 쪽, 때·이끼는 회갈색·올리브
FIELD_STONE = ((0.075, 0.074, 0.078), (0.43, 0.42, 0.41), (0.62, 0.61, 0.6))       # 밭 돌담: 밝은 회색 (풀 위로 드러난다)
MEGALITH = ((0.05, 0.05, 0.055), (0.29, 0.285, 0.29), (0.5, 0.5, 0.5))            # 선돌·노두 바위: 짙은 회색
GRAVE_GREY = ((0.058, 0.056, 0.07), (0.32, 0.312, 0.35), (0.55, 0.54, 0.59))        # 석관: 약한 청보라 (k4r: 기존 묘비 옆에서 연한 회색으로 떴다)
RUST = RU.RUST                                                                      # 검게 삭은 쇠 + 녹
IRON_DARK = ((0.012, 0.011, 0.013), (0.07, 0.05, 0.045), (0.22, 0.19, 0.19))       # 울타리: 검은 쇠 + 옅은 녹
IRON_OLD = ((0.014, 0.012, 0.014), (0.1, 0.06, 0.045), (0.26, 0.21, 0.2))          # 녹이 더 슨 쇠
STEEL_OLD = ((0.03, 0.028, 0.032), (0.2, 0.185, 0.19), (0.5, 0.48, 0.48))          # 흐린 옛 칼날 (해골 유해의 칼: 흙보다 밝은 쇳빛)
WOOD_GREY = ((0.04, 0.034, 0.032), (0.25, 0.21, 0.18), (0.42, 0.38, 0.34))          # 비바람에 바랜 나무 (깃대)
ROPE = ((0.04, 0.032, 0.025), (0.24, 0.2, 0.15), (0.36, 0.32, 0.26))
CLOTH_RED = ((0.025, 0.009, 0.012), (0.16, 0.042, 0.047), (0.27, 0.11, 0.1))           # 바랜 검붉은 천
CRYSTAL = ((0.015, 0.05, 0.06), (0.1, 0.3, 0.32), (0.38, 0.72, 0.7))              # 영혼 수정: 깊은 청록 → 창백한 청록
COAL = ((0.012, 0.012, 0.014), (0.07, 0.068, 0.07), (0.2, 0.19, 0.19))
ASH = ((0.03, 0.029, 0.03), (0.16, 0.155, 0.15), (0.26, 0.25, 0.25))
WOOD_BURNT = ((0.015, 0.012, 0.011), (0.1, 0.068, 0.05), (0.24, 0.19, 0.16))
ASH_COL = (0.32, 0.31, 0.3)
SHADOW_GREY = (0.12, 0.1, 0.15)
MOSS_OLIVE = (0.085, 0.11, 0.06)       # 이끼: 올리브·회갈색 쪽 (청록으로 튀지 않게)          # paint3 틈 그늘 (기본 보라 (0.16, 0.1, 0.3) 보다 덜 파랗게)

# kit.load_fbx 가 FBX 의 Foliage·Glow 재질을 진짜로 착각하지 않게 먼저 만든다 (assets_graves 와 같은 이유)
if kit.sc is not None:
    foliage_mat()
    for _g in GLOW:
        glow_mat(_g)


# ───────────────────────── 도우미 ─────────────────────────
def rough_box(rng, sx, sy, sz, jit=0.12, chips=(1, 3), depth=(0.015, 0.045), flakes=(0, 2), bevel=0.006):
    """다듬지 않은 돌 한 덩이: 상자 꼭짓점을 제각각 흔들어 비뚤게 + 모서리를 평면으로 쳐냄 (마른 돌쌓기·돌 고리)"""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx * (1 + rng.uniform(-jit, jit)), v.co.y * sy * (1 + rng.uniform(-jit, jit)),
                       v.co.z * sz * (1 + rng.uniform(-jit, jit))))
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    G.bm_chip(bm, rng, rng.randint(*chips), depth)
    G.bm_flake(bm, rng, rng.randint(*flakes))
    G.bm_bevel(bm, bevel)
    return bm


def drop_faces(o, fn):
    """fn(면 가운데, 법선) 이 참인 면을 지운다 (땅속 바닥면 등)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    kill = [f for f in bm.faces if fn(f.calc_center_median(), f.normal)]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o


def below_cut(o, z=0.0):
    """z 아래를 평면으로 잘라 막는다 (바닥을 땅 높이에 맞춘다)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    G.bm_cut(bm, (0, 0, z), (0, 0, -1))
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    return o


def surf_hit(o, p, d):
    """o 표면에 광선 (객체 좌표 = 월드, 변환 적용된 객체)"""
    ok, loc, nrm, idx = o.ray_cast(Vector(p), Vector(d).normalized())
    return (loc, nrm) if ok else (None, None)


def engrave_surface(o, strokes, toward, width, depth, step=0.03, floor=0.3):
    """울퉁불퉁한 면에 획을 판다: 획을 step 조각으로 나눠 앞(toward 반대쪽)에서 쏜 광선으로 표면에 붙이고, 조각마다 그 자리 법선으로 V 홈.
    strokes: [(a, b), ...] 3D 점 (표면 앞쪽 아무 곳), toward: 면이 바라보는 방향 (예 (0,-1,0))"""
    t = Vector(toward).normalized()
    bpy.context.view_layer.update()
    cs = []
    for a, b in strokes:
        a, b = Vector(a), Vector(b)
        n = max(1, int((b - a).length / step))
        pts = []
        for i in range(n + 1):
            p = a.lerp(b, i / n)
            loc, nrm = surf_hit(o, p + t * 1.5, -t)
            if loc is not None:
                pts.append((loc, nrm))
        for (pa, na), (pb, nb) in zip(pts, pts[1:]):
            cs.append(vgroove(pa, pb, (na + nb).normalized(), width, depth, floor))
    if cs:
        cut(o, cs)
    return o


def grass_at(cards, rng, pts, h=(0.25, 0.45), w=(0.22, 0.38), dead=0.4, n=3):
    for p in pts:
        N.grass_tuft(cards, rng, Vector(p), rng.uniform(*h), rng.uniform(*w), n, dead)


def _M(nt, op, a, b=None):
    m = nt.nodes.new('ShaderNodeMath'); m.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if hasattr(v, 'links'):
            nt.links.new(v, m.inputs[i])
        else:
            m.inputs[i].default_value = v
    return m.outputs[0]


def _seg_mask(nt, X, Z, a, b, w):
    """XZ 평면 선분 a-b 에서 거리 w 안 = 1 (노드)"""
    ax, az = a; bx, bz = b
    ex, ez = bx - ax, bz - az
    L2 = max(1e-8, ex * ex + ez * ez)
    px = _M(nt, 'SUBTRACT', X, ax); pz = _M(nt, 'SUBTRACT', Z, az)
    t = _M(nt, 'MINIMUM', _M(nt, 'MAXIMUM', _M(nt, 'DIVIDE', _M(nt, 'ADD', _M(nt, 'MULTIPLY', px, ex), _M(nt, 'MULTIPLY', pz, ez)), L2), 0.0), 1.0)
    qx = _M(nt, 'SUBTRACT', px, _M(nt, 'MULTIPLY', t, ex)); qz = _M(nt, 'SUBTRACT', pz, _M(nt, 'MULTIPLY', t, ez))
    d = _M(nt, 'SQRT', _M(nt, 'ADD', _M(nt, 'MULTIPLY', qx, qx), _M(nt, 'MULTIPLY', qz, qz)))
    return _M(nt, 'LESS_THAN', d, w)


def sigil_paint(mat, cx, cz, r, w, color, amount=0.75, wear=0.55):
    """천에 칠한 바랜 문장 (XZ 평면, 앞뒤 같은 자리). 이 게임용으로 지은 사령 군기:
    고리 + 고리 안 이지러진 달 + 고리 위로 솟은 세 갈래 가지(왕관처럼 벌어짐) + 고리 아래로 흘러내린 두 줄기.
    잡음으로 군데군데 벗겨진다"""
    nt = mat.node_tree
    b, col = G._final_color(mat)
    tc = nt.nodes.new('ShaderNodeTexCoord'); P = tc.outputs['Object']
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(P, sep.inputs[0])
    X, Z = sep.outputs['X'], sep.outputs['Z']
    dx = _M(nt, 'SUBTRACT', X, cx)
    dz = _M(nt, 'SUBTRACT', Z, cz)
    d = _M(nt, 'SQRT', _M(nt, 'ADD', _M(nt, 'MULTIPLY', dx, dx), _M(nt, 'MULTIPLY', dz, dz)))
    mask = _M(nt, 'LESS_THAN', _M(nt, 'ABSOLUTE', _M(nt, 'SUBTRACT', d, r)), w)
    dx2 = _M(nt, 'SUBTRACT', dx, r * 0.3)
    dz2 = _M(nt, 'SUBTRACT', dz, r * 0.12)
    d2 = _M(nt, 'SQRT', _M(nt, 'ADD', _M(nt, 'MULTIPLY', dx2, dx2), _M(nt, 'MULTIPLY', dz2, dz2)))
    moon = _M(nt, 'MULTIPLY', _M(nt, 'LESS_THAN', d, r * 0.58), _M(nt, 'GREATER_THAN', d2, r * 0.5))
    mask = _M(nt, 'MAXIMUM', mask, moon)
    segs = [((0.0, r), (0.0, r * 2.0)), ((-0.35 * r, r * 0.94), (-0.85 * r, r * 1.75)), ((0.35 * r, r * 0.94), (0.85 * r, r * 1.75)),
            ((-0.55 * r, -0.83 * r), (-0.7 * r, -1.9 * r)), ((0.55 * r, -0.83 * r), (0.62 * r, -2.4 * r))]
    for (ax, az), (bx, bz) in segs:
        mask = _M(nt, 'MAXIMUM', mask, _seg_mask(nt, X, Z, (cx + ax, cz + az), (cx + bx, cz + bz), w * 0.85))
    worn = kit._ramp(nt, kit._noise(nt, P, 7.0, 5, 0.6), wear - 0.12, W((0, 0, 0)), wear + 0.06, W((1, 1, 1)))
    m = kit._mul(nt, kit._mul(nt, mask, worn), amount)
    out = kit._mix(nt, 'MIX', m, col, W(color))
    nt.links.new(out, b.inputs['Base Color'])
    return mat


def glow_lathe(prof, seg, M, name='Glow_Spirit'):
    o = G.obj_bm(G.lathe(prof, seg), "glow", M)
    return glow(o, name)


def flame_lick(base, h, w, lean, curl=0.0, twist=1.2, flat=0.42, rings=14, seg=8, name='Glow_Spirit'):
    """(k4fix) 가늘게 휘어 꼬인 불 혀 하나: 납작한 타원 단면을 굽은 길을 따라 쓸고, 위로 갈수록 가늘어져 한 점으로 모인다.
    base 밑 점, h 높이, w 밑 반폭, lean (x, y) 끝이 쏠리는 양 (t² 로 휜다), curl 옆으로 한 번 너울지는 양, twist 단면이 도는 각도.
    둥근 원뿔 묶음은 테두리 이빨과 합쳐 흰 왕관·종이 조각처럼 읽혔다"""
    base = Vector(base)
    lv = Vector((lean[0], lean[1], 0.0))
    side = Vector((-lean[1], lean[0], 0.0))
    side = side.normalized() if side.length > 1e-6 else Vector((1, 0, 0))
    path = []
    for i in range(rings + 1):
        t = i / rings
        path.append(base + Vector((0, 0, h * t)) + lv * (t * t) + side * (curl * math.sin(math.pi * t * 1.3)))
    bm = bmesh.new()
    rv = []
    for i, p in enumerate(path):
        t = i / rings
        if i == rings:
            rv.append([bm.verts.new(p)])
            continue
        d = (path[i + 1] - p).normalized()
        x = side - d * side.dot(d)
        x = x.normalized() if x.length > 1e-6 else d.orthogonal().normalized()
        y = d.cross(x)
        a_ = w * (1.0 - t) ** 0.8 * (1.0 + 0.18 * math.sin(math.pi * min(1.0, t * 1.6)))
        b_ = a_ * flat
        ang = twist * t
        ca, sa = math.cos(ang), math.sin(ang)
        xr, yr = x * ca + y * sa, -x * sa + y * ca
        ring = []
        for k in range(seg):
            q = 2 * math.pi * k / seg
            ring.append(bm.verts.new(p + xr * (math.cos(q) * a_) + yr * (math.sin(q) * b_)))
        rv.append(ring)
    bm.faces.new(rv[0][::-1])
    for i in range(len(rv) - 1):
        r0, r1 = rv[i], rv[i + 1]
        for k in range(seg):
            j = (k + 1) % seg
            if len(r1) == 1:
                bm.faces.new((r0[k], r0[j], r1[0]))
            else:
                bm.faces.new((r0[k], r0[j], r1[j], r1[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = G.obj_bm(bm, "lick")
    return glow(o, name), path


def place_xf(o, M):
    o.data.transform(M)
    o.data.update()
    return o


def repad_textures(name, low, is_main=None, erode=1, iters=24):
    """굽은 뒤 UV 섬 바깥 여백을 섬 안쪽(테두리 erode 화소를 뺀) 값으로 다시 넓힌다 (albedo JPG·노멀 PNG 를 다시 저장).
    finish 는 여백을 '굽은 직후의 섬 가장자리' 값으로 메운 뒤 flat_hard 로 섬 안쪽 띠만 고친다. 그래서 비스듬히 놓인(회전 배치된) 섬의
    계단 가장자리 바깥 여백에 누운 노멀·밝은 점이 그대로 남아, 필터링·밉맵에서 섬 테두리를 따라 반짝이는 빗살이 된다 (선돌·수정 rim_soft 13%).
    low: 내보낸 LOD0 (is_main(재질 이름) 이 참인 면만 섬으로 친다)"""
    import numpy as np
    from PIL import Image, ImageDraw
    alb = os.path.join(kit.OUT, name + "_albedo.jpg")
    nrm = os.path.join(kit.OUT, name + "_normal.png")
    A = Image.open(alb).convert('RGB'); Nm = Image.open(nrm).convert('RGB')
    w, h = A.size
    ss = 2                                                     # 2배로 그려 화소 가운데 기준으로 줄인다
    cov = Image.new('L', (w * ss, h * ss), 0)
    dr = ImageDraw.Draw(cov)
    me = low.data
    uvl = me.uv_layers.active.data
    mats = [m_.name if m_ else "" for m_ in me.materials]
    is_main = is_main or (lambda n: n.startswith("Main") or n.endswith("_Main"))
    for p_ in me.polygons:
        if not is_main(mats[p_.material_index] if p_.material_index < len(mats) else ""):
            continue
        pts = [(uvl[li].uv.x * w * ss, (1.0 - uvl[li].uv.y) * h * ss) for li in p_.loop_indices]
        dr.polygon(pts, fill=255)
    m = np.asarray(cov.resize((w, h), Image.BOX)) > 250         # 화소가 거의 다 덮인 곳만 섬 안쪽
    for _ in range(erode):
        e = m.copy()
        e[1:] &= m[:-1]; e[:-1] &= m[1:]; e[:, 1:] &= m[:, :-1]; e[:, :-1] &= m[:, 1:]
        m = e
    out = []
    for im in (A, Nm):
        c = np.asarray(im).astype(np.float32)
        v = m.copy()
        c = np.where(v[..., None], c, 0.0)
        for _ in range(iters):
            cs = np.zeros_like(c); ws = np.zeros(v.shape, np.float32)
            vf = v.astype(np.float32)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if not dy and not dx:
                        continue
                    ys, yd = (slice(0, -dy or None), slice(dy, None)) if dy >= 0 else (slice(-dy, None), slice(0, dy))
                    xs, xd = (slice(0, -dx or None), slice(dx, None)) if dx >= 0 else (slice(-dx, None), slice(0, dx))
                    cs[yd, xd] += c[ys, xs] * vf[ys, xs, None]
                    ws[yd, xd] += vf[ys, xs]
            new = (~v) & (ws > 0)
            if not new.any():
                break
            c[new] = cs[new] / ws[new][:, None]
            v = v | new
        orig = np.asarray(im).astype(np.float32)
        c = np.where(v[..., None], c, orig)
        out.append(c)
    n = out[1] / 255.0 * 2.0 - 1.0
    n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-6)
    out[1] = (n * 0.5 + 0.5) * 255.0
    Image.fromarray(np.clip(out[0] + 0.5, 0, 255).astype(np.uint8)).save(alb, quality=92)
    Image.fromarray(np.clip(out[1] + 0.5, 0, 255).astype(np.uint8)).save(nrm, optimize=True, compress_level=9)
    print("REPAD", name, "island %.1f%%" % (100.0 * m.mean()), "albedo_kb", os.path.getsize(alb) // 1024, "normal_kb", os.path.getsize(nrm) // 1024)
    return low


# ═════════════════════════ 1. 낮은 돌담 ═════════════════════════
def stone_wall_low():
    """밭 경계의 마른 돌쌓기 돌담 한 칸 (4 m, 긴 축 = X). 비뚤게 쪼갠 돌을 켜켜이 앞뒤 두 겹으로 쌓고(아래가 넓은 사다리꼴 단면),
    위에는 모로 세운 갓돌 줄. 가운데 오른쪽이 무너져 내려 돌이 앞쪽 발치에 쏟아졌다. 왼쪽 끝은 낮게 허물어지고(갓돌 없음)
    오른쪽 끝은 갓돌까지 남아 — 4칸을 이어도 이음매마다 모양이 달라진다. 밑동은 z -0.25 까지 땅속으로 (비탈 묻힐 여유)."""
    rng = random.Random(4101)
    x0, x1, zb = -2.02, 2.02, -0.25
    top = RU.profile([(-2.05, 0.6), (-1.78, 0.66), (-1.45, 0.76), (-0.9, 0.8), (-0.35, 0.79), (-0.05, 0.72), (0.18, 0.5),
                      (0.42, 0.4), (0.7, 0.47), (0.95, 0.66), (1.3, 0.79), (1.75, 0.82), (2.05, 0.78)])
    hw = lambda z: 0.385 - 0.105 * (z - zb) / 1.05          # 아래가 넓은 단면 (반폭): z -0.25 에서 0.385, z 0.8 에서 0.28
    acc = RU.Acc()
    n_st = 0
    for face in (-1, 1):
        z = zb
        k = 0
        while z < 0.86:
            ch = rng.uniform(0.13, 0.21) if z > 0.0 else rng.uniform(0.16, 0.24)
            rag = 0.1 + 0.08 * (k % 2)              # 양 끝이 켜마다 들쭉날쭉 (이어 놓으면 이웃 칸과 엇갈린다)
            xa = x0 + rng.uniform(-0.04, rag) + (0.06 if face > 0 else 0.0)
            xe = x1 - rng.uniform(-0.04, rag)
            first = True
            while xa < xe - 0.1:
                L = rng.uniform(0.24, 0.52)
                if first:
                    L *= rng.uniform(0.4, 1.0); first = False
                xb = min(xe, xa + L)
                if xe - xb < 0.14:
                    xb = xe
                xm = (xa + xb) / 2
                h_here = top(xm)
                if z + ch * 0.35 < h_here:
                    sh = ch * rng.uniform(0.62, 1.0)                    # 켜 안에서도 높이가 제각각 (벽돌처럼 고르지 않게)
                    if z + sh > h_here + 0.05:
                        sh = max(0.08, h_here + 0.05 - z)
                    d = rng.uniform(0.2, 0.32)
                    through = rng.random() < 0.06 and face < 0
                    if through:
                        d = 2 * hw(z) + 0.03
                    w_out = hw(z + sh / 2) + rng.uniform(-0.012, 0.022)
                    cy = face * (w_out - d / 2)
                    bm = rough_box(rng, xb - xa - 0.025, d, sh - 0.018, jit=0.2, chips=(2, 4), depth=(0.02, 0.06), flakes=(0, 1), bevel=0.006)
                    zc = z + sh / 2 + rng.uniform(-0.015, 0.02)
                    M = Matrix.Translation((xm, cy, zc)) @ Euler((R(rng.uniform(-4, 4)) + face * R(5.5), R(rng.uniform(-7, 7)),
                                                                  R(rng.uniform(-5, 5))), 'XYZ').to_matrix().to_4x4()
                    acc.add(bm, M)
                    n_st += 1
                    if sh < ch * 0.8 and rng.random() < 0.6:         # 낮은 돌 위 틈에 끼운 작은 쐐기돌
                        ps = rough_box(rng, (xb - xa) * rng.uniform(0.3, 0.55), d * 0.7, (ch - sh) * 0.9, jit=0.25, chips=(1, 3), depth=(0.01, 0.03))
                        acc.add(ps, Matrix.Translation((xm + rng.uniform(-0.08, 0.08), cy + face * 0.01, z + sh + (ch - sh) * 0.45))
                                @ Euler((0, R(rng.uniform(-12, 12)), R(rng.uniform(-8, 8))), 'XYZ').to_matrix().to_4x4())
                xa = xb
            z += ch
            k += 1
    # 심 (앞뒤 돌 사이를 메운 잡석) — 윗선보다 낮게
    core = RU.core_prism(x0 + 0.06, x1 - 0.06, lambda x: top(x) - 0.06, -0.22, 0.22, zb, inset=0.0, drop=0.02, step=0.12, jag=0.05, seed=3)
    acc.add(core)
    # 갓돌: 모로 세운 돌 줄 (윗선이 0.68 넘는 곳만, 비스듬히 한쪽으로 기대고, 군데군데 빠졌다)
    x = -1.78
    lean = R(6)
    while x < 1.98:
        tw = rng.uniform(0.07, 0.13)
        xm = x + tw / 2
        if top(xm) > 0.68 and rng.random() > 0.08:
            hh = rng.uniform(0.13, 0.21)
            wd = 2 * hw(top(xm)) + rng.uniform(-0.04, 0.04)
            bm = rough_box(rng, tw, wd, hh, jit=0.2, chips=(2, 4), depth=(0.015, 0.045), flakes=(0, 1), bevel=0.006)
            ln = lean + R(rng.uniform(-6, 6))
            M = Matrix.Translation((xm, rng.uniform(-0.02, 0.02), top(xm) + hh / 2 - 0.035)) @ Euler((R(rng.uniform(-3, 3)), ln, R(rng.uniform(-6, 6))), 'XYZ').to_matrix().to_4x4()
            acc.add(bm, M)
            n_st += 1
        x += tw + rng.uniform(0.0, 0.025)
    # 무너진 곳 발치에 쏟아진 돌 (앞쪽에 많이, 뒤에 조금) + 떨어진 갓돌
    # (크기 규격: 깊이 0.8 m ±15% → 쏟아진 돌도 벽 발치 ±0.46 m 안에 기대어 쌓였다)
    for i in range(14):
        side = -1 if i < 10 else 1
        px = rng.uniform(-0.1, 1.0)
        s_ = rng.uniform(0.13, 0.24)
        py = side * (0.37 - s_ * 0.3 + rng.uniform(-0.02, 0.01))      # i3: 깊이 규격 0.92 안 (i2 0.99)
        bm = rough_box(rng, s_ * rng.uniform(1.0, 1.5), s_ * rng.uniform(0.7, 1.0), s_ * rng.uniform(0.5, 0.8), jit=0.2, chips=(2, 4))
        pz = s_ * 0.2 + rng.uniform(0.0, 0.12)
        M = Matrix.Translation((px, py, pz)) @ Euler((R(rng.uniform(-18, 18)) - side * R(15), R(rng.uniform(-22, 22)), R(rng.uniform(-14, 14))), 'XYZ').to_matrix().to_4x4()
        acc.add(bm, M)
    for (px, rz) in ((0.32, 8), (0.66, -10)):                 # 무너진 자리 위에 비스듬히 얹힌 갓돌
        bm = rough_box(rng, 0.1, 0.42, 0.18, jit=0.18)
        acc.add(bm, Matrix.Translation((px, -0.08, top(px) + 0.02)) @ Euler((R(62), R(10), R(rz)), 'XYZ').to_matrix().to_4x4())
    print("STONES stone_wall_low", n_st)
    body = acc.obj("wall_low")
    base = carve(body, 0.008, *STONE3(1.0, wear=1.4, cracks=0.55), seed=41, base=True)
    m = paint3("stone_wall_low_src", FIELD_STONE, h=1.05, k=1.0, moss=0.6, moss_color=MOSS_OLIVE, moss_patch=1.6, moss_low=0.7,
               moss_low_h=0.3, dirt=0.75, dirt_h=0.22, streaks=0.1, edge=0.5, edge_w=0.014, edge_gain=0.9, piece_var=0.6, piece_val=0.2,
               grime=0.55, grime_h=0.1, cavity=1.0, ao=0.42, stains=0.55, lichen=0.3, lichen_color=(0.46, 0.47, 0.4), lichen_scale=16.0,
               contrast=0.22, gain=1.12, hue_var=0.12, shadow=SHADOW_GREY, splash=0.7, splash_z=0.06, splash_h=0.16, light=0.9)
    G.blotch(m, (0.33, 0.32, 0.27), 2.6, 0.45, 0.46, 0.62)      # 넓은 물때 (돌마다 고르지 않게)
    set_mat(body, m)
    low = kit.decimated(base, 7600)
    delete(base)
    if low.matrix_world != Matrix.Identity(4):
        xf_all(low)
    drop_faces(low, lambda c, n: c.z < zb + 0.05 and n.z < -0.6)        # 땅속 바닥면
    print("LOW stone_wall_low", tri_count(low))
    # 발치 풀 (앞뒤로 들쭉날쭉) + 무너진 윗면의 풀 한두 포기
    # 풀: 무너진 윗면과 왼쪽 낮은 끝에만 (발치 풀은 크기 규격 깊이 0.8 m 를 넘기고, 월드 쪽 풀이 덮는다)
    cards = N.Cards()
    gr = random.Random(77)
    grass_at(cards, gr, [(0.25, 0.0, 0.44), (0.5, 0.06, 0.42), (0.72, -0.05, 0.47), (-1.9, 0.02, 0.62)], (0.18, 0.32), (0.16, 0.24), 0.5)
    wt = lambda c, n: 0.15 if c.z < -0.04 else (0.5 if n.z < -0.5 else 1.0)
    lod0 = finish3("stone_wall_low", [body], [low], extras=[cards.obj("grass")], cage=0.01, cage_reach=0.1, lod1=0.35, lod2=0.12,
                   uv_margin=0.001, uv_weight=wt)
    return repad_textures("stone_wall_low", lod0)


# ═════════════════════════ 2. 선돌 ═════════════════════════
def _loft(rings, cap=True):
    """고리 목록(같은 개수의 점) → 닫힌 메쉬"""
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(rings[0])
    for a, b in zip(vr, vr[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap:
        bm.faces.new(vr[0][::-1])
        bm.faces.new(vr[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def chip_convex_away(o, rng, n, size, zmin=-1e9, avoid=None, gap=1.4, sharp_deg=25, push=0.35):
    """N.chip_convex 와 같은 볼록 다면체 깨짐이되, avoid(점, 바깥 방향) 이 참인 자리(새김 면 등)는 건너뛰고
    깨짐끼리 gap × (두 크기 합) 보다 가깝지 않게 둔다. (k4r: 선돌 앞면에서 깨짐 둘이 겹쳐 얇은 조각 판 + 어두운 삼각 구멍이 남았다)"""
    cs, used = [], []
    for p, out in edge_points(o, n * 4, rng, sharp_deg, zmin):
        if len(cs) >= n:
            break
        if avoid is not None and avoid(p, out):
            continue
        s_ = rng.uniform(*size)
        if any((p - q).length < gap * (s_ + sq) * 0.5 for q, sq in used):
            continue
        c = sphere(1.0, (0, 0, 0), (s_, s_ * rng.uniform(0.6, 0.9), s_ * rng.uniform(0.5, 0.8)), 1,
                   rot=(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)))
        slice_rock(c, rng, 5, (0.1, 0.3))
        c.data.transform(Matrix.Translation(p + out * s_ * push))
        c.data.update()
        cs.append(c)
        used.append((p, s_))
    if cs:
        cut(o, cs)
    print("CHIPS", o.name, len(cs))
    return o


def spiral_strokes(cx, cz, r0, r1, turns, th_end, sign=1, step=0.03, wob=0.0, rng=None):
    """XZ 평면 나선 획 (r0 안 → r1 밖, 끝 각도 th_end 에서 끝난다, sign=1 반시계로 감아 나감). 손으로 판 듯 반지름이 조금 흔들린다"""
    L = 2 * math.pi * turns * (r0 + r1) / 2
    n = max(8, int(L / step))
    th0 = th_end - sign * 2 * math.pi * turns
    pts = []
    for i in range(n + 1):
        t = i / n
        th = th0 + sign * 2 * math.pi * turns * t
        r = r0 + (r1 - r0) * t
        if rng is not None and wob:
            r *= 1.0 + rng.uniform(-wob, wob)
        pts.append(Vector((cx + r * math.cos(th), -2.0, cz + r * math.sin(th))))
    return list(zip(pts, pts[1:])), pts


def bezier_strokes(a, b, c, step=0.03):
    """XZ 2차 베지어 획 (a → b, 조절점 c)"""
    a, b, c = Vector(a), Vector(b), Vector(c)
    n = max(3, int(((c - a).length + (b - c).length) / step))
    pts = [a * (1 - t) ** 2 + c * 2 * t * (1 - t) + b * t * t for t in [i / n for i in range(n + 1)]]
    return list(zip(pts, pts[1:]))


def smooth_near_strokes(o, strokes, radius=0.026, iters=5, factor=0.5, front=(0, -1, 0), step=0.004):
    """(k4fix) 새김 홈 둘레만 문질러 편다: carve(octree) 가 얕은 V 홈 입술을 3 mm 칸 계단으로 만들어, 굽은 노멀에서 홈 둘레가
    끊긴 검은 점선으로 보였다 (1~2 m). 획(XZ, 앞면) 에서 radius 안, 앞을 보는 정점만 smooth_vert 로 펴서 닳은 옛 새김처럼 만든다"""
    from mathutils.kdtree import KDTree
    pts = []
    for a, b in strokes:
        a, b = Vector((a[0], 0.0, a[2])), Vector((b[0], 0.0, b[2]))
        n = max(1, int((b - a).length / step))
        pts += [a.lerp(b, i / n) for i in range(n + 1)]
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    fv = Vector(front)
    bm = bmesh.new(); bm.from_mesh(o.data)
    # 앞 절반의 정점 (법선으로 고르면 입술에 접힌 잔 조각 — 법선이 위·아래를 보는 — 이 빠져 찢긴 종이 테두리로 남았다)
    sel = [v for v in bm.verts if v.co.dot(fv) > 0.1 and kd.find(Vector((v.co.x, 0.0, v.co.z)))[2] < radius]
    for _ in range(iters):
        bmesh.ops.smooth_vert(bm, verts=sel, factor=factor, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(o.data); bm.free()
    o.data.update()
    print("SMOOTH_NEAR", o.name, len(sel))
    return o


def standing_stone():
    """선돌: 키 큰 거친 돌 한 덩이 (3.2 m, 그중 아래 0.3 m 는 META.sink 로 땅에 묻힌다). 아래가 넓고 위로 좁아지며 한쪽으로 기울고,
    윗면은 비스듬히 깨졌다. 깊은 평면으로 깎은 큰 면 + 모서리 깨짐 + 평면으로 떨어진 계단 자국 (가로 층·네모 블록이 없어 굴뚝처럼 보이지 않는다).
    앞면(-Y)에는 닳아 희미한 옛 새김: 비스듬히 이어진 두 나선 + 작은 잔구멍 셋 (이 게임용).
    k4fix: 고리 + 아래로 갈라진 줄기는 4 m 에서 막대 사람·♀ 로 읽혀 나선으로 바꿨다. 사람·기호처럼 서는 축이 없다"""
    rng = random.Random(5202)
    rings = []
    prof = [(0.0, 1.0, 1.0), (0.35, 1.02, 1.0), (1.2, 0.97, 0.98), (2.1, 0.86, 0.86), (2.75, 0.74, 0.74), (3.3, 0.6, 0.64)]
    base_r = [rng.uniform(0.86, 1.1) for _ in range(9)]
    for z, sx, sy in prof:
        t = z / 3.3
        ring = []
        for i in range(9):
            a = 2 * math.pi * i / 9 + 0.2
            rr = base_r[i] * rng.uniform(0.95, 1.05)
            ring.append(Vector((math.cos(a) * 0.6 * sx * rr + 0.26 * t * t, math.sin(a) * 0.4 * sy * rr - 0.06 * t, z)))   # 위로 갈수록 +X 로 기운다
        rings.append(ring)
    o = G.obj_bm(_loft(rings), "stone")
    N.facet(o, rng, 12, (0.04, 0.12), nz=(-0.15, 0.3))
    # 윗면: 비스듬히 깨진 꼭대기 (+X 쪽이 높다) + 어깨 하나가 크게 떨어져 나감
    bm = bmesh.new(); bm.from_mesh(o.data)
    G.bm_cut(bm, (0.0, 0.0, 3.1), (-0.3, 0.1, 1.0))
    G.bm_cut(bm, (-0.36, -0.1, 2.85), (-0.8, -0.25, 0.75))
    G.bm_cut(bm, (0.3, 0.1, 3.05), (0.5, 0.3, 1.0))
    bm.to_mesh(o.data); bm.free(); o.data.update()
    below_cut(o, 0.0)
    # k4fix: 앞면은 깨지 않는다 — 깨짐 둘이 겹쳐 얇은 조각 판·흰 삼각형이 생겼다
    # (f1: 새김 아래 z 1.1 의 앞면 깨짐 둘이 여전히 옅은 면 + 어두운 삼각 구멍으로 읽혔다 → 앞을 보는 깨짐은 모두 뺀다, 옆·뒤·윗어깨만)
    front = lambda p, out: out.y < -0.3
    chip_convex_away(o, rng, 5, (0.14, 0.26), zmin=0.6, avoid=front, gap=1.5, push=0.42)
    origin0(o)
    low = lowpoly(o, z=-0.02)          # 바닥면은 남긴다 (지우면 열린 테두리를 따라 굽기 빗살이 생긴다, 텍셀은 0.1 배)
    # 희미한 새김 (앞면 z 1.55~2.3): 위 왼쪽 큰 나선(밖으로 감겨 나와 아래 오른쪽으로 흐름) → 아래 오른쪽 작은 나선(반대로 감겨 듦)
    # + 둘레 잔구멍(컵 자국) 셋. 넓고 얕은 V 홈 (벽이 완만해 굽기 광선이 스치지 않는다)
    # (첫 시안: 큰 나선 꼬리가 오른쪽 아래 작은 고리로 떨어져 '?' 처럼 읽혔다 → 비슷한 크기 둘을 비스듬히 마주 감은 이중 나선)
    er = random.Random(77)
    sa, pa = spiral_strokes(0.15, 2.07, 0.02, 0.13, 2.0, R(215), sign=1, step=0.028, wob=0.03, rng=er)
    sb, pb = spiral_strokes(-0.07, 1.75, 0.02, 0.115, 1.8, R(35), sign=1, step=0.028, wob=0.03, rng=er)
    st = sa + sb
    st += bezier_strokes(pa[-1], pb[-1], (0.03, -2.0, 1.96), step=0.028)
    for (x_, z_) in ((0.3, 1.72), (0.22, 1.56), (-0.2, 2.16)):
        st += G.arc_strokes(x_, z_, 0.017, 0, 2 * math.pi, -2.0, 8)
    esrc = copy(o)
    engrave_surface(o, [(Vector(a), Vector(b)) for a, b in st], (0, -1, 0), 0.032, 0.007, step=0.028, floor=0.5)
    co, fi = ROCK3(1.5, 0.22, chisel=0.3)                # 금은 적게 (가로 금이 돌을 켜켜이 쌓은 블록처럼 보이게 한다)
    fi = fi + [{'t': 'chisel', 'scale': 4.2, 'amp': 0.0028, 'tilt': 1.0, 'jitter': 0.5, 'wall': 0.3, 'warp': 0.1, 'cover': 0.6},
               {'t': 'grain', 'scale': 45.0, 'amp': 0.0007}]
    carve(o, 0.006, co, fi, seed=52, pieces=False, mode='octree', edge_from=esrc)
    smooth_near_strokes(o, st, 0.03, 8, 0.5)
    # k4fix: facet_var 0.3 → 0.14 (깨진 면 하나가 몸통보다 0.22 밝은 흰 삼각형이 됐다), cavity_s 0.35 (새김 입술의 AO 표본 잡음 = 검은 점선),
    #        moss 0.7 → 0.55 (홈이 만나는 곳의 노란 이끼 점)
    m = paint3("standing_stone_src", MEGALITH, h=3.2, k=1.5, cells=0.7, piece_var=0.4, piece_val=0.08, facet_var=0.14, light=0.9,
               moss=0.55, moss_color=MOSS_OLIVE, moss_patch=1.5, moss_low=0.8, moss_low_h=0.85, dirt=0.65, dirt_h=0.6, edge=0.0, streaks=0.2, ao=0.5,
               grain=0.25, tooling=0.0, speckle=0.45, strokes=0.7, stains=0.6, edge_mode='attr', lichen=0.0, contrast=0.24,
               strata=0.0, rain=0.8, rain_h=1.6, rain_color=(0.22, 0.24, 0.21), splash=0.7, splash_z=0.3, splash_h=0.3,
               hue_var=0.25, shadow=SHADOW_GREY, cavity=1.0, cavity_s=0.35, gain=1.08)
    G.blotch(m, (0.3, 0.3, 0.26), 1.6, 0.5, 0.46, 0.62)
    G.blotch(m, (0.2, 0.21, 0.19), 4.0, 0.35, 0.5, 0.64)        # 잔 물때 (깨진 면도 새것처럼 밝지 않게)
    set_mat(o, m)
    print("LOW standing_stone", tri_count(low))
    cards = N.Cards()
    gr = random.Random(9)
    pts = []
    for i in range(12):
        a = 2 * math.pi * (i + gr.random() * 0.6) / 12
        pts.append((math.cos(a) * 0.5 + 0.03, math.sin(a) * 0.34, 0.28))
    grass_at(cards, gr, pts, (0.25, 0.45), (0.18, 0.26), 0.45)
    wt = lambda c, n: 0.1 if n.z < -0.9 else (0.45 if c.z < 0.3 else (0.8 if n.z > 0.6 else 1.0))
    # i2: 이음매 테두리 빗살(rim_soft 12%) — hard 22 로도 13% 그대로였다. i3: 거의 모든 UV 이음매를 단단한 모서리로 (hard 5) →
    #     우리를 이음매마다 쪼개 굽고(split_cage), 이음매 둘레 6 화소를 섬 안쪽 값으로 다시 메운다(flat_hard). 깎은 돌이라 면 꺾임이 보여도 된다
    lod0 = finish3("standing_stone", [o], [low], extras=[cards.obj("grass")], cage=0.012, cage_reach=0.1, uv_angle=30, hard=5,
                   uv_margin=0.002, uv_weight=wt, flat_hard=6)
    return repad_textures("standing_stone", lod0)


# ═════════════════════════ 3. 쇠 울타리 ═════════════════════════
def iron_fence():
    """묘지 쇠 울타리 한 칸 (3 m, 긴 축 = X): 양 끝 네모 기둥(왼쪽은 갓·뾰족 머리, 오른쪽은 위가 녹슬어 부러졌다), 가로대 둘,
    창살 19개 (위 끝 창촉, 위 가로대 아래 고리 띠). 휜 창살, 빠진 창살, 옆으로 꺾인 창살, 처진 가로대. 밑동은 z -0.25 까지 (묻힐 여유)"""
    rng = random.Random(3303)
    acc = RU.Acc()
    zb = -0.22
    # 기둥
    for (x, w_, h_, broken) in ((-1.45, 0.085, 1.5, False), (1.455, 0.075, 1.3, True)):
        if broken:
            v, f = RU.bar_path([(x, 0, zb), (x, 0, 1.1), (x + 0.012, 0.004, h_)], w_)
        else:
            v, f = RU.bar_path([(x, 0, zb), (x, 0, h_)], w_)
        acc.add_raw(v, f)
        v, f = RU.bar_path([(x, 0, -0.02), (x, 0, 0.06)], w_ + 0.04)            # 밑동 고리
        acc.add_raw(v, f)
        if not broken:
            v, f = RU.bar_path([(x, 0, h_), (x, 0, h_ + 0.03)], w_ + 0.05)      # 갓
            acc.add_raw(v, f)
            v, f = RU.spear((x, 0, h_ + 0.03), (0, 0, 1), 0.13, 0.07, 0.07, 0.03)
            acc.add_raw(v, f)
        else:
            v, f = RU.bar_path([(x + 0.012, 0.004, h_ - 0.02), (x + 0.02, 0.01, h_ + 0.03)], w_ * 0.55)   # 부러진 끝 (가늘게 삭은 심)
            acc.add_raw(v, f)
    # 가로대 (위 가로대는 가운데 오른쪽이 처졌다)
    sag = lambda x: -0.05 * math.exp(-((x - 0.35) / 0.45) ** 2)
    for z in (0.15, 1.18):
        pts = [(-1.41 + 2.82 * i / 12, 0, z + (sag(-1.41 + 2.82 * i / 12) if z > 1 else 0.0)) for i in range(13)]
        v, f = RU.bar_path(pts, 0.05, 0.016)
        acc.add_raw(v, f)
    xs = [-1.26 + i * 0.14 for i in range(19)]
    tips = []
    for i, x in enumerate(xs):
        zt = 1.38 + rng.uniform(-0.01, 0.01)
        if i == 7:                                   # 빠진 창살: 밑동만 부러져 남았다
            v, f = RU.bar_path([(x, 0, zb), (x, 0, 0.2), (x + 0.01, -0.004, 0.31)], 0.021)
            acc.add_raw(v, f)
            continue
        if i == 4:                                   # 앞으로 불룩 휜 창살
            pts = [(x, 0, zb), (x, 0, 0.15), (x + 0.012, -0.05, 0.4), (x + 0.02, -0.095, 0.65), (x + 0.012, -0.06, 0.93), (x, 0, 1.18), (x, 0, zt)]
            tip_d = (0, 0, 1)
        elif i == 8:                                 # 빠진 이웃 쪽으로 기운 창살 (가로대에 걸려 있다)
            pts = [(x, 0, zb), (x, 0, 0.15), (x - 0.03, 0.0, 0.72), (x - 0.055, 0, 1.18), (x - 0.075, 0, zt - 0.02)]
            tip_d = (-0.05, 0, 1)
        elif i == 12:                                # 위가 옆으로 꺾였다
            pts = [(x, 0, zb), (x, 0, 1.18 + sag(x)), (x + 0.03, -0.01, 1.28), (x + 0.12, -0.035, 1.35)]
            tip_d = (0.8, -0.25, 0.45)
        elif i == 16:                                # 뒤로 조금 휜 창살, 촉이 떨어져 나갔다
            pts = [(x, 0, zb), (x, 0, 0.15), (x, 0.03, 0.62), (x, 0.045, 0.9), (x, 0.01, 1.18), (x, 0.0, zt - 0.06)]
            tip_d = None
        else:
            lean = rng.uniform(-0.01, 0.01)
            pts = [(x, 0, zb), (x, 0, 1.18 + sag(x)), (x + lean, 0, zt)]
            tip_d = (lean * 3, 0, 1)
        v, f = RU.bar_path(pts, 0.021)
        acc.add_raw(v, f)
        if tip_d is not None and i != 2:
            v, f = RU.spear(pts[-1], tip_d, 0.13, 0.052, 0.014)
            acc.add_raw(v, f)
            tips.append(pts[-1])
    # 위 가로대 아래 고리 띠 (창살 사이마다 고리 하나, 두 개는 깨져 빠졌다)
    for i in range(len(xs) - 1):
        if i in (6, 7, 13):
            continue
        cx = (xs[i] + xs[i + 1]) / 2
        z = 1.18 + sag(cx) - 0.07
        v, f = RU.torus_raw(0.05, 0.0065, Matrix.Translation((cx, 0, z)) @ Matrix.Rotation(R(90), 4, 'X'), seg=12, minor=4)
        acc.add_raw(v, f)
    iron = acc.obj("fence_iron")
    low = lowpoly(iron)
    drop_faces(low, lambda c, n: c.z < zb + 0.01 and n.z < -0.9)
    # i2: 원본 = 저폴리 그대로 (2 cm 쇠살을 리메시하면 모서리가 둥글어져 굽은 노멀이 70도 넘게 눕는다: i1 steep 5.5%).
    #     잔 결(두들긴 자국·녹 구멍)은 칠의 bump 로 노멀맵에 넣는다
    h = copy(iron)
    delete(iron)
    sub = h.modifiers.new('sub', 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = 1
    apply_all(h)
    m = paint3("iron_fence_src", IRON_DARK, h=1.5, k=0.6, moss=0.15, moss_color=MOSS_DEAD, dirt=0.7, dirt_h=0.25, edge=0.4, edge_w=0.004,
               edge_gain=0.8, edge_mode='bevel', cavity=0.9, ao=0.08, light=0.6, streaks=0.55, stains=0.6, speckle=0.6, strokes=0.4,
               tooling=0.3, grain=0.8, bump=0.6, hue_var=0.2, piece_var=0.0, contrast=0.2, gain=1.05, shadow=(0.05, 0.03, 0.04), rain=0.6,
               rain_h=0.8, rain_color=(0.25, 0.14, 0.09))
    G.blotch(m, (0.17, 0.075, 0.042), 5.0, 0.4, 0.5, 0.64, mode='MIX')           # 녹 얼룩 (군데군데)
    set_mat(h, m)
    print("LOW iron_fence", tri_count(low))
    webs = [RU.web_card((1.41, -0.02, 1.15), (-1, 0, 0), (0, 0, -1), 0.24, flip=True)]
    wt = lambda c, n: 0.3 if c.z < -0.03 else 1.0
    return finish3("iron_fence", [h], [low], extras=webs, cage=0.004, cage_reach=0.03, hard=55, uv_margin=0.002,
                   uv_weight=wt, lod1=0.5)


# ═════════════════════════ 4. 찢긴 깃발 ═════════════════════════
def _sheet(x0, x1, z0, z1, d, y0, th):
    """XZ 격자 판 (두께 th, 앞면 y0 - th/2): 굽은 뒤 찢기 위한 바탕"""
    nx, nz = int((x1 - x0) / d) + 1, int((z1 - z0) / d) + 1
    bm = bmesh.new()
    grid = [[bm.verts.new((x0 + (x1 - x0) * i / (nx - 1), y0, z0 + (z1 - z0) * j / (nz - 1))) for i in range(nx)] for j in range(nz)]
    for j in range(nz - 1):
        for i in range(nx - 1):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    o = G.obj_bm(bm, "sheet")
    m = o.modifiers.new('sol', 'SOLIDIFY'); m.thickness = th; m.offset = 0.0
    apply_all(o)
    return o


def banner_torn():
    """찢긴 깃발: 비바람에 바랜 나무 장대(4.2 m, 아래 0.15 m 묻힘) + 가로대(밧줄로 묶음) + 쇠 창촉, 가로대에 매달린 검붉은 천.
    천 아래쪽은 길게 찢어진 띠가 바람에 앞으로 들려 날리고, 구멍 셋과 오른쪽 가장자리가 뜯겨 나갔다. 바랜 문장(이 게임용 사령 군기)이
    군데군데 벗겨졌다. 멀리서 '장대 + 가로대 + 늘어진 찢긴 천' 실루엣으로 깃발이 읽히게"""
    rng = random.Random(6404)
    # 장대 (살짝 굽고 +X 로 기운다)
    pole_path = [Vector((0.0, 0.0, 0.0)), Vector((0.012, 0.004, 1.2)), Vector((0.03, 0.0, 2.4)), Vector((0.05, -0.006, 3.4)), Vector((0.07, 0.0, 4.02))]
    pts, rads = N.resample(pole_path, [0.066, 0.062, 0.058, 0.054, 0.05], 0.25)
    v, f = N.tube(pts, rads, 12, bumps=0.06, seed=3, tip=False)
    pole = mesh_from("pole", v, f)
    ytop = -0.09
    bar_pts = [Vector((-0.66, ytop, 3.665)), Vector((-0.2, ytop, 3.655)), Vector((0.25, ytop, 3.648)), Vector((0.7, ytop, 3.632))]
    bp, br = N.resample(bar_pts, [0.034, 0.033, 0.032, 0.03], 0.1)
    v, f = N.tube(bp, br, 10, bumps=0.05, seed=5, tip=False)
    xbar = mesh_from("xbar", v, f)
    # 쇠 창촉 + 깃고리
    acc = RU.Acc()
    tip_p = pts[-1]
    v, f = RU.bar_path([tip_p - Vector((0, 0, 0.07)), tip_p + Vector((0, 0, 0.02))], 0.095)
    acc.add_raw(v, f)
    v, f = RU.spear(tip_p + Vector((0, 0, 0.02)), (0.03, 0, 1), 0.2, 0.075, 0.02, 0.022)
    acc.add_raw(v, f)
    iron = acc.obj("banner_iron")
    # 밧줄: 가로대와 장대가 엇갈린 곳을 X 자로 감고, 천 양쪽 끝을 가로대에 묶은 고리
    racc = RU.Acc()
    jc = Vector((0.065, ytop * 0.5, 3.66))
    for k, ang in enumerate((45, -45, 40, -40)):
        M = Matrix.Translation(jc + Vector((0, 0, 0.012 * (k - 1.5)))) @ Matrix.Rotation(R(90), 4, 'X') @ Matrix.Rotation(R(ang), 4, 'Z')
        v, f = RU.torus_raw(0.072, 0.0085, M @ Matrix.Diagonal((1.0, 0.62, 1.0, 1.0)), seg=14, minor=5)
        racc.add_raw(v, f)
    for x in (-0.57, 0.6):
        for dx in (-0.015, 0.015):
            M = Matrix.Translation((x + dx, ytop, 3.655)) @ Matrix.Rotation(R(90), 4, 'Y')
            v, f = RU.torus_raw(0.04, 0.007, M, seg=12, minor=4)
            racc.add_raw(v, f)
    rope = racc.obj("rope")
    # 천: 판 → 찢기(구멍·띠·뜯긴 가장자리) → 바람에 굽히기
    cx0, cx1, cz0, cz1 = -0.55, 0.6, 1.25, 3.62
    cloth = _sheet(cx0, cx1, cz0, cz1, 0.045, 0.0, 0.012)
    cs = []
    gaps = [(-0.37, 2.55, 0.09), (-0.17, 2.85, 0.07), (0.05, 2.35, 0.11), (0.24, 2.7, 0.08), (0.43, 2.45, 0.1)]
    for gx, gz, gw in gaps:                         # 띠 사이 갈라진 틈 (위는 좁고 아래로 벌어진 들쭉날쭉한 쐐기)
        poly = [(gx - 0.006, gz), (gx + 0.006, gz)]
        n = 5
        for i in range(1, n + 1):
            t = i / n
            z = gz - (gz - 1.1) * t
            poly.append((gx + gw * t * (0.7 + 0.3 * rng.random()) + rng.uniform(-0.012, 0.012), z))
        right = poly[2:]
        left = []
        for i in range(n, 0, -1):
            t = i / n
            z = gz - (gz - 1.1) * t
            left.append((gx - gw * t * (0.7 + 0.3 * rng.random()) + rng.uniform(-0.012, 0.012), z))
        cs.append(G.obj_bm(G.bm_poly([poly[0], poly[1]] + right + left, -0.3, 0.3), "tear"))
    # 띠마다 끝 길이가 다르고 끝이 들쭉날쭉하다
    edges = [cx0 - 0.05] + [g[0] for g in gaps] + [cx1 + 0.05]
    ends = [1.62, 1.35, 1.9, 1.48, 2.05, 1.72]
    for (xa, xb), ze in zip(zip(edges, edges[1:]), ends):
        poly = [(xa, 1.0), (xb, 1.0)]
        k = 6
        for i in range(k, -1, -1):
            t = i / k
            poly.append((xa + (xb - xa) * t, ze + rng.uniform(-0.07, 0.07) + (0.05 if i in (0, k) else 0.0)))
        cs.append(G.obj_bm(G.bm_poly(poly, -0.3, 0.3), "end"))
    for hx, hz, hr in ((-0.27, 3.2, 0.07), (0.36, 3.36, 0.05), (-0.3, 2.62, 0.08)):      # 구멍 (문장은 비켜서)
        poly = []
        for i in range(8):
            a = 2 * math.pi * i / 8 + rng.uniform(-0.2, 0.2)
            rr = hr * rng.uniform(0.6, 1.25)
            poly.append((hx + math.cos(a) * rr * 1.2, hz + math.sin(a) * rr * 0.8))
        cs.append(G.obj_bm(G.bm_poly(poly, -0.3, 0.3), "hole"))
    cs.append(G.obj_bm(G.bm_poly([(0.7, 2.35), (0.52, 2.55), (0.55, 2.68), (0.47, 2.86), (0.53, 3.02), (0.7, 3.12)], -0.3, 0.3), "rip"))
    cut(cloth, cs)

    def wind(p):
        t = max(0.0, (cz1 - p.z) / (cz1 - cz0))
        s_ = min(1.0, t * 5.0)                           # 윗단은 가로대 자루 안에 머문다
        y = ytop - s_ * (0.03 + 0.02 * (0.5 + 0.5 * math.sin(5.2 * p.x + 1.4 * p.z)) + 0.015 * (0.5 + 0.5 * math.sin(2.7 * p.z + 0.8)))
        y -= 0.26 * t * t + 0.08 * t ** 3 * (0.5 + 0.5 * math.sin(13.0 * p.x + 2.0))
        x = p.x + 0.12 * t * t + 0.02 * math.sin(3.0 * p.z) * t
        z = p.z + 0.06 * t ** 3 * (0.5 + 0.5 * math.sin(9.0 * p.x))       # 띠 끝이 바람에 조금 들린다
        return Vector((x, y + p.y, z))
    for vtx in cloth.data.vertices:
        vtx.co = wind(vtx.co)
    cloth.data.update()
    # 천 윗단: 가로대를 감싼 자루 (천과 같은 재질)
    sleeve = cyl(0.046, 1.2, (0.025, ytop, 3.66), 12, rot=(0, R(90), 0))
    cloth = join([cloth, sleeve])
    # 저폴리 = 깨끗한 형태들
    lows = [lowpoly(pole), lowpoly(xbar), lowpoly(iron), lowpoly(rope), lowpoly(cloth, tris=3600)]
    # 원본: 장대·가로대 나뭇결, 쇠 녹 구멍, 밧줄 꼬임, 천 주름·올
    pg = G.grain_guide([p for p in pts], (0, 0, 1))
    remesh(pole, 0.004)
    surface(pole, G.WOOD_LAYERS + [{'t': 'cracks', 'scale': 2.0, 'width': 0.02, 'depth': 0.006, 'warp': 0.05, 'cover': 0.25, 'cover_scale': 0.8}], 61, guide=pg)
    delete(pg)
    xg = G.grain_guide([p for p in bp], (1, 0, 0))
    remesh(xbar, 0.0035)
    surface(xbar, G.WOOD_LAYERS, 62, guide=xg)
    delete(xg)
    wm = paint3("banner_wood", WOOD_GREY, h=4.2, k=0.6, moss=0.3, moss_color=MOSS_DEAD, dirt=0.8, dirt_h=0.45, edge=0.3, cavity=0.9,
                ao=0.05, streaks=0.5, stains=0.6, strokes=0.5, tooling=0.0, grain=0.5, hue_var=0.2, piece_var=0.0, contrast=0.2,
                gain=1.1, shadow=SHADOW_GREY, light=0.6, rain=0.5, rain_h=1.2, rain_color=(0.2, 0.18, 0.16))
    set_mat(pole, wm); set_mat(xbar, wm)
    carve(iron, 0.003, [], [{'t': 'lumps', 'scale': 9.0, 'amp': 0.0012}, {'t': 'pits', 'scale': 70.0, 'depth': 0.0012, 'cover': 0.7}],
          seed=63, pieces=False, edges=False)
    set_mat(iron, paint3("banner_iron", RUST, h=4.2, k=0.4, moss=0.0, dirt=0.0, edge=0.4, cavity=0.9, ao=0.04, streaks=0.4,
                         stains=0.6, tooling=0.0, grain=0.3, piece_var=0.0, gain=1.15, shadow=(0.05, 0.03, 0.04)))
    remesh(rope, 0.0025)
    surface(rope, [{'t': 'grain', 'scale': 160.0, 'amp': 0.0012}, {'t': 'lumps', 'scale': 40.0, 'amp': 0.001}], 64)
    set_mat(rope, paint3("banner_rope", ROPE, h=4.2, k=0.3, moss=0.0, dirt=0.0, edge=0.3, cavity=1.0, ao=0.03, streaks=0.0,
                         stains=0.4, tooling=0.0, grain=0.8, piece_var=0.0, gain=1.1, shadow=SHADOW_GREY))
    ch = copy(cloth)
    delete(cloth)
    sub = ch.modifiers.new('sub', 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = 2; sub.render_levels = 2
    apply_all(ch)
    surface(ch, [{'t': 'lumps', 'scale': 7.0, 'amp': 0.0018}, {'t': 'grain', 'scale': 170.0, 'amp': 0.00035}], 65)
    cm = paint3("banner_cloth", CLOTH_RED, h=3.7, k=0.5, moss=0.0, dirt=0.0, edge=0.35, edge_w=0.006, cavity=0.7, ao=0.03,
                streaks=0.45, stains=0.8, strokes=0.6, tooling=0.0, grain=0.7, hue_var=0.15, piece_var=0.0, contrast=0.2, gain=1.15,
                shadow=(0.06, 0.03, 0.04), light=0.5, speckle=0.3)
    G.blotch(cm, (0.3, 0.2, 0.18), 1.4, 0.3, 0.52, 0.7, mode='MIX')             # 볕에 바랜 얼룩 (크고 옅게)
    sigil_paint(cm, 0.07, 2.98, 0.17, 0.024, (0.46, 0.41, 0.34), 0.6, 0.5)
    G.dirt_low(cm, 1.2, 2.2, 0.75, (0.05, 0.035, 0.03))                          # 아래 띠 끝: 흙탕물에 젖었다 마른 때
    set_mat(ch, cm)
    print("LOW banner_torn", sum(tri_count(l) for l in lows))
    cards = N.Cards()
    gr = random.Random(12)
    grass_at(cards, gr, [(0.09, 0.03, 0.12), (-0.06, -0.03, 0.12), (0.03, 0.06, 0.12)], (0.3, 0.5), (0.12, 0.18), 0.5)
    wt = lambda c, n: 0.4 if c.z < 0.15 else 1.0
    return finish3("banner_torn", [pole, xbar, iron, rope, ch], lows, extras=[cards.obj("grass")], cage=0.003, cage_reach=0.03,
                   uv_margin=0.002, uv_weight=wt, lod1=0.5)


# ═════════════════════════ 5. 영혼 수정 노두 ═════════════════════════
def hex_crystal(base, d, r, L, rng, tip=0.26, taper=0.86, sides=6, rot0=None, broken=None):
    """육각 수정 기둥 + 뾰족 끝 (bmesh). base 에서 d 방향 길이 L (밑은 0.3 m 더 바위 속으로). broken: (높이 비율, 기울기) 면 끝이 비스듬히 부러짐"""
    d = Vector(d).normalized()
    q = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    a0 = rng.uniform(0, 6.28) if rot0 is None else rot0
    jr = [rng.uniform(0.9, 1.1) for _ in range(sides)]
    bm = bmesh.new()

    def ring(z, s):
        return [bm.verts.new(Vector((math.cos(a0 + 2 * math.pi * i / sides) * r * s * jr[i],
                                     math.sin(a0 + 2 * math.pi * i / sides) * r * s * jr[i], z))) for i in range(sides)]
    r0 = ring(-0.3, 1.0)
    r1 = ring(L * (1 - tip), taper)
    ap = bm.verts.new(Vector((r * rng.uniform(-0.18, 0.18), r * rng.uniform(-0.18, 0.18), L)))
    bm.faces.new(r0[::-1])
    for i in range(sides):
        j = (i + 1) % sides
        bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
        bm.faces.new((r1[i], r1[j], ap))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if broken:
        h_, tl = broken
        G.bm_cut(bm, (0, 0, L * h_), (math.sin(tl), 0.3 * math.sin(tl), math.cos(tl)))
    bm.transform(Matrix.Translation(Vector(base)) @ q)
    return bm, a0


def slit_cutter(p, d, nrm, w, depth, length, rng):
    """수정 겉면을 따라 길게 갈라진 틈 커터 (p 면 위 점, d 수정 방향, nrm 면 바깥 방향). 틈 벽은 비스듬해 굽기 광선이 스치지 않는다"""
    d = Vector(d).normalized(); nrm = Vector(nrm).normalized()
    ax = nrm.cross(d).normalized()
    vs = []
    for zz, k in ((-length / 2, 0.55), (-length / 4, 1.0), (length / 4, 0.9), (length / 2, 0.4)):
        for hw_, hy in ((w * k * 0.35, -depth), (w * k, 0.03)):
            jx = rng.uniform(-0.15, 0.15) * w
            vs.append((zz, -hw_ + jx, hy)); vs.append((zz, hw_ + jx, hy))
    verts = [Vector(p) + d * zz + ax * x + nrm * y for zz, x, y in vs]
    faces = []
    for i in range(3):
        a = i * 4; b_ = a + 4
        faces += [(a, a + 1, b_ + 1, b_), (a + 2, b_ + 2, b_ + 3, a + 3), (a, b_, b_ + 2, a + 2), (a + 1, a + 3, b_ + 3, b_ + 1)]
    faces += [(0, 2, 3, 1), (12, 13, 15, 14)]
    o = mesh_from("slit", verts, faces)
    return o


def soul_crystal():
    """영혼 수정 노두: 땅에서 솟은 각진 바위(폭 약 1.2 m, 높이 약 0.85 m)가 비스듬히 갈라졌고, 그 틈에서 육각 수정 무리가 여러 각도로
    뻗었다 (가장 큰 것 2.4 m). 수정 겉은 어두운 청록 → 끝으로 갈수록 옅은 청록, 밑동과 갈라진 틈 둘레는 안쪽 빛이 비친 밝은 청록.
    큰 수정 둘은 모서리를 따라 여러 갈래로 길게 갈라진 틈으로 안쪽 빛나는 심(Glow_Spirit)이 보이고, 바위 틈에 박힌 작은 뾰족 조각 셋은
    통째로 빛난다. 바위는 수정 밑동 둘레가 청록으로 물들었다. 아래 0.2 m 는 META.sink 로 묻힌다.
    k4fix: 바위가 작아(폭 0.8, 높이 0.45) 묻히면 '흙에 꽂힌 수정'이 됐다 → 바위를 키우고 갈라진 틈에서 수정이 나오게.
    가는 흰 막대 틈·흰 알약 수정이 형광등처럼 읽혔다 → 모서리를 따라 갈래진 틈, 밝은 청록 그러데이션, 뾰족 조각"""
    rng = random.Random(7505)
    rock = N.facet_mass(rng, (1.72, 1.52, 1.78), (0.0, 0.0, 0.08), planes=14, depth=(0.06, 0.15), rz=R(20), chamfer=10)
    below_cut(rock, 0.0)
    # 비스듬히 갈라진 틈 (u 방향으로 뻗은 V 홈, 한쪽 끝은 닫혀 있다): 수정 무리가 이 틈에서 솟는다
    ua = R(32)
    u = Vector((math.cos(ua), math.sin(ua), 0.0)); w_ = Vector((-u.y, u.x, 0.0))
    sec = [(-0.3, 1.3), (-0.05, 0.5), (0.04, 0.48), (0.26, 1.3)]
    vs = [(u * L_ + w_ * x_ + Vector((0, 0, z_))) for L_ in (-1.0, 0.42) for x_, z_ in sec]
    cleft = mesh_from("cleft", [tuple(v) for v in vs], [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)])
    cut(rock, [cleft])
    N.chip_convex(rock, rng, 4, (0.14, 0.24), zmin=0.35)
    rd = rock.dimensions
    print("ROCK soul_crystal", tuple(round(v, 3) for v in rd))
    C = lambda s_, t_, z_: tuple(u * s_ + w_ * t_ + Vector((0, 0, z_)))
    specs = [   # (밑 점, 방향, 반지름, 길이, 부러짐, 심) — 밑 점은 틈 바닥 (u 방향 s, 옆 t)
        (C(0.0, -0.02, 0.6), (0.06, 0.03, 1.0), 0.2, 1.8, None, True),
        (C(-0.3, 0.0, 0.62), (-0.42, -0.18, 1.0), 0.15, 1.2, None, True),
        (C(0.2, -0.04, 0.6), (0.45, -0.3, 1.0), 0.12, 0.95, (0.82, 0.5), False),
        (C(-0.12, 0.06, 0.62), (0.1, 0.5, 1.0), 0.11, 0.82, None, False),
        (C(-0.5, 0.05, 0.7), (-0.5, 0.4, 0.75), 0.085, 0.55, None, False),
        (C(0.3, 0.04, 0.62), (0.65, 0.25, 0.65), 0.075, 0.48, (0.7, -0.6), False),
        (C(-0.2, -0.06, 0.6), (-0.15, -0.6, 0.75), 0.075, 0.52, None, False),
    ]
    shells, cores, notch, lit = [], [], [], []
    for (b, d, r, L, brk, core) in specs:
        bm, a0 = hex_crystal(b, d, r, L, rng, broken=brk)
        sh = G.obj_bm(bm, "crystal")
        shells.append(sh)
        if core:
            cb, _ = hex_crystal(b, d, r * 0.55, L * 0.93, random.Random(int(r * 1000)), rot0=a0)
            cores.append(glow(G.obj_bm(cb, "core"), 'Glow_Spirit'))
            dd = Vector(d).normalized()
            q = dd.to_track_quat('Z', 'Y').to_matrix()
            # 모서리(꼭짓점 방향)를 따라 긴 틈 + 틈에서 비스듬히 갈라진 잔가지 틈 (형광등 막대처럼 곧고 하나뿐이면 안 된다)
            cuts = ((0.36, 0, 0.5, 2), (0.55, 2, 0.34, 1), (0.3, 4, 0.3, 1)) if r > 0.17 else ((0.42, 1, 0.46, 2), (0.5, 4, 0.28, 1))
            for (t, k, ln, nb) in cuts:
                fa = a0 + k * math.pi / 3
                nrm = q @ Vector((math.cos(fa), math.sin(fa), 0.0))
                p = Vector(b) + dd * (t * L) + nrm * (r * 0.97)
                notch.append(slit_cutter(p, dd, nrm, r * 0.42, r * 0.62, ln * L, rng))
                lit.append(p)
                for j in range(nb):
                    sg = -1 if j == 0 else 1
                    zz = rng.uniform(-0.25, 0.25) * ln * L
                    bd = (Matrix.Rotation(sg * R(rng.uniform(28, 40)), 3, nrm) @ dd).normalized()
                    pb = p + dd * zz + bd * ln * L * 0.2
                    notch.append(slit_cutter(pb, bd, nrm, r * 0.3, r * 0.5, ln * L * 0.4, rng))
    # 바위 틈에 박혀 통째로 빛나는 작은 뾰족 조각 무리 셋 (갈라진 틈 끝과 옆 틈 — 위에서 광선을 쏘아 바위 겉에 박는다).
    # 처음 시안은 바위 옆구리에서 옆으로 뻗어 흰 가시·이빨처럼 읽혔다 → 거의 곧추세우고 둘씩 무리 지었다
    bpy.context.view_layer.update()
    glows = []
    for (s0, t0, r, L) in ((0.52, 0.12, 0.042, 0.3), (-0.66, -0.12, 0.038, 0.26), (0.05, 0.36, 0.034, 0.22)):
        top = Vector(C(s0, t0, 2.5))
        loc, nrm = surf_hit(rock, top, (0, 0, -1))
        if loc is None:
            continue
        for k, (rk, Lk, off) in enumerate(((1.0, 1.0, 0.0), (0.7, 0.62, 0.07))):
            q = loc + w_ * off * (1 if s0 > 0 else -1) + u * off * 0.4
            d = (nrm * 0.3 + Vector((0, 0, 1)) * 0.7 + w_ * (0.25 * (k * 2 - 1))).normalized()
            bm, _ = hex_crystal(q - Vector((0, 0, 0.04)), d, r * rk, L * Lk, rng, tip=0.62, taper=0.75, sides=5)
            glows.append(glow(G.obj_bm(bm, "gcrys"), 'Glow_Spirit'))
        lit.append(loc)
    cr = join(shells)
    cut(cr, notch)
    # 저폴리: 바위 + 수정 겉을 한 덩어리로 (바위 속에 묻힌 수정 밑동 면이 UV 를 차지하지 않게)
    lsrc = copy(rock)
    union(lsrc, [copy(cr)])
    low = lowpoly(lsrc, z=-0.02)
    delete(lsrc)                       # 바닥면은 남긴다 (선돌과 같은 까닭, 텍셀 0.1 배)
    # 원본: 바위 (옥트리 + ROCK3), 수정 (옥트리 + 속 금 몇 줄)
    origin0(rock)
    co, fi = ROCK3(0.8, 0.6, chisel=0.3)
    carve(rock, 0.004, co, fi + [{'t': 'grain', 'scale': 45.0, 'amp': 0.0006}], seed=75, pieces=False, mode='octree')
    rm = paint3("soul_crystal_rock", MEGALITH, h=1.0, k=0.8, cells=0.5, piece_var=0.3, piece_val=0.08, facet_var=0.3, light=1.0,
                moss=0.7, moss_patch=1.6, moss_low=0.6, moss_low_h=0.4, dirt=0.6, dirt_h=0.4, edge=0.0, streaks=0.2, ao=0.35,
                grain=0.25, tooling=0.0, strokes=0.7, stains=0.5, edge_mode='attr', lichen=0.0, contrast=0.25, hue_var=0.2,
                shadow=SHADOW_GREY, splash=0.6, splash_z=0.2, splash_h=0.2, gain=1.05)
    G.tint_near(rm, (0.0, 0.0, 0.8), 0.7, (0.1, 0.28, 0.27), 0.5)            # 수정 밑동 둘레가 청록으로 물들었다
    set_mat(rock, rm)
    origin0(cr)
    carve(cr, 0.0035, [], [{'t': 'cracks', 'scale': 2.4, 'width': 0.016, 'depth': 0.0035, 'warp': 0.06, 'cover': 0.12, 'cover_scale': 1.0},
                           {'t': 'chisel', 'scale': 7.0, 'amp': 0.0012, 'tilt': 0.6, 'jitter': 0.5, 'wall': 0.25, 'cover': 0.5}],
          seed=76, pieces=False, mode='octree')
    cm = paint3("soul_crystal_src", CRYSTAL, h=2.4, k=0.7, moss=0.0, dirt=0.3, dirt_h=0.7, edge=0.6, edge_w=0.008, edge_gain=0.8,
                edge_mode='attr', cavity=0.9, ao=0.12, light=1.3, streaks=0.0, stains=0.35, strokes=0.35, tooling=0.0, grain=0.15,
                hue_var=0.12, piece_var=0.0, contrast=0.35, gain=1.0, shadow=(0.015, 0.05, 0.06), speckle=0.2)
    G.blotch(cm, (0.3, 0.62, 0.6), 3.2, 0.3, 0.55, 0.7, mode='MIX')               # 흐린 속 무늬 (빛이 고인 곳)
    # k4fix: 안쪽 빛이 비친 그러데이션 — 밑동(바위 틈) 쪽이 밝은 청록, 위로 갈수록 본래 깊은 청록. 갈라진 틈 둘레도 밝게 번진다
    G.dirt_low(cm, 0.55, 1.45, 0.62, (0.32, 0.74, 0.7))
    for p_ in lit:
        G.tint_near(cm, tuple(p_), 0.16, (0.42, 0.86, 0.8), 0.6)
    set_mat(cr, cm)
    print("LOW soul_crystal", tri_count(low))
    cards = N.Cards()
    gr = random.Random(5)
    pts = [(math.cos(a) * 0.58, math.sin(a) * 0.5, 0.18) for a in (0.3, 1.2, 2.2, 3.0, 3.9, 4.8, 5.6)]
    grass_at(cards, gr, pts, (0.2, 0.34), (0.16, 0.24), 0.55)
    wt = lambda c, n: 0.1 if n.z < -0.9 else (0.45 if c.z < 0.2 else 1.0)
    # i2: 바위 깎은 면끼리 얕게 만나는 이음매의 테두리 빗살(rim_soft 7%) → hard 22 로는 그대로 (10.6%).
    # i3: 선돌과 같은 처방 — 거의 모든 이음매를 단단한 모서리로(hard 5) + 이음매 띠 다시 메우기(flat_hard 6) + 바닥면 남김
    lod0 = finish3("soul_crystal", [rock, cr], [low], extras=cores + glows + [cards.obj("grass")], cage=0.008, cage_reach=0.08,
                   uv_angle=30, hard=5, uv_margin=0.002, uv_weight=wt, flat_hard=6)
    return repad_textures("soul_crystal", lod0)


# ═════════════════════════ 6. 화로 ═════════════════════════
def brazier():
    """화로: 세 갈래로 휜 쇠다리(가운데 고리로 묶음) 위 두들겨 편 쇠 그릇, 테두리에 비스듬한 쇠 이빨(하나는 꺾이고 하나는 빠졌다).
    그릇에는 숯과 뼛조각, 그 위로 창백한 청록 영혼불(Glow_Spirit) 혀가 너울거린다. 숯 사이 잉걸도 같은 빛"""
    rng = random.Random(8606)
    acc = RU.Acc()
    prof = [(0.0, 0.76), (0.13, 0.765), (0.27, 0.83), (0.37, 0.92), (0.43, 1.01), (0.445, 1.05), (0.43, 1.065), (0.395, 1.06),
            (0.36, 1.0), (0.26, 0.92), (0.12, 0.87), (0.0, 0.865)]
    bowl = G.lathe(prof, 32)
    bowl.verts.ensure_lookup_table()
    bm_bowl = bowl
    me = bpy.data.meshes.new("_b"); bm_bowl.to_mesh(me); bm_bowl.free()
    acc.add_raw([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    bpy.data.meshes.remove(me)
    v, f = RU.lathe([(0.0, 0.70), (0.085, 0.70), (0.095, 0.74), (0.12, 0.775), (0.0, 0.78)], 16)        # 그릇 밑 목
    acc.add_raw(v, f)
    # 테두리 이빨 9 개 (하나 빠짐, 하나 꺾임)
    for i in range(9):
        if i == 6:
            continue
        a = 2 * math.pi * i / 9 + 0.15
        bend = R(38) if i == 2 else R(rng.uniform(-5, 5))
        bmt = G.bm_poly([(-0.035, 0.0), (0.035, 0.0), (0.01, 0.13), (-0.004, 0.14)], -0.009, 0.009, 'y')
        M = Matrix.Rotation(a - math.pi / 2, 4, 'Z') @ Matrix.Translation((0, 0.432, 1.04)) @ Matrix.Rotation(R(-14) + bend, 4, 'X')
        bmt.transform(M)
        me = bpy.data.meshes.new("_t"); bmt.to_mesh(me); bmt.free()
        acc.add_raw([v_.co.copy() for v_ in me.vertices], [tuple(p.vertices) for p in me.polygons])
        bpy.data.meshes.remove(me)
    # 다리 셋 (S 자로 휘어 바깥으로 벌어진다) + 발 + 묶는 고리
    rz = [(0.11, 0.78), (0.2, 0.7), (0.28, 0.55), (0.3, 0.4), (0.33, 0.22), (0.42, 0.07), (0.49, 0.015)]
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.5
        ca, sa = math.cos(a), math.sin(a)
        wob = 0.025 if k == 1 else 0.0                        # 한 다리는 조금 휘었다
        pts = [(r_ * ca - sa * wob * math.sin(math.pi * i / 6), r_ * sa + ca * wob * math.sin(math.pi * i / 6), z_) for i, (r_, z_) in enumerate(rz)]
        v, f = RU.bar_path(pts, 0.04, 0.03, ref=(-sa, ca, 0))
        acc.add_raw(v, f)
        foot = G.bm_box(0.11, 0.07, 0.03, Matrix.Translation((0.5 * ca, 0.5 * sa, 0.015)) @ Matrix.Rotation(a, 4, 'Z'))
        me = bpy.data.meshes.new("_f"); foot.to_mesh(me); foot.free()
        acc.add_raw([v_.co.copy() for v_ in me.vertices], [tuple(p.vertices) for p in me.polygons])
        bpy.data.meshes.remove(me)
    v, f = RU.torus_raw(0.302, 0.013, Matrix.Translation((0, 0, 0.42)), seg=30, minor=5)
    acc.add_raw(v, f)
    iron = acc.obj("brazier_iron")
    low_i = lowpoly(iron)
    # 숯·뼛조각 (그릇 안 둔덕)
    coal = []
    for i in range(16):
        a = rng.uniform(0, 6.28); rr = math.sqrt(rng.random()) * 0.3
        s_ = rng.uniform(0.045, 0.085)
        coal.append(G.chunk((math.cos(a) * rr, math.sin(a) * rr, 0.985 + 0.05 * (1 - rr / 0.3) + rng.uniform(-0.01, 0.01)),
                            (s_, s_ * rng.uniform(0.7, 1.0), s_ * 0.6), rng, 7, (0.08, 0.3), sub=1))
    co = join(coal)
    low_c = lowpoly(co)
    bitems = []
    for (p, yaw, L, r) in (((0.12, -0.08, 1.04), 30, 0.2, 0.014), ((-0.15, 0.06, 1.035), -50, 0.17, 0.012), ((0.02, 0.17, 1.03), 100, 0.14, 0.011)):
        M = Matrix.Translation(p) @ Matrix.Rotation(R(yaw), 4, 'Z') @ Matrix.Rotation(R(rng.uniform(-12, 12)), 4, 'Y')
        for it in G.long_bone(L, r, rng):
            c, rad = it[0], it[1]
            rot = it[2] if len(it) > 2 else (0, 0, 0)
            bitems.append((M @ Vector(c), rad, tuple((M.to_3x3() @ Euler(rot).to_matrix()).to_euler())))
    bones = G.blobs(bitems, 2, "bones")
    remesh(bones, 0.003)
    low_b = kit.decimated(bones, 260)
    surface(bones, [{'t': 'lumps', 'scale': 18, 'amp': 0.001}, {'t': 'cracks', 'scale': 9, 'width': 0.02, 'depth': 0.0015, 'cover': 0.3},
                    {'t': 'pits', 'scale': 90, 'depth': 0.0007, 'cover': 0.6}], 87)
    set_mat(bones, paint3("brazier_bone", G.BONE_DARK, h=1.05, k=0.3, moss=0.0, dirt=0.0, edge=0.5, cavity=1.0, ao=0.02, streaks=0.0,
                          stains=0.7, tooling=0.0, grain=0.3, piece_var=0.0, gain=0.85, shadow=(0.08, 0.06, 0.06)))
    # 원본: 쇠 (두들긴 평면 자국 + 녹 구멍), 숯 (잔 금)
    # i2: 원본 = 저폴리 그대로 + 칠 bump (다리·이빨 3~4 cm 쇠를 리메시하면 모서리가 둥글어져 i1 steep 6.5%)
    sub = iron.modifiers.new('sub', 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = 1
    apply_all(iron)
    im = paint3("brazier_iron_src", IRON_DARK, h=1.1, k=0.4, moss=0.0, dirt=0.6, dirt_h=0.2, edge=0.4, edge_w=0.004, edge_gain=0.8,
                edge_mode='bevel', cavity=0.9, ao=0.06, light=0.7, streaks=0.5, stains=0.6, speckle=0.5, strokes=0.4, tooling=0.35,
                grain=0.8, bump=0.6, hue_var=0.2, piece_var=0.0, contrast=0.2, gain=1.05, shadow=(0.05, 0.03, 0.04), rain=0.5, rain_h=0.5,
                rain_color=(0.24, 0.14, 0.09))
    G.blotch(im, (0.17, 0.075, 0.042), 6.0, 0.4, 0.5, 0.64, mode='MIX')
    G.tint_near(im, (0.0, 0.0, 1.02), 0.4, (0.012, 0.012, 0.014), 0.85)          # 그릇 안 그을음
    set_mat(iron, im)
    remesh(co, 0.003)
    surface(co, [{'t': 'cracks', 'scale': 14, 'width': 0.06, 'depth': 0.003, 'cover': 0.7, 'cover_scale': 2.0},
                 {'t': 'lumps', 'scale': 12, 'amp': 0.0015}], 88)
    cmat = paint3("brazier_coal", COAL, h=1.05, k=0.3, moss=0.4, moss_color=ASH_COL, moss_patch=6.0, dirt=0.0, edge=0.3, cavity=1.0,
                  ao=0.03, streaks=0.0, stains=0.3, tooling=0.0, grain=0.3, piece_var=0.0, gain=1.0, shadow=(0.02, 0.02, 0.02))
    G.tint_near(cmat, (0.0, 0.0, 1.0), 0.18, (0.1, 0.32, 0.3), 0.5)               # 영혼불에 물든 숯
    set_mat(co, cmat)
    # 영혼불 혀 (Glow_Spirit) + 잉걸
    # k4fix: 둥근 원뿔 10개 → 가늘게 휘어 꼬인 혀 6개 (높이를 크게 다르게, 밑은 둘레에서 나와 끝이 가운데로 모인다, 둘은 끝이 갈라진다)
    fr = random.Random(8607)
    fl = []
    licks = [  # (각도, 밑 반지름, 높이, 밑 반폭, 갈라짐)
        (0.3, 0.04, 0.4, 0.042, True), (1.5, 0.15, 0.27, 0.032, False), (2.6, 0.19, 0.17, 0.028, False),
        (3.6, 0.11, 0.33, 0.036, True), (4.6, 0.2, 0.14, 0.026, False), (5.5, 0.16, 0.22, 0.03, False)]
    for (a, rr, h_, w0, split) in licks:
        c, s_ = math.cos(a), math.sin(a)
        b0 = (c * rr, s_ * rr, 0.995 + 0.04 * (1 - rr / 0.3))
        ln = (-c * rr * 0.85 + fr.uniform(-0.03, 0.03), -s_ * rr * 0.85 + fr.uniform(-0.03, 0.03))     # 끝이 가운데로
        o, path = flame_lick(b0, h_, w0, ln, curl=fr.choice((-1, 1)) * fr.uniform(0.03, 0.055), twist=fr.uniform(-2.2, 2.2))
        fl.append(o)
        if split:                                      # 끝이 갈라진 곁가지 혀 (본 혀 0.55 높이에서 옆으로 벌어진다)
            pm = path[int(len(path) * 0.55)]
            o2, _ = flame_lick(pm - Vector((0, 0, 0.02)), h_ * 0.42, w0 * 0.45, (ln[1] * 0.6 + 0.04, -ln[0] * 0.6 - 0.02),
                               curl=0.015, twist=1.5)
            fl.append(o2)
    for (a, rr, h_, w0) in ((0.9, 0.05, 0.1, 0.065), (3.1, 0.07, 0.085, 0.06), (5.0, 0.06, 0.09, 0.055)):   # 숯 위 낮고 넓은 불 바탕 (혀들이 한 불에서 솟게)
        o, _ = flame_lick((math.cos(a) * rr, math.sin(a) * rr, 1.0), h_, w0, (-math.cos(a) * rr * 0.6, -math.sin(a) * rr * 0.6), curl=0.01, twist=0.8, flat=0.6)
        fl.append(o)
    for i in range(7):
        a = rng.uniform(0, 6.28); rr = rng.uniform(0.05, 0.27)
        e = G.chunk((math.cos(a) * rr, math.sin(a) * rr, 1.015 + 0.03 * (1 - rr / 0.3)), (0.024, 0.02, 0.013), rng, 6, (0.1, 0.3), sub=1)
        fl.append(glow(e, 'Glow_Spirit'))
    print("LOW brazier", tri_count(low_i) + tri_count(low_c) + tri_count(low_b))
    wt = lambda c, n: 0.6 if (c.z > 0.85 and (c.x * c.x + c.y * c.y) < 0.36 * 0.36 and n.z > 0.3) else 1.0     # 그릇 안 (숯에 가린다)
    return finish3("brazier", [iron, co, bones], [low_i, low_c, low_b], extras=fl, cage=0.004, cage_reach=0.04, hard=55,
                   uv_margin=0.002, uv_weight=wt)


# ═════════════════════════ 7. 모닥불 ═════════════════════════
def campfire():
    """꺼져 가는 모닥불: 그을린 돌 고리(돌 하나는 밖으로 굴렀다) 안에 재가 깔리고, 숯이 된 장작이 무너진 원뿔로 기대 있다.
    장작 끝과 재 속 잉걸만 주황으로 빛난다(Glow_Ember). 바깥 끝은 아직 갈색 나무, 안쪽으로 갈수록 거북등처럼 갈라진 숯"""
    rng = random.Random(9707)
    stones = []
    for i in range(11):
        a = 2 * math.pi * i / 11 + rng.uniform(-0.1, 0.1)
        rr = 0.53 + rng.uniform(-0.03, 0.04)
        if i == 5:
            rr = 0.66                                   # 밖으로 굴러간 돌
        s = (rng.uniform(0.13, 0.18), rng.uniform(0.1, 0.13), rng.uniform(0.08, 0.11))
        st = G.chunk((0, 0, 0), s, rng, 9, (0.08, 0.26), sub=1)
        st.data.transform(Matrix.Translation((math.cos(a) * rr, math.sin(a) * rr, s[2] * 0.45)) @ Matrix.Rotation(a + rng.uniform(-0.3, 0.3), 4, 'Z')
                          @ Matrix.Rotation(R(rng.uniform(-10, 10)), 4, 'X'))
        st.data.update()
        stones.append(st)
    so = join(stones)
    low_s = lowpoly(so, z=-0.01)
    drop_faces(low_s, lambda c, n: c.z < 0.0 and n.z < -0.5)
    # 재 둔덕
    ash = sphere(1.0, (0, 0, -0.04), (0.44, 0.42, 0.085), 3)
    remesh(ash, 0.008)
    low_a = kit.decimated(ash, 320)
    drop_faces(low_a, lambda c, n: c.z < -0.01)
    # 장작 (무너진 원뿔: 셋은 가운데로 기대고, 둘은 재 위에 엇갈려 누웠다)
    logs = []
    lspecs = [((0.5, -0.1, 0.11), (0.05, 0.02, 0.34), 0.045), ((-0.36, 0.36, 0.1), (-0.03, 0.05, 0.31), 0.04),
              ((-0.26, -0.44, 0.1), (0.02, -0.06, 0.26), 0.038), ((-0.42, -0.12, 0.07), (0.22, 0.1, 0.07), 0.036),
              ((0.12, 0.42, 0.07), (0.04, -0.2, 0.065), 0.034), ((0.3, 0.3, 0.06), (0.06, 0.06, 0.2), 0.03)]
    tips = []
    for k, (a, b, r) in enumerate(lspecs):
        a, b = Vector(a), Vector(b)
        path = [a.lerp(b, t) + Vector((0, 0, 0.015 * math.sin(math.pi * t))) for t in (0.0, 0.25, 0.5, 0.75, 0.92, 1.0)]
        rads = [r, r * 0.98, r * 0.95, r * 0.85, r * 0.6, r * 0.25]
        v, f = N.tube(path, rads, 9, lobes=3, lobe_amp=0.09, twist=2.0, bumps=0.08, seed=k, tip=True)
        logs.append(mesh_from("log", v, f))
        tips.append((b, (b - a).normalized(), r))
    lo = join(logs)
    low_l = lowpoly(lo)
    # 원본
    origin0(so)
    co_, fi_ = ROCK3(0.15, 0.5, chisel=0.3)
    carve(so, 0.004, co_, fi_, seed=97, mode='octree', pieces=True)
    smat = paint3("campfire_stone", MEGALITH, h=0.25, k=0.2, cells=0.15, piece_var=0.8, piece_val=0.15, facet_var=0.3, moss=0.5,
                  moss_patch=1.5, dirt=0.6, dirt_h=0.06, edge=0.0, streaks=0.0, ao=0.04, grain=0.25, tooling=0.0, strokes=0.6,
                  stains=0.6, edge_mode='attr', lichen=0.0, contrast=0.25, hue_var=0.2, shadow=SHADOW_GREY, gain=1.08)
    G.tint_near(smat, (0.0, 0.0, 0.1), 0.85, (0.015, 0.014, 0.014), 0.9)        # 불 쪽으로 그을림
    set_mat(so, smat)
    surface(ash, [{'t': 'lumps', 'scale': 5, 'amp': 0.012}, {'t': 'lumps', 'scale': 22, 'amp': 0.003},
                  {'t': 'pits', 'scale': 40, 'depth': 0.002, 'cover': 0.6}], 98)
    am = paint3("campfire_ash", ASH, h=0.1, k=0.2, moss=0.0, dirt=0.0, edge=0.0, cavity=0.8, ao=0.03, streaks=0.0, stains=0.7,
                strokes=0.6, speckle=0.7, tooling=0.0, grain=0.3, piece_var=0.0, gain=1.0, shadow=SHADOW_GREY, light=0.4)
    G.tint_near(am, (0.0, 0.0, 0.0), 0.3, (0.05, 0.025, 0.018), 0.7)              # 가운데 검게 탄 자리
    set_mat(ash, am)
    remesh(lo, 0.0025)
    surface(lo, [{'t': 'cracks', 'scale': 18, 'width': 0.1, 'depth': 0.004, 'warp': 0.15, 'cover': 0.8, 'cover_scale': 3.0},
                 {'t': 'cracks', 'scale': 40, 'width': 0.12, 'depth': 0.0015, 'warp': 0.15, 'cover': 0.6, 'cover_scale': 5.0},
                 {'t': 'lumps', 'scale': 10, 'amp': 0.0015}], 99)
    lm = paint3("campfire_log", WOOD_BURNT, h=0.4, k=0.3, moss=0.3, moss_color=ASH_COL, moss_patch=7.0, dirt=0.3, dirt_h=0.05,
                edge=0.3, cavity=1.0, ao=0.02, streaks=0.0, stains=0.5, tooling=0.0, grain=0.5, piece_var=0.0, gain=1.0,
                shadow=(0.02, 0.015, 0.015))
    G.tint_near(lm, (0.0, 0.0, 0.15), 0.95, (0.012, 0.011, 0.011), 1.0)           # 안쪽으로 갈수록 숯 (바깥 끝만 갈색 나무)
    set_mat(lo, lm)
    # 잉걸 (Glow_Ember): 장작 안쪽 끝 셋 + 재 속 조각
    emb = []
    for (b, d, r) in tips[:3]:
        e = G.chunk(tuple(b - d * 0.035), (r * 0.42, r * 0.42, r * 0.5), rng, 6, (0.1, 0.3), sub=1)
        emb.append(glow(e, 'Glow_Ember'))
    for i in range(12):
        a = rng.uniform(0, 6.28); rr = rng.uniform(0.02, 0.26)
        s_ = rng.uniform(0.016, 0.036)
        e = G.chunk((math.cos(a) * rr, math.sin(a) * rr, 0.035 - 0.012 * rr / 0.24), (s_, s_ * 0.8, s_ * 0.5), rng, 6, (0.1, 0.3), sub=1)
        emb.append(glow(e, 'Glow_Ember'))
    print("LOW campfire", tri_count(low_s) + tri_count(low_a) + tri_count(low_l))
    return finish3("campfire", [so, ash, lo], [low_s, low_a, low_l], extras=emb, cage=0.004, cage_reach=0.04, uv_margin=0.002)


# ═════════════════════════ 8. 석관 ═════════════════════════
# (k4fix) 지어낸 비라틴 글꼴: 곧은 줄기 + 갈고리·활·물결·잔가지·점. 라틴 글자(A·L·X…)로 읽히지 않게 둥근 획과 비스듬한 잔가지를 섞었다.
#   좌표: 글자 칸 x -0.35~0.35, z -0.5~0.5 (글자 높이 배)
RUNES = [
    [[(0, -0.5), (0, 0.5), (0.18, 0.47), (0.3, 0.3), (0.28, 0.15)]],                                         # 줄기 + 위 갈고리
    [[(-0.32, -0.1), (-0.23, 0.13), (0, 0.22), (0.23, 0.13), (0.32, -0.1)], [(0, -0.36), (0.03, -0.33)]],      # 엎은 활 + 점
    [[(0.1, -0.5), (0.1, 0.5)], [(0.1, 0.35), (-0.25, 0.05)], [(0.1, 0.0), (-0.25, -0.3)]],                     # 줄기 + 왼쪽 아래 잔가지 둘
    [[(-0.05, -0.5), (-0.05, 0.12)], [(-0.05, 0.12), (0.12, 0.14), (0.22, 0.3), (0.12, 0.46), (-0.05, 0.42), (-0.05, 0.12)]],   # 줄기 + 위 고리
    [[(-0.32, 0.0), (-0.16, 0.2), (0, 0.0), (0.16, -0.2), (0.32, 0.0)], [(0.16, -0.2), (0.16, -0.5)]],         # 물결 + 꼬리
    [[(-0.2, 0.5), (0, 0.4), (0, -0.4), (0.2, -0.5)]],                                                          # 양끝 갈고리 줄기
    [[(0, -0.5), (0, 0.5)], [(0, 0.3), (0.25, 0.38)], [(0, 0.0), (-0.25, 0.08)], [(0, -0.3), (0.25, -0.22)]],   # 엇갈린 눈금
    [[(-0.3, -0.5), (-0.3, 0.2), (0, 0.5), (0.3, 0.2), (0.3, -0.1)]],                                           # 한 다리 짧은 아치
    [[(0, -0.5), (0, 0.5)], [(-0.3, -0.15), (0.3, 0.25)]],                                                     # 비스듬히 그은 줄기
    [[(0.18, -0.5), (0.18, 0.2), (0.0, 0.45), (-0.22, 0.32), (-0.16, 0.08), (0.04, 0.12)]],                    # 위가 안으로 말린 줄기
    [[(-0.3, 0.45), (0.3, 0.45)], [(0.0, 0.45), (-0.2, -0.05), (0.15, -0.5)]],                                  # 덮개 + 굽은 줄기
]


def rune_strokes(rng, cx, zc, width, h, y, wear=0.12, blots=()):
    """한 줄 지어낸 글자 획 (y 평면 위, XZ, 가운데 정렬). wear: 획이 닳아 없어질 확률, blots: [(x, z, 반지름)] 안은 대부분 닳아 지워졌다"""
    lw, gap, wgap = h * 0.78, h * 0.26, h * 0.8
    letters, x, first = [], 0.0, True
    while True:
        n = rng.randint(2, 5)
        need = n * lw + (n - 1) * gap + (0 if first else wgap)
        if x + need > width and not first:
            break
        if not first:
            x += wgap
        for k in range(n):
            if x + lw > width:
                break
            letters.append((x + lw / 2, rng.randrange(len(RUNES))))
            x += lw + gap
        x -= gap
        first = False
    out = []
    for lx, gi in letters:
        px = cx - x / 2 + lx
        pz = zc + rng.uniform(-0.04, 0.04) * h
        sl = rng.uniform(-0.06, 0.06)                          # 손으로 판 글자마다 조금 기울었다
        for line in RUNES[gi]:
            pts = [Vector((px + (a + sl * b) * lw + rng.uniform(-0.03, 0.03) * h, y, pz + b * h + rng.uniform(-0.03, 0.03) * h))
                   for a, b in line]
            for p0, p1 in zip(pts, pts[1:]):
                m = (p0 + p1) / 2
                worn = any((m.x - bx) ** 2 + (m.z - bz) ** 2 < br * br for bx, bz, br in blots)
                if rng.random() < (0.82 if worn else wear):
                    continue
                out.append((p0, p1))
    return out


def winged_skull_strokes(rng, cx, cz, s, y, wing=3.4):
    """날개 달린 해골 (옛 묘비의 장례 문양, 손으로 판 듯 조금씩 흔들림). s = 머리뼈 반폭 (m)"""
    J = lambda: rng.uniform(-0.05, 0.05)
    P = lambda x, z: Vector((cx + (x + J()) * s, y, cz + (z + J()) * s))
    out = []

    def poly(pts):
        q = [P(*p) for p in pts]
        out.extend(zip(q, q[1:]))

    def bez(a, b, c, n=6):
        poly([(a[0] * (1 - t) ** 2 + c[0] * 2 * t * (1 - t) + b[0] * t * t, a[1] * (1 - t) ** 2 + c[1] * 2 * t * (1 - t) + b[1] * t * t)
              for t in [i / n for i in range(n + 1)]])
    # 머리뼈 둥근 통 + 광대 → 턱
    poly([(math.cos(a) * 1.0, 0.15 + math.sin(a) * 1.0) for a in [R(200 - 220 * i / 12) for i in range(13)]])
    poly([(-0.94, -0.19), (-0.72, -0.6), (-0.5, -0.92), (0.5, -0.92), (0.72, -0.6), (0.94, -0.19)])
    poly([(-0.55, -0.66), (0.55, -0.66)])                                           # 이 줄
    for x in (-0.28, 0.0, 0.28):
        poly([(x, -0.66), (x, -0.86)])
    for sx in (-1, 1):                                                              # 눈구멍
        poly([(sx * 0.38 + math.cos(a) * 0.26, -0.1 + math.sin(a) * 0.24) for a in [2 * math.pi * i / 7 for i in range(8)]])
    poly([(-0.13, -0.5), (0.0, -0.3), (0.13, -0.5)])                                # 코
    # 날개: 윗 날개선(뿌리 → 끝) + 깃 여섯 + 깃 끝을 잇는 물결 아랫선
    for sx in (-1, 1):
        U = lambda t: ((1.0 * (1 - t) ** 2 + 2.0 * 2 * t * (1 - t) + wing * t * t) * sx,
                       0.05 * (1 - t) ** 2 + 0.95 * 2 * t * (1 - t) + 0.6 * t * t)
        poly([U(i / 10) for i in range(11)])
        ends = []
        for k in range(6):
            tk = 0.1 + 0.15 * k
            u0 = U(tk)
            e = (u0[0] + sx * (0.3 + 0.07 * k), u0[1] - (1.05 - 0.13 * k))
            poly([u0, ((u0[0] + e[0]) / 2 + sx * 0.04, (u0[1] + e[1]) / 2), e])
            ends.append(e)
        bez((sx * 1.0, -0.35), ends[0], (sx * 1.1, -0.75))
        for e0, e1 in zip(ends, ends[1:]):
            bez(e0, e1, ((e0[0] + e1[0]) / 2, min(e0[1], e1[1]) - 0.2), 4)
        bez(ends[-1], U(1.0), (ends[-1][0] + sx * 0.25, ends[-1][1] + 0.1), 4)
    return out


def sarcophagus():
    """석관 (2.4 m, 긴 축 = X): 받침 + 몸통 + 윗띠, 앞뒤·양 끝에 얕게 판 판면. 앞 왼쪽 판에는 비문, 오른쪽 판에는 고리 문양(이 게임용).
    뚜껑(위가 좁은 사다리꼴, 윗면에 칼 새김)은 +X 쪽으로 밀려 비스듬히 돌아가 왼쪽 뒤 모서리 틈으로 어두운 속이 보인다.
    뚜껑 모서리 하나는 깨져 앞 발치에 떨어졌다. 윗면 이끼, 빗물 때, 발치 흙물"""
    rng = random.Random(1808)
    # 받침 + 몸통 + 윗띠를 합친다 (겹친 상자 → 한 덩어리, 저폴리가 깨끗하게)
    parts = []
    for (sx, sy, sz, z) in ((2.34, 1.06, 0.14, 0.07), (2.2, 0.94, 0.62, 0.45), (2.28, 1.02, 0.08, 0.76)):
        parts.append(box(sx, sy, sz, (0, 0, z)))
    chest = parts[0]
    union(chest, parts[1:])
    # 판면 (앞 둘, 뒤 하나, 양 끝 하나씩) + 속 (위가 열린 상자)
    pc = [box(0.86, 0.1, 0.42, (-0.52, -0.47 - 0.05 + 0.018, 0.44)), box(0.86, 0.1, 0.42, (0.52, -0.47 - 0.05 + 0.018, 0.44)),
          box(1.9, 0.1, 0.42, (0.0, 0.47 + 0.05 - 0.018, 0.44)),
          box(0.1, 0.66, 0.42, (-1.1 - 0.05 + 0.018, 0.0, 0.44)), box(0.1, 0.66, 0.42, (1.1 + 0.05 - 0.018, 0.0, 0.44))]
    cut(chest, pc + [box(1.92, 0.66, 0.7, (0.0, 0.0, 0.26 + 0.35))])
    chip(chest, rng, 22, (0.03, 0.08), sharp_deg=35, bite=0.37, zmin=0.06)          # k4fix 16 → 22: 모서리 이 빠짐 (너무 새것 같았다)
    cut(chest, [G.chunk((1.12, -0.5, 0.79), (0.12, 0.1, 0.09), rng, 9, (0.1, 0.3)), G.chunk((-1.17, 0.52, 0.14), (0.09, 0.08, 0.06), rng, 8)])
    low_src = copy(chest)
    yf = -0.47 + 0.018
    esrc = copy(chest)
    # k4fix: 가짜 라틴 글자(1 m 에서 'XANLZ AAAUR' 로 읽혔다) → 지어낸 글꼴, 오른쪽 아래가 닳아 지워졌다
    tr = random.Random(1809)
    blots = [(-0.27, 0.38, 0.085)]
    st = rune_strokes(tr, -0.52, 0.555, 0.64, 0.058, yf, 0.05, blots)
    st += rune_strokes(tr, -0.52, 0.46, 0.6, 0.05, yf, 0.07, blots)
    st += rune_strokes(tr, -0.52, 0.37, 0.48, 0.05, yf, 0.1, blots)
    # 오른쪽 판: 날개 달린 해골 (k4fix: 고리 + 빛살 + ▽ 는 밝기·재생 아이콘처럼 읽혔다)
    st += winged_skull_strokes(random.Random(1810), 0.52, 0.45, 0.068, yf, wing=3.6)
    engrave_v(chest, st, (0, -1, 0), 0.0095, 0.0065, floor=0.3)
    ck = G.crack_strokes(random.Random(18), (-0.2, -0.47, 0.72), (0.25, 0, -1), 0.5, 7, 0.4, -0.47)
    ck += G.crack_strokes(random.Random(19), (0.95, 0.47, 0.7), (-0.4, 0, -1), 0.4, 6, 0.4, 0.47)
    ck_f = [s for s in ck if s[0].y < 0]
    ck_b = [s for s in ck if s[0].y > 0]
    engrave_surface(chest, ck_f, (0, -1, 0), 0.008, 0.005, step=0.04, floor=0.25)    # 판면 깊이를 따라간다
    engrave_surface(chest, ck_b, (0, 1, 0), 0.008, 0.005, step=0.04, floor=0.25)
    # 뚜껑
    lid = box(2.3, 1.04, 0.07, (0, 0, 0.035))
    fr = G.obj_bm(G.bm_frustum(2.27, 1.01, 2.06, 0.8, 0.07, 0.19), "lidtop")
    union(lid, [fr])
    chip(lid, rng, 10, (0.03, 0.06), sharp_deg=30, bite=0.35)
    cut(lid, [G.chunk((1.15, -0.52, 0.1), (0.16, 0.13, 0.14), rng, 9, (0.1, 0.3))])          # 깨진 모서리
    lid_low_src = copy(lid)
    lesrc = copy(lid)
    zt = 0.19
    sw = [((-0.82, 0.0), (-0.68, 0.035)), ((-0.68, 0.035), (0.42, 0.035)), ((-0.82, 0.0), (-0.68, -0.035)), ((-0.68, -0.035), (0.42, -0.035)),
          ((0.42, -0.2), (0.42, 0.2)), ((0.48, -0.2), (0.48, 0.2)), ((0.42, -0.2), (0.48, -0.2)), ((0.42, 0.2), (0.48, 0.2)),
          ((0.48, -0.018), (0.66, -0.018)), ((0.48, 0.018), (0.66, 0.018)), ((-0.62, 0.0), (0.36, 0.0))]
    sw_st = [(Vector((a[0], a[1], zt)), Vector((b[0], b[1], zt))) for a, b in sw]
    sw_st += [(Vector((0.71 + 0.045 * math.cos(2 * math.pi * i / 10), 0.045 * math.sin(2 * math.pi * i / 10), zt)),
               Vector((0.71 + 0.045 * math.cos(2 * math.pi * (i + 1) / 10), 0.045 * math.sin(2 * math.pi * (i + 1) / 10), zt))) for i in range(10)]
    bx, by = 0.96, 0.33                                      # 윗면 테두리 선
    sw_st += [(Vector((-bx, -by, zt)), Vector((bx, -by, zt))), (Vector((bx, -by, zt)), Vector((bx, by, zt))),
              (Vector((bx, by, zt)), Vector((-bx, by, zt))), (Vector((-bx, by, zt)), Vector((-bx, -by, zt)))]
    engrave_v(lid, sw_st, (0, 0, 1), 0.012, 0.007, floor=0.3)
    # 뚜껑은 앞 모서리(y -0.5)로 받침띠에 걸치고 뒤쪽이 2도 들렸다 — 뒤로 어두운 틈이 보이고, 뚜껑 밑면과 몸통 윗면이 한 평면에
    # 겹치지 않는다 (i1: 겹친 두 면을 서로 맞혀 구워 노멀이 크게 누웠다, steep 8.8%)
    # i3: 1.2 cm 띄운다 (앞 모서리가 받침띠보다 7 cm 밖으로 나와 눈높이에서는 띄운 틈이 가려진다). 굽기 우리(6 mm)가 서로 닿지 않는다
    Ml = (Matrix.Translation((0, -0.5, 0.812)) @ Matrix.Rotation(R(2.0), 4, 'X') @ Matrix.Translation((0, 0.5, -0.812))
          @ Matrix.Translation((0.24, 0.0, 0.812)) @ Matrix.Rotation(R(5.0), 4, 'Z'))
    for o_ in (lid, lid_low_src, lesrc):
        place_xf(o_, Ml)
    # 떨어진 뚜껑 조각
    frag = G.chunk((1.36, -0.5, 0.05), (0.13, 0.1, 0.055), rng, 9, (0.08, 0.25))
    frag_low_src = copy(frag)
    lows = [lowpoly(low_src, z=-0.01), lowpoly(lid_low_src), lowpoly(frag_low_src, z=-0.01)]
    for l in lows:
        drop_faces(l, lambda c, n: c.z < 0.01 and n.z < -0.9)
    drop_faces(lows[1], lambda c, n: n.z < -0.9)               # 뚜껑 밑면: 눈높이에서 안 보인다 (굽을 때 몸통 윗면과 서로 맞는다)
    delete(low_src); delete(lid_low_src); delete(frag_low_src)
    esrc_all = join([esrc, lesrc, copy(frag)])
    body = join([chest, lid, frag])
    back = {'face': (0, 1, 0), 'face_lo': 0.3, 'face_hi': 0.7}
    # 다듬은 면에는 끌 자국 칸을 쓰지 않는다 (거북등·구겨짐) — 금·잔 구멍만, 뒷면만 거칠게 쪼아 다듬은 자국
    fine = [{'t': 'cracks', 'scale': 2.0, 'width': 0.02, 'depth': 0.004, 'warp': 0.08, 'cover': 0.14, 'cover_scale': 0.7},
            {'t': 'cracks', 'scale': 5.0, 'width': 0.025, 'depth': 0.0018, 'warp': 0.08, 'cover': 0.12, 'cover_scale': 1.4},
            {'t': 'pits', 'scale': 30.0, 'depth': 0.0012, 'cover': 0.4},
            dict(back, t='chisel', scale=5.0, amp=0.006, tilt=0.8, jitter=0.6, wall=0.14), dict(back, t='pits', scale=40.0, depth=0.0025, cover=0.7)]
    carve(body, 0.0032, [{'t': 'lumps', 'scale': 0.6, 'amp': 0.0006}], fine, seed=18, edge_from=esrc_all)
    # k4fix: 옆면이 깨끗하고 반듯했다 → 세로 빗물 때를 길고 진하게(rain 0.5 → 0.68, 0.45 → 0.62 m, 0.9 는 줄무늬 천처럼 촘촘했다), 지의류 점(0.2 → 0.5),
    #        큰 물때 얼룩 하나 더. 색은 기존 묘비처럼 약한 청보라 (GRAVE_GREY)
    kw = dict(h=1.0, k=1.1, moss=0.9, moss_color=MOSS_OLIVE, moss_patch=1.4, moss_low=0.8, moss_low_h=0.35,
              dirt=0.75, dirt_h=0.26, tooling=0.45, streaks=0.32, stains=0.9, lichen=0.5, lichen_scale=22.0, edge=0.5, edge_w=0.009,
              edge_gain=0.72, edge_mode='attr', piece_val=0.05, cavity=1.0, contrast=0.3, pivot=0.2, gain=1.08, rain=0.68, rain_h=0.62,
              rain_color=(0.17, 0.19, 0.17), splash=0.9, splash_z=0.14, splash_h=0.26, light=0.85, hue_var=0.2, shadow=SHADOW_GREY)
    m = paint3("sarcophagus_src", GRAVE_GREY, **kw)
    G.blotch(m, (0.3, 0.31, 0.27), 3.0, 0.6, 0.45, 0.62)
    G.blotch(m, (0.17, 0.17, 0.16), 1.3, 0.45, 0.5, 0.66)          # 넓게 번진 검은 물때 (면마다 고르지 않게)
    set_mat(body, m)
    # 뚜껑은 따로 칠한다: 빗물 때가 꼭대기에서 가장 진해 높이 7~19 cm 뚜껑 옆띠에 짧은 세로 줄이 빽빽한 바코드처럼 찍혔다 (f1)
    kw.update(rain=0.22, streaks=0.12)
    ml = paint3("sarcophagus_lid", GRAVE_GREY, **kw)
    G.blotch(ml, (0.3, 0.31, 0.27), 3.0, 0.6, 0.45, 0.62)
    G.blotch(ml, (0.17, 0.17, 0.16), 1.3, 0.45, 0.5, 0.66)
    body.data.materials.append(ml)
    for p_ in body.data.polygons:
        if p_.center.z > 0.805:
            p_.material_index = 1
    print("LOW sarcophagus", sum(tri_count(l) for l in lows))
    # 뒤 받침에서 기어오르는 덩굴 + 발치 풀
    v = G.Vine(random.Random(3), leaf=(0.04, 0.065), leaf_p=0.42)
    tgt = join([copy(l) for l in lows])
    G.ivy_grow(v, tgt, (-0.9, 0.55, 0.02), seed=4, length=1.4, step=0.03, max_roots=7, gravity=0.4, adhesion=0.8, zmax=0.95)
    G.ivy_grow(v, tgt, (1.2, 0.2, 0.02), seed=7, length=0.7, step=0.03, max_roots=4, gravity=0.4, adhesion=0.8, zmax=0.6)
    delete(tgt)
    cards = N.Cards()
    gr = random.Random(8)
    pts = [(x, side * 0.52, 0.03) for side in (-1, 1) for x in (-1.0, -0.4, 0.3, 0.9)]
    pts += [(-1.2, 0.1, 0.03), (1.2, -0.2, 0.03)]
    grass_at(cards, gr, pts, (0.2, 0.36), (0.1, 0.14), 0.45)       # 크기 규격 깊이 1.1 m ±15% 안

    def wt(c, n):
        if abs(c.x) < 0.97 and abs(c.y) < 0.34 and 0.2 < c.z < 0.8:
            return 0.3                                     # 속 (틈으로만 보인다)
        if n.y < -0.7 and c.z > 0.15:
            return 1.0
        return 0.75
    return finish3("sarcophagus", [body], lows, extras=v.objects() + [cards.obj("grass")], cage=0.006, cage_reach=0.05, hard=55,
                   uv_weight=wt)


# ═════════════════════════ 9. 해골 유해 ═════════════════════════
def _curved_plate(x0, x1, a0, a1, rad, cy, cz, th, nx=8, na=10):
    """X 축을 감싸는 휜 판 (가슴판·어깨받이). 각도 a0~a1 (0 = +Z 위), 반지름 rad, 두께 th"""
    bm = bmesh.new()
    rows = []
    for j in range(na + 1):
        a = a0 + (a1 - a0) * j / na
        row = []
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            rr = rad * (1.0 - 0.12 * ((2 * i / nx - 1) ** 2))
            row.append(bm.verts.new((x, cy + math.sin(a) * rr, cz + math.cos(a) * rr)))
        rows.append(row)
    for j in range(na):
        for i in range(nx):
            bm.faces.new((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]))
    o = G.obj_bm(bm, "plate")
    m = o.modifiers.new('sol', 'SOLIDIFY'); m.thickness = th; m.offset = 0.0
    apply_all(o)
    return o


def limb_items(a, b, r, rng, kind, medial=(0, 1, 0)):
    """(k4fix) 사지 뼈 하나 (a → b). 몸통은 가운데가 가늘고 두 끝으로 넓어지며 살짝 휜다 (매끈한 관 끝에 혹을 단 장난감 뼈가 되지 않게).
    kind: femur(넙다리: 공 머리·목·큰돌기 / 무릎 관절 둘), tibia(정강이: 넓은 판 위끝 / 안쪽 복사뼈), fibula(종아리: 가늘고 끝 혹 작게),
          humerus(위팔: 둥근 머리 / 납작 넓은 아래끝), ulna(자: 팔꿈치 갈고리), radius(노: 아래끝이 넓다). medial: 몸 가운데 쪽"""
    a, b = Vector(a), Vector(b)
    L = (b - a).length
    d = (b - a).normalized()
    md = Vector(medial); md = (md - d * md.dot(d)).normalized()
    up = d.cross(md).normalized()
    if up.z < 0:
        up = -up
    thin = kind in ('fibula', 'ulna', 'radius')
    pts, rads = [], []
    n = 10
    for i in range(n + 1):
        t = i / n
        bow = (0.018 if thin else 0.03) * L * math.sin(math.pi * t)
        pts.append(a + d * (L * t) + up * bow * 0.6 + md * bow * 0.4)
        f = (0.85 + 0.35 * (2 * t - 1) ** 4) if thin else (0.74 + 0.56 * (2 * t - 1) ** 4)
        if kind == 'tibia':
            f *= 1.0 + 0.2 * (1 - t) ** 3                       # 위가 굵다 (세모난 정강이)
        rads.append(r * f * rng.uniform(0.96, 1.04))
    it = G.tube_items(pts, rads, 0.55, squash=(1.0, 0.86))
    E = lambda c, sx, sy, sz: (tuple(c), (sx, sy, sz), tuple(d.to_track_quat('X', 'Z').to_euler()))
    if kind == 'femur':
        head = a - d * r * 0.6 + md * r * 1.9 + up * r * 0.4
        it += G.tube_items([a, head], [r * 0.95, r * 1.0], 0.5)                       # 목
        it.append((tuple(head), r * 1.5))                                               # 공 머리
        it.append(E(a - md * r * 0.7 + up * r * 0.3, r * 1.3, r * 1.0, r * 1.1))        # 큰돌기
        for sg in (-1, 1):
            it.append(E(b + d * r * 0.2 + md * sg * r * 0.8 - up * r * 0.15, r * 1.25, r * 0.95, r * 1.05))   # 무릎 관절 둘
    elif kind == 'tibia':
        it.append(E(a + d * r * 0.3, r * 1.0, r * 1.95, r * 1.15))                     # 넓은 위끝 판
        it.append(E(a + d * r * 2.4 + up * r * 0.75, r * 1.4, r * 0.7, r * 0.6))        # 정강이 거친면
        it.append(E(b - d * r * 0.3, r * 1.0, r * 1.25, r * 1.0))
        it.append(E(b + d * r * 0.4 + md * r * 0.8, r * 0.7, r * 0.6, r * 0.6))        # 안쪽 복사뼈
    elif kind == 'fibula':
        it.append(E(a, r * 1.5, r * 1.6, r * 1.4)); it.append(E(b + d * r * 0.8, r * 1.9, r * 1.5, r * 1.4))
    elif kind == 'humerus':
        it.append((tuple(a - d * r * 0.5 + up * r * 0.3), r * 1.55))
        it.append(E(b - d * r * 0.1, r * 0.9, r * 2.0, r * 0.85))                       # 납작하고 넓은 아래끝
    elif kind == 'ulna':
        it.append(E(a - d * r * 0.9 + up * r * 0.3, r * 1.9, r * 1.2, r * 1.5))         # 팔꿈치 갈고리
        it.append(E(b, r * 1.1, r * 1.1, r * 1.0))
    elif kind == 'radius':
        it.append(E(a, r * 1.1, r * 1.4, r * 1.3))
        it.append(E(b - d * r * 0.3, r * 1.2, r * 2.0, r * 1.0))                       # 넓은 아래끝
    return it


def spine_items(x0, x1, y_fn, z):
    """(k4fix) 척추 24 마디: 목 7 (작다) → 등 12 → 허리 5 (크다). 마디마다 몸통(짧은 원기둥꼴) + 양옆 가로돌기 + 아래 가시돌기, 마디 사이는 틈.
    같은 크기 구슬을 줄지어 놓은 것처럼 보이지 않게 크기·간격·돌기 모양이 마디마다 다르다"""
    rs = [0.0095 + 0.0006 * i for i in range(7)] + [0.0125 + 0.00045 * i for i in range(12)] + [0.0185 + 0.0011 * i for i in range(5)]
    lens = [r * 2.05 + 0.0055 for r in rs]
    k = (x1 - x0) / sum(lens)
    out = []
    x = x0
    for i, (r, Ln) in enumerate(zip(rs, lens)):
        Ln *= k
        cxp = x + Ln * 0.5
        y = y_fn(cxp)
        out.append(((cxp, y, z), (Ln * 0.42, r * 1.08, r * 0.82)))                                   # 몸통
        tl = r * (0.75 if i < 7 else (0.95 if i < 19 else 1.35))
        for sg in (-1, 1):
            out.append(((cxp + Ln * 0.08, y + sg * (r * 1.05 + tl * 0.55), z - r * 0.15), (Ln * 0.2, tl * 0.6, r * 0.32),
                        (0, 0, sg * R(10 if i < 19 else -8))))                                            # 가로돌기
        out.append(((cxp + Ln * 0.15, y, z - r * 0.9), (Ln * 0.28, r * 0.3, r * 0.55)))                # 가시돌기 (땅 쪽)
        x += Ln
    return out


def cuirass(x0, x1, R0, amax, th, ns=12, nv=18):
    """(k4fix) 쇠 가슴판 (X 축 = 몸 길이, 위 = 앞가슴). 가운데 세로 능선, 목 쪽 가운데 둥글게 판 목둘레 + 양옆 팔 구멍, 허리 쪽 살짝 벌어진 끝,
    둘레에 말린 테두리. 고른 원통 조각은 녹슨 통·양동이처럼 읽혔다"""
    bm = bmesh.new()
    grid, loop = [], []
    for j in range(nv + 1):
        v = -1 + 2 * j / nv
        a = v * amax
        u_lo = 0.16 * math.exp(-(v / 0.42) ** 2) + 0.2 * math.exp(-((abs(v) - 0.82) / 0.15) ** 2)
        u_hi = 1.0 - 0.07 * v * v
        row = []
        for i in range(ns + 1):
            u = u_lo + (u_hi - u_lo) * i / ns
            x = x0 + (x1 - x0) * u
            Rr = R0 * (0.93 + 0.12 * math.sin(math.pi * min(1.0, u * 1.2))) * (1 + 0.06 * max(0.0, (u - 0.82) / 0.18))
            keel = 1 + 0.08 * max(0.0, 1 - abs(a) / 0.45)
            row.append(Vector((x, math.sin(a) * Rr, math.cos(a) * Rr * keel * 0.82)))
        grid.append(row)
    vs = [[bm.verts.new(p) for p in row] for row in grid]
    for j in range(nv):
        for i in range(ns):
            bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
    o = G.obj_bm(bm, "cuirass")
    m = o.modifiers.new('sol', 'SOLIDIFY'); m.thickness = th; m.offset = 0.0
    apply_all(o)
    # 말린 테두리 (둘레 한 바퀴)
    loop = [grid[j][0] for j in range(nv + 1)] + [grid[nv][i] for i in range(1, ns + 1)] + \
           [grid[j][ns] for j in range(nv - 1, -1, -1)] + [grid[0][i] for i in range(ns - 1, 0, -1)] + [grid[0][0]]
    rim = []
    for p, q in zip(loop, loop[1:]):
        for t in (0.0, 0.5):
            rim.append(p.lerp(q, t))
    rim.append(loop[-1])
    v_, f_ = N.tube(rim, [th * 0.62] * len(rim), 6, tip=False)
    return o, mesh_from("rim", v_, f_)


def skeleton_remains():
    """해골 유해: 반듯이 누운 해골 한 구가 반쯤 흙에 묻혔다. 갈비뼈 한쪽은 주저앉고, 오른팔은 몸 옆에, 왼팔은 녹슨 칼 쪽으로 뻗었다.
    가슴에는 찌그러지고 깨진 쇠 가슴판, 왼 어깨 옆에 떨어진 어깨받이. 칼은 끝이 부러졌다. 뼈 사이로 풀"""
    rng = random.Random(2909)
    items = []
    # 척추 (목 → 엉치, 살짝 S 자)
    # k4fix: 같은 크기 구슬 줄 → 목·등·허리 마디 크기가 다르고 돌기가 있는 척추
    items += spine_items(-0.66, 0.13, lambda x: 0.025 * math.sin((x + 0.66) / 0.8 * 3.0), 0.035)
    # 갈비뼈 9 쌍 (+Y 쪽은 주저앉아 납작, 몇 개는 부러져 없다)
    for k in range(9):
        x = -0.56 + k * 0.05
        for side in (-1, 1):
            if (side, k) in ((1, 2), (1, 6), (-1, 8)):
                continue
            flat = 0.35 if side > 0 else 1.0
            R_ = 0.13 + 0.025 * math.sin(math.pi * k / 8)
            pts = []
            for i in range(8):
                t = i / 7
                a = math.pi * 0.95 * t
                pts.append((x + 0.06 * t, side * (0.02 + R_ * math.sin(a) * (1.0 if t < 0.6 else 0.9)),
                            0.04 + (R_ * 0.75 * (1 - math.cos(a)) * 0.5) * flat + 0.01))
            if side > 0 and k in (3, 4):
                pts = pts[:5]                                                  # 부러진 갈비뼈
            items += G.tube_items(pts, [0.0075] * len(pts), 0.6, squash=(1.0, 0.6))
    # 어깨뼈·빗장뼈·골반
    for side in (-1, 1):
        items.append(((-0.56, side * 0.12, 0.022), (0.075, 0.055, 0.012), (0, 0, side * R(15))))
        items += G.tube_items([(-0.64, side * 0.03, 0.06), (-0.62, side * 0.1, 0.065), (-0.6, side * 0.17, 0.05)], [0.008] * 3, 0.6)
        items.append(((0.17, side * 0.085, 0.05), (0.07, 0.022, 0.055), (R(side * 25), 0, side * R(18))))       # 엉덩뼈 날개
        items.append(((0.24, side * 0.05, 0.03), (0.035, 0.02, 0.022)))
    items.append(((0.15, 0.0, 0.035), (0.05, 0.035, 0.028)))                                                  # 엉치뼈
    # 팔: 오른팔(-Y)은 몸 옆, 왼팔(+Y)은 칼 쪽으로 뻗었다
    # k4fix: 매끈한 관 + 끝 혹 → 뼈마다 끝 모양이 다른 limb_items, 아래팔·아랫다리 두 뼈를 3 cm 넘게 떼었다 (종아리뼈는 바깥쪽)
    items += limb_items((-0.58, -0.19, 0.04), (-0.3, -0.24, 0.035), 0.0135, rng, 'humerus', (0, 1, 0))
    items += limb_items((-0.28, -0.218, 0.03), (-0.04, -0.232, 0.026), 0.0085, rng, 'ulna', (0, 1, 0))
    items += limb_items((-0.27, -0.252, 0.03), (-0.05, -0.272, 0.028), 0.0095, rng, 'radius', (0, 1, 0))
    items += limb_items((-0.58, 0.19, 0.04), (-0.42, 0.43, 0.035), 0.0135, rng, 'humerus', (0, -1, 0))
    items += limb_items((-0.405, 0.455, 0.03), (-0.18, 0.505, 0.028), 0.0095, rng, 'radius', (0, -1, 0))
    items += limb_items((-0.41, 0.42, 0.026), (-0.19, 0.468, 0.025), 0.0085, rng, 'ulna', (0, -1, 0))
    # 다리 (왼다리는 무릎이 조금 굽었다)
    items += limb_items((0.24, -0.1, 0.05), (0.62, -0.13, 0.045), 0.019, rng, 'femur', (0, 1, 0))
    items += limb_items((0.645, -0.128, 0.04), (0.98, -0.138, 0.03), 0.0155, rng, 'tibia', (0, 1, 0))
    items += limb_items((0.67, -0.168, 0.035), (0.965, -0.176, 0.028), 0.0072, rng, 'fibula', (0, 1, 0))
    items += limb_items((0.24, 0.1, 0.05), (0.6, 0.17, 0.05), 0.019, rng, 'femur', (0, -1, 0))
    items += limb_items((0.625, 0.168, 0.045), (0.92, 0.09, 0.03), 0.0155, rng, 'tibia', (0, -1, 0))
    items += limb_items((0.655, 0.205, 0.04), (0.905, 0.133, 0.028), 0.0072, rng, 'fibula', (0, -1, 0))
    for side, (fx, fy) in ((-1, (1.0, -0.15)), (1, (0.94, 0.08))):
        items.append(((fx + 0.02, fy, 0.025), (0.025, 0.018, 0.016)))                  # 발꿈치
        for j in range(4):
            items += G.tube_items([(fx + 0.03, fy + 0.012 * (j - 1.5), 0.02), (fx + 0.085, fy + 0.02 * (j - 1.5), 0.012)], [0.006, 0.005], 0.6)
    for j in range(7):                                                                 # 흩어진 손가락뼈
        items.append(((0.02 + rng.uniform(-0.04, 0.04), -0.27 + rng.uniform(-0.03, 0.03), 0.012), (0.012, 0.005, 0.005), (0, 0, rng.uniform(0, 6.28))))
        items.append(((-0.13 + rng.uniform(-0.04, 0.04), 0.53 + rng.uniform(-0.03, 0.03), 0.012), (0.012, 0.005, 0.005), (0, 0, rng.uniform(0, 6.28))))
    bones = G.blobs(items, 2, "skel")
    remesh(bones, 0.0028)
    keep = copy(bones)
    low_b = kit.decimated(keep, 3400)            # k4fix: 마디·돌기·관절 끝이 늘어 2600 으로는 저폴리가 원본에서 멀어 steep 2.8%
    delete(keep)
    drop_faces(low_b, lambda c, n: c.z < -0.004)
    surface(bones, [{'t': 'lumps', 'scale': 12, 'amp': 0.0012}, {'t': 'cracks', 'scale': 7, 'width': 0.02, 'depth': 0.0018, 'warp': 0.08, 'cover': 0.3},
                    {'t': 'chisel', 'scale': 30, 'amp': 0.0006, 'tilt': 0.6, 'jitter': 0.5, 'wall': 0.3, 'cover': 0.5},
                    {'t': 'pits', 'scale': 110, 'depth': 0.0007, 'cover': 0.6}], 291)
    bmat = paint3("skeleton_bone", G.BONE_DARK, h=0.25, k=0.3, moss=0.35, moss_color=MOSS_DEAD, moss_patch=3.0, dirt=1.0, dirt_h=0.045,
                  edge=0.5, cavity=1.0, ao=0.03, streaks=0.0, stains=0.8, tooling=0.0, grain=0.3, piece_var=0.0, contrast=0.25,
                  gain=0.74, shadow=(0.1, 0.08, 0.07), light=0.5)
    G.blotch(bmat, (0.36, 0.27, 0.13), 9.0, 0.6, 0.42, 0.6)
    set_mat(bones, bmat)
    # 해골: 얼굴이 위로, 정수리가 -X 로, 오른쪽으로 조금 돌아누웠다
    sk = None
    old_surface = G.surface
    G.surface = lambda o, layers, seed=0, guide=None: kit.surface(o, [{'t': 'lumps', 'scale': 14, 'amp': 0.0012},
                                                                      {'t': 'cracks', 'scale': 8, 'width': 0.02, 'depth': 0.0018, 'cover': 0.35},
                                                                      {'t': 'pits', 'scale': 120, 'depth': 0.0007, 'cover': 0.6}], seed)
    try:
        sk = G.skull_high(rng, jaw_open=14, seed=29, moss=0.2, dirt=0.5, hole=True)
    finally:
        G.surface = old_surface
    set_mat(sk, bmat)
    # k4fix: 얼굴이 +Y(뒤)로 돌아 앞·위에서 주름진 덩어리로 읽혔다 → 얼굴이 위와 앞(-Y)을 보게 (눈구멍·턱이 보인다), 정수리는 조금 들렸다
    Ms = (Matrix.Translation((-0.72, 0.0, 0.0)) @ Matrix.Rotation(R(32), 4, 'X') @ Matrix.Rotation(R(-12), 4, 'Y')
          @ Matrix.Rotation(R(90), 4, 'Z') @ Matrix.Rotation(R(-90), 4, 'X') @ Matrix.Diagonal((1.12, 1.12, 1.12, 1)))
    place_xf(sk, Ms)
    zmin = min(v.co.z for v in sk.data.vertices)
    place_xf(sk, Matrix.Translation((0, 0, -zmin - 0.02)))
    low_s = kit.decimated(sk, 700)
    drop_faces(low_s, lambda c, n: c.z < -0.004)
    # 쇠 가슴판 (찌그러지고 깨짐, 갈비뼈 위로 비스듬히 주저앉음) + 떨어진 어깨받이 + 녹슨 칼
    # k4fix: 고른 원통 조각(녹슨 통처럼 읽힘) → 세로 능선·목둘레·팔 구멍·말린 테두리가 있는 가슴판, 오른쪽 위가 눌리고 아래 왼쪽이 깨졌다
    plate, prim = cuirass(-0.6, -0.17, 0.2, R(72), 0.011)
    brk = [(-0.27, -0.2), (-0.23, -0.12), (-0.19, -0.14), (-0.17, -0.05), (-0.1, -0.06), (-0.1, -0.4), (-0.3, -0.4)]   # 아래 왼쪽 깨진 자리 (XY)
    for o_ in (plate, prim):                                    # 판과 테두리를 따로 자른다 (겹친 두 덩어리를 합쳐 자르면 EXACT 불리언이 판을 지웠다)
        for v_ in o_.data.vertices:                             # 찌그러짐 (오른쪽 위가 눌렸다)
            d = (Vector((v_.co.x, v_.co.y, 0)) - Vector((-0.36, 0.08, 0))).length
            v_.co.z -= 0.03 * math.exp(-(d / 0.085) ** 2)
        o_.data.update()
        cut(o_, [G.obj_bm(G.bm_poly(brk, -0.5, 0.5, 'z'), "brk")])
    plate = join([plate, prim])
    # 갈비 끝이 판을 뚫고 나오지 않게 조금 띄우고, 갈비가 주저앉은 +Y 쪽으로 기울였다 (f1: -Y 쪽으로 기울여 성한 갈비 끝이 판 위로 비쳤다)
    place_xf(plate, Matrix.Translation((0.0, 0.0, 0.026)) @ Matrix.Rotation(R(-8), 4, 'X'))
    paul = _curved_plate(-0.08, 0.08, R(-70), R(60), 0.09, 0.0, 0.0, 0.01, 6, 8)
    place_xf(paul, Matrix.Translation((-0.76, 0.32, 0.0)) @ Matrix.Rotation(R(40), 4, 'Z') @ Matrix.Rotation(R(18), 4, 'X'))
    zmin = min(v.co.z for v in paul.data.vertices)
    place_xf(paul, Matrix.Translation((0, 0, -zmin - 0.01)))
    sacc = RU.Acc()
    # k4fix: 가는 선 하나로 읽혔다 → 날 폭 5.6 → 8 cm, 날밑·손잡이(감은 가죽 띠 자국)·둥근 머리를 키웠다
    blade = [(0.0, -0.04), (0.5, -0.036), (0.55, -0.02), (0.585, 0.004), (0.53, 0.016), (0.48, 0.038), (0.0, 0.04)]       # 부러진 끝
    bmb = G.bm_poly(blade, -0.0065, 0.0065, 'z')
    me = bpy.data.meshes.new("_bl"); bmb.to_mesh(me); bmb.free()
    sacc.add_raw([v_.co.copy() for v_ in me.vertices], [tuple(p.vertices) for p in me.polygons])
    bpy.data.meshes.remove(me)
    v, f = RU.bar_path([(-0.014, -0.135, -0.006), (-0.014, 0.0, 0.0), (-0.014, 0.135, -0.006)], 0.028, 0.024)          # 날밑 (끝이 처졌다)
    sacc.add_raw(v, f)
    v, f = RU.lathe([(0.0, 0.0), (0.019, 0.004), (0.017, 0.03), (0.02, 0.042), (0.017, 0.064), (0.02, 0.076), (0.017, 0.1),
                     (0.02, 0.112), (0.018, 0.138), (0.0, 0.142)], 10)                                                  # 손잡이
    sacc.add_raw(v, f, Matrix.Translation((-0.026, 0, 0)) @ Matrix.Rotation(R(-90), 4, 'Y'))
    sacc.add_raw(*RU.lathe([(0.0, -0.026), (0.026, -0.016), (0.031, 0.0), (0.026, 0.016), (0.0, 0.026)], 12), M=Matrix.Translation((-0.19, 0, 0)))
    sword = sacc.obj("sword")
    # 손잡이 쪽은 아래팔뼈에 걸쳐 조금 들리고 끝은 흙에 묻혔다 (f1: 땅에 딱 붙은 검은 날이 흙과 같은 톤이라 날이 보이지 않았다)
    place_xf(sword, Matrix.Translation((-0.05, 0.43, 0.032)) @ Matrix.Rotation(R(-22), 4, 'Z') @ Matrix.Rotation(R(3.6), 4, 'Y'))
    mm = paint3("skeleton_metal", IRON_DARK, h=0.3, k=0.3, moss=0.05, moss_color=MOSS_DEAD, moss_patch=4.0, dirt=0.8, dirt_h=0.03,
                edge=0.7, edge_w=0.004, edge_gain=0.8, edge_mode='bevel', cavity=0.9, ao=0.02, light=0.5, streaks=0.0, stains=0.6,
                speckle=0.5, strokes=0.4, tooling=0.35, grain=0.8, bump=0.6, hue_var=0.2, piece_var=0.0, contrast=0.2, gain=1.1, shadow=(0.05, 0.03, 0.04))
    G.blotch(mm, (0.22, 0.09, 0.045), 9.0, 0.45, 0.5, 0.62, mode='MIX')            # k4fix: 녹은 군데군데 (고른 녹 갈색 통처럼 읽혔다)
    # 칼은 따로: 흐린 쇳빛 날 + 밝게 닳은 날끝·모서리 + 녹 얼룩 (흙 위에서 칼 모양이 읽히게)
    ms = paint3("skeleton_sword", STEEL_OLD, h=0.3, k=0.3, moss=0.0, dirt=0.6, dirt_h=0.025, edge=1.0, edge_w=0.005, edge_gain=1.1,
                edge_mode='bevel', cavity=0.9, ao=0.02, light=0.6, streaks=0.0, stains=0.5, speckle=0.5, strokes=0.4, tooling=0.3,
                grain=0.8, bump=0.5, hue_var=0.15, piece_var=0.0, contrast=0.2, gain=1.1, shadow=(0.05, 0.04, 0.05))
    G.blotch(ms, (0.24, 0.1, 0.05), 7.0, 0.5, 0.52, 0.64, mode='MIX')
    for o_ in (plate, paul):
        set_mat(o_, mm)
    set_mat(sword, ms)
    metal = join([plate, paul, sword])
    # 화살 (갈비뼈에 둘, 다리 옆 땅에 부러진 하나) — 낮게 누운 유해가 멀리서도 '쓰러진 전사'로 읽히게
    aacc = RU.Acc()
    for (p, d, L, fl) in (((-0.42, -0.05, 0.1), (0.35, -0.3, 0.88), 0.35, True), ((-0.3, 0.07, 0.08), (-0.25, 0.42, 0.85), 0.34, True),
                          ((0.52, 0.27, 0.0), (0.45, 0.25, 0.8), 0.2, False)):
        d = Vector(d).normalized()
        a = Vector(p) - d * 0.08
        b = Vector(p) + d * L
        v, f = N.tube([a, b], [0.0065, 0.006], 6, tip=False)
        aacc.add_raw(v, f)
        if fl:
            side = d.cross(Vector((0, 0, 1))).normalized()
            up = side.cross(d).normalized()
            for k in range(3):
                ang = 2 * math.pi * k / 3 + 0.4
                nv = (side * math.cos(ang) + up * math.sin(ang)).normalized()
                c = b - d * 0.06
                vs = [c - d * 0.045, c + d * 0.04, c + d * 0.035 + nv * 0.02, c - d * 0.04 + nv * 0.017]
                t_ = nv.cross(d).normalized() * 0.002
                verts = [q - t_ for q in vs] + [q + t_ for q in vs]
                aacc.add_raw(verts, [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)])
    arrows = aacc.obj("arrows")
    below_cut(arrows, -0.01)                                  # 땅속으로 들어간 화살대는 자른다 (높이 규격)
    low_ar = lowpoly(arrows)
    drop_faces(low_ar, lambda c, n: c.z < -0.01)
    remesh(arrows, 0.0018)
    surface(arrows, [{'t': 'grain', 'scale': 220.0, 'amp': 0.0004}], 293)
    set_mat(arrows, paint3("skeleton_arrow", WOOD_GREY, h=0.45, k=0.2, moss=0.0, dirt=0.6, dirt_h=0.08, edge=0.3, cavity=0.8, ao=0.01,
                           streaks=0.3, stains=0.6, tooling=0.0, grain=0.6, piece_var=0.0, gain=0.8, shadow=SHADOW_GREY))
    low_m = lowpoly(metal)
    drop_faces(low_m, lambda c, n: c.z < -0.005 and n.z < -0.5)
    # 원본 = 저폴리 그대로 + 칠 bump (1.2 cm 판·칼날을 리메시하면 테두리가 둥글어져 노멀이 눕는다 — 울타리·화로와 같은 처방)
    sub = metal.modifiers.new('sub', 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = 1
    apply_all(metal)                                            # 재질은 join 전에 판·어깨받이(mm)·칼(ms) 따로 붙였다
    print("LOW skeleton_remains", tri_count(low_b) + tri_count(low_s) + tri_count(low_m) + tri_count(low_ar))
    cards = N.Cards()
    gr = random.Random(29)
    pts = [(-0.3, -0.05, 0.0), (0.05, 0.12, 0.0), (0.45, 0.0, 0.0), (0.8, -0.02, 0.0), (-0.55, 0.2, 0.0), (0.3, -0.2, 0.0),
           (0.7, 0.22, 0.0)]
    grass_at(cards, gr, pts, (0.16, 0.3), (0.1, 0.16), 0.55)          # 크기 규격(1.8 × 0.8) 안쪽에만
    return finish3("skeleton_remains", [bones, sk, metal, arrows], [low_b, low_s, low_m, low_ar], extras=[cards.obj("grass")], size=1024,
                   cage=0.004, cage_reach=0.05, uv_margin=0.002)


# ═════════════════════════ 2차 7종 (k5): 교수대·매달린 새장·부서진 수레·작은 납골당·길가 사당·사슬 오벨리스크·찢긴 천막 ═════════════════════════
# 1차에서 배운 것 (README 'scenes 묶음 — 지킬 것') 을 그대로 지킨다:
#   - 크기 규격에는 풀·덩굴 카드도 들어간다 → 풀은 소품 윤곽 안쪽에만.
#   - 2~4 cm 쇠는 리메시하지 않는다 (원본 = 저폴리 + SIMPLE subsurf, 잔 결은 칠 bump).
#   - 다듬은 석물 넓은 면에 끌 자국 칸(chisel)을 쓰지 않는다. 금·잔 구멍만, 세월은 빗물 때(rain)·흙물(splash)·이끼 덩어리로.
#   - 지어낸 문양·글자가 실제 기호(♀·막대 사람·UI 아이콘·라틴 글자)로 읽히지 않게: 비문은 rune_strokes, 장례 문양은 날개 해골·이중 나선.
#   - 발광 부품은 Glow_* (굽지 않음), 점광원은 META.light.
WOOD_WEATHER = ((0.034, 0.03, 0.028), (0.25, 0.215, 0.185), (0.43, 0.39, 0.35))     # 비바람에 바랜 각재 (교수대·수레·천막 장대)
CANVAS = ((0.033, 0.029, 0.026), (0.235, 0.205, 0.165), (0.36, 0.33, 0.28))         # 때 묻은 천막 천 (바랜 아마색, 첫 시안은 종이처럼 희었다)
OBELISK_STONE = ((0.04, 0.04, 0.05), (0.235, 0.23, 0.265), (0.47, 0.46, 0.51))      # 검은 오벨리스크 (짙은 청회색)
# 각재 결 (guide 필요): 결을 따라 길게 갈라진 틈(폭 1.7 cm·깊이 8 mm, 벽 45도 안팎 — 더 가파르면 steep 이 오른다) + 잔 결
WOOD_BEAM = [{'t': 'lumps', 'scale': 2.0, 'amp': 0.002},
             {'t': 'bark', 'scale': 7.0, 'width': 0.06, 'depth': 0.008, 'stretch': 0.05, 'ridge': 0.1},
             {'t': 'bark', 'scale': 18.0, 'width': 0.07, 'depth': 0.003, 'stretch': 0.07, 'ridge': 0.15},
             {'t': 'bark', 'scale': 45.0, 'width': 0.08, 'depth': 0.0012, 'stretch': 0.08},
             {'t': 'pits', 'scale': 60.0, 'depth': 0.001, 'cover': 0.4}]
WOOD_PLANK = [{'t': 'lumps', 'scale': 3.0, 'amp': 0.0012},
              {'t': 'bark', 'scale': 11.0, 'width': 0.06, 'depth': 0.0045, 'stretch': 0.05, 'ridge': 0.1},
              {'t': 'bark', 'scale': 30.0, 'width': 0.08, 'depth': 0.0015, 'stretch': 0.07},
              {'t': 'pits', 'scale': 70.0, 'depth': 0.0008, 'cover': 0.4}]


def timber(rng, p0, p1, w, h=None, ref=(0, 0, 1), rot=(0.5, 0.5), chips=(2, 4), name="timber"):
    """각진 나무 각재 객체 (p0→p1, 폭 w·두께 h). ref: 각재 '위' 기준 (축과 나란하면 다른 축). 썩은 끝(rot = 양 끝 확률)은
    비스듬한 평면 몇 장으로 부서지고, 모서리는 이 빠짐. 깨끗한 형태 (저폴리 바탕) — 결은 wood_carve 가 넣는다"""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    h = h or w
    x = d.normalized()
    y = Vector(ref).cross(x)
    if y.length < 1e-4:
        y = x.orthogonal()
    y.normalize()
    z = x.cross(y).normalized()
    bm = G.bm_box(L, w, h)
    for end, pr in zip((-1, 1), rot):
        if rng.random() < pr:
            for _ in range(rng.randint(1, 3)):
                n = Vector((end, rng.uniform(-0.75, 0.75), rng.uniform(-0.75, 0.75))).normalized()
                G.bm_cut(bm, (end * (L / 2 - rng.uniform(0.01, min(0.09, L * 0.12))), 0, 0), n)
    G.bm_chip(bm, rng, rng.randint(*chips), (min(w, h) * 0.12, min(w, h) * 0.32))
    M = Matrix((x, y, z)).transposed().to_4x4()
    M.translation = (p0 + p1) / 2
    return G.obj_bm(bm, name, M)


def grain_guide_segs(segs, step=0.04):
    """여러 각재·장대의 결 방향 안내 (surface 의 bark 층): 축을 따라 점을 찍고 점마다 그 축 방향 'dir'"""
    pts, dirs = [], []
    for a, b in segs:
        a, b = Vector(a), Vector(b)
        L = (b - a).length
        if L < 1e-6:
            continue
        d = (b - a) / L
        n = max(2, int(L / step) + 1)
        for i in range(n):
            pts.append(a.lerp(b, i / (n - 1)))
            dirs.append(d)
    me = bpy.data.meshes.new("gguide")
    me.from_pydata([tuple(p) for p in pts], [], [])
    at = me.attributes.new("dir", 'FLOAT_VECTOR', 'POINT')
    for i, d in enumerate(dirs):
        at.data[i].vector = d
    return link(bpy.data.objects.new("gguide", me))


def wood_carve(o, segs, voxel, seed, layers=None, edge_from=None):
    """각재·판자 원본: carve(되붙이는 복셀 리메시 = 평평한 면·곧은 모서리 + 닳은 모서리 거리 'edist') → 결 방향 갈라짐·잔결(surface + guide).
    edge_from: 판자 이음 홈을 파기 전 사본 (홈 입술이 닳은 모서리처럼 밝게 빛나지 않게, 석물과 같은 이유)"""
    carve(o, voxel, (), (), seed=seed, pieces=False, edge_from=edge_from)
    g = grain_guide_segs(segs)
    surface(o, layers or WOOD_BEAM, seed, guide=g)
    delete(g)
    return o


def wood_paint(name, h, pal=WOOD_WEATHER, **kw):
    """바랜 나무 칠: 닳은 모서리는 'attr'(곧고 고르게, 갈라진 틈 입술은 빛나지 않음), 빗물 때·발치 흙물, 이끼는 위를 향한 면에만 조금"""
    a = dict(h=h, k=0.6, moss=0.35, moss_color=MOSS_DEAD, moss_patch=2.0, dirt=0.75, dirt_h=0.35, edge=0.45, edge_w=0.008, edge_gain=0.9,
             edge_mode='attr', cavity=0.9, cavity_s=0.25, ao=0.06, streaks=0.4, stains=0.6, strokes=0.5, tooling=0.0, grain=0.6,
             hue_var=0.2, piece_var=0.0, contrast=0.22, gain=1.1, shadow=SHADOW_GREY, light=0.6, rain=0.5, rain_h=1.2,
             rain_color=(0.2, 0.18, 0.16))
    a.update(kw)
    return paint3(name, pal, **a)


def iron_src(o):
    """쇠 원본 = 깨끗한 저폴리 형태 그대로 (SIMPLE subsurf 1 단). 2~4 cm 쇠를 리메시하면 모서리가 둥글어져 굽은 노멀이 눕는다 (울타리 i1 steep 5.5%)"""
    h = copy(o)
    sub = h.modifiers.new('sub', 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = 1
    apply_all(h)
    return h


def iron_paint(name, h, pal=IRON_OLD, rust=0.4, **kw):
    a = dict(h=h, k=0.6, moss=0.1, moss_color=MOSS_DEAD, dirt=0.6, dirt_h=0.25, edge=0.4, edge_w=0.004, edge_gain=0.8, edge_mode='bevel',
             cavity=0.9, ao=0.08, light=0.6, streaks=0.55, stains=0.6, speckle=0.6, strokes=0.4, tooling=0.3, grain=0.8, bump=0.6,
             hue_var=0.2, piece_var=0.0, contrast=0.2, gain=1.05, shadow=(0.05, 0.03, 0.04), rain=0.6, rain_h=0.8,
             rain_color=(0.25, 0.14, 0.09))
    a.update(kw)
    m = paint3(name, pal, **a)
    if rust > 0:
        G.blotch(m, (0.17, 0.075, 0.042), 5.0, rust, 0.5, 0.64, mode='MIX')
    return m


def resample_path(pts, step):
    """꺾은선을 길이 step 간격으로 다시 찍는다 (끝점 포함)"""
    pts = [Vector(p) for p in pts]
    lens = [(b - a).length for a, b in zip(pts, pts[1:])]
    total = sum(lens)
    n = max(1, int(round(total / step)))
    out = []
    for i in range(n + 1):
        s = total * i / n
        k = 0
        while k < len(lens) - 1 and s > lens[k]:
            s -= lens[k]
            k += 1
        out.append(pts[k].lerp(pts[k + 1], min(1.0, s / max(lens[k], 1e-9))))
    return out


def rope_tube(pts, r, seg=6, step=None, strands=0, pitch=0.05, closed=False):
    """밧줄 관: 꺾은선(step 이 있으면 그 간격으로 다시 찍음)을 따라 평행 이동 틀로 고리를 잇는다 (꼬이지 않는다).
    strands>0 이면 굵기를 꼬인 가닥처럼 나선으로 흔든다 (고폴리 원본용). 돌아오는 것: verts, faces"""
    pts = [Vector(p) for p in pts]
    if closed:
        pts = pts + [pts[0]]
    P = resample_path(pts, step) if step else pts
    if closed and (P[0] - P[-1]).length < 1e-6:
        P = P[:-1]
    n = len(P)
    tan = []
    for i in range(n):
        if closed:
            d = P[(i + 1) % n] - P[i - 1]
        else:
            d = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        tan.append(d.normalized() if d.length > 1e-9 else Vector((0, 0, 1)))
    u = tan[0].orthogonal().normalized()
    verts, faces = [], []
    s_acc = 0.0
    for i in range(n):
        d = tan[i]
        u = (u - d * u.dot(d))
        u = u.normalized() if u.length > 1e-9 else d.orthogonal().normalized()
        v = d.cross(u)
        if i:
            s_acc += (P[i] - P[i - 1]).length
        for j in range(seg):
            a = 2 * math.pi * j / seg
            rr = r
            if strands:
                rr = r * (1.0 + 0.1 * math.cos(strands * a - 2 * math.pi * s_acc / pitch))
            verts.append(P[i] + (u * math.cos(a) + v * math.sin(a)) * rr)
    rows = n if closed else n - 1
    for i in range(rows):
        i2 = (i + 1) % n
        for j in range(seg):
            j2 = (j + 1) % seg
            faces.append((i * seg + j, i * seg + j2, i2 * seg + j2, i2 * seg + j))
    if not closed:
        faces.append(tuple(range(seg))[::-1])
        L = (n - 1) * seg
        faces.append(tuple(range(L, L + seg)))
    return verts, faces


def rope_pair(paths, r, name="rope", strands=3, pitch=0.045, lo_step=None):
    """밧줄 저폴리(8각 관)와 고폴리 원본(꼬인 가닥, 14각·5 mm 간격). paths: [(점 목록, closed)]
    (k5 i1: 6각 관은 모서리가 60도라 finish3(hard=55) 에서 면마다 단단한 모서리·섬으로 쪼개져, 둥근 원본을 비스듬히 구워
    steep 3.8%·rim_soft 9.8% 였다 → 8각(45도)이면 매끈한 관 하나로 펴진다)"""
    lo, hi = RU.Acc(), RU.Acc()
    for pts, closed in paths:
        v, f = rope_tube(pts, r, 8, step=lo_step or max(r * 2.5, 0.03), closed=closed)
        lo.add_raw(v, f)
        v, f = rope_tube(pts, r, 14, step=0.005, strands=strands, pitch=pitch, closed=closed)
        hi.add_raw(v, f)
    return lo.obj(name + "_low"), hi.obj(name + "_hi")


def rope_paint(name, h):
    return paint3(name, ROPE, h=h, k=0.3, moss=0.0, dirt=0.3, dirt_h=0.3, edge=0.0, cavity=1.0, ao=0.03, streaks=0.2, stains=0.5,
                  tooling=0.0, grain=0.8, piece_var=0.0, gain=1.1, shadow=SHADOW_GREY, light=0.5)


def chain_links(acc, pts, link=0.12, wide=0.065, wire=0.014, seg=6, minor=4, spin=0.0):
    """사슬: 꺾은선을 따라 고리를 잇는다 (고리마다 90도씩 돌아간다). link = 고리 바깥 길이, wide = 바깥 폭, wire = 쇠 반지름.
    고리 중심선은 납작한 타원. 서로 물리도록 간격 = link - 2.4·wire"""
    pitch = link - 2.4 * wire
    P = resample_path(pts, pitch)
    a_, b_ = link / 2 - wire, wide / 2 - wire
    n = 0
    for i in range(len(P) - 1):
        c = (P[i] + P[i + 1]) / 2
        d = (P[i + 1] - P[i]).normalized()
        ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        u0 = (ref - d * ref.dot(d)).normalized()
        u = (Matrix.Rotation(spin + (math.pi / 2 if i % 2 else 0.0), 3, d) @ u0).normalized()
        w = d.cross(u)
        verts, faces = [], []
        for k in range(seg):
            t = 2 * math.pi * k / seg
            cc = c + d * (a_ * math.cos(t)) + u * (b_ * math.sin(t))
            rad = d * math.cos(t) * (b_ / max(a_, 1e-6)) + u * math.sin(t)
            rad = rad.normalized()
            for j in range(minor):
                q = 2 * math.pi * j / minor + math.pi / minor
                verts.append(cc + rad * (math.cos(q) * wire) + w * (math.sin(q) * wire))
        for k in range(seg):
            k2 = (k + 1) % seg
            for j in range(minor):
                j2 = (j + 1) % minor
                faces.append((k * minor + j, k * minor + j2, k2 * minor + j2, k2 * minor + j))
        acc.add_raw(verts, faces)
        n += 1
    return n


def sag_path(a, b, sag, n=16):
    """두 점 사이로 처진 줄 (포물선 근사)"""
    a, b = Vector(a), Vector(b)
    return [a.lerp(b, i / n) - Vector((0, 0, 4 * sag * (i / n) * (1 - i / n))) for i in range(n + 1)]


def bm_to_raw(bm, M=None):
    if M is not None:
        bm.transform(M)
    me = bpy.data.meshes.new("_r"); bm.to_mesh(me); bm.free()
    v = [p.co.copy() for p in me.vertices]; f = [tuple(p.vertices) for p in me.polygons]
    bpy.data.meshes.remove(me)
    return v, f


def stone_paint(name, h, k, pal=GRAVE_GREY, **kw):
    """다듬은 석물 칠 (석관에서 확인한 값): 빗물 때·흙물·이끼 덩어리·물때, 닳은 모서리 'attr'"""
    a = dict(h=h, k=k, moss=0.9, moss_color=MOSS_OLIVE, moss_patch=1.4, moss_low=0.8, moss_low_h=0.35, dirt=0.75, dirt_h=0.26,
             tooling=0.45, streaks=0.32, stains=0.9, lichen=0.4, lichen_scale=22.0, edge=0.5, edge_w=0.009, edge_gain=0.72,
             edge_mode='attr', piece_val=0.05, cavity=1.0, contrast=0.3, pivot=0.2, gain=1.08, rain=0.68, rain_h=0.62,
             rain_color=(0.17, 0.19, 0.17), splash=0.9, splash_z=0.14, splash_h=0.26, light=0.85, hue_var=0.2, shadow=SHADOW_GREY)
    a.update(kw)
    m = paint3(name, pal, **a)
    G.blotch(m, (0.3, 0.31, 0.27), 3.0, 0.6, 0.45, 0.62)
    G.blotch(m, (0.17, 0.17, 0.16), 1.3, 0.45, 0.5, 0.66)          # 넓게 번진 검은 물때
    return m


STONE_FINE = [{'t': 'cracks', 'scale': 2.0, 'width': 0.02, 'depth': 0.004, 'warp': 0.08, 'cover': 0.14, 'cover_scale': 0.7},
              {'t': 'cracks', 'scale': 5.0, 'width': 0.025, 'depth': 0.0018, 'warp': 0.08, 'cover': 0.12, 'cover_scale': 1.4},
              {'t': 'pits', 'scale': 30.0, 'depth': 0.0012, 'cover': 0.4}]


def stone_fine(k=1.0):
    """다듬은 석물 조각 층 (석관과 같은 방식: 끌 자국 칸 없이 금·잔 구멍만, k = 크기 배율)"""
    return [{'t': 'cracks', 'scale': 2.0 / k, 'width': 0.02, 'depth': 0.004 * k, 'warp': 0.08, 'cover': 0.14, 'cover_scale': 0.7 / k},
            {'t': 'cracks', 'scale': 5.0 / k, 'width': 0.025, 'depth': 0.0018 * k, 'warp': 0.08, 'cover': 0.12, 'cover_scale': 1.4 / k},
            {'t': 'pits', 'scale': 30.0 / k, 'depth': 0.0012 * k, 'cover': 0.4}]


def bones_obj(items, voxel=0.003, tris=300, seed=0, name="bones"):
    """뼈 구슬 → 리메시 원본 + 줄인 저폴리 (화로·새장 뼈)"""
    b = G.blobs(items, 2, name)
    remesh(b, voxel)
    low = kit.decimated(b, tris)
    surface(b, [{'t': 'lumps', 'scale': 18, 'amp': 0.001}, {'t': 'cracks', 'scale': 9, 'width': 0.02, 'depth': 0.0015, 'cover': 0.3},
                {'t': 'pits', 'scale': 90, 'depth': 0.0007, 'cover': 0.6}], seed)
    set_mat(b, paint3(name + "_m", G.BONE_DARK, h=1.0, k=0.3, moss=0.0, dirt=0.4, dirt_h=0.1, edge=0.5, cavity=1.0, ao=0.02, streaks=0.0,
                      stains=0.7, tooling=0.0, grain=0.3, piece_var=0.0, gain=0.85, shadow=(0.08, 0.06, 0.06)))
    return b, low


def xf_bone_items(items, M):
    out = []
    for it in items:
        c, rad = it[0], it[1]
        rot = it[2] if len(it) > 2 else (0, 0, 0)
        out.append((M @ Vector(c), rad, tuple((M.to_3x3() @ Euler(rot).to_matrix()).to_euler())))
    return out


# ═════════════════════════ 10. 교수대 ═════════════════════════
def gallows():
    """교수대: 땅에 놓인 침목 위에 선 기둥 둘 + 가로대 + 무릎 버팀대, 앞뒤로 비스듬히 받친 버팀목. 왼쪽 기둥은 가로대 위로 썩은 머리가
    솟고(비대칭 실루엣), 오른쪽 뒤 버팀목은 부러져 발치에 떨어졌다. 가로대에 감긴 밧줄 둘 — 하나는 올가미, 하나는 끊겨 짧게 풀렸다.
    올가미 아래 쓰러진 의자, 오른쪽 가로대에 기댄 사다리(가로장 둘 빠짐). 기둥·가로대 이음에 쇠 꺾쇠.
    40 m 에서 '기둥 둘 + 가로대 + 늘어진 올가미' 로 읽히게 각재를 굵게 (기둥 22 cm)"""
    rng = random.Random(7701)
    W, segs = [], []

    def T(p0, p1, w, h=None, ref=(0, 0, 1), rot=(0.5, 0.5), chips=(2, 4)):
        W.append(timber(rng, p0, p1, w, h, ref, rot, chips))
        segs.append((Vector(p0), Vector(p1)))
    XL, XR = -1.3, 1.3
    for x in (XL, XR):
        T((x, -0.86, 0.06), (x + 0.02, 0.86, 0.06), 0.2, 0.17, rot=(0.8, 0.8))               # 침목
    T((XL - 0.06, 0.0, 0.07), (XR + 0.06, 0.012, 0.07), 0.15, 0.13, rot=(0.0, 0.0))          # 침목을 잇는 문지방
    T((XL, 0, 0.02), (XL - 0.015, 0.0, 4.74), 0.23, 0.22, ref=(0, 1, 0), rot=(0.0, 1.0))     # 왼쪽 기둥 (가로대 위로 썩은 머리)
    T((XR, 0, 0.02), (XR + 0.05, 0.0, 4.42), 0.22, 0.21, ref=(0, 1, 0), rot=(0.0, 0.0))      # 오른쪽 기둥 (조금 기울었다)
    T((-1.79, 0.0, 4.37), (1.8, 0.0, 4.33), 0.22, 0.22, rot=(0.9, 0.6))                       # 가로대
    T((XL + 0.1, 0, 3.56), (-0.56, 0, 4.27), 0.12, 0.13, ref=(0, 1, 0), rot=(0.0, 0.0))      # 무릎 버팀대
    T((XR - 0.1, 0, 3.62), (0.63, 0, 4.25), 0.12, 0.13, ref=(0, 1, 0), rot=(0.0, 0.0))
    for x in (XL, XR):
        for sy in (-1, 1):
            if x == XR and sy > 0:                                                            # 부러진 뒤 버팀목: 밑동 + 기둥에 남은 토막 + 떨어진 토막
                T((x, 0.82, 0.12), (x, 0.6, 0.42), 0.13, 0.12, ref=(1, 0, 0), rot=(0.0, 1.0))
                T((x, 0.1, 1.24), (x, 0.3, 0.92), 0.13, 0.12, ref=(1, 0, 0), rot=(0.0, 1.0))
                T((x + 0.22, 0.36, 0.06), (x + 0.42, 0.88, 0.07), 0.13, 0.12, ref=(0, 0, 1), rot=(1.0, 1.0))
                continue
            T((x, sy * 0.82, 0.12), (x, sy * 0.1, 1.25), 0.13, 0.12, ref=(1, 0, 0), rot=(0.3, 0.0))
    # 사다리 (오른쪽, 가로대 앞면에 기댔다): 다리 둘 + 가로장 (둘은 빠지고 하나는 한쪽만 걸렸다)
    lx = (0.72, 1.08)
    by, ty, tz = -0.86, -0.13, 4.2
    for x in lx:
        T((x, by, 0.0), (x + 0.015, ty, tz), 0.05, 0.075, ref=(1, 0, 0), rot=(0.4, 0.7), chips=(1, 2))
    for i in range(10):
        t = (i + 0.6) / 10.6
        if i in (3, 7):
            continue
        y = by + (ty - by) * t; z = tz * t
        if i == 5:                                                                           # 한쪽이 빠져 비스듬히 매달린 가로장
            T((lx[0] + 0.02, y + 0.01, z), (lx[1] - 0.04, y - 0.03, z - 0.22), 0.04, 0.035, rot=(0.0, 0.8), chips=(0, 1))
            continue
        T((lx[0] - 0.02, y - 0.012, z), (lx[1] + 0.035, y - 0.012, z), 0.042, 0.036, rot=(0.0, 0.0), chips=(0, 1))
    # 쓰러진 의자 (올가미 아래): 둥근 자리 + 다리 셋, 옆으로 누웠다
    stool = []
    seat = xf_all(cyl(0.19, 0.05, (0, 0, 0.47), 14))
    stool.append(seat)
    st_segs = []
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.4
        p0 = Vector((math.cos(a) * 0.11, math.sin(a) * 0.11, 0.46)); p1 = Vector((math.cos(a) * 0.2, math.sin(a) * 0.2, 0.0))
        stool.append(timber(rng, p0, p1, 0.045, 0.045, ref=(0, 0, 1), rot=(0.0, 0.3), chips=(0, 1)))
        st_segs.append((p0, p1))
    Ms = Matrix.Rotation(R(-24), 4, 'Z') @ Matrix.Rotation(R(96), 4, 'X')
    zmin = min((Ms @ v.co).z for o_ in stool for v in o_.data.vertices)
    Ms = Matrix.Translation((-0.42, -0.42, -zmin - 0.01)) @ Ms
    for o_ in stool:
        place_xf(o_, Ms)
    for a, b in st_segs:
        segs.append((Ms @ a, Ms @ b))
    segs.append((Ms @ Vector((0, 0, 0.44)), Ms @ Vector((0, 0, 0.5))))
    W += stool
    wood = W[0]
    union(wood, W[1:])
    low_w = lowpoly(wood)
    drop_faces(low_w, lambda c, n: c.z < 0.0 and n.z < -0.9)
    print("LOW gallows wood", tri_count(low_w))
    # 쇠: 기둥·가로대 이음 꺾쇠 (앞뒤), 왼쪽 기둥 머리 갈라짐을 묶은 띠, 볼트 머리
    acc = RU.Acc()
    for x, sx in ((XL, 1), (XR + 0.04, -1)):
        for fy in (-1, 1):
            yy = fy * 0.117
            v, f = RU.bar_path([(x + sx * 0.0, yy, 3.95), (x + sx * 0.0, yy, 4.3), (x + sx * 0.42, yy, 4.3)], 0.07, 0.012, ref=(0, 1, 0))
            acc.add_raw(v, f)
            for (bx, bz) in ((x, 4.03), (x, 4.17), (x + sx * 0.2, 4.3), (x + sx * 0.36, 4.3)):
                v, f = bm_to_raw(G.bm_box(0.03, 0.016, 0.03), Matrix.Translation((bx, yy + fy * 0.01, bz)))
                acc.add_raw(v, f)
    hw = 0.122
    sq = [(XL - hw, -hw, 0), (XL + hw, -hw, 0), (XL + hw, hw, 0), (XL - hw, hw, 0), (XL - hw, -hw, 0)]
    v, f = RU.bar_path([(x, y, 4.6) for x, y, _ in sq], 0.012, 0.06, ref=(0, 0, 1))
    acc.add_raw(v, f)
    iron = acc.obj("gallows_iron")
    low_i = lowpoly(iron)
    # 밧줄: 가로대를 두 번 감고 → 올가미 (매듭 감은 고리 + 늘어진 고리) / 끊겨 풀린 짧은 줄
    paths, fray = [], []
    zb = 4.35
    for (x0, drop_to, noose) in ((-0.46, 3.24, True), (0.36, 3.62, False)):
        for k in range(2):
            ring = [(x0 + 0.03 * k + 0.012 * math.sin(2 * math.pi * i / 12), 0.15 * math.cos(2 * math.pi * i / 12),
                     zb + 0.16 * math.sin(2 * math.pi * i / 12)) for i in range(12)]
            paths.append((ring, True))
        paths.append(([(x0 + 0.015, -0.02, zb - 0.13), (x0 + 0.02, -0.03, zb - 0.6), (x0 + 0.03, -0.035, (zb + drop_to) / 2),
                       (x0 + 0.035, -0.03, drop_to)], False))
        if noose:
            kx, ky = x0 + 0.035, -0.03
            for i in range(7):                                           # 매듭 (감은 고리 일곱)
                z_ = drop_to - 0.025 - i * 0.027
                ring = [(kx + 0.036 * math.cos(2 * math.pi * j / 10), ky + 0.036 * math.sin(2 * math.pi * j / 10), z_ + 0.004 * math.sin(2 * math.pi * j / 10))
                        for j in range(10)]
                paths.append((ring, True))
            zk = drop_to - 0.2
            loop = [(kx + 0.12 * math.sin(2 * math.pi * i / 16) * math.cos(R(25)), ky + 0.12 * math.sin(2 * math.pi * i / 16) * math.sin(R(25)),
                     zk - 0.19 + 0.19 * math.cos(2 * math.pi * i / 16)) for i in range(16)]
            paths.append((loop, True))
        else:                                                            # 끊긴 끝: 가닥이 풀려 벌어졌다
            for k in range(4):
                a = 2 * math.pi * k / 4 + 0.3
                fray.append(([(x0 + 0.035, -0.03, drop_to + 0.02), (x0 + 0.035 + 0.03 * math.cos(a), -0.03 + 0.03 * math.sin(a), drop_to - 0.06 - 0.02 * k)], False))
    rope_lo, rope_hi = rope_pair(paths, 0.017)
    f_lo, f_hi = rope_pair(fray, 0.007, strands=0)
    rope_lo = join([rope_lo, f_lo]); rope_hi = join([rope_hi, f_hi])
    set_mat(rope_hi, rope_paint("gallows_rope", 4.6))
    # 원본
    wh = copy(wood)
    delete(wood)
    wood_carve(wh, segs, 0.0045, 71)
    wm = wood_paint("gallows_wood", 4.7, rain=0.6, rain_h=1.6, moss=0.45, moss_low=0.6, moss_low_h=0.35, dirt_h=0.5, gain=1.02)
    G.blotch(wm, (0.12, 0.11, 0.1), 2.2, 0.35, 0.5, 0.64)          # 검게 삭은 얼룩
    set_mat(wh, wm)
    ih = iron_src(iron)
    delete(iron)
    set_mat(ih, iron_paint("gallows_iron", 4.6))
    cards = N.Cards()
    gr = random.Random(71)
    pts = [(XL + 0.15, -0.3, 0.02), (XL - 0.12, 0.35, 0.02), (XR + 0.15, -0.4, 0.02), (XR - 0.15, 0.25, 0.02), (XL, -0.75, 0.13),
           (XR, 0.72, 0.13), (-0.2, 0.15, 0.1), (0.4, -0.12, 0.1)]
    grass_at(cards, gr, pts, (0.25, 0.42), (0.16, 0.24), 0.5)
    print("LOW gallows", tri_count(low_w) + tri_count(low_i) + tri_count(rope_lo))
    wt = lambda c, n: 0.55 if c.z < 0.2 else (0.8 if n.z < -0.7 else 1.0)
    lod0 = finish3("gallows", [wh, ih, rope_hi], [low_w, low_i, rope_lo], extras=[cards.obj("grass")], cage=0.006, cage_reach=0.05,
                    hard=55, uv_margin=0.002, uv_weight=wt, lod1=0.5)
    return repad_textures("gallows", lod0)          # 섬 바깥 여백을 섬 안쪽 값으로 다시 메운다 (가는 쇠살·판자 섬이 많아 밉맵에서 테두리가 번진다)


# ═════════════════════════ 11. 매달린 새장 ═════════════════════════
def hanging_cage():
    """매달린 새장: 돌무더기에 박힌 네모 쇠기둥(공 머리 + 창촉) 에서 팔이 뻗고, 팔 아래 소용돌이 받침쇠. 팔 끝 고리에서 사슬로 술통 모양
    쇠 새장이 매달렸다 (조금 기울고 돌았다). 새장 문은 열려 바깥으로 젖혀졌고 창살 하나는 휘어 벌어졌다. 바닥에는 해골과 뼈. 갇힌 혼(Glow_Soul) 이 새장 가운데에서 희미하게 피어오른다 (광원 (0.7, 0, 1.9))"""
    rng = random.Random(7702)
    acc = RU.Acc()
    PX = -0.74
    # 기둥 (아래 굵게) + 띠 + 공 머리 + 창촉
    v, f = RU.bar_path([(PX, 0, -0.12), (PX, 0, 0.95)], 0.15); acc.add_raw(v, f)
    v, f = RU.bar_path([(PX, 0, 0.9), (PX + 0.006, 0.0, 2.2), (PX + 0.016, 0.004, 3.42)], 0.12); acc.add_raw(v, f)
    for z in (0.93, 2.02, 3.34):
        v, f = RU.bar_path([(PX, 0, z - 0.035), (PX + 0.002, 0, z + 0.035)], 0.165 if z < 1 else 0.15); acc.add_raw(v, f)
    v, f = RU.lathe([(0.0, 3.4), (0.05, 3.41), (0.075, 3.455), (0.07, 3.5), (0.04, 3.53), (0.0, 3.535)], 12, (PX + 0.016, 0.004, 0)); acc.add_raw(v, f)
    v, f = RU.spear((PX + 0.016, 0.004, 3.53), (0.02, 0, 1), 0.09, 0.055, 0.016, 0.014); acc.add_raw(v, f)
    # 팔 (끝이 아래로 말린 소용돌이) + 받침쇠 (기둥에서 팔 밑으로 휘어 오르고 안쪽으로 감긴 소용돌이)
    arm = [(PX, 0, 3.22), (-0.2, 0, 3.235), (0.5, 0, 3.225), (0.92, 0, 3.2)]
    v, f = RU.bar_path(arm, 0.085, 0.065); acc.add_raw(v, f)
    sc_ = [(0.92 + 0.065 * math.sin(t) * (1 - 0.4 * t / 5), 0, 3.2 - 0.065 + 0.065 * math.cos(t) * (1 - 0.4 * t / 5)) for t in [i * 0.55 for i in range(10)]]
    v, f = RU.bar_path([(0.9, 0, 3.2)] + sc_, 0.04, 0.05); acc.add_raw(v, f)
    br = [(PX + 0.07, 0, 2.45)]
    for i in range(1, 11):
        t = i / 10
        br.append((PX + 0.07 + 0.95 * (1 - math.cos(t * math.pi / 2)), 0, 2.45 + 0.72 * math.sin(t * math.pi / 2)))
    v, f = RU.bar_path(br, 0.035, 0.035); acc.add_raw(v, f)
    cx0, cz0 = PX + 0.25, 2.97
    sp = []
    for i in range(22):
        t = i / 21
        a = R(200) + t * 2.2 * math.pi
        r_ = 0.17 * (1 - 0.8 * t)
        sp.append((cx0 + r_ * math.cos(a), 0, cz0 + r_ * math.sin(a)))
    v, f = RU.bar_path(sp, 0.03, 0.03); acc.add_raw(v, f)
    # 팔 끝 고리 + 사슬
    HX = 0.72
    v, f = RU.torus_raw(0.04, 0.011, Matrix.Translation((HX, 0, 3.13)) @ Matrix.Rotation(R(90), 4, 'X'), 10, 4); acc.add_raw(v, f)
    v, f = RU.bar_path([(HX, 0, 3.18), (HX, 0, 3.165)], 0.03, 0.05); acc.add_raw(v, f)
    # 새장 (새장 기준 좌표 → 기울여 매단다)
    cage = RU.Acc()
    zb, zt = 0.0, 1.16                                            # 새장 몸 (밑 0 → 어깨 1.16), 둥근 지붕 → 1.3
    rad = lambda z: 0.27 + 0.07 * math.sin(math.pi * min(1.0, max(0.0, z / zt)))
    NB = 10
    door = (7, 8)                                                 # 문 창살 (오른쪽 앞)
    th = [2 * math.pi * i / NB + 0.15 for i in range(NB)]
    zd0, zd1 = 0.06, 0.92                                         # 문 높이
    for i, a in enumerate(th):
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for k in range(15):
            z = zt * k / 14
            r_ = rad(z)
            if i == 1:                                            # 휘어 벌어진 창살 (정면에서 오른쪽 윤곽으로 보인다)
                r_ += 0.06 * math.sin(math.pi * min(1, max(0, (z - 0.15) / 0.75))) ** 1.5
            pts.append((r_ * ca, r_ * sa, z))
        for k in range(1, 6):                                     # 둥근 지붕
            t = k / 5
            r_ = rad(zt) * math.cos(t * math.pi / 2) * 0.92 + 0.035
            pts.append((r_ * ca, r_ * sa, zt + 0.16 * math.sin(t * math.pi / 2)))
        if i in door:
            lo_ = [p for p in pts if p[2] < zd0 + 1e-6]
            hi_ = [p for p in pts if p[2] > zd1 - 1e-6]
            for seg_ in (lo_, hi_):
                if len(seg_) > 1:
                    v, f = RU.bar_path(seg_, 0.024, 0.012, ref=(ca, sa, 0)); cage.add_raw(v, f)
            continue
        v, f = RU.bar_path(pts, 0.024, 0.012, ref=(ca, sa, 0)); cage.add_raw(v, f)

    def hoop(z, w, a0=0.0, a1=2 * math.pi, n=30, closed=True):
        pts = []
        for k in range(n + (0 if closed else 1)):
            a = a0 + (a1 - a0) * k / n
            r_ = rad(z) + 0.006
            pts.append((r_ * math.cos(a), r_ * math.sin(a), z))
        if closed:
            pts.append(pts[0])
        return RU.bar_path(pts, 0.012, w, ref=(0, 0, 1))
    for z in (0.015, zt):
        v, f = hoop(z, 0.04); cage.add_raw(v, f)
    for z in (zd0, zd1, 0.5):
        v, f = hoop(z, 0.03, th[door[1]] + 0.1, th[door[0]] - 0.1 + 2 * math.pi, 30, False); cage.add_raw(v, f)
    v, f = RU.lathe([(0.0, -0.012), (0.27, -0.012), (0.275, 0.006), (0.0, 0.006)], 20); cage.add_raw(v, f)     # 바닥판
    v, f = RU.torus_raw(0.05, 0.012, Matrix.Translation((0, 0, zt + 0.2)) @ Matrix.Rotation(R(90), 4, 'X'), 10, 4); cage.add_raw(v, f)
    v, f = RU.lathe([(0.0, zt + 0.14), (0.06, zt + 0.14), (0.05, zt + 0.17), (0.0, zt + 0.175)], 10); cage.add_raw(v, f)
    # 문: 창살 둘 + 가로대 셋, 경첩(창살 door[0]-1 쪽 세로선)을 축으로 바깥으로 70도 젖혀졌다
    dacc = RU.Acc()
    for i in door:
        ca, sa = math.cos(th[i]), math.sin(th[i])
        pts = [(rad(z) * ca, rad(z) * sa, z) for z in [zd0 + (zd1 - zd0) * k / 8 for k in range(9)]]
        v, f = RU.bar_path(pts, 0.024, 0.012, ref=(ca, sa, 0)); dacc.add_raw(v, f)
    for z in (zd0 + 0.02, (zd0 + zd1) / 2, zd1 - 0.02):
        pts = []
        for k in range(7):
            a = th[door[0]] - 0.12 + (th[door[1]] - th[door[0]] + 0.24) * k / 6
            pts.append(((rad(z) + 0.012) * math.cos(a), (rad(z) + 0.012) * math.sin(a), z))
        v, f = RU.bar_path(pts, 0.012, 0.028, ref=(0, 0, 1)); dacc.add_raw(v, f)
    ha = th[door[0]] - 0.16
    hp = Vector((rad(0.5) * math.cos(ha), rad(0.5) * math.sin(ha), 0.0))
    Md = Matrix.Translation(hp) @ Matrix.Rotation(R(-72), 4, 'Z') @ Matrix.Translation(-hp)
    dv = [Md @ Vector(p) for p in dacc.v]
    cage.add_raw(dv, dacc.f)
    # 새장 놓기: 바닥 z 1.3, 가운데 x HX, 조금 기울고 돈 채로
    Mc = Matrix.Translation((HX, 0.0, 1.3)) @ Matrix.Rotation(R(4), 4, 'Y') @ Matrix.Rotation(R(-3), 4, 'X') @ Matrix.Rotation(R(-28), 4, 'Z')
    acc.add_raw([Mc @ Vector(p) for p in cage.v], cage.f)
    top = Mc @ Vector((0, 0, zt + 0.2))
    chain_links(acc, [(HX, 0, 3.1), (top.x, top.y, top.z + 0.035)], link=0.1, wide=0.055, wire=0.011, seg=6, minor=4)
    iron = acc.obj("cage_iron")
    low_i = lowpoly(iron)
    drop_faces(low_i, lambda c, n: c.z < -0.1 and n.z < -0.9)
    # 기둥 발치 돌무더기
    stones = []
    for i in range(8):
        a = 2 * math.pi * i / 8 + rng.uniform(-0.2, 0.2)
        rr = rng.uniform(0.15, 0.23)
        s_ = (rng.uniform(0.12, 0.18), rng.uniform(0.1, 0.15), rng.uniform(0.09, 0.13))
        bm = rough_box(rng, *s_, jit=0.22, chips=(2, 4), depth=(0.015, 0.04))
        stones.append(G.obj_bm(bm, "st", Matrix.Translation((PX + math.cos(a) * rr, math.sin(a) * rr * 1.1, s_[2] * 0.3 + (0.06 if i % 3 == 0 else 0.0)))
                               @ Euler((R(rng.uniform(-14, 14)), R(rng.uniform(-14, 14)), a), 'XYZ').to_matrix().to_4x4()))
    # k5 i2: 돌 여덟을 join 만 한 저폴리는 서로·기둥 속에 묻힌 면이 남아 굽기 광선이 이웃 돌을 맞혔다 (돌무더기 자리 steep 80~96%).
    #        → 저폴리는 사본을 union 하고 기둥 자리를 파낸 것, 원본은 돌마다 따로 (돌마다 색조가 다르게 칠해지도록)
    scp = [copy(o_) for o_ in stones]
    su = union(scp[0], scp[1:])
    cut(su, [box(0.16, 0.16, 1.2, (PX, 0, 0.4))])
    low_s = lowpoly(su, z=-0.02)
    delete(su)
    so = join(stones)
    co_, fi_ = ROCK3(0.2, 0.5, chisel=0.3)
    carve(so, 0.004, co_, fi_, seed=72, mode='octree', pieces=True)
    smat = paint3("cage_stone", MEGALITH, h=0.4, k=0.25, cells=0.2, piece_var=0.8, piece_val=0.15, facet_var=0.14, moss=0.7,
                  moss_color=MOSS_OLIVE, moss_patch=1.5, dirt=0.6, dirt_h=0.12, edge=0.0, streaks=0.0, ao=0.05, grain=0.25, tooling=0.0,
                  strokes=0.6, stains=0.6, edge_mode='attr', lichen=0.0, contrast=0.25, hue_var=0.2, shadow=SHADOW_GREY, gain=1.08)
    set_mat(so, smat)
    # 뼈: 해골 (바닥에 기울어 누움) + 긴 뼈 둘 (창살 밖으로 늘어진 팔뼈는 흰 막대기처럼 읽혀 뺐다)
    sk = G.skull_high(random.Random(73), jaw_open=14, seed=73, moss=0.1, dirt=0.3)
    Msk = Mc @ Matrix.Translation((0.06, 0.05, 0.012)) @ Matrix.Rotation(R(150), 4, 'Z') @ Matrix.Rotation(R(-18), 4, 'Y')
    sk.data.transform(Msk); sk.data.update()
    low_k = kit.decimated(sk, 500)
    items = []
    for (p, yaw, L, r) in (((-0.08, -0.06, 0.03), 40, 0.4, 0.019), ((0.02, 0.12, 0.028), -30, 0.34, 0.016)):
        M = Mc @ Matrix.Translation(p) @ Matrix.Rotation(R(yaw), 4, 'Z') @ Matrix.Rotation(R(rng.uniform(-6, 6)), 4, 'Y')
        items += xf_bone_items(G.long_bone(L, r, rng), M)
    bh, low_b = bones_obj(items, 0.003, 420, 74, "cage_bones")
    # 갇힌 혼 (Glow_Soul): 새장 가운데에서 피어오르는 한 덩이 혼불 — 한 밑동에서 높이가 다른 혀 넷이 같은 쪽으로 모여 오르고 아래에 둥근 불씨 + 작은 빛알.
    # (k5 i1: 서로 반대로 기운 혀 둘은 흰 실루엣이 총·막대기처럼 읽혔다)
    gl = []
    gc = Mc @ Vector((0.0, 0.0, 0.3))
    for (dx, dy, h_, w_, ln, cu, tw) in ((0.0, 0.0, 0.38, 0.06, (0.015, -0.01), 0.025, 2.2),
                                         (0.035, 0.02, 0.26, 0.042, (0.03, 0.01), -0.02, -1.8),
                                         (-0.03, 0.025, 0.22, 0.04, (-0.025, 0.015), 0.018, 1.6),
                                         (0.0, -0.035, 0.17, 0.036, (0.005, -0.03), -0.015, -1.4),
                                         (0.0, 0.0, 0.1, 0.075, (0.0, 0.0), 0.0, 0.8)):
        o, _ = flame_lick(tuple(gc + Vector((dx, dy, 0.0))), h_, w_, ln, curl=cu, twist=tw, name='Glow_Soul'); gl.append(o)
    for (dx, dy, dz, s_) in ((0.12, -0.08, 0.62, 0.018), (-0.1, 0.06, 0.75, 0.014), (0.05, 0.1, 0.9, 0.011)):
        e = G.chunk(tuple(Mc @ Vector((dx, dy, dz))), (s_, s_, s_ * 1.2), rng, 6, (0.1, 0.25), sub=1)
        gl.append(glow(e, 'Glow_Soul'))
    ih = iron_src(iron)
    delete(iron)
    im = iron_paint("cage_iron", 3.6, rust=0.5)
    G.tint_near(im, (HX, 0.0, 1.32), 0.3, (0.03, 0.025, 0.03), 0.5)             # 새장 바닥: 검게 밴 때
    set_mat(ih, im)
    cards = N.Cards()
    gr = random.Random(75)
    grass_at(cards, gr, [(PX + 0.25, -0.22, 0.05), (PX - 0.22, 0.2, 0.05), (PX + 0.05, 0.3, 0.1), (PX - 0.15, -0.3, 0.04)], (0.22, 0.36), (0.14, 0.2), 0.5)
    print("LOW hanging_cage", tri_count(low_i) + tri_count(low_s) + tri_count(low_k) + tri_count(low_b))
    wt = lambda c, n: 0.6 if c.z < 0.4 else 1.0
    lod0 = finish3("hanging_cage", [ih, so, sk, bh], [low_i, low_s, low_k, low_b], extras=gl + [cards.obj("grass")], cage=0.004,
                    cage_reach=0.04, hard=55, uv_margin=0.002, uv_weight=wt, lod1=0.5)
    return repad_textures("hanging_cage", lod0)          # 섬 바깥 여백을 섬 안쪽 값으로 다시 메운다 (가는 쇠살·판자 섬이 많아 밉맵에서 테두리가 번진다)


# ═════════════════════════ 12. 부서진 수레 ═════════════════════════
def wheel(rng, R_=0.6, rim=0.075, th=0.085, spokes=10, fel=7, gone=(), gone_spokes=(), stub=()):
    """수레바퀴 (XZ 평면, 축 = Y, 가운데 원점): 바퀴통 + 바퀴살 + 바퀴테 조각(펠로) + 쇠 테 → (나무 객체들, 결 축, 쇠 (v, f))
    gone: 빠진 테 조각 번호, gone_spokes: 빠진 살, stub: 부러져 밑동만 남은 살"""
    objs, segs = [], []
    # 바퀴테: 남은 조각이 이어진 구간마다 고리 조각 하나.
    # (k5 i1: 조각 사이 7 mm 틈을 리메시가 반쯤 메워 비스듬히 구워졌고, i2: 조각을 겹쳐 union 하니 같은 평면끼리 겹쳐 불리언이 깨졌다 — steep 12.9%)
    keep = [i not in gone for i in range(fel)]
    runs = []
    if all(keep):
        runs.append((0, fel - 1))
    else:
        start = keep.index(False)
        cur = None
        for k in range(1, fel + 1):
            j = (start + k) % fel
            if keep[j]:
                cur = [j, j] if cur is None else [cur[0], j]
            elif cur is not None:
                runs.append(tuple(cur)); cur = None
        if cur is not None:
            runs.append(tuple(cur))
    for j0, j1 in runs:
        cnt = (j1 - j0) % fel + 1
        a0 = 2 * math.pi * j0 / fel
        a1 = a0 + 2 * math.pi * cnt / fel
        bm = G.annulus_y(0, 0, R_ - rim, R_, -th / 2, th / 2, 6 * cnt, a0, a1)
        G.bm_chip(bm, rng, rng.randint(1, 2) * cnt, (0.008, 0.02))
        objs.append(G.obj_bm(bm, "fel"))
        for k in range(cnt):
            b0, b1 = a0 + 2 * math.pi * k / fel, a0 + 2 * math.pi * (k + 1) / fel
            segs.append((Vector((math.cos(b0), 0, math.sin(b0))) * (R_ - rim / 2), Vector((math.cos(b1), 0, math.sin(b1))) * (R_ - rim / 2)))
    hub = G.obj_bm(G.lathe([(0.0, -0.16), (0.07, -0.16), (0.09, -0.11), (0.115, -0.04), (0.115, 0.04), (0.09, 0.11), (0.07, 0.16), (0.0, 0.16)], 12,
                           Matrix.Rotation(R(90), 4, 'X')), "hub")
    objs.append(hub)
    segs.append((Vector((0, -0.16, 0)), Vector((0, 0.16, 0))))
    for i in range(spokes):
        if i in gone_spokes:
            continue
        a = 2 * math.pi * (i + 0.5) / spokes
        d = Vector((math.cos(a), 0, math.sin(a)))
        r1 = (R_ - rim + 0.02) if i not in stub else rng.uniform(0.22, 0.32)
        p0, p1 = d * 0.1, d * r1
        objs.append(timber(rng, p0, p1, 0.05, 0.036, ref=(0, 1, 0), rot=(0.0, 1.0 if i in stub else 0.0), chips=(0, 1), name="spoke"))
        segs.append((p0, p1))
    tv, tf = [], []
    for i in range(fel):
        if i in gone:
            continue
        a0 = 2 * math.pi * i / fel; a1 = 2 * math.pi * (i + 1) / fel
        if (i + 1) % fel in gone:
            a1 -= 0.05
        if (i - 1) % fel in gone:
            a0 += 0.05
        v, f = bm_to_raw(G.annulus_y(0, 0, R_ - 0.002, R_ + 0.011, -th * 0.42, th * 0.42, 8, a0, a1))
        off = len(tv); tv += v; tf += [tuple(off + j for j in ff) for ff in f]
    return objs, segs, (tv, tf)


def cart_broken():
    """부서진 수레: 끌채가 땅에 닿게 앞으로 고꾸라진(18도) 짐수레. 앞(−Y) 바퀴는 테 조각 둘과 살 셋이 빠져 주저앉고 바깥으로 기울었다
    (수레가 그쪽으로 4도 기움). 앞 옆판은 윗판이 떨어져 발치에 누웠고 아랫판은 반쯤 부러졌다. 뒷판은 경첩 하나에 걸려 아래로 늘어졌다.
    오른쪽(+Y) 끌채는 가운데가 부러져 앞 토막이 땅에 굴렀다. 짐칸 안에는 쇠테 두른 술통 하나가 앞쪽으로 굴러 처박혔다"""
    rng = random.Random(7703)
    W, segs = [], []

    def T(p0, p1, w, h=None, ref=(0, 0, 1), rot=(0.4, 0.4), chips=(1, 3), name="timber"):
        W.append(timber(rng, p0, p1, w, h, ref, rot, chips, name))
        segs.append((Vector(p0), Vector(p1)))
        return W[-1]
    AX, AZ = 0.25, 0.6
    # 짐칸 (수레 기준 좌표: 굴대 (AX, ·, AZ), 고꾸라지기 전)
    bed = []
    n0 = len(W)
    T((AX, -0.64, AZ), (AX, 0.64, AZ), 0.1, 0.1, rot=(0, 0), chips=(0, 1))                          # 굴대 (안쪽: 바퀴통 사이)
    T((AX, -0.62, AZ + 0.09), (AX, 0.62, AZ + 0.09), 0.14, 0.1, rot=(0, 0))                          # 받침목 (굴대에 1 cm 묻힘)
    for sy in (-1, 1):
        T((-0.97, sy * 0.55, 0.79), (1.2, sy * 0.55, 0.79), 0.1, 0.12, rot=(0.3, 0.6))                 # 짐칸 틀
    for i, y in enumerate((-0.5, -0.3, -0.1, 0.1, 0.3, 0.5)):
        x0, x1 = -0.98, 1.22
        if i == 1:
            x0 = -0.35                                                                                # 부러져 빠진 앞쪽 바닥판
        # k5: 판자 사이 틈 3 cm (i1 의 1.5 cm 틈은 리메시(4.5 mm)가 반쯤 메워 틈 벽이 비스듬히 구워졌고, i2 처럼 겹쳐 union 하면
        #     같은 평면끼리 겹쳐 EXACT 불리언이 깨진다 — 판자끼리는 겹치지도, 1~2 cm 로 붙지도 않게)
        T((x0, y, 0.868), (x1 + rng.uniform(-0.02, 0.01), y + rng.uniform(-0.004, 0.004), 0.868), 0.17, 0.04, rot=(0.8 if i == 1 else 0.2, 0.3), chips=(1, 2), name="plank")
    # 옆판 + 말뚝: +Y 는 두 장 그대로, −Y 는 윗판이 떨어지고 아랫판은 반쯤 부러졌다
    for sy in (1, -1):
        yb = sy * 0.6
        if sy > 0:
            T((-0.96, yb, 0.965), (1.2, yb, 0.965), 0.035, 0.16, rot=(0.0, 0.3), name="plank")
            T((-0.96, yb, 1.175), (1.2, yb, 1.175), 0.035, 0.16, rot=(0.2, 0.4), name="plank")
        else:
            T((-0.96, yb, 0.975), (0.28, yb, 0.975), 0.035, 0.17, rot=(0.0, 1.0), name="plank")
        for x in (-0.86, -0.1, 0.56, 1.12):
            ztop = 1.3
            if sy < 0 and x == 0.56:
                ztop = 0.98                                                                           # 부러진 말뚝
            T((x, sy * 0.64, 0.74), (x + rng.uniform(-0.01, 0.01), sy * 0.64, ztop), 0.06, 0.055, ref=(0, 1, 0),        # 옆판에 5 mm 묻힘 (면이 딱 맞닿지 않게)
              rot=(0.0, 1.0 if ztop < 1 else 0.3), chips=(1, 2))
    T((-0.99, -0.58, 0.975), (-0.99, 0.58, 0.975), 0.035, 0.17, rot=(0.3, 0.3), name="plank")        # 앞판 (한 장)
    # 뒷판: 아래 경첩에 걸려 아래로 늘어졌다 (두 장 + 띠목)
    hinge = Vector((1.24, 0.0, 0.88))
    Mt = Matrix.Translation(hinge) @ Matrix.Rotation(R(-100), 4, 'Y') @ Matrix.Rotation(R(4), 4, 'X') @ Matrix.Translation(-hinge)
    tail = []
    for z in (0.965, 1.175):
        tail.append(timber(rng, (1.245, -0.58, z), (1.245, 0.58, z), 0.035, 0.16, rot=(0.2, 0.2), chips=(1, 2), name="plank"))
    tail.append(timber(rng, (1.275, -0.3, 0.9), (1.275, -0.3, 1.24), 0.05, 0.03, ref=(0, 1, 0), rot=(0, 0), chips=(0, 1)))
    tail.append(timber(rng, (1.275, 0.32, 0.9), (1.275, 0.32, 1.24), 0.05, 0.03, ref=(0, 1, 0), rot=(0, 0), chips=(0, 1)))
    for o_ in tail:
        place_xf(o_, Mt)
    for a, b in (((1.245, -0.58, 0.965), (1.245, 0.58, 0.965)), ((1.245, -0.58, 1.175), (1.245, 0.58, 1.175)),
                 ((1.275, -0.3, 0.9), (1.275, -0.3, 1.24)), ((1.275, 0.32, 0.9), (1.275, 0.32, 1.24))):
        segs.append((Mt @ Vector(a), Mt @ Vector(b)))
    W += tail
    # 끌채 (앞으로 모여 땅에 닿는다): −Y 는 온전, +Y 는 가운데가 부러졌다
    T((-0.55, -0.55, 0.77), (-2.15, -0.34, 0.8), 0.085, 0.095, rot=(0.0, 0.7))
    T((-0.55, 0.55, 0.77), (-1.35, 0.44, 0.785), 0.085, 0.095, rot=(0.0, 1.0))
    T((-0.85, -0.5, 0.775), (-0.85, 0.5, 0.775), 0.07, 0.08, rot=(0, 0))                             # 끌채 가로대
    bed_objs = W[n0:]
    bed_segs = segs[n0:]
    # 술통 (짐칸 안에서 앞쪽으로 굴러 처박혔다): 통널 결 + 쇠테
    bar = G.obj_bm(G.lathe([(0.0, -0.29), (0.165, -0.29), (0.19, -0.2), (0.215, -0.07), (0.22, 0.0), (0.215, 0.07), (0.19, 0.2), (0.165, 0.29),
                            (0.0, 0.29)], 18), "barrel")
    Mb = Matrix.Translation((-0.56, 0.12, 0.888 + 0.215)) @ Matrix.Rotation(R(76), 4, 'Z') @ Matrix.Rotation(R(90), 4, 'X')
    place_xf(bar, Mb)
    bed_objs.append(bar)
    bed_segs.append((Mb @ Vector((0, 0, -0.29)), Mb @ Vector((0, 0, 0.29))))
    biron = RU.Acc()
    for zz, rr in ((-0.22, 0.188), (-0.12, 0.208), (0.12, 0.208), (0.22, 0.188)):
        v, f = RU.lathe([(rr, zz - 0.018), (rr + 0.006, zz - 0.012), (rr + 0.006, zz + 0.012), (rr, zz + 0.018)], 18)
        f = [ff for ff in f]
        biron.add_raw([Mb @ Vector(p) for p in v], f)
    # 고꾸라짐 (굴대 축으로 −18도) + −Y 로 4도 기울기 (+Y 바퀴 땅 닿은 곳을 축으로)
    Mp = Matrix.Translation((AX, 0, AZ)) @ Matrix.Rotation(R(-18), 4, 'Y') @ Matrix.Translation((-AX, 0, -AZ))
    Mr = Matrix.Translation((0, 0.86, 0)) @ Matrix.Rotation(R(4), 4, 'X') @ Matrix.Translation((0, -0.86, 0))
    for o_ in bed_objs:
        place_xf(o_, Mr @ Mp)
    for i in range(n0, len(segs)):
        segs[i] = (Mr @ Mp @ segs[i][0], Mr @ Mp @ segs[i][1])
    segs.append((Mr @ Mp @ bed_segs[-1][0], Mr @ Mp @ bed_segs[-1][1]))
    W.append(bar)
    iacc = RU.Acc()
    iacc.add_raw([Mr @ Mp @ Vector(p) for p in biron.v], biron.f)
    # 바퀴: +Y 온전, −Y 부서져 주저앉고 바깥으로 기울었다
    for sy in (1, -1):
        if sy > 0:
            objs, wsg, (tv, tf) = wheel(rng)
            Mw = Mr @ Matrix.Translation((AX, 0.78, AZ)) @ Matrix.Rotation(R(8), 4, 'Y')
        else:
            objs, wsg, (tv, tf) = wheel(rng, gone=(4, 5), gone_spokes=(6, 7, 3), stub=(5, 8))
            Mw = Mr @ Matrix.Translation((AX + 0.04, -0.79, AZ - 0.02)) @ Matrix.Rotation(R(10), 4, 'X') @ Matrix.Rotation(R(-23), 4, 'Y')
        for o_ in objs:
            place_xf(o_, Mw)
        W += objs
        segs += [(Mw @ a, Mw @ b) for a, b in wsg]
        iacc.add_raw([Mw @ Vector(p) for p in tv], tf)
    # 땅에 떨어진 것: −Y 윗 옆판 (앞 발치), 부러진 +Y 끌채 앞 토막, 빠진 바퀴테 조각 하나, 바닥판 토막
    T((-0.6, -0.82, 0.035), (0.75, -0.78, 0.06), 0.17, 0.035, ref=(0.05, -0.1, 1), rot=(0.6, 0.8), name="plank")
    T((-1.4, 0.5, 0.05), (-2.05, 0.18, 0.045), 0.085, 0.095, rot=(1.0, 0.3))
    bm = G.annulus_y(0, 0, 0.525, 0.6, -0.0425, 0.0425, 6, 0.0, 2 * math.pi / 7 - 0.03)
    fe = G.obj_bm(bm, "fel", Matrix.Translation((0.95, -0.55, 0.0)) @ Matrix.Rotation(R(-85), 4, 'X') @ Matrix.Rotation(R(200), 4, 'Y'))
    zmn = min(v.co.z for v in fe.data.vertices)
    place_xf(fe, Matrix.Translation((0, 0, -zmn + 0.002)))
    W.append(fe)
    segs.append((Vector((0.95, -0.55, 0.03)), Vector((1.2, -0.75, 0.03))))
    T((-1.5, -0.8, 0.03), (-0.95, -0.7, 0.04), 0.15, 0.035, ref=(0, 0, 1), rot=(1.0, 1.0), name="plank")
    wood = W[0]
    union(wood, W[1:])
    low_w = lowpoly(wood)
    drop_faces(low_w, lambda c, n: c.z < 0.005 and n.z < -0.9)
    print("LOW cart wood", tri_count(low_w))
    # 쇠: 바퀴 쇠테·술통 테 + 짐칸 모서리 쇠 + 못 머리
    for x in (-0.96, 1.2):
        for sy in (-1, 1):
            v, f = RU.bar_path([(x, sy * 0.62, 0.9), (x, sy * 0.62, 1.12)], 0.05, 0.01, ref=(0, 1, 0))
            iacc.add_raw([Mr @ Mp @ Vector(p) for p in v], f)
    iron = iacc.obj("cart_iron")
    low_i = lowpoly(iron)
    wh = copy(wood)
    delete(wood)
    wood_carve(wh, segs, 0.0045, 76, WOOD_PLANK)
    wm = wood_paint("cart_wood", 1.5, k=0.4, moss=0.55, moss_low=0.7, moss_low_h=0.3, dirt=0.85, dirt_h=0.45, rain=0.55, rain_h=0.7)
    G.blotch(wm, (0.12, 0.11, 0.1), 3.0, 0.35, 0.5, 0.64)
    set_mat(wh, wm)
    ih = iron_src(iron)
    delete(iron)
    set_mat(ih, iron_paint("cart_iron", 1.5, rust=0.6))
    cards = N.Cards()
    gr = random.Random(77)
    pts = [(-1.9, -0.25, 0.02), (-1.65, 0.35, 0.02), (AX - 0.1, -0.55, 0.02), (AX + 0.25, 0.6, 0.02), (0.9, -0.3, 0.02), (1.1, 0.4, 0.02),
           (-0.3, -0.2, 0.02), (0.4, 0.2, 0.02)]
    grass_at(cards, gr, pts, (0.25, 0.42), (0.16, 0.26), 0.5)
    print("LOW cart_broken", tri_count(low_w) + tri_count(low_i))
    wt = lambda c, n: 0.6 if (n.z < -0.7) else 1.0
    lod0 = finish3("cart_broken", [wh, ih], [low_w, low_i], extras=[cards.obj("grass")], cage=0.005, cage_reach=0.04, hard=55,
                    uv_margin=0.002, uv_weight=wt, lod1=0.5)
    return repad_textures("cart_broken", lod0)          # 섬 바깥 여백을 섬 안쪽 값으로 다시 메운다 (가는 쇠살·판자 섬이 많아 밉맵에서 테두리가 번진다)


# ═════════════════════════ 13. 작은 납골당 ═════════════════════════
def mausoleum_small():
    """작은 납골당 (작은 랜드마크): 받침 위 돌집, 앞(−Y)에 박공(날개 해골 새김) + 둥근 아치 문 + 비문 상인방. 문은 깊게 들어간 아치 현관이고
    쇠창살 문 한 짝은 안으로 열리고 한 짝은 처져 비스듬히 걸렸다. 안쪽 작은 방 제단의 단지에 영혼불(Glow_Soul) — 광원 (0, −2.4, 1.6) 은
    문 아치 안. 지붕 꼭대기 앞 꼭지돌(4.8 m), 앞 왼쪽 모서리 장식돌은 떨어져 발치에 굴렀다. 뒤 오른쪽 지붕 모서리가 깨졌다.
    벽은 다듬은 돌 줄눈(V 홈), 빗물 때·흙물·이끼, 왼쪽 모서리로 덩굴"""
    rng = random.Random(7704)
    Y0 = -2.6                                                     # 앞면
    # k5 i3: 상자끼리 면이 딱 맞닿으면(받침 윗면 = 몸 밑면 z 0.24, 몸 윗면 = 처마 띠 밑면) EXACT union 이 그 면을 지우지 못해
    #        저폴리 속에 큰 면이 남았다 (저폴리 넓이의 25%, 원본은 리메시라 그 면이 없어 광선이 멀리 날아가 steep 22.8%).
    #        → 부품마다 2~4 cm 씩 겹치게, 같은 평면에 놓인 면이 없게
    parts = [box(4.4, 5.18, 0.36, (0, 0.0, 0.06)),                # 받침 z -0.12..0.24, y -2.59..2.59
             box(3.9, 4.85, 3.17, (0, 0.125, 0.2 + 1.585)),       # 몸 z 0.2..3.37, y -2.3..2.55
             box(2.5, 0.32, 3.18, (0, Y0 + 0.16, 0.18 + 1.59)),   # 앞 문틀 (y -2.6..-2.28, z 0.18..3.36)
             box(4.1, 5.23, 0.23, (0, 0.005, 3.435))]             # 처마 띠 z 3.32..3.55, y -2.61..2.62
    for sx in (-1, 1):                                            # 문 양옆 붙은 기둥 + 머리
        parts.append(box(0.34, 0.08, 2.94, (sx * 1.0, Y0 - 0.02, 0.2 + 1.47)))        # y -2.66..-2.58 (받침 앞면 -2.59 과 겹침)
        parts.append(box(0.44, 0.1, 0.16, (sx * 1.0, Y0 - 0.035, 3.2)))
    roof = prism([(-2.12, 3.5), (2.12, 3.5), (2.12, 3.6), (0.0, 4.52), (-2.12, 3.6)], Y0 - 0.02, 2.63)
    parts.append(roof)
    ridge = cyl(0.085, 5.2, (0, 0.01, 4.52), 10, rot=(R(90), 0, 0))
    parts.append(ridge)
    # 꼭지돌 (앞 박공 꼭대기) + 모서리 장식돌 (앞 오른쪽만 남음, 뒤 둘)
    parts.append(G.obj_bm(G.bm_frustum(0.3, 0.3, 0.12, 0.12, 4.38, 4.68), "fin", Matrix.Translation((0, Y0 + 0.14, 0))))   # 밑이 지붕 속으로 (뜬 모서리 없게)
    parts.append(G.obj_bm(G.lathe([(0.0, 4.66), (0.1, 4.67), (0.13, 4.72), (0.09, 4.78), (0.0, 4.8)], 10), "fin2", Matrix.Translation((0, Y0 + 0.14, 0))))
    for (x, y) in ((1.92, Y0 + 0.14), (-1.92, 2.48), (1.92, 2.48)):
        parts.append(G.obj_bm(G.bm_frustum(0.24, 0.24, 0.14, 0.14, 3.52, 3.82), "acro", Matrix.Translation((x, y, 0))))
    body = parts[0]
    union(body, parts[1:])
    xf_all(body)        # k5 i1: box() 는 위치를 객체에 남긴다 → engrave_surface 의 ray_cast(객체 좌표)가 6 cm 아래를 맞혀 지붕 돌판 이음 홈이
                        #        지붕 속 빈틈으로 파였고, 되붙이기(snap)가 그 빈틈 정점을 겉면으로 끌어 지붕이 구겨졌다 (steep 37.7%)
    # 현관 아치 (깊게 들어간 문) + 안쪽 작은 방 + 박공 안 우묵한 삼각면
    arch = [(-0.62, 0.12), (0.62, 0.12), (0.62, 2.05)] + [(0.62 * math.cos(a), 2.05 + 0.62 * math.sin(a)) for a in [math.pi * i / 14 for i in range(1, 14)]] + [(-0.62, 2.05)]
    # 문턱 z 0.12 (받침을 12 cm 파고 든다), 안쪽 방 바닥 z 0.2 (문턱·받침 윗면과 다른 높이 — 같은 평면이면 불리언이 흔들린다)
    cut(body, [G.obj_bm(G.bm_poly(arch, Y0 - 0.2, -1.95), "arch")])
    cut(body, [box(1.7, 1.75, 2.49, (0, -2.0 + 0.875 + 0.0, 0.2 + 1.245))])          # 안쪽 방 y -2.0..-0.25, z 0.2..2.69
    tri = [(-1.78, 3.64), (1.78, 3.64), (0.0, 4.32)]
    cut(body, [G.obj_bm(G.bm_poly(tri, Y0 - 0.2, Y0 + 0.07), "tymp")])
    # 문 앞 디딤돌 한 단 (받침 앞면과 2 cm 겹쳐 union. 예전: 아치 안에 join 한 두 단 — 아치 벽과 같은 평면에 겹친 면이 남았다)
    body = union(body, [box(1.5, 0.3, 0.15, (0, Y0 - 0.12, 0.005))])          # y -2.87..-2.57, z -0.07..0.08
    chip(body, rng, 34, (0.05, 0.12), sharp_deg=35, bite=0.37, zmin=0.1)
    cut(body, [G.chunk((2.12, 2.6, 3.58), (0.42, 0.5, 0.3), rng, 9, (0.1, 0.3)),               # 뒤 오른쪽 지붕 모서리 깨짐
               G.chunk((-1.92, Y0 + 0.14, 3.7), (0.2, 0.2, 0.2), rng, 8, (0.1, 0.3)),            # 떨어져 나간 장식돌 자리
               G.chunk((-2.2, -1.0, 0.24), (0.18, 0.3, 0.12), rng, 8, (0.1, 0.3)),
               G.chunk((2.05, -2.62, 3.46), (0.2, 0.16, 0.14), rng, 8, (0.1, 0.3)),            # 처마 앞 오른쪽 모서리
               G.chunk((1.95, 0.6, 0.5), (0.12, 0.3, 0.2), rng, 8, (0.1, 0.3))])
    low_src = copy(body)
    esrc = copy(body)
    # 줄눈 (V 홈): 옆·뒷벽·앞벽(문틀 밖) 의 켜 + 엇갈린 세로 줄눈
    jr = random.Random(7714)
    st_x = {-1: [], 1: []}
    st_y, st_f = [], []
    zs = [0.24 + 0.44 * k for k in range(8) if 0.24 + 0.44 * k < 3.3] + [3.34]
    for k in range(len(zs) - 1):
        z, z1 = zs[k], zs[k + 1]
        for sx in (-1, 1):
            if k:
                st_x[sx].append((Vector((sx * 1.95, -2.28, z)), Vector((sx * 1.95, 2.53, z))))
                st_f.append((Vector((sx * 1.26, -2.3, z)), Vector((sx * 1.93, -2.3, z))))
            y = -2.3 + jr.uniform(0.2, 0.6) + (0.45 if k % 2 else 0.0)
            while y < 2.45:
                st_x[sx].append((Vector((sx * 1.95, y, z)), Vector((sx * 1.95, y, z1))))
                y += jr.uniform(0.75, 1.1)
            xf_ = sx * (1.25 + jr.uniform(0.25, 0.45))
            st_f.append((Vector((xf_, -2.3, z)), Vector((xf_, -2.3, z1))))
        if k:
            st_y.append((Vector((-1.93, 2.55, z)), Vector((1.93, 2.55, z))))
        x = -1.95 + jr.uniform(0.2, 0.6) + (0.4 if k % 2 else 0.0)
        while x < 1.85:
            st_y.append((Vector((x, 2.55, z)), Vector((x, 2.55, z1))))
            x += jr.uniform(0.7, 1.05)
    engrave_v(body, st_x[-1], (-1, 0, 0), 0.03, 0.014, floor=0.35)
    engrave_v(body, st_x[1], (1, 0, 0), 0.03, 0.014, floor=0.35)
    engrave_v(body, st_y, (0, 1, 0), 0.03, 0.014, floor=0.35)
    engrave_v(body, st_f, (0, -1, 0), 0.03, 0.014, floor=0.35)
    # 지붕 돌판 이음 (경사를 따라)
    rs = []
    y = -2.2
    while y < 2.5:
        for sx in (-1, 1):
            rs.append(((sx * 2.1, y, 4.3), (sx * 0.12, y, 5.2)))
        y += jr.uniform(0.55, 0.7)
    for sx in (-1, 1):
        engrave_surface(body, [(Vector((a[0], a[1], 3.61)), Vector((b[0] * 0.95, b[1], 4.45))) for a, b in rs if a[0] * sx > 0],
                        (sx * 0.4, 0, 0.92), 0.045, 0.02, step=0.25, floor=0.35)
    # 비문 상인방 (아치 위) + 박공 날개 해골
    tr = random.Random(7715)
    yf = Y0 - 0.05
    st = rune_strokes(tr, 0.0, 2.98, 1.0, 0.085, yf, 0.06, [(0.32, 2.95, 0.12)])
    st += rune_strokes(tr, 0.0, 2.84, 0.8, 0.07, yf, 0.1, [(0.32, 2.95, 0.12)])
    engrave_surface(body, st, (0, -1, 0), 0.016, 0.009, step=0.02, floor=0.3)
    sk = winged_skull_strokes(random.Random(7716), 0.0, 3.9, 0.11, Y0 + 0.07, wing=3.2)
    engrave_surface(body, [(a + Vector((0, -0.5, 0)), b + Vector((0, -0.5, 0))) for a, b in sk], (0, -1, 0), 0.02, 0.011, step=0.025, floor=0.3)
    # 옆벽 긴 금
    ck = G.crack_strokes(random.Random(7717), (-1.0, 0, 3.2), (0.3, 0, -1), 1.6, 8, 0.4)
    engrave_surface(body, [(Vector((-2.5, a.x, a.z)), Vector((-2.5, b.x, b.z))) for a, b in ck], (-1, 0, 0), 0.016, 0.008, step=0.05, floor=0.25)
    # 원본: 다듬은 돌 (금·잔 구멍만, 끌 자국 칸 없음)
    carve(body, 0.012, [{'t': 'lumps', 'scale': 0.35, 'amp': 0.002}], stone_fine(2.0), seed=78, edge_from=esrc)
    m = stone_paint("mausoleum_src", 4.8, 2.0, rain=0.9, rain_h=1.9, splash_z=0.24, splash_h=0.5, stains=1.0,
                    moss_low_h=0.9, dirt=0.9, dirt_h=0.8, edge_w=0.014)
    G.blotch(m, (0.12, 0.12, 0.13), 0.8, 0.45, 0.5, 0.66)             # 크게 번진 검은 물때 (새 돌처럼 고르지 않게)
    G.tint_near(m, (0.0, -1.2, 1.2), 1.1, (0.02, 0.018, 0.03), 0.8)               # 안쪽 방 어둠
    set_mat(body, m)
    low = lowpoly(low_src)
    delete(low_src)
    drop_faces(low, lambda c, n: c.z < -0.1 and n.z < -0.9)
    print("LOW mausoleum stone", tri_count(low))
    # 안쪽 제단 + 단지 (돌) + 영혼불
    alt = [box(0.9, 0.42, 0.87, (0, -0.48, 0.15 + 0.435)), box(1.0, 0.5, 0.08, (0, -0.48, 1.06))]       # 밑이 방 바닥(0.2) 속으로
    union(alt[0], [alt[1]])
    urn = G.obj_bm(G.lathe([(0.0, 1.1), (0.1, 1.1), (0.12, 1.14), (0.07, 1.18), (0.08, 1.24), (0.16, 1.33), (0.17, 1.42), (0.13, 1.5), (0.0, 1.5)], 14), "urn",
                   Matrix.Translation((0, -0.5, 0)))
    altar = join([alt[0], urn])
    low_a = lowpoly(altar)
    drop_faces(low_a, lambda c, n: c.z < 0.2 and n.z < -0.9)
    carve(altar, 0.006, [], stone_fine(1.0), seed=79)
    set_mat(altar, stone_paint("mausoleum_altar", 1.5, 1.0, moss=0.3, rain=0.3))
    gl = []
    o, _ = flame_lick((0.0, -0.5, 1.48), 0.34, 0.06, (0.02, -0.03), curl=0.03, twist=1.8, name='Glow_Soul'); gl.append(o)
    o, _ = flame_lick((0.04, -0.48, 1.48), 0.2, 0.04, (-0.04, 0.01), curl=-0.02, twist=-1.4, name='Glow_Soul'); gl.append(o)
    for (x, z) in ((-0.32, 1.16), (0.33, 1.14)):                    # 제단 위 영혼 촛불 둘 (뼈빛 초 + 작은 불)
        o, _ = flame_lick((x, -0.42, z + 0.12), 0.07, 0.014, (0.0, 0.0), curl=0.004, twist=1.0, name='Glow_Soul'); gl.append(o)
    candles = [cyl(0.03, 0.12, (x, -0.42, z + 0.06), 8) for x, z in ((-0.32, 1.1), (0.33, 1.1))]
    # 쇠창살 문 두 짝 (한 짝은 안으로 65도 열림, 한 짝은 처져 비스듬히 바깥으로 25도)
    gacc = RU.Acc()
    for side in (-1, 1):
        lf = RU.Acc()
        w_ = 0.6
        top = lambda x: 1.68 + 0.5 * math.sin(0.5 * math.pi * x / w_)       # 아치 밑에 맞춰 문 가운데 쪽이 높다
        for k in range(6):
            x = 0.06 + (w_ - 0.1) * k / 5
            v, f = RU.bar_path([(x, 0, 0.06), (x, 0, top(x))], 0.022); lf.add_raw(v, f)
            v, f = RU.spear((x, 0, top(x)), (0, 0, 1), 0.09, 0.04, 0.012); lf.add_raw(v, f)
        for z in (0.12, 1.0, 1.62):
            v, f = RU.bar_path([(0.0, 0, z), (w_, 0, z)], 0.04, 0.014); lf.add_raw(v, f)
        v, f = RU.bar_path([(0.0, 0, 0.04), (0.0, 0, 1.78)], 0.04); lf.add_raw(v, f)
        if side < 0:                                              # 왼쪽 문짝: 안으로 65도 열림
            M = Matrix.Translation((-0.6, -1.97, 0.12)) @ Matrix.Rotation(R(65), 4, 'Z')
        else:                                                     # 오른쪽 문짝: 바깥으로 25도, 경첩이 빠져 처졌다
            M = Matrix.Translation((0.6, -1.97, 0.12)) @ Matrix.Rotation(R(205), 4, 'Z') @ Matrix.Rotation(R(-6), 4, 'Y')
        gacc.add_raw([M @ Vector(p) for p in lf.v], lf.f)
    gate = gacc.obj("maus_gate")
    low_g = lowpoly(gate)
    gh = iron_src(gate)
    delete(gate)
    set_mat(gh, iron_paint("mausoleum_gate", 2.4, rust=0.5))
    # 떨어진 장식돌 + 돌 조각
    frag = G.chunk((-1.7, Y0 - 0.22, 0.1), (0.15, 0.13, 0.12), rng, 9, (0.08, 0.25))
    frag2 = G.chunk((-1.35, Y0 - 0.2, 0.05), (0.08, 0.07, 0.05), rng, 8, (0.08, 0.25))
    fr = join([frag, frag2] + candles)
    low_f = lowpoly(fr, z=-0.01)
    carve(fr, 0.005, [], stone_fine(1.0), seed=80)
    set_mat(fr, stone_paint("mausoleum_frag", 0.3, 0.5, moss=0.6, rain=0.0))
    # 덩굴 (앞 왼쪽 모서리 → 옆벽) + 발치 풀
    v = G.Vine(random.Random(81), leaf=(0.05, 0.085), leaf_p=0.42)
    tgt = join([copy(low)])
    G.ivy_grow(v, tgt, (-2.0, -2.0, 0.26), seed=82, length=3.2, step=0.04, max_roots=9, gravity=0.35, adhesion=0.85, zmax=3.4)
    G.ivy_grow(v, tgt, (1.96, 1.8, 0.26), seed=83, length=1.6, step=0.04, max_roots=5, gravity=0.4, adhesion=0.85, zmax=2.4)
    delete(tgt)
    cards = N.Cards()
    gr = random.Random(84)
    pts = [(sx * 2.1, y, 0.24) for sx in (-1, 1) for y in (-1.6, -0.4, 0.9, 2.1)] + [(-1.1, 2.5, 0.24), (0.8, 2.5, 0.24), (1.6, -2.45, 0.24)]
    grass_at(cards, gr, pts, (0.2, 0.36), (0.12, 0.18), 0.5)

    def wt(c, n):
        if c.y > -1.98 and abs(c.x) < 0.9 and 0.2 < c.z < 2.75 and c.y < -0.2:
            return 0.4                                           # 안쪽 방
        if n.z > 0.5 and c.z > 3.5:
            return 0.5                                           # 지붕 윗면 (눈높이에서 비스듬히 보인다)
        if n.y < -0.6:
            return 1.0                                           # 앞면
        if n.z > 0.6 or n.z < -0.6 or c.y > 2.5:
            return 0.5                                           # 받침 윗면·처마 밑·뒷벽
        return 0.75
    print("LOW mausoleum_small", tri_count(low) + tri_count(low_a) + tri_count(low_g) + tri_count(low_f))
    lod0 = finish3("mausoleum_small", [body, altar, gh, fr], [low, low_a, low_g, low_f], extras=gl + v.objects() + [cards.obj("grass")],
                    cage=0.012, cage_reach=0.08, hard=55, uv_margin=0.0015, uv_weight=wt, lod1=0.4)
    return repad_textures("mausoleum_small", lod0)          # 섬 바깥 여백을 섬 안쪽 값으로 다시 메운다 (가는 쇠살·판자 섬이 많아 밉맵에서 테두리가 번진다)


# ═════════════════════════ 14. 길가 사당 ═════════════════════════
def shrine_roadside():
    """길가 사당: 넓적한 받침돌 위 위로 좁아지는 돌기둥, 앞(−Y)에 둥근 감실(안에 작은 돌 그릇 + 영혼불 Glow_Soul, 광원 (0, −0.35, 1.2)),
    위에는 앞을 향한 박공 돌지붕 + 꼭지 혹. 감실 둘레에 판 테두리, 아래에는 닳은 비문 두 줄. 받침 위에 해골 하나와
    쌓은 조약돌, 타다 만 초 둘. 지붕 모서리 하나가 깨졌다"""
    rng = random.Random(7705)
    YC = -0.06
    base = G.obj_bm(rough_box(rng, 1.0, 0.92, 0.22, jit=0.04, chips=(3, 5), depth=(0.02, 0.05), flakes=(0, 1), bevel=0.008), "base",
                    Matrix.Translation((0, YC, 0.07)))
    body = G.obj_bm(G.bm_frustum(0.68, 0.72, 0.58, 0.62, 0.17, 1.76), "body", Matrix.Translation((0, YC, 0)))
    slab = box(1.14, 0.98, 0.08, (0, YC - 0.02, 1.79))
    gab = prism([(-0.64, 1.82), (0.64, 1.82), (0.64, 1.86), (0.0, 2.15), (-0.64, 1.86)], YC - 0.53, YC + 0.47)
    knob = G.obj_bm(G.lathe([(0.0, 2.1), (0.06, 2.1), (0.075, 2.14), (0.045, 2.19), (0.0, 2.25)], 8), "knob", Matrix.Translation((0, YC - 0.44, 0)))
    union(base, [body, slab, gab, knob])
    o = base
    # 감실 (둥근 아치, 깊이 0.27) + 감실 둘레 판 테두리
    arch = [(-0.17, 0.98), (0.17, 0.98), (0.17, 1.3)] + [(0.17 * math.cos(a), 1.3 + 0.17 * math.sin(a)) for a in [math.pi * i / 12 for i in range(1, 12)]] + [(-0.17, 1.3)]
    yfront = YC - 0.33
    cut(o, [G.obj_bm(G.bm_poly(arch, yfront - 0.2, yfront + 0.27), "niche")])
    chip(o, rng, 16, (0.03, 0.07), sharp_deg=35, bite=0.37, zmin=0.2)
    cut(o, [G.chunk((0.64, YC + 0.47, 1.84), (0.16, 0.14, 0.1), rng, 9, (0.1, 0.3))])            # 지붕 뒤 오른쪽 모서리 깨짐
    low_src = copy(o)
    esrc = copy(o)
    frame = [(0.27 * math.cos(a), 1.3 + 0.27 * math.sin(a)) for a in [math.pi * i / 14 for i in range(15)]]
    fs = [(Vector((-0.27, -1.0, 0.9)), Vector((-0.27, -1.0, 1.3))), (Vector((0.27, -1.0, 0.9)), Vector((0.27, -1.0, 1.3))),
          (Vector((-0.27, -1.0, 0.9)), Vector((0.27, -1.0, 0.9)))]
    fs += [(Vector((a[0], -1.0, a[1])), Vector((b[0], -1.0, b[1]))) for a, b in zip(frame, frame[1:])]
    # 감실 아래 닳은 비문 두 줄 (지어낸 글꼴, 석관과 같은 RUNES). 첫 시안의 이중 나선 둘은 4 m 에서 'ele' 글자처럼 읽혀 바꿨다
    tr = random.Random(7718)
    sp = rune_strokes(tr, 0.0, 0.7, 0.4, 0.075, -1.0, 0.12, [(0.12, 0.6, 0.06)])
    sp += rune_strokes(tr, 0.0, 0.58, 0.34, 0.065, -1.0, 0.18, [(0.12, 0.6, 0.06)])
    engrave_surface(o, fs, (0, -1, 0), 0.022, 0.008, step=0.03, floor=0.4)
    engrave_surface(o, sp, (0, -1, 0), 0.016, 0.008, step=0.02, floor=0.35)
    ck = G.crack_strokes(random.Random(19), (0.22, 0, 1.75), (0.2, 0, -1), 0.5, 6, 0.4)
    engrave_surface(o, [(Vector((a.x, -1.0, a.z)), Vector((b.x, -1.0, b.z))) for a, b in ck], (0, -1, 0), 0.012, 0.006, step=0.04, floor=0.25)
    carve(o, 0.0035, [{'t': 'lumps', 'scale': 0.6, 'amp': 0.0006}], stone_fine(1.0), seed=85, edge_from=esrc)
    smooth_near_strokes(o, sp, 0.028, 6, 0.5)
    m = stone_paint("shrine_src", 2.2, 1.0, moss=1.0, moss_patch=1.3, rain=0.8, rain_h=0.9, splash_z=0.17, splash_h=0.25)
    G.tint_near(m, (0.0, YC - 0.25, 1.15), 0.2, (0.03, 0.025, 0.04), 0.7)        # 감실 안 그을음
    set_mat(o, m)
    low = lowpoly(low_src)
    delete(low_src)
    drop_faces(low, lambda c, n: c.z < -0.02 and n.z < -0.9)
    # 감실 그릇 + 영혼불
    bowl = G.obj_bm(G.lathe([(0.0, 0.98), (0.05, 0.98), (0.075, 1.0), (0.085, 1.05), (0.07, 1.055), (0.055, 1.02), (0.0, 1.02)], 12), "bowl",
                    Matrix.Translation((0, YC - 0.2, 0)))
    # 받침 위 조약돌 + 초 둘
    peb = []
    zz = 0.18
    for s_ in (0.07, 0.055, 0.04):                                  # 쌓은 조약돌 셋
        peb.append(G.chunk((0.33 + rng.uniform(-0.01, 0.01), YC - 0.32, zz + s_ * 0.45), (s_, s_ * 0.85, s_ * 0.5), rng, 7, (0.08, 0.25), sub=1))
        zz += s_ * 0.85
    peb.append(cyl(0.028, 0.09, (-0.12, YC - 0.36, 0.22), 8))
    peb.append(cyl(0.024, 0.05, (-0.03, YC - 0.4, 0.2), 8))
    small = join([bowl] + peb)
    low_m = lowpoly(small)
    carve(small, 0.003, [], stone_fine(0.5), seed=86)
    set_mat(small, stone_paint("shrine_small", 0.3, 0.4, moss=0.4, rain=0.0, splash=0.0))
    sk = G.skull_high(random.Random(87), jaw_open=4, seed=87, moss=0.25, dirt=0.4)
    Msk = Matrix.Translation((-0.32, YC - 0.3, 0.165)) @ Matrix.Rotation(R(-20), 4, 'Z') @ Matrix.Rotation(R(-8), 4, 'X')
    sk.data.transform(Msk); sk.data.update()
    low_k = kit.decimated(sk, 500)
    gl = []
    o2, _ = flame_lick((0.0, YC - 0.2, 1.03), 0.16, 0.034, (0.01, -0.01), curl=0.015, twist=1.6, name='Glow_Soul'); gl.append(o2)
    o2, _ = flame_lick((0.02, YC - 0.21, 1.03), 0.09, 0.02, (-0.02, 0.0), curl=-0.01, twist=-1.2, name='Glow_Soul'); gl.append(o2)
    v = G.Vine(random.Random(88), leaf=(0.035, 0.06), leaf_p=0.42)
    tgt = copy(low)
    G.ivy_grow(v, tgt, (0.34, 0.3, 0.2), seed=89, length=0.9, step=0.03, max_roots=4, gravity=0.4, adhesion=0.85, zmax=1.4)
    delete(tgt)
    cards = N.Cards()
    gr = random.Random(90)
    grass_at(cards, gr, [(0.42, 0.3, 0.17), (-0.43, 0.32, 0.17), (0.44, -0.2, 0.17)], (0.14, 0.24), (0.1, 0.14), 0.5)
    wt = lambda c, n: 1.0 if n.y < -0.6 else (0.5 if n.z < -0.6 else 0.8)
    print("LOW shrine_roadside", tri_count(low) + tri_count(low_m) + tri_count(low_k))
    lod0 = finish3("shrine_roadside", [o, small, sk], [low, low_m, low_k], extras=gl + v.objects() + [cards.obj("grass")], cage=0.006,
                    cage_reach=0.05, hard=55, uv_margin=0.002, uv_weight=wt)
    return repad_textures("shrine_roadside", lod0)          # 섬 바깥 여백을 섬 안쪽 값으로 다시 메운다 (가는 쇠살·판자 섬이 많아 밉맵에서 테두리가 번진다)


# ═════════════════════════ 15. 사슬 오벨리스크 ═════════════════════════
def obelisk_chained():
    """사슬 오벨리스크: 두 단 받침 위 위로 좁아지는 검은 돌 기둥 + 끝이 깨진 피라미드 머리 (4.6 m, 1.5도 기울었다).
    기둥 2.9 m 높이의 쇠 목테에서 사슬 셋이 받침 모서리의 쇠고리로 팽팽히 내려가고, 넷째는 끊겨 늘어졌다. 1.75 m 에는 느슨한 사슬이
    기둥을 한 바퀴 감고 앞에서 큰 자물쇠로 잠겼다. 앞면에는 세로로 지어낸 글자 줄, 비스듬한 긴 금, 목테 아래로 녹물.
    40 m 에서 '키 큰 바늘 + 땅으로 뻗은 사슬 줄' 실루엣"""
    rng = random.Random(7706)
    p1 = box(1.5, 1.5, 0.34, (0, 0, 0.07))
    p2 = G.obj_bm(G.bm_frustum(1.12, 1.12, 1.0, 1.0, 0.24, 0.62), "p2")
    shaft = G.obj_bm(G.bm_frustum(0.6, 0.6, 0.38, 0.38, 0.6, 4.08), "shaft")
    pyr = G.obj_bm(G.bm_frustum(0.42, 0.42, 0.03, 0.03, 4.05, 4.6), "pyr")
    union(shaft, [pyr])
    Ml = Matrix.Translation((0, 0, 0.62)) @ Matrix.Rotation(R(1.5), 4, 'Y') @ Matrix.Rotation(R(-0.8), 4, 'X') @ Matrix.Translation((0, 0, -0.62))
    place_xf(shaft, Ml)
    union(p1, [p2, shaft])
    xf_all(p1)          # engrave_surface 의 ray_cast 는 객체 좌표 — box() 가 남긴 위치(z 0.07)를 먼저 적용한다
    o = p1
    chip(o, rng, 20, (0.04, 0.1), sharp_deg=35, bite=0.37, zmin=0.1)
    cut(o, [G.chunk(tuple(Ml @ Vector((0.05, -0.02, 4.58))), (0.12, 0.1, 0.12), rng, 9, (0.1, 0.3)),        # 깨진 끝
            G.chunk(tuple(Ml @ Vector((-0.2, 0.19, 3.98))), (0.16, 0.15, 0.2), rng, 9, (0.1, 0.3)),         # 머리 뒤 모서리
            G.chunk((0.75, -0.75, 0.2), (0.2, 0.2, 0.14), rng, 8, (0.1, 0.3))])
    low_src = copy(o)
    esrc = copy(o)
    tr = random.Random(7719)
    st = []
    for z, w_ in ((3.62, 0.3), (3.38, 0.3), (3.14, 0.32), (2.5, 0.34), (2.26, 0.36), (2.02, 0.36)):
        st += rune_strokes(tr, 0.0, z, w_, 0.12, -1.0, 0.2, [(0.08, 2.3, 0.1), (-0.1, 3.4, 0.08)])
    st = [(Ml @ a, Ml @ b) for a, b in st]
    engrave_surface(o, st, (0, -1, 0), 0.018, 0.01, step=0.02, floor=0.3)
    ck = G.crack_strokes(random.Random(7720), (-0.22, 0, 0.9), (0.35, 0, 1), 0.9, 7, 0.35)
    engrave_surface(o, [(Vector((a.x, -1.0, a.z)), Vector((b.x, -1.0, b.z))) for a, b in ck], (0, -1, 0), 0.014, 0.007, step=0.04, floor=0.25)
    ck2 = G.crack_strokes(random.Random(7721), (0.2, 0, 3.0), (-0.3, 0, -1), 0.8, 6, 0.4)
    engrave_surface(o, [(Vector((1.0, a.x, a.z)), Vector((1.0, b.x, b.z))) for a, b in ck2], (1, 0, 0), 0.014, 0.007, step=0.04, floor=0.25)
    fine = stone_fine(1.4)
    fine[0]['cover'] = 0.08; fine[1]['cover'] = 0.07                # 넓은 면에 그물처럼 번지는 잔금을 줄인다 (거북등처럼 읽히지 않게)
    carve(o, 0.0055, [{'t': 'lumps', 'scale': 0.5, 'amp': 0.0015}], fine, seed=91, edge_from=esrc)
    m = stone_paint("obelisk_src", 4.6, 1.4, pal=OBELISK_STONE, moss=0.8, moss_low=0.9, moss_low_h=0.7, rain=0.85, rain_h=2.2,
                    splash_z=0.24, splash_h=0.4, edge_w=0.012)
    G.tint_near(m, tuple(Ml @ Vector((0.0, -0.25, 2.65))), 0.5, (0.2, 0.09, 0.05), 0.45)        # 목테 아래 녹물
    set_mat(o, m)
    low = lowpoly(low_src)
    delete(low_src)
    drop_faces(low, lambda c, n: c.z < -0.05 and n.z < -0.9)
    # 쇠: 목테 + 모서리 고리 넷, 받침 쇠고리 넷 (박은 꺾쇠), 사슬, 자물쇠
    acc = RU.Acc()
    zc = 2.9
    hw = 0.3 - 0.11 * (zc - 0.6) / 3.48 + 0.014
    sq = [(-hw, -hw), (hw, -hw), (hw, hw), (-hw, hw), (-hw, -hw)]
    v, f = RU.bar_path([Ml @ Vector((x, y, zc)) for x, y in sq], 0.022, 0.1, ref=(0, 0, 1)); acc.add_raw(v, f)
    lugs, anchors = [], []
    for sx, sy in ((1, -1), (-1, -1), (-1, 1), (1, 1)):
        lp = Ml @ Vector((sx * (hw + 0.035), sy * (hw + 0.035), zc - 0.06))
        dvec = Vector((sx, sy, 0)).normalized()
        up = Vector((0, 0, 1))
        Mlug = Matrix((dvec, up, dvec.cross(up))).transposed().to_4x4()
        Mlug.translation = lp
        v, f = RU.torus_raw(0.04, 0.012, Mlug, 10, 4); acc.add_raw(v, f)
        lugs.append(lp)
        ap = Vector((sx * 0.64, sy * 0.64, 0.24))
        v, f = RU.torus_raw(0.05, 0.013, Matrix.Translation(ap + Vector((0, 0, 0.04))) @ Matrix.Rotation(math.atan2(sy, sx), 4, 'Z') @ Matrix.Rotation(R(90), 4, 'X'), 10, 4)
        acc.add_raw(v, f)
        v, f = bm_to_raw(G.bm_box(0.09, 0.05, 0.03), Matrix.Translation(ap + Vector((0, 0, 0.012))) @ Matrix.Rotation(math.atan2(sy, sx), 4, 'Z'))
        acc.add_raw(v, f)
        anchors.append(ap + Vector((0, 0, 0.07)))
    nl = 0
    for i, (lp, ap) in enumerate(zip(lugs, anchors)):
        if i == 2:                                                 # 끊겨 늘어진 사슬 (뒤 왼쪽)
            hang = [lp - Vector((0, 0, 0.03)), lp + Vector((-0.04, 0.03, -0.5)), lp + Vector((-0.05, 0.05, -1.05))]
            nl += chain_links(acc, hang, link=0.13, wide=0.075, wire=0.016)
            rest = [ap, ap + Vector((0.12, -0.08, -0.01)), ap + Vector((0.22, -0.25, 0.0))]
            nl += chain_links(acc, rest, link=0.13, wide=0.075, wire=0.016, spin=0.3)
            continue
        nl += chain_links(acc, sag_path(lp - Vector((0, 0, 0.03)), ap, 0.06, 18), link=0.13, wide=0.075, wire=0.016, spin=0.2 * i)
    # 느슨하게 감은 사슬 (1.75 m) + 앞 자물쇠
    zl = 1.78
    hl = 0.3 - 0.11 * (zl - 0.6) / 3.48 + 0.04
    loop = [(0.0, -hl - 0.07, zl - 0.2), (hl, -hl, zl - 0.06), (hl, hl, zl + 0.03), (-hl, hl, zl + 0.05), (-hl, -hl, zl - 0.04), (-0.02, -hl - 0.07, zl - 0.2)]
    loop = [Ml @ Vector(p) for p in loop]
    pathl = []
    for a, b in zip(loop, loop[1:]):
        pathl += [a.lerp(b, t / 6) for t in range(6)]
    pathl.append(loop[-1])
    nl += chain_links(acc, pathl, link=0.13, wide=0.075, wire=0.016)
    lp = Ml @ Vector((0.0, -hl - 0.1, zl - 0.33))
    v, f = bm_to_raw(G.bm_box(0.15, 0.06, 0.13), Matrix.Translation(lp)); acc.add_raw(v, f)
    v, f = RU.torus_raw(0.05, 0.013, Matrix.Translation(lp + Vector((0, 0, 0.07))) @ Matrix.Rotation(R(90), 4, 'X'), 10, 4); acc.add_raw(v, f)
    print("CHAIN links", nl)
    iron = acc.obj("obelisk_iron")
    low_i = lowpoly(iron)
    ih = iron_src(iron)
    delete(iron)
    set_mat(ih, iron_paint("obelisk_iron", 4.6, rust=0.55))
    cards = N.Cards()
    gr = random.Random(92)
    pts = [(sx * 0.62, sy * 0.3, 0.24) for sx in (-1, 1) for sy in (-1, 1)] + [(0.3, 0.62, 0.24), (-0.3, -0.62, 0.24)]
    grass_at(cards, gr, pts, (0.18, 0.3), (0.12, 0.18), 0.5)
    print("LOW obelisk_chained", tri_count(low) + tri_count(low_i))
    wt = lambda c, n: 1.0 if (n.y < -0.6 and c.z > 0.6) else (0.6 if c.z < 0.6 else 0.85)
    lod0 = finish3("obelisk_chained", [o, ih], [low, low_i], extras=[cards.obj("grass")], cage=0.008, cage_reach=0.06, hard=55,
                    uv_margin=0.002, uv_weight=wt, lod1=0.5)
    return repad_textures("obelisk_chained", lod0)          # 섬 바깥 여백을 섬 안쪽 값으로 다시 메운다 (가는 쇠살·판자 섬이 많아 밉맵에서 테두리가 번진다)


# ═════════════════════════ 16. 찢긴 천막 ═════════════════════════
def tent_torn():
    """찢긴 천막: 앞뒤(±X) 장대 + 마룻대에 걸친 마름모꼴 천막. 뒤 장대는 +X 로 기울어 마룻대가 그쪽으로 처졌다. 앞(−Y) 경사면은 아랫단에서
    마룻대 가까이까지 V 자로 찢겨 벌어져 안이 들여다보이고(말아 둔 깔개·나무 상자), 아랫단은 들쭉날쭉. 뒤 경사면은 구멍 하나 + 갈라진 틈. 뒤 박공은 삼각 천으로 막혔고
    앞 박공은 열린 채 한쪽 자락만 늘어졌다. 장대 끝에서 말뚝으로 당긴 밧줄, 천 귀퉁이 말뚝. 천은 바랜 아마색에 얼룩·곰팡이·흙물"""
    rng = random.Random(7707)
    # 장대
    P0 = Vector((-1.56, 0.0, 2.34)); P1 = Vector((1.64, 0.06, 2.04))
    poles = []
    psegs = []
    for a, b, r in (((-1.55, 0.0, -0.08), (-1.56, 0.0, 2.34), 0.042), ((1.5, 0.0, -0.08), (1.64, 0.06, 2.04), 0.04),
                    ((-1.74, -0.005, 2.24), (1.76, 0.065, 1.98), 0.036)):
        pts, rads = N.resample([Vector(a), Vector(b)], [r, r * 0.9], 0.2)
        v, f = N.tube(pts, rads, 10, bumps=0.05, seed=len(poles), tip=False)
        poles.append(mesh_from("pole", v, f))
        psegs.append((Vector(a), Vector(b)))
    # 말뚝 (밧줄 끝 둘 + 천 귀퉁이 넷)
    stakes = [((-1.88, 0.02, 0.0), (-1.8, 0.02, 0.24)), ((1.9, 0.08, 0.0), (1.82, 0.07, 0.22))]
    for sx in (-1, 1):
        for sy in (-1, 1):
            stakes.append(((sx * 1.62, sy * 1.46, -0.02), (sx * 1.6, sy * 1.42, 0.16)))
    W = []
    for a, b in stakes:
        W.append(timber(rng, a, b, 0.045, 0.04, ref=(1, 0, 0), rot=(0.0, 0.6), chips=(0, 1), name="stake"))
        psegs.append((Vector(a), Vector(b)))
    # 나무 상자 (안쪽 뒤)
    crate, csegs = [], []
    cx_, cy_ = 0.55, 0.48

    def CT(a, b, w, h, rot=(0, 0), name="plank"):
        crate.append(timber(rng, a, b, w, h, rot=rot, chips=(0, 1), name=name))
        csegs.append((Vector(a), Vector(b)))
    for k in range(3):
        z = 0.05 + 0.1 * k
        CT((cx_ - 0.24, cy_ - 0.2, z), (cx_ + 0.24, cy_ - 0.2, z), 0.02, 0.09)
        CT((cx_ - 0.24, cy_ + 0.2, z), (cx_ + 0.24, cy_ + 0.2, z), 0.02, 0.09)
        CT((cx_ - 0.25, cy_ - 0.19, z), (cx_ - 0.25, cy_ + 0.19, z), 0.02, 0.09)
        CT((cx_ + 0.25, cy_ - 0.19, z), (cx_ + 0.25, cy_ + 0.19, z), 0.02, 0.09)
    CT((cx_ - 0.24, cy_, 0.32), (cx_ + 0.22, cy_ + 0.03, 0.36), 0.4, 0.025, rot=(0, 0.5), name="lid")
    Mcr = Matrix.Translation((cx_, cy_, 0)) @ Matrix.Rotation(R(-14), 4, 'Z') @ Matrix.Translation((-cx_, -cy_, 0))
    for o_ in crate:
        place_xf(o_, Mcr)
    psegs += [(Mcr @ a, Mcr @ b) for a, b in csegs]
    W += crate
    wood = join(poles + W)
    low_w = lowpoly(wood)
    drop_faces(low_w, lambda c, n: c.z < -0.03)
    # 천: 판(펼친 좌표: X = 마룻대 방향 u, Z = 마룻대에서 땅까지 경사 s, 앞 −, 뒤 +) → 찢기 → 천막 모양으로 굽히기
    Ls = 2.62
    # k5 i1: 5.5 cm 격자를 6,000 삼각형으로 줄인 저폴리는 9 mm 두께 천의 앞뒷면이 어긋나 굽기 광선이 반대쪽 면을 맞혔다 (steep 14.5%)
    #        → 11 cm 격자를 줄이지 않고 저폴리로 쓰고, 원본은 그 사본을 SIMPLE 로 나눈 것 (모양이 같아 광선이 엇나가지 않는다)
    cloth = _sheet(-1.64, 1.64, -Ls, Ls, 0.11, 0.0, 0.009)
    cs = []

    def rag_poly(cx, cz, rx, rz, n=11, jit=0.3):
        return [(cx + math.cos(2 * math.pi * i / n) * rx * rng.uniform(1 - jit, 1 + jit * 0.6),
                 cz + math.sin(2 * math.pi * i / n) * rz * rng.uniform(1 - jit, 1 + jit * 0.6)) for i in range(n)]
    # 앞 경사면: 아랫단에서 마룻대 가까이까지 길게 찢어져 V 자로 벌어졌다 (안이 들여다보인다).
    # 첫 시안(가운데 둥근 큰 구멍 + 옆 작은 구멍 + 고른 톱니 아랫단)은 정면에서 눈·입·이가 있는 얼굴처럼 읽혀 바꿨다 — 둥근 구멍을 나란히 두지 않는다
    def jag_edge(a, b, n, amp):
        a, b = Vector((a[0], 0, a[1])), Vector((b[0], 0, b[1]))
        d = (b - a); nrm = Vector((-d.z, 0, d.x)).normalized()
        out = []
        for k in range(1, n):
            q = a.lerp(b, k / n) + nrm * rng.uniform(-amp, amp)
            out.append((q.x, q.z))
        return out
    apex = (0.08, -0.52)
    lb, rb = (-0.5, -Ls - 0.12), (0.78, -Ls - 0.12)
    tear = [apex] + jag_edge(apex, rb, 9, 0.045) + [rb, lb] + jag_edge(lb, apex, 9, 0.045)
    cs.append(G.obj_bm(G.bm_poly(tear, -0.3, 0.3), "tear"))
    # 아랫단: 들쭉날쭉한 단 + 너비·길이가 제각각인 찢긴 틈 몇 개 (고른 톱니는 이빨처럼 읽혔다)
    for side, gx_list in ((-1, (-1.35, -0.95, 1.05, 1.4)), (1, (-1.1, 0.2, 1.2))):
        hem = [(-1.75, side * (Ls + 0.2)), (1.75, side * (Ls + 0.2))]
        for k in range(14, -1, -1):
            u = -1.7 + 3.4 * k / 14
            hem.append((u, side * (Ls - rng.uniform(0.0, 0.14) - 0.06 * math.sin(2.3 * u + 1.0) ** 2)))
        cs.append(G.obj_bm(G.bm_poly(hem, -0.3, 0.3), "hem"))
        for gx in gx_list:
            L_ = rng.uniform(0.25, 0.6) if side < 0 else rng.uniform(0.15, 0.3)
            w0 = rng.uniform(0.05, 0.13)
            z0 = side * (Ls - L_)
            cs.append(G.obj_bm(G.bm_poly([(gx - 0.004, z0), (gx + 0.004, z0), (gx + w0 * rng.uniform(0.6, 1.2), side * (Ls + 0.2)),
                                          (gx - w0, side * (Ls + 0.2))], -0.3, 0.3), "gap"))
    # 뒤 경사면: 구멍 하나 + 비스듬히 갈라진 틈 하나 (둥근 구멍 둘을 나란히 두면 눈처럼 읽힌다)
    cs.append(G.obj_bm(G.bm_poly(rag_poly(0.85, 1.15, 0.22, 0.15, 9), -0.3, 0.3), "hole"))
    cs.append(G.obj_bm(G.bm_poly([(-0.72, 1.3), (-0.68, 1.3), (-0.48, 2.3), (-0.62, 2.32)], -0.3, 0.3), "slit"))
    cs.append(G.obj_bm(G.bm_poly([(1.1, -Ls - 0.1), (1.64, -Ls - 0.1), (1.7, -1.85), (1.38, -1.95), (1.2, -2.25)], -0.3, 0.3), "torn"))   # 뒤 장대 쪽 앞 아랫단이 뜯겼다
    cut(cloth, cs)

    def zr(u):
        t = (u + 1.74) / 3.5
        return 2.24 + (1.98 - 2.24) * t + 0.04

    def yr(u):
        return -0.005 + 0.07 * (u + 1.74) / 3.5

    def shape(p):
        u, s = p.x, p.z
        t = min(1.0, abs(s) / Ls)
        side = -1.0 if s < 0 else 1.0
        Wd = 1.4 + (0.06 if side > 0 else 0.0)
        y = yr(u) + side * t * Wd
        z = zr(u) * (1 - t) + 0.02 * t
        z -= 0.26 * math.sin(math.pi * t) * (0.6 + 0.4 * math.sin(math.pi * (u + 1.64) / 3.28))          # 천이 처져 오목하게
        z -= 0.12 * math.sin(math.pi * (u + 1.64) / 3.28) * (1 - t) * t * 4                                # 장대 사이 마룻줄이 처짐
        y += side * (0.05 * math.sin(8.0 * u + 0.7) + 0.025 * math.sin(11.0 * u + 2.0 * s)) * t ** 1.5       # 마룻대에서 아랫단으로 내려가는 세로 주름
        if side < 0 and t > 0.15:                                                                           # 찢긴 틈 양쪽 자락이 바깥으로 들려 늘어짐
            uc = 0.08 + (0.14 - 0.08) * (t - 0.2) / 0.8
            dd = abs(u - uc)
            if dd < 0.7:
                y -= 0.14 * (1 - dd / 0.7) ** 2 * (t - 0.15)
        if side < 0 and t > 0.72:                                                                           # 앞 아랫단 띠가 바깥으로 들려 늘어짐
            k = (t - 0.72) / 0.28
            y -= 0.12 * k * k
            z += 0.05 * k * k
        n = Vector((0, side * zr(u), Wd)).normalized()
        return Vector((u, y, z)) + n * p.y
    for vtx in cloth.data.vertices:
        vtx.co = shape(vtx.co)
    cloth.data.update()
    # 박공 천: 뒤(+X)는 삼각으로 막혔고(아래 귀퉁이 하나 뜯김), 앞(−X)은 한쪽 자락만 늘어졌다
    gables = []
    for xg, kind in ((1.66, 'back'), (-1.6, 'front')):
        g = _sheet(-1.42, 1.48, 0.0, 2.3, 0.11, 0.0, 0.009)
        zt_ = zr(xg) - 0.05
        tri = [(-1.6, -0.1), (yr(xg), zt_), (1.65, -0.1), (1.65, 2.5), (-1.6, 2.5)]
        cuts = [G.obj_bm(G.bm_poly([(-1.7, -0.2), (yr(xg) - 0.02, zt_ + 0.02), (yr(xg) - 0.02, 2.6), (-1.7, 2.6)], -0.3, 0.3), "c1"),
                G.obj_bm(G.bm_poly([(yr(xg) + 0.02, zt_ + 0.02), (1.7, -0.2), (1.7, 2.6), (yr(xg) + 0.02, 2.6)], -0.3, 0.3), "c2")]
        if kind == 'back':
            cuts.append(G.obj_bm(G.bm_poly([(0.75, -0.2), (1.6, -0.2), (1.6, 0.5), (1.1, 0.45)], -0.3, 0.3), "c3"))
            cuts.append(G.obj_bm(G.bm_poly(rag_poly(-0.35, 0.8, 0.14, 0.12, 8), -0.3, 0.3), "c4"))
        else:
            cuts.append(G.obj_bm(G.bm_poly([(-0.02, -0.2), (1.7, -0.2), (1.7, 2.6), (-0.02, 2.6)], -0.3, 0.3), "c3"))       # 뒤쪽 절반 없음 (열린 문)
            cuts.append(G.obj_bm(G.bm_poly([(-1.7, -0.2), (-0.2, -0.2), (-0.5, 0.75), (-1.7, 0.6)], -0.3, 0.3), "c4"))     # 아래가 찢겨 짧다
        cut(g, cuts)
        sgn = 1.0 if kind == 'back' else -1.0
        for vtx in g.data.vertices:
            yy, zz, dd = vtx.co.x, vtx.co.z, vtx.co.y
            bulge = 0.08 * math.sin(math.pi * min(1, zz / max(zt_, 0.1))) * (1 - abs(yy) / 1.5)
            if kind == 'front':
                bulge = 0.05 + 0.25 * (1 - zz / max(zt_, 0.1)) ** 2                                         # 늘어진 자락이 바깥으로 들림
            vtx.co = Vector((xg + sgn * (bulge + dd), yy, zz))
        g.data.update()
        gables.append(g)
    cloth = join([cloth] + gables)
    # 깔개 (말아 둔 천)
    roll = xf_all(cyl(0.12, 0.72, (-0.35, 0.55, 0.12), 14, rot=(0, R(90), R(8))))
    # 밧줄: 장대 끝 → 말뚝, 천 귀퉁이 → 말뚝
    rp = [([P0 + Vector((0, 0, -0.04)), Vector((-1.82, 0.02, 0.2))], False), ([P1 + Vector((0, 0, -0.03)), Vector((1.84, 0.07, 0.18))], False)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            c0 = shape(Vector((sx * 1.6, 0, sy * Ls * 0.97)))
            rp.append(([c0, Vector((sx * 1.6, sy * 1.43, 0.12))], False))
    rope_lo, rope_hi = rope_pair(rp, 0.011, lo_step=0.06)
    set_mat(rope_hi, rope_paint("tent_rope", 2.4))
    low_c = lowpoly(cloth)
    low_r = lowpoly(roll)
    # 원본
    wh = copy(wood)
    delete(wood)
    wood_carve(wh, psegs, 0.003, 93, WOOD_PLANK)
    set_mat(wh, wood_paint("tent_wood", 2.4, k=0.4, moss=0.25, rain=0.4, rain_h=0.6))
    ch = copy(cloth)
    delete(cloth)
    sub = ch.modifiers.new('sub', 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = 2
    apply_all(ch)
    surface(ch, [{'t': 'lumps', 'scale': 9.0, 'amp': 0.0015}, {'t': 'grain', 'scale': 160.0, 'amp': 0.0004}], 94)
    cm = paint3("tent_cloth", CANVAS, h=2.4, k=0.6, moss=0.15, moss_color=MOSS_DEAD, dirt=0.95, dirt_h=0.8, edge=0.3, edge_w=0.006,
                cavity=0.7, ao=0.05, streaks=0.5, stains=0.9, strokes=0.6, tooling=0.0, grain=0.7, hue_var=0.2, piece_var=0.0, contrast=0.22,
                gain=1.05, shadow=(0.06, 0.05, 0.05), light=0.6, speckle=0.35, rain=0.6, rain_h=1.6, rain_color=(0.18, 0.17, 0.15))
    G.blotch(cm, (0.12, 0.13, 0.1), 2.0, 0.6, 0.47, 0.63, mode='MIX')            # 곰팡이 얼룩
    G.blotch(cm, (0.09, 0.08, 0.07), 4.5, 0.4, 0.5, 0.62, mode='MIX')             # 잔 때 얼룩
    G.blotch(cm, (0.36, 0.33, 0.27), 1.2, 0.3, 0.52, 0.7, mode='MIX')              # 볕에 바랜 얼룩
    set_mat(ch, cm)
    rh = copy(roll)
    delete(roll)
    sub = rh.modifiers.new('sub', 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = 2   # (k5 i3) 둥글게 나누면 끝이 오그라들어 저폴리에서 3 cm 넘게 멀어졌다
    apply_all(rh)
    surface(rh, [{'t': 'lumps', 'scale': 9.0, 'amp': 0.004}, {'t': 'grain', 'scale': 120.0, 'amp': 0.0006}], 95)
    set_mat(rh, paint3("tent_roll", CLOTH_RED, h=0.3, k=0.3, moss=0.0, dirt=0.6, dirt_h=0.1, edge=0.3, cavity=0.9, ao=0.04, streaks=0.0,
                       stains=0.7, tooling=0.0, grain=0.7, piece_var=0.0, gain=1.1, shadow=(0.06, 0.03, 0.04)))
    cards = N.Cards()
    gr = random.Random(96)
    pts = [(x, y, 0.0) for x, y in ((-1.3, -0.4), (-0.6, 0.9), (0.2, -0.9), (1.2, 0.8), (1.45, -0.6), (-1.5, 1.1), (0.9, -1.2))]
    grass_at(cards, gr, pts, (0.22, 0.4), (0.16, 0.26), 0.5)
    print("LOW tent_torn", tri_count(low_w) + tri_count(low_c) + tri_count(rope_lo) + tri_count(low_r))
    # 천 안쪽 면(아래를 보는 경사면 안쪽, 박공 안쪽)은 텍셀을 덜 준다
    wt = lambda c, n: 0.4 if (n.z < -0.2 or (abs(c.x) > 1.5 and n.x * c.x < 0)) else 1.0
    lod0 = finish3("tent_torn", [wh, ch, rope_hi, rh], [low_w, low_c, rope_lo, low_r], extras=[cards.obj("grass")], cage=0.004,
                    cage_reach=0.02, uv_margin=0.002, uv_weight=wt, lod1=0.5)
    return repad_textures("tent_torn", lod0)          # 섬 바깥 여백을 섬 안쪽 값으로 다시 메운다 (가는 쇠살·판자 섬이 많아 밉맵에서 테두리가 번진다)



BUILDERS = [
    ("stone_wall_low", stone_wall_low),
    ("standing_stone", standing_stone),
    ("iron_fence", iron_fence),
    ("banner_torn", banner_torn),
    ("soul_crystal", soul_crystal),
    ("brazier", brazier),
    ("campfire", campfire),
    ("sarcophagus", sarcophagus),
    ("skeleton_remains", skeleton_remains),
    # 2차 7종 (k5)
    ("gallows", gallows),
    ("hanging_cage", hanging_cage),
    ("cart_broken", cart_broken),
    ("mausoleum_small", mausoleum_small),
    ("shrine_roadside", shrine_roadside),
    ("obelisk_chained", obelisk_chained),
    ("tent_torn", tent_torn),
]

# 월드 생성기 NEW_PROPS 와 같은 값 (tags 도 같다). light.far = LightCuller 가 이 소품 빛을 끄는 거리 (m)
META = {
    "stone_wall_low": {"kind": "prop", "tags": ["wall", "field"], "collider": "box", "footprint": 2.0, "sink": 0.1, "tilt": 2,
                       "align": False, "scale": [0.9, 1.15], "cull": 0.005, "shadows": True, "detail": "stone"},
    "standing_stone": {"kind": "prop", "tags": ["ritual", "stone"], "collider": "box", "footprint": 0.8, "sink": 0.3, "tilt": 6,
                       "align": False, "scale": [0.8, 1.3], "cull": 0.004, "shadows": True, "detail": "stone"},
    "iron_fence": {"kind": "prop", "tags": ["grave", "path"], "collider": "box", "footprint": 1.5, "sink": 0.05, "tilt": 3,
                   "align": False, "scale": [0.95, 1.05], "cull": 0.008, "shadows": True, "detail": "metal"},
    "banner_torn": {"kind": "prop", "tags": ["battle"], "collider": "capsule", "footprint": 0.5, "sink": 0.15, "tilt": 8,
                    "align": False, "scale": [0.85, 1.15], "cull": 0.004, "shadows": True, "detail": "wood"},
    "soul_crystal": {"kind": "prop", "tags": ["light", "crystal"], "collider": "mesh", "footprint": 0.9, "sink": 0.2, "tilt": 12,
                     "align": False, "scale": [0.7, 1.4], "cull": 0.005, "shadows": True, "detail": "stone",
                     "light": {"offset": [0.0, 0.0, 1.2], "color": SPIRIT, "intensity": 4, "range": 7, "far": FAR}},
    "brazier": {"kind": "prop", "tags": ["light", "path"], "collider": "capsule", "footprint": 0.6, "sink": 0.04, "tilt": 2,
                "align": False, "scale": [0.9, 1.1], "cull": 0.01, "shadows": True, "detail": "metal",
                "light": {"offset": [0.0, 0.0, 1.25], "color": SPIRIT, "intensity": 7, "range": 9, "far": FAR}},
    "campfire": {"kind": "prop", "tags": ["camp", "light"], "collider": "none", "footprint": 0.8, "sink": 0.03, "tilt": 2,
                 "align": True, "scale": [0.9, 1.1], "cull": 0.012, "shadows": True, "detail": "stone",
                 "light": {"offset": [0.0, 0.0, 0.5], "color": EMBER, "intensity": 3.5, "range": 7, "far": FAR}},
    "sarcophagus": {"kind": "prop", "tags": ["grave"], "collider": "box", "footprint": 1.3, "sink": 0.05, "tilt": 2,
                    "align": False, "scale": [0.95, 1.1], "cull": 0.008, "shadows": True, "detail": "stone"},
    "skeleton_remains": {"kind": "scatter", "tags": ["bone"], "collider": "none", "footprint": 0.9, "sink": 0.03, "tilt": 4,
                         "align": True, "scale": [0.9, 1.1], "cull": 0.02, "shadows": True, "detail": "bone"},
    # 2차 7종 (k5). 키 큰 실루엣(교수대·새장·오벨리스크)과 랜드마크(납골당)는 cull 을 작게 (멀리서도 보이게)
    "gallows": {"kind": "prop", "tags": ["ruin", "execution"], "collider": "mesh", "footprint": 1.9, "sink": 0.05, "tilt": 2,
                "align": False, "scale": [0.95, 1.1], "cull": 0.003, "shadows": True, "detail": "wood"},
    "hanging_cage": {"kind": "prop", "tags": ["execution", "light"], "collider": "capsule", "footprint": 0.9, "sink": 0.05, "tilt": 4,
                     "align": False, "scale": [0.9, 1.1], "cull": 0.004, "shadows": True, "detail": "metal",
                     "light": {"offset": [0.7, 0.0, 1.9], "color": SOUL, "intensity": 1.5, "range": 3}},
    "cart_broken": {"kind": "prop", "tags": ["camp"], "collider": "mesh", "footprint": 1.8, "sink": 0.08, "tilt": 6, "align": True,
                    "scale": [0.9, 1.1], "cull": 0.006, "shadows": True, "detail": "wood"},
    "mausoleum_small": {"kind": "landmark", "tags": ["grave", "landmark", "light"], "collider": "mesh", "footprint": 3.0, "sink": 0.06,
                        "tilt": 0, "align": False, "scale": [0.95, 1.05], "cull": 0.002, "shadows": True, "detail": "stone",
                        "light": {"offset": [0.0, -2.4, 1.6], "color": SOUL, "intensity": 3, "range": 5, "far": FAR}},
    "shrine_roadside": {"kind": "prop", "tags": ["grave", "path", "light"], "collider": "box", "footprint": 0.8, "sink": 0.04, "tilt": 3,
                        "align": False, "scale": [0.9, 1.1], "cull": 0.006, "shadows": True, "detail": "stone",
                        "light": {"offset": [0.0, -0.35, 1.2], "color": SOUL, "intensity": 2.5, "range": 5, "far": FAR}},
    "obelisk_chained": {"kind": "prop", "tags": ["ritual"], "collider": "box", "footprint": 1.0, "sink": 0.1, "tilt": 3,
                        "align": False, "scale": [0.9, 1.15], "cull": 0.003, "shadows": True, "detail": "stone"},
    "tent_torn": {"kind": "prop", "tags": ["camp"], "collider": "mesh", "footprint": 2.0, "sink": 0.05, "tilt": 4, "align": True,
                  "scale": [0.9, 1.1], "cull": 0.005, "shadows": True, "detail": "wood"},
}

SCENES1 = [n for n, _ in BUILDERS[:9]]
SCENES2 = [n for n, _ in BUILDERS[9:]]
PREVIEWS = [("all", SCENES1, False), ("all2", SCENES2, False)] + [(n, [n], True) for n, _ in BUILDERS]
