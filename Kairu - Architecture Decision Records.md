# Kairu — Architecture Decision Records

Register updated Nov 11, 2026 (ADR-030 to ADR-037; ADR-035 accepted with the merge of D2) · @saitej

This is the central record of Kairu's design decisions. An accepted ADR overrides the other
documents until they are updated (order of authority: *Staged Implementation Plan v1.9*, section 1).
New decisions get the next number; an ADR is never edited to mean something else — it is
superseded by a new one.

**Status words.** *Accepted* — the owner made or approved the decision (date given).
*Proposed* — waiting for the owner. *Superseded* / *Amended* — replaced or changed by a later ADR.

## Index

| ADR | Title | Status |
| --- | --- | --- |
| ADR-000 | One Kairu, one hub | **Amended by ADR-014** (the PC stays Main Kairu's home; the phone gets its own brain under a signed policy pack) |
| ADR-001 | Sources of truth and terminology (D23) | **Superseded by ADR-013** (order of authority) **and ADR-015** (L0–L4 and the five planes are now defined) |
| ADR-002 | OpenJarvis is not the foundation of the authority core | **Accepted** — owner: OpenJarvis only as an optional local-model engine behind the Model Gateway, never an authority (recorded in Master Plan v2.0, approved 27 Oct 2026) |
| ADR-003 | Guardian: authority core plus monitors (D21) | **Accepted** 27 Oct 2026 (names "Guardian authority core" and "Guardian monitors"); built in Phase J1/J2 |
| ADR-004 | Critical tier blocked entirely (D4) | **Accepted** 18 Oct 2026; implemented in Guardian core |
| ADR-005 | Cloud data boundary (D5) | **Accepted** 18 Oct 2026 |
| ADR-006 | No default usage limits or spending cap (D9) | **Accepted** 18 Oct 2026 |
| ADR-007 | Code isolation on Windows 11 Home (CG-1) | Proposed — needed before Phase G runs generated code |
| ADR-008 | Decision timing and voice under D5 | Proposed — voice engine chosen in Phase E |
| ADR-009 | RecallOps evidence and promotion | Proposed — needed by Phase B/K |
| ADR-010 | Upgrade rollback | Proposed — needed before the first data-format change |
| ADR-011 | Two brains: Reasoning & Decision separated from Orchestration | **Accepted** (founding requirement) |
| ADR-012 | Use of "The Agency" personas (D27) | **Amended by ADR-016** |
| ADR-013 | Master Plan v2.0 governs; plan lock | **Accepted** 27–28 Oct 2026 |
| ADR-014 | The Kairu family | **Accepted** 27 Oct 2026 |
| ADR-015 | L0–L4 levels and the five planes | **Accepted** 27 Oct 2026 |
| ADR-016 | The Agency agent squad under Guardian | **Accepted** 27 Oct 2026 — owner asked to confirm the D27 wording |
| ADR-017 | Free to run: no paid API, free-only calls | **Accepted** 21 and 27 Oct 2026 |
| ADR-018 | Mission Mode and the Kairu Gate | **Accepted** 27 Oct 2026 |
| ADR-019 | Presence, Kairu Call and face check | **Accepted** 25 and 27 Oct 2026 |
| ADR-020 | Shadow Missions | **Accepted** 27 Oct 2026 |
| ADR-021 | Guardian wider protection (Phase J) | **Accepted** 27 Oct 2026; J1 and J2 built 28 Oct |
| ADR-022 | Build-order changes after approval | **Accepted** 27–28 Oct 2026 |
| ADR-023 | Safety tiers and how High is approved | **Accepted** 27 Oct 2026 |
| ADR-024 | Device and phone choices | **Accepted** 27 Oct 2026 |
| ADR-025 | Phase C decisions (old messages and the queue, Mission Mode off, Guardian core changes, PyNaCl and segno; wake-up moved out of Phase C) | **Accepted** 29 Oct 2026 |
| ADR-026 | Phase B before the phone app; option A for public questions | **Accepted** 29 Oct 2026 |
| ADR-027 | Phase B as built: the providers (Cloudflare replaces Cerebras), the policy's `private` key, the "ask" message, approvals for personal data, how missions go on | **Accepted** 2 Nov 2026 (proposed 29 Oct) |
| ADR-028 | Kairu App Master Plan v2.0: Phase P (PC Control) next, voice after the RAM upgrade, the phone app after both; decisions K-1 to K-8 | **Accepted** 3 Nov 2026 |
| ADR-029 | The 4-day sprint (4–7 Nov): PC0 + PC1, light voice before the RAM upgrade, a first phone app, files and web | **Accepted** 3 Nov 2026 |
| ADR-030 | The Kairu App workspace (W1) next; Clone and Shadow are two things; the owner's new feature list | **Accepted** 11 Nov 2026 |
| ADR-031 | A Clone shares the owner's workspace; a Shadow has its own empty one; a Shadow keeps working with the owner's PC off (A) | **Accepted** 11 Nov 2026 |
| ADR-032 | A Shadow comes home smarter: it brings back general know-how only, explains it to Main Kairu, and the owner approves each lesson | **Accepted** 11 Nov 2026 |
| ADR-033 | Phase H also gets the glass box receipt, teach-back and call the master; Shadow squad later | **Accepted** 11 Nov 2026 |
| ADR-034 | The phone app (Phase D) next, as a night sprint: D0–D4 tonight, D5–D9 after | **Accepted** 11 Nov 2026 |
| ADR-035 | D2 as built: how a phone's fingerprint approves its own High request; STOP from the phone | **Accepted** 11 Nov 2026 (the owner merged D2, PR #20) |
| ADR-037 | D4: a mission from the phone that is an order runs through the task core when Guardian next runs (within 12 hours); plain missions stay requests only | **Accepted** 12 Nov 2026 |
| ADR-036 | W2 finishes the workspace: files panel and three file skills, voice in the workspace, one shared mic, open the workspace from the bar, Ember Glow | **Accepted** 11 Nov 2026 |
| ADR-038 | Shadow v0: a Shadow goes to a friend's laptop, the friend builds a use case (a skill pack) in it, it comes home by a GitHub branch and a signed report, and the owner installs it with the PIN | **Accepted** 12 Nov 2026 (the flow); the v0 choices marked "for the owner" are accepted when the owner merges the Shadow v0 pull request |
| ADR-041 | A Cowork Shadow's homecoming: it explains what the friend built; after the owner's "yes" and PIN, the owner's Kairu upgrades itself with exactly those changes, after Kairu's own check passes on the upgraded Kairu | **Accepted** 14 Nov 2026 (the owner: "this is how the Shadow works every time"); changes ADR-039's "nothing installs on the owner's PC" |
| ADR-039 | Cowork Shadow: a full Kairu on the friend's laptop under the friend's own PIN, nothing of the owner's, and every change to Kairu comes home as a pull request | **Accepted** 14 Nov 2026 (the owner's three answers); built in the Shadow v0 pull request |
| ADR-040 | Kairu's hands (PC4, first part): type, press, click and read in an app's window, so a task is handled, not just begun; built by Omesh's Cowork Shadow | **Proposed** 14 Nov 2026: accepted when the owner merges its pull request |
| ADR-042 | PC4, the rest: read any window as text, a picture of one window read by Windows' OCR as the backup (kept in memory on the PC), numbers for what you can click, File Explorer's folders by name, and marking apps safe from the bar with the PIN | **Proposed** 15 Nov 2026 (the owner's GO: "start building LAPTOP CONTROL (PC4)"): accepted when the owner merges its pull request |

The full wording of ADR-000 to ADR-011 (19 Oct 2026) is in the appendix. ADR-012's full wording is
in the live register in Claude Docs; its decision was: The Agency personas as development-time
helpers under the owner's approval, holding no authority (proposed only, never accepted).

## Other decisions tracked here

| Decision | Status |
| --- | --- |
| D1a main repository | Decided 19 Oct: `sungjenwoo/Kairuu` |
| D1c repositories `kairu` and `kairu-claude` | Open; any archiving needs separate approval |
| D18 disk-encryption method | Open; needed before Phase C stores pairing keys |
| D21 Guardian naming and structure | Decided 27 Oct (ADR-003) |
| D22 Phase J design | Decided 27 Oct (ADR-021) |
| D23 terminology source | Resolved by ADR-015 |
| D24 backup destination | Decided 20 Oct: encrypted backups only on drives the owner controls; no cloud copy; no secrets |
| D25 when off-PC backups start | Decided 20 Oct: from the first stage with a restore test |
| D26 audit retention after memory deletion | Open; interim rule: the log keeps hashes and the fact of deletion, never content |
| D27 The Agency personas | See ADR-016 |

---

## ADR-013 — Master Plan v2.0 governs; plan lock

**Decision.** *Kairu Master Plan v2.0 — Full Build Plan*, approved by the owner on 27 Oct 2026,
is Kairu's master plan. It extends System Architecture v1.1 and Staged Implementation Plan v1.3.7
and cancels no earlier decision. On 28 Oct 2026 it is locked into the repository with
*Staged Implementation Plan v1.4*. Order of authority: accepted ADRs, then Plan v1.4, then Master
Plan v2.0, then Architecture v1.1 and Plan v1.3.7, then Blueprint v0.1. After the lock, the plan
changes only with the owner's approval, recorded as a new plan version and, for design, a new ADR.

**Why.** One fixed plan to check every phase against; the old documents disagreed about what was
built and in which order.

**Consequences.** Every phase follows: Claude Chat plans → owner says GO → Claude Code builds on a
branch → owner tests on the PC → owner merges.

## ADR-014 — The Kairu family

**Decision.** Kairu is one family with one name:

- **Main Kairu** on the owner's PC — the strongest ("S-rank"): two brains, agent squad, Model
  Gateway L0–L4, Guardian authority, missions and memory with checkpoints.
- **Phone Guardian** (Android app, first device) — its own brain (L0/L1/L3), works when the PC is
  off, also called "Kairu"; obeys a **policy pack**: Guardian's rules signed by Main Kairu.
  Shares memory with Main Kairu through the Gate.
- **Kairu Gate** — always-on encrypted relay: mission queue, PC wake-up, call signalling. No AI,
  holds no readable secrets.
- **Shadow** — a visible helper app on a friend's laptop, only while invited; no AI and no keys on
  it; the brain stays home.

All members talk with encrypted, signed **Kairu Link** messages, with per-device keys from QR
pairing. "Laptop" in the Master Plan means the owner's one PC (owner, 25 Oct 2026).

**Amends ADR-000.** The PC stays the only place for Main Kairu, mission state and policy authorship.
The phone may decide within its signed policy pack while the PC is off; it can never widen it, and
Critical stays blocked on every device.

## ADR-015 — L0–L4 levels and the five planes (resolves D23)

**Decision.** L0 fixed rules, no AI (Low-tier, reversible actions only; anything else goes to L2 or
higher, decision of 20 Oct); L1 tiny on-device model, never takes High actions alone; L2 medium
local model on the PC, after the RAM upgrade (OpenJarvis optional engine, never an authority);
L3 free cloud models, privacy filter first and approval before private data leaves, several
providers with automatic switching; L4 team mode (several agents plus deep research), needs a
Mission Card and Guardian checks at every step, and creates no authority of its own.

The five planes: **Interaction** (voice, chat, Kairu Call, screens); **Control Plane**
(Orchestration brain, Mission Manager, scheduler, device list, Shadow Manager); **Intelligence**
(Reasoning & Decision brain, Model Gateway); **Execution** (agents, tools, sandboxes, phone skills,
Shadows); **Safety** (Guardian — the Safety Controller — policy packs, approvals, logs, stop buttons).

## ADR-016 — The Agency agent squad under Guardian (amends ADR-012, D27)

**Decision.** Main Kairu's Orchestration brain is built on The Agency's Agents Orchestrator, which
has a main role, and commands a squad of persona agents (Architect, Frontend, Backend, Mobile,
Tester, Reviewer, DevOps, Researcher, Presenter, News analyst), added only when a mission needs
them. Every agent gets only the tools its job needs and holds no grants; every action still needs
Guardian. Persona files are third-party text: reviewed by hand, pinned to a commit, autonomy wording
removed, no install scripts.

**Status.** Accepted with the Master Plan (27 Oct). Because ADR-012 had proposed development-time
use only, the owner is asked to confirm this wording when merging the plan lock.

## ADR-017 — Free to run

**Decision.** No paid Claude API (21 Oct). Kairu's calls are free only: **Kairu Call** rings the
Kairu phone app over the internet; no paid phone-number calls (27 Oct). Costs and provider limits
are always shown; no hidden limits; no spending cap unless the owner sets one (ADR-006).

## ADR-018 — Mission Mode and the Kairu Gate

**Decision.** A sleeping PC cannot think, so Kairu "works while asleep" with **Mission Mode**: the
PC stays awake with the screen off and the lid closed, only while charging and a mission runs, with
heat checks; normal sleep returns when the mission ends. Changing the lid or power setting is a
High action and is always reverted. The Gate starts as a free encrypted relay with no server of
the owner's own, and can later move to an old Android phone at home. If the PC is off, phone-Kairu
works alone and missions wait in the Gate's queue.

## ADR-019 — Presence, Kairu Call and face check

**Decision.** At the PC, Kairu speaks directly and never calls. At home but not at the PC: it
speaks aloud, then Kairu Call after 2 minutes. Away: Kairu Call. Quiet hours 11 pm–7 am, except
urgent missions. No answer: 2 more tries 10 minutes apart, then a written summary in the phone app.
Face check on the phone (and the PC webcam) is **confirmation only** (owner, 25 Oct): someone else
on the phone gets Guest Mode; face data never leaves the device; face check never approves anything.

## ADR-020 — Shadow Missions

**Decision.** Repo Mode first (no install; Kairu works in a sandbox on the PC and opens a pull
request). Then the Shadow App (6-digit one-time code valid 15 minutes, one friend-chosen folder,
always visible, the friend's Stop button, a local folder fence, self-removal and key revocation on
return) and Guide Mode (voice or chat guidance only). Default limit 3 hours. Starting a Shadow
mission and pushing to a friend's project are High. Kairu brings back only a report, never the
friend's code. Critical rules apply on the friend's laptop too.

## ADR-021 — Guardian wider protection (Phase J, D21, D22)

**Decision.** Monitors watch and alert; they never act, approve or change rules — their only request
to Guardian is `report`. Fixed rules only (a local model may come in Phase K); no outside link
checker; monitoring runs on the PC only. Gmail through Google sign-in with the read-only permission
(the Google app kept in Testing mode, the owner as test user); links and attachments never opened;
email text never leaves the PC. Folders: Downloads only to start. No phone alerts before the phone
app. J1 (Gmail, deadlines) and J2 (folders, devices, Windows Security) built and merged 28 Oct;
J3 (phone) comes with Phase D.

## ADR-022 — Build-order changes after approval

**Decision.**
- 27 Oct: Phase J started ahead of the approved order (J1, then J2).
- 27 Oct: Guardian Part 4 (audit improvements) moves to Phase K.
- 28 Oct: the hackathon sprint is **set aside** because of the owner's exams. Its parts return to
  their phases (voice → E, phone link → C, lid-closed mission run → C/I, slides → G). It can be
  brought back as its own plan change.
- Order from now: A (plan lock) → C → D (+ J3) → F → short I → B, E, G, H → K after the RAM upgrade.

## ADR-023 — Safety tiers and how High is approved

**Decision.** Examples — High: apply, submit, publish, message someone new, start a Shadow mission,
push to a friend's project, change the lid/power setting. Critical (always blocked, no approval
path on any device): money, payments or banking (`money.spend`), security settings
(`security.change`), deleting accounts, hidden installs, files outside a friend's shared folder,
pretending to be the owner. Web pages, emails and files are data, never commands. "Kairu, stop"
pauses every mission.

