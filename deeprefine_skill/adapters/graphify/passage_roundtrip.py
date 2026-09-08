"""Preserve staged passage nodes across the refine write-back roundtrip.

``sync_kg_to_graphify`` rebuilds graph.json from the refinement graph, and
the engine excludes passage nodes from that graph by design — they are text
sources, not entities (upstream deeprefine.py routes them into its text map
at init and filters them out of the working subgraph). Without help, every
write-back therefore drops the ``type=="passage"`` nodes that
``passage_nodes.py`` staged, and the next refine run silently degrades to
closed-book. This module carries them across the sync verbatim: snapshot
before the rebuild, re-append after it.

Staging adds no incident links (a passage is tied to entities only through
the shared ``source_file`` string), and links touching passage endpoints are
deliberately NOT re-introduced here: ``parallel_links.py`` already treats a
passage endpoint as "endpoint gone" and must not be bypassed. Like the other
graphify adapter helpers (entity_fold.py, parallel_links.py), this module
must stay importable without the upstream stack (atlas_rag lives in a
sibling checkout reachable only at runtime) — standard library only.
"""

from __future__ import annotations

import copy
from typing import Any


def split_passages(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Snapshot the passage nodes of a graphify raw dict (deep copies).

    Call this BEFORE the sync overwrites ``raw["nodes"]`` — the snapshot is
    the only place staged passages still exist at write-back time, since the
    refinement kg never contains them. Nodes are returned verbatim (id,
    label=full text, type="passage", source_file), so re-appending them
    reproduces exactly what staging wrote.
    """
    return [
        copy.deepcopy(node)
        for node in raw.get("nodes", [])
        if node.get("type") == "passage"
    ]


def merge_passages(
    out: dict[str, Any], passages: list[dict[str, Any]]
) -> dict[str, Any]:
    """Re-append passage nodes into a freshly synced node-link dict.

    Entities win on id collisions (mirrors staging's own skip rule when a
    non-passage node occupies a passage key), and the appended node dicts
    are deep copies so caller-owned structures are never shared. The merge
    is a no-op when nothing was staged.
    """
    if not passages:
        return out
    present = {node.get("id") for node in out.get("nodes", [])}
    out.setdefault("nodes", []).extend(
        copy.deepcopy(node) for node in passages if node.get("id") not in present
    )
    return out
