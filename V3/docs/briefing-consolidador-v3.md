# Briefing Completo para IA — Consolidador V3

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #7 (Alta Prioridade)
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / LangGraph / Kafka / Redis / PostgreSQL + pgvector / WordPress REST API / LiteLLM
**Componente:** `brasileira/consolidador/` — módulo completo

---

## LEIA ISTO PRIMEIRO — Por que o Consolidador é Crítico

O Consolidador é o **agente de inteligência editorial** do sistema. Ele não apenas agrega matérias — ele toma decisões editoriais em tempo real baseadas no que os concorrentes estão colocando nas capas dos seus portais. É o componente que garante que a brasileira.news nunca perca um tema importante e sempre entregue matérias com ângulo editorial próprio, não apenas replicando o que os concorrentes publicaram.

**O bug mais grave da V2** foi o `MIN_SOURCES=3` — o Consolidador simplesmente ignorava temas cobertos por 1 ou 2 fontes, deixando a brasileira.news muda sobre assuntos que estavam nas capas de G1, UOL e Folha. Isso criou gaps editoriais gritantes.

**Este briefing contém TUDO que você precisa para implementar o Consolidador V3 do zero.** Não improvise nos pontos marcados como OBRIGATÓRIO. Não mantenha lógicas da V2 que contradizem as regras de negócio aqui descritas.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ QUEBRADO NA V2

### 1.1 O Arquivo: `consolidador-14.py` (1.105 linhas)

O Consolidador V2 está em `consolidador-14.py`. A análise completa revela **6 problemas fatais**:

#### Problema Fatal #1: MIN_SOURCES=3 — A Regra de Negócio Errada

```python
# V2 — ERRADO (consolidador-14.py, linha 38-39)
MIN_SOURCES_PER_TOPIC = 3   # ← ERRADO. Destrói a lógica editorial
MAX_SOURCES_PER_TOPIC = 7

# No _handle_trending_cluster (linha 344):
if len(sources) < MIN_SOURCES_PER_TOPIC:
    self.logger.debug(f"Cluster has only {len(sources)} sources, need {MIN_SOURCES_PER_TOPIC}")
    return  # ← DESCARTA silenciosamente temas com 1 ou 2 fontes
```

**Impacto:** Se o G1 tem uma matéria importante sobre política que só nós e o G1 cobrimos (2 fontes), o Consolidador V2 descarta silenciosamente. A brasileira.news fica sem consolidar, sem reescrever. O leitor não vê nada diferente. Isso contradiz diretamente as regras de negócio.

**V3 CORRETO:**
- 0 fontes → aciona Reporter para cobertura
- 1 fonte → REESCREVER com ângulo editorial
- 2+ fontes → CONSOLIDAR em análise aprofundada

#### Problema Fatal #2: Acionado por TrendingDetector Interno, Não pelo Monitor Concorrência

```python
# V2 — ERRADO (consolidador-14.py, linha 304-314)
async def start(self) -> None:
    if self.event_bus and not self._subscribed:
        await self.event_bus.subscribe(
            channels=["trending_cluster"],  # ← EventBus interno, não Kafka
            callback=self._handle_trending_cluster,
        )
```

O Consolidador V2 escuta um EventBus interno (`trending_cluster`), acionado por um `TrendingDetector` que analisa artigos do próprio sistema. Isso é o inverso do que deveria ser: o Consolidador deve ser acionado pelo **Monitor Concorrência**, que detecta o que está nas capas dos **concorrentes**. A diferença é fundamental:

- **TrendingDetector interno:** "O que nós já publicamos está trending"
- **Monitor Concorrência:** "O que os concorrentes estão colocando na capa que não temos cobertura equivalente"

**V3 CORRETO:** Consolidador consome do tópico Kafka `consolidacao`, que é produzido exclusivamente pelo Monitor Concorrência.

#### Problema Fatal #3: Revisa Qualidade com Gate de Rejeição

```python
# V2 — ERRADO (consolidador-14.py, linha 395-410)
def _should_publish(self, state) -> str:
    quality_review = state.get("quality_review", {})
    score = quality_review.get("score", 0)
    if score >= 7.0:
        return "prepare_publish"
    self.logger.warning(f"Article quality too low (score={score}), aborting publish")
    return "end"  # ← DESCARTA o artigo se score < 7. Viola regra #1
```

A V2 tem um gate de qualidade que pode **abortar a publicação**. Isso viola a regra de negócio #1: "Publicar primeiro, revisar depois." O Revisor pós-publicação (componente #3) cuida da qualidade. O Consolidador deve **sempre publicar**, mesmo que o LLM produza algo imperfeito.

**V3 CORRETO:** Qualidade é informação, nunca bloqueio. Se a síntese produziu algo, publicar. O Revisor corrige depois.

#### Problema Fatal #4: Sem Consumer Kafka

```python
# V2 — Não tem consumer Kafka. Depende de EventBus interno.
# Sem integração com tópico 'consolidacao'.
# Sem integração com tópico 'pautas-gap'.
```

A V2 usa um sistema de eventos interno (EventBus) que não se integra com a arquitetura Kafka da V3. O Consolidador V3 deve consumir do tópico `consolidacao` e produzir para `pautas-gap`.

#### Problema Fatal #5: Publicação via EventBus, Não WordPress Direto

```python
# V2 — ERRADO (consolidador-14.py, linha ~800)
# Emite evento para PublisherAgent (eliminado na V3)
await self.event_bus.publish("article_ready_to_publish", payload)
```

O PublisherAgent foi **eliminado na V3**. A publicação deve ser feita diretamente via WordPress REST API, igual ao Reporter V3.

#### Problema Fatal #6: Sem Lógica de Reescrita (1 Fonte)

A V2 só sabe **consolidar** (múltiplas fontes). Não tem nenhuma lógica para **reescrever** um artigo existente com ângulo editorial próprio quando há apenas 1 fonte. Isso significa que metade da função do Consolidador V3 simplesmente não existe na V2.

---

### 1.2 Resumo dos Problemas V2

| Problema | Impacto | Solução V3 |
|----------|---------|-----------|
| `MIN_SOURCES=3` descarta temas com 1-2 fontes | Gaps editoriais gritantes | Lógica 0/1/2+: acionar/reescrever/consolidar |
| Acionado por TrendingDetector interno | Monitora o errado (nós, não concorrentes) | Consumer Kafka `consolidacao` do Monitor Concorrência |
| Gate de qualidade bloqueia publicação | Viola regra "publicar primeiro" | Publicar sempre, Revisor corrige depois |
| Sem consumer Kafka | Não integra com pipeline V3 | Consumer Kafka completo |
| Publicação via EventBus | PublisherAgent foi eliminado | WordPress REST API direto |
| Sem lógica de reescrita | 50% da função do componente ausente | Implementar `reescrever()` com LLM PREMIUM |

---

## PARTE II — ARQUITETURA V3

### 2.1 Visão Geral

```
                    ┌─────────────────────────────────────┐
                    │       MONITOR CONCORRÊNCIA           │
                    │  (Scanneia capas G1, UOL, Folha,     │
                    │   Estadão, CNN Brasil a cada 30min)  │
                    └─────────────┬───────────────────────┘
                                  │ Kafka: consolidacao
                                  │ (tema com 1+ matérias nossas)
                                  ▼
                    ┌─────────────────────────────────────┐
                    │         CONSOLIDADOR V3              │
                    │                                      │
                    │  ┌──────────────────────────────┐   │
                    │  │   Consumer Kafka              │   │
                    │  │   topic: consolidacao         │   │
                    │  └──────────┬───────────────────┘   │
                    │             │                        │
                    │  ┌──────────▼───────────────────┐   │
                    │  │   Busca Matérias Próprias     │   │
                    │  │   (PostgreSQL + pgvector)     │   │
                    │  └──────────┬───────────────────┘   │
                    │             │                        │
                    │  ┌──────────▼───────────────────┐   │
                    │  │   ROTEADOR 0/1/2+             │   │
                    │  └─────┬──────────┬─────────┐   │   │
                    │        │          │         │   │   │
                    │      0 │        1 │       2+│   │   │
                    │        ▼          ▼         ▼   │   │
                    │  Kafka:pautas  Reescrita  Consol │   │
                    │  -gap → Rep.  Editorial  idação  │   │
                    │  (Reporter)   (LLM PREM)  Analít │   │
                    │                          (LLM   │   │
                    │                          PREM)  │   │
                    │        └──────────┴─────────┘   │   │
                    │                  │               │   │
                    │  ┌───────────────▼─────────────┐│   │
                    │  │   WordPress REST API         ││   │
                    │  │   Publica direto             ││   │
                    │  └─────────────────────────────┘│   │
                    └─────────────────────────────────┘
```

### 2.2 Fluxo de Dados Completo

```
Monitor Concorrência detecta tema na capa do G1
    │
    ├── Quantas matérias nossas temos sobre esse tema?
    │   ├── 0 → envia para Kafka: pautas-gap (Reporter cobre)
    │   ├── 1 → envia para Kafka: consolidacao (Consolidador reescreve)
    │   └── 2+ → envia para Kafka: consolidacao (Consolidador consolida)
    │
Consolidador consome mensagem de 'consolidacao'
    │
    ├── Enriquece contexto (busca matérias no PostgreSQL)
    ├── Detecta matérias relacionadas (TF-IDF + pgvector)
    ├── ROTEADOR decide: 0/1/2+ fontes nossas
    │
    ├── 0 fontes → envia para Kafka: pautas-gap
    │   └── Reporter cobre o tema
    │
    ├── 1 fonte → REESCRITA EDITORIAL (LLM PREMIUM)
    │   ├── Coleta conteúdo da nossa matéria
    │   ├── Coleta artigos dos concorrentes (para contexto)
    │   ├── LLM PREMIUM reescreve com ângulo editorial próprio
    │   └── Publica no WordPress (novo artigo, não sobrescreve)
    │
    └── 2+ fontes → CONSOLIDAÇÃO ANALÍTICA (LLM PREMIUM)
        ├── Coleta conteúdo de todas as matérias nossas
        ├── Coleta artigos dos concorrentes (para contexto adicional)
        ├── LLM PREMIUM consolida em análise aprofundada
        └── Publica no WordPress como matéria de análise
```

### 2.3 Grafo LangGraph V3

```python
# Estrutura do grafo LangGraph do Consolidador V3

nodes = {
    "consumir_mensagem":      consumir_e_validar_mensagem,
    "buscar_materias":        buscar_materias_proprias,
    "detectar_relacionadas":  detectar_materias_relacionadas,
    "rotear":                 rotear_0_1_2_mais,
    "acionar_reporter":       enviar_para_reporter,
    "coletar_fontes":         coletar_fontes_completas,
    "reescrever":             reescrever_editorial,    # 1 fonte
    "consolidar":             consolidar_analitico,    # 2+ fontes
    "publicar":               publicar_wordpress,
    "registrar_memoria":      registrar_na_memoria,
}

edges = {
    "consumir_mensagem"   → "buscar_materias",
    "buscar_materias"     → "detectar_relacionadas",
    "detectar_relacionadas" → "rotear",
    "rotear" → {
        "zero":        "acionar_reporter",
        "um":          "coletar_fontes",
        "dois_mais":   "coletar_fontes",
    },
    "acionar_reporter"    → "registrar_memoria" → END,
    "coletar_fontes" → {
        "reescrever": "reescrever",
        "consolidar": "consolidar",
    },
    "reescrever"          → "publicar",
    "consolidar"          → "publicar",
    "publicar"            → "registrar_memoria" → END,
}
```

### 2.4 Localização dos Arquivos

```
brasileira/
└── consolidador/
    ├── __init__.py
    ├── agent.py              ← ConsolidadorAgent (LangGraph)
    ├── consumer.py           ← KafkaConsumer topic consolidacao
    ├── detector.py           ← DetectorMateraisRelacionadas (TF-IDF + pgvector)
    ├── router.py             ← Roteador 0/1/2+
    ├── rewriter.py           ← ReescritorEditorial (1 fonte)
    ├── consolidator.py       ← ConsolidadorAnalitico (2+ fontes)
    ├── publisher.py          ← PublicadorWordPress (direto)
    ├── memory.py             ← MemoriaConsolidador
    ├── prompts.py            ← System prompts (reescrita + consolidação)
    ├── schemas.py            ← Schemas Pydantic + Kafka
    └── main.py               ← Entrypoint
```

---

## PARTE III — CONSUMER KAFKA (tópico: consolidacao)

### 3.1 Schema da Mensagem de Entrada

O Monitor Concorrência produz mensagens no tópico `consolidacao` quando detecta um tema em capa de concorrente E já temos pelo menos 1 matéria sobre o tema. Se não tivermos nenhuma matéria, o Monitor produz diretamente no `pautas-gap` (sem passar pelo Consolidador).

```python
# brasileira/consolidador/schemas.py

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


class ArtigoConcorrente(BaseModel):
    """Artigo de concorrente detectado na capa."""
    portal: str                   # "G1", "UOL", "Folha", "Estadão", "CNN Brasil"
    titulo: str
    url: str
    resumo: Optional[str] = None
    publicado_em: Optional[datetime] = None
    posicao_capa: int = 99        # 1 = manchete principal, 99 = rodapé


class MensagemConsolidacao(BaseModel):
    """
    Mensagem produzida pelo Monitor Concorrência para o tópico 'consolidacao'.
    
    IMPORTANTE: Esta mensagem só é enviada quando há 1+ matérias nossas sobre o tema.
    Se houver 0 matérias nossas, o Monitor envia direto para 'pautas-gap'.
    """
    tema_id: str                  # Hash do tema, ex: "tema_lula_pec_2026"
    tema_descricao: str           # Descrição textual do tema
    palavras_chave: List[str]     # ["Lula", "PEC", "2026", "Congresso"]
    
    # Contexto dos concorrentes
    num_capas: int                # Quantas capas de concorrentes têm o tema
    portais_detectados: List[str] # ["G1", "UOL", "Folha"]
    artigos_concorrentes: List[ArtigoConcorrente]
    
    # Nossas matérias já identificadas (1+ — senão não viria aqui)
    ids_materias_proprias: List[int]  # IDs dos artigos na tabela 'artigos'
    
    # Urgência
    urgencia: Literal["baixa", "media", "alta", "maxima"]
    detectado_em: datetime = Field(default_factory=datetime.utcnow)
    
    # Metadados para roteamento
    categoria_inferida: Optional[str] = None  # "política", "economia", etc.


class MensagemPautaGap(BaseModel):
    """
    Mensagem enviada para 'pautas-gap' quando:
    - Consolidador detecta 0 matérias nossas sobre o tema, OU
    - Monitor Concorrência detecta tema sem nenhuma cobertura nossa
    """
    tema_id: str
    tema_descricao: str
    palavras_chave: List[str]
    num_capas: int
    portais_detectados: List[str]
    artigos_concorrentes: List[ArtigoConcorrente]
    urgencia: Literal["baixa", "media", "alta", "maxima"]
    tipo: Literal["cobertura_nova", "reforco_cobertura"]
    detectado_em: datetime = Field(default_factory=datetime.utcnow)
    origem: Literal["consolidador", "monitor_concorrencia"] = "consolidador"
```

