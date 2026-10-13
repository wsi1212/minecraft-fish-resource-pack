"""Reject missing/misrouted native dex fish models before resource-pack packaging."""
import io
import json
import hashlib
import re
import zipfile
from pathlib import Path
from PIL import Image


def validate(root, zip_path=None):
    root = Path(root)
    contract = json.loads((root / 'tools/fish-models-contract.json').read_text())
    expected = contract['models']
    if len(expected) != contract['dexFishCount'] or not expected:
        raise ValueError('Invalid reviewed dex fish model census')
    # Companion sources are available locally; RP-only CI retains the reviewed census.
    # A definition/registry change needs a new reviewed census before packaging.
    sources_checked = []
    for name, row in contract['authority'].items():
        path = Path(row['path'])
        if path.is_file():
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Fish model authority changed; review new definitions/models: ' + name)
            sources_checked.append(name)
    archive = zipfile.ZipFile(zip_path) if zip_path else None
    def read(path):
        try:
            return archive.read(path) if archive else (root / path).read_bytes()
        except (KeyError, FileNotFoundError) as error:
            raise ValueError('Missing fish model dependency: ' + path) from error
    try:
        selector = json.loads(read('assets/minecraft/items/cod.json'))['model']
        if (selector.get('type') != 'minecraft:select'
                or selector.get('property') != 'minecraft:custom_model_data'
                or selector.get('index', 0) != 0):
            raise ValueError('Fish CMD selector type/property/index changed')
        cases = {}
        for case in selector['cases']:
            names = case['when'] if isinstance(case['when'], list) else [case['when']]
            for name in names:
                if name in cases:
                    raise ValueError('Duplicate fish selector: ' + name)
                cases[name] = case['model']
        models, textures = set(), set()
        for name, model_id in expected.items():
            model_ref = 'minecraft:item/fish/' + model_id
            if cases.get(model_id) != {'type': 'minecraft:model', 'model': model_ref}:
                raise ValueError('Missing/wrong fish selector: ' + name + '/' + model_id)
            model_path = 'assets/minecraft/models/item/fish/' + model_id + '.json'
            model = json.loads(read(model_path)); models.add(model_path)
            if model.get('parent') != 'minecraft:item/generated' or not model.get('textures'):
                raise ValueError('Wrong native fish model structure: ' + model_path)
            if model['textures'].get('layer0') != model_ref:
                raise ValueError('Wrong fish image assigned to model: ' + model_path)
            for texture in model['textures'].values():
                if not isinstance(texture, str) or texture.startswith('#'):
                    raise ValueError('Unresolved fish texture: ' + model_path)
                namespace, _, relative = texture.partition(':')
                if not relative:
                    namespace, relative = 'minecraft', namespace
                if (not re.fullmatch(r'[a-z0-9_.-]+', namespace)
                        or not re.fullmatch(r'[a-z0-9_./-]+', relative)
                        or relative.startswith('/') or '..' in relative.split('/')):
                    raise ValueError('Invalid fish texture resource ID: ' + texture)
                texture_path = 'assets/' + namespace + '/textures/' + relative + '.png'
                with Image.open(io.BytesIO(read(texture_path))) as image:
                    image.load()
                    if image.format != 'PNG' or min(image.size) <= 0 or image.convert('RGBA').getchannel('A').getextrema()[1] == 0:
                        raise ValueError('Empty fish image: ' + texture_path)
                textures.add(texture_path)
        return {'dexFish': len(expected), 'modelFiles': len(models), 'textureFiles': len(textures),
                'sourcesChecked': sources_checked, 'deliveredZip': bool(archive)}
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
