"""Register the native Declan management panel without replacing Ingress."""
import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig

PANEL_PATH = "declan-two-native"
ASSET_PATH = "/declan_two_native"
DATA_KEY = "declan_two_native_panel_registered"
FRONTEND = Path(__file__).parent / "frontend"


def panel_version(path=FRONTEND / "panel.js"):
    """A short hash of panel.js. It goes in the module URL, so a browser (or the
    HA app) that cached an older panel loads the new one after an upgrade."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return "0"


async def async_register_native_panel(hass):
    """Register once, even if a config entry is reloaded."""
    if hass.data.get(DATA_KEY):
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig(ASSET_PATH, str(FRONTEND), cache_headers=False)
    ])
    version = await hass.async_add_executor_job(panel_version)
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="declan-two-native-panel",
        frontend_url_path=PANEL_PATH,
        sidebar_title="Declan 2.0",
        sidebar_icon="mdi:robot-outline",
        module_url=f"{ASSET_PATH}/panel.js?v={version}",
        require_admin=True,
        embed_iframe=False,
    )
    hass.data[DATA_KEY] = True


def async_remove_native_panel(hass):
    """Remove the panel on integration unload, leaving static routes intact."""
    if hass.data.pop(DATA_KEY, False):
        frontend.async_remove_panel(hass, PANEL_PATH)
