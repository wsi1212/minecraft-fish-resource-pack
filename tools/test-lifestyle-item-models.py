#!/usr/bin/env python3
"""Small corruption fixtures for the pinned selected lifestyle asset gate."""
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
API = runpy.run_path(str(ROOT / "tools/build-lifestyle-item-models.py"))


class LifestylePackGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "tools/lifestyle-item-models/manifest.json").read_text())
        cls.files = {r["path"]: (ROOT / r["path"]).read_bytes() for r in cls.manifest["outputs"]}
        census = json.loads((ROOT / "tools/lifestyle-item-models/inputs/canonical-census.json").read_text())

        def collect_model(ref):
            if API["qualified"](ref) in cls.manifest["builtinParents"]:
                return
            path = API["asset_path"](ref, "models", ".json")
            if path in cls.files:
                # Pinned models have only builtin parents and direct textures.
                return
            cls.files[path] = (ROOT / path).read_bytes()
            model = json.loads(cls.files[path])
            if model.get("parent"):
                collect_model(model["parent"])
            for texture in model.get("textures", {}).values():
                if not texture.startswith("#"):
                    p = API["asset_path"](texture, "textures", ".png")
                    cls.files[p] = (ROOT / p).read_bytes()

        def collect_definition(node):
            if isinstance(node, dict):
                if isinstance(node.get("model"), str):
                    collect_model(node["model"])
                for value in node.values():
                    collect_definition(value)
            elif isinstance(node, list):
                for value in node:
                    collect_definition(value)

        for _, row in API["canonical_entries"](census):
            if row["itemModel"]:
                p = API["asset_path"](row["itemModel"], "items", ".json")
                cls.files[p] = (ROOT / p).read_bytes()
                collect_definition(json.loads(cls.files[p]))

    def check_zip(self, changes=None, missing=()):
        files = dict(self.files)
        files.update(changes or {})
        with tempfile.TemporaryDirectory(prefix="barkan-lifestyle-negative-") as temp:
            path = Path(temp) / "selected.zip"
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for name, data in files.items():
                    if name not in missing:
                        z.writestr(name, data)
            return API["validate"](ROOT, path)

    def test_lossless_png_optimization_is_allowed(self):
        name = "assets/minecraft/textures/item/custom/drill.png"
        out = io.BytesIO()
        Image.open(io.BytesIO(self.files[name])).save(out, "PNG", optimize=True)
        result = self.check_zip({name: out.getvalue()})
        self.assertEqual((136, 123, 79), (result["canonicalEntries"], result["explicitItemModels"], result["repairedItemModels"]))

    def test_missing_definition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            self.check_zip(missing=("assets/default/items/drill.json",))

    def test_one_pixel_change_is_rejected(self):
        name = "assets/barkan/textures/item/food_lib/cr_apple_pie.png"
        image = Image.open(io.BytesIO(self.files[name])).convert("RGBA")
        rgba = image.getpixel((0, 0)); image.putpixel((0, 0), ((rgba[0] + 1) % 256, *rgba[1:]))
        out = io.BytesIO(); image.save(out, "PNG")
        with self.assertRaisesRegex(ValueError, "pixels/size"):
            self.check_zip({name: out.getvalue()})

    def test_animation_change_is_rejected(self):
        name = "assets/minecraft/textures/item/custom/drill_selected.png.mcmeta"
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            self.check_zip({name: b'{"animation":{"frametime":2}}'})

    def test_missing_model_and_texture_are_rejected(self):
        for name in ("assets/minecraft/models/item/custom/drill_selected.json",
                     "assets/minecraft/textures/item/custom/drill_selected.png"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "missing"):
                self.check_zip(missing=(name,))

    def test_new_canonical_definition_requires_refresh(self):
        census = json.loads((ROOT / "tools/lifestyle-item-models/inputs/canonical-census.json").read_text())
        census["요리"]["entries"].append({"id": "dish:new", "material": "COOKIE", "itemModel": "barkan:new"})
        census["요리"]["count"] += 1
        with tempfile.TemporaryDirectory(prefix="barkan-lifestyle-census-") as temp:
            path = Path(temp) / "fresh.json"; path.write_text(json.dumps(census))
            with self.assertRaisesRegex(ValueError, "canonical IDs"):
                API["_validate"](ROOT, census_path=path)


if __name__ == "__main__":
    unittest.main()
