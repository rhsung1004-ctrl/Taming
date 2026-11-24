#!/usr/bin/env python3
# 1장 오픈월드 생성기 (버려진 묘지 들판, 지형 2 km × 2 km, 걸어 다니는 범위 1.33 km)
#   python3 worldgen.py <출력 폴더(Ch1)> <소품 manifest.json 또는 manifest_*.json 이 있는 폴더> [씨앗]
# 결과 (규격: SPEC.md)
#   <출력>/Data~/world.json, height.r16, splat_0/1.png, detail_0/1.png, trees.json, objects.json
#   <출력>/Terrain/ground_*  (groundtex.py 가 만든다. 없으면 여기서 부른다)
#   <출력>/map.png, <출력>/_overview.png, <출력>/_scenes.json (확인용, Unity 로 가져가지 않아도 됨)
import sys, os, json, math, time, glob
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from terrain import (fbm, ridged, eroded, ss, ssf, box_blur, catmull, wobble, polyline_field, sample, disk, perlin)

SIZE = 2048
RES = 2049
HMAX = 320.0
T0 = time.time()


def log(*a):
    print("[%5.1fs]" % (time.time() - T0), *a, flush=True)


# ─────────────────────────── 배치도 (Unity 좌표: X 동쪽, Z 북쪽) ───────────────────────────
# v2 (압축): 지형은 2048 m 그대로, 걸을 수 있는 범위를 1.7 km → 1.33 km 로 줄이고 장소를 가운데로 당겼다
# (장소 사이 걷는 거리 150~300 m). 늘어난 바깥 띠(360 m)는 큰 산. 빈 들판은 작은 장면(lay_vignettes)으로 채운다
# 이름 있는 장소. 대사·지역 이름은 2D판 1장(버려진 묘지)과 같은 세계관
POIS = [
    ("altar", "봉인의 제단", (1005, 630), 40),
    ("graveyard", "잊힌 자들의 묘지", (1005, 905), 135),
    ("crypt", "이름 없는 납골당", (1005, 1002), 30),
    ("cathedral", "무너진 대성당", (1012, 1330), 70),
    ("swamp", "안개 늪", (1430, 950), 180),
    ("dragon", "용의 무덤", (605, 1055), 130),
    ("tree", "영혼의 고목", (1372, 1335), 50),
    ("village", "버려진 마을", (1305, 562), 75),
    ("tower", "부서진 망루", (722, 1450), 40),
    ("bridge", "끊어진 개울 다리", None, 30),            # 자리는 개울을 따라 계산
    ("gate", "북쪽 봉인문", (1012, 1634), 50),
    ("forest", "검은 숲", (562, 722), 160),
    ("lake", "달그림자 호수", (790, 495), 78),
]
SPAWN = (1005, 602)           # 제단 앞에서 눈을 뜬다 (북쪽 = 제단을 본다)
BOUNDS = ((360, 360), (1690, 1690))
COMPRESS = 0.78               # 바탕 언덕 = 옛 판(1.7 km) 지형을 가운데로 이만큼 줄인 것 (높이도 같은 배율 → 기울기는 그대로)

ALTAR = (1005, 630)
GRAVE_C, GRAVE_R = (1005, 905), (150, 124)     # 묘지 타원 (X 반지름, Z 반지름)
CRYPT = (1005, 1002)
CATH = (1012, 1330)
SWAMP, SWAMP_R = (1430, 950), 228
DRAGON, DRAGON_R = (605, 1055), 170
TREE = (1372, 1335)
VILLAGE = (1305, 562)
TOWER = (722, 1450)
GATE = (1012, 1634)
FOREST_SW, FOREST_NE = ((562, 722), 185), ((1372, 1335), 140)
LAKE, LAKE_R = (790, 495), 84
CREEK = [(853, 1313), (835, 1212), (812, 1107), (788, 1013), (771, 912), (763, 802), (771, 693), (781, 592), (788, 537)]
BRIDGE_AT = (788, 1013)

# 길: (경유점, 반폭 m). 다리 구간은 개울을 따라 계산해서 끼운다. 순서를 바꾸면 lay_altar·lay_graveyard 의 길 번호도 고친다
ROADS = [
    ([(1005, 580), (1005, 690), (1005, 790), (1005, 905), (1005, 977)], 2.7),                       # 제단 → 묘지 → 납골당
    ([(1005, 977), (1040, 988), (1066, 1035), (1046, 1130), (1016, 1220), (1012, 1272), (1012, 1300)], 2.5),   # 납골당 → 대성당
    ([(1042, 1312), (1072, 1360), (1066, 1450), (1024, 1560), (1012, 1607)], 2.3),                  # 대성당 → 북쪽 봉인문
    ([(847, 907), (925, 903), (1005, 905), (1085, 909), (1128, 907)], 2.0),                         # 묘지 동서 길
    ([(1128, 907), (1185, 916), (1237, 926)], 2.1),                                                  # 묘지 → 안개 늪
    ([(1045, 625), (1140, 598), (1230, 570), (1282, 563)], 2.1),                                    # 제단 → 버려진 마을
    ([(965, 615), (926, 598), (912, 560), (911, 515), (900, 484), (873, 480)], 2.0),               # 제단 → 달그림자 호수 (동쪽 완만한 비탈로 내려가 물가에서 멈춘다)
    ([(626, 1117), (655, 1239), (695, 1350), (717, 1420)], 1.9),                                    # 용의 무덤 → 망루
    ([(1395, 1138), (1380, 1239), (1372, 1310)], 1.9),                                              # 늪 → 고목
    ([(1352, 1355), (1239, 1411), (1122, 1438), (1067, 1440)], 1.9),                                # 고목 → 북쪽 길
    ([(1005, 690), (927, 699), (818, 722), (693, 738), (631, 760)], 1.8),                           # 제단 북쪽 → 검은 숲
    ([(738, 1452), (805, 1432), (872, 1398), (925, 1360), (955, 1334)], 1.9),                       # 망루 → 대성당 서쪽 (v2: 북서쪽 고리)
]
ROAD_NAMES = ["제단→묘지→납골당", "납골당→대성당", "대성당→북쪽 봉인문", "묘지 동서 길", "묘지→안개 늪", "제단→버려진 마을",
              "제단→달그림자 호수", "용의 무덤→망루", "늪→고목", "고목→북쪽 길", "제단 북쪽→검은 숲", "망루→대성당 서쪽",
              "묘지 서쪽→다리 동쪽", "다리 서쪽→용의 무덤"]      # ROADS 순서 + 다리 앞뒤 길 둘 (검사 스크립트가 읽는다)
ROAD_TO_BRIDGE_E = [(847, 907), (826, 960)]     # 묘지 서쪽 → 다리 동쪽 끝 (끝점은 계산)
ROAD_FROM_BRIDGE_W = [(724, 1036), (668, 1048)]  # 다리 서쪽 끝 → 용의 무덤

LAYERS = [  # 이름, 타일 크기(m), 매끈함
    ("grass", 4.0, 0.04), ("moss", 4.5, 0.06), ("dirt", 5.0, 0.05), ("mud", 6.0, 0.32),
    ("rock", 11.0, 0.12), ("path", 4.0, 0.06), ("leaves", 4.0, 0.05), ("ash", 5.0, 0.04)]
DETAILS = [  # 풀 종류, 칸(1 m²)당 최대 포기 수, 크기
    # grass_a 2, grass_dead 1.5 는 임시 값 (풀 한 포기 400~650 삼각형이라 화면 안 삼각형 예산을 넘는다).
    # 포기당 200 삼각형쯤인 저폴리 풀이 나오면 3, 2 로 되돌린다
    ("grass_a", 2, 0.85, 1.35), ("grass_b", 2, 0.8, 1.25), ("grass_dead", 1.5, 0.8, 1.3),
    ("fern_a", 2, 0.75, 1.3), ("weeds", 2, 0.8, 1.35), ("reed", 3, 0.85, 1.25)]

# 죽은 나무(dead_tree_a/b/c) 개수 배율. 지금 LOD 가 둘뿐이라 먼 숲(400 m 너머)이 삼각형을 많이 쓴다.
# 먼 거리용 LOD2 가 생기면 1.0 으로 되돌린다
DEAD_TREE_CUT = 0.7

SOUL = [0.62, 0.35, 1.0]
SPIRIT = [0.45, 0.95, 0.9]
TOXIC = [0.55, 1.0, 0.35]
EMBER = [1.0, 0.5, 0.28]       # 꺼져 가는 모닥불 (차가운 밤 속의 작은 따뜻한 점)

# 장면용 새 소품의 예상 META (크기 = Blender x 폭, y 깊이, z 높이 m). manifest 에 그 소품이 있으면 manifest 를 쓴다.
# 없으면 sub(대체 소품, 크기 배율 또는 None = 그 소품의 META 범위)로 놓고, 예상 META 에 광원이 있는데 대체 소품에 없으면
# objects.json lights 에 같은 광원을 따로 넣는다 (밤에 장면이 보이게). sub 가 None 이면 건너뛴다.
# 소품이 생기면 (BlenderKit 에서 이 이름으로 빌드) 다음 생성부터 자동으로 진짜 소품이 쓰인다
NEW_PROPS = {
    "gallows":          dict(size=[3.6, 1.8, 4.8], footprint=1.9, kind="prop", collider="mesh", sink=0.05, tilt=2, align=False,
                             scale=[0.95, 1.1], light=None, tags=["ruin", "execution"], sub=("dead_tree_c", None)),
    "hanging_cage":     dict(size=[2.0, 1.0, 3.6], footprint=0.9, kind="prop", collider="capsule", sink=0.05, tilt=4, align=False,
                             scale=[0.9, 1.1], light={"offset": [0.7, 0.0, 1.9], "color": SOUL, "intensity": 1.5, "range": 3},
                             tags=["execution", "light"], sub=None),
    "brazier":          dict(size=[1.0, 1.0, 1.3], footprint=0.6, kind="prop", collider="capsule", sink=0.04, tilt=2, align=False,
                             scale=[0.9, 1.1], light={"offset": [0.0, 0.0, 1.25], "color": SPIRIT, "intensity": 7, "range": 9},
                             tags=["light", "path"], sub=("lantern", None)),
    "banner_torn":      dict(size=[1.4, 0.5, 4.2], footprint=0.5, kind="prop", collider="capsule", sink=0.15, tilt=8, align=False,
                             scale=[0.85, 1.15], light=None, tags=["battle"], sub=("bone_spike", None)),
    "sarcophagus":      dict(size=[2.4, 1.1, 1.1], footprint=1.3, kind="prop", collider="box", sink=0.05, tilt=2, align=False,
                             scale=[0.95, 1.1], light=None, tags=["grave"], sub=("coffin", None)),
    "cart_broken":      dict(size=[3.4, 1.8, 1.5], footprint=1.8, kind="prop", collider="mesh", sink=0.08, tilt=6, align=True,
                             scale=[0.9, 1.1], light=None, tags=["camp"], sub=("log_fallen", None)),
    "soul_crystal":     dict(size=[1.4, 1.3, 2.4], footprint=0.9, kind="prop", collider="mesh", sink=0.2, tilt=12, align=False,
                             scale=[0.7, 1.4], light={"offset": [0.0, 0.0, 1.2], "color": SPIRIT, "intensity": 4, "range": 7},
                             tags=["light", "crystal"], sub=("rock_b", 0.6)),
    "skeleton_remains": dict(size=[1.8, 0.8, 0.4], footprint=0.9, kind="scatter", collider="none", sink=0.03, tilt=4, align=True,
                             scale=[0.9, 1.1], light=None, tags=["bone"], sub=("bones_scatter", None)),
    "iron_fence":       dict(size=[3.0, 0.2, 1.7], footprint=1.5, kind="prop", collider="box", sink=0.05, tilt=3, align=False,
                             scale=[0.95, 1.05], light=None, tags=["grave", "path"], sub=("fence", None)),
    "mausoleum_small":  dict(size=[4.4, 5.2, 4.8], footprint=3.0, kind="landmark", collider="mesh", sink=0.06, tilt=0, align=False,
                             scale=[0.95, 1.05], light={"offset": [0.0, -2.4, 1.6], "color": SOUL, "intensity": 3, "range": 5},
                             tags=["grave", "landmark", "light"], sub=("crypt", 0.5)),
    "shrine_roadside":  dict(size=[1.3, 1.0, 2.2], footprint=0.8, kind="prop", collider="box", sink=0.04, tilt=3, align=False,
                             scale=[0.9, 1.1], light={"offset": [0.0, -0.35, 1.2], "color": SOUL, "intensity": 2.5, "range": 5},
                             tags=["grave", "path", "light"], sub=("grave_obelisk", None)),
    "obelisk_chained":  dict(size=[1.5, 1.5, 4.6], footprint=1.0, kind="prop", collider="box", sink=0.1, tilt=3, align=False,
                             scale=[0.9, 1.15], light=None, tags=["ritual"], sub=("grave_obelisk", 1.6)),
    "tent_torn":        dict(size=[3.6, 3.0, 2.4], footprint=2.0, kind="prop", collider="mesh", sink=0.05, tilt=4, align=True,
                             scale=[0.9, 1.1], light=None, tags=["camp"], sub=None),
    "campfire":         dict(size=[1.4, 1.4, 0.5], footprint=0.8, kind="prop", collider="none", sink=0.03, tilt=2, align=True,
                             scale=[0.9, 1.1], light={"offset": [0.0, 0.0, 0.5], "color": EMBER, "intensity": 3.5, "range": 7},
                             tags=["camp", "light"], sub=("rubble", 0.75)),
}


# ─────────────────────────── 높이 ───────────────────────────
class World:
    pass


def flatten(h, cx, cz, r_in, r_out, target=None, strength=1.0):
    rs, cs, d = disk(h.shape, cx, cz, r_out)
    sub = h[rs, cs]
    if target is None:
        target = float(sub[d <= r_in].mean())
    w = ss(-d, -r_out, -r_in) * strength
    h[rs, cs] = sub * (1 - w) + target * w
    return target


def build_height(W):
    log("높이: 바탕")
    ax = np.arange(RES, dtype=np.float32)
    X, Z = np.meshgrid(ax, ax)
    W.X, W.Z = X, Z
    # 바탕 언덕: 옛 판(걸을 수 있는 범위 1.7 km)의 언덕을 지도 가운데로 COMPRESS 배 줄여 쓴다.
    # 높이도 같은 배율로 줄여 기울기는 옛 판과 같다 (길 오르내림·들판 기울기 검사 기준을 그대로 지킨다)
    kc = COMPRESS
    Xo = (1024 + (X - 1024) / kc).astype(np.float32)
    Zo = (1024 + (Z - 1024) / kc).astype(np.float32)
    h = 34 + 14 * fbm(Xo, Zo, 1 / 700, 4, 100) + 22 * (Zo / SIZE)
    h += 16 * ss(fbm(Xo, Zo, 1 / 420, 3, 110), -0.1, 0.6)          # 큰 언덕 덩어리
    h += 15 * fbm(Xo, Zo, 1 / 300, 4, 120)                           # 구릉 (장소 사이의 오르내림)
    h += eroded(Xo, Zo, 1 / 230, 6, 200, 12.0)
    h = h * kc + 34 * (1 - kc)
    del Xo, Zo
    # 가장자리 산 (안쪽 선이 구불구불하게). v2: 바깥 띠가 360 m 라 산이 더 크고 높다
    log("높이: 산")
    wob = 125 * fbm(X, Z, 1 / 520, 3, 300) + 40 * fbm(X, Z, 1 / 150, 3, 310)
    k = 140.0      # 모서리를 둥글게 (부드러운 최소)
    a = -k * np.log(np.exp(-X / k) + np.exp(-(SIZE - X) / k))
    b = -k * np.log(np.exp(-Z / k) + np.exp(-(SIZE - Z) / k))
    # 산이 시작하는 선 = bounds 안쪽 약 35 m (옛 판: 가장자리에서 205 m, bounds 170 m)
    d_edge = -k * np.log(np.exp(-a / k) + np.exp(-b / k)) + 95 - (BOUNDS[0][0] - 170) + wob
    m = ss(-d_edge, -300, -70)
    del a, b
    rid = ridged(X, Z, 1 / 300, 7, 400)
    massif = ss(fbm(X, Z, 1 / 380, 3, 420), -0.25, 0.45)                     # 봉우리 무리 (높은 산줄기와 낮은 안부가 번갈아)
    mount = (m ** 1.25) * (60 + 175 * rid + 75 * massif * rid) + m * eroded(X, Z, 1 / 120, 5, 500, 16.0, k=3.0)
    # 북쪽 봉인문 고갯길 (산 실루엣의 홈). 문 뒤 막다른 벽 너머에서 다시 닫힌다
    gz0 = GATE[1]
    corridor = np.exp(-((X - GATE[0]) / 60.0) ** 2) * ss(Z, gz0 - 162, gz0 - 32) * (1 - ss(Z, gz0 + 58, gz0 + 138))
    mount *= 1 - 0.94 * corridor
    h += mount
    # 아주 높은 봉우리는 둥글게 눌러 HMAX(320 m) 에 잘려 평평해지지 않게 (최대 약 300 m)
    h[:] = np.where(h > 240, 240 + 60 * np.tanh((h - 240) / 60), h)
    del massif
    # 가장자리 벽: 산 노이즈와 상관없이 걸을 수 있는 범위(bounds) 밖을 막는다 (기울기 1.0 넘는 띠가 20 m 넘게 이어진다).
    # 높이는 finish_height 에서 자리 고르기(pads) 뒤에 더한다 (봉인문 자리 고르기가 벽을 깎지 않게)
    gdx = np.abs(X - GATE[0])
    zn = BOUNDS[1][1] - (BOUNDS[1][1] - GATE[1]) * (1 - ss(gdx, 50, 160))      # 북쪽 선은 봉인문 둘레 ±50 m 에서 문 줄까지 당긴다
    dout = np.maximum.reduce([BOUNDS[0][0] - X, X - BOUNDS[1][0], BOUNDS[0][1] - Z, Z - zn])
    calm = (1 - ss(gdx, 60, 110)) * ss(Z, gz0 - 122, gz0 - 62)                 # 문 둘레는 발치 선을 흔들지 않는다
    # 발치 선: 잔 흔들림(±5 m)과 큰 굽이(안쪽으로 0~10 m). 흔들림 폭 합(약 20 m)이 가파른 띠(기울기 > 1, 약 24 m)보다
    # 좁아야 등고선을 따라 비스듬히 벽을 타고 오르는 길이 생기지 않는다
    jit = (7 * fbm(X, Z, 1 / 110, 3, 930) + 10 * ss(fbm(X, Z, 1 / 330, 2, 935), -0.25, 0.35)) * (1 - calm)
    amp = 65 + 15 * fbm(X, Z, 1 / 260, 2, 940)                                   # 벽 높이 55~75 m
    fade = ss(-dout, -140, -60)                                                  # 지도 끝 봉우리에는 더하지 않는다 (320 m 잘림 방지)
    north = Z > gz0 - 122
    gap = np.where(north, ss(gdx, 8.5, 13.0), 1.0)                              # 봉인문 폭만큼 홈 (문 충돌이 막는다)
    zb = Z - (GATE[1] + 150) + jit                                               # 홈 안쪽: 문 뒤 150 m 의 막다른 턱 (문 사이로 하늘이 보이게 멀리)
    # 봉인문 둘레 벼랑은 낮게 (약 40 m): 오르지 못하게 하는 것은 높이가 아니라 기울기(가운데 띠 1.2 넘음)라서,
    # 문 위로 하늘과 뒤쪽 산 실루엣이 보이게 한다
    amp = amp * (1 - 0.4 * calm)
    wf = gap * ss(dout + jit, -5, 25) + (1 - gap) * ss(zb, -5, 25) * north * 0.45
    crest = gap * ss(dout + jit, 18, 50) + (1 - gap) * ss(zb, 18, 50) * north * 0.45   # 벼랑 위는 평평한 대지 대신 들쭉날쭉한 봉우리
    rug = 45 * ridged(X, Z, 1 / 120, 4, 945) * (1 - 0.65 * calm)
    W.wall = ((amp * wf + rug * crest) * fade * (1 - ss(h, 200, 300))).astype(np.float32)
    W.mount = np.maximum(m * (1 - corridor), ss(dout + jit, 0, 25) * np.maximum(gap, ss(zb, 0, 25)))
    del wob, rid, mount, corridor, gdx, zn, dout, calm, jit, amp, fade, north, gap, zb, wf, crest, rug

    log("높이: 지형지물")
    # 대성당 고원 (v2: 반지름을 줄이고 높이도 줄여 오르막 기울기는 옛 판과 같게)
    rs, cs, d = disk(h.shape, CATH[0], CATH[1], 155)
    h[rs, cs] += 22 * ss(-d, -150, -55)
    flatten(h, CATH[0], CATH[1] + 4, 42, 66)
    # 망루 언덕
    rs, cs, d = disk(h.shape, TOWER[0], TOWER[1], 105)
    h[rs, cs] += 17 * ss(-d, -100, -18)
    flatten(h, TOWER[0], TOWER[1], 14, 28)
    # 제단 둔덕
    rs, cs, d = disk(h.shape, ALTAR[0], ALTAR[1], 70)
    h[rs, cs] += 3.5 * ss(-d, -65, -14)
    flatten(h, ALTAR[0], ALTAR[1], 26, 50)
    # 묘지: 완만하게 고른다
    ex = ((X - GRAVE_C[0]) / (GRAVE_R[0] + 32)) ** 2 + ((Z - GRAVE_C[1]) / (GRAVE_R[1] + 32)) ** 2
    hb = box_blur(h, 18)
    wgr = ss(-ex, -1.0, -0.55) * 0.8
    h = h * (1 - wgr) + hb * wgr
    # 마을
    flatten(h, VILLAGE[0], VILLAGE[1], 50, 85, strength=0.75)
    # 고목 둔덕 (멀리서도 솟아 보이게)
    rs, cs, d = disk(h.shape, TREE[0], TREE[1], 105)
    h[rs, cs] += 10 * ss(-d, -100, -22)
    # 용의 무덤 분지 (가장자리는 턱)
    rs, cs, d = disk(h.shape, DRAGON[0], DRAGON[1], DRAGON_R + 60)
    d = d / (1 + 0.2 * fbm(X[rs, cs], Z[rs, cs], 1 / 90, 3, 1010))          # 둥글지 않게
    sub = h[rs, cs]
    sub += -16 * ss(-d, -DRAGON_R, -60) + 6 * np.exp(-((d - DRAGON_R - 5) / 24.0) ** 2)
    hbd = box_blur(sub, 12)
    wf = ss(-d, -125, -50) * 0.7
    h[rs, cs] = sub * (1 - wf) + hbd * wf
    # 검은 숲: 울퉁불퉁한 숲 바닥 (둔덕과 골)
    R0 = FOREST_SW[1]
    rs, cs, d = disk(h.shape, FOREST_SW[0][0], FOREST_SW[0][1], R0 + 5)
    h[rs, cs] += 4 * fbm(X[rs, cs], Z[rs, cs], 1 / 40, 3, 1020) * ss(-d, -(R0 - 5), -(R0 - 95))

    # 늪: 수면 아래위로 오르내리는 섬과 물길
    log("높이: 늪·호수")
    rs, cs, d = disk(h.shape, SWAMP[0], SWAMP[1], SWAMP_R + 20)
    ring = h[rs, cs][(d > SWAMP_R - 10) & (d < SWAMP_R + 10)]
    W.swamp_level = float(np.percentile(ring, 6)) - 3.0
    Xs, Zs = X[rs, cs], Z[rs, cs]
    edge = SWAMP_R + 35 * fbm(Xs, Zs, 1 / 140, 3, 610)
    isl = 1.9 * fbm(Xs, Zs, 1 / 55, 4, 620) + 0.7 * fbm(Xs, Zs, 1 / 14, 3, 630)
    target = W.swamp_level - 0.05 + isl * 1.25
    w = ss(-(d / edge), -1.0, -0.66)
    h[rs, cs] = h[rs, cs] * (1 - w) + target * w
    W.swamp_box = (rs, cs, w)
    # 호수
    rs, cs, d = disk(h.shape, LAKE[0], LAKE[1], LAKE_R + 40)
    ring = h[rs, cs][(d > LAKE_R + 5) & (d < LAKE_R + 25)]
    W.lake_level = float(np.percentile(ring, 6)) - 2.0
    Xs, Zs = X[rs, cs], Z[rs, cs]
    edge = LAKE_R + 18 * fbm(Xs, Zs, 1 / 70, 3, 640)
    # 바닥은 키(1.8 m)보다 얕게: 물에 충돌·헤엄이 없어 깊으면 머리까지 잠겨 걷는다 (가장 깊은 곳 약 1.4 m)
    target = W.lake_level - 0.3 - 0.6 * ss(-(d / edge), -0.95, -0.3) + 0.3 * fbm(Xs, Zs, 1 / 20, 3, 650)
    w = ss(-(d / edge), -1.15, -0.8)
    h[rs, cs] = h[rs, cs] * (1 - w) + target * w
    W.lake_box = (rs, cs, w)
    W.h = h
    carve_creek(W)
    lay_roads(W)
    return W


