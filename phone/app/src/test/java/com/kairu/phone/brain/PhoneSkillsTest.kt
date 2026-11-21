package com.kairu.phone.brain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneSkillsTest {
    private fun parse(text: String) = PhoneSkill.parse(text)

    @Test fun phoneAppsOpenOnThePhoneAndPcAppsGoToThePc() {
        assertEquals(PhoneSkill.OpenApp("WhatsApp", "com.whatsapp"), parse("open WhatsApp"))
        assertEquals(PhoneSkill.OpenApp("Maps", "com.google.android.apps.maps"), parse("Kairu, open google maps"))
        assertEquals(PhoneSkill.Camera, parse("open the camera"))
        assertNull(parse("open YouTube"))  // the PC has it too: only "on my phone" opens it here
        assertEquals(PhoneSkill.OpenApp("YouTube", "com.google.android.youtube"), parse("open youtube on my phone"))
        assertEquals(PhoneSkill.Settings, parse("open settings on my phone"))
        assertNull(parse("open settings"))
        assertNull(parse("open Notepad"))
    }

    @Test fun callsAndTextsOnlyOpenTheAppTheOwnerPressesSendOrCall() {
        assertEquals(PhoneSkill.Dial("9876543210"), parse("call 98765 43210"))
        assertEquals(PhoneSkill.Dial("+919876543210"), parse("dial +91 98765-43210"))
        assertEquals(PhoneSkill.CallName("mom"), parse("call Mom"))
        assertEquals(PhoneSkill.CallName("rahul sharma"), parse("Kairu, call Rahul Sharma"))
        assertEquals(PhoneSkill.Sms("9876543210", "I'll be late, Mom"), parse("text 9876543210 I'll be late, Mom"))
        assertEquals(PhoneSkill.Sms("9876543210", "Reached"), parse("SMS 9876543210 saying Reached"))
    }

    @Test fun whatsappTextIsKeptAsTyped() {
        assertEquals(PhoneSkill.WhatsApp("I'll be late"), parse("WhatsApp: I'll be late"))
        assertEquals(PhoneSkill.WhatsApp("Meet at 5 on my phone"), parse("send a whatsapp message saying Meet at 5 on my phone"))
    }

    @Test fun alarmsRemindersAndTimers() {
        assertEquals(PhoneSkill.Alarm(6, 30, "Kairu"), parse("set an alarm for 6:30 am"))
        assertEquals(PhoneSkill.Alarm(18, 0, "Kairu"), parse("wake me up at 6 pm"))
        assertEquals(PhoneSkill.Alarm(17, 0, "call Mom"), parse("remind me at 5 pm to call Mom"))
        assertEquals(PhoneSkill.Alarm(21, 15, "drink water"), parse("remind me to drink water at 9:15 pm"))
        assertEquals(PhoneSkill.Alarm(0, 5, "Kairu"), parse("set alarm 12:05 am"))
        assertEquals(PhoneSkill.Timer(600, "check the rice"), parse("remind me in 10 minutes to check the rice"))
        assertEquals(PhoneSkill.Timer(90, "Kairu"), parse("set a timer for 90 seconds"))
        assertTrue(parse("set an alarm for 25:00") is PhoneSkill.Say)
        assertTrue(parse("set an alarm for 13 pm") is PhoneSkill.Say)
    }

    @Test fun everythingElseGoesToThePc() {
        for (text in listOf("status", "set volume to 20", "restart", "how much RAM is free?", "close Notepad",
                            "who is the prime minister of India", "what time is it")) {
            assertNull(text, parse(text))
        }
    }

    @Test fun textsAndWhatsappByName() {
        assertEquals(PhoneSkill.SmsName("rahul", "I'll be late"), parse("text Rahul I'll be late"))
        assertEquals(PhoneSkill.SmsName("rahul sharma", "Reached home"), parse("message Rahul Sharma saying Reached home"))
        assertEquals(PhoneSkill.SmsName("mom", "On my way"), parse("text Mom: On my way"))
        assertEquals(PhoneSkill.WhatsAppName("rahul", "Meet at 5"), parse("WhatsApp Rahul saying Meet at 5"))
        assertEquals(PhoneSkill.WhatsAppName("mom", "Coming"), parse("whatsapp mom: Coming"))
        assertEquals(PhoneSkill.WhatsApp("I'll be late"), parse("WhatsApp: I'll be late"))  // no name: you pick the chat
    }

    @Test fun whatsappNumbersGetIndiasCodeWhenTheyHaveNone() {
        assertEquals("919876543210", PhoneSkill.international("98765 43210"))
        assertEquals("919876543210", PhoneSkill.international("098765-43210"))
        assertEquals("447700900123", PhoneSkill.international("+44 7700 900123"))
    }

    @Test fun thankYouEndsATalk() {
        for (text in listOf("thank you", "Thanks!", "Kairu, thank you", "thank you Kairu", "bye")) {
            assertTrue(text, PhoneSkill.endsTalk(text))
        }
        for (text in listOf("thank you for the help, now open WhatsApp", "set a timer", "")) {
            assertTrue(text, !PhoneSkill.endsTalk(text))
        }
    }
}
