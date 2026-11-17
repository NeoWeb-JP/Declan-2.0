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

## Verification scope and remaining checks

The environment inventory has automated regression coverage for runtime reads in production Python modules, including indexed `os.environ` access and `get`, `setdefault`, and `pop` calls. The checks detect newly introduced names and require documented purposes/examples, but **inventory completeness does not prove every default, precedence rule, or invalid-value behaviour has been exercised**. Do not mark the repo-wide defaults audit complete based on inventory coverage alone.

Verified runtime behaviour has dedicated tests for history retention, persisted configuration fallback, media-player and Spotify catalogue paths, OpenAI planner model/key selection, updater source/root/supervision, and sensitive routine/trusted speaker settings. Other entries still require a source-level defaults/override audit, with tests where the behaviour is safety-critical. Distinguish process environment from Home Assistant config-entry options and values persisted in Declan's configuration store. Never place real tokens or personal credentials in documentation fixtures.

When closing the remaining [P2 documentation task](https://github.com/NeoWeb-JP/Declan-2.0/issues/17), record which runtime settings were checked, their unset/empty/invalid handling, and whether tests enforce the documented defaults. Update this table and `.env.example` together when a setting changes.

The added HA, Assist, bind-address and release-version names were verified against `server.py` on 17 November 2026. This inventory covers names verified in the backend modules listed by the environment documentation regression test, including `updates.py` and `sensitive_confirmations.py`; additional modules may define more settings. Configuration keys in `configuration.py` are stored as named configuration entries and should not be assumed to be read directly from the process environment. Confirm each value's source in the deployment before relying on an environment override.

## Verified runtime defaults and precedence

The following behaviours are exercised by dedicated regression tests. These
describe runtime behaviour, not merely the presence of an inventory entry.

| Setting | Unset or empty | Override and invalid handling | Test |
| --- | --- | --- | --- |
| DECLAN_WEATHER_ENTITY  | Uses `weather.forecast_home` when unset | Trims valid weather entity IDs; malformed IDs are rejected before a request | `tests/test_conditions_environment_defaults.py` |
| DECLAN_INDOOR_TEMPERATURE_ENTITY  | Uses the configured climate default when unset | Valid entity overrides are accepted; malformed entities are rejected | `tests/test_conditions_environment_defaults.py` |
| DECLAN_SPOTIFY_PRESETS  | Built-in presets remain available | Valid JSON object entries override presets; malformed JSON and invalid references are ignored | `tests/test_spotify_presets_environment_defaults.py` |
| DECLAN_SPOTIFY_CLIENT_ID, DECLAN_SPOTIFY_CLIENT_SECRET  | Missing or partial credentials are unconfigured | Both environment values are trimmed; valid saved settings take precedence and invalid saved settings do not silently fall back | `tests/test_spotify_credential_environment_defaults.py` |
| DECLAN_ALLOW_UNCONFIGURED_MA  | Compatibility discovery is disabled | Only the exact value `1` enables discovery of registered Music Assistant players; approved mappings take precedence | `tests/test_music_assistant_compat_environment.py` |
| DECLAN_SPOTIFY_MARKET  | Defaults to `GB` when unset | Trims and uppercases a two-letter code; empty or invalid codes fail before a search request | `tests/test_spotify_market_environment_defaults.py` |
| DECLAN_INGRESS_TOKEN  | Missing or short tokens cannot authenticate | Requires an exact token match of at least 32 characters and must differ from the Assist token | `tests/test_ingress_token_environment_defaults.py` |
| DECLAN_BROWSER_TIMER_SATELLITE | Unset or blank browser satellite disables timer output resolution | Trims configured satellite ID, rejects malformed IDs before contacting HA, and rejects mismatched HA resolution | `tests/test_browser_timer_satellite_environment.py` |
| DECLAN_TIMER_ALARM_MEDIA_ID | Unset or blank uses a spoken timer announcement | Trims media-source IDs; unsupported schemes or rejected media playback fall back to speech | `tests/test_timer_alarm_media_environment.py` |
| DECLAN_VOICEPIPELINE_URL | Missing or blank URL fails before network access | Trims trailing slash and whitespace; malformed or unsafe URLs fail before network access | `tests/test_voicepipeline_environment_defaults.py` |
| DECLAN_VOICEPIPELINE_TOKEN | Unset or blank omits the Authorization header | Trims nonempty tokens and sends them as bearer credentials | `tests/test_voicepipeline_environment_defaults.py` |
| DECLAN_BIND_ADDRESS | Normal mode binds to `127.0.0.1` and ignores this override; Assist LAN mode defaults to `0.0.0.0` | In Assist LAN mode accepts IPv4 addresses only, rejecting invalid addresses before binding; requires an Assist token of at least 32 characters | `tests/test_bind_address_environment_defaults.py` |
| DECLAN_UPDATE_SOURCE | Defaults to `github` when unset | Accepts `github` or `pinned` after trimming whitespace; rejects blank, unknown and differently cased values | `tests/test_release_source_environment_defaults.py` |
| DECLAN_UPDATE_ROOT | Missing or blank disables the updater | Requires an absolute POSIX root with writable directories, a releases directory and a current symlink pointing to the running app | `tests/test_update_root_environment_defaults.py` |
| DECLAN_UPDATE_SUPERVISED | Missing or blank blocks installation | Only exact `1` passes the supervisor gate; other values fail before release selection or staging | `tests/test_update_supervised_environment_gate.py` |
| DECLAN_RELEASE_VERSION | Optional configured fallback when no valid installed release marker exists | A valid installed `.declan-release` marker takes precedence; missing, invalid or unreadable markers preserve the fallback | `tests/test_installed_release_version_defaults.py` |

The Spotify credential source can also be a persisted settings file, not just
the process environment. The `DECLAN_WEB_TTS_ENTITY` and
`DECLAN_VISITORS_ENTITY` values are read through Declan's configuration
store in `server.py`, rather than directly from `os.environ` at their use
sites. Treat the inventory as an operator-facing configuration guide, not proof
that every listed key is a direct environment override.

## Installation

1. Copy [`.env.example`](../.env.example) into the protected server configuration location.
2. Replace placeholder secrets with randomly generated credentials.
3. Restrict access to the file and restart the standalone Declan service.
4. Verify the server and Home Assistant Ingress connections before removing any existing configuration.

Do not commit populated `.env` files, live access tokens, Spotify credentials or OpenAI keys. The Home Assistant Assist bridge token and the Ingress token serve different purposes and must not be reused.

For deployment instructions, see [installation](installation.md) and [Proxmox updates](../PROXMOX-UPDATES.md).
