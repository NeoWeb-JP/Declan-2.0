"""Separate device-action requests from ordinary conversation.

Local intent handlers always run first. Only plausible device commands enter
the guarded action planner; general chat keeps its existing conversation path.
"""
import re

ACTION = re.compile(
    r"\b(?:turn|turning|switch|switching|set|setting|dim|brighten|"
    r"open|opening|close|closing|start|stop|run|activate|deactivate|"
    r"make|raise|lower|increase|decrease|adjust)\b",
    re.IGNORECASE,
)


def is_action_request(utterance):
    if not isinstance(utterance, str):
        return False
    if ACTION.search(utterance):
        return True
    return bool(re.search(r"\\bmake\\b", utterance, re.I) and
                re.search(r"\\b(?:light|lights|fan|blinds|curtains|room|lounge|kitchen|bedroom|brighter|darker)\\b", utterance, re.I))
