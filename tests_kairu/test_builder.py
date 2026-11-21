"""The Builder (BUILDER.md, ADR-050 proposed): Builder powers, Forge and Five Paths, without the Guardian program.

What each part may never do is tested here: a build that reaches the network or past its folder, Python that imports what it
must not, a recipe with a skill it may not use or a slot it doesn't have, a judge that scores what isn't there. The program
tests (test_builder_program.py) take the same orders through the real Guardian.
"""

import json
import os

import pytest

from kairu import config as kairu_config
from kairu import executors, policy
from kairu.brain import privacy
from kairu.brain.gateway import Gateway
from kairu.build import conduct, forge, make, paths
from kairu.build.store import BuilderStore, digest
from kairu.policy import Tier
from kairu.tasks import pc
from kairu.tasks import plan as planner
from kairu.tasks.store import TaskStore
from tests_kairu.helpers import POLICY

RULES = policy.load(POLICY).rules
JOB = "a" * 16
SUBJECTS = ("physics", "maths", "chemistry", "biology", "history")


def site(**changes):
    files = [{"name": "index.html", "text": "<!doctype html><html><head><link rel='stylesheet' href='style.css'></head><body>"
                                            "<h1>Fresh Bakes</h1><a href='https://maps.google.com'>Find us</a>"
                                            "<script src='script.js'></script></body></html>"},
             {"name": "style.css", "text": "body { font-family: system-ui; color: #3b2a1a; }"},
             {"name": "script.js", "text": "document.querySelector('h1').onclick = () => alert('Fresh bread every morning');"}]
    return {"folder": "fresh-bakes", "files": files, **changes}


def program(**changes):
    files = [{"name": "convert.py", "text": "def c_to_f(c):\n    return c * 9 / 5 + 32\n"},
             {"name": "test_convert.py", "text": "import unittest\nfrom convert import c_to_f\n\n\nclass Convert(unittest.TestCase):\n"
                                                 "    def test_boiling(self):\n        self.assertEqual(c_to_f(100), 212)\n"}]
    return {"folder": "temperature-converter", "files": files, **changes}


def recipe(**changes):
    return {"name": "make a study folder", "says": ["make a study folder for {subject}", "set up a study folder for {subject}"],
            "slots": {"subject": "a school subject"},
            "steps": [{"action": "files.write", "details": {"name": "{subject}-plan.md", "text": "Study plan for {subject}"}},
                      {"action": "files.move", "details": {"name": "{subject}-plan.md", "to": "{subject}"}},
                      {"action": "apps.open", "details": {"name": "Notepad"}},
                      {"action": "web.search", "details": {"query": "{subject} revision notes"}}],
            "examples": [{"subject": subject} for subject in SUBJECTS], **changes}


# --- the policy --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, tier", [
    ("build.draft", Tier.LOW), ("build.write", Tier.MEDIUM), ("build.test", Tier.HIGH), ("forge.draft", Tier.LOW),
    ("forge.test", Tier.LOW), ("forge.save", Tier.HIGH), ("forge.forget", Tier.MEDIUM), ("paths.draft", Tier.LOW)])
def test_each_builder_action_has_its_tier_and_keeps_only_a_hash_of_your_words(name, tier):
    assert RULES[name].tier is tier and RULES[name].private and not RULES[name].read_only
    assert name in executors.EXECUTORS


def test_the_work_folder_data_folder_and_brain_come_from_guardian_never_from_a_request():
    for name in ("build.draft", "build.write", "build.test", "forge.draft", "forge.test", "forge.save", "forge.forget",
                 "paths.draft"):
        executor = executors.EXECUTORS[name]
        assert "data_dir" in executor.supplied
        assert not {"data_dir", "work_folder", "brain"} & set(executor.arguments)
    assert executors.EXECUTORS["build.write"].supplied == ("data_dir", "work_folder")


def test_the_builder_adds_no_critical_action_and_never_a_command_to_a_recipe():
    assert all(rule.tier is not Tier.CRITICAL for name, rule in RULES.items() if name.startswith(("build.", "forge.", "paths.")))
    assert "terminal.run" not in forge.FORGEABLE and set(forge.FORGEABLE) <= set(planner.PLANNABLE)


