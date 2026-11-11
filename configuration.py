"""Versioned non-secret server settings; imports never execute household actions."""
import hashlib
import json
import os
import re

import history

FIELDS = {
    'DECLAN_GOOD_MORNING_SCRIPT': 'script', 'DECLAN_GOOD_NIGHT_SCRIPT': 'script',
    'DECLAN_MOVIE_SCRIPT': 'script', 'DECLAN_BEDROOM_MOVIE_SCRIPT': 'script',
    'DECLAN_MOVIE_REMOTE': 'remote', 'DECLAN_BEDROOM_MOVIE_REMOTE': 'remote',
    'DECLAN_WEB_TTS_ENTITY': 'tts', 'DECLAN_MEDIA_SEARCH_AGENT': 'conversation',
    'DECLAN_WEB_ASSIST_PIPELINE': 'pipeline',
}


def _table(db):
    db.execute('CREATE TABLE IF NOT EXISTS server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')


def get(key, default=''):
    if key not in FIELDS:
        return os.environ.get(key, default)
    with history.database() as db:
        _table(db)
        row = db.execute('SELECT value FROM server_settings WHERE key = ?', (key,)).fetchone()
    return row[0] if row and row[0] else os.environ.get(key, default)


def _state(db):
    _table(db)
    history._intent_table(db)
    return {'settings': dict(db.execute('SELECT key, value FROM server_settings')),
            'learned_intents': dict(db.execute('SELECT phrase, target FROM learned_intents'))}


def _fingerprint(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def export(include_learning=False):
    with history.database() as db:
        state = _state(db)
    settings = {key: state['settings'].get(key, os.environ.get(key, '')) for key in FIELDS}
    document = {'format': 'declan-settings', 'schema_version': 1, 'settings': settings}
    if include_learning:
        document['learned_intents'] = state['learned_intents']
    return document


def validate(document):
    if (not isinstance(document, dict) or set(document) - {'format', 'schema_version', 'settings', 'learned_intents'}
            or document.get('format') != 'declan-settings' or type(document.get('schema_version')) is not int
            or document['schema_version'] != 1 or not isinstance(document.get('settings'), dict)):
        raise ValueError('Choose a supported Declan settings export (version 1).')
    for key, value in document['settings'].items():
        domain = FIELDS.get(key)
        if domain is None or not isinstance(value, str) or len(value) > 128:
            raise ValueError('Unknown or invalid setting. Credentials cannot be imported here.')
        pattern = r'[A-Za-z0-9_-]{1,64}' if domain == 'pipeline' else re.escape(domain) + r'\.[a-z0-9_]+'
        if value and not re.fullmatch(pattern, value):
            raise ValueError('Invalid entity or pipeline identifier.')
    aliases = document.get('learned_intents', {})
    if not isinstance(aliases, dict) or len(aliases) > 500:
        raise ValueError('Import up to 500 learned intentions.')
    for phrase, target in aliases.items():
        if (not all(isinstance(item, str) and 0 < len(item) <= 120
                    and not any(ord(char) < 32 for char in item) for item in (phrase, target))
                or history.normalize_phrase(phrase) != phrase or history.normalize_phrase(target) != target
                or phrase == target):
            raise ValueError('Invalid learned intention.')
    return document


def preview(document):
    document = validate(document)
    with history.database() as db:
        state = _state(db)
    return {'expected': _fingerprint({'state': state, 'document': document}), 'settings': document['settings'],
            'learning_count': len(document.get('learned_intents', {})),
            'replaces_learning': 'learned_intents' in document,
            'notice': 'Check entity IDs for this home. Non-empty imported settings override server environment defaults; empty values use those defaults. '
                      'HA credentials, speech caches and voice samples are not included.'}


def apply(document, expected):
    document = validate(document)
    with history.database() as db:
        state = _state(db)
        if not isinstance(expected, str) or expected != _fingerprint({'state': state, 'document': document}):
            raise ValueError('Settings changed since preview. Preview the file again.')
        # Recovery data and all imported changes commit together, or none do.
        db.execute('CREATE TABLE IF NOT EXISTS settings_recovery (id INTEGER PRIMARY KEY, document TEXT)')
        previous = {'format': 'declan-settings', 'schema_version': 1,
                    'settings': {key: state['settings'].get(key, os.environ.get(key, '')) for key in FIELDS},
                    'learned_intents': state['learned_intents']}
        db.execute('INSERT OR REPLACE INTO settings_recovery VALUES (1, ?)', (json.dumps(previous),))
        db.executemany('INSERT OR REPLACE INTO server_settings VALUES (?, ?)', document['settings'].items())
        if 'learned_intents' in document:
            db.execute('DELETE FROM learned_intents')
            db.executemany('INSERT INTO learned_intents VALUES (?, ?)', document['learned_intents'].items())


def recovery(include_learning=False):
    with history.database() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'settings_recovery'").fetchone()
        row = db.execute('SELECT document FROM settings_recovery WHERE id = 1').fetchone() if exists else None
    if not row:
        raise ValueError('No previous settings import is available.')
    document = json.loads(row[0])
    if not include_learning:
        document.pop('learned_intents', None)
    return document
