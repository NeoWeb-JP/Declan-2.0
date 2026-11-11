# P1 security and privacy: first implementation

Tracks issue #17. These changes cover HTTP response policy, bad Assist token throttling, history retention and an HTTPS deployment path. They do not complete speaker authorisation, encrypted sample storage, per-person consent records or event-bus provenance checks. Nothing changes on an installed household system until deployed and configured.

## Response policy

The standalone server and HA sidebar proxy send Content Security Policy, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and a Permissions Policy permitting the same-origin microphone while disabling camera and location access. Inline scripts receive a fresh random nonce for each page response. The proxy applies its own nonce to both the UI script and its panel-token script. Inline CSS remains allowed because the existing UI uses a style block and a style attribute; inline event handlers and arbitrary inline scripts are blocked.

Direct standalone pages prohibit framing (`frame-ancestors 'none'`, `X-Frame-Options: DENY`). Authenticated ingress responses and the proxy allow only same-origin framing, matching HA's sidebar URL. No wildcard frame origins are accepted. Relative API calls, blob audio playback and same-origin microphone capture remain permitted. Upgrade the Declan Web HA app to **1.0.4**, update the standalone server and reload the panel. Live microphone and playback checks are still needed in HA and iPhone browsers.

## Failed Assist credentials

`/api/assist` and `/api/assist/history` share a per-socket-peer failure budget on the standalone server: ten invalid tokens per sixty-second window beginning with the first failure. Further requests during that window receive HTTP 429 and `Retry-After`, including requests with valid credentials. After expiry, authentication resumes. A valid request before the limit clears that peer's failures. Invalid and throttled requests close their connections without consuming a command body. Tokens are compared in constant time and are never stored in the limiter.

Forwarding headers cannot change the peer identity. The ledger is lock-protected and limited to 4096 peers, with no eviction of active failures to bypass the limit. At capacity new invalid peers are throttled until the earliest expiry. Restarting the service resets the in-memory budget. Behind a reverse proxy all clients share its socket address; restrict access to HA's address at the proxy/firewall too. This is brute-force throttling, not a boundary against a stolen valid token or a determined denial-of-service attack.

## HTTPS between HA and Declan

The HA bridge and the ingress proxy already accept `https://` URLs and validate server certificates. Keep the stable launcher's HTTP health check on loopback, and terminate TLS on a reverse proxy on the **same host as Declan**. Set `DECLAN_BIND_ADDRESS=127.0.0.1` in the service environment so the authenticated Assist listener is no longer exposed directly on the LAN. This optional setting applies to `--assist-lan`; it defaults to the existing `0.0.0.0` binding for compatibility and accepts IPv4 addresses only.

For example, after provisioning a DNS name and a certificate whose full chain HA trusts, an nginx server block can expose only the required bridge and ingress paths:

```nginx
server {
    listen 443 ssl;
    server_name declan.example.net;
    ssl_certificate /etc/nginx/tls/declan-fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/declan-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # Replace with the actual HA host address. Keep this private to the LAN.
    allow 192.0.2.10;
    deny all;

    location / {
        proxy_pass http://127.0.0.1:52737;
        proxy_set_header Host 127.0.0.1:52737;
        proxy_read_timeout 90s;
        client_max_body_size 1m;
    }
}
```

Use `https://declan.example.net` in the HA bridge configuration and the HA app's `declan_url`. Keep `DECLAN_INGRESS_TOKEN` separate from `DECLAN_ASSIST_TOKEN`. Do not disable certificate validation or redirect an HTTP request containing a bearer token to HTTPS: configure the HTTPS URL from the start. Verify the old LAN HTTP port is unreachable, both HA clients can connect with the trusted name, and an untrusted certificate is rejected. TLS requires deployment-specific DNS, certificate and firewall configuration; these are not created by this change. Protect the separate Declan-to-HA URL with HTTPS too when it crosses the LAN. A same-host TLS proxy avoids changing updater health checks or trusting forwarded headers.

References: [nginx HTTPS configuration](https://nginx.org/en/docs/http/configuring_https_servers.html) and [proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

## HA credentials

Use a dedicated, non-administrator HA account for Declan and create its long-lived token from that account. Replace `DECLAN_HA_TOKEN` in the server environment, restart Declan, verify the required scripts/media/template operations and revoke the previous token. Keep the account LAN-only if appropriate. This is an administrator deployment task, not something Declan can do with its bearer token.

A non-administrator account reduces access to administrator APIs, but does **not** provide a per-entity sandbox: ordinary HA users and administrators can control the same entities. Do not claim that this makes sensitive voice commands safe. See [HA permissions](https://contributors.home-assistant.io/core/internals/permissions/) and [user setup](https://www.home-assistant.io/docs/configuration/user-configuration/). Issue #17's restricted-account task remains open until deployed and checked.

## Stored history and audio

Set `DECLAN_HISTORY_RETENTION_DAYS` to a whole number from **1 to 30** in the standalone service environment, then restart. The default remains 30 days. Invalid values fail startup. History and export reads immediately omit expired turns, including their transcripts and speaker-match metadata. The existing hourly prune deletes expired rows without doing writes on history reads. Learned intentions are separate settings and remain until explicitly forgotten. Clearing history removes active rows immediately, but SQLite free pages, WAL files, upgrade snapshots and external backups are not securely erased by that operation.

For example, `DECLAN_HISTORY_RETENTION_DAYS=7` keeps a week's conversation history. The setting does not alter HA's own recorder/log retention, diagnostic storage, TTS caches or VoicePipeline retention. Declan does not persist browser STT uploads, but when the selected HA pipeline uses OpenAI transcription its audio is sent to OpenAI. A configured local STT fallback receives the audio after cloud failure. Text and speaker matches can also be stored by HA and VoicePipeline independently.

Voice profiles and reviewed recordings now live in VoicePipeline. Declan retrieves audio for playback without persisting it. Legacy local WAV samples remain in unencrypted SQLite with their existing export/deletion controls; new local enrolment is retired. Upgrade snapshots retain up to three copies after a healthy supervised start. Deleting a sample or shortening active history retention does not scrub those retained snapshots or an external backup. Per-person consent records and encrypted storage require a separate change coordinated with VoicePipeline. No extra permission checkbox is introduced into the review UI.

## Validation

Regression checks cover actual standalone and proxied HTTP headers, matching per-response script nonces, error responses, shared Assist endpoint throttling and recovery, concurrency, ledger capacity, spoofed forwarding headers, retention boundaries, export filtering and prune behaviour. No live HA credentials, certificates, voices or devices are used by those tests.
