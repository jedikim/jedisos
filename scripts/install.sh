#!/bin/bash
# [JS-X003] scripts/install.sh
# JediSOS 원클릭 설치 스크립트
# 사용법: curl -sSL https://raw.githubusercontent.com/jedikim/jedisos/main/scripts/install.sh | bash
#
# version: 2.0.0
# created: 2026-02-18
# modified: 2026-02-18

set -euo pipefail

JEDISOS_VERSION="${JEDISOS_VERSION:-latest}"
JEDISOS_HOME="${JEDISOS_HOME:-$HOME/.jedisos}"
COMPOSE_URL="https://raw.githubusercontent.com/jedikim/jedisos/main/docker-compose.yml"

echo ""
echo "  ╔═══════════════════════════════╗"
echo "  ║     JediSOS 설치를 시작합니다     ║"
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
    echo "   설치 후 이 스크립트를 다시 실행하세요."
    exit 1
fi

# 2. docker compose 확인
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose V2가 필요합니다."
    echo "   Docker Desktop을 최신 버전으로 업데이트해주세요."
    exit 1
fi

echo "✅ Docker 확인 완료"

# 3. 디렉토리 생성
mkdir -p "$JEDISOS_HOME/config"
cd "$JEDISOS_HOME"

# 4. docker-compose.yml 다운로드
echo "📦 설정 파일 다운로드..."
curl -sSL "$COMPOSE_URL" -o docker-compose.yml

# 5. Docker 이미지 pull + 실행
echo "🐳 Docker 이미지 다운로드... (최초 실행 시 2~5분 소요)"
docker compose pull
docker compose up -d

# 6. 헬스체크 대기
echo "⏳ JediSOS 시작 대기..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

# 7. 완료
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       ✅ JediSOS 설치 완료!            ║"
echo "  ║                                       ║"
echo "  ║  👉 http://localhost:8080 접속하세요    ║"
echo "  ║     브라우저에서 모든 설정이 가능합니다     ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""
echo "  설정 위치: $JEDISOS_HOME/"
echo "  중지:     cd $JEDISOS_HOME && docker compose down"
echo "  시작:     cd $JEDISOS_HOME && docker compose up -d"
echo "  업데이트: cd $JEDISOS_HOME && docker compose pull && docker compose up -d"
echo ""

# 8. 브라우저 자동 열기
if command -v open &> /dev/null; then
    open "http://localhost:8080"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:8080"
fi
