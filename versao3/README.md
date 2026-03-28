# Newsroom V3

Base modular da V3 do brasileira.news.

## Estrutura

- `src/newsroom_v3/agents`: agentes (a implementar via briefings específicos)
- `src/newsroom_v3/ingestion`: ingestão paralela e deduplicação
- `src/newsroom_v3/classification`: classificador de categorias
- `src/newsroom_v3/llm`: SmartRouter, tiers e health tracking
- `src/newsroom_v3/integrations`: clientes externos (Kafka, Postgres, Redis, WordPress)
- `src/newsroom_v3/memory`: memória de trabalho/episódica/semântica
- `src/newsroom_v3/observability`: métricas, tracing e alertas

## Subir infraestrutura local

```bash
docker compose up -d
```

Serviços:
- PostgreSQL + pgvector
- Redis
- Kafka (KRaft)
- Kafka UI
