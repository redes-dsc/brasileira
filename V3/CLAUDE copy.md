# CLAUDE.md — brasileira.news V3 Multi-Agent System

## Identidade do Projeto
- **Portal:** brasileira.news — portal jornalístico brasileiro 100% automatizado por IA
- **Repositório:** https://github.com/redes-dsc/brasileira
- **Branch principal:** main
- **Servidor:** AWS Lightsail Bitnami WordPress (ip-172-26-3-153)
- **Ambiente:** Python 3.12+, WordPress Multisite (Bitnami), MariaDB

## Stack V3
- **Orquestração:** LangGraph (StateGraph por agente)
- **Mensageria:** Apache Kafka (tópicos particionados)
- **Cache/Locks:** Redis 7+
- **Database:** PostgreSQL 16 + pgvector (memória semântica)
- **WordPress:** REST API + MariaDB direta (DB: bitnami_wordpress, PREFIX: wp_7_, BLOG_ID: 7, USER: iapublicador)
- **LLM Proxy:** LiteLLM (ATENÇÃO: versões 1.82.7 e 1.82.8 comprometidas — supply chain attack março/2026)
- **7 Provedores LLM:** Anthropic (Claude Opus 4/Sonnet 4), OpenAI (GPT-5.4/4.1-mini), Google (Gemini 3.1 Pro/2.5 Flash), xAI (Grok 4), Perplexity (Sonar Pro), DeepSeek (V3.2), Alibaba (Qwen 3.5)
- **NÃO disponíveis:** Llama, Mixtral ou qualquer modelo open-source local
- **Containers:** Docker + Docker Compose

## Estrutura do Servidor (Filesystem)
```
/home/bitnami/
├── htdocs/                    # WordPress (NÃO TOCAR)
├── V3/                        # ← PASTA DE TRABALHO DA V3
├── versao2/                   # Código V2 (referência)
├── versao3/                   # Tentativa anterior (referência)
├── motor_rss/                 # Motor RSS V2 em produção
├── motor_scrapers/            # Motor Scrapers V2 em produção
├── motor_consolidado/         # Motor Consolidado V2
├── curator/                   # Curador V2
├── scripts/                   # Scripts operacionais
├── logs/                      # Logs de operação
├── tests/                     # Testes existentes
├── venv/                      # Virtual environment Python
├── stack/                     # Infraestrutura (Kafka, Redis, PostgreSQL)
└── backups_adsense/           # Backups
```

