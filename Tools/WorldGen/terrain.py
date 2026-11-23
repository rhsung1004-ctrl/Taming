# 월드 생성기 공통: 노이즈, 흐림, 꺾은선 거리, 높이 샘플
# 배열은 [행 = Z(남→북), 열 = X(서→동)], 1 칸 = 1 m (높이 2049 × 2049)
import math
import numpy as np


class Perlin:
    """경사 노이즈 (-1 ~ 1 근처). 씨앗마다 다른 표"""

    def __init__(self, seed):
        r = np.random.default_rng(seed)
        p = r.permutation(1024).astype(np.int64)
        self.p = np.concatenate([p, p])
        a = r.random(1024) * 2 * np.pi
        self.gx = np.cos(a).astype(np.float32)
        self.gy = np.sin(a).astype(np.float32)

    def __call__(self, x, y):
        xf0 = np.floor(x)
        yf0 = np.floor(y)
        xf = (x - xf0).astype(np.float32)
        yf = (y - yf0).astype(np.float32)
        xi = xf0.astype(np.int64) & 1023
        yi = yf0.astype(np.int64) & 1023
        p, gx, gy = self.p, self.gx, self.gy

        def g(ix, iy, dx, dy):
            h = p[p[ix] + iy] & 1023
            return gx[h] * dx + gy[h] * dy

        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        v = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
        n00 = g(xi, yi, xf, yf)
        n10 = g(xi + 1, yi, xf - 1, yf)
        n01 = g(xi, yi + 1, xf, yf - 1)
        n11 = g(xi + 1, yi + 1, xf - 1, yf - 1)
        a = n00 + (n10 - n00) * u
        b = n01 + (n11 - n01) * u
        return (a + (b - a) * v) * 1.45


_P = {}


def perlin(x, y, seed):
    if seed not in _P:
        _P[seed] = Perlin(seed)
    return _P[seed](x, y)


def fbm(X, Z, freq, octaves, seed, gain=0.5, lac=2.0):
    s = np.zeros(X.shape, np.float32)
    amp, f, tot = 1.0, freq, 0.0
    for i in range(octaves):
        s += amp * perlin(X * f + 31.7 * i, Z * f - 17.3 * i, seed + i)
        tot += amp
        amp *= gain
        f *= lac
    return s / tot


def ridged(X, Z, freq, octaves, seed, gain=0.5, lac=2.0):
    """능선 노이즈 0~1 (날카로운 산등성이)"""
    s = np.zeros(X.shape, np.float32)
    w = np.ones(X.shape, np.float32)
    amp, f, tot = 1.0, freq, 0.0
    for i in range(octaves):
        n = 1.0 - np.abs(perlin(X * f + 11.1 * i, Z * f + 7.7 * i, seed + i))
        n = n * n
        n *= w
        w = np.clip(n * 1.6, 0, 1)
        s += amp * n
        tot += amp
        amp *= gain
        f *= lac
    return s / tot


def eroded(X, Z, freq, octaves, seed, amp_m, k=6.0, gain=0.5):
    """기울기가 큰 곳에서 잔 노이즈를 줄인 fbm (빗물에 깎인 듯한 비탈) — 결과는 m 단위"""
    h = np.zeros(X.shape, np.float32)
    amp, f = amp_m, freq
    for i in range(octaves):
        n = perlin(X * f + 5.3 * i, Z * f + 2.9 * i, seed + i)
        if i > 0:
            gz, gx = np.gradient(h)
            damp = 1.0 / (1.0 + k * (gx * gx + gz * gz))
            n = n * damp
        h += amp * n
        amp *= gain
        f *= 2.0
    return h


