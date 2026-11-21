"""ADR-054 (proposed, the owner's GO of 20 Nov 2026): the screen agent, finished, and "register / apply / log in when I say".

    - yes without the PIN, only for screen.agent_confirm, only inside a take-control run at the PC; every other High action
      still needs "yes" and the PIN, and policy.yaml can give no other action `pin: false`;
    - scroll, choose, tick, a point, hand-over ("Your turn ... go on"), Gemini's "too many requests", the time each look took;
    - My details: on this PC only, never a secret; Gemini sees only a detail's NAME, screen.fill types the value here, later
      pictures paint those boxes black, and the run is locked to the site the first detail was typed on;
    - the browser's own saved login, never a password read or typed;
    - "scroll down" as a plain order.

Everything runs on the pretend PC (KAIRU_TEST_PC) with a stand-in Gemini on 127.0.0.1: no real picture, click or request.
"""

import json

import pytest
import yaml

from kairu import executors, policy
from kairu.brain import keys
from kairu.guardian import Action, Refused, Verdict
from kairu.policy import Tier
from kairu.tasks import agent, details, eyes, pc, screen
from kairu.tasks.actions import Refusal
from kairu.tasks.core import Step, TaskCore
from kairu.tasks.store import TaskStore
from tests_kairu.helpers import PIN, POLICY
from tests_kairu.program import end, program, program_with_pin, start  # noqa: F401 (fixtures)
from tests_kairu.test_day4_program import Owner, calls
from tests_kairu.test_screen_agent import (GEMINI_KEY, JOB, ON, config_path, core_for, desk, fast, gemini,  # noqa: F401
                                           providers, steps, work)

RULES = policy.load(POLICY).rules
EMAIL = "saitej.k@example.com"
NAME = "Saitej Kumar"


def set_pc(desk, **changes):
    state = json.loads((desk / "pc.json").read_text())
    state.update(changes)
    (desk / "pc.json").write_text(json.dumps(state))


def reply_of(data_dir):
    return TaskStore(data_dir).take_reply(JOB)


# --- yes without the PIN: one action only ----------------------------------------------------------------------------

def test_only_screen_agent_confirm_is_high_without_a_pin_and_every_other_high_still_needs_one():
    rule = RULES["screen.agent_confirm"]
    assert rule.tier is Tier.HIGH and rule.pin is False and rule.private
    assert [name for name, rule in RULES.items() if not rule.pin] == ["screen.agent_confirm"]
    assert RULES["screen.confirm"].pin is True and RULES["details.keep"].tier is Tier.HIGH and RULES["details.keep"].pin
    assert policy.NO_PIN_ACTIONS == frozenset({"screen.agent_confirm"})


@pytest.mark.parametrize("entry", [
    "  screen.confirm:\n    tier: High\n    pin: false\n",                    # any other action
    "  screen.agent_confirm:\n    tier: Medium\n    pin: false\n",            # not High
    "  screen.agent_confirm:\n    tier: Critical\n    pin: false\n",          # Critical never gets an approval path
    "  screen.agent_confirm:\n    tier: High\n    pin: \"no\"\n",             # not true or false
])
def test_a_policy_that_gives_any_other_action_no_pin_is_refused_whole(tmp_path, entry):
    path = tmp_path / "policy.yaml"
    path.write_text("version: 1\nactions:\n" + entry)
    with pytest.raises(policy.PolicyError):
        policy.load(path)


def test_guardian_takes_yes_alone_only_for_screen_agent_confirm(program_with_pin):
    client = program_with_pin.client
    careful = Action("screen.agent_confirm", {"verb": "click", "app": "chrome", "what": "Submit", "field": "", "enter": "no",
                                              "site": "", "filled": "", "job": "a" * 16})
    decision = client.check(careful)
    assert decision.verdict is Verdict.NEEDS_APPROVAL and decision.pin is False and decision.tier is Tier.HIGH
    with pytest.raises(Refused):
        client.approve(decision.request_id, "no", "")  # still needs "yes"
    decision = client.check(careful)
    assert client.approve(decision.request_id, "yes", "").action == "screen.agent_confirm"
    old = client.check(Action("screen.confirm", {"verb": "click", "app": "chrome", "what": "Submit", "job": "b" * 16}))
    assert old.verdict is Verdict.NEEDS_APPROVAL and old.pin is True
    with pytest.raises(Refused):
        client.approve(old.request_id, "yes", "")  # outside a run: the PIN, as always
    for name in ("details.keep", "hands.mark_safe", "screen.confirm"):
        assert client.check(Action(name, {"job": "c" * 16})).pin is True


