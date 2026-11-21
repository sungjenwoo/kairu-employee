# Kairu Clones: Main Kairu and its team (ADR-043, ADR-048 and ADR-049, proposed)

A **Clone** is a full Kairu on a teammate's laptop. **Main Kairu** (the manager's PC) splits a project into tasks, hands
each Clone its orders, follows what each Clone says, hands the next task on when the ones it waits for are done, and shows
the manager one board with progress and the tasks that are slipping.

```
Main Kairu (manager)                         Clone (Ravi's laptop)                     Clone (Anu's laptop)
kairu team split "brief" --hours 6           its own Guardian, bar, PIN                its own Guardian, bar, PIN
kairu team start ──── order [K1.1.1] ──────▶ task core ─▶ Guardian decides each step
       ▲  board  ◀── "[K1.1.1 finished] …" ─ link.send                                ◀── same, for Anu's tasks
       └─ task 3 waits for 1 and 2, then goes to Anu ─────────────────────────────────▶
```

## How it is safe

- **Towards a Clone, Main Kairu is a paired device, exactly like your phone.** The Clone's owner pairs it at the Clone with
  `kairu device pair` and its 6-digit code. Every order is a D4 mission (`task.order`): a *request* that the Clone's own
  Guardian decides step by step. Low and Medium go; **High waits for "yes" and the PIN typed on that laptop**
  (`kairu link approve N` there); Critical is refused there as everywhere. Main Kairu can never approve anything on a Clone.
- **A Clone's words are data.** Its reports are kept in Main Kairu's `data/team.db` for the board, never handed to Guardian, to
  an AI or to another Clone. A report moves a task only when its tag names that Clone's running task and step.
- **The split is only words until you start it.** `team.split` uses the brain like a free-form plan: the same privacy filter
  (a secret is never sent, a brief with personal words is not sent), free providers only. The answer is read strictly
  (kairu/team/split.py): JSON only, at most 8 tasks of at most 4 short orders, only Clones you added, a task may wait only for
  earlier tasks, and no order may carry a PIN, a password or a "yes".
- `team.add` is High ("yes" and your PIN on Main Kairu), `team.run`, `team.remove`, `team.set` and `team.move` are Medium,
  `team.split` and `team.status` are Low. On a Clone, `team.note` (Low) keeps Main Kairu's notes in its inbox.