# --- Builder powers: what a build may be ---------------------------------------------------------------------------

def test_a_good_site_is_read_with_a_plain_folder_name():
    folder, files = make.parse(json.dumps(site(folder="Fresh Bakes!")), "site")
    assert folder == "fresh-bakes" and [item["name"] for item in files] == ["index.html", "style.css", "script.js"]


def test_a_fenced_answer_or_one_with_words_around_the_json_is_still_read():
    text = "Here it is:\n```json\n" + json.dumps(site()) + "\n```"
    assert make.parse(text, "site")[0] == "fresh-bakes"
    assert make.parse("Sure! " + json.dumps(site()) + " Enjoy.", "site")[0] == "fresh-bakes"


@pytest.mark.parametrize("text", [
    "<script src='https://cdn.example.com/x.js'></script>", "<script src=//cdn.example.com/x.js></script>",
    "<link rel='stylesheet' href='https://fonts.googleapis.com/css'>", "<img src='http://example.com/a.png'>",
    "@import url(x.css);", "body { background: url('https://example.com/a.png') }", "fetch('/api')",
    "new XMLHttpRequest()", "new WebSocket('wss://x')", "navigator.sendBeacon('x')", "eval('1')", "new Function('x')",
    "<iframe src='x.html'></iframe>", "<form action='https://evil.example'>", "document.cookie", "location.href = 'x'",
    "window.location = 'https://x'", "<meta http-equiv='refresh' content='0;url=x'>", "import('https://x.js')",
    "<base href='https://x/'>", "<object data='x'></object>"])
def test_a_page_that_would_reach_the_network_by_itself_is_no_build(text):
    files = site()["files"]
    files[2] = {"name": "script.js", "text": text}
    with pytest.raises(make.NoBuild, match="network"):
        make.parse(json.dumps(site(files=files)), "site")


@pytest.mark.parametrize("name", ["../index.html", "sub/index.html", "C:index.html", "run.bat", "app.exe", "x.ps1", "a.lnk",
                                  "con.html", ".hidden.html", "index.py"])
def test_a_file_outside_the_folder_or_of_a_kind_the_build_may_not_have_is_no_build(name):
    files = site()["files"] + [{"name": name, "text": "x"}]
    with pytest.raises(make.NoBuild):
        make.parse(json.dumps(site(files=files)), "site")


def test_a_build_needs_its_page_keeps_its_limits_and_never_holds_a_secret():
    no_page = site(files=[{"name": "about.html", "text": "<p>hi</p>"}])
    for bad, why in ((no_page, "index.html"),
                     (site(files=[{"name": f"p{n}.html", "text": "x"} for n in range(7)]), "1 to 6 files"),
                     (site(files=site()["files"] + [{"name": "index.html", "text": "again"}]), "same name"),
                     (site(files=[{"name": "index.html", "text": "x" * 30_001}]), "too long"),
                     (site(files=[{"name": "index.html", "text": "key = sk-or-" + "a" * 40}]), "API key or token"),
                     ({"folder": "x", "files": "index.html"}, "wasn't a build"), ({"files": [], "extra": 1}, "wasn't a build")):
        with pytest.raises(make.NoBuild, match=why):
            make.parse(json.dumps(bad), "site")
    with pytest.raises(make.NoBuild, match="wasn't a build"):
        make.parse("I can't help with that.", "site")


def test_a_python_build_uses_only_safe_standard_modules_and_its_own_files():
    assert make.parse(json.dumps(program()), "tests")[0] == "temperature-converter"
    for text, why in (("import os\nos.system('x')", "imports os"), ("import subprocess", "imports subprocess"),
                      ("from socket import socket", "imports socket"), ("import urllib.request", "imports urllib"),
                      ("open('x', 'w').write('y')", "calls open"), ("eval('1')", "calls eval"), ("exec('x')", "calls exec"),
                      ("__import__('os')", "calls __import__"), ("getattr(int, 'x')", "calls getattr"),
                      ("x = ().__class__.__bases__", r"uses \.__"), ("print(__builtins__)", "reaches __builtins__"),
                      ("def f(:\n    pass", "isn't valid Python")):
        files = program()["files"] + [{"name": "extra.py", "text": text}]
        with pytest.raises(make.NoBuild, match=why):
            make.parse(json.dumps(program(files=files)), "tests")


