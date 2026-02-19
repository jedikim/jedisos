"""
[JS-T011] tests.unit.test_web_api
웹 API 단위 테스트 - FastAPI TestClient 기반

version: 1.0.0
created: 2026-02-18
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from jedisos import __version__
from jedisos.web.app import create_app


@pytest.fixture
def app():
    """테스트용 FastAPI 앱."""
    return create_app()


@pytest.fixture
def client(app):
    """TestClient 픽스처."""
    return TestClient(app)


class TestHealthCheck:  # [JS-T011.1]
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == __version__

    def test_openapi_docs(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        assert "JediSOS" in resp.json()["info"]["title"]


class TestChatAPI:  # [JS-T011.2]
    def test_send_message_success(self, client):
        """POST /api/chat/send 정상 응답."""
        with patch(
            "jedisos.web.api.chat._run_agent",
            new_callable=AsyncMock,
            return_value="안녕하세요!",
        ):
            resp = client.post(
                "/api/chat/send",
                json={
                    "message": "안녕",
                    "bank_id": "test-bank",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["response"] == "안녕하세요!"
            assert data["bank_id"] == "test-bank"

    def test_get_connections(self, client):
        resp = client.get("/api/chat/connections")
        assert resp.status_code == 200
        assert "active_connections" in resp.json()


class TestSettingsAPI:  # [JS-T011.3]
    def test_get_llm_settings_no_state(self, client):
        """앱 상태가 없을 때 기본값 반환."""
        resp = client.get("/api/settings/llm")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "temperature" in data

    def test_get_llm_settings_with_state(self, client):
        mock_config = MagicMock()
        mock_config.llm.models = ["gpt-5.2", "gemini/gemini-3-flash"]
        mock_config.llm.temperature = 0.7
        mock_config.llm.max_tokens = 8192
        mock_config.llm.timeout = 60

        with patch("jedisos.web.app._app_state", {"config": mock_config}):
            resp = client.get("/api/settings/llm")
            assert resp.status_code == 200
            data = resp.json()
            assert data["models"] == ["gpt-5.2", "gemini/gemini-3-flash"]

    def test_update_llm_settings(self, client, tmp_path):
        with patch("jedisos.web.api.settings._CONFIG_DIR", tmp_path):
            resp = client.put(
                "/api/settings/llm",
                json={
                    "models": ["gpt-5.2"],
                    "temperature": 0.5,
                },
            )
            assert resp.status_code == 200
            assert (tmp_path / "llm_config.yaml").exists()

    def test_get_env_keys(self, client, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=sk-test\nDEBUG=false\n")

        with patch("jedisos.web.api.settings._ENV_PATH", env_file):
            resp = client.get("/api/settings/env")
            assert resp.status_code == 200
            data = resp.json()
            assert "known_keys" in data
            assert "OPENAI_API_KEY" in data["known_keys"]

    def test_update_env_allowed(self, client, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DEBUG=false\n")

        with patch("jedisos.web.api.settings._ENV_PATH", env_file):
            resp = client.put("/api/settings/env", json={"key": "DEBUG", "value": "true"})
            assert resp.status_code == 200
            assert "DEBUG=true" in env_file.read_text()

    def test_get_env_keys_includes_channel_tokens(self, client, tmp_path):  # [JS-T011.3a]
        """known_keys에 채널 토큰이 포함되어야 합니다."""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        with patch("jedisos.web.api.settings._ENV_PATH", env_file):
            resp = client.get("/api/settings/env")
            data = resp.json()
            for key in [
                "TELEGRAM_BOT_TOKEN",
                "DISCORD_BOT_TOKEN",
                "SLACK_BOT_TOKEN",
                "SLACK_APP_TOKEN",
            ]:
                assert key in data["known_keys"]

    def test_update_env_channel_token(self, client, tmp_path):  # [JS-T011.3b]
        """채널 토큰 업데이트가 허용되어야 합니다."""
        env_file = tmp_path / ".env"
        env_file.write_text("DEBUG=false\n")
        with patch("jedisos.web.api.settings._ENV_PATH", env_file):
            resp = client.put(
                "/api/settings/env",
                json={"key": "TELEGRAM_BOT_TOKEN", "value": "123456:ABC-DEF"},
            )
            assert resp.status_code == 200
            content = env_file.read_text()
            assert "TELEGRAM_BOT_TOKEN=123456:ABC-DEF" in content

    def test_update_env_blocked(self, client):
        resp = client.put("/api/settings/env", json={"key": "DANGEROUS_KEY", "value": "bad"})
        assert resp.status_code == 400

    def test_get_security_no_state(self, client):
        resp = client.get("/api/settings/security")
        assert resp.status_code == 200


class TestMCPAPI:  # [JS-T011.4]
    def test_list_servers_empty(self, client, tmp_path):
        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", tmp_path / "mcp.json"):
            resp = client.get("/api/mcp/servers")
            assert resp.status_code == 200
            assert resp.json()["total"] == 0

    def test_install_server(self, client, tmp_path):
        config_path = tmp_path / "mcp.json"
        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", config_path):
            resp = client.post(
                "/api/mcp/servers",
                json={
                    "name": "test-server",
                    "url": "http://localhost:9000",
                    "description": "테스트 서버",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "installed"

            # 다시 조회
            resp2 = client.get("/api/mcp/servers")
            assert resp2.json()["total"] == 1

    def test_install_duplicate(self, client, tmp_path):
        config_path = tmp_path / "mcp.json"
        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", config_path):
            client.post("/api/mcp/servers", json={"name": "dup", "url": "http://a"})
            resp = client.post("/api/mcp/servers", json={"name": "dup", "url": "http://b"})
            assert resp.status_code == 409

    def test_uninstall_server(self, client, tmp_path):
        config_path = tmp_path / "mcp.json"
        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", config_path):
            client.post("/api/mcp/servers", json={"name": "rm-me", "url": "http://a"})
            resp = client.delete("/api/mcp/servers/rm-me")
            assert resp.status_code == 200
            assert resp.json()["status"] == "uninstalled"

    def test_uninstall_not_found(self, client, tmp_path):
        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", tmp_path / "mcp.json"):
            resp = client.delete("/api/mcp/servers/nonexistent")
            assert resp.status_code == 404

    def test_toggle_server(self, client, tmp_path):
        config_path = tmp_path / "mcp.json"
        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", config_path):
            client.post("/api/mcp/servers", json={"name": "toggle-me", "url": "http://a"})
            resp = client.put("/api/mcp/servers/toggle-me/toggle")
            assert resp.status_code == 200
            assert resp.json()["enabled"] is False

    def test_toggle_not_found(self, client, tmp_path):
        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", tmp_path / "mcp.json"):
            resp = client.put("/api/mcp/servers/nope/toggle")
            assert resp.status_code == 404


class TestMonitoringAPI:  # [JS-T011.5]
    def test_status_no_state(self, client):
        resp = client.get("/api/monitoring/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == __version__

    def test_status_with_state(self, client):
        mock_memory = MagicMock()
        mock_memory.health_check = AsyncMock(return_value=True)
        mock_llm = MagicMock()
        mock_llm.models = ["gpt-5.2"]

        with patch(
            "jedisos.web.app._app_state",
            {
                "memory": mock_memory,
                "llm": mock_llm,
            },
        ):
            resp = client.get("/api/monitoring/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["services"]["memory"] == "ok"
            assert data["models"] == ["gpt-5.2"]

    def test_audit_no_state(self, client):
        resp = client.get("/api/monitoring/audit")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_audit_with_entries(self, client):
        from jedisos.security.audit import AuditLogger

        audit = AuditLogger()
        audit.log_tool_call(tool_name="echo", allowed=True)
        audit.log_tool_call(tool_name="shell_exec", allowed=False, reason="차단됨")

        with patch("jedisos.web.app._app_state", {"audit": audit}):
            resp = client.get("/api/monitoring/audit")
            assert resp.status_code == 200
            assert resp.json()["total"] == 2

    def test_denied_log(self, client):
        from jedisos.security.audit import AuditLogger

        audit = AuditLogger()
        audit.log_tool_call(tool_name="shell_exec", allowed=False, reason="차단됨")

        with patch("jedisos.web.app._app_state", {"audit": audit}):
            resp = client.get("/api/monitoring/audit/denied")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1

    def test_policy_no_state(self, client):
        resp = client.get("/api/monitoring/policy")
        assert resp.status_code == 200


class TestSetupWizardAPI:  # [JS-T011.6]
    def test_setup_status_first_run(self, client, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("JEDISOS_FIRST_RUN=true\nOPENAI_API_KEY=\n")

        with patch("jedisos.web.setup_wizard._ENV_PATH", env_file):
            resp = client.get("/api/setup/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_first_run"] is True
            assert data["has_api_key"] is False

    def test_setup_status_configured(self, client, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("JEDISOS_FIRST_RUN=false\nOPENAI_API_KEY=sk-test\n")

        with patch("jedisos.web.setup_wizard._ENV_PATH", env_file):
            resp = client.get("/api/setup/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_first_run"] is False
            assert data["has_api_key"] is True

    def test_complete_setup(self, client, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("JEDISOS_FIRST_RUN=true\n")
        config_dir = tmp_path / "config"

        with (
            patch("jedisos.web.setup_wizard._ENV_PATH", env_file),
            patch(
                "jedisos.web.setup_wizard.Path",
                side_effect=lambda p: tmp_path / p if p != ".env" else env_file,
            ),
        ):
            # 직접 config 디렉토리 패치
            import jedisos.web.setup_wizard as wizard_mod

            async def patched_complete(request):
                # .env 업데이트
                env_lines = env_file.read_text().splitlines()
                env_lines = wizard_mod._update_env_line(
                    env_lines, "OPENAI_API_KEY", request.openai_api_key
                )
                env_lines = wizard_mod._update_env_line(env_lines, "JEDISOS_FIRST_RUN", "false")
                env_file.write_text("\n".join(env_lines) + "\n")

                # config 생성
                config_dir.mkdir(exist_ok=True)
                models = request.models or ["gpt-5.2"]
                (config_dir / "llm_config.yaml").write_text(f"models:\n  - {models[0]}\n")
                return {"status": "completed"}

            with patch.object(wizard_mod, "complete_setup", patched_complete):
                resp = client.post(
                    "/api/setup/complete",
                    json={
                        "openai_api_key": "sk-test",
                        "models": ["gpt-5.2"],
                    },
                )
                assert resp.status_code == 200

    def test_complete_setup_with_channel_tokens(self, client, tmp_path):  # [JS-T011.6a]
        """Setup 완료 시 채널 토큰이 .env에 저장되어야 합니다."""
        env_file = tmp_path / ".env"
        env_file.write_text("JEDISOS_FIRST_RUN=true\n")
        config_dir = tmp_path / "config"

        with (
            patch("jedisos.web.setup_wizard._ENV_PATH", env_file),
            patch(
                "jedisos.web.setup_wizard.Path",
                side_effect=lambda p: config_dir if p == "config" else Path(p),
            ),
        ):
            resp = client.post(
                "/api/setup/complete",
                json={
                    "openai_api_key": "sk-test",
                    "google_api_key": "",
                    "telegram_bot_token": "123456:ABC-DEF",
                    "discord_bot_token": "discord-token",
                    "slack_bot_token": "xoxb-slack",
                    "slack_app_token": "xapp-slack",
                    "models": ["gpt-5.2"],
                },
            )
            assert resp.status_code == 200
            content = env_file.read_text()
            assert "TELEGRAM_BOT_TOKEN=123456:ABC-DEF" in content
            assert "DISCORD_BOT_TOKEN=discord-token" in content
            assert "SLACK_BOT_TOKEN=xoxb-slack" in content
            assert "SLACK_APP_TOKEN=xapp-slack" in content

    def test_recommended_mcp(self, client):
        resp = client.get("/api/setup/recommended-mcp")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["servers"]) >= 1
        assert data["servers"][0]["name"] == "zvec-memory"


class TestWebUI:  # [JS-T011.7]
    """웹 UI 서빙 테스트."""

    def test_root_returns_html(self, client):  # [JS-T011.7a]
        """GET / 은 HTML을 반환해야 합니다."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "JediSOS" in resp.text

    def test_root_contains_alpine_js(self, client):  # [JS-T011.7b]
        """Alpine.js CDN이 포함되어야 합니다."""
        resp = client.get("/")
        assert "alpinejs" in resp.text

    def test_root_contains_tailwind(self, client):  # [JS-T011.7c]
        """Tailwind CSS CDN이 포함되어야 합니다."""
        resp = client.get("/")
        assert "tailwindcss" in resp.text

    def test_static_js_served(self, client):  # [JS-T011.7d]
        """정적 JS 파일이 서빙되어야 합니다."""
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200

    def test_static_css_served(self, client):  # [JS-T011.7e]
        """정적 CSS 파일이 서빙되어야 합니다."""
        resp = client.get("/static/css/app.css")
        assert resp.status_code == 200
