# Usar el router desde tu APK / harness Android

Tu harness (la app que ya usas para probar modelos) solo necesita **tres datos**
y un proveedor de tipo *OpenAI compatible*. No hay que tocar la app.

| Campo del harness | Valor |
|---|---|
| **Base URL / API Base** | `http://127.0.0.1:8080/v1` |
| **API Key** | tu `ROUTER_TOKEN` (si lo dejaste vacío: cualquier texto, p. ej. `sk-local`) |
| **Modelo** | `auto` |

Y si el router corre en otro equipo de la red:

| Campo | Valor |
|---|---|
| Base URL | `http://IP-DEL-EQUIPO:8080/v1` |

---

## 1. ¿Dónde ejecuto el router?

| Escenario | Ventaja | Inconveniente |
|---|---|---|
| **A. En el propio móvil** (Termux / Linux proot) | sin red, sin TLS, privado | Android puede matar el proceso; batería |
| **B. En el PC/servidor de tu Wi-Fi** | no consume batería, sigue vivo | el móvil debe estar en la misma red |
| **C. En un VPS con HTTPS** | funciona desde cualquier red (datos móviles) | requiere dominio/TLS y exponerlo con token |

Recomendación: prueba con **A** para desarrollo y pasa a **C** para uso real.

---

## 2. Escenario A · router en el mismo móvil

Suponiendo que tu app tiene Linux con terminal (Termux o un proot con Ubuntu):

```bash
pkg install -y git python          # Termux; en Ubuntu: apt install -y git python3 python3-venv
git clone https://github.com/yoandryforbes776-rgb/apk2.git
cd apk2

nano .env      # pega al menos una clave: GROQ_API_KEY=..., GEMINI_API_KEY=...
               # y pon ROUTER_TOKEN=algo-largo

bash scripts/android.sh
```

El script instala dependencias, arranca el servidor y te imprime el bloque para
pegar en el harness:

```
Base URL : http://127.0.0.1:8080/v1
API Key  : tu-token
Modelo   : auto
```

Para dejarlo corriendo en segundo plano:

```bash
termux-wake-lock
nohup bash scripts/android.sh > router.log 2>&1 &
tail -f router.log
```

Notas para que no se muera:

