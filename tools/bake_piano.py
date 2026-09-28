#!/usr/bin/env python3
"""그랜드 피아노 «몸통» 굽기 — block_display 조각 수백 개를 ItemDisplay 몇 개로.

왜: 피아노 1대 = block_display 523개(조각 519 + 루트 4). 엔티티 추적 비용은 «엔티티 × 근처 플레이어»라
    건반이 아닌 몸통 조각을 회전이 같은 것끼리 한 모델로 굽는다(짚라인 밧줄·도개교 발판과 같은 발상).

무엇을 굽나:
  - 건반 후보는 절대 안 굽는다. 업스트림 indexPianoKeys 가 «quartz_block & ty≈1.0899» 52개,
    «polished_blackstone_slab & ty≈1.1384» 36개를 정확히 요구한다(흰 후보 53개 중 맨 왼쪽 1개는
    업스트림이 버리는 여분) — 후보 판정은 업스트림과 같은 식을 쓴다.
  - 나머지를 회전으로 묶는다. 그룹 회전 R_g 에 대해 R_gᵀ·R_i 가 «부호 있는 치환»(90° 배수)이면
    같은 그룹이다 → 그룹 프레임에서 조각이 축정렬 상자라 손실 없이 구워진다.
  - MIN_GROUP(10)개 미만 그룹은 굽지 않고 block_display 로 남긴다(엔티티 절감이 작고 모델만 는다).

좌표계(런타임과의 약속 — kr.barkan.companion.PianoBake 가 이 행렬을 그대로 쓴다):
  조각 = 루트(피아노 origin − 0.5) 에서 world = A_i·x + t_i  (x ∈ [0,1]³ 블록 좌표, 회전 0 기준)
  그룹 프레임 u = R_gᵀ·p. 모델 좌표 q = 8 + 16·K·(u − c_g)  (K = 모델 배율, c_g = 그룹 상자 중심)
  ItemDisplay 렌더 = M · Ry(180°) · (q/16 − ½)   ← 바닐라 ItemDisplayRenderer 가 Y 180° 를 먼저 돈다
  ⇒ M = [ (1/K)·R_g·diag(−1,1,−1) | R_g·c_g ]  (행 우선 4×4, 피아노 회전 0, 루트 기준)
  피아노 회전 r 은 런타임이 업스트림 rotateModelCommand 와 같은 행 섞기(Q_r·M)로 덧씌운다.

산출물(매번 전부 다시 쓴다 — 손편집 금지. 이 폴더들은 이 스크립트가 «소유»한다):
  assets/barkan/models/piano/grand_<그룹>.json
  assets/barkan/items/piano/grand_<그룹>.json
  assets/barkan/textures/block/piano/<바닐라이름>.png   (1.21.11 클라 jar 에서 벤더링)
  <barkan-chess>/tools/piano-bake.json                  (런타임 디스크립터: 몸통 행렬 + 구운 조각 목록 + mcfunction sha1)
미리보기(검산): --preview <폴더> → 원본 vs 구운 결과 위·앞·옆 PNG + 꼭짓점 오차.

사용: python3 tools/bake_piano.py [--jar 피아노jar] [--client 1.21.11.jar] [--descriptor 경로] [--preview 폴더]
"""
import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
DEFAULT_JAR = os.path.join(HOME, "development/barkan-chess/upstream/BarkanPiano-1.20.0.jar")
DEFAULT_CLIENT = os.path.join(HOME, "Library/Application Support/minecraft/versions/1.21.11/1.21.11.jar")
DEFAULT_DESC = os.path.join(HOME, "development/barkan-chess/tools/piano-bake.json")

MODEL_DIR = os.path.join(ROOT, "assets/barkan/models/piano")
ITEM_DIR = os.path.join(ROOT, "assets/barkan/items/piano")
TEX_DIR = os.path.join(ROOT, "assets/barkan/textures/block/piano")
TEX_NS = "barkan:block/piano/"
MODEL_NS = "barkan:piano/"

MIN_GROUP = 10
K = 0.5                      # 모델 1블록 = 8유닛 → [-16,32] 안에 6블록까지 들어간다
PERM_TOL = 2e-3              # R_gᵀR_i 가 치환행렬에서 이만큼까지 벗어나도 같은 그룹
WHITE_Y, BLACK_Y, KEY_TOL = 1.0899, 1.1384, 0.08   # 업스트림 indexPianoKeys 와 같아야 한다

