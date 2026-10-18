import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap", PROJECT / "scripts/bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.template = PROJECT / "templates/config.json"

    def initialize(self, gateway=False, use_redis=False):
        bootstrap.initialize(self.root, self.template, gateway, use_redis)

    def test_reinitialization_preserves_credentials_edits_and_database(self):
        self.initialize()
        config = self.root / "config.paper.json"
        value = json.loads(config.read_text())
        value["stake_amount"] = 25
        config.write_text(json.dumps(value))
        database = self.root / "trades.paper.sqlite"
        database.write_bytes(b"existing user database")
        self.initialize()
        self.assertEqual(json.loads(config.read_text()), value)
        self.assertEqual(database.read_bytes(), b"existing user database")
        other = json.loads((self.root / "config.backtest.json").read_text())
        self.assertNotEqual(value["api_server"]["password"], other["api_server"]["password"])

    def test_routing_can_switch_gateway_on_and_off_without_changing_credentials(self):
        self.initialize()
        config = (self.root / "config.paper.json").read_bytes()
        for enabled in (True, False):
            self.initialize(enabled, enabled)
            route = json.loads((self.root / "config.route.json").read_text())
            for ccxt in ("ccxt_config", "ccxt_async_config"):
                url = route["exchange"][ccxt]["urls"]["api"]["fapiPublic"]
                self.assertEqual("market_gateway" in url, enabled)
            self.assertEqual((self.root / "config.paper.json").read_bytes(), config)

    def test_reject_unsafe_existing_config_before_creating_any_other_files(self):
        self.initialize()
        paper = self.root / "config.paper.json"
        backtest = self.root / "config.backtest.json"
        route_before = (self.root / "config.route.json").read_bytes()
        value = json.loads(paper.read_text())
        value["dry_run"] = False
        paper.write_text(json.dumps(value))
        backtest.unlink()
        with self.assertRaisesRegex(ValueError, "Real trading"):
            self.initialize(True, False)
        self.assertFalse(backtest.exists())
        self.assertEqual((self.root / "config.route.json").read_bytes(), route_before)

    def test_reject_exchange_secrets_and_empty_authentication(self):
        self.initialize()
        value = json.loads((self.root / "config.paper.json").read_text())
        for location, field in (("exchange", "key"), ("exchange", "secret"), ("api_server", "password")):
            with self.subTest(field=field):
                invalid = copy.deepcopy(value)
                invalid[location][field] = "" if location == "api_server" else "test-value"
                with self.assertRaises(ValueError):
                    bootstrap.validate_config(invalid)

    def test_redis_without_gateway_does_not_write(self):
        root = self.root / "new"
        with self.assertRaisesRegex(ValueError, "Redis requires"):
            bootstrap.initialize(root, self.template, False, True)
        self.assertFalse(root.exists())

    def test_demo_rejects_empty_trade_result_instead_of_reporting_success(self):
        self.initialize()

        def fake_freqtrade(arguments):
            if arguments[0] == "backtesting":
                with zipfile.ZipFile(self.root / "backtest_results/result.zip", "w") as archive:
                    archive.writestr("result.json", json.dumps({
                        "strategy": {"StarterStrategy": {"total_trades": 0}},
                    }))

        with patch.object(bootstrap, "ROOT", self.root), patch.object(
            bootstrap, "run_freqtrade", side_effect=fake_freqtrade,
        ):
            with self.assertRaisesRegex(RuntimeError, "No trades were executed"):
                bootstrap.demo(7)


if __name__ == "__main__":
    unittest.main()
