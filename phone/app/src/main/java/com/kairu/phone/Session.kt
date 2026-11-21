package com.kairu.phone

import android.content.Context
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import com.kairu.phone.store.ChatLine
import com.kairu.phone.store.Store
import com.kairu.phone.link.Link
import com.kairu.phone.link.LinkError
import com.kairu.phone.link.Relay
import com.kairu.phone.link.RelayError
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The phone's side of Kairu Link (PHONE.md, D1). Everything it sends is a request: the PC's Guardian decides
 * what, if anything, happens. Everything it receives is text to show; the phone acts on none of it.
 */
class Session(context: Context) {
    private val app = context.applicationContext
    val store = Store(app)
    val paired = mutableStateOf(store.paired)
    val lines = mutableStateListOf<ChatLine>().apply { addAll(store.chat()) }
    val gate = mutableStateOf("Connecting")  // Connecting, Listening, or why it can't
    val waiting = mutableStateOf(false)  // a question is on its way, and no answer has come yet
    val answered = mutableStateListOf<Int>()  // cards already approved or refused here

    private fun now() = System.currentTimeMillis()

    private fun add(line: ChatLine) {
        store.addChat(line)
        lines.add(line)
        if (speakNext && line.who == "kairu" && contactsAsk.value == null) {  // D6: after a spoken order, the answer is spoken
            speakNext = false
            speak(line.text)
        }
    }

    // --- D6: speaking the answer to a spoken order ----------------------------------------------------------

    private var speakNext = false
    private var voice: android.speech.tts.TextToSpeech? = null
    private var ready = false
    private var pending: String? = null

    /** The next answer from Kairu (on the phone or from the PC) is spoken aloud, once. */
    fun speakNextAnswer() {
        speakNext = true
        if (voice == null) voice = android.speech.tts.TextToSpeech(app) { status ->
            ready = status == android.speech.tts.TextToSpeech.SUCCESS
            if (ready) {
                voice?.language = java.util.Locale("en", "IN")
                pending?.let { speak(it) }
            }
            pending = null
        }
    }

    /** D6: goes up by one each time a spoken answer has finished, so the chat screen can listen again (talk in a loop). */
    val spoken = mutableStateOf(0)