### 3.2 Implementação do Consumer Kafka

```python
# brasileira/consolidador/consumer.py

import asyncio
import json
import logging
from typing import AsyncIterator, Optional
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from .schemas import MensagemConsolidacao

logger = logging.getLogger("consolidador.consumer")


class ConsolidacaoConsumer:
    """
    Consumer assíncrono do tópico Kafka 'consolidacao'.
    
    Particionamento: por tema_id (garante que o mesmo tema vai para o mesmo consumer).
    Group ID: 'consolidador-v3' (permite múltiplas instâncias com balanceamento).
    """
    
    TOPIC = "consolidacao"
    GROUP_ID = "consolidador-v3"
    
    def __init__(
        self,
        bootstrap_servers: str,
        max_poll_interval_ms: int = 300_000,  # 5 min — síntese LLM pode demorar
        session_timeout_ms: int = 30_000,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.max_poll_interval_ms = max_poll_interval_ms
        self.session_timeout_ms = session_timeout_ms
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
    
    async def start(self) -> None:
        """Inicia o consumer Kafka com retry exponencial."""
        retry_delay = 1
        max_delay = 60
        
        while True:
            try:
                self._consumer = AIOKafkaConsumer(
                    self.TOPIC,
                    bootstrap_servers=self.bootstrap_servers,
                    group_id=self.GROUP_ID,
                    auto_offset_reset="earliest",
                    enable_auto_commit=False,        # Commit manual após processamento
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                    max_poll_interval_ms=self.max_poll_interval_ms,
                    session_timeout_ms=self.session_timeout_ms,
                )
                await self._consumer.start()
                self._running = True
                logger.info(f"Consumer iniciado. Tópico: {self.TOPIC}, Group: {self.GROUP_ID}")
                return
                
            except KafkaConnectionError as e:
                logger.warning(f"Kafka indisponível, tentando em {retry_delay}s: {e}")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_delay)
    
    async def stop(self) -> None:
        """Para o consumer graciosamente."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            logger.info("Consumer parado.")
    
    async def mensagens(self) -> AsyncIterator[MensagemConsolidacao]:
        """
        Iterador assíncrono de mensagens.
        
        Processa uma mensagem por vez. Commit após processamento bem-sucedido.
        Em caso de erro de parsing, loga e avança (não trava o pipeline).
        """
        if not self._consumer:
            raise RuntimeError("Consumer não iniciado. Chame start() primeiro.")
        
        async for msg in self._consumer:
            try:
                payload = msg.value
                mensagem = MensagemConsolidacao(**payload)
                
                logger.info(
                    f"Mensagem recebida: tema={mensagem.tema_id!r} | "
                    f"capas={mensagem.num_capas} | "
                    f"materias_proprias={len(mensagem.ids_materias_proprias)} | "
                    f"urgencia={mensagem.urgencia}"
                )
                
                yield mensagem
                
                # Commit manual após processamento completo
                await self._consumer.commit()
                
            except Exception as e:
                logger.error(
                    f"Erro ao parsear mensagem Kafka (offset={msg.offset}): {e}",
                    exc_info=True
                )
                # NUNCA travar o pipeline por erro de parsing
                # Commit mesmo assim para não reproceesar mensagem corrompida
                await self._consumer.commit()
                continue
```

### 3.3 Producer Kafka (pautas-gap)

```python
# brasileira/consolidador/consumer.py (continuação)

from aiokafka import AIOKafkaProducer
from .schemas import MensagemPautaGap


class PautaGapProducer:
    """
    Producer para o tópico 'pautas-gap'.
    Acionado quando o Consolidador detecta 0 matérias nossas sobre o tema.
    """
    
    TOPIC = "pautas-gap"
    
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer: Optional[AIOKafkaProducer] = None
    
    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str, ensure_ascii=False).encode("utf-8"),
        )
        await self._producer.start()
        logger.info(f"Producer iniciado. Tópico: {self.TOPIC}")
    
    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
    
    async def enviar_pauta_gap(self, mensagem: MensagemPautaGap) -> None:
        """Envia pauta de gap para os Reporters."""
        if not self._producer:
            raise RuntimeError("Producer não iniciado.")
        
        await self._producer.send_and_wait(
            self.TOPIC,
            value=mensagem.model_dump(),
            key=mensagem.tema_id.encode("utf-8"),  # Particionamento por urgência
        )
        
        logger.info(
            f"Pauta gap enviada: tema={mensagem.tema_id!r} | "
            f"urgencia={mensagem.urgencia} | tipo={mensagem.tipo}"
        )
```

---

## PARTE IV — DETECÇÃO DE MATÉRIAS RELACIONADAS

### 4.1 Estratégia Híbrida: TF-IDF + pgvector

A detecção de matérias relacionadas usa **dois níveis de similaridade** complementares:

1. **TF-IDF rápido:** Para triagem inicial. Usa termos compartilhados (keywords, nomes próprios, entidades). Rápido mas não captura paráfrases.
2. **pgvector semântico:** Para validação. Compara embeddings vetoriais das matérias. Captura paráfrases e variações semânticas.

```python
# brasileira/consolidador/detector.py

import asyncio
import logging
import re
from typing import List, Tuple, Optional
import asyncpg
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("consolidador.detector")


# Stopwords portuguesas para TF-IDF
STOPWORDS_PT = [
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para",
    "uma", "os", "no", "se", "na", "por", "mais", "as", "dos",
    "como", "mas", "foi", "ao", "ele", "das", "tem", "à", "seu",
    "sua", "ou", "ser", "quando", "muito", "há", "nos", "já",
    "também", "pelo", "pela", "até", "isso", "ela", "entre",
    "era", "depois", "sem", "mesmo", "aos", "ter", "seus", "suas",
    "num", "numa", "pelos", "pelas", "esse", "essa", "eles", "elas",
    "esta", "este", "nem", "com", "não", "são", "sobre", "após",
]


class MateriaPropria:
    """Representa uma matéria publicada pela brasileira.news."""
    def __init__(
        self,
        id: int,
        titulo: str,
        conteudo: str,
        url: str,
        wp_post_id: int,
        editoria: str,
        publicado_em,
        embedding: Optional[List[float]] = None,
    ):
        self.id = id
        self.titulo = titulo
        self.conteudo = conteudo
        self.url = url
        self.wp_post_id = wp_post_id
        self.editoria = editoria
        self.publicado_em = publicado_em
        self.embedding = embedding
    
    @property
    def texto_completo(self) -> str:
        return f"{self.titulo}\n{self.conteudo}"


class DetectorMateriasRelacionadas:
    """
    Detecta matérias próprias relacionadas a um tema recebido do Monitor Concorrência.
    
    Estratégia em 2 camadas:
    1. Busca por palavras-chave no PostgreSQL (rápida, O(n) com índice GIN)
    2. Validação semântica com pgvector + TF-IDF (precisa, para evitar falsos positivos)
    """
    
    # Janela de tempo para busca (não buscar matérias muito antigas)
    JANELA_HORAS = 72  # 3 dias — temas de capa costumam ser recentes
    
    # Thresholds de similaridade
    TFIDF_THRESHOLD = 0.15    # Mínimo para considerar candidata
    SEMANTIC_THRESHOLD = 0.65  # Mínimo para confirmar como relacionada
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db = db_pool
        self._vectorizer = TfidfVectorizer(
            stop_words=STOPWORDS_PT,
            ngram_range=(1, 2),  # Unigrams e bigrams
            max_features=5000,
            sublinear_tf=True,   # log(tf) — melhora resultados para jornalismo
        )
    
    async def buscar_materias_sobre(
        self,
        palavras_chave: List[str],
        tema_descricao: str,
        janela_horas: int = None,
    ) -> List[MateriaPropria]:
        """
        Busca matérias próprias sobre um tema usando busca híbrida.
        
        Returns:
            Lista de matérias próprias relacionadas ao tema, ordenadas por relevância.
        """
        janela = janela_horas or self.JANELA_HORAS
        
        # 1. Busca inicial por palavras-chave (PostgreSQL full-text ou LIKE)
        candidatas = await self._buscar_por_keywords(palavras_chave, janela)
        
        if not candidatas:
            logger.info(f"Nenhuma matéria candidata encontrada para: {palavras_chave}")
            return []
        
        # 2. Validação com TF-IDF + similaridade semântica
        confirmadas = await self._validar_por_similaridade(
            candidatas=candidatas,
            tema_descricao=tema_descricao,
            palavras_chave=palavras_chave,
        )
        
        logger.info(
            f"Detecção concluída: {len(candidatas)} candidatas → "
            f"{len(confirmadas)} confirmadas como relacionadas"
        )
        
        return confirmadas
    
    async def _buscar_por_keywords(
        self,
        palavras_chave: List[str],
        janela_horas: int,
    ) -> List[MateriaPropria]:
        """
        Busca candidatas no PostgreSQL usando busca por texto.
        
        Usa ILIKE para compatibilidade. Em produção, considerar
        adicionar índice GIN com pg_trgm para melhor performance.
        """
        if not palavras_chave:
            return []
        
        # Constrói condição para pelo menos N palavras-chave
        # Precisamos de pelo menos 2 palavras-chave em comum para ser candidata
        # (exceto se só tivermos 1 palavra-chave)
        min_matches = max(1, len(palavras_chave) // 2)
        
        # Monta query com contagem de matches
        conditions = []
        params = []
        param_idx = 1
        
        for kw in palavras_chave:
            kw_pattern = f"%{kw.lower()}%"
            conditions.append(
                f"(LOWER(titulo) LIKE ${param_idx} OR LOWER(conteudo) LIKE ${param_idx + 1})"
            )
            params.extend([kw_pattern, kw_pattern])
            param_idx += 2
        
        # Janela de tempo
        params.append(janela_horas)
        janela_param = param_idx
        
        # Monta query: seleciona artigos que atendam a pelo menos min_matches condições
        match_sum = " + ".join(
            f"CASE WHEN {cond} THEN 1 ELSE 0 END"
            for cond in conditions
        )
        
        query = f"""
            SELECT 
                id,
                titulo,
                conteudo,
                url_fonte AS url,
                wp_post_id,
                editoria,
                publicado_em
            FROM artigos
            WHERE 
                publicado_em >= NOW() - INTERVAL '1 hour' * ${janela_param}
                AND wp_post_id IS NOT NULL
                AND ({match_sum}) >= {min_matches}
            ORDER BY 
                ({match_sum}) DESC,
                publicado_em DESC
            LIMIT 20
        """
        
        try:
            rows = await self.db.fetch(query, *params)
        except Exception as e:
            logger.error(f"Erro na busca por keywords: {e}", exc_info=True)
            return []
        
        materias = []
        for row in rows:
            materias.append(MateriaPropria(
                id=row["id"],
                titulo=row["titulo"] or "",
                conteudo=row["conteudo"] or "",
                url=row["url"] or "",
                wp_post_id=row["wp_post_id"],
                editoria=row["editoria"] or "",
                publicado_em=row["publicado_em"],
            ))
        
        return materias
    
    async def _validar_por_similaridade(
        self,
        candidatas: List[MateriaPropria],
        tema_descricao: str,
        palavras_chave: List[str],
    ) -> List[MateriaPropria]:
        """
        Valida candidatas usando TF-IDF cosine similarity.
        
        O tema_descricao é tratado como o "documento de consulta" e as
        matérias são o corpus. Matérias com similaridade >= threshold
        são confirmadas como relacionadas.
        """
        if not candidatas:
            return []
        
        # Prepara textos
        query_texto = f"{tema_descricao} {' '.join(palavras_chave)}"
        corpus = [query_texto] + [m.texto_completo for m in candidatas]
        
        try:
            # Ajusta vectorizer ao corpus + query
            tfidf_matrix = self._vectorizer.fit_transform(corpus)
            
            # Similaridade: query (índice 0) vs cada matéria (índices 1..N)
            query_vec = tfidf_matrix[0:1]
            materias_vecs = tfidf_matrix[1:]
            
            scores = cosine_similarity(query_vec, materias_vecs)[0]
            
            # Filtra por threshold
            confirmadas = []
            for i, (materia, score) in enumerate(zip(candidatas, scores)):
                if score >= self.TFIDF_THRESHOLD:
                    logger.debug(
                        f"Matéria confirmada (score={score:.3f}): "
                        f"{materia.titulo[:60]!r}"
                    )
                    confirmadas.append(materia)
                else:
                    logger.debug(
                        f"Matéria descartada (score={score:.3f}): "
                        f"{materia.titulo[:60]!r}"
                    )
            
            return confirmadas
            
        except Exception as e:
            logger.error(f"Erro no TF-IDF: {e}", exc_info=True)
            # Fallback: retorna todas as candidatas (melhor false positive que miss)
            return candidatas
    
    async def buscar_por_ids(self, ids: List[int]) -> List[MateriaPropria]:
        """
        Busca matérias por IDs específicos (quando o Monitor já identificou).
        Usado quando a mensagem Kafka já vem com ids_materias_proprias preenchidos.
        """
        if not ids:
            return []
        
        query = """
            SELECT id, titulo, conteudo, url_fonte AS url, wp_post_id, editoria, publicado_em
            FROM artigos
            WHERE id = ANY($1) AND wp_post_id IS NOT NULL
        """
        
        try:
            rows = await self.db.fetch(query, ids)
            return [
                MateriaPropria(
                    id=row["id"],
                    titulo=row["titulo"] or "",
                    conteudo=row["conteudo"] or "",
                    url=row["url"] or "",
                    wp_post_id=row["wp_post_id"],
                    editoria=row["editoria"] or "",
                    publicado_em=row["publicado_em"],
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Erro ao buscar por IDs {ids}: {e}", exc_info=True)
            return []
```

### 4.2 Busca Semântica com pgvector (Nível Avançado)

```python
# brasileira/consolidador/detector.py (continuação)

class DetectorMateriasRelacionadas:
    # ... (código anterior)
    
    async def buscar_semanticamente(
        self,
        embedding_tema: List[float],
        limit: int = 10,
    ) -> List[Tuple[MateriaPropria, float]]:
        """
        Busca matérias semanticamente similares usando pgvector.
        
        Usa cosine distance (1 - cosine_similarity).
        Threshold: distância < 0.35 = similar (equivale a similarity > 0.65).
        
        Requer que a tabela 'artigos' tenha coluna 'embedding vector(1536)'.
        """
        query = """
            SELECT 
                id, titulo, conteudo, url_fonte AS url,
                wp_post_id, editoria, publicado_em,
                1 - (embedding <=> $1::vector) AS similarity
            FROM artigos
            WHERE 
                embedding IS NOT NULL
                AND wp_post_id IS NOT NULL
                AND publicado_em >= NOW() - INTERVAL '72 hours'
                AND 1 - (embedding <=> $1::vector) > 0.65
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """
        
        try:
            embedding_str = "[" + ",".join(str(x) for x in embedding_tema) + "]"
            rows = await self.db.fetch(query, embedding_str, limit)
            
            result = []
            for row in rows:
                materia = MateriaPropria(
                    id=row["id"],
                    titulo=row["titulo"] or "",
                    conteudo=row["conteudo"] or "",
                    url=row["url"] or "",
                    wp_post_id=row["wp_post_id"],
                    editoria=row["editoria"] or "",
                    publicado_em=row["publicado_em"],
                )
                result.append((materia, float(row["similarity"])))
            
            return result
            
        except Exception as e:
            logger.error(f"Erro na busca semântica pgvector: {e}", exc_info=True)
            return []
```

