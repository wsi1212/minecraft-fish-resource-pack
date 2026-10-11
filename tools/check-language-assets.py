"""Check generated GUI language assets before packaging, offline and without Java sources."""
from pathlib import Path
import hashlib
import json

from PIL import Image


def plate(root, prefix):
    """Reconstruct exactly what the GUI bitmap providers will display."""
    image = Image.new('RGBA', (704, 888))
    y = 0
    for r, height in enumerate((224, 224, 220, 220)):
        x = 0
        for c, width in enumerate((236, 236, 232)):
            path = root / f'assets/barkan/textures/gui/{prefix}r{r}c{c}.png'
            with Image.open(path) as tile:
                if tile.size != (width, height):
                    raise ValueError('Guild background tile has the wrong native size: ' + str(path))
                image.paste(tile.convert('RGBA'), (x, y))
            x += width
        y += height
    return image


def validate(root):
    root = Path(root)
    contract = json.loads((root / 'tools/guild-language-art-contract.json').read_text())
    font = json.loads((root / 'assets/barkan/font/gui.json').read_text())
    expected = {p['file']: p for p in contract['providers']}
    actual = {p.get('file'): p for p in font['providers']
              if p.get('file', '').startswith('barkan:gui/guild_i18n_')}
    errors = []
    if actual != expected or len(actual) != 66:
        errors.append('Generated GUI language providers do not match the reviewed contract')
    korean = {p['file']: p for p in contract['koreanProviders']}
    if {p.get('file'): p for p in font['providers'] if p.get('file') in korean} != korean:
        errors.append('Korean guild background providers do not match the corrected grid')
    for key, prefix in (('korean', 'guild_'), ('neutral', 'guild_i18n_')):
        layout = contract['backgroundLayout'][key]
        image = plate(root, prefix)
        if hashlib.sha256(image.tobytes()).hexdigest() != layout['rgbaSha256']:
            errors.append(key + ': packed background differs from the corrected native plate')
        if (layout['actionFrames'], layout['largeTiles'], layout['inventoryCells'],
                layout['informationCells'], layout['outsideApprovedRegionsChangedPixels']) != (9, 6, 36, 1, 0):
            errors.append(key + ': guild layout audit is incomplete')
        for cell in layout['cells']:
            if hashlib.sha256(image.crop(cell['box']).tobytes()).hexdigest() != cell['rgbaSha256']:
                errors.append(key + ': missing/changed GUI cell ' + cell['cell'])
    advances = {k: v for p in font['providers'] if p['type'] == 'space'
                for k, v in p['advances'].items()}
    if any(advances.get(chr(0xF818+i)) != 1 << i for i in range(8)):
        errors.append('GUI language cursor shifts are missing')
    owned = {c for p in expected.values() for row in p['chars'] for c in row}
    counts = {c: 0 for c in owned}
    for provider in font['providers']:
        for row in provider.get('chars', []):
            for char in row:
                if char in counts:
                    counts[char] += 1
    if any(n != 1 for n in counts.values()):
        errors.append('A generated GUI language glyph is defined more than once')
    for relative, checksum in contract['textureSha256'].items():
        path = root / relative
        if not path.is_file():
            errors.append('Missing language texture: ' + relative)
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            errors.append('Changed language texture: ' + relative)
        with Image.open(path) as image:
            if max(image.size) > 256:
                errors.append('Language texture exceeds the font atlas limit: ' + relative)
    license_path = root / 'assets/barkan/font/Barkan-International-OFL.txt'
    if not license_path.is_file() or hashlib.sha256(license_path.read_bytes()).hexdigest() != \
            '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2':
        errors.append('Pinned international font license missing/changed')
    if errors:
        raise ValueError('\n'.join(errors))
    return {'locales': 9, 'providers': len(actual), 'textures': len(contract['textureSha256'])}


if __name__ == '__main__':
    import sys
    print(json.dumps(validate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())))
