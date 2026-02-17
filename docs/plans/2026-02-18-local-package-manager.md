# Phase 11: Local Package Manager Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local-only package manager that manages 6 package types via filesystem under `tools/`.

**Architecture:** Filesystem-based local registry where each package's `jedisos-package.yaml` is the source of truth. No remote API, no database. Reuses Forge's `CodeSecurityChecker` for Skill validation.

**Tech Stack:** Python 3.12+, pydantic, pyyaml, structlog, typer, rich, shutil

---

### Task 1: Models (`models.py`)

**Files:**
- Create: `src/jedisos/marketplace/__init__.py`
- Create: `src/jedisos/marketplace/models.py`
- Test: `tests/unit/test_marketplace.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_marketplace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jedisos.marketplace'`

**Step 3: Write minimal implementation**

`src/jedisos/marketplace/__init__.py`:
```python
```

`src/jedisos/marketplace/models.py`:
```python
"""
[JS-M004] jedisos.marketplace.models
패키지 메타데이터 모델 - 6종 패키지 유형 정의

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: pydantic>=2.12
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path

# 허용 라이선스 목록  [JS-M004.1]
ALLOWED_LICENSES: set[str] = {"MIT", "Apache-2.0", "BSD-3-Clause"}


class PackageType(str, Enum):  # [JS-M004.2]
    """패키지 유형 (6종)."""

    SKILL = "skill"
    MCP_SERVER = "mcp_server"
    PROMPT_PACK = "prompt_pack"
    WORKFLOW = "workflow"
    IDENTITY_PACK = "identity_pack"
    BUNDLE = "bundle"

    @property
    def dir_name(self) -> str:  # [JS-M004.3]
        """tools/ 하위 디렉토리 이름."""
        mapping = {
            "skill": "skills",
            "mcp_server": "mcp-servers",
            "prompt_pack": "prompts",
            "workflow": "workflows",
            "identity_pack": "identities",
            "bundle": "bundles",
        }
        return mapping[self.value]


class PackageMeta(BaseModel):  # [JS-M004.4]
    """패키지 메타데이터 (jedisos-package.yaml 내용)."""

    name: str
    version: str
    description: str
    type: PackageType = PackageType.SKILL
    license: str = "MIT"
    author: str = "anonymous"
    tags: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class PackageInfo(BaseModel):  # [JS-M004.5]
    """설치된 패키지 정보 (메타 + 디렉토리 경로)."""

    meta: PackageMeta
    directory: Path

    model_config = {"arbitrary_types_allowed": True}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_marketplace.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/jedisos/marketplace/__init__.py src/jedisos/marketplace/models.py tests/unit/test_marketplace.py
git commit -m "feat(marketplace): [JS-M004] 패키지 메타데이터 모델 (6종 유형)"
```

---

### Task 2: Scanner (`scanner.py`)

**Files:**
- Create: `src/jedisos/marketplace/scanner.py`
- Create: `tools/skills/.gitkeep`, `tools/prompts/.gitkeep`, `tools/workflows/.gitkeep`, `tools/identities/.gitkeep`, `tools/mcp-servers/.gitkeep`, `tools/bundles/.gitkeep`
- Modify: `tests/unit/test_marketplace.py`

**Step 1: Write the failing test**

Append to `tests/unit/test_marketplace.py`:

```python
from pathlib import Path

import yaml

from jedisos.marketplace.scanner import PackageScanner


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_marketplace.py::TestPackageScanner -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jedisos.marketplace.scanner'`

**Step 3: Write minimal implementation**

