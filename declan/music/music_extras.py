"""Music controls that were missing (FUT-28, #834).

- "What song is this?" / "who sings this?"
- "Play <song> next" / "queue <song>": added after the current track.
- "Play something similar" / "more like this": Music Assistant radio from the current track.
- "Don't play this artist again": the artist is skipped whenever they come up
  (Settings -> Spotify playlists shows and removes blocked artists).
- Sleep timer: "stop the music in 30 minutes" fades out over the last 30
  seconds, stops, then puts the volume back for next time. "Cancel the sleep
  timer" stops it; starting new music in that room cancels it too. A restart of
  Declan cancels sleep timers.

Everything goes through Music Assistant and the approved players. Commands
only report what Home Assistant accepted; nothing claims a song is playing
unless the player says so.
"""
import re
import sqlite3
import threading
from urllib.error import HTTPError

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import ha_inventory

FADE_STEPS = 6
FADE_SECONDS = 30
MAX_SLEEP_SECONDS = 4 * 3600
_ROOM = r"(?: (?:in|on) (?:the )?(?P<room>[a-z][a-z ]{1,40}?)| (?P<group>everywhere|upstairs|downstairs))?"
_NOW_PLAYING = re.compile(r"(?:what(?:'s| is) (?:playing|the song|this song|this track|that song|that track)|"
                          r"what song is (?:this|that|playing)|who (?:sings|sang) (?:this|that)(?: song)?|who is singing|"
                          r"what are (?:we|you) (?:listening to|playing)|name (?:this|that) (?:song|tune))" + _ROOM)
_NEXT = re.compile(r"(?:play (?P<title>.+?) next|queue (?:up )?(?P<title2>.+?)|add (?P<title3>.+?) to the queue|"
                   r"play (?P<title4>.+?) after this(?: one| song)?)" + _ROOM)
_SIMILAR = re.compile(r"(?:play (?:something|more|songs|music) (?:similar|like this|like that)|more like this|"
                      r"play similar (?:music|songs|stuff)|(?:start|play) (?:a |the )?radio (?:based on|from) this(?: song)?)" + _ROOM)
_BLOCK_ARTIST = re.compile(r"(?:(?:don't|do not|never) play (?:this|that) (?:artist|band|singer)(?: again)?|"
                           r"(?:block|ban) (?:this|that) (?:artist|band|singer)|"
                           r"(?:i|we) (?:hate|can't stand) (?:this|that) (?:artist|band|singer))" + _ROOM)
_SLEEP = re.compile(r"(?:(?:stop|turn off|fade out|switch off) (?:the )?(?:music|spotify|playback) in |"
                    r"(?:set )?(?:a |the )?(?:music )?sleep timer (?:for )?)(?P<duration>.+?)" + _ROOM)
_SLEEP_CANCEL = re.compile(r"(?:cancel|stop|turn off) (?:the )?(?:music )?sleep timer" + _ROOM)
_SLEEPERS: dict[str, tuple[threading.Timer, threading.Event]] = {}
_SLEEPERS_LOCK = threading.Lock()


def _room(found):
    if found["group"]:
        return found["group"]
    room = found["room"]
    if room and room.strip() in {"here", "this room"}:
        return None
    return room.strip() if room else None


