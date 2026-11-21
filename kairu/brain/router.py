"""The Model Gateway's router: which brain level answers a question (ADR-015, BRAIN.md "The five brain levels").

    L0  fixed rules on this PC, no AI: the time, the date, Kairu's status and usage, greetings, help, and Kairu's
        memory ("remember that ...", "forget ...", "what do you remember": MEMORY.md). L0 does
        only Low-tier, reversible things (the 20 Oct rule): it reads and tells, it never changes anything.
        A request to DO something ("delete this folder", "pay the bill") is recognised here too and handed
        to Guardian as that action, by its policy name; Guardian decides by its tier. Answers never run it.
    L1  a tiny model on the device: off on the PC (RAM); it comes with the phone app (Phase D)
    L2  a medium local model on the PC: off until the RAM upgrade (Phase K)
    L3  free cloud AI: every other question, after the privacy filter (kairu/brain/privacy.py). A question that
        needs fresh facts (today, latest, who holds an office now, scores, news, prices, weather, dates) or says
        "search" is marked `research`: with research on, Guardian's search and page reads come first (RESEARCH.md)
    L4  team mode (several agents): building apps or sites, long reports. It comes with Phase G; until then Kairu
        says so instead of guessing. Deep research on request ("research deeply ...") is built: it is an L3 question
        marked `deep`, which gets several searches and a short report (RESEARCH.md "Deep research")

route() is rules only, no AI: the same question always goes to the same level.
"""

import re
from dataclasses import dataclass

from kairu.brain import privacy
from kairu.brain.privacy import Verdict
from kairu.memory.talks import TALKS
from kairu.research import weather, where as whereabouts

LEVELS = {  # level -> (what it is, its state in Phase B)
    "L0": ("fixed rules on this PC, no AI", "on"),
    "L1": ("a tiny AI model on the device", "off on the PC (RAM); on the phone in Phase D"),
    "L2": ("a medium local AI model on the PC", "off until the RAM upgrade (Phase K)"),
    "L3": ("free cloud AI", "on: the main brain in Phase B"),
    "L4": ("team mode: several agents and deep research", "comes with Phase G"),
}


@dataclass(frozen=True)
class Route:
    level: str  # L0, L3 or L4 (L1 and L2 are off on the PC in Phase B)
    kind: str  # "rule" (L0 answers), "action" (handed to Guardian), "team" (L4, not built yet), "cloud" (L3), "memory" (L0)
    name: str = ""  # the rule, or the policy action; for "memory": remember, forget, recall or talks (its words are in query)
    privacy: Verdict | None = None  # for "cloud": what the filter found
    follow_up: bool = False  # "yes, tell me more": the answer before it is needed to understand it
    dated: bool = False  # the answer may have changed since the model learned it
    research: bool = False  # it needs fresh facts, or you said "search": the web comes first, when research is on
    query: str = ""  # for research: the words to search for (the Gateway writes out "today" as a date)
    deep: bool = False  # "research deeply ...": several searches and a short report with numbered sources (RESEARCH.md)
    when: str = ""  # for "talks": today, yesterday or recent


# "ask Claude X and summarise it" (ASK.md, 15 Nov 2026): the task core sends the AI website's answer here with this lead.
# It is summarised like any cloud question (the privacy filter reads all of it), but never searched for and never kept
# in the talk history: the answer is quoted page text (orders and secrets already left out), not your words.
SUMMARY_LEAD = "Summarise this answer from an AI website."

POLITE = re.compile(r"^(?:(?:hey|hi|ok|okay|hello)\s+)?(?:kairu[\s,:!.-]*)?(?:please\s+|pls\s+|plz\s+)?"
                    r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+want\s+you\s+to\s+|i\s+need\s+you\s+to\s+|"
                    r"go\s+and\s+|just\s+)?")

