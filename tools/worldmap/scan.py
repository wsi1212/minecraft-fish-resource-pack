#!/usr/bin/env python3
"""Scan Anvil regions -> per-column (block class id, height, water depth). Output npz."""
import sys, struct, zlib, os, io
import numpy as np
from multiprocessing import Pool

W = "/Users/user/Library/Application Support/feather/player-server/servers/07de2d81-991a-47e2-b62d-06c0d1b5150a/world/region"
X1, X2, Z1, Z2 = -1400, 1400, -1300, 1400   # blocks
OUT = sys.argv[1] if len(sys.argv)>1 else None

# ---- minimal NBT ----
def rd(b, p, t):
    if t == 1: return struct.unpack_from('>b', b, p)[0], p + 1
    if t == 2: return struct.unpack_from('>h', b, p)[0], p + 2
    if t == 3: return struct.unpack_from('>i', b, p)[0], p + 4
    if t == 4: return struct.unpack_from('>q', b, p)[0], p + 8
    if t == 5: return struct.unpack_from('>f', b, p)[0], p + 4
    if t == 6: return struct.unpack_from('>d', b, p)[0], p + 8
    if t == 7:
        n = struct.unpack_from('>i', b, p)[0]; return b[p+4:p+4+n], p + 4 + n
    if t == 8:
        n = struct.unpack_from('>H', b, p)[0]; return b[p+2:p+2+n].decode('utf8', 'replace'), p + 2 + n
    if t == 9:
        it = b[p]; n = struct.unpack_from('>i', b, p+1)[0]; p += 5; out = []
        for _ in range(n):
            v, p = rd(b, p, it); out.append(v)
        return out, p
    if t == 10:
        d = {}
        while True:
            tt = b[p]; p += 1
            if tt == 0: return d, p
            n = struct.unpack_from('>H', b, p)[0]; k = b[p+2:p+2+n].decode(); p += 2 + n
            d[k], p = rd(b, p, tt)
    if t == 11:
        n = struct.unpack_from('>i', b, p)[0]; return np.frombuffer(b, '>i4', n, p+4), p + 4 + 4*n
    if t == 12:
        n = struct.unpack_from('>i', b, p)[0]; return np.frombuffer(b, '>i8', n, p+4), p + 4 + 8*n
    raise ValueError(t)

def parse(b):
    t = b[0]; n = struct.unpack_from('>H', b, 1)[0]
    v, _ = rd(b, 3 + n, t); return v

# ---- block classification ----
# class ids: 0 air/skip, 1 water, then materials
CLS = {}
NAMES = []
def cid(name):
    if name not in CLS: CLS[name] = len(NAMES) + 2; NAMES.append(name)
    return CLS[name]

