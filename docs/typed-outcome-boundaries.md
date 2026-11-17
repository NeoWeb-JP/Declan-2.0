# Typed provider and dispatch outcomes

The active command registry consumes frozen `ExecutionResult` objects with validated
`Outcome` members. HTTP responses, history records and existing public Python APIs
continue to expose ordinary strings through explicit compatibility adapters.

The follow-up to merged PR #250 removes the remaining music playback and feedback
round trips through the public tuple APIs. Music provider branches construct typed
results directly. Lighting now has `set_lights_result()` and
`handle_light_request_result()` through the registry and routine follow-ons;
`set_lights()` and `handle_light_request()` retain their existing tuple contracts.
The registry accepts both typed results and legacy injected lighting pairs.

Routine selection and cancellation now produce typed results directly. Script
execution, background receipts and correlated trace evidence have typed provider
cores. Their public `execute()`, `enqueue()` and `completion_from_trace()` adapters
retain legacy triples, including optional receipt and trace details. No provider
request is repeated to obtain or convert its outcome.

Timer execution already uses the typed `handle_result()` core, with `handle()` as
the legacy adapter. Stop and origin-specific Stop retain their previous typed
providers. Incoming Home Assistant outcome strings are validated at the boundary;
external protocol values such as script `success` and trace `finished_unverified`
remain external vocabulary and map to the existing internal outcomes.

Mapped routine execution also exposes `run_custom_routine_result()`,
`run_routine_result()`, `routine_completion_result()` and `run_sexy_time_result()`.
These produce typed execution results plus optional status detail. Their original
entrypoints preserve plain-string triples. The bedroom routine consumes typed
music playback/control directly; mapped execution consumes typed correlated
completion directly. `chained_outcome_result()` validates and combines enums,
with `chained_outcome()` retaining its plain-string compatibility contract.

Device status exposes `describe_result()` with a frozen `DeviceStatusResult`
containing an `ExecutionResult` and optional follow-up target. The registry
accepts this model and validates legacy injected triples. `describe()` retains
its original string triple. Media search exposes `search_media_result()` through
the active registry, preserving typed result identity; `search_media()` retains
its original pair/None contract. Provider resolution, search routing and response
decoration retain their previous behavior.

Auxiliary actions expose `launch_movie_app_result()`, `start_dinner_result()`,
`guest_assignment_result()` and `set_switch_as_light_result()`. Movie launch uses
a frozen `MovieLaunchResult` with its own status enum: `sent` means dispatch was
accepted, not verified completion. The other providers use `ExecutionResult`;
`Outcome.SKIPPED` preserves the existing quiet-hours announcement outcome.
Mapped movies and lighting consume the typed auxiliary cores directly; guest
dispatch adapts its typed result at the existing response boundary. All original
public status/detail or reply/outcome APIs retain plain strings and unmatched
switch results remain `None`.

Stop, information and device response orchestration use a frozen `CommandResponse`
that preserves the original `ExecutionResult`, including action evidence, plus
routine status, information context or device target. Their earlier response
helpers remain compatibility entrypoints. Early preview/timer selection retains
typed results and preview precedence; legacy previews are validated on entry.
Session success vocabulary uses `Outcome` members while accepting existing string
callers. HTTP outcome metadata and history persistence explicitly convert enum
values to plain strings at those external boundaries.

Routine follow-on execution and dispatch expose `execute_result()` and
`execute_follow_on_result()`, returning `CommandResponse` with typed lighting
context and original routine voice results. Combined execution preserves both
routine and follow-on action evidence. No-follow-on dispatch retains the original
execution object. Routine response decoration consumes the typed original voice
result while still accepting legacy pairs. Lighting response dispatch exposes
`dispatch_lighting_response()` and retains typed execution identity and scoped
follow-up context. Existing follow-on and lighting tuple APIs remain available.

Guarded fallback exposes `guarded_openai_fallback_result()` with a frozen
`FallbackResponse`: the original typed execution plus separately redacted
diagnostic action steps. `dispatch_fallback_result()` and
`resolve_fallback_result()` preserve execution identity through authorization and
eligibility gating, appending validated steps once. Legacy provider triples are
validated before appending actions. The public server fallback triple and older
dispatch/orchestration entrypoints remain compatible. Accepted local results,
including empty replies, still block fallback before authorization is evaluated.

