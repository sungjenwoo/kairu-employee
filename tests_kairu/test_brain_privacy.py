"""The privacy filter (Phase B): secrets never leave, personal data waits for you, and it fails closed."""

import pytest

from kairu.brain import privacy
from kairu.brain.privacy import PERSONAL, PUBLIC, SECRET, classify, luhn, secrets_in, verhoeff

CASES = [  # (question, class, a word its reasons must contain)
    # public: nothing personal, so with option A it may go to a no-training provider
    ("who is the prime minister of India", PUBLIC, ""),
    ("What is the capital of France?", PUBLIC, ""),
    ("Should I learn Python or Java?", PUBLIC, ""),
    ("Einstein said time is relative, is it true?", PUBLIC, ""),
    ("what is a strong password?", PUBLIC, ""),
    ("what is a good password to use", PUBLIC, ""),
    ("is the password case sensitive", PUBLIC, ""),
    ("What does 'salt' mean in password hashing?", PUBLIC, ""),
    ("what area is pin code 500081", PUBLIC, ""),
    ("gift ideas for my mom", PUBLIC, ""),
    ("how do I delete a folder in Windows?", PUBLIC, ""),
    ("What is 12345678 times 3?", PUBLIC, ""),
    ("When is Modi's birthday?", PUBLIC, ""),
    # secret: never sent, even with approval
    ("my password is Tiger@123", SECRET, "password"),
    ("my password is sunshine", SECRET, "password"),
    ("change my password to Bl@ck2026", SECRET, "password"),
    ("is 'Tiger@123' a strong password?", SECRET, "password"),
    ("my otp is 482916", SECRET, "code"),
    ("my pin is 4821", SECRET, "PIN"),
    ("my aadhaar is 2341 2341 2346", SECRET, "number"),
    ("my PAN is ABCPE1234F", SECRET, "PAN"),
    ("card 4111 1111 1111 1111 expiry 12/27", SECRET, "card"),
    ("my account number is 123456789012", SECRET, "account"),
    ("send 500 to ravi@okaxis", SECRET, "UPI"),
    ("use the key gsk_abcdefghijklmnopqrstuvwxyz123456", SECRET, "key"),
    ("what is https://example.com/reset?token=abcdef123456", SECRET, "key"),
    ("-----BEGIN RSA PRIVATE KEY-----", SECRET, "private key"),
    ("my passport number is K1234567", SECRET, "number"),
    # personal: waits for your approval
    ("call me on 9876543210", PERSONAL, "phone"),
    ("call me on +91 98765 43210 tonight", PERSONAL, "phone"),
    ("email me at sai@example.com", PERSONAL, "email"),
    ("tell Ravi I will be late", PERSONAL, "name"),
    ("should I tell Priya about the party?", PERSONAL, "name"),
    ("Ravi told me he is quitting, what should I do", PERSONAL, "name"),
    ("gift ideas for my friend Priya", PERSONAL, "name"),
    ("What is Ravi's phone number?", PERSONAL, "private details"),
    ("what are the side effects of my medicines", PERSONAL, "health"),
    ("I have diabetes, can I eat mangoes?", PERSONAL, "health"),
    ("my salary is low, how do I save", PERSONAL, "money"),
    ("I live at Flat 402, Madhapur, Hyderabad 500081", PERSONAL, "live"),
    ("reply to this message: hey are you coming tomorrow", PERSONAL, "message"),
    ("my bank's branch is SBIN0001234, what city is that", PERSONAL, "IFSC"),
    # unsure counts as personal: it fails closed
    ("प्रधानमंत्री कौन है", PERSONAL, "cannot read"),
    ("భారత ప్రధాని ఎవరు", PERSONAL, "cannot read"),
    ("how many people live in India? 1400000000?", PERSONAL, "long number"),
    ("what does commit 3f786850e387550fdab836ed7e6dc881de23001b do", PERSONAL, "code"),
    ("summarise this:\none\ntwo\nthree\nfour", PERSONAL, "lines"),
    ("x " * 400, PERSONAL, "long text"),
]


@pytest.mark.parametrize("text,level,why", CASES, ids=[case[0][:40] for case in CASES])
def test_each_question_gets_its_class(text, level, why):
    verdict = classify(text)
    assert verdict.level == level, verdict
    assert why.lower() in verdict.why().lower()


@pytest.mark.parametrize("text", [case[0] for case in CASES if case[1] != PUBLIC])
def test_a_reason_never_repeats_what_it_found(text):
    """A reason can be shown or kept without leaking the secret it describes."""
    for reason in classify(text).reasons:
        for word in text.split():
            if len(word) >= 5 and any(c.isdigit() for c in word):
                assert word not in reason


def test_the_backstop_finds_secrets_in_any_text_and_nothing_in_kairus_own_instructions():
    from kairu.brain.gateway import DATED_NOTE, SYSTEM, TEAM
    assert secrets_in("ok, my otp is 482916") and secrets_in("Bearer abcdefghijklmnopqrstuvwxyz0123")
    for own in (SYSTEM, DATED_NOTE, TEAM):
        assert secrets_in(own) == [] and classify(own).level != SECRET


def test_an_answer_written_by_an_ai_counts_only_what_is_certain():
    """The answer before a follow-up: a name in it is not "someone you know", a phone number still is."""
    assert classify("Narendra Modi said India will grow; I think so too.", answer=True).level == PUBLIC
    assert classify("You can reach them on 9876543210.", answer=True).level == PERSONAL
    assert classify("The code is 4111 1111 1111 1111.", answer=True).level == SECRET


def test_check_digits():
    assert verhoeff("234123412346") and not verhoeff("234123412345")
    assert luhn("4111111111111111") and not luhn("4111111111111112")


def test_a_verdict_is_only_labels():
    verdict = classify("my password is Tiger@123 and call me on 9876543210")
    assert verdict.level == SECRET and "Tiger@123" not in repr(verdict) and "9876543210" not in repr(verdict)
    assert privacy.Verdict(PUBLIC).why() == ""
