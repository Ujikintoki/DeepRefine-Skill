"""Integration tests for DeepSeek Harness (dsh) skill — CLI layer + frontmatter.

dsh discovers skills under ``.dsh/skills/<name>/SKILL.md`` (project) or
``~/.dsh/skills/<name>/SKILL.md`` (user) and follows the same Agent Skills
contract as Claude Code: YAML frontmatter with a kebab-case ``name`` and a
``description`` the model uses to decide when to invoke the skill.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DSH = REPO_ROOT / "deeprefine_skill" / "dsh_skill" / "SKILL.md"
REFERENCES_DIR = REPO_ROOT / "deeprefine_skill" / "dsh_skill" / "references"
EXPECTED_REFERENCES: tuple[str, ...] = (
    "deeprefine-workflow.md",
    "llm-prompts.md",
    "trace-and-commands.md",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse YAML frontmatter from a markdown file (between ``---`` fences)."""
    parts = text.split("---")
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``python -m deeprefine_skill.cli`` with given args."""
    cmd = [sys.executable, "-m", "deeprefine_skill.cli", *args]
    return subprocess.run(
        cmd,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Frontmatter tests (no filesystem side-effects)
# ---------------------------------------------------------------------------


class TestSkillFrontmatter:
    """Verify dsh SKILL.md frontmatter satisfies the dsh skill contract."""

    def test_name_field_kebab_case(self) -> None:
        """Required field: ``name`` must be kebab-case (lowercase + hyphens)."""
        text = SKILL_DSH.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert "name" in fm, "missing required 'name' field"
        name: str = fm["name"]
        assert name == "deeprefine"
        assert all(c.islower() or c.isdigit() or c == "-" for c in name), (
            f"name {name!r} is not kebab-case (dsh ignores non-kebab names)"
        )

    def test_description_field_present(self) -> None:
        """Required field: ``description`` (1-1024 chars)."""
        text = SKILL_DSH.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert "description" in fm, "missing required 'description' field"
        desc = fm["description"]
        if isinstance(desc, str):
            assert 1 <= len(desc) <= 1024, f"description length {len(desc)} out of range [1,1024]"

    def test_no_allowed_tools_leak(self) -> None:
        """Claude Code-specific field must NOT leak into the dsh skill."""
        text = SKILL_DSH.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert "allowed-tools" not in fm, (
            "allowed-tools is Claude Code-only and must not appear in dsh SKILL.md"
        )

    def test_model_invocation_enabled(self) -> None:
        """The model must be able to auto-invoke the skill in dsh."""
        text = SKILL_DSH.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert fm.get("disable-model-invocation") is False, (
            "disable-model-invocation must be false for auto-invocation in dsh"
        )

    @pytest.mark.parametrize("ref_name", EXPECTED_REFERENCES)
    def test_reference_files_exist(self, ref_name: str) -> None:
        """Every reference linked from SKILL.md must be bundled."""
        ref_path = REFERENCES_DIR / ref_name
        assert ref_path.is_file(), f"reference file missing: {ref_path}"
        assert ref_path.read_text(encoding="utf-8").strip(), (
            f"reference file empty: {ref_path}"
        )


# ---------------------------------------------------------------------------
# Installer tests (temporary directories, no side-effects)
# ---------------------------------------------------------------------------


class TestDshInstall:
    """End-to-end install/uninstall in isolated temp dirs."""

    def _run_install(self, cwd: Path, *, project: bool = True) -> subprocess.CompletedProcess[str]:
        args = ["dsh", "install"]
        if project:
            args.append("--project")
        return _run_cli(*args, cwd=cwd)

    def _run_uninstall(self, cwd: Path, *, project: bool = True) -> subprocess.CompletedProcess[str]:
        args = ["dsh", "uninstall"]
        if project:
            args.append("--project")
        return _run_cli(*args, cwd=cwd)

    def test_install_creates_skill_file(self, tmp_path: Path) -> None:
        """Install creates .dsh/skills/deeprefine/SKILL.md."""
        skill_dest = tmp_path / ".dsh" / "skills" / "deeprefine" / "SKILL.md"
        result = self._run_install(cwd=tmp_path)
        assert result.returncode == 0, f"install failed: {result.stderr}"
        assert skill_dest.is_file(), f"SKILL.md not created at {skill_dest}"

    def test_install_creates_references(self, tmp_path: Path) -> None:
        """Install creates all reference files under references/."""
        result = self._run_install(cwd=tmp_path)
        assert result.returncode == 0, f"install failed: {result.stderr}"
        for ref_name in EXPECTED_REFERENCES:
            ref_path = tmp_path / ".dsh" / "skills" / "deeprefine" / "references" / ref_name
            assert ref_path.is_file(), f"reference {ref_name} not created at {ref_path}"

    def test_uninstall_removes_skill_file(self, tmp_path: Path) -> None:
        """Uninstall removes .dsh/skills/deeprefine/SKILL.md."""
        self._run_install(cwd=tmp_path)
        skill_dest = tmp_path / ".dsh" / "skills" / "deeprefine" / "SKILL.md"
        assert skill_dest.is_file(), "precondition: install must succeed"

        result = self._run_uninstall(cwd=tmp_path)
        assert result.returncode == 0, f"uninstall failed: {result.stderr}"
        assert not skill_dest.exists(), f"SKILL.md not removed: {skill_dest}"

    def test_uninstall_removes_references(self, tmp_path: Path) -> None:
        """Uninstall removes all reference files."""
        self._run_install(cwd=tmp_path)
        for ref_name in EXPECTED_REFERENCES:
            ref_path = tmp_path / ".dsh" / "skills" / "deeprefine" / "references" / ref_name
            assert ref_path.is_file(), f"precondition: {ref_name} must exist"

        result = self._run_uninstall(cwd=tmp_path)
        assert result.returncode == 0
        for ref_name in EXPECTED_REFERENCES:
            ref_path = tmp_path / ".dsh" / "skills" / "deeprefine" / "references" / ref_name
            assert not ref_path.exists(), f"reference {ref_name} not removed"

    def test_uninstall_clean_dirs(self, tmp_path: Path) -> None:
        """Uninstall cleans up empty parent directories."""
        self._run_install(cwd=tmp_path)
        self._run_uninstall(cwd=tmp_path)

        skill_deep_dir = tmp_path / ".dsh" / "skills" / "deeprefine"
        assert not skill_deep_dir.exists(), f"skill dir not cleaned: {skill_deep_dir}"

    def test_install_idempotent(self, tmp_path: Path) -> None:
        """Install twice should succeed (overwrite)."""
        r1 = self._run_install(cwd=tmp_path)
        r2 = self._run_install(cwd=tmp_path)
        assert r1.returncode == 0
        assert r2.returncode == 0, f"second install failed: {r2.stderr}"
        skill_dest = tmp_path / ".dsh" / "skills" / "deeprefine" / "SKILL.md"
        assert skill_dest.is_file()


# ---------------------------------------------------------------------------
# CLI help tests
# ---------------------------------------------------------------------------


class TestCliHelp:
    """Verify CLI --help output for dsh subcommands."""

    def test_dsh_help_shows_subcommands(self) -> None:
        """``deeprefine dsh --help`` shows install and uninstall."""
        result = _run_cli("dsh", "--help")
        assert result.returncode == 0
        out = result.stdout
        assert "install" in out
        assert "uninstall" in out

    def test_install_help_shows_flags(self) -> None:
        """``deeprefine dsh install --help`` shows --project and --user."""
        result = _run_cli("dsh", "install", "--help")
        assert result.returncode == 0
        out = result.stdout
        assert "--project" in out, f"missing --project flag in help: {out}"
        assert "--user" in out, f"missing --user flag in help: {out}"

    def test_uninstall_help_shows_flags(self) -> None:
        """``deeprefine dsh uninstall --help`` shows --project and --user."""
        result = _run_cli("dsh", "uninstall", "--help")
        assert result.returncode == 0
        out = result.stdout
        assert "--project" in out
        assert "--user" in out
