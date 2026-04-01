#!/bin/bash
# ===== 바르칸 열도 리소스팩 배포 자동화 =====
# 사용법: ./deploy.sh
# 1. ZIP 생성 (로컬 + 배포용)
# 2. GitHub 릴리스 업로드
# 3. SHA1 갱신 → server.properties 업데이트
# 4. Git 커밋+푸시

set -e

# 경로 설정
PACK_SRC="$HOME/Downloads/barkan-resourcepack"
LOCAL_ZIP="$HOME/Library/Application Support/minecraft/resourcepacks/barkan-resourcepack.zip"
DEPLOY_ZIP="/tmp/barkan-resourcepack.zip"
GIT_REPO="$HOME/New DeskTop/develop/minecraft-fish-resource-pack"
SERVER_PROPS="$HOME/Library/Application Support/feather/player-server/servers/07de2d81-991a-47e2-b62d-06c0d1b5150a/server.properties"
GITHUB_REPO="wsi1212/minecraft-fish-resource-pack"

echo "===== 바르칸 리소스팩 배포 ====="

# 1. ZIP 생성
echo "[1/5] ZIP 생성..."
cd "$PACK_SRC"
rm -f "$LOCAL_ZIP" "$DEPLOY_ZIP"
zip -r "$LOCAL_ZIP" . -x ".*" -x "deploy.sh"
cp "$LOCAL_ZIP" "$DEPLOY_ZIP"
echo "  ✓ 로컬: $LOCAL_ZIP"
echo "  ✓ 배포: $DEPLOY_ZIP"

# 2. Git 동기화 + 커밋
echo "[2/5] Git 동기화..."
rsync -av --delete --exclude='.git' --exclude='deploy.sh' "$PACK_SRC/" "$GIT_REPO/"
cd "$GIT_REPO"
git add -A
if git diff --cached --quiet; then
    echo "  ✓ 변경 없음 (커밋 스킵)"
else
    git commit -m "update resource pack $(date +%Y-%m-%d)"
    git push origin main
    echo "  ✓ Git 푸시 완료"
fi

# 3. GitHub 릴리스 (기존 latest 삭제 후 재생성)
echo "[3/5] GitHub 릴리스..."
gh release delete latest --repo "$GITHUB_REPO" --yes 2>/dev/null || true
gh release create latest "$DEPLOY_ZIP" \
    --repo "$GITHUB_REPO" \
    --title "Latest Resource Pack" \
    --notes "자동 배포 $(date +%Y-%m-%d_%H:%M)" \
    --latest
DOWNLOAD_URL="https://github.com/$GITHUB_REPO/releases/download/latest/barkan-resourcepack.zip"
echo "  ✓ URL: $DOWNLOAD_URL"

# 4. SHA1 갱신
echo "[4/5] SHA1 갱신..."
SHA1=$(shasum "$DEPLOY_ZIP" | awk '{print $1}')
echo "  SHA1: $SHA1"

# server.properties 업데이트
sed -i '' "s|^resource-pack=.*|resource-pack=$DOWNLOAD_URL|" "$SERVER_PROPS"
sed -i '' "s|^resource-pack-sha1=.*|resource-pack-sha1=$SHA1|" "$SERVER_PROPS"
echo "  ✓ server.properties 업데이트 완료"

# 5. 확인
echo "[5/5] 완료!"
echo ""
echo "  리소스팩 URL: $DOWNLOAD_URL"
echo "  SHA1: $SHA1"
echo "  require-resource-pack: $(grep 'require-resource-pack' "$SERVER_PROPS" | cut -d= -f2)"
echo ""
echo "  → 서버 재시작하면 접속자에게 자동 적용됩니다."
echo "  → 로컬 테스트: F3+T로 리소스팩 리로드"

rm -f "$DEPLOY_ZIP"
