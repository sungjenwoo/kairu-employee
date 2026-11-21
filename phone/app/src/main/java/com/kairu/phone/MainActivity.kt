package com.kairu.phone

import android.os.Build
import android.os.Bundle
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.BorderStroke
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import android.security.keystore.KeyPermanentlyInvalidatedException
import com.kairu.phone.link.Approver
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import com.google.zxing.client.android.Intents
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.launch

/** Kairu's colours, the same as the workspace's dark mode (WORKSPACE.md). */
object KairuColors {
    val Background = Color(0xFF262624)
    val Surface = Color(0xFF30302E)
    val Raised = Color(0xFF3A3936)
    val Border = Color(0xFF3D3D3A)
    val Text = Color(0xFFECECEA)
    val Muted = Color(0xFFA6A39B)
    val Accent = Color(0xFF3B82F6)
    val Green = Color(0xFF3FB27F)
    val Amber = Color(0xFFE0A43A)
    val Red = Color(0xFFE5484D)
    val Tile = Color(0xFF0B0B0B)
}

class MainActivity : FragmentActivity() {
    private lateinit var session: Session

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        session = Session(this)
        setContent {
            KairuTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = KairuColors.Background) {
                    if (session.paired.value) ChatScreen(session) else PairScreen(session, BuildConfig.VERSION_NAME)
                }
            }
        }
    }

    override fun onDestroy() {
        session.close()  // D6: let Android's voice go
        super.onDestroy()
    }
}

@Composable
fun KairuTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            background = KairuColors.Background,
            surface = KairuColors.Surface,
            primary = KairuColors.Accent,
            onBackground = KairuColors.Text,
            onSurface = KairuColors.Text,
        ),
        content = content,
    )
}

/** The logo from the owner's sketch: a black tile with a white pill ring. */
@Composable
fun KairuLogo(modifier: Modifier = Modifier, ring: Color = Color.White) {
    Canvas(modifier = modifier) {
        val side = size.minDimension
        drawRoundRect(color = KairuColors.Tile, cornerRadius = CornerRadius(side * 0.25f))
        val pillWidth = side * 0.56f
        val pillHeight = side * 0.31f
        drawRoundRect(
            color = ring,
            topLeft = Offset((size.width - pillWidth) / 2f, (size.height - pillHeight) / 2f),
            size = Size(pillWidth, pillHeight),
            cornerRadius = CornerRadius(pillHeight / 2f),
            style = Stroke(width = side * 0.075f),
        )
    }
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = KairuColors.Muted,
    unfocusedBorderColor = KairuColors.Border,
    focusedTextColor = KairuColors.Text,
    unfocusedTextColor = KairuColors.Text,
    cursorColor = KairuColors.Accent,
    focusedLabelColor = KairuColors.Muted,
    unfocusedLabelColor = KairuColors.Muted,
)

// --- pairing ------------------------------------------------------------------------------------------------

