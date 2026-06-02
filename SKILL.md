---
name: deeprefine
description: >-
  Refines a graphify knowledge graph (graphify-out/graph.json) using DeepRefine
  Reafiner based on session query history. Use when the user runs /deeprefine,
  asks to improve the graphify KB after Q&A, or wants to patch graph.json from
  failed retrieval queries.
disable-model-invocation: false
---

# DeepRefine (graphify)

Refine a **[graphify](https://github.com/safishamsi/graphify)** `graph.json` with the DeepRefine agent loop.

## Setup

**DeepRefine-Skill** (CLI + this file) is separate from the **DeepRefine** model repo.

```bash
# 1) DeepRefine env (atlastune) + main package
conda activate atlastune
cd /path/to/DeepRefine && pip install -e .

# 2) This skill CLI
pip install deeprefine-cli

# 3) Optional if DeepRefine is not ../DeepRefine
export DEEPREFINE_REPO=/path/to/DeepRefine

# 4) Cursor skill in KB project root
cd /path/to/your-kb-project
deeprefine cursor install
```

Inference defaults to your current API model setup (`OPENAI_API_KEY` or `DEEPREFINE_API_KEY`).

Optional: local vLLM from DeepRefine (embedding `8128`, refine model `8134`; see `scripts/vllm_serve/`).

## `/deeprefine` (agent-native)

From the **KB project root** (with `graphify-out/graph.json`):

```bash
deeprefine history add --query "..."   # after graph Q&A
/deeprefine                            # run inside agent (no extra API key)
```

What the agent should do when `/deeprefine` is invoked:

1. Load pending queries from `graphify-out/.deeprefine/history.jsonl`.
2. Read `graphify-out/graph.json`.
3. Propose and apply minimal graph updates directly to `graph.json` for unresolved queries.
4. Write a timestamped log to `graphify-out/.deeprefine/refinement_results_*.jsonl`.
5. Mark processed history items as `refined: true`.

Use `deeprefine refine` CLI only when explicitly asked to run DeepRefine runtime (vLLM/API).

## Paths

- History: `graphify-out/.deeprefine/history.jsonl`
- Log: `graphify-out/.deeprefine/refinement_results_*.jsonl`
- Backup: `graphify-out/.deeprefine/graph.json.bak`
