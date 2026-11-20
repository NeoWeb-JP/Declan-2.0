"""#373: optional voice command style gate ("question-first" / "my bru" sign-off).

Owner decisions (20 Nov, #802 D6): off by default; a rejected command is
silent (empty reply, conversation closed, nothing run, no retry window); the
opener list is the one #801 already understands; control words and real
questions always pass. Only satellite / HA Assist turns are gated. Typed chat
and the panel microphone are never gated.

A value saved in Settings -> Voice & learning wins, then DECLAN_COMMAND_STYLE,
then "any".
"""
import json
import os
import re
from pathlib import Path

STYLES = ("any", "question", "my_bru", "either")
ENVIRONMENT = "DECLAN_COMMAND_STYLE"
DEFAULT = "any"
PATH = Path(__file__).resolve().parents[2] / ".data" / "command-style.json"
GATED_SOURCES = frozenset({"assist"})

# Wake-word echo and fillers some STT engines keep at the start.
_LEAD_NOISE = re.compile(r"^(?:(?:hey|ok|okay|howzit|hi)\s+)?declan\b[,.!]?\s*")
# Openers from #801's polite-request wrapper, minus a bare leading "please".
_QUESTION_OPENER = re.compile(
    r"^(?:please,? )?(?:(?:can|could|would|will) you|(?:would|do) you mind)\b,?\s+\S")
_MY_BRU_TAIL = re.compile(r"(?:^|,?\s)my bru(?:,? (?:please|thanks|thank you))*[.!?]*$")
# Real questions and control words always pass.
_QUESTION_WORDS = frozenset({
    "what", "what's", "whats", "who", "who's", "whos", "when", "where", "where's", "which",
    "why", "how", "how's", "hows", "is", "are", "am", "do", "does", "did", "was", "were",
    "has", "have", "should", "shall",
})
CONTROL_PHRASES = frozenset({
    "stop", "cancel", "never mind", "nevermind", "forget it", "stop listening",
    "stop routine", "cancel routine", "yes", "no", "yes please", "no thanks",
    "yes confirm", "confirm", "go ahead", "do it",
})


def _valid(value):
    return isinstance(value, str) and value in STYLES


def listing(path=None):
    path = PATH if path is None else path
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8")).get("style")
    except (FileNotFoundError, ValueError, OSError, AttributeError):
        saved = None
    if _valid(saved):
        return {"style": saved, "source": "saved"}
    environment = os.environ.get(ENVIRONMENT, "").strip().lower()
    if _valid(environment):
        return {"style": environment, "source": "environment"}
    return {"style": DEFAULT, "source": "default"}


def style(path=None):
    return listing(path)["style"]


def save(payload, path=None):
    path = Path(PATH if path is None else path)
    if not isinstance(payload, dict) or set(payload) != {"style"} or not _valid(payload["style"]):
        raise ValueError("Choose any, question, my_bru or either.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"style": payload["style"]}) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return listing(path)


def _clean(phrase):
    phrase = " ".join(phrase.casefold().replace("’", "'").split()).strip(" .!?,")
    return _LEAD_NOISE.sub("", phrase).strip(" ,")


def rejection(phrase, *, mode, source, awaiting_reply=False):
    """Return why a turn is ignored under ``mode``, or None when it may run.

    ``phrase`` is the spoken command after self-correction and filler removal.
    ``awaiting_reply`` is true when Declan itself just asked something (a
    rephrase retry), so the answer is never gated.
    """
    if mode not in STYLES or mode == "any" or source not in GATED_SOURCES or awaiting_reply:
        return None
    if not isinstance(phrase, str):
        return "empty"
    text = _clean(phrase)
    if not text:
        return "empty"
    if text in CONTROL_PHRASES or text.split()[0] in _QUESTION_WORDS:
        return None
    question = bool(_QUESTION_OPENER.match(text))
    my_bru = bool(_MY_BRU_TAIL.search(text)) and len(text.split()) > 2
    if mode == "question" and question:
        return None
    if mode == "my_bru" and my_bru:
        return None
    if mode == "either" and (question or my_bru):
        return None
    return {"question": "not_a_question", "my_bru": "no_my_bru", "either": "no_opener_or_my_bru"}[mode]