@Composable
fun PairScreen(session: Session, version: String) {
    var offer by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var name by remember { mutableStateOf(Build.MODEL ?: "My phone") }
    var busy by remember { mutableStateOf(false) }
    var problem by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val scanner = rememberLauncherForActivityResult(ScanContract()) { result ->
        result.contents?.let {
            offer = it
            problem = null
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(modifier = Modifier.height(24.dp))
        KairuLogo(modifier = Modifier.size(72.dp))
        Spacer(modifier = Modifier.height(16.dp))
        Text(text = "Kairu", color = KairuColors.Text, fontSize = 32.sp, fontFamily = FontFamily.Serif)
        Spacer(modifier = Modifier.height(4.dp))
        Text(text = "Pair this phone with your PC", color = KairuColors.Muted, fontSize = 15.sp)
        Spacer(modifier = Modifier.height(28.dp))

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = KairuColors.Surface),
        ) {
            Column(modifier = Modifier.padding(18.dp)) {
                Text("1. On your PC, run  kairu device pair", color = KairuColors.Text, fontSize = 14.sp)
                Spacer(modifier = Modifier.height(12.dp))
                Button(
                    onClick = {
                        scanner.launch(
                            ScanOptions()
                                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                .setPrompt("Scan the QR code your PC shows")
                                .setBeepEnabled(false)
                                .setOrientationLocked(false)
                                .addExtra(Intents.Scan.SCAN_TYPE, Intents.Scan.MIXED_SCAN),
                        )
                    },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = KairuColors.Text, contentColor = KairuColors.Background),
                ) { Text(if (offer.isEmpty()) "2. Scan the QR code" else "QR code scanned ✓  (scan again)") }
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = offer,
                    onValueChange = { offer = it.trim(); problem = null },
                    label = { Text("…or paste the text under the QR code") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = fieldColors(),
                )
                Spacer(modifier = Modifier.height(12.dp))
                OutlinedTextField(
                    value = code,
                    onValueChange = { typed -> code = typed.filter { it.isDigit() }.take(6); problem = null },
                    label = { Text("3. The 6-digit code") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                    modifier = Modifier.fillMaxWidth(),
                    colors = fieldColors(),
                )
                Spacer(modifier = Modifier.height(12.dp))
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.take(40) },
                    label = { Text("This phone's name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = fieldColors(),
                )
                Spacer(modifier = Modifier.height(16.dp))
                Button(
                    onClick = {
                        busy = true
                        problem = null
                        scope.launch {
                            problem = session.pair(offer, code, name)
                            busy = false
                        }
                    },
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = KairuColors.Accent, contentColor = Color.White),
                ) { Text(if (busy) "Waiting for your PC…" else "Pair") }
                problem?.let {
                    Spacer(modifier = Modifier.height(10.dp))
                    Text(it, color = KairuColors.Red, fontSize = 13.sp)
                }
            }
        }
        Spacer(modifier = Modifier.height(20.dp))
        Text(
            text = "Your phone only sends requests. Your PC's Guardian decides everything.\nVersion $version",
            color = KairuColors.Muted,
            fontSize = 12.sp,
            textAlign = TextAlign.Center,
        )
    }
}

// --- talking to Kairu -------------------------------------------------------------------------------------

