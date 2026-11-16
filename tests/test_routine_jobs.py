"""Receipt latency, exactly-once dispatch, and durable background evidence."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from io import BytesIO
import unittest

import script_discovery
import personality_policy
import server
import test_ha_audit as audit_tests


class BackgroundDispatchTests(unittest.TestCase):
    def test_movie_uses_receipt_endpoint_and_never_blocking_execute(self):
        with patch.object(server, "ha_device_connection", return_value="connection"), \
             patch.object(server.script_discovery, "enqueue", return_value=("requested", "started", "job")) as enqueue, \
             patch.object(server.script_discovery, "execute", side_effect=AssertionError("blocking call")):
            result = server.execute_routine(("auto:script.movie_time", {"_declan_background": True, "requested_action": "end"}), [])
        enqueue.assert_called_once_with("connection", "script.movie_time", {"requested_action": "end"})
        self.assertEqual(result[1], "started")

    def test_receipt_has_short_timeout_and_correlated_id(self):
        opener = MagicMock()
        def receipt(request, timeout):
            self.assertEqual(timeout, 2)
            self.assertEqual(request.full_url, "http://ha/api/declan_two/routine-jobs")
            body = json.loads(request.data)
            response = MagicMock(status=202)
            response.read.return_value = json.dumps({**body, "status": "accepted"}).encode()
            response.__enter__.return_value = response
            return response
        opener.open.side_effect = receipt
        result = script_discovery.enqueue(("http://ha", {}, opener), "script.movie_time", {})
        self.assertEqual(result[1], "started")
        opener.open.assert_called_once()

    def test_timeout_or_rejection_never_retries_or_claims_completion(self):
        for error, expected in ((TimeoutError(), "unverified"),
                (HTTPError("http://ha", 409, "busy", {}, BytesIO()), "busy"),
                (HTTPError("http://ha", 404, "missing", {}, BytesIO()), "not_configured")):
            opener = MagicMock()
            opener.open.side_effect = error
            reply, outcome, _ = script_discovery.enqueue(("http://ha", {}, opener), "script.movie_time", {})
            self.assertEqual(outcome, expected)
            opener.open.assert_called_once()
            self.assertNotIn("completed", reply)

    def test_request_speech_is_honest_and_directional(self):
        for action in ("start", "end", "toggle"):
            reply = personality_policy.movie_request_reply(action, guest=False, visitor_present=False)
            self.assertIn("requested", reply)
            self.assertNotIn("completed", reply)
            self.assertNotIn("Shared Local Routine", reply)
        self.assertIn("shutdown", personality_policy.movie_request_reply("end", guest=True, visitor_present=False))


class RoutineJobTests(unittest.IsolatedAsyncioTestCase):
    # Reuse loaded HA interfaces, not their tests.
    def setUp(self):
        audit_tests.AuditViewTests.setUp(self)
        self.pending = []
        self.calls = []
        self.fields = {"requested_action": {}, "request_id": {}, "routine_id": {}}
        self.entity = SimpleNamespace(unique_id="movie_time", fields=self.fields)
        self.hass.data["script"] = SimpleNamespace(get_entity=lambda entity_id: self.entity)
        self.hass.services.has_service = lambda *args: True
        def schedule(coro, name, *, eager_start):
            self.assertFalse(eager_start)
            self.pending.append(coro)
        self.hass.async_create_background_task = schedule
        self.endpoint = self.jobs_view.DeclanRoutineJobsView()
        self.endpoint.context = lambda request: SimpleNamespace(id="context1")

    def tearDown(self):
        for coro in self.pending:
            coro.close()
        audit_tests.AuditViewTests.tearDown(self)

    def request(self, number=1, admin=True, entity_id="script.movie_time"):
        class Request(dict):
            app = {"hass": self.hass}
            content_length = 200
            async def json(inner):
                return {"job_id": "declan-" + f"{number:032x}", "entity_id": entity_id,
                        "parameters": {"requested_action": "start", "secret": "do-not-save", "request_id": "spoof"}}
        return Request(hass_user=SimpleNamespace(is_admin=admin))

    async def test_receipt_precedes_execution_and_partial_result_is_saved(self):
        async def service(domain, name, parameters, **options):
            self.calls.append((domain, name, parameters, options))
            self.assertEqual(parameters["requested_action"], "start")
            self.assertNotIn("secret", parameters)
            return {"request_id": parameters["request_id"], "routine_id": parameters["routine_id"],
                    "outcome": "partial", "reason_code": "projector_unavailable",
                    "steps": [{"target": "screen", "status": "confirmed"},
                              {"target": "projector", "status": "unavailable", "secret": "hidden"}]}
        self.hass.services.async_call = service
        payload, options = await self.endpoint.post(self.request())
        self.assertEqual(options["status"], 202)
        self.assertEqual(self.calls, [])
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(len(self.pending), 1)
        await self.pending[0]
        state = await self.jobs_view.job_state(self.hass)
        job = state["jobs"][payload["job_id"]]
        self.assertEqual(job["outcome"], "partial")
        self.assertEqual(job["reason"], "projector_unavailable")
        self.assertNotIn("hidden", str(job))
        self.assertNotIn("do-not-save", str(job))
        await self.endpoint.post(self.request())
        self.assertEqual(len(self.pending), 1)  # Idempotent receipt, no replay.
        self.hass.data.pop("declan_two_routine_jobs")
        restored = await self.jobs_view.latest_results(self.hass)
        self.assertEqual(restored["script.movie_time"]["outcome"], "partial")

    async def test_acknowledgement_does_not_wait_for_blocked_service(self):
        gate = asyncio.Event()
        async def service(*args, **kwargs):
            await gate.wait()
            return {"outcome": "unknown"}
        self.hass.services.async_call = service
        tasks = []
        self.hass.async_create_background_task = lambda coro, name, **kwargs: tasks.append(asyncio.create_task(coro))
        try:
            _, options = await asyncio.wait_for(self.endpoint.post(self.request()), timeout=0.5)
            self.assertEqual(options["status"], 202)
            await asyncio.sleep(0)
            self.assertFalse(tasks[0].done())
        finally:
            gate.set()
            await asyncio.gather(*tasks)

    async def test_busy_duplicate_authentication_and_restart_never_replay(self):
        await self.endpoint.post(self.request())
        _, options = await self.endpoint.post(self.request(2))
        self.assertEqual(options["status"], 409)
        with self.assertRaises(self.web.HTTPForbidden):
            await self.endpoint.post(self.request(3, admin=False))
        with self.assertRaises(self.web.HTTPBadRequest):
            await self.endpoint.post(self.request(entity_id="script.other"))
        self.hass.data.pop("declan_two_routine_jobs")
        state = await self.jobs_view.job_state(self.hass)
        job = next(iter(state["jobs"].values()))
        self.assertEqual(job["outcome"], "unverified")
        self.assertEqual(job["reason"], "interrupted")
        self.assertEqual(len(self.pending), 1)

    async def test_exception_is_logged_without_raw_error_or_extra_speech(self):
        async def service(*args, **kwargs):
            raise ValueError("secret-token")
        self.hass.services.async_call = service
        await self.endpoint.post(self.request())
        await self.pending[0]
        job = (await self.jobs_view.latest_results(self.hass))["script.movie_time"]
        self.assertEqual(job["outcome"], "failed")
        self.assertEqual(job["reason"], "ValueError")
        self.assertNotIn("secret-token", str(job))

    async def test_result_validation_does_not_promote_unverified_steps(self):
        job = {"job_id": "j", "entity_id": "script.movie_time"}
        summarize = self.jobs_view.summarize_result
        self.assertEqual(summarize({"outcome": "success", "request_id": "wrong"}, job, ["request_id"])["outcome"], "unverified")
        self.assertEqual(summarize({"outcome": "success", "steps": [{"status": "unavailable"}]}, job, [])["outcome"], "unverified")
        self.assertEqual(summarize({"outcome": []}, job, [])["outcome"], "unverified")
        self.assertEqual(summarize({"outcome": "success", "steps": [{"status": "confirmed"}, {"status": "requested", "required": False}]}, job, [])["outcome"], "reported_success")

    async def test_storage_failure_rejects_request_without_scheduling(self):
        state = await self.jobs_view.job_state(self.hass)
        async def fail(*args): raise OSError("private-path")
        with patch.object(state["store"], "async_save", fail):
            payload, options = await self.endpoint.post(self.request())
        self.assertEqual(options["status"], 503)
        self.assertEqual(self.pending, [])
        self.assertEqual(state["jobs"], {})
        self.assertNotIn("private-path", str(payload))

    async def test_background_results_reopen_review_and_reach_audit(self):
        before = await self.view.collect_report(self.hass)
        row = next(row for row in before["routines"] if row["entity_id"] == "automation.actual_entity")
        state = await self.jobs_view.job_state(self.hass)
        await self.jobs_view.save_job(state, {"job_id": "j", "entity_id": row["entity_id"], "outcome": "partial",
            "created_at": "2026-11-16", "updated_at": "2026-11-16", "steps": []})
        after = await self.view.collect_report(self.hass)
        changed = next(item for item in after["routines"] if item["entity_id"] == row["entity_id"])
        self.assertEqual(changed["background_result"]["outcome"], "partial")
        self.assertNotEqual(changed["fingerprint"], row["fingerprint"])


