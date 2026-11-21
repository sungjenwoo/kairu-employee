# The Kairu workspace (W1 and W2, Plan v2.0 sections 4b and 4b-2, ADR-030 and ADR-036)

One home window for everything Kairu does, inspired by Claude's own app. All your projects and missions are on the left,
the mission you have open is in the middle, and the steps that run and Guardian's approval card are beside it. The bar
stays the quick way in; the workspace is where the work lives.

It holds no authority. An order typed here goes to the same task core as the bar, so Guardian decides every step: Low
and Medium run, High waits for `yes` and your PIN on the card, Critical is refused, and an unknown action is denied.

## Start it

```
kairu workspace            start it and open its window (if it already runs: one more window)
kairu workspace quit       end it; Guardian and running actions carry on
kairu workspace status     is it running?
```

Guardian must be running for orders to run (`kairu guardian run`); without it, the window opens and says
`Guardian off`. The window is your installed Chrome or Edge as an app window, with a profile of its own
(`workspace-profile` in Guardian's data folder): never your own browser profile, and not the profile `web.open` uses.
With neither installed, your default browser opens it. `workspace.log` in Guardian's data folder says what went wrong
if it doesn't start.

## In the window

| Part | What it does |
| --- | --- |
| **New mission** | A fresh start. Type an order and press Enter; the mission takes its first words as its title |
| **Search** (Ctrl+K) | Finds missions by their title or anything said in them |
| **Projects** | Each project with its missions (the arrow opens it). **+ New** makes one. A project has a name, your own notes, and its missions; you can rename it, archive it or delete it (its missions stay, under Recent) |
| **Recent** | Your newest missions, in any project or none. A red dot shows the one that's running |
| **Guardian, Clones, Shadows, Devices** | Guardian's state, how it decides, and its monitors' open alerts and deadlines; what a Clone and a Shadow are (they do nothing yet); your paired phones |
| **Stop** (top right) | The same as `kairu stop` and Ctrl+Alt+K: every running action halts within a second, then Safe Mode until `kairu resume`. Typing `stop` or `Kairu, stop` does the same |
| Middle | Your orders, each finished step with a tick or a cross, and Kairu's short answer |
| **Progress** (right) | The steps of the order that runs, as they run |
| **The card** | Above the box you type in, when Guardian asks: the action, its details and tier, a `yes` box and, for High, a PIN box |
| **No project / In …** | Under the box you type in: which project a new mission goes in, or, in a mission, move it to another |
| **Files** (right, W2) | The files and folders this mission's finished steps made, changed, opened or put in the Recycle Bin, newest first. **Open** and **Show** send the same order as typing `open the file "…"` or `show "…" in its folder`, so Guardian decides them, and the order shows in the mission |
| **Mic** (W2) | Beside the send button, with `voice.enabled`. Click it or press **Ctrl+M** while the window is in front |
| **The glass bar** (W2) | Ember Glow, above the box: blue with your words while Kairu listens, red with the step and how far it has got while it works, a short white "Done", and gone when there is no work. The logo's ring turns blue or red with it |

Kairu works on one order at a time, as in the bar. Another order while one runs gets "Kairu is still on the last order";
`stop` always works.

**The card's two boxes are filled only by your own typing.** The page's code only reads them and empties them, and never
presses their buttons; a test reads the code to check. Your answer goes to Guardian with `GuardianClient.approve`, as in
the bar, and then the server forgets it; it never keeps or shows what you typed. A card nobody answers in 110 seconds
ends as a refusal. The PIN box shows dots, and the browser isn't asked to remember it.

## Files a mission made (W2)

Three file skills came with W2 (BAR.md has the full list), all inside your work folder only:

- `make a file called notes.txt saying buy milk` (`files.write`, Medium): a **new** text file; it never overwrites, and `undo`
  puts it in the Recycle Bin if you haven't changed it since. Its words stay out of Guardian's log (a hash only).
- `open the file notes.txt`, `open notes.txt`, `open the folder Reports` (`files.open`, Medium): with its own app, through
  Explorer. Documents, pictures, sound, video, text and .zip only: a program, script or shortcut is refused by its kind, so
  opening a file never runs code.
- `show notes.txt in its folder` (`files.show`, Low): Explorer, with it selected.

The Files panel lists the names the steps themselves named (a rename's new name, a move's folder, a made, opened, shown or
recycled file). It never reads your disk to find them, and a step that wasn't done names nothing. The list is kept with the
mission in `data/workspace.db` and goes when the mission is deleted.

## Voice in the workspace (W2)

With `voice.enabled` (VOICE.md), the workspace has the bar's mic. Every rule of the bar's voice holds here:

- **The mic is off** every time the workspace starts. Only your own click on its mic button, or your own **Ctrl+M** in the
  window, switches it on: those two are the only places in the page that ask the server, and `Workspace.mic_pressed` is the
  only code there that switches it (a test reads both).
- **What you say goes into the mission open in the window**, through the same task core, so Guardian decides every step. On
  the home page or a project page, it makes a new mission there, and the window opens it.
- **Voice never approves.** A High step opens the card, and only your typed `yes` and PIN answer it.
- Kairu answers questions aloud, Tenmin's way; finished tasks stay quiet. "Kairu, stop" stops everything.
- **The mic goes off** on Stop and every emergency stop, when the PC locks or sleeps, when no workspace window has been open
  for 15 seconds, and when the workspace ends. The window keeps asking the server while it is minimized (it is started with
  Chrome's background timers on), so only really closing it counts.
- **One mic.** The bar and the workspace share the voice link: whichever switched its mic on first has it while it is on, and
  the other says so. Switch it off there first.

`open the workspace`, typed or said in the bar, opens this window (starting the workspace if it isn't running). In the
workspace itself it answers "You're in the workspace already."

## What is kept, and where

Projects, missions and what was said in them are in `data/workspace.db` on this PC (readable by you only on Linux). They
never go into Guardian's audit log and are never sent anywhere. Deleting a mission deletes what was said in it. Nothing
in this file is a permission: Guardian never reads it.

## Who can talk to it

The server listens on 127.0.0.1 only, on a port picked at each start. Every API call must carry the key made for that
start, and its Host must be the server's own address, so no web page in any browser can reach it, even through a name
that points at 127.0.0.1. The key is in `workspace.json` in Guardian's data folder (yours only) and in the window's
address after the `#`, which never goes over the network; the page hides it from the address bar at once. The page has a
strict Content Security Policy (its own script and style only, nothing from the internet) and shows every name, order and
answer as plain text, never as markup.

It does not keep out a program that already runs as you, which could also type into the bar. That is why the PIN stays
Guardian's: a request with the key still can't approve anything without your PIN.

## Built with

The standard library only: `http.server` for the server, `sqlite3` for the store, and the browser Windows already has
for the window. No new dependency (no Tauri, Electron or pywebview). The task core gained an optional `progress` hook that
the workspace uses to show steps; it only hears, so it can never change what runs.

## Later in the app

Built in W2: the Ember Glow look, the Files panel, voice inside the workspace, and "open the workspace" from the bar. Still
to come: the Clones and Shadows pages working (with Clones, and with Phase H), and voice that acts while you are still
talking in the workspace's own glass bar (as the bar's voice does: each order runs as soon as you pause).

## The gate test (W1)

On your PC, with Guardian running (`kairu guardian run`):

1. `kairu workspace`: the window opens and shows `Guardian on` at the bottom left.
2. **Projects → + New**: make "Gate test". It shows on the left. Rename it to "Gate test 2": the left side follows.
3. In the project, type `open Notepad and set volume to 20`: Notepad opens, the volume is 20, both steps show with a
   tick, and the mission shows under the project on the left.
4. Type `close Notepad` in the same mission: Notepad closes (if it asks to save, that's Notepad).
5. Type `restart`: the card opens. Press **Refuse**: "Not done: you refused it." and nothing restarts.
6. Press **Stop**: Guardian goes to Safe Mode (`Safe Mode` at the bottom left). Run `kairu resume`.
7. Close the window, then `kairu workspace` again: every project and message is still there.
8. In PowerShell, `curl.exe http://127.0.0.1:<port>/api/state` (the port is in `workspace.json`): it answers
   `401`, because it has no key.
9. `kairu workspace quit`, then `py -3.12 tools\check_guardian.py`: every test passes.

## The gate test (W2)

After W1's gate test, on your PC, with Guardian running and `voice.enabled: true`:

1. In a mission, type `make a file called gate.txt saying hello`: one step with a tick, and **gate.txt** under **Files** on
   the right, "Made".
2. Press **Open** beside gate.txt: Notepad opens it. Press **Show**: Explorer opens with gate.txt selected. Both orders show
   in the mission.
3. Type `open file notepad.exe`: "Refused: Kairu never opens programs, scripts or shortcuts …", and nothing opens.
4. Type `undo`: "Undone: gate.txt is in the Recycle Bin."
5. Click the **mic** (or press Ctrl+M). Say "Kairu, open Notepad and set volume to 20": the glass bar turns blue with your
   words, then red with each step, then "Done"; both steps show in the mission.
6. Say "Kairu, who is the prime minister of India?": the answer is spoken, short, with one follow-up question.
7. With the mic on here, click **Mic** in the Kairu bar: it says the mic is on in another Kairu window. Click the workspace's
   mic off, then the bar's mic works.
8. Switch the workspace's mic on again and close the window: within about 20 seconds the mic is off (open the window again
   with `kairu workspace`: the mic button is off).
9. In the Kairu bar, type `open the workspace`: the window opens. While Kairu works on an order, the bar shows the red ember
   line under its box.
10. `kairu workspace quit`, then `py -3.12 tools\check_guardian.py`: every test passes.
