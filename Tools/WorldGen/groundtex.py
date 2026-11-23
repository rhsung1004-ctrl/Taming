# 지형 층 텍스처 8종 (이어 붙여도 경계가 안 보이는 색 + 노멀)
#   python3 groundtex.py <출력 폴더> [이름,이름]
# 결과: ground_<이름>_albedo.jpg (sRGB), ground_<이름>_normal.png (OpenGL 방식, 초록 = 위)
# 색은 선형 값으로 정하고 저장할 때 sRGB 로 바꾼다 (소품 굽기와 같은 밝기 기준)
import sys, os, math
import numpy as np
from PIL import Image

N = 1024


def rng(seed):
    return np.random.default_rng(seed)


def fbm(beta, seed, n=N):
    """주기 노이즈 (FFT). beta 가 클수록 큰 덩어리. 0~1"""
    r = rng(seed)
    f = np.fft.fft2(r.standard_normal((n, n)))
    fx = np.fft.fftfreq(n)[:, None]
    fy = np.fft.fftfreq(n)[None, :]
    k = np.sqrt(fx * fx + fy * fy)
    k[0, 0] = 1
    v = np.real(np.fft.ifft2(f / k ** beta))
    v -= v.min()
    v /= v.max()
    return v.astype(np.float32)


def band(beta, seed, lo, hi, n=N):
    """특정 크기 범위만 남긴 주기 노이즈 (lo~hi: 한 변에 몇 번 반복되는지)"""
    r = rng(seed)
    f = np.fft.fft2(r.standard_normal((n, n)))
    fx = np.fft.fftfreq(n)[:, None] * n
    fy = np.fft.fftfreq(n)[None, :] * n
    k = np.sqrt(fx * fx + fy * fy)
    k[0, 0] = 1
    w = np.exp(-((np.log(k) - math.log(math.sqrt(lo * hi))) / (0.5 * math.log(hi / lo) + 1e-6)) ** 2)
    v = np.real(np.fft.ifft2(f * w / k ** beta))
    v -= v.min()
    v /= v.max()
    return v.astype(np.float32)


