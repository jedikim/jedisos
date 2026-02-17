#!/bin/bash
# [JS-X003] scripts/install.sh
# JediSOS 원클릭 설치 스크립트
# 사용법: curl -sSL https://get.jedisos.com | bash
#
# version: 1.0.0
# created: 2026-02-18

set -euo pipefail

JEDISOS_VERSION="${JEDISOS_VERSION:-latest}"
JEDISOS_HOME="${JEDISOS_HOME:-$HOME/.jedisos}"
COMPOSE_URL="https://raw.githubusercontent.com/jedikim/jedisos/main/docker-compose.yml"

echo "JediSOS 설치를 시작합니다..."
echo ""

# 1. Docker 확인
if ! command -v docker &> /dev/null; then
    echo "Docker가 설치되어 있지 않습니다."
    echo ""
    echo "Docker Desktop을 먼저 설치해주세요:"
    echo "  macOS:   https://docs.docker.com/desktop/install/mac-install/"
    echo "  Windows: https://docs.docker.com/desktop/install/windows-install/"
    echo "  Linux:   https://docs.docker.com/engine/install/"
    echo ""
    echo "설치 후 이 스크립트를 다시 실행하세요."
    exit 1
fi

# 2. docker compose 확인
if ! docker compose version &> /dev/null; then
    echo "Docker Compose V2가 필요합니다."
    echo "Docker Desktop을 최신 버전으로 업데이트해주세요."
    exit 1
fi

# 3. 디렉토리 생성
mkdir -p "$JEDISOS_HOME"
cd "$JEDISOS_HOME"

# 4. docker-compose.yml 다운로드
echo "설정 파일을 다운로드합니다..."
curl -sSL "$COMPOSE_URL" -o docker-compose.yml

# 5. config 디렉토리
mkdir -p config

# 6. .env 생성 (비어있는 상태 - Setup Wizard에서 설정)
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
# JediSOS 환경변수
# 웹 UI Setup Wizard에서 자동 설정되거나 직접 편집하세요
JEDISOS_FIRST_RUN=true
OPENAI_API_KEY=
GOOGLE_API_KEY=
ENVEOF
    echo ".env 파일이 생성되었습니다."
fi

# 7. Docker 이미지 pull + 실행
echo "Docker 이미지를 다운로드합니다... (최초 1회, 약 2~5분)"
docker compose pull
docker compose up -d

# 8. 헬스체크 대기
echo "JediSOS를 시작하는 중..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

# 9. 완료
echo ""
echo "JediSOS가 설치되었습니다!"
echo ""
echo "  웹 UI:     http://localhost:8080"
echo "  설정 위치:  $JEDISOS_HOME/"
echo ""
echo "  중지:     cd $JEDISOS_HOME && docker compose down"
echo "  시작:     cd $JEDISOS_HOME && docker compose up -d"
echo "  업데이트:  cd $JEDISOS_HOME && docker compose pull && docker compose up -d"
echo ""

# 10. 브라우저 열기 (가능한 경우)
if command -v open &> /dev/null; then
    open "http://localhost:8080/setup"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:8080/setup"
fi
