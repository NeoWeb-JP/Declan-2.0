"""Route one household Spotify stream through Music Assistant."""

import json
import diagnostics
import approved_media_players
import os
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from random import choices
from tempfile import NamedTemporaryFile
from threading import Lock
from time import monotonic, sleep
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
HANDOFF = Lock()
SPOTIFY_TOKEN_LOCK = Lock()
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
spotify_token = None
SPOTIFY_SETTINGS = Path(__file__).with_name(".data") / "spotify-settings.json"
PREFERENCES = SPOTIFY_SETTINGS.with_name("music-preferences.sqlite3")
recent_blacklist_skips = {}


def room_key(name):
    return " ".join(name.casefold().split()).removeprefix("master ")


def music_players(inventory, *, origin=None):
    approved = approved_media_players.resolve(inventory)
    if approved is not None:
        entities = {row.get("entity_id"): row for row in inventory if isinstance(row, dict)}
        return approved, {entity: entities[entity] for entity in approved.values() if entity in entities}
    destinations = PLAYERS.copy()
    entities = {row["entity_id"]: row for row in inventory
                if isinstance(row, dict) and isinstance(row.get("entity_id"), str)}
    if entities.get(destinations["everywhere"], {}).get("state") in (None, "unknown", "unavailable"):
        candidates = [entity for entity, row in entities.items()
                      if re.fullmatch(r"media_player\.[a-z0-9_]+", entity)
                      and row.get("state") not in (None, "unknown", "unavailable")
                      and str((row.get("attributes") or {}).get("friendly_name", "")).strip().casefold() == "everywhere"]
        if len(candidates) == 1:
            destinations["everywhere"] = candidates[0]
    registered = any("declan_music_assistant" in row for row in entities.values())
    if registered:
        # Resolve Music Assistant wrappers from HA areas, including inherited device areas.
        destinations = {"everywhere": destinations["everywhere"]}
        rooms = {}
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
    return destinations, {entity: entities[entity] for entity in destinations.values() if entity in entities}