def carve_creek(W):
    log("높이: 개울")
    h = W.h
    c = wobble(catmull(CREEK, 2.0), 4.0, 1 / 55.0, 701)
    seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    L = s[-1]
    # 다리 자리 = BRIDGE_AT 에 가장 가까운 곡선 점
    ib = int(np.argmin(np.linalg.norm(c - np.array(BRIDGE_AT), axis=1)))
    sb = s[ib]
    bx, bz = c[ib]
    dvec = c[min(ib + 3, len(c) - 1)] - c[max(ib - 3, 0)]
    dvec /= np.linalg.norm(dvec)
    W.creek, W.creek_s, W.creek_dir_b = c, s, dvec
    # 다리 양쪽 둑을 같은 높이로
    W.bridge_bank = flatten(h, bx, bz, 15, 34)
    W.bridge_p = (float(bx), float(bz))
    hb = box_blur(h, 6)
    hs = np.array([sample(hb, x, z) for x, z in c])

    NV = 185                                                   # 북쪽 깊은 골짜기 길이 (v2: 개울이 0.78 배로 짧다)

    def depth(si):
        if si < NV:
            return 2.4 + 7.0 * ssf(NV - si, 0, 120)           # 북쪽은 깊은 골짜기
        return 2.2 if si < L - 160 else 1.6

    D = np.array([depth(si) for si in s])
    raw = hs - D
    Bb = W.bridge_bank - 2.1
    B = raw.copy()
    pool = (s > sb - 38) & (s < sb + 38)
    B[pool] = Bb
    up = s <= sb - 38
    B[up] = np.maximum(raw[up], Bb)
    for i in range(int(np.max(np.nonzero(up)[0])) - 1, -1, -1):
        B[i] = max(B[i], B[i + 1])
    dn = np.nonzero(s >= sb + 38)[0]
    B[dn] = np.minimum(raw[dn], Bb)
    for i in dn[1:]:
        B[i] = min(B[i], B[i - 1])
    # 호수로 들어가는 끝은 호수 바닥보다 조금 낮게
    tail = s > L - 70
    B[tail] = np.minimum(B[tail], W.lake_level - 0.8 + (B[tail] - W.lake_level + 0.8) * np.clip((L - s[tail]) / 70.0, 0, 1))
    B[tail] = np.maximum(B[tail], W.lake_level - 0.5)         # 호수 안 개울 자국이 키보다 깊게 파이지 않게
    W.creek_bed = B

    def widths(si):
        if si < NV:
            dd = depth(si)
            return 3.0, 3.0 + dd * 0.75
        if abs(si - sb) < 45:
            return 2.6, 5.6
        return 2.8, 6.5

    wb = np.array([widths(si)[0] for si in s])
    wt = np.array([widths(si)[1] for si in s])
    (z0, z1), (x0, x1), dist, along = polyline_field(c, 40, RES)
    idx = np.clip(np.searchsorted(s, along), 0, len(s) - 1)
    Bc, wbc, wtc = B[idx].astype(np.float32), wb[idx].astype(np.float32), wt[idx].astype(np.float32)
    sub = h[z0:z1, x0:x1]
    bank = sub - Bc
    # 둑 기울기를 0.5 아래로: 땅이 높은 곳에서는 둑 폭을 넓힌다 (북쪽 깊은 골짜기와 다리 둘레는 그대로)
    wide = ss(along, NV - 30, NV + 30) * ss(np.abs(along - sb), 16, 40)      # 북쪽 골짜기·다리 둘레(교각 자리)에서 부드럽게 바뀐다
    wt_eff = wtc + (wbc + np.maximum(wtc - wbc, np.maximum(bank, 0.5) / 0.5) - wtc) * wide
    prof = Bc + np.where(dist < wbc, 0, (dist - wbc) / np.maximum(wt_eff - wbc, 0.5) * np.maximum(bank, 0.5))
    prof += 0.25 * perlin(np.arange(x1 - x0)[None, :] * 0.2 + x0 * 0.2, np.arange(z1 - z0)[:, None] * 0.2 + z0 * 0.2, 707) * (dist < wbc)
    k = 1.2   # 부드러운 최소
    new = -k * np.log(np.exp(-sub / k) + np.exp(-prof / k))
    w = ss(-dist, -(wt_eff + 10), -wt_eff)
    sub[:] = sub * (1 - w) + np.minimum(sub, new) * w
    W.creek_win = ((z0, z1), (x0, x1))
    W.creek_dist = dist
    W.creek_wt = wtc
    # 다리 아래 물웅덩이 (평평한 바닥 구간)
    W.pool_level = Bb + 0.42
    W.pool_range = (sb - 24, sb + 36)          # 북쪽 끝은 양쪽 둑이 수면 위로 올라오는 자리에서 (턱은 make_pool_mask)


def lay_roads(W):
    log("길")
    h = W.h
    bx, bz = W.bridge_p
    d = W.creek_dir_b
    r = np.array([d[1], -d[0]])                     # 개울에 직각 (동쪽으로 가는 쪽)
    if r[0] < 0:
        r = -r
    W.bridge_axis = r
    east_end = (bx + r[0] * 7.6, bz + r[1] * 7.6)
    west_end = (bx - r[0] * 7.6, bz - r[1] * 7.6)
    roads = list(ROADS)
    roads.append((ROAD_TO_BRIDGE_E + [(bx + r[0] * 20, bz + r[1] * 20), east_end], 1.9))
    roads.append(([west_end, (bx - r[0] * 20, bz - r[1] * 20)] + ROAD_FROM_BRIDGE_W, 1.9))
    W.road_curves = []
    dist = np.full(h.shape, 1e9, np.float32)
    hw_map = np.full(h.shape, 2.0, np.float32)
    for i, (pts, hw) in enumerate(roads):
        c = wobble(catmull(pts, 2.0), 3.2, 1 / 70.0, 900 + i)
        W.road_curves.append((c, hw))
        (z0, z1), (x0, x1), dd, _ = polyline_field(c, hw + 14, RES)
        sub = dist[z0:z1, x0:x1]
        m = dd < sub
        sub[m] = dd[m]
        hw_map[z0:z1, x0:x1][m] = hw
    W.road_dist, W.road_hw = dist, hw_map
    hb = box_blur(h, 9)
    w = ss(-dist, -(hw_map + 7), -hw_map * 0.7)
    # 다리 아래 개울은 메우지 않는다
    rs, cs, dd = disk(h.shape, bx, bz, 12)
    w[rs, cs] *= ss(dd, 7.5, 11.0)
    # 늪·호수 물속은 메우지 않는다
    h[:] = h * (1 - w) + hb * w
    h -= 0.12 * ss(-dist, -hw_map, -hw_map * 0.3)


def finish_height(W, pads):
    log("높이: 자리 고르기·잔 굴곡")
    h = W.h
    for (x, z, rin, rout) in pads:
        t = flatten(h, x, z, rin, rout)
        if (x, z) == tuple(CATH):
            W.cath_level = t
    # 가장자리 벽 (자리 고르기 뒤에 더해야 봉인문 둘레 벽이 깎이지 않는다)
    h += W.wall
    del W.wall
    X, Z = W.X, W.Z
    micro = 0.22 * fbm(X, Z, 1 / 7.0, 3, 800) + 0.5 * fbm(X, Z, 1 / 28.0, 2, 810)
    keep = ss(W.road_dist, 2, 8)
    rs, cs, d = disk(h.shape, W.bridge_p[0], W.bridge_p[1], 24)
    keep[rs, cs] *= ss(d, 10, 22)                     # 다리 둑 높이는 그대로
    for (x, z, rin, rout) in pads:
        rs, cs, d = disk(h.shape, x, z, rout)
        keep[rs, cs] *= ss(d, rin * 0.8, rout)
    h += micro * keep
    # 대성당 정문: 정면 벽 두께 자리(메시 문턱 없음)는 지형을 딛는다. 바깥 윗계단(로컬 0.49 m)에서 한 턱(0.19 m)으로 들어서게
    L = W.cath_level
    zr, xc = int(CATH[1] - 16), int(CATH[0] - 2)
    h[zr, xc:xc + 5] = L + 0.30
    h[zr + 1, xc:xc + 5] = L + 0.15
    # 물을 담는 테두리: 물 평면 상자 안에서 의도하지 않은 낮은 곳을 올린다
    contain(W)
    gz, gx = np.gradient(h)
    W.slope = np.sqrt(gx * gx + gz * gz)
    W.gx, W.gz = gx, gz
    np.clip(h, 0.5, HMAX - 1, out=h)


def contain(W):
    """물 평면 상자 안에서 의도하지 않은 낮은 곳(물이 넘쳐 보일 자리)을 둑처럼 부드럽게 올린다"""
    h = W.h
    for (cx, cz), R, lev, box in ((SWAMP, SWAMP_R + 40, W.swamp_level, W.swamp_box), (LAKE, LAKE_R + 30, W.lake_level, W.lake_box)):
        half = R + 2
        z0, z1 = int(cz - half), int(cz + half)
        x0, x1 = int(cx - half), int(cx + half)
        intended = np.zeros(h.shape, bool)
        rs, cs, w = box
        intended[rs, cs] = w > 0.15
        need = np.zeros(h.shape, np.float32)
        sub = h[z0:z1, x0:x1]
        need[z0:z1, x0:x1] = np.clip(lev + 0.6 - sub, 0, None) * (~intended[z0:z1, x0:x1])
        if need.max() <= 0:
            continue
        P0, P1 = max(0, z0 - 60), min(RES, z1 + 60)
        Q0, Q1 = max(0, x0 - 60), min(RES, x1 + 60)
        sm = box_blur(need[P0:P1, Q0:Q1], 14) * 2.5
        raise_ = np.maximum(need[P0:P1, Q0:Q1], np.minimum(sm, need[P0:P1, Q0:Q1].max()))
        raise_ *= ~intended[P0:P1, Q0:Q1] | (need[P0:P1, Q0:Q1] > 0)
        h[P0:P1, Q0:Q1] += raise_
        log("물 상자 밖 낮은 칸 둑으로 올림", int((need > 0).sum()), "최대 %.1f m" % need.max())


# ─────────────────────────── 배치 ───────────────────────────
def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def quat_axis(ax, ang):
    l = math.sqrt(ax[0] ** 2 + ax[1] ** 2 + ax[2] ** 2) + 1e-12
    s = math.sin(ang / 2)
    return (ax[0] / l * s, ax[1] / l * s, ax[2] / l * s, math.cos(ang / 2))


def yaw_to(dx, dz):
    """앞면(+Z)이 (dx, dz) 를 보게 하는 Unity Y 회전 (도)"""
    return math.degrees(math.atan2(dx, dz))


def quat_mat(q):
    """Unity 쿼터니언 (x, y, z, w) → 3×3 회전 행렬 (열 벡터에 곱한다)"""
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def road_point(W, i, x, z, side, gap):
    """길 i 곡선에서 (x, z) 에 가장 가까운 점 c 와 법선 n → c + n·side·(반폭 + gap) 자리와 길을 보는 yaw"""
    c, hw = W.road_curves[i]
    k = int(np.argmin((c[:, 0] - x) ** 2 + (c[:, 1] - z) ** 2))
    d = c[min(k + 1, len(c) - 1)] - c[max(k - 1, 0)]
    d = d / (np.linalg.norm(d) + 1e-9)
    n = np.array([d[1], -d[0]]) * side
    p = c[k] + n * (hw + gap)
    return float(p[0]), float(p[1]), yaw_to(-n[0], -n[1]), k, len(c)


