# Hackathon: Kairu Employee

**Brief:** build an AI employee that converts meetings into actual completed work. The judges stress
**cross-meeting memory** and **conflict detection**; a simple meeting summarizer is not enough.

**Status:** plan only. Nothing in `kairu/meeting/` is built yet; building starts on the owner's GO.

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
