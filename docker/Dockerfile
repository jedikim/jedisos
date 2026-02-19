# docker/Dockerfile
# JediSOS 프로덕션 이미지
#
# [JS-X001] docker/Dockerfile
# version: 3.0.0
# created: 2026-02-18
# modified: 2026-02-19

# --- Stage 1: Python 빌드 ---
FROM python:3.12-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# PyTorch CPU-only 먼저 설치 (CUDA 제거 → ~300MB vs ~1.5GB)
# 이 레이어는 거의 바뀌지 않으므로 캐시 효율 극대화
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# sentence-transformers (local embedding) — PyTorch CPU 이미 설치되어 CUDA 안 받음
RUN pip install --no-cache-dir sentence-transformers

# zvec: AVX-512 이슈 회피 — 커스텀 x86-64-v2 wheel
COPY dist/zvec-*.whl /tmp/
RUN pip install --no-cache-dir /tmp/zvec-*.whl

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
