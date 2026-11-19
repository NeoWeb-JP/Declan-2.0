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
| Reasoning/output cap | #760 follow-up raises the allowance from 600 to 2,000 tokens, sets supported low reasoning effort for both priced models and preserves the pre-request spending check. Incomplete responses receive a specific safe diagnostic/spoken result and known usage is settled. Live completion frequency and latency remain unmeasured; this is a mitigation, not live acceptance. |
| Restrictive intent gate | #760 follow-up removes fixed action-word filtering. Bounded unmatched text reaches the opt-in planner after local handlers; the model must return an empty plan for unrelated chat, status questions or ambiguity. Authenticated exposure, allowed domains, budgets and confirmations still apply. Synthetic route regressions cover implicit requests and no-action responses. |
| Free-string JSON schema | #760 follow-up uses request-specific entity and service enums paired per domain, plus the owner's action-count limit. Local validation still independently rejects exposure/service/count/dependency violations. Empty permitted context makes no provider call or reservation. |
| Toggle/preflight mismatch | #760 follow-up shares the verified-service vocabulary across validator, preflight and dispatcher. Toggle and unverifiable cover-stop are excluded. Script/media remain outside live AI allowed domains; no permissions are widened. |
| Lexical context selection | The next #760 batch reads HA's configured area/floor names and aliases through an authenticated, admin-only, read-only endpoint for over-limit inventories. It selects complete matching groups intersected with existing exposure/domain permissions, carries aliases/floors into model context and rejects ambiguity, stale metadata, unsupported exclusions, oversized context or broad groups exceeding owner action limits before AI spending. Older integrations retain canonical-name/exact-ID fallback; configured aliases require the updated HA integration. No automatic household synonym guesses or multi-request execution are added. |
| Sensitive garage/gate actions | Generic guarded path defaults to unconfirmed. Do not set confirmation true automatically. Verify and explain the policy, or add a correctly origin-bound confirmation flow. |
| General chat/questions | Current action planner is not a general chat service. This needs an explicit product scope decision, budget/privacy controls and separate acceptance criteria. |
| Synchronous timeout/retries | The 12-second request timeout is present. Review voice latency and acknowledgement semantics; retries must reserve/charge conservatively and never duplicate actions. |
| Pricing/model table | Two hardcoded rate entries remain. Verified 19 November 2026 against official model pages: gpt-6-luna exists and its standard text rates match the current table. gpt-5-mini's published rates also match, but its model page is marked deprecated. Configurable pricing and model lifecycle handling remain open; this batch does not change the owner's chosen model. |
| Key rotation | Local DVAE1 and the separate shared-storage prototype lack key-ID/keyring rotation. This remains an explicit future migration/key-lifecycle requirement, not an implemented feature. No key rotation is attempted here. |
| Flat layout/package moves | Real navigation/coupling cost; package moves were explicitly deferred by accepted #756. Acceptance of that scope does not prove architectural quality. Revisit through a cohesive dependency/ownership change if required. |
| Server service locator | Confirmed residual coupling, explicitly retained by #756. Narrow dependencies where a demonstrated consumer/lifecycle requirement warrants it; no wrapper-only extraction campaign. |
| Source-coupled tests | Confirmed. A scoped scan finds 56 Python files containing read_text/getsource; the supplied larger counts were not reproduced using that same pattern. Replace structural assertions selectively with behavior/fault tests; do not remove safety coverage to reduce counts. |
| Coverage threshold | Restored to 80% without changing measured sources or exclusions. The current full regression baseline exceeds that gate. This does not claim every fault path is covered. |
| Mypy scope | First-party imports now use follow_imports=normal. A behavioral CI regression checks an incompatible return type across an imported module using the actual configuration. The earlier parser repair remains enforced. Missing Home Assistant runtime APIs and untyped external libraries remain limitations; this is not strict typing or full HA runtime type validation. |
| Broad exception boundaries | Requires site-by-site review. The supplied exact count is not adopted as evidence. Keep deliberate execution/service/accounting boundaries and preserve privacy-safe diagnostics. |
| Capture arbitration | First accepted capture is the current #12 VOI-01 requirement, not a newly introduced best-capture regression. Narrow phrase normalization and 4096-cap rejection are present and need duplicate/overload observability tests. Do not silently change the accepted winner policy. |
| Updater trust | github default is an accepted owner trust model, not signature verification. A stricter default requires an explicit policy change; crash-loop/data rollback concerns still require verification and tests. |
| Household content | Some portability concerns remain. #758 accepted installation-owned examples and #12 explicitly requires Edd pronunciation. Do not remove owner-required behavior under a blanket rename/config move; inspect remaining roast/response content separately. |
| Legacy names | Explicit allowlist is already documented and accepted in #757. Adapters are retained deliberately for caches, producers and recursion safety. |
| Stale documentation | Live guarded-fallback docstring was wrong and is corrected in this batch. Other historical/current documentation still needs targeted drift review. |
| CI naming/dependency mismatch | Job name now identifies its blocking checks. Lightweight dependencies are installed before the blocking type check; voice crypto/websocket dependencies use the shipped hash-locked requirements rather than divergent advisory pins. The import inventory remains advisory with a blocking unexpected-import guard. Lock verification remains Linux Python 3.12 only; this does not establish other-platform support. |
| Integration iot_class | Requires comparison to HA's supported classification and actual runtime behavior. No metadata change is made without that check. |

