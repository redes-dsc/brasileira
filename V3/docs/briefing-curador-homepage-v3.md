# Briefing Completo para IA — Curador Homepage V3

**Data:** 26 de março de 2026  
**Classificação:** Briefing de Implementação — Componente #8 (Camada 4: Curadoria e Inteligência)  
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)  
**Repositório:** https://github.com/redes-dsc/brasileira  
**Stack:** Python 3.12+ / LangGraph / Kafka / Redis / PostgreSQL / WordPress REST API / ACF PRO / asyncio  
**Componente:** `brasileira/agents/curador_homepage.py` + `brasileira/wordpress/` (templates PHP)  
**Depende de:** #1 SmartLLMRouter, #2 Worker Pool de Coletores  

---

## LEIA ISTO PRIMEIRO — Por Que o Curador da Homepage É Crítico

A homepage é a **vitrine do portal**. É o primeiro contato do leitor, o cartão de visita editorial, a referência de qualidade percebida. Em portais como G1, Folha e UOL, a homepage é curada manualmente dezenas de vezes por dia por equipes de 5-10 editores. Na brasileira.news V3, **um único agente de IA substitui essa equipe com ciclos de 15-30 minutos, 24 horas por dia, 365 dias por ano**.

A V2 do curador falhou em múltiplos níveis críticos — usando modelo econômico para decisões que exigem inteligência PREMIUM, gerando janelas de homepage vazia por até 90 segundos, sem controle de layout, sem leitura de métricas de CTR. Como registrado na auditoria de bugs: **"Os problemas de gestão das homes não parece ter sido endereçado com a força que precisa."**

Este briefing contém TUDO que você precisa para implementar o Curador Homepage V3 do zero. Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ QUEBRADO NA V2

### 1.1 O Bug Mais Grave: Janela de Homepage Vazia (Race Condition)

**Arquivo V2:** `curator_tagger.py` (chamado pelo `curator_agent.py` linha 433)  
**Localização:** `apply_all_positions()` → `clear_curator_tags()` seguido de loop de aplicação

```python
# V2 — CÓDIGO COM BUG CRÍTICO (NÃO USAR)
clear_curator_tags(dry_run=dry_run)  # ← Limpa TUDO primeiro

# ↑ Entre esta linha e o loop abaixo: homepage VAZIA por 30-90 segundos!

for tag_slug, post_ids in selections.items():
    apply_tag(tag_slug, post_ids)    # ← Reaplica lentamente (1 req/s * 60 posts = 60s)
```

**O problema:** Com `WP_PATCH_DELAY = 1.0s` e até ~60 posts para retaguar em ~14 posições, existe uma janela de **30 a 90 segundos** onde a homepage tem zero posts tagueados. Qualquer visitante nesse período vê a homepage completamente vazia.

**Agravante:** O curador V2 roda nos minutos 15 e 45. O Motor RSS publica nos minutos 0 e 30. Os ciclos se cruzam frequentemente, ampliando o problema.

**A V3 NUNCA faz clear antes de apply.** Usa diff atômico.

### 1.2 Tier LLM Invertido: Econômico Onde Deveria Ser Premium

| Função | Tier V2 (ERRADO) | Tier V3 (CORRETO) |
|--------|-------------------|---------------------|
| Homepage scoring | ECONÔMICO | **PREMIUM** |
| Decisão de layout | Nenhum LLM | **PREMIUM** |
| Seleção de manchete | Heurísticas simples | **PREMIUM** |
| Análise de breaking news | Nenhum | **PREMIUM** |

A auditoria do briefing principal é categórica: **"Curar homepage com modelo econômico é um erro grotesco."** O modelo econômico não tem capacidade de avaliar importância editorial, impacto jornalístico, e equilíbrio de cobertura com a profundidade necessária.

### 1.3 Arquitetura V2 por Tags (Sistema Errado)

O V2 controla a homepage aplicando **tags do WordPress** a posts. Isso é um anti-padrão grave:

```python
# V2 — ABORDAGEM POR TAGS (INCORRETA PARA V3)
# Aplica tag "home-manchete" no post #1234
# Aplica tag "home-destaque-1" no post #5678
# Theme lê as tags para montar a home
```

**Problemas:**
1. Tags são visíveis no front-end (poluem metadados públicos do post)
2. Sem controle de layout: sempre o mesmo layout, nunca muda para BREAKING
3. Sem etiquetas editoriais: sem labels "URGENTE", "EXCLUSIVO", "AO VIVO"
4. Sem tamanho de slot: não distingue destaque pequeno/médio/grande
5. Impossível mudar o layout global (normal/amplo/breaking) via tags

**A V3 usa ACF Options Page**, onde campos de opções globais controlam cada zona editorial, com total separação de layout e dados.

### 1.4 Outros Bugs Críticos da V2

| Bug | Severidade | Impacto |
|-----|-----------|---------|
| Timezone naive: `datetime.now()` vs `post_date` UTC | CRÍTICO | Erro sistemático de até 3h na comparação de datas |
| Dois `curator_config.py` completamente diferentes | CRÍTICO | Configurações em conflito silencioso |
| Self-import circular em `curator_agent.py` | CRÍTICO | Comportamento indefinido em reload |
| Credenciais hardcoded em 3 arquivos | CRÍTICO | Senha do banco exposta no repositório |
| SQL injection em `aplicar_homepage_tags.py` | CRÍTICO | Vulnerabilidade de segurança |
| `logger` não definido em `log_cycle()` | CRÍTICO | NameError silencia erros de log |
| `MAX_SAME_CATEGORY_DESTAQUE` definida mas nunca usada | ALTO | Sem diversidade editorial na home |
| Manchete pode ser post com 4h de idade | ALTO | Home aparentemente desatualizada |
| Budget LLM: os 30 últimos posts não são avaliados | MÉDIO | Ordem de processamento determina homepage |
| Cron sem lock: dois ciclos simultâneos possíveis | MÉDIO | Estado de tags completamente indefinido |
| `max(score, 0)` mascara posts negativos | MÉDIO | Posts ruins entram na home como "neutros" |

### 1.5 O Que Estava Certo na V2 (Manter)

- Conceito de window de artigos recentes para candidatos
- Registro de decisões editoriais em banco de dados
- Ciclo periódico (manter os 15-30 min)
- Separação entre score objetivo e score LLM
- Respeito a diversidade de categorias (conceito certo, implementação errada)

---

## PARTE II — ARQUITETURA V3

### 2.1 Visão Geral do Componente

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CURADOR HOMEPAGE V3                              │
│                                                                      │
│  TRIGGERS (entrada):                                                 │
│  ├── Kafka: article-published (novo artigo publicado)               │
│  ├── Kafka: breaking-candidate (Monitor Concorrência)               │
│  ├── Cron: ciclo periódico 15-30 min                                │
│  └── Redis: homepage:force_refresh (emergência)                     │
│                                                                      │
│  PIPELINE (6 etapas em LangGraph):                                  │
│  1. coletar_candidatos  — Artigos recentes do WordPress             │
│  2. score_editorial     — LLM PREMIUM avalia cada candidato         │
│  3. decidir_layout      — NORMAL / AMPLO / BREAKING                 │
│  4. compor_zonas        — 6 zonas editoriais montadas               │
│  5. aplicar_atomico     — Diff + patch no WordPress (sem janela)    │
│  6. registrar           — Métricas, memória, Kafka                  │
│                                                                      │
│  OUTPUTS (saída):                                                    │
│  ├── WordPress ACF Options: 6 zonas atualizadas                     │
│  ├── Redis: homepage:current (estado atual)                         │
│  ├── Kafka: homepage-updates (notificação Monitor)                  │
│  └── PostgreSQL: curador_cycles (log histórico)                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Estrutura de Arquivos

```
brasileira/
├── agents/
│   └── curador_homepage.py          # Agente principal (LangGraph)
├── homepage/
│   ├── __init__.py
│   ├── candidatos.py                # Coleta e filtra artigos candidatos
│   ├── scorer.py                    # Score objetivo + LLM PREMIUM
│   ├── layout.py                    # Decisão de layout (normal/amplo/breaking)
│   ├── compositor.py                # Monta as 6 zonas editoriais
│   ├── aplicador.py                 # Aplica no WordPress (diff atômico)
│   ├── metricas.py                  # CTR, bounce, tempo (Google Analytics / WP Stats)
│   └── state.py                     # HomepageState (Pydantic)
├── wordpress/
│   ├── template-homepage.php        # Template principal adaptativo
│   ├── acf-setup.php                # Registro de campos ACF Options
│   └── zones/
│       ├── breaking-fullwidth.php   # Zona 1: breaking news
│       ├── manchete-padrao.php      # Zona 1: layout normal
│       ├── manchete-ampla.php       # Zona 1: layout amplo
│       ├── destaques-grid.php       # Zona 2: grid adaptativo
│       ├── editoria-carrossel.php   # Zona 3: carrosséis por editoria
│       ├── mais-lidas.php           # Zona 4: auto-curada por analytics
│       ├── opiniao.php              # Zona 5: opinião e análise
│       └── regional.php             # Zona 6: conteúdo regional
└── config/
    └── homepage_zones.yaml          # Definição das 6 zonas
```

### 2.3 Modelo de Dados Central

```python
# brasileira/homepage/state.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel


class ArtigoCandidato(BaseModel):
    """Artigo candidato para a homepage."""
    wp_post_id: int
    titulo: str
    subtitulo: Optional[str] = None
    editoria: str                        # Uma das 16 macrocategorias
    urgencia: Literal["FLASH", "NORMAL", "ANALISE"] = "NORMAL"
    url: str
    imagem_url: Optional[str] = None
    imagem_width: int = 0
    imagem_height: int = 0
    fonte_nome: str
    publicado_em: datetime               # UTC sempre
    score_objetivo: float = 0.0          # Score calculado localmente
    score_llm: float = 0.0               # Score dado pelo LLM PREMIUM
    score_total: float = 0.0             # score_objetivo + score_llm
    ctr_atual: float = 0.0               # CTR nas últimas 2h (se disponível)
    capas_concorrentes: int = 0          # Quantas capas de concorrentes cobrem o tema
    views_1h: int = 0                    # Views na última hora
    is_breaking: bool = False            # Flag de breaking news
    label: Literal["", "URGENTE", "EXCLUSIVO", "AO VIVO", "ANÁLISE"] = ""


class SlotDestaque(BaseModel):
    """Um slot na zona de destaques."""
    artigo: ArtigoCandidato
    tamanho: Literal["pequeno", "medio", "grande"] = "medio"
    label: str = ""
    posicao: int = 0                     # 0-3 (até 4 destaques)


class ZonaEditoria(BaseModel):
    """Zona de uma editoria específica."""
    editoria: str
    artigos: List[ArtigoCandidato] = []  # 3-5 artigos por editoria
    destaque_editoria: Optional[ArtigoCandidato] = None


class HomepageComposicao(BaseModel):
    """Composição completa da homepage."""
    
    # ZONA 1: Manchete principal
    manchete: Optional[ArtigoCandidato] = None
    manchete_modo: Literal["normal", "amplo", "breaking"] = "normal"
    
    # ZONA 1 Breaking: Artigo de breaking news
    breaking_news: Optional[ArtigoCandidato] = None
    breaking_ativo: bool = False
    
    # ZONA 2: Destaques (2-4 artigos, grid adaptativo)
    destaques: List[SlotDestaque] = []
    
    # ZONA 3: Por editoria (carrosséis)
    por_editoria: Dict[str, ZonaEditoria] = {}
    
    # ZONA 4: Mais lidas (auto-curada por analytics)
    mais_lidas: List[ArtigoCandidato] = []
    
    # ZONA 5: Opinião / Análise
    opiniao: List[ArtigoCandidato] = []
    
    # ZONA 6: Regional
    regional: List[ArtigoCandidato] = []
    
    # Metadados do ciclo
    ciclo_id: str = ""
    layout_atual: Literal["normal", "amplo", "breaking"] = "normal"
    atualizado_em: Optional[datetime] = None
    ciclo_duracao_s: float = 0.0
    total_candidatos_avaliados: int = 0
    llm_provider_usado: str = ""
    llm_model_usado: str = ""


class HomepageState(BaseModel):
    """Estado completo do LangGraph para o Curador Homepage."""
    
    # Input triggers
    trigger: Literal["article_published", "breaking_candidate", "periodic", "force_refresh"] = "periodic"
    artigo_novo: Optional[ArtigoCandidato] = None
    breaking_candidato: Optional[ArtigoCandidato] = None
    
    # Pipeline state
    candidatos: List[ArtigoCandidato] = []
    composicao_proposta: Optional[HomepageComposicao] = None
    composicao_atual: Optional[HomepageComposicao] = None  # Carregada do Redis
    layout_decidido: Literal["normal", "amplo", "breaking"] = "normal"
    
    # Execution
    erros: List[str] = []
    ciclo_id: str = ""
    iniciado_em: Optional[datetime] = None
```

---

## PARTE III — CICLO DE CURADORIA (15-30 MINUTOS)

### 3.1 Frequência e Triggers

O Curador Homepage opera em **dois modos complementares**:

**Modo Reativo** (imediato):
- Kafka `article-published`: novo artigo publicado → avalia se deve entrar na home
- Kafka `breaking-candidate`: Monitor Concorrência detectou breaking → force breaking mode

**Modo Periódico** (15 min):
- Cron a cada 15 minutos → reavalia todos os candidatos
- Garante rotação mesmo se não houver novos artigos
- Evita conteúdo estagnado

**Lógica de frequência adaptativa:**
```python
# brasileira/homepage/scheduler.py

class HomepageCycleScheduler:
    """
    Ajusta frequência do ciclo baseado no estado editorial.
    
    BREAKING MODE: ciclo a cada 5 min (notícias surgem rapidamente)
    ALTA ATIVIDADE: ciclo a cada 15 min (fluxo normal de notícias)
    BAIXA ATIVIDADE (madrugada): ciclo a cada 30 min
    """
    
    BASE_INTERVAL_MIN = 15
    BREAKING_INTERVAL_MIN = 5
    LOW_ACTIVITY_INTERVAL_MIN = 30
    
    # Horários de baixa atividade (horário de Brasília)
    LOW_ACTIVITY_HOURS = range(2, 7)  # 02h00 às 06h59
    
    def get_next_interval(
        self,
        breaking_ativo: bool,
        artigos_ultima_hora: int,
    ) -> int:
        hora_brasilia = datetime.now(tz=ZoneInfo("America/Sao_Paulo")).hour
        
        if breaking_ativo:
            return self.BREAKING_INTERVAL_MIN
        
        if hora_brasilia in self.LOW_ACTIVITY_HOURS and artigos_ultima_hora < 5:
            return self.LOW_ACTIVITY_INTERVAL_MIN
        
        return self.BASE_INTERVAL_MIN
```

### 3.2 Controle de Concorrência (Lock Distribuído)

O V2 não tinha proteção contra execuções simultâneas. A V3 usa **lock Redis** para garantir que apenas um ciclo rode por vez:

```python
# brasileira/agents/curador_homepage.py

import asyncio
from contextlib import asynccontextmanager
import redis.asyncio as aioredis

LOCK_KEY = "curador_homepage:lock"
LOCK_TTL_SECONDS = 120  # Se travar, libera após 2 min


@asynccontextmanager
async def adquirir_lock_ciclo(redis: aioredis.Redis):
    """
    Lock distribuído Redis para evitar ciclos simultâneos.
    
    NUNCA dois ciclos rodam ao mesmo tempo.
    Se lock não conseguido em 5s: skip este ciclo, próximo assumirá.
    """
    lock_acquired = await redis.set(
        LOCK_KEY,
        value="1",
        nx=True,           # Only set if not exists
        ex=LOCK_TTL_SECONDS,
    )
    
    if not lock_acquired:
        raise CicloEmAndamentoError(
            "Curador: ciclo anterior ainda em execução. Pulando este ciclo."
        )
    
    try:
        yield
    finally:
        await redis.delete(LOCK_KEY)
```

### 3.3 Fluxo Completo do Ciclo

