# Freqtrade Starter

[简体中文](README.md) | [English](README.en.md)

A Docker starter kit for setting up a quantitative research environment: **initialize configuration, download public market data, run a sample backtest, and access FreqUI with one command. Enable paper trading and the market gateway when needed.**

> This project is for learning and validating the toolchain, not investment advice or a promise of returns. The demonstration strategy has not been validated for profitability. Supported launch commands enforce `dry_run=true`; real-money trading is not supported and exchange API keys are not required.

## Features and scope

| Feature | Enabled by default | Notes |
| --- | --- | --- |
| Backtesting web interface | Yes | FreqUI bundled in the official image; no separate frontend deployment |
| Initial data download and sample backtest | Yes | Last 30 complete UTC days, plus one day of warmup data |
| Paper trading | No | `paper` or `both` mode; a virtual wallet of 1,000 USDT |
| Market gateway | No | Caches Binance futures candles and provides market health information |
| Redis | No | Optional with the gateway; persists recent candles |
| GPU, FreqAI, personal research strategies | Not included | No GPU requirement, personal models, or private strategies |

The verified scope is **Binance USDT futures, 5m, StarterStrategy, CPU, and Linux x86_64 containers**. The demo is long-only, with a virtual stake of 200 USDT per trade to meet BTC quantity precision and minimum order requirements at the time of validation. You can change pairs and the virtual stake, but must check exchange constraints yourself. Do not disable authentication or dry-run mode to troubleshoot.

## Prerequisites

- Windows: install Docker Desktop, select WSL2 / Linux containers, and start Docker.
- Linux: install Docker Engine and the Docker Compose plugin.
- Docker Compose **2.20 or newer**.
- Recommended Docker allocation: 2 CPU cores, 4 GB RAM, and several GB of disk space.
- Network access to Docker Hub, Binance spot market metadata, futures REST endpoints, and WebSocket streams.
- No host installation of Python, Node.js, or CUDA is required for normal use.

“One command” refers to project setup **after Docker is installed**. The launchers do not silently install system software, change system execution policies, configure proxies, or bypass regional restrictions.

Official installation sources: [Docker Desktop for Windows][docker-windows], [Docker Engine for Linux][docker-linux], and [Docker Compose plugin installation][docker-compose-install]. The upstream container workflow is described in [Freqtrade Docker Quickstart][ft-docker]. This project adds its own initialization and verification workflow; it is not an official Freqtrade deployment script.

Download and extract the repository ZIP, or clone the repository. Run all commands below from the repository root.

## Windows quick start

```powershell
# Default: backtesting UI, data download, and first backtest
.\start.ps1

# Backtesting and paper trading
.\start.ps1 -Mode both

# Also enable the market gateway and Redis
.\start.ps1 -Mode both -Gateway -Redis
```

If Windows blocks a downloaded script, inspect it first, then unblock that file according to your organization's policy. This project does not require globally relaxing the PowerShell execution policy.

## Linux quick start

```sh
sh start.sh
sh start.sh start --mode both
sh start.sh start --mode both --gateway --redis
```

The launcher writes runtime files using the current Linux user's UID/GID to avoid root-owned configuration. The base image has one compatibility adjustment: allowing a non-default UID to traverse the upstream user directory containing Python dependencies. No extra trading dependencies are installed. Do not alternate users when starting the same directory. Windows with Docker Linux containers has been validated locally; the native Linux launcher is checked in CI. Confirm GitHub Actions passes before publishing a release.

## Sign in and view results

| Mode | Default URL | Local credentials |
| --- | --- | --- |
| Backtesting | http://127.0.0.1:18085 | `api_server` in [runtime/config.backtest.json](runtime/config.backtest.json) |
| Paper trading | http://127.0.0.1:18080 | `api_server` in [runtime/config.paper.json](runtime/config.paper.json) |
| Optional gateway | http://127.0.0.1:19000/health | Local access only; no account system |

Open the UI, click **Login**, and enter a Bot Name, the current API URL, and the configured `username` and `password`. In the backtesting instance, open Backtesting to load historical results. Use the paper-trading instance to monitor simulated orders and trading state. These are separate instances with different passwords.

The first run generates random passwords, JWT secrets, and WebSocket tokens. Credentials stay on your machine; the launcher does not print passwords or commit them to Git.

Upstream feature and security sources: [FreqUI, including login and web backtesting][ft-ui], and [REST API, including authentication, Docker port mappings, and remote-access warnings][ft-api]. This project's port numbers, credential generation, and two-instance layout are local implementation choices.

Backtest results are saved in [runtime/backtest_results](runtime/backtest_results), the paper-trading database in [runtime/trades.paper.sqlite](runtime/trades.paper.sqlite), and logs in [runtime/logs](runtime/logs). A successful backtest verifies that the toolchain can simulate trades; **it does not establish profitability**.

## Common operations

