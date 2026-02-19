# docker/Dockerfile
# JediSOS 프로덕션 이미지 (multi-arch: amd64 + arm64)
#
# [JS-X001] docker/Dockerfile
# version: 4.0.0
# created: 2026-02-18
# modified: 2026-02-19

# --- Stage 1: Python 빌드 ---
FROM python:3.12-slim AS builder
WORKDIR /app

ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# PyTorch CPU-only (CUDA 제거 → ~189MB vs ~1.5GB)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# sentence-transformers (local embedding)
RUN pip install --no-cache-dir sentence-transformers

# zvec: 아키텍처별 분기
#   amd64 → 커스텀 wheel (AVX-512 회피, x86-64-v2 빌드)
#   arm64 → PyPI 공식 wheel (ARM에는 AVX 이슈 없음)
COPY dist/zvec-*.whl /tmp/
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        pip install --no-cache-dir /tmp/zvec-*.whl; \
    else \
        pip install --no-cache-dir zvec; \
    fi

# zvecsearch
RUN pip install --no-cache-dir git+https://github.com/jedikim/zvecsearch.git

# JediSOS 빌드
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir build && \
    python -m build --wheel && \
    pip install --no-cache-dir dist/*.whl && \
    pip install --no-cache-dir "jedisos[channels]"

# --- Stage 2: 프로덕션 ---
FROM python:3.12-slim
WORKDIR /app

# OCI 라벨 (ghcr.io 리포지토리 자동 연결)
LABEL org.opencontainers.image.source="https://github.com/jedikim/jedisos"
LABEL org.opencontainers.image.description="JediSOS - AI Personal Assistant"
LABEL org.opencontainers.image.licenses="MIT"

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/jedisos /usr/local/bin/jedisos

# 데이터 디렉토리
RUN mkdir -p /data/memory /data/tools/generated /data/.zvecsearch /data/.secvault

# 빌트인 스킬 복사
COPY tools/generated/ /data/tools/generated/

# 웹 UI 포트
EXPOSE 8866

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8866/health')" || exit 1

ENTRYPOINT ["jedisos"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8866"]