```
TRIGGER (artigo publicado / breaking / periódico)
    │
    ▼
[LOCK Redis] — se não conseguir: skip (ciclo anterior ainda rodando)
    │
    ▼
ETAPA 1: COLETAR CANDIDATOS
    ├── GET /wp-json/wp/v2/posts?per_page=50&orderby=date (últimas 4h)
    ├── Filtra: tem imagem? tem editoria válida? não é duplicata?
    ├── Enriquece: CTR das últimas 2h (Redis/Analytics)
    ├── Enriquece: capas_concorrentes (Redis: monitor_concorrencia:capas)
    └── Retorna: List[ArtigoCandidato] ordenados por recência
    │
    ▼
ETAPA 2: SCORE EDITORIAL (LLM PREMIUM)
    ├── Score objetivo local (sem LLM):
    │   ├── +30: fonte Tier 1 (Agência Brasil, G1, Folha)
    │   ├── +20: artigo consolidado (2+ fontes)
    │   ├── +15: urgência FLASH
    │   ├── +10: tem imagem high-res (largura > 800px)
    │   ├── +10: publicado há < 1h
    │   ├── +8: capas_concorrentes >= 2
    │   ├── +5: CTR > 5% nas últimas 2h
    │   ├── -10: sem imagem
    │   ├── -15: conteúdo de nicho sem relevância nacional
    │   └── -5: editoria regional (salvo seção Regional)
    ├── LLM PREMIUM avalia top-20 candidatos (score objetivo >= 20)
    │   └── [ver PARTE V para system prompt completo]
    └── score_total = score_objetivo + score_llm (max: 100+50=150)
    │
    ▼
ETAPA 3: DECIDIR LAYOUT
    ├── BREAKING: score_total > 130 AND capas >= 4 AND publicado < 1h
    ├── AMPLO: score_total > 100 AND capas >= 2
    └── NORMAL: todos os outros casos
    │
    ▼
ETAPA 4: COMPOR ZONAS EDITORIAIS
    ├── Zona 1: Manchete (top-1 por score_total)
    ├── Zona 2: Destaques (top 2-5, diversidade de editorias)
    ├── Zona 3: Por Editoria (3 artigos por categoria, 16 categorias)
    ├── Zona 4: Mais Lidas (por views_1h + CTR, auto-curada)
    ├── Zona 5: Opinião/Análise (filtro por editoria)
    └── Zona 6: Regional (filtro por editoria regional)
    │
    ▼
ETAPA 5: APLICAR (ATOMICAMENTE)
    ├── Carrega composição atual (Redis homepage:current)
    ├── Calcula DIFF: o que mudou?
    ├── PATCH apenas os campos que mudaram (NUNCA clear-all)
    ├── Atualiza ACF Options via WordPress REST API
    └── Atualiza Redis homepage:current
    │
    ▼
ETAPA 6: REGISTRAR
    ├── PostgreSQL: curador_cycles (log histórico)
    ├── Kafka: homepage-updates (notifica Monitor Sistema)
    ├── Memória episódica: decisões para aprendizado futuro
    └── [UNLOCK Redis]
```

---

## PARTE IV — COLETA DE ARTIGOS RECENTES

### 4.1 Query WordPress REST API

```python
# brasileira/homepage/candidatos.py

import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional
import asyncio

from brasileira.homepage.state import ArtigoCandidato
from brasileira.integrations.redis_client import RedisClient


class ColetorCandidatos:
    """
    Coleta artigos candidatos para a homepage.
    
    REGRAS:
    - Janela: últimas 4 horas de artigos publicados
    - Mínimo: 10 candidatos (alargar janela se necessário)
    - Máximo: 50 candidatos para score LLM (top-50 por score objetivo)
    - TODOS os candidatos passam por score objetivo local
    - Apenas top-20 (score objetivo >= 20) passam por LLM
    """
    
    JANELA_HORAS = 4
    MAX_CANDIDATOS = 50
    MIN_CANDIDATOS = 10
    
    def __init__(self, wp_client, redis_client: RedisClient):
        self.wp = wp_client
        self.redis = redis_client
    
    async def coletar(self) -> List[ArtigoCandidato]:
        """
        Coleta e enriquece artigos candidatos para scoring.
        Sempre retorna pelo menos MIN_CANDIDATOS artigos.
        """
        # Data de corte (UTC)
        agora_utc = datetime.now(tz=ZoneInfo("UTC"))
        corte = agora_utc - timedelta(hours=self.JANELA_HORAS)
        
        # Busca no WordPress
        posts = await self._buscar_posts_wp(corte)
        
        # Se poucos posts, alarga a janela até ter o mínimo
        if len(posts) < self.MIN_CANDIDATOS:
            corte_extra = agora_utc - timedelta(hours=self.JANELA_HORAS * 2)
            posts_extra = await self._buscar_posts_wp(corte_extra)
            posts = posts_extra  # Usa a janela maior
        
        # Converte para ArtigoCandidato e enriquece
        candidatos = []
        for post in posts:
            candidato = await self._post_para_candidato(post)
            if candidato:
                candidatos.append(candidato)
        
        # Ordena por score objetivo inicial (para priorizar LLM nos melhores)
        candidatos.sort(key=lambda c: c.score_objetivo, reverse=True)
        
        return candidatos[:self.MAX_CANDIDATOS]
    
    async def _buscar_posts_wp(self, depois_de: datetime) -> list:
        """Busca posts recentes via WordPress REST API."""
        # Formato: 2026-03-26T14:30:00
        after = depois_de.strftime("%Y-%m-%dT%H:%M:%S")
        
        params = {
            "per_page": 50,
            "orderby": "date",
            "order": "desc",
            "status": "publish",
            "after": after,
            "_fields": (
                "id,title,excerpt,date,date_gmt,categories,"
                "featured_media,meta,link,_links,acf"
            ),
        }
        
        try:
            response = await self.wp.get("/wp/v2/posts", params=params)
            return response.json()
        except Exception as e:
            # Nunca travar o ciclo por falha de coleta
            import logging
            logging.getLogger("curador.candidatos").error(
                f"Erro ao buscar posts WP: {e}"
            )
            return []
    
    async def _post_para_candidato(
        self, post: dict
    ) -> Optional[ArtigoCandidato]:
        """
        Converte um post WordPress para ArtigoCandidato.
        Enriquece com métricas do Redis.
        """
        try:
            wp_post_id = post["id"]
            
            # Data de publicação — SEMPRE usar date_gmt para consistência UTC
            publicado_em = datetime.fromisoformat(
                post["date_gmt"].replace("Z", "+00:00")
            )
            
            # Imagem destacada
            imagem_url = None
            imagem_width = 0
            imagem_height = 0
            
            # Tenta pegar imagem dos metadados ACF primeiro
            acf = post.get("acf", {})
            if acf.get("imagem_principal"):
                img_data = acf["imagem_principal"]
                imagem_url = img_data.get("url")
                imagem_width = img_data.get("width", 0)
                imagem_height = img_data.get("height", 0)
            
            # Fallback: featured_media (busca separada se necessário)
            if not imagem_url and post.get("featured_media"):
                imagem_url = await self._get_media_url(post["featured_media"])
            
            # Editoria (da taxonomy do WordPress)
            editoria = await self._resolver_editoria(post)
            
            # Urgência (do meta do post)
            urgencia = post.get("acf", {}).get("urgencia", "NORMAL")
            if urgencia not in ("FLASH", "NORMAL", "ANALISE"):
                urgencia = "NORMAL"
            
            # Métricas em tempo real (Redis, preenchidas pelo Monitor Sistema)
            metricas_key = f"metricas:post:{wp_post_id}"
            metricas_raw = await self.redis.hgetall(metricas_key)
            ctr_atual = float(metricas_raw.get("ctr_2h", 0.0))
            views_1h = int(metricas_raw.get("views_1h", 0))
            
            # Capas de concorrentes (Monitor Concorrência atualiza essa key)
            capas_key = f"monitor_concorrencia:capas:{wp_post_id}"
            capas_concorrentes = int(
                await self.redis.get(capas_key) or 0
            )
            
            return ArtigoCandidato(
                wp_post_id=wp_post_id,
                titulo=post["title"]["rendered"],
                subtitulo=acf.get("subtitulo", ""),
                editoria=editoria,
                urgencia=urgencia,
                url=post["link"],
                imagem_url=imagem_url,
                imagem_width=imagem_width,
                imagem_height=imagem_height,
                fonte_nome=acf.get("fonte_nome", ""),
                publicado_em=publicado_em,
                ctr_atual=ctr_atual,
                views_1h=views_1h,
                capas_concorrentes=capas_concorrentes,
                is_breaking=(urgencia == "FLASH" and capas_concorrentes >= 4),
            )
        
        except Exception as e:
            import logging
            logging.getLogger("curador.candidatos").warning(
                f"Erro ao converter post {post.get('id', '?')}: {e}"
            )
            return None
    
    async def _resolver_editoria(self, post: dict) -> str:
        """
        Resolve a editoria do post.
        Usa campo ACF first, depois taxonomy de categorias WP.
        """
        # ACF field tem prioridade (já normalizado pelo Classificador)
        acf_editoria = post.get("acf", {}).get("editoria_normalizada")
        if acf_editoria:
            return acf_editoria
        
        # Fallback: categoria WP (array de IDs)
        cat_ids = post.get("categories", [])
        if cat_ids:
            # Mapa de category IDs para nomes (cacheado no Redis)
            cat_key = f"wp:category:{cat_ids[0]}"
            cat_nome = await self.redis.get(cat_key)
            if cat_nome:
                return cat_nome
        
        return "brasil"  # Default: editoria Brasil
    
    async def _get_media_url(self, media_id: int) -> Optional[str]:
        """Busca URL da imagem pelo ID de mídia (com cache Redis)."""
        cache_key = f"wp:media:url:{media_id}"
        cached = await self.redis.get(cache_key)
        if cached:
            return cached
        
        try:
            response = await self.wp.get(
                f"/wp/v2/media/{media_id}",
                params={"_fields": "source_url,media_details"},
            )
            data = response.json()
            
            # Prefere tamanho "large" para homepage (melhor qualidade visual)
            sizes = data.get("media_details", {}).get("sizes", {})
            url = (
                sizes.get("large", {}).get("source_url")
                or sizes.get("medium_large", {}).get("source_url")
                or data.get("source_url")
            )
            
            if url:
                await self.redis.setex(cache_key, 3600, url)
            
            return url
        
        except Exception:
            return None
```

### 4.2 Score Objetivo Local (Sem LLM)

```python
# brasileira/homepage/scorer.py — PARTE 1: Score Objetivo

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from brasileira.homepage.state import ArtigoCandidato


# Constantes de score (calibradas para faixa 0-100)
SCORE_FONTE_TIER1 = 30       # Agência Brasil, Reuters, AP, G1, Folha
SCORE_FONTE_TIER2 = 20       # UOL, Estadão, Veja, exame, etc.
SCORE_FONTE_TIER3 = 10       # Fontes secundárias
SCORE_CONSOLIDADO = 20       # Artigo de múltiplas fontes
SCORE_URGENCIA_FLASH = 15    # Urgência máxima
SCORE_URGENCIA_NORMAL = 0    # Score base
SCORE_TEM_IMAGEM = 10        # Tem imagem destacada
SCORE_IMAGEM_HIRES = 5       # Imagem tem largura > 800px (extra)
SCORE_FRESCOR_1H = 10        # Publicado há < 1h
SCORE_FRESCOR_2H = 5         # Publicado há < 2h
SCORE_CAPAS_4MAIS = 12       # 4+ capas de concorrentes
SCORE_CAPAS_2A3 = 8          # 2-3 capas de concorrentes
SCORE_CTR_ALTO = 5           # CTR > 5% nas últimas 2h
SCORE_VIEWS_PICO = 5         # 500+ views na última hora
PENALTY_SEM_IMAGEM = -10     # Sem imagem (homepage visualmente pobre)
PENALTY_REGIONAL = -5        # Conteúdo muito regional (exceto zona Regional)
PENALTY_NICHO = -15          # Conteúdo de nicho sem interesse nacional

# Fontes Tier 1 (máxima credibilidade editorial)
FONTES_TIER1 = {
    "agencia_brasil", "reuters", "ap", "afp", "g1", "folha_de_sao_paulo",
    "o_estado_de_sao_paulo", "valor_economico", "cnn_brasil",
    "bbc_brasil", "the_intercept_brasil"
}

# Fontes Tier 2
FONTES_TIER2 = {
    "uol", "r7", "terra", "metropoles", "veja", "exame",
    "correio_braziliense", "o_globo", "band", "sbt"
}


def calcular_score_objetivo(
    artigo: ArtigoCandidato,
    agora: datetime | None = None,
) -> float:
    """
    Calcula score editorial objetivo (sem LLM).
    Faixa: pode ser negativo. NÃO aplica max(score, 0).
    Posts com score negativo são eliminados antes do LLM.
    
    NOTA: agora deve ser UTC-aware para comparações corretas.
    """
    if agora is None:
        agora = datetime.now(tz=ZoneInfo("UTC"))
    
    score = 0.0
    breakdown = {}
    
    # 1. QUALIDADE DA FONTE
    fonte_slug = artigo.fonte_nome.lower().replace(" ", "_")
    if fonte_slug in FONTES_TIER1:
        score += SCORE_FONTE_TIER1
        breakdown["fonte"] = SCORE_FONTE_TIER1
    elif fonte_slug in FONTES_TIER2:
        score += SCORE_FONTE_TIER2
        breakdown["fonte"] = SCORE_FONTE_TIER2
    else:
        score += SCORE_FONTE_TIER3
        breakdown["fonte"] = SCORE_FONTE_TIER3
    
    # 2. URGÊNCIA
    if artigo.urgencia == "FLASH":
        score += SCORE_URGENCIA_FLASH
        breakdown["urgencia"] = SCORE_URGENCIA_FLASH
    
    # 3. IMAGEM
    if artigo.imagem_url:
        score += SCORE_TEM_IMAGEM
        breakdown["imagem"] = SCORE_TEM_IMAGEM
        if artigo.imagem_width >= 800:
            score += SCORE_IMAGEM_HIRES
            breakdown["imagem_hires"] = SCORE_IMAGEM_HIRES
    else:
        score += PENALTY_SEM_IMAGEM
        breakdown["sem_imagem"] = PENALTY_SEM_IMAGEM
    
    # 4. FRESCOR — usando UTC consistente (BUG V2 corrigido)
    # artigo.publicado_em DEVE ser UTC-aware
    pub_utc = artigo.publicado_em
    if pub_utc.tzinfo is None:
        # Fallback: assume UTC se não tiver tzinfo
        pub_utc = pub_utc.replace(tzinfo=ZoneInfo("UTC"))
    
    idade = agora - pub_utc
    if idade <= timedelta(hours=1):
        score += SCORE_FRESCOR_1H
        breakdown["frescor"] = SCORE_FRESCOR_1H
    elif idade <= timedelta(hours=2):
        score += SCORE_FRESCOR_2H
        breakdown["frescor"] = SCORE_FRESCOR_2H
    
    # 5. CAPAS DE CONCORRENTES
    if artigo.capas_concorrentes >= 4:
        score += SCORE_CAPAS_4MAIS
        breakdown["capas"] = SCORE_CAPAS_4MAIS
    elif artigo.capas_concorrentes >= 2:
        score += SCORE_CAPAS_2A3
        breakdown["capas"] = SCORE_CAPAS_2A3
    
    # 6. MÉTRICAS EM TEMPO REAL
    if artigo.ctr_atual > 5.0:
        score += SCORE_CTR_ALTO
        breakdown["ctr"] = SCORE_CTR_ALTO
    
    if artigo.views_1h >= 500:
        score += SCORE_VIEWS_PICO
        breakdown["views"] = SCORE_VIEWS_PICO
    
    # 7. PENALIDADES
    editorias_regionais = {"regionais", "regional", "municipio", "bairro"}
    if artigo.editoria.lower() in editorias_regionais:
        score += PENALTY_REGIONAL
        breakdown["regional"] = PENALTY_REGIONAL
    
    artigo.score_objetivo = score
    artigo._score_breakdown = breakdown  # Para debug/log
    
    return score
```

---

## PARTE V — SCORING EDITORIAL COM LLM PREMIUM

### 5.1 Estratégia de Avaliação LLM

Apenas os **top-20 candidatos** (score objetivo >= 20) são avaliados pelo LLM PREMIUM. Isso garante:

1. **Custo controlado:** 20 chamadas LLM por ciclo, não 50
2. **Qualidade máxima:** O LLM avalia apenas candidatos pré-qualificados
3. **Tempo adequado:** LLM PREMIUM pode ter 3-8s por chamada; 20 em paralelo = viável
4. **Nunca bloqueia:** Se LLM falha, usa score objetivo (nunca retorna None)

**OBRIGATÓRIO:** O `task_type` para o SmartLLMRouter é `"homepage_scoring"`, que mapeia para Tier PREMIUM. Nunca usar `"analise_metricas"` (PADRÃO) ou `"classificacao_categoria"` (ECONÔMICO).

### 5.2 System Prompt Completo para Scoring Editorial

