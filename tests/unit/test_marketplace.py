"""
[JS-T014] tests.unit.test_marketplace
로컬 패키지 매니저 단위 테스트

version: 1.0.0
created: 2026-02-18
"""

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from jedisos.cli.main import app
from jedisos.marketplace.manager import LocalPackageManager
from jedisos.marketplace.models import (
    ALLOWED_LICENSES,
    PackageInfo,
    PackageMeta,
    PackageType,
)
from jedisos.marketplace.scanner import PackageScanner
from jedisos.marketplace.validator import PackageValidator, ValidationResult

runner = CliRunner()


class TestPackageType:  # [JS-T014.1]
    """PackageType enum 테스트."""

    def test_all_six_types(self):
        assert len(PackageType) == 6

    def test_skill_type(self):
        assert PackageType.SKILL.value == "skill"

    def test_mcp_server_type(self):
        assert PackageType.MCP_SERVER.value == "mcp_server"

    def test_prompt_pack_type(self):
        assert PackageType.PROMPT_PACK.value == "prompt_pack"

    def test_workflow_type(self):
        assert PackageType.WORKFLOW.value == "workflow"

    def test_identity_pack_type(self):
        assert PackageType.IDENTITY_PACK.value == "identity_pack"

    def test_bundle_type(self):
        assert PackageType.BUNDLE.value == "bundle"

    def test_directory_name(self):
        assert PackageType.SKILL.dir_name == "skills"
        assert PackageType.MCP_SERVER.dir_name == "mcp-servers"
        assert PackageType.PROMPT_PACK.dir_name == "prompts"
        assert PackageType.WORKFLOW.dir_name == "workflows"
        assert PackageType.IDENTITY_PACK.dir_name == "identities"
        assert PackageType.BUNDLE.dir_name == "bundles"


class TestPackageMeta:  # [JS-T014.2]
    """PackageMeta 모델 테스트."""

    def test_minimal_meta(self):
        meta = PackageMeta(name="weather", version="1.0.0", description="날씨 도구")
        assert meta.name == "weather"
        assert meta.type == PackageType.SKILL

    def test_full_meta(self):
        meta = PackageMeta(
            name="weather",
            version="1.0.0",
            description="날씨 도구",
            type=PackageType.PROMPT_PACK,
            license="MIT",
            author="jedi",
            tags=["weather", "api"],
        )
        assert meta.type == PackageType.PROMPT_PACK
        assert meta.license == "MIT"
        assert meta.tags == ["weather", "api"]

    def test_default_license(self):
        meta = PackageMeta(name="test", version="1.0.0", description="테스트")
        assert meta.license == "MIT"


class TestPackageInfo:  # [JS-T014.3]
    """PackageInfo 모델 테스트."""

    def test_package_info(self, tmp_path):
        meta = PackageMeta(name="weather", version="1.0.0", description="날씨")
        info = PackageInfo(meta=meta, directory=tmp_path / "weather")
        assert info.meta.name == "weather"
        assert info.directory == tmp_path / "weather"


class TestAllowedLicenses:  # [JS-T014.4]
    """허용 라이선스 테스트."""

    def test_contains_mit(self):
        assert "MIT" in ALLOWED_LICENSES

    def test_contains_apache(self):
        assert "Apache-2.0" in ALLOWED_LICENSES

    def test_contains_bsd(self):
        assert "BSD-3-Clause" in ALLOWED_LICENSES


def _create_package(
    base: Path, pkg_type: str, name: str, meta_override: dict | None = None
) -> Path:
    """테스트용 패키지 디렉토리 생성 헬퍼."""
    type_dir_map = {
        "skill": "skills",
        "prompt_pack": "prompts",
        "workflow": "workflows",
        "identity_pack": "identities",
        "mcp_server": "mcp-servers",
        "bundle": "bundles",
    }
    pkg_dir = base / type_dir_map[pkg_type] / name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "name": name,
        "version": "1.0.0",
        "description": f"{name} 패키지",
        "type": pkg_type,
        "license": "MIT",
        **(meta_override or {}),
    }
    (pkg_dir / "jedisos-package.yaml").write_text(yaml.dump(meta, allow_unicode=True))
    return pkg_dir


