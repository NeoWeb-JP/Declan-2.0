# Music Assistant and Spotify acceptance (issue #12)

- Spotify discovery and category storage are owned by Declan 2.0. Declan Local is retired and not installed.
- Each category holds at most **25 playlists**, not 25 tracks.
- The native Home Assistant Settings panel provides playlist add/pin, remove, delete/exclude, and restore.
- A weekly refresh uses the Declan 2.0 Spotify API search and retains pinned favourites and exclusions.
- Category playback uses curated playlists before live Spotify search and respects recent-playlist and blacklist preferences.
- Media player approval is fail-closed by default. Configure the Music Assistant destination per HA area in Settings.
- `DECLAN_ALLOW_UNCONFIGURED_MA=1` is an opt-in migration compatibility setting. Do not enable it on a normally configured household.
- The native HA panel proxies authenticated requests to the Declan 2.0 backend. There is no dependency on the retired Declan Local integration.

Acceptance coverage: `tests/test_spotify_playlists.py`, `tests/test_native_music_playlists_contract.py`, `tests/test_approved_media_players.py`, `tests/test_music_stop_everywhere.py`.