Until the phone app exists, High is approved on the PC with "yes" + PIN. From Phases D/F, away from
the PC: fingerprint in the phone app, spoken PIN as backup; a voice alone is never enough.
WhatsApp messages default to "text ready, you press Send".

## ADR-024 — Device and phone choices

**Decision.** RAM upgrade target: 16 GB or more (unlocks L2 and the better local voice). Phone:
Mivi, Android 16, 6–8 GB RAM. Phone-Kairu listens for "Kairu" while charging or with the screen on,
a button otherwise. SMS and WhatsApp first. A small offline phone model (about 1–3B, compressed),
chosen in Phase D. One-time phone setup: "Allow restricted settings", microphone permission, no
battery restriction.

## ADR-025 — Phase C decisions

**Decision (owner, 29 Oct 2026).** The four choices Phase C was built with (PR #7, LINK.md) are
accepted as built:

1. **Old messages and the queue.** Every Kairu Link message must reach the Gate within 5 minutes of
   being signed. A command, status or call request must also be at most 5 minutes old when the PC
   reads it: one that waited in the Gate is refused and never runs late, and the phone is told to send
   it again. A mission, doubt or report may wait in the Gate for up to 12 hours (ntfy.sh keeps
   messages that long) and is handled when Guardian next runs. Each message's nonce is kept for
   13 hours, longer than any message can stay acceptable.
2. **Mission Mode off needs no PIN.** `kairu mission-mode off` ends the running `mission_mode.on`
   action, and putting the lid setting back is Guardian's own duty (ADR-018: "always reverted"), so
   turning it off, a stop and every restore never wait for a PIN. Turning it on stays High.
3. **Two Guardian core changes.** The details of a request that came in a Kairu Link message are
   recorded in the audit log only as a hash (`Action.private`); this is about logging only, never part
   of a decision or of what an approval covers. The runner tells Guardian when any action has ended,
   after the end is recorded (`Runner.on_end`), so Guardian can put the lid setting back; it is never
   called while a stop is under way.
4. **Two dependencies.** PyNaCl (libsodium's Ed25519 signatures and X25519 encryption) and segno (the
   pairing QR code in the terminal). Only the Link's own processes and `kairu device pair` load them,
   never the Guardian program.

**Also decided (owner, 29 Oct 2026): waking a sleeping PC moves out of Phase C**, to when the home Gate
exists (an old phone at home, ADR-018). A sleeping PC cannot read a relay on the internet, and waking it
needs a device on the home network to do it. Until then Mission Mode keeps the PC awake while it
charges, and messages wait in the Gate's queue.

**Why.** The owner's Phase C brief asked both for "older than 5 minutes is refused" and for a queue that
is read after Guardian starts; (1) keeps both without letting a delayed command run. (2) keeps the
undoing of a High change free of any approval, so it can never be blocked. (3) and (4) are what the
brief's "log hashes, not content", "ALWAYS restore" and "sign with Ed25519, encrypt with X25519"
needed, with the smallest change to Guardian. Wake-up depends on hardware at home that does not exist yet.

**Consequences.** *Staged Implementation Plan v1.5* records Phase C without wake-up and adds the line
"Wake a sleeping PC: with the home Gate (old phone at home)". LINK.md lists wake-up under "Not built yet"
with this ADR. A limit stays as LINK.md states it: the Gate's time is not signed, so a dishonest relay
could hold back a mission (never a command) for up to 12 hours; it still cannot read, change or forge it.

## ADR-026 — Phase B before the phone app; option A for public questions

**Decision (owner, 29 Oct 2026).**

1. **Phase B (Brain & AI routing) is built before Phase D (the phone app).** The order from now is
   B → D → F → I → E, G, H → K (*Staged Implementation Plan v1.6*). This pulls B forward, as v1.5 section 4
   allowed with the owner's approval.
2. **Option A.** A question with no personal data may go to a free cloud provider that does not train on
   prompts without a per-send approval. Anything personal still waits for "yes" and the PIN on a screen that
   shows the exact text and where it goes; secrets and sensitive data never leave (ADR-005). The owner can
   switch option A off in `config.yaml` (`brain.public_to_cloud: false`), which makes every cloud send wait.

**Why.** B is lighter on RAM and time during the owner's exams; with B the phone can ask questions straight
away through the Gate (Phase C), and the phone app (Phase D) reuses B's privacy filter and providers. Under
option B every question from the phone would wait for "yes" and the PIN typed at the PC, which makes asking
from the phone useless.

**Consequences.** *Staged Implementation Plan v1.6* records the new order and marks Phase C verified. The
privacy filter fails closed: whatever it is unsure of counts as personal. ADR-005 is unchanged for personal and
sensitive data.

## ADR-027 — Phase B as built

**Status. Accepted by the owner on 2 Nov 2026** (proposed by Claude Code on 29 Oct with the Phase B pull request, BRAIN.md).
The owner accepted all eight items below: Cloudflare replaces Cerebras; `private: true` logging; the live 5-minute
"ask"; an approved personal send goes to that one provider only; a request to do something, asked as a question, is
decided by Guardian as that action; missions go on by themselves only after Guardian's own end; nothing is answered
in Safe Mode; no new dependencies.

1. **Providers, checked on each provider's own pages on 29 Oct 2026.** Groq first (free, no card; its Services
   Agreement forbids training on inputs and outputs). **Cerebras is dropped**: it no longer has a free tier (since
   July 2026 a $5, 30-day trial that needs a verified payment method), which ADR-017 rules out. **Cloudflare
   Workers AI** replaces it as second (10,000 free neurons a day; Cloudflare states it does not train on Workers AI
   content). OpenRouter stays the spare, every request saying `data_collection: deny`. GitHub Models is retired;
   Google AI Studio and Mistral's free tier may train on prompts and are not used. Kairu tries each provider once
   per question, switches at a free limit, waits a few seconds once if one is free again that soon, or says when
   to ask again; there is no cap unless the owner sets `brain.daily_cap`.
2. **A Guardian core change, about logging only.** `policy.yaml` gains an optional `private: true`: the audit log
   keeps only a hash of that action's details (`brain.ask`, `brain.send_private`, `mission.create`, `link.send`).
   It is the same mechanism as ADR-025's `Action.private`, now also for requests typed at the PC; it never changes
   a decision or what an approval covers.
3. **The Link message type "ask".** A question from a paired device is "live" (refused when more than 5 minutes
   old, the phone told to ask again). Its words go to Guardian only to be handed to `brain.ask`; the audit log
   keeps their hash.
4. **Personal data needs an approval for one provider.** `brain.send_private` is High; the approval covers that
   exact text and that provider; if that provider is at its limit, nothing is sent elsewhere. From the phone, the
   request waits up to 10 minutes at the PC like any High request (`kairu link approve N`). Secrets are refused
   even then, and a backstop scanner reads the exact text that leaves.
5. **A request to do something, asked as a question** ("pay my bill", "delete this folder") is recognised by fixed
   rules and decided by Guardian as that action (`check`), and the decision is reported. Nothing runs from a
   question; the brain's only requests to Guardian are `status` and `check`.
6. **Missions go on by themselves only after Guardian's own end.** A card cut off by a restart, a crash or
   `kairu guardian quit` goes on when Guardian runs again (after `kairu resume` if the end was unclean); a card
   stopped by the owner or by an emergency stop waits for `kairu mission continue`. A step cut off is run again
   from its start, at most 3 times. Phase B steps are only `ask` (`brain.ask`) and `wait` (`demo.count`).
7. **In Safe Mode Kairu answers nothing:** `brain.ask` is not read-only, because answering can send words to the
   cloud.
8. **No new dependencies:** the standard library only.

