"""Declan's self-report (FUT-50, #834).

"How are you, Declan?", "how's it going?", "status report": a short answer
in character, with:
- how long he's been running;
- how many of today's requests he didn't catch (the same "not understood"
  count as the Understanding card: the unmatched rephrase reply);
- this month's AI spend against the monthly AI budget ("pocket money").

Guests get the uptime and a quip, not the household's numbers. Anything that
can't be read is left out rather than guessed.
"""
import re
import sqlite3
from datetime import datetime
from time import time

from declan.core.execution_results import ExecutionResult, Outcome

STARTED = time()  # replaced by mark_started() when the server starts
_ASK = re.compile(
    r"(?:and )?how (?:are|r) (?:you|ya|u)(?: (?:doing|today|holding up|keeping|feeling))?"
    r"|how(?:'s| is) it going|how(?:'s| is) your day(?: going)?|how(?:'s| is) life"
    r"|(?:give me (?:a |your )?)?status report|how are things(?: with you)?|you (?:ok|okay|alright)"
    r"|how(?:'s| is) declan(?: doing)?"
)
OPENERS = (
    "Still standing, boet.",
    "Lekker, thanks for asking. Nobody ever asks.",
    "Surviving this household, just.",
)
OPENERS_TOPIC = "Declan saying how he is when asked 'how are you', before his status numbers"


def mark_started(now=None):
    global STARTED
    STARTED = time() if now is None else now


def match(phrase):
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:hey |howzit |hi |hello |morning |evening )?(?:declan,? )?", "", text)
    text = re.sub(r",? (?:declan|my bru|boet)$", "", text)
    return ("self_report",) if _ASK.fullmatch(text) else None


def uptime(seconds):
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60

    def unit(count, name):
        return f"{count} {name}" + ("" if count == 1 else "s")
    if days:
        return unit(days, "day") + (f" and {unit(hours, 'hour')}" if hours else "")
    if hours:
        return unit(hours, "hour") + (f" and {unit(minutes, 'minute')}" if minutes else "")
    return unit(max(minutes, 1), "minute")


def today_misses(*, now=None):
    """(requests today, not understood today) from History, same rules as the Understanding card."""
    from declan.core import history
    from declan.core.understanding_quality import REQUEST_SOURCES
    from declan.turn.command_vocabulary import UNMATCHED_REPLY
    now = time() if now is None else now
    midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    with history.database() as connection:
        rows = connection.execute(
            "SELECT source, message, reply, outcome FROM turns "
            "WHERE typeof(created_at) IN ('integer', 'real') AND created_at BETWEEN ? AND ?", (midnight, now)).fetchall()
    turns = misses = 0
    for source, message, reply, outcome in rows:
        if source not in REQUEST_SOURCES or outcome in {"duplicate", "ignored"} or not isinstance(message, str):
            continue
        turns += 1
        misses += int(isinstance(reply, str) and reply.startswith(UNMATCHED_REPLY))
    return turns, misses


def spend():
    """(spent this month, monthly budget) in USD from the AI ledger and AI settings."""
    from decimal import Decimal

    from declan.ai import ai_budget, ai_settings
    from declan.core import history
    with history.database() as connection:
        spent = ai_budget.monthly_reserved(connection) / 1_000_000
    budget = float(Decimal(str(ai_settings.read()["monthly_budget_usd"])))
    return spent, budget


def _money(amount):
    return f"${amount:,.2f}"


def result(request, *, guest, now=None):
    if request is None:
        return None
    from declan.turn import line_freshness
    now = time() if now is None else now
    parts = [line_freshness.pick("self_report:opener", OPENERS, topic=OPENERS_TOPIC),
             f"I've been up {uptime(now - STARTED)}."]
    if guest:
        parts.append("The rest is household business.")
        return ExecutionResult(" ".join(parts), Outcome.CHAT_ANSWER)
    try:
        turns, misses = today_misses(now=now)
    except (OSError, sqlite3.Error, ValueError):
        turns = misses = None
    if turns:
        if misses:
            parts.append(f"Today I didn't catch {misses} of your {turns} requests"
                         + (". Mumble less." if misses * 5 >= turns else "."))
        else:
            parts.append(f"Today I've understood all {turns} of your requests. Not bad, hey?")
    try:
        spent, budget = spend()
    except (OSError, sqlite3.Error, ValueError, KeyError, ArithmeticError):
        spent = budget = None
    if spent is not None and budget:
        parts.append(f"I've spent {_money(spent)} of my {_money(budget)} pocket money this month.")
    return ExecutionResult(" ".join(parts), Outcome.CHAT_ANSWER)
