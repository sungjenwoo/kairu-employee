"""The Phase B gate test's 20 questions, and where each must go (BRAIN.md "The gate test").

`py -3.12 tools\\brain_gate.py` routes them on your PC and sends nothing; tests_kairu/test_brain_router.py checks
the same list.
"""

GATE = [  # (question, level, kind, the rule / the action / the privacy class)
    ("what time is it", "L0", "rule", "time"),
    ("Kairu, what's the date today?", "L0", "rule", "date"),
    ("status", "L0", "rule", "status"),
    ("how are you", "L0", "rule", "status"),
    ("hello", "L0", "rule", "greeting"),
    ("usage", "L0", "rule", "usage"),
    ("thanks", "L0", "rule", "thanks"),
    ("pay my electricity bill", "L0", "action", "money.spend"),
    ("please delete this folder", "L0", "action", "files.delete"),
    ("turn off the firewall", "L0", "action", "security.disable"),
    ("show me my saved passwords", "L0", "action", "credentials.reveal"),
    ("who is the prime minister of India", "L3", "cloud", "public"),
    ("what is photosynthesis", "L3", "cloud", "public"),
    ("how do I delete a folder in Windows?", "L3", "cloud", "public"),
    ("explain gravity simply", "L3", "cloud", "public"),
    ("what is the capital of Japan", "L3", "cloud", "public"),
    ("my friend Ravi's number is 9876543210, what should I tell him", "L3", "cloud", "personal"),
    ("I have diabetes, can I eat mangoes?", "L3", "cloud", "personal"),
    ("my password is Tiger@123", "L3", "cloud", "secret"),
    ("build me a website for my shop", "L4", "team", ""),
]
