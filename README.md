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