## Estrutura Alvo V3 (a ser criada em /home/bitnami/V3/)
```
V3/
├── CLAUDE.md                  # Este arquivo
├── docker-compose.yml         # Orquestração de todos os serviços
├── docker-compose.infra.yml   # Kafka + Redis + PostgreSQL + pgvector
├── .env.example               # Template de variáveis de ambiente
├── requirements-base.txt      # Dependências compartilhadas
├── shared/                    # Código compartilhado entre componentes
│   ├── __init__.py
│   ├── config.py              # Configurações centralizadas via .env
│   ├── kafka_client.py        # Producer/Consumer Kafka reutilizável
│   ├── redis_client.py        # Conexão Redis reutilizável
│   ├── db.py                  # PostgreSQL + pgvector connection pool
│   ├── wp_client.py           # WordPress REST API client assíncrono
│   ├── memory.py              # Sistema de memória em 3 camadas
│   └── schemas.py             # Schemas Pydantic V2 compartilhados
├── smart_router/              # Componente #1 — SmartLLMRouter
│   ├── __init__.py
│   ├── router.py
│   ├── health_checker.py
│   ├── tier_manager.py
│   ├── cost_tracker.py
│   └── Dockerfile
├── worker_pool/               # Componente #2 — Worker Pool de Coletores
│   ├── __init__.py
│   ├── collector.py
│   ├── rss_fetcher.py
│   ├── scraper_engine.py
│   ├── feed_scheduler.py
│   └── Dockerfile
├── classificador/             # Componente #3 — Classificador + Kafka Pipeline
│   ├── __init__.py
│   ├── classifier.py
│   ├── ner_extractor.py
│   ├── relevance_scorer.py
│   ├── pipeline.py
│   └── Dockerfile
├── reporter/                  # Componente #4 — Reporter
│   ├── __init__.py
│   ├── reporter.py
│   ├── content_extractor.py
│   ├── writer.py
│   ├── seo_optimizer.py
│   ├── publisher.py
│   └── Dockerfile
├── fotografo/                 # Componente #5 — Fotógrafo
│   ├── __init__.py
│   ├── fotografo.py
│   ├── tier1_original.py
│   ├── tier2_stocks.py
│   ├── tier3_generative.py
│   ├── tier4_placeholder.py
│   ├── query_generator.py
│   ├── clip_validator.py
│   └── Dockerfile
├── revisor/                   # Componente #6 — Revisor
│   ├── __init__.py
│   ├── revisor.py
│   ├── grammar_checker.py
│   ├── style_checker.py
│   ├── seo_checker.py
│   └── Dockerfile
├── consolidador/              # Componente #7 — Consolidador
│   ├── __init__.py
│   ├── consolidador.py
│   ├── topic_detector.py
│   ├── rewriter.py
│   ├── merger.py
│   └── Dockerfile
├── curador_homepage/          # Componente #8 — Curador Homepage
│   ├── __init__.py
│   ├── curador.py
│   ├── scorer.py
│   ├── compositor.py
│   ├── layout_manager.py
│   ├── acf_applicator.py
│   └── Dockerfile
├── pauteiro/                  # Componente #9 — Pauteiro
│   ├── __init__.py
│   ├── pauteiro.py
│   ├── trend_scanner.py
│   ├── signal_aggregator.py
│   ├── briefing_generator.py
│   └── Dockerfile
├── editor_chefe/              # Componente #10 — Editor-Chefe
│   ├── __init__.py
│   ├── editor_chefe.py
│   ├── metrics_collector.py
│   ├── coverage_analyzer.py
│   ├── gap_detector.py
│   └── Dockerfile
├── monitor_concorrencia/      # Componente #11 — Monitor Concorrência
│   ├── __init__.py
│   ├── monitor.py
│   ├── portal_scanner.py
│   ├── tfidf_analyzer.py
│   ├── urgency_scorer.py
│   └── Dockerfile
├── monitor_sistema/           # Componente #12 — Monitor Sistema + Focas
│   ├── __init__.py
│   ├── monitor_sistema.py
│   ├── focas.py
│   ├── health_checker.py
│   ├── adaptive_polling.py
│   └── Dockerfile
├── migrations/                # Migrações SQL
│   ├── 001_schema_base.sql
│   ├── 002_pgvector.sql
│   └── 003_indices.sql
├── tests/                     # Testes por componente
│   ├── test_smart_router.py
│   ├── test_worker_pool.py
│   ├── ... (um por componente)
│   └── test_integration.py
└── docs/                      # Briefings de referência (copiados do workspace)
    ├── briefing-master.md
    ├── briefing-smart-llm-router-v3.md
    ├── briefing-worker-pool-coletores-v3.md
    ├── briefing-classificador-kafka-v3.md
    ├── briefing-reporter-v3.md
    ├── briefing-fotografo-v3.md
    ├── briefing-revisor-v3.md
    ├── briefing-consolidador-v3.md
    ├── briefing-curador-homepage-v3.md
    ├── briefing-pauteiro-v3.md
    ├── briefing-editor-chefe-v3.md
    ├── briefing-monitor-concorrencia-v3.md
    ├── briefing-monitor-focas-v3.md
    ├── context-engineering.md
    └── catalogo-modelos-llm-2026.md
```

## 13 Regras INVIOLÁVEIS

