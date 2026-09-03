"""Tests for the per-call API usage recorder (final-config observation layer).

Fake-client tests only: the module must stay importable without the upstream
stack (same hygiene rule as relation_contract / entity_fold).
"""

import json
import threading

import pytest

from deeprefine_skill.adapters.graphify.api_usage import (
    ApiUsageRecorder,
    instrument_openai_client,
    write_usage_log,
)


class _FakeUsage:
    def __init__(self, prompt_tokens, completion_tokens, total_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _FakeResponse:
    def __init__(self, usage=None):
        self.usage = usage


class _Completions:
    def create(self, *args, **kwargs):
        raise AssertionError("not stubbed")


class _Chat:
    def __init__(self):
        self.completions = _Completions()


class _Embeddings:
    def create(self, *args, **kwargs):
        raise AssertionError("not stubbed")


class _FakeClient:
    def __init__(self):
        self.chat = _Chat()
        self.embeddings = _Embeddings()


def test_llm_calls_recorded_with_usage():
    recorder = ApiUsageRecorder()
    client = _FakeClient()
    client.chat.completions.create = lambda **kw: _FakeResponse(_FakeUsage(10, 5, 15))
    instrument_openai_client(client, recorder, kind="llm")

    resp = client.chat.completions.create(model="Qwen/Qwen3-32B", messages=[])
    assert isinstance(resp, _FakeResponse)
    assert len(recorder) == 1
    rec = recorder.records[0]
    assert rec["kind"] == "llm"
    assert rec["model"] == "Qwen/Qwen3-32B"
    assert rec["prompt_tokens"] == 10
    assert rec["completion_tokens"] == 5
    assert rec["total_tokens"] == 15
    assert rec["error"] is None
    assert rec["elapsed_s"] >= 0


def test_errors_recorded_then_reraised():
    recorder = ApiUsageRecorder()
    client = _FakeClient()

    def boom(**kw):
        raise RuntimeError("connection reset")

    client.chat.completions.create = boom
    instrument_openai_client(client, recorder, kind="llm")

    with pytest.raises(RuntimeError):
        client.chat.completions.create(model="m")
    assert len(recorder) == 1
    assert recorder.records[0]["error"] == "RuntimeError"
    assert recorder.records[0]["total_tokens"] is None


def test_embed_calls_recorded():
    recorder = ApiUsageRecorder()
    client = _FakeClient()
    client.embeddings.create = lambda **kw: _FakeResponse(_FakeUsage(40, 0, 40))
    instrument_openai_client(client, recorder, kind="embed")

    client.embeddings.create(model="Qwen/Qwen3-Embedding-8B", input=["a"])
    assert recorder.records[0]["kind"] == "embed"
    assert recorder.records[0]["prompt_tokens"] == 40


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        instrument_openai_client(_FakeClient(), ApiUsageRecorder(), kind="rerank")


def test_phase_tag_follows_caller():
    recorder = ApiUsageRecorder()
    recorder.phase = "index-build"
    recorder.record(kind="embed", model="e", elapsed_s=0.1)
    recorder.phase = "refine:sq-001"
    recorder.record(kind="llm", model="l", elapsed_s=0.2)
    assert [rec["phase"] for rec in recorder.records] == ["index-build", "refine:sq-001"]


def test_totals_aggregate_calls_errors_and_tokens():
    recorder = ApiUsageRecorder()
    recorder.record(kind="llm", model="m", elapsed_s=1.0,
                    prompt_tokens=10, completion_tokens=5, total_tokens=15)
    recorder.record(kind="llm", model="m", elapsed_s=2.0,
                    error="APITimeoutError")
    recorder.record(kind="embed", model="e", elapsed_s=0.5, prompt_tokens=40, total_tokens=40)

    totals = recorder.totals()
    assert totals["calls"] == 3
    assert totals["errors"] == 1
    assert totals["elapsed_s"] == 3.5
    assert totals["prompt_tokens"] == 50
    assert totals["total_tokens"] == 55
    assert totals["by_kind"]["llm"]["calls"] == 2
    assert totals["by_kind"]["llm"]["errors"] == 1
    assert totals["by_kind"]["embed"]["calls"] == 1


def test_concurrent_records_all_landed():
    recorder = ApiUsageRecorder()
    client = _FakeClient()
    client.chat.completions.create = lambda **kw: _FakeResponse(_FakeUsage(1, 1, 2))
    instrument_openai_client(client, recorder, kind="llm")

    def worker():
        for _ in range(50):
            client.chat.completions.create(model="m")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(recorder) == 400


def test_usage_log_written_with_summary_line(tmp_path):
    recorder = ApiUsageRecorder()
    recorder.phase = "refine:sq-000"
    recorder.record(kind="llm", model="m", elapsed_s=1.0,
                    prompt_tokens=10, completion_tokens=5, total_tokens=15)

    path = tmp_path / "api_usage_123.jsonl"
    totals = write_usage_log(recorder, path)

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert totals["calls"] == 1
    assert len(rows) == 2
    assert rows[0]["kind"] == "llm"
    assert rows[-1]["kind"] == "summary"
    assert rows[-1]["calls"] == 1
    assert rows[-1]["total_tokens"] == 15
