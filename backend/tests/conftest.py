import os

import pytest

os.environ.setdefault("PLATON_TESTING", "1")


@pytest.fixture(autouse=True)
def _clear_rate_limiters():
    from platon.main import (
        _ask_limiter,
        _dream_limiter,
        _invoke_limiter,
        _project_limiter,
        _steer_limiter,
    )

    for lim in (_ask_limiter, _invoke_limiter, _dream_limiter, _steer_limiter, _project_limiter):
        lim._buckets.clear()
    yield
    for lim in (_ask_limiter, _invoke_limiter, _dream_limiter, _steer_limiter, _project_limiter):
        lim._buckets.clear()


@pytest.fixture(autouse=True)
def _no_kernel_socket_table(monkeypatch):
    """Synthetic ASGI sockets keep secure defaults until a test opts in."""
    import platon.main as _m

    monkeypatch.setattr(_m, "_PROC_NET_TCP", ())
    monkeypatch.delenv("PLATON_LOCAL_UNVERIFIED", raising=False)
    monkeypatch.delenv("PLATON_LOCAL_RELAY", raising=False)


@pytest.fixture
def local_http_opt_in(monkeypatch):
    """Explicit operator choice for behavior tests using synthetic local TCP."""
    monkeypatch.setenv("PLATON_LOCAL_RELAY", "1")
    monkeypatch.setenv("PLATON_LOCAL_UNVERIFIED", "1")
