"""
[JS-A002] jedisos.core.config
pydantic-settings 기반 환경변수 설정 관리

version: 1.0.0
created: 2026-02-16
modified: 2026-02-16
dependencies: pydantic-settings>=2.13
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HindsightConfig(BaseSettings):  # [JS-A002.1]
    """Hindsight 메모리 서버 설정."""

    model_config = SettingsConfigDict(env_prefix="HINDSIGHT_")

    api_url: str = Field(default="http://localhost:8888", description="Hindsight API URL")
    bank_id: str = Field(default="jedisos-default", description="기본 메모리 뱅크 ID")
    api_llm_provider: str = Field(default="openai", description="Hindsight LLM 프로바이더")
    api_llm_api_key: str = Field(default="", description="Hindsight LLM API 키")


class LLMConfig(BaseSettings):  # [JS-A002.2]
    """LiteLLM 라우터 설정.

    모델 폴백 체인은 models 리스트로 자유롭게 설정 가능.
    llm_config.yaml 파일로도 설정 가능 (환경변수보다 우선).
    """

    model_config = SettingsConfigDict(env_prefix="LLM_")

    models: list[str] = Field(
        default=[
            "gpt-5.2",
            "gemini/gemini-3-flash",
        ],
        description="폴백 순서대로 나열. 첫 번째가 1차 모델",
    )
    config_file: str = Field(default="llm_config.yaml", description="YAML 설정 파일 경로")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, ge=1)
    timeout: int = Field(default=60, description="초 단위")


class SecurityConfig(BaseSettings):  # [JS-A002.3]
    """보안 설정."""

    model_config = SettingsConfigDict(env_prefix="SECURITY_")

    max_requests_per_minute: int = Field(default=30)
    allowed_tools: list[str] = Field(default_factory=list, description="빈 리스트 = 모두 허용")
    blocked_tools: list[str] = Field(default_factory=lambda: ["shell_exec", "file_delete"])


class JedisosConfig(BaseSettings):  # [JS-A002.4]
    """JediSOS 메인 설정. 모든 하위 설정을 포함."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    hindsight: HindsightConfig = Field(default_factory=HindsightConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
