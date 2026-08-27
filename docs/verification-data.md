# Verification Data Design

10-node synthetic knowledge graph for end-to-end Reafiner protocol verification.
Schema conforms to graphify `graph.json` (NetworkX `node_link_data`).

> **Path note (2026-08 restructure):** harness modules now live in
> `deeprefine_skill/core/`; the CLI entry is `deeprefine_skill/cli.py`.
> Evidence anchors use `file::symbol` form (no line numbers) so they survive
> future refactors.

## Design Goals

One data file, two Reafiner paths:

| Path | Condition | Expected |
|------|-----------|----------|
| Early exit | Query answerable from existing edges | 1 step → JUDGE Yes → FINISH |
| Refinement | Query requires an edge missing from KG | ≥2 steps → JUDGE No → ABDUCE → REFINE → HARD STOP |

## KG Topology

### Nodes (10)

| id | label | type | source_file | community |
|----|-------|------|-------------|-----------|
| `validate_trace` | validate_trace | function | agent_loop.py | harness |
| `Reafiner` | Reafiner | concept | README.md | concept |
| `action_review` | action_review | module | action_review.py | harness |
| `graph_json` | graph.json | data file | README.md | data |
| `apply_refinement_text` | apply_refinement_text | function | agent_graph.py | operations |
| `loop_trace` | loop_trace | data file | agent_loop.py | data |
| `deeprefine` | deeprefine | CLI entry | cli.py | entrypoint |
| `agent_prompts` | agent_prompts | module | agent_prompts.py | prompts |
| `history_jsonl` | history.jsonl | data file | history.py | data |
| `query_id` | query_id | function | history.py | operations |

### Edges (11)

**EXTRACTED (confidence 1.0)** — represent AST-derivable facts:

| source | relation | target | evidence |
|--------|----------|--------|----------|
| validate_trace | implements | Reafiner | `core/agent_loop.py::validate_trace` |
| validate_trace | reads | loop_trace | `core/agent_loop.py::validate_trace` |
| action_review | depends_on | validate_trace | fixture scenario edge from PR #4 layout (current code imports `agent_graph`); kept by design for Query 2 — see Known Drifts |
| apply_refinement_text | modifies | graph_json | `core/agent_graph.py::apply_refinement_text` |
| deeprefine | contains | validate_trace | `deeprefine_skill/cli.py::cmd_loop_validate` |
| deeprefine | contains | apply_refinement_text | `deeprefine_skill/cli.py::cmd_apply` |
| deeprefine | reads | history_jsonl | `deeprefine_skill/cli.py` (history commands) |
| deeprefine | writes | loop_trace | `deeprefine_skill/cli.py` (loop commands) |

**INFERRED (confidence 0.7–0.8)** — represent LLM-derived semantic links:

| source | relation | target | score | evidence |
|--------|----------|--------|-------|----------|
| agent_prompts | defines | Reafiner | 0.8 | `core/agent_prompts.py` |
| history_jsonl | tracks | query_id | 0.7 | `core/history.py::query_id` |
| deeprefine | modifies | graph_json | 0.8 | `deeprefine_skill/cli.py` (apply/refine commands) |

### Deliberately Missing (2 gaps)

These edges exist in the real codebase but are **absent from the KG** to trigger refinement:

| source | relation | target | Real evidence |
|--------|----------|--------|---------------|
| action_review | audits | graph_json | `core/action_review.py::review_action` (evidence strings reference `graph.json`) |
| validate_trace | imports | agent_prompts | `core/agent_loop.py` header: `from deeprefine_skill.core.agent_prompts import ...` |

## Queries

### Query 1 — Early Exit

```
What does validate_trace implement?
```

- **Retrieved**: `validate_trace → implements → Reafiner`, `validate_trace → reads → loop_trace`
- **Expected**: JUDGE **Yes** → FINISH (1 step)

### Query 2 — Refinement (missing edge)

```
How does action_review check graph.json?
```

- **Retrieved**: `action_review → depends_on → validate_trace`, `apply_refinement_text → modifies → graph_json`
- **Gap**: No direct edge between `action_review` and `graph_json`
- **Expected**: JUDGE No → k-hop → JUDGE No → ABDUCE → `insert_edge("action_review", "audits", "graph.json")` → REVIEW: **HIGH** (both nodes exist, source file evidence in action_review.py) → HARD STOP

### Query 3 — Refinement (missing entity + edge)

