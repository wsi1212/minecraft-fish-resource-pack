#!/usr/bin/env python3
"""날씨 앰비언스 음원 생성 — assets/barkan/sounds/weather/*.ogg

절차적 생성(ffmpeg 노이즈 셰이핑)이다. 저작권 걱정이 없고, 마음에 안 들면
필터만 고쳐 다시 뽑으면 된다. ★생성물을 손으로 고치지 말고 이 스크립트를 고칠 것.

## 규격을 이렇게 정한 이유
* **길이 8초 고정** — 플러그인이 `AMBIENT_PERIOD_TICKS`(155틱=7.75초)마다 재생을
  다시 걸어 끊김 없이 이어붙인다. 8초 파일 + 7.75초 주기 = 0.25초 겹침이라 빈틈이 없다.
  (구 코드는 24틱=1.2초마다 19초 파일을 재생해 소리가 겹겹이 쌓이는 버그였다.)
* **양끝 0.25초 페이드** — 겹치는 구간이 크로스페이드가 되어 이음선이 안 들린다.
* **스테레오 44.1kHz vorbis** — 기존 sandstorm.ogg 규격과 동일. 마인크래프트는 스테레오
  파일을 거리감쇠 없이 재생하므로 넓게 깔리는 날씨 앰비언스에 맞다.
  (BGM 스피커처럼 위치를 갖는 소리는 모노여야 한다 — 그건 다른 시스템이다.)

사용: python3 tools/gen_weather_sounds.py [이름 ...]     (인자 없으면 전부)
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets", "barkan", "sounds", "weather")
DUR = 8.0
FADE = 0.25
SR = 44100

# anoisesrc color: white(균등) / pink(-3dB/oct) / brown(-6dB/oct, 저역 우세)
#
# 각 항목: (색, 필터체인, **목표 LUFS**)
# ★게인을 손으로 적지 않는다 — 목표 음량만 선언하고, 스크립트가 렌더 → 측정(ebur128)
#   → 차이만큼 보정 후 다시 렌더한다. 처음엔 고정 게인을 손으로 맞췄는데 실측해보니
#   비가 -13.8 LUFS 로 태풍(-18.2)보다 4dB 크게 나왔다(사다리가 뒤집힘). 필터를 조금만
#   고쳐도 음량이 딸려 움직이므로, 손으로 맞추는 방식은 언젠가 반드시 어긋난다.
#
# 음량 사다리(의도): 태풍 > 모래돌풍 > 천둥 > 눈보라 > 모래바람 > 약한바람 > 안개
LUFS = {
    "typhoon": -20.0,        # 가장 위협적
    "sandstorm_gust": -21.0,
    "thunder": -22.0,
    "blizzard": -23.0,
    "sandstorm": -25.0,
    "wind_light": -32.0,     # 배경으로 깔리는 정도
    "fog": -34.0,            # 있는지 모를 정도
}

SPECS = {
    # 천둥: 저역 우르릉. 아주 느린 트레몰로로 멀리서 굴러오는 느낌.
    "thunder": ("brown", "lowpass=f=190,tremolo=f=0.32:d=0.75"),

    # 눈보라: 비보다 건조하고 날카로운 바람 + 불규칙한 돌풍.
    "blizzard": ("pink", "highpass=f=260,lowpass=f=4200,tremolo=f=0.55:d=0.55"),

    # 안개: 거의 안 들리는 저역 드론.
    "fog": ("brown", "lowpass=f=320,tremolo=f=0.18:d=0.35"),

    # 태풍: 저역 압력 + 광대역 바람 + 강한 돌풍.
    "typhoon": ("pink", "highpass=f=90,lowpass=f=5200,tremolo=f=0.42:d=0.80"),

    # 약한 바람: 부드럽게.
    "wind_light": ("pink", "highpass=f=200,lowpass=f=2600,tremolo=f=0.30:d=0.40"),

    # 모래바람: 알갱이가 섞인 건조한 바람.
    "sandstorm": ("pink", "highpass=f=320,lowpass=f=6000,tremolo=f=0.70:d=0.45"),

    # ★모래바람 돌풍: sandstorm 과 반드시 달라야 한다 — 예전엔 두 파일이 sha1 까지
    #   같은 복사본이었다. 더 세게, 더 낮게, 한 번 훅 몰아치는 느낌으로 구분한다.
    "sandstorm_gust": ("brown", "highpass=f=150,lowpass=f=3800,tremolo=f=0.22:d=0.9"),
}


def gen(name):
    """ffmpeg 로 셰이핑한 wav 를 oggenc 로 vorbis 로 굽는다.

    ★homebrew ffmpeg 에는 libvorbis 인코더가 없다("Unknown encoder 'libvorbis'").
      ffmpeg 내장 vorbis 는 experimental 이라 품질이 떨어진다 → BGM 작업과 같이
      vorbis-tools 의 oggenc 를 쓴다.
    """
    color, chain = SPECS[name]
    dst = os.path.join(OUT, f"{name}.ogg")
    wav = os.path.join(tempfile.gettempdir(), f"weather-{name}.wav")
    fade = f"afade=t=in:st=0:d={FADE},afade=t=out:st={DUR - FADE}:d={FADE}"

    def render(gain_db):
        af = (f"{chain},{fade},volume={gain_db}dB,"
              f"aformat=sample_fmts=s16:sample_rates={SR}:channel_layouts=stereo")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            # ★seed 를 고정해 재실행에도 같은 바이트가 나오게 한다(팩 sha1 안정 → 헛된 재다운로드 방지).
            #   파이썬 hash() 는 문자열에 대해 실행마다 값이 바뀌므로(PYTHONHASHSEED) 쓰면 안 된다.
            "-f", "lavfi", "-i",
            f"anoisesrc=color={color}:sample_rate={SR}:amplitude=0.9:duration={DUR}"
            f":seed={zlib.crc32(name.encode()) % 100000}",
            "-af", af, "-ac", "2", wav,
        ], check=True)

    render(0)                                   # 1패스: 무보정으로 렌더해 실측
    measured = measure_lufs(wav)
    render(round(LUFS[name] - measured, 2))      # 2패스: 목표까지의 차이만큼만 올리거나 내린다
    final = measure_lufs(wav)
    subprocess.run(["oggenc", "-Q", "-q", "4", "-o", dst, wav], check=True)
    os.remove(wav)
    return dst, final


def measure_lufs(path):
    """ebur128 통합 라우드니스(I) 를 읽는다."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    vals = re.findall(r"^\s+I:\s+(-?\d+\.\d+)\s+LUFS", out, re.M)
    if not vals:
        raise RuntimeError(f"라우드니스 측정 실패: {path}")
    return float(vals[-1])


