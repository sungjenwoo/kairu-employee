# Kairu App Master Plan v2.0 (PC, Voice, Phone)

Nov 3, 2026 · @saitej

> **Approved by the owner with GO on 3 Nov 2026 (ADR-028).** This is the whole Kairu app plan. It is a copy of
> the live plan in Claude Docs (https://claude.ai/artifact/SvMy2hTuSKLnv5gEWuCHbo), taken on 3 Nov 2026; the two
> diagrams there are written out as text here. The build order and gate tests are also in *Kairu - Staged
> Implementation Plan v1.7*, which governs. Phase B is finished and merged (PR #8, 3 Nov). Next: R1. Each stage
> still waits for its own GO.

One plan for the whole Kairu app: the Kairu bar on the PC (Part 1), voice in the same bar (Part 2), and the phone
app (Part 3). The earlier phone-app plan (Kairu App Master Plan v1.0) is folded into Part 3.

## 1. What the owner asked for

Two things, in this order of importance:

1. **Kairu hears the owner and does whatever task they say.** Voice is finished after the RAM upgrade, then
   attached to Kairu.
2. **Kairu has overall control of the PC.** Once that works, Kairu comes to the phone.

**Build order:**

| Part | What | When | Why this order |
| --- | --- | --- | --- |
| **Part 1. PC Control** (Phase P) | Kairu can do tasks on the PC: apps, files, settings, browser, any window, multi-step jobs. Starts with live web research. Orders are typed in the Kairu bar | **Next** (Phase B done 3 Nov) | Light on RAM, so it runs before the upgrade. It reuses the brain. Voice needs something to control, so this comes first |
| **Part 2. Voice** (Phase E) | Wake word "Kairu", your-voice check, speech-to-text, Tenmin-style spoken replies, all feeding the same task system as Part 1 | **After the RAM upgrade** (16 GB or more) | The voice prototype already ran but was too slow on 7.7 GB |
| **Part 3. Phone** (Phase D + J3) | The Kairu phone app (Kotlin) controls the same PC Kairu from anywhere, by voice or text | **After Parts 1 and 2 pass** | The owner's rule: PC control first, then phone |

The key design idea: **one task system, many ways in.** Typing now, voice after RAM, phone later. Each new way in
plugs into the same brain, the same Guardian rules and the same PC skills, so nothing is built twice.

## 1a. The target: "talk and it does it" (from the owner's video, 3 Nov)

The owner's 50-second screen recording is the standard Kairu must match. The speaker never types or clicks: they
talk in one long, natural stream, and the assistant does each task **while they are still talking**. The video's
sound track is silent, so everything below comes from the picture.

**What happens, second by second**

| Time | What the person says (shown live on screen) | What the assistant does |
| --- | --- | --- |
| 0–2 s | (starts the assistant) | A small dark bar appears at the top centre: "Go ahead, I'm listening." |
| 3–8 s | "Alright. Can you open up the Notes app for me? And, um, once you're there, can you create a new note?" | Notes opens about 1 s after "Notes app for me", before the sentence ends. Then a new note is made |
| 9–12 s | "And inside this new note, let's make the title say 'Hello.'" | Types "hello" as the title |
| 13–16 s | "Great, great. Okay, let's move on and can you open up the Arc browser?" | Ignores "Great, great. Okay"; opens the browser |
| 17–20 s | "Can you Google search 'Norbert Wiener'?" | Types the search; results appear about 2 s later |
| 21–24 s | "Now, can you open up X dot com?" | Opens x.com in a new tab |
| 25–30 s | "Nice, nice. Okay. Um, now can you open up the Photo Booth?" | Ignores the filler; opens the camera app |
| 31–37 s | "And let's take a picture of me." | Presses the shutter; 3-2-1 countdown; photo taken |
| 38–42 s | "Cool, awesome. Thank you." | Understands the session is over; the bar goes back to waiting |
| 43–50 s | (later) "Alright, can you open up the Notes app…" | Bar again shows "Go ahead, I'm listening" and the loop repeats |

**The 8 behaviours Kairu must copy**

1. **One small floating bar, not a big window.** It sits at the top centre, over every app, and shows a sound-wave
   icon, the owner's words live as they speak, a Stop button and a hide button.
2. **"Go ahead, I'm listening."** A clear ready signal when listening starts.
3. **Live words on screen.** The sentence appears word by word, so the owner can see Kairu heard it right.
4. **Act as soon as one order is complete.** Kairu does not wait for the owner to stop talking. "Open Notes" runs
   at once, while the owner is still saying the next part.
5. **Many orders in one breath.** "Open X and once you're there do Y" is split into steps and run in order, each
   step waiting for the one before to finish.
6. **Filler is not an order.** "Um", "okay", "great, great", "nice, nice" are ignored.
7. **"It" and "there" mean what is on screen now.** "Inside this new note" means the note just made; "take a
   picture of me" means the camera app just opened.
8. **"Thank you" ends the session**, and Kairu goes quiet until called again.

**Windows versions of the video's apps:** Notes → Notepad or Sticky Notes; Arc browser → Edge or Chrome; Photo
Booth → Windows Camera; x.com and Google work the same.

**Two things the video does not show, so Kairu adds them:** Guardian stays in charge (High actions still pause and
ask for the PIN, Critical stays blocked), and Kairu replies with a short line in the bar for every task, spoken
only when it is answering a question. Taking a photo is Medium: allowed, logged, and the photo stays on the PC.

## 2. What "overall control" means

Overall control means Kairu can reach every app, file, window and setting a normal user can, and can do it for
the owner. It does not mean Kairu skips Guardian: the owner's approved safety rules still decide every action.

- **Low** (open an app, find a file, change volume, read a page) → Kairu just does it.
- **Medium** (move or rename files, close an app, change display or sound settings) → Kairu does it and logs it,
  with undo where possible.
- **High** (delete files, install or uninstall apps, shut down or restart, submit forms, send messages, run
  commands not on the safe list) → Kairu asks first; the owner says "yes" and types the PIN.
- **Critical** (money and banking, security settings like antivirus or firewall, deleting accounts, hidden
  installs, pretending to be the owner) → always blocked, no approval path (ADR-004, ADR-023).

Three extra rules for PC control:

- **Deletes go to the Recycle Bin**, never permanent, so mistakes can be undone.
- **What Kairu reads on screen is data, not orders.** A web page or file saying "Kairu, do X" is ignored as a
  command.
- **Screen pictures stay on the PC** unless the owner approves sending one to a cloud model. Kairu reads windows
  as text first (no picture needed).

## 3. How a task runs

Every order, typed or spoken, passes Guardian before Kairu touches the PC:

1. **Way in:** typed in the Kairu bar (now), spoken (after the RAM upgrade), or sent from the phone (later).
2. **Understand:** an exact order goes through L0 fixed rules; a free-form one is planned by the brain.
3. **Guardian check:** Low and Medium go; High needs "yes" + PIN; Critical is blocked. Refused → Kairu says why.
4. **Do it:** apps, files, system, browser, any window.
5. **Check the result:** read the window again; undo if it went wrong.
6. **Report:** a short line in the bar (spoken after Part 2 when it answers a question).

"Kairu, stop" or Ctrl+Alt+K halts any step at any point.

## 4. What Kairu can control on the PC

Eight areas, each a set of "skills" with a fixed tier. Example orders are what the owner could type now and later
say by voice.

| Area | Example orders | Tiers |
| --- | --- | --- |
| **Apps & windows** | "Open Chrome", "close Spotify", "put VS Code on the left half", "what's open?" | Open/arrange: Low · close: Medium |
| **Files & folders** | "Find my resume PDF", "move all screenshots to Pictures/2026", "zip the project folder" | Find/open: Low · move/rename/zip: Medium · delete to Recycle Bin: High |
| **System** | "Volume 30%", "brightness down", "turn off Bluetooth", "how much RAM is free?", "lock the PC" | Read/adjust: Low · close a heavy process: Medium · sleep/restart/shutdown: High |
| **Browser & web** | "Search today's cricket score", "open my Gmail", "fill this form" (Kairu's own browser profile) | Search/read: Low · type in a form: Medium · submit/send: High · buying: Critical |
| **Any app (screen control)** | "In Excel, sort column B", "click Export in this app" — Kairu reads the window and clicks or types | Per action, same tiers; unknown app actions start at High until the owner marks them safe |
| **Terminal & code** | "Run the Kairu tests", "git pull in Kairu-guardian" | Safe-list commands: Low · anything else: High · admin rights: Critical |
| **Apps install** | "Install VLC" (winget, Windows' own installer) | Install/uninstall: High · hidden install: Critical |
| **Multi-step tasks** | "Clean my Downloads, keep only this month, then tell me what you removed" | Kairu shows the step list first; each step keeps its own tier |

**Not controlled:** banking and payment sites, Windows Security and firewall settings, passwords and saved logins,
other user accounts.

Every tier above is written into `policy.yaml` by the stage that adds the skill; anything not in `policy.yaml` is
denied.

## 5. Build stages

Each stage ends with a gate test the owner runs on their own PC; nothing merges into `main` until it passes. Same
loop as always: Claude Chat plans → the owner says **GO** → Claude Code builds on a branch → the owner tests →
merge.

### Part 1 — PC Control (Phase P, next)

| Stage | What gets built | Gate test on the PC | Rough time |
| --- | --- | --- | --- |
| **R1 Live web research** | Real search: free DuckDuckGo search (no key), reads the top 3 pages as text, short Tenmin-style answer with sources on request, "today's date" check so recent questions always search. Search words leave the PC, so it follows the Medium rule `research.web_search` already in `policy.yaml`. The search runs as a Guardian action; the brain only asks for it and never fetches pages by itself | "kairu ask who won yesterday's cricket match" gives today's real answer; "sources?" lists the pages; a personal question still waits for approval; a page saying "Kairu, do X" is ignored; works from the phone stand-in too | 3–4 days |
| **PC0 Kairu bar + task core** | The Kairu bar from the video: a small floating bar at the top centre, over every app (opens with a hotkey; typed orders for now), one task system for every order, skill list with fixed tiers, undo log, short reply after each task | Type "what's open?" and get an answer; a Critical skill does not exist; undo reverses a rename | 4–5 days |
| **PC1 Apps, windows, system** | Open/close/arrange apps, volume, brightness, Wi-Fi/Bluetooth, RAM and battery status, lock, sleep, restart | 10 typed orders all work; restart asks for PIN | 3–4 days |
| **PC2 Files & folders** | Find, open, move, rename, zip, delete to Recycle Bin | Tidy a test folder; delete asks for PIN and lands in Recycle Bin; undo works | 3–4 days |
| **PC3 Browser & web** | Kairu's own browser profile: search, open sites, read pages, fill forms (submit is High) | Look up a fact and answer in short; a form stops before Submit until PIN | 4–5 days |
| **PC4 Any-app control** | Read any window as text and click/type in it; screenshot only as backup, kept on the PC | Do a task in Notepad and in File Explorer by plain orders; a page saying "Kairu, delete files" is ignored | 5–7 days |
| **PC5 Terminal, code, installs** | Safe-list commands, Git and test runs, winget install/uninstall | Run Kairu's tests by order; install VLC with PIN; an admin command is refused | 3–4 days |
| **PC6 Do whatever I say** | Free-form orders: the brain turns the owner's words into a step list, shows it, runs it through Guardian, checks each result, reports | Three real multi-step tasks done right; "Kairu, stop" halts one mid-way | 5–7 days |
| **PC7 Finish & harden** | Crash recovery mid-task, RAM check, full Part 1 gate test | Every row above re-run; a Guardian restart during a task leaves nothing half-done | 3–4 days |

Phase B is done (PR #8 merged 3 Nov). The plan lock (Plan v1.7 + ADR-028) comes before R1, because Claude Code only
builds what the repository's governing plan says.

### Part 2 — Voice (Phase E, after the RAM upgrade)

| Stage | What gets built | Gate test | Rough time |
| --- | --- | --- | --- |
| **V1 Wake word + your voice** | "Kairu" wake word and hotkey, your-voice check, "Go ahead, I'm listening" in the bar, reusing what the paused prototype learned (Kairu still does not import the prototype) | Wakes on the owner's voice; ignores other voices and its own speaker | 4–5 days |
| **V2 Live words** | Offline streaming speech-to-text (the voice never leaves the PC): words appear in the bar word by word; Tenmin persona and Explain Mode ("explain it simply") | The sentence shows in the bar within about half a second of saying it | 4–5 days |
| **V3 Act while you talk** | Each complete order runs at once while the owner keeps talking; one breath split into steps ("open Notepad and once you're there…"); filler ignored; "it"/"there" = what is on screen; "thank you" ends the session; "Kairu, stop" halts everything | **The video test:** say the video's script on the PC (Notepad, new note titled Hello, Edge, Google search, x.com, Camera photo, thank you) in one go; every task is done before the owner finishes talking or within 2 s after | 6–8 days |
| **V4 Always on** | 24/7 listening at the PC, mic on/off from the tray, quiet hours; High actions pause the flow and ask for PIN; only one Kairu listener runs at a time | A full day with no false wake-ups the owner notices; RAM stays healthy | 3–4 days |

Part 2 is Phase E of the repository plan. Face check on the PC (confirmation only) and the presence rules (speak at
the PC, Kairu Call when away) stay in Phase F, after Part 3.

### Part 3 — Phone (Phase D + J3, after Parts 1 and 2)

The phone app is **Kotlin native** (decided 3 Nov), built on GitHub's free build machines and installed with ADB,
so the 7.7 GB PC never runs Android Studio. Its main job: **say an order on the phone, and Main Kairu does it on
the PC**, through the same task system, Guardian rules and Kairu bar flow. It also has its own small brain for when
the PC is off.

| Stage | What gets built | Gate test on the Mivi phone | Rough time |
| --- | --- | --- | --- |
| **D0 Setup** | `phone/` folder in Kairuu, GitHub build, wireless ADB install, one-time phone setup (Allow restricted settings, microphone, no battery restriction), `kairu phone install` | App builds on GitHub, installs, opens | 2–3 days |
| **D1 Link & pairing** | Keystore keys, Kairu Link, QR pairing with `kairu device pair`, background Gate listener, text chat | Pair by QR; ask a question, PC answers; old or copied messages refused; Termux removed | 4–5 days |
| **D2 Approvals & STOP** | Signed policy pack from Guardian, fingerprint approval for High (spoken PIN backup), STOP both ways | A PC High action approved by fingerprint; a fake approval refused; Critical has no button; phone STOP halts a PC task | 4–5 days |
| **D3 Remote PC control** | Phone orders run through the PC task system: "open Edge on my PC", "tidy my Downloads"; live step list and results on the phone | Three Part 1 tasks done from the phone; High ones ask for the fingerprint | 4–5 days |
| **D4 Missions & research** | Missions screen, doubts, reports; R1 research from the phone; queue when the PC is off; memory shared with Main Kairu (encrypted) | Research answer with sources on the phone; a mission waits while the PC is off and runs when it is on | 3–4 days |
| **D5 Phone brain** | L0 rules, free cloud models with the privacy filter, small offline model (Gemma 3 1B, about 0.6 GB, Wi-Fi download) | PC off and airplane mode: simple questions still answered | 4–5 days |
| **D6 Phone voice** | Same behaviour as the video: floating bar, live words, act while you talk, "thank you" ends; listens for "Kairu" while charging or screen on, a button otherwise | Say the video script on the phone, aimed at the PC; every task done | 5–7 days |
| **D7 Phone skills** | SMS read/draft/send, WhatsApp text-ready (the owner presses Send), open phone apps, phone calls by voice, reminders | Each skill works; SMS to a new number needs the fingerprint | 4–5 days |
| **D8 J3 phone protection** | Notification reader, scam SMS rules, J1/J2 alerts on the phone | A test scam SMS is caught on phone and PC; Phase J reaches 100% | 3–4 days |
| **D9 Face check & finish** | Face check (confirmation only), Guest Mode, lost-phone lock, 24-hour battery test | Full Part 3 gate test re-run; Guest Mode and lost-phone lock work | 4–5 days |

After Part 3: Kairu Call and presence rules (Phase F), then the trip mission (I), builder powers (G), Shadow
Missions (H) and hardening (K), as in Master Plan v2.0.

## 6. Roadmap

1. **Phase B** — done (merged 3 Nov).
2. **Plan lock** — Plan v1.7 + ADR-028.
3. **Part 1 (Phase P): R1, PC0–PC7** — about 6 weeks. Gate: the Part 1 gate test, plus the RAM upgrade before
   Part 2.
4. **Part 2 (Phase E): V1–V4** — about 2.5 weeks. Gate: the video test.
5. **Part 3 (Phase D + J3): D0–D9** — about 6–8 weeks.
6. Then F, I, G, H, K.

Times are at 2–3 hours a day. If the RAM arrives early, voice can start right after Part 1 passes; if it arrives
late, PC skills keep improving while waiting.

## 7. Tech choices and RAM use

All free, all running on the PC, all in Python 3.12 inside the Kairuu repo next to Guardian. RAM figures are
approximate and get measured in each gate test. Every new dependency is justified in `pyproject.toml` when its
stage adds it (CLAUDE.md).

| Part | Recommended | Why | Approx. RAM |
| --- | --- | --- | --- |
| Kairu bar | **Tkinter** (built into Python) | Lightest possible window; voice and phone plug into the same task system later | ~30 MB |
| Task core + skills | **Python, run inside Guardian's sealed process boxes** | Every action passes Guardian, same tiers, same audit log | ~50–80 MB |
| Understanding orders | **L0 fixed rules first** for exact orders ("open Chrome"); **Phase B brain** (free cloud, privacy filter) for free-form ones | Simple orders work instantly and offline; only free-form orders need a model | small |
| Apps, windows, any-app control | **pywinauto** (Windows UI Automation) | Reads windows as text and clicks real buttons, no picture needed | ~40 MB |
| System controls | **pycaw** (volume), **screen-brightness-control**, Windows' own commands | Free, well-known, no admin rights | small |
| Files | Python standard library + **Send2Trash** | Deletes always go to the Recycle Bin | small |
| Browser | **Playwright driving Microsoft Edge** in a separate Kairu profile | Edge is already installed (no extra browser download); the owner's own logins stay untouched | +300–500 MB, only while a browser task runs |
| Installs | **winget** (Windows' own app installer) | Official, already on Windows 11 | small |
| Screenshots (backup only) | **mss**, saved on the PC, never sent to cloud without approval | Privacy | small |
| Voice (Part 2) | Re-test the prototype's wake word, voice check, speech-to-text and voice after the RAM upgrade, rebuilt inside Kairu | Already proven to work, only too slow on 7.7 GB | 1–3 GB, decided after the upgrade |
| Web research (R1) | **ddgs** (DuckDuckGo search, free, no key) + Python's own HTML reader for page text | Worked in the voice prototype; one small new dependency, needed because Python has no search engine built in | ~20 MB |
| Phone app (Part 3) | **Kotlin + Jetpack Compose**, libsodium, Android Keystore, BiometricPrompt, LiteRT-LM, sherpa-onnx | Built on GitHub, installed by ADB; nothing heavy on the PC | PC: ADB only, ~15 MB |

**Part 1 total:** about 150–200 MB while waiting, up to about 700 MB during a browser task. That fits the current
7.7 GB if heavy apps are closed.

## 8. Decisions (settled by the owner's GO, 3 Nov 2026)

Every blank "Owner's choice" uses the recommendation. The owner can still change any of them before its stage
starts.

| # | Decision | Recommendation | Owner's choice |
| --- | --- | --- | --- |
| K-1 | Kairu bar style | **Tkinter floating bar like the video**: plain but very light (~30 MB). A nicer web-style bar costs about 150 MB more | |
| K-2 | Hotkey to open the Kairu bar | **Ctrl+Alt+Space** (Ctrl+Alt+K stays STOP) | |
| K-3 | Which browser profile Kairu uses | **A separate Kairu profile** with no saved logins. The owner's own profile would give Kairu their logged-in sites: more power, more risk | **Decided 3 Nov: Kairu's own profile** |
| K-4 | Commands Kairu may run without asking | **Only:** `git status`, `git pull`, Kairu's own tests and `kairu` commands. Everything else asks for PIN | |
| K-5 | Finishing the brain (Phase B) | **Done: Phase B merged 3 Nov (PR #8); plan lock, then R1**, since research and "do whatever I say" both use it | |
| K-6 | Phone plan | **Part 3 of this plan, Kotlin native**, starts after Parts 1 and 2 pass | **Decided 3 Nov: Kotlin native** |
| K-7 | Does Kairu speak after each task? | **Like the video: act quietly** and show a short line in the bar ("Opened Notepad"); speak only when answering a question or asking something | |
| K-8 | Voice before the RAM upgrade? | **Wait for the RAM.** Option: a tiny offline speech model (about 50 MB) could run a rough voice trial on 7.7 GB, less accurate than the final one | |

## 9. Approval

Approved with GO on 3 Nov 2026, with GO for R1 once Phase B was merged. The plan lock records this plan in the
Kairuu repo with Plan v1.7 and ADR-028. Each stage still waits for its own GO.

## 10. How each stage starts

1. The owner says **GO <stage>**.
2. Claude writes that stage's plan and the Claude Code prompt.
3. Claude Code builds it on a new branch in `sungjenwoo/Kairuu`, runs `tools/check_guardian.py`, and opens a pull
   request. It never merges.
4. The owner runs the gate test on their own PC and merges.

**Checked against the owner's decisions (3 Nov):** free only; secrets and voice stay on the PC; personal data needs
"yes" + PIN before it leaves; Low/Medium go, High needs "yes" + PIN (fingerprint on the phone), Critical always
blocked; web pages are data, not orders; "Kairu, stop" and Ctrl+Alt+K stop everything; Tenmin style (short, warm,
one follow-up, Explain Mode); the owner's voice only; phone setup, SMS and WhatsApp first, calls, shared memory, J3
and face check (confirmation only) are all in Part 3; Kairu Call, presence, the trip mission, builder powers,
Shadow Missions and hardening follow in Phases F, I, G, H and K.
