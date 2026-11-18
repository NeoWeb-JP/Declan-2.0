"""Explicitly consented local samples. This module never trains or identifies people."""
import base64
import hashlib
import io
import math
from pathlib import Path
import re
import secrets
import sqlite3
import struct
from time import time
import wave

from voice_audio_crypto import encrypt, decrypt
from contextlib import closing, contextmanager

DATABASE = Path(__file__).resolve().parent / '.data' / 'voice-profiles.sqlite3'


@contextmanager
def database():
    DATABASE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with closing(sqlite3.connect(DATABASE, timeout=2)) as db, db:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('PRAGMA secure_delete = ON')
        db.execute('CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, name TEXT NOT NULL, consent_at REAL)')
        db.execute('''CREATE TABLE IF NOT EXISTS consent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, profile TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('granted', 'revoked')),
            recorded_at REAL NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS samples (id TEXT PRIMARY KEY, profile TEXT NOT NULL
            REFERENCES profiles(id) ON DELETE CASCADE, audio BLOB NOT NULL, duration REAL, digest TEXT,
            consent_at REAL, UNIQUE(profile, digest))''')
        yield db
    DATABASE.chmod(0o600)


def listing():
    with database() as db:
        profiles = [{'id': row[0], 'name': row[1], 'consent_at': row[2], 'samples': []}
                    for row in db.execute('SELECT id, name, consent_at FROM profiles ORDER BY name')]
        for profile in profiles:
            profile['samples'] = [{'id': row[0], 'duration': row[1], 'consent_at': row[2]}
                                  for row in db.execute('SELECT id, duration, consent_at FROM samples WHERE profile = ?',
                                                        (profile['id'],))]
            # Expose a small, metadata-only consent history. Never include
            # sample audio, digests, tokens or free-form user input in events.
            profile['consent_events'] = [
                {'action': row[0], 'recorded_at': row[1]}
                for row in db.execute(
                    'SELECT action, recorded_at FROM consent_events '
                    'WHERE profile = ? ORDER BY id DESC LIMIT 20', (profile['id'],))
            ]
    return {'profiles': profiles, 'recogniser_connected': False,
            'notice': 'Voice samples are encrypted in local storage and do not change '
                      'speaker matching yet. A person must consent before storing samples; '
                      'revocation deletes live samples. Retained older upgrade backups '
                      'must be sanitised separately if not already cleaned.'}


