"""Tests for index cache bundle invalidation on rollback (B8).

``refine`` caches the built working data (graphify raw + embeddings) under
``graphify-out/.deeprefine/cache/`` and trusts it purely by mtime
(``cache_pkl.st_mtime >= graph.json.st_mtime``). Rollback restores
graph.json via ``shutil.copy2``, which preserves the backup's original
mtime — an older state reappears carrying an older mtime, so a bundle built
from a newer, since-undone state can pass the freshness check and be
replayed silently. Rollback now deletes every scope variant
(``deeprefine_data[-<scope>].pkl``); these tests pin the helper semantics
and both rollback branches, in the same shape as test_proposed_cleanup.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from deeprefine_skill.cli import main
from deeprefine_skill.core.paths import cache_bundles, clear_cache_bundles


def _sandbox_with_bundles(tmp_path: Path) -> tuple[Path, Path]:
    cache = tmp_path / "graphify-out" / ".deeprefine" / "cache"
    cache.mkdir(parents=True)
    (cache / "deeprefine_data.pkl").write_bytes(b"all-scope bundle")
    (cache / "deeprefine_data-code.pkl").write_bytes(b"code-scope bundle")
    (cache / "unrelated.txt").write_text("keep me", encoding="utf-8")
    return cache, cache / "unrelated.txt"


def test_cache_bundles_globs_all_scope_variants_sorted(tmp_path: Path) -> None:
    """The helper lists every scope variant, in deterministic order."""
    cache, _unrelated = _sandbox_with_bundles(tmp_path)

    names = [p.name for p in cache_bundles(tmp_path)]

    assert names == ["deeprefine_data-code.pkl", "deeprefine_data.pkl"]
    assert all(p.parent == cache for p in cache_bundles(tmp_path))


def test_clear_removes_all_bundles_and_is_idempotent(tmp_path: Path) -> None:
    """Cleanup deletes every bundle, keeps neighbours, and is safe to re-run."""
    cache, unrelated = _sandbox_with_bundles(tmp_path)

    assert clear_cache_bundles(tmp_path) == 2
    assert list(cache.glob("deeprefine_data*.pkl")) == []
    assert unrelated.is_file()
    assert clear_cache_bundles(tmp_path) == 0


def test_clear_without_cache_dir_returns_zero(tmp_path: Path) -> None:
    """A project without the cache dir is a zero-count no-op."""

    assert cache_bundles(tmp_path) == []
    assert clear_cache_bundles(tmp_path) == 0


def _make_rollback_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Minimal project that supports ``rollback --query sq-000`` / ``rollback 1``,
    plus the index cache bundle the undone refinement would have left behind."""
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
    cache = deep / "cache"
    cache.mkdir()
    (cache / "deeprefine_data.pkl").write_bytes(b"bundle of the undone state")
    return project, graph, pre_state


def test_rollback_by_query_invalidates_cache_bundles(
    tmp_path: Path, capsys
) -> None:
    """``rollback --query`` restores the pre-state AND drops the stale bundle."""
    project, graph, pre_state = _make_rollback_project(tmp_path)

    rc = main(["rollback", "--query", "sq-000", "--project-root", str(project)])

    assert rc == 0
    assert graph.read_text(encoding="utf-8") == pre_state.read_text(encoding="utf-8")
    deep = project / "graphify-out" / ".deeprefine"
    assert list(deep.glob("cache/deeprefine_data*.pkl")) == []
    assert (deep / "history.jsonl").is_file()
    assert (deep / "checkpoints" / "graph.checkpoint.1.json").is_file()
    assert "Cleared 1 index cache bundle(s)" in capsys.readouterr().out


def test_rollback_to_seq_invalidates_cache_bundles(
    tmp_path: Path, capsys
) -> None:
    """``rollback <seq>`` behaves the same on the checkpoint branch."""
    project, _graph, _pre_state = _make_rollback_project(tmp_path)

    rc = main(["rollback", "1", "--project-root", str(project)])

    assert rc == 0
    deep = project / "graphify-out" / ".deeprefine"
    assert list(deep.glob("cache/deeprefine_data*.pkl")) == []
    assert "Cleared 1 index cache bundle(s)" in capsys.readouterr().out
