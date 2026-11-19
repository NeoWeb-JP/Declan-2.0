"""Household status and routine selection boundaries using live server dependencies."""

def home_assistant_status_result() -> HomeAssistantStatusResult, *, r):
    return r.ha_household_status.home_assistant_status_result(
        environ=r.os.environ, history_store=r.history, request_factory=r.Request,
        opener_factory=r.build_opener, proxy_factory=r.ProxyHandler,
        redirect_factory=r.NoRedirect, parse_url=r.urlsplit,
    )


def configured_guest_mode_entity(), *, r):
    return r.ha_household_status.configured_guest_mode_entity(entities=r.household_entities)


def read_guest_mode(), *, r):
    return r.ha_household_status.read_guest_mode(
        environ=r.os.environ, entities=r.household_entities,
        request_factory=r.Request, opener_factory=r.build_opener,
        proxy_factory=r.ProxyHandler, redirect_factory=r.NoRedirect, parse_url=r.urlsplit,
    )


def read_visitors_present(), *, r):
    return r.ha_household_status.read_visitors_present(
        environ=r.os.environ, config=r.configuration,
        visitors_entity=r.VISITORS_PRESENT_ENTITY,
        request_factory=r.Request, opener_factory=r.build_opener,
        proxy_factory=r.ProxyHandler, redirect_factory=r.NoRedirect, parse_url=r.urlsplit,
    )


def parse_movie_request(phrase), *, r):
    return r.routine_request_selection.r.parse_movie_request(
        phrase, rooms=r.MOVIE_ROOMS, apps=r.MOVIE_APPS,
    )


HOUSE_STATUS_REQUESTS = r.routine_request_selection.HOUSE_STATUS_REQUESTS


def select_routine_result(phrase, origin) -> RoutineSelection | None, *, r):
    return r.routine_request_selection.r.select_routine_result(
        phrase, origin, connect=r.ha_device_connection,
        discovery_module=r.script_discovery, movie_parser=r.parse_movie_request,
        morning_phrases=r.GOOD_MORNING_PHRASES, night_phrases=r.GOOD_NIGHT_PHRASES,
        dinner_phrases=r.DINNER_PHRASES, sexy_commands=r.SEXY_TIME_COMMANDS,
    )


def select_routine_turn_result(phrase, origin) -> RoutineTurnSelection | None, *, r):
    return r.routine_turn_orchestration.r.select_routine_turn_result(
        phrase, origin, select=r.select_routine_result, parse_movie=r.parse_movie_request,
    )


def preview_routine_result(phrase, origin=None), *, r):
    return r.routine_turn_orchestration.preview_routine_result(
        phrase, origin, select_turn=r.select_routine_turn_result,
    )


def execute_routine_result(selection, action_results, *, approved=False), *, r):
    return r.routine_turn_orchestration.execute_routine_result(
        selection, action_results, approved=approved,
        discovery=r.script_discovery, connect=r.ha_device_connection,
    )

