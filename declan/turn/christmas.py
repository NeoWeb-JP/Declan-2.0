"""Christmas mode (FUT-59, #834).

On automatically from 1 December to 2 January (Settings -> Household), or by
voice: "Christmas mode on/off". While it's on:

- Christmas lines join Declan's everyday sass (about half the time), so lights,
  timers, greetings, routines and dinner get seasonal roasts. They rest and get
  topped up like every other line (FUT-61).
- "Play some music" prefers the Christmas playlist category when it has playlists.
- On Boxing Day music starts no louder than 20%, and good morning gets the
  hangover lines.

Always available: "how many sleeps till Christmas?", and several cooking timers
in one sentence ("set a turkey timer for 3 hours and a roast potatoes timer for
50 minutes"), which live in compound_commands.
"""
import re
from datetime import date, datetime
from random import SystemRandom

MODES = ("auto", "on", "off")
_RANDOM = SystemRandom()
SEASONAL_SHARE = 0.5

LINES = {
    "mode_on": (
        "Christmas mode on. The house is full of tinsel and people who don't know how anything works. Lekker.",
        "Christmas mode on. I've been told to be festive. I'll be festive at you.",
        "Ja, fine, Christmas mode. Somebody tell the tinsel it's not the boss of me.",
    ),
    "mode_off": (
        "Christmas mode off. The tinsel can go back in the box, and so can the relatives.",
        "Christmas is cancelled. I'll tell the reindeer, you tell the in-laws.",
    ),
    "lights_on": (
        "Back home we'd be on the beach right now, but sure, let's sit inside next to a plastic pine.",
        "There. Festive enough for you, boet?",
        "Lights on. The tinsel thanks you. Nobody else does.",
    ),
    "lights_off": (
        "Lights off. Santa can find his own way in, the cheeky bugger.",
        "Off. Saving electricity for the fairy lights, I see.",
    ),
    "timer_set": (
        "If the turkey comes out dry, I'm blaming the cook, not the timer.",
        "Timer set. Last year's roast potatoes still haunt me, my bru.",
        "Ticking. Keep the gravy off my screen this time.",
    ),
    "general": (
        "Gravy on my screen now as well? Who's cleaning up that shit?",
        "Merry Christmas, you lazy sod. Even the elves do their own switches.",
        "Done. Put it on my list of Christmas miracles.",
        "Sorted, boet. I'll take my bonus in mince pies I can't eat.",
    ),
    "greeting": (
        "Howzit, and merry Christmas. What festive nonsense do you need now?",
        "Season's greetings, boet. Make it quick, the tinsel needs supervising.",
    ),
    "guest_on": (
        "More guests? Wonderful. More people shouting at the wrong satellite.",
        "Guests again? I'll hide the good biscuits.",
    ),
    "morning": (
        "Morning, boet. Christmas is coming and so is the washing up.",
        "Rise and shine. The tree's still standing, which is more than I can say for you.",
    ),
    "night": (
        "Good night. Leave a beer out for Father Christmas; he's had a long shift too.",
        "Bedtime. If you hear reindeer on the roof, that's not my department.",
    ),
    "dinner": (
        "Christmas dinner is served. Loosen the belts and pass the gravy. Not to my screen.",
        "Dinner time. Somebody cut the turkey before the dog does.",
    ),
    "boxing_day": (
        "Volume down. I can hear the hangover from here, my bru.",
        "Boxing Day. Gently does it; your liver has filed a complaint.",
        "Morning. Leftovers for breakfast, lunch and supper. Lekker.",
    ),
    "countdown": (
        "Eleven if you count the one on the couch after lunch.",
        "Better start on the presents, boet. The shops won't raid themselves.",
        "And no, I'm not wrapping anything. No hands.",
    ),
}
TOPICS = {name: f"Christmas-themed: {text}" for name, text in {
    "lights_on": "after turning lights or the Christmas tree lights on",
    "lights_off": "after turning lights off",
    "timer_set": "after setting a Christmas cooking timer (turkey, roast potatoes, pudding)",
    "general": "after doing a household job over Christmas with a house full of people",
    "greeting": "greeting someone over Christmas", "guest_on": "guests have just arrived for Christmas",
    "morning": "saying good morning in the Christmas holidays", "night": "saying good night at Christmas",
    "dinner": "announcing Christmas dinner", "boxing_day": "a hungover Boxing Day morning",
    "mode_on": "switching Christmas mode on", "mode_off": "switching Christmas mode off",
    "countdown": "a joke after saying how many sleeps are left until Christmas",
}.items()}
# Everyday line categories that get Christmas lines while the mode is on.
CATEGORY_MAP = {"lights_on": "lights_on", "full_brightness": "lights_on", "lights_off": "lights_off",
                "timer_set": "timer_set", "greeting": "greeting", "general": "general",
                "good_morning": "morning", "morning": "morning", "good_night": "night", "night": "night",
                "dinner": "dinner", "dinner_announcement": "dinner", "guest_on": "guest_on"}

_MODE = re.compile(r"(?:(?:turn|switch|put) (on|off) )?(?:the )?christmas (?:mode|spirit)(?: (on|off))?|"
                   r"(start|stop|end|cancel) (?:the )?christmas(?: mode)?|"
                   r"(?:is it|are we in) christmas mode|is christmas mode on")
