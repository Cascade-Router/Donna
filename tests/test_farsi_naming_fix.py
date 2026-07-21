"""Unit tests for the roadmap-deployed farsi_naming_fix plugin."""

from __future__ import annotations

import time
import unittest

from donna.tools.broker import IntentBroker, get_broker, reload_broker_registry
from donna.tools.plugins.farsi_naming_fix import farsi_naming_fix, handle_tool_call
from donna.tools.schema import ToolCall


class FarsiNamingFixTests(unittest.TestCase):
    def test_amirhosein_persian_spacing(self) -> None:
        t0 = time.perf_counter()
        result = farsi_naming_fix("امیر حسین و نارگِس آمدند")
        ms = (time.perf_counter() - t0) * 1000.0
        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        self.assertIn("Amirhosein", result["text"])
        self.assertIn("Narges", result["text"])
        self.assertNotIn("امیر", result["text"])
        self.assertLess(ms, 50.0, f"latency too high: {ms:.2f} ms")
        # Expose for Compilation Report consumers.
        type(self).last_latency_ms = ms  # type: ignore[attr-defined]

    def test_english_mangling(self) -> None:
        result = farsi_naming_fix("Amir Hosein and Narius arrived")
        self.assertEqual(result["text"], "Amirhosein and Narges arrived")

    def test_dedup_after_repair(self) -> None:
        result = farsi_naming_fix("Amirhosein and Amirhosein")
        self.assertEqual(result["text"], "Amirhosein")

    def test_sanitize_control_chars(self) -> None:
        result = farsi_naming_fix("Narges\x00\x01 hello")
        self.assertEqual(result["text"], "Narges hello")

    def test_empty_input(self) -> None:
        result = farsi_naming_fix("")
        self.assertFalse(result["changed"])
        self.assertEqual(result["text"], "")

    def test_broker_dispatch_plugin(self) -> None:
        reload_broker_registry()
        broker = get_broker()
        self.assertIn("farsi_naming_fix", broker.registry)
        call = ToolCall(
            tool_id="farsi_naming_fix",
            arguments={"text": "امیرحسین"},
            source_lang="fa",
        )
        # No agent.py handlers — plugin path must resolve inside broker.dispatch.
        obs = broker.dispatch(call, handlers={})
        self.assertIsInstance(obs, str)
        self.assertTrue(obs.startswith("OK: farsi_naming_fix"))
        self.assertIn("Amirhosein", obs)

    def test_handle_missing_text(self) -> None:
        obs = handle_tool_call(ToolCall(tool_id="farsi_naming_fix", arguments={}))
        self.assertEqual(obs, "ERROR: missing text")

    def test_alias_parse(self) -> None:
        broker = IntentBroker()
        parsed = broker.parse_utterance("please fix farsi names in this line")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.tool_id, "farsi_naming_fix")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FarsiNamingFixTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    latency = getattr(FarsiNamingFixTests, "last_latency_ms", None)
    if latency is not None:
        print(f"\n[METRICS] farsi_naming_fix core latency: {latency:.3f} ms")
    raise SystemExit(0 if result.wasSuccessful() else 1)
