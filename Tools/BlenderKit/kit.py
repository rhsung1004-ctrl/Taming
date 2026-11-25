# 사령술사 3D 배경 소품 제작 공통 도구 (Blender 4.0, 배경 실행)
#
# 과정
#   1. 도형 조립 (box, cyl, sphere, prism ...)
#   2. 깎기: chip() — 모서리를 평평한 면으로 쳐낸다 (둥근 구멍이 아니라 정으로 친 자국)
#   3. 리메시: 한 덩어리로 합친다
#   4. 조각: surface() — 금, 판처럼 갈라진 면, 패인 자국, 결, 층리를 실제 형태로 새긴다 (지오메트리 노드)
#   5. 저폴리 복사본 → 고폴리의 색·굴곡을 텍스처로 굽는다 (finish)
#   6. FBX 내보내기: 이름_LOD0, 이름_LOD1 (Unity가 LOD 그룹을 자동으로 만든다)
#
# 재질 이름 규칙 (Unity 도구가 이름으로 머티리얼을 바꿔 끼운다)
#   Main        굽기 텍스처 (이름_albedo.jpg, 이름_normal.png)
#   Glow_Soul   보랏빛 영혼 발광      Glow_Spirit 창백한 청록 발광      Glow_Toxic 독기 어린 초록 발광      Glow_Ember 잿불
#   Foliage     잎·풀·덩굴·이끼·거미줄 (foliage_atlas.png, 정점 색 = 색, 정점 알파 = 바람에 흔들리는 정도)
import bpy, bmesh, math, random, os
from mathutils import Vector, Matrix, Euler

sc = None
OUT = None
LOWS = {}
R = math.radians

def init(out, samples=24):
    global sc, OUT
    OUT = out
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.threads_mode = 'AUTO'

# ───────────────────────── 기본 조작 ─────────────────────────
def act(o):
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o

def xf(o):
    act(o)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return o

def xf_all(o):
    act(o)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o

def origin0(o):
    """원점을 월드 (0,0,0)으로 (바닥 중심 = 0 이 되도록 모델링한다)"""
    act(o)
    sc.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    return o

def apply_all(o):
    act(o)
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o

def delete(o):
    if o is not None and o.name in bpy.data.objects:
        bpy.data.objects.remove(o, do_unlink=True)

def box(sx, sy, sz, loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = (sx, sy, sz)
    return xf(o)

def cyl(r, h, loc=(0, 0, 0), verts=24, r2=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r2 is None else r2, depth=h, location=loc, rotation=rot)
    return xf(bpy.context.object)

def sphere(r, loc=(0, 0, 0), scale=(1, 1, 1), sub=3, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=r, location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = scale
    return xf(o)

def torus(R_, r, loc=(0, 0, 0), rot=(0, 0, 0), seg=40, minor=10):
    bpy.ops.mesh.primitive_torus_add(major_radius=R_, minor_radius=r, major_segments=seg, minor_segments=minor, location=loc, rotation=rot)
    return xf(bpy.context.object)

def link(o):
    """새로 만든 객체를 장면에 넣는다 (kit.sc 는 init() 뒤에 생기므로 from kit import * 로 가져온 sc 를 쓰지 말 것)"""
    sc.collection.objects.link(o)
    return o

def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update(calc_edges=True)
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    return o

def prism(poly, y0, y1):
    """XZ 평면의 다각형을 Y 방향으로 늘인 기둥 (박공 지붕, 뾰족 아치 등)"""
    n = len(poly)
    verts = [(x, y0, z) for x, z in poly] + [(x, y1, z) for x, z in poly]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return mesh_from("prism", verts, faces)

def pointed_arch(w, h_spring, rise, steps=12):
    """뾰족 아치 윤곽 (XZ). 바닥 폭 w, 수직 부분 높이 h_spring, 그 위 뾰족 부분 높이 rise"""
    pts = [(-w / 2, 0), (w / 2, 0), (w / 2, h_spring)]
    r = (w * w / 4 + rise * rise) / w            # 두 원호의 반지름
    for i in range(1, steps):
        t = i / steps
        # 오른쪽 원호: 중심 (w/2 - r, h_spring)
        a = math.asin(min(1, rise / r)) * t
        pts.append((w / 2 - r + r * math.cos(a), h_spring + r * math.sin(a)))
    pts.append((0, h_spring + rise))
    for i in range(steps - 1, 0, -1):
        t = i / steps
        a = math.asin(min(1, rise / r)) * t
        pts.append((-(w / 2 - r + r * math.cos(a)), h_spring + r * math.sin(a)))
    pts.append((-w / 2, h_spring))
    return pts

def join(objs):
    objs = [o for o in objs if o is not None]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    return bpy.context.object

def copy(o):
    c = o.copy()
    c.data = o.data.copy()
    sc.collection.objects.link(c)
    return c

def _bool(a, cutters, op):
    col = bpy.data.collections.new("cutters")
    sc.collection.children.link(col)
    for c in cutters:
        for uc in list(c.users_collection):
            uc.objects.unlink(c)
        col.objects.link(c)
    m = a.modifiers.new('bool', 'BOOLEAN')
    m.operation = op
    m.operand_type = 'COLLECTION'
    m.collection = col
    m.solver = 'EXACT'
    act(a)
    bpy.ops.object.modifier_apply(modifier=m.name)
    for c in list(col.objects):
        bpy.data.objects.remove(c, do_unlink=True)
    bpy.data.collections.remove(col)
    return a

def cut(a, *cutters):
    """a 에서 cutters 를 파낸다"""
    flat = []
    for c in cutters:
        flat += list(c) if isinstance(c, (list, tuple)) else [c]
    return _bool(a, flat, 'DIFFERENCE')

def union(a, *others):
    flat = []
    for c in others:
        flat += list(c) if isinstance(c, (list, tuple)) else [c]
    return _bool(a, flat, 'UNION')

# ───────────────────────── 깎기: 평평한 면으로 쳐낸 자국 ─────────────────────────
def edge_points(o, n, rng, sharp_deg=30.0, zmin=-1e9, zmax=1e9):
    """날카로운 모서리 위의 무작위 점과 그 자리의 바깥 방향"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    bm.normal_update()
    cands, weights = [], []
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        ang = e.calc_face_angle(0.0)
        if ang < R(sharp_deg):
            continue
        out = (e.link_faces[0].normal + e.link_faces[1].normal).normalized()
        cands.append((e.verts[0].co.copy(), e.verts[1].co.copy(), out))
        weights.append(e.calc_length())
    bm.free()
    pts = []
    if not cands:
        return pts
    mw = o.matrix_world
    for _ in range(n * 4):
        if len(pts) >= n:
            break
        a, b, out = rng.choices(cands, weights)[0]
        p = mw @ a.lerp(b, rng.uniform(0.05, 0.95))
        if zmin <= p.z <= zmax:
            pts.append((p, (mw.to_3x3() @ out).normalized()))
    return pts

def chip(o, rng, n=12, size=(0.03, 0.09), sharp_deg=30.0, bite=0.45, zmin=-1e9, zmax=1e9):
    """모서리를 정으로 친 것처럼 평평한 면으로 쳐낸다. bite: 클수록 깊게."""
    cutters = []
    for p, out in edge_points(o, n, rng, sharp_deg, zmin, zmax):
        s = rng.uniform(*size)
        c = box(s * rng.uniform(0.8, 1.6), s * rng.uniform(0.8, 1.4), s * rng.uniform(0.6, 1.2),
                rot=(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)))
        c.location = p + out * (s * (0.55 - bite))
        cutters.append(c)
    if cutters:
        cut(o, cutters)
    return o

def slice_rock(o, rng, planes=14, depth=(0.05, 0.25)):
    """여러 각도의 평면으로 잘라 깎아낸 바위 덩어리 (볼록한 각진 형태)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    for _ in range(planes):
        nrm = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.6, 1))).normalized()
        # 이 방향으로 물체가 차지하는 두께 중 depth 비율만큼 바깥쪽을 잘라낸다
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

# ───────────────────────── 리메시와 조각 ─────────────────────────
def remesh(o, voxel):
    m = o.modifiers.new('remesh', 'REMESH')
    m.mode = 'VOXEL'
    m.voxel_size = voxel
    m.adaptivity = 0.0
    apply_all(o)
    return o

def _ng_link(ng, a, b):
    ng.links.new(a, b)

