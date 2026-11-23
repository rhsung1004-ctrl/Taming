# 만든 소품을 Unity 폴더로 옮긴다 (manifest 합치기 + 모델·텍스처 복사 + 이전 버전 정리)
#   python3 publish.py <빌드 출력 폴더> [Unity 소품 폴더]
# 기본 Unity 폴더: Assets/_Necro/Art/Environment/Graveyard
import sys, os, json, glob, shutil

src = sys.argv[1]
dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "..", "Assets", "_Necro", "Art", "Environment", "Graveyard")
dst = os.path.abspath(dst)
os.makedirs(dst, exist_ok=True)

man = {}
for f in sorted(glob.glob(os.path.join(src, "manifest_*.json"))):
    for k, v in json.load(open(f)).items():
        if os.path.exists(os.path.join(src, k + ".fbx")):
            man[k] = v
copied = removed = 0
for name in man:
    for suf in (".fbx", "_albedo.jpg", "_normal.png"):
        p = os.path.join(src, name + suf)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(dst, name + suf))
            copied += 1
    old = os.path.join(dst, name + "_albedo.png")         # 이전 버전 (PNG 색 텍스처)
    if os.path.exists(os.path.join(dst, name + "_albedo.jpg")) and os.path.exists(old):
        os.remove(old)
        meta = old + ".meta"
        if os.path.exists(meta):
            os.remove(meta)
        removed += 1
atlas = os.path.join(src, "foliage_atlas.png")
if os.path.exists(atlas):
    shutil.copy2(atlas, os.path.join(dst, "foliage_atlas.png"))
    copied += 1
json.dump(dict(sorted(man.items())), open(os.path.join(dst, "manifest.json"), "w"), ensure_ascii=False, indent=1)
print("소품", len(man), "개, 파일", copied, "개 복사, 이전 PNG", removed, "개 지움 →", dst)
