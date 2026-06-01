"""DeepRefine CLI: `deeprefine cursor install` (graphify-style)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from deeprefine_skill.history import append_history, iter_history, pending_queries
from deeprefine_skill.installers import install_cursor_skill, uninstall_cursor_skill
from deeprefine_skill.paths import (
    env_defaults,
    find_deeprefine_repo,
    find_project_root,
    graphify_paths,
    setup_import_paths,
)


def _setup_repo_imports() -> None:
    setup_import_paths(find_deeprefine_repo())


def cmd_cursor_install(args: argparse.Namespace) -> int:
    dest = install_cursor_skill(project=args.project)
    scope = "project" if args.project else "user"
    print(f"Installed DeepRefine Cursor skill ({scope}) → {dest}")
    if args.project:
        print("Open this folder in Cursor, then use /deeprefine in chat.")
    return 0


def cmd_cursor_uninstall(args: argparse.Namespace) -> int:
    removed = uninstall_cursor_skill(project=args.project)
    if removed:
        scope = "project" if args.project else "user"
        print(f"Removed DeepRefine Cursor skill ({scope}).")
    else:
        print("Skill not installed at the selected scope.")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    """Alias for `deeprefine cursor install` (graphify-compatible naming)."""
    return cmd_cursor_install(args)


def cmd_history_add(args: argparse.Namespace) -> int:
    project = find_project_root()
    paths = graphify_paths(project)
    entry = append_history(
        paths["history"], args.query, source=args.source, refined=False
    )
    print(f"Recorded: {entry['id']} → {paths['history']}")
    return 0


def cmd_history_list(args: argparse.Namespace) -> int:
    project = find_project_root()
    paths = graphify_paths(project)
    rows = (
        pending_queries(paths["history"])
        if args.pending
        else list(iter_history(paths["history"]))
    )
    if not rows and args.pending:
        print("No pending queries.")
        return 0
    for row in rows:
        flag = "refined" if row.get("refined") else "pending"
        print(f"[{flag}] {row.get('id', '?')}: {row.get('query', '')}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    _setup_repo_imports()
    from deeprefine_skill.adapter_graphify import load_or_build_data
    from deeprefine_skill.refine_runner import make_clients

    project = find_project_root()
    paths = graphify_paths(project)
    cfg = env_defaults()
    llm, encoder = make_clients(cfg)
    del llm
    load_or_build_data(
        paths["graph_json"],
        paths["reafiner_pkl"],
        encoder,
        rebuild=True,
    )
    print(f"Index cache: {paths['reafiner_pkl']}")
    return 0


def cmd_refine(args: argparse.Namespace) -> int:
    _setup_repo_imports()
    from deeprefine_skill.refine_runner import refine_from_history

    project = find_project_root(Path(args.project_root) if args.project_root else None)
    paths = graphify_paths(project)
    cfg = env_defaults()
    result = refine_from_history(
        paths,
        cfg,
        query=args.query,
        rebuild_index=args.rebuild_index,
    )
    print("\n--- DeepRefine summary ---")
    print(f"Queries processed: {result['queries_processed']}")
    print(f"Graph: {result['graph_path']} ({result['nodes']} nodes, {result['edges']} edges)")
    print(f"Log: {result['log_path']}")
    return 0


def _add_project_flag(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--project",
        action="store_true",
        default=None,
        help="Install to .cursor/skills in the current directory (default for cursor install)",
    )
    group.add_argument(
        "--user",
        action="store_true",
        help="Install to ~/.cursor/skills (all projects)",
    )


def _resolve_project(args: argparse.Namespace, *, default_project: bool) -> None:
    if getattr(args, "user", False):
        args.project = False
    elif getattr(args, "project", None) is True:
        args.project = True
    else:
        args.project = default_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deeprefine",
        description="DeepRefine: refine graphify-out/graph.json using query history",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # deeprefine cursor install | uninstall
    p_cursor = sub.add_parser("cursor", help="Cursor IDE integration")
    cursor_sub = p_cursor.add_subparsers(dest="cursor_cmd", required=True)

    p_ci = cursor_sub.add_parser("install", help="Install /deeprefine skill for Cursor")
    _add_project_flag(p_ci)
    p_ci.set_defaults(func=cmd_cursor_install, _default_project=True)

    p_cu = cursor_sub.add_parser("uninstall", help="Remove Cursor skill")
    _add_project_flag(p_cu)
    p_cu.set_defaults(func=cmd_cursor_uninstall, _default_project=True)

    # deeprefine install (alias)
    p_install = sub.add_parser(
        "install",
        help="Install Cursor skill (alias: deeprefine cursor install)",
    )
    _add_project_flag(p_install)
    p_install.set_defaults(func=cmd_install, _default_project=True)

    p_hist = sub.add_parser("history", help="Manage query history")
    hsub = p_hist.add_subparsers(dest="history_cmd", required=True)
    p_add = hsub.add_parser("add", help="Append a query to history")
    p_add.add_argument("--query", required=True)
    p_add.add_argument("--source", default="user")
    p_add.set_defaults(func=cmd_history_add)
    p_list = hsub.add_parser("list", help="List history entries")
    p_list.add_argument("--pending", action="store_true")
    p_list.set_defaults(func=cmd_history_list)

    p_index = sub.add_parser("index", help="Rebuild FAISS cache from graph.json")
    p_index.add_argument("--rebuild", action="store_true", default=True)
    p_index.set_defaults(func=cmd_index)

    p_refine = sub.add_parser("refine", help="Run refinement on pending or given query")
    p_refine.add_argument("--query", default=None, help="Single query (also recorded)")
    p_refine.add_argument("--project-root", default=None)
    p_refine.add_argument("--rebuild-index", action="store_true")
    p_refine.set_defaults(func=cmd_refine)

    args = parser.parse_args(argv)
    if hasattr(args, "_default_project"):
        _resolve_project(args, default_project=args._default_project)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