# Guests ask for the Wi-Fi every way imaginable, and speech-to-text drops apostrophes, so any mention of the
# Wi-Fi with a password/details/join word counts, unless it's a command to change or control the network.
_WIFI_NET = r"(?:wi-?fi|wi fi|wireless|internet|network)"
_WIFI_ASK = re.compile(r"\b(?:password|passcode|pass word|code|key|details|login|log in|name)\b|"
                       r"\b(?:join|connect|get on|get onto|log on|log onto|hook up|access)\b")
_WIFI_BARE = re.compile(r"(?:what(?:'s|s| is)|which is) (?:the |your )?(?:guest )?(?:wi-?fi|wi fi|wireless)")
_WIFI_CONTROL = re.compile(r"\b(?:change|reset|update|turn|switch|restart|reboot|disable|enable|block|"
                           r"kick|pause|forget|delete|remove|speed|slow|down|router)\b")
_WIFI_NET_RE = re.compile(r"\b" + _WIFI_NET + r"\b")


def _is_wifi_question(text):
    if _WIFI_CONTROL.search(text):
        return False
    if _WIFI_BARE.fullmatch(text):
        return True
    return bool(_WIFI_NET_RE.search(text) and _WIFI_ASK.search(text))
_SLEEPS = re.compile(r"(?:how many|how much) (?:sleeps|days|more sleeps|more days) (?:is it |are there |left )?"
                     r"(?:till|until|to|before|left (?:till|until|to|before)) christmas|"
                     r"how long (?:is it |left )?(?:till|until|to|before) christmas|when is christmas")


def mode():
    from declan.turn import household_settings
    try:
        value = household_settings.listing()["settings"]["christmas"]
    except (OSError, ValueError, KeyError, TypeError):
        return "auto"
    return value if value in MODES else "auto"


def in_season(today=None):
    today = today or now_date()
    return (today.month == 12 and today.day >= 1) or (today.month == 1 and today.day <= 2)


def active(today=None):
    current = mode()
    return current == "on" or (current == "auto" and in_season(today))


def boxing_day(today=None):
    today = today or now_date()
    return active(today) and (today.month, today.day) == (12, 26)


def seasonal(category, *, today=None, coin=None):
    """Christmas lines to use for ``category`` this time, or None for the normal ones."""
    if not active(today):
        return None
    name = CATEGORY_MAP.get(category)
    if name == "morning" and boxing_day(today):
        return "boxing_day"
    if name is None:
        return None
    return name if (coin if coin is not None else _RANDOM.random()) < SEASONAL_SHARE else None  # nosec B311 - variety only


def pick(name, *, polite=False):
    from declan.turn import line_freshness
    return line_freshness.pick("christmas:" + name, LINES[name], topic=TOPICS[name], polite=polite)


def match(phrase):
    """("mode", "on"|"off"|"status") or ("sleeps", None), else None."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    found = _MODE.fullmatch(text)
    if found:
        verb = found[1] or found[2] or found[3]
        if verb is None:
            return ("mode", "status")
        return ("mode", "on" if verb in {"on", "start"} else "off")
    if _SLEEPS.fullmatch(text):
        return ("sleeps", None)
    if _is_wifi_question(text):
        return ("wifi", None)
    return None


def sleeps(today=None):
    today = today or now_date()
    christmas = date(today.year, 12, 25)
    if today > christmas:
        christmas = date(today.year + 1, 12, 25)
    return (christmas - today).days


def answer(request, *, today=None, save=None):
    """Spoken reply for a matched Christmas request; save(mode) stores a voice change."""
    from declan.turn import personality_dials
    kind, value = request
    if kind == "wifi":
        return wifi_answer()
    if kind == "sleeps":
        days = sleeps(today)
        if days == 0:
            return personality_dials.fixed("It's Christmas, boet! Zero sleeps. Go and open something.")
        head = "One sleep till Christmas." if days == 1 else f"{days} sleeps till Christmas."
        return head + (" " + pick("countdown") if active(today) else "")
    if value == "status":
        current, on = mode(), active(today)
        how = {"on": "switched on", "off": "switched off", "auto": "on from 1 December to 2 January"}[current]
        return f"Christmas mode is {'on' if on else 'off'} right now. It's {how} in Settings."
    (save or _save_mode)(value)
    return pick("mode_on" if value == "on" else "mode_off")


def wifi_answer():
    """The guest Wi-Fi from Settings -> Household; guests are exactly who ask (off until set)."""
    from declan.turn import household_settings, personality_dials
    try:
        settings = household_settings.listing()["settings"]
    except (OSError, ValueError, KeyError, TypeError):
        settings = {}
    name, password = settings.get("wifi_name") or "", settings.get("wifi_password") or ""
    if not password:
        return personality_dials.fixed("Nobody's told me the Wi-Fi password, boet. Ask your host.")
    spelled = " ".join(password) if len(password) <= 24 else password
    network = f"The Wi-Fi is {name}. " if name else ""
    return f"{network}The password is {password}. Spelled out: {spelled}."


def _save_mode(value):
    from declan.turn import household_settings
    current = household_settings.listing()["settings"]
    household_settings.save({"guest_tone": current["guest_tone"], "christmas": value})


def now_date():
    return datetime.now().astimezone().date()
