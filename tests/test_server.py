import os
from pathlib import Path
import sys
import tempfile
import unittest


TEST_DATA = tempfile.TemporaryDirectory()
os.environ["PANEL_PROVIDER"] = "demo"
os.environ["PANEL_DATA_DIR"] = TEST_DATA.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import server  # noqa: E402


class PanelTests(unittest.TestCase):
    def test_only_schedule_and_away_are_allowed(self):
        self.assertEqual(server.ALLOWED_MODES, {"schedule", "away"})

    def test_demo_provider_persists_allowed_modes(self):
        provider = server.DemoProvider()
        provider.set_mode("away")
        self.assertEqual(provider.status()["mode"], "away")
        provider.set_mode("schedule")
        self.assertEqual(provider.status()["mode"], "schedule")

    def test_schedule_uses_guard_mode_not_active_rule(self):
        provider = server.EufyWsProvider.__new__(server.EufyWsProvider)
        state = provider._station_state({"guardMode": 2, "currentMode": 1})
        self.assertEqual(state["mode"], "schedule")
        self.assertFalse(state["pending"])

    def test_away_can_be_pending_during_exit_delay(self):
        provider = server.EufyWsProvider.__new__(server.EufyWsProvider)
        state = provider._station_state({"guardMode": 0, "currentMode": 1})
        self.assertEqual(state["mode"], "away")
        self.assertTrue(state["pending"])

    def test_homepage_payload_is_minimal_and_session_free(self):
        server.PROVIDER.set_mode("schedule")
        handler = server.PanelHandler.__new__(server.PanelHandler)
        payload = handler._homepage_payload()
        self.assertEqual(
            set(payload), {"ok", "mode", "connected", "provider"}
        )
        self.assertEqual(payload["mode"], "schedule")
        self.assertTrue(payload["connected"])


if __name__ == "__main__":
    unittest.main()
