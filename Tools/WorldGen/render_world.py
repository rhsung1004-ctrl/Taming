# 월드 데이터를 Blender 로 그려 보는 확인 렌더 (Unity 화면과 같지는 않다: 조명·안개·풀 모양을 가늠하는 용도)
#   blender -b --python-exit-code 1 -P render_world.py -- <월드 폴더(Ch1)> <소품 폴더(kit_out)> <출력 접두어> [보기,보기] [samples]
# 보기: overview, spawn, graveyard, swamp, cathedral, dragon, tree, bridge, gate, village (장소),
#       fields, roadside, ne_field, hamlet, pair, quiet (v3 눈높이 1.7 m 보기: 장면이 지형에 가리지 않고 보이는 자리),
#       scene_<틀> (예: scene_barrow — <월드>/_scenes.json 에서 그 틀의 첫 장면을 앞 24 m 눈높이에서),
#       eye_<x>_<z>_<방향> (v3 채움: 좌표 눈높이 보기. 땅 + 1.7 m, 세로 시야 60°, 방향 = Unity Y 회전 도(0 북쪽, 90 동쪽), 수평에서 3° 아래를 본다.
#       예: eye_1395_1440_265). 생략하면 장소·눈높이 보기 전부
# 눈높이 보기(fields … quiet, scene_*, eye_*)는 카메라 둘레 260 m 를 1 m 격자 지형으로 그린다 (Unity 높이맵과 같은 해상도. 작은 둔덕·턱·도랑이 보이게)
import sys, os, json, math, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "BlenderKit"))
import bpy
import numpy as np
from mathutils import Matrix, Vector, Euler, Quaternion
import kit

argv = sys.argv[sys.argv.index("--") + 1:]
WORLD, KIT, PREFIX = argv[0], argv[1], argv[2]
VIEWS = argv[3].split(",") if len(argv) > 3 and argv[3] not in ("", "all") else None
SAMPLES = int(argv[4]) if len(argv) > 4 else 48
DATA = os.path.join(WORLD, "Data~")

kit.init(KIT, samples=SAMPLES)
sc = bpy.context.scene
# FBX 를 읽기 전에 진짜 재질을 먼저 만든다 (FBX 안의 같은 이름 재질이 이름을 차지하면 kit 가 그것을 돌려준다)
kit.foliage_mat()
for _g in kit.GLOW:
    kit.glow_mat(_g)
W = json.load(open(os.path.join(DATA, "world.json")))
RES = W["heightRes"]
H = np.fromfile(os.path.join(DATA, "height.r16"), dtype='<u2').reshape(RES, RES).astype(np.float32) / 65535.0 * W["height"]
OBJ = json.load(open(os.path.join(DATA, "objects.json")))
TREES = json.load(open(os.path.join(DATA, "trees.json")))
MAN = {}
for f in os.listdir(KIT):
    if f.startswith("manifest_") and f.endswith(".json"):
        for k, v in json.load(open(os.path.join(KIT, f))).items():
            MAN[k] = v.get("meta", {})

C_W = Matrix(((1, 0, 0), (0, 0, 1), (0, 1, 0)))
C_O = Matrix(((-1, 0, 0), (0, 0, 1), (0, -1, 0)))


def u2b(p):
    return Vector((p[0], p[2], p[1]))


def quat_u(q):
    x, y, z, w = q
    return Quaternion((w, x, y, z)).to_matrix()


def rot_b(Ru):
    """Unity 회전 행렬 → 소품의 Blender 회전 (SPEC: R_unity = C_w · M_b · C_o⁻¹)"""
    return C_W @ Ru @ C_O


def yaw_u(deg):
    return Matrix.Rotation(math.radians(deg), 3, 'Y')    # 수학 회전 그대로: +Z → +X (Unity 와 같은 행렬)


def hsample(x, z):
    x = min(max(x, 0), RES - 1.001)
    z = min(max(z, 0), RES - 1.001)
    i, j = int(z), int(x)
    fz, fx = z - i, x - j
    a = H[i, j] * (1 - fx) + H[i, j + 1] * fx
    b = H[i + 1, j] * (1 - fx) + H[i + 1, j + 1] * fx
    return float(a * (1 - fz) + b * fz)


# ───────────────────────── 지형 ─────────────────────────
_TMAT = []


