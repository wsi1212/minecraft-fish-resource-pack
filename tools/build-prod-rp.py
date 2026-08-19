"""Build the deterministic, production-sized resource pack.

The source tree stays untouched. GitHub Actions and the local prod deployer
both use this builder so mobile releases and Mac releases have the same pack
contents and SHA1 semantics.
"""
import io
import os
import zipfile
from pathlib import Path

from PIL import Image

RP = Path(os.environ.get("RP_ROOT", Path.cwd())).resolve()
EXTRA = Path(os.environ.get("RP_EXTRA", "")) if os.environ.get("RP_EXTRA") else None
OUT = Path(os.environ.get("OUT", "/tmp/barkan-resourcepack-slim.zip"))
JUNK = (".bak", "backup", "_prepad", "pf_reference", ".DS_Store", ".codex-backup")


def gather(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(part in JUNK or any(j in part for j in JUNK) for part in rel.split("/")):
            continue
        yield rel, p


files = {}
for top in ("assets", "pack.mcmeta", "pack.png"):
    src = RP / top
    if src.is_dir():
        for rel, path in gather(src):
            files[f"{top}/{rel}"] = path
    elif src.is_file():
        files[top] = src

if EXTRA and EXTRA.is_dir():
    for rel, path in gather(EXTRA):
        files.setdefault(rel, path)

OUT.parent.mkdir(parents=True, exist_ok=True)
png_before = png_after = 0
epoch = (1980, 1, 1, 0, 0, 0)

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name in sorted(files):
        data = files[name].read_bytes()
        if name.endswith(".png"):
            png_before += len(data)
            try:
                image = Image.open(io.BytesIO(data))
                if (
                    name.startswith("assets/minecraft/textures/item/")
                    and f"{name}.mcmeta" not in files
                    and max(image.size) > 128
                ):
                    ratio = 128 / max(image.size)
                    image = image.resize(
                        (
                            max(1, round(image.width * ratio)),
                            max(1, round(image.height * ratio)),
                        ),
                        Image.Resampling.LANCZOS,
                    )
                buf = io.BytesIO()
                image.save(buf, "PNG", optimize=True)
                if buf.tell() < len(data):
                    data = buf.getvalue()
            except Exception:
                pass
            png_after += len(data)
        info = zipfile.ZipInfo(name, date_time=epoch)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        z.writestr(info, data)

print(f"entries={len(files)}")
print(f"png={png_before}->{png_after}")
print(f"zip={OUT.stat().st_size}")
