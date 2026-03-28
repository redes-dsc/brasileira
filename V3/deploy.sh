#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "[deploy] diretório: $ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[deploy] erro: docker não encontrado"
  exit 1
fi

compose_cmd() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

if [[ ! -f ".env" ]]; then
  echo "[deploy] .env não encontrado, copiando de .env.example"
  cp .env.example .env
  echo "[deploy] ajuste o arquivo .env e rode novamente."
  exit 1
fi

set -a
source .env
set +a

PROFILE="${PROFILE:-prod}"
HYBRID="${HYBRID:-0}"
NO_BUILD="${NO_BUILD:-0}"

if [[ "$HYBRID" == "1" ]]; then
  echo "[deploy] modo HYBRID=1 (Kafka local + Redis local + Postgres Aiven)"

  if ! grep -q "^KAFKA_BOOTSTRAP_SERVERS=kafka:29092" .env; then
    sed -i "s|^KAFKA_BOOTSTRAP_SERVERS=.*|KAFKA_BOOTSTRAP_SERVERS=kafka:29092|" .env
  fi
  if ! grep -q "^REDIS_URL=redis://redis:6379/0" .env; then
    sed -i "s|^REDIS_URL=.*|REDIS_URL=redis://redis:6379/0|" .env
  fi
  set -a
  source .env
  set +a

  echo "[deploy] subindo Kafka local..."
  compose_cmd -f docker-compose.kafka-local.yml up -d
  sleep 8
  if ! compose_cmd -f docker-compose.kafka-local.yml exec -T redis redis-cli ping >/dev/null 2>&1; then
    echo "[deploy] erro: Redis local (compose) não está saudável"
    exit 1
  fi
  ./scripts/setup_kafka_topics.sh localhost:9092 docker-compose.kafka-local.yml || true

  echo "[deploy] validando PostgreSQL remoto..."
  psql "$POSTGRES_DSN" -c "select now();" >/dev/null

  echo "[deploy] rodando migrações no PostgreSQL remoto..."
  psql "$POSTGRES_DSN" -f migrations/001_schema_base.sql
  psql "$POSTGRES_DSN" -f migrations/002_pgvector.sql
  psql "$POSTGRES_DSN" -f migrations/003_indices.sql
else
  echo "[deploy] subindo infraestrutura completa local (docker-compose.infra.yml)..."
  compose_cmd -f docker-compose.infra.yml up -d
  sleep 8

  echo "[deploy] rodando migrações no PostgreSQL local..."
  psql -h localhost -U brasileira -d brasileira_v3 -f migrations/001_schema_base.sql
  psql -h localhost -U brasileira -d brasileira_v3 -f migrations/002_pgvector.sql
  psql -h localhost -U brasileira -d brasileira_v3 -f migrations/003_indices.sql
fi

if [[ "$NO_BUILD" == "1" ]]; then
  echo "[deploy] NO_BUILD=1: pulando build"
else
  echo "[deploy] build de serviços..."
  if [[ "$HYBRID" == "1" ]]; then
    compose_cmd build --no-cache \
      smart_router worker_pool classificador reporter \
      monitor_concorrencia monitor_sistema pauteiro editor_chefe \
      fotografo revisor consolidador curador_homepage
  else
    compose_cmd build --no-cache
  fi
fi

echo "[deploy] subindo stack..."
echo "[deploy] profile: $PROFILE"
compose_cmd --profile "$PROFILE" up -d

echo "[deploy] status infraestrutura:"
if [[ "$HYBRID" == "1" ]]; then
  compose_cmd -f docker-compose.kafka-local.yml ps
else
  compose_cmd -f docker-compose.infra.yml ps
fi
echo "[deploy] status:"
compose_cmd ps

echo "[deploy] concluído."
