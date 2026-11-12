from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.registry import Registry
from app.settings import Settings

from support import FakeStreamResponse, FakeUpstream, err_response, make_provider, ok_response


def build_client(upstream: FakeUpstream | None = None, **settings_kwargs) -> TestClient:
    provider = make_provider("p1", models=("model-a", "model-b"))
    settings_kwargs.setdefault("router_token", "secret")
    settings_kwargs.setdefault("admin_token", "admin-secret")
    settings_kwargs.setdefault("persist_keys", False)
    settings_kwargs.setdefault("allow_cors", False)
    settings = Settings(**settings_kwargs)
    registry = Registry(providers={"p1": provider})
    app = create_app(settings=settings, registry=registry, upstream=upstream or FakeUpstream([ok_response()]))
    return TestClient(app)


AUTH = {"Authorization": "Bearer secret"}


def test_health_is_public():
    client = build_client()
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["providers_ready"] == 1


def test_requires_token():
    client = build_client()
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/v1/models", headers=AUTH).status_code == 200


def test_models_lists_auto_and_namespaced():
    client = build_client()
    data = client.get("/v1/models", headers=AUTH).json()["data"]
    ids = {item["id"] for item in data}
    assert {"auto", "p1/model-a", "model-a", "p1/model-b", "model-b"} <= ids


def test_chat_completion_returns_metadata_headers():
    client = build_client()
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "auto", "messages": [{"role": "user", "content": "hola"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "hola"
    assert response.headers["x-router-provider"] == "p1"
    assert response.headers["x-router-model"] == "model-a"
    assert response.headers["x-router-attempts"] == "1"


def test_chat_streaming():
    stream = FakeStreamResponse([b'data: {"choices":[{"delta":{"content":"ho"}}]}\n\n', b"data: [DONE]\n\n"])
    upstream = FakeUpstream(streams=[stream])
    client = build_client(upstream)
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "auto", "messages": [{"role": "user", "content": "hola"}], "stream": True},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "ho" in response.text
    assert stream.closed is True


def test_invalid_messages_rejected():
    client = build_client()
    response = client.post("/v1/chat/completions", headers=AUTH, json={"model": "auto"})
    assert response.status_code == 400
    assert response.json()["error"]["message"]


def test_router_error_is_openai_shaped():
    client = build_client(FakeUpstream([err_response(retry_after=10)]))
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "auto", "messages": [{"role": "user", "content": "hola"}]},
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "10"
    body = response.json()["error"]
    assert body["code"] == "rate_limited"
    assert body["router"]["attempts"]


def test_admin_requires_token():
    client = build_client()
    assert client.get("/admin/status").status_code == 401
    assert client.get("/admin/status", headers={"X-Admin-Token": "admin-secret"}).status_code == 200


def test_admin_add_and_remove_key():
    client = build_client()
    headers = {"X-Admin-Token": "admin-secret"}
    added = client.post("/admin/keys", headers=headers, json={"provider": "p1", "key": "sk-runtime"})
    assert added.status_code == 200
    key_id = added.json()["key_id"]
    assert added.json()["source"] == "runtime"

    status = client.get("/admin/status", headers=headers).json()
    row = status["providers"][0]
    assert row["keys_total"] == 2

    removed = client.delete(f"/admin/keys/{key_id}", headers=headers)
    assert removed.status_code == 200
    assert client.delete(f"/admin/keys/{key_id}", headers=headers).status_code == 404


def test_admin_reset_reactivates_keys():
    client = build_client(FakeUpstream([err_response(kind="invalid_key", status=401, error="401")]))
    headers = {"X-Admin-Token": "admin-secret"}
    client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "auto", "messages": [{"role": "user", "content": "hola"}]},
    )
    assert client.post("/admin/reset", headers=headers).status_code == 200
    status = client.get("/admin/status", headers=headers).json()
    assert status["providers"][0]["keys_available"] == 1
