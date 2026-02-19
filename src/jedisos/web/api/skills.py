"""
[JS-W007] jedisos.web.api.skills
Skill(도구) 관리 API - 목록, 삭제, 활성/비활성

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

import structlog
import yaml
from fastapi import APIRouter, HTTPException

logger = structlog.get_logger()

router = APIRouter()

# Skill 디렉토리: tools/ + tools/generated/
_TOOLS_DIR = Path(os.environ.get("JEDISOS_DATA_DIR", ".")) / "tools"
_BUILTIN_TOOLS_DIR = Path("tools")  # 프로젝트 루트의 tools/


def _get_tools_dirs() -> list[Path]:  # [JS-W007.1]
    """모든 Skill 검색 디렉토리를 반환합니다."""
    dirs = []
    for d in [_BUILTIN_TOOLS_DIR, _TOOLS_DIR]:
        if d.exists():
            dirs.append(d)
    return dirs


def _scan_skills() -> list[dict[str, Any]]:  # [JS-W007.2]
    """모든 Skill을 스캔하여 메타데이터 목록을 반환합니다."""
    skills: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for tools_dir in _get_tools_dirs():
        for category_dir in sorted(tools_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            if category_dir.name.startswith(".") or category_dir.name == "__pycache__":
                continue

            # skills/, generated/ 등 카테고리 디렉토리 내부 검색
            if category_dir.name in ("skills", "generated"):
                for skill_dir in sorted(category_dir.iterdir()):
                    if skill_dir.is_dir() and (skill_dir / "tool.py").exists():
                        info = _read_skill_info(skill_dir, category_dir.name)
                        if info and info["name"] not in seen_names:
                            skills.append(info)
                            seen_names.add(info["name"])
            elif (category_dir / "tool.py").exists():
                # 루트 레벨 skill (tools/weather/ 등)
                info = _read_skill_info(category_dir, "custom")
                if info and info["name"] not in seen_names:
                    skills.append(info)
                    seen_names.add(info["name"])

    return skills


def _read_skill_info(skill_dir: Path, category: str) -> dict[str, Any] | None:  # [JS-W007.3]
    """Skill 디렉토리에서 메타데이터를 읽습니다."""
    tool_py = skill_dir / "tool.py"
    if not tool_py.exists():
        return None

    info: dict[str, Any] = {
        "name": skill_dir.name,
        "category": category,
        "path": str(skill_dir),
        "enabled": not (skill_dir / ".disabled").exists(),
        "auto_generated": category == "generated",
        "description": "",
        "version": "1.0.0",
        "author": "unknown",
        "tags": [],
    }

    # tool.yaml에서 메타데이터 로드
    yaml_path = skill_dir / "tool.yaml"
    if yaml_path.exists():
        try:
            data = yaml.safe_load(yaml_path.read_text())
            if data:
                info["description"] = data.get("description", "")
                info["version"] = data.get("version", "1.0.0")
                info["author"] = data.get("author", "unknown")
                info["tags"] = data.get("tags", [])
                info["auto_generated"] = data.get("auto_generated", category == "generated")
        except Exception as e:
            logger.warning("skill_yaml_parse_error", path=str(yaml_path), error=str(e))

    return info


@router.get("/")  # [JS-W007.4]
async def list_skills() -> dict[str, Any]:
    """설치된 Skill 목록을 반환합니다."""
    skills = _scan_skills()
    return {
        "skills": skills,
        "total": len(skills),
        "active": sum(1 for s in skills if s["enabled"]),
    }


@router.delete("/{name}")  # [JS-W007.5]
async def delete_skill(name: str) -> dict[str, str]:
    """Skill을 삭제합니다. 자동 생성된 Skill만 삭제 가능합니다."""
    skills = _scan_skills()
    skill = next((s for s in skills if s["name"] == name), None)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}'을(를) 찾을 수 없습니다.")

    if not skill.get("auto_generated"):
        raise HTTPException(status_code=403, detail="수동으로 설치한 Skill은 삭제할 수 없습니다.")

    # 경로 traversal 방지: generated 디렉토리 안에 있는지 검증
    skill_path = Path(skill["path"]).resolve()
    allowed_dirs = [
        (_BUILTIN_TOOLS_DIR / "generated").resolve(),
        (_TOOLS_DIR / "generated").resolve(),
    ]
    if not any(str(skill_path).startswith(str(d)) for d in allowed_dirs):
        logger.warning("skill_delete_path_traversal_blocked", name=name, path=str(skill_path))
        raise HTTPException(status_code=403, detail="허용되지 않은 경로입니다.")

    if not re.match(r"^[a-zA-Z0-9_\-]+$", name):
        raise HTTPException(status_code=400, detail="잘못된 Skill 이름 형식입니다.")

    if not skill_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Skill 디렉토리를 찾을 수 없습니다: {skill_path}"
        )

    # 삭제 전 메타정보 보존 (메모리 기록용)
    description = skill.get("description", "")

    shutil.rmtree(skill_path)
    logger.info("skill_deleted", name=name, path=str(skill_path))

    # 메모리에 삭제 이력 기록 (재생성 방지)
    await _record_skill_deletion(name, description)

    return {"status": "deleted", "name": name}


@router.put("/{name}/toggle")  # [JS-W007.6]
async def toggle_skill(name: str) -> dict[str, Any]:
    """Skill 활성화/비활성화를 토글합니다."""
    skills = _scan_skills()
    skill = next((s for s in skills if s["name"] == name), None)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}'을(를) 찾을 수 없습니다.")

    skill_path = Path(skill["path"])
    disabled_marker = skill_path / ".disabled"

    if disabled_marker.exists():
        disabled_marker.unlink()
        enabled = True
    else:
        disabled_marker.touch()
        enabled = False

    logger.info("skill_toggled", name=name, enabled=enabled)
    return {"name": name, "enabled": enabled}


async def _record_skill_deletion(name: str, description: str) -> None:  # [JS-W007.7]
    """삭제된 스킬 정보를 메모리에 기록합니다.

    SkillGenerator.retain_skill_deletion()을 호출하여 동일 스킬 재생성을 방지합니다.
    메모리 연결 실패 시에도 삭제 자체는 완료됩니다.
    """
    try:
        from jedisos.forge.generator import SkillGenerator
        from jedisos.memory.zvec_memory import ZvecMemory

        memory = ZvecMemory()
        generator = SkillGenerator(memory=memory)
        await generator.retain_skill_deletion(tool_name=name, description=description)
        await memory.close()
    except Exception as e:
        logger.warning("skill_deletion_record_failed", name=name, error=str(e))
