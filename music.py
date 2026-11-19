"""Route one household Spotify stream through Music Assistant."""

import json
import diagnostics
import ha_inventory
import approved_media_players
from execution_results import ExecutionResult, Outcome
from music_provider_result import music_execution_result
from music_provider_result import PlayerAvailability, PlayerAvailabilityResult
from music_provider_result import MusicFailureKind, MusicRequestFailure
import os
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from random import choices
from tempfile import NamedTemporaryFile
import music_runtime_state
from threading import Thread
from time import monotonic, sleep, time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request


PLAYERS = {
    "bedroom": "media_player.bedroom_declan_voice_assistant",
    "kitchen": "media_player.kitchen_declan_voice_assistant",
    "everywhere": "media_player.everywhere",
}
ACTIVE = {"playing", "buffering", "paused"}
STOPPED = {"idle", "off", "standby", "on"}
CONTROLS = {
    "stop": "media_stop", "pause": "media_pause",
    "continue": "media_play", "resume": "media_play", "play": "media_play",
    "skip": "media_next_track", "next": "media_next_track",
    "previous": "media_previous_track", "go back": "media_previous_track",
}
RUNTIME = music_runtime_state.MusicRuntimeState()
FAVOURITE_TRACK = "https://open.spotify.com/track/0JkIre0YxNmKGMU5V7ZiDx"
SPOTIFY_PRESETS = {
    "coward of the county": FAVOURITE_TRACK,
    "coward of the county by kenny rogers": FAVOURITE_TRACK,
}
SPOTIFY_PLAYLIST_FALLBACKS = {
    "romantic dinner music": ("https://open.spotify.com/playlist/37i9dQZF1DXbm6HfkbMtFZ", "playlist", "Feel Good Dinner"),
    "sexy time music": ("https://open.spotify.com/playlist/0mQbGXAlmsI3T2Vyfa0IVd", "playlist", "Sexy Time"),
}
SPOTIFY_REFERENCE = re.compile(
    r"(?:https://open\.spotify\.com/|spotify(?:--[\w-]+)?://|spotify:)"
    r"(track|album|artist|playlist)[/:]([A-Za-z0-9]{22})/?(?:\?[^\s#]*)?"
)
SPOTIFY_SETTINGS = Path(__file__).with_name(".data") / "spotify-settings.json"
PREFERENCES = SPOTIFY_SETTINGS.with_name("music-preferences.sqlite3")


def room_key(name):
    return " ".join(name.casefold().split()).removeprefix("master ")


def music_players(inventory, *, origin=None):
    approved = approved_media_players.resolve(inventory)
    if approved is not None:
        entities = {row["entity_id"]: row for row in inventory
                    if isinstance(row, dict) and isinstance(row.get("entity_id"), str)}
        return approved, {entity: entities[entity] for entity in approved.values() if entity in entities}
    # Strict by default: registered MA devices are only candidates until the
    # user approves the room mapping in Settings. The opt-in compatibility
    # switch exists solely for installations migrating older auto-discovery.
    if os.environ.get("DECLAN_ALLOW_UNCONFIGURED_MA", "") != "1":
        return {}, {}
    entities = {row["entity_id"]: row for row in inventory
                if isinstance(row, dict) and isinstance(row.get("entity_id"), str)}
    registered = any("declan_music_assistant" in row for row in entities.values())
    if registered:
        # Fail closed: only registered Music Assistant players may be selected.
        groups = [entity for entity, row in entities.items()
                  if row.get("declan_music_assistant") is True
                  and row.get("state") not in (None, "unknown", "unavailable")
                  and (str((row.get("attributes") or {}).get("friendly_name", "")).strip().casefold() == "everywhere"
                       or re.fullmatch(r"media_player\.everywhere(?:_[0-9]+)?", entity))]
        destinations = {"everywhere": groups[0] if len(groups) == 1 else None}
        rooms: dict[str, list[str]] = {}
        for entity, row in entities.items():
            area = row.get("declan_area")
            if row.get("declan_music_assistant") is True and isinstance(area, str) and area.strip():
                rooms.setdefault(room_key(area), []).append(entity)
        def devices(row):
            linked = {row.get("declan_device")} - {None, ""}
            sources = row.get("declan_source_entities")
            if isinstance(sources, list):
                linked.update(entities[source].get("declan_device") for source in sources
                              if isinstance(source, str) and source in entities)
            return linked - {None, ""}

        # MA wrappers can have their own HA device. Follow their registered
        # source entities back to the satellite's device, never its name.
        origin_row = entities.get(origin) if isinstance(origin, str) else None
        origin_devices = devices(origin_row) if origin_row else ({origin} if origin else set())
        satellite_devices = {row.get("declan_device") for entity, row in entities.items()
                             if entity.startswith("assist_satellite.")} - {None, ""}
        for room, candidates in rooms.items():
            available = [entity for entity in candidates if entities[entity].get("state") not in (None, "unknown", "unavailable")]
            direct = [entity for entity in available if devices(entities[entity]) & origin_devices]
            associated = [entity for entity in available if devices(entities[entity]) & satellite_devices]
            preferred = direct or associated or available
            destinations[room] = preferred[0] if len(preferred) == 1 else None
        players = {entity: row for entity, row in entities.items()
                   if row.get("declan_music_assistant") is True or entity == destinations["everywhere"]}
        return destinations, players
    # Never fall back to hardcoded household targets without MA registration.
    return {}, {}


