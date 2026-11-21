# Changelog

This file records significant repository changes. Historical releases are available in [GitHub Releases](https://github.com/NeoWeb-JP/Declan-2.0/releases); consult each release for its exact changes.

## Unreleased

- **"The usual" (FUT-44, #834).**
  - "The usual" runs the usual for the room that heard you and the time of day (morning, afternoon, evening, night), or that room's "any time" usual.
  - Set it by voice ("my usual for the lounge in the evening is lamps to 40% and play chill music") or in Settings → Household → The usual, where you can also edit and forget them.
  - Each step is an ordinary command said in that room, so a failed step is reported and the rest still run. No usual yet: "You haven't told me the usual for the lounge yet."
  - Per room, not per person. Guests can ask for the usual but can't set or forget one. Stored locally; nothing goes to the AI except the sass top-ups.
- **Braai master (FUT-43, #834).**
  - "Braai time" plays the Braai playlist in the room you're in, turns on the garden lights and checks for rain, opening with braai sass: your three lines plus the approved extras, rested and topped up like the rest.
  - Each part is an ordinary command, so a failed part is reported and the rest still runs.
  - "Boerewors 12 minutes, chops 8 minutes" sets both timers; "how long on the chops?" asks the chops timer.
  - "Braai's over" gets a closing line and leaves the music alone.
- **Clearer failures (FUT-24, #834).** When a request fails as unavailable or failed, Declan checks what's actually down before saying so:
  - **Home Assistant not answering:** "Home Assistant isn't answering, boet, so nothing in the house will work until it's back."
  - **Declan's HA token rejected:** he says so.
  - **Every Music Assistant player unavailable,** for a music failure: "Music Assistant's having a tantrum, my bru. The speakers aren't answering, but your lights still work."

  Otherwise the original, specific reply stands. A check that can't run blames nothing, and checks are cached for 30 seconds.
- **Intercom (FUT-25, #834).**
  - "Tell the kitchen dinner's ready", "announce to everyone: leaving in five minutes", "announce upstairs: bedtime".
  - The message is spoken on that room's satellites (or every satellite except yours, or the ones on HA's upstairs/downstairs floors) with the pre-announce chime: "Message from the lounge: dinner's ready."
  - Unreachable satellites are named in the reply.
  - Not during quiet hours (23:00 to 07:00).
  - "Tell me a joke" and "announce dinner" still go where they did.
- **Reminders (FUT-26, #834).**
  - "Remind me at six to put the bins out", "remind me in 20 minutes to check the oven", "remind Edd tomorrow at 8 to call the plumber".
  - They ring on the satellite you asked from, saying "Reminder: put the bins out." every 30 seconds until someone says "stop", for up to 10 minutes, exactly like timers. They survive restarts.
  - "What reminders do I have?", "cancel the bins reminder", "cancel my reminders".
  - Up to a week ahead. "At six" means the next six o'clock.
  - Optional: `DECLAN_REMINDER_NOTIFY=notify.mobile_app_jaco,…` also sends the first ring to phones.
- Documented the environment variables added for FUT-59 to FUT-61.
- **Shopping and to-do lists (FUT-27, #834).**
  - "Add milk and eggs to the shopping list", "what's on the shopping list?", "take milk off the list", "add call the plumber to my to-do list".
  - Uses Home Assistant's own to-do lists (the one with "shopping" or "grocer" in its name, and the one with "to-do", "tasks" or "chores"), so items show on everyone's phone in the HA app. "The list" means the shopping list.
  - Long lists are summarised (first six, then "and 3 more").
  - Ticking off marks the item completed in HA.
  - "I put milk on the shopping list" goes to the list, not to "where did I put".
- **More music controls (FUT-28, #834).**
  - "What song is this?" / "who sings this?"
  - "Play Jolene next" / "queue Thunderstruck by AC/DC" adds it after the current track.
  - "Play something similar" / "more like this" starts Music Assistant radio from the current track.
  - "Don't play this artist again" skips them now and whenever they come up. Settings → Music behaviour → Blocked artists has Unblock.
  - Sleep timer: "stop the music in 30 minutes" fades out over the last 30 seconds, stops, then puts the volume back. "Cancel the sleep timer" stops it, and new music in that room cancels it too. A Declan restart cancels sleep timers.
  - Commands act on the room you're in when music is playing there, else on the single active player. Replies only report what Home Assistant accepted.
- **"Where did I put…?" (FUT-42, #834).** Tell Declan where something is ("the spare car key is in the hall drawer", "I've moved the passports to the safe"), then ask: "where's the spare car key?" gets "Lucky for you, one of us pays attention. In the hall drawer, since Tuesday."
  - Local only, shared by the household, survives restarts.
  - Near misses and plurals match ("car keys" finds "spare car key").
  - Moving something says where it was before; asking twice in a day gets the lost-property line.
  - **Guests** get your lines ("Wouldn't you like to know.") and never a location; they can't save things either.
  - A bare "the key is in the drawer" is only filed when nothing else understood the sentence, so "the lights are on in the kitchen" is never filed.
  - "Where is Peru?" still goes to general chat.
  - Settings → Household → **Where things are** lists everything, with Forget.
- **HA script sync (FUT-62, #834).** The HA Audit page has a new **Declan scripts** block. It compares each script Declan relies on (Sexy Time, Good Night, Good Morning, Movie Time, Dinner, Christmas Morning) with the version that came with this release. Home Assistant is the master copy, and formatting-only differences count as in sync. Each script shows one of these:
  - **In sync.**
  - **Changed in Home Assistant:** copy the YAML so the repo can be updated, or keep HA's version.
  - **Updated by Declan:** **Apply in Home Assistant** asks first, backs up `scripts.yaml`, reloads scripts and checks the result.
  - **Changed in both / Different:** HA wins, with a diff.
  - **Not in Home Assistant yet.**

  Scripts defined outside `scripts.yaml` (for example in packages) are never overwritten. The integration ships the scripts in `custom_components/declan_two/declan_scripts/`, which a test keeps identical to `home_assistant/`.
- **Christmas mode (FUT-59, #834).** On automatically from 1 December to 2 January, or say "Christmas mode on/off" (Settings → Household → Christmas mode: automatic, on or off). While it's on:
  - About half of Declan's everyday sass is Christmas sass (lights, timers, greetings, good morning/night, dinner, guests arriving). These lines rest and get topped up like the rest.
  - "Play some music" plays from a new **Christmas** playlist category, when it has playlists.
  - On Boxing Day music starts no louder than 20%, and good morning gets the hangover lines.
- **Always available:**
  - "How many sleeps till Christmas?"
  - Several cooking timers in one sentence: "set a turkey timer for 3 hours and a roast potatoes timer for 50 minutes", or "turkey 3 hours, roast potatoes 50 minutes".
  - "What's the Wi-Fi password?" reads out the guest Wi-Fi from Settings → Household (empty, and so secret, until you set it).
- **New example script:** `home_assistant/christmas_morning.script.yaml`.
- **Guests arriving:** "Mike and Kathy are in charge" now gets its own sass.
- **Fresh sass every day (FUT-61, #834).** Once Declan says a sass line, roast or routine response, it rests for **3 days** before he uses it again, and that's remembered across restarts. If everything in a category is resting, he uses the line that has rested longest. When a category runs low, he writes a batch of new lines in the background: short, rude, South African, and checked so they never claim anything happened, mention numbers, or repeat existing lines. It has its own monthly budget ($1 by default, `DECLAN_FRESH_LINES_BUDGET_USD`) on top of the main AI ledger, needs the AI model and key to be set up, and never slows a reply. Settings → Household: rest days (0 turns it off), fresh lines on/off, and the list of lines Declan wrote, with Delete.
- **Guest Mode keeps the sass (FUT-60, #834).** Guests now hear exactly the same lines as the household: roasts, swearing and innuendo included. The old polite guest lines are still there: Settings → **Household** → Guest tone → Polite (or `DECLAN_GUEST_TONE=polite`). This only changes wording: sensitive routines still ask for confirmation and private answers stay private. Needs the updated HA integration for the new Settings card.
- **Sexy Time stays in its room.** Declan now tells the Sexy Time script which satellite heard the request. The updated `home_assistant/sexy_time.script.yaml` keeps the master bedroom's own lights, and in any other room dims that room's lights (pink where they can) and puts them back afterwards. **Manual step:** paste the new YAML into the Sexy Time script in Home Assistant; until then it keeps using the bedroom.
- **Easier for people who've never used Declan.** "Play some music", "put some music on" or "play something" now plays a favourite, or a playlist from one of your categories, instead of searching Spotify for the words "some music" (with Conversation on, the agent still chooses). In Guest Mode, a misunderstood request ends with a hint ("Try 'lights on', 'play some music', 'louder' or 'stop'") and "what can you do?" gives a five-item guest answer. Hinted misses still open the rephrase window and still count on History → Understanding.

## 2.13.1 (20 November 2026)

Includes everything from 2.13.1-rc1 to rc5.

- **Fix: a ringing timer couldn't be stopped.** Plain "stop" only silenced an alarm after it had verified music stopping on that device, so with nothing playing the alarm kept repeating every 30 seconds. "Cancel the timer" on a ringing timer was refused ("say stop…"), and "stop the timer" on a running one was refused ("say cancel…"). Now, while an alarm is ringing, "stop", "stop the alarm", "okay", "thanks" and similar silence it straight away. If nothing is ringing on that satellite, they silence whichever alarm is ringing. "Cancel" and "stop" mean the same for a timer. An alarm nobody answers gives up after 10 minutes instead of ringing forever. Running timers are never cancelled by a plain "stop".
- Tests (D5, #802): the backend tests that grepped Python source for call order or wiring now check behaviour instead. Covered: dispatch stages and their dependencies, AI fallback wiring, the Assist-token access gate, cancel and confirmation running before the command-style gate, answers to the agent bypassing that gate, verified-only routine personality, HTTP event logging and repairing data before the history store starts. Ten source-text files or tests are gone. The `test_native_*` contracts that check the HA integration and panel against the backend stay, because they need a Home Assistant runtime to test behaviourally.
- **Fix: music and lighting stage timings were never recorded.** The `music_playback`, `music_control` and `lighting` timers sat on old reply/outcome wrapper functions that the live request path no longer called, so diagnostics showed no time for those stages. They are now on the functions actually used.
- Refactor (D5, #802): retired the old reply/outcome tuple APIs. Every `as_legacy_pair` / `as_legacy_triple` / `as_legacy_result` method and the wrapper functions built on them (`music.play/control/feedback`, `timers.handle`, `conditions.handle`, `ha_inventory.read`, `script_discovery.discover/match/execute/enqueue`, `device_status.describe`, `server.set_lights`, `server.handle_light_request` and the tuple variants of the dispatch helpers) are gone; production passes typed results only. Routine response composition now reads the typed routine selection. Tests compare plain tuples through `tests/result_pairs.py`. No behaviour change.
- Housekeeping: removed the root `voice_audio_crypto.py` alias kept for updaters older than the package move (every install now runs the newer updater), and brought `docs/now-work.md` up to date (NOW register closed, DEV-01 device inventory).
- **Music starts at 30% volume.** Before Declan starts or moves music, any speaker louder than 30% is turned down to 30% first, so music never blasts out at the last volume used. Quieter speakers are left alone, and for "everywhere" each speaker in the group is turned down. Change the level in Settings → Music behaviour → Start volume (`0` turns it off); `DECLAN_MUSIC_START_VOLUME` applies until a value is saved there. The panel field needs the updated HA integration; older panels can still save the music switches without losing the start volume. A failed volume change never stops the music from starting.
- **Declan warnings now appear in `journalctl -u declan`.** They were only shown in the panel's Declan logs, because adding the panel log feed stopped Python printing them anywhere else. Warnings and errors from Declan (for example "AI fallback stopped before changing devices: …") now also go to the service log, with secrets redacted. "What time was it?" is also understood.
- **Fix: asking the time with Conversation on.** Built-in answers (the time, "what's my name", "what did I just say") could be sent to the conversation agent (which has no clock) or the AI device planner (whose reply replaced the answer). They are now always answered locally, for free.
- **Fix: OpenAI transcripts falling through to "I couldn't safely complete that request".** OpenAI speech-to-text keeps how you address Declan, so "Declan, turn on the kitchen lights.", "Good night, Declan." or "Pause the music, please." no longer matched the local commands and went to the AI planner. A leading "Declan," / "Hey," / "Okay Declan," and a trailing ", Declan" / "please" / "thanks" are now dropped before matching ("my bru" is kept for the command style setting). More ways of asking the time are understood ("what was the time", "what's the time now", "can you tell me the time", "do you know what time it is"). With Conversation off, general questions like "where is South Africa?" now say how to switch Conversation on instead of costing an AI planner call that is bound to be refused.
- AI fallback: **"I couldn't safely complete that request using OpenAI" now says why**: API key rejected, model not available on the account, rate limit or no credit, OpenAI unreachable or erroring, a plan that failed Declan's safety checks, an unavailable device, or the per-request cost limit. The reason is also logged (`journalctl -u declan`), and the reply always says no devices were changed.
- **Fix: "AI device permissions are unavailable".** The HA integration asked Home Assistant for the devices shared with Assist through a function that doesn't exist, so the list was always empty and every AI device request (the AI fallback and Conversation) was refused. It now uses Home Assistant's `async_should_expose`, includes media players so Conversation can control TVs, logs a warning if the list can't be read, and says plainly when nothing is shared with Assist.
- **Near-miss light names** now work without the AI: "kitchen spot" (Kitchen Spots), "the bedroom lamps", "office lamp light" or a slight mishearing like "studdy light" turn on the one clearly matching light. If two lights are equally close ("lounge lamp" with a floor and a table lamp), Declan doesn't guess, and Conversation can ask which. Room names still mean the whole room.
- **Better hearing (opt-in):** a new integration option, *Use my Home Assistant names as vocabulary*, gives OpenAI speech-to-text your room names and the names of devices shared with Assist (plus "Howzit Declan" and "my bru"), so names are misheard less. It's capped at 40 names, refreshed every 10 minutes, and off by default because these names are sent to OpenAI. The extra-words vocabulary field now has a proper label.
- **Free local help:** "what can you do?", "which lights are in here?" / "what lights are in the kitchen?", "what routines are there?", "what rooms do you know?" and "where can you play music?" are answered from Home Assistant data, with no AI and with Conversation on or off.
- New household guide, **[Talking to Declan](docs/talking-to-declan.md)**, linked from the README and from Settings → AI Intelligence → Conversation.
- Conversation: **follow-ups work after Declan acts**. After "it's dark in here" turns the lights on, "turn them off" or "make them brighter" is understood locally and instantly.
- Conversation: **Declan remembers what worked**. When a phrase was turned into one successful command ("put some jazz on" → "play jazz"), it is saved, so the next time it's instant and free. It shows in Learned commands as "learned from a conversation", where you can edit or forget it. It never overwrites a phrase you taught, and never learns room-dependent wording ("in here", "it", "them"), vague requests ("play something"), routines, timers or commands naming a room you didn't say.
- History → Understanding now shows **Conversation this week**: how many requests reached the conversation agent, how many it acted on, asked about, answered or failed, how many were general questions, the cost, and the typical AI reply time. Each agent turn also adds a `conversation_agent` stage (kind, model time, cost, device count) to the request's diagnostics trace. No text or names are stored.
- **Volume:** "turn it up/down", "louder", "quieter", "volume up", "turn the music down in the kitchen", "set the volume to 30 percent" and "volume 40" now work. Volume changes go to the speaker in your room (or the named room / Everywhere), in steps of 10%, and the new level is checked and spoken. A speaker that doesn't report its level is asked to step up/down instead.
- **Brightness:** more ways to say a percentage: "turn the kitchen lights to 40%", "put the lamp at 30 percent", "kitchen lights 50 percent", "set the brightness in the office to 70%", and "lights to 30 percent in here" (uses your room). The conversation agent can use brightness and volume too.
- Confirmations: **Good Night no longer asks for a spoken yes.** By default only homelab, server, camera/CCTV, security and alarm routines (and guest assignment) need confirming; a security *light* is just a light. Change it with `DECLAN_SENSITIVE_ROUTINES` (default `guest,security`); a routine's saved confirmation setting still wins.
- **Conversation (new):** Settings → AI Intelligence → **Conversation** lets Declan understand everyday speech from people who don't know the commands or device names. When a request isn't an exact command ("it's dark in here", "put some music on", "switch the lamp on", "play something", "what can you do?"), Declan uses the room you're in, your Assist-exposed devices, music rooms, routines and the last few lines of the conversation to **act**, **ask** a short question (the mic stays open, so "the spots" is understood), or **answer**.
  - Lights, switches, fans, blinds and TVs change only through the verified executor, on exposed entities.
  - Music, routines and timers become normal Declan commands, re-checked by the local parsers. Sensitive routines still need a spoken yes, and garage/gate covers stay blocked.
  - If a device isn't confirmed, the reply says so instead of using the AI's wording.
  - Exact commands stay local and instant. When Conversation is off or unavailable, behaviour is unchanged.
  - To keep spend down, replies are one short sentence where possible. General-knowledge questions ("where is Peru?") get a one-sentence answer and are sent without any house context (no device, room or routine lists).
  - It replaces the separate general chat setting from earlier in this release, keeping the same switch and budget (now defaulting to $20 a month). The AI monthly budget default is now $20 for new installs.
- TV control: `media_player` turn on/off is now an allowed, verified action (any active state counts as on; off or standby counts as off).
- Voice (#373): optional **voice command style** in Settings → Voice & learning: any wording (default), must start with a question ("can you…", "could you…", "would you (mind)…", "will you…"), must end with "my bru", or either. It applies to satellites and Echo Shows only. A command in another style is ignored silently: nothing runs, Declan stops listening, and History records it as `ignored`. Stop, cancel, yes/no, real questions and replies to Declan's own questions always work. Also `DECLAN_COMMAND_STYLE`.
- Speech (REL-01): optional **local TTS fallback**. Set *Local TTS fallback entity* (for example `tts.piper`) in the Declan 2.0 integration options. When ElevenLabs fails or the daily character limit is reached, and no saved equivalent reply exists, Declan speaks with the local voice instead of going silent. Local audio is cached separately, so it never replaces ElevenLabs audio. Leave the option blank to keep ElevenLabs only.
- Settings → Voice & learning: each speaker now shows a **match rate** (HIS-11): of the recordings VoicePipeline attributed to that speaker and you then reviewed, the share where you kept that speaker. Pending, dismissed, rejected and discarded recordings don't count. It shows "n/a" until there are 5 reviews.
- Settings → Voice & learning: **Learned commands** is back. A refactor had left its code in place but removed it from the page. It lists every learned phrase, however old, with a search box, and shows when and how each was last trained (History, a recording, a successful retry, edited here or imported). Phrases learned before this release show "Learned before training dates were recorded" (#98).
- History: new **Understanding** card (VOI-12). It shows how many spoken or typed requests got the "say it another way" reply in the last 7 days and the three weeks before, the most-missed phrases (marked when since learned), and this week's speaker-ID confidence against the recognised-speaker threshold.
- Voice: the recognised-speaker threshold (VOI-08, default 85%) is now a setting in **Settings → Voice & learning** or `DECLAN_SPEAKER_THRESHOLD`. It controls History speaker labels and duplicate-capture arbitration. Sensitive routine confirmations keep their fixed 85% floor.
- **Fix (data):** 2.13.0 and 2.13.1-rc1 stored the conversations and diagnostics databases inside the release folder (`declan/core/.data`) instead of the shared `.data`, so learned phrases, history, server settings, routines, custom responses and AI settings appeared reset, and changes made on 2.13 would be lost on the next update. Paths are fixed. On first start Declan merges what was done on 2.13 (learned phrases, history, AI spend) back into the shared database and keeps the release-local file as `*.merged-<timestamp>`. Settings changed on 2.13 are not merged automatically; the log lists them.
- Settings: new **Music behaviour** card for reply-first playback and Music Assistant search, so neither needs `declan.env`. A saved value wins; until then the environment variable (or default) applies.
- Music: reply-first playback is now on by default, so "play …" is answered as soon as Home Assistant accepts it and verified in the background. Set `DECLAN_MUSIC_REPLY_FIRST=0` to restore the slower verified-first reply.
- Music: optional `DECLAN_MUSIC_ASSISTANT_SEARCH=1` hands "play X" to Music Assistant's own search on the right speaker or group, bypassing Declan's Spotify search (kept for switching back). "Play X upstairs/downstairs" now parses like "everywhere".
- Voice: polite requests are understood locally, so "can you turn on the office light", "turn on the office light please" and "... my bru" no longer fall through to the AI fallback or a rephrase prompt (#801).
- Fix: one lighting command joined to one music command ("turn on the office lights and play country music everywhere", either order) now runs both actions and reports each result (#300, #799).
- Voice encryption: optional key IDs (`DECLAN_VOICE_AUDIO_KEY_ID`), retired keys (`DECLAN_VOICE_AUDIO_PREVIOUS_KEYS`) and `migrate_voice_audio --rewrap` for key rotation. Nothing changes until a key ID is set (#800).
- Fix: the Home Assistant integration no longer reads `manifest.json` or imports the Wyoming client on the event loop, which removes the "blocking call" warnings from the HA log.
- Updater: a failed install now records which stage failed (for example `install-dependencies`). The step appears in the service log and in the Updates panel; command output is never logged.
- Fix: the voice dependency lock now includes the Python 3.11 `cffi` wheel hash, so staged installs succeed on Python 3.11 hosts (the 2.13.0 release failed hash verification there).
- Documentation reorganised into a concise entry-point README, installation instructions, architecture overview, and configuration reference.
- P2 CI maintenance: Dependabot, Hassfest, and advisory Python quality and security checks.

## Release history

See [GitHub Releases](https://github.com/NeoWeb-JP/Declan-2.0/releases) for versioned release notes. This changelog intentionally does not reconstruct undocumented release histories.
