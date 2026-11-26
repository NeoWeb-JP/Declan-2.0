"""Shopping and to-do lists (FUT-27, #834), using Home Assistant's own to-do lists.

"Add milk and eggs to the shopping list", "what's on the shopping list?",
"take milk off the list", "add 'call the plumber' to my to-do list".

Items live in Home Assistant's to-do entities (todo.*), so they show up in the
HA app on everyone's phones; Declan keeps no copy. "The list" means the
shopping list. Long lists are summarised. Guests may add to and read the
shopping list too.
"""
import json
import logging
import re
from urllib.error import HTTPError
from urllib.request import Request

from declan.core.execution_results import ExecutionResult, Outcome

LOGGER = logging.getLogger(__name__)
READ_LIMIT = 6
# Only the to-do lists, not every entity: a big house's /api/states is far larger
# than the 256 KB read limit, and a cut-off reply can't be parsed (26 Nov 2026).
_TODO_LISTS = ("{% set ns = namespace(rows=[]) %}{% for s in states.todo %}"
               "{% set ns.rows = ns.rows + [{'entity_id': s.entity_id, 'state': s.state, "
               "'attributes': {'friendly_name': s.name}}] %}{% endfor %}{{ ns.rows | to_json }}")
_LIST = r"(?:the |my |our )?(?P<list>shopping list|shopping|grocery list|groceries|to[- ]?do list|to[- ]?dos?|list)"
_ADD = re.compile(rf"(?:(?:i|we)(?:'ve)? )?(?:add|added|put|stick|pop) (?P<items>.+?) (?:to|on|onto) {_LIST}")
_REMOVE = re.compile(rf"(?:remove|delete|take|cross|tick) (?P<items>.+?) (?:off|from|of) {_LIST}|"
                     rf"(?:tick|cross) off (?P<items2>.+?)(?: (?:on|from) {_LIST.replace('?P<list>', '?P<list2>')})?|"
                     rf"(?:i've |we've |i |we )?(?:got|bought) (?P<items3>.+?) (?:off|from) {_LIST.replace('?P<list>', '?P<list3>')}")
_READ = re.compile(rf"(?:what(?:'s| is) on|read(?: me)?|what do (?:i|we) need (?:from|on)|check) {_LIST}|"
                   rf"what do (?:i|we) need(?: to buy| from the shops)?")


def _split(items):
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", items)
    return [re.sub(r"^(?:some|a|an|the|more) ", "", part.strip(" .'\"")).strip()
            for part in parts if part.strip(" .'\"")][:10]


def _kind(name):
    if not name:
        return "shopping"
    return "todo" if re.search(r"to[- ]?do", name) else "shopping"


