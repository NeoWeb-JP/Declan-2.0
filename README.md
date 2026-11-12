# Declan 2.0

Declan 2.0 is a household voice assistant with a standalone web service and a Home Assistant Assist integration.

## Install the Assist Bridge with HACS

1. In Home Assistant, open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/NeoWeb-JP/Declan-2.0` with category **Integration**.
3. Download **Declan 2.0 Assist Bridge**. Choose a release containing `hacs.json` or select `main` to test the current code.
4. Restart Home Assistant. If you already configured the bridge manually, keep the existing integration entry. For a new installation, add **Declan 2.0 Assist Bridge** under **Settings → Devices & services**.
5. Enter the base URL of your running Declan server and its Assist bridge token. Select **Declan 2.0** as your Assist conversation agent.

### Switch Assist from Declan Local

Open **Settings → Devices & services → Declan 2.0 → Configure**. Enable the speech engines you want:

- **Declan 2.0 Wyoming Speaker Recognition** sends audio to the existing VoicePipeline. Enter its Wyoming host and port (for example, `192.168.0.43:10300`). VoicePipeline still controls which backend transcribes this audio.
- **Declan 2.0 OpenAI Transcription** sends audio directly to OpenAI. Enter your OpenAI API key if it has not been configured yet. This route does not create VoicePipeline entries.
- **Declan 2.0 Voice Manager** uses your existing ElevenLabs integration. Select `tts.elevenlabs_text_to_speech` and the same voice and cache revision used by Declan Local to reuse its saved audio. If you used a daily character limit, set it here too. The new manager tracks its own usage.

In **Settings → Voice assistants**, select the Declan 2.0 conversation agent, one of the Declan 2.0 STT engines, and **Declan 2.0 Voice Manager** for each relevant Assist profile. Test from a satellite and verify the trace names the new engines before disabling Declan Local. Keep the ElevenLabs integration and, if using Wyoming, VoicePipeline running.

HACS manages the files in `custom_components/declan_two`. The standalone service on Proxmox has its own release lifecycle. See [Proxmox release updates](PROXMOX-UPDATES.md) for that service.


## Open Declan Web from Home Assistant

The **Declan 2.0 Web** Home Assistant app proxies the existing Proxmox server through
Home Assistant Ingress. The sidebar panel requires an HA administrator. The HACS Assist
Bridge is a separate integration and can keep its existing configuration.

1. Deploy a Declan server build with Ingress support to Proxmox.
2. Generate a separate token on Proxmox with `openssl rand -hex 32`. Set
   `DECLAN_INGRESS_TOKEN` in `/etc/declan/declan.env` and restart the `declan` service.
   Keep the existing Assist token separate.
3. In the Home Assistant app store, add
   `https://github.com/NeoWeb-JP/Declan-2.0` as an app repository. Install
   **Declan 2.0 Web** and enter the Proxmox Declan URL and the new token in its Configuration.
4. Start the app, enable **Show in sidebar**, and open **Declan 2.0**. Chat and history use
   the same running server and data as the SSH-tunnel UI.

Use HTTPS for the upstream Declan URL if the network between HA and Proxmox is
untrusted. For the default LAN HTTP URL, restrict the existing Declan port to the
trusted network and do not port-forward it. Browser microphone capture requires
opening Home Assistant over HTTPS and granting microphone permission.


## Automatic voice outputs

Assign satellites, speakers and Music Assistant players to their real Home Assistant
areas. Declan discovers the players through HA's registry for each music request.
No Show entity IDs are needed in Declan's configuration. Playback prefers the Music
Assistant player linked to the speaking satellite's device, including wrappers whose
registered source entity belongs to that device. An explicit different room is still
honoured. Within a room, a single available satellite-linked player takes priority
over TVs and other players; otherwise the single available area player is used.
Ambiguous matches ask for clarification. Available players replace unavailable entries automatically.