def surface(o, layers, seed=0, guide=None):
    """지오메트리 노드로 표면을 실제로 조각한다 (법선 방향으로 밀고 당김).
    layers: dict 목록
      {'t':'lumps',  'scale':1.5, 'amp':0.02}                         완만한 굴곡
      {'t':'plates', 'scale':4,   'amp':0.012, 'cover':0.6}            판처럼 들뜨고 갈라진 면 (칸마다 높이가 달라 날카로운 턱이 생김)
      {'t':'cracks', 'scale':3,   'width':0.03, 'depth':0.02, 'cover':0.55}  금 (가늘고 깊은 홈)
      {'t':'pits',   'scale':18,  'depth':0.006, 'cover':0.5}          잔 구멍
      {'t':'grain',  'scale':60,  'amp':0.0015}                        잔 결
      {'t':'strata', 'freq':6,    'amp':0.02, 'warp':0.4}              가로 층리 (절벽)
      {'t':'bark',   'scale':5,   'width':0.12, 'depth':0.025, 'stretch':0.12}   나무껍질 세로 균열 (guide 필요)
                     (v3b) 'ridge': 판 위 잔 물결 비율(기본 0.25, 크면 구겨진 천), 'plate': 판마다 높이 차, 'warp': 골 휘어짐
      {'t':'chisel', 'scale':9,   'amp':0.003, 'tilt':0.9, 'jitter':0.7}  (v3) 평면 끌 자국: 칸마다 기울기가 다른 평면으로 얕게 깎은 면
      terrace 에 'soft' (기본 0.35): 턱 위를 굴리는 정도. v3 는 0.08~0.12 로 또렷하게
      (v3b) 어느 층이든 'face': (x,y,z) 를 주면 그 방향을 향한 면에만 (face_lo~face_hi 로 부드럽게)
    guide: 나무 뼈대 메쉬 (각 점에 'dir' 속성 = 가지 방향). 껍질 결을 가지 방향으로 늘이는 데 쓴다."""
    ng = bpy.data.node_groups.new("surface", 'GeometryNodeTree')
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    N = ng.nodes
    gin = N.new('NodeGroupInput'); gout = N.new('NodeGroupOutput')
    pos = N.new('GeometryNodeInputPosition')
    nrm = N.new('GeometryNodeInputNormal')
    rnd = random.Random(seed)
    # 씨앗별로 좌표를 옮겨 같은 무늬가 반복되지 않게
    off = N.new('ShaderNodeVectorMath'); off.operation = 'ADD'
    off.inputs[1].default_value = (rnd.uniform(-50, 50), rnd.uniform(-50, 50), rnd.uniform(-50, 50))
    _ng_link(ng, pos.outputs[0], off.inputs[0])
    P = off.outputs[0]

    def math(op, a, b=None, c=None):
        m = N.new('ShaderNodeMath'); m.operation = op
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if hasattr(v, 'is_linked') or hasattr(v, 'links'):
                _ng_link(ng, v, m.inputs[i])
            else:
                m.inputs[i].default_value = v
        return m.outputs[0]

    def maprange(v, a, b, c, d, clamp=True):
        m = N.new('ShaderNodeMapRange'); m.clamp = clamp
        _ng_link(ng, v, m.inputs['Value'])
        m.inputs['From Min'].default_value = a; m.inputs['From Max'].default_value = b
        m.inputs['To Min'].default_value = c; m.inputs['To Max'].default_value = d
        return m.outputs['Result']

    def noise(vec, scale, detail=4.0, rough=0.5):
        t = N.new('ShaderNodeTexNoise')
        _ng_link(ng, vec, t.inputs['Vector'])
        t.inputs['Scale'].default_value = scale
        t.inputs['Detail'].default_value = detail
        t.inputs['Roughness'].default_value = rough
        return t.outputs['Fac']

    def voronoi(vec, scale, feature='F1', rand=1.0):
        t = N.new('ShaderNodeTexVoronoi'); t.feature = feature
        _ng_link(ng, vec, t.inputs['Vector'])
        t.inputs['Scale'].default_value = scale
        t.inputs['Randomness'].default_value = rand
        return t

    def warp(vec, scale, amt):
        t = N.new('ShaderNodeTexNoise')
        _ng_link(ng, vec, t.inputs['Vector'])
        t.inputs['Scale'].default_value = scale
        t.inputs['Detail'].default_value = 2.0
        sub = N.new('ShaderNodeVectorMath'); sub.operation = 'SUBTRACT'
        _ng_link(ng, t.outputs['Color'], sub.inputs[0]); sub.inputs[1].default_value = (0.5, 0.5, 0.5)
        sca = N.new('ShaderNodeVectorMath'); sca.operation = 'SCALE'
        _ng_link(ng, sub.outputs[0], sca.inputs[0]); sca.inputs['Scale'].default_value = amt
        add = N.new('ShaderNodeVectorMath'); add.operation = 'ADD'
        _ng_link(ng, vec, add.inputs[0]); _ng_link(ng, sca.outputs[0], add.inputs[1])
        return add.outputs[0]

    def cover(vec, amount, scale=1.2):
        """amount(0~1)만큼의 영역에만 효과가 나타나게 하는 가리개"""
        n = noise(vec, scale, 2.0)
        return maprange(n, 0.5 - (amount - 0.5) * 0.35 - 0.04, 0.5 - (amount - 0.5) * 0.35 + 0.04, 0.0, 1.0) if amount < 0.999 else None

    def masked(v, m):
        return v if m is None else math('MULTIPLY', v, m)

    # 껍질 결 방향: 뼈대에서 가장 가까운 점의 'dir'
    Pbark = None
    if guide is not None:
        oi = N.new('GeometryNodeObjectInfo'); oi.inputs['Object'].default_value = guide; oi.transform_space = 'RELATIVE'
        near = N.new('GeometryNodeSampleNearest'); near.domain = 'POINT'
        _ng_link(ng, oi.outputs['Geometry'], near.inputs['Geometry'])
        _ng_link(ng, pos.outputs[0], near.inputs['Sample Position'])
        na = N.new('GeometryNodeInputNamedAttribute'); na.data_type = 'FLOAT_VECTOR'; na.inputs['Name'].default_value = 'dir'
        si = N.new('GeometryNodeSampleIndex'); si.data_type = 'FLOAT_VECTOR'; si.domain = 'POINT'
        _ng_link(ng, oi.outputs['Geometry'], si.inputs['Geometry'])
        _ng_link(ng, na.outputs['Attribute'], si.inputs['Value'])
        _ng_link(ng, near.outputs['Index'], si.inputs['Index'])
        D = si.outputs['Value']
        Pbark = (D, P)

    total = None
    for L in layers:
        t = L['t']
        v = None
        if t == 'lumps':
            n = noise(P, L.get('scale', 1.5), L.get('detail', 3.0))
            v = maprange(n, 0.25, 0.75, -L['amp'], L['amp'], clamp=False)
        elif t == 'grain':
            n = noise(P, L.get('scale', 60), 2.0)
            v = maprange(n, 0.3, 0.7, -L['amp'], L['amp'])
        elif t == 'plates':
            vo = voronoi(warp(P, L['scale'] * 0.6, L.get('warp', 0.25) / L['scale']), L['scale'])   # v3: warp 0.05 안팎 = 곧은 경계(각진 판)
            sep = N.new('ShaderNodeSeparateXYZ'); _ng_link(ng, vo.outputs['Color'], sep.inputs[0])
            h = maprange(sep.outputs['X'], 0.0, 1.0, -L['amp'], L['amp'] * 0.35)
            v = masked(h, cover(P, L.get('cover', 0.6), L.get('cover_scale', 1.3)))
        elif t == 'terrace':
            # 잡음의 등고선을 따라 계단처럼 깨진 턱 (자연스럽게 겹겹이 떨어져 나간 돌)
            n = noise(warp(P, L['scale'] * 0.5, 0.2 / L['scale']), L['scale'], L.get('detail', 3.0), 0.55)
            st = L.get('steps', 5)
            q = math('DIVIDE', math('FLOOR', math('MULTIPLY', n, st)), st)
            # 턱 바로 위를 살짝 둥글게 (완전 수직이면 굽기에서 계단 현상). v3 는 'soft' 를 0.1 안팎으로 줄여 턱을 또렷하게
            fr = math('FRACT', math('MULTIPLY', n, st))
            soft = maprange(fr, 0.0, 0.25, -L.get('soft', 0.35) / st, 0.0)
            v = masked(maprange(math('ADD', q, soft), 0.2, 0.8, -L['amp'], L['amp']), cover(P, L.get('cover', 1.0), L.get('cover_scale', 1.2)))
        elif t == 'fissure':
            # 잡음 등고선 위의 가늘고 구불구불한 금 (그물 모양이 아니라 자연스러운 금)
            n = noise(warp(P, L['scale'] * 0.7, 0.25 / L['scale']), L['scale'], L.get('detail', 4.0), 0.6)
            line = math('ABSOLUTE', math('SUBTRACT', n, 0.5))
            d = maprange(line, 0.0, L['width'], -L['depth'], 0.0)
            v = masked(d, cover(P, L.get('cover', 0.6), L.get('cover_scale', 1.4)))
        elif t == 'chisel':
            # (v3) 평면 끌 자국: 칸(보로노이)마다 바닥이 평평하고 벽이 비스듬한 얕은 홈 (정으로 쳐낸 면).
            # 깊이 = 경계까지 거리(0 → 경계에서 0) × 칸마다 다른 깊이·기울기 → 경계에서 이어져(값이 튀지 않아) 복셀 계단이 생기지 않고,
            # 칸 안은 평면, 칸 사이는 또렷한 능선이 된다 (plates·terrace 처럼 값이 뚝 끊기는 층은 리메시 격자에 톱니가 생긴다)
            sc_ = L['scale']
            Wp = warp(P, sc_ * 0.5, L.get('warp', 0.08) / sc_)
            ve = voronoi(Wp, sc_, 'DISTANCE_TO_EDGE')
            vo = voronoi(Wp, sc_)
            loc = N.new('ShaderNodeVectorMath'); loc.operation = 'SUBTRACT'
            _ng_link(ng, Wp, loc.inputs[0]); _ng_link(ng, vo.outputs['Position'], loc.inputs[1])
            g = N.new('ShaderNodeVectorMath'); g.operation = 'SUBTRACT'
            _ng_link(ng, vo.outputs['Color'], g.inputs[0]); g.inputs[1].default_value = (0.5, 0.5, 0.5)
            dot = N.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
            _ng_link(ng, loc.outputs[0], dot.inputs[0]); _ng_link(ng, g.outputs[0], dot.inputs[1])
            sep = N.new('ShaderNodeSeparateXYZ'); _ng_link(ng, vo.outputs['Color'], sep.inputs[0])
            # 칸 바닥: 0.55~1 사이 깊이 + 칸 안 위치에 따른 기울기 (평면)
            lin = math('MULTIPLY', dot.outputs['Value'], sc_ * L.get('tilt', 0.9))
            base_ = math('ADD', math('MULTIPLY', sep.outputs['X'], L.get('jitter', 0.6)), 1.0 - L.get('jitter', 0.6))
            floor_ = maprange(math('ADD', base_, lin), 0.0, 1.4, 0.15, 1.0)
            # 벽: 경계에서 칸 반지름의 'wall' 비율까지 비스듬히
            wall = maprange(ve.outputs['Distance'], 0.0, L.get('wall', 0.12), 0.0, 1.0)     # 보로노이 거리는 칸 크기 단위 (0~0.5)
            v = masked(math('MULTIPLY', math('MULTIPLY', wall, floor_), -L['amp']), cover(P, L.get('cover', 1.0), L.get('cover_scale', 1.3)))
        elif t == 'cracks':
            vo = voronoi(warp(P, L['scale'] * 0.8, L.get('warp', 0.3) / L['scale']), L['scale'], 'DISTANCE_TO_EDGE')   # v3: warp 0.08 = 곧게 꺾인 금
            d = maprange(vo.outputs['Distance'], 0.0, L['width'], -L['depth'], 0.0)
            v = masked(d, cover(P, L.get('cover', 0.55), L.get('cover_scale', 1.6)))
        elif t == 'pits':
            vo = voronoi(P, L['scale'], 'F1')
            d = maprange(vo.outputs['Distance'], 0.0, 0.32, -L['depth'], 0.0)
            v = masked(d, cover(P, L.get('cover', 0.5), 2.5))
        elif t == 'strata':
            sep = N.new('ShaderNodeSeparateXYZ'); _ng_link(ng, warp(P, 0.7, L.get('warp', 0.4)), sep.inputs[0])
            z = math('MULTIPLY', sep.outputs['Z'], L['freq'])
            fr = math('FRACT', z)
            step = maprange(fr, 0.0, 0.12, -L['amp'], 0.0)        # 층마다 아래쪽이 움푹 들어간 턱
            jag = math('MULTIPLY', noise(P, L['freq'] * 1.7, 3.0), L['amp'] * 0.8)
            v = math('ADD', step, jag)
        elif t == 'bark':
            if Pbark is None:
                raise ValueError("bark 층은 guide(나무 뼈대)가 필요합니다")
            D, PP = Pbark
            # 결을 가지 방향으로 늘인다: q = p - d*(p·d)*(1-stretch)
            dot = N.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
            _ng_link(ng, PP, dot.inputs[0]); _ng_link(ng, D, dot.inputs[1])
            k = math('MULTIPLY', dot.outputs['Value'], 1.0 - L.get('stretch', 0.12))
            sc_ = N.new('ShaderNodeVectorMath'); sc_.operation = 'SCALE'
            _ng_link(ng, D, sc_.inputs[0]); _ng_link(ng, k, sc_.inputs['Scale'])
            sub = N.new('ShaderNodeVectorMath'); sub.operation = 'SUBTRACT'
            _ng_link(ng, PP, sub.inputs[0]); _ng_link(ng, sc_.outputs[0], sub.inputs[1])
            Q = warp(sub.outputs[0], L['scale'] * 0.5, L.get('warp', 0.15) / L['scale'])
            vo = voronoi(Q, L['scale'], 'DISTANCE_TO_EDGE')
            groove = maprange(vo.outputs['Distance'], 0.0, L['width'], -L['depth'], 0.0)
            rg = L.get('ridge', 0.25)
            ridges = maprange(noise(Q, L['scale'] * 3.0, 3.0), 0.3, 0.7, -L['depth'] * rg, L['depth'] * rg)
            v = math('ADD', groove, ridges)
            if L.get('plate', 0.0) > 0:
                # (v3b) 껍질판마다 높이가 다르다 (판 사이 턱). 골 바닥(경계)에서 0 이 되게 곱해 값이 끊기지 않는다
                vc = voronoi(Q, L['scale'])
                sepc = N.new('ShaderNodeSeparateXYZ'); _ng_link(ng, vc.outputs['Color'], sepc.inputs[0])
                ph = maprange(sepc.outputs['X'], 0.0, 1.0, -L['depth'] * L['plate'], L['depth'] * L['plate'] * 0.4)
                v = math('ADD', v, math('MULTIPLY', ph, maprange(vo.outputs['Distance'], 0.0, L['width'] * 1.5, 0.0, 1.0)))
        if v is None:
            continue
        if 'face' in L:
            # (v3b) 그 방향을 향한 면에만: 'face': (x,y,z), 'face_lo'/'face_hi': 법선·방향 내적이 lo→hi 에서 0→1
            # 예: 묘비 뒷면(+Y)만 거친 다듬 자국, 앞면은 매끈하게
            fd = N.new('ShaderNodeVectorMath'); fd.operation = 'DOT_PRODUCT'
            _ng_link(ng, nrm.outputs[0], fd.inputs[0]); fd.inputs[1].default_value = tuple(Vector(L['face']).normalized())
            v = math('MULTIPLY', v, maprange(fd.outputs['Value'], L.get('face_lo', 0.3), L.get('face_hi', 0.7), 0.0, 1.0))
        total = v if total is None else math('ADD', total, v)

    setp = N.new('GeometryNodeSetPosition')
    _ng_link(ng, gin.outputs[0], setp.inputs['Geometry'])
    if total is not None:
        sca = N.new('ShaderNodeVectorMath'); sca.operation = 'SCALE'
        _ng_link(ng, nrm.outputs[0], sca.inputs[0]); _ng_link(ng, total, sca.inputs['Scale'])
        _ng_link(ng, sca.outputs[0], setp.inputs['Offset'])
    _ng_link(ng, setp.outputs[0], gout.inputs[0])
    mod = o.modifiers.new('surface', 'NODES'); mod.node_group = ng
    apply_all(o)
    bpy.data.node_groups.remove(ng)
    for p in o.data.polygons:
        p.use_smooth = True
    return o

def sculpt(o, voxel, layers, seed=0):
    """리메시 + 조각을 한 번에"""
    origin0(o)
    remesh(o, voxel)
    return surface(o, layers, seed)

# 자주 쓰는 조각 묶음
def STONE_LAYERS(k=1.0, wear=1.0, cracks=0.5):
    """다듬은 돌 (묘비·기둥·벽). k: 물체 크기 배율 (1 = 사람 키 정도의 물체), wear: 풍화 정도"""
    return [
        {'t': 'lumps', 'scale': 1.4 / k, 'amp': 0.005 * k * wear},
        {'t': 'terrace', 'scale': 2.2 / k, 'steps': 4, 'amp': 0.006 * k * wear, 'cover': 0.55 * wear, 'cover_scale': 1.6 / k},
        {'t': 'terrace', 'scale': 6.0 / k, 'steps': 3, 'amp': 0.0025 * k * wear},
        {'t': 'fissure', 'scale': 1.6 / k, 'width': 0.012, 'depth': 0.01 * k, 'cover': cracks, 'cover_scale': 1.2 / k},
        {'t': 'fissure', 'scale': 4.5 / k, 'width': 0.01, 'depth': 0.004 * k, 'cover': cracks * 0.9},
        {'t': 'pits', 'scale': 26.0 / k, 'depth': 0.0025 * k * wear, 'cover': 0.6},
        {'t': 'grain', 'scale': 80.0 / k, 'amp': 0.0006 * k},
    ]

def ROCK_LAYERS(k=1.0, cracks=0.6):
    """자연석 (바위·절벽). 평면으로 깎은 형태(slice_rock) 위에 겹겹이 떨어져 나간 턱과 금"""
    return [
        {'t': 'lumps', 'scale': 0.8 / k, 'amp': 0.015 * k},
        {'t': 'terrace', 'scale': 1.1 / k, 'steps': 5, 'amp': 0.035 * k, 'cover': 0.8, 'cover_scale': 0.9 / k},
        {'t': 'terrace', 'scale': 3.5 / k, 'steps': 4, 'amp': 0.01 * k},
        {'t': 'fissure', 'scale': 0.9 / k, 'width': 0.014, 'depth': 0.03 * k, 'cover': cracks},
        {'t': 'fissure', 'scale': 3.0 / k, 'width': 0.012, 'depth': 0.008 * k, 'cover': cracks},
        {'t': 'pits', 'scale': 16.0 / k, 'depth': 0.005 * k, 'cover': 0.6},
        {'t': 'grain', 'scale': 50.0 / k, 'amp': 0.0012 * k},
    ]

def decimated(o, tris):
    c = copy(o)
    n = sum(len(p.vertices) - 2 for p in c.data.polygons)
    if n > tris:
        m = c.modifiers.new('dec', 'DECIMATE')
        m.ratio = tris / n
        m.use_collapse_triangulate = True
        apply_all(c)
    for p in c.data.polygons:
        p.use_smooth = True
    return c

def shade_auto(o, angle=40):
    for p in o.data.polygons:
        p.use_smooth = True
    try:
        o.data.use_auto_smooth = True
        o.data.auto_smooth_angle = R(angle)
    except AttributeError:
        pass

def tri_count(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)

# ───────────────────────── 굽기용 재질 (손으로 칠한 듯한 색) ─────────────────────────
def _ramp(nt, src, p0, c0, p1, c1, interp='LINEAR'):
    r = nt.nodes.new('ShaderNodeValToRGB')
    r.color_ramp.interpolation = interp
    e = r.color_ramp.elements
    e[0].position, e[0].color = p0, c0
    e[1].position, e[1].color = p1, c1
    nt.links.new(src, r.inputs['Fac'])
    return r.outputs['Color']

def _mix(nt, mode, fac, a, b):
    m = nt.nodes.new('ShaderNodeMixRGB')
    m.blend_type = mode
    for sock, v in ((m.inputs['Fac'], fac), (m.inputs['Color1'], a), (m.inputs['Color2'], b)):
        if hasattr(v, 'links'):
            nt.links.new(v, sock)
        else:
            sock.default_value = v
    return m.outputs['Color']

def _mul(nt, a, b, op='MULTIPLY'):
    m = nt.nodes.new('ShaderNodeMath')
    m.operation = op
    for sock, v in ((m.inputs[0], a), (m.inputs[1], b)):
        if hasattr(v, 'links'):
            nt.links.new(v, sock)
        else:
            sock.default_value = v
    return m.outputs[0]

def _noise(nt, vec, scale, detail=5.0, rough=0.55):
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = rough
    nt.links.new(vec, n.inputs['Vector'])
    return n.outputs['Fac']

def W(c):
    return (c[0], c[1], c[2], 1.0)

# 색 묶음: (어두운 색, 밝은 색, 닳은 모서리 색)
PAL = {
    'stone':      ((0.055, 0.058, 0.09), (0.25, 0.25, 0.34), (0.66, 0.68, 0.86)),
    'stone_pale': ((0.085, 0.085, 0.12), (0.36, 0.35, 0.44), (0.78, 0.78, 0.92)),
    'stone_warm': ((0.07, 0.06, 0.07), (0.3, 0.27, 0.29), (0.7, 0.66, 0.7)),
    'stone_dark': ((0.03, 0.03, 0.05), (0.13, 0.13, 0.19), (0.42, 0.43, 0.58)),
    'marble':     ((0.2, 0.2, 0.26), (0.62, 0.62, 0.7), (0.92, 0.92, 1.0)),
    'iron':       ((0.012, 0.012, 0.018), (0.055, 0.05, 0.065), (0.2, 0.2, 0.26)),
    'rust':       ((0.03, 0.015, 0.015), (0.16, 0.07, 0.05), (0.32, 0.2, 0.16)),
    'bark':       ((0.022, 0.017, 0.025), (0.1, 0.08, 0.09), (0.24, 0.2, 0.24)),
    'bark_pale':  ((0.05, 0.045, 0.055), (0.22, 0.2, 0.22), (0.45, 0.42, 0.46)),
    'wood':       ((0.03, 0.02, 0.02), (0.14, 0.09, 0.07), (0.32, 0.24, 0.2)),
    'bone':       ((0.2, 0.18, 0.15), (0.62, 0.58, 0.48), (0.9, 0.88, 0.8)),
    'earth':      ((0.025, 0.022, 0.03), (0.09, 0.075, 0.08), (0.18, 0.16, 0.17)),
    'cloth':      ((0.04, 0.02, 0.05), (0.16, 0.08, 0.18), (0.3, 0.2, 0.32)),
}
MOSS = (0.07, 0.13, 0.095)
MOSS_DEAD = (0.12, 0.12, 0.07)

