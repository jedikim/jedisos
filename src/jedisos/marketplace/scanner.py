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