```python
# brasileira/homepage/scorer.py — PARTE 2: LLM PREMIUM

SYSTEM_PROMPT_SCORING = """Você é o Editor-Chefe de Curadoria da brasileira.news, 
um portal de notícias TIER-1 brasileiro equivalente ao G1 e Folha de S. Paulo.

Sua única função neste contexto é **avaliar a relevância editorial** de artigos 
candidatos para a homepage principal do portal.

## SUA EXPERTISE

Você possui 20 anos de experiência em jornalismo digital brasileiro e conhece:
- O que captura atenção do público brasileiro em 2026
- Quais temas têm impacto nacional vs. regional
- A diferença entre notícia importante e sensacionalismo
- Como balancear cobertura editorial (não deixar uma editoria dominar)
- O valor jornalístico de exclusivos, análises profundas e dados inéditos

## SEU JULGAMENTO EDITORIAL

Para cada artigo candidato, atribua um score de 0 a 50 pontos baseado em:

### Critérios de Alta Pontuação (40-50 pts):
- Impacto nacional imediato: decisões do governo federal, STF, Congresso
- Crises econômicas com efeito imediato no bolso do cidadão (câmbio, inflação, combustível)
- Catástrofes e emergências de amplo alcance
- Exclusivos com documentos ou fontes primárias
- Resultado de eleições, votações decisivas
- Breaking news verificada por múltiplas fontes
- Temas que dominam o debate público nacional

### Critérios de Pontuação Média (20-39 pts):
- Notícias políticas relevantes sem caráter de urgência imediata
- Economia com impacto médio prazo
- Esportes de repercussão nacional (Copa, seleção, final de campeonato)
- Cultura e entretenimento com grande audiência
- Ciência e saúde de interesse amplo
- Temas internacionais com reflexo direto no Brasil

### Critérios de Baixa Pontuação (0-19 pts):
- Notícias regionais sem interesse nacional
- Fofoca de celebridade ou entretenimento frívolo
- Repetição de pauta já cobertura exaustivamente nas últimas 24h
- Conteúdo de nicho com público muito restrito
- Opinião sem fato jornalístico novo
- Temas internacionais sem conexão com o Brasil

## REGRAS DE AVALIAÇÃO

1. **Seja objetivo:** Não deixe preferências pessoais influenciarem o score.
2. **Considere o contexto:** Um artigo sobre futebol pode valer 45 pts na véspera da Copa.
3. **Priorize impacto imediato:** Uma notícia publicada há 20 min com impacto médio > uma análise profunda de 3h atrás.
4. **Diversidade editorial:** Penalize levemente artigos que representam mais uma notícia de editoria já bem representada.
5. **Verifique a fonte:** Fontes primárias (governo, empresas, tribunais) valem mais que secundárias.
6. **Identifique breaking:** Se o artigo descreve um evento que acabou de ocorrer e tem impacto nacional, sinalize como breaking.

## FORMATO DE RESPOSTA

Responda SOMENTE em JSON válido, sem texto adicional:

```json
{
  "scores": [
    {
      "wp_post_id": 12345,
      "score_llm": 42,
      "justificativa": "Decisão do STF que afeta todos os trabalhadores com carteira assinada. Impacto imediato e nacional. Fonte primária (Supremo).",
      "e_breaking": false,
      "label_sugerido": "",
      "editoria_confirmada": "politica"
    },
    {
      "wp_post_id": 67890,
      "score_llm": 12,
      "justificativa": "Estreia de filme nacional. Interesse cultural limitado para a home principal.",
      "e_breaking": false,
      "label_sugerido": "",
      "editoria_confirmada": "cultura"
    }
  ]
}
```

Campos:
- `wp_post_id`: ID do post (use o mesmo valor recebido)
- `score_llm`: 0 a 50 (inteiro)
- `justificativa`: 1-2 frases explicando o score (para auditoria)
- `e_breaking`: true se for breaking news nacional urgente
- `label_sugerido`: "" | "URGENTE" | "EXCLUSIVO" | "AO VIVO" | "ANÁLISE"
- `editoria_confirmada`: editoria correta se diferente da informada (ou a mesma)

IMPORTANTE: Avalie TODOS os artigos fornecidos. Não omita nenhum ID.
"""


USER_PROMPT_SCORING_TEMPLATE = """Avalie os seguintes {n} artigos candidatos para a homepage da brasileira.news.

## CONTEXTO DO MOMENTO ATUAL
- Data/hora atual: {agora_brasilia}
- Artigos em destaque nas homepages concorrentes (G1, UOL, Folha): {temas_concorrentes}
- Breaking news ativa no momento: {breaking_ativo}

## ARTIGOS CANDIDATOS

{artigos_json}

Responda com o JSON de scores para TODOS os {n} artigos acima.
"""


async def score_llm_batch(
    candidatos: list,
    router,  # SmartLLMRouter
    temas_concorrentes: list[str],
    breaking_ativo: bool,
) -> dict:
    """
    Avalia candidatos com LLM PREMIUM em batch.
    
    Retorna dict: {wp_post_id: {"score_llm": X, "label": Y, "e_breaking": Z}}
    Se LLM falha: retorna dict com score_llm=0 para todos (não bloqueia).
    """
    from zoneinfo import ZoneInfo
    import json
    
    agora_brasilia = datetime.now(
        tz=ZoneInfo("America/Sao_Paulo")
    ).strftime("%d/%m/%Y %H:%M")
    
    # Prepara lista compacta para o LLM (sem informações desnecessárias)
    artigos_para_llm = []
    for c in candidatos:
        artigos_para_llm.append({
            "wp_post_id": c.wp_post_id,
            "titulo": c.titulo,
            "editoria": c.editoria,
            "urgencia": c.urgencia,
            "fonte": c.fonte_nome,
            "publicado_ha_min": int(
                (datetime.now(tz=ZoneInfo("UTC")) - c.publicado_em).total_seconds() / 60
            ),
            "capas_concorrentes": c.capas_concorrentes,
            "ctr_pct": round(c.ctr_atual, 1),
        })
    
    user_prompt = USER_PROMPT_SCORING_TEMPLATE.format(
        n=len(candidatos),
        agora_brasilia=agora_brasilia,
        temas_concorrentes=", ".join(temas_concorrentes[:10]) or "Nenhum disponível",
        breaking_ativo="SIM" if breaking_ativo else "Não",
        artigos_json=json.dumps(artigos_para_llm, ensure_ascii=False, indent=2),
    )
    
    try:
        resultado = await router.call(
            task_type="homepage_scoring",  # → Tier PREMIUM obrigatório
            system_prompt=SYSTEM_PROMPT_SCORING,
            user_prompt=user_prompt,
            response_format="json_object",
            max_tokens=2000,
        )
        
        data = json.loads(resultado)
        scores = {
            item["wp_post_id"]: {
                "score_llm": min(50, max(0, item["score_llm"])),
                "justificativa": item.get("justificativa", ""),
                "e_breaking": item.get("e_breaking", False),
                "label": item.get("label_sugerido", ""),
                "editoria_confirmada": item.get("editoria_confirmada", ""),
            }
            for item in data.get("scores", [])
        }
        return scores
    
    except Exception as e:
        import logging
        logging.getLogger("curador.scorer").error(
            f"LLM PREMIUM falhou no scoring: {e}. Usando apenas score objetivo."
        )
        # Graceful fallback: retorna score_llm=0 para todos
        return {c.wp_post_id: {"score_llm": 0, "e_breaking": False, "label": ""} 
                for c in candidatos}


async def aplicar_scores(
    candidatos: list,
    router,
    temas_concorrentes: list[str],
    breaking_ativo: bool,
) -> list:
    """
    Pipeline completo de scoring:
    1. Calcula score objetivo para TODOS
    2. Seleciona top-20 (score_objetivo >= 20) para LLM
    3. Aplica LLM PREMIUM nos top-20
    4. Combina scores e ordena
    """
    agora_utc = datetime.now(tz=ZoneInfo("UTC"))
    
    # Score objetivo para todos
    for c in candidatos:
        calcular_score_objetivo(c, agora=agora_utc)
    
    # Filtra candidatos para LLM (score_objetivo >= 20, máximo 20)
    para_llm = [c for c in candidatos if c.score_objetivo >= 20][:20]
    
    # Avalia com LLM PREMIUM
    scores_llm = {}
    if para_llm:
        scores_llm = await score_llm_batch(
            para_llm, router, temas_concorrentes, breaking_ativo
        )
    
    # Aplica scores LLM e calcula score_total
    for c in candidatos:
        if c.wp_post_id in scores_llm:
            llm_data = scores_llm[c.wp_post_id]
            c.score_llm = llm_data["score_llm"]
            if llm_data.get("e_breaking"):
                c.is_breaking = True
            if llm_data.get("label"):
                c.label = llm_data["label"]
            if llm_data.get("editoria_confirmada"):
                c.editoria = llm_data["editoria_confirmada"]
        
        c.score_total = c.score_objetivo + c.score_llm
    
    # Ordena por score_total descrescente
    candidatos.sort(key=lambda c: c.score_total, reverse=True)
    
    return candidatos
```

---

## PARTE VI — 6 ZONAS EDITORIAIS

### 6.1 Mapa Visual das 6 Zonas

```
┌──────────────────────────────────────────────────────────────────────┐
│ ZONA 1: MANCHETE PRINCIPAL                                            │
│                                                                       │
│ MODO NORMAL:                     MODO BREAKING NEWS:                  │
│ ┌───────────────────┐ ┌───────┐  ┌───────────────────────────────────┐│
│ │                   │ │SIDE   │  │  ████ BREAKING NEWS ████          ││
│ │  MANCHETE         │ │BAR    │  │                                    ││
│ │  com foto         │ │1/3    │  │  [Título da notícia urgente]       ││
│ │  2/3              │ │       │  │  Full-width, banner vermelho       ││
│ └───────────────────┘ └───────┘  └───────────────────────────────────┘│
│                                                                       │
│ MODO AMPLO:                                                           │
│ ┌────────────────────────────────────────────────────────────────────┐│
│ │  MANCHETE  —  foto maior, sem sidebar  —  destaque máximo          ││
│ └────────────────────────────────────────────────────────────────────┘│
├───────────────────────────────────────────────────────────────────────┤
│ ZONA 2: DESTAQUES (2-4 artigos, grid adaptativo)                      │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                  │
│ │GRANDE    │ │MÉDIO     │ │MÉDIO     │ │PEQUENO   │                  │
│ │(1 col)   │ │(1 col)   │ │(1 col)   │ │(0.5 col) │                  │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘                  │
├───────────────────────────────────────────────────────────────────────┤
│ ZONA 3: POR EDITORIA (carrosséis horizontais com scroll)              │
│ [Política ›]  [Economia ›]  [Esportes ›]  [Tecnologia ›]  [Saúde ›]  │
├───────────────────────────────────────────────────────────────────────┤
│ ZONA 4: MAIS LIDAS (auto-curada por analytics)                        │
│ 1. [título] — views   2. [título] — views   3. [título] — views       │
├───────────────────────────────────────────────────────────────────────┤
│ ZONA 5: OPINIÃO / ANÁLISE                                             │
│ [Artigo 1] [Artigo 2] [Artigo 3]                                      │
├───────────────────────────────────────────────────────────────────────┤
│ ZONA 6: REGIONAL                                                      │
│ [São Paulo] [Rio] [Minas] [Bahia] [RS]                                │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.2 Regras de Composição por Zona

```python
# brasileira/homepage/compositor.py

from brasileira.homepage.state import (
    ArtigoCandidato, HomepageComposicao, SlotDestaque, ZonaEditoria
)


# Editorias que aparecem na Zona 3 (ordem de exibição)
EDITORIAS_ZONA3 = [
    "politica", "economia", "esportes", "tecnologia",
    "saude", "educacao", "mundo", "meio_ambiente",
    "seguranca", "ciencia", "cultura", "sociedade",
]

# Editorias de Opinião
EDITORIAS_OPINIAO = {"opiniao", "analise", "coluna"}

# Editorias Regionais
EDITORIAS_REGIONAL = {"regionais", "regional", "municipio"}

# Max artigos por editoria em Zona 3
MAX_ARTIGOS_ZONA3 = 5
# Max artigos em Mais Lidas (Zona 4)
MAX_MAIS_LIDAS = 8
# Max artigos em Opinião (Zona 5)
MAX_OPINIAO = 4
# Max artigos em Regional (Zona 6)
MAX_REGIONAL = 5
# Max destaques (Zona 2)
MAX_DESTAQUES = 4
# Max artigos da mesma editoria nos destaques (Zona 2)
MAX_DESTAQUES_POR_EDITORIA = 1


class Compositor:
    """
    Monta as 6 zonas editoriais da homepage.
    
    Princípios:
    - Diversidade: sem dominância de uma editoria
    - Frescor: prioriza artigos mais recentes em score igual
    - Cobertura: todas as editorias representadas na Zona 3
    - Qualidade: imagem obrigatória para Manchete e Destaques
    """
    
    def compor(
        self,
        candidatos: list[ArtigoCandidato],
        layout: str,  # "normal" | "amplo" | "breaking"
        breaking_candidato: ArtigoCandidato | None = None,
    ) -> HomepageComposicao:
        """Monta a composição completa da homepage."""
        
        composicao = HomepageComposicao(
            layout_atual=layout,
            atualizado_em=datetime.now(tz=ZoneInfo("UTC")),
        )
        
        # BREAKING NEWS: tem prioridade absoluta
        if layout == "breaking" and breaking_candidato:
            composicao.breaking_ativo = True
            composicao.breaking_news = breaking_candidato
            composicao.manchete_modo = "breaking"
            # Manchete secundária = próximo melhor candidato
            restantes = [c for c in candidatos if c.wp_post_id != breaking_candidato.wp_post_id]
            composicao.manchete = self._selecionar_manchete(restantes)
            candidatos_para_zonas = restantes
        else:
            composicao.breaking_ativo = False
            composicao.manchete_modo = layout  # "normal" ou "amplo"
            composicao.manchete = self._selecionar_manchete(candidatos)
            candidatos_para_zonas = candidatos
        
        # Remove a manchete do pool de candidatos
        if composicao.manchete:
            candidatos_para_zonas = [
                c for c in candidatos_para_zonas 
                if c.wp_post_id != composicao.manchete.wp_post_id
            ]
        
        # ZONA 2: Destaques (diversidade editorial)
        composicao.destaques = self._selecionar_destaques(candidatos_para_zonas)
        ids_destaques = {s.artigo.wp_post_id for s in composicao.destaques}
        candidatos_restantes = [c for c in candidatos_para_zonas if c.wp_post_id not in ids_destaques]
        
        # ZONA 3: Por editoria
        composicao.por_editoria = self._compor_editorias(candidatos_restantes)
        
        # ZONA 4: Mais lidas (por views + CTR, não por score editorial)
        composicao.mais_lidas = self._selecionar_mais_lidas(candidatos)
        
        # ZONA 5: Opinião
        composicao.opiniao = self._selecionar_opiniao(candidatos)
        
        # ZONA 6: Regional
        composicao.regional = self._selecionar_regional(candidatos)
        
        return composicao
    
    def _selecionar_manchete(
        self, 
        candidatos: list[ArtigoCandidato],
    ) -> ArtigoCandidato | None:
        """
        Seleciona a manchete.
        
        OBRIGATÓRIO: a manchete DEVE ter imagem.
        Critério: maior score_total entre candidatos com imagem.
        """
        com_imagem = [c for c in candidatos if c.imagem_url]
        if not com_imagem:
            # Fallback: sem imagem (situação excepcional)
            return candidatos[0] if candidatos else None
        return com_imagem[0]  # Já ordenados por score_total desc
    
    def _selecionar_destaques(
        self,
        candidatos: list[ArtigoCandidato],
    ) -> list[SlotDestaque]:
        """
        Seleciona destaques com diversidade editorial.
        
        Regra: máximo MAX_DESTAQUES_POR_EDITORIA artigos da mesma editoria.
        Tamanho: primeiro destaque = grande, outros = médio.
        """
        selecionados = []
        editoria_count: dict[str, int] = {}
        
        for candidato in candidatos:
            if len(selecionados) >= MAX_DESTAQUES:
                break
            
            editoria = candidato.editoria
            if editoria_count.get(editoria, 0) >= MAX_DESTAQUES_POR_EDITORIA:
                continue
            
            # Prefere candidatos com imagem
            if not candidato.imagem_url and len(selecionados) < 2:
                continue  # Os 2 primeiros destaques DEVEM ter imagem
            
            tamanho = "grande" if len(selecionados) == 0 else "medio"
            label = candidato.label or ""
            
            selecionados.append(SlotDestaque(
                artigo=candidato,
                tamanho=tamanho,
                label=label,
                posicao=len(selecionados),
            ))
            editoria_count[editoria] = editoria_count.get(editoria, 0) + 1
        
        return selecionados
    
    def _compor_editorias(
        self,
        candidatos: list[ArtigoCandidato],
    ) -> dict[str, ZonaEditoria]:
        """
        Agrupa candidatos por editoria para a Zona 3.
        Garante que cada editoria tenha pelo menos 1 artigo.
        """
        por_editoria: dict[str, list] = {}
        
        for c in candidatos:
            editoria = c.editoria
            if editoria not in por_editoria:
                por_editoria[editoria] = []
            if len(por_editoria[editoria]) < MAX_ARTIGOS_ZONA3:
                por_editoria[editoria].append(c)
        
        resultado = {}
        for editoria in EDITORIAS_ZONA3:
            artigos = por_editoria.get(editoria, [])
            destaque = artigos[0] if artigos else None
            resultado[editoria] = ZonaEditoria(
                editoria=editoria,
                artigos=artigos,
                destaque_editoria=destaque,
            )
        
        return resultado
    
    def _selecionar_mais_lidas(
        self,
        candidatos: list[ArtigoCandidato],
    ) -> list[ArtigoCandidato]:
        """
        Zona 4: ordena por engajamento (views + CTR), não por score editorial.
        Diversidade editorial ainda se aplica.
        """
        # Score de engajamento: views normalizadas + CTR ponderado
        def engajamento(c: ArtigoCandidato) -> float:
            views_score = min(c.views_1h / 100, 10.0)  # Cap em 10 pts
            ctr_score = min(c.ctr_atual, 10.0)          # Cap em 10 pts
            return views_score + ctr_score
        
        ordenados = sorted(candidatos, key=engajamento, reverse=True)
        return ordenados[:MAX_MAIS_LIDAS]
    
    def _selecionar_opiniao(
        self,
        candidatos: list[ArtigoCandidato],
    ) -> list[ArtigoCandidato]:
        """Zona 5: apenas editorias de opinião/análise."""
        opiniao = [c for c in candidatos if c.editoria in EDITORIAS_OPINIAO]
        return opiniao[:MAX_OPINIAO]
    
    def _selecionar_regional(
        self,
        candidatos: list[ArtigoCandidato],
    ) -> list[ArtigoCandidato]:
        """Zona 6: apenas editorias regionais."""
        regional = [c for c in candidatos if c.editoria in EDITORIAS_REGIONAL]
        return regional[:MAX_REGIONAL]
