"""The kairu command.

  kairu guardian run               start Guardian: its own program, in the background, with no window
  kairu guardian quit              end the Guardian program; Kairu then refuses every request
  kairu guardian install           start Guardian at sign-in, and within a minute whenever it is not running
  kairu guardian uninstall         stop starting it so (Windows Task Scheduler)
  kairu status                     Guardian running or not; Safe Mode, PIN, policy, switches, audit log
  kairu stop                       emergency stop: halt every running action, then Safe Mode
  kairu resume                     leave Safe Mode ("yes" and your PIN), through Guardian
  kairu pin set                    set or change your PIN, through Guardian
  kairu request ACTION [key=value] ask Guardian about one action; High tier asks for "yes" and the PIN
  kairu audit verify               check the audit log's hash chain and compare it with the anchor
  kairu audit reanchor             accept the audit log as it is now, after a problem ("yes" and your PIN)
  kairu audit show [-n 20]         the newest audit rows
  kairu demo [--seconds 60]        Guardian runs a harmless counting action, to try the stop and Ctrl+Alt+K
  kairu hotkey                     hold Ctrl+Alt+K (Windows) until you press Ctrl+C

Protection (Phase J, PROTECTION.md): Guardian's monitors watch what you connect and raise alerts; they never act.
  kairu alerts [--all]                    the alerts, newest first
  kairu alerts show N                     one alert in full: what, why, the evidence, what was not checked
  kairu alerts dismiss N [--false-alarm]  mark it done (or wrong: kept as your report)
  kairu protect status                    each source's health, the monitors, new alerts
  kairu protect start                     start the monitors now (Guardian usually does it itself)
  kairu protect pause|resume [SOURCE]     gmail, deadlines, folders, devices, security or all
  kairu protect connect-gmail FILE        read-only Gmail, with Google's sign-in in your browser ("yes" and your PIN)
  kairu protect setup-pc [--folder PATH]  watch Downloads, devices and Windows Security ("yes" and your PIN)
  kairu protect add-folder PATH           watch one more folder ("yes" and your PIN)
  kairu protect remove-folder PATH        stop watching a folder
  kairu protect disconnect-gmail          remove Kairu's Gmail access and delete its key
  kairu deadline add TITLE DATE [TIME]    reminders 3 days, 1 day and 3 hours before
  kairu deadline list | remove N

Kairu Link and Mission Mode (Phase C, LINK.md): your phone talks to this PC through the Gate; Guardian decides.
  kairu device pair                pair your phone: a QR code and a 6-digit code, valid 10 minutes ("yes" and your PIN)
  kairu device list                the paired devices
  kairu device remove ID           unpair one: every message from it is refused from then on
  kairu link status                the Gate, the receiver, the paired devices, requests waiting for you
  kairu link send ID TEXT          send a paired device a message
  kairu link waiting               your phone's High requests, waiting for "yes" and your PIN here
  kairu link approve N | refuse N  answer one ("yes" and your PIN to approve)
  kairu mission-mode on            keep the PC awake with the lid closed while it charges ("yes" and your PIN)
  kairu mission-mode off           end it: the lid setting is put back at once
  kairu mission-mode status        on or off, the lid setting, the limits, how it last ended

Kairu's brain and Mission Cards (Phase B, BRAIN.md): Guardian decides every question and every step.
  kairu ask QUESTION               a short answer: fixed rules here (L0), or free cloud AI (L3) after the privacy filter
  kairu ask --dry-run QUESTION     where it would go and what the privacy filter finds; nothing is sent
  kairu ask "search ..."           look it up on the web first (RESEARCH.md), as for questions that need fresh facts
  kairu ask "sources?"             the page titles and links the last answer used
  kairu usage                      each provider's questions today, its free limit, and every switch
  kairu provider add NAME          save a free provider's key, sealed ("yes" and your PIN): groq, cloudflare, openrouter
  kairu provider list | remove NAME | pause NAME [--minutes M] | resume NAME
  kairu mission new FILE           a Mission Card from a card file (`kairu mission example` shows one)
  kairu mission new --practice     the gate test's practice card: it counts, then answers one question
  kairu mission list | show N | stop N | continue N | remove N

The Kairu bar (Sprint Day 1, BAR.md): typed orders in a small floating bar; Guardian decides every step.
  kairu bar                        start it and show it; Ctrl+Alt+Space shows and hides it
  kairu bar quit                   end it; Guardian and running actions carry on
  kairu bar install | uninstall    start it, hidden, when you sign in (Task Scheduler)

Kairu's light voice (Sprint Day 2, VOICE.md): the mic button in the bar, "Kairu" or Ctrl+Alt+V; Guardian decides every step.
  kairu voice setup [--model M]    download the speech model (voice.engine's: Whisper base.en by default; with --model a
                                   Vosk one), Piper and the voices, each SHA-256 checked; you run it
  kairu voice status               the voice switch, the model, the key, and Windows' microphone setting
  kairu voice enroll [--forget]    keep (or delete) your voice print, for voice.only_my_voice; you run it

Shadows (Phase H, SHADOW.md): a temporary helper on a friend's laptop that comes home with a use case; it holds no authority.
  kairu shadow create --for NAME --mission TEXT   an invite and a 6-digit code, valid 15 minutes ("yes" and your PIN)
  kairu shadow list | status N     your Shadows, their progress and reports
  kairu shadow recall N            "come back now"
  kairu shadow install N           install the use case it brought home, after you tested it ("yes" and your PIN)
  kairu shadow lessons | keep K | drop K   what your Shadows learned: kept only after your yes
  kairu pack list | run NAME [WORDS] | remove NAME   the installed use cases; running one needs "yes" and your PIN

Clones (TEAM.md): Main Kairu splits a project across Kairus on your team's laptops; each Clone's own Guardian decides.
  kairu team add NAME "OFFER" CODE  make a Clone from what `kairu device pair` shows on its laptop ("yes" and your PIN)
  kairu team split "BRIEF" --hours 6   Main Kairu splits the project into tasks for the Clones
  kairu team start [N] | show [N]   run it, and the team board: progress, each Clone's last words, slipping tasks

  kairu doctor                     Guardian's state, Kairu's memory use per program and the PC's free memory (read only)

Requests, approvals, actions, resume, the PIN and re-anchoring go to the Guardian program over its
private channel (kairu/client.py); if it is not running, they are refused. Guardian starts every
action itself and holds Ctrl+Alt+K. `kairu stop` needs only the database, so it works without Guardian.

Without installing, use `python -m kairu ...` in this folder.
"""

import argparse
import getpass
import sys
import time
from datetime import datetime

from kairu import config as kairu_config


