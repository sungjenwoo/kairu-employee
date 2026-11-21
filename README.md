# Kairu Employee

**An AI employee that turns meetings into finished work, not just notes.**

Most meeting tools stop at a summary and a list of action items. Kairu goes on to do the work: it
remembers what every earlier meeting decided, flags anything today's meeting contradicts, splits the
decisions into tasks, and Kairu clones on each teammate's laptop carry them out.

```
Meeting  ->  Memory + conflict check  ->  Main Kairu splits  ->  Clones do the work  ->  Proof of done
```

## What is here

This repo starts from Kairu (github.com/sungjenwoo/Kairuu, branch `screen-agent-signin`, 20 Nov 2026),
keeping the parts the hackathon needs:

| Part | Status | Where |
| --- | --- | --- |
| Main Kairu splits a project into tasks with "done when" checks | Built, laptop-tested 17 Nov | `kairu/team/split.py`, TEAM.md |
| Clone on each employee laptop, Gate and Link pairing | Built, laptop-tested 17 Nov | `kairu/team/`, `kairu/link/`, LINK.md |
| Clones talk and sync, hand-offs | Built, laptop-tested 17 Nov | `kairu/team/conduct.py`, `inbox.py` |
| Manager board, deadline bar, SLIPPING alerts | Built, laptop-tested 17 Nov | `kairu/team/board.py` |
| Laptop control: apps, files, web, any-app typing (PC0-PC6) | Built, laptop-tested | `kairu/tasks/`, BAR.md |
| Screen agent ("take control") | Built, laptop test pending | `kairu/tasks/agent.py`, `eyes.py` |
| Memory (remember, recall, forget; on this PC only) | Built, laptop test pending | `kairu/memory/`, MEMORY.md |
| Guardian safety: tiers, PIN, stop, audit log | Built, laptop-tested | `kairu/guardian.py`, GUARDIAN.md |
| **Meeting agent** | **To build** | `kairu/meeting/`, HACKATHON.md |

Other Kairu parts (voice, research, Builder, Shadows, phone) are still in the code because the tests
and Guardian depend on them; they are simply not part of the hackathon demo.

## The new part

See **HACKATHON.md** for the meeting agent plan: meeting capture, decisions/owners/deadlines,
the cross-meeting decision ledger, conflict detection, auto-split to clones and proof of done.

## Run

Windows 11, Python 3.12:

```powershell
py -3.12 -m pip install -e .
py -3.12 tools\check_guardian.py
```

How Guardian works and every rule Kairu follows: GUARDIAN.md and CLAUDE.md.