def paint(name, pal='stone', moss=0.6, moss_color=MOSS, dirt=0.6, streaks=0.5, ao=0.35, edge=0.85, cavity=0.85,
          grain_bump=1.0, cracks=0.6, streak_dir='z', hue_var=0.5):
    """굽기 원본 재질. 색 → Base Color(굽기: DIFFUSE 색), 잔 굴곡 → Normal(굽기: NORMAL).
    pal: PAL 이름 또는 (어두운, 밝은, 모서리) 튜플"""
    dark, light, edgec = PAL[pal] if isinstance(pal, str) else pal
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 1.0
    tc = nt.nodes.new('ShaderNodeTexCoord')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    P = tc.outputs['Object']
    PS = P
    if streak_dir == 'grain':      # 나무: 세로로 길게 늘인 결
        mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (8, 8, 0.8)
        nt.links.new(P, mp.inputs['Vector']); PS = mp.outputs['Vector']
    # 바탕: 큰 얼룩 → 중간 얼룩 → 붓 자국
    col = _ramp(nt, _noise(nt, PS, 1.4, 8, 0.6), 0.28, W(dark), 0.74, W(light))
    if hue_var > 0:   # 차가운/따뜻한 쪽으로 살짝 갈리는 색
        col = _mix(nt, 'OVERLAY', 0.55 * hue_var, col, _ramp(nt, _noise(nt, P, 0.55, 2), 0.35, W((0.3, 0.36, 0.6)), 0.65, W((0.62, 0.5, 0.48))))
    vor = nt.nodes.new('ShaderNodeTexVoronoi'); vor.inputs['Scale'].default_value = 4.5
    nt.links.new(P, vor.inputs['Vector'])
    col = _mix(nt, 'OVERLAY', 0.45, col, _ramp(nt, vor.outputs['Distance'], 0.0, W((0.18, 0.18, 0.24)), 0.8, W((0.82, 0.8, 0.88))))
    fine = _noise(nt, PS, 32, 4)
    col = _mix(nt, 'OVERLAY', 0.4, col, _ramp(nt, fine, 0.3, W((0.25, 0.25, 0.25)), 0.7, W((0.75, 0.75, 0.75))))
    # 빗물 자국: 위에서 아래로 흘러내린 어두운 줄
    if streaks > 0:
        mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (14, 14, 0.6)
        nt.links.new(P, mp.inputs['Vector'])
        st = _ramp(nt, _noise(nt, mp.outputs['Vector'], 3.0, 3), 0.45, W((1, 1, 1)), 0.7, W((0.45, 0.42, 0.55)))
        col = _mix(nt, 'MULTIPLY', streaks, col, st)
    # 틈·구석: 깊은 보랏빛 그늘 (손으로 칠한 듯 진하게)
    aon = nt.nodes.new('ShaderNodeAmbientOcclusion'); aon.inputs['Distance'].default_value = ao; aon.samples = 12
    col = _mix(nt, 'MULTIPLY', cavity, col, _ramp(nt, aon.outputs['AO'], 0.15, W((0.16, 0.12, 0.26)), 0.88, W((1, 1, 1))))
    aon2 = nt.nodes.new('ShaderNodeAmbientOcclusion'); aon2.inputs['Distance'].default_value = ao * 0.12; aon2.samples = 8
    col = _mix(nt, 'MULTIPLY', cavity, col, _ramp(nt, aon2.outputs['AO'], 0.3, W((0.2, 0.16, 0.3)), 0.95, W((1, 1, 1))))
    # 닳아서 밝아진 모서리 (볼록한 곳)
    pt = geo.outputs['Pointiness']
    col = _mix(nt, 'MIX', _mul(nt, _ramp(nt, pt, 0.51, W((0, 0, 0)), 0.58, W((1, 1, 1))), edge), col, W(edgec))
    # 이끼: 윗면 + 틈에 고인 곳
    if moss > 0:
        sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(geo.outputs['Normal'], sep.inputs[0])
        up = _ramp(nt, sep.outputs['Z'], 0.35, W((0, 0, 0)), 0.85, W((1, 1, 1)))
        crev = _ramp(nt, aon.outputs['AO'], 0.35, W((1, 1, 1)), 0.7, W((0, 0, 0)))
        where = _mul(nt, _mul(nt, up, crev, 'MAXIMUM'), _ramp(nt, _noise(nt, P, 2.8, 6), 0.42, W((0, 0, 0)), 0.56, W((1, 1, 1))))
        mc = _ramp(nt, _noise(nt, P, 18, 4), 0.3, W(tuple(c * 0.55 for c in moss_color)), 0.72, W(tuple(c * 1.6 for c in moss_color)))
        col = _mix(nt, 'MIX', _mul(nt, where, moss), col, mc)
    # 땅에 닿는 아래쪽: 흙물
    if dirt > 0:
        sp = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Object'], sp.inputs[0])
        low = _ramp(nt, sp.outputs['Z'], 0.0, W((1, 1, 1)), 0.35, W((0, 0, 0)))
        lowm = _mul(nt, low, _ramp(nt, _noise(nt, P, 5, 3), 0.3, W((0.6, 0.6, 0.6)), 0.7, W((1, 1, 1))))
        col = _mix(nt, 'MIX', _mul(nt, lowm, dirt), col, W((0.035, 0.03, 0.045)))
    nt.links.new(col, bsdf.inputs['Base Color'])
    # 잔 굴곡 (노멀에 함께 굽힌다)
    hgt = _mul(nt, _noise(nt, PS, 90, 3), 0.6)
    if cracks > 0:
        cn = _noise(nt, P, 5.0, 5, 0.6)
        ln = _ramp(nt, _mul(nt, _mul(nt, cn, 0.5, 'SUBTRACT'), 0.0, 'ABSOLUTE'), 0.0, W((0, 0, 0)), 0.012, W((1, 1, 1)))
        msk = _ramp(nt, _noise(nt, P, 2.2, 2), 0.5, W((1, 1, 1)), 0.56, W((0, 0, 0)))
        crack_h = _mul(nt, _mul(nt, _mul(nt, 1.0, ln, 'SUBTRACT'), msk), cracks)
        hgt = _mul(nt, hgt, crack_h, 'SUBTRACT')
        col2 = _mix(nt, 'MIX', _mul(nt, crack_h, 0.9), col, W((0.02, 0.015, 0.035)))
        nt.links.new(col2, bsdf.inputs['Base Color'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.6 * grain_bump
    bump.inputs['Distance'].default_value = 0.004
    nt.links.new(hgt, bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return m

def set_mat(o, m):
    o.data.materials.clear()
    o.data.materials.append(m)
    return o

# ───────────────────────── 발광·잎 재질 ─────────────────────────
GLOW = {
    'Glow_Soul':   ((0.55, 0.28, 1.0), 9.0),
    'Glow_Spirit': ((0.45, 0.85, 1.0), 7.0),
    'Glow_Toxic':  ((0.45, 1.0, 0.35), 7.0),
    'Glow_Ember':  ((1.0, 0.42, 0.12), 8.0),
}

def glow(o, name='Glow_Soul'):
    """발광 부품: 재질을 입히고 UV를 맞춰 둔다 (합칠 때 UV가 어긋나지 않게)"""
    set_uv(o, lambda fi, k, co: (0.5, 0.5))
    return set_mat(o, glow_mat(name))

def glow_mat(name='Glow_Soul'):
    m = bpy.data.materials.get(name)
    if m:
        return m
    c, s = GLOW[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*c, 1)
    b.inputs["Emission Color"].default_value = (*c, 1)
    b.inputs["Emission Strength"].default_value = s
    return m

# 잎 아틀라스 (4x4 칸, 칸마다 256px). 회색조 + 알파. 색은 정점 색으로 입힌다.
ATLAS = {
    'solid': (0, 0), 'ivy_a': (1, 0), 'ivy_b': (2, 0), 'leaf_dead': (3, 0),
    'fern': (0, 1), 'grass_card': (1, 1), 'moss_hang': (2, 1), 'petal': (3, 1),
    'web': (0, 2), 'cloth': (1, 2), 'thorn_leaf': (2, 2), 'stem': (3, 2),
    'lily': (0, 3), 'mushroom_gill': (1, 3), 'reed': (2, 3), 'web_corner': (3, 3),
}

def atlas_uv(cell, u, v, pad=0.02):
    """칸 안의 (u,v) 0~1 → 아틀라스 UV"""
    cx, cy = ATLAS[cell]
    s = 0.25
    return (cx * s + s * (pad + u * (1 - 2 * pad)), cy * s + s * (pad + v * (1 - 2 * pad)))

def foliage_mat():
    m = bpy.data.materials.get("Foliage")
    if m:
        return m
    m = bpy.data.materials.new("Foliage")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.8
    path = os.path.join(OUT, "foliage_atlas.png")
    if os.path.exists(path):
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(path, check_existing=True)
        vc = nt.nodes.new('ShaderNodeVertexColor'); vc.layer_name = "Col"
        mul = nt.nodes.new('ShaderNodeMixRGB'); mul.blend_type = 'MULTIPLY'; mul.inputs['Fac'].default_value = 1
        nt.links.new(t.outputs['Color'], mul.inputs['Color1']); nt.links.new(vc.outputs['Color'], mul.inputs['Color2'])
        nt.links.new(mul.outputs['Color'], b.inputs['Base Color'])
        nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
        m.blend_method = 'CLIP'
        m.shadow_method = 'CLIP'
        m.alpha_threshold = 0.5
    m.use_backface_culling = False
    return m

def vcolor(o, fn):
    """정점 색 칠하기. fn(위치, 법선, 정점 인덱스) → (r,g,b,a). a = 바람에 흔들리는 정도 (0 뿌리 ~ 1 끝)"""
    me = o.data
    if "Col" not in me.color_attributes:
        me.color_attributes.new("Col", 'BYTE_COLOR', 'CORNER')
    attr = me.color_attributes["Col"]
    vcache = {}
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            if vi not in vcache:
                v = me.vertices[vi]
                vcache[vi] = fn(o.matrix_world @ v.co, v.normal, vi)
            attr.data[li].color = vcache[vi]
    return o

def set_uv(o, fn, name="UVMap"):
    """UV 직접 지정: fn(면 인덱스, 면 안의 꼭짓점 순번, 정점 위치) → (u, v)"""
    me = o.data
    if not me.uv_layers:
        me.uv_layers.new(name=name)
    # 합칠 때 UV가 이름으로 맞춰지므로 항상 "UVMap" 하나만 쓴다
    me.uv_layers.active.name = name
    while len(me.uv_layers) > 1:
        other = next(l for l in me.uv_layers if l.name != name)
        me.uv_layers.remove(other)
    uv = me.uv_layers.active.data
    for poly in me.polygons:
        for k, li in enumerate(poly.loop_indices):
            uv[li].uv = fn(poly.index, k, me.vertices[me.loops[li].vertex_index].co)
    return o

def card_uv(cell, flip=False):
    """사각 카드 면(꼭짓점 순서 0-1-2-3 = 왼아래·오른아래·오른위·왼위)에 아틀라스 칸을 붙인다"""
    corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
    def fn(fi, k, co):
        u, v = corners[k % 4]
        if flip:
            u = 1 - u
        return atlas_uv(cell, u, v)
    return fn

# ───────────────────────── 덩굴 (IvyGen) ─────────────────────────
def ivy(target, start, seed=0, length=1.2, size=0.02, leaf=0.05, leaf_prob=0.35, branch=0.05, gravity=1.0,
        adhesion=0.1, float_len=0.5, adhesion_dist=1.0, stem_radius=0.006, color=(0.2, 0.32, 0.24), dead=0.25):
    """target 표면을 따라 start에서 덩굴이 자란다. 줄기 메쉬와 잎 메쉬를 Foliage 재질로 돌려준다."""
    import sys
    sys.path.append(bpy.utils.user_resource('SCRIPTS') or "")
    import add_curve_ivygen as ig
    ig.rand_seed(seed)
    act(target)
    bvh = ig.bvhtree_from_object(target)
    IVY = ig.Ivy(primaryWeight=0.5, randomWeight=0.2, gravityWeight=gravity, adhesionWeight=adhesion,
                 branchingProbability=branch, leafProbability=leaf_prob, ivySize=size, ivyLeafSize=leaf,
                 ivyBranchSize=0.001, maxFloatLength=float_len, maxAdhesionDistance=adhesion_dist)
    IVY.seed(Vector(start))
    guard = 0
    while any(r.alive for r in IVY.ivyRoots) and IVY.maxLength < length and guard < 4000:
        IVY.grow(target, bvh)
        guard += 1
    before = set(bpy.data.objects.keys())
    ig.createIvyGeometry(IVY, True)
    new = [bpy.data.objects[k] for k in set(bpy.data.objects.keys()) - before]
    curve = next((o for o in new if o.type == 'CURVE'), None)
    leaves = next((o for o in new if o.type == 'MESH'), None)
    parts = []
    rng = random.Random(seed)
    fm = foliage_mat()
    if curve is not None:
        curve.data.bevel_depth = stem_radius
        curve.data.bevel_resolution = 1
        curve.data.resolution_u = 2
        act(curve)
        bpy.ops.object.convert(target='MESH')
        stem = bpy.context.object
        set_uv(stem, lambda fi, k, co: atlas_uv('stem', 0.5, 0.5))
        vcolor(stem, lambda p, n, i: (color[0] * 0.55, color[1] * 0.45, color[2] * 0.45, 0.05))
        set_mat(stem, fm)
        parts.append(stem)
    if leaves is not None and len(leaves.data.polygons):
        cells = ['ivy_a', 'ivy_b', 'ivy_a', 'leaf_dead']
        pick = {}
        def leaf_uv(fi, k, co):
            if fi not in pick:
                pick[fi] = cells[3] if rng.random() < dead * 0.5 else cells[rng.randrange(3)]
            u, v = [(0, 0), (1, 0), (1, 1), (0, 1)][k % 4]
            return atlas_uv(pick[fi], u, v)
        set_uv(leaves, leaf_uv)
        tint = {}
        def leaf_col(p, n, i):
            f = i // 4
            if f not in tint:
                d = rng.random() < dead
                base = (0.45, 0.4, 0.22) if d else color
                j = rng.uniform(0.75, 1.2)
                tint[f] = (min(1, base[0] * j), min(1, base[1] * j), min(1, base[2] * j), 0.25)
            return tint[f]
        vcolor(leaves, leaf_col)
        set_mat(leaves, fm)
        parts.append(leaves)
    return parts

# ───────────────────────── 굽기와 내보내기 ─────────────────────────
def _bake(low, highs, img, kind, extr, cage=None, margin=16, margin_type='EXTEND', use_clear=True):
    """cage: 굽기 우리 객체 (make_cage). 있으면 extr 대신 우리에서 저폴리 쪽으로 광선을 쏜다"""
    bpy.ops.object.select_all(action='DESELECT')
    for h in highs:
        h.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    kw = dict(use_selected_to_active=True, max_ray_distance=0.0, margin=margin, margin_type=margin_type, use_clear=use_clear)
    if cage is not None:
        kw.update(use_cage=True, cage_object=cage.name)
    else:
        kw.update(cage_extrusion=extr)
    if kind == 'DIFFUSE':
        bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, **kw)
    else:
        bpy.ops.object.bake(type=kind, **kw)

def _save_jpg(img, path, quality=92):
    """굽힌 색을 그대로(sRGB) 저장한다. save_render 는 장면의 보기 변환(4.0 기본 AgX, 미리보기 뒤에는 Filmic)을
    입혀 색이 바래고 어두워지므로 저장하는 동안만 Standard 로 바꾼다 (v3 에서 고침: 예전 albedo 는 AgX 가 입혀져 있었다)"""
    scn = bpy.context.scene
    s = scn.render.image_settings
    vs = scn.view_settings
    old = (vs.view_transform, vs.look, vs.exposure, vs.gamma)
    vs.view_transform = 'Standard'; vs.look = 'None'; vs.exposure = 0.0; vs.gamma = 1.0
    s.file_format = 'JPEG'; s.quality = quality; s.color_mode = 'RGB'
    try:
        img.save_render(path)
    finally:
        vs.view_transform, vs.look, vs.exposure, vs.gamma = old

def png_max(path):
    """PNG 를 무손실 최대 압축으로 다시 저장한다 (PIL optimize + compress_level 9. Blender 기본 압축보다 15~20% 작다).
    저장소 용량 규칙(LFS 1 GB) 때문에 노멀맵은 이걸 거친다. PIL 이 없으면 그대로 둔다"""
    try:
        from PIL import Image
    except ImportError:
        return os.path.getsize(path)
    im = Image.open(path)
    im.load()
    if im.mode not in ('RGB', 'RGBA', 'L'):
        im = im.convert('RGB')
    im.save(path, optimize=True, compress_level=9)
    return os.path.getsize(path)

def save_png(img, path):
    """굽힌 Non-Color 그림(노멀맵)을 PNG 로 저장하고 최대 압축한다"""
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    return png_max(path)

def tex_size(dims, size='auto'):
    """텍스처 크기 규칙 (저장소 용량): 가장 긴 변 1.5 m 미만 1024, 그 밖 2048. 4096 은 쓰지 않는다 (2048 로 낮추고 WARN)"""
    if size in (None, 'auto'):
        return 1024 if max(dims) < 1.5 else 2048
    if size > 2048:
        print("WARN tex", size, "→ 2048 (4096 금지: 저장소 용량 규칙)")
        return 2048
    return size

SENTINEL = (1.0, 0.0, 1.0)      # 굽기 전에 albedo 를 이 색(자홍)으로 채워 두면, 굽힌 뒤 남은 자홍 = UV 밖, 검정 = 광선이 빗나간 곳

def _pushpull(rgb, valid):
    """빈 화소를 둘레 색으로 메운다 (밉맵 피라미드로 내려가며 평균 → 올라오며 빈 곳만 채움)"""
    import numpy as np
    levels = []
    c = np.where(valid[..., None], rgb, 0.0).astype(np.float32)
    w = valid.astype(np.float32)
    while min(c.shape[:2]) > 1:
        levels.append((c, w))
        h2, w2 = c.shape[0] // 2, c.shape[1] // 2
        c = c[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2, 3).sum(axis=(1, 3))
        w = w[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2).sum(axis=(1, 3))
    cur = c / np.maximum(w[..., None], 1e-8)
    for cl, wl in reversed(levels):
        up = np.repeat(np.repeat(cur, 2, axis=0), 2, axis=1)[:cl.shape[0], :cl.shape[1]]
        cur = np.where((wl > 0)[..., None], cl / np.maximum(wl[..., None], 1e-8), up)
    return cur

def _grow_fill(rgb, valid, iters):
    """(v3b) 섬마다 자기 가장자리 색을 바깥으로 한 화소씩 넓힌다 (8 이웃 평균). 두 섬 사이 틈은 가운데서 만난다.
    pushpull 만 쓰면 거친 단계에서 이웃 섬(다른 방향으로 놓인 섬의 노멀)이 섞여 이음매에 흰 보풀·검은 점이 생긴다"""
    import numpy as np
    c = np.where(valid[..., None], rgb, 0.0).astype(np.float32)
    v = valid.copy()
    for _ in range(iters):
        if v.all():
            break
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
        c[new] = cs[new] / ws[new][:, None]
        v = v | new
    return c, v

def fill_holes(img, misses=True, grow=None):
    """굽힌 그림의 빈 곳을 메운다: 여백 밖(자홍 또는 검정) + [misses] 광선이 빗나가 검게 남은 화소. 빗나간 비율을 돌려준다.
    (v3b) 먼저 섬마다 grow 화소(기본 그림 크기/256)만큼 자기 색으로 넓히고, 나머지 빈 곳만 pushpull 로 메운다"""
    import numpy as np
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    rgb = a[..., :3]
    sent = (rgb[..., 0] > 0.995) & (rgb[..., 1] < 0.005) & (rgb[..., 2] > 0.995)
    miss = (rgb.max(axis=2) <= 0.0) & ~sent
    if not misses:
        miss[:] = False
    cov = int((~sent).sum())
    valid = ~(sent | miss)
    if valid.any() and not valid.all():
        n = grow if grow is not None else max(4, w // 256)
        grown, gv = _grow_fill(rgb, valid, n)
        rgb[gv] = grown[gv]
        if not gv.all():
            filled = _pushpull(rgb, gv)
            rgb[~gv] = filled[~gv]
        a[..., :3] = rgb
        img.pixels.foreach_set(a.ravel())
    return float(miss.sum()) / max(1, cov)

def despeckle(img, thr=0.08):
    """(v3b) 굽힌 albedo 의 외딴 점(둘레 3x3 의 중앙값과 밝기가 thr 넘게 다른 화소)을 중앙값 이웃 색으로 바꾼다.
    paint3 의 AO 는 표본이 적어, 깊은 틈 바로 옆 입술(반쯤 가려진 곳)에서 밝은 모서리 띠 위에 검은 점(소금·후추)이 생긴다.
    중앙값이라 모서리·글자 경계는 그대로 남는다. 바꾼 비율을 돌려준다"""
    import numpy as np
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    rgb = a[..., :3]
    L = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    P = np.pad(L, 1, mode='edge')
    offs = [(dy, dx) for dy in (0, 1, 2) for dx in (0, 1, 2)]
    st = np.stack([P[dy:dy + h, dx:dx + w] for dy, dx in offs])
    med = np.partition(st, 4, axis=0)[4]
    bad = np.abs(L - med) > thr
    n = int(bad.sum())
    if n:
        k = np.abs(st[:, bad] - med[bad]).argmin(axis=0)          # 밝기가 중앙값인 이웃
        ys, xs = np.nonzero(bad)
        dy = np.array([o[0] for o in offs])[k] - 1
        dx = np.array([o[1] for o in offs])[k] - 1
        rgb[ys, xs] = rgb[np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)]
        a[..., :3] = rgb
        img.pixels.foreach_set(a.ravel())
    return n / float(w * h)

RIM_PX = 4          # UV 섬 경계에서 몇 화소까지를 '테두리'로 볼지
RIM_Z = 0.6         # 테두리에서 이보다 누운 법선(z<0.6, 약 53도)은 비스듬히 스친 광선 흔적 = 흰 보풀·검은 톱니 테두리
WARN_STEEP = 2.0    # steep(%) 이 넘으면 WARN
WARN_RIM = 5.0      # rim_soft(%) 가 이보다 크고 섬 안쪽(inner) 의 1.5 배보다도 크면 WARN
                    # (v3 시범 rim: 벽 0.6, 묘비 6.3, 바위 26 — 바위의 흰·검은 테두리. v3b: 벽 0.2, 묘비 0, 바위 1.9)

def _sharp_uv_segments(o):
    """단단한(sharp) 모서리의 UV 선분들 (섬 경계 띠에서 빼려고). 양쪽 면의 UV 를 모두 넣는다"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    uvl = bm.loops.layers.uv.active
    segs = []
    for e in bm.edges:
        if e.smooth or len(e.link_loops) != 2:
            continue
        for l in e.link_loops:
            a, b = l[uvl].uv, l.link_loop_next[uvl].uv
            segs.append((a.x, a.y, b.x, b.y))
    bm.free()
    return segs

def normal_stats(img, hard_segs=None):
    """굽은 직후(자홍으로 채워 둔 노멀맵, 메우기 전) 법선 통계: (rim, rim_soft, steep, 덮인 비율, inner).
    rim  = UV 섬 경계 RIM_PX 화소 띠 안에서 z < RIM_Z 인 비율 — 'miss 0%' 가 못 잡는, 비스듬히 스친 광선의 테두리 결함
           (폭이 16 화소도 안 되는 잔 섬은 뺀다: 잔가지 관처럼 섬 전체가 띠라 비율만 부풀린다)
    rim_soft = 그 가운데 단단한 모서리(hard_segs) 둘레를 뺀 것. 단단한 모서리에서는 원본의 둥근 모서리가 띠 안에서
    눕는 것이 정상(모서리 빛)이라 rim 을 부풀린다 → WARN 은 rim_soft 로 판단한다
    steep = 덮인 화소 가운데 z < 0.35 (70도 넘게 누운 것, clamp_normals 가 세운다) 비율
    inner = 테두리 띠 밖(섬 안쪽)의 z < RIM_Z 비율 — 깊은 껍질 골처럼 원래 누운 면이 많으면 rim 도 그만큼 높다 (WARN 은 둘을 견준다)"""
    import numpy as np
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    rgb = a[..., :3]
    sent = (rgb[..., 0] > 0.995) & (rgb[..., 1] < 0.005) & (rgb[..., 2] > 0.995)
    cov = ~sent
    if not cov.any():
        return 0.0, 0.0, 0.0, 0.0, 0.0
    def grow(m, n):
        for _ in range(n):
            e = m.copy()
            e[1:] |= m[:-1]; e[:-1] |= m[1:]; e[:, 1:] |= m[:, :-1]; e[:, :-1] |= m[:, 1:]
            m = e
        return m
    d = grow(sent, RIM_PX)
    # 폭이 4 RIM_PX 보다 좁은 섬(잔가지 관·작은 조각)은 통째로 '테두리'라 비율을 부풀린다 → 속이 있는 섬의 테두리만 센다
    inner = ~grow(sent, 2 * RIM_PX)
    rim = cov & d & grow(inner, 2 * RIM_PX + 1)
    nz = rgb[..., 2] * 2.0 - 1.0
    r = float((nz[rim] < RIM_Z).mean()) if rim.any() else 0.0
    rs = r
    if hard_segs:
        try:
            from PIL import Image, ImageDraw
            ex = Image.new('L', (w, h), 0)
            dr = ImageDraw.Draw(ex)
            for x0, y0, x1, y1 in hard_segs:      # 그림 배열의 줄 = v*h (Blender 는 아래에서 위로)
                dr.line([(x0 * w, y0 * h), (x1 * w, y1 * h)], fill=255, width=2 * RIM_PX + 3)
            soft = rim & ~(np.asarray(ex) > 0)
            rs = float((nz[soft] < RIM_Z).mean()) if soft.any() else 0.0
        except ImportError:
            pass
    s = float((nz[cov] < 0.35).mean())
    # 테두리 밖(섬 안쪽) 같은 비율: 껍질 골처럼 원래 누운 면이 많은 소품은 rim 이 높아도 결함이 아니다 → 안쪽과 견준다
    core = cov & ~d
    ins = float((nz[core] < RIM_Z).mean()) if core.any() else 0.0
    return r, rs, s, float(cov.mean()), ins

def clamp_normals(img, zmin=0.35):
    """굽힌 노멀맵에서 너무 누운 법선(z < zmin, 약 70도 넘게 꺾인 것)을 zmin 까지 세운다.
    깊은 골의 벽·부품이 겹친 곳에서 생기는 극단 법선은 빛 반대쪽에서 검은 점으로 보인다. 돌려주는 값: 고친 비율"""
    import numpy as np
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    n = a[..., :3] * 2.0 - 1.0
    bad = n[..., 2] < zmin
    if bad.any():
        xy = n[..., :2]
        ln = np.sqrt((xy ** 2).sum(axis=2)) + 1e-8
        k = np.sqrt(1.0 - zmin * zmin) / ln
        n[..., 0] = np.where(bad, xy[..., 0] * k, n[..., 0])
        n[..., 1] = np.where(bad, xy[..., 1] * k, n[..., 1])
        n[..., 2] = np.where(bad, zmin, n[..., 2])
        a[..., :3] = n * 0.5 + 0.5
        img.pixels.foreach_set(a.ravel())
    return float(bad.mean())

def make_cage(low, highs, push=0.006, reach=0.2):
    """굽기 우리(cage): 저폴리 사본을 정점 법선(평균) 방향으로 '그 자리 원본 표면 바로 바깥'까지 부풀린 것.
    정점과 둘레 면 가운데에서 법선 방향으로 광선을 쏴, 원본이 저폴리보다 바깥으로 나와 있으면 그 거리 + push, 아니면 push.
    → 광선이 늘 원본 바깥에서 출발해 맞는 면에 닿는다 (extr 하나로 정할 때 생기던 검은 얼룩·줄 방지).
    push: 남는 여유 (작은 소품 0.004~0.006, 바위·큰 것 0.01~0.02), reach: 원본이 저폴리보다 튀어나올 수 있는 최대 거리"""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    trees = []
    for h in highs:
        mw = h.matrix_world
        trees.append((BVHTree.FromObject(h, dg), mw.inverted(), mw.to_3x3().inverted()))
    cage = copy(low)
    cage.name = low.name + "_cage"
    me = cage.data
    lmw = low.matrix_world
    l3 = lmw.to_3x3()

    def out_dist(p, n):
        best = 0.0
        for t, inv, inv3 in trees:
            lp = inv @ p
            ln = (inv3 @ n).normalized()
            hit, hn, idx, d = t.ray_cast(lp, ln, reach)
            if hit is not None and hn.dot(ln) > 0.0:       # 원본 안에서 바깥으로 나가는 면 = 원본이 바깥에 있다
                best = max(best, d)
        return best
    dv = [out_dist(lmw @ v.co, (l3 @ v.normal).normalized()) for v in me.vertices]
    for p in me.polygons:                                 # 면 가운데가 더 튀어나온 곳 (정점 사이 잔 조각)
        d = out_dist(lmw @ p.center, (l3 @ p.normal).normalized())
        for vi in p.vertices:
            if d > dv[vi]:
                dv[vi] = d
    for v, d in zip(me.vertices, dv):
        v.co = v.co + v.normal * (d + push)
    me.update()
    _ray_off(cage)
    cage.hide_render = False
    print("CAGE", low.name, "push", push, "max", round(max(dv) + push, 4) if dv else 0)
    return cage

def _ray_off(o, off=True):
    """광선에 안 보이게 (굽기 중 AO 가 저폴리·우리에 가려 검게 되는 것 방지)"""
    for a in ('visible_camera', 'visible_diffuse', 'visible_glossy', 'visible_transmission', 'visible_volume_scatter', 'visible_shadow'):
        setattr(o, a, not off)

def uv_stats(o, size, zmax=None):
    """(텍셀 밀도 px/m, UV 채운 비율) — 표면 1m 가 텍스처 몇 화소인지. zmax: 그 높이 아래 면만 (밑동·땅 가까운 부분)"""
    me = o.data
    if not me.uv_layers:
        return 0.0, 0.0
    uv = me.uv_layers.active.data
    mw = o.matrix_world
    a3, a2 = 0.0, 0.0
    for p in me.polygons:
        if zmax is not None and (mw @ p.center).z > zmax:
            continue
        pts = [uv[i].uv for i in p.loop_indices]
        s = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % len(pts)]
            s += x0 * y1 - x1 * y0
        a2 += abs(s) * 0.5
        a3 += p.area
    return size * math.sqrt(a2 / max(a3, 1e-9)), a2

def uv_islands(o):
    """UV 섬: 면 번호 목록들 (모서리 양쪽 UV 가 같으면 같은 섬)"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    uvl = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    par = list(range(len(bm.faces)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for e in bm.edges:
        if len(e.link_loops) != 2:
            continue
        l0, l1 = e.link_loops
        # 같은 모서리를 두 면이 반대 방향으로 돈다: l0.vert == l1.next.vert
        a0, b0 = l0[uvl].uv, l0.link_loop_next[uvl].uv
        if l1.vert == l0.vert:          # 면 방향이 뒤집힌 이웃
            a1, b1 = l1[uvl].uv, l1.link_loop_next[uvl].uv
        else:
            a1, b1 = l1.link_loop_next[uvl].uv, l1[uvl].uv
        if (a0 - a1).length < 1e-5 and (b0 - b1).length < 1e-5:
            ra, rb = find(l0.face.index), find(l1.face.index)
            if ra != rb:
                par[ra] = rb
    groups = {}
    for f in bm.faces:
        groups.setdefault(find(f.index), []).append(f.index)
    bm.free()
    return list(groups.values())

def scale_islands(o, weight):
    """섬마다 텍셀 배율을 준다 (pack_islands 는 모든 섬을 같은 배율로 키우므로 상대 크기가 남는다).
    weight(면 가운데 월드 좌표, 면 법선) → 배율 (1 = 기본, 0.6 = 덜 중요한 뒷면 …). 섬의 겉넓이 가중 평균을 쓴다"""
    me = o.data
    uv = me.uv_layers.active.data
    mw = o.matrix_world
    n3 = mw.to_3x3()
    for isl in uv_islands(o):
        ws, wa = 0.0, 0.0
        for fi in isl:
            p = me.polygons[fi]
            w = weight(mw @ p.center, (n3 @ p.normal).normalized())
            ws += w * p.area; wa += p.area
        k = ws / wa if wa > 0 else 1.0
        if abs(k - 1.0) < 1e-4:
            continue
        loops = [li for fi in isl for li in me.polygons[fi].loop_indices]
        c = sum((uv[li].uv for li in loops), Vector((0, 0))) / len(loops)
        for li in loops:
            uv[li].uv = c + (uv[li].uv - c) * k
    return o

def _hard_edges(o, angle):
    """UV 섬 경계이면서 angle 도보다 꺾인 모서리를 단단하게(sharp) — 굽은 노멀맵이 모서리에서 급하게 휘지 않아 또렷하다.
    단단한 모서리는 반드시 UV 이음매여야 한다 (아니면 그 줄에 이음매 자국)"""
    act(o)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.seams_from_islands(mark_seams=True, mark_sharp=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    bm = bmesh.new(); bm.from_mesh(o.data)
    n = 0
    for e in bm.edges:
        if e.seam and len(e.link_faces) == 2 and e.calc_face_angle(0.0) > R(angle):
            e.smooth = False
            n += 1
    bm.to_mesh(o.data); bm.free()
    o.data.use_auto_smooth = True
    o.data.auto_smooth_angle = math.pi
    return n

def finish(name, highs, low_parts, extras=(), size=1024, extr=0.03, lod1=0.35, lod2=None, uv_angle=66,
           cage=None, cage_reach=0.2, hard=None, pack=False, samples=None, margin=16, margin_type='EXTEND', uv_margin=0.003,
           uv='smart', uv_weight=None, lod_rule=False, bake_groups=None, probe=None, split_cage=False, despeck=False):
    """highs: 굽기 원본 / low_parts: 저폴리 조각 (하나로 합쳐 UV를 펴고 Main 재질)
    extras: 굽지 않고 그대로 붙이는 부품 (Glow_* 재질, Foliage 재질을 미리 입힌 것)
    lod1, lod2: LOD 비율 (Main 부분만 줄인다). None 이면 만들지 않는다.
    (v3 선택 인자, 기본값이면 예전과 같다 — finish3 가 v3 기본값으로 부른다)
      cage: 숫자면 make_cage(push=cage) 로 우리를 만들어 굽는다 (extr 무시). cage_reach: 우리 최대 거리
      hard: 각도(도). UV 섬 경계이면서 그보다 꺾인 모서리를 단단하게 / pack: UV 섬을 다시 빽빽하게 배치
      samples: 굽기 표본 수 / margin, margin_type: 굽기 여백 (0 이면 자홍으로 채워 굽고 빈 곳을 직접 메운다)
      uv_margin: (pack 일 때) UV 섬 사이 여백. 섬이 수백 개인 벽·돌무더기는 0.001 (여백이 텍스처를 절반 넘게 먹는다)
    (v3b 선택 인자)
      size: 'auto' 면 tex_size 규칙 (가장 긴 변 1.5 m 미만 1024, 그 밖 2048). 2048 보다 크면 2048 로 낮춘다 (4096 금지)
      uv: 'smart' = smart_project 로 편다 / 'keep' = 저폴리 조각에 이미 있는 UV 를 쓴다 (나무 원통 전개 등). pack 이면 다시 배치
      uv_weight: f(면 가운데, 법선) → 텍셀 배율. 섬마다 크기를 바꾼 뒤 배치 (앞면 1.0, 뒷면·바닥 0.6 처럼 중요한 면에 텍셀을 몰아 준다)
      lod_rule: 깨끗한 저폴리 규칙 (finish3 기본). Main 1,000 삼각형 미만이면 LOD1 은 줄이지 않고 잎·덩굴만 뺀다
        (잎이 없으면 LOD1 없음), 1,000~3,000 이면 LOD1 비율을 0.6 이상으로
      bake_groups: [[원본, ...], ...] — 저폴리 면 속성 'bgrp' 가 g 인 면은 bake_groups[g] 의 원본에만 굽는다 (나무 가지별 굽기)
      probe: f(low, size) — TEXEL 줄 뒤에 더 찍을 것 (나무 줄기 밑동 텍셀 등)
      split_cage: (hard 와 함께) 단단한 모서리에서 저폴리 사본을 쪼갠 뒤 우리를 만들어 굽는다. 쪼개지 않으면 모서리 정점의 우리가
        양쪽 면 법선의 평균으로 부풀어, 좁은 면(모따기·떨어진 자국 벽)에서 광선이 옆 면으로 비껴 맞아 빗살 무늬(흰 점선 + 검은 점)가 된다.
        단단한 모서리 = UV 이음매라 쪼개도 이음매가 늘지 않는다 (내보내는 저폴리는 그대로)
      despeck: albedo 의 외딴 점(AO 표본 잡음)을 지운다 (despeckle, 로그 BAKE 의 despeck %)"""
    t0 = __import__('time').time()
    low = join(low_parts)
    origin0(low)
    low.name = name + "_LOD0"
    low.data.name = name + "_LOD0"
    low.data.materials.clear()
    if size == 'auto' or (isinstance(size, int) and size > 2048):
        size = tex_size(low.dimensions, size)
    if os.environ.get("KIT_FAST"):
        # 빠른 반복용 (밝기·칠·형태만 볼 때): 텍스처 512, 굽기 표본 4. 결과물로 쓰지 않는다
        size = min(size, 512); samples = 4
        print("KIT_FAST", name, "tex", size)
    if uv == 'keep' and low.data.uv_layers:
        # 조각마다 이름이 다른 UV 층이면 join 이 층을 여러 개 만든다 → 첫 층만 남긴다
        while len(low.data.uv_layers) > 1:
            low.data.uv_layers.remove(low.data.uv_layers[-1])
        low.data.uv_layers.active = low.data.uv_layers[0]
    else:
        act(low)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        # v3(pack): 빈 곳을 둘레 색으로 메우므로(fill_holes) 섬 사이 여백은 작아도 된다 → 섬이 수백 개인 벽에서 텍셀이 크게 는다
        bpy.ops.uv.smart_project(angle_limit=R(uv_angle), island_margin=uv_margin if pack else 0.008)
        bpy.ops.object.mode_set(mode='OBJECT')
    if pack:
        # 다시 빽빽하게 배치 — 섬이 수백 개면 Blender 배치기가 오히려 성기게 놓을 때가 있어, 채운 비율이 줄면 되돌린다
        uvd = low.data.uv_layers.active.data
        keep = [0.0] * (len(uvd) * 2)
        uvd.foreach_get('uv', keep)
        f0 = uv_stats(low, size)[1]
        if uv_weight is not None:
            scale_islands(low, uv_weight)
        act(low)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.pack_islands(rotate=True, margin=uv_margin, shape_method='CONCAVE')
        bpy.ops.object.mode_set(mode='OBJECT')
        f1 = uv_stats(low, size)[1]
        if f1 < f0 and uv_weight is None and uv != 'keep':
            low.data.uv_layers.active.data.foreach_set('uv', keep)
            f1 = -f1
        print("UVPACK", name, "first", round(f0, 3), "pack", round(abs(f1), 3), "keep" if f1 >= 0 else "revert",
              "islands", len(uv_islands(low)))
    if low.data.uv_layers:
        low.data.uv_layers[0].name = "UVMap"
    hard_segs = None
    if hard:
        print("HARD", name, _hard_edges(low, hard))
        hard_segs = _sharp_uv_segments(low)
    td, fillr = uv_stats(low, size)
    td_low = uv_stats(low, size, zmax=1.5)[0]
    print("TEXEL", name, "px/m", round(td), "uv_fill", round(fillr, 3), "tex", size, "low1.5m", round(td_low))
    if probe is not None:
        probe(low, size)

    # v3(margin=0): 두 그림을 자홍으로 채워 두고 여백 없이 굽은 뒤 빈 곳을 직접 메운다 (Blender 여백은 둘레의 빈 화소와 섞여
    # 섬 가장자리에 자홍·검정 테두리를 남긴다). 예전 방식(margin>0)은 검게 지우고 굽은 뒤 검게 남은 곳만 메운다.
    sentinel = (margin == 0)
    img_a = bpy.data.images.new(name + "_albedo", size, size, alpha=False)
    img_n = bpy.data.images.new(name + "_normal", size, size, alpha=False)
    img_n.colorspace_settings.name = 'Non-Color'
    if sentinel:
        img_a.generated_color = (SENTINEL[0], SENTINEL[1], SENTINEL[2], 1.0)
        img_n.generated_color = (SENTINEL[0], SENTINEL[1], SENTINEL[2], 1.0)
    mat = bpy.data.materials.new("Main")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    ta = nt.nodes.new('ShaderNodeTexImage'); ta.image = img_a
    tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = img_n
    low.data.materials.append(mat)
    _ray_off(low)
    old_samples = sc.cycles.samples
    if samples:
        sc.cycles.samples = samples
    if bake_groups:
        # (v3b) 무리마다 따로 굽기: 저폴리 면의 'bgrp'(면 속성) = 무리 번호, 그 면은 그 무리의 원본에만 광선을 쏜다.
        # 나무: 가지마다 따로 깎은 원본에 그 가지 관만 구워 가지 이음매(원본이 합쳐진 곳)의 극단 법선·검은 점이 생기지 않는다
        tb = __import__('time').time()
        jobs = []
        for g, hs in enumerate(bake_groups):
            hs = [h for h in hs if h is not None]
            if not hs:
                continue
            tmp = copy(low)
            bm = bmesh.new(); bm.from_mesh(tmp.data)
            lay = bm.faces.layers.int.get('bgrp')
            kill = [f for f in bm.faces if lay is None or f[lay] != g]
            bmesh.ops.delete(bm, geom=kill, context='FACES')
            bm.to_mesh(tmp.data); bm.free()
            if not tmp.data.polygons:
                delete(tmp)
                continue
            _ray_off(tmp)
            jobs.append((tmp, hs, make_cage(tmp, hs, cage, cage_reach) if cage else None))
        nt.nodes.active = ta
        for tmp, hs, cg in jobs:
            _bake(tmp, hs, img_a, 'DIFFUSE', extr, cg, margin, margin_type, use_clear=False if sentinel else (tmp is jobs[0][0]))
        tb2 = __import__('time').time()
        nt.nodes.active = tn
        for tmp, hs, cg in jobs:
            _bake(tmp, hs, img_n, 'NORMAL', extr, cg, margin, margin_type, use_clear=False if sentinel else (tmp is jobs[0][0]))
        tb3 = __import__('time').time()
        for tmp, hs, cg in jobs:
            delete(cg); delete(tmp)
        print("BAKEGROUPS", name, len(jobs))
    else:
        bl = low
        if split_cage and hard:
            bl = copy(low)
            bm = bmesh.new(); bm.from_mesh(bl.data)
            sharp = [e for e in bm.edges if not e.smooth]
            if sharp:
                bmesh.ops.split_edges(bm, edges=sharp)
            bm.to_mesh(bl.data); bm.free()
            _ray_off(bl)
            print("SPLITCAGE", name, "sharp", len(sharp))
        cg = make_cage(bl, highs, cage, cage_reach) if cage else None
        tb = __import__('time').time()
        nt.nodes.active = ta
        _bake(bl, highs, img_a, 'DIFFUSE', extr, cg, margin, margin_type, use_clear=not sentinel)
        tb2 = __import__('time').time()
        nt.nodes.active = tn
        _bake(bl, highs, img_n, 'NORMAL', extr, cg, margin, margin_type, use_clear=not sentinel)
        tb3 = __import__('time').time()
        delete(cg)
        if bl is not low:
            delete(bl)
    sc.cycles.samples = old_samples
    _ray_off(low, False)
    miss = fill_holes(img_a)
    dsp = despeckle(img_a) if despeck else None
    steep = 0.0
    rim = rim_s = None
    inner = 0.0
    if sentinel:
        # v3b: 메우기 전에 법선 통계 — rim(섬 경계 띠의 누운 법선) 은 비스듬히 스친 광선의 흰·검은 테두리를 잡는다
        rim, rim_s, steep, _cov, inner = normal_stats(img_n, hard_segs)
        fill_holes(img_n, misses=False)
        clamp_normals(img_n)
    print("BAKE", name, "miss %.3f%%" % (miss * 100), "steep %.2f%%" % (steep * 100),
          ("rim %.2f%% rim_soft %.2f%% inner %.2f%%" % (rim * 100, rim_s * 100, inner * 100)) if rim is not None else "rim -",
          ("despeck %.3f%%" % (dsp * 100)) if dsp is not None else "",
          "albedo_s", round(tb2 - tb, 1), "normal_s", round(tb3 - tb2, 1), "total_s", round(__import__('time').time() - t0, 1))
    if sentinel and (steep * 100 > WARN_STEEP or (rim_s * 100 > WARN_RIM and rim_s > 1.5 * inner)):
        print("WARN BAKE", name, "steep %.2f%% (기준 %.0f%%)" % (steep * 100, WARN_STEEP),
              "rim_soft %.2f%% (기준 %.0f%% 이면서 섬 안쪽 %.2f%% 의 1.5 배)" % (rim_s * 100, WARN_RIM, inner * 100),
              "— 섬 경계·깊은 홈을 광선이 비스듬히 스친다: 저폴리가 큰 면(slice·spall)을 따라가게, 홈 벽을 45도 안팎으로, 단단한 모서리+이음매로")
    _save_jpg(img_a, os.path.join(OUT, name + "_albedo.jpg"))
    nbytes = save_png(img_n, os.path.join(OUT, name + "_normal.png"))
    print("FILES", name, "albedo_kb", os.path.getsize(os.path.join(OUT, name + "_albedo.jpg")) // 1024, "normal_kb", nbytes // 1024)
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(ta.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    for h in highs:
        delete(h)

    extra_list = [e for e in extras if e is not None]
    is_fol = lambda e: bool(e.data.materials) and all(m_ is not None and m_.name.startswith("Foliage") for m_ in e.data.materials)
    specs = [(r, True) for r in (lod1, lod2) if r]          # (줄임 비율, 잎·덩굴을 남기나)
    if lod_rule and specs:
        n0 = tri_count(low)
        if n0 < 1000:
            # 깨끗한 저폴리는 줄이면 실루엣·단단한 모서리·UV 이음매가 무너진다 → 본체는 그대로, 잎·덩굴만 뺀다 (없으면 LOD1 없음)
            specs = [(1.0, False)] if any(is_fol(e) for e in extra_list) else []
        elif n0 < 3000:
            specs = [(max(specs[0][0], 0.6), True)] + specs[1:]
        print("LODRULE", name, "main", n0, "->", specs)
    lods = [low]
    keep_fol = [True]
    for i, (ratio, kf) in enumerate(specs):
        c = copy(low)
        c.name = name + "_LOD%d" % (i + 1)
        c.data.name = c.name
        if ratio < 0.999:
            m = c.modifiers.new('dec', 'DECIMATE'); m.ratio = ratio; m.use_collapse_triangulate = True
            apply_all(c)
        lods.append(c)
        keep_fol.append(kf)
    for i, L in enumerate(lods):
        ex_i = [e for e in extra_list if keep_fol[i] or not is_fol(e)]
        if ex_i:
            ex = [copy(e) for e in ex_i]
            joined = join([L] + ex)
            joined.name = name + "_LOD%d" % i
            lods[i] = joined
    for e in extra_list:
        delete(e)
    for L in lods:
        for p in L.data.polygons:
            p.use_smooth = True
    info = {'name': name, 'tris': [tri_count(L) for L in lods], 'size': [round(v, 2) for v in lods[0].dimensions], 'tex': size}
    bpy.ops.object.select_all(action='DESELECT')
    for L in lods:
        L.select_set(True)
    bpy.context.view_layer.objects.active = lods[0]
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, name + ".fbx"), use_selection=True, object_types={'MESH'},
                             apply_scale_options='FBX_SCALE_UNITS', bake_space_transform=True, axis_forward='-Z', axis_up='Y',
                             use_mesh_modifiers=True, mesh_smooth_type='OFF', add_leaf_bones=False, bake_anim=False,
                             colors_type='SRGB')
    print("ASSET", info)
    for i, L in enumerate(lods):
        L.location = (1000 + len(LOWS) * 40, 1000 + i * 40, 0)   # 미리보기 장면에서 복제해 쓸 원본은 멀리 치워 둔다
        L.hide_render = True
    LOWS[name] = lods[0]
    return lods[0]

def finish_foliage(name, parts, lod1=None):
    """굽지 않는 식물 (풀·꽃·버섯 등): 재질이 이미 붙은 부품을 합쳐 바로 내보낸다"""
    o = join(parts)
    origin0(o)
    o.name = name + "_LOD0"
    o.data.name = o.name
    lods = [o]
    if lod1:
        c = copy(o); c.name = name + "_LOD1"; c.data.name = c.name
        m = c.modifiers.new('dec', 'DECIMATE'); m.ratio = lod1
        apply_all(c)
        lods.append(c)
    bpy.ops.object.select_all(action='DESELECT')
    for L in lods:
        L.select_set(True)
    bpy.context.view_layer.objects.active = lods[0]
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, name + ".fbx"), use_selection=True, object_types={'MESH'},
                             apply_scale_options='FBX_SCALE_UNITS', bake_space_transform=True, axis_forward='-Z', axis_up='Y',
                             use_mesh_modifiers=True, mesh_smooth_type='OFF', add_leaf_bones=False, bake_anim=False,
                             colors_type='SRGB')
    info = {'name': name, 'tris': [tri_count(L) for L in lods], 'size': [round(v, 2) for v in o.dimensions], 'tex': 0}
    print("ASSET", info)
    for i, L in enumerate(lods):
        L.location = (1000 + len(LOWS) * 40, 1000 + i * 40, 0)
        L.hide_render = True
    LOWS[name] = o
    return o

# ───────────────────────── 다시 읽기 (검증·미리보기) ─────────────────────────
def _base_name(n):
    """Blender 가 이름이 겹칠 때 붙이는 '.001' 꼬리를 뗀다"""
    import re
    return re.sub(r"\.\d{3,}$", "", n)

def load_fbx(name):
    """내보낸 FBX와 텍스처를 디스크에서 다시 읽는다. LOD0만 남긴다.
    같은 이름을 두 번 읽으면(비교 렌더 등) 두 번째는 '이름_LOD0.001' 이 되므로 꼬리를 떼고 LOD0 을 찾는다
    (v3b 에서 고침: 예전에는 endswith('_LOD0') 이 실패해 아무 LOD 나 골랐다)"""
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.fbx(filepath=os.path.join(OUT, name + ".fbx"))
    new = [bpy.data.objects[k] for k in set(bpy.data.objects.keys()) - before]
    meshes = [x for x in new if x.type == 'MESH']
    o = (next((x for x in meshes if _base_name(x.name) == name + "_LOD0"), None)
         or next((x for x in meshes if _base_name(x.name).endswith("_LOD0")), None)
         or (meshes or new)[0])
    for x in new:
        if x is not o:
            delete(x)
    o.parent = None
    xf_all(o)
    main = None
    alb = os.path.join(OUT, name + "_albedo.jpg")
    if os.path.exists(alb):
        main = bpy.data.materials.new(name + "_Main")
        main.use_nodes = True
        nt = main.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        bsdf.inputs["Roughness"].default_value = 0.85
        ta = nt.nodes.new('ShaderNodeTexImage'); ta.image = bpy.data.images.load(alb)
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = bpy.data.images.load(os.path.join(OUT, name + "_normal.png"))
        tn.image.colorspace_settings.name = 'Non-Color'
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(ta.outputs['Color'], bsdf.inputs['Base Color'])
        nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    for slot in o.material_slots:
        n = slot.material.name if slot.material else ""
        base = n.split(".")[0]
        if base in GLOW:
            slot.material = glow_mat(base)
        elif base.startswith("Foliage"):
            slot.material = foliage_mat()
        elif main is not None:
            slot.material = main
    o.location = (1000 + len(LOWS) * 40, 1000, 0)
    o.hide_render = True
    LOWS[name] = o
    return o

def place(name, loc, rz=0.0, s=1.0, tilt=(0, 0)):
    src = LOWS[name]
    o = bpy.data.objects.new(name + "_i", src.data)
    sc.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (tilt[0], tilt[1], rz)
    o.scale = (s, s, s) if not isinstance(s, (tuple, list)) else s
    return o

# ═════════════════════════ v3: 정으로 깎은 고급 스타일라이즈드 ═════════════════════════
# 기존 함수(sculpt, paint, STONE_LAYERS, finish 의 기본 인자)는 그대로 두고, 새 함수로만 쓴다 (기존 묶음은 그대로 빌드된다).
#   carve()        리메시 + 리메시 전 표면에 되붙이기(평평한 면·날카로운 모서리) + 조각(블록) 번호 + 조각 층
#   lowpoly()      조립한 깨끗한 형태(리메시 전)에서 저폴리 — 면이 평평하고 모서리가 곧다 (석물·벽돌)
#   STONE3/ROCK3/BARK3   (큰 형태 층, 잔 조각 층). lumps 는 아주 약하게, chisel(평면 끌 자국)·또렷한 terrace 위주
#   paint3()       손칠 재질: 위는 밝고 아래·틈은 보라, 베벨로 찾은 닳은 모서리, 블록마다 색조, 위·틈 이끼, 끌 자국 결
#   finish3()      finish + 굽기 우리(cage) + UV 다시 배치 + 빈 곳 메우기, 텍스처 기본 2048

def remesh_sharp(o, voxel, relax=0):
    """복셀 리메시는 모서리를 voxel 만큼 둥글리고 비스듬한 모서리를 계단처럼 만든다.
    리메시 전 표면의 가장 가까운 점으로 되붙여(Shrinkwrap) 평평한 면과 곧은 모서리를 되살린다.
    되붙이면 오목한 꺾임에 voxel 보다 작은 톱니(접힌 삼각형)가 남는다 → relax(1~2)번 고르게 펴면 없어진다 (모서리가 voxel 만큼 무뎌짐).
    톱니는 깊은 벽(바위의 떨어진 자국 등)이 있을 때 굽힌 테두리에 검은 톱니로 보인다"""
    src = copy(o)
    remesh(o, voxel)
    m = o.modifiers.new('snap', 'SHRINKWRAP')
    m.target = src
    m.wrap_method = 'NEAREST_SURFACEPOINT'
    if relax:
        r = o.modifiers.new('relax', 'SMOOTH')
        r.factor = 0.5
        r.iterations = relax
    apply_all(o)
    delete(src)
    return o

def _piece_src(o, seed=0):
    """떨어진 조각(블록·덩어리)마다 0~1 무작위 값. (원래 면 BVH, 면별 값, 조각 수) — 리메시 전에 부른다"""
    from mathutils.bvhtree import BVHTree
    rng = random.Random(seed * 7 + 3)
    bm = bmesh.new(); bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    bm.verts.ensure_lookup_table()
    comp = [-1] * len(bm.verts)
    vals = []
    for v in bm.verts:
        if comp[v.index] >= 0:
            continue
        cid = len(vals); vals.append(rng.random())
        comp[v.index] = cid
        stack = [v]
        while stack:
            x = stack.pop()
            for e in x.link_edges:
                y = e.other_vert(x)
                if comp[y.index] < 0:
                    comp[y.index] = cid
                    stack.append(y)
    verts = [v.co.copy() for v in bm.verts]
    polys = [[v.index for v in f.verts] for f in bm.faces]
    fcomp = [comp[f.verts[0].index] for f in bm.faces]
    fval = [vals[c] for c in fcomp]
    # 조각마다 위·아래 높이 (paint3 grime: 줄눈 바로 아래 흙물·그을음, 블록 아래쪽 그늘)
    zr = [[1e9, -1e9] for _ in vals]
    for v in bm.verts:
        c = comp[v.index]
        zr[c][0] = min(zr[c][0], v.co.z); zr[c][1] = max(zr[c][1], v.co.z)
    bm.free()
    return BVHTree.FromPolygons(verts, polys), fval, len(vals), fcomp, zr

def _piece_put(o, src):
    """리메시한 객체의 각 정점에 가장 가까운 원래 조각의 값을 'piece' 속성으로 (paint3 가 블록마다 색조를 바꾼다).
    v3b: 'ptop' = 그 조각 꼭대기까지 내려온 거리(m), 'pbot' = 조각 바닥에서 올라간 거리(m) — 줄눈 아래 흙물·그을음에 쓴다"""
    tree, fval, n = src[:3]
    fcomp, zr = (src[3], src[4]) if len(src) > 4 else (None, None)
    me = o.data
    for nm in ('piece', 'ptop', 'pbot'):
        if nm in me.attributes:
            me.attributes.remove(me.attributes[nm])
    at = me.attributes.new('piece', 'FLOAT', 'POINT')
    mw = o.matrix_world
    out, tops, bots = [], [], []
    for v in me.vertices:
        p = mw @ v.co
        hit = tree.find_nearest(p)
        fi = hit[2]
        out.append(fval[fi] if fi is not None else 0.5)
        if zr is not None:
            if fi is not None:
                z0, z1 = zr[fcomp[fi]]
                tops.append(max(0.0, z1 - p.z)); bots.append(max(0.0, p.z - z0))
            else:
                tops.append(1.0); bots.append(1.0)
    at.data.foreach_set('value', out)
    if zr is not None:
        me.attributes.new('ptop', 'FLOAT', 'POINT').data.foreach_set('value', tops)
        me.attributes.new('pbot', 'FLOAT', 'POINT').data.foreach_set('value', bots)
    return n

def remesh_octree(o, voxel):
    """(v3b) 날카로운 모서리를 살리는 옥트리 리메시 (Blender Remesh 'SHARP' = 듀얼 컨투어링). 칸 크기 ≈ voxel.
    복셀 리메시 + 되붙이기는 비스듬한 모서리를 따라 정점이 계단(지그재그)으로 놓여, 닳은 모서리 빛이 찢어진 종이 테두리처럼 보인다.
    옥트리는 정점이 모서리 선 위에 놓여 모서리가 곧다. 얇은 판·좁은 틈(칸 2개 미만)은 뭉개질 수 있으니 깨끗한 덩어리(바위)에 쓴다"""
    dim = max(o.dimensions) / 0.99
    depth = max(6, min(10, int(math.ceil(math.log2(max(dim / max(voxel, 1e-4), 2.0))))))
    m = o.modifiers.new('remesh', 'REMESH')
    m.mode = 'SHARP'; m.octree_depth = depth; m.scale = 0.99; m.sharpness = 1.0
    m.use_remove_disconnected = False
    apply_all(o)
    print("OCTREE", o.name, "depth", depth, "cell", round(dim / 2 ** depth, 4), "faces", len(o.data.polygons))
    return o

def _edge_src(o, angle=35.0, step=0.004):
    """(v3b) 깨끗한 형태의 볼록한 날카로운 모서리 위 점들 (KD 나무). 리메시 뒤 정점마다 '모서리까지 거리'를 재는 데 쓴다"""
    from mathutils.kdtree import KDTree
    bm = bmesh.new(); bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    bm.normal_update()
    pts = []
    for e in bm.edges:
        if len(e.link_faces) != 2 or e.calc_face_angle(0.0) < R(angle):
            continue
        if not e.is_convex:
            continue
        a, b = e.verts[0].co, e.verts[1].co
        n = max(1, int((b - a).length / step))
        for i in range(n + 1):
            pts.append(a.lerp(b, i / n))
    bm.free()
    if not pts:
        return None
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    return kd

def _edge_put(o, kd, cap=0.2):
    """정점마다 볼록 모서리까지 거리(m) → 'edist' 속성 (paint3(edge_mode='attr') 가 닳은 모서리를 곧고 고르게 칠한다)"""
    me = o.data
    if 'edist' in me.attributes:
        me.attributes.remove(me.attributes['edist'])
    mw = o.matrix_world
    out = []
    for v in me.vertices:
        r = kd.find(mw @ v.co)
        out.append(min(cap, r[2]) if r[0] is not None else cap)
    me.attributes.new('edist', 'FLOAT', 'POINT').data.foreach_set('value', out)

def carve(o, voxel, coarse=(), fine=(), seed=0, snap=True, pieces=True, base=False, relax=0, mode='voxel', edges=True,
          edge_from=None):
    """v3 조각: [조각 번호] → 리메시(+snap: 원래 표면에 되붙임, relax: 되붙인 톱니 펴기) → 큰 형태 층(coarse) → 잔 조각 층(fine).
    voxel: 작은 소품 0.0025~0.0035, 중간 0.005~0.009, 큰 것 0.01~0.02 (snap 덕에 예전보다 조금 커도 모서리가 산다)
    mode='octree' (v3b): 복셀 + 되붙이기 대신 옥트리(SHARP) 리메시 — 모서리가 곧다 (바위처럼 깨끗한 덩어리)
    edges (v3b): 깨끗한 형태의 볼록 모서리까지 거리를 'edist' 속성으로 → paint3(edge_mode='attr') 의 닳은 모서리가 곧고 고르다
    edge_from (v3b): 닳은 모서리를 찾을 형태 (기본 o). 글자·금을 새기기 전 사본을 주면 글자·금 입술이 밝게 빛나지 않는다
      (금 둘레에 흰 외곽선이 생기면 장난감 같다). 쓰고 나면 지운다
    base=True 면 저폴리 바탕(되붙이지 않은 리메시 + coarse)을 돌려준다 (리메시 형태에서 저폴리를 줄일 때.
    다 새긴 것·되붙인 것에서 줄이면 면이 구겨지거나 접힌 잔 삼각형 때문에 UV 섬이 수천 개로 쪼개진다)"""
    origin0(o)
    src = _piece_src(o, seed) if pieces else None
    ekd = _edge_src(edge_from or o, step=max(0.002, voxel * 0.5)) if edges else None
    if edge_from is not None:
        delete(edge_from)
    b = None
    if base:
        # 저폴리 바탕은 되붙이지 않은 리메시에서 (되붙인 면은 모서리에 접힌 잔 삼각형이 있어, 줄이면 UV 섬이 수천 개로 쪼개진다)
        b = copy(o)
        remesh(b, voxel)
        if coarse:
            surface(b, list(coarse), seed)
    if mode == 'octree':
        remesh_octree(o, voxel)
    elif snap:
        remesh_sharp(o, voxel, relax)
    else:
        remesh(o, voxel)
    if src is not None:
        print("PIECES", o.name, _piece_put(o, src))
    if ekd is not None:
        _edge_put(o, ekd)
    if coarse:
        surface(o, list(coarse), seed)
    if fine:
        surface(o, list(fine), seed + 1)
    return b

def lowpoly(o, tris=None, z=None):
    """조립한 깨끗한 형태(리메시 전)를 저폴리로: 사본 → 삼각형 → (tris 보다 많으면) 줄이기 → [z 아래 면 지우기].
    면이 평평하고 모서리가 곧아서 finish3(hard=...) 의 단단한 모서리와 잘 맞는다"""
    c = copy(o)
    c.modifiers.clear()
    if c.matrix_world != Matrix.Identity(4):
        xf_all(c)
    bm = bmesh.new(); bm.from_mesh(c.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0004)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.0004)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    if z is not None:
        kill = [f for f in bm.faces if all(v.co.z < z for v in f.verts)]
        if kill:
            bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(c.data); bm.free()
    if tris and tri_count(c) > tris:
        m = c.modifiers.new('dec', 'DECIMATE'); m.ratio = tris / tri_count(c); m.use_collapse_triangulate = True
        apply_all(c)
    for p in c.data.polygons:
        p.use_smooth = True
    return c