def test_a_python_build_needs_its_program_and_its_tests():
    only_tests = program(files=[{"name": "test_convert.py", "text": "import unittest\n"}])
    with pytest.raises(make.NoBuild, match="program and a test"):
        make.parse(json.dumps(only_tests), "tests")


# --- build.write and build.test (their code, without Guardian) -----------------------------------------------------

@pytest.fixture
def data(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


@pytest.fixture
def work(tmp_path):
    folder = tmp_path / "Kairu-files"
    folder.mkdir()
    return folder


def reply(data, job=JOB):
    return TaskStore(data).take_reply(job)


def drafted(data, kind, built):
    folder, files = make.parse(json.dumps(built), kind)
    return BuilderStore(data).add_draft("b" * 16, kind, folder, files)


def test_build_write_makes_exactly_the_draft_in_a_new_folder_and_only_once(data, work):
    number, sha = drafted(data, "site", site())
    make.write(str(data), JOB, float(number), sha, str(work))
    assert reply(data).text == "Made fresh-bakes in your work folder: index.html, style.css, script.js."
    assert (work / "fresh-bakes" / "style.css").read_text() == site()["files"][1]["text"]
    make.write(str(data), JOB, float(number), sha, str(work))
    assert not reply(data).ok


def test_build_write_never_writes_a_draft_you_were_not_shown_and_never_over_a_folder(data, work):
    number, sha = drafted(data, "site", site())
    make.write(str(data), JOB, float(number), "0" * 64, str(work))
    assert reply(data).text == "Not made: that build isn't the one you were shown." and not (work / "fresh-bakes").exists()
    (work / "fresh-bakes").mkdir()
    (work / "fresh-bakes" / "index.html").write_text("mine")
    make.write(str(data), JOB, float(number), sha, str(work))
    assert "overwrites nothing" in reply(data).text and (work / "fresh-bakes" / "index.html").read_text() == "mine"


def test_a_draft_changed_in_the_store_is_never_made(data, work):
    number, sha = drafted(data, "site", site())
    with BuilderStore(data).connect() as db:
        changed = site()["files"]
        changed[2]["text"] = "fetch('https://evil.example')"
        db.execute("UPDATE drafts SET files = ? WHERE id = ?", (json.dumps(changed), number))
    make.write(str(data), JOB, float(number), sha, str(work))
    assert "isn't the one you were shown" in reply(data).text and not (work / "fresh-bakes").exists()


def test_build_test_runs_only_the_tests_the_builder_made_unchanged(data, work, monkeypatch):
    monkeypatch.delenv(pc.TEST_PC, raising=False)
    number, sha = drafted(data, "tests", program())
    make.write(str(data), JOB, float(number), sha, str(work))
    assert reply(data).ok
    make.test(str(data), JOB, "temperature-converter", str(work))
    assert reply(data).text == "The tests in temperature-converter passed (1 ran)."
    (work / "temperature-converter" / "sneaky.py").write_text("print('hi')")
    make.test(str(data), JOB, "temperature-converter", str(work))
    assert "wasn't made by the Builder" in reply(data).text
    (work / "temperature-converter" / "sneaky.py").unlink()
    with open(work / "temperature-converter" / "convert.py", "a") as file:
        file.write("import os\n")
    make.test(str(data), JOB, "temperature-converter", str(work))
    assert "changed since the Builder made it" in reply(data).text
    make.test(str(data), JOB, "fresh-bakes", str(work))
    assert "isn't a Python program the Builder made" in reply(data).text


def test_failing_tests_are_said_as_failed(data, work, monkeypatch):
    monkeypatch.delenv(pc.TEST_PC, raising=False)
    files = program()["files"]
    files[1] = {"name": "test_convert.py", "text": files[1]["text"].replace("212", "999")}
    number, sha = drafted(data, "tests", program(files=files))
    make.write(str(data), JOB, float(number), sha, str(work))
    reply(data)
    assert make.test(str(data), JOB, "temperature-converter", str(work)) is not None
    said = reply(data)
    assert not said.ok and said.text.startswith("The tests in temperature-converter failed.")


# --- the Builder asks Gemini first ----------------------------------------------------------------------------------

def test_the_builder_asks_build_providers_and_otherwise_the_usual_providers(tmp_path):
    assert Gateway(tmp_path, {"providers": ["groq"], "build_providers": ["gemini", "groq"]}).build_order == ["gemini", "groq"]
    assert Gateway(tmp_path, {"providers": ["groq", "cloudflare"]}).build_order == ["groq", "cloudflare"]
    shipped = kairu_config.load(kairu_config.ROOT / "config.yaml")
    assert shipped.brain_settings()["build_providers"][0] == "gemini"
    path = tmp_path / "c.yaml"
    path.write_text("brain:\n  build_providers: [gemini, nobody]\n")
    with pytest.raises(kairu_config.ConfigError, match="build_providers"):
        kairu_config.load(path)


def test_a_personal_or_secret_brief_never_goes_to_the_builder(tmp_path):
    gateway = Gateway(tmp_path, {"public_to_cloud": True, "providers": ["groq"]})
    assert gateway.build("build a website for my bank, my password is hunter2", "pc", "x").status == "refused"
    assert gateway.build("build a website with my phone number 9876543210", "pc", "x").status == "not_sent"
    assert Gateway(tmp_path, {"public_to_cloud": False}).build("build a website for a bakery", "pc", "x").status == "not_sent"


# --- Forge -------------------------------------------------------------------------------------------------------

def test_a_good_recipe_is_read_and_answers_its_orders_with_your_words():
    kept = forge.read(recipe())
    assert forge.matching([kept], "make a study folder for computer science") == (kept, {"subject": "computer science"})
    assert forge.matching([kept], "Set up a study folder for maths") == (kept, {"subject": "maths"})
    assert forge.matching([kept], "make a study folder") is None
    assert forge.fill(kept["steps"], {"subject": "art"})[1] == ("files.move", {"name": "art-plan.md", "to": "art"})


@pytest.mark.parametrize("change, why", [
    ({"steps": [{"action": "terminal.run", "details": {"command": "git status", "folder": ""}}]}, "skills a recipe may use"),
    ({"steps": [{"action": "money.spend", "details": {}}]}, "skills a recipe may use"),
    ({"steps": [{"action": "files.delete", "details": {"name": "{other}"}}]}, "slot the recipe doesn't have"),
    ({"steps": [{"action": "files.write", "details": {"name": "a.txt"}}] * 9}, "1 to 8 steps"),
    ({"steps": [{"action": "web.open", "details": {"url": "x", "extra": "y"}}]}, "wrong details"),
    ({"examples": [{"subject": "physics"}] * 4}, "exactly 5 examples"),
    ({"examples": [{"subject": "x" * 61}] * 5}, "1 to 60 characters"),
    ({"examples": [{"subject": "{evil}"}] * 5}, "no braces"),
    ({"says": ["study {subject} {subject}"]}, "every slot once"),
    ({"says": ["make a study folder"]}, "every slot once"),
    ({"says": ["open {subject}"]}, "already knows"),
    ({"slots": {"a": "x", "b": "y", "c": "z", "d": "w"}}, "at most 3 slots"),
    ({"name": "x"}, "3 to 40 plain letters"),
    ({"extra": True}, "exactly a name"),
])
def test_a_recipe_that_breaks_a_rule_is_no_recipe(change, why):
    with pytest.raises(forge.NoRecipe, match=why):
        forge.read(recipe(**change))


def test_a_recipe_never_shadows_a_built_in_skill_and_a_value_never_carries_a_slot():
    kept = forge.read(recipe())
    assert forge.matching([kept], "make a study folder for " + "x" * 61) is None


def test_five_dry_runs_on_a_stand_in_laptop_touch_nothing_here(data, tmp_path, monkeypatch):
    monkeypatch.delenv(pc.TEST_PC, raising=False)
    store = BuilderStore(data)
    number, sha = store.add_recipe("c" * 16, forge.read(recipe()))
    forge.test(str(data), JOB, float(number), sha)
    assert reply(data).text == "Dry runs on a stand-in laptop: 5 of 5 passed."
    assert store.recipe(number)["passed"] == 5 and os.environ.get(pc.TEST_PC) is None
    assert not (tmp_path / "Kairu-files").exists() and not any(data.glob("*.txt"))


def test_a_dry_run_that_fails_says_where_and_the_skill_cannot_be_kept(data, monkeypatch):
    monkeypatch.delenv(pc.TEST_PC, raising=False)
    store = BuilderStore(data)
    broken = recipe(steps=[{"action": "files.open", "details": {"name": "{subject}-missing.md"}}])
    number, sha = store.add_recipe("c" * 16, forge.read(broken))
    forge.test(str(data), JOB, float(number), sha)
    said = reply(data)
    assert not said.ok and said.text.startswith("Dry runs on a stand-in laptop: 0 of 5 passed.") and "step 1" in said.text
    forge.save(str(data), JOB, float(number), sha)
    assert "only after all 5 dry runs pass" in reply(data).text and store.skills() == []


def test_forge_save_keeps_only_the_recipe_you_were_shown_and_forget_removes_it(data, monkeypatch):
    monkeypatch.delenv(pc.TEST_PC, raising=False)
    store = BuilderStore(data)
    number, sha = store.add_recipe("c" * 16, forge.read(recipe()))
    forge.test(str(data), JOB, float(number), sha)
    reply(data)
    forge.save(str(data), JOB, float(number), "0" * 64)
    assert "isn't the one you were shown" in reply(data).text
    forge.save(str(data), JOB, float(number), sha)
    assert reply(data).text == 'Learned "make a study folder". Say, for example: make a study folder for physics.'
    assert [kept["name"] for kept in store.skills()] == ["make a study folder"]
    forge.forget(str(data), JOB, "Make a Study Folder")
    assert reply(data).ok and store.skills() == []


def test_a_kept_skill_changed_by_hand_is_never_used(data):
    store = BuilderStore(data)
    store.keep_skill(forge.read(recipe()))
    with store.connect() as db:
        db.execute("UPDATE skills SET recipe = replace(recipe, 'files.write', 'files.delete')")
    assert store.skills() == []


# --- Five Paths -----------------------------------------------------------------------------------------------------

def test_the_judge_must_score_every_path_that_came_back_once_from_0_to_10():
    good = json.dumps({"done": "every pdf is in a folder", "scores": [{"path": 1, "score": 7, "why": "Quick."},
                                                                          {"path": 3, "score": 9.4, "why": "Looks first."}]})
    assert paths.read_judgement(good, [1, 3]) == ("every pdf is in a folder", {1: (7, "Quick."), 3: (9, "Looks first.")})
    for bad in ({"done": "", "scores": [{"path": 1, "score": 7, "why": "x"}]},
                {"done": "", "scores": [{"path": 1, "score": 11, "why": "x"}, {"path": 3, "score": 1, "why": "x"}]},
                {"done": "", "scores": [{"path": 2, "score": 5, "why": "x"}, {"path": 3, "score": 1, "why": "x"}]},
                {"done": "", "scores": [{"path": 1, "score": True, "why": "x"}, {"path": 3, "score": 1, "why": "x"}]},
                {"done": "", "scores": [{"path": 1, "score": 5, "why": "x" * 161}, {"path": 3, "score": 1, "why": "x"}]}):
        with pytest.raises(paths.NoJudgement):
            paths.read_judgement(json.dumps(bad), [1, 3])


def test_five_styles_and_rules_when_the_judge_says_nothing():
    assert [style for style, _ in paths.STYLES] == ["Fast", "Careful", "Simple", "Creative", "Thorough"]
    scored = paths.by_rules([{"steps": [["a", {}]] * 2}, {"steps": None}, {"steps": [["a", {}]] * 6}])
    assert scored[1][0] > scored[3][0] and 2 not in scored


# --- the orders ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("order, kind", [
    ("build a website for Fresh Bakes, a bakery in Hyderabad", "site"), ("make me a landing page for my startup Sung", "site"),
    ("make a web app: a tip calculator", "app"), ("create a simple game where you catch falling stars", "app"),
    ("make slides about Kairu for the Buildathon", "slides"), ("make a presentation on solar energy", "slides"),
    ("build a python app that converts temperatures", "tests"), ("write a python program that counts words", "tests")])
