#!/usr/bin/env python3
"""Isometric-ish voxel town renderer (camera SE looking NW, like the website map).
usage: vox_render.py TOWN   (TOWN key in TOWNS)"""
import sys, os, json, math, re
import numpy as np
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scan_vox

ROOT = "/Users/user/Library/Application Support/feather/player-server/servers/07de2d81-991a-47e2-b62d-06c0d1b5150a"
TEX = f"{ROOT}/plugins/Skript/scripts/website/assets/mc-blocks"
NPCJ = f"{ROOT}/plugins/BlockShip/npc.json"
FONT = f"{ROOT}/plugins/Skript/scripts/website/assets/barkan-aggro-bold.ttf"

EL = math.radians(float(os.environ.get('EL', 40)))
CE, SE = math.cos(EL), math.sin(EL)
R2 = math.sqrt(2)
FINAL = 2048
RENDER = 3072

# key: (title, cx, cz, cy, screen width in blocks)
TOWNS = {
    'harbor': ('바르칸 항구', 380, 925, 76, 360),
    'desert': ('사막마을', -455, 200, 68, 190),
    'upper':  ('상단마을', 1075, -70, 66, 310),
    'royal':  ('왕도', 463, 203, 90, 300),
}
FORCE_HEAL_TO_GUILD = {'desert'}
# NPC-tag -> label text (None = skip)
TAGS = {'대장간': '대장간', '상점': '상점', '길드': '길드', '물고기 판매': '물고기 판매', '요리': '요리',
        '여관': '여관', '유저마켓': '마켓', '회복': '회복', '조선소': '조선소', '말 대여': '말 대여', '퀘스트': '퀘스트'}

# ------------------------------------------------------------ palette
_tc = {}
def texavg(fn):
    if fn in _tc: return _tc[fn]
    p = f"{TEX}/{fn}.png"
    if not os.path.exists(p): _tc[fn] = None; return None
    im = Image.open(p).convert('RGBA'); w, h = im.size
    if h > w: im = im.crop((0, 0, w, w))
    a = np.asarray(im, np.float32); m = a[..., 3] > 128
    if not m.any(): _tc[fn] = None; return None
    c = a[..., :3][m].mean(0); _tc[fn] = c; return c

SKIP_SUB = ('air', 'flower', 'tulip', 'poppy', 'dandelion', 'orchid', 'allium', 'azure_bluet', 'cornflower', 'lily_of', 'rose_bush',
            'peony', 'lilac', 'sunflower', 'short_grass', 'tall_grass', 'fern', 'sapling', 'bush', 'vine', 'torch', 'lantern', 'chain',
            'rail', 'button', 'pressure_plate', 'sign', 'banner', 'ladder', 'lever', 'carpet', 'fence', 'iron_bars', 'candle', 'head',
            'skull', 'frame', 'painting', 'bell', 'cobweb', 'string', 'tripwire', 'redstone_wire', 'fire', 'kelp', 'seagrass',
            'coral', 'sea_pickle', 'hanging_roots', 'glow_lichen', 'sculk_vein', 'amethyst_cluster', 'pointed_dripstone', 'lily_pad',
            'dead_bush', 'berry_bush', 'wheat', 'carrots', 'potatoes', 'beetroots', 'bamboo', 'sugar_cane', 'pot', 'light', 'barrier',
            'structure_void', 'moss_carpet', 'hay_block_never', 'leaf_litter', 'wildflowers', 'pink_petals', 'firefly', 'cactus_flower',
            'scaffolding', 'shulker', 'rod', 'campfire', 'cake', 'repeater', 'comparator', 'daylight', 'end_rod', 'lightning_rod')
LEAF_TINT = {'oak': (78, 142, 50), 'spruce': (62, 104, 64), 'birch': (118, 158, 78), 'jungle': (56, 148, 34), 'acacia': (104, 156, 48),
             'dark_oak': (56, 116, 40), 'mangrove': (96, 150, 58)}