def vgroove(pa, pb, nrm, width, depth, floor=0.3):
    """V 자(사다리꼴) 홈 커터 — 끌로 판 글자·선. 겉면 폭 width, 바닥 폭 width*floor, 깊이 depth, 끝도 비스듬하다.
    벽이 수직인 상자 커터는 굽힌 노멀맵에서 글자 테두리가 1화소 폭 검은 점선이 된다 (v3 에서 바꾼 까닭)"""
    pa, pb = Vector(pa), Vector(pb)
    z = Vector(nrm).normalized()
    d = pb - pa
    d = d - z * d.dot(z)
    L = d.length
    x = d.normalized() if L > 1e-6 else z.orthogonal().normalized()
    y = z.cross(x).normalized()
    c = (pa + pb) / 2
    top = depth * 0.8                                    # 겉면 위로 조금 더 (불리언이 겉면과 겹치지 않게)
    wb, lb = width * floor * 0.5, L * 0.5 + width * floor * 0.4
    k = (width * 0.5 - wb) / depth                       # 깊이 1 당 넓어지는 폭
    wt, lt = wb + k * (depth + top), lb + k * (depth + top) * 0.9
    vs = []
    for hz, hw, hl in ((-depth, wb, lb), (top, wt, lt)):
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vs.append(c + x * (sx * hl) + y * (sy * hw) + z * hz)
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return mesh_from("vgroove", vs, faces)

