"""Conversation agent: understand loose speech, then act (safely), ask or answer."""
import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

import server
from declan.ai import conversation_agent as agent
from declan.ai import general_chat
from declan.ai.action_plan import CandidateAction
from declan.core import history
from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha.light_command_parsing import parse_light_command
from declan.music import music
from declan.timers import timers
from declan.turn import conversation_entry, conversation_turn

ROOT = Path(__file__).resolve().parents[1]
DEVICES = [
    {"entity_id": "light.kitchen_spots", "state": "off", "declan_area": "Kitchen",
     "attributes": {"friendly_name": "Kitchen Spots"}},
    {"entity_id": "light.kitchen_pendant", "state": "off", "declan_area": "Kitchen",
     "attributes": {"friendly_name": "Kitchen Pendant"}},
    {"entity_id": "light.office", "state": "on", "declan_area": "Office", "attributes": {"friendly_name": "Office"}},
    {"entity_id": "media_player.lounge_tv", "state": "off", "declan_area": "Lounge",
     "attributes": {"friendly_name": "Lounge TV"}},
    {"entity_id": "lock.front_door", "state": "locked", "declan_area": "Hall", "attributes": {}},
    {"entity_id": "light.broken", "state": "unavailable", "declan_area": "Hall", "attributes": {}},
]
CHECKS = (lambda p: parse_light_command(p) is not None, lambda p: music.parse(p) is not None,
          lambda p: music.parse_control(p) is not None, timers.matches)
ROUTINES = {"good night", "movie time"}


def context(devices=DEVICES, room="Office"):
    return agent.build_context("it's dark in here", you_are_in=room, dialogue=[], devices=devices,
                               areas={"Kitchen", "Office", "Lounge"}, music_rooms={"kitchen", "everywhere"},
                               routines=ROUTINES)


class ContextAndSchemaTests(unittest.TestCase):
    def test_origin_room_first_only_agent_domains_and_available(self):
        payload, permitted = context()
        self.assertEqual(payload["devices"][0]["entity_id"], "light.office")
        self.assertEqual(set(permitted), {"light.kitchen_spots", "light.kitchen_pendant", "light.office",
                                          "media_player.lounge_tv"})
        self.assertEqual(payload["you_are_in"], "Office")
        self.assertIn("good night", payload["routines"])

    def test_schema_enumerates_entities_and_services(self):
        _, permitted = context()
        schema = agent.response_schema(permitted)
        variants = schema["properties"]["device_actions"]["items"]["anyOf"]
        media = next(v for v in variants if "media_player.lounge_tv" in v["properties"]["entity_id"]["enum"])
        self.assertIn("turn_on", media["properties"]["service"]["enum"])
        self.assertEqual(schema["properties"]["device_actions"]["maxItems"], agent.MAX_DEVICE_ACTIONS)
        self.assertEqual(agent.response_schema({})["properties"]["device_actions"]["maxItems"], 0)
        body = agent.request_body(*context(), model="gpt-5-mini", profile={"reasoning_effort": "low"})
        self.assertFalse(body["store"])
        self.assertNotIn("tools", body)


