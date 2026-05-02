#!/usr/bin/env bash
#
# Run the full Python test suite with coverage.
#
# Usage:
#   tools/test.sh                 # bring up local Postgres, run tests, tear down
#   tools/test.sh --no-docker     # assume Postgres is already running (CI uses this)
#   tools/test.sh --keep-db       # leave the Postgres container running after tests
#   tools/test.sh -k some_name    # any pytest args after a `--` are forwarded
#
# Coverage report:
#   - Terminal summary printed at end
#   - HTML report at htmlcov/index.html
#   - Fails the run with exit 1 if combined line+branch coverage is below 100%
#
# The script is idempotent: rerunning it doesn't accumulate containers or
# leave the working tree dirty.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

USE_DOCKER=true
KEEP_DB=false
PYTEST_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --no-docker) USE_DOCKER=false ;;
        --keep-db)   KEEP_DB=true ;;
        *)           PYTEST_ARGS+=("$arg") ;;
    esac
done

CONTAINER_NAME="card-market-test-postgres"

if [[ "$USE_DOCKER" == "true" ]]; then
    echo "==> Starting test Postgres ($CONTAINER_NAME)..."

    # Remove any leftover container from an interrupted previous run so the
    # name is free. `|| true` because rm fails (harmlessly) when nothing
    # exists.
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

    docker run -d --rm \
        --name "$CONTAINER_NAME" \
        -p 5433:5432 \
        -e POSTGRES_USER=test \
        -e POSTGRES_PASSWORD=test \
        -e POSTGRES_DB=card_market_test \
        docker.io/library/postgres:16-alpine >/dev/null

    if [[ "$KEEP_DB" != "true" ]]; then
        # The container has --rm so `docker stop` cleans up automatically.
        trap 'echo "==> Stopping test Postgres..."; docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true' EXIT
    fi

    echo "==> Waiting for Postgres to become ready..."
    for _ in $(seq 1 60); do
        if pg_isready -h localhost -p 5433 -U test -d card_market_test >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
fi

export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql://test:test@localhost:5433/card_market_test}"

echo "==> Syncing root virtualenv..."
uv sync --quiet

echo "==> Running pytest with branch coverage..."
uv run pytest \
    --cov \
    --cov-branch \
    --cov-report=term-missing \
    --cov-report=html \
    --cov-fail-under=100 \
    "${PYTEST_ARGS[@]}"
