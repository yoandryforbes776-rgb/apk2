"""Registro de proveedores: lee config/providers.json y descubre claves en el entorno."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .settings import Settings

_ENV_PLACEHOLDER = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


@dataclass(slots=True)
class KeyRef:
    secret: str
    label: str = "env"
    source: str = "env"


@dataclass
class Provider:
    id: str
    label: str
    base_url: str
    default_model: str
    models: list[str] = field(default_factory=list)
    priority: int = 100
    kind: str = "openai"
    chat_path: str = "/chat/completions"
    embeddings_path: str = "/embeddings"
    models_path: str = "/models"
    keys: list[KeyRef] = field(default_factory=list)
    rpm: int = 0
    rpd: int = 0
    tpm: int = 0
    tpd: int = 0
    cooldown_seconds: float = 60.0
    quota_cooldown_seconds: float = 21600.0
    timeout_seconds: float = 90.0
    requires_key: bool = True
    supports_streaming: bool = True
    supports_embeddings: bool = False
    embedding_model: str = ""
    embedding_models: list[str] = field(default_factory=list)
    enabled: bool = True
    disabled_reason: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict = field(default_factory=dict)
    signup_url: str = ""
    docs_url: str = ""
    notes: str = ""

    @property
    def has_keys(self) -> bool:
        return bool(self.keys) or not self.requires_key

    def all_models(self) -> list[str]:
        models = list(self.models)
        if self.default_model and self.default_model not in models:
            models.insert(0, self.default_model)
        return models

    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.chat_path.lstrip("/")

    def embeddings_url(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.embeddings_path.lstrip("/")

    def models_url(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.models_path.lstrip("/")


def _expand_env(text: str) -> str:
    """Sustituye {VAR} y ${VAR} por su valor de entorno ('' si no existe)."""
    text = _ENV_PLACEHOLDER.sub(lambda m: os.getenv(m.group(1), ""), text or "")
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", lambda m: os.getenv(m.group(1), ""), text)


def collect_env_keys(prefixes: str | list[str] | None) -> list[KeyRef]:
    """Busca claves en variables tipo PREFIX, PREFIX_2, PREFIX_3, PREFIX_4..."""
    if not prefixes:
        return []
    if isinstance(prefixes, str):
        prefixes = [prefixes]

    refs: list[KeyRef] = []
    seen: set[str] = set()
    for prefix in prefixes:
        prefix = str(prefix).strip()
        if not prefix:
            continue
        for name in sorted(os.environ):
            if not (name == prefix or name.startswith(prefix + "_")):
                continue
            suffix = name[len(prefix):].lstrip("_")
            if suffix and not suffix.isdigit():
                continue
            raw = os.getenv(name, "")
            for part in raw.split(","):
                secret = part.strip().strip("\"'")
                if not secret or secret in seen:
                    continue
                seen.add(secret)
                refs.append(KeyRef(secret=secret, label=name, source="env"))
    return refs


@dataclass
class Registry:
    providers: dict[str, Provider]
    updated: str = ""
    version: int = 1
    source_path: Path | None = None
    load_error: str = ""

    def ordered(self) -> list[Provider]:
        return sorted(self.providers.values(), key=lambda p: (p.priority, p.id))

    def enabled(self) -> list[Provider]:
        return [p for p in self.ordered() if p.enabled and not p.disabled_reason]

    def routable(self) -> list[Provider]:
        return [p for p in self.enabled() if p.has_keys]

    def get(self, provider_id: str) -> Provider | None:
        return self.providers.get((provider_id or "").strip().lower())


def load_registry(settings: Settings | None = None, path: Path | None = None) -> Registry:
    settings = settings or Settings.from_env()
    config_path = Path(path or settings.config_path)

    if not config_path.exists():
        return Registry(providers={}, source_path=config_path, load_error=f"No existe {config_path}")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Registry(providers={}, source_path=config_path, load_error=f"JSON inválido: {exc}")

    defaults = raw.get("defaults") or {}
    default_timeout = float(defaults.get("providerTimeoutSeconds", settings.provider_timeout))

    providers: dict[str, Provider] = {}
    for item in raw.get("providers", []):
        try:
            provider_id = str(item["id"]).strip().lower()
        except KeyError:
            continue

        base_url = _expand_env(str(item.get("baseUrl", ""))).strip()
        headers = {str(k): _expand_env(str(v)) for k, v in (item.get("headers") or {}).items()}
        headers = {k: v for k, v in headers.items() if v}

        keys = collect_env_keys(item.get("keyEnvPrefix"))

        provider = Provider(
            id=provider_id,
            label=str(item.get("label") or provider_id),
            kind=str(item.get("kind") or "openai"),
            base_url=base_url,
            default_model=str(item.get("defaultModel") or ""),
            models=[str(m) for m in (item.get("models") or [])],
            priority=int(item.get("priority", 100)),
            chat_path=str(item.get("chatPath") or "/chat/completions"),
            embeddings_path=str(item.get("embeddingsPath") or "/embeddings"),
            models_path=str(item.get("modelsPath") or "/models"),
            keys=keys,
            rpm=int(item.get("rpm") or 0),
            rpd=int(item.get("rpd") or 0),
            tpm=int(item.get("tpm") or 0),
            tpd=int(item.get("tpd") or 0),
            cooldown_seconds=float(item.get("cooldownSeconds", 60)),
            quota_cooldown_seconds=float(item.get("quotaCooldownSeconds", 21600)),
            timeout_seconds=float(item.get("timeoutSeconds", default_timeout)),
            requires_key=bool(item.get("requiresKey", True)),
            supports_streaming=bool(item.get("supportsStreaming", True)),
            supports_embeddings=bool(item.get("supportsEmbeddings", False)),
            embedding_model=str(item.get("embeddingModel") or ""),
            embedding_models=[str(m) for m in (item.get("embeddingModels") or [])],
            enabled=bool(item.get("enabled", True)),
            headers=headers,
            extra_body=dict(item.get("extraBody") or {}),
            signup_url=str(item.get("signupUrl") or ""),
            docs_url=str(item.get("docsUrl") or ""),
            notes=str(item.get("notes") or ""),
        )

        # Base URL con placeholders sin resolver (p. ej. cuenta de Cloudflare).
        if "{" in provider.base_url:
            missing = sorted(set(_ENV_PLACEHOLDER.findall(provider.base_url)))
            provider.enabled = False
            provider.disabled_reason = "Falta configurar: " + ", ".join(missing)
        elif not provider.base_url:
            provider.enabled = False
            provider.disabled_reason = "baseUrl vacía"

        providers[provider_id] = provider

    return Registry(
        providers=providers,
        updated=str(raw.get("updated") or ""),
        version=int(raw.get("version") or 1),
        source_path=config_path,
    )
