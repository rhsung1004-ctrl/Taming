# 묘지 배경 소품 제작 공통 도구 (Blender 4.0, 배경 실행)
# 과정: 도형 조립 → 복셀 리메시로 한 덩어리 → 노이즈로 닳은 표면 → 저폴리 복사본 → 고폴리의 색·굴곡을 텍스처로 굽기 → FBX
import bpy, bmesh, math, random, os
from mathutils import Vector

sc = None
OUT = None
LOWS = {}

def init(out):
    global sc, OUT
    OUT = out
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 20
    sc.cycles.use_denoising = False

def act(o):
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o

def xf(o):
    act(o)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return o

def origin0(o):
    act(o)
    sc.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    return o

def apply_all(o):
    act(o)
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o

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

def torus(R, r, loc=(0, 0, 0), rot=(0, 0, 0), seg=40):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=seg, minor_segments=10, location=loc, rotation=rot)
    return xf(bpy.context.object)

def prism(tri, y0, y1):
    """XZ 평면의 다각형을 Y 방향으로 늘인 기둥 (박공 지붕 등)"""
    n = len(tri)
    verts = [(x, y0, z) for x, z in tri] + [(x, y1, z) for x, z in tri]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    me = bpy.data.meshes.new("prism")
    me.from_pydata(verts, [], faces)
    o = bpy.data.objects.new("prism", me)
    sc.collection.objects.link(o)
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    return o

def join(objs):
    objs = [o for o in objs if o is not None]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    return bpy.context.object

