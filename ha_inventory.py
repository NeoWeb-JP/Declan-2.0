"""Read command-relevant state fields in bounded HA template pages."""
import json
from dataclasses import dataclass
import diagnostics
from execution_results import Outcome
from time import monotonic
from urllib.error import HTTPError
from urllib.request import Request

PAGE_SIZE = 200
MAX_PAGES = 100
MAX_PAGE_BYTES = 1024 * 1024
DEVICE_DOMAINS = ('binary_sensor', 'climate', 'cover', 'fan', 'light', 'media_player',
                  'switch', 'script', 'remote', 'input_boolean')
DEVICE_FIELDS = ('friendly_name', 'current_position', 'brightness', 'supported_color_modes', 'entity_id', 'device_class', 'supported_features')
MUSIC_FIELDS = ('friendly_name', 'media_title', 'media_artist', 'media_content_id', 'group_members')


@dataclass(frozen=True)
class InventoryResult:
    rows: tuple[dict, ...] | None
    error: Outcome | None = None

    def __post_init__(self):
        if self.rows is not None and not isinstance(self.rows, tuple):
            raise TypeError('inventory rows must be a tuple or None')
        if self.error is not None and not isinstance(self.error, Outcome):
            raise TypeError('inventory error must be an Outcome or None')

    @property
    def inventory(self):
        return list(self.rows) if self.rows is not None else None

    def as_legacy_pair(self):
        return self.inventory, self.error.value if self.error is not None else None

    @classmethod
    def coerce(cls, value) -> 'InventoryResult':
        if isinstance(value, cls):
            return value
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise ValueError('inventory provider must return a typed result or inventory/error pair')
        rows, error = value
        return cls(tuple(rows) if rows is not None else None, Outcome(error) if error else None)


def read(connection, *, music=False):
    return read_result(connection, music=music).as_legacy_pair()


def read_result(connection, *, music=False) -> InventoryResult:
    with diagnostics.stage('ha_inventory_music' if music else 'ha_inventory') as entry:
        result = _read_result(connection, music=music)
        entry['rows'] = len(result.rows) if result.rows is not None else None
        if result.error is not None:
            diagnostics.set_outcome(entry, result.error)
        return result


def _read_result(connection, *, music=False) -> InventoryResult:
    url, headers, opener = connection
    domains = ('media_player', 'assist_satellite') if music else DEVICE_DOMAINS
    fields = MUSIC_FIELDS if music else DEVICE_FIELDS
    inventory: list[dict] = []
    total = None
    deadline = monotonic() + 10
    try:
        for page in range(MAX_PAGES):
            template = (
                "{# declan_inventory_page #}"
                "{% set entities = states | selectattr('domain', 'in', " + json.dumps(domains) + ") | sort(attribute='entity_id') | list %}"
                "{% set result = namespace(rows=[]) %}"
                "{% set ma = integration_entities('music_assistant') %}"
                "{% for entity in entities[" + str(page * PAGE_SIZE) + ":" + str((page + 1) * PAGE_SIZE) + "] %}"
                "{% set attrs = namespace(values={}) %}"
                "{% for key in " + json.dumps(fields) + " %}"
                "{% if key in entity.attributes %}"
                "{% set attrs.values = dict(attrs.values, **{key: entity.attributes[key]}) %}"
                "{% endif %}{% endfor %}"
                + ("{% set source = namespace(entities=[]) %}"
                   "{% if entity.entity_id in ma %}"
                   "{% for identifier in device_attr(entity.entity_id, 'identifiers') or [] %}"
                   "{% if identifier[0] == 'music_assistant' and identifier[1] is string "
                   "and identifier[1].startswith('media_player.') %}"
                   "{% set source.entities = source.entities + [identifier[1]] %}"
                   "{% endif %}{% endfor %}{% endif %}" if music else "")
                + "{% set result.rows = result.rows + [dict(entity_id=entity.entity_id, state=entity.state, attributes=attrs.values"
                + (", declan_area=area_name(entity.entity_id), declan_device=device_id(entity.entity_id), "
                   "declan_music_assistant=entity.entity_id in ma, declan_source_entities=source.entities" if music else ", declan_area=area_name(entity.entity_id)")
                + ")] %}{% endfor %}{{ dict(total=entities | count, rows=result.rows) | to_json }}"
            )
            request = Request(url + '/api/template', headers=headers,
                              data=json.dumps({'template': template}).encode())
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError('Inventory deadline exceeded')
            with opener.open(request, timeout=min(4, remaining)) as response:
                raw = response.read(MAX_PAGE_BYTES + 1)
            if len(raw) > MAX_PAGE_BYTES:
                raise ValueError('Inventory page too large')
            payload = json.loads(raw)
            if (not isinstance(payload, dict) or type(payload.get('total')) is not int
                    or not 0 <= payload['total'] <= PAGE_SIZE * MAX_PAGES
                    or not isinstance(payload.get('rows'), list)):
                raise ValueError('Invalid inventory page')
            if total is None:
                total = payload['total']
            if total != payload['total']:
                raise ValueError('Entity registry changed during paging')
            rows = payload['rows']
            if len(rows) != min(PAGE_SIZE, total - len(inventory)) or not all(
                    isinstance(row, dict) and isinstance(row.get('entity_id'), str)
                    and row['entity_id'].partition('.')[0] in domains
                    and isinstance(row.get('state'), str) and isinstance(row.get('attributes'), dict)
                    for row in rows):
                raise ValueError('Incomplete inventory page')
            inventory.extend(rows)
            if len(inventory) == total:
                if len({row['entity_id'] for row in inventory}) != total:
                    raise ValueError('Duplicate inventory entities')
                return InventoryResult(tuple(inventory))
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, TypeError):
        pass
    return InventoryResult(None, Outcome.UNAVAILABLE)
