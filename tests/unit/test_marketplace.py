"""
[JS-T014] tests.unit.test_marketplace
로컬 패키지 매니저 단위 테스트

version: 1.0.0
created: 2026-02-18
"""

import pytest

from jedisos.marketplace.models import (
    ALLOWED_LICENSES,
    PackageInfo,
    PackageMeta,
    PackageType,
)


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
