# Cliente Android (Kotlin + OkHttp)

Copiar `FreeAiClient.kt` a `app/src/main/java/com/tuapp/network/` (ajusta el
`package`). Sin dependencias raras: solo OkHttp, corrutinas y `org.json`
(incluido en Android).

## 1. Dependencias

`app/build.gradle.kts`:

```kotlin
dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
```

Permisos en `AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
```

## 2. Usarlo

```kotlin
val api = FreeAiClient(
    baseUrl = "http://10.0.2.2:8080",   // emulador -> PC. Móvil real -> http://IP_LAN:8080
    routerToken = "el-mismo-ROUTER_TOKEN-del-.env",
    model = "auto",
)

lifecycleScope.launch {
    try {
        val respuesta = api.chat(
            listOf(
                ChatMessage("system", "Responde en español, breve."),
                ChatMessage("user", "¿Qué es un gateway de IA?"),
            )
        )
        Log.d("AI", "proveedor=${respuesta.provider} modelo=${respuesta.model}")
        textView.text = respuesta.content
    } catch (e: RouterException) {
        // e.message ya viene del router, en español, con los intentos en e.attempts
        textView.text = e.message
    }
}
```

### Streaming

```kotlin
lifecycleScope.launch {
    val buffer = StringBuilder()
    api.chatStream(listOf(ChatMessage("user", "Cuéntame un cuento corto")))
        .onEach { trozo ->
            buffer.append(trozo)
            textView.text = buffer.toString()
        }
        .catch { e -> textView.text = "Error: ${e.message}" }
        .collect()
}
```

### Cambiar modelo o consultar estado

```kotlin
val modelos = api.models()                 // ["auto", "groq/llama-3.3-70b-versatile", ...]
val estado = api.status()                  // JSON con proveedores, claves libres, cooldowns
val conGroq = api.withModel("groq/llama-3.3-70b-versatile")
```

## 3. HTTP sin TLS en la red local

Android bloquea `http://` desde API 28. Opciones:

**a) Solo para desarrollo**, `res/xml/network_security_config.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">10.0.2.2</domain>
        <domain includeSubdomains="true">192.168.1.50</domain>
    </domain-config>
</network-security-config>
```

Y en el manifest: `android:networkSecurityConfig="@xml/network_security_config"`.

**b) Producción**: pon el router detrás de HTTPS (Caddy/nginx/Cloudflare
Tunnel) y apunta la APK a `https://tu-dominio`. Ver `docs/DEPLOY.md`.

## 4. Buenas prácticas en la APK

- No incrustes `ROUTER_TOKEN` como único control: cualquiera puede extraerlo
  del APK. Úsalo para evitar usos accidentales, no como autenticación fuerte.
- Reintenta en el cliente solo errores de red (el router ya reintenta entre
  proveedores). Un `429` trae cabecera `Retry-After`.
- Si el router está en el propio móvil (Termux), usa `http://127.0.0.1:8080`.
- En segundo plano, Android puede matar el proceso del router: pide al usuario
  desactivar la optimización de batería o ejecuta el router en un VPS.
- Los tiempos de respuesta varían mucho entre proveedores: usa streaming para
  dar feedback inmediato.
