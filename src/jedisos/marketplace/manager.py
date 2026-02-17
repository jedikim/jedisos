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

    def list_packages(
        self, package_type: PackageType | None = None
    ) -> list[PackageInfo]:  # [JS-M001.2]
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
        return {
            "status": "installed",
            "name": meta.name,
            "version": meta.version,
            "dir": str(target_dir),
        }

    def remove(self, name: str) -> dict[str, str]:  # [JS-M001.6]
        """패키지를 삭제합니다."""
        pkg = self.get_package(name)
        if not pkg:
            msg = f"패키지를 찾을 수 없습니다: {name}"
            raise MarketplaceError(msg)

        shutil.rmtree(pkg.directory)
        logger.info("package_removed", name=name)
        return {"status": "removed", "name": name}
