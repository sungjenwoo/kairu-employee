# Kairu — Staged Implementation Plan v2.0

Nov 11, 2026 · @saitej

> **This is Kairu's governing build plan.** v2.0 adds **W2, finishing the workspace (ADR-036)**, section 4b-2: the files a
> mission made or changed in the right panel (with three file skills: make a text file, open a file, show it in its
> folder), voice inside the workspace, "Kairu, open the workspace" from the bar, and the owner's Ember Glow look. Everything
> else is as in v1.9, which stays in the repository, marked superseded.
>
> v1.9 added the owner's **Kairu App workspace (W1, ADR-030)**, section 4b:
> one home window for everything Kairu does, inspired by Claude's own app, with all projects on the left. It also records
> what a **Clone** and a **Shadow** are (they are different), and the owner's list of new features for later phases.
> Everything else is as in v1.8, which stays in the repository, marked superseded.

## 1. Order of authority

When two documents disagree, the higher one wins:

1. **Accepted ADRs** in *Kairu - Architecture Decision Records* (ADR-013 onwards are the newest).
2. **This plan, v2.0** — order of work, status, gate tests.
3. **Kairu App Master Plan v2.0 (PC, Voice, Phone)** — the stages of Phases P, E and D, the Kairu bar, the
   owner's video standard and decisions K-1 to K-8 — and **Kairu Master Plan v2.0** — what Kairu is and how
   each part works.
4. **System Architecture v1.1** and **Staged Implementation Plan v1.3.7** — detailed design and tests,
   where they do not conflict with 1–3.
5. **Master Vision & Behavioral Blueprint v0.1** — the original requirements.

**Plan lock rule.** From 28 Oct 2026 this plan changes only when the owner approves the change.
Every approved change gets a new version of this file (v2.0 …) and, for a design decision, a new ADR.
Claude Code builds only phases and parts that this plan lists, and never merges to `main`.

## 2. What is really built (11 Nov 2026)

