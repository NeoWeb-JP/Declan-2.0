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

Issue #17 and its overall typed-outcome checklist remain open. Remaining audit
scope includes auxiliary action providers (movie launch, announcements, guest
assignment and switch-as-light fallback) and
response/session orchestration that still uses legacy tuples. Structured action
evidence also retains legacy statuses such as `already_set`, `planned` and
`skipped`; those must not be silently narrowed to `ActionStatus` members.