PASSENGER = re.compile(r'\{id:"minecraft:block_display",block_state:\{Name:"([^"]+)",Properties:\{([^}]*)\}\},'
                       r'transformation:\[([^\]]+)\]\}')

DIRS = {"down": (0, -1, 0), "up": (0, 1, 0), "north": (0, 0, -1),
        "south": (0, 0, 1), "west": (-1, 0, 0), "east": (1, 0, 0)}
# 면의 기본(rotation 0) 텍스처 축: (+u 방향, +v 방향). 바닐라 자동 UV 식과 같은 규약.
FACE_UV_AXES = {"down": ((1, 0, 0), (0, 0, -1)), "up": ((1, 0, 0), (0, 0, 1)),
                "north": ((-1, 0, 0), (0, -1, 0)), "south": ((1, 0, 0), (0, -1, 0)),
                "west": ((0, 0, 1), (0, -1, 0)), "east": ((0, 0, -1), (0, -1, 0))}


# ---------------------------------------------------------------- 선형대수 (3×3 은 행 우선 리스트)
def mmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mvec(a, v):
    return tuple(sum(a[i][k] * v[k] for k in range(3)) for i in range(3))


def transpose(a):
    return [[a[j][i] for j in range(3)] for i in range(3)]


def rot_x(deg):
    c, s = round(math.cos(math.radians(deg))), round(math.sin(math.radians(deg)))
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def rot_y(deg):
    c, s = round(math.cos(math.radians(deg))), round(math.sin(math.radians(deg)))
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def orthonormal(R):
    """열 Gram-Schmidt — mcfunction 4자리 반올림으로 살짝 어긋난 회전을 그룹 프레임으로 쓰기 전에 바로잡는다."""
    c = [[R[r][j] for r in range(3)] for j in range(3)]
    n = lambda v: [x / math.sqrt(sum(y * y for y in v)) for x in v]
    c0 = n(c[0])
    d = sum(c0[i] * c[1][i] for i in range(3))
    c1 = n([c[1][i] - d * c0[i] for i in range(3)])
    c2 = [c0[1] * c1[2] - c0[2] * c1[1], c0[2] * c1[0] - c0[0] * c1[2], c0[0] * c1[1] - c0[1] * c1[0]]
    return [[c0[r], c1[r], c2[r]] for r in range(3)]


def as_perm(m, tol):
    """m 이 부호 있는 치환행렬에 tol 이내로 가까우면 그 정수 행렬, 아니면 None."""
    out = []
    for row in m:
        r = [0, 0, 0]
        big = [j for j in range(3) if abs(abs(row[j]) - 1) <= tol]
        if len(big) != 1 or any(abs(row[j]) > tol for j in range(3) if j != big[0]):
            return None
        r[big[0]] = 1 if row[big[0]] > 0 else -1
        out.append(r)
    return out


def decompose(v):
    """행 우선 4×4 → (R 3×3, 열별 스케일 s, t). A = R·diag(s)."""
    a = [[v[r * 4 + c] for c in range(3)] for r in range(3)]
    s = [math.sqrt(sum(a[r][c] ** 2 for r in range(3))) for c in range(3)]
    R = [[a[r][c] / s[c] for c in range(3)] for r in range(3)]
    ortho = max(abs(sum(R[r][i] * R[r][j] for r in range(3)) - (i == j)) for i in range(3) for j in range(3))
    det = (R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1]) - R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0])
           + R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0]))
    if ortho > 0.01 or det < 0 or v[12:16] != [0, 0, 0, 1]:
        raise SystemExit(f"❌ 회전·양의 스케일로 분해되지 않는 변환(전단/거울): {v}")
    return R, s, (v[3], v[7], v[11])


def apply4(v, p):
    return (v[0] * p[0] + v[1] * p[1] + v[2] * p[2] + v[3],
            v[4] * p[0] + v[5] * p[1] + v[6] * p[2] + v[7],
            v[8] * p[0] + v[9] * p[1] + v[10] * p[2] + v[11])


