# Issue 17 closure evidence

Baseline: main `9a36718` (merged PR #746), reviewed 19 November 2026.
This record distinguishes implemented boundaries from outstanding work. It does
not establish deployed configuration, migration or Home Assistant acceptance.

## Batch 2: remaining external evidence

Local sample encryption, explicit legacy migration and retained-snapshot
sanitization are implemented. PR #746 ensures a damaged voice database does not
prevent cleaning later regular databases, while incomplete cleanup still fails.
Verify the deployed key, stopped-service migration and cleanup separately.
External backups are outside the local cleanup command.

The accessible `NeoWeb-JP/VoicePipeline-Development` repository is empty. Shared
sample encryption requires the authoritative service source/version, recording
and backup locations, key ownership and recovery requirements. Do not copy its
samples into Declan or claim its storage is protected by Declan's local key.

The global `declan_two_assist_reply` listener is removed and repository Python
sources have no publishers. External HA automations/custom integrations require
an installed-configuration inventory and verification of any replacement history
path. Keep that migration checkbox open until evidence is recorded.

## Batch 3: mutable state

`SessionStore` owns session entries, recall and a shared lock; `RoutineCooldown`
owns attempts under its own lock. `MusicRuntimeState` owns the Spotify token and
its lock, playback handoff and skip throttles. The old bare global names are not
an accurate description of current ownership. Regression evidence lives in
`test_session_store.py`, `test_routine_cooldown.py` and
`test_music_runtime_state.py` under `tests/`.

Process-default owners still exist (`DEFAULT_SESSION_STORE`, the server runtime
singletons and music's `RUNTIME`). The original global-state/package checkbox
therefore remains incomplete. Before a broader change, identify a concrete
isolation or lifecycle requirement, enumerate consumers and test independent
owners. Moving files into a package alone does not remove shared state.

## Batch 3: legacy names

Retain the following compatibility paths for existing installations:

| Reference | Current purpose | Evidence |
| --- | --- | --- |
| `jarvis_speaker` | Alias/fallback for older transcript producers; canonical field is `speaker` | `speaker_models.py`, `tests/test_speaker_transcript_identity.py` |
| `jarvis_voice_cache` | Reuses existing paid audio; new installs use `declan_voice_cache` | `voice_cache_location.py`, `tests/test_voice_cache_location.py` |
| Legacy TTS entity prefixes | Rejects self-recursive voice-manager providers | `config_flow.py`, `tts.py` |
| `declan_local` / `jarvis_local` | Discovers older independent media-search agents and excludes Declan itself | `media_search_agents.py`, `tests/test_media_search_agents.py` |

Integration module paths in this table are under `custom_components/declan_two/`;
`media_search_agents.py` is a backend module. These references should not be
deleted by a blind rename. This is an engineering recommendation for the listed
adapters, not approval to close the repository-wide rename finding. Any adapter
retirement needs an inventory, migration and regressions for existing users.

## Batch 3: speaker metadata and credentials

An explicit `SpeakerMetadata` snapshot and JSON projection already exist, but
the HA STT boundary still uses `SpeakerTranscript(str)`. String transformations
still lose its attributes; `tests/test_speaker_metadata_boundary_contract.py`
explicitly demonstrates this. Keep the transport checkbox open. Select a
supported HA metadata channel only after checking the deployed HA version and
its STT-to-conversation contract; test simultaneous speakers, plain strings,
normalization and missing metadata before removing the compatibility carrier.

The STT API key is still retained in config-entry options by `config_flow.py`.
Reusing HA OpenAI credentials needs a supported configuration contract and a
decision about the distinction between backend planning and STT credentials.
Do not read another integration's private options as a speculative fix.

Household-specific configuration and personalisation remain a separate audit.
Issue #12's owner decisions, including Edd pronunciation and routine semantics,
must be preserved. No original Batch 3 parent checkbox is completed by this
record alone.

## Household audit after PR #747

At main `4f643c0`, the ingress default is loopback, not the original household
IP. Backend helper targets in `household_entities.py` have validated saved or
environment overrides; their legacy defaults preserve existing installations.
`tests/test_household_entities.py` covers overrides, domain validation and guest
service payloads. The example scripts under `home_assistant/` still contain
fixed bedroom lights, projector and guest-helper targets. Those templates need
an explicit installation-configuration design and action/readback tests before
the original household checkbox can be completed. Do not silently change their
device targets on an installed household.

The Edd-to-Ed TTS pronunciation in `custom_components/declan_two/voice_text.py`
is required by Issue #12 and should be retained. This does not dispose of other
personalisation or certify every configuration file.

## Response payload ownership

Normal and retry-cancellation results detach their session payload on
construction and serialization, including nested values. Caller-owned input,
wire output and metadata callbacks cannot mutate retained payloads through
shared aliases. `tests/test_response_payload_isolation.py` covers those paths
and dataclass replacement. This is boundary isolation, not recursively immutable
storage: direct mutation through `session_response` remains possible, and
`routine_status` remains a compatibility string. The broader typed-outcome
inventory and acceptance decision remain open.

## Batch 4: CI, documentation and observability

At merged #748 main `167bfae`, `.github/workflows/python-quality.yml` has a
blocking repository mypy step, followed by a dependency inventory and a blocking
guard that permits only missing Home Assistant runtime imports. This is not
strict typing: `mypy.ini` skips following imports and checks untyped function
bodies. The original evaluate/enforce-mypy task is implemented for that stated
scope; expanding strictness is a separate decision. All five workflow checks on
#748's code commit `c0d2f0f` report success, including Python quality, regression,
browser, HACS and encryption-lock verification.

README already links separate installation, changelog, architecture, environment
and example configuration documents. The repository-wide environment-name
inventory is tested, but inventory coverage is not proof of every unset, blank
and invalid default. Keep the broader defaults audit open until each setting
has recorded behavior and safety-relevant regression coverage.

`declan_logs.py` provides a bounded structured log feed with redaction;
`http_response_transport.py` emits route/status events, and
`diagnostic_metrics.py` aggregates bounded route/stage counts, errors and
latencies without private payload labels. The historical "print only" finding
is stale. These implementations do not establish an external monitoring service,
alert delivery or live household acceptance. Regression evidence is in
`tests/test_declan_logs.py` and `tests/test_diagnostic_metrics.py`.

The operational logging regression now sets and restores its logger level
explicitly. It must pass in isolation without relying on another test importing
the server to initialize logging.
