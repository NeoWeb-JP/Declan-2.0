"""Home Assistant connection and web speech HTTP operations."""
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit


def ha_device_connection(*, environ, redirect_handler, proxy_handler, opener_factory):
    url = environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = environ.get("DECLAN_HA_TOKEN", "").strip()
    try:
        parsed = urlsplit(url)
        configured = (token and parsed.scheme in {"http", "https"} and parsed.hostname
                      and not any((parsed.username, parsed.password, parsed.query, parsed.fragment)))
    except ValueError:
        configured = False
    if not configured:
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    opener = opener_factory(proxy_handler({}), redirect_handler())
    return url, headers, opener


def render_web_voice(message, *, connect, config, request_factory):
    connection = connect()
    engine = config.get("DECLAN_WEB_TTS_ENTITY", "").strip()
    if connection is None or (engine and not re.fullmatch(r"tts\.[a-z0-9_]+", engine)):
        return None
    url, headers, opener = connection
    try:
        if not engine:
            template = (
                "{% set providers = integration_entities('elevenlabs') + integration_entities('elevenlabs_custom_tts') %}"
                "{% set result = namespace(engines=[]) %}"
                "{% for entity in states.tts if entity.state != 'unavailable' "
                "and (entity.entity_id in providers or 'elevenlabs' in entity.entity_id or 'elevenlabs' in entity.name | lower) %}"
                "{% set result.engines = result.engines + [[entity.entity_id, entity.name]] %}"
                "{% endfor %}{{ result.engines | to_json }}"
            )
            request = request_factory(f"{url}/api/template", headers=headers,
                              data=json.dumps({"template": template}).encode())
            with opener.open(request, timeout=2) as response:
                rows = json.loads(response.read(16384))
            candidates = {entity: name for entity, name in rows
                          if isinstance(entity, str) and re.fullmatch(r"tts\.[a-z0-9_]+", entity)
                          and isinstance(name, str)}
            named = [entity for entity, name in candidates.items() if "declan" in (entity + " " + name).casefold()]
            matches = named or list(candidates)
            if len(matches) != 1:
                return None
            engine = matches[0]
        request = request_factory(f"{url}/api/tts_get_url", headers=headers, data=json.dumps({
            "engine_id": engine, "message": message, "cache": False,
            "options": {"preferred_format": "mp3"},
        }).encode())
        with opener.open(request, timeout=10) as response:
            path = json.loads(response.read(8192))["path"]
        if not isinstance(path, str) or not re.fullmatch(r"/api/tts_proxy/[\w.-]+\.mp3", path, re.ASCII):
            return None
        limit = 8 * 1024 * 1024
        with opener.open(request_factory(url + path, headers=headers), timeout=10) as response:
            audio = response.read(limit + 1)
        return audio if 0 < len(audio) <= limit else None
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None
