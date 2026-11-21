package com.kairu.phone.link

import org.bouncycastle.crypto.agreement.X25519Agreement
import org.bouncycastle.crypto.macs.Poly1305
import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters
import org.bouncycastle.crypto.params.KeyParameter
import org.bouncycastle.crypto.params.X25519PrivateKeyParameters
import org.bouncycastle.crypto.params.X25519PublicKeyParameters
import org.bouncycastle.crypto.signers.Ed25519Signer
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Kairu Link's crypto, exactly as the PC does it with libsodium (kairu/link/message.py, LINK.md):
 * Ed25519 signatures, and crypto_box = X25519 + HSalsa20 + XSalsa20-Poly1305 with a random 24-byte nonce,
 * laid out as nonce (24) + Poly1305 tag (16) + ciphertext. Checked against vectors made with PyNaCl (LinkCryptoTest).
 */
object Crypto {
    private val random = SecureRandom()
    private val SIGMA = intArrayOf(0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)

    fun randomBytes(count: Int): ByteArray = ByteArray(count).also { random.nextBytes(it) }

    fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 0xFF) }

    fun sha256(bytes: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(bytes)

    fun hmacSha256Hex(key: ByteArray, text: ByteArray): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return hex(mac.doFinal(text))
    }

    // --- Ed25519 ---------------------------------------------------------------------------------------

    fun ed25519Public(seed: ByteArray): ByteArray = Ed25519PrivateKeyParameters(seed, 0).generatePublicKey().encoded

    fun sign(seed: ByteArray, message: ByteArray): ByteArray {
        val signer = Ed25519Signer()
        signer.init(true, Ed25519PrivateKeyParameters(seed, 0))
        signer.update(message, 0, message.size)
        return signer.generateSignature()
    }

    fun verify(public: ByteArray, message: ByteArray, signature: ByteArray): Boolean {
        if (public.size != 32 || signature.size != 64) return false
        return try {
            val verifier = Ed25519Signer()
            verifier.init(false, Ed25519PublicKeyParameters(public, 0))
            verifier.update(message, 0, message.size)
            verifier.verifySignature(signature)
        } catch (error: Exception) {
            false
        }
    }

    // --- X25519 and crypto_box -------------------------------------------------------------------------

    fun x25519Public(private: ByteArray): ByteArray = X25519PrivateKeyParameters(private, 0).generatePublicKey().encoded

    private fun shared(private: ByteArray, public: ByteArray): ByteArray {
        require(public.size == 32) { "a public key is 32 bytes" }
        val secret = ByteArray(32)
        X25519Agreement().apply { init(X25519PrivateKeyParameters(private, 0)) }
            .calculateAgreement(X25519PublicKeyParameters(public, 0), secret, 0)  // throws on an all-zero result
        return hsalsa20(secret, ByteArray(16))
    }

    fun boxEncrypt(private: ByteArray, public: ByteArray, message: ByteArray, nonce: ByteArray = randomBytes(24)): ByteArray {
        require(nonce.size == 24)
        val stream = xsalsa20Stream(shared(private, public), nonce, 32 + message.size)
        val cipher = ByteArray(message.size) { (message[it].toInt() xor stream[32 + it].toInt()).toByte() }
        return nonce + poly1305(stream.copyOfRange(0, 32), cipher) + cipher
    }

    /** The message, or null if it does not open (changed on the way, or not for this key). */
    fun boxDecrypt(private: ByteArray, public: ByteArray, data: ByteArray): ByteArray? {
        if (data.size < 40) return null
        val nonce = data.copyOfRange(0, 24)
        val tag = data.copyOfRange(24, 40)
        val cipher = data.copyOfRange(40, data.size)
        val stream = try {
            xsalsa20Stream(shared(private, public), nonce, 32 + cipher.size)
        } catch (error: Exception) {
            return null
        }
        if (!MessageDigest.isEqual(poly1305(stream.copyOfRange(0, 32), cipher), tag)) return null
        return ByteArray(cipher.size) { (cipher[it].toInt() xor stream[32 + it].toInt()).toByte() }
    }

    private fun poly1305(key: ByteArray, message: ByteArray): ByteArray {
        val mac = Poly1305()
        mac.init(KeyParameter(key))
        mac.update(message, 0, message.size)
        return ByteArray(16).also { mac.doFinal(it, 0) }
    }

    // --- Salsa20 ---------------------------------------------------------------------------------------

    private fun rotl(value: Int, shift: Int) = (value shl shift) or (value ushr (32 - shift))

    private fun le32(bytes: ByteArray, at: Int) = (bytes[at].toInt() and 0xFF) or ((bytes[at + 1].toInt() and 0xFF) shl 8) or
        ((bytes[at + 2].toInt() and 0xFF) shl 16) or ((bytes[at + 3].toInt() and 0xFF) shl 24)

    private fun put32(bytes: ByteArray, at: Int, value: Int) {
        bytes[at] = value.toByte()
        bytes[at + 1] = (value ushr 8).toByte()
        bytes[at + 2] = (value ushr 16).toByte()
        bytes[at + 3] = (value ushr 24).toByte()
    }

    private fun state(key: ByteArray, sixteen: ByteArray): IntArray {
        val k = IntArray(8) { le32(key, it * 4) }
        val i = IntArray(4) { le32(sixteen, it * 4) }
        return intArrayOf(SIGMA[0], k[0], k[1], k[2], k[3], SIGMA[1], i[0], i[1], i[2], i[3], SIGMA[2], k[4], k[5], k[6], k[7], SIGMA[3])
    }

    private fun core(input: IntArray, add: Boolean): IntArray {
        val x = input.copyOf()
        fun quarter(a: Int, b: Int, c: Int, d: Int) {
            x[b] = x[b] xor rotl(x[a] + x[d], 7)
            x[c] = x[c] xor rotl(x[b] + x[a], 9)
            x[d] = x[d] xor rotl(x[c] + x[b], 13)
            x[a] = x[a] xor rotl(x[d] + x[c], 18)
        }
        repeat(10) {
            quarter(0, 4, 8, 12); quarter(5, 9, 13, 1); quarter(10, 14, 2, 6); quarter(15, 3, 7, 11)
            quarter(0, 1, 2, 3); quarter(5, 6, 7, 4); quarter(10, 11, 8, 9); quarter(15, 12, 13, 14)
        }
        if (add) for (j in 0 until 16) x[j] += input[j]
        return x
    }

    fun hsalsa20(key: ByteArray, sixteen: ByteArray): ByteArray {
        val x = core(state(key, sixteen), add = false)
        val out = ByteArray(32)
        intArrayOf(x[0], x[5], x[10], x[15], x[6], x[7], x[8], x[9]).forEachIndexed { index, word -> put32(out, index * 4, word) }
        return out
    }

    private fun xsalsa20Stream(key: ByteArray, nonce: ByteArray, length: Int): ByteArray {
        val subkey = hsalsa20(key, nonce.copyOfRange(0, 16))
        val out = ByteArray(length)
        val block = ByteArray(16)
        nonce.copyInto(block, 0, 16, 24)
        var counter = 0L
        var written = 0
        while (written < length) {
            for (j in 0 until 8) block[8 + j] = (counter ushr (8 * j)).toByte()
            val words = core(state(subkey, block), add = true)
            val bytes = ByteArray(64)
            words.forEachIndexed { index, word -> put32(bytes, index * 4, word) }
            val take = minOf(64, length - written)
            bytes.copyInto(out, written, 0, take)
            written += take
            counter++
        }
        return out
    }
}
