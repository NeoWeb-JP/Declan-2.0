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

Issue #17 and its overall typed-outcome checklist remain open. Remaining audit
scope includes conversational retry cancellation, roast/guest dispatch and
final-response/session orchestration still using legacy tuples. Structured action
evidence also retains legacy statuses such as `already_set`, `planned` and
`skipped`; those must not be silently narrowed to `ActionStatus` members.
