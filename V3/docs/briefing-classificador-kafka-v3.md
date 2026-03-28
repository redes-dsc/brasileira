# Briefing Completo para IA — Classificador de Artigos + Kafka Pipeline V3

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #3 (Prioridade Alta)
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / aiokafka / sentence-transformers / spaCy / scikit-learn / Redis / PostgreSQL
**Componente:** `brasileira/classification/` — consumer Kafka, classificador ML, NER, relevance scorer, producer Kafka, DLQ

---

## LEIA ISTO PRIMEIRO — Por que este é o Componente #3

O Classificador de Artigos é o **cérebro de roteamento editorial do pipeline**. Ele fica entre o Worker Pool de Coletores (Componente #2) e o Worker Pool de Reporters (Componente #4). Sem ele, 1.000+ artigos/dia chegando no tópico Kafka `raw-articles` não chegam a lugar nenhum — ficam acumulados sem destino.

**Missão crítica:** Classificar CADA artigo em uma das 16 macrocategorias, extrair entidades nomeadas, calcular score de relevância/urgência, e publicar no tópico `classified-articles` em **menos de 200ms por artigo** — sem chamar nenhuma LLM (custo proibitivo para 1.000+ artigos/dia).

**Volume de produção:** 1.000 artigos/dia = ~42 artigos/hora = ~0,7 artigos/minuto em média. Mas o fluxo é BURST: às 8h, 12h e 18h (picos de publicação das fontes), o sistema pode receber 100-200 artigos em uma janela de 10 minutos. O classificador DEVE absorver esses picos sem bloqueio.

**Custo:** Chamar uma LLM para cada artigo a $0,07/1M tokens (econômico) com um prompt de ~500 tokens = $0,000035/artigo × 1.000 = $0,035/dia. Parece barato. Mas com 10.000+ artigos/dia = $0,35/dia = $127/ano só para classificação — enquanto ML local tem custo ZERO após setup. Além disso: latência de API (50-500ms) vs ML local (<10ms). O ML leve ganha em todos os critérios.

**Fallback LLM:** Quando o ML tem confiança < 0.6 (artigos ambíguos, interdisciplinares), aciona LLM ECONÔMICO via SmartLLMRouter. Custo real: apenas ~5-10% dos artigos = 50-100 chamadas LLM/dia. Absolutamente aceitável.

**Este briefing contém TUDO que você precisa para implementar o Classificador do zero.** Não consulte outros documentos. Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTAVA QUEBRADO NA V2

### 1.1 O Editor de Editoria — O Gate Que Matava a Produção

O arquivo `editor_editoria-9.py` (V2) era um **gatekeeper** que operava como 3º filtro no pipeline, ANTES do Reporter:

```
V2 (QUEBRADO):
Pauteiro → Editor-Chefe → Editor Editoria (gate) → Reporter (draft) → Revisor (rejeita)
= 0 artigos publicados
```

O `editor_editoria-9.py` tinha três falhas fatais:

**1. Apenas 4 editorias hardcoded:**
```python
# editor_editoria-9.py — estados do agente V2
class EditorialSection(str, Enum):
    POLITICA = "politica"
    ECONOMIA = "economia"
    ESPORTES = "esportes"
    TECNOLOGIA = "tecnologia"
# PROBLEMA: Brasil tem 16+ temas jornalísticos relevantes. Saúde? Educação? Meio Ambiente?
# Todos eram silenciosamente descartados ou mal classificados.
```

**2. Classificação via LLM (custo proibitivo):**
O agente usava LLM para classificar CADA artigo antes de qualquer coisa:
```python
# editor_editoria-9.py — linha ~180 (aproximado)
tier = LLMTier.PREMIUM  # PREMIUM para classificar! Crime contra o orçamento.
response = await gateway.complete(tier=tier, messages=[
    {"role": "system", "content": "Determine the editoria of this article"},
    {"role": "user", "content": article_content}
])
# 1.000 artigos/dia × chamada PREMIUM = destruição financeira
```

**3. Era um gate bloqueante:**
```python
# Se o Editor Editoria não aprovasse (e ele era seletivo), o artigo morria aqui.
# LangGraph state machine com estado "reject" que parava o pipeline.
states = ["receive", "plan", "assign_reporter", "review", "track"]
# "review" podia rejeitar artigos — menos publicação = portal morto
```

**Resultado V2:** Artigos de saúde, educação, meio ambiente, cultura, sociedade, segurança, ciência, mundo — nenhum tinha uma "casa" no sistema. Eram jogados numa vala comum ou descartados. O portal publicava (quando publicava) quase só Política, Economia, Esportes e Tecnologia.

### 1.2 Classificação no Motor Scrapers V2 — Rudimentar e Incorreta

O `motor_scrapers_v2.py` tinha uma função `calcular_relevancia()` (linhas 788-823) que tentava fazer scoring mas era fundamentalmente limitada:

```python
# motor_scrapers_v2.py — calcular_relevancia() — REFERÊNCIA DO QUE NÃO FAZER
_KEYWORDS = ["governo","presidente","ministro","congresso","senado","camara","stf",
             "economia","inflacao","pib","saude","educacao","tecnologia",
             "meio ambiente","reforma","lei","decreto","eleicao","seguranca",
             "investimento","mercado"]

_GRUPO_PESOS = {
    "governo":1.3, "reguladores":1.2, "legislativo":1.2,
    "judiciario":1.1, "nicho":1.0, "internacional":0.9
}

def calcular_relevancia(artigo):
    score = 50.0  # Baseline: TODO mundo começa com 50

    titulo = artigo.get("titulo","").lower()
    grupo = artigo.get("grupo","")

    score *= _GRUPO_PESOS.get(grupo, 1.0)

    if grupo in ("governo","reguladores","legislativo","judiciario"):
        score += SCORE_GOV_BONUS  # Bônus opaco, hardcoded

    score += min(sum(1 for kw in _KEYWORDS if kw in titulo) * 3, 15)
    # PROBLEMA 1: Lista de keywords ridiculamente pequena (21 palavras)
    # PROBLEMA 2: Só olha o título, ignora o corpo do artigo
    # PROBLEMA 3: Match simples de string, sem contexto semântico
    # PROBLEMA 4: Bias fortíssimo para notícias governamentais

    if len(titulo) < 30:
        score *= 0.8  # Penaliza títulos curtos — arbitrário sem evidência

    peso = artigo.get("peso", 3)
    if peso >= 5: score *= 1.2
    elif peso >= 4: score *= 1.1
    elif peso <= 1: score *= 0.8

    return round(min(score, 100), 2)
```

**Problemas críticos desta implementação:**

| Problema | Impacto |
|----------|---------|
| Keywords fixas de 21 palavras | Perde semântica completa de categorias como Cultura, Saúde, Ciência |
| Só analisa o título | Ignora 95% do conteúdo relevante para classificação |
| Sem classificação de categoria | Score de relevância ≠ categoria editorial |
| Bias para "governo" | Internacional, Esportes, Entretenimento recebem scores artificialmente baixos |
| Sem entidades nomeadas | Não identifica pessoas, organizações, locais — crucial para o Consolidador |
| Sem detecção de urgência | Breaking news tratada igual a análise de fundo |

### 1.3 Categorias V2 vs Necessidade V3

O arquivo `brasileira/motor_rss/config.py` definia 15 categorias WordPress:

```python
VALID_CATEGORIES = [
    "Segmentos de Tecnologia", "Política & Poder", "Saúde & Bem-Estar",
    "Economia & Negócios", "Meio Ambiente", "Segurança & Defesa",
    "Educação & Cultura", "Esportes", "Internacional", "Entretenimento",
    "Agronegócio", "Infraestrutura & Urbanismo", "Ciência & Inovação",
    "Direito & Justiça", "Energia & Clima",
]
```

Essas categorias existiam no WordPress, mas o código V2 **nunca as usava corretamente**:
- O editor_editoria só conhecia 4 delas
- O motor RSS escolhia categoria via prompt LLM livre (sem validação se a resposta estava na lista)
- Artigos eram publicados em categorias inválidas ou na categoria padrão do WordPress

**Na V3: 16 macrocategorias bem definidas com keywords, embeddings e regras específicas para cada uma.**

### 1.4 Ausência Total de NER na V2

Nenhum componente da V2 extraía entidades nomeadas (NER) de forma sistemática. O Consolidador (`consolidador-14.py`) tinha `MIN_SOURCES_PER_TOPIC = 3` mas **não tinha como encontrar artigos sobre o mesmo tema** de forma semântica — dependia de clustering frágil por palavras-chave.

Na V3: NER em tempo real com spaCy `pt_core_news_lg` para extrair PER, ORG, LOC, MISC de cada artigo. Essas entidades alimentam:
1. O Consolidador (agrupar artigos sobre mesmo tema/pessoa)
2. O sistema de tags WordPress
3. O Pauteiro (detectar quando uma entidade está em alta)
4. O Monitor de Concorrência (gap analysis semântico)

---

## PARTE II — ARQUITETURA DO CLASSIFICADOR V3

### 2.1 Visão Geral — Posição no Pipeline

```
[Kafka: raw-articles]
        │
        ▼
┌────────────────────────────────────────────────────────────────────┐
│  CLASSIFICADOR V3 (brasileira/classification/)                      │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ CONSUMER (classificador/consumer.py)                          │   │
│  │  • AIOKafkaConsumer — group_id: "classificador-group"         │   │
│  │  • Batch processing: até 50 msgs de uma vez                   │   │
│  │  • Manual commit após processamento confirmado                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                          │                                           │
│                          ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PIPELINE DE CLASSIFICAÇÃO (assíncrono, por artigo)            │   │
│  │                                                                │   │
│  │  1. Pré-processamento do texto                                 │   │
│  │      └── Limpeza HTML, normalização, extração título+corpo     │   │
│  │                                                                │   │
│  │  2. Classificador ML (ml_classifier.py)                        │   │
│  │      ├── Sentence embeddings (paraphrase-multilingual-MiniLM)  │   │
│  │      ├── Cosine similarity vs. protótipos de categoria         │   │
│  │      ├── Confiança ≥ 0.6 → usa resultado ML diretamente        │   │
│  │      └── Confiança < 0.6 → aciona LLM fallback (econômico)     │   │
│  │                                                                │   │
│  │  3. NER (ner_extractor.py)                                     │   │
│  │      └── spaCy pt_core_news_lg → PER, ORG, LOC, MISC           │   │
│  │                                                                │   │
│  │  4. Relevance Scorer (relevance_scorer.py)                     │   │
│  │      ├── Score 0-100 (fonte tier + frescor + entidades + kws)   │   │
│  │      └── Urgência: FLASH / NORMAL / ANÁLISE                    │   │
│  │                                                                │   │
│  │  5. Montagem do ClassifiedArticle                              │   │
│  │                                                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                          │                                           │
│                          ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PRODUCER (producer.py)                                        │   │
│  │  • AIOKafkaProducer → topic: classified-articles              │   │
│  │  • Partition key: categoria (garante ordering por editoria)   │   │
│  │  • Serialização: JSON + Schema Kafka                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                          │                                           │
│                          ├──────────────────────────────────────┐   │
│                          ▼                                       ▼   │
│  [Kafka: classified-articles]           [Kafka: dlq-articles]       │
│       (→ Reporter)                          (→ Monitoramento)        │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Princípios INVIOLÁVEIS do Classificador

1. **Sem LLM para artigos com confiança ≥ 0.6** — ML local, custo zero, latência <10ms
2. **Fallback LLM apenas para casos ambíguos** — Tier ECONÔMICO via SmartLLMRouter
3. **Sem hard cap de artigos** — fluxo contínuo, sem `MAX_ARTICLES_PER_CYCLE`
4. **Sem bloqueio do pipeline** — falha em 1 artigo não para os demais
5. **Commit manual Kafka** — só após processamento confirmado (at-least-once delivery)
6. **Todas as 16 macrocategorias suportadas** — sem lixo, sem "outros"
7. **DLQ para falhas** — artigos problemáticos vão para `dlq-articles`, nunca são descartados

### 2.3 Estrutura de Módulos

```
brasileira/
└── classification/
    ├── __init__.py
    ├── consumer.py           # AIOKafkaConsumer + orquestração do pipeline
    ├── ml_classifier.py      # Classificador ML com sentence-transformers
    ├── ner_extractor.py      # NER com spaCy pt_core_news_lg
    ├── relevance_scorer.py   # Scoring de relevância e urgência
    ├── producer.py           # AIOKafkaProducer para classified-articles
    ├── dlq_handler.py        # Dead Letter Queue management
    ├── schemas.py            # Modelos Pydantic (RawArticle, ClassifiedArticle)
    ├── text_processor.py     # Pré-processamento de texto
    ├── category_config.py    # Configuração das 16 macrocategorias
    ├── llm_fallback.py       # Integração com SmartLLMRouter para casos ambíguos
    └── metrics.py            # Prometheus metrics para o classificador
```

### 2.4 Tecnologias Usadas

| Componente | Biblioteca | Versão | Justificativa |
|-----------|------------|--------|---------------|
| Consumer Kafka | `aiokafka` | ≥0.10 | Async nativo, suporte a consumer groups |
| Producer Kafka | `aiokafka` | ≥0.10 | Mesma biblioteca, API unificada |
| ML Classificação | `sentence-transformers` | ≥3.0 | Embeddings multilíngues, offline, <10ms |
| Modelo de embedding | `paraphrase-multilingual-MiniLM-L12-v2` | — | 50+ idiomas incluindo pt, 384 dims, 117MB |
| NER | `spacy` + `pt_core_news_lg` | ≥3.7 | NER pt-BR, 90%+ F1, CPU-optimized |
| Pré-processamento | `beautifulsoup4` + `ftfy` | — | Limpeza HTML, normalização Unicode |
| Serialização | `pydantic` v2 | ≥2.0 | Schemas tipados, validação automática |
| Métricas | `prometheus-client` | ≥0.19 | Observabilidade por categoria |
| Fallback LLM | `SmartLLMRouter` | V3 | Componente #1 já implementado |

---

## PARTE III — ESPECIFICAÇÃO DO CONSUMER KAFKA

### 3.1 Configuração do Consumer

```python
# brasileira/classification/consumer.py

import asyncio
import json
import logging
from typing import AsyncIterator
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError, CommitFailedError

logger = logging.getLogger(__name__)

CONSUMER_CONFIG = {
    "bootstrap_servers": "kafka:9092",           # Via env: KAFKA_BOOTSTRAP_SERVERS
    "group_id": "classificador-group",           # Consumer group para scaling horizontal
    "auto_offset_reset": "earliest",             # Reprocessa desde o início se sem offset
    "enable_auto_commit": False,                 # OBRIGATÓRIO: commit manual após processamento
    "max_poll_records": 50,                      # Máximo 50 msgs por poll (batching)
    "fetch_max_wait_ms": 500,                    # Aguarda até 500ms para encher o batch
    "session_timeout_ms": 30_000,               # 30s sem heartbeat → rebalance
    "heartbeat_interval_ms": 10_000,            # Heartbeat a cada 10s
    "max_poll_interval_ms": 300_000,            # 5 min max para processar um batch
    "value_deserializer": lambda v: json.loads(v.decode("utf-8")),
    "key_deserializer": lambda k: k.decode("utf-8") if k else None,
}
```

### 3.2 Loop Principal do Consumer

```python
# brasileira/classification/consumer.py (continuação)

from brasileira.classification.pipeline import ClassificationPipeline
from brasileira.classification.schemas import RawArticle
from brasileira.classification.dlq_handler import DLQHandler
from brasileira.classification.metrics import ClassifierMetrics

class ClassificadorConsumer:
    """
    Consumer Kafka para o tópico raw-articles.
    Processa artigos em batches, classifica e produz para classified-articles.
    """

    def __init__(self, pipeline: ClassificationPipeline, dlq: DLQHandler,
                 metrics: ClassifierMetrics):
        self.pipeline = pipeline
        self.dlq = dlq
        self.metrics = metrics
        self.consumer: AIOKafkaConsumer = None
        self._running = False

    async def start(self):
        """Inicia o consumer e começa a processar mensagens."""
        self.consumer = AIOKafkaConsumer(
            "raw-articles",
            **CONSUMER_CONFIG
        )
        await self.consumer.start()
        self._running = True
        logger.info("Classificador Consumer iniciado — aguardando artigos em raw-articles")

        try:
            await self._consume_loop()
        finally:
            await self.consumer.stop()
            logger.info("Classificador Consumer encerrado")

    async def stop(self):
        """Sinaliza parada graceful."""
        self._running = False

    async def _consume_loop(self):
        """Loop principal de consumo com processamento paralelo de batch."""
        async for msg_batch in self._batch_generator():
            if not msg_batch:
                continue

            # Processa todos os artigos do batch em paralelo (asyncio.gather)
            tasks = []
            for msg in msg_batch:
                tasks.append(self._process_message(msg))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Conta sucessos e falhas
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            fail_count = len(results) - success_count

            if fail_count > 0:
                logger.warning(f"Batch processado: {success_count} OK, {fail_count} falhas (DLQ)")

            self.metrics.batch_processed(total=len(msg_batch), success=success_count, fail=fail_count)

            # COMMIT MANUAL — só após processamento completo do batch
            try:
                await self.consumer.commit()
            except CommitFailedError as e:
                # Rebalance aconteceu durante processamento — normal, não é erro fatal
                logger.warning(f"Commit falhou (rebalance?): {e}")

    async def _batch_generator(self) -> AsyncIterator[list]:
        """Gera batches de mensagens do consumer."""
        while self._running:
            try:
                # getmany retorna dict[TopicPartition, list[ConsumerRecord]]
                batch_dict = await self.consumer.getmany(
                    timeout_ms=1000,
                    max_records=50
                )
                # Flatten: todas as partições em uma lista única
                all_msgs = []
                for msgs in batch_dict.values():
                    all_msgs.extend(msgs)

                if all_msgs:
                    yield all_msgs
                else:
                    # Sem mensagens — aguarda um pouco para não spinloop
                    await asyncio.sleep(0.1)

            except KafkaError as e:
                logger.error(f"Erro Kafka no consumer: {e}")
                await asyncio.sleep(5)  # Backoff antes de tentar novamente
            except Exception as e:
                logger.error(f"Erro inesperado no consumer loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _process_message(self, msg) -> None:
        """Processa uma única mensagem Kafka."""
        import time
        start_time = time.monotonic()

        try:
            # Desserializa e valida
            raw_data = msg.value
            article = RawArticle.model_validate(raw_data)

            # Executa o pipeline de classificação
            classified = await self.pipeline.classify(article)

            # Produz para classified-articles
            await self.pipeline.producer.send(classified)

            elapsed_ms = (time.monotonic() - start_time) * 1000
            self.metrics.article_classified(
                categoria=classified.categoria,
                latency_ms=elapsed_ms,
                method=classified.classification_method
            )
            logger.debug(
                f"Artigo classificado: '{article.titulo[:60]}' → {classified.categoria} "
                f"(conf={classified.categoria_confidence:.2f}, {elapsed_ms:.0f}ms)"
            )

        except Exception as e:
            logger.error(f"Falha ao classificar artigo (offset={msg.offset}): {e}", exc_info=True)
            # Envia para DLQ — NUNCA descarta silenciosamente
            await self.dlq.send(msg, error=str(e))
            self.metrics.article_failed(reason=type(e).__name__)
```

### 3.3 Rebalance Listener

```python
# brasileira/classification/consumer.py (continuação)

from aiokafka import ConsumerRebalanceListener

class ClassificadorRebalanceListener(ConsumerRebalanceListener):
    """
    Handler de rebalance de partições.
    Garante que offsets pendentes são commitados antes da revogação.
    """

    def __init__(self, consumer: AIOKafkaConsumer):
        self.consumer = consumer

    async def on_partitions_revoked(self, revoked: list):
        """Chamado ANTES de revogar partições durante rebalance."""
        if revoked:
            logger.info(f"Partições sendo revogadas: {revoked}. Commitando offsets...")
            try:
                await self.consumer.commit()
                logger.info("Offsets commitados antes do rebalance")
            except Exception as e:
                logger.warning(f"Erro ao commitar antes do rebalance: {e}")

    async def on_partitions_assigned(self, assigned: list):
        """Chamado APÓS receber novas partições."""
        logger.info(f"Novas partições atribuídas: {assigned}")
```

### 3.4 Configuração do Tópico `raw-articles`

O Componente #2 (Worker Pool) produz para `raw-articles`. O Classificador consome deste tópico com as seguintes características:

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Partitions | 16 | 1 por macrocategoria (permite scaling por editoria) |
| Replication Factor | 2 | Alta disponibilidade |
| Retention | 24h | Artigos têm validade de 1 dia |
| Partition Key | `publisher_id` | Artigos da mesma fonte no mesmo consumer |
| Max Message Size | 1MB | Artigos com conteúdo HTML podem ser grandes |

---

## PARTE IV — ESPECIFICAÇÃO DO CLASSIFICADOR ML

### 4.1 Estratégia de Classificação — Zero-Shot com Protótipos

A abordagem escolhida é **zero-shot classification via embeddings semânticos**:
1. Cada macrocategoria tem um conjunto de **frases prototípicas** em português
2. O modelo gera embeddings dessas frases e calcula um **centróide** por categoria
3. Para classificar um artigo: gera embedding do título+lide → cosine similarity vs. todos os centróides
4. A categoria com maior cosine similarity ganha

**Por que esta abordagem vs. alternativas:**

| Abordagem | Prós | Contras | Escolha |
|-----------|------|---------|---------|
| Zero-shot com embeddings | Sem treino, atualização fácil, funciona bem com frases prototípicas | Menos preciso que modelo fine-tuned | ✅ **Escolhida** |
| BERTimbau fine-tuned | Alta precisão (>95% com dados suficientes) | Requer dataset rotulado, setup GPU, deploy complexo | ❌ |
| fastText supervisioned | Muito rápido (0.1ms), peso leve | Requer dataset rotulado em pt, sem contexto semântico | ❌ |
| TF-IDF + SVM | Simples, interpretável | Sem semântica, vocabulário fixo, ruim para novos termos | ❌ |
| Prompt LLM | Altíssima precisão | Custo proibitivo: ~$0,035/dia escalável para $127/ano | ❌ (apenas fallback) |

### 4.2 Modelo: `paraphrase-multilingual-MiniLM-L12-v2`

```python
# brasileira/classification/ml_classifier.py

from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import logging

logger = logging.getLogger(__name__)

# Modelo multilingue leve: 117MB, suporta 50+ idiomas incluindo pt-BR
# Dimensão: 384. Velocidade: ~1ms/artigo em CPU. F1 zero-shot: ~85% pt-BR.
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# Alternativa se modelo acima não disponível:
# MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
# (768 dims, melhor qualidade, mais lento e pesado — 970MB)
```

### 4.3 Configuração das 16 Macrocategorias com Protótipos

```python
# brasileira/classification/category_config.py

"""
Configuração das 16 macrocategorias V3 com frases prototípicas em português.
Os protótipos são usados para gerar embeddings centróide de cada categoria.

REGRA: Mínimo 10 frases prototípicas por categoria para qualidade de centróide.
REGRA: Frases devem cobrir diferentes aspectos da categoria (não apenas sinônimos).
REGRA: Frases em português brasileiro natural, sem jargão excessivo.
"""

CATEGORY_PROTOTYPES: dict[str, list[str]] = {

    "politica": [
        "presidente da república assinou medida provisória no palácio do planalto",
        "câmara dos deputados aprovou projeto de lei por maioria",
        "senado federal votou a favor da proposta de emenda constitucional",
        "ministro explicou decisão do governo em coletiva de imprensa",
        "eleições municipais definem prefeitos em todo o brasil",
        "partido político lançou candidato para as próximas eleições",
        "oposição criticou medida do governo federal",
        "congresso nacional rejeitou veto presidencial ao orçamento",
        "supremo tribunal federal julgou ação de inconstitucionalidade",
        "governador decretou estado de calamidade no estado",
        "deputado federal propôs projeto de lei para regulamentar setor",
        "ministério da fazenda anunciou nova política econômica fiscal",
        "petição popular colheu assinaturas contra projeto controverso",
        "comissão parlamentar de inquérito investigou irregularidades",
        "vice-presidente representou brasil em reunião diplomática internacional",
    ],

    "economia": [
        "banco central elevou a taxa selic para controlar inflação",
        "pib do brasil cresceu no segundo trimestre segundo ibge",
        "índice de desemprego caiu de acordo com pesquisa do ibge",
        "bolsa de valores registrou alta expressiva impulsionada por ações",
        "dólar fechou em alta frente ao real no mercado de câmbio",
        "empresa brasileira anunciou investimento bilionário em expansão",
        "inflação medida pelo ipca ficou abaixo da meta do banco central",
        "agronegócio brasileiro bateu recorde de exportações no semestre",
        "startups brasileiras captaram investimentos de venture capital",
        "fusão entre grandes empresas foi aprovada pelo cade",
        "reforma tributária impacta pequenas e médias empresas nacionais",
        "mercado financeiro reagiu positivamente ao anúncio do governo",
        "produção industrial cresceu segundo dados do ibge",
        "comércio exterior registrou superávit na balança comercial",
        "crise no setor bancário preocupa investidores internacionais",
    ],

    "esportes": [
        "brasil venceu jogo pelo campeonato mundial de futebol",
        "flamengo derrotou o palmeiras no campeonato brasileiro de futebol",
        "atleta olímpico brasileiro conquistou medalha de ouro nos jogos",
        "seleção brasileira se classificou para a copa do mundo",
        "técnico da equipe nacional convocou jogadores para amistoso",
        "tenista brasileiro avançou às semifinais do torneio internacional",
        "fórmula um corrida em são paulo reuniu milhares de torcedores",
        "nadador quebrou recorde mundial em competição internacional",
        "vôlei feminino do brasil conquistou título sul-americano",
        "clube anunciou contratação de atacante por valor milionário",
        "basquete nba jogador brasileiro assinou contrato com time americano",
        "maratona de são paulo reuniu atletas de todo o mundo",
        "ciclismo brasileiro brilhou em etapa da vuelta espanhola",
        "futebol feminino seleção brasileira disputou final do torneio",
        "árbitro expulsou jogador em partida polémica do brasileirão",
    ],

    "tecnologia": [
        "inteligência artificial transforma indústria com automação avançada",
        "empresa de tecnologia lançou novo smartphone com recursos inovadores",
        "startup brasileira desenvolveu aplicativo revolucionário para mercado",
        "segurança cibernética vazamento de dados afetou milhões de usuários",
        "brasil aprovou lei de proteção de dados pessoais lgpd regulamentação",
        "computação quântica avança com novo processador desenvolvido por pesquisadores",
        "redes 5g chegam às principais cidades brasileiras com alta velocidade",
        "plataforma digital brasileira expandiu operações para outros países",
        "robótica industrial automatizou fábrica no estado de são paulo",
        "algoritmo de machine learning prevê doenças com alta precisão",
        "blockchain tecnologia descentralizada usada em transações financeiras",
        "metaverso empresas investem em realidade virtual e aumentada",
        "anatel regulamentou uso de frequências para serviços de internet",
        "bitcoin criptomoeda atingiu nova máxima histórica no mercado",
        "deep learning modelo de linguagem natural impressiona especialistas",
    ],

    "saude": [
        "ministério da saúde anunciou campanha de vacinação em todo brasil",
        "sus sistema único de saúde amplia atendimento em hospitais públicos",
        "pesquisadores brasileiros desenvolveram vacina contra doença tropical",
        "anvisa aprovou novo medicamento para tratamento de câncer",
        "epidemia de dengue preocupa autoridades sanitárias em cidades",
        "hospital universitário realizou cirurgia inovadora com robô médico",
        "estudo clínico descobriu tratamento mais eficaz para diabetes",
        "saúde mental pandemia aumentou casos de ansiedade e depressão",
        "plano de saúde privado deve cobrir procedimento conforme resolução",
        "farmácia popular disponibiliza remédios gratuitos para população",
        "oms organização mundial da saúde alertou para surto global de gripe",
        "médicos residentes fizeram greve por melhores condições de trabalho",
        "telemedicina consulta médica online expandiu durante isolamento social",
        "doação de órgãos campanha incentiva cadastro de doadores no brasil",
        "nutrição pesquisa aponta benefícios de dieta mediterrânea para saúde",
    ],

    "educacao": [
        "ministério da educação anunciou novo programa para escolas públicas",
        "enem resultados do exame nacional foram divulgados pelo inep",
        "universidade federal abriu inscrições para vestibular unificado",
        "mec avaliou desempenho de faculdades particulares no brasil",
        "professores fizeram greve por reajuste salarial nas redes municipais",
        "programa bolsa família inclui requisito de frequência escolar filhos",
        "tecnologia ensino híbrido combina aulas presenciais com online",
        "pesquisa científica universidade recebeu financiamento para inovação",
        "analfabetismo brasil ainda enfrenta desafio de educação básica",
        "reforma curricular mec propõe mudanças no ensino fundamental",
        "prouni programa oferece bolsas em faculdades privadas para estudantes",
        "olimpíada brasileira matemática premiou alunos do ensino médio",
        "educação especial inclusão de alunos com deficiência nas escolas",
        "livro didático distribuição gratuita nas escolas públicas do país",
        "fies financiamento estudantil amplia acesso ao ensino superior privado",
    ],

    "ciencia": [
        "pesquisadores brasileiros descobriram nova espécie na floresta amazônica",
        "nasa exploração espacial divulgou imagens inéditas do universo",
        "estudo científico publicado em revista nature revelou descoberta",
        "mudanças climáticas relatório do ipcc alerta para aquecimento global",
        "embrapa desenvolveu nova variedade de soja resistente à seca",
        "fapesp financiou pesquisa em biotecnologia na universidade de são paulo",
        "geologia pesquisadores mapearam reservas de minerais no brasil",
        "paleontologia fóssil de dinossauro inédito foi encontrado no mato grosso",
        "astronomia telescópio james webb captou imagens de galáxias distantes",
        "genética sequenciamento dna revelou origem de população indígena",
        "neurociência estudo mapeou funcionamento do cérebro humano em detalhes",
        "física quântica experimento confirmou teoria sobre comportamento partículas",
        "bioinformática algoritmo analisa genoma para personalizar tratamentos",
        "oceanografia pesquisa identificou espécies marinhas ameaçadas no litoral",
        "zoologia pesquisador brasileiro descreveu comportamento inédito de primatas",
    ],

    "cultura_entretenimento": [
        "show internacional trouxe artista estrangeiro para turnê no brasil",
        "filme brasileiro foi selecionado para o festival de cannes",
        "emicida lançou novo álbum com colaborações de artistas nacionais",
        "teatro peça encenada no rio de janeiro recebeu crítica positiva",
        "carnaval desfile das escolas de samba foi transmitido na televisão",
        "livro romance nacional ganhou prêmio literário jabuti",
        "música sertaneja artista bateu recorde de streams no spotify",
        "grammy americano premiou cantora brasileira em cerimônia nova york",
        "museu exposição de arte contemporânea atraiu visitantes em são paulo",
        "netflix série brasileira alcançou topo das mais assistidas no mundo",
        "celebridade influencer digital divulgou polêmica nas redes sociais",
        "cinema blockbuster de hollywood estreou nas salas brasileiras",
        "festival gastronomia reúne chefs renomados em cidade turística",
        "moda semana brasileira desfiles apresentaram coleção para próxima temporada",
        "humor stand up comediante lotou teatro com novo espetáculo",
    ],

    "mundo_internacional": [
        "conflito armado no oriente médio deixou mortos e feridos civis",
        "estados unidos anunciaram novas sanções contra país estrangeiro",
        "união europeia aprovou regulamentação sobre inteligência artificial",
        "china e eua tensão comercial escalou com imposição de tarifas",
        "onu assembleia geral debateu crise humanitária em país africano",
        "otan aliança militar expandiu fronteiras com novo país membro",
        "eleições presidenciais em país europeu definiram novo governo",
        "fmi fundo monetário internacional revisou projeções de crescimento",
        "acordo climático países assinaram tratado para redução emissões",
        "crise migratória onda de refugiados cruzou fronteiras europeias",
        "diplomacia brasil mediou acordo de paz entre nações em conflito",
        "terrorismo ataque reivindicado por grupo extremista causou vítimas",
        "mercosuL bloco econômico sul-americano assinou acordo comercial",
        "pandemia oms alertou para surgimento de novo vírus preocupante",
        "golpe militar governo deposto em país latino-americano por militares",
    ],

    "meio_ambiente": [
        "desmatamento amazônia atingiu recorde histórico em relatório oficial",
        "incêndios florestais destruíram hectares de vegetação nativa no pantanal",
        "copa2020 acordo climático paris metas de emissões carbono não cumpridas",
        "energia solar investimentos em fontes renováveis cresceram no brasil",
        "poluição do rio tietê preocupa autoridades ambientais de são paulo",
        "extinção espécies animais listadas em perigo pelo ibama e icmbio",
        "agricultura orgânica produtores migram para práticas sustentáveis",
        "enchente chuvas intensas causaram destruição em cidade do sul do brasil",
        "seca rio são francisco atingiu nível mais baixo em décadas",
        "parque nacional amazônico expandiu área de proteção ambiental",
        "plástico oceano pesquisa revelou concentração de microplásticos em peixes",
        "reflorestamento programa plantou milhões de árvores em área degradada",
        "eólica offshore instalação de parques eólicos no litoral nordestino",
        "lixo eletrônico brasil enfrenta desafio de destinação correta de resíduos",
        "agrotóxico uso em lavouras gerou debate sobre saúde de trabalhadores",
    ],

    "seguranca_justica": [
        "polícia federal deflagrou operação contra tráfico de drogas",
        "preso chefe de facção criminosa capturado após anos foragido",
        "stf supremo tribunal federal julgou habeas corpus de réu condenado",
        "assassinato investigação policial revelou motivação de crime hediondo",
        "assalto banco criminosos roubaram agência usando explosivos no nordeste",
        "homicídio índice de violência caiu em metrópoles brasileiras",
        "tráfico de pessoas operação internacional desarticulou rede criminosa",
        "corrupção delegado indiciado por receber propina de empresa",
        "lavagem de dinheiro réu foi condenado por esquema milionário",
        "defesa civil alertou sobre risco de enchentes em regiões serranas",
        "sistema penitenciário superlotação em presídios preocupa autoridades",
        "mandado de prisão expedido contra ex-governador acusado de peculato",
        "acidente de trânsito caminhão tombado bloqueou rodovia federal",
        "perito forense laudo comprovou participação de suspeito em crime",
        "ministério público denunciou empresário por fraude licitatória",
    ],

    "sociedade": [
        "pesquisa ibge revelou dados sobre condições de vida da população",
        "movimento social protestou nas ruas contra política governamental",
        "desigualdade social relatório aponta concentração de renda no brasil",
        "reforma previdência impacto nas aposentadorias de trabalhadores",
        "crise habitacional falta de moradia atinge famílias de baixa renda",
        "violência doméstica delegacia de mulheres registrou aumento de casos",
        "comunidade lgbtqia parada do orgulho reuniu milhões em são paulo",
        "racismo campanha combate discriminação racial no mercado de trabalho",
        "povos indígenas luta pela demarcação de terras tradicionais",
        "fome programa emergencial distribuiu alimentos a famílias vulneráveis",
        "imigrantes brasileiros comunidade no exterior enfrenta dificuldades",
        "religião censo revelar crescimento de evangélicos e queda de católicos",
        "idosos terceira idade demografias mostram envelhecimento da população",
        "criança adolescente programa social ofereceu vagas em atividades extracurriculares",
        "voluntariado organização social mobilizou jovens para ação comunitária",
    ],

    "brasil_geral": [
        "brasil celebrou data nacional com eventos em todo o território",
        "região norte enfrenta desafios de desenvolvimento econômico e social",
        "nordeste brasileiro recebe investimentos em infraestrutura hídrica",
        "amazônia legal políticas públicas para desenvolvimento sustentável",
        "copa do brasil jogo definiu finalistas da competição nacional",
        "censo demográfico ibge publicou dados sobre crescimento populacional",
        "identidade brasileira diversidade cultural une povo de norte a sul",
        "carnaval festa nacional movimentou bilhões na economia turística",
        "aviação civil anac aprovou nova norma para companhias aéreas",
        "correios empresa pública reestruturou serviços de entrega postal",
        "caixa econômica lançou programa de financiamento habitacional",
        "petrobras pré-sal produção de petróleo atingiu novo recorde diário",
        "vale mineração empresa anunciou investimento em projetos na região norte",
        "embratel telecomunicações expandiu fibra óptica para cidades menores",
        "sebrae apoiou empreendedores em programa de microcrédito nacional",
    ],

    "regionais": [
        "são paulo prefeito anunciou obras de infraestrutura na capital",
        "rio de janeiro estado enfrenta crise fiscal no governo",
        "minas gerais governador inaugurou hospital regional no interior",
        "rio grande do sul enchentes devastaram cidades do sul do país",
        "ceará seca flagelo histórico afeta produção rural no nordeste",
        "bahia carnaval de salvador reuniu turistas de todo o mundo",
        "amazon manaus polo industrial zona franca registrou crescimento",
        "pará belém sediará conferência climática internacional",
        "santa catarina blumenau cidade alemã preserva cultura europeia",
        "goiás brasília governo do distrito federal ampliou transporte público",
        "paraná curitiba cidade foi eleita a mais arborizada do brasil",
        "pernambuco recife tecnologia hub de inovação no nordeste brasileiro",
        "espírito santo vitória porto exportou minério de ferro recorde",
        "mato grosso agronegócio estado lidera produção de soja no país",
        "rondônia fronteira agrícola expandiu sobre floresta nativa",
    ],

    "opiniao_analise": [
        "colunista analisou impacto da reforma tributária na classe média",
        "editorial do jornal criticou decisão do governo sobre política social",
        "artigo de opinião defendeu mudança na legislação trabalhista",
        "análise especialista avaliou perspectivas da economia brasileira",
        "debate intelectual sobre o papel do estado na economia nacional",
        "comentarista político fez análise da situação parlamentar",
        "pesquisador publicou artigo sobre tendências eleitorais no brasil",
        "ex-ministro escreveu artigo sobre reforma da previdência social",
        "carta aberta professores universitários manifesto sobre educação",
        "coluna semanalmente reflete sobre temas da política internacional",
        "ensaio jornalístico investigativo revelou bastidores de escândalo",
        "tribuna livre cidadão defendeu causa ambiental no espaço público",
        "crítica cultural avaliou tendências das artes visuais contemporâneas",
        "perspectiva econômica analista previu cenário para próximo semestre",
        "panorama político jornalista descreveu disputa eleitoral regional",
    ],

    "ultimas_noticias": [
        "urgente breaking news aconteceu agora há pouco em brasília",
        "alerta ao vivo cobertura em tempo real de evento importante",
        "última hora decisão foi tomada há minutos com impacto nacional",
        "plantão notícia de última hora sobre situação em andamento",
        "direto do local repórter acompanha ocorrência ao vivo",
        "edição extra jornal publicou boletim urgente sobre crise",
        "informação atualizada situação evolui rapidamente segundo fontes",
        "boletim informativo autoridade se pronunciou sobre emergência",
        "notícia quente reportagem mostrou cenas do evento que acabou de ocorrer",
        "hard news factual acontecimento de extrema relevância pública",
        "alerta máximo autoridades convocaram reunião de emergência imediata",
        "exclusivo imprensa divulgou documento inédito com informações cruciais",
        "atualização redação confirmou segunda versão do ocorrido",
        "cronograma ao vivo acompanhe minuto a minuto os desdobramentos",
        "ao vivo transmissão especial cobre evento de grande impacto nacional",
    ],
}

# Mapeamento de categoria interna → WordPress Category ID
# Estes IDs devem ser configurados conforme o banco WordPress do site
CATEGORY_WP_IDS: dict[str, int] = {
    "politica": 2,
    "economia": 3,
    "esportes": 4,
    "tecnologia": 5,
    "saude": 6,
    "educacao": 7,
    "ciencia": 8,
    "cultura_entretenimento": 9,
    "mundo_internacional": 10,
    "meio_ambiente": 11,
    "seguranca_justica": 12,
    "sociedade": 13,
    "brasil_geral": 14,
    "regionais": 15,
    "opiniao_analise": 16,
    "ultimas_noticias": 1,  # Categoria padrão WordPress
}

# Labels display em português (para UI e logs)
CATEGORY_LABELS: dict[str, str] = {
    "politica": "Política",
    "economia": "Economia",
    "esportes": "Esportes",
    "tecnologia": "Tecnologia",
    "saude": "Saúde",
    "educacao": "Educação",
    "ciencia": "Ciência",
    "cultura_entretenimento": "Cultura & Entretenimento",
    "mundo_internacional": "Mundo/Internacional",
    "meio_ambiente": "Meio Ambiente",
    "seguranca_justica": "Segurança & Justiça",
    "sociedade": "Sociedade",
    "brasil_geral": "Brasil (Geral)",
    "regionais": "Regionais",
    "opiniao_analise": "Opinião & Análise",
    "ultimas_noticias": "Últimas Notícias",
}
```

### 4.4 Implementação do Classificador ML

```python
# brasileira/classification/ml_classifier.py

import asyncio
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from brasileira.classification.category_config import (
    CATEGORY_PROTOTYPES, CATEGORY_LABELS
)
from brasileira.classification.schemas import ClassificationResult

logger = logging.getLogger(__name__)

# Caminho para cachear os embeddings de protótipos (evita recalcular a cada startup)
PROTOTYPE_CACHE_PATH = Path("/tmp/clasificador_prototypes.pkl")

CONFIDENCE_THRESHOLD = 0.6  # Abaixo disso → fallback LLM


class MLClassifier:
    """
    Classificador ML leve usando sentence-transformers.

    Abordagem: Zero-shot com embeddings de protótipos.
    - Gera centróides de embedding para cada categoria usando frases prototípicas.
    - Classifica artigos por cosine similarity do embedding do texto vs centróides.
    - Latência: <10ms por artigo em CPU.
    - Sem dataset de treino necessário.
    - Atualização fácil: adicionar/modificar protótipos em category_config.py.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self.model: Optional[SentenceTransformer] = None
        self.category_centroids: dict[str, np.ndarray] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Carrega o modelo e calcula os centróides. Chame uma vez no startup."""
        logger.info(f"Inicializando MLClassifier com modelo {self.model_name}...")

        # Carrega modelo em thread separada (operação bloqueante)
        loop = asyncio.get_event_loop()
        self.model = await loop.run_in_executor(
            None,
            lambda: SentenceTransformer(self.model_name)
        )
        logger.info(f"Modelo {self.model_name} carregado ({self.model.get_sentence_embedding_dimension()} dims)")

        # Tenta carregar centróides do cache
        if PROTOTYPE_CACHE_PATH.exists():
            try:
                with open(PROTOTYPE_CACHE_PATH, "rb") as f:
                    cached = pickle.load(f)
                    if cached.get("model_name") == self.model_name:
                        self.category_centroids = cached["centroids"]
                        logger.info(f"Centróides carregados do cache ({len(self.category_centroids)} categorias)")
                        self._initialized = True
                        return
            except Exception as e:
                logger.warning(f"Cache de centróides inválido, recalculando: {e}")

        # Calcula centróides dos protótipos
        await self._compute_centroids()
        self._initialized = True
        logger.info("MLClassifier inicializado com sucesso")

    async def _compute_centroids(self) -> None:
        """Calcula o centróide de embedding para cada categoria."""
        logger.info("Calculando centróides das categorias...")

        loop = asyncio.get_event_loop()

        for category, prototypes in CATEGORY_PROTOTYPES.items():
            # Gera embeddings de todos os protótipos da categoria
            embeddings = await loop.run_in_executor(
                None,
                lambda p=prototypes: self.model.encode(p, normalize_embeddings=True)
            )
            # Centróide = média dos embeddings (já normalizados)
            centroid = np.mean(embeddings, axis=0)
            # Renormaliza o centróide
            centroid = centroid / np.linalg.norm(centroid)
            self.category_centroids[category] = centroid

        # Salva no cache
        try:
            with open(PROTOTYPE_CACHE_PATH, "wb") as f:
                pickle.dump({
                    "model_name": self.model_name,
                    "centroids": self.category_centroids
                }, f)
            logger.info(f"Centróides salvos em {PROTOTYPE_CACHE_PATH}")
        except Exception as e:
            logger.warning(f"Não foi possível salvar cache de centróides: {e}")

    async def classify(
        self,
        titulo: str,
        conteudo: str = "",
        fonte_categoria_hint: str = ""  # Dica do Worker Pool, se disponível
    ) -> ClassificationResult:
        """
        Classifica um artigo e retorna categoria + score de confiança.

        Args:
            titulo: Título do artigo
            conteudo: Primeiros 500 caracteres do corpo (opcional, melhora precisão)
            fonte_categoria_hint: Categoria sugerida pela fonte (ex: feed RSS de saúde)

        Returns:
            ClassificationResult com categoria, confiança e todas as pontuações
        """
        if not self._initialized:
            raise RuntimeError("MLClassifier não inicializado. Chame initialize() primeiro.")

        # Monta texto de entrada: título tem peso 3x, conteudo 1x
        # Justificativa: título é o sinal mais forte de categoria
        input_text = f"{titulo}. {titulo}. {titulo}. {conteudo[:500]}"

        # Gera embedding do artigo
        loop = asyncio.get_event_loop()
        article_embedding = await loop.run_in_executor(
            None,
            lambda: self.model.encode([input_text], normalize_embeddings=True)[0]
        )

        # Calcula cosine similarity vs. todos os centróides
        scores: dict[str, float] = {}
        for category, centroid in self.category_centroids.items():
            sim = float(cosine_similarity(
                article_embedding.reshape(1, -1),
                centroid.reshape(1, -1)
            )[0][0])
            scores[category] = sim

        # Ordena por score
        sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_category, best_score = sorted_categories[0]
        second_category, second_score = sorted_categories[1]

        # Aplica dica de categoria da fonte (boost de 0.05 se consistente)
        if fonte_categoria_hint and fonte_categoria_hint in scores:
            hint_score = scores[fonte_categoria_hint]
            if hint_score > best_score * 0.85:  # Fonte só vence se estiver próxima
                best_category = fonte_categoria_hint
                best_score = hint_score + 0.05  # Boost por consistência com fonte

        # Calcula margem de separação (gap entre 1º e 2º lugar)
        margin = best_score - second_score

        # Confiança final: combina score absoluto + margem de separação
        # Score alto + margem alta = certeza. Score alto + margem baixa = ambíguo.
        confidence = best_score * 0.7 + min(margin * 5, 0.3)

        return ClassificationResult(
            categoria=best_category,
            confianca=confidence,
            best_score=best_score,
            second_category=second_category,
            second_score=second_score,
            margin=margin,
            all_scores=scores,
            method="ml_zero_shot"
        )
```

### 4.5 Fallback LLM para Confiança Baixa

```python
# brasileira/classification/llm_fallback.py

import logging
from brasileira.llm.smart_router import SmartLLMRouter
from brasileira.classification.category_config import CATEGORY_LABELS
from brasileira.classification.schemas import ClassificationResult

logger = logging.getLogger(__name__)

FALLBACK_PROMPT_TEMPLATE = """Você é um editor de notícias especializado em categorização editorial.
Classifique o artigo abaixo em EXATAMENTE UMA das categorias listadas.
Responda APENAS com o slug da categoria, sem explicações.

CATEGORIAS DISPONÍVEIS:
{categories}

ARTIGO:
Título: {titulo}
Texto: {conteudo_preview}

RESPOSTA (apenas o slug da categoria):"""


class LLMFallbackClassifier:
    """
    Classificador de fallback usando LLM ECONÔMICO via SmartLLMRouter.
    Usado APENAS quando MLClassifier tem confiança < 0.6.
    Custo estimado: ~5-10% dos artigos × $0,07/1M tokens = irrelevante.
    """

    def __init__(self, router: SmartLLMRouter):
        self.router = router
        self.categories_list = "\n".join(
            f"- {slug}: {label}"
            for slug, label in CATEGORY_LABELS.items()
        )

    async def classify(
        self,
        titulo: str,
        conteudo: str,
        ml_suggestion: str,
        ml_score: float
    ) -> ClassificationResult:
        """
        Classifica via LLM quando ML tem baixa confiança.

        Args:
            ml_suggestion: Melhor palpite do ML (usado como hint no prompt)
            ml_score: Score do ML (para logging)
        """
        prompt = FALLBACK_PROMPT_TEMPLATE.format(
            categories=self.categories_list,
            titulo=titulo,
            conteudo_preview=conteudo[:800]
        )

        try:
            response = await self.router.route_request(
                task_type="classificacao_categoria",  # Tier ECONÔMICO
                content=prompt
            )

            # Valida resposta: deve ser um slug válido
            raw_category = response.content.strip().lower()
            if raw_category in CATEGORY_LABELS:
                logger.info(
                    f"LLM fallback classificou '{titulo[:60]}' como '{raw_category}' "
                    f"(ML tinha '{ml_suggestion}' com {ml_score:.2f})"
                )
                return ClassificationResult(
                    categoria=raw_category,
                    confianca=0.85,  # LLM tem alta confiança por default
                    method="llm_fallback"
                )
            else:
                # LLM retornou categoria inválida — usa sugestão do ML
                logger.warning(
                    f"LLM retornou categoria inválida '{raw_category}', usando ML: '{ml_suggestion}'"
                )
                return ClassificationResult(
                    categoria=ml_suggestion,
                    confianca=ml_score,
                    method="ml_fallback_forced"
                )

        except Exception as e:
            logger.error(f"Erro no fallback LLM: {e}. Usando sugestão ML.")
            return ClassificationResult(
                categoria=ml_suggestion,
                confianca=ml_score,
                method="ml_error_recovery"
            )
```

---

## PARTE V — ESPECIFICAÇÃO DO NER (EXTRAÇÃO DE ENTIDADES)

### 5.1 Modelo: `pt_core_news_lg` do spaCy

```python
# brasileira/classification/ner_extractor.py

import asyncio
import logging
from dataclasses import dataclass, field
from collections import Counter
from typing import Optional
import spacy
from spacy.language import Language

logger = logging.getLogger(__name__)

# Entidades suportadas pelo pt_core_news_lg:
# PER  - Pessoas (políticos, atletas, celebridades, cientistas)
# ORG  - Organizações (empresas, partidos, instituições, times)
# LOC  - Locais (países, cidades, estados, bairros, rios)
# MISC - Miscelânea (eventos, obras, leis, produtos)

# Precisão NER pt_core_news_lg:
# ENTS_P: 90.17%, ENTS_R: 90.46%, ENTS_F: 90.31%
# Fonte: https://huggingface.co/spacy/pt_core_news_lg
```

### 5.2 Implementação do Extrator NER

```python
# brasileira/classification/ner_extractor.py (continuação)

@dataclass
class ExtractedEntities:
    """Entidades nomeadas extraídas de um artigo."""
    pessoas: list[str] = field(default_factory=list)      # PER
    organizacoes: list[str] = field(default_factory=list)  # ORG
    locais: list[str] = field(default_factory=list)        # LOC
    misc: list[str] = field(default_factory=list)          # MISC

    # Contagens (para determinar entidades primárias)
    pessoas_count: dict[str, int] = field(default_factory=dict)
    org_count: dict[str, int] = field(default_factory=dict)
    loc_count: dict[str, int] = field(default_factory=dict)

    @property
    def entidade_principal(self) -> Optional[str]:
        """Entidade mais mencionada no texto (person > org > loc)."""
        if self.pessoas_count:
            return max(self.pessoas_count, key=self.pessoas_count.get)
        if self.org_count:
            return max(self.org_count, key=self.org_count.get)
        if self.loc_count:
            return max(self.loc_count, key=self.loc_count.get)
        return None

    @property
    def todas_entidades(self) -> list[str]:
        """Lista deduplicada de todas as entidades, ordenadas por relevância."""
        # Pessoas primeiro (maior relevância editorial), depois orgs e locais
        return list(dict.fromkeys(self.pessoas + self.organizacoes + self.locais + self.misc))

    @property
    def tags_wordpress(self) -> list[str]:
        """Top 5 entidades para usar como tags WordPress."""
        return self.todas_entidades[:5]


class NERExtractor:
    """
    Extrator de entidades nomeadas usando spaCy pt_core_news_lg.

    Performance:
    - Velocidade: ~5-15ms por artigo (300-1000 palavras) em CPU
    - Memória: ~800MB RAM (modelo 'lg' inclui vetores word2vec)
    - Precisão: F1 = 0.903 no corpus de notícias portuguesas
    """

    def __init__(self):
        self.nlp: Optional[Language] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Carrega o modelo spaCy. Operação bloqueante, faça no startup."""
        logger.info("Carregando spaCy pt_core_news_lg...")

        loop = asyncio.get_event_loop()
        try:
            # Carrega apenas os componentes necessários (tok2vec + ner)
            # Desativa parser, morphologizer para economia de tempo
            self.nlp = await loop.run_in_executor(
                None,
                lambda: spacy.load(
                    "pt_core_news_lg",
                    disable=["morphologizer", "senter", "lemmatizer"]
                )
            )
            self._initialized = True
            logger.info("spaCy pt_core_news_lg carregado com sucesso")
        except OSError:
            logger.error(
                "Modelo pt_core_news_lg não encontrado. "
                "Execute: python -m spacy download pt_core_news_lg"
            )
            raise

    async def extract(self, titulo: str, conteudo: str) -> ExtractedEntities:
        """
        Extrai entidades nomeadas do artigo.

        Args:
            titulo: Título do artigo (processado com peso duplo)
            conteudo: Corpo do artigo (primeiros 2000 caracteres para eficiência)

        Returns:
            ExtractedEntities com listas e contagens por tipo
        """
        if not self._initialized:
            raise RuntimeError("NERExtractor não inicializado.")

        # Combina título (repetido para peso) + corpo
        # O spaCy processa melhor texto corrido do que múltiplos campos separados
        text = f"{titulo}. {titulo}. {conteudo[:2000]}"

        # Executa NER em thread separada (CPU-bound)
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(
            None,
            lambda: self.nlp(text)
        )

        # Coleta entidades com contagem de frequência
        pessoas: list[str] = []
        orgs: list[str] = []
        locais: list[str] = []
        misc: list[str] = []

        pessoas_raw: list[str] = []
        orgs_raw: list[str] = []
        locs_raw: list[str] = []

        seen = set()  # Para deduplicação por normalização

        for ent in doc.ents:
            normalized = self._normalize_entity(ent.text)
            if not normalized or len(normalized) < 2:
                continue

            if ent.label_ == "PER":
                pessoas_raw.append(normalized)
                if normalized not in seen:
                    pessoas.append(normalized)
                    seen.add(normalized)
            elif ent.label_ == "ORG":
                orgs_raw.append(normalized)
                if normalized not in seen:
                    orgs.append(normalized)
                    seen.add(normalized)
            elif ent.label_ == "LOC":
                locs_raw.append(normalized)
                if normalized not in seen:
                    locais.append(normalized)
                    seen.add(normalized)
            elif ent.label_ == "MISC":
                if normalized not in seen:
                    misc.append(normalized)
                    seen.add(normalized)

        return ExtractedEntities(
            pessoas=pessoas[:10],       # Máximo 10 de cada tipo
            organizacoes=orgs[:10],
            locais=locais[:10],
            misc=misc[:5],
            pessoas_count=dict(Counter(pessoas_raw)),
            org_count=dict(Counter(orgs_raw)),
            loc_count=dict(Counter(locs_raw)),
        )

    def _normalize_entity(self, text: str) -> str:
        """
        Normaliza texto de entidade:
        - Remove espaços extras
        - Remove caracteres de pontuação no início/fim
        - Normaliza para Title Case se for all caps
        """
        text = text.strip()
        # Remove pontuação do início/fim
        text = text.strip(".,;:!?\"'()-")
        # Se all caps (e >3 chars), converte para Title Case
        if text.isupper() and len(text) > 3:
            text = text.title()
        return text
```

### 5.3 Pós-processamento de Entidades para Uso Downstream

```python
# brasileira/classification/ner_extractor.py (continuação)

# Entidades de parar (stoplist editorial)
# Entidades genéricas que poluem as tags sem agregar valor
ENTITY_STOPLIST = {
    "brasil", "governo", "federal", "estado", "município",
    "decreto", "lei", "projeto", "programa", "agência",
    "segundo", "conforme", "através", "mediante",
    "presidente", "ministro", "secretário",  # Roles genéricos sem nome
    "empresa", "banco", "hospital", "escola",  # Instituições genéricas
}

def filter_entities(entities: ExtractedEntities) -> ExtractedEntities:
    """Remove entidades genéricas que não agregam valor editorial."""

    def _filter(ent_list: list[str]) -> list[str]:
        return [
            e for e in ent_list
            if e.lower() not in ENTITY_STOPLIST
            and len(e) >= 3  # Remove siglas de 1-2 letras ambíguas
            and not e.isdigit()  # Remove números puros
        ]

    entities.pessoas = _filter(entities.pessoas)
    entities.organizacoes = _filter(entities.organizacoes)
    entities.locais = _filter(entities.locais)
    entities.misc = _filter(entities.misc)
    return entities
```

---

## PARTE VI — ESPECIFICAÇÃO DO RELEVANCE SCORER

### 6.1 Fatores de Relevância

O Relevance Scorer calcula dois valores para cada artigo:
1. **Score de relevância** (0-100): importância editorial geral
2. **Urgência** (FLASH / NORMAL / ANÁLISE): timing de publicação

```python
# brasileira/classification/relevance_scorer.py

import re
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Urgencia(str, Enum):
    """Nível de urgência editorial."""
    FLASH = "flash"        # Breaking news — publicar em < 5 min
    NORMAL = "normal"      # Notícia do dia — publicar em < 30 min
    ANALISE = "analise"    # Análise/opinião — publicar em < 2h


@dataclass
class RelevanceScore:
    """Resultado do scoring de relevância."""
    score: float           # 0-100
    urgencia: Urgencia
    breakdown: dict        # Decomposição do score por fator (para debug)
```

### 6.2 Algoritmo de Scoring

```python
# brasileira/classification/relevance_scorer.py (continuação)

# Keywords de urgência/breaking news
BREAKING_KEYWORDS = {
    "urgente", "breaking", "agora", "acabou de", "há pouco",
    "últimas horas", "ao vivo", "em andamento", "minutos atrás",
    "alerta", "emergência", "acaba de", "neste momento",
    "explosão", "terremoto", "acidente", "morte", "assassinato",
    "eleito", "aprovado agora", "sancionado", "vetado",
}

# Keywords de análise/opinião (reduz urgência)
ANALYSIS_KEYWORDS = {
    "análise", "opinião", "coluna", "editorial", "perspectiva",
    "retrospectiva", "panorama", "reflexão", "ensaio", "comentário",
    "entenda por que", "como funciona", "o que é", "saiba mais",
    "especial", "infográfico", "explicamos",
}

# Pesos por tier de fonte (de acordo com contexto-subagentes.md)
TIER_WEIGHTS = {
    "governo": 1.35,
    "reguladores": 1.25,
    "legislativo": 1.20,
    "judiciario": 1.15,
    "grande_midia": 1.10,  # G1, UOL, Folha, Estadão
    "nicho": 1.00,
    "regional": 0.90,
    "internacional": 0.85,
    "blog": 0.80,
    "default": 1.00,
}


class RelevanceScorer:
    """
    Calcula score de relevância editorial e urgência de artigos.

    Substitui o `calcular_relevancia()` do motor_scrapers_v2.py com uma
    abordagem muito mais robusta: analisa título + corpo, detecta urgência
    semântica, considera frescor temporal e tier da fonte.
    """

    def score(
        self,
        titulo: str,
        conteudo: str,
        fonte_tier: str = "default",
        fonte_peso: int = 3,
        data_publicacao: datetime = None,
        categoria: str = "",
    ) -> RelevanceScore:
        """
        Calcula score de relevância e urgência do artigo.

        Args:
            titulo: Título do artigo
            conteudo: Corpo do artigo (primeiros 2000 chars)
            fonte_tier: Tier da fonte (governo, midia_grande, etc.)
            fonte_peso: Peso configurado para esta fonte específica (1-5)
            data_publicacao: Data de publicação (None = agora)
            categoria: Categoria classificada (afeta peso)

        Returns:
            RelevanceScore com score 0-100 e urgência
        """
        breakdown = {}
        titulo_lower = titulo.lower()
        conteudo_lower = conteudo[:1000].lower()

        # === FATOR 1: BASELINE (40 pontos) ===
        score = 40.0
        breakdown["baseline"] = 40.0

        # === FATOR 2: TIER DA FONTE (0-25 pontos) ===
        tier_multiplier = TIER_WEIGHTS.get(fonte_tier, TIER_WEIGHTS["default"])
        tier_bonus = (tier_multiplier - 0.80) * 56  # Normalizado: 0-25 pts
        score += tier_bonus
        breakdown["tier_fonte"] = round(tier_bonus, 2)

        # === FATOR 3: PESO CONFIGURADO DA FONTE (0-10 pontos) ===
        peso_bonus = (fonte_peso - 3) * 3  # Peso 3=0pts, Peso 5=+6pts, Peso 1=-6pts
        score += peso_bonus
        breakdown["peso_fonte"] = round(peso_bonus, 2)

        # === FATOR 4: KEYWORDS SEMÂNTICAS NO TÍTULO+CORPO (0-15 pontos) ===
        # Expandido vs V2 (que tinha apenas 21 keywords globais)
        categoria_keywords = self._get_categoria_keywords(categoria)
        kw_hits = sum(1 for kw in categoria_keywords if kw in titulo_lower or kw in conteudo_lower)
        kw_bonus = min(kw_hits * 2, 15)
        score += kw_bonus
        breakdown["keywords"] = round(kw_bonus, 2)

        # === FATOR 5: FRESCOR TEMPORAL (0 a -15 pontos) ===
        if data_publicacao:
            now = datetime.now(timezone.utc)
            if data_publicacao.tzinfo is None:
                data_publicacao = data_publicacao.replace(tzinfo=timezone.utc)
            age_hours = (now - data_publicacao).total_seconds() / 3600

            if age_hours <= 1:
                freshness_penalty = 0
            elif age_hours <= 6:
                freshness_penalty = -age_hours * 0.5
            elif age_hours <= 24:
                freshness_penalty = -3 - (age_hours - 6) * 0.5
            else:
                freshness_penalty = -12  # Notícias com mais de 24h — mínimo frescor
        else:
            freshness_penalty = 0  # Sem data = assume artigo recente

        score += freshness_penalty
        breakdown["frescor"] = round(freshness_penalty, 2)

        # === FATOR 6: COMPRIMENTO DO TÍTULO (qualidade) ===
        # Título < 30 chars: possivelmente incompleto (ex: só "Breaking News")
        # Título 50-80 chars: ideal
        title_len = len(titulo)
        if title_len < 20:
            title_penalty = -5
        elif title_len < 30:
            title_penalty = -2
        elif 50 <= title_len <= 90:
            title_penalty = 3  # Bônus para títulos bem formatados
        else:
            title_penalty = 0

        score += title_penalty
        breakdown["titulo_qualidade"] = round(title_penalty, 2)

        # Clamp entre 0 e 100
        score = max(0, min(100, score))

        # === CLASSIFICAÇÃO DE URGÊNCIA ===
        urgencia = self._classify_urgencia(titulo_lower, conteudo_lower, categoria, data_publicacao)

        breakdown["score_final"] = round(score, 2)
        breakdown["urgencia"] = urgencia.value

        return RelevanceScore(
            score=round(score, 2),
            urgencia=urgencia,
            breakdown=breakdown,
        )

    def _classify_urgencia(
        self,
        titulo_lower: str,
        conteudo_lower: str,
        categoria: str,
        data_publicacao: datetime = None
    ) -> Urgencia:
        """
        Determina urgência do artigo com base em sinais textuais e temporais.

        Lógica:
        1. Breaking keywords → FLASH
        2. Análise/opinião keywords → ANÁLISE
        3. Artigo > 6 horas → ANÁLISE (notícia velha)
        4. Default → NORMAL
        """
        # Detecta breaking news
        breaking_hits = sum(1 for kw in BREAKING_KEYWORDS if kw in titulo_lower)
        if breaking_hits >= 1:
            return Urgencia.FLASH

        # Detecta análise/opinião
        analysis_hits = sum(1 for kw in ANALYSIS_KEYWORDS if kw in titulo_lower or kw in conteudo_lower)
        if analysis_hits >= 2 or categoria == "opiniao_analise":
            return Urgencia.ANALISE

        # Notícia velha → análise por default
        if data_publicacao:
            now = datetime.now(timezone.utc)
            if data_publicacao.tzinfo is None:
                data_publicacao = data_publicacao.replace(tzinfo=timezone.utc)
            if (now - data_publicacao).total_seconds() > 6 * 3600:
                return Urgencia.ANALISE

        return Urgencia.NORMAL

    def _get_categoria_keywords(self, categoria: str) -> list[str]:
        """Retorna keywords relevantes por categoria para boost de score."""
        # Keywords específicas para cada categoria — complementam os protótipos do ML
        KEYWORDS_BY_CATEGORY = {
            "politica": [
                "presidente", "ministro", "senado", "câmara", "congresso", "eleição",
                "votação", "aprovado", "vetado", "decreto", "medida provisória", "stf",
                "partido", "deputado", "governador", "prefeito", "reforma"
            ],
            "economia": [
                "pib", "inflação", "ipca", "selic", "dólar", "bolsa", "investimento",
                "exportação", "importação", "desemprego", "recessão", "crescimento",
                "banco central", "mercado", "receita federal", "tributário"
            ],
            "saude": [
                "covid", "vacina", "hospital", "sus", "anvisa", "doença", "epidemia",
                "pandemia", "tratamento", "medicamento", "cirurgia", "câncer", "dengue",
                "saúde mental", "ministério da saúde", "internação"
            ],
            "esportes": [
                "gol", "placar", "campeonato", "copa", "final", "torneio", "olimpíada",
                "medalhista", "técnico", "jogador", "time", "clube", "brasileiro",
                "libertadores", "nba", "fórmula 1", "mundial"
            ],
            "tecnologia": [
                "inteligência artificial", "ia", "startup", "software", "hardware", "app",
                "dados", "privacidade", "hacker", "segurança digital", "robô", "algoritmo",
                "blockchain", "5g", "quantum", "metaverso", "chatgpt"
            ],
            "meio_ambiente": [
                "amazônia", "desmatamento", "clima", "carbono", "emissão", "reflorestamento",
                "biodiversidade", "espécie", "poluição", "seca", "enchente", "oceano",
                "energia solar", "eólica", "sustentável", "ibama", "pantanal"
            ],
            "seguranca_justica": [
                "polícia", "crime", "preso", "operação", "tráfico", "assassinato",
                "homicídio", "roubo", "fraude", "corrupção", "lavagem", "tribunal",
                "sentença", "condenado", "investigação", "ministério público"
            ],
        }
        return KEYWORDS_BY_CATEGORY.get(categoria, [])
```

---

## PARTE VII — ESPECIFICAÇÃO DO PRODUCER KAFKA

### 7.1 Configuração do Producer

```python
# brasileira/classification/producer.py

import json
import logging
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

logger = logging.getLogger(__name__)

PRODUCER_CONFIG = {
    "bootstrap_servers": "kafka:9092",
    "acks": "all",               # Confirmação de todos os replicas
    "retry_backoff_ms": 200,
    "max_block_ms": 10_000,      # 10s timeout para envio
    "compression_type": "lz4",   # Compressão para reduzir tráfego de rede
    "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
    "key_serializer": lambda k: k.encode("utf-8") if k else None,
}


class ClassifiedArticleProducer:
    """
    Producer Kafka para o tópico classified-articles.

    Particionamento: por categoria (slug)
    → garante que todos artigos de "politica" vão para a mesma partição
    → Reporter pode consumir por partição/categoria com paralelismo
    """

    def __init__(self):
        self.producer: AIOKafkaProducer = None
        self._initialized = False

    async def start(self) -> None:
        """Inicia o producer."""
        self.producer = AIOKafkaProducer(**PRODUCER_CONFIG)
        await self.producer.start()
        self._initialized = True
        logger.info("ClassifiedArticleProducer iniciado")

    async def stop(self) -> None:
        """Para o producer gracefully."""
        if self.producer:
            await self.producer.stop()
            logger.info("ClassifiedArticleProducer encerrado")

    async def send(self, classified_article: "ClassifiedArticle") -> None:
        """
        Envia artigo classificado para classified-articles.
        Partition key = categoria (routing por editoria).
        """
        if not self._initialized:
            raise RuntimeError("Producer não inicializado")

        try:
            data = classified_article.model_dump(mode="json")
            await self.producer.send_and_wait(
                topic="classified-articles",
                key=classified_article.categoria,   # Partition key por categoria
                value=data,
            )
            logger.debug(
                f"Artigo publicado em classified-articles: "
                f"'{classified_article.titulo[:60]}' → {classified_article.categoria}"
            )
        except KafkaError as e:
            logger.error(f"Erro Kafka ao enviar artigo classificado: {e}")
            raise

    async def send_batch(self, articles: list["ClassifiedArticle"]) -> None:
        """Envia múltiplos artigos em batch (mais eficiente para burst de mensagens)."""
        batch = self.producer.create_batch()

        for article in articles:
            data = json.dumps(article.model_dump(mode="json")).encode("utf-8")
            key = article.categoria.encode("utf-8")
            batch.append(key=key, value=data, timestamp=None)

        await self.producer.send_batch(batch, "classified-articles", partition=None)
```

### 7.2 Configuração do Tópico `classified-articles`

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Partitions | 16 | 1 por macrocategoria — permite Reporters especializados por editoria |
| Replication Factor | 2 | Alta disponibilidade |
| Retention | 4h | Artigos classificados devem ser consumidos rapidamente |
| Partition Key | `categoria` (slug) | Ordering por editoria, scaling por especialização |
| Max Message Size | 2MB | Artigo com NER + scores pode ter payload maior |

---

## PARTE VIII — DEAD LETTER QUEUE E TRATAMENTO DE FALHAS

### 8.1 Filosofia de Tratamento de Falhas

**REGRA FUNDAMENTAL:** Um artigo que falha no Classificador NUNCA é descartado silenciosamente. Ele vai para a Dead Letter Queue `dlq-articles` onde pode ser:
1. **Inspecionado** pelo Monitor Sistema para alertas
2. **Reprocessado** manualmente ou automaticamente após correção
3. **Reportado** nas métricas de saúde do sistema

### 8.2 Tipos de Falha e Tratamento

```python
# brasileira/classification/dlq_handler.py

import json
import logging
import traceback
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

# Categorias de erro para o DLQ
class DLQErrorType:
    VALIDATION_ERROR = "validation_error"       # RawArticle inválido (schema)
    CLASSIFICATION_ERROR = "classification_error"  # ML + LLM ambos falharam
    NER_ERROR = "ner_error"                     # spaCy falhou (OOM, modelo ausente)
    SCORING_ERROR = "scoring_error"             # Relevance scorer falhou
    PRODUCER_ERROR = "producer_error"           # Falha ao publicar no Kafka
    UNKNOWN_ERROR = "unknown_error"             # Exceção não catalogada


class DLQHandler:
    """
    Dead Letter Queue para artigos que falham no pipeline de classificação.

    Tópico: dlq-articles
    Retention: 7 dias (tempo para diagnóstico e reprocessamento)
    """

    def __init__(self, producer: AIOKafkaProducer):
        self.producer = producer

    async def send(
        self,
        original_msg,          # Mensagem Kafka original
        error: str,
        error_type: str = DLQErrorType.UNKNOWN_ERROR,
    ) -> None:
        """Envia mensagem para DLQ com contexto de erro."""
        dlq_payload = {
            "dlq_timestamp": datetime.now(timezone.utc).isoformat(),
            "dlq_error_type": error_type,
            "dlq_error": error[:2000],  # Trunca erros muito longos
            "dlq_attempts": 1,

            # Contexto original
            "original_topic": original_msg.topic,
            "original_partition": original_msg.partition,
            "original_offset": original_msg.offset,
            "original_timestamp_ms": original_msg.timestamp,

            # Dados originais (para reprocessamento)
            "original_value": original_msg.value,
        }

        try:
            await self.producer.send_and_wait(
                topic="dlq-articles",
                key=f"dlq_{original_msg.partition}_{original_msg.offset}".encode(),
                value=json.dumps(dlq_payload, ensure_ascii=False).encode("utf-8"),
            )
            logger.warning(
                f"Artigo enviado para DLQ: {error_type} — "
                f"offset={original_msg.offset} — erro: {error[:100]}"
            )
        except Exception as e:
            # Se até o DLQ falha — log crítico mas não propaga exceção
            logger.critical(
                f"FALHA CRÍTICA: Não foi possível enviar para DLQ: {e}. "
                f"Artigo perdido: offset={original_msg.offset}"
            )
```

### 8.3 Estratégia de Retry com Backoff

```python
# brasileira/classification/consumer.py — retry logic

import asyncio
from functools import wraps

def with_retry(max_attempts: int = 3, base_delay: float = 1.0):
    """Decorator para retry com exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))  # 1s, 2s, 4s
                        logger.warning(
                            f"Tentativa {attempt}/{max_attempts} falhou: {e}. "
                            f"Retry em {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Todas {max_attempts} tentativas falharam: {e}")
            raise last_error
        return wrapper
    return decorator


