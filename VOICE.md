# Kairu's light voice (Sprint Day 2)

You switch the mic on in the Kairu bar, say "Kairu" (or press Ctrl+Alt+V), and talk. Your words appear in the bar once Kairu
has heard them (Whisper hears each sentence whole), each order goes to the same task core as a typed one, Guardian decides every step, and Kairu answers aloud the Tenmin
way, in a natural offline voice (Piper). Everything runs on this PC, offline, on the current 7.7 GB of RAM: no sound and no
words ever leave it.

Built per *Staged Implementation Plan v1.8* (section 4a), ADR-029 item 1 ("voice before the RAM upgrade, light") and the
owner's Tenmin rule (22-24 Oct 2026). The full voice (your-voice-only check, a bigger model) still comes after the RAM upgrade.

## Set it up (once)

In your Guardian folder:

```
kairu voice setup            the speech model (Whisper base.en), Piper and Kairu's voices, each SHA-256 checked
kairu voice status           the voice switch, the engine and its model, Piper and your voice, the key, and Windows' microphone setting
```

If your Guardian folder had voice before 10 Nov 2026, first install the new package into it (faster-whisper, see Licences):
`.venv-guardian\Scripts\python -m pip install -e .` in your Guardian folder. If you ran the hearing test there, Whisper
base.en (and tiny.en) are already in place and `kairu voice setup` finds them.

Setup is yours to run; it is never a Kairu action (no executor, skill or request can start it). It downloads from the
official sources only, each file checked against a SHA-256 pinned in `kairu/voice/models.py`, into Guardian's data folder
(`data/voice/`). A file with the wrong hash, or one sent from anywhere else, is deleted and nothing is unpacked. Nothing of it
goes into the repository (`.gitignore`).

| What | From | Size |
| --- | --- | --- |
| Speech model: Whisper `base.en` for faster-whisper (Systran/faster-whisper-base.en, pinned commit) | huggingface.co | 141.0 MiB |
| Only with `voice.engine: whisper-tiny.en`: Whisper `tiny.en` (Systran/faster-whisper-tiny.en, pinned commit) | huggingface.co | 74.2 MiB |
| Only for the fallback (`voice.engine: vosk`, then `kairu voice setup --model small-en-us`): `vosk-model-small-en-us-0.15` | alphacephei.com | 39.3 MiB |
| Piper `2023.11.14-2`, Windows build | github.com/rhasspy/piper (release files) | 21.4 MiB |
| The one voice you picked (`voice.voice`), medium quality | huggingface.co/rhasspy/piper-voices, v1.0.0 | 60-75 MiB |

The 16 voices (`kairu voice status` names yours; `voice.voice` in config.yaml):

| Voices | File | Size |
| --- | --- | --- |
| `indian-svbi`, `indian-tni` (women), `indian-asi`, `indian-rrbi` (men): Indian English, L2-ARCTIC speakers | `en_US-l2arctic-medium`, one file | 73.2 MiB |
| `us-libritts-1093`, `us-libritts-3905` (women), `us-libritts-6694`, `us-libritts-3490` (men): US English | `en_US-libritts_r-medium`, one file | 74.9 MiB |
| `us-kristin` (woman), `us-ryan`, `us-joe` (men): US English | one file each | 60.3-60.6 MiB |
| `us-hfc-female`: US English, woman | `en_US-hfc_female-medium` | 60.3 MiB |
| `uk-alba` (Scottish), `uk-cori` (women), `uk-northern-male`: British English | one file each | 60.3-60.6 MiB |
| `uk-jenny`: British English, woman, "Jenny (Dioco)" | `en_GB-jenny_dioco-medium` | 60.3 MiB |

Then turn voice on in `config.yaml` (it ships off) and restart Guardian and the bar:

```yaml
voice:
  enabled: true
  # engine: whisper-base.en  # how Kairu hears you: whisper-base.en (the default; "whisper" means it too), whisper-tiny.en
  #                          # (smaller, heard you less well), or vosk (the small Vosk model, the fallback)
  # model: small-en-us   # the Vosk model, with engine: vosk only; or small-en-in (then run `kairu voice setup --model ...`)
  # key: V               # Ctrl+Alt+this letter starts listening; never K, and not tasks.bar_key
  # voice: indian-svbi   # Kairu's voice, one of the 16 below; the gate test lets you hear each, pick, and saves it here
```

```
kairu guardian quit
kairu guardian run
kairu bar quit
kairu bar
```

## Using it

| You | Kairu |
| --- | --- |
| Click **Mic** in the bar, or press **Ctrl+Alt+V** | The mic comes on ("Mic on", blue since W2), and Kairu says "Go ahead, I'm listening." |
| "Kairu" | Wakes up: the bar opens and says "Go ahead, I'm listening." |
| "Kairu, open Chrome and set volume to 30" | Both steps, in order, each through Guardian. A short line in the bar, **and no speech**: finished tasks stay quiet |
| Keep talking | Each order runs as soon as you pause (about 0.6 s), while you say the next |
| "um", "okay so" | Ignored |
| "Kairu, open" | One short question ("Open what?"), never a guess |
| "Kairu, set the volume to 230" (Whisper heard "to 30" as "230") | "Did you mean 30?" and nothing changes. Say it again with the number ("volume 30"); a spoken "yes" is never an order, so Kairu asks for that |
| "Kairu, search the volume to 30" (tiny.en heard your "set the volume" so) | Never a search: "Did you mean set the volume to 30?" and nothing runs. The same for brightness and Wi-Fi ("Did you mean turn Wi-Fi off?"). Say the order again ("set the volume to 30"); a spoken "yes" is never an order. To search the web for such a thing, type it in the bar |
| "Kairu, who is the prime minister of India?" | "Narendra Modi. Want to know more about him?" The full answer is shown in the bar |
| "explain it simply", "explain like a teacher" | Explain Mode: simpler words and one small example, then one follow-up |
| "Kairu, search the weather" | Goes to `brain.ask` (with web research if it is on); the short answer is spoken and shown |
| "Kairu, restart" | The approval card opens. Only your **typed** "yes" and PIN answer it. A spoken "yes" or PIN is ignored |
| "thank you" | "You're welcome." The session ends; Kairu waits for "Kairu" again |
| 30 seconds without a word | The session ends quietly |
| "Kairu, stop" (or "stop" in a session) | The same emergency stop as Ctrl+Alt+K and the bar's Stop: everything halts, the mic goes off, Safe Mode until `kairu resume` ("yes" + PIN typed) |
| Click **Mic on** again | The mic goes off |

**The mic is off** when the bar starts, and so after every restart and sign-in. It also goes off on every emergency stop,
when the PC locks or sleeps, when you sign out, and if the listener ends for any reason. Nothing turns it back on by itself.

**Only your own click or keystroke turns it on.** The mic button's own command and Ctrl+Alt+V's own handler are the only
code that calls it, and a test reads the code to check. No spoken order, Kairu action, phone message, web page or test switch
can: Guardian may be asked to run `voice.listen` by anything, but the listener first says hello to the bar with a session
token, and the bar makes a token only when you switch the mic on. A listener with any other token is refused before it opens
the microphone (a test proves it hears nothing).

**One mic for the bar and the workspace (W2, ADR-036).** The workspace has the same mic (its mic button, or Ctrl+M while its
window is in front; WORKSPACE.md). The voice link is claimed when you switch a mic on and let go when it goes off, so whichever
of the two switched on first has it; the other says "The mic is on in another Kairu window (the bar or the workspace). Switch
it off there first." Every rule here holds in both.

**If Windows' microphone privacy setting blocks the mic,** the bar says so plainly ("Windows' privacy setting blocks the
microphone for desktop apps (Settings > Privacy & security > Microphone > ...)"). Kairu only reads the setting, never changes
it, and never tries another way in. If the microphone sends only silence (for example, its volume is at 0 %), the bar says that too.

## Tenmin: how Kairu talks

The owner's rule, in `kairu/brain/tenmin.py`. Every spoken answer follows it:

- **Warm and encouraging, like a kind teacher**; explains simply.
- **Correct and short.** A simple question gets just the answer: "who is the prime minister of India" is only the name.
- **Kairu waits, answers, then offers exactly one short follow-up question.** It never leads, and never asks two.
- **Short, quick turns**; no speeches.
- **Explain Mode**: "explain it simply" or "explain like a teacher" gives simpler words and one small example.
- **Finished tasks stay quiet** (K-7): a short line in the bar, no speech. Kairu speaks only to answer or to ask.

