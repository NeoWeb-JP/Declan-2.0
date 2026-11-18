"""Shared input contract for bounded automatic voice retry learning."""

MAX_RETRY_PHRASE_LENGTH = 4096


def valid_retry_phrase(value):
    """Only accept a nonblank bounded plain transcript."""
    return (type(value) is str and bool(value.strip())
            and len(value) <= MAX_RETRY_PHRASE_LENGTH)
