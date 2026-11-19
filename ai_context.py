"""Choose complete, permission-filtered device groups for bounded AI planning."""
import re
from typing import Any

IGNORE = frozenset({
    'a', 'all', 'and', 'at', 'can', 'could', 'do', 'for', 'in', 'is', 'the',
    'light', 'lights', 'lighting', 'on', 'off', 'open', 'close', 'cover', 'covers',
    'fan', 'fans', 'switch', 'switches', 'blinds', 'blind', 'curtains', 'curtain',
    'please', 'set', 'turn', 'you', 'would', 'my', 'me', 'it', 'up', 'down',
    'every', 'everything', 'then', 'make', 'to', 'room', 'floor',
})


class ContextSelectionError(ValueError):
    """Only fixed, privacy-safe clarification messages cross the voice boundary."""
    def __init__(self, reason='precise'):
        messages = {
            'precise': 'Please specify a more precise room or device for AI planning.',
            'ambiguous': 'More than one area, floor or device matches. Please use a unique name.',
            'large': 'That group has too many devices for one AI request. Please choose a smaller area.',
            'actions': 'That group exceeds your AI action limit. Please choose fewer devices or change the limit in Settings.',
            'metadata': 'Home Assistant area metadata is unavailable or changed. Please retry, update the Declan integration, or use an exact entity ID.',
            'missing': 'Some requested groups contain no permitted devices. Please choose an exposed device or area.',
            'compound': 'Please split exclusions or unclear mixed-area requests into separate commands.',
        }
        super().__init__(messages.get(reason, messages['precise']))


def _phrase(value):
    return ' '.join(re.findall(r'[^\W_]+', value.casefold())) if isinstance(value, str) else ''


def _catalogue(payload):
    if not isinstance(payload, dict) or set(payload) != {'areas', 'floors'}:
        raise ContextSelectionError('metadata')
    result: dict[str, list[dict[str, Any]]] = {}
    for kind, bound in (('areas', 1024), ('floors', 128)):
        rows = payload[kind]
        if not isinstance(rows, list) or len(rows) > bound:
            raise ContextSelectionError('metadata')
        ids: set[str] = set()
        names: set[str] = set()
        clean = []
        for row in rows:
            if not isinstance(row, dict):
                raise ContextSelectionError('metadata')
            identifier, name, aliases = row.get('id'), row.get('name'), row.get('aliases')
            if (not isinstance(identifier, str) or not 0 < len(identifier) <= 128
                    or not isinstance(name, str) or not 0 < len(name) <= 160 or not _phrase(name)
                    or not isinstance(aliases, list) or len(aliases) > 32
                    or any(not isinstance(alias, str) or not 0 < len(alias) <= 160 or not _phrase(alias) for alias in aliases)
                    or identifier in ids or _phrase(name) in names):
                raise ContextSelectionError('metadata')
            ids.add(identifier)
            names.add(_phrase(name))
            clean.append(dict(row, aliases=list(aliases)))
        result[kind] = clean
    floor_ids = {row['id'] for row in result['floors']}
    if any(row.get('floor_id') is not None and (
            not isinstance(row['floor_id'], str) or row['floor_id'] not in floor_ids) for row in result['areas']):
        raise ContextSelectionError('metadata')
    return result