RULES = [  # (substring, class)  first match wins
    ('cherry_leaves', 'cherry'), ('azalea_leaves', 'leaf'), ('leaves', 'leaf'),
    ('grass_block', 'grass'), ('moss', 'moss'), ('podzol', 'podzol'), ('mycelium', 'podzol'),
    ('short_grass', 'grass'), ('tall_grass', 'grass'), ('fern', 'grass'), ('bush', 'leaf'),
    ('crimson_nylium', 'grass'), ('snow', 'snow'), ('ice', 'ice'),
    ('red_sand', 'redsand'), ('sandstone', 'sandstone'), ('sand', 'sand'), ('gravel', 'gravel'),
    ('terracotta', 'terracotta'), ('mud', 'mud'), ('clay', 'clay'),
    ('coarse_dirt', 'dirt'), ('dirt', 'dirt'), ('farmland', 'dirt'), ('rooted', 'dirt'),
    ('deepslate', 'deepslate'), ('blackstone', 'deepslate'), ('basalt', 'deepslate'),
    ('cobblestone', 'cobble'), ('stone_brick', 'stonebrick'), ('stone', 'stone'),
    ('andesite', 'stone'), ('diorite', 'diorite'), ('granite', 'granite'), ('tuff', 'stone'),
    ('calcite', 'diorite'), ('dripstone', 'granite'),
    ('spruce', 'spruce'), ('dark_oak', 'darkoak'), ('oak', 'oak'), ('birch', 'birch'),
    ('acacia', 'acacia'), ('jungle', 'jungle'), ('mangrove', 'mangrove'), ('cherry', 'cherry'),
    ('bamboo', 'birch'), ('crimson', 'mangrove'), ('warped', 'jungle'),
    ('brick', 'brick'), ('quartz', 'quartz'), ('white', 'white'), ('concrete', 'white'), ('wool', 'white'),
    ('iron', 'iron'), ('copper', 'copper'), ('gold', 'gold'), ('lantern', 'gold'), ('torch', 'gold'),
    ('prismarine', 'prismarine'), ('glass', 'glass'), ('lava', 'lava'), ('magma', 'lava'),
    ('wheat', 'crop'), ('carrots', 'crop'), ('potatoes', 'crop'), ('beetroots', 'crop'), ('hay', 'hay'),
    ('pumpkin', 'orange'), ('melon', 'grass'), ('cactus', 'cactus'), ('dead_bush', 'dirt'),
    ('lily_pad', 'grass'), ('kelp', 'skip'), ('seagrass', 'skip'), ('sea_pickle', 'skip'),
    ('flower', 'flower'), ('tulip', 'flower'), ('poppy', 'flower'), ('dandelion', 'flower'), ('rose', 'flower'),
    ('lilac', 'flower'), ('peony', 'flower'), ('cornflower', 'flower'), ('allium', 'flower'), ('orchid', 'flower'),
    ('azure', 'flower'), ('lily_of', 'flower'),
    ('vine', 'leaf'), ('carpet', 'white'), ('planks', 'oak'), ('log', 'oak'), ('wood', 'oak'), ('stripped', 'oak'),
    ('slab', 'stone'), ('stairs', 'stone'), ('wall', 'stone'), ('fence', 'oak'), ('door', 'oak'),
    ('path', 'dirt'), ('bedrock', 'deepslate'), ('obsidian', 'deepslate'), ('netherrack', 'granite'),
    ('ore', 'stone'), ('dye', 'white'),
]
SKIP_EXACT = {'air', 'cave_air', 'void_air', 'light', 'barrier', 'structure_void'}
SKIP_SUB = ('kelp', 'seagrass', 'sea_pickle', 'coral', 'button', 'pressure_plate', 'sign', 'banner', 'rail', 'tripwire',
            'redstone_wire', 'ladder', 'lever', 'head', 'skull', 'candle', 'frame', 'painting', 'bell', 'chain', 'rod',
            'pane', 'bars', 'trapdoor', 'lantern', 'torch', 'amethyst_cluster', 'sculk_vein', 'glow_lichen', 'pale_hanging',
            'hanging_roots', 'cobweb', 'fire', 'string')
WATERLIKE = {'water', 'bubble_column'}
for _s,_c in RULES:
    if _c!='skip': cid(_c)
cid('other')
_cache = {}
def classify(name):
    r = _cache.get(name)
    if r is not None: return r
    n = name.replace('minecraft:', '')
    if n in SKIP_EXACT: r = 0
    elif n in WATERLIKE: r = 1
    elif any(s in n for s in SKIP_SUB) and 'glass_pane' not in n and 'iron_bars' not in n:
        r = 0
    else:
        r = None
        for sub, c in RULES:
            if sub in n:
                r = 0 if c == 'skip' else CLS[c]; break
        if r is None: r = CLS['other']
    _cache[name] = r
    return r