# ---------------------------------------------------------------- 1) mcfunction
def load_pieces(jar):
    pieces, sha = [], {}
    with zipfile.ZipFile(jar) as z:
        for fi in range(1, 5):
            name = f"models/grand-piano-1013-{fi}.mcfunction"
            raw = z.read(name)
            sha[os.path.basename(name)] = hashlib.sha1(raw).hexdigest()
            text = raw.decode("utf-8-sig")
            if not text.startswith("summon block_display ~-0.5 ~-0.5 ~-0.5 {Passengers:["):
                raise SystemExit(f"❌ {name}: 루트 형식이 예상과 다르다(루트 = origin−0.5 전제)")
            found = PASSENGER.findall(text)
            if len(found) != text.count('id:"minecraft:block_display"'):
                raise SystemExit(f"❌ {name}: 패신저 파싱 누락 ({len(found)})")
            for pi, (bname, props, tr) in enumerate(found):
                v = [float(x.rstrip("f")) for x in tr.split(",")]
                pr = props.replace('"', "").replace(":", "=")
                state = bname + (f"[{pr}]" if pr else "")
                ty = v[7]
                key = ((bname == "minecraft:quartz_block" and abs(ty - WHITE_Y) < KEY_TOL) or
                       (bname == "minecraft:polished_blackstone_slab" and abs(ty - BLACK_Y) < KEY_TOL))
                pieces.append(dict(file=fi, index=pi, name=bname, props=dict(
                    kv.split("=") for kv in pr.split(",") if kv), state=state, m=v, key=key))
    return pieces, sha


# ---------------------------------------------------------------- 2) 바닐라 블록 모델
class Vanilla:
    def __init__(self, client_jar):
        self.z = zipfile.ZipFile(client_jar)

    def read(self, path):
        return json.loads(self.z.read(path))

    def model(self, mid):
        mid = mid.removeprefix("minecraft:")
        tex, elements = {}, None
        while mid:
            d = self.read(f"assets/minecraft/models/{mid}.json")
            for k, val in d.get("textures", {}).items():
                tex.setdefault(k, val)
            if elements is None and "elements" in d:
                elements = d["elements"]
            mid = d.get("parent", "").removeprefix("minecraft:")
        return elements or [], tex

    def variant(self, name, props):
        bs = self.read(f"assets/minecraft/blockstates/{name.removeprefix('minecraft:')}.json")
        for cond, var in bs["variants"].items():
            want = dict(kv.split("=") for kv in cond.split(",") if kv)
            if all(props.get(k) == val for k, val in want.items()):
                # 가중 목록(검은 콘크리트 가루)은 첫 항목 — 무늬 없는 단색이라 차이가 안 보인다
                return var[0] if isinstance(var, list) else var
        raise SystemExit(f"❌ blockstate 변형을 못 찾음: {name} {props}")

    @staticmethod
    def resolve(tex, ref):
        seen = 0
        while ref.startswith("#"):
            ref = tex[ref[1:]]
            seen += 1
            if seen > 10:
                raise SystemExit("❌ 텍스처 참조 순환")
        return ref.removeprefix("minecraft:")


def auto_uv(face, f, t):
    return {"down": [f[0], 16 - t[2], t[0], 16 - f[2]], "up": [f[0], f[2], t[0], t[2]],
            "north": [16 - t[0], 16 - t[1], 16 - f[0], 16 - f[1]], "south": [f[0], 16 - t[1], t[0], 16 - f[1]],
            "west": [f[2], 16 - t[1], t[2], 16 - f[1]], "east": [16 - t[2], 16 - t[1], 16 - f[2], 16 - f[1]]}[face]


def tex_axes(face, rot):
    """면 + face rotation(시계방향) → 텍스처 (+u, +v) 의 3D 방향."""
    U, V = FACE_UV_AXES[face]
    neg = lambda a: tuple(-x for x in a)
    return {0: (U, V), 90: (V, neg(U)), 180: (neg(U), neg(V)), 270: (neg(V), U)}[rot % 360]


def dir_name(v):
    for n, d in DIRS.items():
        if tuple(d) == tuple(v):
            return n
    raise SystemExit(f"❌ 축정렬이 아닌 면 방향: {v}")


