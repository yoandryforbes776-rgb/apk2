"""Endpoints HTTP: API compatible con OpenAI + administración."""

from __future__ import annotations

import hmac
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .registry import Provider
from .router import RouterEngine, RouterError
from .settings import Settings

router = APIRouter()

VALID_ROLES = {"system", "user", "assistant", "tool", "developer"}


# --------------------------------------------------------------------- helpers
def _engine(request: Request) -> RouterEngine:
    return request.app.state.engine


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _presented_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            return token
    for name in ("x-api-key", "x-router-token"):
        value = request.headers.get(name)
        if value:
            return value.strip()
    return None


def require_client(request: Request) -> None:
    """Protege /v1/* con ROUTER_TOKEN (si está configurado)."""
    expected = _settings(request).router_token
    if not expected:
        return
    presented = _presented_token(request)
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=401,
            detail="Token de cliente inválido. Envía 'Authorization: Bearer <ROUTER_TOKEN>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin(request: Request) -> None:
    settings = _settings(request)
    presented = request.headers.get("x-admin-token") or _presented_token(request)
    if settings.admin_token:
        if not presented or not hmac.compare_digest(presented, settings.admin_token):
            raise HTTPException(status_code=401, detail="Token de administración inválido.")
        return
    host = request.client.host if request.client else ""
    local = host in {"127.0.0.1", "::1", "localhost", "testclient"}
    if not local and not settings.allow_insecure_admin:
        raise HTTPException(
            status_code=403,
            detail="Configura ADMIN_TOKEN para usar /admin desde fuera de localhost.",
        )


def _validate_chat(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="El cuerpo debe ser un objeto JSON.")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(
            status_code=400,
            detail="'messages' es obligatorio y debe ser una lista con al menos un mensaje.",
        )
    for message in messages:
        if not isinstance(message, dict) or "role" not in message:
            raise HTTPException(status_code=400, detail="Cada mensaje necesita 'role' y 'content'.")
        if str(message["role"]) not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol no válido: {message['role']}")
    if "model" in payload and payload["model"] is not None and not isinstance(payload["model"], str):
        raise HTTPException(status_code=400, detail="'model' debe ser una cadena.")
    if isinstance(payload.get("stream"), str):
        payload["stream"] = payload["stream"].strip().lower() in {"1", "true", "yes", "si", "sí"}
    return payload


def _provider_public(provider: Provider) -> dict:
    return {
        "id": provider.id,
        "label": provider.label,
        "enabled": provider.enabled,
        "disabled_reason": provider.disabled_reason,
        "default_model": provider.default_model,
        "models": provider.all_models(),
        "priority": provider.priority,
        "requires_key": provider.requires_key,
        "has_keys": provider.has_keys,
        "rpm": provider.rpm,
        "rpd": provider.rpd,
        "tpm": provider.tpm,
        "tpd": provider.tpd,
        "signup_url": provider.signup_url,
        "docs_url": provider.docs_url,
        "notes": provider.notes,
    }


# ----------------------------------------------------------------------- salud
@router.get("/health")
async def health(request: Request) -> dict:
    registry = request.app.state.registry
    pool = request.app.state.pool
    settings = _settings(request)
    return {
        "status": "ok",
        "version": settings.version,
        "uptime_seconds": round(time.time() - getattr(request.app.state, "started_at", time.time()), 1),
        "providers_enabled": len(registry.enabled()),
        "providers_ready": len(registry.routable()),
        "keys": len(pool.keys),
        "load_error": registry.load_error,
    }


# ---------------------------------------------------------------------- modelos
def _model_entries(registry, include_all: bool = False) -> list[dict]:
    created = 1_700_000_000
    data: list[dict] = [
        {
            "id": "auto",
            "object": "model",
            "created": created,
            "owned_by": "router",
            "x_router": {"description": "Elige el mejor proveedor disponible y rota si falla"},
        }
    ]
    seen: set[str] = {"auto"}
    for provider in registry.ordered():
        if not provider.enabled or provider.disabled_reason:
            continue
        if not provider.has_keys and not include_all:
            continue
        for model in provider.all_models():
            meta = {"provider": provider.id, "model": model, "label": provider.label}
            qualified = f"{provider.id}/{model}"
            seen.add(qualified)
            data.append(
                {
                    "id": qualified,
                    "object": "model",
                    "created": created,
                    "owned_by": provider.id,
                    "x_router": meta,
                }
            )
            if model not in seen:
                seen.add(model)
                data.append(
                    {
                        "id": model,
                        "object": "model",
                        "created": created,
                        "owned_by": provider.id,
                        "x_router": meta,
                    }
                )
    return data


