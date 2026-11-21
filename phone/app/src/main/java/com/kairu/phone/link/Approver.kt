package com.kairu.phone.link

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * This phone's fingerprint key (D2, PHONE.md, ADR-035): an Ed25519 key made inside Android's Keystore. Its private half
 * never leaves the phone's secure hardware, and it signs only right after a strong biometric (your fingerprint), once per
 * signature. The PC keeps its public half only after your "yes" and PIN at the PC, and then accepts its signature over
 * exactly one of this phone's High requests as that request's approval. A new fingerprint added to the phone ends the key.
 */
object Approver {
    private const val ALIAS = "kairu-approver-v1"
    private val X509_PREFIX = byteArrayOf(0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00)

    /** Ed25519 keys in the Keystore came with Android 13. */
    val supported: Boolean get() = Build.VERSION.SDK_INT >= 33

    private fun keyStore() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    val exists: Boolean get() = try {
        keyStore().containsAlias(ALIAS)
    } catch (error: Exception) {
        false
    }

    /** Make a new fingerprint key (replacing any old one); its raw 32-byte public key. Throws if the phone can't. */
    fun create(): ByteArray {
        keyStore().deleteEntry(ALIAS)
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("ed25519"))
            .setDigests(KeyProperties.DIGEST_NONE)
            .setUserAuthenticationRequired(true)
            .setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
            .setInvalidatedByBiometricEnrollment(true)
            .build()
        generator.initialize(spec)
        val encoded = generator.generateKeyPair().public.encoded
        return rawPublic(encoded)
    }

    fun rawPublic(encoded: ByteArray): ByteArray = when {
        encoded.size == 32 -> encoded
        encoded.size == 44 && encoded.copyOfRange(0, 12).contentEquals(X509_PREFIX) -> encoded.copyOfRange(12, 44)
        else -> throw IllegalStateException("the Keystore gave a key Kairu doesn't know")
    }

    /** A Signature ready to sign once a fingerprint unlocks it (BiometricPrompt.CryptoObject). */
    fun signer(): Signature {
        val key = keyStore().getKey(ALIAS, null) as? PrivateKey ?: throw IllegalStateException("no fingerprint key")
        return Signature.getInstance("Ed25519").apply { initSign(key) }
    }

    fun forget() {
        try {
            keyStore().deleteEntry(ALIAS)
        } catch (error: Exception) {
        }
    }

    /** What the fingerprint signs for one request: the same text the PC builds (kairu/link/approver.py, statement). */
    fun statement(device: String, number: Int, fingerprint: String, expires: Long): ByteArray =
        "kairu-approve-v1|$device|$number|$fingerprint|$expires".toByteArray(Charsets.US_ASCII)
}