class SpendTests(unittest.TestCase):
    def test_general_questions_send_no_house_context(self):
        many = [{"entity_id": f"light.lamp_{i}", "state": "off", "declan_area": "Lounge",
                 "attributes": {"friendly_name": f"Lamp {i}"}} for i in range(100)]
        slim, permitted = agent.build_context("Where is Peru?", you_are_in="Lounge", dialogue=[], devices=many,
                                              areas={"Lounge"}, music_rooms={"kitchen"}, routines=ROUTINES)
        self.assertEqual((slim["devices"], slim["rooms"], slim["routines"], permitted), ([], [], [], {}))
        full, _ = agent.build_context("it's dark in here", you_are_in="Lounge", dialogue=[], devices=many,
                                      areas={"Lounge"}, music_rooms={"kitchen"}, routines=ROUTINES)
        slim_body = agent.request_body(slim, {}, model="m", profile={})
        full_body = agent.request_body(full, {"light.lamp_0": many[0]}, model="m", profile={})
        self.assertLess(len(json.dumps(slim_body)) * 3, len(json.dumps(full_body)))
        self.assertLessEqual(slim_body["max_output_tokens"], 800)

    def test_house_questions_and_follow_ups_keep_context(self):
        for text in ("what can you do", "is the office light on", "is movie time running", "what's playing"):
            with self.subTest(text=text):
                self.assertFalse(agent.is_general_question(text, names=["Office", "movie time"]))
        payload, _ = agent.build_context("where is peru", you_are_in="Office",
                                         dialogue=[{"who": "declan", "text": "Spots or pendant?"}],
                                         devices=DEVICES, areas={"Office"}, music_rooms=set(), routines=set())
        self.assertTrue(payload["devices"])

    def test_answers_are_asked_to_be_short(self):
        self.assertIn("ONE short sentence, under 20 words", agent.INSTRUCTIONS)


class DecisionValidationTests(unittest.TestCase):
    def parse(self, raw):
        _, permitted = context()
        return agent.parse_decision(raw, permitted, routines=ROUTINES, checks=CHECKS)

    def test_valid_actions_and_commands_survive(self):
        decision = self.parse({"kind": "act", "say": "Office lights on, and some jazz.",
                               "device_actions": [{"entity_id": "light.office", "service": "turn_on"}],
                               "commands": ["Play jazz in the kitchen.", "run good night", "set a timer for 5 minutes"]})
        self.assertEqual(decision.device_actions, (CandidateAction("light.office", "turn_on"),))
        self.assertEqual(decision.commands, ("play jazz in the kitchen", "run good night", "set a timer for 5 minutes"))

    def test_invented_or_unsafe_proposals_are_dropped(self):
        decision = self.parse({"kind": "act", "say": "Done.",
                               "device_actions": [{"entity_id": "lock.front_door", "service": "unlock"},
                                                  {"entity_id": "light.office", "service": "toggle"},
                                                  {"entity_id": "script.anything", "service": "turn_on"}],
                               "commands": ["yes", "confirm", "run the garage opener", "forget this conversation",
                                            "unlock the door"]})
        self.assertEqual(decision.kind, "ask")  # nothing valid left: ask, never claim "Done."
        self.assertNotIn("Done", decision.say)
        self.assertEqual(len(decision.rejected), 7)  # 3 actions + the first 4 commands (max 4 considered)

    def test_ask_and_answer(self):
        self.assertEqual(self.parse({"kind": "ask", "say": "The spots or the pendant?", "device_actions": [],
                                     "commands": []}).kind, "ask")
        answer = self.parse({"kind": "answer", "say": "I look after lights, music and routines.",
                             "device_actions": [{"entity_id": "light.office", "service": "turn_on"}], "commands": []})
        self.assertEqual(answer.device_actions, ())  # an answer never acts
        with self.assertRaises(ValueError):
            self.parse({"kind": "dance", "say": "x", "device_actions": [], "commands": []})


