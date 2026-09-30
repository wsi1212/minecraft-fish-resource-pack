#!/usr/bin/env python3
import sys, numpy as np
from scipy import ndimage as ndi
from PIL import Image
import scan

S = sys.argv[1]; OUTP = sys.argv[2]
TITLE = sys.argv[6]; TCX, TCZ, THW = int(sys.argv[7]), int(sys.argv[8]), int(sys.argv[9])
TILT = float(sys.argv[3]) if len(sys.argv) > 3 else 24.0     # degrees from straight down
VEX = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0      # vertical exaggeration
SIZE = int(sys.argv[5]) if len(sys.argv) > 5 else 2048
SS = 6  # supersample (town zoom)

d = np.load(S)
C, H, D, HAVE = d['C'].astype(np.int32), d['H'].astype(np.float32), d['D'].astype(np.float32), d['HAVE']
inv = {v: k for k, v in scan.CLS.items()}
water = D > 0
SEA = float(np.median((H + D)[water])) if water.any() else 62.0
print('sea level', SEA)
surf = np.where(water, SEA, H)          # geometric surface height
solidtop = C > 1
# treat columns with no data as deep water
nodata = (C == 0) | ~HAVE
water |= nodata
surf[nodata] = SEA; D[nodata] = 60

nz, nx = C.shape
rng = np.random.default_rng(7)

PAL = {
    'grass': (104, 158, 62), 'leaf': (58, 110, 44), 'moss': (84, 130, 56), 'podzol': (96, 78, 46), 'cherry': (236, 160, 190),
    'snow': (240, 245, 250), 'ice': (170, 205, 235), 'redsand': (196, 108, 58), 'sandstone': (214, 196, 150),
    'sand': (226, 208, 156), 'gravel': (140, 136, 132), 'terracotta': (176, 100, 68), 'mud': (90, 70, 60), 'clay': (150, 158, 170),
    'dirt': (128, 92, 60), 'deepslate': (76, 76, 84), 'cobble': (122, 122, 122), 'stonebrick': (128, 128, 128),
    'stone': (126, 126, 128), 'diorite': (190, 190, 192), 'granite': (150, 104, 90), 'spruce': (72, 52, 32), 'darkoak': (60, 42, 22),
    'oak': (160, 128, 76), 'birch': (200, 190, 140), 'acacia': (170, 90, 50), 'jungle': (150, 106, 76), 'mangrove': (120, 50, 50),
    'brick': (150, 80, 66), 'quartz': (232, 228, 220), 'white': (226, 226, 222), 'iron': (200, 200, 204), 'copper': (192, 116, 84),
    'gold': (240, 200, 70), 'prismarine': (90, 160, 150), 'glass': (180, 210, 230), 'lava': (240, 110, 30), 'crop': (196, 176, 70),
    'hay': (214, 180, 60), 'orange': (220, 130, 40), 'cactus': (70, 130, 60), 'flower': (200, 90, 130), 'other': (140, 130, 120),
}
lut = np.zeros((256, 3), np.float32)
for k, v in scan.CLS.items():
    lut[v] = PAL.get(k, (140, 130, 120))
base = lut[np.clip(C, 0, 255)]
# per-block variation
noise = rng.normal(0, 1, (nz, nx)).astype(np.float32)
noise = 0.6 * noise + 0.8 * ndi.gaussian_filter(noise, 2.0) * 6
base *= (1 + 0.035 * np.clip(noise, -2.5, 2.5))[..., None]
# altitude tint: higher grass paler/cooler, lowlands lusher
rel = np.clip((surf - SEA) / 140.0, 0, 1)
isgrass = np.isin(C, [scan.CLS['grass'], scan.CLS['leaf'], scan.CLS['moss']])
base[isgrass] = base[isgrass] * (1 - 0.12 * rel[isgrass][:, None]) + np.array([170, 175, 150]) * 0.12 * rel[isgrass][:, None]

