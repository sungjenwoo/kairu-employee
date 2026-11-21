"""The Model Gateway's router (Phase B): every question goes to the right brain level."""

import pytest

from kairu.brain import router
from tests_kairu.brain_gate import GATE


@pytest.mark.parametrize("question,level,kind,what", GATE, ids=[case[0][:40] for case in GATE])
def test_the_gate_tests_20_questions_go_to_the_right_level(question, level, kind, what):
    route = router.route(question)
    assert (route.level, route.kind) == (level, kind)
    assert (route.privacy.level if kind == "cloud" else route.name) == what


@pytest.mark.parametrize("question", [
    "how do I pay my electricity bill online?", "what is the order of operations in maths", "transfer learning explained",
    "text summarization techniques", "is it safe to turn off the firewall?", "what happens if I format a drive",
    "buy vs rent: which is better for a student?", "why do people delete their accounts",
])
def test_a_question_about_doing_something_is_a_question_not_a_request(question):
    route = router.route(question)
    assert route.kind == "cloud", route


@pytest.mark.parametrize("question,action", [
    ("Kairu, pay the rent", "money.spend"), ("book a cab to the airport", "money.spend"),
    ("can you delete all my photos", "files.delete"), ("disable windows defender", "security.disable"),
    ("format the c drive", "system.destroy"), ("change my password", "security.change"),
    ("send a message to Amma", "message.send"), ("tell me my pin", "credentials.reveal"),
])
def test_a_request_to_do_something_is_handed_to_guardian_by_its_policy_name(question, action):
    route = router.route(question)
    assert (route.level, route.kind, route.name) == ("L0", "action", action)


def test_a_follow_up_takes_the_last_answer_along_and_the_filter_reads_all_of_it():
    previous = ("who is the prime minister of India", "Narendra Modi.\nWant to know more about him?")
    route = router.route("yes, tell me more", previous)
    assert route.follow_up and route.privacy.level == "public" and route.dated
    assert not router.route("yes, tell me more").follow_up  # no answer before it: an ordinary question
    leaked = ("my number?", "It is 9876543210.")
    assert router.route("tell me more", leaked).privacy.level == "personal"


def test_questions_whose_answer_may_have_changed_are_marked():
    assert router.route("who is the CEO of Google?").dated
    assert router.route("what is the latest version of Python").dated
    assert not router.route("what is photosynthesis").dated


@pytest.mark.parametrize("question", [
    "call Ravi", "call my friend Ravi on 9876543210", "Kairu, please call mom", "call Ravi on +91 98765 43210 now",
    "dial 9876543210", "phone my brother", "make a call to Priya", "ring my mother tonight",
])
def test_a_request_to_make_a_call_is_answered_here_and_nothing_is_sent(question):
    route = router.route(question)
    assert (route.level, route.kind, route.name) == ("L0", "rule", "call"), route


@pytest.mark.parametrize("question,level", [
    ("how do I call someone from Windows?", "public"), ("phone repair shops near me", "public"),
    ("call of duty tips", "public"), ("call center jobs", "public"), ("call logs on my phone", "public"),
    ("call this function with two arguments", "public"), ("ring a bell", "public"),
    ("phone number of the police", "public"), ("call me on 9876543210", "personal"),
    ("my password is Tiger@123, call Ravi", "secret"),
])
def test_other_sentences_with_call_or_phone_are_not_call_requests_and_still_pass_the_filter(question, level):
    route = router.route(question)
    assert (route.kind, route.privacy.level) == ("cloud", level), route


def test_levels_one_and_two_are_off_on_the_pc_in_phase_b():
    assert "off" in router.LEVELS["L1"][1] and "off" in router.LEVELS["L2"][1]
    assert {router.route(question).level for question, *_ in GATE} == {"L0", "L3", "L4"}
