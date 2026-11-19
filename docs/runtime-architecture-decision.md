# Runtime architecture closure decision

Review baseline: merged #755 main `11d87a0`, 19 November 2026.
Accepted through merged PR #756. It does not claim that every
module global has been eliminated or that multiple households are isolated in
one Python interpreter.

## Supported runtime

Retain one backend runtime per process. HTTP request threads share the process's
session, arbitration, confirmation, cooldown, active-routine and music owners.
That sharing is intentional: duplicate suppression and Stop must see concurrent
requests within the same household. Independent deployments require separate
processes and data directories; the compatibility facade is not a multi-tenant
container.

## Retain the compatibility facade

The original server decomposition scope is implemented. `server.py` retains
public entry points, re-exports, compatibility constants and runtime wiring.
HTTP transport/ingress, turn orchestration, sessions, response composition,
persistence and startup are owned by dedicated modules. A facade wrapper is not
unfinished extraction solely because it still delegates through the live server
module. Keep current imports and patch points stable.

The broad `r` dependency surface remains coupling. Accept it for the supported
single-runtime deployment rather than requiring a blanket rewrite to finish
#17. New domain logic belongs in its owning module; introduce a narrower
dependency contract when a concrete consumer needs independent composition.
Do not start more wrapper-only extraction PRs or set a server line-count target.

## State ownership

| Owner | Contract and current evidence |
| --- | --- |
| `SessionStore` | Session data and lock are owned together; separate instances have separate data/locks; current injected store reaches conversation handling |
| `RoutineCooldown` | Atomic claims under an owner lock; exactly one simultaneous claim wins |
| `ActiveRoutineRegistry` | Registration is released after normal/exceptional exits; detached snapshots and overlap ownership are tested |
| `MusicRuntimeState` | Handoff and token locks are independent; tokens and skip state are independent across owner instances |
| `server_runtime_state.create_runtime` | Uses the process-default session store and constructs the other owners once per invocation; repeated calls do not create fully isolated application runtimes |

Tests: `test_session_store`, `test_routine_cooldown`,
`test_active_routine_registry`, `test_music_runtime_state`,
`test_server_runtime_state_extraction`, and the HTTP/dispatch/completion/atomic
finalization extraction tests under `tests/`. The combined 35-test group passed
on Ubuntu/Python 3.12. This is evidence for these contracts, not a proof that all
possible races are absent.

## Disposition of the original global-state/package request

The unsafe loose-state patterns cited in the original review have explicit
owners and synchronization. Process-default owners still exist. Recommend
accepting that ownership model for #17 and deferring wholesale package moves
and universal dependency injection: neither is required by the current
single-runtime contract, and moving files alone does not change ownership.

The original global-removal/package request is explicitly dispositioned by
accepted #756: retain synchronized process owners and defer wholesale package
moves. Do not describe this as literal removal of all global mutable state.

Revisit this decision if multiple applications must coexist in one interpreter,
tests demonstrate cross-owner leakage, shutdown/reload must replace owners
without restarting the process, or a concrete concurrency defect appears.
Those changes require a lifecycle design and tests for the demonstrated need.

## Separate remaining work

This decision does not dispose of household YAML targets, legacy naming
migrations, speaker metadata transport, HA credential integration, shared
VoicePipeline privacy or deployment/UAT evidence. #17 stays open for those
items even if this architecture disposition is accepted.