# ---------- lighting ----------
Hs = ndi.gaussian_filter(surf, 0.7)
gy, gx = np.gradient(Hs)
# light from north-west (az 315), elevation ~ 42deg
lx, ly, lz = -0.55, -0.55, 0.62
zex = 1.6
nxv, nyv, nzv = -gx * zex, -gy * zex, np.ones_like(gx)
ln = np.sqrt(nxv**2 + nyv**2 + nzv**2)
lam = (nxv * lx + nyv * ly + nzv * lz) / ln
lam0 = lz / np.sqrt(lx*lx+ly*ly+lz*lz)
shade = 1.0 + 0.95 * (lam - lam0)
# cavity / AO
blur = ndi.gaussian_filter(surf, 3.5)
ao = np.clip((surf - blur) / 6.0, -1, 1)          # >0 convex, <0 concave
shade *= (1 + 0.16 * ao)
# tall-thing local contrast (trees/buildings vs ground)
blur2 = ndi.gaussian_filter(surf, 12)
ao2 = np.clip((surf - blur2) / 25.0, -1, 1)
shade *= (1 + 0.10 * ao2)
# cast shadows: marching toward SE (away from NW light)
shadow = np.zeros_like(surf)
tanel = np.tan(np.radians(38))
sd = np.array([1, 1]) / np.sqrt(2)
best = np.full_like(surf, -1e9)
for k in range(1, 48):
    dx = int(round(k * sd[0])); dz = int(round(k * sd[1]))
    sh = np.full_like(surf, -1e9)
    sh[dz:, dx:] = surf[:nz - dz, :nx - dx] - k * tanel
    best = np.maximum(best, sh)
shadow = np.clip((best - surf) / 3.0, 0, 1)
shadow = ndi.gaussian_filter(shadow, 0.8)
shade *= (1 - 0.30 * shadow)
shade = np.clip(shade, 0.55, 1.4)
land = base * shade[..., None]
# warm sun tint in light / cool tint in shadow
warm = np.array([1.03, 1.0, 0.94], np.float32); cool = np.array([0.90, 0.96, 1.10], np.float32)
t = np.clip((shade - 0.7) / 0.6, 0, 1)[..., None]
land = land * (cool * (1 - t) + warm * t)

# ---------- water ----------
isw = water
landmask = ~isw
dist = ndi.distance_transform_edt(isw)        # distance from land, inside water
depth = np.maximum(D, 0)
dd = np.clip(np.maximum(depth / 30.0, np.minimum(dist / 70.0, 1.0)), 0, 1)
dd = dd**0.8
dd = ndi.gaussian_filter(dd, 1.2)
shallow = np.array([104, 200, 200], np.float32); mid = np.array([52, 138, 186], np.float32); deep = np.array([28, 84, 140], np.float32)
wc = np.where((dd < 0.5)[..., None], shallow + (mid - shallow) * (dd / 0.5)[..., None],
              mid + (deep - mid) * ((dd - 0.5) / 0.5)[..., None])
# gentle wave texture
wave = ndi.gaussian_filter(rng.normal(0, 1, (nz, nx)).astype(np.float32), 14) * 110
wc *= (1 + 0.035 * np.clip(wave, -1.5, 1.5))[..., None]
# river vs sea: rivers are shallow strips -> keep them a bit greener/lighter (dd already small)
# coast foam (surf) + sand bleed
foam = np.clip(1.15 - dist / 2.6, 0, 1) * (0.6 + 0.4 * np.clip(rng.normal(0, 1, (nz, nx)), -1, 1))
foam = ndi.gaussian_filter(foam, 0.6)
wc = wc * (1 - 0.65 * foam[..., None]) + np.array([236, 246, 250]) * 0.65 * foam[..., None]
# soft shadow of land over water (cliffs/mountains near coast)
wc *= (1 - 0.18 * shadow)[..., None]
img = np.where(isw[..., None], wc, land)
# bridges/piers over water: solid tops over water where seabed... (solid above sea) already land
img = np.clip(img, 0, 255)

# ---------- town crop ----------
_ox, _oz = int(d['ox']), int(d['oz'])
_c = np.cos(np.radians(TILT))
M = 60
HD = int(THW / _c)
x0 = TCX - THW - _ox - M; x1 = TCX + THW - _ox + M
y0 = TCZ - _oz - HD - M; y1 = TCZ - _oz + HD + M + 40
img = img[y0:y1, x0:x1]; surf_c = surf[y0:y1, x0:x1]; isw_c = isw[y0:y1, x0:x1]
nz2, nx2 = img.shape[:2]

