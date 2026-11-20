# Changelog

This file records significant repository changes. Historical releases are available in [GitHub Releases](https://github.com/NeoWeb-JP/Declan-2.0/releases); consult each release for its exact changes.

## Unreleased

- Speech (REL-01): optional **local TTS fallback**. Set *Local TTS fallback entity* (for example `tts.piper`) in the Declan 2.0 integration options. When ElevenLabs fails or the daily character limit is reached, and no saved equivalent reply exists, Declan speaks with the local voice instead of going silent. Local audio is cached separately, so it never replaces ElevenLabs audio. Leave the option blank to keep ElevenLabs only.
- Settings → Voice & learning: each speaker now shows a **match rate** (HIS-11): of the recordings VoicePipeline attributed to that speaker and you then reviewed, the share where you kept that speaker. Pending, dismissed, rejected and discarded recordings don't count. It shows "n/a" until there are 5 reviews.
- Settings → Voice & learning: **Learned commands** is back. A refactor had left its code in place but removed it from the page. It lists every learned phrase, however old, with a search box, and shows when and how each was last trained (History, a recording, a successful retry, edited here or imported). Phrases learned before this release show "Learned before training dates were recorded" (#98).
- History: new **Understanding** card (VOI-12). It shows how many spoken or typed requests got the "say it another way" reply in the last 7 days and the three weeks before, the most-missed phrases (marked when since learned), and this week's speaker-ID confidence against the recognised-speaker threshold.
- Voice: the recognised-speaker threshold (VOI-08, default 85%) is now a setting in **Settings → Voice & learning** or `DECLAN_SPEAKER_THRESHOLD`. It controls History speaker labels and duplicate-capture arbitration. Sensitive routine confirmations keep their fixed 85% floor.
- **Fix (data):** 2.13.0 and 2.13.1-rc1 stored the conversations and diagnostics databases inside the release folder (`declan/core/.data`) instead of the shared `.data`, so learned phrases, history, server settings, routines, custom responses and AI settings appeared reset, and changes made on 2.13 would be lost on the next update. Paths are fixed. On first start Declan merges what was done on 2.13 (learned phrases, history, AI spend) back into the shared database and keeps the release-local file as `*.merged-<timestamp>`. Settings changed on 2.13 are not merged automatically; the log lists them.
- Settings: new **Music behaviour** card for reply-first playback and Music Assistant search, so neither needs `declan.env`. A saved value wins; until then the environment variable (or default) applies.
- Music: reply-first playback is now on by default, so "play …" is answered as soon as Home Assistant accepts it and verified in the background. Set `DECLAN_MUSIC_REPLY_FIRST=0` to restore the slower verified-first reply.
- Music: optional `DECLAN_MUSIC_ASSISTANT_SEARCH=1` hands "play X" to Music Assistant's own search on the right speaker or group, bypassing Declan's Spotify search (kept for switching back). "Play X upstairs/downstairs" now parses like "everywhere".
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