def test_screen_agent_confirm_is_still_refused_in_safe_mode_and_never_runs_without_an_approval(program_with_pin, desk):
    client = program_with_pin.client
    with pytest.raises(Refused):
        client.run(Action("screen.agent_confirm", {"verb": "click", "app": "chrome", "what": "Submit", "job": "d" * 16}))
    from kairu import safemode
    from kairu.store import Store
    safemode.emergency_stop(Store(program_with_pin.data_dir), "test")
    assert client.check(Action("screen.agent_confirm", {"verb": "click", "app": "chrome", "what": "x",
                                                        "job": "e" * 16})).verdict is Verdict.DENY


def test_the_new_actions_run_only_their_own_code_and_no_request_can_carry_a_details_value():
    for name in ("screen.scroll", "screen.choose", "screen.tick", "screen.point", "screen.fill", "screen.saved_password",
                 "screen.agent_confirm", "details.keep", "details.forget", "details.show"):
        assert name in RULES and name in executors.EXECUTORS and RULES[name].private, name
        assert executors.EXECUTORS[name].supplied == ("data_dir",)
    assert set(executors.EXECUTORS["screen.fill"].arguments) == {"job", "app", "box", "detail", "site"}  # a name, never a value
    assert RULES["screen.fill"].tier is RULES["screen.scroll"].tier is Tier.MEDIUM
    assert RULES["details.show"].read_only and RULES["details.show"].tier is Tier.LOW


# --- my details: on this PC only, never a secret ---------------------------------------------------------------------

def test_details_are_kept_and_read_by_name_and_a_secret_is_never_kept(tmp_path):
    assert details.keep(tmp_path, "email", EMAIL) == "Kept your email, on this PC only."
    assert details.keep(tmp_path, details.key_of("Mobile number"), "+91 98765 43210").startswith("Kept your phone")
    assert details.keep(tmp_path, "username", "sungjenwoo", "https://www.github.com/login").endswith("for github.com, on this PC only.")
    for key, value in [("name", "my password is Tiger@123"), ("phone", "1234 5678 9012 3456"), ("email", "not an email"),
                       ("city", "Aadhaar 1234 5678 9012"), ("name", "otp 482916")]:
        with pytest.raises(details.DetailProblem):
            details.keep(tmp_path, key, value)
    with pytest.raises(details.DetailProblem):
        details.keep(tmp_path, "username", "x")  # a username needs its site
    with pytest.raises(details.DetailProblem):
        details.keep(tmp_path, "password", "Tiger@123")  # a password is never a detail
    assert details.value(tmp_path, "email") == EMAIL
    assert details.value(tmp_path, "username", "github.com") == "sungjenwoo"
    assert details.value(tmp_path, "username", "internshala.com") == EMAIL  # no username there: your email
    assert details.forget(tmp_path, "phone") == "Forgotten: your phone number."


def test_a_secret_put_in_the_file_by_hand_is_never_read(tmp_path):
    (tmp_path / details.FILE).write_text(json.dumps({"email": EMAIL, "name": "my password is Tiger@123",
                                                     "password": "Tiger@123", "username:not a site": "x"}))
    assert details.load(tmp_path) == {"email": EMAIL}


@pytest.mark.parametrize("address,site", [
    ("https://internshala.com/internships", "internshala.com"), ("www.github.com/login", "github.com"),
    ("https://accounts.google.co.in/signin", "google.co.in"), ("internshala.com", "internshala.com"),
    ("http://user@evil.example.org:8080/x", "example.org"), ("chrome://settings", ""), ("not a site", ""),
])
def test_a_site_is_the_name_you_registered(address, site):
    assert details.site_of(address) == site


