"""Declan 2.0 Running sensor and the down alert (power cut, 26 Nov 2026)."""
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components/declan_two"


class ClientError(Exception):
    pass


def load_sensor():
    session = MagicMock()
    aiohttp = SimpleNamespace(ClientTimeout=lambda total: total, ClientError=ClientError)
    binary_sensor = SimpleNamespace(BinarySensorDeviceClass=SimpleNamespace(RUNNING="running"),
                                    BinarySensorEntity=object)
    with patch.dict("sys.modules", {
        "aiohttp": aiohttp, "homeassistant": SimpleNamespace(), "homeassistant.components": SimpleNamespace(),
        "homeassistant.components.binary_sensor": binary_sensor, "homeassistant.helpers": SimpleNamespace(),
        "homeassistant.helpers.aiohttp_client": SimpleNamespace(async_get_clientsession=lambda hass: session),
    }):
        spec = importlib.util.spec_from_file_location("running_sensor_fixture", INTEGRATION / "binary_sensor.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, session


class SensorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.module, self.session = load_sensor()
        entry = SimpleNamespace(entry_id="abc", data={"url": "http://declan:8000", "token": "t" * 40})
        self.sensor = self.module.DeclanRunningSensor(SimpleNamespace(), entry)

    def answer(self, status=200, payload=None, error=None):
        if error is not None:
            self.session.get.side_effect = error
            return
        response = MagicMock(status=status)
        response.json = AsyncMock(return_value=payload)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        self.session.get.side_effect = None
        self.session.get.return_value = context

    async def test_on_when_declan_answers(self):
        self.answer(payload={"server_version": "2.15.0"})
        await self.sensor.async_update()
        self.assertIs(self.sensor._attr_is_on, True)
        attributes = self.sensor._attr_extra_state_attributes
        self.assertEqual(attributes["version"], "2.15.0")
        self.assertIsNotNone(attributes["last_seen"])
        self.assertIsNone(attributes["problem"])
        url = self.session.get.call_args.args[0]
        self.assertEqual(url, "http://declan:8000/api/capabilities")
        self.assertEqual(self.session.get.call_args.kwargs["headers"], {"Authorization": "Bearer " + "t" * 40})

    async def test_off_when_down_or_refusing(self):
        self.answer(payload={"server_version": "2.15.0"})
        await self.sensor.async_update()
        for kwargs, problem in (({"error": ClientError()}, "Can't reach Declan"),
                                ({"error": TimeoutError()}, "No answer within 5 seconds"),
                                ({"status": 403}, "refused the token"),
                                ({"status": 503}, "HTTP 503")):
            with self.subTest(problem=problem):
                self.answer(**kwargs)
                await self.sensor.async_update()
                self.assertIs(self.sensor._attr_is_on, False)
                self.assertIn(problem, self.sensor._attr_extra_state_attributes["problem"])
                # The last good contact is kept, so you can see when he went down.
                self.assertIsNotNone(self.sensor._attr_extra_state_attributes["last_seen"])

    def test_identity(self):
        self.assertEqual(self.sensor._attr_unique_id, "abc_running")
        self.assertEqual(self.sensor._attr_name, "Declan 2.0 Running")
        self.assertEqual(self.module.SCAN_INTERVAL.total_seconds(), 30)


class WiringTests(unittest.TestCase):
    def test_platform_is_loaded(self):
        self.assertIn('PLATFORMS = ["binary_sensor", ', (INTEGRATION / "__init__.py").read_text())

    def test_alert_automation(self):
        automation = yaml.safe_load((ROOT / "home_assistant/declan_down_alert.automation.yaml").read_text())
        triggers = {trigger["id"]: trigger for trigger in automation["triggers"]}
        self.assertEqual(triggers["down"]["entity_id"], "binary_sensor.declan_2_0_running")
        self.assertEqual(triggers["down"]["for"], {"minutes": 3})
        self.assertEqual(triggers["started"]["event"], "start")
        self.assertEqual(automation["mode"], "restart")
        text = (ROOT / "home_assistant/declan_down_alert.automation.yaml").read_text()
        self.assertEqual(text.count("action: notify.mobile_app_your_iphone"), 2)
        self.assertIn("total_seconds() >= 180", text)  # no "back" message after an update restart


if __name__ == "__main__":
    unittest.main()