def engrave_v(o, strokes, nrm, width, depth, floor=0.3):
    """획 목록 [(시작, 끝), ...] 을 V 자 홈으로 판다"""
    cs = [vgroove(a, b, nrm, width, depth, floor) for a, b in strokes]
    if cs:
        cut(o, cs)
    return o

def STONE3(k=1.0, wear=1.0, cracks=0.5):
    """v3 다듬은 돌 (묘비·벽돌·기둥): (coarse, fine). 넓은 면은 평평하게 두고 얕은 평면 끌 자국(chisel), 곧게 꺾인 가는 금(cracks),
    드문 잔 구멍. 값이 뚝 끊기는 층(plates, soft 작은 terrace)은 쓰지 않는다 (복셀 격자에 톱니). 구불구불한 fissure 는 고리 모양이 생겨 뺐다.
    k: 물체 크기 배율 (1 = 사람 키 정도), wear: 풍화, cracks: 금이 덮는 비율"""
    coarse = [{'t': 'lumps', 'scale': 0.7 / k, 'amp': 0.0008 * k * wear}]
    fine = [
        {'t': 'chisel', 'scale': 5.5 / k, 'amp': 0.003 * k * wear, 'tilt': 0.8, 'jitter': 0.6, 'wall': 0.14},
        {'t': 'chisel', 'scale': 16.0 / k, 'amp': 0.0012 * k * wear, 'tilt': 0.8, 'jitter': 0.6, 'wall': 0.18, 'cover': 0.6},
        {'t': 'cracks', 'scale': 2.2 / k, 'width': 0.02, 'depth': 0.005 * k, 'warp': 0.08, 'cover': 0.16 * cracks / 0.5, 'cover_scale': 0.8 / k},
        {'t': 'cracks', 'scale': 6.0 / k, 'width': 0.025, 'depth': 0.002 * k, 'warp': 0.08, 'cover': 0.14 * cracks / 0.5, 'cover_scale': 1.6 / k},
        {'t': 'pits', 'scale': 34.0 / k, 'depth': 0.001 * k * wear, 'cover': 0.35},
    ]
    return coarse, fine

