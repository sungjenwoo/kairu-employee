# Kairu's memory (stage M1)

Tell Kairu what to remember, and it keeps the line **on this PC only**. Ask about it later and Kairu answers from the PC,
with no AI and nothing sent anywhere. Built on your GO of 14 Nov 2026 ("yes, remember"; memory answers on the PC only).

## Use it

| You say (typed or spoken) | What happens |
| --- | --- |
| `kairu ask "remember that my sister's name is Anu"` | "Got it, I'll remember that. It stays on this PC." Also "don't forget that ...", "note that ...", "keep in mind ..." |
| `kairu ask "what is my sister's name?"` | "You told me: my sister's name is Anu." Also "who is my ...", "when is my ...", "where is my ...", "do you remember my ..." |
| `kairu ask "what do you remember"` | Every line, newest first (the first 20). "what do you remember about my exam" shows only those |
| `kairu ask "forget about my sister"` | Deletes every line about those words and says how many. It cannot be undone |
| `kairu ask "forget everything"` | Deletes all of it. Also "clear your memory" |
| `kairu ask "remember that my otp is 482916"` | "I didn't keep that: it has a one-time code, and I never keep secrets." |
| `kairu ask --dry-run "remember that ..."` | Says it would stay on this PC. Nothing is kept or sent |

The same words work in the bar, in the workspace and by voice ("Kairu, remember that ...").

## How it works

```
"remember that X" / "forget X"  ─► Guardian decides brain.ask ─► the router: fixed rules, no AI
        ▼
   the brain reads X with the privacy filter: a secret is refused here, and nothing more happens
        ▼
   kairu/memory/conduct.py asks Guardian:   run memory.remember (Low)   or   run memory.forget (Medium)
        ▼
   the action reads X with the filter again, then changes data/memory.db

"what is my X" / "what do you remember"  ─► the brain only reads data/memory.db and answers (L0); nothing is sent
```

- **The brain changes nothing.** It only reads the memory. Keeping and deleting are two Guardian actions, each decided by
  `policy.yaml`, each with only a hash of your words in the audit log (`private: true`).
- **Nothing leaves this PC.** No file in `kairu/memory/` uses the network (a test reads the code to check). A line from
  memory is never added to a question that goes to a cloud AI, and an answer from memory is never kept as the "last
  answer" for a follow-up, so "tell me more" cannot carry it out either.
- **Secrets are never kept**: passwords, OTPs, keys, card and ID numbers. The filter reads the line twice: in the brain,
  and again in the action, so a request that skips the brain cannot store one.
- **Rules, not AI.** Kairu finds a line by its telling words: "what is my sister's name" finds lines with "sister" in them.
  The same question always gives the same lines, in your own words.
- **Who may use it.** You at the PC: everything. Your paired phone: "remember that ..." and "forget ..." only; Kairu does
  not tell the phone what it remembers, because that would send it off this PC. A Mission Card: nothing.
- **Limits:** 500 lines, 3 to 300 characters each, the same line once.

## Talk history (stage M2, 14 Nov 2026)

Kairu keeps your talks **by itself**: every answer you get at the PC (typed, in the bar, or by voice) is kept with your
question, **on this PC only** (data/brain.db), for 30 days, at most 300.

| You say | What happens |
| --- | --- |
| "what did I ask yesterday", "what did we talk about today", "show our chat history" | Your questions with the time and the start of each answer (the last 8). Nothing is sent |
| "what did I ask about solar panels", "did I ask about tea", "what did you say about black holes" | Only the talks with those words |
| "forget our talks", "clear the chat history" | All of it is deleted (`memory.forget`, Medium) |

- **Never kept:** a talk with a secret in it; questions about the memory or the history itself; what your phone or a
  Mission Card asks. `brain.talk_history: false` in config.yaml keeps nothing at all.
- **Never sent:** no talk is added to a question for a cloud AI, a search or the phone, and none reaches the audit log.
  Your history is told only at the PC.
- **Rules, not AI:** Kairu lists the talks; it doesn't yet use them to answer better ("as you asked yesterday ..."). That
  needs a model on the PC (after the RAM upgrade), so nothing personal leaves it.

## Proposed ADR items (for you to accept or change; the ADR register and the plan are not edited)

1. **Memory is a new stage, M1, built now** on your GO of 14 Nov, ahead of the plan's "Missions & memory" order.
2. **Two new actions in `policy.yaml`: `memory.remember` (Low) and `memory.forget` (Medium).** Forgetting cannot be undone,
   so it is Medium, like other deletes of Kairu's own things. Nothing else in the policy changed.
