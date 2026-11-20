# Talking to Declan

A short guide for everyone in the house, including guests who have never used him. Say the wake word, then speak normally.

## Things you can just say

**Lights**
- "Turn on the kitchen lights", "turn off the office light"
- "Dim the lounge lights", "make it brighter in here"
- "Set the kitchen lights to 40 percent", "lights to 30 percent in here"
- Afterwards: "turn them off", "make them brighter"

**Music**
- "Play jazz", "play country music in the kitchen", "play the Beatles everywhere"
- "Pause", "resume", "next song", "stop the music"
- "Turn it up", "quieter", "set the volume to 30 percent"
- "Move the music to the bedroom"

**Routines**: say the routine's name, for example "good night", "good morning" or "movie time". Homelab, camera and security routines ask you to say **yes** first.

**Timers**: "set a timer for 10 minutes", "how much time is left on the timer", "cancel the timer"

**Finding out what's here** (always free, no AI):
- "What can you do?"
- "Which lights are in here?" or "what lights are in the kitchen?"
- "What routines are there?", "what rooms do you know?", "where can you play music?"

## Conversation: when you don't know the words

With **Conversation** on (Settings → AI Intelligence), you don't need the exact phrases or device names:

| You say | Declan |
|---|---|
| "It's dark in here" | Turns on the lights in the room you're in |
| "Put some music on" | Picks something and plays it in your room, then says what |
| "Switch the lamp on" | If there's more than one lamp, asks "the floor lamp or the table lamp?" Just answer |
| "Turn on the TV" | Turns on the TV, if it's shared with Assist |
| "I'm bored" | Asks if you'd like some music |
| "Where is Peru?" | Answers in one short sentence |

How it behaves:
- **Exact commands stay instant.** Conversation is only used when Declan doesn't recognise what you said.
- **He only acts on what's shared with Assist** in Home Assistant, and only says "done" once the device confirms it.
- **When a question needs an answer** ("which one?"), he keeps listening, so you don't need the wake word again.
- **He learns.** When a phrase leads to one successful command, it's remembered, so next time it's instant and costs nothing. These show in Settings → Voice & learning → Learned commands as "learned from a conversation", where you can edit or forget them. Phrases like "in here" or "turn it on" are never learned, because they depend on the room.

## Settings that change how Declan listens

| Setting | Where | What it does |
|---|---|---|
| Conversation | AI Intelligence | Everyday speech, questions and "which one?" follow-ups. It has a monthly budget, and History → Understanding shows how much it's used and what it costs |
| Voice command style | Voice & learning | Optional: only act on requests that start with "can you…", or that end with "my bru" |
| Recognised-speaker threshold | Voice & learning | How confident voice recognition must be before Declan treats you as you |
| Music behaviour | Music behaviour | Reply before music starts; let Music Assistant search |

## When Declan doesn't understand

He says "say it another way" and keeps listening. Rephrase it, and he'll learn the first phrase. To fix a phrase for good, open **History**, find it, and use **Teach Declan**. **History → Understanding** lists the phrases he missed most this week.
