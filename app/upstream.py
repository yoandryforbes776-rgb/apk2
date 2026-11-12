"""Llamadas HTTP a los proveedores y clasificación de errores."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from .registry import Provider
from .settings import Settings
from .util import parse_retry_after

log = logging.getLogger("router.upstream")

_KINDS_MODEL_NOT_FOUND = (
    "model_not_found",
    "model not found",
    "no such model",
    "unknown model",
    "does not exist",
    "invalid model",
    "model does not exist",
    "not a valid model",
)
_KINDS_UNSUPPORTED = (
    "unsupported",
    "not supported",
    "unrecognized",
    "unknown field",
    "unknown parameter",
    "extra inputs are not permitted",
    "invalid_request_error: unsupported",
)
_KINDS_CONTEXT = (
    "context length",
    "context_length",
    "maximum context",
    "too many tokens",
    "reduce the length",
    "prompt is too long",
)
_KINDS_QUOTA = (
    "insufficient_quota",
    "insufficient quota",
    "billing",
    "payment required",
    "credit",
    "quota exceeded",
    "exceeded your current quota",
    "out of credits",
)


@dataclass
class UpstreamResult:
    status: int = 0
    ok: bool = False
    kind: str = "ok"
    data: dict | None = None
    text: str = ""
    error: str = ""
    retry_after: float | None = None
    headers: dict[str, str] = field(default_factory=dict)


def _header(response: httpx.Response, name: str) -> str | None:
    return response.headers.get(name)


def classify(status: int, text: str, headers: dict[str, str]) -> tuple[str, float | None]:
    """Devuelve (tipo_de_fallo, retry_after_segundos)."""
    low = (text or "").lower()

    parsed: list[float] = []
    for name in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens", "x-ratelimit-reset"):
        value = parse_retry_after(headers.get(name))
        if value is not None:
            parsed.append(value)
    retry_after_ms = headers.get("retry-after-ms")
    if retry_after_ms:
        try:
            parsed.append(float(retry_after_ms) / 1000.0)
        except ValueError:
            pass
    retry_after = max(parsed) if parsed else None

    if 200 <= status < 300:
        return "ok", None

    if status == 429:
        return "rate_limited", retry_after
    if status == 402:
        return "quota", retry_after
    if status == 401:
        return "invalid_key", None
    if status == 403:
        if any(token in low for token in _KINDS_QUOTA):
            return "quota", retry_after
        if any(token in low for token in ("model", "permission", "not enabled", "region")):
            return "forbidden", retry_after
        return "forbidden", retry_after
    if status == 404:
        return "model_not_found", None
    if status in (400, 422):
        if any(token in low for token in _KINDS_MODEL_NOT_FOUND):
            return "model_not_found", None
        if any(token in low for token in _KINDS_CONTEXT):
            return "context_length", None
        if any(token in low for token in _KINDS_UNSUPPORTED):
            return "unsupported_param", None
        if any(token in low for token in _KINDS_QUOTA):
            return "quota", retry_after
        return "bad_request", None
    if status == 408:
        return "transient", retry_after
    if status >= 500:
        return "transient", retry_after
    return "bad_request", None


def _extract_error(text: str, data: dict | None) -> str:
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("msg") or error.get("detail")
            if message:
                return str(message)[:600]
        if isinstance(error, str) and error:
            return error[:600]
        for key in ("message", "detail", "msg"):
            if data.get(key):
                return str(data[key])[:600]
    cleaned = " ".join((text or "").split())
    return cleaned[:600]


class Upstream:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                limits=httpx.Limits(max_connections=60, max_keepalive_connections=20),
                timeout=httpx.Timeout(
                    connect=self.settings.connect_timeout,
                    read=self.settings.provider_timeout,
                    write=60.0,
                    pool=self.settings.connect_timeout,
                ),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ helpers
    def headers_for(self, provider: Provider, secret: str | None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "free-ai-router/1.0 (+android)",
        }
        headers.update(provider.headers)
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    def _timeout(self, provider: Provider, stream: bool = False) -> httpx.Timeout:
        read = provider.timeout_seconds if not stream else None
        return httpx.Timeout(
            connect=self.settings.connect_timeout,
            read=read,
            write=60.0,
            pool=self.settings.connect_timeout,
        )

    @staticmethod
    def _parse(response: httpx.Response) -> tuple[dict | None, str]:
        text = response.text
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError):
            return None, text
        return (data if isinstance(data, dict) else None), text

    # -------------------------------------------------------------------- calls
    async def chat(
        self,
        provider: Provider,
        secret: str,
        payload: dict,
        path: str | None = None,
    ) -> UpstreamResult:
        url = provider.base_url.rstrip("/") + "/" + (path or provider.chat_path).lstrip("/")
        try:
            response = await self.client.post(
                url,
                json=payload,
                headers=self.headers_for(provider, secret),
                timeout=self._timeout(provider),
            )
        except httpx.TimeoutException as exc:
            return UpstreamResult(kind="transient", error=f"Timeout con {provider.id}: {exc}")
        except httpx.HTTPError as exc:
            return UpstreamResult(kind="transient", error=f"Error de red con {provider.id}: {exc}")

        data, text = self._parse(response)
        headers = {k.lower(): v for k, v in response.headers.items()}
        kind, retry_after = classify(response.status_code, text, headers)
        return UpstreamResult(
            status=response.status_code,
            ok=kind == "ok",
            kind=kind,
            data=data,
            text=text,
            error="" if kind == "ok" else _extract_error(text, data),
            retry_after=retry_after,
            headers=headers,
        )

    async def open_stream(
        self,
        provider: Provider,
        secret: str,
        payload: dict,
        path: str | None = None,
    ) -> tuple[httpx.Response | None, UpstreamResult | None]:
        url = provider.base_url.rstrip("/") + "/" + (path or provider.chat_path).lstrip("/")
        request = self.client.build_request(
            "POST",
            url,
            json=payload,
            headers={**self.headers_for(provider, secret), "Accept": "text/event-stream"},
            timeout=self._timeout(provider, stream=True),
        )
        try:
            response = await self.client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            return None, UpstreamResult(kind="transient", error=f"Timeout con {provider.id}: {exc}")
        except httpx.HTTPError as exc:
            return None, UpstreamResult(kind="transient", error=f"Error de red con {provider.id}: {exc}")

        if response.status_code >= 400:
            try:
                body = (await response.aread()).decode("utf-8", "replace")
            finally:
                await response.aclose()
            headers = {k.lower(): v for k, v in response.headers.items()}
            kind, retry_after = classify(response.status_code, body, headers)
            data = None
            try:
                parsed = json.loads(body)
                data = parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, ValueError):
                pass
            return None, UpstreamResult(
                status=response.status_code,
                ok=False,
                kind=kind,
                data=data,
                text=body,
                error=_extract_error(body, data),
                retry_after=retry_after,
                headers=headers,
            )
        return response, None

    async def list_models(self, provider: Provider, secret: str) -> UpstreamResult:
        try:
            response = await self.client.get(
                provider.models_url(),
                headers=self.headers_for(provider, secret),
                timeout=httpx.Timeout(self.settings.connect_timeout, read=30.0),
            )
        except httpx.HTTPError as exc:
            return UpstreamResult(kind="transient", error=str(exc))
        data, text = self._parse(response)
        headers = {k.lower(): v for k, v in response.headers.items()}
        kind, retry_after = classify(response.status_code, text, headers)
        return UpstreamResult(
            status=response.status_code,
            ok=kind == "ok",
            kind=kind,
            data=data,
            text=text,
            error="" if kind == "ok" else _extract_error(text, data),
            retry_after=retry_after,
            headers=headers,
        )