def main(argv: list[str] | None = None) -> int:
    from kairu.store import MissingDatabase
    for stream in (sys.stdout, sys.stderr):  # an email's words may not fit the terminal's code page: never crash on them
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    try:
        if args.command == "stop":  # first and lightest: needs only the database
            return _stop(args)
        cfg = kairu_config.load(args.config)
        return COMMANDS[args.command](args, cfg)
    except kairu_config.ConfigError as error:
        print(f"kairu: {error}", file=sys.stderr)
        return 2
    except MissingDatabase as error:
        if args.command == "audit" and args.audit_command == "verify":
            print(f"Audit log PROBLEM: database file missing. {error}")
            return 1
        print(f"kairu: {error}", file=sys.stderr)
        if args.command == "stop":
            print("kairu: running Kairu actions halt on their own when guardian.db is missing, because they can no "
                  "longer read the stop flag.", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kairu", description="Kairu Guardian core.")
    parser.add_argument("--config", help="config.yaml to use (default: the one in the project folder, or $KAIRU_CONFIG)")
    commands = parser.add_subparsers(dest="command", required=True)
    guardian = commands.add_parser("guardian", help="the Guardian program").add_subparsers(dest="guardian_command", required=True)
    run = guardian.add_parser("run", help="start Guardian in the background, with no window")
    run.add_argument("--autostart", action="store_true", help="what the Task Scheduler task runs: start it only if it "
                                                               "is not running, and print nothing")
    guardian.add_parser("quit", help="end the Guardian program; Kairu then refuses every request")
    guardian.add_parser("install", help="start Guardian at sign-in, and within a minute whenever it is not running")
    guardian.add_parser("uninstall", help="remove the Task Scheduler task that `install` made")
    commands.add_parser("status", help="show whether Guardian runs, Safe Mode, PIN, policy, switches and the audit log")
    commands.add_parser("stop", help="emergency stop: halt every running action, then Safe Mode")
    commands.add_parser("resume", help='leave Safe Mode ("yes" and your PIN)')
    pin = commands.add_parser("pin", help="your Kairu PIN").add_subparsers(dest="pin_command", required=True)
    pin.add_parser("set", help="set or change your PIN")
    request = commands.add_parser("request", help="ask Guardian about one action")
    request.add_argument("action")
    request.add_argument("details", nargs="*", metavar="key=value", help="details shown when you approve")
    audit = commands.add_parser("audit", help="the audit log").add_subparsers(dest="audit_command", required=True)
    audit.add_parser("verify", help="check the hash chain and the anchor; exit code 1 if there is a problem")
    audit.add_parser("reanchor", help='accept the audit log as it is now, after a problem ("yes" and your PIN)')
    show = audit.add_parser("show", help="the newest rows")
    show.add_argument("-n", type=int, default=20)
    demo = commands.add_parser("demo", help="Guardian runs a harmless counting action, to try the emergency stop")
    demo.add_argument("--seconds", type=float, default=60)
    commands.add_parser("hotkey", help="hold Ctrl+Alt+K (Windows) until Ctrl+C")

    alerts = commands.add_parser("alerts", help="the alerts Guardian's monitors raised, newest first")
    alerts.add_argument("--all", action="store_true", help="also the ones you dismissed")
    alerts_commands = alerts.add_subparsers(dest="alerts_command")
    alerts_show = alerts_commands.add_parser("show", help="one alert in full")
    alerts_show.add_argument("number", type=int)
    alerts_dismiss = alerts_commands.add_parser("dismiss", help="mark an alert done")
    alerts_dismiss.add_argument("number", type=int)
    alerts_dismiss.add_argument("--false-alarm", action="store_true", help="it was wrong (kept as your report)")

    protect = commands.add_parser("protect", help="Guardian's monitors").add_subparsers(dest="protect_command", required=True)
    protect.add_parser("status", help="each source's health, the monitors and new alerts")
    protect.add_parser("start", help="start the monitors now")
    for name, verb in (("pause", "pause watching"), ("resume", "watch again")):
        one = protect.add_parser(name, help=f"{verb} a source, or all")
        one.add_argument("source", nargs="?", default="all",
                         choices=("all", "gmail", "deadlines", "folders", "devices", "security"))
    connect = protect.add_parser("connect-gmail", help="read-only Gmail, with Google's sign-in in your browser")
    connect.add_argument("client_file", help="the OAuth client file (Desktop app) you downloaded from Google Cloud")
    protect.add_parser("disconnect-gmail", help="remove Kairu's Gmail access and delete its key")
    setup = protect.add_parser("setup-pc", help="watch Downloads, devices and Windows Security, read-only")
    setup.add_argument("--folder", help="a folder to watch instead of Downloads")
    protect.add_parser("add-folder", help="watch one more folder for risky new files").add_argument("folder")
    protect.add_parser("remove-folder", help="stop watching a folder").add_argument("folder")

    deadline = commands.add_parser("deadline", help="your deadlines").add_subparsers(dest="deadline_command", required=True)
    add = deadline.add_parser("add", help="add a deadline: reminders 3 days, 1 day and 3 hours before")
    add.add_argument("title")
    add.add_argument("date", help="2026-11-05, 05/11/2026, 5 Nov or tomorrow")
    add.add_argument("time", nargs="?", default="", help="18:00 or 6pm (default 11:59 pm)")
    add.add_argument("--note", default="")
    deadline.add_parser("list", help="the open deadlines")
    remove = deadline.add_parser("remove", help="take a deadline off the list")
    remove.add_argument("number", type=int)

    device = commands.add_parser("device", help="your paired devices (Kairu Link)").add_subparsers(
        dest="device_command", required=True)
    device.add_parser("pair", help="pair your phone: a QR code and a 6-digit code, valid 10 minutes")
    device.add_parser("list", help="the paired devices")
    device.add_parser("remove", help="unpair a device").add_argument("device", help="its id, from `kairu device list`")
    link = commands.add_parser("link", help="Kairu Link: messages with your phone").add_subparsers(
        dest="link_command", required=True)
    link.add_parser("status", help="the Gate, the receiver, the paired devices and the requests waiting for you")
    send = link.add_parser("send", help="send a paired device a message")
    send.add_argument("device")
    send.add_argument("text")
    send.add_argument("--type", default="report", choices=("report", "status", "doubt", "call_request", "mission", "command"))
    link.add_parser("waiting", help="your phone's High requests, waiting for \"yes\" and your PIN")
    link.add_parser("approve", help="approve one (\"yes\" and your PIN): Guardian runs it").add_argument("number", type=int)
    link.add_parser("refuse", help="refuse one").add_argument("number", type=int)
    missions = commands.add_parser("mission-mode", help="the PC stays awake with the lid closed while it charges")
    missions.add_argument("switch", choices=("on", "off", "status"))

    ask = commands.add_parser("ask", help="ask Kairu a question: a short answer")
    ask.add_argument("words", nargs="+", metavar="QUESTION")
    ask.add_argument("--dry-run", action="store_true", help="only show where it would go; nothing is sent")
    bar = commands.add_parser("bar", help="the Kairu bar: typed orders in a small floating bar")
    bar.add_argument("bar_command", nargs="?", default="start", choices=("start", "quit", "install", "uninstall"))
    bar.add_argument("--hidden", action="store_true", help="start it without showing it; Ctrl+Alt+Space shows it")
    phone = commands.add_parser("phone", help="put the Kairu phone app on your phone with adb (PHONE.md)").add_subparsers(
        dest="phone_command", required=True)
    phone_install = phone.add_parser("install", help="install the app built on GitHub (newest kairu-phone file in Downloads)")
    phone_install.add_argument("file", nargs="?", help="a kairu-phone .apk, or GitHub's artifact .zip")
    phone_pair = phone.add_parser("pair", help="once: pair adb with the phone's Wireless debugging")
    phone_pair.add_argument("address", help="the address under 'Pair device with pairing code'")
    phone_pair.add_argument("code", help="the 6-digit pairing code")
    phone.add_parser("connect", help="connect adb to the phone over Wi-Fi").add_argument("address", help="Wireless debugging's address")
    phone.add_parser("status", help="adb, the phone and the newest app file")
    from kairu.shadow import commands as shadow_commands  # argparse only: nothing of the Link or its crypto is loaded
    shadow_commands.add_parsers(commands)
    from kairu.team import commands as team_commands  # argparse only
    commands.add_parser("doctor", help="Guardian's state, Kairu's memory use and the PC's free memory (read only)")
    details = commands.add_parser("details", help="your details for forms (name, email ...), on this PC only (BAR.md)") \
        .add_subparsers(dest="details_command", required=True)
    details_set = details.add_parser("set", help="keep one detail: name, email, phone, city, college, linkedin, resume, "
                                                 "username (with --site)")
    details_set.add_argument("key")
    details_set.add_argument("value", nargs="+")
    details_set.add_argument("--site", default="", help="the site a username is for, such as github.com")
    details.add_parser("show", help="your saved details")
    details_forget = details.add_parser("forget", help="forget one detail")
    details_forget.add_argument("key")
    details_forget.add_argument("--site", default="")
    team_commands.add_parsers(commands)
    workspace = commands.add_parser("workspace", help="the Kairu workspace: projects and missions in one window (WORKSPACE.md)")
    workspace.add_argument("workspace_command", nargs="?", default="start", choices=("start", "quit", "status"))
    voice = commands.add_parser("voice", help="Kairu's light voice: the offline speech model").add_subparsers(
        dest="voice_command", required=True)
    from kairu.config import VOICE_MODELS
    setup = voice.add_parser("setup", help="download the offline speech model, Piper and the voices, each SHA-256 checked")
    setup.add_argument("--model", choices=VOICE_MODELS, help="a Vosk model instead (the fallback, voice.engine: vosk)")
    voice.add_parser("status", help="the voice switch, the model, the key, and Windows' microphone setting")
    from kairu.config import VOICE_STYLES, VOICE_VOICES
    check = voice.add_parser("check", help="what your microphone and Whisper hear, and whether it wakes Kairu (you run it)")
    check.add_argument("--seconds", type=float, default=15, help="how long to listen (3 to 60; default 15)")
    enroll = voice.add_parser("enroll", help="keep your voice print for voice.only_my_voice (you run it; no sound is kept)")
    enroll.add_argument("--forget", action="store_true", help="delete your voice print instead")
    hear = voice.add_parser("try", help="hear how Kairu says an answer in each style (you run it; nothing is sent or kept)")
    hear.add_argument("--style", choices=VOICE_STYLES, help="only this style (default: all four, one after the other)")
    from kairu.config import KOKORO_VOICES, VOICE_TTS
    hear.add_argument("--voice", choices=VOICE_VOICES + KOKORO_VOICES, help="another voice than the one in config.yaml")
    hear.add_argument("--tts", choices=VOICE_TTS, help="kokoro or piper instead of voice.tts in config.yaml")
    hear.add_argument("--voices", action="store_true", help="every voice instead, one after the other, to pick the one you like")
    commands.add_parser("usage", help="each free provider's questions today, its free limit, and every switch")
    provider = commands.add_parser("provider", help="the free AI providers").add_subparsers(
        dest="provider_command", required=True)
    from kairu.config import PROVIDER_NAMES
    provider.add_parser("list", help="the providers, which are set up, and their free limits")
    provider.add_parser("add", help="save a provider's key, sealed (\"yes\" and your PIN)").add_argument(
        "name", choices=PROVIDER_NAMES)
    provider.add_parser("remove", help="delete a provider's key from this PC").add_argument("name", choices=PROVIDER_NAMES)
    pause = provider.add_parser("pause", help="leave a provider alone for a while, as if at its free limit")
    pause.add_argument("name", choices=PROVIDER_NAMES)
    pause.add_argument("--minutes", type=float, default=10)
    provider.add_parser("resume", help="use a paused provider again").add_argument("name", choices=PROVIDER_NAMES)
    mission = commands.add_parser("mission", help="Mission Cards: long jobs with a checkpoint after every step")
    mission_commands = mission.add_subparsers(dest="mission_command", required=True)
    new = mission_commands.add_parser("new", help="save a new Mission Card; Guardian starts it")
    new.add_argument("file", nargs="?", help="a card file (`kairu mission example` shows one)")
    new.add_argument("--practice", action="store_true", help="the gate test's practice card")
    mission_commands.add_parser("example", help="print an example card file, or write it to FILE").add_argument(
        "file", nargs="?", help="where to write it, for example card.yaml")
    mission_commands.add_parser("list", help="the missions")
    for name, text in (("show", "one mission in full"), ("stop", "stop one; it keeps its last checkpoint"),
                       ("continue", "go on from the last checkpoint (and approve the steps that wait for you)"),
                       ("remove", "delete a mission that is not running")):
        mission_commands.add_parser(name, help=text).add_argument("number", type=int)
    return parser


def _store(cfg):
    from kairu.store import Store
    return Store(cfg.data_dir, cfg.anchor_path)


def _stop(args) -> int:
    from kairu import safemode
    try:
        cfg = kairu_config.load(args.config)
    except kairu_config.ConfigError as error:  # a broken config.yaml must not block the stop
        cfg = kairu_config.Config(False, False, kairu_config.ROOT / "policy.yaml", kairu_config.ROOT / "data")
        print(f"kairu: {error}\nkairu: stopping with the default data folder, {cfg.data_dir}", file=sys.stderr)
    count = safemode.emergency_stop(_store(cfg), "kairu stop")
    print(f"Emergency stop sent (stop {count}). Every running Kairu action halts within 1 second.")
    print("Kairu is in Safe Mode: read-only actions only, until you run `kairu resume`.")
    _stop_mission_mode(cfg)
    return 0


def _stop_mission_mode(cfg) -> None:
    """After a stop: Guardian puts Mission Mode's lid setting back as the action halts; without Guardian, do it here."""
    from kairu import mission
    if mission.saved(cfg.data_dir) is None:
        return
    try:
        from kairu.client import GuardianClient
        if GuardianClient(cfg, start_if_down=False).alive():
            print("Mission Mode ends with the stop; Guardian puts the lid setting back.")
            return
        print(f"Mission Mode: {mission.restore(cfg.data_dir) or 'the lid setting was already back'}.")
    except Exception as error:  # the stop itself has happened; this must not hide it
        print(f"kairu: Mission Mode's lid setting was not put back here ({error}); Guardian puts it back when it starts.",
              file=sys.stderr)


def _guardian(args, cfg) -> int:
    from kairu import autostart, channel, client
    config_file = args.config or kairu_config.config_path()
    if args.guardian_command == "run" and args.autostart:  # the Task Scheduler task, every minute and at sign-in
        if autostart.paused(cfg.data_dir):
            return 0
        try:
            if not client.GuardianClient(cfg, start_if_down=False).alive():
                client.start_guardian(cfg, config_file)
        except channel.ChannelError:
            return 1
        return 0
    if args.guardian_command == "run":
        autostart.unpause(cfg.data_dir)  # starting it by hand also ends a pause left by an interrupted check
        try:
            state, started = client.start_guardian(cfg, config_file)
        except channel.ChannelError as error:
            print(f"Guardian was not started: {error}.")
            return 1
        print(f"Guardian is {'running' if started else 'already running'} (process {state['pid']}), in the background "
              "with no window. Kairu asks it for every decision; `kairu guardian quit` ends it.")
        return 0
    if args.guardian_command == "install":
        return _install(cfg, config_file)
    if args.guardian_command == "uninstall":
        name = autostart.uninstall(cfg.data_dir)
        print(f"Removed the Task Scheduler task \"{name}\"." if name else "There was no Task Scheduler task to remove.")
        print("Guardian no longer starts by itself. If it is running, it keeps running until `kairu guardian quit`, "
              "or until you sign out.")
        return 0
    try:
        client.quit_guardian(cfg)
    except channel.NotRunning:
        print("Guardian is not running.")
        return 0
    except channel.ChannelError as error:
        print(f"Guardian was not asked to quit: {error}.")
        return 1
    print("Guardian has quit. Kairu refuses every request until Guardian runs again.")
    if autostart.installed(cfg.data_dir):
        print("Task Scheduler starts it again within a minute; `kairu guardian uninstall` stops that.")
    return 0


def _install(cfg, config_file) -> int:
    from kairu import autostart, channel, client
    try:
        name = autostart.install(cfg.data_dir, client.windowless_python(), config_file)
    except autostart.AutostartError as error:
        print(f"Not installed: {error}")
        return 1
    print(f"Made the Task Scheduler task \"{name}\": it starts Guardian when you sign in, and again within a minute "
          "whenever it is not running. It runs as you, with normal rights, only while you are signed in.")
    try:
        state, _ = client.start_guardian(cfg, config_file)
    except channel.ChannelError as error:
        print(f"Guardian is not running yet: {error}. Task Scheduler tries again within a minute.")
        return 1
    print(f"Guardian is running (process {state['pid']}). `kairu guardian uninstall` removes the task.")
    return 0


def _status(args, cfg) -> int:
    from kairu import audit, channel
    from kairu.client import GuardianClient, unavailable
    try:
        state = GuardianClient(cfg).status()
        running = f"running (process {state['pid']}); every decision is made there"
    except channel.ChannelError as error:
        state = _state_on_disk(cfg)
        running = f"{unavailable(error)}. What follows is read from the files"
    on_off = lambda enabled, name: "on" if enabled else f"off ({name}.enabled: false)"
    mode = f"Safe Mode ({state['safe_reason']})" if state["mode"] == "safe" else "normal"
    policy = state["policy"]
    policy = (f"{policy['file']}, {policy['actions']} actions" if "actions" in policy
              else f"NOT READ, so every action is denied: {policy['error']}")
    verdict = state["audit"]
    chain = (f"{verdict['rows']} rows, chain intact, anchor agrees" if verdict["ok"]
             else f"PROBLEM ({audit.LABELS.get(verdict['kind'], verdict['kind'])}): {verdict['problem']}")
    running_now = state.get("running")
    actions = ("none: they run only inside Guardian" if running_now is None
               else ", ".join(f"{run['action']} (run {run['run']}, process {run['pid']})" for run in running_now)
               or "none running")
    key = state.get("hotkey")
    key = ("Ctrl+Alt+K held by Guardian: it stops every action from any window" if key == "held"
           else f"Ctrl+Alt+K NOT held by Guardian ({key or 'Guardian is not running'}); `kairu stop` still works")
    task = state.get("autostart")
    task = (f"Task Scheduler task \"{task}\": at sign-in, and within a minute whenever Guardian is not running" if task
            else "not set up (`kairu guardian install`)")
    print("Kairu Guardian")
    print(f"  Guardian:  {running}")
    print(f"  autostart: {task}")
    print(f"  hotkey:    {key}")
    print(f"  actions:   {actions}")
    print(f"  mode:      {mode}")
    print(f"  PIN:       {'set' if state['pin_set'] else 'not set (run `kairu pin set`)'}")
    print(f"  policy:    {policy}")
    print(f"  voice:     {on_off(state['voice'], 'voice')}")
    print(f"  research:  {on_off(state['research'], 'research')}")
    print(f"  audit log: {chain}")
    print(f"  protection: {_protection_summary(cfg, running_now)}")
    link = state["link"]
    waiting = state.get("phone_waiting")
    print(f"  link:      {'on' if link['enabled'] else 'off (link.enabled: false)'}, Gate {link['relay']}, "
          f"{link['devices']} device{'s' if link['devices'] != 1 else ''} paired"
          + (f", {waiting} request{'s' if waiting != 1 else ''} waiting for your PIN (`kairu link waiting`)" if waiting else ""))
    print(f"  mission:   {'ON: the lid setting is changed (`kairu mission-mode status`)' if state['mission_mode'] else 'off'}")
    print(f"  brain:     {_brain_summary(cfg)}")
    print(f"  data:      {state['data']}")
    return 0


def _protection_summary(cfg, running) -> str:
    """One line for `kairu status`: the monitors, each source, new alerts. Reads only."""
    from kairu.protect import store as protect_store
    if not (cfg.data_dir / protect_store.DB_NAME).exists():
        return "nothing connected yet (see PROTECTION.md)"
    store = protect_store.ProtectStore(cfg.data_dir)
    watching = running is not None and any(run["action"] == "protect.watch" for run in running)
    sources = ", ".join(f"{name} {info['state']}" for name, info in store.sources().items()) or "no sources"
    new = store.count_new()
    return (f"monitors {'running' if watching else 'not running'}; {sources}; "
            f"{new} new alert{'s' if new != 1 else ''}{' (`kairu alerts`)' if new else ''}")


def _state_on_disk(cfg) -> dict:
    """What the files say, for `kairu status` while Guardian is not running. Reads only."""
    from kairu import policy
    from kairu.guardian_program import describe
    try:
        rules, error = policy.load(cfg.policy_path), ""
    except policy.PolicyError as problem:
        rules, error = None, str(problem)
    return describe(_store(cfg), cfg, rules, error)


def _resume(args, cfg) -> int:
    from kairu import approval, channel
    from kairu.client import GuardianClient, unavailable
    guardian = GuardianClient(cfg)
    try:
        state = guardian.status()
    except channel.ChannelError as error:
        print(f"Not resumed: {unavailable(error)}.")
        return 1
    if state["mode"] != "safe":
        print("Kairu is not in Safe Mode.")
        return 0
    print(f"Kairu is in Safe Mode: {state['safe_reason']}.")
    return 0 if approval.ask_resume(guardian) else 1


def _pin(args, cfg) -> int:
    from kairu import channel, pin
    from kairu.client import GuardianClient, unavailable
    from kairu.guardian import Refused
    guardian = GuardianClient(cfg)
    try:
        state = guardian.status()  # before you type anything: is Guardian there to take it?
    except channel.ChannelError as error:
        print(f"Not changed: {unavailable(error)}.")
        return 1
    current = getpass.getpass("Current PIN: ") if state["pin_set"] else None
    new = getpass.getpass(f"New PIN (at least {pin.MIN_LENGTH} characters): ")
    if getpass.getpass("New PIN again: ") != new:
        print("The two PINs are different; nothing was changed.")
        return 1
    try:
        guardian.set_pin(new, current)
    except Refused as error:
        print(f"Not changed: {error}")
        return 1
    print("PIN saved (only its Argon2id hash is stored).")
    return 0


def _request(args, cfg) -> int:
    from kairu import approval
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Verdict
    details = dict(item.split("=", 1) if "=" in item else (item, "") for item in args.details)
    guardian = GuardianClient(cfg)
    decision = guardian.check(Action(args.action, details))
    print(f"Guardian: {decision.verdict} ({decision.reason})")
    if decision.verdict is Verdict.NEEDS_APPROVAL and approval.ask(guardian, decision) is None:
        return 1
    if decision.verdict is Verdict.DENY:
        return 1
    print("Nothing runs: `kairu request` only asks. Guardian runs only the actions it has code for: demo.count "
          "(`kairu demo`), the protection commands (`kairu protect`, `kairu alerts`, `kairu deadline`), Kairu Link "
          "and Mission Mode (`kairu device`, `kairu link`, `kairu mission-mode`), and the brain (`kairu ask`, "
          "`kairu provider`, `kairu mission`).")
    return 0


def _audit(args, cfg) -> int:
    from kairu import audit
    store = _store(cfg)
    if args.audit_command == "verify":
        verdict = audit.verify(store)
        if verdict.ok:
            print(f"Audit log intact: {verdict.rows} rows, every hash matches, and the anchor agrees.")
            return 0
        if verdict.kind == audit.CHAIN_BROKEN:
            print(f"Audit log TAMPERED at row {verdict.bad_row}: {verdict.problem}. "
                  f"The {verdict.rows} rows before it are intact.")
        else:
            print(f"Audit log PROBLEM: {audit.LABELS.get(verdict.kind, verdict.kind)}. {verdict.problem}.")
        return 1
    if args.audit_command == "reanchor":
        return _reanchor(store, cfg)
    for row in audit.tail(store, args.n):
        print(f"{row['id']:>5}  {row['ts']}  {row['kind']:<14} {row['action'] or '':<22} {row['decision'] or '':<15} "
              f"{row['details']}")
    return 0


def _reanchor(store, cfg) -> int:
    from kairu import audit, channel
    from kairu.approval import read_answer
    from kairu.client import GuardianClient, unavailable
    from kairu.guardian import Refused
    verdict = audit.verify(store)  # what you are asked to accept; Guardian checks it again itself
    if verdict.ok:
        print("The audit log and its anchor already agree; nothing to do.")
        return 0
    if verdict.kind == audit.CHAIN_BROKEN:
        print(f"Refused: rows inside the audit log were changed (row {verdict.bad_row}: {verdict.problem}). "
              "Re-anchoring cannot fix that; keep guardian.db as it is, as evidence.")
        return 1
    print(f"Problem: {audit.LABELS.get(verdict.kind, verdict.kind)}. {verdict.problem}.")
    print(f"Re-anchoring accepts the audit log as it is now ({verdict.rows} rows). What was wrong stays on record "
          "as a new audit row.")
    answer = read_answer(input, 'Type "yes" to re-anchor, anything else to leave it: ')
    if answer.strip().lower() != "yes":
        print('Not re-anchored: you did not type "yes".')
        return 1
    guardian = GuardianClient(cfg)
    try:
        guardian.status()  # before you type the PIN: is Guardian there to take it?
    except channel.ChannelError as error:
        print(f"Not re-anchored: {unavailable(error)}.")
        return 1
    try:
        guardian.reanchor(answer, read_answer(getpass.getpass, "Your Kairu PIN: "))
    except Refused as error:
        print(f"Not re-anchored: {error}")
        return 1
    print("Re-anchored: the anchor now matches the audit log.")
    return 0


def _demo(args, cfg) -> int:
    """Guardian runs demo.count. If Guardian is not running, the demo starts it, and ends again only a Guardian it started."""
    from kairu import channel, client
    guardian = client.GuardianClient(cfg)
    started_here = False
    try:
        state = guardian.status()
    except channel.NotRunning:
        try:
            state, started_here = client.start_guardian(cfg, args.config or kairu_config.config_path())
        except channel.ChannelError as error:
            print(f"Guardian refused demo.count: Guardian is not running, and could not be started ({error}).")
            return 1
        print(f"Guardian was not running, so the demo started it (process {state['pid']}); it ends again with the demo."
              if started_here else f"Guardian is running now (process {state['pid']}); the demo leaves it running.")
    except channel.ChannelError as error:
        print(f"Guardian refused demo.count: {client.unavailable(error)}.")
        return 1
    try:
        return _demo_watch(args, cfg, guardian, state)
    finally:
        if started_here:  # never a Guardian that someone else started
            try:
                client.quit_guardian(cfg)
            except channel.ChannelError as error:
                print(f"kairu: the Guardian this demo started did not quit ({error}); `kairu guardian quit` ends it.",
                      file=sys.stderr)


def _demo_watch(args, cfg, guardian, state) -> int:
    from kairu import hotkey, safemode
    from kairu.guardian import Action, Refused
    store = _store(cfg)  # for the stop, which needs only the database, and for timing it
    key = hotkey.Hotkey(lambda: safemode.emergency_stop(store, hotkey.NAME))
    guardian_has_key = state.get("hotkey") == "held"
    has_key = guardian_has_key or key.start()  # the demo holds the key only when Guardian does not
    try:
        try:
            run = guardian.run(Action("demo.count", {"seconds": args.seconds, "quiet": True}))
        except Refused as refusal:
            print(f"Guardian refused demo.count: {refusal}")
            return 1
        print(f"demo.count is running inside Guardian (process {run['pid']}) for {args.seconds:g} s.")
        print(f"Press {hotkey.NAME} anywhere{' (Guardian holds it)' if guardian_has_key else ''}, or run `kairu stop` "
              "in another terminal, to stop it." if has_key else f"Run `kairu stop` in another terminal to stop it ({key.error}).")
        started, shown = time.monotonic(), 0
        try:
            while (outcome := guardian.run_status(run["run"])["outcome"]) is None:
                if (elapsed := int(time.monotonic() - started)) > shown:
                    shown = elapsed
                    print(f"  demo.count: {elapsed} s", flush=True)
                time.sleep(0.2)  # short waits, so Ctrl+C still works on Windows
        except KeyboardInterrupt:
            print("Ctrl+C: ending the demo.")
            try:
                guardian.end(run["run"])
            except Refused:
                pass  # it had ended already
            return 0
        except Refused as refusal:
            print(f"Lost touch with Guardian: {refusal}. Run `kairu stop` to be sure the demo has stopped.")
            return 1
        if outcome == "halted":
            requested = safemode.stop_requested_at(store) or time.time()
            print(f"Halted {time.time() - requested:.2f} s after the stop request. Kairu is now in Safe Mode; "
                  "`kairu resume` to leave it.")
        else:
            print(f"demo.count {outcome}.")
        return 0
    finally:
        key.close()


def _hotkey(args, cfg) -> int:
    from kairu import channel, hotkey, safemode
    from kairu.client import GuardianClient
    try:
        if GuardianClient(cfg, start_if_down=False).status().get("hotkey") == "held":
            print(f"Guardian holds {hotkey.NAME} already: it stops every Kairu action from any window. Nothing to do here.")
            return 0
    except channel.ChannelError:
        pass  # without Guardian, hold it here
    store = _store(cfg)

    def pressed():
        count = safemode.emergency_stop(store, hotkey.NAME)
        print(f"{hotkey.NAME}: emergency stop sent (stop {count}). Kairu is in Safe Mode.", flush=True)

    key = hotkey.Hotkey(pressed)
    if not key.start():
        print(f"kairu: {key.error}", file=sys.stderr)
        return 1
    print(f"Holding {hotkey.NAME}: press it anywhere to stop every Kairu action. Ctrl+C here to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    key.close()
    return 0


# --- protection (Phase J) ---------------------------------------------------------------------------

def _protect_store(cfg):
    from kairu.protect.store import ProtectStore
    return ProtectStore(cfg.data_dir)


def _act(cfg, name: str, details: dict | None = None, high: bool = False, seconds: float = 60, while_waiting=None) -> str:
    """Ask Guardian to run one action and wait until it ends. "" if it finished; otherwise why not, in words."""
    from kairu import approval, channel
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Refused, Verdict
    guardian, action, granted = GuardianClient(cfg), Action(name, details or {}), None
    if high:  # shown in full, then "yes" and your PIN
        decision = guardian.check(action)
        if decision.verdict is Verdict.DENY:
            return f"Guardian refused {name}: {decision.reason}"
        if decision.verdict is Verdict.NEEDS_APPROVAL:
            granted = approval.ask(guardian, decision)
            if granted is None:
                return "not approved, so nothing was done"
    try:
        run = guardian.run(action, granted)
        deadline = time.monotonic() + seconds
        while (outcome := guardian.run_status(run["run"])["outcome"]) is None:
            if while_waiting:
                while_waiting()
            if time.monotonic() > deadline:
                return f"{name} is still running after {seconds:g} s"
            time.sleep(0.2)
    except Refused as refusal:
        return f"Guardian refused {name}: {refusal}"
    except channel.ChannelError as error:
        return str(error)
    return "" if outcome == "finished" else f"{name} {outcome}; Guardian's log ({cfg.data_dir / 'guardian.log'}) says why"


def _start_watch(cfg, say: bool = False) -> None:
    """Start the monitors if they are not running (they end by themselves when there is nothing to watch)."""
    from kairu import channel
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Refused
    try:
        GuardianClient(cfg).run(Action("protect.watch"))
        if say:
            print("Guardian started its monitors.")
    except Refused as refusal:
        if say:
            print("The monitors are already running." if "already running" in str(refusal)
                  else f"The monitors were not started: {refusal}")
    except channel.ChannelError as error:
        if say:
            print(f"The monitors were not started: {error}")


def _when(moment) -> str:
    local = moment.astimezone()
    hour = local.hour % 12 or 12
    return f"{local.strftime('%a')} {local.day} {local.strftime('%b %Y')}, {hour}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"


def _ago(moment) -> str:
    from kairu.protect.store import now_utc
    if moment is None:
        return "never"
    seconds = int((now_utc() - moment).total_seconds())
    if seconds < 90:
        return f"{max(seconds, 0)} s ago"
    if seconds < 5400:
        return f"{seconds // 60} min ago"
    return f"{seconds // 3600} h ago" if seconds < 172800 else f"{seconds // 86400} days ago"


def _alerts(args, cfg) -> int:
    store = _protect_store(cfg)
    if args.alerts_command == "show":
        alert = store.alert(args.number)
        if alert is None:
            print(f"There is no alert {args.number}.")
            return 1
        print(f"Alert {alert.id}: {alert.title}")
        confidence = f" · {alert.confidence} confidence" if alert.confidence else ""
        print(f"  {alert.classification}{confidence} · {alert.source} · {_when(alert.created)}")
        for label, text in alert.lines:
            print(f"  {label + ':':<13}{text}")
        if alert.why:
            print("  Why:")
            for point in alert.why:
                print(f"    - {point}")
        if alert.confidence_reason:
            print(f"  {'Confidence:':<13}{alert.confidence or 'n/a'}: {alert.confidence_reason}")
        if alert.not_checked:
            print("  Not checked:")
            for point in alert.not_checked:
                print(f"    - {point}")
        if alert.you_can:
            print(f"  {'You can:':<13}{alert.you_can}")
        status = {"new": f"new (`kairu alerts dismiss {alert.id}` when done; add --false-alarm if it is wrong)",
                  "dismissed": "dismissed", "false_alarm": "you marked it a false alarm"}[alert.status]
        print(f"  {'Status:':<13}{status}")
        return 0
    if args.alerts_command == "dismiss":
        alert = store.alert(args.number)
        if alert is None or alert.status != "new":
            print(f"There is no open alert {args.number}.")
            return 1
        problem = _act(cfg, "alerts.dismiss", {"alert": args.number, "false_alarm": args.false_alarm})
        if problem:
            print(f"Not dismissed: {problem}")
            return 1
        print(f"Alert {args.number} {'marked a false alarm (kept as your report)' if args.false_alarm else 'dismissed'}.")
        return 0
    shown = store.alerts(include_closed=args.all)
    if not shown:
        print("No new alerts." if not args.all else "No alerts yet.")
        print("That means only that nothing was found in the sources being watched (`kairu protect status`); "
              "it never means everything is safe.")
        return 0
    print(f"{'Alerts' if args.all else 'New alerts'}, newest first ({len(shown)}):")
    for alert in shown:
        late = " (found late)" if alert.found_late else ""
        status = "" if alert.status == "new" else f" [{alert.status.replace('_', ' ')}]"
        local = alert.created.astimezone()
        print(f"  #{alert.id:<4} {local.strftime('%a')} {local.day:>2} {local.strftime('%b %H:%M')}  "
              f"{alert.severity.upper() if alert.severity == 'high' else alert.severity:<8} {alert.title}{late}{status}")
    print(f"`kairu alerts show {shown[0].id}` for the details; `kairu alerts dismiss {shown[0].id}` when done.")
    return 0


def _protect(args, cfg) -> int:
    command = args.protect_command
    if command == "status":
        return _protect_status(cfg)
    if command == "start":
        _start_watch(cfg, say=True)
        return 0
    if command in ("pause", "resume"):
        problem = _act(cfg, f"protect.{command}", {"source": args.source})
        if problem:
            print(f"Not {'paused' if command == 'pause' else 'resumed'}: {problem}")
            return 1
        what = "everything" if args.source == "all" else args.source
        if command == "pause":
            print(f"Paused: {what} is not watched until `kairu protect resume{'' if args.source == 'all' else ' ' + args.source}`. "
                  "`kairu protect status` shows it as Paused.")
        else:
            print(f"Watching {what} again.")
            _start_watch(cfg)
        return 0
    if command == "connect-gmail":
        return _connect_gmail(args, cfg)
    if command in ("setup-pc", "add-folder", "remove-folder"):
        return _watch_pc(args, cfg)
    problem = _act(cfg, "protect.disconnect_email")
    if problem:
        print(f"Not disconnected: {problem}")
        return 1
    print(f"Gmail: {(_protect_store(cfg).source('gmail') or {}).get('detail', 'disconnected')}.")
    return 0


def _watch_pc(args, cfg) -> int:
    from pathlib import Path
    from kairu.protect import folders
    command = args.protect_command
    if command == "remove-folder":
        target = str(Path(args.folder).expanduser().resolve())
        watched = folders.approved(_protect_store(cfg))
        target = next((path for path in watched if path.lower() == target.lower()), target)
        problem = _act(cfg, "protect.remove_folder", {"folder": target})
        print(f"Not removed: {problem}" if problem else f"Kairu no longer watches {target}.")
        return 1 if problem else 0
    chosen = getattr(args, "folder", None) or (str(folders.downloads_folder()) if command == "setup-pc" else "")
    try:
        folder = folders.fence(chosen, cfg.data_dir)  # checked here first, so a refused folder asks for no PIN
    except folders.FolderProblem as problem:
        print(f"Not watched: {problem}.")
        return 1
    if command == "add-folder":
        print(f"Kairu asks Guardian to watch {folder}, read-only: it sees file names, sizes and times, and never opens, "
              "runs, moves or deletes a file.")
        problem = _act(cfg, "protect.add_folder", {"folder": folder}, high=True)
    else:
        security = sys.platform == "win32"
        print("Kairu asks Guardian to watch this PC, read-only:")
        print(f"  - {folder}: new programs and disguised files (names, sizes and times only; files are never opened)")
        print("  - devices: a USB or other device this PC has never seen")
        print("  - Windows Security: the firewall or the antivirus turned off" if security
              else "  - (Windows Security: Windows only, so not on this PC)")
        problem = _act(cfg, "protect.watch_pc", {"folder": folder, "devices": True, "security": security}, high=True)
    if problem:
        print(f"Not watched: {problem}")
        return 1
    print("Done. The first check only learns what is already there, so there are no alerts for what you have now. "
          "`kairu protect status` shows each part.")
    _start_watch(cfg)
    return 0


def _connect_gmail(args, cfg) -> int:
    from pathlib import Path
    from kairu.protect import gmail
    from kairu.protect.store import ACTIVE
    path = Path(args.client_file).expanduser().resolve()
    try:
        gmail.read_client(str(path))  # a quick look first, so a wrong file is caught before you approve anything
    except gmail.ConnectError as error:
        print(f"Not connected: {error}")
        return 1
    print("Kairu asks Guardian to connect your Gmail with read-only access: it can read emails, and cannot send, "
          "delete, move or mark them.")
    store, shown = _protect_store(cfg), []

    def show_link():
        import webbrowser
        detail = (store.source("gmail") or {}).get("detail", "")
        if detail.startswith(gmail.AUTH_URL) and not shown:
            shown.append(detail)
            print("Your browser opens Google's own sign-in page: sign in there and allow read-only access. "
                  "If no browser opened, open this link yourself:")
            print(f"  {detail}")
            webbrowser.open(detail)  # from your terminal, so the browser is not part of Guardian's action

    problem = _act(cfg, "protect.connect_email", {"client_file": str(path)}, high=True,
                   seconds=gmail.SIGN_IN_SECONDS + 30, while_waiting=show_link)
    source = store.source("gmail") or {}
    if problem or source.get("state") != ACTIVE:
        print(f"Not connected: {source.get('detail') if source.get('detail', '').startswith('not connected') else problem}")
        return 1
    print(f"Gmail {source['detail']}. Guardian's monitors check new emails every few minutes; alerts appear in "
          "the tray and in `kairu alerts`.")
    _start_watch(cfg)
    return 0


def _protect_status(cfg) -> int:
    from kairu import channel
    from kairu.client import GuardianClient, unavailable
    from kairu.protect.store import parse_iso
    from kairu.protect.watch import LAST_WATCHED
    store = _protect_store(cfg)
    try:
        running = [run for run in GuardianClient(cfg, start_if_down=False).status()["running"]
                   if run["action"] == "protect.watch"]
        last = parse_iso(store.setting(LAST_WATCHED))
        stale = last is not None and time.time() - last.timestamp() > 3 * cfg.protect_check_seconds + 60
        monitors = (f"running inside Guardian (process {running[0]['pid']}); last round {_ago(last)}"
                    + (" (Stale: they should have checked by now)" if stale else "")) if running else \
            "not running (they start when there is something to watch; `kairu protect start`)"
    except channel.ChannelError as error:
        monitors = f"not running: {unavailable(error)}"
    print("Kairu protection")
    print(f"  monitors:  {monitors}")
    from kairu.protect import folders as protect_folders
    sources = store.sources()
    set_up = {"folders": bool(protect_folders.approved(store)), "devices": store.setting("devices:on") == "1",
              "security": store.setting("security:on") == "1"}
    how = {"gmail": " (`kairu protect connect-gmail`, see PROTECTION.md)", "deadlines": " (`kairu deadline add`)",
           "folders": " (`kairu protect setup-pc`)", "devices": " (`kairu protect setup-pc`)",
           "security": " (`kairu protect setup-pc`)"}
    for name in ("gmail", "deadlines", "folders", "devices", "security"):
        info = sources.get(name)
        if not set_up.get(name, True) or (info is None and name not in set_up):
            print(f"  {name + ':':<10} Not set up{how[name]}")
            continue
        if info is None:  # approved, but the monitors have not looked yet
            print(f"  {name + ':':<10} Starting: the first check comes within a minute")
            continue
        checked = f"; checked {_ago(info['last_checked'])}" if info["last_checked"] else ""
        detail = info["detail"] if not info["detail"].startswith("https://") else "waiting for Google's sign-in"
        print(f"  {name + ':':<10} {info['state']}{': ' + detail if detail else ''}{checked}")
    new = store.count_new()
    print(f"  alerts:    {new} new" + (" (`kairu alerts`)" if new else ""))
    print(f"  automatic: {'on' if cfg.protect_enabled else 'off'} (protect.enabled in config.yaml: Guardian starts "
          "the monitors by itself)")
    return 0


def _deadline(args, cfg) -> int:
    from kairu.protect import deadlines
    store = _protect_store(cfg)
    if args.deadline_command == "list":
        open_now = store.deadlines()
        if not open_now:
            print("No open deadlines. `kairu deadline add \"Hackathon submission\" 2026-11-05 18:00` adds one.")
            return 0
        print(f"Open deadlines ({len(open_now)}), soonest first:")
        for item in open_now:
            where = "yours" if item["origin"] == "you" else "from an email"
            print(f"  #{item['id']:<4} {_when(item['due']):<28} {item['title']}  ({where})")
        return 0
    if args.deadline_command == "remove":
        if not any(item["id"] == args.number for item in store.deadlines()):
            print(f"There is no open deadline {args.number}.")
            return 1
        problem = _act(cfg, "deadline.remove", {"deadline": args.number})
        print(f"Not removed: {problem}" if problem else f"Deadline {args.number} removed: no more reminders for it.")
        return 1 if problem else 0
    try:
        due = deadlines.parse_when(args.date, args.time)
    except deadlines.DateNotUnderstood as error:
        print(f"Not added: {error}.")
        return 1
    if due <= deadlines.local_now():
        print(f"Not added: {_when(due)} has already passed.")
        return 1
    before = {item["id"] for item in store.deadlines()}
    problem = _act(cfg, "deadline.add", {"title": args.title, "due": due.isoformat(timespec="minutes"), "note": args.note})
    if problem:
        print(f"Not added: {problem}")
        return 1
    added = [item for item in store.deadlines() if item["id"] not in before]
    number = f" {added[0]['id']}" if added else ""
    print(f"Added deadline{number}: {' '.join(args.title.split())}, due {_when(due)} ({deadlines.describe_due(due)}).")
    print("Reminders come 3 days, 1 day and 3 hours before; `kairu deadline remove" + number + "` once it is done.")
    _start_watch(cfg)
    return 0


# --- Kairu Link and Mission Mode (Phase C) ------------------------------------------------------------

def _clock(moment: float | None) -> str:
    if not moment:
        return "never"
    local = datetime.fromtimestamp(moment).astimezone()
    return f"{local.day} {local.strftime('%b %H:%M')}"


def _device(args, cfg) -> int:
    from kairu.link import store as link_store
    if args.device_command == "pair":
        return _device_pair(cfg)
    if args.device_command == "remove":
        known = link_store.find(cfg.data_dir, args.device)
        if known is None:
            print(f"There is no paired device {args.device}. `kairu device list` shows them.")
            return 1
        problem = _act(cfg, "device.remove", {"device": args.device})
        if problem:
            print(f"Not removed: {problem}")
            return 1
        print(f"Removed {known.name} ({known.id}): every message from it is refused from now on.")
        return 0
    devices = link_store.paired(cfg.data_dir)
    if not devices:
        print("No device is paired. `kairu device pair` pairs your phone.")
        return 0
    print(f"Paired devices ({len(devices)}):")
    for device in devices:
        print(f"  {device.id}  {device.name:<20}  paired {_clock(device.paired_at)}, last message {_clock(device.last_seen)}")
    print("`kairu device remove ID` unpairs one.")
    return 0


def _device_pair(cfg, team_name: str = "") -> int:
    from kairu import approval, channel
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Refused, Verdict
    from kairu.link import kinds as link_kinds, store as link_store
    guardian, action = GuardianClient(cfg), Action("device.pair")
    print("Pairing lets one device, your phone, send this PC requests through the Gate. Guardian decides every "
          "request; High ones still need \"yes\" and your PIN at this PC, and Critical ones are always refused.")
    decision = guardian.check(action)
    if decision.verdict is Verdict.DENY:
        print(f"Guardian refused device.pair: {decision.reason}")
        return 1
    granted = approval.ask(guardian, decision) if decision.verdict is Verdict.NEEDS_APPROVAL else None
    if decision.verdict is Verdict.NEEDS_APPROVAL and granted is None:
        return 1
    before, run = {device.id for device in link_store.paired(cfg.data_dir)}, None
    try:
        run = guardian.run(action, granted)
        shown, deadline = False, time.monotonic() + link_kinds.PAIR_SECONDS + 30
        while (outcome := guardian.run_status(run["run"])["outcome"]) is None and time.monotonic() < deadline:
            offer = None if shown else link_store.read_offer(cfg.data_dir)
            if offer:
                _show_offer(offer, team_name)
                shown = True
            time.sleep(0.3)
    except KeyboardInterrupt:
        try:
            if run:
                guardian.end(run["run"])
        except Refused:
            pass
        print("Pairing cancelled.")
        return 1
    except (Refused, channel.ChannelError) as error:
        print(f"Not paired: {error}")
        return 1
    new = [device for device in link_store.paired(cfg.data_dir) if device.id not in before]
    if outcome == "finished" and new:
        print(f"Paired: {new[0].name} ({new[0].id}). It has its own keys and its own Gate topic.")
        if not cfg.link_enabled:
            print("link.enabled is false in config.yaml, so Kairu does not read its messages yet; set it to true and "
                  "restart Guardian.")
        return 0
    print(f"Not paired ({outcome or 'no answer'}): the 10 minutes passed, the code was wrong 5 times, or the Gate could "
          f"not be reached. Guardian's log ({cfg.data_dir / 'guardian.log'}) says which.")
    return 1


def _show_offer(offer: dict, team_name: str = "") -> None:
    if team_name:  # Clones (TEAM.md): `kairu team join`, the line the manager types on Main Kairu
        print(f"\nOn Main Kairu's PC, type this (then \"yes\" and the manager's PIN there):\n\n"
              f"  kairu team add {team_name if ' ' not in team_name else repr(team_name)} \"{offer['text']}\" {offer['code']}\n")
        print(f"The code is valid until {datetime.fromtimestamp(offer['expires']).strftime('%H:%M')}; send it to the manager "
              "yourself (chat or in person). Waiting for Main Kairu ... (Ctrl+C cancels)", flush=True)
        return
    import segno
    print("\nScan this with the Kairu phone app (Phase D). Until then, the stand-in phone takes the text below it:")
    try:
        segno.make(offer["text"], error="m").terminal(compact=True, border=2)
    except (OSError, UnicodeError):
        print("  (this terminal cannot draw the QR code)")
    print(f"\n  kairu-link-test pair \"{offer['text']}\" {offer['code']}\n")
    print(f"Code: {offer['code'][:3]} {offer['code'][3:]}   (not in the QR code; valid until "
          f"{datetime.fromtimestamp(offer['expires']).strftime('%H:%M')}; 5 wrong codes cancel the pairing)")
    print("Waiting for the phone ... (Ctrl+C cancels)", flush=True)


def _link(args, cfg) -> int:
    from kairu import approval, channel
    from kairu.client import GuardianClient, unavailable
    from kairu.guardian import Refused
    from kairu.link import store as link_store
    command, guardian = args.link_command, GuardianClient(cfg)
    if command == "send":
        problem = _act(cfg, "link.send", {"device": args.device, "type": args.type, "text": args.text})
        print(f"Not sent: {problem}" if problem else f"Sent to {args.device} through the Gate.")
        return 1 if problem else 0
    if command == "status":
        devices = link_store.paired(cfg.data_dir)
        try:
            state = guardian.status()
            receiving = [run for run in state["running"] if run["action"] == "link.receive"]
            receiver = (f"running inside Guardian (process {receiving[0]['pid']})" if receiving
                        else "not running (it runs while link.enabled is true and a device is paired, outside Safe Mode)")
            waiting = state.get("phone_waiting", 0)
        except channel.ChannelError as error:
            receiver, waiting = f"not running: {unavailable(error)}", 0
        print("Kairu Link")
        print(f"  Gate:      {cfg.link_relay} ({'on' if cfg.link_enabled else 'off: link.enabled is false in config.yaml'})")
        print(f"  receiver:  {receiver}")
        print(f"  devices:   {len(devices)} paired" + (" (`kairu device list`)" if devices else " (`kairu device pair`)"))
        print(f"  waiting:   {waiting} request{'s' if waiting != 1 else ''} from your phone" +
              (" (`kairu link waiting`)" if waiting else ""))
        return 0
    try:
        waiting = guardian.link_waiting()
    except Refused as refusal:
        print(f"Kairu cannot tell: {refusal}")
        return 1
    if command == "waiting":
        if not waiting:
            print("No request from your phone is waiting.")
            return 0
        for entry in waiting:
            _show_phone_request(entry)
        print("`kairu link approve N` (\"yes\" and your PIN) runs one; `kairu link refuse N` refuses it.")
        return 0
    entry = next((entry for entry in waiting if entry["number"] == args.number), None)
    if entry is None:
        print(f"No request {args.number} from your phone is waiting (they end after 10 minutes).")
        return 1
    if command == "refuse":
        guardian.link_refuse(args.number)
        print(f"Refused: {entry['action']} does not run, and your phone is told.")
        return 0
    print("\nGuardian: your phone asks for this action, and it needs your approval (High tier).")
    _show_phone_request(entry)
    print("  The words came from your phone: approve only what you yourself asked for.")
    answer = approval.read_answer(input, 'Type "yes" to approve, anything else to refuse: ')
    secret = approval.read_answer(getpass.getpass, "Your Kairu PIN: ") if answer.strip().lower() == "yes" else ""
    try:
        started = guardian.link_approve(args.number, answer, secret)
    except Refused as refusal:
        print(f"Refused: {refusal}")
        return 1
    if started.get("step"):  # a step of the device's own order: its task core goes on with it now
        print(f"Approved: {entry['action']}. The order it belongs to goes on with this step now.")
        return 0
    print(f"Approved: {entry['action']} " + (f"started (run {started['run']})." if started.get("run") else
                                             "was allowed, but Kairu has no code for it, so nothing ran."))
    return 0


def _show_phone_request(entry: dict) -> None:
    print(f"  #{entry['number']}  {entry['action']}  from {entry['name']} ({entry['device']}), "
          f"{max(0, entry['seconds_left']) // 60} min left")
    print(f"       what:    {entry['description']}")
    for key, value in entry["details"].items():
        print(f"       {key + ':':<8} {value!r}")


def _mission_mode(args, cfg) -> int:
    from kairu import channel, mission
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Refused
    guardian = GuardianClient(cfg)
    try:
        running = [run for run in guardian.status()["running"] if run["action"] == "mission_mode.on"]
    except channel.ChannelError:
        running = None  # Guardian is not running
    if args.switch == "status":
        return _mission_status(cfg, running)
    if args.switch == "off":
        if running:
            try:
                guardian.end(running[0]["run"])
            except Refused:
                pass  # it had just ended
            for _ in range(50):  # Guardian puts the setting back as the action ends
                if mission.saved(cfg.data_dir) is None:
                    break
                time.sleep(0.1)
        if mission.saved(cfg.data_dir) is not None:
            try:
                print(f"Mission Mode is off: {mission.restore(cfg.data_dir)}.")
            except mission.MissionError as error:
                print(f"Mission Mode is off, but {error}. Guardian tries again when it starts.")
                return 1
            return 0
        print("Mission Mode is off; the lid setting is yours again." if running else "Mission Mode was not on.")
        return 0
    if running:
        print("Mission Mode is already on. `kairu mission-mode off` ends it.")
        return 0
    pc = mission.power()
    if pc is None:
        print("Not started: Mission Mode is for Windows.")
        return 1
    if pc.on_mains() is not True:
        print("Not started: plug the PC in first. Mission Mode runs only while it is charging.")
        return 1
    print("Mission Mode keeps this PC awake with the lid closed, only while it charges: \"When I close the lid\" "
          "becomes \"Do nothing\" on mains power, and is always put back when Mission Mode ends.")
    problem = _act_and_leave(cfg, Action("mission_mode.on"), until=lambda: mission.saved(cfg.data_dir) is not None)
    if problem:
        print(f"Not started: {problem}")
        return 1
    print(f"Mission Mode is on. It ends by itself after {cfg.mission_max_hours:g} hours, when the PC is unplugged, at "
          f"{cfg.mission_max_celsius:g} °C where Windows gives a temperature, or when the processor stays above "
          f"{cfg.mission_cpu_percent:g}% for {cfg.mission_cpu_minutes:g} minutes. `kairu mission-mode off` ends it now.")
    return 0


def _act_and_leave(cfg, action, until, seconds: float = 15) -> str:
    """High: show, "yes" and PIN, then start the action and leave it running once until() is true. "" if so."""
    from kairu import approval, channel
    from kairu.client import GuardianClient
    from kairu.guardian import Refused, Verdict
    guardian = GuardianClient(cfg)
    decision = guardian.check(action)
    if decision.verdict is Verdict.DENY:
        return f"Guardian refused {action.name}: {decision.reason}"
    granted = approval.ask(guardian, decision) if decision.verdict is Verdict.NEEDS_APPROVAL else None
    if decision.verdict is Verdict.NEEDS_APPROVAL and granted is None:
        return "not approved, so nothing was done"
    try:
        run = guardian.run(action, granted)
        deadline = time.monotonic() + seconds
        while not until():
            outcome = guardian.run_status(run["run"])["outcome"]
            if outcome is not None:
                return f"{action.name} {outcome}; Guardian's log ({cfg.data_dir / 'guardian.log'}) says why"
            if time.monotonic() > deadline:
                return f"{action.name} did not start within {seconds:g} s"
            time.sleep(0.2)
    except (Refused, channel.ChannelError) as error:
        return str(error)
    return ""


def _mission_status(cfg, running) -> int:
    from kairu import mission
    saved, last, pc = mission.saved(cfg.data_dir), mission.last_ending(cfg.data_dir), mission.power()
    if running:
        state = "ON, inside Guardian (process {})".format(running[0]["pid"])
    elif saved is not None:
        state = "not running, but the lid setting is still changed: `kairu mission-mode off` puts it back"
    else:
        state = "off" if running is not None else "off (Guardian is not running)"
    print("Mission Mode")
    print(f"  state:     {state}")
    if saved:
        print(f"  lid:       \"Do nothing\" on mains power; yours, \"{mission.LID_ACTIONS.get(saved.get('lid_ac'), '?')}\", "
              f"comes back when it ends (since {_clock(saved.get('since'))})")
    if pc is not None:
        mains = {True: "plugged in", False: "on battery", None: "unknown"}[pc.on_mains()]
        heat = pc.celsius()
        print(f"  power:     {mains}; temperature: {f'{heat:.0f} °C' if heat is not None else 'Windows gives none on this PC'}")
    print(f"  limits:    {cfg.mission_max_hours:g} h; {cfg.mission_max_celsius:g} °C; processor above "
          f"{cfg.mission_cpu_percent:g}% for {cfg.mission_cpu_minutes:g} min")
    if last:
        detail = f" ({last['detail']})" if last.get("detail") else ""
        print(f"  last time: ended {_clock(last.get('at'))}: {mission.ENDINGS.get(last.get('reason'), '?')}{detail}")
    return 0


# --- Kairu's brain and Mission Cards (Phase B) ---------------------------------------------------------

ANSWER_SECONDS = 150  # a question gets this long, providers switching included


def _brain_summary(cfg) -> str:
    """One line for `kairu status`. Reads only."""
    from kairu.brain import keys
    from kairu.missions import store as missions
    ready = [name for name in cfg.brain_providers if keys.has(cfg.data_dir, name)]
    open_cards = [card for card in missions.summary(cfg.data_dir) if card["status"] in missions.OPEN]
    return (f"providers {', '.join(ready) if ready else 'none set up (`kairu provider add groq`)'}; "
            f"{'public questions go to the cloud without asking (option A)' if cfg.brain_public_to_cloud else 'every cloud send waits for your PIN'}; "
            f"{len(open_cards)} open mission{'s' if len(open_cards) != 1 else ''}")


def _brain_run(cfg, guardian, action, ask: str, approval=None, seconds: float = ANSWER_SECONDS):
    """Ask Guardian to run a brain action and read its answer: (answer, "") or (None, why not)."""
    from kairu import channel
    from kairu.brain.store import BrainStore
    from kairu.guardian import Refused
    run = None
    try:
        run = guardian.run(action, approval)
        deadline = time.monotonic() + seconds
        while (outcome := guardian.run_status(run["run"])["outcome"]) is None:
            if time.monotonic() > deadline:
                guardian.end(run["run"])
                return None, f"no answer within {seconds:g} s, so Kairu stopped waiting"
            time.sleep(0.1)
    except KeyboardInterrupt:
        try:
            if run:
                guardian.end(run["run"])
        except (Refused, channel.ChannelError):
            pass
        return None, "cancelled"
    except Refused as refusal:
        return None, f"Guardian refused {action.name}: {refusal}"
    except channel.ChannelError as error:
        return None, str(error)
    if outcome != "finished":
        return None, f"{action.name} {outcome}; Guardian's log ({cfg.data_dir / 'guardian.log'}) says why"
    answer = BrainStore(cfg.data_dir).take_answer(ask)
    return (answer, "") if answer else (None, f"the brain gave no answer; Guardian's log ({cfg.data_dir / 'guardian.log'}) "
                                              "says why")


def _show_answer(answer) -> None:
    from kairu.brain.providers import PROVIDERS
    print(answer.text)
    if answer.level == "L0":
        where = "L0: answered on this PC, nothing sent"
    elif answer.level == "L4":
        where = "L4: team mode comes with Phase G"
    elif answer.status == "answered":
        label = PROVIDERS[answer.provider].label if answer.provider in PROVIDERS else answer.provider
        where = f"L3: {label}, {answer.seconds:.1f} s" + (f"; {answer.note}" if answer.note else "")
    else:
        where = "L3: nothing was sent"
    print(f"  ({where})")


def _ask(args, cfg) -> int:
    import secrets
    from kairu.client import GuardianClient
    from kairu.guardian import Action
    question = " ".join(args.words).strip()
    if args.dry_run:
        return _ask_dry_run(cfg, question)
    guardian, ask = GuardianClient(cfg), secrets.token_hex(8)
    answer, problem = _brain_run(cfg, guardian, Action("brain.ask", {"question": question, "ask": ask, "source": "pc"}),
                                 ask)
    if problem:
        print(f"No answer: {problem}.")
        return 1
    if answer.status == "needs_approval":
        return _ask_approval(cfg, guardian, question, answer)
    _show_answer(answer)
    return 0 if answer.status == "answered" else 1


def _ask_approval(cfg, guardian, question: str, answer) -> int:
    """A personal question: the exact text and where it would go, then "yes" and your PIN, or nothing is sent."""
    import secrets
    from kairu import approval
    from kairu.brain.providers import PROVIDERS
    from kairu.guardian import Action, Verdict
    why = ", ".join(answer.reasons) or "personal data"
    if answer.provider not in PROVIDERS:
        print(f"Not sent: your question has {why}, and no free AI provider is set up yet (`kairu provider add groq`).")
        return 1
    provider = PROVIDERS[answer.provider]
    details = {"question": question, "provider": answer.provider, "ask": secrets.token_hex(8), "source": "pc"}
    if answer.search:
        details["search"] = answer.search
        print(f"Your question has {why}, so Kairu did not search for it or send it.")
        print("If you approve, Kairu searches the web once, on DuckDuckGo, for exactly these words (they leave this PC):")
        print(f"  | {answer.search}")
        print("It reads the top pages found (their addresses leave this PC), then sends what they say and exactly this "
              f"text, once, to {provider.label} ({provider.host}) and nowhere else:")
    else:
        print(f"Your question has {why}, so Kairu did not send it.")
        print(f"If you approve, Kairu sends exactly this text, once, to {provider.label} ({provider.host}) and nowhere else:")
    for line in question.splitlines() or [""]:
        print(f"  | {line}")
    action = Action("brain.send_private", details)
    decision = guardian.check(action)
    if decision.verdict is Verdict.DENY:
        print(f"Not sent: Guardian refused brain.send_private: {decision.reason}")
        return 1
    granted = approval.ask(guardian, decision) if decision.verdict is Verdict.NEEDS_APPROVAL else None
    if decision.verdict is Verdict.NEEDS_APPROVAL and granted is None:
        print("Not sent.")
        return 1
    sent, problem = _brain_run(cfg, guardian, action, details["ask"], granted)
    if problem:
        print(f"No answer: {problem}.")
        return 1
    _show_answer(sent)
    return 0 if sent.status == "answered" else 1


def _ask_dry_run(cfg, question: str) -> int:
    from kairu.brain import router
    from kairu.brain.gateway import Gateway
    from kairu.brain.providers import PROVIDERS
    from kairu.brain.store import BrainStore
    route = router.route(question, BrainStore(cfg.data_dir).context("pc"))
    what, state = router.LEVELS[route.level]
    print(f"Level: {route.level} ({what}; {state})")
    if route.kind == "rule":
        print(f"  A fixed rule on this PC answers it ({route.name}). Nothing is sent.")
    elif route.kind == "action":
        print(f"  A request to do something: Guardian decides it as {route.name}, by its tier. Nothing runs from a "
              "question.")
    elif route.kind == "team":
        print("  Team mode is not built yet (Phase G): Kairu says so. Nothing is sent.")
    elif route.kind == "memory":
        what = {"remember": "Guardian is asked to keep this line (memory.remember)", "recall": "It only reads",
                "forget": "Guardian is asked to delete the lines about these words (memory.forget)",
                "talks": "It only reads your talk history"}[route.name]
        print(f"  Kairu's memory, on this PC ({route.name}). {what}. Nothing is sent.")
    else:
        verdict = route.privacy
        first = Gateway(cfg.data_dir, cfg.brain_settings()).first_ready()
        where = f"{PROVIDERS[first].label} ({PROVIDERS[first].host})" if first in PROVIDERS else "no provider set up yet"
        if verdict.secret:
            print(f"  Privacy filter: SECRET ({verdict.why()}). Never sent, not even with your approval.")
        elif verdict.personal:
            print(f"  Privacy filter: personal ({verdict.why()}). It waits for your \"yes\" and PIN; then it goes to "
                  f"{where}.")
        elif not cfg.brain_public_to_cloud:
            print(f"  Privacy filter: public. brain.public_to_cloud is false, so it waits for your PIN; then {where}.")
        else:
            print(f"  Privacy filter: public. It goes to {where} without asking (option A).")
        if route.follow_up:
            print("  It follows the last answer, so the last question and answer go with it.")
        if route.deep and not verdict.secret and cfg.research_enabled and not verdict.personal:
            print("  Deep research: up to 3 searches (these words, and up to 2 more angles the AI names from them; all leave "
                  "this PC), up to 9 pages, then a short report with numbered sources:")
            print(f"    {route.query}")
        elif route.research and not verdict.secret:
            if cfg.research_enabled:
                print("  It needs fresh facts, so Guardian searches DuckDuckGo first, for these words (they leave this "
                      "PC), and reads the top pages:")
                print(f"    {route.query}")
            else:
                print("  It needs fresh facts, but web research is off (research.enabled in config.yaml), so the AI "
                      "answers from what it knows.")
    print("Nothing was sent (dry run).")
    return 0


def _bar(args, cfg) -> int:
    from pathlib import Path
    from kairu import client
    from kairu.autostart import AutostartError
    from kairu.bar import app, install
    config_file = args.config or kairu_config.config_path()
    data_dir = Path(cfg.data_dir)
    if args.bar_command == "install":
        try:
            print(f"The bar starts when you sign in (Task Scheduler task \"{install.install(data_dir, client.windowless_python(), config_file)}\").")
        except AutostartError as error:
            print(f"Not installed: {error}.")
            return 1
        return 0
    if args.bar_command == "uninstall":
        name = install.uninstall(data_dir)
        print(f"Removed the task \"{name}\"." if name else "There was no task to remove.")
        return 0
    if args.bar_command == "quit":
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / app.QUIT_FILE).write_text("", encoding="utf-8")
        print("The bar ends within a second or two, if it runs. Guardian and running actions carry on.")
        return 0
    python, environment = client.guardian_python()
    argv = [python, "-m", "kairu.bar.app", "--config", str(Path(config_file).resolve())] + ([] if args.hidden else ["--show"])
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / app.LOG_FILE, "ab") as log:
        process = client._spawn(argv, log, environment)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.1)
    if process.returncode == app.ALREADY_RUNNING:
        print(f"The bar is already running: Ctrl+Alt+{cfg.bar_key} shows and hides it.")
        return 0
    if process.returncode is not None:
        print(f"The bar did not start; {data_dir / app.LOG_FILE} says why.")
        return 1
    print(f"The bar is running: Ctrl+Alt+{cfg.bar_key} shows and hides it.")
    return 0


