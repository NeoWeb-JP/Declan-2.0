"""Prioritized local handlers, with pure matching and injected execution dependencies."""
from collections.abc import Callable
from dataclasses import dataclass
import re

from execution_results import ExecutionResult, Outcome
from music_provider_result import music_execution_result
from local_outcome_contracts import timer_execution_result, routine_execution_result
from device_status import DeviceStatusResult


@dataclass(frozen=True)
class RequestContext:
    phrase: str
    source: str
    last_device: str | None = None
    origin_device: object = None
    satellite: object = None


@dataclass(frozen=True)
class HandledCommand:
    handler: str
    result: ExecutionResult
    status_target: str | None = None
    routine_status: str | None = None
    information_context: object = None
    routine_follow_on: str | None = None
    routine_reply: str | None = None
    routine_selection: object = None


@dataclass(frozen=True)
class Handler:
    name: str
    priority: int
    match: Callable
    execute: Callable


@dataclass(frozen=True)
class HandlerRegistry:
    handlers: tuple[Handler, ...]

    def __post_init__(self):
        handlers = tuple(self.handlers)
        if any(not isinstance(handler, Handler) or not isinstance(handler.name, str)
               or not handler.name or type(handler.priority) is not int
               or not callable(handler.match) or not callable(handler.execute) for handler in handlers):
            raise ValueError("Invalid command handler")
        if len({handler.name for handler in handlers}) != len(handlers) or len(
                {handler.priority for handler in handlers}) != len(handlers):
            raise ValueError("Handler names and priorities must be unique")
        object.__setattr__(self, "handlers", tuple(sorted(handlers, key=lambda handler: handler.priority)))

    def dispatch(self, context):
        if not isinstance(context, RequestContext):
            raise ValueError("Command request context is required")
        for handler in self.handlers:
            match = handler.match(context)
            if match:
                # A match owns the command, including failure/clarification.
                # Never try another executor after an uncertain side effect.
                result = handler.execute(context, match)
                if result is None and handler.name == "lighting":
                    return None
                if not isinstance(result, HandledCommand) or result.handler != handler.name:
                    raise ValueError("Invalid command handler result")
                return result
        return None


@dataclass(frozen=True)
class Dependencies:
    parse_status: Callable
    describe_status: Callable
    connection: Callable
    inventory: Callable
    decorate: Callable
    guest_mode_entity: str
    parse_feedback: Callable
    feedback: Callable
    parse_control: Callable
    control: Callable
    parse_music: Callable
    play: Callable
    music_inventory: Callable
    areas: Callable
    search_media: Callable | None = None


def registry(deps):
    """Preserve the old status -> feedback -> control -> play precedence."""
    if not isinstance(deps, Dependencies):
        raise ValueError("Command handler dependencies are required")

    def status(context, query):
        connection = deps.connection()
        target = None
        if connection is None:
            reply, outcome = "The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED
        else:
            inventory, error = deps.inventory(connection)
            if error:
                reply, outcome = "I couldn't read device states from Home Assistant.", error
            else:
                described = DeviceStatusResult.coerce(deps.describe_status(*query, inventory))
                reply, outcome, target = described.result.reply, described.result.outcome, described.target
                if outcome is Outcome.CONFIRMED:
                    guest = next((row.get("state") for row in inventory if isinstance(row, dict)
                                  and row.get("entity_id") == deps.guest_mode_entity), None)
                    reply = deps.decorate(reply, "device_status", guest)
        return HandledCommand("device_status", ExecutionResult(reply, outcome), target)

    def feedback(context, command):
        result = deps.feedback(command, deps.connection(), deps.music_inventory)
        return HandledCommand("music_feedback", music_execution_result(result))

    def control(context, command):
        result = deps.control(
            command, deps.connection(), deps.music_inventory,
            origin=context.origin_device or context.satellite, read_areas=deps.areas,
            assist=context.source == "assist",
        )
        return HandledCommand("music_control", music_execution_result(result))

    def play(context, command):
        result = deps.play(
            command, deps.connection(), deps.music_inventory,
            **({"origin": context.satellite or context.origin_device}
               if context.satellite or context.origin_device else {}),
        )
        return HandledCommand("music_play", music_execution_result(result))

    def media_search(context, phrase):
        result = deps.search_media(phrase)
        return HandledCommand("media_search", result if isinstance(result, ExecutionResult) else ExecutionResult(*result))

    return HandlerRegistry((
        Handler("device_status", 10, lambda context: deps.parse_status(context.phrase, context.last_device), status),
        Handler("music_feedback", 20, lambda context: deps.parse_feedback(context.phrase), feedback),
        Handler("music_control", 30, lambda context: deps.parse_control(context.phrase), control),
        Handler("music_play", 40, lambda context: deps.parse_music(context.phrase), play),
        *([Handler("media_search", 50, lambda context: context.phrase if re.fullmatch(
            r"(?:where can i (?:watch|stream|find)|(?:search|look) for|find (?:the )?(?:movie|film|show)|"
            r"start (?:movie time|cinema time|cinema mode) and play(?: the (?:movie|film|show))?) (.+)",
            context.phrase,
        ) else None, media_search)] if deps.search_media is not None else []),
    ))


