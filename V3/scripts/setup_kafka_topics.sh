#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP="${1:-localhost:9092}"
COMPOSE_FILE="${2:-docker-compose.kafka-local.yml}"

CONTAINER_NAME="$(docker-compose -f "$COMPOSE_FILE" ps -q kafka | xargs docker inspect --format '{{.Name}}' | sed 's#^/##')"
if [[ -z "${CONTAINER_NAME}" ]]; then
  echo "Kafka container não encontrado para compose file: $COMPOSE_FILE" >&2
  exit 1
fi

TOPICS=(
  "fonte-assignments:8"
  "raw-articles:16"
  "classified-articles:16"
  "article-published:16"
  "pautas-especiais:8"
  "pautas-gap:8"
  "consolidacao:8"
  "homepage-updates:4"
  "breaking-candidate:4"
)

for item in "${TOPICS[@]}"; do
  name="${item%%:*}"
  parts="${item##*:}"
  docker exec "$CONTAINER_NAME" kafka-topics \
    --bootstrap-server "$BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic "$name" \
    --partitions "$parts" \
    --replication-factor 1
done

docker exec "$CONTAINER_NAME" kafka-topics --bootstrap-server "$BOOTSTRAP" --list
