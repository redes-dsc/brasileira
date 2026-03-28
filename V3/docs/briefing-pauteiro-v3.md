# Briefing Completo para IA — Pauteiro V3 (Agente de Inteligência Editorial)

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #9
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / LangGraph / Kafka / Redis / PostgreSQL + pgvector / LiteLLM
**Componente:** `brasileira/agents/pauteiro.py` + módulos auxiliares de trending

---

## LEIA ISTO PRIMEIRO — Papel e Mandato do Pauteiro V3

O Pauteiro V3 é o **Agente de Inteligência Editorial** da brasileira.news. Ele opera **em paralelo** ao pipeline principal, nunca bloqueando, nunca filtrando. Seu único propósito é detectar oportunidades editoriais que as fontes RSS/scrapers não cobrem automaticamente — trending topics no Google Trends, movimentos em redes sociais, eventos em tempo real — e gerar briefings de alta qualidade para os Reporters via Kafka `pautas-especiais`.

**O que mudou radicalmente em relação à V2:** O `pauteiro-15.py` da V2 era um gargalo fatal: ele se posicionava como entry point do pipeline, filtrava 99% das fontes, e gerava no máximo ~20 pautas por ciclo. **Na V3, o Pauteiro não toca no pipeline de fontes RSS/scrapers.** As 648+ fontes fluem 100% pelos Workers de Coletores (Componente #2), independentemente do Pauteiro. O Pauteiro monitora fontes **externas** — Google Trends, Twitter/X Trends, Reddit, feeds de agências — que os coletores não cobrem.

**Regras INVIOLÁVEIS do Pauteiro V3:**
1. **NÃO é entry point.** Conteúdo de 648+ fontes flui sem passar pelo Pauteiro.
2. **NÃO filtra conteúdo.** Nunca rejeita artigos das fontes.
3. **NÃO bloqueia publicação.** O Reporter publica independentemente.
4. **LLM PREMIUM** para geração de briefings de pauta especial.
5. **LLM PADRÃO** para trending detection e análise inicial.
6. **Produz para Kafka `pautas-especiais`** com particionamento por editoria.
7. **Memória real:** semântica, episódica e working — nunca hooks vazios.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTAVA QUEBRADO NA V2

### 1.1 O Problema Central: Pauteiro como Gatekeeper Fatal

O `pauteiro-15.py` cometia o erro arquitetural mais grave do sistema V2: posicionava-se no **início** do pipeline de publicação, bloqueando tudo.

```
V2 (QUEBRADO):
Fontes RSS/Scrapers (648+)
    ↓
[pauteiro-15.py] ← FILTRA 99% DAS FONTES
    ↓ (no máximo ~20 pautas)
[Editor-Chefe] ← GATE #2
    ↓
[Editor de Editoria] ← GATE #3
    ↓
[Reporter] → FAZ DRAFT (não publica)
    ↓
[Revisor] ← PODE REJEITAR
    ↓
[Publisher] ← ESPERA APROVAÇÃO QUE NUNCA CHEGA
= 0 artigos publicados em 24h
```

**Resultado:** Com 648 fontes gerando centenas de artigos, o pauteiro selecionava ~20 e descartava o resto. O sistema inteiro dependia desses 20 itens para publicar.

### 1.2 Mapeamento dos Problemas do pauteiro-15.py

| # | Problema Fatal | Impacto | Solução V3 |
|---|----------------|---------|------------|
| 1 | **Entry point do pipeline** — fontes só chegam ao Reporter se passarem pelo Pauteiro | 0 artigos publicados | Pauteiro é paralelo, não bloqueante |
| 2 | **Filtro de 99% das fontes** — detectava "trends" com min_sources=3 e descartava o resto | Cobertura de <1% das fontes | Worker Pool de Coletores cobre 100% das fontes |
| 3 | **EventBus em vez de Kafka** — publicava via `event_bus.publish("nova_noticia")` sem persistência | Pautas perdidas se o consumer não estiver ativo | Kafka `pautas-especiais` com retenção e replay |
| 4 | **LLM PADRÃO para pautas especiais** — a geração de briefings usava modelo econômico | Briefings genéricos, sem ângulo editorial | LLM PREMIUM obrigatório para geração de briefings |
| 5 | **Memória fake** — `SemanticMemory` injetada mas nunca usada efetivamente | Duplicação de pautas entre ciclos | Memória semântica real com pgvector |
| 6 | **TF-IDF simples para trending** — só RSS interno, sem Google Trends, sem X/Twitter | Perde trends que não estão nas fontes | Multi-fonte: Google Trends + X + Reddit + RSS |
| 7 | **Ciclos síncronos** — poll_sources → detect_trends → create_pautas em sequência | Latência alta, miss de breaking news | Loops assíncronos paralelos por fonte |
| 8 | **Categoria inferida por keywords simples** — 5 categorias hardcoded | Cobertura de apenas 5/16 editorias | 16 macrocategorias via classificador ML |
| 9 | **Sem scratchpad** — estado perdido entre ciclos | Ciclo reinicia sem histórico | `radar_fontes_{ciclo}.json` persistido |
| 10 | **Sem circuit breaker em APIs externas** — Google Trends, Twitter sem proteção | Crash do agente inteiro se API falha | Circuit breaker por fonte externa |

### 1.3 O Código V2 que Exemplifica os Problemas

```python
# pauteiro-15.py — PROBLEMA 1: Entry point bloqueante
# O Reporter ESPERAVA o evento "nova_noticia" do Pauteiro para escrever
# Se Pauteiro não detectava trend → Reporter ficava idle
if self.event_bus:
    await self.event_bus.publish(
        channel="nova_noticia",  # ← Reporter ficava esperando ISTO
        message={"pauta": pauta, "trending_score": topic.get("score", 0)},
        sender=self.agent_id,
        message_type="nova_noticia",
    )

# PROBLEMA 2: TF-IDF com min_sources=3 → descarta 99%
trends = self.trending_detector.detect_trends(
    titles, min_sources=self.min_sources_trending  # min_sources_trending=3
)
# Se um tema aparece em apenas 1-2 fontes → DESCARTADO
# Com 648 fontes e ~20 trends detectados → 99% das notícias filtradas

# PROBLEMA 3: Só 5 categorias hardcoded
category_keywords = {
    "politica": ["lula", "bolsonaro", "governo", ...],
    "economia": ["dólar", "bolsa", "pib", ...],
    "tecnologia": ["ia", "inteligência artificial", ...],
    "esportes": ["futebol", "copa", "brasileirão", ...],
    "entretenimento": ["bbb", "novela", "celebridade", ...],
}
# Saúde, Ciência, Mundo, Meio Ambiente, Educação, etc. → "brasil" genérico

# PROBLEMA 4: Sem Google Trends, sem X, sem Reddit
# Só consumia RSS das mesmas fontes que o Worker Pool já cobre
# Não havia valor agregado externo
```

### 1.4 O que o V3 Corrige

```
V3 (CORRETO):

[648+ Fontes] → [Worker Pool Coletores] → [Kafka: raw-articles] → [Reporter] → PUBLICA
                                                                              (independente)

PARALELO (nunca bloqueia o pipeline acima):
[Pauteiro V3]
    ├── [Loop A] Google Trends Brasil → trending keywords → briefing PREMIUM → Kafka pautas-especiais
    ├── [Loop B] Twitter/X Trending Topics → análise → briefing PREMIUM → Kafka pautas-especiais
    ├── [Loop C] Reddit r/brasil + r/saopaulo → discussions → briefing PREMIUM → Kafka pautas-especiais
    ├── [Loop D] Agências (AP, AFP, Reuters) → breaking news → briefing PREMIUM → Kafka pautas-especiais
    └── [Loop E] Dedup + memória → evita briefings duplicados

[Reporter] consome Kafka pautas-especiais → escreve + publica
           (além de consumir classified-articles normalmente)
```

---

## PARTE II — ARQUITETURA V3 DO PAUTEIRO

### 2.1 Visão Geral do Componente

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PAUTEIRO V3                                          │
│                   Agente de Inteligência Editorial                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ CAMADA 1: MONITORES EXTERNOS (5 loops assíncronos paralelos)         │    │
│  │  ├── GoogleTrendsMonitor     (ciclo: 30 min)                         │    │
│  │  ├── XTrendsMonitor          (ciclo: 15 min)                         │    │
│  │  ├── RedditMonitor           (ciclo: 30 min)                         │    │
│  │  ├── AgenciasMonitor         (ciclo: 10 min) — AP, AFP, Reuters      │    │
│  │  └── InternalTrendMonitor    (ciclo: 20 min) — analisa artigos já    │    │
│  │                               publicados para detectar temas quentes │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │ raw_signals[]                              │
│  ┌──────────────────────────────▼──────────────────────────────────────┐    │
│  │ CAMADA 2: AGREGADOR DE SINAIS                                         │    │
│  │  ├── Normalização de sinais (score 0-100)                             │    │
│  │  ├── Cross-fonte correlation (mesmo tema em múltiplas fontes)         │    │
│  │  ├── Deduplicação por tema (MinHash)                                  │    │
│  │  └── Urgency scoring (BREAKING / ESPECIAL / NORMAL)                  │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │ signals_candidatos[]                       │
│  ┌──────────────────────────────▼──────────────────────────────────────┐    │
│  │ CAMADA 3: FILTRO DE COBERTURA (consulta memória)                     │    │
│  │  ├── Consulta pgvector: tema já coberto recentemente?                 │    │
│  │  ├── Consulta Redis: pauta já enviada neste ciclo?                    │    │
│  │  └── Consulta Kafka: artigo sobre este tema já publicado?             │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │ sinais_novos[]                             │
│  ┌──────────────────────────────▼──────────────────────────────────────┐    │
│  │ CAMADA 4: GERAÇÃO DE BRIEFINGS (LLM PREMIUM)                         │    │
│  │  ├── Briefing completo: título, ângulo, contexto, fontes, urgência    │    │
│  │  ├── Sugestão de ângulo editorial diferenciado                        │    │
│  │  └── Mapeamento para 1 das 16 macrocategorias                         │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │ briefings[]                                │
│  ┌──────────────────────────────▼──────────────────────────────────────┐    │
│  │ CAMADA 5: PUBLICAÇÃO E MEMÓRIA                                        │    │
│  │  ├── Kafka: pautas-especiais (key=editoria)                           │    │
│  │  ├── pgvector: salva embedding do tema (evita futura duplicação)      │    │
│  │  └── Redis: working memory do ciclo atual                             │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Princípios OBRIGATÓRIOS

1. **NUNCA bloqueia o pipeline principal.** O Pauteiro roda em processo separado, totalmente desacoplado via Kafka.
2. **NUNCA filtra fontes RSS/scrapers.** Essas fontes são responsabilidade exclusiva do Worker Pool de Coletores.
3. **LLM PREMIUM para `pauta_especial`.** Briefings exigem criatividade editorial máxima.
4. **LLM PADRÃO para `trending_detection`.** Análise inicial de sinais não precisa de máxima qualidade.
5. **Circuit breaker em cada API externa.** Se Google Trends cai, os outros 4 loops continuam.
6. **Memória semântica real.** Embeddings em pgvector para detectar cobertura duplicada.
7. **Progressive Disclosure.** Primeiro carrega só título+score, depois expande contexto para geração do briefing.
8. **Kafka como saída única.** Nunca EventBus, nunca chamada direta ao Reporter.

### 2.3 Stack do Componente

| Dependência | Versão | Função |
|-------------|--------|--------|
| `pytrends` | `>=4.9.0` | Interface não-oficial para Google Trends |
| `tweepy` | `>=4.14.0` | X/Twitter API v2 (trending topics) |
| `praw` | `>=7.7.0` | Reddit API (threads trending) |
| `httpx` | `>=0.27.0` | Requisições async para feeds de agências |
| `feedparser` | `>=6.0.10` | Parse de RSS/Atom de agências |
| `aiokafka` | `>=0.10.0` | Producer/Consumer Kafka assíncrono |
| `redis[hiredis]` | `>=5.0.0` | Working memory e deduplicação |
| `asyncpg` | `>=0.29.0` | Acesso async ao PostgreSQL (pgvector) |
| `pgvector` | `>=0.2.5` | Embeddings de temas para dedup semântica |
| `litellm` | `>=1.80.0,!=1.82.7,!=1.82.8` | Roteamento LLM (via SmartLLMRouter) |
| `langgraph` | `>=0.1.0` | Grafo de estados do agente |
| `scikit-learn` | `>=1.4.0` | TF-IDF e similaridade para clustering interno |
| `datasketch` | `>=1.6.0` | MinHash para deduplicação rápida |
| `langchain-openai` | `>=0.1.0` | Embeddings OpenAI para pgvector |

---

## PARTE III — MONITORAMENTO DE TRENDS: 5 FONTES EXTERNAS

### 3.1 Google Trends Monitor

**Ciclo:** 30 minutos | **Tier LLM:** PADRÃO (análise) + PREMIUM (briefing)

O Google Trends é a fonte primária de inteligência editorial. A API oficial do Google Trends foi lançada em 2025, mas `pytrends` ainda é a interface mais prática para Python.

```python
# brasileira/agents/pauteiro/monitors/google_trends.py

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from pytrends.request import TrendReq

logger = logging.getLogger("brasileira.pauteiro.google_trends")


class GoogleTrendsMonitor:
    """
    Monitora Google Trends Brasil para detectar trending searches.

    Ciclo: 30 minutos
    Foco: Brasil (geo='BR'), português
    Retorna sinais normalizados com score 0-100
    """

    CYCLE_INTERVAL_SECONDS = 1800  # 30 min
    GEO_BRASIL = "BR"
    LANG_PORTUGUES = "pt-BR"

    # Categorias Google Trends mapeadas para macrocategorias V3
    CATEGORY_MAP = {
        "Manchetes": "Últimas Notícias",
        "Negócios": "Economia",
        "Entretenimento": "Cultura/Entretenimento",
        "Saúde": "Saúde",
        "Ciência/Tecnologia": "Tecnologia",
        "Esportes": "Esportes",
        "Mundo": "Mundo/Internacional",
    }

    def __init__(
        self,
        circuit_breaker: Any,
        redis_client: Any,
        timeout_s: int = 20,
    ):
        self.circuit_breaker = circuit_breaker
        self.redis = redis_client
        self.timeout_s = timeout_s
        self._pytrends = None
        self._last_run: datetime | None = None

    def _get_client(self) -> TrendReq:
        """Retorna client pytrends, criando se necessário."""
        if self._pytrends is None:
            self._pytrends = TrendReq(
                hl=self.LANG_PORTUGUES,
                tz=-180,  # UTC-3 (Brasília)
                timeout=(self.timeout_s, self.timeout_s),
                retries=2,
                backoff_factor=0.1,
            )
        return self._pytrends

    async def get_realtime_trends(self) -> list[dict]:
        """
        Retorna trending searches em tempo real no Brasil.

        Returns:
            Lista de sinais com: keyword, score, categoria, fonte
        """
        if not self.circuit_breaker.should_allow("google_trends"):
            logger.warning("GoogleTrends circuit breaker ABERTO — skipping ciclo")
            return []

        try:
            # Executa em thread pool (pytrends é síncrono)
            trends_data = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_trends_sync
            )
            self.circuit_breaker.record_success("google_trends")
            self._last_run = datetime.utcnow()
            return trends_data

        except Exception as e:
            self.circuit_breaker.record_failure("google_trends")
            logger.error("GoogleTrends fetch falhou: %s", e)
            return []

    def _fetch_trends_sync(self) -> list[dict]:
        """Execução síncrona do pytrends (chamada em executor)."""
        client = self._get_client()
        signals = []

        # 1. Realtime Trending Searches (últimas 24h, Brasil)
        try:
            df_realtime = client.realtime_trending_searches(pn="BR")
            if df_realtime is not None and not df_realtime.empty:
                for _, row in df_realtime.iterrows():
                    title = row.get("title", "")
                    articles = row.get("articles", [])
                    if not title:
                        continue

                    # Score baseado em posição no ranking (1º = 100, 20º = 5)
                    score = max(5, 100 - (signals.__len__() * 5))

                    signals.append({
                        "keyword": title,
                        "score": score,
                        "fonte": "google_trends_realtime",
                        "categoria_raw": row.get("entityNames", []),
                        "artigos_relacionados": [
                            a.get("url", "") for a in articles[:3]
                        ],
                        "timestamp": datetime.utcnow().isoformat(),
                        "geo": self.GEO_BRASIL,
                    })
        except Exception as e:
            logger.warning("Realtime trends fetch falhou: %s", e)

        # 2. Daily Trending Searches (hoje, Brasil)
        try:
            df_daily = client.today_searches(pn="BR")
            if df_daily is not None:
                for i, keyword in enumerate(df_daily.tolist()[:20]):
                    if keyword and keyword not in [s["keyword"] for s in signals]:
                        signals.append({
                            "keyword": keyword,
                            "score": max(5, 80 - (i * 4)),
                            "fonte": "google_trends_daily",
                            "categoria_raw": [],
                            "artigos_relacionados": [],
                            "timestamp": datetime.utcnow().isoformat(),
                            "geo": self.GEO_BRASIL,
                        })
        except Exception as e:
            logger.warning("Daily trends fetch falhou: %s", e)

        # 3. Interest Over Time para palavras-chave editoriais importantes
        # (Complementa com contexto para os trending)
        editorial_keywords = [
            "governo federal", "eleições", "dólar hoje",
            "copa do mundo", "STF", "inflação"
        ]
        try:
            client.build_payload(
                editorial_keywords[:5],
                timeframe="now 1-d",
                geo=self.GEO_BRASIL,
            )
            interest_df = client.interest_over_time()
            if interest_df is not None and not interest_df.empty:
                last_row = interest_df.iloc[-1]
                for kw in editorial_keywords[:5]:
                    if kw in last_row and last_row[kw] > 70:  # Acima de 70/100
                        signals.append({
                            "keyword": kw,
                            "score": int(last_row[kw]),
                            "fonte": "google_trends_interest",
                            "categoria_raw": [],
                            "artigos_relacionados": [],
                            "timestamp": datetime.utcnow().isoformat(),
                            "geo": self.GEO_BRASIL,
                        })
        except Exception as e:
            logger.debug("Interest over time fetch falhou: %s", e)

        return signals


### 3.2 X/Twitter Trends Monitor

```python
# brasileira/agents/pauteiro/monitors/x_trends.py

import asyncio
import logging
from datetime import datetime
from typing import Any

import tweepy

logger = logging.getLogger("brasileira.pauteiro.x_trends")

# WOEID do Brasil para trends do Twitter (legado, ainda funciona)
BRASIL_WOEID = 23424768
# Grandes cidades brasileiras
CIDADE_WOEIDS = {
    "São Paulo": 455827,
    "Rio de Janeiro": 455820,
    "Brasília": 455854,
    "Belo Horizonte": 455812,
}


class XTrendsMonitor:
    """
    Monitora trending topics do X/Twitter para Brasil.

    Ciclo: 15 minutos (mais frequente — X tem alta volatilidade)
    Usa Twitter API v2 via Tweepy
    Fallback: dados de ciclo anterior se API indisponível
    """

    CYCLE_INTERVAL_SECONDS = 900  # 15 min
    MAX_TRENDS = 30

    def __init__(
        self,
        bearer_token: str,
        circuit_breaker: Any,
        redis_client: Any,
    ):
        self.bearer_token = bearer_token
        self.circuit_breaker = circuit_breaker
        self.redis = redis_client
        self._client: tweepy.Client | None = None
        self._last_trends: list[dict] = []

    def _get_client(self) -> tweepy.Client:
        if self._client is None:
            self._client = tweepy.Client(
                bearer_token=self.bearer_token,
                wait_on_rate_limit=False,  # Não bloqueia — usamos circuit breaker
            )
        return self._client

    async def get_trends(self) -> list[dict]:
        """Retorna trending topics do X/Twitter para o Brasil."""
        if not self.circuit_breaker.should_allow("x_twitter"):
            logger.warning("X/Twitter circuit breaker ABERTO — retornando cache")
            return self._last_trends  # Retorna último resultado conhecido

        try:
            trends = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_trends_sync
            )
            if trends:
                self._last_trends = trends
                # Cache Redis por 20 min
                await self.redis.setex(
                    "pauteiro:x_trends:latest",
                    1200,
                    __import__("json").dumps(trends[:20])
                )
            self.circuit_breaker.record_success("x_twitter")
            return trends

        except tweepy.TooManyRequests:
            logger.warning("X/Twitter rate limit — circuit breaker fechado por 15 min")
            self.circuit_breaker.record_failure("x_twitter")
            return self._last_trends

        except Exception as e:
            self.circuit_breaker.record_failure("x_twitter")
            logger.error("X/Twitter trends fetch falhou: %s", e)
            return self._last_trends

    def _fetch_trends_sync(self) -> list[dict]:
        """Busca trends via Tweepy API v1.1 (trends/place ainda disponível)."""
        # Nota: Para trends por localização, ainda usamos API v1.1
        auth = tweepy.OAuth2BearerHandler(self.bearer_token)
        api_v1 = tweepy.API(auth, wait_on_rate_limit=False)

        signals = []

        # Trends do Brasil (nacional)
        try:
            brasil_trends = api_v1.get_place_trends(BRASIL_WOEID)
            if brasil_trends and brasil_trends[0].get("trends"):
                for i, trend in enumerate(brasil_trends[0]["trends"][:self.MAX_TRENDS]):
                    name = trend.get("name", "")
                    tweet_volume = trend.get("tweet_volume") or 0

                    if not name:
                        continue

                    # Score: combinação de posição + volume de tweets
                    position_score = max(5, 100 - (i * 3))
                    volume_score = min(40, tweet_volume // 1000) if tweet_volume else 0
                    score = min(100, position_score + volume_score)

                    signals.append({
                        "keyword": name,
                        "score": score,
                        "tweet_volume": tweet_volume,
                        "fonte": "x_twitter_brasil",
                        "is_hashtag": name.startswith("#"),
                        "url": trend.get("url", ""),
                        "geo": "BR",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
        except Exception as e:
            logger.warning("Trends Brasil falhou: %s", e)

        return signals
```

### 3.3 Reddit Monitor

```python
# brasileira/agents/pauteiro/monitors/reddit_monitor.py

import asyncio
import logging
from datetime import datetime
from typing import Any

import praw

logger = logging.getLogger("brasileira.pauteiro.reddit")


# Subreddits brasileiros relevantes para monitoramento editorial
SUBREDDITS_BRASIL = [
    "brasil",           # General — 2M+ membros
    "braziliannews",    # Notícias em inglês sobre o Brasil
    "saopaulo",         # Regional SP
    "riodejaneiro",     # Regional RJ
    "farialimabets",    # Economia/finanças brasileiras
    "investimentos",    # Economia pessoal
    "futebol",          # Esportes
    "brdev",            # Tecnologia/dev brasileiro
]


class RedditMonitor:
    """
    Monitora Reddit para detectar discussões quentes sobre o Brasil.

    Ciclo: 30 minutos
    Foco: Posts hot/rising em subreddits brasileiros
    Score: upvote ratio × upvotes (normalizado 0-100)
    """

    CYCLE_INTERVAL_SECONDS = 1800  # 30 min
    MAX_POSTS_PER_SUB = 10
    MIN_SCORE = 50  # Upvotes mínimos para considerar

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        circuit_breaker: Any,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.circuit_breaker = circuit_breaker
        self._reddit: praw.Reddit | None = None

    def _get_client(self) -> praw.Reddit:
        if self._reddit is None:
            self._reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
                read_only=True,
            )
        return self._reddit

    async def get_hot_topics(self) -> list[dict]:
        """Retorna tópicos quentes do Reddit brasileiro."""
        if not self.circuit_breaker.should_allow("reddit"):
            logger.warning("Reddit circuit breaker ABERTO")
            return []

        try:
            topics = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_topics_sync
            )
            self.circuit_breaker.record_success("reddit")
            return topics

        except Exception as e:
            self.circuit_breaker.record_failure("reddit")
            logger.error("Reddit fetch falhou: %s", e)
            return []

    def _fetch_topics_sync(self) -> list[dict]:
        """Busca posts hot/rising em subreddits brasileiros."""
        reddit = self._get_client()
        signals = []
        seen_titles: set[str] = set()

        for subreddit_name in SUBREDDITS_BRASIL:
            try:
                subreddit = reddit.subreddit(subreddit_name)

                # Posts em alta (hot) — últimas 24h
                for post in subreddit.hot(limit=self.MAX_POSTS_PER_SUB):
                    if post.score < self.MIN_SCORE:
                        continue
                    if post.title in seen_titles:
                        continue

                    seen_titles.add(post.title)

                    # Score normalizado: max(100, upvotes/10)
                    score = min(100, post.score // 10)

                    signals.append({
                        "keyword": post.title,
                        "score": score,
                        "upvotes": post.score,
                        "num_comments": post.num_comments,
                        "upvote_ratio": post.upvote_ratio,
                        "url": f"https://reddit.com{post.permalink}",
                        "subreddit": subreddit_name,
                        "fonte": "reddit_hot",
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                # Posts em ascensão (rising) — tendências emergentes
                for post in subreddit.rising(limit=5):
                    if post.score < 20:  # Limiar menor para rising
                        continue
                    if post.title in seen_titles:
                        continue

                    seen_titles.add(post.title)
                    signals.append({
                        "keyword": post.title,
                        "score": min(60, post.score // 5),
                        "upvotes": post.score,
                        "num_comments": post.num_comments,
                        "url": f"https://reddit.com{post.permalink}",
                        "subreddit": subreddit_name,
                        "fonte": "reddit_rising",
                        "timestamp": datetime.utcnow().isoformat(),
                    })

            except Exception as e:
                logger.warning("Falha no subreddit r/%s: %s", subreddit_name, e)
                continue

        return signals
```

### 3.4 Agências de Notícias Monitor

```python
# brasileira/agents/pauteiro/monitors/agencias_monitor.py

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx

logger = logging.getLogger("brasileira.pauteiro.agencias")


# Feeds RSS de agências de notícias globais e brasileiras
AGENCIAS_FEEDS = [
    # Agências internacionais
    {
        "nome": "Reuters Brasil",
        "url": "https://feeds.reuters.com/reuters/BRESTopNews",
        "idioma": "pt-BR",
        "tier": "alta",
    },
    {
        "nome": "AP Brasil",
        "url": "https://apnews.com/hub/brazil/rss",
        "idioma": "en",
        "tier": "alta",
    },
    {
        "nome": "AFP Brasil",
        "url": "https://www.afp.com/en/rssfeed",
        "idioma": "en",
        "tier": "alta",
    },
    # Agências brasileiras
    {
        "nome": "Agência Brasil",
        "url": "https://agenciabrasil.ebc.com.br/rss/ultimas-noticias/feed.xml",
        "idioma": "pt-BR",
        "tier": "alta",
    },
    {
        "nome": "Agência Senado",
        "url": "https://www12.senado.leg.br/noticias/rss/ultimas-noticias.rss",
        "idioma": "pt-BR",
        "tier": "media",
    },
    {
        "nome": "Agência Câmara",
        "url": "https://www.camara.leg.br/noticias/rss/ultimas-noticias",
        "idioma": "pt-BR",
        "tier": "media",
    },
    # Feeds internacionais relevantes para o Brasil
    {
        "nome": "BBC Brasil",
        "url": "https://feeds.bbci.co.uk/portuguese/rss.xml",
        "idioma": "pt-BR",
        "tier": "alta",
    },
    {
        "nome": "Al Jazeera Brasil",
        "url": "https://brasil.elpais.com/rss/brasil/a_fondo/portada_brasil.xml",
        "idioma": "pt-BR",
        "tier": "media",
    },
]

# Palavras-chave de breaking news em português
BREAKING_KEYWORDS = [
    "urgente", "breaking", "ao vivo", "última hora", "alerta",
    "acidente", "explosão", "terremoto", "ataque", "morte",
    "eleição", "resultado", "declaração", "pronunciamento",
]


class AgenciasMonitor:
    """
    Monitora feeds RSS de agências de notícias para detecting breaking news.

    Ciclo: 10 minutos (mais frequente — agências têm breaking news)
    Diferencial: detecta notícias de agências ANTES de chegarem às fontes RSS
    normais, gerando pautas antecipadas para o Reporter.
    """

    CYCLE_INTERVAL_SECONDS = 600  # 10 min
    MAX_AGE_MINUTES = 30  # Ignora itens mais velhos que 30 min

    def __init__(
        self,
        circuit_breaker: Any,
        http_timeout: int = 15,
    ):
        self.circuit_breaker = circuit_breaker
        self.http_timeout = http_timeout
        self._processed_urls: set[str] = set()

    async def get_breaking_signals(self) -> list[dict]:
        """Busca breaking news de todas as agências em paralelo."""
        if not self.circuit_breaker.should_allow("agencias"):
            return []

        tasks = [
            self._fetch_feed(feed)
            for feed in AGENCIAS_FEEDS
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        signals = []

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Feed de agência falhou: %s", result)
                continue
            if isinstance(result, list):
                signals.extend(result)

        self.circuit_breaker.record_success("agencias")
        return signals

    async def _fetch_feed(self, feed_config: dict) -> list[dict]:
        """Busca e processa um feed de agência."""
        url = feed_config["url"]
        nome = feed_config["nome"]
        tier = feed_config["tier"]

        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                content = response.text

            # Parse do feed (em executor para não bloquear)
            parsed = await asyncio.get_event_loop().run_in_executor(
                None, feedparser.parse, content
            )

            signals = []
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.MAX_AGE_MINUTES)

            for entry in parsed.entries[:20]:
                entry_url = getattr(entry, "link", "")

                # Pula já processados
                if entry_url in self._processed_urls:
                    continue

                # Verifica idade
                published = getattr(entry, "published_parsed", None)
                if published:
                    import time
                    pub_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
                    if pub_dt < cutoff:
                        continue

                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")

                if not title:
                    continue

                # Detecta breaking news por palavras-chave
                is_breaking = any(
                    kw in title.lower() or kw in summary.lower()
                    for kw in BREAKING_KEYWORDS
                )

                # Score baseado em tier da agência + breaking status
                base_score = 80 if tier == "alta" else 60
                score = min(100, base_score + (20 if is_breaking else 0))

                self._processed_urls.add(entry_url)
                signals.append({
                    "keyword": title,
                    "resumo": summary[:500],
                    "url": entry_url,
                    "score": score,
                    "is_breaking": is_breaking,
                    "agencia": nome,
                    "idioma": feed_config["idioma"],
                    "fonte": f"agencia_{nome.lower().replace(' ', '_')}",
                    "timestamp": datetime.utcnow().isoformat(),
                })

            # Limita conjunto de URLs processadas (evita crescimento ilimitado)
            if len(self._processed_urls) > 10000:
                self._processed_urls = set(list(self._processed_urls)[-5000:])

            return signals

        except Exception as e:
            logger.warning("Falha ao buscar feed %s (%s): %s", nome, url, e)
            return []
```

### 3.5 Internal Trend Monitor

```python
# brasileira/agents/pauteiro/monitors/internal_trends.py

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import asyncpg
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

logger = logging.getLogger("brasileira.pauteiro.internal_trends")


class InternalTrendMonitor:
    """
    Analisa artigos já publicados para detectar temas em alta internamente.

    Ciclo: 20 minutos
    Função: Detecta clusters de cobertura que indicam tema quente,
            sinaliza oportunidade de consolidação ou ângulo adicional.
    Diferencial: Cross-referencia o que JÁ publicamos com o que está
                 em alta externamente — evita redundância E detecta gaps.
    """

    CYCLE_INTERVAL_SECONDS = 1200  # 20 min
    LOOKBACK_HOURS = 4  # Analisa últimas 4 horas de publicação
    MIN_ARTICLES_FOR_CLUSTER = 3  # Mínimo de artigos para detectar cluster

    def __init__(self, db_pool: asyncpg.Pool, circuit_breaker: Any):
        self.db_pool = db_pool
        self.circuit_breaker = circuit_breaker

    async def get_internal_trends(self) -> list[dict]:
        """Detecta clusters de temas nos artigos recentes publicados."""
        try:
            async with self.db_pool.acquire() as conn:
                # Busca artigos das últimas 4 horas
                cutoff = datetime.utcnow() - timedelta(hours=self.LOOKBACK_HOURS)
                rows = await conn.fetch(
                    """
                    SELECT id, titulo, editoria, score_relevancia, wp_post_id,
                           created_at
                    FROM artigos
                    WHERE created_at >= $1
                      AND wp_post_id IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 200
                    """,
                    cutoff,
                )

            if len(rows) < self.MIN_ARTICLES_FOR_CLUSTER:
                return []

            titles = [row["titulo"] for row in rows]
            editorias = [row["editoria"] for row in rows]

            # TF-IDF clustering para detectar temas recorrentes
            vectorizer = TfidfVectorizer(
                max_features=500,
                ngram_range=(1, 3),
                min_df=2,
                stop_words=self._stopwords_pt(),
            )

            try:
                tfidf_matrix = vectorizer.fit_transform(titles)
            except ValueError:
                return []  # Corpus muito pequeno

            # Similaridade entre artigos
            sim_matrix = cosine_similarity(tfidf_matrix)

            # Agrupa artigos similares (threshold 0.3)
            clusters = self._find_clusters(sim_matrix, rows, threshold=0.3)

            signals = []
            for cluster in clusters:
                if len(cluster["artigos"]) < self.MIN_ARTICLES_FOR_CLUSTER:
                    continue

                # Extrai keywords do cluster via TF-IDF
                cluster_indices = cluster["indices"]
                cluster_matrix = tfidf_matrix[cluster_indices]
                feature_names = vectorizer.get_feature_names_out()
                mean_tfidf = np.asarray(cluster_matrix.mean(axis=0)).flatten()
                top_indices = mean_tfidf.argsort()[-5:][::-1]
                keywords = [feature_names[i] for i in top_indices]

                # Score: baseado no número de artigos no cluster
                score = min(100, len(cluster["artigos"]) * 15)

                # Editoria dominante no cluster
                cluster_editorias = [
                    rows[i]["editoria"] for i in cluster_indices
                ]
                editoria_dominante = max(
                    set(cluster_editorias),
                    key=cluster_editorias.count
                )

                signals.append({
                    "keyword": " + ".join(keywords[:3]),
                    "keywords": keywords,
                    "score": score,
                    "num_artigos_cluster": len(cluster["artigos"]),
                    "editoria": editoria_dominante,
                    "fonte": "internal_trend_cluster",
                    "artigos_referencia": [
                        {"titulo": a["titulo"], "id": a["id"]}
                        for a in cluster["artigos"][:3]
                    ],
                    "timestamp": datetime.utcnow().isoformat(),
                })

            return signals

        except Exception as e:
            logger.error("InternalTrendMonitor falhou: %s", e)
            return []

    def _find_clusters(
        self,
        sim_matrix: np.ndarray,
        rows: list,
        threshold: float,
    ) -> list[dict]:
        """Clustering simples por similaridade acima do threshold."""
        n = len(rows)
        visited = set()
        clusters = []

        for i in range(n):
            if i in visited:
                continue

            cluster_indices = [i]
            visited.add(i)

            for j in range(i + 1, n):
                if j not in visited and sim_matrix[i, j] >= threshold:
                    cluster_indices.append(j)
                    visited.add(j)

            if len(cluster_indices) >= 2:
                clusters.append({
                    "indices": cluster_indices,
                    "artigos": [rows[idx] for idx in cluster_indices],
                })

        return clusters

    @staticmethod
    def _stopwords_pt() -> list[str]:
        """Stopwords em português para TF-IDF."""
        return [
            "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
            "por", "para", "com", "uma", "um", "que", "se", "ao", "aos",
            "às", "o", "a", "os", "as", "é", "são", "foi", "foram",
            "será", "serão", "ter", "ter", "tem", "têm", "sobre", "após",
            "durante", "entre", "mais", "menos", "muito", "pouco", "já",
            "ainda", "também", "mas", "ou", "e", "nem", "quando", "como",
        ]
```

---

## PARTE IV — DETECÇÃO E CLASSIFICAÇÃO DE PAUTAS

### 4.1 Agregador de Sinais

```python
# brasileira/agents/pauteiro/signal_aggregator.py

import hashlib
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from datasketch import MinHash, MinHashLSH

logger = logging.getLogger("brasileira.pauteiro.aggregator")


class SignalAggregator:
    """
    Agrega e normaliza sinais de todas as fontes externas.

    Responsabilidades:
    1. Normaliza scores para 0-100 por fonte
    2. Cross-correlaciona: mesmo tema em múltiplas fontes = score maior
    3. Deduplicação rápida via MinHash LSH
    4. Classifica urgência: BREAKING / ESPECIAL / NORMAL
    """

    # Boost por confirmação cross-fonte
    CROSS_SOURCE_BOOST = {
        1: 0,    # Só 1 fonte: sem boost
        2: 15,   # 2 fontes: +15 pontos
        3: 30,   # 3 fontes: +30 pontos
        4: 45,   # 4+ fontes: +45 pontos
    }

    # Threshold de urgência
    BREAKING_THRESHOLD = 85
    ESPECIAL_THRESHOLD = 65

    def __init__(self, lsh_threshold: float = 0.5, lsh_num_perm: int = 128):
        self.lsh = MinHashLSH(threshold=lsh_threshold, num_perm=lsh_num_perm)
        self._processed_hashes: dict[str, str] = {}  # hash → keyword

    def aggregate(self, all_signals: list[dict]) -> list[dict]:
        """
        Agrega sinais de múltiplas fontes em candidatos únicos.

        Args:
            all_signals: Lista de sinais brutos de todos os monitores

        Returns:
            Lista de sinais agregados e enriquecidos, ordenados por score
        """
        if not all_signals:
            return []

        # 1. Agrupa sinais similares pelo tema
        theme_groups = self._group_by_theme(all_signals)

        # 2. Para cada grupo, calcula score agregado
        aggregated = []
        for theme_key, signals in theme_groups.items():
            sources = list({s["fonte"] for s in signals})
            num_sources = len(sources)

            # Score base: média dos scores do grupo
            base_score = sum(s["score"] for s in signals) / len(signals)

            # Boost por confirmação cross-fonte
            boost_key = min(num_sources, 4)
            boost = self.CROSS_SOURCE_BOOST.get(boost_key, 45)

            # Score final (capped em 100)
            final_score = min(100, base_score + boost)

            # Determina urgência
            is_breaking = any(s.get("is_breaking") for s in signals)
            if is_breaking or final_score >= self.BREAKING_THRESHOLD:
                urgencia = "BREAKING"
            elif final_score >= self.ESPECIAL_THRESHOLD:
                urgencia = "ESPECIAL"
            else:
                urgencia = "NORMAL"

            # Keyword principal: a de maior score no grupo
            best_signal = max(signals, key=lambda s: s["score"])

            aggregated.append({
                "tema": best_signal["keyword"],
                "score": round(final_score, 1),
                "urgencia": urgencia,
                "num_fontes": num_sources,
                "fontes": sources,
                "sinais_raw": signals,
                "urls_referencia": [
                    s.get("url", "") for s in signals if s.get("url")
                ][:5],
                "resumo_disponivel": best_signal.get("resumo", ""),
                "is_breaking": is_breaking,
                "timestamp": datetime.utcnow().isoformat(),
                "theme_key": theme_key,
            })

        # Ordena por score decrescente
        aggregated.sort(key=lambda x: x["score"], reverse=True)
        return aggregated

    def _group_by_theme(self, signals: list[dict]) -> dict[str, list[dict]]:
        """Agrupa sinais similares usando MinHash LSH."""
        groups: dict[str, list[dict]] = defaultdict(list)
        signal_minhashes = []

        # Cria MinHash para cada sinal
        for signal in signals:
            keyword = signal.get("keyword", "").lower()
            words = set(keyword.split())

            m = MinHash(num_perm=128)
            for word in words:
                m.update(word.encode("utf-8"))

            signal_minhashes.append((signal, m))

        # Agrupa usando LSH
        lsh_temp = MinHashLSH(threshold=0.4, num_perm=128)
        key_map: dict[int, str] = {}

        for idx, (signal, minhash) in enumerate(signal_minhashes):
            key = f"sig_{idx}"
            try:
                result = lsh_temp.query(minhash)
                if result:
                    # Similar a um existente — adiciona ao mesmo grupo
                    group_key = key_map[int(result[0].split("_")[1])]
                else:
                    # Novo grupo
                    group_key = self._make_group_key(signal["keyword"])

                lsh_temp.insert(key, minhash)
                key_map[idx] = group_key
                groups[group_key].append(signal)

            except Exception:
                # Fallback: cria grupo individual
                group_key = self._make_group_key(signal["keyword"])
                groups[group_key].append(signal)

        return dict(groups)

    @staticmethod
    def _make_group_key(keyword: str) -> str:
        """Gera chave de grupo normalizada."""
        normalized = keyword.lower().strip()[:50]
        return hashlib.md5(normalized.encode()).hexdigest()[:12]
```

### 4.2 Filtro de Cobertura (Verificação de Memória)

```python
# brasileira/agents/pauteiro/coverage_filter.py

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

logger = logging.getLogger("brasileira.pauteiro.coverage_filter")


class CoverageFilter:
    """
    Filtra sinais para remover temas já cobertos recentemente.

    Consulta 3 fontes:
    1. pgvector: embedding de temas cobertos (últimas 6h)
    2. Redis: pautas já enviadas neste ciclo
    3. PostgreSQL: artigos publicados sobre o tema (últimas 4h)

    IMPORTANTE: Diferente da V2, este filtro NÃO descarta fontes RSS.
    Filtra apenas pautas EXTERNAS para evitar enviar briefing duplicado
    de algo que o pipeline já está cobrindo.
    """

    # TTL para cache de cobertura no Redis (em segundos)
    COVERAGE_CACHE_TTL = 3600  # 1 hora

    # Similaridade mínima para considerar "já coberto"
    SIMILARITY_THRESHOLD = 0.82

    # Janela de tempo para verificar cobertura recente
    COVERAGE_WINDOW_HOURS = 6

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_client: Any,
        embeddings_client: Any,  # LangChain OpenAI Embeddings
    ):
        self.db_pool = db_pool
        self.redis = redis_client
        self.embeddings_client = embeddings_client

    async def filter_covered(
        self, signals: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """
        Filtra sinais já cobertos.

        Returns:
            Tuple: (sinais_novos, sinais_descartados)
        """
        novos = []
        descartados = []

        for signal in signals:
            tema = signal.get("tema", "")

            # Verificação rápida no Redis primeiro (mais barato)
            if await self._redis_check(tema):
                descartados.append({**signal, "descarte_motivo": "redis_cache"})
                continue

            # Verificação semântica no pgvector
            if await self._semantic_check(tema):
                descartados.append({**signal, "descarte_motivo": "semantica_similar"})
                continue

            # Verificação no banco de artigos publicados
            if await self._db_check(tema):
                descartados.append({**signal, "descarte_motivo": "artigo_publicado"})
                continue

            novos.append(signal)

        logger.info(
            "Coverage filter: %d novos, %d descartados de %d sinais",
            len(novos), len(descartados), len(signals)
        )
        return novos, descartados

    async def _redis_check(self, tema: str) -> bool:
        """Verifica se tema já foi enviado como pauta recentemente."""
        key = f"pauteiro:pauta_enviada:{_normalize_key(tema)}"
        return await self.redis.exists(key) > 0

    async def _semantic_check(self, tema: str) -> bool:
        """Verifica similaridade semântica com temas já cobertos em pgvector."""
        try:
            # Gera embedding do tema
            embedding = await self.embeddings_client.aembed_query(tema)

            async with self.db_pool.acquire() as conn:
                await register_vector(conn)

                # Busca temas similares nas últimas COVERAGE_WINDOW_HOURS
                row = await conn.fetchrow(
                    """
                    SELECT conteudo, 1 - (embedding <=> $1::vector) AS similarity
                    FROM memoria_agentes
                    WHERE agente = 'pauteiro'
                      AND tipo = 'episodica'
                      AND created_at >= NOW() - INTERVAL '%s hours'
                      AND 1 - (embedding <=> $1::vector) >= $2
                    ORDER BY similarity DESC
                    LIMIT 1
                    """ % self.COVERAGE_WINDOW_HOURS,
                    embedding,
                    self.SIMILARITY_THRESHOLD,
                )

                return row is not None

        except Exception as e:
            logger.warning("Semantic check falhou: %s", e)
            return False  # Em caso de erro, NÃO descarta (falha aberta)

    async def _db_check(self, tema: str) -> bool:
        """Verifica se artigos sobre o tema foram publicados recentemente."""
        try:
            # Palavras-chave significativas do tema (sem stopwords)
            palavras = [
                w for w in tema.lower().split()
                if len(w) > 3
            ][:3]

            if not palavras:
                return False

            # Busca no PostgreSQL usando full-text search
            query_parts = " & ".join(palavras)
            async with self.db_pool.acquire() as conn:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM artigos
                    WHERE created_at >= NOW() - INTERVAL '4 hours'
                      AND to_tsvector('portuguese', titulo) @@
                          to_tsquery('portuguese', $1)
                      AND wp_post_id IS NOT NULL
                    """,
                    query_parts,
                )

                return count > 0

        except Exception as e:
            logger.warning("DB check falhou: %s", e)
            return False

    async def mark_as_covered(self, tema: str, pauta_id: str):
        """Marca tema como coberto no Redis para evitar duplicação."""
        key = f"pauteiro:pauta_enviada:{_normalize_key(tema)}"
        await self.redis.setex(key, self.COVERAGE_CACHE_TTL, pauta_id)


def _normalize_key(text: str) -> str:
    """Normaliza texto para uso como Redis key."""
    import re
    normalized = text.lower().strip()
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    normalized = re.sub(r"\s+", "_", normalized)
    return normalized[:50]
```

---

## PARTE V — GERAÇÃO DE BRIEFINGS (LLM PREMIUM)

### 5.1 BriefingGenerator — Classe Principal

```python
# brasileira/agents/pauteiro/briefing_generator.py

import json
import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger("brasileira.pauteiro.briefing")


# Mapeamento de fontes para macrocategorias V3
FONTE_TO_CATEGORIA = {
    "x_twitter_brasil": None,  # Categoria inferida pelo LLM
    "google_trends_realtime": None,
    "google_trends_daily": None,
    "reddit_hot": None,
    "agencia_reuters_brasil": "Mundo/Internacional",
    "agencia_ap_brasil": "Mundo/Internacional",
    "agencia_agência_brasil": "Brasil (geral)",
    "agencia_bbc_brasil": None,
    "internal_trend_cluster": None,  # Usa editoria detectada internamente
}

# 16 macrocategorias V3
MACROCATEGORIAS_V3 = [
    "Política", "Economia", "Esportes", "Tecnologia", "Saúde",
    "Educação", "Ciência", "Cultura/Entretenimento", "Mundo/Internacional",
    "Meio Ambiente", "Segurança/Justiça", "Sociedade", "Brasil (geral)",
    "Regionais", "Opinião/Análise", "Últimas Notícias",
]


SYSTEM_PROMPT_BRIEFING = """Você é o Pauteiro da brasileira.news, agente de inteligência editorial de um portal jornalístico automatizado de alto volume.

Sua função EXCLUSIVA é detectar oportunidades editoriais que as fontes RSS/scrapers não capturam automaticamente — trending topics, discussões virais, eventos em tempo real — e transformá-las em briefings de pauta precisos e acionáveis para os Reporters.

## MANDATO INVIOLÁVEL

1. VOCÊ NÃO FILTRA FONTES. O pipeline de 648+ fontes RSS/scrapers opera independentemente de você.
2. VOCÊ NÃO BLOQUEIA PUBLICAÇÃO. Sua função é adicionar valor, não barrar conteúdo.
3. VOCÊ É PARALELO. Seus briefings chegam ao Reporter como oportunidade adicional, não como pré-requisito.
4. VOCÊ USA LLM PREMIUM apenas para geração de briefings especiais que exigem ângulo editorial criativo.

## QUALIDADE DO BRIEFING

Um bom briefing de pauta deve:
- Ter um ÂNGULO EDITORIAL DIFERENCIADO (não apenas "escreva sobre X")
- Contextualizar por que este tema está em alta AGORA
- Sugerir fontes específicas para o Reporter buscar
- Indicar a urgência real (BREAKING = publicar em 5 min, ESPECIAL = 30 min, NORMAL = até 2h)
- Mapear para UMA das 16 macrocategorias do sistema

## MACROCATEGORIAS DO SISTEMA
{categorias}

## ESTILO EDITORIAL
- Português brasileiro padrão
- Tom objetivo e factual
- Lide: O quê? Quem? Quando? Onde? Por quê? Como?
- Manchetes diretas e informativas
- Foco no leitor brasileiro
- Crédito às fontes OBRIGATÓRIO

## O QUE NÃO FAZER
- NÃO gere ficção editorial — apenas fatos verificáveis
- NÃO sugira pautas de opinião sem base factual
- NÃO priorize sensacionalismo sobre relevância
- NÃO ignore contexto regional brasileiro
""".format(categorias="\n".join(f"- {c}" for c in MACROCATEGORIAS_V3))


PROMPT_BRIEFING_ESPECIAL = """## SINAL DE PAUTA DETECTADO

**Tema em alta:** {tema}
**Score de tendência:** {score}/100
**Urgência inicial:** {urgencia}
**Fontes que confirmam:** {num_fontes} fontes ({fontes})
**URLs de referência:**
{urls}

**Resumo disponível:**
{resumo}

**Dados brutos dos sinais:**
{sinais_contexto}

---

## TAREFA

Gere um briefing de pauta completo para este tema, que será enviado diretamente para um Reporter da brasileira.news publicar.

O Reporter tem acesso a:
1. O briefing que você gerar agora
2. O pipeline normal de 648+ fontes RSS/scrapers (já em andamento)
3. Ferramentas de busca para apurar detalhes

**FORMATO OBRIGATÓRIO — RETORNE APENAS JSON VÁLIDO:**

```json
{{
  "pauta_id": "uuid gerado por você",
  "titulo_sugerido": "Título jornalístico até 80 chars",
  "subtitulo_editorial": "Contexto adicional em até 120 chars",
  "angulo_editorial": "Qual ângulo diferenciado o Reporter deve explorar (2-3 frases)",
  "por_que_agora": "Por que este tema está em alta exatamente AGORA (1-2 frases)",
  "lide_sugerido": "Sugestão de primeiro parágrafo com O quê, Quem, Quando, Onde, Por quê, Como",
  "fontes_sugeridas": [
    "Fonte específica 1 para o Reporter buscar",
    "Fonte específica 2",
    "Fonte específica 3"
  ],
  "palavras_chave_seo": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "categoria": "Uma das 16 macrocategorias exatas do sistema",
  "urgencia": "BREAKING | ESPECIAL | NORMAL",
  "prioridade": "ALTA | MEDIA | BAIXA",
  "estimativa_engajamento": "ALTO | MEDIO | BAIXO",
  "notas_reporter": "Informações adicionais específicas que o Reporter deve saber",
  "urls_referencia": ["url1", "url2"],
  "timestamp_geracao": "ISO8601",
  "agente": "pauteiro-v3"
}}
```
"""


class BriefingGenerator:
    """
    Gera briefings de pauta usando LLM PREMIUM via SmartLLMRouter.

    Implementa Progressive Disclosure:
    - Passo 1: Recebe sinal bruto com título + score
    - Passo 2: Expande contexto (URLs, resumos, sinais brutos)
    - Passo 3: Gera briefing completo com PREMIUM
    """

    def __init__(self, llm_router: Any):
        """
        Args:
            llm_router: Instância do SmartLLMRouter V3
        """
        self.llm_router = llm_router

    async def generate_briefing(self, signal: dict) -> dict | None:
        """
        Gera um briefing completo a partir de um sinal de pauta.

        Args:
            signal: Sinal agregado com tema, score, fontes, etc.

        Returns:
            Briefing completo como dict, ou None se geração falhou
        """
        tema = signal.get("tema", "")
        if not tema:
            return None

        # Prepara contexto de sinais para o prompt
        sinais_raw = signal.get("sinais_raw", [])
        sinais_contexto = json.dumps(
            [
                {
                    "fonte": s.get("fonte"),
                    "score": s.get("score"),
                    "keyword": s.get("keyword"),
                    "resumo": s.get("resumo", "")[:200],
                }
                for s in sinais_raw[:5]  # Máximo 5 sinais brutos no contexto
            ],
            ensure_ascii=False,
            indent=2,
        )

        urls_texto = "\n".join(
            f"- {url}" for url in signal.get("urls_referencia", [])[:5]
            if url
        ) or "- (sem URLs disponíveis)"

        user_prompt = PROMPT_BRIEFING_ESPECIAL.format(
            tema=tema,
            score=signal.get("score", 0),
            urgencia=signal.get("urgencia", "NORMAL"),
            num_fontes=signal.get("num_fontes", 1),
            fontes=", ".join(signal.get("fontes", [])),
            urls=urls_texto,
            resumo=signal.get("resumo_disponivel", "(sem resumo disponível)")[:500],
            sinais_contexto=sinais_contexto,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_BRIEFING},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # PREMIUM obrigatório para geração de briefing
            response_text = await self.llm_router.route_request(
                task_type="pauta_especial",  # → Tier PREMIUM
                messages=messages,
                max_tokens=1500,
                temperature=0.3,  # Mais determinístico para briefings
            )

            if not response_text:
                logger.error("LLM retornou resposta vazia para briefing: %s", tema[:50])
                return None

            # Parse do JSON retornado
            briefing = self._parse_briefing_json(response_text, signal)
            if briefing:
                # Garante pauta_id único
                if not briefing.get("pauta_id"):
                    briefing["pauta_id"] = str(uuid.uuid4())
                briefing["timestamp_geracao"] = datetime.utcnow().isoformat()
                briefing["agente"] = "pauteiro-v3"
                briefing["score_original"] = signal.get("score", 0)
                briefing["num_fontes_confirmaram"] = signal.get("num_fontes", 1)

            return briefing

        except Exception as e:
            logger.error("BriefingGenerator falhou para '%s': %s", tema[:50], e)
            return None

    def _parse_briefing_json(
        self, response_text: str, signal: dict
    ) -> dict | None:
        """Extrai JSON do response do LLM com fallbacks robustos."""
        import re

        # Tenta extrair JSON de dentro de code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Tenta parsear o texto inteiro
            # Encontra o primeiro { e o último }
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start == -1 or end <= start:
                logger.error("Não encontrou JSON no response: %s...", response_text[:100])
                return self._create_fallback_briefing(signal)
            json_str = response_text[start:end]

        try:
            briefing = json.loads(json_str)

            # Validação mínima
            required_fields = ["titulo_sugerido", "categoria", "urgencia"]
            if not all(f in briefing for f in required_fields):
                logger.warning(
                    "Briefing incompleto (faltam campos): %s",
                    [f for f in required_fields if f not in briefing]
                )
                return self._create_fallback_briefing(signal)

            # Valida categoria
            if briefing.get("categoria") not in MACROCATEGORIAS_V3:
                briefing["categoria"] = "Últimas Notícias"

            # Valida urgência
            if briefing.get("urgencia") not in ["BREAKING", "ESPECIAL", "NORMAL"]:
                urgencia_from_signal = signal.get("urgencia", "NORMAL")
                briefing["urgencia"] = urgencia_from_signal

            return briefing

        except json.JSONDecodeError as e:
            logger.error("JSON inválido no response LLM: %s", e)
            return self._create_fallback_briefing(signal)

    def _create_fallback_briefing(self, signal: dict) -> dict:
        """Briefing mínimo quando o parse do LLM falha."""
        tema = signal.get("tema", "Tema não identificado")
        return {
            "pauta_id": str(uuid.uuid4()),
            "titulo_sugerido": tema[:80],
            "subtitulo_editorial": "Tema em alta detectado pelo sistema de inteligência editorial",
            "angulo_editorial": "Cobertura do tema em destaque nos trending topics brasileiros.",
            "por_que_agora": f"Tema apareceu em {signal.get('num_fontes', 1)} fonte(s) de monitoramento simultâneas.",
            "lide_sugerido": f"{tema} está em destaque nos trending topics brasileiros.",
            "fontes_sugeridas": list(signal.get("fontes", [])),
            "palavras_chave_seo": tema.lower().split()[:5],
            "categoria": "Últimas Notícias",
            "urgencia": signal.get("urgencia", "NORMAL"),
            "prioridade": "MEDIA",
            "estimativa_engajamento": "MEDIO",
            "notas_reporter": "Briefing gerado automaticamente — verifique as fontes antes de publicar.",
            "urls_referencia": signal.get("urls_referencia", []),
            "timestamp_geracao": datetime.utcnow().isoformat(),
            "agente": "pauteiro-v3",
            "score_original": signal.get("score", 0),
            "fallback": True,
        }
```

### 5.2 System Prompt para Trending Detection (Tier PADRÃO)

```python
# Usado apenas para análise/classificação inicial de sinais, NÃO para briefings

SYSTEM_PROMPT_TRENDING_ANALYSIS = """Você é um analisador de trending topics para a brasileira.news.

Sua tarefa é rápida e objetiva: dado um conjunto de sinais de tendência (keywords do Google Trends, hashtags do X, posts do Reddit), classifique cada um por:
1. Relevância para o público brasileiro (0-10)
2. Categoria editorial (das 16 macrocategorias)
3. Se é notícia (informacional) ou entretenimento/viral sem valor jornalístico

Seja direto. Não elabore. Retorne apenas JSON.

MACROCATEGORIAS: Política, Economia, Esportes, Tecnologia, Saúde, Educação, Ciência, Cultura/Entretenimento, Mundo/Internacional, Meio Ambiente, Segurança/Justiça, Sociedade, Brasil (geral), Regionais, Opinião/Análise, Últimas Notícias

Descarte temas que são: memes sem valor jornalístico, celebridades sem notícia real, entretenimento puro (reality shows sem polêmica noticiável), spam/bots.
"""
```

---

## PARTE VI — INTEGRAÇÃO KAFKA

### 6.1 Producer Kafka: Tópico `pautas-especiais`

```python
# brasileira/agents/pauteiro/kafka_producer.py

import json
import logging
from datetime import datetime
from typing import Any

from aiokafka import AIOKafkaProducer

logger = logging.getLogger("brasileira.pauteiro.kafka")


class PauteiroKafkaProducer:
    """
    Producer Kafka para o tópico pautas-especiais.

    Tópico: pautas-especiais
    Particionamento: por editoria (categoria da pauta)
    Retenção: 24h (briefings expiram — não faz sentido republlar uma pauta antiga)
    """

    TOPIC = "pautas-especiais"

    # Mapeamento editoria → partition key
    EDITORIA_PARTITION_KEY = {
        "Política": "politica",
        "Economia": "economia",
        "Esportes": "esportes",
        "Tecnologia": "tecnologia",
        "Saúde": "saude",
        "Educação": "educacao",
        "Ciência": "ciencia",
        "Cultura/Entretenimento": "cultura",
        "Mundo/Internacional": "mundo",
        "Meio Ambiente": "meio_ambiente",
        "Segurança/Justiça": "seguranca",
        "Sociedade": "sociedade",
        "Brasil (geral)": "brasil",
        "Regionais": "regionais",
        "Opinião/Análise": "opiniao",
        "Últimas Notícias": "ultimas",
    }

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self):
        """Inicializa o producer Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            # Configs de confiabilidade
            acks="all",           # Aguarda confirmação de todos os ISR
            retries=5,            # Retry em caso de falha transitória
            max_in_flight_requests_per_connection=1,  # Garante ordem
        )
        await self._producer.start()
        logger.info("PauteiroKafkaProducer iniciado: %s", self.TOPIC)

    async def stop(self):
        """Para o producer graciosamente."""
        if self._producer:
            await self._producer.stop()

    async def send_pauta(self, briefing: dict) -> bool:
        """
        Envia um briefing de pauta para o Kafka.

        Args:
            briefing: Briefing completo gerado pelo BriefingGenerator

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        if not self._producer:
            logger.error("Producer não iniciado!")
            return False

        categoria = briefing.get("categoria", "Últimas Notícias")
        partition_key = self.EDITORIA_PARTITION_KEY.get(categoria, "ultimas")

        # Envelope Kafka padronizado
        message = {
            "schema_version": "3.0",
            "tipo": "pauta_especial",
            "pauta_id": briefing.get("pauta_id"),
            "titulo": briefing.get("titulo_sugerido"),
            "categoria": categoria,
            "urgencia": briefing.get("urgencia", "NORMAL"),
            "prioridade": briefing.get("prioridade", "MEDIA"),
            "briefing": briefing,
            "publisher_id": f"pauteiro-v3",
            "timestamp": datetime.utcnow().isoformat(),
            "expires_at": self._calculate_expiry(briefing.get("urgencia", "NORMAL")),
        }

        try:
            await self._producer.send_and_wait(
                self.TOPIC,
                value=message,
                key=partition_key,
            )
            logger.info(
                "Pauta enviada: [%s] %s (urgência: %s)",
                categoria,
                briefing.get("titulo_sugerido", "")[:60],
                briefing.get("urgencia"),
            )
            return True

        except Exception as e:
            logger.error(
                "Falha ao enviar pauta '%s' para Kafka: %s",
                briefing.get("titulo_sugerido", "")[:40],
                e
            )
            return False

    @staticmethod
    def _calculate_expiry(urgencia: str) -> str:
        """Calcula timestamp de expiração baseado na urgência."""
        from datetime import timedelta
        expiry_map = {
            "BREAKING": timedelta(minutes=30),
            "ESPECIAL": timedelta(hours=2),
            "NORMAL": timedelta(hours=6),
        }
        delta = expiry_map.get(urgencia, timedelta(hours=4))
        return (datetime.utcnow() + delta).isoformat()
```

### 6.2 Consumer no Reporter: Como o Reporter Consome pautas-especiais

```python
# REFERÊNCIA — Como o Reporter deve consumir pautas-especiais
# Este código vai no briefing do Reporter, não no Pauteiro
# Incluído aqui apenas para documentar a integração

# O Reporter já tem seu próprio consumer de classified-articles (pipeline principal)
# Este é um CONSUMER ADICIONAL para pautas-especiais

class PautasEspeciaisConsumer:
    """
    Consumer secundário do Reporter para pautas-especiais.

    IMPORTANTE: Este consumer é COMPLEMENTAR ao pipeline principal.
    O Reporter continua processando classified-articles normalmente.
    As pautas especiais chegam como oportunidades adicionais.
    """

    async def consume_pautas_especiais(self):
        """Loop de consumo de pautas especiais do Pauteiro."""
        consumer = AIOKafkaConsumer(
            "pautas-especiais",
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id="reporters-pautas-especiais",
            auto_offset_reset="latest",  # Só pautas novas (não reprocesa antigas)
            enable_auto_commit=True,
            consumer_timeout_ms=5000,
        )
        await consumer.start()

        async for msg in consumer:
            try:
                data = json.loads(msg.value)

                # Verifica expiração
                expires_at = data.get("expires_at")
                if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
                    logger.info("Pauta expirada ignorada: %s", data.get("pauta_id"))
                    continue

                briefing = data.get("briefing", {})
                urgencia = briefing.get("urgencia", "NORMAL")

                # BREAKING: prioriza imediatamente
                if urgencia == "BREAKING":
                    await self.handle_breaking_pauta(briefing)
                else:
                    # Enfileira na fila normal do Reporter
                    await self.queue_pauta_for_reporter(briefing)

            except Exception as e:
                logger.error("Erro ao processar pauta especial: %s", e)
```

---

## PARTE VII — MEMÓRIA DO PAUTEIRO

### 7.1 Arquitetura de Memória

O Pauteiro V3 implementa **três tipos de memória real** — não apenas hooks vazios como na V2.

| Tipo | O Que Armazena | Storage | TTL |
|------|----------------|---------|-----|
| **Semântica** | Padrões editoriais aprendidos: quais temas têm alto engajamento por categoria, quais fontes externas são mais confiáveis | pgvector | Permanente |
| **Episódica** | Histórico de pautas enviadas: tema, briefing, categoria, urgência, timestamp | pgvector | 90 dias |
| **Working** | Estado do ciclo atual: sinais coletados, pautas enviadas, scores de monitores | Redis | 4h |

### 7.2 Scratchpad Redis por Ciclo

```python
# brasileira/agents/pauteiro/memory.py

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg
import numpy as np

logger = logging.getLogger("brasileira.pauteiro.memory")

# Redis key format
WORKING_MEMORY_KEY = "agent:working_memory:pauteiro:{cycle_id}"
SCRATCHPAD_KEY = "pauteiro:radar_fontes:{cycle_id}"


class PauteiroMemory:
    """
    Implementação real de memória para o Pauteiro V3.

    Diferente da V2 (hooks vazios), esta implementação efetivamente:
    - Salva embeddings de pautas geradas
    - Persiste histórico episódico em pgvector
    - Mantém working memory no Redis durante o ciclo
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_client: Any,
        embeddings_client: Any,
    ):
        self.db_pool = db_pool
        self.redis = redis_client
        self.embeddings_client = embeddings_client

    # ── Working Memory (Redis) ─────────────────────────────────────────────

    async def save_working_state(self, cycle_id: str, state: dict):
        """Salva estado do ciclo atual no Redis."""
        key = WORKING_MEMORY_KEY.format(cycle_id=cycle_id)
        await self.redis.setex(
            key,
            14400,  # 4h TTL
            json.dumps(state, ensure_ascii=False, default=str),
        )

    async def load_working_state(self, cycle_id: str) -> dict:
        """Carrega estado do ciclo atual do Redis."""
        key = WORKING_MEMORY_KEY.format(cycle_id=cycle_id)
        data = await self.redis.get(key)
        return json.loads(data) if data else {}

    async def save_scratchpad(self, cycle_id: str, radar_data: dict):
        """
        Salva scratchpad do ciclo: radar_fontes_{ciclo}.json

        Conteúdo: fontes processadas, scores de relevância, sinais detectados
        """
        key = SCRATCHPAD_KEY.format(cycle_id=cycle_id)
        await self.redis.setex(
            key,
            14400,  # 4h
            json.dumps(radar_data, ensure_ascii=False, default=str),
        )

    # ── Memória Episódica (pgvector) ───────────────────────────────────────

    async def save_pauta_episodica(self, briefing: dict):
        """
        Salva pauta gerada na memória episódica (pgvector).

        Permite que ciclos futuros detectem duplicação semântica.
        """
        tema = briefing.get("titulo_sugerido", "")
        if not tema:
            return

        try:
            embedding = await self.embeddings_client.aembed_query(tema)

            conteudo = {
                "pauta_id": briefing.get("pauta_id"),
                "titulo": briefing.get("titulo_sugerido"),
                "categoria": briefing.get("categoria"),
                "urgencia": briefing.get("urgencia"),
                "score_original": briefing.get("score_original", 0),
                "timestamp": datetime.utcnow().isoformat(),
            }

            async with self.db_pool.acquire() as conn:
                from pgvector.asyncpg import register_vector
                await register_vector(conn)

                await conn.execute(
                    """
                    INSERT INTO memoria_agentes
                        (agente, tipo, conteudo, embedding, created_at)
                    VALUES
                        ('pauteiro', 'episodica', $1::jsonb, $2::vector, NOW())
                    """,
                    json.dumps(conteudo),
                    embedding,
                )

            logger.debug("Pauta salva na memória episódica: %s", tema[:50])

        except Exception as e:
            logger.error("Falha ao salvar memória episódica: %s", e)

    # ── Memória Semântica (pgvector) ───────────────────────────────────────

    async def save_fonte_reliability(
        self,
        fonte: str,
        score_medio: float,
        pautas_geradas: int,
    ):
        """
        Salva aprendizado sobre confiabilidade de fontes externas.

        Permite ao Pauteiro aprender quais fontes externas geram
        pautas de maior qualidade ao longo do tempo.
        """
        conteudo = {
            "fonte": fonte,
            "score_medio": score_medio,
            "pautas_geradas": pautas_geradas,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Para memória semântica de fonte, o embedding é do nome da fonte
        # (simplificado — em produção usaria embedding mais rico)
        try:
            embedding = await self.embeddings_client.aembed_query(
                f"fonte externa {fonte} confiabilidade editorial"
            )

            async with self.db_pool.acquire() as conn:
                from pgvector.asyncpg import register_vector
                await register_vector(conn)

                # Upsert: atualiza se já existe, insere se não
                await conn.execute(
                    """
                    INSERT INTO memoria_agentes
                        (agente, tipo, conteudo, embedding, created_at)
                    VALUES
                        ('pauteiro', 'semantica', $1::jsonb, $2::vector, NOW())
                    ON CONFLICT (agente, tipo, (conteudo->>'fonte'))
                    DO UPDATE SET
                        conteudo = EXCLUDED.conteudo,
                        embedding = EXCLUDED.embedding,
                        created_at = NOW()
                    """,
                    json.dumps(conteudo),
                    embedding,
                )

        except Exception as e:
            logger.debug("Falha ao salvar memória semântica de fonte: %s", e)

    async def get_fonte_stats(self, fonte: str) -> dict:
        """Recupera estatísticas históricas de uma fonte."""
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT conteudo
                    FROM memoria_agentes
                    WHERE agente = 'pauteiro'
                      AND tipo = 'semantica'
                      AND conteudo->>'fonte' = $1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    fonte,
                )
                if row:
                    return json.loads(row["conteudo"])
        except Exception:
            pass
        return {}
```

---

## PARTE VIII — GRAFO LANGGRAPH DO PAUTEIRO V3

### 8.1 PauteiroState e PauteiroAgent

```python
# brasileira/agents/pauteiro.py
# ARQUIVO PRINCIPAL — Entry point do agente (como serviço, não como pipeline step)

"""
Pauteiro V3 — Agente de Inteligência Editorial

MANDATO: Agente PARALELO. NÃO é entry point do pipeline.
NÃO filtra fontes. NÃO bloqueia publicação.

Monitora fontes externas (Google Trends, X, Reddit, Agências)
e gera briefings de pauta via Kafka pautas-especiais.

Ciclo de execução: loop contínuo com 5 monitores assíncronos paralelos.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

logger = logging.getLogger("brasileira.pauteiro")


# ── Estado do Agente ────────────────────────────────────────────────────────

class PauteiroState(BaseModel):
    """Estado do Pauteiro V3 para o grafo LangGraph."""

    model_config = {"arbitrary_types_allowed": True}

    # Identidade
    cycle_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_id: str = "pauteiro-v3"
    timestamp_inicio: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    # Sinais coletados por cada monitor
    sinais_google_trends: list[dict] = Field(default_factory=list)
    sinais_x_twitter: list[dict] = Field(default_factory=list)
    sinais_reddit: list[dict] = Field(default_factory=list)
    sinais_agencias: list[dict] = Field(default_factory=list)
    sinais_internos: list[dict] = Field(default_factory=list)

    # Após agregação
    sinais_agregados: list[dict] = Field(default_factory=list)

    # Após filtro de cobertura
    sinais_novos: list[dict] = Field(default_factory=list)
    sinais_descartados: list[dict] = Field(default_factory=list)

    # Briefings gerados
    briefings_gerados: list[dict] = Field(default_factory=list)
    briefings_enviados: int = 0
    briefings_falhos: int = 0

    # Erros
    errors: list[dict] = Field(default_factory=list)

    # Métricas do ciclo
    duracao_coleta_s: float = 0.0
    duracao_geracao_s: float = 0.0
    total_sinais_brutos: int = 0


# ── Agente Principal ─────────────────────────────────────────────────────────

class PauteiroAgent:
    """
    Pauteiro V3 — Agente de Inteligência Editorial.

    Arquitetura: 5 monitores externos paralelos + agregador + gerador PREMIUM.
    Saída: Kafka pautas-especiais (nunca bloqueia pipeline principal).
    """

    def __init__(
        self,
        # Dependências de monitoramento
        google_trends_monitor: Any,
        x_trends_monitor: Any,
        reddit_monitor: Any,
        agencias_monitor: Any,
        internal_trend_monitor: Any,
        # Processamento
        signal_aggregator: Any,
        coverage_filter: Any,
        briefing_generator: Any,
        # Infraestrutura
        kafka_producer: Any,
        memory: Any,
        circuit_breaker: Any,
        # Configuração
        max_briefings_per_cycle: int = 10,
        min_score_for_briefing: float = 55.0,
    ):
        self.google_trends = google_trends_monitor
        self.x_trends = x_trends_monitor
        self.reddit = reddit_monitor
        self.agencias = agencias_monitor
        self.internal = internal_trend_monitor
        self.aggregator = signal_aggregator
        self.coverage_filter = coverage_filter
        self.briefing_gen = briefing_generator
        self.kafka = kafka_producer
        self.memory = memory
        self.circuit_breaker = circuit_breaker
        self.max_briefings = max_briefings_per_cycle
        self.min_score = min_score_for_briefing

        self._graph = self._build_graph()
        self._stop = asyncio.Event()

    def _build_graph(self) -> StateGraph:
        """Constrói o grafo LangGraph do Pauteiro."""
        graph = StateGraph(PauteiroState)

        # Nós do grafo
        graph.add_node("coletar_sinais", self._step_coletar_sinais)
        graph.add_node("agregar_sinais", self._step_agregar_sinais)
        graph.add_node("filtrar_cobertura", self._step_filtrar_cobertura)
        graph.add_node("gerar_briefings", self._step_gerar_briefings)
        graph.add_node("publicar_kafka", self._step_publicar_kafka)
        graph.add_node("salvar_memoria", self._step_salvar_memoria)
        graph.add_node("aguardar_proximo_ciclo", self._step_aguardar)

        # Fluxo do grafo
        graph.set_entry_point("coletar_sinais")
        graph.add_edge("coletar_sinais", "agregar_sinais")
        graph.add_edge("agregar_sinais", "filtrar_cobertura")
        graph.add_conditional_edges(
            "filtrar_cobertura",
            self._deve_gerar_briefings,
            {
                True: "gerar_briefings",
                False: "aguardar_proximo_ciclo",
            },
        )
        graph.add_edge("gerar_briefings", "publicar_kafka")
        graph.add_edge("publicar_kafka", "salvar_memoria")
        graph.add_edge("salvar_memoria", "aguardar_proximo_ciclo")
        graph.add_conditional_edges(
            "aguardar_proximo_ciclo",
            self._deve_continuar,
            {
                True: "coletar_sinais",
                False: END,
            },
        )

        return graph.compile()

    # ── Steps do Grafo ───────────────────────────────────────────────────────

    async def _step_coletar_sinais(self, state: PauteiroState) -> dict:
        """
        Coleta sinais de todos os 5 monitores em paralelo.

        Implementa Progressive Disclosure: coleta apenas título + score
        neste passo. O contexto expandido é carregado apenas para os
        candidatos selecionados na etapa de geração.
        """
        logger.info("[Ciclo %s] Coletando sinais externos...", state.cycle_id)
        inicio = datetime.utcnow()

        # Executa todos os monitores em paralelo (independentes entre si)
        results = await asyncio.gather(
            self.google_trends.get_realtime_trends(),
            self.x_trends.get_trends(),
            self.reddit.get_hot_topics(),
            self.agencias.get_breaking_signals(),
            self.internal.get_internal_trends(),
            return_exceptions=True,
        )

        duracao = (datetime.utcnow() - inicio).total_seconds()

        # Desempacota resultados (exceptions viram listas vazias)
        sinais_gt = results[0] if not isinstance(results[0], Exception) else []
        sinais_x  = results[1] if not isinstance(results[1], Exception) else []
        sinais_rd = results[2] if not isinstance(results[2], Exception) else []
        sinais_ag = results[3] if not isinstance(results[3], Exception) else []
        sinais_in = results[4] if not isinstance(results[4], Exception) else []

        total = sum(len(s) for s in [sinais_gt, sinais_x, sinais_rd, sinais_ag, sinais_in])
        logger.info(
            "[Ciclo %s] Sinais coletados: GT=%d X=%d Reddit=%d Agências=%d Interno=%d (total=%d, %.1fs)",
            state.cycle_id, len(sinais_gt), len(sinais_x), len(sinais_rd),
            len(sinais_ag), len(sinais_in), total, duracao,
        )

        return {
            "sinais_google_trends": sinais_gt,
            "sinais_x_twitter": sinais_x,
            "sinais_reddit": sinais_rd,
            "sinais_agencias": sinais_ag,
            "sinais_internos": sinais_in,
            "total_sinais_brutos": total,
            "duracao_coleta_s": duracao,
        }

    async def _step_agregar_sinais(self, state: PauteiroState) -> dict:
        """Agrega e normaliza sinais de todas as fontes."""
        logger.info("[Ciclo %s] Agregando %d sinais brutos...", state.cycle_id, state.total_sinais_brutos)

        all_signals = (
            state.sinais_google_trends
            + state.sinais_x_twitter
            + state.sinais_reddit
            + state.sinais_agencias
            + state.sinais_internos
        )

        if not all_signals:
            return {"sinais_agregados": []}

        agregados = self.aggregator.aggregate(all_signals)

        # Filtra por score mínimo
        agregados_filtrados = [
            s for s in agregados
            if s.get("score", 0) >= self.min_score
        ]

        logger.info(
            "[Ciclo %s] Agregação: %d candidatos (score >= %.0f) de %d clusters",
            state.cycle_id,
            len(agregados_filtrados),
            self.min_score,
            len(agregados),
        )

        return {"sinais_agregados": agregados_filtrados}

    async def _step_filtrar_cobertura(self, state: PauteiroState) -> dict:
        """Filtra sinais já cobertos pelo pipeline principal ou por ciclos anteriores."""
        if not state.sinais_agregados:
            return {"sinais_novos": [], "sinais_descartados": []}

        novos, descartados = await self.coverage_filter.filter_covered(
            state.sinais_agregados
        )

        logger.info(
            "[Ciclo %s] Filtro de cobertura: %d novos, %d descartados",
            state.cycle_id, len(novos), len(descartados),
        )

        return {
            "sinais_novos": novos,
            "sinais_descartados": descartados,
        }

    async def _step_gerar_briefings(self, state: PauteiroState) -> dict:
        """
        Gera briefings usando LLM PREMIUM para cada sinal novo.

        Limita ao MAX_BRIEFINGS_PER_CYCLE mais relevantes.
        Usa Progressive Disclosure: carrega contexto completo só para top N.
        """
        candidatos = state.sinais_novos[:self.max_briefings]
        logger.info(
            "[Ciclo %s] Gerando briefings PREMIUM para %d candidatos...",
            state.cycle_id, len(candidatos),
        )

        inicio = datetime.utcnow()
        briefings = []
        falhos = 0

        # BREAKING: processa imediatamente, em sequência para prioridade
        breakings = [s for s in candidatos if s.get("urgencia") == "BREAKING"]
        normais   = [s for s in candidatos if s.get("urgencia") != "BREAKING"]

        # Breaking em paralelo (urgência máxima)
        if breakings:
            tasks = [self.briefing_gen.generate_briefing(s) for s in breakings]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict):
                    briefings.append(r)
                else:
                    falhos += 1

        # Normais: até MAX_BRIEFINGS - len(breakings)
        slots_restantes = self.max_briefings - len(briefings)
        for sinal in normais[:slots_restantes]:
            try:
                briefing = await self.briefing_gen.generate_briefing(sinal)
                if briefing:
                    briefings.append(briefing)
                else:
                    falhos += 1
                # Pequeno delay para não saturar LLM
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("Falha ao gerar briefing: %s", e)
                falhos += 1

        duracao = (datetime.utcnow() - inicio).total_seconds()
        logger.info(
            "[Ciclo %s] Briefings gerados: %d OK, %d falhos (%.1fs)",
            state.cycle_id, len(briefings), falhos, duracao,
        )

        return {
            "briefings_gerados": briefings,
            "briefings_falhos": falhos,
            "duracao_geracao_s": duracao,
        }

    async def _step_publicar_kafka(self, state: PauteiroState) -> dict:
        """Publica briefings no Kafka pautas-especiais."""
        enviados = 0

        for briefing in state.briefings_gerados:
            try:
                success = await self.kafka.send_pauta(briefing)
                if success:
                    enviados += 1
                    # Marca como coberto no Redis (evita duplicação futura)
                    await self.coverage_filter.mark_as_covered(
                        briefing.get("titulo_sugerido", ""),
                        briefing.get("pauta_id", ""),
                    )
            except Exception as e:
                logger.error("Falha ao publicar pauta no Kafka: %s", e)

        logger.info(
            "[Ciclo %s] Kafka: %d/%d briefings publicados em pautas-especiais",
            state.cycle_id, enviados, len(state.briefings_gerados),
        )

        return {"briefings_enviados": enviados}

    async def _step_salvar_memoria(self, state: PauteiroState) -> dict:
        """Salva estado do ciclo na memória episódica e working."""
        try:
            # Salva cada briefing na memória episódica (pgvector)
            for briefing in state.briefings_gerados:
                await self.memory.save_pauta_episodica(briefing)

            # Salva scratchpad do ciclo no Redis
            radar_data = {
                "cycle_id": state.cycle_id,
                "timestamp": state.timestamp_inicio,
                "total_sinais_brutos": state.total_sinais_brutos,
                "sinais_agregados": len(state.sinais_agregados),
                "sinais_novos": len(state.sinais_novos),
                "briefings_gerados": len(state.briefings_gerados),
                "briefings_enviados": state.briefings_enviados,
                "duracao_coleta_s": state.duracao_coleta_s,
                "duracao_geracao_s": state.duracao_geracao_s,
                # Fontes com score médio neste ciclo
                "scores_por_fonte": self._calc_source_scores(state),
            }

            await self.memory.save_scratchpad(state.cycle_id, radar_data)
            await self.memory.save_working_state(state.cycle_id, radar_data)

        except Exception as e:
            logger.error("Falha ao salvar memória do ciclo: %s", e)

        return {}

    async def _step_aguardar(self, state: PauteiroState) -> dict:
        """
        Aguarda até o próximo ciclo (mínimo 10 minutos).

        O ciclo é determinado pelo monitor mais frequente (Agências: 10 min).
        """
        WAIT_SECONDS = 600  # 10 minutos
        logger.info(
            "[Ciclo %s] Ciclo completo. Aguardando %ds até próximo ciclo...",
            state.cycle_id, WAIT_SECONDS,
        )

        try:
            await asyncio.wait_for(
                self._stop.wait(),
                timeout=WAIT_SECONDS,
            )
        except asyncio.TimeoutError:
            pass  # Timeout normal — próximo ciclo

        return {
            "cycle_id": str(uuid.uuid4())[:8],
            "timestamp_inicio": datetime.utcnow().isoformat(),
            # Reset dos sinais para o próximo ciclo
            "sinais_google_trends": [],
            "sinais_x_twitter": [],
            "sinais_reddit": [],
            "sinais_agencias": [],
            "sinais_internos": [],
            "sinais_agregados": [],
            "sinais_novos": [],
            "sinais_descartados": [],
            "briefings_gerados": [],
            "briefings_enviados": 0,
            "briefings_falhos": 0,
            "total_sinais_brutos": 0,
        }

    # ── Conditional Edges ───────────────────────────────────────────────────

    def _deve_gerar_briefings(self, state: PauteiroState) -> bool:
        """Verifica se há sinais novos suficientes para gerar briefings."""
        return len(state.sinais_novos) > 0

    def _deve_continuar(self, state: PauteiroState) -> bool:
        """Verifica se o agente deve continuar rodando."""
        return not self._stop.is_set()

    # ── Utilitários ────────────────────────────────────────────────────────

    def _calc_source_scores(self, state: PauteiroState) -> dict:
        """Calcula score médio de cada fonte no ciclo."""
        fonte_scores: dict[str, list[float]] = {}
        all_signals = (
            state.sinais_google_trends + state.sinais_x_twitter
            + state.sinais_reddit + state.sinais_agencias + state.sinais_internos
        )
        for s in all_signals:
            fonte = s.get("fonte", "unknown")
            score = s.get("score", 0)
            fonte_scores.setdefault(fonte, []).append(score)

        return {
            fonte: round(sum(scores) / len(scores), 1)
            for fonte, scores in fonte_scores.items()
        }

    async def run_continuous(self):
        """Roda o Pauteiro continuamente como serviço paralelo."""
        logger.info("Pauteiro V3 iniciado — modo contínuo PARALELO")
        state = PauteiroState()

        while not self._stop.is_set():
            try:
                state = await self._graph.ainvoke(state)
            except Exception as e:
                logger.error("Erro crítico no ciclo do Pauteiro: %s", e, exc_info=True)
                await asyncio.sleep(60)  # Backoff de 1 min em erro crítico

    async def stop(self):
        """Para o agente graciosamente."""
        self._stop.set()
        logger.info("Pauteiro V3: parada solicitada")
```

---

## PARTE IX — SCHEMAS DE DADOS

### 9.1 Schema do Sinal Bruto (de qualquer monitor)

```python
# brasileira/agents/pauteiro/schemas.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class RawSignal(BaseModel):
    """Sinal bruto de um monitor externo."""

    keyword: str = Field(..., description="Keyword ou título do trending topic")
    score: float = Field(..., ge=0, le=100, description="Score de tendência 0-100")
    fonte: str = Field(..., description="Identificador da fonte: google_trends_realtime | x_twitter_brasil | reddit_hot | etc.")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    geo: str = Field(default="BR")

    # Campos opcionais (nem todos os monitores preenchem todos)
    url: Optional[str] = None
    resumo: Optional[str] = None
    is_breaking: bool = False
    is_hashtag: bool = False
    tweet_volume: Optional[int] = None
    upvotes: Optional[int] = None
    subreddit: Optional[str] = None
    agencia: Optional[str] = None
    idioma: str = "pt-BR"
    artigos_relacionados: list[str] = Field(default_factory=list)
    categoria_raw: list[str] = Field(default_factory=list)


class AggregatedSignal(BaseModel):
    """Sinal agregado após cross-correlação de fontes."""

    tema: str
    score: float = Field(..., ge=0, le=100)
    urgencia: str = Field(..., pattern="^(BREAKING|ESPECIAL|NORMAL)$")
    num_fontes: int = Field(..., ge=1)
    fontes: list[str]
    sinais_raw: list[dict]
    urls_referencia: list[str] = Field(default_factory=list)
    resumo_disponivel: str = ""
    is_breaking: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    theme_key: str = ""


class PautaEspecialKafka(BaseModel):
    """Envelope do briefing publicado no Kafka pautas-especiais."""

    schema_version: str = "3.0"
    tipo: str = "pauta_especial"
    pauta_id: str
    titulo: str
    categoria: str
    urgencia: str = Field(..., pattern="^(BREAKING|ESPECIAL|NORMAL)$")
    prioridade: str = Field(..., pattern="^(ALTA|MEDIA|BAIXA)$")
    briefing: dict
    publisher_id: str = "pauteiro-v3"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: str


class BriefingCompleto(BaseModel):
    """Briefing de pauta completo gerado pelo LLM PREMIUM."""

    pauta_id: str
    titulo_sugerido: str = Field(..., max_length=80)
    subtitulo_editorial: str = Field(default="", max_length=120)
    angulo_editorial: str
    por_que_agora: str
    lide_sugerido: str
    fontes_sugeridas: list[str] = Field(default_factory=list)
    palavras_chave_seo: list[str] = Field(default_factory=list)
    categoria: str
    urgencia: str = Field(..., pattern="^(BREAKING|ESPECIAL|NORMAL)$")
    prioridade: str = Field(..., pattern="^(ALTA|MEDIA|BAIXA)$")
    estimativa_engajamento: str = Field(..., pattern="^(ALTO|MEDIO|BAIXO)$")
    notas_reporter: str = ""
    urls_referencia: list[str] = Field(default_factory=list)
    timestamp_geracao: str
    agente: str = "pauteiro-v3"
    score_original: float = 0.0
    num_fontes_confirmaram: int = 1
    fallback: bool = False
```

### 9.2 Schema Kafka: `pautas-especiais`

```json
{
  "schema_version": "3.0",
  "tipo": "pauta_especial",
  "pauta_id": "uuid-v4",
  "titulo": "Título da pauta para o Reporter",
  "categoria": "Política",
  "urgencia": "ESPECIAL",
  "prioridade": "ALTA",
  "publisher_id": "pauteiro-v3",
  "timestamp": "2026-03-26T14:30:00Z",
  "expires_at": "2026-03-26T16:30:00Z",
  "briefing": {
    "pauta_id": "uuid-v4",
    "titulo_sugerido": "Congresso aprova medida que muda regras tributárias",
    "subtitulo_editorial": "Votação ocorreu em sessão extraordinária nesta tarde",
    "angulo_editorial": "Explore o impacto prático para contribuintes de renda média, com comparativo de alíquotas antes e depois",
    "por_que_agora": "Votação ocorreu há 40 minutos e está trending no Google Brasil com score 94/100",
    "lide_sugerido": "O Congresso Nacional aprovou nesta tarde...",
    "fontes_sugeridas": [
      "Agência Câmara (fonte oficial da votação)",
      "Receita Federal (impacto tributário)",
      "IBRE/FGV (análise econômica)"
    ],
    "palavras_chave_seo": ["reforma tributária", "imposto renda", "congresso", "votação"],
    "categoria": "Política",
    "urgencia": "ESPECIAL",
    "prioridade": "ALTA",
    "estimativa_engajamento": "ALTO",
    "notas_reporter": "Verificar placar de votos e partidos favoráveis/contrários",
    "urls_referencia": ["https://camara.leg.br/...", "https://senado.leg.br/..."],
    "timestamp_geracao": "2026-03-26T14:30:00Z",
    "agente": "pauteiro-v3",
    "score_original": 94.0,
    "num_fontes_confirmaram": 4
  }
}
```

---

## PARTE X — CIRCUIT BREAKER POR FONTE EXTERNA

### 10.1 Implementação do Circuit Breaker Multi-Fonte

```python
# brasileira/agents/pauteiro/circuit_breaker.py

import logging
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

logger = logging.getLogger("brasileira.pauteiro.circuit_breaker")


@dataclass
class SourceCircuitBreaker:
    """
    Circuit breaker para uma fonte externa específica.

    Estados:
    - CLOSED: operação normal
    - OPEN: fonte com falhas — skip por COOLDOWN_SECONDS
    - HALF_OPEN: tentativa após cooldown

    Threshold: 30% de falha em janela de 10 chamadas
    """

    FAILURE_THRESHOLD = 0.30    # 30% de falhas abre o circuit
    WINDOW_SIZE = 10             # Janela de 10 chamadas para calcular taxa
    COOLDOWN_SECONDS = 300       # 5 min de cooldown quando aberto

    source_id: str
    _calls: deque = field(default_factory=lambda: deque(maxlen=10), init=False)
    _opened_at: Optional[float] = field(default=None, init=False)
    _state: str = field(default="CLOSED", init=False)

    def should_allow(self, source_id: str = None) -> bool:
        """Verifica se a fonte deve ser consultada."""
        if self._state == "CLOSED":
            return True

        if self._state == "OPEN":
            if time.time() - self._opened_at > self.COOLDOWN_SECONDS:
                self._state = "HALF_OPEN"
                logger.info("Circuit %s: HALF_OPEN (tentando recuperação)", self.source_id)
                return True
            return False

        # HALF_OPEN: permite uma tentativa
        return True

    def record_success(self, source_id: str = None):
        """Registra chamada bem-sucedida."""
        self._calls.append(True)
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            self._opened_at = None
            logger.info("Circuit %s: recuperado → CLOSED", self.source_id)

    def record_failure(self, source_id: str = None):
        """Registra falha e verifica se deve abrir o circuit."""
        self._calls.append(False)

        if self._state == "HALF_OPEN":
            self._state = "OPEN"
            self._opened_at = time.time()
            logger.warning("Circuit %s: HALF_OPEN falhou → OPEN", self.source_id)
            return

        # Calcula taxa de falha na janela
        if len(self._calls) >= 3:  # Mínimo 3 chamadas para avaliar
            failure_rate = self._calls.count(False) / len(self._calls)
            if failure_rate >= self.FAILURE_THRESHOLD:
                self._state = "OPEN"
                self._opened_at = time.time()
                logger.warning(
                    "Circuit %s ABERTO: %.0f%% de falhas na janela de %d chamadas",
                    self.source_id,
                    failure_rate * 100,
                    len(self._calls),
                )

    @property
    def state(self) -> str:
        return self._state

    @property
    def failure_rate(self) -> float:
        if not self._calls:
            return 0.0
        return self._calls.count(False) / len(self._calls)


class MultiSourceCircuitBreaker:
    """Circuit breaker para múltiplas fontes externas do Pauteiro."""

    SOURCES = [
        "google_trends",
        "x_twitter",
        "reddit",
        "agencias",
        "internal",
    ]

    def __init__(self):
        self._breakers = {
            source: SourceCircuitBreaker(source_id=source)
            for source in self.SOURCES
        }

    def should_allow(self, source_id: str) -> bool:
        breaker = self._breakers.get(source_id)
        return breaker.should_allow() if breaker else True

    def record_success(self, source_id: str):
        breaker = self._breakers.get(source_id)
        if breaker:
            breaker.record_success()

    def record_failure(self, source_id: str):
        breaker = self._breakers.get(source_id)
        if breaker:
            breaker.record_failure()

    def get_status(self) -> dict:
        """Retorna status de todos os circuits (para observabilidade)."""
        return {
            source: {
                "state": b.state,
                "failure_rate": round(b.failure_rate * 100, 1),
            }
            for source, b in self._breakers.items()
        }
```

---

## PARTE XI — DIRETÓRIOS E ESTRUTURA DE ARQUIVOS

### 11.1 Estrutura Completa do Componente

```
brasileira/
├── agents/
│   ├── pauteiro.py                          # Agente principal (este arquivo)
│   └── pauteiro/                            # Módulos auxiliares
│       ├── __init__.py
│       ├── monitors/
│       │   ├── __init__.py
│       │   ├── google_trends.py             # Monitor Google Trends
│       │   ├── x_trends.py                  # Monitor X/Twitter
│       │   ├── reddit_monitor.py            # Monitor Reddit
│       │   ├── agencias_monitor.py          # Monitor Agências (RSS)
│       │   └── internal_trends.py           # Monitor tendências internas
│       ├── signal_aggregator.py             # Agregação + deduplicação (MinHash)
│       ├── coverage_filter.py               # Filtro de cobertura (pgvector + Redis)
│       ├── briefing_generator.py            # Geração LLM PREMIUM
│       ├── kafka_producer.py                # Producer Kafka pautas-especiais
│       ├── circuit_breaker.py               # Circuit breaker multi-fonte
│       ├── memory.py                        # Memória: semântica + episódica + working
│       └── schemas.py                       # Pydantic schemas
│
├── llm/
│   └── smart_router.py                      # SmartLLMRouter V3 (Componente #1)
│
tests/
└── test_pauteiro/
    ├── __init__.py
    ├── test_google_trends_monitor.py
    ├── test_x_trends_monitor.py
    ├── test_reddit_monitor.py
    ├── test_agencias_monitor.py
    ├── test_signal_aggregator.py
    ├── test_coverage_filter.py
    ├── test_briefing_generator.py
    ├── test_kafka_producer.py
    ├── test_circuit_breaker.py
    ├── test_memory.py
    └── test_pauteiro_integration.py
```

### 11.2 Configuração (.env)

```bash
# Credenciais de APIs externas do Pauteiro
# (adicionar ao .env existente)

# X/Twitter API v2
TWITTER_BEARER_TOKEN=...
TWITTER_API_KEY=...
TWITTER_API_SECRET=...
TWITTER_ACCESS_TOKEN=...
TWITTER_ACCESS_TOKEN_SECRET=...

# Reddit API (PRAW)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT="brasileira.news Pauteiro/3.0 (by /u/brasileira_news)"

# Pytrends não precisa de credenciais (usa cookies do navegador simulado)
# Google Cloud Trends API oficial (opcional — fallback para pytrends)
GOOGLE_TRENDS_API_KEY=...

# Pauteiro Config
PAUTEIRO_MAX_BRIEFINGS_PER_CYCLE=10
PAUTEIRO_MIN_SCORE_FOR_BRIEFING=55
PAUTEIRO_COVERAGE_WINDOW_HOURS=6
```

### 11.3 Arquivo requirements.txt (adições para o Pauteiro)

```
# Pauteiro V3 - Dependências adicionais
pytrends>=4.9.0
tweepy>=4.14.0
praw>=7.7.0
datasketch>=1.6.0
scikit-learn>=1.4.0

# Já presentes no requirements.txt principal (verificar versões)
httpx>=0.27.0
feedparser>=6.0.10
aiokafka>=0.10.0
redis[hiredis]>=5.0.0
asyncpg>=0.29.0
pgvector>=0.2.5
litellm>=1.80.0,!=1.82.7,!=1.82.8
langgraph>=0.1.0
langchain-openai>=0.1.0
pydantic>=2.5.0
```

---

## PARTE XII — ENTRYPOINT: COMO EXECUTAR O PAUTEIRO

### 12.1 Script de Inicialização

```python
# scripts/run_pauteiro.py
"""
Script de inicialização do Pauteiro V3.

Uso:
    python scripts/run_pauteiro.py

O Pauteiro é um serviço PARALELO. Rode em processo separado:
    # Terminal 1: Pipeline principal
    python scripts/run_workers.py

    # Terminal 2: Pauteiro (paralelo, independente)
    python scripts/run_pauteiro.py

Com Docker Compose:
    services:
      pauteiro:
        command: python scripts/run_pauteiro.py
        restart: unless-stopped
"""

import asyncio
import logging
import os
import signal
import sys

import asyncpg
import redis.asyncio as aioredis

# Adiciona o root do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brasileira.config import get_settings
from brasileira.llm.smart_router import SmartLLMRouter
from brasileira.agents.pauteiro import PauteiroAgent
from brasileira.agents.pauteiro.monitors.google_trends import GoogleTrendsMonitor
from brasileira.agents.pauteiro.monitors.x_trends import XTrendsMonitor
from brasileira.agents.pauteiro.monitors.reddit_monitor import RedditMonitor
from brasileira.agents.pauteiro.monitors.agencias_monitor import AgenciasMonitor
from brasileira.agents.pauteiro.monitors.internal_trends import InternalTrendMonitor
from brasileira.agents.pauteiro.signal_aggregator import SignalAggregator
from brasileira.agents.pauteiro.coverage_filter import CoverageFilter
from brasileira.agents.pauteiro.briefing_generator import BriefingGenerator
from brasileira.agents.pauteiro.kafka_producer import PauteiroKafkaProducer
from brasileira.agents.pauteiro.circuit_breaker import MultiSourceCircuitBreaker
from brasileira.agents.pauteiro.memory import PauteiroMemory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_pauteiro")


async def main():
    settings = get_settings()
    logger.info("Iniciando Pauteiro V3...")

    # ── Infraestrutura ──────────────────────────────────────────────────────

    # PostgreSQL
    db_pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=2,
        max_size=5,
        command_timeout=30,
    )

    # Redis
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

    # ── SmartLLMRouter ──────────────────────────────────────────────────────
    llm_router = SmartLLMRouter(
        redis_client=redis_client,
        db_pool=db_pool,
    )
    await llm_router.initialize()

    # ── Embeddings (para pgvector) ──────────────────────────────────────────
    from langchain_openai import OpenAIEmbeddings
    embeddings_client = OpenAIEmbeddings(
        openai_api_key=settings.OPENAI_KEYS[0],
        model="text-embedding-3-small",
    )

    # ── Circuit Breaker ─────────────────────────────────────────────────────
    circuit_breaker = MultiSourceCircuitBreaker()

    # ── Monitores ────────────────────────────────────────────────────────────
    google_trends_monitor = GoogleTrendsMonitor(
        circuit_breaker=circuit_breaker,
        redis_client=redis_client,
    )

    x_trends_monitor = XTrendsMonitor(
        bearer_token=settings.TWITTER_BEARER_TOKEN,
        circuit_breaker=circuit_breaker,
        redis_client=redis_client,
    )

    reddit_monitor = RedditMonitor(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
        circuit_breaker=circuit_breaker,
    )

    agencias_monitor = AgenciasMonitor(
        circuit_breaker=circuit_breaker,
    )

    internal_trend_monitor = InternalTrendMonitor(
        db_pool=db_pool,
        circuit_breaker=circuit_breaker,
    )

    # ── Processamento ────────────────────────────────────────────────────────
    signal_aggregator = SignalAggregator()

    coverage_filter = CoverageFilter(
        db_pool=db_pool,
        redis_client=redis_client,
        embeddings_client=embeddings_client,
    )

    briefing_generator = BriefingGenerator(
        llm_router=llm_router,
    )

    # ── Kafka Producer ───────────────────────────────────────────────────────
    kafka_producer = PauteiroKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    )
    await kafka_producer.start()

    # ── Memória ──────────────────────────────────────────────────────────────
    memory = PauteiroMemory(
        db_pool=db_pool,
        redis_client=redis_client,
        embeddings_client=embeddings_client,
    )

    # ── Agente ───────────────────────────────────────────────────────────────
    agent = PauteiroAgent(
        google_trends_monitor=google_trends_monitor,
        x_trends_monitor=x_trends_monitor,
        reddit_monitor=reddit_monitor,
        agencias_monitor=agencias_monitor,
        internal_trend_monitor=internal_trend_monitor,
        signal_aggregator=signal_aggregator,
        coverage_filter=coverage_filter,
        briefing_generator=briefing_generator,
        kafka_producer=kafka_producer,
        memory=memory,
        circuit_breaker=circuit_breaker,
        max_briefings_per_cycle=int(
            os.getenv("PAUTEIRO_MAX_BRIEFINGS_PER_CYCLE", "10")
        ),
        min_score_for_briefing=float(
            os.getenv("PAUTEIRO_MIN_SCORE_FOR_BRIEFING", "55")
        ),
    )

    # ── Signal Handlers ───────────────────────────────────────────────────────
    loop = asyncio.get_running_loop()

    def handle_shutdown():
        logger.info("Sinal de parada recebido — finalizando Pauteiro...")
        asyncio.create_task(agent.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_shutdown)

    # ── Executar ─────────────────────────────────────────────────────────────
    try:
        logger.info("Pauteiro V3 rodando como serviço PARALELO")
        logger.info("NÃO é entry point. Pipeline principal opera independentemente.")
        await agent.run_continuous()
    finally:
        await kafka_producer.stop()
        await db_pool.close()
        await redis_client.close()
        logger.info("Pauteiro V3 finalizado.")


if __name__ == "__main__":
    asyncio.run(main())
```

### 12.2 Docker Compose Service

```yaml
# Adicionar ao docker-compose.yml existente:

services:
  pauteiro:
    build: .
    command: python scripts/run_pauteiro.py
    restart: unless-stopped
    environment:
      - TWITTER_BEARER_TOKEN=${TWITTER_BEARER_TOKEN}
      - REDDIT_CLIENT_ID=${REDDIT_CLIENT_ID}
      - REDDIT_CLIENT_SECRET=${REDDIT_CLIENT_SECRET}
      - REDDIT_USER_AGENT=brasileira.news Pauteiro/3.0
      - PAUTEIRO_MAX_BRIEFINGS_PER_CYCLE=10
      - PAUTEIRO_MIN_SCORE_FOR_BRIEFING=55
    depends_on:
      - kafka
      - redis
      - postgres
    healthcheck:
      test: ["CMD", "python", "-c", "import redis; redis.from_url('${REDIS_URL}').ping()"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
```

---

## PARTE XIII — TESTES

### 13.1 Testes Unitários: Monitor Google Trends

```python
# tests/test_pauteiro/test_google_trends_monitor.py

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from brasileira.agents.pauteiro.monitors.google_trends import GoogleTrendsMonitor
from brasileira.agents.pauteiro.circuit_breaker import MultiSourceCircuitBreaker


@pytest.fixture
def circuit_breaker():
    return MultiSourceCircuitBreaker()


@pytest.fixture
def redis_mock():
    mock = AsyncMock()
    mock.exists.return_value = 0
    mock.setex.return_value = True
    return mock


@pytest.fixture
def google_trends_monitor(circuit_breaker, redis_mock):
    return GoogleTrendsMonitor(
        circuit_breaker=circuit_breaker,
        redis_client=redis_mock,
    )


class TestGoogleTrendsMonitor:

    @pytest.mark.asyncio
    async def test_retorna_lista_vazia_quando_circuit_aberto(
        self, google_trends_monitor, circuit_breaker
    ):
        """Circuit aberto deve retornar lista vazia sem chamar a API."""
        # Força abertura do circuit
        for _ in range(10):
            circuit_breaker.record_failure("google_trends")

        result = await google_trends_monitor.get_realtime_trends()
        assert result == []

    @pytest.mark.asyncio
    async def test_retorna_sinais_com_score_valido(self, google_trends_monitor):
        """Todos os sinais devem ter score entre 0 e 100."""
        mock_trends = [
            {"keyword": "lula", "score": 95, "fonte": "google_trends_realtime",
             "categoria_raw": [], "artigos_relacionados": [],
             "timestamp": "2026-03-26T14:00:00", "geo": "BR"},
            {"keyword": "dólar", "score": 80, "fonte": "google_trends_daily",
             "categoria_raw": [], "artigos_relacionados": [],
             "timestamp": "2026-03-26T14:00:00", "geo": "BR"},
        ]

        with patch.object(
            google_trends_monitor, "_fetch_trends_sync", return_value=mock_trends
        ):
            result = await google_trends_monitor.get_realtime_trends()

        assert all(0 <= s["score"] <= 100 for s in result)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_registra_falha_no_circuit_breaker_em_excecao(
        self, google_trends_monitor, circuit_breaker
    ):
        """Exceção deve registrar falha no circuit breaker."""
        with patch.object(
            google_trends_monitor, "_fetch_trends_sync", side_effect=ConnectionError("timeout")
        ):
            result = await google_trends_monitor.get_realtime_trends()

        assert result == []
        assert circuit_breaker._breakers["google_trends"].failure_rate > 0

    def test_fetch_trends_sync_formato_correto(self, google_trends_monitor):
        """Sinal bruto deve ter campos obrigatórios."""
        with patch("pytrends.request.TrendReq") as mock_pytrends:
            import pandas as pd
            mock_df = pd.DataFrame([{"title": "test trend", "articles": []}])
            mock_pytrends.return_value.realtime_trending_searches.return_value = mock_df
            mock_pytrends.return_value.today_searches.return_value = pd.Series(["trend2"])

            google_trends_monitor._pytrends = mock_pytrends.return_value
            result = google_trends_monitor._fetch_trends_sync()

        required_fields = ["keyword", "score", "fonte", "timestamp", "geo"]
        for signal in result:
            for field in required_fields:
                assert field in signal, f"Campo obrigatório '{field}' ausente"
```

### 13.2 Testes Unitários: Signal Aggregator

```python
# tests/test_pauteiro/test_signal_aggregator.py

import pytest
from brasileira.agents.pauteiro.signal_aggregator import SignalAggregator


@pytest.fixture
def aggregator():
    return SignalAggregator(lsh_threshold=0.4, lsh_num_perm=64)


class TestSignalAggregator:

    def test_agregacao_basica_retorna_lista(self, aggregator):
        """Agregação de sinais básica deve retornar lista."""
        sinais = [
            {"keyword": "reforma tributária", "score": 80, "fonte": "google_trends_realtime",
             "timestamp": "2026-03-26T14:00:00"},
            {"keyword": "imposto renda", "score": 70, "fonte": "x_twitter_brasil",
             "timestamp": "2026-03-26T14:00:00"},
        ]
        result = aggregator.aggregate(sinais)
        assert isinstance(result, list)

    def test_score_maior_com_multiplas_fontes(self, aggregator):
        """Mesmo tema em múltiplas fontes deve ter score maior."""
        sinal_unico = [
            {"keyword": "reforma tributária", "score": 60, "fonte": "google_trends_realtime",
             "timestamp": "2026-03-26T14:00:00"},
        ]
        sinais_multiplos = [
            {"keyword": "reforma tributária", "score": 60, "fonte": "google_trends_realtime",
             "timestamp": "2026-03-26T14:00:00"},
            {"keyword": "reforma tributária", "score": 60, "fonte": "x_twitter_brasil",
             "timestamp": "2026-03-26T14:00:00"},
            {"keyword": "reforma tributária", "score": 60, "fonte": "reddit_hot",
             "timestamp": "2026-03-26T14:00:00"},
        ]

        result_unico = aggregator.aggregate(sinal_unico)
        result_multiplo = aggregator.aggregate(sinais_multiplos)

        # Com múltiplas fontes, o score deve ser maior
        if result_unico and result_multiplo:
            assert result_multiplo[0]["score"] >= result_unico[0]["score"]

    def test_urgencia_breaking_para_score_alto(self, aggregator):
        """Score alto + is_breaking deve resultar em urgência BREAKING."""
        sinais = [
            {"keyword": "urgente terremoto", "score": 95, "fonte": "agencia_reuters_brasil",
             "is_breaking": True, "timestamp": "2026-03-26T14:00:00"},
        ]
        result = aggregator.aggregate(sinais)
        assert len(result) > 0
        assert result[0]["urgencia"] == "BREAKING"

    def test_lista_vazia_retorna_lista_vazia(self, aggregator):
        """Entrada vazia deve retornar lista vazia."""
        result = aggregator.aggregate([])
        assert result == []

    def test_resultado_ordenado_por_score_desc(self, aggregator):
        """Resultado deve estar ordenado por score decrescente."""
        sinais = [
            {"keyword": "tema a", "score": 30, "fonte": "google_trends_realtime",
             "timestamp": "2026-03-26T14:00:00"},
            {"keyword": "tema b", "score": 90, "fonte": "x_twitter_brasil",
             "timestamp": "2026-03-26T14:00:00"},
            {"keyword": "tema c", "score": 60, "fonte": "reddit_hot",
             "timestamp": "2026-03-26T14:00:00"},
        ]
        result = aggregator.aggregate(sinais)
        if len(result) >= 2:
            scores = [r["score"] for r in result]
            assert scores == sorted(scores, reverse=True)
```

### 13.3 Testes Unitários: BriefingGenerator

```python
# tests/test_pauteiro/test_briefing_generator.py

import json
import pytest
from unittest.mock import AsyncMock
from brasileira.agents.pauteiro.briefing_generator import BriefingGenerator, MACROCATEGORIAS_V3


@pytest.fixture
def llm_router_mock():
    mock = AsyncMock()
    mock.route_request = AsyncMock(return_value=json.dumps({
        "pauta_id": "test-uuid-123",
        "titulo_sugerido": "Reforma tributária aprovada pelo Congresso",
        "subtitulo_editorial": "Votação ocorreu em sessão extraordinária",
        "angulo_editorial": "Explore o impacto para contribuintes de renda média",
        "por_que_agora": "Votação ocorreu há 40 minutos, trending score 94",
        "lide_sugerido": "O Congresso Nacional aprovou nesta tarde...",
        "fontes_sugeridas": ["Agência Câmara", "Receita Federal"],
        "palavras_chave_seo": ["reforma tributária", "imposto renda"],
        "categoria": "Política",
        "urgencia": "ESPECIAL",
        "prioridade": "ALTA",
        "estimativa_engajamento": "ALTO",
        "notas_reporter": "Verificar placar de votos",
        "urls_referencia": ["https://camara.leg.br"],
        "timestamp_geracao": "2026-03-26T14:30:00Z",
        "agente": "pauteiro-v3",
    }))
    return mock


@pytest.fixture
def briefing_generator(llm_router_mock):
    return BriefingGenerator(llm_router=llm_router_mock)


class TestBriefingGenerator:

    @pytest.mark.asyncio
    async def test_gera_briefing_valido(self, briefing_generator, llm_router_mock):
        """Briefing gerado deve ter todos os campos obrigatórios."""
        sinal = {
            "tema": "Reforma tributária aprovada",
            "score": 90.0,
            "urgencia": "ESPECIAL",
            "num_fontes": 3,
            "fontes": ["google_trends_realtime", "x_twitter_brasil", "agencia_reuters_brasil"],
            "urls_referencia": ["https://camara.leg.br"],
            "resumo_disponivel": "Congresso votou reforma tributária",
            "sinais_raw": [],
        }

        result = await briefing_generator.generate_briefing(sinal)

        assert result is not None
        assert result["titulo_sugerido"] == "Reforma tributária aprovada pelo Congresso"
        assert result["categoria"] in MACROCATEGORIAS_V3
        assert result["urgencia"] in ["BREAKING", "ESPECIAL", "NORMAL"]
        assert result["prioridade"] in ["ALTA", "MEDIA", "BAIXA"]

    @pytest.mark.asyncio
    async def test_usa_tier_premium(self, briefing_generator, llm_router_mock):
        """Briefing deve ser gerado com task_type=pauta_especial (PREMIUM)."""
        sinal = {
            "tema": "Teste premium",
            "score": 70.0,
            "urgencia": "NORMAL",
            "num_fontes": 2,
            "fontes": ["google_trends_realtime"],
            "urls_referencia": [],
            "resumo_disponivel": "",
            "sinais_raw": [],
        }

        await briefing_generator.generate_briefing(sinal)

        # Verifica que route_request foi chamado com task_type=pauta_especial
        llm_router_mock.route_request.assert_called_once()
        call_kwargs = llm_router_mock.route_request.call_args
        assert call_kwargs.kwargs.get("task_type") == "pauta_especial"

    @pytest.mark.asyncio
    async def test_retorna_none_para_tema_vazio(self, briefing_generator):
        """Tema vazio deve retornar None sem chamar LLM."""
        sinal = {"tema": "", "score": 80.0}
        result = await briefing_generator.generate_briefing(sinal)
        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_quando_llm_retorna_json_invalido(
        self, briefing_generator, llm_router_mock
    ):
        """JSON inválido do LLM deve gerar briefing de fallback."""
        llm_router_mock.route_request = AsyncMock(return_value="texto sem json válido")

        sinal = {
            "tema": "Tema teste",
            "score": 65.0,
            "urgencia": "NORMAL",
            "num_fontes": 1,
            "fontes": ["google_trends_daily"],
            "urls_referencia": [],
            "resumo_disponivel": "",
            "sinais_raw": [],
        }

        result = await briefing_generator.generate_briefing(sinal)

        # Deve retornar briefing de fallback, nunca None
        assert result is not None
        assert result.get("fallback") is True
        assert result["titulo_sugerido"] == "Tema teste"

    @pytest.mark.asyncio
    async def test_categoria_invalida_convertida_para_ultimas_noticias(
        self, briefing_generator, llm_router_mock
    ):
        """Categoria inválida do LLM deve ser substituída por 'Últimas Notícias'."""
        llm_router_mock.route_request = AsyncMock(return_value=json.dumps({
            "titulo_sugerido": "Título teste",
            "categoria": "CategoriaInexistente",  # Inválida
            "urgencia": "NORMAL",
            "prioridade": "MEDIA",
        }))

        sinal = {
            "tema": "Teste categoria",
            "score": 60.0,
            "urgencia": "NORMAL",
            "num_fontes": 1,
            "fontes": ["reddit_hot"],
            "urls_referencia": [],
            "resumo_disponivel": "",
            "sinais_raw": [],
        }

        result = await briefing_generator.generate_briefing(sinal)
        assert result["categoria"] == "Últimas Notícias"
```

### 13.4 Teste de Integração: Ciclo Completo

```python
# tests/test_pauteiro/test_pauteiro_integration.py

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from brasileira.agents.pauteiro import PauteiroAgent, PauteiroState
from brasileira.agents.pauteiro.circuit_breaker import MultiSourceCircuitBreaker


@pytest.fixture
def mock_dependencies():
    """Cria mocks de todas as dependências do Pauteiro."""

    # Sinais mock de cada monitor
    sinais_google = [
        {"keyword": "reforma previdência", "score": 85, "fonte": "google_trends_realtime",
         "timestamp": "2026-03-26T14:00:00", "geo": "BR"},
    ]
    sinais_x = [
        {"keyword": "#reformaprevidência", "score": 75, "fonte": "x_twitter_brasil",
         "tweet_volume": 15000, "is_hashtag": True, "timestamp": "2026-03-26T14:00:00"},
    ]
    sinais_agencias = [
        {"keyword": "Previdência social: nova proposta aprovada no Senado", "score": 90,
         "is_breaking": True, "agencia": "Agência Brasil", "fonte": "agencia_agência_brasil",
         "url": "https://agenciabrasil.ebc.com.br/...", "timestamp": "2026-03-26T14:00:00"},
    ]

    # Briefing mock
    mock_briefing = {
        "pauta_id": "test-pauta-001",
        "titulo_sugerido": "Senado aprova mudanças na previdência social",
        "subtitulo_editorial": "Votação ocorreu em sessão extraordinária",
        "angulo_editorial": "Foco no impacto para trabalhadores informais",
        "por_que_agora": "Votação confirmada pela Agência Brasil há minutos",
        "lide_sugerido": "O Senado Federal aprovou nesta tarde...",
        "fontes_sugeridas": ["Agência Brasil", "Ministério da Previdência"],
        "palavras_chave_seo": ["previdência", "reforma", "senado", "votação"],
        "categoria": "Política",
        "urgencia": "BREAKING",
        "prioridade": "ALTA",
        "estimativa_engajamento": "ALTO",
        "notas_reporter": "Verificar texto final da votação",
        "urls_referencia": ["https://agenciabrasil.ebc.com.br/..."],
        "timestamp_geracao": "2026-03-26T14:05:00Z",
        "agente": "pauteiro-v3",
        "score_original": 91.7,
        "num_fontes_confirmaram": 3,
    }

    google_trends_mock = AsyncMock()
    google_trends_mock.get_realtime_trends.return_value = sinais_google

    x_trends_mock = AsyncMock()
    x_trends_mock.get_trends.return_value = sinais_x

    reddit_mock = AsyncMock()
    reddit_mock.get_hot_topics.return_value = []

    agencias_mock = AsyncMock()
    agencias_mock.get_breaking_signals.return_value = sinais_agencias

    internal_mock = AsyncMock()
    internal_mock.get_internal_trends.return_value = []

    aggregator_mock = MagicMock()
    aggregator_mock.aggregate.return_value = [{
        "tema": "Previdência Social - Reforma aprovada no Senado",
        "score": 91.7,
        "urgencia": "BREAKING",
        "num_fontes": 3,
        "fontes": ["google_trends_realtime", "x_twitter_brasil", "agencia_agência_brasil"],
        "sinais_raw": sinais_google + sinais_x + sinais_agencias,
        "urls_referencia": ["https://agenciabrasil.ebc.com.br/..."],
        "resumo_disponivel": "Senado aprova mudanças na previdência",
        "is_breaking": True,
        "timestamp": "2026-03-26T14:05:00Z",
        "theme_key": "abc123",
    }]

    coverage_filter_mock = AsyncMock()
    coverage_filter_mock.filter_covered.return_value = (
        [aggregator_mock.aggregate.return_value[0]],  # novos
        [],  # descartados
    )
    coverage_filter_mock.mark_as_covered.return_value = None

    briefing_gen_mock = AsyncMock()
    briefing_gen_mock.generate_briefing.return_value = mock_briefing

    kafka_mock = AsyncMock()
    kafka_mock.send_pauta.return_value = True

    memory_mock = AsyncMock()
    memory_mock.save_pauta_episodica.return_value = None
    memory_mock.save_scratchpad.return_value = None
    memory_mock.save_working_state.return_value = None

    return {
        "google_trends_monitor": google_trends_mock,
        "x_trends_monitor": x_trends_mock,
        "reddit_monitor": reddit_mock,
        "agencias_monitor": agencias_mock,
        "internal_trend_monitor": internal_mock,
        "signal_aggregator": aggregator_mock,
        "coverage_filter": coverage_filter_mock,
        "briefing_generator": briefing_gen_mock,
        "kafka_producer": kafka_mock,
        "memory": memory_mock,
        "circuit_breaker": MultiSourceCircuitBreaker(),
    }


@pytest.fixture
def pauteiro_agent(mock_dependencies):
    return PauteiroAgent(**mock_dependencies, max_briefings_per_cycle=5)


class TestPauteiroIntegration:

    @pytest.mark.asyncio
    async def test_ciclo_completo_breaking_news(self, pauteiro_agent, mock_dependencies):
        """
        Ciclo completo com breaking news:
        - Coleta sinais → Agrega → Filtra → Gera briefing PREMIUM → Publica Kafka
        """
        state = PauteiroState()

        # Executa um ciclo (sem o loop de aguardo)
        state_dict = state.model_dump()

        # Step 1: Coletar sinais
        result = await pauteiro_agent._step_coletar_sinais(PauteiroState(**state_dict))
        state_dict.update(result)
        assert state_dict["total_sinais_brutos"] > 0

        # Step 2: Agregar
        result = await pauteiro_agent._step_agregar_sinais(PauteiroState(**state_dict))
        state_dict.update(result)
        assert len(state_dict["sinais_agregados"]) > 0

        # Step 3: Filtrar cobertura
        result = await pauteiro_agent._step_filtrar_cobertura(PauteiroState(**state_dict))
        state_dict.update(result)
        assert len(state_dict["sinais_novos"]) > 0

        # Step 4: Gerar briefings (PREMIUM)
        result = await pauteiro_agent._step_gerar_briefings(PauteiroState(**state_dict))
        state_dict.update(result)
        assert len(state_dict["briefings_gerados"]) > 0
        # Verifica que LLM PREMIUM foi chamado
        mock_dependencies["briefing_generator"].generate_briefing.assert_called()

        # Step 5: Publicar Kafka
        result = await pauteiro_agent._step_publicar_kafka(PauteiroState(**state_dict))
        state_dict.update(result)
        assert state_dict["briefings_enviados"] > 0
        # Verifica publicação no tópico correto
        mock_dependencies["kafka_producer"].send_pauta.assert_called()

        # Step 6: Salvar memória
        await pauteiro_agent._step_salvar_memoria(PauteiroState(**state_dict))
        mock_dependencies["memory"].save_pauta_episodica.assert_called()

    @pytest.mark.asyncio
    async def test_pipeline_nao_bloqueado_quando_todos_monitores_falham(
        self, pauteiro_agent, mock_dependencies
    ):
        """
        Se todos os monitores falharem, o pipeline principal NÃO é afetado.
        O Pauteiro simplesmente não gera pautas neste ciclo.
        """
        # Força falha em todos os monitores
        mock_dependencies["google_trends_monitor"].get_realtime_trends.side_effect = Exception("API down")
        mock_dependencies["x_trends_monitor"].get_trends.side_effect = Exception("Rate limit")
        mock_dependencies["reddit_monitor"].get_hot_topics.side_effect = Exception("503")
        mock_dependencies["agencias_monitor"].get_breaking_signals.side_effect = Exception("Timeout")
        mock_dependencies["internal_trend_monitor"].get_internal_trends.side_effect = Exception("DB error")

        state = PauteiroState()
        result = await pauteiro_agent._step_coletar_sinais(state)

        # Deve retornar 0 sinais, sem levantar exceção
        assert result["total_sinais_brutos"] == 0
        assert result["sinais_google_trends"] == []
        assert result["sinais_x_twitter"] == []

        # Pipeline principal NÃO é afetado (verificação conceitual)
        # O Pauteiro é um processo separado que apenas deixa de gerar pautas

    @pytest.mark.asyncio
    async def test_nao_envia_pauta_duplicada(self, pauteiro_agent, mock_dependencies):
        """
        Tema já coberto deve ser filtrado pelo CoverageFilter.
        Nenhuma pauta duplicada deve chegar ao Kafka.
        """
        # Configura filtro para descartar todos os sinais
        mock_dependencies["coverage_filter"].filter_covered.return_value = (
            [],  # novos: NENHUM
            [{"tema": "tema já coberto", "score": 90.0, "descarte_motivo": "semantica_similar"}],
        )

        state = PauteiroState(
            sinais_agregados=[{"tema": "tema já coberto", "score": 90.0, "urgencia": "ESPECIAL"}]
        )

        result_filter = await pauteiro_agent._step_filtrar_cobertura(state)

        # Não há sinais novos
        assert len(result_filter["sinais_novos"]) == 0

        # Sem sinais novos, não gera briefings
        should_generate = pauteiro_agent._deve_gerar_briefings(
            PauteiroState(**{**state.model_dump(), **result_filter})
        )
        assert should_generate is False

        # Kafka NÃO é chamado
        mock_dependencies["kafka_producer"].send_pauta.assert_not_called()
```

### 13.5 Testes de Performance

```python
# tests/test_pauteiro/test_performance.py

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from brasileira.agents.pauteiro.signal_aggregator import SignalAggregator


class TestPerformance:

    def test_agregacao_de_500_sinais_em_menos_de_2s(self):
        """Agregação de 500 sinais deve concluir em menos de 2 segundos."""
        aggregator = SignalAggregator()

        # Gera 500 sinais sintéticos
        sinais = []
        for i in range(500):
            sinais.append({
                "keyword": f"trending topic {i % 50}",  # 50 temas únicos × 10 variações
                "score": 50 + (i % 50),
                "fonte": f"fonte_{i % 5}",
                "timestamp": "2026-03-26T14:00:00",
            })

        inicio = time.time()
        result = aggregator.aggregate(sinais)
        duracao = time.time() - inicio

        assert duracao < 2.0, f"Agregação demorou {duracao:.2f}s (limite: 2s)"
        assert len(result) > 0
        assert len(result) <= 50  # Máximo de temas únicos

    @pytest.mark.asyncio
    async def test_5_monitores_em_paralelo_mais_rapido_que_sequencial(self):
        """Coleta paralela deve ser mais rápida que sequencial."""

        async def mock_monitor_slow():
            await asyncio.sleep(0.5)  # Simula latência de 500ms
            return [{"keyword": "trend", "score": 80, "fonte": "mock", "timestamp": ""}]

        # Mede tempo sequencial
        inicio_seq = time.time()
        for _ in range(5):
            await mock_monitor_slow()
        tempo_seq = time.time() - inicio_seq

        # Mede tempo paralelo
        inicio_par = time.time()
        await asyncio.gather(*[mock_monitor_slow() for _ in range(5)])
        tempo_par = time.time() - inicio_par

        assert tempo_par < tempo_seq / 2, (
            f"Paralelo ({tempo_par:.2f}s) deveria ser 2x mais rápido "
            f"que sequencial ({tempo_seq:.2f}s)"
        )
```

---

## PARTE XIV — CHECKLIST DE IMPLEMENTAÇÃO

### ✅ Verificação de Arquitetura

```
□ pauteiro.py NUNCA se posiciona no path de publicação de artigos
□ pauteiro.py NUNCA consome de classified-articles ou raw-articles
□ pauteiro.py APENAS produz para pautas-especiais
□ Pipeline principal (Worker Pool → Classificador → Reporter) opera SEM o Pauteiro
□ 5 monitores externos rodam em paralelo com asyncio.gather()
□ Circuit breaker ativo em cada fonte externa
□ LLM PREMIUM (task_type="pauta_especial") para geração de briefings
□ LLM PADRÃO (task_type="trending_detection") para análise inicial
```

### ✅ Verificação de Integração Kafka

```
□ Producer configurado para tópico "pautas-especiais"
□ Partition key = editoria/categoria (ex: "politica", "economia")
□ Schema version "3.0" em todos os envelopes
□ Campo expires_at calculado por urgência (BREAKING=30min, ESPECIAL=2h, NORMAL=6h)
□ acks="all" configurado no producer
□ Consumer no Reporter com group_id="reporters-pautas-especiais"
□ auto_offset_reset="latest" no consumer (não reprocessa pautas antigas)
```

### ✅ Verificação de Memória

```
□ Memória working: Redis key "agent:working_memory:pauteiro:{cycle_id}" com TTL 4h
□ Scratchpad: Redis key "pauteiro:radar_fontes:{cycle_id}" com TTL 4h
□ Memória episódica: tabela memoria_agentes com embedding vector(1536)
□ Deduplicação via pgvector com threshold 0.82
□ Redis cache de pautas enviadas com TTL 1h
□ Progressive Disclosure implementado (título+score primeiro, contexto depois)
```

### ✅ Verificação dos Monitores

```
□ GoogleTrendsMonitor: pytrends com geo='BR', hl='pt-BR'
□ GoogleTrendsMonitor: realtime_trending_searches + today_searches
□ XTrendsMonitor: tweepy + WOEID Brasil (23424768) + principais cidades
□ XTrendsMonitor: fallback para último resultado em cache se API falha
□ RedditMonitor: praw read_only + subreddits brasileiros
□ RedditMonitor: hot + rising com MIN_SCORE=50
□ AgenciasMonitor: httpx async + feedparser para 8 feeds de agências
□ AgenciasMonitor: detecção de breaking por palavras-chave em pt-BR
□ InternalTrendMonitor: TF-IDF clustering em artigos das últimas 4h
□ Todos os monitores com circuit breaker (30% falha → abre por 5 min)
```

### ✅ Verificação da Geração de Briefings

```
□ BriefingGenerator usa SmartLLMRouter com task_type="pauta_especial"
□ System prompt em português BR com contexto editorial completo
□ 16 macrocategorias no prompt (Política, Economia, Esportes... etc.)
□ Parse robusto de JSON com fallback em caso de output inválido
□ Validação de categoria (se inválida → "Últimas Notícias")
□ Validação de urgência (se inválida → valor do sinal original)
□ Máximo 10 briefings por ciclo (configurável)
□ Breaking news processados em paralelo com prioridade
□ Delay de 0.5s entre briefings normais para não saturar LLM
```

### ✅ Verificação de Testes

```
□ test_google_trends_monitor.py: 4+ testes unitários
□ test_signal_aggregator.py: 5+ testes unitários
□ test_briefing_generator.py: 5+ testes unitários (inclui teste de tier PREMIUM)
□ test_coverage_filter.py: testes de cada fonte de dedup (Redis, pgvector, DB)
□ test_kafka_producer.py: testes de serialização e partition key
□ test_circuit_breaker.py: testes de estados CLOSED/OPEN/HALF_OPEN
□ test_pauteiro_integration.py: ciclo completo + pipeline não bloqueado
□ test_performance.py: agregação <2s, paralelismo confirmado
```

### ✅ Verificação de Configuração

```
□ TWITTER_BEARER_TOKEN no .env
□ REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT no .env
□ PAUTEIRO_MAX_BRIEFINGS_PER_CYCLE=10 (default)
□ PAUTEIRO_MIN_SCORE_FOR_BRIEFING=55 (default)
□ PAUTEIRO_COVERAGE_WINDOW_HOURS=6 (default)
□ pytrends>=4.9.0 no requirements.txt
□ tweepy>=4.14.0 no requirements.txt
□ praw>=7.7.0 no requirements.txt
□ datasketch>=1.6.0 no requirements.txt
□ scripts/run_pauteiro.py criado e funcional
□ Docker Compose service "pauteiro" configurado
```

### ✅ Verificação de Observabilidade

```
□ Logs estruturados em cada step do grafo LangGraph
□ Log de ciclo com: total_sinais, agregados, novos, briefings_gerados, briefings_enviados
□ Circuit breaker status exportado periodicamente
□ Scratchpad radar_fontes_{ciclo}.json no Redis por ciclo
□ Métricas: pautas_geradas/ciclo, latência_coleta, latência_geração
□ Alerta se 0 pautas geradas em 3 ciclos consecutivos
□ Log de descarte com motivo (redis_cache | semantica_similar | artigo_publicado)
```

---

## PARTE XV — REGRAS INVIOLÁVEIS (REVISÃO FINAL)

Esta seção existe para que a IA de implementação leia uma última vez antes de finalizar o código.

### 🚫 O QUE O PAUTEIRO NUNCA FAZ

| Proibição | Consequência se violado | Verificação |
|-----------|------------------------|-------------|
| Ser entry point do pipeline | 0 artigos publicados (bug fatal da V2) | grep "classified-articles" em pauteiro.py → deve ser 0 |
| Filtrar fontes RSS/scrapers | Mesmo bug fatal da V2 | Pauteiro não tem acesso ao tópico raw-articles |
| Bloquear publicação | Gargalo no pipeline | Reporter não espera resposta do Pauteiro |
| Usar LLM ECONÔMICO para briefings | Qualidade editorial baixa | task_type="pauta_especial" → Tier PREMIUM obrigatório |
| Usar EventBus em vez de Kafka | Pautas perdidas sem consumer ativo | Toda publicação via aiokafka producer |
| Ter memória fake | Duplicação de pautas | Embeddings reais em pgvector obrigatórios |

### ✅ O QUE O PAUTEIRO SEMPRE FAZ

| Obrigação | Implementação |
|-----------|---------------|
| Rodar em paralelo ao pipeline | Processo separado, Kafka desacoplado |
| Monitorar 5 fontes externas | Google Trends + X + Reddit + Agências + Internos |
| Usar circuit breaker por fonte | MultiSourceCircuitBreaker em cada monitor |
| Gerar briefings com LLM PREMIUM | task_type="pauta_especial" via SmartLLMRouter |
| Publicar em pautas-especiais | PauteiroKafkaProducer com partition key=editoria |
| Deduplicar semanticamente | pgvector com threshold 0.82 |
| Persistir memória episódica | Embedding de cada pauta gerada em pgvector |
| Usar Progressive Disclosure | Título+score primeiro, contexto expandido depois |

### 🔑 Fluxo Correto — Diagrama de Confirmação

```
[Google Trends] ──┐
[X/Twitter]     ──┤
[Reddit]        ──┼→ [Agregador] → [Filtro Cobertura] → [BriefingGen PREMIUM] → Kafka: pautas-especiais
[Agências]      ──┤
[Interno]       ──┘

                              PARALELO — SEM CONEXÃO COM:

[648+ Fontes] → [Worker Pool] → [Kafka: raw-articles] → [Classificador] → [Kafka: classified-articles] → [Reporter] → [WordPress]
                                                                                                                  ↑
                                                                                       Também consome pautas-especiais
                                                                                       COMO OPORTUNIDADE ADICIONAL
```

---

*Briefing #9 — Pauteiro V3 | brasileira.news | Data: 26 de março de 2026*
*Documento de implementação para IA — não consulte outros documentos para os pontos marcados como OBRIGATÓRIO*