class ExecuteTests(unittest.TestCase):
    def run_decision(self, decision, *, summary=None, dispatch=None, prompt=None):
        dispatched = []

        def dispatch_command(command):
            dispatched.append(command)
            return dispatch(command) if dispatch else SimpleNamespace(reply=f"Done: {command}.", outcome=Outcome.REQUESTED)
        result = conversation_turn.execute(
            decision, {"light.office": DEVICES[2]}, connection=("http://ha", {}, object()),
            dispatch_command=dispatch_command, confirm_command=lambda command: prompt,
            run_devices=lambda actions, permitted, connection: summary,
            result_factory=lambda reply, outcome, base=None: SimpleNamespace(reply=reply, outcome=outcome))
        return result, dispatched

    def test_verified_devices_use_agent_wording_otherwise_the_truth(self):
        decision = agent.AgentDecision("act", "Office lights on.", (CandidateAction("light.office", "turn_on"),))
        ok, _ = self.run_decision(decision, summary=ExecutionResult("All confirmed", Outcome.CONFIRMED))
        self.assertEqual((ok.dispatch_result.reply, ok.dispatch_result.outcome), ("Office lights on.", Outcome.CONFIRMED))
        bad, _ = self.run_decision(decision, summary=ExecutionResult("No actions confirmed: 1 failed", Outcome.UNVERIFIED))
        self.assertEqual(bad.dispatch_result.reply, "No actions confirmed: 1 failed")

    def test_commands_run_through_dispatch_and_sensitive_ones_stop_for_confirmation(self):
        decision = agent.AgentDecision("act", "Jazz it is.", (), ("play jazz in the kitchen",))
        result, dispatched = self.run_decision(decision)
        self.assertEqual(dispatched, ["play jazz in the kitchen"])
        self.assertIn("Done: play jazz in the kitchen.", result.dispatch_result.reply)
        prompt = {"reply": "Say yes to confirm.", "session_id": "s"}
        held, dispatched = self.run_decision(agent.AgentDecision("act", "x", (), ("run lock down",)), prompt=prompt)
        self.assertEqual((held.immediate_reply, dispatched), (prompt, []))

    def test_ask_keeps_mic_open_and_answer_does_not(self):
        asked, _ = self.run_decision(agent.AgentDecision("ask", "Spots or pendant?"))
        self.assertTrue(asked.follow_up)
        answered, _ = self.run_decision(agent.AgentDecision("answer", "Lights, music and routines."))
        self.assertEqual((answered.follow_up, answered.dispatch_result.outcome), (False, Outcome.CHAT_ANSWER))


class DialogueTests(unittest.TestCase):
    def test_remember_expiry_and_awaiting(self):
        conversation_turn.remember("s1", "kitchen", "lights on", "Spots or pendant?", asked=True, now=100.0)
        self.assertTrue(conversation_turn.awaiting_answer("s1", "kitchen", now=150.0))
        self.assertEqual(len(conversation_turn.dialogue("s1", "kitchen", now=150.0)), 2)
        self.assertFalse(conversation_turn.awaiting_answer("s1", "kitchen", now=1000.0))
        self.assertEqual(conversation_turn.dialogue("s1", "lounge", now=150.0), [])  # never crosses rooms

    def test_vague_music_prefers_agent(self):
        self.assertTrue(conversation_turn.prefers_agent("play something", parse_music=music.parse))
        self.assertFalse(conversation_turn.prefers_agent("play the beatles", parse_music=music.parse))

    def test_gate_bypass_for_agent_questions(self):
        source = (ROOT / "declan/turn/turn_preflight.py").read_text()
        self.assertIn("pending_retry or _agent_asked(session_id, scope)", source)