@Composable
fun ChatScreen(session: Session) {
    var text by remember { mutableStateOf("") }
    var problem by remember { mutableStateOf<String?>(null) }
    var mission by remember { mutableStateOf(false) }
    var talking by remember { mutableStateOf(false) }  // D6: a spoken conversation is going on
    var menu by remember { mutableStateOf(false) }
    var askStop by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    val activity = LocalContext.current as FragmentActivity

    if (askStop) {
        AlertDialog(
            onDismissRequest = { askStop = false },
            title = { Text("Stop everything on your PC?") },
            text = { Text("Every running action halts within a second and your PC goes to Safe Mode. You resume at the PC with kairu resume.") },
            confirmButton = {
                TextButton(onClick = {
                    askStop = false
                    scope.launch { problem = session.stop() }
                }) { Text("Stop", color = KairuColors.Red) }
            },
            dismissButton = { TextButton(onClick = { askStop = false }) { Text("Cancel") } },
            containerColor = KairuColors.Surface,
            titleContentColor = KairuColors.Text,
            textContentColor = KairuColors.Muted,
        )
    }

    LaunchedEffect(Unit) { session.listen(this) }
    LaunchedEffect(session.lines.size, session.waiting.value) {
        val count = session.lines.size + (if (session.waiting.value) 1 else 0)
        if (count > 0) listState.animateScrollToItem(count - 1)
    }

    // D6: Kairu listens with the phone's own on-device speech engine (voice/Ear.kt): offline, so no sound leaves the phone,
    // with the words shown live. It asks once for the Microphone and opens it only after the owner's tap (or, in a spoken
    // conversation, after Kairu's spoken answer), for one sentence. Phones without that engine use Android's speech screen.
    // What was heard is sent like typed words; a spoken "yes" or PIN is only words, never an approval.
    val context = androidx.compose.ui.platform.LocalContext.current
    val ear = remember { com.kairu.phone.voice.Ear(context.applicationContext) }
    androidx.compose.runtime.DisposableEffect(Unit) { onDispose { ear.stop() } }
    var live by remember { mutableStateOf<String?>(null) }  // the words so far while Kairu listens; null when it isn't

    fun heard(words: String) {
        if (com.kairu.phone.brain.PhoneSkill.endsTalk(words)) {
            talking = false  // "thank you": the conversation ends, and the mic stays closed
            session.speakNextAnswer()
            session.sayBye()
            return
        }
        if (!mission) session.speakNextAnswer()  // a mission's answer may come hours later: shown, not spoken
        problem = null
        scope.launch { session.send(words, mission)?.let { problem = it } }
    }

    fun nothing() {
        if (talking) talking = false  // silence ends a conversation quietly
        else problem = "Didn't hear anything. Tap 🎤 and speak."
    }

    fun listenHere() {
        live = ""
        ear.listen(
            onWords = { live = it },
            onHeard = { live = null; heard(it) },
            onNothing = { live = null; nothing() },
            onProblem = { live = null; talking = false; problem = it },
        )
    }

    val askMic = rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) listenHere() else { talking = false; problem = "Without the Microphone permission Kairu can't hear you." }
    }

    // Android's speech screen: only for phones without an on-device engine
    val listen = rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult()) { result ->
        val words = result.data?.getStringArrayListExtra(android.speech.RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (result.resultCode == android.app.Activity.RESULT_OK && !words.isNullOrBlank()) heard(words) else nothing()
    }

    fun startListening() {
        problem = null
        if (com.kairu.phone.voice.Ear.onDevice(context)) {
            if (context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED) listenHere()
            else askMic.launch(android.Manifest.permission.RECORD_AUDIO)
            return
        }
        try {
            listen.launch(android.content.Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL, android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
                .putExtra(android.speech.RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                .putExtra(android.speech.RecognizerIntent.EXTRA_PROMPT,
                    if (mission) "A mission for Kairu" else if (talking) "Go on (say \"thank you\" to end)" else "Talk to Kairu"))
        } catch (error: android.content.ActivityNotFoundException) {
            talking = false
            problem = "This phone has no speech recognition to use."
        }
    }

    // D6: talk in a loop. The owner's tap starts it; after each spoken answer the speech screen opens again, until "thank
    // you", silence or closing it. Only Android's speech screen ever holds the mic, and only while it shows.
    LaunchedEffect(session.spoken.value) {
        if (talking && session.spoken.value > 0) startListening()
    }

    // D7: a call, text or WhatsApp by name asks Android for the Contacts permission once, then runs
    val askContacts = rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { granted ->
        session.contactsAnswered(granted)
    }
    LaunchedEffect(session.contactsAsk.value) {
        if (session.contactsAsk.value != null) askContacts.launch(android.Manifest.permission.READ_CONTACTS)
    }

    fun send(words: String, asMission: Boolean = false) {
        problem = null
        scope.launch {
            val failed = session.send(words, asMission)
            if (failed == null) text = "" else problem = failed
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .imePadding(),
    ) {
        // the top: logo, name, whether the Gate is being read, and the menu
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            KairuLogo(modifier = Modifier.size(30.dp), ring = if (session.waiting.value) KairuColors.Red else Color.White)
            Spacer(modifier = Modifier.width(10.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text("Kairu", color = KairuColors.Text, fontSize = 18.sp, fontWeight = FontWeight.Medium)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val listening = session.gate.value == "Listening"
                    Box(
                        modifier = Modifier
                            .size(7.dp)
                            .background(if (listening) KairuColors.Green else KairuColors.Amber, CircleShape),
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        if (listening) "Connected to your PC's Gate" else session.gate.value,
                        color = KairuColors.Muted,
                        fontSize = 12.sp,
                    )
                }
            }
            Button(
                onClick = { askStop = true },
                colors = ButtonDefaults.buttonColors(containerColor = KairuColors.Red, contentColor = Color.White),
            ) { Text("Stop", fontWeight = FontWeight.Medium) }
            Box {
                TextButton(onClick = { menu = true }) { Text("•••", color = KairuColors.Muted) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text("Ask how my PC is (status)") }, onClick = { menu = false; send("status") })
                    DropdownMenuItem(
                        text = { Text(if (Approver.exists) "Set up fingerprint approval again" else "Turn on fingerprint approval") },
                        onClick = {
                            menu = false
                            scope.launch { problem = session.enrollFingerprint() }
                        },
                    )
                    DropdownMenuItem(
                        text = { Text("Test: send my last message again") },
                        onClick = {
                            menu = false
                            scope.launch { problem = session.replayLast() }
                        },
                    )
                    DropdownMenuItem(
                        text = { Text("Unpair this phone") },
                        onClick = {
                            menu = false
                            Approver.forget()
                            session.unpair()
                        },
                    )
                }
            }
        }

        // the conversation
        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(session.lines) { line ->
                if (line.who == "card") {
                    ApprovalRequest.parse(line.text)?.let { card ->
                        ApprovalCard(card, done = card.number in session.answered) { approve ->
                            scope.launch {
                                if (!approve) {
                                    problem = session.answerCard(card, null)
                                } else {
                                    val signed = signWithFingerprint(activity, card, session.statementFor(card))
                                    val signature = signed.getOrNull()
                                    problem = if (signature != null) session.answerCard(card, signature) else signed.exceptionOrNull()?.message
                                }
                            }
                        }
                    }
                } else {
                    ChatBubble(line.who, line.text)
                }
            }
            if (session.waiting.value) item { ChatBubble("note", "Kairu is thinking…") }
        }

        // quick starts, the box, and send
        if (session.lines.size <= 1) {
            LazyRow(
                modifier = Modifier.padding(start = 16.dp, bottom = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(listOf("status", "how much RAM is free?", "open Notepad", "who is the prime minister of India")) { chip ->
                    Text(
                        chip,
                        color = KairuColors.Muted,
                        fontSize = 13.sp,
                        modifier = Modifier
                            .background(KairuColors.Surface, RoundedCornerShape(50))
                            .clickable { send(chip) }
                            .padding(horizontal = 14.dp, vertical = 7.dp),
                    )
                }
            }
        }
        problem?.let { Text(it, color = KairuColors.Red, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 18.dp)) }
        live?.let {  // D6: the words, live, while Kairu listens
            Text("🎙 " + it.ifEmpty { if (talking) "Listening… (say \"thank you\" to end)" else "Listening…" },
                color = KairuColors.Accent, fontSize = 15.sp, modifier = Modifier.padding(horizontal = 18.dp, vertical = 4.dp))
        }
        // D4: "Now" runs at once (the PC must be on); "Mission" waits for the PC, up to 12 hours
        Row(modifier = Modifier.padding(start = 16.dp, top = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(false to "Now", true to "Mission (waits for PC)").forEach { (isMission, label) ->
                val on = mission == isMission
                Text(
                    label,
                    color = if (on) KairuColors.Background else KairuColors.Muted,
                    fontSize = 13.sp,
                    modifier = Modifier
                        .background(if (on) KairuColors.Text else KairuColors.Surface, RoundedCornerShape(50))
                        .clickable { mission = isMission }
                        .padding(horizontal = 14.dp, vertical = 6.dp),
                )
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it; problem = null },
                placeholder = { Text(if (mission) "A mission for your PC, for when it's on…" else "Tell Kairu what to do on your PC…", color = KairuColors.Muted) },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(22.dp),
                maxLines = 4,
                colors = fieldColors(),
            )
            Spacer(modifier = Modifier.width(6.dp))
            OutlinedButton(
                onClick = {
                    if (live != null) {  // listening: the same button stops it, and the mic is let go
                        ear.stop()
                        live = null
                        talking = false
                    } else {
                        talking = !mission  // a conversation with Now; a mission is one spoken order
                        startListening()
                    }
                },
                shape = CircleShape,
                contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
                modifier = Modifier.size(48.dp),
            ) { Text(if (live != null) "■" else "🎤", fontSize = 18.sp) }
            Spacer(modifier = Modifier.width(6.dp))
            Button(
                onClick = { send(text, mission) },
                shape = CircleShape,
                colors = ButtonDefaults.buttonColors(containerColor = KairuColors.Text, contentColor = KairuColors.Background),
            ) { Text("↑", fontSize = 18.sp) }
        }
    }
}

