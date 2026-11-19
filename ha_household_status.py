"""Home Assistant connectivity and household presence status readers."""
import json
import re
import sqlite3
from urllib.error import HTTPError
from home_assistant_results import HomeAssistantStatus, HomeAssistantStatusResult


def home_assistant_status_result(*, environ, history_store, request_factory, opener_factory, proxy_factory, redirect_factory, parse_url):
    url = environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = environ.get("DECLAN_HA_TOKEN", "").strip()
    if not url or not token:
        try:
            if history_store.has_recent_assist():
                return HomeAssistantStatusResult(HomeAssistantStatus.ASSIST_RECENT)
        except (OSError, sqlite3.Error):
            pass
        return HomeAssistantStatusResult(HomeAssistantStatus.NOT_CONFIGURED)
    try:
        parsed = parse_url(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return HomeAssistantStatusResult(HomeAssistantStatus.NOT_CONFIGURED)
        request = request_factory(url + "/api/", headers={"Authorization": f"Bearer {token}"})
        opener = opener_factory(proxy_factory({}), redirect_factory())
        with opener.open(request, timeout=3) as response:
            payload = json.loads(response.read(4096))
            if response.status == 200 and payload == {"message": "API running."}:
                return HomeAssistantStatusResult(HomeAssistantStatus.CONNECTED)
    except HTTPError as error:
        status = error.code
        error.close()
        if status in {401, 403}:
            return HomeAssistantStatusResult(HomeAssistantStatus.AUTHENTICATION_FAILED)
    except (OSError, ValueError):
        pass
    return HomeAssistantStatusResult(HomeAssistantStatus.DISCONNECTED)


def configured_guest_mode_entity(*, entities):
    """Avoid a default household ID or HTTP failure for invalid settings."""
    try:
        return entities.guest_mode()
    except (OSError, sqlite3.Error, ValueError):
        return ""


def read_guest_mode(*, environ, entities, request_factory, opener_factory, proxy_factory, redirect_factory, parse_url):
    url = environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = environ.get("DECLAN_HA_TOKEN", "").strip()
    try:
        parsed = parse_url(url)
        if (not token or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return None
        entity = entities.guest_mode()
        request = request_factory(f"{url}/api/states/{entity}", headers={"Authorization": f"Bearer {token}"})
        opener = opener_factory(proxy_factory({}), redirect_factory())
        with opener.open(request, timeout=1) as response:
            return json.loads(response.read(4096)).get("state")
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, TypeError, AttributeError, sqlite3.Error):
        pass
    return None


def read_visitors_present(*, environ, config, visitors_entity, request_factory, opener_factory, proxy_factory, redirect_factory, parse_url):
    """Visitor presence is independent of guest authority.

    Missing or unavailable state is unknown and therefore privacy-safe.
    """
    url = environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = environ.get("DECLAN_HA_TOKEN", "").strip()
    try:
        parsed = parse_url(url)
        if (not token or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return None
        visitor_entity = config.get("DECLAN_VISITORS_ENTITY", visitors_entity)
        if not re.fullmatch(r"input_boolean\.[a-z0-9_]+", visitor_entity):
            return None
        request = request_factory(f"{url}/api/states/{visitor_entity}",
                          headers={"Authorization": f"Bearer {token}"})
        with opener_factory(proxy_factory({}), redirect_factory()).open(request, timeout=1) as response:
            state = json.loads(response.read(4096)).get("state")
            return {"on": True, "off": False}.get(state)
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, TypeError, AttributeError, sqlite3.Error):
        pass
    return None
