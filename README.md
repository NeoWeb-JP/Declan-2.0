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
