# brasileira.news V3 — Deploy

Este diretório sobe a stack completa V3 (infra + agentes) via Docker Compose.

## Pré-requisitos

- Docker Engine + Docker Compose plugin
- `psql` client instalado no host
- Acesso de rede para baixar imagens/pacotes
- Arquivo `.env` com credenciais reais (WP + chaves LLM)

## Subida rápida

```bash
cd /home/bitnami/V3
chmod +x deploy.sh
cp .env.example .env
./deploy.sh
```

## Modo híbrido automático (recomendado no seu cenário)

```bash
cd /home/bitnami/V3
# .env deve apontar para Postgres Aiven e host local para Kafka/Redis
HYBRID=1 PROFILE=prod ./deploy.sh
```

Esse modo usa:
- Kafka local (`docker-compose.kafka-local.yml`)
- Redis local (`127.0.0.1:6379`)
- PostgreSQL remoto (Aiven via `POSTGRES_DSN`)

## Subida manual

```bash
cd /home/bitnami/V3
cp .env.example .env
docker compose -f docker-compose.infra.yml up -d
psql -h localhost -U brasileira -d brasileira_v3 -f migrations/001_schema_base.sql
psql -h localhost -U brasileira -d brasileira_v3 -f migrations/002_pgvector.sql
psql -h localhost -U brasileira -d brasileira_v3 -f migrations/003_indices.sql
docker compose build
docker compose --profile prod up -d
docker compose ps
```

## Profiles (dev/prod)

```bash
# DEV: núcleo mínimo para desenvolvimento
docker compose --profile dev up -d

# PROD: stack completa
docker compose --profile prod up -d

# Infra dedicada
docker compose -f docker-compose.infra.yml up -d

# Kafka local barato (híbrido)
docker compose -f docker-compose.kafka-local.yml up -d
./scripts/setup_kafka_topics.sh localhost:9092

# Derrubar perfil
docker compose --profile prod down
```

## Logs e operação

```bash
docker compose logs -f smart_router
docker compose logs -f monitor_concorrencia
docker compose restart reporter
docker compose -f docker-compose.infra.yml ps
docker compose --profile prod down
```

## Testes

```bash
source /home/bitnami/venv/bin/activate
cd /home/bitnami/V3
pytest -q
```

## Observações

- `monitor_concorrencia` usa Playwright (Chromium) no container.
- `editor_chefe` publica pesos em Redis (`editorial:pesos:*`) e gaps em Kafka (`pautas-gap`).
- `monitor_sistema/focas` nunca desativa fontes; só ajusta polling até 24h.
- O `docker-compose.infra.yml` sobe Redis/Kafka/PostgreSQL+pgvector.
- O `docker-compose.yml` sobe os agentes com healthchecks e profiles.
- Para arranjo híbrido (Aiven Postgres + Redis local + Kafka local), use `docker-compose.kafka-local.yml`.
- O `deploy.sh` suporta `HYBRID=1` para automatizar esse arranjo.
- Em modo container, use `host.docker.internal` nas URLs de Kafka/Redis se os serviços rodarem no host.
