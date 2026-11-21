"""What the small speech model heard, made into an order: fillers out, numbers as digits, its usual mishearings put right.

Rules only, and the same words always give the same order. Nothing here guesses: an order that is only a verb ("open")
gets one short question back, and so does one the model was not sure of. A spoken "yes", "no" or string of digits is never
an order, so a PIN said aloud goes nowhere (approvals are typed in the bar's card, never spoken).

"Kairu" is not a word the model knows. The wake recognizer (kairu/voice/hearing.py) listens for the words it hears instead:
"cairo", "carew", "kai", "kai ru". The word recognizer hears it as many things ("kaoru", "career", "hi"), so its words for
"Kairu" are cut by time, not by spelling; KAIRU_LIKE only tidies the live words shown while you speak.
"""

import re

WAKE_GRAMMAR = ["cairo", "kai ru", "kai rue", "carew", "stop", "[unk]"]  # what the wake recognizer may hear
WAKE_START = ("cairo", "carew", "kai")  # a wake word starts with one of these
WAKE_PARTS = frozenset({"cairo", "carew", "kai", "ru", "rue"})
KAIRU_LIKE = frozenset({"cairo", "kaoru", "carew", "kai", "career", "courier", "collier", "carroll", "carol", "kyra", "cara"})
KAIRU_TAIL = frozenset({"you", "to", "do", "who", "room", "rule", "euro", "are", "he", "a", "hero", "through", "ooh", "true", "ru",
                        "roo", "rue", "your", "oh", "is", "as"})  # how the word recognizer may hear the end of "Kairu"

FILLERS = frozenset({"um", "uh", "er", "erm", "ah", "hmm", "mm", "uhm", "huh"})
LEADING = frozenset({"okay", "ok", "so", "well", "alright", "right", "now", "and", "then", "also", "oh",
                     "i'm", "hm", "mhm"})  # at the start only; a quick "um" is often heard as "i'm"
YES_NO = frozenset({"yes", "yeah", "yep", "yup", "no", "nope", "okay", "ok", "sure", "confirm", "approve", "approved"})

UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
NUMBER_WORDS = frozenset({*UNITS, *TENS, "hundred", "a"})
DIGITS = frozenset({*UNITS, "oh", "for", "to", "too", "won", "ate"})  # how a PIN said aloud comes out

FIXES = (  # the small model's usual mishearings in Kairu's own orders, then Whisper's in the owner's own voice (10 Nov 2026)
    (re.compile(r"\b(set|said|sat) (the )?value\b"), r"\1 \2volume"),  # Whisper: "set the value to 30"
    (re.compile(r"\bvalue(?= (?:to |at )?(?:\d|(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|"
                r"fifty|sixty|seventy|eighty|ninety|a hundred)\b))"), "volume"),  # "value to 30"
    (re.compile(r"^(?:wants|want's|whats|watts|once) open$"), "what's open"),  # Whisper: "wants open"
    (re.compile(r"^starts\b"), "search"),  # Whisper: "starts the weather"
    (re.compile(r"^set a (volume|brightness)\b"), r"set the \1"),  # Whisper: "set a volume to 80"
    (re.compile(r"\bsaid (the )?(volume|sound|brightness)\b"), r"set \1\2"),
    (re.compile(r"\bsat (the )?(volume|sound|brightness)\b"), r"set \1\2"),
    (re.compile(r"\bnote pad\b"), "notepad"),
    (re.compile(r"\bwi fi\b"), "wifi"),
    (re.compile(r"\bvolumes\b"), "volume"),
)
_NUMBER = "(?:" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + ")"
LEVEL_PLACE = re.compile(rf"\b(volume|sound|brightness)( (?:to|two|too|at))? ({_NUMBER}(?: {_NUMBER})*)\b( percent)?")

BARE = {  # an order that is only its verb: one short question, never a guess
    "open": "Open what?", "start": "Open what?", "launch": "Open what?", "close": "Close what?", "quit": "Close what?",
    "rename": "Rename which file, and to what?", "set": "Set what?", "turn": "Turn what?", "turn on": "Turn what on?",
    "turn off": "Turn what off?", "switch on": "Switch what on?", "switch off": "Switch what off?", "put": "Put what where?",
    "volume": "Volume to what?", "set volume": "Volume to what?", "set the volume": "Volume to what?",
    "set volume to": "Volume to what?", "brightness": "Brightness to what?", "set brightness": "Brightness to what?",
    "set brightness to": "Brightness to what?", "search": "Search for what?", "search for": "Search for what?",
    "maximize": "Maximize what?", "minimize": "Minimize what?",
}
NOT_CAUGHT = "Sorry, I didn't catch that. Could you say it again?"
SURE = 0.5  # below this average confidence, the model was not sure what it heard
LEVEL_DIGITS = re.compile(r"\b(volume|sound|brightness)\b(?: (?:to|at|two|too))? (\d+(?: \d+)*)\b")
PLACES = {"volume": "volume", "sound": "volume", "brightness": "brightness"}
SEARCHED_SETTING = re.compile(r"\bsearch\b.*?\b(volume|sound|brightness|wifi)\b(.*)$")  # "search" with a setting after it
SPOKEN_SETTINGS = {"volume": "volume", "sound": "volume", "brightness": "brightness", "wifi": "Wi-Fi"}


def number(words: list[str]) -> int | None:
    """Spoken words for a whole number from 0 to 100 ("thirty", "twenty five", "a hundred"), or None."""
    words = [word for word in words if word]
    if words in (["hundred"], ["a", "hundred"], ["one", "hundred"]):
        return 100
    if len(words) == 1:
        return UNITS.get(words[0], TENS.get(words[0]))
    if len(words) == 2 and words[0] in TENS and words[1] in UNITS and 0 < UNITS[words[1]] < 10:
        return TENS[words[0]] + UNITS[words[1]]
    return None


