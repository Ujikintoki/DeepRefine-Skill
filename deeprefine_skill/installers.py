from __future__ import annotations

import shutil
from pathlib import Path

_SKILL_MD_NAME = "SKILL.md"


def skill_md_path() -> Path:
    """SKILL.md bundled in the wheel, or repo root when doing editable install."""
    bundled = Path(__file__).resolve().parent / _SKILL_MD_NAME
    if bundled.is_file():
        return bundled
    repo_root = Path(__file__).resolve().parents[1]
    fallback = repo_root / _SKILL_MD_NAME
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(
        f"Missing {_SKILL_MD_NAME} (expected next to deeprefine_skill/ or repo root)."
    )


def install_cursor_skill(*, project: bool) -> Path:
    src = skill_md_path()
    if project:
        dest_dir = Path.cwd() / ".cursor" / "skills" / "deeprefine"
    else:
        dest_dir = Path.home() / ".cursor" / "skills" / "deeprefine"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / _SKILL_MD_NAME)
    return dest_dir / _SKILL_MD_NAME


def uninstall_cursor_skill(*, project: bool) -> bool:
    if project:
        dest = Path.cwd() / ".cursor" / "skills" / "deeprefine" / _SKILL_MD_NAME
    else:
        dest = Path.home() / ".cursor" / "skills" / "deeprefine" / _SKILL_MD_NAME
    if dest.is_file():
        dest.unlink()
        for parent in [dest.parent, dest.parent.parent]:
            try:
                parent.rmdir()
            except OSError:
                pass
        return True
    return False