def ss(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def worley(cells, seed, n=N):
    """주기 보로노이: F1, F2 (픽셀 단위), 칸 번호"""
    r = rng(seed)
    pts = r.random((cells, cells, 2)).astype(np.float32)
    cs = n / cells
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    cy = (yy // cs).astype(np.int32)
    cx = (xx // cs).astype(np.int32)
    f1 = np.full((n, n), 1e9, np.float32)
    f2 = np.full((n, n), 1e9, np.float32)
    cid = np.zeros((n, n), np.int32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gy = cy + dy
            gx = cx + dx
            wy = gy % cells
            wx = gx % cells
            py = (gy + pts[wy, wx, 0]) * cs
            px = (gx + pts[wy, wx, 1]) * cs
            d = np.sqrt((yy - py) ** 2 + (xx - px) ** 2)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            cid = np.where(closer, wy * cells + wx, cid)
            f1 = np.where(closer, d, f1)
    return f1, f2, cid


class Canvas:
    """높이 기준으로 겹쳐 그리는 판 (위에 있는 것이 이긴다). 가장자리는 반대편으로 이어진다"""

    def __init__(self, base_h, base_c):
        self.h = base_h.astype(np.float32).copy()
        self.c = base_c.astype(np.float32).copy()

    def stamp(self, y0, x0, sh, sc, mask):
        """(y0, x0) 에서 시작하는 작은 판 sh(높이), sc(색 HxWx3), mask(덮는 정도 0~1)"""
        hh, ww = sh.shape
        iy = (np.arange(hh) + y0) % N
        ix = (np.arange(ww) + x0) % N
        H = self.h[np.ix_(iy, ix)]
        C = self.c[np.ix_(iy, ix)]
        win = (sh > H) & (mask > 0.02)
        m = (mask * win)[..., None]
        C = C * (1 - m) + sc * m
        H = np.where(win, H * (1 - mask) + sh * mask, H)
        self.h[np.ix_(iy, ix)] = H
        self.c[np.ix_(iy, ix)] = C


def seg_stamp(p0, p1, w0, w1, h0, h1):
    """선분(풀잎·잔가지) 하나: p=(y,x) 실수, 굵기 w0→w1, 높이 h0→h1. (y0, x0, 높이판, 덮개, t판)"""
    y0 = int(math.floor(min(p0[0], p1[0]) - max(w0, w1) - 1))
    x0 = int(math.floor(min(p0[1], p1[1]) - max(w0, w1) - 1))
    y1 = int(math.ceil(max(p0[0], p1[0]) + max(w0, w1) + 1))
    x1 = int(math.ceil(max(p0[1], p1[1]) + max(w0, w1) + 1))
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dy, dx = p1[0] - p0[0], p1[1] - p0[1]
    L2 = dy * dy + dx * dx + 1e-6
    t = np.clip(((yy - p0[0]) * dy + (xx - p0[1]) * dx) / L2, 0, 1)
    d = np.sqrt((yy - (p0[0] + t * dy)) ** 2 + (xx - (p0[1] + t * dx)) ** 2)
    w = w0 + (w1 - w0) * t
    cov = np.clip(w - d + 0.5, 0, 1)
    h = h0 + (h1 - h0) * t + 0.35 * np.clip(1 - d / np.maximum(w, 0.3), 0, 1)
    return y0, x0, h, cov, t


def ellipse_stamp(cy, cx, ry, rx, ang, h0, bulge):
    r = max(ry, rx) + 2
    y0, x0 = int(cy - r), int(cx - r)
    yy, xx = np.mgrid[y0:y0 + int(2 * r) + 1, x0:x0 + int(2 * r) + 1].astype(np.float32)
    ca, sa = math.cos(ang), math.sin(ang)
    u = ((xx - cx) * ca + (yy - cy) * sa) / rx
    v = (-(xx - cx) * sa + (yy - cy) * ca) / ry
    q = u * u + v * v
    cov = np.clip((1 - q) * max(rx, ry) * 0.5, 0, 1)
    h = h0 + bulge * np.sqrt(np.clip(1 - q, 0, 1))
    return y0, x0, h, cov, u, v


def lin(c):
    return np.array(c, np.float32)


def mix(a, b, t):
    t = t[..., None] if np.ndim(t) == 2 else t
    return a * (1 - t) + b * t


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def normal_map(h, strength):
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    # 열 → u(오른쪽), 행 아래로 → v 는 위가 + 이므로 부호를 뒤집는다 (OpenGL 방식: 초록 = 위)
    nx = -gx
    ny = gy
    nz = np.ones_like(h)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / l, ny / l, nz / l], -1)
    return ((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)


def save(out, name, col, h, strength):
    img = (to_srgb(col) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(img, 'RGB').save(os.path.join(out, "ground_%s_albedo.jpg" % name), quality=92)
    Image.fromarray(normal_map(h, strength), 'RGB').save(os.path.join(out, "ground_%s_normal.png" % name))
    print("ground", name, "색 평균", np.round(col.reshape(-1, 3).mean(0), 3))


def blur(a, k):
    """주기 상자 흐림 (세 번 = 가우시안 비슷)"""
    for _ in range(3):
        s = a.copy()
        for i in range(1, k + 1):
            s += np.roll(a, i, 0) + np.roll(a, -i, 0)
        a = s / (2 * k + 1)
        s = a.copy()
        for i in range(1, k + 1):
            s += np.roll(a, i, 1) + np.roll(a, -i, 1)
        a = s / (2 * k + 1)
    return a


# ───────────────────────── 층별 ─────────────────────────

def soil(seed, dark, light):
    big, mid, fine = fbm(1.8, seed), fbm(1.2, seed + 1), fbm(0.6, seed + 2)
    t = 0.55 * big + 0.3 * mid + 0.15 * fine
    col = mix(lin(dark), lin(light), ss(t, 0.25, 0.8))
    col *= (0.85 + 0.3 * fine)[..., None]
    h = 0.5 * big + 0.3 * mid + 0.2 * fine
    return col, h


def blades(cv, r, count, length, width, colors, hbase=0.4, lean=None, curl=0.35):
    """짧은 풀잎을 흩뿌린다. colors: [(색, 확률)]"""
    cols = [lin(c) for c, _ in colors]
    ps = np.array([p for _, p in colors], np.float64)
    ps /= ps.sum()
    for i in range(count):
        y, x = r.random() * N, r.random() * N
        L = r.uniform(*length)
        a = (lean if lean is not None else r.uniform(0, 2 * math.pi)) + r.normal(0, curl)
        mid = (y + math.sin(a) * L * 0.5, x + math.cos(a) * L * 0.5)
        a2 = a + r.normal(0, 0.35)
        tip = (mid[0] + math.sin(a2) * L * 0.5, mid[1] + math.cos(a2) * L * 0.5)
        c = cols[r.choice(len(cols), p=ps)] * r.uniform(0.75, 1.2)
        w = r.uniform(*width)
        for p0, p1, w0, w1, h0, h1, t0, t1 in ((
                (y, x), mid, w, w * 0.75, hbase, hbase + 0.4, 0.0, 0.5), (mid, tip, w * 0.75, 0.25, hbase + 0.4, hbase + 0.75, 0.5, 1.0)):
            y0, x0, sh, cov, t = seg_stamp(p0, p1, w0, w1, h0, h1)
            tt = t0 + (t1 - t0) * t
            sc = c[None, None, :] * (0.45 + 0.75 * tt)[..., None]   # 뿌리 쪽은 어둡고 끝은 밝다
            cv.stamp(y0, x0, sh, sc, cov)


def make_grass(out):
    r = rng(11)
    col, h = soil(10, (0.028, 0.026, 0.034), (0.05, 0.045, 0.05))
    moss = fbm(1.6, 13)
    col = mix(col, lin((0.04, 0.07, 0.055)), ss(moss, 0.35, 0.65) * 0.8)
    cv = Canvas(h * 0.35, col)
    tint = fbm(1.7, 14)
    blades(cv, r, 26000, (7, 15), (1.0, 1.7), [((0.05, 0.095, 0.07), 5), ((0.065, 0.11, 0.075), 3), ((0.1, 0.105, 0.05), 1.2),
                                                   ((0.12, 0.1, 0.06), 0.5), ((0.05, 0.07, 0.08), 1)])
    c = cv.c * (0.85 + 0.3 * tint)[..., None]
    save(out, "grass", c, cv.h, 2.2)


def make_moss(out):
    r = rng(21)
    big, mid, fine = fbm(1.7, 22), fbm(1.2, 25), fbm(0.5, 23)
    f1, f2, cid = worley(30, 21)
    clump = 1 - ss(f1 / (N / 30), 0.1, 1.0)            # 둥근 이끼 방석 (경계선은 그리지 않는다)
    clump = blur(clump, 3)
    h = 0.45 * clump + 0.3 * mid + 0.15 * big + 0.1 * fine
    a, b, cc = lin((0.04, 0.075, 0.055)), lin((0.085, 0.13, 0.075)), lin((0.055, 0.095, 0.1))
    col = mix(a, b, ss(0.6 * mid + 0.4 * clump, 0.25, 0.85))
    col = mix(col, cc, ss(big, 0.55, 0.8) * 0.55)
    col = mix(col, lin((0.03, 0.028, 0.035)), ss(-mid - clump * 0.6 + 0.75, 0.0, 0.25) * 0.6)   # 사이로 보이는 흙
    col *= (0.75 + 0.45 * fine)[..., None]
    cv = Canvas(h, col)
    blades(cv, r, 9000, (2, 5), (0.5, 0.9), [((0.09, 0.14, 0.08), 3), ((0.12, 0.15, 0.07), 1), ((0.06, 0.11, 0.09), 2)], hbase=0.7, curl=1.0)
    save(out, "moss", cv.c, cv.h, 3.0)


def pebbles(cv, r, count, size, colors, seed):
    for i in range(count):
        y, x = r.random() * N, r.random() * N
        s = r.uniform(*size)
        y0, x0, sh, cov, u, v = ellipse_stamp(y, x, s * r.uniform(0.6, 1.0), s, r.uniform(0, math.pi), 0.6, s * 0.12)
        c = lin(colors[r.integers(len(colors))]) * r.uniform(0.8, 1.15)
        shade = np.clip(0.75 + 0.35 * (-u * 0.5 - v * 0.6), 0.45, 1.25)   # 위왼쪽이 밝게
        cv.stamp(y0, x0, sh, c[None, None, :] * shade[..., None], cov)


def make_dirt(out):
    r = rng(31)
    col, h = soil(30, (0.05, 0.04, 0.045), (0.11, 0.085, 0.085))
    cr = band(0.0, 33, 3, 8)
    crack = (1 - ss(np.abs(cr - 0.5), 0.0, 0.012)) * ss(fbm(1.4, 34), 0.55, 0.7)   # 마른 곳에만 드문 금
    col = mix(col, lin((0.03, 0.024, 0.032)), crack * 0.6)
    h = h - crack * 0.25
    cv = Canvas(h * 0.4, col)
    pebbles(cv, r, 2400, (1.5, 5), [(0.12, 0.12, 0.14), (0.15, 0.14, 0.15), (0.1, 0.09, 0.1)], 32)
    blades(cv, r, 900, (4, 8), (0.6, 1.0), [((0.12, 0.1, 0.06), 2), ((0.05, 0.08, 0.06), 1)], hbase=0.5)
    save(out, "dirt", cv.c, cv.h, 2.0)


def make_mud(out):
    big, mid, fine = fbm(2.0, 41), fbm(1.3, 42), fbm(0.7, 43)
    h = 0.6 * big + 0.3 * mid + 0.1 * fine
    wet = ss(-h + 0.55, 0.0, 0.2)
    col = mix(lin((0.05, 0.043, 0.045)), lin((0.075, 0.06, 0.055)), ss(mid, 0.3, 0.8))
    col = mix(col, lin((0.02, 0.022, 0.03)), wet * 0.85)   # 고인 물 자리는 검게
    streak = band(0.0, 44, 30, 90)
    col *= (0.85 + 0.25 * streak)[..., None]
    h = np.where(wet > 0.5, h * 0.4 + 0.2, h)
    r = rng(45)
    cv = Canvas(h, col)
    pebbles(cv, r, 300, (1.5, 3.5), [(0.07, 0.07, 0.08), (0.09, 0.08, 0.08)], 46)
    blades(cv, r, 1600, (5, 12), (0.7, 1.1), [((0.08, 0.07, 0.04), 2), ((0.04, 0.06, 0.05), 1)], hbase=0.6)   # 쓰러진 갈대 잎
    save(out, "mud", cv.c, cv.h, 1.6)


def make_rock(out):
    big, mid, fine, micro = fbm(1.9, 53), fbm(1.3, 54), fbm(0.8, 55), fbm(0.3, 59)
    yy = np.mgrid[0:N, 0:N][0].astype(np.float32)
    warp = band(0.0, 56, 2, 5)
    lay = np.sin((yy / N * 2 * math.pi) * 6 + warp * 9) * 0.5 + 0.5           # 휘어진 층리
    hr = 0.45 * big + 0.3 * mid + 0.15 * lay + 0.1 * fine
    q = np.floor(hr * 9) / 9                                                  # 계단처럼 떨어져 나간 턱 (면이 평평하게)
    ledge = hr * 9 - np.floor(hr * 9)
    h = 0.7 * q + 0.15 * ss(ledge, 0.0, 0.25) + 0.1 * fine + 0.05 * micro
    lit = np.clip(1.0 + (np.roll(h, 3, 0) - np.roll(h, -3, 0)) * 6 + (np.roll(h, 3, 1) - np.roll(h, -3, 1)) * 3, 0.6, 1.35)
    col = mix(lin((0.1, 0.105, 0.14)), lin((0.2, 0.2, 0.24)), ss(0.5 * mid + 0.3 * q + 0.2 * micro, 0.25, 0.85))
    col = mix(col, lin((0.14, 0.12, 0.12)), ss(big, 0.62, 0.85) * 0.45)       # 녹물 든 곳
    col *= lit[..., None] * (0.85 + 0.25 * micro)[..., None]
    lip = 1 - ss(ledge, 0.0, 0.06)                                            # 턱 아래 그늘 (깊은 보라)
    col = mix(col, lin((0.04, 0.03, 0.06)), lip * 0.7)
    fis = band(0.0, 57, 2, 6)
    crack = (1 - ss(np.abs(fis - 0.5), 0, 0.01)) * ss(fine, 0.4, 0.6)
    col = mix(col, lin((0.035, 0.025, 0.055)), crack * 0.8)
    h = h - crack * 0.2
    lichen = ss(fbm(1.0, 58), 0.7, 0.8) * ss(-ledge, -0.6, -0.2)
    col = mix(col, lin((0.08, 0.12, 0.09)), lichen * 0.6)
    save(out, "rock", col, h, 5.0)


def make_path(out):
    r = rng(61)
    col, h = soil(60, (0.06, 0.055, 0.06), (0.11, 0.1, 0.1))
    f1, f2, cid = worley(22, 62)
    stone = ss(f2 - f1, 1.5, 6) * ss(fbm(1.5, 63), 0.55, 0.68)     # 군데군데만 남은 납작한 판석
    tone = rng(64).random(22 * 22).astype(np.float32)[cid]
    scol = mix(lin((0.11, 0.11, 0.125)), lin((0.18, 0.175, 0.19)), tone)
    fine = fbm(0.5, 65)
    scol *= (0.8 + 0.35 * fine)[..., None]
    col = mix(col, scol, stone)
    h = h * 0.4 + stone * (0.5 + 0.2 * fine)
    cv = Canvas(h, col)
    pebbles(cv, r, 5000, (1.2, 3.2), [(0.13, 0.12, 0.13), (0.1, 0.095, 0.1), (0.16, 0.15, 0.15)], 66)
    save(out, "path", cv.c, cv.h, 2.4)


def make_leaves(out):
    r = rng(71)
    col, h = soil(70, (0.03, 0.025, 0.03), (0.06, 0.045, 0.045))
    cv = Canvas(h * 0.2, col)
    cols = [(0.13, 0.055, 0.035), (0.1, 0.07, 0.045), (0.085, 0.07, 0.08), (0.15, 0.09, 0.04), (0.06, 0.05, 0.06)]
    for i in range(7000):
        y, x = r.random() * N, r.random() * N
        L = r.uniform(9, 19)
        ang = r.uniform(0, math.pi)
        y0, x0, sh, cov, u, v = ellipse_stamp(y, x, L * 0.42, L, ang, 0.3 + r.random() * 0.5, 0.15)
        cov = cov * (1 - ss(np.abs(u), 0.85, 1.0) * ss(-np.abs(v), -0.25, 0.0))   # 끝이 뾰족하게
        c = lin(cols[r.integers(len(cols))]) * r.uniform(0.7, 1.2)
        vein = 1 - 0.35 * (1 - ss(np.abs(v), 0.0, 0.08)) - 0.2 * (1 - ss(np.abs(np.sin(u * 6) - v * 1.5), 0, 0.12))
        curl = 0.8 + 0.4 * u
        cv.stamp(y0, x0, sh + 0.08 * u * u, c[None, None, :] * (vein * curl)[..., None], cov)
    blades(cv, r, 700, (6, 14), (0.6, 0.9), [((0.07, 0.05, 0.04), 1)], hbase=0.9)    # 잔가지
    save(out, "leaves", cv.c, cv.h, 2.6)


def make_ash(out):
    r = rng(81)
    col, h = soil(80, (0.14, 0.13, 0.155), (0.27, 0.25, 0.28))
    cinder = ss(fbm(0.9, 83), 0.62, 0.75)
    col = mix(col, lin((0.04, 0.035, 0.045)), cinder * 0.7)
    rip = band(0.0, 84, 20, 50)
    h = h * 0.6 + rip * 0.3
    cv = Canvas(h * 0.4, col)
    # 뼛조각: 길쭉한 파편
    for i in range(1300):
        y, x = r.random() * N, r.random() * N
        L = r.uniform(4, 13)
        a = r.uniform(0, math.pi * 2)
        p1 = (y + math.sin(a) * L, x + math.cos(a) * L)
        w = r.uniform(0.8, 1.8)
        y0, x0, sh, cov, t = seg_stamp((y, x), p1, w, w * r.uniform(0.5, 1.1), 0.7, 0.75)
        c = lin((0.42, 0.39, 0.35)) * r.uniform(0.7, 1.1)
        sc = c[None, None, :] * (0.85 + 0.2 * np.sin(t * 7))[..., None]
        cv.stamp(y0, x0, sh, sc, cov)
    pebbles(cv, r, 1500, (1, 2.6), [(0.05, 0.045, 0.05), (0.2, 0.19, 0.21)], 85)
    save(out, "ash", cv.c, cv.h, 2.0)


MAKERS = {"grass": make_grass, "moss": make_moss, "dirt": make_dirt, "mud": make_mud,
          "rock": make_rock, "path": make_path, "leaves": make_leaves, "ash": make_ash}

if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    names = sys.argv[2].split(",") if len(sys.argv) > 2 else list(MAKERS)
    for n in names:
        MAKERS[n](out)
