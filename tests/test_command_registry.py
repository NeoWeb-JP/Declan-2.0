"""Priority, overlap, failure ownership, origin routing and real HTTP dispatch."""
from typing import Any, cast
import io
import json
import tempfile
from dataclasses import FrozenInstanceError, replace
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from declan.turn import command_registry as commands
from execution_results import ExecutionResult, Outcome
import history
import server


def dependencies():
    return commands.Dependencies(
        parse_status=Mock(return_value=None), describe_status=Mock(return_value=("Lamp is on.","confirmed","light.lamp")),
        connection=Mock(return_value="connection"), inventory=Mock(return_value=([
            {"entity_id":"input_boolean.guest_mode","state":"off"}],None)),
        decorate=Mock(side_effect=lambda reply,*_:reply), guest_mode_entity="input_boolean.guest_mode",
        parse_feedback=Mock(return_value=None), feedback=Mock(return_value=("Feedback saved.","music_feedback")),
        parse_control=Mock(return_value=None), control=Mock(return_value=("Stopped.","confirmed")),
        parse_music=Mock(return_value=None), play=Mock(return_value=("Playing.","confirmed")),
        music_inventory=Mock(), areas=Mock(),
    )


class RegistryTests(TestCase):
    def setUp(self):
        self.deps=dependencies()
        self.context=commands.RequestContext("test","assist",last_device="light.lamp",
                                             origin_device="device",satellite="satellite")

    def test_registration_order_does_not_change_priority(self):
        calls=[]
        def handler(name,priority):
            def execute(*_):
                calls.append(name)
                return commands.HandledCommand(name, ExecutionResult(name, Outcome.CONFIRMED))
            return commands.Handler(name, priority, lambda _: True, execute)
        registry=commands.HandlerRegistry((handler("later",20),handler("first",10)))
        self.assertEqual(registry.dispatch(self.context).handler,"first")
        self.assertEqual(calls,["first"])
        self.assertEqual([h.priority for h in registry.handlers],[10,20])
        with self.assertRaises(FrozenInstanceError):
            setattr(registry, 'handlers', ())
        with self.assertRaises(ValueError):
            registry.dispatch("not a context")

    def test_invalid_duplicate_or_ambiguous_registrations_are_rejected(self):
        good=commands.Handler("first",10,lambda _:None,lambda *_:None)
        for handlers in (
            (good,replace(good)), (good,replace(good,name="second")),
            (good,replace(good,priority=20)), ("not a handler",),
            (replace(good,priority=True),), (replace(good,name=""),),
            (cast(Any, replace)(good,match=None),), (cast(Any, replace)(good,execute=None),),
        ):
            with self.subTest(handlers=handlers), self.assertRaises(ValueError):
                cast(Any, commands.HandlerRegistry)(handlers)
        with self.assertRaises(ValueError):
            commands.registry(None)

    def test_unmatched_command_has_no_connections_or_side_effects(self):
        self.assertIsNone(commands.registry(self.deps).dispatch(self.context))
        for method in (self.deps.connection,self.deps.inventory,self.deps.feedback,
                       self.deps.control,self.deps.play,self.deps.describe_status):
            method.assert_not_called()

    def test_status_wins_overlap_and_preserves_target_and_guest_tone(self):
        self.deps.parse_status.return_value=("lamp","on")
        self.deps.parse_feedback.return_value=("like","track")
        self.deps.parse_control.return_value=("pause",None)
        self.deps.parse_music.return_value=("room","country","spotify")
        result=commands.registry(self.deps).dispatch(self.context)
        self.assertEqual(result.handler,"device_status")
        self.assertEqual(result.status_target,"light.lamp")
        self.assertIs(result.result.outcome,Outcome.CONFIRMED)
        self.deps.parse_status.assert_called_once_with("test","light.lamp")
        self.deps.decorate.assert_called_once_with("Lamp is on.","device_status","off")
        self.deps.parse_feedback.assert_not_called()
        self.deps.feedback.assert_not_called()
        self.deps.control.assert_not_called()
        self.deps.play.assert_not_called()

    def test_status_errors_own_the_command_without_falling_into_music(self):
        self.deps.parse_status.return_value=("lamp","on")
        self.deps.parse_control.return_value=("pause",None)
        for connection,inventory,expected in (
            (None,([],None),Outcome.NOT_CONFIGURED),
            ("connection",(None,"unavailable"),Outcome.UNAVAILABLE),
            ("connection",([],None),Outcome.UNRESOLVED),
        ):
            self.deps.connection.return_value=connection
            self.deps.inventory.return_value=inventory
            self.deps.describe_status.return_value=("Which lamp?","unresolved",None)
            result=commands.registry(self.deps).dispatch(self.context)
            self.assertIs(result.result.outcome,expected)
            self.deps.control.assert_not_called()
        self.deps.decorate.assert_not_called()

    def test_feedback_wins_music_overlap_and_keeps_typed_feedback_outcome(self):
        self.deps.parse_feedback.return_value=("like","track")
        self.deps.parse_control.return_value=("pause",None)
        self.deps.parse_music.return_value=("room","country","spotify")
        result=commands.registry(self.deps).dispatch(self.context)
        self.assertEqual(result.handler,"music_feedback")
        self.assertIs(result.result.outcome,Outcome.MUSIC_FEEDBACK)
        self.deps.feedback.assert_called_once_with(("like","track"),"connection",self.deps.music_inventory)
        self.deps.parse_control.assert_not_called()
        self.deps.control.assert_not_called()
        self.deps.play.assert_not_called()

    def test_music_control_keeps_device_origin_and_assist_flag(self):
        self.deps.parse_control.return_value=("pause",None)
        self.deps.parse_music.return_value=("room","country","spotify")
        commands.registry(self.deps).dispatch(self.context)
        self.deps.control.assert_called_once_with(("pause",None),"connection",self.deps.music_inventory,
            origin="device",read_areas=self.deps.areas,assist=True)
        self.deps.parse_music.assert_not_called()
        self.deps.play.assert_not_called()
        self.deps.control.reset_mock()
        commands.registry(self.deps).dispatch(replace(self.context,source="browser_keyboard",origin_device=None))
        self.assertEqual(self.deps.control.call_args.kwargs["origin"],"satellite")
        self.assertFalse(self.deps.control.call_args.kwargs["assist"])

    def test_music_play_keeps_satellite_precedence_and_omits_unknown_origin(self):
        command=("room","country","spotify")
        self.deps.parse_music.return_value=command
        commands.registry(self.deps).dispatch(self.context)
        self.deps.play.assert_called_once_with(command,"connection",self.deps.music_inventory,origin="satellite")
        self.deps.play.reset_mock()
        commands.registry(self.deps).dispatch(replace(self.context,satellite=None))
        self.assertEqual(self.deps.play.call_args.kwargs,{"origin":"device"})
        self.deps.play.reset_mock()
        commands.registry(self.deps).dispatch(replace(self.context,satellite=None,origin_device=None))
        self.deps.play.assert_called_once_with(command,"connection",self.deps.music_inventory)

    def test_uncertain_dispatch_and_executor_exception_never_try_next_handler(self):
        self.deps.parse_feedback.return_value=("like","track")
        self.deps.parse_control.return_value=("pause",None)
        self.deps.feedback.return_value=("Not confirmed.","unverified")
        result=commands.registry(self.deps).dispatch(self.context)
        self.assertIs(result.result.outcome,Outcome.UNVERIFIED)
        self.deps.control.assert_not_called()
        self.deps.feedback.side_effect=OSError("lost response")
        with self.assertRaises(OSError):
            commands.registry(self.deps).dispatch(self.context)
        self.deps.control.assert_not_called()

    def test_invalid_executor_result_cannot_continue_to_another_handler(self):
        later=Mock()
        registry=commands.HandlerRegistry((
            commands.Handler("first",10,lambda _:True,lambda *_:None),
            commands.Handler("later",20,lambda _:True,later),
        ))
        with self.assertRaises(ValueError):
            registry.dispatch(self.context)
        later.assert_not_called()


