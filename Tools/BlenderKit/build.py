# 소품 묶음 빌드 실행기
#   blender -b --python-exit-code 1 -P build.py -- <출력 폴더> <묶음 이름> [이름,이름 | all] [preview | nopreview]
# assets_<묶음>.py 에는 다음이 있어야 한다
#   BUILDERS = [("이름", 함수), ...]      함수는 kit.finish(...) 또는 kit.finish_foliage(...)를 불러 내보낸다
#   META = {"이름": {...배치·Unity 설정...}}  (README.md 의 META 항목 참고)
#   PREVIEWS = [("파일 접미사", ["이름", ...], close여부), ...]   (생략하면 전부 한 장 + 각각 가까이)
# 이미 만든 것은 다시 만들지 않고 내보낸 파일을 읽어 미리보기에 쓴다 (이름을 지정하면 그것만 다시 만든다)
import sys, os, json, time, importlib, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import kit, preview

argv = sys.argv[sys.argv.index("--") + 1:]
out, group = argv[0], argv[1]
only = None if len(argv) < 3 or argv[2] in ("all", "") else set(argv[2].split(","))
want_preview = not (len(argv) > 3 and argv[3] == "nopreview")
kit.init(out)
mod = importlib.import_module("assets_" + group)

infos = {}
failed = []
for name, fn in mod.BUILDERS:
    fbx = os.path.join(out, name + ".fbx")
    if only is not None and name not in only:
        if os.path.exists(fbx):
            kit.load_fbx(name)
        continue
    t0 = time.time()
    try:
        fn()
        print("BUILT", name, round(time.time() - t0, 1), "s")
    except Exception:
        traceback.print_exc()
        failed.append(name)
        print("FAILED", name)
# 이번에 만들지 않았어도 이미 있는 것은 미리보기에 넣는다
for name, fn in mod.BUILDERS:
    if name not in kit.LOWS and os.path.exists(os.path.join(out, name + ".fbx")):
        kit.load_fbx(name)

# 목록 파일 (크기·삼각형 수 + META)
man_path = os.path.join(out, "manifest_%s.json" % group)
man = json.load(open(man_path)) if os.path.exists(man_path) else {}
for name, fn in mod.BUILDERS:
    if name in kit.LOWS:
        o = kit.LOWS[name]
        entry = man.get(name, {})
        entry.update({"name": name, "group": group, "size": [round(v, 3) for v in o.dimensions],
                      "tris_lod0": kit.tri_count(o), "meta": getattr(mod, "META", {}).get(name, {})})
        man[name] = entry
json.dump(man, open(man_path, "w"), ensure_ascii=False, indent=1)

if want_preview:
    names = [n for n, _ in mod.BUILDERS if n in kit.LOWS]
    groups = getattr(mod, "PREVIEWS", None)
    if not groups:
        groups = [("all", names, False)] + [(n, [n], True) for n in names]
    for suffix, ns, close in groups:
        ns = [n for n in ns if n in kit.LOWS]
        if not ns:
            continue
        preview.sheet(ns, os.path.join(out, "_pv_%s_%s.png" % (group, suffix)), close=close, samples=40)
print("DONE", group, "failed:", failed)
