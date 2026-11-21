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

## NOW status, 20 November 2026

[#12](https://github.com/NeoWeb-JP/Declan-2.0/issues/12) closed on 20 Nov. Every NOW criterion is implemented and merged; household acceptance runs through #779. Follow-ups are tracked in #802.

| Criterion | Status |
| --- | --- |
| HIS-11 | Per-speaker match rate (D1: of reviewed recordings VoicePipeline attributed to a speaker, the % kept; n/a under 5 reviews). Merged in #810. |
| REL-01 | Local TTS fallback after the primary provider and cached alternatives fail (D2). Merged in #811 (`local_tts` option, own cache identity). |
| REL-08 | Re-scoped (D3) to Declan-managed data and met. VoicePipeline's own storage is a documented limitation; live deletion acceptance is a #779 check. |
| VOI-12 (new) | Weekly "not understood" rate and top missed phrases. Merged in #808; the owner sets the target. |
| DEV-01 (new) | "Howzit Declan" wake word and multi-room Spotify on every satellite. Met: one wake word per satellite; music and wake word work on all of them. |

### DEV-01 device inventory

| Room | Device |
| --- | --- |
| Kitchen | Guition 10.1 inch (Echo Show 8 Gen 1 and 2) |
| Lounge | Guition 10.1 inch (Echo Show 8 Gen 1 and 2) |
| Master Bedroom | Guition 10.1 inch (Echo Show 8 Gen 1 and 2) |
| Utility Room | Sunton 7 inch (Echo Show 5 Gen 1) |

#17 was closed on 19 Nov. #98's all-time phrase manager and provenance are implemented in #809. The D5 refactor is complete (#824, #831, #832). Future work, including latency targets (FUT-14) and the parked Echo Show dashboard, is tracked in the FUTURE register #834.

Historical implementation notes and earlier product decisions are available in Git history. They must not override the current issue register. Homelab operations and predictive heating/EV optimisation remain deferred and are listed in #834.
