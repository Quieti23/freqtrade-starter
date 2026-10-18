import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import redis.asyncio as redis
import websockets
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse


LOGGER = logging.getLogger("market_gateway")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

BINANCE_ENV = os.getenv("BINANCE_ENV", "production").strip().lower()
DEFAULT_UPSTREAMS = {
    "production": {
        "rest": "https://fapi.binance.com",
        "ws": "wss://fstream.binance.com/stream",
    },
    "testnet": {
        "rest": "https://testnet.binancefuture.com",
        "ws": "wss://stream.binancefuture.com/stream",
    },
}
DEFAULT_UPSTREAM = DEFAULT_UPSTREAMS.get(BINANCE_ENV, DEFAULT_UPSTREAMS["production"])
UPSTREAM_REST = (os.getenv("BINANCE_FAPI_BASE_URL") or DEFAULT_UPSTREAM["rest"]).rstrip("/")
UPSTREAM_WS = os.getenv("BINANCE_FSTREAM_URL") or DEFAULT_UPSTREAM["ws"]
SYMBOLS = [s.strip().upper() for s in os.getenv("GATEWAY_SYMBOLS", "BTCUSDT").split(",") if s.strip()]
INTERVALS = [s.strip() for s in os.getenv("GATEWAY_INTERVALS", "5m").split(",") if s.strip()]
PREWARM_LIMIT = int(os.getenv("GATEWAY_PREWARM_LIMIT", "500"))
CACHE_MAX_ROWS = int(os.getenv("GATEWAY_CACHE_MAX_ROWS", "1500"))
UPSTREAM_MIN_INTERVAL_MS = int(os.getenv("UPSTREAM_MIN_INTERVAL_MS", "200"))
HTTP_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "15"))
PUBLIC_CACHE_TTL_SECONDS = float(os.getenv("PUBLIC_CACHE_TTL_SECONDS", "1"))
PUBLIC_CACHE_PATHS = {
    path.strip().lstrip("/")
    for path in os.getenv("PUBLIC_CACHE_PATHS", "ticker/bookTicker,ticker/price,premiumIndex").split(",")
    if path.strip()
}
REDIS_URL = os.getenv("REDIS_URL", "")
LIQUIDITY_REFRESH_SECONDS = int(os.getenv("LIQUIDITY_REFRESH_SECONDS", "60"))
ORDERBOOK_LIMIT = int(os.getenv("LIQUIDITY_ORDERBOOK_LIMIT", "20"))
MAX_SPREAD_BPS = float(os.getenv("LIQUIDITY_MAX_SPREAD_BPS", "8"))
MIN_DEPTH_USDT = float(os.getenv("LIQUIDITY_MIN_DEPTH_USDT", "50000"))
MIN_24H_QUOTE_VOLUME = float(os.getenv("LIQUIDITY_MIN_24H_QUOTE_VOLUME", "10000000"))
MAX_CANDLE_STALE_SECONDS = int(os.getenv("MAX_CANDLE_STALE_SECONDS", "900"))
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

Kline = list[Any]