def _phone(args, cfg) -> int:
    """`kairu phone install | pair | connect | status` (PHONE.md): moving the app to the phone, nothing more."""
    from pathlib import Path
    from kairu import phone
    try:
        if args.phone_command == "pair":
            phone.pair(args.address, args.code)
            print("Paired. Now run `kairu phone connect <the address at the top of Wireless debugging>`.")
            return 0
        if args.phone_command == "connect":
            phone.connect(args.address)
            print("Connected. Now `kairu phone install`.")
            return 0
        if args.phone_command == "status":
            try:
                adb = phone.find_adb()
                found = phone.devices(adb)
                print(f"adb: {adb}")
                print(f"Phone: {found[0] if len(found) == 1 else (', '.join(found) or 'none connected')}")
            except phone.PhoneError as error:
                print(error)
            newest = phone.newest_app()
            print(f"Newest app file in Downloads: {newest.name if newest else 'none'}")
            return 0
        source = Path(args.file) if args.file else phone.newest_app()
        if source is None:
            print("No kairu-phone file in your Downloads. Download the newest 'kairu-phone' from GitHub "
                  "(Actions > Phone app > the newest run > Artifacts), then run this again.")
            return 1
        app = phone.app_from(source, Path(cfg.data_dir))
        print(f"Installing {app.name} …")
        serial = phone.install(app)
        print(f"Kairu is on your phone ({serial}). Open it from the app drawer.")
        return 0
    except phone.PhoneError as error:
        print(error)
        return 1