```python
"""
[JS-M002] jedisos.marketplace.scanner
패키지 스캐너 - tools/ 디렉토리 파일시스템 탐색

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: pyyaml>=6.0
"""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml

from jedisos.marketplace.models import PackageInfo, PackageMeta, PackageType

logger = structlog.get_logger()


class PackageScanner:  # [JS-M002.1]
    """tools/ 디렉토리를 스캔하여 패키지 목록을 반환."""

    def __init__(self, tools_dir: Path | None = None) -> None:
        self.tools_dir = tools_dir or Path("tools")

    def scan_all(self) -> list[PackageInfo]:  # [JS-M002.2]
        """모든 패키지 유형을 스캔합니다."""
        packages: list[PackageInfo] = []
        for pkg_type in PackageType:
            packages.extend(self.scan_type(pkg_type))
        return packages

    def scan_type(self, package_type: PackageType) -> list[PackageInfo]:  # [JS-M002.3]
        """특정 유형의 패키지만 스캔합니다."""
        type_dir = self.tools_dir / package_type.dir_name
        if not type_dir.exists():
            return []

        packages: list[PackageInfo] = []
        for pkg_dir in sorted(type_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue
            info = self._load_package(pkg_dir)
            if info:
                packages.append(info)

        return packages

    def _load_package(self, pkg_dir: Path) -> PackageInfo | None:  # [JS-M002.4]
        """패키지 디렉토리에서 메타데이터를 로드합니다."""
        meta_path = pkg_dir / "jedisos-package.yaml"
        if not meta_path.exists():
            return None

        try:
            data = yaml.safe_load(meta_path.read_text())
            if not isinstance(data, dict):
                return None
            meta = PackageMeta(**data)
        except (yaml.YAMLError, Exception) as e:
            logger.warning("package_meta_load_failed", dir=str(pkg_dir), error=str(e))
            return None

        return PackageInfo(meta=meta, directory=pkg_dir)
```

Also create `.gitkeep` files for the 6 type directories:

```bash
mkdir -p tools/{skills,prompts,workflows,identities,mcp-servers,bundles}
touch tools/{skills,prompts,workflows,identities,mcp-servers,bundles}/.gitkeep
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_marketplace.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/jedisos/marketplace/scanner.py tools/
git commit -m "feat(marketplace): [JS-M002] PackageScanner + tools/ 디렉토리 구조"
```

---

### Task 3: Validator (`validator.py`)

**Files:**
- Create: `src/jedisos/marketplace/validator.py`
- Modify: `tests/unit/test_marketplace.py`

**Step 1: Write the failing test**

Append to `tests/unit/test_marketplace.py`:

```python
from jedisos.marketplace.validator import PackageValidator, ValidationResult


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
        assert "security" not in result.checks or result.checks["security"] is True

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_marketplace.py::TestPackageValidator -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
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

        logger.info("package_validation_complete", package=package_name, passed=passed, checks=checks)
        return ValidationResult(
            passed=passed, package_name=package_name,
            checks=checks, errors=errors, warnings=warnings,
        )

    def _check_metadata(self, package_dir: Path) -> tuple[PackageMeta | None, bool, list[str]]:  # [JS-M003.5]
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
```