class TestPackageScanner:  # [JS-T014.5]
    """PackageScanner 테스트."""

    def test_scan_empty(self, tmp_path):
        scanner = PackageScanner(tmp_path)
        result = scanner.scan_all()
        assert result == []

    def test_scan_one_skill(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        scanner = PackageScanner(tmp_path)
        result = scanner.scan_all()
        assert len(result) == 1
        assert result[0].meta.name == "weather"

    def test_scan_multiple_types(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        _create_package(tmp_path, "prompt_pack", "coding")
        _create_package(tmp_path, "workflow", "daily")
        scanner = PackageScanner(tmp_path)
        result = scanner.scan_all()
        assert len(result) == 3

    def test_scan_type_filter(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        _create_package(tmp_path, "skill", "calculator")
        _create_package(tmp_path, "prompt_pack", "coding")
        scanner = PackageScanner(tmp_path)
        result = scanner.scan_type(PackageType.SKILL)
        assert len(result) == 2

    def test_scan_ignores_invalid_yaml(self, tmp_path):
        pkg_dir = tmp_path / "skills" / "broken"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "jedisos-package.yaml").write_text("{{invalid: yaml: [")
        scanner = PackageScanner(tmp_path)
        result = scanner.scan_all()
        assert len(result) == 0

    def test_scan_ignores_dir_without_yaml(self, tmp_path):
        (tmp_path / "skills" / "empty").mkdir(parents=True)
        scanner = PackageScanner(tmp_path)
        result = scanner.scan_all()
        assert len(result) == 0

    def test_scan_includes_directory(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        scanner = PackageScanner(tmp_path)
        result = scanner.scan_all()
        assert result[0].directory == tmp_path / "skills" / "weather"


class TestPackageValidator:  # [JS-T014.6]
    """PackageValidator 테스트."""

    @pytest.mark.asyncio
    async def test_valid_skill(self, tmp_path):
        pkg = _create_package(tmp_path, "skill", "weather")
        (pkg / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="weather", description="날씨")\n'
            "async def get_weather(city: str) -> str:\n"
            '    return f"{city} 맑음"\n'
        )
        (pkg / "README.md").write_text("# Weather Tool\n\n" + "날씨 도구입니다. " * 20)
        validator = PackageValidator()
        result = await validator.validate(pkg)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_missing_metadata(self, tmp_path):
        pkg_dir = tmp_path / "empty_pkg"
        pkg_dir.mkdir()
        validator = PackageValidator()
        result = await validator.validate(pkg_dir)
        assert result.passed is False
        assert any("jedisos-package.yaml" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_invalid_license(self, tmp_path):
        pkg = _create_package(tmp_path, "skill", "bad-license", {"license": "GPL-3.0"})
        validator = PackageValidator()
        result = await validator.validate(pkg)
        assert result.passed is False
        assert any("라이선스" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_prompt_pack_no_code_check(self, tmp_path):
        """Prompt Pack은 코드 보안 검사를 건너뛰어야 합니다."""
        pkg = _create_package(tmp_path, "prompt_pack", "coding")
        (pkg / "prompts.yaml").write_text("prompts:\n  - name: test\n")
        (pkg / "README.md").write_text("# Coding Prompts\n\n" + "코딩 프롬프트 팩입니다. " * 20)
        validator = PackageValidator()
        result = await validator.validate(pkg)
        assert result.passed is True
        assert result.checks.get("security") is True

    @pytest.mark.asyncio
    async def test_short_readme_warning(self, tmp_path):
        pkg = _create_package(tmp_path, "skill", "short-readme")
        (pkg / "README.md").write_text("짧음")
        validator = PackageValidator()
        result = await validator.validate(pkg)
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_validation_result_fields(self, tmp_path):
        pkg = _create_package(tmp_path, "skill", "test-fields")
        validator = PackageValidator()
        result = await validator.validate(pkg)
        assert isinstance(result, ValidationResult)
        assert isinstance(result.checks, dict)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)


class TestLocalPackageManager:  # [JS-T014.7]
    """LocalPackageManager 테스트."""

    def test_list_empty(self, tmp_path):
        mgr = LocalPackageManager(tmp_path)
        assert mgr.list_packages() == []

    def test_list_packages(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        _create_package(tmp_path, "prompt_pack", "coding")
        mgr = LocalPackageManager(tmp_path)
        result = mgr.list_packages()
        assert len(result) == 2

    def test_list_by_type(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        _create_package(tmp_path, "skill", "calculator")
        _create_package(tmp_path, "prompt_pack", "coding")
        mgr = LocalPackageManager(tmp_path)
        result = mgr.list_packages(package_type=PackageType.SKILL)
        assert len(result) == 2

    def test_search_by_name(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        _create_package(tmp_path, "skill", "calculator")
        mgr = LocalPackageManager(tmp_path)
        result = mgr.search("weath")
        assert len(result) == 1
        assert result[0].meta.name == "weather"

    def test_search_by_tag(self, tmp_path):
        _create_package(tmp_path, "skill", "weather", {"tags": ["api", "weather"]})
        _create_package(tmp_path, "skill", "calc", {"tags": ["math"]})
        mgr = LocalPackageManager(tmp_path)
        result = mgr.search("api")
        assert len(result) == 1

    def test_search_by_description(self, tmp_path):
        _create_package(tmp_path, "skill", "weather", {"description": "날씨 정보를 조회합니다"})
        _create_package(tmp_path, "skill", "calc", {"description": "계산기"})
        mgr = LocalPackageManager(tmp_path)
        result = mgr.search("날씨")
        assert len(result) == 1

    def test_get_package(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        mgr = LocalPackageManager(tmp_path)
        info = mgr.get_package("weather")
        assert info is not None
        assert info.meta.name == "weather"

    def test_get_package_not_found(self, tmp_path):
        mgr = LocalPackageManager(tmp_path)
        assert mgr.get_package("nonexistent") is None

    def test_install_from_local(self, tmp_path):
        source = tmp_path / "source" / "my-tool"
        source.mkdir(parents=True)
        meta = {
            "name": "my-tool",
            "version": "1.0.0",
            "description": "내 도구",
            "type": "skill",
            "license": "MIT",
        }
        (source / "jedisos-package.yaml").write_text(yaml.dump(meta, allow_unicode=True))
        (source / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="my-tool", description="내 도구")\n'
            "async def run(x: str) -> str:\n"
            "    return x\n"
        )

        tools_dir = tmp_path / "tools"
        mgr = LocalPackageManager(tools_dir)
        result = mgr.install(source)
        assert result["status"] == "installed"
        assert (tools_dir / "skills" / "my-tool" / "jedisos-package.yaml").exists()

    def test_install_already_exists(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        source = tmp_path / "source" / "weather"
        source.mkdir(parents=True)
        meta = {
            "name": "weather",
            "version": "2.0.0",
            "description": "날씨 v2",
            "type": "skill",
            "license": "MIT",
        }
        (source / "jedisos-package.yaml").write_text(yaml.dump(meta, allow_unicode=True))

        mgr = LocalPackageManager(tmp_path)
        with pytest.raises(Exception, match="이미 설치"):
            mgr.install(source)

    def test_install_force_overwrite(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        source = tmp_path / "source" / "weather"
        source.mkdir(parents=True)
        meta = {
            "name": "weather",
            "version": "2.0.0",
            "description": "날씨 v2",
            "type": "skill",
            "license": "MIT",
        }
        (source / "jedisos-package.yaml").write_text(yaml.dump(meta, allow_unicode=True))

        mgr = LocalPackageManager(tmp_path)
        result = mgr.install(source, force=True)
        assert result["status"] == "installed"
        assert result["version"] == "2.0.0"

    def test_remove_package(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        mgr = LocalPackageManager(tmp_path)
        assert mgr.get_package("weather") is not None
        result = mgr.remove("weather")
        assert result["status"] == "removed"
        assert mgr.get_package("weather") is None

    def test_remove_not_found(self, tmp_path):
        mgr = LocalPackageManager(tmp_path)
        with pytest.raises(Exception, match="찾을 수 없"):
            mgr.remove("nonexistent")


class TestMarketCLI:  # [JS-T014.8]
    """CLI market 서브커맨드 테스트."""

    def test_market_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JEDISOS_TOOLS_DIR", str(tmp_path))
        result = runner.invoke(app, ["market", "list"])
        assert result.exit_code == 0
        assert "패키지가 없습니다" in result.stdout

    def test_market_list_with_packages(self, tmp_path, monkeypatch):
        _create_package(tmp_path, "skill", "weather")
        monkeypatch.setenv("JEDISOS_TOOLS_DIR", str(tmp_path))
        result = runner.invoke(app, ["market", "list"])
        assert result.exit_code == 0
        assert "weather" in result.stdout

    def test_market_search(self, tmp_path, monkeypatch):
        _create_package(tmp_path, "skill", "weather", {"description": "날씨 조회"})
        monkeypatch.setenv("JEDISOS_TOOLS_DIR", str(tmp_path))
        result = runner.invoke(app, ["market", "search", "weather"])
        assert result.exit_code == 0
        assert "weather" in result.stdout

    def test_market_info(self, tmp_path, monkeypatch):
        _create_package(tmp_path, "skill", "weather")
        monkeypatch.setenv("JEDISOS_TOOLS_DIR", str(tmp_path))
        result = runner.invoke(app, ["market", "info", "weather"])
        assert result.exit_code == 0
        assert "weather" in result.stdout

    def test_market_info_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JEDISOS_TOOLS_DIR", str(tmp_path))
        result = runner.invoke(app, ["market", "info", "nonexistent"])
        assert result.exit_code == 1

    def test_market_remove(self, tmp_path, monkeypatch):
        _create_package(tmp_path, "skill", "weather")
        monkeypatch.setenv("JEDISOS_TOOLS_DIR", str(tmp_path))
        result = runner.invoke(app, ["market", "remove", "weather", "--yes"])
        assert result.exit_code == 0
        assert "삭제" in result.stdout