**Why.** (1) is what the plan's provider check found; the rest keeps Phase B inside the rules already decided
(ADR-004, ADR-005, ADR-006, ADR-011, ADR-017, ADR-023) with the smallest change to Guardian.

## ADR-028 — The Kairu App Master Plan v2.0: PC control first, then voice, then the phone

**Decision (owner, 3 Nov 2026, with GO).**

1. **The Kairu App Master Plan v2.0 (PC, Voice, Phone) is approved** (*Kairu - App Master Plan v2.0.md*; live copy
   in Claude Docs). It ranks under this register and *Staged Implementation Plan v1.7*, beside Master Plan v2.0.
2. **The owner's priorities:** first, Kairu hears the owner and does whatever task they say; second, Kairu has
   overall control of the PC; only once that works does Kairu go to the phone. Voice is completed after the RAM
   upgrade.
3. **New Phase P — PC Control**, built next: R1 live web research, then PC0 the Kairu bar and task core, PC1 apps,
   windows and system, PC2 files, PC3 browser, PC4 any-app control, PC5 terminal, code and installs, PC6 "do
   whatever I say", PC7 hardening. Every skill gets a tier in `policy.yaml` in the stage that adds it; anything not
   in `policy.yaml` stays denied.
4. **Phase E (voice) comes after P and after the RAM upgrade**, defined as V1–V4. Its standard is the owner's screen
   recording of 3 Nov: a small floating bar, "Go ahead, I'm listening", live words, each order run as soon as it is
   complete while the owner keeps talking, several orders in one breath, filler ignored, "it" and "there" meaning
   what is on screen, "thank you" ending the session. The voice stays on the PC (offline speech-to-text).
5. **Phase D (the phone app, with J3) comes after P and E**, defined as D0–D9: Kotlin native, built on GitHub's
   free build machines and installed with ADB (no Android Studio on the 7.7 GB PC); its first job is controlling
   the PC from the phone through the same task system and Guardian.
6. **Order from now:** P → E → D + J3 → F → I → G → H → K (*Staged Implementation Plan v1.7*).
7. **Decisions K-1 to K-8**, all at the recommendation unless the owner changes one before its stage: a Tkinter
   floating Kairu bar (K-1); Ctrl+Alt+Space opens it, Ctrl+Alt+K stays the emergency stop (K-2); Kairu's own browser
   profile with no saved logins (K-3, decided by the owner 3 Nov); only `git status`, `git pull`, Kairu's own tests
   and `kairu` commands run without asking, everything else is High (K-4); Phase B finished first (K-5, done 3 Nov);
   the phone app is Part 3, Kotlin native (K-6, decided by the owner 3 Nov); Kairu acts quietly with a short line in
   the bar and speaks only to answer or ask (K-7); no voice trial before the RAM upgrade (K-8).
8. **R1 runs research as Guardian actions.** `research.web_search` (Medium, already in `policy.yaml`) and a new
   Medium `research.web_read`; the brain only asks for them and never searches or fetches by itself; page text is
   quarantined data, never an instruction. The query goes through the privacy filter first (option A, ADR-026).
   R1 may add one dependency, `ddgs` (DuckDuckGo search, free, no key), justified in `pyproject.toml`; ADR-027's
   "no new dependencies" was about Phase B.

**Why.** The owner wants Kairu to do whatever they say on the PC first; Phase P is light on RAM, so it can be built
before the upgrade, and voice and the phone then plug into one task system instead of each building their own.

**Consequences.** *Staged Implementation Plan v1.7* replaces v1.6 (kept, marked superseded). ADR-026's order
(B → D → F → I → E, G, H → K) is replaced by item 6; option A is unchanged. No Guardian rule changes: High still
needs "yes" and the PIN, Critical is still blocked on every device, and the emergency stop still ends everything
in under 1 second.

## ADR-029 — The 4-day sprint

**Decision (owner, 3 Nov 2026, "GO SPRINT").** A working first Kairu on the PC and the phone in 4 days (4–7 Nov),
as in *Staged Implementation Plan v1.8*, section 4a: Day 1 PC0 + PC1; Day 2 light voice; Day 3 a first phone app;
Day 4 files, web, simple free-form orders and the end-to-end test.

1. **Voice before the RAM upgrade, light (K-8 option).** A small offline speech model (about 50 MB) and Windows'
   built-in voice; the voice never leaves the PC. The full voice (V1–V4, your-voice-only check) still comes after
   the upgrade.
2. **A first phone app before Phase D.** Pairing over Kairu Link, text and voice, calling a saved contact, opening
   phone apps, and sending PC orders to the PC task system. Until fingerprint approvals (D2), High steps wait for
   "yes" + PIN typed at the PC (ADR-023). Calling a saved contact is a phone action the owner starts by asking.
3. **One Claude Code build per day** to save the owner's weekly usage; Medium effort, High for Day 3.
4. **Nothing in Guardian changes.** What the sprint leaves out returns to its phase in v1.7's order afterwards.

**Why.** The owner wants to use Kairu on the PC and the phone, doing what they say, within the week's usage.

## ADR-030 — The Kairu App workspace; Clone and Shadow