---

## PARTE V — LÓGICA 0/1/2+ (QUANDO ACIONAR REPORTER vs. REESCREVER vs. CONSOLIDAR)

### 5.1 Roteador de Decisão

Esta é a **lógica mais importante** do Consolidador. Determina o que fazer com base no número de matérias próprias encontradas sobre o tema.

```python
# brasileira/consolidador/router.py

import logging
from typing import List, Literal
from .detector import MateriaPropria
from .schemas import MensagemConsolidacao

logger = logging.getLogger("consolidador.router")


# Tipo de ação decidida pelo roteador
TipoAcao = Literal["acionar_reporter", "reescrever", "consolidar"]


class DecisaoRoteador:
    """Resultado da decisão do roteador."""
    def __init__(
        self,
        acao: TipoAcao,
        materias: List[MateriaPropria],
        justificativa: str,
        prioridade: int,  # 1-10, maior = mais urgente
    ):
        self.acao = acao
        self.materias = materias
        self.justificativa = justificativa
        self.prioridade = prioridade
    
    def __repr__(self) -> str:
        return (
            f"DecisaoRoteador(acao={self.acao!r}, "
            f"materias={len(self.materias)}, "
            f"prioridade={self.prioridade})"
        )


class RoteadorConsolidador:
    """
    Implementa a lógica 0/1/2+ do Consolidador V3.
    
    REGRAS INVIOLÁVEIS:
    1. 0 fontes nossas → acionar_reporter (vai para pautas-gap)
    2. 1 fonte → reescrever (com ângulo editorial próprio)
    3. 2+ fontes → consolidar (análise aprofundada)
    4. Portal TIER-1 (G1, Folha, Estadão) em capa NÃO precisa de 3+ matérias
    5. Tudo baseado em capas dos CONCORRENTES, não em número arbitrário interno
    """
    
    # Portais de TIER-1: presença na capa deles = alta relevância
    PORTAIS_TIER1 = {"G1", "Folha", "Estadão", "UOL", "CNN Brasil"}
    PORTAIS_TIER2 = {"R7", "Terra", "Metrópoles", "Band News", "Correio Braziliense"}
    
    def rotear(
        self,
        mensagem: MensagemConsolidacao,
        materias_proprias: List[MateriaPropria],
    ) -> DecisaoRoteador:
        """
        Decide a ação com base nas matérias próprias encontradas.
        
        Args:
            mensagem: Mensagem do Monitor Concorrência
            materias_proprias: Matérias nossas sobre o tema (pode ser vazia)
        
        Returns:
            DecisaoRoteador com a ação decidida
        """
        n = len(materias_proprias)
        
        # Calcula prioridade baseada em capas de concorrentes
        prioridade = self._calcular_prioridade(mensagem)
        
        if n == 0:
            # CASO 0: Não temos NADA sobre o tema
            # → Acionar Reporter para cobertura imediata
            justificativa = (
                f"0 matérias próprias encontradas. "
                f"Tema em {mensagem.num_capas} capa(s) de concorrentes "
                f"({', '.join(mensagem.portais_detectados)}). "
                f"Reporter deve cobrir imediatamente."
            )
            logger.info(f"ROTA: acionar_reporter | {justificativa}")
            return DecisaoRoteador(
                acao="acionar_reporter",
                materias=[],
                justificativa=justificativa,
                prioridade=prioridade,
            )
        
        elif n == 1:
            # CASO 1: Temos exatamente 1 matéria sobre o tema
            # → REESCREVER com ângulo editorial próprio
            # Contexto dos concorrentes enriquece a reescrita
            justificativa = (
                f"1 matéria própria encontrada: {materias_proprias[0].titulo[:60]!r}. "
                f"Reescrevendo com ângulo editorial próprio usando contexto de "
                f"{mensagem.num_capas} fonte(s) concorrentes."
            )
            logger.info(f"ROTA: reescrever | {justificativa}")
            return DecisaoRoteador(
                acao="reescrever",
                materias=materias_proprias,
                justificativa=justificativa,
                prioridade=prioridade,
            )
        
        else:
            # CASO 2+: Temos 2 ou mais matérias sobre o tema
            # → CONSOLIDAR em análise aprofundada
            justificativa = (
                f"{n} matérias próprias encontradas. "
                f"Consolidando em análise aprofundada com {mensagem.num_capas} "
                f"fonte(s) de concorrentes como contexto adicional."
            )
            logger.info(f"ROTA: consolidar | {justificativa}")
            return DecisaoRoteador(
                acao="consolidar",
                materias=materias_proprias,
                justificativa=justificativa,
                prioridade=prioridade,
            )
    
    def _calcular_prioridade(self, mensagem: MensagemConsolidacao) -> int:
        """
        Calcula prioridade 1-10 baseada em:
        - Número de capas de concorrentes
        - Tier dos portais que colocaram na capa
        - Urgência declarada pelo Monitor
        """
        prioridade = 1
        
        # Boost por urgência
        urgencia_boost = {
            "baixa": 0,
            "media": 2,
            "alta": 4,
            "maxima": 6,
        }
        prioridade += urgencia_boost.get(mensagem.urgencia, 0)
        
        # Boost por portais tier-1 na capa
        portais_tier1_na_capa = set(mensagem.portais_detectados) & self.PORTAIS_TIER1
        prioridade += len(portais_tier1_na_capa)  # +1 por portal tier-1
        
        # Boost por número de capas
        if mensagem.num_capas >= 4:
            prioridade += 2  # 4+ capas = potencial manchete
        elif mensagem.num_capas >= 2:
            prioridade += 1
        
        return min(10, prioridade)
```

### 5.2 Tabela de Decisão

| N° Matérias Nossas | N° Capas Concorrentes | Ação | Output |
|---------------------|----------------------|------|--------|
| 0 | qualquer | `acionar_reporter` | Kafka: `pautas-gap` |
| 1 | 1 (tier-2) | `reescrever` | WordPress |
| 1 | 1+ (tier-1) | `reescrever` (alta prioridade) | WordPress |
| 1 | 2+ | `reescrever` (muito urgente) | WordPress |
| 2 | qualquer | `consolidar` | WordPress |
| 3+ | qualquer | `consolidar` (análise completa) | WordPress |
| 4+ | 4+ | `consolidar` + `breaking_candidate` | WordPress + Curador |

### 5.3 Regra Inviolável: Portal Tier-1 É Relevante por Si Só

```python
# ERRADO (mentalidade V2):
if len(materias_proprias) < 3:
    return  # Descarta

# CORRETO (V3):
# Se G1 colocou na capa, é relevante.
# Se Folha colocou na capa, é relevante.
# Não precisamos de 3 matérias para determinar importância.
# 1 capa do G1 = acionar reescrita imediata se tivermos 1 matéria.
```

---

## PARTE VI — REESCRITA EDITORIAL (1 FONTE)

### 6.1 Quando Ocorre

Quando o Consolidador detecta exatamente **1 matéria própria** sobre o tema que está na capa de concorrentes. O objetivo é:

1. Pegar nossa matéria existente (pode ser um artigo simples, baseado em RSS)
2. Usar o contexto dos artigos dos concorrentes para **enriquecer** o entendimento
3. Reescrever com **ângulo editorial próprio** — não é um clone da nossa matéria nem dos concorrentes
4. Publicar como **novo artigo** (não sobrescreve o original)

### 6.2 System Prompt — Reescrita Editorial

```python
# brasileira/consolidador/prompts.py

SYSTEM_PROMPT_REESCRITA = """Você é o Editor Especialista da brasileira.news, portal jornalístico brasileiro de referência.

Sua missão: Reescrever uma matéria existente com ângulo editorial PRÓPRIO, incorporando contexto adicional dos concorrentes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGRA DE OURO: TOLERÂNCIA ZERO PARA ALUCINAÇÃO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRITAMENTE PROIBIDO inventar fatos, dados, estatísticas, declarações ou citações que não estejam presentes nas fontes fornecidas.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O QUE É UMA REESCRITA EDITORIAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NÃO é uma tradução da matéria original para palavras diferentes
- NÃO é uma colagem de trechos dos concorrentes
- É uma NOVA LEITURA do fato, com perspectiva editorial própria
- Incorpora contexto adicional dos concorrentes para ENRIQUECER a análise
- Destaca o que a brasileira.news considera mais relevante para o leitor brasileiro
- Pode ter ênfase diferente da matéria original (ex: impacto econômico vs. político)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DIFERENCIAÇÃO EDITORIAL OBRIGATÓRIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Escolha UM ângulo editorial diferenciador para a reescrita:
- IMPACTO NO CIDADÃO: O que este fato muda na vida do brasileiro comum?
- CONTEXTO HISTÓRICO: Este fato se encaixa em qual padrão maior?
- PERSPECTIVA ECONÔMICA: Quais as implicações financeiras?
- ANÁLISE POLÍTICA: Quem ganha e quem perde com isso?
- DIMENSÃO SOCIAL: Como isso afeta diferentes grupos da sociedade?

Indique o ângulo escolhido no campo "angulo_editorial" do JSON.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTILO JORNALÍSTICO BRASILEIRO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Português do Brasil formal mas acessível — sem tecnicismos desnecessários
- Tom informativo e analítico, sem sensacionalismo
- Presunção de inocência: "suspeito de", "acusado de", "investigado por"
- Números: por extenso de zero a dez, numerais de 11 em diante
- Moedas: R$ antes do número; acima de mil: R$ 1,5 milhão; acima de bilhão: R$ 2,3 bilhões
- Datas: DD/MM/AAAA no texto; "ontem", "hoje", "na última segunda" quando contextual
- Citar nossa fonte original COM LINK e as fontes dos concorrentes COM LINK

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRUTURA OBRIGATÓRIA (HTML — sem Markdown)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. TÍTULO: 65-90 caracteres. Palavra-chave principal nos primeiros 40 chars. Sem prefixos genéricos como "URGENTE:".
2. LIDE (1º parágrafo em <p>): Responda O quê, Quem, Quando, Onde, Por quê, Como — máximo 60 palavras.
3. CONTEXTO (2º parágrafo em <p>): O que estava acontecendo antes deste fato?
4. DESENVOLVIMENTO: 3-5 parágrafos em <p> com os fatos principais.
   - Use <h2> a cada 2-3 parágrafos com subtítulos informativos
   - Use <strong> apenas em dados numéricos e nomes cruciais
   - Inclua aspas REAIS das fontes em <blockquote> (nunca invente aspas)
   - Cite nossa fonte original: "Conforme publicado anteriormente pela <a href="URL">brasileira.news</a>"
   - Cite concorrentes consultados: "De acordo com o <a href="URL" rel="nofollow noopener">G1</a>"
5. ANÁLISE EDITORIAL: 1-2 parágrafos com a perspectiva diferenciada escolhida
6. PERSPECTIVAS: O que pode acontecer a seguir? (quando pertinente)
7. BLOCO DE FONTES (ao final do conteúdo):
   <h2>Fontes consultadas</h2>
   <ul><li><a href="URL" rel="nofollow noopener">Nome do Veículo</a></li></ul>

PROIBIDO: asteriscos (**), underscores (__), cerquilhas (#), qualquer Markdown.
OBRIGATÓRIO: Todo conteúdo em HTML semântico.
Extensão mínima: 500 palavras. Extensão ideal: 700-900 palavras.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAÍDA OBRIGATÓRIA (JSON)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Retorne APENAS JSON válido sem texto extra antes ou depois:

{
  "titulo": "string — 65-90 chars",
  "conteudo": "string — HTML completo",
  "excerpt": "string — 2 frases objetivas, máx 300 chars, sem aspas",
  "tags": ["3 a 5 entidades reais — pessoas, instituições, leis"],
  "seo_title": "string — máx 60 chars, keyword no início",
  "seo_description": "string — máx 155 chars, inclua CTA sutil",
  "categoria": "string — UMA das categorias listadas",
  "angulo_editorial": "string — ângulo diferenciador escolhido",
  "imagem_busca_gov": "string — 2-3 palavras para busca em banco gov",
  "imagem_busca_commons": "string — nome formal para Wikimedia Commons",
  "block_stock_images": true,
  "legenda_imagem": "string — legenda factual máx 150 chars",
  "tipo_conteudo": "reescrita_editorial"
}"""


PROMPT_REESCRITA_TEMPLATE = """Abaixo estão os materiais para a reescrita editorial:

═══════════════════════════════════════
NOSSA MATÉRIA ORIGINAL
═══════════════════════════════════════
Título: {titulo_original}
URL: {url_original}
Publicado em: {publicado_em}

Conteúdo:
{conteudo_original}

═══════════════════════════════════════
CONTEXTO: O QUE OS CONCORRENTES ESTÃO PUBLICANDO
(Use apenas para contexto adicional e aspas — não reproduza)
═══════════════════════════════════════
{contexto_concorrentes}

═══════════════════════════════════════
METADADOS DO TEMA
═══════════════════════════════════════
Tema detectado: {tema_descricao}
Palavras-chave: {palavras_chave}
Portais com tema na capa: {portais_detectados}
Número de capas: {num_capas}
Urgência: {urgencia}

═══════════════════════════════════════
CATEGORIAS DISPONÍVEIS
═══════════════════════════════════════
{categorias}

─────────────────────────────────────
Agora produza a reescrita editorial em JSON conforme as instruções do sistema.
A reescrita deve ter ângulo editorial PRÓPRIO, diferente da nossa matéria original
e dos artigos dos concorrentes. Não é uma colagem — é uma nova perspectiva editorial."""
```

### 6.3 Implementação do Reescritor

