# Changelog

## 2026-06-18 — P0: Copilot CLI Skill Adaptation

### Added
- **`deeprefine_skill/SKILL_COPILOT.md`**: Copilot CLI agent skill file.  Shares
  the identical Reafiner control flow, prompt templates, constants, and
  FORBIDDEN rules as the Cursor variant (`SKILL.md`), with the following
  platform-specific adjustments:
  - Frontmatter declares `allowed-tools: shell`, pre-approving `deeprefine`
    and `graphify` CLI invocations without per-command confirmation dialogs.
  - Removed `disable-model-invocation` field (Cursor-specific; absent from the
    Copilot CLI skill schema).
  - Description rewritten for Copilot's automatic skill-to-task matching
    (description-based dispatch in addition to explicit `/deeprefine`
    invocation).
  - Added preamble noting this is the Copilot variant and that additional
    scripts in the skill directory are auto-discovered.
- **`deeprefine copilot install` / `deeprefine copilot uninstall`** CLI
  subcommands.  Mirror the existing `cursor install` / `cursor uninstall`
  interface with `--project` (`.github/skills/deeprefine/`) and `--user`
  (`~/.copilot/skills/deeprefine/`) scope flags.  Default scope: `--project`.

### Changed
- **`deeprefine_skill/installers.py`**: Extracted shared source-file resolution
  into `_resolve_skill_source()`; added `skill_md_path_copilot()`,
  `install_copilot_skill()`, and `uninstall_copilot_skill()`.  Existing
  Cursor functions are unchanged.
- **`deeprefine_skill/cli.py`**: Added `cmd_copilot_install` and
  `cmd_copilot_uninstall` handlers; registered `copilot` subparser group.
  Module docstring expanded.
- **`pyproject.toml`**: `package-data` now includes `SKILL_COPILOT.md`;
  keywords extended with `copilot` and `copilot-cli`; description updated.
- **`MANIFEST.in`**: Added `deeprefine_skill/SKILL_COPILOT.md` for source
  distribution inclusion.
