# Kairu's brain (Phase B)

You ask a question on this PC or on your phone; Kairu picks the right brain level, keeps your private data
on this PC unless you approve, and gives back a short answer. Long jobs become **Mission Cards** with a
checkpoint after every step, so a restart, a crash or a stop never makes Kairu start over or do a step twice.

Built per *Staged Implementation Plan v1.6* (Phase B) and ADR-026 (the owner's decisions of 29 Oct 2026: B
before the phone app; option A for public questions). Parts: **B1** the Model Gateway, **B2** asking from the
PC and the phone, **B3** Mission Cards. Guardian still decides every action: the brain only thinks and answers.

## Set it up (about 10 minutes)

### 1. Update and restart Guardian

In PowerShell, in the project folder:

```
py -3.12 tools\check_guardian.py
$env:Path = "$PWD\.venv-guardian\Scripts;" + $env:Path
kairu guardian quit
kairu guardian run
kairu status
```

`kairu status` now has a `brain:` line. `config.yaml` has a `brain:` section with `public_to_cloud: true`
(option A) and the providers in the order Kairu tries them.

### 2. Groq (first choice; no card)

1. Make a free account at <https://console.groq.com> and create an API key (**API Keys → Create API Key**).
   Optional: in the console's **Data Controls**, turn on **Zero Data Retention**, so Groq keeps no logs at all.
2. On the PC: `kairu provider add groq`, type `yes` and your PIN, then paste the key (it is not shown).

### 3. Cloudflare (second; replaces Cerebras, which is no longer free)

1. Make a free account at <https://dash.cloudflare.com>. Cloudflare did not ask for a card for the free
   Workers plan when this was checked; if it asks you for one, stop: Kairu works with Groq alone.
2. In the dashboard, open **AI → Workers AI → Use REST API**: it shows your **Account ID** and a button to
   create a **Workers AI API token**.
3. On the PC: `kairu provider add cloudflare`, paste the Account ID, type `yes` and your PIN, then paste the token.

### 4. OpenRouter (spare; optional)

A free account at <https://openrouter.ai> and a key (**Keys**), then `kairu provider add openrouter`. Its free
models allow 50 questions a day.

### 5. Check

`kairu usage` lists each provider as **ready**. `kairu ask "what is 2+2"` gets an answer.

## Use it

