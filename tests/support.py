"""Ayudas compartidas por los tests (proveedores falsos, upstream simulado)."""

from __future__ import annotations

from pathlib import Path

from app.pool import KeyPool
from app.registry import KeyRef, Provider, Registry
from app.router import RouterEngine
from app.settings import Settings
from app.upstream import UpstreamResult


def make_provider(
    provider_id: str = "p1",
    *,
    priority: int = 10,
    keys: tuple[str, ...] = ("k1",),
    default_model: str = "model-a",
    models: tuple[str, ...] = ("model-a",),
    rpm: int = 0,
    rpd: int = 0,
    **kwargs,
) -> Provider:
    return Provider(
        id=provider_id,
        label=provider_id,
        base_url=f"https://{provider_id}.example/v1",
        default_model=default_model,
        models=list(models),
        priority=priority,
        keys=[KeyRef(secret=k, label="test") for k in keys],
        rpm=rpm,
        rpd=rpd,
        **kwargs,
    )


def ok_response(content: str = "hola", model: str = "model-a", tokens: int = 12) -> UpstreamResult:
    return UpstreamResult(
        status=200,
        ok=True,
        kind="ok",
        data={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": tokens - 4, "total_tokens": tokens},
        },
    )


def err_response(
    kind: str = "rate_limited",
    status: int = 429,
    error: str = "rate limit",
    retry_after: float | None = None,
) -> UpstreamResult:
    return UpstreamResult(status=status, ok=False, kind=kind, error=error, retry_after=retry_after)


class FakeStreamResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.closed = False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class FakeUpstream:
    def __init__(self, results: list | None = None, streams: list | None = None) -> None:
        self.results = list(results or [])
        self.streams = list(streams or [])
        self.calls: list[dict] = []
        self.stream_calls: list[dict] = []

    async def chat(self, provider, secret, payload, path=None):
        self.calls.append(
            {"provider": provider.id, "secret": secret, "model": payload.get("model"), "payload": payload, "path": path}
        )
        if not self.results:
            raise AssertionError("FakeUpstream.chat sin resultados programados")
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def open_stream(self, provider, secret, payload, path=None):
        self.stream_calls.append(
            {"provider": provider.id, "secret": secret, "model": payload.get("model"), "payload": payload}
        )
        if not self.streams:
            raise AssertionError("FakeUpstream.open_stream sin resultados programados")
        item = self.streams.pop(0)
        if isinstance(item, UpstreamResult):
            return None, item
        return item, None

    async def aclose(self) -> None:
        return None


def make_engine(
    providers: list[Provider],
    results: list | None = None,
    *,
    streams: list | None = None,
    tmp_path: Path | None = None,
    **settings_kwargs,
) -> tuple[RouterEngine, KeyPool, FakeUpstream]:
    settings_kwargs.setdefault("max_attempts", 4)
    settings_kwargs.setdefault("request_timeout", 30)
    settings_kwargs.setdefault("persist_keys", False)
    if tmp_path is not None:
        settings_kwargs.setdefault("state_path", tmp_path / "state.json")
    settings = Settings(**settings_kwargs)
    registry = Registry(providers={p.id: p for p in providers})
    upstream = FakeUpstream(results=results, streams=streams)
    pool = KeyPool(registry.providers, settings.state_path if settings.persist_keys else None, settings.persist_keys)
    engine = RouterEngine(registry, pool, upstream, settings)
    return engine, pool, upstream
