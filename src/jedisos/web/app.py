"""
[JS-W001] jedisos.web.app
FastAPI 메인 애플리케이션 + 라우터 등록

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115, uvicorn>=0.34
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jedisos import __version__

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()

# 웹 디렉토리 경로
_WEB_DIR = Path(__file__).parent

# Jinja2 템플릿 엔진
_templates = Jinja2Templates(directory=str(_WEB_DIR / "templates"))

# 앱 상태 (lifespan에서 초기화)
_app_state: dict[str, Any] = {}

# 백그라운드 태스크 참조 (GC 방지)
_background_tasks: set[asyncio.Task[None]] = set()


def _load_env_from_data_dir() -> None:  # [JS-W001.7]
    """JEDISOS_DATA_DIR/.env에서 환경변수를 로드합니다 (이미 설정된 것은 덮어쓰지 않음)."""
    data_dir = Path(os.environ.get("JEDISOS_DATA_DIR", "."))
    env_path = data_dir / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value and key not in os.environ:
            os.environ[key] = value
            logger.debug("env_loaded_from_data", key=key)


async def _start_channels() -> None:  # [JS-W001.8]
    """설정된 채널 봇을 백그라운드로 시작합니다."""
    from jedisos.agents.react import ReActAgent
    from jedisos.llm.prompts import JEDISOS_IDENTITY

    memory = _app_state.get("memory")
    llm = _app_state.get("llm")
    pdp = _app_state.get("pdp")
    audit = _app_state.get("audit")
    builtin_tools = _app_state.get("builtin_tools", [])
    tool_executor = _app_state.get("tool_executor")

    if not memory or not llm:
        return

    agent = ReActAgent(
        memory=memory,
        llm=llm,
        tools=builtin_tools,
        tool_executor=tool_executor,
        identity_prompt=JEDISOS_IDENTITY,
    )

    # Telegram
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if telegram_token and "telegram_app" not in _app_state:
        try:
            from jedisos.channels.telegram import TelegramChannel

            tg = TelegramChannel(token=telegram_token, agent=agent, pdp=pdp, audit=audit)
            tg_app = tg.build_app()
            await tg_app.initialize()
            await tg_app.start()
            if tg_app.updater:
                await tg_app.updater.start_polling(drop_pending_updates=True)
            _app_state["telegram_app"] = tg_app
            logger.info("telegram_bot_started")
        except Exception as e:
            logger.error("telegram_bot_start_failed", error=str(e))

    # Discord (채널 모듈 구현 후 활성화)
    discord_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if discord_token:
        logger.info("discord_token_found_but_channel_not_implemented")

    # Slack (채널 모듈 구현 후 활성화)
    slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    if slack_bot_token:
        logger.info("slack_token_found_but_channel_not_implemented")


class ToolDef:  # [JS-W001.11]
    """OpenAI function calling 형식 도구 래퍼."""

    def __init__(self, definition: dict) -> None:
        self._def = definition

    def to_dict(self) -> dict:
        return self._def


def _skill_func_to_openai_def(func: Any) -> dict[str, Any]:  # [JS-W001.12]
    """@tool 데코레이터 함수를 OpenAI function calling 형식으로 변환합니다."""
    name = getattr(func, "_tool_name", func.__name__)
    description = getattr(func, "_tool_description", func.__doc__ or "")
    params = getattr(func, "_tool_parameters", {})

    # OpenAI에서 허용하는 JSON Schema 타입
    valid_types = {"string", "integer", "number", "boolean", "array", "object"}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for pname, pinfo in params.items():
        ptype = pinfo.get("type", "string")

        # Python 타입 표현을 JSON Schema로 변환
        if not isinstance(ptype, str):
            ptype = "string"
        elif ptype not in valid_types:
            # "str | None", "Optional[str]", "list[str]", etc → 기본 타입으로 매핑
            ptype_lower = ptype.lower().replace(" ", "")
            if "int" in ptype_lower:
                ptype = "integer"
            elif "float" in ptype_lower or "number" in ptype_lower:
                ptype = "number"
            elif "bool" in ptype_lower:
                ptype = "boolean"
            elif "list" in ptype_lower or "array" in ptype_lower:
                ptype = "array"
            elif "dict" in ptype_lower or "object" in ptype_lower:
                ptype = "object"
            else:
                ptype = "string"

        properties[pname] = {"type": ptype, "description": pname}
        if pinfo.get("required"):
            required.append(pname)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description[:1024],
            "parameters": {
                "type": "object",
                "properties": properties,
                **({"required": required} if required else {}),
            },
        },
    }


def _register_builtin_tools(  # [JS-W001.10]
    memory: Any,
    llm: Any,
) -> tuple[list[Any], Any]:
    """내장 도구 + 생성된 Skill을 등록합니다.

    Returns:
        (tool_definitions, tool_executor) 튜플
    """
    from pathlib import Path as _Path

    from jedisos.forge.generator import SkillGenerator
    from jedisos.forge.loader import ToolLoader

    data_dir = _Path(os.environ.get("JEDISOS_DATA_DIR", "."))
    generated_dir = data_dir / "tools" / "generated"
    generator = SkillGenerator(output_dir=generated_dir, memory=memory)

    # 동적 스킬 레지스트리: name → callable
    skill_registry: dict[str, Any] = {}

    # 기존 생성된 스킬 로드
    loader = ToolLoader(tools_dir=data_dir / "tools")
    _load_generated_skills(loader, generated_dir, skill_registry)

    # 내장 도구 정의 (OpenAI function calling)
    builtin_defs = [
        {
            "type": "function",
            "function": {
                "name": "recall_memory",
                "description": "사용자에 대한 장기 기억을 검색합니다. 사용자의 이름, 선호도, 이전 대화에서 언급한 내용 등을 기억해낼 때 사용합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "검색할 내용 (예: '사용자 이름', '좋아하는 음식')",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "retain_memory",
                "description": "중요한 정보를 장기 기억에 저장합니다. 사용자의 이름, 선호도, 중요한 사실 등을 기억해둘 때 사용합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "저장할 내용"},
                    },
                    "required": ["content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_skill",
                "description": "새로운 도구/스킬을 자동 생성합니다. 사용자가 새 기능을 요청할 때 한 번만 호출하세요. 이미 생성 중이면 중복 호출하지 마세요. 생성은 백그라운드에서 진행되며 완료 시 알림이 갑니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "만들 도구에 대한 설명 (예: '현재 날씨를 조회하는 도구')",
                        },
                    },
                    "required": ["description"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_skills",
                "description": "현재 설치된 스킬(도구) 목록을 조회합니다. 스킬 이름, 설명, 활성 상태를 확인할 수 있습니다.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_skill",
                "description": "설치된 스킬을 삭제합니다. 자동 생성된 스킬만 삭제 가능합니다. 삭제 전 반드시 사용자에게 확인을 받으세요.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "삭제할 스킬 이름"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "upgrade_skill",
                "description": "기존 스킬을 개선하거나 버그를 수정합니다. 기존 코드를 기반으로 새 버전을 생성합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "개선할 스킬 이름"},
                        "instructions": {
                            "type": "string",
                            "description": "개선/수정 지시사항 (예: '에러 처리 추가', '응답 형식 변경')",
                        },
                    },
                    "required": ["name", "instructions"],
                },
            },
        },
    ]

    # 생성된 스킬의 OpenAI 정의 추가
    skill_defs = [_skill_func_to_openai_def(func) for func in skill_registry.values()]

    all_defs = builtin_defs + skill_defs
    wrapped_tools = [ToolDef(td) for td in all_defs]

    # 도구 실행기
    async def tool_executor(name: str, arguments: dict) -> Any:
        if name == "recall_memory":
            query = arguments.get("query", "")
            try:
                result = await memory.recall(query)
                return {"memories": str(result)}
            except Exception as e:
                return {"error": str(e)}

        elif name == "retain_memory":
            content = arguments.get("content", "")
            try:
                await memory.retain(content)
                return {"status": "saved", "content": content}
            except Exception as e:
                return {"error": str(e)}

        elif name == "create_skill":
            description = arguments.get("description", "")

            # 중복 생성 방지: 이미 생성 중인 스킬이 있으면 거절
            if _app_state.get("_skill_generating"):
                logger.warning("skill_creation_blocked_duplicate", description=description)
                return {
                    "status": "already_generating",
                    "message": "이미 스킬을 생성 중입니다. 완료된 후 다시 시도해 주세요.",
                }

            _app_state["_skill_generating"] = True

            max_outer_retries = 2

            async def _bg_create_skill() -> None:
                """백그라운드에서 스킬을 생성하고 완료/실패를 모든 채널에 알립니다.

                generator.generate() 내부에 3회 재시도가 있고,
                그래도 예외가 발생하면 외부에서 1회 더 재시도합니다.
                """
                try:
                    last_outer_error = ""
                    for outer_attempt in range(1, max_outer_retries + 1):
                        try:
                            if outer_attempt > 1:
                                await _broadcast_notification(
                                    "skill_retry",
                                    f"스킬 생성 재시도 중... (시도 {outer_attempt}/{max_outer_retries})\n"
                                    f"이전 오류: {last_outer_error}",
                                )

                            result = await generator.generate(description)
                            if result.success:
                                for tool_func in result.tools:
                                    tname = getattr(tool_func, "_tool_name", "")
                                    if tname:
                                        skill_registry[tname] = tool_func
                                        new_def = _skill_func_to_openai_def(tool_func)
                                        wrapped_tools.append(ToolDef(new_def))
                                        logger.info("skill_hotloaded", name=tname)
                                _app_state.pop("_cached_agent", None)
                                from jedisos.web.api.chat import clear_all_history

                                clear_all_history()
                                logger.info(
                                    "skill_created_bg",
                                    tool_name=result.tool_name,
                                    tools_count=len(result.tools),
                                )
                                tool_func = result.tools[0] if result.tools else None
                                desc = (
                                    getattr(tool_func, "_tool_description", "") if tool_func else ""
                                )

                                msg = (
                                    f"'{result.tool_name}' 스킬이 생성되었습니다!\n"
                                    f"{desc}\n"
                                    f"이제 대화에서 자연스럽게 물어보시면 됩니다."
                                )
                                await _broadcast_notification("skill_created", msg)
                                return  # 성공 → 종료
                            else:
                                last_outer_error = "내부 재시도 3회 모두 실패"
                                logger.warning(
                                    "skill_creation_failed_bg",
                                    description=description,
                                    outer_attempt=outer_attempt,
                                )
                                if outer_attempt < max_outer_retries:
                                    continue  # 외부 재시도
                                msg = (
                                    f"'{description}' 스킬 생성에 실패했습니다. "
                                    f"다른 표현으로 다시 시도해 주세요."
                                )
                                await _broadcast_notification("skill_failed", msg)
                        except Exception as e:
                            last_outer_error = f"{type(e).__name__}: {e}"
                            logger.error(
                                "skill_creation_error_bg",
                                error=str(e),
                                outer_attempt=outer_attempt,
                            )
                            if outer_attempt < max_outer_retries:
                                continue  # 외부 재시도
                            msg = f"스킬 생성 중 오류가 발생했습니다: {e}"
                            await _broadcast_notification("skill_error", msg)
                finally:
                    _app_state["_skill_generating"] = False

            task = asyncio.create_task(_bg_create_skill())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

            return {
                "status": "generating",
                "message": f"'{description}' 스킬을 백그라운드에서 생성 중입니다. 잠시 후 사용 가능합니다.",
            }

        elif name == "list_skills":
            from jedisos.web.api.skills import _scan_skills

            skills = _scan_skills()
            summary = [
                {
                    "name": s["name"],
                    "description": s["description"],
                    "enabled": s["enabled"],
                    "version": s.get("version", ""),
                }
                for s in skills
            ]
            return {"skills": summary, "total": len(summary)}

        elif name == "delete_skill":
            import re as _re
            import shutil

            from jedisos.web.api.chat import clear_all_history
            from jedisos.web.api.skills import _scan_skills

            skill_name = arguments.get("name", "")
            if not skill_name:
                return {"error": "스킬 이름을 지정해주세요."}

            skills = _scan_skills()
            skill = next((s for s in skills if s["name"] == skill_name), None)
            if not skill:
                return {"error": f"'{skill_name}' 스킬을 찾을 수 없습니다."}

            if not skill.get("auto_generated"):
                return {"error": "수동으로 설치한 스킬은 삭제할 수 없습니다."}

            # 경로 검증 (traversal 방지)
            skill_path = Path(skill["path"]).resolve()
            if not _re.match(r"^[a-zA-Z0-9_\-]+$", skill_name):
                return {"error": "잘못된 스킬 이름 형식입니다."}

            data_dir = Path(os.environ.get("JEDISOS_DATA_DIR", "."))
            allowed_dirs = [
                (Path("tools") / "generated").resolve(),
                (data_dir / "tools" / "generated").resolve(),
            ]
            if not any(str(skill_path).startswith(str(d)) for d in allowed_dirs):
                logger.warning("skill_delete_path_blocked", name=skill_name, path=str(skill_path))
                return {"error": "허용되지 않은 경로입니다."}

            if not skill_path.exists():
                return {"error": "스킬 디렉토리를 찾을 수 없습니다."}

            # 파일 삭제
            description = skill.get("description", "")
            shutil.rmtree(skill_path)
            logger.info("skill_deleted_by_agent", name=skill_name)

            # 레지스트리에서 제거
            skill_registry.pop(skill_name, None)
            wrapped_tools[:] = [
                t
                for t in wrapped_tools
                if t.to_dict().get("function", {}).get("name") != skill_name
            ]

            # 캐시 무효화
            _app_state.pop("_cached_agent", None)
            clear_all_history()

            # Hindsight에 삭제 기록
            try:
                await generator.retain_skill_deletion(tool_name=skill_name, description=description)
            except Exception as e:
                logger.warning("skill_deletion_record_failed", error=str(e))

            return {"status": "deleted", "name": skill_name}

        elif name == "upgrade_skill":
            skill_name = arguments.get("name", "")
            instructions = arguments.get("instructions", "")

            if not skill_name or not instructions:
                return {"error": "스킬 이름과 수정 지시사항을 모두 입력해주세요."}

            # 중복 방지
            if _app_state.get("_skill_generating"):
                return {
                    "status": "already_generating",
                    "message": "이미 스킬을 생성/업그레이드 중입니다. 완료된 후 다시 시도해 주세요.",
                }

            # 기존 스킬 찾기
            from jedisos.web.api.skills import _scan_skills

            skills = _scan_skills()
            skill = next((s for s in skills if s["name"] == skill_name), None)
            if not skill:
                return {"error": f"'{skill_name}' 스킬을 찾을 수 없습니다."}

            # 기존 코드 읽기
            skill_path = Path(skill["path"])
            tool_py = skill_path / "tool.py"
            if not tool_py.exists():
                return {"error": f"'{skill_name}' 스킬의 코드를 찾을 수 없습니다."}

            existing_code = tool_py.read_text()

            _app_state["_skill_generating"] = True

            async def _bg_upgrade_skill() -> None:
                """백그라운드에서 스킬을 업그레이드합니다."""
                try:
                    upgrade_desc = (
                        f"[기존 스킬 '{skill_name}' 업그레이드]\n"
                        f"기존 코드:\n{existing_code}\n\n"
                        f"수정 지시:\n{instructions}\n\n"
                        f"중요: tool_name은 반드시 '{skill_name}'을 유지하세요."
                    )
                    result = await generator.generate(upgrade_desc)
                    if result.success:
                        # 레지스트리 업데이트
                        for tool_func in result.tools:
                            tname = getattr(tool_func, "_tool_name", "")
                            if tname:
                                skill_registry[tname] = tool_func
                                new_def = _skill_func_to_openai_def(tool_func)
                                # 기존 정의 교체
                                wrapped_tools[:] = [
                                    t
                                    for t in wrapped_tools
                                    if t.to_dict().get("function", {}).get("name") != tname
                                ]
                                wrapped_tools.append(ToolDef(new_def))
                                logger.info("skill_upgraded", name=tname)

                        _app_state.pop("_cached_agent", None)
                        from jedisos.web.api.chat import clear_all_history

                        clear_all_history()

                        msg = f"'{result.tool_name}' 스킬이 업그레이드되었습니다! 대화에서 바로 사용해보세요."
                        await _broadcast_notification("skill_upgraded", msg)
                    else:
                        msg = f"'{skill_name}' 스킬 업그레이드에 실패했습니다."
                        await _broadcast_notification("skill_failed", msg)
                except Exception as e:
                    logger.error("skill_upgrade_error", error=str(e))
                    msg = f"스킬 업그레이드 중 오류가 발생했습니다: {e}"
                    await _broadcast_notification("skill_error", msg)
                finally:
                    _app_state["_skill_generating"] = False

            task = asyncio.create_task(_bg_upgrade_skill())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

            return {
                "status": "upgrading",
                "message": f"'{skill_name}' 스킬을 업그레이드 중입니다. 잠시 후 완료됩니다.",
            }

        # 동적 스킬 실행
        elif name in skill_registry:
            try:
                func = skill_registry[name]
                return await func(**arguments)
            except Exception as e:
                logger.error("skill_execution_failed", skill=name, error=str(e))
                return {"error": f"스킬 실행 오류: {e}"}

        return {"error": f"알 수 없는 도구: {name}"}

    # 레지스트리를 app_state에 저장 (외부 접근용)
    _app_state["skill_registry"] = skill_registry

    logger.info(
        "tools_registered",
        builtin=len(builtin_defs),
        skills=len(skill_defs),
        total=len(all_defs),
    )
    return wrapped_tools, tool_executor


def _load_generated_skills(  # [JS-W001.13]
    loader: Any,
    generated_dir: Path,
    registry: dict[str, Any],
) -> None:
    """generated/ 디렉토리의 스킬을 로드하여 레지스트리에 등록합니다."""
    if not generated_dir.exists():
        return

    for skill_dir in sorted(generated_dir.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "tool.py").exists():
            continue
        # .disabled 마커가 있으면 스킵
        if (skill_dir / ".disabled").exists():
            continue
        try:
            tools = loader.load_tool(skill_dir)
            for func in tools:
                tool_name = getattr(func, "_tool_name", "")
                if tool_name:
                    registry[tool_name] = func
                    logger.info("generated_skill_loaded", name=tool_name, dir=str(skill_dir))
        except Exception as e:
            logger.warning("generated_skill_load_failed", dir=str(skill_dir), error=str(e))


async def _broadcast_notification(event: str, message: str) -> None:  # [JS-W001.14]
    """모든 연결된 채널(WebSocket + 텔레그램 + 디스코드 + 슬랙)에 알림을 전송합니다."""
    # 1) WebSocket 클라이언트
    try:
        import contextlib

        from jedisos.web.api.chat import manager as ws_manager

        payload = {"type": "notification", "event": event, "message": message}
        for conn in list(ws_manager.active_connections):
            with contextlib.suppress(Exception):
                await conn.send_json(payload)
    except Exception:
        pass

    # 2) 텔레그램 — 최근 대화한 사용자에게 알림
    tg_app = _app_state.get("telegram_app")
    if tg_app and hasattr(tg_app, "bot"):
        from jedisos.channels.telegram import _md_to_telegram_html, _telegram_history

        for chat_id in list(_telegram_history.keys()):
            try:
                await tg_app.bot.send_message(
                    chat_id=int(chat_id),
                    text=_md_to_telegram_html(message),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.debug("telegram_notify_failed", chat_id=chat_id, error=str(e))


async def _stop_channels() -> None:  # [JS-W001.9]
    """실행 중인 채널 봇을 중지합니다."""
    # Telegram 정리
    tg_app = _app_state.get("telegram_app")
    if tg_app:
        try:
            if tg_app.updater and tg_app.updater.running:
                await tg_app.updater.stop()
            if tg_app.running:
                await tg_app.stop()
            await tg_app.shutdown()
            logger.info("telegram_bot_stopped")
        except Exception as e:
            logger.warning("telegram_bot_stop_error", error=str(e))

    # Discord/Slack 태스크 정리
    for key in ("discord_task", "slack_task"):
        task = _app_state.get(key)
        if task and not task.done():
            task.cancel()
            logger.info("channel_task_cancelled", channel=key)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # [JS-W001.1]
    """앱 시작/종료 시 리소스를 관리합니다."""
    logger.info("web_app_starting", version=__version__)

    # data dir의 .env에서 환경변수 로드 (Setup Wizard 저장값)
    _load_env_from_data_dir()

    # 시작 시 초기화
    from jedisos.core.config import JedisosConfig, LLMConfig, MemoryConfig, SecurityConfig
    from jedisos.llm.router import LLMRouter
    from jedisos.memory.zvec_memory import ZvecMemory
    from jedisos.security.audit import AuditLogger
    from jedisos.security.pdp import PolicyDecisionPoint
    from jedisos.security.secvault_client import SecVaultClient
    from jedisos.security.secvault_daemon import start_daemon, stop_daemon

    config = JedisosConfig()
    memory = ZvecMemory(MemoryConfig())
    llm = LLMRouter(LLMConfig())
    pdp = PolicyDecisionPoint(SecurityConfig())
    audit = AuditLogger()

    # SecVault 데몬 시작
    data_dir = Path(os.environ.get("JEDISOS_DATA_DIR", memory.config.data_dir))
    secvault_dir = data_dir / ".secvault"
    vault_process = start_daemon(secvault_dir)
    _app_state["vault_process"] = vault_process

    # SecVault 클라이언트 연결 (데몬 소켓 대기)
    vault_client = SecVaultClient(secvault_dir)
    _app_state["vault_client"] = vault_client

    # 메모리에 SecVault 클라이언트 연결
    memory.set_vault_client(vault_client)

    # SecVault 상태 확인 (소켓 준비 대기)
    for _retry in range(20):
        try:
            vault_status = await vault_client.status()
            _app_state["vault_status"] = vault_status.get("status", "unknown")
            logger.info("secvault_status", vault_status=vault_status)
            break
        except ConnectionError:
            await asyncio.sleep(0.2)
    else:
        _app_state["vault_status"] = "unavailable"
        logger.warning("secvault_daemon_not_ready")

    # 스킬 공유 컨텍스트 초기화 (LLM + 메모리를 스킬에서 사용 가능하게)
    from jedisos.forge.context import initialize as init_skill_context

    init_skill_context(llm_router=llm, memory=memory)

    _app_state["config"] = config
    _app_state["memory"] = memory
    _app_state["llm"] = llm
    _app_state["pdp"] = pdp
    _app_state["audit"] = audit

    # 내장 도구 등록 (ZvecMemory + Forge 스킬 생성)
    builtin_tools, tool_executor = _register_builtin_tools(memory, llm)
    _app_state["builtin_tools"] = builtin_tools
    _app_state["tool_executor"] = tool_executor

    # 채널 봇 시작 (토큰이 있는 경우만)
    await _start_channels()

    logger.info("web_app_ready")
    yield

    # 종료 시 채널 봇 정리
    await _stop_channels()

    # SecVault 데몬 종료
    vault_proc = _app_state.get("vault_process")
    if vault_proc:
        stop_daemon(vault_proc)

    _app_state.clear()
    logger.info("web_app_shutdown")


def get_app_state() -> dict[str, Any]:  # [JS-W001.2]
    """앱 공유 상태를 반환합니다."""
    return _app_state


def create_app() -> FastAPI:  # [JS-W001.3]
    """FastAPI 앱을 생성하고 라우터를 등록합니다."""
    app = FastAPI(
        title="JediSOS",
        description="AI Agent System with zvecsearch Memory",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS 설정 (로컬 개발용)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 등록
    from jedisos.web.api.chat import router as chat_router
    from jedisos.web.api.mcp import router as mcp_router
    from jedisos.web.api.monitoring import router as monitoring_router
    from jedisos.web.api.settings import router as settings_router
    from jedisos.web.api.skills import router as skills_router
    from jedisos.web.setup_wizard import router as wizard_router

    app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
    app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
    app.include_router(mcp_router, prefix="/api/mcp", tags=["mcp"])
    app.include_router(skills_router, prefix="/api/skills", tags=["skills"])
    app.include_router(monitoring_router, prefix="/api/monitoring", tags=["monitoring"])
    app.include_router(wizard_router, prefix="/api/setup", tags=["setup"])

    @app.get("/", response_class=HTMLResponse)
    async def serve_index(request: Request) -> HTMLResponse:  # [JS-W001.6]
        """메인 웹 UI를 렌더링합니다."""
        return _templates.TemplateResponse(request, "index.html", {"version": __version__})

    @app.get("/health")
    async def health_check() -> JSONResponse:  # [JS-W001.4]
        """헬스 체크 엔드포인트."""
        return JSONResponse({"status": "ok", "version": __version__})

    # 정적 파일 서빙 (/api/* 라우터보다 뒤에 마운트하여 API 경로 우선)
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR / "static")), name="static")

    logger.info("web_app_created")
    return app


def run_server(host: str = "0.0.0.0", port: int = 8866) -> None:  # [JS-W001.5]  # nosec B104
    """uvicorn으로 서버를 실행합니다."""
    import uvicorn

    logger.info("web_server_starting", host=host, port=port)
    uvicorn.run(
        "jedisos.web.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level="info",
    )