SUF = ('_stairs', '_slab', '_wall', '_fence_gate', '_fence', '_trapdoor', '_door', '_button', '_pressure_plate')
def resolve(name):
    n = name.replace('minecraft:', '')
    if n in ('water', 'bubble_column'): return 2, (60, 140, 190)
    if n == 'lava': return 1, (236, 110, 30)
    if any(s in n for s in SKIP_SUB) and 'glass' not in n and 'iron_bars' not in n: return 0, (0, 0, 0)
    if n == 'grass_block': return 1, (122, 178, 66)
    if n.endswith('leaves'):
        if 'cherry' in n or 'azalea' in n:
            c = texavg(n); return 1, tuple(c) if c is not None else (236, 160, 190)
        sp = next((k for k in ('dark_oak', 'spruce', 'birch', 'jungle', 'acacia', 'mangrove', 'oak') if n.startswith(k)), 'oak')
        return 1, tuple(0.92 * np.array(LEAF_TINT[sp]))
    if n in ('dirt_path',): c = texavg('dirt_path_top')
    else:
        base = n
        for s in SUF:
            if base.endswith(s): base = base[:-len(s)]; break
        cands = [n, base, base + '_planks', base + 's', base.replace('_brick', '_bricks'), base + '_block', base + '_top', base + '_side', base + '_front']
        c = None
        for cnd in cands:
            c = texavg(cnd)
            if c is not None: break
    if c is None:
        c = np.array([148, 128, 108], np.float32)
        if 'glass' in n: c = np.array([170, 205, 225], np.float32)
    return 1, tuple(c)

def build_palette(names):
    kind = np.zeros(len(names), np.uint8); rgb = np.zeros((len(names), 3), np.float32)
    for i, nm in enumerate(names):
        k, c = resolve(str(nm)); kind[i] = k; rgb[i] = c
    return kind, rgb

# ------------------------------------------------------------ polygon offset tables
def poly_offsets(pts, margin=0.85):
    pts = np.array(pts, np.float64)
    cen = pts.mean(0)
    # order convex hull by angle
    ang = np.arctan2(pts[:, 1] - cen[1], pts[:, 0] - cen[0]); pts = pts[np.argsort(ang)]
    x0, y0 = np.floor(pts.min(0) - 2).astype(int); x1, y1 = np.ceil(pts.max(0) + 2).astype(int)
    out = []
    for j in range(y0, y1 + 1):
        for i in range(x0, x1 + 1):
            ok = True
            for a in range(4):
                p, q = pts[a], pts[(a + 1) % 4]
                e = q - p; L = math.hypot(*e)
                d = (e[0] * (j - p[1]) - e[1] * (i - p[0])) / L   # signed distance (positive = left of edge)
                # interior is on one side; determine using centroid sign
                dc = (e[0] * (cen[1] - p[1]) - e[1] * (cen[0] - p[0])) / L
                if dc > 0: d = -d
                if d > margin: ok = False; break
            if ok: out.append((i, j))
    return np.array(out, np.int32)

def proj_rel(dx, dy, dz, S):
    return ((dx - dz) * S / R2, (-dy * CE + (dx + dz) * SE / R2) * S)

