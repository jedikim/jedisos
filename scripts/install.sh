#!/bin/bash
# [JS-X003] scripts/install.sh
# JediSOS one-click install script
# Usage: curl -sSL https://raw.githubusercontent.com/jedikim/jedisos/main/scripts/install.sh | bash
#
# x86_64 / ARM64 모두 pre-built image pull (빌드 불필요)
#
# version: 6.0.0
# created: 2026-02-18
# modified: 2026-02-19

set -euo pipefail

JEDISOS_HOME="${JEDISOS_HOME:-$HOME/.jedisos}"
RAW_BASE="https://raw.githubusercontent.com/jedikim/jedisos/main"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║  JediSOS Installer               ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# --- 1. Check Docker ---
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

echo "[ok] Docker found ($(uname -m))"

# --- 2. Setup directory ---
mkdir -p "$JEDISOS_HOME/config"
cd "$JEDISOS_HOME"

# --- 3. Download compose file ---
echo "[..] Downloading configuration..."
curl -sSL -o docker-compose.yml "$RAW_BASE/docker-compose.yml"

# .env (create template if not exists)
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
# JediSOS environment variables
# Add your API keys below:
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AI...
ENVEOF
    echo "[ok] Created .env template — edit to add your API keys"
fi

# --- 4. Pull pre-built image ---
echo "[..] Pulling JediSOS image..."
docker compose pull

# --- 5. Start ---
echo "[..] Starting JediSOS..."
docker compose up -d

# --- 6. Wait for health check ---
echo "[..] Waiting for JediSOS to start (loading models, ~30s)..."
for i in $(seq 1 60); do
    if curl -s http://localhost:8866/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

if ! curl -s http://localhost:8866/health > /dev/null 2>&1; then
    echo "[!!] JediSOS is taking longer than expected to start."
    echo "     Check: cd $JEDISOS_HOME && docker compose logs -f"
    echo "     It may still be loading models. Try again in 1 minute."
else
    echo "[ok] JediSOS is running"
fi

# --- 7. Done ---
echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║  JediSOS is ready!               ║"
echo "  ║                                  ║"
echo "  ║  Open http://localhost:8866       ║"
echo "  ╚══════════════════════════════════╝"
echo ""
echo "  API keys:  nano $JEDISOS_HOME/.env"
echo "  Stop:      cd $JEDISOS_HOME && docker compose down"
echo "  Start:     cd $JEDISOS_HOME && docker compose up -d"
echo "  Update:    cd $JEDISOS_HOME && docker compose pull && docker compose up -d"
echo ""

# --- 8. Open browser ---
if command -v open &> /dev/null; then
    open "http://localhost:8866"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:8866"
fi