def stop_registry(*, stop_routines, stop_everywhere, connection):
    """Higher-priority stop commands; run after timer parsing to preserve timer ownership."""
    def run_routines(context, match):
        typed, status = routine_execution_result(stop_routines())
        return HandledCommand("stop_routine", typed, routine_status=status)

    def run_everywhere(context, match):
        typed, status = routine_execution_result(stop_everywhere(connection()))
        return HandledCommand("stop_everywhere", typed, routine_status=status)

    return HandlerRegistry((
        Handler("stop_routine", 1,
                lambda context: context.phrase in {"stop routine", "cancel routine",
                                                    "stop the routine", "cancel the routine"}, run_routines),
        Handler("stop_everywhere", 2, lambda context: context.phrase == "stop", run_everywhere),
    ))


def timer_registry(*, matches, handle, opener, guest_mode, decorate):
    """Timer requests own their outcome before Stop and routine dispatch."""
    def run(context, phrase):
        result = handle(
            phrase, opener, satellite=context.satellite if isinstance(context.satellite, str)
            and len(context.satellite) <= 128 else None,
            device=context.origin_device, browser=context.source != "assist",
        )
        if result is None:
            raise ValueError("Matched timer command returned no result")
        typed = timer_execution_result(result)
        if typed.outcome in {Outcome.TIMER_SET, Outcome.TIMER_ADJUSTED,
                             Outcome.TIMER_CANCELLED, Outcome.TIMER_STOPPED}:
            typed = ExecutionResult(decorate(typed.reply, typed.outcome.value, guest_mode()), typed.outcome)
        return HandledCommand("timer", typed)

    return HandlerRegistry((Handler("timer", 0,
        lambda context: context.phrase if matches(context.phrase) else None, run),))


def information_registry(*, matches, follow_up, handle, question_context,
                         opener, last_information, decorate, guest_mode):
    """Read-only information commands with contextual follow-up ownership."""
    def run(context, phrase):
        information_phrase, clarification = follow_up(phrase, last_information)
        if clarification:
            return HandledCommand("information", ExecutionResult(clarification, Outcome.UNRESOLVED))
        result = handle(information_phrase, opener)
        if result is None:
            raise ValueError("Matched information request returned no result")
        reply, outcome, category = result
        typed = ExecutionResult(reply, outcome)
        next_context = question_context(information_phrase) if typed.outcome in {
            Outcome.CONFIRMED, Outcome.PARTIAL, Outcome.UNAVAILABLE} else None
        if typed.outcome is Outcome.CONFIRMED:
            typed = ExecutionResult(decorate(reply, category, guest_mode()), typed.outcome)
        return HandledCommand("information", typed, information_context=next_context)

    return HandlerRegistry((Handler("information", 0,
        lambda context: context.phrase if matches(context.phrase, last_information) else None, run),))


def lighting_registry(*, matches, parse_light_command, handle_light_request,
                      action_results, last_lights, origin_device):
    """Lighting command ownership with injected action/history dependencies."""
    def run(context, phrase):
        result = handle_light_request(
            phrase, action_results=action_results, last_lights=last_lights,
            origin_device=origin_device,
        )
        if result is None:
            return None
        return HandledCommand("lighting", result if isinstance(result, ExecutionResult) else ExecutionResult(*result))

    return HandlerRegistry((Handler("lighting", 0,
        lambda context: context.phrase if matches(context.phrase, parse_light_command) else None,
        run),))


def routine_registry(*, select, execute, action_results, origin):
    """Select and execute a HA routine, leaving chained follow-on work to the caller."""
    def run(context, selection):
        routine, follow_on = selection
        typed, status = routine_execution_result(execute(routine, action_results))
        return HandledCommand("routine", typed,
                              routine_status=status, routine_follow_on=follow_on,
                              routine_reply=typed.reply, routine_selection=selection)

    return HandlerRegistry((Handler("routine", 0,
        lambda context: select(context.phrase, origin), run),))