class GatewayState:
    def __init__(self) -> None:
        self.cache: dict[tuple[str, str], list[Kline]] = {}
        self.last_ws_update: dict[tuple[str, str], int] = {}
        self.market_health: dict[str, dict[str, Any]] = {}
        self.public_cache: dict[str, tuple[float, int, str, bytes]] = {}
        self.active_alerts: set[str] = set()
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "public_cache_hits": 0,
            "public_cache_misses": 0,
            "upstream_requests": 0,
            "upstream_errors": 0,
            "ws_reconnects": 0,
            "dynamic_markets_added": 0,
            "alerts_sent": 0,
        }
        self.markets = {
            (symbol.replace("/", "").replace(":USDT", "").upper(), interval)
            for symbol in SYMBOLS
            for interval in INTERVALS
        }
        self.ws_refresh = asyncio.Event()
        self._client: httpx.AsyncClient | None = None
        self._redis: redis.Redis | None = None
        self._lock = asyncio.Lock()
        self._last_upstream_request = 0.0
        self.ws_task: asyncio.Task[None] | None = None
        self.liquidity_task: asyncio.Task[None] | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)
        return self._client

    @property
    def redis_client(self) -> redis.Redis | None:
        if not REDIS_URL:
            return None
        if self._redis is None:
            self._redis = redis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        for task in (self.ws_task, self.liquidity_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._client:
            await self._client.aclose()
        if self._redis:
            await self._redis.aclose()

    async def upstream_get(self, path: str, params: dict[str, str]) -> httpx.Response:
        async with self._lock:
            wait_for = (UPSTREAM_MIN_INTERVAL_MS / 1000) - (time.monotonic() - self._last_upstream_request)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_upstream_request = time.monotonic()

        self.stats["upstream_requests"] += 1
        try:
            return await self.client.get(f"{UPSTREAM_REST}{path}", params=params)
        except Exception:
            self.stats["upstream_errors"] += 1
            raise

    def public_cache_key(self, path: str, params: dict[str, str]) -> str:
        return f"{path}?{json.dumps(params, sort_keys=True, separators=(',', ':'))}"

    def get_public_response(self, path: str, params: dict[str, str]) -> tuple[int, str, bytes] | None:
        cached = self.public_cache.get(self.public_cache_key(path, params))
        if cached is None:
            return None
        expires_at, status_code, media_type, content = cached
        if expires_at <= time.monotonic():
            self.public_cache.pop(self.public_cache_key(path, params), None)
            return None
        return status_code, media_type, content

    def set_public_response(self, path: str, params: dict[str, str], response: httpx.Response) -> None:
        if PUBLIC_CACHE_TTL_SECONDS <= 0 or response.status_code != 200:
            return
        media_type = response.headers.get("content-type", "application/json")
        expires_at = time.monotonic() + PUBLIC_CACHE_TTL_SECONDS
        self.public_cache[self.public_cache_key(path, params)] = (expires_at, response.status_code, media_type, response.content)

    def merge_klines(self, symbol: str, interval: str, klines: list[Kline]) -> None:
        key = (symbol.upper(), interval)
        merged = {int(k[0]): k for k in self.cache.get(key, [])}
        for kline in klines:
            if len(kline) >= 12:
                merged[int(kline[0])] = kline
        self.cache[key] = [merged[t] for t in sorted(merged)][-CACHE_MAX_ROWS:]
        if self.cache[key]:
            self.last_ws_update[key] = int(time.time() * 1000)

    def add_market(self, symbol: str, interval: str) -> None:
        key = (symbol.upper(), interval)
        if key in self.markets:
            return
        self.markets.add(key)
        self.stats["dynamic_markets_added"] += 1
        self.ws_refresh.set()
        LOGGER.info("added dynamic market %s %s", symbol, interval)

    async def persist_klines(self, symbol: str, interval: str) -> None:
        client = self.redis_client
        if client is None:
            return
        rows = self.cache.get((symbol.upper(), interval), [])
        if rows:
            try:
                await client.set(f"klines:{symbol.upper()}:{interval}", json.dumps(rows))
            except redis.RedisError as exc:
                LOGGER.warning("redis persist failed for %s %s: %s", symbol, interval, exc)

    async def load_klines(self, symbol: str, interval: str) -> bool:
        client = self.redis_client
        if client is None:
            return False
        try:
            raw = await client.get(f"klines:{symbol.upper()}:{interval}")
        except redis.RedisError as exc:
            LOGGER.warning("redis load failed for %s %s: %s", symbol, interval, exc)
            return False
        if not raw:
            return False
        rows = json.loads(raw)
        if not isinstance(rows, list):
            return False
        self.merge_klines(symbol, interval, rows)
        return True

    def get_cached_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | None,
        end_time: int | None,
        limit: int,
    ) -> list[Kline] | None:
        rows = self.cache.get((symbol.upper(), interval), [])
        if not rows:
            return None
        if len(interval) < 2 or interval[-1] not in "smhdw":
            return None
        try:
            interval_count = int(interval[:-1])
        except ValueError:
            return None
        if interval_count <= 0:
            return None
        interval_ms = interval_count * {
            "s": 1_000,
            "m": 60_000,
            "h": 3_600_000,
            "d": 86_400_000,
            "w": 604_800_000,
        }[interval[-1]]

        filtered = rows
        if start_time is not None:
            filtered = [row for row in filtered if int(row[0]) >= start_time]
        if end_time is not None:
            filtered = [row for row in filtered if int(row[0]) <= end_time]
        if not filtered:
            return None
        if start_time is not None and int(filtered[0][0]) - start_time >= interval_ms:
            return None

        selected = filtered[:limit] if start_time is not None else filtered[-limit:]
        if len(selected) < min(limit, 2):
            return None
        if any(
            int(current[0]) - int(previous[0]) > interval_ms
            for previous, current in zip(selected, selected[1:])
        ):
            return None
        if (
            end_time is not None
            and len(selected) < limit
            and int(selected[-1][0]) < end_time - interval_ms
        ):
            return None
        return selected


