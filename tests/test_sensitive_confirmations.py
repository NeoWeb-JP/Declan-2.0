"""Sensitive Assist confirmations: expiry, origin, replay, speaker and alias safety."""
from typing import Any
import os
import unittest
from unittest.mock import patch
from declan.turn import sensitive_confirmations as sc

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
        routine: tuple[Any, ...]
        routine = (("night", {}), None)
        mapping = {"night": {"script": "script.good_night", "phrases": ["good night"],
                             "fields": {}, "sensitive": False}}
        with patch("declan.turn.routine_registry.load", return_value=mapping):
            self.assertIsNone(sc.sensitive_group("good night", routine, {}))
            self.assertIsNone(sc.sensitive_group("time for bed", None, {}))
        self.assertEqual(self.gate.evaluate(session="s1", origin="kitchen", phrase="good night",
                                            group=None, speaker=None)[0], "allow")

    def test_good_night_respects_checked_confirmation_setting(self):
        routine: tuple[Any, ...]
        routine = (("night", {}), None)
        mapping = {"night": {"script": "script.good_night", "phrases": ["good night"],
                             "fields": {}, "sensitive": True}}
        with patch("declan.turn.routine_registry.load", return_value=mapping):
            self.assertEqual(sc.sensitive_group("good night", routine, {}), "custom:night")
            self.assertEqual(sc.sensitive_group("time for bed", None, {}), "custom:night")

    def test_legacy_night_default_when_no_saved_mapping(self):
        with patch("declan.turn.routine_registry.load", return_value={}):
            self.assertEqual(sc.sensitive_group("good night", (("night", {}), None), {}), "night")

    def test_ha_scripts_do_not_use_declan_confirmation_gate(self):
        from pathlib import Path
        server = Path(__file__).resolve().parents[1].joinpath("server.py").read_text()
        decision = Path(__file__).resolve().parents[1].joinpath(
            "declan/turn/sensitive_confirmation_decision.py").read_text()
        turn = Path(__file__).resolve().parents[1].joinpath(
            "declan/turn/sensitive_confirmation_turn.py").read_text()
        preflight = Path(__file__).resolve().parents[1].joinpath("declan/turn/turn_preflight.py").read_text()
        session_preflight = Path(__file__).resolve().parents[1].joinpath("declan/turn/turn_session_preflight.py").read_text()
        self.assertIn("turn_preflight_entry.resolve(", session_preflight)
        self.assertIn("turn_preflight.resolve(", (Path(__file__).resolve().parents[1] / "declan/turn/turn_preflight_entry.py").read_text())
        self.assertIn("sensitive_confirmation_resolution.resolve_confirmation(", preflight)
        self.assertIn("confirm=sensitive_confirmation_turn.confirmation_turn_result", session_preflight)
        ingress = Path(__file__).resolve().parents[1].joinpath("declan/turn/sensitive_confirmation_resolution.py").read_text()
        self.assertIn("confirmation = confirm(", ingress)
        self.assertIn("return resolve(confirmation, phrase, effective_message)", ingress)
        self.assertIn("evaluate(", turn)
        self.assertIn("confirmation_response(", turn)
        self.assertIn("confirmations.evaluate(", decision)
        self.assertIn("candidate, None, guest_commands, {}, set()", decision)
        orchestration = Path(__file__).resolve().parents[1].joinpath("declan/turn/routine_turn_orchestration.py").read_text()
        self.assertIn("discovery.execute_result(", orchestration)
        self.assertIn("discovery.enqueue_result(", orchestration)
        self.assertIn("household_selection_boundaries.execute_routine_result(", server)
        boundary = (Path(__file__).resolve().parents[1] / "declan" / "ha" / "household_selection_boundaries.py").read_text()
        self.assertIn("discovery=r.script_discovery", boundary)


if __name__=="__main__":
    unittest.main()
