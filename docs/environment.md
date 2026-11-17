# Environment configuration

Declan's standalone backend reads its runtime configuration from its deployment environment. Keep the live environment file private and out of version control.

## Variables documented for operators

| Variable | Purpose | Example |
| --- | --- | --- |
| `DECLAN_HA_URL` | Home Assistant API base URL used by the standalone backend | Set to your HA URL |
| `DECLAN_HA_TOKEN` | Home Assistant API access token | Keep secret |
| `DECLAN_ASSIST_TOKEN` | Bearer token for the Assist bridge; server requires at least 32 characters for LAN Assist | Generate a separate long random secret |
| `DECLAN_BIND_ADDRESS` | Optional server bind address override | Configure for your network |
| `DECLAN_RELEASE_VERSION` | Optional release version override for server reporting | Leave unset unless needed |
| `DECLAN_INGRESS_TOKEN` | Separate bearer token used by the Home Assistant Ingress proxy | Generate with `openssl rand -hex 32` |
| `DECLAN_VOICEPIPELINE_URL` | Optional URL of the VoicePipeline management API | `http://127.0.0.1:8000` |
| `DECLAN_VOICEPIPELINE_TOKEN` | Optional VoicePipeline API bearer token, if authentication is enabled | Leave empty when not required |

The added HA, Assist, bind-address and release-version names were verified against `server.py` on 17 November 2026. This is **not yet a complete inventory** of every `DECLAN_*` setting. Before expanding this reference, verify names and defaults against the current backend configuration code. Do not guess names, defaults, or required/optional status.

## Installation

1. Copy [`.env.example`](../.env.example) into the protected server configuration location.
2. Replace placeholder secrets with randomly generated credentials.
3. Restrict access to the file and restart the standalone Declan service.
4. Verify the server and Home Assistant Ingress connections before removing any existing configuration.

Do not commit populated `.env` files, live access tokens, Spotify credentials or OpenAI keys. The Home Assistant Assist bridge token and the Ingress token serve different purposes and must not be reused.

For deployment instructions, see [installation](installation.md) and [Proxmox updates](../PROXMOX-UPDATES.md).
