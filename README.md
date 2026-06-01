<div align="center">

# DeepRefine-Skill


[![PyPi](https://img.shields.io/badge/HuggingFace-DeepRefine-blue.svg)](https://pypi.org/project/deeprefine-cli/0.1.3/)
[![Python](https://img.shields.io/badge/HuggingFace-DeepRefine-blue.svg)](https://pypi.org/project/deeprefine-cli/0.1.3/)
[![Paper](https://img.shields.io/badge/HuggingFace-DeepRefine-b31b1b.svg)](https://arxiv.org/pdf/2605.10488)
[![Project](https://img.shields.io/badge/HuggingFace-DeepRefine-green.svg)](https://github.com/HKUST-KnowComp/DeepRefine)

</div>

Type `/deeprefine` in your AI coding assistant after you've built a **[graphify](https://github.com/safishamsi/graphify)** knowledge base — it patches `graphify-out/graph.json` from your session's query history to evolve your LLM-Wiki.

Works in **Cursor** (install the skill once with `deeprefine cursor install`). The same workflow is available from any terminal via the `deeprefine` CLI ([`deeprefine-cli` on PyPI](https://pypi.org/project/deeprefine-cli/)).

```
/deeprefine
```

**Typical flow:** `graphify .` → `graphify query "..."` → record the question → `/deeprefine`.

```bash
deeprefine history add --query "your question"   # or let the agent do this
```

That's it. Under `graphify-out/.deeprefine/` you get:

```
graphify-out/
├── graph.json                          updated graph (graphify reads this)
└── .deeprefine/
    ├── history.jsonl                   queries queued for refinement
    ├── refinement_results_*.jsonl      run logs
    └── graph.json.bak                  backup before each refine
```

> **Standalone repo.** Model code (`autorefiner`, `atlas_rag`) lives in a separate [DeepRefine](https://github.com/HKUST-KnowComp/DeepRefine) checkout.  
> `pip install deeprefine-cli` ships the CLI and `SKILL.md`. `deeprefine refine` still needs DeepRefine + `atlastune` + inference (today: local vLLM).

---

## Roadmap

**Inference today:** local vLLM only (see [Inference](#4-inference-vllm) below).

**Coming soon:** third-party API support (OpenAI-compatible hosted LLM + embeddings) — no local GPU required.

---

## Quick start

| Step | What |
|:----:|------|
| 1 | Install [DeepRefine](https://github.com/HKUST-KnowComp/DeepRefine) in `atlastune` |
| 2 | `pip install deeprefine-cli` |
| 3 | `deeprefine cursor install` in your KB project |
| 4 | Start vLLM (embedding + refine) |
| 5 | `deeprefine history add` → `deeprefine refine` |

```bash
# 1) DeepRefine (once)
conda activate atlastune
cd /path/to/DeepRefine && pip install -e .

# 2) CLI (once per env)
pip install deeprefine-cli

# 3) Cursor skill (KB project root)
cd /path/to/your-kb-project
deeprefine cursor install

# 4) vLLM (each session, from DeepRefine repo)
bash /path/to/DeepRefine/scripts/vllm_serve/qwen3-0.6b-emb.sh
bash /path/to/DeepRefine/scripts/vllm_serve/qwen3-8b-vllm-reafiner.sh

# 5) Refine
deeprefine history add --query "your question"
deeprefine refine
```

---

## Pipeline

| Stage | Tool | Input | Output |
|:-----:|------|-------|--------|
| Build | **graphify** | Project files | `graphify-out/graph.json` |
| Query | **graphify** | Questions | `graphify query "..."` |
| Refine | **deeprefine** | Graph + query history | Updated `graph.json`, logs |

```text
  project files
        │
        ▼ graphify
   graph.json ◄────────────────────────┐
        │                              │
        ▼ graphify query               │ deeprefine refine
   (Q&A session)                      │
        │                              │
        ▼ deeprefine history add       │
   history.jsonl ──────────────────────┘
        │
        ▼ graphify query (verify)
```

DeepRefine does not build the graph; it patches `graph.json` so later `graphify query` retrieves better.

---

## Repository layout

```text
DeepRefine-Skill/              ← this repo (PyPI: deeprefine-cli)
├── deeprefine_skill/          ← package (SKILL.md bundled)
└── scripts/deeprefine.py

DeepRefine/                    ← separate clone
├── autorefiner/
├── AutoSchemaKG/
└── scripts/vllm_serve/

your-kb-project/
└── graphify-out/
    ├── graph.json
    └── .deeprefine/           ← history, logs, FAISS cache
```

**Recommended sibling layout** (auto-detects `../DeepRefine` when `DEEPREFINE_REPO` is unset):

```text
www/code/
├── DeepRefine/
└── DeepRefine-Skill/
```

---

## Installation

### 1. DeepRefine (`atlastune`)

See [DeepRefine — Environment](https://github.com/HKUST-KnowComp/DeepRefine#environment).

```bash
conda activate atlastune
cd /path/to/DeepRefine
pip install -e .
```

### 2. CLI

| Method | Command |
|--------|---------|
| **PyPI** (recommended) | `pip install deeprefine-cli` |
| **Source** | `pip install -e /path/to/DeepRefine-Skill` |

```bash
deeprefine --help    # verify
```

### 3. DeepRefine path (optional)

Only if `DeepRefine` is not `../DeepRefine` and not found by walking up from cwd:

```bash
export DEEPREFINE_REPO=/path/to/DeepRefine
```

### 4. Inference (vLLM)

From the **DeepRefine** repo:

```bash
conda activate atlastune
bash /path/to/DeepRefine/scripts/vllm_serve/qwen3-0.6b-emb.sh
bash /path/to/DeepRefine/scripts/vllm_serve/qwen3-8b-vllm-reafiner.sh
```

| Variable | Default |
|----------|---------|
| `DEEPREFINE_LLM_URL` | `http://127.0.0.1:8134/v1` |
| `DEEPREFINE_EMBED_URL` | `http://127.0.0.1:8128/v1` |
| `DEEPREFINE_MODEL` | `HaoyuHuang2/DeepRefine-v1-8B` |
| `DEEPREFINE_EMBED_MODEL` | `Qwen/Qwen3-Embedding-0.6B` |

### 5. Cursor skill

Run at **KB project root** (folder with or that will have `graphify-out/`):

| Command | Scope |
|---------|-------|
| `deeprefine cursor install` | `.cursor/skills/` (this project) |
| `deeprefine cursor install --user` | `~/.cursor/skills/` (all projects) |
| `deeprefine install` | alias for `cursor install` |
| `deeprefine cursor uninstall` | remove skill |

---

## Workflow with graphify

**One-time**

```bash
pip install graphifyy deeprefine-cli    # deeprefine-cli in atlastune

cd /path/to/your-kb-project
graphify cursor install
deeprefine cursor install
```

**Each session** (KB project root)

| # | Action |
|:-:|--------|
| 1 | `graphify .` or `/graphify .` → `graphify-out/graph.json` |
| 2 | `graphify query "..."` |
| 3 | `deeprefine history add --query "..."` |
| 4 | `deeprefine refine` or `/deeprefine` |
| 5 | *(optional)* `graphify query "..."` to verify |

---

## Commands

All commands below run from **KB project root**.

| Command | Description |
|---------|-------------|
| `deeprefine history add --query "..."` | Record a query after graph Q&A |
| `deeprefine history list` | List all history entries |
| `deeprefine history list --pending` | List unrefined queries only |
| `deeprefine refine` | Refine all pending queries |
| `deeprefine refine --query "..."` | Refine one query (also recorded) |
| `deeprefine refine --rebuild-index` | Rebuild FAISS before refine |
| `deeprefine index --rebuild` | Rebuild FAISS cache only |
| `deeprefine cursor install \| uninstall` | Manage Cursor skill |

**Artifacts** (`graphify-out/.deeprefine/`)

| File | Purpose |
|------|---------|
| `history.jsonl` | Query history |
| `refinement_results_*.jsonl` | Refinement logs |
| `graph.json.bak` | Backup before refine |
| `reafiner.pkl` | FAISS index cache |

Cursor agent instructions: [SKILL.md](./SKILL.md) → installed as `.cursor/skills/deeprefine/SKILL.md`.

---

## Where to run what

| What | Where |
|------|-------|
| `pip install deeprefine-cli` | Anywhere (`atlastune` for refine) |
| `pip install -e .../DeepRefine` | DeepRefine repo |
| `graphify` / `deeprefine cursor install` | **KB project root** |
| `deeprefine refine` / `history` | **KB project root** |
| vLLM serve scripts | **DeepRefine repo** |

---

## License

MIT — see [LICENSE](./LICENSE).