def test_details_orders_reach_their_actions():
    from kairu.tasks import skills
    usable, refused = skills.check(skills.SKILLS, RULES)
    assert refused == ()
    for order, action, wanted in [
        (f"save my email as {EMAIL}", "details.keep", {"key": "email", "value": EMAIL}),
        ("set my username for github.com to sungjenwoo", "details.keep", {"key": "username", "site": "github.com"}),
        ("show my details", "details.show", {}),
        ("forget my saved phone number", "details.forget", {"key": "phone number"}),
        ("scroll down", "screen.scroll", {"direction": "down", "times": "3", "app": ""}),
        ("scroll up 5 times", "screen.scroll", {"direction": "up", "times": "5"}),
        ("scroll down in chrome", "screen.scroll", {"app": "chrome"}),
        ("scroll to the bottom", "screen.scroll", {"direction": "down", "times": "10"}),
    ]:
        found = skills.match(usable, order)
        assert found and found[0].action == action, order
        assert wanted.items() <= found[1].items(), (order, found[1])


# --- the new hands, on the pretend PC ------------------------------------------------------------------------------

@pytest.fixture
def form(desk):
    set_pc(desk, address={"chrome": "https://internshala.com/apply"},
           controls={"chrome": [["box", "Full name"], ["box", "Email address"], ["button", "Submit"], ["button", "Next"]],
                     "notepad": [["box", "Text editor"]]},
           password_boxes={"chrome": ["Password"]},
           rects={"chrome": {"Full name": [10, 10, 200, 30], "Email address": [10, 40, 200, 60]}},
           lists={"chrome": {"Course": ["B.Tech", "M.Tech"], "Pay with": ["Pay now"]}},
           ticks={"chrome": {"Remember me": False, "I agree to the terms": False}},
           points={"chrome": {"40,50": {"name": "Search", "password": False}, "60,70": {"name": "Submit", "password": False},
                              "80,90": {"name": "", "password": False}, "5,5": {"name": "", "password": True}}},
           saved_logins={"chrome": ["sungjenwoo"]})
    return desk


def test_scroll_goes_by_the_wheel_and_never_into_kairus_own_or_a_terminal(tmp_path, form):
    sys = pc.backend()
    assert screen._scroll(sys, "chrome", "down", "3") == "Scrolled down in Chrome."
    assert screen._scroll(sys, "", "up", "10") == "Scrolled up in Chrome."
    assert calls(form)[-1] == "scroll chrome 10" and "scroll chrome -3" in calls(form)
    for direction, times in (("left", "3"), ("down", "11"), ("down", "0"), ("down", "x")):
        with pytest.raises(Refusal):
            screen._scroll(sys, "chrome", direction, times)
    set_pc(form, windows=[{"app": "cmd", "title": "Command Prompt"}])
    with pytest.raises(Refusal, match="security"):
        screen._scroll(sys, "cmd", "down", "3")
    with pytest.raises(Refusal, match="own windows"):
        screen._scroll(sys, "kairu", "down", "3")


def test_choose_tick_and_point_keep_the_tiers_of_what_is_really_there(tmp_path, form):
    sys = pc.backend()
    assert screen._choose(sys, "chrome", "Course", "B.Tech", False) == 'Chose "B.Tech" in "Course" in Chrome.'
    with pytest.raises(Refusal, match="Money"):
        screen._choose(sys, "chrome", "Pay with", "Pay now", False)
    with pytest.raises(Refusal, match="Money"):
        screen._choose(sys, "chrome", "Pay with", "Pay now", True)  # no approval path
    assert screen._tick(sys, "chrome", "Remember me", "yes", False) == 'Ticked "Remember me" in Chrome.'
    with pytest.raises(Refusal, match=screen.NEEDS_PIN):
        screen._tick(sys, "chrome", "I agree to the terms", "yes", False)
    assert screen._tick(sys, "chrome", "I agree to the terms", "yes", True).startswith("Ticked")
    assert screen._tick(sys, "chrome", "I agree to the terms", "no", False).startswith("Unticked")  # unticking asks nothing
    assert screen._point(sys, "chrome", "40,50", False) == 'Clicked "Search" in Chrome (at the point Gemini named).'
    with pytest.raises(Refusal, match=screen.NEEDS_PIN):
        screen._point(sys, "chrome", "60,70", False)  # "Submit" is there: as careful as a click by name
    with pytest.raises(Refusal, match=screen.NEEDS_PIN):
        screen._point(sys, "chrome", "80,90", False)  # nothing readable there: you decide
    assert screen._point(sys, "chrome", "80,90", True) == "Clicked the point you approved in Chrome."
    with pytest.raises(Refusal, match="password box"):
        screen._point(sys, "chrome", "5,5", True)
    with pytest.raises(Refusal):
        screen._point(sys, "chrome", "x,1", True)
    assert "point chrome 40 50" in calls(form) and "point chrome 60 70" not in calls(form)
    assert screen.needs_pin_now("screen.tick", {"target": "I agree to the terms", "on": "yes"})
    assert screen.needs_pin_now("screen.choose", {"box": "Account", "item": "Delete account"})


