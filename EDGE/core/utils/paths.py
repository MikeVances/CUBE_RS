#!/usr/bin/env python3
"""
Path helpers for EDGE repo, to keep imports and file paths stable
whether EDGE lives as a subfolder in a monorepo or as a standalone repo.
"""
from __future__ import annotations

from pathlib import Path


def get_project_root(start: Path | None = None) -> Path:
    """Detect project root by walking up looking for typical markers.

    Markers:
    - "core/config_manager.py" and "config/"
    - fallback to directory containing "EDGE" (monorepo layout)
    - fallback to filesystem root of current file
    """
    cur = (start or Path(__file__)).resolve()
    candidates: list[Path] = []
    for p in [cur] + list(cur.parents):
        if (p / "core" / "config_manager.py").exists() and (p / "config").exists():
            candidates.append(p)
    if candidates:
        # Prefer repository root if a Git directory is available one level up.
        for candidate in candidates:
            parent = candidate.parent
            if (parent / ".git").exists():
                return parent
        for candidate in candidates:
            if (candidate / ".git").exists():
                return candidate
        return candidates[0]
    # Monorepo fallback: choose the parent containing the EDGE folder
    for p in [cur] + list(cur.parents):
        if (p / "EDGE").exists() and (p / "EDGE" / "core").exists():
            return p / "EDGE"
    # Last resort: go  up to the first parent that has a "config" folder
    for p in [cur] + list(cur.parents):
        if (p / "config").exists():
            return p
    return cur.parent


def resolve_under_root(rel_or_abs: str) -> str:
    """Resolve a (possibly relative) path under the project root.

    Policy for bare filenames (no directory component):
    - Database files (*.db, *.sqlite, *.sqlite3) → place under `data/`
    - Log files (*.log) → place under `logs/`
    - Otherwise → place at project root
    """
    p = Path(rel_or_abs)
    if p.is_absolute():
        return str(p)
    root = get_project_root()
    # Bare filename → route by extension
    if p.parent == Path('.'):
        ext = p.suffix.lower()
        if ext in {'.db', '.sqlite', '.sqlite3'}:
            target = root / 'data' / p.name
        elif ext == '.log':
            target = root / 'logs' / p.name
        else:
            target = root / p.name
    else:
        target = root / p
    target.parent.mkdir(parents=True, exist_ok=True)
    return str(target)
