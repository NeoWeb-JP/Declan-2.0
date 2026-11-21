"""Timed reminders (FUT-26, #834), built on the timer engine.

"Remind me at six to put the bins out", "remind me in 20 minutes to check the
oven", "remind Edd tomorrow at 8 to call the plumber". The reminder rings on
the satellite that heard it, speaking "Reminder: put the bins out." every
30 seconds until someone says "stop" (or for ten minutes), exactly like a
timer. "What reminders do I have?" and "cancel the bins reminder" work too.

Optionally the first ring also goes to phones: set DECLAN_REMINDER_NOTIFY to
one or more notify services, e.g. "notify.mobile_app_jaco,notify.mobile_app_edd".

Reminders for someone else ring in the room where they were set; delivering
them when that person arrives home is FUT-34.
"""
import re
from datetime import datetime, timedelta

PREFIX = "reminder: "
MAX_SECONDS = 7 * 86400
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_CLOCK = (r"(?P<hour>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
          r"(?:[:.](?P<minute>\d{2})| (?P<minute_words>o'clock|thirty|fifteen|forty five|forty-five))?"
          r"(?: ?(?P<ampm>am|pm|a\.m\.|p\.m\.|in the morning|in the evening|tonight|in the afternoon))?|"
          r"(?P<named>noon|midday|midnight)|half past (?P<half>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)")
_WHEN = rf"(?:in (?P<duration>.+?)|(?P<tomorrow>tomorrow )?(?:at )?(?:{_CLOCK})(?P<tomorrow2> tomorrow)?)"
_WHO = r"(?P<who>me|us|edd|ed|jaco|[a-z]+)"
_FORMS = (
    re.compile(rf"(?:please )?remind {_WHO} {_WHEN} (?:to |that |about )(?P<text>.+)"),
    re.compile(rf"(?:please )?remind {_WHO} (?:to |that |about )(?P<text>.+?) {_WHEN}"),
    re.compile(rf"(?:set|add) a reminder (?:for )?{_WHEN} (?:to |that |about |for )(?P<text>.+)"),
)
_LIST = re.compile(r"(?:what|which|any) reminders(?: do (?:i|we) have| are (?:there|set))?|list (?:my |the |all )?reminders")
_CANCEL = re.compile(r"(?:cancel|delete|remove|forget) (?:the |my )?(?:reminder (?:to |about |for )(?P<text>.+)|"
                     r"(?P<text2>.+?) reminder|(?P<all>all (?:my |the )?reminders|my reminders|reminders))")


def is_reminder(name):
    return isinstance(name, str) and name.startswith(PREFIX)


def label(name):
    return "reminder to " + name.removeprefix(PREFIX) if is_reminder(name) else name


def spoken(name):
    text = name.removeprefix(PREFIX)
    who, _, rest = text.partition(": ")
    return f"Reminder for {who}: {rest}." if rest else f"Reminder: {text}."


def _hour(value):
    return int(value) if value.isdigit() else _NUMBER_WORDS[value]


def _long_duration(text):
    """Timers stop at 24 hours; reminders also take "3 days" or "30 hours"."""
    found = re.fullmatch(r"(?P<amount>\d{1,3}|a|an|one|two|three|four|five|six|seven) (?P<unit>days?|hours?|weeks?)", text.strip())
    if not found:
        return None
    amount = found["amount"]
    number = 1 if amount in {"a", "an"} else int(amount) if amount.isdigit() else _NUMBER_WORDS[amount]
    return number * {"d": 86400, "h": 3600, "w": 7 * 86400}[found["unit"][0]]


def deadline(found, now, duration_seconds):
    """Unix time for the matched "in 20 minutes" / "at six" / "tomorrow at 8", or None."""
    if found["duration"]:
        seconds = duration_seconds(found["duration"]) or _long_duration(found["duration"])
        return now.timestamp() + seconds if seconds else None
    if found["named"]:
        hour, minute = (0, 0) if found["named"] == "midnight" else (12, 0)
        candidates = [(hour, minute)]
    else:
        if found["half"]:
            hour, minute = _hour(found["half"]), 30
        else:
            hour = _hour(found["hour"])
            words = found["minute_words"] or ""
            minute = int(found["minute"]) if found["minute"] else {"thirty": 30, "fifteen": 15}.get(words, 45 if "forty" in words else 0)
        if hour > 23 or minute > 59:
            return None
        ampm = (found["ampm"] or "") if not found["half"] else ""
        if hour > 12 or hour == 0:
            candidates = [(hour, minute)]
        elif ampm.startswith(("p", "in the evening", "tonight", "in the afternoon")):
            candidates = [(hour % 12 + 12, minute)]
        elif ampm.startswith(("a", "in the morning")):
            candidates = [(hour % 12, minute)]
        else:
            candidates = [(hour % 12, minute), (hour % 12 + 12, minute)]
    tomorrow = bool(found["tomorrow"] or found["tomorrow2"])
    days = (1,) if tomorrow else (0, 1)
    for day in days:
        for hour, minute in candidates:
            moment = (now + timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if moment > now:
                return moment.timestamp()
    return None


def parse(phrase, *, now=None, duration_seconds=None):
    """("set", name, deadline) | ("list",) | ("cancel", text or None) or None."""
    if not isinstance(phrase, str):
        return None
    from declan.timers.timers import duration_seconds as default_duration
    duration_seconds = duration_seconds or default_duration
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    if _LIST.fullmatch(text):
        return ("list",)
    if found := _CANCEL.fullmatch(text):
        if found["all"]:
            return ("cancel", None)
        target = (found["text"] or found["text2"] or "").strip()
        return ("cancel", re.sub(r"^(?:the|my) ", "", target)) if target and "timer" not in target else None
    now = now or datetime.now().astimezone()
    for form in _FORMS:
        found = form.fullmatch(text)
        if not found:
            continue
        message = found["text"].strip(" .")
        message = re.sub(r"^(?:i |we )(?:need|have) to ", "", message)
        if not message or len(message) > 120:
            return None
        when = deadline(found, now, duration_seconds)
        who = found.groupdict().get("who") or "me"
        name = PREFIX + (message if who in {"me", "us"} else f"{who.capitalize()}: {message}")
        return ("set", name, when)
    return None