def match(phrase):
    """("add" | "remove" | "read", list kind, items) or None."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    if found := _ADD.fullmatch(text):
        return ("add", _kind(found["list"]), _split(found["items"]))
    if found := _REMOVE.fullmatch(text):
        items = found["items"] or found["items2"] or found["items3"]
        name = found["list"] or found["list2"] or found["list3"]
        return ("remove", _kind(name), _split(items))
    if found := _READ.fullmatch(text):
        return ("read", _kind(found.groupdict().get("list")), [])
    return None


def _call(connection, path, data=None):
    url, headers, opener = connection
    request = Request(url + path, data=json.dumps(data).encode() if data is not None else None,
                      headers=headers, method="POST" if data is not None else "GET")
    with opener.open(request, timeout=5) as response:
        return json.loads(response.read(262144) or b"null")


def _todo_states(connection):
    rows = _call(connection, "/api/template", {"template": _TODO_LISTS})
    return rows if isinstance(rows, list) else []


def chosen_shopping_list():
    """The to-do entity picked in Settings -> Household, or "" to find one by name."""
    try:
        from declan.turn import household_settings
        return household_settings.listing()["settings"].get("shopping_list") or ""
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def find_list(states, kind):
    """The todo entity for "shopping" or "todo", or None."""
    lists = [row for row in states if isinstance(row, dict) and str(row.get("entity_id", "")).startswith("todo.")
             and row.get("state") not in ("unavailable", "unknown")]
    if kind == "shopping" and (chosen := chosen_shopping_list()):
        # The shared iPhone list, synced into HA, may not have "shopping" in its name.
        return chosen if any(row["entity_id"] == chosen for row in lists) else None

    def name(row):
        return f"{row['entity_id']} {(row.get('attributes') or {}).get('friendly_name', '')}".casefold()
    if kind == "shopping":
        wanted = [row for row in lists if "shop" in name(row) or "grocer" in name(row)]
    else:
        wanted = [row for row in lists if re.search(r"to.?do|task|chore", name(row)) and "shop" not in name(row)]
    if len(wanted) == 1:
        return wanted[0]["entity_id"]
    return None


def _items(connection, entity):
    result = _call(connection, "/api/services/todo/get_items?return_response",
                   {"entity_id": entity, "status": "needs_action"})
    response = result.get("service_response", {}) if isinstance(result, dict) else {}
    items = (response.get(entity) or {}).get("items") if isinstance(response, dict) else None
    return [item["summary"] for item in items or [] if isinstance(item, dict) and isinstance(item.get("summary"), str)]


def _names(values):
    return values[0] if len(values) == 1 else ", ".join(values[:-1]) + " and " + values[-1]


def result(request, connection):
    kind, which, items = request
    label = "shopping list" if which == "shopping" else "to-do list"
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    try:
        entity = find_list(_todo_states(connection), which)
        if entity is None:
            return ExecutionResult(f"I can't find one {label} in Home Assistant. Add a to-do list called "
                                   f"'{label.capitalize()}' there.", Outcome.NOT_CONFIGURED)
        if kind == "read":
            current = _items(connection, entity)
            if not current:
                return ExecutionResult(f"The {label} is empty. Miracles happen.", Outcome.CHAT_ANSWER)
            more = f", and {len(current) - READ_LIMIT} more" if len(current) > READ_LIMIT else ""
            count = f"{len(current)} things" if len(current) > 1 else "One thing"
            return ExecutionResult(f"{count} on the {label}: {_names(current[:READ_LIMIT])}{more}.", Outcome.CHAT_ANSWER)
        if not items:
            return ExecutionResult(f"What should I {'add to' if kind == 'add' else 'take off'} the {label}?", Outcome.UNRESOLVED)
        if kind == "add":
            for item in items:
                _call(connection, "/api/services/todo/add_item", {"entity_id": entity, "item": item[:1].upper() + item[1:]})
            return ExecutionResult(f"Added {_names(items)} to the {label}.", Outcome.CONFIRMED)
        current = _items(connection, entity)
        lookup = {value.casefold(): value for value in current}
        removed, missing = [], []
        for item in items:
            match_name = lookup.get(item.casefold()) or next(
                (value for value in current if item.casefold() in value.casefold()), None)
            if match_name is None:
                missing.append(item)
                continue
            _call(connection, "/api/services/todo/update_item",
                  {"entity_id": entity, "item": match_name, "status": "completed"})
            removed.append(match_name)
        if not removed:
            return ExecutionResult(f"{_names(missing).capitalize()} isn't on the {label}.", Outcome.UNRESOLVED)
        tail = f" {_names(missing).capitalize()} wasn't on it." if missing else ""
        return ExecutionResult(f"Ticked {_names(removed)} off the {label}.{tail}",
                               Outcome.CONFIRMED if not missing else Outcome.PARTIAL)
    except HTTPError as error:
        error.close()
        return ExecutionResult(f"Home Assistant didn't accept that change to the {label}.", Outcome.UNAVAILABLE)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        LOGGER.warning("To-do list %s failed (%s)", kind, type(error).__name__)
        return ExecutionResult(f"I couldn't reach the {label} in Home Assistant.", Outcome.UNAVAILABLE)


def add_to_shopping(connection, item):
    """Put one item on the shopping list unless it's already there (FUT-76 pantry).

    Returns "added", "already" or "unavailable".
    """
    if connection is None:
        return "unavailable"
    try:
        entity = find_list(_todo_states(connection), "shopping")
        if entity is None:
            return "unavailable"
        wanted = item.casefold()
        if any(wanted == value.casefold() or wanted in value.casefold() for value in _items(connection, entity)):
            return "already"
        _call(connection, "/api/services/todo/add_item", {"entity_id": entity, "item": item[:1].upper() + item[1:]})
        return "added"
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return "unavailable"
