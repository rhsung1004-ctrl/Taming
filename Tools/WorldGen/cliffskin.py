#!/usr/bin/env python3
# 산 벽 덮개 (cliff skin) — w6a
# Unity 지형은 텍스처를 위에서 내려 찍어(UV = XZ) 가파른 산 벽(기울기 60~83°)에서 무늬가 세로로 늘어나고, 1 m 높이맵 격자로는
# 벽의 턱·처마가 1~2 칸이라 30~75 m 앞에서 '매끈한 커튼'으로 보였다. 셰이더를 새로 쓰지 않고(지형 셰이더는 Unity 없이 확인할 수 없다)
# 가파른 면만 따로 메쉬로 덮는다:
#  - 걸어 다니는 범위 안쪽 둘레에 기준선(모서리 둥근 사각형, 봉인문 자리만 안쪽으로 들어감)을 긋고, 기준선의 바깥 법선을 따라 수평 광선을 쏜다.
#    열 = 기준선 위 1.25 m 마다의 광선, 행 = 높이 1 m 마다. 광선이 그 높이에서 처음 땅에 닿는 점이 덮개 정점이다
#    (골짜기에서 보이는 면만 잡힌다. 벽 뒤의 봉우리·평평한 턱 위는 잡히지 않는다).
#  - 덮는 곳: 닿은 점의 지형 기울기 ≥ SKIN_SLOPE (약 48°), 위아래 행 사이도 가파르고, 옆 열 사이 깊이가 크게 튀지 않는 곳.
#    평평한 지층 턱(지형 그대로, 이끼 칠)에서 덮개가 끊겨 층마다 띠가 된다.
#  - 변위: 광선 반대(수평) 방향으로 앞으로 민다 → 턱·처마가 수평으로 남는다. 지층(worldgen strata_steps 와 같은 경계, 기운 q = 높이 + 기울기 노이즈)
#    마다 단단함이 달라 윗부분이 튀어나온 처마 + 그 위 턱, 층 안 잔 층리, 세로 골, 큰 부풂, 깨진 덩이. 벽 발치(사람 키 높이)는 거의 평평하게,
#    덮개 가장자리 정점은 지형 속으로 SKIN_SINK 만큼 넣어 경계가 땅에 묻힌다.
#  - UV: u = 둘레 호 길이 (m, 열마다 같은 값 → 옆 투영, 늘어남 없음), v = q (m, 기운 지층을 따른다). 재질 타일 SKIN_TILE m.
#    지층 밝기 띠는 q(세로) × 둘레(가로, 약 360 m 마다 되풀이) 띠 텍스처(파일 머리의 strip)로 URP Lit 의 Detail Albedo(×2)에 건다.
#    띠의 진하기가 둘레를 따라 옅어졌다 짙어진다 (어디서나 같은 줄무늬가 되지 않게)
#  - 조각: 열 SKIN_CHUNK[0] × 행 SKIN_CHUNK[1] 칸. LOD 셋(격자 1·2·4 배), 마지막 LOD 끝에서 사라진다. 충돌체 없음 (지형 충돌체 그대로).
# 결과: <Data~>/cliffs.bin (gzip). 규격은 SPEC.md '산 벽 덮개'. read() 로 다시 읽는다 (render_world.py, 성능 검사)
import os, sys, io, math, gzip, struct, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from terrain import fbm, ridged, perlin, ss, box_blur

