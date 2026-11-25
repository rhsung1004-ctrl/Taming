# 전후 비교 렌더: 같은 소품의 이전 판과 새 판을 같은 카메라·조명으로 찍어 나란히 붙인다 (판단용)
#   blender -b --python-exit-code 1 -P compare.py -- <이전 폴더> <새 폴더> <이름> <출력 접두사> [near=x,y,z,거리[,방위도,앙각도]]
#                                                  [views=near,mid,game[,back]] [ref=이름[,이름]] [samples=32]
#   결과: <접두사>_near.png (가까이 1~2m), <접두사>_mid.png (중간 거리, 전체), [<접두사>_back.png (뒤에서)]  — 왼쪽 = 이전, 오른쪽 = 새 판
#         <접두사>_game.png (게임 시점: 눈높이 1.7m 카메라, 3m·6m, 밤 달빛 — 월드 룩 도구의 달빛·주변광·노출) — 왼쪽 열 이전, 오른쪽 열 새 판
#   ref=이름: 게임 시점에 이전 폴더의 다른 소품을 옆에 같이 세운다 (새 판이 이전 소품들 사이에서 붕 뜨는지 본다)
#   로그 LUM 줄: 게임 시점 렌더에서 소품이 차지한 화소의 평균 밝기 (화면 sRGB 휘도) — 이전/새 판 밝기 비교
#   near 를 주지 않으면 앞면(-Y) 가운데 높이 55% 를 1.3m 에서 본다.
# 여러 게임 시점 비교를 한 장으로: blender -b -P compare.py -- --sheet <출력.png> <그림1.png> <그림2.png> ...
# 두 폴더 모두 kit.finish 가 내보낸 <이름>.fbx, <이름>_albedo.jpg, <이름>_normal.png 가 있어야 한다.
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]

if argv and argv[0] == "--sheet":
    # 게임 시점 비교 여러 장을 세로로 이어 붙인다 (폭을 맞춰 줄인다)
    from PIL import Image
    out, files = argv[1], argv[2:]
    ims = [Image.open(f).convert('RGB') for f in files if os.path.exists(f)]
    wmax = min(1600, max(im.width for im in ims))
    ims = [im.resize((wmax, round(im.height * wmax / im.width)), Image.LANCZOS) for im in ims]
    sheet = Image.new('RGB', (wmax, sum(im.height for im in ims) + 6 * (len(ims) - 1)), (255, 255, 255))
    y = 0
    for im in ims:
        sheet.paste(im, (0, y)); y += im.height + 6
    sheet.save(out)
    print("SHEET", out, sheet.size)
    sys.exit(0)

import kit

dir_a, dir_b, name, prefix = argv[:4]
opts = dict(a.split("=", 1) for a in argv[4:] if "=" in a)
RES = (960, 720)
SAMPLES = int(opts.get("samples", 32))
VIEWS = opts.get("views", "near,mid,game").split(",")
REFS = [r for r in opts.get("ref", "").split(",") if r]

kit.init(dir_b, samples=SAMPLES)
sc = kit.sc
kit.foliage_mat()
for g in kit.GLOW:
    kit.glow_mat(g)


def load(folder, nm, tag):
    kit.OUT = folder
    o = kit.load_fbx(nm)          # 같은 이름을 두 번 읽어도 LOD0 을 고른다 (kit 에서 고침)
    kit.LOWS.pop(nm, None)
    o.name = "_cmp_%s_%s" % (nm, tag)
    o.data.name = o.name
    o.location = (0, 0, 0)
    o.hide_render = True
    return o


objs = [load(dir_a, name, "a"), load(dir_b, name, "b")]
refs = []
for r in REFS:
    if os.path.exists(os.path.join(dir_a, r + ".fbx")):
        refs.append(load(dir_a, r, "ref"))
kit.OUT = dir_b