```

---

## PARTE VII — DECISÃO DE LAYOUT (NORMAL / AMPLO / BREAKING)

### 7.1 Matriz de Decisão de Layout

| Condição | Layout | Justificativa |
|----------|--------|---------------|
| `score_total > 130` AND `capas_concorrentes >= 4` AND `publicado_em < 1h` | **BREAKING** | Evento de máxima urgência nacional |
| `is_breaking == True` (sinalizado pelo LLM) | **BREAKING** | LLM confirmou breaking news |
| Kafka `breaking-candidate` recebido | **BREAKING** | Monitor Concorrência detectou |
| `score_total > 100` AND `capas_concorrentes >= 2` | **AMPLO** | Grande destaque editorial |
| `score_total > 85` AND `urgencia == "FLASH"` | **AMPLO** | Urgência alta com relevância confirmada |
| Todos os outros casos | **NORMAL** | Layout padrão cotidiano |

### 7.2 Código de Decisão de Layout

```python
# brasileira/homepage/layout.py

from brasileira.homepage.state import ArtigoCandidato
from typing import Literal


LayoutTipo = Literal["normal", "amplo", "breaking"]


class DecidorLayout:
    """
    Decide o layout da homepage baseado no artigo mais importante.
    
    NUNCA usa modelo econômico. A lógica é determinística, baseada
    em scores calculados pelo LLM PREMIUM na etapa anterior.
    """
    
    # Thresholds de decisão
    BREAKING_SCORE_MIN = 130        # Score total mínimo para breaking
    BREAKING_CAPAS_MIN = 4          # Capas de concorrentes mínimas para breaking
    BREAKING_IDADE_MAX_MIN = 60     # Publicado há no máximo 60 min para breaking
    
    AMPLO_SCORE_MIN = 100           # Score total mínimo para amplo
    AMPLO_CAPAS_MIN = 2             # Capas mínimas para amplo
    AMPLO_FLASH_SCORE_MIN = 85      # Score com urgência FLASH para amplo
    
    # Quanto tempo o modo breaking pode durar sem renovação
    BREAKING_MAX_DURACAO_MIN = 120  # 2 horas máximo
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def decidir(
        self,
        manchete: ArtigoCandidato | None,
        breaking_candidato: ArtigoCandidato | None,
        layout_anterior: LayoutTipo,
    ) -> LayoutTipo:
        """
        Decide o layout para o ciclo atual.
        
        Prioridade:
        1. Breaking candidato externo (Monitor Concorrência)
        2. Manchete com critérios de breaking
        3. Manchete com critérios de amplo
        4. Normal (default)
        """
        
        # 1. Breaking candidato externo (máxima prioridade)
        if breaking_candidato:
            return "breaking"
        
        if manchete is None:
            return "normal"
        
        agora_utc = datetime.now(tz=ZoneInfo("UTC"))
        
        # Garante que publicado_em é UTC-aware
        pub = manchete.publicado_em
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=ZoneInfo("UTC"))
        
        idade_min = (agora_utc - pub).total_seconds() / 60
        
        # 2. Breaking: LLM confirmou + thresholds numéricos
        if manchete.is_breaking:
            if idade_min <= self.BREAKING_IDADE_MAX_MIN:
                return "breaking"
            # Passou do tempo → rebaixa para amplo
        
        # 3. Breaking: thresholds numéricos
        if (
            manchete.score_total >= self.BREAKING_SCORE_MIN
            and manchete.capas_concorrentes >= self.BREAKING_CAPAS_MIN
            and idade_min <= self.BREAKING_IDADE_MAX_MIN
        ):
            return "breaking"
        
        # 4. Amplo: score alto + capas
        if (
            manchete.score_total >= self.AMPLO_SCORE_MIN
            and manchete.capas_concorrentes >= self.AMPLO_CAPAS_MIN
        ):
            return "amplo"
        
        # 5. Amplo: urgência FLASH com score alto
        if (
            manchete.urgencia == "FLASH"
            and manchete.score_total >= self.AMPLO_FLASH_SCORE_MIN
        ):
            return "amplo"
        
        # 6. Verificar se deve expirar breaking anterior
        if layout_anterior == "breaking":
            duracao_breaking_min = await self._duracao_breaking()
            if duracao_breaking_min > self.BREAKING_MAX_DURACAO_MIN:
                return "normal"  # Breaking expirou
            # Mantém breaking se ainda recente
            return "breaking"
        
        return "normal"
    
    async def _duracao_breaking(self) -> float:
        """Retorna minutos desde que breaking foi ativado."""
        inicio_key = "homepage:breaking_inicio"
        inicio_str = await self.redis.get(inicio_key)
        
        if not inicio_str:
            return 0.0
        
        inicio = datetime.fromisoformat(inicio_str)
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=ZoneInfo("UTC"))
        
        return (datetime.now(tz=ZoneInfo("UTC")) - inicio).total_seconds() / 60
```

### 7.3 Sinais de Métricas para Decisão de Troca

A decisão de trocar artigos na homepage não é apenas de ciclo a ciclo. Sinais de métricas em tempo real também disparam ações:

| Sinal | Threshold | Ação |
|-------|-----------|------|
| CTR > 5% | Qualquer zona | Manter ou promover para zona superior |
| CTR < 1% por 30 min | Manchete | Rebaixar para destaque, promover próximo |
| Bounce > 70% | Manchete | Registrar como candidato fraco (memória episódica) |
| Tempo médio > 5 min | Qualquer | Marcar para "Mais Lidas" |
| 0 cliques em 30 min | Qualquer destaque | Substituir no próximo ciclo |
| Pico de tráfego externo em tema | Detecção via Redis | Promover matéria sobre o tema |
| Views delta > 300% em 10 min | Qualquer artigo | Promover para destaque urgente |

```python
# brasileira/homepage/metricas.py

class MonitorMetricasHomepage:
    """
    Monitora métricas em tempo real e sinaliza necessidade de refresh.
    
    Roda em background (ciclo de 2 min), separado do ciclo principal.
    Se detectar anomalia, publica em Redis: homepage:force_refresh = "1"
    """
    
    REFRESH_INTERVAL_S = 120       # Verifica a cada 2 min
    CTR_MUITO_BAIXO = 1.0          # % — abaixo disso é ruim
    MINUTOS_SEM_CLIQUE_ALERT = 30  # Artigo sem clique por 30 min
    VIEWS_PICO_THRESHOLD = 300     # % de aumento para considerar viral
    
    async def verificar_e_alertar(self, redis, composicao_atual: HomepageComposicao):
        """
        Verifica métricas do artigo na manchete atual.
        Se performance ruim: sinaliza force_refresh no Redis.
        """
        if not composicao_atual.manchete:
            return
        
        manchete_id = composicao_atual.manchete.wp_post_id
        metricas_key = f"metricas:post:{manchete_id}"
        metricas = await redis.hgetall(metricas_key)
        
        ctr_atual = float(metricas.get("ctr_30min", 0.0))
        clicks_30min = int(metricas.get("clicks_30min", 0))
        
        # Manchete sem clique por 30 min → force refresh
        if clicks_30min == 0:
            await redis.set("homepage:force_refresh", "1", ex=300)
            return
        
        # CTR muito baixo → force refresh
        if ctr_atual < self.CTR_MUITO_BAIXO:
            await redis.set("homepage:force_refresh", "1", ex=300)
```

---

## PARTE VIII — ACF OPTIONS E WORDPRESS REST API

### 8.1 Estrutura Completa de Campos ACF

Os campos ACF Options controlam toda a homepage. Abaixo o mapeamento completo:

```php
<?php
// brasileira/wordpress/acf-setup.php
// Registrar campos ACF Options para a homepage V3

add_action('acf/init', function () {
    if (!function_exists('acf_add_options_page')) {
        return;
    }

    // Página de opções da homepage
    acf_add_options_page([
        'page_title' => 'Configurações da Homepage',
        'menu_title' => 'Homepage',
        'menu_slug'  => 'homepage-settings',
        'capability' => 'edit_posts',
        'redirect'   => false,
        'icon_url'   => 'dashicons-layout',
    ]);
});

// Definição dos campos via acf_add_local_field_group
add_action('acf/init', function () {
    acf_add_local_field_group([
        'key'    => 'group_homepage_v3',
        'title'  => 'Homepage V3 — Curador',
        'fields' => [

            // ── ZONA 1: MANCHETE ───────────────────────────────────────────

            [
                'key'   => 'field_manchete_modo',
                'label' => 'Modo da Manchete',
                'name'  => 'manchete_modo',
                'type'  => 'select',
                'choices' => [
                    'normal'   => 'Normal (2/3 + sidebar 1/3)',
                    'amplo'    => 'Amplo (sem sidebar)',
                    'breaking' => 'Breaking News (full-width)',
                ],
                'default_value' => 'normal',
            ],
            [
                'key'   => 'field_manchete_post_id',
                'label' => 'Manchete — Post ID',
                'name'  => 'manchete_post_id',
                'type'  => 'number',
                'min'   => 0,
            ],
            [
                'key'   => 'field_manchete_label',
                'label' => 'Manchete — Label',
                'name'  => 'manchete_label',
                'type'  => 'select',
                'choices' => [
                    ''         => 'Sem label',
                    'URGENTE'  => 'URGENTE',
                    'EXCLUSIVO'=> 'EXCLUSIVO',
                    'AO VIVO'  => 'AO VIVO',
                    'ANÁLISE'  => 'ANÁLISE',
                ],
            ],

            // ── BREAKING NEWS ──────────────────────────────────────────────

            [
                'key'   => 'field_breaking_ativo',
                'label' => 'Breaking News — Ativo',
                'name'  => 'breaking_ativo',
                'type'  => 'true_false',
                'default_value' => 0,
            ],
            [
                'key'   => 'field_breaking_post_id',
                'label' => 'Breaking News — Post ID',
                'name'  => 'breaking_post_id',
                'type'  => 'number',
                'min'   => 0,
            ],
            [
                'key'   => 'field_breaking_titulo_manual',
                'label' => 'Breaking — Título Manual (opcional)',
                'name'  => 'breaking_titulo_manual',
                'type'  => 'text',
                'instructions' => 'Deixe vazio para usar o título do post.',
            ],

            // ── ZONA 2: DESTAQUES ──────────────────────────────────────────

            [
                'key'    => 'field_destaques',
                'label'  => 'Destaques (Zona 2)',
                'name'   => 'destaques',
                'type'   => 'repeater',
                'min'    => 0,
                'max'    => 4,
                'layout' => 'table',
                'sub_fields' => [
                    [
                        'key'   => 'field_destaque_post_id',
                        'label' => 'Post ID',
                        'name'  => 'post_id',
                        'type'  => 'number',
                    ],
                    [
                        'key'     => 'field_destaque_tamanho',
                        'label'   => 'Tamanho',
                        'name'    => 'tamanho',
                        'type'    => 'select',
                        'choices' => [
                            'pequeno' => 'Pequeno (0.5 col)',
                            'medio'   => 'Médio (1 col)',
                            'grande'  => 'Grande (1.5 col)',
                        ],
                    ],
                    [
                        'key'     => 'field_destaque_label',
                        'label'   => 'Label',
                        'name'    => 'label',
                        'type'    => 'select',
                        'choices' => [
                            ''         => 'Sem label',
                            'URGENTE'  => 'URGENTE',
                            'EXCLUSIVO'=> 'EXCLUSIVO',
                            'AO VIVO'  => 'AO VIVO',
                        ],
                    ],
                ],
            ],

            // ── ZONA 3: EDITORIAS ──────────────────────────────────────────
            // Gerado para cada uma das 16 editorias
            // Padrão: editoria_{slug}_posts (array de post IDs)

            // Exemplo para Política:
            [
                'key'   => 'field_editoria_politica_posts',
                'label' => 'Política — Posts (IDs)',
                'name'  => 'editoria_politica_posts',
                'type'  => 'textarea',  // JSON array de IDs
                'instructions' => 'JSON: [123, 456, 789]',
            ],
            // ... repetido para cada uma das 16 editorias

            // ── ZONA 4: MAIS LIDAS ─────────────────────────────────────────

            [
                'key'   => 'field_mais_lidas_posts',
                'label' => 'Mais Lidas — Posts (IDs)',
                'name'  => 'mais_lidas_posts',
                'type'  => 'textarea',
                'instructions' => 'JSON: [id1, id2, ...] — até 8 posts',
            ],

            // ── METADADOS DO CICLO ─────────────────────────────────────────

            [
                'key'   => 'field_curador_ciclo_id',
                'label' => 'Último Ciclo ID',
                'name'  => 'curador_ciclo_id',
                'type'  => 'text',
                'readonly' => 1,
            ],
            [
                'key'   => 'field_curador_atualizado_em',
                'label' => 'Última Atualização',
                'name'  => 'curador_atualizado_em',
                'type'  => 'text',
                'readonly' => 1,
            ],
        ],
        'location' => [
            [
                [
                    'param'    => 'options_page',
                    'operator' => '==',
                    'value'    => 'homepage-settings',
                ],
            ],
        ],
    ]);
});
```

### 8.2 Cliente WordPress para ACF Options (Python)

```python
# brasileira/homepage/aplicador.py

import asyncio
import json
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from brasileira.homepage.state import HomepageComposicao


# Endpoint ACF Options Page
ACF_OPTIONS_ENDPOINT = "/acf/v3/options/homepage-settings"


class AplicadorHomepage:
    """
    Aplica a composição da homepage no WordPress via ACF Options.
    
    PRINCÍPIO FUNDAMENTAL: Diff atômico.
    NUNCA limpa tudo e reaplicar.
    SEMPRE calcula diferença e atualiza apenas o que mudou.
    Isso elimina a janela de homepage vazia do V2.
    """
    
    def __init__(self, wp_client, redis_client):
        self.wp = wp_client
        self.redis = redis_client
    
    async def aplicar(
        self,
        composicao: HomepageComposicao,
        composicao_anterior: HomepageComposicao | None,
    ) -> bool:
        """
        Aplica a composição no WordPress.
        
        Retorna True se aplicou com sucesso.
        Nunca lança exceção — log + retorna False se falhar.
        """
        try:
            # Serializa a nova composição para campos ACF
            campos_novos = self._serializar_para_acf(composicao)
            
            # Se há composição anterior, calcula diff (otimização)
            if composicao_anterior:
                campos_anteriores = self._serializar_para_acf(composicao_anterior)
                campos_para_atualizar = {
                    k: v
                    for k, v in campos_novos.items()
                    if v != campos_anteriores.get(k)
                }
            else:
                # Primeira aplicação: atualiza tudo
                campos_para_atualizar = campos_novos
            
            if not campos_para_atualizar:
                import logging
                logging.getLogger("curador.aplicador").info(
                    "Homepage já está atualizada. Nenhuma mudança necessária."
                )
                return True
            
            # Atualiza via ACF REST API
            # NOTA: ACF Options usa POST para atualização (não PATCH)
            response = await self.wp.post(
                ACF_OPTIONS_ENDPOINT,
                json={"fields": campos_para_atualizar},
            )
            
            if response.status_code not in (200, 201):
                raise Exception(
                    f"WordPress retornou {response.status_code}: {response.text[:200]}"
                )
            
            # Atualiza Redis com o estado atual
            await self.redis.setex(
                "homepage:current",
                1800,  # 30 min TTL
                composicao.model_dump_json(),
            )
            
            # Se layout mudou para/de breaking: registra no Redis
            if composicao.breaking_ativo:
                inicio_key = "homepage:breaking_inicio"
                if not await self.redis.exists(inicio_key):
                    await self.redis.set(
                        inicio_key,
                        datetime.now(tz=ZoneInfo("UTC")).isoformat(),
                        ex=7200,  # 2h
                    )
            else:
                await self.redis.delete("homepage:breaking_inicio")
            
            return True
        
        except Exception as e:
            import logging
            logging.getLogger("curador.aplicador").error(
                f"Erro ao aplicar homepage no WordPress: {e}"
            )
            return False
    
    def _serializar_para_acf(self, c: HomepageComposicao) -> dict:
        """
        Converte HomepageComposicao para campos ACF Options.
        """
        campos = {}
        
        # ZONA 1: Manchete
        campos["manchete_modo"] = c.manchete_modo
        campos["manchete_post_id"] = c.manchete.wp_post_id if c.manchete else 0
        campos["manchete_label"] = c.manchete.label if c.manchete else ""
        
        # Breaking News
        campos["breaking_ativo"] = 1 if c.breaking_ativo else 0
        campos["breaking_post_id"] = c.breaking_news.wp_post_id if c.breaking_news else 0
        
        # ZONA 2: Destaques (repeater)
        destaques_data = []
        for slot in c.destaques:
            destaques_data.append({
                "post_id": slot.artigo.wp_post_id,
                "tamanho": slot.tamanho,
                "label": slot.label,
            })
        campos["destaques"] = destaques_data
        
        # ZONA 3: Editorias
        for editoria, zona in c.por_editoria.items():
            ids = [a.wp_post_id for a in zona.artigos]
            campos[f"editoria_{editoria}_posts"] = json.dumps(ids)
        
        # ZONA 4: Mais lidas
        campos["mais_lidas_posts"] = json.dumps(
            [a.wp_post_id for a in c.mais_lidas]
        )
        
        # Metadados do ciclo
        campos["curador_ciclo_id"] = c.ciclo_id
        campos["curador_atualizado_em"] = (
            c.atualizado_em.isoformat() if c.atualizado_em else ""
        )
        
        return campos
    
    async def carregar_composicao_atual(self) -> HomepageComposicao | None:
        """
        Carrega composição atual do Redis.
        Fallback: busca no WordPress (mais lento).
        """
        cached = await self.redis.get("homepage:current")
        if cached:
            try:
                return HomepageComposicao.model_validate_json(cached)
            except Exception:
                pass
        
        # Fallback: busca do WordPress (primeira execução ou cache expirado)
        try:
            response = await self.wp.get(ACF_OPTIONS_ENDPOINT)
            if response.status_code == 200:
                data = response.json()
                acf_fields = data.get("acf", {})
                return self._deserializar_do_acf(acf_fields)
        except Exception as e:
            import logging
            logging.getLogger("curador.aplicador").warning(
                f"Não foi possível carregar composição atual: {e}"
            )
        
        return None
