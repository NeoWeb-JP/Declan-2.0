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

The Home Assistant Assist bridge currently has two ways to forward an already-produced reply to the standalone server's authenticated `POST /api/assist/history` endpoint:

1. **Integration-local callback:** `hass.data["declan_two"]["record_assist_reply"]` accepts a dictionary and calls the shared forwarding helper. It is registered per config entry and removed on unload only if the callback is still owned by that entry. This avoids publishing a globally visible Home Assistant event, but it is an internal integration API, not a general-purpose public service or an authentication mechanism for arbitrary Python callers.
2. **Legacy event:** `declan_two_assist_reply` on Home Assistant's global event bus still invokes the same helper. Any integration or automation able to fire that event may submit plausible history data. **Payload validation is not sender authentication.** Do not treat event-sourced history as provenance-verified.

Both paths validate nonblank `message` and `reply` (up to 1,000 characters each); optional `session_id`, `outcome`, and `routine_status` strings (up to 128 characters); and optional `steps` (up to 50 strings of at most 256 characters). Malformed payloads are ignored. The bridge forwards using its configured backend bearer token, so the backend sees the bridge credential rather than the original event producer.

**Migration before disabling the legacy listener:** inventory any Home Assistant scripts, automations and custom integrations that fire `declan_two_assist_reply`, including configuration outside this repository; migrate each supported producer to a trusted recording path; verify that history still captures the intended interaction; then remove the bus subscription and add a regression asserting forged events cannot create history. The repository's native `conversation.py` and `chat_view.py` currently do not publish this event. Removing the listener without checking the deployed Home Assistant configuration may silently lose historical entries. Track the outstanding migration in [issue #17](https://github.com/NeoWeb-JP/Declan-2.0/issues/17).

## Security and operations

The Assist bridge and Ingress have separate credentials. Never commit live tokens or keys. Limit HTTP access to trusted networks or use HTTPS. The server and Home Assistant components are deployed and updated independently.

See [security and privacy](p1-security.md), [installation](installation.md), and [current work](now-work.md) for operational details and active migration limitations.
