# Home Assistant Audit

Open **Declan > Home Assistant Audit** using a Home Assistant administrator account.
Opening the page or pressing **Refresh audit** reads the currently loaded HA sources.
Search names, entity IDs or finding codes. Both groups and individual rows start collapsed.

Stale entity records with no loaded script/automation are hidden by default in both
groups. Enable **Show stale entity records** to inspect them. Loaded routines remain
visible even when unavailable; stale records are not counted as loaded scripts or
automations. The review checkbox and download button have separate, spaced controls.

Use **Download YAML** inside a routine row to export its current loaded Home Assistant
definition. This is read from HA when clicked, not from Declan's repository or the earlier
audit snapshot. It contains the routine's configuration only, without audit/review metadata,
trace variables or runtime history. No household action is executed and nothing is written
back to HA. Stale entities without a loaded definition have no download button.

The export represents loaded configuration, so original comments, formatting and include
file layout are not preserved. Blueprint definitions keep their `use_blueprint` reference;
the blueprint file itself is not bundled. Configured values can be present in the export,
just as in HA's own configuration editor. The endpoint requires an HA administrator.

**Edit YAML** opens that routine's native Home Assistant editor using its persistent
script/automation ID, including when its entity ID has been renamed. If HA opens the
visual editor, choose its three-dot menu and **Edit in YAML**. HA currently has no
supported YAML-mode-only deep link. File/package-managed routines may be read-only in
the native editor; HA retains control of edit/save permissions. Stale records have no
editor button. Navigating to the editor does not save or change the routine.

The audit inventories current states and the entity registry, including disabled entities.
It inspects loaded script and automation configuration, expanded action sequences, and
HA's extracted entity, device and area references. It checks explicit dependencies
against current registries and registered services. This includes packaged sources;
the repository examples and files on disk are not the audit's source of truth.

Recent retained trace summaries are linked by HA's persistent automation ID or script
ID. Up to five recent runs per routine show run ID, timestamps, status and last step.
Action paths record observed steps and failures, including errors suppressed by
`continue_on_error` (reported as partial). At most 100 paths per run are displayed;
truncation is explicit and all observed paths are checked for errors before truncation.
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

## Human review flags

Each routine has a **Reviewed and fixed** checkbox. The routine list defaults to
**Unreviewed routines**; use **All routines** or **Reviewed and fixed** to find reviewed
items and undo a review. Flags persist in the integration's separate metadata store.
Checking a flag records your assessment; it does not repair or execute anything.
The **Entities** inventory remains a complete inventory independent of review filters.

A flag applies to the inspected version of the loaded routine. Configuration changes,
changed static findings, or a new failed/partial run make it unreviewed again. Ordinary
successful runs and newly available traces do not clear a review. Saving a flag from
an outdated snapshot is rejected; refresh and review the current version. The separate
admin-only `POST /api/declan_two/ha-audit/reviews` route writes review metadata only.

## Voice completion evidence

When a script returns no structured outcome, Declan can read
`GET /api/declan_two/script-result` using the script state context returned by the
original service call. The lookup requires exactly one retained trace for that script
and context. It never runs the script again. A finished error-free run produces
`execution_completed` with a short spoken acknowledgement and personality; device
state verification remains separate. Suppressed action errors remain partial, and
missing/ambiguous evidence stays unverified. Status questions still need their actual
spoken summary, and explicit script failures or mismatched response IDs are preserved.

HA's internal loaded-entity and trace interfaces can vary by release. Missing evidence
is reported rather than replaced by example YAML or an assumed successful result.
