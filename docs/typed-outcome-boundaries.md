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

Issue #17 and its overall typed-outcome checklist remain open. Remaining audit
scope includes older mapped-routine helpers (`run_custom_routine`, `run_routine`,
`format_routine_result`, `run_sexy_time`), auxiliary media/device providers, and
response/session orchestration that still uses legacy tuples. Structured action
evidence also retains legacy statuses such as `already_set`, `planned` and
`skipped`; those must not be silently narrowed to `ActionStatus` members.