- **Main Kairu's notes are its own words.** A welcome, a hand-off or a heads-up is built only from Main Kairu's data (the
  project's name, the task titles of the split you saw, Clone names, times), never from what another Clone said.
- `kairu stop`, Ctrl+Alt+K and the tray's STOP end a running project with everything else. On a Clone, its own stop ends
  its part.
- The `kairu` command and the Guardian program still never load PyNaCl: Main Kairu's side uses kairu/link/testclient.py's
  standard-library crypto. Its keys for each Clone are in `data/team/<name>.json`, sealed with DPAPI for your Windows account
  (a file from before the seal is read once and written back sealed); on Linux, readable by you only.

## Set it up (about 5 minutes per Clone)

On the **Clone's laptop** (Kairu installed, Guardian running, `link.enabled: true` in its config.yaml):

```
kairu team join Ravi-laptop
```

It is `kairu device pair` (yes and that laptop's PIN) and prints the exact line for the manager, with the 6-digit code (valid
10 minutes). The teammate sends it to the manager themselves (chat or in person). On **Main Kairu**:

```
kairu team add Ravi-laptop "kairu-pair:1:..." 123456 --skills "writing, design"          yes and your PIN
kairu team add Anu-laptop  "kairu-pair:1:..." 654321 --share 2 --skills "research"       twice the work
kairu team list
kairu team set Anu-laptop --skills "research, testing"     change a share or skills later (Medium)
```

Skills are the manager's words (letters, digits and , . & + / # -, 120 at most). They only tell the split who fits a task.

**One laptop only (for a demo):** Main Kairu can also be its own Clone: run `kairu device pair` in one PowerShell and
`kairu team add Me "kairu-pair:1:..." CODE` in another, on the same PC. Its orders then run in your own bar's task core.

## Run a project

```
kairu team split "Build a one-page website for Fresh Bakes: a homepage text, three menu items, research two competitor sites" --hours 4
kairu team show          the plan: each task, its Clone, its orders, what "done" means
kairu team start         the Clones get their orders
kairu team show          or the workspace's Clones page: it updates every 3 seconds
```

The split gives each task to the Clone whose skills fit, balanced by share and by the minutes each Clone already has in
unfinished projects, and shows the work per Clone against its share. If one has too much, move a task before you start:

```
kairu team move 3 4 Anu-laptop       project 3, task 4 goes to Anu (only a task that hasn't started)
```

From the bar or by voice, at Main Kairu's own PC: **"split the project: a one-page site for Fresh Bakes, in 4 hours"**,
**"start the project"**, and **"how's the project going?"** (also "project status", "are we on track"). An order from a phone,
or from Main Kairu to a Clone, never splits or starts a project there.

Each Clone does one order at a time. A task's next order goes when its last one finished; a task that waits for others
starts when they are done (the hand-off). A finished step whose words say it was refused or not done marks its task
**blocked**; `kairu team start` again tries it once more from that order. A run ends by itself when every task is done
(**done**) or nothing more can go on (**stuck**), and after 12 hours at most.

**Slipping.** The plan: from the start, each Clone does its tasks in order, each takes its minutes, and a task starts when
the ones it waits for are done. A task that isn't done is *slipping* when its planned end has passed, or when at its pace it
would end after the deadline. The project is *at risk* when the expected end is after the deadline.

## Talk and sync

- **Main Kairu's notes ride on orders.** A Clone's first order of a project carries a welcome (the project, its due time, that
  Clone's tasks); the first order of a task that waited for others carries the hand-off ("task 1 'Copy' (Ravi) and task 2
  'Research' (Anu) are done, so your task 3 'Review' starts now"); and when a task slips, its next order carries a heads-up.
  On the Clone the note is taken off before the task core sees the order and kept in its team inbox (`kairu team inbox`, and
  the Clone's own workspace Clones page, "From Main Kairu"). A note never goes as a message of its own, so it can never bump
  an order (a Clone runs one order at a time).
- **A Clone can tell the team something:** `kairu team say "the logo is ready"` on its laptop (Guardian's link.send to its
  paired Main Kairu). On Main Kairu it goes on the board's team feed, nothing more: never an order, never moves a task even if
  it holds a tag, never passed to another Clone or an AI. It is read while a project runs.
- **Hand-off:** a task that waits starts the moment the tasks it waits for are done, on its own Clone, with its note.

## The manager's view

`kairu team show` and the workspace's **Clones** page (every 3 seconds):

- the progress bar (orders done) and under it the **deadline bar** (time used since the start); it turns red when time used is
  more than 10 points ahead of the work done;
- each Clone: share, skills, when it was last heard from, tasks done of its tasks, minutes left, the task it is on;
- each task: ▶ working · waiting ✓ done ! blocked, its orders, what "done" means, what its Clone last said, **SLIPPING**, and
  **SILENT** when its Clone has said nothing for 10 minutes while it works;
- the project: **AT RISK** when the expected end is after the deadline;
- the **team feed**: Main Kairu's notes (welcomes, hand-offs, moves, "task 3 is slipping") and what the Clones said.

"How's the project going?" answers from the same board in two short sentences and one question (Tenmin), by rules.

## Growth: good work gets seen, and a person decides (ADR-049)

Main Kairu keeps a **growth record** for each Clone, by rules from team.db (no AI): tasks delivered; early, on time or after
plan (a task's real time, first order sent to last order done, against its planned minutes; on time is within 10% or 5
minutes); tasks that let others start; tasks finished after being blocked (what the person at that laptop added); tasks the
manager checked (`kairu team check P T`); and kinds of work (research, writing, design, testing, building, data, docs, from the
task titles).

```
kairu team growth                  each Clone on its own, suggestions for you to decide, and offers
kairu team check 3 2               you confirm task 2 of project 3 met its "done when" check (Medium)
kairu team offer Anu "Lead the next research task"     (Medium)
```

The safe version, by design:

- **Tasks, not people.** Every entry says what a task did ("Task 3 'Research' was delivered 12 min early; it let 2 other
  tasks start"), never how fast or hard a person works. A task's time includes the Clone's own work and any wait.
- **No score, no ranking.** No totals across people, no "best", and the Clones are always listed by name.
- **The employee sees everything recorded about them.** Each entry (and the manager's check) waits in that Clone's queue and
  rides on its next order, in this project or a later one, so it reaches that laptop's inbox. On the Clone:
  `kairu team record`. The manager's view says how many entries are still waiting to reach each laptop.
- **The manager decides; the employee accepts.** A suggestion appears only for a kind of work with 3 or more tasks delivered
  early or on time and none after plan, and only as "Suggestions for you to decide (Kairu never assigns or promotes)". An
  offer is the manager's own words (no PIN, password or brackets), reaches the person with their next order, and only that
  Clone's answer counts: `kairu team accept N` or `kairu team decline N` on their laptop (Guardian's link.send).
- The workspace's Clones page shows the growth record, the suggestions and the offers.



The orders are the bar's own orders, the ones it already knows: open or close an app, type in an app, save in an app, make a
text file, open a file, google something, open a site, research or ask a question. A free-form order that needs a plan is
not run on a Clone (a plan needs a "yes" at that laptop's bar, which a request from another PC can't give); it comes back
as "Not done" and the task is blocked.

## The Clones test (you, about 15 minutes; one laptop is enough)

1. On the laptop: `kairu team join Me`; in a second PowerShell: the `kairu team add Me "<offer>" <code>` line it printed, with
   `--skills "writing"` on the end → yes + PIN → "Me is now a Clone". `kairu team list` shows the skills.
2. `kairu team split "Make a short note about Hyderabad's best bakeries and open it" --hours 1` → a plan with 1–3 tasks for Me.
3. `kairu team start`, then open the workspace (`kairu workspace`) → **Clones** page: the tasks go ▶ working → ✓ done, the
   bar shows the steps as they run, and each task shows what the Clone last said.
4. Split something with a High step (e.g. "… then delete the note"): the step waits; `kairu link waiting` and
   `kairu link approve N` with yes + PIN on the Clone let it go on; refusing blocks the task.
5. `kairu stop` while a project runs: everything ends; `kairu resume`, `kairu team start` goes on.
6. With a second laptop: the same with `kairu team join Ravi` there, and watch the hand-off on the board.
7. ADR-048: in the bar, "how's the project going?" → two sentences and a question. `kairu team inbox` on the Clone → the
   welcome (and a hand-off, if a task waited). `kairu team say "the note is ready"` on the Clone while a project runs → it shows
   in the team feed on Main Kairu. Split something with 3+ tasks, then `kairu team move N 3 Me` before starting.

## Files

| File | What |
| --- | --- |
| kairu/team/store.py | data/team.db: Clones, projects, tasks, what each Clone last said |
| kairu/team/split.py | the brain's instructions for a split, and the strict reading of its answer |
| kairu/team/peer.py | Main Kairu's side of the Link to one Clone (pair, send an order, read its news), the step tags |
| kairu/team/conduct.py | the actions team.add, team.remove, team.split, team.run (the Runner) |
| kairu/team/board.py | the team board: progress, slipping, at risk |
| kairu/team/commands.py | `kairu team ...` |
| kairu/tasks/remote.py | the Clone's side: takes the tag (and Main Kairu's note) off an order and puts the tag back on its reports |
| kairu/team/inbox.py | the Clone's team inbox: Main Kairu's notes (team.note), data/team-inbox.json |
| kairu/workspace/page.html | the Clones page |
| tests_kairu/test_team.py | the split, the tags, the runner, the board, and an order over the stand-in Gate |
| kairu/team/growth.py | the growth record, by rules: entries, counts per Clone, suggestions for the manager |
| tests_kairu/test_team_growth.py | the growth record's safe version: tasks not people, no ranking, the queue, offers and answers |
| tests_kairu/test_team_sync.py | skills and workload, moving a task, notes on orders, the slip watch, say, the inbox, sealed keys, the manager's view, the team orders |

## Not built yet, and known limits

- The Clones talk through Main Kairu (the hub), not directly to each other; a Clone's words reach the manager only.
- A Clone's own workspace shows its inbox (Main Kairu's notes), not the whole team board.
- An offer and a record entry reach a Clone only with an order; an answer to an offer is read while a project runs.
- `kairu team say` is read only while a project runs; a heads-up can't reach a Clone on its last order (the board still shows it).
- Plans (free-form orders) don't run on a Clone, as above.