def unpack(data, bits, n):
    """unpack 1.16+ style (no straddling) longs -> n indices"""
    per = 64 // bits
    a = data.astype('>i8').view('>u8').astype(np.uint64)
    idx = np.arange(n)
    word = a[idx // per]
    return ((word >> ((idx % per) * bits).astype(np.uint64)) & np.uint64((1 << bits) - 1)).astype(np.int32)

def scan_chunk(ch):
    """-> cls[16,16], h[16,16] (top solid y), wd[16,16] water depth, or None"""
    secs = ch.get('sections') or ch.get('Level', {}).get('Sections')
    if not secs: return None
    secs = sorted([s for s in secs if 'block_states' in s], key=lambda s: -s['Y'])
    cls = np.zeros((16, 16), np.uint8)
    hy = np.full((16, 16), -64, np.int16)
    wd = np.zeros((16, 16), np.uint8)
    done = np.zeros((16, 16), bool)      # finished (solid top found)
    wtop = np.full((16, 16), -999, np.int16)  # water surface y (first water seen)
    for s in secs:
        bs = s['block_states']; pal = bs['palette']
        pc = np.array([classify(p['Name']) for p in pal], np.uint8)
        if len(pal) == 1:
            arr = np.full(4096, pc[0], np.uint8)
        else:
            bits = max(4, (len(pal) - 1).bit_length())
            arr = pc[unpack(bs['data'], bits, 4096)]
        arr = arr.reshape(16, 16, 16)   # y, z, x
        y0 = s['Y'] * 16
        for yy in range(15, -1, -1):
            if done.all(): break
            row = arr[yy]
            y = y0 + yy
            # water columns
            isw = (row == 1)
            first_w = isw & (wtop == -999) & ~done
            wtop[first_w] = y
            solid = (row > 1) & ~done
            if solid.any():
                cls[solid] = row[solid]; hy[solid] = y
                w = solid & (wtop > -999)
                wd[w] = np.clip(wtop[w] - y, 0, 255)
                done |= solid
        if done.all(): break
    # water-only columns (no floor found) -> deep
    nf = ~done & (wtop > -999)
    cls[nf] = 1; hy[nf] = wtop[nf]; wd[nf] = 255
    cls[~done & ~nf] = 0
    # cls==1 marks pure deep water column
    return cls, hy, wd

def do_region(args):
    rx, rz = args
    fn = f"{W}/r.{rx}.{rz}.mca"
    if not os.path.exists(fn): return rx, rz, None
    with open(fn, 'rb') as f: data = f.read()
    C = np.zeros((512, 512), np.uint8); H = np.full((512, 512), -64, np.int16); D = np.zeros((512, 512), np.uint8)
    have = np.zeros((512, 512), bool)
    for i in range(1024):
        off = struct.unpack_from('>I', data, i * 4)[0]
        if off == 0: continue
        sec, cnt = off >> 8, off & 255
        p = sec * 4096
        ln = struct.unpack_from('>I', data, p)[0]; comp = data[p + 4]
        raw = data[p + 5:p + 4 + ln]
        b = zlib.decompress(raw) if comp == 2 else raw
        ch = parse(b)
        if ch.get('Status', '').replace('minecraft:', '') not in ('full', ''): pass
        r = scan_chunk(ch)
        if r is None: continue
        cx, cz = i % 32, i // 32
        sl = (slice(cz * 16, cz * 16 + 16), slice(cx * 16, cx * 16 + 16))
        C[sl], H[sl], D[sl] = r
        have[sl] = True
    return rx, rz, (C, H, D, have)

if __name__ == '__main__':
    rxs = range(X1 // 512, X2 // 512 + 1); rzs = range(Z1 // 512, Z2 // 512 + 1)
    jobs = [(x, z) for x in rxs for z in rzs]
    ox, oz = min(rxs) * 512, min(rzs) * 512
    nx, nz = len(rxs) * 512, len(rzs) * 512
    C = np.zeros((nz, nx), np.uint8); H = np.full((nz, nx), -64, np.int16); D = np.zeros((nz, nx), np.uint8)
    HAVE = np.zeros((nz, nx), bool)
    with Pool(8) as p:
        for rx, rz, r in p.imap_unordered(do_region, jobs):
            print('region', rx, rz, 'ok' if r else 'missing', flush=True)
            if not r: continue
            sl = (slice((rz - min(rzs)) * 512, (rz - min(rzs) + 1) * 512), slice((rx - min(rxs)) * 512, (rx - min(rxs) + 1) * 512))
            C[sl], H[sl], D[sl], HAVE[sl] = r[0], r[1], r[2], r[3]
    # class names must be consistent across processes -> recompute mapping deterministically
    np.savez_compressed(OUT, C=C, H=H, D=D, HAVE=HAVE, ox=ox, oz=oz)
    print('done', C.shape)
