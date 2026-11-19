"""Bedroom routine dispatch and verified music playback."""
import json
import sqlite3
from urllib.error import HTTPError
from declan.core.execution_results import ExecutionResult, Outcome


def run_sexy_time_result(operation, connection, *, approved=False, registry, gates, inventory_reader, inventory_module, music_provider, request_factory, token_hex, choose_response, guest_mode):
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED), None
    try:
        sexy_mapping = registry.load().get("sexy_time")
    except (OSError, ValueError, sqlite3.Error):
        sexy_mapping = None
    if not sexy_mapping:
        return ExecutionResult("Map the Sexy Time script in Declan Settings.", Outcome.NOT_CONFIGURED), None
    if sexy_mapping["sensitive"] and not approved:
        return ExecutionResult("Sexy Time requires explicit confirmation.", Outcome.UNRESOLVED), None
    sexy_script = sexy_mapping["script"]
    if not gates.sexy_time.acquire(blocking=False):
        return ExecutionResult("I'm still handling the previous Sexy Time request.", Outcome.BUSY), None
    try:
        inventory_result = inventory_module.InventoryResult.coerce(inventory_reader(connection))
        inventory, inventory_error = inventory_result.inventory, inventory_result.error
        if inventory_error:
            return ExecutionResult("I couldn't discover the bedroom music player.", inventory_error), None
        destinations, _ = music_provider.music_players(inventory)
        player = destinations.get("bedroom")
        if not player:
            return ExecutionResult("I couldn't identify one available bedroom satellite speaker. Check its Home Assistant device and area.", Outcome.UNRESOLVED), None
        url, headers, opener = connection
        request_id = "declan-" + token_hex(16)
        request = request_factory(
            f"{url}/api/services/script/{sexy_script.split('.', 1)[1]}?return_response", headers=headers,
            data=json.dumps({"operation": operation, "music_player": player, "request_id": request_id, "routine_id": sexy_script}).encode(), method="POST",
        )
        try:
            with opener.open(request, timeout=8) as response:
                payload = json.loads(response.read(65536))
        except HTTPError as error:
            error.close()
            return ExecutionResult("I couldn't confirm the bedroom routine completed. Check its Home Assistant trace.", Outcome.UNVERIFIED), None
        except (OSError, ValueError):
            return ExecutionResult("I couldn't confirm the bedroom routine completed. Check its Home Assistant trace.", Outcome.UNVERIFIED), None

        result = payload.get("service_response") if isinstance(payload, dict) else None
        if isinstance(result, dict) and set(result) == {sexy_script}:
            result = result[sexy_script]
        if (not isinstance(result, dict) or result.get("operation") != operation
                or result.get("request_id") != request_id or result.get("routine_id") != sexy_script):
            return ExecutionResult("I couldn't verify the bedroom routine's result.", Outcome.UNVERIFIED), None

        lighting_ok = result.get("lighting_ok") is True
        if operation == "end":
            music_result = music_provider.control_result(
                ("media_stop", "bedroom"), connection, lambda _: inventory_result,
            )
            music_ok = music_result.outcome is Outcome.CONFIRMED
            if lighting_ok:
                detail = None if music_ok else "Bedroom lights restored. Bedroom music stop could not be verified."
                return ExecutionResult(choose_response("sexy_time_end", guest_mode()), Outcome.CONFIRMED if music_ok else Outcome.PARTIAL), detail
            playback = "The music has stopped." if music_ok else "I couldn't verify that the bedroom music stopped."
            return ExecutionResult(f"I couldn't verify the bedroom lights. {playback}", Outcome.PARTIAL if music_ok else Outcome.UNVERIFIED), None

        if not lighting_ok:
            return ExecutionResult("I couldn't verify the bedroom lights, so I held off on the playlist.", Outcome.UNVERIFIED), None
        volume_ok = True
        try:
            music_provider.request(connection, "/api/services/media_player/volume_set",
                          {"entity_id": player, "volume_level": 0.2})
        except (OSError, ValueError):
            volume_ok = False
        music_result = music_provider.play_result(("bedroom", "sexy time music", "spotify"), connection,
                                    lambda _: inventory_result)
        reply, outcome = music_result.reply, music_result.outcome
        spoken = choose_response("sexy_time_start", guest_mode())
        if outcome is Outcome.CONFIRMED and volume_ok:
            return ExecutionResult(spoken, Outcome.CONFIRMED), None
        volume_detail = "" if volume_ok else " Bedroom music volume could not be set."
        return ExecutionResult(spoken, Outcome.PARTIAL), f"Bedroom lights set. {reply}{volume_detail}"
    finally:
        gates.sexy_time.release()


