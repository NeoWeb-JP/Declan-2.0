"""Prioritized local handlers, with pure matching and injected execution dependencies."""
from collections.abc import Callable
from dataclasses import dataclass
import re

from execution_results import ExecutionResult, Outcome


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
                reply, outcome, target = deps.describe_status(*query, inventory)
                if outcome == Outcome.CONFIRMED:
                    guest = next((row.get("state") for row in inventory if isinstance(row, dict)
                                  and row.get("entity_id") == deps.guest_mode_entity), None)
                    reply = deps.decorate(reply, "device_status", guest)
        return HandledCommand("device_status", ExecutionResult(reply, outcome), target)

    def feedback(context, command):
        reply, outcome = deps.feedback(command, deps.connection(), deps.music_inventory)
        return HandledCommand("music_feedback", ExecutionResult(reply, outcome))

    def control(context, command):
        reply, outcome = deps.control(
            command, deps.connection(), deps.music_inventory,
            origin=context.origin_device or context.satellite, read_areas=deps.areas,
            assist=context.source == "assist",
        )
        return HandledCommand("music_control", ExecutionResult(reply, outcome))

    def play(context, command):
        reply, outcome = deps.play(
            command, deps.connection(), deps.music_inventory,
            **({"origin": context.satellite or context.origin_device}
               if context.satellite or context.origin_device else {}),
        )
        return HandledCommand("music_play", ExecutionResult(reply, outcome))

    def media_search(context, phrase):
        reply, outcome = deps.search_media(phrase)
        return HandledCommand("media_search", ExecutionResult(reply, outcome))

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