def _level(found: re.Match) -> str:
    place, before, spoken, percent = found.group(1), found.group(2) or "", found.group(3).split(), found.group(4) or ""
    value = number(spoken)
    if value is None and before.strip() in ("", "two") and spoken and spoken[0] == "two":
        value, before = number(spoken[1:]), " to"  # "volume two thirty": "two" was "to"
    if value is None and before.strip() == "two":
        value, before = number(spoken), " to"
    if value is None:
        return found.group(0)
    if before.strip() in ("two", "too"):
        before = " to"
    return f"{place}{before} {value}{percent}"


def clean(words: list[str]) -> str:
    """The order in these words: fillers out, levels as digits, usual mishearings put right. Lower case, as heard."""
    kept = [word for word in words if word and word not in FILLERS and word != "[unk]"]
    while kept and kept[0] in LEADING:
        kept.pop(0)
    text = " ".join(kept)
    for pattern, replacement in FIXES:
        text = pattern.sub(replacement, text)
    return LEVEL_PLACE.sub(_level, text).strip()


def is_thanks(text: str) -> bool:
    words = [word for word in text.split() if word not in KAIRU_LIKE]
    return " ".join(words) in ("thank you", "thanks", "thank you so much", "thank you very much", "thanks a lot", "thank you that's all",
                               "that's all thank you", "thanks that's all", "that's all thanks")


def is_stop(text: str) -> bool:
    """Within a session: "stop" on its own, said to Kairu, is the emergency stop."""
    return text in ("stop", "stop stop", "stop everything", "stop it", "stop now")


def is_yes_or_digits(text: str) -> bool:
    """A spoken yes, no or PIN: never an order, and never an approval."""
    words = text.split()
    return bool(words) and (all(word in YES_NO for word in words) or all(word in DIGITS or word.isdigit() for word in words))


def level_question(text: str) -> tuple[str, str] | None:
    """A level out of range ("volume 230"): (the one short question, the order to say instead), never a guess at the number.

    A level is 0 to 100. Whisper sometimes writes "to 30" as "230" (or "2 30"), and "for 30" as "430": then Kairu asks "Did
    you mean 30?" and does nothing; you answer by saying it again ("volume 30"). Any other number out of range gets the range."""
    for found in LEVEL_DIGITS.finditer(text):
        place, groups = PLACES[found.group(1)], found.group(2).split()
        digits = "".join(groups)
        if len(groups) == 1 and int(digits) <= 100:
            continue
        rest = groups[-1] if len(groups) > 1 else digits[1:]
        if (len(groups) > 1 or digits[0] in "24") and rest and int(rest) <= 100:
            return f"Did you mean {int(rest)}?", f"{place} {int(rest)}"
        return f"{place.capitalize()} goes from 0 to 100. What level?", f"{place} 50"
    return None


def setting_question(text: str) -> tuple[str, str] | None:
    """A heard "search" with a setting word after it (volume, brightness, Wi-Fi): (the one short question, the order to say
    instead). Never a search: Whisper heard the owner's "set the volume" as "search the volume" (10 Nov 2026), and a search
    would send their words to the web. Kairu asks "Did you mean set the volume to 30?" and does nothing; you answer by saying
    the order again. A level out of range is never guessed here either ("search the volume to 230": "... to 30?")."""
    found = SEARCHED_SETTING.search(text)
    if not found:
        return None
    setting, rest = found.group(1), found.group(2)
    place, spoken = PLACES.get(setting, setting), SPOKEN_SETTINGS[setting]
    if setting == "wifi":
        state = re.search(r"\b(on|off)\b", rest)
        if state:
            return f"Did you mean turn {spoken} {state.group(1)}?", f"turn wifi {state.group(1)}"
        return f"Did you mean turn {spoken} on or off?", "turn wifi on"
    level = re.search(r"\b(\d+(?: \d+)*)\b", rest)
    if level:
        value = level_question(f"{place} {level.group(1)}")
        if value and not value[0].startswith("Did you mean"):
            return value[0], value[1]  # no number to offer: the range
        number = value[1].split()[-1] if value else str(int(level.group(1)))
        return f"Did you mean set the {spoken} to {number}?", f"set the {place} to {number}"
    way = re.search(r"\b(up|down)\b", rest)
    if way:
        return f"Did you mean turn the {spoken} {way.group(1)}?", f"turn the {place} {way.group(1)}"
    return f"Did you mean set the {spoken}?", f"set the {place} to 50"


def asked_instead(text: str) -> tuple[str, str] | None:
    """(the "Did you mean ...?" question, the order to say instead), for a heard order Kairu must not guess at, or None."""
    return setting_question(text) or level_question(text)


def unclear(text: str, sure: float) -> str:
    """The one short question for an order that is unclear, or "" if it is clear enough to hand on."""
    if sure < SURE:
        return NOT_CAUGHT
    asked = asked_instead(text)
    if asked:
        return asked[0]
    return BARE.get(text, "")


def say_it_again(example: str) -> str:
    """After "Did you mean 30?", a spoken "yes" is still never an order: you say the order again, with the number."""
    if not any(character.isdigit() for character in example):
        return f'Please say the whole order again, like "{example}".'
    return f'Please say it again with the number, like "{example}".'


def shown(words: list[str], strip_kairu: bool) -> str:
    """The live words for the bar, while you are still speaking: as the order will be, so far."""
    kept = list(words)
    if strip_kairu:
        for _ in range(3):
            if kept and kept[0] in KAIRU_LIKE:
                kept.pop(0)
    return clean(kept)
