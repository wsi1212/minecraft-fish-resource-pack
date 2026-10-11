#!/usr/bin/env python3
"""Restore selected, original CE lifestyle assets; verify them before/after packing.

Runtime validation needs only Python's standard library and Pillow. Original CE
YAML was resolved once when pinning the existing generated pack; no CE runtime,
YAML parser, network, or regeneration of artwork is used by this gate.
"""
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

from PIL import Image


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def qualified(value):
    return value if ":" in value else "minecraft:" + value


def asset_path(ref, kind, suffix):
    namespace, tail = qualified(ref).split(":", 1)
    if ".." in tail.split("/") or not tail or namespace in ("", ".", ".."):
        raise ValueError("Unsafe asset reference: " + ref)
    return f"assets/{namespace}/{kind}/{tail}{suffix}"


def normalized_model(node):
    if isinstance(node, list):
        return [normalized_model(v) for v in node]
    if not isinstance(node, dict):
        return node
    result = {}
    for key, value in node.items():
        if key in ("type", "property", "model") and isinstance(value, str):
            value = qualified(value)
        elif isinstance(value, (dict, list)):
            value = normalized_model(value)
        result[key] = value
    return result


def canonical_entries(census):
    result = []
    for category, group in census.items():
        if not isinstance(group, dict) or "entries" not in group:
            continue
        if group["count"] != len(group["entries"]):
            raise ValueError("Canonical census count mismatch: " + category)
        ids = set()
        for entry in group["entries"]:
            if entry["id"] in ids:
                raise ValueError("Duplicate canonical ID: " + entry["id"])
            ids.add(entry["id"])
            result.append((category, entry))
    if not result:
        raise ValueError("Empty canonical lifestyle census")
    return result


def bindings(census):
    return sorted((category, row["id"], row.get("itemModel"), row["material"])
                  for category, row in canonical_entries(census))


def _pinned(root):
    base = root / "tools/lifestyle-item-models"
    manifest = load(base / "manifest.json")
    if manifest.get("schemaVersion") != 1:
        raise ValueError("Unsupported lifestyle manifest")
    inputs = base / "inputs"
    for row in manifest["inputs"]:
        path = inputs / row["path"]
        if not path.is_file() or sha(path.read_bytes()) != row["sha256"]:
            raise ValueError("Pinned original input changed/missing: " + row["path"])
    census_row = manifest["census"]
    path = inputs / census_row["path"]
    if not path.is_file() or sha(path.read_bytes()) != census_row["sha256"]:
        raise ValueError("Pinned canonical census changed/missing")
    census = load(path)
    if len(canonical_entries(census)) != census_row["entries"]:
        raise ValueError("Pinned canonical entry count mismatch")
    output_paths = set()
    for row in manifest["outputs"]:
        if row["path"] in output_paths or not row["path"].startswith("assets/"):
            raise ValueError("Duplicate/unsafe owned output: " + row["path"])
        output_paths.add(row["path"])
        path = inputs / row["input"]
        if not path.is_file() or sha(path.read_bytes()) != row["sha256"]:
            raise ValueError("Pinned original payload changed/missing: " + row["input"])
    return manifest, inputs, census


def _sources(root, manifest, java_root=None):
    explicit_root = java_root is not None
    java_root = Path(java_root) if explicit_root else root.parent / "blockship-plugin"
    checked = []
    if java_root.is_dir():
        for row in manifest["javaAuthorities"]:
            path = java_root / row["javaPath"]
            if not path.is_file() or sha(path.read_bytes()) != row["sha256"]:
                raise ValueError("Lifestyle authority changed; refresh actual census/bindings: "
                                 + row["javaPath"])
            checked.append(row["javaPath"])
    elif explicit_root:
        raise ValueError("Requested Java source root does not exist: " + str(java_root))
    # The fresh JVM census uses the actual packaged runtime recipes, which can
    # differ from the development plugin's recipes.json. Never substitute it.
    recipe = manifest.get("runtimeRecipes")
    if recipe and Path(recipe["originalPath"]).is_file():
        if sha(Path(recipe["originalPath"]).read_bytes()) != recipe["sha256"]:
            raise ValueError("Actual runtime recipes changed; refresh canonical census")
        checked.append(recipe["originalPath"])
    return checked