1. **Publicar primeiro, revisar depois.** Reporter publica direto com `status="publish"`. Sem draft. Sem gate de aprovação. NUNCA.
2. **100% das fontes processadas.** Nenhuma fonte ignorada. NUNCA desativar fonte. Focas ajusta frequência, nunca desativa.
3. **Nenhuma notícia sem imagem.** 4 tiers de fallback. Placeholder temático se tudo falhar. Zero posts sem featured_media.
4. **Homepage scoring com LLM PREMIUM.** Curador Homepage usa tier PREMIUM. Econômico para homepage é "erro grotesco".
5. **Image query generation com LLM PREMIUM.** Fotógrafo gera queries com tier PREMIUM, não econômico.
6. **Roteador inteligente, não engessado.** SmartLLMRouter escolhe o modelo mais apropriado por contexto. Sem hardcoding de modelos.
7. **Pauteiro NÃO é entry point.** Conteúdo flui independentemente de todas as fontes. Pauteiro gera pautas especiais em paralelo.
8. **Editor-Chefe NÃO é gatekeeper.** Observa métricas no FIM do pipeline. Nunca bloqueia publicação.
9. **Consolidador: 1 fonte → reescrever, 2+ fontes → consolidar.** Sem MIN_SOURCES=3. Portal Tier 1 não precisa de 3 fontes.
10. **Revisor NUNCA rejeita.** Corrige in-place no post já publicado via PATCH. Sem enum REJECT.
11. **Custo é INFORMAÇÃO, nunca bloqueio.** Token budgets são alertas informativos. NUNCA interrompem operação.
12. **Todos os agentes DEVEM ter memória** em 3 camadas: semântica (pgvector), episódica (PostgreSQL), working (Redis).
13. **Ingestão paralela, nunca sequencial.** Um erro em uma fonte NUNCA trava as demais. Workers independentes.

## Tópicos Kafka
| Tópico | Partições | Producers | Consumers |
|--------|-----------|-----------|-----------|
| `fonte-assignments` | por fonte_id | Feed Scheduler | Workers |
| `raw-articles` | por publisher_id | Workers | Classificador |
| `classified-articles` | por categoria | Classificador | Reporters |
| `article-published` | por post_id | Reporter | Fotógrafo, Revisor, Curador, Monitor |
| `pautas-especiais` | por editoria | Pauteiro | Reporters |
| `pautas-gap` | por urgência | Consolidador, Monitor Conc. | Reporters |
| `consolidacao` | por tema_id | Monitor Concorrência | Consolidador |
| `homepage-updates` | — | Curador | Monitor Sistema |
| `breaking-candidate` | — | Monitor Concorrência | Curador Homepage |

## Tiers LLM por Tarefa
| Tarefa (task_type) | Tier | Exemplos de Modelo |
|--------------------|------|--------------------|
| `redacao_artigo` | PREMIUM | Claude Opus 4, GPT-5.4, Gemini 3.1 Pro |
| `imagem_query` | PREMIUM | Claude Opus 4, GPT-5.4 |
| `homepage_scoring` | PREMIUM | Claude Opus 4, GPT-5.4 |
| `consolidacao_sintese` | PREMIUM | Claude Opus 4, GPT-5.4 |
| `pauta_especial` | PREMIUM | Claude Opus 4, GPT-5.4 |
| `seo_otimizacao` | PADRÃO | Claude Sonnet 4, GPT-4.1-mini, Gemini 2.5 Flash |
| `revisao_texto` | PADRÃO | Claude Sonnet 4, GPT-4.1-mini |
| `trending_detection` | PADRÃO | Claude Sonnet 4, Gemini 2.5 Flash |
| `analise_metricas` | PADRÃO | Claude Sonnet 4, GPT-4.1-mini |
| `classificacao_categoria` | ECONÔMICO | GPT-4.1-mini, Gemini 2.5 Flash, DeepSeek V3.2 |
| `extracao_entidades` | ECONÔMICO | GPT-4.1-mini, DeepSeek V3.2 |
| `deduplicacao_texto` | ECONÔMICO | Gemini 2.5 Flash, DeepSeek V3.2 |
| `monitoring_health` | ECONÔMICO | DeepSeek V3.2, Qwen 3.5 |

