# Freqtrade Starter

[简体中文](README.md) | [English](README.en.md)

面向初次搭建量化研究环境的 Docker 启动套件：**一条命令初始化、下载公开行情、完成示例回测，并打开 FreqUI；模拟交易与行情网关按需启用。**

> 本项目用于学习和验证工具链，不构成投资建议，不承诺收益。演示策略并不是经过盈利验证的交易策略。发布版强制 `dry_run=true`，不支持真实资金交易，也不需要交易所 API 密钥。

## 功能范围

| 功能 | 默认启用 | 说明 |
| --- | --- | --- |
| 回测 Web 界面 | 是 | 官方镜像内置 FreqUI，不额外部署前端 |
| 首次数据下载与示例回测 | 是 | 最近 30 个完整 UTC 日，另下载 1 日预热数据 |
| 模拟交易 | 否 | `paper` 或 `both` 模式，虚拟钱包 1000 USDT |
| 行情网关 | 否 | 可缓存 Binance 合约 K 线、提供行情健康信息 |
| Redis | 否 | 与网关一起启用，用于持久化最近的 K 线 |
| GPU、FreqAI、个人研究策略 | 不包含 | 基础版不依赖 GPU，不打包个人模型或策略 |

当前验证范围为 **Binance USDT 合约、5m、StarterStrategy、CPU、Linux x86_64 容器**。演示策略只做多，默认每笔虚拟 stake 为 200 USDT，以满足当前 BTC 数量精度与最小金额要求。支持修改交易对和虚拟 stake，但需自行验证交易所约束；不通过删除认证或关闭模拟模式来排错。

## 环境准备

- Windows：安装 Docker Desktop，使用 WSL2 / Linux containers，启动 Docker。
- Linux：安装 Docker Engine 与 Docker Compose 插件。
- Docker Compose **2.20 或更新版本**。
- 建议为 Docker 预留 2 核 CPU、4 GB 内存及数 GB 磁盘空间。
- 网络需要允许访问 Docker Hub，以及 Binance 的现货市场元数据、合约 REST 与 WebSocket 接口。
- 用户主机不需要安装 Python、Node.js 或 CUDA。

这里的“一键”指 Docker 安装完成后的项目初始化。脚本不会静默安装系统软件、修改系统执行策略、配置代理或绕过地区限制。

安装出处：[Docker Desktop for Windows][docker-windows]、[Docker Engine for Linux][docker-linux]、[Docker Compose 插件安装][docker-compose-install]。Freqtrade 官方的基础容器流程见 [Docker Quickstart][ft-docker]；本项目在此基础上增加了自动初始化与验收流程，并不是官方部署脚本。

下载本仓库 ZIP 并解压，或者克隆仓库。以下命令均在本仓库根目录执行。

## Windows 快速开始

```powershell
# 默认：回测界面 + 下载行情 + 首次回测
.\start.ps1

# 回测 + 模拟交易
.\start.ps1 -Mode both

# 再加上行情网关和 Redis
.\start.ps1 -Mode both -Gateway -Redis
```

如果 Windows 阻止运行已下载脚本，先检查脚本内容，再按组织策略解锁该文件；本项目不要求全局放宽 PowerShell 执行策略。

## Linux 快速开始

```sh
sh start.sh
sh start.sh start --mode both
sh start.sh start --mode both --gateway --redis
```

脚本使用当前 Linux 用户的 UID/GID 写入运行文件，避免默认生成 root 所有的用户配置。基础镜像只做一项兼容性调整：允许非默认 UID 遍历上游 Python 依赖所在的用户目录；不安装额外交易依赖。不要使用不同用户交替启动同一目录。当前交付在 Windows + Docker Linux 容器上验证；原生 Linux 启动脚本由 CI 验证，发布前应确认 GitHub Actions 通过。

## 登录和查看结果

| 模式 | 默认访问地址 | 本地凭据 |
| --- | --- | --- |
| 回测 | http://127.0.0.1:18085 | [runtime/config.backtest.json](runtime/config.backtest.json) 的 `api_server` |
| 模拟交易 | http://127.0.0.1:18080 | [runtime/config.paper.json](runtime/config.paper.json) 的 `api_server` |
| 可选网关 | http://127.0.0.1:19000/health | 仅本机访问，不提供账号体系 |

打开界面，点击 **Login**，填写 Bot Name、当前访问地址、配置中的 `username` 与 `password`。回测界面登录后可进入 Backtesting，查看历史回测结果；模拟交易界面用于查看模拟订单与交易状态。它们是两个独立实例，使用不同密码。

首次运行自动生成随机密码、JWT 密钥与 WebSocket token。凭据只保存在本机，脚本不输出密码，也不把它们提交到 Git。

上游功能与安全说明出处：[FreqUI（登录与回测界面）][ft-ui]、[REST API（认证、Docker 端口映射及远程访问警告）][ft-api]。本项目的端口号、随机凭据生成方式和双实例布局属于本地封装。

