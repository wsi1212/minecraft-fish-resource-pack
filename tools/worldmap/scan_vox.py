#!/usr/bin/env python3
"""Extract a voxel volume (block-name ids) for a world window from Anvil files.
usage: scan_vox.py out.npz x1 x2 z1 z2 [ymin ymax]"""
import sys, os, struct, zlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan as S0   # reuse NBT parser + unpack (scan.py needs argv guard, handled there)

NAMES = {}      # name -> gid
LIST = []
def gid(name):
    g = NAMES.get(name)
    if g is None:
        g = len(LIST); NAMES[name] = g; LIST.append(name)
    return g

def extract(x1, x2, z1, z2, ymin=56, ymax=260):
    gid('minecraft:air')
    W, D, H = x2 - x1 + 1, z2 - z1 + 1, ymax - ymin + 1
    vol = np.zeros((H, D, W), np.uint16)
    rx0, rx1 = x1 >> 9, x2 >> 9; rz0, rz1 = z1 >> 9, z2 >> 9
    for rz in range(rz0, rz1 + 1):
        for rx in range(rx0, rx1 + 1):
            fn = f"{S0.W}/r.{rx}.{rz}.mca"
            if not os.path.exists(fn): continue
            data = open(fn, 'rb').read()
            for i in range(1024):
                cx, cz = i % 32, i // 32
                bx, bz = rx * 512 + cx * 16, rz * 512 + cz * 16
                if bx + 15 < x1 or bx > x2 or bz + 15 < z1 or bz > z2: continue
                off = struct.unpack_from('>I', data, i * 4)[0]
                if off == 0: continue
                p = (off >> 8) * 4096
                ln = struct.unpack_from('>I', data, p)[0]; comp = data[p + 4]
                raw = data[p + 5:p + 4 + ln]
                ch = S0.parse(zlib.decompress(raw) if comp == 2 else raw)
                for s in ch.get('sections') or []:
                    if 'block_states' not in s: continue
                    y0 = s['Y'] * 16
                    if y0 + 15 < ymin or y0 > ymax: continue
                    bs = s['block_states']; pal = bs['palette']
                    pg = np.array([gid(q['Name']) for q in pal], np.uint16)
                    if len(pal) == 1: arr = np.full(4096, pg[0], np.uint16)
                    else:
                        bits = max(4, (len(pal) - 1).bit_length())
                        arr = pg[S0.unpack(bs['data'], bits, 4096)]
                    arr = arr.reshape(16, 16, 16)  # y,z,x
                    # clip to window
                    ya, yb = max(y0, ymin), min(y0 + 15, ymax)
                    xa, xb = max(bx, x1), min(bx + 15, x2)
                    za, zb = max(bz, z1), min(bz + 15, z2)
                    vol[ya - ymin:yb - ymin + 1, za - z1:zb - z1 + 1, xa - x1:xb - x1 + 1] = \
                        arr[ya - y0:yb - y0 + 1, za - bz:zb - bz + 1, xa - bx:xb - bx + 1]
    return vol

if __name__ == '__main__':
    out = sys.argv[1]; x1, x2, z1, z2 = map(int, sys.argv[2:6])
    ymin = int(sys.argv[6]) if len(sys.argv) > 6 else 56
    ymax = int(sys.argv[7]) if len(sys.argv) > 7 else 260
    vol = extract(x1, x2, z1, z2, ymin, ymax)
    np.savez_compressed(out, vol=vol, names=np.array(LIST), x1=x1, z1=z1, ymin=ymin)
    print('vol', vol.shape, 'names', len(LIST), 'nonair', int((vol != 0).sum()))