def test_the_builders_orders_and_their_kinds(order, kind):
    found = conduct.BUILD.fullmatch(order)
    assert found and conduct.kind_of(found["what"]) == kind


@pytest.mark.parametrize("order", ["make a file called notes.txt", "open the app store", "create a folder called x",
                                   "write a shopping list", "build", "make a plan"])
def test_other_orders_are_not_builds(order):
    assert conduct.BUILD.fullmatch(order) is None


def test_forge_and_five_paths_orders():
    assert conduct.LEARN_TO.fullmatch("learn to make a study folder for physics")["task"] == "make a study folder for physics"
    assert conduct.FORGE.fullmatch("forge a skill for tidying my downloads")["task"] == "tidying my downloads"
    assert conduct.FORGE_IT.fullmatch("forge it") and conduct.FORGE_IT.fullmatch("learn to do that")
    found = conduct.PATHS.fullmatch("try five ways to tidy my downloads, done when every pdf is in a folder")
    assert (found["task"], found["done"]) == ("tidy my downloads", "every pdf is in a folder")
    assert conduct.PICK.fullmatch("run path two")["number"] == "two" and conduct.PICK.fullmatch("run the best path")["best"]
    assert conduct.FORGET_SKILL.fullmatch('forget the skill "make a study folder"')["name"] == "make a study folder"


