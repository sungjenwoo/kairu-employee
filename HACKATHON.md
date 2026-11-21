# Hackathon: Kairu Employee

**Brief:** build an AI employee that converts meetings into actual completed work. The judges stress
**cross-meeting memory** and **conflict detection**; a simple meeting summarizer is not enough.

**Status (21 Nov 2026):** stage 1, **Meeting in, is built** and laptop-tested (ADR-055, proposed). **Stage 2 (memory and
conflicts) and stage 3 (split to Clones) are built** on top of it (branch `meeting-ledger`). **Stage 5 (proof and tracking)
is built** on top of that (branch `meeting-proof`), laptop test pending.

## Stage 5: proof and tracking (built)

| Order (bar, workspace) | PowerShell | What happens |
| --- | --- | --- |
| `split the meeting` (as before) | `kairu meeting split` | The brief now carries each item's id (`[A2.3]` an action, `[D2.1]` a decision). Main Kairu's split names the id each task does (`"from"`); if it doesn't, Kairu matches the words (and the owner's name); a brief with one action links every task to it. The answer says "Linked to the meeting: task 1 → A2.3 …". Links are kept in data/meetings.db (`work` table). |
| (nothing to say) | `kairu team start` | When the team board marks a task done, team.run writes it back: the action (and the decision it serves) becomes **done** in the ledger, with its **proof**: which Clone did which task, when, its "done when" check, the files it made, and what the Clone said. The team feed says "Written back to the ledger as done: …". `kairu team check P T` adds "(checked by you)". |
| `brief me for the next meeting` / `what got done` / `show the proof` | `kairu meeting brief` | Before the next meeting (`meeting.brief`, Low, read only): what got done (with proof), what's still open (overdue, no owner, how many Clone tasks done, or "not split yet"), slipping / blocked / silent Clone tasks with the meeting item each does, conflicts to decide, open questions; then one question. |
| | `kairu meeting ledger` | Each done item shows its proof line; open items show "Clones 1 of 2 tasks done". |

The Meetings page: a **Before the next meeting** box (done, open, overdue, slipping, conflicts, with a "Brief me" button);
each item shows "✓ done" with its **Proof**, or "Clones: 1 of 2 tasks done".

How it stays honest: only the team board's own state "done" (every task linked to the item, in one split) moves an item; a
Clone's words never do. A replaced or dropped item stays as the manager decided. A done item is left out of the next split
and of the workload check. Every reader lays the Clone work over the ledger, so "done" shows at once; team.run and team.check
write it into data/meetings.db. A meetings.db from stages 1-3 gets the new columns by itself.

Code: `kairu/meeting/proof.py` (links, progress, write-back, the brief), `store.py` (work table, proof), `ledger.py` (ids in
the brief), `kairu/team/split.py` ("from"), `kairu/team/conduct.py` (link on split, write back on done and check), tests in
`tests_kairu/test_meeting_proof.py`.

## Stage 2 and 3: memory, conflicts, split (built)

| Order (bar, workspace) | PowerShell | What happens |
| --- | --- | --- |
| `read the meeting weekly sync` | `kairu meeting add FILE --date D` | As stage 1, and Gemini is also shown the earlier open decisions and actions (the ledger, ids `E1.2`) and names each clash: a dropped thing back, a moved date, a changed owner, someone overloaded. Kept, read strictly (an id never shown is dropped, quotes checked). |
| `show the conflicts` / `check for conflicts` | `kairu meeting conflicts` | Gemini's open conflicts between meetings, plus Kairu's own checks: no owner, two owners for the same work, an owner with more than 3 open actions this week or over 240 busy minutes on the team board, a task due before what it waits on. (`meeting.check`, Low) |
| `what did we decide about the launch?` | `kairu meeting ask "the launch"` | The newest decision about it, with the meeting, the day, its status and the words; then what came before. (`meeting.ask`, Low) |
| `keep the new one 2.1` / `keep the old one 2.1` | `kairu meeting resolve 2.1 new` | The manager decides: new marks the earlier item replaced; old marks the newer item dropped. (`meeting.resolve`, Medium) |
| `split the meeting [N] [in 2 hours]` | `kairu meeting split [N] --hours 2` | Refused while conflicts between meetings are open. Then the open actions (with owners and dates) become a brief for `team.split`, as "split the project" does; `kairu team start` runs it. |
| | `kairu meeting ledger` | Every decision and action across meetings, with its status (open, done, replaced, dropped). |

