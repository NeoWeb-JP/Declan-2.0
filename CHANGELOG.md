# Changelog

This file records significant repository changes. Historical releases are available in [GitHub Releases](https://github.com/NeoWeb-JP/Declan-2.0/releases); consult each release for its exact changes.

## Unreleased

- Updater: a failed install now records which stage failed (for example `install-dependencies`). The step appears in the service log and in the Updates panel; command output is never logged.
- Fix: the voice dependency lock now includes the Python 3.11 `cffi` wheel hash, so staged installs succeed on Python 3.11 hosts (the 2.13.0 release failed hash verification there).
- Documentation reorganised into a concise entry-point README, installation instructions, architecture overview, and configuration reference.
- P2 CI maintenance: Dependabot, Hassfest, and advisory Python quality and security checks.

## Release history

See [GitHub Releases](https://github.com/NeoWeb-JP/Declan-2.0/releases) for versioned release notes. This changelog intentionally does not reconstruct undocumented release histories.