def test_fill_types_a_saved_detail_by_its_name_only_on_the_runs_site_and_never_says_it(tmp_path, form):
    sys, data = pc.backend(), str(tmp_path)
    details.keep(data, "email", EMAIL)
    said = screen._fill(sys, data, "chrome", "Email address", "email", "internshala.com")
    assert said == 'Filled your email in "Email address" on internshala.com.' and EMAIL not in said
    assert calls(form)[-3:] == ["focus chrome Email address", "press chrome ctrl+a", f"type chrome {EMAIL}"]
    with pytest.raises(Refusal, match="not internshala-jobs.xyz|not internshala.com"):
        screen._fill(sys, data, "chrome", "Email address", "email", "internshala-jobs.xyz")
    with pytest.raises(Refusal, match=screen.YOUR_TURN):
        screen._fill(sys, data, "chrome", "Full name", "name", "")  # not saved: your turn
    with pytest.raises(Refusal, match=screen.YOUR_TURN):
        screen._fill(sys, data, "chrome", "Password", "email", "")  # a password box: never
    with pytest.raises(Refusal, match="only in the browser"):
        screen._fill(sys, data, "notepad", "Text editor", "email", "")
    with pytest.raises(Refusal, match="saved details"):
        screen._fill(sys, data, "chrome", "Email address", "password", "")
    set_pc(form, address={"chrome": ""})
    with pytest.raises(Refusal, match="can't tell which site"):
        screen._fill(sys, data, "chrome", "Email address", "email", "")
    set_pc(form, address={"chrome": "https://internshala.com"}, password_focus=["chrome"])
    with pytest.raises(Refusal, match=screen.YOUR_TURN):
        screen._fill(sys, data, "chrome", "Email address", "email", "")
    assert sum(line == f"type chrome {EMAIL}" for line in calls(form)) == 1


def test_the_saved_login_is_the_browsers_own_or_it_is_your_turn(tmp_path, form):
    sys, data = pc.backend(), str(tmp_path)
    set_pc(form, address={"chrome": "https://github.com/login"})
    with pytest.raises(Refusal, match=screen.YOUR_TURN):
        screen._saved_password(sys, data, "chrome", "")  # no username for github.com and no email
    details.keep(data, "username", "sungjenwoo", "github.com")
    assert screen._saved_password(sys, data, "chrome", "github.com").startswith("Picked the browser's saved login")
    assert calls(form)[-1] == "saved login chrome sungjenwoo"
    details.keep(data, "username", "someone-else", "github.com")
    with pytest.raises(Refusal, match=screen.YOUR_TURN):
        screen._saved_password(sys, data, "chrome", "github.com")
    assert not any("type" in line for line in calls(form))  # a password is never typed by Kairu


# --- the look: filled boxes painted black, no picture at a password box, your details never sent ------------------------

def test_a_look_paints_filled_boxes_black_and_never_sends_your_details(tmp_path, form, gemini):
    keys.save(tmp_path, "gemini", GEMINI_KEY)
    details.keep(tmp_path, "email", EMAIL)
    set_pc(form, controls={"chrome": [["box", "Full name"], ["box", "Email address"], ["text", EMAIL],
                                      ["button", f"Signed in as {EMAIL}"], ["button", "Submit"]]})
    gemini.answers["gemini"] = '{"do": "click", "target": "Submit"}'
    eyes.look(str(tmp_path), JOB, "chrome", "apply for the internship", "", "next", ON, json.dumps(["Email address"]))
    reply = reply_of(tmp_path)
    assert reply.ok and json.loads(reply.text)["site"] == "internshala.com"
    assert calls(form) == ["picture chrome hide:1"]
    assert EMAIL not in gemini.text_heard() and "Signed in as" not in gemini.text_heard()