```

---

## PARTE IX — TEMPLATES PHP

### 9.1 Template Principal Adaptativo

```php
<?php
/**
 * Template da Homepage — brasileira.news V3
 * Gerenciado pelo Curador Homepage (Agente #8)
 * 
 * Este template lê os campos ACF Options para montar as 6 zonas
 * editoriais de forma dinâmica e adaptativa.
 * 
 * NÃO editar manualmente os campos ACF — são gerenciados por IA.
 */

if (!defined('ABSPATH')) {
    exit;
}

get_header();

// ─────────────────────────────────────────────────────────────────
// ZONA 1: MANCHETE PRINCIPAL (layout variável)
// ─────────────────────────────────────────────────────────────────

$breaking_ativo  = (bool) get_field('breaking_ativo', 'option');
$manchete_modo   = get_field('manchete_modo', 'option') ?: 'normal';
$manchete_post_id = (int) get_field('manchete_post_id', 'option');

if ($breaking_ativo) {
    // MODO BREAKING: full-width com banner vermelho
    get_template_part('zones/breaking-fullwidth');
} elseif ($manchete_modo === 'amplo') {
    // MODO AMPLO: manchete sem sidebar (foto grande)
    get_template_part('zones/manchete-ampla', null, [
        'post_id' => $manchete_post_id,
        'label'   => get_field('manchete_label', 'option'),
    ]);
} else {
    // MODO NORMAL: 2/3 manchete + 1/3 sidebar
    get_template_part('zones/manchete-padrao', null, [
        'post_id' => $manchete_post_id,
        'label'   => get_field('manchete_label', 'option'),
    ]);
}

// ─────────────────────────────────────────────────────────────────
// ZONA 2: DESTAQUES (grid adaptativo, 2-4 artigos)
// ─────────────────────────────────────────────────────────────────

$destaques_raw = get_field('destaques', 'option') ?: [];
$destaques = [];

foreach ($destaques_raw as $d) {
    $post_id = (int) ($d['post_id'] ?? 0);
    if ($post_id > 0) {
        $post = get_post($post_id);
        if ($post && $post->post_status === 'publish') {
            $destaques[] = [
                'post'    => $post,
                'tamanho' => $d['tamanho'] ?? 'medio',
                'label'   => $d['label'] ?? '',
            ];
        }
    }
}

if (!empty($destaques)) {
    get_template_part('zones/destaques-grid', null, [
        'destaques' => $destaques,
    ]);
}

// ─────────────────────────────────────────────────────────────────
// ZONA 3: EDITORIAS (carrosséis por categoria)
// ─────────────────────────────────────────────────────────────────

$editorias_ordem = [
    'politica'         => 'Política',
    'economia'         => 'Economia',
    'esportes'         => 'Esportes',
    'tecnologia'       => 'Tecnologia',
    'saude'            => 'Saúde',
    'mundo'            => 'Mundo',
    'meio_ambiente'    => 'Meio Ambiente',
    'seguranca'        => 'Segurança',
    'ciencia'          => 'Ciência',
    'cultura'          => 'Cultura',
    'sociedade'        => 'Sociedade',
    'educacao'         => 'Educação',
];

foreach ($editorias_ordem as $slug => $nome_exibicao) {
    $ids_json = get_field("editoria_{$slug}_posts", 'option');
    $ids = [];
    
    if ($ids_json) {
        $ids_decoded = json_decode($ids_json, true);
        if (is_array($ids_decoded)) {
            $ids = array_map('intval', $ids_decoded);
        }
    }
    
    if (empty($ids)) {
        continue; // Não exibe carrossel vazio
    }
    
    $posts_editoria = [];
    foreach ($ids as $pid) {
        $p = get_post($pid);
        if ($p && $p->post_status === 'publish') {
            $posts_editoria[] = $p;
        }
    }
    
    if (!empty($posts_editoria)) {
        get_template_part('zones/editoria-carrossel', null, [
            'editoria'       => $slug,
            'nome_exibicao'  => $nome_exibicao,
            'posts'          => $posts_editoria,
        ]);
    }
}

// ─────────────────────────────────────────────────────────────────
// ZONA 4: MAIS LIDAS (auto-curada por analytics)
// ─────────────────────────────────────────────────────────────────

$mais_lidas_json = get_field('mais_lidas_posts', 'option');
$mais_lidas_ids  = [];

if ($mais_lidas_json) {
    $decoded = json_decode($mais_lidas_json, true);
    if (is_array($decoded)) {
        $mais_lidas_ids = array_map('intval', $decoded);
    }
}

if (!empty($mais_lidas_ids)) {
    $mais_lidas = [];
    foreach ($mais_lidas_ids as $pid) {
        $p = get_post($pid);
        if ($p && $p->post_status === 'publish') {
            $mais_lidas[] = $p;
        }
    }
    
    if (!empty($mais_lidas)) {
        get_template_part('zones/mais-lidas', null, [
            'posts' => $mais_lidas,
        ]);
    }
}

// ─────────────────────────────────────────────────────────────────
// ZONA 5: OPINIÃO / ANÁLISE
// ─────────────────────────────────────────────────────────────────
// (implementação simples — WP_Query por categoria de opinião)
get_template_part('zones/opiniao');

// ─────────────────────────────────────────────────────────────────
// ZONA 6: REGIONAL
// ─────────────────────────────────────────────────────────────────
get_template_part('zones/regional');

get_footer();
```

### 9.2 Template: Breaking News Full-Width

```php
<?php
/**
 * zones/breaking-fullwidth.php
 * 
 * Layout de breaking news: full-width, banner vermelho, urgência máxima.
 * Só exibido quando breaking_ativo = true na ACF Options Page.
 */

$post_id = (int) get_field('breaking_post_id', 'option');
$titulo_manual = get_field('breaking_titulo_manual', 'option');

if (!$post_id) {
    return;
}

$post = get_post($post_id);
if (!$post || $post->post_status !== 'publish') {
    return;
}

$titulo    = $titulo_manual ?: get_the_title($post);
$permalink = get_permalink($post);
$thumb_url = get_the_post_thumbnail_url($post, 'full');
$excerpt   = get_the_excerpt($post);
$editoria  = get_post_meta($post->ID, 'editoria_normalizada', true);
$pub_date  = get_the_date('H:i', $post);
?>

<section class="zona-breaking zona-breaking--fullwidth" 
         aria-label="Breaking News"
         data-post-id="<?= esc_attr($post_id) ?>">
    
    <!-- Banner vermelho de BREAKING NEWS -->
    <div class="breaking-banner">
        <span class="breaking-banner__badge">
            <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16">
                <circle cx="12" cy="12" r="10" fill="currentColor"/>
                <rect x="11" y="6" width="2" height="6" fill="white"/>
                <rect x="11" y="14" width="2" height="2" fill="white"/>
            </svg>
            BREAKING NEWS
        </span>
        <span class="breaking-banner__time"><?= esc_html($pub_date) ?></span>
        <?php if ($editoria): ?>
        <span class="breaking-banner__editoria"><?= esc_html(strtoupper($editoria)) ?></span>
        <?php endif; ?>
    </div>
    
    <!-- Conteúdo principal -->
    <div class="breaking-content">
        <?php if ($thumb_url): ?>
        <figure class="breaking-content__imagem" aria-hidden="true">
            <img 
                src="<?= esc_url($thumb_url) ?>"
                alt="<?= esc_attr($titulo) ?>"
                loading="eager"
                fetchpriority="high"
            />
        </figure>
        <?php endif; ?>
        
        <div class="breaking-content__texto">
            <h1 class="breaking-content__titulo">
                <a href="<?= esc_url($permalink) ?>"><?= esc_html($titulo) ?></a>
            </h1>
            <?php if ($excerpt): ?>
            <p class="breaking-content__excerpt"><?= esc_html($excerpt) ?></p>
            <?php endif; ?>
            <a href="<?= esc_url($permalink) ?>" class="breaking-content__cta">
                Leia a cobertura completa →
            </a>
        </div>
    </div>
    
    <!-- Ticker de breaking: atualização automática via JS -->
    <div class="breaking-ticker" role="marquee" aria-live="polite">
        <span class="breaking-ticker__label">AO VIVO:</span>
        <span class="breaking-ticker__conteudo" id="js-breaking-ticker">
            Acompanhe as atualizações em tempo real
        </span>
    </div>
</section>

<style>
.zona-breaking--fullwidth {
    background: #000;
    color: #fff;
    padding: 0;
    margin: 0 0 2rem;
    position: relative;
}
.breaking-banner {
    background: #c0392b;
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.5rem 1.5rem;
    font-weight: 700;
    font-size: 0.875rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.breaking-banner__badge {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    animation: blink 1s step-end infinite;
}
@keyframes blink {
    50% { opacity: 0.5; }
}
.breaking-content {
    display: grid;
    grid-template-columns: 1fr 1fr;
    min-height: 400px;
}
@media (max-width: 768px) {
    .breaking-content {
        grid-template-columns: 1fr;
    }
}
.breaking-content__imagem {
    margin: 0;
    overflow: hidden;
}
.breaking-content__imagem img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}
.breaking-content__texto {
    padding: 2rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.breaking-content__titulo {
    font-size: 2rem;
    line-height: 1.2;
    margin: 0 0 1rem;
}
.breaking-content__titulo a {
    color: #fff;
    text-decoration: none;
}
.breaking-content__titulo a:hover {
    text-decoration: underline;
}
.breaking-content__cta {
    display: inline-block;
    margin-top: 1rem;
    color: #e74c3c;
    font-weight: 700;
    text-decoration: none;
    font-size: 1.1rem;
}
.breaking-ticker {
    background: #111;
    padding: 0.5rem 1.5rem;
    font-size: 0.875rem;
    border-top: 2px solid #c0392b;
    overflow: hidden;
    white-space: nowrap;
}
.breaking-ticker__label {
    color: #e74c3c;
    font-weight: 700;
    margin-right: 1rem;
}
</style>
```

### 9.3 Template: Manchete Padrão (Normal)

```php
<?php
/**
 * zones/manchete-padrao.php
 * 
 * Layout normal: 2/3 manchete + 1/3 sidebar com artigos recentes.
 */

$args = wp_parse_args($args, [
    'post_id' => 0,
    'label'   => '',
]);

$post_id = (int) $args['post_id'];
$label   = sanitize_text_field($args['label']);

if (!$post_id) {
    return;
}

$post = get_post($post_id);
if (!$post || $post->post_status !== 'publish') {
    return;
}

$titulo    = get_the_title($post);
$permalink = get_permalink($post);
$thumb_url = get_the_post_thumbnail_url($post, 'large');
$excerpt   = get_the_excerpt($post);
$editoria  = get_post_meta($post->ID, 'editoria_normalizada', true);
$autor     = get_post_meta($post->ID, 'fonte_nome', true) ?: get_the_author_meta('display_name', $post->post_author);
$pub_time  = get_the_date('d/m/Y H:i', $post);

// Sidebar: 3 artigos recentes (excluindo a manchete)
$sidebar_posts = get_posts([
    'post_status'    => 'publish',
    'posts_per_page' => 5,
    'exclude'        => [$post_id],
    'orderby'        => 'date',
    'order'          => 'DESC',
]);
?>

<section class="zona-manchete zona-manchete--normal"
         aria-label="Manchete principal">
    <div class="manchete-grid">
        
        <!-- MANCHETE: 2/3 da largura -->
        <article class="manchete-principal" 
                 itemscope itemtype="https://schema.org/NewsArticle">
            
            <?php if ($thumb_url): ?>
            <figure class="manchete-principal__imagem">
                <a href="<?= esc_url($permalink) ?>" tabindex="-1" aria-hidden="true">
                    <img 
                        src="<?= esc_url($thumb_url) ?>"
                        alt="<?= esc_attr($titulo) ?>"
                        loading="eager"
                        fetchpriority="high"
                        itemprop="image"
                    />
                </a>
                <?php if ($label): ?>
                <span class="manchete-label manchete-label--<?= esc_attr(strtolower($label)) ?>">
                    <?= esc_html($label) ?>
                </span>
                <?php endif; ?>
            </figure>
            <?php endif; ?>
            
            <div class="manchete-principal__corpo">
                <?php if ($editoria): ?>
                <span class="manchete-editoria"><?= esc_html(ucfirst($editoria)) ?></span>
                <?php endif; ?>
                
                <h1 class="manchete-principal__titulo" itemprop="headline">
                    <a href="<?= esc_url($permalink) ?>" itemprop="url">
                        <?= esc_html($titulo) ?>
                    </a>
                </h1>
                
                <?php if ($excerpt): ?>
                <p class="manchete-principal__excerpt" itemprop="description">
                    <?= esc_html($excerpt) ?>
                </p>
                <?php endif; ?>
                
                <footer class="manchete-principal__meta">
                    <span class="manchete-fonte" itemprop="author"><?= esc_html($autor) ?></span>
                    <time class="manchete-hora" datetime="<?= esc_attr($post->post_date_gmt) ?>Z" itemprop="datePublished">
                        <?= esc_html($pub_time) ?>
                    </time>
                </footer>
            </div>
        </article>
        
        <!-- SIDEBAR: 1/3 da largura -->
        <aside class="manchete-sidebar" aria-label="Últimas notícias">
            <h2 class="sidebar-titulo">Últimas Notícias</h2>
            
            <?php foreach ($sidebar_posts as $sp): ?>
            <?php if (!$sp) continue; ?>
            <article class="sidebar-item">
                <?php $sp_thumb = get_the_post_thumbnail_url($sp, 'thumbnail'); ?>
                <?php if ($sp_thumb): ?>
                <figure class="sidebar-item__thumb">
                    <a href="<?= esc_url(get_permalink($sp)) ?>" tabindex="-1" aria-hidden="true">
                        <img 
                            src="<?= esc_url($sp_thumb) ?>"
                            alt="<?= esc_attr(get_the_title($sp)) ?>"
                            loading="lazy"
                        />
                    </a>
                </figure>
                <?php endif; ?>
                <div class="sidebar-item__texto">
                    <h3 class="sidebar-item__titulo">
                        <a href="<?= esc_url(get_permalink($sp)) ?>">
                            <?= esc_html(get_the_title($sp)) ?>
                        </a>
                    </h3>
                    <time class="sidebar-item__hora">
                        <?= esc_html(get_the_date('H:i', $sp)) ?>
                    </time>
                </div>
            </article>
            <?php endforeach; ?>
        </aside>
    </div>
</section>
```

### 9.4 Template: Grid de Destaques (Zona 2)

```php
<?php
/**
 * zones/destaques-grid.php
 * 
 * Grid adaptativo de 2-4 destaques.
 * Tamanhos: grande (1.5 col) | medio (1 col) | pequeno (0.5 col)
 */

$args     = wp_parse_args($args, ['destaques' => []]);
$destaques = $args['destaques'];

if (empty($destaques)) {
    return;
}

$total = count($destaques);
?>

<section class="zona-destaques zona-destaques--<?= esc_attr($total) ?>-itens"
         aria-label="Destaques editoriais">
    <div class="destaques-grid">
        
        <?php foreach ($destaques as $idx => $destaque): ?>
        <?php
        $d_post   = $destaque['post'];
        $tamanho  = $destaque['tamanho'] ?? 'medio';
        $label    = $destaque['label'] ?? '';
        $thumb    = get_the_post_thumbnail_url($d_post, 'medium_large');
        $titulo   = get_the_title($d_post);
        $url      = get_permalink($d_post);
        $editoria = get_post_meta($d_post->ID, 'editoria_normalizada', true);
        $hora     = get_the_date('H:i', $d_post);
        ?>
        
        <article class="destaque-item destaque-item--<?= esc_attr($tamanho) ?>"
                 data-pos="<?= esc_attr($idx) ?>"
                 itemscope itemtype="https://schema.org/NewsArticle">
            
            <?php if ($thumb): ?>
            <figure class="destaque-item__imagem">
                <a href="<?= esc_url($url) ?>" tabindex="-1" aria-hidden="true">
                    <img 
                        src="<?= esc_url($thumb) ?>"
                        alt="<?= esc_attr($titulo) ?>"
                        loading="<?= $idx < 2 ? 'eager' : 'lazy' ?>"
                        itemprop="image"
                    />
                </a>
                <?php if ($label): ?>
                <span class="destaque-label destaque-label--<?= esc_attr(strtolower(str_replace(' ', '-', $label))) ?>">
                    <?= esc_html($label) ?>
                </span>
                <?php endif; ?>
            </figure>
            <?php endif; ?>
            
            <div class="destaque-item__corpo">
                <?php if ($editoria): ?>
                <span class="destaque-editoria" itemprop="articleSection">
                    <?= esc_html(ucfirst($editoria)) ?>
                </span>
                <?php endif; ?>
                
                <h2 class="destaque-item__titulo" itemprop="headline">
                    <a href="<?= esc_url($url) ?>" itemprop="url">
                        <?= esc_html($titulo) ?>
                    </a>
                </h2>
                
                <time class="destaque-hora" 
                      datetime="<?= esc_attr($d_post->post_date_gmt) ?>Z"
                      itemprop="datePublished">
                    <?= esc_html($hora) ?>
                </time>
            </div>
        </article>
        
        <?php endforeach; ?>
    </div>
</section>

<style>
.zona-destaques {
    padding: 1.5rem 0;
}
.destaques-grid {
    display: grid;
    gap: 1rem;
}

/* Layout para 2 itens */
.zona-destaques--2-itens .destaques-grid {
    grid-template-columns: 1fr 1fr;
}

/* Layout para 3 itens */
.zona-destaques--3-itens .destaques-grid {
    grid-template-columns: 1.5fr 1fr 1fr;
}

/* Layout para 4 itens */
.zona-destaques--4-itens .destaques-grid {
    grid-template-columns: 1.5fr 1fr 1fr 0.5fr;
}

@media (max-width: 768px) {
    .destaques-grid {
        grid-template-columns: 1fr !important;
    }
}

.destaque-item {
    position: relative;
    background: #fff;
    border-radius: 4px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    transition: box-shadow 0.2s;
}
.destaque-item:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
}
.destaque-item__imagem {
    margin: 0;
    aspect-ratio: 16/9;
    overflow: hidden;
}
.destaque-item__imagem img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.3s;
}
.destaque-item:hover .destaque-item__imagem img {
    transform: scale(1.03);
}
.destaque-item__corpo {
    padding: 0.75rem;
}
.destaque-editoria {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #c0392b;
    display: block;
    margin-bottom: 0.25rem;
}
.destaque-item__titulo {
    font-size: 1rem;
    line-height: 1.3;
    margin: 0 0 0.5rem;
}
.destaque-item__titulo a {
    color: #1a1a1a;
    text-decoration: none;
}
.destaque-item__titulo a:hover {
    color: #c0392b;
}
.destaque-label {
    position: absolute;
    top: 0.5rem;
    left: 0.5rem;
    padding: 0.2rem 0.5rem;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #fff;
    background: #c0392b;
    border-radius: 2px;
    z-index: 1;
}
.destaque-label--ao-vivo {
    background: #27ae60;
    animation: blink 1s step-end infinite;
}
.destaque-label--exclusivo {
    background: #2980b9;
}
.destaque-hora {
    font-size: 0.75rem;
    color: #666;
}
</style>
```

### 9.5 Template: Carrossel de Editoria (Zona 3)

```php
<?php
/**
 * zones/editoria-carrossel.php
 * 
 * Carrossel horizontal com scroll para artigos de uma editoria.
 */

