# Free AI Router · APIs de IA gratis con rotación automática

Gateway **compatible con la API de OpenAI** que reparte tus peticiones entre
**17 proveedores de IA con capa gratuita** (Gemini, Groq, Cerebras, OpenRouter,
Mistral, GitHub Models, SambaNova, NVIDIA, Cohere, Cloudflare, Together,
Hugging Face, Z.ai, Qwen, Pollinations, Ollama, LM Studio) y **rota de clave /
proveedor cuando se agota un límite**.

Pensado para usarse desde una **APK Android** (Kotlin, Java, WebView, Flutter,
React Native, Termux…) como si fuera la API de OpenAI: cambias la `baseUrl` y
ya está.

```
   APK Android / curl / SDK OpenAI
              │
              ▼
   ┌──────────────────────────┐
   │   Free AI Router :8080   │  ← un solo endpoint, un solo token
   │  /v1/chat/completions    │
   └────────────┬─────────────┘
                │ elige proveedor + clave, reintenta si falla
      ┌─────────┼─────────┬──────────┬─────────┐
      ▼         ▼         ▼          ▼         ▼
   Gemini     Groq     Cerebras  OpenRouter  …  (17)
   429/402 → clave en cuarentena → siguiente proveedor
```

---

## Índice

- [Qué resuelve](#qué-resuelve)
- [Cómo funciona la rotación](#cómo-funciona-la-rotación)
- [Inicio rápido](#inicio-rápido)
- [Usarlo desde la APK](#usarlo-desde-la-apk)
- [Endpoints](#endpoints)
- [Proveedores incluidos](#proveedores-incluidos)
- [Configuración](#configuración)
- [Añadir un proveedor nuevo](#añadir-un-proveedor-nuevo)
- [Administración en caliente](#administración-en-caliente)
- [Seguridad y uso responsable](#seguridad-y-uso-responsable)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Tests](#tests)
- [Documentación adicional](#documentación-adicional)

---

## Qué resuelve

| Problema | Solución en este repo |
|---|---|
| Cada API gratis tiene su propio formato y SDK | Todo se expone como **`/v1/chat/completions`** estilo OpenAI |
| Al llegar al límite (429) la app se rompe | Se pone esa **clave en cuarentena** y se prueba el siguiente proveedor |
| Cambiar de proveedor implica tocar la APK | La APK solo habla con el router; el router decide |
| Las claves se filtran si van dentro del APK | Las claves viven **solo en el servidor/.env** |
| No sabes qué proveedor está saturado | **Consola web** en `/` y estado en `/v1/router/status` |
| Una clave inválida arruina todo | Se **deshabilita** sola y el resto sigue funcionando |
| Los modelos gratis cambian cada semana | Lista editable en `config/providers.json` + `scripts/doctor.py --models` para descubrir los actuales |

Lo que **no** hace: no crea cuentas, no evade límites y no multiplica cuotas por
organización. Ver [uso responsable](#seguridad-y-uso-responsable).

---

## Cómo funciona la rotación

1. **Entrada**: la APK manda `POST /v1/chat/completions` con `model: "auto"`
   (o `"groq/llama-3.3-70b-versatile"`, o un id suelto).
2. **Plan**: el router construye una lista ordenada de candidatos
   `(proveedor, modelo)` por `priority` y descarta los que no tienen clave libre
   (rpm/rpd/tpd agotados o en cuarentena).
3. **Intento**: elige la clave **menos usada** del proveedor, llama al upstream.
4. **Clasificación** de la respuesta:

   | Respuesta del proveedor | Acción |
   |---|---|
   | `200` | devuelve al cliente + cabeceras `x-router-*` |
   | `429` / `x-ratelimit-*` | clave en cuarentena (`Retry-After`, mínimo 5 s, máx. 24 h) → siguiente |
   | `402` / `403` con *quota/billing* | cuarentena larga (por defecto 6 h) → siguiente |
   | `401` | clave **deshabilitada** hasta que la reactives → siguiente |
   | `404` / *model not found* | reintenta ese proveedor con su modelo por defecto → siguiente |
   | `400` *unknown parameter* | reintenta sin `tools`, `response_format`, `logprobs`… |
   | `400` genérico | **no** se reintenta: es un error de la petición (se devuelve 400) |
   | `5xx` / timeout / red | cuarentena corta (≤120 s) → siguiente |

5. **Fin**: si todo falla, respuesta `429` (todo saturado, con `Retry-After`)
   o `502` con el detalle de cada intento en `error.router.attempts`.

El estado (cooldowns, contadores diarios, claves añadidas en caliente) se guarda
en `data/state.json` para sobrevivir reinicios. Los contadores se reinician a
medianoche UTC.

Detalles internos en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

---

## Inicio rápido

### Opción A · Linux / VPS (recomendado)

```bash
git clone https://github.com/yoandryforbes776-rgb/apk2.git
cd apk2
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env          # pon al menos una clave (p. ej. GROQ_API_KEY) y los tokens

python scripts/doctor.py        # comprueba qué proveedores están listos
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Abre `http://IP-DEL-SERVIDOR:8080` → consola de chat con streaming.
Documentación interactiva: `http://IP-DEL-SERVIDOR:8080/docs`.

### Opción B · Dentro del Android (Termux / Linux proot) — modo harness

```bash
pkg install git python -y
git clone https://github.com/yoandryforbes776-rgb/apk2.git
cd apk2
nano .env                  # pega tus claves y ROUTER_TOKEN
bash scripts/android.sh    # instala, arranca y muestra qué pegar en tu APK
```

El script imprime el bloque exacto para el harness:

```
Base URL : http://127.0.0.1:8080/v1
API Key  : tu-token
Modelo   : auto
```

Guía paso a paso para harnesses y APKs:
[`docs/HARNESS.md`](docs/HARNESS.md). Desde el emulador usa
`http://10.0.2.2:8080/v1`.

### Opción C · Docker

```bash
cp .env.example .env && nano .env
docker compose up -d --build
docker compose logs -f
```

---

## Usarlo desde la APK

### curl (para probar)

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $ROUTER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hola, ¿quién eres?"}]
  }'
```

### Kotlin (OkHttp) — cliente listo para copiar

[`clients/kotlin/FreeAiClient.kt`](clients/kotlin/FreeAiClient.kt) incluye
`chat()` y `chatStream()` con Flow. Ver
[`clients/kotlin/README.md`](clients/kotlin/README.md) y
[`docs/ANDROID.md`](docs/ANDROID.md).

```kotlin
val api = FreeAiClient(
    baseUrl = "http://10.0.2.2:8080",
    routerToken = "tu-ROUTER_TOKEN",
    model = "auto",
)
val r = api.chat(listOf(ChatMessage("user", "Ideas de nombres para mi app")))
Log.d("AI", "${r.provider} respondió en ${r.latencyMs} ms")
```

### Cualquier SDK de OpenAI

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="tu-ROUTER_TOKEN")
print(client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hola"}],
).choices[0].message.content)
```

Las cabeceras de respuesta te dicen quién atendió:

```
x-router-provider: groq
x-router-model: llama-3.3-70b-versatile
x-router-attempts: 2
x-router-latency-ms: 640
x-router-key: 0fed8044f40a
```

---

## Endpoints

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/health` | — | estado básico del servicio |
| GET | `/v1/models` | cliente | modelos disponibles (`auto`, `proveedor/modelo`, sueltos) |
| POST | `/v1/chat/completions` | cliente | chat con **streaming SSE** o JSON |
| POST | `/v1/completions` | cliente | formato viejo (se traduce a chat) |
| GET | `/v1/models/{id}` | cliente | consulta de un modelo concreto |
| POST | `/v1/embeddings` | cliente | embeddings (Gemini, Mistral, Cohere, Cloudflare) |
| GET | `/v1/router/status` | cliente | proveedores y claves libres, sin secretos |
| GET | `/admin/status` | admin | estado completo con claves enmascaradas |
| GET | `/admin/providers` | admin | catálogo con enlaces de registro |
| POST | `/admin/keys` | admin | añadir clave en caliente |
| DELETE | `/admin/keys/{id}` | admin | quitar/desactivar clave |
| POST | `/admin/test` | admin | ping real a uno o todos los proveedores |
| POST | `/admin/reload` | admin | recargar `providers.json` sin reiniciar |
| POST | `/admin/reset` | admin | limpiar cooldowns y reactivar claves |
| GET | `/docs` | — | Swagger UI |
| GET | `/` · `/ui` | — | consola de chat para el móvil |

Referencia completa con ejemplos:
[`docs/API.md`](docs/API.md).

---

## Proveedores incluidos

Ordenados por `priority` (menor = se intenta antes).

| # | Proveedor | Clave en `.env` | Modelo por defecto | Gratis (aprox.) |
|---|---|---|---|---|
| 1 | Google Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash` | ~1.500 req/día, 1M TPM |
| 2 | Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | 30 RPM, 1.000 req/día |
| 3 | Cerebras | `CEREBRAS_API_KEY` | `llama-3.3-70b` | 30 RPM, ~1M tok/día |
| 4 | OpenRouter | `OPENROUTER_API_KEY` | `deepseek/deepseek-r1:free` | 20 RPM, 50 req/día |
| 5 | Mistral | `MISTRAL_API_KEY` | `mistral-small-latest` | cuota mensual |
| 6 | Z.ai (GLM) | `ZHIPU_API_KEY` | `glm-4.5-flash` | modelo flash gratis |
| 7 | SambaNova | `SAMBANOVA_API_KEY` | `Meta-Llama-3.3-70B-Instruct` | free tier dev |
| 8 | NVIDIA NIM | `NVIDIA_API_KEY` | `meta/llama-3.3-70b-instruct` | ~1.000 llamadas |
| 9 | GitHub Models | `GITHUB_MODELS_TOKEN` | `openai/gpt-4o-mini` | límites por nivel |
| 10 | Cohere | `COHERE_API_KEY` | `command-r7b-12-2024` | trial key |
| 11 | Cloudflare Workers AI | `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 10k neuronas/día |
| 12 | Together | `TOGETHER_API_KEY` | `...-Turbo-Free` | solo modelos `-Free` |
| 13 | Hugging Face | `HF_TOKEN` | `meta-llama/Llama-3.3-70B-Instruct` | créditos mensuales |
| 14 | Alibaba DashScope | `DASHSCOPE_API_KEY` | `qwen-plus` | cuota inicial |
| 15 | Pollinations | *(sin clave, desactivado)* | `openai` | comunitario, sin SLA |
| 16 | Ollama local | *(sin clave, desactivado)* | `llama3.2` | ilimitado en tu equipo |
| 17 | LM Studio local | *(sin clave, desactivado)* | `local-model` | ilimitado en tu equipo |

Límites, enlaces de registro y notas por proveedor:
[`docs/PROVIDERS.md`](docs/PROVIDERS.md). **Los límites gratuitos cambian**:
verifícalos en la consola de cada proveedor.

> ⚠️ Muchos proveedores aplican el límite **por organización/cuenta**, no por
> clave. Varias claves de la misma cuenta **no** multiplican la cuota; en ese
> caso el router simplemente pasa al siguiente proveedor.

---

## Configuración

Todo va en `.env` (copia de `.env.example`):

| Variable | Por defecto | Para qué |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8080` | dónde escucha |
| `ROUTER_TOKEN` | *(vacío)* | token que debe enviar la APK en `Authorization: Bearer` |
| `ADMIN_TOKEN` | *(vacío)* | token para `/admin/*`; si está vacío solo se permite localhost |
| `MAX_ATTEMPTS` | `8` | proveedores/claves distintos por petición |
| `PROVIDER_TIMEOUT` | `90` | timeout de lectura por proveedor (s) |
| `REQUEST_TIMEOUT` | `240` | presupuesto total incluyendo reintentos (s) |
| `CONNECT_TIMEOUT` | `15` | timeout de conexión (s) |
| `PERSIST_KEYS` | `true` | guardar claves/cooldowns en `data/state.json` |
| `ALLOW_CORS` | `true` | CORS abierto para WebView y navegador |
| `CONFIG_PATH` | `config/providers.json` | catálogo de proveedores |
| `STATE_PATH` | `data/state.json` | estado persistente |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning` |

Claves múltiples por proveedor:

```env
GROQ_API_KEY=sk-aaa
GROQ_API_KEY_2=sk-bbb
GROQ_API_KEY_3=sk-ccc
# o en una sola línea:
GROQ_API_KEY=sk-aaa,sk-bbb,sk-ccc
```

---

## Añadir un proveedor nuevo

Casi todos los proveedores gratis hablan el formato OpenAI. Añade un objeto a
`config/providers.json`:

```json
{
  "id": "miproveedor",
  "label": "Mi Proveedor",
  "kind": "openai",
  "baseUrl": "https://api.miproveedor.com/v1",
  "keyEnvPrefix": "MIPROVEEDOR_API_KEY",
  "defaultModel": "modelo-gratis",
  "models": ["modelo-gratis", "modelo-grande"],
  "priority": 35,
  "rpm": 20,
  "rpd": 200,
  "cooldownSeconds": 60,
  "quotaCooldownSeconds": 21600,
  "signupUrl": "https://miproveedor.com/keys",
  "docsUrl": "https://miproveedor.com/docs/limits",
  "notes": "texto libre para la consola"
}
```

Añade la clave en `.env`, ejecuta `python scripts/doctor.py --ping` y, si todo
va bien, `POST /admin/reload` (o reinicia). No hace falta tocar código.

Campos disponibles y su significado:
[`docs/PROVIDERS.md`](docs/PROVIDERS.md#añadir-o-editar-proveedores).

---

## Administración en caliente

```bash
# Añadir una clave sin reiniciar (se persiste en data/state.json)
curl -X POST http://localhost:8080/admin/keys \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"provider":"groq","key":"gsk_xxx","label":"cuenta-2"}'

# Ver qué está saturado y cuándo se libera
curl http://localhost:8080/admin/status -H "X-Admin-Token: $ADMIN_TOKEN" | jq

# Probar todos los proveedores con una petición real
curl -X POST http://localhost:8080/admin/test -H "X-Admin-Token: $ADMIN_TOKEN"

# Limpiar cooldowns tras corregir una clave
curl -X POST http://localhost:8080/admin/reset -H "X-Admin-Token: $ADMIN_TOKEN"
```

---

## Seguridad y uso responsable

- **Las claves nunca van en la APK.** Viven en `.env` o en `data/state.json`
  (modo `600`). El APK solo conoce `ROUTER_TOKEN`.
- **Usa HTTPS** si el router sale de tu red local (Caddy, nginx o Cloudflare
  Tunnel). Ver [`docs/DEPLOY.md`](docs/DEPLOY.md).
- **No publiques** un router abierto: sin `ROUTER_TOKEN` cualquiera puede gastar
  tus cuotas.
- Respeta los términos de cada proveedor: nada de cuentas masivas para esquivar
  límites ni reventa del servicio. La rotación está pensada para **resiliencia
  entre proveedores legítimos**, no para evadir cuotas.
- Algunos free tiers usan tus prompts para entrenar (Gemini, OpenRouter…).
  No envíes datos personales o secretos.
- Los límites son orientativos y cambian sin aviso: este repo no garantiza
  disponibilidad ni exactitud de las cuotas.

---

## Estructura del proyecto

```
apk2/
├── app/
│   ├── main.py          FastAPI + CORS + manejadores de error
│   ├── api.py           endpoints /v1 y /admin
│   ├── router.py        selección de proveedor, reintentos, streaming
│   ├── pool.py          claves, cooldowns, rpm/rpd/tpd, persistencia
│   ├── registry.py      carga y valida config/providers.json
│   ├── upstream.py      HTTP a proveedores + clasificación de errores
│   ├── settings.py      .env y variables de entorno
│   ├── util.py          Retry-After, huellas de claves, modelos
│   └── static/index.html  consola web de chat
├── config/providers.json    catálogo de 17 proveedores
├── clients/kotlin/          cliente Android (OkHttp + Flow)
├── docs/                    API, proveedores, harness, Android, despliegue
├── scripts/                 doctor, instalación en Termux y arranque Android
├── tests/                   42 tests sin llamadas de red
├── Dockerfile · docker-compose.yml
├── requirements.txt · .env.example
└── README.md
```

---

## Tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

42 tests cubren rotación, cooldowns, cuotas, persistencia, selección de modelos,
streaming, autenticación y endpoints, sin tocar la red (upstream simulado).

---

## Documentación adicional

| Documento | Contenido |
|---|---|
| [`docs/API.md`](docs/API.md) | endpoints, cabeceras, errores, ejemplos |
| [`docs/PROVIDERS.md`](docs/PROVIDERS.md) | catálogo, límites, cómo añadir uno |
| [`docs/HARNESS.md`](docs/HARNESS.md) | **pegar el router en tu harness/APK paso a paso** |
| [`docs/ANDROID.md`](docs/ANDROID.md) | integración en la APK, TLS, batería, OpenAI SDK |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | VPS, Docker, systemd, Caddy, Cloudflare Tunnel, Termux |
| [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) | algoritmo de rotación, estado, ampliaciones |

---

## Licencia

MIT. Úsalo bajo tu responsabilidad y respetando los términos de cada proveedor.