回测结果保存在 [runtime/backtest_results](runtime/backtest_results)，模拟交易数据库保存在 [runtime/trades.paper.sqlite](runtime/trades.paper.sqlite)，日志保存在 [runtime/logs](runtime/logs)。回测成功意味着工具链能完成交易模拟，**不意味着策略有收益**。

## 常用操作

| 操作 | Windows | Linux |
| --- | --- | --- |
| 仅初始化，不启动 | `.\start.ps1 -Action init` | `sh start.sh init` |
| 只开模拟交易 | `.\start.ps1 -Mode paper` | `sh start.sh start --mode paper` |
| 启动但跳过自动回测 | `.\start.ps1 -Mode both -SkipDemo` | `sh start.sh start --mode both --skip-demo` |
| 只执行最近 7 日示例回测 | `.\start.ps1 -Action demo -Days 7` | `sh start.sh demo --days 7` |
| 配置与策略加载检查 | `.\start.ps1 -Action check` | `sh start.sh check` |
| 查看状态 | `.\start.ps1 -Action status` | `sh start.sh status` |
| 停止项目，不删除数据 | `.\start.ps1 -Action stop` | `sh start.sh stop` |

`check` 和 `demo` 需要先完成初始化；它们不会改变已有网关路由。使用网关路由时，需先启动相应网关。`Redis` 不能脱离网关单独通过启动脚本启用。

每次 `start` 会先停止**本 Compose 项目内**的旧服务，再按本次指定的模式启动，并重新应用路由；不会停止其他 Compose 项目。要继续使用网关，每次启动都传入网关参数。重复初始化不会覆盖已有账号、虚拟 stake、交易数据库或回测记录。**不要在服务运行中执行 `init` 修改路由；使用 `start` 完成切换。**

### 修改端口

复制 [.env.example](.env.example) 为 `.env`，修改端口后重新启动。端口始终绑定 `127.0.0.1`，Redis 不发布到主机。脚本成功后会显示实际服务端口。

远程服务器建议通过 SSH 隧道访问这些本机端口。不要直接把交易 API 或网关暴露到公网；公网部署需要额外的 HTTPS、访问控制和运维设计，不属于这个本地启动套件。

### 健康检查与失败处理

启动流程依次检查 Redis（如启用）、网关上游连通性（如启用）、服务健康、登录认证、有效配置中的模拟模式、模拟交易循环状态及 FreqUI HTML。默认回测还检查新结果归档与非零成交数。

失败时脚本返回非零退出码；已启动服务和诊断数据不会自动删除，可以检查：

```sh
docker compose --profile "*" ps --all
docker compose logs --tail 100 backtest trader market_gateway market_redis
```

常见原因：

- Docker 未启动、不是 Linux 容器模式，或 Compose 版本过旧。
- 端口已被占用：通过 `.env` 调整。
- Binance 访问超时、地区限制或限流：检查合规可用的网络和官方服务状态。网关不是地区限制的解决办法。
- 提示 `No trades were executed`：检查 `stake_amount` 是否满足交易所最小数量/金额，再检查行情与策略；也可扩大 `Days`。不要把零成交视为执行链路已验证。
- 原生 Linux 提示权限错误：确认运行目录归当前启动用户所有，不要对系统目录执行递归权限修改。
- 界面看不到结果：确认登录的是回测实例，示例回测已完成；刷新 Backtesting 的历史结果列表。

## 配置与扩展边界

- [templates/config.json](templates/config.json)：无密钥的初始模板。
- [templates/safety.json](templates/safety.json)：所有受支持命令最后应用的安全约束之一，强制模拟、空交易所密钥并关闭 Telegram。
- [scripts/bootstrap.py](scripts/bootstrap.py)：配置生成、就绪验证、数据下载与回测。
- [strategies/StarterStrategy.py](strategies/StarterStrategy.py)：原创 EMA 交叉演示策略，不使用未来数据，也不以回测收益作为部署验收标准。
- [market_gateway](market_gateway)：从原工作目录复用的行情网关；仅改动构建和部署方式。

当前网关只接管 CCXT 的 `fapiPublic`（合约 v1 公共行情）路由，其余端点仍直连 Binance；它不是全量透明代理。Redis 用于保存网关最近 K 线，不代替磁盘上的历史回测数据。

下载参数和回测参数分别参考 [Freqtrade Data Downloading][ft-data] 与 [Backtesting][ft-backtest]；配置字段及多配置文件规则参考 [Configure the bot][ft-config]。最近 30 个完整 UTC 日、额外 1 日预热、非零成交验收，以及强制模拟交易限制，均是本项目的实现选择，不是这些上游文档要求的默认行为。

基础版明确验证固定演示策略与周期。引入个人策略、外部数据、WFO、FreqAI 或 GPU 前，应单独补齐依赖、授权、配置和验证。

## 更新与备份

