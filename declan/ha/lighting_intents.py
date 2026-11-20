"""Lighting phrase handling with injected parser and execution dependencies."""
import re

from declan.core.execution_results import ExecutionResult, Outcome


_LIGHT_WORDS = r"(?:lights?|lamps?|spots?|spotlights?|bulbs?|pendants?|lighting)"
_PERCENT = r"(?P<level>\d{1,3})\s*(?:percent|per cent|%)"
_BRIGHTNESS_VARIANTS = (
    # "turn the kitchen lights to 40%", "put the lamp at 30 percent"
    re.compile(r"(?:turn|put|make) (?:the )?(?P<name>.*?\b" + _LIGHT_WORDS + r"\b.*?) (?:to|at) " + _PERCENT
               + r"(?P<here> in here)?"),
    # "kitchen lights 50 percent", "the lamp to 20%"
    re.compile(r"(?:the )?(?P<name>.*?\b" + _LIGHT_WORDS + r"\b.*?) (?:to |at )?" + _PERCENT
               + r"(?P<here> in here)?"),
    # "brightness to 40 percent in the kitchen", "set the brightness in the office to 70%"
    re.compile(r"(?:set |change |put )?(?:the )?brightness(?: in (?:the )?(?P<room_first>.+?))? (?:to |at )?"
               + _PERCENT + r"(?: in (?:the )?(?P<room>.+))?"),
)


def canonical_brightness(phrase):
    """Rewrite loose percentage wording to "set the <x> to <n> percent"; else unchanged."""
    if not isinstance(phrase, str) or not re.search(r"\d\s*(?:percent|per cent|%)", phrase):
        return phrase
    if (re.match(r"(?:set|dim|brighten) ", phrase) and "brightness" not in phrase) or re.search(r" by \d", phrase):
        return phrase  # Already canonical, or a relative "by N percent" change.
    for pattern in _BRIGHTNESS_VARIANTS:
        match = pattern.fullmatch(phrase)
        if not match:
            continue
        groups = match.groupdict()
        name = groups.get("name")
        if name is None:
            room = groups.get("room_first") or groups.get("room")
            name = f"lights in the {room}" if room and room != "here" else "lights"
            suffix = " in here" if room == "here" else ""
            return f"set the {name} to {match['level']} percent{suffix}"
        here = " in here" if groups.get("here") or name.endswith(" in here") else ""
        return f"set the {name.removesuffix(' in here')} to {match['level']} percent{here}"
    return phrase


def _lighting_result(value):
    """Validate a lighting execution result at the provider boundary."""
    return value if isinstance(value, ExecutionResult) else ExecutionResult(*value)


