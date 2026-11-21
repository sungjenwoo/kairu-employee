# Kairu "Ask Anything": run it on your laptop

One page to try everything built for the Tenmin use case (14 Nov 2026): speak, think, research, browse, remember.
Each part has its own page with the full rules and gate test: RESEARCH.md, MEMORY.md, ASK.md, BAR.md, VOICE.md.

## 1. Get it

After you merge the pull request "Tenmin use case: everything in one branch", on your PC:

```
cd C:\Users\saitej\Kairu-guardian
git pull
py -3.12 -m pip install -e .
py -3.12 tools\check_guardian.py
```

Then restart Kairu (tray > Stop, then sign out and in, or start Guardian and the bar as you usually do).
`kairu status` should say `research: on`. If it says off: `research.enabled: true` in config.yaml.

## 2. Try it (type in the bar, or mic on and start with "Kairu, ...")

| Say | What you should see |
| --- | --- |
| who is the prime minister of India | A short answer, then one follow-up question (Tenmin) |
| what is the weather in Hyderabad today | A web search, then a short answer with sources |
| research deeply how solar panels work | 3 searches, then a short report with [1] [2] sources. "sources?" shows the links |
| remember that my exam is on 20 Nov | "Got it, I'll remember that. It stays on this PC." |
| when is my exam | "You told me: my exam is on 20 Nov." Nothing is sent anywhere |
| what do you remember / forget about my exam | The list / it is deleted |
| open chrome, then: on search bar type instagram, then: search | Omesh's hands: each order carries on in Chrome |
| open claude.ai | Kairu's own browser opens Claude. **Sign in yourself, once.** |
| ask Claude what is photosynthesis | Kairu types it into Claude, sends it, and shows "Claude says: ..." |
| read this page | The words of the page in the browser in front |

High steps (sending, personal words, anything risky) still show the card: type "yes" and your PIN. A spoken yes never counts.
**Ctrl+Alt+K** stops everything within a second.

## 3. Tell Claude what happened

For each line above: worked, or what it showed instead (a screenshot is best). These parts have **never run on Windows**
before; the most likely to need a fix are "ask Claude" and "read this page" (they read Chrome's page through Windows UI
Automation) and the timing of deep research.

## New on 14 Nov night: the voice and the talk history

```
kairu voice try --voices   # every voice says one line: pick the one you like (the new default is uk-jenny)
kairu voice try            # the four styles: warm (default), lively, calm, plain
```

Then, in the bar: ask two or three questions, and say "what did we talk about today", "what did I ask about tea",
"forget our talks". VOICE.md "How Kairu sounds" and MEMORY.md "Talk history" have the details.

## New on 15 Nov: Kokoro, the human-sounding voice

```
py -3.12 -m pip install -e .[kokoro]
py -3.12 -m kairu voice setup
py -3.12 -m kairu voice try --voices
```

Pick a voice, put `kokoro_voice: <name>` under `voice:` in config.yaml, restart Guardian. After Kairu asks its follow-up
question, just answer: it listens 8 seconds without "Kairu". VOICE.md "Kokoro" has the details.

## New on 15 Nov: what was left, built

| Try | What you should see |
| --- | --- |
| remember that my sister's name is Anu, then: who is Anu | "You told me: my sister's name is Anu." (memory M3, MEMORY.md) |
| remember that my mother was born on 5 June, then: when is mummy's birthday | "You told me: my mother was born on 5 June." |
| ask Claude what is photosynthesis and summarise it | "In short: ..." then "Claude says: ..." (ASK.md) |
| set `listen_at_start: true` under voice: in config.yaml, then `kairu bar quit`, `kairu bar` | The mic comes on by itself and waits for "Kairu" (again after you unlock the PC) |
| set `barge_in: true`, ask a question by voice, and say "wait" while Kairu answers | Kairu stops talking; the answer stays in the bar |
| set `live_caption_every: 0.20` under voice:, restart Guardian, then say "Kairu, open Notepad" slowly | The words appear in grey as you speak, then turn white when you stop (VOICE.md "Live words") |
| with live words on, say "Kairu, open Edge" | Edge starts about 0.2 s after you stop speaking plus the app's own start, not 3-5 s (VOICE.md "Quick orders"); turn on Edge's Startup boost too |
| `kairu voice setup`, `fast_orders: true` under voice:, restart Guardian, say "Kairu, open Edge" | The grey words appear word by word; Edge starts about 0.3 s after you stop (VOICE.md "Fast orders") |
| `kairu voice enroll`, `only_my_voice: true`, restart Guardian; then let someone else say "Kairu, open Notepad" | The bar says "That didn't sound like your voice"; yours still works; "Kairu, stop" works from anyone (VOICE.md "Only your voice") |
| `py -3.12 tools\pin_whisper.py`, then `engine: whisper-large-v3-turbo` under voice:, then `kairu voice setup` | The top hearing model (about 1.6 GB). Commit kairu\voice\whisper_pins.json. VOICE.md "The top hearing model" |

## What is still not built

- **A voice exactly like Tenmin's**: Kokoro is close, but Tenmin uses a bigger cloud voice; Kairu's stays on your PC.
- **Starting to speak while the AI is still writing**: not picked (15 Nov).
- **Understanding meaning in memory**: related words work now ("who is Anu"); real meaning needs a model on the PC.
