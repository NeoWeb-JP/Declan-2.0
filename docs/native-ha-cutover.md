# Final native Home Assistant cutover

This release consolidates the Home Assistant native Declan panel and Assist integration. **Retire the legacy Declan Web/Ingress interface, not the Declan backend service.** The backend still supplies chat, music, Spotify discovery, speaker review, updates and settings APIs to the HA integration. Do not stop the backend VM or remove its data.

## Current functionality in the native panel

- Overview: connection status, text chat, microphone transcription and current reply.
- History & Voice Recognition: conversation timeline, reviewed/pending recordings, speaker assignment, audio playback and history, plus learned-command editing, forgetting and teaching missed requests.
- Media players: Home Assistant area-to-approved-player mappings.
- Settings: Spotify credentials rotation, non-secret export, recovery download, validated JSON import with preview and explicit confirmation, diagnostics.
- Updates: backend update/status controls and separate backend/integration version display.
- Assist: configured conversation, STT and TTS integration platforms.

The Spotify client ID and secret are not exported or imported. A release must not overwrite stored credentials, force Spotify reauthentication, or reset media-player mappings.

## Sensitive voice routine confirmation (issue #31)

- Voice requests for bedtime and guest-register changes require a one-use confirmation unless a speaker is explicitly allowlisted and recognised with confidence of at least 0.85.
- Set `DECLAN_TRUSTED_SPEAKERS` to comma-separated VoicePipeline speaker names to permit direct execution. An empty list trusts nobody.
- `DECLAN_SENSITIVE_ROUTINES` defaults to `guest,security` (homelab, cameras/CCTV, alarm); optionally include `night,morning,movie,dinner,sexy`.
- The confirmation is tied to Assist conversation ID and physical satellite/device, expires after 30 seconds, and is consumed once. Browser management commands retain their existing access control.
- Test actual HA follow-up behavior: some pipelines may require saying the wake word again for the confirmation. Automatic continued listening has **not** been verified.
- Voice recognition confidence is not a biometric guarantee; the HA integration's authentication and existing permissions remain essential.

## Required acceptance before disabling Declan Web

Record the installed HA integration version and backend commit/release for each test. **CI passing is not evidence of live acceptance.**

- [ ] Cold-open the native panel in the iPhone HA app, reload, navigate away/back, and verify no blank screen or menu-toggle dependency (issue #42).
- [ ] On iPhone and desktop, send text and microphone commands, deny microphone permission, cancel recording, and test a lost connection.
- [ ] Confirm voice timeline, pending/reviewed samples, playback, speaker corrections and enrolment in the HA panel; verify actual VoicePipeline identity through Wyoming.
- [ ] Verify Spotify playback on Kitchen, Master Bedroom and Everywhere, including Sexy Time routing, using approved media players.
- [ ] Check Spotify credential rotation in Settings **without changing current values for testing**; verify fields are not prefilled and that normal upgrades preserve existing credentials.
- [ ] Export settings, preview the export, verify the exact proposed changes, import only a safe test configuration, and download the recovery snapshot.
- [ ] Check backend release install/status, failed update and restart/reconnection on mobile; confirm no stale sidebar proxy errors.
- [ ] Confirm learned-intention edit, forget and teaching a missed command in the native panel. Confirm stale edit rejection and no command execution during save.
- [ ] Verify bedtime and guest-change confirmation on real Assist satellites, including recognised/unknown speaker, expiry, replay, different satellite, learned alias and chained commands (issue #31).
- [ ] Verify quiet-hours schedule, volume restoration, announcement destinations, routine selectors, and shared completion results in the deployed Home Assistant scripts (issue #12). These remain unverified and must not be marked complete on code inspection alone.
- [ ] Verify cross-room follow-ups for a recognised speaker and no context leakage between unknown speakers (issue #12).
- [ ] Take a backup of the Declan backend database, server configuration and HA integration configuration, then verify recovery steps.

## Cutover and rollback

1. Install the approved backend release and matching HA integration version. Restart HA if required, then confirm both version indicators.
2. Run the acceptance checks above. Keep the existing Declan Web interface available until all blocking checks pass.
3. Switch household Assist pipelines and satellites to the Declan 2.0 integration, confirm both speakers and music outputs, and monitor for regressions.
4. Only then disable the **legacy web UI/Ingress entry**, leaving the Declan backend and VoicePipeline services running.
5. If a critical command, microphone, recognition, or music test fails, restore the previous HA Assist pipeline and re-enable the legacy UI. Do not delete its configuration or database during this release.

Known limitation: browser microphone transcription does not itself establish speaker identity. Test the Wyoming satellite path separately.
