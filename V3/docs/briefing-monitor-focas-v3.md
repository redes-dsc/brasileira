# Briefing Completo para IA — Monitor Sistema + Focas V3

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #12 (Observabilidade e Gerenciamento de Fontes)
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / LangGraph / asyncio / aiohttp / Redis / PostgreSQL / Kafka
**Componentes:** `brasileira/agents/monitor_sistema.py` + `brasileira/agents/focas.py` + módulos de observabilidade

---

## LEIA ISTO PRIMEIRO — Por que estes são os Componentes #12

O **Monitor Sistema** e o **Focas** são os olhos e ouvidos da brasileira.news V3. Sem eles, o sistema é cego: publica artigos sem saber se a cobertura está completa, coleta feeds sem saber se as fontes estão vivas, e cresce sem descobrir novas fontes.

**São dois agentes distintos num único briefing porque compartilham filosofia:**
1. Ambos são **guardiões do throughput**, não auditores de custo.
2. Ambos **nunca bloqueiam** — observam, alertam, ajustam.
3. Ambos operam em **loop contínuo e autônomo**, sem precisar de gatilho externo.

**O Monitor Sistema responde a duas perguntas simples:**
- *"O sistema está publicando?"* — se < 20 artigos/hora, algo está errado.
- *"A cobertura está completa?"* — se alguma das 16 editorias ficou sem artigo em 2h, alerta.

**O Focas garante que as 648+ fontes estejam sempre sendo monitoradas** — nunca desativadas, apenas com frequência de polling ajustada, e descobrindo novas fontes via citações em artigos publicados.

**Este briefing contém TUDO que você precisa.** Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ QUEBRADO NA V2

### 1.1 Monitor V2 (`monitor-16.py`): Foco Errado em Custos

O Monitor V2 tem **seis etapas** em sua máquina de estados:

```
check_agents → collect_metrics → analyze_costs → detect_anomalies → generate_alerts → compile_report
```

O problema não é o fluxo — é a **prioridade errada**. A etapa `analyze_costs` é a terceira mais importante no workflow, com constantes como `DAILY_BUDGET_USD = 10.0` e `COST_SPIKE_MULTIPLIER = 2.0`. O system prompt inclui "CONTROLE DE CUSTOS" como responsabilidade central.

**Problemas fatais do Monitor V2:**

| # | Problema | Impacto |
|---|----------|---------|
| 1 | `DAILY_BUDGET_USD = 10.0` — custo como limite operacional | Pode bloquear publicação se orçamento for atingido |
| 2 | `analyze_costs` como etapa central do workflow | Custo consome tempo de ciclo que deveria ser gasto em throughput |
| 3 | `MIN_ARTICLES_PER_HOUR = 1` — threshold absurdamente baixo | Sistema publica 40+/hora; alerta só com 1 é inútil |
| 4 | System prompt: "CONTROLE DE CUSTOS" como responsabilidade #3 | Filosofia errada: custo é informação, não métrica de controle |
| 5 | Sem verificação de cobertura por editoria | Pode passar horas sem artigos em "Esportes" e ninguém sabe |
| 6 | `STALE_AGENT_THRESHOLD = 120s` — sem gradação | 2 minutos de silêncio = agente "stale", mas pode ser carga normal |
| 7 | Sem integração com Kafka para métricas em tempo real | Polled do PostgreSQL, latência de até 60s para detectar parada |
| 8 | Sem tracking de SLO de throughput | Sem conceito de "burn rate" de artigos |

**Código problemático do Monitor V2:**

```python
# ERRADO: custo como variável de controle
class MonitorConfig:
    DAILY_BUDGET_USD = 10.0          # ← NUNCA deve ser limite
    COST_SPIKE_MULTIPLIER = 2.0      # ← informação, não alarme
    MIN_ARTICLES_PER_HOUR = 1        # ← threshold inútil (sistema faz 40+)

# ERRADO: system prompt foca em custo
"""
3. CONTROLE DE CUSTOS
   - Rastrear gastos por tier (Premium, Redação, Econômico)
   - Detectar picos de custo anormais
   - Comparar com orçamento diário   ← NUNCA deve bloquear
"""

# ERRADO: etapa de análise de custo no caminho crítico
self.graph.add_edge("collect_metrics", "analyze_costs")   # custo no workflow principal
self.graph.add_edge("analyze_costs", "detect_anomalies")  # blocos em sequência
```

### 1.2 Focas V2 (`focas-8.py`): DESATIVA Fontes — Proibido

O Focas V2 tem a lógica mais perigosa do sistema: **desativa automaticamente fontes "mortas"**.

```python
# PROIBIDO — Constante que NUNCA deve existir no V3
PRODUCTIVITY_DEAD_DAYS = 7   # 0 artigos por 7 dias = fonte "morta"
INTERVAL_DEAD_THRESHOLD = 7200  # 2 horas antes da desativação
```

O workflow V2 inclui:
```python
# PROIBIDO — lógica de desativação
if category == "dead" or consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
    deactivated_sources.append({...})

# E depois no update_catalog:
await catalog.deactivate(source_id, f"Auto-deactivated: {reason}")
```

**Problemas fatais do Focas V2:**

| # | Problema | Impacto |
|---|----------|---------|
| 1 | `PRODUCTIVITY_DEAD_DAYS = 7` — fonte sem artigo em 7 dias = desativada | Viola Regra #2: NUNCA desativar fonte. Pode perder fonte sazonal |
| 2 | `deactivated_sources` como campo de estado | A própria existência do campo normaliza desativação |
| 3 | Fast-path para desativação quando há problemas críticos | Falhas HTTP transitórias podem causar desativação permanente |
| 4 | `MAX_CONSECUTIVE_FAILURES = 5` → desativa | 5 falhas de rede = fonte desativada. Servidor pode ter voltado |
| 5 | Rota condicional `health_check → update_catalog` bypassa análise | Desativação sem análise de produtividade histórica |
| 6 | `PRODUCTIVITY_DEAD_DAYS` é conceito errado | Fonte de nicho pode não publicar por semanas e não estar "morta" |
| 7 | Sem discovery via Kafka `article-published` | Discovery baseado em batch, não em tempo real |
| 8 | `INTERVAL_DEAD_THRESHOLD = 7200` para fontes lentas | 2h é arbitrário; algumas fontes publicam mensalmente |

### 1.3 Resumo: O Que Muda Completamente no V3

| Componente | V2 (ERRADO) | V3 (CORRETO) |
|------------|-------------|--------------|
| Monitor: foco principal | Custos | Throughput e cobertura |
| Monitor: threshold | 1 artigo/hora | 20 artigos/hora (alerta), 40/hora (SLO) |
| Monitor: custo | Limite operacional | Informação em relatório |
| Monitor: cobertura | Não verificada | 16 editorias monitoradas a cada ciclo |
| Focas: fontes mortas | Desativa após 7 dias | NUNCA desativa — ajusta frequência para 24h |
| Focas: falhas consecutivas | 5 falhas → desativa | 5+ falhas → intervalo máximo (24h), nunca desativa |
| Focas: discovery | Batch periódico | Tempo real via Kafka `article-published` |
| Focas: conceito de "dead" | Existe no código | ELIMINADO — não existe fonte morta |

---

## PARTE II — ARQUITETURA V3: VISÃO GERAL

### 2.1 Dois Agentes, Uma Filosofia

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    brasileira.news V3 — Observabilidade                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────┐ │
│  │      MONITOR SISTEMA         │  │            FOCAS                 │ │
│  │   (Ciclo: 60s)               │  │   (Ciclo: 10min fontes ativas)   │ │
│  │                              │  │                                  │ │
│  │  "Está publicando?"          │  │  "Fontes estão vivas?"           │ │
│  │  "Cobertura completa?"       │  │  "Polling ajustado?"             │ │
│  │  "Agentes OK?"               │  │  "Novas fontes descobertas?"     │ │
│  │                              │  │                                  │ │
│  │  → Alerta se throughput cai  │  │  → NUNCA desativa fontes         │ │
│  │  → Informa custo (não bloqueia)  │  → Ajusta frequência (min-max) │ │
│  │  → Dashboard em tempo real   │  │  → Discovery via citações        │ │
│  └──────────────────────────────┘  └──────────────────────────────────┘ │
│                                                                         │
│  Inputs:                           Inputs:                              │
│  • Kafka: article-published        • PostgreSQL: tabela fontes          │
│  • Kafka: homepage-updates         • Kafka: article-published           │
│  • Redis: agent:*:heartbeat        • HTTP: HEAD/GET por fonte           │
│  • PostgreSQL: artigos, llm_health │                                    │
│                                                                         │
│  Outputs:                          Outputs:                             │
│  • Redis: monitor:dashboard        • PostgreSQL: fontes (interval)      │
│  • Alertas estruturados (log)      • Redis: focas:health_report         │
│  • Métricas Prometheus             • Alertas fontes críticas            │
│  • Custo em relatório (só info)    • Novas fontes → tabela fontes       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Fluxo do Monitor Sistema V3

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  check_      │    │  check_          │    │  check_         │
│  throughput  │───▶│  coverage        │───▶│  agents         │
│  (Kafka)     │    │  (16 editorias)  │    │  (Redis)        │
└─────────────┘    └──────────────────┘    └─────────────────┘
                                                    │
                   ┌──────────────────┐    ┌────────▼────────┐
                   │  compile_        │◀───│  collect_       │
                   │  dashboard       │    │  cost_info      │
                   │  (Redis)         │    │  (só relatório) │
                   └──────────────────┘    └─────────────────┘
                          │
                   ┌──────▼──────────┐
                   │  generate_      │
                   │  alerts         │
                   └─────────────────┘
```

### 2.3 Fluxo do Focas V3

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  health_    │    │  adapt_          │    │  discover_      │
│  check_     │───▶│  frequency       │───▶│  sources        │
│  sources    │    │  (NUNCA desativa)│    │  (Kafka)        │
└─────────────┘    └──────────────────┘    └─────────────────┘
                                                    │
                   ┌──────────────────┐    ┌────────▼────────┐
                   │  publish_        │◀───│  update_        │
                   │  report          │    │  catalog        │
                   └─────────────────┘    └─────────────────┘
```

### 2.4 Posição no Pipeline Geral

```
article-published (Kafka)
         │
         ├──▶ Monitor Sistema  (consome: contagem por editoria, por hora)
         │
         └──▶ Focas (consome: citações em artigos para discovery)

Redis (agent:*:heartbeat)
         │
         └──▶ Monitor Sistema  (verifica saúde dos 10 agentes)

HTTP (fontes RSS/scrapers)
         │
         └──▶ Focas  (health check direto nas URLs)
```

---

## PARTE III — MONITOR SISTEMA: HEALTH CHECKS

### 3.1 Conceito: Três Perguntas Fundamentais

O Monitor Sistema só precisa responder três perguntas a cada ciclo de 60 segundos:

```
1. "Está publicando?"    → throughput de artigos/hora ≥ 20?
2. "Cobertura completa?" → todas as 16 editorias têm artigos recentes?
3. "Agentes OK?"         → todos os agentes estão com heartbeat recente?
```

Se a resposta a qualquer uma for "não" → **alerta imediato**. Sem debates de custo.

### 3.2 Health Check de Throughput (Prioridade #1)

O throughput é medido por janelas deslizantes diretamente do Kafka consumer, não via polling do PostgreSQL:

```python
# SLO de throughput — adaptado de OneUptime SLO patterns (2026)
THROUGHPUT_SLO = {
    "target_per_hour": 40,           # SLO: 40 artigos/hora
    "alert_threshold": 20,           # Alerta: < 20/hora
    "critical_threshold": 5,         # Crítico: < 5/hora
    "window_minutes": 60,            # Janela de medição
    "short_window_minutes": 15,      # Janela curta para detecção rápida
}

# Burn rate de artigos (analogia com SLO burn rates)
# Se o sistema está em "burn rate" negativo = publicando menos do que deveria
def calculate_article_burn_rate(
    current_rate: float,         # artigos/hora atual
    target_rate: float = 40.0    # SLO target
) -> float:
    """
    Burn rate > 1.0 = publicando acima do esperado (ótimo)
    Burn rate < 1.0 = publicando abaixo do SLO (problema)
    Burn rate < 0.5 = crítico (< 50% do SLO)
    """
    if target_rate == 0:
        return 0.0
    return current_rate / target_rate
```

### 3.3 Health Check de Cobertura por Editoria (Prioridade #2)

**OBRIGATÓRIO:** Verificar todas as 16 macrocategorias a cada ciclo. Se qualquer editoria ficou 2 horas sem artigo → alerta WARNING.

```python
# 16 macrocategorias V3 — devem ser verificadas no health check
EDITORIAS_V3 = [
    "Política", "Economia", "Esportes", "Tecnologia",
    "Saúde", "Educação", "Ciência", "Cultura/Entretenimento",
    "Mundo/Internacional", "Meio Ambiente", "Segurança/Justiça",
    "Sociedade", "Brasil", "Regionais", "Opinião/Análise",
    "Últimas Notícias"
]

COVERAGE_GAP_ALERT_MINUTES = 120   # Alerta se editoria ficou 2h sem artigo
COVERAGE_GAP_CRITICAL_MINUTES = 240  # Crítico: 4h sem cobertura
```

### 3.4 Health Check de Agentes (Prioridade #3)

Os 10 agentes V3 devem ter heartbeat no Redis a cada 30 segundos:

```python
AGENTES_V3 = [
    "reporter", "fotografo", "revisor", "consolidador",
    "curador_homepage", "pauteiro", "editor_chefe",
    "monitor_concorrencia", "monitor_sistema", "focas"
]

# Thresholds de staleness por tipo de agente
HEARTBEAT_STALE_SECONDS = {
    "reporter": 120,          # Reporter: alerta após 2 min de silêncio
    "fotografo": 180,         # Fotógrafo: mais tolerante (APIs lentas)
    "revisor": 300,           # Revisor: ciclos mais longos
    "consolidador": 300,      # Consolidador: pode processar temas complexos
    "curador_homepage": 120,  # Curador: alerta rápido (homepage crítica)
    "pauteiro": 600,          # Pauteiro: ciclos de análise longos
    "editor_chefe": 900,      # Editor-Chefe: observador, ciclos lentos
    "monitor_concorrencia": 180,  # Monitor Concorrência: ciclo médio
    "monitor_sistema": 120,   # O próprio Monitor: se silencia, alerta
    "focas": 600,             # Focas: ciclos de 10min são normais
}
```

---

## PARTE IV — MONITOR SISTEMA: MÉTRICAS DE THROUGHPUT

### 4.1 Métricas-Alvo V3

Tabela completa de métricas, thresholds e alertas conforme especificado na Parte XI do briefing principal:

| Métrica | SLO Alvo | Alerta WARNING | Alerta CRITICAL |
|---------|----------|----------------|-----------------|
| Artigos publicados/hora | ≥ 40 | < 20 | < 5 |
| Tempo médio de publicação | < 60s | > 120s | > 300s |
| Fontes processadas/ciclo | 648+ | < 600 | < 500 |
| Taxa de sucesso LLM | > 95% | < 90% | < 70% |
| Artigos sem imagem | 0% | > 5% | > 20% |
| Cobertura (16 editorias) | 100% | 1+ com 0 em 2h | 1+ com 0 em 4h |
| Latência homepage update | < 2min | > 5min | > 15min |
| Health score LLM mínimo | > 50 | < 30 | < 10 |

### 4.2 Coleta de Métricas via Kafka Consumer

**OBRIGATÓRIO:** O Monitor deve consumir o tópico `article-published` em tempo real para calcular throughput com precisão máxima:

```python
class ThroughputTracker:
    """
    Rastreador de throughput usando janelas deslizantes.
    Adaptado de RateBasedThroughputTracker (OneUptime, 2026).
    """
    
    def __init__(self):
        # Janela de 60 minutos com timestamps individuais
        self._timestamps_60min: deque = deque()
        # Janela de 15 minutos para detecção rápida
        self._timestamps_15min: deque = deque()
        # Contador por editoria com timestamp do último artigo
        self._last_by_editoria: Dict[str, datetime] = {}
        # Lock para thread safety
        self._lock = asyncio.Lock()
    
    async def record_article(self, editoria: str, published_at: datetime):
        """Registra um artigo publicado."""
        async with self._lock:
            now = published_at or datetime.utcnow()
            self._timestamps_60min.append(now)
            self._timestamps_15min.append(now)
            self._last_by_editoria[editoria] = now
            self._cleanup(now)
    
    def _cleanup(self, now: datetime):
        """Remove timestamps fora das janelas."""
        cutoff_60 = now - timedelta(minutes=60)
        cutoff_15 = now - timedelta(minutes=15)
        while self._timestamps_60min and self._timestamps_60min[0] < cutoff_60:
            self._timestamps_60min.popleft()
        while self._timestamps_15min and self._timestamps_15min[0] < cutoff_15:
            self._timestamps_15min.popleft()
    
    def get_rate_per_hour(self) -> float:
        """Artigos publicados na última hora."""
        now = datetime.utcnow()
        self._cleanup(now)
        return len(self._timestamps_60min)
    
    def get_rate_last_15min_projected(self) -> float:
        """Taxa dos últimos 15min projetada para 1 hora."""
        now = datetime.utcnow()
        self._cleanup(now)
        return len(self._timestamps_15min) * 4  # 15min × 4 = 1h
    
    def get_coverage_gaps(
        self,
        editorias: List[str],
        gap_minutes: int = 120
    ) -> List[Dict[str, Any]]:
        """Retorna editorias sem artigo nos últimos N minutos."""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=gap_minutes)
        gaps = []
        for editoria in editorias:
            last = self._last_by_editoria.get(editoria)
            if last is None or last < cutoff:
                minutes_ago = None
                if last:
                    minutes_ago = int((now - last).total_seconds() / 60)
                gaps.append({
                    "editoria": editoria,
                    "last_article_at": last.isoformat() if last else None,
                    "minutes_since_last": minutes_ago,
                    "never_published": last is None,
                })
        return gaps
```

