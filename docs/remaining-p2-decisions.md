# Remaining P2 closure decisions

Baseline: merged #757 main `e92e64c`, reviewed 19 November 2026.
The following proposed dispositions need acceptance through PR review; they are
not assertions that the original implementation requests were completed.

## Speaker metadata transport

Retain `SpeakerTranscript` only at the current Home Assistant STT compatibility
edge, with explicit `SpeakerMetadata` snapshots and JSON projection inside
Declan. Propose deferring retirement of the carrier until a supported final-turn
metadata channel is verified for the deployed HA pipeline. Do not introduce a
global transcript lookup, fuzzy recording join or text-embedded identity as a
replacement: those create correlation/privacy risks.

The plain-string metadata-loss risk remains real. Regression tests demonstrate
it; they do not constitute deployed pipeline acceptance. Revisit when an
upstream channel is available, a demonstrated pipeline transformation loses
identity, or supported HA versions change. A replacement must verify concurrent
speakers, exact turn correlation, missing identity and normalization before
retiring the carrier. Proposed disposition: accepted compatibility limitation
with deferred transport migration, not a completed migration.

## OpenAI credential reuse

Propose retaining separately configured STT and backend planner credentials.
The observed HA installation has no `openai_conversation` entry, and this review
has not established a supported cross-integration secret-sharing contract.
Do not install another integration solely to obtain its key or read its private
config-entry data. Keep the credential-reuse suggestion deferred until a
supported sharing/lifecycle contract and actual configured source exist.

This does not encrypt HA config-entry options or remove their backup exposure.
Protect HA storage/backups, avoid logging or exporting secrets, and replace keys
through the existing authenticated configuration paths. No key rotation,
credential inspection or storage migration was performed in this review.

## Household-specific scripts

Backend helper targets and spoken display names are configurable and validated;
the ingress household IP has been replaced by loopback. Edd pronunciation is an
explicit Issue #12 requirement. Fixed action/readback targets remain in the HA
script examples. Propose treating those definitions as installation-owned
examples, requiring explicit operator customization and functional verification
rather than silently rewriting the live household's targets.

This is a scope disposition, not a reusable parameterized YAML implementation.
If portable install-ready scripts are required, keep that requirement open and
design configuration for both actions and verification templates together.
The installation guide now states the customization/acceptance requirements.

## Acceptance and remaining blockers

On acceptance, record each item above as explicitly dispositioned/deferred,
preserving its limitation and revisit trigger. Do not mark the STT migration or
portable-script implementation subtask as implemented. Shared VoicePipeline
encryption/deletion, external publisher inventory and #496 live acceptance are
not covered by these proposals; #17 remains open for unresolved agreed scope.
