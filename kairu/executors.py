"""The code Guardian can run: for each action that has any, its function and the details it takes.

Kairu asks Guardian to run an action by its name, with details. Guardian decides with the policy
as always, then runs the code listed here, in its own process, with exactly those details as its
arguments. Kairu never names the code: it cannot point an allowed action at other code, or hand
it an argument it was not shown. An action that is not listed here is never run.

`supplied` names arguments that Guardian itself fills in from its own config.yaml, such as the data
folder: a request can never set them (they are not in `arguments`, so a request naming one is
refused). `single` actions run at most once at a time.

demo.count's `heartbeat` argument is left out on purpose: it would let a request make Guardian
rewrite any file.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

NONE: Mapping[str, type] = MappingProxyType({})


@dataclass(frozen=True)
class Executor:
    target: str  # "module:function", run in its own process by kairu/worker.py
    arguments: Mapping[str, type]  # the details it takes: str, float (a number) or bool (true/false)
    supplied: tuple[str, ...] = ()  # filled in by Guardian from its own settings, never from a request
    single: bool = False  # at most one running at a time


def _takes(**arguments) -> Mapping[str, type]:
    return MappingProxyType(arguments)


EXECUTORS: Mapping[str, Executor] = MappingProxyType({
    "demo.count": Executor("kairu.demo:count", _takes(seconds=float, quiet=bool)),
    # Guardian protection (Phase J): the monitors, and the small actions on their notes
    "protect.watch": Executor("kairu.protect.watch:main", NONE, ("data_dir", "check_seconds", "gmail_seconds"), single=True),
    "protect.connect_email": Executor("kairu.protect.gmail:connect", _takes(client_file=str), ("data_dir",), single=True),
    "protect.disconnect_email": Executor("kairu.protect.gmail:disconnect", NONE, ("data_dir",), single=True),
    "protect.pause": Executor("kairu.protect.actions:pause", _takes(source=str), ("data_dir",)),
    "protect.resume": Executor("kairu.protect.actions:resume", _takes(source=str), ("data_dir",)),
    "alerts.dismiss": Executor("kairu.protect.actions:dismiss", _takes(alert=float, false_alarm=bool), ("data_dir",)),
    "protect.watch_pc": Executor("kairu.protect.actions:watch_pc", _takes(folder=str, devices=bool, security=bool),
                                 ("data_dir",)),
    "protect.add_folder": Executor("kairu.protect.actions:add_folder", _takes(folder=str), ("data_dir",)),
    "protect.remove_folder": Executor("kairu.protect.actions:remove_folder", _takes(folder=str), ("data_dir",)),
    "deadline.add": Executor("kairu.protect.actions:add_deadline", _takes(title=str, due=str, note=str), ("data_dir",)),
    "deadline.remove": Executor("kairu.protect.actions:remove_deadline", _takes(deadline=float), ("data_dir",)),
    # Kairu Link and Mission Mode (Phase C, LINK.md): the relay and the limits come from Guardian's config.yaml
    "link.receive": Executor("kairu.link.receive:main", NONE, ("data_dir", "relay"), single=True),
    "link.send": Executor("kairu.link.send:main", _takes(device=str, type=str, text=str), ("data_dir", "relay")),
    "device.pair": Executor("kairu.link.pairing:pair", NONE, ("data_dir", "relay"), single=True),
    "device.remove": Executor("kairu.link.devices:remove", _takes(device=str), ("data_dir",)),
    "device.approver": Executor("kairu.link.approver:enroll", _takes(device=str, key=str), ("data_dir",)),
    "task.order": Executor("kairu.tasks.remote:main", _takes(order=str, device=str), ("data_dir",), single=True),
    "mission_mode.on": Executor("kairu.mission:run", NONE,
                                ("data_dir", "max_hours", "cpu_percent", "cpu_minutes", "max_celsius"), single=True),
    # Kairu's brain and Mission Cards (Phase B, BRAIN.md): the brain's settings come from Guardian's config.yaml
    "brain.ask": Executor("kairu.brain.ask:main", _takes(question=str, ask=str, source=str), ("data_dir", "brain")),
    "brain.send_private": Executor("kairu.brain.ask:private",
                                   _takes(question=str, provider=str, ask=str, source=str, search=str),
                                   ("data_dir", "brain")),
    "provider.add": Executor("kairu.brain.actions:add", _takes(provider=str), ("data_dir",), single=True),
    "provider.remove": Executor("kairu.brain.actions:remove", _takes(provider=str), ("data_dir",)),
    "provider.pause": Executor("kairu.brain.actions:pause", _takes(provider=str, minutes=float), ("data_dir",)),
    "mission.create": Executor("kairu.missions.actions:create", _takes(file=str, practice=bool), ("data_dir",)),
    "mission.run": Executor("kairu.missions.run:main", NONE, ("data_dir",), single=True),
    "mission.stop": Executor("kairu.missions.actions:stop", _takes(card=float), ("data_dir",)),
    "mission.continue": Executor("kairu.missions.actions:resume", _takes(card=float, skip=bool), ("data_dir",)),
    "mission.remove": Executor("kairu.missions.actions:remove", _takes(card=float), ("data_dir",)),
    # Kairu's memory (stage M1, MEMORY.md): a question asks for these; they change only data/memory.db
    "memory.remember": Executor("kairu.memory.actions:remember", _takes(text=str, job=str, source=str), ("data_dir",)),
    "memory.forget": Executor("kairu.memory.actions:forget", _takes(what=str, job=str), ("data_dir",)),
    # Live web research (stage R1, RESEARCH.md): a question asks for these; each ends with a stop
    "research.web_search": Executor("kairu.research.search:main", _takes(query=str, job=str, recent=str), ("data_dir", "brain")),
    "research.weather": Executor("kairu.research.weather:main", _takes(place=str, job=str), ("data_dir",)),
    "research.location": Executor("kairu.research.where:main", _takes(job=str), ("data_dir",)),
    "research.web_read": Executor("kairu.research.pages:main", _takes(job=str, url1=str, url2=str, url3=str), ("data_dir",)),
    # The Kairu bar's skills (Sprint Day 1, BAR.md): work_folder comes from Guardian's config.yaml, never from a request
    "apps.list_open": Executor("kairu.tasks.actions:list_open", _takes(job=str), ("data_dir",)),
    "apps.open": Executor("kairu.tasks.actions:open_app", _takes(job=str, name=str), ("data_dir",)),
    "apps.close": Executor("kairu.tasks.actions:close_app", _takes(job=str, name=str), ("data_dir",)),
    "apps.arrange": Executor("kairu.tasks.actions:arrange_app", _takes(job=str, name=str, how=str), ("data_dir",)),
    "files.rename": Executor("kairu.tasks.actions:rename", _takes(job=str, old=str, new=str), ("data_dir", "work_folder")),
    "task.undo": Executor("kairu.tasks.actions:undo", _takes(job=str), ("data_dir", "work_folder")),
    "system.volume": Executor("kairu.tasks.actions:volume", _takes(job=str, setting=str), ("data_dir",)),
    "system.brightness": Executor("kairu.tasks.actions:brightness", _takes(job=str, setting=str), ("data_dir",)),
    "system.wifi": Executor("kairu.tasks.actions:wifi", _takes(job=str, setting=str), ("data_dir",)),
    "system.status": Executor("kairu.tasks.actions:status", _takes(job=str), ("data_dir",)),
    "system.lock": Executor("kairu.tasks.actions:lock", _takes(job=str), ("data_dir",)),
    "system.sleep": Executor("kairu.tasks.actions:sleep", _takes(job=str), ("data_dir",)),
    "system.restart": Executor("kairu.tasks.actions:restart", _takes(job=str), ("data_dir",)),
    "system.shutdown": Executor("kairu.tasks.actions:shutdown", _takes(job=str), ("data_dir",)),
    # Light voice (Sprint Day 2, VOICE.md): the model comes from Guardian's config.yaml, never from a request; the listener
    # opens the mic only for the session token of a mic you switched on in the bar
    "voice.listen": Executor("kairu.voice.listen:main", _takes(session=str), ("data_dir", "voice_model", "voice_engine", "voice_live_every",
                                                                       "voice_fast", "voice_only_mine", "voice_hearing",
                                                                       "voice_gemini_model", "voice_camera"),
                             single=True),
    # Kairu Live (VOICE.md "Kairu Live", ADR-052 proposed): voice.live and voice.live_folder come from Guardian's config.yaml, never
    # from a request; like voice.listen, it hears only for the session token of a mic you switched on in the bar
    "live.talk": Executor("kairu.live.listener:main", _takes(session=str), ("data_dir", "voice_live", "voice_live_folder",
                                                                          "voice_only_mine", "voice_camera"),
                           single=True),
    "voice.speak": Executor("kairu.voice.speak:main", _takes(text=str), ("data_dir", "voice_voice", "voice_style", "voice_tts", "voice_kokoro"),
                            single=True),
    # Files, Kairu's own browser and plans (Sprint Day 4, BAR.md): work_folder and the browser profile come from Guardian's
    # own config.yaml and data folder, never from a request
    "files.find": Executor("kairu.tasks.actions:find_files", _takes(job=str, what=str, when=str), ("data_dir", "work_folder")),
    "files.move": Executor("kairu.tasks.actions:move_files", _takes(job=str, name=str, to=str), ("data_dir", "work_folder")),
    "files.delete": Executor("kairu.tasks.actions:delete", _takes(job=str, name=str), ("data_dir", "work_folder")),
    # Make, open and show a file (W2, ADR-036): the work folder comes from Guardian's config.yaml, never from a request
    "files.write": Executor("kairu.tasks.actions:write_file", _takes(job=str, name=str, text=str), ("data_dir", "work_folder")),
    "files.open": Executor("kairu.tasks.actions:open_file", _takes(job=str, name=str), ("data_dir", "work_folder")),
    "files.show": Executor("kairu.tasks.actions:show_file", _takes(job=str, name=str), ("data_dir", "work_folder")),
    "web.open": Executor("kairu.tasks.actions:web_open", _takes(job=str, url=str), ("data_dir",)),
    "web.search": Executor("kairu.tasks.actions:web_search", _takes(job=str, query=str), ("data_dir",)),
    "web.search_private": Executor("kairu.tasks.actions:web_search_private", _takes(job=str, query=str), ("data_dir",)),
    # Kairu's browser eyes and asking an AI website (ASK.md): only the sites in kairu/tasks/ask_ai.py, only in Kairu's own profile
    "web.read_page": Executor("kairu.tasks.ask_ai:read_page", _takes(job=str, app=str), ("data_dir",)),
    "web.ask": Executor("kairu.tasks.ask_ai:ask", _takes(job=str, site=str, question=str), ("data_dir",), single=True),
    "web.ask_private": Executor("kairu.tasks.ask_ai:ask_private", _takes(job=str, site=str, question=str), ("data_dir",), single=True),
    "task.wait": Executor("kairu.tasks.actions:wait", _takes(job=str, seconds=str), ("data_dir",)),
    "task.plan": Executor("kairu.tasks.actions:record_plan",
                          _takes(job=str, plan=str, approved=str, request=str, source=str), ("data_dir",)),
    # Kairu's hands (PC4, first part, BAR.md "Handling a task"): type, press, click and read in an app's window
    "screen.read": Executor("kairu.tasks.screen:read", _takes(job=str, app=str), ("data_dir",)),
    "screen.type": Executor("kairu.tasks.screen:type_text", _takes(job=str, app=str, text=str, field=str, enter=str), ("data_dir",)),
    "screen.press": Executor("kairu.tasks.screen:press", _takes(job=str, app=str, keys=str), ("data_dir",)),
    "screen.click": Executor("kairu.tasks.screen:click", _takes(job=str, app=str, target=str), ("data_dir",)),
    "screen.confirm": Executor("kairu.tasks.screen:confirm", _takes(job=str, verb=str, app=str, what=str, field=str, enter=str),
                               ("data_dir",)),
    # The screen agent's other steps (ADR-054 proposed, BAR.md "Kairu's eyes"): scroll, forms, a point, your details, a saved
    # login, and a careful step inside a take-control run (yes, no PIN). Your details' values never travel in a request:
    # screen.fill reads them here, on this PC, by their name
    "screen.scroll": Executor("kairu.tasks.screen:scroll", _takes(job=str, app=str, direction=str, times=str), ("data_dir",)),
    "screen.choose": Executor("kairu.tasks.screen:choose", _takes(job=str, app=str, box=str, item=str), ("data_dir",)),
    "screen.tick": Executor("kairu.tasks.screen:tick", _takes(job=str, app=str, target=str, on=str), ("data_dir",)),
    "screen.point": Executor("kairu.tasks.screen:point", _takes(job=str, app=str, point=str), ("data_dir",)),
    "screen.fill": Executor("kairu.tasks.screen:fill", _takes(job=str, app=str, box=str, detail=str, site=str), ("data_dir",)),
    "screen.saved_password": Executor("kairu.tasks.screen:saved_password", _takes(job=str, app=str, site=str), ("data_dir",)),
    "screen.agent_confirm": Executor("kairu.tasks.screen:agent_confirm",
                                     _takes(job=str, verb=str, app=str, what=str, field=str, enter=str, site=str, filled=str),
                                     ("data_dir",)),
    "details.keep": Executor("kairu.tasks.details:keep_action", _takes(job=str, key=str, value=str, site=str), ("data_dir",),
                             single=True),
    "details.forget": Executor("kairu.tasks.details:forget_action", _takes(job=str, key=str, site=str), ("data_dir",),
                               single=True),
    "details.show": Executor("kairu.tasks.details:show_action", _takes(job=str), ("data_dir",)),
    # PC4, the rest (BAR.md "Reading any window, numbers and the safe list"): read any window, numbers, the safe list
    "screen.read_text": Executor("kairu.tasks.screen:read_text", _takes(job=str, app=str), ("data_dir",)),
    "screen.numbers": Executor("kairu.tasks.screen:numbers", _takes(job=str, app=str), ("data_dir",)),
    # Kairu's eyes (BAR.md "Kairu's eyes", ADR-051 proposed): one look, a picture of one safe window to Gemini; the brain's
    # settings (tasks.eyes, public_to_cloud) come from Guardian's own config.yaml, never from a request
    "screen.look": Executor("kairu.tasks.eyes:look", _takes(job=str, app=str, goal=str, history=str, mode=str, hide=str),
                            ("data_dir", "brain")),
    "hands.safe_list": Executor("kairu.tasks.screen:safe_list", _takes(job=str), ("data_dir",)),
    "hands.mark_safe": Executor("kairu.tasks.screen:mark_safe", _takes(job=str, app=str), ("data_dir",), single=True),
    "hands.unmark_safe": Executor("kairu.tasks.screen:unmark_safe", _takes(job=str, app=str), ("data_dir",), single=True),
    "brain.plan": Executor("kairu.brain.ask:plan", _takes(order=str, ask=str, source=str), ("data_dir", "brain")),
    # Shadows and skill packs (Phase H, SHADOW.md): the relay and the data folder come from Guardian's config.yaml. A Shadow's
    # words are data: none of these takes a request from one, and a pack is run only through pack.run
    "shadow.create": Executor("kairu.shadow.manager:create", _takes(friend=str, mission=str, pack=str, hours=float, repo=str,
                                                                        mode=str, base=str),
                              ("data_dir", "relay"), single=True),
    "shadow.sync": Executor("kairu.shadow.manager:sync", NONE, ("data_dir", "relay"), single=True),
    "shadow.recall": Executor("kairu.shadow.manager:recall", _takes(shadow=float, give_up=bool), ("data_dir", "relay")),
    "shadow.lesson": Executor("kairu.shadow.manager:lesson", _takes(lesson=float, keep=bool), ("data_dir",)),
    "shadow.install": Executor("kairu.shadow.manager:install", _takes(shadow=float, folder=str), ("data_dir",), single=True),
    "shadow.upgrade": Executor("kairu.shadow.manager:upgrade", _takes(shadow=float), ("data_dir",), single=True),
    "pack.run": Executor("kairu.shadow.manager:run_pack", _takes(name=str, text=str, job=str), ("data_dir",)),
    "pack.remove": Executor("kairu.shadow.manager:remove_pack", _takes(name=str), ("data_dir",)),
    # Clones (TEAM.md): Main Kairu is a paired device towards each Clone, so every order is a request its own Guardian decides
    "team.add": Executor("kairu.team.conduct:add", _takes(name=str, offer=str, code=str, share=float, skills=str), ("data_dir", "relay"),
                         single=True),
    "team.remove": Executor("kairu.team.conduct:remove", _takes(name=str), ("data_dir",)),
    "team.split": Executor("kairu.team.conduct:split", _takes(brief=str, name=str, deadline=float, ask=str, source=str),
                           ("data_dir", "brain")),
    "team.run": Executor("kairu.team.conduct:run", _takes(project=float), ("data_dir", "relay"), single=True),
    "team.set": Executor("kairu.team.conduct:set_clone", _takes(name=str, share=float, skills=str), ("data_dir",)),
    "team.move": Executor("kairu.team.conduct:move", _takes(project=float, task=float, clone=str), ("data_dir",)),
    "team.status": Executor("kairu.team.conduct:status", _takes(job=str), ("data_dir",)),
    "team.note": Executor("kairu.team.inbox:note", _takes(text=str, device=str), ("data_dir",)),
    "team.check": Executor("kairu.team.conduct:check", _takes(project=float, task=float), ("data_dir",)),
    "team.offer": Executor("kairu.team.conduct:offer", _takes(clone=str, words=str), ("data_dir",)),
    # Meeting in (HACKATHON.md stage 1, ADR-055 proposed): the brain's settings, the work folder and the data folder come from
    # Guardian's config.yaml. meeting.read takes the file's sha256 you approved and reads only exactly that file
    "meeting.read": Executor("kairu.meeting.conduct:read_meeting", _takes(job=str, file=str, sha=str, title=str, held=str),
                             ("data_dir", "brain", "work_folder")),
    "meeting.record": Executor("kairu.meeting.conduct:record", _takes(job=str, title=str, minutes=float, held=str),
                               ("data_dir", "brain"), single=True),
    "meeting.stop": Executor("kairu.meeting.conduct:stop_recording", _takes(job=str), ("data_dir",)),
    "meeting.show": Executor("kairu.meeting.conduct:show", _takes(job=str, meeting=float), ("data_dir",)),
    "meeting.forget": Executor("kairu.meeting.conduct:forget", _takes(job=str, meeting=float), ("data_dir",)),
    # Stage 2 (HACKATHON.md): the conflict check and "what did we decide about X?" read data/meetings.db only; resolve changes
    # only the ledger's statuses
    "meeting.check": Executor("kairu.meeting.conduct:check", _takes(job=str), ("data_dir",)),
    "meeting.ask": Executor("kairu.meeting.conduct:ask", _takes(job=str, topic=str), ("data_dir",)),
    "meeting.resolve": Executor("kairu.meeting.conduct:resolve", _takes(job=str, meeting=float, conflict=float, keep=str),
                                ("data_dir",)),
    # The Builder (BUILDER.md, ADR-050 proposed): the brain's settings, the work folder and the data folder come from Guardian's
    # config.yaml. A draft is only kept; build.write and forge.save take the draft's number and the sha256 you were shown
    "build.draft": Executor("kairu.build.make:draft", _takes(brief=str, kind=str, ask=str, source=str),
                            ("data_dir", "brain", "work_folder")),
    "build.write": Executor("kairu.build.make:write", _takes(job=str, draft=float, sha=str), ("data_dir", "work_folder"),
                            single=True),
    "build.test": Executor("kairu.build.make:test", _takes(job=str, folder=str), ("data_dir", "work_folder"), single=True),
    "forge.draft": Executor("kairu.build.forge:draft", _takes(task=str, ask=str, source=str), ("data_dir", "brain")),
    "forge.test": Executor("kairu.build.forge:test", _takes(job=str, recipe=float, sha=str), ("data_dir",), single=True),
    "forge.save": Executor("kairu.build.forge:save", _takes(job=str, recipe=float, sha=str), ("data_dir",), single=True),
    "forge.forget": Executor("kairu.build.forge:forget", _takes(job=str, name=str), ("data_dir",)),
    "paths.draft": Executor("kairu.build.paths:draft", _takes(task=str, done=str, ask=str, source=str), ("data_dir", "brain")),
    # PC5 (BAR.md "Commands and installs"): a command as a list of words, no shell, in the work folder or Kairu's own folder
    "terminal.run": Executor("kairu.tasks.terminal:run", _takes(job=str, command=str, folder=str), ("data_dir", "work_folder")),
    "terminal.run_work": Executor("kairu.tasks.terminal:run_work", _takes(job=str, command=str, folder=str),
                                  ("data_dir", "work_folder")),
    "terminal.run_any": Executor("kairu.tasks.terminal:run_any", _takes(job=str, command=str, folder=str),
                                 ("data_dir", "work_folder")),
    "apps.install": Executor("kairu.tasks.terminal:install", _takes(job=str, app=str), ("data_dir",), single=True),
    "apps.uninstall": Executor("kairu.tasks.terminal:uninstall", _takes(job=str, app=str), ("data_dir",), single=True),
})

_KINDS = {str: "text", float: "a number", bool: "true or false"}


def argument_problem(action: str, executor: Executor, details: Mapping) -> str:
    """Why these details cannot be this action's arguments, or "" if they can."""
    extra = sorted(set(details) - set(executor.arguments))
    if extra:
        takes = ", ".join(executor.arguments) or "no details"
        return (f"{action} takes only {takes}, not "
                f"{', '.join(repr(name[:40]) for name in extra[:5])}; nothing was run")
    for name, value in details.items():
        wanted = executor.arguments[name]
        fits = type(value) in (int, float) if wanted is float else type(value) is wanted
        if not fits:
            return f"{action}: {name} must be {_KINDS[wanted]}; nothing was run"
    return ""
