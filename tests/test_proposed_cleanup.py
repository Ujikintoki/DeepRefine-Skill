"""Tests for stale ``proposed_*`` artifact cleanup (rollback hygiene).

``refine``/``apply`` write per-query proposal files under
``graphify-out/.deeprefine`` that nothing cleaned up, so they accumulated
across rounds — a round-N leftover was once misread as a round-N+1 proposal
in an audit. ``rollback`` now clears them on every successful restore; these
tests pin the helper semantics and both rollback branches. All fixtures are
on-disk ``tmp_path`` sandboxes, driven through ``main()`` like
``test_wiki_refresh.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from deeprefine_skill.cli import main
from deeprefine_skill.core.paths import (
    clear_proposed_artifacts,
    proposed_artifacts,
)


def _sandbox_with_proposals(tmp_path: Path) -> tuple[Path, Path]:
    deep = tmp_path / "graphify-out" / ".deeprefine"
    deep.mkdir(parents=True)
    (deep / "proposed_refinement_actions_sq-000.txt").write_text(
        "old proposal", encoding="utf-8"
    )
    (deep / "proposed_refinement_review_sq-000.json").write_text("{}", encoding="utf-8")
    (deep / "history.jsonl").write_text("{}", encoding="utf-8")
    return deep, deep / "history.jsonl"


def test_proposed_artifacts_globs_only_proposed_sorted(tmp_path: Path) -> None:
    """The helper lists proposed_* files only, in deterministic order."""
    deep, _ = _sandbox_with_proposals(tmp_path)

    names = [p.name for p in proposed_artifacts(tmp_path)]

    assert names == [
        "proposed_refinement_actions_sq-000.txt",
        "proposed_refinement_review_sq-000.json",
    ]
    assert all(p.parent == deep for p in proposed_artifacts(tmp_path))


def test_clear_removes_only_proposed_and_is_idempotent(tmp_path: Path) -> None:
    """Cleanup deletes proposed_*, keeps neighbours, and is safe to re-run."""
    deep, history = _sandbox_with_proposals(tmp_path)

    assert clear_proposed_artifacts(tmp_path) == 2
    assert list(deep.glob("proposed_*")) == []
    assert history.is_file()
    assert clear_proposed_artifacts(tmp_path) == 0


def test_clear_without_deeprefine_dir_returns_zero(tmp_path: Path) -> None:
    """A project without graphify-out/.deeprefine is a zero-count no-op."""

    assert proposed_artifacts(tmp_path) == []
    assert clear_proposed_artifacts(tmp_path) == 0


def _make_rollback_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Minimal project that supports ``rollback --query sq-000`` / ``rollback 1``."""
    project = tmp_path / "project"
    out = project / "graphify-out"
    deep = out / ".deeprefine"
    deep.mkdir(parents=True)

    graph = out / "graph.json"
    graph.write_text('{"nodes": ["post"]}', encoding="utf-8")
    pre_state = deep / "graph.json.bak.1"
    pre_state.write_text('{"nodes": ["pre"]}', encoding="utf-8")
    checkpoint = deep / "checkpoints" / "graph.checkpoint.1.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('{"nodes": ["post"]}', encoding="utf-8")
    (deep / "checkpoints.json").write_text(
        json.dumps(
            [
                {
                    "seq": 1,
                    "query_id": "sq-000",
                    "query_text": "question",
                    "ts": "2026-09-08T00:00:00Z",
                    "path": str(checkpoint),
                }
            ]
        ),
        encoding="utf-8",
    )
    (deep / "history.jsonl").write_text(
        json.dumps({"id": "sq-000", "refined": True}) + "\n", encoding="utf-8"
    )
    (deep / "proposed_refinement_actions_sq-000.txt").write_text(
        "round-1 leftover", encoding="utf-8"
    )
    (deep / "proposed_refinement_review_sq-000.json").write_text(
        "{}", encoding="utf-8"
    )
    return project, graph, pre_state


def test_rollback_by_query_clears_stale_proposed_artifacts(
    tmp_path: Path, capsys
) -> None:
    """``rollback --query`` restores the pre-state AND drops stale proposals."""
    project, graph, pre_state = _make_rollback_project(tmp_path)

    rc = main(["rollback", "--query", "sq-000", "--project-root", str(project)])

    assert rc == 0
    assert graph.read_text(encoding="utf-8") == pre_state.read_text(encoding="utf-8")
    deep = project / "graphify-out" / ".deeprefine"
    assert list(deep.glob("proposed_*")) == []
    assert (deep / "history.jsonl").is_file()
    assert (deep / "checkpoints" / "graph.checkpoint.1.json").is_file()
    assert "Cleared 2 stale proposed_* file(s)" in capsys.readouterr().out


def test_rollback_to_seq_clears_stale_proposed_artifacts(
    tmp_path: Path, capsys
) -> None:
    """``rollback <seq>`` behaves the same on the checkpoint branch."""
    project, _graph, _pre_state = _make_rollback_project(tmp_path)

    rc = main(["rollback", "1", "--project-root", str(project)])

    assert rc == 0
    deep = project / "graphify-out" / ".deeprefine"
    assert list(deep.glob("proposed_*")) == []
    assert "Cleared 2 stale proposed_* file(s)" in capsys.readouterr().out
