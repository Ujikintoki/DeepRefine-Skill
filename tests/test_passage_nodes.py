"""Tests for the passage-node builder (open-book refine support).

The contract under test: a passage node's graph-key ``id`` equals the entity
nodes' ``source_file`` verbatim, its ``label`` carries the file text, and its
``type`` is ``"passage"`` — see deeprefine_skill/adapters/graphify/passage_nodes.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from deeprefine_skill.adapters.graphify.passage_nodes import (
    PASSAGE_TYPE,
    add_passage_nodes,
)


def _write_graph(path: Path, nodes: list[dict]) -> Path:
    path.write_text(
        json.dumps({"directed": False, "nodes": nodes, "links": []}, indent=2),
        encoding="utf-8",
    )
    return path


def _make_tree(root: Path) -> None:
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / "pkg" / "sub").mkdir()
    (root / "src" / "pkg" / "sub" / "b.py").write_text("import os\n", encoding="utf-8")


def _entities() -> list[dict]:
    return [
        {"id": "pkg_a", "label": "VALUE", "source_file": "src/pkg/a.py"},
        {"id": "pkg_b", "label": "os", "source_file": "src/pkg/sub/b.py"},
        {"id": "meta", "label": "no source file"},
    ]


def test_passage_contract_matches_entity_source_file(tmp_path: Path) -> None:
    graph = _write_graph(tmp_path / "graph.json", _entities())
    _make_tree(tmp_path / "repo")

    stats = add_passage_nodes(graph, tmp_path / "repo", backup=False)

    assert stats["passages_added"] == 2
    assert stats["missing_on_disk"] == []
    raw = json.loads(graph.read_text(encoding="utf-8"))
    passages = {n["id"]: n for n in raw["nodes"] if n.get("type") == PASSAGE_TYPE}
    # Passage graph-key == entity source_file verbatim (adapter file_id match).
    assert set(passages) == {"src/pkg/a.py", "src/pkg/sub/b.py"}
    assert passages["src/pkg/a.py"]["label"] == "VALUE = 1\n"
    assert passages["src/pkg/sub/b.py"]["label"] == "import os\n"
    assert passages["src/pkg/a.py"]["source_file"] == "src/pkg/a.py"
    # Entities untouched.
    by_id = {n["id"]: n for n in raw["nodes"] if n.get("type") != PASSAGE_TYPE}
    assert by_id["pkg_a"]["label"] == "VALUE"
    assert by_id["meta"]["label"] == "no source file"


def test_missing_file_is_skipped_and_reported(tmp_path: Path) -> None:
    nodes = _entities()
    nodes.append({"id": "ghost", "label": "x", "source_file": "src/pkg/ghost.py"})
    graph = _write_graph(tmp_path / "graph.json", nodes)
    _make_tree(tmp_path / "repo")

    stats = add_passage_nodes(graph, tmp_path / "repo", backup=False)

    assert stats["missing_on_disk"] == ["src/pkg/ghost.py"]
    assert stats["passages_added"] == 2  # the two real files still land
    raw = json.loads(graph.read_text(encoding="utf-8"))
    assert "src/pkg/ghost.py" not in {n["id"] for n in raw["nodes"]}


def test_rerun_refreshes_not_duplicates(tmp_path: Path) -> None:
    graph = _write_graph(tmp_path / "graph.json", _entities())
    repo = tmp_path / "repo"
    _make_tree(repo)
    add_passage_nodes(graph, repo, backup=False)

    (repo / "src" / "pkg" / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    stats = add_passage_nodes(graph, repo, backup=False)

    assert stats["passages_added"] == 0
    assert stats["passages_updated"] == 2
    assert stats["total_passages"] == 2
    raw = json.loads(graph.read_text(encoding="utf-8"))
    passages = [n for n in raw["nodes"] if n.get("type") == PASSAGE_TYPE]
    assert len(passages) == 2
    assert {n["id"]: n["label"] for n in passages}["src/pkg/a.py"] == "VALUE = 2\n"


def test_files_restriction_and_not_in_graph_report(tmp_path: Path) -> None:
    graph = _write_graph(tmp_path / "graph.json", _entities())
    _make_tree(tmp_path / "repo")

    stats = add_passage_nodes(
        graph,
        tmp_path / "repo",
        files=["src/pkg/a.py", "src/pkg/unreferenced.py"],
        backup=False,
    )

    assert stats["passages_added"] == 1
    assert stats["requested_not_in_graph"] == ["src/pkg/unreferenced.py"]
    raw = json.loads(graph.read_text(encoding="utf-8"))
    assert {n["id"] for n in raw["nodes"] if n.get("type") == PASSAGE_TYPE} == {
        "src/pkg/a.py"
    }


def test_backup_created_once(tmp_path: Path) -> None:
    graph = _write_graph(tmp_path / "graph.json", _entities())
    _make_tree(tmp_path / "repo")
    backup = tmp_path / "graph.json.passage-bak"

    add_passage_nodes(graph, tmp_path / "repo")
    assert backup.is_file()
    first = json.loads(backup.read_text(encoding="utf-8"))
    assert all(n.get("type") != PASSAGE_TYPE for n in first["nodes"])

    add_passage_nodes(graph, tmp_path / "repo")  # second run must not clobber
    assert json.loads(backup.read_text(encoding="utf-8")) == first