RULES = [  # (rule, pattern on the plain question)
    ("time", r"(?:what(?:'s|s| is)? (?:the )?(?:current |exact )?time(?: is it)?(?: now| right now)?|time(?: now)?|"
             r"current time|tell me the time|what time is it(?: now)?)"),
    ("date", r"(?:what(?:'s|s| is)? (?:the |today'?s )?date(?: today)?|today'?s date|date(?: today)?|"
             r"what day is (?:it|today)(?: today)?|which day is (?:it|today)|what is today)"),
    ("greeting", r"(?:hi|hello|hey|namaste|namaskaram|good (?:morning|afternoon|evening)|hey there|hi there|"
                 r"hello there|yo)"),
    ("status", r"(?:status|your status|kairu status|pc status|are you (?:running|there|ok|okay|working|awake|on)|"
               r"how are you(?: doing)?|are you alive)"),
    ("thanks", r"(?:thanks|thank you|thx|ok thanks|okay thanks|thanks a lot|thank you so much)"),
    ("help", r"(?:help|what can you do|what do you do|how do i use you|commands)"),
    ("usage", r"(?:usage|(?:show )?(?:my |your )?usage|how much (?:free )?(?:limit|quota) (?:is )?(?:left|used)|"
              r"free limits?|providers|which ai (?:are you using|do you use))"),
    ("missions", r"(?:missions|mission status|my missions|what are you working on|any missions)"),
    ("stop", r"(?:stop|stop everything|stop all|halt|pause|pause all|pause all missions|stop all missions|"
             r"emergency stop)"),
    ("sources", r"(?:sources?|your sources?|(?:show|list|give|tell)(?: me)? (?:the |your )?(?:sources?|links?)|"
                r"what (?:are|were|is|was) (?:the |your )?sources?|where did you (?:get|find|read) (?:that|this|it)|"
                r"which (?:pages|sites|websites)(?: did you (?:use|read))?)"),
    ("call", r"(?:(?:call(?: up)?|make a (?:phone )?call to|place a call to) "
             r"(?!(?:it|this|that|the|a|an|me|us|these|those|number|numbers|center|centre|of|function|method|stack|logs?|"
             r"recordings?|history|quality|forwarding|waiting)\b)[\w+'-]+(?: [\w+'-]+){0,3}?|"
             r"(?:phone|ring|dial) (?:(?:my|our) [\w'-]+(?: [\w'-]+)?|him|her|them|mom|mum|dad|amma|nanna|\+?\d[\d -]{2,}))"
             r"(?: (?:on|at) \+?[\d -]+)?(?: (?:now|please|today|tomorrow|tonight))?"),
]

ACTIONS = [  # (policy action, pattern at the start of the request): what "do this" means to Guardian
    ("credentials.reveal", r"(?:show|tell|give|send|read|copy|share|reveal)(?: me| him| her)? (?:all )?(?:my |the |your )?"
                           r"(?:saved )?(?:passwords?|api keys?|keys|tokens?|pins?|otps?|secrets?|credentials)\b"),
    ("security.disable", r"(?:turn off|disable|switch off|stop|uninstall|kill|close|pause) (?:the |my |windows )?"
                         r"(?:antivirus|anti-virus|firewall|defender|windows defender|windows security|guardian|"
                         r"kairu guardian|protection|security)\b"),
    ("security.change", r"(?:change|reset|remove|turn off) (?:my |the )?(?:password|passcode|pin|security settings?|"
                        r"2fa|two[- ]factor(?: authentication)?|screen lock|lock screen)\b"),
    ("system.destroy", r"(?:format|wipe|erase|factory reset) (?:the |my |this )?(?:drive|disk|hard disk|pc|computer|"
                       r"laptop|c drive|d drive|system|everything|phone)\b|delete (?:everything|all files|system32|windows)\b"),
    ("money.spend", r"(?:pay (?:the |my |for |rs\.?|inr|₹|\d|bill|bills|him|her|them|back|fees|rent)|send money|"
                    r"transfer (?:money|rs\.?|inr|₹|\d|funds|cash|the amount)|buy (?:me |a |an |the |some |\d)|"
                    r"purchase (?:a |an |the |me |some )|order (?:food|pizza|groceries|a |an |me |something|from)|"
                    r"recharge (?:my |the |\d|rs\.?|₹)|top up|donate (?:to |rs\.?|₹|\d)|subscribe to)|"
                    r"book (?:a |an |the |my )?(?:ticket|tickets|cab|taxi|flight|hotel|train|bus|room|table)\b"),
    ("files.delete", r"(?:delete|remove|erase|trash|clear) (?:this |that |the |my |a |all |these |those |old )*"
                     r"(?:files?|folders?|documents?|photos?|pictures?|videos?|downloads|screenshots)\b"),
    ("message.send", r"(?:send|write) (?:a |an )?(?:message|email|mail|text|sms|whatsapp|reply)\b|"
                     r"(?:text|message|whatsapp|sms|email|mail) (?:my \w+|him|her|them|back)\b|"
                     r"reply to (?:my |his |her |this |that )?\w+"),
    ("files.write", r"(?:create|make|write|save) (?:a |an |new )?(?:file|document|note|text file)\b"),
]