@Composable
fun ChatBubble(who: String, text: String) {
    when (who) {
        "you" -> Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Text(
                text,
                color = KairuColors.Text,
                fontSize = 15.sp,
                modifier = Modifier
                    .widthIn(max = 290.dp)
                    .background(KairuColors.Raised, RoundedCornerShape(18.dp))
                    .padding(horizontal = 14.dp, vertical = 9.dp),
            )
        }
        "kairu" -> Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            KairuLogo(modifier = Modifier.size(24.dp).padding(top = 2.dp))
            Spacer(modifier = Modifier.width(10.dp))
            Text(text, color = KairuColors.Text, fontSize = 17.sp, lineHeight = 25.sp, fontFamily = FontFamily.Serif)
        }
        else -> Text(
            text,
            color = KairuColors.Muted,
            fontSize = 13.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        )
    }
}

/** Guardian's question for one High request: approve with the fingerprint, or refuse. Critical never asks. */
@Composable
fun ApprovalCard(card: ApprovalRequest, done: Boolean, onAnswer: (Boolean) -> Unit) {
    val left = ((card.expires * 1000 - System.currentTimeMillis()) / 1000).coerceAtLeast(0)
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0x24E0A43A)),
        border = BorderStroke(1.dp, KairuColors.Amber),
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text("Guardian asks for your approval", color = KairuColors.Text, fontWeight = FontWeight.Medium, fontSize = 15.sp)
            Spacer(modifier = Modifier.height(6.dp))
            Text("${card.action}: ${card.description}", color = KairuColors.Text, fontSize = 14.sp)
            card.details.forEach { (key, value) -> Text("$key: $value", color = KairuColors.Muted, fontSize = 13.sp) }
            Text("High tier · this approves it once · ${if (left > 0) "${left / 60}:${"%02d".format(left % 60)} left" else "ended"}",
                color = KairuColors.Muted, fontSize = 12.sp)
            Spacer(modifier = Modifier.height(10.dp))
            if (done) {
                Text("Answered.", color = KairuColors.Muted, fontSize = 13.sp)
            } else if (left > 0) {
                Row {
                    Button(
                        onClick = { onAnswer(true) },
                        colors = ButtonDefaults.buttonColors(containerColor = KairuColors.Text, contentColor = KairuColors.Background),
                    ) { Text("Approve with fingerprint") }
                    Spacer(modifier = Modifier.width(8.dp))
                    OutlinedButton(onClick = { onAnswer(false) }) { Text("Refuse", color = KairuColors.Text) }
                }
            }
        }
    }
}