## Priority after this batch

1. Live model completion/latency evidence and sensitive-action policy clarity,
   preserving exposure and confirmation controls. Planner/schema/preflight,
   implicit-input eligibility and bounded area/alias selection are implemented
   in the #760 batches.
2. Updater crash/data rollback fault testing and production key/backup lifecycle.
3. Cross-module typing and stable behavioral tests, followed by deliberate
   architecture improvements where accepted scope needs revisiting.

Issue #17 remains open. These findings are not resolved by documentation or by
the separate, still-unreleased VoicePipeline encryption candidate.

## Previously hidden type errors and CI correction

With mypy 1.18.2, the malformed configuration reports a parsing error but can
exit successfully using defaults. Indenting the regex terminator restores the
intended check_untyped_defs setting. The first repaired-config commit exposed
652 diagnostics in Windows and 648 in Linux CI. Those diagnostics have now been
repaired: validated numeric and optional inputs are narrowed explicitly, mixed
data collections have declared types, and result producers use their enum
contracts. Shared test setup is inherited through fixtures; HTTP doubles carry
real response/header interfaces, and dynamically registered modules are explicit.
The Spotify pagination fixture now resets the actual runtime token cache.

Intentional invalid-input and legacy-coercion tests still call the real runtime
validators; casts at those test boundaries permit deliberate violations of the
static contract. No existing test methods were removed, production type-error
suppressions added, checked paths excluded, or coverage thresholds reduced.
Local validation: the intended Linux mypy 1.18.2 command passes across 677
source files; all 2,397 regressions pass with 86.98% Python line coverage.
Ruff, Bandit and the source-location guard also pass. Before merge, require
the final commit's Linux CI checks to pass.

## #760 planner contract evidence

The new behavioral tests exercise the actual server fallback, model request,
budget ledger, local validation, preflight and verified dispatcher with synthetic
network transports. They do not replace model intent understanding with a claim
of live acceptance. Provider responses attempting private entities, wrong-domain
services and toggle cannot dispatch; unrelated-chat empty plans and missing
permissions cannot change devices. Sensitive covers remain unconfirmed.

Parameter/schema references checked 19 November 2026:
[GPT-5 reasoning controls](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.md),
[GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna.md),
[reasoning output limits](https://developers.openai.com/api/docs/guides/reasoning),
[structured output schemas](https://developers.openai.com/api/docs/guides/structured-outputs).
No live paid API calls or real Home Assistant actions were made by these tests.

Local #760 batch checks: all 2,413 Python regressions pass, with 87.03% line
coverage; mypy passes across 678 source files; Ruff and Bandit pass. Require
final-head GitHub CI before merge. Issue #760 remains open for the unimplemented
findings and the live acceptance evidence described above.

## #760 area and floor selection

The HA integration supplies only location IDs, names, aliases and area-to-floor
relationships. It does not supply entity permissions or cause device actions.
The backend performs one bounded 1.5-second read (at most 1 MiB), only when the
already permission-filtered inventory exceeds the planning context limit.
Metadata remains outside the model until selection attaches relevant labels to
permitted rows. Registry failure does not permit guessed aliases or floors.

Deployment requires updating the native HA integration as well as the backend,
then restarting Home Assistant to register the new endpoint. Until
then, canonical area names and exact entity IDs still work; alias-only requests
receive a clarification. The existing 100-entity context and owner action limits
remain enforced. "Everything off" across an oversized scope is explicitly
refused, rather than implemented as a silently partial group or extra API calls.
Mixed exclusions that cannot be safely scoped also require separate commands.

Behavioral coverage includes an actual server-to-metadata-to-model-to-verified-HA
dispatch path using synthetic network transports, alias collisions, floor/domain
intersection, oversized/empty groups, registry failure, changed area names and
malformed exposure lists. The backend authorization test now checks live function
behavior instead of a source-text condition. No live device/API acceptance is
claimed.

Registry interfaces verified against Home Assistant 2026.11.2:
[area registry](https://github.com/home-assistant/core/blob/2026.11.2/homeassistant/helpers/area_registry.py),
[floor registry](https://github.com/home-assistant/core/blob/2026.11.2/homeassistant/helpers/floor_registry.py).

Validation gates for this batch are full Python regression/coverage, repository
mypy, Ruff, Bandit and HA integration validation. Use the PR checks on the exact
final head for current test counts and coverage. Live HA registry/deployment
acceptance remains separate from these synthetic interface and transport tests.
