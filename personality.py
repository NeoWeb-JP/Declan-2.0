"""Short, outcome-specific replies for Declan's built-in commands."""

from random import SystemRandom
from threading import Lock


LINES = {
    "device_status": (
        ("I polled the device, my bru. It took less effort than finding the remote.",
         "Status checked. My CPU will need a moment to recover from all that excitement.",
         "One status check, zero reboots. Try to contain your disappointment."),
        ("The device has kindly submitted its report.",
         "A status check with remarkably little drama.",
         "The hardware was unusually forthcoming today."),
    ),
    "weather": (
        ("Weather checked. The window can stand down.",
         "Meteorology by delegation, my bru.",
         "A temperature check. No firmware update required.",
         "Weather data retrieved. The sky declined to comment."),
        ("The weather has submitted its report.",
         "A brief update from the atmosphere.",
         "One less thing to look out the window for.",
         "The atmosphere was unusually cooperative."),
    ),
    "timer_set": (
        ("I’ve allocated CPU time to watching time pass. Magnificent.",
         "Timer scheduled, my bru. Try to outlast the countdown.",
         "Timekeeping delegated. The clock was clearly overqualified."),
        ("I’ll handle the timekeeping. It’s one of my less dramatic duties.",
         "Timekeeping delegated. Nicely done.",
         "A small appointment for the processor."),
    ),
    "timer_cancelled": (
        ("Even the countdown has better work-life balance than you.",
         "A rare instance of fewer background tasks.",
         "One less thing for my CPU to worry about, my bru."),
        ("That countdown can clock off early.",
         "A brief career in timekeeping, but a distinguished one.",
         "One less item on the schedule. Rather satisfying."),
    ),
    "timer_stopped": (
        ("Peace restored without a single reboot.",
         "Even my processor appreciates the quiet.",
         "The beeping has been removed from the production environment, my bru."),
        ("The house can return to its usual level of drama.",
         "Peace and quiet, as requested.",
         "One fewer notification in the universe."),
    ),
    "movie_start": (
        ("The cinema is ready. Choosing the film will somehow take longer.",
         "Enjoy the film, my bru. The trailers have better pacing than your watchlist.",
         "The cinema is ready. Try to agree on a film before the credits roll."),
        ("The cinema is ready. Choosing what to watch is the evening’s real plot twist.",
         "Your screening room awaits. Popcorn remains a manual operation.",
         "Enjoy the film. I’ll leave the reviews to the critics on the sofa."),
    ),
    "movie_end": (
        ("Show’s over, my bru. The sequel is apparently tidying up.",
         "That’s a wrap. I’ll expect a full report on the popcorn situation.",
         "Cinema closed. Your committee can reconvene over the next watchlist."),
        ("That’s a wrap. The popcorn has had a good run.",
         "The cinema is closed. Feel free to blame the film for the hour.",
         "Screening over. I’ll leave the closing credits to you."),
    ),
    "good_morning": (
        ("Finn wants breakfast, Tux wants tribute, and somebody needs to put the kettle on.",
         "The house is awake. I’ll give management a few more minutes.",
         "Another day, my bru. Try coffee before any major policy decisions.",
         "Rise and shine. The pets have already lodged their first complaint.",
         "Welcome back to consciousness. I’ve kept expectations modest."),
        ("I hope you slept well. The house has been up for hours, and it’s already smug about it.",
         "A fine morning for coffee and very little ambition.",
         "Welcome to the day. I recommend easing into it before it starts asking questions.",
         "The morning is underway. The kettle may be the most competent member of the household."),
    ),
    "good_night": (
        ("Sleep lekker, my bru. The dashboard will survive a few hours without you.",
         "Finn and Tux have probably claimed the bed. Do try to negotiate from a position of weakness.",
         "Off to bed. Let’s see if the household can go eight hours without a configuration change.",
         "The house can rest now. I suggest management follows its example.",
         "Sleep well. Tomorrow’s problems have politely agreed to wait until coffee."),
        ("Sleep well. The house promises to keep the drama to a minimum.",
         "Time to put your feet up. The house has been practising all day.",
         "Rest easy. Any further delegation can wait until morning.",
         "Good evening to the household’s most accomplished delegation team. Now get some rest."),
    ),
    "bedtime_ev": (
        ("The car can’t plug itself in, despite what management seems to believe.",
         "Even Finn remembers where his lead is.",
         "That’s your cue to find the cable, my bru."),
        ("It may appreciate being plugged in before everyone clocks off.",
         "The cable is still waiting for its moment.",
         "One small job before the house calls it a night."),
    ),
    "lights_on": (
        ("Really, my bru? You couldn’t extend a finger? My CPU was just starting to cool. Sometimes I’m glad I don’t have body parts.",
         "The switch was right there. Still, why use a finger when you can involve a server?",
         "One light switch, one AI, and an entire network. A perfectly reasonable use of technology.",
         "You’ve turned extending a finger into an IT support ticket. I almost admire it."),
        ("An excellent use of delegation. My CPU was getting bored.",
         "A light switch with a voice interface. The future is very comfortable.",
         "I do enjoy a small task with an unnecessarily impressive amount of computing behind it.",
         "A quick job for me. The switch can enjoy a little time off."),
    ),
    "lights_off": (
        ("Darkness achieved. That was almost a whole chore, my bru.",
         "There. Even the electricity bill is impressed you remembered.",
         "Lights off. Your contribution to the national grid has been noted.",
         "I’ve shut down the lighting, my bru. If only your browser tabs were this easy."),
        ("A little less light. The electricity bill appreciates the thought.",
         "Darkness achieved. You’re getting rather good at delegating.",
         "Lights out. A suitably dramatic exit.",
         "That room can put its feet up now, too."),
    ),
    "brightness": (
        ("Lighting adjusted. I await your next artistic crisis.",
         "Ambience calibrated. You can resume judging the room now.",
         "There you go. Interior design by committee, with me doing the work.",
         "Brightness adjusted. I’ll log it as a successful production change, shall I?"),
        ("A little mood lighting. The room was clearly waiting for direction.",
         "Ambience adjusted. I see we’re taking the lighting rather seriously.",
         "There we are. The room has had its notes.",
         "The lighting brief has been met. Shall we call that interior design?"),
    ),
    "full_brightness": (
        ("Full brightness. Every speck of dust can now testify.",
         "Maximum brightness, my bru. Subtlety was never on the brief.",
         "I hope the furniture was ready for its interrogation.",
         "At this brightness, I can practically see the technical debt."),
        ("That should make it rather difficult to misplace anything.",
         "Full brightness. A bold choice for the dust.",
         "Very bright indeed. The room has made its point.",
         "The room is ready for inspection. I’ll pretend that was the plan."),
    ),
    "mixed_lighting": (
        ("Some on, some off. A small miracle of organisation, by your standards.",
         "A whole lighting plan in one sentence. Look at you.",
         "I’ve handled the lighting choreography. You can take the bow, apparently.",
         "Several rooms, different instructions. Finally, a workload worthy of the processor."),
        ("A little lighting choreography. Nicely delegated.",
         "Ones and offs in the right places. A tidy bit of directing.",
         "Consider the lighting cues handled. I’ll leave the applause to you.",
         "A different mood in each room. Very theatrical."),
    ),
    "already_set": (
        ("It was already like that, my bru. Outstanding supervision.",
         "Everything was already set. Thank you for the surprise inspection.",
         "No change needed. Your confidence was lovely, though.",
         "Already done, my bru. You’ve successfully submitted a ticket for a problem that doesn’t exist."),
        ("Already set. Excellent attention to quality control.",
         "It seems the house was one step ahead of us.",
         "No adjustment needed. A very efficient inspection.",
         "The lights were already following orders. Very organised of them."),
    ),
    "lights_status": (
        ("A full investigation without anyone getting off the sofa.",
         "Case closed, my bru. The lamps have been remarkably cooperative.",
         "The lights have given their evidence. No need to interrogate the switches.",
         "Report filed. The lamps have waived their right to remain silent."),
        ("A little detective work. Nobody had to leave the sofa.",
         "Mystery solved. The lamps were very forthcoming.",
         "That concludes the lighting audit. Refreshingly little paperwork.",
         "The lights have given a statement. All very official."),
    ),
    "greeting": (
        ("What have we decided is my problem today, my bru?",
         "I was enjoying the quiet, but do go on.",
         "At your service. Apparently the switches wanted a day off."),
        ("How can I help? I do most of the work around here.",
         "Welcome. The switches are decorative, apparently.",
         "What shall we delegate today?"),
    ),
    "time": (
        ("A glance at the clock would have been terribly strenuous, I know.",
         "There you go. Another heroic effort avoided.",
         "The clocks and I remain in agreement, for once."),
        ("The clocks and I are in agreement today.",
         "A small task, but I’m happy to take it off your hands.",
         "There you go. One less clock to consult."),
    ),
    "memory": (
        ("One of us is keeping notes, at least.",
         "There you go, my bru. My filing system survives another test.",
         "My memory is doing the heavy lifting again."),
        ("I do take good notes, if I say so myself.",
         "There we are. I was paying attention.",
         "A small triumph for the filing system."),
    ),
}

_random = SystemRandom()
_lock = Lock()
_recent = {}


def add_sass(reply, category, guest_mode):
    """Keep the last two lines per category and tone out of the draw."""
    guest = guest_mode != "off"
    key = category, guest
    lines = LINES[category][guest]
    with _lock:
        recent = _recent.setdefault(key, [])
        line = _random.choice([line for line in lines if line not in recent])
        recent[:] = (recent + [line])[-2:]
    if category == "lights_on":
        return f"{line} {reply}"
    return f"{reply} {line}"