@contextmanager
def preference_db():
    PREFERENCES.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(PREFERENCES, timeout=1)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS preferences (uri TEXT PRIMARY KEY, weight INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS recent_playlists (id INTEGER PRIMARY KEY, category TEXT, uri TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS playlist_play_counts (uri TEXT PRIMARY KEY, plays INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS search_cache (key TEXT PRIMARY KEY, uri TEXT NOT NULL, kind TEXT NOT NULL, "
                   "name TEXT NOT NULL, saved REAL NOT NULL)")
        yield db


def parse_feedback(phrase):
    match = re.fullmatch(
        r"(never play this song again|never play this playlist again|i don't like this song|we don't like this song|i don't like this playlist|we don't like this playlist|i love this song|we love this song|i love this playlist|we love this playlist|i like this song|we like this song|i like this playlist|we like this playlist)"
        r"(?: (?:in (?:the )?)?(.+))?", phrase,
    )
    return match.groups() if match else None


def playback_sources(destinations, players):
    group = destinations.get("everywhere")
    group_state = players.get(group, {})
    members = ((group_state.get("attributes") or {}).get("group_members") or []
               if group_state.get("state") in ACTIVE else [])
    return {entity: player for entity, player in players.items()
            if player.get("state") in ACTIVE and (entity == group or entity not in members)}


def feedback(command, connection, read_inventory):
    """Legacy reply/outcome API backed by a validated typed provider result."""
    return music_execution_result(_feedback_provider(command, connection, read_inventory)).as_legacy_pair()


def _feedback_provider(command, connection, read_inventory):
    phrase, room = command
    if connection is None or not RUNTIME.handoff.acquire(blocking=False):
        return ExecutionResult("I couldn't check the current music. Try again in a moment.", Outcome.UNAVAILABLE)
    try:
        inventory_result = ha_inventory.InventoryResult.coerce(read_inventory(connection))
        inventory, error = inventory_result.inventory, inventory_result.error
        if error:
            return ExecutionResult("I couldn't check what's playing.", error)
        destinations, players = music_players(inventory)
        active = playback_sources(destinations, players)
        if room:
            entity = destinations.get(room_key(room))
            active = {entity: active[entity]} if entity in active else {}
        if len(active) != 1:
            return ExecutionResult("Tell me which active music player you mean.", Outcome.UNRESOLVED)
        entity, player = next(iter(active.items()))
        attrs = player.get("attributes") or {}
        playlist = "playlist" in phrase
        kind = "playlist" if playlist else "track"
        uri = next((media_key(value) for value in (attrs.get("media_playlist_id"), attrs.get("media_content_id"))
                    if isinstance(value, str) and media_key(value).startswith(f"spotify://{kind}/")
                    and SPOTIFY_REFERENCE.fullmatch(value)), None)
        if not uri:
            return ExecutionResult(f"I couldn't identify the current Spotify {kind}.", Outcome.UNRESOLVED)
        ban = phrase.startswith("never") or "don't like" in phrase
        with preference_db() as db:
            if not ban and db.execute("SELECT 1 FROM preferences WHERE uri = ? AND weight = 0", (uri,)).fetchone():
                return ExecutionResult("That song is on your do-not-play list.", Outcome.UNRESOLVED)
            db.execute("INSERT INTO preferences VALUES (?, ?) ON CONFLICT(uri) DO UPDATE SET weight = "
                       "CASE WHEN excluded.weight = 0 THEN 0 ELSE min(5, max(1, weight) + 1) END",
                       (uri, 0 if ban else 3))
        label = (attrs.get("media_playlist") or "this playlist") if playlist else (attrs.get("media_title") or "this song")
        return ExecutionResult(f"Blocked {label}. I'll skip it when it comes up." if ban else f"Saved {label} as a favourite.", Outcome.MUSIC_FEEDBACK)
    except (OSError, ValueError, sqlite3.Error):
        return ExecutionResult("I couldn't save that music preference.", Outcome.UNAVAILABLE)
    finally:
        RUNTIME.handoff.release()


def skip_blocked_tracks(connection, read_inventory):
    if connection is None or not PREFERENCES.exists() or not RUNTIME.handoff.acquire(blocking=False):
        return
    try:
        with preference_db() as db:
            blocked = {uri for (uri,) in db.execute("SELECT uri FROM preferences WHERE weight = 0")}
        if not blocked:
            return
        inventory_result = ha_inventory.InventoryResult.coerce(read_inventory(connection))
        inventory, error = inventory_result.inventory, inventory_result.error
        if error:
            return
        now = monotonic()
        for entity, player in playback_sources(*music_players(inventory)).items():
            track = media_key(spotify_id(player))
            attrs = player.get("attributes") or {}
            playlist_uri = next((media_key(value) for value in
                                 (attrs.get("media_playlist_id"), attrs.get("media_content_id"))
                                 if isinstance(value, str) and
                                 media_key(value).startswith("spotify://playlist/")), None)
            if player.get("state") == "playing" and (track in blocked or playlist_uri in blocked) and RUNTIME.allow_blacklist_skip(entity, now):
                request(connection, "/api/services/media_player/media_next_track", {"entity_id": entity}, timeout=2)
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, sqlite3.Error):
        pass
    finally:
        RUNTIME.handoff.release()


class SpotifyNotConfigured(Exception):
    """Spotify search needs its own application credentials."""


def spotify_credentials():
    try:
        saved = json.loads(SPOTIFY_SETTINGS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        environment_credentials = tuple(os.environ.get(key, "").strip()
                            for key in ("DECLAN_SPOTIFY_CLIENT_ID", "DECLAN_SPOTIFY_CLIENT_SECRET"))
        return environment_credentials, "environment" if all(environment_credentials) else "unconfigured"
    if not isinstance(saved, dict):
        raise ValueError("Invalid Spotify settings")
    credentials = (saved.get("client_id"), saved.get("client_secret"))
    if not all(isinstance(value, str) and value for value in credentials):
        raise ValueError("Invalid Spotify settings")
    return credentials, "saved"


def save_spotify_credentials(client_id, client_secret):
    with RUNTIME.spotify_token_lock:
        if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value.strip())
                   for value in (client_id, client_secret)):
            raise ValueError("Enter both the Spotify Client ID and Client Secret.")
        SPOTIFY_SETTINGS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = NamedTemporaryFile(mode="w", encoding="utf-8", dir=SPOTIFY_SETTINGS.parent, delete=False)
        temp_path = Path(temp.name)
        try:
            with temp:
                json.dump({"client_id": client_id.strip(), "client_secret": client_secret.strip()}, temp)
            temp_path.replace(SPOTIFY_SETTINGS)
        finally:
            temp_path.unlink(missing_ok=True)


@diagnostics.timed("spotify_search")
def spotify_search(opener, title, artist, types):
    with RUNTIME.spotify_token_lock:
        credentials, _ = spotify_credentials()
        if not all(credentials):
            raise SpotifyNotConfigured
        now = monotonic()
        if RUNTIME.spotify_token is None or RUNTIME.spotify_token[0] != credentials or RUNTIME.spotify_token[2] <= now:
            data = urlencode(dict(zip(("client_id", "client_secret"), credentials))
                             | {"grant_type": "client_credentials"}).encode()
            token_request = Request("https://accounts.spotify.com/api/token", data=data,
                                    headers={"Content-Type": "application/x-www-form-urlencoded"})
            with opener.open(token_request, timeout=4) as response:
                token = json.load(response)
            access_token = token.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("Spotify did not return an access token")
            RUNTIME.spotify_token = (credentials, access_token, now + max(0, int(token.get("expires_in", 0)) - 30))
        access_token = RUNTIME.spotify_token[1]
    def quoted(value):
        return value.replace('\\', '\\\\').replace('"', '\\"')
    query = f'track:"{quoted(title)}" artist:"{quoted(artist)}"' if artist else quoted(title)
    market = os.environ.get("DECLAN_SPOTIFY_MARKET", "GB").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", market):
        raise ValueError("DECLAN_SPOTIFY_MARKET must be a two-letter country code")
    # Spotify search accepts at most 10 results per request (2026 API).
    # The 25-playlist category capacity is independent of this page size.
    playlist_search = types == ("playlist",)
    page_size = 10 if playlist_search else 5
    collected = []
    seen = set()
    for offset in (range(0, 25, page_size) if playlist_search else (0,)):
        limit = min(page_size, 25 - offset) if playlist_search else page_size
        params = urlencode({"q": query, "type": ",".join(types), "market": market,
                            "limit": limit, **({"offset": offset} if playlist_search else {})})
        search_request = Request("https://api.spotify.com/v1/search?" + params,
                                 headers={"Authorization": f"Bearer {access_token}"})
        try:
            with opener.open(search_request, timeout=8) as response:
                results = json.load(response)
        except HTTPError as error:
            if error.code == 401:
                with RUNTIME.spotify_token_lock:
                    if RUNTIME.spotify_token is not None and RUNTIME.spotify_token[1] == access_token:
                        RUNTIME.spotify_token = None
            raise
        for kind in types:
            page = results.get(f"{kind}s", {})
            items = page.get("items") or [] if isinstance(page, dict) else []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    continue
                identifier = str(item.get("id", ""))
                if not re.fullmatch(r"[A-Za-z0-9]{22}", identifier):
                    continue
                link = f"https://open.spotify.com/{kind}/{identifier}"
                if link not in seen:
                    seen.add(link)
                    collected.append((link, kind, item["name"]))
        if not playlist_search or not isinstance(page, dict) or len(items) < limit:
            break
    return collected


def parse(phrase):
    phrase = re.sub(r" on (spotify|radio|tunein)( in (?:the )?(?:bedroom|master bedroom|kitchen|everywhere))$",
                    r"\2 on \1", phrase)
    match = re.fullmatch(
        r"(?:(?:move|transfer) (?:the )?music(?: to (?:the )?| )|"
        r"play (?:(.+) in (?:the )?|(.+?) (?=everywhere\b)))"
        r"(.+?)(?: on (spotify|radio|tunein))?",
        phrase,
    )
    if not match:
        unqualified = re.fullmatch(r"play (.+?)(?: on (spotify|radio|tunein))?", phrase)
        if not unqualified:
            return None
        title, provider = unqualified.groups()
        room = None
    else:
        title, group_title, room, provider = match.groups()
        title = title or group_title
    if provider is None and title:
        station = re.fullmatch(r"radio (.+)|(.+) radio", title)
        if station:
            title = station[1] or station[2]
            provider = "radio"
    if title in {"music", "the music", "this", "this music"}:
        title = None
    return room_key(room) if room else None, title, provider or "spotify"


def reply_first_enabled():
    """Opt in to answering once Home Assistant accepts a play request.

    Playback is then verified in the background and a failure is announced on
    the originating satellite. Off by default: the reply is only spoken after
    verification, which is slower but never claims more than was observed.
    """
    return os.environ.get("DECLAN_MUSIC_REPLY_FIRST", "").strip() == "1"


def _satellite_for(inventory, origin):
    """Return the single Assist satellite entity for an origin, else None."""
    if not isinstance(origin, str) or not origin:
        return None
    matches = [row.get("entity_id") for row in inventory
               if isinstance(row, dict) and isinstance(row.get("entity_id"), str)
               and re.fullmatch(r"assist_satellite\.[a-z0-9_]{1,100}", row["entity_id"])
               and origin in (row["entity_id"], row.get("declan_device"))]
    return matches[0] if len(matches) == 1 else None


def _verify_in_background(connection, destination, verify, *, attempts, location,
                          satellite, observed, on_playing):
    """Check playback after the reply was sent; speak up only if nothing started.

    Runs in a fresh thread context so it never mutates the request's live trace;
    its result is added to the saved trace afterwards. Any later music command
    supersedes the check, so a quick "Stop" is never contradicted by a stale
    failure announcement.
    """
    generation = RUNTIME.begin_operation()
    trace = diagnostics.ACTIVE.get()

    def work():
        started = monotonic()
        try:
            verified = wait_for(connection, destination, verify, attempts=attempts)
        except (OSError, ValueError, TimeoutError):
            verified = False
        outcome = (Outcome.CONFIRMED if verified
                   else Outcome.PARTIAL if observed() else Outcome.UNVERIFIED)
        entry = {"stage": "music_verification", "player_entity_id": destination,
                 "duration_ms": round((monotonic() - started) * 1000)}
        diagnostics.set_outcome(entry, outcome)
        if trace is not None:
            # The request's own trace is saved when its reply is sent.
            deadline = monotonic() + 5
            while "_saved" not in trace and monotonic() < deadline:
                sleep(0.05)
            diagnostics.amend(trace, entry)
        if verified or observed():
            on_playing()
        if outcome is not Outcome.UNVERIFIED or not satellite or not RUNTIME.is_current(generation):
            return
        try:
            request(connection, "/api/services/assist_satellite/announce",
                    {"entity_id": satellite, "preannounce": False,
                     "message": f"Sorry, I couldn't confirm the music started {location}."},
                    timeout=7)
        except (OSError, ValueError, TimeoutError):
            pass

    Thread(target=work, daemon=True, name="music-verify").start()


def request(connection, path, data=None, *, timeout=None):
    if data is not None and path.startswith("/api/services/"):
        # Any state-changing music call supersedes a pending background check.
        RUNTIME.begin_operation()
    label = ('stop_dispatch' if path.endswith('/media_stop') else
             'play_dispatch' if path.endswith('/play_media') else 'ha_media_request')
    with diagnostics.stage(label) as entry:
        # Only record validated entity IDs, never URLs, headers or media payloads.
        entity = data.get("entity_id") if isinstance(data, dict) else path.removeprefix("/api/states/")
        if isinstance(entity, str) and re.fullmatch(r"media_player\.[a-z0-9_]{1,100}", entity):
            entry["player_entity_id"] = entity
        source = data.get("source_player") if isinstance(data, dict) else None
        if isinstance(source, str) and re.fullmatch(r"media_player\.[a-z0-9_]{1,100}", source):
            entry["source_player_entity_id"] = source
        try:
            return _request(connection, path, data, timeout=timeout)
        except HTTPError as error:
            failure = MusicRequestFailure.from_http_status(error.code)
            entry["http_status"] = failure.http_status
            entry["failure_kind"] = failure.kind.value
            raise
        except TimeoutError:
            entry["failure_kind"] = MusicRequestFailure(MusicFailureKind.TIMEOUT).kind.value
            raise


def player_availability_result(entity, state) -> PlayerAvailabilityResult:
    """Record the selected player even when no service can be dispatched."""
    result = PlayerAvailabilityResult(PlayerAvailability.UNAVAILABLE if state in
        (None, "unknown", "unavailable") else PlayerAvailability.AVAILABLE)
    with diagnostics.stage("music_player") as entry:
        if isinstance(entity, str) and re.fullmatch(r"media_player\.[a-z0-9_]{1,100}", entity):
            entry["player_entity_id"] = entity
        entry["outcome"] = result.status.value
    return result


def player_available(entity, state):
    """Compatibility API retaining the original boolean availability result."""
    return player_availability_result(entity, state).available


def _request(connection, path, data=None, *, timeout=None):
    url, headers, opener = connection
    body = json.dumps(data).encode() if data is not None else None
    search = path.endswith("/search?return_response")
    with opener.open(Request(url + path, data=body, headers=headers),
                     timeout=timeout if timeout is not None else 10 if search else 4) as response:
        if data is None or search:
            return json.load(response)
        if path == "/api/template":
            return response.read().decode().strip()


def parse_control(phrase):
    dislike = re.fullmatch(
        r"(?:i|we) (?:do not|don['’]t) like this (?:song|track)"
        r"(?: in (?:the )?(.+))?", phrase,
    )
    if dislike:
        room = dislike[1]
        return "media_next_track", room_key(room) if room else None
    match = re.fullmatch(
        r"(stop|pause|continue|resume|play|skip|next|previous|go back)"
        r"(?: (?:the |this )?(music|playback|playing|spotify|radio|track|song|next track|next song|previous track|previous song))?"
        r"(?: in (?:the )?(.+)| (bedroom|master bedroom|kitchen|everywhere))?",
        phrase,
    )
    if not match:
        return None
    verb, subject, named_room, short_room = match.groups()
    room = named_room or short_room
    if verb == "play" and subject not in {"music", "playback", "next track", "next song", "previous track", "previous song"}:
        return None
    action = CONTROLS[subject.split()[0] if verb == "play" and subject.startswith(("next ", "previous ")) else verb]
    return action, room_key(room) if room else None


@diagnostics.timed("music_control")
def control(command, connection, read_inventory, *, origin=None, read_areas=None, assist=False):
    """Legacy reply/outcome API backed by a validated typed provider result."""
    return music_execution_result(_control_provider(command, connection, read_inventory, origin=origin, read_areas=read_areas, assist=assist)).as_legacy_pair()


def _control_provider(command, connection, read_inventory, *, origin=None, read_areas=None, assist=False):
    action, room = command
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    if not RUNTIME.handoff.acquire(blocking=False):
        return ExecutionResult("A music request is already in progress.", Outcome.BUSY)
    location = "on the music player"
    try:
        inventory_result = ha_inventory.InventoryResult.coerce(read_inventory(connection))
        inventory, error = inventory_result.inventory, inventory_result.error
        if error is Outcome.UNAVAILABLE:
            inventory_result = ha_inventory.InventoryResult.coerce(read_inventory(connection))
            inventory, error = inventory_result.inventory, inventory_result.error
        if error:
            return ExecutionResult("I couldn't check the music players.", error)
        destinations, players = music_players(inventory)
        # Unqualified Stop is household-wide, regardless of the originating room.
        # Only approved Music Assistant destinations may receive commands.
        if action == "media_stop" and room is None:
            active = dict.fromkeys(
                entity for entity in destinations.values()
                if entity and players.get(entity, {}).get("state") in ACTIVE
            )
            if not active:
                return ExecutionResult("There's no active Music Assistant playback to stop.", Outcome.CONFIRMED)
            # Stop the Everywhere group once, not again through its members.
            group_entity = destinations.get("everywhere")
            if group_entity in active:
                members = (players[group_entity].get("attributes") or {}).get("group_members") or []
                for member in members:
                    if member != group_entity:
                        active.pop(member, None)
            failed = []
            for entity in active:
                try:
                    request(connection, "/api/services/media_player/media_stop",
                            {"entity_id": entity})
                    if not wait_for(connection, entity,
                                    lambda player: player.get("state") in STOPPED):
                        failed.append(entity)
                except (OSError, ValueError, HTTPError, TimeoutError):
                    failed.append(entity)
            if failed:
                return ExecutionResult(f"I couldn't verify playback stopped on {len(failed)} "
                        "Music Assistant player(s).", Outcome.PARTIAL)
            return ExecutionResult("Stopped Music Assistant playback Everywhere.", Outcome.CONFIRMED)
        group = destinations.get("everywhere")
        grouped = players.get(group, {})
        members = ((grouped.get("attributes") or {}).get("group_members") or []
                   if grouped.get("state") in ACTIVE else [])
        if room is None and assist:
            areas = read_areas(connection, origin) if origin and read_areas else {}
            room = next((room_key(name) for name in areas if room_key(name) in destinations), None)
            if room and destinations.get(room) is None:
                return ExecutionResult(f"No approved Music Assistant player is configured for {room}.", Outcome.UNRESOLVED)
            if action in {"media_next_track", "media_previous_track"}:
                if room and destinations[room] in members:
                    room = "everywhere"
                elif room and players.get(destinations[room], {}).get("state") not in ACTIVE:
                    return ExecutionResult(f"No active playback in the {room}.", Outcome.UNAVAILABLE)
            elif room is None:
                return ExecutionResult("Which room should I control?", Outcome.UNRESOLVED)
        if room is None:
            active_rooms = [name for name, entity in destinations.items()
                      if (entity == group or entity not in members)
                      and players.get(entity, {}).get("state") in ACTIVE]
            if len(active_rooms) != 1:
                return ExecutionResult("Which room should I control?", Outcome.UNRESOLVED)
            room = active_rooms[0]
        entity = destinations.get(room)
        if entity is None:
            return ExecutionResult(f"No approved Music Assistant player is configured for {room}, or its registration is missing.", Outcome.UNRESOLVED)
        location = "everywhere" if room == "everywhere" else f"in the {room}"
        player = players.get(entity, {})
        state = player.get("state")
        if player_availability_result(entity, state).status is PlayerAvailability.UNAVAILABLE:
            return ExecutionResult(f"The music player {location} is unavailable.", Outcome.UNAVAILABLE)
        if entity != group and entity in members:
            return ExecutionResult("That player is part of Everywhere. Say Everywhere to control the group.", Outcome.UNRESOLVED)
        target_states = {"media_stop": STOPPED, "media_pause": {"paused"}, "media_play": {"playing"}}
        expected = target_states.get(action)
        if expected and state in expected:
            label = {"media_stop": "stopped", "media_pause": "paused", "media_play": "playing"}[action]
            return ExecutionResult(f"Playback is already {label} {location}.", Outcome.CONFIRMED)
        if action != "media_play" and state not in ACTIVE:
            return ExecutionResult(f"There's no active playback {location}.", Outcome.UNAVAILABLE)
        before = player.get("attributes") or {}
        timed_out = False
        deadline = monotonic() + 5
        remaining = deadline - monotonic()
        if remaining <= 0:
            return ExecutionResult(f"I ran out of time checking the player {location}.", Outcome.UNVERIFIED)
        try:
            request(connection, "/api/services/media_player/" + action, {"entity_id": entity},
                    timeout=min(remaining, 2.5))
        except TimeoutError:
            # The command may already be running in Home Assistant.
            timed_out = True

        def verify(current):
            if expected:
                return current.get("state") in expected
            after = current.get("attributes") or {}
            return current.get("state") in {"playing", "paused"} and any(
                after.get(key) and after[key] != before.get(key) for key in ("media_content_id", "media_title")
            )

        attempts = 12 if timed_out else 8 if action == "media_pause" else 4
        if wait_for(connection, entity, verify, attempts=attempts, deadline=deadline):
            result = {"media_stop": "Stopped playback", "media_pause": "Paused playback",
                      "media_play": "Resumed playback", "media_next_track": "Skipped to the next track",
                      "media_previous_track": "Went to the previous track"}[action]
            return ExecutionResult(f"{result} {location}.", Outcome.CONFIRMED)
        if timed_out:
            return ExecutionResult(f"Home Assistant took too long to respond, and I couldn't verify playback {location}.", Outcome.UNVERIFIED)
        return ExecutionResult(f"I sent the playback command {location}, but couldn't verify the result.", Outcome.UNVERIFIED)
    except HTTPError as error:
        error.close()
        failure = MusicRequestFailure.from_http_status(error.code)
        if failure.kind is MusicFailureKind.RATE_LIMITED:
            return ExecutionResult("Music playback is being rate limited. I haven't retried the command.", Outcome.UNVERIFIED)
        if failure.kind is MusicFailureKind.SERVICE_UNAVAILABLE:
            return ExecutionResult("Home Assistant's music service is temporarily unavailable. I couldn't verify playback.", Outcome.UNVERIFIED)
        return ExecutionResult(f"Home Assistant returned an error for the playback command {location}.", Outcome.UNVERIFIED)
    except (OSError, ValueError):
        return ExecutionResult(f"I couldn't verify the playback command {location}.", Outcome.UNVERIFIED)
    finally:
        RUNTIME.handoff.release()


def spotify_id(player):
    content = (player.get("attributes") or {}).get("media_content_id")
    if isinstance(content, str) and re.match(r"^(?:spotify(?:--[^:]+)?(?::|://)|https://open\.spotify\.com/)", content):
        return content
    return None


def media_key(uri):
    match = SPOTIFY_REFERENCE.fullmatch(uri or "")
    if match:
        return f"spotify://{match[1]}/{match[2]}"
    return re.sub(r"^spotify(?:--[^:]+)?://", "spotify://", uri or "")


def saved_spotify_selection(title, artist):
    phrase = f"{title} by {artist}" if artist else title
    try:
        configured = json.loads(os.environ.get("DECLAN_SPOTIFY_PRESETS", "{}"))
    except json.JSONDecodeError:
        configured = {}
    presets = SPOTIFY_PRESETS.copy()
    if isinstance(configured, dict):
        presets.update({" ".join(name.casefold().split()): link for name, link in configured.items()
                        if isinstance(link, str) and SPOTIFY_REFERENCE.fullmatch(link.strip())})
    link = presets.get(phrase)
    if link:
        match = SPOTIFY_REFERENCE.fullmatch(link.strip())
        if match is None:
            return None
        return f"https://open.spotify.com/{match[1]}/{match[2]}", match[1], title
    return None


def search_cache_ttl():
    """Seconds a resolved Spotify search stays valid; 0 disables the cache."""
    raw = os.environ.get("DECLAN_SPOTIFY_SEARCH_CACHE_DAYS", "").strip()
    try:
        days = float(raw) if raw else 7.0
    except ValueError:
        days = 7.0
    return max(0.0, min(days, 365.0)) * 86400


def search_cache_key(title, artist):
    market = os.environ.get("DECLAN_SPOTIFY_MARKET", "GB").strip().upper()
    return "|".join((" ".join(title.casefold().split()), " ".join(artist.casefold().split()), market))


def search_media(connection, destination, title, artist, provider):
    if provider == "spotify":
        with preference_db() as db:
            weights = dict(db.execute("SELECT uri, weight FROM preferences"))
            recent = [uri for (uri,) in db.execute(
                "SELECT uri FROM recent_playlists WHERE category = ? ORDER BY id DESC LIMIT 3", (title,))]
        if title in {"my favourites", "our favourites", "my favorites", "our favorites"}:
            options = [(uri, uri.split("/")[-2], "a favourite") for uri, weight in weights.items() if weight > 1]
            if not options:
                return None
            uri, kind, name = choices(options, weights=[weights[item[0]] for item in options])[0]  # nosec B311 - weighted playlist selection, not security randomness
            return uri.replace("spotify://", "https://open.spotify.com/", 1), kind, name
        # Curated category playlists take precedence over generic Spotify search.
        # The catalogue is owned by Declan 2.0, not the retired HA integration.
        import spotify_playlists
        category = "_".join(title.casefold().replace("-", " ").split())
        if category.endswith("_music"):
            category = category[:-6]
        catalogue = spotify_playlists.listing()["categories"] if not artist else {}
        if not artist and category in catalogue:
            curated = catalogue[category]["playlists"]
            available = [uri for uri in curated if weights.get(media_key(uri), 1) > 0]
            if available:
                for count in range(len(recent), -1, -1):
                    pool = [uri for uri in available if media_key(uri) not in recent[:count]]
                    if pool:
                        selected = choices(pool, weights=[weights.get(media_key(uri), 1) for uri in pool])[0]  # nosec B311 - weighted playlist selection, not security randomness
                        return selected.replace("spotify://", "https://open.spotify.com/", 1), "playlist", title
        types = (("track",) if artist else ("playlist",) if title.endswith(" music")
                 else ("track", "album", "artist", "playlist"))
        # Track/album/artist lookups are deterministic, so remember what they resolved to.
        # Playlist picks are weighted-random and never cached.
        ttl = search_cache_ttl() if types != ("playlist",) else 0
        cache_key = search_cache_key(title, artist)
        if ttl:
            with preference_db() as db:
                row = db.execute("SELECT uri, kind, name, saved FROM search_cache WHERE key = ?", (cache_key,)).fetchone()
                if row and (time() - row[3] > ttl or weights.get(media_key(row[0]), 1) <= 0):
                    db.execute("DELETE FROM search_cache WHERE key = ?", (cache_key,))  # expired or now disliked
                    row = None
            if row:
                return row[0], row[1], row[2]
        options = spotify_search(connection[2], title, artist, types)
        options = [item for item in options if weights.get(media_key(item[0]), 1) > 0]
        if types == ("playlist",) and options:
            for count in range(len(recent), -1, -1):
                pool = [item for item in options if media_key(item[0]) not in recent[:count]]
                if pool:
                    return choices(pool, weights=[weights.get(media_key(item[0]), 1) for item in pool])[0]  # nosec B311 - weighted playlist selection, not security randomness
        chosen = next((item for item in options if item[2].casefold() == title.casefold()),
                      options[0] if options else None)
        if ttl and chosen is not None:
            with preference_db() as db:
                db.execute("INSERT OR REPLACE INTO search_cache(key, uri, kind, name, saved) VALUES (?, ?, ?, ?, ?)",
                           (cache_key, chosen[0], chosen[1], chosen[2], time()))
        return chosen
    entry = request(connection, "/api/template", {
        "template": "{{ config_entry_id(" + json.dumps(destination) + ") or '' }}",
    })
    if not entry:
        return None
    data = {"config_entry_id": entry, "name": title, "media_type": ["radio"], "limit": 5}
    payload = request(connection, "/api/services/music_assistant/search?return_response", data)
    results = payload.get("service_response") or {}
    options = []
    for item in results.get("radio") or []:
        uri = item.get("uri") or ""
        name = item.get("name") or ""
        if provider == "tunein" and not re.match(r"^tunein(?:--[^:]+)?://radio/", uri):
            mapping = next((m for m in item.get("provider_mappings") or []
                            if m.get("provider_domain") == "tunein" and m.get("item_id")
                            and m.get("available", True)), None)
            uri = f"tunein://radio/{mapping['item_id']}" if mapping else ""
        if uri and name:
            options.append((uri, "radio", name))
    return next((item for item in options if item[2].casefold() == title.casefold()),
                options[0] if options else None)


def matches_track(player, title, artist):
    attributes = player.get("attributes") or {}
    return (str(attributes.get("media_title") or "").casefold() == title.casefold()
            and (not artist or str(attributes.get("media_artist") or "").casefold() == artist.casefold()))


POLL_INTERVAL = 0.25


@diagnostics.timed("playback_verification")
def wait_for(connection, player, predicate, *, attempts=4, deadline=None):
    """Poll until predicate passes. `attempts` keeps its meaning as one-second
    steps (the wait window is attempts - 1 seconds); polling is just finer so a
    player that is ready after 200 ms is noticed then, not a second later."""
    polls = (attempts - 1) * round(1 / POLL_INTERVAL) + 1
    for attempt in range(polls):
        if attempt:
            delay = POLL_INTERVAL if deadline is None else min(POLL_INTERVAL, deadline - monotonic())
            if delay <= 0:
                return False
            sleep(delay)
        timeout = 1 if deadline is None else min(1, deadline - monotonic())
        if timeout <= 0:
            return False
        try:
            state = request(connection, "/api/states/" + player, timeout=timeout)
        except TimeoutError:
            continue
        if predicate(state):
            return True
    return False


@diagnostics.timed("music_playback")
def play(command, connection, read_inventory, *, origin=None):
    """Legacy reply/outcome API backed by a validated typed provider result."""
    return music_execution_result(_play_provider(command, connection, read_inventory, origin=origin)).as_legacy_pair()


def _play_provider(command, connection, read_inventory, *, origin=None):
    room, title, provider = command
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    if not RUNTIME.handoff.acquire(blocking=False):
        return ExecutionResult("A music request is already in progress.", Outcome.BUSY)
    stopped = False
    try:
        inventory_result = ha_inventory.InventoryResult.coerce(read_inventory(connection))
        inventory, error = inventory_result.inventory, inventory_result.error
        if error:
            return ExecutionResult("I couldn't check which players are active.", error)
        if room is None:
            areas = {room_key(row["declan_area"]) for row in inventory
                     if origin and (row.get("entity_id") == origin or row.get("declan_device") == origin)
                     and isinstance(row.get("declan_area"), str) and row["declan_area"].strip()}
            if len(areas) != 1:
                return ExecutionResult("Which room should I play the music in?", Outcome.UNRESOLVED)
            room = areas.pop()
        location = "everywhere" if room == "everywhere" else f"in the {room}"
        destinations, players = music_players(inventory, origin=origin) if origin else music_players(inventory)
        explicit = room.startswith('media_player.')
        if explicit:
            # Buttons can choose an exact HA Music Assistant wrapper without
            # pretending to originate from a physical voice satellite.
            if (not re.fullmatch(r'media_player\.[a-z0-9_]+', room)
                    or players.get(room, {}).get('declan_music_assistant') is not True
                    or (approved_media_players.load() is not None and room not in destinations.values())):
                return ExecutionResult("That target is not a registered Music Assistant player. I haven't changed playback.", Outcome.UNRESOLVED)
            destination = room
            label = (players[destination].get('attributes') or {}).get('friendly_name')
            location = 'on ' + (label if isinstance(label, str) and label.strip() else destination)
        else:
            destination = destinations.get(room)
        if destination is None:
            return ExecutionResult(f"No approved Music Assistant player is configured for {room}, or its registration is missing.", Outcome.UNRESOLVED)
        if player_availability_result(destination, players.get(destination, {}).get("state")).status is PlayerAvailability.UNAVAILABLE:
            return ExecutionResult(f"The Music Assistant player {location} is unavailable.", Outcome.UNAVAILABLE)
        previous_state = players[destination]["state"]
        previous_track = (players[destination].get("attributes") or {}).get("media_content_id")
        streams = {entity: player for entity, player in players.items()
                   if player.get("state") in ACTIVE and spotify_id(player)}
        group = destinations.get("everywhere")
        if group in streams:
            members = streams[group]["attributes"].get("group_members") or []
            for entity in tuple(streams):
                if entity != group and entity in members and spotify_id(streams[entity]) == spotify_id(streams[group]):
                    del streams[entity]
        if len(streams) > 1:
            return ExecutionResult("I found more than one active Spotify queue and couldn't tell which one to move.", Outcome.UNVERIFIED)
        source = next(iter(streams), None)
        artist = ""
        if title and provider == "spotify" and " by " in title:
            title, _, artist = title.rpartition(" by ")
        saved = saved_spotify_selection(title, artist) if title and provider == "spotify" else None
        if saved and PREFERENCES.exists():
            with preference_db() as db:
                if db.execute("SELECT 1 FROM preferences WHERE uri = ? AND weight = 0",
                              (media_key(saved[0]),)).fetchone():
                    return ExecutionResult("That track is on your do-not-play list.", Outcome.UNAVAILABLE)
        same_track = source and (
            media_key(spotify_id(streams[source])) == media_key(saved[0]) if saved
            else title and matches_track(streams[source], title, artist)
        )
        move = provider == "spotify" and (title is None or same_track)
        if provider != "spotify" and title is None:
            return ExecutionResult("Tell me which radio station to play.", Outcome.UNAVAILABLE)
        if title is None and source is None:
            return ExecutionResult("I couldn't find an active Spotify queue. Tell me what to play.", Outcome.UNAVAILABLE)
        if move and source == destination and streams[source]["state"] == "playing":
            return ExecutionResult(f"Spotify is already playing {location}.", Outcome.CONFIRMED)
        if move:
            if source == destination:
                path = "/api/services/media_player/media_play"
                data = {"entity_id": destination}
            else:
                path = "/api/services/music_assistant/transfer_queue"
                data = {"entity_id": destination, "source_player": source, "auto_play": True}
        else:
            try:
                selection = saved or search_media(connection, destination, title, artist, provider)
            except SpotifyNotConfigured:
                selection = SPOTIFY_PLAYLIST_FALLBACKS.get(title) if not artist else None
                if selection is None:
                    return ExecutionResult("Spotify search isn't configured. Saved Spotify links can still play.", Outcome.NOT_CONFIGURED)
                if PREFERENCES.exists():
                    with preference_db() as db:
                        if db.execute("SELECT 1 FROM preferences WHERE uri = ? AND weight = 0",
                                      (media_key(selection[0]),)).fetchone():
                            return ExecutionResult("The saved playlist is on your do-not-play list.", Outcome.UNAVAILABLE)
            except HTTPError as search_error:
                if provider != "spotify":
                    raise
                search_error.close()
                detail = ("Spotify search is being rate limited." if search_error.code == 429
                          else f"Spotify search returned HTTP {search_error.code}.")
                return ExecutionResult(f"{detail} I haven't changed playback.", Outcome.UNVERIFIED)
            except TimeoutError:
                return ExecutionResult("The search took too long. I haven't changed playback.", Outcome.UNVERIFIED)
            if selection is None:
                source_name = {"spotify": "Spotify", "radio": "radio", "tunein": "TuneIn"}[provider]
                return ExecutionResult(f"I couldn't find {title} on {source_name}.", Outcome.UNAVAILABLE)
            uri, kind, selected_name = selection
            if provider == "spotify" and PREFERENCES.exists():
                with preference_db() as db:
                    if db.execute("SELECT 1 FROM preferences WHERE uri = ? AND weight = 0", (media_key(uri),)).fetchone():
                        return ExecutionResult("That Spotify item is on your disliked list. I won't play it.", Outcome.UNAVAILABLE)
            if provider == "spotify" and source:
                request(connection, "/api/services/media_player/media_stop", {"entity_id": source})
                if not wait_for(connection, source, lambda player: player.get("state") in STOPPED):
                    return ExecutionResult("I couldn't confirm Spotify stopped on the previous player. I didn't start another stream.", Outcome.UNVERIFIED)
                stopped = True
                if source == destination:
                    previous_state = "idle"
            data = {"entity_id": destination, "media_id": uri, "media_type": kind, "enqueue": "play"}
            path = "/api/services/music_assistant/play_media"
        timed_out = False
        try:
            request(connection, path, data)
        except TimeoutError:
            # Home Assistant can finish the command after our request times out.
            timed_out = True

        observed_playback = False

        def verify(player):
            nonlocal observed_playback
            attributes = player.get("attributes") or {}
            track = spotify_id(player) if provider == "spotify" else attributes.get("media_content_id")
            if player.get("state") != "playing" or not track:
                return False
            if provider != "spotify" and spotify_id(player):
                return False
            if previous_state != "playing" or track != previous_track:
                observed_playback = True
            if move:
                return media_key(track) == media_key(spotify_id(streams[source]))
            if media_key(track) == media_key(uri):
                return True
            if kind == "artist":
                reported_artist = attributes.get("media_artist") or ""
                return observed_playback and reported_artist.casefold() == selected_name.casefold()
            return not saved and kind == "track" and matches_track(player, selected_name, artist)

        playback_source = "Spotify" if provider == "spotify" else "Radio"

        def record_playlist_play():
            if not move and kind == "playlist" and provider == "spotify":
                with preference_db() as db:
                    db.execute("INSERT INTO playlist_play_counts(uri, plays) VALUES (?, 1) ON CONFLICT(uri) DO UPDATE SET plays = plays + 1", (media_key(uri),))
                    db.execute("INSERT INTO recent_playlists(category, uri) VALUES (?, ?)", (title, media_key(uri)))
                    db.execute("DELETE FROM recent_playlists WHERE id <= "
                               "(SELECT max(id) - 500 FROM recent_playlists)")

        if reply_first_enabled() and not timed_out:
            # Home Assistant accepted the request. Answer now and verify later;
            # the outcome is "requested", never "confirmed", until observed.
            _verify_in_background(
                connection, destination, verify, attempts=10, location=location,
                satellite=_satellite_for(inventory, origin),
                observed=lambda: observed_playback, on_playing=record_playlist_play)
            subject = playback_source if move else selected_name
            prefix = "I stopped the previous Spotify stream. " if stopped else ""
            return ExecutionResult(f"{prefix}Starting {subject} {location}.", Outcome.REQUESTED)
        # Music Assistant may still be retrying Spotify or expanding a playlist
        # after the playback POST times out. Only poll state, never resend it.
        verified = wait_for(connection, destination, verify, attempts=12 if timed_out else 4)
        if verified or observed_playback:
            record_playlist_play()
        if verified:
            if not move and kind == "artist":
                prefix = "I stopped the previous Spotify stream. " if stopped else ""
                return ExecutionResult(f"{prefix}{selected_name} is playing {location}.", Outcome.CONFIRMED)
            if stopped:
                return ExecutionResult(f"I stopped the previous Spotify stream and started {title} {location}.", Outcome.CONFIRMED)
            return ExecutionResult(f"{playback_source} is playing {location}.", Outcome.CONFIRMED)
        prefix = "I stopped the previous Spotify stream. " if stopped else ""
        if observed_playback:
            return ExecutionResult(f"{prefix}{playback_source} started playing {location}, but I couldn't verify the requested selection.", Outcome.PARTIAL)
        if timed_out:
            return ExecutionResult(f"{prefix}Home Assistant took too long to respond, and I couldn't verify playback {location}.", Outcome.UNVERIFIED)
        return ExecutionResult(f"{prefix}I sent the music request {location}, but couldn't verify playback.", Outcome.UNVERIFIED)
    except HTTPError as error:
        error.close()
        failure = MusicRequestFailure.from_http_status(error.code)
        if failure.kind is MusicFailureKind.RATE_LIMITED:
            detail = "Music playback is being rate limited. I haven't retried the request."
        elif failure.kind is MusicFailureKind.SERVICE_UNAVAILABLE:
            detail = "Home Assistant's music service is temporarily unavailable. I couldn't verify playback."
        else:
            detail = "Home Assistant returned an error for the music request."
        return ExecutionResult(("I stopped the previous stream. " if stopped else "") + detail, Outcome.UNVERIFIED)
    except (OSError, ValueError, sqlite3.Error):
        return ExecutionResult("I stopped the previous Spotify stream, but couldn't verify the new request." if stopped
                else "I couldn't verify the music request.", Outcome.UNVERIFIED)
    finally:
        RUNTIME.handoff.release()



def feedback_result(command, connection, read_inventory):
    """Typed music preference result; legacy feedback() remains supported."""
    return music_execution_result(_feedback_provider(command, connection, read_inventory))


def control_result(command, connection, read_inventory, *, origin=None,
                   read_areas=None, assist=False):
    """Typed Music Assistant control result with existing locking semantics."""
    return music_execution_result(_control_provider(
        command, connection, read_inventory, origin=origin,
        read_areas=read_areas, assist=assist,
    ))


def play_result(command, connection, read_inventory, *, origin=None):
    """Typed Music Assistant playback result; preserve legacy call behaviour."""
    return music_execution_result(_play_provider(
        command, connection, read_inventory, origin=origin,
    ))
