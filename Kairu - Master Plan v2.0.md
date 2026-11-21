# Kairu Master Plan v2.0 — Full Build Plan

> **Status: APPROVED by the owner on 27 Oct 2026. Locked as Kairu's governing plan on 28 Oct 2026.**
> This file is a copy of the approved plan (Claude Docs, revision 28): https://claude.ai/artifact/76NCgH7qdYtfHHf3Pv6Ntz
> The five diagrams live only in that original. Changes made after approval (27–28 Oct) are recorded in
> *Kairu - Staged Implementation Plan v1.4* and *Kairu - Architecture Decision Records*, which take priority
> over this text where they differ (for example: the hackathon sprint is set aside).

Oct 27, 2026 · @saitej

## 1. What you asked for, in simple words

Kairu becomes one family: one powerful **Main Kairu** on your laptop, small **Guardians** with their own brains on your devices (first: your phone), and **Shadows** that Main Kairu sends to a friend's laptop. This plan explains every part, the order to build it, and how we test that each part really works.

**How to read it.** Sections 3 to 10 follow your six points. Section 13 is the build order. Section 14 lists the few choices only you can make, each with my recommendation. When you say **APPROVE**, I save this plan to memory as the new master plan. It extends your System Architecture v1.1 and Staged Implementation Plan v1.3.7; it does not cancel any decision you already made.

| # | What I understood | Section |
| --- | --- | --- |
| 1 | Main Kairu lives on your laptop and is the strongest member, like an S-rank hunter. It builds large websites, apps, AI agents and AI assistants, does deep research, runs large-scale and high-level testing, speaks like Tenmin, explains clearly to you, makes presentations, explains what is happening in other countries, and keeps working while the laptop "sleeps". | 5, 6 |
| 2 | Every Guardian has its own brain, separate from Main Kairu, so it keeps working when the laptop is off. The Phone Guardian does limited jobs: send messages, open apps, do what you say, call people, and good research. Big research stays with Main Kairu. | 7 |
| 3 | You call the Phone Guardian "Kairu" too. Same name, same personality, no confusion. | 7 |
| 4 | On a trip without the laptop: you tell phone-Kairu to have Main Kairu call you. Main Kairu calls, you give a mission (for example: apply to the XYZ hackathon, wait for the problem statement, then build it to 100%). It calls back when the work is done, or when it has a doubt or a suggestion. It calls only when you cannot use the laptop. | 8 |
| 5 | When you are at the laptop, Kairu speaks to you directly instead of calling. | 9 |
| 6 (main role) | You say "Go to my friend's laptop, help him finish his project, then come back to me." Kairu goes, helps, and returns with a report. | 10 |

"Laptop" in this plan means your one computer (Windows 11 Home), which is Kairu's home.

## 2. Where Kairu is today

Kairu is about 15% complete: the design is nearly finished and Guardian core is built and merged, but five of the nine parts have not started yet.

> *Diagram: typed from your progress chart · 9 parts and whole Kairu, 27 Oct 2026 — see the original in Claude Docs (link at the top).*


| Part | What is done | What is left |
| --- | --- | --- |
| Planning & design | Master Vision v0.1, System Architecture v1.1, Staged Implementation Plan v1.3.7 and the decision register, all in the Kairuu repository | Approve this plan, answer section 14, define the five planes and L0–L4 |
| Guardian core | Built, tested on your PC, merged into main on 25 Oct | Nothing; later it also signs the policy packs for devices |
| Guardian own program | Approved as a background process that starts at login | Build it: login start, tray icon, stop button, logs |
| Guardian wider protection | Designed: email, notifications, files, deadlines, devices; monitoring never acts | Build it (Phase J) |
| Research & speak | Research and speech worked in your tests, but slowly because of low RAM | Wake word "Kairu", short answers, speed, 24/7 listening |
| Tenmin-style talking | Persona described on 24 Oct | Build the persona and the voice |
| Brain & AI routing | Rules decided: L0 limits, cloud approval, free providers only | Build the Model Gateway |
| Phone & face check | Face check decided: confirmation only | Build the phone app and the face check |
| Build websites & apps | Wanted since 25 Oct | Build the builder squad (Phase G) |

### Fixed rules this plan keeps (your earlier decisions)

- Free to run: no paid Claude API, costs and limits shown openly, no hidden daily limits, no spending cap unless you set one.
- Secrets and sensitive data stay local; your approval before any private information goes to cloud AI.
- Tiers: Low and Medium go ahead within scope, High needs your confirmation, Critical is blocked with no approval path.
- Guardian is the only authority; monitoring never acts by itself.
- Two brains (Reasoning & Decision separate from Orchestration), the five-plane architecture, the Safety Controller, the Control Plane and L0–L4 routing all stay.
- The Agency's Agents Orchestrator has a main role; OpenJarvis is only an optional local engine, never an authority.
- Answers are short, correct and easy, in Tenmin style.
- Everything lives in github.com/sungjenwoo/Kairuu; plans are approved before building; Claude Chat plans and reviews, Claude Code builds and tests.
- Low RAM for now: RAM-heavy parts wait for the upgrade.

## 3. Honest reality checks (read this first)

Almost everything you asked for can be built and kept free to run, but seven points need a clear workaround because of how laptops, phones and the law work. Knowing them now avoids surprises later.