更新前停止本项目，并把整个 `runtime` 目录和本地 `.env` 备份到安全位置；两者都可能包含凭据或个人运行数据。

更新只替换仓库管理的代码和模板，不覆盖运行数据。模板的新增字段不会自动改写已有个人配置，升级时应阅读变更并重新执行 `check`。基础镜像使用固定版本和摘要；升级镜像属于维护操作，需要重新验证，而不是自动追随 `latest`。

`stop` 不使用删除卷选项。不要为了“重装”直接删除数据库和运行目录。

## 测试与 CI

不依赖交易所的配置/策略测试（Linux Shell）：

```sh
mkdir -p runtime
docker compose run --rm --no-deps -v "$PWD:/opt/project:ro" \
  --entrypoint python tools -m unittest discover -s /opt/project/tests -v
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory runtime -Force | Out-Null
docker compose run --rm --no-deps -v "${PWD}:/opt/project:ro" --entrypoint python tools -m unittest discover -s /opt/project/tests -v
```

该命令默认跳过需要运行服务的两项测试。完成 `both` 模式和示例回测后，可在装有 Python 的开发机运行在线验收：

```powershell
$env:STARTER_RUNTIME_TESTS = "1"
python -m unittest discover -s tests -p test_runtime.py -v
```

```sh
STARTER_RUNTIME_TESTS=1 python3 -m unittest discover -s tests -p test_runtime.py -v
```

在线测试检查错误密码被拒绝、登录后强制模拟、交易循环运行，以及回测归档中确实包含成交记录。若修改端口，测试进程也需设置对应的 `BACKTEST_PORT` / `PAPER_PORT` 环境变量（Python 测试不会自动读取 `.env`）。

[GitHub Actions](.github/workflows/validate.yaml) 默认验证 Compose、Shell、配置初始化、策略信号、官方配置和网关镜像构建；真实数据下载回测通过 `workflow_dispatch` 的 `online` 选项手动启用。公共 CI 的交易所可达性可能与本地不同，在线失败不能伪装成通过。

## 官方文档与出处

以下链接均指向相应项目维护的官方文档，用于说明上游能力与参数；**不表示上游对本启动套件或演示策略的背书**。链接查阅日期：2026-10-18。Freqtrade 的 `stable` 文档会随上游版本变化，而本项目基础镜像固定为 **2026.1 + 摘要**；如文档与运行版本有差异，以固定镜像内的 `freqtrade <command> --help` 及本项目实际配置为准。

| 主题 | 官方出处 | 本项目对应位置或用途 |
| --- | --- | --- |
| Windows 容器环境 | [Docker — Install Docker Desktop on Windows][docker-windows] | WSL2 / Linux containers 的安装与系统要求 |
| Linux 容器环境 | [Docker — Install Docker Engine][docker-linux]；[Install the Compose plugin][docker-compose-install] | Docker Engine 与 Compose 的安装 |
| Freqtrade 容器入门 | [Freqtrade — Using Freqtrade with Docker][ft-docker] | 官方镜像、用户目录、配置与界面的基础工作方式 |
| 配置与模拟交易字段 | [Freqtrade — Configure the bot][ft-config] | `dry_run`、虚拟钱包、stake、交易所及配置合并；参见 [配置模板](templates/config.json) |
| 下载历史行情 | [Freqtrade — Data Downloading][ft-data] | `download-data`、交易对、时间周期和时间范围；由 [bootstrap.py](scripts/bootstrap.py) 调用 |
| 回测与结果导出 | [Freqtrade — Backtesting][ft-backtest] | `backtesting`、预热历史、时间范围、缓存和导出选项 |
| Web 界面 | [Freqtrade — FreqUI][ft-ui] | 登录、webserver 回测与历史结果查看 |
| API 与访问安全 | [Freqtrade — REST API][ft-api] | API 认证、JWT、回环端口映射与 SSH/VPN 访问建议 |
| 可选服务 | [Docker — Using profiles with Compose][docker-profiles] | [compose.yaml](compose.yaml) 中的 `research`、`paper`、`gateway`、`redis` 与 `tools` profiles |
| 环境变量与端口替换 | [Docker — Interpolation][docker-interpolation] | [.env.example](.env.example) 与 Compose 变量替换；不等同于 Python 测试自动加载 `.env` |

行情网关、Redis 缓存整合、`start.ps1` / `start.sh`、`StarterStrategy` 和初始化/验收逻辑属于本项目；其行为以本仓库源码和测试为依据，不应当作 Freqtrade 官方功能说明引用。第三方软件许可出处另见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 许可和来源

本项目自有代码采用 [MIT License](LICENSE)。行情网关来自项目维护者授权公开的原工作目录，演示策略及启动逻辑为本项目新编写。

Freqtrade、内置 FreqUI、Redis、Python 和依赖库由各自上游提供，保留各自许可证；本项目的 MIT 许可不替换这些第三方许可证。参见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

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
