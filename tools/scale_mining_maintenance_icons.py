#!/usr/bin/env python3
"""Normalize mining-maintenance skill badges to the common 64px icon footprint.

The four maintenance icons were drawn with a 59–64px alpha footprint, while
the other mining badges occupy roughly 50–54px.  Their item-model GUI scale is
already shared, so only their texture canvas needs shrinking.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / "assets/minecraft/textures/item/barkan_icon"
NAMES = (
    "skill_mining_maintenance",
    "skill_mining_protective_coating",
    "skill_mining_emergency_repair",
    "skill_mining_artisan_touch",
)
STATES = ("", "_avail", "_locked", "_maxed")
SCALE = 0.84


def resize_centered(source: Image.Image) -> Image.Image:
    """Keep the transparent canvas but match the established badge footprint."""
    edge = round(source.width * SCALE)
    scaled = source.resize((edge, edge), Image.Resampling.NEAREST)
    out = Image.new("RGBA", source.size)
    offset = ((source.width - edge) // 2, (source.height - edge) // 2)
    out.alpha_composite(scaled, offset)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="replace the four production icon sets")
    args = parser.parse_args()
    destination = TEXTURES if args.apply else Path("/tmp/barkan-maintenance-icons-preview")
    destination.mkdir(parents=True, exist_ok=True)

    for name in NAMES:
        for state in STATES:
            src = TEXTURES / f"{name}{state}.png"
            if not src.is_file():
                raise SystemExit(f"missing source icon: {src}")
            out = destination / src.name
            resize_centered(Image.open(src).convert("RGBA")).save(out)
            bbox = Image.open(out).getchannel("A").getbbox()
            print(f"{out.name}: alpha bbox={bbox}")


if __name__ == "__main__":
    main()
