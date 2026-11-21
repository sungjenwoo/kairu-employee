package com.kairu.phone.brain

import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * The phone's own brain, level 0 (D5, first part; App Master Plan Part 3): fixed rules that answer a few simple questions
 * on the phone itself, with the PC off and no internet. Nothing here acts: it only reads the clock and the battery it is
 * given, and answers in words. Anything else goes to the PC as before. The small offline model comes later in D5.
 */
object Rules {
    /** What the phone knows right now, given by the app (so the rules are plain and testable). */
    data class Facts(
        val now: ZonedDateTime,
        val batteryPercent: Int?,  // null when the phone can't tell
        val charging: Boolean?,
        val gate: String,  // "Listening", "Connecting", or why it can't
        val paired: Boolean,
    )

    private val TIME = Regex("""^(what('?s| is) the time|what time is it|time( now)?|current time)\??$""")
    private val DATE = Regex("""^(what('?s| is) (the |today'?s )?date|what day is (it|today)|today'?s date|date( today)?)\??$""")
    private val BATTERY = Regex("""^((what('?s| is) )?(my |the )?(phone'?s? )?battery( level| percentage)?|how much battery( do i have| is left)?( left)?)\??$""")
    private val HELP = Regex("""^(help|what can you do|who are you|what are you)\??$""")
    private val LINK = Regex("""^(is my pc (on|connected|online)|are you connected( to my pc)?|pc status)\??$""")

    /** An answer from the phone itself, or null when the question is for the PC. */
    fun answer(text: String, facts: Facts): String? {
        val words = text.trim().lowercase(Locale.ROOT).replace(Regex("""^(kairu,?\s+)"""), "").replace(Regex("""\s+"""), " ")
        return when {
            TIME.matches(words) -> "It's ${facts.now.format(DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH))}."
            DATE.matches(words) -> "Today is ${facts.now.format(DateTimeFormatter.ofPattern("EEEE, d MMMM yyyy", Locale.ENGLISH))}."
            BATTERY.matches(words) -> when (facts.batteryPercent) {
                null -> "I can't read the battery right now."
                else -> "Your phone's battery is at ${facts.batteryPercent}%" +
                    (if (facts.charging == true) ", charging." else ".")
            }
            HELP.matches(words) -> "I'm Kairu, Saitej's assistant. On the phone I tell you the time, the date and the " +
                "battery, open WhatsApp, the camera or Maps, get a call, text or WhatsApp message ready for you to send, and " +
                "set alarms, reminders and timers. Everything else goes to Kairu on your PC: orders like \"open Notepad\", " +
                "questions, and missions that wait for the PC. Stop halts everything on the PC."
            LINK.matches(words) -> when {
                !facts.paired -> "This phone isn't paired with a PC yet."
                facts.gate == "Listening" -> "The phone is connected to the Gate. Send \"status\" to hear from the PC itself."
                else -> "The phone can't reach the Gate right now (${facts.gate}). Missions still wait for the PC."
            }
            else -> null
        }
    }
}
