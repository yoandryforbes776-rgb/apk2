# Integración en la APK Android

El router es un servidor HTTP normal: la APK solo necesita `INTERNET` y una
`baseUrl`. No hay SDK propietario, ni claves de proveedores dentro del APK, ni
lógica de reintentos en el cliente.

## 1. Dónde vive el router

| Escenario | `baseUrl` desde la APK | Notas |
|---|---|---|
| Router en Termux, mismo móvil | `http://127.0.0.1:8080/v1` | sin red, sin TLS; el proceso debe seguir vivo |
| Emulador Android Studio | `http://10.0.2.2:8080/v1` | `10.0.2.2` = `localhost` del PC |
| Móvil + PC en la misma Wi-Fi | `http://192.168.x.x:8080/v1` | abre el puerto en el firewall |
| VPS / servidor doméstico | `https://ai.tudominio.com/v1` | recomendado para uso real |

Si usas Termux en el propio teléfono, arranca con `termux-wake-lock` y considera
un servicio de primer plano para que Android no lo mate:

```bash
termux-wake-lock
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 > router.log 2>&1 &
```

## 2. Gradle y permisos

`app/build.gradle.kts`:

```kotlin
android {
    compileSdk = 35
    defaultConfig {
        minSdk = 24
        // Opcional: configuración por build flavor
        // buildConfigField("String", "ROUTER_URL", "\"https://ai.tudominio.com\"")
    }
    buildFeatures { buildConfig = true }
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    // Si prefieres Compose:
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
}
```

`AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

<application
    android:networkSecurityConfig="@xml/network_security_config"
    ... >
</application>
```

## 3. HTTP en red local (sin TLS)

Desde API 28 el cleartext está bloqueado. Crea
`res/xml/network_security_config.xml` **solo con tus IPs de desarrollo**:

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">10.0.2.2</domain>
        <domain includeSubdomains="true">127.0.0.1</domain>
        <domain includeSubdomains="true">192.168.1.50</domain>
    </domain-config>
</network-security-config>
```

En producción usa HTTPS (Caddy/Cloudflare Tunnel) y deja el cleartext apagado.

## 4. Código

Copia [`clients/kotlin/FreeAiClient.kt`](../clients/kotlin/FreeAiClient.kt).

### ViewModel con streaming

```kotlin
class ChatViewModel(private val api: FreeAiClient) : ViewModel() {
    private val _texto = MutableStateFlow("")
    val texto: StateFlow<String> = _texto

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private var job: Job? = null

    fun enviar(historial: List<ChatMessage>) {
        job?.cancel()
        _texto.value = ""
        _error.value = null
        job = viewModelScope.launch {
            api.chatStream(historial)
                .onEach { trozo -> _texto.value += trozo }
                .catch { e ->
                    _error.value = when (e) {
                        is RouterException -> e.message
                        else -> "Sin conexión con el router"
                    }
                }
                .collect()
        }
    }
}
```

### Compose

```kotlin
@Composable
fun ChatScreen(vm: ChatViewModel) {
    val texto by vm.texto.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text(texto.ifEmpty { "Escribe algo…" }, Modifier.weight(1f))
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(onClick = { vm.enviar(listOf(ChatMessage("user", "Hola"))) }) {
            Text("Enviar")
        }
    }
}
```

### Java clásico (sin corrutinas)

```java
OkHttpClient client = new OkHttpClient.Builder()
        .readTimeout(120, TimeUnit.SECONDS)
        .build();

JSONObject body = new JSONObject()
        .put("model", "auto")
        .put("messages", new JSONArray().put(
                new JSONObject().put("role", "user").put("content", "Hola")));

Request request = new Request.Builder()
        .url(BuildConfig.ROUTER_URL + "/v1/chat/completions")
        .header("Authorization", "Bearer " + BuildConfig.ROUTER_TOKEN)
        .post(RequestBody.create(body.toString(), MediaType.parse("application/json")))
        .build();

client.newCall(request).enqueue(new Callback() {
    @Override public void onFailure(Call call, IOException e) { runOnUiThread(() -> mostrar("Error: " + e.getMessage())); }
    @Override public void onResponse(Call call, Response response) throws IOException {
        // parsear JSON y actualizar la UI
    }
});
```

### SDK oficial de OpenAI (Java)

```java
OpenAIClient client = OpenAIClient.builder()
        .baseUrl("https://ai.tudominio.com/v1")
        .apiKey(System.getenv("ROUTER_TOKEN"))   // no lo incrustes en el APK
        .build();
```

Dentro del APK, cualquier SDK que acepte `baseUrl` funciona igual.

## 5. Seguridad del token

- `ROUTER_TOKEN` **no es una barrera fuerte** si va dentro del APK: se puede
  extraer. Sirve para evitar usos accidentales y para poder rotarlo.
- Opciones reales de protección:
  1. Router en el propio dispositivo (Termux) → no hay exposición de red.
  2. Router en VPS con HTTPS + token por dispositivo emitido por tu backend.
  3. Añadir delante un proxy con autenticación (Caddy `basicauth`, Cloudflare
     Access) y que la APK use credenciales de usuario.
- Rota `ROUTER_TOKEN` si publicas una versión del APK y luego cambias de plan.

## 6. Comportamiento en móvil

- **Streaming** (`"stream": true`) es clave: el primer token llega en cientos de
  ms aunque el proveedor tarde en generar todo.
- Usa `max_tokens` moderado (150–400) para ahorrar cuota y batería.
- Reintenta en el cliente **solo errores de red**. El router ya reintenta entre
  proveedores. Respeta `Retry-After` en los `429`.
- Cancela las peticiones al salir de pantalla (`job.cancel()` / `call.cancel()`);
  así no gastas cuota en respuestas que nadie verá.
- Guarda historial local (Room/DataStore) y no lo reenvíes entero cada vez:
  recorta a los últimos N mensajes.
- Dark mode y tipografía monoespaciada hacen la respuesta más legible; los
  modelos a veces devuelven markdown: usa `Markwon` o similar si lo necesitas.

## 7. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `CLEARTEXT communication not permitted` | HTTP en API 28+ | `network_security_config` (solo dev) o HTTPS |
| `Connection refused` | router en `127.0.0.1` | arranca con `--host 0.0.0.0` |
| `Failed to connect to /10.0.2.2` | emulador sin red al host | usa `10.0.2.2` y comprueba firewall |
| `401` | token distinto | revisa `ROUTER_TOKEN` en `.env` y en la app |
| Timeout en respuestas largas | `readTimeout` bajo | 120–180 s en OkHttp |
| El router muere en segundo plano | optimización de batería de Android | `termux-wake-lock`, foreground service o VPS |
| CORS en WebView | origen `file://`/`null` | `ALLOW_CORS=true` y sirve la consola desde el router |
