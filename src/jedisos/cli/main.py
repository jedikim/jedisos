"""
[JS-H001] jedisos.cli.main
Typer CLI 엔트리포인트 - JediSOS 커맨드라인 인터페이스

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: typer>=0.23.1, rich>=14.3.2
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import structlog
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from jedisos import __version__

logger = structlog.get_logger()

app = typer.Typer(
    name="jedisos",
    help="JediSOS - AI Agent System with Hindsight Memory",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()
err_console = Console(stderr=True)


def version_callback(value: bool) -> None:  # [JS-H001.1]
    """버전 정보를 출력합니다."""
    if value:
        console.print(f"JediSOS v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", "-V", help="버전 정보 출력", callback=version_callback, is_eager=True
        ),
    ] = None,
) -> None:
    """JediSOS - Hindsight Memory + LangGraph + LiteLLM 기반 AI 비서."""


@app.command()  # [JS-H001.2]
def chat(
    message: Annotated[str, typer.Argument(help="AI에게 보낼 메시지")],
    bank_id: Annotated[str, typer.Option("--bank", "-b", help="메모리 뱅크 ID")] = "cli-default",
    model: Annotated[str | None, typer.Option("--model", "-m", help="사용할 LLM 모델")] = None,
) -> None:
    """AI 에이전트에게 메시지를 보냅니다.

    예시: jedisos chat "오늘 날씨 알려줘"
    """
    try:
        response = asyncio.run(_run_chat(message, bank_id, model))
        console.print(Panel(response, title="JediSOS", border_style="green"))
    except KeyboardInterrupt:
        err_console.print("\n중단됨.", style="yellow")
        raise typer.Exit(1) from None
    except Exception as e:
        err_console.print(f"오류: {e}", style="red")
        raise typer.Exit(1) from e


async def _run_chat(message: str, bank_id: str, model: str | None) -> str:  # [JS-H001.3]
    """chat 명령의 비동기 실행부."""
    from jedisos.core.config import HindsightConfig, LLMConfig
    from jedisos.llm.router import LLMRouter
    from jedisos.memory.hindsight import HindsightMemory

    memory = HindsightMemory(HindsightConfig())

    llm_config = LLMConfig()
    if model:
        llm_config = LLMConfig(models=[model, *llm_config.models])

    llm = LLMRouter(llm_config)

    from jedisos.agents.react import ReActAgent

    agent = ReActAgent(memory=memory, llm=llm)
    return await agent.run(message, bank_id=bank_id)


@app.command()  # [JS-H001.4]
def health(
    url: Annotated[
        str, typer.Option("--url", "-u", help="Hindsight API URL")
    ] = "http://localhost:8888",
) -> None:
    """시스템 헬스 체크를 실행합니다."""
    import httpx

    table = Table(title="JediSOS Health Check")
    table.add_column("서비스", style="cyan")
    table.add_column("상태", style="bold")
    table.add_column("URL")

    # JediSOS 버전
    table.add_row("JediSOS", f"v{__version__}", "-")

    # Hindsight 체크
    try:
        resp = httpx.get(f"{url}/health", timeout=5)
        if resp.status_code == 200:
            table.add_row("Hindsight", "[green]OK[/green]", url)
        else:
            table.add_row("Hindsight", f"[yellow]HTTP {resp.status_code}[/yellow]", url)
    except httpx.ConnectError:
        table.add_row("Hindsight", "[red]OFFLINE[/red]", url)
    except Exception as e:
        table.add_row("Hindsight", f"[red]ERROR: {e}[/red]", url)

    # Python 버전
    table.add_row(
        "Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "-"
    )

    console.print(table)


@app.command()  # [JS-H001.5]
def init(
    directory: Annotated[Path, typer.Option("--dir", "-d", help="설정 디렉토리")] = Path("."),
) -> None:
    """JediSOS 프로젝트를 초기화합니다.

    .env 파일과 기본 설정을 생성합니다.
    """
    env_path = directory / ".env"
    config_dir = directory / "config"

    if env_path.exists():
        overwrite = typer.confirm(f"{env_path} 파일이 이미 존재합니다. 덮어쓸까요?", default=False)
        if not overwrite:
            console.print("초기화를 취소합니다.", style="yellow")
            raise typer.Exit()

    # .env 생성
    env_content = """# JediSOS 환경변수
