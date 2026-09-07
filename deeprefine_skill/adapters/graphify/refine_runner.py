from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from atlas_rag.llm_generator import GenerationConfig, LLMGenerator
from atlas_rag.vectorstore.embedding_model import Qwen3Emb
import autorefiner.src.deeprefine as upstream_deeprefine
from autorefiner.src.deeprefine import DeepRefine, RetrievalStepResult

from deeprefine_skill.adapters.graphify.adapter import (
    load_or_build_data,
    save_bundle,
    save_graphify_json,
    sync_kg_to_graphify,
)
from deeprefine_skill.adapters.graphify.api_usage import (
    ApiUsageRecorder,
    instrument_openai_client,
    write_usage_log,
)
from deeprefine_skill.adapters.graphify.entity_fold import fold_refined_entities
from deeprefine_skill.adapters.graphify.parallel_links import (
    collect_parallel_links,
    reinject_parallel_links,
)
from deeprefine_skill.adapters.graphify.relation_contract import (
    apply_relation_contract,
    relation_labels_from_graph,
)
from deeprefine_skill.core.action_review import write_review_files
from deeprefine_skill.core.history import (
    append_history,
    mark_refined,
    pending_queries,
    query_id,
)
from deeprefine_skill.core.paths import checkpoints_metadata_path, create_checkpoint


def refinement_to_jsonable(
    sample: dict[str, Any],
    final_answer: Any,
    refinement_result: Any,
) -> dict[str, Any]:
    base = {"sample": sample, "final_answer": final_answer}
    if refinement_result is None:
        base["refinement_result"] = None
        return base

    hist = []
    for step in refinement_result.interaction_history:
        if isinstance(step, RetrievalStepResult):
            hist.append(
                {
                    "num_hops": step.num_hops,
                    "base_top_k": step.base_top_k,
                    "query": step.query,
                    "retrieved_subgraph": step.retrieved_subgraph,
                    "raw_response": step.raw_response,
                    "answerable": step.answerable,
                    "answer": step.answer,
                }
            )
        else:
            hist.append(str(step))

    base["refinement_result"] = {
        "query": refinement_result.query,
        "history_horizon_size": refinement_result.history_horizon_size,
        "interaction_history": hist,
        "error_abduction_reason": refinement_result.error_abduction_reason,
        "original_subgraph": refinement_result.original_subgraph,
        "refined_subgraph": refinement_result.refined_subgraph,
        "refinement_action_raw": refinement_result.refinement_action_raw,
        "refinement_action_count": len(refinement_result.refinement_action_list),
    }
    return base


def _build_openai_client(*, base_url: str, api_key: str) -> OpenAI:
    kwargs: dict[str, str] = {}
    if base_url:
        kwargs["base_url"] = base_url
    # For local compatible servers (e.g. vLLM) api_key can be empty.
    if api_key:
        kwargs["api_key"] = api_key
    elif base_url:
        kwargs["api_key"] = "EMPTY"
    # Upstream's GenerationConfig path sends no per-request timeout, so a dead
    # connection stalls on the SDK default (600s) and silently stretches an
    # unattended batch. 300s still leaves headroom for the largest 8k-token calls.
    return OpenAI(timeout=300.0, **kwargs)


def make_clients(
    cfg: dict[str, str],
    *,
    seed: int | None = None,
    recorder: ApiUsageRecorder | None = None,
) -> tuple[LLMGenerator, Qwen3Emb]:
    llm_client = _build_openai_client(
        base_url=cfg["DEEPREFINE_LLM_URL"],
        api_key=cfg["DEEPREFINE_LLM_API_KEY"],
    )
    embed_client = _build_openai_client(
        base_url=cfg["DEEPREFINE_EMBED_URL"],
        api_key=cfg["DEEPREFINE_EMBED_API_KEY"],
    )
    if recorder is not None:
        # Observation layer for the final-config reruns: usage/latency/failures
        # per HTTP call. Wrapping the client (not the generator) catches LLM
        # calls AND the embed calls upstream fires during refine (edge
        # embeddings), plus index builds. Recording never alters the request.
        instrument_openai_client(llm_client, recorder, kind="llm")
        instrument_openai_client(embed_client, recorder, kind="embed")
    gen_kwargs: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": False}}
    if seed is not None:
        # Final-config knob (2026-09-03): GenerationConfig.seed is forwarded
        # into every request (generation_config.py:132), so the provider-side
        # RNG is pinned per run instead of being silently server-chosen.
        # Historical rounds R0..R4-confirm ran without it.
        gen_kwargs["seed"] = seed
    llm = LLMGenerator(
        client=llm_client,
        model_name=cfg["DEEPREFINE_MODEL"],
        default_config=GenerationConfig(**gen_kwargs),
    )
    encoder = Qwen3Emb(
        embed_client,
        model_name=cfg["DEEPREFINE_EMBED_MODEL"],
    )
    return llm, encoder


