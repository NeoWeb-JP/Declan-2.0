"""Declan 2.0 owned Spotify playlist discovery and category curation."""
import json
import os
import re
import logging
from urllib.error import HTTPError
from pathlib import Path
from threading import RLock, Thread

CATEGORIES = ("country", "braai", "romantic", "sexy_time", "rock", "afrikaans",
              "80s", "90s", "work_focus", "adhd_focus", "massage")
CAPACITY = 25
URI = re.compile(r"(?:spotify(?::|://)playlist[:/]|https://open\.spotify\.com/playlist/)([A-Za-z0-9]{22})(?:\?[^#]*)?\Z")
LOCK = RLock()
LOGGER = logging.getLogger(__name__)
DEFAULT_PATH = Path(__file__).with_name(".data") / "spotify-playlists.json"
_REFRESH = {"running": False, "category": None, "error": None, "completed": None}


def canonical(value):
    match = URI.fullmatch(value.strip()) if isinstance(value, str) else None
    return "spotify://playlist/" + match.group(1) if match else None


def unique(values):
    return list(dict.fromkeys(x for value in values if (x := canonical(value))))


def catalogue_path():
    return Path(os.environ.get("DECLAN_SPOTIFY_PLAYLISTS_FILE") or DEFAULT_PATH)


def normalize(raw):
    # Dislikes are global, not category-specific: a playlist must not
    # reappear via another genre's discovery refresh.
    try:
        import music
        with music.preference_db() as db:
            globally_disliked = {uri for (uri,) in db.execute(
                "SELECT uri FROM preferences WHERE weight = 0 AND uri LIKE 'spotify://playlist/%'"
            )}
    except (OSError, ValueError):
        globally_disliked = set()
    result = {}
    for category in CATEGORIES:
        item = raw.get(category, {}) if isinstance(raw, dict) else {}
        item = item if isinstance(item, dict) else {}
        excluded = unique(item.get("excluded") or [])
        excluded = list(dict.fromkeys(excluded + sorted(globally_disliked)))
        favourites = [x for x in unique(item.get("favourites") or []) if x not in excluded][:CAPACITY]
        discovered = [x for x in unique(item.get("discovered") or []) if x not in excluded and x not in favourites]
        discovered = discovered[:CAPACITY - len(favourites)]
        titles = item.get("titles") if isinstance(item.get("titles"), dict) else {}
        titles = {uri: name[:160] for uri, name in titles.items()
                  if isinstance(uri, str) and isinstance(name, str) and uri in favourites + discovered + excluded}
        result[category] = {"favourites": favourites, "excluded": excluded,
                            "discovered": discovered, "playlists": favourites + discovered,
                            "titles": titles}
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
    if not isinstance(body, dict) or set(body) != {"category", "playlist", "operation"}:
        raise ValueError("Invalid playlist change")
    category, operation = body["category"], body["operation"]
    if category in {"disliked_songs", "disliked_playlists"} and operation == "restore":
        import music
        value = body["playlist"]
        kind = "track" if category == "disliked_songs" else "playlist"
        if not isinstance(value, str) or not re.fullmatch(r"spotify://" + kind + r"/[A-Za-z0-9]{22}", value):
            raise ValueError("Invalid disliked item")
        with music.preference_db() as db:
            db.execute("DELETE FROM preferences WHERE uri = ? AND weight = 0", (value,))
        if kind == "playlist":
            with LOCK:
                data = load()
                for item in data.values():
                    item["excluded"] = [uri for uri in item["excluded"] if uri != value]
                save(data)
        return listing()
    selected = canonical(body["playlist"])
    if category not in CATEGORIES or operation not in ("add", "remove", "delete", "favourite", "unfavourite", "dislike", "restore") or not selected:
        raise ValueError("Invalid playlist change")
    with LOCK:
        data = load()
        item = data[category]
        if operation in {"favourite", "unfavourite", "dislike", "restore"}:
            import music
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
                item["excluded"] = [uri for uri in item["excluded"] if uri != selected]
            elif operation == "favourite":
                if selected not in item["playlists"] and len(item["playlists"]) >= CAPACITY:
                    raise ValueError("Category has 25 playlists; remove one first")
                item["discovered"] = [uri for uri in item["discovered"] if uri != selected]
                if selected not in item["favourites"]:
                    item["favourites"].append(selected)
            elif operation == "unfavourite" and selected in item["favourites"]:
                item["favourites"] = [uri for uri in item["favourites"] if uri != selected]
                if selected not in item["discovered"]:
                    item["discovered"].append(selected)
            data = normalize(data)
            save(data)
            return {"categories": data, "max_playlists": CAPACITY}
        for key in ("favourites", "discovered", "excluded"):
            item[key] = [x for x in item[key] if x != selected]
        if operation == "add":
            if len(item["favourites"]) >= CAPACITY:
                raise ValueError("Category has 25 pinned playlists; remove one first")
            item["favourites"].append(selected)
        elif operation == "delete":
            item["excluded"].append(selected)
        data = normalize(data)
        save(data)
        return {"categories": data, "max_playlists": CAPACITY}


def listing():
    with LOCK:
        import music
        with music.preference_db() as db:
            weights = dict(db.execute("SELECT uri, weight FROM preferences WHERE uri LIKE 'spotify://playlist/%'"))
            plays = dict(db.execute("SELECT uri, plays FROM playlist_play_counts"))
            disliked_songs = [uri for uri, weight in db.execute(
                "SELECT uri, weight FROM preferences WHERE uri LIKE 'spotify://track/%'") if weight == 0]
        return {"categories": load(), "max_playlists": CAPACITY, "refresh": dict(_REFRESH),
                "preferences": {"favourites": [uri for uri, weight in weights.items() if weight > 1],
                                "disliked_playlists": [uri for uri, weight in weights.items() if weight == 0],
                                "disliked_songs": disliked_songs,
                                "play_counts": plays}}


def refresh(discovered, titles=None):
    """Merge Spotify search results without losing manual pins or exclusions."""
    with LOCK:
        data = load()
        for category in CATEGORIES:
            if category in discovered:
                data[category]["discovered"] = unique(discovered[category])
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


def discover(opener, category=None):
    """Search Spotify playlists and preserve existing results on failed searches."""
    import music
    targets = (category,) if category else CATEGORIES
    results = {}
    titles = {}
    for name in targets:
        found = []
        names = {}
        for term in QUERIES[name]:
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
    if category not in CATEGORIES:
        raise ValueError("Unknown Spotify category")
    with LOCK:
        if _REFRESH["running"]:
            return {"refresh": dict(_REFRESH), "categories": load(), "max_playlists": CAPACITY}
        _REFRESH.update(running=True, category=category, error=None, completed=None)

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
            with LOCK:
                _REFRESH["error"] = f"{endpoint}: {message}"
        except Exception as error:
            LOGGER.exception("Spotify playlist discovery failed")
            with LOCK:
                _REFRESH["error"] = "Spotify discovery failed: " + type(error).__name__
        finally:
            with LOCK:
                _REFRESH["running"] = False
                _REFRESH["completed"] = datetime.now(timezone.utc).isoformat()

    Thread(target=work, daemon=True, name="spotify-playlist-refresh").start()
    return listing()