@router.get("/v1/models", dependencies=[Depends(require_client)])
async def list_models(request: Request, all: bool = False) -> dict:
    return {"object": "list", "data": _model_entries(request.app.state.registry, include_all=all)}


@router.get("/v1/models/{model_id:path}", dependencies=[Depends(require_client)])
async def get_model(request: Request, model_id: str) -> dict:
    """Algunos clientes consultan el modelo uno a uno."""
    wanted = model_id.strip()
    entries = _model_entries(request.app.state.registry, include_all=True)
    for entry in entries:
        if entry["id"] == wanted or entry["id"].lower() == wanted.lower():
            return entry
    # Id libre: el router lo acepta y cae al modelo por defecto del proveedor.
    return {
        "id": wanted,
        "object": "model",
        "created": 1_700_000_000,
        "owned_by": "router",
        "x_router": {"description": "Id libre: se usará el modelo por defecto del proveedor"},
    }


# ------------------------------------------------------------------ chat/complet
@router.post("/v1/chat/completions", dependencies=[Depends(require_client)])
async def chat_completions(request: Request):
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - JSON malformado
        raise HTTPException(status_code=400, detail="JSON inválido en el cuerpo de la petición.")
    payload = _validate_chat(payload)
    engine = _engine(request)

    if payload.get("stream"):
        handle = await engine.open_stream(payload)
        headers = {
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "x-accel-buffering": "no",
            **handle.meta.headers(),
        }
        return StreamingResponse(handle.chunks(), media_type="text/event-stream", headers=headers)

    data, meta = await engine.complete(payload)
    return JSONResponse(content=data, headers=meta.headers())


# ------------------------------------------------------- completions (formato viejo)
@router.post("/v1/completions", dependencies=[Depends(require_client)])
async def completions(request: Request):
    """Compatibilidad con clientes que aún usan /v1/completions (texto plano).

    Se traduce a chat internamente, así que se beneficia de toda la rotación.
    """
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="JSON inválido en el cuerpo de la petición.")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="El cuerpo debe ser un objeto JSON.")

    prompt = payload.get("prompt")
    if prompt is None:
        raise HTTPException(status_code=400, detail="'prompt' es obligatorio.")
    if isinstance(prompt, list):
        prompt_text = "\n".join(str(item) for item in prompt)
    else:
        prompt_text = str(prompt)

    messages: list[dict] = []
    if payload.get("system"):
        messages.append({"role": "system", "content": str(payload["system"])})
    messages.append({"role": "user", "content": prompt_text})

    chat_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"prompt", "system", "echo", "best_of", "suffix", "stream", "logprobs"}
    }
    chat_payload["messages"] = messages

    data, meta = await _engine(request).complete(chat_payload)
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        text = ""
    usage = data.get("usage") or {}
    body = {
        "id": data.get("id") or "cmpl-router",
        "object": "text_completion",
        "created": int(time.time()),
        "model": meta.model,
        "choices": [{"text": text, "index": 0, "finish_reason": "stop", "logprobs": None}],
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        },
    }
    return JSONResponse(content=body, headers=meta.headers())


# -------------------------------------------------------------------- embeddings
@router.post("/v1/embeddings", dependencies=[Depends(require_client)])
async def embeddings(request: Request):
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="JSON inválido en el cuerpo de la petición.")
    if not isinstance(payload, dict) or not payload.get("input"):
        raise HTTPException(status_code=400, detail="'input' es obligatorio.")
    engine = _engine(request)
    return JSONResponse(content=await engine.embed(payload))


# ----------------------------------------------------------------------- estado
@router.get("/v1/router/status", dependencies=[Depends(require_client)])
async def router_status(request: Request) -> dict:
    return _engine(request).status(include_keys=False)


