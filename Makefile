.PHONY: dev check test lint format security down test-all test-cov tracking

dev:             ## 개발 환경 전체 시작
	docker compose -f docker-compose.dev.yml up -d
	@echo "Hindsight: http://localhost:8888"
	@echo "Hindsight UI: http://localhost:9999"

down:            ## 개발 환경 중지
	docker compose -f docker-compose.dev.yml down

check: lint security test  ## 전체 검증

lint:            ## 코드 린트
	ruff check src/ tests/
	ruff format --check src/ tests/

format:          ## 코드 포맷팅
	ruff format src/ tests/

security:        ## 보안 검사
	bandit -r src/ -c pyproject.toml

test:            ## 단위 테스트만
	pytest tests/unit/ -v --timeout=30

test-all:        ## 전체 테스트
	pytest tests/ -v --timeout=300

test-cov:        ## 커버리지 포함
	pytest tests/ --cov=jedisos --cov-report=html --cov-report=term

tracking:        ## 추적 해시 문서 생성
	python scripts/generate_tracking.py > docs/TRACKING_REGISTRY.md
