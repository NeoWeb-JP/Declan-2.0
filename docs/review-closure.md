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

## Environment documentation audit acceptance

Reviewed against merged #751 main `c88bc9a`. The README split, installation
guide, changelog, architecture guide, environment reference and safe example
file exist. The environment audit covers production literal reads and all
`configuration.FIELDS` indirect fallbacks, with each inventoried name mapped to
default/override behavior and regression evidence. Consumer review corrected
stale claims about saved-setting environment fallback and one-time routine
registry migration. Explicit blank environment values are preserved by the
configuration layer and interpreted by consumers, not universally defaulted.

All 119 environment-named tests passed on Ubuntu/Python 3.12, followed by 37
combined documentation, precedence, registry, TTS, visitor, media-agent and
pipeline tests. All five GitHub gates on merged #751's head succeeded. This
supports completing the original documentation/default-audit implementation
items for the supported configuration surface. It does not prove arbitrary
dynamic names, every possible invalid input, third-party HA options or deployed
settings. Changes to supported settings must update the behavior matrix and
regressions. Live privacy and deployment acceptance stays in #496.

## Main dispatch contract

The turn-dispatch result validates reply/status metadata and normalizes known
legacy outcome values to `Outcome` before response preparation. Unknown outcome
values are rejected rather than allowed into fallback or response decisions;
`None` remains the unmatched-turn sentinel. This validation occurs after handler
execution and cannot undo actions already performed. Providers must still
validate before dispatching actions.

The `routine_status` field is explanatory display text produced by Stop/routine
handlers and forwarded to history/HTTP. It is not the execution-state enum:
`outcome` and typed action evidence carry those decisions. Preserve free-form
status wording and do not infer completion from it. The same distinction applies
to `CommandResponse` and `TurnResponse`. Internal stage context fields still
contain broadly typed objects, so this does not complete the repository-wide
typed-contract finding or remove the live server dependency facade.

`tests/test_turn_dispatch_outcome_contract.py` covers all known enum members,
unknown/malformed outcomes, unmatched turns and display-status separation.
Extraction tests use real enum values instead of the invalid mock status `ok`.

## Internal stage outcomes

Direct, routine, local-fallback and response-preparation result dataclasses also
normalize known outcome values to `Outcome`, preserve `None`, and reject unknown
or malformed outcomes at construction. This keeps the execution discriminator
typed across the whole stage chain rather than only at the final dispatch
boundary. The contract matrix exercises every enum member for all four stages,
rejection of arbitrary success-like strings and frozen outcome identity.

This does not interpret routine display text as execution state, validate all
context payloads, or replace external provider parsing. Invalid results are
rejected after their producing stage has run, not before its actions. Existing
wire adapters continue to emit strings. The original typed-outcome finding still
requires final inventory/disposition of provider and compatibility boundaries;
remaining `object` context annotations alone are not evidence of string-based
execution decisions.

## Typed outcome audit disposition

Baseline: merged #754 main `84ba32a`. The original replace-stringly-typed-outcomes
implementation scope is satisfied for the reviewed command/turn execution paths:
execution discriminators use enums and result dataclasses. Keep the following
intentional boundaries; removing their strings would break external contracts.

| Boundary | Typed internal contract | Intentional external/compatibility behavior |
| --- | --- | --- |
| Timer, routine, music, information providers | `ExecutionResult`, `Outcome`, `InformationResult` | Legacy pairs/triples are validated by `local_outcome_contracts`, `music_provider_result` and `InformationResult.coerce` |
| Ordered action dispatch/readback | `DispatchResult`, `ActionStatus`, `ActionResult` | Legacy dispatcher tuples are coerced; action status strings are emitted by wire adapters |
| Script receipts/reports/traces | `BackgroundReceiptResult`, `ScriptProviderResult`, trace enums | Exact HTTP/payload correlation is parsed at ingress; reported/accepted is distinct from verified completion |
| Model completion | `ModelResponseResult` | Provider status and output strings are parsed before plan decoding; incomplete results cannot become completed plans |
| Confirmation | `ConfirmationDecisionResult`, `ConfirmationTurnResult` | The active preflight calls `confirmation_turn_result`; the old string-comparing function remains a legacy API |
| Turn stages and final response | `Outcome` across all stage result dataclasses and `TurnResponse` | `None` denotes no outcome; wire adapters emit strings; routine status is explanatory text |
| Inventory, STT and updater | `InventoryResult`, `TranscriptionResult`, `UpdateStatusResult` | Existing public JSON/text responses remain stable; unknown states retain conservative interpretation |
| Diagnostics and retained history | Serialized strings from typed results | Metrics classify bounded stored/wire labels; they do not authorize execution |

Verification includes provider identity retention, malformed and hostile legacy
input rejection, dependency skips, acknowledgement-only results, unknown status
handling and typed-to-wire compatibility. Broad `object` annotations for context
payloads and the mutable session-response mapping remain architecture concerns,
not evidence that execution outcomes still depend on arbitrary strings. This
disposition does not assert strict typing of every payload or eliminate
compatibility APIs. Any newly discovered internal string-based execution decision
needs a specific regression and reopens that scope; do not keep this checkbox
open solely because external JSON and human-readable detail remain strings.