def test_store_digest_is_stable():
    assert digest({"b": 1, "a": [1, 2]}) == digest({"a": [1, 2], "b": 1})


# --- the answer, file by file (as the AI is asked), and JSON with real line breaks ----------------------------------

def as_blocks(built) -> str:
    return f"FOLDER: {built['folder']}\n" + "".join(f"=== FILE: {item['name']} ===\n{item['text']}\n=== END FILE ===\n"
                                                    for item in built["files"])


def test_the_file_by_file_answer_is_read_with_every_line_kept():
    page = '<!doctype html>\n<html>\n  <body>\n    <h1 class="title">Fresh "Bakes"</h1>\n  </body>\n</html>'
    built = site(files=[{"name": "index.html", "text": page}, site()["files"][1]])
    folder, files = make.parse("Here is your site:\n" + as_blocks(built) + "Enjoy!", "site")
    assert folder == "fresh-bakes" and files[0] == {"name": "index.html", "text": page + "\n"}


def test_a_fence_around_a_file_is_taken_off_and_a_cut_off_file_is_no_build():
    fenced = "FOLDER: x-site\n=== FILE: index.html ===\n```html\n<p>hi</p>\n```\n=== END FILE ===\n"
    assert make.parse(fenced, "site")[1] == [{"name": "index.html", "text": "<p>hi</p>\n"}]
    with pytest.raises(make.NoBuild, match="cut off"):
        make.parse("FOLDER: x-site\n=== FILE: index.html ===\n<p>hi", "site")
    with pytest.raises(make.NoBuild, match="before the next file"):
        make.parse("=== FILE: index.html ===\n<p>\n=== FILE: style.css ===\nb{}\n=== END FILE ===", "site")