def handle_light_request_result(phrase, *, parse_light_command, set_lights, action_results=None, last_lights=(), origin_device=None):
    """Typed lighting intent outcome, or None for an unmatched request."""
    if phrase in {"what lights are on", "which lights are on", "what lights are still on", "which lights are still on"}:
        return _lighting_result(set_lights("", None))
    preview = re.match(r"^(?:preview|dry[ -]run)\b[ ,:]*", phrase)
    if preview:
        phrase = phrase[preview.end():]
    phrase = canonical_brightness(phrase)
    room_adjustment = re.fullmatch(r"make it (darker|lighter|brighter|very bright) in (.+)", phrase)
    turn_adjustment = re.fullmatch(r"turn (down|up) ((?:the )?(?:all )?lights(?: in .+)?)", phrase)
    if room_adjustment:
        phrase = f"make the lights in {room_adjustment[2]} {room_adjustment[1]}"
    elif turn_adjustment:
        direction = "darker" if turn_adjustment[1] == "down" else "brighter"
        phrase = f"make {turn_adjustment[2]} {direction}"
    if phrase.endswith(" in here"):
        contextual = phrase.removesuffix(" in here")
        level = re.fullmatch(r"(?:set|dim) (?:the )?(?:(?:all )?(?:the )?" + _LIGHT_WORDS + r")? ?to (\d{1,3}) percent",
                             contextual)
        if level:
            level_pct = int(level[1])
            if not 0 <= level_pct <= 100:
                return ExecutionResult("Please choose a brightness from 0 to 100 percent.", Outcome.UNRESOLVED)
            if origin_device is None:
                return ExecutionResult("Which room do you mean? I can't identify a room for this request.",
                                       Outcome.UNRESOLVED)
            return _lighting_result(set_lights("lights", "on" if level_pct else "off", brightness=level_pct or None,
                                               preview=bool(preview), action_results=action_results,
                                               origin_device=origin_device))
        if re.fullmatch(r"make it (?:darker|lighter|brighter|very bright)", contextual):
            contextual = contextual.replace("make it ", "make the lights ", 1)
        command = parse_light_command(contextual)
        if command is None or re.search(r"\b(?:actually|i mean|turn|make|except)\b", command[0]):
            return ExecutionResult("Please give me one lighting action for this room.", Outcome.UNRESOLVED)
        if origin_device is None:
            return ExecutionResult("Which room do you mean? I can't identify a room for this request.", Outcome.UNRESOLVED)
        if command[0] == "some lights" and command[1] != "on":
            return ExecutionResult("Please name the lights you want to change in this room.", Outcome.UNRESOLVED)
        return _lighting_result(set_lights(*command, preview=bool(preview), action_results=action_results,
                          origin_device=origin_device))
    follow_up = (
        re.fullmatch(r"turn (it|them) (on|off)", phrase)
        or re.fullmatch(r"(?:turn )?(on|off) (it|them)", phrase)
        or re.fullmatch(r"make (it|them) (darker|lighter|brighter|very bright)", phrase)
    )
    if follow_up:
        pronoun, direction = follow_up.groups()
        if direction in ("it", "them"):
            pronoun, direction = direction, pronoun
        if not last_lights or (pronoun == "it") != (len(last_lights) == 1):
            return ExecutionResult("Which light or room do you mean?", Outcome.UNRESOLVED)
        return _lighting_result(set_lights(" and ".join(last_lights), "brighter" if direction == "lighter" else direction,
                          preview=bool(preview), require_all=True, action_results=action_results))
    parts = re.split(r"[ ,;]+(?:actually|no[ ,]+i mean|i mean|no(?=,))\b[ ,:;]*", phrase)
    corrected = len(parts) > 1
    if corrected and re.search(r"(?:^|\s)(?:and|then|as well as|in the|except(?: the)?)$", parts[-1]):
        return ExecutionResult("Please finish the corrected light command.", Outcome.UNRESOLVED)
    brightness = None
    relative_step = 10
    dimming = re.fullmatch(r"(?:set|dim) (?:the )?(.+?) to\s+([+-]?\d+)\s*(?:percent|per cent|%)", parts[-1])
    adjustment = re.fullmatch(r"(dim|brighten) (?:the )?(.+?) by\s+([+-]?\d+)\s*(?:percent|per cent|%)", parts[-1])
    if dimming:
        brightness = int(dimming[2])
        if not 0 <= brightness <= 100:
            return ExecutionResult("Please choose a brightness from 0 to 100 percent.", Outcome.UNRESOLVED)
        if re.search(r"\bturn (?:on|off)\b", dimming[1]):
            return ExecutionResult("Please give the brightness and on/off changes as separate commands.", Outcome.UNRESOLVED)
        command = dimming[1], "on" if brightness else "off"
    elif adjustment:
        relative_step = int(adjustment[3])
        if not 1 <= relative_step <= 100:
            return ExecutionResult("Please choose a brightness change from 1 to 100 percent.", Outcome.UNRESOLVED)
        command = adjustment[2], "darker" if adjustment[1] == "dim" else "brighter"
    else:
        command = parse_light_command(parts[-1])
    if corrected and command is None:
        previous = parse_light_command(parts[0])
        replacement = parts[-1].removeprefix("the ").strip()
        if (previous and replacement and not previous[0].startswith("everything except ")
                and not re.search(r"\b(?:turn (?:on|off)|make (?:darker|brighter|very bright))\b", previous[0])
                and not re.match(r"^(?:turn|switch|make|on|off|the)\b", replacement)):
            command = replacement, previous[1]
    if command is None:
        if corrected:
            return ExecutionResult("Please say the corrected light command in full.", Outcome.UNRESOLVED)
        if preview:
            return ExecutionResult("Please give me a lighting command to preview.", Outcome.UNRESOLVED)
        return None
    return _lighting_result(set_lights(*command, brightness=brightness or None, preview=bool(preview),
                      require_all=corrected, action_results=action_results, relative_step=relative_step))


def response_category(phrase, parse_light_command):
    """Classify only recognized lighting wording, never invent a result."""
    if re.search(r"\bon\b", phrase) and re.search(r"\boff\b", phrase):
        return "mixed_lighting"
    if re.search(r"\bvery bright\b|\bto 100\s*(?:percent|per cent|%)", phrase):
        return "full_brightness"
    if re.match(r"^(?:set|dim|brighten)\b", phrase) or re.search(r"\b(?:darker|lighter|brighter|very bright)\b", phrase):
        return "brightness"
    command = parse_light_command(phrase)
    if command and command[1] in {"on", "off"}:
        return "lights_" + command[1]
    return "lights_status"


def matches(phrase, parse_light_command):
    """Recognize lighting phrases without executing Home Assistant actions."""
    if phrase in {"what lights are on", "which lights are on",
                  "what lights are still on", "which lights are still on"}:
        return True
    preview = re.match(r"^(?:preview|dry[ -]run)\b[ ,:]*", phrase)
    candidate = canonical_brightness(phrase[preview.end():] if preview else phrase)
    if re.fullmatch(r"(?:set|dim) (?:the )?volume\b.*", candidate):
        return False  # "set the volume to 30 percent" is music.
    if re.fullmatch(r"make it (?:darker|lighter|brighter|very bright) in .+", candidate):
        return True
    if re.fullmatch(r"turn (?:down|up) (?:the )?(?:all )?lights(?: in .+)?", candidate):
        return True
    if candidate.endswith(" in here") and re.match(r"^(?:turn|make|dim|brighten|set)\b", candidate):
        return True
    if re.fullmatch(r"(?:turn (?:it|them) (?:on|off)|(?:turn )?(?:on|off) (?:it|them)|make (?:it|them) (?:darker|lighter|brighter|very bright))", candidate):
        return True
    if re.fullmatch(r"(?:set|dim) (?:the )?.+? to\s+[+-]?\d+\s*(?:percent|per cent|%)", candidate):
        return True
    if re.fullmatch(r"(?:dim|brighten) (?:the )?.+? by\s+[+-]?\d+\s*(?:percent|per cent|%)", candidate):
        return True
    parts = re.split(r"[ ,;]+(?:actually|no[ ,]+i mean|i mean|no(?=,))\b[ ,:;]*", candidate)
    if len(parts) > 1:
        return bool(parse_light_command(parts[0]) or parse_light_command(parts[-1]))
    return bool(parse_light_command(candidate)) or bool(preview)
