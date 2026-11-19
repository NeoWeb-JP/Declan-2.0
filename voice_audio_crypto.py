"""Transitional alias for declan.voice.voice_audio_crypto; remove one release after the package move.

Releases installed before the package move run their updater from the *old* layout.
When it stages this release it checks that this file exists and runs
``from voice_audio_crypto import _aesgcm`` inside the staged directory, so without
this file that update would be refused. New code must import from declan.voice.
"""
from declan.voice.voice_audio_crypto import MAGIC, _aesgcm, _key, decrypt, encrypt  # noqa: F401
