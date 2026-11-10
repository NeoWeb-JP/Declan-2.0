"""Route one household Spotify stream through Music Assistant."""

import json
import re
from threading import Lock
from time import sleep
from urllib.error import HTTPError
from urllib.request import Request


PLAYERS = {
    "bedroom": "media_player.bedroom_declan_voice_assistant",
    "kitchen": "media_player.kitchen_declan_voice_assistant",
    "everywhere": "media_player.everywhere_2",
}
ACTIVE = {"playing", "buffering", "paused"}
STOPPED = {"idle", "off", "standby", "on"}
HANDOFF = Lock()


def parse(phrase):
    match = re.fullmatch(
        r"(?:(?:move|transfer) (?:the )?music(?: to (?:the )?| )|"
        r"play (?:(.+?) in (?:the )?|(.+?) (?=everywhere(?: on spotify)?$)))"
        r"(bedroom|master bedroom|kitchen|everywhere)(?: on spotify)?",
        phrase,
    )
    if not match:
        return None
    title, group_title, room = match.groups()
    title = title or group_title
    if title in {"music", "the music", "this", "this music"}:
        title = None
    return room.removeprefix("master "), title


def request(connection, path, data=None):
    url, headers, opener = connection
    body = json.dumps(data).encode() if data is not None else None
    with opener.open(Request(url + path, data=body, headers=headers), timeout=4) as response:
        return json.load(response) if data is None else None


def spotify_id(player):
    content = (player.get("attributes") or {}).get("media_content_id")
    if isinstance(content, str) and re.match(r"^(?:spotify(?:--[^:]+)?(?::|://)|https://open\.spotify\.com/)", content):
        return content
    return None


def matches_track(player, title, artist):
    attributes = player.get("attributes") or {}
    return (str(attributes.get("media_title") or "").casefold() == title.casefold()
            and (not artist or str(attributes.get("media_artist") or "").casefold() == artist.casefold()))


def wait_for(connection, player, predicate):
    for attempt in range(4):
        if attempt:
            sleep(1)
        state = request(connection, "/api/states/" + player)
        if predicate(state):
            return True
    return False


def play(command, connection, read_inventory):
    room, title = command
    destination = PLAYERS[room]
    location = "everywhere" if room == "everywhere" else f"in the {room}"
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured"
    if not HANDOFF.acquire(blocking=False):
        return "A music request is already in progress.", "busy"
    stopped = False
    try:
        inventory, error = read_inventory(connection)
        if error:
            return "I couldn't check which players are active.", error
        players = {row["entity_id"]: row for row in inventory
                   if isinstance(row, dict) and row.get("entity_id") in PLAYERS.values()}
        if players.get(destination, {}).get("state") in (None, "unknown", "unavailable"):
            return f"The Music Assistant player {location} is unavailable.", "unavailable"
        streams = {entity: player for entity, player in players.items()
                   if player.get("state") in ACTIVE and spotify_id(player)}
        group = PLAYERS["everywhere"]
        if group in streams:
            members = streams[group]["attributes"].get("group_members") or []
            for entity in tuple(streams):
                if entity != group and entity in members and spotify_id(streams[entity]) == spotify_id(streams[group]):
                    del streams[entity]
        if len(streams) > 1:
            return "I found more than one active Spotify queue and couldn't tell which one to move.", "unverified"
        source = next(iter(streams), None)
        artist = ""
        if title and " by " in title:
            title, _, artist = title.rpartition(" by ")
        move = title is None or bool(source and matches_track(streams[source], title, artist))
        if title is None and source is None:
            return "I couldn't find an active Spotify queue. Tell me what to play.", "unavailable"
        if move and source == destination and streams[source]["state"] == "playing":
            return f"Spotify is already playing {location}.", "confirmed"
        if move and source == destination:
            request(connection, "/api/services/media_player/media_play", {"entity_id": destination})
        elif move:
            request(connection, "/api/services/music_assistant/transfer_queue",
                    {"entity_id": destination, "source_player": source, "auto_play": True})
        else:
            if source and source != destination:
                request(connection, "/api/services/media_player/media_stop", {"entity_id": source})
                if not wait_for(connection, source, lambda player: player.get("state") in STOPPED):
                    return "I couldn't confirm Spotify stopped on the previous player. I didn't start another stream.", "unverified"
                stopped = True
            data = {"entity_id": destination, "media_id": title, "enqueue": "play"}
            if artist:
                data.update(artist=artist, media_type="track")
            request(connection, "/api/services/music_assistant/play_media", data)
        if wait_for(connection, destination, lambda player: (
            player.get("state") == "playing" and spotify_id(player) and (
                spotify_id(player) == spotify_id(streams[source]) if move
                else matches_track(player, title, artist)
            )
        )):
            if stopped:
                return f"I stopped the previous Spotify stream and started {title} {location}.", "confirmed"
            return f"Spotify is playing {location}.", "confirmed"
        prefix = "I stopped the previous Spotify stream. " if stopped else ""
        return f"{prefix}I sent the music request {location}, but couldn't verify playback.", "unverified"
    except HTTPError as error:
        error.close()
        if error.code == 429:
            detail = "Music playback is being rate limited. I haven't retried the request."
        else:
            detail = "Home Assistant returned an error for the music request."
        return ("I stopped the previous stream. " if stopped else "") + detail, "unverified"
    except (OSError, ValueError):
        return ("I stopped the previous Spotify stream, but couldn't verify the new request." if stopped
                else "I couldn't verify the music request."), "unverified"
    finally:
        HANDOFF.release()
