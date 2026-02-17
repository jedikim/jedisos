"""
[JS-T014] tests.unit.test_marketplace
로컬 패키지 매니저 단위 테스트

version: 1.0.0
created: 2026-02-18
"""

from pathlib import Path

import pytest
import yaml

from jedisos.marketplace.models import (
    ALLOWED_LICENSES,
    PackageInfo,
    PackageMeta,
    PackageType,
)
from jedisos.marketplace.scanner import PackageScanner
from jedisos.marketplace.validator import PackageValidator, ValidationResult


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


def _create_package(base: Path, pkg_type: str, name: str, meta_override: dict | None = None) -> Path:
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
    (pkg_dir / "jedisos-package.yaml").write_text(
        yaml.dump(meta, allow_unicode=True)
    )
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
            'from jedisos.forge.decorator import tool\n\n'
            '@tool(name="weather", description="날씨")\n'
            'async def get_weather(city: str) -> str:\n'
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
