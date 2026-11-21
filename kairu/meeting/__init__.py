"""The meeting agent (hackathon, HACKATHON.md): meeting in, decision ledger, conflict check, split to clones.

Stage 1, Meeting in, is built (ADR-055 proposed): read.py (files, prompts, Gemini's answer read strictly), hear.py (Gemini
writes a recording down), store.py (data/meetings.db), conduct.py (the Guardian actions), orders.py (the bar's orders) and
commands.py (`kairu meeting ...`). Like every Kairu part it holds no authority: each step that sends or changes anything is
a Guardian action in policy.yaml, and nothing that comes out of a meeting runs.
"""
