# DeepRefine Skill for DeepSeek Harness (dsh)

DeepRefine-Skill can be installed as a DeepSeek Harness (dsh) skill. This adds
the `/deeprefine` agent-native refinement workflow to dsh while keeping the
existing platform adapters (Cursor, Copilot CLI, Gemini CLI, Codex, Claude
Code, OpenCode) unchanged.

## Prerequisites

```bash
pip install -e /path/to/DeepRefine-Skill   # or: pip install deeprefine-cli
```

The skill is a plain Markdown bundle and does not require any dsh plugin or
Node.js code.

## Setup

Install into the current project:

```bash
deeprefine dsh install
# → .dsh/skills/deeprefine/SKILL.md + references/
```

Install for all projects:

```bash
deeprefine dsh install --user
# → ~/.dsh/skills/deeprefine/
```

Remove with:

```bash
deeprefine dsh uninstall
```

dsh discovers skills under `<projectRoot>/.dsh/skills` (project) and
`~/.dsh/skills` (user). The skill is picked up automatically; a running session
hot-refreshes its catalog after install, so no restart is required.

## Usage

From a knowledge-base project root where `graphify-out/graph.json` exists:

```text
/deeprefine
```

The model loads the skill and runs the canonical DeepRefine loop: sync memory
→ select pending queries → retrieve → `<judge>` → (multi-hop) error abduction →
`<refinement>` → `loop validate` → `review`. A normal `/deeprefine` turn is
dry-run only and stops at the HIGH/MEDIUM/LOW report for explicit approval; it
never calls `deeprefine apply` on its own.

## Notes

- `/deeprefine` expects a project with `graphify-out/graph.json`; without one it
  reports that Graphify outputs are missing.
- `deeprefine apply` aborts and writes nothing if any LOW-confidence action is
  present. Use `--allow-low-confidence` only with explicit user approval.
- The dsh skill is a platform adapter for the same DeepRefine control flow; see
  `deeprefine_skill/dsh_skill/references/` for the workflow, prompts, and trace
  schema it loads on demand.
