# P1 reliability changes for issue #17

## Capture arbitration

The first completed transcription claims an utterance immediately, without a fixed arbitration sleep. Later copies are checked against a bounded 120-second ledger using capture start/end times, strong overlap and a conservative command key. Generic `turn on/off the light(s)` variants match; unrelated music titles and opposite actions remain distinct. Confidently identified different speakers remain separate. Repeating a command after the first capture finishes is allowed.

This chooses the first usable transcript rather than waiting to rank satellites by loudness. A louder satellite whose transcription finishes later is suppressed. Capture clocks must be synchronised; requests without valid capture metadata retain normal handling. Capacity is 4096 unexpired claims; additional metadata-bearing captures are suppressed at capacity rather than evicting live claims and risking duplicate actions. This is duplicate suppression, not speaker authorisation.

The HA conversation bridge leaves the speech response empty for suppressed captures and successful silent stop commands. It does not populate speech with an empty string. The pipeline can therefore finish without TTS. Verify this on the installed satellite/HA versions during live testing.

## HA inventory

Device discovery reads a projection of relevant domains and attributes through `/api/template`. Music discovery reads only media players and Assist satellites, with the registry metadata needed for automatic room/player mapping. Neither discovery path downloads `/api/states` or serialises all attributes. Playback/action verification still uses individual live entity endpoints.

Reads use sorted pages of 200 entities, a 1 MiB page limit, at most 20,000 relevant entities and a ten-second overall paging budget (up to four seconds per request). Invalid, oversized, incomplete, duplicate or changing-count pages return unavailable instead of a partial inventory. No stale state cache is used for action decisions. The five-second blacklist poll uses the same media-only projection, and still avoids HA calls if there are no blocked tracks.

## Concurrency and timers

Both the standalone HTTP server and ingress proxy allow at most 16 request threads. Excess connections receive HTTP 503 with `Retry-After: 1`. Handler completion and failures release capacity. The ingress app version is 1.0.2 and needs its normal HA app update to receive the limit.

Spotify token refresh and credential replacement are serialized. Searches retain a local token snapshot; a late 401 from an older token cannot clear a newer token.

Timer schema creation runs once per database file, with WAL enabled. Idle alarm checks use a SELECT and never acquire a write transaction. A due alarm is claimed by a conditional update, so concurrent pollers cannot claim the same deadline twice. Timer status queries also avoid write transactions.

Movie app HOME/app commands are sent together to HA with `delay_secs: 2`, removing the Python sleep between those commands. The configured remote integration must honour HA's command-list pacing. The existing seven-second projector readiness wait remains.

## Spotify and speech settings

`DECLAN_SPOTIFY_MARKET` sets the two-letter country code for Spotify search. It defaults to `GB` for compatibility; for example use `ZA` for South Africa. Quoted title/artist search fields escape quotes and backslashes.

OpenAI STT waits at most eight seconds (three seconds to connect). HTTP errors, timeout, invalid JSON and empty transcripts trigger one local fallback attempt with a twelve-second budget. The bounded PCM buffer is replayed once, retaining original capture times and any local speaker identity. Cancellation is propagated, and recursive selection of a Declan OpenAI wrapper is rejected.

In Declan's voice settings, set **Local STT fallback entity** to an installed local `stt.*` provider. If blank, the enabled/configured Wyoming speaker bridge is used. If neither is available, or the fallback also fails, the STT result is an error. This does not silently choose an unrelated provider or change the selected HA pipeline. Browser recordings use their selected HA pipeline, so this fallback also applies when that pipeline uses Declan OpenAI STT.

## Validation

Regression coverage includes delayed plural transcripts, opposite commands and repeat commands; silent bridge responses; real HTTP overload/recovery; template rendering with native datetime attributes; complete/invalid/oversized paging; concurrent token refresh and stale 401s; read-only timer polling and concurrent alarm claims; and cloud failure with local audio replay.

Live checks still needed: two satellites hearing the same command, a large HA installation, remote command-list pacing, and local STT fallback on the actual HA host. No live household actions are run by the regression suite.
