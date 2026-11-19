# Corrective review following external findings

Baseline: main `6d9f687`, reviewed 19 November 2026. Passing regressions and
accepted architecture dispositions did not establish fault-path correctness.
This register distinguishes reproduced defects, verified code limitations and
changes that require a product/security decision. It does not mark the supplied
review wholesale as either correct or resolved.

## First corrective batch: failed-planning accounting

The reservation was retained on every planner exception. Proven pre-request
validation/credential failures therefore depleted the budget despite no API
call, and known usage from rejected/incomplete plans was not settled.

The fix introduces a trusted nonbillable-failure classification, settles it at
zero, and settles other failed plans only when the existing usage callback can
provide a valid measured charge. Unknown exceptions, timeouts, HTTP 408 and
server errors without usage retain the ceiling. Do not refund every ValueError
or assume every HTTP 5xx proves no work was processed. Known request-rejection
HTTP statuses are classified separately. No retries or extra API calls are added.

The panel shows remaining budget including spend/pending reservations, and
spoken budget-denied responses state the remaining amount. Existing ambiguous
historical reservations are not reset: they lack the provenance needed for a
safe automatic refund. The guarded-fallback docstring is corrected.

## Remaining findings and disposition

| Finding | Verified status and required next action |
| --- | --- |
| Reasoning/output cap | The code caps output at 600 and defaults to gpt-5-mini. Reasoning tokens share that cap; actual model failure frequency is not measured. Test supported effort/cap choices within the spend ceiling and distinguish incomplete responses. |
| Restrictive intent gate | Confirmed fixed action-word filtering. Add natural implicit-command regressions and a bounded classification/planning policy without granting extra device permissions. |
| Free-string JSON schema | Confirmed entity/service strings are unconstrained in the model schema; local validation still rejects invalid plans. Add request-specific enum constraints and retain local validation. |
| Toggle/preflight mismatch | Confirmed plan validator permits toggle while preflight rejects it. Align planner capabilities without widening script/media permissions implicitly. |
| Lexical context selection | Confirmed over-limit inventory uses word overlap and can reject broad/alias requests. Review area/alias resolution and safe bounded grouping; do not truncate away required actions silently. |
| Sensitive garage/gate actions | Generic guarded path defaults to unconfirmed. Do not set confirmation true automatically. Verify and explain the policy, or add a correctly origin-bound confirmation flow. |
| General chat/questions | Current action planner is not a general chat service. This needs an explicit product scope decision, budget/privacy controls and separate acceptance criteria. |
| Synchronous timeout/retries | The 12-second request timeout is present. Review voice latency and acknowledgement semantics; retries must reserve/charge conservatively and never duplicate actions. |
| Pricing/model table | Two hardcoded rate entries are present. The gpt-6-luna entry/rates are not independently verified here; absence from a quick search would not prove nonexistence. Verify official model/pricing data and design owner-visible configurable rates. |
| Key rotation | Local DVAE1 and the separate shared-storage prototype lack key-ID/keyring rotation. This remains an explicit future migration/key-lifecycle requirement, not an implemented feature. No key rotation is attempted here. |
| Flat layout/package moves | Real navigation/coupling cost; package moves were explicitly deferred by accepted #756. Acceptance of that scope does not prove architectural quality. Revisit through a cohesive dependency/ownership change if required. |
| Server service locator | Confirmed residual coupling, explicitly retained by #756. Narrow dependencies where a demonstrated consumer/lifecycle requirement warrants it; no wrapper-only extraction campaign. |
| Source-coupled tests | Confirmed. A scoped scan finds 56 Python files containing read_text/getsource; the supplied larger counts were not reproduced using that same pattern. Replace structural assertions selectively with behavior/fault tests; do not remove safety coverage to reduce counts. |
| Coverage threshold | Current gate is 75%. The claimed historical reduction and reason have not been audited here. Measure behavior coverage and restore stronger gates with evidence, rather than changing a number without a passing baseline. |
| Mypy scope | follow_imports=skip and missing-import relaxation are real limitations. Validation also found an unindented multiline-regex terminator that causes config parsing to fail while mypy can report success using defaults. This batch fixes parsing and adds a config-parser regression; first-party import following remains a separate expansion. |
| Broad exception boundaries | Requires site-by-site review. The supplied exact count is not adopted as evidence. Keep deliberate execution/service/accounting boundaries and preserve privacy-safe diagnostics. |
| Capture arbitration | First accepted capture is the current #12 VOI-01 requirement, not a newly introduced best-capture regression. Narrow phrase normalization and 4096-cap rejection are present and need duplicate/overload observability tests. Do not silently change the accepted winner policy. |
| Updater trust | github default is an accepted owner trust model, not signature verification. A stricter default requires an explicit policy change; crash-loop/data rollback concerns still require verification and tests. |
| Household content | Some portability concerns remain. #758 accepted installation-owned examples and #12 explicitly requires Edd pronunciation. Do not remove owner-required behavior under a blanket rename/config move; inspect remaining roast/response content separately. |
| Legacy names | Explicit allowlist is already documented and accepted in #757. Adapters are retained deliberately for caches, producers and recursion safety. |
| Stale documentation | Live guarded-fallback docstring was wrong and is corrected in this batch. Other historical/current documentation still needs targeted drift review. |
| CI naming/dependency mismatch | The advisory-named job runs blocking checks; different advisory/runtime dependency pins exist. Reconcile labels and audit environments without weakening gates or confusing Linux-only lock verification with all-platform support. |
| Integration iot_class | Requires comparison to HA's supported classification and actual runtime behavior. No metadata change is made without that check. |

## Priority after this batch

1. Planner/schema/preflight alignment, implicit device commands and model
   completion/latency tests, preserving exposure and sensitive-action controls.
2. Updater crash/data rollback fault testing and production key/backup lifecycle.
3. Cross-module typing and stable behavioral tests, followed by deliberate
   architecture improvements where accepted scope needs revisiting.

Issue #17 remains open. These findings are not resolved by documentation or by
the separate, still-unreleased VoicePipeline encryption candidate.

## Validation blocker: previously hidden type errors

With mypy 1.18.2, the malformed configuration reports a parsing error but can
exit successfully using defaults. Indenting the regex terminator restores the
intended check_untyped_defs setting. The corrected configuration exposes 652
diagnostics in 164 files in the Windows validation environment (676 checked
files); platform and dependency differences can change this count. This is not
a passing typing baseline. No suppressions, exclusions or lower gates were
added to conceal it. This corrective PR remains a draft pending a clean intended
Linux CI type check and correction of the existing diagnostics.
