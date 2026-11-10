# Declan 2.0

Declan 2.0 is a household voice assistant with a standalone web service and a Home Assistant Assist integration.

## Install the Assist Bridge with HACS

1. In Home Assistant, open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/NeoWeb-JP/Declan-2.0` with category **Integration**.
3. Download **Declan 2.0 Assist Bridge**. Choose a release containing `hacs.json` or select `main` to test the current code.
4. Restart Home Assistant. If you already configured the bridge manually, keep the existing integration entry. For a new installation, add **Declan 2.0 Assist Bridge** under **Settings → Devices & services**.
5. Enter the base URL of your running Declan server and its Assist bridge token. Select **Declan 2.0** as your Assist conversation agent.

Open the integration's **Configure** dialog to enable **Declan 2.0 OpenAI Transcription** and enter the OpenAI API key. Select that entity as the speech-to-text engine in an Assist pipeline to use it. Existing Assist pipelines can keep their selected speech engines during migration.

HACS manages the files in `custom_components/declan_two`. The standalone service on Proxmox has its own release lifecycle. See [Proxmox release updates](PROXMOX-UPDATES.md) for that service.