SKIN_INSET = 60.0            # 기준선: 걸어 다니는 범위(bounds) 안쪽 이만큼 (m). 능선 밑동(26 m)·발치 흔들림(±17 m)보다 안쪽
SKIN_CORNER_R = 160.0        # 기준선 모서리 반지름 (m)
SKIN_GATE_PULL = (40.0, 300.0)   # 봉인문 둘레 기준선을 안쪽으로 당기는 폭 (|x − 문| 이 범위에서 0 → 다 당김). 벽 발치보다 넓고 완만하게 (광선이 엇갈리지 않게)
SKIN_RAY = (-10.0, 230.0)    # 광선 길이 (기준선에서 m, 음수 = 안쪽). 벽 발치 바깥 약 170 m 까지
SKIN_RAY_STEP = 0.25         # 광선 위 높이 표본 간격 (m)
SKIN_GROUND_LOOK = 40.0      # 광선 처음 이만큼(m) 안의 가장 낮은 땅부터 잰다 (기준선이 작은 둔덕 위여도 벽 발치 아래쪽을 놓치지 않게)
SKIN_DS = 1.25               # 열 간격 (기준선 위 m). 모서리에서는 벽까지 퍼져 1.5~2.5 m
SKIN_DY = 1.0                # 행 간격 (높이 m)
SKIN_Y = (12.0, 300.0)       # 행 높이 범위 (m)
SKIN_SLOPE = 1.1             # 덮는 지형 기울기 하한 (약 48°. 걸을 수 있는 한계 1.0~1.19 와 같은 띠)
SKIN_ROW_SLOPE = 0.8         # 위아래 이웃 행 사이 면 기울기 하한 (이보다 눕으면 지층 턱 → 덮개를 끊는다. 0.5 로 낮추면 턱을 덮어 버려 벽이 다시 뭉개졌다)
SKIN_COL_JUMP = 2.0          # 옆 열 사이 깊이 차 ÷ 열 간격 상한 (광선에 63° 넘게 빗긴 면 = 능선 옆면·봉인문 골은 지형 그대로)
SKIN_FACING = 0.25           # 면이 광선 반대쪽(골짜기)을 보는 정도 하한 (접힌 칸 빼기)
SKIN_MIN_RUN = 3             # 같은 행에서 이어진 칸이 이보다 짧은 덮개 조각은 뺀다 (부스러기)
SKIN_TILE = 6.0              # 바위 텍스처 한 장이 덮는 크기 (m). 지형 바위 층(11 m)보다 촘촘하게 (30~75 m 에서 결이 보이게)
SKIN_BASE = 0.35             # 덮개를 지형 앞으로 띄우는 기본 거리 (m, 광선 방향). 지형 LOD·쌍선형 오차로 지형이 비쳐 나오지 않게
SKIN_CLEAR = 0.25            # 덮개 칸 둘레(±반 칸)에서 가장 앞으로 나온 땅보다 적어도 이만큼(m) 앞에 정점을 둔다 (지형이 비쳐 나오지 않게)
SKIN_HOLE_FILL = 2           # 작은 구멍 메우기 횟수: 둘레 8 정점 중 7 넘게 덮인 정점, 둘레 넷 중 셋 넘게 덮인 칸 (벽 가운데 작은 구멍 = 가장자리가 묻혀 검은 웅덩이처럼 보였다)
SKIN_HOLE_RUN = 3            # 같은 행에서 양쪽이 덮인 이 칸 수 이하의 빈 줄은 메운다 (더 길면 지층 턱으로 둔다)
SKIN_SINK = 0.3              # 덮개 가장자리 정점을 지형 속으로 넣는 깊이 (m)
SKIN_CAP = (0.5, 1.4)        # 지층(8~25 m) 윗부분 처마가 튀어나오는 정도 (m): 기본 + 단단함 × 범위
SKIN_CAP_F = (0.7, 0.86)     # 층 안 높이 비율에서 처마가 솟는 구간 (짧을수록 처마 밑이 깊게 파인다)
SKIN_BED = (1.2, 4.0)        # 층 안 잔 층(켜) 두께 범위 (m). 켜마다 앞뒤로 조금 나오고 들어가며, 켜 밑동이 파여 가로 그늘 줄이 생긴다
SKIN_BED_OFF = 0.45          # 켜마다 앞뒤로 나오고 들어가는 양 (m, ± × (0.6 + 단단함))
SKIN_BED_CUT = 0.35          # 켜 밑동이 파인 깊이 (m)
SKIN_JOINT = (3.5, 10.0)     # 세로 절리 간격 범위 (m, 켜마다 다르고 엇갈린다) → 덩이마다 앞뒤로 ± SKIN_BLOCK
SKIN_BLOCK = 0.45            # 절리 덩이가 앞뒤로 엇갈리는 양 (m. 둥근 구멍(벌집)은 덩이가 아니라 작은 빈 칸 가장자리를 묻은 탓이었다 → SKIN_HOLE_FILL·SKIN_ROW_SLOPE 로 고침). 덩이마다 면이 좌우·위아래로 조금씩 기울어(SKIN_FACET) 깨진 면처럼 빛이 다르게 든다
SKIN_FACET = (0.15, 0.25)    # 덩이 면 기울기 (좌우 m/m, 위아래 켜 안에서 m). 덩이마다 빛이 다르게 들어 깨진 면으로 읽힌다 (0.06·0.15 는 벽이 다시 뭉개졌다)
SKIN_JOINT_CUT = 0.2         # 절리 틈이 파인 깊이 (m)
SKIN_BULGE = 0.5             # 큰 부풂 (m, 50 m 무늬)
SKIN_REL_MIN = 1.1           # 요철 합을 이만큼 앞으로 민다 (m). 더 깊이 파인 곳은 기본 거리(SKIN_BASE)에서 평평하게 멈춘다 (지형 속으로 들어가지 않게)
SKIN_FOOT_FADE = (1.0, 6.0)  # 매끈하게 고른 발치 선 위 이 높이(m) 사이에서 요철이 0 → 다 든다 (발치에 선 사람이 덮개에 파묻히지 않게)
SKIN_FOOT_DIP = 2.5          # 발치 선 위 이 높이(m)까지 덮개가 지형 속(−SKIN_SINK)에서 SKIN_BASE 로 올라온다 (아래 경계가 계단으로 보이지 않게)
SKIN_FOOT_EXT = 2.0          # 발치 선 아래로 덮개를 더 내리는 높이 (m, 덜 가파른 너덜 위. 지형 속에 묻힌다)
SKIN_FOOT_SMOOTH = (4, 6)    # 발치 선 고르기: 옆 ±4 열의 가장 낮은 발치 → ±6 열 평균 두 번
SKIN_SIDE_FADE = (0.35, 0.7) # 옆 가장자리에서 1·2 번째 정점의 요철 비율 (3 번째부터 1)
SKIN_UV_WARP = 0.7           # u 를 흔드는 양 (m, 21 m 무늬. 세로 반복 무늬가 격자로 줄 서지 않게)
SKIN_SEAM_BLEND = 60.0       # 둘레 이음매(열 0 = 마지막 열) 앞 이 길이(m)에서 노이즈를 처음 값으로 섞는다
SKIN_CHUNK = (64, 48)        # 조각 크기 (열 수, 행 수) = 약 80 m × 48 m
SKIN_LOD_END = (150.0, 300.0, 500.0)  # LOD0·1·2 가 끝나는 거리 (조각 가운데까지 m). 조각이 80 × 48 m 라 30~75 m 벽이 LOD0 이게. 500 m 에서 안개 99.7% → 사라진다
SKIN_LOD_SIZE = 20.0         # LODGroup.size (전환 화면 높이 = size / (1.041 × 거리), 시야 55°)
SKIN_SHADOW_LODS = 2         # 그림자를 드리우는 LOD 수 (LOD0·1: 처마 그늘. LOD2 는 그림자 거리 150 m 밖)
SKIN_STRIP = (2048, 0.25)    # 지층 밝기 띠 텍스처: 줄 수, 한 줄 높이 (m)
SKIN_STRIP_W = (64, 360.0)   # 띠 텍스처 가로 칸 수, 가로 한 번 되풀이 길이 (m, 둘레 길이를 나누어 떨어지게 맞춘다). 칸마다 띠 진하기 0.35~1
SKIN_KEEP_NEAR = ("rock", "cliff", "rubble", "roots", "stump", "log", "bush", "bramble", "fern", "grass", "weeds", "reed",
                  "vine", "moss", "flower", "mushroom", "bones", "skull")   # 덮개와 겹쳐도 되는 소품 (이름이 이것으로 시작). 나머지는 덮개에 구멍
MAGIC = b"NCLF"
VERSION = 1


def _bilinear(h, x, z):
    n = h.shape[0] - 1
    x = np.clip(x, 0, n - 1e-3)
    z = np.clip(z, 0, n - 1e-3)
    x0 = np.floor(x).astype(np.int32)
    z0 = np.floor(z).astype(np.int32)
    fx = (x - x0).astype(np.float32)
    fz = (z - z0).astype(np.float32)
    a = h[z0, x0] * (1 - fx) + h[z0, x0 + 1] * fx
    b = h[z0 + 1, x0] * (1 - fx) + h[z0 + 1, x0 + 1] * fx
    return a * (1 - fz) + b * fz


