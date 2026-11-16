# Home Assistant Audit

Open **Declan > Home Assistant Audit** using a Home Assistant administrator account.
Opening the page or pressing **Refresh audit** reads the currently loaded HA sources.
Search names, entity IDs or finding codes. Both groups and individual rows start collapsed.

The audit inventories current states and the entity registry, including disabled entities.
It inspects loaded script and automation configuration, expanded action sequences, and
HA's extracted entity, device and area references. It checks explicit dependencies
against current registries and registered services. This includes packaged sources;
the repository examples and files on disk are not the audit's source of truth.

Recent retained trace summaries are linked by HA's persistent automation ID or script
ID. Up to five recent runs per routine show run ID, timestamps, status and last step.
Use that run ID in Home Assistant Traces to inspect the detailed failure. Raw trace
errors, variables, configuration, messages and state attributes are not returned.

Missing configuration, missing retained traces, unavailable trace APIs, broad targets
and unevaluated templates are explicitly unverified. Templates are never evaluated.
The audit cannot prove every branch ran or that a device changed successfully. A
finished trace remains `finished_unverified`. Historical traces may refer to earlier
configuration. No trace does not mean a routine has never run. Disabled routines are
reported for review, not automatically treated as broken.

The authenticated admin-only `GET /api/declan_two/ha-audit` route has no write handler,
service calls, execution buttons, repair operation, or persistent audit cache. The
page clears the previous snapshot when refreshing, including when a refresh fails.
Recommendations are for manual review in Home Assistant. Nothing modifies household
scripts, automations, helpers, entities, or their enabled state.

HA's internal loaded-entity and trace interfaces can vary by release. Missing evidence
is reported rather than replaced by example YAML or an assumed successful result.
