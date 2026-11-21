# The Kairu phone app (Phase D, ADR-034)

Kotlin, built on GitHub's machines (`.github/workflows/phone.yml`), installed on the Mivi phone with `adb` over Wi-Fi.
The PC never runs Android Studio: it only needs Google's small platform-tools (`adb`).

Built so far: **D0 (setup)**, **D1 (Link and pairing)**, **D2 (approvals and STOP)** and **D3 (control your PC from the
phone)**. The app pairs with your PC by its QR code and 6-digit code,
then you talk to Kairu from the phone: ask anything, or say `status`. Each later stage (D2 approvals and STOP, D3 PC
control, D4 missions and research) adds only the permissions it needs.

## One-time setup

1. **The phone.** Settings → About phone → tap *Build number* 7 times. Then Settings → System → Developer options →
   turn on **Wireless debugging**. The phone and the PC must be on the same Wi-Fi.
2. **The PC.** Download *SDK Platform-Tools for Windows* from Google
   (developer.android.com/tools/releases/platform-tools) and unzip it so that `C:\platform-tools\adb.exe` exists.
3. **Pair adb with the phone (once).** On the phone, in Wireless debugging, tap *Pair device with pairing code*. It shows an
   address and a 6-digit code. On the PC:

   ```
   kairu phone pair 192.168.1.5:37145 123456
   ```

4. **Connect.** The address at the top of the Wireless debugging screen (not the pairing one):

   ```
   kairu phone connect 192.168.1.5:41823
   ```

   This address changes when the phone's Wi-Fi changes or Wireless debugging is turned off and on; connect again then.

## Install or update the app

1. On GitHub: **Actions → Phone app → the newest green run → Artifacts → kairu-phone**. It downloads as a `.zip`.
2. On the PC:

   ```
   kairu phone install
   ```

   It takes the newest `kairu-phone…` file in your Downloads (the `.zip` is fine; give a path to use another one),
   checks that exactly one phone is connected, and installs it. An update keeps the app's data.

`kairu phone status` shows whether adb is found, which phone is connected, and the newest app file.

**The signing key.** Android only updates an app with one signed by the same key. Builds are signed with the owner's key
when the repository has the secrets `KAIRU_PHONE_KEYSTORE` (the keystore, base64) and `KAIRU_PHONE_KEYSTORE_PASSWORD`;
until then GitHub keeps one debug key between builds. If the key ever changes, `kairu phone install` says so: uninstall
Kairu on the phone once (its pairing goes with it), then install again.

`kairu phone` only moves the app to the phone. It is the owner's command, like `kairu voice setup`, never a Kairu action, and
it runs adb with its path and arguments as a list (no shell). It takes the `.apk` out of GitHub's `.zip` by its name only, into
`data/phone/`.

## D1: pair, then talk to Kairu

Guardian must be running on the PC, with Kairu Link on (LINK.md) and the brain set up (BRAIN.md).

1. On the PC: `kairu device pair`. It's High: type `yes` and your PIN. A QR code, the text under it, and a 6-digit code
   appear, valid 10 minutes.
2. On the phone: open Kairu → **Scan the QR code** (allow the camera once). If it won't scan, paste the text under the
   QR code instead. Type the 6-digit code, keep or change the phone's name, then **Pair**.
3. Within a few seconds the PC says `Paired: <name> (dev-…)` and the phone opens the conversation.
4. Ask anything ("who is the prime minister of India"), or tap **status**. The answer comes back in a few seconds.

What the phone does with the Link (all in `phone/app/src/main/java/com/kairu/phone/link/`):

- **The same crypto as the PC:** Ed25519 signatures and crypto_box (X25519 + XSalsa20-Poly1305), with Bouncy Castle for the
  curves and Poly1305. Its tests (`LinkCryptoTest`) use vectors made with PyNaCl and the PC's own code, and the PC checks the
  same vectors (`tests_kairu/test_phone_link_vectors.py`), so neither side can drift.
- **Its keys** are made on the phone at the first pairing and sealed with an AES key that Android's Keystore holds; they never
  leave the phone. The app is never backed up (`allowBackup` is off). Unpairing deletes them.
- **What it sends is a request**: `ask` (a question) or `status`. The PC's Guardian decides; the phone can't approve anything.
- **What it receives is text to show.** Each message from the PC is checked as the PC checks the phone's: from the paired PC,
  for this phone, opens, signed by the PC, at most 12 hours old, and never seen before (nonces kept 13 hours). Anything else
  is refused and nothing in it is acted on.
- **It reads the Gate while the app is open.** Reading in the background comes with the next stages.

## D2: approve with your fingerprint, and STOP

**STOP.** The red **Stop** at the top of the conversation (it asks once) does what Ctrl+Alt+K does on the PC: every running
action halts within a second and the PC goes to Safe Mode. The PC then stops listening to the phone too, until you run
`kairu resume` at the PC.

**Fingerprint approval** (Android 13 or newer; ADR-035):

