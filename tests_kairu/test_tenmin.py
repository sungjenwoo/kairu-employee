"""Tenmin (kairu/brain/tenmin.py): every spoken answer is short, answer first, then exactly one short follow-up question.

The replies below are written the way the free models answer (a greeting first, two questions, markdown lists, long
explanations, notes in brackets, no follow-up at all); none was taken from a live provider.
"""

import pytest

from kairu.brain import gateway, router, tenmin

REPLIES = [  # (question, what the AI wrote, what Kairu says aloud)
    ("who is the prime minister of India?",
     "Narendra Modi is the Prime Minister of India.\nWant to know more about him?",
     "Narendra Modi. Want to know more about him?"),
    ("Kairu, who's the president of the USA",
     "Great question! Donald Trump is the 47th President of the United States, serving since January 2025. "
     "Would you like to know about his policies? Or about the election?",
     "Donald Trump. Would you like to know about his policies?"),
    ("what is the capital of Japan",
     "The capital of Japan is **Tokyo**.",
     "The capital of Japan is Tokyo. Want to know more?"),
    ("what is photosynthesis",
     "Photosynthesis is the process plants use to turn sunlight, water and carbon dioxide into food (glucose) and oxygen. "
     "It happens mainly in the leaves, inside tiny parts called chloroplasts, which hold a green pigment called chlorophyll. "
     "This pigment captures light energy. Plants then use the glucose to grow.\n\nDo you want an example?",
     "Photosynthesis is the process plants use to turn sunlight, water and carbon dioxide into food and oxygen. "
     "Do you want an example?"),
    ("how do I stay focused while studying",
     "Here are some tips:\n- Study in short blocks of 25 minutes\n- Keep your phone in another room\n- Take short breaks\n"
     "Which one would you like to try first? And should I make you a plan?",
     "Study in short blocks of 25 minutes. Which one would you like to try first?"),
    ("what's the weather in Hyderabad",
     "It is sunny and 31 degrees in Hyderabad today. (This may be out of date: I answer from what I already know.)",
     "It is sunny and 31 degrees in Hyderabad today. Want to know more?"),
    ("explain it simply",
     "Sure! Photosynthesis is how a plant cooks its own food. It uses sunlight, water and air as its ingredients. "
     "For example, a mango tree uses sunlight on its leaves to make the sugar in its mangoes. Want to try another one?",
     "Photosynthesis is how a plant cooks its own food. It uses sunlight, water and air as its ingredients. "
     "For example, a mango tree uses sunlight on its leaves to make the sugar in its mangoes. Want to try another one?"),
    ("explain like a teacher how rain forms",
     "Rain forms when the sun warms water and it rises as vapour. High up, the vapour cools and joins into tiny drops that "
     "make clouds. When the drops grow heavy, they fall as rain. For example, steam from a kettle turns into drops on a cold "
     "plate. Isn't that neat? Shall I explain clouds next?",
     "Rain forms when the sun warms water and it rises as vapour. High up, the vapour cools and joins into tiny drops that "
     "make clouds. For example, steam from a kettle turns into drops on a cold plate. Isn't that neat?"),
    ("what did you mean",
     "Did you mean the weather today or tomorrow?",
     "Did you mean the weather today or tomorrow?"),
]


@pytest.mark.parametrize("question,reply,said", REPLIES)
def test_every_spoken_answer_is_tenmins_short_answer_then_one_follow_up(question, reply, said):
    line = tenmin.spoken(reply, question)
    assert line == said
    assert tenmin.is_spoken_well(line)


@pytest.mark.parametrize("question,reply,said", REPLIES)
def test_never_two_questions_never_a_speech(question, reply, said):
    line = tenmin.spoken(reply, question)
    assert line.count("?") == 1 and line.endswith("?")
    most = tenmin.EXPLAIN_WORDS if tenmin.explain_mode(question) else tenmin.SHORT_WORDS
    assert len(line.split()) <= most + tenmin.FOLLOW_UP_WORDS
    for unsaid in ("**", "- ", "(", "http", "Great question", "Sure!"):
        assert unsaid not in line


def test_a_simple_who_question_gets_only_the_name():
    for reply in ("Narendra Modi is the Prime Minister of India.", "Narendra Modi has been India's Prime Minister since 2014."):
        assert tenmin.spoken(reply, "who is the prime minister of india").startswith("Narendra Modi.")


def test_an_answer_with_no_follow_up_gets_exactly_one_short_one():
    assert tenmin.spoken("Tokyo.", "capital of japan") == "Tokyo. Want to know more?"
    long_offer = "Tokyo. " + "Would you like me to tell you all about its history, food, trains, temples and festivals today?"
    assert tenmin.spoken(long_offer, "capital of japan") == "Tokyo. Want to know more?"  # a follow-up stays short


def test_explain_mode_is_heard_and_asks_the_ai_for_simple_words_and_one_example():
    for asked in ("explain it simply", "explain like a teacher", "Kairu, explain that like I'm five", "explain in simple words"):
        assert tenmin.explain_mode(asked), asked
        assert "one small example" in gateway.Gateway.messages(asked)[0]["content"]
    assert not tenmin.explain_mode("explain the plan") and "one small example" not in gateway.Gateway.messages("who is the PM")[0]["content"]
    assert router.route("explain like a teacher", ("who is the PM?", "Narendra Modi.")).follow_up  # it explains the last answer


def test_the_ai_is_told_tenmins_rules_with_every_question():
    system = gateway.Gateway.messages("who is the prime minister of India?")[0]["content"]
    for rule in ("kind, encouraging teacher", "give just the name", "exactly one short follow-up", "Never two questions",
                 "never take the lead"):
        assert rule in system, rule
    assert tenmin.RULES in gateway.SYSTEM
