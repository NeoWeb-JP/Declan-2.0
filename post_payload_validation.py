"""POST JSON body validation and VoicePipeline management access boundary."""

import post_payload_http
import post_validation_errors_http
import request_validation
import voicepipeline_access_http


def read_authorized_body(handler, *, ingress):
    """Read JSON then enforce VoicePipeline permissions before any route dispatch."""
    body = post_payload_http.read_json_body(handler)
    if not voicepipeline_access_http.enforce_access(handler, body, ingress=ingress):
        return None
    return body


def message_and_session(body):
    """Preserve the existing conversation input-validation contract."""
    return request_validation.message_and_session(body)


def send_validation_error(handler):
    """Preserve the existing HTTP validation error response."""
    return post_validation_errors_http.send_validation_error(handler)