$args           = wp_parse_args($args, ['editoria' => '', 'nome_exibicao' => '', 'posts' => []]);
$editoria       = sanitize_text_field($args['editoria']);
$nome_exibicao  = sanitize_text_field($args['nome_exibicao']);
$posts          = (array) $args['posts'];

if (empty($posts) || empty($editoria)) {
    return;
}

// URL da página de arquivo da editoria
$editoria_url = get_category_link(get_category_by_slug($editoria));
?>

<section class="zona-editoria zona-editoria--<?= esc_attr($editoria) ?>"
         aria-label="<?= esc_attr($nome_exibicao) ?>">
    
    <header class="editoria-header">
        <h2 class="editoria-titulo">
            <a href="<?= esc_url($editoria_url) ?>">
                <?= esc_html($nome_exibicao) ?>
            </a>
        </h2>
        <a href="<?= esc_url($editoria_url) ?>" class="editoria-ver-mais" aria-label="Ver mais notícias de <?= esc_attr($nome_exibicao) ?>">
            Ver mais →
        </a>
    </header>
    
    <div class="editoria-carrossel" 
         data-editoria="<?= esc_attr($editoria) ?>"
         role="list"
         aria-label="Artigos de <?= esc_attr($nome_exibicao) ?>">
        
        <?php foreach ($posts as $p): ?>
        <?php if (!$p) continue; ?>
        <?php
        $p_thumb   = get_the_post_thumbnail_url($p, 'medium');
        $p_titulo  = get_the_title($p);
        $p_url     = get_permalink($p);
        $p_hora    = get_the_date('H:i', $p);
        $p_excerpt = get_the_excerpt($p);
        ?>
        <article class="carrossel-item" role="listitem" itemscope itemtype="https://schema.org/NewsArticle">
            <?php if ($p_thumb): ?>
            <figure class="carrossel-item__thumb">
                <a href="<?= esc_url($p_url) ?>" tabindex="-1" aria-hidden="true">
                    <img src="<?= esc_url($p_thumb) ?>"
                         alt="<?= esc_attr($p_titulo) ?>"
                         loading="lazy"
                         itemprop="image" />
                </a>
            </figure>
            <?php endif; ?>
            <div class="carrossel-item__corpo">
                <h3 class="carrossel-item__titulo" itemprop="headline">
                    <a href="<?= esc_url($p_url) ?>" itemprop="url">
                        <?= esc_html($p_titulo) ?>
                    </a>
                </h3>
                <time class="carrossel-item__hora" datetime="<?= esc_attr($p->post_date_gmt) ?>Z">
                    <?= esc_html($p_hora) ?>
                </time>
            </div>
        </article>
        <?php endforeach; ?>
    </div>
</section>
```

---

## PARTE X — INTEGRAÇÃO COM MONITOR CONCORRÊNCIA (BREAKING-CANDIDATE)

### 10.1 Fluxo de Breaking-Candidate

O Monitor Concorrência (Componente a ser implementado) publica no tópico Kafka `breaking-candidate` quando detecta que **4 ou mais portais concorrentes** têm o mesmo tema nas suas capas.

```
Monitor Concorrência
    │ Scan capa G1, UOL, Folha, Estadão, CNN, R7 (a cada 30 min)
    │ TF-IDF gap analysis: tema X está em 4+ capas?
    │ urgency_score > threshold?
    ▼
Kafka: breaking-candidate
    {
        "tema": "STF suspende votação da PEC da...",
        "artigos_concorrentes": [...],
        "capas_count": 5,
        "urgency_score": 92.5,
        "post_id_sugerido": 12345,  // post nosso sobre o tema (se existir)
        "detectado_em": "2026-03-26T14:33:00Z"
    }
    │
    ▼
Curador Homepage (consumer do breaking-candidate)
    │ Verifica se post_id_sugerido é válido
    │ Se sim: IMEDIATAMENTE muda para modo BREAKING
    │ Se não: sinaliza Redis para Reporters cobrirem o tema
    │ Envia para Kafka: homepage-updates
    ▼
WordPress: breaking_ativo = true, breaking_post_id = X
```

### 10.2 Consumer Kafka do Breaking-Candidate

```python
# brasileira/agents/curador_homepage.py — Consumer Kafka

from aiokafka import AIOKafkaConsumer
import json


class CuradorHomepageAgent:
    """
    Curador Homepage V3.
    
    Dois modos de operação:
    1. Consumer Kafka: reage a eventos (artigos novos, breaking candidates)
    2. Cron periódico: ciclo de 15 min para rotação e atualização
    """
    
    async def consumir_breaking_candidates(self):
        """
        Loop permanente: consome eventos de breaking-candidate do Kafka.
        Executa com alta prioridade (interrompe ciclo periódico se necessário).
        """
        consumer = AIOKafkaConsumer(
            "breaking-candidate",
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="curador-homepage-breaking",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",  # Só eventos novos
        )
        
        await consumer.start()
        try:
            async for message in consumer:
                evento = message.value
                await self._processar_breaking_candidate(evento)
        finally:
            await consumer.stop()
    
    async def _processar_breaking_candidate(self, evento: dict):
        """
        Processa um evento de breaking-candidate.
        
        Ação imediata: não espera o próximo ciclo periódico.
        """
        import logging
        log = logging.getLogger("curador.breaking")
        
        log.warning(
            f"Breaking candidate recebido! "
            f"Tema: '{evento.get('tema', 'N/A')}' | "
            f"Capas: {evento.get('capas_count', 0)} | "
            f"Score: {evento.get('urgency_score', 0)}"
        )
        
        post_id_sugerido = evento.get("post_id_sugerido")
        
        if post_id_sugerido:
            # Temos o artigo: atualizar para breaking imediatamente
            async with adquirir_lock_ciclo(self.redis):
                await self._forcar_breaking(post_id_sugerido, evento)
        else:
            # Não temos o artigo: sinalizar para o Reporter cobrir
            await self.redis.setex(
                f"pautas_urgentes:{evento.get('tema', 'N/A')[:50]}",
                1800,
                json.dumps({
                    "tema": evento.get("tema"),
                    "capas_count": evento.get("capas_count"),
                    "urgencia": "FLASH",
                }),
            )
            log.info(
                f"Breaking sem artigo próprio. Sinalizando para Reporters: "
                f"'{evento.get('tema')}'"
            )
    
    async def _forcar_breaking(self, post_id: int, evento: dict):
        """Força modo BREAKING imediatamente."""
        from brasileira.homepage.aplicador import AplicadorHomepage
        
        composicao_atual = await self.aplicador.carregar_composicao_atual()
        
        # Cria breaking news como artigo candidato
        post = await self.wp_client.get_post(post_id)
        if not post:
            return
        
        breaking_artigo = ArtigoCandidato(
            wp_post_id=post_id,
            titulo=post.get("title", {}).get("rendered", ""),
            editoria=post.get("acf", {}).get("editoria_normalizada", "brasil"),
            urgencia="FLASH",
            url=post.get("link", ""),
            imagem_url=await self.aplicador._get_media_url(post.get("featured_media", 0)),
            publicado_em=datetime.fromisoformat(
                post["date_gmt"].replace("Z", "+00:00")
            ),
            fonte_nome=post.get("acf", {}).get("fonte_nome", ""),
            capas_concorrentes=evento.get("capas_count", 4),
            is_breaking=True,
        )
        
        # Monta composição com breaking ativo
        nova_composicao = composicao_atual or HomepageComposicao()
        nova_composicao.breaking_ativo = True
        nova_composicao.breaking_news = breaking_artigo
        nova_composicao.manchete_modo = "breaking"
        nova_composicao.layout_atual = "breaking"
        nova_composicao.ciclo_id = f"breaking-{int(time.time())}"
        nova_composicao.atualizado_em = datetime.now(tz=ZoneInfo("UTC"))
        
        sucesso = await self.aplicador.aplicar(nova_composicao, composicao_atual)
        
        if sucesso:
            # Notifica Monitor Sistema
            await self.kafka_producer.send(
                "homepage-updates",
                value=json.dumps({
                    "tipo": "breaking_ativado",
                    "post_id": post_id,
                    "ciclo_id": nova_composicao.ciclo_id,
                    "timestamp": nova_composicao.atualizado_em.isoformat(),
                }).encode("utf-8"),
            )
```

---

## PARTE XI — MÉTRICAS E SINAIS (CTR, BOUNCE, TEMPO)

### 11.1 Métricas Coletadas e Usadas

O Curador Homepage consome métricas que são populadas pelo **Monitor Sistema** (via Google Analytics / WordPress Stats). As chaves Redis são:

| Chave Redis | Tipo | TTL | Conteúdo |
|-------------|------|-----|----------|
| `metricas:post:{id}` | HASH | 2h | `ctr_2h`, `views_1h`, `clicks_30min`, `bounce_rate`, `tempo_medio_s` |
| `metricas:homepage:global` | HASH | 1h | `pageviews_1h`, `usuarios_ativos`, `taxa_saida` |
| `monitor_concorrencia:capas:{post_id}` | STRING | 4h | Número de capas de concorrentes sobre o tema |
| `monitor_concorrencia:temas_destaque` | LIST | 1h | Top 10 temas nas capas concorrentes |

### 11.2 Sinal de CTR para Decisão Editorial

O CTR é a métrica mais usada para validar decisões de curadoria:

```python
# brasileira/homepage/metricas.py — Sistema de decisão por CTR

CTR_BENCHMARKS = {
    "manchete":   {"excelente": 8.0, "bom": 5.0, "mediano": 3.0, "ruim": 1.0},
    "destaque_1": {"excelente": 5.0, "bom": 3.0, "mediano": 1.5, "ruim": 0.5},
    "destaque_2": {"excelente": 3.0, "bom": 2.0, "mediano": 1.0, "ruim": 0.3},
    "editoria":   {"excelente": 2.0, "bom": 1.0, "mediano": 0.5, "ruim": 0.1},
}


async def avaliar_performance_atual(
    redis,
    composicao: HomepageComposicao,
) -> dict:
    """
    Avalia performance de cada artigo na composição atual.
    
    Retorna: {wp_post_id: performance_rating}
    onde performance_rating: "excelente" | "bom" | "mediano" | "ruim" | "sem_dados"
    """
    ratings = {}
    
    # Avalia manchete
    if composicao.manchete:
        manchete_id = composicao.manchete.wp_post_id
        metricas = await redis.hgetall(f"metricas:post:{manchete_id}")
        ctr = float(metricas.get("ctr_2h", -1))
        
        if ctr < 0:
            ratings[manchete_id] = "sem_dados"
        else:
            bench = CTR_BENCHMARKS["manchete"]
            if ctr >= bench["excelente"]:
                ratings[manchete_id] = "excelente"
            elif ctr >= bench["bom"]:
                ratings[manchete_id] = "bom"
            elif ctr >= bench["mediano"]:
                ratings[manchete_id] = "mediano"
            else:
                ratings[manchete_id] = "ruim"
    
    return ratings
```

### 11.3 Memória Episódica de Decisões

O Curador aprende com decisões passadas usando memória episódica no PostgreSQL (pgvector):

```python
# brasileira/homepage/scorer.py — Memória episódica

async def registrar_decisao_episodica(
    pg_client,
    composicao: HomepageComposicao,
    performance_24h: dict,  # {post_id: {"ctr": X, "views": Y}}
):
    """
    Registra a decisão de curadoria e sua performance 24h depois.
    Usado para melhorar o system prompt do LLM com exemplos reais.
    """
    
    # Para cada artigo na manchete e destaques
    artigos_avaliados = []
    if composicao.manchete:
        artigos_avaliados.append(("manchete", composicao.manchete))
    for slot in composicao.destaques:
        artigos_avaliados.append((f"destaque_{slot.posicao}", slot.artigo))
    
    for zona, artigo in artigos_avaliados:
        perf = performance_24h.get(artigo.wp_post_id, {})
        
        episodio = {
            "ciclo_id": composicao.ciclo_id,
            "zona": zona,
            "wp_post_id": artigo.wp_post_id,
            "titulo": artigo.titulo,
            "editoria": artigo.editoria,
            "score_total": artigo.score_total,
            "layout": composicao.layout_atual,
            "ctr_real_24h": perf.get("ctr"),
            "views_real_24h": perf.get("views"),
            "decisao_acertada": perf.get("ctr", 0) > 3.0,  # CTR > 3% = acerto
            "timestamp": composicao.atualizado_em.isoformat() if composicao.atualizado_em else None,
        }
        
        await pg_client.execute(
            """
            INSERT INTO memoria_agentes (agente, tipo, conteudo, criado_em)
            VALUES ($1, $2, $3::jsonb, NOW())
            """,
            "curador_homepage",
            "episodica",
            json.dumps(episodio, ensure_ascii=False),
        )
```

---

## PARTE XII — SCHEMAS E DEPENDÊNCIAS

### 12.1 Tabelas PostgreSQL Específicas do Curador

```sql
-- Histórico de ciclos do curador
CREATE TABLE curador_cycles (
    id               SERIAL PRIMARY KEY,
    ciclo_id         VARCHAR(50) UNIQUE NOT NULL,
    trigger_tipo     VARCHAR(30),  -- 'article_published' | 'breaking_candidate' | 'periodic'
    layout           VARCHAR(20),  -- 'normal' | 'amplo' | 'breaking'
    manchete_post_id INTEGER,
    destaques_ids    INTEGER[],    -- Array de post_ids nos destaques
    total_candidatos INTEGER,
    llm_provider     VARCHAR(50),
    llm_model        VARCHAR(100),
    llm_tokens_in    INTEGER,
    llm_tokens_out   INTEGER,
    llm_custo_usd    DECIMAL(10, 6),
    duracao_s        DECIMAL(8, 3),
    sucesso          BOOLEAN DEFAULT TRUE,
    erro             TEXT,
    iniciado_em      TIMESTAMPTZ DEFAULT NOW(),
    concluido_em     TIMESTAMPTZ
);

CREATE INDEX idx_curador_cycles_iniciado ON curador_cycles(iniciado_em DESC);
CREATE INDEX idx_curador_cycles_manchete ON curador_cycles(manchete_post_id);

