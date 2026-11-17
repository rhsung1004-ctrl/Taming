# 만든 소품으로 묘지 장면을 조립해 분위기 렌더 (Unity 테스트 장면과 같은 배치)
import bpy, math, random, os
from mathutils import Vector
import kit
R = math.radians

def render(tex_dir, out_path):
    sc = bpy.context.scene
    P = kit.place
    rnd = random.Random(7)

    # 땅
    bpy.ops.mesh.primitive_plane_add(size=160, location=(0, 10, 0))
    g = bpy.context.object
    gm = bpy.data.materials.new("Ground"); gm.use_nodes = True
    nt = gm.node_tree; b = nt.nodes["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.95
    tc = nt.nodes.new('ShaderNodeTexCoord'); mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (40, 40, 1)
    nt.links.new(tc.outputs['UV'], mp.inputs['Vector'])
    ta = nt.nodes.new('ShaderNodeTexImage'); ta.image = bpy.data.images.load(os.path.join(tex_dir, "ground_albedo.png"))
    tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = bpy.data.images.load(os.path.join(tex_dir, "ground_normal.png")); tn.image.colorspace_settings.name = 'Non-Color'
    nm = nt.nodes.new('ShaderNodeNormalMap')
    for t in (ta, tn): nt.links.new(mp.outputs['Vector'], t.inputs['Vector'])
    nt.links.new(ta.outputs['Color'], b.inputs['Base Color']); nt.links.new(tn.outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    g.data.materials.append(gm)

    def light(loc, color, watts, radius=0.15):
        d = bpy.data.lights.new("p", 'POINT'); d.energy = watts; d.color = color; d.shadow_soft_size = radius
        o = bpy.data.objects.new("p", d); sc.collection.objects.link(o); o.location = loc

    soul = (0.55, 0.3, 1.0)
    P("altar", (0, 6, 0))
    light((0, 6, 2.6), soul, 520, 0.3)
    for i, name in enumerate(["pillar_a", "pillar_b", "pillar_a", "pillar_a", "pillar_b"]):
        a = i * 2 * math.pi / 5 + 0.3
        P(name, (math.cos(a) * 4.3, 6 + math.sin(a) * 4.3, 0), rz=a + 1.0)
    P("crypt", (0, 25, 0))
    light((0, 21.5, 3.0), (0.3, 1.0, 0.55), 260, 0.3)
    P("arch_ruin", (0, -8.5, 0))
    for (x, y, rz) in [(-3.2, -6, 0.2), (3.2, -1, 2.9), (-3.4, 2, 0.4), (-13, 10, 1.0), (12, 13, 3.6), (-9, -4, 0.3), (15, -2, 2.5)]:
        P("lantern", (x, y, 0), rz=rz)
        lx, ly = x + math.cos(rz) * 0.5, y + math.sin(rz) * 0.5
        light((lx, ly, 2.25), soul, 130, 0.08)
    for sx in (-1, 1):
        for i in range(5):
            P("fence", (sx * 7.5, -9 + i * 3.4, 0), rz=R(90) + R(rnd.uniform(-3, 3)), tilt=(R(rnd.uniform(-3, 3)), 0))
        P("fence", (sx * 4.3, -9.6, 0), rz=R(rnd.uniform(-4, 4)))
    graves = ["grave_slab_a", "grave_slab_b", "grave_cross", "grave_obelisk"]
    n = 0
    while n < 60:
        x, y = rnd.uniform(-30, 30), rnd.uniform(-8, 22)
        if abs(x) < 2.6 and y < 2: continue
        if x * x + (y - 6) ** 2 < 6 ** 2: continue
        if abs(x) < 8 and y > 17: continue
        if abs(abs(x) - 7.5) < 1.2 and y < 8: continue
        P(rnd.choice(graves), (x, y, rnd.uniform(-0.06, 0)), rz=rnd.choice([0, R(180)]) + R(rnd.uniform(-18, 18)) + (R(180) if y > 6 else 0) * 0,
          s=rnd.uniform(0.9, 1.2), tilt=(R(rnd.uniform(-7, 7)), R(rnd.uniform(-7, 7))))
        n += 1
    for i in range(14):
        a = rnd.uniform(0, 2 * math.pi); d = rnd.uniform(12, 34)
        x, y = math.cos(a) * d, 6 + math.sin(a) * d
        if abs(x) < 9 and y > 15: continue
        if abs(x) < 5 and y < 0: continue
        P(rnd.choice(["dead_tree_a", "dead_tree_b"]), (x, y, 0), rz=rnd.uniform(0, 6.28), s=rnd.uniform(0.9, 1.5))
    P("dead_tree_a", (-6.2, -3.5, 0), rz=1.2, s=1.25)
    P("dead_tree_b", (8.5, 3, 0), rz=4.0, s=1.3)
    for i in range(26):
        x, y = rnd.uniform(-28, 28), rnd.uniform(-10, 24)
        if abs(x) < 2.5 and y < 3: continue
        if x * x + (y - 6) ** 2 < 5 ** 2: continue
        P(rnd.choice(["rock_a", "rock_b", "rock_c", "rock_c"]), (x, y, rnd.uniform(-0.15, 0)), rz=rnd.uniform(0, 6.28), s=rnd.uniform(0.5, 1.1))

    # 달빛: 뒤쪽 위에서 비춰 윤곽이 살아나게
    sun = bpy.data.lights.new("moon", 'SUN'); sun.energy = 4.2; sun.color = (0.78, 0.86, 1.0); sun.angle = R(2)
    so = bpy.data.objects.new("moon", sun); sc.collection.objects.link(so); so.rotation_euler = (R(58), 0, R(155))
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    wn = w.node_tree; bg = wn.nodes["Background"]
    tcw = wn.nodes.new('ShaderNodeTexCoord'); sep = wn.nodes.new('ShaderNodeSeparateXYZ'); ramp = wn.nodes.new('ShaderNodeValToRGB')
    wn.links.new(tcw.outputs['Generated'], sep.inputs[0]); wn.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    ramp.color_ramp.elements[0].position = 0.0; ramp.color_ramp.elements[0].color = (0.04, 0.045, 0.11, 1)
    ramp.color_ramp.elements[1].position = 0.55; ramp.color_ramp.elements[1].color = (0.006, 0.006, 0.03, 1)
    # 별
    sn = wn.nodes.new('ShaderNodeTexNoise'); sn.inputs['Scale'].default_value = 1500; sn.inputs['Detail'].default_value = 0
    wn.links.new(tcw.outputs['Generated'], sn.inputs['Vector'])
    sr = wn.nodes.new('ShaderNodeValToRGB')
    sr.color_ramp.elements[0].position = 0.80; sr.color_ramp.elements[0].color = (0, 0, 0, 1)
    sr.color_ramp.elements[1].position = 0.86; sr.color_ramp.elements[1].color = (1.6, 1.7, 2.4, 1)
    wn.links.new(sn.outputs['Fac'], sr.inputs['Fac'])
    add = wn.nodes.new('ShaderNodeMixRGB'); add.blend_type = 'ADD'; add.inputs['Fac'].default_value = 1
    wn.links.new(ramp.outputs['Color'], add.inputs['Color1']); wn.links.new(sr.outputs['Color'], add.inputs['Color2'])
    wn.links.new(add.outputs['Color'], bg.inputs[0]); bg.inputs[1].default_value = 0.6
    w.mist_settings.start = 10; w.mist_settings.depth = 75; w.mist_settings.falloff = 'QUADRATIC'
    bpy.context.view_layer.use_pass_mist = True

    # 합성: 안개 + 번지는 빛
    sc.use_nodes = True
    ct = sc.node_tree; ct.nodes.clear()
    rl = ct.nodes.new('CompositorNodeRLayers')
    fog = ct.nodes.new('CompositorNodeMixRGB'); fog.inputs[2].default_value = (0.04, 0.045, 0.11, 1)
    mul = ct.nodes.new('CompositorNodeMath'); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 0.62
    glare = ct.nodes.new('CompositorNodeGlare'); glare.glare_type = 'FOG_GLOW'; glare.threshold = 1.2; glare.size = 8; glare.quality = 'HIGH'
    comp = ct.nodes.new('CompositorNodeComposite')
    ct.links.new(rl.outputs['Mist'], mul.inputs[0]); ct.links.new(mul.outputs[0], fog.inputs[0])
    ct.links.new(rl.outputs['Image'], fog.inputs[1]); ct.links.new(fog.outputs[0], glare.inputs[0]); ct.links.new(glare.outputs[0], comp.inputs[0])

    cd = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
    sc.cycles.samples = 220
    sc.view_settings.view_transform = 'Filmic'
    sc.view_settings.look = 'Medium High Contrast'
    sc.view_settings.exposure = 0.75
    shots = [("wide", (1.6, -15.5, 1.9), (0, 7, 2.4), 30, (1600, 900)),
             ("graves", (-5.6, -1.6, 1.1), (-1.0, 6.5, 1.3), 35, (1600, 900)),
             ("altar", (4.2, 0.2, 1.5), (0, 6.2, 1.6), 32, (1600, 900))]
    for name, loc, tgt, lens, res in shots:
        cam.location = loc; cd.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.filepath = out_path + "_" + name + ".png"
        bpy.ops.render.render(write_still=True)
        print("RENDERED", name)
