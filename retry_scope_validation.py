"""Validate voice retry origin scopes at creation and consumption."""


def valid_retry_scope(scope):
    """Accept a bounded room scope or the four-field Assist origin tuple."""
    if type(scope) is str:
        return bool(scope.strip()) and len(scope) <= 256
    if type(scope) is tuple and len(scope) == 4:
        return (scope[0] == "assist"
                and any(value is not None for value in scope[1:])
                and all(value is None or (type(value) is str and 0 < len(value) <= 128)
                        for value in scope[1:]))
    return False
