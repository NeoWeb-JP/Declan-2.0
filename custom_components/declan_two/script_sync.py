"""HA script sync (FUT-62, #834): keep the Declan scripts in the repo and in HA in step.

Home Assistant is the master. The integration ships the repo's versions of the
scripts Declan relies on (``declan_scripts/*.script.yaml``, identical to
``home_assistant/`` in the repo) and compares each with the live script that
has the same alias. Formatting does not count: both sides are parsed and
whitespace inside text is collapsed before comparing.

The last version seen in sync is remembered (HA storage), so the integration
can tell which side changed:

- in_sync: they match.
- ha_changed: HA was edited since the last sync. HA is master, so the repo
  needs updating: the panel offers the live YAML to pass on.
- repo_changed: a Declan release changed the script and HA hasn't been
  edited: "Apply in HA" writes it (after confirmation, with a backup).
- both_changed: both moved. HA wins; the panel shows the differences.
- different: they differ and there's no earlier sync to compare with. HA wins.
- missing: not in HA yet; "Apply in HA" creates it.

This module holds the pure logic; script_sync_view.py does the HA I/O.
"""
import difflib
import hashlib
import json
import re
from collections.abc import Mapping

STATES = ("in_sync", "ha_changed", "repo_changed", "both_changed", "different", "missing")
_SPACE = re.compile(r"\s+")


def normalise(value):
    """Parsed YAML -> a form where formatting-only differences disappear."""
    if isinstance(value, Mapping):
        return {str(key): normalise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalise(item) for item in value]
    if isinstance(value, str):
        return _SPACE.sub(" ", value).strip()
    return value


def fingerprint(config):
    if config is None:
        return None
    text = json.dumps(normalise(config), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).casefold()).strip("_")


def object_id(alias, live_aliases):
    """The live script with this alias (case-insensitive), else the alias slug."""
    wanted = str(alias).casefold().strip()
    for entity_object_id, live_alias in sorted(live_aliases.items()):
        if isinstance(live_alias, str) and live_alias.casefold().strip() == wanted:
            return entity_object_id
    return slug(alias)


def state(repo_config, live_config, baseline):
    """One script's sync state. ``baseline`` is {"repo": hash, "ha": hash} or None."""
    repo, live = fingerprint(repo_config), fingerprint(live_config)
    if live is None:
        return "missing"
    if repo == live:
        return "in_sync"
    if not isinstance(baseline, Mapping) or not baseline.get("repo") or not baseline.get("ha"):
        return "different"
    repo_moved, ha_moved = repo != baseline["repo"], live != baseline["ha"]
    if repo_moved and ha_moved:
        return "both_changed"
    if repo_moved:
        return "repo_changed"
    if ha_moved:
        return "ha_changed"
    return "different"


def unified_diff(repo_yaml, live_yaml, name):
    lines = difflib.unified_diff(
        repo_yaml.splitlines(keepends=True), live_yaml.splitlines(keepends=True),
        fromfile=f"repo/{name}", tofile=f"home-assistant/{name}", n=2)
    text = "".join(lines)
    return text[:20000]


def report(repo, live, baselines):
    """repo: {file: (alias, config)}; live: {object_id: (alias, config)}; baselines: {file: {...}}.

    Returns rows for the panel, without YAML (the view adds YAML and diffs).
    """
    live_aliases = {key: value[0] for key, value in live.items()}
    rows = []
    for name, (alias, config) in sorted(repo.items()):
        target = object_id(alias, live_aliases)
        live_config = live.get(target, (None, None))[1]
        rows.append({
            "file": name, "alias": alias, "entity_id": "script." + target,
            "state": state(config, live_config, baselines.get(name)),
            "repo_hash": fingerprint(config), "ha_hash": fingerprint(live_config),
        })
    return rows


def merge_script(existing, target, config):
    """scripts.yaml content (parsed) with ``target`` replaced by ``config``."""
    if existing is None:
        existing = {}
    if not isinstance(existing, Mapping):
        raise ValueError("scripts.yaml is not a mapping of scripts")  # noqa: TRY004 - reported as a write failure
    merged = dict(existing)
    merged[target] = config
    return merged
