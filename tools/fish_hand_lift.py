#!/usr/bin/env python3
"""Fit fish held-item models using alpha-weighted center of mass and visible bounds.

Preview with:
    python3 tools/fish_hand_lift.py
Apply the whole-catalog alignment with:
    python3 tools/fish_hand_lift.py --apply
Align selected models using the same visual anchor:
    python3 tools/fish_hand_lift.py --apply --only gaebogchi maega_oli

The baseline file makes --apply idempotent: rerunning it recalculates from the
original hand scales and translations, avoiding cumulative lift or shrinking.
The accepted reference fish defines the safe model-space frame; GUI and ground
poses remain untouched. Camera FOV/aspect-ratio still need in-game verification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = PACK_ROOT / "assets" / "minecraft"
MODEL_DIR = ASSETS_ROOT / "models" / "item" / "fish"
BASELINE_PATH = Path(__file__).resolve().with_name("fish_hand_lift_baseline.json")
HAND_POSES = (
    "firstperson_righthand",
    "firstperson_lefthand",
    "thirdperson_righthand",
    "thirdperson_lefthand",
)


def alpha_center_of_mass(image_path: Path) -> tuple[float, float, float]:
    """Return normalized COM x/y and visible fraction, weighted by alpha."""
    from PIL import Image

    with Image.open(image_path) as source:
        alpha = source.convert("RGBA").getchannel("A")
        width, height = alpha.size
        raw = alpha.tobytes()

    row_mass = [sum(raw[y * width : (y + 1) * width]) for y in range(height)]
    total = sum(row_mass)
    if total == 0:
        raise ValueError(f"texture is fully transparent: {image_path}")

    # Pixel centers keep the result symmetric for even-sized textures.
    com_y = sum((y + 0.5) * mass for y, mass in enumerate(row_mass)) / total
    col_mass = [0] * width
    for y in range(height):
        offset = y * width
        for x, value in enumerate(raw[offset : offset + width]):
            col_mass[x] += value
    com_x = sum((x + 0.5) * mass for x, mass in enumerate(col_mass)) / total
    visible_fraction = total / (255 * width * height)
    return com_x / width, com_y / height, visible_fraction


def texture_path(model: dict, model_path: Path) -> Path | None:
    texture = model.get("textures", {}).get("layer0")
    if not isinstance(texture, str):
        return None
    if texture.startswith("minecraft:"):
        texture = texture.removeprefix("minecraft:")
    elif ":" in texture:
        return None
    path = ASSETS_ROOT / "textures" / f"{texture}.png"
    return path if path.is_file() else None


def load_baselines() -> dict:
    if BASELINE_PATH.is_file():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {"format": 1, "models": {}}


def json_bytes(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def visible_bounds(path: Path) -> tuple[float, float, float, float]:
    from PIL import Image
    with Image.open(path) as im:
        alpha = im.convert("RGBA").getchannel("A")
        box = alpha.point(lambda value: 255 if value >= 32 else 0).getbbox()
        if box is None:
            raise ValueError(f"no visible body: {path}")
        return (box[0] / im.width, box[1] / im.height,
                box[2] / im.width, box[3] / im.height)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--anchor-model", default="gaebogchi")
    parser.add_argument("--anchor-y", type=float, default=3.0)
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--hand-depth-ratio", type=float,
                        help="Persist a generated-mesh depth ratio for selected first-person models")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.hand_depth_ratio is not None and not 0 < args.hand_depth_ratio <= 1:
        parser.error("--hand-depth-ratio must be greater than zero and at most one")
    baselines = load_baselines()
    baselines["format"] = 2
    originals = baselines.setdefault("poses", {})
    entries = []
    for path in sorted(MODEL_DIR.glob("*.json")):
        model = json.loads(path.read_text())
        image = texture_path(model, path)
        if image is None:
            raise ValueError(f"unresolvable texture: {path}")
        cx, cy, mass = alpha_center_of_mass(image)
        bounds = visible_bounds(image)
        saved = originals.setdefault(path.name, {})
        for name in HAND_POSES:
            pose = model["display"][name]
            if pose.get("rotation", [0, 0, 0]) != [0, 0, 0]:
                raise ValueError(f"rotated pose requires projected bounds: {path}, {name}")
            # Version 1 aligned Y only, so its current scale and X are originals.
            saved.setdefault(name, {
                "scale": list(pose.get("scale", [1, 1, 1])),
                "translation": list(pose.get("translation", [0, 0, 0])),
            })
        entries.append(dict(path=path, model=model, cx=cx, cy=cy, bounds=bounds, saved=saved))
    ref = next(e for e in entries if e["path"].stem == args.anchor_model)
    report = []
    changed = 0
    for e in entries:
        if args.only and e["path"].stem not in args.only:
            continue
        before = json_bytes(e["model"])
        pose_report = {}
        for name in HAND_POSES:
            ref_scale = ref["saved"][name]["scale"]
            scale = e["saved"][name]["scale"]
            # Distance from alpha COM to all four visible edges in model units.
            def extents(item, base_scale):
                left, top, right, bottom = item["bounds"]
                return [(item["cx"]-left)*16*base_scale[0],
                        (right-item["cx"])*16*base_scale[0],
                        (item["cy"]-top)*16*base_scale[1],
                        (bottom-item["cy"])*16*base_scale[1]]
            allowed = extents(ref, ref_scale)
            distances = extents(e, scale)
            factor = min([1.0] + [a / d for a, d in zip(allowed, distances) if d > 0])
            # Round down so serialized scales never push an edge outside the frame.
            import math
            fitted = [math.floor(v*factor*1_000_000)/1_000_000 for v in scale]
            if name.startswith("firstperson"):
                if args.hand_depth_ratio is not None:
                    e["saved"][name]["hand_depth_ratio"] = args.hand_depth_ratio
                # Stored separately from original scales so ordinary full-catalog
                # refits retain the chosen mesh depth without cumulative shrink.
                fitted[2] = math.floor(fitted[2] * e["saved"][name].get("hand_depth_ratio", 1)
                                       * 1_000_000) / 1_000_000
            tx = ref["saved"][name]["translation"][0] + (ref["cx"]-.5)*16*ref_scale[0]
            ty = args.anchor_y + (.5-ref["cy"])*16*ref_scale[1]
            translation = list(e["saved"][name]["translation"])
            translation[0] = round(tx-(e["cx"]-.5)*16*fitted[0], 6)
            translation[1] = round(ty-(.5-e["cy"])*16*fitted[1], 6)
            pose = e["model"]["display"][name]
            pose["scale"] = fitted
            pose["translation"] = translation
            pose_report[name] = dict(fit=factor, scale=fitted, translation=translation,
                                     edges=extents(e, fitted), allowed=allowed)
        after = json_bytes(e["model"])
        if before != after:
            changed += 1
            if args.apply:
                e["path"].write_bytes(after)
        report.append(dict(model=e["path"].stem, com=[e["cx"], e["cy"]], bounds=e["bounds"], poses=pose_report))
    if args.apply:
        BASELINE_PATH.write_bytes(json_bytes(baselines))
    if args.report:
        args.report.write_bytes(json_bytes(dict(anchor=args.anchor_model, anchor_y=args.anchor_y,
                                                count=len(entries), changed=changed, items=report)))
    print(f"Analyzed {len(entries)} fish; changed {changed}; {'applied' if args.apply else 'preview'}. "
          f"All four hand poses fit the calibrated {args.anchor_model} frame.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
