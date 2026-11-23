# 확인용 렌더: 만든 소품을 나란히 세워 극적인 조명으로 찍는다 (표면이 매끈한지·깨졌는지 판단용)
import bpy, math, os
from mathutils import Vector
import kit

def _light(kind, loc, energy, color, target=(0, 0, 1), size=1.0):
    d = bpy.data.lights.new(kind, kind); d.energy = energy; d.color = color
    if kind == 'AREA':
        d.size = size
    if kind == 'SUN':
        d.angle = math.radians(2)
    o = bpy.data.objects.new(kind, d); kit.sc.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o

def sheet(names, path, res=(1600, 900), gap=0.6, samples=64, close=False, cam_height=0.55, lens=45):
    """names 를 한 줄로 세워 찍는다. close=True 면 첫 소품을 가까이서."""
    sc = kit.sc
    for o in list(sc.objects):
        if o.name.startswith("_pv"):
            kit.delete(o)
    x = 0.0
    insts = []
    hmax = 0.0
    for n in names:
        src = kit.LOWS[n]
        w = max(src.dimensions.x, src.dimensions.y, 0.4)
        o = kit.place(n, (x + w / 2, 0, 0))
        o.name = "_pv_" + n
        insts.append(o)
        hmax = max(hmax, src.dimensions.z)
        x += w + gap
    total = x - gap
    bpy.ops.mesh.primitive_plane_add(size=400, location=(total / 2, 0, 0))
    g = bpy.context.object; g.name = "_pv_ground"
    gm = bpy.data.materials.new("_pv_g"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.022, 0.022, 0.03, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    g.data.materials.append(gm)
    w = bpy.data.worlds.new("_pv_w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.035, 0.07, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    c = Vector((total / 2, 0, hmax * 0.4))
    L = [_light('SUN', (c.x - 5, c.y - 6, 8), 3.2, (0.78, 0.84, 1.0), c),                      # 달빛 (왼쪽 위)
         _light('AREA', (c.x + total * 0.6 + 2, c.y + 4, hmax * 1.2 + 1), 400 + total * 60, (0.6, 0.35, 1.0), c, size=3),   # 보랏빛 역광
         _light('AREA', (c.x + 2, c.y - 8, 1.0), 120 + total * 20, (0.4, 0.55, 0.8), c, size=4)]  # 아래 채움
    for o in L:
        o.name = "_pv_" + o.name
    cd = bpy.data.cameras.new("_pv_c"); cam = bpy.data.objects.new("_pv_cam", cd); sc.collection.objects.link(cam); sc.camera = cam
    cd.lens = lens
    hfov = 2 * math.atan(18.0 / lens)              # 36mm 센서 폭 기준
    vfov = 2 * math.atan(18.0 / lens * res[1] / res[0])
    if close:
        f = insts[0]
        w_, h_ = max(f.dimensions.x, f.dimensions.y), f.dimensions.z
        tgt = Vector((f.location.x, 0, h_ * 0.5))
        d = max(w_ / (2 * math.tan(hfov / 2)), h_ / (2 * math.tan(vfov / 2))) * 1.05 + 0.3
        cam.location = tgt + Vector((d * 0.42, -d * 0.9, d * 0.22))
    else:
        tgt = Vector((total / 2, 0, hmax * 0.5))
        d = max(total / (2 * math.tan(hfov / 2)), hmax / (2 * math.tan(vfov / 2))) * 1.08 + 0.5
        cam.location = tgt + Vector((0, -d, d * 0.12))
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.cycles.samples = samples
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = 'Filmic'
    sc.view_settings.look = 'Medium High Contrast'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("PREVIEW", path)
