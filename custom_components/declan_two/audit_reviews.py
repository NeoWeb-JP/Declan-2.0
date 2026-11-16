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
        routine["reviewed"] = isinstance(saved, dict) and saved.get("fingerprint") == routine["fingerprint"]
        routine["reviewed_at"] = saved.get("reviewed_at") if routine["reviewed"] else None
    report["summary"]["reviewed"] = sum(row["reviewed"] for row in report["routines"])
    report["summary"]["unreviewed"] = len(report["routines"]) - report["summary"]["reviewed"]
