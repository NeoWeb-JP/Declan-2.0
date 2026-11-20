"""One-time, explicit migration of legacy plaintext local voice samples.

Run with DECLAN_VOICE_AUDIO_KEY configured and the backend stopped:
python -m migrate_voice_audio --database /path/to/.data/voice-profiles.sqlite3
Do not store the key beside the database or in upgrade snapshots.

Key rotation: configure the new DECLAN_VOICE_AUDIO_KEY/DECLAN_VOICE_AUDIO_KEY_ID,
list the old key in DECLAN_VOICE_AUDIO_PREVIOUS_KEYS, then run with --rewrap to
re-encrypt every sample under the new key.
"""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

from declan.voice.voice_audio_crypto import encrypt, decrypt, is_encrypted, _aesgcm


def migrate(path, *, rewrap=False):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Choose an existing regular local voice database.')
    _aesgcm()  # Verify key and crypto runtime before obtaining a write lock.
    with closing(sqlite3.connect(path, timeout=5)) as db:
        db.execute('PRAGMA secure_delete = ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('Voice database failed integrity check.')
            rows = db.execute('SELECT id, audio FROM samples').fetchall()
            # Authenticate every encrypted sample before writing any plaintext rows.
            # This also prevents a wrong key from causing partial migration work.
            for sample_id, audio in rows:
                if not isinstance(audio, bytes):
                    raise ValueError('Voice database contains an invalid audio value.')
                if is_encrypted(audio):
                    decrypt(audio, sample_id)
            for sample_id, audio in rows:
                if not is_encrypted(audio):
                    db.execute('UPDATE samples SET audio = ? WHERE id = ?', (encrypt(audio, sample_id), sample_id))
                elif rewrap:
                    db.execute('UPDATE samples SET audio = ? WHERE id = ?',
                               (encrypt(decrypt(audio, sample_id), sample_id), sample_id))
            # Verify the updated rows inside the same transaction before committing.
            for sample_id, audio in db.execute('SELECT id, audio FROM samples'):
                decrypt(audio, sample_id)
            db.commit()
            # Rewrite free pages to reduce recoverable plaintext from the live DB.
            db.execute('VACUUM')
        except Exception:
            db.rollback()
            raise
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Encrypt legacy local voice samples in place.')
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--rewrap', action='store_true',
                        help='Re-encrypt every sample under the current key (key rotation).')
    args = parser.parse_args(argv)
    try:
        count = migrate(args.database, rewrap=args.rewrap)
    except (ValueError, RuntimeError, sqlite3.Error) as error:
        parser.exit(1, f'Voice migration failed: {error}\\n')
    print(f'Verified/encrypted {count} local voice sample(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