| Command | What it does |
| --- | --- |
| `kairu ask QUESTION` | a short answer, with a small line saying where it came from: `(L0: answered on this PC, nothing sent)` or `(L3: Groq, 0.8 s)` |
| `kairu ask --dry-run QUESTION` | where it would go and what the privacy filter finds; nothing is sent |
| `kairu usage` | per provider: questions today, how much of its free limit is used, and every switch |
| `kairu provider add NAME` | save a provider's key, sealed (High: `yes` and your PIN): `groq`, `cloudflare`, `openrouter` |
| `kairu provider list` | the providers, which are set up, their model, free limit and where they say they do not train on prompts |
| `kairu provider remove NAME` | delete a provider's key from this PC |
| `kairu provider pause NAME [--minutes 10]` / `resume NAME` | leave a provider alone, as if at its free limit (the gate test's simulated limit) |
| `kairu mission new FILE` | a Mission Card from a card file (`kairu mission example card.yaml` writes one to change) |
| `kairu mission new --practice` | the gate test's practice card: it counts five times 20 seconds, then answers one question |
| `kairu mission list` / `show N` | the missions; one in full, with each step and its answer |
| `kairu mission stop N` | stop one; it keeps its last checkpoint |
| `kairu mission continue N` | go on from the last checkpoint; first, the steps that wait for your approval are shown together |
| `kairu mission remove N` | delete a mission that is not running |
| `py -3.12 tools\brain_gate.py` | the gate test's 20 questions: where each goes (nothing is sent) |

On the stand-in phone (Termux): `python testclient.py ask "who is the prime minister of India"`. Copy the new
`kairu\link\testclient.py` to the phone first: the old one does not know `ask`.

## How a question flows

```
question ─► Guardian decides brain.ask (Low; Safe Mode refuses it)
              │
              ▼
         the router (rules only) ──► L0: a fixed rule answers here (time, date, status, usage, help, ...)
              │                 ──► "do something" (pay, delete, send, turn off ...): Guardian decides that
              │                     action by its tier; nothing ever runs from a question
              │                 ──► L4: team mode, "comes with Phase G"
              ▼
         L3: the privacy filter ──► secret:   never sent, not even with your approval
                                ──► personal: waits for "yes" + PIN, on a screen with the exact text and where it goes
                                ──► public:   option A: straight to the first ready provider
              ▼
         the backstop scanner reads the exact text that leaves ──► Groq ─(at its limit)─► Cloudflare ─► OpenRouter
```

Guardian's audit log keeps a hash of each question, never its words (`private: true` in `policy.yaml`).

## The five brain levels on this PC in Phase B

| Level | What it is | In Phase B |
| --- | --- | --- |
| L0 | Fixed rules, no AI: the time, the date, Kairu's status, usage, missions, greetings, help, the last answer's sources | **On.** It only reads and tells (your 20 Oct rule). A request to *do* something is handed to Guardian as that action, by its policy name (`money.spend`, `files.delete`, ...), and Guardian decides by its tier |
| L1 | A tiny AI model on the device | **Off on the PC** (RAM); comes on the phone in Phase D |
| L2 | A medium local AI model on the PC | **Off** until the RAM upgrade (Phase K) |
| L3 | Free cloud AI | **On.** The main brain in Phase B |
| L4 | Team mode: several agents | "Comes with Phase G": Kairu says so instead of guessing. Deep research on request ("research deeply ...") is built as an L3 question (RESEARCH.md "Deep research") |

## Free AI providers (checked 29 Oct 2026, on each provider's own pages)

| Provider | Free limit | Card? | Trains on your prompts? | Plan |
| --- | --- | --- | --- | --- |
| **Groq** (`openai/gpt-oss-120b`) | 30 a minute, 1,000 a day | No | **No**: its [Services Agreement](https://console.groq.com/docs/legal/services-agreement), section 4.2, does not let Groq use inputs or outputs for training. It may keep logs up to 30 days for reliability and abuse checks, unless you turn on Zero Data Retention ([Your Data](https://console.groq.com/docs/your-data)) | **First choice** |
| **Cloudflare Workers AI** (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`) | 10,000 neurons a day (a few hundred short answers), new at 00:00 UTC (5:30 am in India) ([pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)) | Not asked when checked | **No**: "does not use Customer Content processed by Workers AI to train AI models" ([privacy](https://developers.cloudflare.com/workers-ai/platform/privacy/)) | **Second** (replaces Cerebras) |
| **OpenRouter** free models (`google/gemma-4-31b-it:free`) | 20 a minute, 50 a day | No | OpenRouter itself does not; each request says `data_collection: deny`, so it may only go to providers that do not collect data ([provider routing](https://openrouter.ai/docs/features/provider-routing)) | Spare |
| Cerebras | **No free tier any more**: since July 2026 a $5, 30-day trial that needs a verified payment method ([its rate-limits page](https://inference-docs.cerebras.ai/support/rate-limits)) | Yes | — | **Not used** (ADR-017: no card) |
| GitHub Models | **Retired** on 30 July 2026 ([GitHub docs](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models)) | — | — | Not used |
| Google AI Studio, Mistral free tier | as in the plan | No | Yes, on free prompts | Not used |

Rules: **free only** (no paid API, no paid Claude API, no card, ADR-017); **no tricks** (no extra accounts, no
key rotation, one try per provider per question; at a limit Kairu switches, waits a few seconds if one is free
that soon, or tells you when to ask again); **your keys stay sealed** (DPAPI, like the Gmail key; each key goes
only to its own provider's address, which is fixed in Kairu, never taken from a question or a message).

If a provider retires its model, set another in `config.yaml` (`brain: models: groq: ...`) and restart Guardian.

The Builder (BUILDER.md, ADR-050 proposed) has its own order, `brain.build_providers`: the shipped config.yaml puts Google
Gemini first (the key from `kairu provider add gemini`, as for Gemini hearing), then Groq, then Gemma on OpenRouter. Only
public briefs go, through the same privacy filter as plans, because Gemini's free tier may use what is sent to improve
Google's products. Leave `build_providers` out and the Builder asks `brain.providers` instead.

## The privacy filter

Before anything goes to the cloud, the filter reads it (`kairu/brain/privacy.py`, rules only):

1. **Secrets** → **never sent**, even with your approval: passwords, PINs and one-time codes with their value,
   API keys and tokens, private keys, ID numbers (Aadhaar with its check digit, PAN, passport, voter ID,
   driving licence), bank details (card numbers with their check digit, account numbers, UPI IDs, IBANs).
2. **Personal data** → waits for your approval on a screen that shows the exact text and the provider it would
   go to: phone numbers, email addresses, where you live, a person's name in what you do with them ("tell
   Ravi ...", "my friend Priya"), your health or money, a message you pasted, a bank branch code.
3. **No personal data** ("who is the prime minister of India") → sent straight to a no-training provider
   (option A, chosen 29 Oct). `brain.public_to_cloud: false` in `config.yaml` makes every cloud send wait for
   you (option B).

**It fails closed.** What it cannot read well enough counts as personal: words in a script it cannot read yet
(Hindi, Telugu), a long pasted text, many lines, a long number, a long code. **The backstop.** The connector
scans the exact text about to leave once more and sends nothing if it finds a secret, whatever let it through.
A reason is always a label ("a phone number"), never the text it found.

A follow-up ("yes, tell me more") takes the last public question and answer along (kept 10 minutes, for each
place you ask from); the filter reads all of it. A personal exchange is never kept for follow-ups.

Answers say when they may be out of date: without a search the AI answers from what it already knows. Live web
research came with stage R1: RESEARCH.md.

## Asking from your phone

`python testclient.py ask "QUESTION"` sends a new Kairu Link message type, **ask**: signed and encrypted like
every Link message, and "live" (a question that waited more than 5 minutes is refused, and the phone is told to
ask again). Guardian runs it as `brain.ask`, exactly like a question typed at the PC, and the answer comes back
as Guardian's own `link.send`.

A question with personal data is **not** sent: the phone is told so, and it waits up to 10 minutes as a High
request at the PC. `kairu link waiting` shows the exact text and the provider; `kairu link approve N` (`yes` and
your PIN) sends it, and the answer goes to the phone (`python testclient.py listen` shows it, since `ask` stops
at the first reply). A "yes" or PIN typed on the phone is only text.

## Mission Cards

A card is a long job saved on disk (`data\missions.db`). `kairu mission example card.yaml` writes this one, to
change in Notepad:

```yaml
goal: Learn about two rivers
done:                       # what "100% done" means to you
  - every question answered
steps:                      # ask: a question for Kairu's brain; wait: count seconds (practice)
  - ask: How long is the Godavari river?
  - wait: 20
  - ask: How long is the Krishna river?
deadline: 2026-11-30 18:00  # optional
report: both                # pc (the tray and `kairu mission show`), phone, or both
```

- **A checkpoint after every step.** Each step's start and end are written to disk before anything else
  happens. A step that finished is never run again; a step cut off half-way runs again from its start (safe,
  because Phase B steps only ask and count), at most 3 times (ADR-006: bounded retries).
- **Each step goes through Guardian**: an ask step is `brain.ask`, a wait step is `demo.count`, both Low.
  Missions run only these in Phase B; reading files, writing, sending and anything High come with later phases.
- **Guardian keeps missions going** (`mission.run`): when a card is queued, when Guardian starts (after a
  restart or a crash, the cut-off mission goes on by itself; after an unclean end, once you `kairu resume`).
- **Stop.** Ctrl+Alt+K, the tray or `kairu stop` end a mission and its step in under a second; the card keeps
  its checkpoint and says "stopped"; `kairu mission continue N` goes on. `kairu mission stop N` stops one.
- **Personal data in a step** is not sent: that step waits, the mission goes on with the others, and at the end
  the card says how many wait. `kairu mission continue N` shows them **together**, then asks `yes` and your PIN
  for each (Guardian approves one action at a time); a refused one is skipped.
- **The report**: when a card ends, you are told in the tray and/or on your phone, with each answer, Kairu's own
  checks (every step through, report sent) and your checklist, which you tick yourself (Kairu cannot check it in
  Phase B).

The trip story (missions by voice, Kairu calls you back) is built on these cards in Phase I.

## The gate test (you, about 20 minutes)

Phase B passes when all of these hold.

1. **20 questions go to the right level.** `py -3.12 tools\brain_gate.py` (nothing is sent): it ends with
   `PASSED 20 of 20`. Then ask three for real: `kairu ask "status"`, `kairu ask "what time is it"` (both `L0`) and
   `kairu ask "who is the prime minister of India"` (`L3: Groq`).
2. **Private test data does not reach the cloud until you approve it.** `kairu usage` (note Groq's count). Then
   `kairu ask "my friend Ravi's number is 9876543210, what should I tell him"`: it shows the text and `Groq (api.groq.com)`; type `no`.
   `kairu usage`: the count has not moved. Ask again and type `yes` and your PIN: you get an answer and the count
   goes up by one.
3. **A secret is never sent, even if you approve.** `kairu ask "my password is Tiger@123, is it strong?"`:
   `Not sent ... not even with your approval`, and you are not even asked.
4. **The switch at a free limit.** `kairu provider pause groq --minutes 10`, then `kairu ask "what is
   photosynthesis"`: `(L3: Cloudflare ...; Groq paused by you -> switched to Cloudflare)`. `kairu usage` shows the
   switch. Then `kairu provider resume groq`.
5. **The phone, on mobile data.** `python testclient.py ask "who is the prime minister of India"`: a short answer
   within seconds.
6. **A mission cut off by a forced restart goes on from its last checkpoint.** `kairu mission new --practice`.
   Run `kairu mission show 1` until step 2 or 3 says `running`. Then restart the PC by force: hold the power
   button about 10 seconds until it switches off, and switch it on again. Sign in, wait a minute, then
   `kairu status` (Safe Mode, because Guardian could not end cleanly) and `kairu resume`. Within a few seconds
   `kairu mission show 1` shows the mission going on; at the end, every step `done` and only the cut-off step
   `tried 2 times`. (A normal **Restart** from the Start menu also works: then Guardian ends cleanly and the
   mission goes on by itself after you sign in, with no `kairu resume`.)
7. **Ctrl+Alt+K still stops everything in under 1 second.** `kairu mission new --practice`, wait until a step
   is `running`, press Ctrl+Alt+K. `kairu audit show -n 10`: the `halted` rows show `seconds_since_stop` under
   1. `kairu mission show 2` says `stopped`. Then `kairu resume` and `kairu mission continue 2`.
8. **The audit log keeps hashes, never your questions.** `kairu audit show -n 80`: no question appears; the
   `brain.send_private` rows show `details_sha256`. `kairu audit verify` says intact.

Please send me the output of `tools\brain_gate.py`, `kairu usage`, `kairu mission show 1`, `kairu audit show -n 80`,
and how many seconds the phone's answer took.

## Gate test result (3 Nov 2026)

**Passed.** Run by the owner on 2 and 3 Nov 2026 on their own PC (Dell, i5-1135G7, Windows 11, Modern Standby),
with the Guardian installed in `C:\Users\saitej\Kairu-guardian` on this branch, and a Mivi phone with Termux as the
stand-in phone, through the real ntfy.sh, Groq and Cloudflare. Times are the PC's (IST). `tools\check_guardian.py` on that PC at `6d17970`, the last code change: 595 passed,
0 failed, 5 skipped, real Ctrl+Alt+K passed.

**The phone's answer took 4 seconds:** ntfy.sh logged the phone's question at 15:42:34 and the PC's answer at
15:42:38 on 2 Nov, with the phone on mobile data.

| Step | Result | Evidence |
| --- | --- | --- |
| 1 Questions go to the right level | Pass | `brain_gate.py`: `PASSED 20 of 20`. `status` and `what time is it`: L0. The prime minister: L3 Groq, 1.0 s, with one follow-up offer and the dated note |
| 2 Private data waits for approval | Pass | `no`: "Not sent", Groq's count stayed at 4. `yes` and the PIN: answered, count 3 to 4 (done in the opposite order). Audit rows show `details_sha256` |
| 3 A secret is never sent | Pass | "Not sent ... not even with your approval"; not asked; count stayed at 4; the password is not in the audit log |
| 4 The switch at a free limit | Pass | Groq paused: Cloudflare answered in 1.1 s, `Groq paused by you -> switched to Cloudflare`; `kairu usage` showed the switch at 3:38 pm; Groq resumed and answered in 0.9 s |
| 5 The phone, on mobile data | Pass | **4 s** on ntfy.sh (15:42:34 to 15:42:38), with a short answer |
| 6 A mission cut off by a restart | Pass | Both ways, below |
| 7 Ctrl+Alt+K under 1 second | Pass | 3 Nov 15:41:43: all four running actions, the mission's step among them, `halted` at **0.029 to 0.030 s**. Mission 7 said `stopped`; after `kairu resume` and `kairu mission continue 7` it ended 6 of 6, only the cut-off step `tried 2 times` |
| 8 Hashes, not questions | Pass | No question or answer anywhere in the whole log (searched all rows, not only the last 80, including the phone's). `brain.send_private` rows show `details_sha256`. `kairu audit verify`: 682 rows, intact, anchor agrees |

**Step 6, both restarts.**
- A normal Restart (mission 5, 2 Nov): step 5 was cut at 15:50:48, the PC booted at 15:51:22 and Guardian was back at
  15:51:44 in normal mode. The mission went on by itself and ended 6 of 6, with only that step `tried 2 times`.
- A forced power-off (mission 6, 2 Nov): step 3 was cut after 16:00:31. At 16:01:19 Guardian found the unclean exit
  and went to Safe Mode, and a later normal restart kept it there. After the owner's `kairu resume` on 3 Nov the
  mission ended 6 of 6, with only step 3 `tried 2 times` and steps 1 and 2 not run again.

**Memory on this PC:** Guardian 33 MiB with the brain and Mission Cards (96 for a moment during a PIN check),
`protect.watch` 34 MiB, `link.receive` 29 to 32 MiB, one question's own process 27 MiB (with the stand-in provider,
only while it runs).

**Providers used:** Groq first (Zero Data Retention on) and Cloudflare second. OpenRouter is optional and was not set
up, so it was not tested.

**Notes.**
- In step 5 the PC was on the Wi-Fi network "Sung" and the phone's status bar showed a round icon that may be its
  hotspot, so the PC may have been on the phone's hotspot. The phone itself was on mobile data, and both sides went
  through ntfy.sh. This was not a test with the PC and the phone on separate networks.
- Step 2 used the earlier sentence "call my friend Ravi on 9876543210", and Groq answered it with a refusal. Requests
  to make a call are now answered at L0 ("I can't make calls yet; that comes with the phone app."), and nothing is
  sent. The gate's sentence is now the one in step 2 above, with the same name and number, and the filter still says
  personal; the tests check this, but that sentence was not run through the real provider.
- The two small fixes on the real Guardian, after the check: `kairu ask "call Ravi"` gave that answer at L0 with
  nothing sent, and a real Groq answer had one space before its follow-up offer.
- Step 7's log shows a second Ctrl+Alt+K 11 seconds after the first, which did nothing because all had stopped.
- Testing found one real gap, now fixed: a stop could wait behind the work done after another action ended. That
  work now runs on its own thread: a stop during 0.8 s of it takes 0.03 to 0.04 s, 10 of 10. A stop still waits for
  an action that is starting at that very moment (0.766 s once in a check run, under the limit; 0.015 to 0.032 s alone).

## How the safety rules are kept

- **Two brains stay separate (ADR-011).** The brain (`kairu/brain/`) only thinks and answers: its only requests
  to Guardian are `status` and `check` (a decision it reports and never carries out). The missions
  (`kairu/missions/`) only ask Guardian to `run`, follow (`run_status`) and `end` their steps. Neither can
  approve anything; tests check both by reading their code.
- **Tiers unchanged (ADR-004, ADR-023).** Asking is Low; adding a key and sending personal data are High ("yes"
  and the PIN at the PC); Critical stays refused. An answer can never run anything, and a request to do something
  that arrives as a question is decided by Guardian as that action.
- **Cloud data boundary (ADR-005).** Secrets never leave; personal data only with your approval, for that exact
  text and that provider only (an approved question is never switched to another provider); the filter fails
  closed; the backstop scans what leaves.
- **Free to run (ADR-017).** Free tiers only; no card; no cap unless you set one (`brain.daily_cap`, ADR-006).
- **Hashes, not words.** `brain.ask`, `brain.send_private`, `mission.create` and `link.send` are `private: true`
  in `policy.yaml`: the audit log keeps their details' hash. Answers wait in `data\brain.db` only until they are
  read (at most 10 minutes); your keys never pass through Guardian's channel, an action's details or a log.
- **Stop.** Every question and every mission step runs inside Guardian's Job Object: Ctrl+Alt+K, the tray and
  `kairu stop` end them in under a second. In Safe Mode Kairu answers nothing, because answering can send words
  to the cloud.
- **Low RAM.** No AI model runs on the PC. The Guardian program does not load the brain's network code.

## Measured while building (29 Oct 2026, the 4-CPU Linux build machine, Python 3.12)

| Measure | Result |
| --- | --- |
| `tools/check_guardian.py` | 554 passed, 0 failed, 21 skipped (Windows-only tests); 336 before Phase B |
| Guardian program memory with the brain and Mission Cards | 28 MiB at rest (92 MiB for a moment during a PIN check, as before) |
| One question's own process (`brain.ask`, with HTTPS loaded) | 23 MiB, only while it runs |
| Routing a question (router and privacy filter) | 0.08 ms |
| The phone's question to its answer (stand-in relay and provider on this PC) | 0.39 to 0.41 s |
| A stop with a question on its way | halted in 0.04 to 0.06 s |
| A stop with a mission and its step running | halted in 0.01 to 0.11 s |

Times through the real Groq, Cloudflare and ntfy.sh come from your gate test.

## Not built yet, and known limits

- **Answers can be out of date** when they do not come from a search (RESEARCH.md); Kairu says so when it matters.
- **Free limits change.** Providers can change them at any time; `kairu usage` shows what they report, and Kairu
  switches or waits. Cloudflare's share is an estimate from the answers' length. Cerebras and GitHub Models show
  how fast this happens.
- **The privacy filter reads English best.** Hindi and Telugu questions wait for your approval for now. It
  catches names only in what you do with someone ("tell Ravi", "my friend Priya"), not every name; it can miss
  personal data written in unusual ways. The backstop catches secrets, not personal data. When unsure, use
  `kairu ask --dry-run`, or set `brain.public_to_cloud: false`.
- **Needs the internet** for L3. With no internet, only L0 works.
- **No local AI yet.** L1 and L2 wait for the phone (Phase D) and the RAM upgrade (Phase K).
- **Missions only ask and count** in Phase B. Reading files (the plan's example "summarise the 3 newest files in
  my Downloads") needs a folder you approve for reading, which is not in the Phase B plan: it belongs to Phase I (Plan v1.6, open
  decisions). Missions are made at the PC; from the phone they come with Phase I. Each approved step needs its own PIN.
- **Stopping from the phone** is not built: the Stop button on the phone comes with the phone app, Phase D (Plan v1.6,
  open decisions). Until then a stop is at the PC: Ctrl+Alt+K, the tray or `kairu stop`.
- **The phone's `ask`** shows the first reply; for a personal question the answer comes after your approval at the
  PC (`python testclient.py listen`).
- **On Linux only**, a Guardian killed outright (`kill -9`) leaves its actions running (GUARDIAN.md); a mission's
  orphaned program then finds the new Guardian in Safe Mode and stops its card. Windows' Job Objects do not have
  this gap.
- **D26** (audit retention after memory deletion) is still open; the interim rule holds: hashes only, never content.

## Files

```
kairu/brain/
  router.py      which level answers: L0 rules, a request to do something, L4, or L3 (rules only)
  privacy.py     the privacy filter (secret, personal, public; fails closed) and the backstop scanner
  gateway.py     the Model Gateway: L0 answers, the providers in order, switching, approvals, the dated note
  providers.py   Groq, Cloudflare, OpenRouter: fixed addresses and models, one HTTPS connector, the backstop
  rules.py       L0's answers
  usage.py       what `kairu usage` shows
  store.py       data/brain.db: answers until read, the last public exchange, sources, usage, limits, switches
  keys.py        the providers' keys, sealed (data/brain-keys/)
  ask.py         brain.ask and brain.send_private, as Guardian actions
  actions.py     provider.add (High), provider.remove, provider.pause
kairu/missions/
  card.py        the card file: checked, and the practice card
  store.py       data/missions.db: the cards and a checkpoint at each step's start and end
  run.py         mission.run: works through the cards, each step through Guardian
  actions.py     mission.create, mission.stop, mission.continue, mission.remove
tools/brain_gate.py            the gate test's 20 questions: where each goes, nothing sent
tests_kairu/brain_gate.py      those 20 questions
```
