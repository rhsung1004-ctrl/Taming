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

# fern: 깃꼴 잎. 잎줄기(아래 = 잎자루) 양쪽으로 깃조각, 깃조각마다 작은 잎(소엽)이 줄지어 달린다.
#   좁은 캔버스(폭 = 길이 × 0.5)에 실제 비율로 그린 뒤 가로로 늘인다 → 카드 폭을 길이의 0.5 로 쓰면 비율이 맞다
def draw_fern():
    Wc = C // 2
    img = Image.new("RGBA", (Wc, C), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    veins = Image.new("L", (Wc, C), 0); dv = ImageDraw.Draw(veins)
    frng = random.Random(41)
    def rachis(t):
        return Wc / 2 + C * 0.012 * math.sin(t * math.pi * 0.9), C * 0.995 - C * 0.985 * t
    pts = [rachis(i / 80) for i in range(81)]
    for i in range(80):
        d.line([pts[i], pts[i + 1]], fill=(255, 255, 255, 255), width=max(2, int(SS * (4.5 - 3.3 * i / 80))))
        dv.line([pts[i], pts[i + 1]], fill=140, width=max(1, int(SS * (2 - 1.4 * i / 80))))
    def ellipse(cx, cy, ax, ay, L, W):
        poly = []
        for k in range(14):
            q = k / 14 * 2 * math.pi
            x, y = math.cos(q) * L / 2, math.sin(q) * W / 2
            poly.append((cx + ax * x - ay * y, cy + ay * x + ax * y))
        d.polygon(poly, fill=(255, 255, 255, 255))
    n = 19
    for i in range(n):
        for s in (-1, 1):
            t = 0.1 + 0.87 * i / (n - 1) + (0.018 if s > 0 else 0.0)
            env = math.sin(math.pi * min(1.0, max(0.0, (t - 0.05) / 0.95)) ** 0.6)
            ang = math.radians(62 + 20 * t)
            L = Wc * 0.47 * env / math.sin(ang)
            if L < SS * 5:
                continue
            x0, y0 = rachis(t)
            dx, dy = s * math.sin(ang), -math.cos(ang)
            m = max(3, int(L / (SS * 3.2)))
            sp = L / (m + 0.4)
            for k in range(m):
                u = (k + 0.5) / (m + 0.4)
                cx = x0 + dx * L * u
                cy = y0 + dy * L * u - L * 0.1 * u * u
                Wp = sp * 1.25
                Lp = min(C * 0.024, Wp * 2.3) * (1 - 0.5 * u) * (0.55 + 0.45 * env) * frng.uniform(0.9, 1.1)
                for side in (-1, 1):
                    # 소엽: 깃조각 축에서 바로 나온 긴 타원, 끝 쪽으로 기울어 서로 붙어 빗살처럼 보인다
                    px, py = -dy * side, dx * side
                    lx, ly = px * 0.85 + dx * 0.4, py * 0.85 + dy * 0.4
                    ln = math.hypot(lx, ly); lx, ly = lx / ln, ly / ln
                    ellipse(cx + lx * Lp * 0.42, cy + ly * Lp * 0.42, lx, ly, Lp, Wp * 0.9)
            line = [(x0 + dx * L * u, y0 + dy * L * u - L * 0.1 * u * u) for u in (0, 0.25, 0.5, 0.75, 1.0)]
            d.line(line, fill=(255, 255, 255, 255), width=SS * 2)
            dv.line(line, fill=210, width=SS)
    img = img.resize((C, C), Image.LANCZOS)
    veins = veins.resize((C, C), Image.LANCZOS).filter(ImageFilter.GaussianBlur(SS * 0.6))
    return shade(img, 235, 120, veins=veins)
put(draw_fern(), 0, 1)

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

# petal: 끝이 뾰족한 긴 꽃잎 (아래 = 꽃받침 쪽). 세로 잎맥, 가운데 홈, 가장자리 잔물결
def draw_petal():
    img = cell(); d = ImageDraw.Draw(img)
    def half(v):
        sm = min(1.0, v / 0.28); sm = sm * sm * (3 - 2 * sm)
        return C * 0.34 * math.sin(math.pi * min(1.0, v) ** 1.35) ** 0.8 * (0.3 + 0.7 * sm) * (1 + 0.03 * math.sin(v * 37))
    L, Rr = [], []
    for i in range(141):
        v = i / 140
        y = C * (0.995 - 0.985 * v)
        w = half(v)
        L.append((C / 2 - w, y)); Rr.append((C / 2 + w * (1 + 0.02 * math.sin(v * 23)), y))
    d.polygon(L + Rr[::-1], fill=(255, 255, 255, 255))
    veins = Image.new("L", (C, C), 0); dv = ImageDraw.Draw(veins)
    for k in range(-6, 7):
        line = []
        for i in range(60):
            v = 0.02 + 0.9 * i / 59
            line.append((C / 2 + half(v) * k / 7.2, C * (0.995 - 0.985 * v)))
        dv.line(line, fill=255 if k == 0 else 120, width=SS * (3 if k == 0 else 1))
    veins = veins.filter(ImageFilter.GaussianBlur(SS * 0.7))
    return shade(img, 255, 165, veins=veins)
put(draw_petal(), 3, 1)

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

# thorn leaf: 끝이 뾰족한 달걀꼴 잎, 앞으로 향한 겹톱니, 휘어진 곁잎맥 (가시덤불·잡초)
def draw_thorn_leaf():
    img = cell(); d = ImageDraw.Draw(img)
    base, tip = C * 0.9, C * 0.03
    def half(v):
        w = C * 0.36 * math.sin(math.pi * min(1.0, v) ** 0.78) ** 0.9
        if v > 0.08:
            f = (v * 19) % 1.0
            g = (v * 38) % 1.0
            w *= 1 + 0.085 * f + 0.03 * g
        return w
    L, Rr = [], []
    for i in range(241):
        v = i / 240
        y = base + (tip - base) * v
        w = half(v)
        L.append((C / 2 - w, y)); Rr.append((C / 2 + w, y))
    d.polygon(L + Rr[::-1], fill=(255, 255, 255, 255))
    d.line([(C / 2, base - SS * 6), (C / 2, C * 0.995)], fill=(205, 205, 205, 255), width=SS * 6)
    veins = Image.new("L", (C, C), 0); dv = ImageDraw.Draw(veins)
    dv.line([(C / 2, base), (C / 2, tip + C * 0.05)], fill=255, width=SS * 3)
    for k in range(8):
        v0 = 0.08 + 0.1 * k
        y0 = base + (tip - base) * v0
        for s in (-1, 1):
            line = []
            for i in range(12):
                u = i / 11
                vv = v0 + 0.16 * u ** 1.3
                line.append((C / 2 + s * half(vv) * 0.9 * u, base + (tip - base) * vv))
            dv.line(line, fill=200, width=SS * 2)
    veins = veins.filter(ImageFilter.GaussianBlur(SS * 0.8))
    return shade(img, 225, 125, veins=veins)
put(draw_thorn_leaf(), 2, 2)

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

# mushroom gill: 위에서 본 버섯 주름 (불투명). 긴 주름 사이에 짧은 주름, 가운데 대 자리, 바깥 테두리
def draw_gill():
    lines = Image.new("L", (C, C), 0); dl = ImageDraw.Draw(lines)
    grng = random.Random(21)
    N = 44
    for i in range(N * 4):
        a = i / (N * 4) * 2 * math.pi + grng.uniform(-0.01, 0.01)
        r0 = 0.13 if i % 4 == 0 else (grng.uniform(0.3, 0.55) if i % 2 == 0 else grng.uniform(0.6, 0.85))
        r1 = 0.97
        dl.line([(C / 2 + math.cos(a) * C / 2 * r0, C / 2 + math.sin(a) * C / 2 * r0),
                 (C / 2 + math.cos(a) * C / 2 * r1, C / 2 + math.sin(a) * C / 2 * r1)], fill=255, width=SS * 2)
    lines = lines.filter(ImageFilter.GaussianBlur(SS * 0.9))
    lv = np.array(lines).astype(np.float32) / 255.0
    g = 120 + 100 * lv
    g = np.where(rr < 0.12, 165, g)
    g = g * (1 - 0.35 * np.clip((rr - 0.9) / 0.1, 0, 1)) * (0.8 + 0.2 * np.clip(rr * 2, 0, 1))
    a = np.zeros((C, C, 4), np.uint8)
    a[..., 0] = a[..., 1] = a[..., 2] = np.clip(g, 0, 255).astype(np.uint8); a[..., 3] = 255
    return Image.fromarray(a)
put(draw_gill(), 1, 3)

# reed: 키가 다른 가는 잎 여러 장, 몇 장은 위에서 꺾여 늘어진다
def draw_reed():
    img = cell(); d = ImageDraw.Draw(img)
    rrng = random.Random(33)
    for i in range(10):
        x = C * (0.08 + 0.84 * i / 9) + rrng.uniform(-C * 0.025, C * 0.025)
        w = SS * rrng.uniform(5.5, 8.5)
        h = C * rrng.uniform(0.62, 0.99)
        lean = rrng.uniform(-C * 0.07, C * 0.07)
        bend = rrng.random() < 0.3
        k_at = rrng.uniform(0.55, 0.75)
        L, Rr = [], []
        m = 30
        for k in range(m + 1):
            t = k / m
            if bend and t > k_at:
                tb = (t - k_at) / (1 - k_at)
                cx = x + lean * k_at * k_at + (1 if lean > 0 else -1) * h * 0.35 * tb
                cy = C - h * k_at - h * 0.12 * math.sin(tb * 1.6)
            else:
                cx = x + lean * t * t
                cy = C - h * t
            ww = w * (1 - t) ** 0.7 + SS * 0.6
            L.append((cx - ww, cy)); Rr.append((cx + ww, cy))
        d.polygon(L + Rr[::-1], fill=(255, 255, 255, 255))
    return shade(img, 240, 115)
put(draw_reed(), 2, 3)

atlas.save(OUT + "/foliage_atlas.png")
print("atlas ok")