```
Where does validate_trace get its prompts from?
```

- **Retrieved**: `validate_trace → implements → Reafiner`, `agent_prompts → defines → Reafiner`
- **Gap**: No `validate_trace → imports → agent_prompts` edge
- **Expected**: JUDGE No → k-hop → JUDGE No → ABDUCE → `insert_edge("validate_trace", "imports", "agent_prompts")` → REVIEW → HARD STOP

## Schema Conformance

- Uses `"edges"` key (graphify default; `core/agent_graph.py` also handles `"links"`)
- Node fields match graphify: `id`, `label`, `file_type`, `source_file`, `source_location`, `community`
- Edge fields match graphify: `source`, `target`, `relation`, `confidence`, `confidence_score`, `source_file`, `source_location`, `weight`
- `confidence` uses graphify tags: `EXTRACTED` / `INFERRED` / `AMBIGUOUS`
- `hyperedges` present as empty array
- `input_tokens` / `output_tokens` present as 0
- Validated by `scripts/validate_graph_schema.py`

## Quick Start

No external dependencies — only `deeprefine` CLI (already installed if you `pip install -e .`).

```bash
cd /path/to/DeepRefine-Skill

# 1. Schema check
python scripts/validate_graph_schema.py fixtures/synth-minimal.json
# Expected: OK — 10 nodes, 11 edges

# 2. Trace validation
python -m deeprefine_skill.cli loop validate --trace-file fixtures/trace-valid-early-exit.json
# Expected: OK — loop trace matches Reafiner.refine() rules.

python -m deeprefine_skill.cli loop validate --trace-file fixtures/trace-valid.json --refinement-file fixtures/refinement-good.txt
# Expected: OK

python -m deeprefine_skill.cli loop validate --trace-file fixtures/trace-invalid-order.json
# Expected: INVALID + error messages + exit 1

# 3. Review (dry-run) — needs a temp KB project
mkdir -p /tmp/test_kb/graphify-out
cp fixtures/synth-minimal.json /tmp/test_kb/graphify-out/graph.json
python -m deeprefine_skill.cli review --refinement-file fixtures/refinement-good.txt --trace-file fixtures/trace-valid.json --project-root /tmp/test_kb
# Expected: [MEDIUM] confidence report

python -m deeprefine_skill.cli review --refinement-file fixtures/refinement-ambiguous.txt --project-root /tmp/test_kb
# Expected: [LOW] confidence report

# 4. Apply gate
python -m deeprefine_skill.cli apply --refinement-file fixtures/refinement-good.txt --trace-file fixtures/trace-valid.json --project-root /tmp/test_kb
# Expected: Applied 1 action(s)

python -m deeprefine_skill.cli apply --refinement-file fixtures/refinement-ambiguous.txt --trace-file fixtures/trace-valid.json --project-root /tmp/test_kb
# Expected: Refusing...LOW-confidence + exit 1

# 5. Cleanup
rm -rf /tmp/test_kb
```

## Files

| File | Purpose |
|------|---------|
| `fixtures/synth-minimal.json` | 10-node synthetic KG (graphify schema) |
| `fixtures/trace-valid-early-exit.json` | 1-step trace (early exit path) |
| `fixtures/trace-valid.json` | 2-step trace (refinement path) |
| `fixtures/trace-invalid-order.json` | Malformed trace for negative testing |
| `fixtures/refinement-good.txt` | Valid refinement action → MEDIUM confidence |
| `fixtures/refinement-ambiguous.txt` | Fuzzy node name → LOW confidence |
| `fixtures/refinement-invalid.txt` | No `<refinement>` block → parse error |
| `scripts/validate_graph_schema.py` | Schema conformance checker |

## Known Drifts (2026-08-27 audit) — accepted by design

This fixture is a self-authored scenario snapshot (PR #4), not a live index of
the codebase: the project graphifies its own code, so fixture provenance
naturally lags refactors. Both drifts below are accepted; do not "fix" them
against current code — the fixture must stay internally consistent with the
Query scenarios, not with the moving codebase.

1. Node `source_file` values use pre-restructure paths
   (`deeprefine_skill/agent_loop.py` …). Cosmetic; no test asserts them.
2. The edge `action_review → depends_on → validate_trace` reflects the PR #4
   layout (current code imports `agent_graph` instead). It is a prop of the
   Query 2 refinement scenario (retrieve → abduce → insert
   `action_review → audits → graph_json`) and stays as-is.