### 4.3 Cálculo de Burn Rate de Throughput

```python
def calculate_throughput_health(
    rate_last_hour: float,
    rate_last_15min_projected: float,
    target_per_hour: float = 40.0,
) -> Dict[str, Any]:
    """
    Calcula saúde do throughput com duas janelas (padrão SRE/SLO 2026).
    
    Usa two-window approach:
    - Janela longa (1h): burn rate sustentado
    - Janela curta (15min projetada): detecção rápida de queda
    """
    burn_rate_1h = rate_last_hour / target_per_hour if target_per_hour > 0 else 0
    burn_rate_15m = rate_last_15min_projected / target_per_hour if target_per_hour > 0 else 0
    
    # Severidade baseada em duas janelas (evita falsos positivos de spike)
    if burn_rate_1h < 0.125 and burn_rate_15m < 0.125:
        # Crítico: < 12.5% do SLO em AMBAS as janelas
        severity = "CRITICAL"
    elif burn_rate_1h < 0.5 and burn_rate_15m < 0.5:
        # Warning: < 50% do SLO em AMBAS as janelas
        severity = "WARNING"
    elif burn_rate_1h < 1.0 or burn_rate_15m < 0.5:
        # Info: abaixo do SLO mas ainda aceitável
        severity = "INFO"
    else:
        severity = "OK"
    
    return {
        "rate_last_hour": rate_last_hour,
        "rate_last_15min_projected": rate_last_15min_projected,
        "target_per_hour": target_per_hour,
        "burn_rate_1h": round(burn_rate_1h, 3),
        "burn_rate_15m": round(burn_rate_15m, 3),
        "severity": severity,
        "meets_slo": burn_rate_1h >= 1.0,
    }
```

### 4.4 Métricas de Qualidade de Pipeline

```python
async def collect_pipeline_quality(
    pg: asyncpg.Connection,
    window_hours: int = 1
) -> Dict[str, Any]:
    """
    Coleta métricas de qualidade do pipeline nas últimas N horas.
    Custo é INFORMAÇÃO apenas — nunca usado como bloqueio.
    """
    since = datetime.utcnow() - timedelta(hours=window_hours)
    
    # Artigos sem imagem
    row = await pg.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE wp_post_id IS NOT NULL) as total_published,
            COUNT(*) FILTER (WHERE imagem_url IS NULL AND wp_post_id IS NOT NULL) as sem_imagem,
            AVG(EXTRACT(EPOCH FROM (publicado_em - criado_em))) as avg_latency_sec,
            AVG(score_relevancia) as avg_relevancia
        FROM artigos
        WHERE criado_em >= $1
    """, since)
    
    total = row['total_published'] or 0
    sem_imagem = row['sem_imagem'] or 0
    pct_sem_imagem = (sem_imagem / total * 100) if total > 0 else 0
    
    # Health LLM por provedor (INFORMAÇÃO, não bloqueio)
    llm_rows = await pg.fetch("""
        SELECT
            provider,
            model,
            COUNT(*) as total_calls,
            AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as success_rate,
            AVG(latency_ms) as avg_latency_ms,
            SUM(custo_usd) as total_cost_usd  -- só informação
        FROM llm_health_log
        WHERE timestamp >= $1
        GROUP BY provider, model
        ORDER BY total_calls DESC
    """, since)
    
    llm_health = []
    total_cost_usd = 0.0  # informação para relatório
    for r in llm_rows:
        total_cost_usd += float(r['total_cost_usd'] or 0)
        llm_health.append({
            "provider": r['provider'],
            "model": r['model'],
            "total_calls": r['total_calls'],
            "success_rate": round(float(r['success_rate'] or 0), 3),
            "avg_latency_ms": round(float(r['avg_latency_ms'] or 0)),
            "cost_usd": round(float(r['total_cost_usd'] or 0), 4),  # só info
        })
    
    return {
        "window_hours": window_hours,
        "total_published": total,
        "sem_imagem": sem_imagem,
        "pct_sem_imagem": round(pct_sem_imagem, 2),
        "avg_latency_sec": round(float(row['avg_latency_sec'] or 0), 1),
        "avg_relevancia": round(float(row['avg_relevancia'] or 0), 2),
        "llm_health": llm_health,
        # CUSTO: só informação, nunca bloqueio
        "cost_info": {
            "total_usd_last_hour": round(total_cost_usd, 4),
            "note": "Informativo apenas. Nunca bloqueia publicação."
        },
    }
```

---

## PARTE V — MONITOR SISTEMA: SISTEMA DE ALERTAS

### 5.1 Taxonomia de Alertas V3

**REGRA INVIOLÁVEL:** Nenhum alerta pode interromper o pipeline de publicação. Alertas são notificações, nunca bloqueios.

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class AlertSeverity(Enum):
    INFO = "INFO"        # Informativo — sem ação necessária
    WARNING = "WARNING"  # Atenção — investigar nas próximas horas
    CRITICAL = "CRITICAL"  # Urgente — investigar imediatamente

class AlertType(Enum):
    # Monitor Sistema
    THROUGHPUT_LOW = "throughput_low"          # < 20 artigos/hora
    THROUGHPUT_CRITICAL = "throughput_critical" # < 5 artigos/hora
    COVERAGE_GAP = "coverage_gap"              # Editoria sem artigo em 2h
    COVERAGE_CRITICAL = "coverage_critical"     # Editoria sem artigo em 4h
    AGENT_STALE = "agent_stale"                # Agente sem heartbeat
    AGENT_DOWN = "agent_down"                  # Agente offline confirmado
    LLM_DEGRADED = "llm_degraded"             # Health score LLM baixo
    NO_IMAGE_SPIKE = "no_image_spike"          # Spike de artigos sem imagem
    PIPELINE_LATENCY = "pipeline_latency"      # Latência média alta
    # Focas
    SOURCE_UNREACHABLE = "source_unreachable"  # Fonte sem resposta por 1h
    SOURCE_CLUSTER_DOWN = "source_cluster_down" # 10+ fontes do mesmo domínio offline
    NEW_SOURCE_CANDIDATE = "new_source_candidate"  # Nova fonte encontrada
    DISCOVERY_BATCH = "discovery_batch"        # Lote de novas fontes para review

@dataclass
class Alert:
    """Alerta estruturado do Monitor Sistema ou Focas."""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    # NUNCA bloqueia — apenas informa
    blocks_pipeline: bool = False  # SEMPRE False. Sempre.
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "blocks_pipeline": self.blocks_pipeline,  # sempre False
        }
```

### 5.2 Regras de Geração de Alertas

```python
class AlertGenerator:
    """Gera alertas baseados em métricas de throughput e cobertura."""
    
    def generate_throughput_alerts(
        self,
        throughput_health: Dict[str, Any]
    ) -> List[Alert]:
        alerts = []
        rate = throughput_health["rate_last_hour"]
        severity = throughput_health["severity"]
        
        if severity == "CRITICAL":
            alerts.append(Alert(
                alert_id=f"thr-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                alert_type=AlertType.THROUGHPUT_CRITICAL,
                severity=AlertSeverity.CRITICAL,
                title=f"CRÍTICO: Apenas {rate:.0f} artigos/hora (SLO: 40)",
                description=(
                    f"Sistema publicou {rate:.0f} artigos na última hora. "
                    f"SLO é 40/hora. Taxa de {throughput_health['burn_rate_1h']:.1%} "
                    f"do target. Investigar IMEDIATAMENTE."
                ),
                context=throughput_health,
                blocks_pipeline=False,  # NUNCA bloqueia
            ))
        elif severity == "WARNING":
            alerts.append(Alert(
                alert_id=f"thr-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                alert_type=AlertType.THROUGHPUT_LOW,
                severity=AlertSeverity.WARNING,
                title=f"Throughput baixo: {rate:.0f} artigos/hora",
                description=(
                    f"Sistema está publicando abaixo do SLO. "
                    f"Atual: {rate:.0f}/hora, Target: 40/hora."
                ),
                context=throughput_health,
                blocks_pipeline=False,
            ))
        
        return alerts
    
    def generate_coverage_alerts(
        self,
        coverage_gaps: List[Dict[str, Any]]
    ) -> List[Alert]:
        alerts = []
        
        for gap in coverage_gaps:
            editoria = gap["editoria"]
            minutes = gap.get("minutes_since_last")
            
            if gap.get("never_published"):
                severity = AlertSeverity.WARNING
                title = f"Editoria '{editoria}' nunca publicou"
            elif minutes and minutes >= 240:
                severity = AlertSeverity.CRITICAL
                title = f"CRÍTICO: '{editoria}' sem artigo há {minutes}min"
            elif minutes and minutes >= 120:
                severity = AlertSeverity.WARNING
                title = f"'{editoria}' sem artigo há {minutes}min"
            else:
                continue  # Ainda dentro do threshold
            
            alerts.append(Alert(
                alert_id=f"cov-{editoria[:3]}-{datetime.utcnow().strftime('%H%M%S')}",
                alert_type=(
                    AlertType.COVERAGE_CRITICAL
                    if severity == AlertSeverity.CRITICAL
                    else AlertType.COVERAGE_GAP
                ),
                severity=severity,
                title=title,
                description=f"Editoria '{editoria}' não tem cobertura recente.",
                context=gap,
                blocks_pipeline=False,
            ))
        
        return alerts
    
    def generate_agent_alerts(
        self,
        agent_statuses: Dict[str, Dict[str, Any]]
    ) -> List[Alert]:
        alerts = []
        
        for agent_id, status in agent_statuses.items():
            age_seconds = status.get("age_seconds", 0)
            agent_type = status.get("agent_type", "unknown")
            threshold = HEARTBEAT_STALE_SECONDS.get(agent_type, 300)
            
            if age_seconds > threshold * 3:
                # Mais de 3x o threshold = provavelmente offline
                alerts.append(Alert(
                    alert_id=f"agt-{agent_id}-{datetime.utcnow().strftime('%H%M%S')}",
                    alert_type=AlertType.AGENT_DOWN,
                    severity=AlertSeverity.CRITICAL,
                    title=f"Agente {agent_id} pode estar OFFLINE ({age_seconds:.0f}s sem heartbeat)",
                    description=f"Agente {agent_type} não reporta há {age_seconds:.0f}s (threshold: {threshold}s).",
                    context=status,
                    blocks_pipeline=False,
                ))
            elif age_seconds > threshold:
                alerts.append(Alert(
                    alert_id=f"agt-{agent_id}-{datetime.utcnow().strftime('%H%M%S')}",
                    alert_type=AlertType.AGENT_STALE,
                    severity=AlertSeverity.WARNING,
                    title=f"Agente {agent_id} sem heartbeat recente ({age_seconds:.0f}s)",
                    description=f"Agente {agent_type} não reporta há {age_seconds:.0f}s.",
                    context=status,
                    blocks_pipeline=False,
                ))
        
        return alerts
```

### 5.3 Deduplicação e Rate Limiting de Alertas

```python
class AlertDeduplicator:
    """
    Evita flood de alertas do mesmo tipo.
    Padrão inspirado em alert fatigue reduction (IBM, LogicMonitor 2026).
    """
    
    def __init__(self, redis_client):
        self._redis = redis_client
        # Cooldown por tipo de alerta (segundos)
        self._cooldowns = {
            AlertType.THROUGHPUT_CRITICAL: 300,    # 5min entre alertas críticos de throughput
            AlertType.THROUGHPUT_LOW: 900,          # 15min entre warnings de throughput
            AlertType.COVERAGE_GAP: 1800,           # 30min entre gaps por editoria
            AlertType.COVERAGE_CRITICAL: 600,       # 10min entre críticos por editoria
            AlertType.AGENT_DOWN: 180,              # 3min entre alertas de agente offline
            AlertType.AGENT_STALE: 600,             # 10min entre stale alerts
            AlertType.SOURCE_UNREACHABLE: 3600,     # 1h entre alertas por fonte
            AlertType.SOURCE_CLUSTER_DOWN: 1800,    # 30min entre cluster alerts
        }
    
    async def should_send(self, alert: Alert, context_key: str = "") -> bool:
        """
        Verifica se alerta deve ser enviado (não está em cooldown).
        context_key: chave adicional para dedup por contexto (ex: nome da editoria)
        """
        dedup_key = f"alert:dedup:{alert.alert_type.value}:{context_key}"
        cooldown = self._cooldowns.get(alert.alert_type, 300)
        
        existing = await self._redis.get(dedup_key)
        if existing:
            return False
        
        await self._redis.setex(dedup_key, cooldown, "1")
        return True
```

---

## PARTE VI — MONITOR SISTEMA: DASHBOARD TEMPO REAL

### 6.1 Estrutura do Dashboard Redis

```python
DASHBOARD_KEY = "monitor:dashboard"
DASHBOARD_TTL = 120  # Expira em 2min se Monitor parar

async def update_dashboard(
    redis_client,
    throughput_health: Dict[str, Any],
    coverage_gaps: List[Dict[str, Any]],
    agent_statuses: Dict[str, Any],
    pipeline_quality: Dict[str, Any],
    active_alerts: List[Alert],
) -> None:
    """
    Atualiza dashboard em Redis.
    Formato JSON para consumo por qualquer cliente.
    """
    dashboard = {
        "updated_at": datetime.utcnow().isoformat(),
        "system_status": _calc_system_status(throughput_health, coverage_gaps, active_alerts),
        
        # Throughput (foco principal)
        "throughput": {
            "rate_last_hour": throughput_health["rate_last_hour"],
            "rate_15min_projected": throughput_health["rate_last_15min_projected"],
            "target_per_hour": throughput_health["target_per_hour"],
            "burn_rate": throughput_health["burn_rate_1h"],
            "meets_slo": throughput_health["meets_slo"],
            "status": throughput_health["severity"],
        },
        
        # Cobertura por editoria
        "coverage": {
            "total_editorias": 16,
            "editorias_ok": 16 - len(coverage_gaps),
            "editorias_com_gap": len(coverage_gaps),
            "gaps": coverage_gaps,
        },
        
        # Saúde dos agentes
        "agents": {
            "total": len(agent_statuses),
            "healthy": sum(1 for s in agent_statuses.values() if s.get("health") == "healthy"),
            "stale": sum(1 for s in agent_statuses.values() if s.get("health") == "stale"),
            "details": agent_statuses,
        },
        
        # Qualidade do pipeline
        "pipeline": {
            "total_published_last_hour": pipeline_quality["total_published"],
            "pct_sem_imagem": pipeline_quality["pct_sem_imagem"],
            "avg_latency_sec": pipeline_quality["avg_latency_sec"],
        },
        
        # Custo: INFORMAÇÃO APENAS
        "cost_info": pipeline_quality.get("cost_info", {}),
        
        # Alertas ativos
        "active_alerts": [a.to_dict() for a in active_alerts],
        "alert_counts": {
            "critical": sum(1 for a in active_alerts if a.severity == AlertSeverity.CRITICAL),
            "warning": sum(1 for a in active_alerts if a.severity == AlertSeverity.WARNING),
            "info": sum(1 for a in active_alerts if a.severity == AlertSeverity.INFO),
        },
    }
    
    await redis_client.setex(
        DASHBOARD_KEY,
        DASHBOARD_TTL,
        json.dumps(dashboard, ensure_ascii=False)
    )

def _calc_system_status(
    throughput_health: Dict,
    coverage_gaps: List,
    active_alerts: List[Alert]
) -> str:
    """
    healthy: throughput OK, sem gaps, sem alertas críticos
    degraded: warnings presentes mas publicando
    critical: throughput abaixo de 5/hora OU 4h de gap
    """
    critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]
    if critical_alerts or throughput_health["severity"] == "CRITICAL":
        return "critical"
    
    warning_alerts = [a for a in active_alerts if a.severity == AlertSeverity.WARNING]
    if warning_alerts or throughput_health["severity"] == "WARNING":
        return "degraded"
    
    return "healthy"
