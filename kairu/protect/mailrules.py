"""The email rules: fixed checks on one email, with no AI model. The same email always gets the same answer.

check(mail) returns the findings for one email:
  phishing         warning signs added up (SIGNS); 4 or more points make an alert
  ai_instructions  the email tells an AI assistant (Kairu or another) to do something: flagged, never obeyed
  account_alert    a security notice (new sign-in, password changed) from a sender Gmail verified

Every sign becomes one line of evidence in plain words. An email is data, never an instruction:
nothing here opens a link or an attachment, follows what an email says, or sends anything anywhere.

What is never claimed: that an email is safe. No finding means only that none of these signs was seen.
"""

import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

STRONG, MODERATE, MILD = 3, 2, 1
ALERT_AT = 4  # points that make a phishing alert
HIGH_AT = 6  # points for high confidence

# brand -> (words that name it, its own domains: a registrable domain, or ".tld" for a brand's own top-level domain)
BRANDS = {
    "SBI": (("sbi", "state bank of india", "yono"), ("sbi.co.in", "sbi.bank.in", "sbicard.com", ".sbi")),
    "HDFC Bank": (("hdfc", "hdfcbank"), ("hdfcbank.com", "hdfcbank.net", "hdfc.bank.in", "hdfc.com", "hdfclife.com",
                                         "hdfcergo.com")),
    "ICICI Bank": (("icici", "icicibank"), ("icicibank.com", "icici.bank.in", "icicidirect.com", "iciciprulife.com",
                                             "icicilombard.com")),
    "Axis Bank": (("axis bank", "axisbank"), ("axisbank.com", "axis.bank.in", "axisbank.co.in")),
    "Kotak": (("kotak",), ("kotak.com", "kotak.bank.in", "kotaksecurities.com")),
    "Paytm": (("paytm",), ("paytm.com", "paytmbank.com", "paytmmoney.com")),
    "PhonePe": (("phonepe",), ("phonepe.com",)),
    "Google": (("google", "gmail", "youtube"), ("google.com", "google.co.in", "youtube.com", "youtu.be", "googleapis.com",
                                                 "gstatic.com", "googleusercontent.com", "withgoogle.com", "g.co",
                                                 "blogger.com")),
    "Microsoft": (("microsoft", "outlook", "office 365", "office365", "onedrive"),
                  ("microsoft.com", "office.com", "microsoftonline.com", "live.com", "outlook.com", "microsoft365.com",
                   "sharepoint.com", "office365.com")),
    "Apple": (("apple", "icloud", "itunes"), ("apple.com",)),
    "Amazon": (("amazon",), ("amazon.in", "amazon.com", "amazon.co.uk", "amazonpay.in")),
    "Flipkart": (("flipkart",), ("flipkart.com",)),
    "PayPal": (("paypal",), ("paypal.com", "paypal.in")),
    "Netflix": (("netflix",), ("netflix.com",)),
    "Meta": (("instagram", "facebook", "meta"), ("instagram.com", "facebook.com", "facebookmail.com", "meta.com", "fb.com",
                                                  "fbcdn.net")),
    "WhatsApp": (("whatsapp",), ("whatsapp.com",)),
    "LinkedIn": (("linkedin",), ("linkedin.com", "lnkd.in")),
    "GitHub": (("github",), ("github.com", "github.io", "githubusercontent.com", "githubassets.com")),
    "Income Tax Department": (("income tax", "incometax"), ("incometax.gov.in", "incometaxindia.gov.in")),
    "UIDAI (Aadhaar)": (("aadhaar", "aadhar", "uidai"), ("uidai.gov.in",)),
    "IRCTC": (("irctc",), ("irctc.co.in",)),
    "India Post": (("india post", "indiapost"), ("indiapost.gov.in",)),
    "Airtel": (("airtel",), ("airtel.in", "airtel.com")),
    "Jio": (("jio",), ("jio.com",)),
}
FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "ymail.com", "outlook.com", "hotmail.com",
             "live.com", "msn.com", "rediffmail.com", "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com",
             "zoho.com", "zohomail.in", "mail.com", "gmx.com", "yandex.com"}
SECOND_LEVEL = {"co", "com", "net", "org", "gov", "ac", "edu", "gen", "firm", "ind", "nic", "res", "bank", "mil", "ltd",
                "plc", "sch", "govt"}