def piece_parts(vanilla, p):
    """조각 → [(블록좌표 from/to 8꼭짓점 생성기, 면 목록)] — 블록상태 회전까지 반영한 «블록 단위» 기하."""
    var = vanilla.variant(p["name"], p["props"])
    if var.get("uvlock"):
        raise SystemExit(f"❌ uvlock 변형은 미지원: {p['state']}")
    B = mmul(rot_y(-var.get("y", 0)), rot_x(-var.get("x", 0)))   # 바닐라: rotateYXZ(-y, -x, 0)
    elements, tex = vanilla.model(var["model"])
    parts = []
    for e in elements:
        if e.get("rotation") and e["rotation"].get("angle", 0):
            return None           # 요소 회전이 있는 블록(식물 X자 등)은 굽지 않는다
        f, t = e["from"], e["to"]
        corners = []
        for ix in (0, 1):
            for iy in (0, 1):
                for iz in (0, 1):
                    q = ((f[0] if ix == 0 else t[0]) / 16 - .5, (f[1] if iy == 0 else t[1]) / 16 - .5,
                         (f[2] if iz == 0 else t[2]) / 16 - .5)
                    r = mvec(B, q)
                    corners.append((r[0] + .5, r[1] + .5, r[2] + .5))
        faces = []
        for fname, fd in e.get("faces", {}).items():
            if "tintindex" in fd:
                return None
            faces.append(dict(dir=fname, uv=fd.get("uv") or auto_uv(fname, f, t), rot=fd.get("rotation", 0),
                              tex=Vanilla.resolve(tex, fd["texture"])))
        parts.append((corners, faces, B))
    return parts


# ---------------------------------------------------------------- 3) 그룹 나누기
def group_pieces(pieces):
    groups = []   # dict(R=..., members=[(piece, P)])
    for p in pieces:
        if p["key"]:
            continue
        R, s, t = decompose(p["m"])
        p["R"], p["s"], p["t"] = R, s, t
        if as_perm(R, PERM_TOL) is not None:           # 축정렬 그룹은 늘 단위행렬 프레임
            target = next((g for g in groups if g["label"] == "axis"), None)
            if target is None:
                target = dict(label="axis", R=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], members=[])
                groups.insert(0, target)
            target["members"].append((p, as_perm(R, PERM_TOL)))
            continue
        for g in groups:
            if g["label"] == "axis":
                continue
            P = as_perm(mmul(transpose(g["R"]), R), PERM_TOL)
            if P is not None:
                g["members"].append((p, P))
                break
        else:
            groups.append(dict(label=None, R=orthonormal(R), members=[(p, [[1, 0, 0], [0, 1, 0], [0, 0, 1]])]))
    baked = [g for g in groups if len(g["members"]) >= MIN_GROUP]
    baked.sort(key=lambda g: (g["label"] != "axis", -len(g["members"])))
    n = 0
    for g in baked:
        if g["label"] is None:
            n += 1
            g["label"] = f"r{n}"
    kept = [m[0] for g in groups if g not in baked for m in g["members"]]
    return baked, kept