def main(key):
    title, cx, cz, cy, Wb = TOWNS[key]
    S = RENDER / Wb
    R = int(Wb * 0.95)
    x1, x2, z1, z2 = cx - R, cx + R, cz - R, cz + R
    ymin, ymax = 56, 210
    print('scan', x1, x2, z1, z2, flush=True)
    vol = scan_vox.extract(x1, x2, z1, z2, ymin, ymax)
    names = scan_vox.LIST
    kind, rgb = build_palette(names)
    K = kind[vol]
    solid = (K == 1); water = (K == 2)
    Hn, Dn, Wn = solid.shape
    del K
    print('solid', int(solid.sum()), 'water', int(water.sum()), flush=True)

    def nb(a, axis):        # value of neighbour at +1 along axis; False outside
        o = np.zeros_like(a)
        sl_dst = [slice(None)] * 3; sl_src = [slice(None)] * 3
        sl_dst[axis] = slice(0, -1); sl_src[axis] = slice(1, None)
        o[tuple(sl_dst)] = a[tuple(sl_src)]; return o
    s_up, s_x, s_z = nb(solid, 0), nb(solid, 2), nb(solid, 1)
    w_up, w_x, w_z = nb(water, 0), nb(water, 2), nb(water, 1)
    top = solid & ~s_up & ~w_up
    east = solid & ~s_x & ~w_x
    south = solid & ~s_z & ~w_z
    wtop = water & ~w_up & ~s_up
    # water depth
    dep = np.zeros((Dn, Wn), np.float32); wdepth = np.zeros(water.shape, np.float32)
    for y in range(Hn):
        dep = np.where(water[y], dep + 1, 0); wdepth[y] = dep
    # max solid height per column (absolute idx units: top surface = y+1)
    ys = np.arange(Hn, dtype=np.float32)[:, None, None] + 1
    Hmax = (solid * ys).max(0)
    # sun shadow ceiling
    L = np.array([-0.45, 0.68, 0.50]); L /= np.linalg.norm(L)
    hh = np.array([L[0], L[2]]); hn = np.linalg.norm(hh); hx, hz = hh / hn; slope = L[1] / hn
    SH = np.zeros((Dn, Wn), np.float32)
    for k in range(1, 46):
        ox, oz = int(round(k * hx)), int(round(k * hz))
        sh = np.full((Dn, Wn), -1e9, np.float32)
        zs0, zs1 = max(0, -oz), min(Dn, Dn - oz); xs0, xs1 = max(0, -ox), min(Wn, Wn - ox)
        sh[zs0:zs1, xs0:xs1] = Hmax[zs0 + oz:zs1 + oz, xs0 + ox:xs1 + ox] - k * slope
        SH = np.maximum(SH, sh)
    occ = ndi.gaussian_filter(solid.astype(np.float32), 1.3)

    faces = []   # (type, iy,iz,ix, color(float), key)
    def add(mask, ftype, diff, front_off, yref_off):
        iy, iz, ix = np.nonzero(mask)
        col = rgb[vol[iy, iz, ix]].copy()
        # water top color from depth
        if ftype == 3:
            dd = np.clip(wdepth[iy, iz, ix] / 26.0, 0, 1) ** 0.8
            sh_ = np.array([100, 200, 202], np.float32); mid = np.array([54, 140, 188], np.float32); dp = np.array([30, 88, 146], np.float32)
            t = dd[:, None]
            col = np.where(t < 0.5, sh_ + (mid - sh_) * (t / 0.5), mid + (dp - mid) * ((t - 0.5) / 0.5))
        # lighting
        yref = iy + yref_off
        shad = (yref + 0.02 < SH[iz, ix]).astype(np.float32)
        fy, fz, fx = iy + front_off[0], iz + front_off[1], ix + front_off[2]
        fy = np.clip(fy, 0, Hn - 1); fz = np.clip(fz, 0, Dn - 1); fx = np.clip(fx, 0, Wn - 1)
        ao = np.clip(1.12 - 1.5 * occ[fy, fz, fx], 0.58, 1.0)
        amb = 0.55
        shade = (amb + (1 - amb) * diff * (1 - 0.92 * shad)) * ao * 1.12
        if ftype == 3: shade = (0.92 - 0.18 * shad)
        noise = (((ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791)) & 255) / 255.0 - 0.5
        col = col * (shade * (1 + 0.09 * noise))[:, None]
        nearness = (ix + iz) * CE / R2 + iy * SE
        if ftype == 3: nearness = nearness + 0.5 * SE   # surface sits at top of the cell
        faces.append((np.full(len(iy), ftype, np.uint8), iy.astype(np.int32), iz.astype(np.int32), ix.astype(np.int32),
                      col.astype(np.float32), nearness.astype(np.float32)))
    add(top, 0, max(L[1], 0), (1, 0, 0), 1.0)
    add(east, 1, max(L[0], 0), (0, 0, 1), 0.5)
    add(south, 2, max(L[2], 0), (0, 1, 0), 0.5)
    add(wtop, 3, 0, (1, 0, 0), 1.0)
    del occ
    ft = np.concatenate([f[0] for f in faces]); fiy = np.concatenate([f[1] for f in faces])
    fiz = np.concatenate([f[2] for f in faces]); fix_ = np.concatenate([f[3] for f in faces])
    fcol = np.concatenate([f[4] for f in faces]); fnear = np.concatenate([f[5] for f in faces])
    print('faces', len(ft), flush=True)
    order = np.argsort(fnear, kind='stable')
    ft, fiy, fiz, fix_, fcol = ft[order], fiy[order], fiz[order], fix_[order], fcol[order]

    # patch tables
    tabs = []
    quad = {0: [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)],
            1: [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
            2: [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]}
    quad[3] = quad[0]
    for t in range(4):
        pts = [proj_rel(*p, S) for p in quad[t]]
        tabs.append(poly_offsets(pts))
    Pmax = max(len(t) for t in tabs)
    tab = np.zeros((4, Pmax, 2), np.int32)
    for t in range(4):
        o = tabs[t]; tab[t, :len(o)] = o; tab[t, len(o):] = o[0]
    print('patch', [len(t) for t in tabs], flush=True)

    # camera: world centre -> canvas centre
    lx, lz, ly = cx - x1, cz - z1, cy - ymin
    ux0, uy0 = proj_rel(lx, ly, lz, S)
    offx, offy = RENDER / 2 - ux0, RENDER / 2 - uy0
    canvas = np.zeros((RENDER, RENDER, 3), np.uint8); canvas[:] = (30, 88, 146)
    ax = np.round((fix_ - fiz) * S / R2 + offx).astype(np.int32)
    ay = np.round((-fiy * CE + (fix_ + fiz) * SE / R2) * S + offy).astype(np.int32)
    CH = 60000
    for a in range(0, len(ft), CH):
        b = min(a + CH, len(ft))
        px = ax[a:b, None] + tab[ft[a:b], :, 0]; py = ay[a:b, None] + tab[ft[a:b], :, 1]
        m = (px >= 0) & (px < RENDER) & (py >= 0) & (py < RENDER)
        colu = np.clip(fcol[a:b], 0, 255).astype(np.uint8)
        cc = np.broadcast_to(colu[:, None, :], (b - a, Pmax, 3))
        canvas[py[m], px[m]] = cc[m]
    img = Image.fromarray(canvas).resize((FINAL, FINAL), Image.LANCZOS)
    sc = FINAL / RENDER

    # ---------------- labels ----------------
    npcs = json.load(open(NPCJ))['npcs']
    raw = []
    for nm, v in npcs.items():
        if v.get('world') != 'world': continue
        mm = re.search(r'\[([^\]]+)\]', v.get('displayName', ''))
        if not mm: continue
        tag = mm.group(1)
        if tag not in TAGS: continue
        x, z = v['x'], v['z']
        if not (x1 + 8 <= x <= x2 - 8 and z1 + 8 <= z <= z2 - 8): continue
        raw.append((TAGS[tag], x, z, v['y']))
    # cluster same label within 24 blocks
    cl = []
    for t, x, z, y in raw:
        for c in cl:
            if c[0] == t and math.hypot(c[1] / c[4] - x, c[2] / c[4] - z) < 24:
                c[1] += x; c[2] += z; c[3] += y; c[4] += 1; break
        else: cl.append([t, x, z, y, 1])
    # merge different labels standing within 16 blocks (same building) -> one pill
    mg = []
    for t, x, z, y, n in cl:
        cxx, czz = x / n, z / n
        for m in mg:
            if math.hypot(m['x'] / m['n'] - cxx, m['z'] / m['n'] - czz) < 16:
                if t not in m['t']: m['t'].append(t)
                m['x'] += cxx; m['z'] += czz; m['y'] += y / n; m['n'] += 1; break
        else: mg.append({'t': [t], 'x': cxx, 'z': czz, 'y': y / n, 'n': 1})
    if key in FORCE_HEAL_TO_GUILD:   # 회복 NPC 라벨을 길드 라벨에 합친다
        g = next((m for m in mg if '길드' in m['t']), None)
        h = next((m for m in mg if m['t'] == ['회복']), None)
        if g and h:
            g['t'].append('회복'); g['x'] += h['x']; g['z'] += h['z']; g['y'] += h['y']; g['n'] += h['n']; mg.remove(h)
    cl = [[m['t'], m['x'], m['z'], m['y'], m['n']] for m in mg]
    def project(x, y, z):
        u, v = proj_rel(x - x1, y - ymin, z - z1, S)
        return (u + offx) * sc, (v + offy) * sc
    lab = []
    for t, x, z, y, n in cl:
        x, z = x / n, z / n
        ix, iz = int(x - x1), int(z - z1)
        rr = 3
        roof = Hmax[max(iz - rr, 0):iz + rr + 1, max(ix - rr, 0):ix + rr + 1].max() + ymin
        px, py = project(x, roof, z)
        if not (60 < px < FINAL - 60 and 150 < py < FINAL - 60): continue
        lab.append([t, px, py])
    print('labels', lab, flush=True)
    font = ImageFont.truetype(FONT, 38)
    lay = Image.new('RGBA', img.size, (0, 0, 0, 0)); shl = Image.new('RGBA', img.size, (0, 0, 0, 0))
    dl, ds = ImageDraw.Draw(lay), ImageDraw.Draw(shl)
    lab.sort(key=lambda l: l[2])
    placed = []
    for tl, px, py in lab:
        lines = [' · '.join(tl[i:i + 3]) for i in range(0, len(tl), 3)] if isinstance(tl, list) else [tl]
        t = '\n'.join(lines)
        tw = max(dl.textlength(q, font=font) for q in lines); w, h = tw + 34, 16 + 46 * len(lines)
        lx_, ly_ = px, py - 70
        for _ in range(30):
            box = (lx_ - w / 2, ly_ - h / 2, lx_ + w / 2, ly_ + h / 2)
            if any(not (box[2] < p[0] - 6 or box[0] > p[2] + 6 or box[3] < p[1] - 6 or box[1] > p[3] + 6) for p in placed):
                ly_ -= 30
            else: break
        placed.append((lx_ - w / 2, ly_ - h / 2, lx_ + w / 2, ly_ + h / 2))
        # pointer line + dot
        ds.line([(px, py), (lx_, ly_ + h / 2)], fill=(0, 0, 0, 200), width=8)
        dl.line([(px, py), (lx_, ly_ + h / 2)], fill=(255, 250, 235, 255), width=4)
        dl.ellipse([px - 9, py - 9, px + 9, py + 9], fill=(255, 210, 80, 255), outline=(38, 30, 66, 255), width=4)
        rb = [lx_ - w / 2, ly_ - h / 2, lx_ + w / 2, ly_ + h / 2]
        ds.rounded_rectangle([rb[0], rb[1] + 6, rb[2], rb[3] + 6], radius=24, fill=(0, 0, 0, 190))
        dl.rounded_rectangle(rb, radius=24, fill=(255, 250, 235, 255), outline=(38, 30, 66, 255), width=5)
        for qi, q in enumerate(lines):
            dl.text((lx_, ly_ - h / 2 + 8 + 23 + 46 * qi - 2), q, font=font, anchor='mm', fill=(38, 30, 66, 255))
    tf = ImageFont.truetype(FONT, 96)
    ds.text((FINAL // 2, 120 + 6), title, font=tf, anchor='mm', fill=(0, 0, 0, 200), stroke_width=20, stroke_fill=(0, 0, 0, 200))
    dl.text((FINAL // 2, 120), title, font=tf, anchor='mm', fill=(255, 250, 235, 255), stroke_width=14, stroke_fill=(38, 30, 66, 255))
    shl = shl.filter(ImageFilter.GaussianBlur(6))
    out = Image.alpha_composite(Image.alpha_composite(img.convert('RGBA'), shl), lay).convert('RGB')
    out.save(f'{HERE}/iso_{key}.png')
    print('saved', key)

if __name__ == '__main__':
    main(sys.argv[1])