def validate_audio(encoded):
    if not isinstance(encoded, str) or len(encoded) > 427000:
        raise ValueError('Use a one to ten second mono 16 kHz PCM WAV recording.')
    try:
        audio = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(audio), 'rb') as recording:
            if (recording.getnchannels(), recording.getsampwidth(), recording.getframerate(), recording.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise ValueError
            frames = recording.getnframes()
            if not 16000 <= frames <= 160000:
                raise ValueError
            pcm = recording.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError
        values = struct.unpack('<' + 'h' * frames, pcm)
        if math.sqrt(sum(value * value for value in values) / frames) < 80:
            raise ValueError('The recording is too quiet. Record a clear spoken sentence.')
    except (wave.Error, EOFError, struct.error, ValueError) as error:
        raise ValueError('Use a clear one to ten second mono 16 kHz PCM WAV recording.') from error
    return audio, frames / 16000


def manage(body):
    if not isinstance(body, dict):
        raise ValueError('Choose a voice profile operation.')
    operation = body.get('operation')
    if operation == 'create':
        name = body.get('name')
        if body.get('consent') is not True or not isinstance(name, str) or not re.fullmatch(r"[^\W\d_][\w '\u2019-]{0,39}", name):
            raise ValueError('Enter your name and confirm consent to store your voice locally.')
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM profiles').fetchone()[0] >= 10:
                raise ValueError('Up to ten local voice profiles are supported.')
            if db.execute('SELECT 1 FROM profiles WHERE lower(name) = lower(?)', (name,)).fetchone():
                raise ValueError('That name already has a profile.')
            profile_id, granted_at = secrets.token_hex(12), time()
            db.execute('INSERT INTO profiles VALUES (?, ?, ?)', (profile_id, name, granted_at))
            db.execute('INSERT INTO consent_events(profile, action, recorded_at) VALUES (?, ?, ?)',
                       (profile_id, 'granted', granted_at))
        return listing()
    audio = duration = None
    if operation == 'save_sample':
        if body.get('consent') is not True:
            raise ValueError('Confirm consent before saving a sample.')
        audio, duration = validate_audio(body.get('audio'))
    if not isinstance(body.get('profile'), str) or not re.fullmatch(r'[a-f0-9]{24}', body['profile']):
        raise ValueError('Choose an existing voice profile.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        profile = db.execute('SELECT id, name, consent_at FROM profiles WHERE id = ?', (body.get('profile'),)).fetchone()
        if not profile:
            raise ValueError('Refresh and choose an existing voice profile.')
        if operation == 'revoke_consent' and body.get('confirm') is True:
            # Revoke storage permission and erase all live local samples atomically.
            db.execute('DELETE FROM samples WHERE profile = ?', (profile[0],))
            db.execute('UPDATE profiles SET consent_at = NULL WHERE id = ?', (profile[0],))
            db.execute('INSERT INTO consent_events(profile, action, recorded_at) VALUES (?, ?, ?)',
                       (profile[0], 'revoked', time()))
        elif operation == 'grant_consent' and body.get('consent') is True:
            granted_at = time()
            db.execute('UPDATE profiles SET consent_at = ? WHERE id = ?', (granted_at, profile[0]))
            db.execute('INSERT INTO consent_events(profile, action, recorded_at) VALUES (?, ?, ?)',
                       (profile[0], 'granted', granted_at))
        elif operation == 'delete_profile' and body.get('confirm') is True:
            # Remove profile-specific consent identifiers in the same
            # transaction. Keeping orphaned audit IDs defeats profile erasure.
            db.execute('DELETE FROM consent_events WHERE profile = ?', (profile[0],))
            db.execute('DELETE FROM profiles WHERE id = ?', (profile[0],))
        elif operation == 'save_sample':
            if profile[2] is None:
                raise ValueError('Voice storage consent was revoked. Grant consent before saving samples.')
            if db.execute('SELECT count(*) FROM samples WHERE profile = ?', (profile[0],)).fetchone()[0] >= 20:
                raise ValueError('Review or remove samples before adding more (20 per person).')
            digest = hashlib.sha256(audio).hexdigest()
            if db.execute('SELECT 1 FROM samples WHERE profile = ? AND digest = ?', (profile[0], digest)).fetchone():
                raise ValueError('This recording has already been saved.')
            sample_id = secrets.token_hex(12)
            encrypted = encrypt(audio, sample_id)
            db.execute('INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?)',
                       (sample_id, profile[0], encrypted, duration, digest, time()))
        elif operation == 'delete_sample' and body.get('confirm') is True:
            if db.execute('DELETE FROM samples WHERE id = ? AND profile = ?', (body.get('sample'), profile[0])).rowcount != 1:
                raise ValueError('That sample no longer exists.')
        elif operation in {'preview', 'export'}:
            rows = db.execute('SELECT id, audio, duration, digest FROM samples WHERE profile = ?', (profile[0],)).fetchall()
            if operation == 'preview':
                rows = [row for row in rows if row[0] == body.get('sample')]
                if not rows:
                    raise ValueError('That sample no longer exists.')
            return {'format': 'declan-voice-samples', 'schema_version': 1, 'name': profile[1],
                    'consent_at': profile[2], 'recogniser_connected': False,
                    'samples': [{'id': row[0], 'audio': base64.b64encode(decrypt(row[1], row[0])).decode(),
                                 'duration': row[2], 'sha256': row[3]} for row in rows]}
        else:
            raise ValueError('Choose an operation and confirm before deleting.')
    return listing()
