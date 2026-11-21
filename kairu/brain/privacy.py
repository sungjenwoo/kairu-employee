"""The privacy filter: what may leave this PC for a cloud AI (ADR-005, BRAIN.md "The privacy filter").

classify(text) reads a question before anything is sent and puts it in one of three classes:

    secret    passwords, PINs and one-time codes, keys and tokens, ID numbers (Aadhaar, PAN, passport, ...),
              bank details (card and account numbers, UPI IDs): NEVER sent, even with your approval
    personal  something about you or people you know: phone numbers, email addresses, where you live, a
              person's name in what you do with them, your health or money, a message you pasted: sent
              only after you approve that exact text, on a screen that shows where it goes
    public    none of the above: with option A (brain.public_to_cloud) it goes straight to a free provider
              that does not train on prompts

It fails closed: what it cannot read well enough to be sure of (words in a script it cannot read
yet, a long pasted text, many lines, a long number or code) counts as personal, so it waits for you.

It never repeats what it found: each reason is a short label ("a phone number"), never the text
itself, so a reason can be shown or kept without leaking the secret it describes.

secrets_in(text) is the backstop scanner (ADR-005): the provider connector runs it on the exact text
that is about to leave, and refuses to send anything in which it finds a secret, whatever said it was fine.

Rules only, no AI: the same text always gets the same answer. It reads English best; numbers, codes,
email addresses and links are found in any language.
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

SECRET, PERSONAL, PUBLIC = "secret", "personal", "public"

LONGEST = 600  # characters; a longer question may be pasted, so it counts as personal
MOST_LINES = 3
FOREIGN_SHARE = 0.15  # of the letters: more than this in a script the filter cannot read, and it is unsure
I = re.IGNORECASE


@dataclass(frozen=True)
class Verdict:
    level: str  # SECRET, PERSONAL or PUBLIC
    reasons: tuple[str, ...] = ()  # short labels, never the text that was found

    @property
    def secret(self) -> bool:
        return self.level == SECRET

    @property
    def personal(self) -> bool:
        return self.level == PERSONAL

    def why(self) -> str:
        return ", ".join(self.reasons)


# --- check digits and randomness ----------------------------------------------------------------------

_VERHOEFF_D = ((0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5), (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
               (3, 4, 0, 1, 2, 8, 9, 5, 6, 7), (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
               (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3), (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
               (9, 8, 7, 6, 5, 4, 3, 2, 1, 0))
_VERHOEFF_P = ((0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4), (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
               (8, 9, 1, 6, 0, 4, 3, 5, 2, 7), (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
               (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8))


def verhoeff(number: str) -> bool:
    """The Aadhaar check digit is right."""
    check = 0
    for place, digit in enumerate(reversed(number)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[place % 8][int(digit)]]
    return check == 0


def luhn(number: str) -> bool:
    """The card-number check digit is right."""
    total = 0
    for place, digit in enumerate(reversed(number)):
        value = int(digit) * (2 if place % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def _entropy(text: str) -> float:
    counts = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _looks_like_a_password(value: str) -> bool:
    """Mixed case, a digit or a symbol: not just an ordinary word."""
    return bool(re.search(r"\d", value) or re.search(r"[^A-Za-z]", value) or (value != value.lower() and
                                                                              value != value.capitalize()))


# --- secrets: never sent ------------------------------------------------------------------------------

PASSWORD_WORD = (r"(?:password|passwd|pass\s?word|pwd|passcode|pass\s?code|passphrase|mpin|m-pin|upi\s?pin|atm\s?pin|"
                 r"login\s?pin|otp|one[- ]time\s?(?:password|code|pin)|cvv|cvc|security\s?code|verification\s?code|"
                 r"login\s?code|pin(?!\s?code))")
NOT_A_VALUE = {  # words that follow "password is" in questions about passwords, not in a password itself
    "strong", "weak", "safe", "secure", "correct", "wrong", "incorrect", "required", "needed", "changed", "reset",
    "expired", "valid", "invalid", "the", "a", "an", "my", "your", "his", "her", "their", "our", "not", "what", "how",
    "too", "very", "same", "different", "long", "short", "good", "bad", "ok", "okay", "fine", "case", "sensitive",
    "important", "necessary", "hidden", "encrypted", "stored", "saved", "visible", "shown", "asked", "sent", "used",
    "for", "to", "of", "in", "on", "at", "by", "with", "and", "or", "it", "this", "that", "there", "here", "only",
    "just", "also", "still", "always", "never", "usually", "often", "set", "new", "old", "forgotten", "forgot", "lost",
    "locked", "blocked", "mandatory", "enough", "secret", "private", "unknown", "empty", "missing", "so", "being",
    "be", "been", "right", "which", "when", "where", "why", "who", "best", "better", "worse", "worst", "easy", "hard",
    "easier", "harder", "common", "popular", "recommended", "allowed", "accepted", "ideal", "complex", "simple",
    "unique", "random", "typical", "default", "standard", "generally", "mostly", "really", "actually", "probably",
    "likely", "considered", "stronger", "weaker", "safer", "longer", "shorter", "possible", "impossible", "no", "yes",
    "now", "then", "less", "more", "most", "least", "required.", "enough.", "needed.", "case-sensitive", "guessable",
    "easily", "hackable", "hacked", "leaked", "compromised", "known", "same.", "saved.", "different.", "one", "two",
}
POSTAL = re.compile(r"\b(?:area|post|postal|post\s?office|city|town|district|state|place|location|locality|address|"
                    r"where|which|village|mandal|pincode|pin\s?code|zip)\b", I)
SECRET_PATTERNS = [  # (label, pattern); a match is a secret
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("an API key or token", re.compile(
        r"(?<![A-Za-z0-9])(?:sk-(?:proj-|ant-|or-v1-)?[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9]{16,}|csk-[A-Za-z0-9]{16,}|"
        r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?:AKIA|ASIA)[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|"
        r"xox[abprs]-[A-Za-z0-9-]{10,}|(?:sk|rk|pk)_live_[A-Za-z0-9]{10,}|glpat-[A-Za-z0-9_-]{16,}|"
        r"hf_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})")),
    ("a bot token", re.compile(r"(?<!\d)\d{8,10}:[A-Za-z0-9_-]{30,}")),
    ("an API key or token", re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{16,}", I)),
    ("an API key or token", re.compile(
        r"\b(?:api[\s_-]?key|access[\s_-]?key|secret[\s_-]?key|client[\s_-]?secret|auth[\s_-]?token|access[\s_-]?token|"
        r"refresh[\s_-]?token|token|secret)\s*(?:is|=|:)\s*[\"'`]?(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{8,}", I)),
    ("a link with a key in it", re.compile(
        r"https?://\S*[?&](?:api[_-]?key|key|token|access_token|auth|sig|signature|password|pwd|secret|session|"
        r"sessionid|code)=[^&\s]{6,}", I)),
    ("a PAN number", re.compile(r"\b[A-Z]{3}[ABCFGHLJPTK][A-Z]\d{4}[A-Z]\b")),
    ("an ID number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),  # a US social security number
    ("an ID number", re.compile(r"\b[A-Z]{2}[ -]?\d{2}[ -]?(?:19|20)\d{2}[ -]?\d{7}\b")),  # an Indian driving licence
    ("an ID or account number", re.compile(
        r"\b(?:my|his|her|our|their|your)\s+(?:aadhaa?r|pan|passport|voter\s?id|driving\s?licen[cs]e|licen[cs]e|"
        r"ssn|social\s?security|bank\s?account|account|credit\s?card|debit\s?card|card|policy|uan|pf|ration\s?card|"
        r"employee\s?id|student\s?id|roll|registration|customer\s?id|consumer)\s*(?:number|no\.?|num|#|id)?\s*"
        r"(?:is|was|=|:|-)\s*(?=[A-Za-z0-9/-]*\d)[A-Za-z0-9/-]{4,}", I)),
    ("a bank account number", re.compile(
        r"\b(?:account|a/c|acct|ac)\s*(?:number|no\.?|num|#)?\s*[:=-]?\s*\d[\d -]{7,20}\d\b", I)),
    ("a UPI ID", re.compile(
        r"\b[a-zA-Z0-9._-]{2,64}@(?:upi|ybl|ibl|axl|apl|okaxis|okhdfcbank|okicici|oksbi|paytm|ptyes|ptaxis|pthdfc|ptsbi|"
        r"yapl|ikwik|kotak|icici|hdfcbank|sbi|axisbank|freecharge|jupiteraxis|fbl|airtel|jio|waicici|wahdfcbank|wasbi|"
        r"waaxis|abfspay|nyes|rapl|pingpay|kbl|federal|indus|idfcbank|yesbank|barodampay|aubank|unionbank|cnrb|"
        r"pnb|boi|mahb|ubi|centralbank|idbi|okbizaxis)\b(?!\.)", I)),
    ("a bank account number", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")),  # an IBAN
]
CONTEXT_IDS = [  # (label, pattern, a word that must be in the text as well)
    ("a passport number", re.compile(r"\b[A-Z][1-9]\d\s?\d{4}[1-9]\b"), re.compile(r"passport", I)),
    ("a voter ID number", re.compile(r"\b[A-Z]{3}\d{7}\b"), re.compile(r"\b(?:voter|epic|election)\b", I)),
    ("a PAN number", re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b"), re.compile(r"\bpan\b", I)),
]
SAID = re.compile(rf"(?P<who>\b\w+\s+)?\b{PASSWORD_WORD}\b\s*(?:for\s+\S+\s+)?(?P<how>is|was|=|:|-|will\s+be|should\s+be|"
                  r"to)\s*[\"'“‘`]?(?P<value>[^\s\"'”’`]{3,})", I)
CODE = re.compile(rf"\b(?P<word>{PASSWORD_WORD})\b[^0-9\n]{{0,15}}(?<![\d.])(?P<number>\d{{3,8}})(?![\d.:])", I)


def _password_values(text: str) -> bool:
    """A password, PIN or code with its value in the text ("my password is Tiger@123"), not a question about one."""
    for match in SAID.finditer(text):
        value = match.group("value").strip(".,!?;:")
        if value.lower() in NOT_A_VALUE or len(value) < 3:
            continue
        possessive = (match.group("who") or "").strip().lower() in ("my", "our", "his", "her", "their", "the", "your")
        if _looks_like_a_password(value) or (possessive and match.group("how").lower() not in ("to",)):
            return True
    quoted = [word for word in re.findall(r"[\"'“‘`]([^\"'”’`\s]{4,40})[\"'”’`]", text) if _looks_like_a_password(word)]
    return bool(quoted and re.search(rf"\b{PASSWORD_WORD}\b", text, I))


def _codes(text: str) -> bool:
    """A PIN or one-time code with its digits. A postal PIN code (6 digits, about a place) is not one."""
    for match in CODE.finditer(text):
        bare_pin = match.group("word").lower() == "pin"
        if bare_pin and len(match.group("number")) == 6 and match.group("number")[0] != "0" and POSTAL.search(text):
            continue
        return True
    return False


def _secret_numbers(text: str) -> list[str]:
    found, cards = [], []
    for match in re.finditer(r"(?<!\d)(?<!\d\.)(?:\d[ -]?){12,18}\d(?!\d|\.\d)", text):  # 13 to 19 digits: a card
        digits = _digits(match.group())
        if 13 <= len(digits) <= 19 and luhn(digits):
            found.append("a card number")
            cards.append(match.span())
    for match in re.finditer(r"(?<!\d)(?<!\d\.)(?:\d[ -]?){11}\d(?!\d|\.\d)", text):  # 12 digits: Aadhaar
        if any(start <= match.start() < end for start, end in cards):
            continue
        digits = _digits(match.group())
        if digits[0] in "23456789" and (verhoeff(digits) or re.search(r"\b(?:aadhaa?r|uidai|uid)\b", text, I)):
            found.append("an Aadhaar number")
    return found


def _random_codes(text: str) -> list[tuple[str, str]]:
    """Long random-looking strings: probably a key or token. A long hexadecimal code is only unsure."""
    found = []
    for word in re.findall(r"[A-Za-z0-9_+/=.-]{24,}", text):
        if re.match(r"(?:https?|www\.)", word, I) or re.search(r"\.(?:com|org|net|in|io|ai|dev|gov|edu)\b", word, I):
            continue
        letters, digits = sum(c.isalpha() for c in word), sum(c.isdigit() for c in word)
        if re.fullmatch(r"[0-9a-fA-F]{32,}", word):
            found.append(("unsure", "a long code (maybe a key)"))
        elif letters and digits and _entropy(word) >= 3.5 and (word != word.lower() or digits >= 4):
            found.append(("secret", "a long random-looking code (maybe a key or token)"))
    return found


def secrets_in(text: str) -> list[str]:
    """The backstop: labels of the secrets in this text ([] if none). Never the secrets themselves."""
    found = [label for label, pattern in SECRET_PATTERNS if pattern.search(text)]
    found += [label for label, pattern, needs in CONTEXT_IDS if pattern.search(text) and needs.search(text)]
    if _password_values(text):
        found.append("a password, PIN or code")
    elif _codes(text):
        found.append("a PIN or one-time code")
    found += _secret_numbers(text)
    found += [label for kind, label in _random_codes(text) if kind == "secret"]
    return list(dict.fromkeys(found))


# --- personal: sent only with your approval -----------------------------------------------------------

RELATIONS = (r"(?:mom|mum|mother|amma|ammi|maa|dad|father|nanna|appa|papa|abba|wife|husband|girlfriend|boyfriend|gf|bf|"
             r"friend|best\s?friend|bestie|brother|sister|bro|sis|anna|akka|thammudu|chelli|son|daughter|uncle|aunt|"
             r"aunty|auntie|cousin|grandma|grandpa|grandmother|grandfather|nani|tata|boss|manager|colleague|coworker|"
             r"co-worker|teacher|professor|mentor|classmate|roommate|flatmate|neighbou?r|doctor|lawyer|landlord|"
             r"partner|fianc[ée]e?|crush|ex|team\s?lead|hr|client|student|tutor|maid|driver)")
NAME = r"[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})?"  # always matched case-sensitively: a name starts with a capital
NOT_NAMES = {
    "Kairu", "Google", "Alexa", "Siri", "Windows", "Linux", "Python", "Java", "Android", "Apple", "Microsoft", "Amazon",
    "Netflix", "India", "Hyderabad", "Telangana", "God", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday", "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December", "English", "Hindi", "Telugu", "Claude", "Gemini", "Groq", "The", "This", "That",
    "What", "When", "Where", "Which", "Who", "Why", "How", "Please", "Thanks", "Hello", "Sir", "Madam", "Mister", "Him",
    "Her", "Them", "Everyone", "Someone", "Anyone", "Nobody", "Customer", "Support", "Police", "Chatgpt", "Copilot",
}
FIRST_PERSON = re.compile(r"\b(?:i|me|my|mine|we|us|our|i'm|i've|i'd|i'll)\b", I)
HEALTH = (r"(?:diagnosis|disease|illness|cancer|diabetes|bp|blood\s?pressure|sugar\s?levels?|hiv|depression|anxiety|"
          r"adhd|autism|pregnancy|periods?|medicines?|medications?|prescription|test\s?results?|lab\s?results?|"
          r"blood\s?(?:test|report)s?|medical\s?reports?|symptoms|surgery|operation|therapy|therapist|psychiatrist|"
          r"mental\s?health|allerg(?:y|ies)|treatment|scan\s?results?|x-?rays?)")
MONEY = (r"(?:salary|income|pay\s?slip|payslip|loans?|debts?|emi|emis|credit\s?score|cibil|bank\s?balance|savings|"
         r"investments?|portfolio|tax\s?return|itr|net\s?worth|rent\s?agreement)")
LIFE = (r"(?:religion|caste|sexuality|sexual\s?orientation|breakup|break-up|divorce|affair|fir|court\s?case|"
        r"case\s?number|criminal\s?record)")
ADDRESS_WORDS = (r"(?:road|rd|street|nagar|colony|sector|flat|house|h\.?\s?no|plot|floor|apartments?|apts?|layout|"
                 r"village|mandal|district|lane|cross|opp|opposite|near|beside|behind|block|phase|tower|society|"
                 r"enclave|residency|hills|gardens|towers|marg|chowk|gali|basti)")
TOLD = (r"(?:said|says|told|tells|asked|asks|wants|wanted|thinks|thought|feels|felt|is\s+angry|is\s+upset|is\s+sad|"
        r"is\s+sick|is\s+coming|came|called|texted|messaged|replied|blocked|broke\s+up|likes|loves|hates|ignored|ignores)")

PERSONAL_PATTERNS = [  # (label, pattern); a pattern with a group: the group is a name, checked against NOT_NAMES
    ("an email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("a phone number", re.compile(r"(?<![\d+])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("a phone number", re.compile(r"(?<![\w+])\+\d{1,3}[\s-]?\d[\d\s-]{6,14}\d(?!\d)")),
    ("a phone number", re.compile(r"(?<!\d)0\d{2,4}[\s-]\d{6,8}(?!\d)")),
    ("where you live", re.compile(r"\b(?:i\s+(?:live|stay|reside)\s+(?:at|in|near|on|opposite)|my\s+(?:home|house|flat|"
                                  r"room|hostel|pg)\s+(?:address|is\s+(?:at|in|near|on))|where\s+i\s+(?:live|stay)|"
                                  r"my\s+(?:current\s+|home\s+|exact\s+)?(?:address|location))\b", I)),
    ("an address", re.compile(r"\b(?:flat|house|h\.?\s?no|plot|door)\s*(?:no\.?|number|#)?\s*[\w/-]*\d", I)),
    ("a bank branch code (IFSC)", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
    ("someone you know, by name", re.compile(
        rf"(?i:\b(?:tell|ask|call|message|text|email|mail|meet|invite|remind|wish|thank|ping|whatsapp|visit|marry|"
        rf"propose\s+to|apologi[sz]e\s+to|reply\s+to|talk\s+to|speak\s+to|dating))\s+({NAME})\b")),
    ("someone you know, by name", re.compile(rf"(?i:\bmy\s+{RELATIONS})\s+({NAME})\b")),
    ("someone you know, by name", re.compile(rf"\b({NAME}),?\s+(?i:(?:is\s+)?my\s+{RELATIONS})\b")),
    ("someone's private details", re.compile(
        rf"\b({NAME})'s\s+(?i:number|phone|mobile|address|email|salary|health|surgery|operation|account|password|"
        rf"location|house|home|marks|reports?)\b")),
    ("your health", re.compile(rf"\bmy\s+(?:\w+\s+)?{HEALTH}\b", I)),
    ("your health", re.compile(r"\bi\s+(?:have|had|got|am|'m|was|have\s+been)\s+(?:diagnosed\s+with\s+)?(?:diabetes|"
                               r"cancer|hiv|depression|anxiety|adhd|autism|pregnant|covid|tb|tuberculosis|asthma|bp|"
                               r"thyroid|pcos|pcod|a\s+fever|fever|migraine|ocd|bipolar)\b", I)),
    ("your money", re.compile(rf"\bmy\s+(?:\w+\s+)?{MONEY}\b", I)),
    ("something private about you", re.compile(rf"\bmy\s+(?:\w+\s+)?{LIFE}\b", I)),
    ("a message", re.compile(r"\b(?:this|that|the|his|her|their|my|your)\s+(?:message|email|e-mail|mail|text|chat|dm|sms|"
                             r"whatsapp|letter|note)\s+(?:says|said|reads|from|to|i\s+got|i\s+received|he\s+sent|"
                             r"she\s+sent)\b|\b(?:he|she|they)\s+(?:wrote|texted|messaged|replied|sent\s+me)\b|"
                             r"\breply\s+to\s+(?:this|his|her|their|my)\b|\bforwarded\s+message\b", I)),
    ("a message", re.compile(r"^\s*(?:from|to|subject|sent|date|cc)\s*:", I | re.MULTILINE)),
    ("quoted text (maybe a message)", re.compile(r"[\"“][^\"”]{60,}[\"”]")),
]
PAST_WITH = re.compile(rf"(?i:\b(?:met|saw|told|asked|called|texted|messaged|with))\s+({NAME})\b")
SAID_BY = re.compile(rf"\b({NAME})\s+{TOLD}\b")


def _is_name(name: str) -> bool:
    return name.split()[0] not in NOT_NAMES


def _personal(text: str) -> list[str]:
    found = []
    for label, pattern in PERSONAL_PATTERNS:
        for match in pattern.finditer(text):
            if pattern.groups and not _is_name(match.group(1)):
                continue
            found.append(label)
            break
    # "I met Ravi", "Ravi told me ...": a name in what you did with someone counts when you are in it too
    if FIRST_PERSON.search(text) and any(_is_name(match.group(1)) for pattern in (PAST_WITH, SAID_BY)
                                         for match in pattern.finditer(text)):
        found.append("someone you know, by name")
    if re.search(r"\b[1-9]\d{2}\s?\d{3}\b", text) and re.search(rf"\b{ADDRESS_WORDS}\b", text, I):
        found.append("an address")
    return found


def _unsure(text: str) -> list[str]:
    """What the filter cannot read well enough to be sure about: it counts as personal (fails closed)."""
    found = []
    letters = [c for c in text if c.isalpha()]
    foreign = [c for c in letters if not unicodedata.name(c, "").startswith("LATIN")]
    if letters and len(foreign) / len(letters) > FOREIGN_SHARE:
        found.append("words the filter cannot read yet (it reads English)")
    if len(text) > LONGEST:
        found.append("a long text (it may be pasted)")
    if len([line for line in text.splitlines() if line.strip()]) > MOST_LINES:
        found.append("several lines (they may be pasted)")
    rest = re.sub(r"(?<![\d.])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)", " ", text)  # phone numbers: found above
    if re.search(r"(?<!\d)(?<![\d][.,])\d(?:[ -]?\d){8,}(?!\d|[.,]\d)", rest):
        found.append("a long number (maybe an account or ID)")
    found += [label for kind, label in _random_codes(text) if kind == "unsure"]
    if re.search(r"https?://\S*\?\S{8,}|https?://\S*/[A-Za-z0-9_-]{20,}", text, I):
        found.append("a web link with codes in it")
    return found


HARD_FINDS = ("an email address", "a phone number", "an address", "a bank branch code (IFSC)")


def classify(text: str, answer: bool = False) -> Verdict:
    """Secret, personal or public, with short reasons.

    answer=True is for text an AI wrote (the answer before a follow-up question): only what is certain
    counts there (secrets, email addresses, phone numbers, addresses), not names or what is unsure.
    """
    secrets = secrets_in(text)
    if secrets:
        return Verdict(SECRET, tuple(secrets))
    personal = [label for label in _personal(text) if not answer or label in HARD_FINDS]
    if not answer:
        personal += _unsure(text)
    if personal:
        return Verdict(PERSONAL, tuple(dict.fromkeys(personal)))
    return Verdict(PUBLIC)
