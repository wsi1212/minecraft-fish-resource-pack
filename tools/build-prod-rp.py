"""Build the deterministic, production-sized resource pack.

The source tree stays untouched. GitHub Actions and the local prod deployer
both use this builder so mobile releases and Mac releases have the same pack
contents and SHA1 semantics.
"""
import io
import json
import os
import zipfile
from pathlib import Path

from PIL import Image

RP = Path(os.environ.get("RP_ROOT", Path.cwd())).resolve()
# 서버에만 있고 소스에 없던 파일들(누군가 박스에서 직접 넣은 것)을 같이 굽는다.
# 맥 배포기가 쓰던 기본 경로를 그대로 둔다 — 없으면 무시된다.
EXTRA = Path(os.environ.get("RP_EXTRA") or Path.home() / "development/barkan-rp-extra")
OUT = Path(os.environ.get("OUT", "/tmp/barkan-resourcepack-slim.zip"))
JUNK = (".bak", "backup", "_prepad", "pf_reference", ".DS_Store", ".codex-backup")

# 아이템 텍스처 해상도 상한 (2026-09-03).
#   대부분의 아이콘은 인벤 슬롯 16px 로만 그려진다 — 거기에 128px 을 실어 보내면
#   16px 로 축소된 결과가 64px 짜리와 화면상 구분되지 않는데 용량만 4배다.
#   팩이 112MB 까지 커지면서 느린 회선 유저가 다 받지 못하고 튕겼기에(GrimAC 60초
#   트랜잭션 타임아웃) 슬롯 전용 아이콘만 64px 로 내린다.
#   ★크게 그려지는 아이콘(oversized_in_gui, 물고기·스킬 노드 등)은 128px 을 유지한다.
SLOT_MAX = 64
BIG_MAX = 128
# 메뉴 아트는 GUI 에서 크게 렌더링된다 — 아이템 정의에 oversized_in_gui 도 gui.scale 도
# 없어서 위 자동 판정에 걸리지 않으므로 이름으로 예외를 둔다(맥 배포기에 있던 규칙).
MENU_ART_PREFIX = "assets/minecraft/textures/item/barkan_icon/ui_menu_"
MENU_ART_MAX = 256


def gather(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(part in JUNK or any(j in part for j in JUNK) for part in rel.split("/")):
            continue
        yield rel, p


def _model_refs(node, out):
    """아이템 정의 안에 흩어진 model 참조를 모은다(조건부/범위 모델도 있다)."""
    if isinstance(node, dict):
        if isinstance(node.get("model"), str):
            out.add(node["model"])
        for v in node.values():
            _model_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            _model_refs(v, out)


def _ref_to_path(ref: str, kind: str, ext: str) -> Path:
    ns, _, rel = ref.partition(":")
    if not rel:
        ns, rel = "minecraft", ns
    return RP / "assets" / ns / kind / (rel + ext)


def big_textures() -> set:
    """`oversized_in_gui` 로 슬롯 밖까지 크게 그려지는 아이템이 쓰는 텍스처 경로(zip 내 이름)."""
    keep = set()
    for items_dir in RP.glob("assets/*/items"):
        for jf in items_dir.rglob("*.json"):
            try:
                raw = jf.read_text(encoding="utf-8")
            except Exception:
                continue
            if "oversized_in_gui" not in raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            refs = set()
            _model_refs(data, refs)
            for ref in refs:
                mp = _ref_to_path(ref, "models", ".json")
                try:
                    model = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:
                    continue
                for tex in (model.get("textures") or {}).values():
                    if isinstance(tex, str):
                        tp = _ref_to_path(tex, "textures", ".png")
                        try:
                            keep.add(tp.relative_to(RP).as_posix())
                        except ValueError:
                            pass
    return keep


BIG = big_textures()

# ★소스 폴더를 잘못 잡으면 «항목 2개짜리 팩»이 조용히 만들어진다(2026-09-03 실측:
#   RP_ROOT 없이 스크립트 폴더에서 돌렸다). 여기서 크게 실패시켜 다음 단계로 못 가게 한다.
if not (RP / "pack.mcmeta").is_file():
    raise SystemExit(
        f"리소스팩 소스가 아니다: {RP}\n"
        "  RP_ROOT 로 barkan-resourcepack 경로를 넘기거나 그 폴더에서 실행할 것."
    )

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
                if name.startswith(MENU_ART_PREFIX):
                    cap = MENU_ART_MAX
                elif name in BIG:
                    cap = BIG_MAX
                else:
                    cap = SLOT_MAX
                if (
                    name.startswith("assets/minecraft/textures/item/")
                    and f"{name}.mcmeta" not in files
                    and max(image.size) > cap
                ):
                    ratio = cap / max(image.size)
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
print(f"big_textures={len(BIG)} (128px 유지) · 나머지 아이템 텍스처 상한={SLOT_MAX}px")
print(f"png={png_before}->{png_after}")
print(f"zip={OUT.stat().st_size}")