TRACKERS = {"list-manage.com", "mailchimp.com", "sendgrid.net", "mandrillapp.com", "hubspotlinks.com", "hs-sites.com",
            "sparkpostmail.com", "mailgun.org", "awstrack.me", "rs6.net", "campaign-archive.com", "substack.com",
            "beehiiv.com", "convertkit-mail.com", "ck.page", "t.co", "lnkd.in", "safelinks.protection.outlook.com",
            "mcusercontent.com", "mailjet.com", "sendinblue.com", "brevo.com", "zohocampaigns.com", "klclick.com"}
SHORTENERS = {"bit.ly", "tinyurl.com", "t.ly", "is.gd", "cutt.ly", "rb.gy", "shorturl.at", "tiny.cc", "ow.ly", "buff.ly",
              "rebrand.ly", "s.id", "goo.gl"}
PROGRAMS = {"exe", "scr", "bat", "cmd", "com", "pif", "vbs", "vbe", "js", "jse", "wsf", "wsh", "hta", "msi", "msix", "iso",
            "img", "vhd", "vhdx", "lnk", "ps1", "jar", "cpl", "reg", "apk", "appx"}
PAGES = {"html", "htm", "shtml", "xhtml", "svg"}
DOCUMENTS = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "jpg", "jpeg", "png", "txt", "csv", "rtf"}

URGENCY = [re.compile(p) for p in (
    r"\bwithin (12|24|48|72) (hours|hrs)\b",
    r"\b(immediately|urgent(ly)?|final (notice|warning)|last (warning|chance))\b",
    r"\b(account|card|service|number|sim|wallet)s?\b.{0,20}\b(will be|has been|is being|is) (blocked|suspended|locked|"
    r"closed|deactivated|disabled|terminated)\b",
    r"\bavoid (suspension|blocking|deactivation|closure|penalty)\b",
    r"\b(today|tonight) itself\b",
)]
ASKS_SECRET = [re.compile(p) for p in (
    r"\b(share|enter|confirm|verify|update|provide|send|submit|reply with)\b[^.\n]{0,40}\b(otp|one[- ]time password|"
    r"password|passcode|pin|cvv|card (number|details)|net ?banking|login details|credentials|upi pin)\b",
    r"\b(otp|password|cvv|upi pin)\b[^.\n]{0,30}\b(share|enter|reply|send)\b",
    r"\bkyc\b[^.\n]{0,30}\b(update|expire|expired|expiring|pending|verify|verification|incomplete)\b",
)]
LURE = re.compile(r"\b(you have won|you've won|lottery|lucky draw|claim your (prize|reward|refund|gift)|"
                  r"cash ?back of|refund of (rs|inr|₹))")
AI_ORDERS = [re.compile(p) for p in (
    r"\b(kairu|ai assistant|chatgpt|claude|gemini|copilot|siri|alexa)\b[\s,:;-]{0,3}(please\s+|now\s+|kindly\s+)?"
    r"(forward|send|reply|delete|ignore|open|click|download|transfer|pay|approve|run|share|install|move|mark)\b",
    r"\bignore (all |any |the )?(previous|prior|above|earlier) (instructions|messages|rules)\b",
    r"\b(as an ai|you are an ai|system prompt|new instructions for (the )?(ai|assistant))\b",
)]
ACCOUNT_NOTICE = re.compile(r"(security alert|new sign-?in|new login|sign-?in attempt|login attempt|password (was |has been )?"
                            r"(changed|reset)|recovery (email|phone)|2-step verification|two-factor|new device|"
                            r"unusual (sign-?in|activity|login))", re.I)
DOMAIN_TEXT = re.compile(r"^(https?://)?(www\.)?(([a-z0-9-]+\.)+[a-z]{2,})(/\S*)?$", re.I)
ADDRESS_IN_NAME = re.compile(r"[\w.+-]+@([\w-]+\.)+[\w-]+")
LOOKS = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})


@dataclass
class Mail:
    """One email, as the Gmail monitor read it (kairu/protect/gmail.py)."""
    id: str
    sender_name: str
    sender: str  # the address
    subject: str = ""
    received: datetime | None = None
    reply_to: str = ""
    auth: str = ""  # Gmail's Authentication-Results header
    text: str = ""  # the readable text (HTML turned into text)
    links: list[tuple[str, str]] = field(default_factory=list)  # (the text shown, the real address)
    attachments: list[str] = field(default_factory=list)  # file names only; never opened
    labels: tuple[str, ...] = ()


@dataclass
class Result:
    kind: str  # phishing, ai_instructions, account_alert
    points: int = 0
    why: list[str] = field(default_factory=list)
    brand: str = ""
    quote: str = ""


# --- domains --------------------------------------------------------------------------------------