Sensitive confirmation uses `ConfirmationDecision` and frozen evaluation,
session-decision and turn-result models. The gate exposes `evaluate_result()`;
typed decision and turn orchestration retain those models through the execution
gate. Legacy gate/decision/turn APIs preserve their existing tuples. Confirmation
HTTP/history outcomes use explicit `Outcome` members converted to plain strings.
Origin binding, 30-second expiry, one-shot consumption and non-Assist bypass
retain their previous semantics.

Conversational retry cancellation exposes `cancel_retry_result()` with a frozen
`RetryCancellationResult`, retaining typed cancellation execution, session
metadata and persistence status. Its wire adapter preserves plain outcomes,
silent cancellation and nonfatal history errors. Roast response and roast/guest
dispatch expose typed result entrypoints, preserving result/action identity,
roast-before-guest priority and single execution. Legacy injected pairs are
validated at that dispatch boundary; public APIs retain their existing mappings
or tuples.

Final response composition exposes `compose_turn_result()` with a frozen
`TurnResponse`, validating outcomes before session/composition changes and
retaining `None` for unhandled chat. `persist_turn_result()` uses this response's
outcome and routine status as authoritative values, preserving session, retry,
training and history mutations in the returned typed response. Explicit wire
adapters retain plain outcomes and extra metadata; original mapping-based
composition and persistence APIs remain compatible.

Information providers expose `home_temperatures_result()`,
`forecast_reply_result()` and `handle_result()`. A frozen `InformationResult`
retains typed execution and validated weather/time category through the registry,
including action evidence during decoration. Routine previews expose typed core
and dispatch entrypoints without executing routines. Their original public pair/
triple APIs remain compatible. The active lighting-result marker now retains the
lighting `ExecutionResult` instead of rebuilding a reply/outcome pair.

Mapped routine action evidence uses frozen `RoutineActionEvidence` and a separate
`RoutineActionStatus` enum covering all ten existing provider statuses. Its
bounded parser preserves the 200-row cap, 240-character text limits, optional
required flags and filtering behavior. Mapped custom execution and correlated
completion consume the typed evidence; legacy `routine_action_results()` and
response action lists explicitly emit ordinary string mappings. Only confirmed
and already-set evidence count as completed; requested/planned states remain
distinct and cannot verify a claimed success.

Discovered-script providers use a frozen `ScriptActionEvidence` report with typed
routine action steps and an independent required-step completion flag. Its
diagnostic projection retains the existing nine statuses (excluding planned),
200-row cap, text bounds and narrow field set. Required-step verification still
examines the full supplied list, including failures after the output cap, and
preserves existing required-flag/non-list behavior. The provider consumes this
typed report before emitting plain action mappings; unknown required statuses
cannot verify reported success. Explicit outcome mappings also use enums.

Lighting and switch-as-light providers construct frozen `LightingActionEvidence`
with a dedicated six-status enum, explicitly projecting ordinary mappings into
their existing action-results sinks. Planned, skipped and uncertain evidence
remain distinct from confirmed/already-set completion. Lighting context and
routine follow-on entity selection accept typed or legacy evidence with stable
deduplication; scope, preview and count guards remain in place. Existing text and
optional-field output are preserved without introducing new truncation limits.

Movie launch action rows use frozen `MovieActionEvidence`, retaining the existing
sent/skipped/failed/unverified vocabulary and exact plain mapping shape.
`action_evidence_to_wire()` explicitly serializes verified, routine, lighting and
movie evidence at shared conversation-response and direct history boundaries.
Mixed batches preserve legacy JSON rows and extra fields; legacy-only containers
retain their existing behavior. Conversion does not mutate typed input rows.
History failures retain their existing nonfatal response behavior.

Active requests and lighting follow-ons use `ActionEvidenceBuffer`. Provider
append/extend adapters retain typed evidence in that accumulator while ordinary
list callers continue receiving legacy mappings. Mapped/discovered routines,
lighting, switches and movie evidence remain typed until explicit serialization.
Context preparation, retry state, general decoration and optional dinner-music
feedback read typed fields without converting statuses to strings. Mixed injected
legacy rows remain supported, including transfer to ordinary-list callers.

Fallback diagnostic rows use frozen `FallbackActionEvidence`, retaining verified
action statuses and the AI-generated marker. Detail redaction is applied when the
model is constructed, so disabled details are absent even before serialization.
Typed accumulation retains these rows; ordinary lists and the public fallback
triple receive the same plain diagnostic mappings as before. External routine
history events retain typed parsed evidence until direct history serialization.

## Compatibility audit

