# Spotify genre buttons through Declan

A room can contain several Music Assistant players, such as a Sonos, TV and Echo. An area-only request must stay unresolved when Declan cannot select one safely. Do not remove other devices from the correct HA area to force a match.

Music playback requests also accept an exact, registered HA Music Assistant entity ID in the destination position, for example:

`Play 80s music in the media_player.kitchen_declan_voice_assistant on Spotify`

This goes through the existing parser, Spotify search/playlist preferences, single-stream handoff and playback verification. It does not send a fixed stream URL, bypass search, or fall back to another player when the named entity is missing/unavailable. The target must be present in the current inventory with `declan_music_assistant: true`; native/non-MA entities and malformed IDs are rejected before search or playback changes. Room-based voice requests retain their existing behaviour. This syntax applies to playback/transfer requests; it does not add an explicit-entity destination to the separate music-control/feedback parsers.

## Existing reusable script

If the shared `script.declan_play_music_genre` already builds `Play {{ genre }} music in the {{ room }} on Spotify`, it needs no change. Set its `room` argument to the exact MA entity. This field now accepts either a room or a player destination.

Paste this into the individual HA YAML editor for the 80s Kitchen button:

```yaml
alias: 80s music (Kitchen)
icon: mdi:cassette
sequence:
  - action: script.declan_play_music_genre
    data:
      genre: 80s
      room: media_player.kitchen_declan_voice_assistant
```

For other buttons, change `genre` to `country` or `classical`. For a bedroom button choose the actual registered MA wrapper, for example `media_player.master_bedroom_declan` when that is its current entity ID. These are user-side examples, not hard-coded production player mappings. Update script values if you rename the MA entities.

The shared script is invoked through HA's existing Declan conversation agent and credentials; no extra bearer token is needed in YAML. Reaching `action_done` in the HA response is not proof of playback: inspect Declan's spoken reply in the script trace when troubleshooting. This change needs a standalone Declan server update before using an entity ID as the destination. It is not activated by editing YAML alone, and does not require a new HA bridge action or ingress app version.

## Verification

Regression tests model three available players in Kitchen. The area-only request still refuses to guess, while the explicit target performs the real `music.py` Spotify search against fixture responses, stops the previous stream and dispatches only to the selected wrapper. Invalid/non-MA/unavailable targets perform no search or playback mutation. These tests do not contact Spotify or change any real speakers.
