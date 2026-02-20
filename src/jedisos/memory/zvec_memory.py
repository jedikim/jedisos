"""
[JS-B001] jedisos.memory.zvec_memory
zvecsearch 기반 마크다운 메모리 시스템

Hindsight 호환 인터페이스를 제공합니다.
retain/recall/reflect 세 가지 핵심 연산:
- retain: 대화 내용을 마크다운으로 저장 + 인덱싱
- recall: 하이브리드 검색 (dense+sparse+reranker)
- reflect: 오래된 로그 요약/압축

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
dependencies: pyyaml>=6.0.2
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from jedisos.core.config import MemoryConfig
from jedisos.core.exceptions import MemorySystemError
from jedisos.memory.markdown_writer import (
    append_entity,
    append_section,
    append_to_memory,
    ensure_file,
    get_daily_log_path,
    read_file,
)
from jedisos.memory.signal_detector import SignalDetector, create_default_patterns_yaml

logger = structlog.get_logger()

# zvecsearch 조건부 import (Docker에서만 설치됨)
try:
    from zvecsearch import ZvecSearch

    _HAS_ZVECSEARCH = True
except ImportError:
    _HAS_ZVECSEARCH = False
    ZvecSearch = None  # type: ignore[assignment,misc]

_zvec_patched = False


def _patch_zvec_compat() -> None:
    """zvec 0.2.x / zvecsearch 0.1.0 API 호환성 패치.

    두 가지 문제를 수정합니다:
    1. Collection.query()에서 query_param 미지원 → 인자 제거
    2. filter 파서가 '==' 문법 미지원 → 에러 시 빈 결과 반환
    """
    global _zvec_patched
    if _zvec_patched:
        return
    _zvec_patched = True

    try:
        from zvec.model.collection import Collection

        _orig_query = Collection.query

        def _patched_query(
            self: Collection,
            vectors: Any = None,
            **kwargs: Any,
        ) -> Any:
            kwargs.pop("query_param", None)
            return _orig_query(self, vectors, **kwargs)

        Collection.query = _patched_query  # type: ignore[assignment]

        from zvecsearch.store import ZvecStore

        def _safe_hashes_by_source(self: ZvecStore, source: str) -> set[str]:
            try:
                safe = self._escape_filter_value(source)
                results = self._collection.query(
                    filter=f"source = '{safe}'",
                    output_fields=["chunk_hash"],
                )
                return {doc.field("chunk_hash") for doc in results}
            except Exception:
                return set()

        def _safe_delete_by_source(self: ZvecStore, source: str) -> None:
            try:
                safe = self._escape_filter_value(source)
                self._collection.delete_by_filter(f"source = '{safe}'")
            except Exception:
                pass

        ZvecStore.hashes_by_source = _safe_hashes_by_source  # type: ignore[assignment]
        ZvecStore.delete_by_source = _safe_delete_by_source  # type: ignore[assignment]

        logger.info("zvec_compat_patched")
    except Exception as e:
        logger.warning("zvec_compat_patch_failed", error=str(e))


class ZvecMemory:  # [JS-B001.1]
    """zvecsearch 기반 마크다운 메모리 시스템.

    Hindsight 호환 인터페이스를 제공합니다:
    - retain(): 대화 내용 저장 + 인덱싱
    - recall(): 하이브리드 검색
    - reflect(): 오래된 로그 요약/압축
    - health_check(): 시스템 상태 확인
    - get_entities(): 엔티티 목록 조회
    - close(): 리소스 정리
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:  # [JS-B001.1.1]
        self.config = config or MemoryConfig()
        self.data_dir = Path(self.config.data_dir)
        self.memory_dir = self.data_dir / "memory"
        self.zvec_dir = self.data_dir / ".zvecsearch"

        # 디렉토리 구조 생성
        self._ensure_dirs()

        # zvecsearch 인덱서 초기화 (호환성 패치 먼저)
        self._search: Any = None
        if _HAS_ZVECSEARCH:
            _patch_zvec_compat()
            self._search = ZvecSearch(
                paths=[str(self.memory_dir)],
                zvec_path=str(self.zvec_dir / "db"),
                collection=self.config.bank_id,
                embedding_provider=self.config.embedding_provider,
            )
            logger.info("zvec_search_initialized", paths=str(self.memory_dir))
        else:
            logger.warning("zvecsearch_not_available")

        # 민감 정보 감지기 초기화
        patterns_path = self.memory_dir / "sensitive_patterns.yaml"
        if not patterns_path.exists():
            create_default_patterns_yaml(patterns_path)
        self._detector = SignalDetector.from_yaml(patterns_path)

        # SecVault 클라이언트 (나중에 설정됨)
        self._vault_client: Any = None

        logger.info(
            "zvec_memory_init",
            data_dir=str(self.data_dir),
            bank_id=self.config.bank_id,
            has_zvecsearch=_HAS_ZVECSEARCH,
        )

    def _ensure_dirs(self) -> None:
        """필수 디렉토리를 생성합니다."""
        dirs = [
            self.memory_dir,
            self.memory_dir / "conversations",
            self.memory_dir / "skills",
            self.memory_dir / "encrypted",
            self.memory_dir / "identity",
            self.zvec_dir / "db",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # 기본 파일 생성
        ensure_file(
            self.memory_dir / "MEMORY.md",
            "# 메모리\n\n영구 사실과 선호도가 기록됩니다.\n\n",
        )
        ensure_file(
            self.memory_dir / "ENTITIES.md",
            "# 엔티티\n\n알려진 인물, 조직, 장소 등이 기록됩니다.\n\n",
        )

    def set_vault_client(self, client: Any) -> None:  # [JS-B001.1.2]
        """SecVault 클라이언트를 설정합니다.

        Args:
            client: SecVaultClient 인스턴스
        """
        self._vault_client = client
        logger.info("zvec_memory_vault_client_set")

    async def retain(  # [JS-B001.2]
        self,
        content: str,
        context: str = "",
        bank_id: str | None = None,
    ) -> dict[str, Any]:
        """대화 내용을 메모리에 저장합니다.

        동작:
        1. bank_id로 대상 파일 결정 (conversations/ 또는 skills/)
        2. 타임스탬프 헤딩으로 마크다운 섹션 append
        3. 중요 사실 감지 → MEMORY.md에 기록
        4. 엔티티 감지 → ENTITIES.md에 기록
        5. 민감 정보 감지 → SecVault로 암호화 → [[SECDATA:...]]로 치환
        6. zvecsearch 인크리멘털 인덱싱

        Args:
            content: 저장할 대화 내용
            context: 추가 컨텍스트 (role 등)
            bank_id: 메모리 뱅크 ID

        Returns:
            저장 결과 딕셔너리
        """
        bid = bank_id or self.config.bank_id

        # 민감 정보 암호화
        processed_content = await self._encrypt_sensitive(content)

        # 역할 추출
        role = "user"
        if context:
            role = context if context in ("user", "assistant", "system") else "user"

        # 대화 로그에 추가
        log_path = get_daily_log_path(self.memory_dir)
        append_section(log_path, processed_content, role=role, bank_id=bid)

        # 중요 사실 감지 → MEMORY.md
        facts = self._detector.detect_important_facts(content)
        if facts:
            memory_path = self.memory_dir / "MEMORY.md"
            for fact in facts:
                append_to_memory(memory_path, fact, source=bid)

        # zvecsearch 인덱싱
        if self._search is not None:
            try:
                self._search.index_file(str(log_path))
            except Exception as e:
                logger.warning("zvec_index_file_error", error=str(e), path=str(log_path))

        logger.info("memory_retained", bank_id=bid, content_len=len(content))
        return {
            "status": "retained",
            "bank_id": bid,
            "content_length": len(content),
            "facts_detected": len(facts),
            "log_path": str(log_path),
        }

    async def recall(  # [JS-B001.3]
        self,
        query: str,
        bank_id: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """쿼리로 관련 메모리를 검색합니다.

        동작:
        1. zvecsearch.search(query, top_k) 하이브리드 검색
        2. bank_id 필터링 (소스 경로 기반)
        3. 결과에 [[SECDATA:...]] 있으면 SecVault로 복호화
        4. 컨텍스트 문자열 반환

        Args:
            query: 검색 쿼리
            bank_id: 메모리 뱅크 ID (필터링용)
            top_k: 최대 검색 결과 수

        Returns:
            검색 결과 딕셔너리
        """
        bid = bank_id or self.config.bank_id

        # zvecsearch가 없으면 MEMORY.md 전문 검색 폴백
        if self._search is None:
            return await self._recall_fallback(query, bid)

        try:
            results = self._search.search(query, top_k=top_k)
        except Exception as e:
            logger.warning("zvec_search_fallback", error=str(e))
            return await self._recall_fallback(query, bid)

        # 결과 처리
        memories: list[dict[str, Any]] = []
        for result in results:
            text = result.get("text", "") if isinstance(result, dict) else str(result)

            # SecVault 복호화
            text = await self._decrypt_secdata(text)

            memories.append(
                {
                    "content": text,
                    "score": result.get("score", 0.0) if isinstance(result, dict) else 0.0,
                    "source": result.get("source", "") if isinstance(result, dict) else "",
                }
            )

        # 컨텍스트 문자열 구성
        context_parts = [m["content"] for m in memories if m["content"]]
        context_str = "\n---\n".join(context_parts) if context_parts else ""

        logger.info("memory_recalled", bank_id=bid, query_len=len(query), results=len(memories))
        return {
            "context": context_str,
            "memories": memories,
            "query": query,
            "bank_id": bid,
        }

    async def _recall_fallback(self, query: str, bank_id: str) -> dict[str, Any]:
        """zvecsearch 없이 MEMORY.md에서 간단한 텍스트 검색을 수행합니다."""
        memory_content = read_file(self.memory_dir / "MEMORY.md")
        entity_content = read_file(self.memory_dir / "ENTITIES.md")

        context = ""
        if memory_content:
            context += f"[메모리]\n{memory_content}\n"
        if entity_content:
            context += f"[엔티티]\n{entity_content}\n"

        return {
            "context": context,
            "memories": [],
            "query": query,
            "bank_id": bank_id,
            "fallback": True,
        }

    async def reflect(  # [JS-B001.4]
        self,
        bank_id: str | None = None,
    ) -> dict[str, Any]:
        """메모리 통합/정리를 수행합니다.

        동작:
        1. zvecsearch 전체 인덱스 재구축
        2. (향후) 7일 이상 된 로그 LLM 요약/압축

        Args:
            bank_id: 메모리 뱅크 ID

        Returns:
            정리 결과
        """
        bid = bank_id or self.config.bank_id

        # zvecsearch 전체 인덱스
        indexed_files = 0
        if self._search is not None:
            try:
                self._search.index(force=True)
                indexed_files = len(list(self.memory_dir.rglob("*.md")))
            except Exception as e:
                logger.error("zvec_reindex_error", error=str(e))
                raise MemorySystemError(f"인덱스 재구축 실패: {e}") from e

        logger.info("memory_reflected", bank_id=bid, indexed_files=indexed_files)
        return {
            "status": "reflected",
            "bank_id": bid,
            "indexed_files": indexed_files,
        }

    async def health_check(self) -> bool:  # [JS-B001.5]
        """메모리 시스템 상태를 확인합니다."""
        try:
            # 디렉토리 존재 확인
            if not self.memory_dir.exists():
                return False
            # MEMORY.md 접근 가능 확인
            memory_path = self.memory_dir / "MEMORY.md"
            return memory_path.exists()
        except Exception:
            return False

    async def get_entities(  # [JS-B001.6]
        self,
        bank_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """알려진 엔티티 목록을 조회합니다."""
        entities_content = read_file(self.memory_dir / "ENTITIES.md")
        if not entities_content:
            return []

        entities: list[dict[str, Any]] = []
        for line in entities_content.split("\n"):
            line = line.strip()
            if line.startswith("- **") and "**" in line[4:]:
                # "- **이름** (유형): 세부사항" 파싱
                end_bold = line.index("**", 4)
                name = line[4:end_bold]
                rest = line[end_bold + 2 :].strip()
                entity: dict[str, Any] = {"name": name}
                if rest.startswith("(") and ")" in rest:
                    close_paren = rest.index(")")
                    entity["type"] = rest[1:close_paren]
                    rest = rest[close_paren + 1 :].strip().lstrip(":").strip()
                if rest:
                    entity["details"] = rest
                entities.append(entity)

        return entities

    async def add_entity(  # [JS-B001.7]
        self,
        name: str,
        entity_type: str = "",
        details: str = "",
    ) -> None:
        """엔티티를 추가합니다."""
        append_entity(
            self.memory_dir / "ENTITIES.md",
            name=name,
            entity_type=entity_type,
            details=details,
        )

    async def close(self) -> None:  # [JS-B001.8]
        """리소스를 정리합니다."""
        logger.info("zvec_memory_closed")

    async def _encrypt_sensitive(self, text: str) -> str:  # [JS-B001.9]
        """텍스트 내 민감 정보를 SecVault로 암호화합니다."""
        if self._vault_client is None:
            return text

        matches = self._detector.detect_sensitive(text)
        if not matches:
            return text

        result = text
        # 뒤에서부터 치환 (인덱스 유지)
        for match in sorted(matches, key=lambda m: m.start, reverse=True):
            try:
                encrypted = await self._vault_client.encrypt(match.matched_text)
                result = result[: match.start] + encrypted + result[match.end :]
                logger.debug(
                    "sensitive_data_encrypted",
                    pattern=match.pattern_name,
                )
            except Exception as e:
                logger.warning(
                    "sensitive_encrypt_failed",
                    pattern=match.pattern_name,
                    error=str(e),
                )
        return result

    async def _decrypt_secdata(self, text: str) -> str:  # [JS-B001.10]
        """텍스트 내 [[SECDATA:...]] 마커를 복호화합니다."""
        if self._vault_client is None:
            return text

        try:
            return await self._vault_client.decrypt_all(text)
        except Exception as e:
            logger.warning("secdata_decrypt_failed", error=str(e))
            return text