| Boundary | Retained contract |
| --- | --- |
| Public music, timer, lighting, preview and information helpers | Original pair/triple or `None` adapters around typed cores |
| Public mapped/discovered routine execution | Original reply/outcome/status triples |
| Final HTTP responses and stored history | Plain outcome/status strings and existing extra metadata |
| Legacy list evidence callers | Original mapping rows and order, including mixed injected rows |
| Fallback diagnostics | AI-generated marker and opt-in detail field; no verification promotion |
| External routine history events | Bounded external outcome/status text remains compatible; it is persisted rather than used as an internal execution decision |

Home Assistant background jobs now use `RoutineJobOutcome` for state transitions
and frozen `RoutineJobSummary` values for script-response summaries. The active
dispatch path consumes the typed summary directly; `summarize_result` remains a
mapping adapter. Storage and HTTP boundaries retain plain strings, bounded step
projections, correlation failures, reason filtering, and interrupted-job behavior.
Reported script success is still distinct from verified device execution.

Trace classification now returns frozen `TraceExecution` values with a dedicated
seven-value `TraceOutcome` enum. Audit report serialization preserves the original
status vocabulary, timestamp conversion, step bounds and failure precedence.
`lookup_result_typed` returns a frozen `ScriptTraceResult` directly from the shared
classifier, without building and reparsing an audit report. The HTTP endpoint and
background-job fallback consume that typed result; `lookup_result` retains the
original mapping API. Missing or ambiguous contexts remain unverified, and a
finished trace never establishes device success.

Trace collectors now retain frozen `TraceStepEvidence` values with dedicated
`TraceStepStatus` members (`observed` and `failed`). Classification checks all
steps before limiting the output to 100, so a later error still yields `partial`.
`trace_steps` remains a plain-list compatibility adapter; legacy mapping steps
remain accepted by classification. Audit review/failure consumers retain typed
executions until report serialization. Fingerprints and review issue identifiers
are identical for typed and legacy inputs, preserving existing review decisions.

Persisted background jobs now use frozen `StoredRoutineJob` snapshots at the
readback boundary. `latest_results_typed` feeds audit collection and enum-backed
review decisions directly; `latest_results` remains the original mapping API.
Queue, restart, retention and logging decisions parse stored outcomes explicitly.
The shared job enum includes trace `skipped` results. Unknown future outcomes have
no recognized enum interpretation and retain their original wire values, metadata
and steps. Serialization returns detached copies, preserving storage compatibility
and existing review identifiers without promoting unknown evidence to success.

Backend script completion now parses external values into frozen
`ScriptProviderResult` values and dedicated `ScriptReportedOutcome` members
before discovered-script or mapped-routine execution decisions. Discovered
scripts retain their lowercase normalization; mapped routines retain exact-value
matching. Required-step downgrades, direction/correlation guards, speech and
legacy result triples remain unchanged. Correlated trace lookup similarly parses
the independent trace-provider vocabulary before selecting an execution result;
unknown or malformed trace statuses never establish completion.

Script discovery now returns frozen `DiscoveryResult` values with a dedicated
`DiscoveryError` enum; matching returns frozen `ScriptMatchResult` values with
explicit matched, ambiguous and no-match states. Selection, fresh execution
verification, and routine-editor listing/saving consume the typed APIs directly.
The cache retains typed discovery values, and `fresh=True` still bypasses it.
Legacy `discover` list/error pairs and `match` pairs/`None` remain explicit
adapters. Inventory validation, capability-based tie-breaking, candidate order,
and no-execution behavior on missing/ambiguous routines remain compatible.

Response composition, routine response phases, persona verification, session
retry success and lighting context/correction finalization now interpret legacy
inputs with `parse_outcome` and use enum decisions internally. Routine response
phases have a dedicated `ResponsePhase` enum; stored response-library phase keys
and callbacks retain plain strings. Unknown outcomes remain ineligible for
verified-success decoration/training, while an actual absent chat outcome retains
its previous training behavior. Dinner music evidence uses its existing status
enum. Routine rendering also consumes the typed discovery cache directly so live
script metadata remains available after discovery.

Lighting-provider aggregation now retains skipped/error replies as
`ExecutionResult` values and combines their enum outcomes directly. It preserves
first-skipped-result precedence, partial results when any lighting confirmation
exists, response ordering, preview/correction guards and plain legacy pairs.
Timer provider paths construct `ExecutionResult` values with `Outcome` members
directly rather than passing new string pairs through the compatibility adapter.
The public timer API still returns its original pair or `None`; timer persistence,
expiry and cancellation semantics are unchanged.