@contextmanager
def preference_db():
    PREFERENCES.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(PREFERENCES, timeout=1)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS preferences (uri TEXT PRIMARY KEY, weight INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS recent_playlists (id INTEGER PRIMARY KEY, category TEXT, uri TEXT)")
        yield db


def parse_feedback(phrase):
    match = re.fullmatch(
        r"(never play this song again|i like this song|we like this song|i like this playlist|we like this playlist)"
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
    phrase, room = command
    if connection is None or not HANDOFF.acquire(blocking=False):
        return "I couldn't check the current music. Try again in a moment.", "unavailable"
    try:
        inventory, error = read_inventory(connection)
        if error:
            return "I couldn't check what's playing.", error
        destinations, players = music_players(inventory)
        active = playback_sources(destinations, players)
        if room:
            entity = destinations.get(room_key(room))
            active = {entity: active[entity]} if entity in active else {}
        if len(active) != 1:
            return "Tell me which active music player you mean.", "unresolved"
        entity, player = next(iter(active.items()))
        attrs = player.get("attributes") or {}
        playlist = phrase.endswith("playlist")
        kind = "playlist" if playlist else "track"
        uri = next((media_key(value) for value in (attrs.get("media_playlist_id"), attrs.get("media_content_id"))
                    if isinstance(value, str) and media_key(value).startswith(f"spotify://{kind}/")
                    and SPOTIFY_REFERENCE.fullmatch(value)), None)
        if not uri:
            return f"I couldn't identify the current Spotify {kind}.", "unresolved"
        ban = phrase.startswith("never")
        with preference_db() as db:
            if not ban and db.execute("SELECT 1 FROM preferences WHERE uri = ? AND weight = 0", (uri,)).fetchone():
                return "That song is on your do-not-play list.", "unresolved"
            db.execute("INSERT INTO preferences VALUES (?, ?) ON CONFLICT(uri) DO UPDATE SET weight = "
                       "CASE WHEN excluded.weight = 0 THEN 0 ELSE min(5, max(1, weight) + 1) END",
                       (uri, 0 if ban else 2))
        label = (attrs.get("media_playlist") or "this playlist") if playlist else (attrs.get("media_title") or "this song")
        return (f"Blocked {label}. I'll skip it when it comes up." if ban else f"Saved {label} as a favourite."), "music_feedback"
    except (OSError, ValueError, sqlite3.Error):
        return "I couldn't save that music preference.", "unavailable"
    finally:
        HANDOFF.release()


def skip_blocked_tracks(connection, read_inventory):
    if connection is None or not PREFERENCES.exists() or not HANDOFF.acquire(blocking=False):
        return
    try:
        with preference_db() as db:
            blocked = {uri for (uri,) in db.execute("SELECT uri FROM preferences WHERE weight = 0")}
        if not blocked:
            return
        inventory, error = read_inventory(connection)
        if error:
            return
        now = monotonic()
        for entity, player in playback_sources(*music_players(inventory)).items():
            track = media_key(spotify_id(player))
            if player.get("state") == "playing" and track in blocked and now >= recent_blacklist_skips.get(entity, 0):
                recent_blacklist_skips[entity] = now + 10
                request(connection, "/api/services/media_player/media_next_track", {"entity_id": entity}, timeout=2)
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, sqlite3.Error):
        pass
    finally:
        HANDOFF.release()


class SpotifyNotConfigured(Exception):
    """Spotify search needs its own application credentials."""


def spotify_credentials():
    try:
        saved = json.loads(SPOTIFY_SETTINGS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        credentials = tuple(os.environ.get(key, "").strip()
                            for key in ("DECLAN_SPOTIFY_CLIENT_ID", "DECLAN_SPOTIFY_CLIENT_SECRET"))
        return credentials, "environment" if all(credentials) else "unconfigured"
    if not isinstance(saved, dict):
        raise ValueError("Invalid Spotify settings")
    credentials = (saved.get("client_id"), saved.get("client_secret"))
    if not all(isinstance(value, str) and value for value in credentials):
        raise ValueError("Invalid Spotify settings")
    return credentials, "saved"


def save_spotify_credentials(client_id, client_secret):
    with SPOTIFY_TOKEN_LOCK:
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
    global spotify_token
    with SPOTIFY_TOKEN_LOCK:
        credentials, _ = spotify_credentials()
        if not all(credentials):
            raise SpotifyNotConfigured
        now = monotonic()
        if spotify_token is None or spotify_token[0] != credentials or spotify_token[2] <= now:
            data = urlencode(dict(zip(("client_id", "client_secret"), credentials))
                             | {"grant_type": "client_credentials"}).encode()
            token_request = Request("https://accounts.spotify.com/api/token", data=data,
                                    headers={"Content-Type": "application/x-www-form-urlencoded"})
            with opener.open(token_request, timeout=4) as response:
                token = json.load(response)
            access_token = token.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("Spotify did not return an access token")
            spotify_token = (credentials, access_token, now + max(0, int(token.get("expires_in", 0)) - 30))
        access_token = spotify_token[1]
    def quoted(value):
        return value.replace('\\', '\\\\').replace('"', '\\"')
    query = f'track:"{quoted(title)}" artist:"{quoted(artist)}"' if artist else quoted(title)
    market = os.environ.get("DECLAN_SPOTIFY_MARKET", "GB").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", market):
        raise ValueError("DECLAN_SPOTIFY_MARKET must be a two-letter country code")
    params = urlencode({"q": query, "type": ",".join(types), "market": market, "limit": 5})
    search_request = Request("https://api.spotify.com/v1/search?" + params,
                             headers={"Authorization": f"Bearer {access_token}"})
    try:
        with opener.open(search_request, timeout=8) as response:
            results = json.load(response)
    except HTTPError as error:
        if error.code == 401:
            with SPOTIFY_TOKEN_LOCK:
                if spotify_token is not None and spotify_token[1] == access_token:
                    spotify_token = None
        raise
    return [(f"https://open.spotify.com/{kind}/{item['id']}", kind, item["name"])
            for kind in types for item in (results.get(f"{kind}s", {}).get("items") or [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
            and re.fullmatch(r"[A-Za-z0-9]{22}", str(item.get("id", "")))]


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


def request(connection, path, data=None, *, timeout=None):
    label = ('stop_dispatch' if path.endswith('/media_stop') else
             'play_dispatch' if path.endswith('/play_media') else 'ha_media_request')
    with diagnostics.stage(label):
        return _request(connection, path, data, timeout=timeout)


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
    action, room = command
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured"
    if not HANDOFF.acquire(blocking=False):
        return "A music request is already in progress.", "busy"
    location = "on the music player"
    try:
        inventory, error = read_inventory(connection)
        if error == "unavailable":
            inventory, error = read_inventory(connection)
        if error:
            return "I couldn't check the music players.", error
        destinations, players = music_players(inventory)
        group = destinations.get("everywhere")
        grouped = players.get(group, {})
        members = ((grouped.get("attributes") or {}).get("group_members") or []
                   if grouped.get("state") in ACTIVE else [])
        if room is None and assist:
            areas = read_areas(connection, origin) if origin and read_areas else {}
            room = next((room_key(name) for name in areas if room_key(name) in destinations), None)
            if room and destinations.get(room) is None:
                return f"No approved Music Assistant player is configured for {room}.", "unresolved"
            if action in {"media_next_track", "media_previous_track"}:
                if room and destinations[room] in members:
                    room = "everywhere"
                elif room and players.get(destinations[room], {}).get("state") not in ACTIVE:
                    return f"No active playback in the {room}.", "unavailable"
            elif room is None:
                return "Which room should I control?", "unresolved"
        if room is None:
            active = [name for name, entity in destinations.items()
                      if (entity == group or entity not in members)
                      and players.get(entity, {}).get("state") in ACTIVE]
            if len(active) != 1:
                return "Which room should I control?", "unresolved"
            room = active[0]
        entity = destinations.get(room)
        if entity is None:
            return f"No approved Music Assistant player is configured for {room}, or its registration is missing.", "unresolved"
        location = "everywhere" if room == "everywhere" else f"in the {room}"
        player = players.get(entity, {})
        state = player.get("state")
        if state in (None, "unavailable", "unknown"):
            return f"The music player {location} is unavailable.", "unavailable"
        if entity != group and entity in members:
            return "That player is part of Everywhere. Say Everywhere to control the group.", "unresolved"
        target_states = {"media_stop": STOPPED, "media_pause": {"paused"}, "media_play": {"playing"}}
        expected = target_states.get(action)
        if expected and state in expected:
            label = {"media_stop": "stopped", "media_pause": "paused", "media_play": "playing"}[action]
            return f"Playback is already {label} {location}.", "confirmed"
        if action != "media_play" and state not in ACTIVE:
            return f"There's no active playback {location}.", "unavailable"
        before = player.get("attributes") or {}
        timed_out = False
        deadline = monotonic() + 5
        remaining = deadline - monotonic()
        if remaining <= 0:
            return f"I ran out of time checking the player {location}.", "unverified"
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
            return f"{result} {location}.", "confirmed"
        if timed_out:
            return f"Home Assistant took too long to respond, and I couldn't verify playback {location}.", "unverified"
        return f"I sent the playback command {location}, but couldn't verify the result.", "unverified"
    except HTTPError as error:
        error.close()
        return f"Home Assistant returned an error for the playback command {location}.", "unverified"
    except (OSError, ValueError):
        return f"I couldn't verify the playback command {location}.", "unverified"
    finally:
        HANDOFF.release()


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
        return f"https://open.spotify.com/{match[1]}/{match[2]}", match[1], title
    return None


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
            uri, kind, name = choices(options, weights=[weights[item[0]] for item in options])[0]
            return uri.replace("spotify://", "https://open.spotify.com/", 1), kind, name
        types = (("track",) if artist else ("playlist",) if title.endswith(" music")
                 else ("track", "album", "artist", "playlist"))
        options = spotify_search(connection[2], title, artist, types)
        options = [item for item in options if weights.get(media_key(item[0]), 1) > 0]
        if types == ("playlist",) and options:
            for count in range(len(recent), -1, -1):
                pool = [item for item in options if media_key(item[0]) not in recent[:count]]
                if pool:
                    return choices(pool, weights=[weights.get(media_key(item[0]), 1) for item in pool])[0]
        return next((item for item in options if item[2].casefold() == title.casefold()),
                    options[0] if options else None)
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


@diagnostics.timed("playback_verification")
def wait_for(connection, player, predicate, *, attempts=4, deadline=None):
    for attempt in range(attempts):
        if attempt:
            delay = 1 if deadline is None else min(1, deadline - monotonic())
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
    room, title, provider = command
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured"
    if not HANDOFF.acquire(blocking=False):
        return "A music request is already in progress.", "busy"
    stopped = False
    try:
        inventory, error = read_inventory(connection)
        if error:
            return "I couldn't check which players are active.", error
        if room is None:
            areas = {room_key(row["declan_area"]) for row in inventory
                     if origin and (row.get("entity_id") == origin or row.get("declan_device") == origin)
                     and isinstance(row.get("declan_area"), str) and row["declan_area"].strip()}
            if len(areas) != 1:
                return "Which room should I play the music in?", "unresolved"
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
                return "That target is not a registered Music Assistant player. I haven't changed playback.", "unresolved"
            destination = room
            label = (players[destination].get('attributes') or {}).get('friendly_name')
            location = 'on ' + (label if isinstance(label, str) and label.strip() else destination)
        else:
            destination = destinations.get(room)
        if destination is None:
            return f"No approved Music Assistant player is configured for {room}, or its registration is missing.", "unresolved"
        if players.get(destination, {}).get("state") in (None, "unknown", "unavailable"):
            return f"The Music Assistant player {location} is unavailable.", "unavailable"
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
            return "I found more than one active Spotify queue and couldn't tell which one to move.", "unverified"
        source = next(iter(streams), None)
        artist = ""
        if title and provider == "spotify" and " by " in title:
            title, _, artist = title.rpartition(" by ")
        saved = saved_spotify_selection(title, artist) if title and provider == "spotify" else None
        if saved and PREFERENCES.exists():
            with preference_db() as db:
                if db.execute("SELECT 1 FROM preferences WHERE uri = ? AND weight = 0",
                              (media_key(saved[0]),)).fetchone():
                    return "That track is on your do-not-play list.", "unavailable"
        same_track = source and (
            media_key(spotify_id(streams[source])) == media_key(saved[0]) if saved
            else title and matches_track(streams[source], title, artist)
        )
        move = provider == "spotify" and (title is None or same_track)
        if provider != "spotify" and title is None:
            return "Tell me which radio station to play.", "unavailable"
        if title is None and source is None:
            return "I couldn't find an active Spotify queue. Tell me what to play.", "unavailable"
        if move and source == destination and streams[source]["state"] == "playing":
            return f"Spotify is already playing {location}.", "confirmed"
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
                    return "Spotify search isn't configured. Saved Spotify links can still play.", "not_configured"
                if PREFERENCES.exists():
                    with preference_db() as db:
                        if db.execute("SELECT 1 FROM preferences WHERE uri = ? AND weight = 0",
                                      (media_key(selection[0]),)).fetchone():
                            return "The saved playlist is on your do-not-play list.", "unavailable"
            except HTTPError as error:
                if provider != "spotify":
                    raise
                error.close()
                detail = ("Spotify search is being rate limited." if error.code == 429
                          else f"Spotify search returned HTTP {error.code}.")
                return f"{detail} I haven't changed playback.", "unverified"
            except TimeoutError:
                return "The search took too long. I haven't changed playback.", "unverified"
            if selection is None:
                source_name = {"spotify": "Spotify", "radio": "radio", "tunein": "TuneIn"}[provider]
                return f"I couldn't find {title} on {source_name}.", "unavailable"
            uri, kind, selected_name = selection
            if provider == "spotify" and source:
                request(connection, "/api/services/media_player/media_stop", {"entity_id": source})
                if not wait_for(connection, source, lambda player: player.get("state") in STOPPED):
                    return "I couldn't confirm Spotify stopped on the previous player. I didn't start another stream.", "unverified"
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
        # Music Assistant may still be retrying Spotify or expanding a playlist
        # after the playback POST times out. Only poll state, never resend it.
        verified = wait_for(connection, destination, verify, attempts=12 if timed_out else 4)
        if not move and kind == "playlist" and provider == "spotify" and (verified or observed_playback):
            with preference_db() as db:
                db.execute("INSERT INTO recent_playlists(category, uri) VALUES (?, ?)", (title, media_key(uri)))
                db.execute("DELETE FROM recent_playlists WHERE id <= "
                           "(SELECT max(id) - 500 FROM recent_playlists)")
        if verified:
            if not move and kind == "artist":
                prefix = "I stopped the previous Spotify stream. " if stopped else ""
                return f"{prefix}{selected_name} is playing {location}.", "confirmed"
            if stopped:
                return f"I stopped the previous Spotify stream and started {title} {location}.", "confirmed"
            return f"{playback_source} is playing {location}.", "confirmed"
        prefix = "I stopped the previous Spotify stream. " if stopped else ""
        if observed_playback:
            return (f"{prefix}{playback_source} started playing {location}, but I couldn't verify the requested selection.",
                    "partial")
        if timed_out:
            return f"{prefix}Home Assistant took too long to respond, and I couldn't verify playback {location}.", "unverified"
        return f"{prefix}I sent the music request {location}, but couldn't verify playback.", "unverified"
    except HTTPError as error:
        error.close()
        if error.code == 429:
            detail = "Music playback is being rate limited. I haven't retried the request."
        else:
            detail = "Home Assistant returned an error for the music request."
        return ("I stopped the previous stream. " if stopped else "") + detail, "unverified"
    except (OSError, ValueError, sqlite3.Error):
        return ("I stopped the previous Spotify stream, but couldn't verify the new request." if stopped
                else "I couldn't verify the music request."), "unverified"
    finally:
        HANDOFF.release()