```python
# brasileira/consolidador/rewriter.py

import json
import logging
from typing import Dict, Any, List, Optional
from .detector import MateriaPropria
from .schemas import MensagemConsolidacao, ArtigoConcorrente
from .prompts import SYSTEM_PROMPT_REESCRITA, PROMPT_REESCRITA_TEMPLATE

logger = logging.getLogger("consolidador.rewriter")

CATEGORIAS = [
    "Política", "Economia", "Esportes", "Tecnologia", "Saúde",
    "Educação", "Ciência", "Cultura/Entretenimento", "Mundo/Internacional",
    "Meio Ambiente", "Segurança/Justiça", "Sociedade", "Brasil (geral)",
    "Regionais", "Opinião/Análise", "Últimas Notícias",
]


class ReescritorEditorial:
    """
    Reescreve uma matéria existente com ângulo editorial próprio.
    Usa LLM PREMIUM para máxima qualidade.
    """
    
    def __init__(self, smart_router):
        """
        Args:
            smart_router: SmartLLMRouter V3 (componente #1)
        """
        self.router = smart_router
    
    async def reescrever(
        self,
        materia: MateriaPropria,
        mensagem: MensagemConsolidacao,
    ) -> Dict[str, Any]:
        """
        Reescreve a matéria com ângulo editorial próprio.
        
        Args:
            materia: Nossa matéria existente sobre o tema
            mensagem: Contexto do Monitor Concorrência (concorrentes, capas)
        
        Returns:
            Dicionário com todos os campos para publicação no WordPress
        """
        # Formata contexto dos concorrentes
        contexto_concorrentes = self._formatar_contexto_concorrentes(
            mensagem.artigos_concorrentes
        )
        
        # Monta o prompt
        prompt = PROMPT_REESCRITA_TEMPLATE.format(
            titulo_original=materia.titulo,
            url_original=materia.url,
            publicado_em=materia.publicado_em.strftime("%d/%m/%Y %H:%M") if materia.publicado_em else "N/A",
            conteudo_original=materia.conteudo[:3000],  # Limita para não exceder context
            contexto_concorrentes=contexto_concorrentes,
            tema_descricao=mensagem.tema_descricao,
            palavras_chave=", ".join(mensagem.palavras_chave),
            portais_detectados=", ".join(mensagem.portais_detectados),
            num_capas=mensagem.num_capas,
            urgencia=mensagem.urgencia,
            categorias="\n".join(f"- {c}" for c in CATEGORIAS),
        )
        
        # Chama LLM PREMIUM via SmartLLMRouter
        logger.info(
            f"Iniciando reescrita editorial: {materia.titulo[:60]!r} | "
            f"task=reescrita_editorial | tier=PREMIUM"
        )
        
        response = await self.router.complete(
            task_type="consolidacao_sintese",  # tier PREMIUM
            system_prompt=SYSTEM_PROMPT_REESCRITA,
            user_prompt=prompt,
            response_format="json",
            temperature=0.7,   # Alguma criatividade para ângulo editorial
            max_tokens=4000,
        )
        
        # Parse da resposta JSON
        try:
            artigo = json.loads(response.content)
            artigo["tipo_conteudo"] = "reescrita_editorial"
            artigo["materia_original_id"] = materia.id
            artigo["materia_original_wp_id"] = materia.wp_post_id
            artigo["tema_id"] = mensagem.tema_id
            artigo["llm_model"] = response.model
            artigo["llm_cost"] = response.cost
            
            logger.info(
                f"Reescrita gerada com sucesso: {artigo.get('titulo', 'N/A')[:60]!r} | "
                f"modelo={response.model} | custo=R${response.cost:.4f}"
            )
            
            return artigo
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM retornou JSON inválido: {e}\nConteúdo: {response.content[:500]}")
            # Tenta extrair JSON do conteúdo (às vezes LLM adiciona texto antes/depois)
            artigo = self._extrair_json_forcado(response.content)
            if artigo:
                return artigo
            raise ValueError(f"Impossível parsear resposta do LLM: {e}")
    
    def _formatar_contexto_concorrentes(
        self,
        artigos: List[ArtigoConcorrente],
    ) -> str:
        """Formata artigos dos concorrentes para o prompt."""
        if not artigos:
            return "(Sem artigos de concorrentes disponíveis)"
        
        blocos = []
        for i, artigo in enumerate(artigos[:5], 1):  # Limita a 5
            bloco = f"[Fonte {i}: {artigo.portal}]\n"
            bloco += f"Título: {artigo.titulo}\n"
            bloco += f"URL: {artigo.url}\n"
            if artigo.resumo:
                bloco += f"Resumo: {artigo.resumo[:500]}\n"
            bloco += f"Posição na capa: {artigo.posicao_capa}ª"
            blocos.append(bloco)
        
        return "\n\n".join(blocos)
    
    def _extrair_json_forcado(self, texto: str) -> Optional[Dict[str, Any]]:
        """Tenta extrair JSON mesmo com texto extra antes/depois."""
        import re
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None
```

---

## PARTE VII — CONSOLIDAÇÃO ANALÍTICA (2+ FONTES)

### 7.1 Quando Ocorre

Quando o Consolidador detecta **2 ou mais matérias próprias** sobre o tema. O objetivo é:

1. Pegar todas as nossas matérias sobre o tema
2. Usar contexto dos concorrentes como referência adicional
3. Criar uma **matéria de análise aprofundada** que:
   - Sintetiza todos os ângulos cobertos por nós
   - Adiciona perspectiva analítica que nenhuma matéria individual oferecia
   - Se diferencia dos concorrentes por ter visão integrada
4. Publicar como **nova matéria** de análise (categoria "Opinião/Análise" ou editoria pertinente)

### 7.2 System Prompt — Consolidação Analítica

```python
# brasileira/consolidador/prompts.py (continuação)

SYSTEM_PROMPT_CONSOLIDACAO = """Você é o Editor-Chefe da brasileira.news, portal jornalístico brasileiro de referência.

Sua missão: Criar uma matéria CONSOLIDADA de análise aprofundada, sintetizando múltiplas reportagens próprias sobre o mesmo tema.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGRA DE OURO: TOLERÂNCIA ZERO PARA ALUCINAÇÃO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRITAMENTE PROIBIDO inventar fatos, dados, estatísticas, nomes ou declarações que não estejam nas fontes fornecidas.
PROIBIDO: parágrafos copiados das fontes originais.
OBRIGATÓRIO: síntese original com voz editorial própria.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O QUE É UMA MATÉRIA CONSOLIDADA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A matéria consolidada é o CARRO-CHEFE do portal — nosso produto editorial de maior valor:
- JAMAIS copie parágrafos das fontes — SINTETIZE com voz editorial própria
- Todas as nossas fontes DEVEM ser citadas NO TEXTO com link
- Produza ANÁLISE ORIGINAL que nenhuma matéria individual oferecia
- Conecte perspectivas diferentes: O que a cobertura completa revela?
- Identifique padrões, contradições ou complementaridades entre nossas reportagens
- Compare discretamente com o que os concorrentes estão cobrindo (sem exaltar concorrentes)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRUTURA DA MATÉRIA CONSOLIDADA (HTML obrigatório)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. TÍTULO: 70-95 caracteres. Mostre que é uma análise abrangente.
   Exemplo: "Como o Congresso passou em silêncio a PEC que muda a aposentadoria de 40 milhões"
   NÃO use prefixos genéricos como "Análise:" ou "Especial:".

2. LIDE (1º parágrafo <p>): 
   — O que está acontecendo (fato central)?
   — Por que é importante (impacto)?
   — O que esta análise revela que as matérias individuais não mostravam?
   Máximo 80 palavras.

3. CORPO DA ANÁLISE:
   Mínimo 800 palavras, máximo 1.400 palavras.
   
   ESTRUTURA RECOMENDADA:
   <h2>O que aconteceu</h2>
   (2-3 parágrafos com os fatos centrais de todas as fontes)
   
   <h2>O que nossa cobertura revelou</h2>
   (Síntese das perspectivas das nossas matérias — cite cada uma)
   
   <h2>O que os números dizem</h2>
   (Dados e estatísticas das fontes — quando disponíveis)
   
   <h2>Quem são os atores e o que disseram</h2>
   (Declarações reais em <blockquote> — APENAS aspas literais das fontes)
   
   <h2>O que pode acontecer</h2>
   (Perspectivas e implicações — baseadas nos fatos, não em especulação)

   REGRAS DE FORMATAÇÃO:
   - Todo texto em <p> — NUNCA texto solto fora de tags
   - Citações em <blockquote>atribuição e aspas literais da fonte</blockquote>
   - Links obrigatórios: De acordo com <a href="URL">brasileira.news</a> em [data]
   - Links concorrentes: Segundo o <a href="URL" rel="nofollow noopener">Portal X</a>
   - Use <strong> em dados numéricos cruciais e nomes na primeira aparição
   - Use <ul><li> para listas de pontos, implicações, cronologias
   - PROIBIDO: **, __, ##, qualquer Markdown

4. BLOCO DE FONTES (ao final):
   <h2>Fontes consultadas</h2>
   <ul>
     <li><a href="URL">brasileira.news — [Título da matéria 1]</a></li>
     <li><a href="URL">brasileira.news — [Título da matéria 2]</a></li>
     <li><a href="URL" rel="nofollow noopener">Portal Concorrente</a></li>
   </ul>

5. EXCERPT: 2-3 frases que resumam a análise, máx 350 caracteres.
   Deve ser diferente do lide. Inclua o diferencial da análise integrada.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTILO JORNALÍSTICO BRASILEIRO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Português do Brasil formal, acessível, sem jargões técnicos
- Tom analítico e informativo — sem sensacionalismo, sem tom opinativo excessivo
- Presunção de inocência: "acusado de", "suspeito de", "investigado por"
- Números: por extenso de zero a dez; numerais de 11 em diante
- Moedas: R$ 1,5 milhão; US$ 2,3 bilhões; EUR 500 milhões
- Porcentagens: 12,5% (com vírgula decimal)
- Datas no formato DD/MM/AAAA quando explícitas

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAÍDA OBRIGATÓRIA (JSON puro — sem texto antes ou depois)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "titulo": "string — 70-95 chars",
  "conteudo": "string — HTML completo da matéria",
  "excerpt": "string — 2-3 frases, máx 350 chars",
  "tags": ["3 a 6 entidades reais — pessoas, org, leis, lugares"],
  "seo_title": "string — máx 60 chars, keyword principal no início",
  "seo_description": "string — máx 155 chars, inclua 'Entenda', 'Saiba mais' ou similar",
  "categoria": "string — UMA das categorias disponíveis",
  "fontes_proprias_citadas": ["URL da matéria 1", "URL da matéria 2"],
  "fontes_concorrentes_citadas": ["URL concorrente 1"],
  "imagem_busca_gov": "string — 2-3 palavras para banco gov",
  "imagem_busca_commons": "string — nome formal Wikimedia Commons",
  "block_stock_images": true,
  "legenda_imagem": "string — legenda factual máx 150 chars",
  "tipo_conteudo": "consolidacao_analitica",
  "num_fontes_proprias": 0,
  "resumo_editorial": "string — 1 frase sobre o ângulo analítico principal"
}"""


PROMPT_CONSOLIDACAO_TEMPLATE = """Abaixo estão as matérias para consolidação analítica:

═══════════════════════════════════════
NOSSAS MATÉRIAS ({n_materias} matérias sobre o tema)
═══════════════════════════════════════
{materias_proprias}

═══════════════════════════════════════
CONTEXTO: O QUE OS CONCORRENTES ESTÃO PUBLICANDO
(Referência para contexto — não reproduza)
═══════════════════════════════════════
{contexto_concorrentes}

═══════════════════════════════════════
METADADOS DO TEMA
═══════════════════════════════════════
Tema: {tema_descricao}
Palavras-chave: {palavras_chave}
Portais com o tema na capa: {portais_detectados} ({num_capas} capas)
Urgência: {urgencia}

═══════════════════════════════════════
CATEGORIAS DISPONÍVEIS
═══════════════════════════════════════
{categorias}

─────────────────────────────────────
Produza a matéria consolidada em JSON conforme as instruções.
A análise deve revelar o que nenhuma das matérias individuais mostrava sozinha.
Mínimo 800 palavras no campo "conteudo"."""
```

### 7.3 Implementação do Consolidador Analítico

```python
# brasileira/consolidador/consolidator.py

import json
import logging
from typing import Dict, Any, List, Optional
from .detector import MateriaPropria
from .schemas import MensagemConsolidacao, ArtigoConcorrente
from .prompts import (
    SYSTEM_PROMPT_CONSOLIDACAO,
    PROMPT_CONSOLIDACAO_TEMPLATE,
    CATEGORIAS,
)

logger = logging.getLogger("consolidador.consolidator")

MAX_CONTEUDO_POR_FONTE = 2000   # chars — para não explodir o context window
MAX_FONTES_PROCESSADAS = 7       # Processa no máximo 7 matérias


class ConsolidadorAnalitico:
    """
    Consolida 2+ matérias próprias em análise aprofundada.
    Usa LLM PREMIUM (task: consolidacao_sintese).
    """
    
    def __init__(self, smart_router):
        self.router = smart_router
    
    async def consolidar(
        self,
        materias: List[MateriaPropria],
        mensagem: MensagemConsolidacao,
    ) -> Dict[str, Any]:
        """
        Consolida múltiplas matérias em análise aprofundada.
        
        Args:
            materias: Nossas matérias (2+) sobre o tema
            mensagem: Contexto do Monitor Concorrência
        
        Returns:
            Dicionário com campos para publicação WordPress
        """
        # Seleciona e ordena matérias (mais recentes e relevantes primeiro)
        materias_selecionadas = self._selecionar_materias(materias)
        
        # Formata matérias para o prompt
        materias_texto = self._formatar_materias_proprias(materias_selecionadas)
        contexto_concorrentes = self._formatar_contexto_concorrentes(
            mensagem.artigos_concorrentes
        )
        
        # Monta o prompt
        prompt = PROMPT_CONSOLIDACAO_TEMPLATE.format(
            n_materias=len(materias_selecionadas),
            materias_proprias=materias_texto,
            contexto_concorrentes=contexto_concorrentes,
            tema_descricao=mensagem.tema_descricao,
            palavras_chave=", ".join(mensagem.palavras_chave),
            portais_detectados=", ".join(mensagem.portais_detectados),
            num_capas=mensagem.num_capas,
            urgencia=mensagem.urgencia,
            categorias="\n".join(f"- {c}" for c in CATEGORIAS),
        )
        
        logger.info(
            f"Iniciando consolidação: {len(materias_selecionadas)} matérias | "
            f"tema={mensagem.tema_id!r} | tier=PREMIUM"
        )
        
        # Chama LLM PREMIUM via SmartLLMRouter
        response = await self.router.complete(
            task_type="consolidacao_sintese",  # Tier PREMIUM obrigatório
            system_prompt=SYSTEM_PROMPT_CONSOLIDACAO,
            user_prompt=prompt,
            response_format="json",
            temperature=0.6,   # Balanceia criatividade e fidelidade aos fatos
            max_tokens=5000,   # Análise aprofundada precisa de mais tokens
        )
        
        # Parse e validação
        try:
            artigo = json.loads(response.content)
            
            # Garante campos obrigatórios
            artigo["tipo_conteudo"] = "consolidacao_analitica"
            artigo["num_fontes_proprias"] = len(materias_selecionadas)
            artigo["ids_materias_origem"] = [m.id for m in materias_selecionadas]
            artigo["tema_id"] = mensagem.tema_id
            artigo["llm_model"] = response.model
            artigo["llm_cost"] = response.cost
            
            logger.info(
                f"Consolidação gerada: {artigo.get('titulo', 'N/A')[:60]!r} | "
                f"modelo={response.model} | custo=R${response.cost:.4f}"
            )
            
            return artigo
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido do LLM: {e}")
            artigo = self._extrair_json_forcado(response.content)
            if artigo:
                return artigo
            raise ValueError(f"LLM retornou resposta não parseável: {e}")
    
    def _selecionar_materias(
        self,
        materias: List[MateriaPropria],
    ) -> List[MateriaPropria]:
        """
        Seleciona e ordena as matérias para consolidação.
        - Ordena por data (mais recente primeiro)
        - Limita a MAX_FONTES_PROCESSADAS
        - Remove matérias sem conteúdo útil
        """
        # Filtra matérias com conteúdo mínimo
        validas = [m for m in materias if len(m.conteudo.strip()) >= 50]
        
        # Ordena por data (mais recente primeiro)
        validas.sort(
            key=lambda m: m.publicado_em if m.publicado_em else 0,
            reverse=True
        )
        
        return validas[:MAX_FONTES_PROCESSADAS]
    
    def _formatar_materias_proprias(
        self,
        materias: List[MateriaPropria],
    ) -> str:
        """Formata nossas matérias para o prompt de consolidação."""
        blocos = []
        for i, m in enumerate(materias, 1):
            publicado = m.publicado_em.strftime("%d/%m/%Y %H:%M") if m.publicado_em else "N/A"
            conteudo = m.conteudo[:MAX_CONTEUDO_POR_FONTE]
            if len(m.conteudo) > MAX_CONTEUDO_POR_FONTE:
                conteudo += "...[truncado]"
            
            bloco = (
                f"[MATÉRIA {i}]\n"
                f"Título: {m.titulo}\n"
                f"URL: {m.url}\n"
                f"Publicado: {publicado}\n"
                f"Editoria: {m.editoria}\n"
                f"Conteúdo:\n{conteudo}"
            )
            blocos.append(bloco)
        
        return "\n\n" + "─" * 50 + "\n\n".join(blocos)
    
    def _formatar_contexto_concorrentes(
        self,
        artigos: List[ArtigoConcorrente],
    ) -> str:
        """Formata artigos dos concorrentes como contexto."""
        if not artigos:
            return "(Sem artigos de concorrentes disponíveis)"
        
        blocos = []
        for artigo in artigos[:5]:
            bloco = (
                f"• {artigo.portal}: {artigo.titulo}\n"
                f"  URL: {artigo.url}"
            )
            if artigo.resumo:
                bloco += f"\n  Resumo: {artigo.resumo[:300]}"
            blocos.append(bloco)
        
        return "\n".join(blocos)
    
    def _extrair_json_forcado(self, texto: str) -> Optional[Dict[str, Any]]:
        """Extrai JSON mesmo com texto extra."""
        import re
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None
```