def main():
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg 가 없다: brew install ffmpeg")
    os.makedirs(OUT, exist_ok=True)
    want = sys.argv[1:] or sorted(SPECS)
    bad = [w for w in want if w not in SPECS]
    if bad:
        sys.exit(f"모르는 이름: {bad}\n가능: {sorted(SPECS)}")
    bad_lufs = []
    for name in sorted(want, key=lambda n: LUFS[n]):
        p, final = gen(name)
        off = final - LUFS[name]
        flag = "" if abs(off) <= 1.0 else f"  ⚠️ 목표에서 {off:+.1f}"
        if abs(off) > 1.0:
            bad_lufs.append(name)
        print(f"  {name:16s} {os.path.getsize(p):>7d}b  {final:6.1f} LUFS "
              f"(목표 {LUFS[name]:.0f}){flag}")
    print(f"\n{len(want)}개 생성 · 길이 {DUR}s · 양끝 {FADE}s 페이드 · stereo {SR}Hz vorbis")
    print("★플러그인의 AMBIENT_PERIOD_TICKS 와 길이가 맞아야 한다 (155틱 = 7.75s)")
    if bad_lufs:
        sys.exit(f"❌ 목표 음량에서 1 LUFS 이상 벗어남: {bad_lufs}")


if __name__ == "__main__":
    main()