## WordPress Config
```env
WP_URL=https://brasileira.news
WP_USER=iapublicador
WP_AUTH=application_password  # em .env
WP_DB_HOST=localhost
WP_DB_NAME=bitnami_wordpress
WP_DB_PREFIX=wp_7_
WP_BLOG_ID=7
```

## 16 Macrocategorias
1. Política  2. Economia  3. Esportes  4. Tecnologia  5. Saúde  6. Educação
7. Ciência  8. Cultura/Entretenimento  9. Mundo/Internacional  10. Meio Ambiente
11. Segurança/Justiça  12. Sociedade  13. Brasil (geral)  14. Regionais
15. Opinião/Análise  16. Últimas Notícias (transversal)

## Ordem de Implementação (OBRIGATÓRIA)
1. `shared/` — Código compartilhado (config, clients, schemas, memory)
2. `smart_router/` — SmartLLMRouter (briefing: docs/briefing-smart-llm-router-v3.md)
3. `worker_pool/` — Worker Pool de Coletores (briefing: docs/briefing-worker-pool-coletores-v3.md)
4. `classificador/` — Classificador + Kafka Pipeline (briefing: docs/briefing-classificador-kafka-v3.md)
5. `reporter/` — Reporter (briefing: docs/briefing-reporter-v3.md)
6. `fotografo/` — Fotógrafo (briefing: docs/briefing-fotografo-v3.md)
7. `revisor/` — Revisor (briefing: docs/briefing-revisor-v3.md)
8. `consolidador/` — Consolidador (briefing: docs/briefing-consolidador-v3.md)
9. `curador_homepage/` — Curador Homepage (briefing: docs/briefing-curador-homepage-v3.md)
10. `pauteiro/` — Pauteiro (briefing: docs/briefing-pauteiro-v3.md)
11. `editor_chefe/` — Editor-Chefe (briefing: docs/briefing-editor-chefe-v3.md)
12. `monitor_concorrencia/` — Monitor Concorrência (briefing: docs/briefing-monitor-concorrencia-v3.md)
13. `monitor_sistema/` — Monitor Sistema + Focas (briefing: docs/briefing-monitor-focas-v3.md)

## Padrões de Código OBRIGATÓRIOS
- Python 3.12+ com type hints estritos
- Pydantic V2 para todos os schemas (model_config = ConfigDict(strict=True))
- asyncio nativo (sem sync wrappers)
- LangGraph StateGraph para cada agente
- Logging via `logging` (NUNCA print())
- Docstrings em português brasileiro
- Exceção tratada em CADA bloco I/O (nunca morrer por erro numa fonte)
- Retry com exponential backoff em toda chamada externa
- NUNCA hardcodar credenciais (tudo via .env)
- Testes com pytest (mínimo 80% de cobertura por componente)

## Referência ao Código V2 (PARA DIAGNÓSTICO, NÃO PARA COPIAR)
Os arquivos V2 estão no servidor em `/home/bitnami/` (raiz) e em `versao2/`. São REFERÊNCIA de bugs documentados nos briefings. NUNCA copie lógica V2 — cada briefing documenta exatamente o que estava errado e o que deve ser diferente na V3.

## Comandos Úteis
```bash
# Ativar venv
source /home/bitnami/venv/bin/activate

# Status da infraestrutura
docker compose -f docker-compose.infra.yml ps

# Logs de um componente
docker compose logs -f smart_router

# Testes
pytest tests/ -v --cov --cov-fail-under=80

# Kafka: verificar tópicos
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Redis: verificar chaves
redis-cli KEYS "*"

# PostgreSQL
psql -h localhost -U brasileira -d brasileira_v3
```
