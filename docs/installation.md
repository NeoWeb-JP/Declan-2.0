# Declan 2.0 installation

Declan 2.0 has two deployment components: the standalone server and the Home Assistant integration. They are updated separately.

## Home Assistant Assist Bridge

1. In Home Assistant, open **HACS → Custom repositories**.
2. Add `https://github.com/NeoWeb-JP/Declan-2.0` as an **Integration** repository. Declan is proprietary; this custom-repository installation is not a claim of HACS default-store eligibility.
3. Install **Declan 2.0 Assist Bridge** and restart Home Assistant.
4. Under **Settings → Devices & services**, add **Declan 2.0 Assist Bridge**.
5. Supply the URL of the running Declan server and its Assist bridge token.
6. Select **Declan 2.0** as the conversation agent in your Assist pipeline.

For speech recognition and speech output, configure the desired Declan STT/TTS entities under the integration's options and select them in **Settings → Voice assistants**. Keep the underlying Wyoming/VoicePipeline or ElevenLabs service available if selected.

## Home Assistant app / panel

The Home Assistant app uses Ingress to proxy the standalone server. It has a separate authentication token from the Assist bridge.

1. Deploy a server release supporting Ingress.
2. Generate a strong token, set `DECLAN_INGRESS_TOKEN` in the server's protected environment configuration and restart the server.
3. Add this repository as a Home Assistant app repository, install **Declan 2.0 Web**, and configure the upstream server URL and token.
4. Start the app, enable the sidebar entry and open Declan from Home Assistant.

Use HTTPS when the upstream connection crosses an untrusted network. Do not expose the server's HTTP port to the public Internet. Browser microphone capture requires an HTTPS Home Assistant origin and microphone permission.

## Household routine scripts

Files under `home_assistant/` contain household-specific script examples, not
portable device mappings. Do not paste or replace them unchanged on a different
installation. Review every action target, state/readback template, area name,
guest helper and active-routine helper first. In particular, the bedroom and
movie examples contain fixed light/projector IDs. Changing only action targets
while leaving verification templates unchanged can produce incorrect outcomes.

Home Assistant owns the installed script definitions. Configure and verify them
there, then let Declan discover the scripts under Issue #12's current policy.
Test start, end, failure and Stop behavior with the intended devices and confirm
reported outcomes match observed state. Declan's backend helper overrides do not
rewrite the YAML examples or installed scripts. Repository tests and an updated
backend do not establish that household YAML has been migrated.

## Updating and troubleshooting

The Assist integration, Home Assistant app and standalone service have separate release lifecycles. See [Proxmox updates](../PROXMOX-UPDATES.md) and the [main README](../README.md) for detailed operational notes. If the panel does not load, first verify the standalone service, the app's upstream URL/token, and the Home Assistant ingress connection.
