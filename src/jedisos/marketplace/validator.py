"""
[JS-M003] jedisos.marketplace.validator
패키지 검증기 - 메타데이터 + 라이선스 + 보안 검증

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: pyyaml>=6.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog
import yaml

from jedisos.marketplace.models import ALLOWED_LICENSES, PackageMeta, PackageType

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger()

VALIDATION_CHECKS: dict[str, str] = {  # [JS-M003.1]
    "metadata": "jedisos-package.yaml 필수 필드 확인",
    "license": "MIT/Apache-2.0/BSD-3-Clause 중 하나",
    "security": "코드 보안 정적분석 (Skill만)",
    "docs": "README.md 존재 + 최소 100자",
}


@dataclass
class ValidationResult:  # [JS-M003.2]
    """검증 결과."""

    passed: bool
    package_name: str
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PackageValidator:  # [JS-M003.3]
    """패키지 검증기."""

    async def validate(self, package_dir: Path) -> ValidationResult:  # [JS-M003.4]
        """패키지 디렉토리를 검증합니다."""
        checks: dict[str, bool] = {}
        errors: list[str] = []
        warnings: list[str] = []
        package_name = package_dir.name

        # 1. 메타데이터 검증
        meta, meta_ok, meta_errors = self._check_metadata(package_dir)
        checks["metadata"] = meta_ok
        errors.extend(meta_errors)
        if meta:
            package_name = meta.name

        # 2. 라이선스 검증
        lic_ok, lic_err = self._check_license(meta)
        checks["license"] = lic_ok
        if lic_err:
            errors.append(lic_err)

        # 3. 보안 검증 (Skill만)
        if meta and meta.type == PackageType.SKILL:
            sec_ok, sec_errors = await self._check_security(package_dir)
            checks["security"] = sec_ok
            errors.extend(sec_errors)
        else:
            checks["security"] = True

        # 4. 문서 검증
        docs_ok, docs_warn = self._check_docs(package_dir)
        checks["docs"] = docs_ok
        if docs_warn:
            warnings.append(docs_warn)

        passed = all(checks.values())

        logger.info(
            "package_validation_complete", package=package_name, passed=passed, checks=checks
        )
        return ValidationResult(
            passed=passed,
            package_name=package_name,
            checks=checks,
            errors=errors,
            warnings=warnings,
        )

    def _check_metadata(
        self, package_dir: Path
    ) -> tuple[PackageMeta | None, bool, list[str]]:  # [JS-M003.5]
        """메타데이터 파일을 검증합니다."""
        meta_path = package_dir / "jedisos-package.yaml"
        if not meta_path.exists():
            return None, False, ["jedisos-package.yaml이 없습니다"]

        try:
            data = yaml.safe_load(meta_path.read_text())
        except yaml.YAMLError as e:
            return None, False, [f"YAML 파싱 오류: {e}"]

        if not isinstance(data, dict):
            return None, False, ["메타데이터가 유효한 딕셔너리가 아닙니다"]

        required = ["name", "version", "description"]
        missing = [f for f in required if f not in data]
        if missing:
            return None, False, [f"필수 필드 누락: {missing}"]

        try:
            if "type" not in data:
                data["type"] = "skill"
            meta = PackageMeta(**data)
        except Exception as e:
            return None, False, [f"메타데이터 파싱 오류: {e}"]

        return meta, True, []

    def _check_license(self, meta: PackageMeta | None) -> tuple[bool, str]:  # [JS-M003.6]
        """라이선스를 검증합니다."""
        if not meta:
            return False, "메타데이터가 없어 라이선스를 확인할 수 없습니다"
        if meta.license not in ALLOWED_LICENSES:
            return False, f"허용되지 않는 라이선스: {meta.license} (허용: {ALLOWED_LICENSES})"
        return True, ""

    async def _check_security(self, package_dir: Path) -> tuple[bool, list[str]]:  # [JS-M003.7]
        """Skill 코드 보안을 검증합니다. Forge의 CodeSecurityChecker 재활용."""
        tool_py = package_dir / "tool.py"
        if not tool_py.exists():
            return True, []

        from jedisos.forge.security import CodeSecurityChecker

        checker = CodeSecurityChecker()
        code = tool_py.read_text()
        result = await checker.check(code, package_dir.name)

        if not result.passed:
            errors = [
                f"[{i.severity}] {i.category}: {i.message}"
                for i in result.issues
                if i.severity == "high"
            ]
            return False, errors

        return True, []

    def _check_docs(self, package_dir: Path) -> tuple[bool, str]:  # [JS-M003.8]
        """README.md 존재를 확인합니다."""
        readme = package_dir / "README.md"
        if not readme.exists():
            return True, "README.md가 없습니다 (권장)"

        content = readme.read_text().strip()
        if len(content) < 100:
            return True, f"README.md가 짧습니다 ({len(content)}자, 100자 이상 권장)"

        return True, ""
