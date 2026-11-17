"""Convert information dispatch results and retain follow-up context."""
from command_response import CommandResponse


def information_response(information_result):
    """Retain typed execution and contextual follow-up information."""
    return CommandResponse(information_result.result,
                           information_context=information_result.information_context)


def information_result_response(information_result):
    """Return (reply, outcome, information_context) for a handled request."""
    reply, outcome = information_result.result.as_legacy_pair()
    return reply, outcome, information_result.information_context