1. On the phone: **••• → Turn on fingerprint approval**. The phone makes a key inside Android's Keystore that only signs
   right after your fingerprint, and asks the PC to accept it.
2. At the PC: `kairu link waiting` shows `device.approver`; `kairu link approve N` with `yes` and your PIN. Only your PIN at the
   PC can turn it on.
3. From then on, when something you ask from the phone is High, the phone shows Guardian's card: the action, its details,
   the time left, **Approve with fingerprint** and **Refuse**. Your fingerprint signs exactly that request, once.

The PC accepts the signature only from that phone's own key, only for a request that same phone made and that is still
waiting, and only for exactly the action and details it shows. What you ask at the PC still needs your PIN at the PC.
Critical never asks. If you add or remove a fingerprint on the phone, the key ends: turn it on again. Unpairing deletes it.

## D3: control your PC from the phone

Type an order on the phone as you would in the Kairu bar: "open Notepad and set volume to 20", "how much RAM is free?",
"restart". It goes to the PC as `task.order` (Low), and the PC runs the bar's own task core with it, so Guardian decides
every step as if you had typed it at the PC. A plan of more than one step shows on the phone first ("On it: open Notepad →
volume 20"), then the answer comes back. A High step shows its card on the phone (approve with your fingerprint, or with
`kairu link approve N` and your PIN at the PC). A warning that needs "yes" (like turning Wi-Fi off) isn't answered from the
phone, so that step isn't done. Questions work too: the task core asks the brain, as the bar does.

## D4: missions that wait for your PC

Under the box, pick **Now** (runs at once; the PC must be on) or **Mission (waits for PC)**. A mission is the same order,
sent as a Link `mission`: it waits in the Gate up to 12 hours while the PC is off, asleep or out of Wi-Fi, and when Guardian
next runs it says "Your mission reached the PC" and runs it through the task core, each step decided by Guardian as in D3.
A High step still shows its card (your fingerprint, or `kairu link approve N` with the PIN at the PC) and waits 10 minutes;
nobody there means it isn't done. A mission older than 12 hours is never run. Only an order can ride on a mission: a
plain-text mission (an old phone, or the test client) is still only kept as a request, and its words stay in the receiver.
The order's words go to the task core only, and Guardian's audit log keeps a hash. Research questions work in either mode:
the task core asks the brain (and live research when `research.enabled` is on), as the bar does.

## D5, first part: the phone answers a few things itself

With **Now** picked, the phone answers these itself, with the PC off and no internet: the time ("what time is it?"), the
date, the battery ("battery", "how much battery is left?"), "what can you do?" and "is my PC connected?". It only reads
its own clock and battery and answers in words; it asks for no new permission and acts on nothing. Everything else goes to
the PC as before. Still to come in D5: free cloud AI with the privacy filter on the phone, and the small offline model
(about 0.6 GB, downloaded on Wi-Fi).

**Gate test (this part):** put the phone in airplane mode and ask "what time is it?", "battery" and "what can you do?": three
answers at once. "open Notepad" in airplane mode: "Not sent…" (it needs the Gate).

## D7, first part: skills on the phone itself

With **Now** picked, these happen on the phone, not the PC. Each one only opens an app with the work ready: Kairu never
sends a message or makes a call by itself, **you** press Send or Call. So the app asks for no SMS, call or contacts
or call permission. The clock's alarm permission is granted at install with no prompt. **Contacts** is asked once, the first
time you use a name ("call Mom"): the app only reads names and numbers, on the phone.

| Say or type | What happens |
| --- | --- |
| `open WhatsApp`, `open Instagram`, `open the camera`, `open Maps`, `open Play Store` | it opens on the phone |
| `open YouTube on my phone` (also Chrome, Gmail, Spotify, Settings) | the PC has these too, so only "on my phone" opens them here; `open YouTube` goes to the PC |
| `call 98765 43210`, `call Mom` | the dialer opens with the number; you press Call |
| `text Rahul I'll be late`, `message Rahul Sharma saying Reached` | Messages opens to Rahul with the text; you press Send |
| `WhatsApp Rahul saying Meet at 5` | WhatsApp opens Rahul's chat with the text; you press Send |
| `text 9876543210 I'll be late` | Messages opens with the text; you press Send |
| `WhatsApp: I'll be late` | WhatsApp opens with the text; you pick the chat and press Send |
| `set an alarm for 6:30 am`, `remind me at 5 pm to call Mom`, `remind me to drink water at 9:15 pm` | the clock app sets the alarm |
| `remind me in 10 minutes to check the rice`, `set a timer for 90 seconds` | the clock app starts a timer |

Two people match a name ("Rahul")? Kairu lists them and asks for the full name. Not in D7 now: reading SMS (Android blocks it
for apps installed outside the Play Store).

**Gate test (this part):** each line of the table once: the right app opens with the work ready, and nothing is sent or
called until you press the button. `open Notepad` still goes to the PC.

## D6, first part: talk to Kairu on the phone

