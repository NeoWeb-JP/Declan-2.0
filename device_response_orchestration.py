"""Device command dispatch and response adaptation boundary."""


def dispatch_device_response(
    phrase, *, source, last_device, origin_device, satellite,
    dispatch, adapt, registry_factory, dependencies_factory, context_factory,
    parse_status, describe_status, connection, inventory, decorate,
    guest_mode_entity, parse_feedback, feedback, parse_control, control,
    parse_music, play, music_inventory, areas, search_media,
):
    local = dispatch(
        phrase, source=source, last_device=last_device,
        origin_device=origin_device, satellite=satellite,
        registry_factory=registry_factory,
        dependencies_factory=dependencies_factory,
        context_factory=context_factory,
        parse_status=parse_status, describe_status=describe_status,
        connection=connection, inventory=inventory, decorate=decorate,
        guest_mode_entity=guest_mode_entity, parse_feedback=parse_feedback,
        feedback=feedback, parse_control=parse_control, control=control,
        parse_music=parse_music, play=play, music_inventory=music_inventory,
        areas=areas, search_media=search_media,
    )
    return adapt(local) if local is not None else None
