"""
[JS-B004] jedisos.memory.signal_detector
민감 정보 감지 + 중요 사실 추출

패턴은 외부 YAML 파일(sensitive_patterns.yaml)로 분리하여
LLM이 차후 패턴 추가/수정 가능하도록 합니다.

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
dependencies: pyyaml>=6.0.2
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog
import yaml

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger()

# 내장 기본 민감 정보 패턴 (YAML 파일이 없을 때 사용)
DEFAULT_PATTERNS: list[dict[str, str]] = [
    {
        "name": "korean_resident_id",
        "regex": r"\d{6}-[1-4]\d{6}",
        "description": "주민등록번호",
    },
    {
        "name": "credit_card",
        "regex": r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",
        "description": "신용카드 번호",
    },
    {
        "name": "bank_account_kr",
        "regex": r"\d{3,4}-\d{2,6}-\d{2,6}",
        "description": "한국 계좌번호",
    },
    {
        "name": "api_key_openai",
        "regex": r"sk-[A-Za-z0-9]{20,}",
        "description": "OpenAI API 키",
    },
    {
        "name": "api_key_github",
        "regex": r"ghp_[A-Za-z0-9]{36,}",
        "description": "GitHub PAT",
    },
    {
        "name": "api_key_aws",
        "regex": r"AKIA[A-Z0-9]{16}",
        "description": "AWS Access Key",
    },
    {
        "name": "bot_token_telegram",
        "regex": r"\d{8,10}:[A-Za-z0-9_-]{35}",
        "description": "텔레그램 봇 토큰",
    },
    {
        "name": "bot_token_slack",
        "regex": r"xoxb-[A-Za-z0-9-]+",
        "description": "슬랙 봇 토큰",
    },
    {
        "name": "password_context",
        "regex": r"(?:비밀번호|password|passwd|secret|credential)[:\s=]+\S+",
        "description": "비밀번호 문맥",
    },
    {
        "name": "ssn_us",
        "regex": r"\d{3}-\d{2}-\d{4}",
        "description": "US Social Security Number",
    },
]

# 중요 사실 키워드 패턴 (한국어 + 영어)
IMPORTANT_FACT_KEYWORDS = [
    # 이름
    r"내\s*이름은?\s+(.+?)(?:이야|예요|입니다|이에요|야|[.\s]|$)",
    # 생일/생년월일
    r"(?:제|나의?)\s*(?:생일|생년월일)[은는이가]?\s+(.+?)(?:이야|예요|입니다|이에요|야|[.\s]|$)",
    # 주소 (핵심)
    r"(?:내|나의?|제)\s*주소[는은]?\s*(.+?)(?:\s*(?:인데|이야|이에요|예요|입니다|야)|$)",
    # 거주지 (다중 단어 캡처)
    r"(?:나는?|저는?)\s+(.+?)\s*(?:에서|에)\s*(?:살아|살고|거주)",
    # 좋아/싫어/선호
    r"(?:나는?|저는?)\s+(.+?)\s*(?:를|을)?\s*(?:좋아해|싫어해|좋아|싫어|선호)",
    # "X 기억해" → X 전체 문장 캡처 (핵심 수정)
    r"(.+?)\s+(?:기억해줘|기억해\s*줘|기억해|remember|잊지\s*마)",
    # 전화번호
    r"(?:내|나의?|제)\s*(?:전화|핸드폰|연락처|번호)[은는]?\s*(.+?)(?:\s|$)",
    # 이메일
    r"(?:내|나의?|제)\s*(?:이메일|메일)[은는]?\s*(\S+@\S+)",
]


class SensitiveMatch:  # [JS-B004.1]
    """민감 정보 매치 결과."""

    def __init__(self, pattern_name: str, matched_text: str, start: int, end: int) -> None:
        self.pattern_name = pattern_name
        self.matched_text = matched_text
        self.start = start
        self.end = end

    def __repr__(self) -> str:
        return f"SensitiveMatch({self.pattern_name!r}, pos={self.start}-{self.end})"


class SignalDetector:  # [JS-B004.2]
    """텍스트에서 민감 정보와 중요 사실을 감지합니다.

    사용법:
        detector = SignalDetector()
        # 또는 YAML 파일에서 로드:
        detector = SignalDetector.from_yaml(Path("sensitive_patterns.yaml"))

        matches = detector.detect_sensitive(text)
        facts = detector.detect_important_facts(text)
    """

    def __init__(self, patterns: list[dict[str, str]] | None = None) -> None:
        self._raw_patterns = patterns or DEFAULT_PATTERNS
        self._compiled: list[tuple[str, re.Pattern[str], str]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:  # [JS-B004.2.1]
        """패턴을 컴파일합니다."""
        self._compiled = []
        for p in self._raw_patterns:
            try:
                compiled = re.compile(p["regex"])
                self._compiled.append((p["name"], compiled, p.get("description", "")))
            except re.error as e:
                logger.warning("signal_pattern_compile_error", name=p["name"], error=str(e))

    @classmethod
    def from_yaml(cls, path: Path) -> SignalDetector:  # [JS-B004.2.2]
        """YAML 파일에서 패턴을 로드합니다.

        파일이 없으면 기본 패턴을 사용합니다.

        Args:
            path: sensitive_patterns.yaml 경로

        Returns:
            SignalDetector 인스턴스
        """
        if not path.exists():
            logger.info("signal_yaml_not_found", path=str(path))
            return cls()

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data or "patterns" not in data:
            logger.warning("signal_yaml_invalid", path=str(path))
            return cls()

        patterns = data["patterns"]
        logger.info("signal_yaml_loaded", path=str(path), pattern_count=len(patterns))
        return cls(patterns=patterns)

    def detect_sensitive(self, text: str) -> list[SensitiveMatch]:  # [JS-B004.3]
        """텍스트에서 민감 정보를 감지합니다.

        Args:
            text: 검사할 텍스트

        Returns:
            감지된 민감 정보 리스트
        """
        matches: list[SensitiveMatch] = []
        for name, pattern, _desc in self._compiled:
            for m in pattern.finditer(text):
                matches.append(
                    SensitiveMatch(
                        pattern_name=name,
                        matched_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                    )
                )
        return matches

    def has_sensitive(self, text: str) -> bool:  # [JS-B004.4]
        """텍스트에 민감 정보가 있는지 빠르게 확인합니다."""
        return any(pattern.search(text) for _, pattern, _ in self._compiled)

    def mask_sensitive(self, text: str, replacement: str = "***") -> str:  # [JS-B004.5]
        """민감 정보를 마스킹합니다.

        Args:
            text: 원본 텍스트
            replacement: 대체 문자열

        Returns:
            마스킹된 텍스트
        """
        result = text
        matches = self.detect_sensitive(text)
        # 뒤에서부터 교체 (인덱스 유지)
        for match in sorted(matches, key=lambda m: m.start, reverse=True):
            result = result[: match.start] + replacement + result[match.end :]
        return result

    def detect_important_facts(self, text: str) -> list[str]:  # [JS-B004.6]
        """텍스트에서 중요 사실/선호도를 감지합니다.

        Args:
            text: 검사할 텍스트

        Returns:
            감지된 중요 사실 리스트
        """
        # 키워드만 있는 의미없는 매치 제거용
        _noise = {"기억해", "기억해줘", "remember", "잊지마", "잊지 마"}

        facts: list[str] = []
        seen: set[str] = set()
        for pattern_str in IMPORTANT_FACT_KEYWORDS:
            for m in re.finditer(pattern_str, text, re.IGNORECASE):
                fact = m.group().strip()

                # 질문은 사실이 아님
                if fact.endswith("?") or fact.endswith("뭐지") or fact.endswith("뭐야"):
                    continue

                # 키워드만 있는 매치 제거
                if fact.lower() in _noise or len(fact) < 4:
                    continue

                # 중복 제거
                if fact in seen:
                    continue
                seen.add(fact)
                facts.append(fact)
        return facts

    def get_pattern_info(self) -> list[dict[str, Any]]:  # [JS-B004.7]
        """현재 로드된 패턴 정보를 반환합니다."""
        return [{"name": name, "description": desc} for name, _, desc in self._compiled]

    def reload_from_yaml(self, path: Path) -> None:  # [JS-B004.8]
        """YAML 파일에서 패턴을 다시 로드합니다."""
        if not path.exists():
            logger.warning("signal_reload_file_not_found", path=str(path))
            return

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data and "patterns" in data:
            self._raw_patterns = data["patterns"]
            self._compile_patterns()
            logger.info("signal_patterns_reloaded", count=len(self._compiled))


def create_default_patterns_yaml(path: Path) -> None:  # [JS-B004.9]
    """기본 패턴 YAML 파일을 생성합니다.

    Args:
        path: 생성할 YAML 파일 경로
    """
    data = {
        "version": 1,
        "patterns": DEFAULT_PATTERNS,
        "not_encrypted": ["이름", "이메일", "전화번호", "주소"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("default_patterns_yaml_created", path=str(path))