---

## PARTE VIII — INTEGRAÇÃO COM MONITOR CONCORRÊNCIA

### 8.1 Contrato de Interface

O Monitor Concorrência e o Consolidador se comunicam **exclusivamente via Kafka**. Não há chamadas diretas, compartilhamento de estado ou acoplamento. O Monitor produz mensagens no tópico `consolidacao`; o Consolidador consome e age.

### 8.2 O Que o Monitor Envia vs. O Que o Consolidador Espera

**O Monitor envia para `consolidacao` quando:**
1. Detecta um tema na capa de 1+ concorrentes
2. E já encontrou 1+ matérias nossas sobre o tema (busca prévia no PostgreSQL)

**O Monitor envia para `pautas-gap` diretamente quando:**
1. Detecta um tema na capa de 1+ concorrentes
2. E NÃO encontrou nenhuma matéria nossa sobre o tema (0 matérias)

**O Consolidador verifica novamente** porque:
- A busca do Monitor pode ter ocorrido minutos atrás — uma nova matéria pode ter sido publicada
- O Monitor pode ter feito uma busca menos precisa que o Consolidador fará
- Garantia de consistência antes de qualquer ação

```python
# brasileira/consolidador/agent.py

import asyncio
import logging
from typing import Optional
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
import asyncpg
import redis.asyncio as redis

from .consumer import ConsolidacaoConsumer, PautaGapProducer
from .detector import DetectorMateriasRelacionadas
from .router import RoteadorConsolidador
from .rewriter import ReescritorEditorial
from .consolidator import ConsolidadorAnalitico
from .publisher import PublicadorWordPress
from .memory import MemoriaConsolidador
from .schemas import MensagemConsolidacao, MensagemPautaGap

logger = logging.getLogger("consolidador.agent")


class EstadoConsolidador(BaseModel):
    """Estado do LangGraph do Consolidador."""
    # Entrada
    mensagem: Optional[MensagemConsolidacao] = None
    
    # Detecção
    materias_proprias: list = Field(default_factory=list)
    
    # Decisão
    acao: Optional[str] = None  # "acionar_reporter" | "reescrever" | "consolidar"
    prioridade: int = 5
    
    # Resultado
    artigo_gerado: Optional[dict] = None
    wp_post_id: Optional[int] = None
    publicado: bool = False
    pauta_gap_enviada: bool = False
    
    # Controle
    erro: Optional[str] = None
    ciclo_id: str = ""


class ConsolidadorAgent:
    """
    Agente LangGraph do Consolidador V3.
    
    Loop principal:
    1. Consome mensagem do tópico Kafka 'consolidacao'
    2. Busca matérias próprias no PostgreSQL
    3. Roteia: 0 → acionar_reporter, 1 → reescrever, 2+ → consolidar
    4. Executa ação com LLM PREMIUM
    5. Publica no WordPress ou envia pauta para Kafka
    6. Registra na memória do agente
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_client: redis.Redis,
        smart_router,
        wp_client,
        kafka_bootstrap_servers: str,
    ):
        self.db = db_pool
        self.redis = redis_client
        self.router_llm = smart_router
        self.wp = wp_client
        
        # Componentes internos
        self.consumer = ConsolidacaoConsumer(kafka_bootstrap_servers)
        self.producer_gap = PautaGapProducer(kafka_bootstrap_servers)
        self.detector = DetectorMateriasRelacionadas(db_pool)
        self.roteador = RoteadorConsolidador()
        self.reescritor = ReescritorEditorial(smart_router)
        self.consolidador = ConsolidadorAnalitico(smart_router)
        self.publicador = PublicadorWordPress(wp_client)
        self.memoria = MemoriaConsolidador(db_pool, redis_client)
        
        # Grafo LangGraph
        self.graph = self._construir_grafo()
    
    def _construir_grafo(self) -> StateGraph:
        """Constrói o grafo LangGraph do Consolidador."""
        graph = StateGraph(EstadoConsolidador)
        
        # Nós
        graph.add_node("buscar_materias", self._node_buscar_materias)
        graph.add_node("rotear", self._node_rotear)
        graph.add_node("acionar_reporter", self._node_acionar_reporter)
        graph.add_node("coletar_fontes", self._node_coletar_fontes)
        graph.add_node("reescrever", self._node_reescrever)
        graph.add_node("consolidar", self._node_consolidar)
        graph.add_node("publicar", self._node_publicar)
        graph.add_node("registrar_memoria", self._node_registrar_memoria)
        
        # Fluxo
        graph.set_entry_point("buscar_materias")
        graph.add_edge("buscar_materias", "rotear")
        
        # Roteamento condicional
        graph.add_conditional_edges(
            "rotear",
            self._decidir_acao,
            {
                "acionar_reporter": "acionar_reporter",
                "reescrever": "coletar_fontes",
                "consolidar": "coletar_fontes",
            }
        )
        
        graph.add_edge("acionar_reporter", "registrar_memoria")
        
        # Após coletar fontes, decide reescrever ou consolidar
        graph.add_conditional_edges(
            "coletar_fontes",
            lambda s: s.acao,
            {
                "reescrever": "reescrever",
                "consolidar": "consolidar",
            }
        )
        
        graph.add_edge("reescrever", "publicar")
        graph.add_edge("consolidar", "publicar")
        graph.add_edge("publicar", "registrar_memoria")
        graph.add_edge("registrar_memoria", END)
        
        return graph.compile()
    
    # ─────────────────────────────────────────────────────────────────────────
    # Nós do LangGraph
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _node_buscar_materias(
        self,
        state: EstadoConsolidador,
    ) -> dict:
        """
        Busca matérias próprias sobre o tema.
        
        Estratégia dupla:
        1. Se a mensagem já traz ids_materias_proprias → busca por ID (mais rápido)
        2. Se não → busca semântica por palavras-chave
        """
        msg = state.mensagem
        
        if msg.ids_materias_proprias:
            # O Monitor já identificou as matérias — busca por ID
            materias = await self.detector.buscar_por_ids(msg.ids_materias_proprias)
            logger.info(
                f"Matérias encontradas por ID: {len(materias)} | "
                f"ids={msg.ids_materias_proprias}"
            )
        else:
            # Busca por palavras-chave + validação semântica
            materias = await self.detector.buscar_materias_sobre(
                palavras_chave=msg.palavras_chave,
                tema_descricao=msg.tema_descricao,
            )
            logger.info(
                f"Matérias encontradas por busca semântica: {len(materias)} | "
                f"keywords={msg.palavras_chave}"
            )
        
        return {"materias_proprias": [m.__dict__ for m in materias]}
    
    async def _node_rotear(self, state: EstadoConsolidador) -> dict:
        """Aplica a lógica 0/1/2+ para decidir a ação."""
        from .detector import MateriaPropria
        
        # Reconstrói objetos MateriaPropria do estado
        materias = [MateriaPropria(**m) for m in state.materias_proprias]
        
        decisao = self.roteador.rotear(
            mensagem=state.mensagem,
            materias_proprias=materias,
        )
        
        return {
            "acao": decisao.acao,
            "prioridade": decisao.prioridade,
        }
    
    def _decidir_acao(self, state: EstadoConsolidador) -> str:
        """Aresta condicional: retorna o nome do próximo nó."""
        return state.acao
    
    async def _node_acionar_reporter(
        self,
        state: EstadoConsolidador,
    ) -> dict:
        """
        Envia pauta para os Reporters via Kafka pautas-gap.
        Ocorre quando temos 0 matérias próprias sobre o tema.
        """
        msg = state.mensagem
        
        pauta = MensagemPautaGap(
            tema_id=msg.tema_id,
            tema_descricao=msg.tema_descricao,
            palavras_chave=msg.palavras_chave,
            num_capas=msg.num_capas,
            portais_detectados=msg.portais_detectados,
            artigos_concorrentes=msg.artigos_concorrentes,
            urgencia=msg.urgencia,
            tipo="cobertura_nova",
            origem="consolidador",
        )
        
        await self.producer_gap.enviar_pauta_gap(pauta)
        
        logger.info(
            f"Pauta gap enviada ao Reporter: tema={msg.tema_id!r} | "
            f"urgencia={msg.urgencia}"
        )
        
        return {"pauta_gap_enviada": True}
    
    async def _node_coletar_fontes(
        self,
        state: EstadoConsolidador,
    ) -> dict:
        """
        Passo de preparação antes de reescrever/consolidar.
        Garante que os conteúdos das matérias estão carregados.
        No estado atual, os conteúdos já vêm do detector.
        Este nó pode fazer enriquecimento adicional se necessário.
        """
        # Os conteúdos já estão em state.materias_proprias
        # Este nó serve como ponto de extensão para enriquecimento futuro
        # (ex: buscar og:image das matérias, enriquecer com metadados)
        logger.info(
            f"Fontes coletadas: {len(state.materias_proprias)} matérias | "
            f"acao={state.acao}"
        )
        return {}
    
    async def _node_reescrever(self, state: EstadoConsolidador) -> dict:
        """Executa a reescrita editorial (1 fonte)."""
        from .detector import MateriaPropria
        
        materia = MateriaPropria(**state.materias_proprias[0])
        
        artigo = await self.reescritor.reescrever(
            materia=materia,
            mensagem=state.mensagem,
        )
        
        return {"artigo_gerado": artigo}
    
    async def _node_consolidar(self, state: EstadoConsolidador) -> dict:
        """Executa a consolidação analítica (2+ fontes)."""
        from .detector import MateriaPropria
        
        materias = [MateriaPropria(**m) for m in state.materias_proprias]
        
        artigo = await self.consolidador.consolidar(
            materias=materias,
            mensagem=state.mensagem,
        )
        
        return {"artigo_gerado": artigo}
    
    async def _node_publicar(self, state: EstadoConsolidador) -> dict:
        """Publica o artigo gerado no WordPress."""
        artigo = state.artigo_gerado
        if not artigo:
            logger.error("Nenhum artigo para publicar — estado inválido")
            return {"erro": "artigo_gerado vazio"}
        
        wp_post_id = await self.publicador.publicar(
            artigo=artigo,
            mensagem=state.mensagem,
        )
        
        return {"wp_post_id": wp_post_id, "publicado": True}
    
    async def _node_registrar_memoria(
        self,
        state: EstadoConsolidador,
    ) -> dict:
        """Registra o ciclo na memória do agente."""
        await self.memoria.registrar_ciclo(state)
        return {}
    
    # ─────────────────────────────────────────────────────────────────────────
    # Loop Principal
    # ─────────────────────────────────────────────────────────────────────────
    
    async def executar(self) -> None:
        """Loop principal do Consolidador. Consome e processa mensagens indefinidamente."""
        await self.consumer.start()
        await self.producer_gap.start()
        
        logger.info("Consolidador V3 iniciado. Aguardando mensagens em 'consolidacao'...")
        
        async for mensagem in self.consumer.mensagens():
            try:
                estado_inicial = EstadoConsolidador(
                    mensagem=mensagem,
                    ciclo_id=f"{mensagem.tema_id}_{mensagem.detectado_em.isoformat()}",
                )
                
                logger.info(
                    f"Processando: tema={mensagem.tema_id!r} | "
                    f"urgencia={mensagem.urgencia} | "
                    f"capas={mensagem.num_capas}"
                )
                
                # Executa o grafo LangGraph
                resultado = await self.graph.ainvoke(estado_inicial.model_dump())
                
                if resultado.get("publicado"):
                    logger.info(
                        f"Concluído com publicação: wp_post_id={resultado['wp_post_id']} | "
                        f"tema={mensagem.tema_id!r}"
                    )
                elif resultado.get("pauta_gap_enviada"):
                    logger.info(
                        f"Concluído com pauta gap enviada: tema={mensagem.tema_id!r}"
                    )
                else:
                    logger.warning(
                        f"Ciclo concluído sem ação clara: {resultado}"
                    )
                    
            except Exception as e:
                # NUNCA trava o loop principal
                logger.error(
                    f"Erro ao processar tema={mensagem.tema_id!r}: {e}",
                    exc_info=True
                )
                # Continua com a próxima mensagem
                continue
```

---

## PARTE IX — PUBLICAÇÃO VIA REPORTER OU DIRETO

### 9.1 Publicação Direta no WordPress

O Consolidador **publica diretamente** no WordPress via REST API — não há intermediário. O PublisherAgent foi eliminado na V3.

