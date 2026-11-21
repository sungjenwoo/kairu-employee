"""The words Guardian accepts in a monitor's report: sources, kinds of alert and severities. Constants only.

Guardian (kairu/guardian_program.py) refuses a report that names anything else, and shows the tray
pop-up only from the titles here, so no text from an email ever reaches Guardian or its audit log.
"""

SOURCES = ("gmail", "deadlines", "folders", "devices", "security", "protect")
SEVERITIES = ("info", "warning", "high")  # info: listed only; warning and high: also a tray pop-up

KINDS = {  # kind -> the tray pop-up's title
    "phishing": "Suspected phishing email",
    "ai_instructions": "An email gives orders to an AI",
    "account_alert": "Account security notice",
    "deadline_found": "Deadline found in an email",
    "deadline_soon": "Deadline coming up",
    "deadline_passed": "Deadline passed",
    "risky_download": "A program was downloaded",
    "disguised_file": "A file disguised as another kind",
    "many_files_changed": "Many files changed at once",
    "new_device": "New device connected",
    "new_keyboard": "New keyboard connected",
    "security_off": "Windows protection is off",
    "security_restored": "Windows protection is back on",
    "protection_degraded": "Protection degraded",
    "monitoring_gap": "Not monitored for a while",
}

CLASSIFICATIONS = ("Confirmed fact", "Suspected", "Unknown")
