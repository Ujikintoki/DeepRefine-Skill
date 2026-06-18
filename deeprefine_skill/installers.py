from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_SKILL_MD_NAME = "SKILL.md"
_GEMINI_EXTENSION_NAME = "deeprefine-skill"


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


def gemini_extension_path(*, prefer_repo: bool = True) -> Path:
    """
    Return a Gemini CLI extension root.

    In editable/source checkouts, the repository root is preferred because it can
    be linked with `gemini extensions link .`. In wheels, use the bundled
    template under deeprefine_skill/gemini_extension/.
    """
    repo_root = Path(__file__).resolve().parents[1]
    if prefer_repo and (repo_root / "gemini-extension.json").is_file():
        return repo_root
    bundled = Path(__file__).resolve().parent / "gemini_extension"
    if (bundled / "gemini-extension.json").is_file():
        return bundled
    if (repo_root / "gemini-extension.json").is_file():
        return repo_root
    raise FileNotFoundError(
        "Missing Gemini extension template. Expected either repo root "
        "gemini-extension.json or deeprefine_skill/gemini_extension/."
    )


def _copy_tree_clean(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


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


def _gemini_executable() -> str:
    exe = shutil.which("gemini")
    if not exe:
        raise FileNotFoundError(
            "Gemini CLI executable `gemini` was not found. Install it first with:\n"
            "  npm install -g @google/gemini-cli"
        )
    return exe


def _run_gemini_extensions(args: list[str]) -> subprocess.CompletedProcess[str]:
    exe = _gemini_executable()
    return subprocess.run([exe, "extensions", *args], text=True)


def copy_gemini_extension(target_dir: Path | None = None) -> Path:
    """Manual fallback: copy extension files under ~/.gemini/extensions."""
    src = gemini_extension_path(prefer_repo=False)
    if target_dir is None:
        dest = Path.home() / ".gemini" / "extensions" / _GEMINI_EXTENSION_NAME
    else:
        dest = Path(target_dir).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    _copy_tree_clean(src, dest)
    return dest


def remove_copied_gemini_extension(target_dir: Path | None = None) -> bool:
    if target_dir is None:
        dest = Path.home() / ".gemini" / "extensions" / _GEMINI_EXTENSION_NAME
    else:
        dest = Path(target_dir).expanduser().resolve()
    if dest.exists():
        shutil.rmtree(dest)
        return True
    return False


def link_gemini_extension(source: Path | None = None) -> Path:
    """Use Gemini CLI's official manager to link an extension directory."""
    src = (source or gemini_extension_path(prefer_repo=True)).expanduser().resolve()
    if not (src / "gemini-extension.json").is_file():
        raise FileNotFoundError(f"Not a Gemini extension root: {src}")
    cp = _run_gemini_extensions(["link", str(src)])
    if cp.returncode != 0:
        raise RuntimeError(f"`gemini extensions link {src}` failed with exit code {cp.returncode}")
    return src


def install_gemini_extension(source: Path | None = None, *, consent: bool = True) -> Path:
    """Use Gemini CLI's official manager to install a copied extension."""
    src = (source or gemini_extension_path(prefer_repo=False)).expanduser().resolve()
    if not (src / "gemini-extension.json").is_file():
        raise FileNotFoundError(f"Not a Gemini extension root: {src}")
    cmd = ["install", str(src)]
    if consent:
        cmd.append("--consent")
    cp = _run_gemini_extensions(cmd)
    if cp.returncode != 0:
        raise RuntimeError(
            f"`gemini extensions {' '.join(cmd)}` failed with exit code {cp.returncode}"
        )
    return src


def uninstall_gemini_extension(*, copy_only: bool = False, target_dir: Path | None = None) -> bool:
    """Uninstall through Gemini CLI manager, or remove manual copied files."""
    if copy_only:
        return remove_copied_gemini_extension(target_dir)
    cp = _run_gemini_extensions(["uninstall", _GEMINI_EXTENSION_NAME])
    if cp.returncode == 0:
        return True
    # Also clean up the old manual-copy fallback if present.
    return remove_copied_gemini_extension(target_dir)