Note: `_check_docs` returns `(True, warning)` instead of `(False, ...)` — README is recommended but not required for local packages.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_marketplace.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/jedisos/marketplace/validator.py tests/unit/test_marketplace.py
git commit -m "feat(marketplace): [JS-M003] PackageValidator (Forge security 재활용)"
```

---

### Task 4: Manager (`manager.py`)

**Files:**
- Create: `src/jedisos/marketplace/manager.py`
- Modify: `src/jedisos/core/exceptions.py` (add `MarketplaceError`)
- Modify: `tests/unit/test_marketplace.py`

**Step 1: Write the failing test**

Append to `tests/unit/test_marketplace.py`:

```python
from jedisos.marketplace.manager import LocalPackageManager


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
        # source 패키지 생성
        source = tmp_path / "source" / "my-tool"
        source.mkdir(parents=True)
        meta = {"name": "my-tool", "version": "1.0.0", "description": "내 도구", "type": "skill", "license": "MIT"}
        (source / "jedisos-package.yaml").write_text(yaml.dump(meta, allow_unicode=True))
        (source / "tool.py").write_text(
            'from jedisos.forge.decorator import tool\n\n'
            '@tool(name="my-tool", description="내 도구")\n'
            'async def run(x: str) -> str:\n'
            '    return x\n'
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
        meta = {"name": "weather", "version": "2.0.0", "description": "날씨 v2", "type": "skill", "license": "MIT"}
        (source / "jedisos-package.yaml").write_text(yaml.dump(meta, allow_unicode=True))

        mgr = LocalPackageManager(tmp_path)
        with pytest.raises(Exception, match="이미 설치"):
            mgr.install(source)

    def test_install_force_overwrite(self, tmp_path):
        _create_package(tmp_path, "skill", "weather")
        source = tmp_path / "source" / "weather"
        source.mkdir(parents=True)
        meta = {"name": "weather", "version": "2.0.0", "description": "날씨 v2", "type": "skill", "license": "MIT"}
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_marketplace.py::TestLocalPackageManager -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add to `src/jedisos/core/exceptions.py`:
```python
class MarketplaceError(JedisosError):  # [JS-A003.9]
    """마켓플레이스/패키지 관련 에러."""
```

`src/jedisos/marketplace/manager.py`:
```python
"""
[JS-M001] jedisos.marketplace.manager
로컬 패키지 매니저 - scan/search/install/remove

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: pyyaml>=6.0
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from jedisos.core.exceptions import MarketplaceError
from jedisos.marketplace.models import PackageInfo, PackageMeta, PackageType
from jedisos.marketplace.scanner import PackageScanner

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger()


class LocalPackageManager:  # [JS-M001.1]
    """로컬 파일시스템 기반 패키지 매니저."""

    def __init__(self, tools_dir: Path | None = None) -> None:
        from pathlib import Path as _Path

        self.tools_dir = tools_dir or _Path("tools")
        self.scanner = PackageScanner(self.tools_dir)

    def list_packages(self, package_type: PackageType | None = None) -> list[PackageInfo]:  # [JS-M001.2]
        """설치된 패키지 목록을 반환합니다."""
        if package_type:
            return self.scanner.scan_type(package_type)
        return self.scanner.scan_all()

    def search(self, query: str) -> list[PackageInfo]:  # [JS-M001.3]
        """이름, 설명, 태그로 패키지를 검색합니다."""
        query_lower = query.lower()
        results: list[PackageInfo] = []

        for pkg in self.scanner.scan_all():
            if (
                query_lower in pkg.meta.name.lower()
                or query_lower in pkg.meta.description.lower()
                or any(query_lower in tag.lower() for tag in pkg.meta.tags)
            ):
                results.append(pkg)

        return results

    def get_package(self, name: str) -> PackageInfo | None:  # [JS-M001.4]
        """이름으로 패키지를 찾습니다."""
        for pkg in self.scanner.scan_all():
            if pkg.meta.name == name:
                return pkg
        return None

    def install(self, source_dir: Path, force: bool = False) -> dict[str, Any]:  # [JS-M001.5]
        """로컬 디렉토리에서 패키지를 설치합니다."""
        meta_path = source_dir / "jedisos-package.yaml"
        if not meta_path.exists():
            msg = f"jedisos-package.yaml이 없습니다: {source_dir}"
            raise MarketplaceError(msg)

        data = yaml.safe_load(meta_path.read_text())
        if "type" not in data:
            data["type"] = "skill"
        meta = PackageMeta(**data)

        target_dir = self.tools_dir / meta.type.dir_name / meta.name
        if target_dir.exists() and not force:
            msg = f"'{meta.name}'이(가) 이미 설치되어 있습니다. --force로 덮어쓸 수 있습니다."
            raise MarketplaceError(msg)

        if target_dir.exists():
            shutil.rmtree(target_dir)

        shutil.copytree(source_dir, target_dir)

        logger.info("package_installed", name=meta.name, version=meta.version, dir=str(target_dir))
        return {"status": "installed", "name": meta.name, "version": meta.version, "dir": str(target_dir)}

    def remove(self, name: str) -> dict[str, str]:  # [JS-M001.6]
        """패키지를 삭제합니다."""
        pkg = self.get_package(name)
        if not pkg:
            msg = f"패키지를 찾을 수 없습니다: {name}"
            raise MarketplaceError(msg)

        shutil.rmtree(pkg.directory)
        logger.info("package_removed", name=name)
        return {"status": "removed", "name": name}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_marketplace.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/jedisos/marketplace/manager.py src/jedisos/core/exceptions.py tests/unit/test_marketplace.py
git commit -m "feat(marketplace): [JS-M001] LocalPackageManager (install/remove/search)"
```

---

### Task 5: CLI `market` subcommand

**Files:**
- Modify: `src/jedisos/cli/main.py`
- Modify: `tests/unit/test_marketplace.py`

**Step 1: Write the failing test**

Append to `tests/unit/test_marketplace.py`:

```python
from typer.testing import CliRunner
from jedisos.cli.main import app

runner = CliRunner()


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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_marketplace.py::TestMarketCLI -v`
Expected: FAIL — no `market` subcommand

**Step 3: Write implementation**

Add to `src/jedisos/cli/main.py` (after the `update` command, before `if __name__`):

```python
# === Market 서브커맨드 === [JS-H001.8]
market_app = typer.Typer(name="market", help="로컬 패키지 매니저", no_args_is_help=True)
app.add_typer(market_app, name="market")


def _get_tools_dir() -> Path:
    """패키지 디렉토리를 환경변수 또는 기본값에서 가져옵니다."""
    import os
    return Path(os.environ.get("JEDISOS_TOOLS_DIR", "tools"))


@market_app.command("list")
def market_list(
    package_type: Annotated[str | None, typer.Option("--type", "-t", help="패키지 유형 필터")] = None,
) -> None:
    """설치된 패키지 목록을 표시합니다."""
    from jedisos.marketplace.manager import LocalPackageManager
    from jedisos.marketplace.models import PackageType as PT

    mgr = LocalPackageManager(_get_tools_dir())

    pt = None
    if package_type:
        try:
            pt = PT(package_type)
        except ValueError:
            err_console.print(f"알 수 없는 유형: {package_type}", style="red")
            raise typer.Exit(1) from None

    packages = mgr.list_packages(package_type=pt)

    if not packages:
        console.print("설치된 패키지가 없습니다.", style="yellow")
        return

    table = Table(title="설치된 패키지")
    table.add_column("이름", style="cyan")
    table.add_column("버전")
    table.add_column("유형", style="green")
    table.add_column("설명")

    for pkg in packages:
        table.add_row(pkg.meta.name, pkg.meta.version, pkg.meta.type.value, pkg.meta.description)

    console.print(table)


@market_app.command("search")
def market_search(
    query: Annotated[str, typer.Argument(help="검색어")],
) -> None:
    """패키지를 검색합니다 (이름/설명/태그)."""
    from jedisos.marketplace.manager import LocalPackageManager

    mgr = LocalPackageManager(_get_tools_dir())
    results = mgr.search(query)

    if not results:
        console.print(f"'{query}'에 대한 결과가 없습니다.", style="yellow")
        return

    table = Table(title=f"검색 결과: '{query}'")
    table.add_column("이름", style="cyan")
    table.add_column("버전")
    table.add_column("유형", style="green")
    table.add_column("설명")

    for pkg in results:
        table.add_row(pkg.meta.name, pkg.meta.version, pkg.meta.type.value, pkg.meta.description)

    console.print(table)


@market_app.command("info")
def market_info(
    name: Annotated[str, typer.Argument(help="패키지 이름")],
) -> None:
    """패키지 상세 정보를 표시합니다."""
    from jedisos.marketplace.manager import LocalPackageManager

    mgr = LocalPackageManager(_get_tools_dir())
    pkg = mgr.get_package(name)

    if not pkg:
        err_console.print(f"패키지를 찾을 수 없습니다: {name}", style="red")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold]{pkg.meta.name}[/bold] v{pkg.meta.version}\n\n"
        f"유형: {pkg.meta.type.value}\n"
        f"설명: {pkg.meta.description}\n"
        f"라이선스: {pkg.meta.license}\n"
        f"작성자: {pkg.meta.author}\n"
        f"태그: {', '.join(pkg.meta.tags) if pkg.meta.tags else '-'}\n"
        f"경로: {pkg.directory}",
        title="패키지 정보",
        border_style="cyan",
    ))


@market_app.command("validate")
def market_validate(
    directory: Annotated[Path, typer.Argument(help="패키지 디렉토리")],
) -> None:
    """패키지를 검증합니다."""
    from jedisos.marketplace.validator import PackageValidator

    if not directory.exists():
        err_console.print(f"디렉토리를 찾을 수 없습니다: {directory}", style="red")
        raise typer.Exit(1)

    validator = PackageValidator()
    result = asyncio.run(validator.validate(directory))

    if result.passed:
        console.print(f"[green]검증 통과:[/green] {result.package_name}")
    else:
        console.print(f"[red]검증 실패:[/red] {result.package_name}")
        for error in result.errors:
            console.print(f"  [red]x[/red] {error}")

    for warning in result.warnings:
        console.print(f"  [yellow]![/yellow] {warning}")

    if not result.passed:
        raise typer.Exit(1)


@market_app.command("install")
def market_install(
    directory: Annotated[Path, typer.Argument(help="설치할 패키지 디렉토리")],
    force: Annotated[bool, typer.Option("--force", "-f", help="이미 존재하면 덮어쓰기")] = False,
) -> None:
    """로컬 디렉토리에서 패키지를 설치합니다."""
    from jedisos.marketplace.manager import LocalPackageManager

    if not directory.exists():
        err_console.print(f"디렉토리를 찾을 수 없습니다: {directory}", style="red")
        raise typer.Exit(1)

    mgr = LocalPackageManager(_get_tools_dir())
    try:
        result = mgr.install(directory, force=force)
        console.print(f"[green]설치 완료:[/green] {result['name']} v{result['version']}")
        console.print(f"  경로: {result['dir']}")
    except Exception as e:
        err_console.print(f"설치 실패: {e}", style="red")
        raise typer.Exit(1) from e


@market_app.command("remove")
def market_remove(
    name: Annotated[str, typer.Argument(help="삭제할 패키지 이름")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="확인 없이 삭제")] = False,
) -> None:
    """패키지를 삭제합니다."""
    from jedisos.marketplace.manager import LocalPackageManager

    mgr = LocalPackageManager(_get_tools_dir())

    if not yes:
        confirm = typer.confirm(f"'{name}' 패키지를 삭제할까요?")
        if not confirm:
            console.print("삭제를 취소합니다.", style="yellow")
            raise typer.Exit()

    try:
        result = mgr.remove(name)
        console.print(f"[green]삭제 완료:[/green] {result['name']}")
    except Exception as e:
        err_console.print(f"삭제 실패: {e}", style="red")
        raise typer.Exit(1) from e
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_marketplace.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/jedisos/cli/main.py tests/unit/test_marketplace.py
git commit -m "feat(cli): [JS-H001.8] market 서브커맨드 (list/search/info/validate/install/remove)"
```

---

### Task 6: Full verification + final commit

**Step 1: Run all tests**

```bash
pytest tests/unit/ -v --timeout=30
```

Expected: All pass (previous 221 + new marketplace tests)

**Step 2: Run lint + security**

```bash
ruff check src/jedisos/marketplace/ tests/unit/test_marketplace.py
ruff format --check src/jedisos/marketplace/ tests/unit/test_marketplace.py
bandit -r src/jedisos/marketplace/ -c pyproject.toml
```

Expected: Clean

**Step 3: Fix any issues, then final verification**

```bash
make check
```

Expected: All green