```python
# brasileira/consolidador/publisher.py

import logging
from typing import Dict, Any, Optional
import httpx
from .schemas import MensagemConsolidacao

logger = logging.getLogger("consolidador.publisher")

# Mapeamento de categorias para IDs do WordPress
CATEGORIA_WP_ID = {
    "Política": 1,
    "Economia": 2,
    "Esportes": 3,
    "Tecnologia": 4,
    "Saúde": 5,
    "Educação": 6,
    "Ciência": 7,
    "Cultura/Entretenimento": 8,
    "Mundo/Internacional": 9,
    "Meio Ambiente": 10,
    "Segurança/Justiça": 11,
    "Sociedade": 12,
    "Brasil (geral)": 13,
    "Regionais": 14,
    "Opinião/Análise": 15,
    "Últimas Notícias": 16,
}

# Labels especiais baseados na urgência
URGENCIA_LABEL = {
    "maxima": "URGENTE",
    "alta": "DESTAQUE",
    "media": "",
    "baixa": "",
}


class PublicadorWordPress:
    """
    Publica artigos gerados pelo Consolidador diretamente no WordPress.
    
    Usa a mesma lógica do Reporter V3:
    - POST /wp-json/wp/v2/posts
    - Status: publish (imediato, sem draft)
    - Tags criadas automaticamente se não existirem
    """
    
    WP_URL = "https://brasileira.news"
    WP_USER = "iapublicador"
    
    def __init__(self, wp_client):
        """
        Args:
            wp_client: Cliente WordPress com autenticação configurada
        """
        self.wp = wp_client
    
    async def publicar(
        self,
        artigo: Dict[str, Any],
        mensagem: MensagemConsolidacao,
    ) -> int:
        """
        Publica o artigo e retorna o wp_post_id.
        
        Processo:
        1. Cria/obtém IDs das tags
        2. Obtém ID da categoria
        3. Publica o post
        4. Registra na tabela artigos (PostgreSQL)
        
        Returns:
            wp_post_id do artigo publicado
        """
        # 1. Prepara tags
        tag_ids = await self._obter_ou_criar_tags(artigo.get("tags", []))
        
        # 2. Obtém categoria
        categoria_nome = artigo.get("categoria", "Últimas Notícias")
        categoria_id = CATEGORIA_WP_ID.get(categoria_nome, 16)
        
        # 3. Determina label especial
        label = URGENCIA_LABEL.get(mensagem.urgencia, "")
        
        # 4. Adiciona meta para indicar origem (Consolidador)
        tipo = artigo.get("tipo_conteudo", "consolidacao_analitica")
        
        # 5. Monta payload WordPress
        payload = {
            "title": artigo["titulo"],
            "content": artigo["conteudo"],
            "excerpt": artigo.get("excerpt", ""),
            "status": "publish",   # SEMPRE publish — nunca draft
            "categories": [categoria_id],
            "tags": tag_ids,
            "meta": {
                "_yoast_wpseo_title": artigo.get("seo_title", ""),
                "_yoast_wpseo_metadesc": artigo.get("seo_description", ""),
                "consolidador_tipo": tipo,
                "consolidador_tema_id": mensagem.tema_id,
                "consolidador_num_capas": mensagem.num_capas,
                "consolidador_portais": ", ".join(mensagem.portais_detectados),
                "consolidador_urgencia": mensagem.urgencia,
                "label_editorial": label,
            },
        }
        
        logger.info(
            f"Publicando no WordPress: {artigo['titulo'][:60]!r} | "
            f"categoria={categoria_nome} | tags={len(tag_ids)} | "
            f"tipo={tipo}"
        )
        
        # 6. POST no WordPress
        try:
            response = await self.wp.post(
                "/wp-json/wp/v2/posts",
                json=payload,
            )
            
            wp_post_id = response["id"]
            wp_url = response.get("link", "")
            
            logger.info(
                f"Artigo publicado: wp_post_id={wp_post_id} | "
                f"url={wp_url}"
            )
            
            return wp_post_id
            
        except Exception as e:
            logger.error(f"Erro ao publicar no WordPress: {e}", exc_info=True)
            raise
    
    async def _obter_ou_criar_tags(self, nomes: list) -> list:
        """Cria tags no WordPress se não existirem e retorna os IDs."""
        ids = []
        for nome in nomes[:6]:  # Limita a 6 tags
            nome = str(nome).strip()
            if not nome:
                continue
            try:
                # Tenta criar — se já existir, retorna o existente
                resp = await self.wp.post(
                    "/wp-json/wp/v2/tags",
                    json={"name": nome},
                )
                ids.append(resp["id"])
            except Exception as e:
                # Tag pode já existir — tenta buscar
                try:
                    search = await self.wp.get(
                        "/wp-json/wp/v2/tags",
                        params={"search": nome, "per_page": 1},
                    )
                    if search:
                        ids.append(search[0]["id"])
                except Exception:
                    logger.warning(f"Falha ao criar/buscar tag {nome!r}: {e}")
        return ids


### 9.2 Envio de Pauta Gap para o Reporter

Quando o Consolidador detecta 0 matérias sobre o tema, ele não publica nada —
ele envia uma pauta para o Reporter via Kafka `pautas-gap`. O Reporter V3 consome
esse tópico e gera a cobertura.

```python
# Trecho já implementado no ConsolidadorAgent._node_acionar_reporter()
# A mensagem MensagemPautaGap contém:
# - Descrição do tema
# - Palavras-chave para pesquisa
# - URLs dos artigos dos concorrentes (para o Reporter usar como referência)
# - Urgência (para o Reporter priorizar)
# - Tipo: "cobertura_nova"
```

**IMPORTANTE:** O Reporter, ao receber uma mensagem de `pautas-gap` do Consolidador,
deve tratar como pauta de ALTA prioridade — o tema já foi validado pelo Monitor Concorrência
como relevante o suficiente para estar nas capas dos concorrentes.

---

## PARTE X — MEMÓRIA DO CONSOLIDADOR

### 10.1 Três Tipos de Memória

O Consolidador V3 implementa os três tipos de memória obrigatórios para todos os agentes:

| Tipo | Backend | TTL | Uso |
|------|---------|-----|-----|
| **Working** | Redis | 4h | Estado do ciclo atual, contexto temporário |
| **Episódica** | PostgreSQL | Permanente | Histórico de consolidações realizadas |
| **Semântica** | PostgreSQL + pgvector | Permanente | Temas já consolidados (evita duplicatas) |

```python
# brasileira/consolidador/memory.py

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import asyncpg
import redis.asyncio as redis

logger = logging.getLogger("consolidador.memory")