state = GatewayState()


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace(":USDT", "").upper()


def kline_from_ws(payload: dict[str, Any]) -> Kline:
    k = payload["k"]
    return [
        int(k["t"]),
        k["o"],
        k["h"],
        k["l"],
        k["c"],
        k["v"],
        int(k["T"]),
        k["q"],
        int(k["n"]),
        k["V"],
        k["Q"],
        "0",
    ]


def depth_usdt(levels: list[list[str]]) -> float:
    return sum(float(price) * float(amount) for price, amount in levels)


def health_status(score: float) -> str:
    if score >= 70:
        return "healthy"
    if score >= 40:
        return "degraded"
    return "unhealthy"


async def prewarm_cache() -> None:
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            if await state.load_klines(normalize_symbol(symbol), interval):
                LOGGER.info("loaded %s %s from redis cache", symbol, interval)
                continue
            response = await state.upstream_get(
                "/fapi/v1/klines",
                {"symbol": normalize_symbol(symbol), "interval": interval, "limit": str(PREWARM_LIMIT)},
            )
            response.raise_for_status()
            normalized = normalize_symbol(symbol)
            state.merge_klines(normalized, interval, response.json())
            await state.persist_klines(normalized, interval)
            LOGGER.info("prewarmed %s %s with %s rows", symbol, interval, len(response.json()))


async def send_alert(symbol: str, health: dict[str, Any]) -> None:
    alert_key = f"{symbol}:{health['status']}"
    if health["status"] == "healthy":
        for key in list(state.active_alerts):
            if key.startswith(f"{symbol}:"):
                state.active_alerts.remove(key)
        return
    if alert_key in state.active_alerts:
        return

    message = f"Market health {health['status']} for {symbol}: score={health['score']} reasons={','.join(health['reasons'])}"
    LOGGER.warning(message)
    state.active_alerts.add(alert_key)
    state.stats["alerts_sent"] += 1
    if ALERT_WEBHOOK_URL:
        await state.client.post(ALERT_WEBHOOK_URL, json={"text": message, "symbol": symbol, "health": health})