def test_a_box_that_cant_be_found_or_a_password_box_with_the_keyboard_means_no_picture(tmp_path, form, gemini):
    keys.save(tmp_path, "gemini", GEMINI_KEY)
    gemini.answers["gemini"] = '{"do": "handover", "say": "Type your password."}'
    eyes.look(str(tmp_path), JOB, "chrome", "log in", "", "next", ON, json.dumps(["No such box"]))
    blind = reply_of(tmp_path)
    assert blind.ok and json.loads(blind.text).get("blind") is True
    parts = gemini.heard("gemini")[-1]["body"]["contents"][-1]["parts"]
    assert len(parts) == 1 and "No picture this time" in parts[0]["text"]
    set_pc(form, password_focus=["chrome"])
    eyes.look(str(tmp_path), JOB, "chrome", "log in", "", "next", ON)
    assert json.loads(reply_of(tmp_path).text).get("blind") is True
    assert len(gemini.heard("gemini")[-1]["body"]["contents"][-1]["parts"]) == 1
    assert calls(form) == []  # no picture was ever taken
    with pytest.raises(Exception):
        eyes._hidden("not json")


def test_kairus_new_instructions_pass_the_backstop():
    from kairu.brain import privacy
    assert privacy.secrets_in(eyes.NEXT) == []
    assert privacy.secrets_in(eyes.NEXT + "\nNo picture this time: the keyboard is in a password box, so no picture was taken.") == []


# --- reading the new proposals strictly ------------------------------------------------------------------------------

@pytest.mark.parametrize("proposal,expected", [
    ({"do": "scroll", "direction": "down", "times": 2}, Step("screen.scroll", {"app": "chrome", "direction": "down", "times": "2"})),
    ({"do": "choose", "list": "Course", "item": "B.Tech"}, Step("screen.choose", {"app": "chrome", "box": "Course", "item": "B.Tech"})),
    ({"do": "tick", "target": "Remember me"}, Step("screen.tick", {"app": "chrome", "target": "Remember me", "on": "yes"})),
    ({"do": "tick", "target": "Remember me", "on": False}, Step("screen.tick", {"app": "chrome", "target": "Remember me", "on": "no"})),
    ({"do": "point", "x": 40, "y": 50}, Step("screen.point", {"app": "chrome", "point": "40,50"})),
    ({"do": "fill", "detail": "e-mail", "box": "Email address"},
     Step("screen.fill", {"app": "chrome", "box": "Email address", "detail": "email", "site": ""})),
    ({"do": "password"}, Step("screen.saved_password", {"app": "chrome", "site": ""})),
])
def test_the_new_proposals_become_kairus_own_steps(proposal, expected):
    kind, step, _ = agent.next_step(proposal, "chrome")
    assert kind == "step" and step == expected


@pytest.mark.parametrize("proposal", [
    {"do": "scroll", "direction": "left"}, {"do": "scroll", "times": 50}, {"do": "choose", "list": "x"},
    {"do": "tick", "target": "x", "on": "maybe"}, {"do": "point", "x": "1", "y": 2}, {"do": "point", "x": -1, "y": 2},
    {"do": "fill", "detail": "password", "box": "Password"}, {"do": "fill", "detail": "card number", "box": "Card"},
    {"do": "fill", "detail": "email"}, {"do": "type_password", "text": "x"},
])
def test_other_new_proposals_are_no_step(proposal):
    with pytest.raises(agent.NoStep):
        agent.next_step(proposal, "chrome")
    with pytest.raises(agent.NoStep):
        agent.next_step({"do": "scroll", "direction": "down"}, "")  # no window seen yet


def test_handover_is_its_own_kind():
    assert agent.next_step({"do": "handover", "say": "Solve the captcha."}, "chrome") == ("handover", None, "Solve the captcha.")


# --- the whole run, through the real Guardian program ------------------------------------------------------------------

class Watcher(Owner):
    """The owner at the bar: yes with NO PIN typed (ADR-054), and "go on" to every hand-over."""

    def __init__(self, program, yes=True, go_on=True):
        super().__init__(program, yes, pin="")
        self.go_on, self.turns, self.events = go_on, [], []

    def handover(self, text, seconds):
        self.turns.append((text, seconds))
        return self.go_on


def core_with(program, owner) -> TaskCore:
    return TaskCore(program.config, program.client, approver=owner.approver, confirmer=owner.confirmer,
                    plan_approver=owner.plan_approver, handover=owner.handover, progress=owner.events.append)


