"""Home Assistant media title search dispatch."""
import json
import re
from urllib.error import HTTPError
from declan.core.execution_results import ExecutionResult, Outcome


def search_media_result(phrase, *, config, connect, agents, request_factory):
    match = re.fullmatch(
        r"(?:where can i (?:watch|stream|find)|(?:search|look) for|find (?:the )?(?:movie|film|show)|"
        r"start (?:movie time|cinema time|cinema mode) and play(?: the (?:movie|film|show))?) (.+)",
        phrase,
    )
    if not match:
        return None
    title = match[1].strip()
    if len(title) > 200 or re.search(r"\b(?:and|then)\s+(?:turn|switch|dim|brighten|set|start|stop|unlock|lock|open|play)\b", title):
        return ExecutionResult("Please ask for the film or show separately from any device commands.", Outcome.UNRESOLVED)
    agent = config.get("DECLAN_MEDIA_SEARCH_AGENT", "").strip()
    if agent and not re.fullmatch(r"conversation\.[a-z0-9_]+", agent):
        return ExecutionResult("The Declan Local media search agent isn't configured.", Outcome.NOT_CONFIGURED)
    connection = connect()
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    url, headers, opener = connection
    try:
        agent = agents.resolve(connection, agent)
    except agents.MediaAgentUnavailable as error:
        return ExecutionResult(str(error), Outcome.UNAVAILABLE)
    except agents.MediaAgentError as error:
        return ExecutionResult(str(error), Outcome.NOT_CONFIGURED)

    try:
        request = request_factory(f"{url}/api/services/conversation/process?return_response",
                          data=json.dumps({"agent_id": agent, "text": f"where can i watch {title}"}).encode(),
                          headers=headers)
        with opener.open(request, timeout=18) as response:
            payload = json.loads(response.read(1024 * 1024))["service_response"]["response"]
        reply = payload["speech"]["plain"]["speech"]
        if isinstance(reply, str) and reply.strip() and payload.get("response_type") != "error":
            return ExecutionResult(reply.strip(), Outcome.SEARCH_RESULT)
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return ExecutionResult("I couldn't get a title search result from Declan Local.", Outcome.UNVERIFIED)
