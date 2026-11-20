"""Convert information dispatch results and retain follow-up context."""
from declan.turn.command_response import CommandResponse


def information_response(information_result):
    """Retain typed execution and contextual follow-up information."""
    return CommandResponse(information_result.result,
                           information_context=information_result.information_context)
