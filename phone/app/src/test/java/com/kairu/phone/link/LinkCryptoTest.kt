package com.kairu.phone.link

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.util.Base64

/**
 * The phone's Kairu Link against the PC's own: link-vectors.json was made with PyNaCl and kairu/link on the PC
 * (fixed keys and nonces), so these tests show the phone signs, encrypts, opens and pairs byte for byte as the PC does.
 */
class LinkCryptoTest {
    private val v = JSONObject(javaClass.classLoader!!.getResource("link-vectors.json")!!.readText())
    private fun bytes(name: String): ByteArray = Base64.getDecoder().decode(v.getString(name))

    private val phone = Identity(bytes("phone_sign_seed"), bytes("phone_box_private"))
    private val pc = Pc(v.getString("pc_id"), bytes("pc_sign_public"), bytes("pc_box_public"))

    @Test fun publicKeysAndIdsMatchThePc() {
        assertArrayEquals(bytes("phone_sign_public"), phone.signPublic)
        assertArrayEquals(bytes("phone_box_public"), phone.boxPublic)
        assertEquals(v.getString("phone_id"), phone.id)
        assertEquals(v.getString("pc_id"), deviceId(bytes("pc_sign_public"), "pc"))
    }

    @Test fun signaturesMatchLibsodium() {
        assertArrayEquals(bytes("phone_signature"), Crypto.sign(phone.signSeed, bytes("message")))
        assertTrue(Crypto.verify(phone.signPublic, bytes("message"), bytes("phone_signature")))
        val changed = bytes("message").also { it[0] = (it[0] + 1).toByte() }
        assertTrue(!Crypto.verify(phone.signPublic, changed, bytes("phone_signature")))
    }

    @Test fun cryptoBoxMatchesLibsodiumBothWays() {
        val sealed = Crypto.boxEncrypt(phone.boxPrivate, bytes("pc_box_public"), bytes("message"), bytes("nonce"))
        assertArrayEquals(bytes("box_phone_to_pc"), sealed)
        assertArrayEquals(bytes("message"), Crypto.boxDecrypt(bytes("pc_box_private"), phone.boxPublic, sealed))
        val tampered = sealed.copyOf().also { it[50] = (it[50].toInt() xor 1).toByte() }
        assertNull(Crypto.boxDecrypt(bytes("pc_box_private"), phone.boxPublic, tampered))
    }

    @Test fun aMessageSealedByThePcOpens() {
        val message = Link.open(v.getString("pc_envelope"), phone, pc, v.getLong("pc_envelope_now_ms"))
        assertEquals("report", message.type)
        assertEquals("Hi from your PC", message.body)
        assertEquals("0".repeat(31) + "1", message.nonce)
    }

    @Test fun aChangedOrMisdirectedMessageIsRefused() {
        val envelope = JSONObject(v.getString("pc_envelope"))
        val box = Base64.getDecoder().decode(envelope.getString("box")).also { it[60] = (it[60].toInt() xor 1).toByte() }
        refused(envelope.put("box", Base64.getEncoder().encodeToString(box)).toString())
        refused(JSONObject(v.getString("pc_envelope")).put("to", "dev-0000000000000000").toString())
        refused(JSONObject(v.getString("pc_envelope")).put("from", "pc-0000000000000000").toString())
        refused("not json")
        try {
            Link.open(v.getString("pc_envelope"), phone, pc, v.getLong("pc_envelope_now_ms") + 13L * 3600 * 1000)
            fail("a message 13 hours old should be refused")
        } catch (expected: LinkError) {
        }
    }

    private fun refused(envelope: String) {
        try {
            Link.open(envelope, phone, pc, v.getLong("pc_envelope_now_ms"))
            fail("should be refused: $envelope")
        } catch (expected: LinkError) {
        }
    }

    @Test fun whatThePhoneSealsThePcCanOpenAndVerify() {
        val envelope = JSONObject(Link.seal(phone, pc, "ask", "who is the prime minister of India", 1_762_850_000_000))
        assertEquals(setOf("v", "from", "to", "box"), envelope.keys().asSequence().toSet())
        assertEquals(phone.id, envelope.getString("from"))
        val signed = Crypto.boxDecrypt(bytes("pc_box_private"), phone.boxPublic, Base64.getDecoder().decode(envelope.getString("box")))!!
        val payload = signed.copyOfRange(64, signed.size)
        assertTrue(Crypto.verify(phone.signPublic, payload, signed.copyOfRange(0, 64)))
        val inner = JSONObject(String(payload, Charsets.UTF_8))
        assertEquals(setOf("from", "to", "type", "tier", "ts", "nonce", "body"), inner.keys().asSequence().toSet())
        assertEquals("ask", inner.getString("type"))
        assertEquals("Low", inner.getString("tier"))
        assertEquals(1_762_850_000_000, inner.getLong("ts"))
        assertTrue(Regex("[0-9a-f]{32}").matches(inner.getString("nonce")))
    }

    @Test fun thePairingProofAndOfferMatchThePc() {
        assertEquals(
            v.getString("proof"),
            Link.proof(v.getString("proof_code"), pc.id, phone.id, v.getString("phone_sign_public"), v.getString("phone_box_public"), v.getString("proof_nonce")),
        )
        val offer = Link.readOffer(v.getString("offer"))
        assertEquals(pc.id, offer.pc.id)
        assertArrayEquals(pc.box, offer.pc.box)
        assertEquals("c".repeat(32), offer.topic)
        assertEquals("https://ntfy.sh", offer.relay)
        assertEquals(1_762_850_600L, offer.expires)
    }

    @Test fun aPairingRequestOpensOnThePcSide() {
        val offer = Link.readOffer(v.getString("offer"))
        val request = JSONObject(Link.pairRequest(phone, offer, "123456", "Mivi", 1_762_850_000_000))
        assertEquals(setOf("v", "pair", "to", "key", "box"), request.keys().asSequence().toSet())
        val signed = Crypto.boxDecrypt(bytes("pc_box_private"), Base64.getDecoder().decode(request.getString("key")),
            Base64.getDecoder().decode(request.getString("box")))!!
        val payload = signed.copyOfRange(64, signed.size)
        assertTrue(Crypto.verify(phone.signPublic, payload, signed.copyOfRange(0, 64)))
        val inner = JSONObject(String(payload, Charsets.UTF_8))
        assertEquals(setOf("type", "from", "to", "name", "sign", "box", "ts", "nonce", "proof"), inner.keys().asSequence().toSet())
        assertEquals(
            Link.proof("123456", pc.id, phone.id, inner.getString("sign"), inner.getString("box"), inner.getString("nonce")),
            inner.getString("proof"),
        )
    }

    @Test fun otherPairingTextIsRefused() {
        for (text in listOf("hello", "kairu-pair:1:!!!", "kairu-pair:1:" + Base64.getUrlEncoder().encodeToString("{}".toByteArray()))) {
            try {
                Link.readOffer(text)
                fail("should be refused: $text")
            } catch (expected: LinkError) {
            }
        }
    }

    @Test fun theFingerprintStatementIsTheOneThePcChecks() {
        assertEquals(v.getString("approve_statement"), String(Approver.statement(phone.id, 7, "f".repeat(64), 1_762_850_600L), Charsets.US_ASCII))
    }

    @Test fun androidsX509KeyFormIsReadAsTheRawKey() {
        val prefix = byteArrayOf(0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00)
        assertArrayEquals(phone.signPublic, Approver.rawPublic(prefix + phone.signPublic))
        assertArrayEquals(phone.signPublic, Approver.rawPublic(phone.signPublic))
    }
}