-- Performance de artigos na homepage (atualizada 24h depois)
CREATE TABLE homepage_performance (
    id               SERIAL PRIMARY KEY,
    ciclo_id         VARCHAR(50) REFERENCES curador_cycles(ciclo_id),
    wp_post_id       INTEGER NOT NULL,
    zona             VARCHAR(30),  -- 'manchete' | 'destaque_0' | 'editoria_politica' etc.
    score_editorial  DECIMAL(6, 2),
    ctr_real_24h     DECIMAL(6, 4),
    views_24h        INTEGER,
    clicks_24h       INTEGER,
    bounce_rate_pct  DECIMAL(5, 2),
    tempo_medio_s    INTEGER,
    registrado_em    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_hp_perf_post ON homepage_performance(wp_post_id);
CREATE INDEX idx_hp_perf_ciclo ON homepage_performance(ciclo_id);
```

### 12.2 Campos ACF WordPress (Referência Completa)

| Campo ACF | Nome | Tipo | Zona | Descrição |
|-----------|------|------|------|-----------|
| `manchete_modo` | Modo da Manchete | select | 1 | `normal` / `amplo` / `breaking` |
| `manchete_post_id` | Manchete Post ID | number | 1 | ID do post principal |
| `manchete_label` | Label da Manchete | select | 1 | `URGENTE` / `EXCLUSIVO` / `AO VIVO` |
| `breaking_ativo` | Breaking Ativo | boolean | 1 | Liga/desliga modo breaking |
| `breaking_post_id` | Breaking Post ID | number | 1 | ID do post breaking |
| `breaking_titulo_manual` | Título Manual | text | 1 | Override de título (opcional) |
| `destaques` | Destaques | repeater | 2 | Array com `post_id`, `tamanho`, `label` |
| `editoria_{slug}_posts` | Editoria Posts | textarea | 3 | JSON array de IDs (1 campo por editoria) |
| `mais_lidas_posts` | Mais Lidas Posts | textarea | 4 | JSON array de IDs |
| `curador_ciclo_id` | Ciclo ID | text | meta | ID do último ciclo (readonly) |
| `curador_atualizado_em` | Atualizado Em | text | meta | ISO datetime (readonly) |

### 12.3 Tópicos Kafka (Curador)

| Tópico | Direção | Evento | Payload |
|--------|---------|--------|---------|
| `article-published` | Consumer | Novo artigo publicado | `{post_id, titulo, editoria, url, urgencia}` |
| `breaking-candidate` | Consumer | Breaking detectado | `{tema, capas_count, urgency_score, post_id_sugerido}` |
| `homepage-updates` | Producer | Homepage atualizada | `{tipo, layout, manchete_id, ciclo_id, timestamp}` |

### 12.4 Dependências de Runtime

| Componente | Versão | Uso |
|------------|--------|-----|
| Python | 3.12+ | Runtime |
| LangGraph | ≥ 0.2 | StateGraph do agente |
| LiteLLM | ≥ 1.40 | Via SmartLLMRouter |
| redis-py (asyncio) | ≥ 5.0 | Working memory + locks |
| aiokafka | ≥ 0.10 | Consumer/Producer Kafka |
| httpx | ≥ 0.27 | WordPress REST API |
| pydantic | ≥ 2.5 | State models |
| asyncpg | ≥ 0.29 | PostgreSQL async |
| zoneinfo | stdlib | Timezones (UTC correto) |
| ACF PRO | ≥ 6.3 | WordPress (server) |

### 12.5 Variáveis de Ambiente Obrigatórias

```bash
# WordPress
WP_URL=https://brasileira.news
WP_USER=iapublicador
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx  # Application Password WP

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Redis
REDIS_URL=redis://localhost:6379/0

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/brasileira

# LLM (via SmartLLMRouter — NÃO referenciar diretamente)
# O SmartLLMRouter gerencia todas as chaves
```

---

## PARTE XIII — ENTRYPOINT

### 13.1 Agente Principal (LangGraph)

```python
# brasileira/agents/curador_homepage.py

import asyncio
import uuid
import time
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.graph import StateGraph, END

from brasileira.homepage.state import (
    HomepageState, HomepageComposicao, ArtigoCandidato
)
from brasileira.homepage.candidatos import ColetorCandidatos
from brasileira.homepage.scorer import aplicar_scores
from brasileira.homepage.layout import DecidorLayout
from brasileira.homepage.compositor import Compositor
from brasileira.homepage.aplicador import AplicadorHomepage
from brasileira.homepage.metricas import MonitorMetricasHomepage
from brasileira.integrations.wordpress_client import WordPressClient
from brasileira.integrations.redis_client import RedisClient
from brasileira.integrations.kafka_client import KafkaProducer, KafkaConsumer
from brasileira.integrations.postgres_client import PostgresClient
from brasileira.llm.smart_router import SmartLLMRouter

logger = logging.getLogger("curador_homepage")


class CuradorHomepageV3:
    """
    Curador Homepage V3 — Agente de curadoria editorial da homepage.
    
    REGRAS INVIOLÁVEIS (configurado aqui, não alterar):
    1. LLM PREMIUM obrigatório (task_type="homepage_scoring")
    2. Lock Redis: nunca dois ciclos simultâneos
    3. Diff atômico: nunca clear-all antes de aplicar
    4. Timezone UTC em TUDO (zoneinfo.ZoneInfo("UTC"))
    5. 6 zonas editoriais: nunca reduzir
    6. Ciclo máximo: 30 min (mínimo: 5 min em breaking)
    """
    
    def __init__(self, settings):
        self.settings = settings
        self.wp = WordPressClient(settings)
        self.redis = RedisClient(settings)
        self.kafka_producer = KafkaProducer(settings)
        self.pg = PostgresClient(settings)
        self.router = SmartLLMRouter(settings)
        
        self.coletor = ColetorCandidatos(self.wp, self.redis)
        self.layout_decididor = DecidorLayout(self.redis)
        self.compositor = Compositor()
        self.aplicador = AplicadorHomepage(self.wp, self.redis)
        self.monitor_metricas = MonitorMetricasHomepage()
        
        self.scheduler = HomepageCycleScheduler()
        
        # Compila o grafo LangGraph
        self._compilar_grafo()
    
    def _compilar_grafo(self):
        """Compila o StateGraph do LangGraph."""
        grafo = StateGraph(HomepageState)
        
        # Nós do pipeline
        grafo.add_node("coletar_candidatos", self._etapa_coletar)
        grafo.add_node("score_editorial", self._etapa_score)
        grafo.add_node("decidir_layout", self._etapa_layout)
        grafo.add_node("compor_zonas", self._etapa_compor)
        grafo.add_node("aplicar_atomico", self._etapa_aplicar)
        grafo.add_node("registrar", self._etapa_registrar)
        
        # Fluxo linear
        grafo.add_edge("coletar_candidatos", "score_editorial")
        grafo.add_edge("score_editorial", "decidir_layout")
        grafo.add_edge("decidir_layout", "compor_zonas")
        grafo.add_edge("compor_zonas", "aplicar_atomico")
        grafo.add_edge("aplicar_atomico", "registrar")
        grafo.add_edge("registrar", END)
        
        grafo.set_entry_point("coletar_candidatos")
        
        self.grafo = grafo.compile()
    
    async def rodar_ciclo(
        self,
        trigger: str = "periodic",
        artigo_novo: ArtigoCandidato | None = None,
        breaking_candidato: ArtigoCandidato | None = None,
    ):
        """
        Executa um ciclo completo de curadoria.
        
        OBRIGATÓRIO: Adquire lock Redis antes de iniciar.
        """
        ciclo_id = f"ciclo-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        logger.info(f"[{ciclo_id}] Iniciando ciclo de curadoria (trigger={trigger})")
        
        try:
            async with adquirir_lock_ciclo(self.redis):
                estado_inicial = HomepageState(
                    trigger=trigger,
                    artigo_novo=artigo_novo,
                    breaking_candidato=breaking_candidato,
                    ciclo_id=ciclo_id,
                    iniciado_em=datetime.now(tz=ZoneInfo("UTC")),
                )
                
                estado_final = await self.grafo.ainvoke(
                    estado_inicial.model_dump()
                )
                
                logger.info(
                    f"[{ciclo_id}] Ciclo concluído. "
                    f"Layout: {estado_final.get('layout_decidido')} | "
                    f"Candidatos: {len(estado_final.get('candidatos', []))}"
                )
                
                return estado_final
        
        except CicloEmAndamentoError as e:
            logger.warning(f"[{ciclo_id}] {e}")
            return None
        
        except Exception as e:
            logger.error(f"[{ciclo_id}] Erro no ciclo: {e}", exc_info=True)
            # Não propaga: o scheduler tentará novamente no próximo ciclo
            return None
    
    # ─────────────────────────────────────────────────────────────────
    # Etapas do Pipeline
    # ─────────────────────────────────────────────────────────────────
    
    async def _etapa_coletar(self, state: dict) -> dict:
        """Etapa 1: Coleta artigos candidatos."""
        candidatos = await self.coletor.coletar()
        logger.info(f"[{state['ciclo_id']}] Coletados {len(candidatos)} candidatos")
        return {**state, "candidatos": [c.model_dump() for c in candidatos]}
    
    async def _etapa_score(self, state: dict) -> dict:
        """Etapa 2: Scoring editorial com LLM PREMIUM."""
        candidatos_raw = state.get("candidatos", [])
        candidatos = [ArtigoCandidato(**c) for c in candidatos_raw]
        
        # Busca temas em destaque nos concorrentes (para contexto do LLM)
        temas_concorrentes = await self.redis.lrange(
            "monitor_concorrencia:temas_destaque", 0, 9
        )
        
        # Verifica se breaking está ativo (contexto para o LLM)
        breaking_ativo = bool(await self.redis.exists("homepage:breaking_inicio"))
        
        # Score com LLM PREMIUM — NUNCA econômico
        candidatos_scored = await aplicar_scores(
            candidatos,
            self.router,
            temas_concorrentes=[t.decode() if isinstance(t, bytes) else t for t in temas_concorrentes],
            breaking_ativo=breaking_ativo,
        )
        
        logger.info(
            f"[{state['ciclo_id']}] Score concluído. "
            f"Top score: {candidatos_scored[0].score_total if candidatos_scored else 0}"
        )
        
        return {**state, "candidatos": [c.model_dump() for c in candidatos_scored]}
    
    async def _etapa_layout(self, state: dict) -> dict:
        """Etapa 3: Decisão de layout."""
        candidatos = [ArtigoCandidato(**c) for c in state.get("candidatos", [])]
        breaking_raw = state.get("breaking_candidato")
        breaking = ArtigoCandidato(**breaking_raw) if breaking_raw else None
        
        # Busca composição atual para saber o layout anterior
        composicao_atual = await self.aplicador.carregar_composicao_atual()
        layout_anterior = composicao_atual.layout_atual if composicao_atual else "normal"
        
        manchete = candidatos[0] if candidatos else None
        
        layout = await self.layout_decididor.decidir(
            manchete=manchete,
            breaking_candidato=breaking,
            layout_anterior=layout_anterior,
        )
        
        logger.info(f"[{state['ciclo_id']}] Layout decidido: {layout}")
        
        return {
            **state,
            "layout_decidido": layout,
            "composicao_atual": composicao_atual.model_dump() if composicao_atual else None,
        }
    
    async def _etapa_compor(self, state: dict) -> dict:
        """Etapa 4: Compõe as 6 zonas editoriais."""
        candidatos = [ArtigoCandidato(**c) for c in state.get("candidatos", [])]
        layout = state.get("layout_decidido", "normal")
        breaking_raw = state.get("breaking_candidato")
        breaking = ArtigoCandidato(**breaking_raw) if breaking_raw else None
        
        composicao = self.compositor.compor(
            candidatos=candidatos,
            layout=layout,
            breaking_candidato=breaking,
        )
        composicao.ciclo_id = state["ciclo_id"]
        composicao.total_candidatos_avaliados = len(candidatos)
        
        return {**state, "composicao_proposta": composicao.model_dump()}
    
    async def _etapa_aplicar(self, state: dict) -> dict:
        """Etapa 5: Aplica a composição no WordPress (diff atômico)."""
        composicao_raw = state.get("composicao_proposta")
        composicao = HomepageComposicao(**composicao_raw) if composicao_raw else None
        
        composicao_atual_raw = state.get("composicao_atual")
        composicao_atual = HomepageComposicao(**composicao_atual_raw) if composicao_atual_raw else None
        
        sucesso = await self.aplicador.aplicar(composicao, composicao_atual)
        
        if sucesso:
            logger.info(f"[{state['ciclo_id']}] Homepage aplicada com sucesso")
        else:
            logger.error(f"[{state['ciclo_id']}] Falha ao aplicar homepage")
        
        return {**state, "aplicacao_sucesso": sucesso}
    
    async def _etapa_registrar(self, state: dict) -> dict:
        """Etapa 6: Registra log, métricas, Kafka."""
        composicao_raw = state.get("composicao_proposta")
        composicao = HomepageComposicao(**composicao_raw) if composicao_raw else None
        
        # PostgreSQL: log do ciclo
        try:
            manchete_id = composicao.manchete.wp_post_id if composicao and composicao.manchete else None
            destaques_ids = (
                [s.artigo.wp_post_id for s in composicao.destaques]
                if composicao else []
            )
            duracao = (
                (datetime.now(tz=ZoneInfo("UTC")) - state["iniciado_em"]).total_seconds()
                if state.get("iniciado_em") else 0
            )
            
            await self.pg.execute(
                """
                INSERT INTO curador_cycles (
                    ciclo_id, trigger_tipo, layout,
                    manchete_post_id, destaques_ids,
                    total_candidatos, sucesso, duracao_s, iniciado_em, concluido_em
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                """,
                state["ciclo_id"],
                state.get("trigger", "periodic"),
                state.get("layout_decidido", "normal"),
                manchete_id,
                destaques_ids,
                state.get("total_candidatos_avaliados", 0),
                state.get("aplicacao_sucesso", False),
                duracao,
                state.get("iniciado_em"),
            )
        except Exception as e:
            logger.warning(f"Erro ao registrar ciclo no PostgreSQL: {e}")
        
        # Kafka: homepage-updates
        try:
            await self.kafka_producer.send(
                "homepage-updates",
                value=json.dumps({
                    "tipo": f"ciclo_{state.get('trigger', 'periodic')}",
                    "layout": state.get("layout_decidido", "normal"),
                    "manchete_id": manchete_id,
                    "ciclo_id": state["ciclo_id"],
                    "timestamp": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
                    "sucesso": state.get("aplicacao_sucesso", False),
                }).encode("utf-8"),
            )
        except Exception as e:
            logger.warning(f"Erro ao publicar homepage-updates no Kafka: {e}")
        
        return state
    
    # ─────────────────────────────────────────────────────────────────
    # Loop Principal
    # ─────────────────────────────────────────────────────────────────
    
    async def iniciar(self):
        """
        Inicia o Curador Homepage.
        
        Roda três tasks em paralelo:
        1. Loop periódico (ciclo a cada 15-30 min)
        2. Consumer Kafka: article-published
        3. Consumer Kafka: breaking-candidate
        """
        logger.info("Curador Homepage V3 iniciando...")
        
        await asyncio.gather(
            self._loop_periodico(),
            self._consumir_article_published(),
            self.consumir_breaking_candidates(),
        )
    
    async def _loop_periodico(self):
        """Loop periódico: ciclo a cada 15-30 min."""
        while True:
            await self.rodar_ciclo(trigger="periodic")
            
            # Calcula próximo intervalo
            composicao_atual = await self.aplicador.carregar_composicao_atual()
            breaking_ativo = composicao_atual.breaking_ativo if composicao_atual else False
            artigos_ultima_hora = await self._contar_artigos_ultima_hora()
            
            intervalo_min = self.scheduler.get_next_interval(
                breaking_ativo=breaking_ativo,
                artigos_ultima_hora=artigos_ultima_hora,
            )
            
            logger.info(f"Próximo ciclo em {intervalo_min} minutos")
            await asyncio.sleep(intervalo_min * 60)
    
    async def _consumir_article_published(self):
        """Consumer Kafka: article-published."""
        consumer = AIOKafkaConsumer(
            "article-published",
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="curador-homepage-articles",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",
        )
        
        await consumer.start()
        try:
            async for message in consumer:
                evento = message.value
                urgencia = evento.get("urgencia", "NORMAL")
                
                # Só dispara ciclo imediato se urgência FLASH
                if urgencia == "FLASH":
                    logger.info(
                        f"Artigo FLASH publicado: #{evento.get('post_id')} — "
                        f"'{evento.get('titulo', '')[:60]}'"
                    )
                    await self.rodar_ciclo(trigger="article_published")
                # Para artigos normais, aguarda o próximo ciclo periódico
        finally:
            await consumer.stop()
    
    async def _contar_artigos_ultima_hora(self) -> int:
        """Conta artigos publicados na última hora (via Redis/WP)."""
        try:
            cached = await self.redis.get("stats:artigos_ultima_hora")
            return int(cached) if cached else 20
        except Exception:
            return 20


# ─────────────────────────────────────────────────────────────────
# CLI Entrypoint
# ─────────────────────────────────────────────────────────────────

async def main():
    """Entrypoint do Curador Homepage."""
    from brasileira.config import get_settings
    
    settings = get_settings()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    curador = CuradorHomepageV3(settings)
    await curador.iniciar()


if __name__ == "__main__":
    asyncio.run(main())
```

### 13.2 Docker / Systemd

```bash
# Inicialização como serviço systemd (recomendado para produção)
# /etc/systemd/system/curador-homepage.service

[Unit]
Description=brasileira.news — Curador Homepage V3
After=network.target redis.service kafka.service postgresql.service
Requires=redis.service kafka.service postgresql.service

[Service]
Type=simple
User=brasileira
WorkingDirectory=/opt/brasileira
ExecStart=/opt/brasileira/venv/bin/python -m brasileira.agents.curador_homepage
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=curador-homepage

[Install]
WantedBy=multi-user.target
```

```yaml
# docker-compose.yml (serviço curador-homepage)
  curador-homepage:
    build:
      context: .
      dockerfile: Dockerfile
    command: python -m brasileira.agents.curador_homepage
    depends_on:
      - redis
      - kafka
      - postgres
    environment:
      - WP_URL=${WP_URL}
      - WP_USER=${WP_USER}
      - WP_APP_PASSWORD=${WP_APP_PASSWORD}
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql+asyncpg://postgres:${DB_PASS}@postgres/brasileira
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "python", "-c", "import asyncio; import redis.asyncio as r; asyncio.run(r.from_url('redis://redis:6379').ping())"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## PARTE XIV — TESTES E CHECKLIST

### 14.1 Testes Unitários Obrigatórios

```python
# tests/test_curador_homepage.py

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock

from brasileira.homepage.state import ArtigoCandidato
from brasileira.homepage.scorer import calcular_score_objetivo
from brasileira.homepage.layout import DecidorLayout
from brasileira.homepage.compositor import Compositor


class TestScoreObjetivo:
    """Testa cálculo de score objetivo (sem LLM)."""
    
    def _artigo(self, **kwargs) -> ArtigoCandidato:
        """Factory de artigo para testes."""
        defaults = {
            "wp_post_id": 1,
            "titulo": "Teste",
            "editoria": "politica",
            "urgencia": "NORMAL",
            "url": "https://brasileira.news/teste",
            "imagem_url": "https://img.example.com/foto.jpg",
            "imagem_width": 1200,
            "fonte_nome": "agencia_brasil",
            "publicado_em": datetime.now(tz=ZoneInfo("UTC")) - timedelta(minutes=30),
            "capas_concorrentes": 0,
            "ctr_atual": 0.0,
            "views_1h": 0,
        }
        return ArtigoCandidato(**{**defaults, **kwargs})
    
    def test_fonte_tier1_score_maximo(self):
        artigo = self._artigo(fonte_nome="agencia_brasil")
        score = calcular_score_objetivo(artigo)
        # Tier1(30) + imagem(10) + hires(5) + frescor_2h(5) = 50
        assert score >= 50
    
    def test_sem_imagem_penalidade(self):
        com_imagem = self._artigo(imagem_url="https://img.example.com/foto.jpg")
        sem_imagem = self._artigo(imagem_url=None)
        
        score_com = calcular_score_objetivo(com_imagem)
        score_sem = calcular_score_objetivo(sem_imagem)
        
        # Diferença deve ser >= 20 (10 bônus + 10 penalidade)
        assert score_com - score_sem >= 20
    
    def test_frescor_1h_bonus(self):
        recente = self._artigo(
            publicado_em=datetime.now(tz=ZoneInfo("UTC")) - timedelta(minutes=30)
        )
        antigo = self._artigo(
            publicado_em=datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=3)
        )
        
        score_recente = calcular_score_objetivo(recente)
        score_antigo = calcular_score_objetivo(antigo)
        
        # Artigo recente deve ter mais pontos
        assert score_recente > score_antigo
    
    def test_timezone_utc_obrigatorio(self):
        """
        BUG V2 CORRIGIDO: timezone naive causava erro de 3h.
        V3: publicado_em DEVE ser UTC-aware.
        """
        agora_utc = datetime.now(tz=ZoneInfo("UTC"))
        
        # Artigo com timezone UTC-aware
        artigo_utc = self._artigo(publicado_em=agora_utc - timedelta(minutes=30))
        score = calcular_score_objetivo(artigo_utc, agora=agora_utc)
        
        # Score deve incluir bônus de frescor (< 1h)
        assert score >= 40  # Deve ter bônus de frescor
    
    def test_capas_concorrentes_bonus(self):
        sem_capas = self._artigo(capas_concorrentes=0)
        com_capas = self._artigo(capas_concorrentes=4)
        
        score_sem = calcular_score_objetivo(sem_capas)
        score_com = calcular_score_objetivo(com_capas)
        
        assert score_com > score_sem
        assert score_com - score_sem == 12  # SCORE_CAPAS_4MAIS = 12


class TestDecisaoLayout:
    """Testa decisão de layout."""
    
    def _artigo(self, score_total, capas, minutos_ago, urgencia="NORMAL", is_breaking=False):
        pub = datetime.now(tz=ZoneInfo("UTC")) - timedelta(minutes=minutos_ago)
        a = ArtigoCandidato(
            wp_post_id=1, titulo="T", editoria="politica", urgencia=urgencia,
            url="u", fonte_nome="agencia_brasil", publicado_em=pub,
            capas_concorrentes=capas, is_breaking=is_breaking,
        )
        a.score_total = score_total
        return a
    
    @pytest.mark.asyncio
    async def test_breaking_por_candidato_externo(self):
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        redis_mock.exists.return_value = False
        
        decididor = DecidorLayout(redis_mock)
        manchete = self._artigo(score_total=80, capas=1, minutos_ago=30)
        breaking = self._artigo(score_total=140, capas=5, minutos_ago=10, is_breaking=True)
        
        layout = await decididor.decidir(manchete, breaking, "normal")
        assert layout == "breaking"
    
    @pytest.mark.asyncio
    async def test_breaking_por_thresholds(self):
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        
        decididor = DecidorLayout(redis_mock)
        manchete = self._artigo(score_total=135, capas=5, minutos_ago=45)
        
        layout = await decididor.decidir(manchete, None, "normal")
        assert layout == "breaking"
    
    @pytest.mark.asyncio
    async def test_amplo_por_score_e_capas(self):
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        
        decididor = DecidorLayout(redis_mock)
        manchete = self._artigo(score_total=105, capas=3, minutos_ago=60)
        
        layout = await decididor.decidir(manchete, None, "normal")
        assert layout == "amplo"
    
    @pytest.mark.asyncio
    async def test_normal_padrao(self):
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        
        decididor = DecidorLayout(redis_mock)
        manchete = self._artigo(score_total=70, capas=1, minutos_ago=120)
        
        layout = await decididor.decidir(manchete, None, "normal")
        assert layout == "normal"


class TestComposicao:
    """Testa composição das 6 zonas."""
    
    def _candidato(self, editoria, score=60, wp_id=None):
        a = ArtigoCandidato(
            wp_post_id=wp_id or hash(editoria) % 10000,
            titulo=f"Título {editoria}",
            editoria=editoria,
            urgencia="NORMAL",
            url=f"https://brasileira.news/{editoria}",
            imagem_url="https://img.example.com/foto.jpg",
            imagem_width=1200,
            fonte_nome="agencia_brasil",
            publicado_em=datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1),
        )
        a.score_total = score
        return a
    
    def test_diversidade_editorial_destaques(self):
        """Destaques não devem ter mais de 1 artigo da mesma editoria."""
        compositor = Compositor()
        candidatos = [
            self._candidato("politica", 100, 1),
            self._candidato("politica", 90, 2),  # Segundo de política
            self._candidato("economia", 85, 3),
            self._candidato("esportes", 80, 4),
        ]
        
        composicao = compositor.compor(candidatos, "normal")
        
        # Conta por editoria nos destaques
        editorias_destaques = [s.artigo.editoria for s in composicao.destaques]
        from collections import Counter
        counts = Counter(editorias_destaques)
        
        # Nenhuma editoria deve ter mais de MAX_DESTAQUES_POR_EDITORIA
        for editoria, count in counts.items():
            assert count <= 1, f"Editoria {editoria} aparece {count} vezes nos destaques"
    
    def test_manchete_tem_imagem(self):
        """A manchete DEVE ter imagem."""
        compositor = Compositor()
        candidatos = [
            ArtigoCandidato(
                wp_post_id=1, titulo="Sem imagem", editoria="politica",
                urgencia="NORMAL", url="u", fonte_nome="f",
                publicado_em=datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1),
                imagem_url=None,  # Sem imagem
            ),
            ArtigoCandidato(
                wp_post_id=2, titulo="Com imagem", editoria="economia",
                urgencia="NORMAL", url="u2", fonte_nome="f",
                publicado_em=datetime.now(tz=ZoneInfo("UTC")) - timedelta(hours=1),
                imagem_url="https://img.example.com/foto.jpg",
                imagem_width=1200,
            ),
        ]
        candidatos[0].score_total = 100  # Score alto mas sem imagem
        candidatos[1].score_total = 80
        
        composicao = compositor.compor(candidatos, "normal")
        
        # Manchete deve ser o que tem imagem (mesmo score menor)
        assert composicao.manchete is not None
        assert composicao.manchete.imagem_url is not None
    
    def test_6_zonas_presentes(self):
        """Composição sempre tem as 6 zonas."""
        compositor = Compositor()
        candidatos = [
            self._candidato("politica", 100, i) for i in range(1, 20)
        ] + [
            self._candidato("economia", 90, i) for i in range(20, 40)
        ]
        
        composicao = compositor.compor(candidatos, "normal")
        
        assert composicao.manchete is not None
        assert isinstance(composicao.destaques, list)
        assert isinstance(composicao.por_editoria, dict)
        assert isinstance(composicao.mais_lidas, list)
        assert isinstance(composicao.opiniao, list)
        assert isinstance(composicao.regional, list)
```

### 14.2 Teste de Integração: Ciclo Completo

```python
# tests/integration/test_ciclo_completo.py

"""
Teste de integração do ciclo completo do Curador Homepage.

Requer: WordPress com ACF PRO, Redis, PostgreSQL, Kafka ativos.
Usar ambiente de staging, nunca produção.

Execute: pytest tests/integration/ -v --integration
"""

import pytest
import asyncio
from brasileira.agents.curador_homepage import CuradorHomepageV3
from brasileira.config import get_settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ciclo_completo_staging():
    """Executa um ciclo completo e verifica resultado no WordPress."""
    settings = get_settings()
    curador = CuradorHomepageV3(settings)
    
    # Executa ciclo
    resultado = await curador.rodar_ciclo(trigger="periodic")
    
    assert resultado is not None, "Ciclo retornou None"
    assert resultado.get("aplicacao_sucesso"), "Aplicação no WordPress falhou"
    
    # Verifica no WordPress
    response = await curador.wp.get("/acf/v3/options/homepage-settings")
    assert response.status_code == 200
    
    acf_data = response.json().get("acf", {})
    manchete_id = acf_data.get("manchete_post_id", 0)
    
    assert manchete_id > 0, "Manchete não foi definida no WordPress"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lock_redis_previne_ciclos_simultaneos():
    """Verifica que o lock Redis previne execuções simultâneas."""
    settings = get_settings()
    curador = CuradorHomepageV3(settings)
    
    # Executa dois ciclos simultaneamente
    resultados = await asyncio.gather(
        curador.rodar_ciclo(trigger="periodic"),
        curador.rodar_ciclo(trigger="periodic"),
        return_exceptions=True,
    )
    
    # Pelo menos um deve ter sido bloqueado (retornado None)
    nones = sum(1 for r in resultados if r is None)
    assert nones >= 1, "Lock não funcionou — dois ciclos rodaram simultaneamente"
```

### 14.3 Checklist de Implementação

**FASE 1 — Fundação (Obrigatório antes de qualquer outra coisa):**

- [ ] Criar arquivo `brasileira/homepage/state.py` com todos os Pydantic models
- [ ] Criar `brasileira/homepage/candidatos.py` com `ColetorCandidatos`
- [ ] Corrigir timezone: TODA comparação de data usa `ZoneInfo("UTC")`
- [ ] Criar `brasileira/homepage/scorer.py` com score objetivo + LLM PREMIUM
- [ ] Verificar: `task_type="homepage_scoring"` → SmartLLMRouter Tier PREMIUM
- [ ] Criar `brasileira/homepage/layout.py` com `DecidorLayout`
- [ ] Criar `brasileira/homepage/compositor.py` com `Compositor`
- [ ] Criar `brasileira/homepage/aplicador.py` com diff atômico (NUNCA clear-all)
- [ ] Implementar lock Redis `adquirir_lock_ciclo()` com TTL 120s
- [ ] Executar testes unitários: `pytest tests/test_curador_homepage.py`

**FASE 2 — WordPress (ACF + Templates PHP):**

- [ ] Criar `brasileira/wordpress/acf-setup.php` e registrar no WordPress
- [ ] Verificar no admin: ACF Options Page aparece no menu "Homepage"
- [ ] Criar `brasileira/wordpress/template-homepage.php`
- [ ] Criar todos os templates de zona: `zones/breaking-fullwidth.php`, `zones/manchete-padrao.php`, `zones/manchete-ampla.php`, `zones/destaques-grid.php`, `zones/editoria-carrossel.php`, `zones/mais-lidas.php`, `zones/opiniao.php`, `zones/regional.php`
- [ ] Testar template: homepage exibe corretamente com dados fake no ACF
- [ ] Verificar: modo BREAKING exibe banner vermelho full-width
- [ ] Verificar: modo AMPLO exibe manchete sem sidebar

**FASE 3 — Agente LangGraph:**

- [ ] Criar `brasileira/agents/curador_homepage.py` com `CuradorHomepageV3`
- [ ] Compilar StateGraph com 6 etapas
- [ ] Implementar consumers Kafka: `article-published` e `breaking-candidate`
- [ ] Implementar loop periódico com frequência adaptativa
- [ ] Criar tabelas PostgreSQL: `curador_cycles`, `homepage_performance`
- [ ] Testar producer Kafka: `homepage-updates` publicado após ciclo

**FASE 4 — Integração e Produção:**

- [ ] Executar teste de integração em staging
- [ ] Verificar: homepage atualiza a cada 15 min em produção
- [ ] Monitorar: log do PostgreSQL `curador_cycles` cresce conforme esperado
- [ ] Verificar: modo breaking ativa corretamente ao receber `breaking-candidate`
- [ ] Verificar: lock Redis funciona (simular dois ciclos simultâneos)
- [ ] Verificar: diversidade editorial nos destaques (no máximo 1 de cada editoria)
- [ ] Verificar: score LLM usa PREMIUM (verificar via `llm_provider` no log)
- [ ] Configurar systemd ou Docker para reinicialização automática

**FASE 5 — Qualidade:**

- [ ] Verificar: nenhuma homepage vazia durante atualização (diff atômico)
- [ ] Verificar: manchete SEMPRE tem imagem
- [ ] Verificar: timezone UTC em todas as comparações de data
- [ ] Verificar: credenciais APENAS em variáveis de ambiente (nunca hardcoded)
- [ ] Monitorar CTR da manchete nas primeiras 24h de produção
- [ ] Ajustar thresholds de layout se necessário (baseado em dados reais)

---

## REFERÊNCIAS E CONTEXTO ADICIONAL

### Decisões Arquiteturais Explicadas

**Por que ACF Options e não tags WordPress?**
As tags do WordPress são metadados públicos de posts. Ao usar tags para controlar a homepage (abordagem V2), cada post fica marcado com tags como `home-manchete`, que são visíveis no front-end e poluem os metadados SEO. O ACF Options Page é uma página de configurações globais, invisível ao visitante, projetada exatamente para armazenar configurações de site como zonas da homepage.

**Por que diff atômico e não clear+apply?**
A V2 causava uma janela de 30-90s com homepage vazia (race condition grave). O diff atômico calcula a diferença entre o estado anterior e o novo, e atualiza apenas os campos que mudaram. Não há janela de inconsistência: o estado transita de um estado válido para outro estado válido diretamente.

**Por que LLM PREMIUM e não econômico ou local?**
A homepage é o produto editorial mais visível do portal. Uma curadoria ruim (artigo não-relevante como manchete) é percebida imediatamente por qualquer visitante. Modelos econômicos têm capacidade de raciocínio editorial inferior: não conseguem avaliar nuances de importância jornalística, contexto político, impacto econômico e equilíbrio de cobertura com a mesma profundidade que modelos PREMIUM.

**Por que ciclo de 15 min e não tempo real?**
Ciclos muito frequentes consomem chamadas LLM desnecessariamente. Ciclos muito lentos deixam a homepage desatualizada. 15 minutos é o equilíbrio: a cada 15 minutos são publicados em média 4-8 novos artigos no portal, justificando uma reavaliação completa. Para breaking news, o modo reativo (consumer Kafka) garante atualização imediata independente do ciclo periódico.

### Padrões de Referência Externos

- **NYT Algorithms (2024):** O New York Times incorpora julgamento editorial em algoritmos via "Exposure Boosting" (artigo começa no topo e gradualmente desce) e "Pinning" (editor pode fixar artigo). A V3 simula isso via score_total decaindo com o tempo (frescor).

- **NZ Herald Top News Model (2024):** Desenvolveu Q-scores (quality scores) combinando CTR previsto e taxa de conversão. Resultou em 14% mais CTR e 19% mais cliques totais. A V3 adota abordagem similar com `score_objetivo + score_llm`.

- **ACF PRO REST API:** Atualização de campos Options via `POST /wp-json/acf/v3/options/{slug}` com payload `{"fields": {campo: valor}}`. Autenticação via Application Password do WordPress (nativo desde WP 5.6).

---

*Este briefing compila análise de código V2 (17 arquivos, 329 bugs catalogados), pesquisa extensiva sobre homepages dinâmicas de grandes portais (NYT, NZ Herald, G1, Folha), padrões ACF PRO REST API (2025-2026), e as diretrizes arquiteturais da brasileira.news V3. Cada decisão aqui foi motivada por bugs reais em produção ou benchmarking de portais TIER-1.*
