# Hackathon: Kairu Employee

**Brief:** build an AI employee that converts meetings into actual completed work. The judges stress
**cross-meeting memory** and **conflict detection**; a simple meeting summarizer is not enough.

**Status (21 Nov 2026):** stage 1, **Meeting in, is built** (ADR-055, proposed; the owner's GO of 21 Nov 2026), on the
branch `meeting-in`; laptop test pending. Stages 2 to 5 are next.

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
4. The board shows progress; the ledger shows "done" against the decision from the meeting.
