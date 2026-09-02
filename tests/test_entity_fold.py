"""Unit tests for sync-time entity folding of refinement phantom nodes.

Upstream mints a fresh sha256 node for every LLM entity string instead of
resolving it against the loaded graph (its entity_to_id table is never
seeded), so refinement leaves duplicate phantoms behind.
``fold_refined_entities`` re-homes them onto baseline twins; these tests pin
every rule: exact/basename matching, honest residuals, edge re-homing, dedup,
and the untouched-relation red line. All fixtures are in-memory.
"""

from __future__ import annotations

import hashlib

import networkx as nx

from deeprefine_skill.adapters.graphify.entity_fold import fold_refined_entities


def _phantom_key(label: str) -> str:
    """Mimic upstream's deterministic phantom key: sha256(label + "_entity")."""
    return hashlib.sha256((label + "_entity").encode("utf-8")).hexdigest()


def _baseline_nodes() -> dict[str, str]:
    """Baseline inventory (key -> label), incl. one deliberately ambiguous pair."""
    return {
        "deeprefine_skill_cli": "cli.py",
        "deeprefine_skill_refine_runner": "refine_runner.py",
        "deeprefine_skill_cli_cmd_refine": "cmd_refine()",
        "deeprefine_skill_paths_path": "path",
        "tests_test_x_path": "path",
    }


def _kg(nodes: dict[str, str], edges: list[tuple[str, str, str]]) -> nx.DiGraph:
    """Pipeline-convention kg: the node attribute ``id`` carries the label."""
    kg = nx.DiGraph()
    for key, label in nodes.items():
        kg.add_node(key, id=label)
    for u, v, relation in edges:
        kg.add_edge(u, v, relation=relation, confidence="INFERRED")
    return kg


def test_exact_label_fold_rehomes_edges_and_removes_phantom() -> None:
    """A phantom whose label equals exactly one baseline label folds; edges follow."""
    key = _phantom_key("cmd_refine()")
    kg = _kg(
        {**_baseline_nodes(), key: "cmd_refine()"},
        [(key, "deeprefine_skill_refine_runner", "calls")],
    )
    report = fold_refined_entities(kg, _baseline_nodes())

    assert kg.has_edge("deeprefine_skill_cli_cmd_refine", "deeprefine_skill_refine_runner")
    assert key not in kg
    assert report["folded"] == {
        key: {"label": "cmd_refine()", "target": "deeprefine_skill_cli_cmd_refine"}
    }
    assert report["edges_remapped"] == 1


def test_basename_fold_for_path_shaped_label() -> None:
    """``deeprefine_skill/cli.py`` folds via its unique basename ``cli.py``."""
    key = _phantom_key("deeprefine_skill/cli.py")
    kg = _kg(
        {**_baseline_nodes(), key: "deeprefine_skill/cli.py"},
        [(key, "deeprefine_skill_refine_runner", "contains")],
    )
    report = fold_refined_entities(kg, _baseline_nodes())

    assert report["folded"] == {key: {"label": "deeprefine_skill/cli.py", "target": "deeprefine_skill_cli"}}
    assert key not in kg
    assert kg.has_edge("deeprefine_skill_cli", "deeprefine_skill_refine_runner")


def test_ambiguous_label_is_kept() -> None:
    """A label matching two baseline nodes is not guessed; phantom and edge stay."""
    key = _phantom_key("path")
    kg = _kg(
        {**_baseline_nodes(), key: "path"},
        [(key, "deeprefine_skill_cli", "calls")],
    )
    report = fold_refined_entities(kg, _baseline_nodes())

    assert report["residual"] == [{"key": key, "label": "path", "reason": "ambiguous"}]
    assert key in kg
    assert kg.has_edge(key, "deeprefine_skill_cli")


def test_unmatched_label_is_kept() -> None:
    """No baseline twin -> phantom survives untouched (honest residue)."""
    key = _phantom_key("max_hops_default")
    kg = _kg({**_baseline_nodes(), key: "max_hops_default"}, [])
    report = fold_refined_entities(kg, _baseline_nodes())

    assert report["residual"] == [
        {"key": key, "label": "max_hops_default", "reason": "unmatched"}
    ]
    assert key in kg


def test_rehomed_edge_duplicating_baseline_edge_is_dropped() -> None:
    """A remap landing on an existing identical edge is dropped, not stacked."""
    key_cli = _phantom_key("cli.py")
    key_rr = _phantom_key("refine_runner.py")
    kg = _kg(
        {**_baseline_nodes(), key_cli: "cli.py", key_rr: "refine_runner.py"},
        [
            ("deeprefine_skill_cli", "deeprefine_skill_refine_runner", "imports_from"),
            (key_cli, key_rr, "imports_from"),
        ],
    )
    report = fold_refined_entities(kg, _baseline_nodes())

    assert len(report["folded"]) == 2
    assert report["edges_duplicated_dropped"] == 1
    assert report["edges_remapped"] == 0
    assert kg.number_of_edges(
        "deeprefine_skill_cli", "deeprefine_skill_refine_runner"
    ) == 1
    assert key_cli not in kg and key_rr not in kg


