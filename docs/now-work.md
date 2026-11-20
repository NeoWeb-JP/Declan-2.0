# Declan NOW status

[Issue #12](https://github.com/NeoWeb-JP/Declan-2.0/issues/12) is the authoritative requirements and acceptance register. This file is a status summary, not a second requirements source.

## Reviewed 16 November 2026

- **58 of 61 NOW criteria implemented** under the latest owner decisions.
- Source: main `06131cbcfea1467548b8e233d16b7897735ead92`, merged through #172.
- Published stable release: [2.10.1](https://github.com/NeoWeb-JP/Declan-2.0/releases/tag/2.10.1).
- [Main CI #715](https://github.com/NeoWeb-JP/Declan-2.0/actions/runs/43909972466) passes Ubuntu, Windows and browser regression/coverage jobs.
- Jaco confirms all implemented work has already been tested. This is owner-confirmed household acceptance. This review did not install anything or independently query the installed version.

## Current decisions

- Native Home Assistant panel is the management interface. HA owns scripts/automations; Declan owns routing, guarded AI and personality; VoicePipeline owns speaker identity; Music Assistant owns Spotify playback.
- Discovered HA scripts are callable without per-script approval or manual mapping UI (#137). Existing configured aliases/fields remain compatible. The old fail-closed classification/approval requirement in #131 is superseded, not fully implemented.
- Explicit Teach Declan remains available. A sufficiently similar successful retry after a rephrasing prompt can also teach the original phrase (#171), scoped to conversation/device. Changed targets/directions/numbers, ambiguous compounds, cancelled and expired retries do not train; explicit corrections win.
- Recording review covers seven days regardless of status, separate from configurable retention. Other saved interactions appear in a separate collapsed section (#171). Verified IDs attach saved replies; unlinked recordings can be taught from their own VoicePipeline transcript. Missing/loading errors are explicit (#172).
- Five-minute context, 85% recognition threshold, unknown origin isolation and no cross-room followups. First accepted duplicate capture wins.
- Bare Stop stops Music Assistant playback Everywhere. Explicit Stop Routine requests best-effort cancellation and never promises rollback.
- Routine acknowledgements can be immediate while completion/partial/failure verification runs in the background. Saved response pools support Home/Guest/failure editing and bulk JSON input (#169/#170).
- Quiet hours are 23:00–07:00 in HA's timezone. PCM speech is 20% of normal, without changing player volume; music/Sexy Time playback stays exempt. Guarded unsolicited overnight speech allows only safety categories, with approved outputs in HA integration Options. #123 is accepted on the owner's testing confirmation; this review did not independently audit installed direct-TTS callers.
- Spotify categories use a **25-playlist** limit, preserve favourites/exclusions and use approved Music Assistant outputs.

## Remaining NOW implementation

| Criterion | Remaining work |
| --- | --- |
| HIS-11 | Per-speaker match rate. Definition agreed 20 Nov (D1): of the recordings VoicePipeline attributed to a speaker that you then reviewed, the % where you kept that speaker; n/a under 5 reviews. Implemented in #810. |
| REL-01 | Local TTS fallback after the primary provider and cached alternatives fail, kept as written (D2). Implemented in #811 (`local_tts` integration option, own cache identity). |
| VOI-12 (new) | Weekly "not understood" rate and top missed phrases. Summary implemented in #808; the owner sets the target. |
| DEV-01 (new) | "Howzit Declan" wake word and multi-room Spotify on every satellite and EchoLocal Echo Show, with a device inventory. |

REL-08 was re-scoped on 20 Nov (D3) to Declan-managed data and is met. VoicePipeline's own storage is a documented limitation, and live deletion acceptance is a #779 check. #17 was closed on 19 Nov; its open items and the engineering follow-ups are tracked in #802. #98's all-time phrase manager is implemented in #809. #12 stays open until #810 and #811 are merged and retested live.

Historical implementation notes and earlier product decisions are available in Git history. They must not override the current issue register. Homelab operations, predictive heating/EV optimisation and the all-time phrase manager remain deferred.
