"""Inventory and stop-command compatibility boundaries."""

def read_ha_inventory(connection, *, r):
    return r.read_ha_inventory_result(connection).as_legacy_pair()

def read_ha_inventory_result(connection) -> r.ha_inventory.InventoryResult:
    return r.ha_inventory.read_result(connection)


def read_music_inventory(connection, *, r):
    return r.read_music_inventory_result(connection).as_legacy_pair()

def read_music_inventory(connection, *, r):
    return inventory_stop_boundaries.read_ha_inventory_result(connection, r=sys.modules[__name__])

def read_music_inventory_result(connection) -> r.ha_inventory.InventoryResult:
    return r.ha_inventory.read_result(connection, music=True)


def stop_everywhere_result(connection, *, r):
    """Return a typed stop-all result with playback diagnostics."""
    return r._stop_everywhere_typed_core(connection)

def stop_everywhere_result(connection, *, r):
    return inventory_stop_boundaries.read_music_inventory_result(connection, r=sys.modules[__name__])

def stop_everywhere_output(connection, *, r):
    """Legacy stop-all response for existing callers."""
    typed, status = r.stop_everywhere_result(connection)
    return typed.reply, typed.outcome.value, status

def _stop_everywhere_typed_core(connection, *, r):
    return r.music_stop_dispatch.stop_everywhere_result(
        connection, inventory_reader=r.read_music_inventory_result,
        inventory_module=r.ha_inventory, music_provider=r.music,
    )

def stop_origin_output(connection, satellite, device, *, r):
    """Preserve legacy triple response for callers of origin-specific Stop."""
    result, status = r.stop_origin_result(connection, satellite, device)
    return result.reply, result.outcome.value, status

def stop_origin_result(connection, satellite, device, *, r):
    return r.music_stop_dispatch.stop_origin_result(
        connection, satellite, device, inventory_reader=r.read_music_inventory_result,
        inventory_module=r.ha_inventory, music_provider=r.music, timer_provider=r.timers,
    )

def read_ha_areas(connection, origin=None, *, r):
    """Compatibility boundary for Home Assistant area discovery."""
    return r.ha_area_switch_actions.read_ha_areas(
        connection, origin, request_factory=r.Request,
    )

def set_switch_as_light_result(name, desired_state, inventory, connection, *, preview=False, action_results=None, r):
    """Compatibility boundary for explicitly marked switch lights."""
    return r.ha_area_switch_actions.set_switch_as_light_result(
        name, desired_state, inventory, connection,
        preview=preview, action_results=action_results,
        request_factory=r.Request, append_evidence=r.append_action_evidence,
        evidence_factory=r.LightingActionEvidence,
    )
