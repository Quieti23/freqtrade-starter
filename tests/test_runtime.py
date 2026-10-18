"""Opt-in tests against running starter services, never a real exchange account."""

import base64
import json
import os
from pathlib import Path
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile


PROJECT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.getenv("STARTER_RUNTIME_TESTS") == "1", "requires running starter services")
class RuntimeTests(unittest.TestCase):
    def test_authenticated_api_rejects_bad_login_and_reports_dry_run(self):
        modes = os.getenv("STARTER_TEST_MODES", "backtest,paper").split(",")
        for mode in modes:
            with self.subTest(mode=mode):
                config = json.loads((PROJECT / f"runtime/config.{mode}.json").read_text())
                port = os.getenv("PAPER_PORT", "18080") if mode == "paper" else os.getenv("BACKTEST_PORT", "18085")
                base = f"http://127.0.0.1:{port}/api/v1"
                bad = base64.b64encode(b"invalid:invalid").decode()
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(f"{base}/token/login", data=b"", headers={
                        "Authorization": f"Basic {bad}",
                    }), timeout=10)
                self.assertEqual(caught.exception.code, 401)
                api = config["api_server"]
                good = base64.b64encode(f"{api['username']}:{api['password']}".encode()).decode()
                with urlopen(Request(f"{base}/token/login", data=b"", headers={
                    "Authorization": f"Basic {good}",
                }), timeout=10) as response:
                    token = json.load(response)["access_token"]
                with urlopen(Request(f"{base}/show_config", headers={
                    "Authorization": f"Bearer {token}",
                }), timeout=10) as response:
                    effective = json.load(response)
                self.assertIs(effective["dry_run"], True)
                if mode == "paper":
                    self.assertEqual(effective["state"], "running")
                    self.assertTrue((PROJECT / "runtime/trades.paper.sqlite").exists())

    def test_backtest_results_persist_and_contain_strategy_trades(self):
        results = sorted((PROJECT / "runtime/backtest_results").glob("*.zip"))
        self.assertTrue(results, "Run the demo before runtime tests.")
        with zipfile.ZipFile(results[-1]) as archive:
            payloads = [name for name in archive.namelist() if name.endswith(".json") and
                        not name.endswith((".meta.json", "_config.json"))]
            results_json = [json.loads(archive.read(name)) for name in payloads]
        result = next(value for value in results_json if "strategy" in value)
        stats = result["strategy"]["StarterStrategy"]
        self.assertGreater(stats["total_trades"], 0)
        self.assertGreater(len(stats["trades"]), 0)


if __name__ == "__main__":
    unittest.main()
