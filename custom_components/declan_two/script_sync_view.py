"""Admin-only HA script sync (FUT-62). HA is master; nothing is written without a confirmed request.

GET  /api/declan_two/script-sync -> one row per Declan script: state, YAML and differences.
POST {"action": "apply", "file": name}     -> write the repo version into scripts.yaml
     (backing up the file first), reload scripts and check the result.
POST {"action": "keep_ha", "file": name}   -> HA's version stays; remember both as synced.
"""
import logging
import os
import re
import shutil
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from . import script_sync

_LOGGER = logging.getLogger(__name__)
FOLDER = Path(__file__).with_name("declan_scripts")
STORE_KEY = "declan_two_script_sync"
FILE = re.compile(r"[a-z0-9_]+\.script\.yaml\Z")


def _yaml():
    from homeassistant.util import yaml as ha_yaml
    return ha_yaml


def read_repo():
    """{file: (alias, config, yaml text)} for the scripts shipped with the integration."""
    loader = _yaml()
    scripts = {}
    for path in sorted(FOLDER.glob("*.script.yaml")):
        text = path.read_text(encoding="utf-8")
        config = loader.parse_yaml(text)
        if isinstance(config, Mapping) and isinstance(config.get("alias"), str):
            scripts[path.name] = (config["alias"], dict(config), text)
    return scripts


def read_live(hass):
    """{object_id: (alias, config)} for loaded scripts with a raw configuration."""
    component = hass.data.get("script")
    live = {}
    for entity in getattr(component, "entities", ()):
        raw = getattr(entity, "raw_config", None)
        if isinstance(raw, Mapping) and isinstance(getattr(entity, "entity_id", None), str):
            live[entity.entity_id.split(".", 1)[1]] = (raw.get("alias"), dict(raw))
    return live


async def _store(hass):
    from homeassistant.helpers.storage import Store
    if STORE_KEY not in hass.data:
        store = Store(hass, 1, STORE_KEY)
        loaded = await store.async_load()
        hass.data[STORE_KEY] = {"store": store, "baselines": loaded if isinstance(loaded, dict) else {}}
    return hass.data[STORE_KEY]


async def _remember(hass, name, repo_hash, ha_hash):
    state = await _store(hass)
    state["baselines"][name] = {"repo": repo_hash, "ha": ha_hash}
    await state["store"].async_save(state["baselines"])


async def build_report(hass):
    repo = await hass.async_add_executor_job(read_repo)
    live = read_live(hass)
    state = await _store(hass)
    rows = script_sync.report({name: (alias, config) for name, (alias, config, _) in repo.items()},
                              live, state["baselines"])
    dump = _yaml().dump
    for row in rows:
        name = row["file"]
        target = row["entity_id"].split(".", 1)[1]
        repo_text = repo[name][2]
        live_config = live.get(target, (None, None))[1]
        live_text = await hass.async_add_executor_job(dump, live_config) if live_config is not None else ""
        row["repo_yaml"], row["ha_yaml"] = repo_text, live_text
        row["diff"] = "" if row["state"] in {"in_sync", "missing"} else script_sync.unified_diff(
            await hass.async_add_executor_job(dump, repo[name][1]), live_text, name)
        if row["state"] == "in_sync":
            current = state["baselines"].get(name)
            if current != {"repo": row["repo_hash"], "ha": row["ha_hash"]}:
                await _remember(hass, name, row["repo_hash"], row["ha_hash"])
    return rows


def write_scripts_file(path, target, config):
    """Back up scripts.yaml, then replace one script in it. Returns the backup path."""
    loader = _yaml()
    path = Path(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = loader.parse_yaml(text) if text.strip() else {}
    merged = script_sync.merge_script(existing, target, config)
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.declan-{datetime.now().astimezone():%Y%m%d-%H%M%S}.bak")
        shutil.copy2(path, backup)
    temporary = path.with_name(path.name + ".declan-tmp")
    temporary.write_text(loader.dump(merged), encoding="utf-8")
    os.replace(temporary, path)
    return str(backup) if backup else None


def defined_in_scripts_file(path, target):
    loader = _yaml()
    path = Path(path)
    if not path.exists():
        return False
    data = loader.parse_yaml(path.read_text(encoding="utf-8"))
    return isinstance(data, Mapping) and target in data


class DeclanScriptSyncView(HomeAssistantView):
    url = "/api/declan_two/script-sync"
    name = "api:declan_two:script_sync"
    requires_auth = True

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            raise web.HTTPForbidden()
        hass = request.app["hass"]
        try:
            rows = await build_report(hass)
        except Exception as error:  # noqa: BLE001 - report, never break the panel
            _LOGGER.error("Script sync report failed (%s)", type(error).__name__)
            return web.json_response({"error": "unavailable"}, status=503, headers={"Cache-Control": "no-store"})
        return web.json_response({"scripts": rows}, headers={"Cache-Control": "no-store"})

    async def post(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            raise web.HTTPForbidden()
        if request.content_type != "application/json" or request.content_length is None or not 0 < request.content_length <= 512:
            return web.json_response({"error": "Invalid content"}, status=400)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid JSON"}, status=400)
        if (not isinstance(body, dict) or set(body) != {"action", "file"} or body["action"] not in {"apply", "keep_ha"}
                or not isinstance(body["file"], str) or not FILE.fullmatch(body["file"])):
            return web.json_response({"error": "Invalid request"}, status=400)
        hass = request.app["hass"]
        rows = {row["file"]: row for row in await build_report(hass)}
        row = rows.get(body["file"])
        if row is None:
            return web.json_response({"error": "Unknown script"}, status=404)
        if body["action"] == "keep_ha":
            if row["ha_hash"] is None:
                return web.json_response({"error": "That script isn't in Home Assistant."}, status=409)
            await _remember(hass, row["file"], row["repo_hash"], row["ha_hash"])
            return web.json_response({"result": "kept", "file": row["file"]})
        return await self._apply(hass, row)

    async def _apply(self, hass, row):
        target = row["entity_id"].split(".", 1)[1]
        path = hass.config.path("scripts.yaml")
        if row["state"] != "missing" and not await hass.async_add_executor_job(defined_in_scripts_file, path, target):
            return web.json_response({"error": "This script isn't in scripts.yaml (it may be in a package), "
                                               "so Declan can't update it. Paste the YAML in by hand."}, status=409)
        repo = await hass.async_add_executor_job(read_repo)
        config = repo[row["file"]][1]
        try:
            backup = await hass.async_add_executor_job(write_scripts_file, path, target, config)
        except (OSError, ValueError) as error:
            _LOGGER.error("Script sync write failed (%s)", type(error).__name__)
            return web.json_response({"error": "Could not write scripts.yaml. Nothing was changed."}, status=500)
        try:
            await hass.services.async_call("script", "reload", blocking=True)
        except Exception as error:  # noqa: BLE001 - report the reload failure with the backup
            _LOGGER.error("Script reload failed after sync (%s)", type(error).__name__)
            return web.json_response({"result": "written_not_reloaded", "backup": backup}, status=502)
        live = read_live(hass).get(target, (None, None))[1]
        if script_sync.fingerprint(live) != row["repo_hash"]:
            return web.json_response({"result": "unverified", "backup": backup}, status=502)
        await _remember(hass, row["file"], row["repo_hash"], row["repo_hash"])
        return web.json_response({"result": "applied", "file": row["file"], "entity_id": row["entity_id"],
                                  "backup": backup})
