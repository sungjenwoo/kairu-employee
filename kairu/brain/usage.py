"""What `kairu usage` shows: per provider, today's questions, how much of its free limit is used, and every switch.

The share of the free limit comes from what the provider itself reported with its last answer when it
reports it (Groq, OpenRouter); otherwise it is Kairu's own count against the published free limit, or
for Cloudflare an estimate in neurons from the answers' length. There is no cap unless you set one
(brain.daily_cap in config.yaml, ADR-006).
"""

import time
from datetime import datetime

from kairu.brain import keys
from kairu.brain.providers import PROVIDERS, next_utc_midnight
from kairu.brain.store import BrainStore, start_of_today

CLOUDFLARE_NEURONS = 10_000


def clock(moment: float) -> str:
    local = datetime.fromtimestamp(moment).astimezone()
    hour = local.hour % 12 or 12
    when = f"{hour}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"
    return when if local.date() == datetime.now().astimezone().date() else f"{local.strftime('%a')} {when}"


def state(data_dir, name: str, store: BrainStore, now: float | None = None) -> tuple[bool, str]:
    """(ready, in words): whether Kairu would use this provider now, and why not."""
    now = time.time() if now is None else now
    if not keys.has(data_dir, name):
        return False, f"not set up (`kairu provider add {name}`)"
    limit = store.limit(name)
    if limit and limit.until > now:
        until = "until you add its key again" if limit.until - now > 86400 * 300 else f"until {clock(limit.until)}"
        return False, f"{limit.why} {until}"
    return True, "ready"


def share(name: str, store: BrainStore, counted: tuple[int, int, int] | None, model_changed: bool) -> str:
    """How much of today's free limit is used, in words, with where the number comes from."""
    provider = PROVIDERS[name]
    questions, tokens_in, tokens_out = counted or (0, 0, 0)
    limit = store.limit(name)
    fresh = limit and limit.seen and limit.seen >= start_of_today() and limit.day_limit
    if fresh and limit.day_left is not None:
        used = max(0, limit.day_limit - limit.day_left)
        return f"{used * 100 / limit.day_limit:.0f}% of its free limit used ({provider.label} says {limit.day_left:,} " \
               f"of {limit.day_limit:,} left)"
    if provider.per_day:
        return f"about {questions * 100 / provider.per_day:.0f}% of its free limit ({questions} of {provider.per_day:,}, " \
               "Kairu's own count)"
    if provider.neurons and not model_changed:
        neurons = tokens_in * provider.neurons[0] / 1e6 + tokens_out * provider.neurons[1] / 1e6
        return f"about {neurons * 100 / CLOUDFLARE_NEURONS:.1f}% of its {CLOUDFLARE_NEURONS:,} free neurons " \
               f"(estimated from the answers' length; new at {clock(next_utc_midnight(time.time()))})"
    return f"{questions} question{'s' if questions != 1 else ''} (its free limit is counted in another unit)"


def report(data_dir, settings: dict) -> list[str]:
    """The lines of `kairu usage`."""
    store = BrainStore(data_dir)
    today = store.usage()
    order = list(settings.get("providers") or PROVIDERS)
    models = settings.get("models") or {}
    lines = [f"Kairu usage, today ({datetime.now().strftime('%d %b')}), in the order Kairu tries them:"]
    for name in order:
        counted = today.get(name)
        ready, words = state(data_dir, name, store)
        questions = counted[0] if counted else 0
        used = share(name, store, counted, name in models) if keys.has(data_dir, name) else ""
        lines.append(f"  {PROVIDERS[name].label:<11} {questions:>4} question{'s' if questions != 1 else ' '}  "
                     f"{words}{'; ' + used if used else ''}")
    for name in [name for name in today if name not in order]:
        lines.append(f"  {PROVIDERS[name].label if name in PROVIDERS else name:<11} {today[name][0]:>4} questions  "
                     "(no longer in brain.providers)")
    switches = store.events(start_of_today())
    if switches:
        lines.append("  Today's switches and limits:")
        for at, _, _, note in switches[-12:]:
            lines.append(f"    {clock(at):>8}  {note}")
    else:
        lines.append("  No switches today.")
    cap = settings.get("daily_cap") or 0
    total = sum(counted[0] for counted in today.values())
    lines.append(f"  Cap: {cap} cloud questions a day ({total} used)" if cap else
                 "  Cap: none (brain.daily_cap in config.yaml sets one, if you ever want it)")
    lines.append("  Public questions go to the cloud without asking (option A)." if settings.get("public_to_cloud")
                 else "  Every cloud question waits for your \"yes\" and PIN (brain.public_to_cloud is false).")
    return lines


def short(data_dir, settings: dict) -> str:
    """One line for a question about usage (L0)."""
    store = BrainStore(data_dir)
    today = store.usage()
    parts = []
    for name in settings.get("providers") or PROVIDERS:
        ready, words = state(data_dir, name, store)
        if not keys.has(data_dir, name):
            continue
        counted = today.get(name, (0, 0, 0))
        parts.append(f"{PROVIDERS[name].label} {counted[0]} question{'s' if counted[0] != 1 else ''}"
                     + ("" if ready else f" ({words})"))
    if not parts:
        return "No free AI provider is set up yet: `kairu provider add groq` (BRAIN.md)."
    return "Today: " + ", ".join(parts) + ". `kairu usage` shows the limits and every switch."