TEAM = (r"(?:build|make|create|develop|code|design|generate) (?:me |us )?(?:a |an |the |my )?(?:\w+ )?"
        r"(?:website|web ?site|web app|webapp|app|application|mobile app|android app|ai agent|agent|bot|chatbot|game|"
        r"presentation|slides|slide deck|deck|landing page|portfolio site)\b|"
        r"(?:do |a )?deep research\b|research and write\b|write (?:me )?a (?:full |detailed |long )?(?:report|thesis)\b")

FOLLOW_WORDS = {  # a short reply made only of these words follows the answer before it: "yes, tell me more"
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "please", "pls", "tell", "me", "more", "go", "on", "continue",
    "and", "why", "how", "so", "explain", "in", "detail", "details", "elaborate", "really", "then", "about", "it",
    "that", "this", "him", "her", "them", "a", "bit", "little", "further", "simply", "simpler", "again", "what",
    "else", "do", "you", "mean", "is", "ahead", "of", "course",
    "like", "teacher", "simple", "words", "child", "kid", "five", "easy", "plain",  # Explain Mode: "explain like a teacher"
}
FOLLOW_UP_START = re.compile(r"(?:and )?(?:what about|how about|what else|and then|tell me more about)\b", re.IGNORECASE)

DATED = re.compile(r"\b(?:current|currently|now|today|tonight|latest|newest|recent|recently|this (?:week|month|year)|"
                   r"who is the (?:\w+ )?(?:president|prime minister|pm|ceo|chief minister|cm|governor|captain|"
                   r"coach|chairman|chairperson|head|minister|leader|king|queen|pope|mayor|speaker|owner|founder|"
                   r"chief|director|manager|champion)|who (?:won|leads|runs|owns)|price|prices|cost|rate|rates|score|"
                   r"scores|weather|news|stock|stocks|share price|version|release|released|election|elections|winner|"
                   r"champion|ranking|rankings|population|exchange rate|still)\b", re.IGNORECASE)
FRESH = re.compile(r"\b(?:today|tonight|yesterday|tomorrow|now|currently|current|latest|newest|recent|recently|"
                   r"this (?:morning|afternoon|evening|week|month|year)|last (?:night|week|weekend|month|year)|"
                   r"at the moment|these days|"
                   r"who(?:'s| is) the (?:\w+ )?(?:president|prime minister|pm|ceo|chief minister|cm|governor|captain|coach|"
                   r"chairman|chairperson|head|minister|leader|king|queen|pope|mayor|speaker|owner|chief|director|manager|"
                   r"champion)|who (?:won|leads|runs|owns)|who(?:'s| is) (?:winning|leading)|"
                   r"scores?|scorecard|news|headlines?|prices?|costs?|share price|stocks?|exchange rate|weather|forecast|"
                   r"temperature in|elections?|winner|champion|rankings?|schedule|fixtures?|"
                   r"when(?:'s| is)|what date|which date)\b", re.IGNORECASE)
# "I want to eat biryani, just find some websites with low cost" (the owner, 19 Nov 2026): the web, for the lowest prices
CHEAP = re.compile(r"\b(?:cheap|cheapest|cheaper|low[- ]?cost|lowest (?:price|cost)s?|low[- ]?price[sd]?|affordable|"
                   r"budget[- ](?:friendly|options?|places?|hotels?|phones?|laptops?|food|meals?|restaurants?)|inexpensive|best (?:deals?|prices?|offers?)|less (?:price|cost|money))\b", re.IGNORECASE)
NOT_CHEAP = re.compile(r"(?:what|why|how) (?:is|are|does|do)\b|(?:is|are|was|were) (?:it|that|this|they|these)\b|(?:define|meaning of|explain)\b|.*\bmean(?:s|ing)?$")
CHEAP_FILLER = re.compile(
    r"\b(?:i (?:want|wanna|would like|need|feel like)(?: to)? (?:eat|buy|get|order|have|try|purchase)|i(?:'m| am) (?:hungry|craving)"
    r"(?: for)?|(?:just |please |can you |could you )*(?:find|show|give|get|search|look for|tell|suggest|list)(?: me)?"
    r"(?: (?:some|a few|the|any|good|best))*(?: (?:websites?|sites?|apps?|places?|options?|shops?|restaurants?|deals?))?"
    r"(?: (?:with|for|that have|that sell|selling|which (?:have|sell)|at|of|in))?|websites?|sites?|with|for|at|some|so|best|good|top|please|pls|just)\b",
    re.IGNORECASE)


