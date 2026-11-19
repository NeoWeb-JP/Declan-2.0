"""Typed stop-all and origin-specific music dispatch boundaries."""
import sqlite3
from urllib.error import HTTPError
from execution_results import ExecutionResult, Outcome


def stop_everywhere_result(connection, *, inventory_reader, inventory_module, music_provider):
    """Stop all active approved Music Assistant destinations, including Everywhere."""
    if connection is None:
        return ExecutionResult("", Outcome.NOT_CONFIGURED), "Home Assistant is not configured."
    inventory_result = inventory_module.InventoryResult.coerce(inventory_reader(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error:
        return ExecutionResult("", error), "Could not discover the approved music players."
    destinations, players = music_provider.music_players(inventory)
    targets = sorted({entity for entity in destinations.values()
                      if entity and players.get(entity, {}).get("state") in music_provider.ACTIVE})
    # A running Everywhere group owns its members: one stop on the group
    # must not dispatch additional stop requests to the same stream.
    group = destinations.get("everywhere")
    if group in targets:
        members = (players[group].get("attributes") or {}).get("group_members") or []
        targets = [entity for entity in targets if entity == group or entity not in members]
    if not targets:
        return ExecutionResult("", Outcome.CONFIRMED), "No approved music players are currently playing."
    failed = []
    for entity in targets:
        try:
            music_provider.request(connection, "/api/services/media_player/media_stop", {"entity_id": entity}, timeout=2)
            if not music_provider.wait_for(connection, entity, lambda row: row.get("state") in music_provider.STOPPED):
                failed.append(entity)
        except HTTPError as exc:
            exc.close()
            failed.append(entity)
        except (OSError, ValueError):
            failed.append(entity)
    if failed:
        return ExecutionResult("", Outcome.PARTIAL if len(failed) < len(targets) else Outcome.UNVERIFIED), (
            "Could not verify Stop for: " + ", ".join(failed))
    return ExecutionResult("", Outcome.CONFIRMED), "Stopped playback on all active approved music players."


def stop_origin_result(connection, satellite, device, *, inventory_reader, inventory_module, music_provider, timer_provider):
    """Typed stop result for playback on the originating device."""
    if connection is None or not (satellite or device):
        return ExecutionResult("", Outcome.UNRESOLVED), "Stop needs an identifiable Assist satellite or device."
    inventory_result = inventory_module.InventoryResult.coerce(inventory_reader(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error:
        return ExecutionResult("", error), "Could not discover the originating satellite's outputs."
    origin = next((row for row in inventory if row.get("entity_id") == satellite), None)
    origin_device = (origin.get("declan_device") if origin else None) or device
    if not origin and device:
        satellites = [row for row in inventory if str(row.get("entity_id", "")).startswith("assist_satellite.")
                      and row.get("declan_device") == device]
        origin = satellites[0] if len(satellites) == 1 else None
        satellite = origin.get("entity_id") if origin else None
    direct = [row for row in inventory if str(row.get("entity_id", "")).startswith("media_player.")
              and origin_device and row.get("declan_device") == origin_device
              and row.get("declan_music_assistant") is False
              and row.get("state") not in (None, "unknown", "unavailable")]
    if len(direct) > 1:
        return ExecutionResult("", Outcome.UNRESOLVED), "More than one playback output belongs to the originating device."
    if len(direct) == 1:
        target = direct[0]["entity_id"]
        members = (direct[0].get("attributes") or {}).get("group_members") or []
        if len(members) > 1:
            return ExecutionResult("", Outcome.UNRESOLVED), "The device output is grouped; Stop left the shared group alone."
        try:
            music_provider.request(connection, "/api/services/media_player/media_stop", {"entity_id": target}, timeout=2)
            if music_provider.wait_for(connection, target, lambda row: row.get("state") in music_provider.STOPPED):
                if satellite:
                    timer_provider.stop_due(satellite)
                return ExecutionResult("", Outcome.CONFIRMED), f"Stopped {target}."
        except HTTPError as error:
            error.close()
        except (OSError, ValueError, sqlite3.Error):
            pass
        return ExecutionResult("", Outcome.UNVERIFIED), f"Could not verify Stop on {target}."
    area = origin.get("declan_area") if origin else None
    if not isinstance(area, str) or not area.strip():
        return ExecutionResult("", Outcome.UNRESOLVED), "No playback output or area could be resolved for the satellite."
    music_result = music_provider.control_result(
        ("media_stop", music_provider.room_key(area)), connection,
        lambda _: inventory_result,
    )
    if music_result.outcome is Outcome.CONFIRMED and satellite:
        try:
            timer_provider.stop_due(satellite)
        except (OSError, sqlite3.Error):
            return ExecutionResult("", Outcome.PARTIAL), "Playback stopped, but the local timer alarm could not be acknowledged."
    return ExecutionResult("", music_result.outcome), music_result.reply
