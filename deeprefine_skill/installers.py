"""Installers for agent-platform skill files (Cursor, Copilot CLI).

Each platform has a source SKILL.md variant (SKILL.md for Cursor,
SKILL_COPILOT.md for Copilot CLI) bundled in the wheel or found at the
repo root during editable installs.  The install/remove functions copy
the appropriate variant into the platform-specific directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

_SKILL_MD_NAME = "SKILL.md"
_SKILL_COPILOT_MD_NAME = "SKILL_COPILOT.md"

# ---------------------------------------------------------------------------
# Source-file resolution
# ---------------------------------------------------------------------------


def _resolve_skill_source(filename: str) -> Path:
    """Return *filename* from the package directory, or fall back to repo root."""
    bundled = Path(__file__).resolve().parent / filename
    if bundled.is_file():
        return bundled
    repo_root = Path(__file__).resolve().parents[1]
    fallback = repo_root / filename
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(
        f"Missing {filename} (expected next to deeprefine_skill/ or repo root)."
    )


def skill_md_path() -> Path:
    """Return the path to the Cursor SKILL.md source."""
    return _resolve_skill_source(_SKILL_MD_NAME)


def skill_md_path_copilot() -> Path:
    """Return the path to the Copilot CLI SKILL_COPILOT.md source."""
    return _resolve_skill_source(_SKILL_COPILOT_MD_NAME)


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------


def install_cursor_skill(*, project: bool) -> Path:
    """Install the Cursor skill into ``.cursor/skills/deeprefine/``.

    Parameters
    ----------
    project : bool
        If *True*, install under the current working directory
        (``.cursor/skills/deeprefine/``).  If *False*, install under
        ``~/.cursor/skills/deeprefine/`` (user-wide).

    Returns
    -------
    Path
        Destination path of the installed ``SKILL.md``.
    """
    src = skill_md_path()
    if project:
        dest_dir = Path.cwd() / ".cursor" / "skills" / "deeprefine"
    else:
        dest_dir = Path.home() / ".cursor" / "skills" / "deeprefine"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / _SKILL_MD_NAME)
    return dest_dir / _SKILL_MD_NAME


def uninstall_cursor_skill(*, project: bool) -> bool:
    """Remove a previously installed Cursor skill.

    Returns
    -------
    bool
        *True* if a file was removed, *False* if nothing was installed.
    """
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


# ---------------------------------------------------------------------------
# Copilot CLI
# ---------------------------------------------------------------------------


def install_copilot_skill(*, project: bool) -> Path:
    """Install the Copilot CLI skill into ``.github/skills/deeprefine/``.

    Parameters
    ----------
    project : bool
        If *True*, install under the current working directory
        (``.github/skills/deeprefine/``).  If *False*, install under
        ``~/.copilot/skills/deeprefine/`` (user-wide).

    Returns
    -------
    Path
        Destination path of the installed ``SKILL.md``.
    """
    src = skill_md_path_copilot()
    if project:
        dest_dir = Path.cwd() / ".github" / "skills" / "deeprefine"
    else:
        dest_dir = Path.home() / ".copilot" / "skills" / "deeprefine"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / _SKILL_MD_NAME)
    return dest_dir / _SKILL_MD_NAME


def uninstall_copilot_skill(*, project: bool) -> bool:
    """Remove a previously installed Copilot CLI skill.

    Returns
    -------
    bool
        *True* if a file was removed, *False* if nothing was installed.
    """
    if project:
        dest = Path.cwd() / ".github" / "skills" / "deeprefine" / _SKILL_MD_NAME
    else:
        dest = Path.home() / ".copilot" / "skills" / "deeprefine" / _SKILL_MD_NAME
    if dest.is_file():
        dest.unlink()
        for parent in [dest.parent, dest.parent.parent]:
            try:
                parent.rmdir()
            except OSError:
                pass
        return True
    return False
