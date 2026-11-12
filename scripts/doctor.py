#!/usr/bin/env python3
"""Diagnóstico del router: configuración, claves y prueba real de proveedores.

Uso:
    python scripts/doctor.py                 # estado local
    python scripts/doctor.py --ping           # prueba los proveedores con claves
    python scripts/doctor.py --ping --provider groq
    python scripts/doctor.py --models groq    # lista modelos que reporta el proveedor
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pool import KeyPool  # noqa: E402
from app.registry import Provider, load_registry  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.upstream import Upstream  # noqa: E402

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def paint(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{RESET}" if enabled else text


async def ping_provider(upstream: Upstream, provider: Provider, key) -> dict:
    payload = {
        "model": provider.default_model,
        "messages": [{"role": "user", "content": "Responde solo: ok"}],
        "max_tokens": 8,
        "stream": False,
    }
    began = time.perf_counter()
    result = await upstream.chat(provider, key.secret, payload)
    latency = int((time.perf_counter() - began) * 1000)
    reply = ""
    if result.ok and result.data:
        try:
            reply = (result.data["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError, TypeError):
            reply = ""
    return {
        "provider": provider.id,
        "ok": result.ok,
        "status": result.status,
        "kind": result.kind,
        "latency_ms": latency,
        "reply": reply[:60],
        "error": result.error,
        "retry_after": result.retry_after,
    }


async def fetch_models(upstream: Upstream, provider: Provider, key) -> list[str]:
    result = await upstream.list_models(provider, key)
    if not result.ok or not result.data:
        return []
    items = result.data.get("data") or result.data.get("models") or []
    ids: list[str] = []
    for item in items:
        if isinstance(item, dict):
            value = item.get("id") or item.get("name")
            if value:
                ids.append(str(value))
        elif isinstance(item, str):
            ids.append(item)
    return sorted(ids)


async def main_async(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    registry = load_registry(settings)
    pool = KeyPool(registry.providers, settings.state_path, settings.persist_keys)
    upstream = Upstream(settings)

    color = sys.stdout.isatty()
    print(paint(f"Free AI Router · diagnóstico ({settings.version})", DIM, color))
    print(f"config: {settings.config_path}")
    print(f"estado: {settings.state_path if settings.persist_keys else '(solo memoria)'}")
    if registry.load_error:
        print(paint(f"ERROR de configuración: {registry.load_error}", RED, color))
        return 1
    print()

    headers = f"{'proveedor':<14} {'prio':>4} {'claves':>6} {'listas':>6}  {'modelo por defecto':<44} estado"
    print(headers)
    print("-" * len(headers))

    ready = 0
    for provider in registry.ordered():
        keys = pool.keys_for(provider.id)
        available = sum(1 for k in keys if k.available(provider, time.time()))
        if provider.enabled and not provider.disabled_reason and available:
            ready += 1
            status = paint("listo", GREEN, color)
        elif provider.disabled_reason:
            status = paint(provider.disabled_reason[:40], YELLOW, color)
        elif not provider.enabled:
            status = paint("desactivado", DIM, color)
        elif not provider.requires_key:
            status = paint("sin clave requerida", DIM, color)
        else:
            status = paint("sin clave", YELLOW, color)
        print(
            f"{provider.id:<14} {provider.priority:>4} {len(keys):>6} {available:>6}  "
            f"{provider.default_model[:44]:<44} {status}"
        )

    print()
    print(f"{ready} proveedor(es) listo(s) para enrutar.")
    if ready == 0:
        print(paint("Añade claves en .env (ver .env.example) o con POST /admin/keys", YELLOW, color))

    exit_code = 0 if ready or not args.ping else 1

    if args.ping:
        print("\nPruebas reales:")
        targets = registry.routable()
        if args.provider:
            targets = [p for p in targets if p.id == args.provider]
            if not targets:
                print(paint(f"No hay proveedor '{args.provider}' con claves.", RED, color))
                return 1
        for provider in targets:
            for key in pool.keys_for(provider.id):
                if not key.available(provider, time.time()):
                    continue
                outcome = await ping_provider(upstream, provider, key)
                if outcome["ok"]:
                    print(
                        f"  {paint('OK  ', GREEN, color)} {provider.id:<12} "
                        f"{outcome['latency_ms']:>5} ms  {paint(outcome['reply'], DIM, color)}"
                    )
                    pool.mark_success(key)
                else:
                    print(
                        f"  {paint('FAIL', RED, color)} {provider.id:<12} "
                        f"HTTP {outcome['status']} · {outcome['kind']} · {outcome['error'][:90]}"
                    )
                    exit_code = 1
                if args.json:
                    print(json.dumps(outcome, ensure_ascii=False))

    if args.models:
        provider = registry.get(args.models)
        if provider is None:
            print(paint(f"Proveedor desconocido: {args.models}", RED, color))
            return 1
        keys = pool.keys_for(provider.id)
        if not keys:
            print(paint(f"'{provider.id}' no tiene claves.", YELLOW, color))
            return 1
        ids = await fetch_models(upstream, provider, keys[0])
        if not ids:
            print(paint("El proveedor no devolvió modelos (¿endpoint no soportado?).", YELLOW, color))
        for model_id in ids:
            print(" ", model_id)

    await upstream.aclose()
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico de Free AI Router")
    parser.add_argument("--ping", action="store_true", help="haz una petición real a cada proveedor con claves")
    parser.add_argument("--provider", help="limita la prueba a un proveedor")
    parser.add_argument("--models", help="lista los modelos que reporta un proveedor")
    parser.add_argument("--json", action="store_true", help="imprime también el resultado en JSON")
    args = parser.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