# API 키 설정
OPENAI_API_KEY=
GOOGLE_API_KEY=

# Hindsight 설정
HINDSIGHT_API_URL=http://localhost:8888

# 보안 설정
SECURITY_MAX_REQUESTS_PER_MINUTE=30

# 디버그 모드
DEBUG=false
LOG_LEVEL=INFO
"""
    env_path.write_text(env_content)
    console.print(f"[green]{env_path}[/green] 생성 완료")

    # config 디렉토리 + llm_config.yaml
    config_dir.mkdir(exist_ok=True)
    llm_config_path = config_dir / "llm_config.yaml"
    if not llm_config_path.exists():
        llm_config_content = """# JediSOS LLM 설정
models:
  - gpt-5.2
  - gemini/gemini-3-flash

temperature: 0.7
max_tokens: 8192
timeout: 60
"""
        llm_config_path.write_text(llm_config_content)
        console.print(f"[green]{llm_config_path}[/green] 생성 완료")

    console.print()
    console.print(
        Panel(
            "[bold]초기화 완료![/bold]\n\n"
            "1. .env 파일에 API 키를 설정하세요\n"
            "2. docker compose up -d 로 인프라를 시작하세요\n"
            "3. jedisos health 로 상태를 확인하세요\n"
            "4. jedisos chat '안녕' 으로 AI와 대화하세요",
            title="JediSOS",
            border_style="green",
        )
    )


@app.command()  # [JS-H001.6]
def serve(
    host: Annotated[str, typer.Option("--host", "-h", help="바인딩 호스트")] = "0.0.0.0",  # nosec B104
    port: Annotated[int, typer.Option("--port", "-p", help="포트")] = 8080,
) -> None:
    """JediSOS 서버를 실행합니다. (웹 UI + API)

    Phase 9 (Web UI) 구현 후 활성화됩니다.
    """
    console.print(
        Panel(
            f"JediSOS 서버가 [bold]{host}:{port}[/bold]에서 시작됩니다.\n"
            "웹 UI는 Phase 9에서 구현 예정입니다.",
            title="JediSOS Server",
            border_style="blue",
        )
    )
    logger.info("server_start_requested", host=host, port=port)
    # Phase 9에서 FastAPI 앱 실행 추가 예정
    console.print("[yellow]웹 서버는 Phase 9에서 구현됩니다.[/yellow]")


@app.command()  # [JS-H001.7]
def update() -> None:
    """JediSOS를 최신 버전으로 업데이트합니다."""
    import subprocess  # nosec B404

    console.print("JediSOS 업데이트를 확인합니다...", style="cyan")

    # docker compose pull 시도
    try:
        result = subprocess.run(  # nosec B603 B607
            ["docker", "compose", "pull"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode == 0:
            console.print("[green]Docker 이미지 업데이트 완료[/green]")
            # restart
            restart = typer.confirm("서비스를 재시작할까요?", default=True)
            if restart:
                subprocess.run(  # nosec B603 B607
                    ["docker", "compose", "up", "-d"],
                    timeout=60,
                    check=False,
                )
                console.print("[green]서비스 재시작 완료[/green]")
        else:
            console.print(
                "[yellow]Docker Compose가 없거나 실행할 수 없습니다.[/yellow]\n"
                "수동 업데이트: pip install --upgrade jedisos",
            )
    except FileNotFoundError:
        console.print(
            "[yellow]Docker가 설치되어 있지 않습니다.[/yellow]\n"
            "수동 업데이트: pip install --upgrade jedisos",
        )
    except subprocess.TimeoutExpired as e:
        err_console.print("[red]업데이트 시간 초과[/red]", style="red")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
