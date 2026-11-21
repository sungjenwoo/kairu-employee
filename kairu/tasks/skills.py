"""The skill registry: every PC skill Kairu has, with its policy action, its executor and the exact orders it answers.

The registry never decides anything: Guardian decides each step by policy.yaml. It only refuses, at load, a skill that
must not exist: one whose action is missing from the policy, or is Critical. There is no Critical skill, and a test
proves that one would be refused. A skill's code is named here and in kairu/executors.py, and a test checks they agree.
"""

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from kairu.policy import Rule, Tier
from kairu.tasks import ask_ai, web
from kairu.tasks import details as my_details
from kairu.tasks import screen as screen_names

I = re.IGNORECASE
LEVEL = r"(?P<setting>\d{1,3})(?: ?%| percent)?"
UP_DOWN = r"(?P<setting>up|down)"
APP = r"(?P<name>[^\\/:*?\"<>|&;%$`]+?)"  # a name, never a path or a command line
THE = r"(?:the )?"
Q = r"[\"'“”]?"  # a name may be in quotes
FILE = r"(?P<name>.+?(?:\*[^ ]*|\.[A-Za-z0-9]{1,8}))"  # a file name with its extension, or a pattern such as *.pdf
FOLDER = r"(?P<to>[^\"“”]+?)"
WORD = r"(?!(?:of|for|to|near|about|in|on|at|with|from|out|how|what|where|why|who|when|a|an|someone|somebody)\b)[\w.*?-]+"
FIND_WHAT = rf"(?P<what>{WORD}(?: {WORD}){{0,2}})"
WHEN = r"(?: (?:from|made|changed|modified|saved|added) (?P<when>today|yesterday|this week|last week))?"
IN_THE_FOLDER = r"(?: in (?:the |my )?(?:work folder|kairu-files))?"
SITE = "|".join(re.escape(name) for name in sorted(web.SITES, key=len, reverse=True))
URL = rf"(?P<url>{SITE}|{web.DOMAIN.pattern}|[a-z][a-z0-9+.-]+:\S*)"
SEARCH_FOR = r"(?P<query>.+?)"
NAMED = r"(?P<name>[^\"“”*?]+?)"  # one file or folder in the work folder, never a pattern
# Kairu's hands (kairu/tasks/screen.py): which app, which bar, which words, which keys, which button
APPN = r"(?P<app>(?!(?:in|on|of|the|a|an|it|into)\b)[^\\/:*?\"<>|&;%$`,]+?)"
IN_APP = rf"(?: (?:in|on|of|inside) {THE}{APPN}(?: app| window| browser)?)?"
FIELD_WORDS = (r"(?P<field>(?:google |chrome's |edge's |the |its |a )?(?:search ?bar|search ?box|search ?field|search|address ?bar|"
               r"url ?bar|url|location ?bar|omnibox|address))")
OF_APP = rf"(?: (?:of|in|on) {THE}{APPN}(?: app| window| browser)?)?"
TEXT = r"[\"'“”‘’]?(?P<text>.+?)[\"'“”‘’]?"
TYPE_VERB = r"(?:type|write|enter)(?! (?:me )?(?:a |an |the )?(?:new )?(?:text |note |notes )?file\b)"
KEY_WORDS = (r"(?P<keys>(?:(?:ctrl|control|shift|alt|win|windows)(?: ?\+ ?| ))*(?:enter|return|tab|esc|escape|space(?:bar)?|backspace|back space|"
             r"delete|del|insert|home|end|page ?up|page ?down|(?:up|down|left|right)(?: arrow)?|arrow (?:up|down|left|right)|"
             r"f1[0-2]|f[1-9]|plus|minus|windows|win|[a-z0-9]))")
