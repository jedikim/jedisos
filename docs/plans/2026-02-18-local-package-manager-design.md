# Phase 11: Local-Only Package Manager Design

**Date:** 2026-02-18
**Status:** Approved

## Context

Phase 11 was originally designed as a remote marketplace (marketplace.jedisos.com).
The user decided to simplify to a **local-only package manager** — no external site, no remote registry.

Phase 10 (Forge) already provides tool loading, security checking, validation, and hot-reload.
Phase 11 builds on top of Forge to manage 6 package types locally via filesystem.

## Approach

**Option A: Filesystem-based local registry** (chosen over SQLite or JSON manifest).

Each package's `jedisos-package.yaml` is the registry entry itself.
No separate database or index file — the filesystem is the source of truth.

## Directory Structure

```
tools/
├── skills/           # Skill (tool.yaml + tool.py)
├── prompts/          # Prompt Pack (prompts.yaml)
├── workflows/        # Workflow (workflow.yaml)
├── identities/       # Identity Pack (IDENTITY.md)
├── mcp-servers/      # MCP Server (docker-compose.yaml)
├── bundles/          # Bundle (references to other packages)
└── generated/        # Forge auto-generated Skills (existing)
```

## Module Structure

```
src/jedisos/marketplace/
├── __init__.py
├── models.py      [JS-M004] 6 package types, PackageMeta, PackageInfo
├── manager.py     [JS-M001] LocalPackageManager (scan/install/remove/search)
├── validator.py   [JS-M003] PackageValidator (reuses Forge security)
└── scanner.py     [JS-M002] PackageScanner (filesystem scan + metadata)
```

No `client.py` (no remote API). No `publisher.py` (no remote upload).

## Core Classes

**LocalPackageManager** [JS-M001]:
- `scan()` — scan tools/ directory, return all packages
- `search(query, type)` — filter by name/description/tags
- `get_package(name)` — get specific package details
- `install(source_dir, name)` — copy from local directory + validate
- `remove(name)` — delete package directory
- `validate(package_dir)` — run Forge security + metadata checks

**PackageScanner** [JS-M002]:
- `scan_all()` — traverse 6 type directories, parse jedisos-package.yaml
- `scan_type(package_type)` — scan specific type only

**PackageValidator** [JS-M003]:
- Reuses `CodeSecurityChecker` from Forge for Skill packages
- Validates metadata (required fields, allowed licenses)
- Checks docs (README.md presence)

**Models** [JS-M004]:
- `PackageType` enum: skill, mcp_server, prompt_pack, workflow, identity_pack, bundle
- `PackageMeta`: name, version, description, type, license, tags, dependencies
- `PackageInfo`: meta + directory path + installed status
- `ALLOWED_LICENSES`: MIT, Apache-2.0, BSD-3-Clause

## CLI Commands

```bash
jedisos market list [--type TYPE]        # List installed packages
jedisos market search QUERY              # Search by name/description/tags
jedisos market info NAME                 # Package details
jedisos market validate DIR              # Validate before install
jedisos market install DIR               # Install from local directory
jedisos market remove NAME               # Remove package
```

No publish, review, or update commands (remote-only features removed).

## Testing

All tests use `tmp_path` fixture — no httpx mocks, no external services.
Tests cover: models, scanner, validator, manager, CLI commands.
