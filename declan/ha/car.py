"""Car questions and charging (FUT-31, #834).

"Is the car charged?", "how much charge has the car got?", "is the car
plugged in?", "is the car charging?", "start charging the car", "stop
charging the car".

- The charger is the Pod Point integration in Home Assistant, found
  automatically: its status sensor, cable sensor and "charging allowed"
  switch. The car's own battery comes from the sensor set in Settings ->
  Household -> Car (or DECLAN_CAR_BATTERY_ENTITY).
- Starting or stopping charging changes the Pod Point, so it always asks for
  a spoken yes first (``is_control`` puts it through the confirmation gate).
  Pod Point's "charging allowed" switch overrides its schedule while it's on,
  and turning it off hands control back to the schedule; Declan says so.
- Guests can ask about the car but can't change charging.
- A sensor that isn't reporting is said plainly, never guessed.
"Will it be charged by 8?" and failed-session detection are later (P3).
"""
import json
import re

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import ha_reads, house_info

_UNKNOWN = frozenset({"unknown", "unavailable", "", "none"})
_CAR = r"(?:the |my |our )?(?:car|ev|electric car|peugeot|e-?208|motor)"
_QUESTIONS = (
    ("plugged", re.compile(rf"is {_CAR} plugged in|(?:has|did) (?:anyone|someone|somebody|edd|jaco|you|i) plug(?:ged)? "
                           rf"(?:in )?{_CAR}(?: in)?|is {_CAR} on (?:the )?charge")),
    ("charging", re.compile(rf"is {_CAR} charging|is {_CAR} still charging|(?:is|has) {_CAR} (?:started|stopped) charging")),
    ("battery", re.compile(rf"is {_CAR} (?:charged|full|fully charged|flat)(?: yet| up)?"
                           rf"|how (?:much charge|much battery|charged) (?:has|does|is) {_CAR}(?: got| have)?"
                           rf"|what(?:'s| is) {_CAR}(?:'s)? (?:battery|charge|charge level|battery level)"
                           rf"|(?:how's|how is) {_CAR}(?:'s)? (?:battery|charge|charging)"
                           rf"|{_CAR}(?:'s)? (?:battery|charge)(?: level)?")),
)
_START = re.compile(rf"(?:start|begin|resume) charging {_CAR}|(?:start|begin|resume) {_CAR}(?:'s)? charging"
                    rf"|(?:start|turn on) (?:the )?(?:car |pod ?point )charg(?:ing|er)|start charging|charge {_CAR}(?: now)?")
_STOP = re.compile(rf"(?:stop|pause) charging {_CAR}|(?:stop|pause) {_CAR}(?:'s)? charging"
                   rf"|(?:stop|pause|turn off) (?:the )?(?:car |pod ?point )charg(?:ing|er)|stop charging")

_TEMPLATE = (
    "{% set ns = namespace(rows=[]) %}"
    "{% for entity in integration_entities('pod_point') %}"
    "{% set ns.rows = ns.rows + [[entity, states(entity)]] %}"
    "{% endfor %}"
    "{% set battery = BATTERY %}"
    "{{ {'charger': ns.rows, 'battery': states(battery) if battery else '', 'guest': states(GUEST)} | to_json }}"
)


def _clean(phrase):
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:declan,? |hey declan,? |howzit declan,? |please )", "", text)
    return re.sub(r",? (?:declan|please)$", "", text)


def _with_name(text):
    """Also accept the car's own name ("is the Peugeot charged?")."""
    try:
        name = house_info.get("car_name").casefold().removeprefix("the ").removeprefix("my ")
    except (OSError, ValueError, KeyError):
        return text
    return re.sub(rf"\b{re.escape(name)}\b", "car", text) if name and name != "car" else text


def match(phrase):
    """("ask", kind) | ("start",) | ("stop",) | None."""
    if not isinstance(phrase, str):
        return None
    text = _with_name(_clean(phrase))
    if _START.fullmatch(text):
        return ("start",)
    if _STOP.fullmatch(text):
        return ("stop",)
    for kind, pattern in _QUESTIONS:
        if pattern.fullmatch(text):
            return ("ask", kind)
    return None