```

### 6.2 Métricas Prometheus

```python
# brasileira/observability/metrics.py
from prometheus_client import Counter, Gauge, Histogram, Summary

# Throughput
articles_published_total = Counter(
    "brasileira_articles_published_total",
    "Total de artigos publicados",
    ["editoria"]
)
articles_per_hour = Gauge(
    "brasileira_articles_per_hour",
    "Taxa de artigos publicados na última hora"
)
throughput_burn_rate = Gauge(
    "brasileira_throughput_burn_rate",
    "Burn rate em relação ao SLO de throughput"
)

# Cobertura
coverage_gap_minutes = Gauge(
    "brasileira_coverage_gap_minutes",
    "Minutos desde o último artigo por editoria",
    ["editoria"]
)
editorias_with_gap = Gauge(
    "brasileira_editorias_with_gap_total",
    "Número de editorias sem artigo recente"
)

# Agentes
agent_heartbeat_age_seconds = Gauge(
    "brasileira_agent_heartbeat_age_seconds",
    "Segundos desde o último heartbeat do agente",
    ["agent_type", "agent_id"]
)
agent_health_status = Gauge(
    "brasileira_agent_health_status",
    "Status de saúde do agente (1=healthy, 0=stale)",
    ["agent_type", "agent_id"]
)

# LLM Health
llm_success_rate = Gauge(
    "brasileira_llm_success_rate",
    "Taxa de sucesso das chamadas LLM",
    ["provider", "model"]
)

# Custo (INFORMATIVO APENAS — sem alertas baseados nisto)
llm_cost_usd_total = Counter(
    "brasileira_llm_cost_usd_total",
    "Custo total em USD das chamadas LLM (informativo)",
    ["provider", "tier"]
)

# Focas
source_health_status = Gauge(
    "brasileira_source_health_status",
    "Status de saúde da fonte (1=healthy, 0=unreachable)",
    ["source_id", "source_name"]
)
source_polling_interval_seconds = Gauge(
    "brasileira_source_polling_interval_seconds",
    "Intervalo de polling atual da fonte",
    ["source_id"]
)
source_discovery_total = Counter(
    "brasileira_source_discovery_total",
    "Total de novas fontes descobertas"
)
```

---

## PARTE VII — FOCAS: HEALTH DE FONTES

### 7.1 Filosofia: Fontes Nunca Morrem

**REGRA INVIOLÁVEL:** Uma fonte nunca é desativada automaticamente. Sempre existe uma razão para uma fonte estar temporariamente indisponível:
- Servidor em manutenção
- Fonte sazonal (publica apenas em período eleitoral, Copa do Mundo, etc.)
- Paywall temporário
- Mudança de URL
- Rate limiting

Em vez de desativar, o Focas **aumenta o intervalo de polling até 24 horas** e continua verificando. Se a fonte voltar, volta ao intervalo normal automaticamente.

### 7.2 Health Check Assíncrono Paralelo

```python
# Configuração de health check
HEALTH_CHECK_CONFIG = {
    "timeout_seconds": 15,          # HEAD request timeout
    "get_fallback_timeout": 20,     # GET fallback se HEAD falhar
    "max_concurrent": 50,           # Semáforo: max 50 concurrent checks
    "user_agent": "FocasBot/3.0 (+https://brasileira.news/bot)",
    "retry_on_timeout": 1,          # 1 retry imediato se timeout
    "batch_size": 100,              # Processa em lotes de 100
}

async def health_check_all_sources(
    sources: List[Dict[str, Any]],
    redis_client,
) -> List[SourceHealthResult]:
    """
    Health check paralelo de todas as 648+ fontes.
    Usa semáforo para não overwhelmar a rede.
    """
    semaphore = asyncio.Semaphore(HEALTH_CHECK_CONFIG["max_concurrent"])
    
    timeout = aiohttp.ClientTimeout(
        total=HEALTH_CHECK_CONFIG["timeout_seconds"],
        connect=5,
    )
    headers = {"User-Agent": HEALTH_CHECK_CONFIG["user_agent"]}
    
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        tasks = [
            _check_single_source(session, source, semaphore, redis_client)
            for source in sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Normaliza exceções em resultados de falha
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            source = sources[i]
            final_results.append(SourceHealthResult(
                source_id=source.get("id"),
                source_name=source.get("nome", "unknown"),
                url=source.get("url", ""),
                is_healthy=False,
                status_code=None,
                latency_ms=None,
                error_message=str(result)[:200],
                consecutive_failures=source.get("consecutive_failures", 0) + 1,
                checked_at=datetime.utcnow(),
            ))
        else:
            final_results.append(result)
    
    return final_results

async def _check_single_source(
    session: aiohttp.ClientSession,
    source: Dict[str, Any],
    semaphore: asyncio.Semaphore,
    redis_client,
) -> SourceHealthResult:
    """Health check de uma única fonte com HEAD → GET fallback."""
    
    async with semaphore:
        url = source.get("url", "")
        source_id = source.get("id")
        source_name = source.get("nome", "unknown")
        prev_failures = source.get("consecutive_failures", 0)
        
        result = SourceHealthResult(
            source_id=source_id,
            source_name=source_name,
            url=url,
            is_healthy=False,
            status_code=None,
            latency_ms=None,
            error_message=None,
            consecutive_failures=prev_failures,
            checked_at=datetime.utcnow(),
        )
        
        if not url:
            result.error_message = "URL não configurada"
            return result
        
        start = time.monotonic()
        
        try:
            # Tenta HEAD primeiro (mais leve)
            try:
                async with session.head(url, allow_redirects=True) as resp:
                    result.status_code = resp.status
                    result.is_healthy = 200 <= resp.status < 400
                    result.latency_ms = int((time.monotonic() - start) * 1000)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                # Fallback para GET
                start = time.monotonic()
                async with session.get(url, allow_redirects=True) as resp:
                    result.status_code = resp.status
                    result.is_healthy = 200 <= resp.status < 400
                    result.latency_ms = int((time.monotonic() - start) * 1000)
            
            if result.is_healthy:
                result.consecutive_failures = 0
            else:
                result.consecutive_failures = prev_failures + 1
                result.error_message = f"HTTP {result.status_code}"
        
        except asyncio.TimeoutError:
            result.consecutive_failures = prev_failures + 1
            result.error_message = "Timeout"
        except aiohttp.ClientConnectorError as e:
            result.consecutive_failures = prev_failures + 1
            result.error_message = f"Conexão recusada: {str(e)[:100]}"
        except Exception as e:
            result.consecutive_failures = prev_failures + 1
            result.error_message = f"Erro: {str(e)[:100]}"
        
        # Persiste contador de falhas no Redis para histórico
        if not result.is_healthy:
            await redis_client.setex(
                f"focas:failures:{source_id}",
                86400,  # 24h TTL
                str(result.consecutive_failures)
            )
        else:
            await redis_client.delete(f"focas:failures:{source_id}")
        
        return result
```

### 7.3 Schema do Resultado de Health Check

```python
@dataclass
class SourceHealthResult:
    """Resultado do health check de uma fonte."""
    source_id: str
    source_name: str
    url: str
    is_healthy: bool
    status_code: Optional[int]
    latency_ms: Optional[int]
    error_message: Optional[str]
    consecutive_failures: int
    checked_at: datetime
    
    @property
    def health_tier(self) -> str:
        """
        Classifica a saúde para determinar intervalo de polling.
        NUNCA retorna 'dead' — máximo é 'slow'.
        """
        if self.is_healthy and self.latency_ms and self.latency_ms < 500:
            return "fast"           # Responde rápido → polling agressivo
        elif self.is_healthy:
            return "healthy"        # Responde, mas lento → polling normal
        elif self.consecutive_failures < 3:
            return "flaky"          # Falhas esporádicas → aumenta intervalo
        elif self.consecutive_failures < 10:
            return "degraded"       # Muitas falhas → intervalo maior
        else:
            return "slow"           # 10+ falhas → máximo 24h, mas NUNCA desativa
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "url": self.url,
            "is_healthy": self.is_healthy,
            "health_tier": self.health_tier,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
            "consecutive_failures": self.consecutive_failures,
            "checked_at": self.checked_at.isoformat(),
        }
```

---

## PARTE VIII — FOCAS: ADAPTIVE POLLING

### 8.1 Princípios do Adaptive Polling V3

O sistema de polling adaptativo é baseado em **3 sinais**, não apenas em produtividade histórica:

1. **Health da fonte:** Está respondendo? Qual latência?
2. **Ritmo de publicação:** Publica diariamente, semanalmente, mensalmente?
3. **Tier da fonte:** Fontes VIP têm polling mais agressivo independentemente de ritmo.

**A regra mais importante:** O intervalo máximo absoluto é **24 horas**. Nenhuma fonte fica mais de 24h sem ser verificada. Isso permite detectar quando uma fonte "dormida" volta a publicar.

### 8.2 Tabela de Intervalos de Polling

```python
# Intervalos de polling em segundos — NUNCA desativa
POLLING_INTERVALS = {
    # Por tier de fonte (override de saúde quando VIP)
    "tier_vip": 900,          # 15min — fontes VIP sempre têm polling agressivo
    "tier_alta": 1800,        # 30min — fontes de alta produtividade
    "tier_media": 3600,       # 1h — produtividade média
    "tier_baixa": 7200,       # 2h — produtividade baixa
    "tier_esporadica": 21600, # 6h — publica esporadicamente
    "tier_inativa": 86400,    # 24h — fontes não respondendo (máximo absoluto)
    
    # Por health da fonte (aplicado se não for VIP)
    "health_fast": None,         # Usa intervalo por produtividade (fonte saudável e rápida)
    "health_healthy": None,      # Usa intervalo por produtividade
    "health_flaky": lambda x: min(x * 2, 21600),   # Dobra o intervalo, máx 6h
    "health_degraded": lambda x: min(x * 4, 43200), # 4x o intervalo, máx 12h
    "health_slow": 86400,       # 24h fixo (10+ falhas consecutivas)
}

