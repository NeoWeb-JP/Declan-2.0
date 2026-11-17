# Environment configuration

Declan's standalone backend reads its runtime configuration from its deployment environment. Keep the live environment file private and out of version control.

## Variables documented for operators

| Variable | Purpose | Example |
| --- | --- | --- |
| `DECLAN_INGRESS_TOKEN` | Separate bearer token used by the Home Assistant Ingress proxy | Generate with `openssl rand -hex 32` |
| `DECLAN_VOICEPIPELINE_URL` | Optional URL of the VoicePipeline management API | `http://127.0.0.1:8000` |
| `DECLAN_VOICEPIPELINE_TOKEN` | Optional VoicePipeline API bearer token, if authentication is enabled | Leave empty when not required |

These variables are documented in the existing deployment instructions. This is **not yet a complete inventory** of every `DECLAN_*` setting. Before expanding this reference, verify names and defaults against the current backend configuration code. Do not guess names, defaults, or required/optional status.

## Installation

1. Copy [`.env.example`](../.env.example) into the protected server configuration location.
2. Replace placeholder secrets with randomly generated credentials.
3. Restrict access to the file and restart the standalone Declan service.
4. Verify the server and Home Assistant Ingress connections before removing any existing configuration.

Do not commit populated `.env` files, live access tokens, Spotify credentials or OpenAI keys. The Home Assistant Assist bridge token and the Ingress token serve different purposes and must not be reused.

For deployment instructions, see [installation](installation.md) and [Proxmox updates](../PROXMOX-UPDATES.md).
