# Asking an AI website, and reading a page (browser eyes)

Built on Kairu's hands (`task-handling-hands`, BAR.md "Handling a task"), on your GO of 14 Nov 2026 ("both": Kairu reads
and clicks pages, and asks AI websites when told).

**Fixed before the first Windows run (15 Nov 2026):** Kairu's browser now starts with `--force-renderer-accessibility`
(without it Chrome often shows UI Automation only its own bars, so "read this page" would be empty), and the UI Automation
script answers in UTF-8 (em-dashes, quotes and other languages were garbled). **If Kairu's browser is already open, close
it once**, so it restarts with the new setting.

**Not tried on Windows yet.** Everything here was built and tested on the pretend PC only (tests_kairu/test_ask_ai.py).
The parts that touch a real browser (finding the page's question box, reading the page's words through Windows' UI
Automation) have never met a real Chrome or a real AI website. Expect the gate test below to find things to fix.

## Use it (in the bar, the workspace, or by voice)

| You say | What happens |
| --- | --- |
| "ask Claude what is photosynthesis" | Kairu's own browser opens claude.ai, Kairu types the question, presses Enter, waits, and shows "Claude says: ...". By voice it also says the first line and one follow-up question (Tenmin) |
| "ask ChatGPT about black holes", "ask Gemini ...", "ask Perplexity ...", "what does Claude say about tea" | The same, on that site |
| "ask Claude what I should tell my friend Ravi about his salary" | Personal words: the card asks for "yes" and your PIN first (`web.ask_private`) |
| "ask Claude what is photosynthesis and summarise it", "summarise what ChatGPT says about tea" | The same, then Kairu's own brain summarises the answer: "In short: ..." first, then what the site said. By voice it says the short version |
| "read this page", "what does the page say" | The words of the page in the browser in front, shown in the bar (the first 1,500 characters) |

**First, once for each site:** say "open claude.ai" (it opens in Kairu's browser), and **sign in yourself**. Kairu's browser
profile starts empty and keeps your sign-in after that. Kairu never types a password, an OTP or a CAPTCHA: if the page
shows a sign-in box, it types nothing and tells you.

## What it will and won't do

- **Only four sites, at fixed addresses**: Claude, ChatGPT, Gemini, Perplexity (`kairu/tasks/ask_ai.py`, `SITES`). Adding
  one is a change to that file, in a pull request.
- **Only Kairu's own browser profile** (`data/browser-profile`). Before typing, Kairu checks that the window's program was
  started with that profile. Your own Chrome window is never typed into.
- **The question passes the privacy filter**: a secret is never typed, not even with your PIN; personal words need "yes"
  and your PIN; public words go at once.
- **One question at a time, 15 seconds apart at least.**
- **The page's answer is data.** Lines that give orders ("Kairu, ...", "ignore your instructions") or hold a secret are left
  out, and nothing in the answer can become an order. It is shown to you and goes nowhere else.
- **Every rule of Kairu's hands still holds**: never Kairu's own windows, never a bank or payment page, typing stops if
  another window comes to the front, and Ctrl+Alt+K ends it within a second.

## Things you must know before using it

1. **The sites' rules are yours to check.** Some AI websites do not allow a program to use them, and can block or close an
   account. Kairu asks at a person's pace, with your own sign-in, one question at a time, but that does not make it
   allowed. Read each site's terms first. Kairu's own brain (`kairu ask`, Groq and Cloudflare's free APIs) answers the
   same questions without that risk.
2. **Your question leaves this PC**, to that website, under your account there. The site keeps it as it keeps anything
   you type there.
3. **The answer is only what the page shows.** Kairu reads the words after your question; on a page laid out in an unusual
   way it may read too much, too little, or the site's own buttons.

## Proposed ADR items (for you to accept or change; the ADR register and the plan are not edited)

1. **Three new actions in `policy.yaml`**: `web.read_page` (Low, read-only), `web.ask` (Medium), `web.ask_private` (High).
2. **`web.ask` is Medium for public words**, like `web.search` (public words typed into Google in Kairu's browser). The
   hands' rule is that Enter where it may send needs "yes" and your PIN; here Enter sends a question to an AI, which I
   treated as a search, not a message to a person. **If you want every question to an AI website to need your PIN, say so**:
   it is a one-line change of the tier.
3. **Accepted 15 Nov 2026: "ask Claude, then summarise" is built.** Only when you ask for it ("... and summarise it"), the
   answer as shown to you (orders and secrets already left out) goes to `brain.ask`, marked as page text, never
   instructions. The privacy filter reads all of it: personal words wait for "yes" and your PIN, a secret never goes. It is
   never searched for and never kept in your talk history. `web.ask` stays Medium (your choice: no PIN for public words).
4. **`ask-ai.last`** in the data folder holds only the time of the last question, for the 15-second pace.

## The gate test (you, about 15 minutes, after `task-handling-hands` is merged)

1. "open claude.ai" in the bar. Kairu's browser opens. Sign in yourself. Close nothing.
2. "read this page": the bar shows words from the page. **Tell me if it is empty**: that means Chrome did not give its page
   to UI Automation, and I need to fix how the page is read.
3. "ask Claude what is photosynthesis": the question appears in Claude's box, is sent, and the bar shows "Claude says: ...".
   Tell me what it shows, and how many seconds it took.
4. Sign out of Claude in Kairu's browser, then ask again: Kairu must type nothing and tell you to sign in.
5. With your **own** Chrome open in front and Kairu's browser closed, ask again: Kairu's browser opens and only it is typed into.
6. "ask Claude what should I tell my friend Ravi about his salary": the card asks for "yes" and your PIN.
7. Ask something and press **Ctrl+Alt+K** while it types: it stops within a second.
8. Mic on: "Kairu, ask Claude what is a black hole": the answer is in the bar and Kairu says one line and one question.
9. `kairu audit show -n 30`: `web.ask` runs, and none of your words.

## Files

```
kairu/tasks/ask_ai.py   the sites, the checks, the asking, reading a page (uses the hands; makes no key press itself)
kairu/tasks/pc.py       read_page and ask_box, on Windows and on the pretend PC
kairu/hands.py          two more UI Automation modes: `page` (the page's words) and `ask` (the page's question box)
kairu/tasks/skills.py   the orders; kairu/tasks/core.py: personal words become web.ask_private, and these steps get 100 s
kairu/bar/voice.py      an AI website's answer and a page read are spoken Tenmin's way; a refusal is not
```