def ROCK3(k=1.0, cracks=0.6, chisel=0.0):
    """v3b 자연석 (바위·절벽): (coarse, fine). 형태는 깨끗한 덩어리의 큰 평면(slice·chip_convex·평면 spall, 저폴리에도 들어간다)이
    만들고, 조각 층은 굵은 금 몇 줄 + 아주 얕은 큰 굴곡뿐이다. 끌 자국(chisel) 층은 바위 넓은 면에서 칸 경계마다 접힌 능선이 생겨
    구겨진 종이·은박지처럼 읽혀 기본으로 뺐다 (chisel=0.3 정도로만 되살린다). 잔 구멍(pits)·terrace 도 뺐다.
    k: 크기 배율 (바위 크기/2), cracks: 금이 덮는 비율. carve(mode='octree') 와 함께 쓴다"""
    coarse = []
    fine = [
        {'t': 'lumps', 'scale': 0.9 / k, 'amp': 0.009 * k},
        {'t': 'cracks', 'scale': 1.5 / k, 'width': 0.022, 'depth': 0.018 * k, 'warp': 0.08, 'cover': cracks * 0.6, 'cover_scale': 0.6 / k},
        {'t': 'cracks', 'scale': 3.6 / k, 'width': 0.03, 'depth': 0.006 * k, 'warp': 0.08, 'cover': cracks * 0.3, 'cover_scale': 1.3 / k},
    ]
    if chisel > 0:
        fine.insert(1, {'t': 'chisel', 'scale': 2.4 / k, 'amp': 0.02 * k * chisel, 'tilt': 1.0, 'jitter': 0.5, 'wall': 0.25, 'warp': 0.1})
    return coarse, fine