| # | Your wish | The hard truth | The workaround in this plan |
| --- | --- | --- | --- |
| 1 | Kairu works while the laptop is in sleep mode | In real sleep the processor is stopped. No software on any laptop can think while it sleeps. | **Mission Mode**: while a mission runs and the laptop is charging, Kairu keeps it awake with screen off and lid closed. It looks asleep and uses little power. A tiny always-on **Kairu Gate** keeps listening for you and can wake the laptop. Section 6. |
| 2 | Kairu works when the laptop is shut down | If the laptop is powered off, Main Kairu cannot run until it is switched on. Remote wake-up from "off" works only on some laptops, mostly with a wired cable. | The **Phone Guardian keeps working on its own brain** (your point 2 is exactly right). The Gate keeps your missions in a queue, and Main Kairu starts them the moment the laptop turns on. |
| 3 | Main Kairu makes a "normal call" | A real SIM-network call to your number costs money per minute and needs a paid calling provider with identity checks in India. That breaks your "free to run" rule. | **Kairu Call**: Main Kairu calls the Kairu app on your phone over the internet. It rings full-screen like a normal call with Answer and Decline buttons, and works on mobile data. A paid real-number call can be added later as a backup (your choice, section 14). |
| 4 | Kairu applies to hackathons by itself | Many sites ask for an OTP, a CAPTCHA, or "I agree to the terms". | Kairu fills everything else, then asks you during the call for the OTP or your "yes". It never solves CAPTCHAs and never accepts terms alone. This also follows your rule that High actions need your confirmation. |
| 5 | Kairu goes to a friend's laptop | Entering someone's computer without their permission is hacking and is illegal. | The friend must allow it: either by sharing the project online (no install) or by opening a small, always-visible **Shadow** app with a code from you. The friend can stop it at any time. Section 10. |
| 6 | Big local AI on the laptop | Your laptop's RAM is too small right now, so heavy local models run slowly (you saw this on 25 Oct). | Low-RAM parts and free cloud models come first. Local models switch on after your RAM upgrade, with no redesign. |
| 7 | Phone does whatever you say | Android allows a lot (open apps, SMS, calls, tapping inside apps). Some apps change their screens often, which can break automation. | Each phone skill has a fallback: if tapping inside an app fails, Kairu opens the app with the text ready and tells you what to press. |

## 4. The big picture — the Kairu family

Kairu is one family with one name: Main Kairu is the strong leader on your laptop, Guardians are devices with their own brains, Shadows are helpers sent to friends, and they all talk through the Kairu Gate using encrypted messages.

> *Diagram: the Kairu family · Main Kairu, Phone Guardian, Gate, Shadow, cloud models — see the original in Claude Docs (link at the top).*


The phone never needs the laptop to be on; it only needs the Gate when it wants Main Kairu's help.

| Member | Lives on | Own brain? | Works when laptop is off? | Main job |
| --- | --- | --- | --- | --- |
| Main Kairu | Your laptop | Yes, the biggest (L0–L4) | No (its missions wait safely in the Gate) | Building, deep research, testing, missions, Shadows |
| Phone Guardian | Your Android phone | Yes, small (L0, L1, L3) | Yes | Messages, apps, calls, good research, Kairu Call screen |
| Kairu Gate | Free relay, later a home device | No AI; only passes messages and wakes the laptop | Yes | Queue, wake-up, call signalling |
| Shadow | A friend's laptop, only while invited | No; it is Kairu's hands, the brain stays home | No | Work inside one project folder, then remove itself |

### Kairu Link: how the members talk

- Every member gets its own key pair when you pair it with Main Kairu (scan a QR code once).
- Every message is small, signed and encrypted. It says who sent it, who it is for, its type (command, mission, status, call request, doubt, report), its safety tier, and its content.
- The Gate stores messages it cannot read until the receiver comes online, and drops old or repeated messages so nobody can replay them.

### The five planes (proposed meaning — please confirm)

You asked to keep a five-plane architecture with a Safety Controller and a Control Plane. This plan places every part in one of five planes:

1. **Interaction plane** — how you talk to Kairu: voice, wake word, chat, Kairu Call, screens.
2. **Control Plane** — the Orchestration brain, Mission Manager, scheduler, device list, Shadow Manager.
3. **Intelligence plane** — the Reasoning & Decision brain and the Model Gateway (L0–L4).
4. **Execution plane** — agents, tools, project sandboxes, phone skills, Shadows.
5. **Safety plane** — Guardian, the Safety Controller, policy packs, approvals, logs and stop buttons.

## 5. Point 1 — Main Kairu, the S-rank hunter

