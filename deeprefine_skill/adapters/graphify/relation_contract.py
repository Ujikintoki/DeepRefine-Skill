"""Relation-vocabulary contract for upstream's refinement action prompt.

Upstream's action prompt (``REAFINER_KG_REFINEMENT_ACTION_SYSTEM_PROMPT``)
specifies the ``insert_edge(subject, relation, object)`` format but never
constrains relation wording — verified against the upstream repo (the insert
path passes ``rel`` through verbatim, no prompt mentions vocabulary, the
Reafiner paper defines the operators only) — so proposal wording varies run
to run: the same query proposed ``imports_from`` in Stage 2 Round 3 (credited
by structeval) and ``depends_on`` in the identical-config confirm run
(invisible — the scorer only counts import-family relations, matching the AST
gold that defines imports by code fact, not by word).

The fix is interface alignment, not scorer tuning: a graphify graph has a
closed relation schema (the deterministic extractor only ever emits its own
labels), so an LLM-invented relation word is off-schema data that fragments
one fact into synonym edges. The contract tells the LLM which labels the
graph actually uses. The labels are extracted from the loaded graph at run
time — nothing is hardcoded, so the contract adapts to any domain (code
graphs, wiki graphs, ...) and teaches only what the graph itself speaks.

This module must stay importable without the upstream stack (atlas_rag /
autorefiner live in a sibling checkout reachable only at runtime), so it
depends on nothing beyond the standard library.
"""

from __future__ import annotations

import collections
from typing import Any

_MARK = "Relation vocabulary:"

_MAX_LABELS = 12


def relation_labels_from_graph(raw: dict[str, Any], cap: int = _MAX_LABELS) -> list[str]:
    """Collect a graph's relation labels, most frequent first.

    ``raw`` is the node-link JSON as loaded from graphify-out/graph.json
    (``links`` or ``edges`` key). Labels are returned in direct-quote form
    ready for the contract sentence.
    """
    counts = collections.Counter(
        str(edge.get("relation", "")).strip()
        for edge in raw.get("links", raw.get("edges", []))
        if edge.get("relation")
    )
    return [label for label, _ in counts.most_common(cap)]


def build_relation_contract(labels: list[str]) -> str:
    """Render the contract sentence for a graph's relation labels."""
    quoted = ", ".join(f"`{label}`" for label in labels)
    return (
        " " + _MARK + " this KG uses a fixed set of relation labels: "
        f"{quoted}. Reuse these labels — never invent a new relation word;"
        " pick the label whose meaning best matches the fact, judging from"
        " how the same labels are used in the KG triples."
    )


def apply_relation_contract(prompt: str, labels: list[str]) -> str:
    """Append the relation-vocabulary contract to an upstream prompt.

    Idempotent: a prompt already carrying the contract is returned unchanged,
    so re-running in one process never stacks duplicate copies. A graph with
    no relation labels gets no contract (nothing to align to).
    """
    if _MARK in prompt or not labels:
        return prompt
    return prompt.rstrip() + build_relation_contract(labels)
