package com.kairu.phone.store

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import com.kairu.phone.link.Identity
import com.kairu.phone.link.Pc
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** One line of the conversation, as the phone shows it. who: you, kairu, note. */
data class ChatLine(val who: String, val text: String, val at: Long)

/**
 * What the phone keeps, in its own private storage (never backed up: allowBackup is off).
 * Its Link keys are sealed with an AES key held by Android's Keystore, which never leaves the phone's secure hardware.
 * The PC's public keys, the Gate topic and the conversation are kept as they are.
 */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("kairu", Context.MODE_PRIVATE)
    private val alias = "kairu-link-v1"

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    private fun seal(plain: ByteArray): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        return Base64.getEncoder().encodeToString(cipher.iv + cipher.doFinal(plain))
    }

    private fun unseal(text: String): ByteArray {
        val all = Base64.getDecoder().decode(text)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, all, 0, 12))
        return cipher.doFinal(all, 12, all.size - 12)
    }

    /** This phone's Link keys, made the first time they are needed. */
    fun identity(): Identity {
        prefs.getString("identity", null)?.let { sealed ->
            try {
                val raw = unseal(sealed)
                return Identity(raw.copyOfRange(0, 32), raw.copyOfRange(32, 64))
            } catch (error: Exception) {
                // the Keystore key is gone (for example after a restore): make new keys; the phone must pair again
                forgetPairing()
            }
        }
        val made = Identity.create()
        prefs.edit().putString("identity", seal(made.signSeed + made.boxPrivate)).apply()
        return made
    }

    // --- the pairing ------------------------------------------------------------------------------------

    val paired: Boolean get() = prefs.getString("topic", null) != null

    fun pc(): Pc? {
        val id = prefs.getString("pc_id", null) ?: return null
        val decoder = Base64.getDecoder()
        return Pc(id, decoder.decode(prefs.getString("pc_sign", "")), decoder.decode(prefs.getString("pc_box", "")))
    }

    val relay: String get() = prefs.getString("relay", "") ?: ""
    val topic: String get() = prefs.getString("topic", "") ?: ""
    val name: String get() = prefs.getString("name", "") ?: ""

    fun savePairing(pc: Pc, relay: String, topic: String, name: String, nowSeconds: Long) {
        val encoder = Base64.getEncoder()
        prefs.edit()
            .putString("pc_id", pc.id).putString("pc_sign", encoder.encodeToString(pc.sign)).putString("pc_box", encoder.encodeToString(pc.box))
            .putString("relay", relay).putString("topic", topic).putString("name", name).putLong("since", nowSeconds - 5)
            .apply()
    }

    /** Forget the PC, the conversation and this phone's keys: the next pairing starts fresh. */
    fun forgetPairing() {
        prefs.edit().clear().apply()
        try {
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(alias)
        } catch (error: Exception) {
        }
    }

    // --- reading the Gate -------------------------------------------------------------------------------

    var since: Long
        get() = prefs.getLong("since", System.currentTimeMillis() / 1000 - 60)
        set(value) = prefs.edit().putLong("since", value).apply()

    var lastSent: String?
        get() = prefs.getString("last_sent", null)
        set(value) = prefs.edit().putString("last_sent", value).apply()

    /** True the first time a PC message's nonce is seen; false for a replay. Nonces are kept 13 hours. */
    @Synchronized
    fun firstSight(nonce: String, nowMs: Long): Boolean {
        val seen = JSONObject(prefs.getString("seen", "{}") ?: "{}")
        if (seen.has(nonce)) return false
        val cutoff = nowMs - 13L * 3600 * 1000
        val keep = JSONObject()
        for (key in seen.keys()) if (seen.optLong(key) >= cutoff) keep.put(key, seen.optLong(key))
        keep.put(nonce, nowMs)
        prefs.edit().putString("seen", keep.toString()).apply()
        return true
    }

    // --- the conversation -------------------------------------------------------------------------------

    fun chat(): List<ChatLine> {
        val array = JSONArray(prefs.getString("chat", "[]") ?: "[]")
        return (0 until array.length()).map {
            val item = array.getJSONObject(it)
            ChatLine(item.getString("who"), item.getString("text"), item.getLong("at"))
        }
    }

    @Synchronized
    fun addChat(line: ChatLine) {
        val array = JSONArray(prefs.getString("chat", "[]") ?: "[]")
        array.put(JSONObject().put("who", line.who).put("text", line.text).put("at", line.at))
        val keep = JSONArray()
        val start = maxOf(0, array.length() - 200)
        for (index in start until array.length()) keep.put(array.get(index))
        prefs.edit().putString("chat", keep.toString()).apply()
    }
}
