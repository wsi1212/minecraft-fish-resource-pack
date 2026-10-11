"""Verify the audited native GUI grids before a pack is published.

This release gate reads only resource-pack files. Full source/ROI/Java checks
live with the native compilers; this checks the actual bitmap providers and
pixels users receive, including every recorded interactive/inventory cell.
"""
from collections import Counter
from pathlib import Path
import hashlib
import io
import json
import os
import re
import zipfile

from PIL import Image


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate(root, zip_path=None):
    root = Path(root)
    contract = json.loads((root / 'tools/gui-layout-contract.json').read_text())
    archive = zipfile.ZipFile(zip_path) if zip_path else None
    def read(relative):
        return archive.read(relative) if archive else (root / relative).read_bytes()
    try:
        font = json.loads(read('assets/barkan/font/gui.json'))
        providers = font['providers']
        by_file = {p.get('file'): p for p in providers if p.get('file')}
        gui = [p for p in providers if p.get('file', '').startswith('barkan:gui/')]
        counts = Counter(ch for p in providers for line in p.get('chars', []) for ch in line)
        counts.update(ch for p in providers if p['type'] == 'space' for ch in p['advances'])
        shifts = {ch: value for p in providers if p['type'] == 'space' for ch, value in p['advances'].items()}
        required_shifts = {0xF801: -8, 0xF802: -1, 0xF803: -177}
        required_shifts.update({0xF810+i: -(1 << i) for i in range(8)})
        required_shifts.update({0xF818+i: 1 << i for i in range(8)})
        if any(shifts.get(chr(ch)) != value or counts[chr(ch)] != 1
               for ch, value in required_shifts.items()):
            raise ValueError('GUI background cursor shifts are missing, duplicated or changed')
        for p in gui:
            relative = 'assets/barkan/textures/' + p['file'].split(':', 1)[1]
            read(relative)  # Every existing and newly added GUI provider needs its file.
            if any(counts[ch] != 1 for line in p.get('chars', []) for ch in line):
                raise ValueError('Duplicate GUI glyph: ' + p['file'])
        checked_cells = 0
        for group in contract['plates']:
            expected = group['providers']
            columns = group.get('columns', [236, 236, 232])
            tile_rows = group.get('tileRows', 4)
            scale = group.get('scale', 4)
            baseline = group.get('baseline', 13)
            if (scale not in (1, 4) or tile_rows not in (1, 3, 4)
                    or len(expected) != len(columns)*tile_rows
                    or sum(columns) != group['nativeSize'][0]
                    or any(by_file.get(p['file']) != p for p in expected)):
                raise ValueError('Missing/changed GUI provider: ' + group['name'])
            # Full chest backgrounds share this exact atlas grid. The single
            # 192x104 profile glyph uses its original one-pixel art separately.
            if scale == 4 and columns != [236, 236, 232]:
                raise ValueError('Changed native chest columns: ' + group['name'])
            if scale == 1 and (columns != [192] or tile_rows != 1 or baseline != 18):
                raise ValueError('Changed profile geometry: ' + group['name'])
            image = Image.new('RGBA', group['nativeSize'])
            y = 0
            for r in range(tile_rows):
                x = 0
                height = expected[r*len(columns)]['height']*scale
                for c, width in enumerate(columns):
                    p = expected[r*len(columns)+c]
                    if p['height']*scale != height:
                        raise ValueError('GUI columns use different bitmap scales: ' + group['name'])
                    path = 'assets/barkan/textures/' + p['file'].split(':', 1)[1]
                    payload = read(path)
                    # ZIP optimization may losslessly rewrite PNG bytes. Decoded
                    # pixels stay the authority for the delivered ZIP.
                    if not archive and sha(payload) != group['textureSha256'][path]:
                        raise ValueError('Changed GUI texture: ' + path)
                    with Image.open(io.BytesIO(payload)) as tile:
                        if tile.size != (width, height) or max(tile.size) > 256:
                            raise ValueError('Wrong native GUI tile size: ' + path)
                        if y % scale or p['ascent'] != baseline-y//scale:
                            raise ValueError('GUI tile baseline moved: ' + path)
                        image.paste(tile.convert('RGBA'), (x, y))
                    x += width
                y += height
            if y != image.height or sha(image.tobytes()) != group['rgbaSha256']:
                raise ValueError('Packed GUI differs from the reviewed layout: ' + group['name'])
            for cell in group['cells']:
                box = cell['box']
                if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
                    raise ValueError('GUI cell is outside its real window: ' + group['name'])
                if sha(image.crop(box).tobytes()) != cell['rgbaSha256']:
                    raise ValueError('Missing/changed GUI cell: ' + group['name'] + '/' + cell['name'])
                checked_cells += 1
        # The local deployer/build sees the companion Java repository. Check it
        # here, in the actual packaging path, so a newly added menu cannot reuse
        # an old grid audit silently. Standalone RP CI still checks packed pixels.
        java_root = Path(os.environ.get('BARKAN_JAVA_ROOT', Path.home() / 'development/blockship-plugin'))
        java_checked = (java_root / 'src/main/java').is_dir()
        if java_checked:
            sources = {}
            for path in sorted((java_root / 'src/main/java').rglob('*.java')):
                code = path.read_text()
                if re.search(r'\bcreateInventory\s*\(', code) or path.name in ('Plates.java', 'GuiTitle.java', 'GuildMenuArt.java', 'BakedMenuArt.java', 'GuiFrame.java'):
                    sources[str(path.relative_to(java_root))] = sha(path.read_bytes())
            if sources != contract['javaGuiSources']:
                raise ValueError('Java GUI code changed: compare the new buttons/window sizes and refresh the native layout audit')
        return dict(guiProviders=len(gui), auditedPlates=len(contract['plates']),
                    checkedCells=checked_cells, deliveredZip=bool(archive), javaGuiSourcesChecked=java_checked)
    finally:
        if archive:
            archive.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--zip', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.root, args.zip)))
