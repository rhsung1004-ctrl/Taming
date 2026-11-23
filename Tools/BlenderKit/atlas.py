# 잎 아틀라스 (foliage_atlas.png) 그리기: 4x4 칸, 칸마다 256px. 회색조 + 알파 (색은 정점 색으로 입힌다)
# 사용법: python3 atlas.py <출력 폴더>
import sys, math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SS = 4                 # 4배로 그린 뒤 줄여 가장자리를 매끄럽게
C = 256 * SS
OUT = sys.argv[1]
atlas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
rng = random.Random(3)

def cell():
    return Image.new("RGBA", (C, C), (0, 0, 0, 0))

def put(img, cx, cy):
    small = img.resize((256, 256), Image.LANCZOS)
    # 알파가 0인 곳의 색을 주변 색으로 채워 밉맵에서 검은 테두리가 생기지 않게
    a = np.array(small).astype(np.float32)
    rgb, al = a[..., :3], a[..., 3:4] / 255.0
    blur = Image.fromarray(np.clip(rgb * al, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))
    ablur = Image.fromarray((al[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))
    bb = np.array(blur).astype(np.float32); ab = np.array(ablur).astype(np.float32)[..., None] / 255.0
    fill = np.where(ab > 0.01, bb / np.maximum(ab, 0.01), 170)
    rgb2 = np.where(al > 0.02, rgb, fill)
    out = np.dstack([np.clip(rgb2, 0, 255), a[..., 3]]).astype(np.uint8)
    # 아틀라스는 아래쪽이 v=0 이므로 칸의 y를 뒤집어 놓는다
    atlas.paste(Image.fromarray(out), (cx * 256, (3 - cy) * 256))

def shade(img, top=235, bottom=150, veins=None):
    """잎 안쪽에 밝기 변화 (위가 밝고 아래·가장자리가 어둡다)"""
    a = np.array(img).astype(np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    g = bottom + (top - bottom) * (1 - yy / h)
    alpha = a[..., 3] / 255.0
    blurred = np.array(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(C / 40))) / 255.0
    g = g * (0.65 + 0.35 * blurred)
    noise = np.array(Image.effect_noise((w, h), 40).filter(ImageFilter.GaussianBlur(SS * 2))).astype(np.float32) / 255.0
    g = g * (0.85 + 0.3 * noise)
    if veins is not None:
        v = np.array(veins).astype(np.float32) / 255.0
        g = g * (1 - 0.35 * v)
    a[..., 0] = a[..., 1] = a[..., 2] = np.clip(g, 0, 255)
    return Image.fromarray(a.astype(np.uint8))

def leaf_poly(lobes, w, h, wobble, cx=C / 2, base=C * 0.92):
    pts = []
    n = 120
    for i in range(n + 1):
        t = i / n
        ang = math.pi * t
        r = (math.sin(ang) ** 0.8) * (1 + lobes * 0.18 * math.sin(ang * (2 * lobes + 1)) ** 2)
        x = cx + (t - 0.5) * 0  # 자리
        px = cx + math.cos(ang) * w / 2 * r * (1 + wobble * math.sin(i * 1.7))
        py = base - math.sin(ang) * h * (0.35 + 0.65 * r)
        pts.append((px, py))
    return pts

def draw_leaf(lobes, w, h, wobble=0.02, holes=0, tip=True):
    img = cell(); d = ImageDraw.Draw(img)
    pts = []
    n = 160
    for i in range(n):
        t = i / n * 2 * math.pi
        # 하트 모양 잎 (ivy): 극좌표 + 갈래
        r = 1 - 0.18 * math.cos(lobes * t) ** 2 if lobes else 1
        x = math.sin(t) * r * w / 2 * (1 + wobble * math.sin(t * 9))
        y = -(math.cos(t) * r) * h / 2 - (0.18 * h * math.sin(t / 2) ** 8 if tip else 0)
        pts.append((C / 2 + x, C * 0.55 + y))
    d.polygon(pts, fill=(255, 255, 255, 255))
    for _ in range(holes):
        r = rng.uniform(C * 0.02, C * 0.06)
        x, y = rng.uniform(C * 0.3, C * 0.7), rng.uniform(C * 0.3, C * 0.75)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(0, 0, 0, 0))
    veins = Image.new("L", (C, C), 0); dv = ImageDraw.Draw(veins)
    dv.line([(C / 2, C * 0.95), (C / 2, C * 0.2)], fill=255, width=SS * 3)
    for k in range(-3, 4):
        if k == 0:
            continue
        y0 = C * (0.62 - 0.08 * abs(k))
        dv.line([(C / 2, y0), (C / 2 + k * C * 0.11, y0 - C * 0.12)], fill=200, width=SS * 2)
    veins = veins.filter(ImageFilter.GaussianBlur(SS))
    # 잎자루
    d.line([(C / 2, C * 0.78), (C / 2, C * 0.98)], fill=(200, 200, 200, 255), width=SS * 4)
    return shade(img, veins=veins)

