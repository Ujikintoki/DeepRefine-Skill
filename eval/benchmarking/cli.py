"""Standalone CLI for benchmark evaluation.

Usage:
    python eval/benchmarking/cli.py prepare --suite <suite-id> --output-dir <dir>
    python eval/benchmarking/cli.py evaluate --suite <dir> --baseline-graph <f> --candidate-graph <f> --output-dir <dir>
    python eval/benchmarking/cli.py report --result <f> --output <f>
    python eval/benchmarking/cli.py structeval --graph <f> --output-dir <dir>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

# Dual-mode entry point:
#   package mode (python -m eval.benchmarking.cli): relative imports resolve
#   script mode   (python eval/benchmarking/cli.py): no parent package, so
#     eval/ is put on sys.path and the bare ``benchmarking`` imports are used
if __name__ == "__main__":
    eval_root = Path(__file__).resolve().parent.parent
    if str(eval_root) not in sys.path:
        sys.path.insert(0, str(eval_root))

try:
    from .ast_gold import extract_gold, materialize_git_tree, resolve_commit
    from .evaluator import evaluate_suite
    from .prepare import SUPPORTED_SUITES, prepare_suite
    from .report import render_markdown
    from .structeval import (
        compare_runs,
        emit_queries,
        evaluate_structure,
        render_structural_report,
    )
except ImportError:  # script mode: no parent package context
    from benchmarking.ast_gold import extract_gold, materialize_git_tree, resolve_commit
    from benchmarking.evaluator import evaluate_suite
    from benchmarking.prepare import SUPPORTED_SUITES, prepare_suite
    from benchmarking.report import render_markdown
    from benchmarking.structeval import (
        compare_runs,
        emit_queries,
        evaluate_structure,
        render_structural_report,
    )


def _fail(exc: Exception) -> int:
    print(f"benchmark: {exc}", file=sys.stderr)
    return 2


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def cmd_benchmark_prepare(args: argparse.Namespace) -> int:
    """Prepare a deterministic suite from an official upstream data file."""

    try:
        profile = args.profile or (
            "smoke" if args.suite == "synthetic-smoke-v1" else "quick"
        )
        destination = prepare_suite(
            args.suite,
            profile,
            args.output_dir,
            source=args.source,
        )
    except (OSError, ValueError) as exc:
        return _fail(exc)
    print(f"Prepared benchmark suite: {destination}")
    print(f"Suite manifest: {destination / 'suite.json'}")
    return 0


def _metadata(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "graphify_version": args.graphify_version,
        "deeprefine_version": args.deeprefine_version,
        "model": args.model,
        "temperature": args.temperature,
        "prompt_config_hash": args.prompt_config_hash,
        "llm_calls": args.llm_calls,
        "input_tokens": args.input_tokens,
        "output_tokens": args.output_tokens,
    }


def cmd_benchmark_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a graph pair and write result.json plus report.md."""

    try:
        result = evaluate_suite(
            args.suite,
            args.baseline_graph,
            args.candidate_graph,
            baseline_predictions=args.baseline_predictions,
            candidate_predictions=args.candidate_predictions,
            baseline_wiki=args.baseline_wiki,
            candidate_wiki=args.candidate_wiki,
            semantic_model=args.semantic_model,
            metadata=_metadata(args),
        )
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        result_path = output_dir / "result.json"
        report_path = output_dir / "report.md"
        _write_json(result_path, result)
        report_path.write_text(render_markdown(result), encoding="utf-8")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return _fail(exc)
    print(f"Benchmark result: {result_path}")
    print(f"Markdown report: {report_path}")
    return 0


