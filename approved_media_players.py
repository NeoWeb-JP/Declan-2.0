"""Persistent, fail-closed approved Music Assistant destinations per HA area."""
import json
import os
import re
from pathlib import Path

ENTITY = re.compile(r"media_player\.[a-z0-9_]+\Z")
DEFAULT_PATH = Path(__file__).with_name(".data") / "approved-media-players.json"


def config_path():
    return Path(os.environ.get("DECLAN_APPROVED_MEDIA_PLAYERS_FILE") or DEFAULT_PATH)


def load():
    """Return None when not configured; raise on invalid configuration."""
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), dict):
        raise ValueError("Approved media players must contain a rooms object")
    rooms = data["rooms"]
    if any(not isinstance(k, str) or not k.strip()
           or not isinstance(v, str) or not ENTITY.fullmatch(v)
           for k, v in rooms.items()):
        raise ValueError("Invalid room or media player entity in approved media players")
    return {" ".join(k.casefold().split()).removeprefix("master "): v
            for k, v in rooms.items()}


def save(rooms):
    """Validate and atomically persist owner-selected players."""
    if not isinstance(rooms, dict):
        raise ValueError("Expected room-to-player mapping")
    for room, entity in rooms.items():
        if not isinstance(room, str) or not room.strip() or not isinstance(entity, str) or not ENTITY.fullmatch(entity):
            raise ValueError("Invalid approved player mapping")
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        json.dump({"rooms": rooms}, stream, indent=2)
        stream.write("\n")
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def resolve(inventory):
    """Return only explicitly approved, currently registered Music Assistant players."""
    approved = load()
    if approved is None:
        return None
    entities = {row.get("entity_id"): row for row in inventory if isinstance(row, dict)}
    destinations = {}
    for room, entity in approved.items():
        row = entities.get(entity)
        destinations[room] = entity if row and row.get("declan_music_assistant") is True else None
    return destinations
