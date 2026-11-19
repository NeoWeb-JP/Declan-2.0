"""OpenAI API credentials. Never return the secret through a status endpoint."""
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from sensitive_write_state import DEFAULT_SENSITIVE_WRITE_STATE

PATH = Path(__file__).resolve().parents[2] / ".data" / "openai-api-key"


def configured():
    return bool(os.environ.get("OPENAI_API_KEY", "").strip()) or PATH.is_file()


def get_key():
    """Read credentials consistently with in-process replacements."""
    with DEFAULT_SENSITIVE_WRITE_STATE.ai_credentials:
        return _read_key()


def _read_key():
    if PATH.is_symlink():
        raise ValueError("Unsafe OpenAI credential path")
    if PATH.is_file():
        if os.name != "nt" and PATH.stat().st_mode & 0o077:
            raise ValueError("OpenAI credential file permissions are unsafe")
        value = PATH.read_text(encoding="utf-8").strip()
    else:
        value = os.environ.get("OPENAI_API_KEY", "").strip()
    if not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,256}", value):
        raise ValueError("OpenAI API key is not configured")
    return value


def replace_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,256}", value):
        raise ValueError("Invalid OpenAI API key")
    with DEFAULT_SENSITIVE_WRITE_STATE.ai_credentials:
        PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=PATH.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(value + "\n")
        try:
            os.replace(temporary, PATH)
        finally:
            temporary.unlink(missing_ok=True)
