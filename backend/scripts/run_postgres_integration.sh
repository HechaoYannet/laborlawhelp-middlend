#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PG_CONTAINER="${PG_CONTAINER:-laborlawhelp-it-postgres}"
REDIS_CONTAINER="${REDIS_CONTAINER:-laborlawhelp-it-redis}"
PG_PORT="${PG_PORT:-55432}"
REDIS_PORT="${REDIS_PORT:-56379}"
PG_DB="${PG_DB:-laborlawhelp_it}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"
KEEP_CONTAINERS="${KEEP_CONTAINERS:-0}"

DATABASE_URL="postgresql://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_PORT}/${PG_DB}"
REDIS_URL="redis://127.0.0.1:${REDIS_PORT}/15"

cleanup() {
    docker rm -f "${PG_CONTAINER}" "${REDIS_CONTAINER}" >/dev/null 2>&1 || true
}

if [[ "${KEEP_CONTAINERS}" != "1" ]]; then
    trap cleanup EXIT
fi

echo "[1/5] 启动 PostgreSQL 与 Redis 容器..."
docker rm -f "${PG_CONTAINER}" "${REDIS_CONTAINER}" >/dev/null 2>&1 || true
docker run -d \
    --name "${PG_CONTAINER}" \
    -e POSTGRES_DB="${PG_DB}" \
    -e POSTGRES_USER="${PG_USER}" \
    -e POSTGRES_PASSWORD="${PG_PASSWORD}" \
    -p "${PG_PORT}:5432" \
    postgres:16-alpine >/dev/null

docker run -d \
    --name "${REDIS_CONTAINER}" \
    -p "${REDIS_PORT}:6379" \
    redis:7-alpine >/dev/null

echo "[2/5] 等待依赖就绪..."
for i in {1..40}; do
    if docker exec "${PG_CONTAINER}" pg_isready -U "${PG_USER}" -d "${PG_DB}" >/dev/null 2>&1; then
        break
    fi
    if [[ "${i}" == "40" ]]; then
        echo "PostgreSQL 启动超时"
        exit 1
    fi
    sleep 1
done

for i in {1..40}; do
    if docker exec "${REDIS_CONTAINER}" redis-cli ping | grep -q "PONG"; then
        break
    fi
    if [[ "${i}" == "40" ]]; then
        echo "Redis 启动超时"
        exit 1
    fi
    sleep 1
done

echo "[3/5] 初始化 Schema 与 Migration..."
cat "${ROOT_DIR}/sql/init_schema.sql" | docker exec -i "${PG_CONTAINER}" psql -v ON_ERROR_STOP=1 -U "${PG_USER}" -d "${PG_DB}" >/dev/null

if compgen -G "${ROOT_DIR}/sql/migrations/*.sql" > /dev/null; then
    for migration in "${ROOT_DIR}"/sql/migrations/*.sql; do
        cat "${migration}" | docker exec -i "${PG_CONTAINER}" psql -v ON_ERROR_STOP=1 -U "${PG_USER}" -d "${PG_DB}" >/dev/null
    done
fi

echo "[4/5] 运行 Postgres/Redis 集成测试..."
(
    cd "${ROOT_DIR}"
    INTEGRATION_DATABASE_URL="${DATABASE_URL}" \
    INTEGRATION_REDIS_URL="${REDIS_URL}" \
    storage_backend=postgres \
    database_url="${DATABASE_URL}" \
    redis_url="${REDIS_URL}" \
    auth_mode=anonymous \
    oh_use_mock=true \
    python -m pytest -q tests/integration
)

echo "[5/5] 集成测试完成。"
if [[ "${KEEP_CONTAINERS}" == "1" ]]; then
    echo "KEEP_CONTAINERS=1，容器未自动删除：${PG_CONTAINER}, ${REDIS_CONTAINER}"
fi