# 땅·하늘·조명 (preview.sheet 와 같은 분위기: 차가운 달빛 + 보랏빛 역광 + 아래 채움)
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
ground = bpy.context.object
gm = bpy.data.materials.new("_g"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.022, 0.022, 0.03, 1)
gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
ground.data.materials.append(gm)
w = bpy.data.worlds.new("_w"); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.03, 0.035, 0.07, 1)
dims = objs[1].dimensions
H = max(dims.z, 0.3)
span = max(dims.x, dims.y, H)
studio = []


def light(kind, loc, energy, color, target, size=1.0):
    d = bpy.data.lights.new(kind, kind); d.energy = energy; d.color = color
    if kind == 'AREA':
        d.size = size
    if kind == 'SUN':
        d.angle = math.radians(2)
    o = bpy.data.objects.new(kind, d); sc.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o


c = Vector((0, 0, H * 0.4))
studio.append(light('SUN', (c.x - 5, c.y - 6, 8), 3.2, (0.78, 0.84, 1.0), c))
studio.append(light('AREA', (c.x + span * 0.6 + 2, c.y + 4, H * 1.2 + 1), 400 + span * 60, (0.6, 0.35, 1.0), c, 3))
studio.append(light('AREA', (c.x + 2, c.y - 8, 1.0), 120 + span * 20, (0.4, 0.55, 0.8), c, 4))
cd = bpy.data.cameras.new("_c"); cam = bpy.data.objects.new("_cam", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGB'


def studio_look():
    sc.view_settings.view_transform = 'Filmic'
    sc.view_settings.look = 'Medium High Contrast'
    sc.view_settings.exposure = 0.0


def read_png(p):
    im = bpy.data.images.load(p)
    a = np.empty(im.size[0] * im.size[1] * 4, np.float32); im.pixels.foreach_get(a)
    a = a.reshape(im.size[1], im.size[0], 4)
    bpy.data.images.remove(im)
    return a


def render_to(p):
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    return read_png(p)


def aim(tgt, loc):
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


def show_only(o, also=()):
    for x in objs + refs:
        x.hide_render = not (x is o or x in also)


def save_rgb(arr, path):
    out = bpy.data.images.new("_cmp", arr.shape[1], arr.shape[0], alpha=False)
    out.pixels.foreach_set(arr.ravel())
    out.filepath_raw = path; out.file_format = 'PNG'; out.save()
    bpy.data.images.remove(out)


def shoot(tgt, loc, lens, path):
    cd.lens = lens
    cd.sensor_fit = 'AUTO'
    aim(tgt, loc)
    ims = []
    for i, o in enumerate(objs):
        show_only(o)
        p = path + "_%d.png" % i
        ims.append(render_to(p))
        os.remove(p)
    # 나란히 붙이기 (왼쪽 = 이전, 오른쪽 = 새 판), 가운데 흰 줄
    bar = np.ones((RES[1], 4, 4), np.float32)
    save_rgb(np.concatenate([ims[0], bar, ims[1]], axis=1), path + ".png")
    print("CMP", path + ".png")


# ───────── 게임 시점: 월드 룩 도구(NecroLookTools.ApplyLook)의 달빛·주변광·노출에 맞춘 밤 ─────────
MOON_COL = (0.62, 0.7, 1.0)
MOON_I = 1.25                  # Unity 방향광 세기 (Unity 확산 = albedo × 색 × 세기 × cos, Cycles 해는 /π 라서 π 를 곱한다)
AMB = ((0.2, 0.2, 0.36), (0.17, 0.14, 0.27), (0.07, 0.06, 0.11))     # 주변광 Trilight (하늘, 지평선, 땅)
EXPOSURE = 0.25                # 후처리 노출 (Neutral 톤매핑은 어두운 밤 장면에서 거의 그대로라 Standard 로 흉내)


def night_setup():
    for l in studio:
        l.hide_render = True
    # 주변광: 위·지평선·아래 세 색 그라데이션 하늘 (Unity Trilight 주변광 흉내)
    nt = w.node_tree
    for n in [n for n in nt.nodes if n.name.startswith("_amb")]:
        nt.nodes.remove(n)
    geo = nt.nodes.new('ShaderNodeNewGeometry'); geo.name = "_amb_geo"
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); sep.name = "_amb_sep"
    nt.links.new(geo.outputs['Incoming'], sep.inputs[0])
    rmp = nt.nodes.new('ShaderNodeMapRange'); rmp.name = "_amb_map"
    rmp.inputs['From Min'].default_value = 1.0; rmp.inputs['From Max'].default_value = -1.0   # Incoming 은 바라보는 쪽 반대
    nt.links.new(sep.outputs['Z'], rmp.inputs['Value'])
    cr = nt.nodes.new('ShaderNodeValToRGB'); cr.name = "_amb_ramp"
    e = cr.color_ramp.elements
    e[0].position = 0.0; e[0].color = (*AMB[2], 1)
    e.new(0.5).color = (*AMB[1], 1)
    e[2].position = 1.0; e[2].color = (*AMB[0], 1)
    nt.links.new(rmp.outputs['Result'], cr.inputs['Fac'])
    # 카메라에 보이는 하늘은 어두운 밤하늘, 비추는 빛은 주변광 그라데이션
    lp = nt.nodes.new('ShaderNodeLightPath'); lp.name = "_amb_lp"
    mx = nt.nodes.new('ShaderNodeMixRGB'); mx.name = "_amb_mix"
    nt.links.new(lp.outputs['Is Camera Ray'], mx.inputs['Fac'])
    nt.links.new(cr.outputs['Color'], mx.inputs['Color1'])
    mx.inputs['Color2'].default_value = (0.018, 0.02, 0.045, 1)
    nt.links.new(mx.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    sun = bpy.data.lights.new("_moon", 'SUN'); sun.energy = math.pi * MOON_I; sun.color = MOON_COL; sun.angle = math.radians(1.5)
    so = bpy.data.objects.new("_moon", sun); sc.collection.objects.link(so)
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.035, 0.032, 0.045, 1)
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.view_settings.exposure = EXPOSURE
    return so


