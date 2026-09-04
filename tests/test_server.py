import os
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest


TEST_DATA = tempfile.TemporaryDirectory()
os.environ["PANEL_PROVIDER"] = "demo"
os.environ["PANEL_DATA_DIR"] = TEST_DATA.name
os.environ["BIN_TIMEZONE"] = "UTC"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import server  # noqa: E402


class PanelTests(unittest.TestCase):
    def test_bin_reminder_window_and_black_week(self):
        timezone = server.BIN_TIMEZONE
        before = server.bin_reminder(datetime(2026, 9, 9, 11, 59, tzinfo=timezone))
        wednesday = server.bin_reminder(
            datetime(2026, 9, 9, 12, 0, tzinfo=timezone)
        )
        thursday = server.bin_reminder(
            datetime(2026, 9, 10, 8, 0, tzinfo=timezone)
        )
        after = server.bin_reminder(datetime(2026, 9, 10, 12, 0, tzinfo=timezone))

        self.assertFalse(before["visible"])
        self.assertEqual(wednesday["collection_type"], "black")
        self.assertEqual(wednesday["phase"], "tonight")
        self.assertIn("Food caddy", wednesday["bins"])
        self.assertEqual(thursday["phase"], "morning")
        self.assertFalse(after["visible"])

    def test_bin_reminder_alternates_to_green_and_blue(self):
        reminder = server.bin_reminder(
            datetime(2026, 9, 16, 18, 0, tzinfo=server.BIN_TIMEZONE)
        )
        self.assertEqual(reminder["collection_date"], "2026-09-17")
        self.assertEqual(reminder["collection_type"], "blue-green")
        self.assertEqual(
            reminder["bins"], ["Green bin", "Blue bin", "Food caddy"]
        )

    def test_bin_preview_shows_next_collection_outside_window(self):
        reminder = server.bin_reminder(
            datetime(2026, 9, 4, 14, 0, tzinfo=server.BIN_TIMEZONE), force=True
        )
        self.assertTrue(reminder["visible"])
        self.assertEqual(reminder["phase"], "preview")
        self.assertEqual(reminder["collection_date"], "2026-09-10")
        self.assertEqual(reminder["collection_type"], "black")

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
        self.assertEqual(state["active_mode"], "Home")
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
            set(payload),
            {"ok", "mode", "status", "active_mode", "connected", "provider"},
        )
        self.assertEqual(payload["mode"], "schedule")
        self.assertTrue(payload["connected"])

    def test_homepage_status_includes_active_schedule_rule(self):
        status, active = server.homepage_status(
            {"mode": "schedule", "current_mode": 1}
        )
        self.assertEqual(status, "Schedule · Home")
        self.assertEqual(active, "Home")

    def test_homepage_away_status_is_armed(self):
        status, active = server.homepage_status(
            {"mode": "away", "current_mode": 0}
        )
        self.assertEqual(status, "Armed")
        self.assertEqual(active, "Away")

    def test_weather_codes_are_mapped_to_local_icons(self):
        self.assertEqual(server.weather_condition(0), ("Clear", "clear"))
        self.assertEqual(server.weather_condition(63), ("Rain", "rain"))
        self.assertEqual(server.weather_condition(95), ("Thunderstorms", "storm"))
        self.assertEqual(
            server.weather_condition("invalid"),
            ("Conditions unavailable", "unknown"),
        )

    def test_rain_advice_recommends_umbrella_for_likely_rain(self):
        advice = server.rain_advice(
            2,
            0,
            [
                {"label": "3pm", "probability": 20},
                {"label": "4pm", "probability": 70},
            ],
        )
        self.assertEqual(advice["headline"], "Take an umbrella")
        self.assertEqual(advice["tone"], "wet")
        self.assertIn("4pm", advice["detail"])

    def test_weather_payload_contains_no_coordinates(self):
        payload = server.WEATHER_PROVIDER._normalise(
            {
                "current": {
                    "time": "2026-09-03T12:15",
                    "temperature_2m": 17.2,
                    "apparent_temperature": 16.8,
                    "precipitation": 0,
                    "weather_code": 1,
                    "is_day": 1,
                    "wind_speed_10m": 12,
                },
                "hourly": {
                    "time": ["2026-09-03T12:00", "2026-09-03T13:00"],
                    "precipitation_probability": [10, 15],
                    "precipitation": [0, 0],
                },
                "daily": {
                    "temperature_2m_max": [19],
                    "temperature_2m_min": [11],
                    "precipitation_probability_max": [15],
                },
            },
            "Test town",
        )
        self.assertNotIn("latitude", payload)
        self.assertNotIn("longitude", payload)
        self.assertEqual(payload["location"], "Test town")
        self.assertEqual(payload["rain"]["tone"], "dry")


if __name__ == "__main__":
    unittest.main()