def parse(phrase):
    """("now_playing" | "next" | "similar" | "block_artist" | "sleep" | "sleep_cancel", room, argument) or None."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    if found := _SLEEP_CANCEL.fullmatch(text):
        return ("sleep_cancel", _room(found), None)
    if found := _SLEEP.fullmatch(text):
        from declan.timers.timers import duration_seconds
        seconds = duration_seconds(found["duration"])
        return ("sleep", _room(found), seconds) if seconds else None
    if found := _NOW_PLAYING.fullmatch(text):
        return ("now_playing", _room(found), None)
    if found := _SIMILAR.fullmatch(text):
        return ("similar", _room(found), None)
    if found := _BLOCK_ARTIST.fullmatch(text):
        return ("block_artist", _room(found), None)
    if found := _NEXT.fullmatch(text):
        title = next(value for value in (found["title"], found["title2"], found["title3"], found["title4"]) if value)
        if title in {"this", "that", "it", "music", "the music", "the next song", "the next track"}:
            return None
        return ("next", _room(found), title)
    return None


def _player(music, inventory, room, origin):
    """(entity, attributes, label) of the player to act on, or an ExecutionResult explaining why not."""
    destinations, players = music.music_players(inventory, origin=origin) if origin else music.music_players(inventory)
    if room is None and origin:
        areas = {music.room_key(row["declan_area"]) for row in inventory
                 if (row.get("entity_id") == origin or row.get("declan_device") == origin)
                 and isinstance(row.get("declan_area"), str) and row["declan_area"].strip()}
        if len(areas) == 1:
            candidate = destinations.get(areas.pop())
            if candidate and players.get(candidate, {}).get("state") in music.ACTIVE:
                return candidate, players[candidate].get("attributes") or {}, "here"
    if room is not None:
        entity = destinations.get(music.room_key(room))
        if not entity:
            return ExecutionResult(f"I don't have a music player for the {room}.", Outcome.UNRESOLVED)
        return entity, players.get(entity, {}).get("attributes") or {}, "everywhere" if room == "everywhere" else f"in the {room}"
    active = music.playback_sources(destinations, players)
    if len(active) == 1:
        entity, player = next(iter(active.items()))
        return entity, player.get("attributes") or {}, "on the music player"
    if not active:
        return ExecutionResult("Nothing's playing, boet.", Outcome.UNRESOLVED)
    return ExecutionResult("Music's playing in more than one room. Which one?", Outcome.UNRESOLVED)


def _artists(attributes):
    artist = attributes.get("media_artist")
    return [name.strip() for name in re.split(r",|&| feat\. | ft\. ", artist) if name.strip()] if isinstance(artist, str) else []


def blocked_artists():
    from declan.music import music
    with music.preference_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS blocked_artists (name TEXT PRIMARY KEY, label TEXT NOT NULL)")
        return {name: label for name, label in db.execute("SELECT name, label FROM blocked_artists")}


def unblock_artist(name):
    from declan.music import music
    with music.preference_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS blocked_artists (name TEXT PRIMARY KEY, label TEXT NOT NULL)")
        return db.execute("DELETE FROM blocked_artists WHERE name = ?", (name.casefold().strip(),)).rowcount > 0


def is_blocked(attributes, blocked=None):
    blocked = blocked_artists() if blocked is None else blocked
    return any(name.casefold() in blocked for name in _artists(attributes))


def cancel_sleep(entity):
    with _SLEEPERS_LOCK:
        sleeper = _SLEEPERS.pop(entity, None)
    if sleeper:
        sleeper[0].cancel()
        sleeper[1].set()
    return sleeper is not None


def _fade_and_stop(music, connection, entity, cancelled):
    try:
        state = music.request(connection, f"/api/states/{entity}", timeout=2)
        volume = (state or {}).get("attributes", {}).get("volume_level") if isinstance(state, dict) else None
        if isinstance(volume, (int, float)) and 0 < volume <= 1:
            for step in range(1, FADE_STEPS + 1):
                if cancelled.wait(FADE_SECONDS / FADE_STEPS):
                    return
                music.request(connection, "/api/services/media_player/volume_set",
                              {"entity_id": entity, "volume_level": round(volume * (1 - step / FADE_STEPS), 3)}, timeout=2)
        if cancelled.is_set():
            return
        music.request(connection, "/api/services/media_player/media_stop", {"entity_id": entity}, timeout=2)
        if isinstance(volume, (int, float)) and 0 < volume <= 1:
            music.request(connection, "/api/services/media_player/volume_set",
                          {"entity_id": entity, "volume_level": volume}, timeout=2)
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, TimeoutError):
        pass
    finally:
        with _SLEEPERS_LOCK:
            if _SLEEPERS.get(entity, (None, cancelled))[1] is cancelled:
                _SLEEPERS.pop(entity, None)


def _minutes(seconds):
    minutes = round(seconds / 60)
    if seconds < 60:
        return f"{seconds} seconds"
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours, rest = divmod(minutes, 60)
    return f"{hours} hour{'s' if hours != 1 else ''}" + (f" {rest} minutes" if rest else "")


def result(command, connection, read_inventory, *, origin=None, timer_factory=threading.Timer):
    """Typed outcome for a parsed extra music command."""
    from declan.music import music
    kind, room, argument = command
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    if kind == "sleep" and not 60 <= argument <= MAX_SLEEP_SECONDS:
        return ExecutionResult("Give me a sleep timer between a minute and four hours.", Outcome.UNRESOLVED)
    inventory_result = ha_inventory.InventoryResult.coerce(read_inventory(connection))
    if inventory_result.error:
        return ExecutionResult("I couldn't check the music players.", inventory_result.error)
    found = _player(music, inventory_result.inventory, room, origin)
    if isinstance(found, ExecutionResult):
        if kind == "sleep_cancel" and found.outcome is Outcome.UNRESOLVED:
            with _SLEEPERS_LOCK:
                running = list(_SLEEPERS)
            if len(running) == 1:
                cancel_sleep(running[0])
                return ExecutionResult("Sleep timer cancelled. The music stays on.", Outcome.CONFIRMED)
        return found
    entity, attributes, location = found
    title, artists = attributes.get("media_title"), _artists(attributes)
    try:
        if kind == "now_playing":
            if not isinstance(title, str) or not title.strip():
                return ExecutionResult("I can't tell what's playing. Music Assistant isn't saying.", Outcome.UNRESOLVED)
            by = f" by {', '.join(artists)}" if artists else ""
            return ExecutionResult(f"This is {title}{by}.", Outcome.CHAT_ANSWER)
        if kind == "sleep_cancel":
            return ExecutionResult("Sleep timer cancelled. The music stays on." if cancel_sleep(entity)
                                   else "There's no sleep timer running.", Outcome.CONFIRMED)
        if kind == "sleep":
            cancel_sleep(entity)
            cancelled = threading.Event()
            timer = timer_factory(max(0, argument - FADE_SECONDS), _fade_and_stop, args=(music, connection, entity, cancelled))
            timer.daemon = True
            with _SLEEPERS_LOCK:
                _SLEEPERS[entity] = (timer, cancelled)
            timer.start()
            return ExecutionResult(f"Sleep timer set. The music {location} fades out in {_minutes(argument)}.",
                                   Outcome.CONFIRMED)
        if kind == "block_artist":
            if not artists:
                return ExecutionResult("I can't tell who this is, so I can't block them.", Outcome.UNRESOLVED)
            with music.preference_db() as db:
                db.execute("CREATE TABLE IF NOT EXISTS blocked_artists (name TEXT PRIMARY KEY, label TEXT NOT NULL)")
                for name in artists:
                    db.execute("INSERT OR IGNORE INTO blocked_artists VALUES (?, ?)", (name.casefold(), name))
            music.request(connection, "/api/services/media_player/media_next_track", {"entity_id": entity}, timeout=3)
            return ExecutionResult(f"Blocked {', '.join(artists)}. Skipping, and I'll skip them whenever they come up.",
                                   Outcome.CONFIRMED)
        if kind == "similar":
            current = music.spotify_id({"attributes": attributes})
            seed = current or (f"{title} by {artists[0]}" if isinstance(title, str) and artists else None)
            if not seed:
                return ExecutionResult("I can't tell what's playing, so I don't know what's similar.", Outcome.UNRESOLVED)
            music.request(connection, "/api/services/music_assistant/play_media",
                          {"entity_id": entity, "media_id": seed, "media_type": "track", "radio_mode": True,
                           "enqueue": "replace"}, timeout=8)
            return ExecutionResult(f"Starting more like {title or 'this'} {location}.", Outcome.REQUESTED)
        # kind == "next"
        song, _, artist = argument.rpartition(" by ") if " by " in argument else (argument, "", "")
        if music.music_assistant_search_enabled():
            media_id, label = argument, argument
        else:
            found_media = music.search_media(connection, entity, song, artist, "spotify")
            if not found_media:
                return ExecutionResult(f"I couldn't find {argument} on Spotify.", Outcome.UNRESOLVED)
            media_id, label = found_media[0], found_media[2]
        music.request(connection, "/api/services/music_assistant/play_media",
                      {"entity_id": entity, "media_id": media_id, "enqueue": "next"}, timeout=8)
        return ExecutionResult(f"{label} is up next.", Outcome.REQUESTED)
    except HTTPError as error:
        error.close()
        return ExecutionResult("Music Assistant didn't accept that.", Outcome.UNAVAILABLE)
    except (OSError, ValueError, TimeoutError, sqlite3.Error):
        return ExecutionResult("I couldn't reach Music Assistant.", Outcome.UNAVAILABLE)
