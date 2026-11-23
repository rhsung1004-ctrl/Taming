#!/usr/bin/env python3
# 1장 오픈월드 생성기 (버려진 묘지 들판, 2 km × 2 km)
#   python3 worldgen.py <출력 폴더(Ch1)> <소품 manifest.json 또는 manifest_*.json 이 있는 폴더> [씨앗]
# 결과 (규격: SPEC.md)
#   <출력>/Data~/world.json, height.r16, splat_0/1.png, detail_0/1.png, trees.json, objects.json
#   <출력>/Terrain/ground_*  (groundtex.py 가 만든다. 없으면 여기서 부른다)
#   <출력>/map.png, <출력>/_overview.png (확인용, Unity 로 가져가지 않아도 됨)
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
# 이름 있는 장소. 대사·지역 이름은 2D판 1장(버려진 묘지)과 같은 세계관
POIS = [
    ("altar", "봉인의 제단", (1000, 520), 40),
    ("graveyard", "잊힌 자들의 묘지", (1000, 880), 170),
    ("crypt", "이름 없는 납골당", (1000, 1003), 30),
    ("cathedral", "무너진 대성당", (1010, 1478), 75),
    ("swamp", "안개 늪", (1545, 935), 230),
    ("dragon", "용의 무덤", (470, 1060), 160),
    ("tree", "영혼의 고목", (1470, 1420), 55),
    ("village", "버려진 마을", (1390, 430), 85),
    ("tower", "부서진 망루", (640, 1572), 45),
    ("bridge", "끊어진 개울 다리", None, 30),            # 자리는 개울을 따라 계산
    ("gate", "북쪽 봉인문", (1010, 1822), 55),
    ("forest", "검은 숲", (430, 640), 200),
    ("lake", "달그림자 호수", (720, 330), 95),
]
SPAWN = (1000, 492)           # 제단 앞에서 눈을 뜬다 (북쪽 = 제단을 본다)
BOUNDS = ((170, 170), (1878, 1878))

ALTAR = (1000, 520)
GRAVE_C, GRAVE_R = (1000, 880), (190, 158)     # 묘지 타원 (X 반지름, Z 반지름)
CRYPT = (1000, 1003)
CATH = (1010, 1478)
SWAMP, SWAMP_R = (1545, 935), 300
DRAGON, DRAGON_R = (470, 1060), 215
TREE = (1470, 1420)
VILLAGE = (1390, 430)
TOWER = (640, 1572)
GATE = (1010, 1822)
FOREST_SW, FOREST_NE = ((430, 640), 235), ((1470, 1420), 175)
LAKE, LAKE_R = (720, 330), 105
CREEK = [(805, 1395), (782, 1265), (752, 1130), (722, 1010), (700, 880), (690, 740), (700, 600), (712, 470), (720, 400)]
BRIDGE_AT = (722, 1010)

# 길: (경유점, 반폭 m). 다리 구간은 개울을 따라 계산해서 끼운다
ROADS = [
    ([(1000, 470), (1000, 600), (1000, 722), (1000, 880), (1000, 978)], 2.7),                       # 제단 → 묘지 → 납골당
    ([(1000, 978), (1045, 990), (1078, 1045), (1050, 1180), (1012, 1290), (1010, 1400), (1010, 1448)], 2.5),   # 납골당 → 대성당
    ([(1040, 1460), (1075, 1520), (1068, 1640), (1020, 1740), (1010, 1795)], 2.3),                  # 대성당 → 북쪽 봉인문
    ([(812, 884), (900, 878), (1000, 880), (1100, 884), (1150, 882)], 2.0),                         # 묘지 동서 길
    ([(1150, 882), (1230, 893), (1290, 905)], 2.1),                                                  # 묘지 → 안개 늪
    ([(1040, 515), (1180, 480), (1300, 440), (1365, 432)], 2.1),                                    # 제단 → 버려진 마을
    ([(960, 505), (860, 460), (790, 415), (760, 400)], 2.0),                                        # 제단 → 달그림자 호수
    ([(500, 1140), (545, 1300), (600, 1450), (630, 1540)], 1.9),                                    # 용의 무덤 → 망루
    ([(1500, 1170), (1480, 1300), (1470, 1395)], 1.9),                                              # 늪 → 고목
    ([(1450, 1440), (1300, 1520), (1150, 1560), (1072, 1580)], 1.9),                                # 고목 → 북쪽 길
    ([(1000, 600), (900, 610), (760, 640), (600, 660), (520, 690)], 1.8),                           # 제단 북쪽 → 검은 숲
]
ROAD_TO_BRIDGE_E = [(812, 884), (770, 950)]     # 묘지 서쪽 → 다리 동쪽 끝 (끝점은 계산)
ROAD_FROM_BRIDGE_W = [(640, 1040), (565, 1055)]  # 다리 서쪽 끝 → 용의 무덤

LAYERS = [  # 이름, 타일 크기(m), 매끈함
    ("grass", 4.0, 0.04), ("moss", 4.5, 0.06), ("dirt", 5.0, 0.05), ("mud", 6.0, 0.32),
    ("rock", 11.0, 0.12), ("path", 4.0, 0.06), ("leaves", 4.0, 0.05), ("ash", 5.0, 0.04)]
DETAILS = [  # 풀 종류, 칸(1 m²)당 최대 포기 수, 크기
    ("grass_a", 3, 0.85, 1.35), ("grass_b", 2, 0.8, 1.25), ("grass_dead", 2, 0.8, 1.3),
    ("fern_a", 2, 0.75, 1.3), ("weeds", 2, 0.8, 1.35), ("reed", 3, 0.85, 1.25)]

