# Referencia de la API

Base: `http://IP:8080`. Formato OpenAI. Autenticación con
`Authorization: Bearer <ROUTER_TOKEN>` en todo `/v1/*`
(también se aceptan `X-API-Key` y `X-Router-Token`).

## Cabeceras de respuesta

Todas las respuestas de `/v1/chat/completions` incluyen:

| Cabecera | Ejemplo | Significado |
|---|---|---|
| `x-router-provider` | `groq` | proveedor que atendió |
| `x-router-model` | `llama-3.3-70b-versatile` | modelo real usado |
| `x-router-key` | `0fed8044f40a` | huella de la clave (nunca el secreto) |
| `x-router-attempts` | `2` | intentos realizados |
| `x-router-latency-ms` | `640` | latencia del intento exitoso |

Si todo está saturado, la respuesta `429` trae `Retry-After` en segundos.

---

## `GET /health`

Sin autenticación.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime_seconds": 42.1,
  "providers_enabled": 14,
  "providers_ready": 5,
  "keys": 7,
  "load_error": ""
}
```

`providers_ready` = proveedores con al menos una clave disponible ahora mismo.

---

## `GET /v1/models`

```bash
curl http://localhost:8080/v1/models -H "Authorization: Bearer $TOKEN"
```

```json
{
  "object": "list",
  "data": [
    {"id": "auto", "object": "model", "owned_by": "router"},
    {"id": "groq/llama-3.3-70b-versatile", "object": "model", "owned_by": "groq",
     "x_router": {"provider": "groq", "model": "llama-3.3-70b-versatile"}},
    {"id": "llama-3.3-70b-versatile", "object": "model", "owned_by": "groq"}
  ]
}
```

- `auto` → el router elige el mejor disponible.
- `proveedor/modelo` → fuerza ese proveedor (si falla, se detiene ahí).
- `modelo` suelto → busca coincidencias en todos los proveedores.
- `?all=true` incluye modelos de proveedores sin clave configurada.

---

## `POST /v1/chat/completions`

### Petición mínima

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "system", "content": "Responde en español."},
      {"role": "user", "content": "Dame 3 nombres para una app de notas."}
    ],
    "temperature": 0.7,
    "max_tokens": 300
  }'
```

### Respuesta

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "llama-3.3-70b-versatile",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "1. NotaRápida..."},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 25, "completion_tokens": 180, "total_tokens": 205}
}
```

### Streaming (SSE)

```bash
curl -N http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","stream":true,"messages":[{"role":"user","content":"Cuenta hasta 5"}]}'
```

```
data: {"id":"...","choices":[{"delta":{"role":"assistant"}}]}
data: {"id":"...","choices":[{"delta":{"content":"1"}}]}
data: {"id":"...","choices":[{"delta":{"content":", 2"}}]}
data: [DONE]
```

Formato idéntico al de OpenAI: funciona con `openai` SDK, Vercel AI SDK,
LangChain, etc. El router solo empieza a emitir cuando un proveedor ya devolvió
`200`, así que los reintentos son invisibles para el cliente.

### Parámetros

Se reenvían tal cual al proveedor (`temperature`, `top_p`, `max_tokens`,
`stop`, `tools`, `response_format`…). Si un proveedor rechaza un parámetro
opcional con `400 unknown parameter`, el router reintenta **sin** `tools`,
`response_format`, `logprobs`, `seed`, `stop`, etc., para maximizar
compatibilidad. `stream_options` se añade solo en streaming.

### Errores

```json
{
  "error": {
    "message": "Todos los proveedores gratuitos están en límite ahora mismo. Inténtalo más tarde.",
    "type": "rate_limited",
    "code": "rate_limited",
    "router": {
      "attempts": [
        {"provider": "groq", "model": "llama-3.3-70b-versatile", "key_id": "0fed8044f40a",
         "status": 429, "kind": "rate_limited", "detail": "Rate limit reached...", "latency_ms": 120},
        {"provider": "gemini", "model": "gemini-2.5-flash", "key_id": "8aa1c2d3e4f5",
         "status": 429, "kind": "rate_limited", "detail": "Quota exceeded", "latency_ms": 210}
      ],
      "retry_after": 47
    }
  }
}
```

| HTTP | `code` | Cuándo |
|---|---|---|
| 400 | `bad_request` | petición inválida o rechazada por el proveedor |
| 401 | `invalid_request_error` | token de cliente incorrecto |
| 429 | `rate_limited` | todos en cuarentena; mira `Retry-After` |
| 502 | `all_providers_failed` | fallos mixtos (red, 5xx, modelos) |
| 503 | `no_keys` / `no_providers` / `no_candidates` | configuración incompleta |

---

## `POST /v1/embeddings`

```bash
curl http://localhost:8080/v1/embeddings \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"auto","input":"hola mundo"}'
```

Disponible en Gemini, Mistral, Cohere y Cloudflare (configura `embeddingModel`).
Si ningún proveedor lo soporta: `503 no_embeddings`.

---

## `GET /v1/router/status`

Sin secretos, apto para mostrar en la APK.

```json
{
  "providers": [
    {
      "id": "groq", "label": "Groq", "priority": 20,
      "enabled": true, "requires_key": true,
      "keys_total": 2, "keys_available": 1,
      "available_at": 1794486800.2,
      "default_model": "llama-3.3-70b-versatile",
      "last_error": "Rate limit reached",
      "models": ["llama-3.3-70b-versatile", "..."]
    }
  ],
  "attempts_budget": 8,
  "now": 1794486717.0
}
```

---

## Administración

Requieren `ADMIN_TOKEN` (cabecera `X-Admin-Token` o `Authorization: Bearer`).
Si `ADMIN_TOKEN` está vacío, solo se permite desde `127.0.0.1`/`::1`.

### `GET /admin/status`

Todo el estado, con claves enmascaradas (`gsk_…a1b2`), cooldowns, contadores
diarios y errores por proveedor.

### `GET /admin/providers`

Catálogo con `signup_url`, `docs_url` y notas. Útil para pintar un menú de
"conecta tus cuentas" en la APK.

### `POST /admin/keys`

```bash
curl -X POST http://localhost:8080/admin/keys \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"provider":"openrouter","key":"sk-or-v1-...","label":"mi-cuenta"}'
```

```json
{"ok": true, "provider": "openrouter", "key_id": "a1b2c3d4e5f6", "masked": "sk-o…cdef", "source": "runtime"}
```

### `DELETE /admin/keys/{key_id}`

Las claves de `.env` no se pueden borrar (volverían al recargar): se marcan
como deshabilitadas. Las añadidas en caliente se eliminan físicamente.

### `POST /admin/test`

```bash
curl -X POST http://localhost:8080/admin/test \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"provider":"groq"}'      # vacío {} = todos los que tengan claves
```

Devuelve latencia, modelo y respuesta corta (o el error clasificado).

### `POST /admin/reload`

Vuelve a leer `config/providers.json` y sincroniza claves de `.env` sin reiniciar.

### `POST /admin/reset`

Limpia cooldowns, reactiva claves deshabilitadas y vacía las ventanas de RPM.
No borra contadores históricos.

---

## Consola web

`GET /` sirve una consola móvil con streaming, selector de modelo, badge del
proveedor y panel de estado. Es la forma más rápida de validar el router desde
el propio teléfono.

## OpenAPI

`GET /docs` (Swagger UI) y `GET /openapi.json`.