def ref_curve(bounds, gate):
    """둘레 기준선 (반시계, 남쪽 변 서쪽 끝에서 시작). 반환 = 점 (n+1, 2) (마지막 = 처음), 바깥 법선 (n+1, 2), 열 간격 m"""
    (x0b, z0b), (x1b, z1b) = bounds
    e, R = SKIN_INSET, SKIN_CORNER_R
    xa, xb, za, zb = x0b + e, x1b - e, z0b + e, z1b - e
    gx, gz = gate
    d = 0.2

    def zn(x):          # 북쪽 기준선: 봉인문 둘레를 worldgen 의 북쪽 선(문 줄까지 당김)만큼, 더 넓고 완만하게 당긴다
        return zb - (z1b - gz) * (1 - ss(np.abs(x - gx), SKIN_GATE_PULL[0], SKIN_GATE_PULL[1]))

    def arc(cx, cz, a0, a1):
        a = np.radians(np.arange(a0, a1, d / R * 180 / np.pi))
        return np.stack([cx + R * np.cos(a), cz + R * np.sin(a)], 1)

    parts = []
    x = np.arange(xa + R, xb - R, d); parts.append(np.stack([x, np.full_like(x, za)], 1))
    parts.append(arc(xb - R, za + R, -90, 0))
    z = np.arange(za + R, zb - R, d); parts.append(np.stack([np.full_like(z, xb), z], 1))
    parts.append(arc(xb - R, zb - R, 0, 90))
    x = np.arange(xb - R, xa + R, -d); parts.append(np.stack([x, zn(x)], 1))
    parts.append(arc(xa + R, zb - R, 90, 180))
    z = np.arange(zb - R, za + R, -d); parts.append(np.stack([np.full_like(z, xa), z], 1))
    parts.append(arc(xa + R, za + R, 180, 270))
    P = np.concatenate(parts + [parts[0][:1]], 0)
    seg = np.hypot(*np.diff(P, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    L = s[-1]
    n = int(round(L / SKIN_DS / 4)) * 4          # 4 의 배수: LOD1·2 (2·4 열 건너뛰기)도 마지막 열 = 첫 열
    si = np.linspace(0, L, n + 1)
    C = np.stack([np.interp(si, s, P[:, 0]), np.interp(si, s, P[:, 1])], 1)
    C[-1] = C[0]
    # 접선 → 바깥 법선 (반시계 진행의 오른쪽). 모서리 이음새에서 꺾이지 않게 조금 흐린다
    Cl = np.concatenate([C[-9:-1], C, C[1:9]], 0)
    T = Cl[2:] - Cl[:-2]
    k = np.ones(9) / 9
    T = np.stack([np.convolve(T[:, 0], k, 'same'), np.convolve(T[:, 1], k, 'same')], 1)[7:7 + n + 1]
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.stack([T[:, 1], -T[:, 0]], 1)
    N[-1] = N[0]
    return C, N, L / n


def strata_bounds(seed, thick):
    """worldgen.strata_steps 와 같은 층 경계 (같은 씨앗·두께 → 같은 층)"""
    rng = np.random.default_rng(seed)
    return np.concatenate([[-300.0], -300.0 + np.cumsum(rng.uniform(thick[0], thick[1], 80))]).astype(np.float64)


def strata_tilt(x, z, tilt):
    """worldgen.mountain_face 의 지층 기울기 노이즈 (q = 높이 + 이 값)"""
    x = np.asarray(x, np.float32)
    z = np.asarray(z, np.float32)
    return tilt * fbm(x, z, 1 / 700.0, 2, 960) + 2.5 * fbm(x, z, 1 / 60.0, 2, 961)


def _noise_uq(U, Q, freq, oct_, seed, Lu, ridge=False):
    """덮개 면 좌표 (u = 둘레 m, q = 지층 높이 m) 의 2차원 노이즈. 둘레 이음매 앞 SKIN_SEAM_BLEND m 에서 u − Lu 의 값과 섞어
    마지막 열 = 첫 열이 되게 한다"""
    f = ridged if ridge else fbm
    a = f(U, Q, freq, oct_, seed)
    w = ss(U, Lu - SKIN_SEAM_BLEND, Lu)
    if np.any(w > 0):
        m = w > 0
        b = f(U[m] - Lu, Q[m], freq, oct_, seed)
        a = a.copy()
        a[m] = a[m] * (1 - w[m]) + b * w[m]
    return a


def _erode_cols(ok, it):
    """같은 행 안에서 덮개 가장자리(옆)까지의 정점 수 (0 = 가장자리, it 이상은 it)"""
    dist = np.where(ok, it, 0).astype(np.int32)
    cur = ok.copy()
    for k in range(it):
        nb = cur.copy()
        nb[1:, :] &= cur[:-1, :]
        nb[:-1, :] &= cur[1:, :]
        nb[0, :] = False
        nb[-1, :] = False
        dist[cur & ~nb] = np.minimum(dist[cur & ~nb], k)
        cur = nb
    return dist


def _quads(G, step):
    """한 LOD 단계의 덮개 칸·정점 계산. G: 전체 격자 (열 × 행). step: 1·2·4 (행·열 건너뛰기)"""
    sl = (slice(None, None, step), slice(None, None, step))
    ok = G["ok"][sl]
    t, y = G["t"][sl], G["y"][sl]
    ds = G["ds"] * step
    q = ok[:-1, :-1] & ok[1:, :-1] & ok[:-1, 1:] & ok[1:, 1:]
    # 위아래 행: 면이 SKIN_ROW_SLOPE 보다 서 있어야 (평평한 턱 = 끊는다)
    dy = SKIN_DY * step
    ext = G["ext"][sl]
    rowj = (np.abs(t[:, 1:] - t[:, :-1]) <= dy / SKIN_ROW_SLOPE) | ext[:, 1:] | ext[:, :-1]     # 발치 아래 덮개(묻히는 곳)는 눕어도 된다
    q &= rowj[:-1, :] & rowj[1:, :]
    # 옆 열: 깊이가 크게 튀지 않게
    colj = (np.abs(t[1:, :] - t[:-1, :]) <= SKIN_COL_JUMP * ds) | ext[1:, :] | ext[:-1, :]
    q &= colj[:, :-1] & colj[:, 1:]
    # 면 방향 (접힌 칸 빼기): 칸의 두 대각선 외적이 골짜기 쪽을 보아야
    X, Z = G["x"][sl], G["z"][sl]
    P = np.stack([X, y, Z], -1)
    d1 = P[1:, 1:] - P[:-1, :-1]
    d2 = P[:-1, 1:] - P[1:, :-1]
    nrm = np.cross(d1, d2)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9
    Nx, Nz = G["N"][::step, 0], G["N"][::step, 1]
    inward = -(nrm[..., 0] * 0.5 * (Nx[:-1, None] + Nx[1:, None]) + nrm[..., 2] * 0.5 * (Nz[:-1, None] + Nz[1:, None]))
    q &= np.abs(inward) >= SKIN_FACING
    # 작은 구멍 채우기: 네 모서리가 땅에 닿았고 둘레 네 칸 중 셋 넘게 덮인 빈 칸
    hit = G["hit"][sl]
    hq = hit[:-1, :-1] & hit[1:, :-1] & hit[:-1, 1:] & hit[1:, 1:]
    for _ in range(SKIN_HOLE_FILL):
        nh = np.zeros(q.shape, np.int32); nv = np.zeros(q.shape, np.int32)
        nh[1:] += q[:-1]; nh[:-1] += q[1:]; nv[:, 1:] += q[:, :-1]; nv[:, :-1] += q[:, 1:]
        q = q | (hq & (nh + nv >= 3))
    # 짧은 가로 구멍: 같은 행에서 양쪽이 덮인 SKIN_HOLE_RUN 칸 이하의 빈 칸 줄 (작은 턱 하나로 빠진 2 × 2 구멍 → 가장자리가 묻혀 둥근 구멍이 났다).
    # 더 긴 빈 줄은 지층 턱이라 그대로 둔다
    nv = np.zeros(q.shape, np.int32); nv[:, 1:] += q[:, :-1]; nv[:, :-1] += q[:, 1:]
    fill = np.zeros_like(q)
    for j in range(q.shape[1]):
        col = q[:, j]
        miss = np.nonzero(~col)[0]
        if not len(miss):
            continue
        br = np.nonzero(np.diff(miss) > 1)[0]
        starts = np.concatenate([[miss[0]], miss[br + 1]])
        ends = np.concatenate([miss[br], [miss[-1]]])
        for a, b in zip(starts, ends):
            if b - a + 1 <= SKIN_HOLE_RUN and a > 0 and b < len(col) - 1 and col[a - 1] and col[b + 1] \
                    and hq[a:b + 1, j].all() and (nv[a:b + 1, j] >= 1).all():
                fill[a:b + 1, j] = True
    q = q | fill
    # 부스러기 빼기: 같은 행에서 SKIN_MIN_RUN 칸보다 짧게 이어진 조각, 위아래 이웃이 하나도 없는 칸
    for _ in range(2):
        up = np.zeros_like(q); up[:, :-1] = q[:, 1:]
        dn = np.zeros_like(q); dn[:, 1:] = q[:, :-1]
        q &= up | dn
        run = np.zeros(q.shape, np.int32)
        r = np.zeros(q.shape[1], np.int32)
        for i in range(q.shape[0]):
            r = np.where(q[i], r + 1, 0)
            run[i] = r
        # 뒤에서 앞으로 길이를 퍼뜨린다
        best = np.zeros(q.shape[1], np.int32)
        for i in range(q.shape[0] - 1, -1, -1):
            best = np.where(q[i], np.maximum(best, run[i]), 0)
            run[i] = best
        q &= run >= SKIN_MIN_RUN
    return q


def _march(h, C, N, ys, tk, k_look):
    """열(광선)마다 행 높이 ys 에서 처음 땅에 닿는 광선 거리 T (없으면 nan), 광선 처음 k_look 표본 안의 가장 낮은 땅 높이"""
    nc, nr = len(C), len(ys)
    T = np.full((nc, nr), np.nan, np.float32)
    ystart = np.zeros(nc, np.float32)
    CH = 256
    for c0 in range(0, nc, CH):
        c1 = min(nc, c0 + CH)
        RX = C[c0:c1, 0, None] + N[c0:c1, 0, None] * tk[None, :]
        RZ = C[c0:c1, 1, None] + N[c0:c1, 1, None] * tk[None, :]
        HS = _bilinear(h, RX, RZ)
        k0 = np.argmin(HS[:, :k_look], axis=1)
        H2 = HS.copy()
        H2[np.arange(HS.shape[1])[None, :] < k0[:, None]] = -1e9
        M = np.maximum.accumulate(H2, axis=1)
        for i in range(c1 - c0):
            g0 = HS[i, k0[i]]
            ystart[c0 + i] = g0
            kk = np.searchsorted(M[i], ys, side="left")
            good = (kk > k0[i]) & (kk < len(tk)) & (ys > g0 + 0.25)
            kk = np.clip(kk, 1, len(tk) - 1)
            ha, hb = HS[i, kk - 1], HS[i, kk]
            fr = np.clip((ys - ha) / np.maximum(hb - ha, 1e-6), 0, 1)
            T[c0 + i] = np.where(good, tk[kk - 1] + fr * SKIN_RAY_STEP, np.nan)
    return T, ystart


def build_grid(h, bounds, gate, objects, meta, log=print):
    """광선 격자: 열마다 행(높이)마다 지형에 처음 닿는 점. 반환 G (열 × 행 배열)"""
    C, N, ds = ref_curve(bounds, gate)
    nc = len(C)
    tk = np.arange(SKIN_RAY[0], SKIN_RAY[1] + 1e-6, SKIN_RAY_STEP, dtype=np.float32)
    ys = np.arange(SKIN_Y[0], SKIN_Y[1] + 1e-6, SKIN_DY, dtype=np.float32)
    nr = len(ys)
    hsm = box_blur(h, 1, passes=1)
    gz_, gx_ = np.gradient(hsm)
    slope = np.hypot(gx_, gz_).astype(np.float32)
    del gz_, gx_, hsm
    k_look = int((SKIN_GROUND_LOOK - SKIN_RAY[0]) / SKIN_RAY_STEP)
    T, ystart = _march(h, C, N, ys, tk, k_look)
    # 지형이 덮개 칸 사이로 비쳐 나오지 않게: 열·행 사이 반 칸 자리에서도 땅에 닿는 깊이를 재어, 정점 둘레(±반 칸)에서 가장 앞으로 나온 땅 깊이(Tsafe)를 둔다
    Cm = 0.5 * (C[:-1] + C[1:])
    Nm = 0.5 * (N[:-1] + N[1:])
    Nm /= np.linalg.norm(Nm, axis=1, keepdims=True)
    C2 = np.empty((2 * nc - 1, 2)); C2[0::2] = C; C2[1::2] = Cm
    N2 = np.empty((2 * nc - 1, 2)); N2[0::2] = N; N2[1::2] = Nm
    ys2 = np.arange(SKIN_Y[0] - 0.5 * SKIN_DY, SKIN_Y[1] + 0.5 * SKIN_DY + 1e-6, 0.5 * SKIN_DY, dtype=np.float32)   # 2 j + 1 = 행 j
    T2, _ = _march(h, C2, N2, ys2, tk, k_look)
    T2 = np.where(np.isnan(T2), np.inf, T2)
    T2p = np.pad(T2, ((1, 1), (0, 0)), constant_values=np.inf)
    Ts = np.full((nc, nr), np.inf, np.float32)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            Ts = np.minimum(Ts, T2p[1 + 2 * np.arange(nc) + di][:, 2 * np.arange(nr) + 1 + dj])
    Tsafe = np.where(np.isfinite(Ts), Ts, np.nan_to_num(T, nan=0.0)).astype(np.float32)
    del T2, T2p, Ts
    X = C[:, 0, None] + N[:, 0, None] * T
    Z = C[:, 1, None] + N[:, 1, None] * T
    Y = np.broadcast_to(ys[None, :], T.shape).astype(np.float32)
    hit = ~np.isnan(T)
    sl_hit = np.where(hit, _bilinear(slope, np.nan_to_num(X), np.nan_to_num(Z)), 0)
    ok = hit & (sl_hit >= SKIN_SLOPE)
    # 낱 정점 구멍 메우기: 땅에 닿았고 둘레 8 정점 중 7 넘게 덮이는 정점 (한 점만 덜 가팔라 둘레 네 칸이 빠지면 가장자리가 묻혀 둥근 구멍이 났다)
    for _ in range(SKIN_HOLE_FILL):
        okp = np.pad(ok, 1)
        nb8 = sum(okp[1 + di:1 + di + nc, 1 + dj:1 + dj + nr].astype(np.int32) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj)
        ok = ok | (hit & (nb8 >= 7))          # 7: 낱 정점만 (지층 턱 줄 = 위아래 6 이웃은 메우지 않는다. 메우면 턱이 덮여 벽이 뭉개졌다)
    # 겹치면 안 되는 소품 둘레를 비운다 (덮개가 아치·사당·석상 앞을 가리지 않게)
    holes = 0
    if objects:
        keep = tuple(SKIN_KEEP_NEAR)
        # 기준선 점 근처만 본다
        for o in objects:
            a = o["a"]
            if a.startswith(keep):
                continue
            px, py, pz = o["p"]
            dc = np.hypot(C[:, 0] - px, C[:, 1] - pz)
            i0 = int(np.argmin(dc))
            # 기준선 바깥 쪽(벽 쪽)에 있어야 한다
            if np.dot([px - C[i0, 0], pz - C[i0, 1]], N[i0]) < -15.0:
                continue
            sz = (meta.get(a) or {}).get("_size") or [1.0, 1.0, 1.0]
            s = float(o.get("s", 1.0))
            r = 0.5 * math.hypot(sz[0], sz[1]) * s + 0.5
            y0, y1 = py - 0.5, py + sz[2] * s + 0.5
            w = int(r / ds) + 8
            ii = np.arange(i0 - w, i0 + w + 1) % (nc - 1)
            jj = np.nonzero((ys >= y0 - SKIN_DY) & (ys <= y1 + SKIN_DY))[0]
            if not len(jj):
                continue
            sub = ok[np.ix_(ii, jj)]
            if not sub.any():
                continue
            dx = X[np.ix_(ii, jj)] - px
            dz = Z[np.ix_(ii, jj)] - pz
            near = sub & (dx * dx + dz * dz < r * r)
            if near.any():
                holes += 1
                blk = ok[np.ix_(ii, jj)]
                blk[near] = False
                ok[np.ix_(ii, jj)] = blk
    # 발치 선: 열마다 덮개 맨 아래 높이 → 옆 열의 가장 낮은 값 → 평균으로 고른다. 그 선 아래 SKIN_FOOT_EXT m 까지 덜 가파른 땅도 덮는다 (지형 속에 묻힌다)
    jj = np.where(ok.any(1), np.argmax(ok, 1), nr - 1)
    yf = np.where(ok.any(1), ys[jj], ystart + 30.0).astype(np.float64)
    r0, r1 = SKIN_FOOT_SMOOTH
    ext_ = np.concatenate([yf[-1 - r0 - r1 * 2:-1], yf, yf[1:1 + r0 + r1 * 2]])
    mn = np.min(np.stack([np.roll(ext_, k) for k in range(-r0, r0 + 1)]), 0)
    for _ in range(2):
        mn = np.convolve(mn, np.ones(2 * r1 + 1) / (2 * r1 + 1), "same")
    foot = mn[r0 + r1 * 2:r0 + r1 * 2 + nc].astype(np.float32)
    foot[-1] = foot[0]
    ext = hit & ~ok & (Y >= foot[:, None] - SKIN_FOOT_EXT) & (Y < yf[:, None])
    ok |= ext
    ok[-1] = ok[0]
    log("산 벽 덮개: 기준선 %.0f m, 열 %d (간격 %.2f m), 행 %d, 땅에 닿은 점 %d, 가파른 점 %d, 소품 둘레 구멍 %d 곳" % (
        ds * (nc - 1), nc, ds, nr, int(hit.sum()), int(ok.sum()), holes))
    # 열의 둘레 좌표 u: 열 사이 실제 수평 간격(행 중앙값)을 누적. 끝 = 타일 크기의 정수배 (이음매에서 무늬가 이어지게)
    gap = np.hypot(X[1:] - X[:-1], Z[1:] - Z[:-1])
    both = ok[1:] & ok[:-1]
    med = np.array([np.median(g[b]) if b.sum() > 3 else ds for g, b in zip(gap, both)], np.float32)
    med = np.clip(np.convolve(np.concatenate([med[-6:], med, med[:6]]), np.ones(13) / 13, 'same')[6:-6], ds * 0.9, ds * 3.0)
    U = np.concatenate([[0], np.cumsum(med)])
    Lu = U[-1]
    nt = max(1, round(Lu / SKIN_TILE))
    U *= nt * SKIN_TILE / Lu
    return dict(C=C, N=N, ds=ds, x=np.nan_to_num(X).astype(np.float32), z=np.nan_to_num(Z).astype(np.float32), y=Y, t=np.nan_to_num(T),
                ok=ok, ext=ext, hit=hit, tsafe=Tsafe, slope=sl_hit.astype(np.float32), foot=foot, U=U.astype(np.float64), Lu=float(U[-1]), ys=ys, ystart=ystart, holes=holes)


def displace(G, q_ok, step, B, hard, tilt, foot_y, BEDS):
    """한 LOD 단계의 정점 위치(변위 뒤)·UV·법선. q_ok: 칸 마스크 (열−1 × 행−1)"""
    sl = (slice(None, None, step), slice(None, None, step))
    X, Y, Z, T = G["x"][sl], G["y"][sl], G["z"][sl], G["t"][sl]
    N = G["N"][::step]
    U = G["U"][::step]
    ni, nj = X.shape
    used = np.zeros((ni, nj), bool)
    used[:-1, :-1] |= q_ok; used[1:, :-1] |= q_ok; used[:-1, 1:] |= q_ok; used[1:, 1:] |= q_ok
    # 가장자리 정점 = 둘레 네 칸 중 비어 있는 칸이 있는 정점
    full = np.zeros((ni + 1, nj + 1), np.int32)
    full[1:-1, 1:-1] = q_ok
    nq = full[:-1, :-1] + full[1:, :-1] + full[:-1, 1:] + full[1:, 1:]
    edge = used & (nq < 4)
    UU = np.broadcast_to(U[:, None], X.shape).astype(np.float64)
    Q = (Y + strata_tilt(X, Z, tilt)).astype(np.float64)
    k = np.clip(np.searchsorted(B, Q, side="right"), 1, len(B) - 1)
    b0 = B[k - 1]
    th = B[k] - b0
    f = np.clip((Q - b0) / th, 0, 1)
    hd = hard[k]
    Lu = G["Lu"]
    Uf, Qf = UU.astype(np.float32), Q.astype(np.float32)
    # 처마: 지층 윗부분이 튀어나오고 (그 위는 다음 층의 턱), 길이 방향으로 세기가 바뀐다
    capv = 0.35 + 0.65 * ss(_noise_uq(Uf, Qf, 1 / 40.0, 2, 981, Lu), -0.35, 0.35)
    rel = (SKIN_CAP[0] + SKIN_CAP[1] * hd) * ss(f, SKIN_CAP_F[0], SKIN_CAP_F[1]) * capv
    # 켜 (층 안 1.2~4 m): 켜마다 앞뒤로, 켜 밑동은 파인다
    SB, sbk, sbr = BEDS
    m = np.clip(np.searchsorted(SB, Q, side="right"), 1, len(SB) - 1)
    g = np.clip((Q - SB[m - 1]) / (SB[m] - SB[m - 1]), 0, 1)
    rel = rel + SKIN_BED_OFF * (sbr[m, 0] * 2 - 1) * (0.6 + hd)
    if step <= 2:
        rel = rel - SKIN_BED_CUT * (1 - ss(g, 0.04, 0.3))
        # 세로 절리: 켜마다 간격·자리가 다르다. 덩이마다 앞뒤로 엇갈리고 틈은 파인다
        js = SKIN_JOINT[0] + (SKIN_JOINT[1] - SKIN_JOINT[0]) * sbr[m, 1]
        cu = (UU + 0.8 * _noise_uq(Uf, Qf, 1 / 13.0, 1, 988, Lu)) / js + sbr[m, 2] * 7.0
        c = np.floor(cu).astype(np.int64)
        hsh = ((m.astype(np.int64) * 73856093) ^ (c * 19349663)) & 0xffffff
        h1, h2, h3 = (hsh & 0xff) / 255.0, ((hsh >> 8) & 0xff) / 255.0, ((hsh >> 16) & 0xff) / 255.0
        fr = cu - c
        rel = rel + SKIN_BLOCK * (h1 * 2 - 1) * (0.5 + hd)
        rel = rel + SKIN_FACET[0] * (h2 * 2 - 1) * (fr - 0.5) * js + SKIN_FACET[1] * (h3 * 2 - 1) * (g - 0.5) * 2
        dj = np.minimum(fr, 1 - fr) * js
        rel = rel - SKIN_JOINT_CUT * (1 - ss(dj, 0.2, 0.7))
    rel = rel + SKIN_BULGE * (0.5 + 0.5 * _noise_uq(Uf, Qf, 1 / 50.0, 2, 986, Lu))
    # 발치: 고른 발치 선 위로 요철이 천천히 들고, 덮개가 지형 속에서 앞으로 올라온다 (아래 경계가 계단으로 보이지 않게)
    fy = foot_y[::step]
    dfoot = Y - fy[:, None]
    fade = ss(dfoot, SKIN_FOOT_FADE[0], SKIN_FOOT_FADE[1])
    # 묻는 깊이: 덜 가파른 땅(발치 아래 너덜)에서는 수평으로 더 깊이 (수직으로 SKIN_SINK 넘게 땅 속이게)
    sk = SKIN_SINK * np.maximum(1.0, 1.0 / np.maximum(G["slope"][sl], 0.25))
    base = -sk + (SKIN_BASE + sk) * ss(dfoot, 0.0, SKIN_FOOT_DIP)
    dist = _erode_cols(used, 3)
    sidef = np.select([dist <= 0, dist == 1, dist == 2], [0.0, SKIN_SIDE_FADE[0], SKIN_SIDE_FADE[1]], 1.0)
    d = base + np.maximum(rel + SKIN_REL_MIN, 0) * fade * sidef
    d = np.where(edge, -sk, d)
    Td = T - d
    # 칸 사이로 땅이 비쳐 나오지 않게 (가장자리 정점은 일부러 묻는다)
    ts = G["tsafe"]
    if step > 1:
        r = step // 2
        tp = np.pad(ts, ((r, r), (r, r)), mode="edge")
        acc = ts.copy()
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                acc = np.minimum(acc, tp[r + di:r + di + ts.shape[0], r + dj:r + dj + ts.shape[1]])
        ts = acc
    ts = ts[sl]
    Td = np.where(edge | (dfoot < SKIN_FOOT_DIP), Td, np.minimum(Td, ts - SKIN_CLEAR))   # 발치 선 둘레는 일부러 땅 속에서 올라온다
    PX = (G["C"][::step, 0, None] + N[:, 0, None] * Td).astype(np.float32)
    PZ = (G["C"][::step, 1, None] + N[:, 1, None] * Td).astype(np.float32)
    PY = Y.astype(np.float32)
    # UV: u (둘레 m, 21 m 무늬로 조금 흔든다), v = q (지층 높이 m)
    Uw = UU + SKIN_UV_WARP * _noise_uq(Uf, Qf, 1 / 21.0, 2, 991, Lu)
    # 법선: 변위 뒤 격자의 중앙 차분 (쓰이는 이웃만). 골짜기 쪽을 보게
    P = np.stack([PX, PY, PZ], -1)

    def diff(axis):
        a = np.zeros_like(P)
        if axis == 0:
            fwd = np.zeros((ni, nj), bool); fwd[:-1] = used[1:] & used[:-1]
            bwd = np.zeros((ni, nj), bool); bwd[1:] = used[:-1] & used[1:]
            a[:-1] += np.where(fwd[:-1, :, None], P[1:] - P[:-1], 0)
            a[1:] += np.where(bwd[1:, :, None], P[1:] - P[:-1], 0)
        else:
            fwd = np.zeros((ni, nj), bool); fwd[:, :-1] = used[:, 1:] & used[:, :-1]
            bwd = np.zeros((ni, nj), bool); bwd[:, 1:] = used[:, :-1] & used[:, 1:]
            a[:, :-1] += np.where(fwd[:, :-1, None], P[:, 1:] - P[:, :-1], 0)
            a[:, 1:] += np.where(bwd[:, 1:, None], P[:, 1:] - P[:, :-1], 0)
        return a
    du, dv = diff(0), diff(1)
    nrm = np.cross(du, dv)
    ln = np.linalg.norm(nrm, axis=-1, keepdims=True)
    inward = np.stack([-N[:, 0, None] * np.ones((1, nj)), np.zeros((ni, nj)), -N[:, 1, None] * np.ones((1, nj))], -1)
    nrm = np.where(ln > 1e-6, nrm / np.maximum(ln, 1e-9), inward)
    flip = (nrm * inward).sum(-1) < 0
    nrm[flip] *= -1
    # 이음매: 마지막 열 = 첫 열
    if (ni - 1) * step == len(G["C"]) - 1:
        PX[-1], PY[-1], PZ[-1] = PX[0], PY[0], PZ[0]
        nrm[-1] = nrm[0]
    return dict(used=used, edge=edge, px=PX, py=PY, pz=PZ, td=Td.astype(np.float64), u=Uw.astype(np.float64), v=Q, n=nrm.astype(np.float32), d=d)


def sub_beds(B, seed=970):
    """지층마다 1.2~4 m 켜로 나눈 경계. 반환 (켜 경계 SB, 켜마다 지층 번호, 켜마다 난수 3 개)"""
    rng = np.random.default_rng(seed)
    SB, kk = [B[0]], []
    for k in range(1, len(B)):
        q = B[k - 1]
        while True:
            th = rng.uniform(SKIN_BED[0], SKIN_BED[1])
            if q + th > B[k] - SKIN_BED[0] * 0.6:
                break
            q += th
            SB.append(q); kk.append(k)
        SB.append(B[k]); kk.append(k)
    SB = np.array(SB, np.float64)
    kk = np.array([0] + kk, np.int64)
    return SB, kk, rng.random((len(SB) + 1, 3))


def strip_colors(B, BEDS, lut_seed, q0, n, dq, ncol):
    """지층 밝기 띠 (선형 RGBA, 128 = ×1), 모양 (줄 n, 칸 ncol, 4). 층 번호는 worldgen.paint 의 지층 칠(어두운 층 mud · 흙빛 층 dirt · 맨바위)과 같다.
    켜마다 밝기가 조금씩 다르고 켜 밑동(파인 줄)은 조금 어둡다. 칸(둘레 방향)마다 띠 진하기가 0.35~1 사이로 천천히 바뀐다 (되풀이 이음매 없음)"""
    lut = np.random.default_rng(lut_seed).random(256).astype(np.float32)
    rnd = np.random.default_rng(lut_seed + 7).random(256).astype(np.float32)
    SB, sbk, sbr = BEDS
    q = q0 + (np.arange(n) + 0.5) * dq
    k = np.clip(np.searchsorted(B, q, side="right"), 1, len(B) - 1)
    lay = lut[np.clip(k, 0, 255)]
    f = np.clip((q - B[k - 1]) / (B[k] - B[k - 1]), 0, 1)
    m = np.clip(np.searchsorted(SB, q, side="right"), 1, len(SB) - 1)
    g = np.clip((q - SB[m - 1]) / (SB[m] - SB[m - 1]), 0, 1)
    base = 0.9 + 0.18 * rnd[np.clip(k, 0, 255)]
    base = base * (0.95 + 0.1 * sbr[m, 0])                     # 켜마다 ±5%
    col = np.stack([base, base, base], 1)
    dark = lay < 0.42
    warm = lay > 0.68
    col[dark] = np.stack([base[dark] * 0.74, base[dark] * 0.71, base[dark] * 0.82], 1)
    col[warm] = np.stack([base[warm] * 1.12, base[warm] * 1.04, base[warm] * 0.94], 1)
    cut = 0.1 + 0.15 * sbr[m, 1]                               # 켜 밑동 (파인 줄의 때·그늘). 켜마다 세기가 다르다
    col *= (1 - cut + cut * ss(g, 0.0, 0.3))[:, None]
    col *= (1.0 + 0.12 * ss(f, 0.8, 0.97))[:, None]            # 처마 끝은 조금 밝게 (닳은 모서리)
    kk = np.array([0.25, 0.5, 0.25])
    col = np.stack([np.convolve(np.pad(col[:, c], 1, mode="edge"), kk, "valid") for c in range(3)], 1)
    # 둘레 방향 진하기 (주기 함수: 정수 진동수 사인의 합)
    th = (np.arange(ncol) + 0.5) / ncol * 2 * np.pi
    rr = np.random.default_rng(lut_seed + 11)
    w = sum(rr.uniform(0.5, 1.0) / fq * np.sin(fq * th + rr.uniform(0, 2 * np.pi)) for fq in (1, 2, 3, 5))
    w = (w - w.min()) / max(w.max() - w.min(), 1e-6)
    kcol = 0.35 + 0.65 * w
    col2 = 1 + (col[:, None, :] - 1) * kcol[None, :, None]
    rgba = np.concatenate([np.clip(col2 * 128, 0, 255), np.full((n, ncol, 1), 255)], 2)
    return np.round(rgba).astype(np.uint8)


def _bits(a):
    return np.packbits(a.ravel().astype(np.uint8), bitorder="little").tobytes()


def _oct(n):
    """단위 법선 → 8면체 2 바이트"""
    x, y, z = n[..., 0], n[..., 1], n[..., 2]
    s = np.abs(x) + np.abs(y) + np.abs(z) + 1e-9
    ox, oy = x / s, y / s
    neg = z < 0
    tx = np.where(neg, (1 - np.abs(oy)) * np.sign(ox + 1e-12), ox)
    ty = np.where(neg, (1 - np.abs(ox)) * np.sign(oy + 1e-12), oy)
    return np.clip(np.round(tx * 127), -127, 127).astype(np.int8), np.clip(np.round(ty * 127), -127, 127).astype(np.int8)


def build(h, bounds, gate, objects, meta, out_data, strata_seed=967, strata_thick=(8.0, 25.0), tilt=55.0, lut_seed=968, log=print):
    """덮개를 만들어 <out_data>/cliffs.bin 에 쓴다. h = 최종 높이맵 [z, x] (height.r16 과 같은 값). 반환 = 요약 dict"""
    t0 = time.time()
    G = build_grid(h, bounds, gate, objects, meta, log)
    B = strata_bounds(strata_seed, strata_thick)
    hard = np.random.default_rng(969).random(len(B) + 1)
    hard = np.clip(hard * 1.15 - 0.1, 0, 1)
    BEDS = sub_beds(B)
    foot = G["foot"]
    levels = []
    for L in range(len(SKIN_LOD_END)):
        step = 1 << L
        q = _quads(G, step)
        D = displace(G, q, step, B, hard, tilt, foot, BEDS)
        D["q"] = q
        D["step"] = step
        # 대각선: 짧은 쪽 (턱 모서리가 지그재그가 되지 않게)
        P = np.stack([D["px"], D["py"], D["pz"]], -1)
        dA = np.linalg.norm(P[1:, 1:] - P[:-1, :-1], axis=-1)
        dB = np.linalg.norm(P[:-1, 1:] - P[1:, :-1], axis=-1)
        D["diag"] = dB < dA - 1e-4
        levels.append(D)
        log("  LOD%d (격자 %.1f × %.0f m): 칸 %d → 삼각형 %d" % (L, G["ds"] * step, SKIN_DY * step, int(q.sum()), int(q.sum()) * 2))
    # 지층 밝기 띠
    vq = levels[0]["v"][levels[0]["used"]]
    q0 = math.floor((vq.min() if len(vq) else 0.0) - 8.0)
    sn, sdq = SKIN_STRIP
    sw = SKIN_STRIP_W[0]
    sper = G["Lu"] / max(1, round(G["Lu"] / SKIN_STRIP_W[1]))      # 둘레 길이를 나누어 떨어지게 (이음매에서 이어진다)
    strip = strip_colors(B, BEDS, lut_seed, q0, sn, sdq, sw)
    # 걸을 수 있는 땅(bounds 안, 기울기 < 1) 6 m 격자 → 조각마다 카메라가 가장 가까이 갈 수 있는 거리 (그보다 먼 LOD 만 담는다)
    (x0b, z0b), (x1b, z1b) = bounds
    gx_ = np.arange(x0b + 3, x1b, 6.0)
    gz_ = np.arange(z0b + 3, z1b, 6.0)
    WX, WZ = np.meshgrid(gx_, gz_)
    gzh, gxh = np.gradient(h)
    wsl = _bilinear(np.hypot(gxh, gzh).astype(np.float32), WX, WZ)
    del gzh, gxh
    wk = wsl < 1.0
    WP = np.stack([WX[wk], _bilinear(h, WX[wk], WZ[wk]) + 1.7, WZ[wk]], 1)
    # 조각
    CI, CJ = SKIN_CHUNK
    ni, nj = G["x"].shape
    chunks = []
    skipped = [0] * len(levels)
    for ci in range(0, ni - 1, CI):
        for cj in range(0, nj - 1, CJ):
            if not levels[0]["q"][ci:ci + CI, cj:cj + CJ].any():
                continue
            q0p = levels[0]["q"][ci:ci + CI, cj:cj + CJ]
            sl0 = (slice(ci, ci + q0p.shape[0] + 1), slice(cj, cj + q0p.shape[1] + 1))
            u0 = levels[0]["used"][sl0]
            center = np.array([levels[0]["px"][sl0][u0].mean(), levels[0]["py"][sl0][u0].mean(), levels[0]["pz"][sl0][u0].mean()])
            dmin = float(np.sqrt(((WP - center) ** 2).sum(1)).min())
            first = next((L for L, e in enumerate(SKIN_LOD_END) if dmin < e), None)
            if first is None:
                continue
            ch = {"lv": [], "center": center, "first": first, "dmin": dmin}
            for L, D in enumerate(levels):
                st = D["step"]
                a0, b0 = ci // st, cj // st
                a1 = min((ci + CI) // st, D["q"].shape[0])
                b1 = min((cj + CJ) // st, D["q"].shape[1])
                q = D["q"][a0:a1, b0:b1]
                if L < first:
                    q = np.zeros_like(q)
                    skipped[L] += 1
                used = np.zeros((q.shape[0] + 1, q.shape[1] + 1), bool)
                used[:-1, :-1] |= q; used[1:, :-1] |= q; used[:-1, 1:] |= q; used[1:, 1:] |= q
                sl = (slice(a0, a1 + 1), slice(b0, b1 + 1))
                # 저장 순서: 행(j) 우선 = 인덱스 j × ni + i
                ord_ = np.nonzero(used.T.ravel())[0]
                ii, jj = ord_ % used.shape[0], ord_ // used.shape[0]
                lv = dict(ni=used.shape[0], nj=used.shape[1], q=q, diag=D["diag"][a0:a1, b0:b1],
                          cx=G["C"][::st][a0:a1 + 1, 0], cz=G["C"][::st][a0:a1 + 1, 1], nx=G["N"][::st][a0:a1 + 1, 0], nz=G["N"][::st][a0:a1 + 1, 1],
                          y0=float(G["ys"][::st][b0]), dy=SKIN_DY * st,
                          t=D["td"][sl][ii, jj], u=D["u"][sl][ii, jj], v=D["v"][sl][ii, jj], n=D["n"][sl][ii, jj])
                ch["lv"].append(lv)
            chunks.append(ch)
    path = os.path.join(out_data, "cliffs.bin")
    raw = io.BytesIO()
    w = raw.write
    w(MAGIC); w(struct.pack("<I", VERSION))
    w(struct.pack("<ff", SKIN_TILE, SKIN_LOD_SIZE))
    w(struct.pack("<I", len(SKIN_LOD_END))); w(struct.pack("<%df" % len(SKIN_LOD_END), *SKIN_LOD_END)); w(struct.pack("<I", SKIN_SHADOW_LODS))
    w(struct.pack("<ffIIf", float(q0), float(sn * sdq), sn, sw, float(sper))); w(strip.tobytes())   # 줄 r × 칸 c × RGBA
    w(struct.pack("<I", len(chunks)))
    tris = [0] * len(levels)
    verts = [0] * len(levels)
    rec_t = np.dtype([("t", "<u2"), ("u", "<u2"), ("v", "<u2"), ("n", "i1", 2)])
    for ch in chunks:
        w(struct.pack("<3f", *ch["center"].astype(np.float32)))
        w(struct.pack("<I", ch["first"]))
        for L, lv in enumerate(ch["lv"]):
            nq = int(lv["q"].sum())
            nv = len(lv["t"])
            w(struct.pack("<HHII", lv["ni"], lv["nj"], nv, nq))
            w(struct.pack("<ff", lv["y0"], lv["dy"]))
            w(np.stack([lv["cx"], lv["cz"], lv["nx"], lv["nz"]], 1).astype("<f4").tobytes())
            rng_ = []
            for key in ("t", "u", "v"):
                a = lv[key]
                lo, hi = (float(a.min()) - 0.01, float(a.max()) + 0.01) if nv else (0.0, 1.0)
                rng_ += [lo, hi]
            w(struct.pack("<6f", *rng_))
            w(_bits(lv["q"].T))                  # 칸 마스크, 인덱스 j × (ni − 1) + i
            w(_bits(lv["diag"].T))               # 대각선 (칸마다, 같은 순서)
            rec = np.zeros(nv, dtype=rec_t)
            for k_, key in enumerate(("t", "u", "v")):
                lo, hi = np.float32(rng_[2 * k_]), np.float32(rng_[2 * k_ + 1])
                rec[key] = np.round((lv[key] - lo) / max(hi - lo, 1e-6) * 65535).clip(0, 65535)
            ox, oy = _oct(lv["n"])
            rec["n"] = np.stack([ox, oy], 1)
            w(rec.tobytes())
            tris[L] += nq * 2
            verts[L] += nv
    data = raw.getvalue()
    with open(path, "wb") as fo:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fo, mtime=0, compresslevel=9) as gz:
            gz.write(data)
    size = os.path.getsize(path)
    log("산 벽 덮개: 조각 %d (LOD0 을 뺀 조각 %d, LOD1 까지 뺀 조각 %d: 걸을 땅에서 그 LOD 거리 안으로 못 간다), 정점 LOD0/1/2 %s, 삼각형 %s, 파일 %.1f MB (풀면 %.1f MB), %.0f 초" % (
        len(chunks), skipped[0], skipped[1], "/".join(str(v) for v in verts), "/".join(str(t) for t in tris), size / 1e6, len(data) / 1e6, time.time() - t0))
    return dict(chunks=len(chunks), verts=verts, tris=tris, bytes=size, holes=G["holes"])


# ───────────────────────── 읽기 (render_world.py, 성능 검사) ─────────────────────────
def _unbits(b, n):
    return np.unpackbits(np.frombuffer(b, np.uint8), bitorder="little")[:n].astype(bool)


def _unoct(ox, oy):
    x = ox.astype(np.float32) / 127.0
    y = oy.astype(np.float32) / 127.0
    z = 1 - np.abs(x) - np.abs(y)
    neg = z < 0
    tx = np.where(neg, (1 - np.abs(y)) * np.sign(x + 1e-12), x)
    ty = np.where(neg, (1 - np.abs(x)) * np.sign(y + 1e-12), y)
    v = np.stack([tx, ty, z], -1)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def read(path, meshes=True):
    """cliffs.bin → dict(tile, lod_size, lod_end, shadow_lods, strip_q0, strip_len, strip_period, strip (줄 × 칸 × 4 u8), chunks=[dict(center, first, lv=[...])])
    lv: ni, nj, nverts, nquads, (meshes=True 이면) pos (V×3, Unity 좌표), uv (V×2, m), nrm (V×3), tri (T×3, Unity 감김: 앞면 = 골짜기 쪽)"""
    with gzip.open(path, "rb") as f:
        b = f.read()
    o = 0

    def rd(fmt):
        nonlocal o
        v = struct.unpack_from(fmt, b, o)
        o += struct.calcsize(fmt)
        return v
    assert b[:4] == MAGIC, "cliffs.bin 머리가 다르다"
    o = 4
    ver, = rd("<I")
    tile, lsize = rd("<ff")
    nl, = rd("<I")
    lend = rd("<%df" % nl)
    shl, = rd("<I")
    q0, qlen, sn, sw, sper = rd("<ffIIf")
    strip = np.frombuffer(b, np.uint8, sn * sw * 4, o).reshape(sn, sw, 4)
    o += sn * sw * 4
    nch, = rd("<I")
    out = dict(version=ver, tile=tile, lod_size=lsize, lod_end=list(lend), shadow_lods=shl, strip_q0=q0, strip_len=qlen, strip_period=sper, strip=strip, chunks=[])
    rec_t = np.dtype([("t", "<u2"), ("u", "<u2"), ("v", "<u2"), ("n", "i1", 2)])
    for _ in range(nch):
        center = np.array(rd("<3f"))
        first, = rd("<I")
        ch = dict(center=center, first=first, lv=[])
        for L in range(nl):
            ni, nj, nv, nq = rd("<HHII")
            y0, dy = rd("<ff")
            cols = np.frombuffer(b, "<f4", ni * 4, o).reshape(ni, 4); o += ni * 16
            rg = rd("<6f")
            nqa = (ni - 1) * (nj - 1)
            nb = (nqa + 7) // 8
            qm = _unbits(b[o:o + nb], nqa); o += nb
            dg = _unbits(b[o:o + nb], nqa); o += nb
            rec = np.frombuffer(b, rec_t, nv, o); o += nv * rec_t.itemsize
            lv = dict(ni=ni, nj=nj, nverts=nv, nquads=nq)
            if meshes:
                # 칸 → 삼각형 (SPEC: a=(i,j) b=(i+1,j) c=(i+1,j+1) d=(i,j+1); 대각선 0 → abc, acd / 1 → abd, bcd)
                qm2 = qm.reshape(nj - 1, ni - 1)
                dg2 = dg.reshape(nj - 1, ni - 1)
                used = np.zeros((nj, ni), bool)
                used[:-1, :-1] |= qm2; used[:-1, 1:] |= qm2; used[1:, :-1] |= qm2; used[1:, 1:] |= qm2
                vj, vi = np.nonzero(used)
                t = rg[0] + rec["t"].astype(np.float64) / 65535.0 * (rg[1] - rg[0])
                u = rg[2] + rec["u"].astype(np.float64) / 65535.0 * (rg[3] - rg[2])
                v = rg[4] + rec["v"].astype(np.float64) / 65535.0 * (rg[5] - rg[4])
                c = cols[vi]
                pos = np.stack([c[:, 0] + c[:, 2] * t, y0 + vj * dy, c[:, 1] + c[:, 3] * t], 1)
                nrm = _unoct(rec["n"][:, 0], rec["n"][:, 1])
                idx = np.full(nj * ni, -1, np.int64)
                idx[used.ravel()] = np.arange(int(used.sum()))
                jj, ii = np.nonzero(qm2)
                a = idx[jj * ni + ii]; bb = idx[jj * ni + ii + 1]; cc = idx[(jj + 1) * ni + ii + 1]; d = idx[(jj + 1) * ni + ii]
                g = dg2[jj, ii]
                t1 = np.where(g[:, None], np.stack([a, bb, d], 1), np.stack([a, bb, cc], 1))
                t2 = np.where(g[:, None], np.stack([bb, cc, d], 1), np.stack([a, cc, d], 1))
                lv.update(pos=pos, uv=np.stack([u, v], 1), nrm=nrm, tri=np.concatenate([t1, t2], 0))
            ch["lv"].append(lv)
        out["chunks"].append(ch)
    return out


if __name__ == "__main__":
    # 단독 실행: python3 cliffskin.py <월드 폴더(Data~ 가 있는 곳)> <소품 폴더> [출력 Data~ 폴더]
    # 이미 만든 월드(height.r16, objects.json)로 덮개만 다시 만든다 (worldgen main 이 하는 것과 같은 값)
    import json, glob
    import worldgen as WG
    world = sys.argv[1]
    data = os.path.join(world, "Data~")
    out = sys.argv[3] if len(sys.argv) > 3 else data
    os.makedirs(out, exist_ok=True)
    meta = WG.load_manifest(sys.argv[2])
    hh = np.fromfile(os.path.join(data, "height.r16"), "<u2").reshape(WG.RES, WG.RES).astype(np.float32) * (WG.HMAX / 65535.0)
    objs = json.load(open(os.path.join(data, "objects.json")))["objects"]
    build(hh, WG.BOUNDS, WG.GATE, objs, meta, out, strata_seed=967, strata_thick=WG.FACE_STEP_VAR, tilt=WG.FACE_TILT, lut_seed=968)