TARGET = r"[\"'“”]?(?P<target>[^\"“”]+?)[\"'“”]?"
OPEN_KINDS = "txt|md|csv|json|pdf|docx?|xlsx?|pptx?|odt|ods|odp|rtf|png|jpe?g|gif|bmp|webp|mp3|wav|m4a|mp4|mkv|mov"  # "open notes.txt"
# PC4, the rest (kairu/tasks/screen.py): File Explorer's own folders, apps Kairu knows by name, and "it"
EXPLORER = r"(?:the )?(?:file explorer|windows explorer|explorer)"
KNOWN_FOLDER = r"(?:my )?(?P<text>downloads?|documents|docs|desktop|pictures|photos|music|videos)"
KNOWN_APP = "|".join(re.escape(name) for name in sorted(screen_names.PROGRAM_NAMES, key=len, reverse=True))
READ_OUT = r"(?: to me| aloud| out loud| out)?"
IT = r"(?:it|this|that|this one|that one|this window|that window|this app|that app|here|there|what(?:'s| is) there|what it says)"
# My details (ADR-054, kairu/tasks/details.py): what you may call one, and the site a username is for
DETAIL = "(?P<key>" + "|".join(re.escape(name) for name in sorted(my_details.SAID, key=len, reverse=True)) + ")"
DETAIL_SITE = rf"(?: (?:for|on|at) (?P<site>{web.DOMAIN.pattern}|[a-z0-9-]{{2,40}}))?"


@dataclass(frozen=True)
class Phrase:
    pattern: re.Pattern
    details: Mapping = field(default_factory=dict)  # fixed details; the pattern's named groups are added to them


def _phrases(*items) -> tuple[Phrase, ...]:
    return tuple(Phrase(re.compile(item, I)) if isinstance(item, str) else Phrase(re.compile(item[0], I), item[1]) for item in items)


@dataclass(frozen=True)
class Skill:
    action: str  # its name in policy.yaml
    executor: str  # its code, as in kairu/executors.py
    phrases: tuple[Phrase, ...]
    warning: str = ""  # shown before it runs when `warn_when` fits; you say yes to go on
    warn_when: Mapping = field(default_factory=dict)