def run_refine(
    *,
    graph_path: Path,
    cache_pkl: Path,
    history_path: Path,
    log_dir: Path,
    cfg: dict[str, str],
    queries: list[dict[str, Any]],
    rebuild_index: bool = False,
    retrieval_scope: str = "all",
    base_top_k: int = 5,
    max_hops: int = 4,
    apply: bool = False,
    fold_entities: bool = True,
    seed: int | None = None,
) -> dict[str, Any]:
    if not graph_path.is_file():
        raise FileNotFoundError(f"graphify graph not found: {graph_path}")

    recorder = ApiUsageRecorder()
    llm, encoder = make_clients(cfg, seed=seed, recorder=recorder)
    recorder.phase = "index-build"
    if retrieval_scope != "all":
        # Scoped corpora live in their own cache namespace: the mtime-based
        # validity check must never hand a scoped run the default bundle (or
        # vice versa), and _persist writes back through this same path.
        cache_pkl = cache_pkl.with_name(
            f"{cache_pkl.stem}-{retrieval_scope}{cache_pkl.suffix}"
        )
    raw, data = load_or_build_data(
        graph_path,
        cache_pkl,
        encoder,
        rebuild=rebuild_index,
        retrieval_scope=retrieval_scope,
    )
    original_kg = data["KG"].copy()

    # Stage 2 Round 4 (2026-09-03): relation-vocabulary contract. Upstream's
    # action prompt never constrains relation wording, so the same query
    # proposed `imports_from` in R3 (credited) and `depends_on` in the
    # identical-config confirm run (invisible — structeval only counts
    # import-family relations, matching the AST gold). graphify graphs have a
    # closed relation schema, so invented words are off-schema data; the
    # contract surfaces the loaded graph's own labels (extracted at run time,
    # nothing hardcoded — works for any domain). deeprefine.py from-imports
    # the constant into its own namespace (deeprefine.py:17), so the rebind
    # must land THERE — patching the defining module would not take effect.
    # Upstream files stay untouched on disk.
    contract_labels = relation_labels_from_graph(raw)
    upstream_deeprefine.REAFINER_KG_REFINEMENT_ACTION_SYSTEM_PROMPT = (
        apply_relation_contract(
            upstream_deeprefine.REAFINER_KG_REFINEMENT_ACTION_SYSTEM_PROMPT,
            contract_labels,
        )
    )
    print(
        "relation contract: on (Round 4 knob) — labels:",
        ", ".join(contract_labels) if contract_labels else "(none)",
    )
    if seed is not None:
        print(f"seed: {seed} (final-config knob — sent with every LLM request)")
    else:
        print("seed: not sent (historical behavior)")

    deeprefine = DeepRefine(
        data=data,
        sentence_encoder=encoder,
        llm_generator=llm,
        base_top_k=base_top_k,
        max_hops=max_hops,
        max_triple_num=20,
        max_triple_num_by_step=[5, 10, 15, 20],
        history_horizon_size=4,
        if_gen_answer=False,
        # Stage 2 Round 1 (2026-08-31): the per-hop judge over-claims
        # "answerable" on noise-dominated subgraphs, which silently skipped
        # abduction for queries whose answers are missing by construction.
        # Always run the abduction/action phase instead. Upstream still skips
        # when the FIRST hop is judged answerable (hardcoded).
        skip_action_if_answerable=False,
        # Stage 2 Round 3 (2026-09-02): the conflict guard keeps only the
        # first object per (subject, relation), and the kg persists across
        # queries in a batch — the R2 audit caught it swallowing 3 correct
        # inserts (sq-003's cli.py -> paths.py shadowed by sq-002; sq-006/007
        # shadowed by sq-005). Allow multiple objects per (subject, relation).
        skip_conflict_inserts=False,
    )

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"refinement_results_{int(time.time())}.jsonl"
    usage_path = log_path.with_name(log_path.name.replace("refinement_results_", "api_usage_"))
    refined_ids: set[str] = set()
    summary_rows: list[dict[str, Any]] = []
    completed = 0
    meta_path = checkpoints_metadata_path(graph_path.parent.parent)
    fold_report: dict[str, Any] | None = None
    usage_totals: dict[str, Any] = {}

    def _persist() -> None:
        if completed == 0:
            return
        if not apply:
            return
        data["KG"] = deeprefine.kg
        nonlocal raw, fold_report
        if fold_entities:
            # Upstream mints a fresh sha256 node for every LLM entity string
            # (its entity_to_id table is never seeded from the graph), so a
            # refinement batch leaves duplicate phantom nodes behind. Re-home
            # them onto baseline twins before writing. Dry-run returns above,
            # and in-batch upstream behavior stays untouched, so runs remain
            # R2-comparable.
            fold_report = fold_refined_entities(
                deeprefine.kg,
                {n["id"]: n.get("label") or n["id"] for n in raw.get("nodes", [])},
            )
            print(
                f"  fold: {len(fold_report['folded'])} folded, "
                f"{len(fold_report['residual'])} residual, "
                f"{fold_report['edges_remapped']} edges remapped, "
                f"{fold_report['edges_duplicated_dropped']} duplicates dropped"
            )
        # Baseline links that DiGraph's one-edge-per-pair rule would drop on
        # this roundtrip are stashed pre-sync and re-injected after it — the
        # paper's KB is a set of triples, so parallel (h,r,t) elements are
        # legal facts; sync must not lose them (see parallel_links.py).
        parallels = collect_parallel_links(raw)
        raw = sync_kg_to_graphify(raw, deeprefine.kg)
        parallel_report = reinject_parallel_links(raw, deeprefine.kg, parallels)
        if parallel_report["collected"]:
            print(
                f"  parallel links: {parallel_report['re_injected']} re-injected, "
                f"{parallel_report['already_present']} already present, "
                f"{parallel_report['pair_deleted']} pair deleted, "
                f"{parallel_report['endpoint_gone']} endpoint gone"
            )
        # Per-run pre-state backup: graph.json.bak.<next_seq> = graph exactly
        # as it was before this batch of refinements was written (the seq
        # matches the post-state checkpoint created below).
        from deeprefine_skill.core.paths import load_checkpoint_metadata, run_backup_path

        meta_now = load_checkpoint_metadata(meta_path)
        next_seq = (meta_now[-1]["seq"] if meta_now else 0) + 1
        run_backup = run_backup_path(graph_path.parent.parent, next_seq)
        save_graphify_json(graph_path, raw, backup_path=run_backup)
        save_bundle(cache_pkl, raw, data)
        mark_refined(history_path, refined_ids)
        # Post-state checkpoint: full graph after this batch of refinements.
        if refined_ids:
            latest_qid = sorted(refined_ids)[-1]
            create_checkpoint(graph_path, meta_path, latest_qid, "")

    try:
        with log_path.open("w", encoding="utf-8") as log_f:
            for sample in queries:
                query = sample["query"]
                qid = query_id(query, sample.get("id"))
                recorder.phase = f"refine:{qid}"
                print(f"\n=== [{qid}] {query}")
                try:
                    final_answer, _, refinement_result = deeprefine.refine(query=query)
                except Exception as exc:  # noqa: BLE001 - one bad query must not kill the batch
                    # Upstream raises on malformed LLM output (e.g. an empty
                    # action response after exhausted API retries). Record the
                    # failure, keep the query pending so a rerun retries it,
                    # and preserve dry-run KG isolation.
                    err = f"{type(exc).__name__}: {exc}"
                    print(f"  query error: {err}")
                    record = refinement_to_jsonable(sample, None, None)
                    record["error"] = err
                    log_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log_f.flush()
                    summary_rows.append(
                        {"id": qid, "query": query, "steps": 0, "action_count": 0, "error": err}
                    )
                    if not apply:
                        data["KG"] = original_kg.copy()
                        deeprefine.kg = data["KG"]
                    continue
                record = refinement_to_jsonable(sample, final_answer, refinement_result)
                log_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                log_f.flush()
                n_steps = (
                    len(refinement_result.interaction_history)
                    if refinement_result is not None
                    else 0
                )
                rr = record.get("refinement_result") or {}
                summary_rows.append(
                    {
                        "id": qid,
                        "query": query,
                        "steps": n_steps,
                        "action_count": rr.get("refinement_action_count", 0),
                    }
                )
                if apply:
                    refined_ids.add(qid)
                completed += 1
                action_file = None
                review_file = None
                review_count = 0
                if rr.get("refinement_action_raw"):
                    action_file = log_dir / f"proposed_refinement_actions_{qid}.txt"
                    review_file = log_dir / f"proposed_refinement_review_{qid}.md"
                    action_file.write_text(rr["refinement_action_raw"], encoding="utf-8")
                    reviews, _ = write_review_files(
                        graph_path=graph_path,
                        refinement_text=rr["refinement_action_raw"],
                        report_path=review_file,
                        json_path=log_dir / f"proposed_refinement_review_{qid}.json",
                    )
                    review_count = len(reviews)
                    summary_rows[-1]["action_file"] = str(action_file)
                    summary_rows[-1]["review_file"] = str(review_file)
                    summary_rows[-1]["mode"] = "apply" if apply else "dry-run"
                print(
                    f"  steps={n_steps}, nodes={deeprefine.kg.number_of_nodes()}, "
                    f"edges={deeprefine.kg.number_of_edges()}"
                )
                if action_file and review_file:
                    print(
                        f"  proposed_actions={review_count}, action_file={action_file}, "
                        f"review={review_file}"
                    )
                if not apply:
                    data["KG"] = original_kg.copy()
                    deeprefine.kg = data["KG"]
    finally:
        _persist()
        recorder.phase = "done"
        # Written even when a query raises, so a crashed batch still yields
        # its cost record.
        usage_totals = write_usage_log(recorder, usage_path)

    return {
        "log_path": str(log_path),
        "graph_path": str(graph_path),
        "nodes": deeprefine.kg.number_of_nodes(),
        "edges": deeprefine.kg.number_of_edges(),
        "queries_processed": len(queries),
        "mode": "apply" if apply else "dry-run",
        "fold": fold_report,
        "summary": summary_rows,
        "usage": usage_totals,
        "usage_log_path": str(usage_path),
    }


