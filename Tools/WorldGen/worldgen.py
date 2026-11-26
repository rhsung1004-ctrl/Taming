#!/usr/bin/env python3
# 1장 오픈월드 생성기 (버려진 묘지 들판, 지형 2 km × 2 km, 걸어 다니는 범위 1.33 km)
#   python3 worldgen.py <출력 폴더(Ch1)> <소품 manifest.json 또는 manifest_*.json 이 있는 폴더> [씨앗]
# 결과 (규격: SPEC.md)
#   <출력>/Data~/world.json, height.r16, splat_0/1.png, detail_0/1.png, trees.json, objects.json
#   <출력>/Terrain/ground_*  (groundtex.py 가 만든다. 없으면 여기서 부른다)
#   <출력>/map.png, <출력>/_overview.png, <출력>/_scenes.json (확인용, Unity 로 가져가지 않아도 됨)
import sys, os, json, math, time, glob, collections
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
MAP_MARGIN = 60               # 게임 안 지도(map.png)가 덮는 범위 = 걸어 다니는 범위 + 이 여유 (world.json "map")
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
# w4: 1차 9종(brazier, banner_torn, sarcophagus, soul_crystal, skeleton_remains, iron_fence, campfire, stone_wall_low, standing_stone)은
# 진짜 소품이 생겼다 (BlenderKit scenes 묶음). size·META 는 그 manifest 실측으로 맞췄다 (manifest 가 있으면 어차피 manifest 가 이긴다).
# 2차 7종(gallows, hanging_cage, cart_broken, obelisk_chained, mausoleum_small, shrine_roadside, tent_torn)도 빌드 1회차가 나와
# size 를 실측으로 맞췄다 (독립 검토 전. 2회차 빌드가 나오면 manifest 가 이긴다)
# light 의 far (m): 멀리서 보여야 하는 '등대 빛'. LightCuller 가 range × 12 대신 이 거리에서 끈다 (SPEC.md)
FAR = 140.0                    # 장면·장소 등대 빛의 끄는 거리 (LightCuller 덮어쓰기)
NEW_PROPS = {
    "gallows":          dict(size=[3.56, 1.83, 4.72], footprint=1.9, kind="prop", collider="mesh", sink=0.05, tilt=2, align=False,
                             scale=[0.95, 1.1], light=None, tags=["ruin", "execution"], sub=("dead_tree_c", None)),
    # v3: 대체를 교수 고목(dead_tree_c × 0.7, 약 3.8 m)으로. 처형터의 세로 실루엣
    "hanging_cage":     dict(size=[2.21, 0.93, 3.74], footprint=0.9, kind="prop", collider="capsule", sink=0.05, tilt=4, align=False,
                             scale=[0.9, 1.1], light={"offset": [0.7, 0.0, 1.9], "color": SOUL, "intensity": 1.5, "range": 3},
                             tags=["execution", "light"], sub=("dead_tree_c", 0.7)),
    "brazier":          dict(size=[1.0, 1.0, 1.43], footprint=0.6, kind="prop", collider="capsule", sink=0.04, tilt=2, align=False,
                             scale=[0.9, 1.1], light={"offset": [0.0, 0.0, 1.25], "color": SPIRIT, "intensity": 7, "range": 9, "far": FAR},
                             tags=["light", "path"], sub=("lantern", None)),
    "banner_torn":      dict(size=[1.36, 0.54, 4.24], footprint=0.5, kind="prop", collider="capsule", sink=0.15, tilt=8, align=False,
                             scale=[0.85, 1.15], light=None, tags=["battle"], sub=("bone_spike", None)),
    "sarcophagus":      dict(size=[2.7, 1.24, 1.08], footprint=1.3, kind="prop", collider="box", sink=0.05, tilt=2, align=False,
                             scale=[0.95, 1.1], light=None, tags=["grave"], sub=("coffin", None)),
    "cart_broken":      dict(size=[3.33, 1.92, 1.61], footprint=1.8, kind="prop", collider="mesh", sink=0.08, tilt=6, align=True,
                             scale=[0.9, 1.1], light=None, tags=["camp"], sub=("log_fallen", None)),
    "soul_crystal":     dict(size=[1.43, 1.23, 2.4], footprint=0.9, kind="prop", collider="mesh", sink=0.2, tilt=12, align=False,
                             scale=[0.7, 1.4], light={"offset": [0.0, 0.0, 1.2], "color": SPIRIT, "intensity": 4, "range": 7, "far": FAR},
                             tags=["light", "crystal"], sub=("rock_b", 0.6)),
    "skeleton_remains": dict(size=[2.02, 0.88, 0.44], footprint=0.9, kind="scatter", collider="none", sink=0.03, tilt=4, align=True,
                             scale=[0.9, 1.1], light=None, tags=["bone"], sub=("bones_scatter", None)),
    "iron_fence":       dict(size=[3.03, 0.17, 1.88], footprint=1.5, kind="prop", collider="box", sink=0.05, tilt=3, align=False,
                             scale=[0.95, 1.05], light=None, tags=["grave", "path"], sub=("fence", None)),
    # v3: 대체를 crypt × 0.5 에서 큰 석관 무덤(grave_tomb)으로 (이름 있는 장소 '이름 없는 납골당'의 축소판이 여러 채 생기지 않게)
    "mausoleum_small":  dict(size=[4.5, 5.56, 4.92], footprint=3.0, kind="landmark", collider="mesh", sink=0.06, tilt=0, align=False,
                             scale=[0.95, 1.05], light={"offset": [0.0, -2.4, 1.6], "color": SOUL, "intensity": 3, "range": 5, "far": FAR},
                             tags=["grave", "landmark", "light"], sub=("grave_tomb", 1.15)),
    "shrine_roadside":  dict(size=[1.28, 1.0, 2.29], footprint=0.8, kind="prop", collider="box", sink=0.04, tilt=3, align=False,
                             scale=[0.9, 1.1], light={"offset": [0.0, -0.35, 1.2], "color": SOUL, "intensity": 2.5, "range": 5, "far": FAR},
                             tags=["grave", "path", "light"], sub=("grave_obelisk", None)),
    "obelisk_chained":  dict(size=[1.5, 1.5, 4.65], footprint=1.0, kind="prop", collider="box", sink=0.1, tilt=3, align=False,
                             scale=[0.9, 1.15], light=None, tags=["ritual"], sub=("grave_obelisk", 1.7)),
    "tent_torn":        dict(size=[3.82, 3.04, 2.42], footprint=2.0, kind="prop", collider="mesh", sink=0.05, tilt=4, align=True,
                             scale=[0.9, 1.1], light=None, tags=["camp"], sub=None),
    "campfire":         dict(size=[1.35, 1.28, 0.47], footprint=0.8, kind="prop", collider="none", sink=0.03, tilt=2, align=True,
                             scale=[0.9, 1.1], light={"offset": [0.0, 0.0, 0.5], "color": EMBER, "intensity": 3.5, "range": 7, "far": FAR},
                             tags=["camp", "light"], sub=("rubble", 0.75)),
    # v3 새 소품 둘. 낮은 돌담(밭 경계, 긴 축 = 로컬 X, 양 끝이 무너져 이어 놓아도 자연스럽다)과 선돌(키 큰 거친 돌)
    # 대체(소품이 없을 때만): 돌담 → 무너진 담 조각(wall_ruin_b × 0.5), 선돌 → 바위 기둥(cliff_b × 0.34)
    # 돌담은 비탈을 따라 기울이지 않고 세운다 (턱을 가로지르면 fill_line 이 칸을 끊는다).
    # 실측: 돌담 높이 1.29 m 는 땅속 밑동 0.3 m 를 포함한다 (원점 위 0.99 m). 선돌 3.17 m
    "stone_wall_low":   dict(size=[4.14, 0.89, 1.29], footprint=2.0, kind="prop", collider="box", sink=0.1, tilt=2, align=False,
                             scale=[0.9, 1.15], light=None, tags=["wall", "field"], sub=("wall_ruin_b", 0.5)),
    "standing_stone":   dict(size=[1.28, 0.93, 3.17], footprint=0.8, kind="prop", collider="box", sink=0.3, tilt=6, align=False,
                             scale=[0.8, 1.3], light=None, tags=["ritual", "stone"], sub=("cliff_b", 0.34)),
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
    dj = face_shift(W, dout, jit, calm, gap)          # v3 검토 반영: 능선 밑동은 안쪽으로 튀어나오고 골 위쪽은 벽 속으로 파인다
    wf = gap * ss(dj, -5, 25) + (1 - gap) * ss(zb, -5, 25) * north * 0.45
    crest = gap * ss(dj, 18, 50) + (1 - gap) * ss(zb, 18, 50) * north * 0.45   # 벼랑 위는 평평한 대지 대신 들쭉날쭉한 봉우리
    rug = 45 * ridged(X, Z, 1 / 120, 4, 945) * (1 - 0.65 * calm)
    W.wall = ((amp * wf + rug * crest) * fade * (1 - ss(h, 200, 300))).astype(np.float32)
    W.mount = np.maximum(m * (1 - corridor), ss(dj, 0, 25) * np.maximum(gap, ss(zb, 0, 25)))
    mountain_face(W, h, dj, calm, gap)
    del dj
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


FACE_SPUR = 24.0             # 산 앞면 능선·골 높낮이 (m). 둘레를 따라 약 95 m 마다 번갈아 (골은 비탈 방향으로 길쭉)
FACE_STEP = 10.0             # 층진 바위 턱 한 층 높이 (m)
FACE_STRATA = 0.7            # 층 세기 (0 = 매끈한 비탈, 1 = 평평한 턱 + 가파른 턱 벽)
FACE_TALUS = 3.8             # 골 어귀 너덜 부채꼴 높이 (m, 발치 안쪽 약 22 m 에 걸쳐 기울기 0.3 안팎)
FACE_FOOT = 12.0             # 이보다 발치 쪽(바깥 거리 dd < 12 m: 탈출을 막는 가파른 띠)은 형태를 더하지 않는다


FACE_BUTTRESS = 26.0         # 능선 밑동이 벽 앞으로 튀어나오는 거리 (m, 안쪽으로만: 걸을 수 있는 땅이 bounds 밖으로 늘지 않는다)
FACE_NOTCH = 17.0            # 골 위쪽이 벽 속으로 파이는 거리 (m, 발치 12 m 바깥만: 가파른 발치 띠는 그대로)


def face_shift(W, dout, jit, calm, gap):
    """산 벽의 평면 모양을 둘레 방향으로 흔든다. 반환 = 벽 모양에 쓰는 바깥 거리.
    능선(spur 높음): 밑동부터 FACE_BUTTRESS 만큼 안쪽으로 튀어나오고 위로 갈수록 벽과 합쳐진다 (버팀벽 같은 산줄기).
    골(spur 낮음): 발치 12 m 바깥의 위쪽이 FACE_NOTCH 만큼 벽 속으로 파인다 (벼랑 꼭대기 선의 V 자 홈). 발치 띠는 그대로라 탈출 조건이 같다"""
    X, Z = W.X, W.Z
    dd = dout + jit
    # 둘레 좌표: 벽에 수직인 선을 따라 발치(dout 0)까지 내려간 점의 각도 (같은 수직선 위 점은 같은 값 → 골·능선이 벽에 수직으로 길쭉).
    # 각도를 원 위에 놓아 이음매가 없다. 바깥 방향 거리는 0.3 배로 조금 섞어 능선이 위로 가며 조금 휘게
    gz_, gx_ = np.gradient(box_blur(dout, 22))         # 모서리 바깥의 꺾인 선(대각선)에서 방향이 튀지 않게 흐린 뒤
    gn = np.sqrt(gx_ * gx_ + gz_ * gz_) + 1e-6
    dc = np.clip(dout, -80.0, 420.0)
    th = np.arctan2(Z - dc * gz_ / gn - 1024.5, X - dc * gx_ / gn - 1024.5)
    del gz_, gx_, gn
    rad = 900.0 + 0.3 * dc
    U, V = rad * np.cos(th), rad * np.sin(th)
    del th, rad, dc
    spur = ridged(U, V, 1 / 95.0, 3, 950) + 0.3 * fbm(U, V, 1 / 38.0, 2, 952)      # 1 = 날카로운 능선, 0 = 둥근 골
    del U, V
    W.spur = spur.astype(np.float32)
    quiet = (1 - calm) * gap                                                       # 봉인문 둘레·고갯길은 그대로
    gx, gz = np.abs(X - GATE[0]), Z - GATE[1]
    quiet = quiet * ss(np.hypot(gx, np.minimum(gz, 0)), 120, 200)                  # 문 앞 길목은 넓게 비운다
    del gx, gz
    W.face_quiet = quiet.astype(np.float32)
    big = 0.45 + 0.9 * ss(fbm(X, Z, 1 / 280.0, 2, 955), -0.3, 0.4)                # 능선마다 크기가 다르게 (작은 턱 ~ 큰 산줄기)
    P = FACE_BUTTRESS * ss(spur, 0.3, 1.05) * big * quiet                          # 평면에서 뾰족한 삼각형 (평평한 기둥 모양이 되지 않게)
    G = FACE_NOTCH * ss(0.42 - spur, 0.0, 0.35) * quiet
    # 튀어나온 양은 위로 갈수록 천천히 줄어 능선 마루가 비스듬히 벽에 붙는다 (곧게 선 기둥처럼 보이지 않게)
    return (dd + P * (1 - ss(dd, 0, 95)) - G * ss(dd, 12, 60)).astype(np.float32)


def mountain_face(W, h, dd, calm, gap):
    """v3 검토 반영: 바깥 산 띠가 150 m 높이의 매끈한 벽으로 보였다. 걸어 다니는 범위에서 보이는 앞면(발치 바깥 12~250 m)에
    큰 형태를 준다: 둘레를 따라 번갈아 드는 능선(튀어나온 산줄기)과 골(비탈 방향으로 길쭉), 층진 바위 턱(조금 기운 지층),
    골 어귀의 너덜 부채꼴. 발치의 가파른 띠(dd < FACE_FOOT)는 그대로 두어 걷기·탈출 검사 조건이 바뀌지 않는다.
    dd = 걸을 수 있는 범위(bounds) 밖으로의 거리 + 발치 흔들림 (벽이 시작하는 선 = dd −5 m)"""
    log("높이: 산 앞면 (능선·골·층진 턱·너덜)")
    X, Z = W.X, W.Z
    spur = W.spur
    quiet = W.face_quiet
    band = (ss(dd, FACE_FOOT, FACE_FOOT + 28) * (1 - ss(dd, 160, 260)) * quiet).astype(np.float32)
    face = (FACE_SPUR * (spur - 0.45) * band).astype(np.float32)
    # 층진 바위 턱: 벽까지 더한 높이를 계단 모양으로 (한 층의 반은 거의 평평한 턱, 반은 가파른 턱 벽). 지층은 느린 노이즈로 조금 기운다
    tot = h + W.wall + face
    q = tot + 6.0 * fbm(X, Z, 1 / 260.0, 2, 960)
    u = q / FACE_STEP
    k = np.floor(u)
    qt = FACE_STEP * (k + ss(u - k, 0.5, 1.0))
    band2 = ss(dd, FACE_FOOT + 4, FACE_FOOT + 22) * (1 - ss(tot, 200, 260)) * quiet
    face += ((qt - q) * FACE_STRATA * band2).astype(np.float32)
    del tot, q, u, k, qt, band2
    W.wall = (W.wall + face).astype(np.float32)
    # 골 어귀 너덜: 골(spur 낮음)이 내려오는 발치 안쪽에 굴러떨어진 돌이 쌓인 부채꼴. 길 둘레는 finish_height 에서 뺀다
    mouth = ss(0.42 - spur, 0.0, 0.22) * quiet
    W.talus = (FACE_TALUS * mouth * ss(dd, -26, -3)).astype(np.float32)
    W.dd = dd.astype(np.float32)                 # 산기슭 바위·장면 배치에 쓴다 (lay_mountain_foot, 산기슭 장면). 능선 밑동이 튀어나온 만큼 옮긴 거리
    del face, mouth, band, W.face_quiet


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
    # 가장자리 벽 (자리 고르기 뒤에 더해야 봉인문 둘레 벽이 깎이지 않는다). 산 앞면 형태(mountain_face)가 들어 있다
    h += W.wall
    del W.wall
    # 골 어귀 너덜 부채꼴 (길 둘레는 뺀다)
    h += W.talus * ss(W.road_dist, W.road_hw + 6.0, W.road_hw + 26.0)
    del W.talus
    X, Z = W.X, W.Z
    micro = 0.22 * fbm(X, Z, 1 / 7.0, 3, 800) + 0.5 * fbm(X, Z, 1 / 28.0, 2, 810)
    keep = ss(W.road_dist, 2, 8)
    rs, cs, d = disk(h.shape, W.bridge_p[0], W.bridge_p[1], 24)
    keep[rs, cs] *= ss(d, 10, 22)                     # 다리 둑 높이는 그대로
    for (x, z, rin, rout) in pads:
        rs, cs, d = disk(h.shape, x, z, rout)
        keep[rs, cs] *= ss(d, rin * 0.8, rout)
    h += micro * keep
    relief(W, pads)              # v3 채움: 작은 둔덕·마루 바위 혹·밭 턱(등고선 줄)·마른 도랑 (길·물·장소는 건드리지 않는다)
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


# ─────────────────────────── 지형 잔굴곡 (v3 채움) ───────────────────────────
# 들판이 '모래 언덕'처럼 매끈하게 읽히지 않게, 걸을 수 있음은 그대로 두고 땅 자체에 볼 것을 만든다.
#  - 작은 둔덕: 높이 0.3~0.8 m, 폭 6~15 m 의 둔덕 무리 (넓은 무늬로 둔덕진 풀밭과 매끈한 풀밭이 번갈아)
#  - 마루 바위 혹: 언덕 마루·능선의 날카로운 작은 혹 (바위 층을 칠하고 노두 소품을 놓는 자리, W.crest)
#  - 밭 턱(등고선 줄): 비탈을 따라 등고선 방향으로 30~180 m 이어지는 턱 (높이 RELIEF_STEP, 기울기 한계 안).
#    줄 위에 낮은 돌담·쇠 울타리·산울타리를 놓거나 (lay_fill) 그냥 턱(scarp)으로 둔다 → W.relief_lines
#  - 마른 도랑: 완만한 비탈에서 물이 흐를 길을 따라 파인 물 없는 개울 바닥 (깊이 RELIEF_DITCH) → W.ditches
# 걷기: 고친 뒤 기울기가 RELIEF_MAX_SLOPE 를 넘는 곳은 고친 양을 줄인다 (원래 가파른 곳은 그대로). 줄은 끝이 열려 돌아갈 수 있다
RELIEF_SEED = 5150
RELIEF_SWELL = 1.3           # 중간 크기 오르내림 (m, 폭 30~60 m): 매끈한 큰 둔덕을 깬다
RELIEF_HUMMOCK = 0.9         # 작은 둔덕 최대 높이 (m, 폭 6~15 m)
RELIEF_CREST = 0.6           # 마루 바위 혹 최대 높이 (m)
RELIEF_LINES = 300           # 밭 경계 줄 수 (등고선 줄: 비탈은 밭 턱, 평지는 밭 둑). w4: 170 → 300 (진짜 돌담이 생겨 줄마다 읽힌다. 눈높이 40 m 마다 경계 하나)
RELIEF_SEED_GAP = 16.0       # 줄 씨앗 격자 (m)
RELIEF_LINE_GAP = 22.0       # 새 줄 씨앗은 기존 줄에서 이만큼 떨어져야 (줄 사이 간격, m). w4: 24 → 22
RELIEF_CROSS = 100           # 가로 줄 (등고선 줄 사이를 비탈 방향으로 잇는다) 수. w4: 70 → 100
RELIEF_STEP = (0.6, 1.4)     # 밭 턱 높이 (m). 그냥 턱(scarp)은 × 1.1 (최대 1.5)
RELIEF_BANK = (0.3, 0.55)    # 평지 밭 둑 높이 (m, 폭 약 3 m)
RELIEF_RISER = 3.2           # 턱 비탈 폭 (m)
RELIEF_DITCHES = 34          # 마른 도랑 수
RELIEF_DITCH = (0.5, 0.95)   # 마른 도랑 깊이 (m)
RELIEF_DITCH_GAP = 80.0      # 마른 도랑 시작점 사이 (m)
RELIEF_MAX_SLOPE = 0.8       # 잔굴곡을 더한 뒤 넘지 않게 할 기울기 (걷기 검사 한계 1.0 에 여유)
# 밭 경계 줄의 성격 비율. 줄 하나가 이 성격을 바탕으로 구간마다 모양(산울타리·돌담·쇠 울타리·무너진 돌줄·빈 턱)을 섞는다 (FILL_STYLE)
LINE_KINDS = (("hedge", 0.34), ("wall", 0.16), ("fence", 0.14), ("stones", 0.18), ("scarp", 0.18))


def relief_keep(W, pads):
    """잔굴곡을 넣어도 되는 곳 (0~1): 길·다리·장소·물·개울·산·자리 고르기 둘레는 0"""
    X, Z, h = W.X, W.Z, W.h
    k = ss(W.road_dist, W.road_hw + 1.5, W.road_hw + 7.0).astype(np.float32)
    k *= (1 - ss(W.mount, 0.1, 0.25)).astype(np.float32)          # 산기슭 완만한 띠(걸을 수 있는 땅의 약 4%)까지 (벼랑 띠는 0)
    ex = ((X - GRAVE_C[0]) / (GRAVE_R[0] + 22)) ** 2 + ((Z - GRAVE_C[1]) / (GRAVE_R[1] + 22)) ** 2
    k *= ss(ex, 1.0, 1.4)
    for (c, r_in, r_out) in ((ALTAR, 45, 65), (CRYPT, 40, 60), (CATH, 95, 125), (VILLAGE, 80, 100), (TOWER, 45, 70),
                             (TREE, 55, 75), (GATE, 90, 120), (W.bridge_p, 34, 50), (SWAMP, SWAMP_R + 30, SWAMP_R + 60),
                             (LAKE, LAKE_R + 30, LAKE_R + 55), (DRAGON, DRAGON_R - 20, DRAGON_R + 15)):
        rs, cs, d = disk(h.shape, c[0], c[1], r_out + 1)
        k[rs, cs] *= ss(d, r_in, r_out)
    (z0, z1), (x0, x1) = W.creek_win
    k[z0:z1, x0:x1] *= ss(W.creek_dist - W.creek_wt, 6.0, 16.0)
    for (x, z, rin, rout) in pads:
        rs, cs, d = disk(h.shape, x, z, rout + 8)
        k[rs, cs] *= ss(d, rout, rout + 8)
    return k


def line_field(curve, pad):
    """꺾은선 둘레 상자의 (행 범위, 열 범위, 거리, 따라간 거리, 왼쪽(+)/오른쪽(-) 부호)"""
    (z0, z1), (x0, x1), dist, along = polyline_field(curve, pad, RES)
    zz, xx = np.mgrid[z0:z1, x0:x1].astype(np.float32)
    seg = np.linalg.norm(np.diff(curve, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    k = np.clip(np.searchsorted(cum, along) - 1, 0, len(curve) - 2)
    ax, az = curve[k, 0], curve[k, 1]
    dx, dz = curve[k + 1, 0] - ax, curve[k + 1, 1] - az
    side = np.sign(dx * (zz - az) - dz * (xx - ax)).astype(np.float32)
    side[side == 0] = 1.0
    return (z0, z1), (x0, x1), dist, along, side


def resample(curve, step):
    seg = np.linalg.norm(np.diff(curve, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, s[-1] + 1e-6, step)
    return np.stack([np.interp(t, s, curve[:, 0]), np.interp(t, s, curve[:, 1])], 1), float(s[-1])


def relief(W, pads):
    """작은 둔덕·마루 바위 혹·밭 턱(등고선 줄)·마른 도랑. W.relief_lines, W.ditches, W.crest 를 남긴다"""
    log("높이: 잔굴곡 (둔덕·마루·밭 턱·마른 도랑)")
    t0 = time.time()
    h = W.h
    X, Z = W.X, W.Z
    rng = np.random.default_rng(RELIEF_SEED)
    keep = relief_keep(W, pads)
    h0 = h.copy()
    delta = np.zeros(h.shape, np.float32)
    # 중간 크기 오르내림 (폭 30~60 m): 언덕 비탈에 굽이와 작은 등성이·골이 생긴다
    delta += RELIEF_SWELL * fbm(X, Z, 1 / 48.0, 2, RELIEF_SEED + 5) * (0.5 + 0.5 * ss(fbm(X, Z, 1 / 300.0, 2, RELIEF_SEED + 6), -0.3, 0.3))
    # 작은 둔덕: 양(+)의 둥근 혹만 (골은 만들지 않는다). 넓은 무늬로 둔덕진 곳과 매끈한 곳이 번갈아
    n = fbm(X, Z, 1 / 12.0, 3, RELIEF_SEED + 1)
    patch = 0.2 + 0.8 * ss(fbm(X, Z, 1 / 230.0, 2, RELIEF_SEED + 2), -0.2, 0.3)
    delta += RELIEF_HUMMOCK * 1.7 * np.maximum(n - 0.06, 0) ** 1.15 * patch
    del n, patch
    # 마루 바위 혹: 언덕 마루·능선 (둘레보다 높은 곳)의 날카로운 작은 혹
    hb = box_blur(h, 14)
    calm = 1 - ss(box_blur(W.mount, 30), 0.02, 0.08)
    W.crest = (ss(h - hb, 0.5, 1.8) * calm).astype(np.float32)
    rid = ridged(X, Z, 1 / 7.0, 2, RELIEF_SEED + 3)
    delta += RELIEF_CREST * np.clip((rid - 0.3) / 0.7, 0, 1) * W.crest
    del rid, hb
    # 밭 경계 줄: 비탈에서는 등고선을 따라 (밭 턱), 평지에서는 넓은 무늬의 방향을 따라 (밭 둑).
    # 이어서 등고선 줄 사이를 비탈 방향으로 잇는 가로 줄 (밭을 나눈다, 턱 없음)
    hs = box_blur(h, 8)
    gz, gx = np.gradient(hs)
    sl = np.hypot(gx, gz)
    th = (np.pi * fbm(X, Z, 1 / 320.0, 2, RELIEF_SEED + 4)).astype(np.float32)        # 평지 밭 방향 (라디안)
    (bx0, bz0), (bx1, bz1) = BOUNDS
    forests = [(FOREST_SW[0], FOREST_SW[1] - 5), (FOREST_NE[0], FOREST_NE[1] - 5)]
    pois = [((p if p else W.bridge_p), r) for (_, _, p, r) in POIS]

    def ok_at(x, z, kmin=0.85, smax=0.3):
        if not (bx0 + 25 < x < bx1 - 25 and bz0 + 25 < z < bz1 - 25):
            return False
        if sample(keep, x, z) < kmin or sample(sl, x, z) > smax:
            return False
        if any((x - c[0]) ** 2 + (z - c[1]) ** 2 < R * R for c, R in forests):
            return False
        return True

    used = []                     # 이미 그은 줄의 점 (줄 사이 간격)
    U = {"a": np.zeros((0, 2))}

    def near_used(x, z, r):
        a = U["a"]
        return len(a) and np.min((a[:, 0] - x) ** 2 + (a[:, 1] - z) ** 2) < r * r

    def dir_at(x, z, cross=False):
        """등고선 방향 (cross 면 비탈 방향). 평지(기울기 < 0.03)는 밭 방향 무늬와 섞는다"""
        g = np.array([sample(gx, x, z), sample(gz, x, z)])
        gl = float(np.hypot(*g)) + 1e-9
        w = ssf(gl, 0.012, 0.035)
        a = sample(th, x, z)
        nd = np.array([math.cos(a), math.sin(a)])
        cd = np.array([-g[1], g[0]]) / gl
        if cross:
            nd = np.array([-nd[1], nd[0]])
            cd = g / gl
        if np.dot(nd, cd) < 0:
            nd = -nd
        t = w * cd + (1 - w) * nd
        return t / (np.linalg.norm(t) + 1e-9)

    def trace(x, z, sgn, Lmax, step=3.0, own=(), cross=False, gap=15.0):
        own = list(own)
        pts, dprev = [], None
        for _ in range(int(Lmax / step)):
            t = dir_at(x, z, cross) * sgn
            if dprev is not None:
                if np.dot(t, dprev) < 0:
                    t = -t
                t = 0.55 * t + 0.45 * dprev
                t /= np.linalg.norm(t) + 1e-9
            nx, nz = x + t[0] * step, z + t[1] * step
            if not ok_at(nx, nz) or near_used(nx, nz, gap):
                if cross and ok_at(nx, nz):
                    pts.append((nx, nz))                # 가로 줄은 이웃 줄에 닿아 끝난다
                break
            if len(pts) > 8 and min((nx - a) ** 2 + (nz - b) ** 2 for a, b in pts[:-6] + own) < 15.0 ** 2:
                break                                  # 언덕을 한 바퀴 도는 고리가 되지 않게
            x, z, dprev = nx, nz, t
            pts.append((x, z))
        return pts

    lines = []
    g = np.arange(bx0 + 40, bx1 - 40, RELIEF_SEED_GAP)
    seeds = [(float(a + rng.uniform(-6, 6)), float(b + rng.uniform(-6, 6))) for a in g for b in g]
    rng.shuffle(seeds)
    kinds, kp = [k_ for k_, _ in LINE_KINDS], np.array([p_ for _, p_ in LINE_KINDS])

    def add_line(c, kind, A, B):
        dv = np.gradient(c, axis=0)
        up = np.sign(np.sum([(-dv[i, 1] * sample(gx, *c[i]) + dv[i, 0] * sample(gz, *c[i])) for i in range(0, len(c), 3)])) or 1.0
        gm = float(np.median([sample(sl, px, pz) for px, pz in c[::4]]))
        L = float(np.sum(np.linalg.norm(np.diff(c, axis=0), axis=1)))
        lines.append({"kind": kind, "pts": c, "L": L, "A": float(A), "B": float(B), "up": float(up), "slope": gm})
        used.extend(map(tuple, c[::2]))
        U["a"] = np.array(used)

    # 마른 도랑 (w4: 밭 줄보다 먼저 긋는다. 줄이 촘촘해지자 도랑이 줄 앞에서 멈춰 40 m 를 못 넘어 34 → 11 개로 줄었다): 완만한 비탈에서 내리막을 따라 (매끈한 높이 기준), 줄·장소·길·물 앞에서 멈춘다
    hs6 = box_blur(h, 6)
    gz6, gx6 = np.gradient(hs6)
    ditches = []
    dseeds = [(float(rng.uniform(bx0 + 60, bx1 - 60)), float(rng.uniform(bz0 + 60, bz1 - 60))) for _ in range(2500)]
    for (x, z) in dseeds:
        if len(ditches) >= RELIEF_DITCHES:
            break
        s0 = sample(sl, x, z)
        if not ok_at(x, z, 0.97, 0.22) or s0 < 0.06:
            continue
        if any((x - d_["pts"][0][0]) ** 2 + (z - d_["pts"][0][1]) ** 2 < RELIEF_DITCH_GAP ** 2 for d_ in ditches):
            continue
        pts, dprev, flat = [(x, z)], None, 0
        for i in range(130):
            g = np.array([sample(gx6, x, z), sample(gz6, x, z)])
            gl = float(np.hypot(*g))
            if gl < 0.015:
                flat += 1
                if flat > 6 or dprev is None:
                    break
                t = dprev
            else:
                flat = 0
                t = -g / gl
                if dprev is not None:
                    t = 0.6 * t + 0.4 * dprev
                    t /= np.linalg.norm(t) + 1e-9
            wob = 0.35 * perlin(np.float32(i * 0.18), np.float32(len(ditches) * 3.1), 8401)
            t = np.array([t[0] * math.cos(wob) - t[1] * math.sin(wob), t[0] * math.sin(wob) + t[1] * math.cos(wob)])
            nx, nz = x + t[0] * 2.0, z + t[1] * 2.0
            if not ok_at(nx, nz, 0.9, 0.32) or near_used(nx, nz, 10.0):
                break
            x, z, dprev = nx, nz, t
            pts.append((x, z))
        if len(pts) < 21:                         # 40 m 미만은 버린다
            continue
        c, Lc = resample(np.array(pts), 2.0)
        D = rng.uniform(*RELIEF_DITCH)
        ditches.append({"pts": c, "L": Lc, "D": float(D)})
        used.extend(map(tuple, c[::3]))
        U["a"] = np.array(used)
    for (x, z) in seeds:
        if len(lines) >= RELIEF_LINES:
            break
        if not ok_at(x, z, 0.95, 0.26) or near_used(x, z, RELIEF_LINE_GAP):
            continue
        if any((x - c[0]) ** 2 + (z - c[1]) ** 2 < (r + 20) ** 2 for c, r in pois):
            continue
        L = rng.uniform(45, 160)
        a = trace(x, z, 1, L / 2, own=[(x, z)])
        b = trace(x, z, -1, L / 2, own=[(x, z)] + a)
        pts = b[::-1] + [(x, z)] + a
        if len(pts) < 9:                          # 25 m 미만은 버린다
            continue
        c, Lc = resample(np.array(pts), 2.0)
        kind = str(rng.choice(kinds, p=kp / kp.sum()))
        gm = float(np.median([sample(sl, px, pz) for px, pz in c[::4]]))
        A = rng.uniform(*RELIEF_STEP) * (1.1 if kind == "scarp" else 1.0) * ssf(gm, 0.02, 0.07)     # 평지에는 턱이 없다
        A = min(A, max(0.0, (RELIEF_MAX_SLOPE - 0.05 - gm)) * RELIEF_RISER / 1.5, 1.5)
        B = rng.uniform(*RELIEF_BANK) * (1 - ssf(gm, 0.03, 0.08)) if kind != "scarp" else 0.0    # 평지 밭 둑
        add_line(c, kind, A, B)
    nmain = len(lines)
    # 가로 줄: 등고선 줄 위 70~120 m 마다 비탈 방향으로 (위나 아래로) 다음 줄까지
    ncross = 0
    for ln in lines[:nmain]:
        if ncross >= RELIEF_CROSS:
            break
        c = ln["pts"]
        for tt in np.arange(rng.uniform(15, 50), ln["L"] - 10, rng.uniform(70, 120)):
            k = int(tt / 2.0)
            if k >= len(c):
                break
            x, z = c[k]
            sgn = 1 if rng.random() < 0.5 else -1
            dv = dir_at(x, z, True) * sgn
            x1, z1 = x + dv[0] * 4.0, z + dv[1] * 4.0
            if not ok_at(x1, z1):
                continue
            pts = [(x, z), (x1, z1)] + trace(x1, z1, sgn, rng.uniform(25, 75), cross=True, gap=6.0)
            if len(pts) < 8:
                continue
            cc, Lc = resample(np.array(pts), 2.0)
            add_line(cc, "cross" if rng.random() < 0.7 else ln["kind"], 0.0, rng.uniform(*RELIEF_BANK) * 0.8)
            ncross += 1
    # 밭 턱 (줄 오르막 쪽 +A/2, 내리막 쪽 −A/2, 줄에서 멀어지면 0 으로. 끝 12 m 에서 0 으로)과 밭 둑 (줄 위 낮은 둑 B)
    Rw = RELIEF_RISER
    for ln in lines:
        c = ln["pts"]
        (z0, z1), (x0, x1), dist, along, side = line_field(c, Rw / 2 + 18)
        s = dist * side * ln["up"]
        L = ln["L"]
        env = ss(along, 0, 12) * ss(L - along, 0, 12) * (0.7 + 0.3 * perlin(along * 0.05, np.full(along.shape, 7.7, np.float32), 8301 + len(c)))
        off = ln["A"] * env * (ss(s, -Rw / 2, Rw / 2) - 0.5) * (1 - ss(np.abs(s), Rw / 2 + 2, Rw / 2 + 17))
        off += ln["B"] * env * np.exp(-(dist / 1.7) ** 2)
        delta[z0:z1, x0:x1] += off.astype(np.float32)
    for dt in ditches:
        c, L, D = dt["pts"], dt["L"], dt["D"]
        wb = 0.9
        wbank = 1.5 * D / 0.42
        (z0, z1), (x0, x1), dist, along = polyline_field(c, wb + wbank + 2, RES)
        dd = D * ss(along, 0, 14) * ss(L - along, 0, 22) * (0.75 + 0.25 * perlin(along * 0.06, np.full(along.shape, 2.2, np.float32), 8501))
        prof = dd * (1 - ss(dist, wb, wb + wbank))
        delta[z0:z1, x0:x1] -= prof.astype(np.float32)
    # 고칠 수 있는 곳만, 그리고 걷기 기울기를 넘지 않게 (넘는 곳 둘레는 고친 양을 줄인다)
    delta *= keep
    s_old = np.hypot(*np.gradient(h0))
    for it in range(10):
        s_new = np.hypot(*np.gradient(h0 + delta))
        bad = ((s_new > RELIEF_MAX_SLOPE) & (s_new > s_old + 0.03)).astype(np.float32)
        nb = int(bad.sum())
        if nb == 0:
            break
        delta *= 1 - np.clip(box_blur(bad, 3, 2) * 6.0, 0, 0.9 if it < 6 else 1.0)
    h += delta
    W.relief_lines = lines
    W.ditches = ditches
    W.relief_delta = delta
    log("잔굴곡: 등고선 줄 %d 개 (%s, 합 %.1f km, 턱 높이 중앙값 %.2f m), 마른 도랑 %d 개 (합 %.2f km), 고친 높이 최대 +%.2f/−%.2f m, "
        "기울기 넘은 칸 %d, %.1f 초" % (
            len(lines), ", ".join("%s %d" % (k_, sum(1 for l_ in lines if l_["kind"] == k_)) for k_ in kinds + ["cross"]),
            sum(l_["L"] for l_ in lines) / 1000, float(np.median([l_["A"] for l_ in lines])) if lines else 0, len(ditches),
            sum(d_["L"] for d_ in ditches) / 1000, float(delta.max()), float(-delta.min()), nb, time.time() - t0))


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


BURY_MAX = 0.25        # 바닥 상자 접지 큰 소품: 오르막 쪽 묻힘이 높이의 이 비율을 넘지 않게 (의도된 묻힘 소품은 빼고)
# 묻혀도 자연스러운 것 (바위·낮은 관·잔해): 묻힘 검사와 밑 평탄화를 하지 않는다
BURY_FREE = {"rock_b", "rock_flat", "coffin", "rubble", "roots", "stair_ruin"}   # v3 검토 반영: 울타리·통나무는 뺐다 (묻혀 보였다)


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
        self.boxed = []         # (objects 번호, 의도된 묻힘) 바닥 상자 접지로 놓은 소품 (_boxground.json)
        self.anchors = []       # (x, z, r) 지형을 고치면 안 되는 큰 구조물 발자국 (대성당·제단·다리·문 …)
        self.pads = 0           # 큰 소품 밑 작은 평탄화 횟수
        self.pad_reject = 0     # 평탄화로도 묻힘·기울기를 맞추지 못해 놓지 않은 큰 소품 수
        self.pad_reject_by = collections.Counter()
        self.tf_undo = 0        # 걸을 수 있는 기울기를 넘겨 되돌린 지형 고치기 수

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
        if kw.get("align") is None and spec.get("align"):
            kw["align"] = True                     # 새 소품이 땅 기울기를 따르면 (낮은 돌담 등) 대체 소품도 따른다
        if not self.put(b, x, z, s=s2, **kw):
            return False
        self.subst[a] = self.subst.get(a, 0) + 1
        lt = spec.get("light")
        if lt and lt.get("far") and self.meta[b].get("light") and len(self.objects) > n0:
            self.objects[-1]["far"] = float(lt["far"])      # 대체 소품(등불 등)이 발광 부품과 광원을 가지면 그 광원이 등대 빛
        if lt and not self.meta[b].get("light"):
            y0 = self.objects[-1]["p"][1] if len(self.objects) > n0 else self.height(x, z)
            y = y0 + lt["offset"][2] * (s if s is not None else 1.0)
            l = {"p": [round(x, 2), round(float(y), 2), round(z, 2)], "c": list(lt["color"]),
                 "i": float(lt["intensity"]), "r": float(lt["range"]), "flicker": True}
            if lt.get("far"):
                l["far"] = float(lt["far"])
            self.W.lights.append(l)
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
        best, top = 1e9, -1e9
        for u in (-1, -2 / 3, -1 / 3, 0, 1 / 3, 2 / 3, 1):
            for v in (-1, -0.5, 0, 0.5, 1):
                wx = R[0, 0] * u * hx + R[0, 2] * v * hz
                wy = R[1, 0] * u * hx + R[1, 2] * v * hz
                wz = R[2, 0] * u * hx + R[2, 2] * v * hz
                g = self.height(x + wx, z + wz) - wy
                best = min(best, g)
                top = max(top, g)
        self._spread = top - best          # 바닥 상자 아래 땅의 높낮이 차 (오르막 쪽이 이만큼 + margin 묻힌다)
        return best - margin

    # ───── 지형 고치기 (장면 자리 고르기, 무덤 둔덕, 큰 소품 밑 평탄화) ─────
    def _keep(self, z0, z1, x0, x1):
        """고치면 안 되는 곳을 0 으로: 길(반폭 + 1 m 안), 개울, 물, 다리, 산 벽, 봉인문, 큰 구조물 발자국"""
        W = self.W
        k = ss(W.road_dist[z0:z1, x0:x1], W.road_hw[z0:z1, x0:x1] + 1.0, W.road_hw[z0:z1, x0:x1] + 4.5).astype(np.float32)
        (cz0, cz1), (cx0, cx1) = W.creek_win
        a0, a1, b0, b1 = max(z0, cz0), min(z1, cz1), max(x0, cx0), min(x1, cx1)
        if a0 < a1 and b0 < b1:
            cd = W.creek_dist[a0 - cz0:a1 - cz0, b0 - cx0:b1 - cx0] - W.creek_wt[a0 - cz0:a1 - cz0, b0 - cx0:b1 - cx0]
            k[a0 - z0:a1 - z0, b0 - x0:b1 - x0] *= ss(cd, 2.0, 9.0)
        hh = W.h[z0:z1, x0:x1]
        zz, xx = np.mgrid[z0:z1, x0:x1].astype(np.float32)
        for (cx, cz), R, lev in ((SWAMP, SWAMP_R + 45, W.swamp_level), (LAKE, LAKE_R + 35, W.lake_level)):
            near = np.hypot(xx - cx, zz - cz) < R
            if near.any():
                k *= np.where(near, ss(hh - lev, 0.5, 1.5), 1.0)
        if hasattr(W, "pool_mask"):
            k *= ~W.pool_mask[z0:z1, x0:x1]
        k *= 1 - ss(W.mount[z0:z1, x0:x1], 0.15, 0.35)
        for (ax, az, ar) in [(W.bridge_p[0], W.bridge_p[1], 26.0), (GATE[0], GATE[1] - 10, 70.0)] + self.anchors:
            k *= ss(np.hypot(xx - ax, zz - az) - ar, 0.0, 6.0)
        return k

    def terraform(self, x, z, r_in, r_out, mode="flat", amount=1.0, target=None, max_slope=0.6):
        """지형을 조금 고친다. mode "flat": r_in 안을 target(없으면 평균) 높이로 amount 만큼 고르고 r_out 까지 부드럽게 섞는다.
        "mound": 가운데를 amount m 올리는 둥근 둔덕 (r_out 에서 0). 길·물·개울·산 벽·큰 구조물은 건드리지 않는다.
        고친 뒤 창 안의 기울기가 max_slope 를 (원래보다) 넘으면 되돌린다. 이미 놓인 소품·광원·효과는 땅이 바뀐 만큼 옮긴다"""
        W = self.W
        x0, x1 = max(1, int(x - r_out - 2)), min(RES - 1, int(x + r_out + 3))
        z0, z1 = max(1, int(z - r_out - 2)), min(RES - 1, int(z + r_out + 3))
        sub = W.h[z0:z1, x0:x1]
        old = sub.copy()
        zz, xx = np.mgrid[z0:z1, x0:x1].astype(np.float32)
        d = np.hypot(xx - x, zz - z)
        keep = self._keep(z0, z1, x0, x1)
        if mode == "flat":
            core = d <= r_in
            if target is None:
                target = float(np.median(sub[core])) if core.any() else self.height(x, z)
            w = ss(-d, -r_out, -r_in) * amount * keep
            new = sub * (1 - w) + target * w
        else:
            t = np.clip(d / r_out, 0, 1)
            new = sub + amount * (0.5 + 0.5 * np.cos(np.pi * t)) ** 1.6 * keep
        sl_old = np.hypot(*np.gradient(old)).max()
        sl_new = np.hypot(*np.gradient(new.astype(np.float32))).max()
        if sl_new > max(max_slope, sl_old + 0.02):
            self.tf_undo += 1
            return False
        W.h[z0:z1, x0:x1] = new
        delta = (new - old).astype(np.float32)
        # 기울기 다시 (창 + 1 칸)
        a0, a1, b0, b1 = max(0, z0 - 2), min(RES, z1 + 2), max(0, x0 - 2), min(RES, x1 + 2)
        gz_, gx_ = np.gradient(W.h[a0:a1, b0:b1])
        W.gx[a0 + 1:a1 - 1, b0 + 1:b1 - 1] = gx_[1:-1, 1:-1]
        W.gz[a0 + 1:a1 - 1, b0 + 1:b1 - 1] = gz_[1:-1, 1:-1]
        W.slope[a0 + 1:a1 - 1, b0 + 1:b1 - 1] = np.hypot(gx_, gz_)[1:-1, 1:-1]

        def dh(px, pz):
            if not (x0 <= px < x1 - 1 and z0 <= pz < z1 - 1):
                return 0.0
            return float(sample(delta, px - x0, pz - z0))
        for o in self.objects:
            p = o["p"]
            if x0 <= p[0] < x1 and z0 <= p[2] < z1:
                p[1] = round(p[1] + dh(p[0], p[2]), 3)
        for l in W.lights:
            p = l["p"]
            if x0 <= p[0] < x1 and z0 <= p[2] < z1:
                p[1] = round(p[1] + dh(p[0], p[2]), 2)
        for f in W.fx:
            p = f["p"]
            if x0 <= p[0] < x1 and z0 <= p[2] < z1:
                p[1] = float(p[1]) + dh(p[0], p[2])
        return True

    def root_drop(self, x, z, rad):
        """둘레 8 점(반지름 rad) 가운데 가장 낮은 지형이 가운데보다 얼마나 낮은지"""
        c = self.height(x, z)
        lo = min(self.height(x + math.cos(k * math.pi / 4) * rad, z + math.sin(k * math.pi / 4) * rad) for k in range(8))
        return c - lo

    def put(self, a, x, z, yaw=None, s=None, tilt=None, align=None, y=None, check=True, r=None,
            road=True, water=True, slope=0.75, stamp=None, occupy=True, ground=None, ground_margin=None, align_max=None, pad=True,
            bury_max=None, bury_reject=None):
        """소품 하나. META 기본값(크기·기울기·묻기·경사 맞춤)을 쓴다. 성공하면 True
        align: True/False 또는 0~1 (지형 법선 쪽으로 기울이는 비율), align_max: 기울임 상한(도)
        ground: "box" 면 기울인 바닥 상자 전체가 땅에 닿게 높이를 정한다 (절벽은 기본). ground_margin: 더 묻는 깊이(m)
        pad: 바닥 상자 접지에서 오르막 쪽이 높이의 BURY_MAX 넘게 묻히면 밑을 조금 고른다 (안 되면 check 일 때 놓지 않는다)
        bury_max: 이 소품만 BURY_MAX 대신 (실제 메쉬 바닥이 상자보다 거친 대체 소품 등). bury_reject: 묻힘 때문에 놓지 않는가
        (기본 = check. 장면의 loose 요소는 겹침 검사는 끄되 묻힘 검사는 켠다)"""
        m = self.meta.get(a)
        if m is None:
            if a in NEW_PROPS:
                return self._put_sub(a, x, z, yaw=yaw, s=s, tilt=tilt, align=align, y=y, check=check, r=r, road=road, water=water,
                                     slope=slope, stamp=stamp, occupy=occupy, ground=ground, ground_margin=ground_margin,
                                     align_max=align_max, pad=pad, bury_max=bury_max, bury_reject=bury_reject)
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
        if kind == "tree":
            self._claim(a, x, z, fp, kind, occupy, stamp)
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
        q0 = q
        if ground is None and (a.startswith("cliff_") or a == "fence"):
            ground = "box"              # 절벽·울타리: 길쭉해서 가운데 둘레만 보면 비탈에서 한쪽 끝이 뜬다
        sink_ok = a.startswith("cliff_") and s > 0.6 or ground_margin is not None and ground_margin > 0.25 or a in BURY_FREE
        boxed = False
        for attempt in range(2):
            q = q0
            if al > 0:
                n = self.normal(x, z)
                ang = math.acos(max(-1.0, min(1.0, n[1]))) * al
                if align_max is not None:
                    ang = min(ang, math.radians(align_max))
                if ang > 1e-4:
                    q = quat_mul(quat_axis((n[2], 0.0, -n[0]), ang), q0)
            if y is not None:
                yy = y
                break
            if ground == "box":
                gm = ground_margin
                if gm is None:
                    gm = 0.3 if (a.startswith("cliff_") and s > 0.6) else m.get("sink", 0.0) * s
                yy = self.box_ground(m, x, z, q, s, gm)
                boxed = True
                hgt = (m.get("_size") or [1, 1, 2 * m.get("footprint", 0.5)])[2] * s
                bury = self._spread + gm
                if hgt < 1.0 and a not in ("log_fallen", "stone_wall_low", "standing_stone", "iron_fence"):
                    sink_ok = True                     # 낮은 것(관·잔해)은 묻혀도 눈에 띄지 않는다 (쓰러진 나무는 v3 검토 반영으로, 줄인 돌담 토막·작은 선돌은 w4 에서 본다)
                if a == "log_fallen" and bury_max is None:
                    bury_max = 0.5                     # 쓰러진 나무: 오르막 쪽 끝이 키의 반까지 (가운데는 반 아래로)
                # v3: 큰 소품이 비탈 오르막 쪽에 높이의 25% 넘게 묻히면 밑을 조금 고른다 (의도된 묻힘: 절벽·묻는 깊이를 준 것은 빼고)
                if sink_ok or bury <= (BURY_MAX if bury_max is None else bury_max) * hgt:
                    break
                if attempt == 0 and pad:
                    size = m.get("_size") or [2 * m.get("footprint", 0.5)] * 3
                    rin = 0.5 * math.hypot(size[0] * s, size[1] * s) + 0.4
                    if self.terraform(x, z, rin, rin + max(4.0, 3.5 * self._spread), "flat", 1.0):
                        self.pads += 1
                        continue
                if check if bury_reject is None else bury_reject:
                    self.pad_reject += 1
                    self.pad_reject_by[a] += 1
                    return False
                break
            else:
                hs = [self.height(x, z)]
                if al <= 0:
                    for k in range(6):
                        t = k / 6 * 2 * math.pi
                        hs.append(self.height(x + math.cos(t) * fp * 0.7, z + math.sin(t) * fp * 0.7))
                    yy = min(hs) * 0.6 + hs[0] * 0.4
                else:
                    yy = hs[0]
                yy -= m.get("sink", 0.0) * s
                break
        self._claim(a, x, z, fp, kind, occupy, stamp)
        if boxed:
            self.boxed.append((len(self.objects), bool(sink_ok)))
        if kind == "landmark" or fp > 4.0:
            self.anchors.append((x, z, fp))
        self.objects.append({"a": a, "p": [round(x, 3), round(float(yy), 3), round(z, 3)],
                             "q": [round(v, 5) for v in q], "s": round(s, 3)})
        return True

    def _claim(self, a, x, z, fp, kind, occupy, stamp):
        if occupy:
            self.occupy(x, z, fp)
        if stamp:
            self.stamps.append((x, z, fp * stamp[1], stamp[0]))
        elif kind == "scatter":
            self.stamps.append((x, z, max(fp * 0.8, 1.8), "clear"))      # 작은 발광 소품·해골이 낮은 눈높이에서 풀에 가리지 않게
        else:
            self.stamps.append((x, z, fp * 0.8, "clear"))
        self.count[a] = self.count.get(a, 0) + 1

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
            if e < 0.93 and abs(x - cx) > 6.5 and abs(z - cz) > 5.5 and noise_skip(x, z) > -0.07 and rng.random() > 0.26 \
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
        P.put("fence", x, z, yaw=th, check=False, tilt=3 if rng.random() < 0.8 else 6, stamp=("dirt", 0.7), bury_reject=True,
              bury_max=FILL_UPRIGHT_BURY)            # v3 검토 반영: 비탈에서 한쪽 끝이 깊이 묻히는 칸은 비운다
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
    # v3: 수레는 길 가장자리에서 3.5~7 m, 어귀 둘레 몇 자리를 차례로 본다 (v2 는 한 자리만 봐서 길 검사에 걸려 빠졌다)
    W.village_cart = False
    for along in (30, 36, 24, 42):
        for side in (1, -1):
            for gap in (3.5, 5.0, 6.5):
                rx_, rz_, ryw, _, _ = road_point(W, 5, cx - along, cz, side, gap)
                if P.put("cart_broken", rx_, rz_, yaw=ryw + 70, stamp=("dirt", 1.2)):
                    W.village_cart = True
                    break
            if W.village_cart:
                break
        if W.village_cart:
            break
    log("마을 어귀 수레:", "놓임" if W.village_cart else "못 놓음")
    P.put("hanging_cage", cx - 40, cz + 22, yaw=yaw_to(1, -0.3))
    P.put("brazier", cx - 4.5, cz + 3.0)
    W.lights.append({"p": [round(cx - 4.5, 2), round(P.height(cx - 4.5, cz + 3.0) + 2.6, 2), round(cz + 3.0, 2)], "c": SPIRIT,
                     "i": 4.0, "r": 8.0, "flicker": True, "far": 150.0})          # 우물가 등대 빛 (마을이 멀리서 보이게)
    P.scatter("stump", 6, in_disk((cx, cz), 68, 20))
    P.scatter("log_fallen", 3, in_disk((cx, cz), 68, 20), ground="box")
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
    P.scatter("dead_tree_b", 95, dry, water=True)          # v3: 면적당 v1 이상 (넓이 0.578 배: 160 → 93, 70 → 41)
    P.scatter("dead_tree_c", 42, dry)
    P.scatter("roots", 30, dry)
    P.scatter("log_fallen", 22, dry, ground="box")
    P.scatter("stump", 26, dry)
    P.scatter("mushroom_toxic", 44, dry)
    P.scatter("bush_dead", 40, dry)
    P.scatter("rock_flat", 10, dry)
    P.scatter("grave_sunken", 14, dry)
    P.scatter("grave_slab_c", 8, dry)
    P.scatter("skeleton_remains", 6, dry)
    # 물속에 선 고목 (뿌리가 잠김): 물 위에서도 자리를 차지
    for i in range(240):
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
        l = {"p": [round(x, 2), round(max(P.height(x, z), lev) + rng.uniform(1.2, 3.0), 2), round(z, 2)],
             "c": SPIRIT if i % 3 else SOUL, "i": round(rng.uniform(3.5, 6), 2), "r": round(rng.uniform(7, 11), 1), "flicker": True}
        if i % 4 == 0:
            l["far"] = FAR                       # v3: 늪 둘레에서 늪이 보이게 (등대 빛)
        P.W.lights.append(l)


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
    # 뼈 장면 셋 — 새끼 용의 뼈, 뼈 무더기 제단(화로와 초), 뼈 가시 고리(영혼 불꽃).
    # v3: 장면마다 등대 빛(far)과 키 큰 뼈 가시(3.5 m 넘게)를 둔다. 로컬 좌표 = 월드 방향 (fy 0)
    spots = []
    for ang, dist in ((2.3, 70.0), (4.1, 62.0), (0.9, 85.0)):
        spots.append((cx + math.cos(ang) * dist, cz + math.sin(ang) * dist))
    made = []
    # 1) 새끼 용: 웅크린 작은 해골 (몸을 둥글게 만다)
    jx, jz = spots[0]
    S = Scene(W, P, "dragon_young", jx, jz, 0.0)
    b = rng.uniform(0, 2 * math.pi)
    S.put("dragon_skull", math.cos(b) * 3.0, math.sin(b) * 3.0, ayaw=math.degrees(b) + 60, s=0.55, check=False, stamp=("ash", 1.4), req=True)
    S.put("dragon_ribs", 0, 0, ayaw=math.degrees(b) + 90, s=0.5, check=False, stamp=("ash", 1.2), req=True)
    for k in range(2):
        bb = b + math.pi * (0.7 + 0.45 * k)
        S.put("dragon_spine", math.cos(bb) * 4.0, math.sin(bb) * 4.0, ayaw=math.degrees(bb) + 90, s=0.45, check=False)
    S.put("dragon_claw", math.cos(b - 1.2) * 3.2, math.sin(b - 1.2) * 3.2, s=0.5, check=False)
    for k in range(2):                                  # 새끼를 지키듯 선 큰 뼈 가시 (세로 실루엣)
        bb = b + math.pi + (k - 0.5) * 0.9
        S.put("bone_spike", math.cos(bb) * 6.5, math.sin(bb) * 6.5, s=1.3, slope=None, tag="bone_spike_tall", req=(k == 0))
    S.light(SOUL, 4.0, 9.0, 0, 0, up=2.2, far=FAR)
    made.append(S)
    # 2) 뼈 무더기 제단: 뼈 무더기 고리 + 해골 + 초 + 화로 (누가 아직 제물을 바친다)
    ox, oz = spots[1]
    S = Scene(W, P, "bone_altar", ox, oz, 0.0)
    for k in range(6):
        a_ = k / 6 * 2 * math.pi + rng.uniform(-0.2, 0.2)
        S.put("bone_pile", math.cos(a_) * 4.2, math.sin(a_) * 4.2, check=False, s=rng.uniform(1.1, 1.4), stamp=("ash", 1.3), tag="bone_ring")
    for k in range(10):
        S.put("skull", rng.normal(0, 2.2), rng.normal(0, 2.2), road=False)
    for k in range(4):
        a_ = rng.uniform(0, 2 * math.pi)
        S.put("candles", math.cos(a_) * 2.0, math.sin(a_) * 2.0, road=False)
    S.put("brazier", 0, 0, check=False, req=True)
    for sd in (-1, 1):
        S.put("bone_spike", sd * 6.6, rng.uniform(-1.5, 1.5), s=1.3, slope=None, tag="bone_spike_tall", req=(sd < 0))
    for k in range(3):
        S.put("skeleton_remains", rng.uniform(-7, 7), rng.uniform(-7, 7))
    if S.beacon is None:
        S.light(SPIRIT, 4.0, 8.0, 0, 0, up=2.0, far=FAR)
    made.append(S)
    # 3) 뼈 가시 고리: 바깥을 향해 기운 가시 8 개, 가운데 영혼 불꽃
    rx_, rz_ = spots[2]
    S = Scene(W, P, "spike_ring", rx_, rz_, 0.0)
    for k in range(8):
        a_ = k / 8 * 2 * math.pi
        S.put("bone_spike", math.cos(a_) * 6.5, math.sin(a_) * 6.5, s=rng.uniform(1.15, 1.3), slope=None, req=True)
    S.fx("soulfire", 4, up=0.8)
    S.light(SOUL, 5.0, 10.0, up=2.2, far=FAR)
    made.append(S)
    for S in made:
        P.reserve(S.x, S.z, 9.0)
        S.finish()
        W.scenes.append({"type": S.kind, "p": [round(S.x, 1), round(S.z, 1)], "r": 9.0, "yaw": 0.0, "props": S.n, "feature": "dragon",
                         "road_d": round(face_road(W, S.x, S.z)[1], 1), "hamlet": -1,
                         "top": [round(S.top[0], 2), round(S.top[1], 2), round(S.top[2], 2)], "tall": round(S.top[3], 2),
                         "beacon": [round(v, 2) for v in S.beacon] if S.beacon else None})
    area = in_disk(DRAGON, DRAGON_R - 15)
    P.scatter("bone_spike", 46, area)             # v3: 면적당 v1 이상 (넓이 0.625 배: 70 → 44 이상, 150 → 94 이상)
    P.scatter("bones_scatter", 96, area)
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
        l = {"p": [round(x, 2), round(P.height(x, z) + 2.5, 2), round(z, 2)], "c": SOUL, "i": 5.0, "r": 12.0, "flicker": True}
        if t < 20:
            l["far"] = 160.0                   # v3: 등대 빛
        W.lights.append(l)


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
    W.lights.append({"p": [cx, round(P.height(cx, cz) + 6.0, 2), cz], "c": SOUL, "i": 6.0, "r": 12.0, "flicker": True, "far": 170.0})


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


FORESTS = ((FOREST_SW[0], FOREST_SW[1], 1 / 70.0, 1301, ("camp", "crystal", "barrow")),
           (FOREST_NE[0], FOREST_NE[1], 1 / 71.0, 1311, ("crystal", "camp")))   # v3: 면적당 죽은 나무 v1 이상 (1/85 → 1/75 → 채움 1/71:
#   잔굴곡 위 빈터 장면 자리가 바뀌어도 v1 밀도 35.2 그루/ha 아래로 내려가지 않게)


def forest_mask(W, center, R, seed):
    """숲이 덮는 넓이 (0~1). 장면 계획(숲 가장자리·숲 길목)과 lay_forest 가 같이 쓴다"""
    X, Z = W.X, W.Z
    rs, cs, d = disk(W.h.shape, center[0], center[1], R + 40)
    Xs, Zs = X[rs, cs], Z[rs, cs]
    edge = R + 45 * fbm(Xs, Zs, 1 / 120, 3, seed)
    m = np.zeros(W.h.shape, np.float32)
    m[rs, cs] = ss(-(d / edge), -1.0, -0.6) * (0.55 + 0.45 * ss(fbm(Xs, Zs, 1 / 60, 3, seed + 1), -0.4, 0.4))
    m *= (W.slope < 0.7)
    rs2, cs2, dt = disk(W.h.shape, TREE[0], TREE[1], 36)
    m[rs2, cs2] *= ss(dt, 26, 34)                     # 영혼의 고목 둘레는 비워 거목이 드러나게
    return m, rs, cs, d


def forest_plan(W):
    W.forest_plan = np.zeros(W.h.shape, np.float32)
    for c, R, _, seed, _ in FORESTS:
        W.forest_plan = np.maximum(W.forest_plan, forest_mask(W, c, R, seed)[0])


def lay_forest(W, P, center, R, density, seed, clearings=()):
    """죽은 숲. v2: 덤불숲(시야가 막힘)과 빈터(시야가 열림)가 번갈아 오고, 빈터 몇 곳에 작은 장면(clearings 종류).
    v3: 같은 틀이 200 m 안에 이미 있으면 다른 틀(야영지·수정·둔덕·전장)로"""
    rng = P.rng
    X, Z = W.X, W.Z
    m, rs, cs, d = forest_mask(W, center, R, seed)
    Xs, Zs = X[rs, cs], Z[rs, cs]
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
        pref = clearings[len(got)]
        for kind in [pref] + [k for k in ("camp", "crystal", "barrow", "battle") if k != pref]:
            if lay_scene(W, P, kind, p[0], p[1], feature="forest_clearing"):
                got.append(p)
                break
    # 나무는 덤불숲에 몰리고 빈터에는 드물게, 덤불·쓰러진 나무는 덤불숲에 빽빽하게
    area_t = in_mask(W, m * (0.12 + 0.55 * (1 - glade) + 0.9 * thick))
    area_b = in_mask(W, m * (0.04 + thick) * (1 - glade))
    area_g = in_mask(W, m * glade)
    area_tot = float(m.sum())
    nt = int(area_tot * density)
    for nm_, fr_ in (("dead_tree_a", 0.34), ("dead_tree_c", 0.22), ("dead_tree_b", 0.22)):
        want = int(nt * fr_ * 1.05 * DEAD_TREE_CUT)
        got_ = P.scatter(nm_, want, area_t)
        if got_ < want:                       # v3: 잔굴곡(둔덕·턱) 위에서 뿌리가 뜨는 자리가 늘어 모자라면 더 시도 (숲 밀도 유지)
            P.scatter(nm_, want - got_, area_t, tries=24)
    P.scatter("bramble", int(nt * 0.75), area_b)
    P.scatter("bush_dead", int(nt * 0.55), area_b)
    P.scatter("log_fallen", int(nt * 0.13), area_b, ground="box")
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
    P.scatter("log_fallen", 3, shore, ground="box")
    for i in range(8):
        x, z = area(rng)
        l = {"p": [round(x, 2), round(max(P.height(x, z), lev) + rng.uniform(0.8, 2.2), 2), round(z, 2)], "c": SPIRIT, "i": 3.5, "r": 8.0, "flicker": True}
        if i < 2:
            l["far"] = FAR
        W.lights.append(l)
    W.fx.append({"type": "mist", "p": [LAKE[0], lev + 0.3, LAKE[1]], "r": 58})
    W.fx.append({"type": "fireflies", "p": [LAKE[0], lev + 1.5, LAKE[1]], "r": 50})


MFOOT_CLUSTERS = 125         # 벼랑 밑동 바위 무리 수 (둘레를 따라)
MFOOT_GAP = 34.0             # 바위 무리 사이 최소 (m)
MFOOT_BURY = 0.48            # 벼랑 밑동 큰 절벽 바위를 묻는 비율 (높이의 반쯤)


def foot_frame(W, x, z):
    """발치 자리의 (안쪽 단위 벡터, 둘레 방향 단위 벡터, 안쪽을 보는 yaw). 안쪽 = dd 가 줄어드는 쪽"""
    gx, gz = float(sample(W.dd, x + 1.0, z) - sample(W.dd, x - 1.0, z)), float(sample(W.dd, x, z + 1.0) - sample(W.dd, x, z - 1.0))
    n = math.hypot(gx, gz)
    if n < 1e-6:
        gx, gz, n = sample(W.gx, x, z), sample(W.gz, x, z), 1.0
        n = math.hypot(gx, gz) or 1.0
    ix, iz = -gx / n, -gz / n
    return (ix, iz), (-iz, ix), yaw_to(ix, iz)


def lay_mountain_foot(W, P):
    """산기슭. v3 검토 반영: 벽 비탈 턱(발치보다 10~55 m 위)에 떠 붙어 보이던 바위·절벽은 두지 않는다.
    1) 벼랑 밑동 바위 무리: 발치 선을 따라 큰 절벽 바위(cliff_a·c, 가끔 바위 기둥 cliff_b)를 반쯤 묻는다
       (Unity 지형은 가파른 면에서 텍스처가 늘어나므로 가장 눈에 띄는 벽 밑동을 메쉬 바위로 가린다)
    2) 그 앞 너덜: 굴러떨어진 큰 돌(반쯤 묻힘)과 작은 돌. 골 어귀(너덜 부채꼴)에는 더 많이
    3) 발치 너덜 띠: 비탈이 평지와 만나는 곳의 작은 돌"""
    rng = P.rng
    dd = W.dd
    W.foot_items = []
    gate_far = (np.hypot(W.X - GATE[0], W.Z - GATE[1]) > 95).astype(np.float32)
    foot = ((dd > -3.0) & (dd < 2.5)).astype(np.float32) * gate_far
    pick = in_mask(W, foot)
    centers, nb = [], collections.Counter()
    for _ in range(MFOOT_CLUSTERS * 40):
        if len(centers) >= MFOOT_CLUSTERS:
            break
        p = pick(rng)
        if p is None:
            break
        x, z = p
        if any((x - a) ** 2 + (z - b) ** 2 < MFOOT_GAP ** 2 for a, b in centers):
            continue
        if sample(W.road_dist, x, z) < sample(W.road_hw, x, z) + 8 or P.under_water(x, z, 0.5):
            continue
        (ix, iz), (tx, tz), yin = foot_frame(W, x, z)
        nm, lo, hi = [("cliff_a", 1.25, 1.95), ("cliff_c", 1.15, 1.75), ("cliff_a", 1.1, 1.6), ("cliff_b", 0.75, 1.1)][int(rng.choice(4, p=[0.35, 0.35, 0.15, 0.15]))]
        sc_ = rng.uniform(lo, hi)
        hgt = (P.meta.get(nm, {}).get("_size") or [1, 1, 8])[2] * sc_
        bx, bz = x - ix * rng.uniform(0.5, 3.0), z - iz * rng.uniform(0.5, 3.0)       # 벽 쪽으로 조금 (밑동에 기대어)
        if not P.put(nm, bx, bz, yaw=yin + rng.normal(0, 14), s=sc_, slope=None, align=0.3, align_max=15, ground="box",
                     ground_margin=hgt * MFOOT_BURY, stamp=("rock", 1.25)):
            continue
        centers.append((x, z))
        nb[nm] += 1
        W.foot_items.append({"t": "foot_rocks", "p": [round(x, 1), round(z, 1)], "main": nm, "h": round(hgt * (1 - MFOOT_BURY), 1)})
        mouth = sample(W.spur, x, z) < 0.42
        for q in range(int(rng.integers(1, 3))):                       # 옆에 작은 절벽 조각 (같은 벽에서 떨어져 나온)
            sd = 1 if rng.random() < 0.5 else -1
            o_ = rng.uniform(5.0, 10.0) * sd
            k = rng.uniform(-1.0, 4.0)
            n2 = "cliff_c" if rng.random() < 0.6 else "cliff_a"
            s2 = rng.uniform(0.5, 0.85)
            h2 = (P.meta.get(n2, {}).get("_size") or [1, 1, 6])[2] * s2
            if P.put(n2, x + tx * o_ + ix * k, z + tz * o_ + iz * k, yaw=yin + rng.normal(0, 30), s=s2, slope=None, align=0.4,
                     align_max=20, ground="box", ground_margin=h2 * 0.42, stamp=("rock", 1.2)):
                nb["piece"] += 1
        nbig = int(rng.integers(2, 5)) if mouth else int(rng.integers(1, 3))
        for q in range(nbig):                                          # 굴러떨어진 큰 돌 (반쯤 묻힘)
            d_ = rng.uniform(4.0, 15.0 if mouth else 9.0)
            o_ = rng.normal(0, 5.0)
            n3 = "rock_b" if rng.random() < 0.6 else "rock_flat"
            s3 = rng.uniform(0.7, 1.25)
            h3 = (P.meta.get(n3, {}).get("_size") or [1, 1, 1.5])[2] * s3
            if P.put(n3, x + ix * d_ + tx * o_, z + iz * d_ + tz * o_, yaw=rng.uniform(0, 360), s=s3, slope=0.8, ground="box",
                     align_max=30, ground_margin=h3 * 0.3, stamp=("rock", 1.2)):
                nb["talus_big"] += 1
        for q in range(int(rng.integers(3, 7)) if mouth else int(rng.integers(1, 4))):     # 작은 돌
            d_ = rng.uniform(3.0, 18.0 if mouth else 10.0)
            o_ = rng.normal(0, 6.0)
            if P.put("rock_a" if rng.random() < 0.45 else "rock_c", x + ix * d_ + tx * o_, z + iz * d_ + tz * o_,
                     s=rng.uniform(0.8, 1.5), slope=0.4):
                nb["talus_small"] += 1
        if mouth:
            P.stamps.append((x + ix * 8.0, z + iz * 8.0, rng.uniform(7.0, 10.0), "rock"))
    # 3) 발치 너덜 띠: 비탈이 평지와 만나는 발치 (완만한 곳이라 지형 나무 바위도 땅에 붙는다)
    st = (W.slope > 0.45).astype(np.float32) * (W.mount < 0.75)
    scree = (box_blur(st, 2) > 0.02) * (W.slope < 0.4) * (W.mount < 0.75) * (np.hypot(W.X - GATE[0], W.Z - GATE[1]) > 30) * (W.dd < 3.0)  # 벽 위 층진 턱(평평한 곳)에는 두지 않는다
    a3 = in_mask(W, scree.astype(np.float32))
    n1 = P.scatter("rock_a", 110, a3, slope=0.4)
    n2 = P.scatter("rock_c", 150, a3, slope=0.4)
    log("산기슭: 벼랑 밑동 바위 무리 %d (%s), 발치 너덜 띠 돌 %d" % (len(centers), dict(nb), n1 + n2))


# ─────────────────────────── 작은 장면 (v3: 길과 지형을 따라 구조) ───────────────────────────
# v2 는 '가장 먼 땅부터' 80 m 간격으로 고르게 뿌려 물방울 무늬가 됐다. v3 는 구조를 만든다:
#  - 들판 장면의 60% 넘게 길에서 40 m 안: 갈림길, 굽은 곳, 언덕 마루, 다리·개울가, 숲으로 들어가는 길목
#  - 나머지는 지형 특징 자리에만: 언덕 꼭대기, 능선, 개울가, 숲 가장자리, 움푹한 곳 (아무 특징 없는 평지에는 놓지 않는다)
#  - 조밀한 무리(장면 2~3 개 + 장소가 서로 보이는 '마을 같은 무리', HAMLETS)와 조용한 구역(_zones.json, 다음 단계가 채운다)
#  - 시선: 길을 10 m 마다 걸으며, 또 길 밖 땅에서 150 m 안에 장면·장소·등대 빛이 보이게 (지형 시선, 눈높이 1.7 m)
#  - 같은 틀 장면은 200 m 안에 둘 두지 않는다. 장면마다 키 3.5 m 넘는 세로 요소와 등대 빛(far 140 m) 하나 이상
# 장면 틀: (차지하는 반지름 m, 길가 선호, 들판(지형 특징) 선호)
SCENES = {
    "execution": (9.0, 1.0, 0.6),     # 처형터: 교수대·매달린 새장·해골·화로
    "chapel":    (10.0, 0.7, 1.0),    # 무너진 예배당: 아치·담·기둥·석관 제단·영혼 불꽃
    "shrine":    (5.5, 1.4, 0.15),    # 길가 사당: 작은 사당·선돌 이정표·양초·등불 (길가만)
    "barrow":    (11.0, 0.5, 1.2),    # 선돌이 둘러선 무덤 둔덕: 지형 둔덕 + 선돌 고리 + 입구 돌 + 영혼 불꽃
    "camp":      (8.5, 0.9, 0.9),     # 버려진 야영지: 모닥불·찢긴 천막·통나무 의자·부서진 수레·깃발
    "crystal":   (7.0, 0.35, 1.1),    # 영혼 수정 노두: 바위 기둥에서 솟은 수정
    "family":    (9.0, 0.9, 0.8),     # 가족 묘역: 작은 납골당·사슬 오벨리스크·쇠 울타리·묘비
    "battle":    (12.0, 0.6, 1.0),    # 전장의 흔적: 찢긴 깃발·해골 유해·뼈 무더기
    "outpost":   (8.0, 1.4, 0.2),     # 길목 초소: 낮은 돌담 ㄱ 자·화로·깃발·무너진 모서리 (길가만)
    "graves":    (8.0, 1.0, 0.8),     # 외딴 무덤 무리: 길가 고목 아래 묘비 몇·부서진 쇠 울타리·무덤 위 영혼 불
    "farmstead": (12.0, 0.8, 0.9),    # 버려진 농가: 낮은 돌담 울·집터 담·우물·마당 고목·수레·꺼져 가는 불
    "pyre":      (8.0, 0.7, 0.9),     # 화장터: 엇갈려 쌓은 장작더미·재 바닥·해골·잉걸불·깃발 둘
}
# 틀별로 어울리는 자리 특징 (무게에 1 + 값을 곱한다)
SCENE_FEAT = {
    "execution": {"crest": 1.2, "hilltop": 1.4, "junction": 0.8, "ridge": 0.6},
    "chapel":    {"hilltop": 0.8, "crest": 0.6, "bend": 0.5, "ridge": 0.5},
    "shrine":    {"junction": 1.2, "bend": 1.0, "bridge": 1.0, "forest_entry": 0.8},
    "barrow":    {"hilltop": 1.6, "ridge": 1.4, "crest": 0.4},
    "camp":      {"forest_edge": 1.4, "creek": 1.2, "hollow": 0.8, "forest_entry": 0.8},
    "crystal":   {"hollow": 1.2, "creek": 1.0, "forest_edge": 0.8, "ridge": 0.3},
    "family":    {"bend": 0.8, "crest": 0.5, "forest_edge": 0.5, "hilltop": 0.4},
    "battle":    {"ridge": 1.0, "hilltop": 0.6, "creek": 0.6, "hollow": 0.5},
    "outpost":   {"crest": 1.4, "bridge": 1.2, "junction": 0.8, "forest_entry": 1.0},
    "graves":    {"forest_edge": 0.8, "hilltop": 0.6, "bend": 0.6, "creek": 0.4},
    "farmstead": {"creek": 1.0, "hollow": 0.8, "bend": 0.6, "junction": 0.5},
    "pyre":      {"hilltop": 1.0, "crest": 0.8, "ridge": 0.6, "junction": 0.4},
}
ROAD_FEATS = ("junction", "bend", "crest", "bridge", "forest_entry")
TERRAIN_FEATS = ("hilltop", "ridge", "creek", "forest_edge", "hollow")
SAME_TYPE_GAP = 200.0       # 같은 틀 장면 사이 최소 거리 (m)
SIGHT = 150.0               # 시선 지표 거리 (m)
EYE = 1.7                   # 눈높이 (m)
TALL = 3.6                  # 장면마다 이보다 키 큰 세로 요소 하나 이상 (100 m 밖 실루엣. 기준 3.5 m 에 여유)
HAMLETS = 9                 # 조밀한 무리 수 (장면 2~3 개 + 장소)
PAIRS = 8                   # 길목 짝: 장소가 안 보여도 강한 길 특징(갈림길·마루·굽은 곳) 양쪽에 장면 둘
ROADSIDE = 40.0             # '길가' = 장면 가운데가 길 중심선에서 이 거리 안
SCENE_GAP = 70.0            # 무리 밖 장면 사이 최소 거리 (시선 채우기)
ROAD_GAP, FIELD_GAP = 42.0, 95.0    # 보충 단계의 장면 사이 최소 거리: 길가(길 양쪽에 번갈아), 들판(조용한 구역을 남긴다)
ROAD_TARGET = 64            # 길 40 m 안 들판 장면 목표 (무리 포함)
SCENE_TARGET = 100          # 들판 장면 목표 수 (갈림길·숲 빈터·용의 무덤 장면 빼고). 길가 보충 → 들판 보충 순서
COVER_ROAD, COVER_OFF = 0.985, 0.93   # 계획 단계 시선 목표 (검사 기준 95% / 85% 보다 여유)
SCENE_STATS = {}            # (틀, 요소) → [시도, 놓임, 필수, 실패한 장면 수, 대체 없음]
SCENE_COUNT = {}            # 틀 → 장면 수


class Scene:
    """장면 하나의 로컬 좌표: 가운데 (x, z), 앞(+lz)이 yaw 쪽 (보통 가장 가까운 길), 오른쪽 +lx"""

    def __init__(self, W, P, kind, x, z, fy):
        self.W, self.P, self.kind, self.x, self.z, self.fy = W, P, kind, x, z, fy
        t = math.radians(fy)
        self.f = (math.sin(t), math.cos(t))
        self.r = (math.cos(t), -math.sin(t))
        self.n = 0
        self.beacon = None                    # (x, y, z, far) 등대 빛
        self.top = (x, P.height(x, z), z, 0.0)   # 가장 키 큰 것 (x, 꼭대기 y, z, 땅 위 높이)
        self.tags = {}                        # 요소 → [시도, 놓임, 필수, 대체 없음]
        # v3 검토 반영: 같은 틀 장면이 같은 자리에 같은 소품인 도장처럼 보였다 (가족 묘역 89%). 장면마다 배치를 흔든다:
        # 좌우 뒤집기, 앞뒤·좌우 배율, 요소마다 자리 흔들기, 꾸밈 요소 빼기·바꾸기 (필수 요소는 빼거나 바꾸지 않는다)
        rng = P.rng
        self.mx = -1.0 if rng.random() < 0.5 else 1.0
        self.sx, self.sz = rng.uniform(*SCENE_VARY_SCALE), rng.uniform(*SCENE_VARY_SCALE)

    def at(self, lx, lz):
        return (self.x + self.r[0] * lx + self.f[0] * lz, self.z + self.r[1] * lx + self.f[1] * lz)

    def put(self, a, lx, lz, yaw=None, ayaw=None, loose=False, slope=None, must=False, req=False, tag=None, vary=True, **kw):
        """yaw: 장면 앞 기준 회전(도), ayaw: 절대 회전. loose: 장면 안 다른 소품과의 겹침은 보지 않는다 (땅·길·물은 본다).
        must: 장면의 중심 소품 — 보통 검사로 안 되면 loose 로 한 번 더. must·req 는 필수 요소 (계획 vs 실제 집계에서
        틀 인스턴스의 20% 넘게 빠지면 생성 실패). slope: loose 로 놓을 때 기울기 한계 (v3: 0.6 → 0.35)"""
        tag = tag or a
        if vary:
            rng = self.P.rng
            opt = not (must or req)
            if opt and rng.random() < SCENE_VARY_DROP:
                return False                                   # 이 장면에는 없는 꾸밈 요소
            if opt and a in SCENE_SWAP and rng.random() < SCENE_VARY_SWAP:
                a = str(rng.choice(SCENE_SWAP[a]))             # 비슷한 다른 소품으로
            sig = SCENE_VARY_JIT[0] if must else (SCENE_VARY_JIT[1] if req else SCENE_VARY_JIT[2])
            lx = self.mx * lx * self.sx + rng.normal(0, sig)
            lz = lz * self.sz + rng.normal(0, sig)
            if yaw is not None and self.mx < 0:
                yaw = -yaw
        rec = self.tags.setdefault(tag, [0, 0, False, 0])
        rec[0] += 1
        rec[2] = rec[2] or must or req
        skip0 = self.P.sub_skip.get(a, 0)
        ok = self._put(a, lx, lz, yaw, ayaw, loose, slope, **kw)
        if not ok and (must or req) and self.P.sub_skip.get(a, 0) == skip0:
            # 필수 요소: 정한 자리 둘레 (0.9, 1.8 m) 를 차례로 보고, 그래도 안 되면 겹침 검사 없이 (loose) 정한 자리에
            for (dr, n) in ((0.9, 6), (1.8, 8)):
                for k in range(n):
                    t = k / n * 2 * math.pi + 0.3
                    if self._put(a, lx + math.cos(t) * dr, lz + math.sin(t) * dr, yaw, ayaw, loose, slope, **kw):
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                kw2 = dict(kw)
                kw2["bury_reject"] = False
                ok = self._put(a, lx, lz, yaw, ayaw, True, max(slope or 0.35, 0.45), **kw2)
        if ok:
            rec[1] += 1
        elif self.P.sub_skip.get(a, 0) > skip0:
            rec[3] += 1
        return ok

    def _put(self, a, lx, lz, yaw, ayaw, loose, slope, **kw):
        P, W = self.P, self.W
        x, z = self.at(lx, lz)
        kw = dict(kw)
        if a in BOX_GROUND:
            kw.setdefault("ground", "box")          # 길쭉하거나 큰 구조물: 바닥 상자 전체가 땅에 닿게 (비탈에서 한쪽이 뜨지 않게)
        if ayaw is None:
            ayaw = self.fy + yaw if yaw is not None else P.rng.uniform(0, 360)
        if loose:
            s0 = kw.get("s") or 1.0
            if not P.ok_ground(x, z, P.fp(a) * s0, kw.get("road", True), kw.get("water", True), 0.35 if slope is None else slope):
                return False
            kw["check"] = False
            kw.setdefault("bury_reject", True)       # 겹침은 보지 않되, 큰 구조물이 오르막에 묻히면 놓지 않는다
        else:
            kw.setdefault("slope", 0.6 if slope is None else slope)
        n0, t0, l0 = len(P.objects), len(P.trees), len(W.lights)
        if not P.put(a, x, z, yaw=ayaw, **kw):
            return False
        self.n += 1
        g = P.height(x, z)
        if len(P.objects) > n0:
            o = P.objects[-1]
            m = P.meta.get(o["a"], {})
            hz = (m.get("_size") or [0, 0, 0])[2] * o["s"]
            top = o["p"][1] + hz
            lt = m.get("light")
            if lt and (lt.get("far") or o.get("far")):
                self.beacon = (o["p"][0], o["p"][1] + lt["offset"][2] * o["s"], o["p"][2], float(o.get("far") or lt["far"]))
            self._top(o["p"][0], top, o["p"][2], top - g)
        elif len(P.trees) > t0:
            tr = P.trees[-1]
            m = P.meta.get(P.protos[tr[0]], {})
            hz = ((m.get("_size") or [0, 0, 0])[2] - m.get("sink", 0.0)) * tr[4]
            self._top(tr[1], g + hz, tr[2], hz)
        for l in W.lights[l0:]:
            if l.get("far"):
                self.beacon = (l["p"][0], l["p"][1], l["p"][2], l["far"])
        return True

    def _top(self, x, y, z, hgt):
        if hgt > self.top[3]:
            self.top = (x, y, z, hgt)

    def light(self, c, i, r, lx=0.0, lz=0.0, up=2.0, far=None):
        x, z = self.at(lx, lz)
        l = {"p": [round(x, 2), round(self.P.height(x, z) + up, 2), round(z, 2)], "c": list(c), "i": float(i), "r": float(r), "flicker": True}
        if far:
            l["far"] = float(far)
            self.beacon = (l["p"][0], l["p"][1], l["p"][2], float(far))
        self.W.lights.append(l)

    def fx(self, t, r, lx=0.0, lz=0.0, up=1.0):
        x, z = self.at(lx, lz)
        self.W.fx.append({"type": t, "p": [x, self.P.height(x, z) + up, z], "r": r})

    def floor(self, kind, r, lx=0.0, lz=0.0):
        x, z = self.at(lx, lz)
        self.P.stamps.append((x, z, r, kind))

    def finish(self):
        """틀 요소 집계 (계획 vs 실제)"""
        SCENE_COUNT[self.kind] = SCENE_COUNT.get(self.kind, 0) + 1
        for tag, (n, ok, req, skip) in self.tags.items():
            st = SCENE_STATS.setdefault((self.kind, tag), [0, 0, False, 0, 0])
            st[0] += n
            st[1] += ok
            st[2] = st[2] or req
            st[3] += (req and ok == 0)
            st[4] += skip


SCENE_VARY_SCALE = (0.86, 1.18)      # 장면마다 틀 배치의 좌우·앞뒤 배율
SCENE_VARY_JIT = (0.35, 0.55, 0.8)   # 요소 자리 흔들기 (m, 표준편차): 중심 소품, 필수 요소, 꾸밈 요소
SCENE_VARY_DROP = 0.18               # 꾸밈 요소를 이 장면에서 빼는 비율
SCENE_VARY_SWAP = 0.3                # 꾸밈 요소를 비슷한 다른 소품으로 바꾸는 비율
SCENE_SWAP = {"rubble": ("rock_c", "bone_pile", "stump"), "bone_pile": ("rubble", "bones_scatter"), "rock_a": ("rock_c", "rubble"),
              "rock_b": ("rock_flat",), "rock_flat": ("rock_b",), "grave_slab_a": ("grave_slab_b", "grave_cross", "grave_slab_c"),
              "grave_slab_b": ("grave_slab_a", "grave_sunken"), "grave_slab_c": ("grave_cross", "grave_slab_a"), "grave_cross": ("grave_slab_c", "grave_slab_b"),
              "pillar_b": ("rubble", "pillar_a"), "stump": ("roots", "rubble"), "bones_scatter": ("skull", "bone_pile"),
              "statue_angel": ("statue_reaper", "grave_obelisk"), "flower_lily": ("bush_dead",), "skull": ("bones_scatter",)}
BOX_GROUND = {"wall_ruin_a", "wall_ruin_b", "arch_ruin", "pillar_b", "mausoleum_small", "sarcophagus", "cart_broken", "tent_torn",
              "log_fallen", "gallows", "iron_fence", "stone_wall_low", "standing_stone", "cliff_b", "grave_tomb", "well"}


def polar(rng, r0, r1):
    a = rng.uniform(0, 2 * math.pi)
    d = math.sqrt(rng.uniform((r0 / r1) ** 2, 1)) * r1
    return math.cos(a) * d, math.sin(a) * d


def sc_execution(S, rng):
    S.floor("dirt", 5.5)
    S.put("gallows", 0, 0, yaw=rng.normal(0, 5), must=True, stamp=("dirt", 1.6))
    S.put("brazier", 3.6, 2.6, yaw=0, req=True)        # 필수 요소는 무작위로 흩는 해골·초보다 먼저 (v3 첫 판: 해골이 자리를 차지해 빠졌다)
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
    if rng.random() < 0.6:
        sd = rng.choice([-1, 1])
        S.put("fence", sd * 5.6, 5.0, yaw=rng.normal(0, 8), tilt=8)


def sc_chapel(S, rng):
    hw, hd = 4.2, 6.0
    S.floor("path", 5.5)
    S.floor("rock", 3.0, 0, -1.0)
    S.put("arch_ruin", 0, hd, yaw=rng.normal(0, 3), must=True)
    for sd in (-1, 1):
        for lz, nm in ((2.6, "wall_ruin_a"), (-2.8, "wall_ruin_b")):
            if rng.random() < 0.8:
                S.put(nm, sd * hw, lz, yaw=90 * sd + rng.normal(0, 4), loose=True, stamp=("dirt", 1.1), tag="wall")
    if rng.random() < 0.6:
        S.put("wall_ruin_b", 0, -hd - 0.4, yaw=180 + rng.normal(0, 4), loose=True, tag="wall")
    for sd in (-1, 1):                       # 안쪽은 가는 기둥만 (담 안쪽 면 |lx| 2.7 까지), 부러진 큰 기둥은 담 밖에
        if rng.random() < 0.8:
            S.put("pillar_a", sd * 1.9, 0.9, yaw=rng.uniform(0, 360), loose=True)
        if rng.random() < 0.5:
            S.put("pillar_a", sd * 1.9, -1.6, yaw=rng.uniform(0, 360), loose=True)
    if rng.random() < 0.7:
        a_ = rng.uniform(0, 2 * math.pi)
        S.put("pillar_b", math.cos(a_) * 8.0, math.sin(a_) * 8.0, yaw=rng.uniform(0, 360))
    S.put("sarcophagus", 0, -3.7, yaw=90 + rng.normal(0, 3), loose=True, req=True)
    for (lx, lz) in ((-1.4, -2.0), (1.4, -2.1), (0.2, -1.6)):
        S.put("candles", lx + rng.normal(0, 0.15), lz + rng.normal(0, 0.15), loose=True)
    S.light(SOUL, 4.5, 8.0, 0, -3.0, up=1.8, far=FAR)            # 제단 위 영혼 불꽃 (등대 빛)
    S.fx("soulfire", 2.5, 0, -3.0, up=1.2)
    S.put("lantern", hw + 1.6, hd + 1.4, yaw=rng.normal(0, 10))
    for k in range(3):
        S.put("rubble", *polar(rng, 2.0, 8.0))
    for k in range(int(rng.integers(1, 4))):                # 예배당 마당의 오래된 무덤
        S.put(["grave_slab_c", "grave_cross", "grave_slab_a"][k], -hw - 2.2 - k * 0.4, hd - 1.0 - k * 2.0, yaw=rng.normal(0, 8))
    if rng.random() < 0.3:
        S.put("statue_angel", hw + 2.0, -hd + 1.0, yaw=rng.normal(0, 10))


def sc_shrine(S, rng):
    S.floor("path", 2.4)
    S.put("shrine_roadside", 0, 0, yaw=rng.normal(0, 4), must=True, stamp=("path", 1.4))
    S.put("standing_stone", -2.4, -1.2, yaw=rng.normal(0, 12), s=rng.uniform(1.25, 1.35), req=True, tag="waystone", ground_margin=0.15)   # 이정표 선돌
    for k in range(3):
        S.put("candles", rng.uniform(-0.9, 0.9), rng.uniform(1.3, 1.9), loose=True)
    S.put("lantern", 2.1, 0.7, yaw=-20 + rng.normal(0, 8))
    for k in range(4):
        S.put("flower_lily", *polar(rng, 1.5, 3.4), loose=True)
    if rng.random() < 0.5:
        S.put("skull", rng.uniform(-1.0, 1.0), rng.uniform(1.0, 1.3), loose=True)
    if rng.random() < 0.35:
        S.put("statue_angel", 2.5, -1.6, yaw=-15 + rng.normal(0, 6))


def sc_barrow(S, rng):
    """선돌이 둘러선 무덤 둔덕 (둔덕은 lay_scene 이 지형에 쌓는다). 입구는 앞(+lz, 길 쪽)"""
    S.floor("moss", 7.5)
    n = 10
    off = rng.uniform(-0.15, 0.15)
    for k in range(n):
        a = math.pi / 2 + (k + 0.5) / n * 2 * math.pi + off          # 입구(앞) 양옆은 비운다 (k = 9, 0 사이가 입구)
        if k in (n - 1, 0):
            continue
        if rng.random() < 0.12:
            continue                                                  # 쓰러져 사라진 돌
        lx, lz = math.cos(a) * 9.6, math.sin(a) * 9.6
        x, z = S.at(lx, lz)
        tl = 18 if rng.random() < 0.15 else None                     # 몇은 기울었다
        S.put("standing_stone", lx, lz, ayaw=yaw_to(S.x - x, S.z - z) + rng.normal(0, 8), s=rng.uniform(0.85, 1.1),
              tilt=tl, req=True, stamp=("dirt", 1.0))
    for sd in (-1, 1):                                                # 입구 돌: 키 큰 두 개가 길 쪽 입구를 지킨다
        S.put("standing_stone", sd * 1.9, 9.9, yaw=rng.normal(0, 5), s=rng.uniform(1.25, 1.32), req=True, tag="entrance_stone",
              stamp=("dirt", 1.0), ground_margin=0.15)
    S.put("grave_sunken", 0, 6.9, yaw=rng.normal(0, 5), stamp=("mud", 1.3), tag="entrance_pit")   # 둔덕 발치의 어두운 입구
    for k in range(3):
        S.put("candles", rng.uniform(-1.4, 1.4), rng.uniform(7.9, 8.8), loose=True)
    for k in range(4):
        S.put("skull", *polar(rng, 3.0, 8.5), loose=True)
    S.put("bones_scatter", rng.uniform(-2, 2), rng.uniform(7.5, 8.5), loose=True)
    S.fx("soulfire", 3, up=0.6)
    S.light(SOUL, 5.0, 10.0, up=2.6, far=FAR)


def sc_camp(S, rng):
    S.floor("dirt", 4.8)
    S.put("campfire", 0, 0, must=True, stamp=("ash", 1.3))
    for sd in (-1, 1):                                       # 통나무 의자 (모닥불을 보고)
        S.put("log_fallen", sd * 2.6, 0.6, yaw=sd * 80 + rng.normal(0, 6), s=0.75, tag="log_bench")
    S.put("tent_torn", -3.9, -3.2, yaw=25 + rng.normal(0, 8))
    if rng.random() < 0.5:
        S.put("tent_torn", 3.7, -3.6, yaw=-30 + rng.normal(0, 8))
    S.put("cart_broken", 6.0, 4.0, yaw=rng.uniform(60, 120))
    S.put("stump", -5.4, 3.4)
    S.put("banner_torn", -0.8, -5.8, yaw=rng.normal(0, 20), s=rng.uniform(1.2, 1.3), req=True)   # 야영지 깃발 (멀리서 실루엣)
    for k in range(3):
        a_ = rng.uniform(0, 2 * math.pi)
        S.put("rock_c", math.cos(a_) * 1.1, math.sin(a_) * 1.1, loose=True, s=rng.uniform(0.6, 0.8))
    S.put("skull", *polar(rng, 2.0, 4.0), loose=True)
    S.put("bones_scatter", *polar(rng, 3.0, 6.0), loose=True)
    S.put("skeleton_remains", *polar(rng, 3.0, 5.0), loose=True)      # 불가에서 잠든 채로
    S.fx("fireflies", 7, up=1.2)


def sc_crystal(S, rng):
    S.floor("moss", 4.2)
    S.put("soul_crystal", 0, 0, s=1.3, yaw=rng.uniform(0, 360), must=True, stamp=("rock", 1.4))
    # w4: 바위 기둥은 진짜 선돌로 (cliff_b 를 줄인 기둥은 벽돌 굴뚝처럼 읽혔다). 세로 실루엣 3.6~4.1 m
    S.put("standing_stone", rng.uniform(-0.6, 0.6), -3.4, yaw=rng.normal(0, 25), s=rng.uniform(1.22, 1.38), req=True, tag="rock_spire",
          stamp=("rock", 1.2), tilt=9, ground_margin=0.2)
    for k in range(int(rng.integers(1, 3))):
        n0, b0 = len(S.P.objects), S.beacon
        if S.put("soul_crystal", *polar(rng, 2.4, 3.8), s=rng.uniform(0.7, 0.85), tag="soul_crystal_small") and len(S.P.objects) > n0 \
                and S.P.objects[-1]["a"] == "soul_crystal":
            S.P.objects[-1]["far"] = SMALL_GLOW_FAR          # 곁의 작은 수정은 가까이서만 (등대 빛은 가운데 큰 수정 하나)
            S.beacon = b0
    S.put("rock_b", *polar(rng, 3.5, 5.5))
    S.put("rock_flat", *polar(rng, 3.5, 5.5))
    for k in range(2):
        S.put("rock_a", *polar(rng, 3.0, 6.0))
    for k in range(4):
        S.put("mushroom_glow", *polar(rng, 1.5, 5.0), loose=True)
    S.fx("wisps", 8, up=1.0)


def sc_family(S, rng):
    S.floor("dirt", 5.2)
    S.put("mausoleum_small", 0, -3.6, yaw=rng.normal(0, 3), must=True, stamp=("dirt", 1.2))
    S.put("obelisk_chained", -3.6, -6.4, yaw=rng.uniform(0, 360), req=True, stamp=("dirt", 1.0))   # 가문 비석 (세로 실루엣)
    gn = ["grave_slab_a", "grave_slab_b", "grave_cross", "grave_slab_c"]
    for k, (lx, lz) in enumerate(((-2.6, 1.0), (-0.9, 1.0), (0.9, 1.0), (2.6, 1.0), (-1.8, 3.2), (0.0, 3.2), (1.8, 3.2))):
        if rng.random() < 0.8:
            S.put(gn[k % 4], lx + rng.normal(0, 0.15), lz + rng.normal(0, 0.15), yaw=rng.normal(0, 6), loose=True, stamp=("dirt", 1.4),
                  tag="grave")
    for sd in (-1, 1):
        S.put("iron_fence", sd * 3.1, 5.6, yaw=rng.normal(0, 3), loose=True, tilt=4)
        S.put("iron_fence", sd * 5.2, 2.2, yaw=90 + rng.normal(0, 3), loose=True, tilt=4)
        if rng.random() < 0.6:
            S.put("iron_fence", sd * 5.2, -1.4, yaw=90 + rng.normal(0, 3), loose=True, tilt=6)
    for sd in (-1, 1):
        S.put("candles", sd * 0.7, 4.4, loose=True)
    S.put("lantern", 1.2, 7.6, yaw=rng.normal(0, 10), req=True)     # v2: (1.5, 6.8) 은 앞 울타리와 겹쳐 한 번도 놓이지 않았다


def sc_battle(S, rng):
    S.floor("dirt", 7.0)
    for k in range(4):
        S.put("banner_torn", *polar(rng, 2.0, 10.0), s=rng.uniform(1.15, 1.3) if k < 2 else None, req=True)
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
    for k in range(2):                       # 전장을 떠도는 영혼 빛 (하나는 등대 빛)
        lx, lz = polar(rng, 1.0, 7.0)
        S.light(SPIRIT, 3.5 if k else 4.5, 8.0, lx, lz, up=rng.uniform(1.8, 2.6), far=FAR if k == 0 else None)
    S.fx("wisps", 12, up=1.0)


def sc_outpost(S, rng):
    """길목 초소: 길 쪽(+lz)에 낮은 돌담 ㄱ 자, 화로, 깃발, 무너진 모서리, 쓰러진 보초"""
    S.floor("dirt", 5.0)
    S.put("stone_wall_low", -1.5, 3.2, yaw=rng.normal(0, 3), req=True, tag="stone_wall_low")
    S.put("stone_wall_low", 2.6, 3.0, yaw=rng.normal(0, 4), tag="stone_wall_low")
    S.put("stone_wall_low", -4.2, 0.6, yaw=90 + rng.normal(0, 4), tag="stone_wall_low")
    S.put("brazier", 1.4, -0.6, yaw=0, must=True)
    S.put("banner_torn", -3.0, -2.6, yaw=rng.normal(0, 15), s=rng.uniform(1.2, 1.3), req=True)
    S.put("wall_ruin_b", 3.6, -3.2, yaw=rng.uniform(-60, 60), tag="post_corner")
    for k in range(2):
        S.put("skeleton_remains", *polar(rng, 1.5, 5.0), loose=True)
    for k in range(3):
        S.put("skull", *polar(rng, 1.0, 5.5), loose=True)
    S.put("rubble", *polar(rng, 3.0, 6.5))
    S.put("bones_scatter", *polar(rng, 2.0, 6.0), loose=True)


def sc_graves(S, rng):
    """외딴 무덤 무리: 길가 고목 아래 묘비 몇, 부서진 쇠 울타리, 무덤 위 영혼 불"""
    S.floor("dirt", 4.5)
    S.put("dead_tree_a" if rng.random() < 0.6 else "dead_tree_c", rng.uniform(-1, 1), -3.4, s=rng.uniform(1.05, 1.25), req=True,
          tag="old_tree")
    gn = ["grave_slab_a", "grave_slab_b", "grave_cross", "grave_slab_c", "grave_sunken"]
    for (lx, lz) in ((-2.4, 0.2), (-0.8, 0.6), (0.9, 0.3), (2.5, 0.0), (-1.6, 2.4), (0.2, 2.6), (1.9, 2.3)):
        if rng.random() < 0.75:
            S.put(gn[int(rng.integers(0, 5))], lx + rng.normal(0, 0.2), lz + rng.normal(0, 0.2), yaw=rng.normal(0, 8), loose=True,
                  stamp=("dirt", 1.4), tag="grave")
    S.put("iron_fence", -4.6, 1.0, yaw=90 + rng.normal(0, 6), tilt=10)
    S.put("iron_fence", 3.6, 4.8, yaw=rng.normal(0, 6), tilt=12)
    for k in range(3):
        S.put("candles", rng.uniform(-1.8, 1.8), rng.uniform(3.6, 4.3), loose=True)
    for k in range(2):
        S.put("skull", *polar(rng, 1.0, 4.5), loose=True)
    for k in range(3):
        S.put("flower_lily", *polar(rng, 1.5, 5.0), loose=True)
    S.light(SOUL, 3.5, 7.0, 0, 1.2, up=1.6, far=FAR)              # 무덤 위 영혼 불 (등대 빛)
    S.fx("wisps", 5, 0, 1.0, up=0.8)


def sc_farmstead(S, rng):
    """버려진 농가: 낮은 돌담으로 두른 마당 (앞이 열린 문), 무너진 집 모서리, 우물, 마당 고목, 수레, 꺼져 가는 불"""
    S.floor("dirt", 6.5)
    S.floor("path", 2.0, 0, 5.5)
    first = True
    for (lx, lz, yw) in ((-4.4, 6.2, 0), (4.4, 6.2, 0), (-6.6, 2.0, 90), (-6.6, -2.4, 90), (6.6, 2.0, 90), (6.6, -2.4, 90),
                         (-2.2, -6.4, 0), (2.2, -6.4, 0)):
        if first or rng.random() < 0.85:
            S.put("stone_wall_low", lx, lz, yaw=yw + rng.normal(0, 4), tag="stone_wall_low", req=first)
            first = False
    S.put("wall_ruin_a", -2.2, -1.6, yaw=rng.normal(0, 5), req=True, tag="house_wall", stamp=("dirt", 1.2))
    S.put("well", 2.8, -2.2, yaw=rng.uniform(0, 360), tag="well")
    S.put("dead_tree_b", 2.8, 2.6, s=rng.uniform(1.0, 1.15), req=True, tag="yard_tree")
    S.put("cart_broken", -9.4, 5.6, yaw=rng.uniform(0, 180))
    S.put("campfire", -0.8, 2.6, req=True, stamp=("ash", 1.2))      # 누군가 아직 불을 피운다 (등대 빛)
    for k in range(2):
        S.put("rubble", *polar(rng, 2.0, 5.5))
    for k in range(3):                                   # 마당 안 우물·담에 박히지 않게 겹침 검사를 한다
        S.put("skull", *polar(rng, 1.0, 5.5))
    S.put("bones_scatter", *polar(rng, 2.0, 5.0))


def sc_pyre(S, rng):
    """화장터: 엇갈려 쌓은 통나무 장작더미, 재 바닥, 뼈·해골, 잉걸불, 깃발 둘, 장작더미 둘레의 돌"""
    S.floor("ash", 5.0)
    b = rng.uniform(0, 180)
    if S.put("log_fallen", 0, 0, ayaw=S.fy + b, s=0.8, req=True, tag="pyre_log", stamp=("ash", 1.5), align=0.3, vary=False):
        g = S.P.objects[-1]["p"][1]
        for k, (up, s_) in enumerate(((0.5, 0.72), (0.95, 0.62))):       # 엇갈려 쌓은 장작
            S.put("log_fallen", rng.normal(0, 0.15), rng.normal(0, 0.15), ayaw=S.fy + b + 90 * (k + 1) + rng.normal(0, 8), s=s_,
                  y=g + up, tilt=3, align=False, loose=True, tag="pyre_log_top", vary=False)
    for sd in (-1, 1):
        S.put("banner_torn", sd * 4.4, -2.6, yaw=rng.normal(0, 15), s=rng.uniform(1.2, 1.3), req=True)
    for k in range(8):
        a_ = k / 8 * 2 * math.pi + rng.uniform(-0.2, 0.2)
        S.put("rock_c", math.cos(a_) * 2.8, math.sin(a_) * 2.8, s=rng.uniform(0.8, 1.2), tag="pyre_ring")
    for k in range(2):
        S.put("skeleton_remains", *polar(rng, 3.6, 6.0), loose=True)      # 장작더미를 기다리는 망자
    for k in range(6):
        S.put("skull", *polar(rng, 0.8, 5.0), loose=True)
    S.put("bones_scatter", *polar(rng, 1.5, 4.5), loose=True)
    S.put("bone_pile", *polar(rng, 4.0, 6.5))
    S.light(EMBER, 4.0, 7.0, up=1.3, far=FAR)                       # 잉걸불 (등대 빛)
    S.fx("soulfire", 2.0, up=0.6)


# ───── 산기슭 장면 (v3 검토 반영: 산기슭 가장자리 70 m 띠가 장면·채움 모두에서 빠져 비었다) ─────
FOOT_SCENES = {   # 틀: (차지하는 반지름 m, 발치 안쪽 거리 범위 dd (m, 음수 = 걸을 수 있는 쪽), 수)
    "cave_tomb":    (8.5, (-13.0, -7.0), 9),     # 벼랑 밑 무덤 굴 입구: 벽에 기댄 아치·양옆 절벽 바위·어두운 구덩이·관·초·등불
    "cliff_shrine": (7.0, (-11.0, -5.5), 9),     # 벼랑에 기댄 사당: 사당·석상·벽에 박힌 담·초·꽃·등불
    "rockfall":     (9.0, (-24.0, -9.0), 11),    # 낙석 더미: 무너진 절벽 덩이·바위 기둥·깔린 수레와 유해·등불 (골 어귀 너덜 위)
    "cairns":       (8.0, (-62.0, -24.0), 10),   # 돌무더기 탑: 쌓은 돌탑 몇·선돌·해골·꽃·등불
}
FOOT_SCENE_GAP = 90.0          # 산기슭 장면 사이 최소 (m)


def sc_cave_tomb(S, rng):
    """벼랑 밑 무덤 굴 입구. 뒤(−lz)가 벽"""
    S.floor("dirt", 5.0)
    S.floor("rock", 4.0, 0, -3.0)
    S.put("arch_ruin", 0, -3.2, yaw=rng.normal(0, 3), must=True, stamp=("rock", 1.2), ground_margin=0.25)
    for sd in (-1, 1):                                          # 입구를 감싼 벼랑 바위 (반쯤 묻힘)
        sc_ = rng.uniform(0.5, 0.68)
        h_ = 8.6 * sc_
        S.put("cliff_a" if rng.random() < 0.6 else "cliff_c", sd * rng.uniform(5.0, 6.2), -4.4, yaw=sd * rng.uniform(55, 80), s=sc_,
              req=True, tag="tomb_rock", slope=None, ground="box", ground_margin=h_ * 0.4, align=0.3, align_max=15, loose=True)
    S.put("grave_sunken", 0, -1.0, yaw=rng.normal(0, 4), stamp=("mud", 1.4), req=True, tag="tomb_pit")      # 굴로 내려가는 어두운 입구
    for sd in (-1, 1):
        if rng.random() < 0.75:
            S.put("pillar_a", sd * 2.7, -1.6, yaw=rng.uniform(0, 360), s=rng.uniform(0.7, 1.0))
    for k in range(int(rng.integers(1, 3))):
        S.put("coffin", rng.choice([-1, 1]) * rng.uniform(2.0, 3.4), rng.uniform(0.8, 2.6), yaw=rng.uniform(-40, 40))
    for k in range(3):
        S.put("candles", rng.uniform(-1.2, 1.2), rng.uniform(0.2, 0.8), loose=True)
    for k in range(int(rng.integers(2, 5))):
        S.put("skull", *polar(rng, 1.0, 4.5), loose=True)
    S.put("bones_scatter", *polar(rng, 1.5, 4.0), loose=True)
    S.put("lantern", rng.choice([-1, 1]) * rng.uniform(2.6, 3.6), rng.uniform(2.0, 3.2), yaw=rng.uniform(0, 360), req=True, tag="lamp")
    S.fx("soulfire", 2.0, 0, -2.4, up=0.8)


def sc_cliff_shrine(S, rng):
    """벼랑에 기댄 사당. 뒤(−lz)가 벽"""
    S.floor("path", 3.2)
    S.put("wall_ruin_a", 0, -3.4, yaw=rng.normal(0, 4), tag="back_wall", loose=True, slope=0.45)   # 사당 뒤 담 (벼랑 앞)
    S.put("shrine_roadside", 0, -1.4, yaw=rng.normal(0, 4), must=True, stamp=("path", 1.3))
    S.put("statue_reaper" if rng.random() < 0.5 else "statue_angel", rng.choice([-1, 1]) * rng.uniform(2.0, 2.8), -2.2,
          yaw=rng.normal(0, 10), req=True, tag="statue")
    if rng.random() < 0.6:
        S.put("cliff_c", rng.choice([-1, 1]) * rng.uniform(4.5, 6.0), -5.5, yaw=rng.uniform(0, 360), s=rng.uniform(0.4, 0.55), slope=None,
              ground="box", ground_margin=2.2, align=0.3, align_max=15, loose=True, tag="side_rock")
    for k in range(4):
        S.put("candles", rng.uniform(-1.4, 1.4), rng.uniform(-0.4, 0.6), loose=True)
    for k in range(4):
        S.put("flower_lily", *polar(rng, 1.4, 3.8), loose=True)
    for k in range(int(rng.integers(1, 3))):
        S.put("skull", rng.uniform(-1.2, 1.2), rng.uniform(-0.6, 0.2), loose=True)
    S.put("lantern", rng.choice([-1, 1]) * rng.uniform(1.8, 2.8), rng.uniform(0.8, 2.0), yaw=rng.uniform(0, 360), req=True, tag="lamp")
    S.put("standing_stone", rng.choice([-1, 1]) * rng.uniform(3.2, 4.2), rng.uniform(-3.4, -2.2), yaw=rng.uniform(0, 360), s=rng.uniform(1.2, 1.32),
          tag="waystone", stamp=("dirt", 1.0), ground_margin=0.15)     # w4: 사당 곁 선돌 (세로 실루엣 3.6 m 넘게. 대체 사당은 2.2 m)
    S.fx("wisps", 5, 0, -1.0, up=1.0)


def sc_rockfall(S, rng):
    """낙석 더미: 벽에서 무너져 내린 큰 덩이 (골 어귀). 뒤(−lz)가 벽"""
    S.floor("rock", 6.0)
    sc_ = rng.uniform(0.42, 0.58)
    S.put("cliff_c" if rng.random() < 0.6 else "cliff_a", 0, -1.0, yaw=rng.uniform(0, 360), s=sc_, must=True, slope=None, ground="box",
          ground_margin=5.5 * sc_ * 0.3, align=0.5, align_max=20, tilt=18, stamp=("rock", 1.3))
    S.put("cliff_b", rng.uniform(-3.0, 3.0), -4.2, yaw=rng.uniform(0, 360), s=rng.uniform(0.44, 0.52), req=True, tag="spire", slope=None,
          ground="box", ground_margin=0.6, tilt=14, loose=True)                                     # 기운 바위 기둥 (세로 실루엣)
    for k in range(int(rng.integers(3, 6))):
        n_ = "rock_b" if rng.random() < 0.6 else "rock_flat"
        s3 = rng.uniform(0.55, 1.05)
        S.put(n_, *polar(rng, 3.0, 8.0), s=s3, slope=None, ground="box", align_max=30, ground_margin=0.35 * s3)
    for k in range(int(rng.integers(3, 6))):
        S.put("rubble" if rng.random() < 0.6 else "rock_c", *polar(rng, 2.0, 8.0))
    S.put("cart_broken", rng.uniform(-3.0, 3.0), rng.uniform(2.0, 4.0), yaw=rng.uniform(0, 360), tag="crushed_cart", loose=True, slope=0.5)   # 깔린 수레
    S.put("skeleton_remains", rng.uniform(-2.0, 2.0), rng.uniform(1.5, 3.5), yaw=rng.uniform(0, 360), loose=True)
    for k in range(2):
        S.put("skull", *polar(rng, 1.5, 6.0), loose=True)
    if rng.random() < 0.6:
        S.put("dead_tree_c", rng.choice([-1, 1]) * rng.uniform(5.0, 7.0), rng.uniform(0.0, 4.0), s=rng.uniform(0.9, 1.15))
    S.put("lantern", rng.uniform(-4.0, 4.0), rng.uniform(4.5, 6.0), yaw=rng.uniform(0, 360), tilt=12, req=True, tag="lamp")   # 누군가 두고 간 등불


def sc_cairns(S, rng):
    """돌무더기 탑: 납작한 돌 위에 돌을 쌓은 탑 몇 (길 잃은 망자를 위한 표지)"""
    S.floor("moss", 5.5)
    n = int(rng.integers(3, 6))
    a0 = rng.uniform(0, 2 * math.pi)
    for k in range(n):
        a = a0 + k / n * 2 * math.pi + rng.uniform(-0.3, 0.3)
        d = rng.uniform(1.5, 5.5) if k else 0.0
        cairn(S, rng, math.cos(a) * d, math.sin(a) * d, big=(k == 0))
    S.put("standing_stone", rng.uniform(-3.0, 3.0), -rng.uniform(4.5, 6.0), yaw=rng.uniform(0, 360), s=rng.uniform(1.2, 1.32), req=True,
          tag="waystone", stamp=("dirt", 1.0), ground_margin=0.18)            # w4: 진짜 선돌 3.17 m × 1.2~1.32 (세로 실루엣 3.6 m 넘게)
    for k in range(3):
        S.put("flower_lily", *polar(rng, 1.0, 6.0), loose=True)
    for k in range(int(rng.integers(1, 4))):
        S.put("skull", *polar(rng, 0.8, 5.0), loose=True)
    S.put("candles", rng.uniform(-0.8, 0.8), rng.uniform(0.9, 1.4), loose=True)
    S.put("lantern", rng.uniform(-3.0, 3.0), rng.uniform(3.0, 5.0), yaw=rng.uniform(0, 360), req=True, tag="lamp")


def cairn(S, rng, lx, lz, big=False):
    """돌탑 하나: 납작한 돌(rock_flat) 위에 바위(rock_b)·납작한 돌을 차례로 얹는다 (높이 1.6~2.8 m)"""
    P = S.P
    n0 = len(P.objects)
    s0 = rng.uniform(0.62, 0.78) if big else rng.uniform(0.45, 0.62)
    if not S.put("rock_flat", lx, lz, yaw=rng.uniform(0, 360), s=s0, slope=0.4, ground="box", align_max=8, tilt=2, tag="cairn", vary=False) \
            or len(P.objects) == n0:
        return
    b = P.objects[-1]
    x, y, z = b["p"]
    y += 0.80 * s0 * 0.82
    lay = [("rock_b", 0.62, 1.87), ("rock_flat", 0.62, 0.8), ("rock_b", 0.42, 1.87)] + ([("rock_flat", 0.4, 0.8)] if big else [])
    for nm, k, hz in lay:
        sk = s0 * k * rng.uniform(0.9, 1.1)
        ox, oz = rng.normal(0, 0.08), rng.normal(0, 0.08)
        ok = P.put(nm, x + ox, z + oz, yaw=rng.uniform(0, 360), s=sk, y=y - 0.12 * hz * sk, check=False, tilt=4, occupy=False)
        if not ok:
            break
        S.n += 1
        top = y + hz * sk * 0.75
        S._top(x, top, z, top - P.height(x, z))
        y = top
    if big:
        P.put("skull", x, z, y=y - 0.02, check=False, occupy=False)


def foot_scene_ok(W, P, x, z, R):
    """산기슭 장면 자리: 가운데는 고르고, 둘레 8 점 중 벽 쪽(발치 dd > −4 m)은 가팔라도 되고 나머지는 걸을 수 있는 땅"""
    (bx0, bz0), (bx1, bz1) = BOUNDS
    if not (bx0 - 10 < x < bx1 + 10 and bz0 - 10 < z < bz1 + 10):
        return False
    if not P.ok_ground(x, z, R * 0.6, road=True, water=True, slope=0.35):
        return False
    if sample(W.road_dist, x, z) < sample(W.road_hw, x, z) + R + 4:
        return False
    if not P.free(x, z, R * 0.75):
        return False
    for k in range(8):
        a = k / 8 * 2 * math.pi
        px, pz = x + math.cos(a) * R, z + math.sin(a) * R
        if P.under_water(px, pz, 0.2):
            return False
        if sample(W.dd, px, pz) < -4.0 and sample(W.slope, px, pz) > 0.55:
            return False
    return True


def lay_foot_scenes(W, P):
    """산기슭 장면: 벽 발치 안쪽 띠(FOOT_SCENES 의 dd 범위)에 벼랑 밑 무덤 굴·벼랑 사당·낙석 더미·돌무더기 탑.
    앞(+lz)은 벽에서 안쪽(걸을 수 있는 쪽)을 본다. 장소·문 둘레와 숲 안은 뺀다"""
    rng = P.rng
    t0 = time.time()
    pois = [((p if p else W.bridge_p), r) for (_, _, p, r) in POIS if r < 150]
    gate_d = np.hypot(W.X - GATE[0], W.Z - GATE[1])
    got = collections.Counter()
    placed = [tuple(s_["p"]) for s_ in W.scenes]
    order = []
    for kind, (R, (d0, d1), n) in FOOT_SCENES.items():
        order += [kind] * n
    rng.shuffle(order)
    picks = {}
    for kind, (R, (d0, d1), n) in FOOT_SCENES.items():
        m = (W.dd > d0) & (W.dd < d1) & (gate_d > 140) & (W.slope < 0.3) & (W.forest_plan < 0.25)
        w = m.astype(np.float32)
        if kind == "rockfall":
            w *= 0.25 + ss(0.42 - W.spur, 0.0, 0.2)           # 골 어귀(너덜 부채꼴) 쪽
        picks[kind] = in_mask(W, w)
    for kind in order:
        R, (d0, d1), n = FOOT_SCENES[kind]
        for _ in range(160):
            p = picks[kind](rng)
            if p is None:
                break
            x, z = p
            if any((x - a) ** 2 + (z - b) ** 2 < FOOT_SCENE_GAP ** 2 for a, b in placed):
                continue
            if any((x - c[0]) ** 2 + (z - c[1]) ** 2 < (r + R + 20) ** 2 for c, r in pois):
                continue
            (ix, iz), _, yin = foot_frame(W, x, z)
            rec = lay_scene(W, P, kind, x, z, yaw=yin, feature="mountain_foot", ok_fn=foot_scene_ok)
            if rec:
                placed.append((x, z))
                got[kind] += 1
                break
    log("산기슭 장면 %d 곳 %s, %.1f 초" % (sum(got.values()), dict(got), time.time() - t0))


SCENE_FN = {"execution": sc_execution, "chapel": sc_chapel, "shrine": sc_shrine, "barrow": sc_barrow, "camp": sc_camp,
            "crystal": sc_crystal, "family": sc_family, "battle": sc_battle, "outpost": sc_outpost, "graves": sc_graves,
            "farmstead": sc_farmstead, "pyre": sc_pyre,
            "cave_tomb": sc_cave_tomb, "cliff_shrine": sc_cliff_shrine, "rockfall": sc_rockfall, "cairns": sc_cairns}


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


def type_allowed(W, kind, x, z):
    """같은 틀 장면이 SAME_TYPE_GAP 안에 없는가"""
    return all((x - s_["p"][0]) ** 2 + (z - s_["p"][1]) ** 2 >= SAME_TYPE_GAP ** 2 for s_ in W.scenes if s_["type"] == kind)


def face_road(W, x, z):
    """가장 가까운 길 쪽을 보는 yaw 와 길까지 거리"""
    best, bp = 1e18, None
    for c, hw in W.road_curves:
        d2 = (c[:, 0] - x) ** 2 + (c[:, 1] - z) ** 2
        k = int(np.argmin(d2))
        if d2[k] < best:
            best, bp = float(d2[k]), c[k]
    return yaw_to(bp[0] - x, bp[1] - z), math.sqrt(best)


def lay_scene(W, P, kind, x, z, yaw=None, feature=None, hamlet=-1, ok_fn=None):
    """장면 하나. 자리 검사 → 가운데 자리 고르기(지형) → 틀 → 등대 빛·세로 요소 보충 → 둘레. 성공하면 W.scenes 항목.
    ok_fn: 자리 검사를 바꾼다 (산기슭 장면: 벽 쪽 둘레는 가파라도 된다)"""
    R = SCENES[kind][0] if kind in SCENES else FOOT_SCENES[kind][0]
    if not (ok_fn or scene_ok)(W, P, x, z, R) or not type_allowed(W, kind, x, z):
        return None
    rng = P.rng
    fy, droad = face_road(W, x, z)
    if yaw is not None:
        fy = yaw
    fy += rng.normal(0, 10)
    # v3: 장면 가운데를 부드럽게 고른다 (큰 소품이 비탈 오르막 쪽에 묻히지 않게. 길·물·개울은 건드리지 않는다)
    for amt in (0.8, 0.55, 0.3):                 # 걸을 수 있는 기울기를 넘으면 더 약하게
        if P.terraform(x, z, R * 0.55, R + 6.0, "flat", amt):
            break
    if kind == "barrow":
        P.terraform(x, z, 0.0, 8.0, "mound", rng.uniform(1.6, 2.0), max_slope=0.62)
    S = Scene(W, P, kind, x, z, fy)
    SCENE_FN[kind](S, rng)
    if S.top[3] < TALL:                     # 키 큰 세로 요소가 없으면 (대체 소품이 낮거나 빠졌을 때) 깃발 하나
        for (lx, lz) in ((0.0, -R * 0.7), (R * 0.6, -R * 0.4), (-R * 0.6, -R * 0.4)):
            if S.put("banner_torn", lx, lz, s=1.3, tag="tall_fallback") and S.top[3] >= TALL:
                break
    if S.beacon is None:                    # 멀리서 보이는 등대 빛이 없으면 떠도는 영혼 빛 하나 (far)
        S.light(SPIRIT if rng.random() < 0.5 else SOUL, 4.0, 8.0, up=2.4, far=FAR)
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
    S.finish()
    rec = {"type": kind, "p": [round(x, 1), round(z, 1)], "r": R, "yaw": round(fy % 360, 1), "props": S.n,
           "feature": feature or "", "road_d": round(droad, 1), "hamlet": hamlet,
           "top": [round(S.top[0], 2), round(S.top[1], 2), round(S.top[2], 2)], "tall": round(S.top[3], 2),
           "beacon": [round(v, 2) for v in S.beacon] if S.beacon else None}
    W.scenes.append(rec)
    return rec


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
                if not type_allowed(W, "crossroad", jx, jz):
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
                S = Scene(W, P, "crossroad", jx, jz, 0.0)
                used = []
                for nm in ("brazier", "brazier", "pillar_a"):
                    for (a, x, z) in spots:
                        if any(abs((a - b + math.pi) % (2 * math.pi) - math.pi) < 1.3 for b in used):
                            continue
                        lx, lz = x - jx, z - jz                   # Scene 로컬 = 월드 (fy 0)
                        if S.put(nm, lx, lz, ayaw=yaw_to(jx - x, jz - z), road=False, slope=0.45, tag=nm,
                                 req=(nm == "pillar_a")):
                            used.append(a)
                            if nm == "pillar_a":                    # 이정표 기둥 발치
                                for q in range(3):
                                    P.put("skull", x + rng.normal(0, 0.8), z + rng.normal(0, 0.8), road=False)
                                P.put("candles", x + rng.uniform(-0.8, 0.8), z + rng.uniform(-0.8, 0.8), road=False)
                            break
                if not used:
                    continue
                if S.beacon is None:
                    S.light(SPIRIT, 4.0, 8.0, up=2.6, far=FAR)
                P.reserve(jx, jz, 8.0)
                S.finish()
                W.scenes.append({"type": "crossroad", "p": [round(jx, 1), round(jz, 1)], "r": 8.0, "yaw": 0.0, "props": len(used),
                                 "feature": "junction", "road_d": 0.0, "hamlet": -1,
                                 "top": [round(S.top[0], 2), round(S.top[1], 2), round(S.top[2], 2)], "tall": round(S.top[3], 2),
                                 "beacon": [round(v, 2) for v in S.beacon] if S.beacon else None})
                got += 1
    log("갈림길 화로", got)


# ───── 시선 (지형만 본다) ─────
def hs_arr(h, x, z):
    """높이 쌍선형 보간 (배열)"""
    x = np.clip(x, 0, RES - 1.001)
    z = np.clip(z, 0, RES - 1.001)
    x0 = x.astype(np.int32)
    z0 = z.astype(np.int32)
    fx, fz = x - x0, z - z0
    return (h[z0, x0] * (1 - fx) * (1 - fz) + h[z0, x0 + 1] * fx * (1 - fz) + h[z0 + 1, x0] * (1 - fx) * fz + h[z0 + 1, x0 + 1] * fx * fz)


def los_ok(h, ox, oz, oy, tx, tz, ty, clear=0.15):
    """관측점 배열 (ox, oz, 눈 높이 oy) 에서 표적 한 점 (tx, tz, ty) 이 지형에 가리지 않는가"""
    if len(ox) == 0:
        return np.zeros(0, bool)
    d = np.hypot(tx - ox, tz - oz)
    n = int(max(8, d.max() / 2.0))
    t = np.linspace(0.02, 0.97, n)[None, :]
    sx = ox[:, None] + (tx - ox)[:, None] * t
    sz = oz[:, None] + (tz - oz)[:, None] * t
    line = oy[:, None] + (ty - oy)[:, None] * t
    return (hs_arr(h, sx, sz) < line - clear).all(1)


def sight_samples(W, seed=4242, n_off=3200):
    """시선 표본: 길 중심선 10 m 마다 (RS), 길 밖 걸을 수 있는 땅 무작위 (OS)"""
    rs = []
    for c, hw in W.road_curves:
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        for t in np.arange(0, s[-1], 10.0):
            rs.append((float(np.interp(t, s, c[:, 0])), float(np.interp(t, s, c[:, 1]))))
    rs = np.array(rs)
    rng = np.random.default_rng(seed)
    (bx0, bz0), (bx1, bz1) = BOUNDS
    os_ = []
    tries = 0
    while len(os_) < n_off and tries < n_off * 20:
        tries += 1
        x, z = rng.uniform(bx0 + 2, bx1 - 2), rng.uniform(bz0 + 2, bz1 - 2)
        if sample(W.slope, x, z) > 0.9 or sample(W.road_dist, x, z) < sample(W.road_hw, x, z) + 3:
            continue
        hh = sample(W.h, x, z)
        if (x - SWAMP[0]) ** 2 + (z - SWAMP[1]) ** 2 < (SWAMP_R + 40) ** 2 and hh < W.swamp_level + 0.1:
            continue
        if (x - LAKE[0]) ** 2 + (z - LAKE[1]) ** 2 < (LAKE_R + 30) ** 2 and hh < W.lake_level + 0.1:
            continue
        os_.append((x, z))
    return rs, np.array(os_)


def poi_targets(W):
    """장소마다 표적 점: 가운데(땅 + 5 m)와 반지름 0.6 배 둘레 8 점(땅 + 3 m)"""
    T = []
    for pid, name, p, r in POIS:
        p = p if p else W.bridge_p
        T.append((p[0], p[1], sample(W.h, *p) + 5.0, pid, r))
        for k in range(8):
            a = k / 8 * 2 * math.pi
            x, z = p[0] + math.cos(a) * r * 0.6, p[1] + math.sin(a) * r * 0.6
            T.append((x, z, sample(W.h, x, z) + 3.0, pid, r))
    return T


def vis_set(W, px, pz, peye, tx, tz, ty, rad=SIGHT):
    """표본 배열 중 표적 (tx, tz, ty) 이 rad 안에서 보이는 번호"""
    d = np.hypot(px - tx, pz - tz)
    idx = np.nonzero(d < rad)[0]
    if len(idx) == 0:
        return idx
    return idx[los_ok(W.h, px[idx], pz[idx], peye[idx], tx, tz, ty)]


# ───── 자리 특징 ─────
def site_features(W):
    """지형 특징 지도 (0~1): 언덕 꼭대기, 능선, 개울가, 숲 가장자리, 움푹한 곳"""
    h = W.h
    F = {}
    calm = 1 - ss(box_blur(W.mount, 40), 0.02, 0.08)            # 산기슭 둘레는 빼고 (흐림이 산 높이를 끌어와 모든 발치가 '움푹한 곳'이 된다)
    F["hilltop"] = ss(h - box_blur(h, 40), 1.5, 5.0) * calm
    rid = ss(h - box_blur(h, 12), 0.45, 1.5)
    F["ridge"] = rid * (1 - 0.5 * F["hilltop"]) * calm
    hc = np.minimum(h, box_blur(h, 20) + 1.5)                    # 둔덕 꼭대기를 깎은 높이로 둘레를 잰다
    F["hollow"] = ss(-(h - box_blur(hc, 45)), 2.5, 5.0) * calm
    cr = np.zeros(h.shape, np.float32)
    (z0, z1), (x0, x1) = W.creek_win
    dd = W.creek_dist - W.creek_wt
    cr[z0:z1, x0:x1] = ss(dd, 5.0, 9.0) * (1 - ss(dd, 26.0, 40.0))
    F["creek"] = cr
    fp = W.forest_plan
    F["forest_edge"] = ss(fp, 0.04, 0.18) * (1 - ss(fp, 0.35, 0.55))
    return F


def road_features(W, F):
    """길 표본 10 m 마다의 특징 점수 (갈림길·굽은 곳·마루·다리/개울·숲 길목). [(x, z, 길 번호, 법선, 특징, 점수)]"""
    curves = W.road_curves
    ends = []
    for i, (c, hw) in enumerate(curves):
        for e in (c[0], c[-1]):
            for j, (c2, _) in enumerate(curves):
                if j != i and np.min((c2[:, 0] - e[0]) ** 2 + (c2[:, 1] - e[1]) ** 2) < 100:
                    ends.append(e)
    ends = np.array(ends) if ends else np.zeros((0, 2))
    cdf = np.full(W.h.shape, 1e9, np.float32)
    (z0, z1), (x0, x1) = W.creek_win
    cdf[z0:z1, x0:x1] = W.creek_dist
    out = []
    for i, (c, hw) in enumerate(curves):
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        L = s[-1]
        P_ = lambda t: np.array([np.interp(t, s, c[:, 0]), np.interp(t, s, c[:, 1])])
        for t in np.arange(5.0, L - 5.0, 10.0):
            p = P_(t)
            d = P_(min(t + 2, L)) - P_(max(t - 2, 0))
            d /= np.linalg.norm(d) + 1e-9
            nrm = np.array([d[1], -d[0]])
            f = {}
            if len(ends):
                dj = float(np.min(np.hypot(ends[:, 0] - p[0], ends[:, 1] - p[1])))
                f["junction"] = max(0.0, 1 - dj / 45.0)
            if 45 < t < L - 45:
                # 굽은 곳: 앞뒤 30 m 팔 방향의 꺾임 (길의 잔 흔들림 3 m 는 무시된다. 길 표본의 약 10% 가 0.5 넘음)
                a = P_(t - 15) - P_(t - 45)
                b = P_(t + 45) - P_(t + 15)
                ang = math.degrees(math.acos(max(-1, min(1, float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))))))
                f["bend"] = float(ssf(ang, 8, 24))
                cross = a[0] * b[1] - a[1] * b[0]            # 굽은 바깥쪽 = 법선 부호
                bend_out = -1 if cross > 0 else 1
            else:
                bend_out = 0
            # 언덕 마루: 앞뒤 35 m 보다 높은 곳 (길 표본의 약 10%)
            hc = sample(W.h, *p)
            hn = max(sample(W.h, *P_(max(t - 35, 0))), sample(W.h, *P_(min(t + 35, L))))
            f["crest"] = float(ssf(hc - hn, -0.2, 0.8))
            f["bridge"] = 1.0 if sample(cdf, *p) < 40 else 0.0
            fa, fb = sample(W.forest_plan, *P_(max(t - 25, 0))), sample(W.forest_plan, *P_(min(t + 25, L)))
            f["forest_entry"] = float(ssf(abs(fa - fb), 0.15, 0.4))
            k = max(f, key=f.get)
            out.append((float(p[0]), float(p[1]), i, nrm, k, f[k], bend_out))
    return out


def scene_candidates(W, P, F):
    """장면 후보 자리. 길가(길 특징 자리 옆, 또는 길 40 m 안의 지형 특징)와 들판(길 40 m 밖의 지형 특징 자리만)"""
    (bx0, bz0), (bx1, bz1) = BOUNDS
    pois = [(p if p else W.bridge_p, r) for (_, _, p, r) in POIS]
    cdf = np.full(W.h.shape, 1e9, np.float32)
    (z0, z1), (x0, x1) = W.creek_win
    cdf[z0:z1, x0:x1] = W.creek_dist

    def base_ok(x, z):
        if not (bx0 + 24 < x < bx1 - 24 and bz0 + 24 < z < bz1 - 24):
            return False
        if sample(W.slope, x, z) > 0.3 or sample(W.mount, x, z) > 0.25 or sample(cdf, x, z) < 14:
            return False
        if P.under_water(x, z, 0.4):
            return False
        return all((x - px) ** 2 + (z - pz) ** 2 > (pr + 25) ** 2 for (px, pz), pr in pois)

    cands = []          # (x, z, 특징, 점수, 길가)
    RF = road_features(W, F)
    W.road_feat = RF
    for (x, z, i, nrm, feat, sc, bend_out) in RF:
        if sc < 0.3:
            continue
        hw = W.road_curves[i][1]
        for side in (-1, 1):
            for off in (hw + 12.0, hw + 18.0, hw + 25.0, hw + 33.0):
                cx, cz = x + nrm[0] * side * off, z + nrm[1] * side * off
                if sample(W.road_dist, cx, cz) < off - 3 or not base_ok(cx, cz):
                    continue
                w = sc * (1.2 if feat == "bend" and side == bend_out else 1.0)
                cands.append((cx, cz, feat, w, True))
    g = np.arange(bx0 + 28, bx1 - 28, 10.0)
    for gz_ in g:
        for gx_ in g:
            x, z = gx_ + 2.5 * math.sin(gz_ * 0.37), gz_ + 2.5 * math.sin(gx_ * 0.29)
            iz, ix = int(round(z)), int(round(x))
            best, bk = 0.0, None
            for k in TERRAIN_FEATS:
                v = float(F[k][iz, ix])
                if v > best:
                    best, bk = v, k
            rd = float(W.road_dist[iz, ix])
            if best < (0.35 if rd <= ROADSIDE else 0.4) or not base_ok(x, z):
                continue
            cands.append((x, z, bk, best, rd <= ROADSIDE))
    return cands


def lay_vignettes(W, P, seed):
    """작은 장면 v3: 길과 지형 특징을 따라 구조를 만든다 (갈림길 → 무리 → 길 시선 → 들판 시선 → 길가 보충).
    장면은 따로 씨앗을 쓴다 (앞 단계의 개수를 바꿔도 장면 자리가 흔들리지 않게)"""
    main_rng = P.rng
    P.rng = rng = np.random.default_rng(seed + 9001)
    t0 = time.time()
    lay_crossroads(W, P)
    F = site_features(W)
    cands = scene_candidates(W, P, F)
    C = np.array([(c[0], c[1]) for c in cands])
    cfeat = [c[2] for c in cands]
    cscore = np.array([c[3] for c in cands])
    croad = np.array([c[4] for c in cands])
    # 시선 표본과 표적
    RS, OS = sight_samples(W)
    S_ = np.concatenate([RS, OS])
    nR = len(RS)
    seye = hs_arr(W.h, S_[:, 0], S_[:, 1]) + EYE
    cov = np.zeros(len(S_), bool)
    for pid, name, p, r in POIS:                       # 장소 원 안 = 장소가 보인다
        p = p if p else W.bridge_p
        cov |= np.hypot(S_[:, 0] - p[0], S_[:, 1] - p[1]) < r
    for (tx, tz, ty, pid, r) in poi_targets(W):
        cov[vis_set(W, S_[:, 0], S_[:, 1], seye, tx, tz, ty)] = True
    # 후보마다 보이는 표본 (장면 꼭대기 = 땅 + TALL)
    cvis = []
    for k in range(len(C)):
        ty = sample(W.h, C[k, 0], C[k, 1]) + TALL
        cvis.append(vis_set(W, S_[:, 0], S_[:, 1], seye, C[k, 0], C[k, 1], ty))
    alive = np.ones(len(C), bool)
    log("장면 후보 %d 곳 (길가 %d), 시선 표본 길 %d · 들판 %d, 준비 %.1f 초" % (len(C), int(croad.sum()), nR, len(OS), time.time() - t0))

    def mark(x, z, ty=None):
        if ty is None:
            ty = sample(W.h, x, z) + TALL
        cov[vis_set(W, S_[:, 0], S_[:, 1], seye, x, z, ty)] = True

    for s_ in W.scenes:
        mark(s_["p"][0], s_["p"][1], s_["top"][1])

    def near_scene(x, z, r):
        return any((x - s_["p"][0]) ** 2 + (z - s_["p"][1]) ** 2 < r * r for s_ in W.scenes)

    def type_order(x, z, feat, road, avoid=()):
        w = {}
        n_avg = (sum(SCENE_COUNT.get(t, 0) for t in SCENES) + 1) / len(SCENES)
        for t in SCENES:
            if t in avoid or not type_allowed(W, t, x, z):
                continue
            R, wr, wf = SCENES[t]
            v = wr if road else wf
            v *= 1 + SCENE_FEAT[t].get(feat, 0.0)
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
                v *= {"camp": 1.3, "execution": 1.3, "outpost": 1.2}.get(t, 1.0)
            v *= ((1.0 + n_avg) / (1.0 + SCENE_COUNT.get(t, 0))) ** 0.7       # 적게 쓴 틀을 조금 더
            w[t] = v * rng.uniform(0.8, 1.2)
        return sorted(w, key=lambda k: -w[k])

    def try_at(k, hamlet=-1, avoid=()):
        x, z = float(C[k, 0]), float(C[k, 1])
        for t in type_order(x, z, cfeat[k], bool(croad[k]), avoid):
            rec = lay_scene(W, P, t, x, z, feature=cfeat[k], hamlet=hamlet)
            if rec:
                mark(x, z, rec["top"][1])
                alive[np.hypot(C[:, 0] - x, C[:, 1] - z) < 2 * SCENES[t][0] + 6] = False
                return rec
        alive[k] = False
        return None

    def grow(k, hid, size):
        """후보 k 에 첫 장면, 24~78 m 안에서 서로 보이는 후보에 size 곳까지. 둘 넘게 놓이면 멤버 목록"""
        x, z = float(C[k, 0]), float(C[k, 1])
        first = try_at(k, hid)
        if not first:
            return None
        mem = [first]
        near = np.nonzero(alive & (np.hypot(C[:, 0] - x, C[:, 1] - z) > 24) & (np.hypot(C[:, 0] - x, C[:, 1] - z) < 78))[0]
        near = near[np.argsort(-(cscore[near] + 0.4 * croad[near]) * rng.uniform(0.8, 1.0, len(near)))]
        for j in near:
            if len(mem) >= size:
                break
            if not alive[j]:
                continue
            jx, jz = float(C[j, 0]), float(C[j, 1])
            ok = True
            for m in mem:      # 서로 보이는가 (눈높이 → 상대 꼭대기)
                if not los_ok(W.h, np.array([jx]), np.array([jz]), np.array([sample(W.h, jx, jz) + EYE]), m["top"][0], m["top"][2],
                              m["top"][1])[0]:
                    ok = False
                    break
            if not ok:
                continue
            rec = try_at(j, hid, avoid=[m["type"] for m in mem])
            if rec:
                mem.append(rec)
        if len(mem) < 2:
            first["hamlet"] = -1
            return None
        return mem

    # 1) 무리: 장소에서 30~260 m 의 길 특징 자리, 그 장소가 보이는 곳. 장면 2~3 개가 서로 보이게
    ptg = poi_targets(W)
    hamlets = []
    order = np.argsort(-(cscore * rng.uniform(0.85, 1.0, len(C))))
    for k in order:
        if len(hamlets) >= HAMLETS:
            break
        if not alive[k] or not croad[k] or cfeat[k] not in ROAD_FEATS or cscore[k] < 0.4:
            continue
        x, z = float(C[k, 0]), float(C[k, 1])
        if any(math.hypot(x - hx, z - hz) < 240 for hx, hz, _, _ in hamlets):
            continue
        eye_ = sample(W.h, x, z) + EYE
        seen = []
        for (tx, tz, ty, pid, r) in ptg:
            dd = math.hypot(tx - x, tz - z)
            if pid in seen or dd > 280:
                continue
            if los_ok(W.h, np.array([x]), np.array([z]), np.array([eye_]), tx, tz, ty)[0]:
                seen.append(pid)
        dedge = min(math.hypot(x - (p if p else W.bridge_p)[0], z - (p if p else W.bridge_p)[1]) - r for (_, _, p, r) in POIS)
        if not seen or not (30 <= dedge <= 260):
            continue
        mem = grow(k, len(hamlets), 3)
        if not mem:
            continue
        hamlets.append((float(np.mean([m["p"][0] for m in mem])), float(np.mean([m["p"][1] for m in mem])),
                        [W.scenes.index(m) for m in mem], seen))
    # 1b) 길목 짝: 장소가 안 보이는 강한 길 특징 자리 (갈림길·마루·굽은 곳) 양쪽에 장면 둘. 무리와 160 m 넘게 떨어진 곳
    pairs = 0
    for k in order:
        if pairs >= PAIRS:
            break
        if not alive[k] or not croad[k] or cfeat[k] not in ROAD_FEATS or cscore[k] < 0.6:
            continue
        x, z = float(C[k, 0]), float(C[k, 1])
        if any(math.hypot(x - hx, z - hz) < 160 for hx, hz, _, _ in hamlets) or near_scene(x, z, SCENE_GAP):
            continue
        mem = grow(k, len(hamlets), 2)
        if not mem:
            continue
        hamlets.append((float(np.mean([m["p"][0] for m in mem])), float(np.mean([m["p"][1] for m in mem])),
                        [W.scenes.index(m) for m in mem], []))
        pairs += 1
    W.hamlets = hamlets
    n_h = len(W.scenes)

    def greedy(mask_fn, goal_fn, w_road, w_off, label):
        added = 0
        while not goal_fn():
            best, bk = 0.0, -1
            unc = ~cov
            for k in np.nonzero(alive & mask_fn())[0]:
                v = cvis[k]
                gr = int(unc[v[v < nR]].sum())
                go = int(unc[v[v >= nR]].sum())
                g = (w_road * gr + w_off * go) * (0.6 + 0.4 * cscore[k])
                if g > best:
                    best, bk = g, k
            if bk < 0 or best < 1.0:
                break
            x, z = float(C[bk, 0]), float(C[bk, 1])
            if near_scene(x, z, SCENE_GAP):
                alive[bk] = False
                continue
            if try_at(bk):
                added += 1
        log("  %s: 장면 %d 곳 더함, 길 시선 %.1f%%, 들판 시선 %.1f%%" % (label, added, 100 * cov[:nR].mean(), 100 * cov[nR:].mean()))

    # 2) 길 시선: 길가 후보만으로 길 표본을 덮는다
    greedy(lambda: croad, lambda: cov[:nR].mean() >= COVER_ROAD, 1.0, 0.25, "길 시선")
    # 3) 들판 시선: 지형 특징 자리(길가 포함)로 들판 표본을 덮는다
    greedy(lambda: np.ones(len(C), bool), lambda: cov[nR:].mean() >= COVER_OFF, 0.3, 1.0, "들판 시선")

    # 4) 길가 보충: 목표 수까지 길 특징 자리에 (들판 깊은 곳은 조용히 둔다)
    def field_count():
        return sum(1 for s_ in W.scenes if s_["type"] in SCENES)
    def road_count():
        return sum(1 for s_ in W.scenes if s_["type"] in SCENES and s_["road_d"] <= ROADSIDE)
    order = np.argsort(-(cscore * rng.uniform(0.7, 1.0, len(C))))
    n0 = field_count()
    why = collections.Counter()
    for k in order:
        if road_count() >= ROAD_TARGET or field_count() >= SCENE_TARGET:
            break
        if not croad[k]:
            continue
        if not alive[k]:
            why["dead"] += 1
            continue
        if cscore[k] < 0.4:
            why["low"] += 1
            continue
        x, z = float(C[k, 0]), float(C[k, 1])
        if near_scene(x, z, ROAD_GAP):
            why["near"] += 1
            continue
        if not any(type_allowed(W, t, x, z) for t in SCENES):
            why["types"] += 1
        why["ok" if try_at(k) else "fail"] += 1
    log("  길가 보충: 장면 %d 곳 더함 (길가 %d) %s" % (field_count() - n0, road_count(), dict(why)))
    # 5) 들판 보충: 강한 지형 특징 자리에 (FIELD_GAP 간격, 길가 비율 60% 아래로 내려가지 않게)
    n0 = field_count()
    for k in order:
        if field_count() >= SCENE_TARGET:
            break
        if croad[k] or not alive[k] or cscore[k] < 0.6:
            continue
        if road_count() < 0.62 * (field_count() + 1):
            break
        x, z = float(C[k, 0]), float(C[k, 1])
        if near_scene(x, z, FIELD_GAP):
            continue
        try_at(k)
    log("  들판 보충: 장면 %d 곳 더함" % (field_count() - n0))
    P.rng = main_rng
    cnt = {}
    for s_ in W.scenes:
        cnt[s_["type"]] = cnt.get(s_["type"], 0) + 1
    fs = [s_ for s_ in W.scenes if s_["type"] in SCENES]
    near_road = sum(1 for s_ in fs if s_["road_d"] <= ROADSIDE)
    log("작은 장면 %d 곳 (들판 %d, 길 %d m 안 %d = %.0f%%, 무리·길목 짝 %d 개 %d 곳): %s | 시선 길 %.1f%% 들판 %.1f%% (계획 기준) %.1f 초" % (
        len(W.scenes), len(fs), int(ROADSIDE), near_road, 100.0 * near_road / max(1, len(fs)), len(hamlets),
        sum(len(hh[2]) for hh in hamlets), ", ".join("%s %d" % kv for kv in sorted(cnt.items())),
        100 * cov[:nR].mean(), 100 * cov[nR:].mean(), time.time() - t0))


def scene_report(W, P):
    """장면 틀 요소별 계획 vs 실제 놓임. 필수 요소가 틀 인스턴스의 20% 넘게 빠지면 생성 실패"""
    bad = []
    log("장면 요소 (틀 / 요소: 시도 → 놓임, 필수 요소는 빠진 장면 수 / 장면 수, 대체 없음):")
    for kind in sorted(SCENE_COUNT):
        n = SCENE_COUNT[kind]
        parts = []
        for (k2, tag), (tr, ok, req, fail, skip) in sorted(SCENE_STATS.items()):
            if k2 != kind:
                continue
            s_ = "%s %d→%d" % (tag, tr, ok)
            if req:
                s_ += " [필수 빠짐 %d/%d]" % (fail, n)
                if fail > 0.2 * n:
                    bad.append("%s/%s 빠짐 %d/%d" % (kind, tag, fail, n))
            if skip:
                s_ += " (대체 없음 %d)" % skip
            parts.append(s_)
        log("  %-10s %3d 곳: %s" % (kind, n, ", ".join(parts)))
    short = [s_ for s_ in W.scenes if s_.get("tall", 0) < TALL]
    nob = [s_ for s_ in W.scenes if not s_.get("beacon")]
    log("  세로 요소 %.1f m 미만 장면 %d 곳, 등대 빛 없는 장면 %d 곳" % (TALL, len(short), len(nob)))
    if short:
        log("    낮은 장면:", ", ".join("%s(%.0f, %.0f) %.1f m" % (s_["type"], s_["p"][0], s_["p"][1], s_["tall"]) for s_ in short[:12]))
    if bad:
        raise SystemExit("[실패] 장면 필수 요소가 틀 인스턴스의 20%% 넘게 빠졌다: %s" % "; ".join(bad))


def scene_zones(W):
    """구역 표시: 조밀한 무리(hamlets)와 조용한 구역(quiet: 장면·장소에서 70 m 넘게 떨어진 걸을 수 있는 땅 덩어리, 16 m 칸)"""
    (bx0, bz0), (bx1, bz1) = BOUNDS
    step = 16.0
    g = np.arange(bx0 + step / 2, bx1, step)
    GX, GZ = np.meshgrid(g, g)
    ix, iz = np.round(GX).astype(int), np.round(GZ).astype(int)
    ok = (W.slope[iz, ix] < 0.8) & (W.mount[iz, ix] < 0.3)
    hh = W.h[iz, ix]
    ok &= ~((np.hypot(GX - SWAMP[0], GZ - SWAMP[1]) < SWAMP_R + 40) & (hh < W.swamp_level + 0.1))
    ok &= ~((np.hypot(GX - LAKE[0], GZ - LAKE[1]) < LAKE_R + 30) & (hh < W.lake_level + 0.1))
    d = np.full(GX.shape, 1e9)
    for s_ in W.scenes:
        d = np.minimum(d, np.hypot(GX - s_["p"][0], GZ - s_["p"][1]) - s_["r"])
    dp = np.full(GX.shape, 1e9)
    for (_, _, p, r) in POIS:
        p = p if p else W.bridge_p
        dp = np.minimum(dp, np.maximum(np.hypot(GX - p[0], GZ - p[1]) - r, 0))
    quiet = ok & (np.minimum(d, dp) > 70)
    lab = np.zeros(quiet.shape, int)
    zones = []
    n = 0
    for (a, b) in zip(*np.nonzero(quiet)):
        if lab[a, b]:
            continue
        n += 1
        st = [(a, b)]
        lab[a, b] = n
        cells = []
        while st:
            i, j = st.pop()
            cells.append((i, j))
            for (u, v) in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= u < quiet.shape[0] and 0 <= v < quiet.shape[1] and quiet[u, v] and not lab[u, v]:
                    lab[u, v] = n
                    st.append((u, v))
        if len(cells) < 6:
            continue
        xs = np.array([GX[i, j] for i, j in cells])
        zs = np.array([GZ[i, j] for i, j in cells])
        cx, cz = float(xs.mean()), float(zs.mean())
        ns = min(W.scenes, key=lambda s_: (s_["p"][0] - cx) ** 2 + (s_["p"][1] - cz) ** 2)
        npoi = min(POIS, key=lambda q: math.hypot(cx - (q[2] or W.bridge_p)[0], cz - (q[2] or W.bridge_p)[1]) - q[3])
        rd = float(np.median([sample(W.road_dist, x_, z_) for x_, z_ in zip(xs, zs)]))
        zones.append({"id": "Q%d" % len(zones), "center": [round(cx, 1), round(cz, 1)], "area_ha": round(len(cells) * step * step / 1e4, 2),
                      "cells": [[round(float(x_), 1), round(float(z_), 1)] for x_, z_ in zip(xs, zs)], "cell": step,
                      "road_d_median": round(rd, 1),
                      "nearest_scene": {"type": ns["type"], "p": ns["p"], "d": round(math.hypot(ns["p"][0] - cx, ns["p"][1] - cz), 1)},
                      "nearest_poi": npoi[0],
                      "fill": "밭 경계 돌담(stone_wall_low)·나무 무리·바위 노두·무덤 둔덕·외딴 선돌 (다음 단계)"})
    zones.sort(key=lambda zz: -zz["area_ha"])
    for k, zz in enumerate(zones):
        zz["id"] = "Q%d" % k
    hl = []
    for k, (cx, cz, idx, seen) in enumerate(getattr(W, "hamlets", [])):
        r = max(math.hypot(W.scenes[i]["p"][0] - cx, W.scenes[i]["p"][1] - cz) + W.scenes[i]["r"] for i in idx)
        hl.append({"id": "H%d" % k, "kind": "hamlet" if seen else "pair", "center": [round(cx, 1), round(cz, 1)], "r": round(r + 15, 1),
                   "scenes": idx, "types": [W.scenes[i]["type"] for i in idx], "sees": seen})
    W.zones = {"hamlets": hl, "quiet": zones,
               "note": "hamlets: kind hamlet = 장면 2~3 개 + 장소가 서로 보이는 조밀한 무리, kind pair = 장소가 안 보이는 길목의 장면 둘. "
                       "quiet = 장면·장소에서 70 m 넘게 떨어진 땅 (16 m 칸). "
                       "조용한 구역도 비어 있지 않게 채우는 것은 다음 단계(채움)가 맡는다"}
    log("구역: 무리 %d 개, 길목 짝 %d 개, 조용한 구역 %d 개 (넓이 합 %.1f ha, 가장 큰 것 %.1f ha)" % (
        sum(1 for x_ in hl if x_["kind"] == "hamlet"), sum(1 for x_ in hl if x_["kind"] == "pair"), len(zones), sum(zz["area_ha"] for zz in zones), zones[0]["area_ha"] if zones else 0))


def lay_fields(W, P):
    """넓은 들판의 흩뿌림 소품 (고목·덤불·바위·꽃·해골), 길가 등불.
    v2: 외딴 무덤 무리·폐허 무더기는 작은 장면(lay_vignettes)이 맡는다. 들판이 좁아져(약 0.55 배) 채움 개수도 줄였다"""
    rng = P.rng
    open_ = (W.mount < 0.15).astype(np.float32) * (W.slope < 0.45)
    # 채움 소품은 뭉쳐서 놓는다 (덤불숲과 빈터가 번갈아 온다. 고르게 흩으면 소금·후추처럼 단조롭다)
    # v3 채움: 외톨이로 고르게 흩어지는 것을 줄였다 (FIELD_SCATTER). 나무·덤불은 나무 무리·산울타리(lay_fill)가 맡는다.
    # 바닥의 작은 것(바위 조각·해골·꽃)은 덜 줄인다 (가까이서만 보이고 그리는 물체 수에 거의 들지 않는다)
    wf = open_ * (0.2 + 1.6 * ss(fbm(W.X, W.Z, 1 / 170, 3, 1401), -0.05, 0.25))
    # 장소 둘레(용의 무덤·호수 물가·늪)는 채움(lay_fill)이 들어가지 않으므로 흩뿌림을 줄이지 않는다 (장소 면적당 밀도 유지).
    # 그 몫(가중치 비율 fin)은 장소 안에 그대로(배율 1), 나머지 들판 몫만 FIELD_SCATTER·FIELD_TREES 로 줄인다
    pm = np.zeros(W.h.shape, np.float32)
    for c, R in ((DRAGON, DRAGON_R), (LAKE, LAKE_R + 35), (SWAMP, SWAMP_R)):
        rs, cs, d = disk(W.h.shape, c[0], c[1], R)
        pm[rs, cs] = np.maximum(pm[rs, cs], (d <= R).astype(np.float32))
    tot = float(wf.sum())
    fin = float((wf * pm).sum()) / tot if tot > 0 else 0.0
    af_in, af_out = in_mask(W, wf * pm), in_mask(W, wf * (1 - pm))
    k, k2, kt = FIELD_SCATTER, min(1.0, FIELD_SCATTER * 1.6), FIELD_TREES

    def sc2(a, n, kk, **kw):
        P.scatter(a, int(round(n * fin)), af_in, **kw)
        P.scatter(a, int(n * (1 - fin) * kk), af_out, **kw)
    sc2("dead_tree_a", 130 * DEAD_TREE_CUT, kt)
    sc2("dead_tree_b", 100 * DEAD_TREE_CUT, kt)
    sc2("dead_tree_c", 70 * DEAD_TREE_CUT, kt)
    sc2("bush_dead", 380, k)
    sc2("bramble", 280, k)
    sc2("rock_a", 170, k2)
    sc2("rock_c", 250, k2)
    sc2("rock_b", 35, k)
    sc2("rock_flat", 30, k)
    sc2("stump", 45, k2)
    sc2("log_fallen", 25, k, ground="box")
    sc2("roots", 20, k2)
    sc2("flower_lily", 70, k2)
    sc2("mushroom_glow", 30, k2)
    sc2("skull", 60, k2)
    sc2("bone_pile", 15, k2)
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
    # v3 채움: 길가 울타리 조각(무작위)은 lay_fill 의 길가 경계(이어짐·끊김·문 자리)로 바꿨다


# ─────────────────────────── 채움 (v3): 장면과 장면 사이를 잇는 중간 크기의 것 ───────────────────────────
# 눈높이(1.7 m)에서 20~40 m 마다 눈에 걸리는 것을 길과 지형을 따라 놓는다. 큰 것 몇 개가 작은 것 여러 개보다 낫다 (그리는 물체 수).
#  - 밭 경계: 등고선 줄(relief 의 밭 턱) 위·길가·길에서 들판으로 뻗는 줄에 낮은 돌담·쇠 울타리·가시덤불 산울타리. 끊긴 곳·무너진 곳·문 자리
#  - 나무 무리: 고목 5~15 + 덤불·쓰러진 나무·그루터기·버섯, 낙엽 바닥 (외톨이 나무는 줄이고 무리와 빈터를 대비)
#  - 바위 노두: 언덕 마루·비탈에 반쯤 묻힌 큰 바위 무리 + 바위 바닥
#  - 무덤 둔덕(작은 것)·외딴 선돌·선돌 줄, 길가 물건 (이정표 돌·작은 사당·부서진 수레), 마른 도랑의 돌·뿌리
#  - 물가·장면 둘레 유령 백합, 불·전장 장면 둘레 재
# 줄 소품 상한(FILL_BUDGET)을 넘으면 그 줄은 소품 없이 턱(지형)만 남는다
FILL_SEED = 6262
FILL_BUDGET = {"wall": 1300, "fence": 480, "hedge": 1300, "hedge_tree": 380, "stones": 1600, "post": 110}   # 줄 소품 상한 (그리는 물체 수).
#   밤 눈높이에서 가장 잘 읽히는 것은 밝은 돌담이라 돌담 몫을 크게. w4: 진짜 낮은 돌담(4.1 m 한 칸)이 생겨 1300 칸 = 약 5.4 km.
#   돌담 칸은 META cull 로는 795 m 까지 그려져 WORLD_CULL 로 약 330 m 에서 끈다 (그리는 물체 수 예산 2,000)
FILL_GROVES = 60             # 나무 무리 수 (w4: 40 → 60)
FILL_GROVE_TREES = (5, 11)   # 무리마다 고목 수
FILL_GROVE_GAP = 68.0        # 나무 무리 사이 (m)
FILL_OUTCROP_GAP = 62.0      # 바위 노두 사이 (m)
FILL_CLUMPS = 500            # 작은 덩이 (바위 덩이·덤불 덩이·쓰러진 나무 자리) 수: 눈높이 20~40 m 마다 걸리게. 짧은 거리에서 사라지는 값싼 소품만
FILL_CLUMP_GAP = 26.0        # 작은 덩이 사이 (m)
FILL_SINGLES = 6000          # 낱개 (큰 바위·큰 덤불·돌무더기·그루터기·밝은 돌) 수. w4: 2900 → 6000
FILL_SINGLE_GAP = 7.5        # 낱개 사이 최소 (m). w4: 10 → 7.5
FILL_SINGLE_PALE = 0.6       # w4: 낱개 중 밝은 돌(작은 선돌·무너진 돌담 토막·큰 바위) 몫
FILL_HUTS = 220              # w4: 무너진 움막·우리 터 (낮은 돌담 토막 2~4 개가 네모로 둘러선 자리, 문이나 무너진 쪽이 비었다). 들판의 작은 구조
FILL_HUT_GAP = 42.0          # 움막 터 사이 (m)
SINGLE_CULL = 0.016          # w4: 밝은 돌 낱개가 사라지는 화면 높이 (objects[].cull. 작은 선돌 약 110 m, 돌담 토막 약 200 m, 큰 바위 약 240 m)
FILL_SINGLE_PATCH = 0.8      # 낱개를 넓은 얼룩(약 120 m 무늬)으로 몰아 놓는 세기. 0 = 고르게 (소금·후추처럼 보인다), 클수록 무리와 빈터가 뚜렷
FILL_OUTCROPS = 40           # 바위 노두 수
FILL_BARROWS = 12            # 작은 무덤 둔덕 (장면 '선돌 무덤 둔덕'보다 작고 빛이 없다). w4: 둔덕마다 작은 선돌 고리
FILL_STONES = 60             # 외딴 선돌 (멀리 보이는 세로 실루엣). w4: 진짜 선돌(삼각형 368 개)이 싸서 22 → 60
FILL_ROWS = 12               # 선돌 줄 (능선·마루를 따라). w4: 3 → 12
FILL_ROW_GAP = 140.0         # 선돌 줄 사이 (m)
FILL_BANNERS = 28            # w4: 들판 전장 흔적 깃발 (언덕 마루·능선의 찢긴 깃발 1~2 + 발치 유해). 멀리서 읽히는 세로 실루엣
FILL_CRYSTALS = 16           # w4: 들판 영혼 수정 무리 (움푹한 곳·도랑 가). 큰 수정 하나가 등대 빛, 곁의 작은 수정은 가까이서만 켠다
FILL_GROVE_FIRE = 0.45       # w4: 나무 무리 중 버려진 모닥불(등대 빛, 따뜻한 점)을 두는 비율
SMALL_GLOW_FAR = 45.0        # w4: 곁에 놓는 작은 발광 소품(작은 수정)의 끄는 거리 (objects[].far 로 META 의 140 m 를 줄인다. 등대 빛은 큰 것 하나만)
FILL_SHRINES = 5             # 길가 작은 사당 (굽은 곳)
FILL_CARTS = 6               # 길가 부서진 수레 자리
FILL_MILESTONE = (110.0, 170.0)   # 이정표 돌 간격 (길을 따라 m)
FILL_ROAD_RUN = ((35.0, 95.0), (25.0, 80.0))    # 길가 경계: (이어지는 길이, 끊긴 길이) m. 장면 자리는 저절로 끊긴다
FIELD_TREES = 0.35           # lay_fields 외톨이 고목 배율 (v3 구조 전 1.0. 고목은 나무 무리·산울타리 나무로. w4: 0.2 → 0.35, 하늘에 비치는 실루엣)
FIELD_SCATTER = 0.3          # lay_fields 흩뿌림(외톨이 나무·덤불·바위) 배율 (v3 구조 전 1.0). 장소 둘레(용의 무덤·호수·늪)는 줄이지 않는다


def along_yaw(tx, tz):
    """로컬 X(긴 축)가 (tx, tz) 를 따르게 하는 Unity Y 회전 (도)"""
    return math.degrees(math.atan2(-tz, tx))


def seg_len(P, a, s):
    """줄 소품 하나의 긴 축 길이 (m, 대체 소품이면 대체 소품 크기 × 배율)"""
    m = P.meta.get(a)
    if m is not None:
        return (m.get("_size") or [2 * m.get("footprint", 0.5)])[0] * s
    b, k = NEW_PROPS[a]["sub"]
    mb = P.meta.get(b, {})
    return (mb.get("_size") or [2 * mb.get("footprint", 0.5)])[0] * (k or 1.0) * s


class FillLog:
    def __init__(self):
        self.n = collections.Counter()       # 줄 소품 수
        self.items = []                      # _fill.json 기록
        self.lines = []


FILL_STYLE = {   # 줄 성격 → 구간 모양 비율 (hedge 산울타리, wall 낮은 돌담, fence 쇠 울타리, stones 무너진 돌줄, none 빈 턱·둑)
    # v3 검토 반영: 밤 눈높이에서 가장 잘 읽히는 것은 밝은 돌이다. 돌담을 늘리고 어두운 산울타리를 줄였다 (세운 돌담은 비탈에서 칸이 끊겨 덜 놓인다)
    # w4: 진짜 낮은 돌담·쇠 울타리가 생겨 돌담 몫을 더 올렸다 (어두운 덤불 산울타리는 풀에 묻힌다)
    "hedge":  {"hedge": 0.3, "stones": 0.12, "fence": 0.08, "wall": 0.38, "none": 0.12},
    "wall":   {"wall": 0.68, "stones": 0.18, "hedge": 0.07, "none": 0.07},
    "fence":  {"fence": 0.52, "hedge": 0.12, "stones": 0.08, "wall": 0.16, "none": 0.12},
    "stones": {"stones": 0.45, "hedge": 0.1, "wall": 0.28, "none": 0.17},
    "scarp":  {"none": 0.4, "stones": 0.27, "hedge": 0.11, "wall": 0.22},
    "cross":  {"hedge": 0.2, "stones": 0.24, "fence": 0.12, "wall": 0.32, "none": 0.12},
}
FILL_SCARP_CLEAR = 1.7       # 밭 턱 위 가장자리에서 줄 소품까지 (m). 턱 비탈(RELIEF_RISER) 위에 걸치면 바닥 상자가 기울어 한쪽이 묻힌다
FILL_STEP_DH = 0.36          # 돌담·울타리 한 칸 양 끝 땅 높이 차가 키의 이 비율을 넘으면 그 칸은 비운다 (턱을 가로지르면 칸을 끊는다. 칸마다 세워 놓으므로 계단처럼 높이가 바뀐다)
FILL_UPRIGHT_BURY = 0.42     # 세운 울타리의 묻힘 한계 (높이 비율: 비탈 오르막 쪽이 이만큼까지 묻힌다. 한쪽 끝 50% 넘게 묻힌 것이 없게)
FILL_WALL_SLOPE = 0.3        # 세운 돌담을 놓는 땅 기울기 한계. w4: 진짜 돌담은 깊이 0.89 m 라 (대체 조각 1.5 m) 옆 비탈 0.3 에서도 오르막 쪽 묻힘이 약 0.27 m
FILL_WALL_LEAN = 5.0         # w4: 돌담이 비탈을 따라 기울 수 있는 최대 각(도). 조금만 따르면 오르막 끝 묻힘이 약 0.2 m 준다 (v3 검토: 크게 기운 담은 안 된다)
FILL_WALL_BURY = 0.3         # 세운 돌담의 묻힘 한계 (manifest 높이 1.29 m 비율. 땅속 밑동 0.3 m 가 있어 내리막 쪽도 뜨지 않는다)
FILL_RUN = (10.0, 30.0)      # 줄 구간 길이 (m). w4: 7~24 → 10~30 (줄이 줄로 읽히게)
FILL_GAP = (3.0, 10.0)       # 구간 사이 끊긴 곳 (m). 6 m 넘게 끊기면 눈에는 다른 것으로 읽힌다 (w4: 4~13 → 3~10)


FILL_WISP_GROVE = 0.6        # 나무 무리 중 약한 떠도는 빛(영혼 빛 + 불티 효과)을 두는 비율. 둔덕·선돌 줄은 모두


def field_wisp(W, P, rng, x, z, up=(1.4, 2.4)):
    """들판 무리의 약한 떠도는 빛: 작은 점광원(등대 빛 아님, LightCuller 기본 규칙) + 불티 효과(wisps). 광원 예산이 넘는 곳에서는
    trim_lights 가 초·버섯 다음으로 뺀다 (weak)"""
    if P.under_water(x, z, 0.2):
        return
    y = P.height(x, z) + rng.uniform(*up)
    W.lights.append({"p": [round(x, 2), round(y, 2), round(z, 2)], "c": list(SPIRIT if rng.random() < 0.55 else SOUL),
                     "i": round(float(rng.uniform(1.4, 2.0)), 2), "r": round(float(rng.uniform(5.0, 6.5)), 1), "flicker": True, "weak": True})
    W.fx.append({"type": "wisps", "p": [float(x), y - 0.6, float(z)], "r": round(float(rng.uniform(5.0, 8.0)), 1)})


def step_ok(P, x, z, tv, ln, hgt):
    """줄 소품 한 칸(가운데 x, z, 방향 tv, 길이 ln)의 양 끝과 가운데 땅 높이 차가 키 × FILL_STEP_DH 안인가 (턱을 가로지르면 그 칸은 비운다)"""
    hx, hz = tv[0] * ln / 2, tv[1] * ln / 2
    a, b, c = P.height(x - hx, z - hz), P.height(x, z), P.height(x + hx, z + hz)
    return max(a, b, c) - min(a, b, c) <= FILL_STEP_DH * hgt


def fill_line(W, P, rng, F, pts, kind, src, up=None):
    """꺾은선 pts 를 따라 줄 성격 kind 의 경계를 놓는다. 줄은 구간(FILL_RUN)과 끊긴 곳(FILL_GAP)이 번갈고,
    구간마다 모양(FILL_STYLE: 산울타리·낮은 돌담·쇠 울타리·무너진 돌줄·빈 턱)을 고른다. 끊긴 곳에는 가끔 무너진 돌무더기나
    문 자리(낮은 기둥 둘). up: 오르막 쪽 부호 (밭 턱 위 가장자리에 놓는다). 놓인 소품 수를 돌려준다"""
    c, L = resample(np.asarray(pts, np.float64), 0.5)
    if L < 8:
        return 0
    tang = np.gradient(c, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
    nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    shift = 0.0 if up is None else (RELIEF_RISER / 2 + FILL_SCARP_CLEAR) * up   # 밭 턱이면 턱 위(오르막 쪽), 턱 비탈에서 떨어진 평평한 곳에
    mix = FILL_STYLE.get(kind, FILL_STYLE["hedge"])
    styles, sp_ = list(mix), np.array(list(mix.values()))
    budget = FILL_BUDGET
    placed, runs = [], []
    gates = 0
    pos = rng.uniform(0, 4)
    next_tree = rng.uniform(6, 16)

    def at(p):
        i = min(max(int(p / 0.5), 0), len(c) - 1)
        q = c[i] + nrm[i] * shift
        return float(q[0]), float(q[1]), tang[i], i

    while pos < L - 2:
        run = rng.uniform(*FILL_RUN)
        st = str(rng.choice(styles, p=sp_ / sp_.sum()))
        if st in ("wall", "fence") and F.n[st] >= budget[st]:
            st = "stones"
        if st == "hedge" and F.n["hedge"] >= budget["hedge"]:
            st = "stones"
        if st == "stones" and F.n["stones"] >= budget["stones"]:
            st = "none"
        end = min(L - 1, pos + run)
        got = []
        while pos < end:
            x, z, tv, i = at(pos)
            ty = along_yaw(*tv)
            step = 3.0
            if st == "wall":
                # v3 검토 반영: 같은 조각 실루엣이 1.5 m 마다 되풀이되지 않게 yaw 180° 뒤집기·배율·높이를 섞는다. 기울이지 않고 세운다
                s = rng.uniform(1.0, 1.18)                      # w4: 원점 위 0.99 m × 배율 = 갓돌까지 1.0~1.17 m (풀 0.4~0.8 m 위로 드러나게)
                ln = seg_len(P, "stone_wall_low", s)
                x, z, tv, i = at(pos + ln / 2)
                if F.n["wall"] < budget["wall"] and step_ok(P, x, z, tv, ln, 1.2 * s) and \
                        P.put("stone_wall_low", x, z, yaw=along_yaw(*tv) + (180 if rng.random() < 0.5 else 0) + rng.normal(0, 4), s=s, slope=FILL_WALL_SLOPE,
                              ground="box", r=1.1, bury_max=FILL_WALL_BURY, align=1.0, align_max=FILL_WALL_LEAN, tilt=2,
                              ground_margin=rng.uniform(0.0, 0.08) * 1.2 * s):         # 높이 섞기 (조금씩 다르게 묻는다)
                    F.n["wall"] += 1
                    got.append((x, z))
                step = ln * rng.uniform(0.9, 1.0)
            elif st == "fence":
                s = rng.uniform(0.96, 1.04)
                ln = seg_len(P, "iron_fence", s)
                x, z, tv, i = at(pos + ln / 2)
                if F.n["fence"] < budget["fence"] and step_ok(P, x, z, tv, ln, 1.7 * s) and \
                        P.put("iron_fence", x, z, yaw=along_yaw(*tv) + rng.normal(0, 2), s=s, slope=0.55, ground="box", r=0.9, tilt=3, align=False,
                              bury_max=FILL_UPRIGHT_BURY):
                    F.n["fence"] += 1
                    got.append((x, z))
                step = ln * 0.98
            elif st == "hedge":
                if pos >= next_tree and F.n["hedge_tree"] < budget["hedge_tree"]:      # 산울타리 나무
                    nm = "dead_tree_b" if rng.random() < 0.55 else "dead_tree_c"
                    if P.put(nm, x + rng.normal(0, 0.6), z + rng.normal(0, 0.6), s=rng.uniform(0.95, 1.25), stamp=("leaves", 1.6)):
                        F.n["hedge_tree"] += 1
                        got.append((x, z))
                    next_tree = pos + rng.uniform(6, 12)                  # 산울타리 사이 고목을 자주 (덤불만으로는 밤에 풀에 묻힌다. w4: 8~16 → 6~12 m)
                nm = "bush_dead" if rng.random() < 0.82 else "bramble"           # 가시덤불은 멀리까지 그려져(그리는 물체 수) 조금만
                s = rng.uniform(1.25, 1.6) if nm == "bush_dead" else rng.uniform(1.1, 1.35)
                if F.n["hedge"] < budget["hedge"] and P.put(nm, x + rng.normal(0, 0.35), z + rng.normal(0, 0.35), s=s, r=0.6, stamp=("leaves", 1.3)):
                    F.n["hedge"] += 1
                    got.append((x, z))
                step = rng.uniform(2.4, 3.4)
            elif st == "stones":                                 # 무너진 돌줄 (낮은 돌무더기·바위가 줄지어)
                r_ = rng.random()                                # 풀 위로 드러나게 큰 돌 위주 (돌무더기·작은 돌은 사이에)
                if r_ < 0.2:                                     # w4: 쓰러져 가는 돌 말뚝 (작은 선돌, 1.0~1.4 m, 밝은 돌). 줄이 풀 위로 읽히게
                    ok = P.put("standing_stone", x + rng.normal(0, 0.3), z + rng.normal(0, 0.3), yaw=ty + rng.normal(0, 25),
                               s=rng.uniform(0.32, 0.45), slope=0.45, tilt=14, ground="box", ground_margin=0.12, bury_max=0.4)
                elif r_ < 0.4:
                    ok = P.put("rubble", x + rng.normal(0, 0.3), z + rng.normal(0, 0.3), yaw=ty + rng.normal(0, 20), s=rng.uniform(1.3, 1.6), slope=0.6)
                elif r_ < 0.82 and sample(W.slope, x, z) < 0.32:
                    ok = P.put("rock_a", x + rng.normal(0, 0.3), z + rng.normal(0, 0.3), s=rng.uniform(1.25, 1.65), slope=0.32)
                else:
                    ok = P.put("rock_c", x + rng.normal(0, 0.3), z + rng.normal(0, 0.3), s=rng.uniform(1.5, 1.9), slope=0.6)
                if ok:
                    F.n["stones"] += 1
                    got.append((x, z))
                step = rng.uniform(1.8, 2.8)
            else:                                                # 빈 턱·둑: 드물게 드러난 돌
                if rng.random() < 0.25:
                    P.put("rock_c", x, z, s=rng.uniform(0.9, 1.4), slope=0.8)
                step = rng.uniform(8, 14)
            pos += step
        if got:
            runs.append((st, got))
            placed.extend(got)
        # 끊긴 곳
        gap = rng.uniform(*FILL_GAP)
        x, z, tv, i = at(pos + gap / 2)
        r_ = rng.random()
        if st in ("wall", "stones") and r_ < 0.3:                # 무너진 곳: 돌무더기
            P.put("rubble", x, z, s=rng.uniform(0.9, 1.25), slope=0.6)
        elif st in ("wall", "fence", "hedge") and r_ < 0.45 and gates < 2 and gap > 4.5 and F.n["post"] < budget["post"]:
            for sd in (-1, 1):                                   # 문 자리: 낮은 기둥 둘
                px, pz, _, _ = at(pos + gap / 2 + sd * 1.7)
                if P.put("pillar_a", px, pz, s=rng.uniform(0.46, 0.54), slope=0.6, tilt=4):
                    F.n["post"] += 1
            gates += 1
        elif st == "fence" and r_ < 0.6:                         # 끊긴 울타리 자리: 부서진 기둥 하나
            P.put("pillar_a", x, z, s=rng.uniform(0.34, 0.42), slope=0.5, tilt=5)
        pos += gap
    for st, got in runs:
        F.lines.append({"t": st, "src": src, "kind": kind, "pts": [[round(float(a), 1), round(float(b), 1)] for a, b in got]})
    if kind in ("scarp",) or (up is not None and not runs):
        F.lines.append({"t": "scarp", "src": src, "kind": kind, "pts": [[round(float(a), 1), round(float(b), 1)] for a, b in c[::20]]})
    return len(placed)


def fill_pick(W, P, rng, weight, n, gap, avoid_scene=15.0, avoid_poi=15.0, road_min=10.0, extra_ok=None):
    """가중치 지도(2049) 비례로 자리를 n 개까지 고른다 (서로 gap m 넘게, 장면·장소·길에서 떨어져)"""
    pick = in_mask(W, weight)
    pois = [((p if p else W.bridge_p), r) for (_, _, p, r) in POIS]
    got = []
    for _ in range(n * 60):
        if len(got) >= n:
            break
        p = pick(rng)
        if p is None:
            break
        x, z = p
        if any((x - a) ** 2 + (z - b) ** 2 < gap * gap for a, b in got):
            continue
        if sample(W.road_dist, x, z) < sample(W.road_hw, x, z) + road_min or P.under_water(x, z, 0.3):
            continue
        if any((x - s_["p"][0]) ** 2 + (z - s_["p"][1]) ** 2 < (s_["r"] + avoid_scene) ** 2 for s_ in W.scenes):
            continue
        if any((x - c[0]) ** 2 + (z - c[1]) ** 2 < (r + avoid_poi) ** 2 for c, r in pois if r < 150):
            continue
        if extra_ok is not None and not extra_ok(x, z):
            continue
        got.append((x, z))
    return got


def fill_singles(W, P, rng, F, open_):
    """낱개 채움 (FILL_SINGLES 개, 서로 FILL_SINGLE_GAP m 넘게). 자리 무게 = 줄·도랑 가까이 + 움푹한 곳 + 마루 + 비탈 꺾임"""
    t0 = time.time()
    near = np.zeros(W.h.shape, np.float32)
    for ln in W.relief_lines:
        for (x, z) in ln["pts"][::2]:
            near[int(z), int(x)] = 1.0
    for dt in W.ditches:
        for (x, z) in dt["pts"][::2]:
            near[int(z), int(x)] = 1.0
    near = np.clip(box_blur(near, 7, 2) * 12.0, 0, 1)
    brk = ss(np.abs(W.slope - box_blur(W.slope, 6)), 0.04, 0.15)
    patch = (1.0 - FILL_SINGLE_PATCH * 0.5) + FILL_SINGLE_PATCH * ss(fbm(W.X, W.Z, 1 / 120, 3, 6363), -0.1, 0.3)
    w = open_ * (0.45 + 0.8 * near + 0.6 * W.hollow + 0.6 * W.crest + 0.4 * brk) * (W.slope < 0.5) * np.clip(patch, 0.05, None)
    pick = in_mask(W, w.astype(np.float32))
    sc = np.array([(s_["p"][0], s_["p"][1], s_["r"] + 4.0) for s_ in W.scenes]) if W.scenes else np.zeros((0, 3))
    pois = np.array([((p if p else W.bridge_p)[0], (p if p else W.bridge_p)[1], r + 6.0) for (_, _, p, r) in POIS if r < 150])
    grid = {}
    G = FILL_SINGLE_GAP
    got = collections.Counter()
    n = 0
    for _ in range(FILL_SINGLES * 12):
        if n >= FILL_SINGLES:
            break
        p = pick(rng)
        if p is None:
            break
        x, z = p
        k = (int(x // G), int(z // G))
        if any((x - a) ** 2 + (z - b) ** 2 < G * G for i in (-1, 0, 1) for j in (-1, 0, 1) for (a, b) in grid.get((k[0] + i, k[1] + j), ())):
            continue
        if len(sc) and np.any((sc[:, 0] - x) ** 2 + (sc[:, 1] - z) ** 2 < sc[:, 2] ** 2):
            continue
        if np.any((pois[:, 0] - x) ** 2 + (pois[:, 1] - z) ** 2 < pois[:, 2] ** 2):
            continue
        hv, cv = sample(W.hollow, x, z), sample(W.crest, x, z) + 0.7 * ssf(sample(W.slope, x, z), 0.15, 0.35)
        # w4: 밤 눈높이에서 읽히는 밝은 돌 낱개 (작은 선돌·무너진 돌담 토막·큰 바위). 어두운 rock_a·덤불은 25 m 밖에서 풀에 묻혔다
        #     (검토자 자리 렌더). 가까이서만 그리면 되니 사라지는 화면 높이를 크게 (SINGLE_CULL: 120~250 m 에서 사라진다)
        q_ = rng.random()
        if q_ < FILL_SINGLE_PALE and sample(W.slope, x, z) < 0.4:
            n0 = len(P.objects)
            u_ = rng.random()
            if u_ < 0.42:                                     # 작은 선돌 (1.1~1.7 m, 기울기도)
                ok = P.put("standing_stone", x, z, s=rng.uniform(0.35, 0.55), slope=0.4, tilt=16, ground="box", ground_margin=0.1, bury_max=0.4,
                           pad=False)
                t = "pale_stone"
            elif u_ < 0.72:                                   # 무너진 돌담 토막 (2.5~3.5 m, 0.6~0.85 m)
                gx_, gz_ = sample(W.gx, x, z), sample(W.gz, x, z)
                yw_ = (along_yaw(-gz_, gx_) if abs(gx_) + abs(gz_) > 0.02 else rng.uniform(0, 360)) + rng.normal(0, 15) + (180 if rng.random() < 0.5 else 0)
                ok = P.put("stone_wall_low", x, z, yaw=yw_, s=rng.uniform(0.62, 0.85), slope=0.3, ground="box", align=1.0, align_max=FILL_WALL_LEAN,
                           bury_max=FILL_WALL_BURY, ground_margin=rng.uniform(0.0, 0.12), pad=False)
                t = "wall_bit"
            else:                                             # 큰 바위 (1.4~2 m)
                ok = P.put("rock_b", x, z, s=rng.uniform(0.85, 1.1), slope=None, ground="box", align_max=30)
                t = "big_rock"
            if ok and len(P.objects) > n0:
                P.objects[-1]["cull"] = SINGLE_CULL
                if rng.random() < 0.3:
                    P.put("rock_c", x + rng.normal(0, 1.4), z + rng.normal(0, 1.4), s=rng.uniform(0.9, 1.3), slope=0.6)
            if ok:
                grid.setdefault(k, []).append((x, z))
                got[t] += 1
                n += 1
            continue
        r_ = rng.random() * (1.0 + hv + cv)
        # 풀(키 0.4~0.8 m) 위로 드러나게 키 1.4 m 넘는 것만 (그루터기·돌무더기처럼 낮은 것은 고사리에 묻힌다)
        if r_ < 0.6 + cv:                                     # 큰 바위 (가끔 둘). 밤에 밝게 읽히는 돌을 덤불보다 많이
            if sample(W.slope, x, z) < 0.3:
                ok = P.put("rock_a", x, z, s=rng.uniform(1.35, 1.8), slope=0.3)
            else:
                ok = P.put("rock_b", x, z, s=rng.uniform(0.8, 1.05), slope=None, ground="box", align_max=30)
            if ok and rng.random() < 0.35:
                P.put("rock_c", x + rng.normal(0, 1.6), z + rng.normal(0, 1.6), s=rng.uniform(1.2, 1.6), slope=0.6)
            t = "rock"
        elif r_ < 0.6 + cv + 0.32 + hv:                       # 큰 덤불
            nm = "bush_dead" if rng.random() < 0.85 else "bramble"
            ok = P.put(nm, x, z, s=rng.uniform(1.5, 1.9) if nm == "bush_dead" else rng.uniform(1.2, 1.45), stamp=("leaves", 1.2))
            t = "bush"
        else:                                                 # 고목 둥치(그루터기 + 뿌리) 또는 쓰러진 나무 (조금 큰 것)
            if rng.random() < 0.72:
                ok = P.put("stump", x, z, s=rng.uniform(1.35, 1.6), slope=0.45)
                if ok:
                    P.put("roots", x + rng.normal(0, 1.0), z + rng.normal(0, 1.0), s=rng.uniform(1.0, 1.3))
                t = "stump"
            else:
                ok = P.put("log_fallen", x, z, s=rng.uniform(0.9, 1.15), slope=0.4, ground="box")
                t = "log"
        if ok:
            grid.setdefault(k, []).append((x, z))
            got[t] += 1
            n += 1
    log("  낱개 채움 %d (%s), %.1f 초" % (n, dict(got), time.time() - t0))
    F.n["single"] = n


FOOT_WALL_DD = (16.0, 30.0)    # w4: 산기슭 경계 돌담이 지나는 발치 안쪽 거리 범위 (m, 느린 노이즈로 오르내린다)
FOOT_WALL_KINDS = (("wall", 0.55), ("stones", 0.25), ("fence", 0.08), ("hedge", 0.12))


def foot_wall_lines(W, P):
    """w4: 산기슭 띠(벽 발치 안쪽 16~30 m)를 따라 도는 옛 경계 줄. 산 밑을 걸을 때 벽 앞이 비지 않게 (검토 V1·V4·V7·V8).
    bounds 둘레를 3 m 마다 돌며 안쪽으로 걸어 들어가 발치 거리 dd 가 −D 아래가 되는 점을 잇는다. 길·물·숲·장소·봉인문 둘레는 끊는다"""
    (bx0, bz0), (bx1, bz1) = BOUNDS
    pois = [((p if p else W.bridge_p), r) for (_, _, p, r) in POIS]
    side_pts = []
    for (ax, az, ex, ez, ix, iz, L) in ((bx0, bz0, 1, 0, 0, 1, bx1 - bx0), (bx1, bz0, 0, 1, -1, 0, bz1 - bz0),
                                        (bx1, bz1, -1, 0, 0, -1, bx1 - bx0), (bx0, bz1, 0, -1, 1, 0, bz1 - bz0)):
        for t in np.arange(30.0, L - 30.0, 3.0):
            x0, z0 = ax + ex * t, az + ez * t
            D = FOOT_WALL_DD[0] + (FOOT_WALL_DD[1] - FOOT_WALL_DD[0]) * (0.5 + 0.5 * float(perlin(np.float32(x0 * 0.012), np.float32(z0 * 0.012), 9101)))
            q = None
            for k in range(0, 260, 2):
                x, z = x0 + ix * k, z0 + iz * k
                if sample(W.dd, x, z) < -D:
                    q = (x, z)
                    break
            side_pts.append(q)
    runs, cur = [], []
    for q in side_pts + [None]:
        ok = q is not None
        if ok:
            x, z = q
            ok = (sample(W.road_dist, x, z) > sample(W.road_hw, x, z) + 6 and not P.under_water(x, z, 0.3) and sample(W.forest_plan, x, z) < 0.2
                  and sample(W.slope, x, z) < 0.35 and math.hypot(x - GATE[0], z - GATE[1]) > 150
                  and all((x - c[0]) ** 2 + (z - c[1]) ** 2 > (r + 15) ** 2 for c, r in pois))
            if ok and cur and math.hypot(x - cur[-1][0], z - cur[-1][1]) > 9.0:
                ok = None                              # 능선 밑동에서 건너뛴다: 줄을 끊고 새로 시작
        if ok:
            cur.append(q)
        else:
            if len(cur) >= 8:
                runs.append(cur)
            cur = [q] if ok is None else []
    return runs


def lay_fill(W, P):
    """장면과 장면 사이를 잇는 중간 크기의 것 (v3 채움). 앞 단계(장면·숲·산기슭) 뒤, 들판 흩뿌림(lay_fields) 앞"""
    t0 = time.time()
    main_rng = P.rng
    P.rng = rng = np.random.default_rng(FILL_SEED)
    F = FillLog()
    h = W.h
    hb = box_blur(h, 18)
    W.hollow = (ss(-(h - hb), 0.25, 1.4) * (1 - ss(W.mount, 0.05, 0.2))).astype(np.float32)
    # w4: 숲 가장자리 띠(숲 계획 0.08~0.25, 나무가 거의 없는 곳)가 숲에도 채움에도 들지 않아 비었다 (검토 V6). 채움을 숲 계획 0.22~0.45 까지 들인다
    open_ = ((W.mount < 0.22) & (W.slope < 0.42)).astype(np.float32) * (1 - ss(W.forest_plan, 0.22, 0.45))
    ex = ((W.X - GRAVE_C[0]) / (GRAVE_R[0] + 15)) ** 2 + ((W.Z - GRAVE_C[1]) / (GRAVE_R[1] + 15)) ** 2
    open_ *= ss(ex, 1.0, 1.25)
    # 늪·호수 둘레 빈 띠를 좁힌다 (장소 흩뿌림은 장소 원 안까지라, 원 밖 20~40 m 띠가 아무도 채우지 않는 빈 땅이 됐다)
    for c, R in ((SWAMP, SWAMP_R), (DRAGON, DRAGON_R - 10), (LAKE, LAKE_R + 12)):
        rs, cs, d = disk(h.shape, c[0], c[1], R + 21)
        open_[rs, cs] *= ss(d, R, R + 20)
    W.fill_open = open_

    # 1) 밭 경계 줄 (relief 의 등고선 줄·가로 줄): 턱이 있으면 턱 위 가장자리에, 없으면 둑 위에
    order = sorted(range(len(W.relief_lines)), key=lambda i: -W.relief_lines[i]["L"])
    for i in order:
        ln = W.relief_lines[i]
        fill_line(W, P, rng, F, ln["pts"], ln["kind"], "cross" if ln["A"] <= 0 and ln["kind"] == "cross" else "field",
                  up=ln["up"] if ln["A"] > 0.25 else None)

    # 1b) w4: 산기슭 경계 줄 (벽 발치 안쪽 16~30 m 를 따라 도는 옛 돌담·돌줄)
    fk, fp_ = [k_ for k_, _ in FOOT_WALL_KINDS], np.array([p_ for _, p_ in FOOT_WALL_KINDS])
    nfoot = 0
    for run in foot_wall_lines(W, P):
        c, Lr = resample(np.asarray(run, np.float64), 3.0)
        # 둘레 3 m 걸음의 잔 흔들림을 편다 (이웃 5 점 평균)
        if len(c) > 5:
            k_ = np.ones(5) / 5.0
            c = np.stack([np.convolve(np.pad(c[:, i], 2, mode="edge"), k_, "valid") for i in range(2)], 1)
        nfoot += fill_line(W, P, rng, F, c, str(rng.choice(fk, p=fp_ / fp_.sum())), "foot")
    log("  산기슭 경계 줄: 소품 %d, 줄 소품 %s" % (nfoot, dict(F.n)))

    pois_small = [((p if p else W.bridge_p), r) for (_, _, p, r) in POIS if r < 150]
    # 2) 길가 물건 (길가 경계보다 먼저 자리를 잡는다): 이정표 돌, 작은 사당 (굽은 곳), 부서진 수레 자리
    sc_xy = np.array([s_["p"] for s_ in W.scenes]) if W.scenes else np.zeros((0, 2))

    def scene_near(x, z, r):
        return len(sc_xy) and np.min((sc_xy[:, 0] - x) ** 2 + (sc_xy[:, 1] - z) ** 2) < r * r

    def poi_near(x, z, pad):
        return any((x - q[0]) ** 2 + (z - q[1]) ** 2 < (r + pad) ** 2 for q, r in pois_small)
    nmile = 0
    why = collections.Counter()
    for ri, (c, hw) in enumerate(W.road_curves):
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        pos = rng.uniform(40, 110)
        while pos < s[-1] - 30:
            k = int(np.searchsorted(s, pos))
            x, z, yw, _, _ = road_point(W, ri, float(c[k, 0]), float(c[k, 1]), 1 if rng.random() < 0.5 else -1, 1.6)
            why["try"] += 1
            if scene_near(x, z, 22):
                why["scene"] += 1
            elif poi_near(x, z, 0):
                why["poi"] += 1
            else:
                if not P.put("standing_stone", x, z, yaw=yw + rng.normal(0, 6), s=rng.uniform(0.36, 0.46), slope=0.5, ground="box", ground_margin=0.3):
                    why["put"] += 1
                    why["ground" if not P.ok_ground(x, z, 0.5, True, True, 0.5) else "free"] += 1
                else:
                    P.put("rock_c", x + rng.normal(0, 0.9), z + rng.normal(0, 0.9), slope=0.6, road=False)
                    if rng.random() < 0.35:
                        P.put("skull", x + rng.normal(0, 0.6), z + rng.normal(0, 0.6), road=False)
                    F.items.append({"t": "milestone", "p": [round(x, 1), round(z, 1)]})
                    nmile += 1
            pos += rng.uniform(*FILL_MILESTONE)
    log("  이정표 시도:", dict(why))
    nshr = 0
    bends = sorted([rf for rf in getattr(W, "road_feat", []) if rf[4] in ("bend", "crest", "forest_entry") and rf[5] > 0.35], key=lambda rf: -rf[5])
    used_sh = []
    for (bx_, bz_, ri, nrm_, feat, sc_, bout) in bends:
        if nshr >= FILL_SHRINES:
            break
        if scene_near(bx_, bz_, 32) or poi_near(bx_, bz_, 20) or any((bx_ - a) ** 2 + (bz_ - b) ** 2 < 180 ** 2 for a, b in used_sh):
            continue
        sd = bout if bout else 1
        x, z, yw, _, _ = road_point(W, ri, bx_, bz_, sd, 2.4)
        if P.put("shrine_roadside", x, z, yaw=yw, slope=0.4, ground="box"):
            fx_, fz_ = math.sin(math.radians(yw)), math.cos(math.radians(yw))
            rx_, rz_ = fz_, -fx_
            for q in (-1, 1):
                P.put("candles", x + rx_ * q * 0.9 + fx_ * 0.6, z + rz_ * q * 0.9 + fz_ * 0.6, road=False)
                P.put("flower_lily", x + rx_ * q * 1.6 - fx_ * 0.4, z + rz_ * q * 1.6 - fz_ * 0.4, road=False)
            P.put("rock_c", x - fx_ * 1.2 + rng.normal(0, 0.5), z - fz_ * 1.2 + rng.normal(0, 0.5), road=False)
            used_sh.append((bx_, bz_))
            F.items.append({"t": "shrine", "p": [round(x, 1), round(z, 1)]})
            nshr += 1
    ncart = 0
    cand = [rf for rf in getattr(W, "road_feat", []) if rf[5] < 0.4]
    rng.shuffle(cand)
    used_c = []
    for (bx_, bz_, ri, nrm_, feat, sc_, bout) in cand:
        if ncart >= FILL_CARTS:
            break
        if scene_near(bx_, bz_, 35) or poi_near(bx_, bz_, 15) or any((bx_ - a) ** 2 + (bz_ - b) ** 2 < 200 ** 2 for a, b in used_c + used_sh):
            continue
        sd = 1 if rng.random() < 0.5 else -1
        x, z, yw, _, _ = road_point(W, ri, bx_, bz_, sd, 3.4)
        if P.put("cart_broken", x, z, yaw=yw + 90 + rng.normal(0, 20), slope=0.4, r=1.5):
            for q in range(2):
                P.put("rubble", x + rng.normal(0, 1.8), z + rng.normal(0, 1.8), s=rng.uniform(0.7, 0.95), road=False)
            P.put("skeleton_remains", x + rng.normal(0, 2.0), z + rng.normal(0, 2.0), road=False)
            P.put("skull", x + rng.normal(0, 1.5), z + rng.normal(0, 1.5), road=False)
            P.stamps.append((x, z, 2.6, "dirt"))
            used_c.append((bx_, bz_))
            F.items.append({"t": "cart", "p": [round(x, 1), round(z, 1)]})
            ncart += 1

    # 3) 길가 경계와 길에서 들판으로 뻗는 줄 (길 바깥 3 m, 한쪽씩 번갈아, 이어짐·끊김)
    pois_small = [((p if p else W.bridge_p), r) for (_, _, p, r) in POIS if r < 150]
    road_kinds = (("fence", 0.36), ("wall", 0.3), ("hedge", 0.34))
    rk, rp = [k_ for k_, _ in road_kinds], np.array([p_ for _, p_ in road_kinds])
    nspur = 0
    rwhy = collections.Counter()
    for ri, (c, hw) in enumerate(W.road_curves):
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        L = s[-1]
        pos = rng.uniform(20, 60)
        side = 1 if rng.random() < 0.5 else -1
        while pos < L - 30:
            run = rng.uniform(*FILL_ROAD_RUN[0])
            t = np.arange(pos, min(pos + run, L - 25), 2.0)
            if len(t) < 6:
                break
            px = np.interp(t, s, c[:, 0])
            pz = np.interp(t, s, c[:, 1])
            mid = (float(px[len(px) // 2]), float(pz[len(pz) // 2]))
            ok = not any((mid[0] - q[0]) ** 2 + (mid[1] - q[1]) ** 2 < (r + 12) ** 2 for q, r in pois_small)
            ex_ = ((mid[0] - GRAVE_C[0]) / (GRAVE_R[0] + 10)) ** 2 + ((mid[1] - GRAVE_C[1]) / (GRAVE_R[1] + 10)) ** 2
            ok = ok and ex_ > 1.0 and sample(W.forest_plan, *mid) < 0.25 and \
                math.hypot(mid[0] - SWAMP[0], mid[1] - SWAMP[1]) > SWAMP_R - 20
            rwhy["try"] += 1
            if not ok:
                rwhy["place"] += 1
            if ok:
                d = np.stack([np.gradient(px), np.gradient(pz)], 1)
                d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
                n = np.stack([d[:, 1], -d[:, 0]], 1) * side
                off = hw + 3.0 + rng.uniform(0, 0.8)
                line = np.stack([px, pz], 1) + n * off
                kind = str(rng.choice(rk, p=rp / rp.sum()))
                got = fill_line(W, P, rng, F, line, kind, "road")
                rwhy[kind + ("_ok" if got else "_0")] += 1
                # 들판으로 뻗는 줄 (끝에서, 길에 수직으로 35~90 m, 비탈을 조금 따라). 만나는 곳은 문 자리로 비운다
                if got and rng.random() < 0.55:
                    k = -1 if rng.random() < 0.5 else 0
                    x0_, z0_ = line[k] + n[k] * 4.0
                    dirv = n[k].copy()
                    pts = [(x0_, z0_)]
                    Ls = rng.uniform(35, 90)
                    for q in range(int(Ls / 2)):
                        gx_, gz_ = sample(W.gx, *pts[-1]), sample(W.gz, *pts[-1])
                        dirv = dirv * 0.9 + np.array([-gx_, -gz_]) * 0.6
                        dirv = dirv / (np.linalg.norm(dirv) + 1e-9)
                        nx_, nz_ = pts[-1][0] + dirv[0] * 2, pts[-1][1] + dirv[1] * 2
                        if sample(W.fill_open, nx_, nz_) < 0.5 or sample(W.road_dist, nx_, nz_) < sample(W.road_hw, nx_, nz_) + 4:
                            break
                        pts.append((nx_, nz_))
                    if len(pts) > 10:
                        k2 = str(rng.choice(rk, p=rp / rp.sum()))
                        if fill_line(W, P, rng, F, pts, k2, "spur"):
                            nspur += 1
            pos += run + rng.uniform(*FILL_ROAD_RUN[1])
            side = -side if rng.random() < 0.7 else side

    log("  길가 경계 시도:", dict(rwhy), "줄 소품", dict(F.n))
    # 4) 나무 무리 (움푹한 곳·도랑 가·비탈 아래를 좋아한다)
    wg = open_ * (0.35 + 1.2 * W.hollow + 0.4 * ss(W.slope, 0.08, 0.25)) * (W.slope < 0.35)
    groves = fill_pick(W, P, rng, wg, FILL_GROVES, FILL_GROVE_GAP, avoid_scene=14.0, road_min=9.0)
    ntr = 0
    for (cx, cz) in groves:
        R = rng.uniform(10, 19)
        el = rng.uniform(1.0, 1.8)
        th = rng.uniform(0, math.pi)
        ca, sa = math.cos(th), math.sin(th)

        def gp(sig, cx=cx, cz=cz, R=R, el=el, ca=ca, sa=sa):
            u, v = rng.normal(0, sig * R * el), rng.normal(0, sig * R)
            return cx + u * ca - v * sa, cz + u * sa + v * ca
        nt = int(rng.integers(FILL_GROVE_TREES[0], FILL_GROVE_TREES[1] + 1))
        got = 0
        for _ in range(nt * 5):
            if got >= nt:
                break
            nm = ["dead_tree_a", "dead_tree_a", "dead_tree_b", "dead_tree_c", "dead_tree_b"][int(rng.integers(0, 5))]
            x, z = gp(0.45)
            if P.put(nm, x, z, s=rng.uniform(0.9, 1.3), stamp=("leaves", 2.4)):
                got += 1
        ntr += got
        for _ in range(int(nt * 1.6)):
            x, z = gp(0.6)
            nm = "bramble" if rng.random() < 0.55 else "bush_dead"
            P.put(nm, x, z, s=rng.uniform(1.0, 1.45), stamp=("leaves", 1.6))
        for _ in range(int(rng.integers(0, 3))):
            x, z = gp(0.5)
            P.put("log_fallen", x, z, s=rng.uniform(0.85, 1.15), stamp=("leaves", 1.4), ground="box")
        for _ in range(int(rng.integers(1, 4))):
            x, z = gp(0.55)
            P.put("stump", x, z)
        if rng.random() < 0.5:
            x, z = gp(0.4)
            P.put("roots", x, z)
        # v3 검토 반영: 들판 앞쪽에 보이는 빛이 적었다. 나무 무리마다 발광 버섯 무리, 반쯤은 약한 떠도는 빛
        for q in range(1 + (rng.random() < 0.35)):              # 발광 버섯 무리 (그루터기·통나무 둘레)
            x, z = gp(0.4)
            for q2 in range(int(rng.integers(3, 7))):
                P.put("mushroom_glow" if rng.random() < 0.7 else "mushroom_toxic", x + rng.normal(0, 1.1), z + rng.normal(0, 1.1))
        if rng.random() < FILL_WISP_GROVE:
            x, z = gp(0.3)
            field_wisp(W, P, rng, x, z)
        if rng.random() < FILL_GROVE_FIRE:                          # w4: 버려진 모닥불 (등대 빛. 차가운 밤 들판의 따뜻한 점)
            x, z = gp(0.35)
            if P.put("campfire", x, z, slope=0.25, stamp=("ash", 1.2)):
                yb = rng.uniform(0, 360)
                for sd in (-1, 1):
                    t_ = math.radians(yb + 90 * sd)
                    P.put("log_fallen", x + math.sin(t_) * 2.3, z + math.cos(t_) * 2.3, yaw=yb + rng.normal(0, 8), s=0.7, ground="box")
                P.put("skull", x + rng.normal(0, 1.4), z + rng.normal(0, 1.4))
                P.stamps.append((x, z, 2.4, "dirt"))
        P.stamps.append((cx, cz, R * 0.85, "leaves"))
        P.stamps.append((cx + rng.normal(0, R * 0.3), cz + rng.normal(0, R * 0.3), R * 0.5, "moss"))
        F.items.append({"t": "grove", "p": [round(cx, 1), round(cz, 1)], "r": round(R * el, 1), "trees": got})

    # 5) 바위 노두 (언덕 마루·능선·비탈)
    wo = W.crest * 1.4 + ss(W.slope, 0.18, 0.4) * (W.slope < 0.6) * 0.6
    wo = wo * (W.mount < 0.1) * (1 - ss(W.forest_plan, 0.1, 0.3))
    outs = fill_pick(W, P, rng, wo.astype(np.float32), FILL_OUTCROPS, FILL_OUTCROP_GAP, avoid_scene=12.0, road_min=8.0)
    for (cx, cz) in outs:
        gx_, gz_ = sample(W.gx, cx, cz), sample(W.gz, cx, cz)
        down = yaw_to(-gx_, -gz_) if abs(gx_) + abs(gz_) > 1e-3 else rng.uniform(0, 360)
        main = [("cliff_c", 0.24, 0.36), ("cliff_a", 0.26, 0.38), ("cliff_b", 0.19, 0.26), ("cliff_c", 0.24, 0.36)][int(rng.integers(0, 4))]
        s = rng.uniform(main[1], main[2])
        hgt = (P.meta.get(main[0], {}).get("_size") or [1, 1, 8])[2] * s
        ok = P.put(main[0], cx, cz, yaw=down + rng.normal(0, 12), s=s, slope=None, align=0.5, align_max=18, ground="box",
                   ground_margin=max(0.3, hgt * 0.28), stamp=("rock", 1.5))
        if not ok:
            ok = P.put("rock_b", cx, cz, yaw=down, s=rng.uniform(1.2, 1.5), slope=None, ground="box", align_max=30, stamp=("rock", 1.6))
        if not ok:
            continue
        nb = 0
        for q in range(int(rng.integers(3, 6))):
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(3.0, 7.5)
            nm = "rock_b" if rng.random() < 0.55 else "rock_flat"
            if P.put(nm, cx + math.cos(a) * d, cz + math.sin(a) * d, yaw=down + rng.normal(0, 25), slope=None, ground="box",
                     align_max=35, stamp=("rock", 1.3)):
                nb += 1
        for q in range(int(rng.integers(3, 7))):
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(2.0, 10.0)
            P.put("rock_a" if rng.random() < 0.4 else "rock_c", cx + math.cos(a) * d, cz + math.sin(a) * d, slope=0.5)
        P.stamps.append((cx, cz, rng.uniform(5.0, 8.0), "rock"))
        P.stamps.append((cx + rng.normal(0, 4), cz + rng.normal(0, 4), rng.uniform(4.0, 6.0), "moss"))
        if rng.random() < 0.5:                                     # 바위 그늘의 발광 버섯
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(2.5, 5.0)
            for q in range(int(rng.integers(3, 6))):
                P.put("mushroom_glow" if rng.random() < 0.6 else "mushroom_toxic", cx + math.cos(a) * d + rng.normal(0, 1.0),
                      cz + math.sin(a) * d + rng.normal(0, 1.0))
        F.items.append({"t": "outcrop", "p": [round(cx, 1), round(cz, 1)], "main": main[0], "h": round(hgt * 0.72, 2)})

    # 5b) 작은 덩이: 바위 덩이(비탈·마루), 덤불 덩이(움푹한 곳), 쓰러진 나무 자리(그루터기·뿌리·통나무). 가까이서만 보이는 값싼 소품
    wc = open_ * (0.4 + W.hollow + W.crest + 0.6 * ss(W.slope, 0.1, 0.3))
    clumps = fill_pick(W, P, rng, wc.astype(np.float32), FILL_CLUMPS, FILL_CLUMP_GAP, avoid_scene=8.0, road_min=6.0)
    ncl = collections.Counter()
    for (cx, cz) in clumps:
        hv, cv = sample(W.hollow, cx, cz), sample(W.crest, cx, cz) + 0.6 * ssf(sample(W.slope, cx, cz), 0.12, 0.3)
        r_ = rng.random() * (1 + hv + cv)
        if r_ < cv + 0.35:
            t = "boulders"
            got = 0
            if rng.random() < 0.45:
                got += P.put("rock_b" if rng.random() < 0.5 else "rock_flat", cx, cz, s=rng.uniform(0.75, 1.1), slope=None, ground="box", align_max=30,
                             stamp=("rock", 1.2))
            for q in range(int(rng.integers(2, 5))):
                got += P.put("rock_a" if rng.random() < 0.6 else "rock_c", cx + rng.normal(0, 1.8), cz + rng.normal(0, 1.8),
                             s=rng.uniform(0.9, 1.45), slope=0.32)
        elif r_ < cv + 0.35 + hv + 0.45:
            t = "thicket"
            got = 0
            for q in range(int(rng.integers(3, 6))):
                got += P.put("bush_dead" if rng.random() < 0.75 else "bramble", cx + rng.normal(0, 2.0), cz + rng.normal(0, 2.0),
                             s=rng.uniform(1.2, 1.6), stamp=("leaves", 1.4))
            if rng.random() < 0.3:
                got += P.put("flower_lily", cx + rng.normal(0, 2.5), cz + rng.normal(0, 2.5))
        else:
            t = "deadwood"
            got = P.put("stump", cx, cz, s=rng.uniform(1.0, 1.3))
            got += P.put("roots", cx + rng.normal(0, 1.5), cz + rng.normal(0, 1.5))
            if rng.random() < 0.35:
                got += P.put("log_fallen", cx + rng.normal(0, 2.5), cz + rng.normal(0, 2.5), s=rng.uniform(0.8, 1.05), ground="box")
            if rng.random() < 0.4:
                got += P.put("mushroom_toxic" if rng.random() < 0.4 else "mushroom_glow", cx + rng.normal(0, 1.0), cz + rng.normal(0, 1.0))
        if got:
            ncl[t] += 1
            F.items.append({"t": t, "p": [round(cx, 1), round(cz, 1)], "n": int(got)})

    # 5b2) w4: 무너진 움막·우리 터. 낮은 돌담 토막(× 0.75~0.95, 3.1~3.9 m) 2~4 개가 네모(3.5~5 × 4~6 m)로 둘러서고 한쪽(문·무너진 곳)이 빈다.
    #      안에 돌무더기, 가끔 모서리 선돌(문설주)이나 고목. 들판 어디서 봐도 20~30 m 안에 사람이 살던 흔적이 걸리게
    wh = (open_ * (W.slope < 0.25) * (0.5 + 0.5 * W.hollow + 0.3 * W.crest)).astype(np.float32)
    huts = fill_pick(W, P, rng, wh, FILL_HUTS, FILL_HUT_GAP, avoid_scene=12.0, avoid_poi=12.0, road_min=8.0)
    nhut = 0
    for (cx, cz) in huts:
        gx_, gz_ = sample(W.gx, cx, cz), sample(W.gz, cx, cz)
        base = along_yaw(-gz_, gx_) if abs(gx_) + abs(gz_) > 0.02 else rng.uniform(0, 360)    # 긴 벽이 등고선을 따라
        base += rng.normal(0, 12)
        hw_, hd_ = rng.uniform(1.8, 2.5), rng.uniform(2.0, 3.0)
        t_ = math.radians(base)
        ax_, az_ = math.cos(t_), -math.sin(t_)             # 로컬 X (along_yaw 의 긴 축) 방향
        bx_, bz_ = -az_, ax_
        sides = [(0, hd_, base), (0, -hd_, base + 180), (hw_, 0, base + 90), (-hw_, 0, base - 90)]
        miss = int(rng.integers(0, 4))
        got = 0
        for k_, (u, v, yw) in enumerate(sides):
            if k_ == miss or (got >= 2 and rng.random() < 0.25):
                continue
            px, pz = cx + ax_ * u + bx_ * v, cz + az_ * u + bz_ * v
            n0 = len(P.objects)
            sc_ = rng.uniform(0.75, 0.95)
            if P.put("stone_wall_low", px, pz, yaw=yw + (180 if rng.random() < 0.5 else 0) + rng.normal(0, 4), s=sc_, slope=0.3, ground="box",
                     align=1.0, align_max=FILL_WALL_LEAN, bury_max=FILL_WALL_BURY, ground_margin=rng.uniform(0.0, 0.15), pad=False, r=0.9) \
                    and len(P.objects) > n0:
                P.objects[-1]["cull"] = SINGLE_CULL
                got += 1
        if got == 0:
            continue
        for q in range(int(rng.integers(1, 3))):
            P.put("rubble" if rng.random() < 0.6 else "rock_c", cx + rng.normal(0, 0.8), cz + rng.normal(0, 0.8), s=rng.uniform(0.8, 1.2), slope=0.5)
        if rng.random() < 0.35:
            sd = 1 if rng.random() < 0.5 else -1
            n0 = len(P.objects)
            if P.put("standing_stone", cx + ax_ * hw_ * sd + bx_ * (hd_ + 0.4), cz + az_ * hw_ * sd + bz_ * (hd_ + 0.4), s=rng.uniform(0.4, 0.55),
                     slope=0.4, tilt=8, ground="box", ground_margin=0.1, bury_max=0.4, pad=False) and len(P.objects) > n0:
                P.objects[-1]["cull"] = SINGLE_CULL
        elif rng.random() < 0.25:
            P.put("dead_tree_b" if rng.random() < 0.5 else "dead_tree_c", cx + rng.normal(0, 4.5), cz + rng.normal(0, 4.5), s=rng.uniform(0.85, 1.1))
        P.stamps.append((cx, cz, rng.uniform(3.0, 4.2), "dirt"))
        F.items.append({"t": "hut", "p": [round(cx, 1), round(cz, 1)], "n": int(got)})
        nhut += 1
    log("  움막 터 %d" % nhut)

    # 5c) 낱개: 줄 가장자리·도랑 둑·움푹한 곳·마루·비탈 꺾이는 곳에 큰 덤불·큰 바위·돌무더기·그루터기 하나씩.
    #     짧은 거리(80~260 m)에서 사라지는 값싼 소품이라 그리는 물체 수에는 적게 든다. 눈높이 20~40 m 마다 무엇인가 걸리게
    fill_singles(W, P, rng, F, open_)

    # 6) 작은 무덤 둔덕·외딴 선돌·선돌 줄 (장면 '선돌 무덤 둔덕' 150 m 안에는 두지 않는다)
    barrow_sc = [s_["p"] for s_ in W.scenes if s_["type"] == "barrow"]
    far_barrow = lambda x, z: all((x - a) ** 2 + (z - b) ** 2 > 150 ** 2 for a, b in barrow_sc)
    wb = (W.crest + 0.5 * ss(-W.slope, -0.2, -0.05)) * open_
    bars = fill_pick(W, P, rng, wb.astype(np.float32), FILL_BARROWS * 3, 130.0, avoid_scene=25.0, road_min=12.0, extra_ok=far_barrow)
    upright = np.array([(o["p"][0], o["p"][2]) for o in P.objects if o["a"] in ("stone_wall_low", "iron_fence", "standing_stone", "fence")]) \
        if P.objects else np.zeros((0, 2))
    for (cx, cz) in bars:
        if sum(1 for it in F.items if it["t"] == "barrow") >= FILL_BARROWS:
            break
        R = rng.uniform(6.5, 8.5)
        if len(upright) and np.min((upright[:, 0] - cx) ** 2 + (upright[:, 1] - cz) ** 2) < (R + 3.0) ** 2:
            continue                                    # w4: 먼저 세운 돌담·울타리·선돌이 둔덕에 한쪽만 묻히지 않게
        if not P.terraform(cx, cz, 0.0, R, "mound", rng.uniform(0.9, 1.35), max_slope=0.55):
            continue
        fy = rng.uniform(0, 360)
        t = math.radians(fy)
        hx, hz = cx + math.sin(t) * R * 0.55, cz + math.cos(t) * R * 0.55
        P.put("standing_stone", hx, hz, yaw=fy + rng.normal(0, 8), s=rng.uniform(0.55, 0.72), slope=None, ground="box", ground_margin=0.35)
        P.put("grave_sunken", cx + rng.normal(0, 0.6), cz + rng.normal(0, 0.6), yaw=fy, s=rng.uniform(0.95, 1.15), slope=0.6)
        # w4: 둔덕 발치의 작은 선돌 고리 (1.3~1.9 m, 몇은 빠지고 몇은 기울었다). 장면 '선돌 무덤 둔덕'보다 작고 성기다
        nr = int(rng.integers(6, 10))
        a0 = rng.uniform(0, 2 * math.pi)
        for q in range(nr):
            if rng.random() < 0.2:
                continue
            a = a0 + (q + rng.uniform(-0.15, 0.15)) / nr * 2 * math.pi
            rx_, rz_ = cx + math.cos(a) * (R + 0.6), cz + math.sin(a) * (R + 0.6)
            if (rx_ - hx) ** 2 + (rz_ - hz) ** 2 < 2.5 ** 2:
                continue
            P.put("standing_stone", rx_, rz_, yaw=yaw_to(cx - rx_, cz - rz_) + rng.normal(0, 10), s=rng.uniform(0.42, 0.6),
                  slope=0.5, ground="box", ground_margin=0.15, tilt=16 if rng.random() < 0.25 else None, bury_max=0.4)
        for q in range(int(rng.integers(2, 4))):
            a = rng.uniform(0, 2 * math.pi)
            P.put("rock_c", cx + math.cos(a) * R * 0.8, cz + math.sin(a) * R * 0.8, s=rng.uniform(0.9, 1.3), slope=0.6)
        for q in range(int(rng.integers(1, 3))):
            P.put("skull", cx + rng.normal(0, 2.5), cz + rng.normal(0, 2.5), slope=0.6)
        for q in range(int(rng.integers(2, 5))):
            a = rng.uniform(0, 2 * math.pi)
            P.put("flower_lily", cx + math.cos(a) * (R + 0.8), cz + math.sin(a) * (R + 0.8))
        for q in range(int(rng.integers(2, 4))):                 # 선돌 발치의 초 (발광 부품)
            P.put("candles", hx + rng.normal(0, 0.7), hz + rng.normal(0, 0.7), slope=0.6)
        field_wisp(W, P, rng, cx, cz, up=(1.8, 2.4))
        P.reserve(cx, cz, R * 0.7)
        P.stamps.append((cx, cz, R * 0.9, "moss"))
        F.items.append({"t": "barrow", "p": [round(cx, 1), round(cz, 1)], "r": round(R, 1)})
    ws = (W.crest * 1.5 + 0.2) * open_
    stones = fill_pick(W, P, rng, ws.astype(np.float32), FILL_STONES, 95.0, avoid_scene=20.0, road_min=10.0)
    for (cx, cz) in stones:
        s = rng.uniform(0.85, 1.2)
        if P.put("standing_stone", cx, cz, yaw=rng.uniform(0, 360), s=s, slope=0.45, ground="box", ground_margin=0.45):
            for q in range(int(rng.integers(1, 3))):
                P.put("rock_c", cx + rng.normal(0, 1.6), cz + rng.normal(0, 1.6), slope=0.6)
            F.items.append({"t": "stone", "p": [round(cx, 1), round(cz, 1)], "s": round(s, 2)})
    rows = fill_pick(W, P, rng, ws.astype(np.float32), FILL_ROWS, FILL_ROW_GAP, avoid_scene=25.0, road_min=14.0)
    for (cx, cz) in rows:
        gx_, gz_ = sample(W.gx, cx, cz), sample(W.gz, cx, cz)
        tv = np.array([-gz_, gx_]) if abs(gx_) + abs(gz_) > 1e-3 else np.array([1.0, 0.0])
        tv /= np.linalg.norm(tv) + 1e-9
        n = int(rng.integers(4, 7))
        sp = rng.uniform(4.0, 6.0)
        got = 0
        for q in range(n):
            o = (q - (n - 1) / 2) * sp
            x, z = cx + tv[0] * o + rng.normal(0, 0.4), cz + tv[1] * o + rng.normal(0, 0.4)
            if P.put("standing_stone", x, z, yaw=along_yaw(*tv) + rng.normal(0, 10), s=rng.uniform(0.45, 0.7) * (1.15 if q == n // 2 else 1.0),
                     slope=0.45, ground="box", ground_margin=0.25, bury_max=0.4):
                got += 1
        if got:
            F.items.append({"t": "stone_row", "p": [round(cx, 1), round(cz, 1)], "n": got})
            for q in range(int(rng.integers(4, 8))):                  # 선돌 발치 발광 버섯
                o = (rng.uniform(-0.5, 0.5) * n) * sp
                P.put("mushroom_glow", cx + tv[0] * o + rng.normal(0, 1.0), cz + tv[1] * o + rng.normal(0, 1.0))
            field_wisp(W, P, rng, cx, cz)

    # 6b) w4: 들판 전장 흔적 깃발 (언덕 마루·능선). 찢긴 깃발 1~2 (4~5 m 세로 실루엣) + 발치의 쓰러진 전사·해골
    wfl = ((W.crest * 1.3 + 0.3 * ss(W.slope, 0.05, 0.2) + 0.15) * open_).astype(np.float32)
    flags = fill_pick(W, P, rng, wfl, FILL_BANNERS, 110.0, avoid_scene=25.0, road_min=12.0)
    nflag = 0
    for (cx, cz) in flags:
        got = 0
        for q in range(1 + (rng.random() < 0.45)):
            x, z = (cx, cz) if q == 0 else (cx + rng.normal(0, 3.0), cz + rng.normal(0, 3.0))
            got += P.put("banner_torn", x, z, s=rng.uniform(0.95, 1.2), slope=0.4, tilt=11)
        if not got:
            continue
        for q in range(int(rng.integers(1, 3))):
            P.put("skeleton_remains", cx + rng.normal(0, 2.4), cz + rng.normal(0, 2.4), slope=0.5)
        for q in range(int(rng.integers(1, 4))):
            P.put("skull", cx + rng.normal(0, 3.0), cz + rng.normal(0, 3.0), slope=0.6)
        P.put("rubble" if rng.random() < 0.5 else "rock_c", cx + rng.normal(0, 2.5), cz + rng.normal(0, 2.5), slope=0.6)
        P.stamps.append((cx, cz, rng.uniform(2.5, 3.8), "dirt"))
        F.items.append({"t": "banner", "p": [round(cx, 1), round(cz, 1)], "n": int(got)})
        nflag += 1
    # 6c) w4: 들판 영혼 수정 무리 (움푹한 곳·도랑 가). 큰 수정 하나가 등대 빛, 곁의 작은 수정은 가까이서만 켠다 (SMALL_GLOW_FAR).
    #     장소 둘레(광원이 몰린 곳)는 피한다
    wcr = ((W.hollow * 1.5 + 0.1) * open_ * (W.slope < 0.3)).astype(np.float32)
    crys = fill_pick(W, P, rng, wcr, FILL_CRYSTALS, 150.0, avoid_scene=30.0, avoid_poi=110.0, road_min=14.0)
    ncry = 0
    for (cx, cz) in crys:
        if not P.put("soul_crystal", cx, cz, s=rng.uniform(0.9, 1.15), slope=0.3, stamp=("rock", 1.3)):
            continue
        for q in range(int(rng.integers(1, 3))):
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(1.9, 3.2)
            n0 = len(P.objects)
            if P.put("soul_crystal", cx + math.cos(a) * d, cz + math.sin(a) * d, s=rng.uniform(0.6, 0.78), slope=0.4) and len(P.objects) > n0:
                P.objects[-1]["far"] = SMALL_GLOW_FAR
        for q in range(int(rng.integers(1, 3))):
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(3.0, 5.5)
            P.put("rock_b" if rng.random() < 0.5 else "rock_flat", cx + math.cos(a) * d, cz + math.sin(a) * d, s=rng.uniform(0.7, 1.0), slope=None,
                  ground="box", align_max=30, stamp=("rock", 1.2))
        for q in range(int(rng.integers(3, 6))):
            P.put("mushroom_glow", cx + rng.normal(0, 2.2), cz + rng.normal(0, 2.2))
        W.fx.append({"type": "wisps", "p": [float(cx), P.height(cx, cz) + 1.0, float(cz)], "r": 6})
        P.stamps.append((cx, cz, 4.0, "moss"))
        F.items.append({"t": "crystal", "p": [round(cx, 1), round(cz, 1)]})
        ncry += 1
    log("  들판 깃발 %d, 들판 수정 무리 %d" % (nflag, ncry))

    # 7) 마른 도랑: 바닥 돌·둑의 뿌리·덤불·유령 백합
    for dt in W.ditches:
        c, L = dt["pts"], dt["L"]
        pos = rng.uniform(4, 10)
        nd = 0
        while pos < L - 4:
            k = min(int(pos / 2.0), len(c) - 2)
            x, z = c[k]
            tv = c[k + 1] - c[k]
            tv /= np.linalg.norm(tv) + 1e-9
            nv = np.array([-tv[1], tv[0]])
            r_ = rng.random()
            if r_ < 0.45:
                if P.put("rock_flat" if rng.random() < 0.4 else "rock_c", x + rng.normal(0, 0.4), z + rng.normal(0, 0.4),
                         s=rng.uniform(0.55, 0.8) if rng.random() < 0.4 else None, slope=None, ground="box", align_max=30):
                    nd += 1
            elif r_ < 0.7:
                sd = 1 if rng.random() < 0.5 else -1
                bx_, bz_ = np.array([x, z]) + nv * sd * (1.5 + dt["D"] * 3.0)
                P.put(["roots", "bramble", "bush_dead"][int(rng.integers(0, 3))], bx_, bz_, slope=0.6)
                nd += 1
            elif r_ < 0.88:
                sd = 1 if rng.random() < 0.5 else -1
                bx_, bz_ = np.array([x, z]) + nv * sd * (1.2 + dt["D"] * 2.0)
                for q in range(int(rng.integers(1, 3))):
                    P.put("flower_lily", bx_ + rng.normal(0, 0.6), bz_ + rng.normal(0, 0.6), slope=0.7)
                nd += 1
            pos += rng.uniform(7, 13)
        F.lines.append({"t": "ditch", "src": "relief", "pts": [[round(float(a), 1), round(float(b), 1)] for a, b in c[::5]], "L": round(L, 1),
                        "D": round(dt["D"], 2)})

    # 8) 장면 둘레 유령 백합·불·전장 장면 둘레 재, 늪·호수·개울가 꽃
    for s_ in W.scenes:
        R = s_["r"]
        for q in range(int(rng.integers(2, 5))):
            a = rng.uniform(0, 2 * math.pi)
            P.put("flower_lily", s_["p"][0] + math.cos(a) * (R + rng.uniform(1, 4)), s_["p"][1] + math.sin(a) * (R + rng.uniform(1, 4)))
        if s_["type"] in ("battle", "pyre", "camp", "execution", "crossroad"):
            for q in range(int(rng.integers(3, 7))):
                a, d = rng.uniform(0, 2 * math.pi), rng.uniform(0, R + 3)
                P.stamps.append((s_["p"][0] + math.cos(a) * d, s_["p"][1] + math.sin(a) * d, rng.uniform(1.4, 3.4), "ash"))
    shore = 0
    for _ in range(900):
        if shore >= 60:
            break
        if rng.random() < 0.55:
            a = rng.uniform(0, 2 * math.pi)
            x, z = SWAMP[0] + math.cos(a) * rng.uniform(SWAMP_R - 40, SWAMP_R + 25), SWAMP[1] + math.sin(a) * rng.uniform(SWAMP_R - 40, SWAMP_R + 25)
            lev = W.swamp_level
        else:
            (z0, z1), (x0, x1) = W.creek_win
            x, z = rng.uniform(x0, x1 - 1), rng.uniform(z0, z1 - 1)
            lev = W.pool_level if W.in_pool(x, z) else None
            ci, cj = int(z - z0), int(x - x0)
            cd = float(W.creek_dist[ci, cj] - W.creek_wt[ci, cj])
            if not (0.5 < cd < 5.0):
                continue
        hh = P.height(x, z)
        if lev is not None and not (lev + 0.1 < hh < lev + 2.0):
            continue
        if P.put("flower_lily", x, z, slope=0.6):
            shore += 1
    F.items.extend(getattr(W, "foot_items", []))         # 벼랑 밑동 바위 무리 (lay_mountain_foot)
    P.rng = main_rng
    W.fill = F
    log("  작은 덩이:", dict(ncl))
    log("채움: 줄 소품 %s, 밭 줄 구간 %d · 길가·뻗는 줄 구간 %d (뻗는 줄 %d), 나무 무리 %d (고목 %d), 바위 노두 %d, 작은 둔덕 %d, 선돌 %d, 선돌 줄 %d, "
        "이정표 %d, 사당 %d, 수레 %d, 도랑 %d, 물가 꽃 %d, %.1f 초" % (
            dict(F.n), sum(1 for l_ in F.lines if l_["src"] in ("field", "cross")), sum(1 for l_ in F.lines if l_["src"] in ("road", "spur")), nspur,
            len(groves), ntr, sum(1 for it in F.items if it["t"] == "outcrop"), sum(1 for it in F.items if it["t"] == "barrow"),
            sum(1 for it in F.items if it["t"] == "stone"), sum(1 for it in F.items if it["t"] == "stone_row"), nmile, nshr, ncart,
            len(W.ditches), shore, time.time() - t0))


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
    # v3: 장소 등대 빛 (LightCuller 가 140~160 m 까지 켜 둔다): 묘지 가운데 천사상, 납골당 앞, 영혼의 고목, 다리 웅덩이
    for (x, z, up, c, far) in ((GRAVE_C[0], GRAVE_C[1], 4.2, SOUL, 150.0), (CRYPT[0], CRYPT[1] - 10, 2.6, SOUL, 150.0),
                               (TREE[0] - 3, TREE[1] - 4, 7.0, SPIRIT, 160.0), (W.bridge_p[0], W.bridge_p[1], 3.0, SPIRIT, FAR)):
        y = max(P.height(x, z), W.pool_level if W.in_pool(x, z) else -1e9) + up
        W.lights.append({"p": [round(x, 2), round(y, 2), round(z, 2)], "c": c, "i": 4.0, "r": 8.0, "flicker": True, "far": far})
    # 제단·묘지 광원
    for i in range(6):
        a = i / 6 * 2 * math.pi
        x, z = ALTAR[0] + math.cos(a) * 9, ALTAR[1] + math.sin(a) * 9
        W.lights.append({"p": [round(x, 2), round(P.height(x, z) + 2.2, 2), round(z, 2)], "c": SOUL, "i": 3.0, "r": 8.0, "flicker": True})


BEACON_LAMP = "lantern"        # 발광 소품이 없는 등대 빛 자리에 두는 발광 소품 (새 소품 화로·영혼 수정·사당이 생기면 그 소품이 맡는다)
BEACON_EMIT_H = 0.9            # 등대 빛을 맡길 발광 소품의 최소 키 (m). 초·버섯·연꽃은 100 m 밖에서 점 하나라 맡기지 않는다
BEACON_NEAR = 1.6              # 등대 빛과 발광 소품 광원 사이 최대 거리 (m, 땅 위 평면)
# w4: 장면 틀마다 등대 빛을 맡을 발광 소품 (없으면 BEACON_LAMP). 같은 등불이 장면마다 되풀이되지 않게 진짜 화로·영혼 수정을 쓴다
BEACON_BY_SCENE = {"barrow": ("soul_crystal", (0.85, 1.0)), "battle": ("brazier", None), "chapel": ("brazier", None),
                   "pyre": ("brazier", None), "crossroad": ("brazier", None)}


def beacon_emitters(W, P):
    """v3 검토 반영: Unity 점광원은 광원 자체가 화면에 보이지 않는다 (밝혀진 땅만 보인다). 그래서 등대 빛(far)은 반드시
    발광 부품이 있는 소품의 광원이어야 한다. 따로 놓은 등대 빛(objects.json lights 의 far)마다:
      1) BEACON_NEAR 안에 키 BEACON_EMIT_H 넘는 발광 소품의 광원이 있으면 그 소품에 far 를 넘기고 (objects[].far) 따로 놓은 빛은 뺀다
      2) 없으면 그 자리 둘레에 등불(BEACON_LAMP)을 두고 far 를 넘긴다
      3) 둘 다 안 되면: 물 위(늪·호수의 도깨비불)는 등대 빛을 그만두고 (far 를 빼서) 보통 도깨비불로 남긴다. 그 밖은 남기고 센다 (목표 0)
    w4: 장면의 등대 빛은 틀마다 다른 발광 소품(BEACON_BY_SCENE: 무덤 둔덕 = 영혼 수정, 전장·예배당·화장터 = 화로)이 맡는다.
    장면 기록(_scenes.json)의 beacon 자리도 고친다"""
    emit = []
    for k, o in enumerate(P.objects):
        m = P.meta.get(o["a"], {})
        lt = m.get("light")
        if not lt or m.get("kind") == "tree":
            continue
        hz = (m.get("_size") or [0, 0, 0])[2] * o["s"]
        if hz < BEACON_EMIT_H:
            continue
        q = quat_mat(o["q"])
        ox, oy, oz = -lt["offset"][0] * o["s"], lt["offset"][2] * o["s"], -lt["offset"][1] * o["s"]   # 소품 Blender 축 (x, y, z) → Unity 로컬 (−x, z, −y) (SPEC C_o)
        wx = q[0, 0] * ox + q[0, 1] * oy + q[0, 2] * oz
        wz = q[2, 0] * ox + q[2, 1] * oy + q[2, 2] * oz
        wy = q[1, 0] * ox + q[1, 1] * oy + q[1, 2] * oz
        emit.append((o["p"][0] + wx, o["p"][1] + wy, o["p"][2] + wz, k))
    E = np.array([(a, c) for a, b, c, k in emit], np.float64) if emit else np.zeros((0, 2))
    keep, moved, lamps, bare, wet = [], 0, collections.Counter(), [], 0
    rng = P.rng
    scene_by_beacon = {}
    for sc_ in W.scenes:
        if sc_.get("beacon"):
            scene_by_beacon[(round(sc_["beacon"][0], 1), round(sc_["beacon"][2], 1))] = sc_
    for l in W.lights:
        if not l.get("far"):
            keep.append(l)
            continue
        x, y, z = l["p"]
        new_b = None
        if len(E):
            d2 = (E[:, 0] - x) ** 2 + (E[:, 1] - z) ** 2
            j = int(np.argmin(d2))
            if d2[j] <= BEACON_NEAR ** 2:
                o = P.objects[emit[j][3]]
                o["far"] = max(float(o.get("far", 0.0)), float(l["far"]))
                new_b = (emit[j][0], emit[j][1], emit[j][2], o["far"])
                moved += 1
        sc_ = scene_by_beacon.get((round(x, 1), round(z, 1)))
        if new_b is None:
            spots = [(0.0, 0.0)] + [(math.cos(t) * r_, math.sin(t) * r_) for r_, n_ in ((1.0, 6), (2.0, 8), (3.2, 10), (5.0, 12), (7.5, 14),
                                                                                       (10.0, 16), (12.5, 18))
                                     for t in np.linspace(0, 2 * math.pi, n_, endpoint=False) + rng.uniform(0, 1)]
            pref, psc = BEACON_BY_SCENE.get(sc_["type"], (BEACON_LAMP, None)) if sc_ is not None else (BEACON_LAMP, None)
            if pref not in P.meta:
                pref, psc = BEACON_LAMP, None
            ok = False
            for lamp in ([pref, BEACON_LAMP] if pref != BEACON_LAMP else [BEACON_LAMP]):
                for chk in (True, False):
                    for (dx, dz) in spots:
                        px, pz = x + dx, z + dz
                        if not chk and not P.ok_ground(px, pz, 0.5, True, True, 0.6):
                            continue
                        n0 = len(P.objects)
                        s_ = rng.uniform(*psc) if (psc and lamp == pref) else None
                        if P.put(lamp, px, pz, yaw=rng.uniform(0, 360), s=s_, slope=0.6, check=chk) and len(P.objects) > n0:
                            o = P.objects[-1]
                            o["far"] = float(l["far"])
                            lt = P.meta[lamp]["light"]
                            new_b = (o["p"][0], o["p"][1] + lt["offset"][2] * o["s"], o["p"][2], o["far"])
                            ok = True
                            break
                    if ok:
                        break
                if ok:
                    break
            if ok:
                lamps[lamp] += 1
            elif P.under_water(x, z, 0.0) or P.under_water(x, z, 0.6):
                l.pop("far", None)                     # 물 위 도깨비불: 등대 빛을 그만두고 보통 빛으로
                keep.append(l)
                wet += 1
                continue
            else:
                keep.append(l)
                bare.append((round(x, 1), round(z, 1)))
                continue
        if sc_ is not None and new_b is not None:
            sc_["beacon"] = [round(float(v), 2) for v in new_b]
    W.lights = keep
    log("등대 빛 발광체: 발광 소품에 넘김 %d, 발광 소품을 둠 %d %s, 물 위라 보통 빛으로 %d, 발광체 없이 남은 등대 빛 %d %s" % (
        moved, sum(lamps.values()), dict(lamps), wet, len(bare), bare[:6]))


# w4: 월드에서 소품이 사라지는 화면 높이(LODGroup 마지막 전환 높이)를 META.cull 보다 크게 덮어쓴다 (objects[].cull, SPEC.md).
# 진짜 돌담·깃발·선돌이 META.cull 로 700~1000 m 까지 그려져 숲 가장자리에서 그리는 물체 수(예산 2,000)를 넘겼다.
# 그 거리에서는 몇 화소라 보이지 않는다. 값 → 크기 1 에서 사라지는 거리: 돌담 4.14 / (1.04 × 0.012) ≈ 330 m, 깃발 ≈ 510 m,
# 선돌 ≈ 435 m, 쓰러진 나무 ≈ 320 m, 큰 바위 ≈ 380 m, 낮은 기둥 ≈ 320 m
WORLD_CULL = {"stone_wall_low": 0.012, "banner_torn": 0.008, "standing_stone": 0.007, "log_fallen": 0.016, "rock_b": 0.01, "pillar_a": 0.012}

LIGHT_TRIM = {"candles": 0, "mushroom_glow": 0, "mushroom_toxic": 0, "lotus_glow": 1}   # 광원 예산을 넘는 곳에서 먼저 빼는 작은 광원
# LightCuller 정책 (Assets/_Necro/Scripts/World/LightCuller.cs 기본값과 맞춘다): 광원마다 끄는 거리 = far(있으면) 또는
# clamp(range × 12, 30, 200). 그 거리 안의 광원이 '켜 둘 후보'이고, 후보가 maxActive(48)를 넘으면 (거리/끄는 거리) 비율이 큰 것부터 꺼진다
CULL_FACTOR, CULL_MIN, CULL_MAX, CULL_ACTIVE, CULL_HYST = 12.0, 30.0, 200.0, 48, 10.0


def cull_radius(rng_, far):
    return float(min(max(far, CULL_MIN), CULL_MAX)) if far else float(min(max(rng_ * CULL_FACTOR, CULL_MIN), CULL_MAX))


def trim_lights(W, P, limit=46, step=4.0):
    """LightCuller 예산: 걸을 수 있는 범위의 4 m 격자 어디서도 '켜 둘 후보'(끄는 거리 + 여유 10 m 안의 광원: 켜진 광원은 여유까지 남는다)가
    limit(46, maxActive 48 에 2 개 여유) 를 넘지 않게
    작은 광원 소품(초·버섯·연꽃)을 몰린 곳에서부터 뺀다. 등불·화로·수정·랜드마크·따로 놓은 광원(등대 빛 포함)은 빼지 않는다.
    v3: v2 는 모든 광원을 반지름 80 m 로 셌다. 실제 LightCuller 는 광원마다 끄는 거리가 달라(등대 빛 140 m, 초 48 m) 그대로 흉내 낸다"""
    rng = P.rng
    (bx0, bz0), (bx1, bz1) = BOUNDS
    pos, pri, src, rad = [], [], [], []
    for k, o in enumerate(P.objects):
        m = P.meta.get(o["a"], {})
        lt = m.get("light")
        if lt and m.get("kind") != "tree":
            pos.append((o["p"][0], o["p"][2]))
            pri.append(LIGHT_TRIM.get(o["a"], 9))
            src.append(k)
            rad.append(cull_radius(lt.get("range", 8.0), o.get("far") or lt.get("far")) + CULL_HYST)
    for li, l in enumerate(W.lights):
        pos.append((l["p"][0], l["p"][2]))
        pri.append(2 if l.get("weak") else 9)               # 약한 떠도는 빛은 초·버섯 다음으로 뺀다
        src.append(-2 - li)
        rad.append(cull_radius(l["r"], l.get("far")) + CULL_HYST)
    L = np.array(pos, np.float64)
    pri = np.array(pri)
    R2 = np.array(rad) ** 2
    g = np.arange(bx0 + step / 2, bx1, step)
    GX, GZ = np.meshgrid(g, g)
    gx, gz = GX.ravel(), GZ.ravel()
    cnt = np.zeros(len(gx), np.int32)
    n80 = np.zeros(len(gx), np.int32)
    for c0 in range(0, len(gx), 2000):
        d2 = (gx[c0:c0 + 2000, None] - L[None, :, 0]) ** 2 + (gz[c0:c0 + 2000, None] - L[None, :, 1]) ** 2
        cnt[c0:c0 + 2000] = (d2 <= R2[None, :]).sum(1)
        n80[c0:c0 + 2000] = (d2 < 80.0 * 80.0).sum(1)
    before, before80 = int(cnt.max()), int(n80.max())
    alive = np.ones(len(L), bool)
    removed = 0
    while cnt.max() > limit:
        i = int(np.argmax(cnt))
        d2 = (L[:, 0] - gx[i]) ** 2 + (L[:, 1] - gz[i]) ** 2
        cand = np.nonzero(alive & (d2 <= R2) & (pri < 9))[0]
        if len(cand) == 0:
            log("광원 예산: (%.0f, %.0f) 후보 %d 개 — 뺄 수 있는 작은 광원이 없다" % (gx[i], gz[i], cnt[i]))
            break
        lo = cand[pri[cand] == pri[cand].min()]
        j = int(lo[int(rng.integers(0, len(lo)))])
        alive[j] = False
        removed += 1
        dd = (gx - L[j, 0]) ** 2 + (gz - L[j, 1]) ** 2
        cnt -= (dd <= R2[j]).astype(np.int32)
        n80 -= (dd < 6400.0).astype(np.int32)
    dropl = set(-2 - src[j] for j in np.nonzero(~alive)[0] if src[j] <= -2)
    if dropl:
        W.lights = [l for li, l in enumerate(W.lights) if li not in dropl]
    for l in W.lights:
        l.pop("weak", None)
    drop = set(src[j] for j in np.nonzero(~alive)[0] if src[j] >= 0)
    if drop:
        for k in drop:
            a = P.objects[k]["a"]
            P.count[a] -= 1
        # 바닥 상자 기록(_boxground.json)의 번호를 새 순서로 고친다
        keep_idx = [k for k in range(len(P.objects)) if k not in drop]
        remap = {old: new for new, old in enumerate(keep_idx)}
        P.boxed = [(remap[k], f) for (k, f) in P.boxed if k in remap]
        P.objects = [P.objects[k] for k in keep_idx]
    nfar = sum(1 for l in W.lights if l.get("far")) + sum(1 for o in P.objects if (P.meta.get(o["a"], {}).get("light") or {}).get("far") or o.get("far"))
    log("  약한 떠도는 빛 뺌 %d 개" % len(dropl))
    log("광원 예산 (LightCuller 정책 흉내): 켜 둘 후보 최대 %d → %d (작은 광원 %d 개 뺌, 한도 %d / maxActive %d), 80 m 안 최대 %d → %d, "
        "점광원 합 %d, 등대 빛(far) %d" % (before, int(cnt.max()), removed, limit, CULL_ACTIVE, before80, int(n80.max()), int(alive.sum()), nfar))


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
    # v3 채움: 땅 변화 — 움푹한 곳 이끼·진흙, 마루 바위, 마른 도랑 바닥, 밭 턱 비탈의 흙
    paint_fill(W, over, n1, n2, n3)
    over("rock", ss(sl, 0.62, 1.0) + W.mount * ss(sl, 0.32, 0.6) * 0.85)
    path = ss(-W.road_dist, -(W.road_hw + 0.9), -(W.road_hw - 0.6)) * (0.8 + 0.2 * ss(n3, -0.4, 0.4))
    over("path", path)
    # v3 채움: 바퀴 자국 (길 안 두 줄 진흙, 가운데 풀 줄). 길을 따라 있다 없다 한다
    hw = W.road_hw
    gate = ss(fbm(X, Z, 1 / 55.0, 2, 1031), -0.15, 0.25) * (W.road_dist < hw)
    rut = np.exp(-((W.road_dist - 0.42 * hw) / 0.3) ** 2)
    over("mud", rut * gate * 0.55 * (0.7 + 0.3 * ss(n3, -0.4, 0.4)))
    over("moss", ss(-W.road_dist, -0.2 * hw, -0.06 * hw) * gate * 0.45)
    # 소품 자리 칠하기
    stamp_layers(W, P, lw, n3)
    order = [n for n, _, _ in LAYERS]
    tot = sum(lw[n] for n in order) + 1e-6
    for n in order:
        lw[n] = lw[n] / tot
    W.lw = lw


def paint_fill(W, over, n1, n2, n3):
    """v3 채움 땅 변화. 움푹한 곳 = 이끼(깊으면 진흙 얼룩), 마루 = 바위, 마른 도랑 = 진흙·이끼 바닥과 가운데 자갈,
    밭 턱 비탈 = 흙(턱만인 줄은 바위)"""
    hol, crest = W.hollow, W.crest
    over("moss", hol * 0.6 * (0.6 + 0.4 * ss(n3, -0.3, 0.4)))
    over("mud", ss(hol, 0.55, 1.0) * 0.45 * ss(n1, -0.1, 0.35))
    over("rock", crest * 0.6 * ss(n3, -0.25, 0.3))
    acc = {k: np.zeros(W.h.shape, np.float32) for k in ("bank", "bed", "grit", "riser", "scarp")}

    def put(k, z0, z1, x0, x1, v):
        a = acc[k][z0:z1, x0:x1]
        np.maximum(a, v.astype(np.float32), out=a)
    for dt in W.ditches:
        c, L = dt["pts"], dt["L"]
        bank = 0.9 + 1.5 * dt["D"] / 0.42
        (z0, z1), (x0, x1), dist, along = polyline_field(c, bank + 3, RES)
        env = ss(along, 0, 12) * ss(L - along, 0, 18)
        put("bank", z0, z1, x0, x1, (1 - ss(dist, bank * 0.6, bank + 2.5)) * env)
        put("bed", z0, z1, x0, x1, (1 - ss(dist, 0.5, 1.8)) * env)
        put("grit", z0, z1, x0, x1, (1 - ss(dist, 0.0, 0.7)) * env * ss(perlin(along * 0.4, np.full(along.shape, 1.1, np.float32), 1041), -0.1, 0.3))
    Rw = RELIEF_RISER
    for ln in W.relief_lines:
        c = ln["pts"]
        (z0, z1), (x0, x1), dist, along, side = line_field(c, Rw / 2 + 3)
        s = dist * side * ln["up"]
        env = ss(along, 0, 12) * ss(ln["L"] - along, 0, 12) * min(1.0, ln["A"] / 1.0)
        put("scarp" if ln["kind"] == "scarp" else "riser", z0, z1, x0, x1, (1 - ss(np.abs(s + 0.2), Rw * 0.3, Rw * 0.6)) * env)
    over("moss", acc["bank"] * 0.55)
    over("mud", acc["bed"] * 0.65 * (0.7 + 0.3 * ss(n3, -0.3, 0.3)))
    over("rock", acc["grit"] * 0.5)
    over("dirt", acc["riser"] * 0.45 + acc["scarp"] * 0.35)
    over("rock", acc["scarp"] * 0.45 * ss(n2, -0.3, 0.3))
    W.ditch_bed, W.ditch_bank = acc["bed"], acc["bank"]


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
    # v3 채움: 움푹한 곳·도랑 둑은 무성하게, 마루·도랑 바닥은 성기게. 걸을 수 있는 범위의 풀 합은 그대로 (화면 안 풀 포기 예산)
    (bx0, bz0), (bx1, bz1) = BOUNDS
    win = (slice(bz0, bz1), slice(bx0, bx1))
    tot0 = sum(float(d[k][win].sum()) for k in d)
    lush = 1 + 0.6 * W.hollow + 0.5 * W.ditch_bank * (1 - W.ditch_bed) - 0.65 * W.crest - 0.6 * W.ditch_bed
    for k in ("grass_a", "grass_b", "fern_a", "weeds"):
        d[k] = np.clip(d[k] * lush, 0, 1)
    d["grass_dead"] = np.clip(d["grass_dead"] * (1 + 0.35 * W.crest - 0.3 * W.hollow), 0, 1)     # 마루는 마른 풀이 남는다
    tot1 = sum(float(d[k][win].sum()) for k in d)
    kk = tot0 / max(tot1, 1.0)
    for k in d:
        d[k] = np.clip(d[k] * kk, 0, 1)
    log("풀 밀도: 움푹한 곳·도랑 둑 무성, 마루 성김 (합 맞춤 ×%.3f)" % kk)
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
    for o in P.objects:                    # w4: 소품별 컬링 높이 덮어쓰기 (WORLD_CULL, objects[].cull)
        c = WORLD_CULL.get(o["a"])
        if c and "cull" not in o:                # 이미 정한 것(낱개 SINGLE_CULL)은 그대로
            o["cull"] = c
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
        "map": {"min": [BOUNDS[0][0] - MAP_MARGIN, BOUNDS[0][1] - MAP_MARGIN], "max": [BOUNDS[1][0] + MAP_MARGIN, BOUNDS[1][1] + MAP_MARGIN]},
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
    col = np.clip(col, 0, 1)
    # 게임 안 지도: world.json "map" 범위 (걸어 다니는 범위 + MAP_MARGIN). 가장자리는 어둡게 (양피지 느낌)
    mx0, mz0 = BOUNDS[0][0] - MAP_MARGIN, BOUNDS[0][1] - MAP_MARGIN
    mx1, mz1 = BOUNDS[1][0] + MAP_MARGIN, BOUNDS[1][1] + MAP_MARGIN
    mc = col[mz0:mz1, mx0:mx1].copy()
    hx, hz = (mx1 - mx0) / 2.0, (mz1 - mz0) / 2.0
    r = np.sqrt(((W.X[mz0:mz1, mx0:mx1] - (mx0 + hx)) / hx) ** 2 + ((W.Z[mz0:mz1, mx0:mx1] - (mz0 + hz)) / hz) ** 2)
    mc *= (1 - 0.45 * ss(r, 0.95, 1.42))[..., None]
    img = Image.fromarray((np.flipud(np.clip(mc, 0, 1)) * 255).astype(np.uint8), 'RGB').resize((1024, 1024), Image.LANCZOS)
    img.save(os.path.join(out, "map.png"))
    # 확인용 개요도는 지형 전체 (화소 = m). 가장자리 어둡게
    r = np.sqrt(((W.X - 1024) / 1024) ** 2 + ((W.Z - 1024) / 1024) ** 2)
    col = col * (1 - 0.5 * ss(r, 0.85, 1.4))[..., None]
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
    # 조용한 구역 (16 m 칸, 짙은 파랑으로 물들인다)과 무리 (흰 고리)
    zones = getattr(W, "zones", {"hamlets": [], "quiet": []})
    for zz in zones["quiet"]:
        for (qx, qz) in zz["cells"]:
            for u in range(int(qx - 7), int(qx + 7), 2):
                for v in range(int(qz - 7), int(qz + 7), 2):
                    if 0 <= u < SIZE and 0 <= v < SIZE:
                        c0 = px[u, SIZE - 1 - v]
                        px[u, SIZE - 1 - v] = (c0[0] // 2, c0[1] // 2, min(255, c0[2] // 2 + 70))
    for hm in zones["hamlets"]:
        hx_, hz_ = hm["center"]
        for t in range(240):
            a = t / 240 * 2 * math.pi
            u, v = int(hx_ + math.cos(a) * hm["r"]), int(hz_ + math.sin(a) * hm["r"])
            if 0 <= u < SIZE and 0 <= v < SIZE and t % 4 < 2:
                px[u, SIZE - 1 - v] = (255, 255, 255)
    scol = {"execution": (255, 70, 70), "chapel": (120, 200, 255), "shrine": (255, 170, 255), "barrow": (200, 90, 255),
            "camp": (255, 160, 60), "crystal": (80, 255, 230), "family": (255, 255, 255), "battle": (255, 220, 60),
            "outpost": (255, 120, 170), "crossroad": (60, 255, 90), "graves": (190, 190, 190), "farmstead": (170, 120, 60),
            "pyre": (255, 90, 20)}
    for s_ in W.scenes:                       # 장면: 틀별 색 고리 (확인용)
        x, z = int(s_["p"][0]), int(s_["p"][1])
        c = scol.get(s_["type"], (255, 255, 0))
        for t in range(48):
            a = t / 48 * 2 * math.pi
            for rr in (9, 10):
                u, v = int(x + math.cos(a) * rr), int(z + math.sin(a) * rr)
                if 0 <= u < SIZE and 0 <= v < SIZE:
                    px[u, SIZE - 1 - v] = c
    # v3 채움: 줄(돌담 흰색, 쇠 울타리 하늘색, 산울타리 초록, 턱만 갈색, 마른 도랑 파랑)과 무리·노두·둔덕·선돌
    F = getattr(W, "fill", None)
    if F is not None:
        lcol = {"wall": (235, 235, 225), "fence": (110, 210, 255), "hedge": (90, 200, 80), "scarp": (170, 120, 70), "ditch": (60, 110, 255),
                "stones": (150, 150, 165)}
        for ln in F.lines:
            c = lcol.get(ln["t"], (255, 255, 255))
            pts = ln["pts"]
            for (ax_, az_), (bx_, bz_) in zip(pts[:-1], pts[1:]):
                L_ = max(1, int(math.hypot(bx_ - ax_, bz_ - az_)))
                if L_ > 12 and ln["t"] != "ditch":
                    continue                       # 끊긴 곳은 잇지 않는다
                for q in range(L_ + 1):
                    u, v = int(ax_ + (bx_ - ax_) * q / L_), int(az_ + (bz_ - az_) * q / L_)
                    if 0 <= u < SIZE and 0 <= v < SIZE:
                        px[u, SIZE - 1 - v] = c
        icol = {"grove": (20, 120, 40), "outcrop": (150, 150, 160), "barrow": (200, 90, 255), "stone": (255, 255, 255),
                "stone_row": (255, 255, 255), "milestone": (255, 200, 120), "shrine": (255, 170, 255), "cart": (170, 120, 60),
                "boulders": (120, 120, 130), "thicket": (60, 140, 60), "deadwood": (120, 80, 50)}
        for it in F.items:
            x, z = it["p"]
            rr = 4 if it["t"] in ("grove", "outcrop", "barrow") else 2
            for t in range(24):
                a = t / 24 * 2 * math.pi
                u, v = int(x + math.cos(a) * rr), int(z + math.sin(a) * rr)
                if 0 <= u < SIZE and 0 <= v < SIZE:
                    px[u, SIZE - 1 - v] = icol.get(it["t"], (255, 255, 255))
        json.dump({"note": "v3 채움 확인용. lines: t = wall/fence/hedge/scarp/ditch, src = lynchet(밭 턱 위)/road(길가)/spur(길에서 뻗는 줄)/relief, "
                           "pts = 놓인 소품 자리 (scarp·ditch 는 줄 점). items: grove/outcrop/barrow/stone/stone_row/milestone/shrine/cart",
                   "counts": dict(F.n), "lines": F.lines, "items": F.items},
                  open(os.path.join(out, "_fill.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    ov.save(os.path.join(out, "_overview.png"))
    json.dump(W.scenes, open(os.path.join(out, "_scenes.json"), "w"), ensure_ascii=False, indent=0)
    json.dump(zones, open(os.path.join(out, "_zones.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    names = ROAD_NAMES + ["(이름 없음)"] * max(0, len(W.road_curves) - len(ROAD_NAMES))
    json.dump([{"name": names[i], "hw": hw, "pts": [[round(float(a), 2), round(float(b), 2)] for a, b in c]}
               for i, (c, hw) in enumerate(W.road_curves)], open(os.path.join(out, "_roads.json"), "w"), ensure_ascii=False,
              separators=(",", ":"))
    json.dump({"note": "objects.json 의 objects 번호. intended = 의도된 묻힘(절벽·바위·울타리·낮은 것) — 묻힘 검사에서 뺀다",
               "boxed": [[k, bool(f)] for (k, f) in P.boxed]}, open(os.path.join(out, "_boxground.json"), "w"), separators=(",", ":"))


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
    forest_plan(W)
    lay_vignettes(W, P, seed)
    lay_foot_scenes(W, P)
    log("배치: 숲·산기슭·들판")
    for c, R, dens, fseed, cl in FORESTS:
        lay_forest(W, P, c, R, dens, fseed, clearings=cl)
    lay_mountain_foot(W, P)
    lay_fill(W, P)
    lay_fields(W, P)
    scene_report(W, P)
    scene_zones(W)
    lay_effects(W, P)
    beacon_emitters(W, P)
    trim_lights(W, P)
    log("지형 고치기: 큰 소품 밑 평탄화 %d 번, 평탄화로도 안 돼 뺀 큰 소품 %d 개 %s, 기울기 넘어 되돌림 %d 번" % (
        P.pads, P.pad_reject, dict(P.pad_reject_by), P.tf_undo))
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
