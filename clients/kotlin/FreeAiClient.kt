package com.apk2.router

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Cliente mínimo para Free AI Router.
 *
 * Dependencias (app/build.gradle.kts):
 *   implementation("com.squareup.okhttp3:okhttp:4.12.0")
 *   implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
 *
 * La API es compatible con OpenAI, así que también puedes usar cualquier SDK
 * de OpenAI apuntando baseUrl = "http://IP:8080/v1".
 */
data class ChatMessage(val role: String, val content: String) {
    fun toJson(): JSONObject = JSONObject().put("role", role).put("content", content)
}

data class ChatResult(
    val content: String,
    val provider: String?,
    val model: String?,
    val attempts: Int,
    val latencyMs: Long,
)

class RouterException(
    message: String,
    val status: Int = 0,
    val code: String? = null,
    val attempts: List<String> = emptyList(),
) : IOException(message)

class FreeAiClient(
    private val baseUrl: String,
    private val routerToken: String? = null,
    private val model: String = "auto",
    private val client: OkHttpClient = defaultClient(),
    private val maxTokens: Int? = null,
    private val temperature: Double? = null,
) {
    companion object {
        private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(180, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

    fun withModel(newModel: String): FreeAiClient =
        FreeAiClient(baseUrl, routerToken, newModel, client, maxTokens, temperature)

    private fun url(path: String): String = baseUrl.trimEnd('/') + path

    private fun requestBuilder(path: String, accept: String = "application/json"): Request.Builder {
        val builder = Request.Builder().url(url(path)).header("Accept", accept)
        routerToken?.takeIf { it.isNotBlank() }?.let { builder.header("Authorization", "Bearer $it") }
        return builder
    }

    private fun payload(messages: List<ChatMessage>, stream: Boolean): JSONObject {
        val array = JSONArray()
        messages.forEach { array.put(it.toJson()) }
        return JSONObject()
            .put("model", model)
            .put("messages", array)
            .put("stream", stream)
            .apply {
                maxTokens?.let { put("max_tokens", it) }
                temperature?.let { put("temperature", it) }
            }
    }

    /** Petición normal (sin streaming). */
    suspend fun chat(messages: List<ChatMessage>): ChatResult = withContext(Dispatchers.IO) {
        val request = requestBuilder("/v1/chat/completions")
            .post(payload(messages, stream = false).toString().toRequestBody(JSON_MEDIA))
            .build()

        client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw errorFrom(response.code, raw)

            val json = JSONObject(raw)
            val content = json.optJSONArray("choices")
                ?.optJSONObject(0)
                ?.optJSONObject("message")
                ?.optString("content")
                .orEmpty()

            ChatResult(
                content = content,
                provider = response.header("x-router-provider"),
                model = response.header("x-router-model"),
                attempts = response.header("x-router-attempts")?.toIntOrNull() ?: 1,
                latencyMs = response.header("x-router-latency-ms")?.toLongOrNull() ?: 0L,
            )
        }
    }

    /**
     * Streaming token a token. Emite fragmentos de texto y termina al recibir [DONE].
     *
     *   client.chatStream(listOf(ChatMessage("user", "Hola")))
     *       .catch { e -> ... }
     *       .collect { trozo -> texto += trozo }
     */
    fun chatStream(messages: List<ChatMessage>): Flow<String> = callbackFlow {
        val request = requestBuilder("/v1/chat/completions", accept = "text/event-stream")
            .post(payload(messages, stream = true).toString().toRequestBody(JSON_MEDIA))
            .build()

        val call = client.newCall(request)
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                close(e)
            }

            override fun onResponse(call: Call, response: Response) {
                response.use { resp ->
                    if (!resp.isSuccessful) {
                        close(errorFrom(resp.code, resp.body?.string().orEmpty()))
                        return
                    }
                    val source = resp.body?.source()
                    if (source == null) {
                        close(RouterException("Respuesta vacía del router"))
                        return
                    }
                    try {
                        while (!source.exhausted()) {
                            val line = source.readUtf8Line() ?: break
                            if (!line.startsWith("data:")) continue
                            val data = line.removePrefix("data:").trim()
                            if (data.isEmpty() || data == "[DONE]") continue
                            val delta = JSONObject(data)
                                .optJSONArray("choices")
                                ?.optJSONObject(0)
                                ?.optJSONObject("delta")
                                ?.optString("content")
                                .orEmpty()
                            if (delta.isNotEmpty()) trySend(delta)
                        }
                        close()
                    } catch (e: Exception) {
                        close(e)
                    }
                }
            }
        })

        awaitClose { call.cancel() }
    }

    /** Lista de modelos disponibles (incluye "auto" y "proveedor/modelo"). */
    suspend fun models(): List<String> = withContext(Dispatchers.IO) {
        val request = requestBuilder("/v1/models").get().build()
        client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw errorFrom(response.code, raw)
            val array = JSONObject(raw).optJSONArray("data") ?: JSONArray()
            buildList {
                for (index in 0 until array.length()) {
                    val id = array.optJSONObject(index)?.optString("id").orEmpty()
                    if (id.isNotEmpty()) add(id)
                }
            }
        }
    }

    /** Estado de proveedores/claves (sin secretos). */
    suspend fun status(): JSONObject = withContext(Dispatchers.IO) {
        val request = requestBuilder("/v1/router/status").get().build()
        client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw errorFrom(response.code, raw)
            JSONObject(raw)
        }
    }

    private fun errorFrom(status: Int, raw: String): RouterException {
        var message = "Error HTTP $status"
        var code: String? = null
        val attempts = mutableListOf<String>()
        try {
            val error = JSONObject(raw).optJSONObject("error")
            if (error != null) {
                message = error.optString("message", message)
                code = error.optString("code").takeIf { it.isNotEmpty() }
                val list = error.optJSONObject("router")?.optJSONArray("attempts")
                if (list != null) {
                    for (index in 0 until list.length()) {
                        val item = list.optJSONObject(index) ?: continue
                        val provider = item.optString("provider")
                        val kind = item.optString("kind").ifEmpty { item.optString("status") }
                        attempts += "$provider: $kind"
                    }
                }
            }
        } catch (_: Exception) {
            // El cuerpo no era JSON: nos quedamos con el mensaje genérico.
        }
        return RouterException(message, status, code, attempts)
    }
}
