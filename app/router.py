"""Motor de enrutado: elige proveedor + clave, reintenta y cae al siguiente."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

import httpx

from .pool import KeyPool, KeyState
from .registry import Provider, Registry
from .settings import Settings
from .upstream import Upstream, UpstreamResult
from .util import clamp, model_equal, split_provider_model

log = logging.getLogger("router.engine")

AUTO_MODELS = {"", "auto", "free", "free-auto", "router", "default", "any", "best"}

# Parámetros que algunos proveedores rechazan con 400; se reintenta sin ellos.
STRIP_ON_UNSUPPORTED = (
    "response_format",
    "tools",
    "tool_choice",
    "parallel_tool_calls",
    "logprobs",
    "top_logprobs",
    "n",
    "seed",
    "presence_penalty",
    "frequency_penalty",
    "logit_bias",
    "store",
    "metadata",
    "modalities",
    "audio",
    "prediction",
    "reasoning_effort",
    "verbosity",
    "stream_options",
    "stop",
    "user",
)


@dataclass
class Candidate:
    provider: Provider
    model: str


@dataclass
class AttemptRecord:
    provider: str
    model: str
    key_id: str = ""
    status: int = 0
    kind: str = ""
    detail: str = ""
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "key_id": self.key_id,
            "status": self.status,
            "kind": self.kind,
            "detail": self.detail,
            "latency_ms": self.latency_ms,
        }


@dataclass
class RouteMeta:
    provider: str
    model: str
    key_id: str
    latency_ms: int
    attempts: list[AttemptRecord] = field(default_factory=list)

    def headers(self) -> dict[str, str]:
        value = {
            "x-router-provider": self.provider,
            "x-router-model": self.model,
            "x-router-key": self.key_id,
            "x-router-attempts": str(len(self.attempts)),
            "x-router-latency-ms": str(self.latency_ms),
            "access-control-expose-headers": (
                "x-router-provider,x-router-model,x-router-key,"
                "x-router-attempts,x-router-latency-ms"
            ),
        }
        return value

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "key_id": self.key_id,
            "latency_ms": self.latency_ms,
            "attempts": [a.to_dict() for a in self.attempts],
        }


class RouterError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        code: str = "router_error",
        trace: list[AttemptRecord] | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.trace = trace or []
        self.retry_after = retry_after


@dataclass
class StreamHandle:
    response: httpx.Response
    meta: RouteMeta

    async def chunks(self):
        try:
            async for chunk in self.response.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await self.response.aclose()


class RouterEngine:
    def __init__(
        self,
        registry: Registry,
        pool: KeyPool,
        upstream: Upstream,
        settings: Settings,
    ) -> None:
        self.registry = registry
        self.pool = pool
        self.upstream = upstream
        self.settings = settings

    # ------------------------------------------------------------------ recarga
    def reload(self, registry: Registry) -> None:
        self.registry = registry
        self.pool.sync(registry.providers)

    # ------------------------------------------------------------- candidatos
    def _auto_candidates(self) -> list[Candidate]:
        out: list[Candidate] = []
        for provider in self.registry.routable():
            model = provider.default_model or (provider.models[0] if provider.models else "")
            if model:
                out.append(Candidate(provider, model))
        return out

    def candidates(self, requested: str) -> list[Candidate]:
        requested = (requested or "").strip()
        if requested.lower() in AUTO_MODELS:
            return self._auto_candidates()

        head, tail = split_provider_model(requested)
        provider = self.registry.get(head) if head else None
        if provider is not None:
            if not provider.enabled:
                return []
            model = tail or provider.default_model or (provider.models[0] if provider.models else "")
            return [Candidate(provider, model)] if model else []

        # Coincidencia por nombre de modelo en cualquier proveedor.
        matches: list[Candidate] = []
        for candidate_provider in self.registry.routable():
            for model in candidate_provider.all_models():
                if model.lower() == requested.lower() or model_equal(model, requested):
                    matches.append(Candidate(candidate_provider, model))
                    break
        if matches:
            return matches

        # Id desconocido (típico en harness que fijan "gpt-4" o similar).
        # En vez de gastar 8 intentos en 404, usamos los modelos por defecto.
        # Para forzar un modelo concreto usa "proveedor/modelo".
        return self._auto_candidates()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _prepare(payload: dict, candidate: Candidate, stream: bool) -> dict:
        body = {k: v for k, v in payload.items() if v is not None}
        for key, value in (candidate.provider.extra_body or {}).items():
            body.setdefault(key, value)
        body["model"] = candidate.model
        body["stream"] = stream
        if stream:
            body.setdefault("stream_options", {"include_usage": True})
        else:
            body.pop("stream_options", None)
        return body

    @staticmethod
    def _sanitize(payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k not in STRIP_ON_UNSUPPORTED}

    @staticmethod
    def _tokens(data: dict | None) -> int:
        if not isinstance(data, dict):
            return 0
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            return 0
        total = usage.get("total_tokens")
        if isinstance(total, (int, float)) and total > 0:
            return int(total)
        return int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)

    def _cooldown_for(self, provider: Provider, result: UpstreamResult) -> float:
        text = (result.error or "").lower()
        daily = any(
            token in text
            for token in ("per day", "daily", "day limit", "requests per day", "quota", "billing", "credit")
        )
        if result.kind == "quota":
            daily = True
        seconds = result.retry_after
        if seconds is None:
            seconds = provider.quota_cooldown_seconds if daily else provider.cooldown_seconds
        elif daily:
            seconds = max(seconds, provider.quota_cooldown_seconds)
        return clamp(float(seconds), 5.0, 86400.0)

    def _apply_failure(self, key: KeyState, provider: Provider, result: UpstreamResult) -> float:
        kind = result.kind
        if kind in ("rate_limited", "quota"):
            cooldown = self._cooldown_for(provider, result)
            self.pool.mark_rate_limited(key, cooldown, result.error or "límite del proveedor")
            return cooldown
        if kind in ("invalid_key", "forbidden"):
            self.pool.mark_invalid(key, result.error or f"acceso denegado ({result.status})")
            return 0.0
        if kind in ("model_not_found", "bad_request", "unsupported_param", "context_length"):
            # El problema es la petición, no la clave: no la penalizamos.
            return 0.0
        self.pool.mark_error(key, min(provider.cooldown_seconds, 120), result.error or "error del proveedor")
        return 0.0

    def _no_candidates_error(self, requested: str) -> RouterError:
        if not self.registry.providers:
            return RouterError(503, "No hay proveedores configurados. Revisa config/providers.json", "no_providers")
        routable = self.registry.routable()
        if not routable:
            return RouterError(
                503,
                "Ningún proveedor tiene claves. Añade claves en .env o con POST /admin/keys",
                "no_keys",
            )
        head, _ = split_provider_model(requested)
        if head and self.registry.get(head):
            return RouterError(503, f"El proveedor '{head}' no está disponible o no tiene claves", "provider_unavailable")
        return RouterError(503, f"No hay proveedor disponible para el modelo '{requested}'", "no_candidates")

    def _finish_error(self, trace: list[AttemptRecord]) -> RouterError:
        retry_after = None
        if not trace:
            stamps = [self.pool.available_at(p.id) for p in self.registry.routable()]
            if stamps:
                retry_after = float(math.ceil(clamp(min(stamps) - time.time(), 1.0, 3600.0)))
            return RouterError(
                429,
                "Todas las claves están en espera por límite de cuota. Inténtalo más tarde.",
                "rate_limited",
                [],
                retry_after,
            )
        kinds = {a.kind for a in trace}
        if kinds <= {"rate_limited", "quota"}:
            stamps = [
                self.pool.available_at(p.id)
                for p in self.registry.routable()
            ]
            if stamps:
                retry_after = float(math.ceil(clamp(min(stamps) - time.time(), 1.0, 3600.0)))
            return RouterError(
                429,
                "Todos los proveedores gratuitos están en límite ahora mismo. Inténtalo más tarde.",
                "rate_limited",
                trace,
                retry_after,
            )
        detail = next((a.detail for a in reversed(trace) if a.detail), "")
        return RouterError(
            502,
            "Todos los proveedores fallaron." + (f" Último error: {detail}" if detail else ""),
            "all_providers_failed",
            trace,
        )

    # -------------------------------------------------------------------- chat
    async def complete(self, payload: dict) -> tuple[dict, RouteMeta]:
        requested = str(payload.get("model") or "auto")
        candidates = self.candidates(requested)
        if not candidates:
            raise self._no_candidates_error(requested)

        trace: list[AttemptRecord] = []
        started = time.perf_counter()
        deadline = time.monotonic() + self.settings.request_timeout
        plan = list(candidates)
        seen_models: set[tuple[str, str]] = {(c.provider.id, c.model) for c in candidates}

        while plan and len(trace) < self.settings.max_attempts and time.monotonic() < deadline:
            candidate = plan.pop(0)
            provider = candidate.provider

            if not self.pool.has_available(provider.id):
                continue

            body = self._prepare(payload, candidate, stream=False)
            sanitized = False

            while len(trace) < self.settings.max_attempts and time.monotonic() < deadline:
                key = self.pool.pick(provider.id)
                if key is None:
                    break

                began = time.perf_counter()
                result = await self.upstream.chat(provider, key.secret, body)
                latency = int((time.perf_counter() - began) * 1000)

                if result.ok:
                    self.pool.mark_success(key, self._tokens(result.data))
                    data = result.data or {}
                    data.setdefault("model", candidate.model)
                    meta = RouteMeta(
                        provider=provider.id,
                        model=candidate.model,
                        key_id=key.key_id,
                        latency_ms=latency,
                        attempts=trace + [
                            AttemptRecord(
                                provider.id, candidate.model, key.key_id,
                                result.status, "ok", "", latency,
                            )
                        ],
                    )
                    return data, meta

                trace.append(
                    AttemptRecord(
                        provider.id, candidate.model, key.key_id,
                        result.status, result.kind, result.error, latency,
                    )
                )

                if result.kind == "unsupported_param" and not sanitized:
                    sanitized = True
                    body = self._sanitize(body)
                    continue

                self._apply_failure(key, provider, result)

                if result.kind in ("rate_limited", "quota", "invalid_key", "forbidden", "transient"):
                    # Puede quedar otra clave libre de este mismo proveedor.
                    continue

                if result.kind == "model_not_found":
                    fallback = provider.default_model
                    if fallback and (provider.id, fallback) not in seen_models:
                        seen_models.add((provider.id, fallback))
                        plan.append(Candidate(provider, fallback))
                    break

                if result.kind == "bad_request":
                    raise RouterError(
                        400,
                        f"El proveedor '{provider.id}' rechazó la solicitud: {result.error}",
                        "bad_request",
                        trace,
                    )

                break

        raise self._finish_error(trace)

    async def open_stream(self, payload: dict) -> StreamHandle:
        requested = str(payload.get("model") or "auto")
        candidates = self.candidates(requested)
        if not candidates:
            raise self._no_candidates_error(requested)

        trace: list[AttemptRecord] = []
        deadline = time.monotonic() + self.settings.request_timeout
        plan = list(candidates)
        seen_models: set[tuple[str, str]] = {(c.provider.id, c.model) for c in candidates}

        while plan and len(trace) < self.settings.max_attempts and time.monotonic() < deadline:
            candidate = plan.pop(0)
            provider = candidate.provider

            if not self.pool.has_available(provider.id):
                continue

            body = self._prepare(payload, candidate, stream=True)
            sanitized = False

            while len(trace) < self.settings.max_attempts and time.monotonic() < deadline:
                key = self.pool.pick(provider.id)
                if key is None:
                    break

                began = time.perf_counter()
                response, failure = await self.upstream.open_stream(provider, key.secret, body)
                latency = int((time.perf_counter() - began) * 1000)

                if response is not None:
                    self.pool.mark_success(key)
                    meta = RouteMeta(
                        provider=provider.id,
                        model=candidate.model,
                        key_id=key.key_id,
                        latency_ms=latency,
                        attempts=trace + [
                            AttemptRecord(
                                provider.id, candidate.model, key.key_id,
                                200, "ok", "", latency,
                            )
                        ],
                    )
                    return StreamHandle(response=response, meta=meta)

                assert failure is not None
                trace.append(
                    AttemptRecord(
                        provider.id, candidate.model, key.key_id,
                        failure.status, failure.kind, failure.error, latency,
                    )
                )

                if failure.kind == "unsupported_param" and not sanitized:
                    sanitized = True
                    body = self._sanitize(body)
                    continue

                self._apply_failure(key, provider, failure)

                if failure.kind in ("rate_limited", "quota", "invalid_key", "forbidden", "transient"):
                    # Puede quedar otra clave libre de este mismo proveedor.
                    continue

                if failure.kind == "model_not_found":
                    fallback = provider.default_model
                    if fallback and (provider.id, fallback) not in seen_models:
                        seen_models.add((provider.id, fallback))
                        plan.append(Candidate(provider, fallback))
                    break

                if failure.kind == "bad_request":
                    raise RouterError(
                        400,
                        f"El proveedor '{provider.id}' rechazó la solicitud: {failure.error}",
                        "bad_request",
                        trace,
                    )

                break

        raise self._finish_error(trace)

    # ---------------------------------------------------------------- embeddings
    async def embed(self, payload: dict) -> dict:
        requested = str(payload.get("model") or "auto")
        head, tail = split_provider_model(requested)
        providers = [p for p in self.registry.routable() if p.embedding_model]
        if head and self.registry.get(head):
            providers = [p for p in providers if p.id == head]
        if not providers:
            raise RouterError(
                503,
                "Ningún proveedor con claves soporta embeddings. Configura embeddingModel en providers.json.",
                "no_embeddings",
            )

        trace: list[AttemptRecord] = []
        deadline = time.monotonic() + self.settings.request_timeout
        for provider in providers:
            if len(trace) >= self.settings.max_attempts or time.monotonic() >= deadline:
                break
            if not self.pool.has_available(provider.id):
                continue
            model = tail if (head and provider.id == head and tail) else provider.embedding_model
            body = {k: v for k, v in payload.items() if v is not None}
            body["model"] = model
            while len(trace) < self.settings.max_attempts:
                key = self.pool.pick(provider.id)
                if key is None:
                    trace.append(AttemptRecord(provider.id, model, kind="no_key", detail="sin clave disponible"))
                    break
                began = time.perf_counter()
                result = await self.upstream.chat(
                    provider, key.secret, body, path=provider.embeddings_path
                )
                latency = int((time.perf_counter() - began) * 1000)
                if result.ok:
                    self.pool.mark_success(key, self._tokens(result.data))
                    data = result.data or {}
                    data.setdefault("model", model)
                    return data
                trace.append(
                    AttemptRecord(provider.id, model, key.key_id, result.status, result.kind, result.error, latency)
                )
                self._apply_failure(key, provider, result)
                if result.kind == "bad_request":
                    raise RouterError(
                        400,
                        f"El proveedor '{provider.id}' rechazó la solicitud: {result.error}",
                        "bad_request",
                        trace,
                    )
                break
        raise self._finish_error(trace)

    # ------------------------------------------------------------------ estado
    def status(self, include_keys: bool = False) -> dict:
        snapshot = self.pool.snapshot()
        providers = []
        for row in snapshot["providers"]:
            if not include_keys:
                row = {k: v for k, v in row.items() if k != "keys"}
            providers.append(row)
        return {
            "providers": providers,
            "attempts_budget": self.settings.max_attempts,
            "now": snapshot["now"],
        }
