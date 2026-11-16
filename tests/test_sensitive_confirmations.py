"""Sensitive Assist confirmations: expiry, origin, replay, speaker and alias safety."""
import os
import unittest
from unittest.mock import patch
import sensitive_confirmations as sc

class SensitiveConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.now = [10.0]
        self.gate = sc.ConfirmationGate(clock=lambda: self.now[0])
        self.unknown = {"name":"Jaco","confidence":0.6}
    def check(self, session="s1", origin="assist_satellite.kitchen", phrase="good night", group="night", speaker=None):
        return self.gate.evaluate(session=session, origin=origin, phrase=phrase, group=group, speaker=speaker)
    def test_default_requires_confirmation(self):
        self.assertEqual(self.check()[0], "prompt")
        self.assertEqual(self.check(phrase="confirm"), ("confirmed","good night"))
        self.assertEqual(self.check(phrase="confirm")[0], "allow")
    def test_origin_and_session_isolation(self):
        self.check()
        self.assertEqual(self.check(origin="assist_satellite.bedroom",phrase="confirm")[0], "allow")
        self.assertEqual(self.check(session="other",phrase="confirm")[0], "allow")
        self.assertEqual(self.check(phrase="confirm")[0], "confirmed")
    def test_expiry_and_cancel(self):
        self.check()
        self.now[0] += 31
        self.assertEqual(self.check(phrase="confirm")[0], "allow")
        self.check()
        self.assertEqual(self.check(phrase="cancel")[0], "cancelled")
        self.assertEqual(self.check(phrase="confirm")[0], "allow")
    def test_missing_origin_fails_closed(self):
        self.assertEqual(self.check(origin=None)[0], "denied")
    def test_speaker_recognition_never_bypasses_confirmation(self):
        with patch.dict(os.environ, {"DECLAN_TRUSTED_SPEAKERS":"Jaco,Edd"}):
            self.assertEqual(self.check(speaker={"name":"Jaco","confidence":0.95})[0], "prompt")
            self.assertEqual(self.check(speaker={"name":"Jaco","confidence":0.7})[0], "prompt")
            self.assertEqual(self.check(speaker={"name":"Jaco","confidence":"0.99"})[0], "prompt")
            self.assertEqual(self.check(speaker={"name":"Jaco","confidence":float("nan")})[0], "prompt")
            self.assertEqual(self.check(speaker={"name":"Unknown","confidence":0.99})[0], "prompt")
    def test_configurable_groups_and_chained_routines(self):
        with patch.dict(os.environ, {"DECLAN_SENSITIVE_ROUTINES":"night,guest,sexy,dinner,movie"}):
            self.assertEqual(sc.sensitive_group("good night and turn off the light",(("night",{}),"turn off the light"),{}),"night")
            self.assertEqual(sc.sensitive_group("bedroom mood",None,{},{"bedroom mood":"start"}),"sexy")
            self.assertEqual(sc.sensitive_group("guests have left",None,{"guests have left":"clear"}),"guest")
            self.assertEqual(sc.sensitive_group("dinner time",None,{},None,{"dinner time"}),"dinner")
    def test_good_night_respects_unchecked_confirmation_setting(self):
        routine = (("night", {}), None)
        mapping = {"night": {"script": "script.good_night", "phrases": ["good night"],
                             "fields": {}, "sensitive": False}}
        with patch("routine_registry.load", return_value=mapping):
            self.assertIsNone(sc.sensitive_group("good night", routine, {}))
            self.assertIsNone(sc.sensitive_group("time for bed", None, {}))
        self.assertEqual(self.gate.evaluate(session="s1", origin="kitchen", phrase="good night",
                                            group=None, speaker=None)[0], "allow")

    def test_good_night_respects_checked_confirmation_setting(self):
        routine = (("night", {}), None)
        mapping = {"night": {"script": "script.good_night", "phrases": ["good night"],
                             "fields": {}, "sensitive": True}}
        with patch("routine_registry.load", return_value=mapping):
            self.assertEqual(sc.sensitive_group("good night", routine, {}), "custom:night")
            self.assertEqual(sc.sensitive_group("time for bed", None, {}), "custom:night")

    def test_legacy_night_default_when_no_saved_mapping(self):
        with patch("routine_registry.load", return_value={}):
            self.assertEqual(sc.sensitive_group("good night", (("night", {}), None), {}), "night")

    def test_prompt_never_executes_command(self):
        from pathlib import Path
        server=Path(__file__).resolve().parents[1].joinpath("server.py").read_text()
        self.assertLess(server.index('decision, approved_phrase = SENSITIVE_CONFIRMATIONS.evaluate'),server.index('timer_result = timers.handle('))
        self.assertLess(server.index('decision, approved_phrase = SENSITIVE_CONFIRMATIONS.evaluate'),server.index('elif phrase in GUEST_COMMANDS:'))
        self.assertIn('if decision in {"prompt", "cancelled", "denied"}:',server)

if __name__=="__main__": unittest.main()