class HTTPRegistryTests(TestCase):
    def setUp(self):
        directory=self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history,"DATABASE",Path(directory)/"history.db"))
        self.enterContext(patch.object(server, "SESSION_STORE", server.session_store.SessionStore()))
        self.enterContext(patch.object(server,"read_guest_mode",return_value="off"))
        self.enterContext(patch.object(server,"read_visitors_present",return_value=False))
        self.enterContext(patch.object(server,'select_routine_turn_result',return_value=None))
        self.enterContext(patch.object(server.conditions,"handle_result",return_value=None))
        self.enterContext(patch.object(server.timers,"handle",return_value=None))

    def ask(self,phrase):
        handler=object.__new__(server.Handler)
        handler.path="/api/assist"
        handler.headers=Message()
        raw=json.dumps({"message":phrase,"device_id":"kitchen"}).encode()
        for key,value in {"Authorization":"Bearer test","Content-Type":"application/json",
                           "Content-Length":str(len(raw))}.items():
            handler.headers[key]=value
        handler.rfile=io.BytesIO(raw)
        handler.client_address=("127.0.0.1",1)
        setattr(handler, "server", SimpleNamespace(bad_tokens=SimpleNamespace(check=lambda *_:0)))
        setattr(handler, 'send_json', Mock())
        setattr(handler, 'log_error', Mock())
        with patch.dict(server.os.environ,{"DECLAN_ASSIST_TOKEN":"test"}):
            handler.handle_post()
        status,result=cast(Mock, handler.send_json).call_args.args
        self.assertEqual(status,200,result)
        return result

    def test_actual_music_handler_keeps_failure_in_history_and_does_not_fallback(self):
        with patch.object(server.music,"parse_feedback",return_value=("like","track")), \
             patch.object(server.music,"_feedback_provider",return_value=("Music unavailable.","unavailable")) as feedback, \
             patch.object(server,"guarded_openai_fallback_result") as cloud, \
             patch.object(server,"handle_light_request_result") as lighting:
            result=self.ask("like this track")
        self.assertEqual(result["outcome"],"unavailable")
        self.assertEqual(result["reply"],"Music unavailable.")
        self.assertIs(type(result["outcome"]),str)
        feedback.assert_called_once()
        cloud.assert_not_called()
        lighting.assert_not_called()
        self.assertEqual(history.recent()[0]["outcome"],"unavailable")

    def test_stop_and_information_keep_precedence_over_the_registry(self):
        with patch.object(server.command_registry,"registry") as registry, \
             patch.object(server,"_stop_everywhere_typed_core",return_value=(ExecutionResult("Stopped everywhere.", Outcome.CONFIRMED), None)):
            self.assertEqual(self.ask("stop")["outcome"],"confirmed")
            registry.assert_not_called()
        with patch.object(server.command_registry,"registry") as registry, \
             patch.object(server.conditions,"handle_result",return_value=("Weather unavailable.","unavailable","weather")):
            self.assertEqual(self.ask("what is the weather")["reply"],"Weather unavailable.")
            registry.assert_not_called()
