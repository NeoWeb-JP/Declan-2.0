# Confirming sensitive voice routines

Implements the voice-authorisation item in #17, tracked in #31. Unknown or uncertain voices must confirm a protected routine before Declan runs any part of it. An explicitly approved speaker can skip confirmation when the configured recognition confidence is met. Typed commands in the trusted local/HA management page remain an authorised control surface.

## Defaults and settings

The default protected groups are **night** (the bedtime routine) and **guest** (guest-register changes). Read-only questions such as "who is in charge" remain available. Other routine groups retain their existing behaviour unless added to the policy. Set these variables on the standalone Declan service and restart it:

| Variable | Default | Meaning |
| --- | --- | --- |
| `DECLAN_SENSITIVE_ROUTINES` | `night,guest` | Comma-separated groups: `morning`, `night`, `movie`, `sexy_time`, `dinner`, `guest`. Use the explicit value `none` to disable protection. An empty value or unknown group is an error. |
| `DECLAN_ROUTINE_SPEAKERS` | Empty | Comma-separated enrolled names allowed to skip confirmation. Names match case-insensitively, with no display-name aliases or implicit household members. |
| `DECLAN_ROUTINE_SPEAKER_CONFIDENCE` | `0.9` | Minimum confidence for skipping confirmation, from `0.75` to `1`. Uncertain or malformed matches require confirmation. |

For example, protect every supported routine group with `DECLAN_SENSITIVE_ROUTINES=morning,night,movie,sexy_time,dinner,guest`. Leave the speaker list empty to require confirmation from everyone. The allow-list uses VoicePipeline's enrolled name, not Declan's history display label: if the actual profile is `Ed`, entering `Edd` does not approve it. A name, finite confidence within range and valid recognition interaction ID must arrive together from Assist. HA's user ID and remembered conversational names do not grant voice privileges. Browser microphone requests currently lack the required trusted speaker metadata and always use confirmation for protected groups.

Invalid configuration fails startup. Invalid policy encountered during a request prevents execution instead of silently disabling protection. The policy is not part of settings import/export; edit it as an administrator in the service environment.

## Confirmation flow

An unapproved voice saying "good night" receives a prompt such as: `To run "good night", say "confirm routine 1 2 3 4" within 30 seconds, or say "cancel routine". Nothing has run yet.` The four digits are randomly generated for that request. Declan accepts separate digit words, spaced digits or one four-digit number. A generic "yes" is not sufficient.

The prompt covers the complete effective command, including any learned-intent replacement and chained lighting/music instructions. Confirmation executes that saved command, even if a learned intention is edited afterward. No timers, routine scripts, follow-on lights or music are dispatched while confirmation is pending.

The confirmation must arrive in the same conversation, source and Assist origin (device, satellite and HA user context). An Assist command with no physical device/satellite can run via approved speaker recognition, but cannot create an unbound confirmation. Browser microphone confirmation uses the existing browser conversation. A different room, session or source cannot approve a pending request.

Each confirmation is consumed atomically before execution, including when execution fails. Replaying it cannot retry the routine. A wrong confirmation, cancellation, intervening turn or policy change invalidates the pending request. Expiry is thirty seconds from the original request and is not extended. A service restart discards pending requests. At most 1024 unexpired requests are stored; further requests fail safely until space becomes available. Normal conversation storage remains separately bounded by its existing 128-session limit, so an evicted conversation cannot use its old pending confirmation.

The HA bridge now passes the server's boolean `continue_conversation` flag to HA's `ConversationResult`, preserving the conversation ID for the confirmation response. Update the standalone server and HA Assist Bridge **0.2.5** together. Reload the HA integration after its update. On a satellite that does not support continued conversations or resets conversation IDs on every wake, the safe result is an unfulfilled request; support on the installed satellite still needs a live test. The browser retains its existing session and can send the confirmation through another microphone turn. Typing the original routine in the trusted interface remains direct authorised control; typing a voice confirmation cannot approve a request from a different source.

The continued-conversation contract is documented by [Home Assistant](https://contributors.home-assistant.io/core/entities/conversation/).

## Scope and limits

This reduces accidental actions from TV audio, background speech and uncertain recognition. It is not a biometric security guarantee: voice recognition can misidentify someone, and anyone who hears the challenge at the same device can deliberately confirm it. The Assist shared token remains the trust boundary for submitted recognition/origin metadata. A client holding that token can forge those fields. Keep it private and use the transport protections tracked separately in PR #29.

The browser management interface is trusted; its voice source marker is a usability control, not an independent boundary against a malicious authenticated browser client. Native HA automations, scripts, direct service calls, other integrations and independent lighting/media commands are outside this routine policy. It does not undo an action that already ran. The guest register is not a speaker allow-list, and enabling Guest Mode does not grant speaker privileges.

History records confirmation-required, cancelled and invalid turns with explicit outcomes so they are not offered as unmatched phrases to teach. The request/reply history follows the existing retention configuration. Recognition allow-lists do not add voice samples or consent checkboxes to the review UI.

## Validation

Isolated tests run the actual HTTP handler with in-memory socket streams, real temporary history databases and mocked household dispatch. They cover unknown/low-confidence voices, exact allow-lists, invalid metadata, protected group selection, learned/chained commands, no pre-confirmation dispatch, cross-device/session/source attempts, expiry, cancellation, policy changes, one-use consumption under concurrent replay, bounded capacity and the trusted keyboard/voice distinction. Bridge tests check boolean continued-conversation handling. Existing routine and browser tests remain required.

Live checks pending: confirm a bedtime request from each supported satellite; verify approved and uncertain voices against the actual recognition scores; test cancellation and expiry; and confirm browser microphone continuation. No household actions or speaker settings are changed by the regression suite.
