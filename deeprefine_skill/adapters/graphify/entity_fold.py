"""Fold refinement-minted phantom nodes back onto baseline twins.

Upstream's autorefiner never resolves LLM entity strings against the loaded
graph: its ``entity_to_id`` table starts and stays empty (deeprefine.py:207),
so ``_get_node_id`` mints a deterministic ``sha256(name + "_entity")`` node
for every name the LLM mentions — even when a real node with that exact label
already exists. Refinement therefore leaves duplicate phantom nodes behind,
and their keys persist across runs because the hash is deterministic.

This module re-homes those phantoms onto baseline twins at sync time — after
refinement, before the refined graph is written back. It must stay importable
without the upstream stack (atlas_rag/autorefiner live in a sibling checkout
reachable only at runtime), so it depends on nothing beyond networkx and the
standard library.
"""

from __future__ import annotations

import posixpath
from typing import Any

import networkx as nx


def fold_refined_entities(
    kg: nx.DiGraph, baseline_labels: dict[str, str]
) -> dict[str, Any]:
    """Fold refinement-minted phantom nodes into baseline twins.

    A refined node whose key is absent from ``baseline_labels`` (baseline node
    key -> label) was minted by refinement. When its label equals exactly one
    baseline label — exact match first, then basename match for path-shaped
    labels like ``deeprefine_skill/cli.py`` — its incident edges are re-homed
    onto the twin and the phantom is removed. Ambiguous or unmatched phantoms
    are kept as-is. Relation words are never rewritten, and no baseline node
    is ever removed or modified.

    Returns an audit report: ``folded`` (phantom key -> label/target),
    ``residual`` (kept phantoms with the reason), edge counters, and the
    dropped edges listed for auditability.
    """
    label_to_ids: dict[str, list[str]] = {}
    for node_id, label in baseline_labels.items():
        label_to_ids.setdefault(label, []).append(node_id)

    fold_map: dict[str, str] = {}
    folded: dict[str, dict[str, str]] = {}
    residual: list[dict[str, str]] = []
    for key in kg.nodes:
        if key in baseline_labels:
            continue
        label = str(kg.nodes[key].get("id") or key)
        target: str | None = None
        reason: str | None = None
        candidates = label_to_ids.get(label)
        if candidates is not None and len(candidates) == 1:
            target = candidates[0]
        elif candidates is not None:
            reason = "ambiguous"
        else:
            basename = posixpath.basename(label)
            basename_candidates = label_to_ids.get(basename) if basename != label else None
            if basename_candidates is not None and len(basename_candidates) == 1:
                target = basename_candidates[0]
            elif basename_candidates is not None:
                reason = "ambiguous"
            else:
                reason = "unmatched"
        if target is None:
            residual.append({"key": key, "label": label, "reason": reason or "unmatched"})
        else:
            fold_map[key] = target
            folded[key] = {"label": label, "target": target}

    edges_remapped = 0
    edges_duplicated_dropped = 0
    edges_self_loop_dropped = 0
    dropped_duplicates: list[dict[str, str]] = []
    dropped_self_loops: list[dict[str, str]] = []
    if fold_map:
        incident = [
            (u, v, dict(attrs))
            for u, v, attrs in kg.edges(data=True)
            if u in fold_map or v in fold_map
        ]
        kg.remove_edges_from([(u, v) for u, v, _ in incident])
        for u, v, attrs in incident:
            src = fold_map.get(u, u)
            tgt = fold_map.get(v, v)
            relation = str(attrs.get("relation", ""))
            if src == tgt:
                edges_self_loop_dropped += 1
                dropped_self_loops.append(
                    {"source": src, "relation": relation, "target": tgt}
                )
                continue
            if kg.has_edge(src, tgt):
                # An existing edge on the same pair wins regardless of its
                # relation: baseline facts are never overwritten by
                # refinement-derived attributes (DiGraph allows one edge
                # per ordered pair).
                edges_duplicated_dropped += 1
                dropped_duplicates.append(
                    {"source": src, "relation": relation, "target": tgt}
                )
                continue
            kg.add_edge(src, tgt, **attrs)
            edges_remapped += 1
        kg.remove_nodes_from(fold_map)

    return {
        "folded": folded,
        "residual": residual,
        "edges_remapped": edges_remapped,
        "edges_duplicated_dropped": edges_duplicated_dropped,
        "edges_self_loop_dropped": edges_self_loop_dropped,
        "dropped_duplicate_edges": dropped_duplicates,
        "dropped_self_loop_edges": dropped_self_loops,
    }
