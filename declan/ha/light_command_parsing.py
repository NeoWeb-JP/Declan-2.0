"""Parse multi-clause lighting commands without side effects."""
import re


def parse_light_command(phrase):
    separator = r"\s+(?:and then|as well as|and|then)\s+(?=(?:turn|make)\s)"
    if re.match(r"turn (?!on\b|off\b)", phrase):
        separator += r"|(?:(?<= on)|(?<= off))\s+(?:and then|as well as|and|then)\s+"
    if phrase.startswith("make "):
        separator += r"|(?:(?<= darker)|(?<= lighter)|(?<= brighter)|(?<= very bright))\s+(?:and then|as well as|and|then)\s+"
    clauses = re.split(separator, phrase)
    targets = []
    for index, clause in enumerate(clauses):
        adjustment = re.fullmatch(r"(dim|brighten) (?:the )?(.+)", clause)
        if adjustment:
            targets.append((adjustment[2], "darker" if adjustment[1] == "dim" else "brighter"))
            continue
        relative_prefix = r"(?:make )?" if index and phrase.startswith("make ") else "make "
        relative = re.fullmatch(relative_prefix + r"(?:the )?(.+?) (darker|lighter|brighter|very bright)", clause)
        if relative:
            targets.append((relative[1], "brighter" if relative[2] == "lighter" else relative[2]))
            continue
        exception = re.fullmatch(r"turn (?:everything|all lights) off except (?:for )?(?:the )?(.+)", clause)
        if exception:
            targets.append(("everything except " + exception[1], "off"))
            continue
        command = (
            re.fullmatch(r"turn (?P<state>on|off)(?:\s*[,;:]\s*|\s+)(?:the )?(?P<name>.+)", clause)
            or re.fullmatch(r"(?:turn )?(?:the )?(?P<name>.+) (?P<state>on|off)", clause)
        )
        if command is None:
            return None
        targets.append((command.group("name"), command.group("state")))
    name, direction = targets[0]
    for target, state in targets[1:]:
        verb = "make" if state in ("darker", "brighter", "very bright") else "turn"
        name += f" and {verb} {state} {target}"
    return name, direction
