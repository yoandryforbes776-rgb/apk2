"""Pool de claves con rotación, cooldowns y contadores de cuota.

Reglas:
  * Cada clave tiene su propio estado (disponible, en espera, deshabilitada).
  * `pick()` devuelve la clave menos usada que respete rpm/rpd/tpd.
  * Un 429 pone la clave en cuarentena unos segundos/minutos.
  * Una clave inválida (401) se deshabilita hasta que el admin la reactive.
  * El estado puede persistirse en JSON para sobrevivir reinicios.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .registry import Provider
from .util import key_fingerprint, mask_secret, utc_day

log = logging.getLogger("router.pool")

MIN_COOLDOWN = 5.0


@dataclass
class KeyState:
    key_id: str
    provider_id: str
    secret: str
    label: str = "env"
    source: str = "env"
    disabled: bool = False
    disabled_reason: str = ""
    cooldown_until: float = 0.0
    day: str = ""
    uses_today: int = 0
    tokens_today: int = 0
    total_uses: int = 0
    total_errors: int = 0
    last_used: float = 0.0
    last_error: str = ""
    window: deque[float] = field(default_factory=deque, repr=False)

    @property
    def masked(self) -> str:
        return mask_secret(self.secret)

    def roll_day(self, now: float) -> None:
        today = utc_day(now)
        if self.day != today:
            self.day = today
            self.uses_today = 0
            self.tokens_today = 0

    def prune_window(self, now: float, window_seconds: float = 60.0) -> None:
        cutoff = now - window_seconds
        while self.window and self.window[0] < cutoff:
            self.window.popleft()

    def rpm_used(self, now: float) -> int:
        self.prune_window(now)
        return len(self.window)

    def cooling(self, now: float) -> bool:
        return self.cooldown_until > now

    def available(self, provider: Provider, now: float) -> bool:
        if self.disabled:
            return False
        self.roll_day(now)
        if self.cooling(now):
            return False
        if provider.rpm and self.rpm_used(now) >= provider.rpm:
            return False
        if provider.rpd and self.uses_today >= provider.rpd:
            return False
        if provider.tpd and self.tokens_today >= provider.tpd:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "provider_id": self.provider_id,
            "secret": self.secret,
            "label": self.label,
            "source": self.source,
            "disabled": self.disabled,
            "disabled_reason": self.disabled_reason,
            "cooldown_until": self.cooldown_until,
            "day": self.day,
            "uses_today": self.uses_today,
            "tokens_today": self.tokens_today,
            "total_uses": self.total_uses,
            "total_errors": self.total_errors,
            "last_used": self.last_used,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeyState":
        provider_id = str(data.get("provider_id", ""))
        secret = str(data.get("secret", ""))
        state = cls(
            key_id=str(data.get("key_id") or key_fingerprint(provider_id, secret)),
            provider_id=provider_id,
            secret=secret,
            label=str(data.get("label", "env")),
            source=str(data.get("source", "env")),
        )
        state.disabled = bool(data.get("disabled", False))
        state.disabled_reason = str(data.get("disabled_reason", ""))
        state.cooldown_until = float(data.get("cooldown_until", 0) or 0)
        state.day = str(data.get("day", ""))
        state.uses_today = int(data.get("uses_today", 0) or 0)
        state.tokens_today = int(data.get("tokens_today", 0) or 0)
        state.total_uses = int(data.get("total_uses", 0) or 0)
        state.total_errors = int(data.get("total_errors", 0) or 0)
        state.last_used = float(data.get("last_used", 0) or 0)
        state.last_error = str(data.get("last_error", ""))
        return state


class KeyPool:
    def __init__(
        self,
        providers: dict[str, Provider],
        state_path: Path | None = None,
        persist: bool = True,
    ) -> None:
        self.providers = providers
        self.state_path = Path(state_path) if state_path else None
        self.persist = bool(persist and self.state_path)
        self.keys: dict[str, KeyState] = {}
        self.provider_errors: dict[str, dict] = {}
        self._lock = threading.RLock()

        self._load_state()
        self.sync(providers)

    # ------------------------------------------------------------------ estado
    def _load_state(self) -> None:
        if not self.persist or not self.state_path or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("No se pudo leer el estado (%s): %s", self.state_path, exc)
            return

        for item in data.get("keys", []):
            try:
                state = KeyState.from_dict(item)
            except (TypeError, ValueError):
                continue
            if state.secret:
                self.keys[state.key_id] = state
        self.provider_errors = data.get("provider_errors", {}) or {}

    def save(self) -> None:
        if not self.persist or not self.state_path:
            return
        # No crear el archivo hasta que haya algo que guardar.
        if not self.keys and not self.provider_errors and not self.state_path.exists():
            return
        payload = {
            "version": 1,
            "saved_at": time.time(),
            "keys": [k.to_dict() for k in self.keys.values()],
            "provider_errors": self.provider_errors,
        }
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.state_path)
        except OSError as exc:
            log.warning("No se pudo guardar el estado: %s", exc)

    # ------------------------------------------------------------------ claves
    def sync(self, providers: dict[str, Provider]) -> None:
        """Añade claves nuevas del entorno y elimina las que ya no existen."""
        with self._lock:
            self.providers = providers
            env_ids: set[str] = set()
            for provider in providers.values():
                for ref in provider.keys:
                    key_id = key_fingerprint(provider.id, ref.secret)
                    env_ids.add(key_id)
                    existing = self.keys.get(key_id)
                    if existing is None:
                        self.keys[key_id] = KeyState(
                            key_id=key_id,
                            provider_id=provider.id,
                            secret=ref.secret,
                            label=ref.label,
                            source=ref.source,
                            day=utc_day(),
                        )
                    else:
                        existing.provider_id = provider.id
                        existing.label = ref.label
            for key_id, state in list(self.keys.items()):
                if state.source == "env" and key_id not in env_ids:
                    del self.keys[key_id]
            now = time.time()
            for state in self.keys.values():
                state.roll_day(now)
        self.save()

    def keys_for(self, provider_id: str) -> list[KeyState]:
        return [k for k in self.keys.values() if k.provider_id == provider_id]

    def add_key(self, provider_id: str, secret: str, label: str = "runtime") -> KeyState:
        provider_id = provider_id.strip().lower()
        if provider_id not in self.providers:
            raise KeyError(f"Proveedor desconocido: {provider_id}")
        secret = (secret or "").strip()
        if not secret:
            raise ValueError("La clave está vacía")
        key_id = key_fingerprint(provider_id, secret)
        with self._lock:
            state = self.keys.get(key_id)
            if state is None:
                state = KeyState(
                    key_id=key_id,
                    provider_id=provider_id,
                    secret=secret,
                    label=label or "runtime",
                    source="runtime",
                    day=utc_day(),
                )
                self.keys[key_id] = state
                log.info("Clave añadida para %s (%s)", provider_id, state.masked)
            else:
                state.disabled = False
                state.disabled_reason = ""
                state.cooldown_until = 0.0
        self.save()
        return state

    def remove_key(self, key_id: str) -> bool:
        with self._lock:
            state = self.keys.get(key_id)
            if state is None:
                return False
            if state.source == "env":
                # Las claves de entorno reaparecerían en el siguiente sync.
                state.disabled = True
                state.disabled_reason = "eliminada manualmente"
            else:
                del self.keys[key_id]
        self.save()
        return True

    def pick(self, provider_id: str, now: float | None = None, excludes: set[str] | None = None) -> KeyState | None:
        """Devuelve la clave más conveniente y registra el uso."""
        provider = self.providers.get(provider_id)
        if provider is None:
            return None
        now = now or time.time()
        excludes = excludes or set()
        with self._lock:
            candidates = [
                k
                for k in self.keys_for(provider_id)
                if k.key_id not in excludes and k.available(provider, now)
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda k: (k.last_used, k.uses_today))
            chosen = candidates[0]
            chosen.uses_today += 1
            chosen.total_uses += 1
            chosen.last_used = now
            chosen.window.append(now)
        self.save()
        return chosen

    def has_available(self, provider_id: str, now: float | None = None) -> bool:
        provider = self.providers.get(provider_id)
        if provider is None:
            return False
        now = now or time.time()
        return any(k.available(provider, now) for k in self.keys_for(provider_id))

    def available_at(self, provider_id: str, now: float | None = None) -> float:
        """Timestamp en el que el proveedor volverá a tener alguna clave libre."""
        now = now or time.time()
        provider = self.providers.get(provider_id)
        if provider is None:
            return now
        stamps: list[float] = []
        for key in self.keys_for(provider_id):
            if key.disabled:
                continue
            key.roll_day(now)
            moment = now
            if key.cooldown_until > now:
                moment = max(moment, key.cooldown_until)
            if provider.rpm and key.rpm_used(now) >= provider.rpm:
                moment = max(moment, now + 60)
            if provider.rpd and key.uses_today >= provider.rpd:
                moment = max(moment, now + 3600)
            if provider.tpd and key.tokens_today >= provider.tpd:
                moment = max(moment, now + 3600)
            stamps.append(moment)
        return min(stamps) if stamps else now

    # --------------------------------------------------------------- resultados
    def mark_success(self, key: KeyState, tokens: int = 0) -> None:
        with self._lock:
            now = time.time()
            key.roll_day(now)
            key.tokens_today += max(0, int(tokens or 0))
            key.last_error = ""
            key.cooldown_until = 0.0
            self.provider_errors.pop(key.provider_id, None)
        self.save()

    def mark_rate_limited(self, key: KeyState, seconds: float, reason: str = "límite alcanzado") -> None:
        cooldown = max(MIN_COOLDOWN, float(seconds or 0))
        with self._lock:
            key.total_errors += 1
            key.last_error = reason
            key.cooldown_until = max(key.cooldown_until, time.time() + cooldown)
            self.provider_errors[key.provider_id] = {
                "message": reason,
                "at": time.time(),
                "kind": "rate_limited",
            }
        log.info("Clave %s de %s en espera %.0fs (%s)", key.masked, key.provider_id, cooldown, reason)
        self.save()

    def mark_invalid(self, key: KeyState, reason: str = "clave inválida (401)") -> None:
        with self._lock:
            key.total_errors += 1
            key.last_error = reason
            key.disabled = True
            key.disabled_reason = reason
        log.warning("Clave %s de %s deshabilitada: %s", key.masked, key.provider_id, reason)
        self.save()

    def mark_error(self, key: KeyState, seconds: float, reason: str) -> None:
        cooldown = max(MIN_COOLDOWN, float(seconds or 0))
        with self._lock:
            key.total_errors += 1
            key.last_error = reason
            key.cooldown_until = max(key.cooldown_until, time.time() + cooldown)
            self.provider_errors[key.provider_id] = {
                "message": reason,
                "at": time.time(),
                "kind": "error",
            }
        self.save()

    def reset(self) -> None:
        """Reactiva todas las claves y limpia cooldowns (no borra contadores)."""
        with self._lock:
            for key in self.keys.values():
                key.disabled = False
                key.disabled_reason = ""
                key.cooldown_until = 0.0
                key.window.clear()
            self.provider_errors.clear()
        self.save()

    # ------------------------------------------------------------------ reporte
    def snapshot(self, now: float | None = None) -> dict:
        now = now or time.time()
        providers: list[dict] = []
        for provider in sorted(self.providers.values(), key=lambda p: (p.priority, p.id)):
            keys = self.keys_for(provider.id)
            rows = []
            for key in keys:
                key.roll_day(now)
                rows.append(
                    {
                        "key_id": key.key_id,
                        "label": key.label,
                        "source": key.source,
                        "masked": key.masked,
                        "available": key.available(provider, now),
                        "disabled": key.disabled,
                        "disabled_reason": key.disabled_reason,
                        "cooldown_until": key.cooldown_until,
                        "cooldown_seconds": max(0.0, round(key.cooldown_until - now, 1)),
                        "uses_today": key.uses_today,
                        "tokens_today": key.tokens_today,
                        "total_uses": key.total_uses,
                        "total_errors": key.total_errors,
                        "last_used": key.last_used,
                        "last_error": key.last_error,
                    }
                )
            providers.append(
                {
                    "id": provider.id,
                    "label": provider.label,
                    "priority": provider.priority,
                    "enabled": provider.enabled,
                    "disabled_reason": provider.disabled_reason,
                    "requires_key": provider.requires_key,
                    "default_model": provider.default_model,
                    "models": provider.all_models(),
                    "keys_total": len(keys),
                    "keys_available": sum(1 for r in rows if r["available"]),
                    "available_at": self.available_at(provider.id, now),
                    "last_error": (self.provider_errors.get(provider.id) or {}).get("message", ""),
                    "signup_url": provider.signup_url,
                    "docs_url": provider.docs_url,
                    "notes": provider.notes,
                    "keys": rows,
                }
            )
        return {"now": now, "providers": providers}
