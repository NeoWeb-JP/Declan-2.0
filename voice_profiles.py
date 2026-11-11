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
from contextlib import closing, contextmanager

DATABASE = Path(__file__).resolve().parent / '.data' / 'voice-profiles.sqlite3'


@contextmanager
def database():
    DATABASE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with closing(sqlite3.connect(DATABASE, timeout=2)) as db, db:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('PRAGMA secure_delete = ON')
        db.execute('CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, name TEXT NOT NULL, consent_at REAL)')
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
    return {'profiles': profiles, 'recogniser_connected': False,
            'notice': 'Samples stay on this server. They do not change speaker matching yet. '
                      'Only add your own voice with consent. Existing local upgrade backups may retain deleted samples.'}


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
            db.execute('INSERT INTO profiles VALUES (?, ?, ?)', (secrets.token_hex(12), name, time()))
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
        if operation == 'delete_profile' and body.get('confirm') is True:
            db.execute('DELETE FROM profiles WHERE id = ?', (profile[0],))
        elif operation == 'save_sample':
            if db.execute('SELECT count(*) FROM samples WHERE profile = ?', (profile[0],)).fetchone()[0] >= 20:
                raise ValueError('Review or remove samples before adding more (20 per person).')
            digest = hashlib.sha256(audio).hexdigest()
            if db.execute('SELECT 1 FROM samples WHERE profile = ? AND digest = ?', (profile[0], digest)).fetchone():
                raise ValueError('This recording has already been saved.')
            db.execute('INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?)',
                       (secrets.token_hex(12), profile[0], audio, duration, digest, time()))
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
                    'samples': [{'id': row[0], 'audio': base64.b64encode(row[1]).decode(),
                                 'duration': row[2], 'sha256': row[3]} for row in rows]}
        else:
            raise ValueError('Choose an operation and confirm before deleting.')
    return listing()
