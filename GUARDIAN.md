# Kairu Guardian core

Guardian is the only authority in Kairu (Architecture §10). This is its core: the policy, the
tiers, approvals with your PIN, the emergency stop, Safe Mode and the audit log. No AI model is
used anywhere in it: the same request always gets the same answer. Python 3.12, SQLite, and two
packages: PyYAML and argon2-cffi. Windows parts (Job Objects, DPAPI, the hotkey, the named pipe)
use ctypes.

Guardian runs as its own background program, with no window (`kairu guardian run`). Kairu asks
it for every decision over a private channel on this PC, and Guardian starts every action itself
and holds Ctrl+Alt+K. `kairu guardian install` has Windows start it when you sign in, and again
within a minute whenever it is not running. See "The Guardian program" below.

An action's run ends as `finished`, `refused` (the action would not do what it was asked: exit code 3, kairu/worker.py),
`failed` or `halted`, in the audit log and in `run_status`.

Kairu does not import the voice and research prototype, and `config.yaml` switches voice and
research off. Live web research is built (RESEARCH.md); its switch waits for you.

**Protection (Phase J).** Guardian's monitors watch your Gmail (read-only) and your deadlines and
raise alerts, and (Phase J2) your Downloads folder, new devices and Windows Security; they cannot act. They run as one Guardian action, `protect.watch`, which Guardian
starts by itself (`protect.enabled` in `config.yaml`). How to set them up and use them:
[PROTECTION.md](PROTECTION.md).

## Check everything on your PC: one command

In PowerShell, in the project folder:

```
py -3.12 tools\check_guardian.py
```

The first run makes a private environment in `.venv-guardian` and installs Kairu, PyYAML,
argon2-cffi and pytest into it (from PyPI). Then it runs every Guardian test and ends with a
summary like this:

```
  Result: PASSED   97 passed, 0 failed, 2 skipped
  Real Ctrl+Alt+K test: passed
  Stop timings:
    stop -> action, child and grandchild gone in 0.0xx s
    ...
  Full output: ...\guardian-check-report.txt
```

Some tests press Ctrl+Alt+K for you, so do not type while they run (about two minutes). If your
own Guardian is running, the check ends it while the tests run (they need Ctrl+Alt+K, and only one
Guardian can run) and starts it again afterwards. If anything fails, send me
`guardian-check-report.txt`. `py -3.12` needs Python 3.12 from python.org; if `py` says 3.12 is
not installed, install it and run the command again.

## Use it

