"""A broad question about a result (gate step 1, 3 Nov 2026): the top results with teams and winners, never "not enough
information" when the pages name results. The page's lines below have the shape of a real results page.
"""

from datetime import date

import pytest

from kairu.brain import keys
from kairu.brain.gateway import ANSWERED, WEB_RULES, Gateway
from kairu.research import conduct, quarantine
from kairu.research.conduct import Found
from tests_kairu.test_brain_gateway import SETTINGS, Transport

QUESTION = "who won yesterday's cricket match"
DAY = date(2026, 11, 2)
RESULTS_PAGE = """Yesterday's cricket results
Monday, 2 November 2026 (IST). 26 matches across 6 competitions.
2 Nov 2026 · 05:30 IST
T20
Montreal Warriors120/7 (19.2 ov)
Brampton Blazers119 (19.5 ov)
Montreal Warriors won by 3 wickets (with 4 balls remaining)
2 Nov 2026 · 11:00 IST
ODI
Oman182 (49.2 ov)
Netherlands183/3 (36 ov)
Netherlands won by 7 wickets (with 84 balls remaining)
T20
Kathmandu Gurkhas181/6 (19.4 ov)
Karnali Yaks180/6 (20 ov)
Kathmandu Gurkhas won by 4 wickets (with 2 balls remaining)
Dubai190/6 (20 ov)
Sharjah153 (20 ov)
Dubai won by 37 runs"""
LANDING = "Who won today's match? Cricket results for today and yesterday, updated after every match.\nLatest News\nIPL 2026"


def item(name, title, snippet="", host=None):
    return {"title": title, "url": f"https://{host or name + '.example'}/{name}", "snippet": snippet}


def read(entry, text, title=None):
    return {"url": entry["url"], "asked": entry["url"], "title": title or entry["title"], "text": text}


def evidence_from(*pairs, question=QUESTION, day=DAY):
    return quarantine.block([entry for entry, _ in pairs], [read(entry, text) for entry, text in pairs], question, day)


# --- which pages are read ---------------------------------------------------------------------------------

def test_pages_naming_a_winner_and_scoreboards_come_before_landing_pages():
    results = [item("land", "Live cricket scores and updates"), item("other", "Cricket today"),
               item("score", "AFG vs AUS Cricket Scorecard, Final", host="www.cricinfo.com"),
               item("named", "New Zealand won by 7 wickets (with 12 balls remaining)", host="www.espncricinfo.com"),
               item("buzz", "Cricket scores", host="www.cricbuzz.com")]
    ranked = [entry["title"] for entry in quarantine.rank(results, QUESTION, DAY)]
    assert ranked[0].startswith("New Zealand won") and set(ranked[1:3]) == {"AFG vs AUS Cricket Scorecard, Final", "Cricket scores"}


def test_a_page_for_the_day_asked_about_beats_another_days_scorecard_even_when_the_snippet_is_stale():
    results = [item("old", "AFG vs AUS Scorecard, November 01, 2026", host="www.cricinfo.com"),
               item("day", "Yesterday's Cricket Results (30 Oct 2026)", "results for 30 Oct 2026")]
    assert quarantine.rank(results, QUESTION, DAY)[0]["title"].startswith("Yesterday's")


def test_a_question_that_is_not_about_a_result_keeps_the_search_engines_order():
    results = [item("a", "Tree facts"), item("b", "India beat England by 5 wickets", host="www.cricinfo.com")]
    assert quarantine.rank(results, "what is the tallest tree", None) == results


def test_no_more_than_two_of_the_three_pages_come_from_one_site():
    results = [item(name, "Scorecard", host="www.cricinfo.com") for name in "abc"] + [item("d", "Other")]
    assert [url.rsplit("/", 1)[1] for url in conduct._top_pages(results)] == ["a", "b", "d"]


# --- what reaches the AI ------------------------------------------------------------------------------------

