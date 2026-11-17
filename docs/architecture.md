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

## Security and operations

The Assist bridge and Ingress have separate credentials. Never commit live tokens or keys. Limit HTTP access to trusted networks or use HTTPS. The server and Home Assistant components are deployed and updated independently.

See [security and privacy](p1-security.md), [installation](installation.md), and [current work](now-work.md) for operational details and active migration limitations.
