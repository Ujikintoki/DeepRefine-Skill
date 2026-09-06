"""Build passage nodes in a graphify graph.json from the user's own source files.

The upstream DeepRefine refine loop reads original document text at action
time: ``_collect_original_text`` (upstream deeprefine.py) maps each entity in
the retrieved subgraph to its ``file_id`` and feeds the linked document text
into the refinement action prompt.  The research repo's constructor always
ships that text sidecar; graphify does not — it emits entity nodes whose
``source_file`` points at the user's file but carries no content, so
``build_deeprefine_data`` falls back to a placeholder and refine silently
degrades to closed-book.

This script restores the paper's default configuration for graphify graphs:
one passage node per source file the graph already references.  Node contract
(see ``load_graphify_json`` in adapter.py):

- the passage node's **graph key** (its ``id`` field in graph.json) must equal
  the entity nodes' ``source_file`` verbatim — that value becomes each
  entity's ``file_id``;
- the passage node's **label** carries the file text (``load_graphify_json``
  copies label → the internal ``id`` attr, which upstream reads as the text);
- ``type`` is ``"passage"`` so the node stays out of the entity FAISS corpus
  and is stripped again by ``sync_kg_to_graphify`` on write-back.

Usage:
    python -m deeprefine_skill.adapters.graphify.passage_nodes \
        --graph graphify-out/graph.json --source-root /path/to/project
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PASSAGE_TYPE = "passage"
BACKUP_SUFFIX = ".passage-bak"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _referenced_files(nodes: list[dict[str, Any]]) -> set[str]:
    """Distinct source_file values on non-passage nodes (passage candidates)."""
    referenced: set[str] = set()
    for node in nodes:
        if node.get("type") == PASSAGE_TYPE:
            continue
        source_file = node.get("source_file")
        if isinstance(source_file, str) and source_file:
            referenced.add(source_file)
    return referenced


def add_passage_nodes(
    graph_path: Path,
    source_root: Path,
    *,
    files: list[str] | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    """Add/update one passage node per referenced source file.

    ``files`` optionally restricts the set (default: every distinct
    ``source_file`` found on graph nodes).  Idempotent: a passage node that
    already exists for a file gets its label refreshed, never duplicated.
    The graph is probed before mutation, so a missing source file is reported
    and skipped — never a crash mid-write — and a one-time ``*.passage-bak``
    copy keeps the pre-passage graph recoverable.
    """
    graph_path = Path(graph_path)
    source_root = Path(source_root)
    raw = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes: list[dict[str, Any]] = raw.setdefault("nodes", [])

    referenced = _referenced_files(nodes)
    requested = set(files) if files is not None else None
    targets = referenced & requested if requested is not None else referenced

    # Probe disk before mutating anything: missing files are a reported skip.
    on_disk = sorted(rel for rel in targets if (source_root / rel).is_file())
    missing = sorted(targets - set(on_disk))
    not_in_graph = sorted((requested or set()) - referenced)

    by_id = {node.get("id"): node for node in nodes}
    added = 0
    updated = 0
    collisions: list[str] = []
    for rel in on_disk:
        text = _read_text(source_root / rel)
        node = by_id.get(rel)
        if node is not None and node.get("type") == PASSAGE_TYPE:
            node["label"] = text  # idempotent refresh
            updated += 1
        elif node is not None:
            # A non-passage node already owns this graph key.  Entity ids are
            # graphify-generated slugs and passage keys are file paths, so a
            # collision means source_file equals an entity id; hosting the
            # text there would clobber the entity.  Skip and report.
            collisions.append(rel)
        else:
            new_node = {
                "id": rel,
                "label": text,
                "type": PASSAGE_TYPE,
                "source_file": rel,
            }
            nodes.append(new_node)
            by_id[rel] = new_node
            added += 1

    backup_path = graph_path.with_name(graph_path.name + BACKUP_SUFFIX)
    if backup and not backup_path.is_file():
        shutil.copy2(graph_path, backup_path)
    graph_path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        "passages_added": added,
        "passages_updated": updated,
        "collisions": collisions,
        "missing_on_disk": missing,
        "requested_not_in_graph": not_in_graph,
        "total_passages": sum(
            1 for node in nodes if node.get("type") == PASSAGE_TYPE
        ),
        "graph_nodes_after": len(nodes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deeprefine-passage-nodes",
        description="Add one passage node per referenced source file "
        "(open-book refine support; see module docstring for the contract).",
    )
    parser.add_argument("--graph", required=True, help="graphify graph.json path")
    parser.add_argument(
        "--source-root",
        required=True,
        help="root that the graph's source_file paths resolve against",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=None,
        help="restrict to this source_file (repeatable; default: all referenced files)",
    )
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args(argv)

    stats = add_passage_nodes(
        Path(args.graph),
        Path(args.source_root),
        files=args.file,
        backup=not args.no_backup,
    )
    json.dump(stats, sys.stdout, indent=2, ensure_ascii=False)
    print()
    if stats["missing_on_disk"]:
        print(
            f"!! {len(stats['missing_on_disk'])} referenced file(s) missing on disk: "
            f"{stats['missing_on_disk']}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