@pytest.fixture
def watcher(program_with_pin):
    keys.save(program_with_pin.data_dir, "gemini", GEMINI_KEY)
    return Watcher(program_with_pin)


def test_sign_up_fills_your_details_by_name_and_asks_is_this_correct_without_a_pin(program_with_pin, watcher, providers,
                                                                                    form, fast):
    details.keep(program_with_pin.data_dir, "name", NAME)
    details.keep(program_with_pin.data_dir, "email", EMAIL)
    providers.script["gemini"] = steps({"do": "fill", "detail": "name", "box": "Full name"},
                                       {"do": "fill", "detail": "email", "box": "Email address"},
                                       {"do": "click", "target": "Submit"},
                                       {"do": "done", "say": "The application was sent."})
    reply = core_with(program_with_pin, watcher).handle("take control and apply for this internship on internshala")
    assert reply.startswith("Done (Gemini's word, from the screen): The application was sent."), reply
    assert "3 of 3 steps done" in reply and "Looks took" in reply
    assert len(watcher.cards) == 1
    card = watcher.cards[0]
    assert card.action.name == "screen.agent_confirm" and card.pin is False and card.tier is Tier.HIGH
    assert card.action.details["site"] == "internshala.com"
    assert card.action.details["filled"] == "Full name: name; Email address: email"  # names only, never your details
    log = calls(form)
    assert f"type chrome {NAME}" in log and f"type chrome {EMAIL}" in log and "click chrome Submit" in log
    assert log.index(f"type chrome {EMAIL}") < log.index("click chrome Submit")
    assert "picture chrome hide:1" in log and "picture chrome hide:2" in log  # later pictures paint those boxes black
    assert NAME not in providers.text_heard() and EMAIL not in providers.text_heard()  # Gemini never saw your details
    assert {"kind": "control", "on": True} in watcher.events and watcher.events[-1] == {"kind": "control", "on": False}


def test_saying_no_to_is_this_correct_sends_nothing(program_with_pin, providers, form, fast):
    keys.save(program_with_pin.data_dir, "gemini", GEMINI_KEY)
    details.keep(program_with_pin.data_dir, "email", EMAIL)
    no = Watcher(program_with_pin, yes=False)
    no.confirmer = lambda text: no.confirmed.append(text) or True  # yes to the run, no to the card
    providers.script["gemini"] = steps({"do": "fill", "detail": "email", "box": "Email address"},
                                       {"do": "click", "target": "Submit"}, {"do": "done", "say": "sent"})
    reply = core_with(program_with_pin, no).handle("take control and sign me up for the newsletter")
    assert reply.startswith("Not done: you refused it.") and "click chrome Submit" not in calls(form)


def test_the_run_stops_when_the_page_moves_to_another_site_after_a_detail_was_typed(program_with_pin, watcher, providers,
                                                                                   form, fast):
    details.keep(program_with_pin.data_dir, "email", EMAIL)
    providers.script["gemini"] = steps({"do": "fill", "detail": "email", "box": "Email address"},
                                       {"do": "click", "target": "Next"}, {"do": "done", "say": "x"})
    core = core_with(program_with_pin, watcher)
    real_run_step = core._run_step

    def moved(step, *args, **kwargs):  # after the email is typed, the page goes to a look-alike
        done = real_run_step(step, *args, **kwargs)
        if step.action == "screen.fill":
            set_pc(form, address={"chrome": "https://internshala-login.xyz/apply"})
        return done
    core._run_step = moved
    reply = core.handle("take control and apply on internshala")
    assert "the page moved to internshala-login.xyz, not internshala.com" in reply
    assert "click chrome Next" not in calls(form)


