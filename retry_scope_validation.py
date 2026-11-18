"""Validate and construct voice retry origin scopes consistently."""


def normalize_origin_id(value):
    """Only accept bounded plain identifiers from Home Assistant."""
    return value if type(value) is str and 0 < len(value) <= 128 else None


def assist_scope(device_id, user_id, satellite):
    """Build an origin-bound Assist scope, or None when origin is unknown."""
    parts = tuple(normalize_origin_id(value)
                  for value in (device_id, user_id, satellite))
    return ("assist", *parts) if any(parts) else None


def valid_retry_scope(scope):
    """Accept a bounded room scope or a canonical four-field Assist origin."""
    if type(scope) is str:
        return bool(scope.strip()) and len(scope) <= 256
    if type(scope) is tuple and len(scope) == 4:
        return (type(scope[0]) is str and scope[0] == "assist"
                and assist_scope(*scope[1:]) == scope)
    return False