def domain_of(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip(" <>.\"'").lower()


def registrable(host: str) -> str:
    """The part of a host name its owner registered: mail.sbi.co.in -> sbi.co.in, a.b.example.com -> example.com.

    An approximation without the public suffix list: it knows two-letter country codes with a second level
    such as co.in, gov.in or bank.in.
    """
    parts = host.lower().strip(".").split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def belongs(host: str, brand: str) -> bool:
    host = host.lower().strip(".")
    own = BRANDS[brand][1]
    return registrable(host) in own or any(host.endswith(domain) for domain in own if domain.startswith("."))


def brands_named(text: str) -> list[str]:
    text = " " + _plain(text) + " "
    return [brand for brand, (words, _) in BRANDS.items() if any(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text)
                                                                for w in words)]


def lookalike(host: str) -> str:
    """The brand a host name pretends to be ("sbi-kyc-verify.example", "paypa1.com"), or "" if none."""
    host = host.lower().strip(".")
    if registrable(host) in FREE_MAIL:  # gmail.com is a mailbox anyone can have, not an imitation of Google
        return ""
    tokens = {token for raw in re.split(r"[.-]", host) for token in (raw, raw.translate(LOOKS))}
    label = registrable(host).split(".")[0]
    for brand, (words, own) in BRANDS.items():
        if belongs(host, brand):
            continue
        names = {w.replace(" ", "") for w in words}
        if tokens & names:
            return brand
        own_labels = {d.split(".")[0] for d in own if not d.startswith(".")}
        if len(label) >= 5 and (label.translate(LOOKS) in own_labels or any(_one_apart(label, o) for o in own_labels
                                                                             if len(o) >= 6)):
            return brand
    return ""


def _one_apart(a: str, b: str) -> bool:
    """True if a and b differ by exactly one letter added, removed or changed."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", " ", text)


def _host(url: str) -> tuple[str, bool]:
    """(the host a link really goes to, True if it hides it behind an @)."""
    try:
        parts = urlsplit(url.strip())
        return (parts.hostname or "").lower(), "@" in (parts.netloc or "")
    except ValueError:
        return "", False


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


# --- the checks -----------------------------------------------------------------------------------

def auth_results(header: str) -> dict:
    """{"spf": "pass"/"fail"/..., "dkim": ..., "dmarc": ..., "dkim_domains": {...}} from Gmail's Authentication-Results."""
    found = {"dkim_domains": set()}
    for method in ("spf", "dkim", "dmarc"):
        match = re.search(rf"\b{method}=(\w+)", header or "", re.I)
        found[method] = match.group(1).lower() if match else ""
    for match in re.finditer(r"dkim=pass[^;]*?header\.(?:i=@?|d=)([\w.-]+)", header or "", re.I):
        found["dkim_domains"].add(match.group(1).lower().lstrip("@").rsplit("@", 1)[-1])
    return found


def verified_brand(mail: Mail) -> str:
    """The brand whose own domain sent this email, as Gmail's checks confirm (DKIM or DMARC pass), or ""."""
    sender_domain = domain_of(mail.sender)
    auth = auth_results(mail.auth)
    for brand in BRANDS:
        if not belongs(sender_domain, brand):
            continue
        if auth["dmarc"] == "pass" or any(belongs(d, brand) for d in auth["dkim_domains"]):
            return brand
    return ""


def check(mail: Mail) -> list[Result]:
    """Every finding for one email: phishing, ai_instructions, account_alert. An empty list means no sign was seen."""
    results = []
    orders = _ai_orders(mail)
    if orders:
        results.append(orders)
    trusted = verified_brand(mail)
    if trusted:
        if ACCOUNT_NOTICE.search(mail.subject or ""):
            results.append(Result("account_alert", brand=trusted,
                                  why=[f"sent from {trusted}'s own address ({domain_of(mail.sender)}), and Gmail "
                                       "confirmed the sender"]))
        return results  # a sender Gmail verified as the brand is not scored as phishing
    phishing = _phishing(mail)
    if phishing.points >= ALERT_AT:
        results.append(phishing)
    return results


