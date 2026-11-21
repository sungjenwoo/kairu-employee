"""Guardian protection (Phase J): Guardian monitors that watch the sources you connected and raise alerts.

The monitors have no authority. They run as one Guardian action (protect.watch) in their own
process, read only, and report what they find; they never act, approve or change a rule. Guardian
records each alert in its audit log (kind, source, time and a fingerprint, never the email text)
and shows it in the tray. What each alert says lives in data/protection.db (kairu/protect/store.py).
See PROTECTION.md.
"""