def refine_from_history(
    paths: dict[str, Path],
    cfg: dict[str, str],
    *,
    query: str | None = None,
    rebuild_index: bool = False,
    apply: bool = False,
    seed: int | None = None,
    retrieval_scope: str = "code",
) -> dict[str, Any]:
    if query:
        entry = append_history(paths["history"], query, source="deeprefine")
        queries = [entry]
    else:
        queries = pending_queries(paths["history"])
        if not queries:
            raise SystemExit(
                "No pending queries in history. Use:\n"
                "  deeprefine history add --query '...'\n"
                "  deeprefine refine --query '...'"
            )

    return run_refine(
        graph_path=paths["graph_json"],
        cache_pkl=paths["deeprefine_pkl"],
        history_path=paths["history"],
        log_dir=paths["graphify_out"] / ".deeprefine",
        cfg=cfg,
        queries=queries,
        rebuild_index=rebuild_index,
        apply=apply,
        seed=seed,
        # Stage 2 Round 2 (2026-09-01): retrieval corpus governance — the
        # ablation ladder builds cumulatively on Round 1's
        # skip_action_if_answerable=False above. Default stays "code" for
        # historical builds; wiki/KB sandboxes pass "all" (--retrieval-scope).
        retrieval_scope=retrieval_scope,
    )