# solid
img = cell(); ImageDraw.Draw(img).rectangle([0, 0, C, C], fill=(255, 255, 255, 255)); put(img, 0, 0)
put(draw_leaf(5, C * 0.8, C * 0.72), 1, 0)
put(draw_leaf(0, C * 0.62, C * 0.85, wobble=0.04), 2, 0)
put(draw_leaf(3, C * 0.7, C * 0.75, wobble=0.09, holes=4), 3, 0)

# fern
img = cell(); d = ImageDraw.Draw(img)
d.line([(C / 2, C), (C / 2 + C * 0.05, C * 0.03)], fill=(255, 255, 255, 255), width=SS * 5)
for i in range(18):
    t = i / 18
    y = C * (0.95 - t * 0.9)
    L = C * 0.42 * math.sin(math.pi * (0.15 + 0.85 * (1 - t))) * (1 - t * 0.5)
    for s in (-1, 1):
        x0 = C / 2 + C * 0.05 * t
        pts = [(x0, y), (x0 + s * L * 0.5, y - C * 0.035), (x0 + s * L, y - C * 0.02 - L * 0.15), (x0 + s * L * 0.5, y + C * 0.02)]
        d.polygon(pts, fill=(255, 255, 255, 255))
put(shade(img, 230, 140), 0, 1)

# grass card
img = cell(); d = ImageDraw.Draw(img)
for i in range(26):
    x = rng.uniform(C * 0.08, C * 0.92); h = rng.uniform(C * 0.45, C * 0.98); lean = rng.uniform(-C * 0.18, C * 0.18); w = rng.uniform(SS * 5, SS * 11)
    d.polygon([(x - w, C), (x + w, C), (x + lean + w * 0.1, C - h), (x + lean - w * 0.1, C - h)], fill=(255, 255, 255, 255))
put(shade(img, 245, 110), 1, 1)

# hanging moss
img = cell(); d = ImageDraw.Draw(img)
for i in range(70):
    x = rng.uniform(C * 0.1, C * 0.9); L = rng.uniform(C * 0.3, C * 0.98)
    pts = []
    for k in range(12):
        t = k / 11
        pts.append((x + math.sin(t * 6 + i) * C * 0.03 * t, t * L))
    d.line(pts, fill=(255, 255, 255, 255), width=SS * 2)
img = img.filter(ImageFilter.GaussianBlur(SS * 0.6))
put(shade(img, 220, 120), 2, 1)

# petal
img = cell(); d = ImageDraw.Draw(img)
d.ellipse([C * 0.25, C * 0.05, C * 0.75, C * 0.95], fill=(255, 255, 255, 255))
put(shade(img, 255, 200), 3, 1)

# web
def web(img, cx, cy, R_, start, end, spokes):
    d = ImageDraw.Draw(img)
    angs = [start + (end - start) * i / (spokes - 1) for i in range(spokes)]
    for a in angs:
        d.line([(cx, cy), (cx + math.cos(a) * R_, cy + math.sin(a) * R_)], fill=(255, 255, 255, 255), width=SS * 2)
    r = R_ * 0.08
    while r < R_:
        pts = [(cx + math.cos(a) * r * rng.uniform(0.93, 1.0), cy + math.sin(a) * r * rng.uniform(0.93, 1.0)) for a in angs]
        d.line(pts, fill=(255, 255, 255, 255), width=SS + 2)
        r += R_ * rng.uniform(0.06, 0.1)
img = cell(); web(img, C / 2, C / 2, C * 0.49, 0, 2 * math.pi, 15); put(shade(img, 255, 220), 0, 2)
img = cell(); web(img, 0, 0, C * 0.98, 0, math.pi / 2, 7); put(shade(img, 255, 220), 3, 3)

