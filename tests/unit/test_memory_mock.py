"""
[JS-T002] tests.unit.test_memory_mock
ZvecMemory 단위 테스트 (mock 기반, zvecsearch 불필요)

version: 2.0.0
created: 2026-02-16
modified: 2026-02-19
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from jedisos.core.config import MemoryConfig
from jedisos.memory.identity import AgentIdentity
from jedisos.memory.markdown_writer import (
    append_entity,
    append_section,
    append_to_memory,
    ensure_file,
    get_daily_log_path,
    read_file,
)
from jedisos.memory.mcp_wrapper import HindsightMCPWrapper
from jedisos.memory.signal_detector import SignalDetector, create_default_patterns_yaml
from jedisos.memory.zvec_memory import ZvecMemory

if TYPE_CHECKING:
    from pathlib import Path


# === ZvecMemory 테스트 ===


@pytest.fixture
def memory(tmp_path: Path) -> ZvecMemory:
    config = MemoryConfig(data_dir=str(tmp_path / "data"), bank_id="test-bank")
    return ZvecMemory(config=config)


class TestZvecMemoryRetain:  # [JS-T002.1]
    """retain() 테스트."""

    async def test_retain_success(self, memory: ZvecMemory) -> None:
        result = await memory.retain("Alice는 엔지니어입니다", context="user")
        assert result["status"] == "retained"
        assert result["bank_id"] == "test-bank"
        assert result["content_length"] > 0

    async def test_retain_creates_daily_log(self, memory: ZvecMemory) -> None:
        await memory.retain("안녕하세요", context="user")
        log_path = get_daily_log_path(memory.memory_dir)
        assert log_path.exists()
        content = read_file(log_path)
        assert "안녕하세요" in content
        assert "[user]" in content

    async def test_retain_detects_important_facts_with_llm(self, memory: ZvecMemory) -> None:
        """LLM 라우터가 있으면 사실 추출 + MEMORY.md 저장."""
        from unittest.mock import AsyncMock, MagicMock

        mock_llm = MagicMock()
        mock_llm.complete_text = AsyncMock(return_value='["이름: 김제다이"]')
        memory.set_llm_router(mock_llm)

        result = await memory.retain("내 이름은 김제다이야", context="user")
        assert result["facts_detected"] == 1
        memory_content = read_file(memory.memory_dir / "MEMORY.md")
        assert "김제다이" in memory_content

    async def test_retain_no_facts_without_llm(self, memory: ZvecMemory) -> None:
        """LLM 라우터가 없으면 사실 추출 안 함."""
        result = await memory.retain("내 이름은 김제다이야", context="user")
        assert result["facts_detected"] == 0

    async def test_retain_with_bank_id(self, memory: ZvecMemory) -> None:
        result = await memory.retain("test", bank_id="custom-bank")
        assert result["bank_id"] == "custom-bank"

    async def test_retain_encrypts_sensitive(self, memory: ZvecMemory) -> None:
        """SecVault 클라이언트가 있으면 민감 정보를 암호화."""
        mock_vault = AsyncMock()
        mock_vault.encrypt = AsyncMock(return_value="[[SECDATA:AES256GCM:a:b:c]]")
        memory.set_vault_client(mock_vault)

        await memory.retain("비밀번호: my-secret-123", context="user")
        # SecVault encrypt가 호출되었는지 확인
        mock_vault.encrypt.assert_called()


class TestZvecMemoryRecall:  # [JS-T002.2]
    """recall() 테스트."""

    async def test_recall_fallback_returns_memory(self, memory: ZvecMemory) -> None:
        """zvecsearch 없이 MEMORY.md 폴백 검색."""
        # 메모리에 데이터 저장
        await memory.retain("Alice는 Google에서 일합니다", context="user")

        result = await memory.recall("Alice는 어디서 일하나요?")
        assert "context" in result
        assert result["bank_id"] == "test-bank"
        assert result.get("fallback") is True

    async def test_recall_with_bank_id(self, memory: ZvecMemory) -> None:
        result = await memory.recall("test", bank_id="custom-bank")
        assert result["bank_id"] == "custom-bank"


class TestZvecMemoryReflect:  # [JS-T002.3]
    """reflect() 테스트."""

    async def test_reflect_without_zvecsearch(self, memory: ZvecMemory) -> None:
        """zvecsearch 없이 reflect는 indexed_files=0."""
        result = await memory.reflect()
        assert result["status"] == "reflected"
        assert result["indexed_files"] == 0


class TestZvecMemoryHealthCheck:  # [JS-T002.4]
    """health_check() 테스트."""

    async def test_health_check_success(self, memory: ZvecMemory) -> None:
        assert await memory.health_check() is True

    async def test_health_check_missing_dir(self, tmp_path: Path) -> None:
        config = MemoryConfig(data_dir=str(tmp_path / "nonexistent"))
        m = ZvecMemory(config=config)
        # ZvecMemory가 디렉토리를 자동 생성하므로 성공
        assert await m.health_check() is True


class TestZvecMemoryEntities:  # [JS-T002.5]
    """엔티티 테스트."""

    async def test_get_entities_empty(self, memory: ZvecMemory) -> None:
        entities = await memory.get_entities()
        assert entities == []

    async def test_add_and_get_entities(self, memory: ZvecMemory) -> None:
        await memory.add_entity("김제다이", entity_type="person", details="개발자")
        await memory.add_entity("Google", entity_type="org")

        entities = await memory.get_entities()
        assert len(entities) == 2
        assert entities[0]["name"] == "김제다이"
        assert entities[0]["type"] == "person"
        assert entities[1]["name"] == "Google"

    async def test_add_duplicate_entity(self, memory: ZvecMemory) -> None:
        await memory.add_entity("김제다이", entity_type="person")
        await memory.add_entity("김제다이", entity_type="person")

        entities = await memory.get_entities()
        assert len(entities) == 1  # 중복 방지


# === MarkdownWriter 테스트 ===


class TestMarkdownWriter:  # [JS-T002.6]
    """마크다운 유틸리티 테스트."""

    def test_ensure_file_creates(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "test.md"
        ensure_file(p, "# Hello\n")
        assert p.exists()
        assert p.read_text() == "# Hello\n"

    def test_ensure_file_no_overwrite(self, tmp_path: Path) -> None:
        p = tmp_path / "test.md"
        p.write_text("existing")
        ensure_file(p, "new content")
        assert p.read_text() == "existing"

    def test_read_file_missing(self, tmp_path: Path) -> None:
        assert read_file(tmp_path / "missing.md") == ""

    def test_append_section(self, tmp_path: Path) -> None:
        p = tmp_path / "conversations" / "2026-02-19.md"
        append_section(p, "안녕하세요", role="user", bank_id="test")
        content = p.read_text()
        assert "안녕하세요" in content
        assert "[user]" in content
        assert "bank:test" in content

    def test_append_to_memory(self, tmp_path: Path) -> None:
        p = tmp_path / "MEMORY.md"
        append_to_memory(p, "이름은 김제다이", source="test-bank")
        content = p.read_text()
        assert "김제다이" in content
        assert "test-bank" in content

    def test_append_entity(self, tmp_path: Path) -> None:
        p = tmp_path / "ENTITIES.md"
        append_entity(p, "김제다이", entity_type="person", details="개발자")
        content = p.read_text()
        assert "**김제다이**" in content
        assert "(person)" in content

    def test_append_entity_no_duplicate(self, tmp_path: Path) -> None:
        p = tmp_path / "ENTITIES.md"
        append_entity(p, "Alice")
        append_entity(p, "Alice")
        content = p.read_text()
        assert content.count("**Alice**") == 1

    def test_get_daily_log_path(self, tmp_path: Path) -> None:
        from datetime import datetime

        path = get_daily_log_path(tmp_path, datetime(2026, 2, 19))
        assert str(path).endswith("conversations/2026-02-19.md")


# === SignalDetector 테스트 ===


class TestSignalDetector:  # [JS-T002.7]
    """민감 정보 감지 테스트."""

    def test_detect_korean_resident_id(self) -> None:
        d = SignalDetector()
        matches = d.detect_sensitive("주민번호는 900101-1234567 입니다")
        assert len(matches) >= 1
        assert any(m.pattern_name == "korean_resident_id" for m in matches)

    def test_detect_credit_card(self) -> None:
        d = SignalDetector()
        matches = d.detect_sensitive("카드: 4111-1111-1111-1111")
        assert len(matches) >= 1
        assert any(m.pattern_name == "credit_card" for m in matches)

    def test_detect_api_key(self) -> None:
        d = SignalDetector()
        matches = d.detect_sensitive("키는 sk-1234567890abcdefghij 입니다")
        assert len(matches) >= 1
        assert any(m.pattern_name == "api_key_openai" for m in matches)

    def test_detect_password_context(self) -> None:
        d = SignalDetector()
        matches = d.detect_sensitive("비밀번호: my-secret-123")
        assert len(matches) >= 1
        assert any(m.pattern_name == "password_context" for m in matches)

    def test_no_false_positive_name(self) -> None:
        """이름, 이메일은 감지하지 않아야 함."""
        d = SignalDetector()
        matches = d.detect_sensitive("내 이름은 김제다이입니다")
        assert len(matches) == 0

    def test_has_sensitive(self) -> None:
        d = SignalDetector()
        assert d.has_sensitive("비밀번호: abc123") is True
        assert d.has_sensitive("일반 텍스트") is False

    def test_mask_sensitive(self) -> None:
        d = SignalDetector()
        result = d.mask_sensitive("키는 sk-1234567890abcdefghij 입니다")
        assert "sk-" not in result
        assert "***" in result

    def test_from_yaml(self, tmp_path: Path) -> None:
        create_default_patterns_yaml(tmp_path / "patterns.yaml")
        d = SignalDetector.from_yaml(tmp_path / "patterns.yaml")
        assert len(d.get_pattern_info()) > 0

    def test_from_yaml_missing_file(self, tmp_path: Path) -> None:
        d = SignalDetector.from_yaml(tmp_path / "missing.yaml")
        assert len(d.get_pattern_info()) > 0  # 기본 패턴 사용

    def test_reload_from_yaml(self, tmp_path: Path) -> None:
        create_default_patterns_yaml(tmp_path / "patterns.yaml")
        d = SignalDetector()
        initial_count = len(d.get_pattern_info())
        d.reload_from_yaml(tmp_path / "patterns.yaml")
        assert len(d.get_pattern_info()) == initial_count


# === Identity 테스트 (기존 유지) ===


class TestIdentity:  # [JS-T002.8]
    def test_default_identity(self) -> None:
        identity = AgentIdentity()
        prompt = identity.to_system_prompt()
        assert prompt.startswith("당신의 정체성:")
        assert "JediSOS" in prompt

    def test_custom_identity(self, tmp_path: Path) -> None:
        custom = tmp_path / "IDENTITY.md"
        custom.write_text("# Custom Agent\n커스텀 에이전트입니다.", encoding="utf-8")
        identity = AgentIdentity(identity_path=custom)
        prompt = identity.to_system_prompt()
        assert "커스텀 에이전트" in prompt


# === MCPWrapper 테스트 (기존 인터페이스 호환) ===


class TestMCPWrapper:  # [JS-T002.9]
    @pytest.fixture
    def wrapper(self, memory: ZvecMemory) -> HindsightMCPWrapper:
        return HindsightMCPWrapper(memory)

    async def test_get_tools(self, wrapper: HindsightMCPWrapper) -> None:
        tools = wrapper.get_tools()
        assert len(tools) == 3
        names = {t["name"] for t in tools}
        assert names == {"memory_retain", "memory_recall", "memory_reflect"}

    async def test_execute_retain(self, wrapper: HindsightMCPWrapper) -> None:
        result = await wrapper.execute("memory_retain", {"content": "test memory"})
        assert result["status"] == "retained"

    async def test_execute_unknown_tool(self, wrapper: HindsightMCPWrapper) -> None:
        result = await wrapper.execute("unknown_tool", {})
        assert "error" in result
