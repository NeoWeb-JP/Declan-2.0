# 1.0.4

- Add a nonce-based Content Security Policy and browser security headers to panel pages and errors. Keep same-origin Home Assistant framing and microphone access.
- Update the standalone server too for bad-token throttling and configurable history retention.

# 1.0.3

- Allow the authenticated VoicePipeline management route through the sidebar proxy. Update the standalone Declan server as well to use shared speaker profiles and recording review.

# 1.0.2

- Limit simultaneous proxy requests to 16 workers and return HTTP 503 with a retry hint when busy.

# 1.0.1

- Allow panel update requests over HTTP when browser Fetch Metadata is absent by validating a random panel token delivered through authenticated Ingress.
- Keep Supervisor source restrictions, explicit cross-site rejection, upstream authentication, content types and request size limits.
- Update this app through Home Assistant's app update screen after this version is merged into the app repository; restart and reload the panel afterward. The standalone Declan updater is not required for this app update.

