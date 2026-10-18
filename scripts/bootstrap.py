"""Container-side configuration, readiness and demonstration helpers."""

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile


ROOT = Path("/freqtrade/user_data")
TEMPLATE = Path("/opt/starter/templates/config.json")
SAFETY = "/opt/starter/templates/safety.json"


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def validate_config(config: dict) -> None:
    if config.get("dry_run") is not True:
        raise ValueError("Only dry_run=true is supported. Real trading is intentionally disabled.")
    exchange = config["exchange"]
    if exchange.get("key") or exchange.get("secret"):
        raise ValueError("Remove exchange credentials: this starter uses public data only.")
    if exchange["name"] != "binance" or config.get("trading_mode") != "futures":
        raise ValueError("This release supports Binance USDT futures only.")
    if config.get("timeframe") != "5m" or config.get("strategy") != "StarterStrategy":
        raise ValueError("The verified demo requires StarterStrategy at 5m.")
    if not exchange.get("pair_whitelist"):
        raise ValueError("At least one exchange.pair_whitelist entry is required.")
    for name in ("ccxt_config", "ccxt_async_config"):
        if "urls" in exchange.get(name, {}):
            raise ValueError("Configure gateway routing with the launcher, not base config URLs.")
    api = config["api_server"]
    if not all(api.get(key) for key in ("username", "password", "jwt_secret_key", "ws_token")):
        raise ValueError("API authentication fields must be nonempty.")


def initialize(root: Path, template: Path, gateway: bool, use_redis: bool) -> None:
    if use_redis and not gateway:
        raise ValueError("Redis requires the optional gateway.")
    root.mkdir(parents=True, exist_ok=True)
    existing = {}
    for mode in ("backtest", "paper"):
        path = root / f"config.{mode}.json"
        if path.exists():
            existing[mode] = json.loads(path.read_text(encoding="utf-8"))
            validate_config(existing[mode])
    for folder in ("logs", "data", "backtest_results"):
        (root / folder).mkdir(exist_ok=True)
    for mode in ("backtest", "paper"):
        if mode in existing:
            continue
        config = json.loads(template.read_text(encoding="utf-8"))
        config["bot_name"] = f"starter-{mode}"
        config["api_server"].update(
            password=secrets.token_urlsafe(24),
            jwt_secret_key=secrets.token_urlsafe(48),
            ws_token=secrets.token_urlsafe(32),
        )
        validate_config(config)
        save_json(root / f"config.{mode}.json", config)
    upstream = "http://market_gateway:9000/fapi/v1" if gateway else "https://fapi.binance.com/fapi/v1"
    route = {"urls": {"api": {"fapiPublic": upstream}}}
    save_json(root / "config.route.json", {
        "exchange": {"ccxt_config": route, "ccxt_async_config": route},
    })
    print("Configuration ready. Existing credentials and databases were preserved.")


def config_args(mode: str) -> list[str]:
    return [
        "--config", str(ROOT / f"config.{mode}.json"),
        "--config", SAFETY,
        "--config", str(ROOT / "config.route.json"),
    ]


def run_freqtrade(arguments: list[str]) -> None:
    subprocess.run(["freqtrade", *arguments], check=True)


def demo(days: int) -> None:
    config = json.loads((ROOT / "config.backtest.json").read_text(encoding="utf-8"))
    validate_config(config)
    # Include complete warmup days, but backtest only complete UTC days.
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    download_range = f"{(start - timedelta(days=1)):%Y%m%d}-{end:%Y%m%d}"
    test_range = f"{start:%Y%m%d}-{end:%Y%m%d}"
    run_freqtrade([
        "download-data", *config_args("backtest"),
        "--pairs", *config["exchange"]["pair_whitelist"],
        "--timeframes", "5m", "--trading-mode", "futures",
        "--timerange", download_range,
    ])
    result_dir = ROOT / "backtest_results"
    before = set(result_dir.glob("*.zip"))
    run_freqtrade([
        "backtesting", *config_args("backtest"), "--strategy", "StarterStrategy",
        "--timerange", test_range, "--cache", "none",
        "--export", "trades", "--backtest-directory", str(result_dir),
    ])
    results = set(result_dir.glob("*.zip")) - before
    if not results:
        raise RuntimeError("Backtest returned without creating a new result archive.")
    trades = 0
    for path in results:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith(".json") and not name.endswith((".meta.json", "_config.json")):
                    payload = json.loads(archive.read(name))
                    if "strategy" in payload:
                        trades += payload["strategy"]["StarterStrategy"]["total_trades"]
    if trades == 0:
        raise RuntimeError(
            "No trades were executed. Check stake_amount against the exchange minimum "
            "quantity/notional, available history and signal dates; try a longer --days range."
        )
    print(f"Backtest verified: {trades} trades, {len(results)} new archive(s), range {test_range}.")


