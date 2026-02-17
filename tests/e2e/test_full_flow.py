"""
[JS-T010] tests.e2e.test_full_flow
CLI + 전체 플로우 E2E 테스트

version: 1.0.0
created: 2026-02-18
note: CLI 명령어는 mock 없이 실제 Typer CLI를 테스트
"""

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from jedisos import __version__
from jedisos.cli.main import app

runner = CliRunner()


class TestCLIVersion:  # [JS-T010.1]
    """버전 출력 테스트."""

    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_version_short_flag(self):
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestCLIHelp:  # [JS-T010.2]
    """도움말 테스트."""

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "JediSOS" in result.output

    def test_chat_help(self):
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "메시지" in result.output

    def test_health_help(self):
        result = runner.invoke(app, ["health", "--help"])
        assert result.exit_code == 0

    def test_init_help(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0

    def test_serve_help(self):
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0

    def test_update_help(self):
        result = runner.invoke(app, ["update", "--help"])
        assert result.exit_code == 0

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        # no_args_is_help=True returns exit_code 0 with Typer
        assert "JediSOS" in result.output or "Usage" in result.output


class TestCLIHealth:  # [JS-T010.3]
    """헬스 체크 테스트."""

    def test_health_offline(self):
        """Hindsight가 오프라인이면 OFFLINE 표시."""
        result = runner.invoke(app, ["health", "--url", "http://localhost:19999"])
        assert result.exit_code == 0
        assert "OFFLINE" in result.output or "ERROR" in result.output

    def test_health_shows_version(self):
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_health_shows_python(self):
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "Python" in result.output


class TestCLIInit:  # [JS-T010.4]
    """초기화 테스트."""

    def test_init_creates_env_file(self, tmp_path):
        result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".env").exists()
        assert "OPENAI_API_KEY" in (tmp_path / ".env").read_text()

    def test_init_creates_config_dir(self, tmp_path):
        result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "config").is_dir()
        assert (tmp_path / "config" / "llm_config.yaml").exists()

    def test_init_skip_existing(self, tmp_path):
        """기존 .env가 있으면 덮어쓰기 확인."""
        (tmp_path / ".env").write_text("existing")
        result = runner.invoke(app, ["init", "--dir", str(tmp_path)], input="n\n")
        assert result.exit_code == 0
        assert (tmp_path / ".env").read_text() == "existing"

    def test_init_overwrite_existing(self, tmp_path):
        """기존 .env를 덮어쓰기."""
        (tmp_path / ".env").write_text("existing")
        result = runner.invoke(app, ["init", "--dir", str(tmp_path)], input="y\n")
        assert result.exit_code == 0
        assert "OPENAI_API_KEY" in (tmp_path / ".env").read_text()


class TestCLIChat:  # [JS-T010.5]
    """채팅 명령 테스트."""

    def test_chat_success(self):
        """정상 채팅 플로우 (agent.run mock)."""
        mock_resp = MagicMock()
        mock_resp.model_dump.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "안녕하세요!"}}],
            "model": "gpt-5.2",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        with (
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
            patch(
                "jedisos.memory.hindsight.HindsightMemory.recall",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "jedisos.memory.hindsight.HindsightMemory.retain",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            result = runner.invoke(app, ["chat", "안녕"])
            assert result.exit_code == 0
            assert "안녕하세요!" in result.output

    def test_chat_with_bank_id(self):
        """bank_id 옵션 테스트."""
        mock_resp = MagicMock()
        mock_resp.model_dump.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "답변"}}],
            "model": "gpt-5.2",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        with (
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
            patch(
                "jedisos.memory.hindsight.HindsightMemory.recall",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "jedisos.memory.hindsight.HindsightMemory.retain",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            result = runner.invoke(app, ["chat", "--bank", "test-bank", "테스트"])
            assert result.exit_code == 0

    def test_chat_agent_error(self):
        """에이전트 오류 시 에러 출력."""
        with (
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                side_effect=Exception("API 오류"),
            ),
            patch(
                "jedisos.memory.hindsight.HindsightMemory.recall",
                new_callable=AsyncMock,
                side_effect=Exception("연결 실패"),
            ),
            patch(
                "jedisos.memory.hindsight.HindsightMemory.retain",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            result = runner.invoke(app, ["chat", "테스트"])
            assert result.exit_code == 1


class TestCLIServe:  # [JS-T010.6]
    """서버 명령 테스트."""

    def test_serve_shows_info(self):
        with patch("jedisos.web.app.run_server"):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 0
            assert "8080" in result.output

    def test_serve_custom_port(self):
        with patch("jedisos.web.app.run_server"):
            result = runner.invoke(app, ["serve", "--port", "9090"])
            assert result.exit_code == 0
            assert "9090" in result.output


class TestCLIUpdate:  # [JS-T010.7]
    """업데이트 명령 테스트."""

    def test_update_no_docker(self):
        """Docker 없을 때 안내 메시지."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 0
            assert "pip install" in result.output
