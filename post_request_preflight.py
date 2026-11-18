"""POST request authentication and route preflight before body parsing."""


def enforce(handler, *, assist_token, ingress, authenticate_assist,
            enforce_known_route, enforce_origin):
    if handler.path in {"/api/assist", "/api/assist/history"}:
        if authenticate_assist(handler, token=assist_token):
            return False
    elif not enforce_known_route(handler):
        return False
    elif not enforce_origin(handler, token=assist_token, ingress=ingress):
        return False
    return True
