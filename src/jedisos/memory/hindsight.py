"""
[JS-B001] jedisos.memory.hindsight
Hindsight 메모리 클라이언트 래퍼

version: 1.0.0
created: 2026-02-16
modified: 2026-02-16
dependencies: hindsight-client>=0.4.11, httpx>=0.28.1, nest-asyncio>=1.6.0
"""

from __future__ import annotations

from typing import Any

import httpx
import nest_asyncio
import structlog

from jedisos.core.config import HindsightConfig
from jedisos.core.exceptions import HindsightMemoryError

nest_asyncio.apply()
logger = structlog.get_logger()


class HindsightMemory:  # [JS-B001.1]
    """Hindsight 메모리 래퍼.

    retain/recall/reflect 세 가지 핵심 연산을 제공합니다.
    Hindsight REST API를 직접 호출하여 더 세밀한 제어를 합니다.
    """

    def __init__(self, config: HindsightConfig | None = None) -> None:
        self.config = config or HindsightConfig()
        self.base_url = self.config.api_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0),
        )
        logger.info("hindsight_memory_init", base_url=self.base_url, bank_id=self.config.bank_id)

    async def retain(  # [JS-B001.2]
        self,
        content: str,
        context: str = "",
        bank_id: str | None = None,
    ) -> dict[str, Any]:
        """대화 내용을 메모리에 저장 (Retain).

        Args:
            content: 저장할 대화 내용
            context: 추가 컨텍스트 (선택)
            bank_id: 메모리 뱅크 ID (None이면 기본값 사용)

        Returns:
            Hindsight API 응답
        """
        bid = bank_id or self.config.bank_id
        payload: dict[str, Any] = {"content": content}
        if context:
            payload["context"] = context

        try:
            resp = await self._client.post(
                f"/v1/default/banks/{bid}/memories",
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info("memory_retained", bank_id=bid, content_len=len(content))
            return result
        except httpx.HTTPStatusError as e:
            logger.error("memory_retain_failed", status=e.response.status_code, bank_id=bid)
            raise HindsightMemoryError(f"Retain 실패: {e.response.status_code}") from e

    async def recall(  # [JS-B001.3]
        self,
        query: str,
        bank_id: str | None = None,
    ) -> dict[str, Any]:
        """쿼리로 관련 메모리 검색 (Recall via Reflect endpoint).

        Args:
            query: 검색 쿼리
            bank_id: 메모리 뱅크 ID

        Returns:
            관련 메모리 컨텍스트
        """
        bid = bank_id or self.config.bank_id
        try:
            resp = await self._client.post(
                f"/v1/default/banks/{bid}/reflect",
                json={"query": query},
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info("memory_recalled", bank_id=bid, query_len=len(query))
            return result
        except httpx.HTTPStatusError as e:
            logger.error("memory_recall_failed", status=e.response.status_code, bank_id=bid)
            raise HindsightMemoryError(f"Recall 실패: {e.response.status_code}") from e

    async def reflect(  # [JS-B001.4]
        self,
        bank_id: str | None = None,
    ) -> dict[str, Any]:
        """메모리 통합/정리 트리거 (Reflect).

        4개 네트워크(World/Bank/Opinion/Observation)의 메모리를 정리합니다.
        """
        bid = bank_id or self.config.bank_id
        try:
            resp = await self._client.post(
                f"/v1/default/banks/{bid}/reflect",
                json={"query": "Consolidate and organize all recent memories."},
            )
            resp.raise_for_status()
            logger.info("memory_reflected", bank_id=bid)
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("memory_reflect_failed", status=e.response.status_code)
            raise HindsightMemoryError(f"Reflect 실패: {e.response.status_code}") from e

    async def get_entities(  # [JS-B001.5]
        self,
        bank_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """알려진 엔티티(인물, 조직 등) 목록 조회."""
        bid = bank_id or self.config.bank_id
        resp = await self._client.get(f"/v1/default/banks/{bid}/entities")
        resp.raise_for_status()
        return resp.json()

    async def health_check(self) -> bool:  # [JS-B001.6]
        """Hindsight 서버 헬스체크."""
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except httpx.ConnectError:
            return False

    async def close(self) -> None:
        """HTTP 클라이언트 종료."""
        await self._client.aclose()
