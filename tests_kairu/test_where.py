"""research.location: "where am I?" from Windows' location, said as the area and city (the owner, 19 Nov 2026)."""

import json

import pytest

from kairu import executors, policy
from kairu.brain import router
from kairu.config import ROOT
from kairu.research import where
from kairu.research.store import ResearchStore
from tests_kairu.helpers import POLICY


@pytest.mark.parametrize("said", ["where am I", "Where am I?", "Kairu, where am I right now", "what is my location",
                                  "whats my location", "which area am I in", "locate me", "what's my current location"])
def test_where_am_i_questions_are_taken(said):
    assert where.asked(said)
    route = router.route(said)
    assert (route.kind, route.name, route.query) == ("cloud", "location", "")


@pytest.mark.parametrize("said", ["where am I going wrong with this code", "what is my location history in google",
                                  "where is Hyderabad", "remember that my location is Ameerpet", "weather in Hyderabad"])
def test_other_questions_are_not_taken(said):
    assert not where.asked(said)


def test_it_is_a_medium_private_research_action_that_reaches_only_openstreetmap():
    rule = policy.load(POLICY).rules["research.location"]
    assert rule.tier.name == "MEDIUM" and rule.private and rule.feature == "research" and not rule.read_only
    assert dict(executors.EXECUTORS["research.location"].arguments) == {"job": str}
    assert where.HOSTS == ("nominatim.openstreetmap.org",)
    text = (ROOT / "kairu" / "research" / "where.py").read_text(encoding="utf-8")
    assert text.count("urlopen(") == 1 and "not in HOSTS" in text and "shell=True" not in text


def test_only_a_position_rounded_to_about_a_kilometre_is_asked():
    address = where.reverse_address(17.435678, 78.448123)
    assert "lat=17.44" in address and "lon=78.45" in address and "17.4356" not in address
    assert address.startswith("https://nominatim.openstreetmap.org/reverse?")


def _pretend(tmp_path, monkeypatch, found):
    path = tmp_path / "where.json"
    path.write_text(json.dumps(found), encoding="utf-8")
    monkeypatch.setenv(where.TEST_LOCATION, str(path))


def test_only_the_area_city_and_state_are_kept_never_a_road_or_postcode(tmp_path, monkeypatch):
    _pretend(tmp_path, monkeypatch, {"position": [17.43567, 78.44812],
                                     "address": {"road": "Mytrivanam Rd", "house_number": "7-1-24", "postcode": "500016",
                                                 "suburb": "Ameerpet", "city": "Hyderabad", "state": "Telangana"}})
    where.main(str(tmp_path), "a" * 16)
    found = ResearchStore(str(tmp_path)).take("a" * 16, "location")
    assert found == {"area": "Ameerpet", "city": "Hyderabad", "state": "Telangana"}
    assert where.answer(found) == "You're in Ameerpet, Hyderabad, Telangana.\nWant me to find something nearby?"


def test_location_off_is_said_plainly_with_where_to_turn_it_on(tmp_path, monkeypatch):
    _pretend(tmp_path, monkeypatch, {"position": "denied"})
    where.main(str(tmp_path), "b" * 16)
    said = where.answer(ResearchStore(str(tmp_path)).take("b" * 16, "location"))
    assert said.startswith("Windows' location is off") and "Privacy & security" in said
    with pytest.raises(SystemExit):
        where.main(str(tmp_path), "not-a-job")


def test_the_brain_asks_guardian_for_it_only_at_the_pc_and_never_sends_it_to_an_ai(tmp_path):
    from kairu.brain.gateway import ANSWERED, LOCATION, Gateway
    gateway = Gateway(str(tmp_path), {"research": True, "providers": ["groq"], "public_to_cloud": True})
    assert gateway.ask("where am I", "pc").status == LOCATION
    phone = gateway.ask("where am I", "dev-" + "0" * 16)
    assert phone.status == ANSWERED and "only at your PC" in phone.text


# --- "find cheap biryani": the web, for the lowest prices ---------------------------------------------------------------

@pytest.mark.parametrize("said, words", [
    ("I want to eat biryani just find some websites with low cost", "cheapest biryani price online"),
    ("find cheap biryani in Hyderabad", "cheapest biryani in hyderabad price online"),
    ("I want to buy cheap earphones", "cheapest earphones price online"),
    ("budget friendly hotels in goa", "cheapest hotels in goa price online")])
def test_a_cheap_thing_question_searches_for_the_lowest_prices(said, words):
    route = router.route(said)
    assert route.kind == "cloud" and route.research and route.query == words


@pytest.mark.parametrize("said", ["what is a budget", "what does cheap mean", "is it cheap", "what is the cheapest planet"])
def test_questions_about_the_word_are_not_shopping(said):
    assert router.cheap_words(router.plain(said)) == ""


def test_the_web_answer_names_the_cheapest_options_first_and_never_makes_up_a_price():
    from kairu.brain import gateway
    assert "cheapest first" in gateway.CHEAPEST and "Never make up a price" in gateway.CHEAPEST