def test_same_pair_different_relation_is_dropped_and_baseline_edge_intact() -> None:
    """An existing edge on the same pair wins whatever its relation; attrs intact."""
    key = _phantom_key("cli.py")
    kg = _kg(
        {**_baseline_nodes(), key: "cli.py"},
        [
            ("deeprefine_skill_cli", "deeprefine_skill_refine_runner", "imports"),
            (key, "deeprefine_skill_refine_runner", "calls"),
        ],
    )
    report = fold_refined_entities(kg, _baseline_nodes())

    assert report["edges_duplicated_dropped"] == 1
    edge = kg.edges["deeprefine_skill_cli", "deeprefine_skill_refine_runner"]
    assert edge["relation"] == "imports"
    assert kg.number_of_edges(
        "deeprefine_skill_cli", "deeprefine_skill_refine_runner"
    ) == 1


def test_same_label_phantoms_edge_becomes_self_loop_and_dropped() -> None:
    """Two phantoms sharing a label both fold; an edge between them collapses."""
    key_bare = _phantom_key("cli.py")
    key_path = _phantom_key("deeprefine_skill/cli.py")
    kg = _kg(
        {**_baseline_nodes(), key_bare: "cli.py", key_path: "deeprefine_skill/cli.py"},
        [(key_bare, key_path, "calls")],
    )
    report = fold_refined_entities(kg, _baseline_nodes())

    assert len(report["folded"]) == 2
    assert report["edges_self_loop_dropped"] == 1
    assert not kg.has_edge("deeprefine_skill_cli", "deeprefine_skill_cli")
    assert set(kg.nodes) == set(_baseline_nodes())


def test_phantom_to_phantom_chain_rehomes_real_to_real() -> None:
    """The R2 credited-edge shape: both endpoints fold, the edge survives."""
    key_cli = _phantom_key("cli.py")
    key_rr = _phantom_key("refine_runner.py")
    kg = _kg(
        {**_baseline_nodes(), key_cli: "cli.py", key_rr: "refine_runner.py"},
        [(key_cli, key_rr, "imports_from")],
    )
    report = fold_refined_entities(kg, _baseline_nodes())

    edge = kg.edges["deeprefine_skill_cli", "deeprefine_skill_refine_runner"]
    assert edge["relation"] == "imports_from"
    assert report["edges_remapped"] == 1


def test_relation_words_are_never_rewritten() -> None:
    """Folding re-homes endpoints only; relation labels pass through verbatim."""
    key = _phantom_key("cmd_refine()")
    kg = _kg(
        {**_baseline_nodes(), key: "cmd_refine()"},
        [(key, "deeprefine_skill_cli", "uses_variable")],
    )
    fold_refined_entities(kg, _baseline_nodes())

    edge = kg.edges["deeprefine_skill_cli_cmd_refine", "deeprefine_skill_cli"]
    assert edge["relation"] == "uses_variable"


def test_report_shape_and_residual_reasons() -> None:
    """The report carries folded/residual detail, counters, and dropped edges."""
    matched = _phantom_key("cli.py")
    orphan = _phantom_key("max_hops_default")
    kg = _kg({**_baseline_nodes(), matched: "cli.py", orphan: "max_hops_default"}, [])
    report = fold_refined_entities(kg, _baseline_nodes())

    assert set(report) == {
        "folded",
        "residual",
        "edges_remapped",
        "edges_duplicated_dropped",
        "edges_self_loop_dropped",
        "dropped_duplicate_edges",
        "dropped_self_loop_edges",
    }
    assert report["folded"] == {matched: {"label": "cli.py", "target": "deeprefine_skill_cli"}}
    assert report["residual"] == [
        {"key": orphan, "label": "max_hops_default", "reason": "unmatched"}
    ]
    assert report["edges_remapped"] == 0


def test_no_phantoms_leaves_graph_unchanged() -> None:
    """A pure-baseline graph is a no-op: same nodes, same edges, empty report."""
    kg = _kg(
        _baseline_nodes(),
        [("deeprefine_skill_cli", "deeprefine_skill_cli_cmd_refine", "contains")],
    )
    before = (set(kg.nodes), set(kg.edges))
    report = fold_refined_entities(kg, _baseline_nodes())

    assert report["folded"] == {}
    assert report["residual"] == []
    assert (set(kg.nodes), set(kg.edges)) == before


def test_baseline_nodes_are_never_removed_or_rewritten() -> None:
    """Folding only removes phantoms; every baseline node and label survives."""
    key = _phantom_key("cli.py")
    kg = _kg(
        {**_baseline_nodes(), key: "cli.py"},
        [(key, "deeprefine_skill_refine_runner", "calls")],
    )
    fold_refined_entities(kg, _baseline_nodes())

    for node_id, label in _baseline_nodes().items():
        assert node_id in kg
        assert kg.nodes[node_id]["id"] == label
    assert key not in kg
