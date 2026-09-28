#!/usr/bin/env python3
"""Center fish held-item models using each texture's alpha-weighted center of mass.

Preview with:
    python3 tools/fish_hand_lift.py
Apply the calculated first/third-person hand translations with:
    python3 tools/fish_hand_lift.py --apply

The baseline file makes --apply idempotent: rerunning it recalculates from the
original hand translations instead of adding the lift a second time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write calculated hand transforms")
    parser.add_argument(
        "--target-com",
        type=float,
        help="target vertical COM as a fraction from the top (default: median across fish)",
    )
    args = parser.parse_args()
    if args.target_com is not None and not 0 < args.target_com < 1:
        parser.error("--target-com must be between 0 and 1")

    baselines = load_baselines()
    baseline_models = baselines.setdefault("models", {})
    entries: list[dict] = []
    skipped: list[str] = []

    for model_path in sorted(MODEL_DIR.glob("*.json")):
        try:
            model = json.loads(model_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append(f"{model_path.name}: invalid model JSON ({exc})")
            continue
        image_path = texture_path(model, model_path)
        if image_path is None:
            skipped.append(f"{model_path.name}: no resolvable layer0 texture")
            continue
        try:
            com_x, com_y, visible_fraction = alpha_center_of_mass(image_path)
        except (OSError, ValueError) as exc:
            skipped.append(f"{model_path.name}: {exc}")
            continue

        display = model.setdefault("display", {})
        saved = baseline_models.get(model_path.name)
        baseline_y: dict[str, float] = {}
        for pose_name in HAND_POSES:
            pose = display.setdefault(pose_name, {})
            if saved is not None and pose_name in saved:
                base_y = float(saved[pose_name])
            else:
                current = pose.get("translation", [0, 0, 0])
                base_y = float(current[1]) if len(current) > 1 else 0.0
            baseline_y[pose_name] = base_y
        baseline_models[model_path.name] = baseline_y

        hand_scales = [
            float(display[name].get("scale", [1, 1, 1])[1])
            for name in HAND_POSES
        ]
        entries.append(
            {
                "path": model_path,
                "model": model,
                "com_x": com_x,
                "com_y": com_y,
                "visible_fraction": visible_fraction,
                "baseline_y": baseline_y,
                "hand_scale": sum(hand_scales) / len(hand_scales),
            }
        )

    if not entries:
        print("No fish models with readable layer0 textures were found.")
        return 1

    target = args.target_com if args.target_com is not None else median(e["com_y"] for e in entries)
    print(f"Fish models analyzed: {len(entries)}")
    print(f"Target vertical alpha COM: {target:.3f} (texture y fraction, top to bottom)")
    print("Model                         COM-y   lift   old-y -> new-y")

    changed_files: list[tuple[Path, bytes]] = []
    raised = 0
    for entry in entries:
        model = entry["model"]
        display = model["display"]
        # Positive JSON y moves the held item upward. Convert texture fraction
        # to Minecraft's 16-unit item-model coordinate space. Alpha is the
        # silhouette's mass proxy, so transparent padding has no influence.
        lift = max(0.0, (entry["com_y"] - target) * 16.0)
        if lift > 0.01:
            raised += 1
        old_values = []
        changed = False
        new_y = round(entry["baseline_y"][HAND_POSES[0]] + lift, 3)
        for pose_name in HAND_POSES:
            pose = display[pose_name]
            translation = list(pose.get("translation", [0, 0, 0]))
            while len(translation) < 3:
                translation.append(0)
            old_values.append(float(translation[1]))
            desired_y = round(entry["baseline_y"][pose_name] + lift, 3)
            if float(translation[1]) != desired_y or "translation" not in pose and desired_y != 0:
                changed = True
                translation[1] = desired_y
                pose["translation"] = translation
        if lift > 0.01 or any(value != 0 for value in old_values):
            print(
                f"{entry['path'].stem:29} {entry['com_y']:.3f}  +{lift:5.2f}  "
                f"{old_values[0]:5.2f} -> {new_y:5.2f}"
            )
        if args.apply and changed:
            changed_files.append((entry["path"], json_bytes(model)))

    if skipped:
        print(f"\nSkipped {len(skipped)} model(s):")
        for message in skipped:
            print(f"  {message}")

    if args.apply:
        for path, content in changed_files:
            path.write_bytes(content)
        BASELINE_PATH.write_bytes(json_bytes(baselines))
        print(f"\nApplied calculated lifts to {len(changed_files)} models; raised {raised}.")
        print(f"Baseline saved at {BASELINE_PATH}")
    else:
        print(f"\nPreview only: {raised} of {len(entries)} models would be raised.")
        print("Run again with --apply to write the transforms.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
