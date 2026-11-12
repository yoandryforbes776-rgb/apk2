"""Configuración del servidor, leída de variables de entorno y de .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    """Carga un .env minimalista sin dependencias externas.

    No sobreescribe variables ya presentes en el entorno real.
    """
    if not path.exists():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        name, _, value = line.partition("=")
        name = name.strip()
        if not name or name in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        os.environ[name] = value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8080
    router_token: str = ""
    admin_token: str = ""
    config_path: Path = field(default_factory=lambda: ROOT / "config" / "providers.json")
    state_path: Path = field(default_factory=lambda: ROOT / "data" / "state.json")
    static_dir: Path = field(default_factory=lambda: ROOT / "app" / "static")
    persist_keys: bool = True
    allow_cors: bool = True
    allow_insecure_admin: bool = False
    max_attempts: int = 8
    provider_timeout: float = 90.0
    connect_timeout: float = 15.0
    request_timeout: float = 240.0
    log_level: str = "info"
    version: str = "1.0.0"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        load_env_file(env_file or (ROOT / ".env"))
        return cls(
            host=os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_env_int("PORT", 8080),
            router_token=os.getenv("ROUTER_TOKEN", "").strip(),
            admin_token=os.getenv("ADMIN_TOKEN", "").strip(),
            config_path=Path(os.getenv("CONFIG_PATH", str(ROOT / "config" / "providers.json"))),
            state_path=Path(os.getenv("STATE_PATH", str(ROOT / "data" / "state.json"))),
            static_dir=Path(os.getenv("STATIC_DIR", str(ROOT / "app" / "static"))),
            persist_keys=_env_bool("PERSIST_KEYS", True),
            allow_cors=_env_bool("ALLOW_CORS", True),
            allow_insecure_admin=_env_bool("ALLOW_INSECURE_ADMIN", False),
            max_attempts=_env_int("MAX_ATTEMPTS", 8),
            provider_timeout=_env_float("PROVIDER_TIMEOUT", 90.0),
            connect_timeout=_env_float("CONNECT_TIMEOUT", 15.0),
            request_timeout=_env_float("REQUEST_TIMEOUT", 240.0),
            log_level=os.getenv("LOG_LEVEL", "info").strip() or "info",
        )