def test_the_same_rules_hold_for_the_file_by_file_answer():
    bad = site(files=site()["files"][:2] + [{"name": "script.js", "text": "fetch('https://x')"}])
    with pytest.raises(make.NoBuild, match="network"):
        make.parse(as_blocks(bad), "site")
    with pytest.raises(make.NoBuild):
        make.parse(as_blocks(site(files=[{"name": "../evil.html", "text": "x"}])), "site")


def test_json_with_real_line_breaks_in_a_file_is_still_read():
    raw = '{"folder": "fresh-bakes", "files": [{"name": "index.html", "text": "<html>\n<body>hi</body>\n</html>"}]}'
    assert make.parse(raw, "site")[1][0]["text"] == "<html>\n<body>hi</body>\n</html>"
    assert "FILE" in make.instructions("site") and "no JSON" in make.instructions("site")


def test_a_brief_about_kairu_brings_the_true_facts_and_no_build_is_told_to_invent():
    about = make.instructions("slides", "make slides about Kairu for the Buildathon")
    assert "voice-first AI teammate" in about and "Guardian" in about and "short points per slide" in about
    assert "voice-first" not in make.instructions("site", "build a website for Fresh Bakes")
    for kind in make.KINDS:
        told = make.instructions(kind, "make it about Kairu")
        assert "Never invent names of people, dates" in told
        assert privacy.secrets_in(told) == []  # the backstop would stop the whole build