def obj_mask(o, also=()):
    """o 가 차지한 화소 (발광 흰색 덮어씌우기로 1 표본 렌더)"""
    em = bpy.data.materials.get("_mask") or bpy.data.materials.new("_mask")
    em.use_nodes = True
    ntm = em.node_tree
    for n in list(ntm.nodes):
        ntm.nodes.remove(n)
    e_ = ntm.nodes.new('ShaderNodeEmission'); e_.inputs['Strength'].default_value = 1.0
    out = ntm.nodes.new('ShaderNodeOutputMaterial'); ntm.links.new(e_.outputs[0], out.inputs['Surface'])
    vl = sc.view_layers[0]
    old = (sc.cycles.samples, ground.hide_render, bg.inputs['Strength'].default_value, sc.view_settings.exposure)
    hid = [x for x in sc.objects if x.type == 'LIGHT' and not x.hide_render]
    for x in hid:
        x.hide_render = True
    sc.cycles.samples = 1; ground.hide_render = True; bg.inputs['Strength'].default_value = 0.0; sc.view_settings.exposure = 0.0
    vl.material_override = em
    show_only(o, also)
    p = os.path.join(os.path.dirname(prefix) or ".", "_mask_tmp.png")
    a = render_to(p); os.remove(p)
    vl.material_override = None
    for x in hid:
        x.hide_render = False
    sc.cycles.samples, ground.hide_render, bg.inputs['Strength'].default_value, sc.view_settings.exposure = old
    return a[..., 0] > 0.5