async def refresh_symbol_health(symbol: str) -> None:
    depth_response = await state.upstream_get(
        "/fapi/v1/depth",
        {"symbol": symbol, "limit": str(ORDERBOOK_LIMIT)},
    )
    depth_response.raise_for_status()
    depth = depth_response.json()

    ticker_response = await state.upstream_get("/fapi/v1/ticker/24hr", {"symbol": symbol})
    ticker_response.raise_for_status()
    ticker = ticker_response.json()

    best_bid = float(depth["bids"][0][0])
    best_ask = float(depth["asks"][0][0])
    midpoint = (best_bid + best_ask) / 2
    spread_bps = ((best_ask - best_bid) / midpoint) * 10000 if midpoint else 0
    bid_depth = depth_usdt(depth["bids"])
    ask_depth = depth_usdt(depth["asks"])
    min_depth = min(bid_depth, ask_depth)
    quote_volume = float(ticker.get("quoteVolume", 0))

    symbol_updates = [
        updated
        for (market_symbol, _), updated in state.last_ws_update.items()
        if market_symbol == symbol
    ]
    candle_stale_seconds = None
    if symbol_updates:
        candle_stale_seconds = max(0, int(time.time() - (max(symbol_updates) / 1000)))

    score = 100.0
    reasons: list[str] = []
    if spread_bps > MAX_SPREAD_BPS:
        score -= min(35, 10 + ((spread_bps / MAX_SPREAD_BPS) - 1) * 20)
        reasons.append("wide_spread")
    if min_depth < MIN_DEPTH_USDT:
        score -= min(30, (1 - (min_depth / MIN_DEPTH_USDT)) * 30)
        reasons.append("thin_orderbook")
    if quote_volume < MIN_24H_QUOTE_VOLUME:
        score -= min(20, (1 - (quote_volume / MIN_24H_QUOTE_VOLUME)) * 20)
        reasons.append("low_volume")
    if candle_stale_seconds is None or candle_stale_seconds > MAX_CANDLE_STALE_SECONDS:
        score -= 30
        reasons.append("stale_candles")

    health = {
        "symbol": symbol,
        "status": health_status(score),
        "score": round(max(0, score), 2),
        "spread_bps": round(spread_bps, 4),
        "bid_depth_usdt": round(bid_depth, 2),
        "ask_depth_usdt": round(ask_depth, 2),
        "min_depth_usdt": round(min_depth, 2),
        "quote_volume_24h": round(quote_volume, 2),
        "candle_stale_seconds": candle_stale_seconds,
        "reasons": reasons,
        "updated_at": int(time.time() * 1000),
    }
    state.market_health[symbol] = health
    await send_alert(symbol, health)


async def liquidity_loop() -> None:
    while True:
        symbols = sorted({symbol for symbol, _ in state.markets})
        for symbol in symbols:
            try:
                await refresh_symbol_health(symbol)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("liquidity refresh failed for %s: %s: %s", symbol, type(exc).__name__, exc)
        await asyncio.sleep(LIQUIDITY_REFRESH_SECONDS)