def cheap_words(text: str) -> str:
    """What to search for a cheap-thing question: the thing, and "lowest price"; "" if it is not one."""
    if not CHEAP.search(text) or SEARCH.fullmatch(text) or NOT_CHEAP.match(text):
        return ""
    thing = " ".join(CHEAP.sub(" ", CHEAP_FILLER.sub(" ", text)).split()).strip(" ,.;:-")
    thing = re.sub(r"^(?:and|the|a|an|to|me)\s+|\s+(?:and|the|a|to|me|just|please|pls)$", "", thing).strip()
    if not thing or len(thing) < 3:
        return ""
    return f"cheapest {thing} price online"[:LONGEST_QUERY]


SEARCH = re.compile(r"(?:web |internet |online )?(?:search|google|look up)(?: (?:on )?(?:the )?(?:web|internet|online))?"
                    r"(?: (?:for|about))?\s+(?P<words>\S.*)")
# Kairu's memory (stage M1, MEMORY.md): on this PC, by rules, no AI. Only these words reach it
REMEMBER = re.compile(r"(?:(?:remember|memori[sz]e|keep in mind|don'?t forget|do not forget)(?: this| it)?(?:,| that|:)?|note that|"
                      r"note down that)\s+(?!(?:what|when|where|who|how|why|if|whether|me)\b)(?P<words>\S.{2,})")
FORGET_ALL = re.compile(r"(?:forget|delete|clear|erase|wipe) (?:everything|all)(?: (?:that )?(?:you|u) (?:remember|know)| in (?:your|my) memory)?"
                        r"(?: about me)?|(?:clear|erase|wipe|delete) (?:your|my|the) memory")
FORGET = re.compile(r"forget (?:that |about |what i (?:said|told you) about |everything about |all about )?"
                    r"(?!(?:it|that|this|them|me|us|about it)$)(?P<words>\S.*)")
RECALL = re.compile(r"what do (?:you|u) (?:remember|know)(?: about me| of me)?|what have i told you(?: to remember)?|"
                    r"(?:show|list|tell)(?: me)? (?:what (?:you|u) remember|(?:your|my) memory|everything (?:you|u) remember)|"
                    r"(?:your|my) memory|what do (?:you|u) remember about (?P<words>(?!me$)\S.*)")

# Your talk history (MEMORY.md "Talk history"): read on this PC, by rules
WHEN = r"today|yesterday|earlier|before|last time|lately|recently|this morning|this evening|tonight"


def _when(group: str) -> str:
    return rf"(?: (?P<{group}>{WHEN}))?"


TALKS_RECALL = re.compile(
    r"what (?:did|have) i (?:ask|asked|say|said)(?: (?:you|to you|kairu))?" + _when("w1") + r"|"
    r"what (?:did|have) we (?:talk|talked|speak|spoke|chat|chatted) about" + _when("w2") + r"|"
    r"(?:show|list|tell)(?: me)? (?:my |our |the )?(?:talk|chat|conversation)s?(?: history)?" + _when("w3") + r"|"
    r"(?:my |our |the )?(?:talk|chat|conversation) history|"
    r"what (?:did|have) i (?:ask|asked)(?: you)? about (?P<about>\S.*)|"
    r"what did (?:you|u) (?:say|tell me) about (?P<about2>\S.*)|"
    r"did i (?:ever )?ask(?: you)? about (?P<about3>\S.*)")
TALKS_FORGET = re.compile(r"(?:forget|delete|clear|erase|wipe) (?:all )?(?:of )?(?:our|my|the) (?:talks?|chats?|conversations?)"
                          r"(?: history)?|(?:forget|delete|clear|erase|wipe) (?:the |our |my )?(?:talk|chat|conversation) history")

# Deep research, on request only (RESEARCH.md "Deep research"): "research deeply X", "deep research on X", "research X in depth"
DEEP = re.compile(r"(?:(?:do|make|run|start|give me) )?(?:(?:a|some) )?(?:deep|detailed|thorough|full|in-depth) research"
                  r"(?: (?:on|about|into|of|for))?\s+(?P<after>\S.*)|"
                  r"research deeply(?: (?:on|about|into))?\s+(?P<deeply>\S.*)|"
                  r"research (?:(?:on|about|into) )?(?P<before>\S.*?),? (?:deeply|in depth|in detail|thoroughly)")
LONGEST_QUERY = 300


def plain(question: str) -> str:
    """The question in lower case, without "Kairu, please" in front and punctuation at the ends."""
    text = " ".join(question.split()).lower()
    text = text.strip(" .!?,;:\"'`")
    text = POLITE.sub("", text, count=1).strip(" .!?,;:")
    return text