# tattered cloth
img = cell(); d = ImageDraw.Draw(img)
pts = [(C * 0.06, 0), (C * 0.94, 0)]
x = C * 0.94
while x > C * 0.06:
    pts.append((x, C * rng.uniform(0.72, 0.98)))
    x -= C * rng.uniform(0.03, 0.08)
pts.append((C * 0.06, C * 0.85))
d.polygon(pts, fill=(255, 255, 255, 255))
for _ in range(9):
    r = rng.uniform(C * 0.02, C * 0.07); xx, yy = rng.uniform(C * 0.15, C * 0.85), rng.uniform(C * 0.2, C * 0.8)
    d.polygon([(xx + math.cos(a) * r * rng.uniform(0.5, 1.3), yy + math.sin(a) * r * rng.uniform(0.5, 1.3)) for a in np.linspace(0, 6.28, 9)], fill=(0, 0, 0, 0))
put(shade(img, 210, 150), 1, 2)

# thorn leaf (serrated)
img = cell(); d = ImageDraw.Draw(img)
pts = []
for i in range(80):
    t = i / 80 * 2 * math.pi
    r = 1 + 0.12 * (1 if i % 4 < 2 else -1)
    pts.append((C / 2 + math.sin(t) * r * C * 0.25, C * 0.5 - math.cos(t) * r * C * 0.45))
d.polygon(pts, fill=(255, 255, 255, 255))
put(shade(img, 220, 140), 2, 2)

# stem (opaque gradient)
a = np.zeros((C, C, 4), np.uint8)
xs = np.linspace(-1, 1, C)
v = (140 + 90 * np.sqrt(np.clip(1 - xs ** 2, 0, 1)))[None, :].repeat(C, 0)
a[..., 0] = a[..., 1] = a[..., 2] = v.astype(np.uint8); a[..., 3] = 255
put(Image.fromarray(a), 3, 2)

# lily (top view, 6 petals)
img = cell(); d = ImageDraw.Draw(img)
for k in range(6):
    ang = k * math.pi / 3
    pts = []
    for i in range(40):
        t = i / 39 * math.pi
        r = math.sin(t) ** 0.7
        px = math.cos(ang) * (t / math.pi) * C * 0.47 - math.sin(ang) * r * C * 0.09
        py = math.sin(ang) * (t / math.pi) * C * 0.47 + math.cos(ang) * r * C * 0.09
        pts.append((C / 2 + px, C / 2 + py))
    for i in range(39, -1, -1):
        t = i / 39 * math.pi
        r = math.sin(t) ** 0.7
        px = math.cos(ang) * (t / math.pi) * C * 0.47 + math.sin(ang) * r * C * 0.09
        py = math.sin(ang) * (t / math.pi) * C * 0.47 - math.cos(ang) * r * C * 0.09
        pts.append((C / 2 + px, C / 2 + py))
    d.polygon(pts, fill=(255, 255, 255, 255))
a = np.array(img).astype(np.float32)
yy, xx = np.mgrid[0:C, 0:C]; rr = np.sqrt((xx - C / 2) ** 2 + (yy - C / 2) ** 2) / (C / 2)
g = 255 * (0.75 + 0.25 * rr)
a[..., 0] = a[..., 1] = a[..., 2] = np.clip(g, 0, 255)
put(Image.fromarray(a.astype(np.uint8)), 0, 3)

# mushroom gill (opaque radial lines)
a = np.zeros((C, C, 4), np.uint8)
ang = np.arctan2(yy - C / 2, xx - C / 2)
g = 150 + 70 * (np.sin(ang * 60) > 0.2) * np.clip(rr, 0, 1)
a[..., 0] = a[..., 1] = a[..., 2] = np.clip(g, 0, 255).astype(np.uint8); a[..., 3] = 255
put(Image.fromarray(a), 1, 3)

# reed
img = cell(); d = ImageDraw.Draw(img)
for i in range(9):
    x = C * (0.1 + 0.8 * i / 8) + rng.uniform(-C * 0.03, C * 0.03); w = SS * 7; lean = rng.uniform(-C * 0.06, C * 0.06)
    d.polygon([(x - w, C), (x + w, C), (x + lean, C * rng.uniform(0.0, 0.2))], fill=(255, 255, 255, 255))
put(shade(img, 240, 120), 2, 3)

atlas.save(OUT + "/foliage_atlas.png")
print("atlas ok")
