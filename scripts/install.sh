#!/bin/bash
# [JS-X003] scripts/install.sh
# JediSOS 원클릭 설치 스크립트
# 사용법: curl -sSL https://raw.githubusercontent.com/jedikim/jedisos/main/scripts/install.sh | bash
#
# version: 3.0.0
# created: 2026-02-18
# modified: 2026-02-18

set -euo pipefail

JEDISOS_HOME="${JEDISOS_HOME:-$HOME/.jedisos}"
REPO_URL="https://github.com/jedikim/jedisos.git"

echo ""
echo "  ╔═══════════════════════════════╗"
echo "  ║   JediSOS 설치를 시작합니다    ║"
echo "  ╚═══════════════════════════════╝"
echo ""

# 1. Docker 확인
if ! command -v docker &> /dev/null; then
    echo "❌ Docker가 설치되어 있지 않습니다."
    echo ""
    echo "   Docker Desktop을 먼저 설치해주세요:"
    echo "   macOS:   https://docs.docker.com/desktop/install/mac-install/"
    echo "   Windows: https://docs.docker.com/desktop/install/windows-install/"
    echo "   Linux:   https://docs.docker.com/engine/install/"
    echo ""
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose V2가 필요합니다."
    echo "   Docker Desktop을 최신 버전으로 업데이트해주세요."
    exit 1
fi

echo "✅ Docker 확인 완료"

# 2. Git 확인
if ! command -v git &> /dev/null; then
    echo "❌ Git이 설치되어 있지 않습니다."
    echo "   https://git-scm.com/downloads 에서 설치해주세요."
    exit 1
fi

# 3. 소스 클론 또는 업데이트
if [ -d "$JEDISOS_HOME/.git" ]; then
    echo "📦 기존 설치 업데이트..."
    cd "$JEDISOS_HOME"
    git pull --quiet
else
    echo "📦 JediSOS 다운로드..."
    git clone --quiet "$REPO_URL" "$JEDISOS_HOME"
    cd "$JEDISOS_HOME"
fi

mkdir -p config

# 4. Docker 빌드 + 실행
echo "🐳 Docker 빌드 및 실행... (최초 실행 시 3~7분 소요)"
docker compose up -d --build

# 5. 헬스체크 대기
echo "⏳ JediSOS 시작 대기..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

# 6. 완료
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       ✅ JediSOS 설치 완료!            ║"
echo "  ║                                       ║"
echo "  ║  👉 http://localhost:8080 접속하세요    ║"
echo "  ║     브라우저에서 모든 설정이 가능합니다  ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""
echo "  중지:     cd $JEDISOS_HOME && docker compose down"
echo "  시작:     cd $JEDISOS_HOME && docker compose up -d"
echo "  업데이트: cd $JEDISOS_HOME && docker compose pull && docker compose up -d --build"
echo ""

# 7. 브라우저 자동 열기
if command -v open &> /dev/null; then
    open "http://localhost:8080"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:8080"
fi
