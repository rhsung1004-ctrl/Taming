# -*- coding: utf-8 -*-
"""소품 근접 디테일 텍스처 생성기 (URP Lit 의 Detail Inputs 용).

굽힌 텍스처(1024~2048)는 가까이 가면 흐리므로, 이어 붙는 잔무늬를 URP Lit 의 Detail 로 겹친다.
  stone: 돌의 결(잔 알갱이)·작은 구멍·가는 금      (반복 0.9 m 기준)
  wood : 나무 결·결 따라 갈라진 틈                  (반복 0.75 m 기준)
  bone : 잔구멍·거미줄 같은 잔금·옅은 세로 결       (반복 0.6 m 기준)
  metal: 녹 얼룩(거친 면, 붉은 기)·부식 구멍·옅은 망치 자국 (반복 0.6 m 기준)

규칙 (URP 6000.0 LitInput.hlsl 과 맞춘다)
- albedo: 회색 0.5 중심. URP 는 _DETAIL_MULX2 일 때 "기본 색 × (디테일 × 2)" 로 섞는다 (LitInput.hlsl 224·227 줄).
  Unity 에서 sRGB 를 끄고(선형) 가져오므로 화소값 128 ≈ 0.5 → ×2 = 1 (변화 없음). 셰이더 기본값 "linearGrey" 와 같은 뜻.
- normal: OpenGL 방식 (초록 = 위, +V). Unity 노멀맵과 같다. 높이장에서 미분해 만든다.
- 모두 주기 함수로 만들어 끝이 이어진다 (FFT 스펙트럼 잡음, 감싸는 Worley, np.roll 미분).
- 굽힌 그림과 싸우지 않게 은은하게: 색은 ±5~8 %, 노멀은 평평한 면을 울퉁불퉁하게 만들지 않도록
  중간 크기 굴곡은 빼고 알갱이·구멍·금 같은 잔것만 넣는다 (녹은 밀랍처럼 보이던 문제를 되풀이하지 않게).

실행: python3 Tools/BlenderKit/detailtex.py [--size 1024] [--out 폴더] [--sheet 미리보기.png]
출력: Assets/_Necro/Art/Materials/Detail/detail_<종류>_albedo.png, detail_<종류>_normal.png
같은 씨앗이면 늘 같은 그림이 나온다.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
DEFAULT_OUT = os.path.join(REPO, "Assets", "_Necro", "Art", "Materials", "Detail")
KINDS = ("stone", "wood", "bone", "metal")
# 한 장이 덮는 실제 크기 (m). Unity NecroProps.DetailRepeat 와 같아야 한다
REPEAT_M = {"stone": 0.9, "wood": 0.75, "bone": 0.6, "metal": 0.6}


# ───────────────────────── 주기 잡음 ─────────────────────────
def _freq(n):
    f = np.fft.fftfreq(n) * n          # 한 장에 몇 번 반복하는 주파수인지 (사이클/장)
    return np.meshgrid(f, f)           # fx: 가로(열), fy: 세로(행)


def spectral(n, rng, fmin, fmax, beta=1.0, aniso=1.0, angle=0.0):
    """주기 잡음 (평균 0, 표준편차 1). fmin~fmax 사이클/장 띠, 진폭 ∝ f^(-beta/2).
    aniso > 1 이면 한 방향(angle, 0 = 세로 V 방향)으로 길게 늘어난 결."""
    fx, fy = _freq(n)
    if aniso != 1.0 or angle:
        c, s = np.cos(angle), np.sin(angle)
        u = fx * c - fy * s           # 결을 가로지르는 방향
        v = fx * s + fy * c           # 결을 따라가는 방향
        f = np.sqrt(u * u + (v * aniso) ** 2)
    else:
        f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    amp = f ** (-beta / 2.0)
    # 부드러운 띠 가장자리 (고리 모양 잡음이 생기지 않게)
    lo = np.clip((np.log2(f) - np.log2(fmin)) / 0.7 + 0.5, 0, 1)
    hi = np.clip((np.log2(fmax) - np.log2(f)) / 0.7 + 0.5, 0, 1)
    amp *= lo * hi
    amp[0, 0] = 0.0
    w = rng.standard_normal((n, n))
    out = np.real(np.fft.ifft2(np.fft.fft2(w) * amp))
    out -= out.mean()
    sd = out.std()
    return out / sd if sd > 0 else out


def worley(n, cells, rng, warp=None):
    """감싸는 Worley. 칸마다 점 하나. (F1 거리, F2 거리, 가장 가까운 점 번호) 를 화소 단위로 돌려준다.
    warp: (dx, dy) 화소 단위 좌표 비틀기 (주기 함수여야 이어진다)."""
    cs = n / cells
    pts = (np.stack(np.meshgrid(np.arange(cells), np.arange(cells)), -1).reshape(-1, 2) + rng.random((cells * cells, 2))) * cs
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    if warp is not None:
        xx = xx + warp[0]
        yy = yy + warp[1]
    cx = np.floor(xx / cs).astype(int)
    cy = np.floor(yy / cs).astype(int)
    f1 = np.full((n, n), 1e9)
    f2 = np.full((n, n), 1e9)
    idx = np.zeros((n, n), dtype=np.int64)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            gx = cx + ox
            gy = cy + oy
            wx = np.mod(gx, cells)
            wy = np.mod(gy, cells)
            k = wy * cells + wx
            px = pts[k, 0] + (gx - wx) * cs      # 감싼 칸의 점을 이웃 자리로 옮긴다
            py = pts[k, 1] + (gy - wy) * cs
            d = np.hypot(xx - px, yy - py)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            idx = np.where(closer, k, idx)
            f1 = np.where(closer, d, f1)
    return f1, f2, idx


def pits(n, rng, cells, keep, rmin, rmax, warp=None):
    """작은 구멍: Worley 점 중 keep 비율만 골라 반지름 rmin~rmax 화소의 그릇 모양 (0~1, 가운데 1)."""
    f1, _, idx = worley(n, cells, rng, warp)
    m = cells * cells
    active = rng.random(m) < keep
    rad = rmin + (rmax - rmin) * rng.random(m) ** 1.6     # 작은 구멍이 많게
    r = rad[idx]
    t = np.clip(1.0 - (f1 / r) ** 2, 0, 1)
    return np.where(active[idx], t, 0.0)


def cracks(n, rng, cells, width, fragment, warp_amp, seed_mask):
    """가는 금: 비튼 Worley 의 칸 경계 (F2 - F1 이 작은 곳). fragment: 이어진 금을 끊어 조각으로 남기는 비율 (0~1)."""
    wx = spectral(n, rng, 2, 12, 2.0) * warp_amp
    wy = spectral(n, rng, 2, 12, 2.0) * warp_amp
    f1, f2, _ = worley(n, cells, rng, (wx, wy))
    e = f2 - f1
    line = np.clip(1.0 - e / width, 0, 1) ** 1.5
    if fragment > 0:
        mask = spectral(n, seed_mask, 3, 16, 2.0)
        thr = np.quantile(mask, fragment)
        line *= np.clip((mask - thr) / 0.6, 0, 1)
    return line


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ───────────────────────── 높이 → 노멀 ─────────────────────────
def height_to_normal(h, strength):
    """h: 화소 단위 높이 (주기). OpenGL 노멀 (+V = 이미지 위쪽).
    v = 1 - 행/N 이므로 ∂h/∂v = -∂h/∂행 → n = (-∂h/∂u, -∂h/∂v, 1) = (-∂h/∂열, +∂h/∂행, 1/strength)."""
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    nx = -dx * strength
    ny = dy * strength
    nz = np.ones_like(h)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / l, ny / l, nz / l], -1)


def slope_stats(nrm):
    ang = np.degrees(np.arccos(np.clip(nrm[..., 2], -1, 1)))
    return float(np.sqrt((ang ** 2).mean())), float(np.percentile(ang, 99))


# ───────────────────────── 종류별 무늬 ─────────────────────────
# 반환: (albedo RGB 0~1, 0.5 중심), height(화소 단위), 노멀 세기
def make_stone(n, rng):
    mm = REPEAT_M["stone"] * 1000.0 / n                       # 화소당 mm (1024 → 0.88)
    grain = spectral(n, rng, n / 6, n / 2, 0.6)               # 1~3 mm 알갱이
    grain2 = spectral(n, rng, n / 16, n / 5, 1.2)             # 3~8 mm 결
    mottle = spectral(n, rng, 6, 40, 2.2)                     # 2~15 cm 얼룩 (색만, 높이는 거의 없음). 더 큰 얼룩은 반복이 격자로 보여 뺀다
    warp = (spectral(n, rng, 4, 30, 2.0) * 3, spectral(n, rng, 4, 30, 2.0) * 3)
    p_small = pits(n, rng, int(n / (14 / mm)), 0.30, 1.2 / mm, 2.6 / mm, warp)    # 지름 2~5 mm 구멍
    p_big = pits(n, rng, int(n / (60 / mm)), 0.35, 2.5 / mm, 5.0 / mm, warp)      # 지름 5~10 mm 구멍 (드묾)
    crk = cracks(n, rng, max(4, int(REPEAT_M["stone"] / 0.13)), 1.6, 0.62, 10.0, rng)

    h = grain * 0.22 + grain2 * 0.26 + mottle * 0.03          # 얼룩은 높이에 거의 넣지 않는다 (굴곡 = 녹은 밀랍 느낌)
    h -= p_small * 1.6 + p_big * 2.4 + crk * 1.3
    a = 0.5 + grain * 0.016 + grain2 * 0.010 + mottle * 0.016
    a -= p_small * 0.11 + p_big * 0.14 + crk * 0.08
    # 알갱이 일부는 밝은 결정 (돌의 반짝이는 결)
    a += np.clip(grain - 2.0, 0, None) * 0.03
    rgb = np.stack([a, a, a * 1.004], -1)
    return rgb, h, 0.55


def make_wood(n, rng):
    mm = REPEAT_M["wood"] * 1000.0 / n                        # 화소당 mm (1024 → 0.73)
    # 결: 세로(V)로 길게 늘어난 잡음이 0 을 지나는 곳을 가는 홈으로 (풍화된 나무의 결 홈).
    # 섬 방향이 제각각이라 결이 너무 또렷하면 어긋나 보이므로 홈은 얕고 색 차이는 작게
    s1 = spectral(n, rng, 14, 180, 1.3, aniso=16.0)
    groove = np.clip(1.0 - np.abs(s1) / 0.22, 0, 1) ** 2
    s2 = spectral(n, rng, 30, 320, 1.0, aniso=12.0)
    groove2 = np.clip(1.0 - np.abs(s2) / 0.18, 0, 1) ** 2 * 0.6  # 더 가는 결
    fiber = spectral(n, rng, 40, n / 2, 0.9, aniso=8.0)        # 섬유 잔결
    mottle = spectral(n, rng, 4, 24, 2.2)
    # 결 따라 갈라진 틈: 늘어난 잡음의 0 근처를 가는 선으로, 길이 방향으로 끊는다
    s = spectral(n, rng, 10, 70, 1.4, aniso=14.0)
    split = np.clip(1.0 - np.abs(s) / 0.07, 0, 1) ** 2
    seg = spectral(n, rng, 3, 20, 2.0, aniso=2.5)
    split *= smoothstep(0.35, 1.1, seg)
    # 아주 작은 벌레 구멍 (드묾)
    holes = pits(n, rng, int(n / (40 / mm)), 0.25, 0.8 / mm, 1.8 / mm)

    h = fiber * 0.12 - groove * 0.9 - groove2 * 0.6 - split * 2.4 - holes * 1.6
    a = 0.5 + fiber * 0.008 + mottle * 0.016 - groove * 0.05 - groove2 * 0.03 - split * 0.13 - holes * 0.10
    rgb = np.stack([a * 1.006, a, a * 0.992], -1)
    return rgb, h, 0.6


def make_bone(n, rng):
    mm = REPEAT_M["bone"] * 1000.0 / n                        # 화소당 mm (1024 → 0.59)
    pores = pits(n, rng, int(n / (5 / mm)), 0.45, 0.5 / mm, 1.0 / mm)       # 지름 1~2 mm 잔구멍 (빽빽)
    foram = pits(n, rng, int(n / (30 / mm)), 0.30, 1.2 / mm, 2.4 / mm)     # 지름 2.5~5 mm 혈관 구멍
    stri = spectral(n, rng, 20, n / 3, 1.0, aniso=8.0)                      # 옅은 세로 결
    mottle = spectral(n, rng, 4, 30, 2.2)                                   # 옅은 얼룩 (노란 기)
    craze = cracks(n, rng, max(5, int(REPEAT_M["bone"] / 0.05)), 1.3, 0.45, 6.0, rng)   # 거미줄 잔금 (칸 5 cm)
    fine = spectral(n, rng, n / 6, n / 2, 0.6)

    h = stri * 0.22 + fine * 0.12 - pores * 0.9 - foram * 1.6 - craze * 1.2
    a = 0.5 + stri * 0.010 + fine * 0.008 + mottle * 0.016 - pores * 0.045 - foram * 0.10 - craze * 0.085
    stain = np.clip(mottle, 0, None) * 0.010                                # 얼룩진 곳은 조금 누렇게
    rgb = np.stack([a + stain * 0.4, a, a - stain], -1)
    return rgb, h, 0.6


def make_metal(n, rng):
    mm = REPEAT_M["metal"] * 1000.0 / n
    # 녹 얼룩 가리개: 낮은 주파수 잡음의 윗부분 (면적 약 35 %)
    rm = spectral(n, rng, 3, 18, 2.4) + spectral(n, rng, 12, 60, 1.6) * 0.35
    rust = smoothstep(0.45, 0.95, rm)                                       # 면적 약 25 %
    rough = spectral(n, rng, n / 10, n / 2, 0.8)                            # 녹 표면의 거친 알갱이
    flake = spectral(n, rng, 20, 120, 1.4)
    pit = pits(n, rng, int(n / (8 / mm)), 0.40, 0.6 / mm, 1.6 / mm)          # 부식 구멍 (지름 1~3 mm)
    dent_f1, _, _ = worley(n, int(REPEAT_M["metal"] / 0.07), rng)            # 망치 자국 (7 cm 칸)
    cs = n / int(REPEAT_M["metal"] / 0.07)
    dent = (dent_f1 / cs) ** 2
    edge = smoothstep(0.3, 0.6, rm) - smoothstep(0.6, 1.0, rm)              # 녹 가장자리: 살짝 들뜸

    h = dent * 0.9 + rust * (rough * 0.38 + flake * 0.3) + edge * 0.4 - pit * (0.9 + rust * 0.6)
    base = 0.5 + rough * 0.010 * (1 - rust) + dent * 0.012
    a = base - rust * 0.02 + rust * rough * 0.018 - pit * 0.10
    warm = rust * (0.018 + flake * 0.005)                                    # 녹은 붉은 기 (곱해지면 철색이 살짝 갈색으로)
    rgb = np.stack([a + warm, a + warm * 0.15, a - warm * 0.9], -1)
    return rgb, h, 0.55


MAKERS = {"stone": make_stone, "wood": make_wood, "bone": make_bone, "metal": make_metal}
# 마지막 세기 조절 (색 대비 배수, 노멀 기울기 배수). 미리보기(1 m 에서 굽힌 그림보다 잔결이 보이고, 3 m 밖에서는 티가 거의 안 나게)로 맞췄다
GAIN = {"stone": (1.2, 1.35), "wood": (1.2, 1.3), "bone": (1.35, 1.4), "metal": (1.35, 1.35)}
SEEDS = {"stone": 9101, "wood": 9202, "bone": 9303, "metal": 9404}


def to8(x, rng):
    """0~1 → 8 비트. 낮은 대비의 띠 무늬를 막으려고 ±0.5 단계 떨림을 섞는다."""
    v = x * 255.0 + (rng.random(x.shape) - 0.5)
    return np.clip(np.round(v), 0, 255).astype(np.uint8)


def build(kind, n):
    rng = np.random.default_rng(SEEDS[kind])
    rgb, h, strength = MAKERS[kind](n, rng)
    ga, gn = GAIN[kind]
    rgb = 0.5 + (rgb - 0.5) * ga
    strength *= gn
    # 무늬 크기는 화소 수로 정했으므로 해상도가 반이면 화소당 높이 차가 두 배 → 세기를 n/1024 로 맞춰 같은 기울기로
    nrm = height_to_normal(h, strength * n / 1024.0)
    # 평균을 정확히 0.5 로 (×2 했을 때 전체가 밝아지거나 어두워지지 않게)
    rgb = rgb - rgb.mean(axis=(0, 1)) + 0.5
    return np.clip(rgb, 0, 1), nrm


def save(kind, rgb, nrm, out):
    rng = np.random.default_rng(SEEDS[kind] + 1)
    os.makedirs(out, exist_ok=True)
    pa = os.path.join(out, "detail_%s_albedo.png" % kind)
    pn = os.path.join(out, "detail_%s_normal.png" % kind)
    Image.fromarray(to8(rgb, rng), "RGB").save(pa, optimize=True)
    Image.fromarray(to8(nrm * 0.5 + 0.5, rng), "RGB").save(pn, optimize=True)
    return pa, pn


def seam_error(img):
    """끝 이음매 검사: 마지막 열→첫 열 차이가 내부 이웃 차이와 비슷하면 이어진 것."""
    a = img.astype(np.float64)
    inner = np.abs(np.diff(a, axis=1)).mean()
    seam = np.abs(a[:, 0] - a[:, -1]).mean()
    inner_v = np.abs(np.diff(a, axis=0)).mean()
    seam_v = np.abs(a[0, :] - a[-1, :]).mean()
    return seam / max(inner, 1e-9), seam_v / max(inner_v, 1e-9)


def sheet(results, path):
    """2×2 반복해 붙인 미리보기 (이음매 확인 + 간단한 빛)."""
    tiles = []
    for kind, (rgb, nrm) in results.items():
        L = np.array([-0.45, 0.55, 0.70]); L /= np.linalg.norm(L)
        shade = np.clip((nrm * L).sum(-1), 0, 1) * 0.85 + 0.15
        base = np.array([0.42, 0.40, 0.45])
        col = np.clip(base * rgb * 2.0 * shade[..., None], 0, 1)
        t = np.tile(col, (2, 2, 1))
        im = Image.fromarray((t * 255).astype(np.uint8)).resize((512, 512), Image.LANCZOS)
        tiles.append(np.asarray(im))
    row = np.concatenate(tiles, 1)
    Image.fromarray(row).save(path)


def main():
    ap = argparse.ArgumentParser(description="소품 근접 디테일 텍스처 (stone, wood, bone, metal)")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--kinds", default=",".join(KINDS))
    ap.add_argument("--sheet", default="")
    args = ap.parse_args()
    n = args.size
    if n & (n - 1):
        sys.exit("--size 는 2의 거듭제곱이어야 합니다 (밉맵·반복)")
    results = {}
    for kind in args.kinds.split(","):
        kind = kind.strip()
        if kind not in MAKERS:
            sys.exit("모르는 종류: " + kind)
        rgb, nrm = build(kind, n)
        pa, pn = save(kind, rgb, nrm, args.out)
        rms, p99 = slope_stats(nrm)
        lum = rgb.mean(-1)
        sa = seam_error(np.asarray(Image.open(pa)).mean(-1))
        sn = seam_error(np.asarray(Image.open(pn))[..., 0])
        print("%-5s 색 평균 %.3f 표준편차 %.3f (×2 하면 ±%.0f%%) 범위 %.2f~%.2f | 노멀 기울기 RMS %.1f° 99%% %.1f° | "
              "이음매/내부 차이 색 %.2f·%.2f 노멀 %.2f·%.2f | %s %d KB, %s %d KB" % (
                  kind, lum.mean(), lum.std(), lum.std() * 200, np.percentile(lum, 1), np.percentile(lum, 99), rms, p99,
                  sa[0], sa[1], sn[0], sn[1],
                  os.path.basename(pa), os.path.getsize(pa) // 1024, os.path.basename(pn), os.path.getsize(pn) // 1024))
        results[kind] = (rgb, nrm)
    if args.sheet:
        sheet(results, args.sheet)
        print("미리보기:", args.sheet)


if __name__ == "__main__":
    main()