Diagnostics now interprets outcomes with frozen `DiagnosticResult` values,
separating timing-only `DiagnosticOutcome` values from execution `Outcome`
members. Timed functions recognize typed execution results and typed result/detail
pairs as well as legacy tuples and booleans, returning the original value
unchanged. Live request/stage mappings, SQLite payloads and HTTP exports retain
plain outcomes, including unknown future strings. Error names remain redacted,
stage/retention bounds remain unchanged, and failures after early saves replace
the earlier request outcome.

The compatibility review also converted the remaining mapped custom-routine
completion decisions to `ScriptProviderResult`, preserving their narrower
accepted vocabulary and required-step checks. Local lighting-intent validation
replies now construct enum-backed execution results directly. The remaining
`_lighting_result` calls adapt injected executors; public pair/triple adapters and
external protocol/state comparisons are intentional compatibility boundaries.

The shared inventory transport now returns frozen `InventoryResult` values from
`ha_inventory.read_result`. Production failures use `Outcome.UNAVAILABLE` and
discard incomplete inventory; successful empty inventories remain distinct from
failures. Page/byte/deadline bounds, registry-change detection and duplicate checks
remain unchanged. `read`, `read_ha_inventory` and `read_music_inventory` retain
their original list/error pairs, including `None` on transport failure.

Active server, lighting, music, device-status, fallback and settings paths use
typed inventory readers. Music providers and the registry accept typed inventory
callbacks directly and coerce legacy callbacks only at injection boundaries.
Music retry decisions use enum identity; shared inventory callbacks used by
mapped routines and origin-specific Stop retain typed values. Consumer row lists
retain their existing shape without serializing outcome enums internally.

Home Assistant script-response summaries now retain frozen
`RoutineJobStepEvidence` values with a dedicated `RoutineJobStepStatus` enum.
Required-step verification uses typed completion evidence. Unknown or malformed
statuses never count as completed; unknown textual values still retain their
bounded wire projection. Field filtering, 200-step limits, non-mapping row
behavior and the original distinction between required-step truthiness and the
projected boolean flag remain compatible. Public summary mappings and durable
job payloads still contain the original plain strings and booleans. Direct legacy
summary construction with mapping rows remains supported at serialization.

Routine selection now uses frozen `RoutineSelection` and `RoutineTurnSelection`
values with a dedicated `RoutineSelectionKind` enum. Script, ambiguity,
missing-House-Status and unsupported selections remain distinct through active
selection, preview and execution decisions. The registry passes typed selections
to the active executor and projects legacy tuples only for existing response
metadata. Legacy selection/turn APIs, injected tuple selectors/executors,
follow-on parsing and reply wording remain compatible. Selection options are
detached at construction and when exposed through legacy adapters.

The Home Assistant connection-status provider now returns frozen
`HomeAssistantStatusResult` values with a dedicated five-state
`HomeAssistantStatus` enum. Connection health remains separate from household
execution outcomes: recent Assist activity is not promoted to a verified live
connection. Credential/URL checks, exact health-response verification, bounded
requests, authentication-failure handling and recent-Assist fallback remain
unchanged. `/api/ha-status` and `home_assistant_status()` retain their original
plain status strings. Remaining conditional lighting/bedroom result construction
also uses enum members directly rather than building strings to reparse.

The end-to-end command-path audit found and removed one remaining active legacy
round trip: HTTP timer dispatch now injects `timers.handle_result`, rather than
the public `timers.handle` pair adapter. HTTP regressions disable
`ExecutionResult.as_legacy_pair` while exercising timers, music and chained
routine/lighting requests through both Chat and Assist. They verify authoritative
combined outcomes, typed evidence serialization, and identical plain values in
HTTP replies and stored history. Public legacy timer callers retain their
existing pair/`None` API.

The wider provider audit now includes browser speech recognition. The Assist STT
decoder and transport return frozen `TranscriptionResult` values with explicit
transcribed/no-text statuses rather than using an empty transcript as an implicit
internal result. Existing `run_stt`, `transcribe` and traced-transcription APIs
retain their string adapters. The active HTTP path consumes the typed transport;
its `text` payload, empty-text success response, exception behavior, pipeline
selection, audio framing, deadlines and socket cleanup remain compatible. These
recognition statuses are separate from household execution outcomes.

Issue #17 and its overall typed-outcome checklist remain open as requested. The
identified inventory/provider/dispatch follow-ups above are implemented; this
scoped audit does not claim that every unrelated subsystem or external protocol
has completed the wider outcome migration. Broader evidence statuses must not be
silently narrowed to verified `ActionStatus`.