After the check, the `kairu` command is in the private environment. In each new PowerShell
window, in the project folder, put it on the path first (this works without changing
PowerShell's script policy):

```
$env:Path = "$PWD\.venv-guardian\Scripts;" + $env:Path
kairu guardian install
kairu pin set
kairu status
```

`kairu guardian install` has Windows Task Scheduler start Guardian when you sign in, and again
within a minute whenever it is not running, and starts it now. Run it from the project folder you
keep: the task runs this folder's `.venv-guardian`. Without it, `kairu guardian run` starts
Guardian by hand, until you sign out. While Guardian is not running, Kairu refuses every request
(and, if the task is installed, asks Task Scheduler to start it).

| Command | What it does |
|---|---|
| `kairu guardian install` | Makes the Task Scheduler task (see "Starting at sign-in" below) and starts Guardian. Needs no administrator rights |
| `kairu guardian uninstall` | Removes that task. A running Guardian keeps running until you quit it or sign out |
| `kairu guardian run` | Starts Guardian as its own background program, with no window, and waits until it answers. Says so if it is already running |
| `kairu guardian quit` | Ends the Guardian program, and every action it is running. Kairu refuses every request until Guardian runs again; with the task installed, that is within a minute |
| `kairu status` | Whether Guardian is running (`Guardian is not running` if not), the sign-in task, whether Guardian holds Ctrl+Alt+K, and the actions it is running; normal or Safe Mode, PIN set or not, the policy, the voice and research switches, the audit log check |
| `kairu request ACTION [key=value ...]` | Asks Guardian about one action. High tier shows the details and asks for `yes` and your PIN. Nothing is run: `kairu request` only asks |
| `kairu stop` | Emergency stop: every running Kairu action, and every program it started, ends within 1 second; then Safe Mode. Works whether or not Guardian is running |
| Ctrl+Alt+K | The same stop, from any window, whenever Guardian runs: no Kairu window needs to be open (Windows only) |
| `kairu resume` | Leaves Safe Mode after `yes` and your PIN, through Guardian |
| `kairu pin set` | Sets your PIN (at least 6 characters), or changes it (needs the current one), through Guardian |
| `kairu audit verify` | Checks the hash chain and compares it with the anchor. Exit code 0 if all is well; 1 and what is wrong if not |
| `kairu audit reanchor` | After a problem you have looked into: accepts the audit log as it is now (`yes` and your PIN); the problem stays on record |
| `kairu audit show -n 20` | The newest audit rows |
| `kairu demo --seconds 60` | Guardian runs a harmless counting action so you can try the stop and the hotkey. If Guardian is not running, the demo starts it, and ends again only a Guardian it started itself |
| `kairu hotkey` | Holds Ctrl+Alt+K until you press Ctrl+C here, for when Guardian does not hold it; says so if Guardian does |

## Test Ctrl+Alt+K by hand

1. Open PowerShell in the project folder and run `$env:Path = "$PWD\.venv-guardian\Scripts;" + $env:Path`.
2. Run `kairu guardian run`, then `kairu status`. If it says Safe Mode, run `kairu resume` first
   (`yes`, then your PIN).
3. Run `kairu demo --seconds 120`. It prints `demo.count is running inside Guardian ...` and then
   `demo.count: 1 s`, `2 s`, ... once a second. It should also say
   `Press Ctrl+Alt+K anywhere (Guardian holds it) ...`. If `kairu status` says
   `Ctrl+Alt+K NOT held by Guardian`, another program has the key: close it (Guardian takes the
   key within 5 seconds), or use `kairu stop`, and tell me which program it was.
4. Click on a different window, for example Notepad or your browser, so PowerShell is not in front.
5. Press Ctrl+Alt+K once.
6. Look at PowerShell. The counting stops and it prints
   `Halted 0.xx s after the stop request. Kairu is now in Safe Mode`. The number should be under 1.
7. Run `kairu status`. It shows `mode: Safe Mode (emergency stop (Ctrl+Alt+K))`.
8. Run `kairu demo` again. It is refused: `Guardian refused demo.count: Safe Mode ...`.
9. Run `kairu resume`, type `yes`, then your PIN. `kairu status` shows `mode: normal` again.
10. Optional, the stop from another terminal: start `kairu demo --seconds 120` again, open a
    second PowerShell window in the same folder, run the same `$env:Path = ...` line there, then
    `kairu stop`. The first window prints `Halted ...` the same way.
11. Optional, to see where the action runs: open Task Manager, Details tab, sort by name. While
    the demo runs, Guardian's `pythonw.exe` has started two more `pythonw.exe` processes, the
    action; after the stop they are gone, and Guardian's own stay.

## Starting at sign-in

`kairu guardian install` makes one Task Scheduler task, `Kairu Guardian <8 letters>` (one per
Windows account and data folder; it shows in Task Scheduler's library). The task:

- starts when you sign in: an "At log on" trigger for your account only;
- starts again every minute: a second trigger that repeats every minute from the moment you
  install, so this works right away and not only after your next sign-in;
- runs only while you are signed in, as you, with normal rights (least privilege, never as
  administrator), at normal priority, also on battery;
- runs `pythonw -m kairu --config <config.yaml> guardian run --autostart`, which checks whether
  Guardian answers and, only if it does not, starts it in the background; then it ends. Guardian
  itself is not part of the task, so the task never ends it.

Creating it needs no administrator rights (checked on your PC: done from a normal, not
elevated, PowerShell). `kairu guardian uninstall` removes it. Each minute's check is a short
`pythonw.exe` that ends within a second when Guardian is running.

**Only one Guardian** runs under your account at a time, whatever its data folder: a second one,
whether started by hand, by the task or by `kairu demo`, refuses to start, because Ctrl+Alt+K can
reach only one.

**Clean and unclear exits.** Guardian records a clean exit only when it ends because of
`kairu guardian quit`, or because Windows tells it you sign out, shut down or restart. If the last
Guardian ended in any other way (End task in Task Manager, a crash, a power cut), the next one
cannot be sure what happened in between, so it starts in Safe Mode, with the reason
`the last Guardian (process N, started ...) ended without a clean exit`, until you
`kairu resume`. To hear about sign-out and shutdown, Guardian keeps one hidden window (never
shown, and not a "message-only" window, which would not hear them), because Windows tells
programs about these only through their windows.

How Guardian makes sure it is heard in time:

- **Nothing above it that Windows ends without asking.** A venv's `pythonw.exe` is only a small
  starter that runs the real `pythonw.exe` as its child, and its child dies with it. The starter
  has no window, so at sign-out and restart Windows ended it without asking, and Guardian with
  it, before Guardian had written anything: that was why sign-out and restart came back in Safe
  Mode (shutdown passed only because Guardian happened to be told first). Guardian now runs the
  real `pythonw.exe` directly, told to use the venv, and nothing stands above it.
- **Told among the first** (`SetProcessShutdownParameters`, the highest level an ordinary program
  may use), and it never holds the sign-out up.
- **The clean exit is written first**, as one small write that takes about 10 ms, before any
  action is ended. Its audit row follows; if Windows ends Guardian in between, the next start
  writes that row, marked "recorded at the next start".
- **As early as Windows itself says so.** When Windows asks whether the session may end and
  Windows reports the session really is ending, the clean exit is written right then. A
  message alone does not count: Guardian checks with Windows. If the sign-out is then cancelled,
  Guardian takes the record back.

`data\guardian.log` keeps what Guardian wrote across starts (the newest at the end), with times:
when it was asked, what Windows said, when the clean exit was written.

## Hand tests after install (Windows)

These need you, because they sign you out and restart the PC. Before you start, in PowerShell in
the project folder:

```
$env:Path = "$PWD\.venv-guardian\Scripts;" + $env:Path
kairu guardian install
kairu status
```

`kairu status` should show `autostart: Task Scheduler task "Kairu Guardian ..."`,
`hotkey: Ctrl+Alt+K held by Guardian ...` and `mode: normal` (if it says Safe Mode, run
`kairu resume`, type `yes`, then your PIN). Set your PIN first with `kairu pin set` if you have not.

After each of the four tests below, check these three things, in this order:

- **A. Is Guardian running?** Open PowerShell in the project folder, run the `$env:Path = ...`
  line, then `kairu status`. Its first line should be `Guardian: running (process N)`. After a
  sign-in, give it up to a minute.
- **B. Did it come back in Safe Mode?** In the same output, the `mode:` line.
- **C. Does Ctrl+Alt+K work with no Kairu window open?**
  1. Run `kairu demo --seconds 300` and wait until it counts `demo.count: 2 s`.
  2. Close that PowerShell window with its X. The counting action keeps running inside Guardian,
     and no Kairu window is open now.
  3. Click on any other window (Notepad, your browser) and press Ctrl+Alt+K once.
  4. Open PowerShell again, run the `$env:Path = ...` line, then `kairu status`. It should show
     `actions: none running` and `mode: Safe Mode (emergency stop (Ctrl+Alt+K))`.
  5. Run `kairu audit show -n 5`. The row `run  demo.count  halted` shows `seconds_since_stop`:
     it should be under 1.
  6. Run `kairu resume` (`yes`, then your PIN), so the next test starts from normal.
- **D. The tray icon.** In the notification area (or behind the ^ arrow) there is a shield.
  Point at it: `Kairu Guardian: normal, nothing running. Ctrl+Alt+K ready`. Start
  `kairu demo --seconds 300`, click the icon: the menu shows the state and a large red
  **STOP EVERYTHING**. Choose it: the demo prints `Halted ...` (under 1 s), the icon becomes a
  warning sign, and pointing at it says Safe Mode. Then `kairu resume`.

The four tests:

| Test | How | Expected A | Expected B | Expected C |
|---|---|---|---|---|
| 1. Sign out and in | Start menu, your name, Sign out. Sign in again. Wait a minute | running | `normal` | works, under 1 s |
| 2. Restart | Start menu, Power, Restart. Sign in. Wait a minute | running | `normal` | works, under 1 s |
| 3. Shut down and start again | Start menu, Power, Shut down. Switch the PC on, sign in. Wait a minute | running | `normal` | works, under 1 s |
| 4. End task | Run `kairu status` and note Guardian's process number N. Open Task Manager, Details tab, find `pythonw.exe` with PID N, End task, confirm. Wait a minute | running again, as a new process | `Safe Mode (the last Guardian (process N, ...) ended without a clean exit)` | works, under 1 s (run `kairu resume` before C) |

Please send me, for each test, the `kairu status` output from A and the `kairu audit show -n 5`
output from C. If a sign-out, restart or shut-down test comes back in Safe Mode, also send
`kairu audit show -n 30` and the end of `data\guardian.log`: they show how the last Guardian ended.

## The Guardian program

`kairu guardian run` starts `pythonw -m kairu.guardian_program` (Linux: `python -m ...`, in its
own session) in the background. That program alone holds the policy, the PIN hash and the audit
log, makes every decision, with the same rules as before, and starts every action. Its messages
go to `data\guardian.log`.

**Actions.** Kairu asks Guardian to run an action by its name, with its details. Guardian decides
as for any request (a High action needs its approval, used once and only for exactly those
details), then starts the code it has for that action, with exactly those details as its
arguments. The list of code is Guardian's own (`kairu/executors.py`): Kairu never names the code,
so it cannot point an allowed action at other code, and an action without code is never run. So
far `demo.count` has code (it takes `seconds` and `quiet`, and nothing else: it cannot be told to
write a file), and the protection actions (`protect.*`, `alerts.dismiss`, `deadline.*`, PROTECTION.md).
Where an action keeps its files and how often the monitors check are filled in by Guardian from its
own `config.yaml`, never from the request. `protect.watch` and the Gmail actions run once at a time.
At most 8 actions run at once.

Each action runs in its own process, which Guardian starts in its own Job Object (Windows) or
process group (Linux), as described under "Emergency stop" below. Guardian's runner reads the
stop flag every 0.1 s and halts them all. `kairu guardian quit` ends them before Guardian ends. If
Guardian itself is killed, Windows closes its Job Objects and ends its actions with it.

**The tray icon (Windows).** While Guardian runs, it shows an icon in the notification area,
one of Windows' own: a shield (normal, nothing running), an "i" (normal, actions running) or a
warning sign (Safe Mode). Pointing at it says the state in words. Clicking it opens a menu with
the state and one large red **STOP EVERYTHING**, which does exactly what Ctrl+Alt+K does. There is
no Quit and no Resume in it on purpose: leaving Safe Mode needs `kairu resume`, `yes` and your PIN.
If the icon is in the hidden-icons area (the ^ arrow), you can drag it onto the taskbar.

**Ctrl+Alt+K.** Guardian holds the key for as long as it runs, so it works from any window with
no Kairu window open. A press writes the stop into `guardian.db` and wakes Guardian's runner at
once, which halts every action. If another program already has the key when Guardian starts,
Guardian tries again every 5 seconds; `kairu status` says whether it holds it. `kairu demo` and
`kairu hotkey` hold the key themselves only when Guardian does not.

**The private channel.** Kairu talks to it only on this PC, with no network at all:

- **Windows:** a named pipe, `\\.\pipe\kairu-guardian-...` (one name per Windows account and data
  folder). Only your Windows account may open it; network logons are refused, and so are
  connections from other PCs (`PIPE_REJECT_REMOTE_CLIENTS`). Guardian creates it as the first and
  only instance of that name: if another program already has the name, Guardian does not start,
  and while Guardian has it, no other program can add an instance.
- **Linux:** `data/guardian.sock`, a socket file only you can open (permissions 600). Guardian
  does not start if another program is already listening on it.

Each connection carries one request. Guardian checks that the program connecting runs as you.
Then, **before Kairu sends anything** (the request, or your PIN), it asks Windows or Linux about
the program at the other end, rather than trusting what that program says, and goes on only if:

1. it runs under your account (and on Windows, not at low integrity, as sandboxed programs do);
2. its program file is the Python that runs Kairu;
3. it was started as the Guardian program (`-m kairu.guardian_program`);
4. its greeting names that same process and this data folder.

If any of these fails, Kairu refuses the request, says which check failed, and sends nothing.

**Messages.** Each one is a small JSON object, at most 16 KiB. Guardian answers only the requests
it knows (`check`, `approve`, `authorize`, `run`, `run_status`, `end`, `resume`, `set_pin`,
`reanchor`, `status`, `quit`, `report`), each with exactly its own fields of the right types.
`report` is how the monitors tell Guardian about an alert: its number, source, kind, severity and
fingerprint, each from a fixed list; Guardian writes an `alert` row and shows a tray pop-up, and
grants and runs nothing. Anything else,
such as broken JSON, a message that is too large, an unknown request, a missing or extra field (a
message that names its own tier, an override, its own verdict or the code to run), or one that
stops halfway, gets `deny`, and a `channel` row in the audit log. Guardian keeps running whatever arrives. A program that connects and then says nothing
is answered `deny` after 5 seconds.

**Without Guardian.** If Guardian is not running, every request is refused: `kairu request`,
`resume`, `pin set` and `audit reanchor` say `Guardian is not running`, and `kairu status` says so
first, then shows what the files say.

**Not through Guardian:** `kairu stop` (and Ctrl+Alt+K when `kairu demo` or `kairu hotkey` holds
it) must work even when everything else is broken, so it writes the stop straight into
`guardian.db`, as before; Guardian's runner halts its actions within 0.1 s of it, and its next
decision sees Safe Mode. Also `kairu audit verify` and `audit show` (they only read, and a check
of the log should not depend on the program it checks), and `kairu status` while Guardian is not
running (it only reads).

## The rules

`policy.yaml` lists every action with a tier. Guardian applies these in order:

1. The policy could not be read, or the action is not in it: **deny**.
2. Critical: **deny**, always. There is no approval request, no PIN, no setting and no flag that unlocks it (D4).
3. The action belongs to a feature that is off in `config.yaml` (`voice.*`, `research.*`): **deny**.
4. Safe Mode is on and the action is not `read_only`: **deny**.
5. High: **needs_approval**.
6. Low and Medium: **allow**.

If a decision cannot be written to the audit log, the answer is deny.

**High tier.** You see the action, what it does and its details, then type `yes`, then your PIN
(not shown as you type). The approval is good once, for that action with exactly those details,
for 2 minutes. It is checked again just before the action runs (`authorize`), so a stop or
Safe Mode in between cancels it. Approvals live in memory only, so a restart drops them.

**PIN.** Only an Argon2id hash is stored (RFC 9106 low-memory profile: 3 passes, 64 MiB).
After 5 wrong PINs in a row Kairu enters Safe Mode and refuses every PIN for 60 seconds; each
further wrong PIN starts the 60 seconds again. The count survives a restart, and is written
before anything else, so it holds even if the audit log cannot be written.

**Emergency stop.** `kairu stop`, Ctrl+Alt+K and `Runner.stop()` all write one stop into
`guardian.db`, before anything else. Guardian's action runner reads it every 0.1 s, then ends
each action together with every program it started:

- **Windows:** each action runs inside its own Job Object, set to "kill on job close". Guardian
  creates the action's process suspended, puts it in the job, and only then lets it start, so
  it cannot start a child outside the job. Ending the job ends the whole family at once. If
  Guardian itself crashes or is killed, Windows closes the job and ends them too.
- **Linux:** each action starts a new session, so it and its children share one process group.
  The group is asked to end (SIGTERM), and killed (SIGKILL) 0.3 s later at most.

When an action ends by itself, anything it left running is ended too. After a stop, Kairu stays
in Safe Mode (read-only actions only) until you resume. The stop needs only the database, not
the policy or the PIN, so it works when they are broken.

**Audit log.** Every request and decision, every approval and refusal, every PIN set, change
and refused change, every stop, Safe Mode change, resume, re-anchor, and every action started,
finished or halted is one row in the `audit` table. Each row stores the hash of the row before
it; its own hash covers its id, its contents and that previous hash. The database refuses
UPDATE and DELETE on the table, so Kairu can only add rows. The PIN is never written to it.

**Audit anchor.** A separate file, `data/audit.anchor`, holds the number of rows and the newest
row's hash. It is rewritten in the same database transaction as every new row, atomically (a new
file is written and flushed to disk, then renamed over the old one), so the two always move
together. On Windows it is sealed with DPAPI for your Windows account; on Linux only you can read
or change it (permissions 600). Before rewriting it, Kairu compares the old anchor with the
database; anything wrong is kept inside the anchor as an alert, so the evidence is not lost when
Kairu carries on. `kairu audit verify` reports:

| What it says | What happened |
|---|---|
| `TAMPERED at row N` | a row inside the log was changed, inserted, removed or swapped |
| `newest rows deleted` | the anchor says there were more rows than there are now |
| `database file missing` | `guardian.db` is gone, but the anchor shows it existed |
| `anchor missing` | `audit.anchor` is gone (or was gone at some point) while the log has rows |
| `anchor tampered` | the anchor was edited, cannot be unsealed, or (Linux) other users can read or change it |
| `anchor and database do not match` | the anchor's newest row is not the database's: one of them was rewritten, or an older anchor was put back |

Kairu also refuses to start with a new, empty `guardian.db` while an anchor exists: that would
quietly reset Safe Mode, the PIN and the log. Running actions halt on their own if `guardian.db`
disappears, because they can no longer read the stop flag.

After you have looked into a problem, `kairu audit reanchor` accepts the log as it is now, with
`yes` and your PIN, and adds a row saying what was accepted. It refuses if rows inside the log
were changed: keep that file as it is, as evidence.

**Starting again.** To throw away all Guardian state (Safe Mode, PIN, audit log), delete both
`data\guardian.db` and `data\audit.anchor`. Kairu then starts as on its first run.

**What survives a restart:** Safe Mode and its reason, the stop count, the PIN hash, the
wrong-PIN count and lock, the audit log and its anchor. **What does not:** approval requests and
approvals; they live in the Guardian program's memory, so `kairu guardian quit` drops them too.

## Measured while building

Measured on 25 Oct 2026, Python 3.12. Windows: a GitHub Actions machine (Windows Server 2025,
the same Windows core as Windows 11 24H2), not your PC yet. Linux: the 4-CPU build machine.

| Measure | Windows | Linux |
|---|---|---|
| Tests (`tools/check_guardian.py`) | 97 passed, 2 skipped (Linux-only tests) | 97 passed, 2 skipped (Windows-only tests) |
| Real Ctrl+Alt+K press | passed | not available |
| Stop: action, child and grandchild all gone | 0.06 s | 0.01 s |
| Stop: a family that ignores the request to end | 0.08 s | 0.31 s (killed after the 0.3 s grace) |
| `kairu stop` in another terminal, whole family gone | 0.27 s | 0.41 s; 0.43 s at worst with all CPUs busy |
| `kairu stop` in another terminal, 3 actions | 0.27 s | 0.50 s; 0.55 s at worst with all CPUs busy |
| `kairu stop` while `kairu demo` runs | 0.03 s after the stop is written | 0.01 to 0.07 s |

Memory (Linux; Windows uses somewhat more per Python process):

| Measure | Peak |
|---|---|
| `kairu stop`, `kairu status`, `kairu audit verify` | 21 to 22 MiB each |
| Kairu with Guardian loaded, after 2,000 checks | 23 MiB |
| Checking or setting the PIN | +64 MiB for a moment (Argon2id), peak 87 MiB, back to 23 MiB after |
| Each running action's own process | 11 MiB |
| The whole test run (main process) | 101 MiB |

The Guardian program (`kairu guardian run`), running every action itself and holding Ctrl+Alt+K,
measured on 27 Oct 2026 on your PC and on GitHub Actions:

| Measure | Your PC (Windows 11) | Windows (GitHub) | Linux (GitHub) |
|---|---|---|---|
| Tests (`tools/check_guardian.py`) | 156 passed, 4 skipped (Linux-only tests) | 156 passed, 4 skipped | 143 passed, 17 skipped (Windows-only tests) |
| Ctrl+Alt+K held by Guardian, no Kairu window open: 2 actions gone | 0.03 s | 0.05 s | not available |
| Tray icon, STOP EVERYTHING: 2 actions gone | 0.03 s | 0.06 s | not available |
| `kairu stop` in another terminal, 3 actions inside Guardian | 0.22 s | 0.19 s | 0.17 s |
| `kairu stop`, a family inside Guardian that ignores the request to end | 0.24 s | 0.27 s | 0.41 s |
| Ctrl+Alt+K while `kairu demo` runs, action inside Guardian | 0.03 s after the stop is written | 0.06 s | not available |
| Guardian killed outright: its action gone | 0.02 s | 0.02 s | not built (see known limits) |
| Guardian's memory at rest | 32 MiB | 34 MiB | 29 MiB |
| After a PIN check and 200 decisions | 34 MiB | 37 MiB | 29 MiB |
| Peak, during the PIN check (Argon2id) | 96 MiB | 98 MiB | 93 MiB |

Holding Ctrl+Alt+K, the hidden window and the tray icon add about 5 MiB to Guardian. Guardian
no longer has the venv's `pythonw.exe` starter beside it (that saves about 4 MiB).
Each running action adds its own process (about 11 MiB), plus on Windows its own small starter.

Each Guardian decision takes about 2 ms, including the anchor update and its flush to disk.

Protection, measured on 27 Oct 2026 on the Linux build machine: the monitors' own process
(`protect.watch`, with the Gmail reader loaded) uses 24 MiB; the email rules take about 2 ms per
email; `kairu stop` ends the monitors in 0.1 s.

## Files

```
policy.yaml          every action and its tier
config.yaml          voice.enabled: false, research.enabled: false, where the policy, data and anchor are
kairu/
  guardian_program.py  the Guardian program: holds the Guardian, checks each message, answers it
  channel.py         the private channel: framing, the 16 KiB limit, checking who is at the other end
  winpipe.py         the Windows named pipe and process identity, through ctypes
  client.py          what Kairu uses to ask Guardian; `kairu guardian run` and `quit`
  executors.py       the code Guardian runs for an action, and the details it takes (only demo.count so far)
  autostart.py       the Task Scheduler task: install, uninstall, asking it to start Guardian
  session.py         the hidden window that hears sign-out, shutdown and restart, and owns the tray icon (Windows)
  tray.py            the tray icon: Guardian's state, and STOP EVERYTHING (Windows)
  guardian.py        check, approve, authorize, emergency_stop, resume
  policy.py          reads policy.yaml; refuses mistakes and duplicate actions; read-only once loaded
  config.py          reads config.yaml
  approval.py        the terminal prompt: details, "yes", PIN
  pin.py             Argon2id hash, wrong-PIN lock
  safemode.py        the stop count and Safe Mode, in guardian.db
  runner.py          inside Guardian: runs authorized actions; halts them on a stop
  processes.py       keeps each action with its child programs: Job Object (Windows), process group (Linux)
  worker.py          the process one action runs in
  hotkey.py          Ctrl+Alt+K through the Windows RegisterHotKey function; Guardian's Keeper holds it
  audit.py           the hash-chained log, its check against the anchor, reanchor
  anchor.py          the audit anchor: atomic writes, DPAPI on Windows, mode 600 on Linux
  store.py           guardian.db; moves the anchor with every audit row
  demo.py            the harmless counting action
  protect/           Guardian protection: the monitors and alerts for Gmail, deadlines, folders,
                     devices and Windows Security (PROTECTION.md)
  link/              Kairu Link: messages with your phone through the Gate, pairing, the stand-in phone (LINK.md)
  brain/             Kairu's brain: the Model Gateway, the privacy filter, the free providers (BRAIN.md)
  missions/          Mission Cards: long jobs with a checkpoint after every step (BRAIN.md)
  mission.py         Mission Mode: awake with the lid closed while charging, the lid setting always put back (LINK.md)
  cli.py             the kairu command
tests_kairu/         the Guardian tests
tools/check_guardian.py   install, run all tests, print a short summary
.github/workflows/guardian.yml   the same check on Windows and Linux in GitHub Actions
data/                guardian.db and audit.anchor, created on first run; protection.db and
                     protect-gmail.key once protection is used; link.db and link-pc.key once a
                     device is paired; mission-mode.json only while Mission Mode has the lid
                     setting changed; brain.db, brain-keys/ and missions.db once the brain
                     is used (BRAIN.md); not in Git
```

## Not built yet, and known limits

- **Deleting both `guardian.db` and `audit.anchor`** (or the whole `data` folder) cannot be told
  apart from a first run. Neither can putting back an older copy of both files together. Keeping
  the anchor in another folder (`guardian.anchor` in `config.yaml`) makes this harder, not
  impossible. Catching it for sure needs a copy of the newest hash somewhere Kairu's own files
  cannot reach, such as another device; not built yet.
- **A program running as you can still forge the anchor.** DPAPI stops other Windows accounts
  and copies taken to another PC, but any program running under your own account can ask
  Windows to seal a new anchor. On Linux, anything running as you can rewrite the file. The
  same goes for the PIN: a program that can read `guardian.db` can try PINs against its hash
  without the 5-try limit. The PIN protects against someone using Kairu, not against malware
  already running as you.
- **A crash at the exact moment between writing the anchor and committing its row** makes
  `kairu audit verify` report one newest row deleted. Check the log with `kairu audit show`, then
  `kairu audit reanchor`.
- **On Linux, a program that starts its own new session** (`setsid`) leaves the action's process
  group and escapes the stop. Windows Job Objects do not have this gap. On Linux the action's
  programs also outlive Guardian if Guardian is killed outright (`kill -9`); a plain `kill` or
  `kairu guardian quit` ends them first. On Windows they end with Guardian however it ends.
- **Guardian keeps its state in `guardian.db`** in the data folder, which other Kairu commands can
  read, and into which `kairu stop` writes the stop. Architecture §10 wants Guardian's own store;
  that is a later step.
- **A program running as you can still pass for Guardian on purpose.** The check before anything
  is sent stops other accounts, other PCs, sandboxed programs and any program that is not Kairu's
  Python running the Guardian program. A program written to fool it, running under your own
  account (one that rewrites its own command line, or puts a different `kairu` package in front
  of Python), is not stopped. That is the same limit as the anchor and the PIN above: the
  protection is against someone using Kairu, not against malware already running as you.
- **Ctrl+Alt+K works only on Windows**, and only while Guardian (or `kairu demo` or `kairu hotkey`)
  holds it.
- **Starting at sign-in is built for Windows only** (Task Scheduler). On Linux, start Guardian
  with `kairu guardian run`.
- **On Linux, only `kairu guardian quit` is a clean exit.** Linux ends programs at sign-out with
  the same signal as a plain `kill`, so Guardian cannot tell them apart: it ends its actions, but
  the next start is in Safe Mode.
- **A Guardian started by hand, when the task is installed**, is not the task's: that does not
  matter, because the task's check only starts Guardian when none answers.
- **Only `demo.count`, the protection actions, Kairu Link, Mission Mode, the brain and Mission Cards have code**
  (`kairu/executors.py`). Guardian runs nothing else, and `kairu request` decides and approves but runs nothing.
- **No grants, sessions or devices yet** (plan-bound signed grants, AAL levels, per-device
  permissions): Stage 1a and later.
- **A forgotten PIN** cannot be reset without the old one; see "Starting again".
