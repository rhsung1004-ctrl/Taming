# 이어 붙여도 경계가 안 보이는 묘지 흙바닥 텍스처 (색 + 노멀)
import numpy as np, sys
from PIL import Image
out = sys.argv[1]
N = 1024
rs = np.random.RandomState(4)

def fbm(beta, seed):
    r = np.random.RandomState(seed)
    f = np.fft.fft2(r.randn(N, N))
    fx = np.fft.fftfreq(N)[:, None]; fy = np.fft.fftfreq(N)[None, :]
    k = np.sqrt(fx * fx + fy * fy); k[0, 0] = 1
    n = np.real(np.fft.ifft2(f / k ** beta))
    n -= n.min(); n /= n.max()
    return n

def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)

big, mid, fine, grassn = fbm(1.9, 1), fbm(1.3, 2), fbm(0.7, 3), fbm(1.5, 5)
earth_d, earth_l = np.array([0.055, 0.05, 0.07]), np.array([0.15, 0.13, 0.15])
col = earth_d + (earth_l - earth_d) * (0.6 * big + 0.4 * mid)[..., None]
col *= (0.75 + 0.5 * fine)[..., None]
grass = smooth(grassn, 0.52, 0.66)
gcol = np.array([0.07, 0.11, 0.085]) * (0.6 + 0.8 * fine)[..., None]
col = col * (1 - grass[..., None] * 0.8) + gcol * grass[..., None] * 0.8
height = 0.5 * big + 0.3 * mid + 0.12 * fine + 0.1 * grass

# 자갈: 가장자리를 넘어가도 반대편에서 이어지게
yy, xx = np.mgrid[0:N, 0:N]
for _ in range(170):
    cx, cy, r = rs.randint(N), rs.randint(N), rs.uniform(2, 9) ** 1.15
    dx = np.minimum(np.abs(xx - cx), N - np.abs(xx - cx)); dy = np.minimum(np.abs(yy - cy), N - np.abs(yy - cy))
    d = np.sqrt(dx * dx + (dy * rs.uniform(0.7, 1.4)) ** 2) / r
    m = smooth(1 - d, 0.0, 0.35)
    shade = rs.uniform(0.09, 0.2)
    pc = np.array([shade, shade, shade * 1.25]) * (0.8 + 0.4 * fine)[..., None]
    col = col * (1 - m[..., None]) + pc * m[..., None]
    height = np.maximum(height, height * (1 - m) + (height + 0.25 * np.sqrt(np.clip(1 - d * d, 0, 1))) * m)

gx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)); gy = (np.roll(height, -1, 0) - np.roll(height, 1, 0))
s = 9.0
nrm = np.dstack([-gx * s, gy * s, np.ones_like(gx)])
nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
srgb = np.clip(col, 0, 1) ** (1 / 2.2)
Image.fromarray((srgb * 255).astype(np.uint8)).save(out + "/ground_albedo.png")
Image.fromarray(((nrm * 0.5 + 0.5) * 255).astype(np.uint8)).save(out + "/ground_normal.png")
print("ground ok")