    private fun speak(text: String) {
        val short = text.take(300)  // Tenmin: the answer first, and short
        if (!ready) { pending = short; return }
        voice?.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
            override fun onStart(id: String?) {}
            override fun onDone(id: String?) { android.os.Handler(android.os.Looper.getMainLooper()).post { spoken.value += 1 } }
            @Deprecated("Deprecated in Java") override fun onError(id: String?) {}
        })
        voice?.speak(short, android.speech.tts.TextToSpeech.QUEUE_FLUSH, null, "kairu")
    }

    /** "You're welcome", spoken, at the end of a spoken conversation; the mic is not opened again. */
    fun sayBye() {
        add(ChatLine("you", "thank you", now()))
        add(ChatLine("kairu", "You're welcome.", now()))  // spoken by add(), as the answer to "thank you"
    }

    fun close() {
        voice?.shutdown()
        voice = null
    }

    // --- pairing ----------------------------------------------------------------------------------------

    /** Pair with the PC from its QR code's text and its 6-digit code. Null when paired, or why not. */
    suspend fun pair(offerText: String, code: String, name: String): String? = withContext(Dispatchers.IO) {
        try {
            val offer = Link.readOffer(offerText)
            if (offer.expires * 1000 < now()) return@withContext "That pairing code has run out. Run kairu device pair again."
            if (!Regex("\\d{6}").matches(code)) return@withContext "The code is the 6 digits your PC shows next to the QR code."
            val cleanName = name.trim().ifEmpty { "My phone" }.take(40)
            val me = store.identity()
            val relay = Relay(offer.relay)
            val since = now() / 1000 - 5
            relay.publish(offer.topic, Link.pairRequest(me, offer, code, cleanName, now()))
            val deadline = now() + 60_000
            var topic: String? = null
            while (topic == null && now() < deadline) {
                try {
                    relay.listen(offer.topic, since, keepGoing = { topic == null && now() < deadline }) { event ->
                        if (topic != null || Link.senderOf(event.message) == me.id) return@listen
                        try {
                            val message = Link.open(event.message, me, offer.pc, now())
                            topic = Link.pairedTopic(message, offer.pc)
                        } catch (error: LinkError) {
                            // something else on the pairing topic
                        }
                    }
                } catch (error: RelayError) {
                    delay(2000)
                }
            }
            val found = topic ?: return@withContext "Your PC didn't confirm. Check the 6-digit code, and that kairu device pair is still waiting."
            store.savePairing(offer.pc, offer.relay, found, cleanName, now() / 1000)
            withContext(Dispatchers.Main) {
                paired.value = true
                lines.clear()
                add(ChatLine("note", "Paired with your PC. Ask Kairu anything, or say status.", now()))
            }
            null
        } catch (error: LinkError) {
            error.message
        } catch (error: RelayError) {
            "Can't reach the Gate: ${error.message}. Check the internet and try again."
        } catch (error: Exception) {
            "Pairing didn't work (${error.javaClass.simpleName})."
        }
    }

    fun unpair() {
        store.forgetPairing()
        lines.clear()
        paired.value = false
    }

    // --- talking to Kairu -------------------------------------------------------------------------------

    /** Send what the owner typed: "status" asks how the PC is; anything else is an order (or a question) for the PC.
     *  D4: a mission is the same order sent as a "mission", which waits in the Gate (up to 12 hours) while the PC is off
     *  and runs through the PC's task core when Guardian next runs; each step is still decided by Guardian. */
    suspend fun send(text: String, mission: Boolean = false): String? {
        val words = text.trim()
        if (words.isEmpty()) return "Type something first."
        val pc = store.pc() ?: return "This phone isn't paired."
        val isStatus = !mission && words.equals("status", ignoreCase = true)
        if (!mission) local(words)?.let { said ->  // D5, level 0: a few answers from the phone itself, PC off or not
            add(ChatLine("you", words, now()))
            add(ChatLine("kairu", said, now()))
            return null
        }
        if (!mission) com.kairu.phone.brain.PhoneSkill.parse(words)?.let { skill ->  // D7: a skill on the phone itself
            add(ChatLine("you", words, now()))
            add(ChatLine("kairu", onPhone(skill), now()))
            return null
        }
        return withContext(Dispatchers.IO) {
            try {
                // D3: anything but "status" is an order for the PC's task core, which also answers questions
                val body = org.json.JSONObject().put("action", "task.order").put("details", org.json.JSONObject().put("order", words)).toString()
                val kind = if (isStatus) "status" else if (mission) "mission" else "command"
                val envelope = Link.seal(store.identity(), pc, kind, if (isStatus) "" else body, now())
                Relay(store.relay).publish(store.topic, envelope)
                store.lastSent = envelope
                withContext(Dispatchers.Main) {
                    add(ChatLine("you", if (mission) "Mission: $words" else words, now()))
                    if (mission) add(ChatLine("note", "Mission sent. It waits up to 12 hours for your PC and runs when Kairu is on. A High step still needs your approval.", now()))
                    else waiting.value = true
                }
                null
            } catch (error: LinkError) {
                error.message
            } catch (error: RelayError) {
                "Not sent: ${error.message}."
            }
        }
    }

    /** D7: a skill that needs a contact's number waits here while Android asks for the Contacts permission. */
    val contactsAsk = mutableStateOf<com.kairu.phone.brain.PhoneSkill?>(null)

    /** After the owner answered Android's Contacts question: run the waiting skill, or say why not. */
    fun contactsAnswered(granted: Boolean) {
        val skill = contactsAsk.value ?: return
        contactsAsk.value = null
        add(ChatLine("kairu", if (granted) onPhone(skill) else "Without Contacts I can't find names. Say the number instead.", now()))
    }

    /** One contact's number by (part of) their name, from the phone's own contacts; or what to say instead. */
    private fun numberOf(name: String): Pair<String?, String> {
        val found = LinkedHashMap<String, String>()  // contact name -> first number
        app.contentResolver.query(
            android.provider.ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            arrayOf(android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, android.provider.ContactsContract.CommonDataKinds.Phone.NUMBER),
            "${android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?", arrayOf("%$name%"), null,
        )?.use { rows ->
            while (rows.moveToNext() && found.size <= 5) {
                val who = rows.getString(0) ?: continue
                val number = rows.getString(1) ?: continue
                found.putIfAbsent(who, number)
            }
        }
        val exact = found.keys.filter { it.equals(name, ignoreCase = true) }
        return when {
            found.isEmpty() -> null to "I couldn't find \"$name\" in your contacts."
            exact.size == 1 -> found.getValue(exact[0]) to exact[0]
            found.size == 1 -> found.values.first() to found.keys.first()
            else -> null to "I found ${found.keys.take(5).joinToString(", ")}. Say the full name."
        }
    }

    /** D7: start the app that does it, with the work ready; the owner presses Send or Call. What to tell the owner. */
    private fun onPhone(skill: com.kairu.phone.brain.PhoneSkill): String {
        val named = skill is com.kairu.phone.brain.PhoneSkill.CallName || skill is com.kairu.phone.brain.PhoneSkill.SmsName ||
            skill is com.kairu.phone.brain.PhoneSkill.WhatsAppName
        if (named && app.checkSelfPermission(android.Manifest.permission.READ_CONTACTS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            contactsAsk.value = skill  // the chat screen asks Android, then contactsAnswered() runs it
            return "To find names I need to read your contacts. Allow it on the next screen (asked once)."
        }
        if (named) {
            val name = when (skill) {
                is com.kairu.phone.brain.PhoneSkill.CallName -> skill.name
                is com.kairu.phone.brain.PhoneSkill.SmsName -> skill.name
                is com.kairu.phone.brain.PhoneSkill.WhatsAppName -> skill.name
                else -> ""
            }
            val (number, who) = numberOf(name)
            number ?: return who
            val ready = when (skill) {
                is com.kairu.phone.brain.PhoneSkill.CallName -> com.kairu.phone.brain.PhoneSkill.Dial(number)
                is com.kairu.phone.brain.PhoneSkill.SmsName -> com.kairu.phone.brain.PhoneSkill.Sms(number, skill.text)
                is com.kairu.phone.brain.PhoneSkill.WhatsAppName ->
                    com.kairu.phone.brain.PhoneSkill.WhatsAppTo(com.kairu.phone.brain.PhoneSkill.international(number), skill.text)
                else -> return "?"
            }
            return "$who: " + onPhone(ready)
        }
        val (intent, said) = when (skill) {
            is com.kairu.phone.brain.PhoneSkill.Say -> return skill.text
            is com.kairu.phone.brain.PhoneSkill.CallName, is com.kairu.phone.brain.PhoneSkill.SmsName,
            is com.kairu.phone.brain.PhoneSkill.WhatsAppName -> return "?"
            is com.kairu.phone.brain.PhoneSkill.WhatsAppTo ->
                android.content.Intent(android.content.Intent.ACTION_VIEW,
                    android.net.Uri.parse("https://wa.me/${skill.number}?text=${android.net.Uri.encode(skill.text)}"))
                    .setPackage("com.whatsapp") to "Your text is ready in that WhatsApp chat. Press Send if it's right."
            is com.kairu.phone.brain.PhoneSkill.OpenApp -> (app.packageManager.getLaunchIntentForPackage(skill.pkg)
                ?: return "${skill.label} isn't on this phone.") to "Opened ${skill.label}."
            is com.kairu.phone.brain.PhoneSkill.Camera ->
                android.content.Intent(android.provider.MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA) to "Opened the camera."
            is com.kairu.phone.brain.PhoneSkill.Settings ->
                android.content.Intent(android.provider.Settings.ACTION_SETTINGS) to "Opened Settings."
            is com.kairu.phone.brain.PhoneSkill.Dial ->
                android.content.Intent(android.content.Intent.ACTION_DIAL, android.net.Uri.parse("tel:${skill.number}")) to
                    "The number is ready in your dialer. Press Call if it's right."
            is com.kairu.phone.brain.PhoneSkill.Sms ->
                android.content.Intent(android.content.Intent.ACTION_SENDTO, android.net.Uri.parse("smsto:${skill.number}"))
                    .putExtra("sms_body", skill.text) to "Your message is ready in Messages. Press Send if it's right."
            is com.kairu.phone.brain.PhoneSkill.WhatsApp ->
                android.content.Intent(android.content.Intent.ACTION_SEND).setType("text/plain")
                    .putExtra(android.content.Intent.EXTRA_TEXT, skill.text).setPackage("com.whatsapp") to
                    "Your text is ready in WhatsApp. Pick the chat, then press Send."
            is com.kairu.phone.brain.PhoneSkill.Alarm ->
                android.content.Intent(android.provider.AlarmClock.ACTION_SET_ALARM)
                    .putExtra(android.provider.AlarmClock.EXTRA_HOUR, skill.hour)
                    .putExtra(android.provider.AlarmClock.EXTRA_MINUTES, skill.minute)
                    .putExtra(android.provider.AlarmClock.EXTRA_MESSAGE, skill.label) to
                    "Alarm set for ${"%d:%02d".format(skill.hour, skill.minute)}${if (skill.label != "Kairu") ": ${skill.label}" else ""}."
            is com.kairu.phone.brain.PhoneSkill.Timer ->
                android.content.Intent(android.provider.AlarmClock.ACTION_SET_TIMER)
                    .putExtra(android.provider.AlarmClock.EXTRA_LENGTH, skill.seconds)
                    .putExtra(android.provider.AlarmClock.EXTRA_MESSAGE, skill.label) to
                    "Timer set for ${if (skill.seconds % 60 == 0) "${skill.seconds / 60} min" else "${skill.seconds} s"}" +
                    (if (skill.label != "Kairu") ": ${skill.label}." else ".")
        }
        return try {
            app.startActivity(intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
            said
        } catch (error: android.content.ActivityNotFoundException) {
            "No app on this phone can do that."
        } catch (error: SecurityException) {
            "Android didn't allow that."
        }
    }

    /** The phone's own fixed rules (brain/Rules.kt): the clock and the battery, read here; null when it's for the PC. */
    private fun local(words: String): String? {
        val battery = app.getSystemService(android.os.BatteryManager::class.java)
        val percent = battery?.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY)?.takeIf { it in 0..100 }
        return com.kairu.phone.brain.Rules.answer(words, com.kairu.phone.brain.Rules.Facts(
            java.time.ZonedDateTime.now(), percent, battery?.isCharging, gate.value, paired.value))
    }

    /** A command for the PC: a request only. {"action", "details"}, as kairu/link/receive.py reads it. Null, or why not. */
    suspend fun command(action: String, details: Map<String, Any>, shown: String?): String? {
        val pc = store.pc() ?: return "This phone isn't paired."
        val body = org.json.JSONObject().put("action", action).put("details", org.json.JSONObject(details)).toString()
        return withContext(Dispatchers.IO) {
            try {
                val envelope = Link.seal(store.identity(), pc, "command", body, now())
                Relay(store.relay).publish(store.topic, envelope)
                store.lastSent = envelope
                if (shown != null) withContext(Dispatchers.Main) { add(ChatLine("note", shown, now())) }
                null
            } catch (error: LinkError) {
                error.message
            } catch (error: RelayError) {
                "Not sent: ${error.message}."
            }
        }
    }

    /** STOP: everything on the PC halts within a second and Safe Mode begins (resumed only at the PC). */
    suspend fun stop(): String? = command("guardian.stop", emptyMap(),
        "Stop sent. Your PC halts everything and goes to Safe Mode. It won't hear this phone again until you run kairu resume at the PC.")

    /** Turn fingerprint approvals on: a new Keystore key, sent to the PC, where only your PIN accepts it. */
    suspend fun enrollFingerprint(): String? {
        if (!com.kairu.phone.link.Approver.supported) return "Fingerprint approval needs Android 13 or newer. Approve at the PC instead."
        val key = try {
            withContext(Dispatchers.IO) { com.kairu.phone.link.Approver.create() }
        } catch (error: Exception) {
            return "This phone can't make a fingerprint key (${error.javaClass.simpleName}). Approve at the PC instead."
        }
        return command("device.approver", mapOf("key" to java.util.Base64.getEncoder().encodeToString(key)),
            "Asked your PC to accept this phone's fingerprint key. At the PC: kairu link waiting, then kairu link approve with yes and your PIN.")
    }

    /** Send a card's answer: the fingerprint's signature, or a refusal. */
    suspend fun answerCard(card: ApprovalRequest, signature: String?): String? {
        val failed = if (signature == null) {
            command("link.refuse", mapOf("number" to card.number), "Refused ${card.action}.")
        } else {
            command("link.approve", mapOf("number" to card.number, "signature" to signature), "Approved ${card.action} with your fingerprint.")
        }
        if (failed == null) withContext(Dispatchers.Main) { answered.add(card.number) }
        return failed
    }

    fun statementFor(card: ApprovalRequest): ByteArray {
        val me = store.identity()
        return com.kairu.phone.link.Approver.statement(me.id, card.number, card.fingerprint, card.expires)
    }

    /** For the gate test: the last message again, unchanged. The PC refuses it as a replay and doesn't answer. */
    suspend fun replayLast(): String? {
        val last = store.lastSent ?: return "Nothing sent yet."
        return withContext(Dispatchers.IO) {
            try {
                Relay(store.relay).publish(store.topic, last)
                withContext(Dispatchers.Main) {
                    add(ChatLine("note", "Sent your last message again, unchanged (a replay test). Your PC should ignore it.", now()))
                }
                null
            } catch (error: RelayError) {
                "Not sent: ${error.message}."
            }
        }
    }

    /** Reads the Gate while the app is open, until the scope ends. */
    suspend fun listen(scope: CoroutineScope) = withContext(Dispatchers.IO) {
        var wait = 2000L
        val seenEvents = HashSet<String>()
        while (scope.isActive && store.paired) {
            val pc = store.pc() ?: return@withContext
            val me = store.identity()
            try {
                withContext(Dispatchers.Main) { gate.value = "Listening" }
                Relay(store.relay).listen(store.topic, store.since, keepGoing = { scope.isActive && store.paired }) { event ->
                    if (!seenEvents.add(event.id)) return@listen
                    if (event.time > store.since) store.since = event.time
                    if (Link.senderOf(event.message) == me.id) return@listen  // this phone's own message
                    try {
                        val message = Link.open(event.message, me, pc, now())
                        if (!store.firstSight(message.nonce, now())) return@listen  // a replay, or read again
                        val isCard = ApprovalRequest.parse(message.body) != null
                        val line = ChatLine(if (isCard) "card" else "kairu", message.body.ifEmpty { "(${message.type})" }, now())
                        scope.launchMain {
                            add(line)
                            waiting.value = false
                        }
                    } catch (error: LinkError) {
                        if (Link.senderOf(event.message) == pc.id) {
                            scope.launchMain { add(ChatLine("note", "Refused a message from your PC: ${error.message}.", now())) }
                        }
                    }
                }
                wait = 2000L
            } catch (error: RelayError) {
                withContext(Dispatchers.Main) { gate.value = "Can't reach the Gate" }
                delay(wait)
                wait = minOf(wait * 2, 60_000L)
            }
        }
    }
}

private fun CoroutineScope.launchMain(block: () -> Unit) {
    launch(Dispatchers.Main) { block() }
}

/** A High request the PC asks this phone to approve (kairu/guardian_program.py, approval_card). Text to show, nothing more. */
class ApprovalRequest(
    val number: Int,
    val action: String,
    val description: String,
    val details: List<Pair<String, String>>,
    val expires: Long,
    val fingerprint: String,
) {
    companion object {
        fun parse(body: String): ApprovalRequest? = try {
            val card = org.json.JSONObject(body).getJSONObject("kairu_card")
            val details = card.optJSONObject("details")
            val pairs = mutableListOf<Pair<String, String>>()
            if (details != null) for (key in details.keys()) pairs.add(key to details.get(key).toString())
            val fingerprint = card.getString("fingerprint")
            if (!Regex("[0-9a-f]{64}").matches(fingerprint)) null
            else ApprovalRequest(card.getInt("number"), card.getString("action"), card.optString("description"), pairs, card.getLong("expires"), fingerprint)
        } catch (error: Exception) {
            null
        }
    }
}
