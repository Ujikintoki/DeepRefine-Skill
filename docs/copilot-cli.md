# DeepRefine Skill for GitHub Copilot CLI

DeepRefine-Skill works as a GitHub Copilot CLI agent skill.  Install it into
`.github/skills/deeprefine/` and Copilot auto-discovers and loads it when the
user asks to refine, diagnose, or improve a Graphify / LLM-Wiki knowledge
graph.

## Prerequisites

```bash
pip install deeprefine-cli
# The target project must have graphify-out/graph.json
```

## One-time setup

From your KB project root (the directory containing `graphify-out/`):

```bash
deeprefine copilot install --project
```

This copies the Copilot-variant skill file into `.github/skills/deeprefine/SKILL.md`.
The frontmatter declares `allowed-tools: shell`, so `deeprefine` and `graphify`
commands run without per-invocation confirmation prompts.

After installing or upgrading the package, reload skills inside Copilot CLI:

```text
/skills reload
/skills info deeprefine
```

To install the skill for all projects (user-wide):

```bash
deeprefine copilot install --user
# installs to ~/.copilot/skills/deeprefine/SKILL.md
```

## Mode detection

Copilot CLI does not natively expose sub-commands like `/deeprefine:review`.
Instead, the skill uses keyword-based mode detection from the user's message:

| Mode | Trigger keywords | Behaviour |
|------|-----------------|-----------|
| **Full workflow** | `/deeprefine`, "refine", "improve", "fix", "diagnose" | Full refinement loop for all pending queries; stops after dry-run review; asks for explicit approval before writing `graph.json` |
| **Review only** | "review", "check", "audit", "inspect", "dry-run", "what would change" | Reads trace and refinement files; shows HIGH/MEDIUM/LOW evidence report; does not modify any files |
| **Apply only** | "approve", "apply", "write", "go ahead", "proceed", "yes apply" | Runs `deeprefine apply` only after a prior review; requires explicit user approval in the current message |

A previous `/deeprefine` invocation does not count as approval.  The user must
explicitly approve in a follow-up message.

## Usage

### Default pending-query workflow

```text
/deeprefine
```

The agent runs:

1. `deeprefine history sync-memory`
2. Loads all pending queries from `history.jsonl`
3. For each query: graphify retrieval → k-hop expansion → judgement loop
4. For refinement-path queries: abduction → refinement → validate → review → **HARD STOP**
5. Presents the review report with HIGH/MEDIUM/LOW labels, evidence, and warnings
6. Asks for explicit user approval

### Reviewing proposed changes

```text
Review the refinement actions for the data loading query.
```

The agent runs `deeprefine review` and presents the evidence report without
modifying `graph.json`.

### Applying approved changes

After reviewing, explicitly approve:

```text
Looks good, apply it.
```

The agent runs `deeprefine apply` and `deeprefine loop finish`.  If any actions
were flagged LOW-confidence, the agent asks for explicit risk acknowledgement
before passing `--allow-low-confidence`.

## Notes

- Copilot CLI must be started from the KB project root (where `graphify-out/`
  lives) for `deeprefine` commands to locate the graph file.
- If `/skills list` does not show `deeprefine`, run `/skills reload` or restart
  the Copilot CLI session.
- The skill file is a single Markdown document.  Additional helper scripts
  placed in `.github/skills/deeprefine/` are auto-discovered by Copilot.
- `allowed-tools: shell` pre-approves Bash execution.  Review the skill content
  before installing if you have security concerns about automated shell access.
- `/deeprefine` expects a project with `graphify-out/graph.json`; in this
  repository itself it may correctly report that Graphify outputs are missing.