def _workspace(args, cfg) -> int:
    """`kairu workspace`: start the workspace program (or, if it runs, open one more window); quit; status."""
    from pathlib import Path
    from kairu.workspace import app
    config_file = args.config or kairu_config.config_path()
    data_dir = Path(cfg.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    state = app.read_state(data_dir)
    running = state is not None and app.call(state, "/api/ping") is not None
    if args.workspace_command == "quit":
        (data_dir / app.QUIT_FILE).write_text("", encoding="utf-8")
        print("The workspace ends within a second or two, if it runs. Guardian and running actions carry on.")
        return 0
    if args.workspace_command == "status":
        print(f"The workspace is running on 127.0.0.1:{state['port']}." if running else "The workspace is not running.")
        return 0
    started, said = app.open_or_start(cfg, config_file)
    if said == "The workspace is open.":
        said += " `kairu workspace` again opens one more window; `kairu workspace quit` ends it."
    print(said)
    return 0 if started else 1


TRY_LINE = "The capital of Japan is Tokyo. Want to know more about it?"


def _voice(args, cfg) -> int:
    """`kairu voice setup` and `kairu voice try` (you run them; never a Kairu action) and `kairu voice status`."""
    from kairu.voice import models
    if args.voice_command == "try":
        return _voice_try(args, cfg)
    if args.voice_command == "check":
        from kairu.voice import check
        return check.run(cfg, args.seconds)
    if args.voice_command == "enroll":
        from kairu.voice import myvoice
        if args.forget:
            print("Your voice print is deleted." if myvoice.forget(cfg.data_dir) else "There was no voice print.")
            return 0
        return myvoice.enroll(cfg)
    key = args.model if args.voice_command == "setup" and args.model else cfg.voice_model
    model = models.MODELS[key]
    whisper = models.WHISPERS.get(models.WHISPER_ENGINES.get(cfg.voice_engine, ""))  # None: the engine is Vosk
    unpinned = models.not_pinned(models.WHISPER_ENGINES[cfg.voice_engine]) if cfg.voice_engine in models.WHISPER_ENGINES else ""
    if args.voice_command == "setup" and unpinned and not args.model:
        print(f"Not set up: {unpinned}.")
        return 1
    if args.voice_command == "setup":
        try:
            if whisper and not args.model:  # the engine's own model; --model sets up a Vosk one
                print(f"Ready: Whisper {whisper.key} in {models.setup_whisper(cfg.data_dir, whisper.key)}.")
                # the fast lane (voice.fast_orders) and your-voice-only (voice.only_my_voice) hear beside Whisper
                print(f"Ready: {model.name} for fast orders in {models.setup(cfg.data_dir, key)}.")
                print(f"Ready: {models.SPEAKER.name} for your-voice-only in {models.setup_speaker(cfg.data_dir)}.")
            else:
                place = models.setup(cfg.data_dir, key)
                print(f"Ready: {model.name} ({model.language}) in {place}.")
            if sys.platform == "win32":  # Piper's build is for Windows; elsewhere there is no voice to set up
                print(f"Ready: Piper in {models.setup_piper(cfg.data_dir).parent}.")
                for voice in models.VOICES:  # all three, so the gate test can let you pick one
                    print(f"Ready: the voice {voice} in {models.setup_voice(cfg.data_dir, voice).parent}.")
                print(f"Ready: Kokoro in {models.setup_kokoro(cfg.data_dir)}.")
                if not models.kokoro_installed():
                    print("Kokoro needs its program's packages once: py -3.12 -m pip install -e .[kokoro]  "
                          "(until then Piper speaks).")
        except models.SetupError as error:
            print(f"Not set up: {error}.")
            return 1
        if key != cfg.voice_model or (args.model and cfg.voice_engine != "vosk"):
            print(f"To use it, set voice.engine: vosk and voice.model: {key} in config.yaml, then restart Guardian.")
        if not cfg.voice_enabled:
            print("Voice is still off: set voice.enabled: true in config.yaml, restart Guardian, then `kairu bar quit` and `kairu bar`.")
        return 0

    def state(check) -> str:
        try:
            return f"set up in {check()}"
        except models.NotSetUp:
            return "not set up (`kairu voice setup`)"
    from kairu.voice import mic
    blocked = mic.privacy_problem() if sys.platform == "win32" else "Windows only"
    voice = models.VOICES[cfg.voice_voice]
    print("Kairu voice")
    print(f"  voice:  {'on' if cfg.voice_enabled else 'off (voice.enabled: false in config.yaml)'}")
    if unpinned:
        print(f"  hears:  {cfg.voice_engine}: {unpinned}")
    elif whisper:
        print(f"  hears:  Whisper {whisper.key} (voice.engine: {cfg.voice_engine}, {whisper.mib:.1f} MiB): "
              f"{state(lambda: models.whisper_ready(cfg.data_dir, whisper.key))}")
    else:
        print(f"  hears:  Vosk (voice.engine: vosk), {key}, {model.name} ({model.language}, {model.mib:.1f} MiB): "
              f"{state(lambda: models.ready(cfg.data_dir, key))}")
    if whisper:
        from kairu.voice import myvoice
        print(f"  fast:   {'on' if cfg.voice_fast else 'off'} (voice.fast_orders), {model.name}: "
              f"{state(lambda: models.ready(cfg.data_dir, key))}")
        print(f"  mine:   {'on' if cfg.voice_only_mine else 'off'} (voice.only_my_voice), {models.SPEAKER.name}: "
              f"{state(lambda: models.speaker_ready(cfg.data_dir))}, voice print: "
              f"{'kept' if myvoice.load(cfg.data_dir) else 'none (`kairu voice enroll`)'}")
    print(f"  speaks: Piper {models.PIPER_RELEASE}: {state(lambda: models.piper_ready(cfg.data_dir).parent)}")
    print(f"          voice {cfg.voice_voice}, {voice.label}: {state(lambda: models.voice_ready(cfg.data_dir, cfg.voice_voice)[0])}")
    print(f"          style {cfg.voice_style} (voice.style; `kairu voice try` lets you hear each)")
    installed = "its packages installed" if models.kokoro_installed() else "packages not installed (pip install -e .[kokoro])"
    print(f"  kokoro: {'speaks (voice.tts: kokoro)' if cfg.voice_tts == 'kokoro' else 'off (voice.tts: piper)'}, "
          f"voice {cfg.voice_kokoro}: {state(lambda: models.kokoro_ready(cfg.data_dir)[0].parent)}, {installed}")
    print(f"  key:    Ctrl+Alt+{cfg.voice_key} starts listening; the mic button in the bar switches the mic on and off")
    print(f"  mic:    {blocked or 'Windows lets desktop apps use the microphone'}")
    return 0


def _voice_try(args, cfg) -> int:
    """Say one fixed line, so you can hear the voices and the styles and pick. It plays here, from this command, like
    `kairu voice setup` downloads: an owner command. Kairu's own answers are still only ever said by voice.speak."""
    from kairu.voice import models, speak
    tts = args.tts or cfg.voice_tts
    kokoro = tts == speak.KOKORO

    def say(voice: str, style: str):
        piper_voice = voice if voice in models.VOICES else cfg.voice_voice
        kokoro_voice = voice if voice in models.KOKORO_SPEAKERS else cfg.voice_kokoro
        return speak.main(TRY_LINE, str(cfg.data_dir), piper_voice, style, tts, kokoro_voice)

    if getattr(args, "voices", False):
        style = args.style or cfg.voice_style
        voices = {key: label for key, (label, _) in models.KOKORO_SPEAKERS.items()} if kokoro else \
            {key: voice.label for key, voice in models.VOICES.items()}
        yours = cfg.voice_kokoro if kokoro else cfg.voice_voice
        for number, (key, label) in enumerate(voices.items(), 1):
            print(f"{number:2}. {key}{' (yours now)' if key == yours else ''}: {label}", flush=True)
            if say(key, style) == speak.FAILED:
                print("    It could not be said: is it set up (`kairu voice setup`)?")
            time.sleep(0.6)
        setting = "kokoro_voice" if kokoro else "voice"
        print(f"To keep one: {setting}: <name> under voice: in config.yaml, then restart Guardian.")
        return 0
    styles = [args.style] if args.style else list(speak.STYLES) + [speak.PLAIN]
    voice = args.voice or (cfg.voice_kokoro if kokoro else cfg.voice_voice)
    for style in styles:
        print(f"{style}{' (the default)' if style == speak.DEFAULT_STYLE else ''}: {TRY_LINE}", flush=True)
        if say(voice, style) == speak.FAILED:
            print("It could not be said: is the voice set up (`kairu voice setup`)?")
            return 1
        time.sleep(0.6)
    print(f"To keep one: style: <style> under voice: in config.yaml (now: {cfg.voice_style}), then restart Guardian.")
    return 0


def _usage(args, cfg) -> int:
    from kairu.brain import usage
    for line in usage.report(cfg.data_dir, cfg.brain_settings()):
        print(line)
    return 0


def _provider(args, cfg) -> int:
    from kairu.brain import usage
    from kairu.brain.providers import PROVIDERS
    from kairu.brain.store import BrainStore
    command = args.provider_command
    if command == "list":
        store = BrainStore(cfg.data_dir)
        models = dict(cfg.brain_models)
        print("Free AI providers, in the order Kairu tries them (brain.providers in config.yaml):")
        for name in cfg.brain_providers:
            known = PROVIDERS[name]
            ready, words = usage.state(cfg.data_dir, name, store)
            print(f"  {known.label:<11} {words}")
            print(f"              model {models.get(name, known.model)}; free: {known.day_note}")
            print(f"              does not train on your prompts: {known.terms}")
        return 0
    known = PROVIDERS[args.name]
    if command == "add":
        return _provider_add(cfg, known)
    if command == "remove":
        problem = _act(cfg, "provider.remove", {"provider": known.name})
        print(f"Not removed: {problem}" if problem else f"Removed: {known.label}'s key is deleted from this PC.")
        return 1 if problem else 0
    minutes = 0 if command == "resume" else args.minutes
    problem = _act(cfg, "provider.pause", {"provider": known.name, "minutes": minutes})
    if problem:
        print(f"Not {'resumed' if command == 'resume' else 'paused'}: {problem}")
        return 1
    print(f"{known.label} is used again." if command == "resume" else
          f"{known.label} is paused for {minutes:g} minutes, as if at its free limit: Kairu switches to the next "
          f"provider. `kairu usage` shows it; `kairu provider resume {known.name}` ends it.")
    return 0


def _provider_add(cfg, known) -> int:
    from kairu import approval
    from kairu.brain import keys
    from kairu.brain.providers import ACCOUNT, valid_key
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Verdict
    print(f"Kairu saves your {known.label} key on this PC, sealed (on Windows with DPAPI, for your account only). It goes "
          f"only to {known.host}, and is never shown or written in a log.")
    print(f"  Free account and key: {known.signup}")
    print(f"  It does not train on your prompts: {known.terms}")
    account = ""
    if known.needs_account:
        account = approval.read_answer(input, "Your Cloudflare account ID (32 letters and digits; Workers AI page, or the "
                                              "dashboard's URL): ").strip().lower()
        if not ACCOUNT.fullmatch(account):
            print("Not saved: an account ID is 32 letters (a-f) and digits.")
            return 1
    guardian, action = GuardianClient(cfg), Action("provider.add", {"provider": known.name})
    decision = guardian.check(action)
    if decision.verdict is Verdict.DENY:
        print(f"Not saved: Guardian refused provider.add: {decision.reason}")
        return 1
    granted = approval.ask(guardian, decision) if decision.verdict is Verdict.NEEDS_APPROVAL else None
    if decision.verdict is Verdict.NEEDS_APPROVAL and granted is None:
        return 1
    key = approval.read_answer(getpass.getpass, f"Paste your {known.label} key (it is not shown): ").strip()
    problem = valid_key(known, key)
    if problem:
        print(f"Not saved: {problem}.")
        return 1
    if known.key_start and not key.startswith(known.key_start):
        print(f"(Note: {known.label} keys usually start with {known.key_start}; saving it anyway.)")
    keys.leave_pending(cfg.data_dir, known.name, key, account)
    try:
        problem = _act_approved(cfg, guardian, action, granted)
    finally:
        keys.pending_path(cfg.data_dir, known.name).unlink(missing_ok=True)  # if the action did not take it
    if problem:
        print(f"Not saved: {problem}")
        return 1
    print(f"Saved. {known.label} is ready: `kairu usage` shows it, and `kairu ask \"what is 2+2\"` tries the first "
          "provider that is ready.")
    return 0


def _act_approved(cfg, guardian, action, granted, seconds: float = 30) -> str:
    """Run an action that is already approved, and wait until it ends. "" if it finished."""
    from kairu import channel
    from kairu.guardian import Refused
    try:
        run = guardian.run(action, granted)
        deadline = time.monotonic() + seconds
        while (outcome := guardian.run_status(run["run"])["outcome"]) is None:
            if time.monotonic() > deadline:
                return f"{action.name} is still running after {seconds:g} s"
            time.sleep(0.1)
    except Refused as refusal:
        return f"Guardian refused {action.name}: {refusal}"
    except channel.ChannelError as error:
        return str(error)
    return "" if outcome == "finished" else f"{action.name} {outcome}; Guardian's log ({cfg.data_dir / 'guardian.log'}) says why"


def _mission(args, cfg) -> int:
    from pathlib import Path
    from kairu.missions import card as cards
    from kairu.missions.store import MissionStore
    command = args.mission_command
    if command == "example":
        if not args.file:
            print(cards.EXAMPLE, end="")
            return 0
        target = Path(args.file).expanduser()
        if target.exists():
            print(f"Not written: {target} already exists.")
            return 1
        target.write_text(cards.EXAMPLE, encoding="utf-8")
        print(f"Wrote an example card to {target}. Change it in Notepad, then `kairu mission new {args.file}`.")
        return 0
    store = MissionStore(cfg.data_dir)
    if command == "new":
        if bool(args.file) == bool(args.practice):
            print("Give a card file (`kairu mission example` shows one), or --practice.")
            return 1
        details = {"practice": True}
        if args.file:
            try:
                cards.read(args.file)  # a quick look first, so a mistake is shown before Guardian is asked
            except cards.CardProblem as problem:
                print(f"Not saved: {problem}.")
                return 1
            details = {"file": str(Path(args.file).expanduser().resolve())}
        before = {card.id for card in store.cards()}
        problem = _act(cfg, "mission.create", details)
        added = [card for card in store.cards() if card.id not in before]
        if problem or not added:
            print(f"Not saved: {problem or 'no card was added'}")
            return 1
        card = added[0]
        print(f"Mission {card.id} saved: {card.goal} ({len(card.steps)} steps). Guardian starts it within a few "
              f"seconds and saves a checkpoint after every step. `kairu mission show {card.id}` follows it.")
        return 0
    if command == "list":
        found = store.cards()
        if not found:
            print("No missions yet. `kairu mission new --practice` makes the practice one; `kairu mission example` "
                  "shows a card.")
            return 0
        print(f"Missions ({len(found)}):")
        for card in found:
            done, total = card.counts()
            print(f"  #{card.id:<4} {card.status:<8} {done}/{total} steps  {card.goal[:70]}"
                  + (f"  ({card.reason})" if card.reason else ""))
        return 0
    card = store.card(args.number)
    if card is None:
        print(f"There is no mission {args.number}.")
        return 1
    if command == "show":
        return _mission_show(card)
    if command == "stop":
        problem = _act(cfg, "mission.stop", {"card": card.id})
        print(f"Not stopped: {problem}" if problem else f"Mission {card.id} stopped; it keeps its last checkpoint. "
                                                         f"`kairu mission continue {card.id}` goes on from there.")
        return 1 if problem else 0
    if command == "remove":
        problem = _act(cfg, "mission.remove", {"card": card.id})
        print(f"Not removed: {problem}" if problem else f"Mission {card.id} removed.")
        return 1 if problem else 0
    return _mission_continue(cfg, card)


def _mission_show(card) -> int:
    from datetime import datetime
    done, total = card.counts()
    print(f"Mission {card.id}: {card.goal}")
    print(f"  status:    {card.status}" + (f" ({card.reason})" if card.reason else "") + f"; {done} of {total} steps")
    if card.deadline:
        print(f"  deadline:  {_when(datetime.fromisoformat(card.deadline))}")
    print(f"  report:    {dict(pc='the tray and here', phone='your phone', both='the tray and your phone')[card.report]}")
    for step in card.steps:
        what = f"ask: {step.text}" if step.kind == "ask" else f"wait: {step.text} s"
        tries = f", tried {step.tries} times" if step.tries > 1 else ""
        state = "cut off" if step.status == "running" and card.status != "running" else step.status
        print(f"  {step.number:>2}. [{state}{tries}] {what}")
        if step.status == "waiting":
            print(f"        waits for your approval: it has {', '.join(step.waiting_for.get('reasons', [])) or 'personal data'}")
        elif step.result and step.kind == "ask":
            for line in step.result.splitlines():
                print(f"        {line}")
        elif step.note and step.status == "failed":
            print(f"        {step.note}")
    if card.done:
        print("  your checklist: " + "; ".join(card.done))
    return 0


def _mission_continue(cfg, card) -> int:
    """Approve, together, the steps that wait for you (each with "yes" and your PIN); then go on from the checkpoint."""
    from kairu import approval
    from kairu.brain.providers import PROVIDERS
    from kairu.client import GuardianClient
    from kairu.guardian import Action, Verdict
    if card.status not in ("stopped", "waiting", "failed"):
        print(f"Mission {card.id} is {card.status}: there is nothing to continue.")
        return 1
    waiting = [step for step in card.steps if step.status == "waiting"]
    skip = False
    if waiting:
        guardian = GuardianClient(cfg)
        print(f"{'These' if len(waiting) != 1 else 'This'} {len(waiting)} question{'s' if len(waiting) != 1 else ''} of "
              f"mission {card.id} {'have' if len(waiting) != 1 else 'has'} personal data, so Kairu did not send "
              f"{'them' if len(waiting) != 1 else 'it'}:")
        for step in waiting:
            where = step.waiting_for.get("provider", "")
            print(f"  {step.number}. {step.text}")
            print(f"     has {', '.join(step.waiting_for.get('reasons', [])) or 'personal data'}; would go to "
                  f"{PROVIDERS[where].label + ' (' + PROVIDERS[where].host + ')' if where in PROVIDERS else 'no provider set up'}")
            if step.waiting_for.get("search"):
                print(f"     and first to DuckDuckGo, as a search for: {step.waiting_for['search']}")
        print("For each one: approve it (\"yes\" and your PIN) to send it, or refuse it to skip that step.")
        for step in waiting:
            where = step.waiting_for.get("provider", "")
            if where not in PROVIDERS:
                skip = True
                continue
            details = {"question": step.text, "provider": where, "ask": step.ask, "source": f"mission:{card.id}"}
            if step.waiting_for.get("search"):
                details["search"] = step.waiting_for["search"]
            action = Action("brain.send_private", details)
            decision = guardian.check(action)
            granted = approval.ask(guardian, decision) if decision.verdict is Verdict.NEEDS_APPROVAL else None
            if granted is None:
                print(f"  Step {step.number} is skipped.")
                skip = True
                continue
            problem = _act_approved(cfg, guardian, action, granted, seconds=ANSWER_SECONDS)
            print(f"  Step {step.number}: {'sent' if not problem else problem}.")
    problem = _act(cfg, "mission.continue", {"card": card.id, "skip": skip})
    if problem:
        print(f"Not continued: {problem}")
        return 1
    print(f"Mission {card.id} goes on from its last checkpoint: steps that finished are not done again. "
          f"`kairu mission show {card.id}` follows it.")
    return 0


def _shadow(args, cfg) -> int:
    from kairu.shadow import commands
    return commands.shadow(args, cfg)


def _doctor(args, cfg) -> int:
    from kairu.doctor import report
    print("\n".join(report(cfg)))
    return 0


def _details(args, cfg) -> int:
    """`kairu details`: an owner command typed in PowerShell, never a Kairu action (ADR-054). On this PC only; a secret is
    never kept."""
    from kairu.tasks import details
    try:
        if args.details_command == "show":
            print(details.shown(cfg.data_dir))
        elif args.details_command == "set":
            key = details.key_of(args.key)
            if key is None:
                raise details.DetailProblem(f"Kairu keeps only these details: {', '.join(details.KEYS)}, and a username.")
            print(details.keep(cfg.data_dir, key, " ".join(args.value), args.site))
        else:
            key = details.key_of(args.key)
            if key is None:
                raise details.DetailProblem(f"Kairu keeps only these details: {', '.join(details.KEYS)}, and a username.")
            print(details.forget(cfg.data_dir, key, args.site))
    except details.DetailProblem as why:
        print(f"kairu: {why}", file=sys.stderr)
        return 1
    return 0


def _team(args, cfg) -> int:
    from kairu.team import commands
    return commands.team(args, cfg)


def _pack(args, cfg) -> int:
    from kairu.shadow import commands
    return commands.pack(args, cfg)


COMMANDS = {"guardian": _guardian, "status": _status, "resume": _resume, "pin": _pin, "request": _request,
            "audit": _audit, "demo": _demo, "hotkey": _hotkey, "alerts": _alerts, "protect": _protect,
            "deadline": _deadline, "device": _device, "link": _link, "mission-mode": _mission_mode,
            "ask": _ask, "usage": _usage, "provider": _provider, "mission": _mission, "bar": _bar, "voice": _voice, "workspace": _workspace, "phone": _phone,
            "shadow": _shadow, "pack": _pack, "team": _team, "doctor": _doctor, "details": _details}