def terrain(step=2, hole=None, x0=0, z0=0, n=None, name="Terrain"):
    """지형 격자 메쉬. hole = (x0, z0, x1, z1) 이면 그 상자 안 칸을 뺀다 (고운 패치 자리).
    x0, z0, n: 부분 격자 (고운 패치: step 1, 시작 좌표, 한 변 점 수)"""
    if n is None:
        n = (RES - 1) // step + 1
    hs = H[z0:z0 + (n - 1) * step + 1:step, x0:x0 + (n - 1) * step + 1:step]
    xs = np.arange(n, dtype=np.float32) * step
    X, Y = np.meshgrid(xs + x0, xs + z0)
    verts = np.stack([X.ravel(), Y.ravel(), hs.ravel()], 1).astype(np.float32)
    r = np.arange(n - 1)
    a = (r[:, None] * n + r[None, :]).ravel()
    quads = np.stack([a, a + 1, a + n + 1, a + n], 1).astype(np.int32)
    if hole is not None:
        qx = verts[a, 0]
        qz = verts[a, 1]
        inside = (qx >= hole[0]) & (qx + step <= hole[2]) & (qz >= hole[1]) & (qz + step <= hole[3])
        quads = quads[~inside]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.ravel())
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    uv = me.uv_layers.new(name="UVMap")
    vi = quads.ravel()
    uvs = np.stack([verts[vi, 0] / W["size"], verts[vi, 1] / W["size"]], 1).astype(np.float32)
    uv.data.foreach_set("uv", uvs.ravel())
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    if not _TMAT:
        _TMAT.append(terrain_mat())
    o.data.materials.append(_TMAT[0])
    return o


