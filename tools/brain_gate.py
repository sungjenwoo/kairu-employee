"""The Phase B gate test, step 1: where each of the 20 test questions goes. Nothing is sent anywhere.

On Windows, in the project folder:
    py -3.12 tools\\brain_gate.py      (or, with the private environment: .venv-guardian\\Scripts\\python tools\\brain_gate.py)

Each line shows the question, the level the Model Gateway picks (L0 rules here, L3 free cloud AI, L4 team mode)
and, for L3, what the privacy filter found. It ends with PASSED when all 20 go where BRAIN.md says.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kairu.brain import router  # noqa: E402
from tests_kairu.brain_gate import GATE  # noqa: E402


def main() -> int:
    wrong = 0
    print("Kairu Phase B gate test: where 20 questions go (nothing is sent)")
    for number, (question, level, kind, what) in enumerate(GATE, 1):
        route = router.route(question)
        got = route.privacy.level if route.kind == "cloud" else route.name
        ok = (route.level, route.kind, got) == (level, kind, what)
        wrong += not ok
        found = f" ({route.privacy.why()})" if route.kind == "cloud" and route.privacy.reasons else ""
        print(f"  {number:>2}. {'ok ' if ok else 'NO '} {route.level} {route.kind:<6} {got or '-':<18} {question}{found}")
        if not ok:
            print(f"        expected {level} {kind} {what}")
    print(f"\n  Result: {'PASSED' if not wrong else 'FAILED'}  {len(GATE) - wrong} of {len(GATE)} go to the right level")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