class Placer:
    def __init__(self, W, meta, rng):
        self.W, self.meta, self.rng = W, meta, rng
        self.objects, self.trees, self.protos = [], [], []
        self.grid = {}
        self.cell = 6.0
        self.big = []           # 발자국이 큰 것 (반지름 > 4 m: 대성당·절벽·문·다리 …). 칸 창 밖에서도 본다
        self._big_a = None
        self.missing = set()
        self.count = {}
        self.stamps = []        # (x, z, r, 종류) 바닥 칠·풀 지우기
        self.subst = {}         # 새 소품 이름 → 대체 소품으로 놓은 수
        self.sub_skip = {}      # 새 소품 이름 → 대체가 없어 건너뛴 수
        self.sub_lights = 0     # 대체 소품에 없어 따로 넣은 광원 수

    def spec(self, a):
        """소품 META: manifest 에 있으면 그것, 없으면 NEW_PROPS 의 예상값 (장면 배치의 간격·광원 판단에 쓴다)"""
        m = self.meta.get(a)
        return m if m is not None else NEW_PROPS.get(a, {})

    def fp(self, a):
        return self.spec(a).get("footprint", 0.5)

    def lit(self, a):
        return bool(self.spec(a).get("light"))

    def reserve(self, x, z, r):
        """장면 자리 둘레를 비워 둔다 (뒤에 놓는 채움 소품·숲 나무가 들어오지 않게)"""
        self.big.append((x, z, r))
        self._big_a = None

    def _put_sub(self, a, x, z, s=None, **kw):
        """manifest 에 없는 새 소품: 대체 소품으로 놓고, 예상 광원이 대체 소품에 없으면 따로 넣는다"""
        spec = NEW_PROPS[a]
        if spec["sub"] is None:
            self.sub_skip[a] = self.sub_skip.get(a, 0) + 1
            return False
        b, k = spec["sub"]
        if b not in self.meta:
            self.missing.add(b)
            return False
        if s is None:
            s2 = None if k is None else k * self.rng.uniform(0.95, 1.05)
        else:
            s2 = (k if k is not None else 1.0) * s
        n0 = len(self.objects)
        if not self.put(b, x, z, s=s2, **kw):
            return False
        self.subst[a] = self.subst.get(a, 0) + 1
        lt = spec.get("light")
        if lt and not self.meta[b].get("light"):
            y0 = self.objects[-1]["p"][1] if len(self.objects) > n0 else self.height(x, z)
            y = y0 + lt["offset"][2] * (s if s is not None else 1.0)
            self.W.lights.append({"p": [round(x, 2), round(float(y), 2), round(z, 2)], "c": list(lt["color"]),
                                  "i": float(lt["intensity"]), "r": float(lt["range"]), "flicker": True})
            self.sub_lights += 1
        return True

    def free(self, x, z, r):
        c = self.cell
        i0, i1 = int((x - r - 8) // c), int((x + r + 8) // c)
        j0, j1 = int((z - r - 8) // c), int((z + r + 8) // c)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for (ox, oz, orr) in self.grid.get((i, j), ()):
                    if (ox - x) ** 2 + (oz - z) ** 2 < (orr + r) ** 2 * 0.85:
                        return False
        if self.big:
            if self._big_a is None:
                self._big_a = np.array(self.big, np.float64)
            b = self._big_a
            if np.any((b[:, 0] - x) ** 2 + (b[:, 1] - z) ** 2 < (b[:, 2] + r) ** 2 * 0.85):
                return False
        return True

    def occupy(self, x, z, r):
        if r > 4.0:              # 큰 발자국은 칸 창(r + 8 m)에 다 들지 않으므로 따로 둔다
            self.big.append((x, z, r))
            self._big_a = None
            return
        k = (int(x // self.cell), int(z // self.cell))
        self.grid.setdefault(k, []).append((x, z, r))

    def height(self, x, z):
        return sample(self.W.h, x, z)

    def normal(self, x, z):
        gx, gz = sample(self.W.gx, x, z), sample(self.W.gz, x, z)
        n = np.array([-gx, 1.0, -gz])
        return n / np.linalg.norm(n)

    def ok_ground(self, x, z, r, road=True, water=True, slope=0.75):
        W = self.W
        (bx0, bz0), (bx1, bz1) = BOUNDS
        if not (bx0 - 120 < x < bx1 + 120 and bz0 - 120 < z < bz1 + 120):
            return False
        if road and sample(W.road_dist, x, z) < sample(W.road_hw, x, z) + r + 0.6:
            return False
        if water and self.under_water(x, z, 0.15):
            return False
        if slope is not None and sample(W.slope, x, z) > slope:
            return False
        return True

    def under_water(self, x, z, margin=0.0):
        W = self.W
        h = self.height(x, z)
        if (x - SWAMP[0]) ** 2 + (z - SWAMP[1]) ** 2 < (SWAMP_R + 40) ** 2 and h < W.swamp_level + margin:
            return True
        if (x - LAKE[0]) ** 2 + (z - LAKE[1]) ** 2 < (LAKE_R + 30) ** 2 and h < W.lake_level + margin:
            return True
        if W.in_pool(x, z) and h < W.pool_level + margin:
            return True
        return False

    def box_ground(self, m, x, z, q, s, margin):
        """회전·기울인 바닥 상자(manifest size, 7×5 격자)의 모든 점이 지형에 닿거나 묻히는 가장 높은 원점 y − margin.
        큰 바위·절벽이 비탈에서 아래쪽이 뜨지 않게 한다 (위쪽은 비탈에 묻힌다)"""
        size = m.get("_size") or [2 * m.get("footprint", 0.5)] * 3
        hx, hz = size[0] * s / 2, size[1] * s / 2         # Blender x, y = Unity x, z
        R = quat_mat(q)
        best = 1e9
        for u in (-1, -2 / 3, -1 / 3, 0, 1 / 3, 2 / 3, 1):
            for v in (-1, -0.5, 0, 0.5, 1):
                wx = R[0, 0] * u * hx + R[0, 2] * v * hz
                wy = R[1, 0] * u * hx + R[1, 2] * v * hz
                wz = R[2, 0] * u * hx + R[2, 2] * v * hz
                best = min(best, self.height(x + wx, z + wz) - wy)
        return best - margin

    def root_drop(self, x, z, rad):
        """둘레 8 점(반지름 rad) 가운데 가장 낮은 지형이 가운데보다 얼마나 낮은지"""
        c = self.height(x, z)
        lo = min(self.height(x + math.cos(k * math.pi / 4) * rad, z + math.sin(k * math.pi / 4) * rad) for k in range(8))
        return c - lo

    def put(self, a, x, z, yaw=None, s=None, tilt=None, align=None, y=None, check=True, r=None,
            road=True, water=True, slope=0.75, stamp=None, occupy=True, ground=None, ground_margin=None, align_max=None):
        """소품 하나. META 기본값(크기·기울기·묻기·경사 맞춤)을 쓴다. 성공하면 True
        align: True/False 또는 0~1 (지형 법선 쪽으로 기울이는 비율), align_max: 기울임 상한(도)
        ground: "box" 면 기울인 바닥 상자 전체가 땅에 닿게 높이를 정한다 (절벽은 기본). ground_margin: 더 묻는 깊이(m)"""
        m = self.meta.get(a)
        if m is None:
            if a in NEW_PROPS:
                return self._put_sub(a, x, z, yaw=yaw, s=s, tilt=tilt, align=align, y=y, check=check, r=r, road=road, water=water,
                                     slope=slope, stamp=stamp, occupy=occupy, ground=ground, ground_margin=ground_margin,
                                     align_max=align_max)
            self.missing.add(a)
            return False
        rng = self.rng
        if s is None:
            lo, hi = m.get("scale", [1, 1])
            s = rng.uniform(lo, hi)
        fp = (m.get("footprint", 0.5) if r is None else r) * s
        kind = m.get("kind", "prop")
        if check:
            if kind == "tree" and a in ("rock_a", "rock_c"):
                slope = 0.4 if slope is None else min(slope, 0.4)      # 기울지 못하는 지형 나무 바위: 비탈에서 아래가 뜬다
            if not self.ok_ground(x, z, fp, road, water, slope):
                return False
            if not self.free(x, z, fp):
                return False
            # 죽은 나무: 뿌리 끝(발자국 반지름) 둘레가 가운데보다 많이 낮으면 뿌리가 뜬다
            if kind == "tree" and a.startswith("dead_tree") and self.root_drop(x, z, fp) > 0.3 + m.get("sink", 0.0) * s:
                return False
        if yaw is None:
            yaw = rng.uniform(0, 360)
        if occupy:
            self.occupy(x, z, fp)
        if stamp:
            self.stamps.append((x, z, fp * stamp[1], stamp[0]))
        elif kind == "scatter":
            self.stamps.append((x, z, max(fp * 0.8, 1.8), "clear"))      # 작은 발광 소품·해골이 낮은 눈높이에서 풀에 가리지 않게
        else:
            self.stamps.append((x, z, fp * 0.8, "clear"))
        self.count[a] = self.count.get(a, 0) + 1
        if kind == "tree":
            if a not in self.protos:
                self.protos.append(a)
            self.trees.append([self.protos.index(a), round(x, 2), round(z, 2), round(yaw % 360, 1) % 360, round(s, 3)])
            return True
        al = align if align is not None else m.get("align", False)
        al = 1.0 if al is True else (0.0 if not al else float(al))
        q = quat_axis((0, 1, 0), math.radians(yaw))
        tmax = m.get("tilt", 0) if tilt is None else tilt
        if tmax > 0:
            t = math.radians(rng.uniform(0, tmax))
            phi = rng.uniform(0, 2 * math.pi)
            q = quat_mul(quat_axis((math.cos(phi), 0, math.sin(phi)), t), q)
        if al > 0:
            n = self.normal(x, z)
            ang = math.acos(max(-1.0, min(1.0, n[1]))) * al
            if align_max is not None:
                ang = min(ang, math.radians(align_max))
            if ang > 1e-4:
                q = quat_mul(quat_axis((n[2], 0.0, -n[0]), ang), q)
        if ground is None and (a.startswith("cliff_") or a == "fence"):
            ground = "box"              # 절벽·울타리: 길쭉해서 가운데 둘레만 보면 비탈에서 한쪽 끝이 뜬다
        if y is None:
            if ground == "box":
                if ground_margin is None:
                    ground_margin = 0.3 if a.startswith("cliff_") else m.get("sink", 0.0) * s
                y = self.box_ground(m, x, z, q, s, ground_margin)
            else:
                hs = [self.height(x, z)]
                if al <= 0:
                    for k in range(6):
                        t = k / 6 * 2 * math.pi
                        hs.append(self.height(x + math.cos(t) * fp * 0.7, z + math.sin(t) * fp * 0.7))
                    y = min(hs) * 0.6 + hs[0] * 0.4
                else:
                    y = hs[0]
                y -= m.get("sink", 0.0) * s
        self.objects.append({"a": a, "p": [round(x, 3), round(float(y), 3), round(z, 3)],
                             "q": [round(v, 5) for v in q], "s": round(s, 3)})
        return True

    def scatter(self, a, n, area, tries=8, **kw):
        """area(rng) → (x, z) 또는 None 을 n 번 시도해 놓는다"""
        got = 0
        for i in range(n * tries):
            if got >= n:
                break
            p = area(self.rng)
            if p is None:
                continue
            if self.put(a, p[0], p[1], **kw):
                got += 1
        return got


def in_disk(c, r, inner=0.0):
    def f(rng):
        a = rng.uniform(0, 2 * math.pi)
        d = math.sqrt(rng.uniform((inner / r) ** 2, 1)) * r
        return (c[0] + math.cos(a) * d, c[1] + math.sin(a) * d)
    return f


def in_mask(W, mask, rng_seed=0):
    """가중치 배열(0~1) 비례로 점을 고른다 (2049 격자)"""
    flat = mask.ravel().astype(np.float64)
    tot = flat.sum()
    if tot <= 0:
        return lambda rng: None
    cdf = np.cumsum(flat)
    cdf /= cdf[-1]

    def f(rng):
        i = int(np.searchsorted(cdf, rng.random()))
        z, x = divmod(i, RES)
        return (x + rng.uniform(-0.5, 0.5), z + rng.uniform(-0.5, 0.5))
    return f


# ─────────────────────────── 지역별 배치 ───────────────────────────
def lay_landmarks(W, P):
    """고정 자리의 큰 구조물. 자리 고르기(pads)를 돌려준다"""
    pads = [(ALTAR[0], ALTAR[1], 11, 26), (CRYPT[0], CRYPT[1], 10, 20), (TREE[0], TREE[1], 11, 22),
            (TOWER[0], TOWER[1], 7, 16), (GATE[0], GATE[1], 13, 28), (VILLAGE[0], VILLAGE[1], 4, 10),
            (CATH[0], CATH[1], 29, 44)]          # 대성당: 0.8·29 = 23.2 m 가 반대각 22.6 m 를 덮어 바닥 밑 잔 굴곡이 없다
    return pads


def place_landmarks(W, P):
    bx, bz = W.bridge_p
    r = W.bridge_axis
    # 다리: 로컬 X(경간) = 길 방향. Unity Y 회전 θ 는 +X 를 (cosθ, 0, −sinθ) 로 돌린다
    th = math.degrees(math.atan2(-r[1], r[0]))
    P.put("bridge_ruin", bx, bz, yaw=th, y=W.bridge_bank - 0.02, check=False, stamp=("path", 1.0))
    P.put("altar", ALTAR[0], ALTAR[1], yaw=180, check=False, stamp=("ash", 1.4))
    P.put("crypt", CRYPT[0], CRYPT[1], yaw=180, check=False, stamp=("dirt", 1.2))
    P.put("cathedral_ruin", CATH[0], CATH[1], yaw=180, y=P.height(*CATH), check=False, stamp=("dirt", 1.1))   # 바닥 판석 윗면이 고른 땅 위로
    P.put("tree_giant", TREE[0], TREE[1], yaw=205, s=1.7, check=False, stamp=("leaves", 1.4))     # 숲 위로 솟은 표지 (약 30 m)
    P.put("watchtower_ruin", TOWER[0], TOWER[1], yaw=150, check=False, stamp=("dirt", 1.3))
    P.put("gate_great", GATE[0], GATE[1], yaw=180, check=False, stamp=("path", 1.0))
    P.put("well", VILLAGE[0], VILLAGE[1], yaw=20, check=False, stamp=("path", 2.5))


def lay_altar(W, P):
    rng = P.rng
    cx, cz = ALTAR
    for i in range(10):                                   # 둘레 기둥 (몇은 부러짐)
        a = (i / 10) * 2 * math.pi + 0.15
        x, z = cx + math.cos(a) * 15.5, cz + math.sin(a) * 15.5
        if i in (2, 7):
            continue                                       # 비어 있는 자리 (남쪽 입구 쪽은 열어 둔다)
        nm = "pillar_b" if i in (1, 4, 8) else "pillar_a"
        P.put(nm, x, z, yaw=yaw_to(cx - x, cz - z), check=False, stamp=("dirt", 1.3))
    for i in range(9):
        a = rng.uniform(0, 2 * math.pi)
        P.put("rubble", cx + math.cos(a) * rng.uniform(9, 22), cz + math.sin(a) * rng.uniform(9, 22))
    for i in range(16):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(4.6, 8)
        P.put("candles", cx + math.cos(a) * d, cz + math.sin(a) * d, road=False)
    for i in range(10):
        P.put("skull", cx + rng.uniform(-14, 14), cz + rng.uniform(-14, 14), road=False)
    for side in (-1, 1):                                   # 제단 앞 길 양옆 (실제 길 곡선 기준)
        x, z, yw, _, _ = road_point(W, 0, cx, cz - 21, side, 1.5)
        P.put("lantern", x, z, yaw=yw, check=False)


def lay_graveyard(W, P):
    rng = P.rng
    cx, cz = GRAVE_C
    rx, rz = GRAVE_R
    kinds = [("grave_slab_a", 30), ("grave_slab_b", 18), ("grave_slab_c", 15), ("grave_cross", 16), ("grave_sunken", 8),
             ("grave_obelisk", 3), ("coffin", 1.5), ("bone_pile", 2)]
    names = [k for k, _ in kinds]
    wts = np.array([w for _, w in kinds], float)
    wts /= wts.sum()
    n_graves = 0
    noise_skip = lambda x, z: perlin(np.array([x / 34.0]), np.array([z / 34.0]), 1201)[0]
    # 묘지 안 작은 길 (흙길): 가운데를 도는 타원 고리와 네 귀퉁이로 나가는 샛길. 묘비 줄이 비켜 가고 바닥을 칠한다
    tt = np.linspace(0, 2 * math.pi, 361)
    ring = np.stack([cx + np.cos(tt) * rx * 0.56, cz + np.sin(tt) * rz * 0.56], 1)
    paths = [wobble(ring, 1.2, 1 / 30.0, 1211)]
    for k, ang in enumerate((0.75, 2.4, 3.9, 5.5)):
        a0 = np.array([cx + math.cos(ang) * rx * 0.56, cz + math.sin(ang) * rz * 0.56])
        a1 = np.array([cx + math.cos(ang) * rx * 0.95, cz + math.sin(ang) * rz * 0.95])
        paths.append(wobble(catmull([tuple(a0), tuple((a0 + a1) / 2 + rng.normal(0, 2.5, 2)), tuple(a1)], 2.0), 1.0, 1 / 25.0, 1220 + k))
    fpts = np.concatenate(paths)

    def on_foot(x, z, w=1.7):
        return np.min((fpts[:, 0] - x) ** 2 + (fpts[:, 1] - z) ** 2) < w * w

    for c in paths:
        for i in range(0, len(c), 2):
            P.stamps.append((float(c[i, 0]), float(c[i, 1]), 1.25, "path"))
    # 납골당·석관 무리: 고리 길 바깥쪽 네 자리 (작은 납골당이 길을 보고, 석관·쇠 울타리·초가 둘레에)
    for k, ang in enumerate((0.35, 2.8, 3.55, 5.95)):
        ux, uz = math.cos(ang), math.sin(ang)
        mx, mz = cx + ux * (rx * 0.56 + 9.5), cz + uz * (rz * 0.56 + 9.5)
        face = yaw_to(-ux, -uz)
        P.put("mausoleum_small", mx, mz, yaw=face + rng.normal(0, 4), slope=0.3, ground="box", stamp=("dirt", 1.3))
        tx_, tz_ = -uz, ux                                     # 고리 길을 따르는 방향
        for off in (-4.6, 4.6):                                # 앞 양옆의 석관 (길이가 고리 길을 따라)
            P.put("sarcophagus", mx + tx_ * off - ux * 3.5, mz + tz_ * off - uz * 3.5, yaw=face + 90 + rng.normal(0, 5),
                  slope=0.45, stamp=("dirt", 1.3))
        for (ot, oo, along) in ((-6.5, 2.0, False), (6.5, 2.0, False), (0.0, 6.8, True)):   # 쇠 울타리 조각 (옆 둘, 뒤 하나)
            P.put("iron_fence", mx + tx_ * ot + ux * oo, mz + tz_ * ot + uz * oo, yaw=face + (0 if along else 90) + rng.normal(0, 4),
                  tilt=4)
        for j in range(2):
            P.put("candles", mx - ux * 4.2 + tx_ * rng.uniform(-1.6, 1.6), mz - uz * 4.2 + tz_ * rng.uniform(-1.6, 1.6), road=False)
    # 큰 석관: 가운데 길 양쪽 (먼저 자리를 잡는다). 광원 있는 grave_tomb 과 광원 없는 석관을 번갈아 (묘지 광원 수 조절)
    for k in range(-4, 5):
        zz = cz + k * 22 + 8
        for side in (-1, 1):
            if rng.random() < 0.7:
                nm = "grave_tomb" if (k + (side > 0)) % 2 == 0 else "sarcophagus"
                P.put(nm, cx + side * 9.5, zz, yaw=90 * -side + rng.normal(0, 3), slope=0.5, stamp=("dirt", 1.4))
    # 등불: 실제 길 곡선(흔들림 포함) 옆에 놓는다. 묘비 줄보다 먼저 자리를 잡는다
    for k in range(-5, 4):                              # 가운데 길 (납골당 앞 12 m 까지)
        zz = cz + k * 26 + 13
        side = 1 if k % 2 else -1
        x, z, yw, _, _ = road_point(W, 0, cx, zz, side, 1.6)
        P.put("lantern", x, z, yaw=yw)
    c3 = W.road_curves[3][0]
    for k in (-1, 1):                                   # 동서 길 (길 끝을 넘는 자리는 건너뛴다)
        for d in (40, 80, 120):
            xq = cx + k * d
            if not (c3[:, 0].min() + 6 < xq < c3[:, 0].max() - 6):
                continue
            x, z, yw, _, _ = road_point(W, 3, xq, cz, 1 if d % 80 else -1, 1.4)
            P.put("lantern", x, z, yaw=yw)
    # 십자로 천사상 둘레와 납골당 앞의 초 무리 (빛 웅덩이)
    # (묘지 동쪽은 80 m 안 광원이 LightCuller 한도 48 개를 넘기 쉬워, 묘비마다 흩던 초를 줄이고 이 두 무리에 모은다)
    for i in range(6):
        a = i / 6 * 2 * math.pi + 0.3
        P.put("candles", cx + math.cos(a) * 1.9, cz + math.sin(a) * 1.9, road=False, check=False)
    for i in range(6):
        P.put("candles", CRYPT[0] + rng.uniform(-4.5, 4.5), CRYPT[1] - rng.uniform(7.5, 9.5), road=False)
    row = 0
    z = cz - rz + 10
    while z < cz + rz - 6:
        row += 1
        x = cx - rx + 4 + rng.uniform(0, 2)
        while x < cx + rx - 4:
            e = ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2
            if e < 0.93 and abs(x - cx) > 6.5 and abs(z - cz) > 5.5 and noise_skip(x, z) > 0.0 and rng.random() > 0.3 \
                    and not on_foot(x, z):
                nm = names[int(rng.choice(len(names), p=wts))]
                yaw = 180 + rng.normal(0, 6)
                gx_, gz_ = x + rng.normal(0, 0.25), z + rng.normal(0, 0.3)
                if P.put(nm, gx_, gz_, yaw=yaw, slope=0.5,
                         stamp=("dirt", 1.6) if nm != "grave_sunken" else ("mud", 1.4)):
                    n_graves += 1
                    if rng.random() < 0.008:
                        P.put("candles", gx_ + rng.uniform(-0.4, 0.4), gz_ - (1.6 if nm == "grave_sunken" else 0.95), road=False)
                    if rng.random() < 0.03:
                        P.put("skull", gx_ + rng.uniform(-0.8, 0.8), gz_ - rng.uniform(0.8, 1.5) - (0.7 if nm == "grave_sunken" else 0), road=False)
            x += rng.uniform(2.0, 2.9)
        z += 3.3 + rng.uniform(-0.2, 0.3)
    # 울타리: 타원 둘레 (군데군데 무너짐). 남쪽 정문, 동·서쪽 길 자리는 비운다
    # 둘레 길이로 고르게 나눈다 (타원 각도로 나누면 동·서 끝에서 울타리끼리 겹친다)
    tt = np.linspace(0, 2 * math.pi, 4001)
    ex_, ez_ = cx + np.cos(tt) * (rx + 8), cz + np.sin(tt) * (rz + 8)
    arc = np.concatenate([[0], np.cumsum(np.hypot(np.diff(ex_), np.diff(ez_)))])
    n = int(arc[-1] / 3.6)
    for i in range(n):
        t = float(np.interp(i / n * arc[-1], arc, tt))
        x, z = cx + math.cos(t) * (rx + 8), cz + math.sin(t) * (rz + 8)
        tx, tz = -math.sin(t) * (rx + 8), math.cos(t) * (rz + 8)
        if sample(W.road_dist, x, z) < 6:
            continue
        if rng.random() < 0.16:
            continue
        th = math.degrees(math.atan2(-tz, tx))           # 로컬 X 를 접선 방향으로
        P.put("fence", x, z, yaw=th, check=False, tilt=3 if rng.random() < 0.8 else 9, stamp=("dirt", 0.7))
    P.put("fence_gate", cx, cz - rz - 8, yaw=180, check=False, stamp=("path", 1.0))
    # 가운데 십자로의 천사상, 납골당 앞 사신상
    P.put("statue_angel", cx, cz, yaw=180, check=False, stamp=("path", 3.0))
    for side in (-1, 1):
        P.put("statue_reaper", CRYPT[0] + side * 8.5, CRYPT[1] - 9, yaw=180, check=False, stamp=("path", 1.5))
        P.put("lantern", CRYPT[0] + side * 4.5, CRYPT[1] - 14, yaw=180, check=False)
    # 고목·덤불·해골
    area = lambda rng: (cx + rng.uniform(-rx, rx), cz + rng.uniform(-rz, rz))
    P.scatter("dead_tree_a", 5, area)
    P.scatter("dead_tree_c", 4, area)
    P.scatter("bush_dead", 28, area)
    def ring(rng):
        t = rng.uniform(0, 2 * math.pi)
        return (cx + math.cos(t) * (rx + rng.uniform(4, 14)), cz + math.sin(t) * (rz + rng.uniform(4, 14)))
    P.scatter("bramble", 22, ring)
    P.scatter("skull", 36, area)
    P.scatter("bone_pile", 9, area)
    log("묘비", n_graves)


def lay_cathedral(W, P):
    rng = P.rng
    cx, cz = CATH
    for side in (-1, 1):
        P.put("statue_angel", cx + side * 9, cz - 25, yaw=180 + side * 12, check=False, stamp=("path", 1.4))
        P.put("lantern", cx + side * 4.6, cz - 23, yaw=180, check=False)
        P.put("pillar_a", cx + side * 15, cz - 21, yaw=180, check=False)
    # 고원 가장자리의 무너진 담과 기둥
    for i in range(26):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(26, 50)
        x, z = cx + math.cos(a) * d, cz + math.sin(a) * d
        nm = ["wall_ruin_a", "wall_ruin_b", "pillar_b", "pillar_a", "rubble", "arch_ruin"][i % 6]
        # 앞면이 바깥을 보고 긴 축(로컬 X)이 둘레를 따른다
        P.put(nm, x, z, yaw=yaw_to(x - cx, z - cz) + rng.normal(0, 15), slope=0.6, stamp=("dirt", 1.2))
    P.scatter("rubble", 30, in_disk((cx, cz), 48, 20))
    # 본당 안 촛불: 바닥 판 위 정해진 자리 (가운데 통로 양옆 줄과 제단 앞). yaw 180 이라 로컬 −z(제단 쪽) = 월드 북쪽
    floor = W.cath_level + 0.06
    # (메쉬 바닥 판 높이 지도에서 잔해·아치 기둥이 없는 칸만 골랐다)
    for (lx, lz) in ((0.3, -13.8), (2.0, -14.0), (3.5, -13.4), (-2.6, -5.6), (2.6, -5.6),
                     (-2.6, 6.0), (2.6, 6.0), (-2.6, 12.5), (2.0, 12.8)):
        x, z = cx - lx, cz - lz
        P.put("candles", x, z, y=max(P.height(x, z), floor) - 0.02, check=False)
    # 둘레 무덤: 다가오는 남쪽 길을 본다
    for nm, n in (("grave_slab_c", 14), ("grave_cross", 10)):
        area = in_disk((cx, cz), 70, 30)
        got = 0
        for i in range(n * 8):
            if got >= n:
                break
            x, z = area(rng)
            if P.put(nm, x, z, yaw=yaw_to(cx - x, cz - 60 - z) + rng.normal(0, 8)):
                got += 1
    P.put("stair_ruin", cx - 34, cz - 4, yaw=90, slope=None)


def lay_village(W, P):
    rng = P.rng
    cx, cz = VILLAGE
    houses = [(-28, 18, 15), (22, 24, -10), (34, -14, 30), (-20, -26, 5), (-48, -4, 80), (6, 46, -25)]
    for hx, hz, rot in houses:
        x0, z0 = cx + hx, cz + hz
        a = math.radians(rot)
        ux, uz = math.cos(a), -math.sin(a)       # 집의 로컬 X
        vx, vz = math.sin(a), math.cos(a)        # 로컬 Z
        wdt, dep = 9.2, 6.8
        for side, (ox, oz, ln, along) in enumerate([(0, dep / 2, wdt, 'x'), (0, -dep / 2, wdt, 'x'), (wdt / 2, 0, dep, 'z'), (-wdt / 2, 0, dep, 'z')]):
            if rng.random() < 0.25:
                continue
            px, pz = x0 + ux * ox + vx * oz, z0 + uz * ox + vz * oz
            yaw = rot + (0 if along == 'x' else 90) + (180 if rng.random() < 0.5 else 0)
            nm = "wall_ruin_a" if rng.random() < 0.6 else "wall_ruin_b"
            P.put(nm, px, pz, yaw=yaw, check=False, stamp=("dirt", 1.3))
        for k in range(3):
            P.put("rubble", x0 + rng.uniform(-5, 5), z0 + rng.uniform(-4, 4), road=False)
        if rng.random() < 0.5:
            P.put("pillar_b", x0 + ux * wdt / 2 + vx * dep / 2, z0 + uz * wdt / 2 + vz * dep / 2, check=False)
        for k in range(int(rng.integers(2, 4))):         # 무너진 집 안의 촛불 (누군가 아직 들르는 듯)
            P.put("candles", x0 + rng.uniform(-1.8, 1.8), z0 + rng.uniform(-1.5, 1.5), road=False)
    for k in range(10):
        a = k / 10 * 2 * math.pi
        x, z = cx + 60 * math.cos(a), cz + 50 * math.sin(a)
        tx, tz = -math.sin(a) * 60, math.cos(a) * 50
        if rng.random() < 0.6:
            P.put("fence", x, z, yaw=math.degrees(math.atan2(-tz, tx)), tilt=6)      # 로컬 X 를 둘레 접선으로
    # v2: 마을 어귀(서쪽 길 끝)의 부서진 수레와 교수 새장, 우물가의 화로
    rx_, rz_, ryw, _, _ = road_point(W, 5, cx - 30, cz, 1, 3.0)
    P.put("cart_broken", rx_, rz_, yaw=ryw + 70, stamp=("dirt", 1.2))
    P.put("hanging_cage", cx - 40, cz + 22, yaw=yaw_to(1, -0.3))
    P.put("brazier", cx - 4.5, cz + 3.0)
    P.scatter("stump", 6, in_disk((cx, cz), 68, 20))
    P.scatter("log_fallen", 3, in_disk((cx, cz), 68, 20))
    P.scatter("bush_dead", 16, in_disk((cx, cz), 72))
    P.scatter("bramble", 12, in_disk((cx, cz), 76, 30))
    P.put("lantern", cx + 5, cz - 6, yaw=200, check=True)
    P.put("lantern", cx - 6, cz + 5, yaw=20, check=True)
    P.put("lantern", cx + 2.6, cz + 2.2, yaw=yaw_to(-2.6, -2.2))          # 우물 옆
    for i in range(2):                                                    # 집 사이를 떠도는 영혼 빛
        hx, hz, _ = houses[int(rng.integers(0, len(houses)))]
        x, z = cx + hx + rng.uniform(-3, 3), cz + hz + rng.uniform(-3, 3)
        W.lights.append({"p": [round(x, 2), round(P.height(x, z) + rng.uniform(1.8, 2.8), 2), round(z, 2)],
                         "c": SPIRIT, "i": 4.0, "r": 9.0, "flicker": True})
    # 마을 묘지 (작은 울타리 안)
    gx, gz = cx + 55, cz + 50
    for i in range(14):
        P.put(["grave_slab_a", "grave_cross", "grave_slab_b"][i % 3], gx + (i % 5) * 2.4 - 5, gz + (i // 5) * 3.2, yaw=180 + rng.normal(0, 8))


def lay_swamp(W, P):
    rng = P.rng
    cx, cz = SWAMP
    lev = W.swamp_level
    area = in_disk(SWAMP, SWAMP_R - 20)
    # 돌 징검다리 (나무 다리 대신 rock_flat): 늪 길 끝에서 섬을 건너 고목 길로, 그리고 남쪽 섬으로.
    # 윗면이 수면 위 약 0.12 m, 밑면은 바닥에 묻히는 깊이(0.5 m 안)에만 놓는다. 물 밖은 걷는 땅이라 건너뛴다
    road_end = W.road_curves[4][0][-1]
    tree_start = W.road_curves[8][0][0]
    chains = [[tuple(road_end), (cx - 70, cz + 40), (cx + 5, cz + 95), tuple(tree_start)],
              [tuple(road_end), (cx - 60, cz - 30), (cx + 10, cz - 95), (cx + 95, cz - 120)],
              [(cx - 70, cz + 40), (cx + 10, cz + 5), (cx + 110, cz - 10)]]
    n_step = 0
    for k, ch in enumerate(chains):
        c = wobble(catmull(ch, 1.0), 4.0, 1 / 40.0, 1601 + k)
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        s_ = np.concatenate([[0], np.cumsum(seg)])
        t = 0.0
        while t < s_[-1]:
            x = float(np.interp(t, s_, c[:, 0])) + rng.normal(0, 0.3)
            z = float(np.interp(t, s_, c[:, 1])) + rng.normal(0, 0.3)
            dx_ = float(np.interp(t + 1, s_, c[:, 0])) - float(np.interp(t - 1, s_, c[:, 0]))
            dz_ = float(np.interp(t + 1, s_, c[:, 1])) - float(np.interp(t - 1, s_, c[:, 1]))
            dep = lev - P.height(x, z)
            sc = float(np.clip((dep + 0.22) / 0.8, 0.55, 0.9))
            if not (0.04 < dep < 0.5) or W.in_pool(x, z):
                t += 1.0
                continue
            # 로컬 X(긴 축 3.5 m)가 길을 가로지르게: 길 방향으로는 짧은 축(2.6 m × 크기)만 차지한다
            yw = math.degrees(math.atan2(-dx_, -dz_)) + rng.normal(0, 12)
            if P.put("rock_flat", x, z, yaw=yw, s=sc, y=lev + 0.12 - 0.8 * sc, tilt=3, align=False, check=False, r=0.7, stamp=("mud", 0.6)):
                n_step += 1
            t += 2.6 * sc + rng.uniform(0.45, 0.8)
    log("늪 징검돌", n_step)
    # 물 위의 연꽃: 무리 지어 수면 높이에 띄운다 (빛 웅덩이가 군데군데)
    got = 0
    for k in range(400):
        if got >= 72:
            break
        x0, z0 = area(rng)
        if not (lev - 1.4 < P.height(x0, z0) < lev - 0.3):
            continue
        for j in range(int(rng.integers(5, 10))):
            a_ = rng.uniform(0, 2 * math.pi)
            d_ = math.sqrt(rng.random()) * 4.5
            x, z = x0 + math.cos(a_) * d_, z0 + math.sin(a_) * d_
            hh = P.height(x, z)
            if lev - 1.4 < hh < lev - 0.15 and P.free(x, z, 0.5):
                P.put("lotus_glow", x, z, y=lev + 0.01, align=False, tilt=0, check=False)
                got += 1
    # 물 밖 (섬·물가). v2: 늪이 작아져(반지름 0.76 배) 개수도 줄였다
    dry = lambda rng: (lambda p: p if P.height(*p) > lev + 0.1 else None)(area(rng))
    P.scatter("dead_tree_b", 85, dry, water=True)
    P.scatter("dead_tree_c", 40, dry)
    P.scatter("roots", 30, dry)
    P.scatter("log_fallen", 22, dry)
    P.scatter("stump", 26, dry)
    P.scatter("mushroom_toxic", 44, dry)
    P.scatter("bush_dead", 40, dry)
    P.scatter("rock_flat", 10, dry)
    P.scatter("grave_sunken", 14, dry)
    P.scatter("grave_slab_c", 8, dry)
    P.scatter("skeleton_remains", 6, dry)
    # 물속에 선 고목 (뿌리가 잠김): 물 위에서도 자리를 차지
    for i in range(220):
        x, z = area(rng)
        if lev - 1.0 < P.height(x, z) < lev and P.free(x, z, 1.5):
            P.put("dead_tree_b", x, z, check=False)
    # 섬의 가라앉은 사당 (빛나는 수정과 초)
    for k in range(60):
        x, z = dry(rng) or (None, None)
        if x is None or P.height(x, z) < lev + 0.4 or (x - cx) ** 2 + (z - cz) ** 2 > (SWAMP_R * 0.7) ** 2:
            continue
        if P.put("shrine_roadside", x, z, slope=0.4, stamp=("moss", 1.4)):
            P.put("soul_crystal", x + rng.uniform(2, 3) * rng.choice([-1, 1]), z + rng.uniform(-1.5, 1.5), s=0.8)
            for j in range(2):
                P.put("candles", x + rng.uniform(-1, 1), z + rng.uniform(-2.0, -1.0), road=False)
            break
    # 도깨비불 광원 (떠다닌다)
    for i in range(20):
        x, z = area(rng)
        P.W.lights.append({"p": [round(x, 2), round(max(P.height(x, z), lev) + rng.uniform(1.2, 3.0), 2), round(z, 2)],
                           "c": SPIRIT if i % 3 else SOUL, "i": round(rng.uniform(3.5, 6), 2), "r": round(rng.uniform(7, 11), 1), "flicker": True})


def lay_dragon(W, P):
    """옆으로 쓰러진 고룡의 뼈: 머리 → 목 → 갈비뼈 → 꼬리가 한 줄로, 양옆에 앞발·뒷발.
    소품 축: 두개골은 주둥이가 앞(-Y), 갈비뼈·척추는 길이가 로컬 X"""
    rng = P.rng
    cx, cz = DRAGON
    a = np.array([0.78, -0.62])
    a /= np.linalg.norm(a)                         # 꼬리 → 머리 방향 (남동쪽을 본다)
    side = np.array([-a[1], a[0]])
    head = np.array([cx + 26.0, cz - 20.0])
    fy = yaw_to(a[0], a[1])
    along = math.degrees(math.atan2(-a[1], a[0]))   # 로컬 X 를 몸 축에 맞추는 Unity Y 회전

    def at(t, off=0.0):
        p = head - a * t + side * off
        return float(p[0]), float(p[1])

    x, z = at(0)
    P.put("dragon_skull", x, z, yaw=fy + 12, check=False, stamp=("ash", 1.6))
    W.fx.append({"type": "soulfire", "p": [x, P.height(x, z) + 1.0, z], "r": 10})
    x, z = at(9.5, 0.8)
    P.put("dragon_spine", x, z, yaw=along + 8, s=0.7, check=False, stamp=("ash", 1.2))       # 목
    x, z = at(19.5, -0.5)
    P.put("dragon_ribs", x, z, yaw=along + 180, s=1.0, check=False, stamp=("ash", 1.4))      # 가슴
    x, z = at(31.5, 1.5)
    P.put("dragon_spine", x, z, yaw=along - 6, s=1.0, check=False, stamp=("ash", 1.2))       # 꼬리
    x, z = at(41.0, -1.5)
    P.put("dragon_spine", x, z, yaw=along + 15, s=0.75, check=False, stamp=("ash", 1.2))     # 꼬리 끝
    for t, sd, sc_ in ((15.5, 1, 1.0), (17.0, -1, 0.9), (27.0, 1, 0.85), (28.5, -1, 0.8)):
        x, z = at(t, sd * 8.5)
        P.put("dragon_claw", x, z, yaw=fy + sd * 70 + rng.normal(0, 12), s=sc_, check=False, stamp=("ash", 1.3))
    # v2: 뼈 장면 셋 — 새끼 용의 뼈, 뼈 무더기 제단(화로와 초), 뼈 가시 고리(영혼 불꽃)
    scenes = []
    for ang, dist in ((2.3, 70.0), (4.1, 62.0), (0.9, 85.0)):
        scenes.append((cx + math.cos(ang) * dist, cz + math.sin(ang) * dist))
    # 1) 새끼 용: 웅크린 작은 해골 (몸을 둥글게 만다)
    jx, jz = scenes[0]
    b = rng.uniform(0, 2 * math.pi)
    P.put("dragon_skull", jx + math.cos(b) * 3.0, jz + math.sin(b) * 3.0, yaw=math.degrees(b) + 60, s=0.55, check=False, stamp=("ash", 1.4))
    P.put("dragon_ribs", jx, jz, yaw=math.degrees(b) + 90, s=0.5, check=False, stamp=("ash", 1.2))
    for k in range(2):
        bb = b + math.pi * (0.7 + 0.45 * k)
        P.put("dragon_spine", jx + math.cos(bb) * 4.0, jz + math.sin(bb) * 4.0, yaw=math.degrees(bb) + 90, s=0.45, check=False)
    P.put("dragon_claw", jx + math.cos(b - 1.2) * 3.2, jz + math.sin(b - 1.2) * 3.2, s=0.5, check=False)
    # 2) 뼈 무더기 제단: 뼈 무더기 고리 + 해골 + 초 + 화로 (누가 아직 제물을 바친다)
    ox, oz = scenes[1]
    for k in range(6):
        a_ = k / 6 * 2 * math.pi + rng.uniform(-0.2, 0.2)
        P.put("bone_pile", ox + math.cos(a_) * 4.2, oz + math.sin(a_) * 4.2, check=False, s=rng.uniform(1.1, 1.4), stamp=("ash", 1.3))
    for k in range(10):
        P.put("skull", ox + rng.normal(0, 2.2), oz + rng.normal(0, 2.2), road=False)
    for k in range(4):
        a_ = rng.uniform(0, 2 * math.pi)
        P.put("candles", ox + math.cos(a_) * 2.0, oz + math.sin(a_) * 2.0, road=False)
    P.put("brazier", ox, oz, check=False)
    for k in range(3):
        P.put("skeleton_remains", ox + rng.uniform(-7, 7), oz + rng.uniform(-7, 7))
    # 3) 뼈 가시 고리: 바깥을 향해 기운 가시 8 개, 가운데 영혼 불꽃
    rx_, rz_ = scenes[2]
    for k in range(8):
        a_ = k / 8 * 2 * math.pi
        P.put("bone_spike", rx_ + math.cos(a_) * 6.5, rz_ + math.sin(a_) * 6.5, s=rng.uniform(1.0, 1.3), slope=None)
    W.fx.append({"type": "soulfire", "p": [rx_, P.height(rx_, rz_) + 0.8, rz_], "r": 4})
    W.lights.append({"p": [round(rx_, 2), round(P.height(rx_, rz_) + 2.2, 2), round(rz_, 2)], "c": SOUL, "i": 5.0, "r": 10.0, "flicker": True})
    for (sx_, sz_) in scenes:
        P.reserve(sx_, sz_, 9.0)
    W.scenes += [{"type": t, "p": [round(x, 1), round(z, 1)], "r": 9.0} for t, (x, z) in zip(("dragon_young", "bone_altar", "spike_ring"), scenes)]
    area = in_disk(DRAGON, DRAGON_R - 15)
    P.scatter("bone_spike", 36, area)
    P.scatter("bones_scatter", 80, area)
    P.scatter("bone_pile", 18, area)
    P.scatter("skull", 30, area)
    P.scatter("skeleton_remains", 10, area)
    P.scatter("rock_a", 20, area)
    P.scatter("rock_c", 34, area)
    P.scatter("rock_flat", 7, area)
    # 분지 테두리의 절벽 (안쪽을 본다)
    for i in range(18):
        ang = i / 18 * 2 * math.pi + rng.uniform(-0.08, 0.08)
        d = DRAGON_R - 20 + rng.uniform(-10, 18)
        x, z = cx + math.cos(ang) * d, cz + math.sin(ang) * d
        nm = ["cliff_a", "cliff_c", "cliff_b"][i % 3]
        P.put(nm, x, z, yaw=yaw_to(cx - x, cz - z) + rng.normal(0, 10), slope=None)
    for i in range(4):
        x, z = area(rng)
        W.lights.append({"p": [round(x, 2), round(P.height(x, z) + 1.5, 2), round(z, 2)], "c": SOUL, "i": 4.0, "r": 9.0, "flicker": True})
    for t in (19.5, 31.5):                     # 머리(t=0)는 두개골 프리팹에 광원이 있다
        x, z = at(t)
        W.lights.append({"p": [round(x, 2), round(P.height(x, z) + 2.5, 2), round(z, 2)], "c": SOUL, "i": 5.0, "r": 12.0, "flicker": True})


def lay_tree(W, P):
    rng = P.rng
    cx, cz = TREE
    for i in range(22):                      # 광원 수 (LightCuller 한도 48) 때문에 36 → 22
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(9, 26)
        P.put("mushroom_glow", cx + math.cos(a) * d, cz + math.sin(a) * d, road=False)
    for i in range(22):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(10, 34)
        P.put("flower_lily", cx + math.cos(a) * d, cz + math.sin(a) * d, road=False)
    P.scatter("roots", 10, in_disk(TREE, 30, 11))
    W.fx.append({"type": "fireflies", "p": [cx, P.height(cx, cz) + 2, cz], "r": 30})
    W.fx.append({"type": "wisps", "p": [cx, P.height(cx, cz) + 1, cz], "r": 24})


def lay_tower(W, P):
    rng = P.rng
    cx, cz = TOWER
    for i in range(10):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(9, 22)
        x, z = cx + math.cos(a) * d, cz + math.sin(a) * d
        nm = ["wall_ruin_b", "rubble", "wall_ruin_a", "pillar_b", "rubble"][i % 5]
        P.put(nm, x, z, yaw=yaw_to(x - cx, z - cz) + rng.normal(0, 15), slope=0.7)      # 앞면이 바깥, 긴 축이 둘레를 따른다
    P.scatter("rock_b", 8, in_disk(TOWER, 60, 20), slope=None, ground="box")
    P.scatter("rock_flat", 6, in_disk(TOWER, 60, 20), slope=None, ground="box")
    P.put("lantern", cx + 3, cz - 9, yaw=180)
    for i in range(6):                                   # 망루 발치의 촛불과 꼭대기에서 새는 영혼 빛
        a = i / 6 * 2 * math.pi + rng.uniform(-0.2, 0.2)
        d = rng.uniform(5.6, 6.6)
        P.put("candles", cx + math.cos(a) * d, cz + math.sin(a) * d, road=False)
    W.lights.append({"p": [cx, round(P.height(cx, cz) + 6.0, 2), cz], "c": SOUL, "i": 6.0, "r": 12.0, "flicker": True})


def lay_gate(W, P):
    rng = P.rng
    cx, cz = GATE
    for side in (-1, 1):
        P.put("statue_reaper", cx + side * 13.5, cz - 12, yaw=180 + side * 8, check=False, stamp=("path", 1.2))
        P.put("lantern", cx + side * 5.5, cz - 14, yaw=180, check=False)
        P.put("pillar_a", cx + side * 9, cz - 30, yaw=180, check=False)
        P.put("pillar_b", cx + side * 10, cz - 48, yaw=180, check=False)
    P.scatter("skull", 30, in_disk((cx, cz - 20), 22), road=False)
    P.scatter("candles", 10, in_disk((cx, cz - 16), 9), road=False)
    P.scatter("bones_scatter", 12, in_disk((cx, cz - 25), 25))
    W.fx.append({"type": "soulfire", "p": [cx, P.height(cx, cz - 10) + 1.2, cz - 10], "r": 8})
    # 문이 박힌 벽 홈의 양쪽 면을 바위 절벽으로 덮는다 (매끈한 흙 비탈로 보이지 않게)
    for side in (-1, 1):
        for (dx, dz, nm, sc) in ((19.0, 6.0, "cliff_a", 1.2), (36.0, 9.0, "cliff_c", 1.2), (27.0, 20.0, "cliff_b", 1.8),
                                 (47.0, 17.0, "cliff_a", 1.6), (60.0, 24.0, "cliff_c", 1.5), (38.0, 34.0, "cliff_b", 2.0)):
            P.put(nm, cx + side * dx, cz + dz, yaw=180 + side * 4 + rng.normal(0, 4), s=sc, check=False,
                  align=0.5, align_max=25, stamp=("rock", 1.2))
        for dz in (14.0, 30.0):                           # 문 너머 골짜기 양벽 (쇠창살 사이로 보인다). 밑동은 골짜기 바닥 높이
            P.put("cliff_b", cx + side * 12.5, cz + dz, yaw=-side * 90 + rng.normal(0, 5), s=rng.uniform(1.2, 1.5), check=False,
                  y=P.height(cx, cz + dz) - 0.4, stamp=("rock", 1.0))


def lay_bridge_creek(W, P):
    rng = P.rng
    c, s = W.creek, W.creek_s
    bx, bz = W.bridge_p
    # 물웅덩이 아래쪽 끝의 돌무더기 (물 평면이 끊기는 자리를 가린다)
    s1 = W.pool_range[1]
    i = int(np.searchsorted(s, s1))
    px, pz = c[min(i, len(c) - 1)]
    P.put("rock_b", px, pz, yaw=rng.uniform(0, 360), check=False, align=True, s=1.25, ground="box")
    for k in range(4):
        for t in range(12):                                # 물 밖 둑 위에
            x, z = px + rng.uniform(-5, 5), pz + rng.uniform(-5, 5)
            if P.height(x, z) > W.pool_level + 0.1:
                P.put("rubble", x, z, check=False, s=rng.uniform(1.0, 1.4))
                break
    i0 = int(np.searchsorted(s, W.pool_range[0]))
    qx, qz = c[i0]
    P.put("rock_b", qx, qz, yaw=rng.uniform(0, 360), check=False, align=True, s=1.2, ground="box")      # 위쪽 끝 턱 위의 바위 (개울 골 위로 뜨지 않게 바닥 상자 접지)
    for side in (-1, 1):
        r = W.bridge_axis
        P.put("lantern", bx + r[0] * side * 10 + r[1] * 2.6, bz + r[1] * side * 10 - r[0] * 2.6,
              yaw=math.degrees(math.atan2(r[0] * side, r[1] * side)), check=False)
    # 개울 바닥의 바위와 뼈, 둑의 갈대·고목
    for k in range(0, len(c), 6):
        x, z = c[k]
        if abs(s[k] - (W.pool_range[0] + W.pool_range[1]) / 2) < 50:
            continue
        if rng.random() < 0.35:
            P.put(["rock_c", "rock_a", "bones_scatter", "rock_flat"][k % 4], x + rng.uniform(-3, 3), z + rng.uniform(-3, 3),
                  slope=None)          # 마른 개울 바닥 (호수·웅덩이 물속은 물 검사로 뺀다)
        if rng.random() < 0.25:
            d = W.creek_dir_b
            off = rng.choice([-1, 1]) * rng.uniform(8, 14)
            P.put(["dead_tree_b", "dead_tree_a", "stump", "log_fallen"][k % 4], x - d[1] * off, z + d[0] * off)
    for k in range(0, len(c), 40):
        x, z = c[k]
        hy = P.height(x, z)
        if W.in_pool(x, z):
            hy = max(hy, W.pool_level)
        W.fx.append({"type": "mist", "p": [round(float(x), 2), round(hy + 0.5, 2), round(float(z), 2)], "r": 22})


def lay_forest(W, P, center, R, density, seed, clearings=()):
    """죽은 숲. v2: 덤불숲(시야가 막힘)과 빈터(시야가 열림)가 번갈아 오고, 빈터 몇 곳에 작은 장면(clearings 종류)"""
    rng = P.rng
    X, Z = W.X, W.Z
    rs, cs, d = disk(W.h.shape, center[0], center[1], R + 40)
    Xs, Zs = X[rs, cs], Z[rs, cs]
    edge = R + 45 * fbm(Xs, Zs, 1 / 120, 3, seed)
    m = np.zeros(W.h.shape, np.float32)
    m[rs, cs] = ss(-(d / edge), -1.0, -0.6) * (0.55 + 0.45 * ss(fbm(Xs, Zs, 1 / 60, 3, seed + 1), -0.4, 0.4))
    m *= (W.slope < 0.7)
    rs2, cs2, dt = disk(W.h.shape, TREE[0], TREE[1], 36)
    m[rs2, cs2] *= ss(dt, 26, 34)                     # 영혼의 고목 둘레는 비워 거목이 드러나게
    W.forest = np.maximum(W.forest, m)
    nz = np.zeros(W.h.shape, np.float32)
    nz[rs, cs] = fbm(Xs, Zs, 1 / 42, 3, seed + 7)
    thick = ss(nz, -0.02, 0.28)                        # 덤불숲: 가시덤불·쓰러진 나무가 빽빽
    glade = ss(-nz, 0.2, 0.4)                          # 빈터: 나무가 드문드문, 바닥이 열린다
    del nz
    # 빈터의 작은 장면 (숲 나무보다 먼저 자리를 잡는다)
    cand = in_mask(W, m * glade * (W.slope < 0.3) * (W.road_dist > 14))
    got = []
    for t in range(300):
        if len(got) >= len(clearings):
            break
        p = cand(rng)
        if p is None:
            break
        if any((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 < 70 ** 2 for q in got) or P.under_water(p[0], p[1], 0.3):
            continue
        if lay_scene(W, P, clearings[len(got)], p[0], p[1]):
            got.append(p)
    # 나무는 덤불숲에 몰리고 빈터에는 드물게, 덤불·쓰러진 나무는 덤불숲에 빽빽하게
    area_t = in_mask(W, m * (0.12 + 0.55 * (1 - glade) + 0.9 * thick))
    area_b = in_mask(W, m * (0.04 + thick) * (1 - glade))
    area_g = in_mask(W, m * glade)
    area_tot = float(m.sum())
    nt = int(area_tot * density)
    P.scatter("dead_tree_a", int(nt * 0.34 * 1.05 * DEAD_TREE_CUT), area_t)
    P.scatter("dead_tree_c", int(nt * 0.22 * 1.05 * DEAD_TREE_CUT), area_t)
    P.scatter("dead_tree_b", int(nt * 0.22 * 1.05 * DEAD_TREE_CUT), area_t)
    P.scatter("bramble", int(nt * 0.75), area_b)
    P.scatter("bush_dead", int(nt * 0.55), area_b)
    P.scatter("log_fallen", int(nt * 0.13), area_b)
    P.scatter("roots", int(nt * 0.06), area_b)
    P.scatter("rock_a", int(nt * 0.06), area_t)
    P.scatter("rock_c", int(nt * 0.07), area_t)
    P.scatter("stump", int(nt * 0.07), area_t)
    P.scatter("mushroom_glow", int(nt * 0.04), area_g)
    P.scatter("mushroom_toxic", int(nt * 0.02), area_t)
    P.scatter("flower_lily", int(nt * 0.05), area_g)
    for i in range(int(area_tot / 9000)):
        p = area_g(rng) or area_t(rng)
        W.fx.append({"type": "fireflies", "p": [float(p[0]), P.height(*p) + 1.5, float(p[1])], "r": 26})
    for i in range(int(area_tot / 16000)):
        p = area_t(rng)
        W.fx.append({"type": "mist", "p": [float(p[0]), P.height(*p) + 0.5, float(p[1])], "r": 30})
    log("숲", center, "나무 목표", nt, "빈터 장면", len(got))


def lay_lake(W, P):
    rng = P.rng
    lev = W.lake_level
    area = in_disk(LAKE, LAKE_R + 25)
    got = 0
    for i in range(600):
        if got >= 36:
            break
        x, z = area(rng)
        if lev - 1.2 < P.height(x, z) < lev - 0.15 and P.free(x, z, 0.5):
            P.put("lotus_glow", x, z, y=lev + 0.01, align=False, tilt=0, check=False)
            got += 1
    shore = lambda rng: (lambda p: p if lev + 0.1 < P.height(*p) < lev + 3 else None)(in_disk(LAKE, LAKE_R + 35, LAKE_R - 25)(rng))
    P.scatter("flower_lily", 24, shore)
    P.scatter("rock_a", 11, shore)
    P.scatter("rock_flat", 5, shore)
    P.scatter("dead_tree_b", 10, shore)
    P.scatter("log_fallen", 3, shore)
    for i in range(8):
        x, z = area(rng)
        W.lights.append({"p": [round(x, 2), round(max(P.height(x, z), lev) + rng.uniform(0.8, 2.2), 2), round(z, 2)], "c": SPIRIT, "i": 3.5, "r": 8.0, "flicker": True})
    W.fx.append({"type": "mist", "p": [LAKE[0], lev + 0.3, LAKE[1]], "r": 58})
    W.fx.append({"type": "fireflies", "p": [LAKE[0], lev + 1.5, LAKE[1]], "r": 50})


def lay_mountain_foot(W, P):
    """산기슭·가장자리 벽의 절벽과 바위"""
    rng = P.rng
    foot = ss(W.mount, 0.12, 0.3) * ss(-W.mount, -0.75, -0.5) * ss(W.slope, 0.25, 0.5)
    area = in_mask(W, foot)
    got = 0
    for i in range(4000):
        if got >= 200:
            break
        x, z = area(rng)
        nm = ["cliff_a", "cliff_c", "cliff_b", "cliff_a", "rock_b"][got % 5]
        if nm == "rock_b" and sample(W.slope, x, z) > 1.2:
            continue                                      # 너무 가파른 면의 바위는 거의 다 묻힌다
        # 앞면이 내리막을 보면 긴 축(로컬 X)이 등고선을 따르고 짧은 축만 비탈을 가로지른다.
        # 절벽은 법선 쪽으로 반만 (25° 까지) 기울이고, 높이는 바닥 상자 전체가 땅에 닿게 (아래쪽이 뜨지 않는다)
        gx, gz = sample(W.gx, x, z), sample(W.gz, x, z)
        yaw = yaw_to(-gx, -gz) + rng.normal(0, 10)
        if P.put(nm, x, z, yaw=yaw, slope=None, s=rng.uniform(1.0, 1.9) if nm != "rock_b" else None,
                 align=0.5 if nm != "rock_b" else None, align_max=25 if nm != "rock_b" else 45, ground="box", stamp=("rock", 1.3)):
            got += 1
    # 비탈 면: 경사에 맞춰 눕는 바위만 (지형 나무 바위는 기울지 못해 아래가 뜬다)
    steep = ss(W.slope, 0.45, 0.9) * (W.slope < 1.5) * (W.mount < 0.75)        # 벽처럼 선 면(기울기 1.5 넘음)에는 붙이지 않는다
    a2 = in_mask(W, steep)
    P.scatter("rock_b", 260, a2, slope=None, ground="box", align_max=40)
    P.scatter("rock_flat", 190, a2, slope=None, ground="box", align_max=40)
    # 너덜 띠: 비탈이 평지와 만나는 발치 (무너진 돌이 쌓이는 자리). 완만한 곳이라 지형 나무 바위도 땅에 붙는다
    st = (W.slope > 0.45).astype(np.float32) * (W.mount < 0.75)
    scree = (box_blur(st, 2) > 0.02) * (W.slope < 0.4) * (W.mount < 0.75) * (np.hypot(W.X - GATE[0], W.Z - GATE[1]) > 30)
    a3 = in_mask(W, scree.astype(np.float32))
    P.scatter("rock_a", 170, a3, slope=0.4)
    P.scatter("rock_c", 230, a3, slope=0.4)


# ─────────────────────────── 작은 장면 (v2) ───────────────────────────
# 들판·길가에 80~120 m 마다 하나씩 놓는 작은 이야기 장면. 서로 겹치지 않고, 어디서든 다음 장면이 눈에 들어오게.
# 모든 장면에는 밤에 멀리서 보이는 빛(range 6 m 넘는 광원: 등불·화로·수정·모닥불, 없으면 떠도는 영혼 빛)이 하나 이상 있다.
# 장면 틀: (차지하는 반지름 m, 길가 선호, 들판 선호)
SCENES = {
    "execution": (9.0, 1.0, 0.55),    # 처형터: 교수대·매달린 새장·해골·양초
    "chapel":    (10.0, 0.7, 1.0),    # 무너진 예배당: 벽·아치·기둥·석관·제단 양초
    "shrine":    (5.0, 1.3, 0.25),    # 길가 사당: 작은 사당·양초·등불
    "ritual":    (10.5, 0.35, 1.0),   # 의식의 원: 사슬 오벨리스크·기둥 고리·양초·영혼 불꽃
    "camp":      (8.5, 0.8, 0.9),     # 버려진 야영지: 찢긴 천막·꺼져 가는 모닥불·부서진 수레
    "crystal":   (7.0, 0.3, 1.0),     # 영혼 수정 노두: 빛나는 수정·바위
    "family":    (9.0, 0.9, 0.9),     # 가족 묘역: 작은 납골당·쇠 울타리·묘비
    "battle":    (12.0, 0.6, 1.0),    # 전장의 흔적: 찢긴 깃발·해골·뼈 무더기
}
SCENE_STEP = 80.0           # 볼거리(장소 원 + 30 m, 다른 장면)에서 이 거리보다 먼 후보가 없을 때까지 장면을 더한다 (장면 사이 약 80~130 m)


class Scene:
    """장면 하나의 로컬 좌표: 가운데 (x, z), 앞(+lz)이 yaw 쪽 (보통 가장 가까운 길), 오른쪽 +lx"""

    def __init__(self, W, P, x, z, fy):
        self.W, self.P, self.x, self.z, self.fy = W, P, x, z, fy
        t = math.radians(fy)
        self.f = (math.sin(t), math.cos(t))
        self.r = (math.cos(t), -math.sin(t))
        self.n = 0
        self.beacon = False

    def at(self, lx, lz):
        return (self.x + self.r[0] * lx + self.f[0] * lz, self.z + self.r[1] * lx + self.f[1] * lz)

    def put(self, a, lx, lz, yaw=None, ayaw=None, loose=False, slope=0.6, must=False, **kw):
        """yaw: 장면 앞 기준 회전(도), ayaw: 절대 회전. loose: 장면 안 다른 소품과의 겹침은 보지 않는다 (땅·길·물은 본다).
        must: 장면의 중심 소품 — 보통 검사로 안 되면 loose 로 한 번 더"""
        if must and not loose:
            return self.put(a, lx, lz, yaw, ayaw, False, slope, **kw) or self.put(a, lx, lz, yaw, ayaw, True, slope, **kw)
        P = self.P
        x, z = self.at(lx, lz)
        if a in BOX_GROUND:
            kw.setdefault("ground", "box")          # 길쭉하거나 큰 구조물: 바닥 상자 전체가 땅에 닿게 (비탈에서 한쪽이 뜨지 않게)
        if ayaw is None:
            ayaw = self.fy + yaw if yaw is not None else P.rng.uniform(0, 360)
        if loose:
            s0 = kw.get("s") or 1.0
            if not P.ok_ground(x, z, P.fp(a) * s0, kw.get("road", True), kw.get("water", True), slope):
                return False
            kw["check"] = False
        else:
            kw.setdefault("slope", slope)
        n0, l0 = len(P.objects), len(self.W.lights)
        if not P.put(a, x, z, yaw=ayaw, **kw):
            return False
        self.n += 1
        if len(P.objects) > n0:
            lt = P.meta.get(P.objects[-1]["a"], {}).get("light")
            if lt and lt.get("range", 0) >= 6:
                self.beacon = True
        if any(l["r"] >= 6 for l in self.W.lights[l0:]):
            self.beacon = True
        return True

    def light(self, c, i, r, lx=0.0, lz=0.0, up=2.0):
        x, z = self.at(lx, lz)
        self.W.lights.append({"p": [round(x, 2), round(self.P.height(x, z) + up, 2), round(z, 2)], "c": list(c), "i": float(i),
                              "r": float(r), "flicker": True})
        if r >= 6:
            self.beacon = True

    def fx(self, t, r, lx=0.0, lz=0.0, up=1.0):
        x, z = self.at(lx, lz)
        self.W.fx.append({"type": t, "p": [x, self.P.height(x, z) + up, z], "r": r})

    def floor(self, kind, r, lx=0.0, lz=0.0):
        x, z = self.at(lx, lz)
        self.P.stamps.append((x, z, r, kind))


BOX_GROUND = {"wall_ruin_a", "wall_ruin_b", "arch_ruin", "pillar_b", "mausoleum_small", "sarcophagus", "cart_broken", "tent_torn",
              "log_fallen", "gallows", "iron_fence"}


def polar(rng, r0, r1):
    a = rng.uniform(0, 2 * math.pi)
    d = math.sqrt(rng.uniform((r0 / r1) ** 2, 1)) * r1
    return math.cos(a) * d, math.sin(a) * d


def sc_execution(S, rng):
    S.floor("dirt", 5.5)
    S.put("gallows", 0, 0, yaw=rng.normal(0, 5), must=True, stamp=("dirt", 1.6))
    for sd in (-1, 1):
        if rng.random() < 0.8:
            S.put("hanging_cage", sd * 5.0, -1.2, yaw=sd * 15 + rng.normal(0, 6))
    S.put("skeleton_remains", 0.4, 1.7, yaw=rng.uniform(-30, 30), loose=True)
    for k in range(int(rng.integers(4, 8))):
        S.put("skull", *polar(rng, 1.6, 5.5), loose=True)
    for k in range(3):
        S.put("candles", rng.uniform(-1.4, 1.4), rng.uniform(2.3, 3.1), loose=True)
    S.put("bone_pile", -3.4, -2.8)
    for (lx, lz) in ((-1.8, -5.2), (1.6, -5.6)):           # 처형된 이들의 이름 없는 무덤
        if rng.random() < 0.75:
            S.put("grave_sunken", lx, lz, yaw=rng.normal(0, 10), stamp=("mud", 1.2))
    S.put("brazier", 3.6, 2.6, yaw=0)
    if rng.random() < 0.6:
        sd = rng.choice([-1, 1])
        S.put("fence", sd * 4.8, 4.2, yaw=rng.normal(0, 8), tilt=8)


def sc_chapel(S, rng):
    hw, hd = 4.2, 6.0
    S.floor("path", 5.5)
    S.floor("rock", 3.0, 0, -1.0)
    S.put("arch_ruin", 0, hd, yaw=rng.normal(0, 3), loose=True)
    for sd in (-1, 1):
        for lz, nm in ((2.6, "wall_ruin_a"), (-2.8, "wall_ruin_b")):
            if rng.random() < 0.8:
                S.put(nm, sd * hw, lz, yaw=90 * sd + rng.normal(0, 4), loose=True, stamp=("dirt", 1.1))
    if rng.random() < 0.6:
        S.put("wall_ruin_b", 0, -hd - 0.4, yaw=180 + rng.normal(0, 4), loose=True)
    for sd in (-1, 1):                       # 안쪽은 가는 기둥만 (담 안쪽 면 |lx| 2.7 까지), 부러진 큰 기둥은 담 밖에
        if rng.random() < 0.8:
            S.put("pillar_a", sd * 1.9, 0.9, yaw=rng.uniform(0, 360), loose=True)
        if rng.random() < 0.5:
            S.put("pillar_a", sd * 1.9, -1.6, yaw=rng.uniform(0, 360), loose=True)
    if rng.random() < 0.7:
        a_ = rng.uniform(0, 2 * math.pi)
        S.put("pillar_b", math.cos(a_) * 8.0, math.sin(a_) * 8.0, yaw=rng.uniform(0, 360))
    S.put("sarcophagus", 0, -3.7, yaw=90 + rng.normal(0, 3), loose=True)
    for (lx, lz) in ((-1.4, -2.0), (1.4, -2.1), (0.2, -1.6)):
        S.put("candles", lx + rng.normal(0, 0.15), lz + rng.normal(0, 0.15), loose=True)
    S.put("lantern", hw + 1.6, hd + 1.4, yaw=rng.normal(0, 10))
    for k in range(3):
        S.put("rubble", *polar(rng, 2.0, 8.0))
    for k in range(int(rng.integers(1, 4))):                # 예배당 마당의 오래된 무덤
        S.put(["grave_slab_c", "grave_cross", "grave_slab_a"][k], -hw - 2.2 - k * 0.4, hd - 1.0 - k * 2.0, yaw=rng.normal(0, 8))
    if rng.random() < 0.3:
        S.put("statue_angel", hw + 2.0, -hd + 1.0, yaw=rng.normal(0, 10))


def sc_shrine(S, rng):
    S.floor("path", 2.2)
    S.put("shrine_roadside", 0, 0, yaw=rng.normal(0, 4), must=True, stamp=("path", 1.4))
    for k in range(3):
        S.put("candles", rng.uniform(-0.9, 0.9), rng.uniform(1.3, 1.9), loose=True)
    S.put("lantern", 2.1, 0.7, yaw=-20 + rng.normal(0, 8))
    for k in range(4):
        S.put("flower_lily", *polar(rng, 1.5, 3.4), loose=True)
    if rng.random() < 0.5:
        S.put("skull", rng.uniform(-1.0, 1.0), rng.uniform(1.0, 1.3), loose=True)
    if rng.random() < 0.35:
        S.put("statue_angel", -2.3, -1.3, yaw=15 + rng.normal(0, 6))


def sc_ritual(S, rng):
    S.floor("ash", 4.0)
    S.put("obelisk_chained", 0, 0, yaw=rng.uniform(0, 360), must=True, stamp=("ash", 1.8))
    n = 8
    for k in range(n):
        if rng.random() < 0.2:
            continue
        a = k / n * 2 * math.pi + 0.2
        lx, lz = math.cos(a) * 7.5, math.sin(a) * 7.5
        x, z = S.at(lx, lz)
        S.put("pillar_a" if rng.random() < 0.6 else "pillar_b", lx, lz, ayaw=yaw_to(S.x - x, S.z - z), loose=True, stamp=("dirt", 1.0))
    for k in range(5):
        a = k / 5 * 2 * math.pi + 0.3
        S.put("candles", math.cos(a) * 3.2, math.sin(a) * 3.2, loose=True)
    for k in range(6):
        S.put("skull", *polar(rng, 2.0, 6.0), loose=True)
    S.fx("soulfire", 4, up=0.8)
    S.light(SOUL, 5.0, 10.0, up=2.6)


def sc_camp(S, rng):
    S.floor("dirt", 4.5)
    S.put("campfire", 0, 0, must=True, stamp=("ash", 1.3))
    S.put("tent_torn", -3.6, -2.4, yaw=25 + rng.normal(0, 8))
    if rng.random() < 0.5:
        S.put("tent_torn", 3.4, -3.0, yaw=-30 + rng.normal(0, 8))
    for sd in (-1, 1):
        S.put("log_fallen", sd * 2.5, 1.5, yaw=sd * 70 + rng.normal(0, 8), s=0.75, loose=True)
    S.put("cart_broken", 5.4, 2.4, yaw=rng.uniform(60, 120))
    S.put("stump", -4.6, 2.2)
    for k in range(2):
        S.put("rock_c", *polar(rng, 1.0, 1.4), loose=True)
    S.put("skull", *polar(rng, 2.0, 4.0), loose=True)
    S.put("bones_scatter", *polar(rng, 3.0, 6.0), loose=True)
    S.put("skeleton_remains", *polar(rng, 2.5, 5.0), loose=True)      # 불가에서 잠든 채로
    S.fx("fireflies", 7, up=1.2)


def sc_crystal(S, rng):
    S.floor("moss", 4.0)
    S.put("soul_crystal", 0, 0, s=1.3, yaw=rng.uniform(0, 360), must=True, stamp=("rock", 1.4))
    for k in range(int(rng.integers(1, 3))):
        S.put("soul_crystal", *polar(rng, 2.4, 3.8), s=rng.uniform(0.7, 1.0))
    S.put("rock_b", *polar(rng, 3.5, 5.5))
    S.put("rock_flat", *polar(rng, 3.5, 5.5))
    for k in range(2):
        S.put("rock_a", *polar(rng, 3.0, 6.0))
    for k in range(4):
        S.put("mushroom_glow", *polar(rng, 1.5, 5.0), loose=True)
    S.fx("wisps", 8, up=1.0)


def sc_family(S, rng):
    S.floor("dirt", 5.0)
    S.put("mausoleum_small", 0, -3.8, yaw=rng.normal(0, 3), must=True, slope=0.3, stamp=("dirt", 1.2))
    gn = ["grave_slab_a", "grave_slab_b", "grave_cross", "grave_slab_c"]
    for k, (lx, lz) in enumerate(((-2.6, 1.0), (-0.9, 1.0), (0.9, 1.0), (2.6, 1.0), (-1.8, 3.2), (0.0, 3.2), (1.8, 3.2))):
        if rng.random() < 0.8:
            S.put(gn[k % 4], lx + rng.normal(0, 0.15), lz + rng.normal(0, 0.15), yaw=rng.normal(0, 6), loose=True, stamp=("dirt", 1.4))
    for sd in (-1, 1):
        S.put("iron_fence", sd * 3.1, 5.6, yaw=rng.normal(0, 3), loose=True, tilt=4)
        S.put("iron_fence", sd * 5.2, 2.2, yaw=90 + rng.normal(0, 3), loose=True, tilt=4)
        if rng.random() < 0.6:
            S.put("iron_fence", sd * 5.2, -1.4, yaw=90 + rng.normal(0, 3), loose=True, tilt=6)
    for sd in (-1, 1):
        S.put("candles", sd * 0.7, 4.4, loose=True)
    S.put("lantern", 1.5, 6.8, yaw=rng.normal(0, 10))


def sc_battle(S, rng):
    S.floor("dirt", 7.0)
    for k in range(4):
        S.put("banner_torn", *polar(rng, 2.0, 10.0))
    for k in range(5):
        S.put("skeleton_remains", *polar(rng, 1.0, 10.0), loose=True)
    for k in range(8):
        S.put("skull", *polar(rng, 0.5, 10.0), loose=True)
    for k in range(2):
        S.put("bone_pile", *polar(rng, 2.0, 8.0))
    for k in range(3):
        S.put("bones_scatter", *polar(rng, 1.0, 9.0), loose=True)
    S.put("rubble", *polar(rng, 3.0, 8.0))
    if rng.random() < 0.4:
        S.put("cart_broken", *polar(rng, 4.0, 9.0))
    for k in range(2):                       # 전장을 떠도는 영혼 빛
        lx, lz = polar(rng, 1.0, 7.0)
        S.light(SPIRIT, 3.5, 8.0, lx, lz, up=rng.uniform(1.6, 2.6))
    S.fx("wisps", 12, up=1.0)


SCENE_FN = {"execution": sc_execution, "chapel": sc_chapel, "shrine": sc_shrine, "ritual": sc_ritual, "camp": sc_camp,
            "crystal": sc_crystal, "family": sc_family, "battle": sc_battle}


def scene_ok(W, P, x, z, R):
    """장면 자리: 가운데가 고르고 길·물·다른 소품에서 떨어져 있고, 둘레 8 점도 걸을 수 있는 땅"""
    (bx0, bz0), (bx1, bz1) = BOUNDS
    if not (bx0 + 18 < x < bx1 - 18 and bz0 + 18 < z < bz1 - 18):
        return False
    if not P.ok_ground(x, z, R, road=True, water=True, slope=0.35):
        return False
    if not P.free(x, z, R * 0.75):
        return False
    for k in range(8):
        a = k / 8 * 2 * math.pi
        px, pz = x + math.cos(a) * R, z + math.sin(a) * R
        if sample(W.slope, px, pz) > 0.55 or sample(W.mount, px, pz) > 0.4 or P.under_water(px, pz, 0.2):
            return False
    return True


def face_road(W, x, z):
    """가장 가까운 길 쪽을 보는 yaw 와 길까지 거리"""
    best, bp = 1e18, None
    for c, hw in W.road_curves:
        d2 = (c[:, 0] - x) ** 2 + (c[:, 1] - z) ** 2
        k = int(np.argmin(d2))
        if d2[k] < best:
            best, bp = float(d2[k]), c[k]
    return yaw_to(bp[0] - x, bp[1] - z), math.sqrt(best)


def lay_scene(W, P, kind, x, z, yaw=None):
    R = SCENES[kind][0]
    if not scene_ok(W, P, x, z, R):
        return False
    rng = P.rng
    fy, droad = face_road(W, x, z)
    if yaw is not None:
        fy = yaw
    fy += rng.normal(0, 10)
    S = Scene(W, P, x, z, fy)
    SCENE_FN[kind](S, rng)
    if not S.beacon:                         # 멀리서 보이는 빛이 없으면 떠도는 영혼 빛 하나
        S.light(SPIRIT if rng.random() < 0.5 else SOUL, 4.0, 8.0, up=2.2)
    # 둘레: 덤불·가시덤불·바위·고목 몇 (빈 들판 한가운데 덩그러니 놓이지 않게 둘레를 감싼다)
    for k in range(int(rng.integers(3, 7))):
        a = rng.uniform(0, 2 * math.pi)
        d = R + rng.uniform(1.5, 7.0)
        nm = ["dead_tree_b", "bramble", "bush_dead", "bush_dead", "rock_c", "bramble"][k % 6] if k else \
            ("dead_tree_a" if rng.random() < 0.5 else "dead_tree_c")
        P.put(nm, x + math.cos(a) * d, z + math.sin(a) * d)
    # 길가 장면: 길에서 장면 앞까지 밟힌 오솔길 (바닥 칠·풀 걷기만)
    if droad < 50:
        t = math.radians(fy)
        fx_, fz_ = math.sin(t), math.cos(t)
        n = int((droad - R * 0.4) / 2.0)
        for k in range(max(0, n)):
            d = R * 0.4 + k * 2.0
            P.stamps.append((x + fx_ * d + rng.normal(0, 0.3), z + fz_ * d + rng.normal(0, 0.3), 0.95, "path"))
    P.reserve(x, z, R)
    W.scenes.append({"type": kind, "p": [round(x, 1), round(z, 1)], "r": R, "yaw": round(fy % 360, 1), "props": S.n})
    return True


def lay_crossroads(W, P):
    """길이 갈라지는 곳 (장소 밖): 모서리의 화로 둘과 이정표 기둥, 기둥 발치의 해골·초"""
    rng = P.rng
    pois = [(p if p else W.bridge_p, r) for (_, _, p, r) in POIS]
    curves = W.road_curves
    got = 0
    for i, (c, hw) in enumerate(curves):
        for end in (c[0], c[-1]):
            for j, (c2, hw2) in enumerate(curves):
                if j == i:
                    continue
                d2 = (c2[:, 0] - end[0]) ** 2 + (c2[:, 1] - end[1]) ** 2
                k = int(np.argmin(d2))
                if d2[k] > 10 ** 2:
                    continue
                jx, jz = float(c2[k, 0]), float(c2[k, 1])
                if any((jx - px) ** 2 + (jz - pz) ** 2 < (pr + 12) ** 2 for (px, pz), pr in pois):
                    continue
                if any((jx - s_["p"][0]) ** 2 + (jz - s_["p"][1]) ** 2 < 40 ** 2 for s_ in W.scenes):
                    continue
                # 모서리 후보: 둘레 12 방향, 길 가장자리에서 2.2 m 넘게 떨어진 첫 자리
                spots = []
                for t in range(12):
                    a = t / 12 * 2 * math.pi
                    for rr in (hw2 + 4.5, hw2 + 6.0, hw2 + 7.5):
                        x, z = jx + math.cos(a) * rr, jz + math.sin(a) * rr
                        if sample(W.road_dist, x, z) > sample(W.road_hw, x, z) + 2.2 and P.ok_ground(x, z, 0.8, road=False, slope=0.45):
                            spots.append((a, x, z))
                            break
                used = []
                for nm in ("brazier", "brazier", "pillar_a"):
                    for (a, x, z) in spots:
                        if any(abs((a - b + math.pi) % (2 * math.pi) - math.pi) < 1.3 for b in used):
                            continue
                        if P.put(nm, x, z, yaw=yaw_to(jx - x, jz - z), road=False, slope=0.45):
                            used.append(a)
                            if nm == "pillar_a":                    # 이정표 기둥 발치
                                for q in range(3):
                                    P.put("skull", x + rng.normal(0, 0.8), z + rng.normal(0, 0.8), road=False)
                                P.put("candles", x + rng.uniform(-0.8, 0.8), z + rng.uniform(-0.8, 0.8), road=False)
                            break
                if not used:
                    continue
                P.reserve(jx, jz, 8.0)
                W.scenes.append({"type": "crossroad", "p": [round(jx, 1), round(jz, 1)], "r": 8.0, "yaw": 0.0, "props": len(used)})
                got += 1
    log("갈림길 화로", got)


def lay_vignettes(W, P, seed):
    """빈 들판 채우기: 볼거리(장소·장면)에서 가장 먼 땅부터 장면을 놓는다 (가장 먼 점 고르기).
    길가(길 가장자리에서 10~40 m)를 조금 더 좋아하고, 같은 장면 틀이 가까이 되풀이되지 않게 고른다.
    장면은 따로 씨앗을 쓴다 (앞 단계의 개수를 바꿔도 장면 자리가 흔들리지 않게)"""
    main_rng = P.rng
    P.rng = rng = np.random.default_rng(seed + 9001)
    (bx0, bz0), (bx1, bz1) = BOUNDS
    lay_crossroads(W, P)
    g = np.arange(bx0 + 24, bx1 - 24, 4.0)
    GX, GZ = np.meshgrid(g, g)
    gx, gz = GX.ravel(), GZ.ravel()
    ix, iz = np.round(gx).astype(int), np.round(gz).astype(int)
    rd = W.road_dist[iz, ix] - W.road_hw[iz, ix]
    foot = W.mount[iz, ix] > 0.1                   # 산기슭 띠 (벼랑 발치)
    ok = (W.slope[iz, ix] < 0.3) & (W.mount[iz, ix] < 0.25) & (rd > 7.0)
    cd = np.full(W.h.shape, 1e9, np.float32)
    (z0, z1), (x0, x1) = W.creek_win
    cd[z0:z1, x0:x1] = W.creek_dist
    ok &= cd[iz, ix] > 14
    hh = W.h[iz, ix]
    ok &= ~((((gx - SWAMP[0]) ** 2 + (gz - SWAMP[1]) ** 2) < (SWAMP_R + 40) ** 2) & (hh < W.swamp_level + 0.4))
    ok &= ~((((gx - LAKE[0]) ** 2 + (gz - LAKE[1]) ** 2) < (LAKE_R + 30) ** 2) & (hh < W.lake_level + 0.4))
    pois = [(p if p else W.bridge_p, r) for (_, _, p, r) in POIS]
    d_att = np.full(len(gx), 1e9)
    for (px, pz), pr in pois:
        d = np.hypot(gx - px, gz - pz) - pr
        ok &= d > 25
        d_att = np.minimum(d_att, np.maximum(d, 0))
    sel = np.nonzero(ok)[0]
    gx, gz, rd, d_att, foot = gx[sel], gz[sel], rd[sel], d_att[sel], foot[sel]
    dv = np.full(len(gx), 1e9)
    for s_ in W.scenes:
        dv = np.minimum(dv, np.hypot(gx - s_["p"][0], gz - s_["p"][1]))
    alive = np.ones(len(gx), bool)
    # 길가를 조금 더 좋아하고, 후보마다 고정된 흔들림(0.72~1)을 곱해 격자처럼 고르게 박힌 무늬가 되지 않게
    pref = np.where(rd < 40, 1.0, 0.82) * rng.uniform(0.72, 1.0, len(gx))
    near = lambda c, r: np.hypot(gx - c[0], gz - c[1]) < r
    types = list(SCENES)
    n0 = len(W.scenes)
    tries = 0
    while True:
        val = np.minimum(d_att + 30.0, dv)
        sc = np.where(alive & (val >= SCENE_STEP), val * pref, -1)      # 아직 볼거리에서 SCENE_STEP 넘게 먼 후보만
        i = int(np.argmax(sc))
        if sc[i] < 0:
            break
        x, z = float(gx[i]), float(gz[i])
        road = rd[i] < 40
        # 장면 틀 고르기: 길가/들판 선호 × 둘레 맥락 × 같은 틀과의 거리
        w = {}
        for t in types:
            R, wr, wf = SCENES[t]
            v = wr if road else wf
            if math.hypot(x - GRAVE_C[0], z - GRAVE_C[1]) < 260 or math.hypot(x - CATH[0], z - CATH[1]) < 200:
                v *= {"family": 1.5, "chapel": 1.3}.get(t, 1.0)
            if math.hypot(x - DRAGON[0], z - DRAGON[1]) < DRAGON_R + 90:
                v *= {"battle": 1.7, "execution": 1.3}.get(t, 1.0)
            if math.hypot(x - FOREST_SW[0][0], z - FOREST_SW[0][1]) < FOREST_SW[1] + 90 or \
                    math.hypot(x - FOREST_NE[0][0], z - FOREST_NE[0][1]) < FOREST_NE[1] + 70:
                v *= {"camp": 1.4, "crystal": 1.3}.get(t, 1.0)
            if math.hypot(x - SWAMP[0], z - SWAMP[1]) < SWAMP_R + 120:
                v *= {"crystal": 1.3, "shrine": 1.2}.get(t, 1.0)
            if math.hypot(x - VILLAGE[0], z - VILLAGE[1]) < 220:
                v *= {"camp": 1.3, "execution": 1.3}.get(t, 1.0)
            if foot[i]:                                          # 벼랑 발치: 바위틈 수정, 벼랑 사당, 야영지
                v *= {"crystal": 1.7, "shrine": 1.4, "camp": 1.3, "chapel": 0.6, "battle": 0.6}.get(t, 1.0)
            same = [math.hypot(x - s_["p"][0], z - s_["p"][1]) for s_ in W.scenes if s_["type"] == t]
            v *= min(1.0, (min(same) if same else 1e9) / 280.0) ** 1.5
            w[t] = v * rng.uniform(0.8, 1.2)
        placed = False
        for t in sorted(w, key=lambda k: -w[k]):
            if lay_scene(W, P, t, x, z):
                placed = True
                break
        tries += 1
        if placed:
            dv = np.minimum(dv, np.hypot(gx - x, gz - z))
        else:
            alive &= ~near((x, z), 6.0)
    cnt = {}
    for s_ in W.scenes[n0:]:
        cnt[s_["type"]] = cnt.get(s_["type"], 0) + 1
    log("작은 장면 %d 곳 (시도 %d): %s" % (len(W.scenes) - n0, tries, ", ".join("%s %d" % kv for kv in sorted(cnt.items()))))
    P.rng = main_rng


def lay_fields(W, P):
    """넓은 들판의 채움 소품 (고목·덤불·바위·꽃·해골), 길가 등불·울타리.
    v2: 외딴 무덤 무리·폐허 무더기는 작은 장면(lay_vignettes)이 맡는다. 들판이 좁아져(약 0.55 배) 채움 개수도 줄였다"""
    rng = P.rng
    open_ = (W.mount < 0.15).astype(np.float32) * (W.slope < 0.45)
    # 채움 소품은 뭉쳐서 놓는다 (덤불숲과 빈터가 번갈아 온다. 고르게 흩으면 소금·후추처럼 단조롭다)
    af = in_mask(W, open_ * (0.2 + 1.6 * ss(fbm(W.X, W.Z, 1 / 170, 3, 1401), -0.05, 0.25)))
    P.scatter("dead_tree_a", int(130 * DEAD_TREE_CUT), af)
    P.scatter("dead_tree_b", int(100 * DEAD_TREE_CUT), af)
    P.scatter("dead_tree_c", int(70 * DEAD_TREE_CUT), af)
    P.scatter("bush_dead", 380, af)
    P.scatter("bramble", 280, af)
    P.scatter("rock_a", 170, af)
    P.scatter("rock_c", 250, af)
    P.scatter("rock_b", 35, af)
    P.scatter("rock_flat", 30, af)
    P.scatter("stump", 45, af)
    P.scatter("log_fallen", 25, af)
    P.scatter("roots", 20, af)
    P.scatter("flower_lily", 70, af)
    P.scatter("mushroom_glow", 30, af)
    P.scatter("skull", 60, af)
    P.scatter("bone_pile", 15, af)
    # 길가 등불 (장면이 없는 긴 길 구간만). 다른 길 위에 떨어지지 않게 길 검사를 켠다 (자기 길은 반폭 + 1.4 라 통과)
    sc = np.array([s_["p"] for s_ in W.scenes]) if W.scenes else np.zeros((0, 2))
    pois = [(p if p else W.bridge_p, r) for (_, _, p, r) in POIS if r < 100]      # 작은 장소 (큰 늪·숲·묘지 안 긴 길은 등불을 둔다)
    n_l = 0
    for c, hw in W.road_curves:
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        nxt = rng.uniform(25, 60)
        side = 1
        for i in range(1, len(c) - 1):
            if s[i] < nxt:
                continue
            d = c[i + 1] - c[i - 1]
            d /= np.linalg.norm(d)
            x, z = c[i] + np.array([d[1], -d[0]]) * side * (hw + 1.4)
            if len(sc) and np.min((sc[:, 0] - x) ** 2 + (sc[:, 1] - z) ** 2) < 45 ** 2 or \
                    any((x - px) ** 2 + (z - pz) ** 2 < (pr + 15) ** 2 for (px, pz), pr in pois):
                nxt = s[i] + 20
                continue
            if P.put("lantern", x, z, yaw=yaw_to(-d[1] * side, d[0] * side)):
                side = -side
                n_l += 1
            nxt = s[i] + rng.uniform(70, 110)
    log("길가 등불", n_l)
    # 길가 울타리 조각 (다른 길과 겹치지 않게 길 검사, 검사 반지름은 울타리 두께 쪽으로 줄인다)
    for c, hw in W.road_curves:
        for i in range(0, len(c), 23):
            if rng.random() < 0.18:
                d = c[min(i + 1, len(c) - 1)] - c[max(i - 1, 0)]
                d /= np.linalg.norm(d) + 1e-9
                sd = rng.choice([-1, 1])
                x, z = c[i] + np.array([d[1], -d[0]]) * sd * (hw + 2.4)
                P.put("fence", x, z, yaw=math.degrees(math.atan2(-d[1], d[0])), tilt=8, r=1.0)


def lay_groves(W, P):
    """들판 곳곳의 작은 숲과 언덕 위 바위 무리 (먼 데서 보이는 표지)"""
    rng = P.rng
    open_ = (W.mount < 0.2).astype(np.float32) * (W.slope < 0.5)
    a = in_mask(W, open_)
    for k in range(24):                     # v2: 들판이 좁아져 46 → 24
        p = a(rng)
        if p is None:
            continue
        x, z = p
        if any((x - px) ** 2 + (z - pz) ** 2 < (pr + 30) ** 2 for (px, pz), pr in ((GRAVE_C, GRAVE_R[0]), (SWAMP, SWAMP_R), (DRAGON, DRAGON_R), (CATH, 80), (VILLAGE, 80), (ALTAR, 60))):
            continue
        if any((x - s_["p"][0]) ** 2 + (z - s_["p"][1]) ** 2 < (s_["r"] + 30) ** 2 for s_ in W.scenes):
            continue
        n = int(rng.integers(8, 26))
        R = rng.uniform(14, 34)
        kinds = ["dead_tree_a", "dead_tree_a", "dead_tree_c", "dead_tree_b", "bramble", "bush_dead", "bush_dead", "rock_c", "stump"]
        for j in range(n * 3):
            if n <= 0:
                break
            ang = rng.uniform(0, 2 * math.pi)
            d = math.sqrt(rng.random()) * R
            if P.put(kinds[int(rng.integers(0, len(kinds)))], x + math.cos(ang) * d, z + math.sin(ang) * d, stamp=("leaves", 1.8)):
                n -= 1
        if rng.random() < 0.5:
            P.put("mushroom_glow", x + rng.normal(0, 5), z + rng.normal(0, 5))
    # 언덕 꼭대기 바위 무리
    hb = W.h - box_blur(W.h, 40)
    tops = ss(hb, 2.0, 7.0) * open_
    a2 = in_mask(W, tops)
    for k in range(22):
        p = a2(rng)
        if p is None:
            continue
        x, z = p
        for j in range(int(rng.integers(3, 8))):
            nm = ["rock_b", "rock_flat", "cliff_b", "rock_a", "rock_b"][j % 5]
            P.put(nm, x + rng.normal(0, 6), z + rng.normal(0, 6), s=rng.uniform(0.6, 1.0) if nm == "cliff_b" else None, slope=None,
                  stamp=("moss", 1.4))


def lay_effects(W, P):
    rng = P.rng
    # 묘지와 제단
    for i in range(6):
        x, z = in_disk(GRAVE_C, 120)(rng)
        W.fx.append({"type": "mist", "p": [float(x), P.height(x, z) + 0.4, float(z)], "r": 32})
    for i in range(4):
        x, z = in_disk(GRAVE_C, 110)(rng)
        W.fx.append({"type": "wisps", "p": [float(x), P.height(x, z) + 1.0, float(z)], "r": 24})
    W.fx.append({"type": "soulfire", "p": [ALTAR[0], P.height(*ALTAR) + 1.2, ALTAR[1]], "r": 9})
    W.fx.append({"type": "wisps", "p": [ALTAR[0], P.height(*ALTAR) + 1.0, ALTAR[1]], "r": 26})
    W.fx.append({"type": "soulfire", "p": [CRYPT[0], P.height(CRYPT[0], CRYPT[1] - 10) + 1.0, CRYPT[1] - 10], "r": 6})
    W.fx.append({"type": "wisps", "p": [CATH[0], P.height(*CATH) + 2.0, CATH[1]], "r": 40})
    for i in range(9):
        x, z = in_disk(SWAMP, SWAMP_R - 30)(rng)
        W.fx.append({"type": "mist", "p": [float(x), max(P.height(x, z), W.swamp_level) + 0.3, float(z)], "r": 42})
    for i in range(5):
        x, z = in_disk(SWAMP, SWAMP_R - 40)(rng)
        W.fx.append({"type": "fireflies", "p": [float(x), max(P.height(x, z), W.swamp_level) + 1.5, float(z)], "r": 34})
    for i in range(4):
        x, z = in_disk(DRAGON, DRAGON_R - 40)(rng)
        W.fx.append({"type": "mist", "p": [float(x), P.height(x, z) + 0.4, float(z)], "r": 40})
    for i in range(3):
        x, z = in_disk(DRAGON, 80)(rng)
        W.fx.append({"type": "wisps", "p": [float(x), P.height(x, z) + 1.0, float(z)], "r": 30})
    for i in range(2):                     # 안개 판이 한 점에 겹겹이 쌓이지 않게 넓게
        x, z = in_disk(VILLAGE, 75)(rng)
        W.fx.append({"type": "mist", "p": [float(x), P.height(x, z) + 0.4, float(z)], "r": 30})
    # 영혼 불티와 불꽃이 없던 장소
    for c, r in ((VILLAGE, 34), (TOWER, 18), (GATE, 20), (LAKE, 40)):
        x, z = c[0], c[1] - (14 if c == GATE else 0)
        y = max(P.height(x, z), W.lake_level if c == LAKE else -1e9)
        W.fx.append({"type": "wisps", "p": [float(x), y + 1.0, float(z)], "r": r})
    W.fx.append({"type": "soulfire", "p": [VILLAGE[0] + 2.0, P.height(VILLAGE[0] + 2.0, VILLAGE[1] - 2.5) + 0.6, VILLAGE[1] - 2.5], "r": 5})
    W.fx.append({"type": "soulfire", "p": [TOWER[0], P.height(*TOWER) + 1.0, TOWER[1]], "r": 6})
    # 들판 오목한 곳에 낮게 깔린 골짜기 안개
    hollow = (W.h - box_blur(W.h, 60) < -2.5) * (W.mount < 0.15) * (W.slope < 0.45) * (W.road_dist > 12)
    ha = in_mask(W, hollow.astype(np.float32))
    got, spots = 0, []
    for i in range(400):
        if got >= 9:
            break
        p = ha(rng)
        if p is None or P.under_water(p[0], p[1]):
            continue
        if any((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 < 125 ** 2 for q in spots):
            continue
        spots.append(p)
        W.fx.append({"type": "mist", "p": [float(p[0]), P.height(*p) + 0.4, float(p[1])], "r": 35})
        got += 1
    # 제단·묘지 광원
    for i in range(6):
        a = i / 6 * 2 * math.pi
        x, z = ALTAR[0] + math.cos(a) * 9, ALTAR[1] + math.sin(a) * 9
        W.lights.append({"p": [round(x, 2), round(P.height(x, z) + 2.2, 2), round(z, 2)], "c": SOUL, "i": 3.0, "r": 8.0, "flicker": True})


LIGHT_TRIM = {"candles": 0, "mushroom_glow": 0, "mushroom_toxic": 0, "lotus_glow": 1}   # 광원 예산을 넘는 곳에서 먼저 빼는 작은 광원


def trim_lights(W, P, limit=44, radius=80.0, step=4.0):
    """LightCuller(반지름 80 m, 최대 48) 예산: 걸을 수 있는 범위의 4 m 격자 어디서도 80 m 안 점광원이 limit 를 넘지 않게
    작은 광원 소품(초·버섯·연꽃)을 몰린 곳에서부터 뺀다. 등불·화로·수정·랜드마크·따로 놓은 광원은 빼지 않는다"""
    rng = P.rng
    (bx0, bz0), (bx1, bz1) = BOUNDS
    pos, pri, src = [], [], []
    for k, o in enumerate(P.objects):
        m = P.meta.get(o["a"], {})
        if m.get("light") and m.get("kind") != "tree":
            pos.append((o["p"][0], o["p"][2]))
            pri.append(LIGHT_TRIM.get(o["a"], 9))
            src.append(k)
    for l in W.lights:
        pos.append((l["p"][0], l["p"][2]))
        pri.append(9)
        src.append(-1)
    L = np.array(pos, np.float64)
    pri = np.array(pri)
    g = np.arange(bx0 + step / 2, bx1, step)
    GX, GZ = np.meshgrid(g, g)
    gx, gz = GX.ravel(), GZ.ravel()
    cnt = np.zeros(len(gx), np.int32)
    for c0 in range(0, len(gx), 3000):
        d2 = (gx[c0:c0 + 3000, None] - L[None, :, 0]) ** 2 + (gz[c0:c0 + 3000, None] - L[None, :, 1]) ** 2
        cnt[c0:c0 + 3000] = (d2 < radius * radius).sum(1)
    before = int(cnt.max())
    alive = np.ones(len(L), bool)
    removed = 0
    while cnt.max() > limit:
        i = int(np.argmax(cnt))
        d2 = (L[:, 0] - gx[i]) ** 2 + (L[:, 1] - gz[i]) ** 2
        cand = np.nonzero(alive & (d2 < radius * radius) & (pri < 9))[0]
        if len(cand) == 0:
            log("광원 예산: (%.0f, %.0f) 80 m 안 %d 개 — 뺄 수 있는 작은 광원이 없다" % (gx[i], gz[i], cnt[i]))
            break
        lo = cand[pri[cand] == pri[cand].min()]
        j = int(lo[int(rng.integers(0, len(lo)))])
        alive[j] = False
        removed += 1
        cnt -= ((gx - L[j, 0]) ** 2 + (gz - L[j, 1]) ** 2 < radius * radius).astype(np.int32)
    drop = set(src[j] for j in np.nonzero(~alive)[0] if src[j] >= 0)
    if drop:
        for k in drop:
            a = P.objects[k]["a"]
            P.count[a] -= 1
        P.objects = [o for k, o in enumerate(P.objects) if k not in drop]
    log("광원 예산: 80 m 안 최대 %d → %d (작은 광원 %d 개 뺌), 점광원 합 %d" % (before, int(cnt.max()), removed, int(alive.sum())))


# ─────────────────────────── 층·풀 ───────────────────────────
def paint(W, P):
    log("지형 층 칠하기")
    X, Z, h, sl = W.X, W.Z, W.h, W.slope
    n1 = fbm(X, Z, 1 / 90, 4, 1001)
    n2 = fbm(X, Z, 1 / 35, 3, 1002)
    n3 = fbm(X, Z, 1 / 14, 2, 1003)
    lw = {}
    lw["grass"] = np.ones(h.shape, np.float32)

    def over(name, a):
        a = np.clip(a, 0, 1).astype(np.float32)
        for k in lw:
            lw[k] *= (1 - a)
        lw[name] = lw.get(name, np.zeros(h.shape, np.float32)) + a

    ex = ((X - GRAVE_C[0]) / (GRAVE_R[0] + 20)) ** 2 + ((Z - GRAVE_C[1]) / (GRAVE_R[1] + 20)) ** 2
    grave = ss(-ex, -1.0, -0.7)
    gzn = W.gz / (sl + 1e-4)
    m1 = fbm(X, Z, 1 / 320, 3, 1004)
    m2 = fbm(X, Z, 1 / 260, 3, 1005)
    m3 = fbm(X, Z, 1 / 200, 3, 1006)
    W.dry = ss(m2, 0.12, 0.45)                                       # 마른 풀밭
    over("moss", ss(m1, 0.05, 0.4) * 0.65 * (0.6 + 0.4 * ss(n2, -0.3, 0.3)))
    over("leaves", ss(m3, 0.25, 0.5) * 0.55 * ss(n2, -0.2, 0.4))     # 낙엽이 쌓인 곳
    over("dirt", W.dry * 0.45 * ss(n3, -0.5, 0.3))
    over("moss", ss(n1, 0.05, 0.45) * 0.55 + grave * ss(n2, -0.1, 0.4) * 0.5 + ss(gzn, 0.2, 0.9) * ss(sl, 0.15, 0.4) * 0.5)
    over("dirt", ss(n2, 0.35, 0.65) * 0.55 + ss(sl, 0.3, 0.55) * 0.6 + ss(-W.road_dist, -(W.road_hw + 3.5), -(W.road_hw + 1.0)) * 0.55)
    over("leaves", W.forest * ss(n2, -0.4, 0.3) * 0.95)
    dr = np.sqrt((X - DRAGON[0]) ** 2 + (Z - DRAGON[1]) ** 2)
    dre = dr / (1 + 0.22 * fbm(X, Z, 1 / 90, 3, 1010))
    ash = ss(-dre, -DRAGON_R + 5, -DRAGON_R + 70) * (0.55 + 0.45 * ss(n2, -0.3, 0.3))
    ar = np.sqrt((X - ALTAR[0]) ** 2 + (Z - ALTAR[1]) ** 2)
    ash = np.maximum(ash, ss(-ar, -20, -9) * 0.8)
    over("ash", ash)
    sw = np.sqrt((X - SWAMP[0]) ** 2 + (Z - SWAMP[1]) ** 2)
    lk = np.sqrt((X - LAKE[0]) ** 2 + (Z - LAKE[1]) ** 2)
    mud = ss(-sw, -SWAMP_R - 20, -SWAMP_R + 30) * ss(-(h - W.swamp_level), -1.6, -0.1)
    mud = np.maximum(mud, ss(-lk, -LAKE_R - 20, -LAKE_R + 10) * ss(-(h - W.lake_level), -1.0, -0.1))
    (z0, z1), (x0, x1) = W.creek_win
    cr = np.zeros(h.shape, np.float32)
    cr[z0:z1, x0:x1] = ss(-W.creek_dist, -(W.creek_wt * 0.75), -(W.creek_wt * 0.35))
    mud = np.maximum(mud, cr * 0.9)
    over("mud", mud * (0.85 + 0.15 * ss(n3, -0.3, 0.3)))
    # 장소 바닥: 들판과 구별되게. 걷는 바닥은 path·rock 위주 (dirt 는 grass 와 색 차이가 작다. ash 는 용의 무덤 고유색)
    vil = np.sqrt((X - VILLAGE[0]) ** 2 + (Z - VILLAGE[1]) ** 2)
    cd = np.sqrt((X - CATH[0]) ** 2 + (Z - CATH[1]) ** 2)
    gd = np.sqrt((X - GATE[0]) ** 2 + (Z - (GATE[1] - 18)) ** 2)
    td = np.sqrt((X - TOWER[0]) ** 2 + (Z - TOWER[1]) ** 2)
    over("dirt", ss(-vil, -75, -40) * 0.55 * ss(n3, -0.5, 0.3))                      # 마을: 밟힌 흙
    over("path", ss(-vil, -44, -28) * 0.65 * (0.7 + 0.3 * ss(n2, -0.3, 0.3)))        # 집 사이 길과 우물 둘레
    over("path", ss(-cd, -50, -28) * 0.7 * (0.75 + 0.25 * ss(n3, -0.4, 0.4)))        # 대성당 고원: 돌바닥
    over("rock", ss(-cd, -50, -28) * 0.25 * ss(n2, -0.1, 0.4))                       # 깨진 돌
    over("path", ss(-gd, -40, -22) * 0.6 * (0.75 + 0.25 * ss(n3, -0.4, 0.4)))        # 봉인문 앞 마당
    over("rock", ss(-gd, -40, -22) * 0.3 * ss(n2, -0.1, 0.4))
    over("rock", ss(-td, -26, -14) * 0.5)                                            # 망루 꼭대기
    W.place_floor = np.maximum.reduce([ss(-vil, -60, -35), ss(-cd, -50, -28), ss(-gd, -40, -22), ss(-td, -26, -14)]).astype(np.float32)
    over("rock", ss(sl, 0.62, 1.0) + W.mount * ss(sl, 0.32, 0.6) * 0.85)
    path = ss(-W.road_dist, -(W.road_hw + 0.9), -(W.road_hw - 0.6)) * (0.8 + 0.2 * ss(n3, -0.4, 0.4))
    over("path", path)
    # 소품 자리 칠하기
    stamp_layers(W, P, lw, n3)
    order = [n for n, _, _ in LAYERS]
    tot = sum(lw[n] for n in order) + 1e-6
    for n in order:
        lw[n] = lw[n] / tot
    W.lw = lw


def stamp_layers(W, P, lw, n3):
    for (x, z, r, kind) in P.stamps:
        if kind == "clear" or kind not in lw:
            continue
        rr = max(r, 0.8)
        rs, cs, d = disk(W.h.shape, x, z, rr * 1.6)
        a = ss(-d, -rr * 1.6, -rr * 0.6) * (0.75 + 0.25 * n3[rs, cs])
        for k in lw:
            lw[k][rs, cs] *= (1 - a)
        lw[kind][rs, cs] += a


def details(W, P):
    log("풀 밀도")
    X, Z, h, sl, lw = W.X, W.Z, W.h, W.slope, W.lw
    n1 = fbm(X, Z, 1 / 25, 3, 1101)
    n2 = fbm(X, Z, 1 / 60, 3, 1102)
    n3 = fbm(X, Z, 1 / 9, 2, 1103)
    dry = np.ones(h.shape, np.float32)
    sw = np.sqrt((X - SWAMP[0]) ** 2 + (Z - SWAMP[1]) ** 2)
    lk = np.sqrt((X - LAKE[0]) ** 2 + (Z - LAKE[1]) ** 2)
    in_sw = sw < SWAMP_R + 40
    in_lk = lk < LAKE_R + 30
    dry = np.where(in_sw, ss(h - W.swamp_level, 0.05, 0.4), dry)
    dry = np.where(in_lk, np.minimum(dry, ss(h - W.lake_level, 0.05, 0.4)), dry)
    pool = W.pool_mask
    dry = np.where(pool, np.minimum(dry, ss(h - W.pool_level, 0.05, 0.3)), dry)
    flat = 1 - ss(sl, 0.55, 0.9)
    road = ss(W.road_dist, W.road_hw - 0.3, W.road_hw + 1.2)
    base = dry * flat * road * (1 - lw["rock"]) * (1 - lw["path"] * 0.9)
    d = {}
    d["grass_a"] = (lw["grass"] * 1.0 + lw["moss"] * 0.55 + lw["dirt"] * 0.25) * (0.5 + 0.5 * ss(n1, -0.5, 0.4)) * base
    d["grass_b"] = (lw["grass"] * ss(n2, 0.0, 0.45) + lw["mud"] * 0.35) * base * (0.6 + 0.4 * ss(n3, -0.3, 0.4))
    d["grass_dead"] = (lw["dirt"] * 0.55 + lw["ash"] * 0.45 + lw["grass"] * ss(n2, -0.6, -0.2) * 0.5 + lw["leaves"] * 0.2 + W.dry * 0.6) * base
    d["grass_a"] *= (1 - W.dry * 0.45)
    d["fern_a"] = (lw["leaves"] * 0.7 + lw["moss"] * 0.45 + W.forest * 0.5) * ss(n1, -0.25, 0.4) * base
    ex = ((X - GRAVE_C[0]) / GRAVE_R[0]) ** 2 + ((Z - GRAVE_C[1]) / GRAVE_R[1]) ** 2
    vil = np.sqrt((X - VILLAGE[0]) ** 2 + (Z - VILLAGE[1]) ** 2)
    d["weeds"] = (ss(-ex, -1.2, -0.6) * 0.6 + ss(-vil, -110, -40) * 0.6 + lw["dirt"] * 0.25) * ss(n3, -0.2, 0.5) * base
    edge_sw = in_sw * ss(-np.abs(h - W.swamp_level - 0.1), -0.9, -0.15)
    edge_lk = in_lk * ss(-np.abs(h - W.lake_level - 0.1), -0.8, -0.15)
    edge_pool = pool * ss(-np.abs(h - W.pool_level - 0.1), -0.6, -0.1)
    (z0, z1), (x0, x1) = W.creek_win
    cr = np.zeros(h.shape, np.float32)
    cr[z0:z1, x0:x1] = ss(-np.abs(W.creek_dist - W.creek_wt * 0.6), -3.0, -0.5)
    gy = ss(-ex, -1.25, -0.8)                     # 묘지 안: 묘비가 가려지지 않게 키 큰 풀을 줄인다
    d["grass_b"] *= (1 - gy * 0.9)
    d["fern_a"] *= (1 - gy * 0.9)
    d["grass_a"] *= (1 - gy * 0.35)
    d["weeds"] = np.clip(d["weeds"] + gy * 0.35 * ss(n1, -0.3, 0.5) * base, 0, 1)
    d["reed"] = np.clip(np.maximum.reduce([edge_sw, edge_lk, edge_pool, cr * 0.7]), 0, 1) * flat * road * (0.5 + 0.5 * ss(n1, -0.4, 0.3))
    # 장소 바닥(마을·대성당 고원·봉인문 앞·망루)은 풀을 걷어 바닥 칠이 보이게 (Unity 에서는 풀이 지형 층을 덮는다)
    pf = W.place_floor
    for k, f in (("grass_a", 0.65), ("grass_b", 0.65), ("grass_dead", 0.65), ("fern_a", 0.5)):
        d[k] = d[k] * (1 - f * pf)
    # 소품 자리는 비운다
    clear = np.ones(h.shape, np.float32)
    for (x, z, r, kind) in P.stamps:
        rr = max(r * 0.9, 0.35)
        rs, cs, dd = disk(h.shape, x, z, rr + 0.8)
        clear[rs, cs] *= ss(dd, rr * 0.7, rr + 0.6)
    for k in d:
        d[k] = np.clip(d[k] * clear, 0, 1)
    W.det = d


# ─────────────────────────── 물 ───────────────────────────
def water_planes(W):
    planes = []
    planes.append({"p": [SWAMP[0], round(W.swamp_level, 3), SWAMP[1]], "size": [2 * (SWAMP_R + 40), 2 * (SWAMP_R + 40)], "yaw": 0})
    planes.append({"p": [LAKE[0], round(W.lake_level, 3), LAKE[1]], "size": [2 * (LAKE_R + 30), 2 * (LAKE_R + 30)], "yaw": 0})
    # 다리 아래 물웅덩이: 판 한 장 (여러 장을 이어 붙이면 겹친 곳이 두 번 그려져 얼룩진다).
    # 시작~끝 현(弦) 방향으로 놓고, 곡선이 현에서 벗어난 만큼 폭을 넓힌다 (물 밖은 둑이 가린다)
    c, s = W.creek, W.creek_s
    s0, s1 = W.pool_range
    i0, i1 = int(np.searchsorted(s, s0)), min(int(np.searchsorted(s, s1)), len(c) - 1)
    a, b = c[i0], c[i1]
    dv = b - a
    ln = float(np.linalg.norm(dv))
    du = dv / (ln + 1e-9)
    seg = c[i0:i1 + 1] - a
    dev = float(np.abs(seg[:, 0] * du[1] - seg[:, 1] * du[0]).max())
    wd = 15.0 + 2 * dev
    mid = (a + b) / 2
    yaw = math.degrees(math.atan2(dv[0], dv[1]))
    planes.append({"p": [round(float(mid[0]), 2), round(W.pool_level, 3), round(float(mid[1]), 2)], "size": [round(wd, 2), round(ln, 2)], "yaw": round(yaw, 2)})
    W.pool_rects = [(mid, du, ln, wd)]
    log("다리 웅덩이 물 판 한 장: 길이 %.1f m, 폭 %.1f m (곡선 벗어남 %.1f m)" % (ln, wd, dev))
    return planes


def make_pool_mask(W):
    m = np.zeros(W.h.shape, bool)
    for mid, dv, ln, wd in W.pool_rects:
        rs, cs, d = disk(W.h.shape, mid[0], mid[1], max(ln, wd))
        zz, xx = np.mgrid[rs, cs]
        u = (xx - mid[0]) * dv[0] + (zz - mid[1]) * dv[1]
        v = -(xx - mid[0]) * dv[1] + (zz - mid[1]) * dv[0]
        m[rs, cs] |= (np.abs(u) <= ln / 2) & (np.abs(v) <= wd / 2)
    W.pool_mask = m

    def in_pool(x, z):
        xi, zi = int(round(x)), int(round(z))
        if 0 <= xi < RES and 0 <= zi < RES:
            return bool(m[zi, xi])
        return False
    W.in_pool = in_pool
    # 상자 안인데 개울 밖에서 물보다 낮은 곳은 올린다
    (z0, z1), (x0, x1) = W.creek_win
    cd = np.full(W.h.shape, 1e9, np.float32)
    cd[z0:z1, x0:x1] = W.creek_dist
    bad = m & (cd > 6.5) & (W.h < W.pool_level + 0.4)
    W.h[bad] = W.pool_level + 0.4
    log("물웅덩이 상자 밖 낮은 칸 올림", int(bad.sum()))
    pool_rim(W)


def pool_rim(W):
    """물 판 가장자리가 공중에 끝나지 않게: 판 합집합의 경계에서 1.2 m 안팎은 수면 + 0.3,
    그 밖으로는 기울기 0.35 로 내려간다 (판 끝은 개울을 가로지르는 낮은 턱이 된다)"""
    lev = W.pool_level
    rects = W.pool_rects
    # 경계 위 점들: 판 네 변을 0.25 m 간격으로 찍고, 다른 판 안에 든 점은 뺀다
    pts = []
    for mid, dv, ln, wd in rects:
        nv = np.array([-dv[1], dv[0]])
        for b in (-1, 1):
            for t in np.arange(-ln / 2, ln / 2 + 1e-6, 0.25):
                pts.append(mid + dv * t + nv * b * wd / 2)
        for b in (-1, 1):
            for t in np.arange(-wd / 2, wd / 2 + 1e-6, 0.25):
                pts.append(mid + dv * b * ln / 2 + nv * t)
    pts = np.array(pts)

    def inside(px, pz, shrink=0.0):
        r = np.zeros(px.shape, bool)
        for mid, dv, ln, wd in rects:
            u = (px - mid[0]) * dv[0] + (pz - mid[1]) * dv[1]
            v = -(px - mid[0]) * dv[1] + (pz - mid[1]) * dv[0]
            r |= (np.abs(u) < ln / 2 - shrink) & (np.abs(v) < wd / 2 - shrink)
        return r
    pts = pts[~inside(pts[:, 0], pts[:, 1], 0.05)]
    R = 14
    x0, x1 = int(pts[:, 0].min() - R), int(pts[:, 0].max() + R) + 1
    z0, z1 = int(pts[:, 1].min() - R), int(pts[:, 1].max() + R) + 1
    zz, xx = np.mgrid[z0:z1, x0:x1].astype(np.float64)
    d = np.full(xx.shape, 1e9)
    for k in range(0, len(pts), 256):
        p = pts[k:k + 256]
        dd = np.sqrt((xx[..., None] - p[:, 0]) ** 2 + (zz[..., None] - p[:, 1]) ** 2).min(-1)
        d = np.minimum(d, dd)
    need = lev + 0.3 - 0.35 * np.maximum(d - 1.2, 0)
    sub = W.h[z0:z1, x0:x1]
    up = need > sub
    log("물웅덩이 가장자리 턱: 올린 칸 %d, 최대 %.2f m" % (int(up.sum()), float((need - sub)[up].max()) if up.any() else 0.0))
    W.h[z0:z1, x0:x1] = np.maximum(sub, need).astype(np.float32)


def bridge_ramps(W):
    """다리 양 끝: 상판 끝(로컬 |x| 6.4 m 너머)의 둑을 상판 높이까지 올려 턱 없이 올라서게 한다
    (개울 깎기·길 홈이 둑을 0.5~0.8 m 낮춘 것을 메운다)"""
    bx, bz = W.bridge_p
    r = W.bridge_axis
    rs, cs, d = disk(W.h.shape, bx, bz, 24)
    X, Z = W.X[rs, cs] - bx, W.Z[rs, cs] - bz
    au = np.abs(X * r[0] + Z * r[1])
    av = np.abs(-X * r[1] + Z * r[0])
    tgt = W.bridge_bank - 0.02 + 0.18              # 다리 원점 + 0.18 = 충돌 메쉬 상판 끝(원점 + 0.18~0.26) 바로 아래
    wu = ss(-au, -20, -8.5) * (au > 6.4)          # 8.5 m 까지 꽉, 20 m 에서 원래 지형
    k = ss(au, 8, 12)
    wv = ss(-av, -(4.0 + 3.0 * k), -(2.6 + 2.0 * k))  # 끝 가까이는 다리 폭, 멀어지면 길이 휘는 폭까지
    w = wu * wv
    sub = W.h[rs, cs]
    new = np.maximum(sub, sub * (1 - w) + tgt * w)
    log("다리 양 끝 둑 올림: 최대 %.2f m" % float((new - sub).max()))
    W.h[rs, cs] = new


# ─────────────────────────── 저장 ───────────────────────────
def save_png_rgba(path, chans):
    """chans: 0~1 배열 4개 (행 0 = 남쪽) → PNG (맨 윗줄 = 북쪽)"""
    a = np.stack([np.clip(c[:SIZE, :SIZE] * 255 + 0.5, 0, 255).astype(np.uint8) for c in chans], -1)
    Image.fromarray(np.flipud(a), 'RGBA').save(path, optimize=False, compress_level=6)


def save_all(W, P, out, water):
    data = os.path.join(out, "Data~")
    os.makedirs(data, exist_ok=True)
    log("저장: 높이")
    hq = np.clip(W.h / HMAX, 0, 1) * 65535 + 0.5
    hq.astype('<u2').tofile(os.path.join(data, "height.r16"))
    log("저장: 층 무게")
    names = [n for n, _, _ in LAYERS]
    z = np.zeros(W.h.shape, np.float32)
    # 칸 값의 합이 255 가 되게 (반올림 오차는 가장 큰 층에)
    ws = np.stack([W.lw[n][:SIZE, :SIZE] for n in names], -1)
    q = np.floor(ws * 255).astype(np.int32)
    rem = 255 - q.sum(-1)
    top = np.argmax(ws, -1)
    np.put_along_axis(q, top[..., None], np.take_along_axis(q, top[..., None], -1) + rem[..., None], -1)
    q = np.clip(q, 0, 255).astype(np.uint8)
    for k in range(2):
        img = np.flipud(q[..., k * 4:(k + 1) * 4])
        Image.fromarray(np.ascontiguousarray(img), 'RGBA').save(os.path.join(data, "splat_%d.png" % k))
    log("저장: 풀")
    dn = [n for n, _, _, _ in DETAILS]
    ch = [W.det[n] for n in dn] + [z] * (8 - len(dn))
    save_png_rgba(os.path.join(data, "detail_0.png"), ch[0:4])
    save_png_rgba(os.path.join(data, "detail_1.png"), ch[4:8])
    log("저장: 나무·소품")
    json.dump({"prototypes": P.protos, "instances": P.trees}, open(os.path.join(data, "trees.json"), "w"), separators=(",", ":"))
    for f in W.fx:
        f["p"] = [round(float(v), 2) for v in f["p"]]
    json.dump({"objects": P.objects, "lights": W.lights, "water": water, "fx": W.fx},
              open(os.path.join(data, "objects.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    hs = sample(W.h, *SPAWN)
    pois = []
    for pid, name, p, r in POIS:
        if p is None:
            p = W.bridge_p
        pois.append({"id": pid, "name": name, "p": [round(p[0], 2), round(sample(W.h, *p), 2), round(p[1], 2)], "r": r, "map": True})
    world = {
        "version": 1, "size": SIZE, "height": HMAX, "heightRes": RES, "tiles": 2,
        "splatRes": SIZE, "detailRes": SIZE, "seaLevel": 0,
        "spawn": {"p": [SPAWN[0], round(hs + 0.1, 2), SPAWN[1]], "yaw": 0},
        "layers": [{"name": n, "albedo": "ground_%s_albedo.jpg" % n, "normal": "ground_%s_normal.png" % n, "tile": t, "smoothness": sm}
                   for n, t, sm in LAYERS],
        "details": [{"asset": a, "maxPerCell": m, "minScale": lo, "maxScale": hi} for a, m, lo, hi in DETAILS],
        "pois": pois,
        "fog": {"color": [0.13, 0.11, 0.22], "density": 0.0048},
        "bounds": {"min": list(BOUNDS[0]), "max": list(BOUNDS[1])},
        "levels": {"swamp": round(W.swamp_level, 3), "lake": round(W.lake_level, 3), "creekPool": round(W.pool_level, 3)},
    }
    json.dump(world, open(os.path.join(data, "world.json"), "w"), ensure_ascii=False, indent=1)


def save_map(W, P, out):
    log("지도")
    pal = {"grass": (0.16, 0.25, 0.21), "moss": (0.2, 0.32, 0.24), "dirt": (0.3, 0.25, 0.25), "mud": (0.16, 0.15, 0.16),
           "rock": (0.27, 0.28, 0.34), "path": (0.62, 0.56, 0.5), "leaves": (0.33, 0.2, 0.16), "ash": (0.55, 0.52, 0.58)}
    col = np.zeros(W.h.shape + (3,), np.float32)
    for n, c in pal.items():
        col += W.lw[n][..., None] * np.array(c, np.float32)
    col = mix_forest(W, col)
    # 언덕 그늘 (북서쪽 빛)
    gx, gz = W.gx, W.gz
    shade = np.clip(0.75 + (-gx * 0.7 + gz * 0.7) * 1.6, 0.35, 1.35)
    col *= shade[..., None]
    hn = (W.h - W.h.min()) / (W.h.max() - W.h.min())
    col *= (0.75 + 0.45 * hn)[..., None]
    wat = np.zeros(W.h.shape, np.float32)
    sw = np.sqrt((W.X - SWAMP[0]) ** 2 + (W.Z - SWAMP[1]) ** 2) < SWAMP_R + 40
    lk = np.sqrt((W.X - LAKE[0]) ** 2 + (W.Z - LAKE[1]) ** 2) < LAKE_R + 30
    wat = np.maximum(wat, (sw & (W.h < W.swamp_level)).astype(np.float32))
    wat = np.maximum(wat, (lk & (W.h < W.lake_level)).astype(np.float32))
    wat = np.maximum(wat, (W.pool_mask & (W.h < W.pool_level)).astype(np.float32))
    col = col * (1 - wat[..., None] * 0.85) + np.array([0.12, 0.14, 0.3], np.float32) * wat[..., None] * 0.85
    # 등고선
    cl = np.abs(((W.h / 8.0) % 1.0) - 0.5) > 0.47
    col *= np.where(cl, 0.82, 1.0)[..., None]
    # 가장자리 어둡게 (양피지 느낌)
    r = np.sqrt(((W.X - 1024) / 1024) ** 2 + ((W.Z - 1024) / 1024) ** 2)
    col *= (1 - 0.5 * ss(r, 0.85, 1.4))[..., None]
    col = np.clip(col, 0, 1)
    img = Image.fromarray((np.flipud(col[:SIZE, :SIZE]) * 255).astype(np.uint8), 'RGB').resize((1024, 1024), Image.LANCZOS)
    img.save(os.path.join(out, "map.png"))
    # 확인용 개요도: 소품 점
    ov = Image.fromarray((np.flipud(col[:SIZE, :SIZE]) * 255).astype(np.uint8), 'RGB')
    px = ov.load()
    colors = {"tree": (40, 70, 50), "grave": (220, 220, 235), "landmark": (255, 120, 255), "light": (255, 230, 120)}
    for t in P.trees:
        x, z = int(t[1]), int(t[2])
        if 0 <= x < SIZE and 0 <= z < SIZE:
            px[x, SIZE - 1 - z] = (20, 35, 25)
    for o in P.objects:
        x, z = int(o["p"][0]), int(o["p"][2])
        c = (230, 230, 240) if o["a"].startswith("grave") else (255, 140, 255) if P.meta.get(o["a"], {}).get("kind") == "landmark" else (255, 220, 150)
        for dx in (0, 1):
            for dz in (0, 1):
                if 0 <= x + dx < SIZE and 0 <= z + dz < SIZE:
                    px[x + dx, SIZE - 1 - z - dz] = c
    scol = {"execution": (255, 70, 70), "chapel": (120, 200, 255), "shrine": (255, 170, 255), "ritual": (200, 90, 255),
            "camp": (255, 160, 60), "crystal": (80, 255, 230), "family": (255, 255, 255), "battle": (255, 220, 60),
            "crossroad": (60, 255, 90)}
    for s_ in W.scenes:                       # 장면: 틀별 색 고리 (확인용)
        x, z = int(s_["p"][0]), int(s_["p"][1])
        c = scol.get(s_["type"], (255, 255, 0))
        for t in range(48):
            a = t / 48 * 2 * math.pi
            for rr in (9, 10):
                u, v = int(x + math.cos(a) * rr), int(z + math.sin(a) * rr)
                if 0 <= u < SIZE and 0 <= v < SIZE:
                    px[u, SIZE - 1 - v] = c
    ov.save(os.path.join(out, "_overview.png"))
    json.dump(W.scenes, open(os.path.join(out, "_scenes.json"), "w"), ensure_ascii=False, indent=0)


def mix_forest(W, col):
    return col * (1 - W.forest[..., None] * 0.35) + np.array([0.1, 0.12, 0.1], np.float32) * W.forest[..., None] * 0.35


def load_manifest(path):
    meta = {}
    files = [path] if os.path.isfile(path) else sorted(glob.glob(os.path.join(path, "manifest_*.json")))
    for f in files:
        d = json.load(open(f))
        for k, v in d.items():
            meta[k] = dict(v.get("meta", {}))
            meta[k]["_size"] = v.get("size")          # Blender 축 (x, y, z) = Unity (x, z, y)
    return meta


def main():
    out = sys.argv[1]
    meta = load_manifest(sys.argv[2])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    log("소품", len(meta), "종")
    W = World()
    W.lights, W.fx, W.scenes = [], [], []
    build_height(W)
    W.forest = np.zeros(W.h.shape, np.float32)
    rng = np.random.default_rng(seed)
    P = Placer(W, meta, rng)
    pads = lay_landmarks(W, P)
    finish_height(W, pads)
    water = water_planes(W)
    make_pool_mask(W)
    bridge_ramps(W)
    gz, gx = np.gradient(W.h)
    W.slope, W.gx, W.gz = np.sqrt(gx * gx + gz * gz), gx, gz
    log("배치: 구조물")
    place_landmarks(W, P)
    lay_altar(W, P)
    lay_graveyard(W, P)
    lay_cathedral(W, P)
    lay_village(W, P)
    lay_gate(W, P)
    lay_tower(W, P)
    lay_tree(W, P)
    log("배치: 늪·용의 무덤·개울·호수")
    lay_swamp(W, P)
    lay_dragon(W, P)
    lay_bridge_creek(W, P)
    lay_lake(W, P)
    log("배치: 작은 장면")
    lay_vignettes(W, P, seed)
    log("배치: 숲·산기슭·들판")
    lay_forest(W, P, FOREST_SW[0], FOREST_SW[1], 1 / 70.0, 1301, clearings=("camp", "crystal", "ritual"))
    lay_forest(W, P, FOREST_NE[0], FOREST_NE[1], 1 / 85.0, 1311, clearings=("crystal", "camp"))
    lay_mountain_foot(W, P)
    lay_groves(W, P)
    lay_fields(W, P)
    lay_effects(W, P)
    trim_lights(W, P)
    paint(W, P)
    details(W, P)
    save_all(W, P, out, water)
    save_map(W, P, out)
    terr = os.path.join(out, "Terrain")
    if not all(os.path.exists(os.path.join(terr, "ground_%s_albedo.jpg" % n)) for n, _, _ in LAYERS):
        log("지형 텍스처 만들기")
        import groundtex
        os.makedirs(terr, exist_ok=True)
        for n, _, _ in LAYERS:
            groundtex.MAKERS[n](terr)
    log("끝. 나무", len(P.trees), "소품", len(P.objects), "광원", len(W.lights), "물", len(water), "효과", len(W.fx),
        "장면", len(W.scenes))
    if P.missing:
        log("manifest 에 없는 소품 (건너뜀):", sorted(P.missing))
    if P.subst or P.sub_skip:
        log("아직 없는 새 소품 → 대체: %s | 대체 없어 건너뜀: %s | 대체 소품에 없어 따로 넣은 광원 %d" % (
            ", ".join("%s→%s %d" % (a, NEW_PROPS[a]["sub"][0], n) for a, n in sorted(P.subst.items())),
            ", ".join("%s %d" % kv for kv in sorted(P.sub_skip.items())) or "없음", P.sub_lights))
    cnt = sorted(P.count.items(), key=lambda kv: -kv[1])
    log("종류별:", ", ".join("%s %d" % kv for kv in cnt))
    log("수면: 늪 %.2f, 호수 %.2f, 다리 웅덩이 %.2f, 다리 둑 %.2f" % (W.swamp_level, W.lake_level, W.pool_level, W.bridge_bank))


if __name__ == "__main__":
    main()