def select(inventory, utterance, *, limit=100, locations=None, max_actions=None):
    """Never add entities, truncate a group or treat an alias as permission."""
    if (not isinstance(inventory, list) or not isinstance(utterance, str)
            or type(limit) is not int or not 1 <= limit <= 100
            or max_actions is not None and (type(max_actions) is not int or not 1 <= max_actions <= 8)):
        raise ContextSelectionError()
    if len(inventory) <= limit:
        return inventory
    lookup = {}
    for row in inventory:
        if (not isinstance(row, dict) or not isinstance(row.get('entity_id'), str)
                or not isinstance(row.get('attributes'), dict) or row['entity_id'] in lookup):
            raise ContextSelectionError('metadata')
        lookup[row['entity_id']] = row
    text = _phrase(utterance)
    words = set(text.split())
    broad = bool(words & {'all', 'every', 'everything'})
    if words & {'except', 'excluding', 'without', 'not'}:
        raise ContextSelectionError('compound')

    def finish(rows):
        if not rows:
            raise ContextSelectionError('missing')
        if len(rows) > limit:
            raise ContextSelectionError('large')
        if broad and max_actions is not None and len(rows) > max_actions:
            raise ContextSelectionError('actions')
        return rows

    explicit = set(re.findall(r'(?<![\w.])[a-z_]+\.[a-z0-9_]+(?![\w.])', utterance.casefold()))
    if explicit and not broad:
        if not explicit <= lookup.keys():
            raise ContextSelectionError('missing')
        if max_actions is not None and len(explicit) > max_actions:
            raise ContextSelectionError('actions')
        return finish([row for row in inventory if row['entity_id'] in explicit])

    domains = set()
    for domain, pattern in (('light', r'\b(?:light|lights|lighting)\b'),
                            ('fan', r'\bfans?\b'), ('cover', r'\b(?:covers?|blinds?|curtains?)\b'),
                            ('switch', r'\bswitches\b|\b(?:the|a|all|every) switch\b')):
        if re.search(pattern, text):
            domains.add(domain)
    candidates = [row for row in inventory if not domains or row['entity_id'].split('.', 1)[0] in domains]
    groups: dict[tuple[str, str], list[dict]] = {}
    labels: dict[str, set[tuple[str, str]]] = {}
    enriched: dict[str, dict] = {}

    def label(key, name):
        normalized = _phrase(name)
        if normalized:
            labels.setdefault(normalized, set()).add(key)

    if locations is not None:
        catalogue = _catalogue(locations)
        areas = {_phrase(row['name']): row for row in catalogue['areas']}
        floors = {row['id']: row for row in catalogue['floors']}
        for kind, entries in catalogue.items():
            for entry in entries:
                key = (kind, entry['id'])
                groups[key] = []
                for name in (entry['name'], *entry['aliases']):
                    label(key, name)
        for row in candidates:
            area_name = _phrase(row.get('declan_area'))
            area = areas.get(area_name)
            if area_name and area is None:
                raise ContextSelectionError('metadata')
            copy = dict(row)
            if area is not None:
                copy['declan_area_aliases'] = area['aliases']
                groups['areas', area['id']].append(copy)
                floor = floors.get(area.get('floor_id'))
                if floor is not None:
                    copy.update(declan_floor=floor['name'], declan_floor_aliases=floor['aliases'])
                    groups['floors', floor['id']].append(copy)
            enriched[row['entity_id']] = copy
    else:
        # Older native integrations still support canonical names. Do not
        # invent household aliases or infer a floor from an entity's name.
        for row in candidates:
            name = _phrase(row.get('declan_area'))
            if name:
                key = ('areas', name)
                groups.setdefault(key, []).append(row)
                label(key, name)

    matches = []
    for name, keys in labels.items():
        for match in re.finditer(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text):
            matches.append((match.start(), match.end(), name, keys))
    accepted: list[tuple[int, int, str, set[tuple[str, str]]]] = []
    for candidate_match in sorted(matches, key=lambda item: -(item[1] - item[0])):
        if not any(start <= candidate_match[0] and end >= candidate_match[1] for start, end, *_ in accepted):
            accepted.append(candidate_match)
    if accepted:
        selected: dict[str, dict] = {}
        matched_words = set()
        for _, _, name, keys in accepted:
            if len(keys) != 1:
                raise ContextSelectionError('ambiguous')
            members = groups[next(iter(keys))]
            if not members:
                raise ContextSelectionError('missing')
            selected.update((row['entity_id'], row) for row in members)
            matched_words.update(name.split())
        if words & {'and', 'then'} and words - IGNORE - matched_words:
            raise ContextSelectionError('compound')
        return finish([selected[row['entity_id']] for row in candidates if row['entity_id'] in selected])
    if broad:
        if words - IGNORE:
            raise ContextSelectionError('metadata' if locations is None else 'precise')
        return finish([enriched.get(row['entity_id'], row) for row in candidates])
    exact = [row for row in candidates if _phrase(row['attributes'].get('friendly_name'))
             and ' ' + _phrase(row['attributes']['friendly_name']) + ' ' in ' ' + text + ' ']
    if len(exact) == 1:
        return finish([enriched.get(exact[0]['entity_id'], exact[0])])
    if len(exact) > 1:
        raise ContextSelectionError('ambiguous')
    raise ContextSelectionError('metadata' if locations is None else 'precise')
