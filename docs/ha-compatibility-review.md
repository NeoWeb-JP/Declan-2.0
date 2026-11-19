# Home Assistant compatibility closure review

Baseline: merged #756 main `9040723`, reviewed 19 November 2026.

## Observed installation

Read-only connected Home Assistant queries report Core 2026.11.2, HA OS,
Python 3.14.10 and a loaded `declan_two` config entry. A config-entry query for
`openai_conversation` returned no entries. This establishes current inventory,
not functional voice acceptance, the deployed Declan code version or absence of
OpenAI credentials elsewhere. No device actions or configuration writes were
performed.

## Accepted legacy naming disposition

Accepted through merged PR #757. Retain this allowlist rather than pursuing a
destructive blanket rename.

Retain the remaining compatibility identifiers:

- `jarvis_speaker` reads older producer metadata while canonical code uses
  `speaker`.
- `jarvis_voice_cache` reuses previously generated audio; new installations use
  `declan_voice_cache`. Renaming/deleting the old directory would abandon paid
  audio without a migration.
- Legacy voice-manager entity prefixes in configuration/TTS are recursion
  guards, not providers to start invoking.
- `declan_local` and `jarvis_local` identify older independent media-search
  agents; Declan's own agent remains excluded.
- `declan_local_result` in example YAML is a local response variable, not an
  installed integration identifier. Renaming it has no architecture benefit.

The original rename finding is dispositioned with this explicit allowlist.
Do not remove working adapters to reach zero legacy search matches.
Any retirement requires producer/entity/cache inventory and a tested migration.
This proposal does not certify names in external HA configuration.

The 48-test speaker identity/metadata, cache-location and media-agent group
passes on Ubuntu/Python 3.12. Existing tests verify metadata loss on plain-string
conversion, reuse of old cache bytes and independent provider selection.

## Speaker transport remains incomplete

The deployed-version upstream [STT models](https://github.com/home-assistant/core/blob/2026.11.2/homeassistant/components/stt/models.py)
define final `SpeechResult` with text and result state. `PartialSpeechResult`
has an optional speaker ID, but that is not Declan's final per-turn identity,
confidence and capture contract. This model inspection does not establish a
supported end-to-end replacement channel. Retain the compatibility carrier until
the full pipeline-to-conversation path is verified for this version. Do not
infer a safe replacement merely from partial-transcription speaker support.

## OpenAI credential reuse remains incomplete

There is no configured `openai_conversation` entry in the observed installation
to reuse. This alone is not a security finding or a reason to install one.
Keep separate STT/backend credentials until a supported sharing contract and
credential lifecycle are established; do not read another integration's private
options as a shortcut. No credential contents were requested or inspected.

External legacy event publishers, shared VoicePipeline storage and live
privacy/voice acceptance remain outside this inventory. Their checkboxes stay
open.
