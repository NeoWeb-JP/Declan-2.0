# Changelog

This file records significant repository changes. Historical releases are available in [GitHub Releases](https://github.com/NeoWeb-JP/Declan-2.0/releases); consult each release for its exact changes.

## Unreleased

- Music: reply-first playback is now on by default, so "play …" is answered as soon as Home Assistant accepts it and verified in the background. Set `DECLAN_MUSIC_REPLY_FIRST=0` to restore the slower verified-first reply.
- Voice: polite requests are understood locally, so "can you turn on the office light", "turn on the office light please" and "... my bru" no longer fall through to the AI fallback or a rephrase prompt (#801).
- Fix: one lighting command joined to one music command ("turn on the office lights and play country music everywhere", either order) now runs both actions and reports each result (#300, #799).
- Voice encryption: optional key IDs (`DECLAN_VOICE_AUDIO_KEY_ID`), retired keys (`DECLAN_VOICE_AUDIO_PREVIOUS_KEYS`) and `migrate_voice_audio --rewrap` for key rotation. Nothing changes until a key ID is set (#800).
- Fix: the Home Assistant integration no longer reads `manifest.json` or imports the Wyoming client on the event loop, which removes the "blocking call" warnings from the HA log.
- Updater: a failed install now records which stage failed (for example `install-dependencies`). The step appears in the service log and in the Updates panel; command output is never logged.
- Fix: the voice dependency lock now includes the Python 3.11 `cffi` wheel hash, so staged installs succeed on Python 3.11 hosts (the 2.13.0 release failed hash verification there).
- Documentation reorganised into a concise entry-point README, installation instructions, architecture overview, and configuration reference.
- P2 CI maintenance: Dependabot, Hassfest, and advisory Python quality and security checks.

## Release history

See [GitHub Releases](https://github.com/NeoWeb-JP/Declan-2.0/releases) for versioned release notes. This changelog intentionally does not reconstruct undocumented release histories.