Tap **🎤** next to the box and speak; your words show live above the box (🎙), and **■** stops it. Kairu listens with the
phone's own **on-device** speech engine (the offline English (India) pack in Google Voice Typing), so no sound leaves the
phone. It asks once for **Microphone**; the mic opens only after your tap (or, in a conversation, after Kairu's spoken answer),
for one sentence, and is let go as soon as that sentence is heard. Nothing is recorded or kept. (A phone without an
on-device engine uses Android's speech screen instead.) What it heard is sent exactly like typed words: phone skills and the
phone's own answers stay on the phone, everything else goes to the PC with **Now** or **Mission** as picked. After a spoken
order (with **Now**), Kairu speaks its answer with Android's voice, short, and then **listens again**, so you can keep
talking; **"thank you"** ends it ("You're welcome"), and so do silence and ■. A spoken "yes" or PIN is only words, never an
approval: approvals are the card's buttons and your fingerprint, or the PIN typed at the PC.

**One-time setting** if it says "Didn't catch that" every time: Settings → Google → Voice (or "Speech") → Offline speech
recognition → download **English (India)**.

Still to come in D6: the floating bar and "Kairu" to wake it (they need an always-on model).

**Gate test (this part):** tap 🎤, say "set a timer for 1 minute": the clock app starts a timer and Kairu says so aloud. Tap
🎤, say "how much RAM is free?": the PC answers, and the phone speaks it. In airplane mode, tap 🎤 and say "what time is it?":
it still works (offline). Tap 🎤, say "open WhatsApp", then (when it listens again) "thank you": it says "You're welcome" and
stops listening.

## Gate test D4 (from the App Master Plan: a mission waits while the PC is off and runs when it's on)

1. Update the app (`kairu phone install`). Under the box: **Now** and **Mission (waits for PC)**.
2. On the PC: `kairu guardian quit`. On the phone pick **Mission**, send "open Notepad and set volume to 20": "Mission sent…".
3. Wait a minute, then on the PC `kairu guardian run`: within a few seconds the phone says "Your mission reached the PC",
   Notepad opens, the volume is 20, and the phone says so.
4. Pick **Now**, send "who won yesterday's T20 match?" (with `research.enabled: true`): an answer comes back.
5. Mission: "restart": the card appears on the phone. **Refuse**: nothing restarts.

## Gate test D3 (from the App Master Plan: three tasks done from the phone; High ones ask for the fingerprint)

1. On the phone: "open Notepad and set volume to 20": Notepad opens, the volume is 20, and the phone says so.
2. "how much RAM is free?": the answer comes back.
3. "close Notepad": it closes.
4. "restart": the card appears. **Refuse**: "Not done: you refused it." Nothing restarts.
5. Your Stop button still works while an order runs.

## Gate test D2 (from the App Master Plan: a PC High action approved by fingerprint; a fake approval refused; Critical has no button; phone STOP halts a PC task)

Until D3 lets you type orders on the phone, the High request in step 2 comes from the old stand-in phone's command form.
Run it on the PC in a second terminal, paired as a second device, or re-test with the real phone once D3 is in.

1. Turn on fingerprint approval (above), then `kairu link approve N` with `yes` and your PIN. The phone says fingerprint
   approval is on.
2. Plug the PC in. Make a High request from the phone (after D3: type `mission mode on`). The card appears on the phone.
3. **Approve with fingerprint**: it starts. `kairu audit show -n 10`: the approval row says `how: fingerprint on dev-…`.
4. A fake: another request, then **••• → Test: send my last message again**: the PC ignores the replay, and nothing extra runs.
5. Ask for something Critical: the PC refuses it at once. No card, no button.
6. Start something on the PC, then press **Stop** on the phone: it halts within a second, and the PC is in Safe Mode.
   Run `kairu resume` at the PC.
7. `py -3.12 tools\check_guardian.py`: every test passes.

## Gate test D1 (from the App Master Plan: pair by QR; ask, the PC answers; old or copied messages refused; Termux removed)

1. Pair by QR as above. `kairu device list` shows the phone's name.
2. On the phone, ask "who is the prime minister of India": a short answer comes back.
3. Tap **status**: "PC status: Kairu on your PC is running …".
4. **••• → Test: send my last message again**: no answer comes. On the PC, `kairu audit show -n 10` shows it refused as
   `replayed`.
5. Remove the Termux stand-in: `kairu device remove dev-e66e99310c81c6b6`. `kairu device list` shows only the new phone.
6. Close and open the app: the conversation is still there and the dot is green (connected).
7. `py -3.12 tools\check_guardian.py`: every test passes.

## Gate test D0

1. `kairu phone status`: adb is found and the phone is connected.
2. Download the newest `kairu-phone` artifact from GitHub, then `kairu phone install`: "Kairu is on your phone".
3. On the phone: the Kairu icon (black tile, white ring) is in the app drawer. Open it: the logo, "Kairu", and
   "Not paired yet" with the version number.
4. Install the same build again: it updates in place (no uninstall needed).
5. `py -3.12 tools\check_guardian.py`: every test passes.
