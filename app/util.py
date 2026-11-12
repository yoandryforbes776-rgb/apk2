"""Utilidades pequeñas: tiempos, máscaras de secretos y normalización de modelos."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_DURATION_PART = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(ms|msec|milliseconds?|s|sec|secs|seconds?|m|min|mins|minutes?|h|hr|hrs|hours?|d|day|days)",
    re.IGNORECASE,
)

_UNIT_SECONDS = {
    "ms": 0.001,
    "msec": 0.001,
    "millisecond": 0.001,
    "milliseconds": 0.001,
    "s": 1.0,
    "sec": 1.0,
    "secs": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "m": 60.0,
    "min": 60.0,
    "mins": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "days": 86400.0,
}


def utc_day(now: float | None = None) -> str:
    """Día UTC en formato YYYY-MM-DD (para contadores diarios)."""
    return datetime.fromtimestamp(now or time.time(), tz=timezone.utc).strftime("%Y-%m-%d")


def seconds_until_utc_midnight(now: float | None = None) -> float:
    current = now or time.time()
    dt = datetime.fromtimestamp(current, tz=timezone.utc)
    tomorrow = dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
    return max(1.0, tomorrow - current)


def parse_retry_after(value: str | None) -> float | None:
    """Convierte 'Retry-After' / 'x-ratelimit-reset-requests' a segundos.

    Acepta: '30', '2.5', '2.5s', '1m30s', '1h', fechas HTTP.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    try:
        return max(0.0, float(raw))
    except ValueError:
        pass

    total = 0.0
    found = False
    for number, unit in _DURATION_PART.findall(raw):
        factor = _UNIT_SECONDS.get(unit.lower())
        if factor is None:
            continue
        total += float(number.replace(",", ".")) * factor
        found = True
    if found:
        return max(0.0, total)

    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, dt.timestamp() - time.time())
    except (TypeError, ValueError, OverflowError):
        return None


def key_fingerprint(provider_id: str, secret: str) -> str:
    """Identificador estable y no reversible de una clave."""
    digest = hashlib.sha256(f"{provider_id}\0{secret}".encode("utf-8")).hexdigest()
    return digest[:12]


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return secret[:2] + "***"
    return f"{secret[:4]}…{secret[-4:]}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_model_name(value: str) -> str:
    return (value or "").strip()


def model_equal(a: str, b: str) -> bool:
    """Compara ids de modelo ignorando mayúsculas y el prefijo de proveedor."""
    def norm(item: str) -> str:
        item = (item or "").strip().lower()
        return item.rsplit("/", 1)[-1]
    return norm(a) == norm(b)


def split_provider_model(value: str) -> tuple[str | None, str]:
    """'groq/llama-3.3-70b' -> ('groq', 'llama-3.3-70b')."""
    value = (value or "").strip()
    if "/" not in value:
        return None, value
    head, tail = value.split("/", 1)
    if not head or not tail:
        return None, value
    return head, tail
