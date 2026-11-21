package com.kairu.phone.link

import org.json.JSONObject
import java.util.Base64

/** Why something from the PC, or a pairing offer, was refused. Its text is shown to the owner. */
class LinkError(message: String) : Exception(message)

/** This phone's own Kairu Link keys. Its id is made from its signing key, as the PC makes it (kairu/link/keys.py). */
class Identity(val signSeed: ByteArray, val boxPrivate: ByteArray) {
    val signPublic: ByteArray = Crypto.ed25519Public(signSeed)
    val boxPublic: ByteArray = Crypto.x25519Public(boxPrivate)
    val id: String = deviceId(signPublic, "dev")

    companion object {
        fun create() = Identity(Crypto.randomBytes(32), Crypto.randomBytes(32))
    }
}

/** The paired PC: its id and its two public keys. */
class Pc(val id: String, val sign: ByteArray, val box: ByteArray)

/** What a pairing QR code holds (kairu/link/pairing.py, offer_text). */
class Offer(val pc: Pc, val topic: String, val relay: String, val expires: Long)

/** A checked message from the PC. Only text to show: the phone acts on nothing it receives. */
class Incoming(val type: String, val body: String, val ts: Long, val nonce: String)

fun deviceId(signPublic: ByteArray, prefix: String): String = "$prefix-" + Crypto.hex(Crypto.sha256(signPublic)).substring(0, 16)

object Link {
    const val PREFIX = "kairu-pair:1:"
    val TYPES = setOf("command", "mission", "status", "call_request", "doubt", "report", "ask")
    val TIERS = setOf("Low", "Medium", "High", "Critical")
    private val DEVICE_ID = Regex("(pc|dev)-[0-9a-f]{16}")
    private val TOPIC = Regex("[0-9a-f]{32}")
    private val NONCE = Regex("[0-9a-f]{32}")
    const val MAX_BODY_BYTES = 2000
    const val MAX_ENVELOPE_BYTES = 4000
    private const val OLDEST_MS = 12L * 3600 * 1000
    private const val FUTURE_MS = 5L * 60 * 1000

    private fun b64(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)
    private fun unb64(text: String): ByteArray = try {
        Base64.getDecoder().decode(text)
    } catch (error: IllegalArgumentException) {
        throw LinkError("not a Kairu Link message")
    }

    fun newNonce(): String = Crypto.hex(Crypto.randomBytes(16))

    // --- pairing ----------------------------------------------------------------------------------------

    fun readOffer(text: String): Offer {
        val trimmed = text.trim()
        if (!trimmed.startsWith(PREFIX)) throw LinkError("That isn't a Kairu pairing code. Run kairu device pair on your PC.")
        val data = try {
            JSONObject(String(Base64.getUrlDecoder().decode(trimmed.removePrefix(PREFIX)), Charsets.UTF_8))
        } catch (error: Exception) {
            throw LinkError("That pairing code is cut off. Scan it again.")
        }
        try {
            val pc = Pc(data.getString("pc"), unb64(data.getString("sign")), unb64(data.getString("box")))
            val offer = Offer(pc, data.getString("topic"), data.getString("relay"), data.getLong("expires"))
            if (!DEVICE_ID.matches(pc.id) || !pc.id.startsWith("pc-") || pc.sign.size != 32 || pc.box.size != 32 ||
                !TOPIC.matches(offer.topic) || !(offer.relay.startsWith("https://") || offer.relay.startsWith("http://"))
            ) throw LinkError("That pairing code isn't right. Run kairu device pair again.")
            if (deviceId(pc.sign, "pc") != pc.id) throw LinkError("That pairing code's keys don't match its PC.")
            return offer
        } catch (error: org.json.JSONException) {
            throw LinkError("That pairing code isn't complete. Run kairu device pair again.")
        }
    }

    fun proof(code: String, pc: String, device: String, sign: String, box: String, nonce: String): String =
        Crypto.hmacSha256Hex(code.toByteArray(), "kairu-pair-v1|$pc|$device|$sign|$box|$nonce".toByteArray())

