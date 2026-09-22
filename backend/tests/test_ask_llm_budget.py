"""platon.ask@v1: the same LLM function behind two doors with different guards.

`ask.answer()` reaches a real paid completion (`_deepseek_chat`). It is exposed twice:

    POST /api/ask                      -> _ask_limiter,    30/min per IP
    POST /ai-market/v2/invoke          -> _invoke_limiter, 120/min per IP

Neither door required payment, so the cheaper-guarded one set the real ceiling: 4x the
per-IP rate the operator chose for this function. And unlike the sibling LLM path
(`oracle.generate_witness`, which consults `_witness_llm_budget_available()` and degrades
to a template), `answer()` had no ALL-CALLERS budget at all — and a per-IP limit is the
wrong tool against a distributed caller, which is not hypothetical here: the operator's own
traffic analysis found a 72-address residential-proxy fleet.
"""

from __future__ import annotations

import asyncio

import pytest


def test_ask_has_a_global_all_callers_llm_budget():
    from platon import ask

    assert hasattr(ask, "_ask_llm_budget_available"), (
        "no global budget: a distributed caller is bounded by nothing"
    )


def test_over_the_global_budget_ask_degrades_to_the_deterministic_answer(monkeypatch):
    from platon import ask

    monkeypatch.setattr(ask.settings, "oracle_enabled", True, raising=False)
    monkeypatch.setattr(ask, "_ASK_LLM_PER_MIN", 2, raising=False)
    monkeypatch.setattr(ask, "_ask_calls", type(ask._ask_calls)(), raising=False)

    calls = {"n": 0}

    async def _counting(system, user):
        calls["n"] += 1
        return "an llm answer"

    monkeypatch.setattr(ask, "_deepseek_chat", _counting)

    # The live context is not what is under test, and building it needs a whole engine.
    monkeypatch.setattr(ask, "build_live_context", lambda _engine: "context")
    engine = object()
    sources = []
    for _ in range(5):
        out = asyncio.run(ask.answer("what is the state?", "en", engine))
        sources.append(out["source"])

    assert calls["n"] <= 2, f"the LLM was called {calls['n']} times against a budget of 2"
    assert "fallback" in sources, "over budget it must still answer, deterministically"


def test_the_budget_refills_over_its_window(monkeypatch):
    from platon import ask

    monkeypatch.setattr(ask, "_ASK_LLM_PER_MIN", 1, raising=False)
    monkeypatch.setattr(ask, "_ask_calls", type(ask._ask_calls)(), raising=False)
    assert ask._ask_llm_budget_available() is True
    assert ask._ask_llm_budget_available() is False
    ask._ask_calls.clear()
    assert ask._ask_llm_budget_available() is True


def test_the_invoke_door_uses_the_same_per_ip_rate_as_its_rest_twin():
    """Two doors on one function must not offer two different rates."""
    from platon import main

    assert "platon.ask@v1" in main._LLM_CAPABILITIES
    assert main._ask_limiter.limit <= main._invoke_limiter.limit
