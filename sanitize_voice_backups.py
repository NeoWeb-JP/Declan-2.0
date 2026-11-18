"""Explicit maintenance command for retained local voice upgrade snapshots.

Usage: python -m sanitize_voice_backups --data-dir /path/to/.data
No upgrade or application restart is required. External backups and VoicePipeline
storage are outside this command's scope.
"""
import argparse
from pathlib import Path

from state_backup import sanitize_retained_voice_snapshots


def main(argv=None):
    parser = argparse.ArgumentParser(description='Redact local voice audio from retained Declan upgrade snapshots.')
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent / '.data',
                        help='Declan data directory containing upgrade-backups')
    args = parser.parse_args(argv)
    directory = args.data_dir
    if directory.is_symlink() or not directory.is_dir():
        parser.error('Data directory must be an existing regular directory.')
    try:
        count = sanitize_retained_voice_snapshots(directory)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Voice snapshot sanitization failed: {error}\\n')
    print(f'Sanitized {count} retained local voice snapshot database(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
