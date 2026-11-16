"""Persistent human review metadata, separate from household configuration."""
import asyncio


async def review_state(hass):
    from homeassistant.helpers.storage import Store

    key = "declan_two_audit_reviews"
    if key not in hass.data:
        hass.data[key] = {"store": Store(hass, 1, key), "records": None, "lock": asyncio.Lock()}
    state = hass.data[key]
    async with state["lock"]:
        if state["records"] is None:
            loaded = await state["store"].async_load()
            state["records"] = loaded if isinstance(loaded, dict) else {}
    return state


async def apply_reviews(hass, report):
    state = await review_state(hass)
    for routine in report["routines"]:
        saved = state["records"].get(routine["entity_id"], {})
        if isinstance(saved, dict) and isinstance(saved.get("review_source"), str):
            # Resolved issues and successful runs do not undo a human review.
            # New issues or changed source are tracked separately from the flag.
            matches_current = (saved["review_source"] == routine.get("review_source")
                and isinstance(saved.get("review_issues"), list)
                and set(routine.get("review_issues", [])) <= set(saved["review_issues"]))
        else:
            # Legacy fingerprints still indicate whether the assessment is current.
            matches_current = isinstance(saved, dict) and saved.get("fingerprint") == routine["fingerprint"]
        # Reviewed is a durable human decision, not a live verification result.
        # Only an explicit uncheck removes the saved record. Preserve legacy
        # decisions too, even when the old fingerprint no longer matches.
        routine["reviewed"] = (isinstance(saved, dict) and isinstance(saved.get("fingerprint"), str)
                               and isinstance(saved.get("reviewed_at"), str))
        routine["review_changed"] = routine["reviewed"] and not matches_current
        routine["reviewed_at"] = saved.get("reviewed_at") if routine["reviewed"] else None
    report["summary"]["reviewed"] = sum(row["reviewed"] for row in report["routines"])
    report["summary"]["unreviewed"] = len(report["routines"]) - report["summary"]["reviewed"]
