"""Re-inject parallel baseline links lost to DiGraph's one-edge-per-pair rule.

graph.json allows several links between the same ordered node pair with
different relation words (``imports_from`` and ``re_exports`` on one file
pair, say).  The refine path loads the graph into a networkx ``DiGraph`` —
upstream's ``deeprefine.py`` does, and so does this adapter — whose contract
is ONE edge per ordered pair: a later ``add_edge`` silently overwrites the
earlier link's attributes, and ``sync_kg_to_graphify`` writes the survivor
back.  Every load→refine→sync roundtrip therefore drops the extra relation
of each parallel pair (measured on Route A: 5~58 pairs per library).

The paper models the knowledge base as a *set* of triples
``G={(h,r,t)}`` — parallel triples are legal elements — and baseline facts
must never be overwritten (the same principle ``entity_fold`` enforces for
nodes).  This module restores the dropped links at sync time.

The limitation is inherited, not invented here: upstream's own data prep
(``scripts/prepare_rl_data_*.py``) builds its DiGraph via ``add_edge`` and
collapses parallels identically, and the paper never specifies storage
semantics.  Text-domain corpora never emit parallel pairs (verified: the
Stage 2 KB and all 51 Re-DocRED Phase 2 graphs hold zero), which is why the
behavior stayed latent until Route A's deterministic code graphs.

Call order (refine_runner._persist):

    parallels = collect_parallel_links(raw)          # pre-sync, original links
    raw = sync_kg_to_graphify(raw, kg)
    report = reinject_parallel_links(raw, kg, parallels)

Both functions are networkx + stdlib only, so the module stays importable
without the upstream stack, like entity_fold.  Without parallel links in the
corpus the roundtrip is a byte-level no-op (Stage 2 / Re-DocRED comparability).
"""

from __future__ import annotations

from typing import Any

import networkx as nx

_PASSAGE_TYPE = "passage"


def collect_parallel_links(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """All baseline links belonging to an ordered pair carrying >1 link.

    The surviving link is collected too; the re-injection gate deduplicates
    against the synced output, so collecting it is harmless and keeps the
    stash complete.
    """
    links = raw.get("links") or raw.get("edges") or []
    by_pair: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for link in links:
        by_pair.setdefault((link.get("source"), link.get("target")), []).append(link)
    parallels: list[dict[str, Any]] = []
    for group in by_pair.values():
        if len(group) > 1:
            parallels.extend(group)
    return parallels


def _confidence_fields(link: dict[str, Any]) -> dict[str, Any]:
    """Mirror sync_kg_to_graphify's confidence normalization for uniform output."""
    confidence = link.get("confidence", "INFERRED")
    score = {"EXTRACTED": 1.0, "INFERRED": 0.7}.get(confidence, 0.4)
    return {"confidence": confidence, "confidence_score": score}


def reinject_parallel_links(
    raw: dict[str, Any],
    kg: nx.DiGraph,
    parallels: list[dict[str, Any]],
) -> dict[str, Any]:
    """Put collected parallel links back into the synced graph, gated.

    A link is re-injected only if (1) both endpoints still exist in ``kg`` as
    non-passage nodes — a pair removed by ``delete_edge`` (pair-level by the
    operator's own signature) or a node removed by ``replace_node`` stays
    gone, and (2) its (source, relation, target) triple is not already in the
    synced output.  Returns an audit report; ``raw`` is mutated in place.
    """
    links_key = "links" if "links" in raw else "edges"
    out_links: list[dict[str, Any]] = raw.setdefault(links_key, [])
    existing_triples = {
        (link.get("source"), str(link.get("relation", "")).casefold(), link.get("target"))
        for link in out_links
    }

    reinjected = 0
    already_present = 0
    pair_deleted = 0
    endpoint_gone = 0
    for link in parallels:
        source, target = link.get("source"), link.get("target")
        relation = str(link.get("relation", "") or "")
        triple = (source, relation.casefold(), target)
        if triple in existing_triples:
            already_present += 1
            continue
        if source not in kg or target not in kg:
            endpoint_gone += 1
            continue
        if (
            kg.nodes[source].get("type") == _PASSAGE_TYPE
            or kg.nodes[target].get("type") == _PASSAGE_TYPE
        ):
            endpoint_gone += 1
            continue
        if not kg.has_edge(source, target):
            # The pair itself was removed by refinement; its relations die
            # together, matching delete_edge's pair-level contract.
            pair_deleted += 1
            continue
        out_links.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                **_confidence_fields(link),
            }
        )
        existing_triples.add(triple)
        reinjected += 1

    return {
        "collected": len(parallels),
        "re_injected": reinjected,
        "already_present": already_present,
        "pair_deleted": pair_deleted,
        "endpoint_gone": endpoint_gone,
        "parallel_pairs": len(
            {(link.get("source"), link.get("target")) for link in parallels}
        ),
    }
