"""Tests for parallel-baseline-link re-injection (DiGraph roundtrip fix).

graph.json may carry several links per ordered pair (different relation
words).  The refine path loads it into a networkx DiGraph — one edge per
pair, later add_edge overwrites earlier link attributes — and
sync_kg_to_graphify writes the survivor back, dropping the rest.  These
tests cover collect/reinject against a simulated sync output; the real call
site is refine_runner._persist (collect pre-sync, reinject post-sync).
"""

from __future__ import annotations

import json

import networkx as nx

from deeprefine_skill.adapters.graphify.parallel_links import (
    collect_parallel_links,
    reinject_parallel_links,
)


def _raw_with_parallels() -> dict:
    return {
        "directed": False,
        "nodes": [
            {"id": "a", "label": "a.py"},
            {"id": "b", "label": "b.py"},
            {"id": "c", "label": "c.py"},
        ],
        "links": [
            {"source": "a", "target": "b", "relation": "imports_from"},
            {"source": "a", "target": "b", "relation": "re_exports"},
            {"source": "b", "target": "c", "relation": "calls"},
        ],
    }


def _kg(pairs: list[tuple[str, str, str]]) -> nx.DiGraph:
    kg = nx.DiGraph()
    for source, target, relation in pairs:
        kg.add_edge(source, target, relation=relation)
    return kg


def _synced(raw: dict, kg: nx.DiGraph) -> dict:
    """Simulate sync_kg_to_graphify: one link per kg edge, passage-stripped."""
    out = json.loads(json.dumps(raw))
    out["nodes"] = [
        node
        for node in out["nodes"]
        if node["id"] in kg and kg.nodes[node["id"]].get("type") != "passage"
    ]
    out["links"] = [
        {"source": u, "target": v, "relation": data.get("relation", "related_to")}
        for u, v, data in kg.edges(data=True)
        if kg.nodes[u].get("type") != "passage" and kg.nodes[v].get("type") != "passage"
    ]
    return out


def _rels(out: dict, source: str, target: str) -> list[str]:
    return sorted(
        link["relation"]
        for link in out["links"]
        if link["source"] == source and link["target"] == target
    )


def test_roundtrip_preserves_both_relations() -> None:
    raw = _raw_with_parallels()
    parallels = collect_parallel_links(raw)
    assert len(parallels) == 2
    # DiGraph kept the last-loaded attr (re_exports) and lost imports_from.
    kg = _kg([("a", "b", "re_exports"), ("b", "c", "calls")])
    out = _synced(raw, kg)

    report = reinject_parallel_links(out, kg, parallels)

    assert report["re_injected"] == 1
    assert report["already_present"] == 1
    assert report["parallel_pairs"] == 1
    assert _rels(out, "a", "b") == ["imports_from", "re_exports"]


def test_noop_without_parallel_links() -> None:
    raw = _raw_with_parallels()
    raw["links"] = [raw["links"][2]]
    parallels = collect_parallel_links(raw)
    assert parallels == []
    kg = _kg([("b", "c", "calls")])
    out = _synced(raw, kg)
    before = json.dumps(out["links"], sort_keys=True)

    report = reinject_parallel_links(out, kg, parallels)

    assert report["collected"] == 0
    assert json.dumps(out["links"], sort_keys=True) == before


def test_deleted_pair_stays_deleted() -> None:
    raw = _raw_with_parallels()
    parallels = collect_parallel_links(raw)
    # delete_edge removes the edge, not the nodes (pair-level operator).
    kg = _kg([("b", "c", "calls")])
    kg.add_node("a")
    out = _synced(raw, kg)

    report = reinject_parallel_links(out, kg, parallels)

    assert report["pair_deleted"] == 2
    assert report["re_injected"] == 0
    assert all(link["source"] != "a" for link in out["links"])


def test_replaced_endpoint_stays_gone() -> None:
    raw = _raw_with_parallels()
    parallels = collect_parallel_links(raw)
    # replace_node removed the endpoint node together with its edges.
    kg = _kg([("a", "b", "re_exports"), ("b", "c", "calls")])
    kg.remove_node("a")
    out = _synced(raw, kg)

    report = reinject_parallel_links(out, kg, parallels)

    assert report["endpoint_gone"] == 2
    assert report["re_injected"] == 0


def test_refinement_overwritten_relation_restored() -> None:
    raw = _raw_with_parallels()
    parallels = collect_parallel_links(raw)
    # Refinement inserted a third relation on the pair; upstream add_edge
    # overwrote the surviving baseline attr.
    kg = _kg([("a", "b", "uses"), ("b", "c", "calls")])
    out = _synced(raw, kg)

    report = reinject_parallel_links(out, kg, parallels)

    assert report["re_injected"] == 2
    assert _rels(out, "a", "b") == ["imports_from", "re_exports", "uses"]


def test_passage_endpoint_skipped() -> None:
    raw = _raw_with_parallels()
    parallels = collect_parallel_links(raw)
    kg = _kg([("a", "b", "re_exports"), ("b", "c", "calls")])
    kg.nodes["b"]["type"] = "passage"
    out = _synced(raw, kg)

    report = reinject_parallel_links(out, kg, parallels)

    assert report["endpoint_gone"] == 2
    assert report["re_injected"] == 0


def test_edges_key_fallback() -> None:
    raw = _raw_with_parallels()
    raw["edges"] = raw.pop("links")
    assert len(collect_parallel_links(raw)) == 2
