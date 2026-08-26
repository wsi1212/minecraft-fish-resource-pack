#!/usr/bin/env python3
"""사이드바 시간/날씨 아이콘 글리프 생성 — 9x9 픽셀 아트 → minecraft:default 비트맵 프로바이더.

왜 유니코드가 아니라 커스텀 글리프인가:
  기존 아이콘(☀ ☂ ⚡ ❄ ≋ ☄ ✦ ≈)은 커스텀 폰트 3종에 없어서 전부 바닐라 unifont 폴백으로
  그려졌다 — 두부는 안 나지만 굵기·크기·광학 무게가 제멋대로고, ☀ 가 땡볕과 열대야에,
  ⚡ 가 뇌우와 태풍에 중복돼 색만으로 구분해야 했다. 실루엣을 직접 그리면 둘 다 해결된다.

배치: U+EA00 ~ U+EA10 (17종). 팩 전체 PUA 사용 현황을 스캔해 고른 빈 구간 —
  aurora 0xE001~E6FF · chess_grid 0xE100~E10B · skin 0xE700~E71F · gui ~0xF817 ·
  default 0xF800~F844(음수 advance). BetterHud 는 merge-default-bitmap:false 로 자기 폰트만 쓴다.

★minecraft:default 에 넣는 이유: 사이드바는 Scoreboard API 의 legacy § 문자열이라
  컴포넌트 font 를 지정할 수 없다. 그래서 barkan:gui 같은 별도 폰트로는 못 쓴다.
★프로바이더를 providers 맨 앞에 넣는다 — 이 팩은 앞이 우선순위다(그래서 aggro TTF 가 맨 앞).
★색: 글리프 자체가 컬러다. 호출부는 반드시 §f(흰색)로 출력해야 원래 색이 나온다
  (MC 는 글리프 색 × 텍스트 색으로 곱한다 — §c 를 주면 빨갛게 물든다).
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
# Bitmap font providers resolve their files below assets/<namespace>/textures/.
# Keep the generated sheet beside the other bitmap-font textures so the
# reference in minecraft:default can actually load it on the client.
SHEET = os.path.join(PACK, "assets/barkan/textures/font/weather_icons.png")
FONT  = os.path.join(PACK, "assets/minecraft/font/default.json")
START = 0xEA00

PAL = {
    '.': None,
    # 해 / 열
    'y': (255, 224, 110), 'o': (255, 168,  61), 'r': (232,  98,  42), 'R': (168,  52,  30),
    # 구름
    'w': (233, 239, 245), 'g': (168, 180, 194), 'd': (104, 120, 140), 'D': (66, 78, 94),
    # 물 / 비
    'b': (122, 214, 240), 'B': (ted := 46, 143, 196), 'n': (24,  86, 130),
    # 눈 / 얼음
    'W': (255, 255, 255), 'c': (200, 234, 247),
    # 모래
    's': (227, 192, 122), 'S': (176, 138,  69),
    # 오로라 / 마법
    'p': (232, 111, 224), 'm': (154, 107, 232), 'G': (111, 232, 168),
    # 탄가루
    'k': ( 44,  44,  48), 'K': ( 86,  86,  94), 'a': (128, 128, 138),
    # 달
    'M': (242, 236, 208), 'N': (198, 190, 158),
    # 번개
    'Y': (255, 240, 122),
}
del PAL['B']; PAL['B'] = (46, 143, 196)

# 순서 = 코드포인트 순서. 호출부(SidebarManager/WeatherManager)와 반드시 일치.
ORDER = ["낮", "저녁", "밤", "새벽",
         "맑음", "비", "뇌우", "안개", "유성우", "오로라", "만조",
         "열대야", "땡볕", "모래바람", "태풍", "눈보라", "탄광먼지"]

ART = {
# ── 시간대 ─ 해/달 실루엣을 공유하고 광선·부가요소만 바꾼다 ────────
"낮": [                # 꽉 찬 해 + 8방향 광선
 "....y....",
 ".y.....y.",
 "...ooo...",
 "..oyyyo..",
 "y.oyyyo.y",
 "..oyyyo..",
 "...ooo...",
 ".y.....y.",
 "....y...."],
"저녁": [              # 지평선에 반쯤 잠긴 해 + 노을 반사
 "....o....",
 ".o.....o.",
 "...ooo...",
 "..oyyyo..",
 ".oyyyyyo.",
 ".oyyyyyo.",
 "rrrrrrrrr",
 ".........",
 "........."],
"밤": [                # 두꺼운 초승달 + 별 2 (밤/새벽이 같은 달을 쓴다)
 "..MMM....",
 ".MMMNM..W",
 "MMMN.....",
 "MMM......",
 "MMM......",
 "MMM......",
 "MMMN...W.",
 ".MMMNM...",
 "..MMM...."],
"새벽": [              # 같은 달 + 트는 하늘
 "..MMM....",
 ".MMMNM...",
 "MMMN.....",
 "MMM......",
 "MMMN.....",
 ".MMMNM...",
 "..MMM....",
 "ooooooooo",
 "........."],
# ── 날씨 ─ 해 계열 3종은 광선 처리로만 구분한다 ──────────────────
"맑음": [              # 광선 없는 맨 해 (낮보다 광학적으로 가볍다)
 ".........",
 "...ooo...",
 "..oyyyo..",
 ".oyyyyyo.",
 ".oyyyyyo.",
 ".oyyyyyo.",
 "..oyyyo..",
 "...ooo...",
 "........."],
"땡볕": [              # 해 + 내리꽂는 직선 광선 + 달아오른 땅
 "...rrr...",
 "..ooooo..",
 ".oyyyyyo.",
 "royyyyyor",
 "royyyyyor",
 "royyyyyor",
 ".oyyyyyo.",
 "..ooooo..",
 "...rrr..."],
# ── 구름 계열 4종 ─ 구름 색 + 아래로 떨어지는 것으로 구분 ─────────
"비": [                # 흰 구름 + 물방울 3 (낙차 서로 다름)
 "...www...",
 "..wwwww..",
 ".wwwwwwg.",
 "gwwwwgggg",
 ".ggggggg.",
 "..b...b..",
 "..B.b.B..",
 "....B....",
 "........."],
"뇌우": [              # 먹구름 + 번개
 "...ddd...",
 "..ddddd..",
 ".dddddDd.",
 "ddddDDDDD",
 ".DDDDDDD.",
 "....YY...",
 "...YY....",
 "..YYYYY..",
 "....YY..."],
"탄광먼지": [          # 검은 구름 + 내려앉는 탄가루 (비와 같은 리듬)
 "...kkk...",
 "..kkkkk..",
 ".kkkKkkk.",
 "kkkkkkkkk",
 ".KKKKKKK.",
 "..a...a..",
 "..K.a.K..",
 "....K....",
 "........."],
"안개": [              # 가로 층 4겹 — 이 팩에서 유일한 순수 수평 실루엣
 ".........",
 ".wwww....",
 "....wwww.",
 ".........",
 "gggg.....",
 "....ggggg",
 ".........",
 ".dddd....",
 ".....dddd"],
# ── 나머지 ────────────────────────────────────────────────────
"유성우": [            # 대각 유성 1발 (흰 머리 → 주황 꼬리) + 별 2
 "......WWW",
 ".....WWWy",
 "....yyy..",
 "...oyy...",
 "..ooo....",
 ".ro......",
 "rr.......",
 ".........",
 ".W.....W."],
"오로라": [            # 위아래로 이어지는 커튼 3겹 (초록→보라→자홍)
 "GG..GG...",
 "GG..GG...",
 ".GG..GG..",
 ".GG..GG..",
 "..GG..GG.",
 "..mm..mm.",
 "...mm..mm",
 "...pp..pp",
 "...pp..pp"],
"만조": [              # 보름달 + 밀려오는 물결
 ".....MMM.",
 "....MMMMM",
 "....MMMMM",
 "....MMMMM",
 ".....MMM.",
 "..b...b..",
 ".bBb.bBb.",
 "BBBBBBBBB",
 ".nnnnnnn."],
"열대야": [            # 초승달 + 피어오르는 열기
 "..ooo....",
 ".oooro...",
 "ooor.....",
 "ooo......",
 "ooor.....",
 ".oooro...",
 "..ooo....",
 ".rr...rr.",
 "...rrr..."],
"모래바람": [          # 비스듬히 몰아치는 모래 + 사구
 "....ssss.",
 "..ssss...",
 "sssss....",
 "....ssss.",
 "..ssss...",
 "sss......",
 "....ss...",
 "..SSSSS..",
 ".SSSSSSS."],
"태풍": [              # 두 팔 소용돌이 + 태풍의 눈
 "..DDDD...",
 ".DDDDDDD.",
 "DDDDDDDDn",
 ".nnnnnnnn",
 "..b..b..b",
 ".b..b..b.",
 "b..b..b..",
 "..b..b...",
 ".b..b...."],
"눈보라": [            # 대칭 눈결정
 "....c....",
 ".c..W..c.",
 "..W.W.W..",
 "...WWW...",
 "cWWWWWWWc",
 "...WWW...",
 "..W.W.W..",
 ".c..W..c.",
 "....c...."],
}


def build():
    from PIL import Image
    for name in ORDER:
        art = ART[name]
        assert len(art) == 9, (name, len(art))
        for row in art:
            assert len(row) == 9, (name, row, len(row))
            for ch in row:
                assert ch in PAL, (name, ch)

    sheet = Image.new("RGBA", (9 * len(ORDER), 9), (0, 0, 0, 0))
    for i, name in enumerate(ORDER):
        for y, row in enumerate(ART[name]):
            for x, ch in enumerate(row):
                c = PAL[ch]
                if c:
                    sheet.putpixel((i * 9 + x, y), (*c, 255))
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    sheet.save(SHEET)

    patch_font()

    print(f"{SHEET}  ({sheet.width}x{sheet.height}, {len(ORDER)}글리프)")
    print(f"{FONT}  providers[0] 등록, U+{START:04X}~U+{START+len(ORDER)-1:04X}")
    for i, name in enumerate(ORDER):
        print(f"  U+{START+i:04X}  {name}")


def patch_font():
    """default.json 에 프로바이더를 <b>텍스트로</b> 끼워 넣는다 (멱등).

    ★json.load → json.dump 로 되쓰면 파일 전체가 재포맷돼(`[0, 0]` 이 3줄로 펴진다)
      같은 파일을 만지는 다른 세션의 diff 와 정면충돌한다. 실제로 한 번 그랬다.
      그래서 providers 배열 맨 앞에 블록만 삽입하고 나머지 바이트는 건드리지 않는다.
    """
    chars = "".join(chr(START + i) for i in range(len(ORDER)))
    block = ('    {\n'
             '      "type": "bitmap",\n'
             '      "file": "barkan:font/weather_icons.png",\n'
             '      "ascent": 8,\n'
             '      "height": 9,\n'
             '      "chars": ["%s"]\n'
             '    },\n' % chars)
    txt = open(FONT, encoding="utf-8").read()
    txt = re.sub(r'\s*\{[^{}]*"barkan:font/weather_icons\.png"[^{}]*\},\n?', '\n', txt, count=1)
    anchor = '"providers": [\n'
    i = txt.index(anchor) + len(anchor)
    txt = txt[:i] + block + txt[i:]
    open(FONT, "w", encoding="utf-8").write(txt)
    json.load(open(FONT, encoding="utf-8"))   # 파싱 검증 — 깨진 JSON 을 남기지 않는다


def contact_sheet(path, scale=8):
    """이름표 붙은 대조표 PNG — 배포 전 자기검수 + 사람에게 보여주기용(팩에 안 들어간다).

    ★사본을 고정하지 않는다: 아이콘을 고치면 이 함수를 다시 돌려 새로 뽑을 것.
    """
    from PIL import Image, ImageDraw, ImageFont
    src = Image.open(SHEET)
    FONT_TTF = os.path.join(PACK, "assets/barkan/font/aggro_medium.ttf")
    f_name = ImageFont.truetype(FONT_TTF, 19)
    f_hdr = ImageFont.truetype(FONT_TTF, 16)
    f_line = ImageFont.truetype(FONT_TTF, 26)

    ico = 9 * scale                       # 72
    tile_w, tile_h = ico + 56, ico + 40
    cols = 6
    rows = (len(ORDER) + cols - 1) // cols
    pad = 26
    hdr = 132
    W = pad * 2 + tile_w * cols
    H = hdr + pad + rows * tile_h
    img = Image.new("RGB", (W, H), (13, 16, 21))
    d = ImageDraw.Draw(img)

    def paste(idx, x, y, sc):
        g = src.crop((idx * 9, 0, idx * 9 + 9, 9)).resize((9 * sc, 9 * sc), Image.NEAREST)
        img.paste(g, (x, y), g)

    # 사이드바 모의 줄 (실제 순서: 시간아이콘 + 시간 + 날씨아이콘 + 날씨)
    d.text((pad, 20), "사이드바 실제 한 줄", font=f_hdr, fill=(125, 135, 148))
    demo = [(2, "밤", 10, "만조"), (0, "낮", 12, "땡볕")]
    x = pad
    for ti, tn, wi, wn in demo:
        paste(ti, x, 50, 3)
        d.text((x + 32, 52), tn, font=f_line, fill=(255, 255, 255))
        x += 32 + int(d.textlength(tn, font=f_line)) + 16
        paste(wi, x, 50, 3)
        d.text((x + 32, 52), wn, font=f_line, fill=(255, 255, 255))
        x += 32 + int(d.textlength(wn, font=f_line)) + 64

    for i, name in enumerate(ORDER):
        cx = pad + (i % cols) * tile_w
        cy = hdr + (i // cols) * tile_h
        d.rounded_rectangle([cx, cy, cx + tile_w - 10, cy + tile_h - 10],
                            radius=10, fill=(22, 26, 33), outline=(42, 49, 58))
        paste(i, cx + (tile_w - 10 - ico) // 2, cy + 14, scale)
        tw = d.textlength(name, font=f_name)
        d.text((cx + (tile_w - 10 - tw) / 2, cy + 14 + ico + 6), name,
               font=f_name, fill=(198, 206, 216))
    img.save(path)
    print("contact sheet:", path, img.size)


def preview(path, scale=14):
    """다크 사이드바 배경에 올린 확대 프리뷰 — 배포 전 자기검수용(팩에 들어가지 않는다)."""
    from PIL import Image
    cell = 9 * scale
    pad = scale
    W = (cell + pad) * len(ORDER) + pad
    H = cell + pad * 2
    img = Image.new("RGB", (W, H), (16, 19, 24))
    src = Image.open(SHEET)
    for i in range(len(ORDER)):
        g = src.crop((i * 9, 0, i * 9 + 9, 9)).resize((cell, cell), Image.NEAREST)
        bg = Image.new("RGB", (cell, cell), (16, 19, 24))
        bg.paste(g, (0, 0), g)
        img.paste(bg, (pad + i * (cell + pad), pad))
    img.save(path)
    print("preview:", path, img.size)


if __name__ == "__main__":
    build()
    if len(sys.argv) > 1:
        contact_sheet(sys.argv[1])