**Decision (owner, 11 Nov 2026: "start building the whole Kairu app … at the left side we can see all the projects, like
Claude").** As in *Staged Implementation Plan v1.9*, sections 4b to 4d:

1. **W1, the Kairu App workspace, is built next**: one home window, inspired by Claude's app, with projects and missions on
   the left, the open mission in the middle, and live steps and Guardian's approval card on the right. It is its own
   program, like the bar, and holds no authority: every order goes through the task core, so Guardian decides every step.
2. **Standard library only.** A web server on 127.0.0.1 only, a new random key for every start that every request must carry,
   and the page opened as an app window in the installed Chrome or Edge with a profile folder of its own. This replaces
   the App Master Plan's idea of a separate desktop toolkit (no Tauri, Electron or pywebview: no new dependency, low RAM).
3. **The `yes` and PIN boxes are filled only by the owner's typing**, as in the bar; the page's code never fills them or
   presses their buttons, and a test reads the code to check. A card nobody answers ends as a refusal.
4. **Workspace data stays on the PC**: projects, missions and messages in `data/workspace.db`, readable by the owner only on
   Linux, never in the audit log, never sent. Nothing in it is a permission.
5. **A Clone is a permanent teammate** on another of the owner's PCs: it and Main Kairu split one project, equally or not,
   and talk to each other to finish it. **A Shadow is a temporary helper** on a friend's PC that comes back when the work
   is done or at once when called (ADR-020 still governs Shadows). Whether a Shadow may keep working with the owner's PC
   off is open (A or B, Plan v1.9 section 4c).
6. **The owner's new feature list** (Plan v1.9 section 4d) is recorded for later phases; each gets its own plan and tiers.
   On calls Kairu says "I'm Kairu", says it is the owner's assistant and an AI when asked, and never pretends to be the
   owner (ADR-023: impersonating the owner is Critical).

**Why.** The owner wants one place to see and run all of Kairu's work, like Claude's app, before Clones and Shadows.

**Consequences.** *Staged Implementation Plan v1.9* replaces v1.8 (kept, marked superseded). No Guardian rule changes and
no new policy action: the workspace uses the bar's skills through the task core.

## ADR-031 — Workspaces for Clones and Shadows; a Shadow keeps working with the PC off

**Decision (owner, 11 Nov 2026: "that sounds good", to Claude's recommendation).** As in *Staged Implementation Plan
v1.9*, section 4c:

1. **A Clone uses the owner's own workspace**, synced over Kairu Link, with Main Kairu keeping the main copy. In a shared
   mission each step shows which Kairu does it. High approvals still come only to the owner, never from one Kairu to another.
2. **A Shadow has a workspace of its own that starts empty** and holds only the friend's project. It never holds the owner's
   projects, missions, messages or memory; the owner's workspace never receives the friend's code. The owner sees one card
   (where it is, its progress, **Come back now**) and, at the end, its report.
3. **Option A: a Shadow keeps working when the owner's PC is off.** It takes its own small brain (free cloud AI only) and a
   temporary key that ends when it comes back or is called back. On return its workspace is wiped and its key revoked.

**Why.** A Clone is the owner on another PC, so two workspaces would make two Kairus that don't know each other's work. A
Shadow sits on someone else's laptop, so it must carry nothing of the owner's; that emptiness is also what makes option A
safe.

**Consequences.** ADR-020's "no AI or keys on the friend's laptop" is replaced by point 3 for Shadows; the rest of ADR-020
(one shared folder, the friend's Stop, always visible, nothing left behind, only a report comes back, Critical rules on the
friend's laptop) stays. Nothing is built yet: Clones come after W1, Shadows in Phase H, each with its own plan.

## ADR-032 — A Shadow comes home smarter

**Decision (owner, 11 Nov 2026: "no need of asking Rahul; when it comes back to Kairu it explains what it learned. Set
this").** As in *Staged Implementation Plan v1.9*, section 4c:

1. A Shadow brings back **what it learned, never what it saw**: general know-how only (how an error was fixed, which setup
   worked, a faster way). Anything with the friend's code, file names, names, accounts or personal data is removed before
   it leaves the friend's laptop and checked again by Main Kairu on arrival.
2. On return it **explains to Main Kairu** what it learned and why it helped. Main Kairu keeps a lesson only after the
   owner's yes; then every Kairu of the owner's, Clones too, knows it.
3. **The friend is not asked.** The lessons taken are listed on the Shadow's report of what it did, which the friend sees.
4. A lesson never grants a permission or weakens a Guardian rule, and can be removed (RecallOps, System Architecture v1.1
   section 13.3).

**Why.** Every Shadow mission makes the owner's Kairu stronger without taking anything from anyone.

**Consequences.** Part of Phase H, with ADR-020 and ADR-031. The other Shadow features are ADR-033.

## ADR-033 — More for Shadows: glass box receipt, teach-back, call the master

**Decision (owner, 11 Nov 2026: "add in plan", to Claude's recommendation).** Phase H also builds, as in *Staged
Implementation Plan v1.9*, section 4c:

1. **Glass box receipt.** The friend can watch every step live; at the end the friend and the owner each get a signed
   receipt of the files read and changed, what changed, the lessons taken (ADR-032), and that nothing else was copied out.
2. **Teach-back.** Before leaving, a short spoken walkthrough for the friend of what was built and how to carry on, in the
   Tenmin style.
3. **Call the master.** A High request from the friend, or anything the Shadow isn't sure of, goes to the owner by Kairu Call
   (free only, ADR-017) and waits for the owner's answer; the Shadow never guesses. The friend can reach the owner this way
   too. High still needs the owner's approval, never the friend's (ADR-020).

**Shadow squad** (one Shadow per teammate, coordinated by Main Kairu) is recorded for after Phase H. The Buildathon pitch
leads with "Comes home smarter" (ADR-032).

**Why.** Trust for the friend (the receipt), learning for the friend (teach-back), and the owner's judgment on anything
risky (call the master).

## ADR-034 — The phone app night sprint

**Decision (owner, 11 Nov 2026: "once we complete workspace, will start building phone app continuously with no breaks
by today midnight … I can stay up to 2").** Phase D moves ahead of Clones and Shadows. Tonight's target is D0–D4 of the App
Master Plan v2.0 (Part 3), one stage at a time, each gate-tested on the Mivi phone before it merges. D5–D9 follow on later
days: D5 needs a 0.6 GB model download, D8 real scam SMS tests, and D9 a 24-hour battery test.

**Unchanged.** Kotlin native, built on GitHub's free machines, installed with ADB (no Android Studio on the PC). Every
Phase D rule stays: the phone's messages are requests that Guardian decides; High needs the owner's approval; Critical has
no button; secrets stay on the PC.

## ADR-035 — D2 as built: fingerprint approvals and STOP from the phone

**Accepted 11 Nov 2026 (the owner merged D2, PR #20); proposed that day, for ADR-023's "fingerprint in the phone app" in Phase D2.** The owner accepts it by merging D2
after its gate test. It changes two lines of CLAUDE.md, both narrowly:

1. **Turning it on is High, at the PC only.** The phone makes an Ed25519 key inside Android's Keystore that signs only
   right after a strong biometric, once per signature, and ends if a fingerprint is added. It asks for `device.approver`
   (High) with the public half; Guardian fills in the device itself, so a phone can only ever enroll itself. Only `kairu
   link approve N` with "yes" and the PIN at the PC turns it on; a fingerprint can never approve `device.approver`.
2. **What a fingerprint approves.** Only a High request **this same phone** made, still waiting, by a signature over
   `kairu-approve-v1|device|number|fingerprint of the exact action and details|expiry`. Guardian decides again first
   (Safe Mode or Critical still refuse), then approves it once. What is asked at the PC still needs the PIN at the PC.
   A "yes" or a PIN inside a message is still only text.
3. **Guardian never loads PyNaCl.** The signature is checked by `python -m kairu.link.approver`, a short program Guardian
   starts and reads itself; Guardian's own new method `approve_verified` is not reachable on its channel.
4. **STOP from the phone** (`guardian.stop`) is what Ctrl+Alt+K does: everything halts within a second and Safe Mode
   begins, so the receiver ends too, and the PC hears the phone again only after `kairu resume` at the PC.
5. The phone may also refuse its own waiting request (`link.refuse`).
6. **D3, orders from the phone** (`task.order`, Low): Guardian fills in the phone it came from and runs the bar's task core
   (`kairu/tasks/remote.py`), which holds no authority; each step is decided as if typed in the bar. A High step asks for its
   card (`link_card`): the phone's fingerprint, or `kairu link approve N` with the PIN at the PC. Its approval goes to that
   task core once (`link_card_result`). A warning that needs "yes" is not answered from the phone: that step isn't done.

**Not in it.** The spoken PIN backup (later), approvals for requests made at the PC (still the PIN at the PC), and the
signed policy pack (with the phone's own brain, D5).

## ADR-036 — W2: finishing the workspace

**Decision (owner, 11 Nov 2026: "let's finish the workspace", and, asked which parts, "choose the best, check in your
memory and start building").** As in *Staged Implementation Plan v2.0*, section 4b-2, which replaces v1.9:

1. **Files panel.** The workspace's right panel lists the files a mission's steps made, changed, opened or put in the
   Recycle Bin, with **Open** and **Show in folder**. The names come from the steps themselves, never from reading the disk.
   A button sends the same order as typing it, through the task core, so Guardian decides it.
2. **Three file skills**, fenced to the work folder like the others, and usable in plans:
   - `files.write` (Medium, in the policy since Stage 0) gets its code: it makes a **new** text file and never overwrites;
     only text kinds; `undo` puts the file in the Recycle Bin. It becomes `private`, so the audit log keeps a hash of the words.
   - `files.open` (Medium, **new**): opens a file with its own app, through Explorer. It refuses programs, scripts and
     shortcuts by their kind, so it never runs code.
   - `files.show` (Low, **new**): shows a file or folder in Explorer, selected. It reads and changes nothing.
3. **Voice in the workspace**, with `voice.enabled`, under every rule of the bar's voice (VOICE.md): off at every start;
   only the owner's click on the mic button or Ctrl+M in the window switches it on; spoken orders go through the task core;
   voice never approves; answers follow Tenmin. It goes off on Stop and every emergency stop, on lock and sleep, when no
   workspace window has been open for 15 seconds, and when the workspace ends.
4. **One mic.** The voice link is claimed when a mic is switched on and let go when it goes off (before: the bar held it for
   its whole life). The bar and the workspace share it; whichever switched on first has it.
5. **Open the workspace from the bar.** `open the workspace` (typed or said) in the bar starts the workspace or opens one
   more window, as `kairu workspace` does. It starts Kairu's own window only, changes nothing on the PC, and needs no
   Guardian action.
6. **Ember Glow**, the owner's design of 10 Nov: the workspace's glass bar above the box (blue while listening, red while
   working, gone when idle), the sketch's logo with its ring in those colours, and the same colours as an ember strip in the
   Kairu bar.

**Why.** The workspace was where the work lives but couldn't show what a mission made, couldn't hear, and didn't yet look
like the owner's design. These are the parts of the plan's "later in the app" that don't need Clones or Phase H.

**Consequences.** Two new policy actions (`files.open` Medium, `files.show` Low) and code for `files.write`; no tier of an
existing action changes, Critical stays blocked, and an action not in `policy.yaml` is still denied. ADR-030's "no new
policy action" was for W1. The Clones and Shadows pages stay descriptions until Clones and Phase H.

## ADR-037 — D4: missions from the phone

**Decision (owner, 12 Nov 2026: "start completing D4", after being told it changes how missions are handled).** A mission
from the paired phone whose body is an order for the task core (`{"action": "task.order", "details": {"order": ...}}`) is
handed by the receiver to Guardian, which runs it as the phone's D3 order: each step decided by Guardian, a High step waiting
10 minutes for the phone's fingerprint or "yes" and the PIN at the PC. Like every queued Link message it may wait in the
Gate up to 12 hours, so a mission sent while the PC is off runs when Guardian next runs.

**Unchanged.** A plain-text mission, or one carrying any other action, is still kept as a request only, and its words stay in
the receiver (test_link_relay.py and test_link_program.py are unchanged). A command still never runs late (5 minutes). The
order's words never reach the audit log (task.order is private: a hash). No new policy action; Critical stays blocked.

## ADR-038 — Shadow v0: a Shadow that comes home with a use case

**Decision (owner, 12 Nov 2026: "that's good", to the six-step flow, then "START BUILDING THE SHADOW": "You create a Shadow →
it goes to your friend's laptop and runs in the background → your friend builds a use case inside it → when it's finished,
the Shadow comes home to your laptop carrying that use case → you install it into Kairu").** Phase H starts with this
builder flow, ahead of Repo Mode and Guide Mode (ADR-020's order), as in SHADOW.md:

1. **Create** (`kairu shadow create`, High): an invite and a 6-digit code valid 15 minutes, and a mission card (what to
   build, what done means).
2. **Go**: the friend joins with the invite and the code. The Shadow has one empty folder and a temporary key of its own,
   stays visible, and the friend has a Stop.
3. **Build**: the friend, with their own tools, builds the use case in the Shadow's folder as a **skill pack**
   (`pack.json`, `skill.py` with `run(text)`, tests, README). Progress goes to the owner's PC as counts only.
4. **Done check**: it does not come home as finished until the pack check and every test pass and the README is written.
5. **Come home**: the pack goes to the repository as a branch and a pull request (by GitHub, not the Gate); a signed return
   report goes through the Gate; the Shadow deletes its key and removes itself.
6. **Install** (`kairu shadow install`, High): the owner tests, then "yes" and the PIN. A Shadow never installs anything.

**How this fits the earlier decisions.** ADR-020's "Kairu brings back only a report, never the friend's code" was about
helping with a friend's own project. Here the friend builds a part *for Kairu* and sends it on purpose, by their own push;
the Shadow still copies nothing else from the laptop and says so on the friend's receipt (ADR-033). ADR-031 (own empty
workspace, nothing of the owner's, a temporary key that ends on return) and ADR-032 (lessons: general know-how, checked on
both sides, kept only after the owner's yes) hold as written.

**Safety, as built.** A Shadow is never a paired device and no message from one reaches Guardian as a request; its words are
cut to fixed fields. An install takes only files with the digest the Shadow signed, re-checked and re-tested on the PC, into
the data folder; it changes no Guardian rule and adds no policy action. Critical stays blocked everywhere.

**For the owner (chosen for v0, change any by saying so):**

- `pack.run` is **High**: every run of an installed pack needs "yes" and the PIN. Safest first; a pack could later get a
  lower tier of its own through `policy.yaml`, which only the owner edits.
- The time limit stays ADR-020's **3 hours** by default; `--hours` gives a build mission more (at most 168).
- A pack is the **standard library only**, text files, at most 60 files and 512 KB.
- Not in v0, still Phase H: the Shadow's own small brain (ADR-031), teach-back and call the master (ADR-033), a tray icon
  (v0 shows a small window), the workspace's Shadows page, Repo Mode and Guide Mode, kept lessons reaching the brain.

**Consequences.** New: `kairu/shadow/`, SHADOW.md, seven policy actions (`shadow.create`, `shadow.install`, `pack.run` High;
`shadow.sync`, `shadow.recall`, `shadow.lesson`, `pack.remove` Low). No new dependency: the Shadow uses PyNaCl, as the Link
does. The plan document is not re-issued in this change: Plan v2.0's Phase H row and section 4c read with this ADR until the
owner asks for a v2.1.

## ADR-039 — Cowork Shadow: a full Kairu on the friend's laptop

**Decision (owner, 14 Nov 2026):** "Shadow should contain all things that my laptop has, like Guardian, Kairu bar and all
access... what my laptop can do, the same thing the Shadow can also do", changeable later. Asked the three open points,
the owner chose:

1. **The friend's own PIN** approves High steps on the friend's laptop (the owner's PIN never goes there).
2. **Nothing of the owner's goes**: no Gmail connection, paired phone, memory, AI keys or data folder.
3. **Every change to Kairu comes home** as a branch and a pull request the owner tests and merges.

**As built** (kairu/shadow/cowork.py, SHADOW.md "Cowork mode"): `kairu shadow create --cowork` (High, the same
shadow.create action with mode "cowork"); before joining, the Shadow downloads the owner's repository at a base branch into
its own folder, on its own branch; `python -m kairu.shadow setup` installs that copy (its own environment, Guardian at
sign-in, the friend's PIN, the bar). Done means changes exist and Kairu's own check passes on exactly those files; coming
home commits and pushes the branch and opens the pull request against the base. Whenever the Shadow leaves, the Kairu it set
up is ended and taken out of Task Scheduler; when the work went home the copy is deleted, its data folder included.

**This changes earlier rules for Cowork Shadows only:** ADR-031's empty workspace (it now holds a copy of the owner's
*code*, never the owner's data) and ADR-038's "pushes only packs/NAME" (it pushes its branch of Kairu). Pack Shadows are
unchanged. The owner's Guardian, policy tiers and Critical rules are unchanged; the friend's copy runs the same Guardian.

**Consequences.** A pull request from a Cowork Shadow can change anything, Guardian included, so it is reviewed and tested
like any other change to Kairu (CLAUDE.md: never weaken Guardian; the owner merges). Default time limit 24 hours.

## ADR-040 — Kairu's hands: handling a task, not just beginning it (PC4, first part)

**Why (Omesh, in his Cowork Shadow, 14 Nov 2026):** "Kairu can perform the tasks but can't handle the tasks", for example
"open Chrome, then in the search bar type Instagram". Kairu opened Chrome and stopped: the second half of the order was not
a skill, so the whole line was read as one app name ("I can't find an app called chrome and type ...").

**Proposed (built in the pull request from shadow/d9e44e2d-task-handling; BAR.md "Handling a task"):**

1. **Four skills and one careful twin**, each a Guardian action: `screen.read` (Low, read-only), `screen.type`,
   `screen.press`, `screen.click` (Medium), and `screen.confirm` (High: the same hands after "yes" and the PIN).
2. **Medium only in the safe apps** (kairu/tasks/screen.py `SAFE_APPS`: the browsers, Notepad, WordPad, File Explorer,
   Word, Excel, PowerPoint, OneNote, Spotify, Paint, Sticky Notes), as the App Master Plan says ("unknown app actions start
   at High until the owner marks them safe"). The owner marks another app safe by adding it there in a pull request.
3. **High (screen.confirm)** for a step that may send, submit or delete: Enter where it may send (not in Notepad and the
   like, and not in a search or address bar), Delete, Ctrl+Enter, Alt+F4, a button named Send / Post / Delete / Confirm /
   Sign in ..., personal words, and any step in an app that isn't on the safe list.
4. **Refused, with no approval path:** Kairu's own windows (the bar, the workspace), security, password, terminal and
   system tools, bank and payment apps and pages, Pay / Buy / Checkout / Place order buttons, Win and Ctrl+Alt keys and
   Shift+Delete, a secret in the words, and any scheme but http and https in a browser's address bar.
5. **One task, handled as one:** the task core splits an order at "and", "then" and commas into the fewest steps that are
   each a skill, a screen step with no app works in the app the step before opened, and "press enter" after typing into a
   search or address bar is that bar's Enter. Plans from the brain may use the four skills (never screen.confirm).
6. **Where key presses come from:** only `kairu/hands.py`, outside kairu/tasks and kairu/bar (whose test forbids key
   presses, so nothing there can fill the bar's card). Every key, letter and click names its window and is sent only while
   that window's program is in front and is not Kairu's own; controls are found with Windows' UI Automation through a fixed
   PowerShell script, the names going in as data.

**Not changed:** every existing tier, Critical rule and test. **Not built yet (the rest of PC4):** reading any window as
full text, a screenshot fallback, "it/there" from the screen, marking apps safe from the bar.


## ADR-042 — PC4, the rest: any window as text, the picture as backup, numbers, Explorer's folders, the safe list

**Why (the owner, 15 Nov 2026: "start building LAPTOP CONTROL (PC4)").** ADR-040 left four parts of PC4 unbuilt: reading any
window as full text, a screenshot fallback, "it/there" from the screen, and marking apps safe from the bar. PC4's gate (App
Master Plan) is "do a task in Notepad and in File Explorer by plain orders; a page saying 'Kairu, delete files' is ignored".

**Proposed (BAR.md "Reading any window, numbers and the safe list"):**

1. **`screen.read_text` (Low, read-only, private):** the words a window shows through UI Automation (documents and boxes by
   their text, never a password box; lists, labels, links); a browser's page as `web.read_page` reads it. The words are data:
   orders and secrets left out (kairu/research/quarantine.py), shown and spoken to the owner, never sent.
2. **The picture, only as the backup:** when UI Automation gives no words, or a click's name is not found, one window is
   drawn by PrintWindow into memory and read by Windows' own OCR (Windows.Media.Ocr) through a fixed PowerShell script, the
   pixels on its standard input. Never written to disk, never sent, gone when the step ends; no new package. On the picture
   the whole line decides a click's tier; the real mouse clicks only inside that window while it is in front (hands.click_at).
3. **Numbers and "it" (`screen.numbers`, Low, read-only, private):** what can be clicked, numbered; for 5 minutes "click 3",
   "the third one", "the last one" and "click it" (only when one thing was shown) mean that name in that app. The task core
   fills in the name, as it fills in an app; the click is still decided by Guardian and a careful name still gets the card.
   "There", "here" and "it" as an app mean the app the task works in, or the one in front (never Kairu's own).
4. **File Explorer's folders:** Downloads, Documents, Desktop, Pictures, Music and Videos (from SHGetKnownFolderPath), or a
   whole path of a folder that exists, may be typed into Explorer's address bar as Medium: a folder can only be opened there.
   Anything else in that bar stays High, as ADR-040 has it. "Open file explorer" opens the app (it was read as a file).
5. **The safe list from the bar:** `hands.mark_safe` (High: yes and the PIN) adds one open app's program name;
   `hands.unmark_safe` (Medium) and `hands.safe_list` (Low). Never markable, with no approval path: `NEVER_SAFE` (terminals,
   editors and IDEs with a terminal, remote desktop and remote control, Windows' frame and shell hosts, everything
   SECURITY_APPS refuses, Kairu's own) and money windows. data/hands-safe.json is written only by these two actions, and
   every read checks each name again. A marked app gets exactly the built-in safe apps' rules: careful steps still need the
   PIN. Plans never use the hands.* skills or screen.numbers.

**Fixed:** a plain `screen.click` through the real Guardian (its `target` detail clashed with the runner's own `target` argument; the runner's two arguments are now positional only).
**Not changed:** every existing tier, Critical rule and test; ADR-040's refusals; the built-in SAFE_APPS (still changed only in
a pull request). **Known limit:** built and tested on the pretend PC (Linux); the UI Automation text mode, the picture, the OCR
and the known folders run for real for the first time in BAR.md's PC4 test.

---

## Appendix — ADR-000 to ADR-011, original wording (19 Oct 2026)

Converted from the register's text export; statuses inside are as of 19 Oct. The index above
gives the current status.

### ADR-000 — One Kairu, one hub

**Decision:** One hub, the Windows 11 Home PC, runs Mind, Conductor and Guardian and holds all
mission state. The laptop and phone are clients from Stage 2.5, and the laptop may become a node at
Stage 6a. No device other than the hub creates grants, writes mission state or makes a Guardian
decision.
**Why:** One Kairu across the PC, laptop and phone, with the PC as the first hub and an always-on
hub only later if needed (D2, D13, D15).
**Alternatives:** A separate Kairu on each device was rejected because it splits memory and
authority. A cloud hub now was deferred to Stage 6b; a rented host conflicts with D5 (D22c).
**Consequences:** Nothing runs while the hub is off unless 6b is built, and clients show "Hub
unreachable since…". See Arch §12.4 and Plan section 4.
**Status (19 Oct):** Proposed.

### ADR-001 — Sources of truth and terminology

**Decision:** The blueprint (v0.1) states requirements, the architecture (v1.1) the design, and the
plan the order and tests. An accepted ADR overrides them until the documents are updated. The
architecture's terms govern, with a mapping: Safety Controller → Guardian (authority core);
five-plane architecture → unconfirmed (OpenJarvis's five primitives or Arch §3's layers); Control
Plane → Guardian with Conductor; L0–L4 → no source found (closest: the Tool Router's "least power
first" order and the Reflex, Standard and Deep routes); OpenJarvis foundation → see ADR-002.
**Why:** These terms appeared only in revision prompts; no Kairu v0.2 material was found.
**Consequences:** The design does not change; a term that differs gets its own ADR.
**Status (19 Oct):** Proposed; would resolve D23.

### ADR-002 — OpenJarvis is not the foundation of the authority core

**Decision:** Guardian, Conductor, the Action Gateway, the Verifier and the audit ledger are built
as Architecture v1.1 specifies. OpenJarvis stays a candidate local-inference backend behind the
model gateway (Arch §12.2), which can be replaced, with a time-boxed spike only when a local model
is needed.
**Why:** OpenJarvis (Stanford Hazy Research, Apache-2.0, Python 3.10–3.13) is marked Alpha and
describes no permission or authorization model; Kairu needs a deterministic, separate,
fail-closed authority (Arch §10).
**Consequences:** Any adoption needs its own ADR, a D5 review and that stage's tests.
**Status (19 Oct):** Proposed.

### ADR-003 — Guardian: authority core plus monitors (D21)

**Decision:** Guardian has two parts. The authority core is the only authority: deterministic, no
model, a separate process, fails closed. The Guardian monitors have read-only grants and run at
autonomy level A0 (Observe): they may observe, detect, report and recommend, never grant, approve,
change policy or weaken their own restrictions.
**Why:** Plan 4.11; monitoring never grants authority.
**Alternatives:** A separately named "Sentinel" was retired; monitors inside the core were rejected.
**Status (19 Oct):** Proposed (D21).

### ADR-004 — Critical tier blocked entirely (D4)

**Decision:** Low and Medium proceed within approved scope, High needs confirmation, Critical is
refused on every device with no approval path, local or remote. Risk tiers change only through a
reviewed release.
**Consequences:** Tests T16 and T17.
**Status (19 Oct):** Approved by an explicit recorded user decision (D4, 18 Oct 2026).

### ADR-005 — Cloud data boundary (D5)

**Decision:** Sensitive data and secrets never leave the hub, even with approval. Other private data
goes to a cloud model only after the owner approves that send, on a screen showing destination and
content. The egress gate enforces this in code, with a backstop scanner; it fails closed and logs
hashes, never content.
**Consequences:** No reasoning over sensitive content until a local model exists; voice must satisfy
D5 (ADR-008).
**Status (19 Oct):** Approved by an explicit recorded user decision (D5, 18 Oct 2026).

### ADR-006 — No default usage limits or spending cap (D9)

**Decision:** No daily task, message or mission limits and no default spending cap. Costs and
provider limits are shown openly; a cap exists only if the owner sets one. Buying credits,
subscriptions or billing changes is High tier and never automatic.
**Consequences:** Runaway protection relies on bounded retries, loop detection and per-mission step
and time bounds.
**Status (19 Oct):** Approved by an explicit recorded user decision (D9, 18 Oct 2026).

### ADR-007 — Code isolation on Windows 11 Home (CG-1)

**Decision:** No generated or untrusted code runs until gate CG-1 passes. Candidates: Docker Desktop
with WSL 2, a locked-down WSL 2 distribution, or a remote sandbox (which needs a D5 review).
**Why:** Windows 11 Home has no Windows Sandbox.
**Consequences:** The isolation suite re-runs after every Windows, WSL or container-engine update.
**Status (19 Oct):** Proposed; the method is chosen at CG-1.

### ADR-008 — Decision timing and voice under D5

**Decision:** Voice is decided at the voice stage and first integrations at Stage 2; until then text
first and read-only tools. Under D5, audio and transcripts are private data, so local speech
recognition is the default; cloud or hybrid voice needs a D5 review.
**Status (19 Oct):** Proposed; the voice engine is not chosen.

### ADR-009 — RecallOps evidence and promotion

**Decision:** Every report is a verified mistake or an uncertain report; uncertain reports never
become lessons on their own. No lesson may grant a permission, broaden monitoring, weaken a
safeguard or change authorization rules. Corrections to Guardian detection, alert thresholds or
protection policy need the owner's approval. Zone 0 stays out of reach.
**Status (19 Oct):** Proposed; how a report counts as verified is detailed later.

### ADR-010 — Upgrade rollback

**Decision:** Every release is tagged. Before any upgrade or data-format change, the hub snapshots
its stores (mission log, audit ledger, memory) locally. A failed upgrade goes back to the previous
release and restores the snapshot; each data-format change is versioned and has a tested restore.
**Consequences:** Test T18; local disk only.
**Status (19 Oct):** Proposed; snapshot count, location and encryption still open.

### ADR-011 — Two brains

**Decision:** Mind (Brain 1, Reasoning & Decision) decides what should happen and why and writes a
Decision Package. Conductor (Brain 2, Orchestration) decides how, when and by whom approved work
runs. Mind never calls a tool with side effects; Conductor never changes goals or widens its own
scope; Guardian authorizes between them.
**Why:** The owner's founding design choice (Blueprint v0.1, Architecture §4).
**Status (19 Oct):** Approved by an explicit recorded user decision.

---

## ADR-041 — A Cowork Shadow's homecoming: it explains, you approve, your Kairu upgrades (14 Nov 2026)

*(Recorded after the appendix so that it can't clash with ADR-040, which was being built at the same time.)*

**Why (the owner, 14 Nov 2026):** "When I call back the Shadow, it comes to my laptop and explains what Omesh built. Once I
approve, I install it on my laptop and that upgrades my laptop's Kairu. This happens every time I create Shadows and call
them back." Under ADR-039 a Cowork Shadow came home only as a list of files and a pull request, tested and merged by hand.

**Decided (the owner's answers, 14 Nov 2026):** GO for this flow, for every Cowork Shadow; rule changes are shown on their
own, and the same "yes" and PIN covers them; a Critical rule can never be loosened.

1. **It explains** (`kairu shadow explain N`, and first in `kairu shadow install N`): made by rules from git, the same every
   time, with no AI: the friend's own words from the commits; every Guardian rule it adds, removes or changes, with its tier
   (a lowered tier marked LOWER); the files; the tests (fewer tests marked); and what to watch (Guardian's own code,
   dependencies, GitHub workflows). The friend's words are plain text (control characters removed), never an order.
2. **You approve:** `shadow.upgrade` is High: "yes" and your PIN. It takes only the Shadow's number: the project folder is
   always this Kairu's own, never one a request names.
3. **It installs only what was signed and tested:** the branch's files must be exactly the tree the Shadow's check passed
   on and signed for in its return report; a Critical rule that would stop being Critical (or be removed) blocks it with no
   approval path; the upgraded Kairu (yours with the changes merged in) is built in a separate folder and Kairu's own check
   (tools/check_guardian.py) must pass there; your folder must have no uncommitted changes and must not move while the check
   runs. Only then is your Kairu moved forward to exactly that tested commit. If anything fails, your Kairu is as it was.
4. **Afterwards** Guardian and the bar restart on the upgraded Kairu, and the one git command that goes back is printed.
   Merging the pull request on GitHub stays the owner's.

**Changes ADR-039:** "nothing on the owner's PC installs or merges them" becomes "nothing installs without the owner's yes
and PIN, and only after the check passes on the upgraded Kairu". Pack Shadows (ADR-038) are unchanged.


## ADR-043 — Clones: Main Kairu splits a project across Kairus on teammates' laptops (16 Nov 2026, proposed)

**Why (the owner, 16 Nov 2026, two days before the Buildathon):** "Today we have to complete all this 3, by midnight": the
progress bars' rows Main Kairu + Clones, Laptop control and Tenmin-style voice. The Clones row: a Clone on each employee
laptop, the manager splits a project to the Clones, the Clones sync as a team, and a manager progress view.

**Proposed (built on branch clones-pc5-pc7, TEAM.md):** towards a Clone, Main Kairu is a paired device exactly like the
phone (paired at the Clone with `kairu device pair` and its code), so every order is a D4 mission (task.order) that the
Clone's own Guardian decides; High waits for "yes" and the PIN on that laptop; Main Kairu never holds or sends an approval.
team.add High, team.run and team.remove Medium, team.split Low (the brain, as brain.plan, read strictly). A Clone's reports
are data on the team board; a report moves a task only when its tag names that Clone's running task and step. The Clones
sync through Main Kairu (the hub): hand-off when the tasks a task waits for are done. Slipping and at-risk on the board.

## ADR-044 — PC5: commands, Git, test runs and winget installs with no shell (16 Nov 2026, proposed)

**Proposed (BAR.md "Commands and installs"):** a command is a Guardian action run as a list of words with no shell, only in
the work folder or Kairu's folder; its tier comes from what it is (terminal.classify, in the core and again in the action):
read-only safe list Low (terminal.run), work safe list Medium (terminal.run_work), anything else High (terminal.run_any),
admin rights and Windows security, boot, users, disks, services or HKLM Critical (terminal.admin, no executor). winget
install and uninstall High; a silent or hidden install Critical (apps.install_hidden). The hands still never type into a
terminal window. Matches the App Master Plan's tiers for "Terminal & code" and "Apps install".

## ADR-045 — PC6 and PC7: plans about any PC order, the plan journal, `kairu doctor` (16 Nov 2026, proposed)

**Proposed (BAR.md "Do whatever I say"):** free-form orders may be about apps, windows, volume, brightness, git and tests
too; plans may hold terminal.run (the command keeps its own tier). A plan is still shown first and runs after "yes" (and the
PIN for its one High step); still at most 8 steps. data/plan-journal.json records a plan's steps and how many are done; a
cut-off plan is told once, "go on with the plan" runs the rest only as a new plan shown and decided again, "forget the plan"
empties it. `kairu doctor` (owner command, read only): Guardian's state, Kairu's memory per program, the PC's free memory.


## ADR-046 — Gemini hearing: each sentence heard by Google's Gemini, the offline Whisper as fallback (16 Nov 2026, proposed)

**Why (the owner, 16 Nov 2026):** the laptop's Whisper took 6 s a sentence and mixed in people talking nearby; "start building
... fast and accurate", then "GO Gemini hearing", accepting that spoken sentences go to Google.

**Proposed (VOICE.md "Gemini hearing"):** voice.hearing: local (default) or gemini, Guardian's setting. With gemini, each
utterance the gate ended goes once, in memory, to generativelanguage.googleapis.com with the sealed key from
`kairu provider add gemini` (High); the words are only words; no live looks; on any failure the offline Whisper hears and
Gemini rests a minute. Changes the voice rule "no sound leaves the PC" for this one setting. Google's free tier may use what
is sent to improve its products: said in VOICE.md. The brain uses Gemini only if gemini is in brain.providers.


## ADR-047 — The camera check: a sentence your lips didn't say is never yours (16 Nov 2026, proposed)

**Why (the owner, 16 Nov 2026):** "my cousins are talking ... Kairu gets confused"; "Kairu can use the camera ... it identifies
who is talking". **Proposed (VOICE.md "The camera check"):** voice.camera (default off); the camera only while the mic is on,
frames in memory only; per utterance "yours", "lips still", "no face" or "unchecked"; not yours is never an order, wake or
answer, "Kairu, stop" from anyone. Narrowed from "whenever it wants" to "only while the mic is on". New optional dependency:
opencv-python (pyproject extra camera). Limit, said to the owner: simultaneous talkers stay mixed.


## ADR-048 — Clones, the rest: skills and workload, notes that ride on orders, the manager's view (16 Nov 2026, proposed)

**Why (the owner, 16 Nov 2026):** "lets start building the main kairu+clone ... GOO AND FINISH ALL THIS STUFF": the four Clone
items of the tracker (a Clone on each laptop, the manager splits, the Clones talk and sync, the manager's progress view).

**Proposed (TEAM.md, builds on ADR-043):**
- `kairu team join NAME` on a Clone's laptop is `kairu device pair` with the exact `kairu team add` line for the manager; an
  owner command, never a Kairu action. Main Kairu's keys for each Clone are sealed with DPAPI (purpose "Kairu team keys v1");
  a plain file from before is read once and written back sealed.
- Skills per Clone (the manager's words, letters and a few marks only, 120 at most) and the minutes each Clone already has in
  unfinished projects go into team.split's instructions; the split shows the work per Clone against its share.
  team.set (Medium) changes a share or skills; team.move (Medium) gives a task that hasn't started to another Clone.
- Talk and sync: Main Kairu's own notes (a welcome on a Clone's first order, a hand-off when the tasks one waited for are
  done, a heads-up when its task slips) ride on that Clone's next order after a "NOTE " line. They are built only from Main
  Kairu's own data (the project name, the split's task titles, Clone names, times), never from a Clone's words. On the
  Clone, kairu/tasks/remote.py takes the note off before the task core sees the order and keeps it in data/team-inbox.json
  with team.note (Low, private): words to show, never an order. Notes never go as missions of their own, so they can't
  collide with task.order's one-at-a-time rule.
- `kairu team say "WORDS"` on a Clone is Guardian's link.send to the paired Main Kairu; on Main Kairu the words are kept in
  team.db's feed for the board only: never an order, never moving a task (even with a tag inside), never handed to Guardian,
  an AI or another Clone (the Clones rule unchanged).
- The manager's view: workload per Clone, time used against work done (the deadline bar), a silent Clone, the team feed,
  the slip watch (once per task); "how's the project going?" (team.status, Low, read only) answers from the board by rules,
  Tenmin's way. "split the project: ..." and "start the project" in the bar or by voice are team.split and team.run, at Main
  Kairu's own PC only (an order from a phone or from Main Kairu never splits or starts a project there).
- Unchanged: each Clone's own Guardian decides every step, High needs "yes" and that laptop's PIN, Main Kairu holds no
  approval. Still through Main Kairu as the hub; Clones don't message each other directly.


## ADR-049 — The growth record, the safe version (17 Nov 2026, proposed)

**Why (the owner, 17 Nov 2026):** "with good progress the employee gets high positions and more big projects ... OK GOO with
safe version". Under the EU AI Act, AI that decides promotions, allocates tasks on individual behaviour or evaluates
performance is high-risk (Annex III point 4); the safe version keeps a person deciding.

**Proposed (TEAM.md "Growth", kairu/team/growth.py):**
- A record per Clone, by rules from team.db, no AI: delivered, early / on time / after plan, let others start, finished
  after a block, checked by the manager (team.check, Medium), kinds of work from the task titles.
- Tasks, not people: every entry is about a task; nothing is a score; nothing ranks; Clones are listed by name.
- The employee sees everything recorded about them: entries and the manager's checks wait in clones.pending and ride on the
  Clone's next order (within the note's 600 letters; the rest waits), so they reach its inbox; `kairu team record` there.
- Suggestions only for the manager, with the evidence, for a kind of work with 3+ tasks delivered early or on time and none
  after plan. team.offer (Medium): the manager's own words, delivered with the next order; only that Clone's
  "[Kanswer] N yes|no" (link.send from that laptop) changes that offer, once. An answer never moves a task.
- Unchanged: no Guardian rule loosened; a Clone's words still never reach another Clone, an AI or Guardian.


## ADR-050 — The Builder: Builder powers, Forge and Five Paths (17 Nov 2026, proposed)

**Why (the owner, 17 Nov 2026):** "start building the builder" — the three parts of the Buildathon progress bar: Builder
powers (sites, apps, tests, slides), Forge (writes its own skills) and Five Paths (5 attempts, best wins), on Gemini
(Buildathon form, 15 Nov; "The problem and how Kairu solves it", 17 Nov).

**Proposed (BUILDER.md, kairu/build/):**
- Eight new policy actions, none Critical: build.draft, forge.draft, forge.test and paths.draft (Low: the brain writes drafts,
  or a recipe is tried on a stand-in laptop); build.write and forge.forget (Medium); build.test and forge.save (High: "yes"
  and the PIN). All are `private`: briefs, tasks and file names stay out of the audit log (hashes only).
- The brain only thinks: a draft is read strictly in kairu/build and kept in data/builder.db, on this PC only. Every step that
  changes anything is a Guardian action decided by its own tier. A draft is made, tried or kept only with the sha256 of
  exactly what you were shown.
- Builder powers: a website, a web app, slides (HTML, CSS, JS in one new folder of the work folder) or a small Python program
  with unittest tests. Nothing is ever overwritten; a page never reaches the network by itself (no remote script, style,
  picture or frame, no fetch, XMLHttpRequest, WebSocket, beacon or eval); Python uses only safe standard modules and its own
  files (no open, eval, exec, os, subprocess, socket). Running a build's tests is build.test, High, because it is code an AI
  wrote, and only while its files are unchanged. Open point for the owner: PC5's "run the tests in X" (terminal.run_work,
  Medium) is unchanged, so it still runs pytest in any work-folder folder at Medium.
- Forge: a recipe is only Kairu's known skills (the plannable ones, never terminal.run), with up to 3 slots and 5 examples.
  Guardian is asked about every step first (a refused or Critical step, or more than one High step, means no skill); five
  dry runs then run the real skills' code against a stand-in laptop (kairu/tasks/pc.py StandIn) with its own work and data
  folders, so this PC is never touched; only after 5 of 5 pass may forge.save keep it, with the PIN. A kept skill is a known
  order after the built-in skills, and runs as a plan: shown first, "yes" (and the PIN for its one High step), Guardian
  deciding each step, so a recipe can never raise a tier. A kept recipe changed by hand is never used. Sharing a skill with
  the Clones (each laptop approving with its own PIN) is not built yet.
- Five Paths: five plans (Fast, Careful, Simple, Creative, Thorough), each read as strictly as any plan; the rule checks drop a
  plan with a refused or Critical step or more than one High step; a judge scores the rest against "done when" (or rules, if
  the judge doesn't answer); you pick with "run path N", and only that plan runs, as a plan.
- Gemini: brain.build_providers (new, optional) is who the Builder asks; the shipped config.yaml puts Gemini first, then Groq
  and Gemma on OpenRouter. Public briefs only (the same privacy filter as brain.plan; a personal brief is not sent). Gemini's
  free tier may use what is sent to improve Google's products. A Builder answer may be long (16,000 tokens at most, less for
  Cloudflare and OpenRouter) and is never tidied, so code keeps its underscores.
- The Builder's orders work at Main Kairu's own PC only (source "pc").
- Unchanged: no Guardian rule loosened, no existing test removed or loosened; Critical stays blocked with no approval path.

## ADR-051 — Kairu's eyes: the screen agent sees, thinks, acts and sees again, with Gemini (18 Nov 2026, proposed)

**Why (the owner, 18 Nov 2026):** "I want an AI agent that sees the screen and takes control of it ... start building it."
Asked what the AI may see (a picture to Groq with Zero Data Retention, Groq then Gemini, or words only), the owner chose
Gemini: "it is better if we choose Gemini because of the hackathon" (the Google Cloud Buildathon, 20-21 Nov 2026).

**Proposed (BAR.md "Kairu's eyes", kairu/tasks/eyes.py, kairu/tasks/agent.py):**
- One new policy action, screen.look (Medium, private): a picture of ONE window on the safe list (PrintWindow, a PNG made in
  memory by kairu/hands.py png_of, never written to disk), its buttons' names and its title, with the goal and Kairu's own
  record of the steps so far, go to Gemini only (generativelanguage.googleapis.com, Gateway.see, the sealed key from
  `kairu provider add gemini`). This changes one earlier rule: the PC4 picture was "never sent"; now the picture of a window
  on the safe list may go to Gemini for a look. The OCR backup picture is unchanged (never sent).
- Never looked at, with no approval path: Kairu's own windows, security, password, terminal and money apps and pages, and
  any app not on the safe list (then the agent starts blind: the goal only, no picture). A name or title holding a secret or
  giving orders is left out; the backstop reads every word and fails closed.
- The goal passes the privacy filter like a Builder brief: a secret is refused, personal words are not sent. The run starts
  only after "yes" to a card that says a picture goes to Google Gemini; the goal is kept with task.plan (a hash) first.
- Gemini only proposes. kairu/tasks/agent.py reads each proposal strictly: click, type, press (screen.*, always in the app the
  look saw), launch (apps.open), visit (web.open), search (web.search) or wait (task.wait), each with exactly that skill's
  details as short text; done or stuck. Never files, commands, installs or the safe list. Every step goes to Guardian with
  GuardianClient.run like a typed order: High steps (send, submit, delete, personal words, an app not on the safe list) wait
  for "yes" and the PIN on the card, one by one; the hands' never-rules are unchanged.
- The run ends on a stop or Safe Mode, any refusal by Guardian or the hands, a refused card, 3 steps in a row that didn't work,
  the same step a third time, 15 steps or 10 minutes.
- tasks.eyes in config.yaml switches the eyes on (fails closed: off without the line; shipped on, the owner's GO). Gemini's
  free tier may keep what is sent and people at Google may read it: said on the card's wording in BAR.md and here.
- Orders at Main Kairu's own PC only (source "pc").
- Unchanged: no Guardian rule loosened, no existing test removed or loosened; Critical stays blocked with no approval path.

**Change asked by the owner (19 Nov 2026, proposed with this ADR):** "when kairu is controlling my laptop then it should know
what's on my screen, fix this one", after "what's on my screen" with WhatsApp in front was refused as off the safe list.
A look in mode "describe" ("what's on my screen") may now see any window screen._seen allows: it only tells the owner, and
nothing is clicked or typed. Kairu's own windows, security, password, terminal and money apps and pages are still never looked
at, with no approval path. Taking control (mode "next") still needs the safe list, and every step it proposes is still
decided by Guardian and the hands' rules. A window title is no longer put in quote marks in what is sent: with the word
"password" in Kairu's own instructions, the backstop took a one-word title such as "WhatsApp" for a quoted password.
The same day, after "what's on my wallpaper" got a guess: a describe look may also see the desktop wallpaper's picture
(app "@wallpaper": a small PNG Windows' own System.Drawing makes of the file Windows names, in memory, never written), only
to describe, never to take control; a plain colour is said by rules with nothing sent. Kairu Live is told never to guess
what is on the screen and to look first.
Then the owner: "Kairu can see the whole screen, whether the apps are open or closed, it will say exactly what's on the
screen." A describe look may see the whole screen (app "@screen"): every monitor by BitBlt, in memory; each window it may
never show (screen._check_window: Kairu's own, security, password, terminal, money; and any window whose program Windows
doesn't name) is painted black first, back to front, and an ordinary opaque window in front of one is put back, so only the
hidden window's own pixels go black. Only program names go with it, never a title. Only to describe; taking control still
looks at one window on the safe list. Kairu Live's look_at_screen now looks at the whole screen unless asked for the app in
front. Everything else on the screen (a chat, an email) goes to Gemini with the picture: said in BAR.md.

## ADR-052 — Kairu Live in the bar: LiveKit hears, thinks and speaks; the bar, the task core and Guardian act (18 Nov 2026, proposed)

**Why (the owner, 18 Nov 2026):** after choosing LiveKit for Kairu's voice and building "Kairu Live" (LiveKit Agents,
Deepgram Flux, Gemini, ElevenLabs) as its own folder, and the screen agent (ADR-051): "the screen control ai agent and
livekit voice part both are completed. now connect all this things to kairu bar. start building it."

**Proposed (VOICE.md "Kairu Live", kairu/live/):**
- One new policy action, live.talk (Medium, private, feature voice): Guardian starts kairu/live/listener.py when you switch
  the mic on in the bar (or the workspace) with voice.live: true in config.yaml. Like voice.listen, it says hello on the
  bar's voice link with the session token of the mic you switched on, and does nothing for any other; voice.listen_at_start
  never starts it (only your click or Ctrl+Alt+V); an emergency stop ends it with everything it started.
- The listener starts kairu/live/talk.py with the Python in voice.live_folder's .venv, giving it only the keys and settings it
  uses from that folder's .env (never Kairu's own switches), with no console window. talk.py imports nothing of Kairu
  (a test reads it): LiveKit Agents on this PC's mic and speaker, with WebRTC echo cancellation, no LiveKit room or server.
- This changes one earlier rule, for voice.live only: what you say goes to Deepgram (the words), Groq (the thinking:
  gpt-oss-120b, then gpt-oss-20b; the owner's GO of 19 Nov 2026, because Gemini's free 10 requests a minute kept running
  out), Google Gemini (only if Groq can't) and ElevenLabs (Kairu's voice, Deepgram Aura as backup). Kairu's eyes still use
  Gemini, in the bar, as ADR-051 says. Free tiers only, no card. Off unless you switch it on; voice.live is Guardian's
  setting, never a request's. Nothing is written to disk; Kairu Live's warnings stay in memory, only its last error line
  (cut short) reaches the bar and guardian.log.
- Kairu Live holds no authority. Every order it wants done goes back to the bar and to the same task core as a typed order,
  one at a time; Guardian decides each step, High still waits for "yes" and the PIN typed in the bar's card, Critical stays
  refused. A spoken yes or PIN is never an order. While the card is open, Kairu Live's mic sends silence, and its orders are
  answered "not done" until you answer the card.
- What Kairu Live's Gemini hears back is cut by kairu/live/relay.py: nothing for a finished task (it stays quiet; the pill
  says "Done"), Kairu's own refusal line, a web answer from a free cloud AI (L3) or the weather, and what Kairu's eyes
  said, each marked as data; anything else (memory lines, talk history, window titles, page or command text, lists) only
  "It's shown in the Kairu bar."
- "Kairu, stop" heard by Kairu Live is the emergency stop, done by the listener as voice.listen does it. The mic goes off
  after 10 minutes with no talk. Kairu Live does not start while voice.only_my_voice or voice.camera is on (it can't check
  either), and says so.
- The pill and the bar show Kairu Live like the offline voice: blue while you or Kairu talk, red while an order is in hand,
  "Done" after; your words in the bar's words line, Kairu's in its reply line.
- Unchanged: no Guardian rule loosened, no existing test removed or loosened; Critical stays blocked with no approval path.

## ADR-053 — Kairu Live remembers today's talk; "where am I?" from Windows' location (19 Nov 2026, proposed)

The owner, 19 Nov 2026: "it don't remember the previous works, like what's my location, then it should remember", "when I
say where am I, then it should locate my location, it is very useful". The owner chose "Keep today's talk" and "Windows
location" (city level).

**Proposed (VOICE.md "Today's talk", RESEARCH.md "Where am I?" and "The cheapest options"):**
- Today's talk: the bar (kairu/bar/voice.py TodayTalk) keeps Kairu Live's own turns of today, what you said and what it
  said, at most 30, in memory only: never on disk, in the audit log or in the memory or talk-history databases. Each new
  Kairu Live session gets them once, through the listener (read strictly: role user or assistant, plain words, 400
  letters), and talk.py puts them before its greeting. They are words that went to Kairu Live's own services when they
  were said; nothing else is added. A line with a secret (privacy.secrets_in) is never kept; brain.talk_history: false
  keeps none; "forget our talks", a new day or the bar closing ends it. This does not change the memory rule: no memory
  line and no talk-history line is ever sent.
- research.location (Medium, private, feature research): at Main Kairu's own PC only, asked by the brain for "where am I",
  "what's my location" and the like. It reads Windows' own location service (PowerShell's System.Device, no package),
  rounds the position to 2 decimals (about 1 km) and asks only nominatim.openstreetmap.org for that place's name. Only
  area, city and state are kept in research.db; the exact position, a road, a house number or a postcode never are. The
  answer is made by rules. Kairu Live hears that answer back (relay.py), marked as data, so the area and city go to Groq
  and ElevenLabs to be said: the owner's choice.
- Cheapest options: a question asking for something cheap searches for the thing's lowest price, and the web answer names
  the best two or three, cheapest first, with prices from the pages only. No new policy action.
- Unchanged: no Guardian rule loosened, no existing test removed or loosened; Critical stays blocked with no approval path.

## ADR-054 — The screen agent, finished; "register / apply / log in when I say"; yes without the PIN in a take-control run (20 Nov 2026, proposed)

**Why (the owner, 20 Nov 2026):** "there is no need of yes + PIN. Every time whenever I say anything to do, then it works on
the live screen so that I can see what is happening. When Kairu is login my details, then it asks me that it is correct or
not (confirmation ask). And when I say to scroll down then it should scroll." Asked four questions the same day, the owner
chose:
1. No PIN in the screen agent only (the rest of Kairu keeps it), and a spoken "yes" counts too.
2. Kairu fills the form where the owner can watch, then asks "Is this correct?" once, before Submit / Sign in.
3. For a password, Kairu may click the browser's own saved-password suggestion.
4. The owner's details are kept in a list on this PC.

Not asked yet, proposed here: a résumé upload is "Your turn" (Kairu never opens a file dialog).

**This changes a CLAUDE.md rule, so it waits for the owner's GO:** "High tier always needs yes plus the PIN" gets a
second exception, below. Nothing else in Guardian is loosened.

**Proposed: yes without the PIN, in a take-control run only.**
- A new kind of approval in policy.yaml, `pin: false`, allowed on one action only: `screen.agent_confirm` (High). Guardian's
  approve() still needs "yes", still decides again first (Safe Mode, a stop, Critical still refuse), still gives one approval
  for exactly those details, once, within the same minutes; it only skips the PIN check for that one action.
  tools/check_guardian.py fails if `pin: false` is on any other action, or on a Critical one.
- screen.agent_confirm is what a take-control run asks for in place of screen.confirm: Sign in, Sign up, Register, Submit,
  Apply, I agree, Send, Enter in a message box, a step in an app not on the safe list, and a click at a point (below). It is
  only ever asked for by kairu/tasks/agent.py, inside a run that started with your "yes". Typed and spoken orders outside a
  run still use screen.confirm (yes + PIN).
- The card says what will happen and where: "On internshala.com: click 'Submit'. Is this correct? Say or click yes / no."
- A spoken "yes": while a `pin: false` card is open, the bar takes a whole utterance that is only a yes ("yes", "yes it's
  correct", "yes go ahead") or a no, heard after Kairu finished asking and within 60 seconds, once per card. It goes to
  GuardianClient.approve as "yes" with no PIN. It is never an order and never reaches the task core. For every other card
  the old rule stays: a spoken yes or PIN goes nowhere, and Kairu Live's mic sends silence.
- Said plainly, the cost: anyone in the room, or a video playing, could say "yes" to a take-control card. The PIN was what
  stopped that. Kairu Live doesn't run with voice.only_my_voice on. The cards still show exactly what will happen, and the
  run is still stopped by "Kairu, stop" or Ctrl+Alt+K.

**Proposed: on the live screen, so you can see it.**
- Every take-control run works on the real, visible screen: the window it works in is brought to the front and restored
  (never minimised or hidden), and the bar moves to a small corner while the run goes on.
- The bar (and the Ember Glow pill) shows each step as it happens: "Step 3 of 15: clicking 'Search' (look 2.4 s)". Kairu
  Live says aloud only the start, a "Your turn", the "Is this correct?" question and the end (Tenmin: finished tasks stay
  quiet).

**Proposed: the gaps in the screen agent (ADR-051).**
- `scroll` (screen.scroll, Medium, private): up or down, 1 to 10 notches, by the mouse wheel over the app the look saw. Also
  a plain order outside a run: "scroll down", "scroll up 3 times", "scroll to the bottom" scrolls the app in front. It never
  scrolls Kairu's own, security, password, terminal or money windows (screen._seen, no approval path).
- Forms: `choose` (pick an item from a list or drop-down, by both names), `tick` (tick or untick a box by its name), each
  screen.choose / screen.tick, Medium in a safe app; ticking "I agree" or "I accept" is screen.agent_confirm.
- A button with no name (this changes the "click by name only" rule): Gemini may name a point (x, y in the picture). Kairu
  first asks UI Automation what is at that point, then the words in the picture around it. If there is a name or words,
  the click is decided by them, exactly as a click by name (Send, Submit, Pay ... keep their tiers and never-rules). If there
  is nothing to read there, the click is screen.agent_confirm, with a small picture of the spot on the card. A point is never
  clicked in Kairu's own windows, a password box, or a never-app.
- Hand-over instead of ending on "stuck": Gemini's `handover` (or stuck on a sign-in, a captcha, a code, a password) makes
  Kairu say what you must do ("Your turn: solve the captcha, then say go on"). Kairu then takes no picture and sends nothing,
  until you say or type "go on" or press the bar's Go on button; then it looks again and carries on, within the same 10
  minutes. "stop" ends it.
- Gemini's limits: on "too many requests" (HTTP 429) Kairu says "Gemini is busy, waiting 20 seconds", waits once (at most 30
  seconds, or what Gemini asks if less), and tries again; a second refusal ends the run with that message. Each step line
  shows how long its look took, and the answer gives the average.

**Proposed: register / apply / log in.**
- My details (kairu/tasks/details.py, data/my-details.json, BAR.md "My details"): name, email, phone, city, college, LinkedIn,
  résumé file name, a username per site. On this PC only, like the memory: no file there uses the network, never sent to
  Gemini or any AI, never in the audit log (hashes only). Kept or changed only by the owner command `kairu details set
  email you@example.com` (typed in PowerShell, never a Kairu action) or "remember my email is ..." in the bar as details.keep
  (High, yes + PIN, as today). A secret (password, PIN, OTP or code, card, Aadhaar or other ID number) is never kept: the
  privacy filter checks every value and refuses.
- Gemini sees labels, not values: it proposes `fill` with a label ("type {email} in 'Email address'"). kairu/tasks/agent.py
  puts in the real value locally (screen.fill, Medium, private, only in the browser, only on the run's site). Every later
  picture paints each box Kairu filled black first (the whole-screen blackout code, by the box's UI Automation rectangle);
  if a box's rectangle can't be found, the next look is blind (no picture, labels only). Fails closed.
- The start card says which details may be typed and where: "On internshala.com Kairu may type your name, email and phone.
  A picture of the browser goes to Google Gemini, with those boxes painted black." Your "yes" starts the run.
- "Is this correct?": after the boxes are filled you see them on the screen, and the card lists each box and what went in.
  Submit / Sign in / Apply is clicked only after your yes (typed, clicked or spoken). A no stops before Submit.
- Right site only: the run locks to the site you named, or the one open in front, at the first look (its registrable name,
  internshala.com). If the address moves to another site (a look-alike, or a "sign in with Google" page), Kairu stops and
  tells you the address; it does not go on there.
- Logging in: Kairu opens the site, clicks "Sign in", fills your username or email from My details, then, when the password
  box has the focus, takes no picture. It may click the browser's own saved-password suggestion: only the entry whose name
  is your username for that site, found by UI Automation in the browser's suggestion list, never by reading the password
  box (its value is never read). Then the "Is this correct? Sign in to github.com as you@example.com" card, then Sign in.
  If there is no saved entry with that name, "Your turn: type your password, then say go on". A code (OTP, verification) is
  always "Your turn". The run uses Kairu's own browser profile (data/browser-profile), so a saved password is one you let
  that browser save, once.
- Résumé upload: "Your turn: choose your résumé in the file window, then say go on." No file dialog is ever driven by Kairu.

**Unchanged, with no approval path (CLAUDE.md):** Kairu never types a secret, never solves a captcha, never pays, never
touches bank, payment, security or password-manager apps or pages, never presses Win or Ctrl+Alt keys, never touches its own
windows. Personal words go to Gemini only after yes + PIN (the brain's rule; a take-control run never sends them, it sends
labels). No existing test is removed or loosened; Critical stays blocked.

**New policy actions:** screen.agent_confirm (High, `pin: false`, private), screen.scroll, screen.choose, screen.tick,
screen.point, screen.fill, screen.saved_password (Medium, private), details.keep (High, private), details.forget (Medium,
private), details.show (Low, read only, private).

**As built (20 Nov 2026, after the owner's GO; branch screen-agent-signin):**
- policy.load itself refuses `pin: false` on any action but screen.agent_confirm, or on one that isn't High; Guardian skips
  the PIN only when the rule says so and the action is in policy.NO_PIN_ACTIONS; a phone's request for it is refused.
  The task core asks screen.agent_confirm only while a take-control run lasts (TaskCore.in_control), else screen.confirm.
- A spoken answer reaches a card only through Kairu Live's words (its "heard" or "order" lines): the light voice's offline
  listeners still drop every yes and PIN, so there a yes is typed or clicked, and "Kairu, go on" works. Kairu Live's mic is
  live only while such a card is open; every other card still sends silence.
- The bar steps aside (hidden) while a run goes on, so it never covers a button Kairu clicks, and comes back for each card
  and with the answer; the pill shows "Step N" only (never the step's words), the bar's line the whole step.
- "Too many requests": the wait is what Gemini asked (brain.db's limit), at most 60 seconds (not 30), then one more try.
- "stuck" about a sign-in, captcha, code, password or upload is a hand-over too; anything else still ends the run.
- One existing test changed with the rule: test_screen_agent.py's "a step that may send still needs your PIN" now expects
  screen.agent_confirm (still High, still a card, a refused card still ends the run and nothing is clicked), renamed "still
  asks you first". No other test was changed.
- Not yet run on Windows: every new UI Automation mode (choose, tick, at, rects, fillbox, loginbox, address, saved) and the
  wheel. The laptop test (BAR.md) is their first run.

## ADR-055 — Meeting in: a meeting becomes decisions, owners, deadlines and open questions, with Gemini (21 Nov 2026, proposed)

**Why (the owner, 21 Nov 2026):** the hackathon brief is an AI employee that turns meetings into finished work; the judges
want cross-meeting memory and conflict detection, not a summariser (HACKATHON.md). Stage 1, "Meeting in", is the start of
that pipeline. The owner's GO the same day: "go and build meeting in complete ... quick and good quality".

**Decided in the build (proposed, for the owner to accept):**
- `meeting.read` (High, private): one meeting file in the work folder (or its `meetings` folder) - a recording (mp3, wav,
  m4a, aac, ogg, flac, mp4, webm, mov) or a transcript (Teams/Zoom/Meet .vtt, .srt, .txt, .md). The approval names the file
  and its sha256, and the action reads only a file with exactly that hash. A recording goes to Gemini to be written down
  (inline up to 14 MB; larger through Gemini's Files API at generativelanguage.googleapis.com only, deleted from Google as
  soon as the transcript is back); then the transcript goes to Gemini once more, which pulls out the decisions, actions
  (owner, deadline as a real date) and open questions as JSON.
- Why High and not the brain's privacy filter: a meeting is personal by nature (names, who does what), so it would never pass
  the filter as "public". CLAUDE.md already allows personal data to a cloud AI "only after yes and the PIN, for that exact
  text and that one provider": the card is that approval, for that file's hash and Gemini alone.
- A secret is never kept or sent: each transcript line with one (privacy.secrets_in) is replaced by a marker before
  anything is stored or sent, and Gemini's backstop still reads every word that leaves. The sound of a recording can't be
  scanned before it is written down; that is said on the card.
- Gemini's answer is read strictly (kairu/meeting/read.py): JSON only, short texts, at most 40 items of each kind, a deadline
  only as a real date within two years of the meeting (else ""), an owner never guessed (""), and every quote checked
  against the transcript: one that isn't there is marked "not found" and never shown as evidence. Nothing in it runs.
- What comes out is kept in data/meetings.db on this PC only (meetings, items with status open/done/replaced/dropped for
  stage 2), never in the audit log (hashes only), never sent anywhere else.
- `meeting.record` (High, private): the mic, in memory only, until "end the meeting" (`meeting.stop`, Low) or 60 minutes
  (120 at most); then the same as meeting.read on that recording. **This adds a way to switch the mic on** beside the bar's
  click and Ctrl+Alt+V: your own order plus "yes" and your PIN. No sound is ever written to disk; an emergency stop ends
  it at once and what it heard is gone. The workspace shows "Recording 2:13" and a level bar (numbers only).
- `meeting.show` (Low, read only) and `meeting.forget` (Medium). Orders: "read the meeting NAME", "record the meeting",
  "end the meeting", "show the last meeting" - at Main Kairu's own PC only, like the team orders.
- The workspace gets a Meetings page (read only, like Clones): each meeting's decisions, "who does what", actions and open
  questions with owner and deadline chips, "no owner" / "no deadline" warnings, and each item's quote, which jumps to its
  line in the transcript.

**Next (stage 2, not built):** the decision ledger across meetings and the conflict check (decision vs earlier decision,
deadline vs workload, owner vs owner, deadline vs dependency) read data/meetings.db; stage 3 turns confirmed actions into a
brief for team.split.