The Meetings page shows "Conflicts to decide" (red: between meetings, with the earlier words and day, and Keep new / Keep the
earlier one buttons; amber: Kairu's own checks), each item's status, and a "Split this meeting to the Clones" button.

Code: `kairu/meeting/ledger.py` (rules, ask, brief), `store.py` (conflicts table, ledger, resolve), `read.py` (ledger in the
prompt, conflicts read strictly), tests in `tests_kairu/test_meeting_ledger.py`.

## Stage 1: Meeting in (built)

Say or type, in the bar, the workspace or to Kairu Live (at Main Kairu's own PC):

| Order | What happens |
| --- | --- |
| `read the meeting kickoff` | Finds `kickoff.*` in your work folder or its `meetings` folder. Card: the file and its sha256 ("yes" + PIN). A recording is written down by Gemini (speaker names, `[mm:ss]`); a transcript (.vtt/.srt/.txt) is read as it is. Gemini then pulls out decisions, actions (owner, deadline as a date) and open questions. |
| `record the meeting [called X]` | Card ("yes" + PIN), then the mic records in memory only; the Meetings page shows "Recording 2:13". |
| `end the meeting` | Ends the recording; Gemini writes it down and reads it. |
| `show the last meeting` / `show meeting 2` | The decisions, actions and questions, in a few lines. |

Or in PowerShell: `kairu meeting add FILE [--date YYYY-MM-DD]` (a file outside the work folder is copied into its
`meetings` folder), `kairu meeting record`, `kairu meeting end`, `kairu meeting list`, `kairu meeting show [N]`,
`kairu meeting transcript N`, `kairu meeting forget N`.

The workspace's **Meetings** page: every meeting, its summary and people; counts with warnings ("no owner", "no deadline",
"quote not found"); decisions; **who does what** (one card per person, "Nobody yet" in amber); actions; open questions; and
the transcript, where each item's `[mm:ss]` quote jumps to its line. Kept in data/meetings.db on this PC only.

How it keeps the judges' bar: an owner is never guessed; "Friday" becomes a real date from the meeting's day; every quote is
checked against the transcript (one that isn't there is shown in red as "check this one"); a later change in the same
meeting replaces the earlier decision ("Replaces: ..."); each item has a status (open, done, replaced, dropped) ready for
the stage 2 ledger.

Demo files: `tools/demo_meetings/2026-11-12 Fresh Bakes kickoff.vtt` (scope, owners, the mobile app dropped, launch on the
28th, hosting left open) and `2026-11-19 Fresh Bakes weekly sync.vtt` (the mobile app comes back, the launch moves to the
25th, Ravi is overloaded): the two meetings of the demo story below.

Code: `kairu/meeting/` (read.py, hear.py, store.py, conduct.py, orders.py, commands.py), the Meetings page in
`kairu/workspace/page.html`, tests in `tests_kairu/test_meeting.py`.

## The pipeline

1. **Meeting in.** Record or upload a meeting, transcribe it, and pull out each decision, its owner,
   its deadline, and the open questions.
2. **Memory and conflicts.**
   - A decision ledger across meetings: every decision with its meeting, date, owner, deadline and
     status (open, done, replaced).
   - Conflict check, before anything is split:
     - decision vs an earlier decision ("we dropped the mobile app on 12 Nov, today it's back");
     - deadline vs workload: the owner is already busy on clone tasks (the board knows the minutes);
     - owner vs owner: two people given the same task, or a task nobody owns;
     - deadline vs dependency: a task due before the task it waits on.
   - Ask Kairu: "what did we decide about X?" and get the meeting and date.
3. **Main Kairu splits.** Confirmed decisions become a brief for `team.split`; the manager sees the
   split and the conflicts, and says yes.
4. **Clones do the work.** Each clone runs its tasks on its laptop, every step decided by its own
   Guardian (existing code).
5. **Proof and tracking.** Each finished task is written back to the decision it came from (the
   ledger shows "done", with what was made). Before the next meeting, Kairu gives a short brief:
   open items, slipping tasks and conflicts.

## What already exists and is reused

- `kairu/team/split.py`: brief -> tasks with "done when" checks, weighed by skills and busy minutes.
- `kairu/team/board.py`: progress, deadline bar, SLIPPING; its workload data feeds the conflict check.
- `kairu/memory/`: the pattern for data kept on this PC only (the ledger follows the same rules).
- `kairu/brain/`: the model gateway and privacy filter for transcript reading.
- Guardian: every new action goes into policy.yaml with a tier; nothing bypasses it.

## Demo story (3 minutes)

1. Meeting 1 (recorded earlier): the team decides the scope and owners. The ledger fills.
2. Meeting 2 (live): someone moves a deadline and re-adds a dropped feature. Kairu flags both
   conflicts, with the earlier meeting's date and words, and says Ravi is already over his hours.
3. The manager resolves them and says yes. Main Kairu splits; a clone opens Notepad or the browser
   and does the first task on screen.
4. The board shows progress; the ledger shows "done" against the decision from the meeting, with its proof.
5. Before the next meeting: "brief me for the next meeting": done (with proof), open, slipping, conflicts.
