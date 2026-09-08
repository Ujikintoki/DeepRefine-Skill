"""Tests for staged-passage preservation across the refine write-back (C3).

The refinement kg never contains passage nodes — the engine filters them out
of its working subgraph at init (they are text sources, not entities) — so
``sync_kg_to_graphify`` used to rebuild graph.json without them: every
write-back silently unstaged what ``passage_nodes.py`` had added, and the
next run degraded to closed-book. ``passage_roundtrip.py`` snapshots the
passages from the pre-sync raw and re-appends them after the rebuild.

These tests drive the helper pair around a faithful simulation of the sync
rebuild (the real one lives in adapter.py, which imports the upstream stack
and cannot be imported here — same approach as test_parallel_links.py).
Fixtures are in-memory dicts shaped like ``passage_nodes.py`` output.
"""

from __future__ import annotations

import networkx as nx

from deeprefine_skill.adapters.graphify.passage_roundtrip import (
    merge_passages,
    split_passages,
)


PASSAGE = {
    "id": "docs/src/pkg/a.py",
    "label": "full source text of a.py",
    "type": "passage",
    "source_file": "docs/src/pkg/a.py",
}
ENTITY = {"id": "a", "label": "a.py", "source_file": "docs/src/pkg/a.py"}


def _sync(raw: dict, kg: nx.DiGraph) -> dict:
    """Mirror adapter.sync_kg_to_graphify with the roundtrip wired in.

    Rebuild skips kg-side passage nodes exactly like the real one; the
    passages come back solely through split (pre-rebuild) + merge (post).
    """
    staged_passages = split_passages(raw)
    out: dict = {"directed": raw.get("directed", False), "nodes": [], "links": []}
    for nid in sorted(kg.nodes, key=str):
        if kg.nodes[nid].get("type") == "passage":
            continue
        base = dict(next((n for n in raw["nodes"] if n["id"] == nid), {}))
        base["id"] = nid
        base["label"] = kg.nodes[nid].get("id", nid)
        out["nodes"].append(base)
    out["links"] = [
        {"source": u, "target": v, "relation": data.get("relation", "related_to")}
        for u, v, data in kg.edges(data=True)
        if kg.nodes[u].get("type") != "passage"
        and kg.nodes[v].get("type") != "passage"
    ]
    return merge_passages(out, staged_passages)


def _passage_nodes(out: dict) -> list[dict]:
    return [n for n in out["nodes"] if n.get("type") == "passage"]


def test_two_rounds_keep_passage_nodes() -> None:
    """Two consecutive write-backs: staged passages survive both, verbatim."""
    raw = {
        "directed": False,
        "nodes": [dict(ENTITY), {"id": "b", "label": "b.py"}, dict(PASSAGE)],
        "links": [{"source": "a", "target": "b", "relation": "imports_from"}],
    }
    kg_round_1 = nx.DiGraph()
    kg_round_1.add_edge("a", "b", relation="calls")

    after_round_1 = _sync(raw, kg_round_1)

    assert len(_passage_nodes(after_round_1)) == 1
    kept = _passage_nodes(after_round_1)[0]
    assert kept["id"] == PASSAGE["id"]
    assert kept["label"] == PASSAGE["label"]
    assert kept["source_file"] == PASSAGE["source_file"]

    # Round 2 reloads the round-1 output and refines again (graph mutates).
    kg_round_2 = nx.DiGraph()
    kg_round_2.add_edge("b", "a", relation="calls_back")

    after_round_2 = _sync(after_round_1, kg_round_2)

    assert len(_passage_nodes(after_round_2)) == 1
    assert _passage_nodes(after_round_2)[0] == PASSAGE


def test_passages_come_from_raw_not_kg() -> None:
    """A kg-side passage node (the __deeprefine_passage__ dummy) never lands."""
    raw = {"directed": False, "nodes": [dict(ENTITY)], "links": []}
    kg = nx.DiGraph()
    kg.add_node("a", id="a.py")
    kg.add_node(
        "__deeprefine_passage__",
        id="graphify knowledge graph",
        type="passage",
        file_id=None,
    )

    out = _sync(raw, kg)

    assert _passage_nodes(out) == []


def test_passage_endpoint_links_are_not_carried() -> None:
    """Links touching passage endpoints stay dropped (parallel_links policy)."""
    raw = {
        "directed": False,
        "nodes": [dict(ENTITY), dict(PASSAGE)],
        "links": [{"source": "a", "target": PASSAGE["id"], "relation": "has_text"}],
    }
    kg = nx.DiGraph()
    kg.add_node("a", id="a.py")

    out = _sync(raw, kg)

    assert out["links"] == []
    assert len(_passage_nodes(out)) == 1


def test_entity_wins_on_passage_id_collision() -> None:
    """A passage id occupied by a real entity node is not duplicated."""
    raw = {
        "directed": False,
        "nodes": [dict(ENTITY), {**PASSAGE, "id": "a"}],
        "links": [],
    }
    kg = nx.DiGraph()
    kg.add_node("a", id="a.py")

    out = _sync(raw, kg)

    assert [n["id"] for n in out["nodes"]] == ["a"]


def test_merge_without_passages_is_a_noop() -> None:
    """No staged passages -> output untouched (pure-baseline syncs unchanged)."""
    out = {"nodes": [{"id": "a"}]}

    assert merge_passages(out, []) is out
    assert out["nodes"] == [{"id": "a"}]


def test_split_returns_independent_copies() -> None:
    """Later mutation of raw must not leak into the snapshot."""
    raw = {"nodes": [dict(PASSAGE)]}

    snapshot = split_passages(raw)
    raw["nodes"][0]["label"] = "mutated after snapshot"

    assert snapshot[0]["label"] == PASSAGE["label"]
