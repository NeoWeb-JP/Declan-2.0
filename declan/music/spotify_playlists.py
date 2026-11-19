"""Declan 2.0 owned Spotify playlist discovery and category curation."""
import json
import os
import re
import logging
from urllib.error import HTTPError
from pathlib import Path
from threading import Thread
from declan.music.playlist_refresh_state import PlaylistRefreshState

CATEGORIES = ("country", "braai", "romantic", "sexy_time", "rock", "afrikaans",
              "80s", "90s", "work_focus", "adhd_focus", "massage")
CAPACITY = 25
URI = re.compile(r"(?:spotify(?::|://)playlist[:/]|https://open\.spotify\.com/playlist/)([A-Za-z0-9]{22})(?:\?[^#]*)?\Z")
RUNTIME = PlaylistRefreshState()
LOGGER = logging.getLogger(__name__)
DEFAULT_PATH = Path(__file__).resolve().parents[2] / ".data" / "spotify-playlists.json"


def canonical(value):
    match = URI.fullmatch(value.strip()) if isinstance(value, str) else None
    return "spotify://playlist/" + match.group(1) if match else None


def unique(values):
    return list(dict.fromkeys(x for value in values if (x := canonical(value))))


def catalogue_path():
    return Path(os.environ.get("DECLAN_SPOTIFY_PLAYLISTS_FILE") or DEFAULT_PATH)


def category_names(raw):
    """Built-in genres plus persisted user-created genres."""
    custom = (key for key in raw if isinstance(key, str)
              and re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key))
    return tuple(dict.fromkeys((*CATEGORIES, *custom)))


