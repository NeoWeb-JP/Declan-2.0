"""Dispatch device status and music commands through the local registry."""


def dispatch_device(phrase, *, source, last_device, origin_device, satellite,
                    registry_factory, dependencies_factory, context_factory,
                    parse_status, describe_status, connection, inventory, decorate,
                    guest_mode_entity, parse_feedback, feedback, parse_control,
                    control, parse_music, play, music_inventory, areas, search_media,
                    parse_extra=None, extra=None):
    """Return the local command dispatch result without altering command precedence."""
    dependencies = dependencies_factory(
        parse_status=parse_status, describe_status=describe_status,
        connection=connection, inventory=inventory, decorate=decorate,
        guest_mode_entity=guest_mode_entity, parse_feedback=parse_feedback,
        feedback=feedback, parse_control=parse_control, control=control,
        parse_music=parse_music, play=play, music_inventory=music_inventory,
        areas=areas, search_media=search_media, parse_extra=parse_extra, extra=extra,
    )
    return registry_factory(dependencies).dispatch(context_factory(
        phrase=phrase, source=source, last_device=last_device,
        origin_device=origin_device, satellite=satellite,
    ))