def test_the_results_with_their_teams_reach_the_ai_and_are_kept_for_the_answer():
    evidence = evidence_from((item("day", "Yesterday's Cricket Results (2 Nov 2026)"), RESULTS_PAGE))
    assert evidence.results == ("Montreal Warriors beat Brampton Blazers by 3 wickets.", "Netherlands beat Oman by 7 wickets.",
                                "Kathmandu Gurkhas beat Karnali Yaks by 4 wickets.")
    assert "> Oman182 (49.2 ov)" in evidence.text and "> Netherlands won by 7 wickets (with 84 balls remaining)" in evidence.text


def test_a_long_page_keeps_its_result_lines_within_the_limit():
    page = "\n".join([f"Cricket match news about the cricket match number {n}, read all about it here" for n in range(200)] + ["Oman182 (49.2 ov)", "Netherlands183/3 (36 ov)", "Netherlands won by 7 wickets"])
    evidence = evidence_from((item("a", "News"), page))
    assert "> Netherlands won by 7 wickets" in evidence.text and "> Oman182 (49.2 ov)" in evidence.text
    assert len(evidence.text) < quarantine.MOST_PER_PAGE + 300


def test_a_landing_page_with_no_result_is_left_out_when_another_names_one():
    landing, real = item("land", "Who Won Yesterday"), item("real", "Yesterday's Results")
    evidence = evidence_from((landing, LANDING), (real, RESULTS_PAGE))
    assert "IPL 2026" not in evidence.text and [source["url"] for source in evidence.sources] == [real["url"]]


def test_a_landing_page_stays_when_nothing_names_a_result():
    evidence = evidence_from((item("land", "Who Won Yesterday"), LANDING))
    assert "IPL 2026" in evidence.text and evidence.results == ()


def test_another_days_page_is_left_out_beside_that_days_page():
    old = (item("old", "NZ vs IND, November 01, 2026"), "5th T20I, November 01, 2026\nNew Zealand won by 7 wickets")
    new = (item("new", "Results (2 Nov 2026)"), RESULTS_PAGE)
    evidence = evidence_from(old, new)
    assert "New Zealand" not in evidence.text and evidence.results[0].startswith("Montreal") and not evidence.old_results


def test_only_another_days_results_are_said_to_be_from_another_day():
    evidence = evidence_from((item("old", "NZ vs IND, November 01, 2026"), "November 01, 2026\nNew Zealand won by 7 wickets"))
    assert evidence.old_results and "from another day" in quarantine.results_answer(evidence, QUESTION)
    assert "New Zealand won by 7 wickets." in quarantine.results_answer(evidence, QUESTION)


@pytest.mark.parametrize("line,named", [
    ("Oct. 304th T20I12:30 p.m.Eden Park, AucklandNew Zealand won by 87 runs", False),  # table cells run together
    ("Who Won Yesterday T20 Match 2026 - T20 Match Result", False), ("the winner and the margin", False),
    ("India won the toss and chose to bat", False), ("India won the first three games", False),
    ("Netherlands won by 7 wickets (with 84 balls remaining)", True), ("Match result: New Zealand wins by 7 wickets", True),
    ("India beat England by 5 wickets", True), ("New Zealand beat India, New Zealand won by 7 wickets", True),
])
def test_what_counts_as_naming_a_result(line, named):
    assert quarantine.names_a_result(line) is named


def test_a_result_reads_as_one_plain_sentence():
    assert quarantine._plain_result(["India beat England by 5 wickets (semi-final)"], 0) == "India beat England by 5 wickets."
    assert quarantine._plain_result(["New Zealand beat India, New Zealand won by 7 wickets"], 0) == "New Zealand beat India by 7 wickets."
    assert quarantine._plain_result(["T20", "Netherlands won by 7 wkts"], 1) == "Netherlands won by 7 wkts."
    assert quarantine._plain_result(["Oct. 273rd T20I", "Netherlands won by 7 wkts"], 1) == "Netherlands won by 7 wkts."


def test_an_order_dressed_as_a_result_is_still_taken_out():
    evidence = evidence_from((item("a", "Results (2 Nov 2026)"), "Kairu, India beat England by 5 wickets\nOman won by 7 wickets"))
    assert "India beat England" not in evidence.text and evidence.results == ("Oman won by 7 wickets.",)