def cmd_benchmark_report(args: argparse.Namespace) -> int:
    """Merge one or more result JSON files into a Markdown report."""

    results: list[dict[str, Any]] = []
    try:
        for value in args.result:
            path = Path(value)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
                raise ValueError(f"Unsupported benchmark result: {path}")
            results.append(loaded)
        markdown = render_markdown(results)
        if args.output == "-":
            print(markdown, end="")
        else:
            output = Path(args.output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(markdown, encoding="utf-8")
            print(f"Markdown report: {output}")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return _fail(exc)
    return 0


def cmd_structeval(args: argparse.Namespace) -> int:
    """Evaluate a graph's import subgraph against mechanical AST gold."""

    temp_tree: Path | None = None
    try:
        repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()
        if args.source_tree:
            tree_root = Path(args.source_tree).resolve()
            tag = args.source_tag or ""
            commit = ""
        else:
            tag = args.source_tag or "v0.2.0"
            commit = resolve_commit(repo_root, tag)
            tree_root = materialize_git_tree(repo_root, tag)
            temp_tree = tree_root
        gold = extract_gold(tree_root, source_tag=tag, commit=commit)
        result = evaluate_structure(gold, args.graph)
        if args.baseline_result:
            baseline = json.loads(
                Path(args.baseline_result).read_text(encoding="utf-8")
            )
            result["transitions"] = compare_runs(baseline, result)
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        result_path = output_dir / "structeval_result.json"
        report_path = output_dir / "structural_report.md"
        _write_json(result_path, result)
        report_path.write_text(render_structural_report(result), encoding="utf-8")
        queries = 0
        if args.emit_queries:
            queries = emit_queries(result, args.emit_queries)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return _fail(exc)
    finally:
        if temp_tree is not None:
            shutil.rmtree(temp_tree, ignore_errors=True)
    print(f"Structeval result: {result_path}")
    print(f"Markdown report: {report_path}")
    if args.emit_queries:
        print(f"Refinement queries ({queries}): {args.emit_queries}")
    return 0


def _add_structeval_parser(subparsers: Any) -> None:
    """Register the structeval subcommand on a subparser collection."""

    parser = subparsers.add_parser(
        "structeval",
        help="Evaluate a graph's import subgraph against mechanical AST gold",
    )
    parser.add_argument(
        "--graph", required=True, help="Graphify graph.json to evaluate"
    )
    parser.add_argument(
        "--source-tag",
        default=None,
        help="Git ref to extract gold from (default: v0.2.0)",
    )
    parser.add_argument(
        "--source-tree",
        default=None,
        help="Explicit source tree directory (overrides --source-tag; no git needed)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Git repository used for tag extraction (default: current directory)",
    )
    parser.add_argument(
        "--baseline-result",
        default=None,
        help="Baseline structeval_result.json for the transition diff (Stage 2)",
    )
    parser.add_argument(
        "--emit-queries",
        default=None,
        help="Write JSONL refinement queries for missing gold edges to this path",
    )
    parser.add_argument("--output-dir", required=True)
    parser.set_defaults(func=cmd_structeval)


def register_benchmark_commands(subparsers: Any) -> None:
    """Register the benchmark command group on an argparse subparser action."""

    parser = subparsers.add_parser(
        "benchmark",
        help="Prepare and evaluate lightweight graph-quality benchmarks",
    )
    commands = parser.add_subparsers(dest="benchmark_cmd", required=True)

    prepare = commands.add_parser(
        "prepare",
        help="Prepare a deterministic suite from upstream data",
    )
    prepare.add_argument("--suite", required=True, choices=sorted(SUPPORTED_SUITES))
    prepare.add_argument(
        "--profile",
        default=None,
        choices=("smoke", "quick", "readme"),
        help="Default: smoke for synthetic, quick for real suites",
    )
    prepare.add_argument(
        "--source",
        default=None,
        help="Official upstream JSON file (not needed for synthetic-smoke-v1)",
    )
    prepare.add_argument("--output-dir", required=True)
    prepare.set_defaults(func=cmd_benchmark_prepare)

    evaluate = commands.add_parser(
        "evaluate",
        help="Compare baseline and candidate Graphify graph.json files",
    )
    evaluate.add_argument(
        "--suite",
        required=True,
        help="Prepared suite directory, suite.json, or built-in suite ID",
    )
    evaluate.add_argument("--baseline-graph", required=True)
    evaluate.add_argument("--candidate-graph", required=True)
    evaluate.add_argument("--baseline-predictions", default=None)
    evaluate.add_argument("--candidate-predictions", default=None)
    evaluate.add_argument(
        "--baseline-wiki",
        default=None,
        help="Optional baseline Wiki directory for local-link integrity checks",
    )
    evaluate.add_argument(
        "--candidate-wiki",
        default=None,
        help="Optional candidate Wiki directory for local-link integrity checks",
    )
    evaluate.add_argument(
        "--semantic-model",
        default=None,
        help="Opt in to G-BERTScore with this bert-score model (for example roberta-large)",
    )
    evaluate.add_argument("--output-dir", required=True)
    evaluate.add_argument("--graphify-version", default=None)
    evaluate.add_argument("--deeprefine-version", default=None)
    evaluate.add_argument("--model", default=None)
    evaluate.add_argument("--temperature", type=float, default=None)
    evaluate.add_argument("--prompt-config-hash", default=None)
    evaluate.add_argument("--llm-calls", type=int, default=0)
    evaluate.add_argument("--input-tokens", type=int, default=0)
    evaluate.add_argument("--output-tokens", type=int, default=0)
    evaluate.set_defaults(func=cmd_benchmark_evaluate)

    report = commands.add_parser(
        "report",
        help="Render one or more result.json files as Markdown",
    )
    report.add_argument("--result", action="append", required=True)
    report.add_argument("--format", choices=("markdown",), default="markdown")
    report.add_argument("--output", required=True, help="Output file or '-' for stdout")
    report.set_defaults(func=cmd_benchmark_report)

    _add_structeval_parser(commands)


def main(argv: list[str] | None = None) -> int:
    """Entry point for standalone CLI usage."""

    parser = argparse.ArgumentParser(
        prog="deeprefine-benchmark",
        description="Prepare and evaluate lightweight graph-quality benchmarks",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # prepare
    prepare = subparsers.add_parser(
        "prepare",
        help="Prepare a deterministic suite from upstream data",
    )
    prepare.add_argument("--suite", required=True, choices=sorted(SUPPORTED_SUITES))
    prepare.add_argument(
        "--profile",
        default=None,
        choices=("smoke", "quick", "readme"),
        help="Default: smoke for synthetic, quick for real suites",
    )
    prepare.add_argument(
        "--source",
        default=None,
        help="Official upstream JSON file (not needed for synthetic-smoke-v1)",
    )
    prepare.add_argument("--output-dir", required=True)
    prepare.set_defaults(func=cmd_benchmark_prepare)

    # evaluate
    evaluate = subparsers.add_parser(
        "evaluate",
        help="Compare baseline and candidate Graphify graph.json files",
    )
    evaluate.add_argument(
        "--suite",
        required=True,
        help="Prepared suite directory, suite.json, or built-in suite ID",
    )
    evaluate.add_argument("--baseline-graph", required=True)
    evaluate.add_argument("--candidate-graph", required=True)
    evaluate.add_argument("--baseline-predictions", default=None)
    evaluate.add_argument("--candidate-predictions", default=None)
    evaluate.add_argument(
        "--baseline-wiki",
        default=None,
        help="Optional baseline Wiki directory for local-link integrity checks",
    )
    evaluate.add_argument(
        "--candidate-wiki",
        default=None,
        help="Optional candidate Wiki directory for local-link integrity checks",
    )
    evaluate.add_argument(
        "--semantic-model",
        default=None,
        help="Opt in to G-BERTScore with this bert-score model (for example roberta-large)",
    )
    evaluate.add_argument("--output-dir", required=True)
    evaluate.add_argument("--graphify-version", default=None)
    evaluate.add_argument("--deeprefine-version", default=None)
    evaluate.add_argument("--model", default=None)
    evaluate.add_argument("--temperature", type=float, default=None)
    evaluate.add_argument("--prompt-config-hash", default=None)
    evaluate.add_argument("--llm-calls", type=int, default=0)
    evaluate.add_argument("--input-tokens", type=int, default=0)
    evaluate.add_argument("--output-tokens", type=int, default=0)
    evaluate.set_defaults(func=cmd_benchmark_evaluate)

    # report
    report = subparsers.add_parser(
        "report",
        help="Render one or more result.json files as Markdown",
    )
    report.add_argument("--result", action="append", required=True)
    report.add_argument("--format", choices=("markdown",), default="markdown")
    report.add_argument("--output", required=True, help="Output file or '-' for stdout")
    report.set_defaults(func=cmd_benchmark_report)

    _add_structeval_parser(subparsers)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
