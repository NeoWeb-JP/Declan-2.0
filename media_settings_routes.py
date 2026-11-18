"""Spotify credential and Home Assistant media player settings HTTP adapters."""

def spotify_settings(handler, body=None, *, music):
    try:
        if body is not None:
            music.save_spotify_credentials(body.get("client_id"), body.get("client_secret"))
            source = "saved"
        else:
            _, source = music.spotify_credentials()
    except (OSError, ValueError) as error:
        if body is not None and isinstance(error, ValueError):
            handler.send_json(400, {"error": "Enter both a valid Spotify Client ID and Client Secret."})
        else:
            handler.send_json(503, {"error": "Spotify settings are unavailable."})
        return
    handler.send_json(200, {"source": source})


def approved_player_settings(handler, body=None, *, ha_device_connection, ha_inventory, read_music_inventory_result, read_ha_areas, approved_area_labels, approved_media_players):
    connection = ha_device_connection()
    if connection is None:
        handler.send_json(503, {"error": "Home Assistant is not configured."})
        return
    inventory_result = ha_inventory.InventoryResult.coerce(read_music_inventory_result(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error:
        handler.send_json(503, {"error": "Home Assistant media inventory is unavailable."})
        return
    areas = read_ha_areas(connection)
    if not areas:
        handler.send_json(503, {"error": "Home Assistant areas are unavailable."})
        return
    candidates = {row["entity_id"]: row for row in inventory
                  if row.get("declan_music_assistant") is True
                  and row["entity_id"].startswith("media_player.")}
    room_labels = approved_area_labels(areas)
    rooms = sorted(room_labels)
    if body is not None:
        selected = body.get("rooms") if isinstance(body, dict) else None
        if not isinstance(selected, dict) or any(
            not isinstance(key, str) or key not in rooms
            or not isinstance(value, str) or value not in candidates
            for key, value in selected.items()
        ):
            handler.send_json(400, {"error": "Select registered Music Assistant players for known Home Assistant areas."})
            return
        try:
            approved_media_players.save(selected)
        except (OSError, ValueError):
            handler.send_json(503, {"error": "Could not save approved players."})
            return
    try:
        configured = approved_media_players.load()
    except (OSError, ValueError):
        handler.send_json(503, {"error": "Approved media player configuration is invalid."})
        return
    handler.send_json(200, {
        "configured": configured is not None,
        "rooms": rooms,
        "room_labels": room_labels,
        "selected": configured or {},
        "players": [
            {"entity_id": entity,
             "name": (row.get("attributes") or {}).get("friendly_name") or entity,
             "area": row.get("declan_area") or "",
             "state": row.get("state")}
            for entity, row in sorted(candidates.items())
        ],
    })