Two halves keep it. The rules go to the AI with every question (the brain's own instructions, `kairu/brain/gateway.py`), so
the answer is written this way; Explain Mode adds "simple words, at most three short sentences, one small example". Then
`tenmin.spoken()` holds every spoken answer to it, whatever the AI wrote: the answer first and short, exactly one short
follow-up question at the end, no second question, no lists, links, notes in brackets or markdown, no "Great question!" first.
The whole answer is still shown in the bar; only what is said aloud is cut.

The Tenmin tests use replies written the way the free models answer, not recorded from a live provider, so **your gate's
Tenmin step, with real AI answers, is the real check**. If you say yes there, the gate keeps those three replies (text only,
to public questions it chose) in `tests_kairu/tenmin_real_replies.json`, as test inputs for later.

## How Kairu sounds (voice v2, 14 Nov 2026)

On your word of 14 Nov ("no need to wait for RAM, make it complete" and "change the voice, I don't like it"), built on Piper,
with no new download and no new program:

- **A new voice by default: `uk-jenny`** (British English, female). `indian-svbi`, the voice before, is still there if you
  want it back. **`kairu voice try --voices`** says one line in each of the 16 voices, numbered, so you can pick the one you
  like; put its name as `voice:` under `voice:` in config.yaml and restart Guardian.
- **Tenmin's delivery, `voice.style`** (warm by default): Kairu says the answer a little brighter and quicker, takes a short
  breath, then asks the one follow-up question warmer and slower, the way a teacher asks. It uses Piper's own three dials
  (speed, how much the tone moves, how much each sound's length varies), each part its own run of Piper, one at a time.
  `lively` is quicker and brighter, `calm` slower and softer, `plain` is Piper as before. **`kairu voice try`** says the same
  line in all four, so you can hear the difference; `--style calm` only that one.
- Nothing else changed: the same rules, the same memory limits (one Piper at a time), the same Tenmin words.

**Honest limits.** Piper is a small offline voice: the styles make it livelier, but it still won't sound like a real person,
as Tenmin's voice does. A voice that sounds truly human needs a bigger neural voice model (Kokoro, for example: Apache-2.0,
about 90 MB, but it uses espeak-ng, the GPL part we kept out with piper-tts, and needs onnxruntime). That is a decision for
you (a new download and a new program), and it could not be downloaded and pinned from the machine this was built on; say
GO and it is the next step. Always listening for "Kairu" from the moment the PC starts also stays a decision for you: today's
rule is that the mic is off at every start until you switch it on.

## Kokoro: the human-sounding voice (15 Nov 2026)

On your GO of 15 Nov ("make it more like Tenmin"), Kairu speaks with **Kokoro**, a modern neural voice, instead of Piper.
Piper stays as the fallback: if Kokoro is not set up, or its program does not start, Piper says the answer.

**Set it up once (PowerShell, in the Kairu folder):**

```
py -3.12 -m pip install -e .[kokoro]       # Kokoro's program and its packages
py -3.12 -m kairu voice setup              # downloads Kokoro's model and voices (about 115 MiB), SHA-256 checked
py -3.12 -m kairu voice try --voices       # every Kokoro voice says one line: pick the one you like
py -3.12 -m kairu voice try                # your voice in the four styles
```

Then, under `voice:` in config.yaml: `kokoro_voice: <the name>` (af_heart by default), and restart Guardian.
`tts: piper` goes back to Piper.

| | |
| --- | --- |
| Model | Kokoro-82M, int8 ONNX (`kokoro-v1.0.int8.onnx`, 88 MiB) and `voices-v1.0.bin` (27 MiB), from the official kokoro-onnx release `model-files-v1.0` on GitHub, each SHA-256 pinned in kairu/voice/models.py |
| Voices | 27 English voices: American and British, women and men (`kairu voice try --voices`) |
| Licences | Kokoro's weights: Apache-2.0. kokoro-onnx: MIT. onnxruntime: MIT. **phonemizer and espeak-ng: GPL-3.0**: they run only in Kokoro's own program (kairu/voice/kokoro_worker.py), as espeak-ng already does inside piper.exe; no other Kairu program loads them (a test reads the code) |
| Memory | About 300 MB while Kokoro speaks (measured on the build machine), nothing at rest: its program starts for each answer and ends with it. The voice limit while speaking is 600 MB with Kokoro (your OK of 15 Nov), 400 MB with Piper |
| Speed | On the 2-core build machine: 3.9 s of work for 3.3 s of speech, the model loaded each time. Your PC should be faster; `kairu voice try` shows how it feels |
| Styles | The same four: Kokoro's one dial is speed, so the answer is said a little quicker and the follow-up question a little slower, with a breath between |

**Honest limits.** Kokoro loads its model for every answer, so the first word comes about 1-3 seconds later than with Piper.
It is still a voice made by a computer: much closer to a person than Piper, not yet exactly like Tenmin's. It speaks only
English here.

## Catching "Kairu" better, and the hearing check (15 Nov 2026)

You said Kairu often did not catch "Kairu". Three causes were in the code, and are fixed:

1. **Whisper had to be sure.** "Kairu" is a rare word, so the small Whisper model is often unsure of it, and an unsure
   "Kairu" was dropped without a sign. Now **"Kairu" said alone** opens a short window even when Whisper is unsure: Kairu
   says "Go ahead, I'm listening", and you say the order. An order heard unsure ("Kairu, delete ...") still never runs.
2. **"Hey Kairu", "Okay Kairu", "Hi Kairu"** did not wake it (Kairu had to be the very first word). Now they do.
3. **More of Whisper's spellings** count as "Kairu": Kaira, Kairi, Kaiyu, Kairos, Karoo, Kyra, Kira, Kyrie, Kayro, Cairou.

**Best way to say it:** "Kairu" (short pause) "open Chrome". The pause lets Whisper hear the name on its own.

**If it still misses you, run the check** (switch the bar's mic off first):

```
py -3.12 -m kairu voice check
```

Say "Kairu" a few times, as you normally do. For each one it prints how loud you were, what Whisper wrote, how sure it was,
and whether that wakes Kairu, and why not. Send Claude the lines: they show whether the problem is the mic level (raise it in
Settings > System > Sound > Input), the name Whisper writes, or the model. Nothing is written, sent or kept.

**Still to decide (needs your OK):** Whisper **small.en**, a bigger and much better hearing model (about 3 times base.en's
size). It would break today's rule that the voice stays under 200 MB at rest.

## Listening for your reply (15 Nov 2026)

When Kairu ends with its follow-up question ("Want to know more about it?") and your mic is on, it now listens for your
answer for **8 seconds without "Kairu"**. Say "yes" or ask the next thing, and the talk goes on as usual (30 seconds after
your last word). Say nothing, and it goes quiet. This never switches the mic on: it works only when you switched it on
yourself, and a stop, a lock or sleep still switches it off. Before, Kairu's own thinking and speaking used up the session's
time, so after a long answer you often had to say "Kairu" again.

## How it works

```
 the bar (kairu/bar/)                         Guardian                         voice.listen (kairu/voice/)
 ─────────────────────                        ────────                         ───────────────────────────
 your click / Ctrl+Alt+V ── run voice.listen {session token} ──▶ decides (Low) ──▶ starts it, in its job
 voice link (named pipe) ◀────────────── hello + token ─────────────────────────── connects; mic opens only if accepted
 shows the words         ◀────────────── what was heard, every 0.1 s ──────────── waveIn → speech gate → Whisper base.en
 task core.handle(order) ── each step: check / run ──▶ decides, runs it
 an answer: tenmin.spoken ── run voice.speak {line} ──▶ decides (Low) ──▶ piper.exe → waveOut, in your voice
 "paused" while speaking ────────────────────────────────────────────────────▶ hears silence instead of the mic
                                                                                "Kairu, stop" → the emergency stop
```

- **Hearing with Whisper** (`kairu/voice/whisper.py`, `voice.engine: whisper-base.en`, the default since 10 Nov 2026; or
  `whisper-tiny.en`, the same code with the smaller model):
  - **The speech gate** decides, a tenth of a second at a time, whether someone is speaking: the sound's level in 20 ms
    frames against the room's own steady noise (the quietest tenth of the last 3 seconds), with numpy. Two loud frames in a
    tenth of a second start an utterance; 0.6 s of quiet ends it; under 0.24 s of loud sound (a tap, a click, a cough) is
    dropped. **Whisper runs only on what the gate lets through**: in a silent room, never (measured below).
  - **Whisper base.en** (faster-whisper, int8, 2 CPU threads) hears each utterance whole once it has ended, in a thread of
    its own so the microphone is never kept waiting. It is told how Kairu's words are spelled: the prompt is the names
    ("Kairu, Notepad, Chrome.") and its hotwords are Kairu's order words (`VOCABULARY`: Kairu, volume, brightness, open,
    close, Chrome, Notepad, what's open, search, weather, Google, find, move, rename, delete, undo, thank you, stop, yes, no).
    **Words only, never a whole order**: a whole example order made it "hear" that order when it was not said (8 Nov), and
    the tests check the hint holds none and that "Kairu" alone, noise and taps give no order. It decodes greedily (no
    random retries), at most 48 tokens. Outside a session, a "Kairu" it was not sure of never wakes it; in a session,
    what it was not sure of gets "Sorry, I didn't catch that". **What Whisper itself scores as not speech is dropped
    unheard**, with nothing said back: its no-speech score over 0.6, or over 0.3 when it was also unsure of the words
    (keyboard taps that base.en wrote as "Pup, pup, pup" scored 0.84; the recorded orders 0.00-0.07).
  - Then **the same rules as Vosk**: "Kairu" must begin the utterance (Whisper's spellings of it, `split_wake`), or you
    are in a session; fillers out, levels as digits, its usual near-misses in your voice put right ("set the value to 30"
    → set the volume, "wants open" → what's open, "starts the weather" → search the weather, "said" → set, "set a volume"
    → set the volume); one short question instead of a guess.
  - **Numbers are never guessed**: a level over 100 ("volume 230", "2 30", "brightness 450") gets "Did you mean 30?" (or
    "Volume goes from 0 to 100. What level?") and nothing runs until you say the order again.
  - **A heard "search" with a setting word after it is never a search** (volume, sound, brightness, Wi-Fi anywhere after
    "search"): "Did you mean set the volume to 30?" (or "turn the volume up?", "turn Wi-Fi off?", "set the volume?") and
    nothing runs, no web search included, until you say the order again. This holds with Vosk too (it is in the words
    rules), and only for what is heard: typed orders are unchanged.
  - Your words show in the bar once heard, not live: hearing the start again every half second would cost 0.45 s of CPU
    each time. A spoken PIN's digits are never shown.
- **Hearing with Vosk** (`kairu/voice/hearing.py`, `voice.engine: vosk`, the fallback): one small Vosk model, two recognizers on the same sound. The word recognizer has the
  whole vocabulary. The wake recognizer has a tiny grammar: `cairo`, `kai ru`, `kai rue`, `carew`, `stop` and `[unk]` for
  everything else. "Kairu" is not in the model's vocabulary; these are the words it hears for it. When an utterance ends, the
  wake recognizer says whether it began with "Kairu" and where "Kairu" ended, and the words after that are the order.
- **Outside a session, an utterance without "Kairu" is dropped at once**: nothing is shown, kept or sent.
- **Words** (`kairu/voice/words.py`): fillers out, levels as digits ("thirty" → 30), the small model's usual mishearings put
  right ("said volume" → "set volume", "note pad" → "notepad"). A lone verb gets one short question. A free-form sentence that
  is neither a skill nor a question gets "Sorry, I didn't catch that", never a guess.
- **Speaking** (`kairu/voice/speak.py`): `voice.speak` starts Piper's `piper.exe` as a separate program, gives it the line as
  plain text (no markup), and plays its sound through Windows' own waveOut functions as each sentence is ready, with a 0.25 s
  pause between sentences, at Piper's natural speed. The voice is `voice.voice` in Guardian's `config.yaml`; a request never
  chooses it. Until setup has put Piper in place, Windows' own voice (SAPI) speaks instead. Kairu speaks only when you have
  been quiet for 0.6 s.
- **The mic pauses while Kairu speaks**: the bar tells the listener, which feeds the model silence instead of the microphone
  until 0.4 s after Kairu has finished, so Kairu never hears or obeys itself.
- **The microphone** (`kairu/voice/mic.py`): Windows' own waveIn functions through ctypes; 16 kHz mono, a tenth of a second at a
  time, in memory only, and wiped when it closes.

## Licences

- **faster-whisper** (MIT), the default engine's package since 10 Nov 2026, and Whisper base.en and tiny.en (MIT, OpenAI's
  weights as converted by Systran). It brings ctranslate2 (MIT), numpy (BSD), tokenizers and huggingface-hub (Apache 2.0), onnxruntime
  (MIT), tqdm (MIT/MPL 2.0) and PyAV (BSD, with FFmpeg under the LGPL): about 260 MB on disk. The listener loads only
  faster-whisper, CTranslate2, tokenizers and numpy: never PyAV (it decodes sound files; Kairu hands sound over from
  memory), the Hugging Face downloader (`kairu voice setup` downloads) or onnxruntime (the speech gate is numpy, not Silero).
- **Vosk** (Apache 2.0), the fallback engine, and its small model (Apache 2.0).
- **Piper**: the MIT-licensed build of rhasspy/piper, release 2023.11.14-2 (the project is archived; this is its last
  release). It is run as a separate program and nothing of it is imported or linked. Kairu does **not** use the `piper-tts`
  package on PyPI, which now comes from another project under GPL-3.0.
- **The Piper build bundles espeak-ng, which is GPL-3.0** (for pronunciation), and onnxruntime (MIT). It runs on your own PC,
  for personal use; Kairu does not distribute it.
- **The voices**: rhasspy/piper-voices v1.0.0, all medium quality; each voice's licence follows its recordings, as its model
  card says. Non-commercial use only, which personal use is: `indian-svbi`, `indian-tni`, `indian-asi`, `indian-rrbi`
  (L2-ARCTIC, **CC BY-NC 4.0**), `us-hfc-female` (Hi-Fi CAPTAIN, **CC BY-NC-SA 4.0**), `us-ryan` (RyanSpeech,
  **CC BY-NC-SA 4.0**). Any use: `us-kristin` and `uk-cori` (LibriVox, **public domain**), `us-joe` (**CC0**), `uk-alba`
  (**CC BY 4.0**), `uk-northern-male` (**CC BY-SA 4.0**), the four `us-libritts-*` (LibriTTS-R, **CC BY 4.0**), and
  `uk-jenny`, which asks that the voice be called "Jenny (Dioco)", as Kairu does wherever it names it. Left out for their
  licence: `amy` (no licence found for its recordings), `lessac` (a research licence, granted only to named people) and
  `alan` (its recordings are "All Rights Reserved"). The four LibriTTS-R speakers were picked by measure from every 15th of
  its 904: the darkest tone and steadiest pace, two women and two men. The four Indian voices share one file, as do the
  four LibriTTS-R ones.

## How the safety rules are kept

- **Every spoken order goes through Guardian exactly like a typed one**: the same task core, the same `GuardianClient.run`.
  Nothing in Guardian's decisions changed.
- **Voice can never approve.** A High step (sleep, restart, shutdown) opens the bar's card, answered only by your typed "yes"
  and PIN. Orders said while the card is open are dropped; a spoken "yes", "no" or string of digits is never an order. No voice
  code touches the card (a test reads the code to check).
- **Critical stays blocked.** `voice.listen` and `voice.speak` are Low, `feature: voice`, `private: true`; any other `voice.*`
  action is not in `policy.yaml`, so it is denied.
- **No sound is ever written to disk**, and no sound or transcript leaves the PC. Transcripts never reach the audit log: the
  orders' skills, `brain.ask`, `voice.listen` (its session token) and `voice.speak` (its line) are all `private: true`, so only
  hashes are kept. Tests check both, after a whole spoken session.
- **The listener runs nothing itself.** Its one deed is "Kairu, stop", which it writes straight to Guardian's database (the
  same function as the bar's Stop), so it works even while the bar is busy.
- **Its processes belong to Guardian**: an emergency stop ends `voice.listen` and `voice.speak`, with `piper.exe`.
- **The emergency stop is still under 1 second**, and Ctrl+Alt+K is untouched.

## Honest limits

- **No your-voice-only check yet.** Spoken words are data, and an order spoken by someone else, or by a video, is treated like
  yours: decided by Guardian with the same tiers (so High still needs your typed PIN). The check comes with the full voice
  after the RAM upgrade.
- **Whisper can mishear too**, mostly as near-misses of the right words; the hint and the fixes above were made from your
  own hearing test (10 Nov 2026) and from Piper's Indian English voices, not from a session of yours: the hearing test with
  the hint and your gate test are the real measure. On Piper's RRBI voice it heard "Kairu, stop" as "store" or "star"; that
  is not taken for a stop (a wrong stop puts you in Safe Mode). Ctrl+Alt+K is always the instant stop.
- **The speech gate measures loudness, not voices.** A loud room (music, a TV, someone else talking) makes Whisper run on it;
  without "Kairu" first it is still dropped, but it costs CPU (about 0.4 s of work for each sentence).
- **Your words show once heard, not word by word**, about a second after you stop.
- **Whisper's memory peak**: with base.en about 308 MiB for under a second each time it hears a sentence, and once while it
  loads when you switch the mic on; at rest it is about 182 MiB (tiny.en: 211 and 136). The same peak comes back with each
  sentence (CTranslate2 works on a 30-second window whatever you say), which is in the measures below; you allowed about 307
  for base.en (10 Nov).
- **The memory margin with base.en is thin**: 182-183 MiB at rest against 190, and 370-378 MiB while Kairu speaks against
  381 (the long Explain Mode line, the Indian voice). A longer spoken line, or a later faster-whisper, could cross it:
  `voice.engine: whisper-tiny.en` leaves about 50 MiB more.
- **The small Vosk model (the fallback) can mishear**, especially names it does not know and fast speech. It was chosen and
  tested with Windows' own (US English) voices, and it heard your own voice badly (wake word 0-4 of 10): `voice.engine: vosk`
  only if Whisper cannot run. Then `voice.model: small-en-in` is the other choice.
- **"Kairu" is heard as a sound-alike**, so a name like "Kai" or "Kyra" at the start of a sentence can wake it (see below).
- **No barge-in**: while Kairu speaks the mic is paused, so words you say over it are not heard.
- **"Kairu, stop" is heard at the end of the utterance**: with base.en about 1.6 s after you finish the word on an idle PC
  (the 0.6 s pause, then Whisper's 0.85-0.94 s), slower than tiny.en's 1.1 s; everything halts about 0.1 s after Whisper
  has heard it. While the PC is busy it will be slower: tiny.en took up to 2.2 s then, and base.en has not been measured
  busy (it does about twice tiny.en's work, so perhaps 3 s). (Vosk: about 0.9 s after the word.) You accepted the busy-PC
  time for the sprint (10 Nov); it is on the list for Phase K (Hardening). Ctrl+Alt+K and the bar's Stop are still the
  fastest.
- **Piper has no Indian English voice of its own.** `indian-svbi` is an Indian (Hindi-speaking) speaker of English from the
  L2-ARCTIC recordings, inside a US English voice.
- **The memory margin while Kairu speaks is thin**: 385 MB at worst against 400 MB (below). A longer spoken line needs more.
- **Voice is built for Windows.** On Linux the listener says there is no microphone and Piper's build is not there; the tests
  run there with recorded sounds.

## Measured while building (6-7 Nov 2026, the owner's PC, i5-1135G7, 7.7 GB, Python 3.12)

| Measure | Result |
| --- | --- |
| The voice at rest: `voice.listen`, the model, two recognizers (limit **200 MB**) | **171 MiB** (179 MB); 186 MiB on Linux (CI). vosk loads without its downloader (`load_vosk`, kairu/voice/listen.py): 10 MiB less on both |
| The voice while Kairu speaks: the listener and `voice.speak` with Piper, the Indian voice, a long Explain Mode answer (limit **400 MB**) | **364 MiB** (382 MB): listener 171 + `voice.speak` 192 |
| `voice.speak` with Piper, by voice and line (its Python and piper.exe) | short Tenmin line: 133-150 MiB; long Explain Mode line: 156 (us-hfc-female), 163 (uk-jenny), 190 (indian-svbi) |
| Piper's first sound after the line | 0.6-0.9 s once warm; 1.8-3.3 s the first time after start-up (the voice is read from disk) |
| The bar's own process with voice on (limit 60 MB) | 45 MiB |
| "Kairu, stop" during `kairu demo`, through a real test Guardian | halted **0.069 s** after the stop; the mic off |
| "Kairu, stop" heard after the word ended | 0.87 s (sound time) |
| Wake word, 180 synthetic clips (3 Windows voices × 4 ways of saying "Kairu" × 3 speeds × 5 follow-ups) | **179 woke, 1 missed** |
| "Kairu, stop", 36 of those clips | 36 stopped; **0 false stops** in the other 144 and in 120 sentences without "Kairu" |
| False wakes, 120 synthetic sentences without "Kairu" (40 × 3 voices) | **7**, all on look-alike names at the start ("Kai went…", "Kyra and Cyrus…", "Carry the bags…"); **0 of the 81 ordinary sentences** |
| Orders understood exactly after "Kairu" ("open notepad", "what time is it", "set volume to 20") | 91 of 108 (84 %); the misses are the model mishearing one synthetic voice |
| `kairu voice setup`, real downloads | model 36 s; Piper and the three voices 55 s; every SHA-256 checked |

### Whisper base.en, the default engine since your hearing re-run (10 Nov 2026, the same PC, idle: about 6 % CPU)

| Measure | Result |
| --- | --- |
| The listener at rest with Whisper base.en, after an order, through a real test Guardian (limit **190 MiB**, 200 MB), three runs | **182-183 MiB** |
| Its peak: while it loads, and for under a second each time it hears a sentence (about 307 allowed) | **308 MiB** in every run |
| While Kairu speaks: the listener and `voice.speak` with Piper, the Indian voice, the long Explain Mode line (limit **381 MiB**, 400 MB), three runs | **370-378 MiB** (180-183 + 187-197) |
| "Kairu, stop", Whisper base.en, from the end of the word, during `kairu demo`, idle PC, three runs | the stop written **1.56-1.57 s** after the word; `kairu demo` gone 0.02-0.10 s after that |
| Whisper's time per sentence (base.en, 2 threads, beam 5; tiny.en beside it) | **0.85-0.94 s** (tiny.en 0.42-0.48 s) |
| The 16 recorded test sounds, base.en with the hint | all 16 heard as Kairu should act on them |
| "Kairu" then a loud hiss, keyboard taps and a fan-like hiss (the "invents no order" test) | before the no-speech rule: base.en wrote the taps as "Pup, pup, pup, pup, pup." and the hiss as "I'm sorry."; after it, nothing at all |

Idle CPU and memory with the mic on and you silent were measured with tiny.en (below): the speech gate is the same, and
Whisper never runs in silence whichever model it is, so base.en's idle cost is the same 0.35 % of one core; its memory at
rest is base.en's 182 MiB.

### Whisper tiny.en (10 Nov 2026, the same PC; now `voice.engine: whisper-tiny.en`)

| Measure | Result |
| --- | --- |
| The listener at rest with Whisper tiny.en, after an order, through a real test Guardian (limit **200 MB**) | **135 MiB** |
| Its peak: while it loads (about 0.5 s when the mic is switched on), and for under half a second each time it hears a sentence (about 211 allowed) | **206-211 MiB** |
| While Kairu speaks: the listener and `voice.speak` with Piper, the Indian voice, the long Explain Mode line (limit **400 MB**) | **328 MiB** (135 + 193) |
| Mic on, 2 minutes of silence (a pretend mic sending silence, in real time) | Whisper ran **0** times; **0.42 s of CPU** (0.35 % of one core, 0.04 % of the PC); 119 MiB throughout |
| Mic on, 2 minutes, the real microphone in this room, nobody speaking to Kairu (three runs; the room was not always quiet: up to 2121 RMS) | Whisper ran 3, 4 and 0 times on room sounds (the gate kept 1101-1109 of 1200 tenths from it in the first two); CPU 5.55 and 6.61 s in the first two (4.6-5.5 % of one core, 0.6-0.7 % of the PC), almost all of it those 3-4 hearings; 118-154 MiB |
| "Kairu, stop" heard by Whisper, during `kairu demo`, through a real test Guardian | the stop written **0.10-0.11 s** after the words were heard; `kairu demo` gone **0.01-0.11 s** after that: **0.12-0.17 s** in all (limit 1 s) |
| "Kairu, stop", Whisper tiny.en, from the end of the word | the stop written 1.06-1.07 s after it on an idle PC (the 0.6 s pause, Whisper's 0.36 s, 0.1 s to the next tenth); **1.77-2.19 s** while Edge was busy on the PC (Whisper slower) |
| The 16 recorded test sounds (Windows' voices), Whisper tiny.en with the hint | all 16 heard as Kairu should act on them; the microphone never waited more than 12 ms |
| Whisper's time per sentence (tiny.en, 2 threads, beam 5) | 0.36-0.42 s |

In one of the real-microphone runs, room sound woke it once (a "wake" with nothing after it): whether someone said "Kairu"
or Whisper half-heard one could not be told, since no words were kept. Since then, a "Kairu" that Whisper was not sure of
never wakes it.

None of these used your voice, and nothing was played aloud while building: Piper was measured without playing, and the
speakers only with silence. The microphone was opened once, for a 2-second level check (it read 0 % input volume, since fixed).

## Proposed ADR items (for you to accept or change; the ADR register is not edited)

1. **Model: `small-en-us` (vosk-model-small-en-us-0.15) by default, `small-en-in` the other choice.** You preferred the Indian
   English model, then accepted the US one for now (7 Nov); your gate test decides. Both were tried on this PC, with the same
   hearing code and the same 300 synthetic clips:

   | | small-en-us | small-en-in |
   | --- | --- | --- |
   | "Kairu" woke it (of 180) | **179** | 106 |
   | "Kairu, stop" stopped it (of 36) | **36** | 22 |
   | False wakes (of 120 sentences without "Kairu") | **7** | 50 |

   The Indian model also lacks words Kairu needs, such as "notepad". The test voices are Windows' US English ones, which
   favours the US model. `voice.model: small-en-in` switches, after `kairu voice setup`.
2. **Wake method: a second recognizer with a small grammar** of the model's sound-alikes for "Kairu" (`cairo`, `kai ru`,
   `kai rue`, `carew`) plus `stop` and `[unk]`, on the same sound as the word recognizer; "Kairu" must begin the utterance, and
   word times say where it ends.
3. **Key: Ctrl+Alt+V**, as asked; it was free on this PC. `voice.key` (any letter but K and the bar's) if it is taken.
4. **No audio-capture package.** The microphone is read with Windows' waveIn functions through ctypes; Vosk is the only new package.
5. **"stop" alone, said within a session, is the emergency stop too**, like "Kairu, stop". Outside a session only "Kairu, stop" is.
6. **A session ends after 30 seconds without a word**, as well as on "thank you", so the mic does not keep taking orders forever.
7. **Free-form words that are neither a skill nor a question** ("to you", "go ahead") get "Sorry, I didn't catch that",
   instead of going to `brain.ask` as typed ones do: by voice, a misheard order must not become a question to the cloud.
8. **`voice.speak` is `private: true` too** (you asked it for `voice.listen`): its line may repeat your words.
9. **The listener writes "Kairu, stop" itself**, with the same function as the bar's Stop, rather than through the bar.
10. **The voice's memory limit: under 200 MB at rest (the listener only), under 400 MB while Kairu speaks** (the listener and
    `voice.speak` with Piper), instead of 300 MB for the whole (your decision, 7 Nov 2026, after Piper measured 335-367 MiB
    with the listener).
11. **Piper: the MIT Windows build of rhasspy/piper 2023.11.14-2, run as a separate program**; never the GPL `piper-tts`
    package. Its bundled espeak-ng is GPL-3.0, for personal use, not distributed.
12. **The three voices** you chose to pick from, pinned to rhasspy/piper-voices v1.0.0, and **`voice.voice`** saves your pick;
    `indian-svbi` until you pick. The gate writes your pick into `config.yaml` only after you choose it.
13. **Tenmin in code as well as in the AI's instructions**: what is said aloud is held to the rule whatever the AI writes. A
    task's result, a refusal and an error are shown and not spoken; the greeting, "You're welcome", and Kairu's short questions
    ("Open what?") are spoken, as asks and answers.
14. **Engine: Whisper base.en by default (`voice.engine: whisper-base.en`; plain `whisper` means it too), Whisper tiny.en
    (`whisper-tiny.en`) and Vosk (`vosk`, the fallback) kept as choices**. First tiny.en, after your hearing test on your own
    voice (10 Nov 2026: wake word 10/10 on both Whisper engines, Vosk 0-4/10); then base.en, after your re-run with the hint
    (10 Nov: base.en 10/10 orders, 0 % word errors; tiny.en 8/10). This replaces item 1's default; items 2 and 5 now hold for
    Vosk only (Whisper's "Kairu" is its own spelling at the start of a sentence).
15. **The hint: names as Whisper's prompt, Kairu's order words as its hotwords**, words only, never a whole order.
16. **The speech gate is numpy (loudness against the room's noise), not Silero VAD.** Silero (onnxruntime, bundled with
    faster-whisper) is better at telling a voice from other sound, but it costs about 24 MiB more: the listener measured 140
    MiB at rest and 222-230 MiB while Whisper hears, against 116 and about 205 without it. With Silero the peak with each
    sentence would be well over the 211 you allowed. **Accepted by you (10 Nov 2026): keep the loudness check.**
17. **"Did you mean 30?" is answered by saying the order again**, never by a spoken "yes" (a spoken yes is never an order).
    **Accepted by you (10 Nov 2026): keep as built.**
18. **The voice's memory with Whisper**: under 200 MB at rest and 400 MB while Kairu speaks, as before, with a short peak of
    about 211 MiB allowed, both when it loads and, for under half a second, with each sentence. **Accepted by you (10 Nov
    2026), the per-sentence peak included.** With base.en (your decision, 10 Nov): the short peak about 307 MiB, at rest
    still under 190 MiB, and under 381 MiB with Piper.
19. **"Kairu, stop" with Whisper takes about 1.1 s from the end of the word on an idle PC and up to about 2.2 s while the PC
    is busy** (everything halts within about 0.2 s of Whisper hearing it; Ctrl+Alt+K and the bar's Stop stay instant).
    **Accepted by you for the sprint (10 Nov 2026); to look at again in Phase K (Hardening)**, with the speed work there.
    With base.en: 1.56-1.57 s on an idle PC (measured); busy, not yet measured.
20. **A heard "search" with a setting word after it (volume, sound, brightness, Wi-Fi) is never a search**: "Did you mean
    set the volume to 30?" and nothing runs until you say the order again (your decision, 10 Nov 2026, after tiny.en heard
    "set the volume" as "search the volume"). A spoken yes gets "Please say it again ...". Only for what is heard, with
    either engine; a typed search is unchanged.
21. **What Whisper itself scores as not speech is dropped unheard** (no-speech over 0.6, or over 0.3 with low confidence),
    added when base.en wrote keyboard taps as "Pup, pup, pup" and a hiss as "I'm sorry." (10 Nov 2026).

## The hearing test (which engine hears you best)

The small US model was picked on synthetic American clips; it misheard "Kairu, set the volume to 30" in your voice. Before
the default engine changes, `tools/hearing_test.py` compares five offline engines on your own voice: you read 10 short orders
(the wake word, volume, open Chrome, close Notepad, what's open, the weather, brightness, thank you, stop), and for each the
test shows what each engine heard, the order Kairu would act on, a word error score, how soon after you stop its words are
ready, and its memory against the voice's limits. Your recordings stay in memory and reach each engine through a pipe;
nothing is written to disk.

```
.venv-guardian\Scripts\python tools\hearing_test.py --setup     once: .venv-hearing and the models (about 420 MiB, SHA-256 checked)
.venv-hearing\Scripts\python tools\hearing_test.py              read the 10 orders aloud
.venv-hearing\Scripts\python tools\hearing_test.py --piper      the same orders in Piper's four Indian English voices
```

**With the hint (10 Nov 2026).** Two more engines hear exactly as Kairu now does, through the listener's own code (the
speech gate, Whisper with Kairu's order words as its hint, the words rules): `whisper-base.en+hint` (Kairu's default since
your re-run on 10 Nov: 10 of 10 orders right, 0 % word errors, ready 0.50 s after you stop, steady 182 MiB, 374 MiB with
Piper) and `whisper-tiny.en+hint` (8 of 10: it turned "set the volume" into "search the volume"). To re-check them on your
voice, beside tiny.en without the hint, after `git pull` in your Guardian folder:

```
.venv-guardian\Scripts\python tools\hearing_test.py --setup
.venv-hearing\Scripts\python tools\hearing_test.py --engines whisper-tiny.en,whisper-tiny.en+hint,whisper-base.en+hint
```

On Piper's four Indian voices, with 8 more orders and sentences (72 in all, 10 Nov), tiny.en got 41 right with the names
alone and 56 with the hint, and invented no order from "Kairu" alone, three sentences without "Kairu", hiss, hum or taps.

| Engine | Licence | Memory (steady / peak while loading) |
| --- | --- | --- |
| Vosk `vosk-model-small-en-us-0.15` (the fallback) | Apache-2.0 | 145 / 175 MiB |
| Vosk `vosk-model-small-en-in-0.4` (Indian English) | Apache-2.0 | 112 / 139 MiB |
| Vosk `vosk-model-en-us-0.22-lgraph` (the smallest big model) | Apache-2.0 | 364 / 476 MiB: over |
| Whisper `tiny.en`, faster-whisper 1.2.1, int8 on the CPU | MIT (weights MIT) | 140 / 211 MiB (the short peak you allowed) |
| Whisper `base.en`, the same (the default) | MIT (weights MIT) | 182-187 / 308-374 MiB (you allowed about 307; see the measures above for the listener's own) |

faster-whisper needs ctranslate2 (MIT), onnxruntime (MIT), tokenizers and huggingface-hub (Apache-2.0) and PyAV (BSD, with
FFmpeg under the LGPL); the test installs them only into `.venv-hearing`, and PyAV is never loaded (it decodes sound files;
Kairu hands sound over from memory). Whisper's peak comes while the model loads (CTranslate2 holds its float16 weights while
making them int8), about a second after the mic is switched on; once loaded, tiny.en is 140 MiB. Whisper hears a whole
utterance at once, so live words would mean hearing the start again every half second (tiny.en: 0.45 s each time).
Whisper is told only how "Kairu", "Notepad" and "Chrome" are spelled: a whole example order in its prompt made it "hear" that
order when it was not said.

## The gate test (you, about 20 minutes)

After `kairu voice setup`, voice on, Guardian and the bar restarted:

```
.venv-guardian\Scripts\python tools\sprint_day2_gate.py
```

It walks you through 11 steps and prints PASS or FAIL for each; `--step N` runs one again. Step 1: Enter keeps Kairu's
voice as it is (`indian-svbi`, the default); type `p` instead to hear the 16 voices, pick one and save it as `voice.voice`
(Guardian and the bar then start again so they use it). Step 6: Kairu answers three questions aloud and you judge only
whether each is short; the expressive Tenmin-like voice comes after the phone app (10 Nov 2026), so nothing new is built for
it now. The tool waits for each spoken order
to reach Guardian, never hears you itself and never types into the bar; typing into its window never answers a question. It
puts your volume back afterwards. Step 9 ends in Safe Mode, and it asks for your typed "yes" and PIN to leave it.

## Files

```
kairu/voice/
  whisper.py   the default hearing: the speech gate, Whisper base.en (or tiny.en) and its hint, then the same events as hearing.py
  hearing.py   the fallback (Vosk): sound in, events out: the two recognizers, the wake word, sessions, "thank you", "Kairu, stop"
  words.py     what was heard, made into an order: fillers, numbers, mishearings, the one short question
  listen.py    voice.listen: the mic, the model and the voice link; opens the mic only for the bar's token
  speak.py     voice.speak: Piper (piper.exe) to waveOut; Windows' own voice until Piper is set up
  mic.py       waveIn through ctypes, Windows' privacy setting (read only), the tests' pretend mic
  link.py      the bar's private line to its listener
  models.py    the model, Piper and the three voices, pinned, and `kairu voice setup`
kairu/brain/tenmin.py   Tenmin: the AI's instructions and the rules for every spoken answer
kairu/bar/
  voice.py          the mic switch, orders one at a time, Tenmin answers aloud, mic off on every stop
  session_watch.py  lock, sign-out and sleep turn the mic off
tests_kairu/voice/  the recorded test sounds (Windows' own voices; make.ps1 makes them)
tools/sprint_day2_gate.py   the gate test
tools/hearing_test.py       which engine hears you best (nothing is written to disk)
```


## The top hearing model, listening from the start, and barge-in (15 Nov 2026)

Your GO of 15 Nov 2026: "I want the top hearing one", "barge-in" and "listen from PC start".

**The top hearing model.** `voice.engine` can now be `whisper-large-v3-turbo` (the most accurate that still answers
quickly on a laptop CPU; about 1.6 GB on disk, about 1 GB of memory while it runs), `whisper-distil-large-v3` (English
only, faster), `whisper-medium.en` or `whisper-small.en`. This ends the old "voice under 200 MB at rest" rule, with your
OK. Every file is still pinned (a commit and each file's SHA-256), in `kairu/voice/whisper_pins.json`:

```
py -3.12 tools\pin_whisper.py     # once: reads Hugging Face's own file list at one commit; downloads no model
git add kairu\voice\whisper_pins.json   # review it like code, in a pull request
notepad config.yaml               # under voice:   engine: whisper-large-v3-turbo
py -3.12 -m kairu voice setup     # downloads exactly the pinned files, each SHA-256 checked
py -3.12 -m kairu guardian quit; py -3.12 -m kairu guardian run
```

Without a pin, setup refuses and says how to make one. The bigger models run with 4 threads (base.en and tiny.en keep 2).
If large-v3-turbo is too slow on your PC (`kairu voice check` shows the time), use `whisper-distil-large-v3`.

**Listening from the start** (`voice.listen_at_start: true`, off unless you set it). The bar switches the mic on by itself
when it starts and when you unlock the PC or sign in, and listens for "Kairu" only: no session opens by itself, the bar does
not pop up. It waits up to 2 minutes for Guardian. It still goes off when the PC locks or sleeps, on every stop, and it never
comes back on by itself after an emergency stop (Safe Mode): you resume and switch it on yourself. Only the bar's start and
your unlock call it (a test reads the code to check).

**Barge-in** (`voice.barge_in: true`, off unless you set it; Whisper engines only). While Kairu speaks, the bar tells the
listener what it is saying and the listener keeps hearing. What sounds like Kairu's own words (60 % or more of the words
heard are words it is saying) is left out, so it never takes its own voice as an order. When you talk over it ("wait",
"hold on", "Kairu, what time is it", any two or more words Whisper is sure of), Kairu stops talking at once; the answer stays
in the bar. "wait" and "hold on" only stop it; an order goes on as an order. "Kairu, stop" is still the emergency stop.
Laptop speakers close to the mic can still fool the echo rule: if Kairu stops itself, use headphones or set it back to false.

## Live words in the bar, as you speak (15 Nov 2026)

Your GO of 15 Nov 2026: "like Google: while we speak, the words appear", every 0.20 seconds.

**`voice.live_caption_every: 0.20`** (seconds; 0 or left out: off; 0.1 to 2; Whisper engines only, Vosk always showed its
own). While you are still speaking, Whisper hears what you have said so far five times a second, and the bar's words line
shows it in grey with "…" ("open", "open note", "open notepad …"). When you stop, Whisper hears the whole sentence once more
and its words replace the grey ones in white; only that whole sentence is ever an order, a stop or a wake.

- The same rules as the white words: outside a session nothing shows until Whisper is sure you began with "Kairu"; a spoken
  yes or PIN never shows; Kairu's own voice (barge-in) never shows; nothing is written, kept or sent.
- Never piled up: if Whisper is still busy with the last look (a big model on a laptop CPU), the next one waits, so the
  bar shows the words as fast as your PC can and is never behind. A whole sentence always goes before a live look.
- It costs CPU while you speak (none in silence: the speech gate still keeps Whisper idle). On `whisper-small.en` it keeps
  up; with large-v3-turbo the grey words come less often than five times a second. If the PC feels slow while you talk, set
  0.5 or 1.

```
notepad config.yaml               # under voice:   live_caption_every: 0.20
py -3.12 -m kairu guardian quit; py -3.12 -m kairu guardian run
```

**Quick orders** (your "it must work fast", 15 Nov 2026; needs live words on). Before, "Kairu, open Edge" waited for a 0.6 s
pause, then Whisper heard the whole sentence again (often behind a live look): 3-5 s before Edge came. Now, once you have
been quiet for 0.2 s, Whisper takes one closing look at everything you said. If it is a short, harmless order and Whisper
is sure, it goes at once:

- open (or launch, start) an app, by one or two words: "open Edge", "open Microsoft Edge"
- the volume or brightness: "set the volume to 30", "volume up", "brightness 40", "mute"
- "what's open"

That closing look is then used as the whole sentence (same sound), so Whisper never hears it twice and the order never
runs twice. If you said more after a short pause ("open Edge … and close Notepad"), Edge opens and only "close Notepad" is
sent. Everything else (close, delete, files, typing, search, restart, anything with a card) still waits for the whole
sentence, and Guardian decides every step as always. A short pause in the middle ("open Google … Chrome") can start the
first part: say app names in one go.

What is left after this is Guardian starting the action (about half a second) and the app's own start. For Edge, turn on
**Startup boost** (Edge: `edge://settings/system`): Edge stays ready in the background and opens almost at once.

## Fast orders: Vosk beside Whisper (15 Nov 2026)

Your laptop test of 15 Nov: still too slow ("in Claude's mic it works within 0.5 s"). The reason: Whisper always works on a
30-second window, so each look costs about a second on a laptop CPU, however short the order; the live looks and the
closing look queued behind each other. Claude's mic hears in the cloud; Kairu's hearing stays on your PC, so instead:

**`voice.fast_orders: true`**: the small Vosk model (voice.model, 40 MB, `kairu voice setup` downloads it) hears beside
Whisper, as the sound comes, for almost no CPU.

- The grey live words come from Vosk, word by word, as you speak.
- A second Vosk recognizer knows only "Kairu", the quick order words, about 45 app names and numbers (anything else is
  "[unk]"). 0.2 s after you stop, its words are read in a few milliseconds: if every word is a quick-order word, Vosk is
  sure of each, and it began with "Kairu" (or you are in a session), the order goes at once. "Kairu, open Edge" should start
  about 0.3 s after you stop speaking, then Guardian and Edge's own start.
- Whisper takes no live looks any more: it hears only the whole sentence, for every other order and to put right what Vosk
  heard. The quick order is never sent twice.
- App names Vosk does not know (not in its list) still work: they wait for Whisper, as before.
- Indian English: `model: small-en-in` under voice: may hear you better; `kairu voice setup` then downloads that one.

## Only your voice (15 Nov 2026)

The last item of the Tenmin voice list. **`voice.only_my_voice: true`**, after `kairu voice enroll`:

```
py -3.12 -m kairu voice setup     # also downloads vosk-model-spk-0.4 (14 MB), SHA-256 checked
py -3.12 -m kairu voice enroll    # switch the bar's mic off first; say the 5 sentences it shows
notepad config.yaml               # under voice:   only_my_voice: true
py -3.12 -m kairu guardian quit; py -3.12 -m kairu guardian run
```

- `kairu voice enroll` keeps only a voice print: the average of 128 numbers per sentence, from Vosk's speaker model, in
  data/voice/my-voice.json. No sound, no words. It prints how close each sentence was (Kairu takes 0.50 or more as you).
  `kairu voice enroll --forget` deletes it.
- Then every utterance's voice print is compared with yours. Not yours: never an order, a wake or an answer; the bar says
  "That didn't sound like your voice". Too short to tell (under about 0.3 s of voice, was 0.6 s until 16 Nov 2026): treated as not yours, "say it a
  little longer". "Kairu, stop" works from anyone, always.
- It fails closed: with only_my_voice on but no voice print or models, the mic does not switch on and the bar says why.
- Honest limit: a voice print is not a password. A recording of you, or someone with a very similar voice, can pass; High
  steps still need your typed "yes" and PIN. If it often says "not your voice" to you, run `kairu voice enroll` again in
  your usual room, or tell me and the 0.50 line can be lowered.
- The speaker model's SHA-256 is pinned from a Hugging Face copy (alphacephei publishes no hashes); setup downloads only
  from alphacephei.com and refuses the file unless it is that same file.

## Your voice over the room (16 Nov 2026)

Laptop test, 16 Nov 2026: "it hears me but at the same time the sound of my surroundings, so it mixes and captures wrong".
The speech gate (kairu/voice/whisper.py, SpeechGate) used to start an utterance on any sound three times louder than the
room's quietest noise, and keep it going until 0.6 s of quiet: people, a TV or traffic nearby kept your utterance open and
Whisper wrote them down with your words. Now, with numpy only (no new package, no model):

- **Your level.** You talk close to the microphone, so your words are much louder than sound further away. After two
  utterances the gate knows how loud you are. Sound quieter than a quarter of that (about -12 dB) never starts an utterance,
  and inside one, frames quieter than 30% of your words (about -10 dB) count as quiet, so it ends 0.6 s after you stop
  talking, not when the room goes quiet. Your level fades during quiet (halves in about 35 s), so moving away from the
  microphone never locks you out: say it once more, a little louder.
- **What Whisper hears.** A cleaned copy of the utterance: the room turned down 20 dB between your words (60 ms kept around
  them, so word edges are never cut), and the room's steady noise (a fan, AC, traffic hum), learned from quiet moments, taken
  out of every moment. The copy is in memory only, like the sound itself; nothing is written or sent. `kairu voice check`
  prints what Whisper heard from the same cleaned copy, so it shows exactly what the listener gets.
- Not changed: the fast lane (Vosk) and your voice print still get the sound as it came, and every "heard" rule stays.
  For people talking near you, also turn on "only your voice" (`kairu voice enroll`, then `voice.only_my_voice: true`):
  then a sentence in someone else's voice is never an order.

Settings live in kairu/voice/whisper.py (NEAR_SHARE, START_SHARE, ROOM_DOWN, NOISE_OVER). Tests: tests_kairu/test_voice_room.py
(made-up sound: your voice, people further away, a fan).


## Gemini hearing (voice.hearing: gemini, the owner's GO of 16 Nov 2026)

**Why.** On the laptop, Whisper took 6 s a sentence with little memory free, and people talking nearby were written down
with your words. Google's Gemini hears each sentence on Google's servers in about a second, and is told to write only the
closest speaker.

**What it does.** The speech gate still decides when you start and stop, and still turns the room down (SpeechGate.clean).
Each utterance is then sent once to Gemini (`generativelanguage.googleapis.com`, model `gemini-flash-lite-latest` unless
`voice.gemini_model` names another), and the words come back to Kairu's own rules: "Kairu" first, the order to the task core
and Guardian, exactly as Whisper's words. No live grey words with Gemini (each would be one more request; the free limit is
per minute); the fast lane (Vosk) still gives them if `fast_orders: true`.

**What leaves the PC.** Only that utterance's sound, as a WAV in memory, to Google, with your key. Nothing is written to
disk. Google's free tier may use what is sent to improve its products (https://ai.google.dev/gemini-api/terms): don't speak
anything private while it is on. A spoken "yes" or PIN is still never an approval.

**If Gemini can't hear** (no internet, a refused key, the free limit), that sentence is heard by the offline Whisper (loaded
only then), and Gemini is left alone for a minute. So the demo never goes deaf.

**Turn it on (5 minutes):**
1. A free key: https://aistudio.google.com/apikey → Create API key (starts with `AIza`).
2. `py -3.12 -m kairu provider add gemini` → "yes" and your PIN → paste the key (it isn't shown).
3. In config.yaml under `voice:` → `hearing: gemini` (keep `engine: whisper-base.en` for the fallback).
4. Restart Guardian and the bar. `voice.hearing: local` turns it off again.

Files: kairu/voice/gemini.py, kairu/voice/listen.py (`_gemini_hearing`), kairu/config.py, tests_kairu/test_voice_gemini.py.


## The camera check (voice.camera: true, the owner's GO of 16 Nov 2026)

**Why.** The laptop mic hears everyone in the room; people talking nearby were taken for you. With this on, the camera
watches your mouth while the mic is on, and a sentence your lips didn't say is never an order, a wake or an answer.

**What it says** when a sentence ends (kairu/voice/lips.py): "yours" (a face, lips moving for at least 30 % of it),
"lips still" (a face, lips not moving: someone else talked), "no face" (no face for most of it), or "unchecked" (no
pictures for that time). Not yours: the bar says "Your lips weren't moving, so that was someone else" or "I couldn't see you
at the camera". **"Kairu, stop" still works from anyone.**

**What it can't do.** When you and someone else talk at the same moment, the sound is still mixed: the check only knows
*when* you speak, not which words were yours. A mic near your mouth (earphones) is still the best fix for that.

**The pictures.** One small grey frame at a time, 10 a second, held in memory, compared with the one before, then dropped.
Never written to disk, never sent (not even with Gemini hearing: only the sound goes), never shown. The camera opens only
while the mic is on and is released when it goes off; Windows' camera light shows when it is on.

**Turn it on:** `py -3.12 -m pip install -e .[camera]` (OpenCV, about 90 MB on disk, 60-80 MB of memory while on), then
`camera: true` under `voice:` in config.yaml, then `py -3.12 -m kairu guardian quit`, `py -3.12 -m kairu guardian run`,
`py -3.12 -m kairu bar quit`, `py -3.12 -m kairu bar`. Face the laptop when you speak. Without OpenCV or a camera, Kairu says
"No camera check: ..." once and hears as before.

Files: kairu/voice/lips.py, kairu/voice/whisper.py (attach_lips, _final), kairu/voice/listen.py (_camera),
tests_kairu/test_voice_camera.py.


## Short orders and your voice (16 Nov 2026)

Laptop test, 16 Nov 2026, with `only_my_voice: true`: orders ran, but "most of the time it says I couldn't tell it was you".
Vosk's speaker model counts only the 10 ms frames it is sure are speech, and Kairu asked for 60 of them (0.6 s) before it
compared your voice at all: a short order like "Kairu, open Notepad" often had fewer. Now (kairu/voice/fastlane.py):

- **Too short** is under 30 frames (about 0.3 s of voice), not 60.
- **A short order** (under 80 frames) is yours from a cosine of 0.42 (MATCH_SHORT), a longer one from 0.50 as before: a voice
  print from little sound wavers more, even for you. Someone else's voice is usually far below both. A voice print is still
  not a password: High steps still need your typed "yes" and PIN, and "Kairu, stop" still works from anyone.
- **`kairu voice enroll` now also asks for three short orders** ("Kairu, open Notepad.", "Kairu, volume fifty.", "Kairu,
  what's open?"; at least 0.6 s each), and every sentence counts the same in your voice print (each made the same length
  first), so short orders weigh as much as the long sentences. **Run `kairu voice enroll` again** to get this.

## Kairu Live in the bar (voice.live, ADR-052 proposed, the owner's GO of 18 Nov 2026)

"The screen control AI agent and the LiveKit voice part both are completed. Now connect all these things to the Kairu bar."
Kairu Live (LiveKit Agents: Deepgram Flux hears, Groq thinks, ElevenLabs speaks) now runs from the bar. You switch it on
with the bar's mic button or Ctrl+Alt+V and just talk: no "Kairu" needed. Everything it does on the PC goes through the
bar, the task core and Guardian, like a typed order, and the Ember Glow pill shows it.

| You | What happens |
| --- | --- |
| Ctrl+Alt+V (or the Mic button) | Kairu Live starts in about 10 seconds and says "Hey Saitej! Kairu here. What shall we do?" The bar says "Kairu Live is on" |
| "open notepad", "search lofi music on youtube", "set volume to 40" | The pill turns red ("Opening Notepad…"), then "Done · Notepad is open". Kairu stays quiet: a finished task is a line, not a speech |
| "who is the prime minister of India?", "what's the latest news on ...?" | Kairu answers short, Tenmin's way. For live facts it asks Kairu's research (a Guardian action) first |
| "take control and play lofi music on YouTube" | The bar's card asks for your typed `yes` (Kairu's eyes, BAR.md); then it sees, acts and sees again, and Kairu tells you how it went |
| "what do you see on my screen?" | Kairu's eyes look once, and Kairu says it |
| "what's on my screen?" | Kairu Live looks at the whole screen (every window; Kairu's own, security, terminal and money windows blacked out first) and says what is open; "what's in the app in front" looks at that one window |
| "what's on my wallpaper?" | Kairu's eyes look once at the wallpaper's picture, and Kairu says it (Kairu Live is told never to guess what is on the screen: it always looks first) |
| "remember that the hackathon is on 20 November" | Kept on this PC (memory.remember); Kairu never sees what it remembers |
| Anything High (send, submit, delete, personal words) | The card opens in the bar; you type `yes` and the PIN. While it is open, Kairu Live's mic sends silence |
| Inside "take control and ..." (ADR-054) | "Is this correct?": say "yes" or "no" (or click); "Your turn: ...": say "go on" when you are done, or "stop here". Only those words, alone, within 60 seconds of the card opening, answer that card and nothing else; a number never does. Every other card is as above |
| "Kairu, stop" (or "stop") | The emergency stop: everything halts, Safe Mode until `kairu resume`, and the mic goes off |
| Ctrl+Alt+V again (or the Mic button) | Kairu Live ends. It also ends after 10 minutes with no talk, on lock, sleep and every stop |

**The pill:** blue while you or Kairu are talking (your words in it), warm red while an order is in hand, "Done" after;
hidden when nobody is talking. In the open bar, your words are in the words line and Kairu's in the reply line.

### Switch it on (once, about 5 minutes)

It uses the Kairu Live folder you already set up on 18 Nov 2026 (its `.venv` has LiveKit, its `.env` has the keys), so
nothing new is installed.

1. In `config.yaml` (Notepad), under `voice:`:
   ```yaml
   voice:
     enabled: true
     live: true
     live_folder: C:\Users\saitej\kairu-live\kairu-live
   ```
   and, for "take control", `eyes: true` under `tasks:` (BAR.md "Kairu's eyes").
2. In PowerShell, in the Kairu folder: `py -3.12 -m kairu guardian quit`, `py -3.12 -m kairu guardian run`,
   `py -3.12 -m kairu bar quit`, `py -3.12 -m kairu bar`.
3. Don't run Kairu Live's own `agent.py console` or `agent.py dev` at the same time: one program holds the mic.

Kairu Live reads only these lines of its `.env`: `DEEPGRAM_API_KEY`, `GROQ_API_KEY`, `GOOGLE_API_KEY` (or
`GEMINI_API_KEY`), `ELEVEN_API_KEY`, `GROQ_MODEL`, `GROQ_FALLBACK_MODEL`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`,
`ELEVEN_VOICE_ID`, `ELEVEN_FALLBACK_VOICE_ID`, `ELEVEN_MODEL`, `DEEPGRAM_VOICE` and `MASTER_NAME`. Deepgram is needed, and
Groq or Gemini (Groq first); without ElevenLabs, Deepgram's Aura voice speaks. If
ElevenLabs refuses Sia on the free plan, Kairu uses Sarah and says so once, as Kairu Live did.

### It talks like your phone Kairu (18 Nov 2026)

"Make talk.py use exactly the attached agent.py's settings." kairu/live/talk.py talks exactly as your own Kairu Live
`agent.py` does on the phone; only what it does on the PC is the bar's:

- **Ears and turns:** Silero VAD; Deepgram Flux (`flux-general-en`) with the key terms "Kairu" and your name, deciding when
  your turn ends; LiveKit's own endpointing and interruption defaults (no extra limit: it waits for your whole sentence).
- **Brain:** `GEMINI_MODEL`, then `GEMINI_FALLBACK_MODEL`, each with Gemini's own defaults (no temperature), and each given
  **20 seconds** to answer (`attempt_timeout=20`), as on the phone. Preemptive replies off.
- **Voice:** ElevenLabs `ELEVEN_VOICE_ID` (Sia) if a 2-letter test answers 200, else `ELEVEN_FALLBACK_VOICE_ID` (Sarah);
  Deepgram Aura as the backup voice.
- **Retries:** the same connection options (STT 10 retries and a 20 s liveness limit, LLM 4, TTS 5, 30 errors before it
  gives up); up to 6 tool steps in one turn; emoji and markdown never spoken.
- **Words:** the phone's instructions and greeting, with the bar's tools and the bar's Guardian rules. No memory line is
  put in them (memory stays on the PC).

**Why Gemini failed in the bar ("all LLMs failed", and slow replies):** talk.py's fallback used LiveKit's own limit of
5 seconds for each model, which is also the HTTP timeout of each Gemini request. An answer that took longer (Gemini thinks
first, and gets the instructions and five tools) was dropped, the backup was dropped the same way, and the session tried
again up to 4 more times: about a minute, then "all LLMs failed". The phone gives each model 20 seconds. Tested with
LiveKit 1.8.12 and a stand-in Gemini that takes 6 seconds: before, 5 tries and "all LLMs failed"; now one call, answered in
6 seconds.

### Groq thinks (19 Nov 2026)

"The hackathon is gone, so should we leave Gemini and add the best LLM for Kairu?" Then: "GO." On the laptop, Gemini's
free tier (about 10 requests a minute, and both Gemini models share it) kept failing in a fifth of a second with "all LLMs
failed". Kairu Live now thinks with **Groq** (free, no card, about 30 requests a minute and 1,000 a day for each model):

1. `openai/gpt-oss-120b` (`GROQ_MODEL`), then `openai/gpt-oss-20b` (`GROQ_FALLBACK_MODEL`): each has its own limit, so
   the backup answers when the first says 429. Reasoning "low" (LiveKit's own choice for these), 20 s each.
2. Gemini (`GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`) only if both Groq models can't, and only if `GOOGLE_API_KEY` is there.
3. Hearing (Deepgram Flux), turn-taking, the voice (ElevenLabs) and the instructions stay as on the phone. Kairu's eyes
   ("what's on my screen") still use Gemini, in the bar (BAR.md "Kairu's eyes").

When it can't think, the bar now says the model's own reason in a few words ("Groq's free limit is used up for now
(429). Wait a minute"), not only "all LLMs failed".

**Set it up once (about 3 minutes):**
1. At https://console.groq.com, sign in, open **API Keys**, click **Create API Key**, and copy it.
2. In Notepad, open `C:\Users\saitej\kairu-live\kairu-live\.env` and add the line `GROQ_API_KEY=` with your key after it.
3. In PowerShell, in that folder: `.\.venv\Scripts\python.exe -m pip install "livekit-agents[groq]==1.8.12"`.
4. Restart the bar (`py -3.12 -m kairu bar quit`, `py -3.12 -m kairu bar`).

### What leaves the PC, and what never does

- With `voice.live` on, what you say goes to **Deepgram** (to hear the words), **Groq** (to think; **Google Gemini** only
  if Groq can't) and **ElevenLabs** (to speak Kairu's answer; Deepgram if it can't). That is the difference from the offline voice; with
  `voice.live` off (the default), nothing changes.
- Kairu Live never sees: what Kairu remembers, your talk history, window titles, what a page, a window or a command shows,
  or lists of files and apps. For those it hears only "It's shown in the Kairu bar." For a finished task it hears nothing.
  It does hear Kairu's own refusal lines, an answer the brain got from the web (marked as data), the weather, "where am
  I?" (the area and city only), and what Kairu's eyes said (kairu/live/relay.py). Each new session is told today's
  Kairu Live talk so far, kept by the bar in memory only (see "Today's talk").
- Nothing is written to disk: no sound, no words. Kairu Live's warnings stay in memory; if it ends with an error, its last
  error line (cut short) is shown in the bar and written to guardian.log.

### Today's talk: it remembers (19 Nov 2026)

"It doesn't remember the previous works, like what's my location" (you, 19 Nov 2026). Each Kairu Live session used to
start with an empty talk. Now the bar keeps **today's Kairu Live talk** (what you said, what Kairu said back; the last 30
turns) **in its own memory only**, never on disk or in the audit log, and gives it to the next session, which puts it
before its own greeting. So "where am I?" in the morning and "what's my location?" after lunch get the same answer without
looking again, and Kairu knows what it found for you earlier. These words already went to Deepgram, Groq and ElevenLabs
when they were said; nothing else is added (no memory line, talk history, window title, page or command text). A line with
a secret is never kept; `brain.talk_history: false` keeps none; "forget our talks", a new day or the bar closing ends it.

"Where am I?" said to Kairu Live goes to the bar as research, answered with the area and city from Windows' location
(RESEARCH.md "Where am I?"). "Find low cost biryani websites" goes to the web for the cheapest options (RESEARCH.md "The
cheapest options"). When Kairu's eyes can't look (for example "Google Gemini refused its key"), Kairu Live now says that
line itself, with how to fix it (`kairu provider add gemini`), instead of a vague answer.

### How the safety rules are kept

- **No authority.** kairu/live/talk.py imports nothing of Kairu (a test reads it). Its five tools (do_on_pc, take_control,
  look_at_screen, research, remember) only write an order, which the listener hands to the bar, which hands it to the task
  core: Guardian decides every step, one order at a time. A spoken yes or PIN is never an order; Kairu Live can never fill
  or press the card.
- **Only your click.** live.talk (Medium) starts only for the session token of the mic you switched on, like voice.listen;
  started any other way, it hears nothing. `voice.listen_at_start` never starts it. An emergency stop ends it and the program
  it started.
- **Only its own keys.** The talking program gets only the lines above from its `.env`, never Kairu's own settings.
- **Fails closed.** With `voice.only_my_voice` or `voice.camera` on, Kairu Live doesn't start (it can't check your voice
  print or your lips) and says so.

### The Kairu Live test (you, about 10 minutes, on your own laptop)

1. Ctrl+Alt+V. Within about 15 seconds: "Hey Saitej! Kairu here. What shall we do?" The bar says "Kairu Live is on".
2. Say "open notepad". The pill turns red, then "Done · Notepad is open"; Kairu says nothing.
3. Say "who is the prime minister of India?" Kairu answers in a sentence and asks one short question back.
4. Say "take control and search lofi music on YouTube". Type `yes` in the bar's card. Chrome goes to YouTube and searches;
   Kairu tells you it's done.
5. Say "close notepad and send ..." or anything High: the card asks for `yes` and the PIN; say "yes" aloud first and see that
   nothing happens until you type it.
6. Say "Kairu, stop". Everything stops and the mic goes off; run `py -3.12 -m kairu resume` in PowerShell.
7. Ctrl+Alt+V, then Ctrl+Alt+V again: Kairu Live starts and ends.

### Honest limits

- Built and tested on Linux with a stand-in talking program and LiveKit 1.8.12's own session code (no sound card, no
  network); not yet run on Windows with your mic. The talking program uses LiveKit's own console mic and speaker classes
  (livekit.agents.cli._legacy), so it needs LiveKit 1.8.x, as installed in your Kairu Live folder.
- No email, camera or phone in the bar's Kairu Live: those tools of the standalone Kairu Live aren't Guardian actions yet.
  The standalone folder still works on its own (`agent.py dev` for the phone), but not at the same time as the bar's.
- Gemini's free tier counts each of your sentences as a request (about 500 a day on gemini-3.5-flash-lite).