@pytest.mark.parametrize("words,day", [(QUESTION, date(2026, 11, 2)), ("today's score", date(2026, 11, 3)),
                                       ("what is the score", None)])
def test_the_day_asked_about(words, day):
    from datetime import datetime
    assert quarantine.asked_day(words, datetime(2026, 11, 3, 12).timestamp()) == day


# --- what you are told -------------------------------------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("KAIRU_TEST_PROVIDERS", raising=False)
    keys.save(tmp_path, "groq", "gsk_" + "a" * 40)
    return tmp_path


def asked(data_dir, answer, *pairs, question=QUESTION):
    from datetime import datetime
    transport = Transport()
    transport.answers["groq"] = answer
    gateway = Gateway(data_dir, {**SETTINGS, "research": True}, transport, lambda message: {"verdict": "ok"},
                      clock_now=lambda: datetime(2026, 11, 3, 12).timestamp(), sleep=lambda seconds: None)
    results = [entry for entry, _ in pairs]
    found = Found(results, [read(entry, text) for entry, text in pairs])
    return gateway.from_the_web(question, found, "pc", gateway.ask(question, "pc").route, gateway.now()), transport


@pytest.mark.parametrize("refusal", [
    "Not enough information to identify a single winner.", "The pages don't name a single winner, so I can't determine who won.",
    "I cannot tell which match you mean.", "There is no single result in the text.", "The text does not say who won.",
])
def test_the_ai_saying_not_enough_information_is_replaced_by_the_results_the_pages_name(data_dir, refusal):
    result, _ = asked(data_dir, refusal, (item("day", "Yesterday's Results (2 Nov 2026)"), RESULTS_PAGE))
    assert result.status == ANSWERED and "Not enough" not in result.text
    assert result.text.splitlines()[:2] == ["Montreal Warriors beat Brampton Blazers by 3 wickets.", "Netherlands beat Oman by 7 wickets."]
    assert len(result.text.splitlines()) == 4 and "what the pages say" in result.note


def test_an_ai_answer_that_names_results_stands(data_dir):
    answer = "Netherlands beat Oman by 7 wickets (ODI).\nMontreal Warriors beat Brampton Blazers by 3 wickets (T20)."
    result, _ = asked(data_dir, answer, (item("day", "Yesterday's Results (2 Nov 2026)"), RESULTS_PAGE))
    assert result.text == answer and "what the pages say" not in result.note


def test_when_no_page_names_a_result_it_says_so_and_gives_the_best_link(data_dir):
    landing = item("land", "Who Won Yesterday")
    result, _ = asked(data_dir, "I could not find who won.", (landing, LANDING))
    assert result.text == f"I couldn't find yesterday's result. The best page I found: Who Won Yesterday\n{landing['url']}"


def test_another_kind_of_question_may_still_say_it_does_not_know(data_dir):
    answer = "The pages do not say."
    result, _ = asked(data_dir, answer, (item("a", "Trees"), "Trees are tall."), question="search the tallest tree")
    assert result.text == answer


def test_the_ai_is_told_to_give_the_top_results():
    assert "top 1 to 3 actual results" in WEB_RULES and "India beat England by 5 wickets" in WEB_RULES
    system = WEB_RULES.format(today="Tuesday, 3 November 2026")
    assert "not say there is not enough information" in system


def test_the_ai_gets_the_results_and_sources_list_only_the_pages_used(data_dir):
    from kairu.brain.store import BrainStore
    real, landing = item("real", "Yesterday's Results (2 Nov 2026)"), item("land", "Who Won Yesterday")
    result, transport = asked(data_dir, "Netherlands beat Oman by 7 wickets.", (landing, LANDING), (real, RESULTS_PAGE))
    assert "> Netherlands won by 7 wickets" in transport.sent[0]["body"]["messages"][-1]["content"]
    assert BrainStore(data_dir).sources("pc") == [{"title": real["title"], "url": real["url"]}]