def BARK3(k=1.0, depth=1.0):
    """v3b 나무껍질 (guide 필요): (coarse, fine). 가지 방향으로 긴 껍질판(폭 15 cm 안팎, 길이 그 5~6배)과 깊은 골(폭 6~7 cm, 깊이 4.5 cm, 벽 55도 안팎 — 더 가파르면 steep 이 2% 를 넘는다)
    — 2~5 m 에서 골이 읽히는 굵기. 판 위는 거의 평평하고(ridge 작게) 판마다 높이가 조금 다르다(plate).
    v3 의 잔 골(scale 8)·끌 자국(chisel)·물결(ridge 0.25)은 판을 그물·핏줄·구겨진 천처럼 보이게 해서 뺐다. 잔결은 Unity 디테일 맵(wood)이 맡는다"""
    coarse = [{'t': 'lumps', 'scale': 1.0 / k, 'amp': 0.006 * k}]
    fine = [
        {'t': 'bark', 'scale': 6.0 / k, 'width': 0.2, 'depth': 0.045 * k * depth, 'stretch': 0.17, 'ridge': 0.05, 'plate': 0.12, 'warp': 0.1},
        {'t': 'bark', 'scale': 15.0 / k, 'width': 0.07, 'depth': 0.006 * k * depth, 'stretch': 0.12, 'ridge': 0.0, 'warp': 0.1},
    ]
    return coarse, fine

def _ramp_n(nt, src, stops, interp='LINEAR'):
    """여러 단계 색 띠: stops = [(위치, (r,g,b)), ...]"""
    r = nt.nodes.new('ShaderNodeValToRGB')
    r.color_ramp.interpolation = interp
    e = r.color_ramp.elements
    while len(e) < len(stops):
        e.new(0.5)
    for el, (p, c) in zip(e, stops):
        el.position = p
        el.color = W(c)
    nt.links.new(src, r.inputs['Fac'])
    return r.outputs['Color']

def _vmath(nt, op, a, b=None):
    m = nt.nodes.new('ShaderNodeVectorMath'); m.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if hasattr(v, 'links'):
            nt.links.new(v, m.inputs[i])
        else:
            m.inputs[i].default_value = v
    return m.outputs['Value'] if op in ('DOT_PRODUCT', 'LENGTH', 'DISTANCE') else m.outputs['Vector']

def _vscale(nt, col, k):
    """색 × 수 (1 보다 큰 배율도 된다)"""
    m = nt.nodes.new('ShaderNodeVectorMath'); m.operation = 'SCALE'
    nt.links.new(col, m.inputs[0])
    if hasattr(k, 'links'):
        nt.links.new(k, m.inputs['Scale'])
    else:
        m.inputs['Scale'].default_value = k
    return m.outputs['Vector']

def _maprange(nt, v, a, b, c=0.0, d=1.0):
    m = nt.nodes.new('ShaderNodeMapRange'); m.clamp = True
    nt.links.new(v, m.inputs['Value'])
    m.inputs['From Min'].default_value = a; m.inputs['From Max'].default_value = b
    m.inputs['To Min'].default_value = c; m.inputs['To Max'].default_value = d
    return m.outputs['Result']

def _ao(nt, dist, samples=12):
    a = nt.nodes.new('ShaderNodeAmbientOcclusion')
    a.inputs['Distance'].default_value = dist
    a.samples = samples
    a.only_local = True          # 자기 자신만 (굽기 중 저폴리·다른 객체에 가려 검게 되지 않게)
    return a.outputs['AO']

