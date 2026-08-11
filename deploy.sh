#!/bin/bash
# ⛔ 이 스크립트는 폐지됐다 (2026-08-11). 실행하지 말 것.
#
# 왜: 아래 줄이 prod 를 두 번 깨뜨렸다.
#
#     gh release delete latest --repo ... --yes
#
# 릴리스 `latest` 를 통째로 지우면 **같은 릴리스에 얹힌 barkan-furniture.zip**
# (prod CraftEngine 가구팩)이 함께 날아가서 전 클라의 가구·HUD 가 미싱이 된다.
# 게다가 이 스크립트는 소스를 날것으로 zip 해서 백업 파일까지 배포본에 실었고,
# server.properties 를 dev 것만 고쳤고, 팩 다이어트(아이템 128px 상한)도 안 탔다.
#
# 또 하나: 이 스크립트는 소스를 별도 클론으로 rsync --delete 하는 2단 구조였다.
# 그래서 소스와 클론이 양방향으로 갈라졌고, 2026-08-11 낡은 클론에서 구운 팩이
# prod 로 가서 gui 텍스처 761개 + 글리프 provider 228개가 빠졌다(메뉴 전멸).
# 지금은 이 저장소가 소스 디렉터리 자체의 작업트리다 — 클론도 rsync 도 없다.
#
# ✅ 대신 이걸 쓸 것 (Skript/scripts 저장소):
#
#     ops/rp-deploy.sh <dev|prod> [--restart] [--dry-run]
#
#   새 태그로만 올리고(latest 는 안 건드림), 공개 URL sha1 을 먼저 검증하고,
#   현재 서빙본 대비 파일이 줄면 중단하는 회귀 가드가 있다.
echo "⛔ deploy.sh 는 폐지됐다. ops/rp-deploy.sh <dev|prod> 를 쓸 것." >&2
echo "   이유는 이 파일 주석 참조 (gh release delete latest 가 가구팩을 날린다)." >&2
exit 1
