package com.kairu.phone.voice

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

/**
 * D6: Kairu's ear on the phone. It listens with the phone's own on-device speech engine (Android 12+, the offline
 * English (India) pack in Google Voice Typing), so no sound leaves the phone, and it shows the words live while the owner
 * talks. It opens the microphone only after the owner's tap (or, in a spoken conversation, after Kairu's spoken answer),
 * for one sentence, and lets it go as soon as that sentence is heard, on silence, on an error or on stop(). Nothing is
 * recorded or kept. What it heard is only words: it can never approve anything.
 */
class Ear(private val context: Context) {
    private var recognizer: SpeechRecognizer? = null

    companion object {
        /** True when this phone has an on-device speech engine Kairu can use directly. */
        fun onDevice(context: Context): Boolean =
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
    }

    /** Listen for one sentence. Callbacks run on the main thread. */
    fun listen(onWords: (String) -> Unit, onHeard: (String) -> Unit, onNothing: () -> Unit, onProblem: (String) -> Unit) {
        stop()
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            onProblem("This phone's Android is too old to listen offline.")
            return
        }
        val ear = SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        recognizer = ear
        ear.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}

            override fun onPartialResults(partialResults: Bundle?) {
                partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                    ?.takeIf { it.isNotBlank() }?.let(onWords)
            }

            override fun onResults(results: Bundle?) {
                val heard = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                stop()
                if (heard.isNullOrBlank()) onNothing() else onHeard(heard)
            }

            override fun onError(error: Int) {
                stop()
                when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> onNothing()
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> onProblem("Kairu needs the Microphone permission to hear you.")
                    SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED, SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE ->
                        onProblem("Offline English (India) isn't ready: Settings → Google Voice Typing → Offline speech.")
                    SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> onProblem("The mic is busy in another app. Tap 🎤 again in a moment.")
                    else -> onProblem("The mic stopped (error $error). Tap 🎤 to try again.")
                }
            }
        })
        ear.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true))
    }

    /** Let the microphone go now. */
    fun stop() {
        recognizer?.destroy()
        recognizer = null
    }
}
