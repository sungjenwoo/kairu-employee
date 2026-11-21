"""The Windows Security monitor: notices when the firewall or the antivirus is turned off. Read-only.

It asks Windows Security Center (WscGetSecurityProviderHealth in wscapi.dll, the same source as
the Windows Security app; no administrator rights needed) how the firewall and the antivirus are:

  security_off       one of them is off or in a poor state (high)
  security_restored  it is back on (info)

Each change gives one alert, not one every round. Kairu never turns a protection on or off itself:
changing security settings is Critical, always refused. Windows only; elsewhere it shows
"Unsupported on this device".
"""

import sys

from kairu.protect.store import Finding, ProtectStore, iso, now_utc

PROVIDERS = {"firewall": 0x1, "antivirus": 0x4}
NAMES = {"firewall": "the firewall", "antivirus": "the antivirus (Microsoft Defender or your own)"}
GOOD, NOT_MONITORED, POOR, SNOOZE = 0, 1, 2, 3
WORDS = {GOOD: "on", NOT_MONITORED: "not monitored", POOR: "off or not working", SNOOZE: "snoozed"}
LAST = "security:last:"  # in protection.db settings: the last state seen of each


class Unsupported(Exception):
    pass


def health(provider: int) -> int:
    """The Security Center's health for one provider. Raises Unsupported when Windows cannot tell."""
    if sys.platform != "win32":
        raise Unsupported("Windows Security Center is Windows only")
    import ctypes
    try:
        wscapi = ctypes.WinDLL("wscapi")
    except OSError:
        raise Unsupported("Windows Security Center is not on this PC") from None
    result = ctypes.c_int(-1)
    code = wscapi.WscGetSecurityProviderHealth(ctypes.c_uint(provider), ctypes.byref(result))
    if code != 0 or result.value not in WORDS:
        raise Unsupported(f"Windows Security Center did not answer (code {code & 0xFFFFFFFF:#x})")
    return result.value


class SecurityMonitor:
    name = "security"

    def __init__(self, store: ProtectStore, reader=health):
        self.store, self.reader = store, reader

    def check(self) -> tuple[list[Finding], str]:
        """(findings, a note). Raises Unsupported if neither can be read."""
        findings, notes, read = [], [], 0
        for name, provider in PROVIDERS.items():
            try:
                state = self.reader(provider)
            except Unsupported:
                notes.append(f"{name} unknown")
                continue
            read += 1
            notes.append(f"{name} {WORDS[state]}")
            before = self.store.setting(LAST + name)
            self.store.set_setting(LAST + name, str(state))
            bad, was_bad = state in (POOR, SNOOZE), before is not None and int(before) in (POOR, SNOOZE)
            if bad and not was_bad:
                findings.append(self._off(name, state))
            elif was_bad and state == GOOD:
                findings.append(self._back(name))
        if not read:
            raise Unsupported("; ".join(notes))
        return findings, ", ".join(notes)

    def _off(self, name: str, state: int) -> Finding:
        return Finding(key=f"security:{name}:off:{iso(now_utc())}", source="security", kind="security_off",
                       severity="high", classification="Confirmed fact",
                       title=f"Windows protection is off: {name}",
                       lines=[("What", NAMES[name]), ("State", WORDS[state]),
                              ("Seen at", now_utc().astimezone().strftime("%a %d %b %Y, %H:%M"))],
                       why=["Windows Security Center reports it as " + WORDS[state]],
                       not_checked=["who or what turned it off"],
                       you_can="If you turned it off yourself for a moment, turn it back on in the Windows Security app "
                               "when you are done. If not, turn it back on now, and press Ctrl+Alt+K if anything else "
                               "looks wrong. Kairu never changes security settings itself.")

    def _back(self, name: str) -> Finding:
        return Finding(key=f"security:{name}:on:{iso(now_utc())}", source="security", kind="security_restored",
                       severity="info", classification="Confirmed fact",
                       title=f"Windows protection is back on: {name}", lines=[("What", NAMES[name])],
                       why=["Windows Security Center reports it as on again"])