| Part | Status | Evidence |
| --- | --- | --- |
| Guardian core: risk tiers, deny by default, approvals with "yes" + PIN, Critical always blocked, emergency stop, Safe Mode, hash-chained audit log with anchor | **Verified** (tested on the owner's PC, merged) | PR #1; `GUARDIAN.md`; `tools/check_guardian.py` |
| Guardian as its own program: starts at sign-in, holds Ctrl+Alt+K, tray icon with Stop, sign-out/restart handling | **Verified** (hand-tested, merged 27 Oct) | PR #2; `GUARDIAN.md` |
| Phase A — plan lock: Master Plan v2.0, the plan, the decision register | **Done** (merged 28 Oct) | PR #6 |
| Phase J1 — Guardian monitors: Gmail (read-only) and deadlines | **Verified** (gate test on the owner's PC, merged 28 Oct) | PR #3; `PROTECTION.md` |
| Phase J2 — Guardian monitors: Downloads folder, devices, Windows Security | **Verified** (merged 28 Oct) | PR #4, PR #5; `PROTECTION.md` |
| Phase C — Kairu Gate & Link: Link messages, QR pairing, the Gate client (ntfy.sh), Mission Mode, the queue | **Verified** (gate test passed on the owner's PC, merged 29 Oct) | PR #7; `LINK.md`; ADR-025 |
| Phase B — Brain & AI routing: Model Gateway (L0–L4), free providers with switching, privacy filter, usage display, asking from the PC and the phone, Mission Cards with checkpoints | **Verified** (gate test passed on the owner's PC, merged 3 Nov) | PR #8; `BRAIN.md`; ADR-026, ADR-027 |
| Kairu App Master Plan v2.0 and this plan | **Approved** 3 Nov (owner's GO); merged with this plan lock | ADR-028 |
| Stage R1 — live web research (Guardian actions, page text as quoted data) | **Verified** (merged 4 Nov) | PR #13; `RESEARCH.md` |
| Sprint Day 1 — the Kairu bar, task core, PC skills (PC0 + PC1) | **Verified** (gate test passed, merged 6 Nov) | PR #14, PR #15; `BAR.md` |
| Sprint Day 2 — light voice (offline Whisper base.en, "Kairu" and Ctrl+Alt+V, Tenmin answers, Piper) | **Verified** (merged 10 Nov) | PR #16; `VOICE.md` |
| Sprint Day 4 — files, Kairu's own browser, free-form plans | **Verified** (merged 10 Nov) | PR #17, PR #18; `BAR.md` |
| W1 — the Kairu App workspace (projects on the left, missions, live steps, Guardian's card) | **Merged** 11 Nov | PR #19; `WORKSPACE.md`; ADR-030 |
| W2 — finishing the workspace (files panel and file skills, voice in the workspace, open the workspace, Ember Glow) | **Built**, on top of W1; waits for the owner's gate test | PR #21; `WORKSPACE.md`; ADR-036 |
| Phase D, D0–D3 — the phone app: built on GitHub, installed with ADB, QR pairing and chat, fingerprint approvals and STOP, orders to the PC's task core | **Merged** 11 Nov (D0–D2 gate-tested on the Mivi phone) | PR #20; `PHONE.md`; ADR-034, ADR-035 |
| Phase D4 — missions from the phone: an order that waits in the Gate while the PC is off and runs when Guardian is back | **Built**; waits for the owner's gate test | `PHONE.md`; ADR-037 |
| Sprint Day 3 — first phone app | **Replaced** by Phase D above | — |
| Research & speak prototype (voice in/out, web research) | **Prototype, paused** — worked, but slow on the current RAM; not part of `main`; Kairu does not import it | `research_voice/` notes |
| Everything else in section 4 | **Planned** | — |

CI runs the Guardian checks on every pull request (`.github/workflows/guardian.yml`).

## 3. What changed

| Version | Change | Why |
| --- | --- | --- |
| **v2.0** | **W2, finishing the workspace** (section 4b-2): files panel with three file skills (`files.write` gets its code; `files.open` and `files.show` are new), voice in the workspace, "Kairu, open the workspace", the Ember Glow look; the voice link is claimed only while a mic is on, so the bar and the workspace share one mic | ADR-036 (owner, 11 Nov 2026: "let's finish the workspace … choose the best and start building") |
| **v1.9** | **The phone app (Phase D) is built next, tonight, D0–D4** (section 4e) | ADR-034 (owner, 11 Nov 2026) |
| **v1.9** | **The Kairu App workspace (W1)** (section 4b): a home window inspired by Claude's app, projects and missions on the left, live steps and approvals on the right, built next | ADR-030 (owner, 11 Nov 2026, "start building the whole Kairu app") |
| **v1.9** | **Clone and Shadow are two things**: a Clone is a permanent teammate on another PC that splits a project with Main Kairu; a Shadow is a temporary helper on a friend's PC that comes back (section 4c) | ADR-030 |
| **v1.9** | **The owner's new feature list** (section 4d), for later phases | ADR-030 |
| **v1.9** | **Glass box receipt, teach-back and call the master** join Phase H; Shadow squad comes later (section 4c) | ADR-033 (owner, 11 Nov 2026) |
| **v1.9** | **A Shadow comes home smarter**: it brings back what it learned, explains it to Main Kairu, and the owner approves each lesson (section 4c) | ADR-032 (owner, 11 Nov 2026) |
| **v1.9** | **A Clone shares your workspace; a Shadow has its own empty one; a Shadow keeps working with your PC off (A)** (section 4c) | ADR-031 (owner, 11 Nov 2026) |
| **v1.8** | **4-day sprint** (section 4a): Day 1 PC0 + PC1, Day 2 light voice on the current RAM, Day 3 first phone app, Day 4 files, web and the end-to-end test | ADR-029 (owner, 3 Nov 2026) |
| **v1.7** | **Phase P — PC Control** is added and built next: R1 live web research, then PC0–PC7 (the Kairu bar, apps, files, system, browser, any-app control, terminal and installs, "do whatever I say", hardening) | ADR-028 (owner, 3 Nov 2026): the owner wants Kairu to do whatever they say on the PC first, then by voice, then from the phone |
| **v1.7** | **New order:** P → E (after the RAM upgrade) → D + J3 → F → I → G → H → K | ADR-028 |
| **v1.7** | **Phase E** is defined as V1–V4 of the App Master Plan, ending with the owner's video test ("act while I talk") | ADR-028; the owner's screen recording of 3 Nov |
| **v1.7** | **Phase D** is defined as D0–D9 of the App Master Plan: Kotlin native, built on GitHub, installed with ADB; its first job is controlling the PC from the phone | ADR-028 |
| **v1.7** | Phase B is verified and merged (gate test passed 3 Nov) | PR #8, PR #9 |
| **v1.6** | **B is built before D**: the order is B → D → F → I → E, G, H → K | ADR-026 (owner, 29 Oct 2026): lighter on RAM and time during exams; the phone can ask questions at once; the phone app reuses B's filter and providers |
| **v1.6** | **Option A**: a question with no personal data goes to a no-training free provider without per-send approval; anything personal still waits for "yes" + PIN; secrets never leave. Switchable in `config.yaml` (`brain.public_to_cloud`) | ADR-026 (owner, 29 Oct 2026) |
| **v1.6** | Phase C is verified and merged (gate test passed 29 Oct) | PR #7, LINK.md "Gate test result" |
| **v1.6** | Free cloud providers checked on 29 Oct: Groq first; Cerebras no longer has a free tier (it needs a payment method), so Cloudflare Workers AI is second (accepted 2 Nov); OpenRouter stays the spare | BRAIN.md; ADR-027 (owner, 2 Nov 2026) |
| v1.5 | Phase C's four built choices are accepted; wake-up waits for the home Gate; Gate start option ntfy.sh | ADR-025 |
| v1.4 | Phases A–K in six stages; the Kairu family; L0–L4 and the five planes; J started early; hackathon set aside | ADR-013 to ADR-024 |

## 4. Build order — Phases A to K and P

Each stage ends with a gate test that must pass before the next stage starts. Sizes at about
2–3 hours a day: S ≈ 1 week, M ≈ 2–3 weeks, L ≈ 4–6 weeks.

| Stage | Phase | What gets built | Done when (gate test) | Size | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | **A** — Guardian program + plan lock | Guardian at sign-in, tray Stop, logs; Master Plan v2.0 approved; plan merged into the repo | Restart: Guardian starts by itself, Stop works, every action is logged; the plan merged into `main` | S | **Done** (PR #6) |
| 2 | **B** — Brain & AI routing | Model Gateway (L0–L4), free providers with automatic switching, privacy filter, usage display, asking from the PC and the phone (Link type "ask"), Mission Card store with checkpoints | 20 test requests go to the right level; private test data never reaches the cloud without approval; a secret is never sent; a simulated free limit switches provider and `kairu usage` shows it; the phone gets an answer; a mission resumes after a forced restart without repeating a step; Ctrl+Alt+K under 1 s; the audit log keeps hashes only (BRAIN.md) | M | **Done** (PR #8, gate test passed 3 Nov) |
| 2 | **C** — Kairu Gate & Link | Gate (start option: free encrypted relay, ntfy.sh), Kairu Link messages, QR pairing, Mission Mode switch, the Gate's queue | With the lid closed in Mission Mode, the PC receives a phone message and replies within seconds; a replayed old message is rejected | M | **Done** (PR #7, gate test passed 29 Oct) |
| 3 | **P** — PC Control (App Master Plan Part 1) | R1 live web research (Guardian actions `research.web_search` and `research.web_read`; the brain only asks), then PC0 the Kairu bar and task core, PC1 apps/windows/system, PC2 files, PC3 browser (Kairu's own profile), PC4 any-app control, PC5 terminal/code/installs, PC6 "do whatever I say", PC7 hardening | Each stage's gate test in the App Master Plan; at the end every row is re-run, a Guardian restart mid-task leaves nothing half-done, Ctrl+Alt+K under 1 s, Critical skills do not exist | L | **Next** (R1 first) |
| 4 | **E** — Voice (App Master Plan Part 2) | V1 wake word + your-voice check, V2 offline live words + Tenmin persona + Explain Mode, V3 act while you talk (orders split, filler ignored, "thank you" ends, "Kairu, stop"), V4 always on | The video test: the owner says the video's script on the PC in one go and every task is done before they finish or within 2 s; from across the room, "Kairu, who is the prime minister of India?" gets a short, correct spoken answer and one follow-up offer | M | Planned — after the RAM upgrade (prototype paused) |
| 5 | **D** — Phone app (+ J3) (App Master Plan Part 3) | D0–D9: Kotlin app built on GitHub and installed with ADB; pairing, fingerprint approvals and STOP, controlling the PC from the phone, missions and research, its own L0/L1/L3 brain, phone voice, SMS, WhatsApp (text ready), calls, J3, face check | Three PC tasks done from the phone; with the PC off: a WhatsApp message, "open YouTube", a call and a research question all work; a Critical request is refused | L | Planned — after P and E |
| 5 | **J** — Guardian wider protection | J1 Gmail + deadlines, J2 folders/devices/Windows Security, J3 phone | A test phishing email, a deadline tomorrow and an unknown device each create a clear alert; nothing changes without approval | M | **J1, J2 done; J3 with D** |
| 6 | **F** — Presence, Kairu Call, face check | Presence engine, speak-or-call rules, Kairu Call, face check on phone and PC, fingerprint/PIN for High | At the PC Kairu speaks and never calls; away, the phone rings within a minute; someone else unlocking the phone gets Guest Mode | M | Planned |
| 7 | **I** — Trip & long missions | Call-me request, mission by voice, OTP hand-off, page watching, grouped doubts, callbacks, confirmed submission | The "trip test" on a mock hackathon page | M | Planned |
| 8 | **G** — Builder powers | The Agency agent squad, coding engine behind the gateway, test ladder, Presenter and World Brief, deep research | From a one-paragraph idea Kairu builds a small website with login, passes its tests, deploys it free, makes 5 slides and explains them | L | Planned |
| 9 | **H** — Shadow Missions | Repo Mode first, then Shadow app and Guide Mode, Shadow Manager, folder fence, self-removal | Repo Mode PR accepted on a test project; Shadow app finishes a test project, refuses a file outside the folder, Stop works instantly, nothing left behind | L | Planned |
| 10 | **K** — Hardening | Security tests of every part, speed, Guardian Part 4 (audit improvements), local models (L2) and better voice after the RAM upgrade, backups | Every earlier gate test passes again; answers are faster than before the upgrade | M | Planned (local AI needs RAM) |

**Wake a sleeping PC: with the home Gate (old phone at home).** Moved out of Phase C by ADR-025 (owner,
29 Oct 2026); it gets its phase when the home Gate is planned. Until then Mission Mode keeps the PC
awake while it charges, and messages wait in the Gate's queue.

## 4a. The 4-day sprint (ADR-029, 4–7 Nov 2026)

Goal: on the PC and the phone, Kairu hears the owner and does what they say ("open Chrome", "call Shruthi"),
with every action decided by Guardian. One Claude Code build per day; each day ends with the owner's gate test.

| Day | Build (branch) | Done when |
| --- | --- | --- |
| 1 — 4 Nov | **PC0 + PC1** (`pc0-pc1`): the Kairu bar and task core; apps open/close/arrange, volume, brightness, Wi-Fi, status, lock, sleep/restart/shutdown | Typed orders "open Chrome", "volume 30", "close Notepad", "what's open?" work; restart asks for "yes" + PIN |
| 2 — 5 Nov | **Light voice** (`voice-lite`): small offline speech model (about 50 MB, the voice never leaves the PC), "Kairu" wake word plus a hotkey, live words in the bar, act while the owner talks, Windows' built-in voice for answers | "Kairu, open Chrome and search the weather" works hands-free; "thank you" ends; "Kairu, stop" stops |
| 3 — 6 Nov | **First phone app** (`phone-lite`, Kotlin, built on GitHub, installed with ADB): pairing over Kairu Link, text and voice, call a saved contact, open phone apps, PC orders sent to the PC task system | "Call Shruthi" rings her; "open Chrome on my PC" works from the phone; High steps wait for "yes" + PIN at the PC |
| 4 — 7 Nov | **Files + web + finish** (`sprint-finish`): find/move/rename/delete to the Recycle Bin, open websites, Google search in the browser, simple free-form orders mapped to known skills; end-to-end test and fixes | The sprint test: the owner's video script on the PC by voice, and three orders from the phone |

**Left for after the sprint (back in v1.7's order):** any-app control (PC4), terminal and installs (PC5), long
free-form planning (PC6), PC7, your-voice-only check, the full voice after the RAM upgrade, fingerprint approvals,
the phone's own brain, phone voice wake word, SMS and WhatsApp, J3, face check, Kairu Call, I, G, H, K.

Unchanged in the sprint: Guardian decides every action; High needs "yes" + PIN at the PC; Critical is always
blocked; secrets and voice stay on the PC; free only; Ctrl+Alt+K and "Kairu, stop" end everything in under 1 s.

### Order from now (ADR-028; the sprint of section 4a came first; W1 and W2 are next, ADR-030 and ADR-036)

**Next: W1 and W2 — the Kairu App workspace** (sections 4b and 4b-2), and **the phone app night sprint** (section 4e,
ADR-034). Then Clones and Shadows (section 4c) and the rest of this list.

1. **A** — done (plan lock, PR #6).
2. **C** — Gate & Link: done (PR #7).
3. **B** — Brain & AI routing: done (PR #8, gate test passed 3 Nov).
4. **P** — PC Control: R1 first, then PC0–PC7.
5. **E** — Voice, after the RAM upgrade (16 GB or more). If the RAM is late, work stays on P.
6. **D** — Phone app, with J3.
7. **F** — Kairu Call, presence and face check (phone and PC).
8. **I** — a short trip mission, then **G** and **H**.
9. **K** — hardening and local models (L2) after the RAM upgrade.

### How every phase runs

1. Claude Chat writes the phase plan; the owner approves it and says **GO**.
2. Claude Code builds it on a branch in `sungjenwoo/Kairuu` and runs the checks.
3. The owner tests it on their own PC.
4. The owner merges it into `main`.
5. The progress chart is updated (with the four bars added by Master Plan v2.0: Gate & Link, Calls &
   presence, Shadow Missions, Trip & long missions).

## 4b. The Kairu App workspace — W1 (ADR-030, built next)

The owner's words (11 Nov 2026): build the whole Kairu app, inspired by Claude's app, and at the left side we can see all
the projects. W1 is the home window; the bar stays the quick way in, and the workspace is where the work lives.

| Part | What it is |
| --- | --- |
| Left sidebar | Kairu's logo, **New mission**, search, **Projects** (each with its missions), **Recent** missions, and the pages Guardian, Clones, Shadows, Devices and Settings |
| Middle | The open mission: your orders and Kairu's short answers, each step as it finishes, and a box at the bottom to give the next order |
| Right panel | **Progress** (the steps of the order that runs), **Needs you** (Guardian's approval card: the action, its details and tier, a `yes` box and a PIN box) and the mission's details |
| Top | Guardian's state (running, Safe Mode, not running) and a red **Stop**, the same as `kairu stop` |
| Project page | Its name, its own notes, and its missions; rename, archive |
| Clones, Shadows, Devices | Pages that show what each will be (section 4c); they do nothing yet |

**How it is built.** Its own program, like the bar (`kairu workspace`). The standard library only: a small web server on
127.0.0.1 with a random key for each start, and the page opened as an app window in the installed Chrome or Edge, with a
profile folder of its own. No new dependency. Every order goes through the same task core as the bar, so Guardian decides
every step; the workspace holds no authority. The `yes` and PIN boxes are filled only by the owner's own typing, and go to
Guardian, as in the bar. Projects, missions and their messages are kept on the PC only (`data/workspace.db`), never in the
audit log, never sent anywhere.

**Done when (the W1 gate test).** On the owner's PC: `kairu workspace` opens the window; a project made, renamed and seen
on the left with its missions; "open Notepad and set volume to 20" in a mission shows both steps and closes Notepad
with "close Notepad"; "restart" opens the card and a refusal does nothing; Stop puts Guardian in Safe Mode; closing and
opening the window keeps every project and message; another program on the PC that calls the server without the key gets
nothing. Every existing test still passes.

**Later in the app (not W1):** the Ember Glow bar (the bar's new look), files made by a mission shown in the right panel,
voice inside the workspace, the Clones and Shadows pages working. All but the last are W2 (section 4b-2); the Clones and
Shadows pages start working with Clones and with Phase H.

## 4b-2. Finishing the workspace — W2 (ADR-036)

The owner's words (11 Nov 2026): "Let's finish the workspace", and, asked which parts: "choose the best … and start
building". W2 is built on W1 and merged after it.

| Part | What it is |
| --- | --- |
| **Files panel** (right) | The files this mission's steps made, changed, opened or put in the Recycle Bin, newest first, each with **Open** and **Show in folder**. A button sends the same order as typing `open file <name>` or `show <name> in its folder`: through the task core, so Guardian decides it |
| **Three file skills** | `files.write` (Medium, already in the policy, now with code): `make a file called notes.txt saying …` makes a NEW text file in the work folder, never overwrites, and `undo` puts it in the Recycle Bin. `files.open` (Medium, new): opens a file in the work folder with its own app, through Explorer; never a program, script or shortcut. `files.show` (Low, new): shows a file or folder of the work folder in Explorer, selected. All three are fenced to the work folder, and may be steps of a plan |
| **Voice in the workspace** | With `voice.enabled`: a mic button by the box you type in, and Ctrl+M while the window is in front. Your words show live; each spoken order goes into the open mission (or a new one, which the window opens); Kairu answers questions aloud, Tenmin's way. Same rules as the bar: the mic is off at every start; only your click or key switches it on; voice never approves; "Kairu, stop" stops everything |
| **One mic** | The voice link is claimed when a mic is switched on and let go when it goes off, so the bar and the workspace share it: whichever switched on first has it, and the other says so |
| **Open the workspace** | `open the workspace` (typed or said) in the bar opens it, starting it if it isn't running: the same as `kairu workspace` |
| **Ember Glow** | The owner's design (10 Nov): a smoky glass bar above the box you type in, with a soft glow under it and small embers drifting up. Blue with your words while listening, red with the step while working, a short white "Done", gone when there is no work. The logo becomes the sketch's tile with its ring blue or red. The Kairu bar gets the same colours as an ember strip under its box |

**Safety.** The workspace still holds no authority: the file buttons and every spoken order go through the task core, so
Guardian decides every step. `files.open` refuses programs, scripts and shortcuts by their kind (`.exe`, `.bat`, `.cmd`,
`.ps1`, `.vbs`, `.js`, `.msi`, `.lnk` and the like), so opening a file never runs code. `files.write` writes text kinds only
and its words are private (the audit log keeps a hash). The mic goes off on Stop and every emergency stop, when the PC locks
or sleeps, when the last workspace window has been closed for 15 seconds, and when the workspace ends. Opening the workspace
from the bar starts Kairu's own window and nothing else; it changes nothing on the PC.

**Done when (the W2 gate test).** On the owner's PC, with W1's gate test passed: `make a file called gate.txt saying hello`
shows gate.txt in the Files panel; **Open** opens it in Notepad and **Show in folder** shows it in Explorer; `open file
notepad.exe` is refused; `undo` puts gate.txt in the Recycle Bin; with the mic on in the workspace, "Kairu, open Notepad and
set volume to 20" shows blue words, then red steps, then the mission's steps; a spoken question is answered aloud; the bar's
mic says the workspace has it; closing the window switches the mic off; `open the workspace` in the bar opens the window.
Every existing test still passes.

## 4c. Clone and Shadow (owner, 11 Nov 2026)

| | Clone | Shadow |
| --- | --- | --- |
| What | A permanent copy of Kairu on another PC of the owner's ("stays pakka, all the time") | A temporary helper on a friend's PC |
| Job | Works with Main Kairu as a team on one project: the work is split equally or unevenly (a stronger PC or the owner's choice takes more), and they talk to each other to finish it | Helps the friend with their work while the owner keeps Main Kairu |
| Ends | Never by itself | When the work is done, or at once when the owner says "come back" |
| Safety | Same Guardian rules; High steps come to the owner for the PIN, never to the other Kairu | Master Plan v2.0's Shadow rules (ADR-020): one shared folder, the friend's Stop, nothing left behind, only a report comes back |
| Workspace | **The same as Main Kairu's**, synced over Kairu Link; Main Kairu keeps the main copy. Each step in a shared mission shows which Kairu does it | **Its own, starting empty**, with only the friend's project. It never holds the owner's projects, missions, messages or memory, and the owner's workspace never receives the friend's code |
| The owner sees | Its live steps inside the owner's own missions | One card: where it is, how far it has got, **Come back now**; then its report |
| Phase | New, after W1 | H |

**Decided (owner, 11 Nov 2026, ADR-031): A.** A Shadow keeps working when the owner's PC is off: it takes its own small
brain (free cloud AI only) with a temporary key that ends when it comes back or is called back. Its separate, empty
workspace is what makes this safe: it carries nothing of the owner's. On return its workspace is wiped and its key
revoked; only the report comes back. This changes ADR-020's "no AI or keys on the friend's laptop"; everything else in
ADR-020 stays.

**A Shadow comes home smarter (owner, 11 Nov 2026, ADR-032).** A Shadow brings back what it learned, never what it
saw. While it helps the friend it notes general know-how: how an error was fixed, which setup worked, a faster way to
do something. When it returns, it explains to Main Kairu, in plain words, what it learned and why it helped. Main Kairu
asks the owner, and keeps a lesson only after the owner's yes; from then on every Kairu of the owner's (Clones too) knows it.

- A lesson is general know-how only. Anything with the friend's code, file names, names, accounts or personal data is
  removed automatically before the Shadow leaves the friend's laptop, and checked again by Main Kairu on arrival.
- The friend is not asked. The lessons taken appear on the Shadow's report of what it did, which the friend sees.
- A lesson never grants a permission or weakens a Guardian rule, and it can be removed later (System Architecture
  v1.1, section 13.3, RecallOps).

**Also in Phase H (owner, 11 Nov 2026, ADR-033):**

| Feature | What it does |
| --- | --- |
| **Glass box receipt** | The friend can watch every step live. At the end the friend and the owner each get a signed receipt: the files the Shadow read and changed, what it changed, the lessons it took, and that nothing else was copied out |
| **Teach-back** | Before leaving, the Shadow gives the friend a short spoken walkthrough of what it built and how to carry on, in the Tenmin style (short, warm, one question back) |
| **Call the master** | A risky request from the friend (High, or anything the Shadow isn't sure of) is not guessed: the Shadow calls the owner with Kairu Call and waits for the owner's answer. The friend can also reach the owner this way |

**Later, not in Phase H:** **Shadow squad**, one Shadow per teammate's laptop, each with its own workspace, coordinated by
Main Kairu.

**For the Buildathon pitch:** lead with "Comes home smarter".

## 4e. The phone app tonight (owner, 11 Nov 2026, ADR-034)

The owner's words: once the workspace is done, build the phone app continuously, no breaks, until 2 am. Phase D (App
Master Plan v2.0, Part 3, D0–D9) moves ahead of Clones and Shadows and runs as a night sprint, stage by stage:

| Stage | Tonight? | Why |
| --- | --- | --- |
| D0 Setup | Yes | The app builds on GitHub, installs with ADB, opens |
| D1 Link & pairing | Yes | QR pairing, text chat with Kairu |
| D2 Approvals & STOP | Yes | Phone approval for High, STOP both ways |
| D3 Remote PC control | Yes | Phone orders run through the PC task core, live steps on the phone |
| D4 Missions & research | If time allows | Research from the phone, queue while the PC is off |
| D5–D9 | No | A 0.6 GB model download, real scam SMS tests, and D9's 24-hour battery test can't finish in one night |

Each stage is still: build on a branch, the owner's gate test on the Mivi phone, then merge. A stage is not called done
before its gate test. Every rule of Phase D stays as written (Guardian decides everything; the phone sends requests, never
orders; High needs the owner's approval; Critical has no button).

## 4d. The owner's new feature list (11 Nov 2026, for later phases)

Modes (study, hackathon, game, sleep); watch and learn; laptop doctor; screen eyes; time machine; teacher mode;
theft guard; "is this safe?"; hackathon autopilot; research team; morning brief; game handover ("Kairu, take over");
sleep call handling (only when the owner says so; Kairu says "Hi, I'm Kairu", answers "Saitej's assistant, Kairu, yes,
an AI" when asked, never pretends to be the owner, and wakes the owner for anything important); match time (Kairu
invites the owner to a game such as chess or a speaking challenge, at most once a day, never in study mode or quiet
hours). Each gets a tier in `policy.yaml` and a plan of its own before it is built.

## 5. Old stages → new phases

| v1.3.7 stage | Now |
| --- | --- |
| Stage 0 — setup and decisions | Done in practice: repository, CLAUDE.md rules, CI, Master Plan approval, the plan lock (Phase A) |
| Stage 1a — safe skeleton | Guardian core + Guardian program (done); grants and sessions come with later phases |
| Stage 1b — Kairu 0.1 text companion | B (Model Gateway, privacy filter, usage display, `kairu ask`) |
| Stage 2 — reliable single-device tasks | B (Mission Cards), P (PC Control) and G |
| Stage 2.5 — secure remote access | C (Gate, Link, pairing) |
| Stage 3 — memory and RecallOps | B (Mission Cards, checkpoints) and D (memory sync); RecallOps detail in K |
| Stage 4 — voice | E (App Master Plan Part 2) |
| Stage 5 — Auto Mode | I (long missions) |
| Stage 6 — device expansion | D (phone); the laptop is the PC, so no second computer |
| Stage 7 — recognition, proactive help, Guardian monitors | F (face check), J (monitors) |
| Stage 8 — performance | K |

Tests from v1.3.7 (T-numbers, G-numbers) still apply to the phase that now holds their feature.

## 6. Rules that do not change

- Guardian is the only authority. Monitors watch and report; they never act, approve or change rules.
  The brain only thinks and answers; missions and the Kairu bar's tasks only ask Guardian to run their steps.
- Web pages, files, emails and screen text are data, never orders. Deletes go to the Recycle Bin.
- Low and Medium go ahead within scope; High needs "yes" + PIN (later: fingerprint on the phone);
  Critical is always blocked, with no approval path on any device.
- Secrets and sensitive data stay local; other private data goes to cloud AI only after approval. A question
  with no personal data may go to a no-training free provider without asking (option A, ADR-026).
- Free to run: no paid Claude API, free-only calls, no card, no hidden limits, no spending cap unless set.
- Low RAM for now: RAM-heavy parts wait for the upgrade.
- Two brains: Reasoning & Decision separate from Orchestration.

## 7. Open decisions

| Decision | Status | Needed by |
| --- | --- | --- |
| D1c — what happens to repositories `kairu` and `kairu-claude` | Open; any archiving needs separate approval | Any time |
| D18 — disk-encryption method | Open; meanwhile keys are sealed with DPAPI (Link keys, Gmail key, provider keys) | Before more secrets are stored |
| D26 — audit-log retention after memory deletion | Open; interim rule kept in Phase B: hashes only, never content | Phase D (memory sync) |
| D27 — The Agency personas | Recorded as runtime agents under Guardian by the Master Plan approval; owner to confirm (ADR-012, ADR-016) | Phase G |
| Free cloud providers | **Checked 29 Oct:** Groq first, Cloudflare Workers AI second (Cerebras needs a card now), OpenRouter spare — **accepted 2 Nov** (ADR-027) | Done |
| Phase B's built choices (privacy key in the policy, the "ask" message, how missions go on) | **Accepted 2 Nov** (ADR-027) | Done |
| Reading files in a mission (a folder you approve for reading) | Not built in Phase B. Belongs to **Phase I** (long missions, on B's Mission Cards) | Phase I |
| Stopping from the phone (a Stop button that pauses every mission, Master Plan "Stop buttons") | Not built in Phase B. Belongs to **Phase D** (the phone app) | Phase D |
| Phone offline model (about 1–3B, compressed) | Chosen in Phase D after testing on the phone (Gemma 3 1B first) | Phase D |
| Voice engine (ADR-008) | Chosen in Phase E after the RAM upgrade, offline so the voice never leaves the PC | Phase E |
| Decisions K-1 to K-8 (Kairu bar, hotkey, browser profile, safe commands, speaking after tasks, voice before RAM) | **Accepted 3 Nov** with the App Master Plan (ADR-028); each can be changed before its stage starts | Done |
| A Shadow when the owner's PC is off (section 4c) | **Decided: A** (its own small brain, a temporary key), ADR-031 | Phase H |
| Wake a sleeping PC | With the home Gate (old phone at home), ADR-025 | When the home Gate is planned |