MAX_POLLING_INTERVAL = 86400    # 24 horas — NUNCA exceder
MIN_POLLING_INTERVAL = 900      # 15 minutos — NUNCA abaixo
```

### 8.3 Algoritmo de Adaptive Polling

```python
class AdaptivePollingEngine:
    """
    Motor de adaptive polling para 648+ fontes.
    Baseado em reactive polling patterns (DEV Community, 2025).
    Inspirado em adaptive RSS fetchers com backoff exponencial.
    
    PRINCÍPIO: Nunca desativa. Apenas ajusta frequência.
    """
    
    def calculate_new_interval(
        self,
        source: Dict[str, Any],
        health_result: SourceHealthResult,
        articles_last_7d: int,
        articles_last_30d: int,
    ) -> Tuple[int, str]:
        """
        Calcula novo intervalo de polling.
        Retorna (intervalo_segundos, justificativa).
        
        Lógica:
        1. Se fonte VIP → máximo 15min independente de tudo
        2. Se fonte com health "slow" (10+ falhas) → 24h, mas mantém ativa
        3. Se fonte com health "degraded" (3-9 falhas) → 4x intervalo base, máx 12h
        4. Se fonte saudável → intervalo baseado em ritmo de publicação
        """
        source_tier = source.get("tier", "standard")
        current_interval = source.get("polling_interval_min", 30) * 60  # para segundos
        
        # 1. VIP override — sempre polling agressivo
        if source_tier in ("vip", "premium"):
            return (MIN_POLLING_INTERVAL, "fonte VIP: intervalo mínimo (15min)")
        
        # 2. Fonte com muitas falhas — backoff máximo mas NUNCA desativa
        health_tier = health_result.health_tier
        if health_tier == "slow":
            # 10+ falhas consecutivas = 24h, mas fonte permanece ATIVA
            return (
                MAX_POLLING_INTERVAL,
                f"fonte com {health_result.consecutive_failures} falhas consecutivas: "
                f"polling reduzido a 24h (NUNCA desativada)"
            )
        
        # 3. Fonte degradada — backoff progressivo
        if health_tier == "degraded":
            base = self._interval_by_productivity(articles_last_7d, articles_last_30d)
            new_interval = min(base * 4, 43200)  # 4x, máx 12h
            return (
                new_interval,
                f"fonte degradada ({health_result.consecutive_failures} falhas): "
                f"intervalo aumentado para {new_interval//3600:.1f}h"
            )
        
        if health_tier == "flaky":
            base = self._interval_by_productivity(articles_last_7d, articles_last_30d)
            new_interval = min(base * 2, 21600)  # 2x, máx 6h
            return (
                new_interval,
                f"fonte instável ({health_result.consecutive_failures} falhas): "
                f"intervalo aumentado para {new_interval//3600:.1f}h"
            )
        
        # 4. Fonte saudável — intervalo por produtividade
        interval = self._interval_by_productivity(articles_last_7d, articles_last_30d)
        
        # Se a fonte estava em backoff e voltou, reduz gradualmente
        if current_interval > interval:
            # Reduz para no máximo 2x o target (recuperação gradual)
            interval = min(current_interval // 2, interval * 2)
        
        return (interval, f"fonte saudável: {articles_last_7d} artigos/7d")
    
    def _interval_by_productivity(
        self,
        articles_7d: int,
        articles_30d: int,
    ) -> int:
        """
        Intervalo baseado em produtividade histórica.
        Quanto mais a fonte publica, mais frequentemente verificamos.
        """
        # Artigos por dia (média dos últimos 30 dias)
        daily_avg = articles_30d / 30.0
        
        if daily_avg >= 5:        # >5 artigos/dia = fonte muito ativa
            return 900            # 15min
        elif daily_avg >= 2:      # 2-5 artigos/dia = fonte ativa
            return 1800           # 30min
        elif daily_avg >= 0.5:    # >3 artigos/semana = produtividade média
            return 3600           # 1h
        elif daily_avg >= 0.1:    # >3 artigos/mês = produtividade baixa
            return 7200           # 2h
        elif articles_30d > 0:    # Pelo menos 1 artigo no mês
            return 21600          # 6h
        else:
            # Sem artigos no último mês — mas NUNCA desativa
            # Pode ser fonte sazonal, verifica uma vez por dia
            return MAX_POLLING_INTERVAL  # 24h
    
    async def apply_adjustments(
        self,
        adjustments: List[Dict[str, Any]],
        pg: asyncpg.Connection,
    ) -> int:
        """Persiste ajustes de polling no PostgreSQL. Retorna total atualizado."""
        if not adjustments:
            return 0
        
        # Atualiza em lote
        updated = 0
        for adj in adjustments:
            source_id = adj["source_id"]
            new_interval_min = adj["new_interval_seconds"] // 60
            
            await pg.execute("""
                UPDATE fontes
                SET
                    polling_interval_min = $1,
                    consecutive_failures = $2,
                    ultimo_check = NOW(),
                    metadata = jsonb_set(
                        COALESCE(metadata, '{}'),
                        '{polling_justificativa}',
                        $3::jsonb
                    )
                WHERE id = $4
            """,
                new_interval_min,
                adj["consecutive_failures"],
                json.dumps(adj["justificativa"]),
                source_id
            )
            updated += 1
        
        return updated
```

### 8.4 Visualização dos Intervalos

```
Fonte VIP (G1, Folha, UOL...):  ████████████████  15min sempre
Alta produtividade (>5/dia):    ████████████████  15min
Média produtividade (2-5/dia):  ████████          30min
Baixa produtividade (<2/dia):   ████              1-2h
Esporádica (<3/mês):            ██                6h
Instável (flaky, 1-2 falhas):   ██████            2x intervalo, máx 6h
Degradada (3-9 falhas):         ████              4x intervalo, máx 12h
Muitas falhas (10+ falhas):     █                 24h (NUNCA desativada)
Sem artigos no mês:             █                 24h (pode ser sazonal)

                                ↑ NUNCA zerado. Fonte permanece sempre ativa.
```

---

## PARTE IX — FOCAS: DISCOVERY DE NOVAS FONTES

### 9.1 Arquitetura do Discovery em Tempo Real

O Focas consome o tópico Kafka `article-published` para extrair citações de fontes em tempo real. Cada artigo publicado pode conter links para fontes ainda não cadastradas no sistema.

```
article-published (Kafka)
        │
        ▼
  [Focas Discovery Consumer]
        │
        ├── Extrai todos os links do artigo
        ├── Filtra: domínios já conhecidos → ignora
        ├── Filtra: links internos brasileira.news → ignora
        ├── Filtra: redes sociais, agregadores → ignora
        │
        ▼
  [Candidate Sources Queue] (Redis)
        │
        ▼
  [Classificação via LLM ECONÔMICO]
        │
        ├── Tipo: portal_noticias / governo / agência / blog / etc.
        ├── Confiabilidade: 1-10
        ├── Relevância: 1-10
        │
        ▼
  [Threshold: relevância >= 7 E confiabilidade >= 6]
        │
        ├── Aprovada → INSERT INTO fontes (em mode "pendente" para review)
        └── Rejeitada → log + ignora
```

### 9.2 Extração de Links de Artigos

```python
import re
from urllib.parse import urlparse, urljoin
from typing import Set

# Domínios a ignorar no discovery
DISCOVERY_IGNORE_DOMAINS = {
    # Redes sociais
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "linkedin.com", "youtube.com", "tiktok.com", "whatsapp.com",
    # Agregadores genéricos
    "google.com", "bing.com", "duckduckgo.com",
    # Próprio sistema
    "brasileira.news",
    # Plataformas de conteúdo (não são fontes jornalísticas)
    "medium.com", "substack.com", "wordpress.com",
    # Wikis
    "wikipedia.org", "wikimedia.org",
    # Buscadores de imagem
    "pexels.com", "unsplash.com", "flickr.com",
}

# Padrões de URL que indicam fonte jornalística (não mídias sociais)
JOURNALISTIC_PATTERNS = [
    r'\.gov\.br',           # Governo federal/estadual/municipal
    r'\.org\.br',           # ONGs e organizações
    r'\.jus\.br',           # Judiciário
    r'\.edu\.br',           # Universidades
    r'\bagencia\b',         # "agencia" no domínio
    r'\bnoticias\b',        # "noticias" no domínio
    r'\bjornal\b',          # "jornal" no domínio
    r'\brevista\b',         # "revista" no domínio
    r'\btribuna\b',         # "tribuna" no domínio
    r'\bgazeta\b',          # "gazeta" no domínio
    r'\bdiario\b',          # "diario" no domínio
    r'\bcorreia\b',         # "correia" no domínio
    r'\bfolha\b',           # "folha" no domínio
    r'\bestadao\b',         # "estadao" no domínio
]

def extract_candidate_sources(
    article: Dict[str, Any],
    known_domains: Set[str],
) -> List[Dict[str, Any]]:
    """
    Extrai candidatos a novas fontes de um artigo publicado.
    
    Args:
        article: Artigo publicado (via Kafka article-published)
        known_domains: Conjunto de domínios já cadastrados
    
    Returns:
        Lista de candidatos com URL e contexto
    """
    candidates = []
    
    # Extrai links do conteúdo (HTML ou texto)
    content = article.get("conteudo", "") or article.get("content", "")
    url_fonte = article.get("url_fonte", "")
    
    # Regex para extrair URLs
    url_pattern = re.compile(
        r'https?://[^\s<>"\']+',
        re.IGNORECASE
    )
    
    found_urls = url_pattern.findall(content)
    # Inclui também a URL fonte do artigo
    if url_fonte:
        found_urls.append(url_fonte)
    
    seen_domains = set()
    
    for url in found_urls:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().removeprefix("www.")
            
            # Ignora domínios já processados neste batch
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            
            # Ignora domínios já conhecidos
            if domain in known_domains:
                continue
            
            # Ignora domínios na lista de exclusão
            if domain in DISCOVERY_IGNORE_DOMAINS:
                continue
            
            # Ignora domínios muito genéricos (1-2 chars)
            if len(domain) < 5:
                continue
            
            # Pontuação de relevância inicial pelo padrão do domínio
            initial_score = 0
            matched_patterns = []
            for pattern in JOURNALISTIC_PATTERNS:
                if re.search(pattern, domain, re.IGNORECASE):
                    initial_score += 2
                    matched_patterns.append(pattern)
            
            candidates.append({
                "url": f"https://{domain}",
                "domain": domain,
                "found_in_article": article.get("id") or article.get("wp_post_id"),
                "found_at": datetime.utcnow().isoformat(),
                "article_editoria": article.get("editoria", ""),
                "initial_score": initial_score,
                "matched_patterns": matched_patterns,
                "source_article_url": url,
            })
        
        except Exception:
            continue
    
    # Ordena por score inicial (candidatos mais prováveis primeiro)
    candidates.sort(key=lambda x: x["initial_score"], reverse=True)
    return candidates[:10]  # Máximo 10 candidatos por artigo
```

### 9.3 Classificação de Novas Fontes via LLM Econômico

```python
FOCAS_CLASSIFICATION_PROMPT = """Você é o classificador de fontes jornalísticas da Brasileira.news.

Analise este domínio e classifique-o como fonte de notícias.

DOMÍNIO: {domain}
URL: {url}
CONTEXTO: Encontrado em artigo sobre "{editoria}" em brasileira.news

TIPOS DE FONTE:
- portal_noticias: Veículos jornalísticos (portais, jornais, TVs online)
- governo: Sites oficiais (.gov.br, legislativo, judiciário)
- agencia: Agências de notícias (Reuters, AFP, Agência Brasil)
- blog: Blogs especializados ou jornalismo independente
- instituicao: ONGs, universidades, associações, think tanks
- nao_jornalistico: Site sem conteúdo noticioso relevante

REGRAS:
- Confiabilidade: 1-10 (10 = fonte oficial/grande veículo; 5 = blog conhecido; 1 = desconhecido)
- Relevância: 1-10 (10 = altamente relevante para brasileira.news; 1 = não relevante)
- Se não conseguir classificar com confiança, use tipo "nao_jornalistico"

Responda APENAS em JSON:
{
    "tipo": "...",
    "confiabilidade": 7,
    "relevancia": 8,
    "justificativa": "...",
    "sugestao_editoria": "...",
    "tem_rss": true/false/null
}"""

async def classify_source_candidate(
    candidate: Dict[str, Any],
    llm_router,  # SmartLLMRouter
) -> Optional[Dict[str, Any]]:
    """
    Classifica um candidato a fonte via LLM ECONÔMICO.
    Retorna None se não for fonte jornalística relevante.
    """
    prompt = FOCAS_CLASSIFICATION_PROMPT.format(
        domain=candidate["domain"],
        url=candidate["url"],
        editoria=candidate.get("article_editoria", "geral"),
    )
    
    try:
        response = await llm_router.complete(
            task="classificacao_categoria",  # Tier ECONÔMICO
            prompt=prompt,
            max_tokens=256,
        )
        
        # Parse JSON da resposta
        data = json.loads(response.strip())
        
        # Threshold de aprovação
        confiabilidade = data.get("confiabilidade", 0)
        relevancia = data.get("relevancia", 0)
        tipo = data.get("tipo", "nao_jornalistico")
        
        if tipo == "nao_jornalistico":
            return None
        
        if confiabilidade < 4 or relevancia < 5:
            return None  # Não é relevante o suficiente
        
        return {
            **candidate,
            "tipo": tipo,
            "confiabilidade": confiabilidade,
            "relevancia": relevancia,
            "justificativa": data.get("justificativa", ""),
            "sugestao_editoria": data.get("sugestao_editoria", ""),
            "tem_rss": data.get("tem_rss"),
            "status": "pendente_review",  # Não vai para ativo direto
        }
    
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
    except Exception as e:
        logger.warning(f"Erro classificando {candidate['domain']}: {e}")
        return None
```

---

## PARTE X — FOCAS: A REGRA DE NUNCA DESATIVAR

### 10.1 Por que Nunca Desativar é uma Regra de Negócio

Fontes de notícias têm comportamentos que sistemas automáticos não conseguem distinguir de "morte":

| Situação | Sintomas | Ação Errada (V2) | Ação Correta (V3) |
|----------|----------|-------------------|-------------------|
| Manutenção programada | HTTP 503 por 24h | Desativa | Aumenta intervalo, aguarda |
| Cobertura sazonal | 0 artigos por 60 dias | Desativa | Polling de 24h, aguarda Copa/Eleição |
| Mudança de URL | HTTP 301/302 loops | Desativa | Alerta para atualização manual de URL |
| Rate limiting agressivo | HTTP 429 por horas | Desativa | Backoff exponencial, não desativa |
| Paywall temporário | HTTP 403 | Desativa | Polling reduzido, aguarda |
| Servidor sobrecarregado | Timeout intermitente | Desativa após 5 falhas | Health tier "flaky", dobra intervalo |
| Fonte de nicho regional | 1 artigo/mês | Desativa após 7 dias | Polling de 24h, valiosa quando publica |

### 10.2 Implementação do Princípio "Nunca Desativa"

```python
def categorize_source_for_action(
    source: Dict[str, Any],
    health_result: SourceHealthResult,
    articles_7d: int,
    articles_30d: int,
) -> Dict[str, Any]:
    """
    Determina ação para a fonte baseado em saúde e produtividade.
    
    AÇÕES POSSÍVEIS:
    - adjust_interval: Ajusta o intervalo de polling (única ação automática)
    - alert_url_change: Alerta para possível mudança de URL
    - alert_cluster: Alerta se muitas fontes do mesmo domínio caíram
    
    AÇÃO IMPOSSÍVEL:
    - deactivate: NUNCA. Não existe no V3.
    """
    action = {
        "source_id": health_result.source_id,
        "source_name": health_result.source_name,
        "action": "adjust_interval",  # SEMPRE adjust_interval, nunca deactivate
        "new_interval_seconds": MIN_POLLING_INTERVAL,
        "consecutive_failures": health_result.consecutive_failures,
        "justificativa": "",
        "alert_needed": False,
        "alert_type": None,
    }
    
    health_tier = health_result.health_tier
    
    # Nunca desativa — apenas ajusta
    if health_tier == "slow":
        # 10+ falhas consecutivas
        action["new_interval_seconds"] = MAX_POLLING_INTERVAL  # 24h
        action["justificativa"] = (
            f"{health_result.consecutive_failures} falhas consecutivas. "
            f"Reduzido a polling de 24h. FONTE MANTIDA ATIVA."
        )
        
        # Verifica se pode ser mudança de URL
        if health_result.status_code == 404:
            action["alert_needed"] = True
            action["alert_type"] = "possible_url_change"
        elif health_result.status_code in (301, 302, 308):
            action["alert_needed"] = True
            action["alert_type"] = "redirect_detected"
        
    elif health_tier == "degraded":
        action["new_interval_seconds"] = min(
            source.get("polling_interval_min", 30) * 60 * 4,
            43200  # máx 12h
        )
        action["justificativa"] = (
            f"Fonte instável: {health_result.consecutive_failures} falhas. "
            f"Intervalo quadruplicado."
        )
    
    elif health_tier == "flaky":
        action["new_interval_seconds"] = min(
            source.get("polling_interval_min", 30) * 60 * 2,
            21600  # máx 6h
        )
        action["justificativa"] = (
            f"Fonte instável: {health_result.consecutive_failures} falhas. "
            f"Intervalo dobrado."
        )
    
    else:
        # Fonte saudável — intervalo por produtividade
        engine = AdaptivePollingEngine()
        interval, justificativa = engine.calculate_new_interval(
            source, health_result, articles_7d, articles_30d
        )
        action["new_interval_seconds"] = interval
        action["justificativa"] = justificativa
    
    return action

# VALIDAÇÃO: O V3 nunca deve ter código de desativação
def assert_no_deactivation_logic(catalog_update: Dict[str, Any]) -> None:
    """
    Assertion de segurança: valida que nenhum update desativa fontes.
    Deve ser chamado antes de qualquer operação no banco.
    """
    action = catalog_update.get("action", "")
    if "deactivat" in action.lower() or "desativ" in action.lower():
        raise ValueError(
            f"VIOLAÇÃO DE REGRA INVIOLÁVEL: tentativa de desativar fonte. "
            f"Action proibida: {action}. "
            f"No V3, fontes NUNCA são desativadas automaticamente."
        )
```

### 10.3 Alertas de Fontes Problemáticas (Sem Desativação)

```python
class FocasAlertGenerator:
    """Gera alertas de fontes sem nunca desativá-las."""
    
    def generate_source_alerts(
        self,
        health_results: List[SourceHealthResult],
    ) -> List[Alert]:
        alerts = []
        
        # Agrupa falhas por domínio raiz (detecta CDN/cluster offline)
        domain_failures: Dict[str, List[SourceHealthResult]] = {}
        for result in health_results:
            if not result.is_healthy:
                domain = self._root_domain(result.url)
                domain_failures.setdefault(domain, []).append(result)
        
        # Alerta de cluster down (10+ fontes do mesmo domínio)
        for domain, failures in domain_failures.items():
            if len(failures) >= 10:
                alerts.append(Alert(
                    alert_id=f"cluster-{domain[:10]}-{datetime.utcnow().strftime('%H%M')}",
                    alert_type=AlertType.SOURCE_CLUSTER_DOWN,
                    severity=AlertSeverity.WARNING,
                    title=f"Cluster de fontes offline: {domain} ({len(failures)} fontes)",
                    description=(
                        f"{len(failures)} fontes sob o domínio {domain} estão "
                        f"inacessíveis. Pode ser problema de CDN ou DNS. "
                        f"Todas as fontes permanecem ATIVAS com polling de 24h."
                    ),
                    context={"domain": domain, "affected_count": len(failures)},
                    blocks_pipeline=False,  # NUNCA bloqueia
                ))
        
        # Alertas de fontes individuais com 10+ falhas
        for result in health_results:
            if result.consecutive_failures >= 10:
                alerts.append(Alert(
                    alert_id=f"src-{result.source_id}-{datetime.utcnow().strftime('%H%M')}",
                    alert_type=AlertType.SOURCE_UNREACHABLE,
                    severity=AlertSeverity.WARNING,
                    title=f"Fonte inacessível: {result.source_name} ({result.consecutive_failures} falhas)",
                    description=(
                        f"Fonte '{result.source_name}' inacessível há "
                        f"{result.consecutive_failures} verificações consecutivas. "
                        f"Último erro: {result.error_message}. "
                        f"Polling reduzido a 24h. FONTE MANTIDA ATIVA."
                    ),
                    context=result.to_dict(),
                    blocks_pipeline=False,  # NUNCA bloqueia
                ))
        
        return alerts
    
    def _root_domain(self, url: str) -> str:
        """Extrai domínio raiz (ex: g1.globo.com → globo.com)."""
        try:
            parsed = urlparse(url)
            parts = parsed.netloc.split(".")
            if len(parts) >= 2:
                return ".".join(parts[-2:])
            return parsed.netloc
        except Exception:
            return url
```

---

## PARTE XI — SCHEMAS: POSTGRESQL E REDIS

### 11.1 Schema PostgreSQL — Tabelas Relevantes

```sql
-- Tabela de fontes (648+ registros) — NUNCA tem coluna ativa=False automaticamente
CREATE TABLE IF NOT EXISTS fontes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome                    VARCHAR(255) NOT NULL,
    url                     TEXT NOT NULL UNIQUE,
    tipo                    VARCHAR(50) NOT NULL,  -- portal_noticias, governo, agencia, blog, instituicao
    tier                    VARCHAR(20) DEFAULT 'standard',  -- vip, premium, standard
    
    -- Polling adaptativo (nunca zerado ou desativado)
    polling_interval_min    INTEGER NOT NULL DEFAULT 30,
    ultimo_check            TIMESTAMPTZ,
    ultimo_sucesso          TIMESTAMPTZ,
    consecutive_failures    INTEGER NOT NULL DEFAULT 0,
    
    -- Produtividade
    total_sucessos          INTEGER NOT NULL DEFAULT 0,
    artigos_7d              INTEGER NOT NULL DEFAULT 0,
    artigos_30d             INTEGER NOT NULL DEFAULT 0,
    
    -- Metadados
    config_scraper          JSONB DEFAULT '{}',
    metadata                JSONB DEFAULT '{}',
    editoria_principal      VARCHAR(100),
    
    -- Discovery
    descoberta_em           TIMESTAMPTZ DEFAULT NOW(),
    descoberta_via          VARCHAR(50) DEFAULT 'manual',  -- manual, discovery
    status_review           VARCHAR(20) DEFAULT 'aprovada',  -- aprovada, pendente_review
    
    -- Timestamps
    criado_em               TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ DEFAULT NOW()
    
    -- NOTA: Sem coluna "ativo" booleana — fontes NUNCA são desativadas
    -- Se necessário suspender temporariamente (ex: manutenção manual),
    -- usa polling_interval_min = 1440 (24h) via UPDATE manual.
);

-- Índices para o Focas
CREATE INDEX IF NOT EXISTS idx_fontes_polling ON fontes (polling_interval_min, ultimo_check);
CREATE INDEX IF NOT EXISTS idx_fontes_tier ON fontes (tier);
CREATE INDEX IF NOT EXISTS idx_fontes_failures ON fontes (consecutive_failures) WHERE consecutive_failures > 0;