| Operation | Windows | Linux |
| --- | --- | --- |
| Initialize without starting services | `.\start.ps1 -Action init` | `sh start.sh init` |
| Start paper trading only | `.\start.ps1 -Mode paper` | `sh start.sh start --mode paper` |
| Start without automatically backtesting | `.\start.ps1 -Mode both -SkipDemo` | `sh start.sh start --mode both --skip-demo` |
| Run a sample backtest for the last 7 days | `.\start.ps1 -Action demo -Days 7` | `sh start.sh demo --days 7` |
| Check configuration and strategy loading | `.\start.ps1 -Action check` | `sh start.sh check` |
| Show status | `.\start.ps1 -Action status` | `sh start.sh status` |
| Stop without deleting data | `.\start.ps1 -Action stop` | `sh start.sh stop` |

Initialize before running `check` or `demo`. These actions do not change existing gateway routing. If the saved configuration uses the gateway, start that gateway first. The launcher does not allow Redis without the gateway.

Every `start` first stops old services **within this Compose project**, then starts the selected mode and reapplies routing. It does not stop other Compose projects. Pass the gateway options on every start if you want to keep using it. Reinitialization preserves existing credentials, virtual stake settings, databases, and backtest records. **Do not use `init` to change routing while services are running; use `start` instead.**

### Change ports

Copy [.env.example](.env.example) to `.env`, change the ports, and restart. Published ports always bind to `127.0.0.1`; Redis has no host port mapping. The launcher prints the actual service ports after a successful start.

For a remote server, use an SSH tunnel to access the loopback ports. Do not expose the trading API or gateway directly to the internet. Public deployment requires additional HTTPS, access controls, and operational design beyond the scope of this local starter kit.

### Health checks and troubleshooting

Startup checks Redis when enabled, gateway upstream connectivity when enabled, service health, authentication, effective dry-run configuration, the running paper-trading loop, and FreqUI HTML. The default backtest also requires a new result archive containing at least one executed trade.

Failures return a nonzero exit code. Already-started services and diagnostic data are not automatically removed. Inspect them with:

```sh
docker compose --profile "*" ps --all
docker compose logs --tail 100 backtest trader market_gateway market_redis
```

Common causes:

- Docker is stopped, Windows containers are selected, or Compose is too old.
- Port conflict: select different ports in `.env`.
- Binance timeout, regional restriction, or rate limiting: check legally available connectivity and the official service status. The gateway does not solve regional restrictions.
- `No trades were executed`: check `stake_amount` against minimum order quantity/notional, then inspect history and strategy signals. You can also increase `Days`. Zero trades do not count as a verified execution workflow.
- Native Linux permission errors: check that the runtime directory belongs to the launching user. Do not recursively change permissions on system directories.
- Missing results in the UI: confirm you signed in to the backtesting instance, the demo completed, and the historical results list has been refreshed.

## Configuration and extension boundaries

- [templates/config.json](templates/config.json): initial configuration without secrets.
- [templates/safety.json](templates/safety.json): a final-layer safety configuration used by supported commands; enforces dry-run mode, empty exchange credentials, and disabled Telegram.
- [scripts/bootstrap.py](scripts/bootstrap.py): configuration generation, readiness checks, data download, and backtesting.
- [strategies/StarterStrategy.py](strategies/StarterStrategy.py): an original EMA-cross demonstration strategy without future-data references. Backtest profitability is not a deployment acceptance criterion.
- [market_gateway](market_gateway): reused from the maintainer's working directory, with changes to its build and deployment setup.

The gateway only redirects CCXT's `fapiPublic` route, covering futures v1 public market data. Other endpoints still connect directly to Binance; this is not a full transparent proxy. Redis stores recent gateway candles, not the historical backtest files on disk.

See [Freqtrade Data Downloading][ft-data] and [Backtesting][ft-backtest] for upstream command options, and [Configure the bot][ft-config] for configuration fields and multiple configuration files. Using 30 complete UTC days, adding one warmup day, rejecting zero-trade results, and enforcing paper-only operation are **this project's implementation choices**, not defaults mandated by those upstream documents.

This starter explicitly validates a fixed demonstration strategy and timeframe. Before adding personal strategies, external data, WFO, FreqAI, or GPU support, address dependencies, licensing, configuration, and validation separately.

## Updates and backups

Before updating, stop this project and securely back up the entire `runtime` directory and local `.env`. Both may contain credentials or personal runtime data.

Updates replace repository-managed code and templates, not runtime data. New template fields do not automatically rewrite existing configurations. Review changes and run `check` after upgrading. Base images use fixed versions and digests; changing them is a maintenance operation requiring revalidation, not an automatic move to `latest`.

`stop` does not delete volumes. Do not delete databases or the runtime directory merely to “reinstall.”

## Tests and CI

Configuration and strategy tests without exchange access, from a Linux shell:

