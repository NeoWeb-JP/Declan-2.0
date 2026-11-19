# Declan 2.0 architecture

## Runtime components

- **Standalone Declan server:** Handles voice requests, intent routing, media and routine orchestration, and history/management APIs.
- **Home Assistant Assist Bridge** (`custom_components/declan_two`): Registers the conversation, STT and TTS platforms and exposes authenticated management routes and the native Home Assistant panel.
- **Home Assistant app / Ingress:** Proxies the server into the Home Assistant UI. Its ingress token is separate from the Assist bridge token.
- **Optional upstream services:** VoicePipeline/Wyoming for speaker recognition or transcription, ElevenLabs for speech synthesis, and Music Assistant for playback.

## Request path

1. A satellite or Home Assistant Assist client captures an utterance.
2. The configured STT path transcribes the audio. When configured, VoicePipeline supplies speaker identity.
3. The Assist bridge forwards the request to the Declan server.
4. The server resolves the intent, chooses an approved Home Assistant action, routine or media player, and records the outcome.
5. Home Assistant executes the selected actions. The response returns through the configured TTS path.

The server owns the command decisions; Home Assistant owns entities, scripts, devices and areas. Keep routine implementation in Home Assistant rather than duplicating entity IDs in the server.

## Assist reply history and trust boundary

The Home Assistant Assist bridge forwards an already-produced reply to the standalone server's authenticated `POST /api/assist/history` endpoint through an integration-local callback:

1. **Integration-local callback:** `hass.data["declan_two"]["record_assist_reply"]` accepts a dictionary and calls the shared forwarding helper. It is registered per config entry and removed on unload only if the callback is still owned by that entry. This avoids publishing a globally visible Home Assistant event, but it is an internal integration API, not a general-purpose public service or an authentication mechanism for arbitrary Python callers.
The legacy `declan_two_assist_reply` global event listener has been removed. Publishing that event no longer forwards history. `tests/test_assist_bridge.py` verifies that setup does not register a bus listener and that the internal callback validates forwarded data. The callback remains accessible to trusted in-process Python code; it is not an isolation boundary against another installed integration.

The callback validates nonblank `message` and `reply` (up to 1,000 characters each); optional `session_id`, `outcome`, and `routine_status` strings (up to 128 characters); and optional `steps` (up to 50 strings of at most 256 characters). Malformed payloads are ignored. The bridge forwards using its configured backend bearer token, so the backend sees the bridge credential rather than the original Python caller.

**Outstanding deployment migration:** inventory Home Assistant scripts, automations and custom integrations outside this repository that still fire `declan_two_assist_reply`. Migrate supported producers to a trusted recording path and verify that their intended history entries arrive. Repository Python sources contain no publishers, but this does not verify deployed Home Assistant configuration. External event publishers now silently lose their history entries until migrated; do not restore the global listener to accommodate them. Track external migration evidence in [issue #17](https://github.com/NeoWeb-JP/Declan-2.0/issues/17).

## Security and operations

The Assist bridge and Ingress have separate credentials. Never commit live tokens or keys. Limit HTTP access to trusted networks or use HTTPS. The server and Home Assistant components are deployed and updated independently.

See [security and privacy](p1-security.md), [installation](installation.md), and [current work](now-work.md) for operational details and active migration limitations.
