#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ACTION=start
MODE=backtest
GATEWAY=false
REDIS=false
DAYS=30
SKIP_DEMO=false

usage() {
    echo "sh start.sh [start|init|demo|check|status|stop] [--mode backtest|paper|both] [--gateway] [--redis] [--days 1..365] [--skip-demo]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        start|init|demo|check|status|stop) ACTION=$1; shift ;;
        --mode) MODE=${2:?Missing mode}; shift 2 ;;
        --days) DAYS=${2:?Missing days}; shift 2 ;;
        --gateway) GATEWAY=true; shift ;;
        --redis) REDIS=true; shift ;;
        --skip-demo) SKIP_DEMO=true; shift ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 1 ;;
    esac
done
case "$MODE" in backtest|paper|both) ;; *) usage >&2; exit 1 ;; esac
case "$DAYS" in ''|*[!0-9]*) usage >&2; exit 1 ;; esac
if [ "$DAYS" -lt 1 ] || [ "$DAYS" -gt 365 ]; then usage >&2; exit 1; fi
if "$REDIS" && ! "$GATEWAY"; then echo "--redis requires --gateway" >&2; exit 1; fi
command -v docker >/dev/null 2>&1 || { echo "Install Docker Engine and Compose first." >&2; exit 1; }
DOCKER_OS=$(docker info --format '{{.OSType}}')
if [ "$DOCKER_OS" != linux ]; then echo "Linux containers are required." >&2; exit 1; fi
docker compose version
export LOCAL_UID=$(id -u)
export LOCAL_GID=$(id -g)
export GATEWAY_REDIS_URL=
if "$REDIS"; then export GATEWAY_REDIS_URL=redis://market_redis:6379/0; fi

compose() {
    docker compose --project-directory "$ROOT" --file "$ROOT/compose.yaml" "$@"
}
case "$ACTION" in
    stop) compose --profile '*' down; exit 0 ;;
    status) compose --profile '*' ps --all; exit 0 ;;
esac
mkdir -p "$ROOT/runtime"
set -- --mode "$MODE"
if "$GATEWAY"; then set -- "$@" --gateway; fi
if "$REDIS"; then set -- "$@" --redis; fi
if [ "$ACTION" = start ]; then
    compose --profile '*' stop backtest trader market_gateway market_redis
fi
if [ "$ACTION" = start ] || [ "$ACTION" = init ]; then
    compose run --rm --no-deps tools init "$@"
fi
if [ "$ACTION" = init ]; then exit 0; fi
if [ "$ACTION" = start ] && "$REDIS"; then compose --profile redis up -d --wait --wait-timeout 90 market_redis; fi
if [ "$ACTION" = start ] && "$GATEWAY"; then compose --profile gateway up -d --build --wait --wait-timeout 240 market_gateway; fi
case "$ACTION" in
    check) compose run --rm --no-deps tools validate; exit 0 ;;
    demo) compose run --rm --no-deps tools demo --days "$DAYS"; exit 0 ;;
esac
case "$MODE" in
    backtest) compose --profile research up -d --force-recreate --wait --wait-timeout 240 backtest ;;
    paper) compose --profile paper up -d --force-recreate --wait --wait-timeout 240 trader ;;
    both) compose --profile research --profile paper up -d --force-recreate --wait --wait-timeout 240 backtest trader ;;
esac
compose run --rm --no-deps tools verify "$@"
if ! "$SKIP_DEMO" && [ "$MODE" != paper ]; then
    compose run --rm --no-deps tools demo --days "$DAYS"
fi
echo "Ready. Backtest: http://127.0.0.1:${BACKTEST_PORT:-18085} ; paper: http://127.0.0.1:${PAPER_PORT:-18080} (selected modes only)."
echo "Credentials: runtime/config.backtest.json or runtime/config.paper.json -> api_server."