```sh
mkdir -p runtime
docker compose run --rm --no-deps -v "$PWD:/opt/project:ro" \
  --entrypoint python tools -m unittest discover -s /opt/project/tests -v
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory runtime -Force | Out-Null
docker compose run --rm --no-deps -v "${PWD}:/opt/project:ro" --entrypoint python tools -m unittest discover -s /opt/project/tests -v
```

By default, these commands skip the two tests requiring running services. After starting `both` mode and completing a demo backtest, run online acceptance tests on a development machine with Python installed:

```powershell
$env:STARTER_RUNTIME_TESTS = "1"
python -m unittest discover -s tests -p test_runtime.py -v
```

```sh
STARTER_RUNTIME_TESTS=1 python3 -m unittest discover -s tests -p test_runtime.py -v
```

Online tests verify rejection of incorrect passwords, authenticated dry-run configuration, a running trading loop, and executed trades in the persisted backtest archive. If you change ports, also set `BACKTEST_PORT` / `PAPER_PORT` in the test process environment. Python tests do not automatically load `.env`.

[GitHub Actions](.github/workflows/validate.yaml) checks Compose, shell syntax, initialization, strategy signals, official configuration validation, and the gateway image build by default. Real public-data download and backtesting can be enabled manually through the `online` input of `workflow_dispatch`. Exchange reachability on hosted CI can differ from your local environment; an online failure must not be reported as success.

## Official documentation and sources

The following links point to documentation maintained by the respective upstream projects. They explain upstream capabilities and parameters; **they do not imply endorsement of this starter kit or its demo strategy**. Last consulted: 2026-10-18. Freqtrade's `stable` documentation changes with upstream releases, while this project pins its base image to **2026.1 plus a digest**. If the documentation differs from the running version, consult `freqtrade <command> --help` in the pinned image and this repository's actual configuration.

| Topic | Official source | Relevance to this project |
| --- | --- | --- |
| Windows container environment | [Docker — Install Docker Desktop on Windows][docker-windows] | WSL2 / Linux containers installation and system requirements |
| Linux container environment | [Docker — Install Docker Engine][docker-linux]; [Install the Compose plugin][docker-compose-install] | Docker Engine and Compose installation |
| Freqtrade container setup | [Freqtrade — Using Freqtrade with Docker][ft-docker] | Official image, user directory, configuration, and UI basics |
| Configuration and paper-trading fields | [Freqtrade — Configure the bot][ft-config] | `dry_run`, virtual wallet, stake, exchange configuration, and config merging; see the [template](templates/config.json) |
| Historical market data | [Freqtrade — Data Downloading][ft-data] | `download-data`, pairs, timeframes, and timeranges invoked by [bootstrap.py](scripts/bootstrap.py) |
| Backtesting and exports | [Freqtrade — Backtesting][ft-backtest] | `backtesting`, warmup history, timeranges, cache, and export options |
| Web interface | [Freqtrade — FreqUI][ft-ui] | Login, webserver backtesting, and historical result viewing |
| API and access security | [Freqtrade — REST API][ft-api] | Authentication, JWT, loopback port mappings, and SSH/VPN access recommendations |
| Optional services | [Docker — Using profiles with Compose][docker-profiles] | `research`, `paper`, `gateway`, `redis`, and `tools` profiles in [compose.yaml](compose.yaml) |
| Environment variables and port substitution | [Docker — Interpolation][docker-interpolation] | [.env.example](.env.example) and Compose variable substitution; not automatic `.env` loading in Python tests |

The market gateway, Redis integration, `start.ps1` / `start.sh`, `StarterStrategy`, and initialization/acceptance logic belong to this project. Their behavior is defined by this repository's source and tests, not by the Freqtrade official documentation. For third-party licensing sources, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License and provenance

This project's own code is provided under the [MIT License](LICENSE). The maintainer authorized publication of the reused market gateway; the demonstration strategy and startup logic were newly written for this project.

Freqtrade, bundled FreqUI, Redis, Python, and dependencies retain their respective upstream licenses. This project's MIT license does not replace those licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

[docker-windows]: https://docs.docker.com/desktop/setup/install/windows-install/
[docker-linux]: https://docs.docker.com/engine/install/
[docker-compose-install]: https://docs.docker.com/compose/install/linux/
[docker-profiles]: https://docs.docker.com/compose/how-tos/profiles/
[docker-interpolation]: https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/
[ft-docker]: https://www.freqtrade.io/en/stable/docker_quickstart/
[ft-config]: https://www.freqtrade.io/en/stable/configuration/
[ft-data]: https://www.freqtrade.io/en/stable/data-download/
[ft-backtest]: https://www.freqtrade.io/en/stable/backtesting/
[ft-ui]: https://www.freqtrade.io/en/stable/freq-ui/
[ft-api]: https://www.freqtrade.io/en/stable/rest-api/
