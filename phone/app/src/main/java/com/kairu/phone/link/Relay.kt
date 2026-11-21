package com.kairu.phone.link

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL

/** One message from the Gate: its id, when the Gate got it (seconds), and the envelope. */
class GateEvent(val id: String, val time: Long, val message: String)

class RelayError(message: String) : Exception(message)

/**
 * The Gate's relay, an ntfy server (kairu/link/relay.py): POST {relay}/{topic} sends one envelope; GET
 * {relay}/{topic}/json?since=T reads what waited since T, then each new one as it comes. Messages go with
 * "Firebase: no", as the PC sends them. Blocking calls: run them off the main thread.
 */
class Relay(base: String) {
    private val base = base.trimEnd('/')
    private val topicPattern = Regex("[0-9a-f]{32}")

    init {
        if (!(this.base.startsWith("https://") || this.base.startsWith("http://"))) throw RelayError("not a relay address")
    }

    fun publish(topic: String, text: String) {
        require(topicPattern.matches(topic))
        var attempt = 0
        while (true) {
            val connection = URL("$base/$topic").openConnection() as HttpURLConnection
            try {
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.connectTimeout = 15_000
                connection.readTimeout = 20_000
                connection.setRequestProperty("User-Agent", "kairu-phone/1")
                connection.setRequestProperty("Content-Type", "text/plain; charset=utf-8")
                connection.setRequestProperty("Firebase", "no")
                connection.outputStream.use { it.write(text.toByteArray(Charsets.UTF_8)) }
                val status = connection.responseCode
                if (status == 200) return
                if (status == 429 && attempt < 3) {
                    attempt++
                    Thread.sleep(((connection.getHeaderField("Retry-After")?.toLongOrNull() ?: (5L * attempt)) * 1000).coerceAtMost(30_000))
                    continue
                }
                throw RelayError("the Gate answered HTTP $status")
            } catch (error: java.io.IOException) {
                throw RelayError("can't reach the Gate (${error.javaClass.simpleName})")
            } finally {
                connection.disconnect()
            }
        }
    }

    /**
     * Reads the topic since `since` (seconds) and calls onEvent for each message, until the connection ends,
     * goes quiet past the 45-second keepalive, or keepGoing() turns false. Throws RelayError if it can't connect.
     */
    fun listen(topic: String, since: Long, keepGoing: () -> Boolean, onEvent: (GateEvent) -> Unit) {
        require(topicPattern.matches(topic))
        val connection = URL("$base/$topic/json?since=$since").openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 15_000
            connection.readTimeout = 70_000
            connection.setRequestProperty("User-Agent", "kairu-phone/1")
            val status = try {
                connection.responseCode
            } catch (error: java.io.IOException) {
                throw RelayError("can't reach the Gate (${error.javaClass.simpleName})")
            }
            if (status != 200) throw RelayError("the Gate answered HTTP $status")
            BufferedReader(InputStreamReader(connection.inputStream, Charsets.UTF_8)).use { reader ->
                while (keepGoing()) {
                    val line = try {
                        reader.readLine()
                    } catch (error: SocketTimeoutException) {
                        return
                    } catch (error: java.io.IOException) {
                        return
                    } ?: return
                    val event = try {
                        JSONObject(line)
                    } catch (error: org.json.JSONException) {
                        continue
                    }
                    if (event.optString("event") != "message") continue
                    val message = event.optString("message")
                    val id = event.optString("id")
                    if (message.isEmpty() || id.isEmpty() || message.length > Link.MAX_ENVELOPE_BYTES) continue
                    onEvent(GateEvent(id, event.optLong("time"), message))
                }
            }
        } finally {
            connection.disconnect()
        }
    }
}
