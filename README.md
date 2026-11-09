# Declan 2.0

Standalone local voice and keyboard chat with a Home Assistant Assist bridge.

## Run locally

With Python 3.12 or newer, run `python server.py --port 0 --open`.

For Assist, set a shared secret of at least 32 characters in `DECLAN_ASSIST_TOKEN` and run `python server.py --assist-lan --open`. LAN mode defaults to port 52737. Install `custom_components/declan_two` in Home Assistant and configure the bridge with the server's LAN base URL and the same secret. Select Declan 2.0 in a separate Assist test pipeline.

For the optional Home Assistant status indicator, set `DECLAN_HA_URL` and `DECLAN_HA_TOKEN` in the server environment. Keep credentials out of Git.

Chat history is retained locally for 30 days and can be exported for review from the browser. The prototype does not dispatch household actions.