SKILLS = (
    # My details (ADR-054, BAR.md "My details"): on this PC only, never sent to any AI; keeping one is High (yes and PIN)
    Skill("details.keep", "kairu.tasks.details:keep_action", _phrases(
        rf"(?:save|set|keep|store|update|change) (?:my )?{DETAIL}{DETAIL_SITE} (?:as|to|is|=|:) [\"'“”]?(?P<value>[^\"“”]+?)[\"'“”]?"
        r"(?: in my details| on this pc)?",
        rf"(?:add|put) [\"'“”]?(?P<value>[^\"“”]+?)[\"'“”]? (?:as|to) my (?:saved )?{DETAIL}{DETAIL_SITE}")),
    Skill("details.forget", "kairu.tasks.details:forget_action", _phrases(
        rf"(?:forget|delete|remove|clear) my saved {DETAIL}{DETAIL_SITE}",
        rf"(?:forget|delete|remove|clear) {DETAIL}{DETAIL_SITE} from my details")),
    Skill("details.show", "kairu.tasks.details:show_action", _phrases(
        r"(?:show|list|tell)(?: me)? my (?:saved )?details", r"what (?:are my (?:saved )?details|details do you have(?: saved)?"
        r"(?: about me| for me)?)", r"my details")),
    # Scrolling (ADR-054): "scroll down" scrolls the app in front, by the mouse wheel; never Kairu's own or never-apps
    Skill("screen.scroll", "kairu.tasks.screen:scroll", _phrases(
        (rf"scroll (?P<direction>up|down)(?: (?P<times>[1-9]|10) (?:times|notches))?{IN_APP}", {"app": "", "times": "3"}),
        (rf"scroll (?P<direction>up|down) (?:a lot|lots|all the way|more){IN_APP}", {"app": "", "times": "10"}),
        (rf"scroll (?P<direction>up|down) (?:a (?:little|bit)|slightly){IN_APP}", {"app": "", "times": "1"}),
        (rf"scroll(?: down)? to the (?:bottom|end){IN_APP}", {"app": "", "direction": "down", "times": "10"}),
        (rf"scroll(?: up)? to the top{IN_APP}", {"app": "", "direction": "up", "times": "10"}),
        (rf"scroll{IN_APP}", {"app": "", "direction": "down", "times": "3"}))),
    # Clones (TEAM.md): the team board in two sentences and one question, read only
    Skill("team.status", "kairu.team.conduct:status", _phrases(
        r"how(?:'s| is| are) (?:the |my |our )?(?:team|project|team project|clones?)(?: going| doing| looking| coming along)?",
        r"(?:show |give |tell )?(?:me )?(?:the |our )?(?:team|project|clones?)(?:'s)? (?:status|progress|update)",
        r"(?:are we|is (?:the |our )?(?:team|project)) on (?:track|time|schedule)",
        r"how far (?:along )?(?:is|are) (?:the |our )?(?:team|project|clones?)")),
    Skill("apps.list_open", "kairu.tasks.actions:list_open", _phrases(
        r"what(?:'s| is| are) (?:open|running)", r"(?:what|which) (?:apps|windows|programs) are (?:open|running)",
        r"(?:list|show)(?: me)? (?:the |my )?(?:open )?(?:apps|windows|programs)", r"open (?:apps|windows)")),
    # Kairu's hands: keys and browser shortcuts (before apps.close and apps.open: "close this tab", "open a new tab")
    Skill("screen.press", "kairu.tasks.screen:press", _phrases(
        rf"(?:press|hit|tap|push) {THE}{KEY_WORDS}(?: key| button)?{IN_APP}",
        (rf"(?:go|navigate) back(?: a page| one page)?{IN_APP}", {"keys": "alt+left"}),
        (rf"(?:go|navigate) forward(?: a page| one page)?{IN_APP}", {"keys": "alt+right"}),
        (rf"(?:refresh|reload)(?: the| this)?(?: page| tab)?{IN_APP}", {"keys": "f5"}),
        (rf"(?:open )?(?:a )?new tab{IN_APP}", {"keys": "ctrl+t"}),
        (rf"close (?:the |this )?(?:current )?tab{IN_APP}", {"keys": "ctrl+w"}),
        (r"(?:go to |switch to )?(?:the )?next tab", {"keys": "ctrl+tab"}),
        (r"(?:go to |switch to )?(?:the )?previous tab", {"keys": "ctrl+shift+tab"}),
        (r"reopen (?:the )?(?:last )?closed tab", {"keys": "ctrl+shift+t"}),
        (rf"scroll down{IN_APP}", {"keys": "pagedown"}), (rf"scroll up{IN_APP}", {"keys": "pageup"}),
        (rf"(?:go to |scroll to )?(?:the )?top of (?:the |this )?page{IN_APP}", {"keys": "ctrl+home"}),
        (rf"(?:go to |scroll to )?(?:the )?bottom of (?:the |this )?page{IN_APP}", {"keys": "ctrl+end"}),
        (r"select all(?: the text)?", {"keys": "ctrl+a"}), (r"copy(?: it| this| that| the text)?", {"keys": "ctrl+c"}),
        (rf"paste(?: it| this| that| the text)?{IN_APP}", {"keys": "ctrl+v"}), (r"cut(?: it| this| that| the text)?", {"keys": "ctrl+x"}),
        (rf"zoom in{IN_APP}", {"keys": "ctrl+plus"}), (rf"zoom out{IN_APP}", {"keys": "ctrl+minus"}),
        (rf"save (?:it|this|the file|the document|my work){IN_APP}", {"keys": "ctrl+s"}),
        (rf"find on (?:the |this )?page{IN_APP}", {"keys": "ctrl+f"}),
        # carrying on after typing into a search bar: "search" on its own is that bar's Enter
        (r"(?:search|search it|search that|search this|search now|search for it|do the search|start the search|"
         r"(?:press|hit|click|tap) (?:the )?search(?: button)?|go|go ahead|enter|submit the search)", {"keys": "enter"}))),
    # PC4: numbers for what you can click ("show numbers", then "click 3"), before files.show ("show ... in file explorer")
    Skill("screen.numbers", "kairu.tasks.screen:numbers", _phrases(
        (rf"show (?:me )?(?:the )?numbers(?: for (?:the )?(?:buttons|links|items|options))?{IN_APP}", {"app": ""}),
        (rf"number (?:the |all the )?(?:buttons|links|items|options|things(?: i can click)?){IN_APP}", {"app": ""}),
        (rf"(?:show|give) (?:me )?(?:the )?(?:buttons|links|items|options) with numbers{IN_APP}", {"app": ""}))),
    # PC4: File Explorer's own folders by name ("go to Downloads in File Explorer"): its address bar, with the folder's path
    Skill("screen.type", "kairu.tasks.screen:type_text", _phrases(
        (rf"(?:go to|open|show(?: me)?|switch to) {THE}{KNOWN_FOLDER}(?: folder)? (?:in|on|using|with) {EXPLORER}",
         {"field": "address", "enter": "yes", "app": "file explorer"}),
        (rf"(?:in|on) {EXPLORER},? (?:go to|open|show(?: me)?) {THE}{KNOWN_FOLDER}(?: folder)?",
         {"field": "address", "enter": "yes", "app": "file explorer"}),
        (rf"(?:go to|switch to) {THE}{KNOWN_FOLDER}(?: folder)?", {"field": "address", "enter": "yes", "app": "file explorer"}))),
    Skill("files.rename", "kairu.tasks.actions:rename", _phrases(
        r"rename [\"'“]?(?P<old>.+?)[\"'”]? (?:to|as) [\"'“]?(?P<new>.+?)[\"'”]?")),
    Skill("task.undo", "kairu.tasks.actions:undo", _phrases(r"undo(?: that| it| the last (?:one|change|rename))?")),
    Skill("apps.close", "kairu.tasks.actions:close_app", _phrases(rf"(?:close|quit|exit) {THE}{APP}(?: app| window| windows)?")),
    Skill("apps.arrange", "kairu.tasks.actions:arrange_app", _phrases(
        rf"(?:put|move|snap) {THE}{APP} (?:on|to) {THE}(?P<how>left|right)(?: half| side)?(?: of the screen)?",
        rf"(?P<how>maximi[sz]e|minimi[sz]e) {THE}{APP}",
        (rf"bring {THE}{APP} to {THE}front", {"how": "front"}),
        (rf"(?:switch to|focus(?: on)?) {THE}{APP}", {"how": "front"}))),
    # Sprint Day 4: files in your work folder, Kairu's own browser, waiting (before apps.open: "open youtube" is a site)
    Skill("files.move", "kairu.tasks.actions:move_files", _phrases(
        (rf"(?:move|put) {Q}{FILE}{Q} (?:in|into|to) (?:the |a |my )?(?:new )?(?:folder )?(?:called |named )?{Q}{FOLDER}{Q}(?: folder)?", {}),
        rf"(?:move|put) {THE}folder {Q}(?P<name>[^\"“”]+?){Q} (?:in|into|to) (?:the |a |my )?(?:new )?(?:folder )?(?:called |named )?{Q}{FOLDER}{Q}(?: folder)?")),
    Skill("files.delete", "kairu.tasks.actions:delete", _phrases(
        rf"(?:delete|remove|trash|recycle|bin) {Q}{FILE}{Q}",
        rf"(?:delete|remove|trash|recycle) {THE}folder {Q}(?P<name>[^\"“”]+?){Q}",
        rf"(?:delete|remove|trash|recycle) {THE}{Q}(?P<name>[^ \"“”]+){Q} folder")),
    # W2 (ADR-036): make, open and show a file in your work folder (before web.open: "open notes.txt" is a file, not a site)
    Skill("files.write", "kairu.tasks.actions:write_file", _phrases(
        (rf"(?:make|create|write|save) (?:me )?(?:a |an |the )?(?:new )?(?:text |note |notes )?file (?:called |named )?{Q}{FILE}{Q}"
         rf"(?: (?:saying|that says|with the text|with the words|containing|with) {Q}(?P<text>.+?){Q})?", {"text": ""}))),
    Skill("files.show", "kairu.tasks.actions:show_file", _phrases(
        rf"(?:show|reveal) (?:me )?{THE}(?:file |folder )?{Q}{NAMED}{Q} in (?:its |the |a )?(?:folder|explorer|file explorer)",
        rf"open {THE}folder (?:of|for|with) {Q}{NAMED}{Q}")),
    Skill("files.open", "kairu.tasks.actions:open_file", _phrases(
        rf"open (?:up )?{THE}(?:file|folder|document|doc)(?! explorer\b) {Q}{NAMED}{Q}",  # "open file explorer" is the app (PC4)
        rf"open (?:up )?{Q}(?P<name>[^\\/:*?\"<>|“”]+?\.(?:{OPEN_KINDS})){Q}")),
    Skill("files.find", "kairu.tasks.actions:find_files", _phrases(
        (rf"(?:find|look for|where (?:is|are)) (?:me )?(?:all )?(?:the |my )?(?:files? (?:called|named) )?{Q}{FIND_WHAT}{Q}(?: files?)?{WHEN}{IN_THE_FOLDER}", {"when": ""}),
        (r"(?:list|show)(?: me)? (?:the |my |all )?(?:my )?files(?: in (?:the |my )?(?:work folder|kairu-files))?", {"what": "", "when": ""}),
        (r"what(?:'s| is) in (?:the |my )?(?:work folder|kairu-files)", {"what": "", "when": ""}))),
    # Asking an AI website, and reading a page (ASK.md): before web.open and the hands ("ask claude ..." is never "open ...")
    Skill("web.ask", "kairu.tasks.ask_ai:ask", _phrases(
        rf"ask (?P<site>{ask_ai.SITE_WORDS})(?: ai)?(?:,|:| about| this| that| to tell me| to explain| to)? {Q}(?P<question>.+?){Q}",
        rf"ask {Q}(?P<question>.+?){Q} (?:to|on|in|from|with|using) (?P<site>{ask_ai.SITE_WORDS})(?: ai)?",
        rf"(?:what|how) does (?P<site>{ask_ai.SITE_WORDS})(?: ai)? (?:say|think) about {Q}(?P<question>.+?){Q}")),
    Skill("web.read_page", "kairu.tasks.ask_ai:read_page", _phrases(
        (rf"read (?:me )?(?:the |this |that )?(?:web ?)?page(?: to me| aloud)?{IN_APP}", {"app": ""}),
        (rf"what does (?:the |this |that )?(?:web ?)?page say{IN_APP}", {"app": ""}),
        (rf"what(?:'s| is) on (?:the |this |that )?(?:web ?)?page{IN_APP}", {"app": ""}))),
    Skill("web.open", "kairu.tasks.actions:web_open", _phrases(
        rf"(?:open|go to|visit) (?:up )?{URL}(?: website| site| in (?:the |my |kairu's )?browser"
        rf"| (?:in|on|using) (?:google )?chrome| (?:in|on|using) (?:microsoft )?edge)?")),
    Skill("web.search", "kairu.tasks.actions:web_search", _phrases(
        rf"google {SEARCH_FOR}", rf"search (?:on )?google for {SEARCH_FOR}", rf"search (?:for )?{SEARCH_FOR} on google",
        rf"look up {SEARCH_FOR} on google", rf"search (?:for )?{SEARCH_FOR} in (?:the |my |kairu's )?browser",
        rf"search (?:for )?{SEARCH_FOR} (?:in|on|using) (?:google chrome|chrome|microsoft edge|edge)")),
    # Kairu's hands: type, click and read in an app's window (after the web skills: "search X in the browser" is web.search)
    Skill("screen.type", "kairu.tasks.screen:type_text", _phrases(
        rf"(?:in|into|on|at) {THE}{FIELD_WORDS}{OF_APP},? {TYPE_VERB} {TEXT}",
        rf"{TYPE_VERB} {TEXT} (?:in|into|on|at) {THE}{FIELD_WORDS}{OF_APP}",
        (rf"search (?:for )?{TEXT} (?:in|on|using|with|from) {THE}{FIELD_WORDS}{OF_APP}", {"enter": "yes"}),
        rf"{TYPE_VERB} {TEXT} (?:in|into|on|inside) {THE}{APPN}(?: app| window)?",
        (rf"search (?:for )?{TEXT} (?:in|on|inside) {THE}{APPN}(?: app| window)?", {"field": "search", "enter": "yes"}),
        rf"(?:type|write) {TEXT}")),
    Skill("screen.click", "kairu.tasks.screen:click", _phrases(
        rf"(?:click|double click|double-click|tap)(?: on)? {THE}{TARGET}(?: button| link| tab| option| menu| icon| item)?{IN_APP}",
        rf"(?:press|hit|select|choose|tap) {THE}{TARGET} (?:button|link|tab|option|menu|icon|item){IN_APP}",
        r"(?:choose|pick|select|open) (?P<target>(?:number|no\.?|option|item) \d{1,2})",  # PC4: after "show numbers"
        r"(?:choose|pick|select) (?P<target>\d{1,2})",
        r"(?:choose|pick|select|click|tap) (?:on )?(?:the )?(?P<target>(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|"
        r"tenth|last|\d{1,2}(?:st|nd|rd|th))(?: one| item| option| button| link)?)")),
    Skill("screen.read", "kairu.tasks.screen:read", _phrases(
        r"what(?:'s| is) on (?:the |my )?screen", r"read (?:the |my |this )?(?:screen|window)",
        rf"what can i (?:click|press|do|see) (?:in|on) {THE}{APPN}(?: app| window)?",
        rf"read {THE}{APPN} window", rf"what(?:'s| is) (?:on|in) {THE}{APPN} window")),
    # PC4: any window's words ("read Notepad", "what does Notepad say", "read it"): data, shown to you, never an order
    Skill("screen.read_text", "kairu.tasks.screen:read_text", _phrases(
        (rf"read (?:me )?{IT}{READ_OUT}", {"app": ""}),
        rf"read (?:me )?{THE}(?P<app>{KNOWN_APP})(?: app)?{READ_OUT}",
        rf"read (?:me )?(?:what(?:'s| is) (?:in|on|written in|typed in)|the (?:text|words|writing) (?:in|on|of)) {THE}{APPN}(?: app| window)?{READ_OUT}",
        rf"what does {THE}{APPN}(?: app| window)? say",
        rf"what(?:'s| is) (?:written|typed) (?:in|on) {THE}{APPN}(?: app| window)?",
        rf"what files are (?:in|on|shown in) {THE}{APPN}(?: app| window)?",
        (r"what does (?:it|this|that) say", {"app": ""}),
        (r"what(?:'s| is) (?:written|typed) (?:here|there)", {"app": ""}))),
    # PC4: the safe list from the bar (marking an app safe is High: your yes and PIN)
    Skill("hands.safe_list", "kairu.tasks.screen:safe_list", _phrases(
        r"(?:which|what) apps are (?:on (?:the |kairu's |your )?)?safe(?: list)?", r"(?:show|list|tell)(?: me)? (?:the |kairu's |your )?safe (?:list|apps)",
        r"what(?:'s| is) on (?:the |kairu's |your )?safe list")),
    Skill("hands.unmark_safe", "kairu.tasks.screen:unmark_safe", _phrases(
        rf"unmark {THE}{APPN}(?: app)?(?: as safe| safe)?", rf"mark {THE}{APPN}(?: app)? (?:as )?(?:not safe|unsafe)",
        rf"(?:take|remove) {THE}{APPN}(?: app)? (?:off|from) (?:the |kairu's |your )?safe (?:list|apps)",
        rf"stop trusting {THE}{APPN}(?: app)?")),
    Skill("hands.mark_safe", "kairu.tasks.screen:mark_safe", _phrases(
        rf"mark {THE}{APPN}(?: app)? (?:as )?safe", rf"(?:make|set) {THE}{APPN}(?: app)? (?:a )?safe(?: app)?",
        rf"add {THE}{APPN}(?: app)? to (?:the |kairu's |your )?safe (?:list|apps)")),
    # PC5 (BAR.md "Commands and installs"): commands with no shell, and winget. The core picks the tier from the command itself
    # (terminal.classify): read-only safe list Low, work safe list Medium, anything else High, admin rights Critical
    Skill("terminal.run", "kairu.tasks.terminal:run", _phrases(
        (r"run (?:the |my )?kairu(?:'s)? tests", {"command": "python -m pytest -q -x", "folder": "kairu"}),
        (r"run (?:the |my )?tests(?: in (?P<folder>.+?))?", {"command": "python -m pytest -q -x", "folder": ""}),
        (r"(?:run )?(?P<command>git (?:status|log|diff|pull|fetch|branch))(?: in (?P<folder>.+?))?", {"folder": ""}),
        (r"(?:run|execute) (?:the )?(?:command|terminal command) [`\"'“]?(?P<command>.+?)[`\"'”]?(?: in (?P<folder>(?:the )?(?:work folder|kairu(?:-guardian)?|[\w .-]{1,40})))?",
         {"folder": ""}))),
    Skill("apps.install", "kairu.tasks.terminal:install", _phrases(
        rf"(?P<hidden>silently|quietly|secretly) install {THE}(?P<app>[a-z0-9][a-z0-9 .+#_-]{{0,59}}?)(?: app)?",
        rf"install {THE}(?P<app>[a-z0-9][a-z0-9 .+#_-]{{0,59}}?)(?: app)?(?: (?:with|using|from) winget)?")),
    Skill("apps.uninstall", "kairu.tasks.terminal:uninstall", _phrases(
        rf"uninstall {THE}(?P<app>[a-z0-9][a-z0-9 .+#_-]{{0,59}}?)(?: app)?(?: (?:with|using|from) winget)?",
        rf"remove (?:the )?app (?P<app>[a-z0-9][a-z0-9 .+#_-]{{0,59}})")),
    Skill("task.wait", "kairu.tasks.actions:wait", _phrases(
        r"wait (?:for )?(?P<seconds>\d{1,3}) ?(?:seconds?|secs?|s)", (r"wait (?:for )?(?:a|one) (?:second|sec)", {"seconds": "1"}),
        (r"wait (?:for )?(?:a )?(?:few|couple of) seconds", {"seconds": "3"}), (r"wait (?:for )?(?:a|one) minute", {"seconds": "60"}))),
    Skill("apps.open", "kairu.tasks.actions:open_app", _phrases(rf"(?:open|launch|start) (?:up )?{THE}{APP}(?: app)?")),
    Skill("system.volume", "kairu.tasks.actions:volume", _phrases(
        rf"(?:set )?{THE}(?:volume|sound)(?: to| at)? {LEVEL}", rf"(?:turn )?{THE}(?:volume|sound) {UP_DOWN}",
        rf"turn {UP_DOWN} {THE}(?:volume|sound)", r"(?P<setting>mute|unmute)(?: the volume| the sound)?")),
    Skill("system.brightness", "kairu.tasks.actions:brightness", _phrases(
        rf"(?:set )?{THE}brightness(?: to| at)? {LEVEL}", rf"(?:turn )?{THE}brightness {UP_DOWN}", rf"turn {UP_DOWN} {THE}brightness")),
    Skill("system.wifi", "kairu.tasks.actions:wifi", _phrases(
        rf"(?:turn |switch )?{THE}wi-?fi (?P<setting>on|off)", rf"(?:turn|switch) (?P<setting>on|off) {THE}wi-?fi"),
        warning="Wi-Fi off drops your phone's link to this PC until it's on again.", warn_when=MappingProxyType({"setting": "off"})),
    Skill("system.status", "kairu.tasks.actions:status", _phrases(
        r"how much (?:free )?(?:ram|memory)(?: do i have| is (?:there|free|left|available|used))?", r"(?:free )?(?:ram|memory)",
        r"(?:how much )?battery(?: is left| left)?", r"(?:system|pc|computer|laptop) status", r"cpu(?: usage)?",
        r"what(?:'s| is) using (?:the )?most (?:ram|memory)")),
    Skill("system.lock", "kairu.tasks.actions:lock", _phrases(r"lock(?: the| my| this)?(?: pc| computer| laptop| screen)?")),
    Skill("system.sleep", "kairu.tasks.actions:sleep", _phrases(
        r"(?:go to )?sleep", r"put (?:the|my|this) (?:pc|computer|laptop) to sleep")),
    Skill("system.restart", "kairu.tasks.actions:restart", _phrases(r"(?:restart|reboot)(?: the| my| this)?(?: pc| computer| laptop)?")),
    Skill("system.shutdown", "kairu.tasks.actions:shutdown", _phrases(
        r"(?:shut ?down|power off)(?: the| my| this)?(?: pc| computer| laptop)?", r"turn off (?:the |my |this )?(?:pc|computer|laptop)",
        r"shut (?:the |my |this )?(?:pc|computer|laptop) down")),
)
NOT_YET = re.compile(r".*\bbluetooth\b.*", I)  # the sprint leaves it out: Kairu says so, and nothing runs


class SkillRefused(Exception):
    pass


def check(skills, rules: Mapping[str, Rule]) -> tuple[tuple[Skill, ...], tuple[str, ...]]:
    """(the skills that may exist, why each other one may not). Missing from the policy or Critical: refused at load."""
    usable, refused = [], []
    for skill in skills:
        rule = rules.get(skill.action)
        if rule is None:
            refused.append(f"{skill.action}: not in policy.yaml, so it does not exist")
        elif rule.tier is Tier.CRITICAL:
            refused.append(f"{skill.action}: Critical, so it does not exist")
        else:
            usable.append(skill)
    return tuple(usable), tuple(refused)


def match(skills, text: str) -> tuple[Skill, dict] | None:
    """The skill whose phrase is exactly this text, with the details from it."""
    for skill in skills:
        for phrase in skill.phrases:
            found = phrase.pattern.fullmatch(text)
            if found:
                named = {key: value.strip() for key, value in found.groupdict().items() if value}
                return skill, {**phrase.details, **named}
    return None
