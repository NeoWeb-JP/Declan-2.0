"""Declan 2.0 owned Spotify playlist discovery and category curation."""
import json
import os
import re
from pathlib import Path
from threading import RLock

CATEGORIES = ("country", "braai", "romantic", "sexy_time", "rock", "afrikaans",
              "80s", "90s", "work_focus", "adhd_focus", "massage")
CAPACITY = 25
URI = re.compile(r"(?:spotify(?::|://)playlist[:/]|https://open\.spotify\.com/playlist/)([A-Za-z0-9]{22})(?:\?[^#]*)?\Z")
LOCK = RLock()
DEFAULT_PATH = Path(__file__).with_name(".data") / "spotify-playlists.json"


def canonical(value):
    match = URI.fullmatch(value.strip()) if isinstance(value, str) else None
    return "spotify://playlist/" + match.group(1) if match else None


def unique(values):
    return list(dict.fromkeys(x for value in values if (x := canonical(value))))


def catalogue_path():
    return Path(os.environ.get("DECLAN_SPOTIFY_PLAYLISTS_FILE") or DEFAULT_PATH)


def normalize(raw):
    result = {}
    for category in CATEGORIES:
        item = raw.get(category, {}) if isinstance(raw, dict) else {}
        item = item if isinstance(item, dict) else {}
        excluded = unique(item.get("excluded") or [])
        favourites = [x for x in unique(item.get("favourites") or []) if x not in excluded][:CAPACITY]
        discovered = [x for x in unique(item.get("discovered") or []) if x not in excluded and x not in favourites]
        discovered = discovered[:CAPACITY - len(favourites)]
        result[category] = {"favourites": favourites, "excluded": excluded,
                            "discovered": discovered, "playlists": favourites + discovered}
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
    selected = canonical(body["playlist"])
    if category not in CATEGORIES or operation not in ("add", "remove", "delete") or not selected:
        raise ValueError("Invalid playlist change")
    with LOCK:
        data = load()
        item = data[category]
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
        return {"categories": load(), "max_playlists": CAPACITY}


def refresh(discovered):
    """Merge Spotify search results without losing manual pins or exclusions."""
    with LOCK:
        data = load()
        for category in CATEGORIES:
            if category in discovered:
                data[category]["discovered"] = unique(discovered[category])
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


def discover(opener):
    """Search Spotify through Declan 2.0's existing credentials/token cache."""
    import music
    results = {}
    for category, terms in QUERIES.items():
        found = []
        for term in terms:
            for link, kind, _title in music.spotify_search(opener, term, "", ("playlist",)):
                selected = canonical(link)
                if kind == "playlist" and selected and selected not in found:
                    found.append(selected)
        results[category] = found
    return refresh(results)
