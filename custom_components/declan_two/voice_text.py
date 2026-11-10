"""Pronunciation-only adaptation; written names and entity IDs remain unchanged."""
import re


def spoken_text(text):
    return re.sub(r'(?<![\w.])Edd\b', 'Ed', text, flags=re.I)