def test_a_page_about_guardians_pin_is_code_not_a_secret_but_a_real_secret_still_stops_the_build():
    page = ("<style>body { color: '#1e1e2f'; } .accent { color: '#4a90e2'; }</style>"
            "<ul><li>Low just runs</li><li>High: yes + PIN on that laptop</li><li>the PIN: on the Clone</li></ul>")
    assert make.parse(json.dumps(site(files=[{"name": "index.html", "text": page}])), "site")[0] == "fresh-bakes"
    for secret, why in (("const key = 'gsk_" + "a" * 30 + "';", "API key"), ("password = 'Tiger@123'", "written into the code"),
                        ("const pin = '4821';", "written into the code"), ("card: 4111 1111 1111 1111", "card number")):
        with pytest.raises(make.NoBuild, match=why):
            make.parse(json.dumps(site(files=[{"name": "index.html", "text": f"<p>x</p><script>{secret}</script>"}])), "site")


def test_a_last_file_without_its_end_line_is_whole_only_when_the_provider_finished_writing():
    answer = ("FOLDER: temperature-converter\n=== FILE: convert.py ===\n" + program()["files"][0]["text"] + "=== END FILE ===\n"
              "=== FILE: test_convert.py ===\n" + program()["files"][1]["text"] + "=== END FILE ===\n"
              "=== FILE: README.md ===\n# Temperature converter\nRun the tests with unittest.\n")
    with pytest.raises(make.NoBuild, match="cut off"):
        make.parse(answer, "tests")
    folder, files = make.parse(answer, "tests", whole=True)
    assert files[-1] == {"name": "README.md", "text": "# Temperature converter\nRun the tests with unittest.\n"}
    with pytest.raises(make.NoBuild, match="cut off"):  # a page still needs its </html>
        make.parse("FOLDER: x-site\n=== FILE: index.html ===\n<html><body><h1>Hi", "site", whole=True)
    assert make.parse("=== FILE: index.html ===\n<html><body>Hi</body></html>", "site", whole=True)[1][0]["name"] == "index.html"


def test_the_gateway_marks_a_builder_answer_the_provider_cut_off(tmp_path):
    from kairu.brain import keys
    from kairu.brain.gateway import CUT_OFF

    def answers(finish):
        def transport(url, headers, body, timeout):
            return 200, {}, json.dumps({"choices": [{"message": {"content": "=== FILE: index.html ===\n<p>"},
                                                     "finish_reason": finish}], "usage": {}}).encode()
        return transport

    keys.save(tmp_path, "groq", "gsk_" + "k" * 40)
    settings = {"public_to_cloud": True, "providers": ["groq"]}
    cut = Gateway(tmp_path, settings, transport=answers("length")).build("build a website for a bakery", "pc", "make it")
    assert CUT_OFF in cut.note
    done = Gateway(tmp_path, settings, transport=answers("stop")).build("build a website for a bakery", "pc", "make it")
    assert CUT_OFF not in done.note and done.status == "answered"


def test_harmless_modules_small_programs_use_are_fine_and_the_dangerous_ones_still_are_not():
    head = "from __future__ import annotations\nimport argparse\nfrom contextlib import suppress\nimport cmath, numbers, pprint\n"
    files = program()["files"]
    files[0] = {"name": "convert.py", "text": head + files[0]["text"]}
    assert make.parse(json.dumps(program(files=files)), "tests")[0] == "temperature-converter"
    for module in ("os", "sys", "pathlib", "shutil", "logging", "importlib", "pickle"):
        files[0] = {"name": "convert.py", "text": f"import {module}\n" + program()["files"][0]["text"]}
        with pytest.raises(make.NoBuild, match=f"imports {module}"):
            make.parse(json.dumps(program(files=files)), "tests")