def request_json(url: str, headers: dict | None = None, post: bool = False) -> dict:
    request = Request(url, headers=headers or {}, data=b"" if post else None)
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def verify_services(mode: str, gateway: bool, use_redis: bool, timeout: int = 180) -> None:
    targets = ["backtest", "trader"] if mode == "both" else [
        "trader" if mode == "paper" else "backtest"
    ]
    deadline = time.monotonic() + timeout
    errors = {}
    while targets or gateway or use_redis:
        for service in list(targets):
            try:
                config_mode = "paper" if service == "trader" else "backtest"
                config = json.loads((ROOT / f"config.{config_mode}.json").read_text())
                api = config["api_server"]
                auth = base64.b64encode(f"{api['username']}:{api['password']}".encode()).decode()
                base = f"http://{service}:8080"
                token = request_json(f"{base}/api/v1/token/login", {
                    "Authorization": f"Basic {auth}",
                }, post=True)["access_token"]
                effective = request_json(f"{base}/api/v1/show_config", {
                    "Authorization": f"Bearer {token}",
                })
                if effective.get("dry_run") is not True:
                    raise RuntimeError(f"{service} is not in dry-run mode.")
                if service == "trader" and effective.get("state") != "running":
                    raise ValueError("Trader API is up but the trading loop is not running yet.")
                with urlopen(f"{base}/", timeout=10) as response:
                    if "text/html" not in response.headers.get("Content-Type", ""):
                        raise ValueError(f"{service}: bundled FreqUI is not available.")
                targets.remove(service)
                print(f"Verified {service}: authenticated API, dry-run mode and FreqUI.")
            except (HTTPError, URLError, TimeoutError, ConnectionError, ValueError, KeyError) as error:
                errors[service] = str(error)
        if gateway:
            try:
                request_json("http://market_gateway:9000/upstream/health")
                gateway = False
                print("Verified gateway upstream connectivity.")
            except (HTTPError, URLError, TimeoutError, ConnectionError, ValueError) as error:
                errors["gateway"] = str(error)
        if use_redis:
            import socket
            try:
                with socket.create_connection(("market_redis", 6379), timeout=5) as connection:
                    connection.sendall(b"*1\r\n$4\r\nPING\r\n")
                    if connection.recv(64) != b"+PONG\r\n":
                        raise ValueError("Redis did not reply PONG.")
                use_redis = False
                print("Verified Redis PING.")
            except (OSError, ValueError) as error:
                errors["redis"] = str(error)
        if not targets and not gateway and not use_redis:
            return
        if time.monotonic() >= deadline:
            pending = targets + (["gateway"] if gateway else []) + (["redis"] if use_redis else [])
            raise RuntimeError("Readiness timeout: " + "; ".join(
                f"{name}: {errors.get(name, 'not ready')}" for name in pending
            ))
        time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("init", "demo", "verify", "validate"))
    parser.add_argument("--mode", choices=("backtest", "paper", "both"), default="backtest")
    parser.add_argument("--gateway", action="store_true")
    parser.add_argument("--redis", action="store_true")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        parser.error("--days must be between 1 and 365")
    if args.action == "init":
        initialize(ROOT, TEMPLATE, args.gateway, args.redis)
    elif args.action == "demo":
        demo(args.days)
    elif args.action == "verify":
        verify_services(args.mode, args.gateway, args.redis)
    else:
        for mode in ("backtest", "paper"):
            subprocess.run(
                ["freqtrade", "show-config", *config_args(mode)],
                check=True, stdout=subprocess.PIPE,
            )
            print(f"Official configuration validation passed: {mode}.")
        run_freqtrade(["list-strategies", *config_args("backtest")])


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Starter failed: {error}", file=sys.stderr)
        sys.exit(1)