- Ajustes de Android → Apps → Termux → **Batería: sin restricciones**.
- Instala **Termux:Boot** y crea `~/.termux/boot/router.sh` (ver
  [`DEPLOY.md`](DEPLOY.md#5-termux-router-dentro-del-android)).
- Dentro de un contenedor proot, `127.0.0.1` normalmente sigue siendo el del
  móvil. Si no conecta, usa la **IP de la Wi-Fi** del móvil en la Base URL.

---

## 3. Escenario B · router en el PC de la misma Wi-Fi

En el PC:

```bash
cp .env.example .env && nano .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Averigua la IP (`ip addr` / `ipconfig`), por ejemplo `192.168.1.50`, y en el
móvil abre `http://192.168.1.50:8080/` para comprobar que carga la consola.

En el harness:

```
Base URL: http://192.168.1.50:8080/v1
```

Si no abre: firewall del PC bloqueando el 8080. **Nunca pongas `127.0.0.1`
en el móvil si el router está en el PC** (para el móvil, `127.0.0.1` es él mismo).

---

## 4. Escenario C · VPS con HTTPS

Sigue [`DEPLOY.md`](DEPLOY.md): Docker Compose + Caddy o Cloudflare Tunnel.
En el harness:

```
Base URL: https://ai.tudominio.com/v1
API Key : el ROUTER_TOKEN
Modelo  : auto
```

Con HTTPS no hay problemas de *cleartext* ni necesidad de estar en la misma red
(funciona con datos móviles).

---

## 5. Cómo rellenar los campos del harness

Los nombres cambian según la app, pero el significado es siempre el mismo:

| Lo que pide la app | Qué poner |
|---|---|
| Provider type: *OpenAI*, *OpenAI Compatible*, *Custom OpenAI* | elígelo |
| `API Base URL`, `Base URL`, `Endpoint` | `http://127.0.0.1:8080/v1` |
| `API Endpoint` completo (pide la ruta entera) | `http://127.0.0.1:8080/v1/chat/completions` |
| `API Key` / `Token` | tu `ROUTER_TOKEN` (o `sk-local` si está vacío) |
| `Model` / `Model ID` | `auto` |
| `Modelo concreto` | `groq/llama-3.3-70b-versatile`, `gemini/gemini-2.5-flash`… (ver `/v1/models`) |
| `Context length` / `Context window` | 8192 (conservador) · hasta 32768 en Groq/Gemini |
| `Max tokens` | 256–1024 |
| `Streaming` | **ON** (si la app se atasca, prueba OFF) |
| `Temperature`, `top_p` | los que quieras; se reenvían tal cual |
| `System prompt` | libre |
| Botón "Refresh / Download models" | pulsa: lista `auto` + `proveedor/modelo` |

**Truco**: si el harness no deja escribir `auto` y obliga a elegir de una lista,
pulsa recargar modelos y elige `auto`; si no aparece, escribe cualquier id
(`gpt-4`, `llama-3`, el que traiga por defecto). El router lo acepta y usa el
modelo por defecto del proveedor, **sin gastar 8 intentos en errores 404**.

Si la app solo habla el formato viejo `/v1/completions`, también está soportado
(se traduce a chat internamente).

---

## 6. Verificación en 30 segundos

Desde la terminal del móvil:

```bash
# 1. ¿está vivo?
curl -s http://127.0.0.1:8080/health

# 2. ¿ve las claves?
curl -s http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer TU_TOKEN" | head -c 300

# 3. ¿responde de verdad? (streaming)
curl -sN http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer TU_TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"auto","stream":true,"messages":[{"role":"user","content":"di hola"}]}'
```

Si el paso 3 devuelve `data: ...` en trozos, el harness también funcionará.
También puedes abrir `http://127.0.0.1:8080/` en el navegador del móvil.

---

## 7. Qué esperar del comportamiento

- El harness cree que habla con **un** proveedor; detrás hay 17.
- Si un proveedor está al límite, la respuesta puede tardar un poco más
  (reintento invisible) pero **no falla**.
- Las cabeceras `x-router-provider` / `x-router-latency-ms` te dicen quién
  respondió (visibles en la consola web; en el harness normalmente no).
- `429` = todo saturado; respeta `Retry-After` antes de reintentar.
- Los modelos gratuitos tienen contexto y calidad variables: una respuesta puede
  ser distinta según qué proveedor atienda. Para fijar uno usa
  `proveedor/modelo`.
- Los prompts largos (roleplay con mucha ficha) pueden superar el contexto del
  free tier: recorta historial o usa Gemini (1M de contexto).

---

## 8. Problemas típicos y solución

| Síntoma | Causa | Solución |
|---|---|---|
| `Connection refused` / "failed to connect" | router apagado o escuchando solo en 127.0.0.1 | arranca con `--host 0.0.0.0` (`scripts/android.sh` ya lo hace) |
| Funciona el navegador pero no la app | la app no manda token | pon el `ROUTER_TOKEN` en el campo API Key |
| `401 Unauthorized` | token distinto o con espacios | copia/pega de nuevo; revisa `nano .env` |
| "Cleartext HTTP not permitted" **dentro del harness** | la app bloquea `http://` | usa HTTPS (Cloudflare Tunnel/Caddy) o el router en el propio móvil si la app lo permite |
| Todo `timeout` en el harness pero `curl` va bien | la app espera respuesta completa | activa streaming; sube el timeout de la app a 120–180 s |
| Se queda "pensando" y no escribe nada | proxy bufferizando SSE | si hay proxy delante: `flush_interval -1` (Caddy) o `proxy_buffering off` (nginx) |
| `429` tras unos mensajes | free tiers agotados | añade más proveedores/claves; espera el `Retry-After` |
| No aparece ningún modelo en la lista | proveedores sin claves | `python scripts/doctor.py` y añade claves en `.env` |
| El router desaparece al bloquear el móvil | Android mató Termux | `termux-wake-lock`, batería sin restricciones o router en el PC/VPS |
| Responde en español raro o cambia de estilo | cambió el proveedor | fija `proveedor/modelo` |
| Proot no conecta a 127.0.0.1 | red del contenedor | usa la IP Wi-Fi del móvil |
| `503 no_keys` | `.env` sin claves o mal ubicado | ejecuta desde la raíz del repo; `python scripts/doctor.py` |

---

## 9. Qué modelo usar según el caso

| Caso | Recomendación |
|---|---|
| Chat general, rápido | `gemini/gemini-2.5-flash` · `groq/llama-3.3-70b-versatile` |
| Contexto enorme (documentos, rol) | `gemini/gemini-2.5-pro` (free limitado) · `gemini/gemini-2.5-flash` |
| Código | `openai/gpt-oss-120b` (Groq/Cerebras) · `qwen/qwen3-coder:free` (OpenRouter) |
| Creativo / español natural | `zhipu/glm-4.5-flash` · `mistral/mistral-small-latest` |
| Sin Internet / privacidad | `ollama/llama3.2` (activa el proveedor) |
| Máxima disponibilidad | `auto` (es el propósito del router) |

---

## 10. Límites: cómo estirarlos sin romper las reglas

1. **Añade proveedores, no cuentas.** Gemini, Groq, Cerebras y GitHub limitan
   por organización: clonar cuentas no da más cuota y sí incumple sus términos.
2. **Recorta el historial** y usa `max_tokens` moderado: el límite suele ser de
   tokens, no de peticiones.
3. **Streaming** no gasta menos, pero evita timeouts y mejora la sensación.
4. **Prioriza por calidad/latencia** en `priority` y deja los free pequeños como
   último recurso.
5. **Revisa `python scripts/doctor.py --ping`** una vez por semana: detecta
   claves muertas y modelos renombrados antes de que te afecten.

---

## Checklist de 60 segundos

- [ ] `.env` con al menos una clave + `ROUTER_TOKEN`.
- [ ] `python scripts/doctor.py` dice *N proveedor(es) listo(s)*.
- [ ] `curl /health` responde `ok` desde el móvil.
- [ ] `curl` de chat con `stream:true` devuelve `data:` en trozos.
- [ ] Harness: Base URL `.../v1`, API Key = token, Modelo `auto`.
- [ ] Streaming ON y timeout ≥ 120 s en la app.
- [ ] Router con `--host 0.0.0.0` (`scripts/android.sh` lo hace).
- [ ] Si sales de la Wi-Fi, HTTPS con token largo.

Si quieres, dime **qué harness usas exactamente** (nombre y cómo se llaman sus
campos) y te dejo la configuración literal, captura por captura.
