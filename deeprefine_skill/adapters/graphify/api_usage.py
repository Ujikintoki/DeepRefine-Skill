"""Per-call API usage recording for CLI refine runs.

Stage 2's rounds (R0..R4-confirm) archived only refinement outputs — token
counts, latency and provider failures were never captured, so cost could not
be reported afterwards. This module gives the final-config reruns (r4f-*, seed
pinned per run) an observation layer: every underlying OpenAI-compatible HTTP
call is recorded with its usage block, wall time, and failure class, and the
records land in ``api_usage_<ts>.jsonl`` next to the refinement log.

Two properties matter for how this is wired:

- atlas_rag fans a single generate() out over a ThreadPoolExecutor, so
  appends are locked and each record carries the caller-set ``phase``
  (index-build / refine:<qid>) rather than relying on ordering.
- atlas_rag retries through tenacity around ``client.*.create``, so a retry
  surfaces here as one record per attempt: failures appear as error records
  with the exception class, successes as usage records. Nothing is swallowed.

Stdlib only, like relation_contract.py — importable without the upstream
stack, unit-testable with fake clients.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

_SUMMARY_KIND = "summary"


class ApiUsageRecorder:
    """Thread-safe, append-only record of API calls, tagged with a phase."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = []
        self.phase = "startup"

    @property
    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._records)

    def __len__(self) -> int:
        return len(self.records)

    def record(
        self,
        *,
        kind: str,
        model: str | None,
        elapsed_s: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "ts": round(time.time(), 3),
            "phase": self.phase,
            "kind": kind,
            "model": model,
            "elapsed_s": round(elapsed_s, 3),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "error": error,
        }
        with self._lock:
            self._records.append(rec)
        return rec

    def totals(self) -> dict[str, Any]:
        """Aggregate over records: call/error counts, wall time, token sums."""
        recs = self.records
        by_kind: dict[str, dict[str, Any]] = {}
        for rec in recs:
            bucket = by_kind.setdefault(
                rec["kind"],
                {"calls": 0, "errors": 0, "elapsed_s": 0.0, "prompt_tokens": 0,
                 "completion_tokens": 0, "total_tokens": 0},
            )
            bucket["calls"] += 1
            if rec["error"]:
                bucket["errors"] += 1
            bucket["elapsed_s"] = round(bucket["elapsed_s"] + (rec["elapsed_s"] or 0.0), 3)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if rec[key]:
                    bucket[key] += rec[key]
        errors = sum(1 for rec in recs if rec["error"])
        elapsed = round(sum(rec["elapsed_s"] or 0.0 for rec in recs), 3)
        tokens = {
            key: sum(rec[key] or 0 for rec in recs)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        return {
            "calls": len(recs),
            "errors": errors,
            "elapsed_s": elapsed,
            "by_kind": by_kind,
            **tokens,
        }


def instrument_openai_client(client: Any, recorder: ApiUsageRecorder, kind: str) -> Any:
    """Wrap one OpenAI client's endpoint method in place.

    kind="llm" wraps ``chat.completions.create``; kind="embed" wraps
    ``embeddings.create``. Instance-attribute assignment shadows the bound
    method (verified against the OpenAI SDK's resource objects), so callers
    holding the same client — LLMGenerator, Qwen3Emb — go through the wrapper
    unchanged. Errors are recorded and re-raised: retry loops upstream keep
    their semantics.
    """
    if kind == "llm":
        inner = client.chat.completions.create
    elif kind == "embed":
        inner = client.embeddings.create
    else:
        raise ValueError(f"unknown client kind: {kind}")

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model")
        start = time.time()
        try:
            resp = inner(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - record then re-raise
            recorder.record(
                kind=kind, model=model, elapsed_s=time.time() - start,
                error=type(exc).__name__,
            )
            raise
        usage = getattr(resp, "usage", None)
        recorder.record(
            kind=kind, model=model, elapsed_s=time.time() - start,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
        )
        return resp

    if kind == "llm":
        client.chat.completions.create = wrapped
    else:
        client.embeddings.create = wrapped
    return client


def write_usage_log(recorder: ApiUsageRecorder, path: Path) -> dict[str, Any]:
    """Write one JSON line per call, then a summary line; return the totals."""
    totals = recorder.totals()
    lines = list(recorder.records)
    lines.append({"kind": _SUMMARY_KIND, "phase": recorder.phase, **totals})
    path.write_text(
        "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in lines),
        encoding="utf-8",
    )
    return totals