def test_details_go_only_to_the_site_you_named_or_the_one_open_when_you_started(program_with_pin, watcher, providers,
                                                                                form, fast):
    details.keep(program_with_pin.data_dir, "email", EMAIL)
    set_pc(form, address={"chrome": "https://newsletter-prizes.example.com/win"})
    providers.script["gemini"] = steps({"do": "visit", "url": "https://free-gifts.example.net"},
                                       {"do": "fill", "detail": "email", "box": "Email address"},
                                       {"do": "done", "say": "x"})
    core = core_with(program_with_pin, watcher)
    real_run_step = core._run_step

    def moved(step, *args, **kwargs):
        done = real_run_step(step, *args, **kwargs)
        if step.action == "web.open":
            set_pc(form, address={"chrome": "https://free-gifts.example.net/claim"})
        return done
    core._run_step = moved
    reply = core.handle("take control and sign me up for the newsletter")
    assert "I type your details only on the site you named or the one open when you started" in reply
    assert f"type chrome {EMAIL}" not in calls(form)
    assert agent.allowed_site("internshala.com", "", "apply for this internship on internshala")
    assert agent.allowed_site("github.com", None, "log in to github.com")
    assert agent.allowed_site("example.com", "example.com", "sign me up")
    assert not agent.allowed_site("internshala-login.xyz", "", "apply on internshala")
    assert not agent.allowed_site("", "", "apply on internshala")


def test_your_turn_waits_for_go_on_and_then_looks_again(program_with_pin, watcher, providers, desk, fast):
    providers.script["gemini"] = steps({"do": "handover", "say": "Solve the captcha."},
                                       {"do": "click", "target": "Search"}, {"do": "done", "say": "Searched."})
    reply = core_with(program_with_pin, watcher).handle("take control and search lofi music on youtube")
    assert reply.startswith("Done") and watcher.turns and watcher.turns[0][0] == "Your turn: Solve the captcha."
    assert 0 < watcher.turns[0][1] <= agent.MOST_SECONDS
    record = providers.heard("gemini")[1]["body"]["contents"][-1]["parts"][0]["text"]
    assert "the owner's turn (Solve the captcha.): the owner said go on" in record
    assert calls(desk).count("picture chrome") == 3  # one look before, none while you worked, then two more


def test_your_turn_without_go_on_ends_the_run(program_with_pin, providers, desk, fast):
    keys.save(program_with_pin.data_dir, "gemini", GEMINI_KEY)
    gone = Watcher(program_with_pin, go_on=False)
    providers.script["gemini"] = steps({"do": "stuck", "say": "Please sign in to YouTube first."})
    reply = core_with(program_with_pin, gone).handle("take control and like the video")
    assert reply == "I need you: Please sign in to YouTube first." and gone.turns


def test_a_missing_saved_login_hands_over_for_the_password(program_with_pin, watcher, providers, form, fast):
    set_pc(form, address={"chrome": "https://github.com/login"}, saved_logins={"chrome": []})
    providers.script["gemini"] = steps({"do": "password"}, {"do": "click", "target": "Next"},
                                       {"do": "done", "say": "Signed in."})
    reply = core_with(program_with_pin, watcher).handle("take control and log in to my github")
    assert reply.startswith("Done") and watcher.turns[0][0].startswith(screen.YOUR_TURN)
    assert "type your password yourself" in watcher.turns[0][0]


def test_gemini_too_many_requests_waits_once_then_tries_again(program_with_pin, watcher, providers, desk, fast, monkeypatch):
    monkeypatch.setattr(agent.ScreenAgent, "_busy_wait", lambda self: 0)
    monkeypatch.setattr(agent, "BUSY_WAIT", 0)
    first = {"done": False}
    real_look = agent.ScreenAgent._look

    def look(self, app, goal, record, hide=None):
        if not first["done"]:
            first["done"] = True
            return False, "Not sent: Gemini at its free limit. Ask again after 10:31.", 0.1
        return real_look(self, app, goal, record, hide)
    monkeypatch.setattr(agent.ScreenAgent, "_look", look)
    providers.script["gemini"] = steps({"do": "done", "say": "Nothing to do."})
    reply = core_with(program_with_pin, watcher).handle("take control and check the page")
    assert reply == "Done (Gemini's word, from the screen): Nothing to do."
    assert any(event.get("state") == "waiting" and "too many requests" in event.get("text", "")
               for event in watcher.events)


def test_gemini_still_busy_after_the_wait_ends_with_a_clear_message(program_with_pin, watcher, providers, desk, fast,
                                                                    monkeypatch):
    monkeypatch.setattr(agent.ScreenAgent, "_busy_wait", lambda self: 0)
    monkeypatch.setattr(agent.ScreenAgent, "_look",
                        lambda self, app, goal, record, hide=None: (False, "Not sent: Gemini at its free limit.", 0.1))
    reply = core_with(program_with_pin, watcher).handle("take control and check the page")
    assert reply.startswith("I stopped: Gemini is still busy") and "Try again in a minute" in reply


