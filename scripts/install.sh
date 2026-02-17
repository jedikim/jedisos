#!/bin/bash
# [JS-X003] scripts/install.sh
# JediSOS one-click install script
# Usage: curl -sSL https://raw.githubusercontent.com/jedikim/jedisos/main/scripts/install.sh | bash
#
# version: 4.0.0
# created: 2026-02-18
# modified: 2026-02-18

set -euo pipefail

JEDISOS_HOME="${JEDISOS_HOME:-$HOME/.jedisos}"
REPO_URL="https://github.com/jedikim/jedisos.git"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║  JediSOS Installer               ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# 1. Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed."
    echo ""
    echo "  Please install Docker Desktop first:"
    echo "  macOS:   https://docs.docker.com/desktop/install/mac-install/"
    echo "  Windows: https://docs.docker.com/desktop/install/windows-install/"
    echo "  Linux:   https://docs.docker.com/engine/install/"
    echo ""
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose V2 is required."
    echo "  Please update Docker Desktop to the latest version."
    exit 1
fi

echo "[ok] Docker found"

# 2. Check Git
if ! command -v git &> /dev/null; then
    echo "ERROR: Git is not installed."
    echo "  https://git-scm.com/downloads"
    exit 1
fi

# 3. Clone or update
if [ -d "$JEDISOS_HOME/.git" ]; then
    echo "[..] Updating existing installation..."
    cd "$JEDISOS_HOME"
    git pull --quiet
else
    echo "[..] Downloading JediSOS..."
    git clone --quiet "$REPO_URL" "$JEDISOS_HOME"
    cd "$JEDISOS_HOME"
fi

mkdir -p config

# 4. Docker build + start
echo "[..] Building and starting (3-7 min on first run)..."
docker compose up -d --build

# 5. Wait for health check
echo "[..] Waiting for JediSOS to start..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

# 6. Done
echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║  JediSOS is ready!               ║"
echo "  ║                                  ║"
echo "  ║  Open http://localhost:8080       ║"
echo "  ╚══════════════════════════════════╝"
echo ""
echo "  Stop:   cd $JEDISOS_HOME && docker compose down"
echo "  Start:  cd $JEDISOS_HOME && docker compose up -d"
echo "  Update: cd $JEDISOS_HOME && git pull && docker compose up -d --build"
echo ""

# 7. Open browser
if command -v open &> /dev/null; then
    open "http://localhost:8080"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:8080"
fi
