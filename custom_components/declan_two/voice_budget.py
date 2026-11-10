"""Persistent conservative provider-attempt accounting; never stores speech."""
import asyncio
from datetime import datetime, timezone
import math


class VoiceBudget:
    def __init__(self, store=None, today=None):
        self.store = store
        self.today = today or (lambda: datetime.now(timezone.utc).date().isoformat())
        self.lock = asyncio.Lock()
        self.data = self.empty()
        self.available = True

    def empty(self):
        return {'day':self.today(), 'primary_characters':0, 'primary_attempts':0,
                'fallback_characters':0, 'fallback_attempts':0}

    async def load(self):
        if self.store is None:
            return
        try:
            value = await self.store.async_load()
            if value is None:
                return
            if (not isinstance(value,dict) or set(value)!=set(self.data)
                    or not isinstance(value.get('day'),str)):
                raise ValueError('Invalid voice usage storage')
            from datetime import date
            date.fromisoformat(value['day'])
            if any(type(value[k]) is not int or value[k]<0 for k in self.data if k!='day'):
                raise ValueError('Invalid voice usage counters')
            self.data = value
        except (OSError, ValueError):
            self.available = False

    @staticmethod
    def validate_limit(limit):
        if type(limit) is not int or not 0 <= limit <= 10_000_000:
            raise ValueError('Daily primary character limit must be between 0 and 10000000')
        return limit

    def rollover(self):
        # Clock rollback cannot reset a used allowance.
        if self.today() > self.data['day']:
            self.data = self.empty()

    async def reserve(self, text, role, limit=0):
        if role not in {'primary','fallback'}:
            raise ValueError('Unknown provider role')
        limit = self.validate_limit(limit)
        async with self.lock:
            self.rollover()
            if role == 'primary' and not self.available:
                raise ValueError('Primary speech accounting is unavailable; repair storage and reload')
            count = len(text)
            if role == 'primary' and limit and self.data['primary_characters']+count > limit:
                raise ValueError('Daily primary speech character limit reached')
            new = dict(self.data)
            new[role+'_characters'] += count
            new[role+'_attempts'] += 1
            if self.store and self.available:
                try:
                    await self.store.async_save(new)
                except OSError:
                    self.available = False
                    if role == 'primary':
                        raise ValueError('Could not reserve primary speech usage; no request sent') from None
            self.data = new

    def snapshot(self, limit=0, credit_rate=0):
        limit = self.validate_limit(limit)
        data = self.empty() if self.today() > self.data['day'] else dict(self.data)
        valid_rate = (isinstance(credit_rate,(int,float)) and not isinstance(credit_rate,bool)
                      and math.isfinite(credit_rate) and 0 < credit_rate <= 100)
        return {**data, 'storage_available':self.available, 'daily_character_limit':limit,
                'remaining_characters':max(0,limit-data['primary_characters']) if limit else None,
                'estimated_credits':round(data['primary_characters']*credit_rate,3) if valid_rate else None,
                'credits_per_character':credit_rate if valid_rate else None}
