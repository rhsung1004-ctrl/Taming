import sys, os, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import kit
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
out, only = argv[0], (argv[1].split(",") if len(argv) > 1 and argv[1] != "all" else None)
preview = argv[2] if len(argv) > 2 else None
kit.init(out)
import assets
for name, fn in assets.BUILDERS:
    if only and name not in only:
        if len(argv) > 3 and os.path.exists(os.path.join(out, name + ".fbx")):
            kit.load_fbx(name)      # 다시 만들지 않는 것은 내보낸 파일을 읽어 쓴다
        continue
    t = time.time()
    fn()
    print("TIME", name, round(time.time() - t, 1))

scene_out = argv[3] if len(argv) > 3 else None
if scene_out:
    import beauty
    beauty.render(out, scene_out)

if preview and preview != "none":
    # 만든 것들을 한 줄로 세워 확인용 렌더
    sc = bpy.context.scene
    x = 0.0
    for name, low in kit.LOWS.items():
        w = max(low.dimensions.x, 1.0)
        kit.place(name, (x + w / 2, 0, 0))
        x += w + 0.6
    bpy.ops.mesh.primitive_plane_add(size=200)
    g = bpy.context.object
    gm = bpy.data.materials.new("g"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.03, 0.03, 0.04, 1)
    g.data.materials.append(gm)
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.1, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.lights.new("sun", 'SUN'); sun.energy = 4.0; sun.color = (0.75, 0.82, 1.0); sun.angle = math.radians(3)
    so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so); so.rotation_euler = (math.radians(62), 0, math.radians(-50))
    cd = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
    h = max(l.dimensions.z for l in kit.LOWS.values())
    dist = max(x * 0.75, h * 1.6) + 2
    cam.location = (x / 2 + dist * 0.25, -dist, h * 0.6 + 0.6)
    cam.rotation_euler = (Vector((x / 2, 0, h * 0.42)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cd.lens = 40
    sc.cycles.samples = 64
    sc.render.resolution_x, sc.render.resolution_y = 1500, 900
    sc.view_settings.view_transform = 'Filmic'
    sc.render.filepath = preview
    bpy.ops.render.render(write_still=True)
