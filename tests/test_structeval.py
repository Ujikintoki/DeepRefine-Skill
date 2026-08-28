"""Public-contract tests for the structural evaluator (AST gold vs graph).

The gold side is extracted with stdlib ``ast`` from tiny fixture trees, so
every expected number below is hand-checkable — the same discipline the
bundled smoke suite follows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Import the engine through the ``eval.benchmarking`` namespace package.
# The repo root goes on sys.path so the import resolves; ``eval/`` is
# intentionally left without an ``__init__.py`` so it never enters the wheel.
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from eval.benchmarking.ast_gold import extract_gold
from eval.benchmarking.cli import main as bench_main
from eval.benchmarking.structeval import (
    compare_runs,
    emit_queries,
    evaluate_structure,
)


def _write_tree(root: Path) -> None:
    """Six-module fixture tree with module-level AND function-scoped imports."""

    pkg = root / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text("from pkg import alpha\n", encoding="utf-8")
    (pkg / "alpha.py").write_text(
        "import pkg.sub.charlie\n"
        "from pkg.beta import helper\n"
        "\n"
        "def runner():\n"
        "    from pkg import delta\n"
        "    return delta\n",
        encoding="utf-8",
    )
    (pkg / "beta.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (pkg / "delta.py").write_text("", encoding="utf-8")
    (pkg / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "sub" / "charlie.py").write_text("", encoding="utf-8")


def test_extract_gold_enumerates_modules_symbols_and_imports(tmp_path: Path) -> None:
    tree = tmp_path / "src"
    _write_tree(tree)

    gold = extract_gold(tree, source_tag="test")

    assert gold.modules == (
        "pkg/__init__.py",
        "pkg/alpha.py",
        "pkg/beta.py",
        "pkg/delta.py",
        "pkg/sub/__init__.py",
        "pkg/sub/charlie.py",
    )
    assert gold.file_count == 6
    # Module dependencies include the function-scoped ``from pkg import delta``.
    assert gold.module_dependencies() == {
        ("pkg/__init__.py", "pkg/alpha.py"),
        ("pkg/alpha.py", "pkg/beta.py"),
        ("pkg/alpha.py", "pkg/sub/charlie.py"),
        ("pkg/alpha.py", "pkg/delta.py"),
    }
    assert gold.symbol_imports() == {("pkg/alpha.py", "pkg/beta.py", "helper")}
    assert gold.symbols["pkg/beta.py"] == ("helper",)


def test_extract_gold_resolves_relative_and_skips_external(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg2"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "one.py").write_text(
        "import os\n"
        "from .two import thing\n"
        "from . import three\n"
        "from ..missing import gone\n",
        encoding="utf-8",
    )
    (pkg / "two.py").write_text("def thing():\n    return 1\n", encoding="utf-8")
    (pkg / "three.py").write_text("", encoding="utf-8")

    gold = extract_gold(tmp_path)

    # ``import os`` (stdlib) and ``from ..missing import gone`` (outside the
    # tree) are excluded; both relative forms resolve to project modules.
    assert gold.module_dependencies() == {
        ("pkg2/one.py", "pkg2/two.py"),
        ("pkg2/one.py", "pkg2/three.py"),
    }
    assert gold.symbol_imports() == {("pkg2/one.py", "pkg2/two.py", "thing")}


def _graph_fixture() -> dict:
    """A hand-checkable Graphify node-link graph for the pkg fixture tree.

    Encodes three error classes at once: one missing gold dependency
    (alpha -> delta), one unverified claim (alpha -> ghost), and one
    phantom module node — plus one missing module node.
    """

    return {
        "directed": True,
        "multigraph": True,
        "nodes": [
            {"id": "init", "label": "__init__.py", "source_file": "pkg/__init__.py"},
            {"id": "alpha", "label": "alpha.py", "source_file": "pkg/alpha.py"},
            {"id": "beta", "label": "beta.py", "source_file": "pkg/beta.py"},
            {"id": "charlie", "label": "charlie.py", "source_file": "pkg/sub/charlie.py"},
            {"id": "delta", "label": "delta.py", "source_file": "pkg/delta.py"},
            {"id": "ghost", "label": "ghost.py", "source_file": "pkg/ghost.py"},
            {"id": "helper", "label": "helper()", "source_file": "pkg/beta.py"},
        ],
        "links": [
            {"source": "init", "target": "alpha", "relation": "imports"},
            {"source": "alpha", "target": "charlie", "relation": "imports"},
            {"source": "alpha", "target": "beta", "relation": "imports"},
            {"source": "alpha", "target": "helper", "relation": "imports_from"},
            {"source": "alpha", "target": "ghost", "relation": "imports"},
        ],
    }


def test_evaluate_structure_is_hand_checkable(tmp_path: Path) -> None:
    tree = tmp_path / "src"
    _write_tree(tree)
    gold = extract_gold(tree)

    result = evaluate_structure(gold, _graph_fixture())

    # Module nodes: 13-style counting — 6 predicted, 5 real (ghost is
    # phantom), 6 gold modules with sub/__init__ unrepresented.
    assert result["metrics"]["module_nodes"] == {
        "precision": pytest.approx(5 / 6),
        "recall": pytest.approx(5 / 6),
        "f1": pytest.approx(5 / 6),
        "tp": 5,
        "fp": 1,
        "fn": 1,
    }
    # Dependencies: 3 of 4 captured, ghost claim unverified, delta missing.
    assert result["metrics"]["module_dependencies"] == {
        "precision": pytest.approx(0.75),
        "recall": pytest.approx(0.75),
        "f1": pytest.approx(0.75),
        "tp": 3,
        "fp": 1,
        "fn": 1,
    }
    assert result["metrics"]["symbol_imports"]["f1"] == pytest.approx(1.0)

    assert result["details"]["phantom_module_nodes"] == ["pkg/ghost.py"]
    assert result["details"]["missing_module_nodes"] == ["pkg/sub/__init__.py"]
    assert result["details"]["missing_module_dependencies"] == [
        "pkg/alpha.py -> pkg/delta.py"
    ]
    assert result["details"]["unverified_import_edges"] == [
        "pkg/alpha.py -> pkg/ghost.py"
    ]


def test_structeval_cli_smoke(tmp_path: Path) -> None:
    tree = tmp_path / "src"
    _write_tree(tree)
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")
    output_dir = tmp_path / "out"

    exit_code = bench_main(
        [
            "structeval",
            "--graph",
            str(graph_path),
            "--source-tree",
            str(tree),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    result = json.loads(
        (output_dir / "structeval_result.json").read_text(encoding="utf-8")
    )
    assert result["schema_version"] == 1
    assert result["kind"] == "structural"
    report = (output_dir / "structural_report.md").read_text(encoding="utf-8")
    assert "Structural Evaluation" in report
    assert "Module dependency edges" in report


def test_evaluate_structure_is_deterministic(tmp_path: Path) -> None:
    tree = tmp_path / "src"
    _write_tree(tree)
    gold = extract_gold(tree)

    assert evaluate_structure(gold, _graph_fixture()) == evaluate_structure(
        gold, _graph_fixture()
    )


def test_emit_queries_and_transition_diff(tmp_path: Path) -> None:
    tree = tmp_path / "src"
    _write_tree(tree)
    gold = extract_gold(tree)
    baseline = evaluate_structure(gold, _graph_fixture())

    queries_path = tmp_path / "queries.jsonl"
    count = emit_queries(baseline, queries_path)
    lines = [
        json.loads(line)
        for line in queries_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert count == len(lines) == 1
    assert lines[0]["gold"] == "pkg/alpha.py -> pkg/delta.py"
    assert "depend on" in lines[0]["query"]

    # A "refined" graph recovers the missing dependency and drops the
    # ghost claim — the transition diff must see exactly that.
    fixed = json.loads(json.dumps(_graph_fixture()))
    fixed["links"] = [
        link for link in fixed["links"] if link["target"] != "ghost"
    ]
    fixed["links"].append({"source": "alpha", "target": "delta", "relation": "imports"})
    candidate = evaluate_structure(gold, fixed)

    transitions = compare_runs(baseline, candidate)
    assert transitions["module_dependencies"]["recovered_0_to_1"] == [
        "pkg/alpha.py -> pkg/delta.py"
    ]
    assert transitions["module_dependencies"]["still_missing"] == []
    assert transitions["unverified_import_edges"]["resolved"] == [
        "pkg/alpha.py -> pkg/ghost.py"
    ]
    assert transitions["unverified_import_edges"]["new_unverified"] == []