Main Kairu is a team leader, not one giant program: the **Orchestration brain** (built on The Agency's Agents Orchestrator, as you wanted) commands a squad of specialist agents, and the **Reasoning & Decision brain** checks every plan before the squad acts. This keeps your rule of two separate brains.

### The two brains

- **Reasoning & Decision brain** — understands what you want, asks only the questions that matter, makes the plan, decides, and asks Guardian whether each action is allowed.
- **Orchestration brain** — splits the plan into small tasks, gives each task to the right agent, tracks progress, retries failures, and reports back.

### Missions: how Kairu does long jobs

Every big job becomes a **Mission Card** saved on disk. It holds: the goal, what "100% done" means, the steps, status, open doubts, deadlines, and how to report to you (speak or call). Kairu saves a checkpoint after every step, so if the laptop restarts, it continues from the last checkpoint instead of starting again.

**What "100% done" means for any build mission:** every requirement on the checklist is ticked, all tests pass, the app runs from a clean install, a short demo (screenshots or video) is recorded, a README explains how to run it, and you have been told the result.

### Every power and how it is built

| Power | How it works (simple) | Main free tools (final pick in that phase) | Phase |
| --- | --- | --- | --- |
| Build large websites | Architect agent designs the pages and data. Frontend and Backend agents write the code. Tester agent tests. Reviewer agent checks quality and security. Every project gets its own Git repository and branch, so nothing is lost. | An open-source coding-agent engine behind the Model Gateway, Git, Node/Python, a browser robot for testing | G |
| Build apps | Same squad. Web apps and installable web apps first (easiest to test), then Android apps with a cross-platform framework. | Flutter or React Native (chosen in G) | G |
| Build AI agents and AI assistants | An "Agent Builder" recipe: goal, tools, memory, safety rules, and tests. Kairu reuses its own parts (Model Gateway, tools, Guardian rules), so it can build smaller assistants for others. | Kairu's own components | G |
| Deep research | A research loop: break the question into sub-questions, search many sources, read the full pages, cross-check facts, keep fact and opinion separate. You get the short answer first; the full report with sources only if you ask. | Free search sources and a page reader (checked in B) | E (basic), G (deep, many agents) |
| Large-scale and high-level testing | A test ladder: unit tests, integration tests, end-to-end tests (a browser robot clicks through the site like a user), load tests (thousands of pretend users), security scans, accessibility checks. For AI agents: fixed question sets with expected answers, scored after every change. Kairu never says "done" before tests pass. | pytest/Jest, Playwright, k6 or Locust, OWASP ZAP | G |
| Presentations | Presenter agent: outline, slides, speaker notes, export to PowerPoint or PDF, then explains each slide to you by voice. | python-pptx or HTML slides | G |
| What is happening in other countries | "World Brief": collects news from many countries' sources, groups it by country and topic, removes duplicates, explains in simple words, shows both sides on political topics, and lists sources. Ask any time: "Kairu, what is happening in Japan?" | News RSS feeds plus the research loop | G |
| Speak like Tenmin | The persona you described: warm and encouraging, short quick turns, waits for you, answers first and then offers one follow-up question, explains simply like a teacher, short correct answers ("Who is the prime minister of India?" gets just the name). | Wake word, speech-to-text, text-to-speech (section 11) | E |
| Clear explanations for you | "Explain Mode" for every result: one-line answer, then up to three simple points, then one example, then "Shall I go deeper?" | Built into the persona | E |

### The agent squad

From The Agency's persona library, Kairu starts with these roles and adds more only when a mission needs them: Architect, Frontend developer, Backend developer, Mobile developer, Tester, Reviewer (code and security), DevOps (deploys for free), Researcher, Presenter, News analyst. Each agent gets only the tools its job needs; the Orchestrator never gives every agent every permission.

## 6. Point 1 (last part) — Working while the laptop "sleeps"

Kairu works "during sleep" by splitting the job in two: a tiny always-on **Kairu Gate** keeps listening and watching, and the laptop runs in **Mission Mode** (awake, screen off, lid closed, charging) whenever there is heavy work.

### What Kairu can do in each laptop state

| Laptop state | What Main Kairu can do | How |
| --- | --- | --- |
| On, you are using it | Everything; speaks to you directly | Normal |
| **Mission Mode** — screen off, lid closed, charging | Everything, silently; calls you only if you are away | Kairu asks Windows not to sleep while a mission runs and sets "lid close = do nothing" only while charging. When no mission is running, normal sleep is allowed again. |
| Real sleep | Main brain is paused. The Gate still receives your messages, keeps them in the queue, and watches pages (for example a hackathon page) | The Gate wakes the laptop: by a Windows wake timer that checks the queue at set times, or by a wake-up signal from a device at home |
| Shut down or battery empty | Main Kairu cannot work. The Phone Guardian works alone. The Gate keeps every mission safe in the queue. | Guardian starts at login (already approved on 25 Oct), Main Kairu reads the queue and continues |

**Mission Mode safety rules:** only while charging; Kairu stops heavy work if the laptop gets too hot; it reminds you to keep the laptop on a hard surface; it releases Mission Mode as soon as the mission ends.

### Where the Kairu Gate lives (three options)

1. **Start: no server of your own.** A free encrypted message relay connects phone and laptop. You switch on Mission Mode before you travel. Simplest and free; the relay only ever sees locked (encrypted) messages.
2. **Upgrade (recommended): a home Gate.** An old Android phone or a small mini computer, always plugged in at home on your Wi-Fi. It can wake the laptop, watch pages, and keep the queue, and it stays inside your home, which matches your rule "secrets stay local".
3. **Alternative: a free-tier cloud server.** Always reachable, but it is outside your home, so it must hold no readable secrets — only encrypted messages it cannot open.

Phase C checks the current free limits of each relay option before we pick one, because free tiers change often.

## 7. Points 2 & 3 — Phone Guardian ("Kairu" on your phone)

The Phone Guardian is a separate Android app with its own small brain, its own copy of Guardian's safety rules, and the same name, voice and personality as Main Kairu — so it works alone when the laptop is off, and you simply call it "Kairu".

### How "Guardian" and "guardians" fit together

In your design, **Guardian** is Kairu's protection and authorization authority. In this plan, every device guardian carries a **policy pack**: a copy of Guardian's rules (Low / Medium / High / Critical), signed by Main Kairu. So even with no internet and the laptop off, the phone obeys the same rules. Monitoring still never gives authority to act.

### Its independent brain (three layers)

1. **L0 — instant rules, no AI.** "Open WhatsApp", "call Amma", "set an alarm for 6". Works offline, instantly.
2. **L1 — a small AI model on the phone.** Understands normal sentences offline ("tell Ravi I'll be late"). Its size depends on your phone's RAM — your phone has 6–8 GB, which is enough for a small offline model (about 1–3 billion parameters, compressed). Phase D picks the exact model after testing speed and battery on your phone.
3. **L3 — free cloud AI, when online.** Good research and longer answers. Personal data passes the privacy filter first and leaves the phone only with your approval.

For big jobs (deep research, building, long missions) the phone sends a mission to Main Kairu through the Gate and tells you: "I've given this to the laptop; I'll tell you when it's done."

### What phone-Kairu can do

| Power | How it works on Android | Safety tier | Note |
| --- | --- | --- | --- |
| Send SMS | Our own app (installed directly, not from the Play Store) uses Android's SMS permission | Medium: reads it back first — "Send 'I'll be late' to Ravi?" |  |
| WhatsApp / Telegram messages | Opens the chat with your text ready; Android's Accessibility service presses Send after your "yes" | Medium | These apps have no free official personal API; if their screen changes, Kairu falls back to "text is ready, press Send" |
| Open apps | Launches any app by its name | Low |  |
| Call people | Finds the contact, confirms the name and number, places the call | Medium |  |
| "Do whatever I say" on the phone | Accessibility service can tap, scroll and type inside apps; every action goes in the log | Depends on the action | Banking and payment apps are Critical: blocked completely |
| Good research | Cloud AI plus web search; short Tenmin-style answer, sources on request | Low | Big research goes to Main Kairu |
| Ask Main Kairu | Sends a mission or a "call me" request through the Gate | Low | Section 8 |
| Kairu Call screen | Rings full-screen like a normal call when Main Kairu calls | Low | Section 8 |
| Face check | Checks who opened the phone (confirmation only) | — | Section 9 |

### Hearing "Kairu" on the phone

The wake-word engine runs on the phone itself. Android requires a visible notification ("Kairu is listening") for this. Listening all day uses battery, so the recommended setting is: always listen while charging or while the screen is on; otherwise use a home-screen button or a long-press shortcut (decision 11).

### One name, two bodies — no double answers

- Both answer to "Kairu". If you are at the laptop (section 9), the laptop answers and the phone stays quiet. Otherwise the phone answers.
- Phone-Kairu and Main Kairu share one memory: when both are online they sync recent conversations and mission status through the Gate (encrypted), so phone-Kairu knows what Main Kairu did, and the other way round.
- You never need to say "phone" or "laptop". Phone-Kairu decides by itself whether to do the job or pass it to Main Kairu.

### How the app is built

A Kotlin Android app with these parts: voice service (wake word, speech in and out), command router (L0, L1, L3), action skills (SMS, apps, calls, accessibility), policy pack plus an approval screen with fingerprint, Kairu Link client (talks to the Gate), Kairu Call screen, face check, and encrypted local storage. It has its own keys, created when you pair it with Main Kairu. It is built for your Mivi phone on Android 16. During setup, phone-Kairu walks you through three things once: "Allow restricted settings" in App info (newer Android needs this before an app installed outside the Play Store can use Accessibility or SMS), the microphone permission for listening, and "no battery restriction", so the phone does not stop Kairu in the background. Phase D tests every skill on your phone before it counts as done.

## 8. Point 4 — The trip scenario (you forgot the laptop)

You tell phone-Kairu "get me a call from Main Kairu"; Main Kairu calls your phone, takes the mission by voice, does the whole job at home, and calls you again only for doubts, suggestions and the final result.

> *Diagram: trip scenario · hackathon mission, 15 messages, 3 calls — see the original in Claude Docs (link at the top).*


Every call goes Main Kairu → Gate → the Kairu app on your phone; the diagram draws it as one arrow to keep it simple.

### Step by step, using your hackathon example

1. **You ask.** "Kairu, tell Main Kairu to call me." Phone-Kairu replies "Okay, it will call you in a moment" and sends a call request through the Gate.
2. **Main Kairu wakes and calls.** In Mission Mode it answers at once; if the laptop is asleep, the Gate wakes it (section 6). Your phone rings full-screen: "Kairu is calling".
3. **You give the mission.** "Apply to the XYZ hackathon. When they release the problem statement, start working and take it to 100%." Kairu repeats it back in short sentences: the hackathon, the team details it will use, the deadline, what "100% done" means, and when it will call you.
4. **You confirm the High actions.** Applying is a High action, so Kairu asks for your fingerprint (or spoken PIN) during the call. It also tells you in advance which later steps will need you again (OTP, final submission).
5. **Kairu applies.** It fills the form with your saved profile. If an OTP comes to your phone, phone-Kairu shows it on screen and asks "Give this OTP to Main Kairu?" — you tap Yes. CAPTCHAs and "I agree" boxes are always yours.
6. **Kairu watches.** It checks the hackathon page and your email for the problem statement at sensible intervals. Watching is light work, so the Gate can do it even while the laptop sleeps.
7. **Kairu builds.** When the statement is out, the agent squad plans, builds, tests and fixes (section 5), saving checkpoints all the time.
8. **Doubts and suggestions.** If a choice really needs you (for example "Should the app use your college login or a demo login?"), Kairu first groups all open questions together, then calls once and asks them one by one. Small choices it decides itself and lists them in the report.
9. **Callback.** At 100%, or if it is stuck, Kairu calls: "Mission update: the project is done. All 42 tests pass, the demo video is ready. One suggestion: add a dark mode. Shall I submit?" (42 is only an example.)
10. **Submit.** Submitting is a High action: you say "submit" and confirm with your fingerprint or PIN. Kairu submits and sends the links, screenshots and a short report to the phone app.

### Call rules

- Kairu calls only when presence says you are away from the laptop (section 9); otherwise it speaks directly.
- Calls are short: news first, then questions, then "anything else?" — Tenmin style.
- During a call you can also say "Give me a full update", "Pause the mission", or "Change the plan to…".
- If a call drops, Kairu calls back once, then leaves a written summary in the phone app.
- If the phone has no internet, Kairu keeps working and stores the update; it calls as soon as the phone is back online (or a paid real-number call is used, if you choose that backup).

## 9. Point 5 — Speak directly or call? (presence rules)

Kairu calls you only when it is sure you are away from the laptop; when you are at the laptop, it speaks through the laptop speakers and shows the details on screen.

### How Kairu knows where you are

| Signal | What it tells Kairu | Where it comes from |
| --- | --- | --- |
| Laptop unlocked and keyboard or mouse used recently (default: last 10 minutes, you can change it) | You are at the laptop | Laptop |
| Webcam sees your face (optional, processed only on the laptop) | You are at the laptop | Laptop |
| You said "Kairu, I'm going out" or "I'm back" | Strongest signal; always wins | You |
| Phone is on your home Wi-Fi | You are at home, maybe not at the laptop | Phone Guardian |
| Phone is away from home Wi-Fi | You are away | Phone Guardian |

### What Kairu does

| Situation | Kairu's action |
| --- | --- |
| You are at the laptop | Speaks directly. Never calls. |
| You are at home but not at the laptop | Speaks out loud on the laptop first ("Master, mission update"). No answer in 2 minutes → Kairu Call on your phone. |
| You are away | Kairu Call on your phone. |
| Quiet hours (decision 4) or phone on Do Not Disturb | Written message in the phone app only; calls only if the mission is marked urgent. |
| You don't answer the call | Tries 2 more times, 10 minutes apart, then leaves a written summary in the phone app. |

The times above are starting defaults; you can change them by voice ("Kairu, wait 5 minutes before calling").

### Face check (phone and laptop) — for confirmation only

- **Phone:** when the phone is unlocked, the front camera quickly checks the face, on the phone only. Master → full Kairu. Someone else → **Guest Mode**: Kairu ignores voice commands, does not read your messages or notifications aloud, and notes "someone else used the phone at 14:05" in your log (no photo is saved unless you allow it).
- **Laptop:** the webcam check is used only for presence and before High actions.
- Face data never leaves the device, is stored encrypted, and is never sent to any cloud. Face check confirms; it never replaces your phone's lock screen and never gives authority by itself.

## 10. Point 6 (main role) — Shadow Missions: going to a friend's laptop

Main Kairu cannot physically travel, so it sends a **Shadow**: a small, visible helper on the friend's laptop that acts as Kairu's hands, while Kairu's brain, memory and keys stay safely on your laptop. When the work is done, the Shadow removes itself and Kairu reports back to you — that is "come back to me".

> *Diagram: Shadow Mission flow · 8 steps, 3 early endings — see the original in Claude Docs (link at the top).*


Every path ends at step 8, so Kairu always cleans up and always reports to you, even when the mission stops early.

### Why this design

- **Brain stays home.** Your secrets, memory and API keys never touch the friend's laptop.
- **The friend stays in control.** Nothing happens without their permission, and they can stop it at any time.
- **Works on almost any laptop.** The Shadow is light (no AI model inside), so even an old laptop can run it.
- **Reuses Kairu's builder squad.** The same agents that build your projects (section 5) work on the friend's project through the Shadow.

### Three ways Kairu can "go"

| Mode | What the friend does | What Kairu can do | Best for | Phase |
| --- | --- | --- | --- | --- |
| **1. Repo Mode** (first; no install) | Shares the project online (for example adds your Kairu GitHub account to the repository) | Copies the project into a safe sandbox on your laptop, works there, then proposes the changes as a pull request; the friend reviews and accepts | Code projects that run anywhere | H, step 1 |
| **2. Shadow App** (main mode) | Downloads the small Kairu Shadow app (no admin rights), types the 6-digit code you send, picks one folder | Works directly in that folder on the friend's laptop: reads, runs, tests, fixes; installs packages only after asking the friend | Projects that need the friend's own setup (local database, special tools) | H, step 2 |
| **3. Guide Mode** (no access at all) | Talks to Kairu through a call link or chat and does the typing | Explains and guides step by step, like a teacher | A friend who wants no install, or wants to learn | H, step 2 |

### The full mission, step by step

1. **Command.** You say: "Kairu, go to Ravi's laptop, help him finish his project, then come back." (Ravi is just an example name.) Kairu repeats back: who, the goal, the time limit (default 3 hours, you can change it), the mode, and the style: teach Ravi, work with him, or do it and show him.
2. **Confirm.** Working on another person's computer is a High action, so Kairu asks for your confirmation (your "yes" at the laptop, or fingerprint/PIN if you are away).
3. **Invite.** Kairu creates a one-time 6-digit pairing code (valid 15 minutes) and a download link, drafts a message for Ravi, and sends it from your phone after you approve the text.
4. **Friend allows.** Ravi opens the Shadow app and sees a clear consent screen: who is coming (Kairu, sent by you), what it can do (read and edit files in ONE folder he chooses, run commands there after showing them, talk to him), and what it can never do (see other files, passwords, his browser, his messages, or stay hidden). He picks the folder and the style, then presses Allow.
5. **Recon.** The Shadow reads only that folder: languages, frameworks, README, error messages, tests, Git history. Kairu (thinking on your laptop) writes a short plan: what is missing, the task list, and a time estimate. Ravi sees it; you get a one-line summary.
6. **Work loop.** For each task: make a safe branch called kairu-shadow (or a backup copy if the project has no Git), make one small change, run it, test it, show Ravi the change in simple words, and continue only when he agrees. Anything that installs software or touches outside the folder asks Ravi first. Ravi can read the live log at any time.
7. **Done check.** All planned tasks done, the project runs, tests pass, and Ravi says "OK". Kairu writes a handover note into the project: what changed, how to run it, what is still left.
8. **Return ("come back to me").** The Shadow closes the connection and deletes itself and its temporary files; the Gate cancels the pairing keys so it can never reconnect. Ravi keeps the log and the handover note. Kairu brings back only a report, never Ravi's code, unless Ravi allows it.
9. **Report to you.** Tenmin style: "I'm back. Ravi's project is done: the login page is fixed and 12 tests pass. One thing is left: he must add his own database password. Want the details?"

### When things go differently

| Situation | What Kairu does |
| --- | --- |
| Ravi declines, or the code expires | Mission cancelled; Kairu tells you why |
| Ravi presses Stop | The Shadow stops instantly, cleans up, returns, and tells you |
| You say "Kairu, come back" | Same as Stop, with a polite goodbye message to Ravi |
| Time limit reached | Asks Ravi to finish the current step, then returns with a "not finished" report and the list of what is left |
| Internet drops | The Shadow pauses safely (work is saved in the branch), keeps trying to reconnect for 10 minutes, then leaves a note and waits |
| Your laptop goes off | The Shadow cannot think without its brain, so it pauses and tells Ravi "Kairu will be back"; the Gate tells you |
| The project needs a password or a paid service | Kairu asks Ravi to type it himself; it never stores it |
| Ravi asks for something unsafe or unrelated (break into an account, copy someone's work) | Guardian blocks it; your Critical rules apply on his laptop too |
| Two friends need help at the same time | Later version: one Mission Card and one Shadow per friend |

Tip: if the project is college coursework, choose the "teach me" style, so your friend learns and can explain his own work.

### How it is built

- **Shadow app.** A small program written in the same language as Kairu's core, packed into one file for Windows first (Mac and Linux later). Runs as a normal user, never as admin. Always shows a window and a tray icon with a big Stop button.
- **Connection.** The Shadow makes an outgoing encrypted connection to the Gate, so the friend opens no ports and it works even on college Wi-Fi. The pairing code is turned into keys; every message is signed.
- **Brain split.** The Shadow has no AI model and no keys. It sends what it sees to Main Kairu and receives exact actions (read this file, write this file, run this command).
- **Local guard on the Shadow.** Even if Main Kairu sent a wrong action, the Shadow checks every action itself: the path must be inside the chosen folder (shortcut tricks blocked), commands run only inside that folder, and a list of dangerous commands (formatting disks, deleting outside the folder, changing system settings) is always refused.
- **Self-removal.** On return, it deletes its own files and leaves only the log and the handover note.
- **Main Kairu side.** A Shadow Manager in the Control Plane holds the Mission Card, the task plan and the timers, and lends the builder squad to the mission.

### Build order inside Phase H

1. **Repo Mode first.** It needs nothing new on the friend's laptop, it is the safest, and it proves the builder squad on someone else's project.
2. **Shadow App and Guide Mode next**, tested on a second laptop of yours (or a willing friend's) before any real mission.
3. **Multi-Shadow** (several friends at once) only after the single Shadow passes all tests.

## 11. Brain & AI routing (free-first)

Every request goes through one **Model Gateway** that picks the lowest level (L0 to L4) able to do the job safely, and it never sends private data to the cloud without your approval.

### L0 to L4 — proposed meanings (your documents don't define them yet; please confirm)

| Level | What it is | Where it runs | Used for | Rule |
| --- | --- | --- | --- | --- |
| L0 | No AI: fixed rules and patterns | Phone and laptop | Open an app, set a timer, simple commands | Low-tier, reversible actions only (your 20 Oct decision); anything else goes to L2 or higher |
| L1 | Tiny AI model | Phone and laptop | Understanding commands offline | Never takes High actions alone |
| L2 | Medium local model | Laptop | Private tasks, summaries of your own files | On hold until the RAM upgrade; OpenJarvis can be the optional engine here, never an authority |
| L3 | Free cloud models | Internet | Research, explanations, coding help | Privacy filter first; your approval before private info leaves |
| L4 | Team mode: several agents plus the strongest available free model plus the deep research loop | Laptop orchestrator plus cloud | Building apps, deep research, missions | Needs a Mission Card and Guardian checks at every step |

### How the router decides (every request)

1. Ask Guardian for the safety tier of what will happen.
2. Check for private data (names, numbers, messages, addresses, file contents). If found: remove it, replace it with placeholders, or ask you.
3. Pick the lowest level that can do the job.
4. If the answer fails or confidence is low, move up one level and try again.
5. Show costs and limits openly (your rule): for example "free limit used today: 70% on provider A — switching to provider B". No hidden daily limits and no spending cap unless you set one.

### Free providers (picked in Phase B)

Kairu connects to several free cloud model providers at once and switches automatically when one free limit runs out. Phase B checks each provider's current free limits and terms before connecting, because these change often. It will not use the paid Claude API (your 21 Oct decision). Local engines (such as Ollama or llama.cpp, or OpenJarvis) plug into the same gateway after the RAM upgrade.

### Voice parts (candidates, picked in Phase E)

| Part | Now (low RAM) | After RAM upgrade |
| --- | --- | --- |
| Wake word "Kairu" | openWakeWord, trained on your own voice saying "Kairu" | Same |
| Speech to text | A light offline engine such as Vosk | Whisper-class model, more accurate |
| Text to speech (Tenmin-like warm voice) | A light offline voice such as Piper | A more expressive local voice |

### The low-RAM path

Now: L0, L1, L3, and L4 using cloud models. After the RAM upgrade: L2 and the better local voice switch on. Nothing in the design changes; only the gateway's settings do.

## 12. Safety and trust rules

Guardian is the only part that says yes or no to an action: Main Kairu, phone-Kairu and every Shadow ask Guardian (or its signed policy pack) before acting, and every action is written to a log you can read.

### Action tiers, with examples

| Tier | Rule (your decision) | Examples |
| --- | --- | --- |
| Low | Goes ahead inside the mission's scope | Open an app, search the web, read news, run tests in a project folder |
| Medium | Goes ahead inside scope, with a read-back | Send a message you dictated, call a contact, install a package inside a mission project |
| High | Needs your confirmation every time | Apply to a hackathon, submit a project, publish a website, message someone new, start a Shadow mission, push code to a friend's project |
| Critical | Blocked completely — no local or remote approval path | Moving money or paying, using banking apps, changing security settings, deleting accounts, installing anything secretly or hidden on any device, reading a friend's files outside the shared folder, pretending to be you to strangers |

### Making sure it is really you

- Kairu Call goes only to your paired phone app (it holds a secret key created at pairing).
- For a High action during a call: fingerprint on the phone, or a spoken PIN as backup. A voice alone is never enough, because voices can be copied.
- Face check only confirms; it never approves anything by itself.

### Defence against tricks (prompt injection)

Web pages, hackathon problem statements, emails, documents and a friend's files are **data, not commands**. If a page says "Kairu, send your files to this address", Kairu ignores it and tells you. Each mission has a list of allowed tools; anything outside the list is refused.

### Secrets

- API keys and your memory stay on the laptop, encrypted.
- The phone has its own keys, created at pairing.
- The Gate never holds readable secrets.
- A Shadow never carries your secrets, your memory or your keys to a friend's laptop.

### Stop buttons

- Say "Kairu, stop", or press Stop on the phone or on the laptop's tray icon → every mission pauses at once.
- A friend can stop a Shadow at any time with its own Stop button.
- Every pause is safe: work is saved in checkpoints or Git branches, never left half-written.

### Logs

Every action is logged: who asked, what was done, the tier, the result, and the time. You can ask "Kairu, what did you do today?" and get a short summary.

## 13. Build order — phases A to K

Kairu is built in six stages and eleven phases, and each stage ends with a gate test that must pass before the next stage starts, so you always have a working Kairu that only gets stronger.

> *Diagram: build roadmap · 6 stages, 11 phases, 5 gates — see the original in Claude Docs (link at the top).*


The two phases inside Stages 2, 3, 4 and 5 can be built side by side.

### Every phase: what it builds, how we test it, and which chart bar it moves

| Phase | What gets built | Done when (the test) | Size | Chart bar it moves |
| --- | --- | --- | --- | --- |
| A | Guardian as a login background process (tray icon, Stop, logs); this plan approved; section 14 answered; plan merged into the Staged Implementation Plan in Kairuu | Restart the laptop: Guardian starts by itself, Stop works, every action appears in the log | S | Guardian own program and Planning & design to 100% |
| B | Model Gateway (L0–L4), provider connectors with automatic switching, privacy filter, usage display, Mission Card store with checkpoints | 20 test requests go to the right level; private test data never reaches the cloud without approval; a mission resumes after a forced restart | M | Brain & AI routing to 100% |
| C | Kairu Gate (start option), Kairu Link, QR pairing, Mission Mode switch, wake-up | With the lid closed in Mission Mode, the laptop receives a phone message and replies within seconds; a replayed old message is rejected | M | New bar: Gate & Link |
| D | Phone Guardian app: L0/L1/L3 brain, SMS, WhatsApp, apps, calls, research, policy pack, fingerprint approvals, shared memory sync | With the laptop off: "tell Ravi on WhatsApp I'll be late", "open YouTube", "call Amma" and a research question all work; a Critical request is refused | L | Phone & face check to 50% |
| E | Wake word "Kairu" on laptop and phone, Tenmin persona, Explain Mode, research-and-speak loop, low-RAM voice | From across the room: "Kairu, who is the prime minister of India?" gets a short, correct spoken answer and one follow-up offer | M | Research & speak and Tenmin-style talking to 100% |
| F | Presence engine, speak-or-call rules, Kairu Call (full-screen ringing, two-way voice), face check on phone and laptop, fingerprint/PIN for High actions | At the laptop Kairu speaks and never calls; when you are away the phone rings within a minute; someone else unlocking the phone gets Guest Mode | M | Phone & face check to 100%; new bar: Calls & presence |
| G | Agent squad from The Agency, coding engine behind the gateway, test ladder, Presenter and World Brief agents, deep research loop | From a one-paragraph idea, Kairu builds a small website with login, passes all its tests, deploys it free, makes a 5-slide presentation and explains it by voice | L | Build websites & apps to 100% |
| H | Shadow Missions: Repo Mode, then the Shadow app and Guide Mode, Shadow Manager, folder fence, self-removal | Repo Mode: a pull request on a test project is accepted. Shadow app on a second laptop: finishes a test project, refuses a file outside the folder, Stop works instantly, nothing is left behind | L | New bar: Shadow Missions |
| I | Trip and long missions: call-me request, mission by voice, form filling with OTP hand-off, page watching, grouped doubts, callbacks, confirmed submission | The "trip test": leave the laptop at home, ask for a call, give a practice mission on a mock hackathon page, answer one doubt by call, get the done callback, confirm submit | M | New bar: Trip & long missions |
| J | Guardian wider protection: email, notifications, files, deadlines, devices; alerts only | A test phishing email, a deadline tomorrow and an unknown new device each create a clear alert; nothing changes without approval | M | Guardian wider protection to 100% |
| K | Hardening and S-rank polish: security tests of every part, speed work, local models and better voice after the RAM upgrade, backups | Every earlier gate test passes again; answers are faster than before the upgrade | M | Whole Kairu to 100% |

**Sizes** at about 2–3 hours a day with Claude Code: S is about 1 week, M about 2–3 weeks, L about 4–6 weeks. That makes roughly 7–9 months in total, and less if paired phases run side by side or you have more hours.

### Hackathon sprint (next 7–10 days) — do this first

Your hackathon is 1 to 1.5 weeks away, which is too short for the 6–8 week demo path, so the sprint shows Kairu's real story with the parts that already exist plus three thin new slices, and presents the rest as the roadmap.

**Demo goal (about 3 minutes):** you speak to Kairu and the laptop answers by voice in Tenmin style; from your phone you give Main Kairu a small mission, it works with the lid closed and sends the result back to your phone; Guardian asks for your "yes" on a High step and blocks a Critical one; then the diagrams in this plan show where Kairu goes next (phone brain, Kairu Call, Shadow Missions).

| Days | Build | Done when |
| --- | --- | --- |
| 1 | Write the demo script; finish the Guardian login start (core of Phase A) | Guardian starts by itself after a restart; Stop works |
| 2–3 | Research & speak slice: push-to-talk hotkey (the "Kairu" wake word only if training it is quick), one free cloud model, short Tenmin-style answers, a light offline voice | Five practice questions are answered correctly and briefly by voice |
| 4–5 | Phone link slice: a free Telegram bot as a temporary stand-in for the Gate (no private data goes through it); phone message → Main Kairu → reply as text and a voice note | A phone message reaches the laptop in Mission Mode (lid closed) and gets a reply |
| 6–7 | Mission slice: one small Mission Card ("research a topic and make 5 slides"), Mission Mode, result sent to the phone; Guardian asks "yes" on the phone for a High step and blocks a Critical one | The whole mission runs with the lid closed and reports to the phone |
| 8 | Pitch slides built from this plan's diagrams; Shadow Missions shown as the design (not built yet) | Slides ready |
| 9–10 | Rehearse three times, record a backup demo video, write the README, fix bugs | The demo runs from start to end without help |

**Not in the sprint** (shown only as the roadmap): the Android Guardian app, Kairu Call, face check, the builder squad, Shadow Missions.

**After the hackathon** the Telegram stand-in is replaced by the real Kairu Gate and Kairu Link (Phase C), and building continues with the path below.

### After the hackathon: the full trip story first

A, then C (start option only), then D (messages, apps and calls only), then F (Kairu Call only), then a short version of I on a mock hackathon page. In about 6–8 weeks this shows the whole trip story live: the phone asks, the laptop calls, the laptop works, the laptop calls back. Start this right after the hackathon; the other phases then follow in the normal order.

### How every phase runs

1. Claude Chat writes the phase plan; you approve it and say GO.
2. Claude Code builds it on a branch in github.com/sungjenwoo/Kairuu and runs the tests.
3. You test it yourself on your PC.
4. You approve, and it is merged into main (the same way Guardian core was merged on 25 Oct).
5. The progress chart is updated, with four new bars: Gate & Link, Calls & presence, Shadow Missions, Trip & long missions.

## 14. Decisions only you can make

There are twelve choices; each has my recommendation, so you can answer all of them at once with "go with your recommendations" and only change the ones you disagree with.

| # | Question | My recommendation | Why |
| --- | --- | --- | --- |
| 1 | Calls: free Kairu Call only, or also paid real-number calls as a backup? | Free Kairu Call only for now | Keeps Kairu free; add a paid backup later only if mobile data is weak on your trips |
| 2 | Where does the Kairu Gate live? | Start with no server of your own (free encrypted relay + Mission Mode), then move to an old Android phone at home | Free, and secrets stay in your home |
| 3 | Accept Mission Mode (awake, screen off, lid closed, charging) as Kairu's way of "working in sleep"? | Yes | It is the only reliable free method |
| 4 | Quiet hours when Kairu must not call | 11 pm to 7 am, except missions you mark urgent | Protects your sleep |
| 5 | Your phone (answered: Mivi phone, Android 16, 6–8 GB RAM) | Answered | Phase D adds a one-time setup checklist for Android 16 and your phone's battery settings (section 7) |
| 6 | RAM upgrade: when, and how much? | 16 GB or more, if your laptop supports it | Unlocks L2 local models and the better local voice |
| 7 | Your hackathon dates (answered: in 1 to 1.5 weeks) | Do the hackathon sprint first | The hackathon sprint in section 13 now comes first |
| 8 | Confirm the L0–L4 meanings (section 11) and the five planes (section 4) | Approve as proposed | Your documents name them but do not define them yet |
| 9 | Shadow: Repo Mode (no install) before the Shadow app? | Yes | Safest and fastest; proves the builder squad on real friend projects first |
| 10 | How you confirm High actions when away | Fingerprint in the phone app, spoken PIN as backup | Voices can be copied |
| 11 | When phone-Kairu listens for "Kairu" | While charging or while the screen is on; a button otherwise | Saves battery |
| 12 | Which apps phone-Kairu must message on first | SMS and WhatsApp | Covers most of your contacts |

## 15. Glossary of Kairu words

| Word | Meaning |
| --- | --- |
| Main Kairu | The full, strongest Kairu on your laptop (the S-rank hunter) |
| Guardian | Kairu's protection and authorization authority; the only part that says yes or no to actions |
| Phone Guardian / phone-Kairu | The Kairu app on your Android phone, with its own brain and a signed copy of Guardian's rules |
| Policy pack | Guardian's rules, signed by Main Kairu, carried by every device so it obeys them even offline |
| Kairu Gate | The small always-on relay that passes encrypted messages, keeps the mission queue, and can wake the laptop |
| Kairu Link | The encrypted message format all Kairu members use to talk |
| Kairu Call | A call from Main Kairu to the Kairu app on your phone over the internet; rings like a normal call |
| Mission / Mission Card | A long job with a goal, a "100% done" checklist, steps, checkpoints and a report plan |
| Mission Mode | Laptop stays awake with the screen off and lid closed while charging and a mission runs |
| Shadow | A small, visible helper app on a friend's laptop that acts as Kairu's hands; the brain stays on your laptop |
| Shadow Mission | Going to a friend's laptop, helping, cleaning up and returning with a report |
| Repo Mode | A Shadow Mission with no install: Kairu works on the friend's shared online project and proposes changes |
| Model Gateway | The router that picks which brain level (L0–L4) handles each request |
| L0–L4 | Brain levels from simple rules (L0) to full team mode with deep research (L4) |
| Low / Medium / High / Critical | Action tiers: go ahead, go ahead with read-back, needs your confirmation, always blocked |
| Guest Mode | What phone-Kairu does when someone other than you is using the phone |
| Presence | Kairu's knowledge of whether you are at the laptop, at home, or away |