# ------------------------------------------------------------------------ admin
@router.get("/admin/status", dependencies=[Depends(require_admin)])
async def admin_status(request: Request) -> dict:
    engine = _engine(request)
    settings = _settings(request)
    registry = request.app.state.registry
    return {
        "version": settings.version,
        "config_path": str(settings.config_path),
        "state_path": str(settings.state_path) if settings.persist_keys else "(memoria)",
        "registry_updated": registry.updated,
        "load_error": registry.load_error,
        "router_token_required": bool(settings.router_token),
        "admin_token_required": bool(settings.admin_token),
        "max_attempts": settings.max_attempts,
        "started_at": getattr(request.app.state, "started_at", time.time()),
        **engine.status(include_keys=True),
    }


@router.get("/admin/providers", dependencies=[Depends(require_admin)])
async def admin_providers(request: Request) -> dict:
    registry = request.app.state.registry
    return {
        "updated": registry.updated,
        "load_error": registry.load_error,
        "providers": [_provider_public(p) for p in registry.ordered()],
    }


@router.post("/admin/keys", dependencies=[Depends(require_admin)])
async def admin_add_key(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="JSON inválido.")
    provider_id = str(body.get("provider") or "").strip().lower()
    secret = str(body.get("key") or "").strip()
    if not provider_id or not secret:
        raise HTTPException(status_code=400, detail="Se requieren 'provider' y 'key'.")
    pool = request.app.state.pool
    try:
        state = pool.add_key(provider_id, secret, str(body.get("label") or "runtime"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "provider": provider_id,
        "key_id": state.key_id,
        "masked": state.masked,
        "source": state.source,
    }


@router.delete("/admin/keys/{key_id}", dependencies=[Depends(require_admin)])
async def admin_remove_key(request: Request, key_id: str) -> dict:
    pool = request.app.state.pool
    if not pool.remove_key(key_id):
        raise HTTPException(status_code=404, detail="Clave no encontrada.")
    return {"ok": True, "key_id": key_id}


@router.post("/admin/reset", dependencies=[Depends(require_admin)])
async def admin_reset(request: Request) -> dict:
    pool = request.app.state.pool
    pool.reset()
    return {"ok": True, "message": "Cooldowns y claves deshabilitadas reiniciados."}


@router.post("/admin/reload", dependencies=[Depends(require_admin)])
async def admin_reload(request: Request) -> dict:
    from .registry import load_registry

    settings = _settings(request)
    registry = load_registry(settings)
    request.app.state.registry = registry
    _engine(request).reload(registry)
    return {
        "ok": True,
        "providers": len(registry.providers),
        "ready": len(registry.routable()),
        "load_error": registry.load_error,
    }


@router.post("/admin/test", dependencies=[Depends(require_admin)])
async def admin_test(request: Request) -> dict:
    """Prueba rápida de proveedores. body: {"provider": "groq"} o vacío para todos."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    if not isinstance(body, dict):
        body = {}
    engine = _engine(request)
    registry = request.app.state.registry
    pool = request.app.state.pool

    targets: list[Provider]
    if body.get("provider"):
        provider = registry.get(str(body["provider"]))
        if provider is None:
            raise HTTPException(status_code=404, detail="Proveedor desconocido.")
        targets = [provider]
    else:
        targets = [p for p in registry.routable()][:8]

    results: list[dict] = []
    for provider in targets:
        key = pool.pick(provider.id)
        if key is None:
            results.append({"provider": provider.id, "ok": False, "error": "sin clave disponible"})
            continue
        payload = {
            "model": body.get("model") or provider.default_model,
            "messages": [{"role": "user", "content": "Responde solo: ok"}],
            "max_tokens": 8,
            "stream": False,
        }
        began = time.perf_counter()
        outcome = await engine.upstream.chat(provider, key.secret, payload)
        latency = int((time.perf_counter() - began) * 1000)
        if outcome.ok:
            pool.mark_success(key, engine._tokens(outcome.data))  # noqa: SLF001
            content = ""
            try:
                content = outcome.data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                pass
            results.append(
                {
                    "provider": provider.id,
                    "ok": True,
                    "model": payload["model"],
                    "latency_ms": latency,
                    "reply": content[:120],
                }
            )
        else:
            engine._apply_failure(key, provider, outcome)  # noqa: SLF001
            results.append(
                {
                    "provider": provider.id,
                    "ok": False,
                    "model": payload["model"],
                    "status": outcome.status,
                    "kind": outcome.kind,
                    "error": outcome.error,
                    "latency_ms": latency,
                }
            )
    return {"ok": all(r["ok"] for r in results) if results else False, "results": results}
