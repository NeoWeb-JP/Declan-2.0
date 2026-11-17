"""Validate typed music provider results and legacy injected reply pairs."""
from execution_results import ExecutionResult


def music_execution_result(provider_reply):
    """Validate a provider reply and return a frozen typed execution result."""
    if isinstance(provider_reply, ExecutionResult):
        return provider_reply
    if not isinstance(provider_reply, (tuple, list)) or len(provider_reply) != 2:
        raise ValueError("Music provider must return a reply/outcome pair")
    return ExecutionResult(*provider_reply)
