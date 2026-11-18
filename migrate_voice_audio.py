"""One-time, explicit migration of legacy plaintext local voice samples.

Run with DECLAN_VOICE_AUDIO_KEY configured and the backend stopped:
python -m migrate_voice_audio --database /path/to/.data/voice-profiles.sqlite3
Do not store the key beside the database or in upgrade snapshots.
"""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

from voice_audio_crypto import MAGIC, encrypt, decrypt, _key


def migrate(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Choose an existing regular local voice database.')
    _key()
    with closing(sqlite3.connect(path, timeout=5)) as db:
        db.execute('PRAGMA secure_delete = ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('Voice database failed integrity check.')
            rows = db.execute('SELECT id, audio FROM samples').fetchall()
            for sample_id, audio in rows:
                if audio.startswith(MAGIC):
                    decrypt(audio, sample_id)  # Fail on a wrong key before changing anything.
                else:
                    db.execute('UPDATE samples SET audio = ? WHERE id = ?', (encrypt(audio, sample_id), sample_id))
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
    args = parser.parse_args(argv)
    try:
        count = migrate(args.database)
    except (ValueError, RuntimeError, sqlite3.Error) as error:
        parser.exit(1, f'Voice migration failed: {error}\\n')
    print(f'Verified/encrypted {count} local voice sample(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