def cut(a, b):
    m = a.modifiers.new('cut', 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.object = b
    m.solver = 'EXACT'
    act(a)
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(b, do_unlink=True)
    return a

def chips(o, points, rng, rmin=0.04, rmax=0.09):
    """모서리가 깨져 나간 자국"""
    for p in points:
        r = rng.uniform(rmin, rmax)
        cut(o, sphere(r, loc=p, scale=(rng.uniform(0.7, 1.3), rng.uniform(0.7, 1.3), rng.uniform(0.7, 1.3)), sub=1,
                      rot=(rng.random() * 3, rng.random() * 3, 0)))
    return o

def sculpt(o, voxel, big, big_scale, small, small_scale, seed=0, carve=()):
    """복셀 리메시로 한 덩어리로 만들고, (새김·깨진 자국을 파낸 뒤) 큰 굴곡 + 잔 굴곡을 준다"""
    origin0(o)
    m = o.modifiers.new('remesh', 'REMESH')
    m.mode = 'VOXEL'
    m.voxel_size = voxel
    apply_all(o)
    for c in carve:
        cut(o, c)
    e = bpy.data.objects.new("noise_origin", None)
    sc.collection.objects.link(e)
    e.location = (seed * 7.3 + 1.1, seed * 3.7 - 2.2, seed * 5.1)
    for strength, scale in ((big, big_scale), (small, small_scale)):
        if strength <= 0:
            continue
        t = bpy.data.textures.new("n", 'CLOUDS')
        t.noise_scale = scale
        t.noise_depth = 4
        d = o.modifiers.new('disp', 'DISPLACE')
        d.texture = t
        d.strength = strength
        d.mid_level = 0.5
        d.texture_coords = 'OBJECT'
        d.texture_coords_object = e
    apply_all(o)
    bpy.data.objects.remove(e, do_unlink=True)
    for p in o.data.polygons:
        p.use_smooth = True
    return o

def flat_shade(o, angle=35):
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.use_auto_smooth = True
    o.data.auto_smooth_angle = math.radians(angle)

def copy(o):
    c = o.copy()
    c.data = o.data.copy()
    sc.collection.objects.link(c)
    return c

def decimated(o, tris):
    c = copy(o)
    n = sum(len(p.vertices) - 2 for p in c.data.polygons)
    if n > tris:
        m = c.modifiers.new('dec', 'DECIMATE')
        m.ratio = tris / n
        apply_all(c)
    for p in c.data.polygons:
        p.use_smooth = True
    return c

# ───────────── 굽기용 재질 (색을 발광으로 내보내 조명 없이 굽는다) ─────────────
def _ramp(nt, src, p0, c0, p1, c1):
    r = nt.nodes.new('ShaderNodeValToRGB')
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

def _mul(nt, a, b):
    m = nt.nodes.new('ShaderNodeMath')
    m.operation = 'MULTIPLY'
    for sock, v in ((m.inputs[0], a), (m.inputs[1], b)):
        if hasattr(v, 'links'):
            nt.links.new(v, sock)
        else:
            sock.default_value = v
    return m.outputs[0]

def _noise(nt, vec, scale, detail=5.0):
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    nt.links.new(vec, n.inputs['Vector'])
    return n.outputs['Fac']

def W(c):
    return (c[0], c[1], c[2], 1.0)

def surface_mat(name, dark, light, edge, moss=0.0, moss_color=(0.10, 0.17, 0.12), dirt=0.6, streak=False, ao_dist=0.3, cracks=1.0, crack_scale=2.6):
    """굽기 원본 재질. 색은 Base Color로, 금·결 같은 잔 굴곡은 Bump로 넣어 노멀맵에 함께 구워지게 한다."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 1.0
    tc = nt.nodes.new('ShaderNodeTexCoord')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    P = tc.outputs['Object']
    PS = P
    if streak:   # 나무껍질: 세로로 길게 늘인 무늬
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (9, 9, 0.9)
        nt.links.new(P, mp.inputs['Vector'])
        PS = mp.outputs['Vector']
    col = _ramp(nt, _noise(nt, PS, 1.7 if not streak else 1.0, 8), 0.3, W(dark), 0.72, W(light))
    # 큰 얼룩: 차가운 쪽과 따뜻한 쪽으로 살짝 색이 갈린다
    col = _mix(nt, 'OVERLAY', 0.5, col, _ramp(nt, _noise(nt, P, 0.7, 2), 0.35, W((0.36, 0.38, 0.56)), 0.65, W((0.6, 0.52, 0.5))))
    # 붓질 같은 얼룩
    vor = nt.nodes.new('ShaderNodeTexVoronoi')
    vor.inputs['Scale'].default_value = 5.5
    nt.links.new(P, vor.inputs['Vector'])
    col = _mix(nt, 'OVERLAY', 0.4, col, _ramp(nt, vor.outputs['Distance'], 0.0, W((0.2, 0.2, 0.26)), 0.8, W((0.8, 0.78, 0.86))))
    grain = _noise(nt, PS, 30, 4)
    col = _mix(nt, 'OVERLAY', 0.45, col, _ramp(nt, grain, 0.3, W((0.25, 0.25, 0.25)), 0.7, W((0.75, 0.75, 0.75))))
    # 틈과 구석은 보랏빛으로 어둡게
    ao = nt.nodes.new('ShaderNodeAmbientOcclusion')
    ao.inputs['Distance'].default_value = ao_dist
    ao.samples = 8
    col = _mix(nt, 'MULTIPLY', 1.0, col, _ramp(nt, ao.outputs['AO'], 0.2, W((0.12, 0.09, 0.2)), 0.92, W((1, 1, 1))))
    # 닳아서 밝아진 모서리, 어두운 홈
    col = _mix(nt, 'MIX', _mul(nt, _ramp(nt, geo.outputs['Pointiness'], 0.515, W((0, 0, 0)), 0.6, W((1, 1, 1))), 0.8), col, W(edge))
    col = _mix(nt, 'MULTIPLY', _mul(nt, _ramp(nt, geo.outputs['Pointiness'], 0.36, W((1, 1, 1)), 0.485, W((0, 0, 0))), 0.75), col, W((0.2, 0.17, 0.28)))
    # 금: 보로노이 칸의 경계선을 일부만 살린다
    height = grain
    if cracks > 0:
        warp = nt.nodes.new('ShaderNodeTexNoise')
        warp.inputs['Scale'].default_value = 3.0
        nt.links.new(P, warp.inputs['Vector'])
        wp = nt.nodes.new('ShaderNodeMixRGB')
        wp.blend_type = 'ADD'
        wp.inputs['Fac'].default_value = 0.35
        nt.links.new(P, wp.inputs['Color1'])
        nt.links.new(warp.outputs['Color'], wp.inputs['Color2'])
        cv = nt.nodes.new('ShaderNodeTexVoronoi')
        cv.feature = 'DISTANCE_TO_EDGE'
        cv.inputs['Scale'].default_value = crack_scale
        nt.links.new(wp.outputs['Color'], cv.inputs['Vector'])
        line = _ramp(nt, cv.outputs['Distance'], 0.0, W((1, 1, 1)), 0.035, W((0, 0, 0)))
        where = _ramp(nt, _noise(nt, P, 1.3, 2), 0.47, W((0, 0, 0)), 0.56, W((1, 1, 1)))
        crack = _mul(nt, _mul(nt, line, where), cracks)
        col = _mix(nt, 'MIX', crack, col, W((0.025, 0.02, 0.045)))
        sub = nt.nodes.new('ShaderNodeMath')
        sub.operation = 'SUBTRACT'
        nt.links.new(_mul(nt, grain, 0.25), sub.inputs[0])
        nt.links.new(crack, sub.inputs[1])
        height = sub.outputs[0]
    # 윗면의 이끼
    if moss > 0:
        sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(geo.outputs['Normal'], sep.inputs[0])
        up = _ramp(nt, sep.outputs['Z'], 0.4, W((0, 0, 0)), 0.85, W((1, 1, 1)))
        patch = _ramp(nt, _noise(nt, P, 3.5, 5), 0.4, W((0, 0, 0)), 0.58, W((1, 1, 1)))
        col = _mix(nt, 'MIX', _mul(nt, _mul(nt, up, patch), moss), col,
                   _ramp(nt, _noise(nt, P, 14, 3), 0.3, W(tuple(c * 0.6 for c in moss_color)), 0.7, W(tuple(c * 1.5 for c in moss_color))))
    # 땅에 닿는 아래쪽은 흙빛
    if dirt > 0:
        sp = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(tc.outputs['Object'], sp.inputs[0])
        col = _mix(nt, 'MIX', _mul(nt, _ramp(nt, sp.outputs['Z'], 0.0, W((1, 1, 1)), 0.4, W((0, 0, 0))), dirt), col, W((0.045, 0.04, 0.06)))
    nt.links.new(col, bsdf.inputs['Base Color'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.9
    bump.inputs['Distance'].default_value = 0.012 if not streak else 0.02
    nt.links.new(height, bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return m

def glow_mat():
    m = bpy.data.materials.get("Glow")
    if m:
        return m
    m = bpy.data.materials.new("Glow")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.5, 0.25, 1, 1)
    b.inputs["Emission Color"].default_value = (0.55, 0.28, 1.0, 1)
    b.inputs["Emission Strength"].default_value = 9
    return m

# ───────────── 굽기와 내보내기 ─────────────
def finish(name, highs, low_parts, glows=(), size=1024, extr=0.03):
    """highs: 굽기 원본들 / low_parts: 저폴리 조각들 (하나로 합쳐 UV를 편다) / glows: 발광 부품"""
    low = join(low_parts)
    origin0(low)
    low.name = name
    low.data.name = name
    low.data.materials.clear()
    act(low)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.012)
    bpy.ops.object.mode_set(mode='OBJECT')

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

    bpy.ops.object.select_all(action='DESELECT')
    for h in highs:
        h.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    for node, img, kind, suffix in ((ta, img_a, 'DIFFUSE', "_albedo.png"), (tn, img_n, 'NORMAL', "_normal.png")):
        nt.nodes.active = node
        if kind == 'DIFFUSE':     # 조명 없이 색만
            bpy.ops.object.bake(type=kind, pass_filter={'COLOR'}, use_selected_to_active=True, cage_extrusion=extr, max_ray_distance=extr * 3, margin=8, use_clear=True)
        else:
            bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=extr, max_ray_distance=extr * 3, margin=8, use_clear=True)
        img.filepath_raw = os.path.join(OUT, name + suffix)
        img.file_format = 'PNG'
        img.save()
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(ta.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])

    for h in highs:
        bpy.data.objects.remove(h, do_unlink=True)
    if glows:
        for g in glows:
            g.data.materials.clear()
            g.data.materials.append(glow_mat())
            flat_shade(g, 20)
        low = join([low] + list(glows))
        low.name = name
    tris = sum(len(p.vertices) - 2 for p in low.data.polygons)
    act(low)
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, name + ".fbx"), use_selection=True, object_types={'MESH'},
                             apply_scale_options='FBX_SCALE_UNITS', bake_space_transform=True, axis_forward='-Z', axis_up='Y',
                             use_mesh_modifiers=True, mesh_smooth_type='OFF', add_leaf_bones=False, bake_anim=False)
    print("ASSET", name, "tris", tris, "tex", size)
    low.location = (1000 + len(LOWS) * 30, 1000, 0)     # 미리보기 장면에서 복제해 쓸 원본은 멀리 치워 둔다
    low.hide_render = True
    LOWS[name] = low
    return low

def place(name, loc, rz=0.0, s=1.0, tilt=(0, 0)):
    src = LOWS[name]
    o = bpy.data.objects.new(name + "_i", src.data)
    sc.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (tilt[0], tilt[1], rz)
    o.scale = (s, s, s)
    return o


def load_fbx(name):
    """내보낸 FBX와 텍스처를 디스크에서 다시 읽는다 (실제 결과물 검증용)"""
    bpy.ops.import_scene.fbx(filepath=os.path.join(OUT, name + ".fbx"))
    o = bpy.context.selected_objects[0]
    act(o)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mat = bpy.data.materials.new(name + "_Main")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    ta = nt.nodes.new('ShaderNodeTexImage'); ta.image = bpy.data.images.load(os.path.join(OUT, name + "_albedo.png"))
    tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = bpy.data.images.load(os.path.join(OUT, name + "_normal.png"))
    tn.image.colorspace_settings.name = 'Non-Color'
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(ta.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    for slot in o.material_slots:
        slot.material = glow_mat() if slot.material and 'Glow' in slot.material.name else mat
    print("LOADED", name, tuple(round(d, 2) for d in o.dimensions))
    o.location = (1000 + len(LOWS) * 30, 1000, 0)
    o.hide_render = True
    LOWS[name] = o
    return o
