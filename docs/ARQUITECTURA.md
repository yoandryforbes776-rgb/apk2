# Arquitectura interna

## Módulos

```
settings.py  →  .env + variables de entorno, rutas, límites globales
registry.py  →  lee config/providers.json, descubre claves en el entorno
pool.py      →  estado de cada clave: cooldown, rpm/rpd/tpd, persistencia
upstream.py  →  HTTP a proveedores y clasificación de respuestas
router.py    →  plan de candidatos, reintentos, streaming, embeddings
api.py       →  /v1 (cliente) y /admin (operación)
main.py      →  app FastAPI, CORS, manejadores de error, estáticos
```

## Flujo de una petición

```
POST /v1/chat/completions
   │
   ├─ require_client()            token del APK
   ├─ _validate_chat()            messages/roles/model
   ├─ candidates(modelo)          plan ordenado por prioridad
   │
   └─ bucle de intentos (≤ MAX_ATTEMPTS, ≤ REQUEST_TIMEOUT)
        │
        ├─ pool.pick(provider)   clave menos usada y disponible
        ├─ upstream.chat(...)    POST al proveedor
        │
        ├─ 200 → mark_success → respuesta + x-router-*
        ├─ 429 → mark_rate_limited(Retry-After) → siguiente
        ├─ 401 → mark_invalid → siguiente
        ├─ 404 modelo → añade candidato (provider, defaultModel)
        ├─ 400 "unknown parameter" → reintenta sin parámetros opcionales
        ├─ 400 genérico → corta y devuelve 400 (no gasta más cuotas)
        └─ 5xx/red → mark_error(≤120 s) → siguiente
```

### Selección de candidatos

```python
if modelo in {"", "auto", "free", ...}:
    [(p, p.defaultModel) for p in providers ordenados por priority]
elif "proveedor/modelo" y proveedor existe:
    [(proveedor, modelo)]
elif algún proveedor anuncia ese modelo:
    [(p, modelo) para cada coincidencia, ordenados]
else:
    [(p, modelo) para todos]   # passthrough; los 404 añaden defaultModel
```

Solo entran proveedores `enabled`, sin `disabled_reason` y **con al menos una
clave** (o `requiresKey=false`).

### Estado de una clave

```
        pick() ok                429 / 5xx
  ┌──────────────┐  ──────────►  ┌──────────────┐
  │  disponible  │               │  cooldown    │──► vuelve al expirar
  └──────┬───────┘  ◄──────────  └──────────────┘
         │ 401 / 403
         ▼
  ┌──────────────┐   POST /admin/reset
  │ deshabilitada│  ───────────────────►  disponible
  └──────────────┘
```

Un 400 de validación (`messages` mal, `context_length`…) **no** penaliza la
clave: el problema es la petición.

### Cálculo del cooldown

| Fuente | Valor |
|---|---|
| `Retry-After` / `x-ratelimit-reset-*` | se parsea (`2.5s`, `1m30s`, `1500ms`, fecha HTTP) y se usa el máximo |
| Sin cabecera, error normal | `cooldownSeconds` del proveedor |
| Error de cuota/billing/diario | `quotaCooldownSeconds` (mínimo el `Retry-After`) |
| Límites | mínimo 5 s, máximo 24 h |

`available_at()` calcula cuándo vuelve a haber capacidad teniendo en cuenta
cooldown, rpm (ventana de 60 s) y rpd/tpd (día UTC).

### Contadores

Cada clave mantiene `window` (timestamps de los últimos 60 s), `uses_today`,
`tokens_today` y `day`. Antes de usar una clave se hace *roll* del día UTC; los
límites `rpm/rpd/tpd` del proveedor bloquean proactivamente, así que normalmente
ni siquiera se llega al 429.

### Streaming

No se emite nada al cliente hasta que un proveedor responde `200`:

1. `upstream.open_stream()` → `client.send(request, stream=True)`.
2. Si falla, se lee el cuerpo del error, se cierra y se prueba el siguiente
   candidato (el cliente nunca ve el reintento).
3. Si va bien, se devuelve un `StreamHandle` y `StreamingResponse` copia los
   bytes SSE con `aiter_bytes()`; al terminar o al cancelar el cliente se cierra
   la respuesta upstream (`finally`).

Por eso los reintentos son invisibles también en streaming, y por eso el proxy
inverso debe desactivar el buffering.

## Persistencia (`data/state.json`)

```json
{
  "version": 1,
  "saved_at": 1794486717.0,
  "keys": [
    {
      "key_id": "0fed8044f40a",
      "provider_id": "groq",
      "secret": "gsk_…",
      "label": "GROQ_API_KEY",
      "source": "env",
      "disabled": false,
      "disabled_reason": "",
      "cooldown_until": 1794486800.0,
      "day": "2026-11-12",
      "uses_today": 42,
      "tokens_today": 51234,
      "total_uses": 1200,
      "total_errors": 7,
      "last_used": 1794486710.0,
      "last_error": ""
    }
  ],
  "provider_errors": { "groq": {"message": "Rate limit", "at": 1794486700.0, "kind": "rate_limited"} }
}
```

- Escritura atómica (`tmp` + `os.replace`) y permisos `600`.
- `key_id` = `sha256(provider + "\0" + secret)[:12]`: identifica sin revelar.
- Claves de `.env` se re-sincronizan en cada arranque; las `runtime` solo viven
  aquí. Con `PERSIST_KEYS=false` no se escribe nada (todo en memoria).
- Varias claves de `.env` con el mismo secreto se deduplican.

## Por qué un solo worker

El estado es en memoria y el archivo es compartido. Con `--workers 4` cada
proceso tendría cooldowns y contadores distintos, multiplicando llamadas reales
a los proveedores. Mantén 1 worker (el rendimiento sobra: la latencia la pone el
proveedor, no Python).

## Ampliaciones previstas

| Idea | Dónde tocar |
|---|---|
| Redis/Postgres para estado compartido | `pool.py` (interfaz `snapshot/load/save`) |
| Métricas Prometheus | `api.py` (`/metrics`) + contadores de `pool` |
| Ranking por latencia observada | `router.py` (`candidates()` puede ordenar por EWMA) |
| Auto-descubrimiento de modelos | nuevo `/admin/sync-models` usando `upstream.list_models` |
| Otros formatos (Anthropic, Gemini nativo) | `kind` del proveedor + adaptador en `upstream.py` |
| Enrutado por capacidad (visión, tools) | campo `capabilities` en `providers.json` y filtro en `candidates()` |
| Rate limit por cliente (APK) | middleware con token bucket en `api.py` |

## Decisiones de diseño

- **OpenAI-compatible**: cero fricción con SDKs existentes y con la APK.
- **Config en JSON, no en código**: añadir un proveedor gratis nuevo no requiere
  tocar Python ni reinstalar.
- **Nunca exponer secretos**: `/v1/router/status` omite claves; `/admin/status`
  solo muestra `key_id` y una máscara.
- **Errores útiles**: cada fallo devuelve `error.router.attempts` para depurar
  desde la APK sin acceso al servidor.
- **Dependencias mínimas**: FastAPI + httpx + uvicorn. Corre en Termux sin
  compilar nada exótico.

## Limitaciones

- Los límites gratuitos cambian: la lista es editable, no eterna.
- No hay garantía de disponibilidad ni de calidad de respuesta.
- Un modelo forzado (`proveedor/modelo`) no salta a otro proveedor por diseño.
- `context_length` demasiado grande falla en todos: el router devuelve el error.
- El estado es por proceso (ver arriba).