# ---------------------------------------------------------------- 4) 모델 굽기
def bake_group(vanilla, g, textures_used):
    Rg = g["R"]
    RgT = transpose(Rg)
    boxes = []
    skipped = []
    for p, P in g["members"]:
        parts = piece_parts(vanilla, p)
        if parts is None:
            skipped.append(p)
            continue
        for corners, faces, B in parts:
            us = [mvec(RgT, apply4(p["m"], c)) for c in corners]
            lo = [min(u[i] for u in us) for i in range(3)]
            hi = [max(u[i] for u in us) for i in range(3)]
            O = mmul(P, B)                      # 모델 면 방향 → 그룹 프레임 면 방향
            out_faces = {}
            for fc in faces:
                nd = dir_name(mvec(O, DIRS[fc["dir"]]))
                a, b = tex_axes(fc["dir"], fc["rot"])
                want = (mvec(O, a), mvec(O, b))
                rot = next(r for r in (0, 90, 180, 270)
                           if tuple(map(tuple, tex_axes(nd, r))) == tuple(map(tuple, want)))
                out_faces[nd] = dict(uv=fc["uv"], rot=rot, tex=fc["tex"])
                textures_used.add(fc["tex"])
            boxes.append((lo, hi, out_faces, p))
    lo = [min(b[0][i] for b in boxes) for i in range(3)]
    hi = [max(b[1][i] for b in boxes) for i in range(3)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    tvars, elements = {}, []
    for blo, bhi, faces, _p in boxes:
        f = [round(8 + 16 * K * (blo[i] - c[i]), 5) for i in range(3)]
        t = [round(8 + 16 * K * (bhi[i] - c[i]), 5) for i in range(3)]
        if min(f) < -16 or max(t) > 32:
            raise SystemExit(f"❌ {g['label']}: 모델 좌표가 [-16,32] 밖 ({f}..{t}) — K 를 줄이거나 섹터로 나눌 것")
        el = {"from": f, "to": t, "faces": {}}
        for nd in ("down", "up", "north", "south", "west", "east"):
            if nd not in faces:
                continue
            fd = faces[nd]
            var = tvars.setdefault(fd["tex"], fd["tex"].split("/")[-1])
            face = {"uv": [round(x, 4) for x in fd["uv"]], "texture": "#" + var}
            if fd["rot"]:
                face["rotation"] = fd["rot"]
            el["faces"][nd] = face
        elements.append(el)
    model = {"textures": {v: TEX_NS + k.split("/")[-1] for k, v in tvars.items()},
             "elements": elements}
    model["textures"]["particle"] = model["textures"][next(iter(tvars.values()))]
    # M = [ (1/K)·R_g·diag(−1,1,−1) | R_g·c ]
    L = [[Rg[r][0] * -1 / K, Rg[r][1] / K, Rg[r][2] * -1 / K] for r in range(3)]
    T = mvec(Rg, c)
    M = [L[0][0], L[0][1], L[0][2], T[0], L[1][0], L[1][1], L[1][2], T[1],
         L[2][0], L[2][1], L[2][2], T[2], 0, 0, 0, 1]
    return model, [round(x, 6) for x in M], skipped, boxes


# ---------------------------------------------------------------- 5) 미리보기 · 검산
def model_boxes_world(model, M):
    """구운 모델 JSON + 몸통 행렬 → 월드(루트 기준) 꼭짓점 8개씩. 파일에 실제로 쓴 값으로 되짚는다."""
    out = []
    for el in model["elements"]:
        f, t = el["from"], el["to"]
        cs = []
        for ix in (0, 1):
            for iy in (0, 1):
                for iz in (0, 1):
                    q = (f[0] if ix == 0 else t[0], f[1] if iy == 0 else t[1], f[2] if iz == 0 else t[2])
                    w = ((q[0] - 8) / 16 * -1, (q[1] - 8) / 16, (q[2] - 8) / 16 * -1)   # Ry(180°)·(q/16−½)
                    cs.append(apply4(M, w))
        out.append(cs)
    return out


def source_boxes_world(vanilla, p):
    parts = piece_parts(vanilla, p) or [([(ix, iy, iz) for ix in (0, 1) for iy in (0, 1) for iz in (0, 1)], [], None)]
    return [[apply4(p["m"], c) for c in corners] for corners, _f, _b in parts]


def mean_color(vanilla, tex):
    from PIL import Image
    im = Image.open(io.BytesIO(vanilla.z.read(f"assets/minecraft/textures/{tex}.png"))).convert("RGBA")
    px = [q for q in im.getdata() if q[3] > 0]
    return tuple(sum(q[i] for q in px) // len(px) for i in range(3))


def render(views_boxes, path, scale=110):
    """views_boxes: [(제목, [(꼭짓점8, rgb)])] → 위·앞·옆 3열 PNG (정사영, 화가 알고리즘)."""
    from PIL import Image, ImageDraw
    QUADS = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    # 투영: (가로축, 세로축(위=+), 깊이축(보는 쪽이 +)), 면 음영
    VIEWS = [("top (-y)", lambda p: (p[0], -p[2], p[1])), ("front (-z)", lambda p: (p[0], p[1], -p[2])),
             ("side (+x)", lambda p: (-p[2], p[1], p[0]))]
    allp = [c for _t, bl in views_boxes for cs, _c in bl for c in cs]
    W = len(VIEWS)
    rows = len(views_boxes)
    ext = []
    for _n, pj in VIEWS:
        pts = [pj(p) for p in allp]
        ext.append((min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts)))
    cw = max(int((e[1] - e[0]) * scale) + 20 for e in ext)
    ch = max(int((e[3] - e[2]) * scale) + 40 for e in ext)
    img = Image.new("RGB", (cw * W, ch * rows), (235, 235, 240))
    d = ImageDraw.Draw(img)
    for ri, (title, bl) in enumerate(views_boxes):
        for vi, (vname, pj) in enumerate(VIEWS):
            ox, oy = vi * cw + 10, ri * ch + 30
            x0, _x1, _y0, y1 = ext[vi]
            d.text((ox, ri * ch + 8), f"{title} — {vname}", fill=(20, 20, 20))
            polys = []
            for cs, rgb in bl:
                P = [pj(c) for c in cs]
                for q in QUADS:
                    pts = [P[i] for i in q]
                    depth = sum(p[2] for p in pts) / 4
                    # 면 법선의 깊이 성분으로 음영(정면일수록 밝게)
                    ax = [pts[1][k] - pts[0][k] for k in range(3)]
                    bx = [pts[3][k] - pts[0][k] for k in range(3)]
                    n = (ax[1] * bx[2] - ax[2] * bx[1], ax[2] * bx[0] - ax[0] * bx[2], ax[0] * bx[1] - ax[1] * bx[0])
                    nl = math.sqrt(sum(x * x for x in n)) or 1
                    shade = 0.55 + 0.45 * abs(n[2]) / nl
                    col = tuple(int(c * shade) for c in rgb)
                    polys.append((depth, [(ox + (p[0] - x0) * scale, oy + (y1 - p[1]) * scale) for p in pts], col))
            polys.sort(key=lambda t: t[0])
            for _dp, pts, col in polys:
                d.polygon(pts, fill=col, outline=tuple(max(0, c - 40) for c in col))
    img.save(path)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", default=DEFAULT_JAR)
    ap.add_argument("--client", default=DEFAULT_CLIENT)
    ap.add_argument("--descriptor", default=DEFAULT_DESC)
    ap.add_argument("--preview", default=None)
    a = ap.parse_args()

    pieces, sha = load_pieces(a.jar)
    vanilla = Vanilla(a.client)
    keys = [p for p in pieces if p["key"]]
    print(f"조각 {len(pieces)}개 (건반 후보 {len(keys)}: 흰 "
          f"{sum(p['name'].endswith('quartz_block') for p in keys)} / 검 "
          f"{sum(p['name'].endswith('slab') for p in keys)})")
    groups, kept = group_pieces(pieces)

    textures = set()
    produced, bodies, baked_ids, previews = set(), [], [], []
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(ITEM_DIR, exist_ok=True)
    os.makedirs(TEX_DIR, exist_ok=True)
    for g in groups:
        model, M, skipped, boxes = bake_group(vanilla, g, textures)
        kept += skipped
        name = f"grand_{g['label']}"
        with open(os.path.join(MODEL_DIR, name + ".json"), "w") as fh:
            json.dump(model, fh, separators=(",", ":"))
        with open(os.path.join(ITEM_DIR, name + ".json"), "w") as fh:
            json.dump({"model": {"type": "minecraft:model", "model": MODEL_NS + name}}, fh, separators=(",", ":"))
        produced.add(name + ".json")
        members = [m[0] for m in g["members"] if m[0] not in skipped]
        bodies.append({"id": g["label"], "item_model": MODEL_NS + name, "matrix": M,
                       "pieces": len(members), "elements": len(model["elements"])})
        baked_ids += [{"file": p["file"], "index": p["index"], "block": p["state"]} for p in members]
        previews.append((model, M, members))
        print(f"  {name:12s} 조각 {len(members):3d}  요소 {len(model['elements']):3d}"
              + (f"  (굽기 제외 {len(skipped)})" if skipped else ""))

    # 소유 폴더의 낡은 산출물 정리(예전 body_g* 125개 같은 것)
    for d in (MODEL_DIR, ITEM_DIR):
        for fn in os.listdir(d):
            if fn.endswith(".json") and fn not in produced:
                os.remove(os.path.join(d, fn))
                print(f"  - 낡은 산출물 삭제: {os.path.relpath(os.path.join(d, fn), ROOT)}")
    tex_files = set()
    for tex in sorted(textures):
        base = tex.split("/")[-1]
        with open(os.path.join(TEX_DIR, base + ".png"), "wb") as fh:
            fh.write(vanilla.z.read(f"assets/minecraft/textures/{tex}.png"))
        tex_files.add(base + ".png")
        mc = f"assets/minecraft/textures/{tex}.png.mcmeta"
        if mc in vanilla.z.namelist():
            with open(os.path.join(TEX_DIR, base + ".png.mcmeta"), "wb") as fh:
                fh.write(vanilla.z.read(mc))
            tex_files.add(base + ".png.mcmeta")
    for fn in os.listdir(TEX_DIR):
        if fn not in tex_files:
            os.remove(os.path.join(TEX_DIR, fn))

    kept_body = [p for p in kept if not p["key"]]
    desc = {
        "_note": "barkan-resourcepack/tools/bake_piano.py 가 생성 — 손편집 금지. matrix 는 행 우선, 피아노 회전 0, "
                 "루트(origin-0.5) 기준. baked 는 mcfunction(file 1..4) 의 패신저 순번(0부터).",
        "version": 1,
        "mcfunction_sha1": sha,
        "bodies": bodies,
        "baked": baked_ids,
        "expected": {"pieces": len(pieces), "keys": len(keys), "kept_body": len(kept_body),
                     "remaining_block_displays": len(keys) + len(kept_body)},
    }
    os.makedirs(os.path.dirname(a.descriptor), exist_ok=True)
    with open(a.descriptor, "w") as fh:
        json.dump(desc, fh, ensure_ascii=False, indent=1)
    total_after = len(keys) + len(kept_body) + len(bodies)
    print(f"구운 조각 {len(baked_ids)} / 남는 block_display {len(keys) + len(kept_body)}"
          f"(건반 {len(keys)} + 몸통 자투리 {len(kept_body)}) + ItemDisplay {len(bodies)}"
          f" = 엔티티 {total_after} (현재 {len(pieces) + 4})")
    print(f"텍스처 {len(textures)}장 벤더링 → {os.path.relpath(TEX_DIR, ROOT)}")
    print(f"디스크립터 → {a.descriptor}")

    # 검산: 구운 조각의 꼭짓점을 «쓴 파일»에서 되짚어 원본과 대조
    worst = 0.0
    for gi, (model, M, members) in enumerate(previews):
        gworst = 0.0
        world = model_boxes_world(model, M)
        src = [c for p in members for c in source_boxes_world(vanilla, p)]
        if len(world) != len(src):
            raise SystemExit("❌ 요소 수와 조각 수가 어긋난다")
        for wb, sb in zip(world, src):
            wlo = [min(c[i] for c in wb) for i in range(3)]
            whi = [max(c[i] for c in wb) for i in range(3)]
            # 원본 조각은 그룹 회전을 가진 «기울어진» 상자 → 같은 그룹 프레임에서 비교하려면 꼭짓점 집합을 맞춘다
            for sc in sb:
                gworst = max(gworst, min(math.dist(sc, wc) for wc in wb))
            _ = (wlo, whi)
        print(f"  검산 {bodies[gi]['id']:5s} 최대 꼭짓점 오차 {gworst:.5f} 블록")
        worst = max(worst, gworst)
    print(f"검산: 구운 꼭짓점 ↔ 원본 꼭짓점 최대 오차 {worst:.5f} 블록")
    if worst > 0.01:
        raise SystemExit("❌ 오차가 0.01 블록을 넘는다")

    if a.preview:
        os.makedirs(a.preview, exist_ok=True)
        cache = {}

        def col(p):
            parts = piece_parts(vanilla, p)
            tex = parts[0][1][0]["tex"] if parts and parts[0][1] else "block/stone"
            if tex not in cache:
                cache[tex] = mean_color(vanilla, tex)
            return cache[tex]
        orig = [(cs, col(p)) for p in pieces for cs in source_boxes_world(vanilla, p)]
        baked = [(cs, col(p)) for p in keys + kept for cs in source_boxes_world(vanilla, p)]
        for model, M, members in previews:
            for cs, p in zip(model_boxes_world(model, M), members):
                baked.append((cs, col(p)))
        render([("ORIGINAL 519 block_display", orig), (f"BAKED {len(bodies)} item_display + {len(keys) + len(kept)} block_display", baked)],
               os.path.join(a.preview, "piano_bake_compare.png"))
        only = []
        palette = [(220, 60, 60), (60, 160, 60), (60, 90, 220), (220, 160, 40), (160, 60, 200), (40, 170, 170)]
        for gi, (model, M, members) in enumerate(previews):
            for cs in model_boxes_world(model, M):
                only.append((cs, palette[gi % len(palette)]))
        render([("BAKED bodies only (color = ItemDisplay)", only)], os.path.join(a.preview, "piano_bake_groups.png"))
        print(f"미리보기 → {a.preview}/piano_bake_compare.png, piano_bake_groups.png")


if __name__ == "__main__":
    main()