def is_control(phrase):
    """True for "start/stop charging the car": these need a spoken yes first."""
    return match(phrase) in {("start",), ("stop",)}


def _guest_entity():
    from declan.ha import household_entities
    try:
        return household_entities.guest_mode()
    except ValueError:
        return "input_boolean.guest_mode"


def read(connection, battery_entity, *, fetch=None):
    """The charger's and battery's states. ``fetch(template)`` replaces the HA connection (background jobs)."""
    template = (_TEMPLATE.replace("BATTERY", json.dumps(battery_entity or ""))
                .replace("GUEST", json.dumps(_guest_entity())))
    data = fetch(template) if fetch is not None else ha_reads.template(connection, template)
    if not isinstance(data, dict) or not isinstance(data.get("charger"), list):
        raise ValueError("Home Assistant didn't describe the charger.")
    found: dict[str, object] = {"status": None, "cable": None, "allowed": None, "allowed_entity": None, "energy": None}
    for row in data["charger"]:
        if not (isinstance(row, list) and len(row) == 2 and all(isinstance(value, str) for value in row)):
            continue
        entity, state = row
        if entity.startswith("binary_sensor.") and entity.endswith("_cable_status"):
            found["cable"] = state
        elif entity.startswith("switch.") and entity.endswith(("_charging_allowed", "_allow_charging")):
            found["allowed"], found["allowed_entity"] = state, entity
        elif (entity.startswith("sensor.") and entity.endswith("_status")
              and not any(word in entity for word in ("cloud", "connection", "signal", "cable"))):
            found["status"] = state
        elif entity.startswith("sensor.") and entity.endswith("_current_energy"):
            found["energy"] = state
    found["charger"] = bool(data["charger"])
    battery = data.get("battery")
    found["battery"] = battery if isinstance(battery, str) else ""
    found["guest"] = data.get("guest") if isinstance(data.get("guest"), str) else ""
    return found


def _percent(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number) if 0 <= number <= 100 else None


def _plugged(car):
    if car["cable"] in {"on", "off"}:
        return car["cable"] == "on"
    status = (car["status"] or "").casefold()
    if status in _UNKNOWN:
        return None
    return status not in {"available", "idle"}


def _charge_state(car):
    """A few words about the charger: "charging", "plugged in and waiting for its schedule"..."""
    status = (car["status"] or "").casefold()
    plugged = _plugged(car)
    if status == "charging":
        return "charging"
    if plugged is False:
        return "not plugged in"
    if status == "connected-waiting-for-schedule":
        return "plugged in and waiting for its schedule"
    if status == "suspended-ev":
        return "plugged in, but the car has stopped taking charge"
    if status in {"suspended-evse", "pending"}:
        return "plugged in, but the charger has paused"
    if plugged:
        return "plugged in but not charging"
    return None


def _name(capital=False):
    try:
        name = house_info.get("car_name")
    except (OSError, ValueError, KeyError):
        name = "the car"
    return name[:1].upper() + name[1:] if capital else name