# ---------- oblique projection with extruded walls (painter's algorithm) ----------
c = np.cos(np.radians(TILT)); s = np.sin(np.radians(TILT)) * VEX
hmin, hmax = float(SEA - 2), float(surf_c.max())
hh = np.maximum(surf_c - SEA, 0)               # flat sea, land relative to sea
top_off = float(hh.max()) * s
CH = int(np.ceil((nz2 * c + top_off + 8) * SS)); CW = nx2 * SS
canvas = np.zeros((CH, CW, 3), np.float32)
# sky/ocean base: ocean color at far edges
canvas[:] = np.array([28, 84, 140], np.float32)
imgx = np.repeat(img, SS, axis=1)               # nearest in x
hhx = np.repeat(hh, SS, axis=1)
wallmul = np.array([0.60, 0.60, 0.66], np.float32)
ytop = (top_off + np.arange(nz2)[:, None] * c - hh * s) * SS       # dest y per source pixel (float, SS scale)
ytopx = np.repeat(ytop, SS, axis=1)
ar = np.arange(CW)
# also paint sea as flat rows (fill everything not covered afterwards)
for z in range(nz2):
    y0f = ytopx[z]
    nxt = ytopx[z + 1] if z + 1 < nz2 else y0f + c * SS
    L = np.maximum(np.ceil(nxt - y0f).astype(np.int32), int(np.ceil(c * SS)))
    L = np.minimum(L, 260)
    ys0 = np.floor(y0f).astype(np.int32)
    ltop = int(np.ceil(c * SS))
    col = imgx[z]
    maxL = int(L.max())
    for k in range(maxL):
        m = L > k
        yk = ys0[m] + k
        ok = (yk >= 0) & (yk < CH)
        if k < ltop:
            canvas[yk[ok], ar[m][ok]] = col[m][ok]
        else:
            f = 1.0 - 0.25 * (k - ltop) / np.maximum(L[m] - ltop, 1)
            canvas[yk[ok], ar[m][ok]] = (col[m] * wallmul * f[:, None])[ok]
cy0 = int((top_off + M * c) * SS); cx0 = M * SS
canvas = canvas[cy0:cy0 + 2 * THW * SS, cx0:cx0 + 2 * THW * SS]
out = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))
# fit to square
W_, H_ = out.size
sc = SIZE / max(W_, H_)
out = out.resize((max(1, round(W_ * sc)), max(1, round(H_ * sc))), Image.LANCZOS)
sq = Image.new('RGB', (SIZE, SIZE), (28, 84, 140))
sc_ = sc
sq.paste(out, ((SIZE - out.width) // 2, (SIZE - out.height) // 2))

from PIL import ImageDraw, ImageFont, ImageFilter
OX, OZ = int(d['ox']), int(d['oz'])
FONT = '/Users/user/Library/Application Support/feather/player-server/servers/07de2d81-991a-47e2-b62d-06c0d1b5150a/plugins/Skript/scripts/website/assets/barkan-aggro-bold.ttf'
# (text, world x, world z, size, dx, dy, dot)   dx/dy = final-pixel nudges
LABELS = []
def proj(wx, wz):
    ix = int(np.clip(wx - (OX + x0), 0, nx2 - 1)); iz = int(np.clip(wz - (OZ + y0), 0, nz2 - 1))
    hgt = max(surf_c[iz, ix] - SEA, 0)
    xc = (wx - (OX + x0)) * SS; yc = (top_off + (wz - (OZ + y0)) * c - hgt * s) * SS
    return xc * sc + (SIZE - out.width) // 2, yc * sc + (SIZE - out.height) // 2
lay = Image.new('RGBA', sq.size, (0, 0, 0, 0)); sh = Image.new('RGBA', sq.size, (0, 0, 0, 0))
dl = ImageDraw.Draw(lay); ds = ImageDraw.Draw(sh)
for t, wx, wz, sz, dx, dy, dot in LABELS:
    px, py = proj(wx, wz); px += dx; py += dy
    print(t, round(px), round(py))
    f = ImageFont.truetype(FONT, sz)
    sw = max(5, sz // 7)
    tw = ds.textlength(t, font=f)
    if dot:
        r = sz // 5
        for D_, col in ((ds, (0, 0, 0, 200)),):
            D_.ellipse([px - r - 3, py - dy - r - 3 + 6, px + r + 3, py - dy + r + 3 + 6], fill=col)
        dl.ellipse([px - r - 3, py - dy - r - 3, px + r + 3, py - dy + r + 3], fill=(40, 30, 60, 255))
        dl.ellipse([px - r, py - dy - r, px + r, py - dy + r], fill=(255, 210, 80, 255))
    ds.text((px, py + 6), t, font=f, anchor='mm', fill=(0, 0, 0, 200), stroke_width=sw + 3, stroke_fill=(0, 0, 0, 200))
    dl.text((px, py), t, font=f, anchor='mm', fill=(255, 250, 235, 255), stroke_width=sw, stroke_fill=(38, 30, 66, 255))
tf = ImageFont.truetype(FONT, 72)
ds.text((SIZE//2, 110 + 6), TITLE, font=tf, anchor='mm', fill=(0,0,0,200), stroke_width=15, stroke_fill=(0,0,0,200))
dl.text((SIZE//2, 110), TITLE, font=tf, anchor='mm', fill=(255,250,235,255), stroke_width=11, stroke_fill=(38,30,66,255))
sh = sh.filter(ImageFilter.GaussianBlur(5))
sq = Image.alpha_composite(Image.alpha_composite(sq.convert('RGBA'), sh), lay).convert('RGB')
sq.save(OUTP)
print('saved', OUTP, sq.size)
