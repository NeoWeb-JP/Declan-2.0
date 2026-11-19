"""Home Assistant Movie Time remote, discovery and verification helpers."""
import json
import re
import sqlite3
from urllib.error import HTTPError
from declan.core.execution_results import MovieLaunchResult, MovieLaunchStatus


def launch_movie_app_result(connection, remote, app, *, request_factory):
    label, command = app
    url, headers, opener = connection
    try:
        with opener.open(request_factory(f"{url}/api/states/{remote}", headers=headers), timeout=1.5) as response:
            state = json.loads(response.read(65536))["state"]
        if state in ("unknown", "unavailable"):
            return MovieLaunchResult(MovieLaunchStatus.SKIPPED, f"The remote is unavailable. I didn't send the {label} command.")
        request = request_factory(f"{url}/api/services/remote/send_command", headers=headers,
                          data=json.dumps({"entity_id": remote, "command": ["KEY_HOME", f"app:{command}"],
                                           "delay_secs": 2}).encode())
        with opener.open(request, timeout=6):
            pass
    except HTTPError as error:
        error.close()
        return MovieLaunchResult(MovieLaunchStatus.FAILED, f"Home Assistant rejected the {label} launch request.")
    except (OSError, ValueError, KeyError, TypeError):
        return MovieLaunchResult(MovieLaunchStatus.UNVERIFIED, f"I couldn't confirm whether Home Assistant accepted the {label} launch request.")
    return MovieLaunchResult(MovieLaunchStatus.SENT, f"Home Assistant accepted the command to open {label}.")


def discover_movie_entities(connection, room, *, script, remote, needs_remote, inventory_reader, area_reader, inventory_module):
    inventory_result = inventory_module.InventoryResult.coerce(inventory_reader(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error:
        return script, remote, "I couldn't read the Home Assistant entity list."
    room_names = {"lounge": ("lounge", "living room"), "bedroom": ("bedroom", "master bedroom")}
    areas = area_reader(connection) if needs_remote and not remote else {}
    area_members = set().union(*(areas.get(name, set()) for name in room_names[room]))
    candidates: dict[str, set[str]] = {"script": set(), "remote": set()}
    for row in inventory:
        if not isinstance(row, dict):
            continue
        entity = row.get("entity_id")
        if not isinstance(entity, str) or not re.fullmatch(r"(?:script|remote)\.[a-z0-9_]+", entity):
            continue
        domain, object_id = entity.split(".", 1)
        attrs = row.get("attributes") or {}
        names = [" ".join(re.findall(r"[a-z0-9]+", name.casefold()))
                 for name in (object_id, attrs.get("friendly_name", ""))
                 if isinstance(name, str)]
        named_rooms = {key for key, labels in room_names.items()
                       if any(re.search(rf"\b{label}\b", name) for label in labels for name in names)}
        if named_rooms - {room}:
            continue
        if domain == "script" and not script:
            if not named_rooms and room != "lounge":
                continue
            for name in names:
                for label in sorted(room_names[room], key=len, reverse=True):
                    name = re.sub(rf"\b{label}\b", "", name)
                if re.fullmatch(r"(?:declan )?movie time shared local routine(?: \d+)?", " ".join(name.split())):
                    candidates["script"].add(entity)
        elif domain == "remote" and needs_remote and not remote:
            assigned = any(entity in members for members in areas.values())
            in_room = entity in area_members if assigned else room in named_rooms
            if in_room and any("projector" in name.split() for name in names):
                candidates["remote"].add(entity)
    for domain, configured, label in (("script", script, "Movie Time script"), ("remote", remote, "projector remote")):
        if configured or (domain == "remote" and not needs_remote):
            continue
        matches = candidates[domain]
        if len(matches) != 1:
            setting = ("DECLAN_BEDROOM_MOVIE" if room == "bedroom" else "DECLAN_MOVIE") + "_" + domain.upper()
            detail = "found more than one" if matches else "couldn't find a"
            return script, remote, f"I {detail} {label} for the {room}. Set {setting} to the exact entity ID."
        if domain == "script":
            script = next(iter(matches))
        else:
            remote = next(iter(matches))
    return script, remote, None


def verify_legacy_lounge_start(connection, script, *, inventory_reader, inventory_module, entities):
    inventory_result = inventory_module.InventoryResult.coerce(inventory_reader(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error:
        return "Home Assistant didn't return the lounge device states."
    entities = {row.get("entity_id"): row for row in inventory if isinstance(row, dict)}
    if entities.get(script, {}).get("state") != "off":
        return "Home Assistant hasn't confirmed the Movie Time script is off."
    try:
        projector_entity = entities.projector_power()
    except (OSError, sqlite3.Error, ValueError):
        return "The projector power entity is not configured correctly."
    if entities.get(projector_entity, {}).get("state") != "on":
        return "The projector power socket hasn't reported that it's on."
    return None
