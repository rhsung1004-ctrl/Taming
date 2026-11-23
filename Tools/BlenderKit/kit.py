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
            vo = voronoi(warp(P, L['scale'] * 0.6, 0.25 / L['scale']), L['scale'])
            sep = N.new('ShaderNodeSeparateXYZ'); _ng_link(ng, vo.outputs['Color'], sep.inputs[0])
            h = maprange(sep.outputs['X'], 0.0, 1.0, -L['amp'], L['amp'] * 0.35)
            v = masked(h, cover(P, L.get('cover', 0.6), L.get('cover_scale', 1.3)))
        elif t == 'terrace':
            # 잡음의 등고선을 따라 계단처럼 깨진 턱 (자연스럽게 겹겹이 떨어져 나간 돌)
            n = noise(warp(P, L['scale'] * 0.5, 0.2 / L['scale']), L['scale'], L.get('detail', 3.0), 0.55)
            st = L.get('steps', 5)
            q = math('DIVIDE', math('FLOOR', math('MULTIPLY', n, st)), st)
            # 턱 바로 위를 살짝 둥글게 (완전 수직이면 굽기에서 계단 현상)
            fr = math('FRACT', math('MULTIPLY', n, st))
            soft = maprange(fr, 0.0, 0.25, -0.35 / st, 0.0)
            v = masked(maprange(math('ADD', q, soft), 0.2, 0.8, -L['amp'], L['amp']), cover(P, L.get('cover', 1.0), L.get('cover_scale', 1.2)))
        elif t == 'fissure':
            # 잡음 등고선 위의 가늘고 구불구불한 금 (그물 모양이 아니라 자연스러운 금)
            n = noise(warp(P, L['scale'] * 0.7, 0.25 / L['scale']), L['scale'], L.get('detail', 4.0), 0.6)
            line = math('ABSOLUTE', math('SUBTRACT', n, 0.5))
            d = maprange(line, 0.0, L['width'], -L['depth'], 0.0)
            v = masked(d, cover(P, L.get('cover', 0.6), L.get('cover_scale', 1.4)))
        elif t == 'cracks':
            vo = voronoi(warp(P, L['scale'] * 0.8, 0.3 / L['scale']), L['scale'], 'DISTANCE_TO_EDGE')
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
            Q = warp(sub.outputs[0], L['scale'] * 0.5, 0.15 / L['scale'])
            vo = voronoi(Q, L['scale'], 'DISTANCE_TO_EDGE')
            groove = maprange(vo.outputs['Distance'], 0.0, L['width'], -L['depth'], 0.0)
            ridges = maprange(noise(Q, L['scale'] * 3.0, 3.0), 0.3, 0.7, -L['depth'] * 0.25, L['depth'] * 0.25)
            v = math('ADD', groove, ridges)
        if v is None:
            continue
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
def _bake(low, highs, img, kind, extr):
    bpy.ops.object.select_all(action='DESELECT')
    for h in highs:
        h.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    if kind == 'DIFFUSE':
        bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, use_selected_to_active=True, cage_extrusion=extr,
                            max_ray_distance=0.0, margin=16, use_clear=True)
    else:
        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=extr, max_ray_distance=0.0, margin=16, use_clear=True)

def _save_jpg(img, path, quality=92):
    s = bpy.context.scene.render.image_settings
    s.file_format = 'JPEG'; s.quality = quality; s.color_mode = 'RGB'
    img.save_render(path)

def finish(name, highs, low_parts, extras=(), size=1024, extr=0.03, lod1=0.35, lod2=None, uv_angle=66):
    """highs: 굽기 원본 / low_parts: 저폴리 조각 (하나로 합쳐 UV를 펴고 Main 재질)
    extras: 굽지 않고 그대로 붙이는 부품 (Glow_* 재질, Foliage 재질을 미리 입힌 것)
    lod1, lod2: LOD 비율 (Main 부분만 줄인다). None 이면 만들지 않는다."""
    low = join(low_parts)
    origin0(low)
    low.name = name + "_LOD0"
    low.data.name = name + "_LOD0"
    low.data.materials.clear()
    act(low)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=R(uv_angle), island_margin=0.008)
    bpy.ops.object.mode_set(mode='OBJECT')
    if low.data.uv_layers:
        low.data.uv_layers[0].name = "UVMap"

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
    _bake(low, highs, img_a, 'DIFFUSE', extr)
    nt.nodes.active = tn
    _bake(low, highs, img_n, 'NORMAL', extr)
    _save_jpg(img_a, os.path.join(OUT, name + "_albedo.jpg"))
    img_n.filepath_raw = os.path.join(OUT, name + "_normal.png")
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
    for i, L in enumerate(lods):
        if extra_list:
            ex = [copy(e) for e in extra_list]
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
def load_fbx(name):
    """내보낸 FBX와 텍스처를 디스크에서 다시 읽는다. LOD0만 남긴다."""
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.fbx(filepath=os.path.join(OUT, name + ".fbx"))
    new = [bpy.data.objects[k] for k in set(bpy.data.objects.keys()) - before]
    o = next((x for x in new if x.name.endswith("_LOD0")), new[0])
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
