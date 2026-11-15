"""OpenAI API credentials. Never return the secret through a status endpoint."""
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

PATH = Path(__file__).resolve().parent / ".data" / "openai-api-key"
LOCK = Lock()


def configured():
    return bool(os.environ.get("OPENAI_API_KEY", "").strip()) or PATH.is_file()


def get_key():
    if PATH.is_file():
        value = PATH.read_text(encoding="utf-8").strip()
    else:
        value = os.environ.get("OPENAI_API_KEY", "").strip()
    if not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,256}", value):
        raise ValueError("OpenAI API key is not configured")
    return value


def replace_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,256}", value):
        raise ValueError("Invalid OpenAI API key")
    with LOCK:
        PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=PATH.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(value + "\n")
        try:
            os.replace(temporary, PATH)
        finally:
            temporary.unlink(missing_ok=True)