def paint3(name, pal='stone', h=1.0, k=1.0, moss=0.5, moss_color=MOSS, dirt=0.6, dirt_h=None, edge=0.9, edge_w=None,
           cavity=0.9, ao=None, light=1.0, piece_var=0.6, cells=None, hue_var=0.5, strokes=0.35, tooling=0.25, streaks=0.3,
           grain=0.5, speckle=0.45, stains=0.35, moss_low=0.0, moss_low_h=None, shadow=(0.16, 0.1, 0.3), bump=0.35,
           piece_val=0.0, grime=0.0, grime_h=None, edge_gain=1.0, contrast=0.15, gain=1.1, pivot=0.1, moss_patch=2.4,
           facet_var=0.0, facet_scale=2.5, edge_mode='bevel', lichen=0.0, lichen_color=(0.42, 0.45, 0.36), lichen_scale=11.0):
    """v3 손칠 재질 (굽기 원본용). 색 → Base Color(DIFFUSE 굽기), 잔 결 → Normal(NORMAL 굽기).
    pal: PAL 이름 또는 (어두운, 밝은, 모서리) / h: 물체 높이(m) — 위→아래 밝기 / k: 무늬 크기 배율 (1 = 사람 키)
    light: 위에서 비친 듯한 밝기 차이 / hue_var: 큰 얼룩으로 차가운 청색 ↔ 보랏빛 / piece_var: 블록(carve 의 'piece')마다 색조·밝기 차이 / cells: 블록 번호가 없을 때
    대신 쓸 큰 칸 크기(m, 바위) / edge: 닳은 모서리 밝게 (edge_w: 폭 m) / cavity: 틈·구석 보라 그늘 / moss: 위쪽·틈 이끼
    moss_low: 땅에서 기어오르는 이끼 (moss_low_h 높이까지) / dirt: 흙물 (dirt_h 높이까지)
    strokes: 붓 자국 / speckle: 잔 점 / stains: 검게 삭은 얼룩 / tooling: 끌 자국 결(노멀) / streaks: 빗물 자국 / grain: 잔 결(노멀)
    (v3b) piece_val: 블록(또는 칸)마다 밝기 ±비율 (0.15 = ±15%) / grime: 줄눈 바로 아래 흙물·그을음 (carve 의 'ptop', grime_h 높이까지 흘러내림)
    edge_gain: 닳은 모서리 색 배율 / contrast: 명암 대비(pivot 밝기를 기준으로 거듭제곱, 0.2 = 밝은 곳 더 밝고 어두운 곳 더 어둡게)
    gain: 전체 밝기 배율 / contrast·gain 기본 0.15·1.1 은 v3b 에서 맞춘 값: v3 칠은 이전 판(v2, AgX 로 저장된 albedo)보다
      물체 평균 밝기가 8~17% 어둡고 대비가 작았다 (albmeasure: 겉넓이 가중 sRGB 휘도). 이전 소품들 사이에서 붕 뜨지 않게
      평균은 이전 ±10%, 대비는 더 크게 / moss_patch: 이끼 덩어리 무늬 크기(작을수록 큰 덩어리)
    facet_var: 면 방향마다 밝기·색조 ±비율 (법선의 잡음 → 평평한 깨진 면 하나는 한 톤, 이웃 면과는 다른 톤: 손칠 바위의 면 나눔)
    edge_mode: 'bevel' = 베벨 노드로 모서리 찾기 (표본 잡음 때문에 점선처럼 보일 수 있다) / 'attr' = carve 가 넣은 'edist'
      (깨끗한 형태의 볼록 모서리까지 거리) — 곧고 고른 닳은 모서리. carve(edges=True) 로 만든 원본에서만
    lichen: 지의류 반점 (작고 가장자리가 또렷한 옅은 점, 위·옆면) — 넓은 평면이 비닐처럼 비어 보이지 않게 3~6 m 에서 읽히는 잔무늬
      lichen_scale: 반점 무늬 주파수 (k 로 나눈 좌표 기준, 클수록 잘다. 바위 k=1.8 에서 11 이면 10~20 cm 흰 물감 자국처럼 커서 20 안팎)"""
    dark, lightc, edgec = PAL[pal] if isinstance(pal, str) else pal
    edge_w = edge_w if edge_w is not None else 0.006 * k
    ao = ao if ao is not None else 0.3 * k
    dirt_h = dirt_h if dirt_h is not None else min(0.35, 0.3 * h)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 1.0
    tc = nt.nodes.new('ShaderNodeTexCoord')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    P = tc.outputs['Object']
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1 / k, 1 / k, 1 / k)
    nt.links.new(P, mp.inputs['Vector'])
    Pk = mp.outputs['Vector']
    sN = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(geo.outputs['Normal'], sN.inputs[0])
    sP = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(P, sP.inputs[0])
    lerp = lambda a, b, t: tuple(x + (y - x) * t for x, y in zip(a, b))

    # 1. 위에서 비친 밝기: 높이 + 위를 향한 면 + 큰 얼룩 (손칠 그림의 명암을 색에 그려 넣는다)
    zf = _maprange(nt, sP.outputs['Z'], 0.0, max(h, 0.05))
    nzf = _maprange(nt, sN.outputs['Z'], -0.9, 0.9)
    big = _noise(nt, Pk, 0.9, 3, 0.5)
    midn = _noise(nt, Pk, 3.2, 4, 0.55)
    Lv = _mul(nt, _mul(nt, zf, 0.42 * light), _mul(nt, nzf, 0.32 * light), 'ADD')
    Lv = _mul(nt, Lv, _mul(nt, _mul(nt, big, 0.5, 'SUBTRACT'), 0.6), 'ADD')
    Lv = _mul(nt, Lv, _mul(nt, _mul(nt, midn, 0.5, 'SUBTRACT'), 0.36), 'ADD')
    Lv = _mul(nt, Lv, 0.5 - 0.45 * light, 'ADD')
    col = _ramp_n(nt, Lv, [(0.0, lerp(dark, shadow, 0.5)), (0.26, dark), (0.6, lerp(dark, lightc, 0.62)), (0.94, lightc)])
    if hue_var > 0:   # 큰 얼룩: 차가운 청색 ↔ 보랏빛 (손칠 그림의 색 온도 차이)
        hv = _ramp_n(nt, _noise(nt, Pk, 0.55, 2, 0.5), [(0.3, (0.4, 0.45, 0.62)), (0.5, (0.5, 0.5, 0.5)), (0.7, (0.55, 0.47, 0.56))])
        col = _mix(nt, 'OVERLAY', hue_var, col, hv)

    # 2. 블록마다 색조·밝기 (carve 의 'piece', 없으면 큰 칸)
    if piece_var > 0:
        if cells:
            vo = nt.nodes.new('ShaderNodeTexVoronoi'); vo.inputs['Scale'].default_value = 1.0 / cells
            nt.links.new(P, vo.inputs['Vector'])
            pv = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(vo.outputs['Color'], pv.inputs[0])
            pf = pv.outputs['X']
        else:
            at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_type = 'GEOMETRY'; at.attribute_name = 'piece'
            pf = at.outputs['Fac']
        tint = _ramp_n(nt, pf, [(0.0, (0.36, 0.4, 0.56)), (0.3, (0.5, 0.5, 0.53)), (0.55, (0.44, 0.44, 0.48)),
                                (0.8, (0.62, 0.56, 0.52)), (1.0, (0.58, 0.56, 0.68))])
        col = _mix(nt, 'OVERLAY', piece_var, col, tint)
        if piece_val > 0:   # (v3b) 블록마다 밝기 ±piece_val (색조와 엇갈리게 다른 난수)
            pf2 = _mul(nt, _mul(nt, _mul(nt, pf, 7.31), 0.17, 'ADD'), 0.0, 'FRACT')
            col = _vscale(nt, col, _maprange(nt, pf2, 0.0, 1.0, 1.0 - piece_val, 1.0 + piece_val))

    # 2b. (v3b) 깨진 면마다 다른 톤: 법선의 함수라 평평한 면 하나는 한 톤 (손칠 바위처럼 면이 나뉘어 읽힌다)
    if facet_var > 0:
        fN = _vscale(nt, geo.outputs['Normal'], 1.0)
        f1 = _noise(nt, fN, facet_scale, 0.0, 0.5)
        col = _vscale(nt, col, _maprange(nt, f1, 0.3, 0.7, 1.0 - facet_var, 1.0 + facet_var))
        f2 = _noise(nt, _vmath(nt, 'ADD', fN, (3.7, 1.3, 5.1)), facet_scale * 0.8, 0.0, 0.5)
        col = _mix(nt, 'OVERLAY', facet_var * 1.6, col, _ramp_n(nt, f2, [(0.3, (0.42, 0.46, 0.6)), (0.5, (0.5, 0.5, 0.5)), (0.7, (0.58, 0.5, 0.47))]))

    # 3. 붓 자국: 방향이 다른 두 갈래로 늘인 잡음 (낮은 대비)
    if strokes > 0:
        for sc_, sca in (((1.0, 1.0, 7.0), 3.0), ((6.0, 1.0, 1.0), 5.0)):
            mp2 = nt.nodes.new('ShaderNodeMapping'); mp2.inputs['Scale'].default_value = tuple(s / k for s in sc_)
            mp2.inputs['Rotation'].default_value = (0.3, 0.2, 0.5)
            nt.links.new(P, mp2.inputs['Vector'])
            st = _ramp_n(nt, _noise(nt, mp2.outputs['Vector'], sca, 3, 0.45), [(0.3, (0.4, 0.4, 0.42)), (0.7, (0.6, 0.6, 0.6))])
            col = _mix(nt, 'OVERLAY', strokes * 0.7, col, st)
    if speckle > 0:   # 잔 점 (붓끝으로 찍은 듯)
        spk = _ramp_n(nt, _noise(nt, Pk, 38.0, 2, 0.5), [(0.36, (0.4, 0.4, 0.43)), (0.64, (0.6, 0.6, 0.6))])
        col = _mix(nt, 'OVERLAY', speckle, col, spk)
    if stains > 0:    # 삭아서 어두워진 얼룩 (드문드문, 가장자리 또렷). 바탕색에 곱한다 (어두운 색 묶음에서 새까만 점이 되지 않게)
        stm = _maprange(nt, _noise(nt, Pk, 4.5, 5, 0.65), 0.6, 0.67)
        col = _mix(nt, 'MULTIPLY', _mul(nt, stm, stains), col, W((0.55, 0.5, 0.62)))

    # 4. 빗물 자국 (옆면만, 위에서 아래로)
    if streaks > 0:
        mp3 = nt.nodes.new('ShaderNodeMapping'); mp3.inputs['Scale'].default_value = (16 / k, 16 / k, 0.7 / k)
        nt.links.new(P, mp3.inputs['Vector'])
        sm = _mul(nt, _ramp_n(nt, _noise(nt, mp3.outputs['Vector'], 3.0, 3), [(0.5, (0, 0, 0)), (0.68, (1, 1, 1))]),
                  _maprange(nt, sN.outputs['Z'], 0.6, 0.2))
        col = _mix(nt, 'MIX', _mul(nt, sm, streaks * 0.55), col, W(lerp(dark, shadow, 0.3)))

    # 4b. (v3b) 줄눈 바로 아래 흙물·그을음: 블록 꼭대기(ptop=0)에서 grime_h 만큼 세로 줄무늬로 흘러내린 어두운 띠 (옆면만)
    if grime > 0 and not cells:
        gh = grime_h if grime_h is not None else 0.12 * k
        atT = nt.nodes.new('ShaderNodeAttribute'); atT.attribute_type = 'GEOMETRY'; atT.attribute_name = 'ptop'
        mp4 = nt.nodes.new('ShaderNodeMapping'); mp4.inputs['Scale'].default_value = (22 / k, 22 / k, 1.5 / k)
        nt.links.new(P, mp4.inputs['Vector'])
        drip = _maprange(nt, _noise(nt, mp4.outputs['Vector'], 2.5, 3, 0.5), 0.3, 0.7, 0.35, 1.6)    # 줄마다 흘러내린 길이가 다르다
        band = _maprange(nt, _mul(nt, atT.outputs['Fac'], drip, 'DIVIDE'), gh, 0.0)
        side = _maprange(nt, sN.outputs['Z'], 0.75, 0.35)
        gm = _mul(nt, _mul(nt, band, side), grime)
        col = _mix(nt, 'MULTIPLY', gm, col, W(lerp(shadow, (0.0, 0.0, 0.0), 0.35)))

    # 5. 그늘: 넓은 AO(보라) + 좁은 AO(틈·금은 또렷하게 깊은 보라)
    aoB = _ao(nt, ao, 16)
    col = _mix(nt, 'MULTIPLY', cavity * 0.85, col, _ramp_n(nt, aoB, [(0.2, lerp(shadow, (1, 1, 1), 0.25)), (0.95, (1, 1, 1))]))
    aoS = _ao(nt, ao * 0.1, 16)          # v3b: 10 → 16 (틈 입술의 소금·후추 점)
    col = _mix(nt, 'MULTIPLY', cavity * 0.85, col, _ramp_n(nt, aoS, [(0.35, lerp(shadow, (0, 0, 0), 0.15)), (0.9, (1, 1, 1))]))

    # 6. 닳은 모서리: 베벨 법선과 실제 법선의 차이(모서리) × 좁은 AO 가 밝은 곳(볼록) — 폭이 고르고 또렷한 선
    if edge > 0 and edge_mode == 'attr':
        atE = nt.nodes.new('ShaderNodeAttribute'); atE.attribute_type = 'GEOMETRY'; atE.attribute_name = 'edist'
        wob = _maprange(nt, _noise(nt, Pk, 2.2, 2, 0.5), 0.3, 0.7, 0.4, 1.3)      # 닳은 폭이 길게 변한다
        e1 = _maprange(nt, _mul(nt, atE.outputs['Fac'], wob, 'DIVIDE'), edge_w, edge_w * 0.2)
        # 군데군데 끊긴다 (온 모서리가 같은 굵기로 빛나면 외곽선을 그린 장난감 같다)
        conv = _maprange(nt, _noise(nt, Pk, 1.6, 2, 0.5), 0.38, 0.52)
    elif edge > 0:
        bv = nt.nodes.new('ShaderNodeBevel'); bv.samples = 8; bv.inputs['Radius'].default_value = edge_w
        dv = _vmath(nt, 'DOT_PRODUCT', bv.outputs['Normal'], geo.outputs['Normal'])
        e1 = _maprange(nt, dv, 0.975, 0.9)          # 또렷한 모서리만 (끌 자국 능선·잔 굴곡에는 반응하지 않게)
        aoE = _ao(nt, edge_w * 3.0, 6)
        conv = _maprange(nt, aoE, 0.72, 0.92)
    if edge > 0:
        # 닳은 정도가 길게 이어지며 변한다 (v3: 잡음 9 → 점선·바느질 자국처럼 끊겨 보였다)
        brk = _ramp_n(nt, _noise(nt, Pk, 3.5, 2, 0.5), [(0.3, (0.45, 0.45, 0.45)), (0.6, (1, 1, 1))])
        em = _mul(nt, _mul(nt, _mul(nt, e1, conv), brk), edge)
        col = _mix(nt, 'MIX', em, col, W(tuple(min(1.0, c * edge_gain) for c in edgec)))

    # 7. 이끼: 위를 향한 면에 가장자리가 또렷한 덩어리 + 위쪽 틈에 고인 것
    if moss > 0:
        up = _maprange(nt, sN.outputs['Z'], 0.42, 0.82)
        patch = _ramp_n(nt, _noise(nt, Pk, moss_patch, 6, 0.6), [(0.47, (0, 0, 0)), (0.53, (1, 1, 1))])
        crev = _maprange(nt, aoS, 0.7, 0.4)
        upsoft = _maprange(nt, sN.outputs['Z'], -0.1, 0.5)
        where = _mul(nt, _mul(nt, up, patch), _mul(nt, _mul(nt, crev, upsoft), 0.7), 'MAXIMUM')
        mc = _ramp_n(nt, _noise(nt, Pk, 16, 4), [(0.3, tuple(c * 0.45 for c in moss_color)), (0.72, tuple(min(1, c * 1.3) for c in moss_color))])
        mc = _mix(nt, 'MIX', _mul(nt, nzf, 0.3), mc, W(tuple(min(1, c * 1.6) for c in moss_color)))
        col = _mix(nt, 'MIX', _mul(nt, where, moss), col, mc)
    if moss_low > 0:
        mh = moss_low_h if moss_low_h is not None else 0.3 * h
        wob = _mul(nt, _mul(nt, _noise(nt, Pk, 3.5, 4), 0.5, 'SUBTRACT'), mh * 0.9)
        zz = _mul(nt, sP.outputs['Z'], wob, 'ADD')
        lowm = _maprange(nt, zz, mh, mh * 0.4)
        patch2 = _ramp_n(nt, _noise(nt, Pk, 5.0, 6, 0.6), [(0.46, (0, 0, 0)), (0.53, (1, 1, 1))])
        mc2 = _ramp_n(nt, _noise(nt, Pk, 24, 5), [(0.3, tuple(c * 0.4 for c in moss_color)), (0.72, tuple(min(1, c * 1.2) for c in moss_color))])
        col = _mix(nt, 'MIX', _mul(nt, _mul(nt, lowm, patch2), moss_low), col, mc2)
    if lichen > 0:   # (v3b) 지의류: 작은 덩어리 무늬 × 또렷한 문턱 (솜뭉치처럼 번지지 않게)
        lz = _maprange(nt, sN.outputs['Z'], -0.2, 0.4)
        lsp = _maprange(nt, _noise(nt, Pk, lichen_scale, 3, 0.6), 0.6, 0.63)
        lcl = _maprange(nt, _noise(nt, Pk, 1.3, 2, 0.5), 0.4, 0.6)        # 몰려 있는 곳과 빈 곳
        col = _mix(nt, 'MIX', _mul(nt, _mul(nt, _mul(nt, lsp, lcl), lz), lichen), col, W(lichen_color))
    # 8. 땅에 닿는 아래쪽 흙물
    if dirt > 0:
        dm = _mul(nt, _maprange(nt, sP.outputs['Z'], dirt_h, 0.0),
                  _ramp_n(nt, _noise(nt, Pk, 5, 3), [(0.3, (0.55, 0.55, 0.55)), (0.7, (1, 1, 1))]))
        col = _mix(nt, 'MIX', _mul(nt, dm, dirt), col, W((0.035, 0.03, 0.045)))
    # 10. (v3b) 대비·밝기: pivot 밝기는 그대로 두고 밝은 곳은 더 밝게, 어두운 곳은 더 어둡게 (col^(1+c) × pivot^-c) → × gain
    if contrast or gain != 1.0:
        if contrast:
            gm_ = nt.nodes.new('ShaderNodeGamma'); gm_.inputs['Gamma'].default_value = 1.0 + contrast
            nt.links.new(col, gm_.inputs['Color'])
            col = gm_.outputs['Color']
        col = _vscale(nt, col, gain * pivot ** (-contrast))
    nt.links.new(col, bsdf.inputs['Base Color'])

    # 9. 노멀: 끌 자국 결(칸마다 방향이 다른 가는 평행 줄) + 잔 결
    hgt = None
    if tooling > 0:
        vt = nt.nodes.new('ShaderNodeTexVoronoi'); vt.inputs['Scale'].default_value = 7.0 / k
        nt.links.new(P, vt.inputs['Vector'])
        dirv = _vmath(nt, 'NORMALIZE', _vmath(nt, 'SUBTRACT', vt.outputs['Color'], (0.5, 0.5, 0.5)))
        wn = nt.nodes.new('ShaderNodeTexNoise'); wn.inputs['Scale'].default_value = 60.0 / k
        nt.links.new(P, wn.inputs['Vector'])
        ph = _mul(nt, _vmath(nt, 'DOT_PRODUCT', P, dirv), 2 * math.pi / (0.008 * k))
        ph = _mul(nt, ph, _mul(nt, _mul(nt, wn.outputs['Fac'], 0.5, 'SUBTRACT'), 6.0), 'ADD')     # 줄이 곧지 않게 흔든다
        stripe = _mul(nt, ph, 0.0, 'SINE')
        cm = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(vt.outputs['Color'], cm.inputs[0])
        on = _maprange(nt, cm.outputs['Z'], 0.55, 0.62)
        hgt = _mul(nt, _mul(nt, stripe, on), tooling * 0.35)
    if grain > 0:
        gr = _mul(nt, _mul(nt, _noise(nt, Pk, 140, 3), 0.5, 'SUBTRACT'), grain)
        hgt = gr if hgt is None else _mul(nt, hgt, gr, 'ADD')
    if hgt is not None and bump > 0:
        b = nt.nodes.new('ShaderNodeBump')
        b.inputs['Strength'].default_value = bump
        b.inputs['Distance'].default_value = 0.0015 * k
        nt.links.new(hgt, b.inputs['Height'])
        nt.links.new(b.outputs['Normal'], bsdf.inputs['Normal'])
    return m

def finish3(name, highs, low_parts, extras=(), size='auto', cage=0.006, cage_reach=0.2, hard=None, lod1=0.35, lod2=None,
            uv_angle=66, samples=8, uv_margin=0.003, uv='smart', uv_weight=None, lod_rule=True, bake_groups=None, probe=None,
            split_cage=True, despeck=True):
    """v3 마무리: 굽기 우리(cage) + UV 다시 배치(pack) + 여백 없이 굽고 빈 곳을 둘레 색으로 메우기(자홍·검정 테두리 없음).
    size: 'auto' = 가장 긴 변 1.5 m 미만 1024, 그 밖 2048 (저장소 용량 규칙, 4096 금지)
    cage: 우리 여유(m), hard: 단단한 모서리 각도(도, 석물 55 안팎·각진 바위 35~40 / 나무 None)
    samples: 굽기 표본 (색은 AO·베벨 광선이 따로 있어 8 이면 충분) / uv_margin: 섬 사이 여백 (섬이 수백 개면 0.001)
    uv / uv_weight / lod_rule / split_cage: finish 설명 참고 (lod_rule 기본 켬: Main 1,000 삼각형 미만은 LOD1 에서 잎만 뺀다,
    split_cage 기본 켬: hard 가 있으면 단단한 모서리에서 쪼갠 우리로 굽는다)"""
    return finish(name, highs, low_parts, extras=extras, size=size, lod1=lod1, lod2=lod2, uv_angle=uv_angle,
                  cage=cage, cage_reach=cage_reach, hard=hard, pack=True, samples=samples, margin=0, uv_margin=uv_margin,
                  uv=uv, uv_weight=uv_weight, lod_rule=lod_rule, bake_groups=bake_groups, probe=probe, split_cage=split_cage,
                  despeck=despeck)
