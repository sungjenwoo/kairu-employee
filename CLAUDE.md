# Kairu

Kairu's Guardian safety core: policy tiers, approvals with a PIN, emergency stop, Safe Mode and a
hash-chained audit log with an anchor. How it works and how to run it: GUARDIAN.md.
Guardian protection (Phase J: monitors that watch and alert, never act): PROTECTION.md.
Kairu Gate & Link and Mission Mode (Phase C: the phone's messages are requests only): LINK.md.
The Tenmin "Ask Anything" use case, run on the laptop in one page (research, deep research, memory, hands, asking AI websites): TENMIN.md.
Kairu's brain and Mission Cards (Phase B: the Model Gateway, free cloud AI, the privacy filter): BRAIN.md.
Live web research (stage R1: search and page reads as Guardian actions, page text as quoted data; R2: deep research on request): RESEARCH.md.
Kairu's memory (stage M1: lines you told Kairu to remember, on this PC only, answered by rules with no AI): MEMORY.md.
The Kairu bar and task core (Sprint Days 1 and 4: typed orders, PC, file and web skills, free-form plans, each step decided by Guardian): BAR.md.
Asking an AI website and reading a page (on Kairu's hands: only four sites, only Kairu's own browser profile): ASK.md.
Kairu's light voice (Sprint Day 2: the small offline model, "Kairu" and Ctrl+Alt+V, spoken orders through the task core): VOICE.md.
The Kairu App workspace (W1: projects and missions in one window, orders through the task core, Guardian's card; W2: files panel and file skills, voice, Ember Glow): WORKSPACE.md.
The Kairu phone app (Phase D: Kotlin in phone/, built on GitHub, installed with `kairu phone install`): PHONE.md.
Shadows (Phase H, Shadow v0: a temporary helper on a friend's laptop that comes home with a use case, a skill pack): SHADOW.md.
Clones (Main Kairu splits a project across Kairus on teammates' laptops; each Clone's own Guardian decides every step): TEAM.md.
The Builder (sites, apps, slides and tests; Forge writes its own skills; Five Paths, the best of five plans): BUILDER.md.
Kairu's eyes, the screen agent ("take control and ...": see, think, act, see again, with Gemini): BAR.md "Kairu's eyes".
Kairu Live in the bar (LiveKit hears, Groq thinks, ElevenLabs speaks; the bar, the task core and Guardian act): VOICE.md "Kairu Live".
The hackathon meeting agent (meeting in, decision ledger across meetings, conflict check, split to clones; not built yet, waits for the owner's GO): HACKATHON.md.

## The plan (locked 28 Oct 2026)

- The governing plan is `Kairu - Staged Implementation Plan v2.0.md` (11 Nov 2026, with the Kairu App workspace W1 and W2; v1.9 and older are superseded),
  built on the approved `Kairu - Master Plan v2.0.md` and `Kairu - App Master Plan v2.0.md` (Phases P, E and D).
  Decisions are in `Kairu - Architecture Decision Records.md`.
  Order of authority: accepted ADRs, then Plan v2.0, then the two master plans, then the older documents.
- Build only the phase or part the owner approved with GO. Do not change the plan, an ADR or the
  build order without the owner's approval; propose the change instead.

## Rules for Claude Code

- Python 3.12.
- Claude Code may push new branches, but never to `main`.
- Never force-push.
- Never merge or close pull requests. The owner does that.
- Critical actions stay blocked, with no approval path: no prompt, PIN, setting, flag or test
  helper may ever unlock one.

## Also

- Never weaken Guardian. High tier always needs "yes" plus the PIN (two exceptions: ADR-035, a paired phone's own
  waiting request, by its enrolled fingerprint key's signature, see the Link rule below; and ADR-054 (proposed, the owner's
  GO of 20 Nov 2026), screen.agent_confirm, the only action policy.yaml may give `pin: false` (policy.load refuses it on any
  other action or tier), asked only by a take-control run at the PC that you started with your yes, never from a phone; see
  Kairu's eyes below); an action that is not in `policy.yaml` is always denied; no existing test is removed or loosened.
- The emergency stop must end every running action, with all the programs it started, in under
  1 second.
- The target is the owner's Windows 11 Home PC; everything must also keep working on Linux (CI).
- Keep memory use low. Prefer the standard library and ctypes; before adding a dependency, say
  why it is needed.
- The voice and research prototype is not part of this branch; Kairu does not import it.
- Guardian's monitors (kairu/protect/) never act, approve or change rules; their only request to
  Guardian is `report`. They read Gmail with the read-only permission only, and never open links or
  attachments. Email text never leaves the PC and never goes into Guardian's audit log.
- A Kairu Link message (kairu/link/) is a request, never an order: it is decided by Guardian like any
  other, High still needs "yes" and the PIN typed at the PC, and no message may carry an approval, with one exception
  (D2, ADR-035): a signature by the phone's fingerprint key, enrolled only with "yes" and the PIN at the PC, over exactly
  one of that same phone's own waiting High requests (kairu/link/approver.py). It is checked in its own short program;
  approve_verified is never on Guardian's channel; a fingerprint can never enroll a key. A "yes" or PIN in a message is
  only text. Its words never go into Guardian's audit log (hashes only). The Guardian program never loads PyNaCl.
- Mission Mode always puts the lid setting back, on every way it can end (LINK.md).
- The brain (kairu/brain/) only thinks and answers: it never runs an action, and its only requests to Guardian are
  `status` and `check`. Secrets never leave the PC, not even with approval; personal data goes to a cloud AI only
  after "yes" and the PIN, for that exact text and that one provider; the privacy filter fails closed; free
  providers only, never the paid Claude API or anything that needs a card. Questions never go into the audit log
  (hashes only). Mission Cards (kairu/missions/) only ask Guardian to `run`, follow and `end` their steps.
- Web research (kairu/research/): the search and the page reads are Guardian actions; the brain never searches or fetches.
  Page text is quoted data and can never become a request. The query passes the privacy filter first: secrets are never
  searched, personal ones wait for "yes" and the PIN. A read reaches public web addresses only, and the search goes to
  DuckDuckGo only. kairu/research/conduct.py's only requests to Guardian are `run`, `run_status` and `end`.
  Deep research ("research deeply ...", R2): at most 3 searches for one question, each still its own Guardian action; the
  brain names the extra search words before any page is read, and each passes the privacy filter; no new policy action.
  "Where am I?" (research.location, Medium, private, ADR-053 proposed, the owner's choice of 19 Nov 2026): at Main Kairu's
  own PC only; Windows' location rounded to 2 decimals goes only to nominatim.openstreetmap.org; only area, city and state
  are kept, never the exact position, a road or a postcode; answered by rules.
- The memory (kairu/memory/): data/memory.db never leaves the PC: no file there uses the network, and no memory line is
  ever added to anything sent to a cloud AI, a search or the phone. The brain only reads it; memory.remember and
  memory.forget are Guardian actions asked for by kairu/memory/conduct.py (`run`, `run_status`, `end` only). A secret is
  never kept. Lines never go into the audit log (hashes only).
  The talk history (kairu/memory/talks.py, brain.db talks, MEMORY.md "Talk history"): only answered talks at the PC, never one
  with a secret, 30 days and 300 at most; told only at the PC, by rules; never sent anywhere or written to the audit log;
  "forget our talks" is memory.forget. brain.talk_history: false keeps none.
- The task core (kairu/tasks/) and the bar (kairu/bar/) hold no authority: every step goes to Guardian with GuardianClient.run.
  No code fills or presses the bar's "yes" and PIN boxes (one exception, ADR-054: Kairu Live's spoken answer to a
  take-control card, see Kairu's eyes). A skill missing from policy.yaml or Critical is refused at load. Window
  titles, file names and page text are data. tasks.work_folder is supplied by Guardian and only the owner changes it. Tests of the
  skills run on the pretend PC (KAIRU_TEST_PC), so they never close an app or restart the PC.
  The Ember Glow pill (kairu/bar/pill.py, BAR.md "The pill") only shows what the bar knows: its windows let clicks through, never
  take the keyboard and have no box or button; it reaches no client, core or Guardian; an order is never shown as typed (only an
  app it opens), and only a finished task gets the tick and "Done". Windows only, ctypes; if Windows refuses, there is no pill.
- The voice (kairu/voice/, kairu/bar/voice.py) holds no authority: every spoken order goes to the task core and Guardian like a
  typed one, and voice can never approve (High needs "yes" and the PIN typed in the bar's card; a spoken yes or PIN is never an
  order; the one exception, ADR-054: Kairu Live's words, only "yes"/"no" to "Is this correct?" or "go on"/"stop" to "Your
  turn", alone, within 60 seconds of a take-control card opening, answer that card and nothing else; digits never do). The mic is off at every start, stop, lock and sleep, and only the owner's own click or Ctrl+Alt+V switches it on; the
  listener opens the microphone only for the bar's session token. No sound is ever written to disk; no sound or transcript leaves
  the PC or reaches the audit log (hashes only), with one exception: Gemini hearing (voice.hearing: gemini, the owner's GO of
  16 Nov 2026, kairu/voice/gemini.py, VOICE.md "Gemini hearing") sends each utterance the gate ended, once, in memory, to
  generativelanguage.googleapis.com only, with the sealed key from `kairu provider add gemini`; its words are only words (a spoken
  yes or PIN is still never an approval), and the offline Whisper hears whenever Gemini can't. voice.hearing is Guardian's
  setting, never a request's; the default is local. The camera check (voice.camera, the owner's GO of 16 Nov 2026,
  kairu/voice/lips.py, VOICE.md "The camera check"): the camera opens only while the listener runs (the mic is on) and is
  released when it ends; one small grey frame at a time, in memory only, never written, sent or shown; only lips.py imports
  OpenCV. A sentence the camera says your lips didn't say is never an order, wake or answer; "Kairu, stop" works from anyone;
  without OpenCV or a camera there is no check, said once. The model, Piper and its voices come only from `kairu voice setup` (official
  sources, SHA-256 pinned), never a Kairu action, and are never committed. Piper is the MIT rhasspy/piper build run as a separate
  program; never the GPL piper-tts package. Kokoro (VOICE.md "Kokoro", the owner's GO of 15 Nov 2026) comes only from its official
  release (SHA-256 pinned, `kairu voice setup`) and runs only in its own program, kairu/voice/kokoro_worker.py, which imports
  nothing of Kairu, writes nothing and reaches no network; no other Kairu file imports kokoro-onnx, phonemizer or espeak-ng
  (GPL-3.0). If Kokoro is not set up or its program does not start, Piper speaks. Every spoken answer follows Tenmin (kairu/brain/tenmin.py: answer first and short,
  exactly one follow-up question); finished tasks stay quiet. voice.style (warm, lively, calm, plain) is Guardian's setting, never a
  request's; a style only changes Piper's own speed and tone dials for the answer and the question, one Piper at a time. The voice stays under 200 MB at rest and 400 MB while
  speaking with Piper, 600 MB with Kokoro (raised by the owner, 15 Nov 2026). After Kairu asks a question aloud with the mic
  already on, the listener takes your answer without "Kairu" for at most 8 seconds; that never switches the mic on. A
  "Kairu" heard alone but unsure opens the same short window; an order heard unsure never wakes Kairu or runs.
  Live words (voice.live_caption_every, the owner's GO of 15 Nov 2026): Whisper's look at what you have said so far is only
  shown, in grey ("hearing"), never a stop or an answer; it keeps the "heard" rules (no "Kairu" outside a session: nothing
  shown; never a yes or PIN; never Kairu's own voice), and one look at a time, never queued. The one order it may send
  (the owner's "it must work fast", 15 Nov 2026): after 0.2 s of quiet, Whisper's closing look, if sure, at a QUICK_ORDER
  (open an app, volume, brightness, mute, what's open; never with "and"/"then" or a file), sent to the task core like any
  spoken order and decided by Guardian; never twice; every other order waits for the whole utterance. With voice.fast_orders
  (kairu/voice/fastlane.py) the small Vosk model, beside Whisper, gives the live words and decides the quick order from its
  grammar (QUICK_GRAMMAR: no [unk], every word sure, "Kairu" first outside a session); it writes nothing.
  Your voice (voice.only_my_voice, kairu/voice/myvoice.py): `kairu voice enroll` is an owner command, never a Kairu action; it
  keeps only an averaged voice print (numbers, no sound or words) in data/voice/my-voice.json. On, an utterance not in that
  voice is never an order, wake or answer; "Kairu, stop" works from anyone; no voice print or model: the mic stays off
  (fails closed). The speaker model comes only from alphacephei.com, SHA-256 pinned, via `kairu voice setup`.
  `kairu voice check` (kairu/voice/check.py) is an owner command typed in PowerShell, never a Kairu action: it opens the mic
  for at most 60 seconds, prints what Whisper heard on the screen, and writes, sends and runs nothing.
  Voice tests use recorded sounds (KAIRU_TEST_MIC, KAIRU_TEST_VOICE), never a mic, and play nothing aloud.
- The workspace (kairu/workspace/) holds no authority, like the bar: every order goes to the task core, and no code in the server
  or its page fills or presses the card's "yes" and PIN boxes; what was typed goes to GuardianClient.approve and is forgotten. The
  server listens on 127.0.0.1 only and answers the API only with this start's key and its own Host. The page shows data as text,
  never markup, under a strict CSP. Projects, missions and messages stay in data/workspace.db, never in the audit log. Standard
  library only; tests never open a window (KAIRU_TEST_PC). W2: its mic follows every voice rule; only the page's mic button and
  Ctrl+M (through /api/mic and Workspace.mic_pressed, the one caller) switch it on, and it goes off when no window has asked for
  WINDOW_GONE_SECONDS. The voice link is held only while a mic is on, so the bar and the workspace share one mic. The Files panel
  lists names from the steps, never from the disk, and its buttons send orders. files.open never opens a program, script or
  shortcut; files.write never overwrites.
- The phone app (phone/) is Kotlin, built only on GitHub (.github/workflows/phone.yml); the PC needs adb only, never Android
  Studio. `kairu phone` (kairu/phone.py) only moves the app to the phone: an owner command, never a Kairu action; adb runs with a
  list of arguments, no shell. Each stage adds only the Android permissions it needs. No signing key is ever committed.
- Shadows (kairu/shadow/): a Shadow holds no authority and is never a paired device. What it sends is data, cut to fixed fields
  (kairu/shadow/wire.py), never a request, and no message from one is ever handed to Guardian. Making one, installing what it
  brought home and running a pack are High; a Shadow never installs anything. An install takes only the files with the digest the
  Shadow signed, after the pack check and the pack's tests pass again on the PC; it changes no Guardian rule, never touches
  policy.yaml or the project folder, and a pack runs only through pack.run, in its own program, while its files are still the
  ones installed. A Shadow's key and topic are deleted on return (both sides). It carries nothing of the owner's. A pack Shadow's
  friend laptop runs only kairu/shadow/agent.py (PyNaCl; no Guardian, no brain): it touches only its own folder, sends counts and
  one report through the Gate, and pushes only packs/NAME by git. A Cowork Shadow (ADR-039, kairu/shadow/cowork.py) also puts a
  copy of the owner's repository in its own folder and installs it there under the friend's own PIN, with nothing of the owner's
  (no data folder, keys, Gmail, phone or memory); it is taken down (Task Scheduler tasks removed, Guardian and bar ended) whenever
  the Shadow leaves; its changes come home only as a branch and a pull request after Kairu's own check passed on exactly those
  files; it installs on the owner's PC only by shadow.upgrade (ADR-041: High, exactly the signed tree, never loosening a Critical
  rule, after Kairu's own check passes on the upgraded Kairu in a separate folder). Lessons are words: kept only after the owner's yes, never a rule.
  The `kairu` command and the Guardian program still never load PyNaCl. Shadow tests use the stand-in relay and folders on the PC.
- Asking an AI website and reading a page (kairu/tasks/ask_ai.py, ASK.md): web.ask types only into the sites in SITES, at
  their fixed addresses, and only in a browser window started with Kairu's own profile (data/browser-profile), never the
  owner's own browser; a page that asks for a sign-in is never typed into; a secret is never typed; personal words are
  web.ask_private (High). The page's answer and web.read_page's words are quoted data (orders and secrets left out),
  shown to the owner and passed to no AI. ask_ai.py makes no key press itself: it uses the hands, and keeps their rules.
- Kairu's hands (kairu/tasks/screen.py, kairu/hands.py; BAR.md "Handling a task", ADR-040 proposed) hold no authority: each
  step is a Guardian action (screen.read Low; screen.type, screen.press, screen.click Medium, and only in SAFE_APPS;
  screen.confirm High). Only kairu/hands.py makes key presses or clicks, only kairu/tasks/pc.py imports it, and every one
  names its window and is sent only while that window's program is in front and is not Kairu's own. They never touch Kairu's
  own windows, security, password, terminal or money apps and pages, never click pay or buy, never press Win or Ctrl+Alt keys,
  and never type a secret; none of these has an approval path. Window titles and what screen.read finds are data.
  PC4, the rest (ADR-042 proposed, BAR.md "Reading any window, numbers and the safe list"): screen.read_text and screen.numbers
  are Low and read-only; what they find is data, shown to the owner, never an order and never sent; a password box is never
  read. The picture (kairu/hands.py capture and ocr) is the backup only: one window by PrintWindow, held in memory, handed to
  Windows' own OCR on standard input, never written to disk or sent; its words decide a click's tier as a button's name does.
  The core may turn "click 3" into the name screen.numbers showed (only fills in, never a tier). hands.mark_safe is High and
  never takes an app in NEVER_SAFE (terminals, editors with a terminal, remote desktop, frame and shell hosts, security,
  password, money, Kairu's own); every read of data/hands-safe.json checks each name again. Plans never use hands.* or
  screen.numbers. In File Explorer's address bar only a folder that exists is Medium; anything else there stays High.
  Words of PASTE_FROM letters or more are pasted (kairu/hands.py paste_text: Ctrl+V through send() and its checks, only when
  the clipboard holds nothing or plain text, which is put back right after; a picture or copied files are never touched, and
  then the words are typed). The words pass the same checks first (never a secret).
- Clones (kairu/team/, TEAM.md, ADR-043 proposed): towards a Clone, Main Kairu is a paired device like the phone, so every
  order is a D4 mission (task.order) that the Clone's own Guardian decides; High waits for "yes" and the PIN typed on that
  laptop, and Main Kairu never sends or holds an approval for a Clone. A Clone's reports are data: kept in data/team.db for the
  board, never handed to Guardian, an AI or another Clone; a report moves a task only when its tag names that Clone's running
  task and step. team.split uses the brain like brain.plan (same privacy filter, public briefs only) and its answer is read
  strictly (kairu/team/split.py): no order may carry a PIN, a password or a "yes". team.add is High. Main Kairu's side uses
  kairu/link/testclient.py's crypto, so the `kairu` command and the Guardian program still never load PyNaCl.
  ADR-048 (proposed): Main Kairu's notes to a Clone (welcome, hand-off, heads-up) are built only from its own data, ride on
  that Clone's next order after a "NOTE " line, are taken off before the Clone's task core sees the order and kept in its
  inbox with team.note (Low, private): words to show, never an order. `kairu team say` is link.send to Main Kairu; its words go
  on the board's feed only. team.set and team.move are Medium, team.status Low (read only). "split the project" and "start
  the project" work only at Main Kairu's own PC (source "pc"). Main Kairu's keys for each Clone are DPAPI-sealed.
  The growth record (ADR-049 proposed, kairu/team/growth.py): by rules, about tasks never people, no score and no ranking
  (Clones in name order). Every entry reaches that employee's laptop with its next order (clones.pending); Kairu only
  suggests to the manager, never assigns, promotes or marks anyone down; team.check and team.offer are Medium, and only the
  offered Clone's own answer changes its offer.
- Commands and installs (PC5, kairu/tasks/terminal.py, BAR.md "Commands and installs"): a command runs as a Guardian action,
  as a list of words with no shell (no pipes, chains or redirection), only in the work folder or Kairu's own folder; its tier
  comes from terminal.classify, in the core and again inside the action: read-only safe list Low, work safe list Medium,
  anything else High, admin rights and Windows security, boot, users, disks, services or HKLM Critical (terminal.admin, no
  executor). apps.install and apps.uninstall (winget) are High; a silent or hidden install is apps.install_hidden, Critical.
  What a command prints is data, shown to you only. The hands still never type into a terminal window.
- Plans (PC6, PC7; BAR.md "Do whatever I say"): a plan is still shown first and runs only after "yes" (and the PIN for its one
  High step); terminal.run in a plan keeps the command's own tier. data/plan-journal.json (kairu/tasks/journal.py) only records
  a plan's steps and how many are done, on this PC only; "go on with the plan" runs the rest only as a new plan, shown and
  decided again; a journal step that is not a skill plans may use is forgotten, never run. `kairu doctor` is an owner command,
  read only.
- The Builder (kairu/build/, BUILDER.md, ADR-050 proposed) holds no authority: the AI only writes drafts (build.draft,
  forge.draft, paths.draft, Low), kept in data/builder.db; every step that changes anything is a Guardian action decided by
  its own tier, made, tried or kept only with the sha256 of exactly what you were shown. build.write (Medium) makes a NEW
  folder in the work folder and overwrites nothing; a built page never reaches the network by itself; built Python uses only
  the safe standard modules in make.IMPORTS and its own files, and its tests run only with build.test (High), unchanged. A
  Forge recipe is only plannable skills (never terminal.run); Guardian decides each step first (refused, Critical or two High
  steps: no skill); forge.test runs it five times on a stand-in laptop only (pc.StandIn, its own temporary folders); forge.save
  (High) keeps it only after 5 of 5 pass; a kept skill comes after the built-in skills and runs as a plan, shown first. Five
  Paths drops any plan Guardian refuses a step of, and runs only the one you pick, as a plan. Briefs go to brain.build_providers
  (Gemini first) through the same privacy filter as brain.plan; the Builder's orders work at Main Kairu's own PC only.
- Kairu's eyes (kairu/tasks/eyes.py, kairu/tasks/agent.py, BAR.md "Kairu's eyes", ADR-051 proposed, the owner's GO of
  18 Nov 2026): screen.look (Medium, private) is the one action that sends a picture: ONE window (on the safe list to take
  control; "what's on my screen", mode describe, may see any other window, "what's on my wallpaper" the wallpaper's picture, and "what's on my
  whole screen" every monitor with each never-shown window painted black first, back to front, a window whose program
  Windows doesn't name included; the owner's choices of 19 Nov 2026), never Kairu's
  own, a security, password, terminal or money window (screen._seen and the safe list, no approval path), as a PNG made in
  memory (kairu/hands.py png_of), never written, to Gemini only through Gateway.see, with the window's names and title (a
  line with a secret or an order left out; the backstop reads every word). tasks.eyes is Guardian's setting, never a
  request's; off without it. The goal passes the privacy filter (secret refused, personal not sent) and starts only after the
  owner's "yes" (task.plan keeps it first). Gemini only proposes: kairu/tasks/agent.py reads each answer strictly into one of
  screen.click/type/press (in the app the look saw), apps.open, web.open, web.search or task.wait, never files, commands,
  installs or the safe list, and runs it through the task core's _run_step, so Guardian decides it and High still waits for
  "yes" and the PIN on the card. It stops at a stop, any refusal, a refused card, 3 misses, the same step thrice, 15 steps or
  10 minutes. Orders at Main Kairu's own PC only. Tests use the pretend PC and a stand-in Gemini (KAIRU_TEST_PROVIDERS).
  ADR-054 (proposed, the owner's GO of 20 Nov 2026; BAR.md "Register, apply, log in"): inside a run, a careful step is
  screen.agent_confirm (High, `pin: false`): the card "Is this correct?" takes "yes" typed, clicked or said through Kairu
  Live, with no PIN; outside a run the same step is still screen.confirm (yes and PIN). New steps, each a Guardian action:
  screen.scroll (Medium, also the plain order "scroll down"; never a never-window), screen.choose, screen.tick ("I agree"
  asks first), screen.point (a point on the picture, decided by what UI Automation or the picture's words say is there;
  nothing readable asks first; never a password box), screen.fill and screen.saved_password (Medium, browser only). Hand-over
  ("Your turn: ..."): no picture and nothing sent until you say "go on", within the same 10 minutes. Gemini's "too many
  requests": one wait (at most 60 s), one more try. My details (kairu/tasks/details.py, data/my-details.json): on this PC
  only, never a secret (the privacy filter reads every value, whoever asks), kept only by `kairu details` (an owner command)
  or details.keep (High, yes and PIN); Gemini gets only a detail's name, screen.fill types the value inside Guardian's action
  and its reply never holds it; every later picture paints those boxes black, and with a box not found no picture leaves; a
  line in the names or title holding a detail is left out; never told to Kairu Live, never in the audit log (hashes only).
  Details are typed only on the site open when the run started or one the goal names; the first detail typed locks the run
  to that site; another site stops it. No picture while a password box has the
  keyboard. A password is never read or typed: only the browser's own saved login with your username for that site, else
  "Your turn". Never, with no approval path: a secret, a captcha, money, bank, payment, security or password-manager apps and
  pages, Kairu's own windows, a file window.
- Kairu Live (kairu/live/, VOICE.md "Kairu Live", ADR-052 proposed, the owner's GO of 18 Nov 2026): live.talk (Medium, private)
  starts only for the session token of a mic you switched on in the bar, with voice.live: true (Guardian's setting, never a
  request's), like voice.listen, and never by voice.listen_at_start; an emergency stop ends it with everything it started. kairu/live/talk.py imports nothing of
  Kairu and holds no authority: it runs with the Python in voice.live_folder, gets only its own keys from that folder's .env,
  and every order it wants is handed to the bar's task core and Guardian like a typed one, one at a time (High waits for
  "yes" and the PIN typed in the card; a spoken yes or PIN is never an order; while the card is open its mic sends silence,
  except a take-control card, ADR-054, whose spoken answer it may give).
  What you say goes to Deepgram, Groq (Gemini if Groq can't; the owner's GO of 19 Nov 2026) and ElevenLabs only with voice.live on; nothing is written to disk. What it hears
  back about an order is only what kairu/live/relay.py lets through (never a memory line, talk history, window title, page or
  command text). Today's talk (ADR-053 proposed): the bar keeps today's Kairu Live turns, both sides, at most 30, in memory
  only (never on disk or in the audit log, never a line with a secret, none with brain.talk_history: false; "forget our
  talks" ends it) and hands them to the next session; nothing else is added. "Kairu, stop" is the emergency stop. It does not start with voice.only_my_voice or voice.camera on.
  Its tests use a stand-in talking program, never LiveKit, a microphone or the network.
- Run the checks before pushing: `python tools/check_guardian.py` (Windows: `py -3.12 tools\check_guardian.py`).