def add_genre(name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise ValueError("Enter a genre name (up to 40 characters)")
    slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", slug):
        raise ValueError("Genre must contain letters or numbers")
    with RUNTIME.lock:
        data = load()
        if slug in data:
            raise ValueError("Genre already exists")
        if len(data) >= 50:
            raise ValueError("Maximum 50 genres")
        data[slug] = {"manual": [], "favourites": [], "excluded": [],
                      "discovered": [], "playlists": [], "titles": {}}
        save(data)
    return listing()


def normalize(raw):
    """Keep user-added and liked playlists independently of discovery results.

    A dislike is retained in the global preference database and excluded from
    playback, not erased from the catalogue. Only discovery-owned entries
    rotate during refresh.
    """
    from declan.music import music
    with music.preference_db() as db:
        preferences = dict(db.execute(
            "SELECT uri, weight FROM preferences WHERE uri LIKE 'spotify://playlist/%'"
        ))
    disliked = {uri for uri, weight in preferences.items() if weight == 0}
    liked = {uri for uri, weight in preferences.items() if weight > 1}
    result = {}
    for category in category_names(raw):
        item = raw.get(category, {}) if isinstance(raw, dict) else {}
        item = item if isinstance(item, dict) else {}
        manual = unique(item.get("manual") or [])
        pinned = unique(item.get("favourites") or [])
        excluded = unique(item.get("excluded") or [])
        # Legacy catalogues used favourites for manual additions. Only
        # migrate them when the new manual field is absent; otherwise liking
        # a discovered playlist must not silently convert it to manual.
        if "manual" not in item:
            manual = list(dict.fromkeys(manual + pinned))
        discovered = unique(item.get("discovered") or [])
        protected = list(dict.fromkeys(manual + [uri for uri in discovered if uri in liked]))
        if len(protected) > CAPACITY:
            # Never silently discard protected entries to make room.
            # Older oversized catalogues remain visible for manual resolution.
            LOGGER.warning("Spotify category %s exceeds %d protected playlists", category, CAPACITY)
        excluded = list(dict.fromkeys(excluded + sorted(disliked)))
        visible_protected = [uri for uri in protected if uri not in excluded]
        available = max(0, CAPACITY - len(visible_protected))
        rotating = [uri for uri in discovered if uri not in protected and uri not in excluded][:available]
        active = visible_protected + rotating
        titles = item.get("titles")
        if not isinstance(titles, dict):
            titles = {}
        titles = {uri: name[:160] for uri, name in titles.items()
                  if isinstance(uri, str) and isinstance(name, str)
                  and uri in active + excluded + protected}
        result[category] = {"manual": manual, "favourites": pinned,
                            "excluded": excluded, "discovered": discovered,
                            "playlists": active, "titles": titles}
    return result


def load():
    try:
        raw = json.loads(catalogue_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Invalid Spotify playlist catalogue")
    return normalize(raw)


def save(data):
    path = catalogue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def manage(body):
    if isinstance(body, dict) and set(body) == {"operation", "genre"} and body["operation"] == "add_genre":
        return add_genre(body["genre"])
    if not isinstance(body, dict) or set(body) != {"category", "playlist", "operation"}:
        raise ValueError("Invalid playlist change")
    category, operation = body["category"], body["operation"]
    if category in {"disliked_songs", "disliked_playlists"} and operation == "restore":
        from declan.music import music
        value = body["playlist"]
        kind = "track" if category == "disliked_songs" else "playlist"
        if not isinstance(value, str) or not re.fullmatch(r"spotify://" + kind + r"/[A-Za-z0-9]{22}", value):
            raise ValueError("Invalid disliked item")
        with music.preference_db() as db:
            db.execute("DELETE FROM preferences WHERE uri = ? AND weight = 0", (value,))
        if kind == "playlist":
            with RUNTIME.lock:
                data = load()
                for item in data.values():
                    item["excluded"] = [uri for uri in item["excluded"] if uri != value]
                save(data)
        return listing()
    selected = canonical(body["playlist"])
    if category not in load() or operation not in ("add", "remove", "delete", "favourite", "unfavourite", "dislike", "restore") or not selected:
        raise ValueError("Invalid playlist change")
    with RUNTIME.lock:
        data = load()
        item = data[category]
        if operation in {"favourite", "unfavourite", "dislike", "restore"}:
            from declan.music import music
            with music.preference_db() as db:
                if operation == "dislike":
                    db.execute("INSERT INTO preferences(uri, weight) VALUES (?, 0) ON CONFLICT(uri) DO UPDATE SET weight = 0", (selected,))
                elif operation == "restore":
                    db.execute("DELETE FROM preferences WHERE uri = ? AND weight = 0", (selected,))
                elif operation == "favourite":
                    if db.execute("SELECT weight FROM preferences WHERE uri = ?", (selected,)).fetchone() == (0,):
                        raise ValueError("Restore disliked playlist before favouriting")
                    db.execute("INSERT INTO preferences(uri, weight) VALUES (?, 3) ON CONFLICT(uri) DO UPDATE SET weight = max(3, weight)", (selected,))
                else:
                    db.execute("UPDATE preferences SET weight = 1 WHERE uri = ? AND weight > 0", (selected,))
            if operation == "dislike":
                item["excluded"].append(selected)
            elif operation == "restore":
                # A global dislike was propagated into every genre during
                # normalization. Restoring must remove those exclusions from
                # every category, not only the category where it was clicked.
                for category_item in data.values():
                    category_item["excluded"] = [
                        uri for uri in category_item["excluded"] if uri != selected
                    ]
            elif operation == "favourite":
                if selected not in item["playlists"] and len(item["playlists"]) >= CAPACITY:
                    raise ValueError("Category has 25 playlists; remove one first")
                # A liked discovered playlist is protected by its preference,
                # not reclassified as a manually added playlist.
                if selected not in item["discovered"] and selected not in item["manual"]:
                    item["manual"].append(selected)
                if selected not in item["favourites"]:
                    item["favourites"].append(selected)
            elif operation == "unfavourite" and selected in item["favourites"]:
                item["favourites"] = [uri for uri in item["favourites"] if uri != selected]
                if selected not in item["manual"] and selected not in item["discovered"]:
                    item["discovered"].append(selected)
            data = normalize(data)
            save(data)
            return {"categories": data, "max_playlists": CAPACITY}
        for key in ("manual", "favourites", "discovered", "excluded"):
            item[key] = [x for x in item[key] if x != selected]
        if operation == "add":
            if selected in data[category]["playlists"]:
                return {"categories": data, "max_playlists": CAPACITY}
            if len(data[category]["playlists"]) >= CAPACITY:
                raise ValueError("Category has 25 playlists; remove one first")
            item["manual"].append(selected)
            item["favourites"].append(selected)
        elif operation == "delete":
            item["excluded"].append(selected)
        data = normalize(data)
        save(data)
        return {"categories": data, "max_playlists": CAPACITY}


def listing():
    with RUNTIME.lock:
        from declan.music import music
        with music.preference_db() as db:
            weights = dict(db.execute("SELECT uri, weight FROM preferences WHERE uri LIKE 'spotify://playlist/%'"))
            plays = dict(db.execute("SELECT uri, plays FROM playlist_play_counts"))
            disliked_songs = [uri for uri, weight in db.execute(
                "SELECT uri, weight FROM preferences WHERE uri LIKE 'spotify://track/%'") if weight == 0]
        return {"categories": load(), "max_playlists": CAPACITY, "refresh": RUNTIME.snapshot(),
                "preferences": {"favourites": [uri for uri, weight in weights.items() if weight > 1],
                                "disliked_playlists": [uri for uri, weight in weights.items() if weight == 0],
                                "disliked_songs": disliked_songs,
                                "play_counts": plays}}


def refresh(discovered, titles=None):
    """Merge Spotify search results without losing manual pins or exclusions."""
    with RUNTIME.lock:
        data = load()
        for category in data:
            if category in discovered:
                # Preserve liked discovery entries, even when Spotify search
                # no longer returns them. Dislikes stay excluded globally.
                from declan.music import music
                with music.preference_db() as db:
                    liked = {uri for uri, weight in db.execute(
                        "SELECT uri, weight FROM preferences WHERE uri LIKE 'spotify://playlist/%'"
                    ) if weight > 1}
                previous = data[category]["discovered"]
                data[category]["discovered"] = unique(discovered[category]) + [
                    uri for uri in previous if uri in liked and uri not in discovered[category]
                ]
                if titles and category in titles:
                    data[category]["titles"].update(titles[category])
        data = normalize(data)
        save(data)
        return data

QUERIES = {
    "country": ("country music", "modern country"),
    "braai": ("braai music", "south african braai"),
    "romantic": ("romantic songs", "love songs"),
    "sexy_time": ("romantic evening", "slow romantic"),
    "rock": ("classic rock", "rock anthems"),
    "afrikaans": ("afrikaans treffers", "afrikaans musiek"),
    "80s": ("80s hits", "best of the 80s"),
    "90s": ("90s hits", "best of the 90s"),
    "work_focus": ("deep focus instrumental", "music for concentration"),
    "adhd_focus": ("adhd focus music", "adhd concentration instrumental"),
    "massage": ("relaxing massage music", "spa massage instrumental"),
}


def discover(opener, category):
    """Search exactly one user-selected category; never refresh everything."""
    if category not in load():
        raise ValueError("Select a Spotify category to refresh")
    from declan.music import music
    targets = (category,)
    results = {}
    titles = {}
    for name in targets:
        found = []
        names = {}
        for term in QUERIES.get(name, (name.replace("_", " ") + " music", name.replace("_", " ") + " playlist")):
            for link, kind, title in music.spotify_search(opener, term, "", ("playlist",)):
                selected = canonical(link)
                if kind == "playlist" and selected and selected not in found:
                    found.append(selected)
                    if isinstance(title, str):
                        names[selected] = title
        # A legitimate empty search should not wipe a previously curated list.
        if found:
            results[name] = found
            titles[name] = names
    return refresh(results, titles)


def start_refresh(category, opener_factory):
    """Start one bounded refresh outside the HTTP request thread."""
    if category not in load():
        raise ValueError("Unknown Spotify category")
    with RUNTIME.lock:
        if not RUNTIME.claim(category):
            return {"refresh": RUNTIME.snapshot(), "categories": load(), "max_playlists": CAPACITY}

    def work():
        from datetime import datetime, timezone
        try:
            discover(opener_factory(), category)
        except HTTPError as error:
            status = error.code
            endpoint = "Spotify token" if "accounts.spotify.com" in error.url else "Spotify search"
            message = {
                400: "Spotify rejected the request (400).",
                401: "Spotify rejected authentication (401). Check Spotify credentials.",
                403: "Spotify denied API access (403). Check app permissions and API restrictions.",
                429: "Spotify rate limit reached (429). Retry later.",
            }.get(status, f"Spotify returned HTTP {status}.")
            LOGGER.warning("Spotify playlist discovery failed: %s HTTP %s", endpoint, status)
            error.close()
            with RUNTIME.lock:
                RUNTIME.failure(f"{endpoint}: {message}")
        except Exception as error:
            LOGGER.exception("Spotify playlist discovery failed")
            with RUNTIME.lock:
                RUNTIME.failure("Spotify discovery failed: " + type(error).__name__)
        finally:
            with RUNTIME.lock:
                RUNTIME.finish(datetime.now(timezone.utc).isoformat())

    try:
        Thread(target=work, daemon=True, name="spotify-playlist-refresh").start()
    except Exception as error:
        # A failed worker launch must not permanently block later refreshes.
        from datetime import datetime, timezone
        RUNTIME.failure("Spotify discovery worker failed: " + type(error).__name__)
        RUNTIME.finish(datetime.now(timezone.utc).isoformat())
        raise
    return listing()