    /** The pairing request: this phone's public keys and name, and proof that it knows the code; signed, encrypted to the PC. */
    fun pairRequest(me: Identity, offer: Offer, code: String, name: String, nowMs: Long): String {
        val nonce = newNonce()
        val sign = b64(me.signPublic)
        val box = b64(me.boxPublic)
        val payload = JSONObject()
            .put("type", "pair").put("from", me.id).put("to", offer.pc.id).put("name", name).put("sign", sign).put("box", box)
            .put("ts", nowMs).put("nonce", nonce).put("proof", proof(code, offer.pc.id, me.id, sign, box, nonce))
            .toString().toByteArray(Charsets.UTF_8)
        val boxed = Crypto.boxEncrypt(me.boxPrivate, offer.pc.box, Crypto.sign(me.signSeed, payload) + payload)
        return JSONObject().put("v", 1).put("pair", me.id).put("to", offer.pc.id).put("key", box).put("box", b64(boxed)).toString()
    }

    /** The topic of the PC's "paired" report, or null if this message is something else. */
    fun pairedTopic(message: Incoming, pc: Pc): String? {
        if (message.type != "report") return null
        return try {
            val paired = JSONObject(message.body).optJSONObject("paired") ?: return null
            val topic = paired.getString("topic")
            if (paired.getString("pc") == pc.id && TOPIC.matches(topic)) topic else null
        } catch (error: org.json.JSONException) {
            null
        }
    }

    // --- messages ---------------------------------------------------------------------------------------

    /** One message to the PC: signed with this phone's key, encrypted to the PC's (kairu/link/message.py, seal). */
    fun seal(me: Identity, pc: Pc, kind: String, body: String, nowMs: Long, tier: String = "Low", nonce: String = newNonce()): String {
        require(kind in TYPES && tier in TIERS)
        if (body.toByteArray(Charsets.UTF_8).size > MAX_BODY_BYTES) throw LinkError("That's too long for one message.")
        val payload = JSONObject()
            .put("from", me.id).put("to", pc.id).put("type", kind).put("tier", tier).put("ts", nowMs).put("nonce", nonce).put("body", body)
            .toString().toByteArray(Charsets.UTF_8)
        val boxed = Crypto.boxEncrypt(me.boxPrivate, pc.box, Crypto.sign(me.signSeed, payload) + payload)
        val envelope = JSONObject().put("v", 1).put("from", me.id).put("to", pc.id).put("box", b64(boxed)).toString()
        if (envelope.length > MAX_ENVELOPE_BYTES) throw LinkError("That's too long for one message.")
        return envelope
    }

    /** Who an envelope says it is from, unchecked: only to skip this phone's own messages on the shared topic. */
    fun senderOf(envelope: String): String? = try {
        JSONObject(envelope).optString("from").ifEmpty { null }
    } catch (error: org.json.JSONException) {
        null
    }

    /** A message from the paired PC, checked as the PC checks the phone's. Throws LinkError why not. The caller checks replays. */
    fun open(envelope: String, me: Identity, pc: Pc, nowMs: Long): Incoming {
        if (envelope.length > MAX_ENVELOPE_BYTES) throw LinkError("too long")
        val outer = try {
            JSONObject(envelope)
        } catch (error: org.json.JSONException) {
            throw LinkError("not a Kairu Link message")
        }
        val keys = outer.keys().asSequence().toSet()
        if (keys != setOf("v", "from", "to", "box") || outer.optInt("v") != 1) throw LinkError("not a Kairu Link message")
        if (outer.optString("from") != pc.id) throw LinkError("not from your PC")
        if (outer.optString("to") != me.id) throw LinkError("not for this phone")
        val signed = Crypto.boxDecrypt(me.boxPrivate, pc.box, unb64(outer.optString("box")))
            ?: throw LinkError("it doesn't open: changed on the way")
        if (signed.size <= 64) throw LinkError("it doesn't open: changed on the way")
        val signature = signed.copyOfRange(0, 64)
        val payloadBytes = signed.copyOfRange(64, signed.size)
        if (!Crypto.verify(pc.sign, payloadBytes, signature)) throw LinkError("your PC's signature doesn't match")
        val payload = try {
            JSONObject(String(payloadBytes, Charsets.UTF_8))
        } catch (error: org.json.JSONException) {
            throw LinkError("not a Kairu Link message")
        }
        val type = payload.optString("type")
        val nonce = payload.optString("nonce")
        val ts = payload.optLong("ts", -1)
        if (payload.optString("from") != pc.id || payload.optString("to") != me.id || type !in TYPES ||
            !NONCE.matches(nonce) || ts < 0 || !payload.has("body")
        ) throw LinkError("its parts don't agree")
        if (nowMs - ts > OLDEST_MS) throw LinkError("too old")
        if (ts - nowMs > FUTURE_MS) throw LinkError("dated in the future")
        return Incoming(type, payload.getString("body"), ts, nonce)
    }
}
