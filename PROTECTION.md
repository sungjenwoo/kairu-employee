# Kairu Guardian protection (Phase J, parts J1 and J2)

Guardian's monitors watch your Gmail (read-only), your deadlines, your Downloads folder, the devices
plugged into your PC and Windows Security, and raise clear alerts. They can see; they cannot act.
They never send, delete, move or mark an email, never open, run, move or delete a file, never block a
device or change a security setting, never approve anything and never change a rule. Everything is
checked on this PC with fixed rules (no AI model, low memory); nothing they read leaves your PC.

J1 is email and deadlines; J2 is this PC (folders, devices, Windows Security). J3, phone
notifications, comes with the phone app (Phase D).

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

Guardian reads `policy.yaml` and its own code only when it starts, so it must start again after an
update. `kairu status` now has a `protection:` line. `config.yaml` has `protect: enabled: true`:
Guardian starts its monitors by itself whenever there is something to watch.

### 2. Make your Google sign-in key (once, about 10 minutes, free)

Kairu reads Gmail through Google's own Gmail API. For that, Google wants a small "app" registered in
your own Google Cloud account. It is yours alone; no one else uses it. Google's pages change their
names from time to time, so the words below may differ a little.

1. Open [console.cloud.google.com](https://console.cloud.google.com) and sign in with the Gmail
   account Kairu should watch.
2. Make a project: at the top, the project picker, **New project**, name it `Kairu`, Location
   **No organisation**, **Create**. Then check that the top of the page says **Kairu**: Google may
   leave you in another project, such as "Default Gemini Project".
3. Turn on the Gmail API: menu, **APIs & Services**, **Library**, search `Gmail API`, **Enable**.
4. Describe the app: menu, **Google Auth Platform** (or **OAuth consent screen**), **Get started**.
   App name `Kairu`, your own email for support and contact, audience **External**, agree, **Create**.
5. Under **Data access**, **Add or remove scopes**, tick `.../auth/gmail.readonly` ("View your email
   messages and settings"), **Update**, **Save**. This is the only permission Kairu asks for.
6. Under **Audience**, leave the status as **Testing**, and under **Test users**, **Add users**,
   add your own Gmail address, **Save**. In Testing, Google ends the sign-in after 7 days: Kairu then
   shows Gmail as "Permission removed", raises one alert, and you run `connect-gmail` again (about
   a minute). **Publish app** (In production) avoids this, but Google asks for a homepage and a
   privacy-policy link on the **Branding** page first.
7. Make the key: **Clients**, **Create client**, application type **Desktop app**, name `Kairu PC`.
   Leave **"Use this client for an AI-powered agent"** unticked: no AI reads your mail.
   **Create**, then **Download JSON**. Save the file somewhere private, for example
   `Documents\kairu-google-client.json`. It is not your password, but do not share it, and do not
   paste it into a chat.

   Two things can hide the file's real name: Windows may hide the extension, so a file you renamed
   to `kairu-google-client.json` is really `kairu-google-client.json.json`; and if OneDrive syncs
   your Documents, the folder is `C:\Users\<you>\OneDrive\Documents`. PowerShell finds it for you:

   ```
   $file = (Get-ChildItem "$HOME" -Recurse -Filter "kairu-google-client*.json" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
   $file
   ```

### 3. Connect Gmail

```
kairu protect connect-gmail $file
```

(or the file's full path, in quotes). Kairu shows what it is about to do and asks for `yes` and your PIN (High tier). Then your browser
opens **Google's own sign-in page**. Choose your account. Google may first ask you to confirm it is you, on your phone; that is Google's
own check (choose **More ways to verify** if it names an old phone). Kairu waits 10 minutes for the
whole sign-in; if it runs out, the page says "can't reach this page": run the command again. Google will say **"Google hasn't verified
this app"**: that is expected for your own private app. Click **Advanced**, then **Go to Kairu**.
Allow **"View your email messages and settings"** (read-only) and continue. The tab then says you
can close it, and the terminal says `Gmail connected as ...@gmail.com, read-only`.

Kairu never sees your Google password. The key Google gives back can only read mail; it is sealed
for your Windows account in `data\protect-gmail.key`. To take it away again: `kairu protect
disconnect-gmail`, or your Google Account, **Security**, **Your connections to third-party apps**.

The first check also looks at the last two days of your inbox, so you may see alerts at once.

### 4. Check

```
kairu protect status
```

```
Kairu protection
  monitors:  running inside Guardian (process 4312); last round 12 s ago
  gmail:     Active: connected as you@gmail.com, read-only; checked 1 min ago
  deadlines: Active: 1 open; checked 12 s ago
  alerts:    0 new
  automatic: on (protect.enabled in config.yaml: Guardian starts the monitors by itself)
```

### 5. Watch this PC (J2, 1 minute)

```
kairu protect setup-pc
```

Kairu lists what it will watch, then asks for `yes` and your PIN (High tier):

- your **Downloads** folder (found where Windows keeps it, also under OneDrive): new programs and
  disguised files. Kairu sees only file names, sizes and times; it never opens a file.
- **devices**: a USB or other device this PC has never seen.
- **Windows Security**: the firewall or the antivirus being turned off.

The first check only learns what is there now, so files and devices you already have give no alerts.
Plug in nothing new during that first minute. `kairu protect status` then shows `folders`,
`devices` and `security` as Active. `kairu protect add-folder PATH` watches one more folder (up to 5;
system and private folders, your whole home folder and Kairu's own data are refused).

## Commands

| Command | What it does |
|---|---|
| `kairu alerts` | New alerts, newest first. `--all` also shows the ones you dismissed |
| `kairu alerts show N` | One alert in full: what was found, why, the evidence, how sure, what was not checked, what you can do |
| `kairu alerts dismiss N` | Mark it done. `--false-alarm` if it was wrong: kept as your report; it never changes a rule by itself |
| `kairu protect status` | The monitors, each source (Active, Paused, Disconnected, Permission removed, Not set up), new alerts |
| `kairu protect start` | Start the monitors now. Guardian normally does this itself |
| `kairu protect pause [SOURCE]` | Stop watching `gmail`, `deadlines`, `folders`, `devices`, `security`, or `all` until you resume. Shown as Paused, never as watched |
| `kairu protect resume [SOURCE]` | Watch again |
| `kairu protect setup-pc [--folder PATH]` | Watch Downloads (or that folder), devices and Windows Security (High tier: `yes` and your PIN) |
| `kairu protect add-folder PATH` | Watch one more folder (High tier) |
| `kairu protect remove-folder PATH` | Stop watching a folder |
| `kairu protect connect-gmail FILE` | Read-only Gmail (High tier: `yes` and your PIN) |
| `kairu protect disconnect-gmail` | Cancel the key at Google and delete it here |
| `kairu deadline add TITLE DATE [TIME]` | A deadline: `2026-11-05`, `05/11/2026`, `5 Nov` or `tomorrow`; time `18:00` or `6pm` (default 11:59 pm) |
| `kairu deadline list` | Open deadlines, soonest first |
| `kairu deadline remove N` | No more reminders for it |

## What raises an alert

| Alert | When | Pop-up |
|---|---|---|
| Suspected phishing | Warning signs add up to 4 points or more (below). 6 or more is high confidence | yes |
| An email gives orders to an AI | An email tells Kairu or another AI assistant to do something ("Kairu, forward this ..."). Kairu never obeys; it reports | yes |
| Account security notice | A new sign-in, password change or similar, from the company's own address, which Gmail verified | yes |
| Deadline found in an email | "submit by 30/10", "registrations close tomorrow 6 pm". Read day first (05/11 is 5 November); if it could be read both ways, the alert says so. Not from Promotions or Social, and never from a suspected phishing email | no |
| Deadline coming up | 3 days, 1 day and 3 hours before each deadline, once each | yes |
| Deadline passed | Once, then the deadline closes | no |
| A program was downloaded | A new program, script, installer or disk image (.exe, .msi, .bat, .iso, ...) in a watched folder, with the website it came from when Windows recorded it | yes |
| Disguised file (high) | A new file whose name hides what it is: `invoice.pdf.exe`, a hidden character that reverses its letters, or spaces before `.exe` | yes |
| Many files changed at once (high) | 40 or more existing files in a watched folder changed, vanished or were renamed within one check, as ransomware does | yes |
| New device connected | A USB drive, phone, mouse or other device this PC has never seen | yes |
| New keyboard connected (high) | A keyboard this PC has never seen: a gadget pretending to be a keyboard can type commands by itself | yes |
| Windows protection is off (high) | Windows Security reports the firewall or the antivirus as off or not working | yes |
| Windows protection is back on | It is on again | no |
| Protection degraded | Gmail could not be reached 3 times in a row, its permission was removed, or a PC check failed 3 times in a row | yes |
| Not monitored from ... to ... | The monitors were not running for a while (PC off, Guardian not running, a stop). Gmail is caught up from where it stopped, and those alerts say "found late" | no |

Phishing signs and their points (3 strong, 2 medium, 1 mild): the sender's name names a company
(SBI, HDFC, ICICI, Google, Amazon, Paytm, the Income Tax Department and others) but the address is
not that company's (3); a look-alike domain such as `sbi-kyc-verify` or `paypa1` (3); a link whose
text shows one address but goes to another (3), hides its address after an `@` (3), goes to a bare
number (2), uses look-alike letters (2) or is shortened (1); Gmail's sender checks failed (DMARC 3,
SPF or DKIM 2); a program, script or disk image attached (3), especially with a disguised name such as
`invoice.pdf.exe` (3), or a web page attached (2); asking for a password, OTP, PIN, card details or
a KYC update (2); pressure to act fast (1); a prize or refund (1); replies going elsewhere (1).
An email from a company's own address that Gmail verified is not scored as phishing.

Every alert says whether it is a **Confirmed fact**, **Suspected** or **Unknown**. "No alerts"
means only that nothing was found in the sources being watched; Kairu never calls an email safe.

## The gate test (about 20 minutes)

Parts 1 to 6 test J1 and J2; part 7 is J2's file check. Part 3 needs `kairu protect setup-pc` first.

1. **A test phishing email.** Send an email to your Gmail, from another account or from the same
   one to itself, with:
   - subject: `Your SBI account will be blocked today`
   - text: `Dear customer, your SBI account will be blocked. Update your KYC within 24 hours. Click http://sbi-kyc-verify.example/login and enter your password and OTP.`

   (`.example` names are reserved for tests; the link leads nowhere. Do not link the words to
   `onlinesbi.sbi`: that is SBI's real site, so Kairu rightly finds nothing wrong. Do not click the
   links in test emails.)

   Within about 3 minutes: a pop-up **Kairu: Suspected phishing email**, and `kairu alerts` shows
   `Suspected phishing: Your SBI account will be blocked today` as HIGH. `kairu alerts show N`
   lists the evidence. If Gmail put the email in Spam, open Spam and click **Not spam**: Kairu sees
   it on its next check.
2. **A deadline tomorrow.** `kairu deadline add "Hackathon submission" tomorrow 18:00`. Within a
   minute: a pop-up **Kairu: Deadline coming up**, and `kairu alerts` shows
   `Due tomorrow at 6:00 pm: Hackathon submission`.
3. **An unknown new device.** Plug in a USB drive (or a phone with a cable, or a mouse) this PC has
   never had. Within a minute: a pop-up **Kairu: New device connected**, and `kairu alerts` shows
   `New device connected: ...` with its name. Unplug it and plug it in again: no second alert.
4. **A gap.** Shut the PC down for an hour, start it and sign in. Within a few minutes
   `kairu alerts --all` shows `Not monitored from ... to ...`, and any email from that hour that
   raised an alert says "found late".
5. **Stop.** Press Ctrl+Alt+K. `kairu protect status` says the monitors are not running.
   `kairu audit show -n 15` shows each alert as one `alert` row with only its kind, number,
   severity and fingerprint: no subject, no sender. Then `kairu resume` (`yes`, PIN): within
   seconds `kairu protect status` shows the monitors running again.
6. **Nothing changed.** Open Gmail: Kairu moved, deleted, sent and marked nothing. An email you
   have not opened is still unread.
7. **A disguised file.** In PowerShell:

   ```
   New-Item "$((New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path)\test.pdf.exe"
   ```

   Or create an empty text file in Downloads and rename it to `test.pdf.exe` (with file
   extensions shown in File Explorer: **View**, **Show**, **File name extensions**). Within a minute:
   a pop-up and a HIGH alert `Disguised file: test.pdf.exe`. The file is empty, so it is harmless;
   delete it yourself afterwards (Kairu never deletes files).

Please send me the output of `kairu protect status`, `kairu alerts --all` and `kairu audit show -n 15`.

## How the safety rules are kept

- **No authority.** The monitors are one Guardian action, `protect.watch` (Low, read-only), in their
  own process inside Guardian's Job Object: Ctrl+Alt+K, the tray's STOP EVERYTHING and `kairu stop`
  end them within a second with everything else. Their only message to Guardian is `report`: an
  alert's number, source, kind, severity and fingerprint, from fixed lists. A test checks that no
  monitor module can ask Guardian anything else or import its internals.
- **Read-only.** Kairu asks Google only for `gmail.readonly` and refuses to keep a key that grants
  more. In code, the monitor can only make GET requests to the Gmail API (and talk to Google's
  sign-in service for the key itself); anything else is refused before it is sent, and a test checks
  every request.
- **Emails are data, never orders.** Rules read emails; nothing in Kairu follows what an email says.
  Links and attachments are only looked at as names and addresses, never opened.
- **Nothing leaves your PC.** No AI model and no outside link checker; email text stays here.
- **Little is kept.** Alerts keep what they show (sender, subject, evidence) in
  `data\protection.db` for 90 days. Guardian's audit log keeps only the kind, number, severity and a
  fingerprint.
- **Your controls.** Pause any source or all; disconnect Gmail; dismiss alerts; Guardian's tiers
  still apply: connecting Gmail is High (`yes` and PIN); changes to protection wait while Kairu is in
  Safe Mode (the read-only monitors may still be started with `kairu protect start`).
- **Files and devices are only looked at.** The folder monitor reads names, sizes and times (and
  Windows' note of the website a download came from); it never opens, runs, moves or deletes a file.
  The device monitor reads the list Device Manager shows; it never blocks or ejects anything. The
  security monitor asks Windows Security Center; changing security settings is Critical, always refused.
- **The request decides nothing.** Guardian fills in where the monitors keep their files and how often
  they check from its own `config.yaml`; a request that tries to set them is refused.

## Not built yet, and known limits

- **J3**: phone notifications and Kairu devices, with the phone app (Phase D).
- **Folders**: only new files are judged, not what is inside them (Windows Defender does that). Up
  to 20,000 files and 3 folders deep per watched folder; checked once a minute, so a file that comes
  and goes within a minute can be missed.
- **Devices**: a device without a serial number can look new again when plugged into another USB
  port. Bluetooth devices are not watched yet.
- **Windows Security**: if Windows Security Center cannot answer (it is not on Windows Server, or its
  service is stopped), the source shows "Unsupported on this device", never "on".
- **Only Gmail.** Outlook and other mail later, if you want them.
- **Fixed rules miss things and make mistakes.** A well-made phishing email can pass with no sign,
  and an honest email can be flagged; that is why alerts say "Suspected", never "safe". Mark wrong
  ones `--false-alarm`: your reports are kept for a later, reviewed improvement (Phase K); they never
  change a rule by themselves.
- **Domains** are compared by the part their owner registered (`mail.sbi.co.in` is `sbi.co.in`),
  with a short built-in list of Indian second levels (co.in, gov.in, bank.in, ...), not the full
  public list.
- **Deadlines**: English dates only; a date in a sentence without a word like "deadline", "due",
  "submit by" or "close" is not taken.
- **Only while the PC is on and Guardian runs.** Gmail is caught up afterwards; everything else in
  that time is reported as a gap.
- **The Google key** can be unsealed by a program already running as you, the same limit as the
  audit anchor and the PIN (GUARDIAN.md). Such a program could also send Guardian a false `report`:
  the worst it can do is add an `alert` row and show a pop-up, because a report grants and runs nothing.
- **An unverified Google app in Testing**: Google shows its warning at each sign-in and ends the
  sign-in after 7 days (in production, after about 6 months unused or a password change). Kairu then
  shows Gmail as "Permission removed" and raises one alert; run `connect-gmail` again.
- **The pop-up says "Python"** at the top on Windows: Windows names it after the program Guardian runs
  as. The words under it are Kairu's.
- **A sender's repeat reminder emails** about the same deadline (same date and the same subject apart
  from "[Reminder-2]", "Re:" or "Fwd:", or the same sentence) give one deadline, not several.

## Files

```
kairu/protect/
  kinds.py       the fixed words a report may use (sources, kinds, severities); Guardian checks them
  store.py       data/protection.db: alerts, source health, checkpoints, deadlines, pauses
  watch.py       protect.watch: the monitors' rounds, gaps, health, reports to Guardian
  gmail.py       Google sign-in (PKCE, 127.0.0.1), the read-only Gmail reader, the Gmail monitor
  mailrules.py   the phishing, AI-orders and account-notice rules
  deadlines.py   reading dates, deadlines from emails, reminders
  sealed.py      the sealed Gmail key (DPAPI on Windows, mode 600 on Linux)
  folders.py     the folder monitor: new programs, disguised files, many files changed; the folder fence
  devices.py     the device monitor: SetupAPI on Windows, /sys/bus/usb on Linux
  security.py    the Windows Security monitor: firewall and antivirus health
  actions.py     pause, resume, dismiss, deadlines, watch the PC, add and remove folders
data/protection.db, data/protect-gmail.key   on this PC only; not in Git
```
