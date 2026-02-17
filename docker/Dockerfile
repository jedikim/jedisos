# docker/Dockerfile
# JediSOS 프로덕션 이미지 - 3-stage 빌드
#
# [JS-X001] docker/Dockerfile
# version: 1.0.0
# created: 2026-02-18

# --- Stage 1: Web UI 빌드 ---
FROM node:22-slim AS web-builder
WORKDIR /web
COPY web-ui/package*.json ./
RUN npm ci --production=false 2>/dev/null || echo "web-ui not yet available"
COPY web-ui/ ./
RUN npm run build 2>/dev/null || mkdir -p dist && echo '<!DOCTYPE html><html><body><h1>JediSOS</h1><p>Web UI is coming in Phase 9</p></body></html>' > dist/index.html

# --- Stage 2: Python 빌드 ---
FROM python:3.12-slim AS py-builder
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
# Web UI 빌드 결과 포함 (Phase 9 전까지는 플레이스홀더)
RUN mkdir -p src/jedisos/web/static/
COPY --from=web-builder /web/dist/ src/jedisos/web/static/
RUN pip install --no-cache-dir build && \
    python -m build --wheel && \
    pip install --no-cache-dir dist/*.whl

# --- Stage 3: 프로덕션 ---
FROM python:3.12-slim
WORKDIR /app

COPY --from=py-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=py-builder /usr/local/bin/jedisos /usr/local/bin/jedisos

# 비-root 사용자
RUN groupadd -r jedisos && useradd -r -g jedisos jedisos
USER jedisos

# 웹 UI 포트
EXPOSE 8080

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENTRYPOINT ["jedisos"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
