# Local voice sample encryption deployment

This is an **opt-in migration requiring operator action**. The actual speaker recognition recordings live in the separate VoicePipeline service and are **not** encrypted by this change.

1. Install Python `cryptography==46.0.3` in the Declan backend runtime. CI installs this version, but runtime packaging must be checked before deployment.
2. Generate a 32-byte random key with a secure secret manager. Supply its URL-safe base64 representation as `DECLAN_VOICE_AUDIO_KEY`. Keep it **outside** the Declan data directory, source control, logs and snapshots. Back up the key separately in a secure location. Never rotate it without a dedicated re-encryption migration.
3. Stop the Declan backend to prevent concurrent writes. Confirm the exact `.data/voice-profiles.sqlite3` path.
4. Run `python -m migrate_voice_audio --database /path/to/.data/voice-profiles.sqlite3` with the key available in the environment. The migration is idempotent, verifies existing encrypted samples against the configured key, and VACUUMs after conversion.
5. Restart and verify preview/export of local samples, consent revocation and new sample saving. Test an incorrect/missing key fails closed. Do not delete the separately protected key backup.

**Compatibility:** existing plaintext samples cannot be previewed/exported until migrated. New samples cannot be saved without the key and cryptography dependency. Roll back application code only with an explicit plan: old code cannot read encrypted samples. The migration does not cover filesystem copies, snapshots outside the local upgrade directory, or VoicePipeline.

## Preparing the production dependency lock

On the target Linux/Python environment, run `python generate_voice_dependency_lock.py`. This downloads `websocket-client==1.9.2`, `cryptography==46.0.3` and resolved transitive wheels, then writes `requirements-web-voice.txt.candidate` without modifying the active lock. Review the candidate and test `pip install --require-hashes --only-binary=:all: -r requirements-web-voice.txt.candidate` in a fresh virtual environment. Only then replace and commit `requirements-web-voice.txt` in a separate reviewed change. Locks generated for one platform may need additional hashes for other target architectures. **Until the production lock is updated, encryption releases are intentionally blocked by the preflight in #502.**
