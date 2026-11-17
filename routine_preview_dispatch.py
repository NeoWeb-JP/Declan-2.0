"""Dispatch routine preview requests without executing other commands."""


def dispatch_preview(phrase, *, origin_device, satellite, detect_phrase, preview_routine):
    """Return the preview result or None when the phrase is not a preview."""
    preview_phrase = detect_phrase(phrase)
    if not preview_phrase:
        return None
    return preview_routine(preview_phrase, origin_device or satellite)
