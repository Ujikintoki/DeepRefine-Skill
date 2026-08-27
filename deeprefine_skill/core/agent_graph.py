"""Apply DeepRefine refinement actions to graphify graph.json (agent loop step 5)."""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


def _norm_label(s: str) -> str:
    return unicodedata.normalize("NFKC", s.strip()).casefold()


def _split_qualified_label(label: str) -> tuple[str | None, str]:
    if "::" not in label:
        return None, label
    src, name = label.rsplit("::", 1)
    return src.strip() or None, name.strip()


def _same_source(node_src: str | None, query_src: str | None) -> bool:
    if not node_src or not query_src:
        return False
    node_src = node_src.replace("\\", "/").strip()
    query_src = query_src.replace("\\", "/").strip()
    return (
        node_src == query_src
        or node_src.endswith("/" + query_src)
        or query_src.endswith("/" + node_src)
    )


def _find_node_id_by_label(nodes: list[dict[str, Any]], label: str) -> str | None:
    query_src, query_label = _split_qualified_label(label)
    target = _norm_label(query_label)
    for n in nodes:
        node_src = n.get("source_file") or n.get("file_id") or n.get("source_url")
        if query_src and not _same_source(str(node_src) if node_src else None, query_src):
            continue
        if _norm_label(n.get("label", "")) == target:
            return n["id"]
        for alias in n.get("aliases") or []:
            if _norm_label(str(alias)) == target:
                return n["id"]
    return None


def _ensure_node(
    nodes: list[dict[str, Any]], label: str, *, source_file: str | None = None
) -> str:
    nid = _find_node_id_by_label(nodes, label)
    if nid:
        return nid
    slug = re.sub(r"[^a-z0-9]+", "_", _norm_label(label)).strip("_") or "node"
    base = f"deeprefine_{slug}"
    existing = {n["id"] for n in nodes}
    nid = base
    i = 0
    while nid in existing:
        i += 1
        nid = f"{base}_{i}"
    nodes.append(
        {
            "id": nid,
            "label": label,
            "file_type": "rationale",
            "source_file": source_file or "deeprefine",
            "source_location": "agent-loop",
            "source_url": None,
            "captured_at": None,
            "author": None,
            "contributor": "deeprefine",
            "community": 0,
            "norm_label": _norm_label(label),
        }
    )
    return nid


def _parse_action_string(action: str) -> tuple[str, list[str]]:
    action = re.sub(r"\s+", " ", action.strip())
    match = re.match(r"(\w+)\s*\((.*)\)\s*$", action)
    if not match:
        raise ValueError(f"Invalid action: {action}")
    name = match.group(1)
    args_str = match.group(2).strip()
    parsed: list[str] = []
    i = 0
    while i < len(args_str):
        while i < len(args_str) and args_str[i] in " \t,":
            i += 1
        if i >= len(args_str):
            break
        q = args_str[i]
        if q not in ('"', "'"):
            raise ValueError(f"Expected quoted arg: {action}")
        i += 1
        buf: list[str] = []
        while i < len(args_str):
            if args_str[i] == "\\" and i + 1 < len(args_str):
                buf.append(args_str[i + 1])
                i += 2
            elif args_str[i] == q:
                parsed.append("".join(buf))
                i += 1
                break
            else:
                buf.append(args_str[i])
                i += 1
        else:
            raise ValueError(f"Unclosed quote: {action}")
    return name, parsed


def parse_refinement_block(text: str) -> list[str]:
    m = re.search(r"<refinement>(.*?)</refinement>", text, re.IGNORECASE | re.DOTALL)
    if m:
        body = m.group(1).strip().strip("|")
    else:
        calls = re.findall(
            r"(?:insert_edge|delete_edge|replace_node)\s*\([^)]*\)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not calls:
            raise ValueError("No <refinement> block or action calls found")
        body = "|".join(calls)
    actions = []
    for part in re.split(r"[\|\n]+", body):
        part = part.strip()
        if part:
            actions.append(part)
    return actions


def apply_actions_to_graphify(
    raw: dict[str, Any],
    action_strings: list[str],
) -> list[str]:
    """Apply insert/delete/replace actions; return human-readable change log."""
    data = copy.deepcopy(raw)
    links_key = "links" if "links" in data else "edges"
    nodes: list[dict[str, Any]] = data.setdefault("nodes", [])
    links: list[dict[str, Any]] = data.setdefault(links_key, [])
    changes: list[str] = []

    def _link_key(l: dict[str, Any]) -> tuple[str, str, str]:
        return (l["source"], l["target"], l.get("relation", ""))

    for action in action_strings:
        fn, args = _parse_action_string(action)
        if fn == "insert_edge":
            sub, rel, obj = args[0], args[1], args[2]
            sid = _ensure_node(nodes, sub)
            tid = _ensure_node(nodes, obj)
            key = (sid, tid, rel)
            if not any(_link_key(l) == key for l in links):
                links.append(
                    {
                        "source": sid,
                        "target": tid,
                        "relation": rel,
                        "confidence": "INFERRED",
                        "confidence_score": 0.9,
                        "source_file": "deeprefine",
                        "source_location": "agent-loop",
                        "weight": 1.0,
                    }
                )
                changes.append(f"insert_edge({sub}, {rel}, {obj})")
        elif fn == "delete_edge":
            sub, rel, obj = args[0], args[1], args[2]
            sid = _find_node_id_by_label(nodes, sub)
            tid = _find_node_id_by_label(nodes, obj)
            if sid and tid:
                before = len(links)
                links[:] = [
                    l
                    for l in links
                    if not (
                        l["source"] == sid
                        and l["target"] == tid
                        and l.get("relation") == rel
                    )
                ]
                if len(links) < before:
                    changes.append(f"delete_edge({sub}, {rel}, {obj})")
        elif fn == "replace_node":
            old, new = args[0], args[1]
            nid = _find_node_id_by_label(nodes, old)
            if nid:
                for n in nodes:
                    if n["id"] == nid:
                        n["label"] = new
                        n["norm_label"] = _norm_label(new)
                        aliases = list(n.get("aliases") or [])
                        if old not in aliases:
                            aliases.append(old)
                        n["aliases"] = aliases
                        changes.append(f"replace_node({old}, {new})")
                        break
        else:
            raise ValueError(f"Unknown action: {fn}")

    raw.clear()
    raw.update(data)
    return changes


def apply_refinement_text(graph_path: Path, refinement_text: str) -> list[str]:
    actions = parse_refinement_block(refinement_text)
    raw = json.loads(graph_path.read_text(encoding="utf-8"))
    changes = apply_actions_to_graphify(raw, actions)
    graph_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    return changes
