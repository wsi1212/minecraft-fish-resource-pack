"""Check generated GUI language assets before packaging, offline and without Java sources."""
from pathlib import Path
import hashlib
import io
import json
import zipfile

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
        for char in provider.get('advances', {}):
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
    menus = validate_baked_menus(root, font)
    return {'locales': 9, 'providers': len(actual) + menus['providers'],
            'textures': len(contract['textureSha256']) + menus['textures'], 'bakedMenus': menus['menus']}


def validate_baked_menus(root, font):
    contract = json.loads((root / 'tools/baked-menu-language-contract.json').read_text())
    prefixes = {'menu': 'menu3_', 'myinfo': 'myinfo3_', 'shop': 'shop3_', 'smithy': 'smithy_'}
    expected = {p['file']: p for p in contract['providers']}
    actual = {p.get('file'): p for p in font['providers'] if any(
        p.get('file', '').startswith('barkan:gui/' + prefix + 'i18n_') for prefix in prefixes.values())}
    errors = []
    if actual != expected or len(actual) != 246:
        errors.append('Baked menu language providers differ from their reviewed native contract')
    used = {}
    for p in font['providers']:
        for line in p.get('chars', []):
            for ch in line:
                used[ch] = used.get(ch, 0) + 1
        for ch in p.get('advances', {}):
            used[ch] = used.get(ch, 0) + 1
    if any(used.get(ch) != 1 for p in expected.values() for line in p['chars'] for ch in line):
        errors.append('Baked menu language glyph collision')
    for name, prefix in prefixes.items():
        proof = contract['plates'][name]
        if proof['outsideLabelRegionsChangedPixels'] != 0 or proof['nativeSize'] != [704, 888]:
            errors.append(name + ': lettering-only geometry proof is incomplete')
        for kind, actual_prefix in [('korean', prefix), ('neutral', prefix + 'i18n_')]:
            im = plate(root, actual_prefix)
            if hashlib.sha256(im.tobytes()).hexdigest() != proof[kind + 'RgbaSha256']:
                errors.append(name + '/' + kind + ': native background changed')
    for relative, checksum in contract['textureSha256'].items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            errors.append('Changed/missing baked menu texture: ' + relative)
            continue
        with Image.open(path) as im:
            if max(im.size) > 256:
                errors.append('Baked menu texture exceeds atlas limit: ' + relative)
    if errors:
        raise ValueError('\n'.join(errors))
    return {'menus': 4, 'providers': len(actual), 'textures': len(contract['textureSha256'])}


def validate_delivered_labels(root, zip_path):
    """Lossless ZIP rewriting may change PNG bytes; labels must keep their pixels/metrics."""
    root = Path(root)
    with zipfile.ZipFile(zip_path) as archive:
        packed_font = json.loads(archive.read('assets/barkan/font/gui.json'))
        files = {p.get('file'): p for p in packed_font['providers']}
        checked = 0
        for name in ('guild-language-art-contract.json', 'baked-menu-language-contract.json'):
            contract = json.loads((root / 'tools' / name).read_text())
            for provider in contract['providers']:
                if files.get(provider['file']) != provider:
                    raise ValueError('Delivered language bitmap metrics changed: ' + provider['file'])
            for relative in contract['textureSha256']:
                with Image.open(root / relative) as original, Image.open(io.BytesIO(archive.read(relative))) as delivered:
                    if original.size != delivered.size or original.convert('RGBA').tobytes() != delivered.convert('RGBA').tobytes():
                        raise ValueError('Delivered language artwork changed: ' + relative)
                checked += 1
    return {'deliveredLanguageTextures': checked}


if __name__ == '__main__':
    import sys
    print(json.dumps(validate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())))