def _validate(root, zip_path=None, census_path=None, java_root=None):
    root = Path(root).resolve()
    manifest, inputs, census = _pinned(root)
    if census_path and bindings(load(Path(census_path))) != bindings(census):
        raise ValueError("Current canonical IDs/materials/item_models differ from pinned census")
    checked_sources = _sources(root, manifest, java_root)
    archive = zipfile.ZipFile(zip_path) if zip_path else None
    try:
        names = set(archive.namelist()) if archive else None

        def exists(name):
            return name in names if archive else (root / name).is_file()

        def read(name):
            if not exists(name):
                raise ValueError("Required lifestyle asset missing: " + name)
            return archive.read(name) if archive else (root / name).read_bytes()

        # Owned files have exact source hashes. ZIP PNG optimization may change
        # compression, so packed PNGs must preserve size and every RGBA pixel.
        for row in manifest["outputs"]:
            data = read(row["path"])
            if archive and row["path"].endswith(".png"):
                image = Image.open(io.BytesIO(data)).convert("RGBA")
                if list(image.size) != row["nativeSize"] or sha(image.tobytes()) != row["rgbaSha256"]:
                    raise ValueError("Packed original texture pixels/size changed: " + row["path"])
            elif sha(data) != row["sha256"]:
                raise ValueError("Original output bytes changed: " + row["path"])

        for ref, binding in manifest["canonicalBindings"].items():
            definition = json.loads(read(binding["itemDefinition"]))
            if normalized_model(definition["model"]) != binding["normalizedCeModel"]:
                raise ValueError("CE source model binding mismatch: " + ref)

        # Also traverse every already-present canonical item_model, not only
        # the repaired dishes/drill. Builtin parents are narrow explicit IDs.
        visited, builtin = set(), set(manifest["builtinParents"])

        def visit_model(ref):
            if qualified(ref) in builtin:
                return
            path = asset_path(ref, "models", ".json")
            if path in visited:
                return
            visited.add(path)
            model = json.loads(read(path))
            if model.get("parent"):
                visit_model(model["parent"])
            for value in model.get("textures", {}).values():
                if isinstance(value, str) and not value.startswith("#"):
                    read(asset_path(value, "textures", ".png"))

        def visit_definition(node):
            if isinstance(node, dict):
                if isinstance(node.get("model"), str):
                    visit_model(node["model"])
                for value in node.values():
                    visit_definition(value)
            elif isinstance(node, list):
                for value in node:
                    visit_definition(value)

        null_models, refs = [], set()
        for category, row in canonical_entries(census):
            ref = row.get("itemModel")
            if ref is None:
                null_models.append({"category": category, "id": row["id"],
                                    "material": row["material"],
                                    "scope": "Canonical builder has no item_model; vanilla/legacy CMD path is separate"})
                continue
            refs.add(ref)
            visit_definition(json.loads(read(asset_path(ref, "items", ".json"))))
        return {"status": "PASS", "deliveredZip": str(zip_path) if zip_path else None,
                "canonicalEntries": len(canonical_entries(census)),
                "explicitItemModels": len(refs), "repairedItemModels": len(manifest["canonicalBindings"]),
                "ownedFiles": len(manifest["outputs"]), "ownedOriginalBytes": sum(r["bytes"] for r in manifest["outputs"]),
                "referencedModelFiles": len(visited), "nullModels": null_models,
                "javaAuthoritySourcesChecked": checked_sources,
                "currentCensusCompared": str(census_path) if census_path else None,
                "scope": "File/JSON/pixel/animation dependency validation; no actual Minecraft client render"}
    finally:
        if archive:
            archive.close()


def validate(root, zip_path=None):
    """Read-only shared pack gate (raises on stale/missing/changed dependencies)."""
    return _validate(root, zip_path)


def build(root):
    root = Path(root).resolve()
    manifest, inputs, _ = _pinned(root)
    _sources(root, manifest)
    for row in manifest["outputs"]:
        target = root / row["path"]
        data = (inputs / row["input"]).read_bytes()
        if target.exists() and target.read_bytes() != data:
            raise ValueError("Refusing to overwrite a different existing asset: " + row["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return validate(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--check", action="store_true", help="Read-only input/output/current-source checks")
    parser.add_argument("--zip", type=Path, help="Also check delivered JSON bytes, pixels and animation metadata")
    parser.add_argument("--census", type=Path, help="Fresh canonical builder census; reject registry/model drift")
    parser.add_argument("--java-root", type=Path, help="Explicit source root to require and compare")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.check:
        build(args.root)
    result = _validate(args.root, args.zip, args.census, args.java_root)
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
