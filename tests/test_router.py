from __future__ import annotations

import pytest

from app.router import RouterError

from support import FakeStreamResponse, err_response, make_engine, make_provider, ok_response

PAYLOAD = {"model": "auto", "messages": [{"role": "user", "content": "hola"}]}


def test_auto_uses_priority_order():
    p2 = make_provider("p2", priority=20)
    p1 = make_provider("p1", priority=10)
    engine, _, upstream = make_engine([p2, p1], [ok_response()])

    data, meta = _run(engine.complete(dict(PAYLOAD)))

    assert data["choices"][0]["message"]["content"] == "hola"
    assert meta.provider == "p1"
    assert upstream.calls[0]["provider"] == "p1"


def test_falls_back_after_rate_limit():
    p1 = make_provider("p1", priority=10)
    p2 = make_provider("p2", priority=20)
    engine, pool, _ = make_engine([p1, p2], [err_response(retry_after=30), ok_response()])

    _, meta = _run(engine.complete(dict(PAYLOAD)))

    assert meta.provider == "p2"
    assert len(meta.attempts) == 2
    assert meta.attempts[0].kind == "rate_limited"
    assert all(k.cooldown_until > 0 for k in pool.keys_for("p1"))


def test_all_rate_limited_returns_429_with_retry_after():
    p1 = make_provider("p1")
    engine, _, _ = make_engine([p1], [err_response(retry_after=30)])

    with pytest.raises(RouterError) as info:
        _run(engine.complete(dict(PAYLOAD)))

    assert info.value.status_code == 429
    assert info.value.code == "rate_limited"
    assert info.value.retry_after and info.value.retry_after > 0


def test_bad_request_is_not_retried():
    p1 = make_provider("p1")
    p2 = make_provider("p2", priority=20)
    engine, _, upstream = make_engine(
        [p1, p2], [err_response(kind="bad_request", status=400, error="messages inválidos")]
    )

    with pytest.raises(RouterError) as info:
        _run(engine.complete(dict(PAYLOAD)))

    assert info.value.status_code == 400
    assert len(upstream.calls) == 1


def test_model_not_found_retries_with_default_model():
    p1 = make_provider("p1", default_model="model-a")
    engine, _, upstream = make_engine(
        [p1],
        [err_response(kind="model_not_found", status=404, error="model not found"), ok_response(model="model-a")],
    )

    _, meta = _run(engine.complete({"model": "p1/modelo-inventado", "messages": PAYLOAD["messages"]}))

    assert meta.model == "model-a"
    assert [c["model"] for c in upstream.calls] == ["modelo-inventado", "model-a"]


def test_unknown_bare_model_uses_defaults_without_404_storm():
    """Un harness que fija "gpt-4" no debe gastar 8 intentos en 404."""
    p1 = make_provider("p1", priority=10)
    p2 = make_provider("p2", priority=20)
    engine, _, upstream = make_engine([p1, p2], [ok_response()])

    _, meta = _run(engine.complete({"model": "gpt-4-legacy", "messages": PAYLOAD["messages"]}))

    assert meta.provider == "p1"
    assert meta.model == "model-a"
    assert len(upstream.calls) == 1


def test_unsupported_parameter_retries_sanitized():
    p1 = make_provider("p1")
    engine, _, upstream = make_engine(
        [p1],
        [err_response(kind="unsupported_param", status=400, error="unknown parameter: tools"), ok_response()],
    )
    payload = {
        "model": "model-a",
        "messages": PAYLOAD["messages"],
        "tools": [{"type": "function", "function": {"name": "x", "parameters": {}}}],
        "tool_choice": "auto",
        "temperature": 0.2,
    }

    data, meta = _run(engine.complete(payload))

    assert data["choices"][0]["message"]["content"] == "hola"
    assert "tools" in upstream.calls[0]["payload"]
    assert "tools" not in upstream.calls[1]["payload"]
    assert "tool_choice" not in upstream.calls[1]["payload"]
    assert upstream.calls[1]["payload"]["temperature"] == 0.2
    assert meta.attempts[-1].kind == "ok"


def test_namespaced_model_forces_provider():
    p1 = make_provider("p1", models=("model-a",))
    p2 = make_provider("p2", priority=20, models=("model-b",))
    engine, _, upstream = make_engine([p1, p2], [ok_response(model="model-b")])

    _, meta = _run(engine.complete({"model": "p2/model-b", "messages": PAYLOAD["messages"]}))

    assert meta.provider == "p2"
    assert upstream.calls[0]["model"] == "model-b"


def test_model_match_across_providers():
    p1 = make_provider("p1", models=("model-a",))
    p2 = make_provider("p2", priority=20, models=("model-b", "model-c"))
    engine, _, upstream = make_engine([p1, p2], [ok_response(model="model-c")])

    _, meta = _run(engine.complete({"model": "model-c", "messages": PAYLOAD["messages"]}))

    assert meta.provider == "p2"
    assert upstream.calls[0]["model"] == "model-c"


def test_no_keys_returns_503():
    p1 = make_provider("p1", keys=())
    engine, _, _ = make_engine([p1], [])

    with pytest.raises(RouterError) as info:
        _run(engine.complete(dict(PAYLOAD)))

    assert info.value.status_code == 503
    assert info.value.code in {"no_keys", "provider_unavailable"}


def test_network_error_falls_back():
    p1 = make_provider("p1", priority=10)
    p2 = make_provider("p2", priority=20)
    engine, pool, _ = make_engine(
        [p1, p2],
        [err_response(kind="transient", status=0, error="timeout"), ok_response()],
    )

    _, meta = _run(engine.complete(dict(PAYLOAD)))

    assert meta.provider == "p2"
    key = pool.keys_for("p1")[0]
    assert key.last_error.startswith("timeout")


def test_stream_returns_handle_and_chunks():
    p1 = make_provider("p1")
    stream = FakeStreamResponse([b'data: {"choices":[]}\n\n', b"data: [DONE]\n\n"])
    engine, _, _ = make_engine([p1], streams=[stream])

    async def scenario():
        handle = await engine.open_stream({"model": "auto", "messages": PAYLOAD["messages"], "stream": True})
        assert handle.meta.provider == "p1"
        chunks = [chunk async for chunk in handle.chunks()]
        assert stream.closed is True
        return chunks

    chunks = _run(scenario())
    assert len(chunks) == 2


def test_stream_falls_back_before_starting():
    p1 = make_provider("p1", priority=10)
    p2 = make_provider("p2", priority=20)
    stream = FakeStreamResponse([b"data: ok\n\n"])
    engine, _, upstream = make_engine(
        [p1, p2],
        streams=[err_response(retry_after=20), stream],
    )

    async def scenario():
        handle = await engine.open_stream({"model": "auto", "messages": PAYLOAD["messages"], "stream": True})
        return handle.meta.provider

    assert _run(scenario()) == "p2"
    assert len(upstream.stream_calls) == 2


def _run(coro):
    import asyncio

    return asyncio.run(coro)
