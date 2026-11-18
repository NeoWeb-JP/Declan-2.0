"""Generate reviewed, hash-locked voice dependencies from downloaded wheels.

Run on the target Linux/Python environment. Does not modify the production lock
until every required wheel has been downloaded and hashed successfully.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

PACKAGES = ('websocket-client==1.9.2', 'cryptography==46.0.3')


def generate(target, *, python=sys.executable, runner=subprocess.run):
    target = Path(target)
    with TemporaryDirectory(prefix='declan-voice-lock-') as directory:
        folder = Path(directory)
        runner([python, '-m', 'pip', 'download', '--only-binary=:all:', '--dest', str(folder),
                *PACKAGES], check=True, timeout=180)
        wheels = sorted(folder.glob('*.whl'))
        if not wheels or any(not item.is_file() for item in folder.iterdir()):
            raise ValueError('Dependency download did not produce only wheels.')
        packages = {}
        for wheel in wheels:
            # Wheel filenames encode distribution and version before the Python/ABI tags.
            parts = wheel.name[:-4].split('-')
            if len(parts) < 5:
                raise ValueError('Unexpected wheel filename.')
            name, version = parts[0].replace('_', '-').lower(), parts[1]
            key = (name, version)
            if key in packages:
                raise ValueError('Duplicate wheel distribution/version.')
            packages[key] = hashlib.sha256(wheel.read_bytes()).hexdigest()
        for package in PACKAGES:
            name, version = package.split('==')
            if (name, version) not in packages:
                raise ValueError(f'Missing requested wheel: {package}')
        # Include all transitive dependencies returned by pip, pinned and hashed.
        lines = ['# Generated for the target platform; review before committing.']
        for (name, version), digest in sorted(packages.items()):
            lines.append(f'{name}=={version} --hash=sha256:{digest}')
        candidate = target.with_name(target.name + '.candidate')
        candidate.write_text('\\n'.join(lines) + '\\n', encoding='utf-8')
        return candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'requirements-web-voice.txt')
    args = parser.parse_args(argv)
    try:
        candidate = generate(args.output)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Unable to generate dependency lock: {error}\\n')
    print(f'Review and test {candidate} before replacing {args.output}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