/** Your fingerprint unlocks the Keystore key for one signature over exactly this request. */
suspend fun signWithFingerprint(activity: FragmentActivity, card: ApprovalRequest, statement: ByteArray): Result<String> =
    suspendCancellableCoroutine { waiting ->
        val signature = try {
            Approver.signer()
        } catch (error: KeyPermanentlyInvalidatedException) {
            waiting.resume(Result.failure(Exception("A fingerprint was added or removed on this phone, so its key ended. Turn fingerprint approval on again (••• menu).")))
            return@suspendCancellableCoroutine
        } catch (error: Exception) {
            waiting.resume(Result.failure(Exception("Fingerprint approval isn't on for this phone. Turn it on in the ••• menu, or approve at the PC.")))
            return@suspendCancellableCoroutine
        }
        val prompt = BiometricPrompt(activity, ContextCompat.getMainExecutor(activity), object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                val outcome = try {
                    val unlocked = result.cryptoObject!!.signature!!
                    unlocked.update(statement)
                    Result.success(java.util.Base64.getEncoder().encodeToString(unlocked.sign()))
                } catch (error: Exception) {
                    Result.failure(Exception("The fingerprint key couldn't sign (${error.javaClass.simpleName})."))
                }
                if (waiting.isActive) waiting.resume(outcome)
            }

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                if (waiting.isActive) waiting.resume(Result.failure(Exception("Not approved: $errString")))
            }
        })
        prompt.authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Approve on your PC")
                .setSubtitle(card.action)
                .setDescription(card.description)
                .setNegativeButtonText("Cancel")
                .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                .build(),
            BiometricPrompt.CryptoObject(signature),
        )
    }
