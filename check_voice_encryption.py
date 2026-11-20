"""Read-only readiness checks before enabling local voice sample encryption."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

from cryptography.exceptions import InvalidTag
from declan.voice.voice_audio_crypto import _aesgcm, decrypt, is_encrypted


def inspect(database):
    """Validate key, ciphertext and database without writing or migrating."""
    _aesgcm()  # Require a configured 256-bit key and installed crypto runtime.
    path = Path(database)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Choose an existing regular local voice database.')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise ValueError('Voice database failed integrity check.')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='samples'").fetchone():
            raise ValueError('Voice database has no samples table.')
        plaintext = encrypted = 0
        for sample_id, audio in db.execute('SELECT id, audio FROM samples'):
            if not isinstance(audio, bytes):
                raise ValueError('Voice database contains an invalid audio value.')
            if is_encrypted(audio):
                decrypt(audio, sample_id)
                encrypted += 1
            else:
                plaintext += 1
    return {'encrypted': encrypted, 'plaintext': plaintext}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.database)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, InvalidTag) as error:
        parser.exit(1, f'Voice encryption readiness check failed: {error}' + chr(10))
    print(f"Encrypted samples: {result['encrypted']}; plaintext samples: {result['plaintext']}")
    if result['plaintext']:
        print('Migration required with backend stopped before enabling encrypted reads.')
        return 2
    print('Local voice sample encryption readiness check passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