SOUL = [0.62, 0.35, 1.0]
SPIRIT = [0.45, 0.95, 0.9]
TOXIC = [0.55, 1.0, 0.35]


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
    h = 34 + 14 * fbm(X, Z, 1 / 700, 4, 100) + 22 * (Z / SIZE)
    h += 16 * ss(fbm(X, Z, 1 / 420, 3, 110), -0.1, 0.6)          # 큰 언덕 덩어리
    h += 15 * fbm(X, Z, 1 / 300, 4, 120)                           # 구릉 (장소 사이의 오르내림)
    h += eroded(X, Z, 1 / 230, 6, 200, 12.0)
    # 가장자리 산 (안쪽 선이 구불구불하게)
    log("높이: 산")
    wob = 150 * fbm(X, Z, 1 / 520, 3, 300) + 45 * fbm(X, Z, 1 / 150, 3, 310)
    k = 140.0      # 모서리를 둥글게 (부드러운 최소)
    a = -k * np.log(np.exp(-X / k) + np.exp(-(SIZE - X) / k))
    b = -k * np.log(np.exp(-Z / k) + np.exp(-(SIZE - Z) / k))
    d_edge = -k * np.log(np.exp(-a / k) + np.exp(-b / k)) + 95 + wob
    m = ss(-d_edge, -300, -70)
    del a, b
    rid = ridged(X, Z, 1 / 300, 7, 400)
    mount = (m ** 1.3) * (55 + 230 * rid) + m * eroded(X, Z, 1 / 120, 5, 500, 14.0, k=3.0)
    corridor = np.exp(-((X - GATE[0]) / 60.0) ** 2) * ss(Z, 1660, 1790)      # 북쪽 봉인문 고갯길
    mount *= 1 - 0.94 * corridor
    h += mount
    W.mount = m * (1 - corridor)
    del wob, rid, mount, corridor

    log("높이: 지형지물")
    # 대성당 고원
    rs, cs, d = disk(h.shape, CATH[0], CATH[1], 190)
    h[rs, cs] += 27 * ss(-d, -185, -62)
    flatten(h, CATH[0], CATH[1] + 4, 42, 66)
    # 망루 언덕
    rs, cs, d = disk(h.shape, TOWER[0], TOWER[1], 130)
    h[rs, cs] += 21 * ss(-d, -125, -22)
    flatten(h, TOWER[0], TOWER[1], 14, 28)
    # 제단 둔덕
    rs, cs, d = disk(h.shape, ALTAR[0], ALTAR[1], 70)
    h[rs, cs] += 3.5 * ss(-d, -65, -14)
    flatten(h, ALTAR[0], ALTAR[1], 26, 50)
    # 묘지: 완만하게 고른다
    ex = ((X - GRAVE_C[0]) / (GRAVE_R[0] + 40)) ** 2 + ((Z - GRAVE_C[1]) / (GRAVE_R[1] + 40)) ** 2
    hb = box_blur(h, 22)
    wgr = ss(-ex, -1.0, -0.55) * 0.8
    h = h * (1 - wgr) + hb * wgr
    # 마을
    flatten(h, VILLAGE[0], VILLAGE[1], 60, 105, strength=0.75)
    # 고목 둔덕
    rs, cs, d = disk(h.shape, TREE[0], TREE[1], 70)
    h[rs, cs] += 3.5 * ss(-d, -65, -10)
    # 용의 무덤 분지 (가장자리는 턱)
    rs, cs, d = disk(h.shape, DRAGON[0], DRAGON[1], DRAGON_R + 70)
    d = d / (1 + 0.2 * fbm(X[rs, cs], Z[rs, cs], 1 / 90, 3, 1010))          # 둥글지 않게
    sub = h[rs, cs]
    sub += -19 * ss(-d, -DRAGON_R, -70) + 6 * np.exp(-((d - DRAGON_R - 5) / 28.0) ** 2)
    hbd = box_blur(sub, 14)
    wf = ss(-d, -150, -60) * 0.7
    h[rs, cs] = sub * (1 - wf) + hbd * wf

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
    target = W.lake_level - 0.4 - 4.0 * ss(-(d / edge), -0.95, -0.3) + 0.6 * fbm(Xs, Zs, 1 / 20, 3, 650)
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

    def depth(si):
        if si < 230:
            return 2.4 + 7.0 * ssf(230 - si, 0, 150)          # 북쪽은 깊은 골짜기
        return 2.2 if si < L - 200 else 1.6

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
    W.creek_bed = B

    def widths(si):
        if si < 230:
            dd = depth(si)
            return 3.0, 3.0 + dd * 0.75
        if abs(si - sb) < 45:
            return 2.6, 5.6
        return 2.8, 6.5

    wb = np.array([widths(si)[0] for si in s])
    wt = np.array([widths(si)[1] for si in s])
    (z0, z1), (x0, x1), dist, along = polyline_field(c, 16, RES)
    idx = np.clip(np.searchsorted(s, along), 0, len(s) - 1)
    Bc, wbc, wtc = B[idx].astype(np.float32), wb[idx].astype(np.float32), wt[idx].astype(np.float32)
    sub = h[z0:z1, x0:x1]
    bank = sub - Bc
    prof = Bc + np.where(dist < wbc, 0, (dist - wbc) / np.maximum(wtc - wbc, 0.5) * np.maximum(bank, 0.5))
    prof += 0.25 * perlin(np.arange(x1 - x0)[None, :] * 0.2 + x0 * 0.2, np.arange(z1 - z0)[:, None] * 0.2 + z0 * 0.2, 707) * (dist < wbc)
    k = 1.2   # 부드러운 최소
    new = -k * np.log(np.exp(-sub / k) + np.exp(-prof / k))
    w = ss(-dist, -(wtc + 10), -wtc)
    sub[:] = sub * (1 - w) + np.minimum(sub, new) * w
    W.creek_win = ((z0, z1), (x0, x1))
    W.creek_dist = dist
    W.creek_wt = wtc
    # 다리 아래 물웅덩이 (평평한 바닥 구간)
    W.pool_level = Bb + 0.42
    W.pool_range = (sb - 36, sb + 36)


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
        flatten(h, x, z, rin, rout)
    X, Z = W.X, W.Z
    micro = 0.22 * fbm(X, Z, 1 / 7.0, 3, 800) + 0.5 * fbm(X, Z, 1 / 28.0, 2, 810)
    keep = ss(W.road_dist, 2, 8)
    rs, cs, d = disk(h.shape, W.bridge_p[0], W.bridge_p[1], 24)
    keep[rs, cs] *= ss(d, 10, 22)                     # 다리 둑 높이는 그대로
    for (x, z, rin, rout) in pads:
        rs, cs, d = disk(h.shape, x, z, rout)
        keep[rs, cs] *= ss(d, rin * 0.8, rout)
    h += micro * keep
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


