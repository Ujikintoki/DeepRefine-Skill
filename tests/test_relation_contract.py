"""Tests for the relation-vocabulary contract (Stage 2 Round 4 lever).

Pure-string tests only: the contract module must stay importable without the
upstream stack, mirroring the entity_fold import-hygiene rule.
"""

from deeprefine_skill.adapters.graphify.relation_contract import (
    apply_relation_contract,
    build_relation_contract,
    relation_labels_from_graph,
)


UPSTREAM_PROMPT = (
    "As an advanced knowledge graph refinement assistant...\n"
    "**Important:** DO NOT DELETE ANY IRRELEVANT TRIPLES.\n"
)

CODE_LABELS = ["contains", "calls", "references", "rationale_for", "imports", "method", "imports_from"]


def _raw_graph(*relations: str) -> dict:
    return {
        "links": [
            {"source": "a", "target": "b", "relation": r} for r in relations
        ]
    }


def test_labels_extracted_most_frequent_first():
    raw = _raw_graph("imports_from", "calls", "calls", "calls", "contains", "contains")
    assert relation_labels_from_graph(raw) == ["calls", "contains", "imports_from"]


def test_labels_capped():
    raw = _raw_graph(*(f"r{i}" for i in range(20)))
    assert len(relation_labels_from_graph(raw)) == 12


def test_contract_lists_graph_labels_and_forbids_invention():
    out = apply_relation_contract(UPSTREAM_PROMPT, CODE_LABELS)
    assert out.startswith(UPSTREAM_PROMPT.rstrip())
    assert UPSTREAM_PROMPT.rstrip() in out  # appended, not spliced
    for label in ("`imports_from`", "`imports`", "`contains`", "`calls`"):
        assert label in out
    assert "never invent a new relation word" in out


def test_contract_is_domain_agnostic():
    # Labels come from the graph, not from a hardcoded code vocabulary —
    # a wiki graph's labels must render just as naturally.
    out = apply_relation_contract(UPSTREAM_PROMPT, ["mentions", "relates_to"])
    assert "`mentions`" in out and "`relates_to`" in out
    assert "imports_from" not in out


def test_idempotent_within_one_process():
    once = apply_relation_contract(UPSTREAM_PROMPT, CODE_LABELS)
    assert apply_relation_contract(once, CODE_LABELS) == once


def test_no_labels_no_contract():
    # Nothing to align to: the upstream prompt must pass through untouched.
    assert apply_relation_contract(UPSTREAM_PROMPT, []) == UPSTREAM_PROMPT


def test_contract_does_not_teach_labels_absent_from_the_graph():
    # Labels the LLM invented in R2/R3 (never graph labels) must not be
    # legitimized by the contract.
    out = build_relation_contract(CODE_LABELS)
    for invented in ("defined_in", "uses_variable", "depends_on"):
        assert invented not in out


def test_normalizes_trailing_whitespace():
    out = apply_relation_contract("Prompt ends with space.   ", CODE_LABELS)
    assert not out.endswith(" ")
    assert out.endswith("KG triples.")
