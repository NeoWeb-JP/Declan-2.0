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

| `DECLAN_ALLOW_UNCONFIGURED_MA` | Allows the Music Assistant path without its usual configuration guard when set to `1` | Leave unset unless deliberately testing |
| `DECLAN_SPOTIFY_CLIENT_ID` | Spotify API application client ID | Keep secret where applicable |
| `DECLAN_SPOTIFY_CLIENT_SECRET` | Spotify API application client secret | Keep secret |
| `DECLAN_SPOTIFY_MARKET` | Spotify two-letter country market; code defaults to `GB` | `GB` |
| `DECLAN_SPOTIFY_PRESETS` | JSON object of Spotify preset definitions | `{}` |
| `DECLAN_GOOD_MORNING_SCRIPT` | Configurable Home Assistant morning script entity | `script.example_morning` |
| `DECLAN_GOOD_NIGHT_SCRIPT` | Configurable Home Assistant night script entity | `script.example_night` |
| `DECLAN_MOVIE_SCRIPT` | Configurable movie routine script entity | `script.example_movie` |
| `DECLAN_BEDROOM_MOVIE_SCRIPT` | Configurable bedroom movie routine script entity | `script.example_bedroom_movie` |
| `DECLAN_MOVIE_REMOTE` | Configurable movie remote entity | `remote.example` |
| `DECLAN_BEDROOM_MOVIE_REMOTE` | Configurable bedroom movie remote entity | `remote.example_bedroom` |
| `DECLAN_WEB_TTS_ENTITY` | Home Assistant TTS entity for browser voice | `tts.example` |
| `DECLAN_MEDIA_SEARCH_AGENT` | Home Assistant conversation agent for media search | `conversation.example` |
| `DECLAN_WEB_ASSIST_PIPELINE` | Home Assistant Assist pipeline identifier for browser voice | Set to your configured pipeline ID |
| `DECLAN_VISITORS_ENTITY` | Home Assistant visitor-presence input boolean | `input_boolean.example_visitors` |
| `DECLAN_TRUSTED_RELEASES` | Path to updater allow-list for pinned release mode | `/etc/declan/trusted-releases.json` |
| `DECLAN_UPDATE_SOURCE` | Release trust source; `github` (default) or `pinned` | `github` |
| `DECLAN_UPDATE_ROOT` | Optional updater installation root override | Leave unset |
| `DECLAN_UPDATE_SUPERVISED` | Set to `1` only for the supervised updater process | Leave unset |
| `DECLAN_SENSITIVE_ROUTINES` | Legacy sensitive routine categories; current configured confirmation policy takes precedence | `night,guest` |
| `DECLAN_TRUSTED_SPEAKERS` | Comma-separated trusted speaker labels used by legacy confirmation checks; voice identity is not authentication | Leave empty |
| `DECLAN_HISTORY_RETENTION_DAYS` | Voice and transcript history retention in days; accepts 1–30 | `30` |
| `DECLAN_BROWSER_TIMER_SATELLITE` | Optional satellite identifier for browser timer announcements | Leave empty |
| `DECLAN_TIMER_ALARM_MEDIA_ID` | Optional media identifier used for timer alarm playback | Leave empty |
| `DECLAN_WEATHER_ENTITY` | Home Assistant weather entity for contextual conditions | `weather.forecast_home` |
| `DECLAN_INDOOR_TEMPERATURE_ENTITY` | Home Assistant indoor temperature/climate entity | `climate.home` |
| `DECLAN_DEFAULT_COUNTRY` | Default country for contextual information lookups | `GB` |
| `DECLAN_APPROVED_MEDIA_PLAYERS_FILE` | Optional path for per-area approved media player configuration; defaults to `.data/approved-media-players.json` beside `approved_media_players.py` | Leave unset |
| `DECLAN_SPOTIFY_PLAYLISTS_FILE` | Optional path for Spotify playlist catalogue; defaults to `.data/spotify-playlists.json` beside `spotify_playlists.py` | Leave unset |
| `DECLAN_OPENAI_MODEL` | Optional OpenAI planner model override; defaults to an empty string when unset | Leave unset unless configuring the planner |
| `OPENAI_API_KEY` | Optional OpenAI API credential used by the planner when a key is not passed directly; defaults to an empty string when unset | Keep secret; leave unset when the planner is disabled |

The added HA, Assist, bind-address and release-version names were verified against `server.py` on 17 November 2026. This inventory covers names verified in the backend modules listed by the environment documentation regression test, including `updates.py` and `sensitive_confirmations.py`; additional modules may define more settings. Configuration keys in `configuration.py` are stored as named configuration entries and should not be assumed to be read directly from the process environment. Confirm each value's source in the deployment before relying on an environment override.

## Installation

1. Copy [`.env.example`](../.env.example) into the protected server configuration location.
2. Replace placeholder secrets with randomly generated credentials.
3. Restrict access to the file and restart the standalone Declan service.
4. Verify the server and Home Assistant Ingress connections before removing any existing configuration.

Do not commit populated `.env` files, live access tokens, Spotify credentials or OpenAI keys. The Home Assistant Assist bridge token and the Ingress token serve different purposes and must not be reused.

For deployment instructions, see [installation](installation.md) and [Proxmox updates](../PROXMOX-UPDATES.md).
