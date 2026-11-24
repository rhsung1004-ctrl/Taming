# 전후 비교 렌더: 같은 소품의 이전 판과 새 판을 같은 카메라·조명으로 찍어 나란히 붙인다 (판단용)
#   blender -b --python-exit-code 1 -P compare.py -- <이전 폴더> <새 폴더> <이름> <출력 접두사> [near=x,y,z,거리[,방위도,앙각도]]
#   결과: <출력 접두사>_near.png (가까이 1~2m), <출력 접두사>_mid.png (중간 거리, 전체)
#   near 를 주지 않으면 앞면(-Y) 가운데 높이 55% 를 1.3m 에서 본다.
# 두 폴더 모두 kit.finish 가 내보낸 <이름>.fbx, <이름>_albedo.jpg, <이름>_normal.png 가 있어야 한다.
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import numpy as np
from mathutils import Vector
import kit

argv = sys.argv[sys.argv.index("--") + 1:]
dir_a, dir_b, name, prefix = argv[:4]
opts = dict(a.split("=", 1) for a in argv[4:] if "=" in a)
RES = (960, 720)
SAMPLES = int(opts.get("samples", 32))

kit.init(dir_b, samples=SAMPLES)
sc = kit.sc
kit.foliage_mat()
for g in kit.GLOW:
    kit.glow_mat(g)


def load(folder):
    kit.OUT = folder
    o = kit.load_fbx(name)
    kit.LOWS.pop(name, None)
    # 두 번째 판을 읽을 때 이름이 겹쳐 "_LOD0.001" 이 되면 load_fbx 가 LOD0 대신 아무 LOD 나 고르므로 이름을 비켜 둔다
    o.name = "_cmp_%s_%d" % (name, len(kit.LOWS) + len(bpy.data.objects))
    o.data.name = o.name
    o.location = (0, 0, 0)
    o.hide_render = True
    return o


objs = [load(dir_a), load(dir_b)]
kit.OUT = dir_b

# 땅·하늘·조명 (preview.sheet 와 같은 분위기: 차가운 달빛 + 보랏빛 역광 + 아래 채움)
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
gm = bpy.data.materials.new("_g"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.022, 0.022, 0.03, 1)
gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
bpy.context.object.data.materials.append(gm)
w = bpy.data.worlds.new("_w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.035, 0.07, 1)
dims = objs[1].dimensions
H = max(dims.z, 0.3)
span = max(dims.x, dims.y, H)


def light(kind, loc, energy, color, target, size=1.0):
    d = bpy.data.lights.new(kind, kind); d.energy = energy; d.color = color
    if kind == 'AREA':
        d.size = size
    if kind == 'SUN':
        d.angle = math.radians(2)
    o = bpy.data.objects.new(kind, d); sc.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


c = Vector((0, 0, H * 0.4))
light('SUN', (c.x - 5, c.y - 6, 8), 3.2, (0.78, 0.84, 1.0), c)
light('AREA', (c.x + span * 0.6 + 2, c.y + 4, H * 1.2 + 1), 400 + span * 60, (0.6, 0.35, 1.0), c, 3)
light('AREA', (c.x + 2, c.y - 8, 1.0), 120 + span * 20, (0.4, 0.55, 0.8), c, 4)
cd = bpy.data.cameras.new("_c"); cam = bpy.data.objects.new("_cam", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = RES
sc.view_settings.view_transform = 'Filmic'
sc.view_settings.look = 'Medium High Contrast'
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGB'


def shoot(tgt, loc, lens, path):
    cd.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    outs = []
    for i, o in enumerate(objs):
        for x in objs:
            x.hide_render = x is not o
        p = path + "_%d.png" % i
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        outs.append(p)
    # 나란히 붙이기 (왼쪽 = 이전, 오른쪽 = 새 판), 가운데 흰 줄
    ims = []
    for p in outs:
        im = bpy.data.images.load(p)
        a = np.empty(im.size[0] * im.size[1] * 4, np.float32); im.pixels.foreach_get(a)
        ims.append(a.reshape(im.size[1], im.size[0], 4))
        bpy.data.images.remove(im)
        os.remove(p)
    bar = np.ones((RES[1], 4, 4), np.float32)
    both = np.concatenate([ims[0], bar, ims[1]], axis=1)
    out = bpy.data.images.new("_cmp", both.shape[1], both.shape[0], alpha=False)
    out.pixels.foreach_set(both.ravel())
    out.filepath_raw = path + ".png"; out.file_format = 'PNG'; out.save()
    bpy.data.images.remove(out)
    print("CMP", path + ".png")


# 가까이 (1~2m)
nv = [float(v) for v in opts.get("near", "").split(",") if v] or [0.0, -dims.y * 0.45, H * 0.55, 1.3]
nt_ = Vector(nv[:3]); dist = nv[3]
az = math.radians(nv[4] if len(nv) > 4 else -70.0)    # 카메라 방위 (-90 = 정면 -Y)
el = math.radians(nv[5] if len(nv) > 5 else 10.0)
dirv = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
shoot(nt_, nt_ + dirv * dist, 50, prefix + "_near")
# 중간 거리 (전체가 화면 높이의 70~80%)
lens = 45
vfov = 2 * math.atan(18.0 / lens * RES[1] / RES[0])
hfov = 2 * math.atan(18.0 / lens)
tgt = Vector((0, 0, H * 0.48))
d = max(max(dims.x, dims.y) / (2 * math.tan(hfov / 2)), H / (2 * math.tan(vfov / 2))) * 1.12 + 0.3
shoot(tgt, tgt + Vector((d * 0.42, -d * 0.9, d * 0.2)).normalized() * d, lens, prefix + "_mid")