class MemoriaConsolidador:
    """
    Memória do Consolidador com três camadas:
    1. Working Memory (Redis) — contexto do ciclo atual
    2. Memória Episódica (PostgreSQL) — histórico de consolidações
    3. Memória Semântica (PostgreSQL + pgvector) — temas já cobertos
    """
    
    REDIS_PREFIX = "consolidador:working:"
    REDIS_TTL_SECONDS = 4 * 3600  # 4 horas
    
    # Para evitar reprocessar o mesmo tema em curto período
    REDIS_TEMA_COOLDOWN_PREFIX = "consolidador:tema_cooldown:"
    TEMA_COOLDOWN_SEGUNDOS = 3600  # 1 hora — não reprocessar o mesmo tema em 1h
    
    def __init__(self, db: asyncpg.Pool, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client
    
    # ─── Working Memory ───────────────────────────────────────────────────────
    
    async def salvar_contexto_ciclo(
        self,
        ciclo_id: str,
        contexto: Dict[str, Any],
    ) -> None:
        """Salva contexto temporário do ciclo atual no Redis."""
        key = f"{self.REDIS_PREFIX}{ciclo_id}"
        await self.redis.setex(
            key,
            self.REDIS_TTL_SECONDS,
            json.dumps(contexto, default=str, ensure_ascii=False),
        )
    
    async def carregar_contexto_ciclo(
        self,
        ciclo_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Recupera contexto do ciclo do Redis."""
        key = f"{self.REDIS_PREFIX}{ciclo_id}"
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def tema_em_cooldown(self, tema_id: str) -> bool:
        """
        Verifica se o tema foi processado recentemente.
        Evita reprocessar o mesmo tema em menos de 1 hora.
        """
        key = f"{self.REDIS_TEMA_COOLDOWN_PREFIX}{tema_id}"
        return bool(await self.redis.exists(key))
    
    async def marcar_tema_processado(self, tema_id: str) -> None:
        """Marca tema como processado (cooldown de 1 hora)."""
        key = f"{self.REDIS_TEMA_COOLDOWN_PREFIX}{tema_id}"
        await self.redis.setex(key, self.TEMA_COOLDOWN_SEGUNDOS, "1")
    
    # ─── Memória Episódica ────────────────────────────────────────────────────
    
    async def registrar_ciclo(self, estado) -> None:
        """
        Registra o resultado do ciclo na memória episódica (PostgreSQL).
        
        Insere em memoria_agentes com tipo='episodica'.
        """
        conteudo = {
            "tema_id": estado.mensagem.tema_id if estado.mensagem else None,
            "tema_descricao": estado.mensagem.tema_descricao if estado.mensagem else None,
            "acao": estado.acao,
            "materias_processadas": len(estado.materias_proprias),
            "wp_post_id": estado.wp_post_id,
            "publicado": estado.publicado,
            "pauta_gap_enviada": estado.pauta_gap_enviada,
            "prioridade": estado.prioridade,
            "erro": estado.erro,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        try:
            await self.db.execute(
                """
                INSERT INTO memoria_agentes (agente, tipo, conteudo, timestamp)
                VALUES ($1, $2, $3, NOW())
                """,
                "consolidador",
                "episodica",
                json.dumps(conteudo, ensure_ascii=False),
            )
            
            # Marca tema em cooldown após processamento
            if estado.mensagem:
                await self.marcar_tema_processado(estado.mensagem.tema_id)
            
            logger.debug(f"Memória episódica registrada: {conteudo}")
            
        except Exception as e:
            logger.error(f"Falha ao registrar memória episódica: {e}", exc_info=True)
            # NUNCA deixa falha de memória travar o pipeline
    
    async def registrar_artigo_publicado(
        self,
        wp_post_id: int,
        tema_id: str,
        tipo: str,
        titulo: str,
        llm_model: str,
        llm_cost: float,
    ) -> None:
        """
        Registra artigo publicado na tabela artigos (para futuras buscas).
        Inclui embedding semântico para busca vetorial futura.
        """
        try:
            await self.db.execute(
                """
                INSERT INTO artigos (wp_post_id, titulo, editoria, url_fonte, publicado_em, tipo_origem)
                VALUES ($1, $2, $3, $4, NOW(), $5)
                ON CONFLICT (wp_post_id) DO NOTHING
                """,
                wp_post_id,
                titulo,
                "consolidacao",
                f"https://brasileira.news/?p={wp_post_id}",
                tipo,
            )
        except Exception as e:
            logger.error(f"Falha ao registrar artigo publicado: {e}", exc_info=True)
    
    # ─── Memória Semântica ────────────────────────────────────────────────────
    
    async def buscar_consolidacoes_recentes(
        self,
        tema_id: str,
        limite: int = 5,
    ) -> list:
        """
        Busca consolidações recentes sobre o mesmo tema.
        Útil para decidir se um tema já foi suficientemente coberto.
        """
        try:
            rows = await self.db.fetch(
                """
                SELECT conteudo, timestamp
                FROM memoria_agentes
                WHERE 
                    agente = 'consolidador'
                    AND tipo = 'episodica'
                    AND conteudo->>'tema_id' = $1
                    AND publicado = true
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                tema_id,
                limite,
            )
            return [json.loads(r["conteudo"]) for r in rows]
        except Exception as e:
            logger.error(f"Falha na busca semântica: {e}", exc_info=True)
            return []
```

---

## PARTE XI — SCHEMAS KAFKA E POSTGRESQL

### 11.1 Tópicos Kafka — Especificação

| Tópico | Produtores | Consumidores | Partições | Retenção |
|--------|-----------|--------------|-----------|----------|
| `consolidacao` | Monitor Concorrência | Consolidador | 4 (por tema_id hash) | 24h |
| `pautas-gap` | Consolidador, Monitor Conc. | Worker Pool Reporters | 8 (por urgência) | 12h |

**Criação dos tópicos (kafka-topics.sh):**

```bash
# Tópico consolidacao
kafka-topics.sh --create \
  --bootstrap-server kafka:9092 \
  --topic consolidacao \
  --partitions 4 \
  --replication-factor 1 \
  --config retention.ms=86400000 \
  --config message.max.bytes=1048576

# Tópico pautas-gap (se não existir)
kafka-topics.sh --create \
  --bootstrap-server kafka:9092 \
  --topic pautas-gap \
  --partitions 8 \
  --replication-factor 1 \
  --config retention.ms=43200000 \
  --config message.max.bytes=524288
```

### 11.2 Schemas PostgreSQL

```sql
-- Tabela principal de artigos (já existente — sem alterações obrigatórias)
-- Verificar se tem coluna tipo_origem:
ALTER TABLE artigos 
ADD COLUMN IF NOT EXISTS tipo_origem VARCHAR(50) DEFAULT 'rss';

-- Verificar se tabela memoria_agentes existe:
CREATE TABLE IF NOT EXISTS memoria_agentes (
    id BIGSERIAL PRIMARY KEY,
    agente VARCHAR(100) NOT NULL,
    tipo VARCHAR(50) NOT NULL CHECK (tipo IN ('working', 'episodica', 'semantica')),
    conteudo JSONB NOT NULL,
    embedding vector(1536),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Índices
    CONSTRAINT memoria_agentes_agente_tipo_idx UNIQUE (agente, tipo, id)
);

CREATE INDEX IF NOT EXISTS idx_memoria_agentes_agente ON memoria_agentes(agente);
CREATE INDEX IF NOT EXISTS idx_memoria_agentes_tipo ON memoria_agentes(tipo);
CREATE INDEX IF NOT EXISTS idx_memoria_agentes_timestamp ON memoria_agentes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_memoria_agentes_conteudo_gin ON memoria_agentes USING GIN(conteudo);

-- Tabela específica para rastreamento de consolidações (opcional mas recomendada)
CREATE TABLE IF NOT EXISTS consolidacoes (
    id BIGSERIAL PRIMARY KEY,
    tema_id VARCHAR(255) NOT NULL,
    tema_descricao TEXT,
    acao VARCHAR(50) NOT NULL CHECK (acao IN ('acionar_reporter', 'reescrever', 'consolidar')),
    num_materias_proprias INT DEFAULT 0,
    num_capas_concorrentes INT DEFAULT 0,
    portais_detectados TEXT[],
    wp_post_id INT,
    artigo_titulo TEXT,
    llm_model VARCHAR(100),
    llm_cost_usd NUMERIC(10, 6),
    pauta_gap_enviada BOOLEAN DEFAULT FALSE,
    urgencia VARCHAR(20),
    processado_em TIMESTAMPTZ DEFAULT NOW(),
    
    -- Para não processar o mesmo tema repetidamente
    CONSTRAINT consolidacoes_tema_recente 
        UNIQUE (tema_id, DATE_TRUNC('hour', processado_em))
);

CREATE INDEX IF NOT EXISTS idx_consolidacoes_tema_id ON consolidacoes(tema_id);
CREATE INDEX IF NOT EXISTS idx_consolidacoes_processado_em ON consolidacoes(processado_em DESC);
CREATE INDEX IF NOT EXISTS idx_consolidacoes_wp_post_id ON consolidacoes(wp_post_id);

-- View útil para monitoramento
CREATE OR REPLACE VIEW v_consolidacoes_recentes AS
SELECT 
    c.tema_id,
    c.tema_descricao,
    c.acao,
    c.num_materias_proprias,
    c.num_capas_concorrentes,
    ARRAY_TO_STRING(c.portais_detectados, ', ') AS portais,
    c.wp_post_id,
    c.artigo_titulo,
    c.llm_model,
    c.llm_cost_usd,
    c.urgencia,
    c.processado_em,
    a.url_fonte AS artigo_url
FROM consolidacoes c
LEFT JOIN artigos a ON a.wp_post_id = c.wp_post_id
WHERE c.processado_em >= NOW() - INTERVAL '24 hours'
ORDER BY c.processado_em DESC;
```

### 11.3 Índice GIN para Busca de Keywords

```sql
-- Índice para busca rápida de matérias por título e conteúdo
-- Requer pg_trgm instalado
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_artigos_titulo_trgm 
ON artigos USING GIN (titulo gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_artigos_conteudo_trgm 
ON artigos USING GIN (conteudo gin_trgm_ops);

-- Índice para filtro temporal (busca de matérias recentes)
CREATE INDEX IF NOT EXISTS idx_artigos_publicado_wp 
ON artigos (publicado_em DESC, wp_post_id) 
WHERE wp_post_id IS NOT NULL;
```

---

## PARTE XII — ESTRUTURA DE DIRETÓRIOS

```
brasileira/
├── consolidador/
│   ├── __init__.py
│   ├── agent.py                 ← ConsolidadorAgent (LangGraph + loop principal)
│   ├── consumer.py              ← ConsolidacaoConsumer + PautaGapProducer (Kafka)
│   ├── detector.py              ← DetectorMateriasRelacionadas (TF-IDF + pgvector)
│   ├── router.py                ← RoteadorConsolidador (lógica 0/1/2+)
│   ├── rewriter.py              ← ReescritorEditorial (1 fonte, LLM PREMIUM)
│   ├── consolidator.py          ← ConsolidadorAnalitico (2+ fontes, LLM PREMIUM)
│   ├── publisher.py             ← PublicadorWordPress (direto, sem intermediário)
│   ├── memory.py                ← MemoriaConsolidador (working + episódica + semântica)
│   ├── prompts.py               ← System prompts + templates (reescrita + consolidação)
│   ├── schemas.py               ← Pydantic schemas (MensagemConsolidacao, etc.)
│   └── main.py                  ← Entrypoint
│
├── llm/
│   └── smart_router.py          ← SmartLLMRouter (componente #1) — NÃO modificar
│
├── utils/
│   ├── logging.py
│   └── wp_client.py             ← WordPress REST API client
│
└── config.py                    ← Variáveis de ambiente
```

### 12.1 `__init__.py`

```python
# brasileira/consolidador/__init__.py

from .agent import ConsolidadorAgent
from .schemas import MensagemConsolidacao, MensagemPautaGap, ArtigoConcorrente

__all__ = [
    "ConsolidadorAgent",
    "MensagemConsolidacao",
    "MensagemPautaGap",
    "ArtigoConcorrente",
]
```

---

## PARTE XIII — ENTRYPOINT

```python
# brasileira/consolidador/main.py

"""
Entrypoint do Consolidador V3.

Inicialização:
1. Carrega configuração do ambiente
2. Conecta ao PostgreSQL (pool assíncrono)
3. Conecta ao Redis
4. Inicializa SmartLLMRouter (componente #1)
5. Inicializa WordPress client
6. Cria ConsolidadorAgent e inicia loop

Execução:
docker compose run consolidador
# ou
python -m brasileira.consolidador.main
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis

# Importações internas
from brasileira.consolidador.agent import ConsolidadorAgent
from brasileira.llm.smart_router import SmartLLMRouter
from brasileira.utils.wp_client import WordPressClient
from brasileira.utils.logging import configurar_logging

logger = logging.getLogger("consolidador.main")


# ─── Configuração via Variáveis de Ambiente ───────────────────────────────────

class Config:
    """Configuração do Consolidador via variáveis de ambiente."""
    
    # PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/brasileira"
    )
    DB_MIN_CONNECTIONS: int = int(os.getenv("DB_MIN_CONNECTIONS", "2"))
    DB_MAX_CONNECTIONS: int = int(os.getenv("DB_MAX_CONNECTIONS", "10"))
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        "kafka:9092"
    )
    
    # WordPress
    WP_URL: str = os.getenv("WP_URL", "https://brasileira.news")
    WP_USER: str = os.getenv("WP_USER", "iapublicador")
    WP_APP_PASSWORD: str = os.getenv("WP_APP_PASSWORD", "")
    
    # LLM
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    
    # Log
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = Config()


# ─── Setup de Recursos ────────────────────────────────────────────────────────

async def criar_db_pool() -> asyncpg.Pool:
    """Cria pool de conexões PostgreSQL com retry."""
    retry = 0
    while True:
        try:
            pool = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=config.DB_MIN_CONNECTIONS,
                max_size=config.DB_MAX_CONNECTIONS,
                command_timeout=60,
            )
            logger.info(f"PostgreSQL conectado: pool={config.DB_MIN_CONNECTIONS}-{config.DB_MAX_CONNECTIONS}")
            return pool
        except Exception as e:
            retry += 1
            espera = min(2 ** retry, 60)
            logger.warning(f"PostgreSQL indisponível (tentativa {retry}), aguardando {espera}s: {e}")
            await asyncio.sleep(espera)


async def criar_redis_client() -> aioredis.Redis:
    """Cria cliente Redis com retry."""
    retry = 0
    while True:
        try:
            client = await aioredis.from_url(
                config.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await client.ping()
            logger.info("Redis conectado.")
            return client
        except Exception as e:
            retry += 1
            espera = min(2 ** retry, 60)
            logger.warning(f"Redis indisponível (tentativa {retry}), aguardando {espera}s: {e}")
            await asyncio.sleep(espera)


def criar_smart_router() -> SmartLLMRouter:
    """Inicializa o SmartLLMRouter (componente #1)."""
    return SmartLLMRouter(
        anthropic_api_key=config.ANTHROPIC_API_KEY,
        openai_api_key=config.OPENAI_API_KEY,
        google_api_key=config.GOOGLE_API_KEY,
        xai_api_key=config.XAI_API_KEY,
    )


def criar_wp_client() -> WordPressClient:
    """Inicializa cliente WordPress."""
    return WordPressClient(
        base_url=config.WP_URL,
        username=config.WP_USER,
        app_password=config.WP_APP_PASSWORD,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    """Ponto de entrada principal do Consolidador V3."""
    configurar_logging(level=config.LOG_LEVEL)
    
    logger.info("=" * 60)
    logger.info("Iniciando Consolidador V3 — brasileira.news")
    logger.info("=" * 60)
    
    # Inicializa recursos
    logger.info("Conectando ao PostgreSQL...")
    db_pool = await criar_db_pool()
    
    logger.info("Conectando ao Redis...")
    redis_client = await criar_redis_client()
    
    logger.info("Inicializando SmartLLMRouter...")
    smart_router = criar_smart_router()
    
    logger.info("Inicializando WordPress client...")
    wp_client = criar_wp_client()
    
    # Cria e inicia o agente
    agente = ConsolidadorAgent(
        db_pool=db_pool,
        redis_client=redis_client,
        smart_router=smart_router,
        wp_client=wp_client,
        kafka_bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
    )
    
    logger.info("Consolidador V3 pronto. Iniciando loop de consumo Kafka...")
    
    try:
        await agente.executar()
    except KeyboardInterrupt:
        logger.info("Sinal de parada recebido (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Erro fatal no Consolidador: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Encerrando conexões...")
        await db_pool.close()
        await redis_client.close()
        logger.info("Consolidador V3 encerrado.")


if __name__ == "__main__":
    asyncio.run(main())
```

### 13.1 Docker — Execução

```dockerfile
# Dockerfile.consolidador
FROM python:3.12-slim

WORKDIR /app

# Dependências do sistema para scikit-learn e asyncpg
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "brasileira.consolidador.main"]
```

```yaml
# docker-compose.yml (trecho do serviço consolidador)
services:
  consolidador:
    build:
      context: .
      dockerfile: Dockerfile.consolidador
    restart: unless-stopped
    depends_on:
      - kafka
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql://user:password@postgres:5432/brasileira
      REDIS_URL: redis://redis:6379/0
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      WP_URL: https://brasileira.news
      WP_USER: iapublicador
      WP_APP_PASSWORD: ${WP_APP_PASSWORD}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
      XAI_API_KEY: ${XAI_API_KEY}
      LOG_LEVEL: INFO
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
```

### 13.2 Requirements Específicos do Consolidador

```txt
# requirements.txt (dependências específicas do Consolidador)
# (além do requirements base do projeto)

aiokafka>=0.10.0          # Consumer/Producer Kafka assíncrono
asyncpg>=0.29.0           # PostgreSQL assíncrono
redis[asyncio]>=5.0.0     # Redis assíncrono
langgraph>=0.2.0          # Grafo de agente LangGraph
pydantic>=2.5.0           # Schemas e validação
scikit-learn>=1.4.0       # TF-IDF vectorizer
numpy>=1.26.0             # Arrays numéricos (TF-IDF)
httpx>=0.27.0             # HTTP client (WordPress REST API)
```

---

## PARTE XIV — TESTES E CHECKLIST

### 14.1 Testes Unitários

```python
# tests/consolidador/test_router.py

import pytest
from brasileira.consolidador.router import RoteadorConsolidador, DecisaoRoteador
from brasileira.consolidador.detector import MateriaPropria
from brasileira.consolidador.schemas import MensagemConsolidacao, ArtigoConcorrente
from datetime import datetime


@pytest.fixture
def roteador():
    return RoteadorConsolidador()


@pytest.fixture
def mensagem_base():
    return MensagemConsolidacao(
        tema_id="tema_economia_bc_2026",
        tema_descricao="Banco Central anuncia alta da Selic para 14,5%",
        palavras_chave=["Selic", "Banco Central", "juros", "2026"],
        num_capas=3,
        portais_detectados=["G1", "Folha", "UOL"],
        artigos_concorrentes=[
            ArtigoConcorrente(
                portal="G1",
                titulo="Selic sobe para 14,5% ao ano, maior nível desde 2016",
                url="https://g1.globo.com/economia/...",
                posicao_capa=1,
            )
        ],
        ids_materias_proprias=[],
        urgencia="alta",
        detectado_em=datetime.utcnow(),
    )


def test_rota_zero_materias(roteador, mensagem_base):
    """Com 0 matérias, deve acionar_reporter."""
    decisao = roteador.rotear(mensagem_base, [])
    assert decisao.acao == "acionar_reporter"
    assert decisao.materias == []
    assert decisao.prioridade >= 1


def test_rota_uma_materia(roteador, mensagem_base):
    """Com 1 matéria, deve reescrever."""
    materia = MateriaPropria(
        id=1,
        titulo="BC eleva Selic para 14,5%",
        conteudo="O Banco Central do Brasil elevou a taxa Selic...",
        url="https://brasileira.news/bc-eleva-selic",
        wp_post_id=1001,
        editoria="Economia",
        publicado_em=datetime.utcnow(),
    )
    decisao = roteador.rotear(mensagem_base, [materia])
    assert decisao.acao == "reescrever"
    assert len(decisao.materias) == 1


def test_rota_duas_ou_mais_materias(roteador, mensagem_base):
    """Com 2+ matérias, deve consolidar."""
    materias = [
        MateriaPropria(
            id=i,
            titulo=f"Matéria {i} sobre Selic",
            conteudo=f"Conteúdo da matéria {i} sobre a Selic...",
            url=f"https://brasileira.news/selic-{i}",
            wp_post_id=1000 + i,
            editoria="Economia",
            publicado_em=datetime.utcnow(),
        )
        for i in range(1, 4)
    ]
    decisao = roteador.rotear(mensagem_base, materias)
    assert decisao.acao == "consolidar"
    assert len(decisao.materias) == 3


def test_prioridade_aumenta_com_portais_tier1(roteador, mensagem_base):
    """Portais Tier-1 na capa aumentam a prioridade."""
    mensagem_tier1 = mensagem_base.model_copy(
        update={"portais_detectados": ["G1", "Folha", "Estadão"], "num_capas": 3}
    )
    mensagem_tier2 = mensagem_base.model_copy(
        update={"portais_detectados": ["R7", "Terra"], "num_capas": 2}
    )
    
    decisao_tier1 = roteador.rotear(mensagem_tier1, [])
    decisao_tier2 = roteador.rotear(mensagem_tier2, [])
    
    assert decisao_tier1.prioridade > decisao_tier2.prioridade


def test_regra_inviolavel_min_sources_n_existe(roteador, mensagem_base):
    """
    TESTE CRÍTICO: Garante que MIN_SOURCES=3 não existe mais.
    Com 1 matéria E 1 capa de concorrente, deve reescrever — não ignorar.
    """
    mensagem_1_capa = mensagem_base.model_copy(
        update={
            "num_capas": 1,
            "portais_detectados": ["R7"],
        }
    )
    materia = MateriaPropria(
        id=1,
        titulo="Alguma matéria",
        conteudo="Algum conteúdo",
        url="https://brasileira.news/materia",
        wp_post_id=999,
        editoria="Geral",
        publicado_em=datetime.utcnow(),
    )
    
    decisao = roteador.rotear(mensagem_1_capa, [materia])
    
    # NUNCA deve retornar None ou ignorar
    assert decisao is not None
    assert decisao.acao == "reescrever"
    # Não deve exigir 3 matérias para agir
```

```python
# tests/consolidador/test_detector.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from brasileira.consolidador.detector import DetectorMateriasRelacionadas


@pytest.fixture
def mock_db():
    pool = AsyncMock()
    return pool


@pytest.fixture
def detector(mock_db):
    return DetectorMateriasRelacionadas(mock_db)


@pytest.mark.asyncio
async def test_buscar_materias_sobre_retorna_lista(detector):
    """buscar_materias_sobre deve retornar lista (nunca None)."""
    detector.db.fetch = AsyncMock(return_value=[])
    resultado = await detector.buscar_materias_sobre(
        palavras_chave=["Lula", "PEC"],
        tema_descricao="Lula anuncia nova PEC no Congresso",
    )
    assert isinstance(resultado, list)


@pytest.mark.asyncio
async def test_erro_banco_retorna_lista_vazia(detector):
    """Erro no banco deve retornar lista vazia, não levantar exceção."""
    detector.db.fetch = AsyncMock(side_effect=Exception("DB error"))
    resultado = await detector.buscar_materias_sobre(
        palavras_chave=["teste"],
        tema_descricao="tema teste",
    )
    assert resultado == []


@pytest.mark.asyncio
async def test_buscar_por_ids_vazio(detector):
    """Lista de IDs vazia retorna lista vazia."""
    resultado = await detector.buscar_por_ids([])
    assert resultado == []
```

### 14.2 Teste de Integração — Fluxo Completo

```python
# tests/consolidador/test_integration.py

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from brasileira.consolidador.agent import ConsolidadorAgent, EstadoConsolidador
from brasileira.consolidador.schemas import MensagemConsolidacao, ArtigoConcorrente
from datetime import datetime


@pytest.fixture
def mensagem_alta_urgencia():
    return MensagemConsolidacao(
        tema_id="tema_eleicoes_2026_pesquisa",
        tema_descricao="Nova pesquisa Datafolha: Lula com 55% nas intenções de voto para 2026",
        palavras_chave=["Datafolha", "pesquisa", "eleições 2026", "Lula", "intenção de voto"],
        num_capas=4,
        portais_detectados=["G1", "Folha", "Estadão", "UOL"],
        artigos_concorrentes=[
            ArtigoConcorrente(
                portal="Folha",
                titulo="Datafolha: Lula lidera com 55%; Bolsonaro tem 30%",
                url="https://folha.uol.com.br/pesquisa-2026",
                resumo="Nova pesquisa do Datafolha mostra Lula na liderança...",
                posicao_capa=1,
            ),
        ],
        ids_materias_proprias=[42, 43],  # Já temos 2 matérias sobre o tema
        urgencia="maxima",
        detectado_em=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_fluxo_consolidar_com_2_materias(mensagem_alta_urgencia):
    """
    Teste de integração: com 2 matérias, o agente deve consolidar e publicar.
    """
    # Mock dos componentes externos
    db_pool = AsyncMock()
    db_pool.fetch = AsyncMock(return_value=[
        {
            "id": 42,
            "titulo": "Lula lidera pesquisa para 2026 com 55%",
            "conteudo": "O presidente Lula aparece com 55% das intenções...",
            "url": "https://brasileira.news/lula-pesquisa-2026",
            "wp_post_id": 5001,
            "editoria": "Política",
            "publicado_em": datetime.utcnow(),
        },
        {
            "id": 43,
            "titulo": "Pesquisa eleitoral aponta cenários para 2026",
            "conteudo": "Especialistas analisam os dados da mais recente pesquisa...",
            "url": "https://brasileira.news/pesquisa-eleitoral-2026",
            "wp_post_id": 5002,
            "editoria": "Política",
            "publicado_em": datetime.utcnow(),
        },
    ])
    
    redis_client = AsyncMock()
    redis_client.exists = AsyncMock(return_value=0)  # Sem cooldown
    redis_client.setex = AsyncMock()
    
    smart_router = AsyncMock()
    smart_router.complete = AsyncMock(return_value=MagicMock(
        content='{"titulo": "Pesquisa Datafolha aponta Lula com 55%: o que os dados revelam", "conteudo": "<p>Análise...</p>", "excerpt": "Entenda o que a pesquisa significa.", "tags": ["Datafolha", "Lula", "Eleições 2026"], "seo_title": "Pesquisa Datafolha 2026: Lula com 55%", "seo_description": "Análise dos dados do Datafolha sobre 2026.", "categoria": "Política", "fontes_proprias_citadas": [], "fontes_concorrentes_citadas": [], "imagem_busca_gov": "Lula presidente", "imagem_busca_commons": "Luiz Inácio Lula da Silva", "block_stock_images": true, "legenda_imagem": "Presidente Lula durante coletiva.", "tipo_conteudo": "consolidacao_analitica", "num_fontes_proprias": 2, "resumo_editorial": "Análise integrada da pesquisa Datafolha"}',
        model="claude-opus-4-5",
        cost=0.08,
    ))
    
    wp_client = AsyncMock()
    wp_client.post = AsyncMock(return_value={"id": 99999, "link": "https://brasileira.news/?p=99999"})
    wp_client.get = AsyncMock(return_value=[{"id": 101, "name": "Datafolha"}])
    
    agente = ConsolidadorAgent(
        db_pool=db_pool,
        redis_client=redis_client,
        smart_router=smart_router,
        wp_client=wp_client,
        kafka_bootstrap_servers="kafka:9092",
    )
    
    # Prepara estado inicial
    estado = EstadoConsolidador(
        mensagem=mensagem_alta_urgencia,
        ciclo_id="teste_ciclo_001",
    )
    
    # Executa o grafo
    resultado = await agente.graph.ainvoke(estado.model_dump())
    
    # Verificações
    assert resultado["publicado"] is True
    assert resultado["wp_post_id"] == 99999
    assert resultado["acao"] == "consolidar"
    assert not resultado.get("pauta_gap_enviada", False)


@pytest.mark.asyncio  
async def test_fluxo_zero_materias_aciona_reporter(mensagem_alta_urgencia):
    """
    Teste de integração: com 0 matérias, envia pauta gap para Reporter.
    """
    mensagem_sem_materias = mensagem_alta_urgencia.model_copy(
        update={"ids_materias_proprias": []}
    )
    
    db_pool = AsyncMock()
    db_pool.fetch = AsyncMock(return_value=[])  # Nenhuma matéria encontrada
    
    redis_client = AsyncMock()
    redis_client.exists = AsyncMock(return_value=0)
    redis_client.setex = AsyncMock()
    
    producer_mock = AsyncMock()
    
    agente = ConsolidadorAgent(
        db_pool=db_pool,
        redis_client=redis_client,
        smart_router=AsyncMock(),
        wp_client=AsyncMock(),
        kafka_bootstrap_servers="kafka:9092",
    )
    agente.producer_gap = producer_mock
    
    estado = EstadoConsolidador(
        mensagem=mensagem_sem_materias,
        ciclo_id="teste_ciclo_zero",
    )
    
    resultado = await agente.graph.ainvoke(estado.model_dump())
    
    assert resultado["pauta_gap_enviada"] is True
    assert not resultado.get("publicado", False)
    assert resultado["acao"] == "acionar_reporter"
```

### 14.3 Checklist de Implementação

Use este checklist para validar a implementação antes de considerar o componente pronto:

#### Kafka e Comunicação
- [ ] Consumer do tópico `consolidacao` funcionando (grupo `consolidador-v3`)
- [ ] Commit manual após processamento (não auto-commit)
- [ ] Producer do tópico `pautas-gap` funcionando
- [ ] Retry exponencial na conexão Kafka (não trava se Kafka indisponível no boot)
- [ ] Mensagem malformada é logada e descartada sem travar o loop

#### Detecção de Matérias
- [ ] `buscar_por_ids()` funciona quando Monitor já identificou as matérias
- [ ] `buscar_materias_sobre()` funciona com busca por keywords quando IDs não estão disponíveis
- [ ] TF-IDF com threshold configurável (não fixo no código)
- [ ] Fallback: erro no banco retorna lista vazia, não exceção propagada
- [ ] Janela de tempo configurável (padrão 72h)

#### Lógica de Roteamento (CRÍTICO)
- [ ] **0 matérias → `acionar_reporter` (envia para pautas-gap)** ← REGRA INVIOLÁVEL
- [ ] **1 matéria → `reescrever` (LLM PREMIUM)** ← REGRA INVIOLÁVEL
- [ ] **2+ matérias → `consolidar` (LLM PREMIUM)** ← REGRA INVIOLÁVEL
- [ ] `MIN_SOURCES=3` **NÃO EXISTE** em nenhuma parte do código
- [ ] Portal Tier-1 aumenta prioridade mas não muda a lógica 0/1/2+
- [ ] Prioridade 1-10 calculada corretamente

#### Reescrita Editorial (1 fonte)
- [ ] System prompt `SYSTEM_PROMPT_REESCRITA` usado corretamente
- [ ] LLM chamado com `task_type="consolidacao_sintese"` (tier PREMIUM)
- [ ] JSON parseado corretamente (com fallback para extração forçada)
- [ ] Contexto dos concorrentes incluído no prompt
- [ ] Ângulo editorial diferenciado do original

#### Consolidação Analítica (2+ fontes)
- [ ] System prompt `SYSTEM_PROMPT_CONSOLIDACAO` usado corretamente
- [ ] LLM chamado com `task_type="consolidacao_sintese"` (tier PREMIUM)
- [ ] `max_tokens=5000` (análise precisa de espaço)
- [ ] Até 7 matérias processadas (não mais)
- [ ] Cada matéria limitada a 2000 chars para não explodir context window

#### Publicação WordPress
- [ ] Status sempre `publish` (NUNCA draft)
- [ ] Categoria mapeada para ID correto
- [ ] Tags criadas/reutilizadas corretamente
- [ ] Meta SEO preenchida (Yoast)
- [ ] Meta de rastreamento (consolidador_tipo, consolidador_tema_id, etc.)
- [ ] `wp_post_id` salvo na tabela `consolidacoes`

#### Memória
- [ ] Working memory (Redis): contexto do ciclo salvo e TTL de 4h
- [ ] Cooldown de tema: mesmo tema não reprocessado em menos de 1h
- [ ] Memória episódica (PostgreSQL): ciclo registrado após execução
- [ ] Falha na memória NÃO trava o pipeline (try/except sempre)

#### LangGraph
- [ ] Grafo compila sem erros
- [ ] Fluxo condicional: rotear → {acionar_reporter, coletar_fontes}
- [ ] Fluxo condicional: coletar_fontes → {reescrever, consolidar}
- [ ] Estado `EstadoConsolidador` propagado corretamente entre nós
- [ ] `END` sempre alcançado (não há loops infinitos)

#### Resiliência
- [ ] Qualquer exceção em qualquer nó é capturada e logada
- [ ] Loop principal NUNCA para por uma mensagem com erro
- [ ] LLM sem resposta: timeout e fallback para modelo alternativo (via SmartRouter)
- [ ] PostgreSQL indisponível: log de erro, retorna lista vazia, continua
- [ ] WordPress indisponível: log de erro, retenta 3x com backoff

#### Configuração
- [ ] Todas as credenciais via variáveis de ambiente (NUNCA hardcoded)
- [ ] `config.py` ou `.env` com todos os valores necessários
- [ ] Docker Compose com `restart: unless-stopped`
- [ ] Logs estruturados (nível, timestamp, tema_id, ação)

### 14.4 Validação de Ponta a Ponta

```bash
# 1. Injetar mensagem de teste no Kafka (via kafkacat ou script Python)
kafkacat -P -b kafka:9092 -t consolidacao -k "tema_teste_001" << 'EOF'
{
  "tema_id": "tema_teste_001",
  "tema_descricao": "Câmara aprova projeto de lei sobre inteligência artificial",
  "palavras_chave": ["IA", "inteligência artificial", "Câmara", "PL", "aprovação"],
  "num_capas": 3,
  "portais_detectados": ["G1", "Folha", "Estadão"],
  "artigos_concorrentes": [
    {
      "portal": "G1",
      "titulo": "Câmara aprova Marco da IA por 420 votos a 5",
      "url": "https://g1.globo.com/ia-marco-legal",
      "resumo": "Projeto foi aprovado em votação histórica",
      "posicao_capa": 1
    }
  ],
  "ids_materias_proprias": [],
  "urgencia": "alta",
  "detectado_em": "2026-03-26T14:30:00"
}
EOF

# 2. Verificar logs do Consolidador (deve logar: ROTA: acionar_reporter)
docker compose logs -f consolidador | grep -E "(ROTA|pauta_gap|erro)"

# 3. Verificar se pauta chegou ao Kafka pautas-gap
kafkacat -C -b kafka:9092 -t pautas-gap -o end -e

# 4. Testar com 1 matéria (deve reescrever e publicar)
# Primeiro, verificar que a matéria existe no PostgreSQL:
psql $DATABASE_URL -c "SELECT id, titulo, wp_post_id FROM artigos WHERE titulo ILIKE '%inteligência artificial%' LIMIT 3"

# 5. Verificar publicação no WordPress
curl -s "https://brasileira.news/wp-json/wp/v2/posts?meta_key=consolidador_tema_id&meta_value=tema_teste_001" | jq '.[].title.rendered'
```

### 14.5 Métricas de Saúde do Consolidador

Monitore estas métricas para garantir que o Consolidador está funcionando:

| Métrica | Alerta | Ação |
|---------|--------|------|
| `consolidacoes/hora` | < 2 em 4h | Verificar se Monitor Concorrência está enviando mensagens |
| `erros_llm/hora` | > 5 | Verificar SmartLLMRouter, chaves de API |
| `latencia_p95` | > 120s | LLM lento — verificar SmartRouter |
| `pauta_gap_sem_cobertura` | > 10 em 2h | Reporter pode estar sobrecarregado |
| `falha_wordpress` | > 3 consecutivos | Verificar WordPress, credenciais |
| `temas_em_cooldown` | > 50 | Normal — significa alta atividade |

---

## APÊNDICE A — DIFERENÇAS V2 vs V3 — RESUMO EXECUTIVO

| Aspecto | V2 (ERRADO) | V3 (CORRETO) |
|---------|-------------|--------------|
| **Trigger** | EventBus interno (TrendingDetector) | Kafka `consolidacao` do Monitor Concorrência |
| **Lógica mínima** | `MIN_SOURCES=3` | Lógica 0/1/2+ (NUNCA 3+) |
| **0 fontes** | Ignora silenciosamente | Envia para pautas-gap (Reporter cobre) |
| **1 fonte** | Ignora (< MIN_SOURCES) | **REESCREVE** com ângulo editorial |
| **2+ fontes** | Consolida (mas exigia 3) | **CONSOLIDA** em análise aprofundada |
| **Gate de qualidade** | Sim — pode ABORTAR publicação | Não — publica sempre |
| **Publicação** | Via EventBus → PublisherAgent | WordPress REST API direto |
| **Memória** | Fake (hooks sem implementação) | Working + Episódica + Semântica |
| **LLM tier** | PADRÃO (errado) | **PREMIUM** (correto) |
| **Integração** | Isolado do pipeline Kafka | Integrado: consome consolidacao, produz pautas-gap |

---

## APÊNDICE B — PERGUNTAS FREQUENTES (FAQ)

**P: O Consolidador pode publicar sobre o mesmo tema duas vezes?**
R: Sim, se forem consolidações diferentes (ex: 1h depois há 2 novas matérias). O cooldown de 1h no Redis evita duplicatas excessivas, mas não bloqueia cobertura legítima de evolução do tema.

**P: O que fazer se o LLM retornar JSON inválido?**
R: O método `_extrair_json_forcado()` tenta extrair o JSON via regex. Se ainda falhar, loga o erro e levanta exceção que é capturada no loop principal — o ciclo é marcado como falho e o loop continua com a próxima mensagem.

**P: O Consolidador deve reescrever artigos já publicados?**
R: **NÃO.** A reescrita editorial cria um **NOVO artigo** — não sobrescreve o original. O artigo original permanece publicado. O novo artigo tem um ângulo editorial diferente.

**P: E se o Monitor Concorrência enviar a mesma mensagem duas vezes?**
R: O cooldown de 1h no Redis (`consolidador:tema_cooldown:{tema_id}`) evita o reprocessamento. Se a segunda mensagem chegar após 1h, é tratada normalmente (o tema pode ter evoluído).

**P: O Consolidador usa os artigos dos concorrentes como fonte direta?**
R: **NÃO.** Os artigos dos concorrentes são usados apenas como **contexto** para enriquecer a reescrita/consolidação. O LLM é instruído a citar os concorrentes com `rel="nofollow"` e a NÃO reproduzir parágrafos deles.

**P: Por que a prioridade existe se não muda a lógica 0/1/2+?**
R: A prioridade é passada na mensagem de pautas-gap para o Reporter — artigos de temas com prioridade mais alta podem ser processados primeiro pelo Reporter quando houver fila. Não afeta o Consolidador em si.

**P: Qual o tempo médio de processamento esperado?**
R: Reescrita: 15-45s (1 chamada LLM PREMIUM). Consolidação: 30-90s (1 chamada LLM PREMIUM com prompt maior). Total do ciclo (incluindo I/O): 20-120s.

---

*Briefing gerado em: 26 de março de 2026*
*Componente: #7 — Consolidador (Reescritor/Consolidador de Matérias)*
*Versão: V3*
*Repositório: https://github.com/redes-dsc/brasileira*
