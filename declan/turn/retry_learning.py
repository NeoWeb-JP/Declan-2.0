"""Conservative matching for a successful rephrasing of a missed request."""
import re
from difflib import SequenceMatcher

WINDOW_SECONDS = 30
CANCEL = {"cancel", "stop", "never mind", "nevermind", "forget it", "stop listening"}
_FILLER = {"please", "the", "a", "an", "it", "um", "umm", "uh", "can", "could", "you", "me", "to"}
_ALIASES = {"lights": "light", "switch": "turn", "switches": "turn"}


def similar(first, second):
    """Reject changes to direction, numbers or named targets, even in similar text."""
    def words(text):
        return [_ALIASES.get(w, w) for w in re.findall(r"[\w]+", text.casefold())
                if w not in _FILLER and _ALIASES.get(w, w) != "turn"]
    left, right = words(first), words(second)
    if not left or not right or left == right:
        return bool(left and right)
    protected = {"on", "off", "open", "close", "up", "down", "start", "stop", "pause", "resume", "lock", "unlock"}
    if any(w in {"and", "then", "also", "except", "but"} for w in left + right):
        return False
    if any(len({w for w in phrase if w in protected}) > 1 for phrase in (left, right)):
        return False
    if ({w for w in left if w in protected or any(c.isdigit() for c in w)} !=
            {w for w in right if w in protected or any(c.isdigit() for c in w)}):
        return False
    if set(left) == set(right):
        return True
    # Only tolerate tiny transcription differences. Shared boilerplate such as
    # "turn the light on" must never alias kitchen to bedroom or study to office.
    extra_left, extra_right = set(left) - set(right), set(right) - set(left)
    if len(extra_left) != len(extra_right):
        return False
    for word in extra_left:
        matches = [other for other in extra_right if min(len(word), len(other)) >= 4
                   and SequenceMatcher(None, word, other).ratio() >= 0.8]
        if len(matches) != 1:
            return False
        extra_right.remove(matches[0])
    return SequenceMatcher(None, ' '.join(left), ' '.join(right)).ratio() >= 0.75
