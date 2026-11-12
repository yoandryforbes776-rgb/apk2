# Proveedores gratuitos

Catálogo incluido en `config/providers.json`. Los límites son **aproximados**
(verificados en noviembre de 2026) y cambian con frecuencia: la fuente de verdad
es siempre la consola de cada proveedor.

Orden de intento = `priority` (menor primero). Puedes reordenar editando el JSON
y ejecutando `POST /admin/reload`.

## Resumen

| Proveedor | Registro | Gratis | Límite orientativo | Fuerza |
|---|---|---|---|---|
| **Google Gemini** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Sí, sin tarjeta | ~1.500 req/día en Flash, 1M TPM | modelos grandes, contexto 1M |
| **Groq** | [console.groq.com/keys](https://console.groq.com/keys) | Sí, sin tarjeta | 30 RPM · 1.000 req/día (70B) · 12K TPM | latencia muy baja |
| **Cerebras** | [cloud.cerebras.ai](https://cloud.cerebras.ai/) | Sí | 30 RPM · ~1M tok/día | salida ultra rápida |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | Sí, modelos `:free` | 20 RPM · 50 req/día (1.000 si compras $10) | variedad de modelos |
| **Mistral** | [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys/) | Sí (teléfono) | cuota mensual | modelos europeos |
| **Z.ai (GLM)** | [z.ai](https://z.ai/manage-apikey/apikey-list) | `glm-4.5-flash` gratis | RPM/RPD por cuenta | buen español |
| **SambaNova** | [cloud.sambanova.ai](https://cloud.sambanova.ai/) | free tier dev | ~1.000 req/día | Llama/DeepSeek rápidos |
| **NVIDIA NIM** | [build.nvidia.com](https://build.nvidia.com/) | créditos dev | ~1.000 llamadas | modelos NVIDIA y abiertos |
| **GitHub Models** | [github.com/settings/tokens](https://github.com/settings/tokens) | Sí con PAT `models:read` | bajo, por nivel de cuenta | GPT-4o-mini sin coste |
| **Cohere** | [dashboard.cohere.com](https://dashboard.cohere.com/api-keys) | trial key | RPM/mes limitados | RAG, embeddings |
| **Cloudflare Workers AI** | [dash.cloudflare.com](https://dash.cloudflare.com/profile/api-tokens) | 10.000 neuronas/día | ~decenas de req/día | borde global |
| **Together** | [api.together.ai](https://api.together.ai/settings/api-keys) | modelos `-Free` | 6 RPM | modelos abiertos |
| **Hugging Face** | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | créditos mensuales | pequeño | catálogo enorme |
| **Alibaba DashScope** | [bailian.console.alibabacloud.com](https://bailian.console.alibabacloud.com/) | cuota inicial | tokens de bienvenida | Qwen |
| **Pollinations** | [pollinations.ai](https://pollinations.ai/) | sin clave | uso justo comunitario | cero configuración |
| **Ollama** | [ollama.com](https://ollama.com/download) | local | sin límite | privacidad total |
| **LM Studio** | [lmstudio.ai](https://lmstudio.ai/) | local | sin límite | privacidad total |

> **Límites por organización.** Groq, Gemini, Cerebras y GitHub aplican la cuota
> a la cuenta/organización, no a cada clave. Añadir 5 claves de la misma cuenta
> no da 5× cuota: el router cambiará de **proveedor**, que es lo que sí escala.

## Variables de entorno

| Proveedor | Variable(s) | Extra |
|---|---|---|
| Gemini | `GEMINI_API_KEY` o `GOOGLE_API_KEY` | — |
| Groq | `GROQ_API_KEY` | acepta `_2`, `_3`… o lista con comas |
| Cerebras | `CEREBRAS_API_KEY` | — |
| OpenRouter | `OPENROUTER_API_KEY` | envía `HTTP-Referer`/`X-Title` |
| Mistral | `MISTRAL_API_KEY` | — |
| Z.ai | `ZHIPU_API_KEY` | — |
| SambaNova | `SAMBANOVA_API_KEY` | — |
| NVIDIA | `NVIDIA_API_KEY` | — |
| GitHub Models | `GITHUB_MODELS_TOKEN` | PAT con `models:read` |
| Cohere | `COHERE_API_KEY` | — |
| Cloudflare | `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` | la URL usa `{CLOUDFLARE_ACCOUNT_ID}` |
| Together | `TOGETHER_API_KEY` | — |
| Hugging Face | `HF_TOKEN` | permiso de inferencia |
| Alibaba | `DASHSCOPE_API_KEY` | región internacional |
| Pollinations | `POLLINATIONS_API_KEY` *(opcional)* | requiere activar el proveedor |
| Ollama / LM Studio | *(ninguna)* | activar `"enabled": true` |

## Añadir o editar proveedores

Objeto completo con todos los campos:

```json
{
  "id": "ejemplo",
  "label": "Nombre visible",
  "kind": "openai",
  "baseUrl": "https://api.ejemplo.com/v1",
  "keyEnvPrefix": ["EJEMPLO_API_KEY"],
  "defaultModel": "modelo-por-defecto",
  "models": ["modelo-por-defecto", "otro-modelo"],
  "priority": 50,
  "rpm": 30,
  "rpd": 1000,
  "tpm": 12000,
  "tpd": 100000,
  "cooldownSeconds": 60,
  "quotaCooldownSeconds": 21600,
  "timeoutSeconds": 90,
  "requiresKey": true,
  "supportsStreaming": true,
  "supportsEmbeddings": false,
  "embeddingModel": "",
  "embeddingModels": [],
  "headers": { "HTTP-Referer": "https://mi-app" },
  "extraBody": { "temperature": 0.7 },
  "enabled": true,
  "signupUrl": "https://api.ejemplo.com/keys",
  "docsUrl": "https://api.ejemplo.com/docs/limits",
  "notes": "nota visible en /admin/providers"
}
```

| Campo | Significado |
|---|---|
| `id` | identificador corto; también es el prefijo de modelo `id/modelo` |
| `baseUrl` | raíz compatible con OpenAI (sin `/chat/completions`) |
| `keyEnvPrefix` | cadena o lista de variables; acepta sufijos `_2`, `_3`… |
| `defaultModel` | modelo de `auto` y del reintento tras un 404 |
| `models` | ids que anunciará `/v1/models` (y que el router sabrá emparejar) |
| `priority` | orden de intento (menor = antes) |
| `rpm`/`rpd`/`tpm`/`tpd` | límites locales **proactivos**; `0` = sin control |
| `cooldownSeconds` | cuarentena tras 429/5xx sin `Retry-After` |
| `quotaCooldownSeconds` | cuarentena cuando el error huele a cuota diaria/billing |
| `timeoutSeconds` | lectura por petición |
| `requiresKey` | `false` para Ollama, LM Studio, Pollinations… |
| `headers` | cabeceras extra; admite `${VARIABLE}` |
| `extraBody` | parámetros que se añaden solo si el cliente no los envía |
| `enabled` | `false` lo excluye del enrutado (sigue visible en `/admin/providers`) |
| `embeddingModel` | si existe, el proveedor entra en `/v1/embeddings` |

`baseUrl` admite `{VARIABLE_DE_ENTORNO}`; si falta, el proveedor queda
deshabilitado con el motivo en `/admin/status`.

## Mantener la lista al día

```bash
# ¿Qué modelos reporta hoy el proveedor?
python scripts/doctor.py --models groq

# ¿Qué claves funcionan ahora mismo?
python scripts/doctor.py --ping
```

Copia los ids nuevos a `config/providers.json`, recarga con
`POST /admin/reload` y listo.

## Errores típicos

| Síntoma | Causa habitual | Solución |
|---|---|---|
| `401` en `/admin/test` | clave mal copiada o revocada | genera otra; el router la deshabilita sola |
| `403` con *region* | proveedor no disponible en tu país | baja su `priority` o desactívalo |
| `404 model_not_found` | el modelo cambió de nombre | actualiza `models` y `defaultModel` |
| `429` constante | free tier agotado | añade otro proveedor o espera al `Retry-After` |
| Todo `transient` | sin red / DNS / firewall | `curl -I https://api.groq.com` desde el servidor |
| `no_keys` | `.env` no cargado | ejecuta desde la raíz del repo; revisa `python scripts/doctor.py` |
