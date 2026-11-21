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
| `DECLAN_MUSIC_REPLY_FIRST` | Also in Settings → Music behaviour; a value saved there wins over this variable. On by default: Declan answers a play request as soon as Home Assistant accepts it ("Starting ..."), with outcome `requested`. Playback is then verified in the background, the result is added to the request's diagnostics trace, and a failure is announced on the originating satellite. Set to `0` (or `false`, `no`, `off`) for the slower reply that is spoken only after verification | Leave unset for faster music replies |
| `DECLAN_MUSIC_START_VOLUME` | Also in Settings → Music behaviour; a value saved there wins over this variable. Percentage music starts at. Before Declan starts or moves music, any speaker louder than this is turned down to it; quieter speakers are left alone. For a group ("everywhere"), each member speaker is turned down. Default `30`; `0` turns it off | Leave unset for 30% |
| `DECLAN_MUSIC_ASSISTANT_SEARCH` | Also in Settings → Music behaviour; a value saved there wins over this variable. Set to `1` to let Music Assistant search for Spotify requests. "Play X" sends X (and a "by" artist) to `music_assistant.play_media` on the resolved speaker, room, `everywhere`, `upstairs` or `downstairs` player. Declan's own Spotify search, search cache, curated playlists, saved links and disliked-list checks are bypassed (the code is kept). Radio and queue moves are unchanged | Leave unset to keep Declan's Spotify search |
| `DECLAN_COMMAND_STYLE` | Also in Settings → Voice & learning; a value saved there wins. `any` (default), `question`, `my_bru` or `either`. Satellite (HA Assist) turns in another style are ignored silently, with no reply, no follow-up and no action. Control words, yes/no, real questions and replies to Declan's own prompts always pass | Leave unset |
| `DECLAN_GUEST_TONE` | Also in Settings → Household; a value saved there wins. `home` (default): guests and visitors hear the household's own lines. `polite`: the separate guest line set (FUT-60) | Leave unset |
| `DECLAN_SHELVE_DAYS` | Also in Settings → Household. Days a used sass line, roast or response rests before it can be said again; `0` turns resting off; default `3`, maximum `30` (FUT-61) | Leave unset |
| `DECLAN_FRESH_LINES` | Also in Settings → Household. Write new lines in the background when a category runs low; on unless `0`, `false`, `no` or `off` (FUT-61) | Leave unset |
| `DECLAN_FRESH_LINES_BUDGET_USD` | Monthly limit for writing new lines, on top of the main AI ledger; default `1.00`, capped at `20` (FUT-61) | Leave unset |
| `DECLAN_CHRISTMAS_MODE` | Also in Settings → Household; a saved value (or "Christmas mode on/off") wins. `auto` (default: 1 December to 2 January), `on` or `off` (FUT-59) | Leave unset |
| `DECLAN_WIFI_NAME` | Also in Settings → Household. The guest Wi-Fi network name read out for "what's the Wi-Fi password?" (FUT-59) | Set in Settings instead |
| `DECLAN_WIFI_PASSWORD` | Also in Settings → Household. The guest Wi-Fi password read out (and spelled) for "what's the Wi-Fi password?"; empty keeps it secret. Plain text, so use a guest network (FUT-59) | Set in Settings instead |
| `DECLAN_REMINDER_NOTIFY` | Comma-separated notify services (`notify.mobile_app_jaco,notify.mobile_app_edd`) that also receive a reminder's first ring (FUT-26). Unset: reminders only ring on the satellite | Optional |
| `DECLAN_SPEAKER_THRESHOLD` | Also in Settings → Voice & learning; a value saved there wins over this variable. VoicePipeline match confidence (`0.30`–`0.99`, same scale as a speaker's average confidence) at which a speaker counts as recognised for History labels and duplicate-capture arbitration. Default `0.85` (VOI-08). History labels never need more than `0.75`. Sensitive-routine confirmations always keep their own `0.85` floor | Leave unset; lower it in Settings once the History → Understanding card shows your real confidence range |
| `DECLAN_SPOTIFY_SEARCH_CACHE_DAYS` | Days a resolved Spotify track/album/artist search is remembered; `0` disables; default `7` | `7` |
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
| `DECLAN_GUEST_MODE_ENTITY` | Guest authority helper, with saved-setting precedence | `input_boolean.guest_mode` |
| `DECLAN_GUEST_REGISTER_ENTITY` | Guest names helper, with saved-setting precedence | `input_text.guests_in_charge` |
| `DECLAN_PROJECTOR_POWER_ENTITY` | Projector power helper, with saved-setting precedence | `switch.projector_power_socket` |
| `DECLAN_RESIDENT_ONE_NAME` | Optional first resident display name | Leave empty for generic wording |
| `DECLAN_RESIDENT_TWO_NAME` | Optional second resident display name | Leave empty for generic wording |
| `DECLAN_DOG_NAME` | Optional dog display name | Leave empty for generic wording |
| `DECLAN_CAT_NAME` | Optional cat display name | Leave empty for generic wording |
| `DECLAN_TRUSTED_RELEASES` | Path to updater allow-list for pinned release mode | `/etc/declan/trusted-releases.json` |
| `DECLAN_UPDATE_SOURCE` | Release trust source; `github` (default) or `pinned` | `github` |
| `DECLAN_UPDATE_ROOT` | Optional updater installation root override | Leave unset |
| `DECLAN_UPDATE_SUPERVISED` | Set to `1` only for the supervised updater process | Leave unset |
| `DECLAN_SENSITIVE_ROUTINES` | Sensitive routine categories that need a spoken yes; a saved routine policy takes precedence. `security` covers homelab, server, camera, CCTV and alarm routines | `guest,security` |
| `DECLAN_TRUSTED_SPEAKERS` | Comma-separated trusted speaker labels used by legacy confirmation checks; voice identity is not authentication | Leave empty |
| `DECLAN_HISTORY_RETENTION_DAYS` | Voice and transcript history retention in days; accepts 1–30 | `30` |
| `DECLAN_BROWSER_TIMER_SATELLITE` | Optional satellite identifier for browser timer announcements | Leave empty |
| `DECLAN_TIMER_ALARM_MEDIA_ID` | Optional media identifier used for timer alarm playback | Leave empty |
| `DECLAN_WEATHER_ENTITY` | Home Assistant weather entity for contextual conditions | `weather.forecast_home` |
| `DECLAN_INDOOR_TEMPERATURE_ENTITY` | Home Assistant indoor temperature/climate entity | `climate.home` |
| `DECLAN_DEFAULT_COUNTRY` | Default country for contextual information lookups | `GB` |
| `DECLAN_APPROVED_MEDIA_PLAYERS_FILE` | Optional path for per-area approved media player configuration; defaults to `.data/approved-media-players.json` beside `approved_media_players.py` | Leave unset |
| `DECLAN_SPOTIFY_PLAYLISTS_FILE` | Optional path for Spotify playlist catalogue; defaults to `.data/spotify-playlists.json` beside `spotify_playlists.py` | Leave unset |
| `DECLAN_OPENAI_MODEL` | Legacy direct-Python planner default only; never overrides the live native AI settings | Configure the live model, pricing and lifecycle in native Settings |
| `OPENAI_API_KEY` | Optional OpenAI API credential used by the planner when a key is not passed directly; defaults to an empty string when unset | Keep secret; leave unset when the planner is disabled |
| `DECLAN_VOICE_AUDIO_KEY` | Base64url-encoded 32-byte AES-GCM key for local voice samples and release readiness; no generated default | Provision securely outside `.data`; see the local voice encryption deployment guide |
| `DECLAN_VOICE_AUDIO_KEY_ID` | Optional name for the current voice key (1-32 letters, digits, `.`, `-`, `_`). When set, new samples record it (DVAE2 format) so the key can be rotated later | Leave unset until you plan to rotate; older releases cannot read DVAE2 samples |
| `DECLAN_VOICE_AUDIO_PREVIOUS_KEYS` | Optional retired keys, decrypt only, as comma-separated `id:base64key` entries | Set only during a rotation, then remove after `migrate_voice_audio --rewrap` |

## Verification scope and remaining checks

The environment inventory has automated regression coverage for runtime reads in production Python modules, including indexed `os.environ` access and `get`, `setdefault`, and `pop` calls. The checks detect newly introduced names and require documented purposes/examples, but **inventory completeness does not prove every default, precedence rule, or invalid-value behaviour has been exercised**. Do not mark the repo-wide defaults audit complete based on inventory coverage alone.

As of main after #750, every operator inventory entry is mapped below to default/override guidance and existing regression files. The coverage guard also includes every key in `configuration.FIELDS`, whose environment fallback is indirect. Test-file existence alone is not behavior verification; country fallback, helper validation, safe display names and saved-setting precedence were separately exercised during this audit. Distinguish process environment from Home Assistant config-entry options and values persisted in Declan's configuration store. Never place real tokens or personal credentials in documentation fixtures.

When closing the remaining [P2 documentation task](https://github.com/NeoWeb-JP/Declan-2.0/issues/17), record which runtime settings were checked, their unset/empty/invalid handling, and whether tests enforce the documented defaults. Update this table and `.env.example` together when a setting changes.

The inventory covers literal reads across production Python modules plus indirect fallbacks for every key in `configuration.FIELDS`. The latter use saved nonempty values first, then environment values, then the consumer's explicit default when the environment variable is absent. An explicitly blank environment value is preserved by `configuration.get`; individual consumers decide whether to reject it, discover a provider or use a fallback. Home Assistant config-entry options are a separate configuration source. Dynamically constructed environment names outside this allowlist are not proven by the literal-read scanner.

## Verified runtime defaults and precedence

The following behaviours are exercised by dedicated regression tests. These
describe runtime behaviour, not merely the presence of an inventory entry.

| Setting | Unset or empty | Override and invalid handling | Test |
| --- | --- | --- | --- |
| DECLAN_GUEST_MODE_ENTITY, DECLAN_GUEST_REGISTER_ENTITY, DECLAN_PROJECTOR_POWER_ENTITY | Missing uses the corresponding legacy helper default; explicitly blank is invalid | Saved nonempty values override environment; correct entity domain and lowercase ID required before dispatch | `tests/test_household_entities.py`, `tests/test_settings_precedence.py` |
| DECLAN_RESIDENT_ONE_NAME, DECLAN_RESIDENT_TWO_NAME, DECLAN_DOG_NAME, DECLAN_CAT_NAME | Missing, blank or invalid names render generic wording | Saved nonempty values override environment; safe names are trimmed at rendering and substituted only where referenced | `tests/test_household_language.py`, `tests/test_settings_precedence.py` |
| DECLAN_APPROVED_MEDIA_PLAYERS_FILE, DECLAN_SPOTIFY_PLAYLISTS_FILE | Missing or blank uses the corresponding module-local `.data` JSON file | Nonempty paths override the default without trimming or absolute-path validation; protect the deployment environment | `tests/test_environment_file_path_defaults.py` |
| DECLAN_ASSIST_TOKEN | Missing or short token prevents Assist LAN startup | Requires at least 32 characters at startup; request authorization uses the exact token. Ingress must use a different token | `tests/test_bind_address_environment_defaults.py`, `tests/test_http.py` |
| DECLAN_DEFAULT_COUNTRY | Missing defaults to `GB`; blank supplies no country preference | Uppercases without trimming. Unique matching country is used only without usable HA coordinates; ambiguous matches stay unresolved | `tests/test_country_environment_defaults.py` |
| DECLAN_HISTORY_RETENTION_DAYS | Missing defaults to 30 days; blank is invalid | Accepts integer days 1–30; malformed, padded and out-of-range values raise an error rather than silently weakening retention | `tests/test_history_retention_environment.py` |
| DECLAN_OPENAI_MODEL, OPENAI_API_KEY | Missing or blank planner configuration fails before network access | Explicit arguments override environment; model must pass supported-name validation and key must contain non-whitespace text | `tests/test_openai_planner.py` |
| DECLAN_WEATHER_ENTITY  | Uses `weather.forecast_home` when unset | Trims valid weather entity IDs; malformed IDs are rejected before a request | `tests/test_conditions_environment_defaults.py` |
| DECLAN_INDOOR_TEMPERATURE_ENTITY  | Uses the configured climate default when unset | Valid entity overrides are accepted; malformed entities are rejected | `tests/test_conditions_environment_defaults.py` |
| DECLAN_SPOTIFY_PRESETS  | Built-in presets remain available | Valid JSON object entries override presets; malformed JSON and invalid references are ignored | `tests/test_spotify_presets_environment_defaults.py` |
| DECLAN_SPOTIFY_CLIENT_ID, DECLAN_SPOTIFY_CLIENT_SECRET  | Missing or partial credentials are unconfigured | Both environment values are trimmed; valid saved settings take precedence and invalid saved settings do not silently fall back | `tests/test_spotify_credential_environment_defaults.py` |
| DECLAN_ALLOW_UNCONFIGURED_MA  | Compatibility discovery is disabled | Only the exact value `1` enables discovery of registered Music Assistant players; approved mappings take precedence | `tests/test_music_assistant_compat_environment.py` |
| DECLAN_MUSIC_REPLY_FIRST | Used only when Settings → Music behaviour has not been saved (`.data/music-settings.json`). On unless set to `0`, `false`, `no` or `off` (case-insensitive, trimmed) | Replies "Starting …" (outcome `requested`) once Music Assistant accepts the play command, then verifies in the background, amends the saved trace and announces a failed start on the satellite | `tests/test_music_reply_first.py` |
| DECLAN_MUSIC_START_VOLUME | Used only when no start volume is saved in Settings → Music behaviour (`.data/music-settings.json`). Whole number; unset or invalid means 30, `0` or below turns it off, values above 100 are capped | Sends `media_player.volume_set` to each louder target speaker before the play request; failures never block playback | `tests/test_music_start_volume.py` |
| DECLAN_MUSIC_ASSISTANT_SEARCH | Used only when Settings → Music behaviour has not been saved. Off unless `1`, `true`, `yes` or `on` (case-insensitive, trimmed) | Sends the spoken title to Music Assistant play_media with a `track` (when "by" artist is given) or `playlist` (titles ending "music"/"playlist") type hint; no Spotify API calls; verification accepts any new playback on the player | `tests/test_music_assistant_search.py` |
| DECLAN_COMMAND_STYLE | Used only when Settings → Voice & learning has no saved style (`.data/command-style.json`). `any` unless `question`, `my_bru` or `either` (case-insensitive, trimmed) | Satellite turns in another style get an empty reply, `continue_conversation` false and outcome `ignored`; nothing is dispatched or learned | `tests/test_command_style_gate.py` |
| DECLAN_GUEST_TONE | Used only when Settings → Household has no saved tone (`.data/household-settings.json`). `home` unless `polite` (case-insensitive, trimmed) | With `home`, Guest Mode and visitors use the household's line set; `polite` restores the separate guest lines. Guest Mode authority is unaffected | `tests/test_household_settings.py` |
| DECLAN_SHELVE_DAYS | Used only when nothing is saved in Settings → Household. Whole number `0`–`30`; anything else means 3 | A said line isn't picked again for this many days; `0` turns resting off | `tests/test_line_freshness.py` |
| DECLAN_FRESH_LINES | Used only when nothing is saved in Settings → Household. On unless `0`, `false`, `no` or `off` | When a category has fewer than three rested lines, one background request writes new lines | `tests/test_line_freshness.py` |
| DECLAN_FRESH_LINES_BUDGET_USD | Defaults to `1.00` when unset or invalid; capped at `20` | Generation stops for the month once this is spent; each request also reserves and settles through the main AI ledger | `tests/test_line_freshness.py` |
| DECLAN_CHRISTMAS_MODE | Used only when nothing is saved in Settings → Household (saying "Christmas mode on/off" saves a value). `auto` unless `on` or `off` | `auto` is on from 1 December to 2 January | `tests/test_christmas.py` |
| DECLAN_WIFI_NAME | Used only when nothing is saved in Settings → Household. Up to 63 plain characters | Read out before the password | `tests/test_christmas.py` |
| DECLAN_WIFI_PASSWORD | Used only when nothing is saved in Settings → Household. Up to 63 plain characters; empty keeps it secret | Read out and spelled for "what's the Wi-Fi password?" | `tests/test_christmas.py` |
| DECLAN_REMINDER_NOTIFY | Unset or empty means satellites only. Entries that aren't `notify.<name>` are ignored | Calls `notify.<name>` with title "Declan" and the reminder text once, on the first ring; failures never stop the satellite announcement | `tests/test_reminders.py` |
| DECLAN_SPEAKER_THRESHOLD | Used only when Settings → Voice & learning has no saved threshold (`.data/speaker-settings.json`). Values outside `0.30`–`0.99` or non-numbers are ignored and `0.85` applies | Capture arbitration uses the threshold; History labels use the lower of it and `0.75`; `DECLAN_TRUSTED_SPEAKERS` confirmations stay at `0.85` | `tests/test_speaker_threshold_and_understanding.py` |
| DECLAN_SPOTIFY_SEARCH_CACHE_DAYS | Defaults to 7 days when unset or invalid; `0` disables; capped at 365 | Repeat lookups of the same title/artist/market return the remembered result without calling Spotify; expired or disliked entries are dropped; playlist picks are never cached | `tests/test_spotify_search_cache.py` |
| DECLAN_SPOTIFY_MARKET  | Defaults to `GB` when unset | Trims and uppercases a two-letter code; empty or invalid codes fail before a search request | `tests/test_spotify_market_environment_defaults.py` |
| DECLAN_INGRESS_TOKEN  | Missing or short tokens cannot authenticate | Requires an exact token match of at least 32 characters and must differ from the Assist token | `tests/test_ingress_token_environment_defaults.py` |
| DECLAN_BROWSER_TIMER_SATELLITE | Unset or blank browser satellite disables timer output resolution | Trims configured satellite ID, rejects malformed IDs before contacting HA, and rejects mismatched HA resolution | `tests/test_browser_timer_satellite_environment.py` |
| DECLAN_TIMER_ALARM_MEDIA_ID | Unset or blank uses a spoken timer announcement | Trims media-source IDs; unsupported schemes or rejected media playback fall back to speech | `tests/test_timer_alarm_media_environment.py` |
| DECLAN_VOICEPIPELINE_URL | Missing or blank URL fails before network access | Trims trailing slash and whitespace; malformed or unsafe URLs fail before network access | `tests/test_voicepipeline_environment_defaults.py` |
| DECLAN_VOICEPIPELINE_TOKEN | Unset or blank omits the Authorization header | Trims nonempty tokens and sends them as bearer credentials | `tests/test_voicepipeline_environment_defaults.py` |
| DECLAN_VOICE_AUDIO_KEY | No default; missing or blank fails key validation and release readiness | Requires valid base64url encoding of exactly 32 bytes; no whitespace trimming, auto-generation or automatic key rotation (rotation is an explicit `--rewrap` step). Wrong keys fail sample authentication. Local samples only, not shared VoicePipeline storage | `tests/test_voice_audio_encryption.py`, `tests/test_voice_encryption_readiness.py` |
| DECLAN_VOICE_AUDIO_KEY_ID | Unset keeps the original DVAE1 sample format | Trimmed; must be 1-32 of `A-Za-z0-9_.-`, otherwise key validation and release readiness fail. When set, new samples use DVAE2 with the ID bound to the ciphertext | `tests/test_voice_key_rotation.py` |
| DECLAN_VOICE_AUDIO_PREVIOUS_KEYS | Unset means no retired keys | Comma-separated unique `id:base64key` entries, each exactly 32 bytes; must not repeat the current key ID. Used only to decrypt; malformed values fail validation | `tests/test_voice_key_rotation.py` |
| DECLAN_BIND_ADDRESS | Normal mode binds to `127.0.0.1` and ignores this override; Assist LAN mode defaults to `0.0.0.0` | In Assist LAN mode accepts IPv4 addresses only, rejecting invalid addresses before binding; requires an Assist token of at least 32 characters | `tests/test_bind_address_environment_defaults.py` |
| DECLAN_UPDATE_SOURCE | Defaults to `github` when unset | Accepts `github` or `pinned` after trimming whitespace; rejects blank, unknown and differently cased values | `tests/test_release_source_environment_defaults.py` |
| DECLAN_UPDATE_ROOT | Missing or blank disables the updater | Requires an absolute POSIX root with writable directories, a releases directory and a current symlink pointing to the running app | `tests/test_update_root_environment_defaults.py` |
| DECLAN_UPDATE_SUPERVISED | Missing or blank blocks installation | Only exact `1` passes the supervisor gate; other values fail before release selection or staging | `tests/test_update_supervised_environment_gate.py` |
| DECLAN_RELEASE_VERSION | Optional configured fallback when no valid installed release marker exists | A valid installed `.declan-release` marker takes precedence; missing, invalid or unreadable markers preserve the fallback | `tests/test_installed_release_version_defaults.py` |
| DECLAN_SENSITIVE_ROUTINES | Defaults to `guest,security` (Good Night needs no confirmation); explicitly empty disables group defaults | Comma-separated values are trimmed, case-folded and deduplicated; explicitly saved routine policies take precedence | `tests/test_sensitive_environment_boundaries.py` |
| DECLAN_TRUSTED_SPEAKERS | Missing or empty means no speaker is trusted by the legacy confirmation gate | Names are trimmed and case-folded; membership also requires numeric confidence from 0.85 through 1.0, excluding booleans | `tests/test_sensitive_environment_boundaries.py` |
| DECLAN_TRUSTED_RELEASES | Defaults to `/etc/declan/trusted-releases.json` | Requires an absolute POSIX path and a root-owned, non-group/world-writable, non-symlink file and parent chain; malformed allow-list content fails closed | `tests/test_trusted_releases_environment.py` |
| DECLAN_HA_URL, DECLAN_HA_TOKEN | Missing or blank credentials yield an unconfigured status, or a recent-Assist fallback; guest and visitor state are unknown | URL is trimmed and must use HTTP(S) without embedded credentials, query or fragment; invalid settings fail before network access | `tests/test_ha_status_environment_defaults.py`, `tests/test_ha_presence_environment_defaults.py` |
| DECLAN_VISITORS_ENTITY | Uses the persisted configuration value or built-in visitor entity default; this is not a direct process-environment read | Only `input_boolean.` IDs with lowercase letters, digits and underscores are accepted; invalid IDs fail before HA requests | `tests/test_visitor_entity_configuration.py` |
| DECLAN_MEDIA_SEARCH_AGENT | Empty saved value triggers discovery of a local Declan conversation agent; setting is read from persisted configuration | Nonempty overrides must match a lowercase `conversation.` entity ID; invalid IDs fail before HA connection | `tests/test_media_agent_configuration.py` |
| DECLAN_WEB_TTS_ENTITY | Empty saved value allows TTS provider discovery; setting is read from persisted configuration | Nonempty overrides must match a lowercase `tts.` entity ID; invalid IDs and missing HA connection prevent TTS requests | `tests/test_web_tts_entity_configuration.py` |
| DECLAN_WEB_ASSIST_PIPELINE | Missing or empty saved selection omits the pipeline field, allowing Home Assistant to choose its default STT pipeline; this is read through persisted configuration | An explicitly selected pipeline ID is forwarded to the Assist WebSocket STT run; the HTTP handler trims surrounding whitespace | `tests/test_assist_pipeline_selection.py` |
| DECLAN_GOOD_MORNING_SCRIPT, DECLAN_GOOD_NIGHT_SCRIPT, DECLAN_MOVIE_SCRIPT, DECLAN_BEDROOM_MOVIE_SCRIPT | Empty saved values fall back to environment; empty effective values use legacy morning/night migration defaults or no movie mapping | Used by one-time registry bootstrap only when scripts exist in HA; existing mappings and completed migration are not overwritten. Imported nonempty IDs require the lowercase `script.` domain | `tests/test_routine_settings_import_validation.py`, `tests/test_routine_registry.py`, `tests/test_settings_precedence_matrix.py` |
| DECLAN_MOVIE_REMOTE, DECLAN_BEDROOM_MOVIE_REMOTE | Empty saved values fall back to environment; empty effective values add no remote | One-time movie mapping migration includes the remote only if it exists in HA. Imported nonempty IDs require the lowercase `remote.` domain; existing mappings are not overwritten | `tests/test_routine_settings_import_validation.py`, `tests/test_routine_registry.py`, `tests/test_settings_precedence_matrix.py` |

### Persisted setting precedence

For the settings listed in `configuration.FIELDS`, Declan reads a nonempty saved
value from its settings database first. When the saved value is empty or absent,
it falls back to the corresponding process environment variable, then to the
caller's explicit default if the variable is also missing. Other configuration
keys read the process environment directly without opening the settings database.
These precedence rules are regression-tested in
`tests/test_settings_precedence.py` and the all-fields matrix in
`tests/test_settings_precedence_matrix.py`.

The Spotify credential source can also be a persisted settings file, not just
the process environment. `DECLAN_WEB_TTS_ENTITY`, `DECLAN_VISITORS_ENTITY` and
the other allowlisted settings can fall back to environment through
`configuration.get`; a nonempty saved value wins. The consumer boundaries live
outside the thin `server.py` compatibility facade. Do not confuse this backend
precedence with Home Assistant config-entry options.

## Installation

1. Copy [`.env.example`](../.env.example) into the protected server configuration location.
2. Replace placeholder secrets with randomly generated credentials.
3. Restrict access to the file and restart the standalone Declan service.
4. Verify the server and Home Assistant Ingress connections before removing any existing configuration.

Do not commit populated `.env` files, live access tokens, Spotify credentials or OpenAI keys. The Home Assistant Assist bridge token and the Ingress token serve different purposes and must not be reused.

For deployment instructions, see [installation](installation.md) and [Proxmox updates](../PROXMOX-UPDATES.md).
