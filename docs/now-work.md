# Current work and live testing

The core voice migration is working, but the original NOW requirements are not all complete. On 11 November 2026 Jaco agreed to bring four focused additions into NOW. This list separates code from live household tests.

Original scope: [NOW baseline](https://github.com/NeoWeb-JP/Declan-Local/blob/18f02af9eb6824c1f44163201b529b75f21bf65e/docs/functional-now.md). The archived FUTURE list remains a historical record; this document records the new scope decision for Declan 2.0.

| Item | GitHub issue | Implementation in this branch | Live acceptance |
| --- | --- | --- | --- |
| See why voice or music failed | [#8](https://github.com/NeoWeb-JP/Declan-2.0/issues/8) | Local timings, outcomes and history request references. Spotify search and HA stop/play dispatch are separate stages. | Pending |
| Review and edit learned intentions | [#9](https://github.com/NeoWeb-JP/Declan-2.0/issues/9) | Free-text edits with stale-tab protection; confirmed deletion. Saving never runs a command. | Pending |
| Back up settings and check upgrades | [#10](https://github.com/NeoWeb-JP/Declan-2.0/issues/10) | Versioned export, preview, confirmed import and recovery export; local pre-update SQLite snapshots and integrity checks. | Pending |
| Manage voice profiles and samples | [#11](https://github.com/NeoWeb-JP/Declan-2.0/issues/11) | Consent, local recording/WAV upload, review, sample download and deletion. | Pending; recogniser connection blocked |
| Finish the remaining NOW gaps | [#12](https://github.com/NeoWeb-JP/Declan-2.0/issues/12) | Existing migration work plus remaining implementation below. | Owner testing in progress |

## Where to find the new controls

Open the settings menu in Declan. Request diagnostics, Back up settings and Voice profiles each have their own panel. Learned intention editing stays in Conversation history. These routes use the existing local-browser or authenticated HA admin ingress boundary; the Assist bridge token does not grant access to management routes.

## What to test

- Diagnostics: make an ordinary request and a music request. Find the request reference from history, the Spotify search, stop/play dispatch and playback verification. A state of `playing` does not prove sound was audible. Provider exception messages, credentials, raw audio and transcripts must not appear in diagnostics.
- Learning: edit a correction using free text. It must not run at save time. Say it again to verify normal command handling. Edit the same correction in two tabs: a stale edit must be rejected. Confirm before forgetting it.
- Settings: export, preview and import the same settings. Check all entity IDs. Confirm nothing executes. Confirm credentials stay excluded. Try an unsupported schema. Include learned intentions only when explicitly selected; importing that list replaces the existing list. Download the recovery file to reverse the previous import, selecting learned intentions if those also need restoring.
- Voice samples: create your own profile with explicit consent, record a sentence, listen before saving, download a sample and delete it. Close the panel during microphone permission and check that the microphone is released. Repeat in Safari/iPhone. Samples must not change recognition or confer permissions.
- Updates: on a test deployment, check a normal update makes a private snapshot before activation. A corrupt persistent database must stop activation, leave the old release selected and report failure. A snapshot failure must not leave the update permanently marked as installing.

## Backup boundaries

A settings download includes only supported non-secret server mappings and optionally learned phrases. It excludes Spotify/HA/OpenAI credentials, history, caches and biometric data. Non-empty imported mappings override server environment defaults; empty values use those defaults. Entity IDs must be reviewed for the destination home. This is not a full Home Assistant restore or a replacement for native HA configuration selectors.

Before an update through Declan's updater, each local SQLite database is backed up using SQLite's online backup API, including committed WAL data. Saved Spotify credentials are copied only to that private server-side snapshot. Snapshots live in `.data/upgrade-backups/`, with restrictive directory/file permissions on Linux. They are not downloadable through the settings API and are not automatically deleted. Monitor disk space and keep these files private.

The shared `.data` directory, including caches, remains linked across releases. Speech caches and integration settings stored inside Home Assistant require a separate HA backup. Direct terminal Git updates bypass the web updater's automatic snapshot. For full recovery or a destructive schema downgrade, stop Declan and restore an appropriate local snapshot or container backup; selecting an old code release alone does not roll back data.

## Voice recognition dependency

The linked VoicePipeline-Development repository is empty. Its enrolment/training API cannot be verified from source, so this implementation deliberately does not call guessed endpoints. Local voice profiles are a reviewable sample collection foundation, not working enrolment into the active recogniser. Existing Wyoming speaker recognition continues as before.

Connecting reviewed samples, evaluating accuracy on separate recordings and enabling or rolling back a candidate model remain open in #11 and the existing [speaker work #1](https://github.com/NeoWeb-JP/Declan-2.0/issues/1). No passive daily collection or automatic model changes are enabled. Deleting active samples does not erase copies in older local upgrade backups or previously downloaded exports.

## Existing NOW work still open

- Live verification of dinner music, the new bedroom output, iPhone/desktop capture, silent Stop and duplicate satellite arbitration.
- Quiet-hours schedule, temporary volume changes and safe restoration, and selected announcement destinations.
- Recognised-speaker context across rooms, with separate unknown-speaker sessions.
- Native HA selectors for arbitrary routines and a consistent versioned completion result across Dinner, Sexy Time and the other migrated routines.
- Record the owner-approved differences: no separate Assist exposure filter for this household, and mood-preserving Sexy Time speech with technical failures in history.

Homelab operations, predictive heating/EV optimisation, complex scheduling and autonomous learning remain deferred.
