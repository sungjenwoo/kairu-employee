package com.kairu.phone.brain

import java.util.Locale

/**
 * D7, first part (PHONE.md): skills that act on the phone itself, read from what the owner typed with "Now" picked.
 * Each one only opens an app with the work ready: Kairu never sends a message or makes a call by itself, the owner
 * presses Send or Call. So none needs the SMS, call or contacts permission. Anything not matched here goes to the PC.
 * This file only reads the words; Session starts the app (Android intents).
 */
sealed class PhoneSkill {
    data class OpenApp(val label: String, val pkg: String) : PhoneSkill()
    object Camera : PhoneSkill()
    object Settings : PhoneSkill()
    data class Dial(val number: String) : PhoneSkill()
    data class Sms(val number: String, val text: String) : PhoneSkill()
    data class WhatsApp(val text: String) : PhoneSkill()
    data class WhatsAppTo(val number: String, val text: String) : PhoneSkill()  // a chat with this number, text ready
    data class CallName(val name: String) : PhoneSkill()  // a contact by name: found on the phone (READ_CONTACTS)
    data class SmsName(val name: String, val text: String) : PhoneSkill()
    data class WhatsAppName(val name: String, val text: String) : PhoneSkill()
    data class Alarm(val hour: Int, val minute: Int, val label: String) : PhoneSkill()
    data class Timer(val seconds: Int, val label: String) : PhoneSkill()
    data class Say(val text: String) : PhoneSkill()  // understood, but not something the phone can do yet

