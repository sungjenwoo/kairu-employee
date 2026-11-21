# Kairu Gate & Link (Phase C)

Your phone and this PC talk through the **Kairu Gate**, a free relay on the internet (ntfy.sh to
start), with **Kairu Link** messages: each one signed by the device that sent it and encrypted so that
only the device it is for can read it. The Gate only passes envelopes along; it cannot read, change or
forge them. Every message from the phone is **only a request**: Guardian decides it by `policy.yaml`,
exactly as if you had typed it here. High still needs "yes" and your PIN typed at this PC, and
Critical is still refused, whatever the phone says.

**Mission Mode** keeps the PC awake with the lid closed while it charges, so it can answer the phone,
and always puts your lid setting back.

Built per *Staged Implementation Plan v1.5* (Phase C) and ADR-014, ADR-018, ADR-023 and ADR-025
(the owner's Phase C decisions, 29 Oct 2026). Parts: C1 Link and pairing, C2 Mission Mode, C3 the queue.

## Set it up

### 1. Update and restart Guardian

In PowerShell, in the project folder:

```
py -3.12 tools\check_guardian.py
$env:Path = "$PWD\.venv-guardian\Scripts;" + $env:Path
kairu guardian quit
kairu guardian run
kairu status
```

`kairu status` now has `link:` and `mission:` lines. `config.yaml` has `link: enabled: true` and
`relay: https://ntfy.sh`: nothing is sent or read until you pair a device.

### 2. Pair your phone (2 minutes)

```
kairu device pair
```

Pairing is High: you see what it does, type `yes` and your PIN. Kairu then shows a QR code, the same
text under it, and a 6-digit code. Both are valid 10 minutes; the code is not in the QR code, and 5
wrong codes cancel the pairing.

The Kairu phone app comes in Phase D. Until then the stand-in phone, `kairu-link-test`, pairs and
sends. It is one file of plain Python:

- **In a second terminal on this PC:** `kairu-link-test pair "kairu-pair:1:..." 123456 --name "Second terminal"`
  (copy the command `kairu device pair` prints).
- **On your Android phone, with Termux** (from F-Droid; the Play Store's Termux is out of date):
  `pkg install python`, copy `kairu\link\testclient.py` to the
  phone (for example through Google Drive or a USB cable, into Termux's home folder), then
  `python testclient.py pair "kairu-pair:1:..." 123456 --name "My phone"`. Type the long text
  exactly; it is easier to send it to yourself, for example in an email to your own address.

`kairu device pair` says `Paired: My phone (dev-...)`. `kairu device list` lists it.

### 3. Try it

On the phone (or in the second terminal):

```
python testclient.py send status
```

Within a few seconds: `PC status: Kairu on your PC is running. Mode: normal. Mission Mode: off ...`.

## Commands

| On the PC | What it does |
| --- | --- |
| `kairu device pair` | pair a device: QR code and 6-digit code, 10 minutes ("yes" and your PIN) |
| `kairu device list` | the paired devices, when each was paired and last heard from |
| `kairu device remove ID` | unpair one: every message from it is refused from then on |
| `kairu link status` | the Gate, the receiver, the paired devices, requests waiting for you |
| `kairu link send ID TEXT` | send a paired device a message |
| `kairu link waiting` | the phone's High requests, waiting for "yes" and your PIN |
| `kairu link approve N` / `refuse N` | answer one; approving needs "yes" and your PIN, here |
| `kairu mission-mode on` / `off` / `status` | Mission Mode ("yes" and your PIN to turn it on) |

| On the stand-in phone (`kairu-link-test`, or `python testclient.py` on Termux) | |
| --- | --- |
| `pair TEXT CODE --name NAME` | pair with the PC |
| `send status` | how the PC is |
| `send command demo.count seconds=5 quiet=true` | ask for an action: Guardian decides; Low runs |
| `send command security.disable` | Critical: always refused |
| `send command device.pair` | High: waits for `kairu link approve N` at the PC |
| `send mission "Find tomorrow's train times"` | kept as a request only (missions run from Phase I) |
| `ask "who is the prime minister of India"` | ask Kairu's brain (Phase B, BRAIN.md): a short answer back |
| `send status --age 600` | dated 10 minutes ago: refused as too old |
| `replay` | the last message again, unchanged: refused as a replay |
| `listen --seconds 60` | show what the PC sends |

## Mission Mode

`kairu mission-mode on` (High: "yes" and your PIN) starts only while the PC is plugged in. It:

- keeps Windows from sleeping (`SetThreadExecutionState`: the system, not the screen; the screen still
  turns off);
- sets **When I close the lid** to **Do nothing** for mains power only, after writing your own value
  to `data\mission-mode.json`. On battery your own setting always applies;
- ends by itself when you unplug the PC (checked every 2 seconds), after **4 hours**, at **85 °C**
  where Windows gives a temperature, or when the processor stays above **85 % for 10 minutes**
  (all in `config.yaml`, `mission_mode:`). When it ends at a limit, the actions your phone started
  are stopped too, and the phone is told.

**Heat, honestly.** Windows gives a temperature to a normal program only on some PCs (the "Thermal
Zone Information" counter). **This PC gives none**: the counter exists but has no data. So here
Mission Mode cannot see heat at all; it relies on the time cap and the CPU cap, which only limit how
long and how hard the PC works with the lid closed. Keep the PC on a hard surface, not in a bag.

**Your lid setting always comes back:**

| How Mission Mode ends | Who puts the setting back |
| --- | --- |
| unplugged, time cap, heat, CPU cap | Mission Mode itself, at once |
| `kairu mission-mode off` | Guardian, as the action ends |
| a stop: Ctrl+Alt+K, the tray's STOP, `kairu stop` | Guardian, as the action is halted (within a second) |
| `kairu guardian quit` | Guardian, before it ends |
| sign-out, shutdown, restart | Guardian, as it ends; if Windows ends it first, at its next start |
| `kairu stop` while Guardian is not running | `kairu stop` itself |
| a crash, End task, a power cut | Guardian, the next time it starts (Task Scheduler starts it within a minute) |

`kairu mission-mode status` shows whether the setting is changed, and how the last Mission Mode
ended. To check Windows itself: `powercfg /qh SCHEME_CURRENT SUB_BUTTONS LIDACTION` (the
"Current AC Power Setting Index" is `0x00000001`, Sleep, on this PC).

Two things Windows does that Kairu cannot change: with the lid already closed when Mission Mode
ends, Windows does not sleep at once; it sleeps after its normal idle time. And this PC uses Modern
Standby ("S0 Low Power Idle"): the gate test below is what shows that it stays reachable with the lid
closed.

## The gate test (about 20 minutes, the Termux phone)

The plan's gate: *with the lid closed in Mission Mode, the PC receives a phone message and replies
within seconds; a replayed old message is rejected.*

1. Plug the PC in. `kairu mission-mode on` (`yes`, PIN). `kairu mission-mode status` says ON.
2. Pair the phone (step 2 above), with the phone on mobile data, not your Wi-Fi, so the message
   really goes through the internet.
3. Close the lid. Wait 5 minutes (the screen is off; on Modern Standby this is when it would sleep).
4. On the phone: `python testclient.py send status`. Within a few seconds: `PC status: ...
   Mission Mode: on`. Note how many seconds it took.
5. `python testclient.py replay`: no reply (the PC refused it as a replay).
6. `python testclient.py send status --age 600`: `Kairu refused your message: too old`.
7. `python testclient.py send command security.disable`: `Refused security.disable: Critical tier`.
8. `python testclient.py send command device.pair`: `device.pair is High tier: it waits ... at the PC`.
   Nothing runs.
9. Open the lid. `kairu link waiting` shows it; `kairu link refuse 1`.
10. `kairu mission-mode off`. Then `powercfg /qh SCHEME_CURRENT SUB_BUTTONS LIDACTION`: the AC value is
    your own again (`0x00000001`).
11. Optional: `kairu mission-mode on`, then unplug the charger: within seconds `kairu mission-mode
    status` says it ended because the PC was unplugged, and the lid setting is back.

Please send me the output of `kairu link status`, `kairu mission-mode status` and
`kairu audit show -n 40`, and the seconds from step 4.

## Gate test result (29 Oct 2026)

**Passed.** Run by the owner on their own PC (Dell, i5-1135G7, Windows 11, Modern Standby), with the
Guardian installed in `C:\Users\saitej\Kairu-guardian` on this branch (`tools\check_guardian.py`: 351
passed, 0 failed, real Ctrl+Alt+K passed), and a Mivi phone with Termux (from F-Droid) as the stand-in
phone, through the real ntfy.sh. Times are the PC's (IST).

**Step 4: the reply came 1 second after the phone's message, with the lid shut for 8 minutes 55 seconds.**
A watcher that only recorded Windows' lid notifications logged the lid shut at 19:24:20 and opened at
19:34:02; ntfy.sh logged the phone's message at 19:33:15 and the PC's reply at 19:33:16. The phone was on
mobile data (no Wi-Fi), the PC on mains, Mission Mode on, and Windows logged no standby or power change
in that time.

| Step | Result | Evidence |
| --- | --- | --- |
| 1 Mission Mode on | Pass | Approved with "yes" and the PIN at 18:27; lid on mains "Do nothing" (`0x00000000`), battery unchanged |
| 2 Pair the phone | Pass | Approved with "yes" and the PIN; paired 15:35 with the 6-digit code; the receiver started by itself |
| 3 Lid closed 5 minutes | Pass | Lid shut 19:24:20 to 19:34:02 (watcher) |
| 4 Status reply within 10 seconds | Pass | **1 s** (phone 19:33:15, PC 19:33:16 on ntfy.sh); mobile data; PC on mains |
| 5 Replay | Pass | 18:29:45: refused as `replayed`; no reply |
| 6 A message dated 10 minutes ago | Pass | 18:30:28: refused as `expired`; the phone was told "too old" |
| 7 `security.disable` from the phone | Pass | 18:31:22: denied, Critical; its details recorded only as a hash |
| 8 `device.pair` from the phone | Pass | 18:32:30 and 19:43:04: High, waits for "yes" and the PIN at the PC; nothing ran |
| 9 `kairu link waiting`, `kairu link refuse` | Pass | 19:45:48: refused at the PC; nothing ran; the phone was told |
| 10 Mission Mode off, lid setting back | Pass | 19:48:16: ended, lid setting put back 0.15 s later; `powercfg` shows `0x00000001` (Sleep) |
| 11 Unplug | Pass (unplanned) | 15:51:42 the charger lost power: Mission Mode ended within a second, the lid setting went back to Sleep, the phone was told, and the PC then went to Modern Standby as it normally does |

Replies through ntfy.sh took 1–2 seconds on every step. `kairu audit verify`: 264 rows, intact, anchor
agrees; the audit rows hold message hashes, never the messages' words.

**Notes.** Steps 5 to 8 were run with the lid open (they test refusals, not the lid); the phone may have been
on Wi-Fi then. Earlier tries of step 4 did not count: the lid was not fully shut, or not for 5 minutes, which
the watcher showed. A small fault was seen: the phone's `status` still counted a High request as waiting
after its 10 minutes had passed, because expired requests are only cleared when the waiting list is read
(at 18:45 it said "Waiting for your PIN: 1" for a request that ended at 18:42). It changes no decision
(an expired request can never be approved); a fix is proposed separately.

The Termux phone stays paired (`dev-e66e99310c81c6b6`, "My phone") until the Phase D app replaces it; then
`kairu device remove dev-e66e99310c81c6b6`.

## How the safety rules are kept

- **A message is a request, never an order.** The receiver (`link.receive`) tells Guardian only which
  paired device, the message type, the message's SHA-256 and, for a command, the action and its
  details; for a question (type `ask`, Phase B) its words, which Guardian hands only to `brain.ask`
  (BRAIN.md). Guardian decides by `policy.yaml` as for any request. A mission's, doubt's or report's
  words never leave the receiver; Kairu acts on none of them in Phase C.
- **The phone cannot approve.** No request from the receiver carries a PIN, a "yes" or an approval:
  Guardian refuses any field it does not expect. High waits up to 10 minutes for `kairu link approve N`,
  where you see the action and its details and type "yes" and your PIN here. A "yes" or PIN inside a
  message is only text. (Fingerprint approval on the phone comes in Phases D and F, ADR-023.)
- **Critical stays blocked**, on every path. The tier a message claims decides nothing.
- **Hashes, not words.** Guardian's audit log keeps each message's hash, sender, type and the decision;
  the details of a phone's request are kept as a hash (`details_sha256`), never as text.
- **Signed and encrypted.** Ed25519 signatures and X25519 encryption (libsodium's `crypto_box`, through
  PyNaCl). Each device has its own keys; this PC keeps only their public halves, in `data\link.db`.
  A device's id is made from its signing key, so a stranger cannot take a paired device's id.
- **This PC's keys** are made at the first pairing, in `data\link-pc.key`, sealed with DPAPI for your
  Windows account (mode 600 on Linux), like the Gmail key. Nothing in Kairu shows them.
- **Refused:** not from a paired device, changed on the way, a bad signature, addressed to another
  device, older than 5 minutes, dated in the future, or seen before (its random nonce is remembered
  for 13 hours). The phone is told when its message was too old or could not be read, so it can send
  again; replays and strangers get no answer.
- **Stop.** The receiver, every reply (`link.send`), pairing and Mission Mode are Guardian actions in
  Guardian's Job Object: Ctrl+Alt+K, the tray and `kairu stop` end them within a second with everything
  else. In Safe Mode the receiver does not start again until you resume, and no reply goes out.
- **Low memory.** Guardian itself never loads PyNaCl; only the receiver and each short-lived reply do.
- **Replies are Guardian's own actions.** Each reply is a `link.send` (Low), decided and recorded like
  any action; the relay's address comes from Guardian's `config.yaml`, never from a message.

## Old messages and the queue (C3)

When the PC is off, messages wait in the Gate: ntfy.sh keeps them 12 hours. When Guardian starts
(in normal mode), the receiver reads from where it stopped, so what waited is handled first. Each
Gate message is handled at most once: its nonce is remembered before Guardian is told.

The 5-minute rule is kept like this, so that waiting in the queue never lets a command run late:

- every message must have **reached the Gate** within 5 minutes of being signed;
- a **command, status or call request** must also be at most 5 minutes old **when the PC reads it**.
  One that waited longer is refused as too old, and the phone is told to send it again;
- a **mission, doubt or report** may wait in the Gate up to 12 hours. In Phase C it is only
  acknowledged ("kept as a request only"). From D4 (PHONE.md, ADR-037), a mission that is an order for the task
  core (`{"action": "task.order", ...}`) runs when Guardian next runs, each step decided by Guardian; any other
  mission is still only acknowledged.

The Gate's time is not signed, so a dishonest relay could hold a mission back for up to 12 hours (it
still could not read, change or forge it); it can never hold back a command.

## The Gate: ntfy.sh, and moving it home

The plan left the free relay to be chosen in Phase C after checking its free limits. ntfy.sh, checked
on 28 Oct 2026 with `https://ntfy.sh/v1/account` (no account): **250 messages a day per IP address**,
messages kept **12 hours**, and a rate limit on requests (a burst, then one request every few
seconds; Kairu waits and tries again, longer each time, when told "too many requests"). Each reply
from the PC is one message; reading costs one long-lived connection. Messages are sent with
`Firebase: no`, so ntfy.sh does not pass them to Google.

What ntfy.sh can see: the two device ids, the topic, each envelope's length and time. Each device has
its own topic of 128 random bits, sent to the phone encrypted during pairing.

**A home relay later** (ADR-018: an old Android phone at home): run an ntfy server on an always-on
device at home, set `link.relay` in `config.yaml` (for example `http://192.168.1.20:8080`), restart
Guardian, and pair the phone again (the relay's address is part of the pairing). Messages stay end-to-end encrypted, so plain `http` on
your own network shows only the same envelopes.

## Measured while building (28 Oct 2026)

`tools/check_guardian.py` on the owner's PC (i5-1135G7, 7.7 GB, Windows 11), with a stand-in relay on
the PC: 351 passed, 0 failed. GitHub's CI: Windows 351 passed, Linux 335 passed.

- the phone's `status` to the PC's reply: **0.42 s** (CI: 0.44 s Windows, 0.16 s Linux); most of it is
  starting the `link.send` process;
- a stop with the receiver, Mission Mode and an action the phone started all running: all halted in
  **0.12 s**, and the lid setting back right after;
- the Guardian program with Kairu Link: **34 MiB** (98 MiB for a moment during a PIN check, as before);
  it never loads PyNaCl (a test checks it);
- the receiver (`link.receive`, with PyNaCl and HTTPS loaded): **31 MiB** (26 MiB on Linux);
- the stand-in phone's own crypto: about 6 ms to sign, 9 ms to encrypt a message.

The timings through the real ntfy.sh come from the gate test above.

## Not built yet, and known limits

- **The phone app** (Phase D): scanning the QR code, fingerprint approvals, notifications. Until then the
  stand-in phone is for tests, and High is approved only at the PC.
- **Waking a sleeping PC**: not part of Phase C any more. The owner moved it to when the home Gate (an
  old phone at home) exists (Plan v1.5, ADR-025): a sleeping or switched-off PC cannot read the Gate,
  and waking it needs a device on the home network. Until then Mission Mode keeps the PC awake while it
  charges, and messages wait in the queue.
- **Missions** are acknowledged only, except an order sent as a mission from the phone app (D4, PHONE.md).
- **Heat:** this PC gives no temperature (above); the CPU cap is a stand-in, not a measurement.
- **Modern Standby:** whether this PC stays reachable with the lid closed is what the gate test shows.
- **The Gate's time** is not signed (above). **ntfy.sh's limits** can change; `https://ntfy.sh/v1/account`
  shows them.
- **D18 (disk encryption) is still open.** The keys are sealed with DPAPI as asked for this phase; the
  limit is the same as the audit anchor's and the Gmail key's: a program already running as you could
  unseal them, read `data\link.db`, or ask Guardian things itself.
- **A pairing offer** is shown as text too: someone who sees your screen during those 10 minutes can
  post to the pairing topic, but cannot pair without the code (5 tries).
- **The QR code** is drawn with text blocks; in a terminal with a dark background some scanners need it
  inverted. The phone app will read it in Phase D.
- **The stand-in phone's crypto** is written out in Python for tests (checked against libsodium); it is
  slow and not hardened against timing attacks, so the phone app will not use it.

## Files

```
kairu/link/
  kinds.py       the fixed words and limits: message types, tiers, refusal reasons, the 5-minute and queue rules
  message.py     sealing and opening a message (Ed25519 + X25519), and every check
  keys.py        this PC's keys (sealed), device ids
  store.py       data/link.db: paired devices, seen nonces and Gate ids, where reading stopped; the pairing offer
  relay.py       the ntfy client: publish, long poll, Backoff
  receive.py     link.receive: reads the Gate, checks each message, tells Guardian
  send.py        link.send: one message to one paired device
  pairing.py     device.pair: the offer, the code, the pairing request
  devices.py     device.remove
  testclient.py  kairu-link-test, the stand-in phone (standard library only)
kairu/mission.py Mission Mode: mains power, keep awake, the lid setting and putting it back, the limits
```
