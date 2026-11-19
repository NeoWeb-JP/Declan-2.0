"""Read-only registry names for bounded AI context selection."""
from aiohttp import web
from homeassistant.components.http import HomeAssistantView


def location_catalogue(hass):
    from homeassistant.helpers import area_registry, floor_registry

    def names(entry):
        name = entry.name
        aliases = sorted(entry.aliases)
        if not isinstance(name, str) or not 0 < len(name) <= 160 or len(aliases) > 32 or any(
                not isinstance(alias, str) or not 0 < len(alias) <= 160 for alias in aliases):
            raise ValueError('Location labels exceed bounds')
        return {'name': name, 'aliases': aliases}

    areas = []
    for index, area in enumerate(area_registry.async_get(hass).async_list_areas()):
        if index >= 1024:
            raise ValueError('Area registry exceeds bounds')
        areas.append({'id': area.id, 'floor_id': area.floor_id, **names(area)})
    floors = []
    for index, floor in enumerate(floor_registry.async_get(hass).async_list_floors()):
        if index >= 128:
            raise ValueError('Floor registry exceeds bounds')
        floors.append({'id': floor.floor_id, **names(floor)})
    return {'areas': areas, 'floors': floors}


class DeclanAILocationsView(HomeAssistantView):
    url = '/api/declan_two/ai-locations'
    name = 'api:declan_two:ai_locations'
    requires_auth = True

    async def get(self, request):
        user = request.get('hass_user')
        if user is None or not user.is_admin:
            raise web.HTTPForbidden()
        try:
            payload = location_catalogue(request.app['hass'])
        except (AttributeError, KeyError, TypeError, ValueError):
            return web.json_response({'status': 'location_metadata_unavailable'}, status=503,
                                     headers={'Cache-Control': 'no-store'})
        return web.json_response(payload, headers={'Cache-Control': 'no-store'})
