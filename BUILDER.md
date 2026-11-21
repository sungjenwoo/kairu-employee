# The Builder: Builder powers, Forge and Five Paths

ADR-050 (proposed). Kairu builds things, learns skills it doesn't have, and tries a big task five ways. Gemini thinks first
(`brain.build_providers` in config.yaml). Guardian still decides every step: the AI only writes drafts.

## Try it (the bar, or say it)

| You say | What happens |
|---|---|
| `build a website for Fresh Bakes, a bakery in Hyderabad` | Gemini writes the site. You see the files, type "yes", it is made in a new folder in your work folder and opens in your browser |
| `make a web app: a tip calculator` | The same for an app that runs in the browser |
| `make slides about Kairu for the Buildathon` | A slide deck (arrow keys to move), opened in the browser |
| `build a python app that converts temperatures` | A small Python program and its unittest tests. The tests run only after "yes" and your PIN, because an AI wrote the code |
| `test temperature-converter` (or `test the build`) | Run that program's tests again (yes + PIN) |
| `learn to make a study folder for physics` | Forge writes a skill, Guardian gives each step its tier, five dry runs on a stand-in laptop, then "yes" + PIN to keep it |
| `forge it` | Learn the last order Kairu said it can't do yet (within 10 minutes) |
| `make a study folder for biology` | Use the skill you kept: its plan is shown, and runs after your "yes" |
| `what skills have you learned` / `forget the skill make a study folder` | List them, or forget one (Medium) |
| `try five ways to put my pdfs in one folder, done when every pdf is in pdfs` | Five plans, rule checks, a judge's scores, best first. Nothing runs yet |
| `run path 2` / `run the best path` | Only that plan, shown and run like any plan (within 30 minutes) |

The Builder's orders work at Main Kairu's own PC only.

## How it works

```
your order ─► a Builder order? (kairu/build/conduct.py)
   build ...      build.draft (Low) ─► Gemini writes files ─► read strictly ─► data/builder.db (a draft)
                  ─► you see the files ─► "yes" ─► build.write (Medium): exactly those files (same sha256), a NEW folder
                  ─► files.open index.html (Low)            or, for Python: build.test (High: yes + PIN)
   learn to ...   forge.draft (Low) ─► a recipe of KNOWN skills ─► Guardian decides every step (Critical: no skill)
                  ─► forge.test (Low): 5 dry runs on a stand-in laptop ─► 5 of 5? ─► forge.save (High: yes + PIN)
   try five ways  paths.draft (Low) ─► 5 plans + a judge ─► rule checks (Guardian, the fence) ─► best first ─► you pick
   run path N     that plan ─► shown ─► "yes" ─► Guardian decides each step as it runs
```

## The rules it keeps

- **The AI only writes drafts.** Every step that changes something is a Guardian action with its own tier. A draft is made,
  tried or kept only with the sha256 of exactly what you were shown; a draft changed in data/builder.db is refused.
- **Builds stay in their own new folder** in your work folder, never over anything (the fence and `open(..., "xb")`). File
  kinds: .html .css .js .svg .json .md .txt for pages; .py .md .txt .json .csv for Python.
- **A built page never reaches the network by itself.** No remote script, style, picture or frame, no fetch,
  XMLHttpRequest, WebSocket, beacon, eval, `new Function`, cookies or redirects. A link you click (`<a href="https://...">`)
  is fine. Pictures are shapes, gradients and emoji.
- **Built Python stays in its folder.** Only the standard modules in `kairu/build/make.py` IMPORTS and its own files; no
  open(), eval, exec, getattr, os, sys, subprocess, socket, urllib or dunder tricks. Its tests run only with build.test (High)
  and only while every file is exactly as build.write made it, with no other .py file added.
- **No secrets.** The privacy filter's backstop reads every file of a build. A brief with personal words is not sent
  (the same as brain.plan), and a secret never leaves the PC.
- **A recipe can never raise a tier.** It is only Kairu's known skills (never a command). Guardian decides each step
  before the dry runs (a refused or Critical step, or two High steps: no skill) and again every time it runs.
- **Dry runs touch nothing here.** forge.test runs the skills' own code against a pretend PC (kairu/tasks/pc.py StandIn),
  with its own empty work folder and data folder, in a temporary folder that is deleted after. The stand-in has every app
  and button a recipe names: a dry run proves the steps are whole and keep the rules, not that a real window has that button.
- **Built-in skills come first.** A recipe whose order a built-in skill already answers is refused, and a kept recipe that
  was changed by hand is never used.
- **Only the path you pick runs.** Dropped paths are listed with the reason.

## Gemini

`config.yaml`:

```
brain:
  build_providers: [gemini, groq, openrouter]   # Gemini first, then Groq, then Gemma on OpenRouter
```

Add the Gemini key once with `kairu provider add gemini` (the same key Gemini hearing uses). Without `build_providers`, the
Builder asks `brain.providers`. Gemini's free tier may use what is sent to improve Google's products, which is why only
public briefs go.

## Files

```
kairu/build/
  conduct.py   the orders, and the order in which Guardian is asked (TaskCore.handle calls it)
  make.py      Builder powers: build.draft, build.write, build.test; what a build may be
  forge.py     Forge: forge.draft, forge.test (dry runs), forge.save, forge.forget; what a recipe may be
  paths.py     Five Paths: paths.draft (five plans and the judge)
  store.py     data/builder.db: drafts, builds, recipes, kept skills, five paths
tests_kairu/test_builder.py           the rules, without Guardian
tests_kairu/test_builder_program.py   the same orders through the real Guardian program
```

## Laptop test (about 15 minutes)

1. `py -3.12 -m kairu provider add gemini`, then in config.yaml under `brain:` add `build_providers: [gemini, groq, openrouter]`.
   Restart Guardian (`py -3.12 -m kairu guardian quit`, then `py -3.12 -m kairu guardian run`) and the bar.
2. Bar: `build a website for Fresh Bakes, a bakery in Hyderabad` → you see the files → `yes` → the page opens in the browser.
3. `make slides about Kairu for the Buildathon` → `yes` → arrow keys move between slides.
4. `build a python app that converts temperatures` → `yes` → the PIN card for its tests → the tests pass.
5. `learn to make a study folder for physics` → "5 of 5 passed" → the PIN card → "Learned ...". Then
   `make a study folder for biology` → the plan → `yes` → the folder is in Kairu-files.
6. `try five ways to put my pdfs in one folder` → five paths, best first → `run the best path` → `yes`.
7. `py -3.12 -m kairu audit show -n 30`: build.*, forge.* and paths.draft runs, and none of your words.

## Not built yet

- Sharing a forged skill with the Clones (each laptop approving it with its own PIN).
- The lessons of the four paths that lost going to Forge.
- Gemma on the laptop itself (L1). Today Gemma is reached on OpenRouter.
- The Cloud Run, Pub/Sub and Firestore team layer (the roadmap in the pitch).
