# Kairu Shadows (Phase H, Shadow v0)

A **Shadow** is a temporary helper you send to a friend's laptop. Your friend builds one use case for Kairu inside it;
when it is finished the Shadow comes home carrying that use case, and you install it into Kairu.

```
you: kairu shadow create        friend: join, build in the Shadow's folder        you: kairu shadow install
      |                                   |                                              ^
      v                                   v                                              |
  invite + 6-digit code  ---->  Shadow on the friend's laptop  --->  home: a branch on GitHub + a report through the Gate
```

Built per ADR-020, ADR-031, ADR-032, ADR-033 and ADR-038 (the owner's Shadow v0 flow, 12 Nov 2026).

**What a Shadow is allowed, all of it:**

- On the friend's laptop: **one folder of its own** (`Kairu-shadow` in their user folder), which starts empty, and a
  **temporary key of its own**. It reads and writes nothing else there. It carries nothing of yours: no memory, no files,
  no keys.
- Towards your PC: it can **only report** (progress, then one return report). It is never a paired device, so nothing it
  sends is ever read as a request: it cannot ask Kairu to run, approve or install anything. Its words are data.
- It **never installs anything by itself**. You do, after testing, with "yes" and your PIN.
- Your friend has their own **Stop**, and the Shadow stays visible while it runs (a small Kairu Shadow window).
- When it leaves, its key is deleted on the friend's laptop and forgotten on your PC: nothing more from it is read.

## 1. Create (your PC)

```
kairu shadow create --for Shruthi --mission "Track my expenses: I say what I spent, it keeps a total" --pack expense-tracker
```

High: you see what it does, type `yes` and your PIN. Kairu then shows an **invite** (one long line) and a **6-digit code**,
both valid 15 minutes; the code is never inside the invite, and 5 wrong codes cancel it. Send the invite by chat or email
and tell the code another way, for example on a call.

| Option | Meaning |
| --- | --- |
| `--pack NAME` | the use case's short name (small letters, digits, dashes); also its folder `packs/NAME` and the end of its branch |
| `--hours N` | its time limit, default **3** (ADR-020), at most 168. Give a build mission more: `--hours 48` |
| `--repo URL` | where it pushes; default: this project's own GitHub repository |

## 2. Go (your friend's laptop)

**Before you create the Shadow** (the invite lasts only 15 minutes), get the laptop ready. Kairuu is private, so first add
your friend on GitHub: **Kairuu → Settings → Collaborators → Add people**, and they accept the invite. The Shadow needs
nothing else of Kairu on their laptop: Python 3.12, git, GitHub's `gh` (for the sign-in and the pull request) and PyNaCl.

On the friend's laptop, in PowerShell, once:

```
winget install -e --id Python.Python.3.12
winget install -e --id Git.Git
winget install -e --id GitHub.cli
```

Close PowerShell and open a new one, then:

```
gh auth login        GitHub.com, HTTPS, Yes (authenticate Git), Login with a web browser
gh auth setup-git
cd $env:USERPROFILE
gh repo clone sungjenwoo/Kairuu -- -b shadow-v0
cd Kairuu
py -3.12 -m pip install pynacl
py -3.12 -m kairu.shadow status
```

"no Shadow is on this laptop" means it is ready. (Once Shadow v0 is merged, leave out `-- -b shadow-v0`.)

Then, with what you sent:

```
py -3.12 -m kairu.shadow join "kairu-shadow:1:..." 123456
```

The Shadow makes its key, joins, and makes its workspace: `Kairu-shadow\workspace\`, with `MISSION.md` (what to build and
what "done" means) and the empty pack folder. Its background part starts with a small **Kairu Shadow** window that shows
the mission and the time left and has a red **STOP the Shadow** button; closing the window only minimizes it.

Nothing else of Kairu runs there: no Guardian, no brain, none of your data. In v0 the Shadow has no AI of its own: your
friend builds with their own tools (their own Claude, their editor), inside the pack folder.

## 3. Build (your friend)

A use case is a **skill pack**, one small folder:

```
expense-tracker/
    pack.json        name, title, description, version, who made it
    skill.py         def run(text: str) -> str      your words in, Kairu's answer out
    README.md        what it does and how to use it
    tests/test_*.py  unittest tests that `import skill`
```

Rules, checked the same way on both laptops: text files only, no links, small (60 files, 512 KB); Python's standard
library and the pack's own files only, so installing a pack installs nothing else.

| On the friend's laptop | |
| --- | --- |
| `py -3.12 -m kairu.shadow status` | the mission, the time left, what is still missing |
| `py -3.12 -m kairu.shadow check` | the done check: the pack check and the pack's own tests |
| `py -3.12 -m kairu.shadow home` | come home (only when the done check passes) |
| `py -3.12 -m kairu.shadow stop` | the friend's Stop: the Shadow ends now and removes itself; nothing is pushed, the files stay |

While it works, the Shadow sends your PC progress through the Gate: how many files, whether the tests pass, whether it
is ready. Never file contents. On your PC:

```
kairu shadow list
kairu shadow status 1
kairu shadow recall 1          come back now
```

## 4. Done check

`home` refuses until: the pack check passes, **every test passes**, the README is written, and no `KAIRU-SHADOW-TODO`
marker is left. The Shadow does not come home with half a use case.

## 5. Come home

`py -3.12 -m kairu.shadow home`:

1. pushes **only** `packs/NAME` to the repository as a new branch `shadow/ID-NAME` (with the friend's own git sign-in) and
   opens the pull request if GitHub's `gh` is installed; otherwise it prints the link that opens it. The code travels by
   GitHub, never through the Gate;
2. sends your PC its **return report**, signed with its key: the pack's digest (one SHA-256 over all its files), the
   number of tests that passed, the commit, what the code reaches for, and up to five lessons;
3. writes the friend a **receipt** next to the folder (`Kairu-shadow-receipt-ID.txt`): exactly what left the laptop, and
   that nothing else did;
4. deletes its key and its state and removes its folder. Your PC forgets the key when it reads the report.

It also comes home when you say `kairu shadow recall N`, when its time limit ends, or when the friend presses Stop. Then,
if the work is not finished, nothing is pushed and the files stay with the friend: they are the friend's own.

## 6. Install (your PC)

```
kairu shadow status 1          it is home; read the pull request it names
kairu shadow install 1         "yes" and your PIN
kairu pack list
kairu pack run expense-tracker lunch 120 and bus 30
```

`kairu shadow install` shows who built it, how many tests passed and what its code reaches for (network, other programs,
files, Windows itself), then asks for "yes" and your PIN. Only then does it fetch the branch, and it installs **only if**:

- the files are **exactly** the ones the Shadow tested and signed for (the digest in its report). A branch someone changed
  after the Shadow came home is refused;
- the pack check passes again here;
- its tests pass again here.

The pack is kept in Kairu's data folder (`data/packs/NAME`), not in the project folder. `kairu pack run` runs its `run(text)`
in a program of its own, and only while its files are still exactly the ones you installed. In v0 **each run needs "yes"
and your PIN** (`pack.run` is High): a pack is code a friend wrote. Installing changes no Guardian rule and adds no policy
action. Merging the pull request is separate and yours; installing does not need it.

## Lessons (comes home smarter, ADR-032)

The friend, or their AI, may note up to five general lessons in `LESSONS.md` in the workspace (lines starting with `- `).
A line with anything that could be the friend's (a path, a file name, an address, a long number, their name) is dropped on
their laptop before the Shadow leaves and checked again on your PC. The lessons taken are on the friend's receipt.

```
kairu shadow lessons
kairu shadow keep 1            Kairu keeps a lesson only after your yes
kairu shadow drop 2
```

A kept lesson is words for you. It never grants a permission or changes a rule. (Feeding kept lessons to the brain comes
with the rest of Phase H.)

## Cowork mode: a full Kairu on your friend's laptop (ADR-039)

A Cowork Shadow lets your friend work on **Kairu itself** (the task core, the bar, skills, anything) with a full Kairu on
their laptop: what your laptop can do, theirs can do. Your choices (14 Nov 2026):

- **Their own PIN** approves High steps on their laptop. Your PIN never goes there.
- **None of your data goes**: no Gmail, paired phone, memory or AI keys. Their Kairu starts empty; they add their own free
  AI key if they need the brain.
- **Every change they make to Kairu comes home** as a branch and a pull request. You test it and merge it; nothing
  installs or merges by itself.

**You:**

```
kairu shadow create --cowork --for Omesh --mission "Make the task core open apps and sites in Chrome"
```

High ("yes" and your PIN). Its copy of Kairu starts from the branch this folder is on (`--base main` chooses another).
Time limit: 24 hours unless you give `--hours`. A short name for the work comes from the mission (`--pack` sets it); it
ends the branch's name.

**Your friend** (the laptop setup above first, then):

```
cd $env:USERPROFILE\Kairuu
git pull
py -3.12 -m kairu.shadow join "INVITE" CODE      downloads Kairu into Kairu-shadow\workspace\kairu, then joins
py -3.12 -m kairu.shadow setup                   installs that Kairu: Guardian at sign-in, THEIR OWN PIN, the bar
```

If they already installed Kairu somewhere else on that laptop, only one Guardian can run: in that other folder, first
`kairu guardian uninstall`, `kairu guardian quit`, `kairu bar uninstall`, `kairu bar quit`.

They change Kairu in `Kairu-shadow\workspace\kairu`, and use it there (Ctrl+Alt+Space opens the bar; after a code change,
`.venv-guardian\Scripts\kairu guardian quit` then `... guardian run` in that folder). Then:

```
py -3.12 -m kairu.shadow check     Kairu's own check on exactly their changes (about 20 minutes; do not type meanwhile)
py -3.12 -m kairu.shadow home      push the branch, open the pull request, remove the Kairu it set up
```

Done means: there are changes, and Kairu's own check passes on exactly those files (it runs again only if a file changed
after it passed). `config.yaml` stays as it came, because two of the check's tests need voice and research off in it.

Whenever the Shadow leaves (home, Stop, recall, time limit), the Kairu it set up is ended and taken out of Task Scheduler,
so it never stays running there. When the work went home, the whole copy is deleted, its data folder (with their PIN)
included; when it did not, the copy with their changes stays theirs.

**You, when it is home (ADR-041): it explains, you approve, your Kairu upgrades.**

```
kairu shadow status N          it is home: what changed, and the pull request
kairu shadow explain N         what your friend built, in plain words
kairu shadow install N         the explanation again, then "yes" and your PIN, then the upgrade
```

The explanation is made by rules from git, the same every time: your friend's own words from their commits; every Guardian
rule it adds, removes or changes, with its tier (a lower tier is marked LOWER); the files; the tests (fewer tests are
marked); and what to watch (Guardian's own code, dependencies, GitHub's workflows). If it would make a Critical action
anything but Critical, or remove one, it can't be installed at all.

After your "yes" and PIN (`shadow.upgrade`, High), Kairu:

1. fetches its branch and takes it only if the files are exactly the ones the Shadow's check passed on and signed for;
2. builds your upgraded Kairu (yours, with the changes merged in) in a separate folder, and runs Kairu's own check there,
   about 20 minutes (don't type meanwhile: some tests press Ctrl+Alt+K). Your Kairu is not touched while it runs;
3. only if the check passes, and your Kairu folder has no uncommitted changes, moves your Kairu forward to exactly that
   tested commit, then restarts Guardian and the bar so they run it.

If anything fails, your Kairu stays as it was. It prints the one git command that goes back. A clash with changes you made
since the Shadow left (a merge conflict) is left to you: merge its pull request by hand. Merging the pull request on GitHub
is still yours; installing doesn't need it.

## Tiers

| Action | Tier | |
| --- | --- | --- |
| `shadow.create` | High | "yes" and your PIN, either mode; your words are kept in the audit log as a hash only |
| `shadow.install` | High | "yes" and your PIN |
| `pack.run` | High | "yes" and your PIN, every run (v0) |
| `shadow.sync`, `shadow.recall`, `shadow.lesson`, `pack.remove` | Low | they only read reports, call a Shadow back, or take something away |

## Honest limits of v0

- **A Cowork Shadow's Kairu is a whole Kairu, acting on the friend's laptop** under the friend's PIN. It is the same
  Guardian, with the same rules, as yours. What it brings home is code for you to review: read the pull request.
- **No AI inside a pack Shadow yet.** ADR-031's "small brain of its own" is not built: the friend brings their own tools. So
  teach-back and call the master (ADR-033) are not built either.
- **A window, not a tray icon,** shows the Shadow on the friend's laptop.
- **The folder fence is the Shadow's own behaviour**: the Shadow program touches only its folder. It does not sandbox the
  friend's own tools, which run as the friend, on the friend's laptop.
- **A pack is code.** The pack check and "what it reaches for" are reading aids, not a sandbox. What protects you is: you
  read the pull request, the digest pins exactly what was tested, and nothing runs without your PIN.
- **One Shadow per friend's laptop at a time.** Up to 5 out at once.
- The Shadows page in the workspace still only describes them; `kairu shadow ...` is how you use them for now.
- A recall waits in the Gate up to 12 hours for a laptop that is off. `kairu shadow recall N --give-up` stops waiting and
  revokes the key on your PC at once.

**`py -3.12 tools\check_guardian.py` takes about 18 minutes on the owner's PC.** It keeps Task Scheduler from starting your
Guardian while the tests run, renewing that every 5 minutes. Two of its tests are expected to fail when your own `config.yaml`
has voice and research switched on (`test_the_shipped_config_switches_voice_and_research_off`,
`test_voice_off_in_the_shipped_config_and_guardian_refuses_both`): they check the file as shipped, and yours is changed.
Every other test must pass.

## The gate test (about 15 minutes, two laptops, or two folders on one)

To try it alone on your own PC, open a second terminal and set `$env:KAIRU_SHADOW_HOME = "$env:USERPROFILE\Shadow-test"`
there; that terminal is "the friend".

1. `py -3.12 tools\check_guardian.py`, then restart Guardian (`kairu guardian quit`, `kairu guardian run`).
2. `kairu shadow create --for Shruthi --mission "Add up the expenses I say" --pack expense-total` (`yes`, PIN).
3. Friend: `py -3.12 -m kairu.shadow join "INVITE" CODE`. Your terminal says the Shadow is on Shruthi's laptop.
4. Friend: `py -3.12 -m kairu.shadow home` right away: refused, with the list of what is missing.
5. Friend: write `skill.py`, the test and the README in the pack folder; `py -3.12 -m kairu.shadow check` passes.
6. You: `kairu shadow status 1` shows the progress within a few minutes.
7. Friend: `py -3.12 -m kairu.shadow home`: a branch `shadow/...` on GitHub, a receipt, and the `Kairu-shadow` folder gone.
8. You: `kairu shadow status 1` says returned. `kairu shadow install 1` with a wrong PIN: refused, nothing installed.
   Again with the right PIN: installed.
9. `kairu pack run expense-total lunch 120 and bus 30` (`yes`, PIN): `The total is 150.`
10. A second Shadow, then `kairu shadow recall 2`: within a minute the friend's Shadow is gone and their files are still there.
11. A third, and the friend presses **STOP the Shadow** in the window: it ends at once, nothing is pushed.