def test_outside_a_run_the_same_careful_step_still_needs_the_pin(program_with_pin, desk):
    owner = Owner(program_with_pin, pin="")  # yes, but no PIN
    core = TaskCore(program_with_pin.config, program_with_pin.client, approver=owner.approver, confirmer=owner.confirmer)
    reply = core.handle("click Send in chrome")
    assert owner.cards and owner.cards[0].action.name == "screen.confirm" and owner.cards[0].pin is True
    assert reply.startswith("Not done") and "click chrome Send" not in calls(desk)
    assert core.in_control is False


def test_scroll_down_is_a_plain_order_with_no_card(program_with_pin, desk):
    owner = Owner(program_with_pin)
    core = TaskCore(program_with_pin.config, program_with_pin.client, approver=owner.approver, confirmer=owner.confirmer)
    assert core.handle("scroll down") == "Scrolled down in Chrome."
    assert core.handle("scroll up 2 times in notepad") == "Scrolled up in Notepad."
    assert owner.cards == [] and "scroll chrome -3" in calls(desk) and "scroll notepad 2" in calls(desk)


def test_save_my_email_is_high_and_show_my_details_stays_in_the_bar(program_with_pin, desk):
    owner = Owner(program_with_pin)
    core = TaskCore(program_with_pin.config, program_with_pin.client, approver=owner.approver, confirmer=owner.confirmer)
    assert core.handle(f"save my email as {EMAIL}") == "Kept your email, on this PC only."
    assert owner.cards and owner.cards[0].action.name == "details.keep" and owner.cards[0].pin is True
    assert details.value(program_with_pin.data_dir, "email") == EMAIL
    assert EMAIL in core.handle("show my details")
    from kairu.live import relay
    told, _ = relay.told("show my details", core.handle("show my details"))
    assert EMAIL not in told  # Kairu Live is never told your details


# --- the bar: spoken answers reach only a take-control card -----------------------------------------------------------

@pytest.mark.parametrize("said,card,word", [
    ("Yes.", "correct", "yes"), ("yes, it's correct", "correct", "yes"), ("Kairu, yes", "correct", "yes"),
    ("no", "correct", "no"), ("that's wrong", "correct", "no"), ("go on", "turn", "go on"), ("I'm done.", "turn", "go on"),
    ("stop here", "turn", "stop"), ("yes 4 8 2 9", "correct", ""), ("482916", "correct", ""),
    ("yes delete everything", "correct", ""), ("go on", "correct", ""), ("yes", "turn", ""), ("yes", "", ""),
])
def test_only_a_plain_answer_is_a_spoken_answer(said, card, word):
    from kairu.bar.voice import spoken_answer
    assert spoken_answer(said, card) == word


class CardScreen:
    def __init__(self, card):
        self.card, self.said, self.spoken_words, self.heard_lines = card, [], [], []

    def card_open(self):
        return True

    def spoken_card(self):
        return self.card

    def spoken(self, word):
        self.spoken_words.append(word)

    def say(self, text):
        self.said.append(text)

    def heard(self, text):
        self.heard_lines.append(text)

    def show(self):
        pass


def voice_with(card):
    from kairu.bar.voice import VoiceControl
    control = VoiceControl.__new__(VoiceControl)  # only _event's routing is under test here: no mic, no listener
    control.ui, control.live, control.cfg = CardScreen(card), True, None
    import queue
    import threading
    control._orders, control._lock, control._results = queue.Queue(), threading.Lock(), []
    control.today = type("Today", (), {"add": lambda self, role, text: None})()
    control.cfg = type("Cfg", (), {"brain_talk_history": False, "voice_key": "V"})()
    return control


def test_kairu_lives_words_answer_a_take_control_card_and_nothing_else():
    control = voice_with("correct")
    control._event({"heard": "Yes, it's correct."})
    assert control.ui.spoken_words == ["yes"] and control._orders.empty()
    control._event({"heard": "482916"})  # a PIN said aloud answers nothing
    assert control.ui.spoken_words == ["yes"]
    pin_card = voice_with("")  # an ordinary card (yes and PIN): a spoken yes still goes nowhere
    pin_card._event({"order": "yes", "live": 3})
    assert pin_card.ui.spoken_words == [] and pin_card._orders.empty()