def game_views():
    """눈높이 1.7m 에서 3m·6m. 왼쪽 열 = 이전, 오른쪽 열 = 새 판. 달빛은 카메라 왼쪽 앞에서 38도 높이로"""
    moon = night_setup()
    cd.sensor_fit = 'VERTICAL'
    cd.angle_y = math.radians(55)                     # Unity 카메라 시야 55도
    az_cam = math.radians(-70)                        # 카메라 방위 (앞면 -Y 를 비스듬히)
    tz = min(H * 0.45, 1.4)
    # 참고용 이전 소품: 카메라에서 볼 때 왼쪽 옆
    side = Vector((-math.sin(az_cam), math.cos(az_cam), 0))
    x0 = max(dims.x, dims.y) * 0.5
    for r in refs:
        rx = max(r.dimensions.x, r.dimensions.y) * 0.5
        r.location = -side * (x0 + rx + 0.25)
        x0 += 2 * rx + 0.25
    rows = []
    for dist in (3.0, 6.0):
        fwd = Vector((math.cos(az_cam), math.sin(az_cam), 0))
        loc = Vector((0, 0, 0)) + fwd * dist
        loc.z = 1.7
        tgt = Vector((0, 0, tz)) - side * (0.0 if not refs else min(1.0, x0 * 0.3))
        aim(tgt, loc)
        # 달: 카메라 쪽에서 왼쪽으로 60도 돈 방위, 38도 높이 (앞면이 비스듬히 밝고 옆면은 주변광)
        ma = az_cam + math.radians(60)
        md = Vector((math.cos(ma) * math.cos(math.radians(38)), math.sin(ma) * math.cos(math.radians(38)), math.sin(math.radians(38))))
        moon.rotation_euler = (-md).to_track_quat('-Z', 'Y').to_euler()
        row = []
        for i, o in enumerate(objs):
            show_only(o, refs)
            p = prefix + "_game_tmp%d.png" % i
            img = render_to(p); os.remove(p)
            m = obj_mask(o)
            lum = img[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            print("LUM", name, ("old", "new")[i], "%.0fm" % dist, "mean %.4f" % (float(lum[m].mean()) if m.any() else 0.0),
                  "p90 %.4f" % (float(np.percentile(lum[m], 90)) if m.any() else 0.0), "px", int(m.sum()))
            row.append(img)
        bar = np.ones((RES[1], 4, 4), np.float32)
        rows.append(np.concatenate([row[0], bar, row[1]], axis=1))
    hbar = np.ones((4, rows[0].shape[1], 4), np.float32)
    # Blender 그림은 아래에서 위로 쌓이므로 3m 줄이 위에 오도록 뒤집어 붙인다
    save_rgb(np.concatenate([rows[1], hbar, rows[0]], axis=0), prefix + "_game.png")
    print("CMP", prefix + "_game.png")


studio_look()
if "near" in VIEWS:
    nv = [float(v) for v in opts.get("near", "").split(",") if v] or [0.0, -dims.y * 0.45, H * 0.55, 1.3]
    nt_ = Vector(nv[:3]); dist = nv[3]
    az = math.radians(nv[4] if len(nv) > 4 else -70.0)    # 카메라 방위 (-90 = 정면 -Y)
    el = math.radians(nv[5] if len(nv) > 5 else 10.0)
    dirv = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    shoot(nt_, nt_ + dirv * dist, 50, prefix + "_near")
if "mid" in VIEWS:
    # 중간 거리 (전체가 화면 높이의 70~80%)
    lens = 45
    vfov = 2 * math.atan(18.0 / lens * RES[1] / RES[0])
    hfov = 2 * math.atan(18.0 / lens)
    tgt = Vector((0, 0, H * 0.48))
    d = max(max(dims.x, dims.y) / (2 * math.tan(hfov / 2)), H / (2 * math.tan(vfov / 2))) * 1.12 + 0.3
    shoot(tgt, tgt + Vector((d * 0.42, -d * 0.9, d * 0.2)).normalized() * d, lens, prefix + "_mid")
if "back" in VIEWS:
    # 뒤(+Y)에서 비스듬히 중간 거리 (뒷면이 밋밋하지 않은지)
    lens = 45
    vfov = 2 * math.atan(18.0 / lens * RES[1] / RES[0])
    hfov = 2 * math.atan(18.0 / lens)
    tgt = Vector((0, 0, H * 0.48))
    d = max(max(dims.x, dims.y) / (2 * math.tan(hfov / 2)), H / (2 * math.tan(vfov / 2))) * 1.12 + 0.3
    shoot(tgt, tgt + Vector((-d * 0.42, d * 0.9, d * 0.2)).normalized() * d, lens, prefix + "_back")
if "game" in VIEWS:
    game_views()
