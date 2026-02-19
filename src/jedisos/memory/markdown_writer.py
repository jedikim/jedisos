"""
[JS-B005] jedisos.memory.markdown_writer
마크다운 파일 읽기/쓰기/append 유틸리티

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger()


def ensure_file(path: Path, default_content: str = "") -> Path:  # [JS-B005.1]
    """파일이 없으면 생성합니다.

    Args:
        path: 파일 경로
        default_content: 파일 생성 시 기본 내용

    Returns:
        파일 경로
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(default_content, encoding="utf-8")
        logger.debug("markdown_file_created", path=str(path))
    return path


def read_file(path: Path) -> str:  # [JS-B005.2]
    """마크다운 파일을 읽습니다.

    Args:
        path: 파일 경로

    Returns:
        파일 내용 (없으면 빈 문자열)
    """
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:  # [JS-B005.3]
    """마크다운 파일을 덮어씁니다.

    Args:
        path: 파일 경로
        content: 작성할 내용
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.debug("markdown_file_written", path=str(path), length=len(content))


def append_section(  # [JS-B005.4]
    path: Path,
    content: str,
    *,
    role: str = "user",
    bank_id: str = "",
    timestamp: datetime | None = None,
) -> None:
    """대화 로그 섹션을 마크다운 파일에 추가합니다.

    형식:
        ## HH:MM:SS [role] bank:bank_id
        content

    Args:
        path: 대화 로그 파일 경로
        content: 메시지 내용
        role: 발화자 역할 (user/assistant)
        bank_id: 뱅크 식별자
        timestamp: 타임스탬프 (None이면 현재 시간)
    """
    ts = timestamp or datetime.now()
    time_str = ts.strftime("%H:%M:%S")
    bank_part = f" bank:{bank_id}" if bank_id else ""

    section = f"\n## {time_str} [{role}]{bank_part}\n{content}\n"

    path.parent.mkdir(parents=True, exist_ok=True)

    # 파일이 없으면 일별 헤더 추가
    if not path.exists():
        date_str = ts.strftime("%Y-%m-%d")
        header = f"# {date_str} 대화\n"
        path.write_text(header + section, encoding="utf-8")
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(section)


def append_to_memory(  # [JS-B005.5]
    path: Path,
    fact: str,
    *,
    source: str = "",
    timestamp: datetime | None = None,
) -> None:
    """MEMORY.md에 사실/선호도를 추가합니다.

    중복 방지: 동일한 fact 문자열이 이미 있으면 추가하지 않습니다.

    Args:
        path: MEMORY.md 경로
        fact: 추가할 사실
        source: 출처 (bank_id 등)
        timestamp: 타임스탬프
    """
    ensure_file(path, "# 메모리\n\n영구 사실과 선호도가 기록됩니다.\n\n")

    # 중복 체크
    existing = read_file(path)
    if fact in existing:
        logger.debug("memory_fact_duplicate", fact=fact[:50])
        return

    ts = timestamp or datetime.now()
    date_str = ts.strftime("%Y-%m-%d")
    source_part = f" (from: {source})" if source else ""

    line = f"- [{date_str}] {fact}{source_part}\n"

    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def append_entity(  # [JS-B005.6]
    path: Path,
    name: str,
    entity_type: str = "",
    details: str = "",
) -> None:
    """ENTITIES.md에 엔티티를 추가합니다.

    Args:
        path: ENTITIES.md 경로
        name: 엔티티 이름
        entity_type: 유형 (person/org/place 등)
        details: 세부 정보
    """
    type_part = f" ({entity_type})" if entity_type else ""
    detail_part = f": {details}" if details else ""
    line = f"- **{name}**{type_part}{detail_part}\n"

    ensure_file(path, "# 엔티티\n\n알려진 인물, 조직, 장소 등이 기록됩니다.\n\n")

    # 중복 방지: 이미 같은 이름이 있으면 추가하지 않음
    existing = read_file(path)
    if f"**{name}**" in existing:
        logger.debug("entity_already_exists", name=name)
        return

    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def get_daily_log_path(memory_dir: Path, date: datetime | None = None) -> Path:  # [JS-B005.7]
    """일별 대화 로그 파일 경로를 반환합니다.

    Args:
        memory_dir: 메모리 디렉토리 경로
        date: 날짜 (None이면 오늘)

    Returns:
        conversations/YYYY-MM-DD.md 경로
    """
    d = date or datetime.now()
    return memory_dir / "conversations" / f"{d.strftime('%Y-%m-%d')}.md"