def route(question: str, previous: tuple[str, str] | None = None) -> Route:
    """Where a question goes. previous: (question, answer) just before it, for a follow-up ("tell me more")."""
    if question.startswith(SUMMARY_LEAD):
        return Route("L3", "cloud", "summary", privacy=privacy.classify(question))
    text = plain(question)
    for name, pattern in RULES:
        if re.fullmatch(pattern, text):
            return Route("L0", "rule", name)
    for name, pattern in ACTIONS:
        if re.match(pattern, text) and not re.match(r"(?:how|what|why|when|where|which|who|is|are|can i|should i|do i)\b",
                                                    text):
            return Route("L0", "action", name)
    if TALKS_FORGET.fullmatch(text):
        return Route("L0", "memory", "forget", query=TALKS)
    talked = TALKS_RECALL.fullmatch(text)
    if talked:
        about = talked["about"] or talked["about2"] or talked["about3"] or ""
        when = {"yesterday": "yesterday", "today": "today", "this morning": "today", "this evening": "today",
                "tonight": "today"}.get(talked["w1"] or talked["w2"] or talked["w3"] or "", "recent")
        return Route("L0", "memory", "talks", query=_as_said(question, about) if about else "", when=when)
    for name, pattern in (("remember", REMEMBER), ("forget", FORGET_ALL), ("forget", FORGET), ("recall", RECALL)):
        said = pattern.fullmatch(text)
        if said:  # the line is kept as you said it, capitals and all
            words = said.groupdict().get("words") or ""
            return Route("L0", "memory", name, query=_as_said(question, words) if words else ("*" if name == "forget" else ""))
    if whereabouts.asked(question):  # "where am I?": Windows' location, the area and city (kairu/research/where.py)
        return Route("L3", "cloud", "location", privacy=privacy.classify(question), research=True, query="")
    where = weather.place(question)
    if where:  # "what's the weather in Hyderabad": Open-Meteo answers in a second (kairu/research/weather.py)
        return Route("L3", "cloud", "weather", privacy=privacy.classify(question), dated=True, research=True, query=where)
    deep = DEEP.fullmatch(text)
    if deep:  # before team mode: deep research is built (the rest of L4 comes with Phase G)
        words = re.sub(r"[ ,]+(?:please|pls|plz)$", "", next(group for group in deep.groups() if group))[:LONGEST_QUERY].strip()
        return Route("L3", "cloud", privacy=privacy.classify(question), dated=True, research=True, query=words, deep=True)
    if re.match(TEAM, text):
        return Route("L4", "team")
    words = re.findall(r"[a-z']+", text)
    follow_up = bool(previous) and ((0 < len(words) <= 8 and set(words) <= FOLLOW_WORDS)
                                    or FOLLOW_UP_START.match(text) is not None)
    verdict = privacy.classify(question)
    if follow_up:  # what goes out is the earlier question and answer too: all of it passes the filter
        earlier_question, earlier_answer = previous
        for found in (privacy.classify(earlier_question), privacy.classify(earlier_answer, answer=True)):
            verdict = _worse(verdict, found)
    dated = DATED.search(question) is not None or (follow_up and DATED.search(previous[0]) is not None)
    query = (None if follow_up else cheap_words(text)) or _search_words(question, text, previous if follow_up else None)
    dated = dated or bool(CHEAP.search(text))
    return Route("L3", "cloud", privacy=verdict, follow_up=follow_up, dated=dated, research=bool(query), query=query)


def _as_said(question: str, words: str) -> str:
    """These words of the plain question, as they were typed (plain() made them lower case)."""
    typed = " ".join(question.split())
    place = typed.lower().rfind(words)
    return typed[place:place + len(words)] if place >= 0 else words


def _search_words(question: str, text: str, previous: tuple[str, str] | None) -> str:
    """What to search for, if this question wants the web; "" if not. A follow-up searches for what it follows."""
    said = SEARCH.fullmatch(text)
    if said:
        return said["words"][:LONGEST_QUERY].strip()
    if previous:
        before = plain(previous[0].split(" / ")[0])
        searched = SEARCH.fullmatch(before)
        if searched or FRESH.search(before) or FRESH.search(question):
            words = searched["words"] if searched else before
            only_follows = set(re.findall(r"[a-z']+", text)) <= FOLLOW_WORDS
            return (words if only_follows else f"{words} {text}")[:LONGEST_QUERY].strip()
        return ""
    return text[:LONGEST_QUERY].strip() if FRESH.search(question) else ""


def _worse(one: Verdict, other: Verdict) -> Verdict:
    order = {privacy.PUBLIC: 0, privacy.PERSONAL: 1, privacy.SECRET: 2}
    if order[other.level] > order[one.level]:
        return Verdict(other.level, other.reasons)
    if order[other.level] == order[one.level] and other.reasons:
        return Verdict(one.level, tuple(dict.fromkeys(one.reasons + other.reasons)))
    return one