An unqualified Assist **Stop** first uses the media player attached to the same
Home Assistant device as the satellite. If that is unavailable, it uses the area's
single Music Assistant player. Grouped outputs are left alone to avoid stopping
other rooms. Stop returns no spoken acknowledgement and records its result in history.
Expired local timer alarms are acknowledged after playback stops.

Update the HACS bridge to **0.2.4** and the Proxmox server for two-satellite capture
arbitration. Declan compares overlapping audio captures of the same transcript and
prefers the louder capture arriving within a 250 ms selection window. Later duplicate
captures are suppressed, giving one execution, reply and history entry. Confidently
identified different speakers are kept separate. Audio is not stored for arbitration.
Captures without valid loudness/timing metadata keep the existing processing path.
Live kitchen/bedroom acceptance remains required before removing the legacy routine
result fallback.

### Bedroom mood commands

Say **Start bedroom mood** or **End bedroom mood** after the usual wake word.
**Start romance mode**, **End romance mode**, the existing **Sexy Time** commands,
and the transcription variants **sixty time** and **60 time** also work.
Start/activate and end/stop are accepted for each phrase. These are routine
commands, not additional microphone wake words.

The routine always targets the master-bedroom Music Assistant satellite player,
even when requested from another room. Declan sets its starting volume to 20%,
starts the playlist after lighting confirmation, and verifies Stop on that same
resolved output when ending. The supplied HA script accepts the resolved
`music_player` and leaves playback to Declan; update the script from
`home_assistant/sexy_time.script.yaml` to avoid duplicate legacy music actions.

### Current NOW work

The [current work and live testing list](docs/now-work.md) tracks the agreed additions, remaining migration gaps and new GitHub issues. Settings includes request diagnostics, configuration export/import and shared VoicePipeline speaker management.

### One speaker profile store

Set `DECLAN_VOICEPIPELINE_URL=http://192.168.0.43:8000` on the standalone Declan server and restart it. Update the **Declan 2.0 Web** HA app to **1.0.3** for the new management route, then reload the panel. If your VoicePipeline deployment requires a bearer token, set `DECLAN_VOICEPIPELINE_TOKEN` on the server too. Neither value is supplied by the browser.

Open **Settings → Voice profiles**. Existing speakers and pending recordings come directly from VoicePipeline. Speak through the satellite's Wyoming pipeline, refresh, listen, then explicitly assign the recording to an existing speaker or enrol a new name with permission. Assignment and enrolment add recognition references; the API requests a speaker-cache refresh. Names are sent exactly as enrolled, so an existing `Ed` profile remains `Ed` even when Declan displays `Edd` in conversation history.

History corrections use VoicePipeline's current resolution ID to reject stale edits. Corrections remove references from other speakers but do not add a reference to the selected speaker. Returning a recording to pending removes its references; assigning it afterward deliberately adds it to the selected speaker. Clearing references and deleting speakers require confirmation and do not promise deletion of retained interaction audio or backups.

Audio is fetched through the authenticated management route only when Listen is selected and is not persisted by Declan. Model settings, automatic model reloads, retention settings and HA webhooks are untouched. There is no second recogniser or automatic replay of audio for enrolment. The legacy local sample database is retained; new local profile/sample collection is rejected, while its existing export and deletion API operations remain available. Legacy samples are not automatically uploaded because the deployed VoicePipeline API has no upload endpoint.

The Assist bridge must still use **Declan 2.0 Wyoming Speaker Recognition** at `192.168.0.43:10300` to carry speaker identity alongside the transcript. Management API connectivity does not prove recognition works. Browser microphone STT currently returns text only and still needs a separate metadata-preservation change. Recognition accuracy and cross-room context remain live acceptance work.

VoicePipeline's pending resolve endpoint has no atomic stale-edit token. Declan serialises its own changes and checks that a recording is still pending, but another VoicePipeline client could resolve it in the interval. Avoid reviewing the same pending recording in both interfaces simultaneously. Failed writes are never retried automatically; refresh the list before deciding what to do next.
