"""Resolve, dispatch and verify Home Assistant lighting actions."""
import json
from concurrent.futures import ThreadPoolExecutor
import re
import sqlite3
from time import monotonic
from urllib.error import HTTPError

import diagnostics
from execution_results import ExecutionResult, Outcome
from lighting_action_evidence import LightingActionStatus, LightingActionReason


MAX_PARALLEL_REQUESTS = 6


def concurrently(function, items):
    """Return [function(item) ...] in input order, running up to six at once.

    One item (the common single-light case) runs inline with no thread.
    """
    items = list(items)
    if len(items) < 2:
        return [function(item) for item in items]
    with ThreadPoolExecutor(max_workers=min(len(items), MAX_PARALLEL_REQUESTS)) as pool:
        return list(pool.map(function, items))


def set_lights_result(name, desired_state, *, brightness=None, preview=False, require_all=False, relative_step=10,
               action_results=None, origin_device=None, connect, inventory_reader, inventory_module, entities, sass, areas_reader, switch_dispatch, intents, evidence_factory, append_evidence, clock, sleeper, request_factory):
    """Resolve Home Assistant lights before dispatch and verify their reported states."""
    connection = connect()
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    url, headers, opener = connection
    inventory_result = inventory_module.InventoryResult.coerce(inventory_reader(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error:
        return ExecutionResult("I couldn't read the lights from Home Assistant.", error)

    try:
        guest_mode_entity = entities.guest_mode()
    except (OSError, sqlite3.Error, ValueError):
        guest_mode_entity = None
    guest_mode = next(
        (item.get("state") for item in inventory
         if isinstance(item, dict) and item.get("entity_id") == guest_mode_entity),
        None,
    )

    lights = {}
    names: dict[str, set[str]] = {}
    light_groups = set()
    dimmable = set()
    levels = {}
    for item in inventory:
        entity_id = item.get("entity_id", "") if isinstance(item, dict) else ""
        if not isinstance(entity_id, str) or not re.fullmatch(r"light\.[a-z0-9_]+", entity_id):
            continue
        attributes = item.get("attributes")
        if isinstance(attributes, dict):
            modes = attributes.get("supported_color_modes")
            level = attributes.get("brightness")
            levels[entity_id] = level
            if (isinstance(level, (int, float))
                    or isinstance(modes, list) and any(mode not in ("onoff", "unknown") for mode in modes)):
                dimmable.add(entity_id)
        if isinstance(attributes, dict) and isinstance(attributes.get("entity_id"), (list, tuple, str)):
            light_groups.add(entity_id)
        friendly = attributes.get("friendly_name") if isinstance(attributes, dict) else None
        id_name = entity_id.removeprefix("light.").replace("_", " ")
        label = friendly.strip() if isinstance(friendly, str) and friendly.strip() else id_name
        lights[entity_id] = (label, item.get("state"))
        for candidate in (entity_id, id_name, " ".join(label.casefold().split())):
            names.setdefault(candidate, set()).add(entity_id)

    if desired_state is None:
        individual_lights = [light for entity, light in lights.items() if entity not in light_groups]
        if not individual_lights:
            return ExecutionResult("Home Assistant didn't report any individual lights to check.", Outcome.UNAVAILABLE)
        on = sorted(label for label, state in individual_lights if state == "on")
        unknown = sorted(label for label, state in individual_lights if state not in ("on", "off"))
        if on:
            reply = "Home Assistant reports these lights are on: " + ", ".join(on) + "."
        elif len(unknown) == len(individual_lights):
            reply = "I couldn't verify the state of any individual lights."
        elif unknown:
            reply = "None of the lights I could check are on."
        else:
            reply = "Home Assistant reports all individual lights are off."
        if unknown:
            reply += " I couldn't check: " + ", ".join(unknown) + "."
            return ExecutionResult(reply, Outcome.PARTIAL if len(unknown) < len(individual_lights) else Outcome.UNVERIFIED)
        return ExecutionResult(sass(reply, "lights_status", guest_mode), Outcome.CONFIRMED)

    areas = None
    room_targets = set()

    def load_area_metadata():
        nonlocal areas
        areas = areas_reader(connection, origin_device)
    if origin_device is not None:
        load_area_metadata()
        if not areas:
            return ExecutionResult("Which room do you mean? I couldn't verify the Assist device's area.", Outcome.UNRESOLVED)
        local_members = (lights.keys() & next(iter(areas.values()))) - light_groups
        if not local_members:
            return ExecutionResult("Home Assistant didn't report any individual lights in this room.", Outcome.UNRESOLVED)
        if name == "some lights":
            off = sorted(entity for entity in local_members if lights[entity][1] == "off")
            if not off:
                if any(lights[entity][1] not in ("on", "off") for entity in local_members):
                    return ExecutionResult("I couldn't verify any more lights to turn on in this room.", Outcome.UNVERIFIED)
                return ExecutionResult("All the lights I can see in this room are already on.", Outcome.CONFIRMED)
            local_members = set(off[:2])

    def resolve(target, state, *, use_area=False):
        recovered = target.removeprefix(f"{state} ")
        matches = names.get(target) or names.get(recovered)
        if origin_device is not None:
            if recovered in {"lights", "all lights"} or recovered == name == "some lights":
                room_targets.add(target)
                return local_members
            return (matches or set()) & local_members
        if not use_area:
            return matches

        if areas is None:
            load_area_metadata()
        if areas is None:
            return None

        exception = re.fullmatch(r"everything except (?:the )?(.+)", recovered)
        if exception:
            excluded = areas.get(exception[1])
            if state != "off" or not excluded:
                return None
            members = (lights.keys() & set().union(*areas.values())) - excluded - light_groups
            room_targets.add(target)
            return members
        if recovered in areas:
            room_targets.add(target)
            return (lights.keys() & areas[recovered]) - light_groups
        if matches:
            return matches

        room_suffix = re.fullmatch(r"(.+?) in (?:the )?(.+)", recovered)
        if room_suffix and room_suffix[2] in areas:
            bare_name, area = room_suffix.groups()
        else:
            area = max((label for label in areas if recovered.startswith(label + " ")),
                       key=len, default=None)
            if area is None:
                return None
            bare_name = recovered[len(area) + 1:]
        if bare_name in {"lights", "all lights"}:
            members = (lights.keys() & areas[area]) - light_groups
            if members:
                room_targets.add(target)
            return members
        candidates = names.get(bare_name, set())
        in_area = candidates & areas[area]
        if in_area:
            return in_area
        # A unique light with no registered area can still have a spoken room qualifier.
        if len(candidates) == 1 and not any(candidates & entities for entities in areas.values()):
            return candidates
        return None

    # Prefer a full name, including names that contain "and".
    targets = [name] if name.startswith("everything except ") or resolve(name, desired_state) else re.split(
        r"\s*[,;]\s*|\s+(?:and then|as well as|and|then)\b\s*|\s+(?=turn (?:on|off)\b)",
        name,
    )
    resolved_targets: list[tuple[str, set[str] | None, str]] = []
    skipped: list[ExecutionResult] = []
    direction = desired_state
    for target in targets:
        target = target.strip().removeprefix("the ")
        if not target:
            continue
        explicit = (re.fullmatch(r"turn (on|off)(?: (?:the )?(.+))?", target)
                    or re.fullmatch(r"make (darker|brighter|very bright) (?:the )?(.+)", target))
        if explicit:
            direction, target = explicit.groups()
            if target is None:
                continue
        matches = resolve(target, direction, use_area=True)
        if not matches and not target.startswith("everything except "):
            words = target.split()
            splits = []
            for index in range(1, len(words)):
                left = " ".join(words[:index])
                right = " ".join(words[index:]).removeprefix("the ")
                left_matches = resolve(left, direction, use_area=True)
                right_matches = resolve(right, direction, use_area=True)
                if left_matches and right_matches:
                    splits.append(((left, left_matches), (right, right_matches)))
            if len(splits) > 1:
                skipped.append(ExecutionResult(f"I couldn't tell where to split {target}. Say 'and' between the light names.", Outcome.UNRESOLVED))
                continue
            if splits:
                resolved_targets.extend((part, ids, direction) for part, ids in splits[0])
                continue
        resolved_targets.append((target, matches, direction))

    target_levels: dict[str, int | None] = {}

    def record_action(target, direction, status, *, entity=None, detail=None):
        if action_results is not None and len(action_results) < 200:
            percent = target_levels.get(entity, brightness)
            action_name = (f"set brightness to {percent}%" if percent is not None
                           else direction if direction in ("darker", "brighter", "very bright") else f"turn_{direction}")
            evidence = evidence_factory(target, action_name, status, entity_id=entity, detail=detail)
            append_evidence(action_results, evidence)

    selected: dict[str, tuple[str, str, str]] = {}
    room_off_entities = set()
    conflicts = set()
    for target, matches, direction in resolved_targets:
        if not matches:
            record_action(target, direction, LightingActionStatus.SKIPPED, detail=LightingActionReason.UNRESOLVED)
            skipped.append(ExecutionResult(f"I couldn't find a Home Assistant light called {target}.", Outcome.UNRESOLVED))
            continue
        if len(matches) > 1 and target not in room_targets:
            record_action(target, direction, LightingActionStatus.SKIPPED, detail=LightingActionReason.AMBIGUOUS)
            options = ", ".join(sorted(matches))
            skipped.append(ExecutionResult(f"More than one light matches {target}. Try one of these entity IDs: {options}.", Outcome.UNRESOLVED))
            continue
        for entity in sorted(matches):
            label, state = lights[entity]
            if state not in ("on", "off"):
                record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.UNAVAILABLE)
                skipped.append(ExecutionResult(f"Home Assistant says {label} is unavailable.", Outcome.UNAVAILABLE))
                continue
            relative = direction in ("darker", "brighter")
            if (brightness is not None or relative or direction == "very bright") and entity not in dimmable:
                record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.BRIGHTNESS_UNSUPPORTED)
                skipped.append(ExecutionResult(f"Home Assistant doesn't report brightness control for {label}.", Outcome.UNAVAILABLE))
                continue
            percent = brightness
            goal = direction
            if direction == "very bright":
                percent, goal = 100, "on"
            elif relative:
                level = levels.get(entity)
                if state == "off" or not (isinstance(level, (int, float)) and 0 <= level <= 255):
                    reason = LightingActionReason.ALREADY_OFF if state == "off" else LightingActionReason.BRIGHTNESS_UNKNOWN
                    record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=reason)
                    skipped.append(ExecutionResult(f"I left {label} alone ({reason}).", Outcome.UNAVAILABLE))
                    continue
                change = -relative_step if direction == "darker" else relative_step
                percent = min(100, max(1, round(level * 100 / 255) + change))
                goal = "on"
            if entity in conflicts:
                continue
            if entity in selected and (selected[entity][2], target_levels[entity]) != (goal, percent):
                del selected[entity]
                conflicts.add(entity)
                record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.CONFLICTING_DIRECTIONS)
                skipped.append(ExecutionResult(f"I heard conflicting settings for {label}. I left it alone.", Outcome.UNRESOLVED))
                continue
            selected[entity] = (label, state, goal)
            target_levels[entity] = percent
            if direction == "off" and target in room_targets and not target.startswith("everything except "):
                room_off_entities.add(entity)

    skipped_details = "".join(f" {result.reply}" for result in skipped)
    if not selected:
        if brightness is None and not require_all and len(resolved_targets) == 1:
            switch_result = switch_dispatch(name, desired_state, inventory, connection, preview=preview, action_results=action_results)
            if switch_result is not None:
                return intents._lighting_result(switch_result)
        return (ExecutionResult(skipped_details.strip(), skipped[0].outcome) if skipped else
                ExecutionResult("Tell me which lights to switch.", Outcome.UNRESOLVED))
    if preview:
        for entity, (label, _, direction) in selected.items():
            record_action(label, direction, LightingActionStatus.PLANNED, entity=entity)
        groups: dict[tuple[str, int | None], list[str]] = {}
        for entity, (label, _, direction) in selected.items():
            groups.setdefault((direction, target_levels[entity]), []).append(label)
        plan = [f"set {', '.join(labels)} to {percent}%" if percent is not None
                else f"turn {direction} {', '.join(labels)}"
                for (direction, percent), labels in groups.items()]
        return ExecutionResult(f"Preview: I would {'; '.join(plan)}.{skipped_details}", Outcome.PREVIEW)
    if require_all and skipped:
        for entity, (label, _, direction) in selected.items():
            record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.INCOMPLETE_CORRECTION)
        return ExecutionResult(f"I left the lights unchanged because I couldn't resolve the full correction.{skipped_details}", Outcome.UNRESOLVED)
    pending = {}
    verified: dict[tuple[str, int | None], list[str]] = {(goal, target_levels[entity]): [] for entity, (_, _, goal) in selected.items()}

    def matches_goal(state, direction, level, percent):
        return state == direction and (
            percent is None or (isinstance(level, (int, float))
                                   and abs(level - round(percent * 255 / 100)) <= (0 if percent == 100 else 2))
        )

    already_set = set()
    for entity, (label, state, direction) in selected.items():
        # Reassert an explicit room shutdown even if HA already reports the lights off.
        if entity not in room_off_entities and matches_goal(state, direction, levels.get(entity), target_levels[entity]):
            already_set.add(entity)
            record_action(label, direction, LightingActionStatus.ALREADY_SET, entity=entity)
    dispatch_started = monotonic()
    dispatch_deadline = clock() + 1.75
    batches = []
    for direction, percent in verified:
        entity_ids = [entity for entity, (_, _, goal) in selected.items()
                      if (goal, target_levels[entity]) == (direction, percent) and entity not in already_set]
        verified[direction, percent] = [label for entity, (label, _, goal) in selected.items()
                                        if (goal, target_levels[entity]) == (direction, percent) and entity in already_set]
        if entity_ids:
            batches.append((direction, percent, entity_ids))

    def send(batch):
        """Send one service call; return None when sent, else the failure kind."""
        direction, percent, entity_ids = batch
        data: dict[str, str | list[str] | int] = {"entity_id": entity_ids[0] if len(entity_ids) == 1 else entity_ids}
        if percent is not None:
            data["brightness_pct"] = percent
        remaining = dispatch_deadline - clock()
        if remaining <= 0:
            return "time"
        action = request_factory(
            f"{url}/api/services/light/turn_{direction}",
            data=json.dumps(data).encode(),
            headers=headers, method="POST",
        )
        try:
            with opener.open(action, timeout=min(remaining, 1)):
                pass
        except HTTPError as error:
            error.close()
            return error
        except OSError:
            return "no_response"
        return None

    # Independent service calls share one deadline, so send them together.
    # Outcomes are applied below in the original group order.
    for batch, failure in zip(batches, concurrently(send, batches)):
        direction, percent, entity_ids = batch
        labels = ", ".join(selected[entity][0] for entity in entity_ids)
        if failure == "time":
            for entity in entity_ids:
                record_action(selected[entity][0], direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.DISPATCH_TIME_LIMIT)
            skipped.append(ExecutionResult(f"I ran out of time before sending the command for {labels}.", Outcome.UNVERIFIED))
        elif isinstance(failure, HTTPError):
            for entity in entity_ids:
                record_action(selected[entity][0], direction, LightingActionStatus.FAILED, entity=entity, detail=f"HTTP {failure.code}")
            skipped.append(ExecutionResult(f"Home Assistant returned HTTP {failure.code} for {labels}.", Outcome.ACTION_ERROR))
        elif failure == "no_response":
            for entity in entity_ids:
                record_action(selected[entity][0], direction, LightingActionStatus.UNVERIFIED, entity=entity, detail=LightingActionReason.NO_DISPATCH_RESPONSE)
            skipped.append(ExecutionResult(f"I didn't get a response for {labels}.", Outcome.UNVERIFIED))
        else:
            pending.update({entity: direction for entity in entity_ids})

    diagnostics.record('lights_dispatch', dispatch_started, lights=len(selected), pending=len(pending))
    verify_started = monotonic()
    deadline = clock() + 3
    last_reported = {}
    def read_state(entity):
        """One bounded state read; None when it could not be made or parsed."""
        remaining = deadline - clock()
        if remaining <= 0:
            return None
        request = request_factory(f"{url}/api/states/{entity}", headers=headers)
        try:
            with opener.open(request, timeout=min(remaining, 0.5)) as response:
                observed = json.loads(response.read(65536))
                attributes = observed.get("attributes")
                return observed["state"], (attributes.get("brightness") if isinstance(attributes, dict) else None)
        except HTTPError as error:
            error.close()
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        return None

    while pending and clock() < deadline:
        # Read every pending light at once; apply results in a stable order.
        entities = tuple(pending)
        for entity, observed in zip(entities, concurrently(read_state, entities)):
            if observed is None:
                continue
            state, level = observed
            direction = pending[entity]
            percent = target_levels[entity]
            last_reported[entity] = f"{state}, brightness {round(level * 100 / 255)}%" if (
                percent is not None and isinstance(level, (int, float)) and 0 <= level <= 255
            ) else state
            if matches_goal(state, direction, level, percent):
                verified[direction, percent].append(selected[entity][0])
                record_action(selected[entity][0], direction, LightingActionStatus.CONFIRMED, entity=entity)
                del pending[entity]
        if pending:
            sleeper(min(0.25, max(0, deadline - clock())))
    diagnostics.record('lights_verify', verify_started, lights=len(selected), unconfirmed=len(pending))
    for entity, direction in pending.items():
        label = selected[entity][0]
        state = last_reported.get(entity, "no state reported")
        record_action(label, direction, LightingActionStatus.UNVERIFIED, entity=entity, detail=str(state))
        percent = target_levels[entity]
        goal = f"at {percent}%" if percent is not None else direction
        skipped.append(ExecutionResult(f"I couldn't confirm {label} is {goal} ({state}).", Outcome.UNVERIFIED))
    confirmations = [
        f"{', '.join(labels)} {'is' if len(labels) == 1 else 'are'} "
        + (f"at {percent}%." if percent is not None else f"{direction}.")
        for (direction, percent), labels in verified.items() if labels
    ]
    reply = " ".join(confirmations + [result.reply for result in skipped])
    outcome = (Outcome.PARTIAL if confirmations else skipped[0].outcome) if skipped else Outcome.CONFIRMED
    if outcome is Outcome.PARTIAL and room_targets:
        reply = sass("I handled part of that. Some lighting changes couldn't be confirmed.",
                         "partial_lighting", guest_mode)
    if outcome is Outcome.CONFIRMED:
        if room_targets:
            reply = "Done."
        directions = {direction for direction, _ in verified}
        percents = {percent for _, percent in verified if percent is not None}
        if len(already_set) == len(selected):
            category = "already_set"
        elif len(directions) > 1:
            category = "mixed_lighting"
        elif percents:
            category = "full_brightness" if percents == {100} else "brightness"
        else:
            category = "lights_on" if "on" in directions else "lights_off"
        reply = sass(reply, category, guest_mode)
    return ExecutionResult(reply, outcome)