    companion object {
        /** Apps that "open X" opens on the phone even without "on my phone": they live on the phone. */
        val PHONE_APPS = mapOf(
            "whatsapp" to ("WhatsApp" to "com.whatsapp"),
            "instagram" to ("Instagram" to "com.instagram.android"),
            "play store" to ("Play Store" to "com.android.vending"),
            "maps" to ("Maps" to "com.google.android.apps.maps"),
            "google maps" to ("Maps" to "com.google.android.apps.maps"),
        )

        /** Apps the PC has too: opened on the phone only when the owner says "on my phone". */
        val SHARED_APPS = mapOf(
            "youtube" to ("YouTube" to "com.google.android.youtube"),
            "chrome" to ("Chrome" to "com.android.chrome"),
            "gmail" to ("Gmail" to "com.google.android.gm"),
            "spotify" to ("Spotify" to "com.spotify.music"),
        )

        private val ON_PHONE = Regex("""\s+(on|in) (my |the )?phone$""")
        private val NUMBER = """(\+?\d[\d\s-]{5,16}\d)"""
        private val OPEN = Regex("""^(open|launch|start) (.+)$""")
        private val CALL = Regex("""^(call|dial) (.+)$""")
        private val SMS = Regex("""^(text|sms|message) $NUMBER(?:\s+(?:saying|that|:))?\s*:?\s+(.+)$""")
        private val NAME = """([a-z][a-z.']*(?: [a-z][a-z.']*)?)"""
        private val SMS_NAME = Regex("""^(?:text|sms|message) $NAME\s*(?:saying|that|:)\s+(.+)$""")
        private val SMS_NAME_SHORT = Regex("""^(?:text|sms|message) ([a-z][a-z.']*) (.+)$""")
        private val WHATSAPP_NAME = Regex("""^whatsapp $NAME\s*(?:saying|that|:)\s+(.+)$""")
        private val WHATSAPP = Regex("""^(?:send |message )?(?:on |a )?whatsapp(?: message)?\s*:?\s+(?:saying |that )?(.+)$""")
        private val TIME = """(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"""
        private val ALARM = Regex("""^(?:set (?:an |the |a )?alarm|wake me up)(?: for| at)? $TIME$""")
        private val REMIND_AT = Regex("""^remind me (?:at )?$TIME (?:to |about )?(.+)$""")
        private val REMIND_TO_AT = Regex("""^remind me (?:to |about )(.+?) at $TIME$""")
        private val REMIND_IN = Regex("""^remind me in (\d{1,3}) (minutes?|mins?|hours?|hrs?) (?:to |about )?(.+)$""")
        private val TIMER = Regex("""^(?:set (?:a |the )?)?timer (?:for )?(\d{1,3}) (minutes?|mins?|hours?|hrs?|seconds?|secs?)$""")

        /** The skill the words ask for, or null when they are for the PC. */
        fun parse(text: String): PhoneSkill? {
            var words = text.trim().replace(Regex("""^kairu,?\s+""", RegexOption.IGNORE_CASE), "")
            val original = words  // the message's own words keep their case
            words = words.lowercase(Locale.ROOT).replace(Regex("""\s+"""), " ").trimEnd('.', '!', '?')
            OPEN.matchEntire(words.replace(ON_PHONE, ""))?.let { found ->
                val onPhone = ON_PHONE.containsMatchIn(words)
                val name = found.groupValues[2].removePrefix("the ").removeSuffix(" app")
                return when {
                    name == "camera" -> Camera
                    name == "settings" && onPhone -> Settings
                    name in PHONE_APPS -> PHONE_APPS.getValue(name).let { OpenApp(it.first, it.second) }
                    name in SHARED_APPS && onPhone -> SHARED_APPS.getValue(name).let { OpenApp(it.first, it.second) }
                    else -> null  // "open Notepad", "open YouTube": the PC
                }
            }
            SMS.matchEntire(words)?.let { found ->
                return Sms(digits(found.groupValues[2]), tail(original, found.groupValues[3]))
            }
            SMS_NAME.matchEntire(words)?.let { found -> return SmsName(found.groupValues[1], tail(original, found.groupValues[2])) }
            SMS_NAME_SHORT.matchEntire(words)?.let { found ->
                return SmsName(found.groupValues[1], tail(original, found.groupValues[2]))
            }
            WHATSAPP_NAME.matchEntire(words)?.let { found ->
                return WhatsAppName(found.groupValues[1], tail(original, found.groupValues[2]))
            }
            WHATSAPP.matchEntire(words)?.let { found -> return WhatsApp(tail(original, found.groupValues[1])) }
            CALL.matchEntire(words)?.let { found ->
                val who = found.groupValues[2]
                return when {
                    Regex("^$NUMBER$").matches(who) -> Dial(digits(who))
                    Regex("^$NAME$").matches(who) -> CallName(who)
                    else -> Say("Say a name or a number, like \"call Mom\" or \"call 98xxxxxxxx\".")
                }
            }
            ALARM.matchEntire(words)?.let { found ->
                return clock(found.groupValues[1], found.groupValues[2], found.groupValues[3])?.let { (h, m) -> Alarm(h, m, "Kairu") }
                    ?: Say("That isn't a time I can set.")
            }
            REMIND_AT.matchEntire(words)?.let { found ->
                return clock(found.groupValues[1], found.groupValues[2], found.groupValues[3])
                    ?.let { (h, m) -> Alarm(h, m, tail(original, found.groupValues[4])) } ?: Say("That isn't a time I can set.")
            }
            REMIND_TO_AT.matchEntire(words)?.let { found ->
                return clock(found.groupValues[2], found.groupValues[3], found.groupValues[4])
                    ?.let { (h, m) -> Alarm(h, m, tail(original, found.groupValues[1])) } ?: Say("That isn't a time I can set.")
            }
            REMIND_IN.matchEntire(words)?.let { found ->
                val seconds = found.groupValues[1].toInt() * (if (found.groupValues[2].startsWith("h")) 3600 else 60)
                return if (seconds in 1..86_400) Timer(seconds, tail(original, found.groupValues[3])) else Say("That's too long for a timer.")
            }
            TIMER.matchEntire(words)?.let { found ->
                val unit = found.groupValues[2]
                val seconds = found.groupValues[1].toInt() * when { unit.startsWith("h") -> 3600; unit.startsWith("s") -> 1; else -> 60 }
                return if (seconds in 1..86_400) Timer(seconds, "Kairu") else Say("That's too long for a timer.")
            }
            return null
        }

        private fun digits(number: String) = number.filter { it.isDigit() || it == '+' }

        /** A number as WhatsApp's link wants it: country code and digits only (a 10-digit number is taken as India's). */
        fun international(number: String): String {
            val plain = number.filter { it.isDigit() }
            return when {
                number.trim().startsWith("+") -> plain
                plain.length == 10 -> "91$plain"
                plain.length == 11 && plain.startsWith("0") -> "91${plain.drop(1)}"
                else -> plain
            }
        }

        /** "thank you" and the like: the end of a spoken conversation (D6). */
        fun endsTalk(text: String): Boolean = Regex("""^(kairu,?\s+)?(thank you|thanks|thank you kairu|thanks kairu|stop listening|that's all|bye|goodbye)[.!]?$""")
            .matches(text.trim().lowercase(Locale.ROOT))

        /** Hour and minute (24-hour) from "6", "6:30", "6 pm", "18:30"; null if it is not a time. */
        fun clock(hourText: String, minuteText: String, half: String): Pair<Int, Int>? {
            var hour = hourText.toIntOrNull() ?: return null
            val minute = if (minuteText.isEmpty()) 0 else minuteText.toIntOrNull() ?: return null
            if (minute !in 0..59) return null
            if (half.isNotEmpty()) {
                if (hour !in 1..12) return null
                val pm = half.startsWith("p")
                hour = when { pm && hour < 12 -> hour + 12; !pm && hour == 12 -> 0; else -> hour }
            }
            return if (hour in 0..23) hour to minute else null
        }

        /** The same words as typed (their case kept), found by position from the end of the lowercased match. */
        private fun tail(original: String, lower: String): String {
            val at = original.lowercase(Locale.ROOT).lastIndexOf(lower)
            val kept = if (at >= 0) original.substring(at, at + lower.length) else lower
            return kept.trim().trimEnd('.', '!').ifEmpty { "Kairu" }
        }
    }
}