3. **Memory answers on the PC only** (your choice (a), 14 Nov). ADR-005 is untouched: no memory line goes to a cloud AI,
   not even with approval. Smarter use of memory waits for a local model (L2, after the RAM upgrade).
4. **`data/memory.db` is a plain SQLite file** in Guardian's data folder, like `workspace.db` and `brain.db`. Anyone who
   can read your Windows user folder can read it. Sealing it like the AI keys is possible later, if you want it.

## Smarter matching (stage M3, 15 Nov 2026, on the PC only)

Your GO of 15 Nov: "local only". Still rules, no AI, nothing sent; the same question always finds the same lines.

| You say | What Kairu finds |
| --- | --- |
| "who is Anu", "what do you know about Anu", "tell me about Anu" | Every line with "Anu" in it ("my sister's name is Anu", "Anu lives in Kukatpally") |
| "when is my mom's birthday" / "mummy's birthday" | "my mother was born on 5 June": mom, mum, mummy, amma and mother are one word for memory; so are born and birthday |
| "where does Anu live", "where does Ravi work", "what does my sister like" | The line with both words: lives/address/stay, works/job/office, likes/loves/favourite |
| "what is my favourite drink" (no line has both) | "I don't have that exactly. The closest I remember: ... I like tea": told as the closest, never as the answer |

- **Related words** (kairu/memory/store.py `RELATED`): family words in English, Hindi and Telugu (amma, nanna, akka, didi,
  bhai, ammamma, thatha ...), birthday/born, exam/test, phone/mobile, address/lives, job/works, college/school,
  like/love/favourite, doctor, meeting/appointment, deadline/due, medicine/tablet, wedding/anniversary. Endings come off
  ("likes", "liked", "liking" are one word).
- **A general question is never taken.** "who is X" is answered from memory only when a line has every telling word of
  the question; "who is the prime minister" or "what is the capital of France" go on as before.
- **"my dad's birthday" is never answered with your mother's.** A closest line must have the same person.
- **Forgetting stays strict.** "forget about my mom" deletes the lines about your mother (mom = mother), but never a
  "closest" line.

## Honest limits

- **It keeps only what you tell it to.** It does not yet learn from your talks by itself, and it does not keep a history
  of past conversations: that is the next part (M2), and it needs your decision on what a talk's history may hold.
- **It matches words and related words, not meaning.** "who is Anu" finds "my sister's name is Anu" now (M3); "who is
  the girl I told you about" does not. Real understanding needs a model on the PC (after the RAM upgrade).
  If it finds nothing, the question goes on as before (a personal one waits for your "yes" and PIN).
- **Anyone at your PC can ask.** The bar has no your-voice-only check yet (VOICE.md), so a person who says "Kairu, what
  do you remember" hears the first line and sees the rest in the bar. Do not keep what a guest must not see.
- **English.** The patterns are English words.
- **The phone has no memory of its own yet**; shared memory comes with the phone's later stages.

## The gate test (you, about 5 minutes)

1. `kairu ask "remember that my exam is on 20 Nov"`, then `kairu ask "when is my exam"`: the line comes back, with
   `(L0: answered on this PC, nothing sent)`.
2. `kairu ask "what do you remember"`: the list.
3. `kairu ask "remember that my otp is 482916"`: refused, and `kairu ask "what do you remember"` does not show it.
4. `kairu ask "forget about my exam"`, then `kairu ask "when is my exam"`: it no longer knows.
5. In the bar, mic on: "Kairu, remember that I like tea", then "Kairu, what do you remember".
6. `kairu audit show -n 20`: `memory.remember` and `memory.forget` runs, and none of your words.

Built and tested on the Linux build machine (tests_kairu/test_memory.py, 59 tests). **Not tried on Windows or by voice**:
your gate test is the real check.

## Files

```
kairu/memory/
  store.py     data/memory.db: the lines, and matching by words
  actions.py   memory.remember and memory.forget: the privacy filter again, then the change
  conduct.py   asks Guardian to run them (Orchestration; run, run_status, end only)
  recall.py    what Kairu tells from memory: reads only
kairu/brain/router.py    the words that reach the memory (rules only)
kairu/brain/gateway.py   memory(): refuses a secret, reads for "what do you remember", hands the rest on
```
