from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterator


def query_id(query: str, entry_id: str | None = None) -> str:
    """Stable id for a history row (matches append_history id field)."""
    if entry_id:
        return entry_id
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()[:16]


def _line_id(query: str) -> str:
    return query_id(query)


def append_history(
    path: Path,
    query: str,
    *,
    source: str = "user",
    refined: bool = False,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": _line_id(query),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "query": query.strip(),
        "source": source,
        "refined": refined,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def iter_history(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def pending_queries(path: Path) -> list[dict[str, Any]]:
    seen: set[str] = set()
    pending: list[dict[str, Any]] = []
    for row in iter_history(path):
        q = row.get("query", "").strip()
        if not q or row.get("refined") is True:
            continue
        qid = row.get("id") or _line_id(q)
        if qid in seen:
            continue
        seen.add(qid)
        pending.append(row)
    return pending


def mark_refined(path: Path, query_ids: set[str]) -> None:
    if not path.is_file() or not query_ids:
        return
    rows: list[dict[str, Any]] = list(iter_history(path))
    changed = False
    for row in rows:
        qid = row.get("id") or _line_id(row.get("query", ""))
        if qid in query_ids and not row.get("refined"):
            row["refined"] = True
            row["refined_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            changed = True
    if changed:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