def terrain_for(cam_u, fine_r=260):
    """눈높이 보기: 카메라 둘레 fine_r m 는 1 m 격자, 나머지는 2 m 격자 (구멍을 맞춘다)"""
    for o in list(sc.objects):
        if o.name.startswith("Terrain"):
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(me)
    if cam_u is None:
        terrain(2)
        return
    cx, cz = cam_u[0], cam_u[2]
    x0 = int(max(0, min(RES - 1 - 2 * fine_r, cx - fine_r)) // 2 * 2)
    z0 = int(max(0, min(RES - 1 - 2 * fine_r, cz - fine_r)) // 2 * 2)
    n = 2 * fine_r + 1
    terrain(2, hole=(x0, z0, x0 + n - 1, z0 + n - 1))
    terrain(1, x0=x0, z0=z0, n=n, name="TerrainFine")


def terrain_mat():
    m = bpy.data.materials.new("TerrainMat")
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    uvn = N.new('ShaderNodeUVMap'); uvn.uv_map = "UVMap"
    sp = []
    for k in range(2):
        t = N.new('ShaderNodeTexImage')
        t.image = bpy.data.images.load(os.path.join(DATA, "splat_%d.png" % k))
        t.image.colorspace_settings.name = 'Non-Color'
        t.image.alpha_mode = 'CHANNEL_PACKED'      # 알파 = 넷째 층 무게 (투명도가 아니다)
        t.extension = 'EXTEND'
        L.new(uvn.outputs['UV'], t.inputs['Vector'])
        sep = N.new('ShaderNodeSeparateColor')
        L.new(t.outputs['Color'], sep.inputs['Color'])
        sp += [sep.outputs['Red'], sep.outputs['Green'], sep.outputs['Blue'], t.outputs['Alpha']]
    col_acc = nrm_acc = None
    rough_acc = None
    for i, lay in enumerate(W["layers"]):
        sc_ = N.new('ShaderNodeVectorMath'); sc_.operation = 'SCALE'
        L.new(uvn.outputs['UV'], sc_.inputs[0]); sc_.inputs['Scale'].default_value = W["size"] / lay["tile"]
        ta = N.new('ShaderNodeTexImage'); ta.image = bpy.data.images.load(os.path.join(WORLD, "Terrain", lay["albedo"]))
        tn = N.new('ShaderNodeTexImage'); tn.image = bpy.data.images.load(os.path.join(WORLD, "Terrain", lay["normal"]))
        tn.image.colorspace_settings.name = 'Non-Color'
        for t in (ta, tn):
            L.new(sc_.outputs['Vector'], t.inputs['Vector'])
        w = sp[i]
        c = N.new('ShaderNodeVectorMath'); c.operation = 'SCALE'
        L.new(ta.outputs['Color'], c.inputs[0]); L.new(w, c.inputs['Scale'])
        nn = N.new('ShaderNodeVectorMath'); nn.operation = 'SCALE'
        L.new(tn.outputs['Color'], nn.inputs[0]); L.new(w, nn.inputs['Scale'])
        rr = N.new('ShaderNodeMath'); rr.operation = 'MULTIPLY'
        L.new(w, rr.inputs[0]); rr.inputs[1].default_value = 1.0 - lay.get("smoothness", 0.05)
        if col_acc is None:
            col_acc, nrm_acc, rough_acc = c.outputs['Vector'], nn.outputs['Vector'], rr.outputs['Value']
        else:
            a1 = N.new('ShaderNodeVectorMath'); a1.operation = 'ADD'
            L.new(col_acc, a1.inputs[0]); L.new(c.outputs['Vector'], a1.inputs[1]); col_acc = a1.outputs['Vector']
            a2 = N.new('ShaderNodeVectorMath'); a2.operation = 'ADD'
            L.new(nrm_acc, a2.inputs[0]); L.new(nn.outputs['Vector'], a2.inputs[1]); nrm_acc = a2.outputs['Vector']
            a3 = N.new('ShaderNodeMath'); a3.operation = 'ADD'
            L.new(rough_acc, a3.inputs[0]); L.new(rr.outputs['Value'], a3.inputs[1]); rough_acc = a3.outputs['Value']
    L.new(col_acc, bsdf.inputs['Base Color'])
    L.new(rough_acc, bsdf.inputs['Roughness'])
    nm = N.new('ShaderNodeNormalMap'); nm.uv_map = "UVMap"; nm.inputs['Strength'].default_value = 1.0
    L.new(nrm_acc, nm.inputs['Color'])
    L.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def water():
    m = bpy.data.materials.new("Water")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.004, 0.006, 0.012, 1)
    b.inputs["Roughness"].default_value = 0.03
    b.inputs["IOR"].default_value = 1.33
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 3.0
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.03
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height']); nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    for i, wd in enumerate(OBJ.get("water", [])):
        bpy.ops.mesh.primitive_plane_add(size=1)
        o = bpy.context.active_object
        o.name = "Water%d" % i
        o.scale = (wd["size"][0], wd["size"][1], 1)
        o.location = u2b(wd["p"])
        o.rotation_euler = (0, 0, -math.radians(wd.get("yaw", 0)))
        o.data.materials.append(m)


# ───────────────────────── 산 벽 덮개 (cliffs.bin, w6a) ─────────────────────────
# Unity NecroWorldBuilder.BuildCliffs 와 같은 규칙: 조각 가운데까지 거리로 LOD 를 고르고 마지막 LOD 끝 밖은 그리지 않는다.
# 재질 = 지형 바위 층 텍스처(타일 = 파일의 tile m, UV = 덮개 u·v m) × 지층 밝기 띠(×2, v = 지층 높이 q). 지형 위에 그대로 겹친다
CLIFFS = None
_CMAT = []


def cliff_mat(cs):
    m = bpy.data.materials.new("CliffSkinMat")
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    lay = next(l for l in W["layers"] if l["name"] == "rock")
    uvn = N.new('ShaderNodeUVMap'); uvn.uv_map = "UVMap"
    ta = N.new('ShaderNodeTexImage'); ta.image = bpy.data.images.load(os.path.join(WORLD, "Terrain", lay["albedo"]))
    tn = N.new('ShaderNodeTexImage'); tn.image = bpy.data.images.load(os.path.join(WORLD, "Terrain", lay["normal"]))
    tn.image.colorspace_settings.name = 'Non-Color'
    for t in (ta, tn):
        L.new(uvn.outputs['UV'], t.inputs['Vector'])
    # 지층 띠: 칸 × 줄 그림 (선형, 128 = ×1). 가로(둘레)는 되풀이, 세로는 범위 안 (REPEAT 로 둔다)
    st = cs["strip"]
    img = bpy.data.images.new("CliffStrata", st.shape[1], st.shape[0], alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    px = np.ones((st.shape[0], st.shape[1], 4), np.float32)
    px[..., :3] = st[..., :3].astype(np.float32) / 255.0
    img.pixels.foreach_set(px.ravel())
    uvs = N.new('ShaderNodeUVMap'); uvs.uv_map = "Strata"
    ts = N.new('ShaderNodeTexImage'); ts.image = img; ts.extension = 'REPEAT'; ts.interpolation = 'Linear'
    L.new(uvs.outputs['UV'], ts.inputs['Vector'])
    mul = N.new('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'; mul.inputs['Factor'].default_value = 1.0
    L.new(ta.outputs['Color'], mul.inputs[6])
    x2 = N.new('ShaderNodeVectorMath'); x2.operation = 'SCALE'; x2.inputs['Scale'].default_value = 2.0
    L.new(ts.outputs['Color'], x2.inputs[0])
    L.new(x2.outputs['Vector'], mul.inputs[7])
    L.new(mul.outputs[2], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 1.0 - lay.get("smoothness", 0.12)
    nm = N.new('ShaderNodeNormalMap'); nm.uv_map = "UVMap"; nm.inputs['Strength'].default_value = 1.0
    L.new(tn.outputs['Color'], nm.inputs['Color'])
    L.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def cliffs(cam_u):
    """덮개 조각을 카메라 거리에 맞는 LOD 로 그린다 (cliffs.bin 이 없으면 건너뜀)"""
    global CLIFFS
    for o in list(sc.objects):
        if o.name.startswith("CliffSkin"):
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(me)
    path = os.path.join(DATA, "cliffs.bin")
    if not os.path.exists(path) or os.environ.get("NO_CLIFFS"):
        return
    if CLIFFS is None:
        sys.path.insert(0, HERE)
        import cliffskin
        CLIFFS = cliffskin.read(path)
    cs = CLIFFS
    if not _CMAT:
        _CMAT.append(cliff_mat(cs))
    cam = np.array(cam_u, np.float64)
    pos_all, uv_all, st_all, nrm_all, tri_all = [], [], [], [], []
    base = 0
    nchunk = [0] * len(cs["lod_end"])
    for ch in cs["chunks"]:
        d = float(np.linalg.norm(ch["center"] - cam))
        L = next((i for i, e in enumerate(cs["lod_end"]) if d < e), None)
        if L is None:
            continue
        lv = ch["lv"][L]
        if not lv["nquads"]:
            continue
        nchunk[L] += 1
        p = lv["pos"]
        pos_all.append(np.stack([p[:, 0], p[:, 2], p[:, 1]], 1))           # Unity (x, y, z) → Blender (x, z, y)
        n = lv["nrm"]
        nrm_all.append(np.stack([n[:, 0], n[:, 2], n[:, 1]], 1))
        uv_all.append(lv["uv"] / cs["tile"])
        st_all.append(np.stack([lv["uv"][:, 0] / cs["strip_period"], (lv["uv"][:, 1] - cs["strip_q0"]) / cs["strip_len"]], 1))
        t = lv["tri"]
        tri_all.append(t[:, ::-1] + base)                                  # 축을 바꾸면 감김이 뒤집힌다
        base += len(p)
    if not pos_all:
        return
    P = np.concatenate(pos_all).astype(np.float32)
    T = np.concatenate(tri_all).astype(np.int32)
    me = bpy.data.meshes.new("CliffSkin")
    me.vertices.add(len(P))
    me.vertices.foreach_set("co", P.ravel())
    me.loops.add(T.size)
    me.loops.foreach_set("vertex_index", T.ravel())
    me.polygons.add(len(T))
    me.polygons.foreach_set("loop_start", np.arange(0, T.size, 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(len(T), bool))
    vi = T.ravel()
    UV = np.concatenate(uv_all).astype(np.float32)
    ST = np.concatenate(st_all).astype(np.float32)
    a = me.uv_layers.new(name="UVMap"); a.data.foreach_set("uv", UV[vi].ravel())
    b = me.uv_layers.new(name="Strata"); b.data.foreach_set("uv", ST[vi].ravel())
    me.use_auto_smooth = True
    me.normals_split_custom_set_from_vertices([tuple(v) for v in np.concatenate(nrm_all)])
    o = bpy.data.objects.new("CliffSkin", me)
    sc.collection.objects.link(o)
    o.data.materials.append(_CMAT[0])
    print("산 벽 덮개 조각 LOD0/1/2 %s, 삼각형 %d" % ("/".join(map(str, nchunk)), len(T)))


# ───────────────────────── 소품 (지오메트리 노드로 복제) ─────────────────────────
SRC = {}


def src(name):
    if name in SRC:
        return SRC[name]
    if not os.path.exists(os.path.join(KIT, name + ".fbx")):
        SRC[name] = None
        return None
    o = kit.load_fbx(name)
    me = o.data
    if len(me.color_attributes) and "Col" not in me.color_attributes:
        me.color_attributes[0].name = "Col"
    SRC[name] = o
    return o


def instancer(name, pts, rots, scl):
    o = src(name)
    if o is None or not len(pts):
        return
    me = bpy.data.meshes.new(name + "_pts")
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", np.asarray(pts, np.float32).ravel())
    a = me.attributes.new("rot", 'FLOAT_VECTOR', 'POINT')
    a.data.foreach_set("vector", np.asarray(rots, np.float32).ravel())
    b = me.attributes.new("scl", 'FLOAT', 'POINT')
    b.data.foreach_set("value", np.asarray(scl, np.float32))
    ob = bpy.data.objects.new(name + "_inst", me)
    sc.collection.objects.link(ob)
    ng = bpy.data.node_groups.new(name + "_gn", 'GeometryNodeTree')
    ng.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi = ng.nodes.new('NodeGroupInput'); go = ng.nodes.new('NodeGroupOutput')
    oi = ng.nodes.new('GeometryNodeObjectInfo'); oi.inputs['Object'].default_value = o; oi.inputs['As Instance'].default_value = True
    oi.transform_space = 'ORIGINAL'
    ip = ng.nodes.new('GeometryNodeInstanceOnPoints')
    ra = ng.nodes.new('GeometryNodeInputNamedAttribute'); ra.data_type = 'FLOAT_VECTOR'; ra.inputs['Name'].default_value = "rot"
    sa = ng.nodes.new('GeometryNodeInputNamedAttribute'); sa.data_type = 'FLOAT'; sa.inputs['Name'].default_value = "scl"
    L = ng.links
    L.new(gi.outputs[0], ip.inputs['Points'])
    L.new(oi.outputs['Geometry'], ip.inputs['Instance'])
    L.new(ra.outputs['Attribute'], ip.inputs['Rotation'])
    L.new(sa.outputs['Attribute'], ip.inputs['Scale'])
    L.new(ip.outputs['Instances'], go.inputs[0])
    mod = ob.modifiers.new("inst", 'NODES')
    mod.node_group = ng
    return ob


def cull_r(rng_, far):
    """LightCuller 기본 규칙: far 가 있으면 그 거리, 없으면 clamp(range × 12, 30, 200) m 에서 꺼진다 (Unity 화면과 같게)"""
    return float(min(max(far, 30.0), 200.0)) if far else float(min(max(rng_ * 12.0, 30.0), 200.0))


def props(cam_u, radius=None):
    """objects.json 의 소품과 trees.json 의 나무. radius 가 있으면 카메라 둘레만"""
    groups = {}
    lights = []
    cx, cz = cam_u[0], cam_u[2]
    for d in OBJ["objects"]:
        p = d["p"]
        if radius and (p[0] - cx) ** 2 + (p[2] - cz) ** 2 > radius ** 2:
            continue
        Mb = rot_b(quat_u(d["q"]))
        g = groups.setdefault(d["a"], ([], [], []))
        g[0].append(tuple(u2b(p))); g[1].append(tuple(Mb.to_euler('XYZ'))); g[2].append(d["s"])
        li = MAN.get(d["a"], {}).get("light")
        if li and (p[0] - cx) ** 2 + (p[2] - cz) ** 2 < cull_r(li.get("range", 8.0), d.get("far") or li.get("far")) ** 2:   # 소품별 far (등대 빛 소품)
            off = Mb @ (Vector(li["offset"]) * d["s"])
            lights.append((u2b(p) + off, li["color"], li["intensity"], li["range"]))
    protos = TREES["prototypes"]
    for t in TREES["instances"]:
        a = protos[int(t[0])]
        x, z, yaw, s = t[1], t[2], t[3], t[4]
        if radius and (x - cx) ** 2 + (z - cz) ** 2 > radius ** 2:
            continue
        y = hsample(x, z) - MAN.get(a, {}).get("sink", 0) * s
        Mb = rot_b(yaw_u(yaw))
        g = groups.setdefault(a, ([], [], []))
        g[0].append((x, z, y)); g[1].append(tuple(Mb.to_euler('XYZ'))); g[2].append(s)
    for a, (p, r, s) in groups.items():
        instancer(a, p, r, s)
    for p in OBJ.get("lights", []):
        if (p["p"][0] - cx) ** 2 + (p["p"][2] - cz) ** 2 < cull_r(p["r"], p.get("far")) ** 2:
            lights.append((u2b(p["p"]), p["c"], p["i"], p["r"]))
    for i, (p, c, inten, rng) in enumerate(lights):
        ld = bpy.data.lights.new("L%d" % i, 'POINT')
        ld.color = c[:3]
        ld.energy = inten * rng * 2.2
        ld.shadow_soft_size = 0.15
        lo = bpy.data.objects.new("L%d" % i, ld)
        lo.location = p
        lo.visible_camera = False        # Unity 점광원처럼 광원 자체는 화면에 보이지 않는다 (보이는 것은 소품의 발광 부품과 밝혀진 땅뿐)
        sc.collection.objects.link(lo)
    print("소품 종류", len(groups), "광원", len(lights))


def grass_np(cam_u, fwd_u, radius=70.0, seed=3):
    rng = np.random.default_rng(seed)
    dets = W["details"]
    imgs = []
    for k in range((len(dets) + 3) // 4):       # detail_0/1 = 풀, detail_2 = 땅 잡동사니 (있을 때)
        img = bpy.data.images.load(os.path.join(DATA, "detail_%d.png" % k))
        img.colorspace_settings.name = 'Non-Color'
        img.alpha_mode = 'CHANNEL_PACKED'
        a = np.array(img.pixels[:], np.float32).reshape(img.size[1], img.size[0], 4)   # Blender: 아래 줄부터 = 남쪽부터
        imgs.append(a)
        bpy.data.images.remove(img)
    cx, cz = cam_u[0], cam_u[2]
    x0, x1 = int(max(0, cx - radius)), int(min(W["size"] - 1, cx + radius))
    z0, z1 = int(max(0, cz - radius)), int(min(W["size"] - 1, cz + radius))
    zz, xx = np.mgrid[z0:z1, x0:x1]
    dx, dz = xx + 0.5 - cx, zz + 0.5 - cz
    dist = np.sqrt(dx * dx + dz * dz)
    f = np.array([fwd_u[0], fwd_u[2]], np.float32)
    f /= np.linalg.norm(f) + 1e-9
    front = (dx * f[0] + dz * f[1]) > -0.45 * dist - 4
    ok = (dist < radius) & front
    total = 0
    for k, d in enumerate(dets):
        v = imgs[k // 4][z0:z1, x0:x1, k % 4]
        expect = v * d["maxPerCell"] * ok
        cnt = np.floor(expect + rng.random(expect.shape)).astype(np.int32)
        n = int(cnt.sum())
        if n == 0:
            continue
        rx = np.repeat(xx.ravel(), cnt.ravel()) + rng.random(n)
        rz = np.repeat(zz.ravel(), cnt.ravel()) + rng.random(n)
        ys = np.array([hsample(a, b) for a, b in zip(rx, rz)], np.float32)
        s = rng.uniform(d["minScale"], d["maxScale"], n)
        yaw = rng.uniform(0, 2 * math.pi, n)
        rots = np.stack([np.zeros(n), np.zeros(n), yaw], 1)
        instancer(d["asset"], np.stack([rx, rz, ys], 1), rots, s)
        total += n
    print("풀", total)


# ───────────────────────── 하늘·조명·안개 ─────────────────────────
def sky_and_light():
    wd = bpy.data.worlds.new("Night")
    sc.world = wd
    wd.use_nodes = True
    nt = wd.node_tree
    bg = nt.nodes["Background"]
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.075, 0.06, 0.13, 1)
    ramp.color_ramp.elements[1].position = 0.45
    ramp.color_ramp.elements[1].color = (0.012, 0.014, 0.035, 1)
    nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    wd.mist_settings.start = 25
    wd.mist_settings.depth = 650
    wd.mist_settings.falloff = 'QUADRATIC'
    sun = bpy.data.lights.new("Moon", 'SUN')
    sun.color = (0.62, 0.7, 1.0)
    sun.energy = 0.55
    sun.angle = math.radians(0.8)
    so = bpy.data.objects.new("Moon", sun)
    so.rotation_euler = Euler((math.radians(58), 0, math.radians(-125)), 'XYZ')   # 북서쪽 위에서
    sc.collection.objects.link(so)
    vl = bpy.context.view_layer
    vl.use_pass_mist = True
    sc.view_settings.view_transform = 'AgX'
    for look in ('AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            sc.view_settings.look = look
            break
        except TypeError:
            pass
    sc.view_settings.exposure = 1.3
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.sample_clamp_indirect = 2.0
    sc.cycles.use_light_tree = True
    # 합성: 안개 + 빛 번짐
    sc.use_nodes = True
    ct = sc.node_tree
    for n in list(ct.nodes):
        ct.nodes.remove(n)
    rl = ct.nodes.new('CompositorNodeRLayers')
    mr = ct.nodes.new('CompositorNodeMapRange')
    mr.inputs['From Min'].default_value = 0.0; mr.inputs['From Max'].default_value = 1.0
    mr.inputs['To Min'].default_value = 0.0; mr.inputs['To Max'].default_value = 0.85
    mr.name = "FogAmount"
    ct.links.new(rl.outputs['Mist'], mr.inputs['Value'])
    mix = ct.nodes.new('CompositorNodeMixRGB')
    mix.inputs[2].default_value = (0.016, 0.014, 0.034, 1)
    ct.links.new(mr.outputs['Value'], mix.inputs['Fac'])
    ct.links.new(rl.outputs['Image'], mix.inputs[1])
    gl = ct.nodes.new('CompositorNodeGlare')
    gl.glare_type = 'FOG_GLOW'; gl.quality = 'HIGH'; gl.threshold = 0.7; gl.size = 8; gl.mix = 0.0
    ct.links.new(mix.outputs['Image'], gl.inputs['Image'])
    out = ct.nodes.new('CompositorNodeComposite')
    ct.links.new(gl.outputs['Image'], out.inputs['Image'])


def camera(pos_u, look_u, fov=55, res=(1280, 720), clip=3000):
    cd = bpy.data.cameras.new("Cam")
    cd.lens_unit = 'FOV'
    cd.sensor_fit = 'VERTICAL'
    cd.angle_y = math.radians(fov)          # 세로 시야각 (Unity 카메라와 같은 기준)
    cd.clip_start = 0.1
    cd.clip_end = clip
    co = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(co)
    p, t = u2b(pos_u), u2b(look_u)
    co.location = p
    d = (t - p).normalized()
    co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    sc.camera = co
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    return co


def eye(x, z, up=1.7):
    return (x, hsample(x, z) + up, z)


VIEW_DEFS = {
    # 이름: (카메라 x, z, 높이(지면 위), 바라볼 x, z, 높이(지면 위), 풀 반지름, 소품 반지름)
    # v2 (월드 압축): 장소 좌표는 worldgen.py 의 POIS·상수와 맞춘다
    "overview": ((1024, -150, 760), (1024, 1080, 0), 0, None),
    "spawn": ((1005, 584, 3.2), (1005, 670, 2.5), 75, 900),
    "graveyard": ((1006, 835, 2.6), (1005, 1002, 5.0), 70, 900),
    "swamp": ((1240, 932, 2.2), (1442, 970, 1.0), 60, 900),
    "cathedral": ((1024, 1191, 2.2), (1012, 1330, 14.0), 60, 900),
    "dragon": ((661, 1007, 2.6), (613, 1050, 3.0), 60, 900),
    "tree": ((1342, 1280, 2.0), (1372, 1335, 7.0), 55, 700),
    "bridge": ((826, 991, 2.2), (788, 1013, 0.0), 55, 700),
    "gate": ((1014, 1547, 2.4), (1012, 1634, 6.0), 55, 700),
    "village": ((1245, 527, 3.0), (1305, 562, 1.5), 60, 700),
    # v3 눈높이(1.7 m) 보기. 자리는 지형 시선으로 장면이 보이는 곳을 골랐다 (scratchpad world_v3_qa/pick_views.py, 장면 좌표가 바뀌면 다시 고른다)
    "fields": ((1000, 496, 1.7), (922, 516, 1.6), 60, 900),        # 제단 남쪽 들판(길에서 45 m 넘게)에서 서쪽: 야영지·초소·사당·농가·무덤·둔덕
    "roadside": ((1030, 1176, 1.7), (1063, 1104, 1.6), 60, 900),   # 납골당 → 대성당 길 위에서 남동쪽: 처형터·사당·가족 묘역·예배당
    "ne_field": ((1395, 1440, 1.7), (1316, 1426, 1.6), 60, 900),   # 북동쪽 들판 (v2 검토 자리): 전장·사당·야영지·초소
    "hamlet": ((843, 916, 1.7), (767, 943, 1.6), 60, 900),         # 묘지 서쪽 길에서 다리 쪽 무리 (처형터·예배당, 묘지·납골당·다리가 보이는 무리)
    "pair": ((1372, 1307, 1.7), (1365, 1228, 1.6), 60, 900),       # 영혼의 고목 남쪽 길: 둔덕·농가·무덤·야영지
    "quiet": ((422, 1378, 1.7), (422, 1458, 1.6), 60, 900),        # 가장 큰 조용한 구역 Q0 가운데 (다음 단계 채움 자리. 남은 휑한 곳 확인)
}
EYE_VIEWS = ["fields", "roadside", "ne_field", "hamlet", "pair", "quiet"]


def eye_view(name):
    """eye_<x>_<z>_<방향>: 땅 + 1.7 m 에서 방향(Unity Y 회전 도)으로, 수평에서 3° 아래"""
    _, x, z, yw = name.split("_")
    x, z, yw = float(x), float(z), math.radians(float(yw))
    d = 100.0
    tx, tz = x + math.sin(yw) * d, z + math.cos(yw) * d
    return ((x, z, 1.7), (tx, tz, None), 70, 900)


def scene_view(kind):
    """scene_<틀>: _scenes.json 에서 그 틀의 첫 장면, 앞(길 쪽) 24 m 눈높이에서 장면 가운데 + 1.5 m 를 본다"""
    sc = json.load(open(os.path.join(WORLD, "_scenes.json")))
    s = next(x for x in sc if x["type"] == kind)
    yw = math.radians(s.get("yaw", 0.0))
    cx, cz = s["p"][0] + math.sin(yw) * 24, s["p"][1] + math.cos(yw) * 24
    print("장면 보기", kind, s["p"], "카메라", (round(cx, 1), round(cz, 1)))
    return ((cx, cz, 1.7), (s["p"][0], s["p"][1], 1.5), 45, 400)


def fog(start, depth, amount):
    sc.world.mist_settings.start = start
    sc.world.mist_settings.depth = depth
    sc.node_tree.nodes["FogAmount"].inputs['To Max'].default_value = amount


def build_view(name):
    if name.startswith("eye_"):
        cpos, cl, grass_r, prop_r = eye_view(name)
    else:
        cpos, cl, grass_r, prop_r = scene_view(name[6:]) if name.startswith("scene_") else VIEW_DEFS[name]
    if name == "overview":
        fog(900, 2600, 0.5)
    else:
        fog(30, 520, 0.85)
    if name == "overview":
        pos = (cpos[0], cpos[2], cpos[1])
        look = (cl[0], 40.0, cl[1])
        res = (1440, 810)
        fov = 34
    else:
        # 같은 장소 이름의 기준 정보가 bridge 처럼 계산된 자리면 world.json 의 pois 를 쓴다
        if name == "bridge":
            bp = next(p for p in W["pois"] if p["id"] == "bridge")["p"]
            cl = (bp[0], bp[2], cl[2])
            cpos = (bp[0] + 30, bp[2] - 22, cpos[2])
        pos = eye(cpos[0], cpos[1], cpos[2])
        if cl[2] is None:                     # eye_*: 수평에서 3° 아래 (100 m 앞 5.2 m 아래)
            look = (cl[0], pos[1] - 100.0 * math.tan(math.radians(3.0)), cl[1])
        else:
            look = eye(cl[0], cl[1], cl[2])
        res = (1280, 720)
        fov = 60 if name.startswith("eye_") else 52
    eye_like = name.startswith(("eye_", "scene_")) or name in EYE_VIEWS
    terrain_for(pos if eye_like else None)
    cliffs(pos)
    camera(pos, look, fov, res)
    props(pos, prop_r)
    if grass_r:
        fwd = (look[0] - pos[0], 0, look[2] - pos[2])
        grass_np(pos, fwd, grass_r)


def clear_dynamic():
    for o in list(sc.objects):
        if o.name.endswith("_inst") or o.name.startswith("L") and o.type == 'LIGHT' and o.name != "Moon" or o.type == 'CAMERA':
            bpy.data.objects.remove(o, do_unlink=True)


water()
sky_and_light()
for v in (VIEWS or list(VIEW_DEFS)):
    clear_dynamic()
    build_view(v)
    sc.render.filepath = PREFIX + v + ".png"
    sc.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)
    print("RENDERED", v, sc.render.filepath, flush=True)