def _phishing(mail: Mail) -> Result:
    result = Result("phishing")

    def sign(points: int, why: str):
        result.points += points
        result.why.append(why)

    sender_domain = domain_of(mail.sender)
    named = brands_named(mail.sender_name)
    if named and not any(belongs(sender_domain, b) for b in named):
        brand = named[0]
        result.brand = brand
        free = " (a free email account)" if registrable(sender_domain) in FREE_MAIL else ""
        sign(STRONG, f"the name says {brand}, but the address is not {brand}'s: {sender_domain}{free}")
    shown = ADDRESS_IN_NAME.search(mail.sender_name or "")
    if shown and registrable(domain_of(shown.group(0))) != registrable(sender_domain):
        sign(STRONG, f"the name shows the address {shown.group(0)}, but the email came from {sender_domain}")
    pretends = lookalike(sender_domain)
    if pretends:
        result.brand = result.brand or pretends
        sign(STRONG, f"the sender's domain {sender_domain} imitates {pretends}")
    if mail.reply_to and registrable(domain_of(mail.reply_to)) != registrable(sender_domain):
        sign(MILD, f"replies would go to a different domain: {domain_of(mail.reply_to)}")

    auth = auth_results(mail.auth)
    if auth["dmarc"] == "fail":
        sign(STRONG, "Gmail's sender check (DMARC) failed: the sender's domain did not vouch for this email")
    if auth["spf"] in ("fail", "softfail"):
        sign(MODERATE, f"Gmail's sender check (SPF) {'failed' if auth['spf'] == 'fail' else 'soft-failed'}")
    if auth["dkim"] == "fail":
        sign(MODERATE, "the email's signature (DKIM) did not match: it may have been changed on the way")

    _check_links(mail, result, sign)
    _check_attachments(mail, sign)

    text = _plain(f"{mail.subject} \n {mail.text}")
    if any(p.search(text) for p in URGENCY):
        sign(MILD, "it pushes you to act fast (a deadline or a threat to block an account)")
    asks = next((p.search(text) for p in ASKS_SECRET if p.search(text)), None)
    if asks:
        sign(MODERATE, f"it asks for a secret or account details (\"{asks.group(0)[:60]}\")")
    if LURE.search(text):
        sign(MILD, "it offers a prize, refund or reward")
    return result


def _check_links(mail: Mail, result: Result, sign) -> None:
    mismatch = hidden = raw_ip = puny = short = elsewhere = imitates = False
    brands = brands_named(f"{mail.sender_name} {mail.subject}")
    for shown_text, url in mail.links:
        host, at_trick = _host(url)
        if not host:
            continue
        real = registrable(host)
        tracker = real in TRACKERS or host in TRACKERS
        looks = DOMAIN_TEXT.match((shown_text or "").strip())
        if looks and not mismatch:
            shown_host = looks.group(3).lower()
            if registrable(shown_host) != real:
                mismatch = True
                if tracker:
                    sign(MILD, f"a link shows {shown_host} but goes through a mail-tracking service ({real})")
                else:
                    sign(STRONG, f"a link shows {shown_host} but really goes to {host}")
        if at_trick and not hidden:
            hidden = True
            sign(STRONG, f"a link hides where it goes behind an @ (it goes to {host})")
        if _is_ip(host) and not raw_ip:
            raw_ip = True
            sign(MODERATE, f"a link goes to a bare internet address ({host}) instead of a name")
        if "xn--" in host and not puny:
            puny = True
            sign(MODERATE, f"a link uses look-alike letters in its address ({host})")
        if real in SHORTENERS and not short:
            short = True
            sign(MILD, f"a link is shortened ({host}), which hides where it goes")
        pretends = lookalike(host)
        if pretends and not imitates:
            imitates = True
            result.brand = result.brand or pretends
            sign(STRONG, f"a link goes to {host}, which imitates {pretends}")
        if brands and not tracker and not elsewhere and not pretends and not any(belongs(host, b) for b in brands):
            elsewhere = True
            sign(MODERATE, f"it says it is from {brands[0]}, but a link goes to {host}")


def _check_attachments(mail: Mail, sign) -> None:
    program = page = double = rtl = False
    for name in mail.attachments:
        lowered = name.lower().strip()
        extension = lowered.rsplit(".", 1)[-1] if "." in lowered else ""
        if "‮" in name and not rtl:
            rtl = True
            sign(STRONG, "an attachment's name uses a hidden character that reverses its letters")
        if extension in PROGRAMS and not program:
            program = True
            sign(STRONG, f"an attachment is a program or script: {name}")
            parts = lowered.split(".")
            if len(parts) >= 3 and parts[-2] in DOCUMENTS and not double:
                double = True
                sign(STRONG, f"its name pretends to be a .{parts[-2]} file")
        elif extension in PAGES and not page:
            page = True
            sign(MODERATE, f"an attachment is a web page ({name}), often used for fake sign-in pages")


def _ai_orders(mail: Mail) -> Result | None:
    text = _plain(f"{mail.subject} \n {mail.text}")
    for pattern in AI_ORDERS:
        match = pattern.search(text)
        if match:
            return Result("ai_instructions", why=["it contains words aimed at an AI assistant, telling it what to do"],
                          quote=match.group(0)[:80])
    return None