def test_a_slot_no_step_uses_is_no_recipe():
    unused = recipe(slots={"subject": "a school subject", "folder": "a folder"},
                    says=["make a {folder} folder for {subject}"], examples=[{"subject": s, "folder": s} for s in SUBJECTS],
                    steps=[{"action": "files.write", "details": {"name": "{folder}.txt", "text": "notes"}}])
    with pytest.raises(forge.NoRecipe, match="the slot subject isn't used by any step"):
        forge.read(unused)
    assert "as few slots as the order needs" in forge.instructions()


def test_forge_is_told_how_to_make_and_show_a_folder_without_a_placeholder():
    told = forge.instructions()
    assert "files.open of the folder's name" in told and "Never make an empty placeholder file" in told
    folder = forge.read(recipe(steps=[
        {"action": "files.write", "details": {"name": "{subject}-notes.txt", "text": "Study notes for {subject}"}},
        {"action": "files.move", "details": {"name": "{subject}-notes.txt", "to": "{subject}"}},
        {"action": "files.open", "details": {"name": "{subject}"}}]))
    assert forge.fill(folder["steps"], {"subject": "art"})[2] == ("files.open", {"name": "art"})


# --- the Builder's Gemini: Google's own address, several models, one wait when busy --------------------------------

def gemini_answer(text="=== FILE: index.html ===\n<html><body>Hi</body></html>\n=== END FILE ===", finish="STOP"):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": text}]},
                                       "finishReason": finish}],
                       "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20}}).encode()


def test_the_builder_asks_gemini_at_its_own_address_and_moves_on_from_a_busy_or_missing_model(tmp_path):
    from kairu.brain import keys
    from kairu.brain.providers import gemini_build
    asked = []

    def transport(url, headers, body, timeout):
        asked.append(url.rsplit("/", 1)[1])
        assert url.startswith("https://generativelanguage.googleapis.com/v1beta/models/") and "key" not in url
        assert headers["x-goog-api-key"] == "AIza" + "k" * 35
        sent = json.loads(body)
        assert sent["systemInstruction"]["parts"][0]["text"] == "make it" and sent["contents"][0]["role"] == "user"
        if "flash-latest" in url and "lite" not in url:
            return 503, {}, b'{"error": {"message": "The model is overloaded."}}'
        if "lite-latest" in url:
            return 404, {}, b'{"error": {"message": "not found"}}'
        return 200, {}, gemini_answer()

    reply = gemini_build("AIza" + "k" * 35, [{"role": "system", "content": "make it"}, {"role": "user", "content": "a cafe"}],
                         transport=transport, sleep=lambda seconds: None)
    assert reply.text.startswith("=== FILE: index.html ===") and "thinking" not in reply.text and reply.finish == "stop"
    assert asked == ["gemini-flash-latest:generateContent", "gemini-flash-latest:generateContent",  # busy: once more
                     "gemini-flash-lite-latest:generateContent", "gemini-2.5-flash:generateContent"]
    keys.save(tmp_path, "gemini", "AIza" + "k" * 35)
    result = Gateway(tmp_path, {"public_to_cloud": True, "providers": ["groq"], "build_providers": ["gemini"]},
                     transport=transport, sleep=lambda seconds: None).build("build a website for a cafe", "pc", "make it")
    assert result.status == "answered" and result.provider == "gemini"


def test_gemini_cut_off_and_all_busy_are_said_plainly():
    from kairu.brain.providers import Unreachable, gemini_build
    cut = gemini_build("AIza" + "k" * 35, [{"role": "user", "content": "x"}],
                       transport=lambda *a: (200, {}, gemini_answer(finish="MAX_TOKENS")), sleep=lambda s: None)
    assert cut.finish == "length"
    with pytest.raises(Unreachable, match="503"):
        gemini_build("AIza" + "k" * 35, [{"role": "user", "content": "x"}],
                     transport=lambda *a: (503, {}, b"{}"), sleep=lambda s: None)
    with pytest.raises(Exception, match="backstop"):
        gemini_build("AIza" + "k" * 35, [{"role": "user", "content": "my api key is sk-or-" + "a" * 40}],
                     transport=lambda *a: (200, {}, gemini_answer()), sleep=lambda s: None)
