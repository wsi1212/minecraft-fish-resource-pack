"""Meaningful corruption fixtures for the native dex fish packaging guard."""
import copy
import io
import json
import runpy
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
API = runpy.run_path(str(ROOT / 'tools/check-fish-models.py'))


class FishModelsPackGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contract = json.loads((ROOT / 'tools/fish-models-contract.json').read_text())
        cls.files = {'assets/minecraft/items/cod.json': (ROOT / 'assets/minecraft/items/cod.json').read_bytes()}
        for mid in set(contract['models'].values()):
            model_path = 'assets/minecraft/models/item/fish/' + mid + '.json'
            cls.files[model_path] = (ROOT / model_path).read_bytes()
            for ref in json.loads(cls.files[model_path])['textures'].values():
                ns, relative = ref.split(':', 1)
                path = 'assets/' + ns + '/textures/' + relative + '.png'
                cls.files[path] = (ROOT / path).read_bytes()

    def check(self, changes=None, missing=()):
        with tempfile.TemporaryDirectory(prefix='fish-model-corruption-') as temp:
            path = Path(temp) / 'selected.zip'
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
                for name, data in {**self.files, **(changes or {})}.items():
                    if name not in missing:
                        z.writestr(name, data)
            return API['validate'](ROOT, path)

    def test_current_actual_selected_pack_is_complete(self):
        result = self.check()
        self.assertEqual((490, 489, 489), (result['dexFish'], result['modelFiles'], result['textureFiles']))

    def test_missing_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing fish model dependency'):
            self.check(missing=('assets/minecraft/models/item/fish/ikkideung_mikkuri.json',))

    def test_missing_texture_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing fish model dependency'):
            self.check(missing=('assets/minecraft/textures/item/fish/ikkideung_mikkuri.png',))

    def test_wrong_model_selected_for_a_fish_is_rejected(self):
        data = json.loads(self.files['assets/minecraft/items/cod.json'])
        row = next(c for c in data['model']['cases'] if c['when'] == 'ikkideung_mikkuri')
        row['model']['model'] = 'minecraft:item/fish/beoseotgat_megi'
        with self.assertRaisesRegex(ValueError, 'Missing/wrong fish selector'):
            self.check({'assets/minecraft/items/cod.json': json.dumps(data).encode()})

    def test_another_existing_fish_image_cannot_be_assigned(self):
        path = 'assets/minecraft/models/item/fish/ikkideung_mikkuri.json'
        data = json.loads(self.files[path]); data['textures']['layer0'] = 'minecraft:item/fish/beoseotgat_megi'
        with self.assertRaisesRegex(ValueError, 'Wrong fish image assigned'):
            self.check({path: json.dumps(data).encode()})

    def test_fully_transparent_image_is_rejected(self):
        image = Image.new('RGBA', (16, 16)); out = io.BytesIO(); image.save(out, 'PNG')
        with self.assertRaisesRegex(ValueError, 'Empty fish image'):
            self.check({'assets/minecraft/textures/item/fish/ikkideung_mikkuri.png': out.getvalue()})


if __name__ == '__main__':
    unittest.main()