def ss(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def ssf(x, a, b):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def box_blur(a, r, passes=3):
    """가장자리 반복 상자 흐림 (cumsum). 세 번이면 가우시안에 가깝다"""
    a = a.astype(np.float32)
    for _ in range(passes):
        for axis in (0, 1):
            pad = [(0, 0), (0, 0)]
            pad[axis] = (r + 1, r)
            b = np.pad(a, pad, mode='edge')
            c = np.cumsum(b, axis=axis, dtype=np.float64)
            if axis == 0:
                a = ((c[2 * r + 1:, :] - c[:-2 * r - 1, :]) / (2 * r + 1)).astype(np.float32)
            else:
                a = ((c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)).astype(np.float32)
    return a


def catmull(pts, step=2.0):
    """경유점을 지나는 부드러운 곡선을 대략 step m 간격 점으로"""
    P = [np.array(p, np.float64) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        L = np.linalg.norm(p2 - p1)
        n = max(2, int(L / step))
        for j in range(n):
            t = j / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return np.array(out)


def wobble(curve, amp, freq, seed):
    """곡선을 옆으로 조금씩 흔든다 (손으로 낸 길처럼)"""
    d = np.gradient(curve, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
    side = np.stack([-d[:, 1], d[:, 0]], 1)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(curve, axis=0), axis=1))])
    n = perlin(s * freq, np.full_like(s, 3.3 + seed), seed).astype(np.float64)
    fade = np.minimum(1, np.minimum(s, s[-1] - s) / 30.0)
    return curve + side * (n * amp * fade)[:, None]


def polyline_field(curve, pad, size):
    """곡선까지의 거리와 곡선을 따라간 거리(시작부터 m). 곡선 둘레 상자 안만 계산
    반환: (행 범위, 열 범위, 거리, 따라간 거리, 가장 가까운 점 번호)"""
    x0 = int(max(0, math.floor(curve[:, 0].min() - pad)))
    x1 = int(min(size - 1, math.ceil(curve[:, 0].max() + pad)))
    z0 = int(max(0, math.floor(curve[:, 1].min() - pad)))
    z1 = int(min(size - 1, math.ceil(curve[:, 1].max() + pad)))
    zz, xx = np.mgrid[z0:z1 + 1, x0:x1 + 1].astype(np.float32)
    best = np.full(xx.shape, 1e9, np.float32)
    along = np.zeros(xx.shape, np.float32)
    seg = np.linalg.norm(np.diff(curve, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    for i in range(len(curve) - 1):
        ax, az = curve[i]
        bx, bz = curve[i + 1]
        dx, dz = bx - ax, bz - az
        L2 = dx * dx + dz * dz + 1e-9
        # 이 선분 근처만
        lx0, lx1 = min(ax, bx) - pad, max(ax, bx) + pad
        lz0, lz1 = min(az, bz) - pad, max(az, bz) + pad
        c0 = int(max(0, lx0 - x0)); c1 = int(min(xx.shape[1], lx1 - x0 + 1))
        r0 = int(max(0, lz0 - z0)); r1 = int(min(xx.shape[0], lz1 - z0 + 1))
        if c1 <= c0 or r1 <= r0:
            continue
        X = xx[r0:r1, c0:c1]
        Z = zz[r0:r1, c0:c1]
        t = np.clip(((X - ax) * dx + (Z - az) * dz) / L2, 0, 1)
        d = np.sqrt((X - (ax + t * dx)) ** 2 + (Z - (az + t * dz)) ** 2)
        B = best[r0:r1, c0:c1]
        m = d < B
        B[m] = d[m]
        A = along[r0:r1, c0:c1]
        A[m] = (cum[i] + t * seg[i])[m]
    return (z0, z1 + 1), (x0, x1 + 1), best, along


def sample(h, x, z):
    """높이 배열에서 (x, z) m 위치를 쌍선형으로"""
    n = h.shape[0] - 1
    x = min(max(x, 0.0), n - 1e-4)
    z = min(max(z, 0.0), n - 1e-4)
    i, j = int(z), int(x)
    fz, fx = z - i, x - j
    a = h[i, j] * (1 - fx) + h[i, j + 1] * fx
    b = h[i + 1, j] * (1 - fx) + h[i + 1, j + 1] * fx
    return float(a * (1 - fz) + b * fz)


def disk(shape, cx, cz, r):
    """원 둘레 상자: (행 slice, 열 slice, 거리 배열)"""
    z0, z1 = max(0, int(cz - r - 1)), min(shape[0], int(cz + r + 2))
    x0, x1 = max(0, int(cx - r - 1)), min(shape[1], int(cx + r + 2))
    zz, xx = np.mgrid[z0:z1, x0:x1].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (zz - cz) ** 2)
    return slice(z0, z1), slice(x0, x1), d
