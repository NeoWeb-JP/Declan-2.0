"""Routine intent checks, not a biometric or Home Assistant security boundary."""
from dataclasses import dataclass
import math
import os
import re
import secrets
from threading import Lock
from time import monotonic

GROUPS = frozenset({'morning', 'night', 'movie', 'sexy_time', 'dinner', 'guest'})
NAME = re.compile(r"[^\W\d_][\w '\u2019-]{0,39}")
DIGITS = dict(zip(('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'), '0123456789'))


@dataclass(frozen=True)
class Policy:
    protected: frozenset
    speakers: frozenset
    confidence: float

    @classmethod
    def from_env(cls):
        groups = os.environ.get('DECLAN_SENSITIVE_ROUTINES', 'night,guest').strip()
        protected = frozenset(part.strip() for part in groups.split(','))
        if groups == 'none':
            protected = frozenset()
        elif not protected <= GROUPS:
            raise ValueError('DECLAN_SENSITIVE_ROUTINES must list supported routine groups, or none.')
        names = os.environ.get('DECLAN_ROUTINE_SPEAKERS', '').strip()
        speakers = [name.strip() for name in names.split(',')] if names else []
        if any(not NAME.fullmatch(name) or name.casefold() in {'unknown', 'unidentified', 'none'} for name in speakers):
            raise ValueError('DECLAN_ROUTINE_SPEAKERS must list exact enrolled speaker names.')
        try:
            confidence = float(os.environ.get('DECLAN_ROUTINE_SPEAKER_CONFIDENCE', '0.9'))
        except ValueError:
            confidence = math.nan
        if not math.isfinite(confidence) or not .75 <= confidence <= 1:
            raise ValueError('DECLAN_ROUTINE_SPEAKER_CONFIDENCE must be between 0.75 and 1.')
        return cls(protected, frozenset(name.casefold() for name in speakers), confidence)

    def recognises(self, speaker):
        if not isinstance(speaker, dict):
            return False
        name, confidence, interaction = (speaker.get(key) for key in ('name', 'confidence', 'interaction_id'))
        return (isinstance(name, str) and name.casefold() in self.speakers
                and type(confidence) in (int, float)
                and self.confidence <= confidence <= 1
                and isinstance(interaction, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', interaction) is not None)


@dataclass(frozen=True)
class Decision:
    phrase: str
    reply: str | None = None
    outcome: str | None = None
    authority: str | None = None

    @property
    def allowed(self):
        return self.reply is None


class RoutineAuthorizer:
    def __init__(self, *, clock=monotonic, capacity=1024):
        self.clock, self.capacity = clock, capacity
        self.pending = {}
        self.lock = Lock()

    def check(self, raw, phrase, *, source, session, scope, bindable, speaker, kind_for):
        try:
            policy = Policy.from_env()
        except ValueError:
            return Decision(phrase, 'Routine authorisation settings are invalid. Nothing ran.', 'authorization_unavailable')
        if source == 'browser_keyboard':
            return Decision(phrase, authority='trusted_browser')
        key = (source, session, scope)
        with self.lock:
            now = self.clock()
            self.pending = {key: item for key, item in self.pending.items() if item['expires'] > now}
            # Any intervening turn from this conversation/origin replaces the old request.
            pending = self.pending.pop(key, None)
            if raw in {'cancel routine', 'cancel', 'no', 'never mind'} and (pending or raw == 'cancel routine'):
                return Decision(phrase, 'Cancelled the pending routine. Nothing ran.', 'confirmation_cancelled')
            if raw.startswith('confirm routine'):
                digits = ''.join(DIGITS.get(word, word) for word in raw.removeprefix('confirm routine').split())
                if (pending and pending['policy'] == policy and digits == pending['code']):
                    return Decision(pending['phrase'], authority='spoken_confirmation')
                return Decision(phrase, 'That confirmation is missing, changed or expired. Ask for the routine again.',
                                'confirmation_invalid')
            kind = kind_for(phrase)
            if kind not in policy.protected:
                return Decision(phrase)
            if source == 'assist' and policy.recognises(speaker):
                return Decision(phrase, authority='recognised_speaker')
            if not bindable:
                return Decision(phrase, 'I need a conversation and a specific voice device to confirm this routine. Nothing ran.',
                                'authorization_unavailable')
            if len(self.pending) >= self.capacity:
                return Decision(phrase, 'Too many routines are awaiting confirmation. Try again shortly. Nothing ran.',
                                'authorization_unavailable')
            code = f'{secrets.randbelow(10000):04d}'
            if pending and code == pending['code']:
                code = f'{(int(code) + 1) % 10000:04d}'
            self.pending[key] = {'phrase': phrase, 'code': code, 'policy': policy, 'expires': now + 30}
            return Decision(phrase, f'To run "{phrase}", say "confirm routine {" ".join(code)}" within 30 seconds, '
                            'or say "cancel routine". Nothing has run yet.', 'confirmation_required')