class Placer:
    def __init__(self, W, meta, rng):
        self.W, self.meta, self.rng = W, meta, rng
        self.objects, self.trees, self.protos = [], [], []
        self.grid = {}
        self.cell = 6.0
        self.missing = set()
        self.count = {}
        self.stamps = []        # (x, z, r, 종류) 바닥 칠·풀 지우기

    def free(self, x, z, r):
        c = self.cell
        i0, i1 = int((x - r - 8) // c), int((x + r + 8) // c)
        j0, j1 = int((z - r - 8) // c), int((z + r + 8) // c)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for (ox, oz, orr) in self.grid.get((i, j), ()):
                    if (ox - x) ** 2 + (oz - z) ** 2 < (orr + r) ** 2 * 0.85:
                        return False
        return True

    def occupy(self, x, z, r):
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

    def put(self, a, x, z, yaw=None, s=None, tilt=None, align=None, y=None, check=True, r=None,
            road=True, water=True, slope=0.75, stamp=None, occupy=True):
        """소품 하나. META 기본값(크기·기울기·묻기·경사 맞춤)을 쓴다. 성공하면 True"""
        m = self.meta.get(a)
        if m is None:
            self.missing.add(a)
            return False
        rng = self.rng
        if s is None:
            lo, hi = m.get("scale", [1, 1])
            s = rng.uniform(lo, hi)
        fp = (m.get("footprint", 0.5) if r is None else r) * s
        if check:
            if not self.ok_ground(x, z, fp, road, water, slope):
                return False
            if not self.free(x, z, fp):
                return False
        if yaw is None:
            yaw = rng.uniform(0, 360)
        if occupy:
            self.occupy(x, z, fp)
        kind = m.get("kind", "prop")
        if stamp:
            self.stamps.append((x, z, fp * stamp[1], stamp[0]))
        else:
            self.stamps.append((x, z, fp * 0.8, "clear"))
        self.count[a] = self.count.get(a, 0) + 1
        if kind == "tree":
            if a not in self.protos:
                self.protos.append(a)
            self.trees.append([self.protos.index(a), round(x, 2), round(z, 2), round(yaw % 360, 1), round(s, 3)])
            return True
        if y is None:
            hs = [self.height(x, z)]
            if not (align if align is not None else m.get("align", False)):
                for k in range(6):
                    t = k / 6 * 2 * math.pi
                    hs.append(self.height(x + math.cos(t) * fp * 0.7, z + math.sin(t) * fp * 0.7))
                y = min(hs) * 0.6 + hs[0] * 0.4
            else:
                y = hs[0]
            y -= m.get("sink", 0.0) * s
        q = quat_axis((0, 1, 0), math.radians(yaw))
        tmax = m.get("tilt", 0) if tilt is None else tilt
        if tmax > 0:
            t = math.radians(rng.uniform(0, tmax))
            phi = rng.uniform(0, 2 * math.pi)
            q = quat_mul(quat_axis((math.cos(phi), 0, math.sin(phi)), t), q)
        if align if align is not None else m.get("align", False):
            n = self.normal(x, z)
            ang = math.acos(max(-1.0, min(1.0, n[1])))
            if ang > 1e-4:
                q = quat_mul(quat_axis((n[2], 0.0, -n[0]), ang), q)
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
    pads = [(ALTAR[0], ALTAR[1], 11, 26), (CRYPT[0], CRYPT[1], 10, 20), (TREE[0], TREE[1], 6, 14),
            (TOWER[0], TOWER[1], 7, 16), (GATE[0], GATE[1], 13, 28), (VILLAGE[0], VILLAGE[1], 4, 10)]
    return pads


def place_landmarks(W, P):
    bx, bz = W.bridge_p
    r = W.bridge_axis
    # 다리: 로컬 X(경간) = 길 방향. Unity Y 회전 θ 는 +X 를 (cosθ, 0, −sinθ) 로 돌린다
    th = math.degrees(math.atan2(-r[1], r[0]))
    P.put("bridge_ruin", bx, bz, yaw=th, y=W.bridge_bank - 0.02, check=False, stamp=("path", 1.0))
    P.put("altar", ALTAR[0], ALTAR[1], yaw=180, check=False, stamp=("ash", 1.4))
    P.put("crypt", CRYPT[0], CRYPT[1], yaw=180, check=False, stamp=("dirt", 1.2))
    P.put("cathedral_ruin", CATH[0], CATH[1], yaw=180, check=False, stamp=("dirt", 1.1))
    P.put("tree_giant", TREE[0], TREE[1], yaw=205, check=False, stamp=("leaves", 1.6))
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
        P.put("rubble", cx + math.cos(a) * rng.uniform(9, 22), cz + math.sin(a) * rng.uniform(9, 22), road=False)
    for i in range(16):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(4.6, 8)
        P.put("candles", cx + math.cos(a) * d, cz + math.sin(a) * d, road=False)
    for i in range(10):
        P.put("skull", cx + rng.uniform(-14, 14), cz + rng.uniform(-14, 14), road=False)
    for dx in (-4.2, 4.2):
        P.put("lantern", cx + dx, cz - 21, yaw=180, check=False)


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
    # 큰 석관: 가운데 길 양쪽 (먼저 자리를 잡는다)
    for k in range(-5, 6):
        zz = cz + k * 22 + 8
        for side in (-1, 1):
            if rng.random() < 0.7:
                P.put("grave_tomb", cx + side * 9.5, zz, yaw=90 * -side + rng.normal(0, 3), slope=0.5, stamp=("dirt", 1.4))
    row = 0
    z = cz - rz + 10
    while z < cz + rz - 6:
        row += 1
        x = cx - rx + 4 + rng.uniform(0, 2)
        while x < cx + rx - 4:
            e = ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2
            if e < 0.93 and abs(x - cx) > 6.5 and abs(z - cz) > 5.5 and noise_skip(x, z) > 0.0 and rng.random() > 0.3:
                nm = names[int(rng.choice(len(names), p=wts))]
                yaw = 180 + rng.normal(0, 6)
                if P.put(nm, x + rng.normal(0, 0.25), z + rng.normal(0, 0.3), yaw=yaw, slope=0.5,
                         stamp=("dirt", 1.6) if nm != "grave_sunken" else ("mud", 1.4)):
                    n_graves += 1
                    if rng.random() < 0.05:
                        P.put("candles", x + rng.uniform(-0.5, 0.5), z - 1.0, road=False)
                    if rng.random() < 0.03:
                        P.put("skull", x + rng.uniform(-0.8, 0.8), z - rng.uniform(0.8, 1.5), road=False)
            x += rng.uniform(2.0, 2.9)
        z += 3.3 + rng.uniform(-0.2, 0.3)
    # 울타리: 타원 둘레 (군데군데 무너짐). 남쪽 정문, 동·서쪽 길 자리는 비운다
    per = 2 * math.pi * math.sqrt((rx * rx + rz * rz) / 2) + 8
    n = int(per / 3.45)
    for i in range(n):
        t = i / n * 2 * math.pi
        x, z = cx + math.cos(t) * (rx + 8), cz + math.sin(t) * (rz + 8)
        tx, tz = -math.sin(t) * (rx + 8), math.cos(t) * (rz + 8)
        if sample(W.road_dist, x, z) < 6:
            continue
        if rng.random() < 0.16:
            continue
        th = math.degrees(math.atan2(-tz, tx))           # 로컬 X 를 접선 방향으로
        P.put("fence", x, z, yaw=th, check=False, tilt=3 if rng.random() < 0.8 else 9, stamp=("dirt", 0.7))
    P.put("fence_gate", cx, cz - rz - 8, yaw=180, check=False, stamp=("path", 1.0))
    # 등불: 가운데 길과 동서 길
    for k in range(-6, 6):
        zz = cz + k * 26 + 13
        side = 1 if k % 2 else -1
        P.put("lantern", cx + side * 4.3, zz, yaw=90 * side, check=False)
    for k in (-1, 1):
        for d in (40, 80, 120, 160):
            P.put("lantern", cx + k * d, cz + 4.2 * (1 if d % 80 else -1), yaw=0, check=False)
    # 가운데 십자로의 천사상, 납골당 앞 사신상
    P.put("statue_angel", cx, cz, yaw=180, check=False, stamp=("path", 3.0))
    for side in (-1, 1):
        P.put("statue_reaper", CRYPT[0] + side * 8.5, CRYPT[1] - 9, yaw=180, check=False, stamp=("path", 1.5))
        P.put("lantern", CRYPT[0] + side * 4.5, CRYPT[1] - 14, yaw=180, check=False)
    # 고목·덤불·해골
    area = lambda rng: (cx + rng.uniform(-rx, rx), cz + rng.uniform(-rz, rz))
    P.scatter("dead_tree_a", 7, area)
    P.scatter("dead_tree_c", 5, area)
    P.scatter("bush_dead", 40, area)
    def ring(rng):
        t = rng.uniform(0, 2 * math.pi)
        return (cx + math.cos(t) * (rx + rng.uniform(4, 14)), cz + math.sin(t) * (rz + rng.uniform(4, 14)))
    P.scatter("bramble", 30, ring)
    P.scatter("skull", 50, area)
    P.scatter("bone_pile", 12, area)
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
        P.put(nm, x, z, yaw=yaw_to(x - cx, z - cz) + 90 + rng.normal(0, 15), slope=0.6, stamp=("dirt", 1.2))
    P.scatter("rubble", 30, in_disk((cx, cz), 48, 20), road=False)
    P.scatter("candles", 18, in_disk((cx, cz - 6), 12), road=False, check=True)
    P.scatter("grave_slab_c", 14, in_disk((cx, cz), 70, 30))
    P.scatter("grave_cross", 10, in_disk((cx, cz), 70, 30))
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
    for k in range(10):
        a = k / 10 * 2 * math.pi
        x, z = cx + 60 * math.cos(a), cz + 50 * math.sin(a)
        if rng.random() < 0.6:
            P.put("fence", x, z, yaw=math.degrees(a), tilt=6)
    P.scatter("stump", 8, in_disk((cx, cz), 75, 20))
    P.scatter("log_fallen", 4, in_disk((cx, cz), 75, 20))
    P.scatter("bush_dead", 20, in_disk((cx, cz), 80))
    P.scatter("bramble", 14, in_disk((cx, cz), 85, 30))
    P.put("lantern", cx + 5, cz - 6, yaw=200, check=True)
    P.put("lantern", cx - 6, cz + 5, yaw=20, check=True)
    # 마을 묘지 (작은 울타리 안)
    gx, gz = cx + 55, cz + 50
    for i in range(14):
        P.put(["grave_slab_a", "grave_cross", "grave_slab_b"][i % 3], gx + (i % 5) * 2.4 - 5, gz + (i // 5) * 3.2, yaw=180 + rng.normal(0, 8))


def lay_swamp(W, P):
    rng = P.rng
    cx, cz = SWAMP
    lev = W.swamp_level
    area = in_disk(SWAMP, SWAMP_R - 20)
    # 물 위의 연꽃: 수면 높이에 띄운다
    got = 0
    for i in range(900):
        if got >= 110:
            break
        x, z = area(rng)
        hh = P.height(x, z)
        if lev - 1.4 < hh < lev - 0.15 and P.free(x, z, 0.5):
            P.put("lotus_glow", x, z, y=lev + 0.01, align=False, tilt=0, check=False)
            got += 1
    # 물 밖 (섬·물가)
    dry = lambda rng: (lambda p: p if P.height(*p) > lev + 0.1 else None)(area(rng))
    P.scatter("dead_tree_b", 160, dry, water=True)
    P.scatter("dead_tree_c", 70, dry)
    P.scatter("roots", 45, dry)
    P.scatter("log_fallen", 30, dry)
    P.scatter("stump", 40, dry)
    P.scatter("mushroom_toxic", 70, dry)
    P.scatter("bush_dead", 60, dry)
    P.scatter("rock_flat", 15, dry)
    P.scatter("grave_sunken", 18, dry)
    P.scatter("grave_slab_c", 10, dry)
    # 물속에 선 고목 (뿌리가 잠김): 물 위에서도 자리를 차지
    for i in range(400):
        x, z = area(rng)
        if lev - 1.0 < P.height(x, z) < lev and P.free(x, z, 1.5):
            P.put("dead_tree_b", x, z, check=False)
    # 도깨비불 광원 (떠다닌다)
    for i in range(34):
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
    area = in_disk(DRAGON, DRAGON_R - 15)
    P.scatter("bone_spike", 70, area)
    P.scatter("bones_scatter", 150, area)
    P.scatter("bone_pile", 25, area)
    P.scatter("skull", 40, area)
    P.scatter("rock_a", 30, area)
    P.scatter("rock_c", 50, area)
    P.scatter("rock_flat", 10, area)
    # 분지 테두리의 절벽 (안쪽을 본다)
    for i in range(22):
        ang = i / 22 * 2 * math.pi + rng.uniform(-0.08, 0.08)
        d = DRAGON_R - 20 + rng.uniform(-10, 18)
        x, z = cx + math.cos(ang) * d, cz + math.sin(ang) * d
        nm = ["cliff_a", "cliff_c", "cliff_b"][i % 3]
        P.put(nm, x, z, yaw=yaw_to(cx - x, cz - z) + rng.normal(0, 10), slope=None)
    for i in range(6):
        x, z = area(rng)
        W.lights.append({"p": [round(x, 2), round(P.height(x, z) + 1.5, 2), round(z, 2)], "c": SOUL, "i": 4.0, "r": 9.0, "flicker": True})
    for t in (0, 19.5, 31.5):
        x, z = at(t)
        W.lights.append({"p": [round(x, 2), round(P.height(x, z) + 2.5, 2), round(z, 2)], "c": SOUL, "i": 5.0, "r": 12.0, "flicker": True})


def lay_tree(W, P):
    rng = P.rng
    cx, cz = TREE
    for i in range(36):
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
        P.put(nm, x, z, yaw=yaw_to(x - cx, z - cz) + 90, slope=0.7)
    P.scatter("rock_b", 8, in_disk(TOWER, 60, 20), slope=None)
    P.scatter("rock_flat", 6, in_disk(TOWER, 60, 20), slope=None)
    P.put("lantern", cx + 3, cz - 9, yaw=180)


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


def lay_bridge_creek(W, P):
    rng = P.rng
    c, s = W.creek, W.creek_s
    bx, bz = W.bridge_p
    # 물웅덩이 아래쪽 끝의 돌무더기 (물 평면이 끊기는 자리를 가린다)
    s1 = W.pool_range[1]
    i = int(np.searchsorted(s, s1))
    px, pz = c[min(i, len(c) - 1)]
    P.put("rock_b", px, pz, yaw=rng.uniform(0, 360), check=False, align=True, s=1.25)
    for k in range(4):
        P.put("rubble", px + rng.uniform(-4, 4), pz + rng.uniform(-4, 4), check=False, s=rng.uniform(1.0, 1.4))
    i0 = int(np.searchsorted(s, W.pool_range[0]))
    qx, qz = c[i0]
    P.put("rock_a", qx, qz, check=False, s=1.4)
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
                  water=False, slope=None)
        if rng.random() < 0.25:
            d = W.creek_dir_b
            off = rng.choice([-1, 1]) * rng.uniform(8, 14)
            P.put(["dead_tree_b", "dead_tree_a", "stump", "log_fallen"][k % 4], x - d[1] * off, z + d[0] * off)
    for k in range(0, len(c), 40):
        x, z = c[k]
        W.fx.append({"type": "mist", "p": [float(x), P.height(x, z) + 0.5, float(z)], "r": 22})


def lay_forest(W, P, center, R, density, seed):
    rng = P.rng
    X, Z = W.X, W.Z
    rs, cs, d = disk(W.h.shape, center[0], center[1], R + 40)
    edge = R + 45 * fbm(X[rs, cs], Z[rs, cs], 1 / 120, 3, seed)
    m = np.zeros(W.h.shape, np.float32)
    m[rs, cs] = ss(-(d / edge), -1.0, -0.6) * (0.55 + 0.45 * ss(fbm(X[rs, cs], Z[rs, cs], 1 / 60, 3, seed + 1), -0.4, 0.4))
    m *= (W.slope < 0.7)
    W.forest = np.maximum(W.forest, m)
    area = in_mask(W, m)
    area_tot = float(m.sum())
    nt = int(area_tot * density)
    P.scatter("dead_tree_a", int(nt * 0.34), area)
    P.scatter("dead_tree_c", int(nt * 0.22), area)
    P.scatter("dead_tree_b", int(nt * 0.22), area)
    P.scatter("bramble", int(nt * 0.3), area)
    P.scatter("bush_dead", int(nt * 0.3), area)
    P.scatter("rock_a", int(nt * 0.08), area)
    P.scatter("rock_c", int(nt * 0.08), area)
    P.scatter("stump", int(nt * 0.06), area)
    P.scatter("log_fallen", int(nt * 0.05), area)
    P.scatter("roots", int(nt * 0.05), area)
    P.scatter("mushroom_glow", int(nt * 0.05), area)
    P.scatter("mushroom_toxic", int(nt * 0.02), area)
    P.scatter("flower_lily", int(nt * 0.03), area)
    for i in range(int(area_tot / 9000)):
        p = area(rng)
        W.fx.append({"type": "fireflies", "p": [float(p[0]), P.height(*p) + 1.5, float(p[1])], "r": 26})
    for i in range(int(area_tot / 16000)):
        p = area(rng)
        W.fx.append({"type": "mist", "p": [float(p[0]), P.height(*p) + 0.5, float(p[1])], "r": 30})
    log("숲", center, "나무 목표", nt)


def lay_lake(W, P):
    rng = P.rng
    lev = W.lake_level
    area = in_disk(LAKE, LAKE_R + 25)
    got = 0
    for i in range(600):
        if got >= 45:
            break
        x, z = area(rng)
        if lev - 1.2 < P.height(x, z) < lev - 0.15 and P.free(x, z, 0.5):
            P.put("lotus_glow", x, z, y=lev + 0.01, align=False, tilt=0, check=False)
            got += 1
    shore = lambda rng: (lambda p: p if lev + 0.1 < P.height(*p) < lev + 3 else None)(in_disk(LAKE, LAKE_R + 35, LAKE_R - 25)(rng))
    P.scatter("flower_lily", 30, shore)
    P.scatter("rock_a", 14, shore)
    P.scatter("rock_flat", 6, shore)
    P.scatter("dead_tree_b", 12, shore)
    P.scatter("log_fallen", 4, shore)
    for i in range(10):
        x, z = area(rng)
        W.lights.append({"p": [round(x, 2), round(lev + rng.uniform(0.8, 2.2), 2), round(z, 2)], "c": SPIRIT, "i": 3.5, "r": 8.0, "flicker": True})
    W.fx.append({"type": "mist", "p": [LAKE[0], lev + 0.3, LAKE[1]], "r": 70})
    W.fx.append({"type": "fireflies", "p": [LAKE[0], lev + 1.5, LAKE[1]], "r": 60})


def lay_mountain_foot(W, P):
    """산기슭의 절벽과 바위 (가장자리 산이 시작하는 곳)"""
    rng = P.rng
    foot = ss(W.mount, 0.12, 0.3) * ss(-W.mount, -0.75, -0.5) * ss(W.slope, 0.25, 0.5)
    area = in_mask(W, foot)
    cx, cz = SIZE / 2, SIZE / 2
    got = 0
    for i in range(3000):
        if got >= 170:
            break
        p = area(rng)
        x, z = p
        nm = ["cliff_a", "cliff_c", "cliff_b", "cliff_a", "rock_b"][got % 5]
        if P.put(nm, x, z, yaw=yaw_to(cx - x, cz - z) + rng.normal(0, 25), slope=None, s=rng.uniform(1.0, 1.9) if nm != "rock_b" else None,
                 stamp=("rock", 1.3)):
            got += 1
    steep = ss(W.slope, 0.45, 0.9) * (W.mount < 0.75)
    a2 = in_mask(W, steep)
    P.scatter("rock_b", 160, a2, slope=None)
    P.scatter("rock_a", 500, a2, slope=None)
    P.scatter("rock_c", 600, a2, slope=None)
    P.scatter("rock_flat", 120, a2, slope=None)


def lay_fields(W, P):
    """넓은 들판: 외딴 무덤, 폐허 무더기, 고목, 바위, 길가 등불"""
    rng = P.rng
    (bx0, bz0), (bx1, bz1) = BOUNDS
    open_ = (W.mount < 0.15).astype(np.float32) * (W.slope < 0.45)
    a = in_mask(W, open_)
    P.scatter("dead_tree_a", 260, a)
    P.scatter("dead_tree_b", 200, a)
    P.scatter("dead_tree_c", 140, a)
    P.scatter("bush_dead", 700, a)
    P.scatter("bramble", 500, a)
    P.scatter("rock_a", 420, a)
    P.scatter("rock_c", 650, a)
    P.scatter("rock_b", 70, a)
    P.scatter("rock_flat", 60, a)
    P.scatter("stump", 90, a)
    P.scatter("log_fallen", 50, a)
    P.scatter("roots", 40, a)
    P.scatter("flower_lily", 120, a)
    P.scatter("mushroom_glow", 70, a)
    P.scatter("skull", 120, a)
    P.scatter("bone_pile", 30, a)
    # 외딴 무덤 무리 (울타리 일부와 함께)
    for k in range(26):
        p = a(rng)
        if p is None:
            continue
        x, z = p
        if any((x - px) ** 2 + (z - pz) ** 2 < 220 ** 2 for (px, pz) in (GRAVE_C, VILLAGE, CATH)):
            continue
        yaw = rng.uniform(0, 360)
        for j in range(rng.integers(3, 9)):
            gx, gz = x + rng.normal(0, 4), z + rng.normal(0, 4)
            P.put(["grave_slab_a", "grave_slab_b", "grave_cross", "grave_sunken", "grave_slab_c"][j % 5], gx, gz, yaw=yaw + rng.normal(0, 12),
                  stamp=("dirt", 1.5))
        if rng.random() < 0.6:
            P.put("fence", x + rng.uniform(-6, 6), z + rng.uniform(-6, 6), tilt=9)
        if rng.random() < 0.3:
            P.put("statue_angel", x + rng.uniform(-5, 5), z + rng.uniform(-5, 5), yaw=yaw)
    # 폐허 무더기
    for k in range(34):
        p = a(rng)
        if p is None:
            continue
        x, z = p
        yaw = rng.uniform(0, 360)
        for j in range(rng.integers(2, 6)):
            nm = ["wall_ruin_a", "pillar_b", "rubble", "wall_ruin_b", "pillar_a", "arch_ruin", "rubble"][int(rng.integers(0, 7))]
            P.put(nm, x + rng.normal(0, 6), z + rng.normal(0, 6), yaw=yaw + rng.choice([0, 90, 180, 270]) + rng.normal(0, 8),
                  stamp=("dirt", 1.2))
        if rng.random() < 0.35:
            P.put("lantern", x + rng.uniform(-6, 6), z + rng.uniform(-6, 6))
    # 길가 등불 (갈림길과 장소 가까이)
    for c, hw in W.road_curves:
        seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        nxt = rng.uniform(20, 50)
        side = 1
        for i in range(1, len(c) - 1):
            if s[i] < nxt:
                continue
            d = c[i + 1] - c[i - 1]
            d /= np.linalg.norm(d)
            x, z = c[i] + np.array([d[1], -d[0]]) * side * (hw + 1.4)
            near = min((x - px) ** 2 + (z - pz) ** 2 for (_, _, pp, _) in POIS if pp for (px, pz) in [pp])
            if near < 260 ** 2 and P.put("lantern", x, z, yaw=yaw_to(-d[1] * side, d[0] * side), road=False):
                side = -side
            nxt = s[i] + rng.uniform(42, 75)
    # 길가 울타리 조각과 이정표 대신 기둥
    for c, hw in W.road_curves:
        for i in range(0, len(c), 23):
            if rng.random() < 0.18:
                d = c[min(i + 1, len(c) - 1)] - c[max(i - 1, 0)]
                d /= np.linalg.norm(d) + 1e-9
                sd = rng.choice([-1, 1])
                x, z = c[i] + np.array([d[1], -d[0]]) * sd * (hw + 2.4)
                P.put("fence", x, z, yaw=math.degrees(math.atan2(-d[1], d[0])), tilt=8, road=False)


def lay_groves(W, P):
    """들판 곳곳의 작은 숲과 언덕 위 바위 무리 (먼 데서 보이는 표지)"""
    rng = P.rng
    open_ = (W.mount < 0.2).astype(np.float32) * (W.slope < 0.5)
    a = in_mask(W, open_)
    for k in range(46):
        p = a(rng)
        if p is None:
            continue
        x, z = p
        if any((x - px) ** 2 + (z - pz) ** 2 < (pr + 30) ** 2 for (px, pz), pr in ((GRAVE_C, 190), (SWAMP, SWAMP_R), (DRAGON, DRAGON_R), (CATH, 90), (VILLAGE, 90), (ALTAR, 60))):
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
    for k in range(30):
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
    for i in range(7):
        x, z = in_disk(GRAVE_C, 150)(rng)
        W.fx.append({"type": "mist", "p": [float(x), P.height(x, z) + 0.4, float(z)], "r": 34})
    for i in range(4):
        x, z = in_disk(GRAVE_C, 140)(rng)
        W.fx.append({"type": "wisps", "p": [float(x), P.height(x, z) + 1.0, float(z)], "r": 24})
    W.fx.append({"type": "soulfire", "p": [ALTAR[0], P.height(*ALTAR) + 1.2, ALTAR[1]], "r": 9})
    W.fx.append({"type": "wisps", "p": [ALTAR[0], P.height(*ALTAR) + 1.0, ALTAR[1]], "r": 26})
    W.fx.append({"type": "soulfire", "p": [CRYPT[0], P.height(CRYPT[0], CRYPT[1] - 10) + 1.0, CRYPT[1] - 10], "r": 6})
    W.fx.append({"type": "wisps", "p": [CATH[0], P.height(*CATH) + 2.0, CATH[1]], "r": 40})
    for i in range(12):
        x, z = in_disk(SWAMP, SWAMP_R - 30)(rng)
        W.fx.append({"type": "mist", "p": [float(x), W.swamp_level + 0.3, float(z)], "r": 45})
    for i in range(6):
        x, z = in_disk(SWAMP, SWAMP_R - 40)(rng)
        W.fx.append({"type": "fireflies", "p": [float(x), W.swamp_level + 1.5, float(z)], "r": 34})
    for i in range(4):
        x, z = in_disk(DRAGON, DRAGON_R - 40)(rng)
        W.fx.append({"type": "mist", "p": [float(x), P.height(x, z) + 0.4, float(z)], "r": 40})
    for i in range(3):
        x, z = in_disk(DRAGON, 80)(rng)
        W.fx.append({"type": "wisps", "p": [float(x), P.height(x, z) + 1.0, float(z)], "r": 30})
    for i in range(3):
        x, z = in_disk(VILLAGE, 60)(rng)
        W.fx.append({"type": "mist", "p": [float(x), P.height(x, z) + 0.4, float(z)], "r": 30})
    # 제단·묘지 광원
    for i in range(6):
        a = i / 6 * 2 * math.pi
        x, z = ALTAR[0] + math.cos(a) * 9, ALTAR[1] + math.sin(a) * 9
        W.lights.append({"p": [round(x, 2), round(P.height(x, z) + 2.2, 2), round(z, 2)], "c": SOUL, "i": 3.0, "r": 8.0, "flicker": True})


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
    # 다리 아래 물웅덩이: 개울을 따라 짧은 판 여러 장 (같은 높이)
    c, s = W.creek, W.creek_s
    s0, s1 = W.pool_range
    k = s0
    pool_rects = []
    while k < s1 - 1:
        k2 = min(k + 18, s1)
        i0, i1 = int(np.searchsorted(s, k)), int(np.searchsorted(s, k2))
        i1 = min(i1, len(c) - 1)
        a, b = c[i0], c[i1]
        mid = (a + b) / 2
        dv = b - a
        ln = float(np.linalg.norm(dv)) + 0.6
        yaw = math.degrees(math.atan2(dv[0], dv[1]))
        planes.append({"p": [round(float(mid[0]), 2), round(W.pool_level, 3), round(float(mid[1]), 2)], "size": [15.0, round(ln, 2)], "yaw": round(yaw, 2)})
        pool_rects.append((mid, dv / (np.linalg.norm(dv) + 1e-9), ln, 15.0))
        k = k2
    W.pool_rects = pool_rects
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
    ov.save(os.path.join(out, "_overview.png"))


def mix_forest(W, col):
    return col * (1 - W.forest[..., None] * 0.35) + np.array([0.1, 0.12, 0.1], np.float32) * W.forest[..., None] * 0.35


def load_manifest(path):
    meta = {}
    files = [path] if os.path.isfile(path) else sorted(glob.glob(os.path.join(path, "manifest_*.json")))
    for f in files:
        d = json.load(open(f))
        for k, v in d.items():
            meta[k] = v.get("meta", {})
    return meta


def main():
    out = sys.argv[1]
    meta = load_manifest(sys.argv[2])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    log("소품", len(meta), "종")
    W = World()
    W.lights, W.fx = [], []
    build_height(W)
    W.forest = np.zeros(W.h.shape, np.float32)
    rng = np.random.default_rng(seed)
    P = Placer(W, meta, rng)
    pads = lay_landmarks(W, P)
    finish_height(W, pads)
    water = water_planes(W)
    make_pool_mask(W)
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
    log("배치: 숲·산기슭·들판")
    lay_forest(W, P, FOREST_SW[0], FOREST_SW[1], 1 / 70.0, 1301)
    lay_forest(W, P, FOREST_NE[0], FOREST_NE[1], 1 / 85.0, 1311)
    lay_mountain_foot(W, P)
    lay_groves(W, P)
    lay_fields(W, P)
    lay_effects(W, P)
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
    log("끝. 나무", len(P.trees), "소품", len(P.objects), "광원", len(W.lights), "물", len(water), "효과", len(W.fx))
    if P.missing:
        log("manifest 에 없는 소품 (건너뜀):", sorted(P.missing))
    cnt = sorted(P.count.items(), key=lambda kv: -kv[1])
    log("종류별:", ", ".join("%s %d" % kv for kv in cnt))
    log("수면: 늪 %.2f, 호수 %.2f, 다리 웅덩이 %.2f, 다리 둑 %.2f" % (W.swamp_level, W.lake_level, W.pool_level, W.bridge_bank))


if __name__ == "__main__":
    main()
