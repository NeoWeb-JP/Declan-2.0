"""Single bounded client session identity contract."""


def valid_session_id(value):
    """Accept only nonempty, bounded built-in string IDs."""
    return type(value) is str and 0 < len(value) <= 256
