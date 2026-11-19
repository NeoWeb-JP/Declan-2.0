"""Runtime initialization kept separate from the server compatibility facade."""


def create_runtime(*, logging_module, session_module, arbiter_factory,
                   confirmation_factory, gates_factory, cooldown_factory,
                   registry_factory):
    event_log = logging_module.getLogger("declan.server")
    event_log.setLevel(logging_module.INFO)
    return (
        event_log,
        session_module.DEFAULT_SESSION_STORE,
        arbiter_factory(),
        confirmation_factory(),
        gates_factory(),
        cooldown_factory(),
        registry_factory(),
    )


def runtime_settings(*, updates_module, vocabulary):
    return (
        300,
        52737,
        updates_module.configured_release_version(),
        vocabulary.SEXY_TIME_COMMANDS,
        vocabulary.DINNER_PHRASES,
        vocabulary.GUEST_MODE_ENTITY,
        vocabulary.GUEST_REGISTER_ENTITY,
        vocabulary.VISITORS_PRESENT_ENTITY,
        vocabulary.GUEST_COMMANDS,
        vocabulary.UNMATCHED_REPLY,
        vocabulary.NAME_PATTERN,
        vocabulary.CHAT_COMMANDS,
        vocabulary.GOOD_MORNING_SCRIPT,
        vocabulary.GOOD_MORNING_PHRASES,
        vocabulary.GOOD_NIGHT_SCRIPT,
        vocabulary.GOOD_NIGHT_PHRASES,
    )