-- Tabela de métricas de coleta por ciclo
CREATE TABLE IF NOT EXISTS coleta_metricas (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fonte_id                UUID REFERENCES fontes(id),
    ciclo_id                VARCHAR(100),
    artigos_coletados       INTEGER DEFAULT 0,
    artigos_novos           INTEGER DEFAULT 0,
    artigos_duplicados      INTEGER DEFAULT 0,
    latency_ms              INTEGER,
    status                  VARCHAR(20),  -- success, timeout, error
    erro_mensagem           TEXT,
    coletado_em             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coleta_metricas_fonte ON coleta_metricas (fonte_id, coletado_em DESC);

-- Tabela de alertas do Monitor (log persistido)
CREATE TABLE IF NOT EXISTS monitor_alertas (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type              VARCHAR(50) NOT NULL,
    severity                VARCHAR(20) NOT NULL,  -- INFO, WARNING, CRITICAL
    title                   TEXT NOT NULL,
    description             TEXT,
    context_json            JSONB DEFAULT '{}',
    blocks_pipeline         BOOLEAN NOT NULL DEFAULT FALSE,  -- SEMPRE FALSE
    resolvido               BOOLEAN DEFAULT FALSE,
    criado_em               TIMESTAMPTZ DEFAULT NOW(),
    resolvido_em            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alertas_severity ON monitor_alertas (severity, criado_em DESC)
    WHERE NOT resolvido;

-- Tabela de discovery de fontes (candidatos aprovados aguardando review)
CREATE TABLE IF NOT EXISTS fontes_discovery (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dominio                 VARCHAR(255) NOT NULL UNIQUE,
    url_candidata           TEXT NOT NULL,
    encontrada_em_artigo    UUID,
    editoria_contexto       VARCHAR(100),
    tipo_classificado       VARCHAR(50),
    confiabilidade          INTEGER CHECK (confiabilidade BETWEEN 1 AND 10),
    relevancia              INTEGER CHECK (relevancia BETWEEN 1 AND 10),
    justificativa           TEXT,
    tem_rss                 BOOLEAN,
    status                  VARCHAR(20) DEFAULT 'pendente',  -- pendente, aprovada, rejeitada
    criado_em               TIMESTAMPTZ DEFAULT NOW()
);
```

### 11.2 Redis Keys — Monitor Sistema + Focas

```python
# ── Monitor Sistema ────────────────────────────────────────────────────────
REDIS_DASHBOARD = "monitor:dashboard"               # TTL: 120s
REDIS_THROUGHPUT_SNAPSHOT = "monitor:throughput"    # TTL: 60s
REDIS_COVERAGE_SNAPSHOT = "monitor:coverage"        # TTL: 60s
REDIS_LAST_CYCLE = "monitor:last_cycle"             # TTL: 300s

# Heartbeats dos agentes (escritos por cada agente)
REDIS_AGENT_HEARTBEAT = "agent:{agent_type}:{agent_id}:heartbeat"  # TTL: 180s

# Alert deduplication
REDIS_ALERT_DEDUP = "alert:dedup:{alert_type}:{context_key}"  # TTL: variável

# ── Focas ──────────────────────────────────────────────────────────────────
REDIS_SOURCE_HEALTH = "focas:health:{source_id}"    # TTL: 3600s (1h)
REDIS_SOURCE_FAILURES = "focas:failures:{source_id}" # TTL: 86400s (24h)
REDIS_HEALTH_REPORT = "focas:health_report"          # TTL: 3600s
REDIS_DISCOVERY_QUEUE = "focas:discovery:queue"      # LIST, sem TTL
REDIS_KNOWN_DOMAINS = "focas:known_domains"          # SET, sem TTL

# Cache de domínios conhecidos (carregado do PostgreSQL periodicamente)
# Usado no discovery para filtrar domínios já cadastrados
# Atualizado a cada ciclo do Focas
```

### 11.3 Schemas Pydantic

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

# ── Monitor Sistema ────────────────────────────────────────────────────────

class MonitorSistemaState(BaseModel):
    """Estado da máquina de estados do Monitor Sistema."""
    agent_id: str
    agent_name: str = "monitor_sistema"
    cycle_id: str = Field(default_factory=lambda: f"cycle-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
    
    # Throughput
    throughput_health: Dict[str, Any] = Field(default_factory=dict)
    articles_last_hour: int = 0
    articles_last_15min: int = 0
    
    # Cobertura
    coverage_gaps: List[Dict[str, Any]] = Field(default_factory=list)
    editorias_ok: int = 0
    editorias_com_gap: int = 0
    
    # Agentes
    agent_statuses: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    agents_healthy: int = 0
    agents_stale: int = 0
    
    # Qualidade de pipeline
    pipeline_quality: Dict[str, Any] = Field(default_factory=dict)
    
    # Alertas gerados neste ciclo
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Status geral
    system_status: str = "healthy"  # healthy / degraded / critical
    
    # Custo (INFORMAÇÃO APENAS)
    cost_info: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    cycle_started_at: datetime = Field(default_factory=datetime.utcnow)
    cycle_completed_at: Optional[datetime] = None


# ── Focas ──────────────────────────────────────────────────────────────────

class FocasV3State(BaseModel):
    """Estado da máquina de estados do Focas V3."""
    agent_id: str
    agent_name: str = "focas"
    cycle_id: str = Field(default_factory=lambda: f"focas-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
    
    # Fontes carregadas
    sources_loaded: int = 0
    
    # Resultados de health check
    health_results: List[Dict[str, Any]] = Field(default_factory=list)
    sources_healthy: int = 0
    sources_flaky: int = 0
    sources_degraded: int = 0
    sources_slow: int = 0  # 10+ falhas — polling 24h, mas ATIVAS
    
    # Ajustes de polling
    interval_adjustments: List[Dict[str, Any]] = Field(default_factory=list)
    adjustments_applied: int = 0
    
    # Discovery
    discovered_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    candidates_classified: int = 0
    candidates_approved: int = 0
    candidates_rejected: int = 0
    
    # Alertas
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Relatório
    health_report: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    cycle_started_at: datetime = Field(default_factory=datetime.utcnow)
    cycle_completed_at: Optional[datetime] = None
    
    class Config:
        # NUNCA deve existir campo de desativação
        @classmethod
        def validate_no_deactivation(cls, values):
            if "deactivated_sources" in values:
                raise ValueError("VIOLAÇÃO: campo 'deactivated_sources' proibido no V3")
            return values
```

---

## PARTE XII — ESTRUTURA DE DIRETÓRIOS

### 12.1 Estrutura Completa

```
brasileira/
├── agents/
│   ├── monitor_sistema.py              # ← ESTE BRIEFING (Monitor)
│   ├── focas.py                        # ← ESTE BRIEFING (Focas)
│   └── ...
│
├── monitoring/
│   ├── __init__.py
│   ├── throughput_tracker.py           # ThroughputTracker com janelas deslizantes
│   ├── coverage_checker.py             # CoverageChecker para 16 editorias
│   ├── agent_health_checker.py         # AgentHealthChecker via Redis heartbeats
│   ├── pipeline_quality_collector.py   # PipelineQualityCollector via PostgreSQL
│   ├── alert_generator.py              # AlertGenerator (throughput, cobertura, agentes)
│   ├── alert_deduplicator.py           # AlertDeduplicator com cooldowns
│   └── dashboard_updater.py            # DashboardUpdater → Redis
│
├── focas/
│   ├── __init__.py
│   ├── health_checker.py               # health_check_all_sources() paralelo
│   ├── adaptive_polling.py             # AdaptivePollingEngine
│   ├── source_categorizer.py           # categorize_source_for_action()
│   ├── discovery_extractor.py          # extract_candidate_sources()
│   ├── source_classifier.py            # classify_source_candidate() via LLM
│   ├── catalog_updater.py              # apply_adjustments() → PostgreSQL
│   ├── focas_alert_generator.py        # FocasAlertGenerator
│   └── known_domains_cache.py          # Cache Redis de domínios conhecidos
│
├── observability/
│   ├── __init__.py
│   ├── tracing.py                      # OpenTelemetry traces
│   ├── metrics.py                      # Prometheus metrics (Gauge, Counter, etc.)
│   └── alerts.py                       # Sistema de alertas unificado
│
└── config/
    ├── monitoring.py                   # Constantes de monitoramento
    └── ...
```

### 12.2 Arquivos de Configuração

```python
# brasileira/config/monitoring.py

# ── Monitor Sistema ────────────────────────────────────────────────────────

# SLO de throughput
THROUGHPUT_SLO_PER_HOUR = 40       # Target SLO
THROUGHPUT_ALERT_THRESHOLD = 20    # Alerta WARNING
THROUGHPUT_CRITICAL_THRESHOLD = 5  # Alerta CRITICAL

# Cobertura por editoria
COVERAGE_GAP_MINUTES_WARNING = 120   # 2h sem artigo = WARNING
COVERAGE_GAP_MINUTES_CRITICAL = 240  # 4h sem artigo = CRITICAL

# Heartbeat de agentes
HEARTBEAT_WRITE_INTERVAL = 30       # Agentes escrevem heartbeat a cada 30s

# Ciclo do Monitor
MONITOR_CYCLE_SECONDS = 60          # Monitor roda a cada 60s

# Dashboard Redis
DASHBOARD_REDIS_KEY = "monitor:dashboard"
DASHBOARD_TTL_SECONDS = 120         # Expira em 2min se Monitor parar

# ── Focas ──────────────────────────────────────────────────────────────────

# Polling
MIN_POLLING_INTERVAL_SEC = 900      # 15min — mínimo absoluto
MAX_POLLING_INTERVAL_SEC = 86400    # 24h — máximo absoluto (NUNCA desativa)

# Health check das fontes
SOURCE_HEALTH_CHECK_TIMEOUT = 15    # Segundos
SOURCE_HEALTH_MAX_CONCURRENT = 50   # Semáforo paralelo
SOURCE_HEALTH_BATCH_SIZE = 100      # Lotes de 100 fontes

# Ciclo do Focas
FOCAS_HEALTH_CYCLE_MINUTES = 10     # Health check completo a cada 10min
FOCAS_DISCOVERY_CYCLE_MINUTES = 60  # Discovery a cada 1h

# Discovery
DISCOVERY_MIN_CONFIABILIDADE = 4    # Mínimo para aprovação
DISCOVERY_MIN_RELEVANCIA = 5        # Mínimo para aprovação
MAX_CANDIDATES_PER_ARTICLE = 10     # Máximo de candidatos por artigo

# LLM para classificação de fontes
FOCAS_LLM_TASK = "classificacao_categoria"  # Tier ECONÔMICO (conforme tabela)
FOCAS_LLM_MAX_TOKENS = 256

# PROIBIDO — não deve existir no V3
# SOURCE_DEACTIVATION_ENABLED = False   # Não existe. Não tem. Nunca.
# PRODUCTIVITY_DEAD_DAYS = None         # Conceito eliminado.
```

---

## PARTE XIII — ENTRYPOINTS E LOOPS DE EXECUÇÃO

### 13.1 Monitor Sistema — Entrypoint

```python
# brasileira/agents/monitor_sistema.py
"""
Monitor Sistema V3 — Health, Throughput e Cobertura.

Ciclo de 60 segundos:
1. check_throughput: Lê contagem de artigos do ThroughputTracker (via Kafka consumer)
2. check_coverage: Verifica cobertura das 16 editorias
3. check_agents: Verifica heartbeats no Redis
4. collect_cost_info: Coleta custo como INFORMAÇÃO (não bloqueio)
5. generate_alerts: Gera alertas de throughput, cobertura e agentes
6. compile_dashboard: Publica dashboard no Redis

REGRAS INVIOLÁVEIS:
- Custo como INFORMAÇÃO, nunca bloqueio
- Alertas nunca interrompem o pipeline
- Throughput é a métrica principal (não custo)
"""

import asyncio
import json
import uuid
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from collections import deque

import asyncpg
import redis.asyncio as aioredis
from langgraph.graph import StateGraph, END
from aiokafka import AIOKafkaConsumer

from brasileira.config.monitoring import (
    THROUGHPUT_SLO_PER_HOUR,
    THROUGHPUT_ALERT_THRESHOLD,
    THROUGHPUT_CRITICAL_THRESHOLD,
    COVERAGE_GAP_MINUTES_WARNING,
    COVERAGE_GAP_MINUTES_CRITICAL,
    HEARTBEAT_WRITE_INTERVAL,
    MONITOR_CYCLE_SECONDS,
    DASHBOARD_REDIS_KEY,
    DASHBOARD_TTL_SECONDS,
    EDITORIAS_V3,
    AGENTES_V3,
    HEARTBEAT_STALE_SECONDS,
)
from brasileira.monitoring.throughput_tracker import ThroughputTracker
from brasileira.monitoring.alert_generator import AlertGenerator
from brasileira.monitoring.alert_deduplicator import AlertDeduplicator
from brasileira.monitoring.dashboard_updater import update_dashboard
from brasileira.monitoring.pipeline_quality_collector import collect_pipeline_quality
from brasileira.observability.metrics import (
    articles_per_hour,
    throughput_burn_rate,
    coverage_gap_minutes,
    agent_heartbeat_age_seconds,
)


class MonitorSistemaV3:
    """
    Monitor Sistema V3 — Observabilidade de throughput e cobertura.
    
    NÃO usa LangGraph para o loop principal (complexidade desnecessária
    para um monitor simples). Usa asyncio loop direto.
    
    Para análise LLM ocasional (relatório diário), usa SmartLLMRouter
    com task="analise_metricas" (tier PADRÃO).
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        pg_dsn: str = "postgresql://...",
        kafka_bootstrap: str = "localhost:9092",
    ):
        self._redis_url = redis_url
        self._pg_dsn = pg_dsn
        self._kafka_bootstrap = kafka_bootstrap
        
        self._redis: Optional[aioredis.Redis] = None
        self._pg: Optional[asyncpg.Connection] = None
        self._kafka_consumer: Optional[AIOKafkaConsumer] = None
        
        # Tracker de throughput em memória
        self._throughput = ThroughputTracker()
        
        # Gerador e deduplicador de alertas
        self._alert_gen = AlertGenerator()
        self._alert_dedup: Optional[AlertDeduplicator] = None
        
        self._running = False
        self._cycle_count = 0
        
        self.logger = get_logger("monitor_sistema")
    
    async def start(self):
        """Inicia o Monitor Sistema."""
        self.logger.info("Monitor Sistema V3 iniciando...")
        
        # Conexões
        self._redis = await aioredis.from_url(self._redis_url, decode_responses=True)
        self._pg = await asyncpg.connect(self._pg_dsn)
        self._alert_dedup = AlertDeduplicator(self._redis)
        
        # Kafka consumer para article-published e homepage-updates
        self._kafka_consumer = AIOKafkaConsumer(
            "article-published",
            "homepage-updates",
            bootstrap_servers=self._kafka_bootstrap,
            group_id="monitor-sistema-v3",
            auto_offset_reset="latest",  # Só processa novos artigos
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        await self._kafka_consumer.start()
        
        self._running = True
        
        # Duas tasks concorrentes:
        # 1. Consumer Kafka (contínuo — registra artigos em tempo real)
        # 2. Ciclo de análise (a cada 60s — analisa e gera alertas)
        await asyncio.gather(
            self._kafka_consumer_loop(),
            self._analysis_cycle_loop(),
        )
    
    async def stop(self):
        """Para o Monitor Sistema graciosamente."""
        self._running = False
        if self._kafka_consumer:
            await self._kafka_consumer.stop()
        if self._redis:
            await self._redis.close()
        if self._pg:
            await self._pg.close()
        self.logger.info("Monitor Sistema parado.")
    
    async def _kafka_consumer_loop(self):
        """
        Loop contínuo: consome article-published e registra no ThroughputTracker.
        Roda em paralelo com _analysis_cycle_loop.
        """
        self.logger.info("Kafka consumer loop iniciado (article-published, homepage-updates)")
        
        async for msg in self._kafka_consumer:
            if not self._running:
                break
            
            try:
                topic = msg.topic
                data = msg.value
                
                if topic == "article-published":
                    editoria = data.get("editoria", "Últimas Notícias")
                    published_at = datetime.utcnow()
                    
                    # Registra no tracker em memória
                    await self._throughput.record_article(editoria, published_at)
                    
                    # Atualiza Prometheus
                    articles_per_hour.set(self._throughput.get_rate_per_hour())
                
            except Exception as e:
                self.logger.error(f"Erro processando mensagem Kafka: {e}")
    
    async def _analysis_cycle_loop(self):
        """
        Loop de análise: roda a cada 60s, analisa métricas e gera alertas.
        """
        self.logger.info("Analysis cycle loop iniciado (60s)")
        
        while self._running:
            cycle_start = time.monotonic()
            self._cycle_count += 1
            
            try:
                await self._run_analysis_cycle()
            except Exception as e:
                self.logger.error(f"Erro no ciclo de análise #{self._cycle_count}: {e}")
            
            # Aguarda até completar 60 segundos
            elapsed = time.monotonic() - cycle_start
            wait = max(0, MONITOR_CYCLE_SECONDS - elapsed)
            await asyncio.sleep(wait)
    
    async def _run_analysis_cycle(self):
        """Executa um ciclo completo de análise."""
        cycle_id = f"cycle-{self._cycle_count}-{datetime.utcnow().strftime('%H%M%S')}"
        self.logger.info(f"Iniciando ciclo de análise {cycle_id}")
        
        # 1. Throughput
        rate_1h = self._throughput.get_rate_per_hour()
        rate_15m_proj = self._throughput.get_rate_last_15min_projected()
        throughput_health = calculate_throughput_health(rate_1h, rate_15m_proj)
        
        # Prometheus
        articles_per_hour.set(rate_1h)
        throughput_burn_rate.set(throughput_health["burn_rate_1h"])
        
        # 2. Cobertura por editoria
        coverage_gaps = self._throughput.get_coverage_gaps(
            EDITORIAS_V3, COVERAGE_GAP_MINUTES_WARNING
        )
        for gap in coverage_gaps:
            editoria = gap["editoria"]
            minutes = gap.get("minutes_since_last", 9999) or 9999
            coverage_gap_minutes.labels(editoria=editoria).set(minutes)
        
        # 3. Agentes (via Redis heartbeats)
        agent_statuses = await self._check_agent_heartbeats()
        
        # 4. Qualidade do pipeline + custo (só informação)
        pipeline_quality = await collect_pipeline_quality(self._pg, window_hours=1)
        
        # 5. Gera alertas
        all_alerts = []
        
        throughput_alerts = self._alert_gen.generate_throughput_alerts(throughput_health)
        coverage_alerts = self._alert_gen.generate_coverage_alerts(coverage_gaps)
        agent_alerts = self._alert_gen.generate_agent_alerts(agent_statuses)
        
        for alert in throughput_alerts + coverage_alerts + agent_alerts:
            context_key = alert.context.get("editoria", alert.context.get("agent_id", ""))
            if await self._alert_dedup.should_send(alert, context_key):
                all_alerts.append(alert)
                self.logger.warning(
                    f"ALERTA [{alert.severity.value}] {alert.title}",
                    extra={"alert_id": alert.alert_id, "context": alert.context}
                )
                # Persiste no PostgreSQL
                await self._persist_alert(alert)
        
        # 6. Atualiza dashboard no Redis
        await update_dashboard(
            self._redis,
            throughput_health,
            coverage_gaps,
            agent_statuses,
            pipeline_quality,
            all_alerts,
        )
        
        # 7. Escreve próprio heartbeat
        await self._redis.setex(
            "agent:monitor_sistema:monitor-01:heartbeat",
            HEARTBEAT_WRITE_INTERVAL * 3,
            json.dumps({
                "agent_type": "monitor_sistema",
                "cycle_id": cycle_id,
                "timestamp": datetime.utcnow().isoformat(),
                "system_status": _calc_system_status(throughput_health, coverage_gaps, all_alerts),
            })
        )
        
        self.logger.info(
            f"Ciclo {cycle_id} concluído: "
            f"{rate_1h:.0f}/h, {len(coverage_gaps)} gaps, "
            f"{len(all_alerts)} alertas"
        )
    
    async def _check_agent_heartbeats(self) -> Dict[str, Dict[str, Any]]:
        """Verifica heartbeats de todos os agentes no Redis."""
        agent_statuses = {}
        now = datetime.utcnow()
        
        for agent_type in AGENTES_V3:
            pattern = f"agent:{agent_type}:*:heartbeat"
            keys = await self._redis.keys(pattern)
            
            for key in keys:
                try:
                    data_str = await self._redis.get(key)
                    if not data_str:
                        continue
                    
                    data = json.loads(data_str)
                    timestamp_str = data.get("timestamp")
                    
                    if timestamp_str:
                        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        age_sec = (now - ts.replace(tzinfo=None)).total_seconds()
                    else:
                        age_sec = 9999
                    
                    threshold = HEARTBEAT_STALE_SECONDS.get(agent_type, 300)
                    health = "healthy" if age_sec <= threshold else "stale"
                    
                    agent_id = key.split(":")[2]
                    agent_statuses[agent_id] = {
                        "agent_type": agent_type,
                        "age_seconds": age_sec,
                        "health": health,
                        "threshold_seconds": threshold,
                        "last_cycle_id": data.get("cycle_id", ""),
                    }
                    
                    # Prometheus
                    agent_heartbeat_age_seconds.labels(
                        agent_type=agent_type, agent_id=agent_id
                    ).set(age_sec)
                    
                except Exception as e:
                    self.logger.warning(f"Erro verificando heartbeat {key}: {e}")
        
        return agent_statuses
    
    async def _persist_alert(self, alert: Alert):
        """Persiste alerta no PostgreSQL para histórico."""
        try:
            await self._pg.execute("""
                INSERT INTO monitor_alertas (alert_type, severity, title, description, context_json, blocks_pipeline)
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
                alert.alert_type.value,
                alert.severity.value,
                alert.title,
                alert.description,
                json.dumps(alert.context),
                False,  # SEMPRE False — nunca bloqueia
            )
        except Exception as e:
            self.logger.error(f"Erro persistindo alerta: {e}")


# Entrypoint
async def main():
    monitor = MonitorSistemaV3()
    try:
        await monitor.start()
    except KeyboardInterrupt:
        await monitor.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 13.2 Focas — Entrypoint

```python
# brasileira/agents/focas.py
"""
Focas V3 — Gerenciador de Fontes.

Dois loops concorrentes:
1. Health check loop (a cada 10min): verifica todas as 648+ fontes
2. Discovery loop (a cada 1h): processa candidatos a novas fontes via Kafka

REGRA INVIOLÁVEL: NUNCA desativa fontes.
Apenas ajusta o polling_interval_min via UPDATE no PostgreSQL.
"""

import asyncio
import json
import uuid
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import asyncpg
import redis.asyncio as aioredis
from aiokafka import AIOKafkaConsumer

from brasileira.config.monitoring import (
    MIN_POLLING_INTERVAL_SEC,
    MAX_POLLING_INTERVAL_SEC,
    SOURCE_HEALTH_CHECK_TIMEOUT,
    SOURCE_HEALTH_MAX_CONCURRENT,
    FOCAS_HEALTH_CYCLE_MINUTES,
    FOCAS_DISCOVERY_CYCLE_MINUTES,
    DISCOVERY_MIN_CONFIABILIDADE,
    DISCOVERY_MIN_RELEVANCIA,
    MAX_CANDIDATES_PER_ARTICLE,
    FOCAS_LLM_TASK,
    REDIS_KNOWN_DOMAINS,
)
from brasileira.focas.health_checker import health_check_all_sources
from brasileira.focas.adaptive_polling import AdaptivePollingEngine
from brasileira.focas.source_categorizer import categorize_source_for_action
from brasileira.focas.discovery_extractor import extract_candidate_sources
from brasileira.focas.source_classifier import classify_source_candidate
from brasileira.focas.catalog_updater import apply_catalog_updates
from brasileira.focas.focas_alert_generator import FocasAlertGenerator
from brasileira.observability.metrics import (
    source_health_status,
    source_polling_interval_seconds,
    source_discovery_total,
)


class FocasV3:
    """
    Focas V3 — Gerenciador Adaptativo de Fontes.
    
    Loops concorrentes:
    - _health_cycle_loop: Health check paralelo de todas as fontes (10min)
    - _discovery_loop: Discovery de novas fontes via Kafka (1h)
    
    PROIBIDO: qualquer chamada a catalog.deactivate() ou equivalente.
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        pg_dsn: str = "postgresql://...",
        kafka_bootstrap: str = "localhost:9092",
        llm_router=None,
    ):
        self._redis_url = redis_url
        self._pg_dsn = pg_dsn
        self._kafka_bootstrap = kafka_bootstrap
        self._llm_router = llm_router
        
        self._redis: Optional[aioredis.Redis] = None
        self._pg: Optional[asyncpg.Connection] = None
        self._kafka_consumer: Optional[AIOKafkaConsumer] = None
        
        self._polling_engine = AdaptivePollingEngine()
        self._alert_gen = FocasAlertGenerator()
        
        # Cache de domínios conhecidos (evita re-classificar)
        self._known_domains: Set[str] = set()
        # Fila de candidatos para classificação
        self._discovery_queue: List[Dict[str, Any]] = []
        
        self._running = False
        self.logger = get_logger("focas")
    
    async def start(self):
        """Inicia o Focas."""
        self.logger.info("Focas V3 iniciando...")
        
        self._redis = await aioredis.from_url(self._redis_url, decode_responses=True)
        self._pg = await asyncpg.connect(self._pg_dsn)
        
        # Carrega domínios conhecidos do banco
        await self._reload_known_domains()
        
        # Kafka consumer para discovery via article-published
        self._kafka_consumer = AIOKafkaConsumer(
            "article-published",
            bootstrap_servers=self._kafka_bootstrap,
            group_id="focas-v3-discovery",
            auto_offset_reset="latest",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        await self._kafka_consumer.start()
        
        self._running = True
        
        # Três loops concorrentes
        await asyncio.gather(
            self._health_cycle_loop(),
            self._discovery_kafka_loop(),
            self._discovery_classification_loop(),
        )
    
    async def stop(self):
        """Para o Focas graciosamente."""
        self._running = False
        if self._kafka_consumer:
            await self._kafka_consumer.stop()
        if self._redis:
            await self._redis.close()
        if self._pg:
            await self._pg.close()
        self.logger.info("Focas parado.")
    
    async def _health_cycle_loop(self):
        """
        Loop de health check: verifica todas as fontes a cada 10min.
        """
        self.logger.info(f"Health cycle loop iniciado ({FOCAS_HEALTH_CYCLE_MINUTES}min)")
        
        while self._running:
            cycle_start = time.monotonic()
            
            try:
                await self._run_health_cycle()
            except Exception as e:
                self.logger.error(f"Erro no health cycle: {e}")
            
            elapsed = time.monotonic() - cycle_start
            wait = max(0, FOCAS_HEALTH_CYCLE_MINUTES * 60 - elapsed)
            self.logger.info(f"Próximo health cycle em {wait:.0f}s")
            await asyncio.sleep(wait)
    
    async def _run_health_cycle(self):
        """Executa ciclo completo de health check e ajustes de polling."""
        cycle_id = f"health-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self.logger.info(f"Iniciando health cycle {cycle_id}")
        
        # 1. Carrega todas as fontes do PostgreSQL
        sources = await self._load_all_sources()
        self.logger.info(f"Carregadas {len(sources)} fontes para health check")
        
        # 2. Health check paralelo
        health_results = await health_check_all_sources(sources, self._redis)
        
        # Atualiza Prometheus
        for result in health_results:
            source_health_status.labels(
                source_id=result.source_id,
                source_name=result.source_name[:30]
            ).set(1 if result.is_healthy else 0)
        
        # 3. Calcula ajustes de polling (NUNCA desativa)
        adjustments = []
        for result in health_results:
            source = next(
                (s for s in sources if s["id"] == result.source_id),
                {}
            )
            # Busca contagem de artigos dos últimos 7 e 30 dias
            articles_7d = await self._count_articles(result.source_id, days=7)
            articles_30d = await self._count_articles(result.source_id, days=30)
            
            action = categorize_source_for_action(
                source, result, articles_7d, articles_30d
            )
            
            # Validação: nunca desativa
            assert_no_deactivation_logic(action)
            
            adjustments.append(action)
            
            # Prometheus
            source_polling_interval_seconds.labels(
                source_id=result.source_id
            ).set(action["new_interval_seconds"])
        
        # 4. Aplica ajustes no banco
        updated = await apply_catalog_updates(adjustments, self._pg)
        
        # 5. Gera alertas de fontes problemáticas
        alerts = self._alert_gen.generate_source_alerts(health_results)
        
        # 6. Publica relatório no Redis
        healthy = sum(1 for r in health_results if r.is_healthy)
        report = {
            "cycle_id": cycle_id,
            "completed_at": datetime.utcnow().isoformat(),
            "total_sources": len(sources),
            "healthy": healthy,
            "unhealthy": len(health_results) - healthy,
            "adjustments_applied": updated,
            "alerts_generated": len(alerts),
            # NUNCA tem campo "deactivated"
        }
        await self._redis.setex(
            "focas:health_report",
            3600,
            json.dumps(report, ensure_ascii=False)
        )
        
        # 7. Escreve heartbeat
        await self._redis.setex(
            "agent:focas:focas-01:heartbeat",
            900,  # 15min TTL (ciclo é a cada 10min)
            json.dumps({
                "agent_type": "focas",
                "cycle_id": cycle_id,
                "timestamp": datetime.utcnow().isoformat(),
                "healthy_sources": healthy,
            })
        )
        
        self.logger.info(
            f"Health cycle {cycle_id} concluído: "
            f"{healthy}/{len(sources)} saudáveis, "
            f"{updated} intervalos ajustados, "
            f"{len(alerts)} alertas"
        )
    
    async def _discovery_kafka_loop(self):
        """
        Loop Kafka: coleta candidatos a novas fontes de article-published.
        """
        self.logger.info("Discovery Kafka loop iniciado")
        
        async for msg in self._kafka_consumer:
            if not self._running:
                break
            
            try:
                article = msg.value
                
                # Extrai candidatos deste artigo
                candidates = extract_candidate_sources(article, self._known_domains)
                
                # Adiciona à fila de classificação
                self._discovery_queue.extend(candidates)
                
                if candidates:
                    self.logger.debug(
                        f"Discovery: {len(candidates)} candidatos extraídos de artigo "
                        f"'{article.get('titulo', '')[:50]}'"
                    )
            
            except Exception as e:
                self.logger.error(f"Erro no discovery Kafka loop: {e}")
    
    async def _discovery_classification_loop(self):
        """
        Loop de classificação: processa a fila de candidatos via LLM.
        Roda a cada hora, processa candidatos acumulados.
        """
        self.logger.info(f"Discovery classification loop iniciado ({FOCAS_DISCOVERY_CYCLE_MINUTES}min)")
        
        while self._running:
            await asyncio.sleep(FOCAS_DISCOVERY_CYCLE_MINUTES * 60)
            
            if not self._discovery_queue:
                continue
            
            # Drena a fila
            candidates = self._discovery_queue[:]
            self._discovery_queue.clear()
            
            # Remove duplicatas por domínio
            seen = set()
            unique_candidates = []
            for c in candidates:
                if c["domain"] not in seen:
                    seen.add(c["domain"])
                    unique_candidates.append(c)
            
            self.logger.info(
                f"Discovery: processando {len(unique_candidates)} candidatos únicos "
                f"(de {len(candidates)} total)"
            )
            
            approved = 0
            rejected = 0
            
            for candidate in unique_candidates:
                try:
                    # Reclassifica apenas se LLM disponível
                    if self._llm_router:
                        result = await classify_source_candidate(
                            candidate, self._llm_router
                        )
                    else:
                        # Sem LLM: aprova apenas se score inicial alto
                        result = candidate if candidate.get("initial_score", 0) >= 4 else None
                    
                    if result:
                        # Insere na tabela de discovery (status: pendente_review)
                        await self._pg.execute("""
                            INSERT INTO fontes_discovery
                                (dominio, url_candidata, encontrada_em_artigo, editoria_contexto,
                                 tipo_classificado, confiabilidade, relevancia, justificativa, tem_rss)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ON CONFLICT (dominio) DO NOTHING
                        """,
                            result["domain"],
                            result["url"],
                            result.get("found_in_article"),
                            result.get("article_editoria", ""),
                            result.get("tipo", "desconhecido"),
                            result.get("confiabilidade", 0),
                            result.get("relevancia", 0),
                            result.get("justificativa", ""),
                            result.get("tem_rss"),
                        )
                        
                        # Adiciona ao cache de domínios conhecidos
                        self._known_domains.add(result["domain"])
                        await self._redis.sadd(REDIS_KNOWN_DOMAINS, result["domain"])
                        
                        approved += 1
                        source_discovery_total.inc()
                        
                        self.logger.info(
                            f"Discovery: nova fonte aprovada: {result['domain']} "
                            f"(confiabilidade={result.get('confiabilidade')}, "
                            f"relevância={result.get('relevancia')})"
                        )
                    else:
                        rejected += 1
                
                except Exception as e:
                    self.logger.warning(f"Erro classificando {candidate.get('domain')}: {e}")
                    rejected += 1
            
            self.logger.info(
                f"Discovery cycle concluído: {approved} aprovadas, {rejected} rejeitadas"
            )
    
    async def _load_all_sources(self) -> List[Dict[str, Any]]:
        """Carrega todas as fontes do PostgreSQL."""
        rows = await self._pg.fetch("""
            SELECT
                id::text, nome, url, tipo, tier,
                polling_interval_min, ultimo_check, ultimo_sucesso,
                consecutive_failures, total_sucessos,
                artigos_7d, artigos_30d,
                config_scraper, metadata
            FROM fontes
            ORDER BY tier DESC, polling_interval_min ASC
        """)
        return [dict(row) for row in rows]
    
    async def _count_articles(self, source_id: str, days: int) -> int:
        """Conta artigos coletados de uma fonte nos últimos N dias."""
        try:
            row = await self._pg.fetchrow("""
                SELECT COUNT(*) as total
                FROM coleta_metricas
                WHERE fonte_id = $1
                    AND coletado_em >= NOW() - INTERVAL '%s days'
                    AND status = 'success'
                    AND artigos_novos > 0
            """ % days, source_id)
            return row["total"] if row else 0
        except Exception:
            return 0
    
    async def _reload_known_domains(self):
        """Recarrega cache de domínios conhecidos do PostgreSQL e Redis."""
        rows = await self._pg.fetch("SELECT url FROM fontes")
        for row in rows:
            from urllib.parse import urlparse
            parsed = urlparse(row["url"])
            domain = parsed.netloc.lower().removeprefix("www.")
            self._known_domains.add(domain)
        
        # Também carrega candidatos já descobertos (não re-processa)
        rows2 = await self._pg.fetch("SELECT dominio FROM fontes_discovery")
        for row in rows2:
            self._known_domains.add(row["dominio"])
        
        # Persiste no Redis para acesso rápido
        if self._known_domains:
            await self._redis.sadd(REDIS_KNOWN_DOMAINS, *self._known_domains)
        
        self.logger.info(f"Cache de domínios conhecidos: {len(self._known_domains)} domínios")


# Entrypoint
async def main():
    from brasileira.llm.smart_router import SmartLLMRouter
    router = SmartLLMRouter()
    
    focas = FocasV3(llm_router=router)
    try:
        await focas.start()
    except KeyboardInterrupt:
        await focas.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## PARTE XIV — TESTES

### 14.1 Testes do Monitor Sistema

```python
# tests/test_monitor_sistema.py
"""Testes para o Monitor Sistema V3."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from collections import deque

from brasileira.monitoring.throughput_tracker import ThroughputTracker
from brasileira.monitoring.alert_generator import AlertGenerator
from brasileira.monitoring.alert_deduplicator import AlertDeduplicator
from brasileira.agents.monitor_sistema import (
    calculate_throughput_health,
    MonitorSistemaV3,
    AlertSeverity,
    AlertType,
)
from brasileira.config.monitoring import EDITORIAS_V3


# ── ThroughputTracker ──────────────────────────────────────────────────────

class TestThroughputTracker:
    
    @pytest.mark.asyncio
    async def test_record_and_count(self):
        tracker = ThroughputTracker()
        now = datetime.utcnow()
        
        for i in range(30):
            await tracker.record_article("Política", now)
        
        assert tracker.get_rate_per_hour() == 30
    
    @pytest.mark.asyncio
    async def test_sliding_window_expires(self):
        tracker = ThroughputTracker()
        old = datetime.utcnow() - timedelta(hours=2)
        now = datetime.utcnow()
        
        # Artigos velhos (fora da janela de 1h)
        for _ in range(20):
            await tracker.record_article("Política", old)
        # Artigos recentes
        for _ in range(5):
            await tracker.record_article("Economia", now)
        
        # Só conta os recentes
        assert tracker.get_rate_per_hour() == 5
    
    @pytest.mark.asyncio
    async def test_coverage_gaps_detection(self):
        tracker = ThroughputTracker()
        now = datetime.utcnow()
        
        # Publica artigos para algumas editorias
        await tracker.record_article("Política", now)
        await tracker.record_article("Economia", now)
        
        # Espera-se gap nas outras 14 editorias
        gaps = tracker.get_coverage_gaps(EDITORIAS_V3, gap_minutes=120)
        
        assert len(gaps) == 14  # 16 - 2 publicadas
        editoria_names = [g["editoria"] for g in gaps]
        assert "Política" not in editoria_names
        assert "Economia" not in editoria_names
        assert "Esportes" in editoria_names
    
    @pytest.mark.asyncio
    async def test_coverage_no_gaps_when_all_published(self):
        tracker = ThroughputTracker()
        now = datetime.utcnow()
        
        for editoria in EDITORIAS_V3:
            await tracker.record_article(editoria, now)
        
        gaps = tracker.get_coverage_gaps(EDITORIAS_V3, gap_minutes=120)
        assert len(gaps) == 0
    
    @pytest.mark.asyncio
    async def test_15min_projection(self):
        tracker = ThroughputTracker()
        now = datetime.utcnow()
        
        # 10 artigos nos últimos 15min → projeta 40/hora
        for _ in range(10):
            await tracker.record_article("Tecnologia", now)
        
        projected = tracker.get_rate_last_15min_projected()
        assert projected == 40  # 10 × 4 = 40


# ── calculate_throughput_health ────────────────────────────────────────────

class TestThroughputHealth:
    
    def test_ok_status(self):
        # 40/h = burn rate 1.0 = OK
        result = calculate_throughput_health(40, 40)
        assert result["severity"] == "OK"
        assert result["meets_slo"] is True
        assert result["burn_rate_1h"] == pytest.approx(1.0)
    
    def test_warning_status(self):
        # 15/h = burn rate 0.375 = WARNING
        result = calculate_throughput_health(15, 15)
        assert result["severity"] == "WARNING"
        assert result["meets_slo"] is False
    
    def test_critical_status(self):
        # 4/h = burn rate 0.1 = CRITICAL
        result = calculate_throughput_health(4, 4)
        assert result["severity"] == "CRITICAL"
        assert result["meets_slo"] is False
    
    def test_short_window_spike_doesnt_trigger(self):
        # 1h OK mas 15min baixo → não deve ser CRITICAL (evita falsos positivos)
        result = calculate_throughput_health(
            rate_last_hour=40,          # 1h OK
            rate_last_15min_projected=8  # 15min baixo
        )
        # Com 1h OK, não deve ser CRITICAL (exige AMBAS as janelas)
        assert result["severity"] != "CRITICAL"
    
    def test_cost_never_affects_throughput(self):
        """Custo nunca deve ser fator no cálculo de throughput."""
        result = calculate_throughput_health(40, 40)
        # Resultado não tem campos de custo
        assert "cost" not in result
        assert "budget" not in result
        assert "usd" not in str(result).lower()


# ── AlertGenerator ─────────────────────────────────────────────────────────

class TestAlertGenerator:
    
    def setup_method(self):
        self.gen = AlertGenerator()
    
    def test_critical_throughput_alert(self):
        health = calculate_throughput_health(3, 3)
        alerts = self.gen.generate_throughput_alerts(health)
        
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.CRITICAL
        assert alerts[0].blocks_pipeline is False  # NUNCA bloqueia
    
    def test_no_alert_when_ok(self):
        health = calculate_throughput_health(45, 45)
        alerts = self.gen.generate_throughput_alerts(health)
        assert len(alerts) == 0
    
    def test_coverage_gap_alert(self):
        gaps = [
            {
                "editoria": "Esportes",
                "minutes_since_last": 150,  # 2.5h → WARNING
                "never_published": False,
            }
        ]
        alerts = self.gen.generate_coverage_alerts(gaps)
        
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.WARNING
        assert alerts[0].blocks_pipeline is False  # NUNCA bloqueia
    
    def test_coverage_critical_alert(self):
        gaps = [
            {
                "editoria": "Política",
                "minutes_since_last": 300,  # 5h → CRITICAL
                "never_published": False,
            }
        ]
        alerts = self.gen.generate_coverage_alerts(gaps)
        
        assert any(a.severity == AlertSeverity.CRITICAL for a in alerts)
        # Todas as alerts têm blocks_pipeline=False
        assert all(a.blocks_pipeline is False for a in alerts)
    
    def test_alerts_never_block_pipeline(self):
        """REGRA INVIOLÁVEL: nenhum alerta pode bloquear o pipeline."""
        # Pior cenário: throughput crítico + coverage crítico + agentes offline
        health = calculate_throughput_health(0, 0)
        throughput_alerts = self.gen.generate_throughput_alerts(health)
        
        coverage_gaps = [
            {"editoria": e, "minutes_since_last": 500, "never_published": False}
            for e in EDITORIAS_V3
        ]
        coverage_alerts = self.gen.generate_coverage_alerts(coverage_gaps)
        
        all_alerts = throughput_alerts + coverage_alerts
        
        # REGRA: NENHUM alerta deve bloquear o pipeline
        for alert in all_alerts:
            assert alert.blocks_pipeline is False, (
                f"VIOLAÇÃO: alerta '{alert.title}' tem blocks_pipeline=True"
            )


# ── AlertDeduplicator ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAlertDeduplicator:
    
    async def test_deduplication_works(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Não existe
        mock_redis.setex = AsyncMock()
        
        dedup = AlertDeduplicator(mock_redis)
        
        from brasileira.agents.monitor_sistema import Alert, AlertType, AlertSeverity
        alert = Alert(
            alert_id="test-1",
            alert_type=AlertType.THROUGHPUT_LOW,
            severity=AlertSeverity.WARNING,
            title="Test",
            description="Test",
        )
        
        # Primeira vez: deve enviar
        mock_redis.get.return_value = None
        result = await dedup.should_send(alert)
        assert result is True
        
        # Segunda vez (simula Redis já com a chave):
        mock_redis.get.return_value = "1"
        result2 = await dedup.should_send(alert)
        assert result2 is False


# ── Monitor Sistema integração ─────────────────────────────────────────────

@pytest.mark.asyncio
class TestMonitorSistemaIntegration:
    
    async def test_heartbeat_written_each_cycle(self):
        """Monitor deve escrever seu próprio heartbeat a cada ciclo."""
        mock_redis = AsyncMock()
        mock_redis.keys.return_value = []
        mock_redis.setex = AsyncMock()
        
        monitor = MonitorSistemaV3.__new__(MonitorSistemaV3)
        monitor._redis = mock_redis
        monitor._pg = AsyncMock()
        monitor._throughput = ThroughputTracker()
        monitor._alert_gen = AlertGenerator()
        monitor._alert_dedup = AlertDeduplicator(mock_redis)
        monitor._cycle_count = 1
        monitor.logger = MagicMock()
        
        # Mock dos métodos auxiliares
        monitor._check_agent_heartbeats = AsyncMock(return_value={})
        
        with patch("brasileira.agents.monitor_sistema.collect_pipeline_quality",
                   AsyncMock(return_value={
                       "total_published": 40,
                       "pct_sem_imagem": 0,
                       "avg_latency_sec": 30,
                       "llm_health": [],
                       "cost_info": {"total_usd_last_hour": 0.5, "note": "Informativo."},
                   })), \
             patch("brasileira.agents.monitor_sistema.update_dashboard", AsyncMock()), \
             patch("brasileira.agents.monitor_sistema._calc_system_status", return_value="healthy"):
            
            # Registra alguns artigos para ter throughput > 0
            for i in range(50):
                await monitor._throughput.record_article("Política", datetime.utcnow())
            
            await monitor._run_analysis_cycle()
        
        # Verifica que escreveu heartbeat
        heartbeat_calls = [
            call for call in mock_redis.setex.call_args_list
            if "heartbeat" in str(call)
        ]
        assert len(heartbeat_calls) >= 1
```

### 14.2 Testes do Focas

```python
# tests/test_focas.py
"""Testes para o Focas V3."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from brasileira.focas.adaptive_polling import AdaptivePollingEngine
from brasileira.focas.source_categorizer import categorize_source_for_action
from brasileira.focas.discovery_extractor import extract_candidate_sources
from brasileira.agents.focas import assert_no_deactivation_logic, SourceHealthResult
from brasileira.config.monitoring import MIN_POLLING_INTERVAL_SEC, MAX_POLLING_INTERVAL_SEC


# ── REGRA INVIOLÁVEL: NUNCA DESATIVAR ─────────────────────────────────────

class TestNeverDeactivate:
    """Testes que garantem a regra mais importante do Focas V3."""
    
    def test_assert_no_deactivation_raises_on_deactivate(self):
        """assert_no_deactivation_logic deve levantar ValueError se action for deactivate."""
        with pytest.raises(ValueError, match="VIOLAÇÃO"):
            assert_no_deactivation_logic({"action": "deactivate"})
    
    def test_assert_no_deactivation_raises_on_desativar(self):
        with pytest.raises(ValueError, match="VIOLAÇÃO"):
            assert_no_deactivation_logic({"action": "desativar_fonte"})
    
    def test_assert_no_deactivation_passes_for_adjust(self):
        """Deve passar para adjust_interval (ação correta)."""
        # Não deve levantar exceção
        assert_no_deactivation_logic({"action": "adjust_interval"})
    
    def test_source_with_10_failures_not_deactivated(self):
        """Fonte com 10+ falhas deve ter polling aumentado, nunca desativada."""
        engine = AdaptivePollingEngine()
        
        source = {"id": "src-1", "nome": "Fonte Teste", "polling_interval_min": 30, "tier": "standard"}
        health = SourceHealthResult(
            source_id="src-1",
            source_name="Fonte Teste",
            url="https://example.com",
            is_healthy=False,
            status_code=503,
            latency_ms=None,
            error_message="Service Unavailable",
            consecutive_failures=15,  # Muitas falhas
            checked_at=datetime.utcnow(),
        )
        
        action = categorize_source_for_action(source, health, articles_7d=0, articles_30d=0)
        
        # DEVE ajustar intervalo para máximo (24h)
        assert action["action"] == "adjust_interval"
        assert action["new_interval_seconds"] == MAX_POLLING_INTERVAL_SEC
        # NUNCA deve ter action de desativação
        assert "deactivat" not in action["action"].lower()
        assert "desativ" not in action["action"].lower()
    
    def test_source_with_zero_articles_30d_not_deactivated(self):
        """Fonte sem artigos em 30 dias deve ter polling de 24h, nunca desativada."""
        engine = AdaptivePollingEngine()
        source = {"id": "src-2", "nome": "Fonte Sazonal", "polling_interval_min": 30, "tier": "standard"}
        health = SourceHealthResult(
            source_id="src-2",
            source_name="Fonte Sazonal",
            url="https://sazonal.com.br",
            is_healthy=True,  # Fonte está viva mas sem artigos recentes
            status_code=200,
            latency_ms=300,
            error_message=None,
            consecutive_failures=0,
            checked_at=datetime.utcnow(),
        )
        
        action = categorize_source_for_action(source, health, articles_7d=0, articles_30d=0)
        
        # Deve ajustar para 24h (máximo), nunca desativar
        assert action["action"] == "adjust_interval"
        assert action["new_interval_seconds"] == MAX_POLLING_INTERVAL_SEC  # 24h
    
    def test_vip_source_always_minimum_interval(self):
        """Fontes VIP devem sempre ter intervalo mínimo (15min)."""
        source = {"id": "src-g1", "nome": "G1", "polling_interval_min": 15, "tier": "vip"}
        health = SourceHealthResult(
            source_id="src-g1",
            source_name="G1",
            url="https://g1.globo.com",
            is_healthy=True,
            status_code=200,
            latency_ms=150,
            error_message=None,
            consecutive_failures=0,
            checked_at=datetime.utcnow(),
        )
        
        action = categorize_source_for_action(source, health, articles_7d=50, articles_30d=200)
        
        assert action["new_interval_seconds"] == MIN_POLLING_INTERVAL_SEC  # 15min


# ── AdaptivePollingEngine ─────────────────────────────────────────────────

class TestAdaptivePollingEngine:
    
    def setup_method(self):
        self.engine = AdaptivePollingEngine()
    
    def test_high_productivity_source(self):
        """Fonte com >5 artigos/dia → intervalo de 15min."""
        source = {"id": "src-1", "polling_interval_min": 30, "tier": "standard"}
        health = SourceHealthResult(
            source_id="src-1", source_name="Alta Prod", url="https://example.com",
            is_healthy=True, status_code=200, latency_ms=200, error_message=None,
            consecutive_failures=0, checked_at=datetime.utcnow(),
        )
        
        interval, reason = self.engine.calculate_new_interval(source, health, articles_7d=50, articles_30d=200)
        
        assert interval == 900  # 15min
        assert "saudável" in reason
    
    def test_low_productivity_source(self):
        """Fonte com <2 artigos/dia → intervalo de 1-2h."""
        source = {"id": "src-2", "polling_interval_min": 60, "tier": "standard"}
        health = SourceHealthResult(
            source_id="src-2", source_name="Baixa Prod", url="https://example.com",
            is_healthy=True, status_code=200, latency_ms=500, error_message=None,
            consecutive_failures=0, checked_at=datetime.utcnow(),
        )
        
        interval, reason = self.engine.calculate_new_interval(source, health, articles_7d=3, articles_30d=10)
        
        assert interval >= 3600  # No mínimo 1h para fonte de baixa produtividade
    
    def test_interval_never_exceeds_max(self):
        """Intervalo nunca deve exceder MAX_POLLING_INTERVAL_SEC."""
        source = {"id": "src-3", "polling_interval_min": 1440, "tier": "standard"}
        health = SourceHealthResult(
            source_id="src-3", source_name="Lenta", url="https://example.com",
            is_healthy=False, status_code=503, latency_ms=None, error_message="Timeout",
            consecutive_failures=20, checked_at=datetime.utcnow(),
        )
        
        interval, _ = self.engine.calculate_new_interval(source, health, articles_7d=0, articles_30d=0)
        
        assert interval <= MAX_POLLING_INTERVAL_SEC  # Nunca > 24h
    
    def test_interval_never_below_min(self):
        """Intervalo nunca deve ser menor que MIN_POLLING_INTERVAL_SEC."""
        source = {"id": "src-4", "polling_interval_min": 5, "tier": "standard"}  # 5min no banco
        health = SourceHealthResult(
            source_id="src-4", source_name="Super Ativa", url="https://example.com",
            is_healthy=True, status_code=200, latency_ms=50, error_message=None,
            consecutive_failures=0, checked_at=datetime.utcnow(),
        )
        
        interval, _ = self.engine.calculate_new_interval(source, health, articles_7d=100, articles_30d=400)
        
        assert interval >= MIN_POLLING_INTERVAL_SEC  # Nunca < 15min


# ── Discovery ──────────────────────────────────────────────────────────────

class TestDiscovery:
    
    def test_extract_candidates_from_article(self):
        """Deve extrair domínios desconhecidos de artigos."""
        known_domains = {"g1.globo.com", "folha.uol.com.br"}
        
        article = {
            "id": "art-123",
            "editoria": "Política",
            "titulo": "Novo acordo de segurança",
            "conteudo": (
                "Segundo a <a href='https://agenciabrasil.ebc.com.br/noticia'>Agência Brasil</a>, "
                "o governo federal anunciou medidas. "
                "Mais informações em https://senado.leg.br/noticias/123 "
                "e https://folha.uol.com.br/poder/2026 (já conhecida)."
            ),
            "url_fonte": "https://agenciabrasil.ebc.com.br/noticia",
        }
        
        candidates = extract_candidate_sources(article, known_domains)
        
        # agenciabrasil.ebc.com.br é novo (não em known_domains)
        # senado.leg.br é novo
        # folha.uol.com.br é conhecido → ignorado
        domains_found = {c["domain"] for c in candidates}
        assert "agenciabrasil.ebc.com.br" in domains_found or "ebc.com.br" in domains_found
        assert "folha.uol.com.br" not in domains_found
    
    def test_social_media_ignored(self):
        """Redes sociais devem ser ignoradas no discovery."""
        article = {
            "id": "art-456",
            "editoria": "Política",
            "conteudo": (
                "Ver em https://twitter.com/senadofederal e "
                "https://facebook.com/camara e "
                "https://senado.leg.br/noticias"
            ),
        }
        
        candidates = extract_candidate_sources(article, set())
        domains = {c["domain"] for c in candidates}
        
        assert "twitter.com" not in domains
        assert "facebook.com" not in domains
    
    def test_government_domains_get_high_initial_score(self):
        """Domínios .gov.br devem ter score inicial alto."""
        article = {
            "id": "art-789",
            "editoria": "Política",
            "conteudo": "Ver em https://www.saude.gov.br/noticias/2026",
        }
        
        candidates = extract_candidate_sources(article, set())
        gov_candidates = [c for c in candidates if ".gov.br" in c["domain"]]
        
        assert len(gov_candidates) > 0
        assert gov_candidates[0]["initial_score"] >= 2  # Pelo menos 2 pontos por .gov.br
    
    def test_max_candidates_per_article(self):
        """Não deve retornar mais de MAX_CANDIDATES_PER_ARTICLE candidatos."""
        from brasileira.config.monitoring import MAX_CANDIDATES_PER_ARTICLE
        
        # Artigo com muitos links
        urls = " ".join(f"https://fonte{i}.com.br/noticia" for i in range(50))
        article = {
            "id": "art-999",
            "editoria": "Geral",
            "conteudo": urls,
        }
        
        candidates = extract_candidate_sources(article, set())
        assert len(candidates) <= MAX_CANDIDATES_PER_ARTICLE


# ── SourceHealthResult ─────────────────────────────────────────────────────

class TestSourceHealthResult:
    
    def test_health_tier_fast(self):
        result = SourceHealthResult(
            source_id="1", source_name="Fast", url="https://fast.com",
            is_healthy=True, status_code=200, latency_ms=200,
            error_message=None, consecutive_failures=0, checked_at=datetime.utcnow()
        )
        assert result.health_tier == "fast"
    
    def test_health_tier_slow_never_dead(self):
        """health_tier nunca deve ser 'dead' — máximo é 'slow'."""
        result = SourceHealthResult(
            source_id="2", source_name="Dead-ish", url="https://dead.com",
            is_healthy=False, status_code=503, latency_ms=None,
            error_message="Timeout", consecutive_failures=100,
            checked_at=datetime.utcnow()
        )
        # Máximo é 'slow' — nunca 'dead'
        assert result.health_tier == "slow"
        assert result.health_tier != "dead"
    
    def test_no_dead_tier_exists(self):
        """Garantia estática: 'dead' não pode ser retornado como health_tier."""
        all_tiers = {"fast", "healthy", "flaky", "degraded", "slow"}
        assert "dead" not in all_tiers
        assert "desativada" not in all_tiers
        assert "inactive" not in all_tiers
```

---

## PARTE XV — CHECKLIST DE IMPLEMENTAÇÃO

### 15.1 Monitor Sistema — Checklist Sequencial

```
FASE 1: Infraestrutura Base
─────────────────────────────────────────────────────────────────────────────
[ ] 1.1 Criar brasileira/config/monitoring.py com TODAS as constantes
        → THROUGHPUT_SLO_PER_HOUR = 40 (não 1!)
        → COVERAGE_GAP_MINUTES_WARNING = 120
        → MAX_POLLING_INTERVAL_SEC = 86400 (24h)
        → SEM constante DAILY_BUDGET_USD como limite
[ ] 1.2 Criar brasileira/monitoring/__init__.py
[ ] 1.3 Criar ThroughputTracker com deque de timestamps por editoria
        → Testar: 30 artigos em 1h → get_rate_per_hour() == 30
        → Testar: artigos velhos (>1h) não contam na janela
        → Testar: get_coverage_gaps() detecta editorias sem artigo
[ ] 1.4 Criar tabela monitor_alertas no PostgreSQL
        → CHECK: blocks_pipeline DEFAULT FALSE (não editável)
[ ] 1.5 Criar Prometheus metrics em observability/metrics.py

FASE 2: Kafka Consumer
─────────────────────────────────────────────────────────────────────────────
[ ] 2.1 MonitorSistemaV3.__init__: inicializar AIOKafkaConsumer
        → Tópico: article-published, group_id: monitor-sistema-v3
        → auto_offset_reset: "latest" (não processa histórico)
[ ] 2.2 _kafka_consumer_loop: registra cada artigo no ThroughputTracker
        → Testar: mensagem Kafka → tracker atualizado
[ ] 2.3 _analysis_cycle_loop: roda a cada 60 segundos
        → Usar asyncio.gather() para rodar ambos os loops concorrentes

FASE 3: Análise e Alertas
─────────────────────────────────────────────────────────────────────────────
[ ] 3.1 Implementar calculate_throughput_health()
        → Testar todos os cenários: OK, WARNING, CRITICAL
        → Confirmar: custo NUNCA aparece nos cálculos
[ ] 3.2 Implementar AlertGenerator.generate_throughput_alerts()
        → Confirmar: alerts[0].blocks_pipeline == False
[ ] 3.3 Implementar AlertGenerator.generate_coverage_alerts()
        → Threshold: 120min WARNING, 240min CRITICAL
[ ] 3.4 Implementar AlertDeduplicator com cooldowns por tipo
        → Testar: mesmo alerta em 5min → segundo é suprimido
[ ] 3.5 Implementar _check_agent_heartbeats() via Redis
        → Threshold por tipo de agente (ver HEARTBEAT_STALE_SECONDS)

FASE 4: Dashboard
─────────────────────────────────────────────────────────────────────────────
[ ] 4.1 Implementar update_dashboard() → Redis DASHBOARD_KEY
        → TTL: 120s (expirar se Monitor parar)
        → cost_info presente mas não influencia system_status
[ ] 4.2 Implementar collect_pipeline_quality() via PostgreSQL
        → Custo no campo "cost_info" como informação
        → Nunca em threshold ou bloqueio
[ ] 4.3 Implementar _persist_alert() no PostgreSQL
        → blocks_pipeline SEMPRE False no INSERT

FASE 5: Validação
─────────────────────────────────────────────────────────────────────────────
[ ] 5.1 Rodar todos os testes de TestThroughputTracker
[ ] 5.2 Rodar todos os testes de TestThroughputHealth
[ ] 5.3 Rodar todos os testes de TestAlertGenerator
        → CRÍTICO: test_alerts_never_block_pipeline deve PASSAR
[ ] 5.4 Rodar TestMonitorSistemaIntegration
[ ] 5.5 Smoke test: iniciar Monitor + publicar 30 artigos → dashboard aparece no Redis
[ ] 5.6 Smoke test: parar de publicar 30min → alerta WARNING no log
[ ] 5.7 Confirmar: custo presente no dashboard como info, sem alertas de custo
```

### 15.2 Focas — Checklist Sequencial

```
FASE 1: Remoção do V2 Problemático
─────────────────────────────────────────────────────────────────────────────
[ ] 1.1 DELETAR ou DESABILITAR focas-8.py (V2)
[ ] 1.2 Confirmar que NÃO existem imports de:
        - PRODUCTIVITY_DEAD_DAYS
        - deactivate()
        - deactivated_sources
        → grep -r "PRODUCTIVITY_DEAD_DAYS\|deactivat\|desativ" brasileira/

FASE 2: Infraestrutura
─────────────────────────────────────────────────────────────────────────────
[ ] 2.1 Criar tabela fontes_discovery no PostgreSQL
[ ] 2.2 Garantir que tabela fontes NÃO tem coluna boolean "ativo"
        → ALTER TABLE fontes DROP COLUMN IF EXISTS ativo;
[ ] 2.3 Criar brasileira/focas/__init__.py e módulos

FASE 3: Health Check
─────────────────────────────────────────────────────────────────────────────
[ ] 3.1 Implementar health_check_all_sources() com semáforo (max 50 concurrent)
        → HEAD request → fallback GET → resultado normalizado
        → Timeout: 15s HEAD, 20s GET
[ ] 3.2 Implementar SourceHealthResult com health_tier
        → Testar: health_tier nunca retorna "dead"
        → Testar: 100 falhas consecutivas → "slow" (não "dead")
[ ] 3.3 Testar health check paralelo com 648 fontes simuladas

FASE 4: Adaptive Polling
─────────────────────────────────────────────────────────────────────────────
[ ] 4.1 Implementar AdaptivePollingEngine.calculate_new_interval()
        → Testar: fonte VIP → sempre MIN_POLLING_INTERVAL_SEC (15min)
        → Testar: 10+ falhas → MAX_POLLING_INTERVAL_SEC (24h)
        → Testar: intervalo nunca < MIN nem > MAX
[ ] 4.2 Implementar categorize_source_for_action()
        → action SEMPRE "adjust_interval"
        → NUNCA "deactivate"
[ ] 4.3 Implementar assert_no_deactivation_logic()
        → Chamar ANTES de todo UPDATE no banco
[ ] 4.4 Implementar apply_catalog_updates() → UPDATE fontes SET polling_interval_min
        → Confirmar: UPDATE não tem SET ativo=false

FASE 5: Discovery
─────────────────────────────────────────────────────────────────────────────
[ ] 5.1 Implementar extract_candidate_sources()
        → Testar: links de redes sociais ignorados
        → Testar: domínios conhecidos ignorados
        → Testar: .gov.br tem score inicial alto
        → Testar: máximo MAX_CANDIDATES_PER_ARTICLE por artigo
[ ] 5.2 Implementar _known_domains_cache.py com reload periódico
[ ] 5.3 Implementar classify_source_candidate() via LLM (task="classificacao_categoria")
        → Tier ECONÔMICO (conforme tabela do briefing principal)
        → Threshold: confiabilidade >= 4 E relevância >= 5
[ ] 5.4 Testar discovery end-to-end:
        → Simular article-published com link para nova fonte
        → Confirmar: nova fonte aparece em fontes_discovery com status "pendente_review"

FASE 6: Loops Concorrentes
─────────────────────────────────────────────────────────────────────────────
[ ] 6.1 Implementar FocasV3.start() com asyncio.gather(3 loops)
[ ] 6.2 Implementar _health_cycle_loop (10min)
[ ] 6.3 Implementar _discovery_kafka_loop (contínuo)
[ ] 6.4 Implementar _discovery_classification_loop (1h)
[ ] 6.5 Heartbeat escrito a cada ciclo de health check

FASE 7: Validação
─────────────────────────────────────────────────────────────────────────────
[ ] 7.1 Rodar TestNeverDeactivate — TODOS devem passar
        → test_source_with_10_failures_not_deactivated: PASS
        → test_source_with_zero_articles_30d_not_deactivated: PASS
[ ] 7.2 Rodar TestAdaptivePollingEngine
[ ] 7.3 Rodar TestDiscovery
[ ] 7.4 Smoke test: iniciar Focas com 648 fontes simuladas
        → 600+ healthy → relatório no Redis
        → Fontes com 20 falhas → polling de 24h, NÃO desativadas
[ ] 7.5 Smoke test: publicar artigo com link novo → fonte aparece em fontes_discovery
[ ] 7.6 Verificação final:
        grep -rn "deactivat\|desativ\|PRODUCTIVITY_DEAD" brasileira/agents/focas.py
        → Output deve ser VAZIO
```

### 15.3 Validação Final: Regras Invioláveis

```
REGRAS INVIOLÁVEIS — CONFIRMAR ANTES DO DEPLOY
═══════════════════════════════════════════════
[ ] REGRA 1: Custo como INFORMAÇÃO, nunca bloqueio
    → monitor_alertas.blocks_pipeline = FALSE em todos os registros
    → calculate_throughput_health() não tem parâmetro de custo
    → dashboard cost_info não influencia system_status

[ ] REGRA 2: NUNCA desativar fontes automaticamente
    → grep -rn "deactivate\|desativar" brasileira/ → vazio (exceto comentários históricos)
    → assert_no_deactivation_logic() chamada antes de todo UPDATE
    → Tabela fontes sem coluna "ativo" (ou ativo sempre TRUE)
    → test_source_with_10_failures_not_deactivated: PASS

[ ] REGRA 3: Foco em throughput e cobertura, NÃO em custos
    → THROUGHPUT_SLO_PER_HOUR = 40 (não 1!)
    → COVERAGE_GAP_MINUTES_WARNING = 120 configurado
    → AlertType.THROUGHPUT_* e AlertType.COVERAGE_* existem
    → Sem AlertType.COST_SPIKE ou similar

[ ] REGRA 4: Alertas de throughput corretos
    → < 20 artigos/hora = WARNING
    → < 5 artigos/hora = CRITICAL
    → Editorias com 0 artigos em 2h = WARNING
    → Fontes com 10+ falhas = alerta informativo (fonte permanece ativa)
```

---

## REFERÊNCIAS E FONTES

- **Observabilidade 2026:** [IBM Observability Trends 2026](https://www.ibm.com/think/insights/observability-trends) — AI-driven observability, agentic monitoring patterns.
- **SLO Alerting:** [OneUptime SLO Alerting Strategies (2026)](https://oneuptime.com/blog/post/2026-01-30-slo-alerting-strategies/view) — burn rate, multi-window alerts, two-window approach.
- **Throughput SLOs:** [OneUptime Throughput SLOs (2026)](https://oneuptime.com/blog/post/2026-01-30-throughput-slos/view) — rate-based e count-based throughput tracking.
- **Adaptive Polling:** [Reactive Polling Patterns (DEV Community, 2025)](https://dev.to/alex-nguyen-duy-anh/reactive-polling-efficient-data-monitoring-3ed) — exponential backoff, reset-on-change, dynamic intervals.
- **RSS Adaptive Fetching:** [Building an Intelligent RSS Feed Fetcher (2025)](https://nikolajjsj.com/blog/building-an-intelligent-rss-feed-fetcher/) — adaptive intervals, worker pools, pattern recognition.
- **Alert Fatigue:** [LogicMonitor Observability Trends 2026](https://www.logicmonitor.com/blog/observability-ai-trends-2026) — 36% das equipes soterradas por alertas; necessidade de deduplicação.
- **News Source Discovery:** [WISE Framework for News Crawling (Nature, 2025)](https://www.nature.com/articles/s41598-025-25616-x) — semantic extraction, adaptive crawling strategies.

---

*Briefing gerado em 26 de março de 2026. Componente #12 do sistema brasileira.news V3.*
*Versão: 3.0.0 | Prioridade: Alta | Dependências: SmartLLMRouter (#1), Worker Pool Coletores (#2)*
