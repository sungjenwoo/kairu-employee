package com.kairu.phone.brain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime

class RulesTest {
    private val facts = Rules.Facts(
        now = ZonedDateTime.of(2026, 11, 12, 10, 5, 0, 0, ZoneId.of("Asia/Kolkata")),
        batteryPercent = 76, charging = true, gate = "Listening", paired = true,
    )

    @Test fun theTimeAndDateComeFromThePhone() {
        assertEquals("It's 10:05 AM.", Rules.answer("what time is it?", facts))
        assertEquals("It's 10:05 AM.", Rules.answer("Kairu, what's the time", facts))
        assertEquals("Today is Thursday, 12 November 2026.", Rules.answer("what's the date", facts))
    }

    @Test fun theBattery() {
        assertEquals("Your phone's battery is at 76%, charging.", Rules.answer("battery", facts))
        assertEquals("Your phone's battery is at 76%.", Rules.answer("how much battery is left?", facts.copy(charging = false)))
        assertEquals("I can't read the battery right now.", Rules.answer("battery level", facts.copy(batteryPercent = null)))
    }

    @Test fun helpSaysItIsKairuTheAssistant() {
        val said = Rules.answer("what can you do", facts)!!
        assertTrue(said.startsWith("I'm Kairu, Saitej's assistant."))
    }

    @Test fun theLinkState() {
        assertTrue(Rules.answer("is my PC connected?", facts)!!.startsWith("The phone is connected"))
        assertTrue(Rules.answer("is my pc on", facts.copy(gate = "No internet"))!!.contains("No internet"))
    }

    @Test fun everythingElseGoesToThePc() {
        for (text in listOf("open Notepad", "status", "set volume to 20", "what time is the match tomorrow",
                            "restart", "who is the prime minister of India", "battery saver on")) {
            assertNull(text, Rules.answer(text, facts))
        }
    }
}