class FullTurnTests(unittest.TestCase):
    """Real HTTP handler; HA and OpenAI replaced by fakes."""
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history, 'DATABASE', Path(directory) / 'history.db'))
        self.enterContext(patch.object(general_chat, 'PATH', Path(directory) / 'chat.json'))
        general_chat.save({"enabled": True, "monthly_budget_usd": "20.00"})
        self.enterContext(patch.object(server, "SESSION_STORE", server.session_store.SessionStore()))
        self.enterContext(patch.object(server, 'read_guest_mode', return_value='off'))
        self.enterContext(patch.object(server, 'read_visitors_present', return_value=False))
        self.enterContext(patch.object(server, 'guarded_openai_fallback_result', return_value=None))
        self.enterContext(patch.object(server, 'select_routine_turn_result', return_value=None))
        self.enterContext(patch.object(server, 'handle_light_request_result', return_value=None))
        self.enterContext(patch.object(server.CAPTURE_ARBITER, 'claim', return_value=True))
        self.enterContext(patch.dict(server.os.environ, {'DECLAN_ASSIST_TOKEN': 'test'}))
        self.enterContext(patch.object(server, 'ha_device_connection', return_value=None))
        self.enterContext(patch.object(conversation_entry.script_discovery, 'discover_result',
                                       return_value=SimpleNamespace(scripts=(), error=None)))
        self.decide = self.enterContext(patch.object(conversation_turn, "decide"))

    def ask(self, message, session=None):
        handler = object.__new__(server.Handler)
        handler.path = '/api/assist'
        body = json.dumps({"message": message, "session_id": session, "device_id": "kitchen"}).encode()
        handler.rfile = io.BytesIO(body)
        handler.headers = Message()
        for key, value in {'Content-Type': 'application/json', 'Content-Length': str(len(body)),
                           'Authorization': 'Bearer test'}.items():
            handler.headers[key] = value
        setattr(handler, "server", SimpleNamespace(bad_tokens=SimpleNamespace(check=lambda *args: 0)))
        handler.client_address = ('127.0.0.1', 1)
        setattr(handler, 'has_ingress_access', lambda: True)
        setattr(handler, 'send_json', Mock())
        setattr(handler, 'log_error', Mock())
        handler.handle_post()
        status, result = cast(Mock, handler.send_json).call_args.args
        self.assertEqual(status, 200)
        return result

    def test_question_keeps_listening_then_answer_is_understood_in_context(self):
        self.decide.return_value = (agent.AgentDecision("ask", "The spots or the pendant?"), {})
        first = self.ask("put the big light on")
        self.assertIn("spots or the pendant", first["reply"])
        self.assertTrue(first["continue_conversation"])
        self.assertTrue(conversation_turn.awaiting_answer(first["session_id"]))
        self.decide.return_value = (agent.AgentDecision("answer", "Righto."), {})
        second = self.ask("the spots", first["session_id"])
        self.assertFalse(second["continue_conversation"])
        context = self.decide.call_args.args[1]
        self.assertIn("devices", context)

    def test_help_is_answered(self):
        self.decide.return_value = (agent.AgentDecision("answer", "I can do lights, music and routines."), {})
        result = self.ask("what can you do")
        self.assertIn("lights, music and routines", result["reply"])
        self.assertFalse(result["continue_conversation"])

    def test_vague_music_never_reaches_literal_spotify_search(self):
        self.decide.return_value = (agent.AgentDecision("act", "Some jazz.", (), ("play jazz in the kitchen",)), {})
        with patch.object(server, "play_music_result", create=True), \
                patch("declan.turn.turn_dispatch_orchestration.dispatch") as dispatch:
            dispatch.return_value = conversation_entry._result_factory("Playing jazz.", Outcome.REQUESTED)
            result = self.ask("play something")
        phrases = [call.args[0] for call in dispatch.call_args_list]
        self.assertEqual(phrases, ["play jazz in the kitchen"])
        self.assertIn("Playing jazz.", result["reply"])

    def test_successful_phrase_is_learned_then_handled_locally(self):
        self.decide.return_value = (agent.AgentDecision("act", "Jazz.", (), ("play jazz",)), {})
        with patch("declan.turn.turn_dispatch_orchestration.dispatch") as dispatch:
            dispatch.side_effect = lambda phrase, **kwargs: conversation_entry._result_factory(
                "Playing jazz." if phrase == "play jazz" else None, Outcome.REQUESTED if phrase == "play jazz" else None)
            self.ask("put some jazz on")
            self.assertEqual(history.learned_intent("put some jazz on"), "play jazz")
            self.decide.reset_mock()
            result = self.ask("put some jazz on")
        self.decide.assert_not_called()  # second time: local, instant, free
        self.assertIn("Playing jazz.", result["reply"])

    def test_agent_unavailable_falls_back_to_the_rephrase_prompt(self):
        self.decide.side_effect = general_chat.ModelUnavailable("off")
        result = self.ask("flux the capacitor")
        self.assertEqual(result["reply"], server.UNMATCHED_REPLY)
        self.assertTrue(result["continue_conversation"])

    def test_conversation_off_never_calls_the_model(self):
        general_chat.save({"enabled": False, "monthly_budget_usd": "20.00"})
        self.ask("flux the capacitor")
        self.decide.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class FollowUpAndLearningTests(unittest.TestCase):
    def test_confirmed_agent_lights_become_the_follow_up_context(self):
        from declan.core.execution_results import ActionResult, ActionStatus
        summary = ExecutionResult("All confirmed", Outcome.CONFIRMED, (
            ActionResult(0, "light.office", "turn_on", ActionStatus.CONFIRMED),
            ActionResult(1, "light.hall", "turn_on", ActionStatus.FAILED),
            ActionResult(2, "media_player.lounge_tv", "turn_on", ActionStatus.CONFIRMED)))
        decision = agent.AgentDecision("act", "Lights on.", (CandidateAction("light.office", "turn_on"),))
        captured = {}

        def factory(reply, outcome, base=None, lighting_context=None):
            captured["lighting_context"] = lighting_context
            return SimpleNamespace(reply=reply, outcome=outcome)
        conversation_turn.execute(decision, {}, connection=("u", {}, None), dispatch_command=Mock(),
                                  confirm_command=lambda command: None,
                                  run_devices=lambda *args: summary, result_factory=factory)
        self.assertEqual(captured["lighting_context"], ("light.office",))
        result = conversation_entry._result_factory("x", Outcome.CONFIRMED, lighting_context=("light.office",))
        self.assertEqual(result.lighting_context, ("light.office",))

    def learn(self, message, command, *, rooms=frozenset(), outcome=Outcome.CONFIRMED, vague=False, devices=()):
        decision = agent.AgentDecision("act", "x", tuple(devices), (command,) if command else ())
        return conversation_turn.learnable(message, decision, SimpleNamespace(outcome=outcome), rooms=rooms, vague=vague)

    def test_learns_only_safe_single_successful_commands(self):
        self.assertEqual(self.learn("put some jazz on", "play jazz"), ("put some jazz on", "play jazz"))
        self.assertEqual(self.learn("switch on the lounge lamp please", "turn on the lounge lamp", rooms={"Lounge"}),
                         ("switch on the lounge lamp please", "turn on the lounge lamp"))
        for message, command, kwargs in (
                ("it's dark in here", "turn on the kitchen lights", {"rooms": {"Kitchen"}}),
                ("switch the lamp on", "turn on the lounge lamp", {"rooms": {"Lounge"}}),  # room not said
                ("turn them off", "turn off the lounge lamp", {}),
                ("play something", "play jazz in the kitchen", {"vague": True}),
                ("put some jazz on", "play jazz", {"outcome": Outcome.FAILED}),
                ("bedtime", "run good night", {}),
                ("give me ten minutes", "set a timer for 10 minutes", {}),
                ("lights please", "turn on the lights", {"devices": (CandidateAction("light.office", "turn_on"),)})):
            with self.subTest(message=message):
                self.assertIsNone(self.learn(message, command, **kwargs))

    def test_learned_source_is_shown(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(history, "DATABASE", Path(folder) / "h.db"):
            history.teach_phrase("put some jazz on", "play jazz", automatic=True, source="conversation")
            history.teach_phrase("put some jazz on", "play rock", automatic=True, source="conversation")
            records = {row["phrase"]: row for row in history.learned_intent_records()}
        self.assertEqual(records["put some jazz on"]["source"], "conversation")
        self.assertEqual(records["put some jazz on"]["target"], "play jazz")  # never overwritten
        js = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
        self.assertIn("conversation:'learned from a conversation'", js)