# Uso no pipeline:
@with_retry(max_attempts=2, base_delay=0.5)
async def _classify_with_retry(classifier, titulo, conteudo):
    return await classifier.classify(titulo, conteudo)
```

### 8.4 Circuit Breaker para LLM Fallback

```python
# brasileira/classification/llm_fallback.py — circuit breaker

class LLMFallbackCircuitBreaker:
    """
    Circuit breaker para o fallback LLM.
    Se o LLM falha 5x seguidas, desliga o fallback por 5 minutos
    e usa ML direto mesmo com baixa confiança.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 300.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time: float = 0
        self._open = False

    def is_open(self) -> bool:
        """Retorna True se o circuit está aberto (LLM indisponível)."""
        if not self._open:
            return False

        import time
        if time.monotonic() - self.last_failure_time > self.recovery_timeout:
            logger.info("Circuit breaker LLM: timeout de recovery expirou, tentando novamente")
            self._open = False
            self.failures = 0
            return False

        return True

    def record_success(self):
        self.failures = 0
        self._open = False

    def record_failure(self):
        import time
        self.failures += 1
        self.last_failure_time = time.monotonic()
        if self.failures >= self.failure_threshold:
            if not self._open:
                logger.warning(
                    f"Circuit breaker LLM ABERTO após {self.failures} falhas. "
                    f"Fallback desativado por {self.recovery_timeout/60:.0f} minutos."
                )
            self._open = True
```

---

## PARTE IX — SCHEMA KAFKA (MENSAGENS DE ENTRADA E SAÍDA)

### 9.1 Schema de Entrada: `raw-articles`

Produzido pelo Worker Pool (Componente #2). O Classificador consome este schema.

```python
# brasileira/classification/schemas.py

from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class TipoArtigo(str, Enum):
    """Tipo do artigo coletado."""
    RSS = "rss"           # Coletado via feed RSS/Atom
    SCRAPER = "scraper"   # Coletado via scraper HTML/Playwright
    API = "api"           # Coletado via API da fonte


class RawArticle(BaseModel):
    """
    Schema de mensagem no tópico raw-articles.
    Produzido pelo Componente #2 (Worker Pool de Coletores).

    OBRIGATÓRIO: não modifique campos marcados como compartilhados com Componente #2.
    """

    # === CAMPOS DE IDENTIFICAÇÃO ===
    article_id: str = Field(..., description="UUID único gerado pelo coletor")
    url: str = Field(..., description="URL canônica do artigo")
    url_hash: str = Field(..., description="SHA-256 da URL normalizada para deduplicação")

    # === DADOS DA FONTE ===
    fonte_id: int = Field(..., description="ID da fonte no banco fontes")
    fonte_nome: str = Field(..., description="Nome legível da fonte")
    fonte_tipo: str = Field("default", description="Tier da fonte: governo, reguladores, etc.")
    fonte_peso: int = Field(3, ge=1, le=5, description="Peso configurado 1-5")
    fonte_url: str = Field(..., description="URL da fonte (site principal)")
    fonte_categoria_hint: str = Field("", description="Categoria sugerida pelo feed/scraper")

    # === CONTEÚDO BRUTO ===
    titulo: str = Field(..., description="Título do artigo (raw, sem processamento LLM)")
    conteudo_bruto: str = Field("", description="Corpo do artigo em texto plano (sem HTML)")
    conteudo_html: str = Field("", description="Corpo em HTML original (pode estar vazio)")
    resumo: str = Field("", description="Excerpt/resumo da fonte, se disponível")
    imagem_url: str = Field("", description="og:image ou primeira imagem do artigo")
    autor: str = Field("", description="Autor do artigo, se disponível")
    tipo: TipoArtigo = Field(TipoArtigo.RSS)

    # === METADADOS TEMPORAIS ===
    data_publicacao: Optional[datetime] = Field(None, description="Data de publicação na fonte")
    data_coleta: datetime = Field(default_factory=lambda: datetime.now(), description="Timestamp da coleta")

    # === CICLO DE COLETA ===
    ciclo_id: str = Field("", description="ID do ciclo de coleta que gerou este artigo")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ClassificationResult(BaseModel):
    """Resultado interno da classificação ML/LLM."""
    categoria: str
    confianca: float = 0.0
    best_score: float = 0.0
    second_category: str = ""
    second_score: float = 0.0
    margin: float = 0.0
    all_scores: dict[str, float] = {}
    method: str = "unknown"  # "ml_zero_shot" | "llm_fallback" | "ml_error_recovery"
```

### 9.2 Schema de Saída: `classified-articles`

Produzido pelo Classificador. Consumido pelo Reporter (Componente #4).

```python
# brasileira/classification/schemas.py (continuação)

class ClassifiedArticle(BaseModel):
    """
    Schema de mensagem no tópico classified-articles.
    Produzido pelo Classificador (Componente #3).
    Consumido pelo Reporter (Componente #4).

    CRÍTICO: O Reporter DEVE conseguir publicar no WordPress usando
    apenas os campos deste schema — sem precisar refetch da fonte original.
    """

    # === HERANÇA DO RawArticle ===
    article_id: str
    url: str
    url_hash: str
    fonte_id: int
    fonte_nome: str
    fonte_tipo: str
    fonte_url: str
    titulo: str
    conteudo_bruto: str
    conteudo_html: str
    resumo: str
    imagem_url: str
    autor: str
    tipo: TipoArtigo
    data_publicacao: Optional[datetime]
    data_coleta: datetime

    # === CAMPOS DE CLASSIFICAÇÃO (adicionados pelo Classificador) ===
    categoria: str = Field(..., description="Slug da macrocategoria: 'politica', 'economia', etc.")
    categoria_label: str = Field(..., description="Label display: 'Política', 'Economia', etc.")
    categoria_wp_id: int = Field(..., description="WordPress Category ID para publicação")
    categoria_confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da classificação")
    classification_method: str = Field("", description="'ml_zero_shot' | 'llm_fallback' | etc.")
    all_category_scores: dict[str, float] = Field(default_factory=dict, description="Scores de todas as categorias")

    # === ENTIDADES NOMEADAS (NER) ===
    entidades_pessoas: list[str] = Field(default_factory=list, description="Pessoas mencionadas")
    entidades_orgs: list[str] = Field(default_factory=list, description="Organizações mencionadas")
    entidades_locais: list[str] = Field(default_factory=list, description="Locais mencionados")
    entidades_misc: list[str] = Field(default_factory=list, description="Miscelânea (eventos, leis)")
    entidade_principal: Optional[str] = Field(None, description="Entidade mais relevante (para busca de imagem)")
    tags_sugeridas: list[str] = Field(default_factory=list, description="Top 5 entidades para tags WP")

    # === SCORING DE RELEVÂNCIA ===
    score_relevancia: float = Field(0.0, ge=0.0, le=100.0, description="Score editorial 0-100")
    urgencia: str = Field("normal", description="'flash' | 'normal' | 'analise'")
    score_breakdown: dict = Field(default_factory=dict, description="Decomposição do score por fator")

    # === METADADOS DO CLASSIFICADOR ===
    classificado_em: datetime = Field(
        default_factory=lambda: datetime.now(),
        description="Timestamp da classificação"
    )
    classificador_version: str = Field("3.0.0", description="Versão do classificador")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
```

### 9.3 Schema da DLQ: `dlq-articles`

```python
class DLQArticle(BaseModel):
    """Schema de mensagem no tópico dlq-articles."""
    dlq_timestamp: datetime
    dlq_error_type: str
    dlq_error: str
    dlq_attempts: int = 1
    dlq_resolved: bool = False

    original_topic: str
    original_partition: int
    original_offset: int
    original_timestamp_ms: int
    original_value: Any  # Dados brutos da mensagem original

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
```

### 9.4 Exemplo de Mensagem — Entrada (`raw-articles`)

```json
{
  "article_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "url": "https://agenciabrasil.ebc.com.br/politica/noticia/2026-03/senado-aprova-reforma-tributaria-por-maioria",
  "url_hash": "sha256:abc123...",
  "fonte_id": 42,
  "fonte_nome": "Agência Brasil",
  "fonte_tipo": "governo",
  "fonte_peso": 5,
  "fonte_url": "https://agenciabrasil.ebc.com.br",
  "fonte_categoria_hint": "politica",
  "titulo": "Senado aprova reforma tributária por 54 votos a 26",
  "conteudo_bruto": "O Senado Federal aprovou nesta quarta-feira a reforma tributária...",
  "conteudo_html": "<p>O Senado Federal aprovou nesta quarta-feira...</p>",
  "resumo": "Aprovação histórica em votação no plenário do Senado.",
  "imagem_url": "https://agenciabrasil.ebc.com.br/images/foto_senado.jpg",
  "autor": "João Silva",
  "tipo": "rss",
  "data_publicacao": "2026-03-26T14:30:00-03:00",
  "data_coleta": "2026-03-26T14:32:17.000Z",
  "ciclo_id": "ciclo_20260326_143000"
}
```

### 9.5 Exemplo de Mensagem — Saída (`classified-articles`)

```json
{
  "article_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "url": "https://agenciabrasil.ebc.com.br/politica/noticia/2026-03/senado-aprova-reforma-tributaria-por-maioria",
  "url_hash": "sha256:abc123...",
  "fonte_id": 42,
  "fonte_nome": "Agência Brasil",
  "fonte_tipo": "governo",
  "fonte_peso": 5,
  "fonte_url": "https://agenciabrasil.ebc.com.br",
  "titulo": "Senado aprova reforma tributária por 54 votos a 26",
  "conteudo_bruto": "O Senado Federal aprovou nesta quarta-feira a reforma tributária...",
  "conteudo_html": "<p>O Senado Federal aprovou nesta quarta-feira...</p>",
  "resumo": "Aprovação histórica em votação no plenário do Senado.",
  "imagem_url": "https://agenciabrasil.ebc.com.br/images/foto_senado.jpg",
  "autor": "João Silva",
  "tipo": "rss",
  "data_publicacao": "2026-03-26T14:30:00-03:00",
  "data_coleta": "2026-03-26T14:32:17.000Z",

  "categoria": "politica",
  "categoria_label": "Política",
  "categoria_wp_id": 2,
  "categoria_confidence": 0.91,
  "classification_method": "ml_zero_shot",
  "all_category_scores": {
    "politica": 0.91,
    "economia": 0.43,
    "brasil_geral": 0.38,
    "seguranca_justica": 0.21
  },

  "entidades_pessoas": ["Rodrigo Pacheco", "Arthur Lira", "Lula"],
  "entidades_orgs": ["Senado Federal", "Câmara dos Deputados", "Ministério da Fazenda"],
  "entidades_locais": ["Brasília", "Brasil"],
  "entidades_misc": ["Reforma Tributária", "PEC 45/2019"],
  "entidade_principal": "Rodrigo Pacheco",
  "tags_sugeridas": ["Rodrigo Pacheco", "Senado Federal", "Reforma Tributária", "Câmara dos Deputados", "Lula"],

  "score_relevancia": 87.5,
  "urgencia": "flash",
  "score_breakdown": {
    "baseline": 40.0,
    "tier_fonte": 22.4,
    "peso_fonte": 6.0,
    "keywords": 12.0,
    "frescor": 0.0,
    "titulo_qualidade": 3.0,
    "score_final": 87.5
  },

  "classificado_em": "2026-03-26T14:32:18.234Z",
  "classificador_version": "3.0.0"
}
```

---

## PARTE X — TABELAS POSTGRESQL

### 10.1 Tabela `classificacao_log`

```sql
-- Tabela para log de classificações (analytics + debugging + retreino futuro)
CREATE TABLE IF NOT EXISTS classificacao_log (
    id                    BIGSERIAL PRIMARY KEY,
    article_id            UUID NOT NULL,
    url_hash              VARCHAR(64) NOT NULL,

    -- Resultado da classificação
    categoria             VARCHAR(64) NOT NULL,
    categoria_confidence  FLOAT NOT NULL,
    classification_method VARCHAR(50) NOT NULL,  -- 'ml_zero_shot', 'llm_fallback', etc.

    -- Entidades NER
    entidades_pessoas     TEXT[] DEFAULT '{}',
    entidades_orgs        TEXT[] DEFAULT '{}',
    entidades_locais      TEXT[] DEFAULT '{}',
    entidade_principal    VARCHAR(255),

    -- Scoring
    score_relevancia      FLOAT NOT NULL,
    urgencia              VARCHAR(20) NOT NULL,  -- 'flash', 'normal', 'analise'

    -- Performance
    latency_ms            INTEGER,               -- Tempo total de classificação em ms
    ml_score              FLOAT,                 -- Score bruto do ML
    llm_fallback_used     BOOLEAN DEFAULT FALSE,

    -- Metadados
    fonte_id              INTEGER,
    fonte_tipo            VARCHAR(50),
    classificado_em       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Index para analytics
    CONSTRAINT uq_classificacao_log_article UNIQUE (article_id)
);

CREATE INDEX idx_classificacao_log_categoria ON classificacao_log(categoria);
CREATE INDEX idx_classificacao_log_urgencia ON classificacao_log(urgencia);
CREATE INDEX idx_classificacao_log_classificado_em ON classificacao_log(classificado_em);
CREATE INDEX idx_classificacao_log_fonte_id ON classificacao_log(fonte_id);
CREATE INDEX idx_classificacao_log_confidence ON classificacao_log(categoria_confidence);
```

### 10.2 Tabela `classificacao_metricas_horarias`

```sql
-- Métricas agregadas por hora para dashboard operacional
CREATE TABLE IF NOT EXISTS classificacao_metricas_horarias (
    id                    SERIAL PRIMARY KEY,
    hora                  TIMESTAMP WITH TIME ZONE NOT NULL,  -- Truncado para hora

    -- Volume
    total_classificados   INTEGER DEFAULT 0,
    total_flash           INTEGER DEFAULT 0,
    total_normal          INTEGER DEFAULT 0,
    total_analise         INTEGER DEFAULT 0,
    total_dlq             INTEGER DEFAULT 0,

    -- Distribuição por categoria (JSON para flexibilidade)
    por_categoria         JSONB DEFAULT '{}',

    -- Performance
    avg_latency_ms        FLOAT,
    p95_latency_ms        FLOAT,
    llm_fallback_count    INTEGER DEFAULT 0,
    ml_direct_count       INTEGER DEFAULT 0,

    -- Confiança média
    avg_confidence        FLOAT,

    atualizado_em         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_metricas_hora UNIQUE (hora)
);

CREATE INDEX idx_metricas_hora ON classificacao_metricas_horarias(hora);
```

### 10.3 Extensão da Tabela `artigos`

```sql
-- Adicionar campos de classificação V3 à tabela artigos existente
-- (se tabela artigos já existir do V2, adicionar colunas)

ALTER TABLE artigos
    ADD COLUMN IF NOT EXISTS categoria_slug     VARCHAR(64),
    ADD COLUMN IF NOT EXISTS categoria_wp_id    INTEGER,
    ADD COLUMN IF NOT EXISTS categoria_confidence FLOAT,
    ADD COLUMN IF NOT EXISTS classification_method VARCHAR(50),
    ADD COLUMN IF NOT EXISTS entidades_json     JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS tags_sugeridas     TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS score_relevancia   FLOAT DEFAULT 50.0,
    ADD COLUMN IF NOT EXISTS urgencia           VARCHAR(20) DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS classificado_em    TIMESTAMP WITH TIME ZONE;

-- Index para queries do Reporter e do Monitor
CREATE INDEX IF NOT EXISTS idx_artigos_categoria_slug
    ON artigos(categoria_slug);
CREATE INDEX IF NOT EXISTS idx_artigos_urgencia
    ON artigos(urgencia);
CREATE INDEX IF NOT EXISTS idx_artigos_score_relevancia
    ON artigos(score_relevancia DESC);

-- GIN index para busca em entidades
CREATE INDEX IF NOT EXISTS idx_artigos_entidades_gin
    ON artigos USING gin(entidades_json);
```

### 10.4 Tabela `dlq_artigos`

```sql
-- Registro de artigos que foram para DLQ (para análise e reprocessamento)
CREATE TABLE IF NOT EXISTS dlq_artigos (
    id                    BIGSERIAL PRIMARY KEY,
    dlq_timestamp         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    dlq_error_type        VARCHAR(100) NOT NULL,
    dlq_error             TEXT,
    dlq_attempts          INTEGER DEFAULT 1,
    dlq_resolved          BOOLEAN DEFAULT FALSE,
    dlq_resolved_at       TIMESTAMP WITH TIME ZONE,

    -- Contexto Kafka
    original_topic        VARCHAR(255),
    original_partition    INTEGER,
    original_offset       BIGINT,

    -- Dados do artigo (para reprocessamento)
    original_url          TEXT,
    original_titulo       TEXT,
    original_fonte_nome   VARCHAR(255),
    original_payload      JSONB  -- Payload completo para reprocessamento
);

CREATE INDEX idx_dlq_timestamp ON dlq_artigos(dlq_timestamp);
CREATE INDEX idx_dlq_resolved ON dlq_artigos(dlq_resolved) WHERE dlq_resolved = FALSE;
CREATE INDEX idx_dlq_error_type ON dlq_artigos(dlq_error_type);
```

---

## PARTE XI — ESTRUTURA DE DIRETÓRIOS E DEPENDÊNCIAS

### 11.1 Estrutura de Arquivos

```
brasileira/
└── classification/
    ├── __init__.py
    ├── consumer.py              # AIOKafkaConsumer + loop principal
    ├── pipeline.py              # Orquestrador: ML + NER + Scorer + Producer
    ├── ml_classifier.py         # Classificador zero-shot com sentence-transformers
    ├── ner_extractor.py         # NER com spaCy pt_core_news_lg
    ├── relevance_scorer.py      # Scoring de relevância e urgência
    ├── producer.py              # AIOKafkaProducer para classified-articles
    ├── dlq_handler.py           # Dead Letter Queue
    ├── llm_fallback.py          # Integração SmartLLMRouter para confiança baixa
    ├── schemas.py               # Pydantic models (RawArticle, ClassifiedArticle, etc.)
    ├── text_processor.py        # Limpeza HTML, normalização texto
    ├── category_config.py       # 16 macrocategorias + protótipos + mapeamentos
    ├── metrics.py               # Prometheus metrics
    └── main.py                  # Entrypoint do serviço

tests/
└── classification/
    ├── test_ml_classifier.py
    ├── test_ner_extractor.py
    ├── test_relevance_scorer.py
    ├── test_pipeline.py
    ├── test_consumer.py
    └── fixtures/
        ├── sample_raw_articles.json
        └── expected_classified_articles.json
```

### 11.2 `pipeline.py` — Orquestrador Central

```python
# brasileira/classification/pipeline.py

import asyncio
import logging
import time
from typing import Optional

from brasileira.classification.ml_classifier import MLClassifier, CONFIDENCE_THRESHOLD
from brasileira.classification.ner_extractor import NERExtractor, filter_entities
from brasileira.classification.relevance_scorer import RelevanceScorer
from brasileira.classification.producer import ClassifiedArticleProducer
from brasileira.classification.llm_fallback import LLMFallbackClassifier, LLMFallbackCircuitBreaker
from brasileira.classification.text_processor import TextProcessor
from brasileira.classification.schemas import RawArticle, ClassifiedArticle
from brasileira.classification.category_config import CATEGORY_LABELS, CATEGORY_WP_IDS
from brasileira.classification.metrics import ClassifierMetrics

logger = logging.getLogger(__name__)


class ClassificationPipeline:
    """
    Orquestrador do pipeline de classificação.

    Fluxo por artigo:
    1. Pré-processamento do texto (limpeza HTML, normalização)
    2. Classificação ML (sentence-transformers zero-shot)
       └── Se confiança < 0.6 → Fallback LLM (econômico)
    3. NER (spaCy pt_core_news_lg)
    4. Relevance Scoring
    5. Montagem ClassifiedArticle
    6. Producer → classified-articles
    """

    def __init__(
        self,
        ml_classifier: MLClassifier,
        ner_extractor: NERExtractor,
        relevance_scorer: RelevanceScorer,
        producer: ClassifiedArticleProducer,
        llm_fallback: Optional[LLMFallbackClassifier] = None,
        metrics: Optional[ClassifierMetrics] = None,
    ):
        self.ml = ml_classifier
        self.ner = ner_extractor
        self.scorer = relevance_scorer
        self.producer = producer
        self.llm_fallback = llm_fallback
        self.circuit_breaker = LLMFallbackCircuitBreaker()
        self.text_processor = TextProcessor()
        self.metrics = metrics

    async def classify(self, raw: RawArticle) -> ClassifiedArticle:
        """
        Executa o pipeline completo para um artigo.

        Returns:
            ClassifiedArticle pronto para publicação no Kafka classified-articles.
        Raises:
            Exception: Se o pipeline falhar irrecuperavelmente (vai para DLQ).
        """
        start_time = time.monotonic()

        # === PASSO 1: Pré-processamento ===
        titulo_clean = self.text_processor.clean_title(raw.titulo)
        conteudo_clean = self.text_processor.clean_body(raw.conteudo_bruto or raw.conteudo_html)

        # === PASSO 2: Classificação ML ===
        ml_result = await self.ml.classify(
            titulo=titulo_clean,
            conteudo=conteudo_clean,
            fonte_categoria_hint=raw.fonte_categoria_hint,
        )

        # === PASSO 3: Fallback LLM se necessário ===
        final_result = ml_result
        if ml_result.confianca < CONFIDENCE_THRESHOLD:
            if self.llm_fallback and not self.circuit_breaker.is_open():
                try:
                    logger.debug(
                        f"ML confiança baixa ({ml_result.confianca:.2f}) para "
                        f"'{titulo_clean[:60]}'. Acionando LLM fallback..."
                    )
                    final_result = await self.llm_fallback.classify(
                        titulo=titulo_clean,
                        conteudo=conteudo_clean,
                        ml_suggestion=ml_result.categoria,
                        ml_score=ml_result.confianca,
                    )
                    self.circuit_breaker.record_success()
                except Exception as e:
                    self.circuit_breaker.record_failure()
                    logger.warning(f"LLM fallback falhou: {e}. Usando ML direto.")
                    # Mantém ml_result mesmo com baixa confiança

        # === PASSO 4: NER (paralelo com scoring) ===
        ner_task = asyncio.create_task(
            self.ner.extract(titulo_clean, conteudo_clean)
        )

        # === PASSO 5: Relevance Scoring ===
        score_result = self.scorer.score(
            titulo=titulo_clean,
            conteudo=conteudo_clean,
            fonte_tier=raw.fonte_tipo,
            fonte_peso=raw.fonte_peso,
            data_publicacao=raw.data_publicacao,
            categoria=final_result.categoria,
        )

        # Aguarda NER (deve ter terminado durante scoring)
        entities_raw = await ner_task
        entities = filter_entities(entities_raw)

        # === PASSO 6: Montagem do ClassifiedArticle ===
        categoria = final_result.categoria
        classified = ClassifiedArticle(
            # Campos herdados do RawArticle
            **raw.model_dump(exclude={"fonte_categoria_hint", "ciclo_id"}),

            # Classificação
            categoria=categoria,
            categoria_label=CATEGORY_LABELS[categoria],
            categoria_wp_id=CATEGORY_WP_IDS[categoria],
            categoria_confidence=final_result.confianca,
            classification_method=final_result.method,
            all_category_scores=final_result.all_scores,

            # NER
            entidades_pessoas=entities.pessoas,
            entidades_orgs=entities.organizacoes,
            entidades_locais=entities.locais,
            entidades_misc=entities.misc,
            entidade_principal=entities.entidade_principal,
            tags_sugeridas=entities.tags_wordpress,

            # Scoring
            score_relevancia=score_result.score,
            urgencia=score_result.urgencia.value,
            score_breakdown=score_result.breakdown,
        )

        elapsed_ms = (time.monotonic() - start_time) * 1000
        if self.metrics:
            self.metrics.article_classified(
                categoria=categoria,
                latency_ms=elapsed_ms,
                method=final_result.method,
            )

        return classified
```

### 11.3 `text_processor.py` — Pré-processamento

```python
# brasileira/classification/text_processor.py

import re
from bs4 import BeautifulSoup
import ftfy  # Fix text encoding issues

class TextProcessor:
    """Limpeza e normalização de texto para classificação."""

    def clean_title(self, titulo: str) -> str:
        """Limpa título: remove HTML, normaliza espaços, corrige encoding."""
        if not titulo:
            return ""
        # Remove HTML
        soup = BeautifulSoup(titulo, "html.parser")
        title = soup.get_text(separator=" ")
        # Corrige encoding (ftfy)
        title = ftfy.fix_text(title)
        # Normaliza espaços
        title = re.sub(r'\s+', ' ', title).strip()
        # Remove prefixos comuns de agências (ex: "URGENTE:", "OFICIAL:")
        title = re.sub(r'^(URGENTE|BREAKING|OFICIAL|VIA [A-Z]+):\s*', '', title, flags=re.IGNORECASE)
        return title[:300]  # Trunca títulos absurdamente longos

    def clean_body(self, conteudo: str) -> str:
        """Limpa corpo: remove HTML, JavaScript, CSS, normaliza."""
        if not conteudo:
            return ""
        # Remove HTML
        soup = BeautifulSoup(conteudo, "html.parser")
        # Remove scripts e styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        # Corrige encoding
        text = ftfy.fix_text(text)
        # Normaliza espaços e quebras de linha
        text = re.sub(r'\s+', ' ', text).strip()
        # Retorna apenas os primeiros 3000 chars (suficiente para classificação)
        return text[:3000]
```

### 11.4 `requirements.txt` — Dependências

```
# Kafka
aiokafka>=0.10.0

# ML - Classificação
sentence-transformers>=3.0.0
scikit-learn>=1.4.0
numpy>=1.26.0

# NLP - NER
spacy>=3.7.0
# Modelo spaCy: python -m spacy download pt_core_news_lg

# Pré-processamento
beautifulsoup4>=4.12.0
lxml>=5.0.0
ftfy>=6.2.0

# Schemas e serialização
pydantic>=2.0.0

# Cache e persistência
redis>=5.0.0
asyncpg>=0.29.0

# Observabilidade
prometheus-client>=0.19.0
opentelemetry-api>=1.20.0

# Utilitários
python-dotenv>=1.0.0

# Dependência da brasileira V3
# SmartLLMRouter (Componente #1) já instalado no projeto
```

### 11.5 `metrics.py` — Prometheus Metrics

```python
# brasileira/classification/metrics.py

from prometheus_client import Counter, Histogram, Gauge

class ClassifierMetrics:
    """Métricas Prometheus para o Classificador."""

    def __init__(self):
        self.articles_classified_total = Counter(
            'classificador_artigos_total',
            'Total de artigos classificados',
            ['categoria', 'method']
        )
        self.articles_failed_total = Counter(
            'classificador_artigos_falha_total',
            'Total de artigos que falharam (DLQ)',
            ['reason']
        )
        self.classification_latency = Histogram(
            'classificador_latencia_segundos',
            'Latência de classificação em segundos',
            buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
        )
        self.llm_fallback_total = Counter(
            'classificador_llm_fallback_total',
            'Total de vezes que LLM fallback foi acionado'
        )
        self.batch_size = Histogram(
            'classificador_batch_size',
            'Tamanho dos batches processados',
            buckets=[1, 5, 10, 20, 50]
        )
        self.confidence_score = Histogram(
            'classificador_confianca',
            'Distribuição de scores de confiança',
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )

    def article_classified(self, categoria: str, latency_ms: float, method: str):
        self.articles_classified_total.labels(categoria=categoria, method=method).inc()
        self.classification_latency.observe(latency_ms / 1000)

    def article_failed(self, reason: str):
        self.articles_failed_total.labels(reason=reason).inc()

    def batch_processed(self, total: int, success: int, fail: int):
        self.batch_size.observe(total)

    def llm_fallback_used(self):
        self.llm_fallback_total.inc()
```

---

## PARTE XII — ENTRYPOINT E INICIALIZAÇÃO

### 12.1 `main.py` — Entrypoint Principal

```python
# brasileira/classification/main.py

"""
Classificador de Artigos V3 — Entrypoint

Inicia o serviço completo:
1. Carrega modelos ML e NER (operações bloqueantes, ~10-30s startup)
2. Conecta ao Kafka (consumer + producer)
3. Conecta ao Redis e PostgreSQL
4. Inicia o loop de consumo e classificação
"""

import asyncio
import logging
import signal
import sys
import os
from contextlib import asynccontextmanager

from brasileira.classification.consumer import ClassificadorConsumer, ClassificadorRebalanceListener
from brasileira.classification.pipeline import ClassificationPipeline
from brasileira.classification.ml_classifier import MLClassifier
from brasileira.classification.ner_extractor import NERExtractor
from brasileira.classification.relevance_scorer import RelevanceScorer
from brasileira.classification.producer import ClassifiedArticleProducer
from brasileira.classification.dlq_handler import DLQHandler
from brasileira.classification.llm_fallback import LLMFallbackClassifier
from brasileira.classification.metrics import ClassifierMetrics

# Importa SmartLLMRouter do Componente #1
from brasileira.llm.smart_router import SmartLLMRouter

# Configuração de logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    """Inicializa e roda o Classificador."""
    logger.info("=== Classificador de Artigos V3 — Iniciando ===")

    # === STEP 1: Inicializa componentes de ML/NLP (CPU-bound, faz no startup) ===
    logger.info("Carregando modelos ML e NLP...")

    ml_classifier = MLClassifier()
    await ml_classifier.initialize()  # Carrega sentence-transformers + calcula centróides

    ner_extractor = NERExtractor()
    await ner_extractor.initialize()  # Carrega spaCy pt_core_news_lg

    logger.info("Modelos ML e NLP prontos")

    # === STEP 2: Inicializa componentes de infraestrutura ===
    relevance_scorer = RelevanceScorer()
    metrics = ClassifierMetrics()

    # === STEP 3: Inicializa SmartLLMRouter para fallback ===
    llm_router = SmartLLMRouter()
    await llm_router.initialize()
    llm_fallback = LLMFallbackClassifier(router=llm_router)

    # === STEP 4: Inicializa Producer Kafka ===
    producer = ClassifiedArticleProducer()
    await producer.start()

    # === STEP 5: Inicializa DLQ Handler (usa o mesmo producer mas tópico diferente) ===
    from aiokafka import AIOKafkaProducer
    import json
    dlq_producer = AIOKafkaProducer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await dlq_producer.start()
    dlq_handler = DLQHandler(producer=dlq_producer)

    # === STEP 6: Monta o Pipeline ===
    pipeline = ClassificationPipeline(
        ml_classifier=ml_classifier,
        ner_extractor=ner_extractor,
        relevance_scorer=relevance_scorer,
        producer=producer,
        llm_fallback=llm_fallback,
        metrics=metrics,
    )

    # === STEP 7: Inicializa Consumer ===
    consumer = ClassificadorConsumer(
        pipeline=pipeline,
        dlq=dlq_handler,
        metrics=metrics,
    )

    # === STEP 8: Setup graceful shutdown ===
    loop = asyncio.get_event_loop()

    def handle_signal(sig):
        logger.info(f"Sinal {sig.name} recebido. Iniciando shutdown graceful...")
        asyncio.create_task(shutdown(consumer, producer, dlq_producer))

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    # === STEP 9: Inicia o consumer (loop principal) ===
    logger.info("=== Classificador pronto. Aguardando artigos em raw-articles ===")
    try:
        await consumer.start()
    except Exception as e:
        logger.critical(f"Erro fatal no consumer: {e}", exc_info=True)
    finally:
        await shutdown(consumer, producer, dlq_producer)


async def shutdown(consumer, producer, dlq_producer):
    """Encerramento graceful de todos os componentes."""
    logger.info("Encerrando Classificador...")
    await consumer.stop()
    await producer.stop()
    await dlq_producer.stop()
    logger.info("Classificador encerrado")


if __name__ == "__main__":
    asyncio.run(main())
```

### 12.2 Inicialização em Docker

```dockerfile
# Dockerfile para o Classificador (adicionar ao docker-compose do projeto)

FROM python:3.12-slim

WORKDIR /app

# Dependências do sistema (lxml, spacy)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baixa modelo spaCy (crítico para NER)
RUN python -m spacy download pt_core_news_lg

# Pré-download do modelo sentence-transformers (evita download em runtime)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

COPY . .

# Variáveis de ambiente obrigatórias
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Porta para métricas Prometheus
EXPOSE 8001

CMD ["python", "-m", "brasileira.classification.main"]
```

### 12.3 Health Check e Readiness

```python
# brasileira/classification/main.py — Health check HTTP simples

from aiohttp import web

async def health_handler(request):
    """Endpoint de health check para K8s/Docker."""
    return web.json_response({
        "status": "ok",
        "component": "classificador",
        "version": "3.0.0",
    })

async def readiness_handler(request, consumer: ClassificadorConsumer, ml: MLClassifier):
    """Endpoint de readiness — só fica ok após modelos carregados."""
    if not ml._initialized:
        return web.json_response({"status": "not_ready", "reason": "ML not initialized"}, status=503)
    return web.json_response({"status": "ready"})

async def start_health_server():
    """Servidor HTTP para health checks e métricas."""
    from prometheus_client import generate_latest
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/metrics", lambda r: web.Response(body=generate_latest()))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8001)
    await site.start()
    logger.info("Health server rodando em :8001")
```

### 12.4 Variáveis de Ambiente

```bash
# .env do Classificador
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_GROUP_ID=classificador-group
KAFKA_RAW_ARTICLES_TOPIC=raw-articles
KAFKA_CLASSIFIED_ARTICLES_TOPIC=classified-articles
KAFKA_DLQ_TOPIC=dlq-articles

# PostgreSQL (para log de classificações)
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=brasileira
POSTGRES_USER=brasileira_app
POSTGRES_PASSWORD=...

# Redis (para cache de centróides entre restarts)
REDIS_URL=redis://redis:6379/0

# ML Config
ML_MODEL_NAME=paraphrase-multilingual-MiniLM-L12-v2
ML_CONFIDENCE_THRESHOLD=0.6
ML_PROTOTYPE_CACHE_PATH=/tmp/classificador_prototypes.pkl

# LLM Fallback (via SmartLLMRouter — chaves já no .env global)
LLM_FALLBACK_ENABLED=true

# Logging
LOG_LEVEL=INFO
```

---

## PARTE XIII — TESTES E VALIDAÇÃO

### 13.1 Testes Unitários do Classificador ML

```python
# tests/classification/test_ml_classifier.py

import pytest
import asyncio
from brasileira.classification.ml_classifier import MLClassifier, CONFIDENCE_THRESHOLD


@pytest.fixture
async def classifier():
    """Fixture que inicializa o MLClassifier uma vez para todos os testes."""
    clf = MLClassifier()
    await clf.initialize()
    return clf


@pytest.mark.asyncio
class TestMLClassifier:

    async def test_politica_clara(self, classifier):
        """Artigo claramente político deve ser classificado com alta confiança."""
        result = await classifier.classify(
            titulo="Senado aprova PEC da reforma tributária por maioria absoluta",
            conteudo="O Senado Federal votou hoje a proposta de emenda constitucional..."
        )
        assert result.categoria == "politica"
        assert result.confianca >= CONFIDENCE_THRESHOLD
        assert result.method == "ml_zero_shot"

    async def test_esportes_futebol(self, classifier):
        """Artigo de futebol deve classificar como esportes."""
        result = await classifier.classify(
            titulo="Flamengo derrota Palmeiras por 3x1 no Maracanã",
            conteudo="O Flamengo venceu o Palmeiras pelo campeonato brasileiro..."
        )
        assert result.categoria == "esportes"
        assert result.confianca >= 0.70

    async def test_saude_vacina(self, classifier):
        """Artigo sobre vacina deve classificar como saúde."""
        result = await classifier.classify(
            titulo="Ministério da Saúde lança campanha de vacinação contra dengue",
            conteudo="O Ministério da Saúde anunciou hoje nova campanha de imunização..."
        )
        assert result.categoria == "saude"
        assert result.confianca >= CONFIDENCE_THRESHOLD

    async def test_tecnologia_ia(self, classifier):
        """Artigo sobre IA deve classificar como tecnologia."""
        result = await classifier.classify(
            titulo="Startup brasileira usa inteligência artificial para diagnóstico médico",
            conteudo="Uma startup sediada em São Paulo desenvolveu algoritmo de deep learning..."
        )
        assert result.categoria == "tecnologia"

    async def test_meio_ambiente(self, classifier):
        """Artigo ambiental deve classificar corretamente."""
        result = await classifier.classify(
            titulo="Desmatamento na Amazônia bate recorde em fevereiro, diz INPE",
            conteudo="O Instituto Nacional de Pesquisas Espaciais divulgou dados mostrando..."
        )
        assert result.categoria == "meio_ambiente"

    async def test_ambiguidade_baixa_confianca(self, classifier):
        """Artigo ambíguo deve ter confiança baixa (candidato ao fallback LLM)."""
        result = await classifier.classify(
            titulo="Empresa anuncia mudanças no setor",  # Ambíguo propositalmente
            conteudo="Mudanças foram anunciadas ontem."
        )
        # Não verifica categoria específica, apenas que confiança é baixa
        assert result.confianca < 0.75  # Título ambíguo = menor certeza

    async def test_fonte_hint_consistente(self, classifier):
        """Hint de categoria consistente com ML deve aumentar confiança."""
        result_sem_hint = await classifier.classify(
            titulo="Câmara votou o projeto aprovado",
            conteudo="A Câmara dos Deputados aprovou projeto de lei..."
        )
        result_com_hint = await classifier.classify(
            titulo="Câmara votou o projeto aprovado",
            conteudo="A Câmara dos Deputados aprovou projeto de lei...",
            fonte_categoria_hint="politica"
        )
        # Com hint consistente, confiança deve ser igual ou maior
        assert result_com_hint.confianca >= result_sem_hint.confianca - 0.05

    async def test_todas_16_categorias_funcionam(self, classifier):
        """Verifica que todas as 16 categorias têm embeddings calculados."""
        assert len(classifier.category_centroids) == 16
        from brasileira.classification.category_config import CATEGORY_LABELS
        for cat in CATEGORY_LABELS.keys():
            assert cat in classifier.category_centroids
```

### 13.2 Testes do NER

```python
# tests/classification/test_ner_extractor.py

import pytest
from brasileira.classification.ner_extractor import NERExtractor, filter_entities


@pytest.fixture
async def ner():
    extractor = NERExtractor()
    await extractor.initialize()
    return extractor


@pytest.mark.asyncio
class TestNERExtractor:

    async def test_extrai_pessoas(self, ner):
        entities = await ner.extract(
            titulo="Lula assina decreto em cerimônia no Planalto",
            conteudo="O presidente Luiz Inácio Lula da Silva assinou hoje..."
        )
        assert len(entities.pessoas) > 0
        assert any("Lula" in p for p in entities.pessoas)

    async def test_extrai_organizacoes(self, ner):
        entities = await ner.extract(
            titulo="Petrobras anuncia novo campo de petróleo no pré-sal",
            conteudo="A Petrobras divulgou descoberta em parceria com o IBAMA..."
        )
        assert any("Petrobras" in o for o in entities.organizacoes)

    async def test_extrai_locais(self, ner):
        entities = await ner.extract(
            titulo="Enchente em Porto Alegre deixa 50 famílias desalojadas",
            conteudo="A cidade de Porto Alegre no Rio Grande do Sul..."
        )
        locais = entities.locais
        assert any("Porto Alegre" in l or "Rio Grande do Sul" in l for l in locais)

    async def test_entidade_principal_pessoa(self, ner):
        entities = await ner.extract(
            titulo="Bolsonaro depôs na Polícia Federal sobre tentativa de golpe",
            conteudo="O ex-presidente Jair Bolsonaro prestou depoimento..."
        )
        assert entities.entidade_principal is not None

    async def test_filtro_stoplist(self, ner):
        entities = await ner.extract(
            titulo="Governo Federal anuncia novo programa",
            conteudo="O Governo Federal lançou programa para beneficiar empresas..."
        )
        filtered = filter_entities(entities)
        # "Governo" e "empresa" devem ser filtrados pela stoplist
        assert "Governo" not in filtered.organizacoes
        assert "empresa" not in filtered.organizacoes

    async def test_tags_wordpress_max5(self, ner):
        entities = await ner.extract(
            titulo="Reunião envolveu Lula, Pacheco, Lira, Haddad, Dino, Gonet, Alexandre",
            conteudo="A reunião no Palácio do Planalto reuniu o presidente Lula..."
        )
        assert len(entities.tags_wordpress) <= 5
```

### 13.3 Testes do Relevance Scorer

```python
# tests/classification/test_relevance_scorer.py

import pytest
from datetime import datetime, timezone, timedelta
from brasileira.classification.relevance_scorer import RelevanceScorer, Urgencia


class TestRelevanceScorer:

    def setup_method(self):
        self.scorer = RelevanceScorer()

    def test_score_range_valido(self):
        """Score sempre entre 0 e 100."""
        result = self.scorer.score(
            titulo="Título de teste",
            conteudo="Conteúdo de teste para validação do sistema"
        )
        assert 0 <= result.score <= 100

    def test_fonte_governo_tem_score_maior(self):
        """Fonte do governo deve ter score maior que fonte nicho."""
        score_gov = self.scorer.score(
            titulo="Ministério anuncia programa",
            conteudo="O ministério publicou portaria...",
            fonte_tier="governo",
            fonte_peso=5,
        )
        score_nicho = self.scorer.score(
            titulo="Ministério anuncia programa",
            conteudo="O ministério publicou portaria...",
            fonte_tier="nicho",
            fonte_peso=3,
        )
        assert score_gov.score > score_nicho.score

    def test_urgencia_breaking_news(self):
        """Título com keyword de urgência → FLASH."""
        result = self.scorer.score(
            titulo="URGENTE: Explosão em Brasília deixa feridos",
            conteudo="Explosão ocorreu há pouco na capital federal..."
        )
        assert result.urgencia == Urgencia.FLASH

    def test_urgencia_analise(self):
        """Artigo de análise → ANÁLISE."""
        result = self.scorer.score(
            titulo="Análise: O impacto da reforma tributária na classe média",
            conteudo="Esta análise examina as perspectivas de longo prazo...",
            categoria="opiniao_analise"
        )
        assert result.urgencia == Urgencia.ANALISE

    def test_artigo_velho_perde_score(self):
        """Artigo publicado há 12 horas deve ter score menor que artigo recente."""
        agora = datetime.now(timezone.utc)

        score_recente = self.scorer.score(
            titulo="Mesmo título",
            conteudo="Mesmo conteúdo",
            data_publicacao=agora - timedelta(minutes=30)
        )
        score_velho = self.scorer.score(
            titulo="Mesmo título",
            conteudo="Mesmo conteúdo",
            data_publicacao=agora - timedelta(hours=12)
        )

        assert score_recente.score > score_velho.score

    def test_breakdown_tem_todos_fatores(self):
        """Breakdown deve ter todos os fatores documentados."""
        result = self.scorer.score(
            titulo="Presidente assina decreto econômico importante",
            conteudo="O presidente Lula assinou decreto..."
        )
        required_keys = {"baseline", "tier_fonte", "peso_fonte", "keywords", "frescor", "titulo_qualidade", "score_final"}
        assert required_keys.issubset(set(result.breakdown.keys()))
```

### 13.4 Testes de Integração do Pipeline

```python
# tests/classification/test_pipeline.py

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from brasileira.classification.pipeline import ClassificationPipeline
from brasileira.classification.ml_classifier import MLClassifier
from brasileira.classification.ner_extractor import NERExtractor
from brasileira.classification.relevance_scorer import RelevanceScorer
from brasileira.classification.schemas import RawArticle, TipoArtigo


@pytest.fixture
async def full_pipeline(classifier, ner):
    """Pipeline completo com mock do producer e LLM fallback."""
    mock_producer = AsyncMock()
    mock_producer.send = AsyncMock()

    pipeline = ClassificationPipeline(
        ml_classifier=classifier,
        ner_extractor=ner,
        relevance_scorer=RelevanceScorer(),
        producer=mock_producer,
        llm_fallback=None,  # Sem LLM nos testes unitários
    )
    return pipeline


@pytest.fixture
def sample_raw_article():
    return RawArticle(
        article_id="test-uuid-1234",
        url="https://agenciabrasil.ebc.com.br/politica/teste",
        url_hash="sha256:abc123",
        fonte_id=42,
        fonte_nome="Agência Brasil",
        fonte_tipo="governo",
        fonte_peso=5,
        fonte_url="https://agenciabrasil.ebc.com.br",
        fonte_categoria_hint="politica",
        titulo="Senado aprova reforma tributária em votação histórica",
        conteudo_bruto=(
            "O Senado Federal aprovou nesta terça-feira a reforma tributária "
            "por 54 votos a 26. O presidente Rodrigo Pacheco comemorou a aprovação."
        ),
        conteudo_html="<p>O Senado Federal aprovou...</p>",
        resumo="Aprovação histórica no Senado.",
        imagem_url="https://agenciabrasil.ebc.com.br/foto.jpg",
        tipo=TipoArtigo.RSS,
        data_publicacao=datetime.now(timezone.utc),
        data_coleta=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
class TestClassificationPipeline:

    async def test_pipeline_completo_produz_classified_article(
        self, full_pipeline, sample_raw_article
    ):
        """Pipeline completo deve produzir ClassifiedArticle válido."""
        result = await full_pipeline.classify(sample_raw_article)

        assert result.article_id == sample_raw_article.article_id
        assert result.categoria == "politica"
        assert result.categoria_wp_id == 2
        assert result.categoria_confidence > 0.5
        assert 0 <= result.score_relevancia <= 100
        assert result.urgencia in ("flash", "normal", "analise")
        assert len(result.tags_sugeridas) <= 5
        assert result.classificador_version == "3.0.0"

    async def test_entidades_extraidas(self, full_pipeline, sample_raw_article):
        """NER deve extrair entidades do artigo de teste."""
        result = await full_pipeline.classify(sample_raw_article)
        # Rodrigo Pacheco e Senado Federal devem estar nas entidades
        all_entities = (
            result.entidades_pessoas +
            result.entidades_orgs +
            result.entidades_locais
        )
        assert len(all_entities) > 0

    async def test_score_relevancia_fonte_governo(self, full_pipeline, sample_raw_article):
        """Fonte 'governo' com peso 5 deve ter score alto."""
        result = await full_pipeline.classify(sample_raw_article)
        assert result.score_relevancia >= 60  # Mínimo esperado para fonte governo peso 5
```

### 13.5 Validação em Produção — KPIs de Aceitação

Após deploy, monitorar estas métricas por 24h antes de considerar estável:

| KPI | Valor Mínimo | Como Verificar |
|-----|-------------|----------------|
| Artigos classificados/h | ≥ 40 | Prometheus: `classificador_artigos_total` por hora |
| Latência média de classificação | < 200ms | Prometheus: `classificador_latencia_segundos` p50 |
| Taxa de confiança ≥ 0.6 | ≥ 85% | `classificador_confianca` — percentil 15 deve ser ≥ 0.6 |
| Taxa de LLM fallback | < 15% | `classificador_llm_fallback_total / classificador_artigos_total` |
| Taxa de DLQ | < 2% | `classificador_artigos_falha_total / classificador_artigos_total` |
| Distribuição por categoria | Todas 16 presentes | `classificador_artigos_total` agrupado por categoria |
| Tempo de startup | < 60s | Log: tempo entre "Iniciando" e "Aguardando artigos" |

---

## PARTE XIV — PLANO DE IMPLEMENTAÇÃO E CHECKLIST

### 14.1 Dependências de Outros Componentes

```
Componente #1 (SmartLLMRouter) → OBRIGATÓRIO para LLM fallback
Componente #2 (Worker Pool)    → OBRIGATÓRIO para input (raw-articles)
Componente #3 (este)           → OBRIGATÓRIO para Componente #4 (Reporter)
```

**IMPORTANTE:** O Classificador pode ser implementado e testado ANTES do Componente #2 estar completo, usando mensagens Kafka sintéticas para testes.

### 14.2 Checklist de Implementação

#### Fase 1 — Setup e Infraestrutura (Dia 1)

- [ ] Criar diretório `brasileira/classification/` e estrutura de arquivos
- [ ] Instalar dependências: `aiokafka`, `sentence-transformers`, `spacy`, `scikit-learn`, `beautifulsoup4`, `ftfy`
- [ ] Baixar modelo spaCy: `python -m spacy download pt_core_news_lg`
- [ ] Pre-download modelo sentence-transformers: testar `SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")`
- [ ] Criar tópico Kafka `classified-articles` (16 partições, replication=2)
- [ ] Criar tópico Kafka `dlq-articles` (4 partições, retention=7d)
- [ ] Criar tabelas PostgreSQL: `classificacao_log`, `classificacao_metricas_horarias`, `dlq_artigos`
- [ ] Executar migrations de `ALTER TABLE artigos` para adicionar colunas V3
- [ ] Configurar variáveis de ambiente no `.env`

#### Fase 2 — Implementação Core (Dias 1-2)

- [ ] Implementar `schemas.py` (RawArticle, ClassifiedArticle, ClassificationResult, DLQArticle)
- [ ] Implementar `category_config.py` (16 categorias, protótipos, mapeamentos WP)
- [ ] Implementar `text_processor.py` (limpeza HTML, normalização)
- [ ] Implementar `ml_classifier.py` (MLClassifier com sentence-transformers)
  - [ ] `initialize()` com cache de centróides
  - [ ] `_compute_centroids()` a partir de protótipos
  - [ ] `classify()` com cosine similarity
- [ ] Implementar `ner_extractor.py` (NERExtractor com spaCy)
  - [ ] `initialize()` com pt_core_news_lg
  - [ ] `extract()` retornando ExtractedEntities
  - [ ] `filter_entities()` com stoplist
- [ ] Implementar `relevance_scorer.py` (RelevanceScorer)
  - [ ] `score()` com 6 fatores
  - [ ] `_classify_urgencia()` com detecção de breaking news

#### Fase 3 — Pipeline e Kafka (Dias 2-3)

- [ ] Implementar `llm_fallback.py` (LLMFallbackClassifier + CircuitBreaker)
- [ ] Implementar `producer.py` (ClassifiedArticleProducer)
- [ ] Implementar `dlq_handler.py` (DLQHandler)
- [ ] Implementar `pipeline.py` (ClassificationPipeline)
  - [ ] `classify()` orquestrado
  - [ ] Paralelismo NER + scoring com `asyncio.create_task`
- [ ] Implementar `consumer.py` (ClassificadorConsumer)
  - [ ] `_consume_loop()` com batch processing
  - [ ] `_batch_generator()` com getmany
  - [ ] `_process_message()` com retry
  - [ ] RebalanceListener
- [ ] Implementar `metrics.py` (Prometheus metrics)
- [ ] Implementar `main.py` (entrypoint completo com graceful shutdown)

#### Fase 4 — Testes (Dia 3)

- [ ] Criar fixtures JSON com artigos de exemplo (mínimo 3 por categoria)
- [ ] Implementar `test_ml_classifier.py` — mínimo 7 testes
- [ ] Implementar `test_ner_extractor.py` — mínimo 5 testes
- [ ] Implementar `test_relevance_scorer.py` — mínimo 5 testes
- [ ] Implementar `test_pipeline.py` — mínimo 3 testes de integração
- [ ] Rodar `pytest tests/classification/` — 100% deve passar
- [ ] Verificar cobertura de código: `pytest --cov=brasileira.classification tests/classification/`

#### Fase 5 — Validação em Produção (Dia 4+)

- [ ] Deploy do Classificador em ambiente de staging
- [ ] Injetar 100 artigos de teste via Kafka (um por categoria)
- [ ] Verificar distribuição de categorias: todas 16 devem aparecer
- [ ] Verificar latência média < 200ms (Prometheus)
- [ ] Verificar taxa de LLM fallback < 15%
- [ ] Verificar taxa de DLQ < 2%
- [ ] Verificar que artigos aparecem em `classified-articles` dentro de 1s
- [ ] Deploy em produção
- [ ] Monitorar por 24h com todos os KPIs da Parte XIII

### 14.3 Erros Comuns e Como Evitá-los

| Erro Comum | Como Evitar |
|-----------|-------------|
| `OSError: Can't find model 'pt_core_news_lg'` | Execute `python -m spacy download pt_core_news_lg` no Dockerfile/setup |
| `ModuleNotFoundError: sentence_transformers` | Instale `sentence-transformers>=3.0.0` e não `transformers` direto |
| Consumer sem `group_id` | Sempre definir `group_id="classificador-group"` — sem group não há consumer groups |
| Auto-commit habilitado | Sempre `enable_auto_commit=False` + commit manual após processamento |
| Bloqueio no event loop | Rodar modelos ML/NLP em `run_in_executor`, nunca `model.encode()` diretamente em `async def` |
| Categoria inválida no LLM fallback | Validar resposta LLM contra `CATEGORY_LABELS.keys()` antes de usar |
| OOM com spaCy e batch grande | Processar textos individuais, não batch de 1000 ao mesmo tempo |
| Centróides sem cache = startup lento | `PROTOTYPE_CACHE_PATH` deve ser persistente entre restarts (volume Docker) |
| DLQ silencioso | NUNCA capturar exceção sem enviar para DLQ ou logar |
| Kafka producer sem `acks=all` | `acks="all"` garante durabilidade — sempre |

### 14.4 Escalabilidade Horizontal

O Classificador é projetado para escalar horizontalmente via múltiplas instâncias no mesmo consumer group:

```
raw-articles (16 partições)
    │
    ├── Classificador #1 (partições 0-3)
    ├── Classificador #2 (partições 4-7)
    ├── Classificador #3 (partições 8-11)
    └── Classificador #4 (partições 12-15)
```

**Para escalar:** Apenas adicionar mais instâncias do mesmo Docker container. O Kafka redistribui automaticamente as partições. O modelo ML e NER são carregados em memória por instância — 16 partições = máximo 16 instâncias paralelas (uma por partição).

**Custo de memória por instância:**
- `paraphrase-multilingual-MiniLM-L12-v2`: ~500MB RAM
- `pt_core_news_lg`: ~800MB RAM
- **Total por instância: ~1.3GB RAM**

Para 4 instâncias paralelas (cobre picos de 200+ artigos/min): ~5GB RAM total.

### 14.5 Manutenção e Evolução

**Para adicionar nova categoria:**
1. Adicionar entrada em `CATEGORY_PROTOTYPES` com ≥ 10 frases prototípicas
2. Adicionar mapeamento em `CATEGORY_LABELS` e `CATEGORY_WP_IDS`
3. Deletar cache de centróides: `rm /tmp/classificador_prototypes.pkl`
4. Restart do Classificador (recalcula centróides automaticamente)

**Para melhorar precisão:**
1. Coletar artigos mal classificados do PostgreSQL (`categoria_confidence < 0.7`)
2. Adicionar frases prototípicas mais específicas baseadas nesses artigos
3. Ajustar `CONFIDENCE_THRESHOLD` se necessário (padrão: 0.6)

**Para treinar modelo fine-tuned (futuro):**
- Após 30 dias de produção: exportar `(titulo, conteudo, categoria)` de `classificacao_log` onde `classification_method = 'ml_zero_shot' AND categoria_confidence > 0.8`
- Usar esse dataset para fine-tune de BERTimbau-base em classificação de texto
- Substituir `MLClassifier` pelo modelo fine-tuned mantendo a mesma interface

---

## APÊNDICE A — MAPEAMENTO V2 → V3 RESUMIDO

| Componente V2 | Status | Substituto V3 |
|--------------|--------|---------------|
| `editor_editoria-9.py` (classificação LLM) | **ELIMINADO** | `ml_classifier.py` (ML zero-shot, 0 custo) |
| `calcular_relevancia()` em motor_scrapers | **SUBSTITUÍDO** | `relevance_scorer.py` (6 fatores, score 0-100) |
| 4 editorias hardcoded | **EXPANDIDO** | 16 macrocategorias com protótipos semânticos |
| Sem NER | **NOVO** | `ner_extractor.py` (spaCy pt_core_news_lg) |
| Sem Kafka | **NOVO** | Consumer `raw-articles` + Producer `classified-articles` |
| Sem DLQ | **NOVO** | `dlq_handler.py` com tópico `dlq-articles` |
| Sem métricas | **NOVO** | Prometheus metrics por categoria/método/latência |
| VALID_CATEGORIES no config.py | **REFERÊNCIA** | Expandido para 16 categorias em category_config.py |

---

## APÊNDICE B — FLUXO KAFKA COMPLETO DO SISTEMA

```
[Kafka: fonte-assignments] ─────────────────────── Producer: Feed Scheduler
                                                     Consumer: Workers Coletores
                                │
                                ▼
[Kafka: raw-articles] ──────────────────────────── Producer: Workers Coletores
                                                     Consumer: Classificador ← ESTE COMPONENTE
                                │
                                ▼
[Kafka: classified-articles] ───────────────────── Producer: Classificador ← ESTE COMPONENTE
                                                     Consumer: Worker Pool Reporters
                                │
                                ▼
[Kafka: article-published] ─────────────────────── Producer: Reporter
                                                     Consumer: Fotógrafo, Revisor, Curador, Monitor
                                │
                                ▼
           ┌────────────────────┴───────────────────┐
           │                                         │
[Kafka: pautas-especiais]              [Kafka: dlq-articles] ← ESTE COMPONENTE
[Kafka: pautas-gap]                    Consumer: Monitor Sistema
[Kafka: consolidacao]
[Kafka: homepage-updates]
[Kafka: breaking-candidate]
```

---

## APÊNDICE C — REFERÊNCIAS E BENCHMARKS

- **Modelo sentence-transformers:** `paraphrase-multilingual-MiniLM-L12-v2` — 50+ idiomas incluindo pt-BR, 384 dims, ~117MB. Documentação: https://www.sbert.net/docs/sentence_transformer/pretrained_models.html
- **spaCy pt_core_news_lg:** NER para português com F1=90.31%. Disponível: `python -m spacy download pt_core_news_lg`. Documentação: https://huggingface.co/spacy/pt_core_news_lg
- **aiokafka consumer groups:** Documentação oficial: https://aiokafka.readthedocs.io/en/stable/consumer.html
- **BERTimbau (referência futura):** Modelos BERT para português brasileiro. Souza et al. (2020). Disponível para fine-tuning futuro.
- **Benchmarking pt-BR:** Artigos de notícias em português classificados com BERT atingem >92% de acurácia. Fonte: IIIS.org/CDs2022. Zero-shot com sentence-transformers atinge ~85% para português.

---

*Briefing gerado para brasileira.news V3 — Componente #3: Classificador de Artigos + Kafka Pipeline*
*Data: 26 de março de 2026 | Versão: 1.0*