def answer(kind, car):
    name = _name(capital=True)
    state = _charge_state(car)
    if kind == "plugged":
        plugged = _plugged(car)
        if plugged is None:
            return ExecutionResult("I can't tell; the Pod Point isn't reporting.", Outcome.UNAVAILABLE)
        if plugged:
            detail = ("plugged in and charging" if state == "charging"
                      else state if state and state.startswith("plugged") else "plugged in")
            return ExecutionResult(f"Yes, {_name()}'s {detail}.", Outcome.CHAT_ANSWER)
        return ExecutionResult(f"No, {_name()} isn't plugged in. The charger can't reach it from there, boet.",
                               Outcome.CHAT_ANSWER)
    if kind == "charging":
        if state is None:
            return ExecutionResult("I can't tell; the Pod Point isn't reporting.", Outcome.UNAVAILABLE)
        if state == "charging":
            return ExecutionResult(f"Yes, {_name()}'s charging.", Outcome.CHAT_ANSWER)
        return ExecutionResult(f"No, {_name()}'s {state}.", Outcome.CHAT_ANSWER)
    percent = _percent(car["battery"])
    if percent is None:
        if car["battery"]:
            tail = f" It's {state}." if state else ""
            return ExecutionResult(f"I can't see {_name()}'s battery right now.{tail}", Outcome.UNAVAILABLE)
        if state:
            return ExecutionResult(f"{name}'s {state}. Set its battery sensor in Settings, Household, Car "
                                   "and I'll tell you the percentage too.", Outcome.CHAT_ANSWER)
        return ExecutionResult("I can't see the car. Set its battery sensor in Settings, Household, Car.",
                               Outcome.NOT_CONFIGURED)
    reply = f"{name}'s at {percent}%"
    reply += f" and {state}." if state else "."
    if percent >= 95 and state != "charging":
        reply += " Full, more or less."
    elif percent <= 20 and state == "not plugged in":
        reply += " Plug it in before it leaves you on the side of the road."
    return ExecutionResult(reply, Outcome.CHAT_ANSWER)


def control(action, car, connection):
    if not car["charger"] or car["allowed_entity"] is None:
        return ExecutionResult("I can't find the Pod Point's charging switch in Home Assistant.", Outcome.NOT_CONFIGURED)
    if car["allowed"] in _UNKNOWN:
        return ExecutionResult("The Pod Point isn't answering, so I can't change its charging.", Outcome.UNAVAILABLE)
    if action == "start":
        if _plugged(car) is False:
            return ExecutionResult(f"Plug {_name()} in first, boet. I can't reach through the wall.", Outcome.UNRESOLVED)
        if (car["status"] or "").casefold() == "charging":
            return ExecutionResult(f"{_name(capital=True)}'s already charging.", Outcome.CONFIRMED)
        service, reply = "turn_on", ("Charging allowed. The Pod Point should start within a minute or two. "
                                     "That overrides its schedule until you stop it.")
    else:
        if car["allowed"] == "off" and (car["status"] or "").casefold() != "charging":
            return ExecutionResult("Charging's already off. The Pod Point schedule is in charge.", Outcome.CONFIRMED)
        service, reply = "turn_off", "Charging stopped. The Pod Point schedule is back in charge."
    try:
        ha_reads.call(connection, f"/api/services/switch/{service}", {"entity_id": car["allowed_entity"]})
    except (OSError, ValueError):
        return ExecutionResult("The Pod Point didn't take the change. Try the Pod Point app.", Outcome.FAILED)
    return ExecutionResult(reply, Outcome.REQUESTED)


def result(request, connection, *, guest):
    if request is None:
        return None
    if request[0] in {"start", "stop"} and guest:
        return ExecutionResult("Nice try. Guests don't get to play with the car.", Outcome.REJECTED)
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    try:
        battery = house_info.get("car_battery")
    except (OSError, ValueError, KeyError):
        battery = ""
    try:
        car = read(connection, battery)
    except (OSError, ValueError, TypeError):
        return ExecutionResult("I couldn't ask Home Assistant about the car.", Outcome.UNAVAILABLE)
    if request[0] == "ask":
        if not car["charger"] and not car["battery"]:
            return ExecutionResult("I can't see the car or the Pod Point in Home Assistant. Set the car's battery "
                                   "sensor in Settings, Household, Car.", Outcome.NOT_CONFIGURED)
        return answer(request[1], car)
    return control(request[0], car, connection)


def summary(connection=None, *, fetch=None):
    """One short sentence for the morning briefing and sunrise, or None (also in Guest mode)."""
    try:
        car = read(connection, house_info.get("car_battery"), fetch=fetch)
    except (OSError, ValueError, TypeError, KeyError, TimeoutError):
        return None
    if (not car["charger"] and not car["battery"]) or car["guest"] != "off":
        return None
    reply = answer("battery", car)
    return reply.reply if reply.outcome is Outcome.CHAT_ANSWER and "Settings" not in reply.reply else None