async def websocket_loop() -> None:
    while True:
        markets = sorted(state.markets)
        streams = "/".join(f"{symbol.lower()}@kline_{interval}" for symbol, interval in markets)
        if not streams:
            await asyncio.sleep(5)
            continue

        url = f"{UPSTREAM_WS}?streams={streams}"
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                state.ws_refresh.clear()
                LOGGER.info("connected websocket streams: %s", streams)
                while True:
                    recv_task = asyncio.create_task(ws.recv())
                    refresh_task = asyncio.create_task(state.ws_refresh.wait())
                    done, pending = await asyncio.wait(
                        {recv_task, refresh_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

                    if refresh_task in done and state.ws_refresh.is_set():
                        LOGGER.info("reconnecting websocket to include new dynamic markets")
                        break

                    message = recv_task.result()
                    data = json.loads(message)
                    payload = data.get("data", {})
                    if payload.get("e") != "kline":
                        continue
                    symbol = normalize_symbol(payload["s"])
                    interval = payload["k"]["i"]
                    state.merge_klines(symbol, interval, [kline_from_ws(payload)])
                    asyncio.create_task(state.persist_klines(symbol, interval))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.stats["ws_reconnects"] += 1
            LOGGER.warning("websocket disconnected: %s: %s", type(exc).__name__, exc)
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await prewarm_cache()
    except Exception as exc:
        LOGGER.warning("cache prewarm failed, REST fallback remains active: %s: %s", type(exc).__name__, exc)
    state.ws_task = asyncio.create_task(websocket_loop())
    state.liquidity_task = asyncio.create_task(liquidity_loop())
    yield
    await state.close()


app = FastAPI(title="Freqtrade Market Gateway", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "binance_env": BINANCE_ENV,
        "upstream_rest": UPSTREAM_REST,
        "upstream_ws": UPSTREAM_WS,
        "public_cache_ttl_seconds": PUBLIC_CACHE_TTL_SECONDS,
        "public_cache_paths": sorted(PUBLIC_CACHE_PATHS),
        "symbols": SYMBOLS,
        "intervals": INTERVALS,
        "redis_enabled": bool(REDIS_URL),
        "alert_webhook_enabled": bool(ALERT_WEBHOOK_URL),
        "watched_markets": len(state.markets),
        "cached_markets": len(state.cache),
        "health_markets": len(state.market_health),
        "stats": state.stats,
    }


@app.get("/upstream/health")
async def upstream_health() -> JSONResponse:
    try:
        response = await state.upstream_get("/fapi/v1/time", {})
    except Exception as exc:
        return JSONResponse(
            {
                "status": "error",
                "binance_env": BINANCE_ENV,
                "upstream_rest": UPSTREAM_REST,
                "error": str(exc),
            },
            status_code=502,
        )
    return JSONResponse(
        {
            "status": "ok" if response.status_code == 200 else "error",
            "binance_env": BINANCE_ENV,
            "upstream_rest": UPSTREAM_REST,
            "upstream_status_code": response.status_code,
            "body": response.text[:500],
        },
        status_code=200 if response.status_code == 200 else 502,
    )


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    return state.stats


@app.get("/cache/status")
async def cache_status() -> dict[str, Any]:
    return {
        f"{symbol}:{interval}": {
            "rows": len(rows),
            "first_open_time": int(rows[0][0]) if rows else None,
            "last_open_time": int(rows[-1][0]) if rows else None,
            "last_update": state.last_ws_update.get((symbol, interval)),
        }
        for (symbol, interval), rows in state.cache.items()
    }


@app.get("/liquidity/health")
async def liquidity_health() -> dict[str, dict[str, Any]]:
    return state.market_health


@app.get("/liquidity/health/{symbol}")
async def liquidity_health_symbol(symbol: str) -> JSONResponse:
    normalized = normalize_symbol(symbol)
    health = state.market_health.get(normalized)
    if health is None:
        await refresh_symbol_health(normalized)
        health = state.market_health.get(normalized)
    return JSONResponse(health or {"symbol": normalized, "status": "unknown"}, status_code=200 if health else 404)


@app.get("/alerts")
async def alerts() -> dict[str, Any]:
    return {"active_alerts": sorted(state.active_alerts), "alerts_sent": state.stats["alerts_sent"]}


@app.get("/fapi/v1/klines")
async def futures_klines(request: Request) -> JSONResponse:
    params = dict(request.query_params)
    symbol = normalize_symbol(params["symbol"])
    interval = params["interval"]
    limit = min(int(params.get("limit", "500")), 1500)
    start_time = int(params["startTime"]) if "startTime" in params else None
    end_time = int(params["endTime"]) if "endTime" in params else None

    state.add_market(symbol, interval)
    cached = state.get_cached_klines(symbol, interval, start_time, end_time, limit)
    if cached is not None:
        state.stats["cache_hits"] += 1
        return JSONResponse(cached)

    state.stats["cache_misses"] += 1
    response = await state.upstream_get("/fapi/v1/klines", params)
    rows = response.json()
    if response.status_code == 200 and isinstance(rows, list):
        state.merge_klines(symbol, interval, rows)
        await state.persist_klines(symbol, interval)
    return JSONResponse(rows, status_code=response.status_code)


@app.api_route("/fapi/v1/{path:path}", methods=["GET"])
async def futures_public_fallback(path: str, request: Request) -> Response:
    params = dict(request.query_params)
    if path in PUBLIC_CACHE_PATHS:
        cached = state.get_public_response(path, params)
        if cached is not None:
            state.stats["public_cache_hits"] += 1
            status_code, media_type, content = cached
            return Response(content=content, status_code=status_code, media_type=media_type)
        state.stats["public_cache_misses"] += 1

    response = await state.upstream_get(f"/fapi/v1/{path}", params)
    if path in PUBLIC_CACHE_PATHS:
        state.set_public_response(path, params, response)
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )
