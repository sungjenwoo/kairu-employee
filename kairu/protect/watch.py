"""protect.watch: the Guardian monitors' one background program. Guardian starts it; a stop ends it.

    every `check_seconds`  deadline reminders; approved folders (kairu/protect/folders.py); devices
                           plugged in (kairu/protect/devices.py); Windows Security (kairu/protect/security.py)
    every `gmail_seconds`  new emails in the inbox (kairu/protect/gmail.py)

What it finds goes into data/protection.db, then a short report goes to Guardian (report_all): the
alert's number, source, kind, severity and a fingerprint, never its text. Guardian records that in
its audit log and shows it in the tray. Reporting is all this program ever asks of Guardian: it
cannot ask for an action, an approval or a change of rules (tests_kairu/test_protect_rules.py
checks that no monitor module can).

It ends by itself (exit code 0) when there is nothing to watch: no Gmail connected, no open
deadline, no folder, devices or Windows Security approved (`kairu protect setup-pc`), or everything paused. `kairu deadline add`, `kairu protect connect-gmail` and
`kairu protect resume` start it again.

Health: each source shows Active, Degraded, Disconnected, Permission removed or Paused. A source
that stops working gives one "protection degraded" alert. When the monitors were not running for a
while (the PC was off, or a stop), the next start says "not monitored from ... to ...".
"""

import hashlib
import sys
import time
from datetime import datetime, timedelta

from kairu import channel
from kairu.protect import deadlines
from kairu.protect.devices import DeviceMonitor
from kairu.protect.folders import FolderMonitor
from kairu.protect.gmail import ACCOUNT, GmailMonitor, PermissionRemoved, Unreachable
from kairu.protect.store import (ACTIVE, DEGRADED, DISCONNECTED, NOT_SET_UP, PAUSED, PERMISSION_REMOVED, Finding,
                                 ProtectStore, iso, now_utc, parse_iso)
from kairu.protect.security import SecurityMonitor, Unsupported

UNSUPPORTED = "Unsupported on this device"
PC_SOURCES = ("folders", "devices", "security")

FAILURES_BEFORE_DISCONNECTED = 3
LAST_WATCHED = "watch:last"  # when the monitors last ran a round
GAP_AFTER = timedelta(minutes=10)  # silence longer than this, and longer than 3 rounds, is reported as a gap


def main(data_dir: str, check_seconds: float = 60, gmail_seconds: float = 120) -> None:
    watcher = Watcher(data_dir, check_seconds, gmail_seconds)
    while watcher.round():
        time.sleep(check_seconds)


class Watcher:
    def __init__(self, data_dir: str, check_seconds: float = 60, gmail_seconds: float = 120, transport=None,
                 devices=None, security=None):
        self.data_dir, self.check_seconds, self.gmail_seconds = data_dir, check_seconds, gmail_seconds
        self.store = ProtectStore(data_dir)
        self.gmail = GmailMonitor(self.store, data_dir, transport) if transport else GmailMonitor(self.store, data_dir)
        self.folders = FolderMonitor(self.store, data_dir)
        self.devices = DeviceMonitor(self.store, devices) if devices else DeviceMonitor(self.store)
        self.security = SecurityMonitor(self.store, security) if security else SecurityMonitor(self.store)
        self.next_gmail = 0.0
        self.started = now_utc()
        self.last_cleanup = 0.0
        self._note_gap()

    def watching(self) -> list[str]:
        """The sources there is something to watch on, and that are not paused."""
        sources = []
        removed = (self.store.source("gmail") or {}).get("state") == PERMISSION_REMOVED  # until you connect again
        if self.gmail.set_up() and not self.store.paused("gmail") and not removed:
            sources.append("gmail")
        if self.store.deadlines() and not self.store.paused("deadlines"):
            sources.append("deadlines")
        on = {"folders": self.folders.set_up(), "devices": self.store.setting("devices:on") == "1",
              "security": self.store.setting("security:on") == "1"}
        sources += [name for name in PC_SOURCES if on[name] and not self.store.paused(name)]
        return sources

    def round(self) -> bool:
        """One round of checks. False when there is nothing left to watch, so the program ends."""
        sources = self.watching()
        self._show_paused()
        if not sources:
            self.store.set_setting(LAST_WATCHED, None)  # ended on purpose: the next start is not a gap
            self.report_all()
            return False
        findings = []
        if "deadlines" in sources:
            findings += deadlines.reminders(self.store)
            open_now = len(self.store.deadlines())
            self.store.set_source("deadlines", ACTIVE, f"{open_now} open", checked=True)
        for monitor in (self.folders, self.devices, self.security):
            if monitor.name in sources:
                findings += self._check_pc(monitor)
        if "gmail" in sources and time.monotonic() >= self.next_gmail:
            self.next_gmail = time.monotonic() + self.gmail_seconds
            findings += self._check_gmail()
        for finding in findings:
            self.store.add_alert(finding)
        self.store.set_setting(LAST_WATCHED, iso(now_utc()))
        self.report_all()
        if time.monotonic() - self.last_cleanup > 86400:
            self.last_cleanup = time.monotonic()
            self.store.forget_old()
        return True

    def _check_gmail(self) -> list[Finding]:
        before = self.store.source("gmail") or {}
        try:
            findings = self.gmail.check()
        except PermissionRemoved as error:
            self.store.set_source("gmail", PERMISSION_REMOVED, str(error), checked=True)
            return [self._degraded("gmail", "permission", f"Gmail: {error}")] if before.get("state") != PERMISSION_REMOVED else []
        except Unreachable as error:
            failures = int(before.get("failures") or 0) + 1
            state = DISCONNECTED if failures >= FAILURES_BEFORE_DISCONNECTED else DEGRADED
            self.store.set_source("gmail", state, f"could not reach Gmail ({error}); trying again", failures=failures)
            if failures == FAILURES_BEFORE_DISCONNECTED:
                return [self._degraded("gmail", "unreachable", f"Gmail could not be reached {failures} times in a row "
                                                               f"({error})")]
            return []
        except Exception as error:  # anything unexpected: say so, keep the other sources watched, try again next time
            self.store.set_source("gmail", DEGRADED, f"the check failed ({type(error).__name__}: {error}); trying again")
            print(f"protect.watch: the Gmail check failed ({type(error).__name__}: {error})", file=sys.stderr)
            return []
        self.gmail.gap = None  # caught up
        account = self.store.setting(ACCOUNT)
        self.store.set_source("gmail", ACTIVE, f"connected as {account}, read-only" if account else "connected, read-only",
                              checked=True, failures=0)
        return findings

    def _check_pc(self, monitor) -> list[Finding]:
        """One round of a PC monitor; a failure is shown on its source and never stops the others."""
        before = self.store.source(monitor.name) or {}
        try:
            findings, note = monitor.check()
        except Unsupported as why:
            self.store.set_source(monitor.name, UNSUPPORTED, str(why), checked=True)
            return []
        except Exception as error:
            failures = int(before.get("failures") or 0) + 1
            self.store.set_source(monitor.name, DEGRADED, f"the check failed ({type(error).__name__}: {error})",
                                  failures=failures)
            print(f"protect.watch: the {monitor.name} check failed ({type(error).__name__}: {error})", file=sys.stderr)
            if failures == FAILURES_BEFORE_DISCONNECTED:
                return [self._degraded(monitor.name, "failing", f"the {monitor.name} check failed {failures} times in a row "
                                                                f"({error})")]
            return []
        self.store.set_source(monitor.name, ACTIVE, note, checked=True, failures=0)
        return findings

    def _degraded(self, source: str, why: str, text: str) -> Finding:
        return Finding(key=f"degraded:{source}:{why}:{iso(now_utc())}", source="protect", kind="protection_degraded",
                       severity="warning", classification="Confirmed fact", title=f"Protection degraded: {source} is "
                                                                                   "not being watched",
                       lines=[("Source", source), ("Since", _local(now_utc()))], why=[text],
                       you_can="`kairu protect status` shows each source. Kairu never reports a source as watched "
                               "while it is not." + (" `kairu protect connect-gmail` connects Gmail again."
                                                     if why == "permission" else " It keeps trying by itself."))

    def _note_gap(self) -> None:
        """If the monitors were silent for a while, say so, and let the Gmail monitor mark what it catches up on."""
        last = parse_iso(self.store.setting(LAST_WATCHED))
        if last is None:
            return
        silent = self.started - last
        if silent < max(GAP_AFTER, timedelta(seconds=3 * max(self.check_seconds, self.gmail_seconds))):
            return
        self.gmail.gap = (last, self.started)
        watched = self.watching()
        if not watched:
            return
        self.store.add_alert(Finding(
            key=f"gap:{iso(last)}", source="protect", kind="monitoring_gap", severity="info", classification="Confirmed fact",
            title=f"Not monitored from {_local(last)} to {_local(self.started)}",
            lines=[("Sources", ", ".join(watched)), ("For", _duration(silent))],
            why=["the monitors were not running (the PC was off or asleep, Guardian was not running, or a stop)"],
            not_checked=["anything that happened in that time and left no trace in Gmail",
                         "devices plugged in and out again, and files that came and went, during that time"],
            you_can="Nothing. Gmail is caught up from where it stopped; what arrived meanwhile is marked \"found late\". "
                    "Deadline reminders that fell in the gap come now. New files and devices still present are "
                    "checked on the first round."))

    def _show_paused(self) -> None:
        for name in ("gmail", "deadlines", *PC_SOURCES):
            if self.store.paused(name):
                self.store.set_source(name, PAUSED, "paused by you (`kairu protect resume` to watch again)")
            elif name == "gmail" and not self.gmail.set_up():
                current = self.store.source("gmail")
                if current and current["state"] not in (NOT_SET_UP,) and not current["state"].startswith("Signing"):
                    self.store.set_source("gmail", NOT_SET_UP, "not connected (`kairu protect connect-gmail`)")

    def report_all(self) -> None:
        """Tell Guardian about each new alert: number, source, kind, severity, fingerprint. Nothing else is sent."""
        for number, source, kind, severity, key in self.store.unreported():
            try:
                reply = channel.request(self.data_dir, {
                    "op": "report", "source": source, "kind": kind, "severity": severity, "alert": number,
                    "fingerprint": hashlib.sha256(key.encode()).hexdigest()}, timeout=10)
            except channel.ChannelError as error:  # Guardian is not there now: the next round tries again
                print(f"protect.watch: Guardian did not take the report of alert {number} ({error})", file=sys.stderr)
                return
            if reply.get("verdict") != "ok":
                print(f"protect.watch: Guardian refused the report of alert {number}: {reply.get('reason')}", file=sys.stderr)
            self.store.mark_reported(number)


def _local(moment: datetime) -> str:
    local = moment.astimezone()
    return f"{local.strftime('%a')} {local.day} {local.strftime('%b')}, {local.strftime('%H:%M')}"


def _duration(span: timedelta) -> str:
    minutes = int(span.total_seconds() // 60)
    if minutes >= 120:
        return f"about {round(minutes / 60)} hours"
    return f"{minutes} minutes"
