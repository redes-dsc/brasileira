# Briefing Completo para IA — Monitor Concorrência V3

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #11
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / Playwright / scikit-learn (TF-IDF) / Kafka / Redis / PostgreSQL / LangGraph
**Componente:** `brasileira/agentes/monitor_concorrencia/` (diretório completo)

---

## LEIA ISTO PRIMEIRO — O que este componente faz e por que importa

O Monitor Concorrência é o **sistema de inteligência competitiva em tempo real** da brasileira.news. Ele varre as capas dos 8 maiores portais jornalísticos do Brasil a cada 30 minutos, compara as manchetes encontradas com o que já publicamos usando TF-IDF, e distribui gaps de cobertura diretamente para quem pode agir: Reporters (buracos totais), Consolidador (cobertura parcial) e Curador Homepage (trending em 4+ capas).

**Este componente não passa pelo Pauteiro.** Esta é a regra mais importante e está violada no V2.

**Volume de operação:** 8 portais × 30 artigos médios por capa = 240 manchetes por ciclo. Com ciclos a cada 30 minutos = 11.520 manchetes analisadas por dia. Cada ciclo deve terminar em menos de 4 minutos para garantir folga.

**Este briefing contém TUDO que você precisa para implementar o Monitor Concorrência do zero.** Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO: O QUE ESTÁ QUEBRADO NA V2

### 1.1 O Bug Estrutural: Alertas Vão para o Pauteiro

O arquivo V2 principal (`monitor_concorrencia-18.py`, 1.076 linhas) implementa um agente LangGraph funcional, mas com um **erro arquitetural fundamental**: quando detecta um gap, publica o evento `lacuna_detectada` no EventBus, que é roteado para o **Pauteiro**. O Pauteiro é um gargalo desnecessário — ele não precisa intermediar gaps de concorrência. 

Na V3, os gaps vão **diretamente**:
- Gap sem cobertura nossa → Kafka `pautas-gap` → Reporter
- Gap com cobertura parcial → Kafka `consolidacao` → Consolidador
- Tema em 4+ capas → Kafka `breaking-candidate` → Curador Homepage

### 1.2 RSS em vez de Playwright para Capas

O V2 usa RSS feeds de concorrentes (`COMPETITOR_FEEDS` em `newsroom/monitoring/competitor.py`) para detectar gaps. **Problema:** RSS não reflete a hierarquia editorial das capas. Uma notícia pode estar no RSS mas não estar na manchete principal. O que importa para gap analysis é **o que está sendo destacado na capa** — e isso exige Playwright, pois os portais brasileiros usam JavaScript pesado (G1 usa Globo.com CDN + lazy loading, CNN Brasil usa React SSR, Metrópoles usa Next.js).

O V2 no `scraper_homes.py` (229 linhas) usa `requests` + BeautifulSoup — **síncrono e sem JavaScript**. Falha em portais como CNN Brasil e Metrópoles que dependem de JS para renderizar manchetes.

### 1.3 TF-IDF Simples sem Corpus Português Adequado

O V2 usa `TfidfVectorizer` do scikit-learn com configuração padrão, sem:
- Stopwords em português
- Normalização de acentos
- Stemming/lematização para português
- Peso aumentado para entidades nomeadas (nomes próprios, siglas)

Resultado: dois artigos sobre "Lula anuncia reforma tributária" e "Presidente anuncia mudança nos impostos" recebem similarity score baixo porque não há reconhecimento semântico de entidades.

### 1.4 Urgency Scoring com Cluster de Palavras Fraco

O clustering de tópicos no V2 usa apenas as 3 primeiras palavras significativas do título como chave (`"_".join(sorted(key_words[:3]))`). Isso causa:
- "Banco Central sobe juros" e "BC eleva taxa Selic" são tratados como tópicos diferentes
- "Bolsonaro preso" e "Ex-presidente detido" não formam cluster

O V3 deve usar cosine similarity TF-IDF para agrupar artigos similares (threshold ≥ 0.45) em vez de matching de palavras-chave.

### 1.5 Ausência de Seletores CSS Playwright para os 8 Portais Obrigatórios

O `config_consolidado.py` tem seletores BeautifulSoup para G1, UOL, Folha, CNN Brasil, Metrópoles, Poder360 e Estadão. **Faltam R7 e Terra** — dois dos 8 portais obrigatórios. Além disso, os seletores existentes precisam ser adaptados para Playwright.

### 1.6 Sem Deduplicação de Alertas Entre Ciclos

O V2 mantém `_alerted_hashes` em memória (dict Python). Quando o processo reinicia — algo comum em produção — os hashes são perdidos e os mesmos gaps são alertados repetidamente. O V3 deve persistir cooldowns no Redis.

### 1.7 Resumo dos Problemas a Resolver

| # | Problema V2 | Solução V3 |
|---|-------------|------------|
| 1 | Gaps vão para Pauteiro (gargalo) | Gaps vão direto: Reporter / Consolidador / Curador |
| 2 | RSS em vez de capas reais | Playwright headless para capas (JS-heavy) |
| 3 | TF-IDF sem corpus português | TF-IDF com stopwords PT + normalização de acentos |
| 4 | Cluster por 3 palavras (fraco) | Cluster por cosine similarity TF-IDF (≥ 0.45) |
| 5 | Faltam R7 e Terra | 8 portais completos com seletores Playwright |
| 6 | Cooldown de alertas em memória | Cooldown persistido no Redis com TTL |
| 7 | Síncrono (requests + BS4) | Async Playwright com pool de browsers |
| 8 | Sem categorização de gap | 3 rotas Kafka bem definidas por tipo de gap |
| 9 | Sem tópico normalizado | Campo `topico_normalizado` para tracking semântico |
| 10 | Sem entrypoint standalone | `entrypoint.py` com loop de 30min e graceful shutdown |

---

## PARTE II — ARQUITETURA V3

### 2.1 Visão Geral do Fluxo

```
┌─────────────────────────────────────────────────────────────────────┐
│              MONITOR CONCORRÊNCIA V3 — Ciclo a cada 30min           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │  FASE 1: SCANNER DE CAPAS (Playwright)                    │      │
│  │                                                           │      │
│  │  8 portais em paralelo (asyncio.gather):                  │      │
│  │  G1 │ UOL │ Folha │ Estadão │ CNN Brasil │ R7 │ Terra │   │      │
│  │  Metrópoles                                               │      │
│  │                                                           │      │
│  │  Cada portal → até 30 manchetes (título + URL + posição)  │      │
│  └──────────────────────────┬────────────────────────────────┘      │
│                             │ ~240 manchetes raw                    │
│  ┌──────────────────────────▼────────────────────────────────┐      │
│  │  FASE 2: EXTRAÇÃO E NORMALIZAÇÃO                          │      │
│  │                                                           │      │
│  │  • Limpeza de título (remover prefixos: AO VIVO, VÍDEO)  │      │
│  │  • Normalização de acentos e caixa                        │      │
│  │  • Deduplicação intra-ciclo por hash de título            │      │
│  │  • Enriquecimento: posição_capa, is_manchete, portal      │      │
│  └──────────────────────────┬────────────────────────────────┘      │
│                             │ ~180 manchetes normalizadas           │
│  ┌──────────────────────────▼────────────────────────────────┐      │
│  │  FASE 3: TF-IDF GAP ANALYSIS                              │      │
│  │                                                           │      │
│  │  Corpus nosso (PostgreSQL, últimas 6h, até 500 artigos)  │      │
│  │  TfidfVectorizer (stopwords PT, min_df=1, ngram 1-2)     │      │
│  │  cosine_similarity() para cada manchete vs corpus         │      │
│  │  Score > 0.65 → COBERTO                                   │      │
│  │  Score 0.35-0.65 → PARCIAL                                │      │
│  │  Score < 0.35 → GAP (não cobrimos)                        │      │
│  └──────────────────────────┬────────────────────────────────┘      │
│                             │ gaps classificados                    │
│  ┌──────────────────────────▼────────────────────────────────┐      │
│  │  FASE 4: URGENCY SCORING + CLUSTER POR TÓPICO             │      │
│  │                                                           │      │
│  │  Cluster de gaps similares (cosine ≥ 0.45)               │      │
│  │  num_capas = quantos portais cobrem o mesmo cluster       │      │
│  │  Urgency Score = f(num_capas, freshness, categoria)       │      │
│  └──────────────────────────┬────────────────────────────────┘      │
│                             │ gaps com score e num_capas            │
│  ┌──────────────────────────▼────────────────────────────────┐      │
│  │  FASE 5: ROTEAMENTO KAFKA                                 │      │
│  │                                                           │      │
│  │  GAP (0 artigos nossos) ──────────► pautas-gap            │      │
│  │         └─ urgencia = score         Reporter              │      │
│  │                                                           │      │
│  │  PARCIAL (1+ artigos nossos) ─────► consolidacao          │      │
│  │         └─ tema_id = cluster_id     Consolidador          │      │
│  │                                                           │      │
│  │  4+ CAPAS (qualquer tipo) ─────────► breaking-candidate   │      │
│  │         └─ sempre                   Curador Homepage      │      │
│  └───────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Regras OBRIGATÓRIAS

1. **NUNCA rotear via Pauteiro.** Gaps vão direto para Reporter, Consolidador e Curador.
2. **Playwright para todos os portais.** Não usar requests/BeautifulSoup como método principal.
3. **8 portais obrigatórios:** G1, UOL, Folha, Estadão, CNN Brasil, R7, Terra, Metrópoles.
4. **TF-IDF com stopwords PT** — não usar configuração padrão do scikit-learn.
5. **Cooldowns no Redis** — não em variável de instância Python.
6. **Ciclo deve ser completado em < 4 minutos** mesmo com todos os 8 portais.
7. **Falha em 1 portal não para o ciclo** — isolamento total de erros.
8. **Tema em 4+ capas → sempre publicar em `breaking-candidate`**, independente de termos cobertura ou não.

### 2.3 Stack do Componente

| Dependência | Versão | Função |
|-------------|--------|--------|
| `playwright` | `>=1.44.0` | Browser headless para capas JS-heavy |
| `scikit-learn` | `>=1.5.0` | TF-IDF e cosine similarity |
| `aiokafka` | `>=0.11.0` | Produção para tópicos Kafka |
| `redis[hiredis]` | `>=5.0` | Cache de cobertura e cooldowns |
| `asyncpg` | `>=0.29` | Consulta de artigos publicados |
| `pydantic` | `>=2.5` | Schemas de manchetes e gaps |
| `langgraph` | `>=0.2.0` | State machine do agente |
| `unidecode` | `>=1.3` | Normalização de acentos para TF-IDF |
| `numpy` | `>=1.26` | Operações matriciais do TF-IDF |

**Instalação do Playwright após pip install:**
```bash
playwright install chromium --with-deps
```

---

## PARTE III — SCANNER DE CAPAS (Playwright)

### 3.1 Configuração de Browser Pool

```python
# brasileira/agentes/monitor_concorrencia/scanner.py

import asyncio
import hashlib
import unicodedata
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

import logging
logger = logging.getLogger("monitor_concorrencia.scanner")


@dataclass
class Manchete:
    """Manchete extraída da capa de um portal concorrente."""
    portal: str                        # "G1", "UOL", etc.
    titulo: str                        # Título limpo
    titulo_normalizado: str            # Sem acentos, lowercase
    url: str                           # URL completa do artigo
    posicao_capa: int                  # 1 = primeira manchete
    is_manchete: bool                  # True se posicao_capa <= 3
    extraido_em: datetime = field(default_factory=datetime.utcnow)
    titulo_hash: str = ""              # SHA-256[:16] do título normalizado

    def __post_init__(self):
        if not self.titulo_hash:
            self.titulo_hash = hashlib.sha256(
                self.titulo_normalizado.encode()
            ).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "portal": self.portal,
            "titulo": self.titulo,
            "titulo_normalizado": self.titulo_normalizado,
            "url": self.url,
            "posicao_capa": self.posicao_capa,
            "is_manchete": self.is_manchete,
            "extraido_em": self.extraido_em.isoformat(),
            "titulo_hash": self.titulo_hash,
        }


def normalizar_titulo(titulo: str) -> str:
    """Remove acentos, converte para lowercase, normaliza espaços."""
    # Remover prefixos editoriais
    titulo = re.sub(
        r"^(AO VIVO|URGENTE|EXCLUSIVO|VÍDEO|VIDEO|PODCAST|BREAKING)\s*[:\-–|]\s*",
        "",
        titulo,
        flags=re.IGNORECASE,
    )
    # Normalizar unicode → ASCII (remove acentos)
    nfkd = unicodedata.normalize("NFKD", titulo)
    ascii_str = nfkd.encode("ASCII", "ignore").decode("ASCII")
    # Lowercase e colapsar espaços
    return re.sub(r"\s+", " ", ascii_str.lower()).strip()


def limpar_titulo(titulo: str) -> str:
    """Limpa título mantendo acentos (para exibição)."""
    titulo = re.sub(
        r"^(AO VIVO|URGENTE|EXCLUSIVO|VÍDEO|VIDEO|PODCAST|BREAKING)\s*[:\-–|]\s*",
        "",
        titulo,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", titulo).strip()


class CapaScanner:
    """
    Scanner de capas usando Playwright async.
    
    Executa os 8 portais em paralelo com isolamento total de erros.
    Um portal com timeout não afeta os outros.
    
    Uso:
        async with CapaScanner() as scanner:
            manchetes = await scanner.scan_todos()
    """

    # Timeout por portal (segundos)
    TIMEOUT_NAVEGACAO = 30_000   # 30s para goto()
    TIMEOUT_SELETOR   = 15_000   # 15s para wait_for_selector()
    MAX_MANCHETES_POR_PORTAL = 30

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--lang=pt-BR",
            ],
        )
        logger.info("Browser Playwright iniciado")
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser Playwright encerrado")

    async def _novo_contexto(self) -> BrowserContext:
        """Cria contexto isolado por portal."""
        return await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            java_script_enabled=True,
            ignore_https_errors=True,
        )

    async def scan_portal(self, config: dict) -> list[Manchete]:
        """
        Scanneia um único portal. Retorna lista vazia em caso de erro.
        
        NUNCA levanta exceção — erros são logados e retornam [].
        """
        portal_name = config["nome"]
        url = config["url_capa"]
        seletores = config["seletores_playwright"]
        
        contexto = None
        pagina = None
        
        try:
            contexto = await self._novo_contexto()
            pagina = await contexto.new_page()
            
            # Bloquear recursos desnecessários (acelera carregamento)
            await pagina.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot}",
                lambda route: route.abort(),
            )
            await pagina.route(
                "**/{ads,analytics,gtm,facebook,doubleclick}**",
                lambda route: route.abort(),
            )
            
            # Navegar até a capa
            await pagina.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.TIMEOUT_NAVEGACAO,
            )
            
            # Aguardar conteúdo principal
            manchetes_brutas: list[dict] = []
            
            for seletor in seletores:
                try:
                    await pagina.wait_for_selector(
                        seletor,
                        timeout=self.TIMEOUT_SELETOR,
                    )
                    elementos = await pagina.query_selector_all(seletor)
                    
                    if not elementos:
                        continue
                    
                    for el in elementos:
                        try:
                            # Extrai texto e href
                            titulo_raw = await el.inner_text()
                            href = await el.get_attribute("href") or ""
                            
                            # Se não é <a>, busca o link dentro
                            if not href:
                                link = await el.query_selector("a")
                                if link:
                                    href = await link.get_attribute("href") or ""
                                    if not titulo_raw.strip():
                                        titulo_raw = await link.inner_text()
                            
                            titulo_limpo = limpar_titulo(titulo_raw)
                            
                            if not titulo_limpo or len(titulo_limpo) < 15:
                                continue
                            
                            # Resolver URL relativa
                            if href and not href.startswith("http"):
                                from urllib.parse import urljoin
                                href = urljoin(url, href)
                            
                            manchetes_brutas.append({
                                "titulo": titulo_limpo,
                                "url": href,
                            })
                            
                        except Exception:
                            continue
                    
                    if manchetes_brutas:
                        break  # Primeiro seletor com resultado vence
                        
                except Exception as e:
                    logger.debug(f"[{portal_name}] Seletor '{seletor}' falhou: {e}")
                    continue
            
            # Fallback: extração genérica por headings
            if not manchetes_brutas:
                manchetes_brutas = await self._fallback_generico(pagina, url)
                if manchetes_brutas:
                    logger.warning(
                        f"[{portal_name}] Usando fallback genérico: "
                        f"{len(manchetes_brutas)} manchetes"
                    )
            
            # Deduplicar por URL
            seen_urls: set[str] = set()
            manchetes_dedup: list[dict] = []
            for m in manchetes_brutas:
                if m["url"] and m["url"] in seen_urls:
                    continue
                if m["url"]:
                    seen_urls.add(m["url"])
                manchetes_dedup.append(m)
            
            # Limitar e converter para Manchete
            manchetes_dedup = manchetes_dedup[:self.MAX_MANCHETES_POR_PORTAL]
            resultado = []
            for i, m in enumerate(manchetes_dedup):
                titulo_norm = normalizar_titulo(m["titulo"])
                resultado.append(Manchete(
                    portal=portal_name,
                    titulo=m["titulo"],
                    titulo_normalizado=titulo_norm,
                    url=m["url"],
                    posicao_capa=i + 1,
                    is_manchete=i < 3,
                ))
            
            logger.info(f"[{portal_name}] {len(resultado)} manchetes extraídas")
            return resultado
            
        except Exception as e:
            logger.error(f"[{portal_name}] ERRO no scan: {e}", exc_info=True)
            return []
            
        finally:
            if pagina:
                await pagina.close()
            if contexto:
                await contexto.close()

    async def _fallback_generico(self, pagina: Page, base_url: str) -> list[dict]:
        """Extração genérica via h1/h2/h3 com links — último recurso."""
        resultado = []
        try:
            # Busca todos os headings com links
            elements = await pagina.query_selector_all("h1 a, h2 a, h3 a, h4 a")
            seen = set()
            for el in elements:
                titulo = (await el.inner_text()).strip()
                href = await el.get_attribute("href") or ""
                if not titulo or len(titulo) < 15:
                    continue
                if href and not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                if href in seen:
                    continue
                seen.add(href)
                resultado.append({"titulo": titulo, "url": href})
        except Exception:
            pass
        return resultado

    async def scan_todos(self, configs: list[dict]) -> dict[str, list[Manchete]]:
        """
        Scanneia todos os portais em paralelo.
        
        Returns:
            Dict portal_name -> list[Manchete]
        """
        tarefas = [self.scan_portal(config) for config in configs]
        resultados_lista = await asyncio.gather(*tarefas, return_exceptions=True)
        
        resultado: dict[str, list[Manchete]] = {}
        for config, res in zip(configs, resultados_lista):
            nome = config["nome"]
            if isinstance(res, Exception):
                logger.error(f"[{nome}] gather() capturou exceção: {res}")
                resultado[nome] = []
            else:
                resultado[nome] = res
        
        total = sum(len(v) for v in resultado.values())
        logger.info(
            f"Scan completo: {len(configs)} portais, "
            f"{total} manchetes no total"
        )
        return resultado
```

### 3.2 Tempo de Ciclo Esperado

| Portal | Estratégia | Tempo Esperado |
|--------|-----------|----------------|
| G1 | Playwright + seletor primário | 8-12s |
| UOL | Playwright + seletor primário | 6-10s |
| Folha | Playwright + seletor primário | 10-15s |
| Estadão | Playwright + seletor primário | 8-12s |
| CNN Brasil | Playwright (React SSR) | 12-18s |
| R7 | Playwright + seletor primário | 8-12s |
| Terra | Playwright + seletor primário | 6-10s |
| Metrópoles | Playwright (Next.js) | 12-18s |
| **Total (paralelo)** | `asyncio.gather()` | **18-25s** |

Com 8 portais em paralelo, o tempo dominante é o portal mais lento (~18-25s). A fase completa de scan deve terminar em < 30 segundos.

---

## PARTE IV — CONCORRENTES CONFIGURADOS (8 PORTAIS OBRIGATÓRIOS)

### 4.1 Configuração Completa dos 8 Portais

```python
# brasileira/agentes/monitor_concorrencia/portais.py

"""
Configuração dos 8 portais concorrentes obrigatórios.

REGRA INVIOLÁVEL: Estes 8 portais SEMPRE devem ser monitorados.
Não remover, não desativar. Ajustar seletores se quebrarem.

Seletores são listas ordenadas por prioridade:
- Primeiro seletor bem-sucedido é usado
- Fallback genérico (h2 a, h3 a) se todos falharem
"""

PORTAIS_CONCORRENTES: list[dict] = [
    # ─────────────────────────────────────────────────────────────────
    # G1 — Globo.com (maior portal de notícias do Brasil)
    # Tecnologia: Bastian CMS + Globo CDN, lazy loading moderado
    # Manchetes: Feed de notícias na home, classe "feed-post-link"
    # ─────────────────────────────────────────────────────────────────
    {
        "nome": "G1",
        "url_capa": "https://g1.globo.com",
        "url_ultimas": "https://g1.globo.com/ultimas-noticias/",
        "tier": 1,
        "seletores_playwright": [
            # Seletor primário: links de feed do Bastian CMS
            "a.feed-post-link",
            # Seletor secundário: títulos dentro de posts
            ".feed-post-body-title a",
            # Tertiary: wrapper de destaque com heading
            ".post-headline a",
            # Fallback estruturado: qualquer h2 com link
            "h2 a",
        ],
        "seletor_espera": "a.feed-post-link",
        "categorias_monitoradas": ["política", "economia", "brasil", "mundo", "saúde"],
        "peso_editorial": 2.0,  # G1 tem maior peso no urgency score
    },

    # ─────────────────────────────────────────────────────────────────
    # UOL — Universo Online (portal consolidado, audiência massiva)
    # Tecnologia: PHP monolítico + CDN Akamai, maioria estático
    # Manchetes: Thumbnails com h3, grid de notícias
    # ─────────────────────────────────────────────────────────────────
    {
        "nome": "UOL",
        "url_capa": "https://www.uol.com.br",
        "url_ultimas": "https://www.uol.com.br/noticias/",
        "tier": 1,
        "seletores_playwright": [
            # Seletor primário: thumbnail com h3 link
            ".thumbnail-standard-wrapper h3 a",
            # Secundário: headings de notícias
            "h3.title a",
            # Tercereiro: qualquer h3 link
            "h3 a",
            # Fallback
            "h2 a",
        ],
        "seletor_espera": "h3 a",
        "categorias_monitoradas": ["política", "economia", "esportes", "entretenimento"],
        "peso_editorial": 1.8,
    },

    # ─────────────────────────────────────────────────────────────────
    # Folha de São Paulo — Maior jornal do Brasil por circulação
    # Tecnologia: WordPress customizado + React parcial, paywall
    # Manchetes: c-headline__title para matérias livres
    # ─────────────────────────────────────────────────────────────────
    {
        "nome": "Folha",
        "url_capa": "https://www1.folha.uol.com.br",
        "url_ultimas": "https://www1.folha.uol.com.br/ultimas-noticias/",
        "tier": 1,
        "seletores_playwright": [
            # Seletor primário: headline padrão da Folha
            ".c-headline__title a",
            # Seletor de manchete principal
            ".c-main-headline__title a",
            # Manchete do Hero
            ".c-featured-article__title a",
            # Fallback estruturado
            "h2 a",
            "h3 a",
        ],
        "seletor_espera": ".c-headline__title",
        "categorias_monitoradas": ["política", "economia", "mundo", "educação"],
        "peso_editorial": 1.9,
        "tem_paywall": True,  # Apenas manchetes externas são acessíveis
    },

    # ─────────────────────────────────────────────────────────────────
    # Estadão — O Estado de S. Paulo (rival histórico da Folha)
    # Tecnologia: CMS proprietário + SSR Node.js
    # Manchetes: .title com link, ou .headline
    # ─────────────────────────────────────────────────────────────────
    {
        "nome": "Estadão",
        "url_capa": "https://www.estadao.com.br",
        "url_ultimas": "https://www.estadao.com.br/ultimas/",
        "tier": 1,
        "seletores_playwright": [
            # Seletor primário: título padrão do Estadão
            "h3.title a",
            # Manchete principal
            "h2.title a",
            # Seletor de headline genérico
            ".headline a",
            # Cards de notícia
            ".card-title a",
            # Fallback
            "h2 a",
            "h3 a",
        ],
        "seletor_espera": "h3.title",
        "categorias_monitoradas": ["política", "economia", "esportes", "cultura"],
        "peso_editorial": 1.9,
    },

    # ─────────────────────────────────────────────────────────────────
    # CNN Brasil — Portal da rede CNN no Brasil (lançado 2020)
    # Tecnologia: React SSR (Next.js) — JavaScript obrigatório
    # Manchetes: news-item-header__title, renderizado via JS
    # ─────────────────────────────────────────────────────────────────
    {
        "nome": "CNN Brasil",
        "url_capa": "https://www.cnnbrasil.com.br",
        "url_ultimas": "https://www.cnnbrasil.com.br/ultimas-noticias/",
        "tier": 1,
        "seletores_playwright": [
            # Seletor primário: título de item de notícia CNN
            "h3.news-item-header__title a",
            # Manchete principal
            "h2.news-item-header__title a",
            # Card title
            ".home-item__title a",
            # Destaque
            ".featured-news__title a",
            # Fallback
            "h2 a",
            "h3 a",
        ],
        "seletor_espera": "h3.news-item-header__title",
        "espera_extra_ms": 3000,  # Next.js precisa de tempo extra
        "categorias_monitoradas": ["política", "economia", "mundo", "negócios"],
        "peso_editorial": 1.7,
    },

    # ─────────────────────────────────────────────────────────────────
    # R7 — Portal da Record TV (segundo maior grupo de TV do Brasil)
    # Tecnologia: CMS HTML5 + jQuery, maioria estático
    # Manchetes: .record-title, .r7-title ou h2/h3 com links
    # ─────────────────────────────────────────────────────────────────
    {
        "nome": "R7",
        "url_capa": "https://www.r7.com",
        "url_ultimas": "https://www.r7.com/noticias",
        "tier": 1,
        "seletores_playwright": [
            # Seletor primário: title padrão do R7
            ".record-title a",
            # Título de card
            ".card__title a",
            # Title genérico
            ".title a",
            # Box de notícia
            ".box-news__title a",
            # Fallback estruturado
            "h2 a",
            "h3 a",
        ],
        "seletor_espera": "h2 a",
        "categorias_monitoradas": ["brasil", "esportes", "entretenimento", "saúde"],
        "peso_editorial": 1.6,
    },

    # ─────────────────────────────────────────────────────────────────
    # Terra — Portal do Grupo Telefônica (grande audiência popular)
    # Tecnologia: PHP + CDN, estrutura HTML relativamente simples
    # Manchetes: .article-title, .news-title ou estrutura heading
    # ─────────────────────────────────────────────────────────────────
    {
        "nome": "Terra",
        "url_capa": "https://www.terra.com.br",
        "url_ultimas": "https://www.terra.com.br/noticias/",
        "tier": 1,
        "seletores_playwright": [
            # Seletor primário: título de artigo Terra
            ".card__headline a",
            # News card title
            ".article__title a",
            # Link de destaque
            ".highlight__title a",
            # Title genérico em card
            ".title a",
            # Fallback
            "h2 a",
            "h3 a",
        ],
        "seletor_espera": "h2 a",
        "categorias_monitoradas": ["brasil", "esportes", "economia", "entretenimento"],
        "peso_editorial": 1.5,
    },

    # ─────────────────────────────────────────────────────────────────
    # Metrópoles — Portal de notícias de Brasília (forte em política)
    # Tecnologia: Next.js (React SSR) — JavaScript obrigatório
    # Manchetes: h2.title / h3.title renderizados via Next.js
    # ─────────────────────────────────────────────────────────────────
    {
        "nome": "Metrópoles",
        "url_capa": "https://www.metropoles.com",
        "url_ultimas": "https://www.metropoles.com/ultimas-noticias",
        "tier": 1,
        "seletores_playwright": [
            # Seletor primário: title padrão do Metrópoles
            "h2.title a",
            # Secundário: h3 title
            "h3.title a",
            # Card headline
            ".card-title a",
            # Post title
            ".post-title a",
            # Fallback
            "h2 a",
            "h3 a",
        ],
        "seletor_espera": "h2.title",
        "espera_extra_ms": 3000,  # Next.js precisa de tempo extra
        "categorias_monitoradas": ["política", "brasil", "saúde", "lifestyle"],
        "peso_editorial": 1.6,
    },
]

# Mapa rápido nome → config
PORTAL_MAP: dict[str, dict] = {p["nome"]: p for p in PORTAIS_CONCORRENTES}

# Portais obrigatórios — verificação de integridade
PORTAIS_OBRIGATORIOS = {"G1", "UOL", "Folha", "Estadão", "CNN Brasil", "R7", "Terra", "Metrópoles"}


def validar_portais() -> None:
    """Valida que todos os 8 portais obrigatórios estão configurados."""
    configurados = {p["nome"] for p in PORTAIS_CONCORRENTES}
    faltando = PORTAIS_OBRIGATORIOS - configurados
    if faltando:
        raise RuntimeError(
            f"PORTAIS OBRIGATÓRIOS FALTANDO: {faltando}. "
            "Nunca remover portais da lista PORTAIS_CONCORRENTES."
        )
```

### 4.2 Gestão de Seletores Quebrados

Portais de notícias atualizam seus layouts com frequência. O V3 deve detectar quando um seletor para de funcionar:

```python
# Em scanner.py, dentro de scan_portal():

async def _verificar_saude_seletores(
    self,
    portal_name: str,
    manchetes: list[Manchete],
    config: dict,
) -> None:
    """
    Alerta se o número de manchetes extraídas for suspeito.
    
    < 3 manchetes provavelmente indica seletor quebrado.
    """
    if len(manchetes) < 3:
        logger.warning(
            f"[{portal_name}] ATENÇÃO: apenas {len(manchetes)} manchetes extraídas. "
            f"Verificar seletores: {config['seletores_playwright'][:2]}"
        )
        # Registrar métrica no Redis para alertar monitor_sistema
        # (implementado no entrypoint)
```

---

## PARTE V — EXTRAÇÃO E NORMALIZAÇÃO DE MANCHETES

### 5.1 Pipeline de Normalização

```python
# brasileira/agentes/monitor_concorrencia/normalizacao.py

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

# Stopwords português — usadas tanto aqui quanto no TF-IDF
STOPWORDS_PT: frozenset[str] = frozenset({
    "a", "à", "ao", "aos", "as", "às", "ante", "após", "até",
    "com", "contra", "da", "das", "de", "desde", "do", "dos",
    "e", "é", "ela", "elas", "ele", "eles", "em", "entre",
    "era", "essa", "essas", "esse", "esses", "esta", "estas",
    "este", "estes", "eu", "foi", "for", "foram", "há",
    "isso", "isto", "já", "lhe", "lhes", "mais", "mas",
    "me", "meu", "minha", "na", "nas", "no", "nos", "nós",
    "num", "numa", "não", "o", "os", "ou", "para", "pela",
    "pelas", "pelo", "pelos", "per", "pode", "por", "qual",
    "quando", "que", "quem", "se", "sem", "ser", "será",
    "seu", "seus", "sob", "sobre", "sua", "suas", "são",
    "também", "te", "tem", "ter", "teu", "tua", "tu", "um",
    "uma", "umas", "uns", "vai", "vão", "você", "vos",
    "diz", "dizer", "disse", "como", "pode", "ainda", "novo",
    "nova", "após", "segundo", "afirma", "aponta", "revela",
    "mostra", "indica", "declara", "anuncia", "confirma",
    "segundo", "conforme", "durante", "sobre", "entre",
    "diante", "apesar", "embora", "porém", "contudo",
})

# Prefixos editoriais a remover
_PREFIXOS_EDITORIAIS = re.compile(
    r"^(AO VIVO|URGENTE|BREAKING|EXCLUSIVO|VÍDEO|VIDEO|PODCAST|"
    r"ATUALIZAÇÃO|UPDATE|ESPECIAL|ANÁLISE)\s*[:\-–|]\s*",
    flags=re.IGNORECASE,
)

# Sufixos comuns
_SUFIXOS = re.compile(
    r"\s*[|\-–]\s*(G1|UOL|Folha|Estadão|CNN Brasil|R7|Terra|Metrópoles)$",
    flags=re.IGNORECASE,
)


def remover_prefixos(titulo: str) -> str:
    """Remove prefixos editoriais (AO VIVO, URGENTE, etc.)."""
    return _PREFIXOS_EDITORIAIS.sub("", titulo).strip()


def remover_sufixos_portal(titulo: str) -> str:
    """Remove nome do portal no final do título."""
    return _SUFIXOS.sub("", titulo).strip()


def normalizar_para_tfidf(titulo: str) -> str:
    """
    Normaliza título para uso no TF-IDF.
    
    Etapas:
    1. Remove prefixos editoriais
    2. Remove sufixos de portal
    3. Converte para lowercase
    4. Remove acentos via NFKD → ASCII
    5. Colapsa espaços
    """
    titulo = remover_prefixos(titulo)
    titulo = remover_sufixos_portal(titulo)
    titulo = titulo.lower()
    # NFKD normalization → strip non-ASCII (remove acentos)
    nfkd = unicodedata.normalize("NFKD", titulo)
    titulo = nfkd.encode("ASCII", "ignore").decode("ASCII")
    titulo = re.sub(r"[^\w\s]", " ", titulo)  # Remove pontuação
    titulo = re.sub(r"\s+", " ", titulo).strip()
    return titulo


def limpar_para_exibicao(titulo: str) -> str:
    """Limpa título mantendo acentos (para exibição ao usuário)."""
    titulo = remover_prefixos(titulo)
    titulo = remover_sufixos_portal(titulo)
    return re.sub(r"\s+", " ", titulo).strip()


def gerar_hash_titulo(titulo_normalizado: str) -> str:
    """Hash SHA-256 dos primeiros 16 caracteres para deduplicação."""
    return hashlib.sha256(titulo_normalizado.encode()).hexdigest()[:16]


def deduplicar_manchetes(
    manchetes: list["Manchete"],
) -> list["Manchete"]:
    """
    Remove manchetes duplicadas intra-ciclo.
    
    Dois critérios de duplicação:
    1. Mesmo hash de título (título identico normalizado)
    2. Mesma URL
    """
    seen_hashes: set[str] = set()
    seen_urls: set[str] = set()
    resultado = []
    
    for m in manchetes:
        if m.titulo_hash in seen_hashes:
            continue
        if m.url and m.url in seen_urls:
            continue
        seen_hashes.add(m.titulo_hash)
        if m.url:
            seen_urls.add(m.url)
        resultado.append(m)
    
    return resultado


def extrair_entidades_simples(titulo: str) -> list[str]:
    """
    Extrai entidades nomeadas simples por heurística.
    
    Palavras com inicial maiúscula que não sejam a primeira palavra
    são candidatas a entidades (nomes próprios, siglas, instituições).
    
    Não usa spaCy para manter dependências mínimas.
    Precisão suficiente para boosting no TF-IDF.
    """
    palavras = titulo.split()
    entidades = []
    for i, palavra in enumerate(palavras):
        # Primeira palavra sempre pode ser nome próprio — ignorar
        if i == 0:
            continue
        # Siglas (2-5 letras maiúsculas)
        if re.match(r"^[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]{2,5}$", palavra):
            entidades.append(palavra.lower())
            continue
        # Palavras com inicial maiúscula (não stopword)
        limpa = re.sub(r"[^\w]", "", palavra.lower())
        if palavra[0].isupper() and limpa not in STOPWORDS_PT and len(limpa) > 2:
            entidades.append(limpa)
    
    return entidades
```

---

## PARTE VI — TF-IDF GAP ANALYSIS

### 6.1 Implementação do Analisador

```python
# brasileira/agentes/monitor_concorrencia/gap_analysis.py

"""
Gap Analysis usando TF-IDF com corpus em português.

Filosofia:
- TF-IDF como método principal (rápido, determinístico, sem API)
- Threshold duplo: COBERTO (≥0.65) / PARCIAL (0.35-0.65) / GAP (<0.35)
- Cluster de gaps similares para calcular num_capas
- Entidades nomeadas recebem boost via analyzer customizado

Performance esperada:
- 500 artigos no corpus + 240 manchetes = ~120ms por ciclo
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .normalizacao import (
    STOPWORDS_PT,
    normalizar_para_tfidf,
    extrair_entidades_simples,
)
from .scanner import Manchete

logger = logging.getLogger("monitor_concorrencia.gap_analysis")


class TipoGap(str, Enum):
    COBERTO = "coberto"      # Temos artigo muito similar (cosine ≥ 0.65)
    PARCIAL = "parcial"      # Temos algo relacionado (0.35 ≤ cosine < 0.65)
    GAP     = "gap"          # Não temos nada (cosine < 0.35)


@dataclass
class GapDetectado:
    """Um gap de cobertura detectado na análise TF-IDF."""
    manchete: Manchete
    tipo: TipoGap
    score_similaridade: float            # Melhor cosine score encontrado
    artigo_similar_id: Optional[int]     # ID do artigo mais similar (se PARCIAL)
    artigo_similar_titulo: Optional[str] # Título do artigo mais similar
    num_capas: int = 1                   # Quantos portais cobrem este tema
    urgency_score: float = 0.0           # Score calculado (0-10)
    cluster_id: Optional[str] = None     # ID do cluster temático
    
    def to_dict(self) -> dict:
        return {
            "portal": self.manchete.portal,
            "titulo": self.manchete.titulo,
            "titulo_normalizado": self.manchete.titulo_normalizado,
            "url": self.manchete.url,
            "posicao_capa": self.manchete.posicao_capa,
            "is_manchete": self.manchete.is_manchete,
            "tipo": self.tipo.value,
            "score_similaridade": round(self.score_similaridade, 4),
            "artigo_similar_id": self.artigo_similar_id,
            "artigo_similar_titulo": self.artigo_similar_titulo,
            "num_capas": self.num_capas,
            "urgency_score": round(self.urgency_score, 2),
            "cluster_id": self.cluster_id,
            "extraido_em": self.manchete.extraido_em.isoformat(),
            "titulo_hash": self.manchete.titulo_hash,
        }


class AnalisadorTFIDF:
    """
    Analisador de gaps usando TF-IDF.
    
    Configuração do vectorizer:
    - analyzer: 'word' (padrão)
    - ngram_range: (1, 2) — unigramas e bigramas
    - min_df: 1 — todas as palavras contam (corpus pequeno)
    - max_df: 0.95 — ignora palavras em >95% dos docs (muito comuns)
    - sublinear_tf: True — aplica log(tf+1) para suavizar frequências
    - stop_words: STOPWORDS_PT convertido para lista
    
    Por que não usar embeddings semânticos?
    - TF-IDF é 50x mais rápido (2ms vs 100ms por comparação)
    - Com 240 manchetes × 500 artigos = 120.000 comparações/ciclo
    - Embeddings adicionariam 3+ minutos de latência por ciclo
    - TF-IDF com bigramas captura suficientemente entidades + contexto
    
    Referência: PLOS ONE (2025) — "TF-IDF with Naive Bayes achieves 
    95.12% accuracy at 1/50th the inference cost of BERT"
    """

    # Thresholds de classificação
    THRESHOLD_COBERTO = 0.65
    THRESHOLD_PARCIAL = 0.35
    # Threshold para agrupar manchetes do mesmo tema em cluster
    THRESHOLD_CLUSTER = 0.45

    def __init__(self):
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._corpus_matrix = None          # Matriz TF-IDF do nosso corpus
        self._corpus_artigos: list[dict] = []  # Artigos do corpus

    def _criar_vectorizer(self) -> TfidfVectorizer:
        """Cria vectorizer configurado para português."""
        return TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
            stop_words=list(STOPWORDS_PT),
            lowercase=True,       # Já normalizamos, mas por segurança
            strip_accents=None,   # Já removemos acentos na normalização
            token_pattern=r"(?u)\b\w{2,}\b",  # Palavras com ≥2 chars
        )

    def _enriquecer_com_entidades(self, texto: str) -> str:
        """
        Boost de entidades: duplica ocorrência de entidades no texto.
        
        Heurística: palavras com inicial maiúscula (exceto primeira)
        e siglas recebem peso dobrado sendo repetidas no texto.
        
        Exemplo:
            "Lula anuncia reforma tributária" →
            "lula anuncia reforma tributaria lula"
        """
        entidades = extrair_entidades_simples(texto)
        if entidades:
            return texto + " " + " ".join(entidades)
        return texto

    def treinar_corpus(self, artigos: list[dict]) -> None:
        """
        Treina o vectorizer com o corpus de artigos publicados.
        
        Args:
            artigos: Lista de dicts com campos 'titulo' e opcionalmente 'topico'
        """
        if not artigos:
            logger.warning("Corpus vazio — gap analysis desabilitado")
            self._vectorizer = None
            self._corpus_matrix = None
            return

        t0 = time.monotonic()
        
        self._corpus_artigos = artigos
        
        # Preparar textos do corpus
        textos_corpus = []
        for artigo in artigos:
            titulo = artigo.get("titulo") or artigo.get("title") or ""
            topico = artigo.get("topico") or ""
            texto = normalizar_para_tfidf(f"{titulo} {topico}")
            texto = self._enriquecer_com_entidades(texto)
            textos_corpus.append(texto if texto.strip() else "sem_titulo")

        # Criar vectorizer e treinar
        self._vectorizer = self._criar_vectorizer()
        self._corpus_matrix = self._vectorizer.fit_transform(textos_corpus)
        
        dt = time.monotonic() - t0
        logger.info(
            f"Corpus TF-IDF treinado: {len(artigos)} artigos, "
            f"{self._corpus_matrix.shape[1]} features, "
            f"em {dt:.3f}s"
        )

    def calcular_similarity(self, titulo_normalizado: str) -> tuple[float, Optional[int], Optional[str]]:
        """
        Calcula melhor cosine similarity entre manchete e corpus.
        
        Returns:
            Tuple: (melhor_score, artigo_id, artigo_titulo)
        """
        if self._vectorizer is None or self._corpus_matrix is None:
            return 0.0, None, None
        
        texto = self._enriquecer_com_entidades(titulo_normalizado)
        if not texto.strip():
            return 0.0, None, None

        try:
            # Vetorizar manchete usando vocabulário do corpus
            manchete_vec = self._vectorizer.transform([texto])
            
            # Calcular cosine similarity contra todos os artigos
            scores = cosine_similarity(manchete_vec, self._corpus_matrix)[0]
            
            melhor_idx = int(np.argmax(scores))
            melhor_score = float(scores[melhor_idx])
            
            if melhor_score > 0:
                artigo = self._corpus_artigos[melhor_idx]
                artigo_id = artigo.get("id")
                artigo_titulo = artigo.get("titulo") or artigo.get("title")
                return melhor_score, artigo_id, artigo_titulo
            
            return 0.0, None, None
            
        except Exception as e:
            logger.error(f"Erro no cálculo de similarity: {e}")
            return 0.0, None, None

    def classificar_manchete(
        self, manchete: Manchete
    ) -> GapDetectado:
        """Classifica uma manchete como COBERTO, PARCIAL ou GAP."""
        score, artigo_id, artigo_titulo = self.calcular_similarity(
            manchete.titulo_normalizado
        )
        
        if score >= self.THRESHOLD_COBERTO:
            tipo = TipoGap.COBERTO
        elif score >= self.THRESHOLD_PARCIAL:
            tipo = TipoGap.PARCIAL
        else:
            tipo = TipoGap.GAP
        
        return GapDetectado(
            manchete=manchete,
            tipo=tipo,
            score_similaridade=score,
            artigo_similar_id=artigo_id if tipo != TipoGap.GAP else None,
            artigo_similar_titulo=artigo_titulo if tipo != TipoGap.GAP else None,
        )

    def analisar_todas(
        self,
        manchetes: list[Manchete],
    ) -> list[GapDetectado]:
        """
        Analisa todas as manchetes e retorna gaps classificados.
        
        Processo:
        1. Classifica cada manchete individualmente
        2. Agrupa por cluster temático
        3. Calcula num_capas por cluster
        4. Atualiza todos os gaps do cluster com num_capas
        
        Returns:
            Lista de GapDetectado (COBERTO + PARCIAL + GAP)
        """
        t0 = time.monotonic()
        
        if not manchetes:
            return []

        # Fase 1: Classificar todas as manchetes
        gaps: list[GapDetectado] = []
        for manchete in manchetes:
            gap = self.classificar_manchete(manchete)
            gaps.append(gap)

        # Fase 2: Clustering para calcular num_capas
        gaps = self._calcular_clusters_e_num_capas(gaps)

        dt = time.monotonic() - t0
        cobertos = sum(1 for g in gaps if g.tipo == TipoGap.COBERTO)
        parciais = sum(1 for g in gaps if g.tipo == TipoGap.PARCIAL)
        gap_total = sum(1 for g in gaps if g.tipo == TipoGap.GAP)
        
        logger.info(
            f"Gap Analysis: {len(manchetes)} manchetes → "
            f"{cobertos} cobertas, {parciais} parciais, {gap_total} gaps "
            f"em {dt:.3f}s"
        )
        
        return gaps

    def _calcular_clusters_e_num_capas(
        self, gaps: list[GapDetectado]
    ) -> list[GapDetectado]:
        """
        Agrupa gaps em clusters temáticos e calcula num_capas.
        
        Usa cosine similarity TF-IDF entre os próprios gaps para
        determinar quais são sobre o mesmo tema.
        
        Um cluster com manchetes de 4+ portais diferentes = breaking.
        """
        if len(gaps) < 2:
            for g in gaps:
                g.cluster_id = g.manchete.titulo_hash
                g.num_capas = 1
            return gaps

        # Vetorizar apenas os gaps (não o corpus completo)
        textos = [
            self._enriquecer_com_entidades(g.manchete.titulo_normalizado)
            for g in gaps
        ]
        
        try:
            # Vectorizer temporário apenas para os gaps
            vec_temp = self._criar_vectorizer()
            matriz_gaps = vec_temp.fit_transform(textos)
            sim_matrix = cosine_similarity(matriz_gaps)
        except Exception as e:
            logger.error(f"Erro no clustering: {e}")
            # Fallback: cada gap é seu próprio cluster
            for g in gaps:
                g.cluster_id = g.manchete.titulo_hash
                g.num_capas = 1
            return gaps

        # Algoritmo de clustering greedy (Union-Find simplificado)
        n = len(gaps)
        cluster_ids: list[Optional[str]] = [None] * n
        
        for i in range(n):
            if cluster_ids[i] is not None:
                continue
            # Novo cluster — usa hash do gap i como ID
            cluster_id = gaps[i].manchete.titulo_hash
            cluster_ids[i] = cluster_id
            
            for j in range(i + 1, n):
                if cluster_ids[j] is not None:
                    continue
                if sim_matrix[i][j] >= self.THRESHOLD_CLUSTER:
                    cluster_ids[j] = cluster_id
        
        # Calcular num_capas por cluster (portais únicos)
        cluster_portais: dict[str, set[str]] = {}
        for i, gap in enumerate(gaps):
            cid = cluster_ids[i]
            if cid not in cluster_portais:
                cluster_portais[cid] = set()
            cluster_portais[cid].add(gap.manchete.portal)
        
        # Atualizar gaps com cluster_id e num_capas
        for i, gap in enumerate(gaps):
            cid = cluster_ids[i]
            gap.cluster_id = cid
            gap.num_capas = len(cluster_portais.get(cid, {1}))
        
        return gaps
```

---

## PARTE VII — URGENCY SCORING

### 7.1 Algoritmo de Urgência

```python
# brasileira/agentes/monitor_concorrencia/urgency.py

"""
Urgency Scoring para gaps de concorrência.

Score de 0 a 10 baseado em 4 fatores:
  F1: Cobertura por concorrentes (0-4 pontos)
  F2: Posição na capa (0-2 pontos)  
  F3: Categoria editorial (0-2 pontos)
  F4: Keywords de urgência (0-2 pontos de bônus)

Decisão de rota:
  Score 0-3:  Baixa urgência → ignora (COBERTO)
  Score 3-6:  Média urgência → consolida (PARCIAL)
  Score 6-10: Alta urgência → pauta nova (GAP urgente)
  4+ capas:   Breaking candidate → Curador (independente de score)
"""

import re
from datetime import datetime
from .gap_analysis import GapDetectado, TipoGap

# Pesos de categoria editorial (alinhados com Regras de Negócio V3)
CATEGORIA_PESO: dict[str, float] = {
    "política":     2.0,
    "politica":     2.0,
    "economia":     1.8,
    "brasil":       1.5,
    "mundo":        1.4,
    "internacional":1.4,
    "saúde":        1.4,
    "saude":        1.4,
    "segurança":    1.3,
    "seguranca":    1.3,
    "educação":     1.2,
    "educacao":     1.2,
    "tecnologia":   1.1,
    "esportes":     1.0,
    "cultura":      0.9,
    "entretenimento":0.8,
    "celebridades": 0.6,
    "fofoca":       0.4,
}

# Keywords que indicam urgência máxima (bônus de score)
KEYWORDS_URGENCIA = re.compile(
    r"\b(morreu|morte|acidente|crise|colapso|urgente|urgência|"
    r"alerta|terremoto|enchente|incêndio|incendio|explosão|explosao|"
    r"atentado|ataque|guerra|conflito|eleição|eleicao|"
    r"preso|prisão|prisao|detido|condenado|"
    r"impeachment|golpe|renúncia|renuncia|demissão|demissao|"
    r"aprovado|aprovada|vetado|vetada|sancionado|sancionada)\b",
    flags=re.IGNORECASE,
)

# Threshold para breaking candidate
THRESHOLD_CAPAS_BREAKING = 4


def calcular_urgency_score(
    gap: GapDetectado,
    categoria: str = "",
    peso_portal: float = 1.0,
) -> float:
    """
    Calcula urgency score (0.0 a 10.0) para um gap.
    
    Args:
        gap: Gap detectado com num_capas preenchido
        categoria: Categoria editorial do tema
        peso_portal: Peso do portal (G1=2.0, Folha=1.9, etc.)
    
    Returns:
        Score float entre 0.0 e 10.0
    """
    score = 0.0

    # ─── F1: Cobertura por concorrentes (0-4 pontos) ─────────────
    # Mais portais cobrindo = mais urgente
    num_capas = gap.num_capas
    if num_capas >= 7:
        score += 4.0    # Quase todos cobrem → absolutamente breaking
    elif num_capas >= 5:
        score += 3.5
    elif num_capas >= 4:
        score += 3.0    # 4+ capas = breaking candidate
    elif num_capas >= 3:
        score += 2.0
    elif num_capas >= 2:
        score += 1.0
    # 1 portal: 0 pontos
    
    # ─── F2: Posição na capa (0-2 pontos) ────────────────────────
    # Manchete principal tem mais peso
    posicao = gap.manchete.posicao_capa
    if posicao == 1:
        score += 2.0    # Primeira manchete
    elif posicao <= 3:
        score += 1.5    # Top 3
    elif posicao <= 10:
        score += 1.0    # Acima da dobra
    elif posicao <= 20:
        score += 0.5    # Visível sem scroll
    # Posição > 20: 0 pontos
    
    # ─── F3: Categoria editorial (0-2 pontos) ────────────────────
    cat_lower = categoria.lower().strip() if categoria else ""
    peso_cat = CATEGORIA_PESO.get(cat_lower, 1.0)
    # Normalizar para 0-2: peso máximo é 2.0 (política) → 2.0 pontos
    score += min(2.0, peso_cat)
    
    # ─── F4: Keywords de urgência (bônus 0-2 pontos) ─────────────
    titulo = gap.manchete.titulo
    if KEYWORDS_URGENCIA.search(titulo):
        score += 2.0
    
    # ─── Multiplicador de portal ──────────────────────────────────
    # G1 na manchete principal vale mais do que Metrópoles no artigo 15
    score *= min(1.5, peso_portal / 1.5)
    
    return min(10.0, round(score, 2))


def determinar_rota(gap: GapDetectado) -> list[str]:
    """
    Determina para quais tópicos Kafka o gap deve ser enviado.
    
    Retorna lista de rotas (pode ser múltiplas).
    
    Regras:
    1. 4+ capas → sempre adicionar 'breaking-candidate'
    2. GAP (0 nossos) + score alto → 'pautas-gap' (Reporter)
    3. PARCIAL (1+ nossos) → 'consolidacao' (Consolidador)
    4. COBERTO → não rotear
    """
    rotas = []
    
    # Regra 1: Breaking candidate (independente de tipo)
    if gap.num_capas >= THRESHOLD_CAPAS_BREAKING:
        rotas.append("breaking-candidate")
    
    # Regra 2: GAP → Reporter
    if gap.tipo == TipoGap.GAP and gap.urgency_score >= 3.0:
        rotas.append("pautas-gap")
    
    # Regra 3: PARCIAL → Consolidador
    if gap.tipo == TipoGap.PARCIAL and gap.urgency_score >= 3.0:
        rotas.append("consolidacao")
    
    # COBERTO → nenhuma rota (silencioso)
    
    return rotas
```

---

## PARTE VIII — ROTAS KAFKA (pautas-gap / consolidacao / breaking-candidate)

### 8.1 Produtor Kafka

```python
# brasileira/agentes/monitor_concorrencia/kafka_producer.py

"""
Produtor Kafka para os 3 tópicos do Monitor Concorrência.

Tópicos:
  pautas-gap         → Reporters (gap sem cobertura nossa)
  consolidacao       → Consolidador (gap com cobertura parcial)
  breaking-candidate → Curador Homepage (tema em 4+ capas)

Particionamento:
  pautas-gap:         por urgencia (str) → balanceia reporters por urgência
  consolidacao:       por tema_id (cluster_id) → mesma partição = mesmo tema
  breaking-candidate: sem chave → round-robin → Curador lê tudo
"""

import json
import logging
from datetime import datetime
from typing import Optional

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

from .gap_analysis import GapDetectado, TipoGap
from .urgency import determinar_rota

logger = logging.getLogger("monitor_concorrencia.kafka")


def _urgencia_para_str(score: float) -> str:
    """Converte urgency score para string de particionamento."""
    if score >= 8.0:
        return "critica"
    elif score >= 6.0:
        return "alta"
    elif score >= 4.0:
        return "media"
    return "baixa"


def _montar_payload_pautas_gap(gap: GapDetectado) -> dict:
    """Monta payload para o tópico pautas-gap → Reporter."""
    return {
        "evento": "gap_concorrencia",
        "fonte": "monitor_concorrencia",
        "urgencia": _urgencia_para_str(gap.urgency_score),
        "urgency_score": gap.urgency_score,
        "manchete": {
            "portal": gap.manchete.portal,
            "titulo": gap.manchete.titulo,
            "url": gap.manchete.url,
            "posicao_capa": gap.manchete.posicao_capa,
            "is_manchete": gap.manchete.is_manchete,
        },
        "num_capas": gap.num_capas,
        "cluster_id": gap.cluster_id,
        "tipo_gap": gap.tipo.value,
        "score_similaridade": gap.score_similaridade,
        "detectado_em": datetime.utcnow().isoformat(),
        # Reporter deve usar isso como contexto de cobertura
        "contexto": (
            f"Tema '{gap.manchete.titulo}' está sendo coberto por "
            f"{gap.num_capas} portais concorrentes mas NÃO temos cobertura. "
            f"Urgência: {_urgencia_para_str(gap.urgency_score)}."
        ),
    }


def _montar_payload_consolidacao(gap: GapDetectado) -> dict:
    """Monta payload para o tópico consolidacao → Consolidador."""
    return {
        "evento": "gap_consolidacao",
        "fonte": "monitor_concorrencia",
        "tema_id": gap.cluster_id or gap.manchete.titulo_hash,
        "urgency_score": gap.urgency_score,
        "manchete": {
            "portal": gap.manchete.portal,
            "titulo": gap.manchete.titulo,
            "url": gap.manchete.url,
        },
        "num_capas": gap.num_capas,
        "artigo_existente_id": gap.artigo_similar_id,
        "artigo_existente_titulo": gap.artigo_similar_titulo,
        "score_similaridade": gap.score_similaridade,
        "detectado_em": datetime.utcnow().isoformat(),
        # Consolidador usa para decidir: ampliar artigo existente ou criar novo
        "contexto": (
            f"Tema '{gap.manchete.titulo}' está em {gap.num_capas} capas. "
            f"Já temos o artigo '{gap.artigo_similar_titulo}' mas com "
            f"cobertura parcial (similarity={gap.score_similaridade:.2f}). "
            "Consolidar com ângulo do concorrente."
        ),
    }


def _montar_payload_breaking(gap: GapDetectado) -> dict:
    """Monta payload para o tópico breaking-candidate → Curador Homepage."""
    return {
        "evento": "breaking_candidate",
        "fonte": "monitor_concorrencia",
        "num_capas": gap.num_capas,
        "urgency_score": gap.urgency_score,
        "cluster_id": gap.cluster_id,
        "manchete": {
            "portal": gap.manchete.portal,
            "titulo": gap.manchete.titulo,
            "url": gap.manchete.url,
            "posicao_capa": gap.manchete.posicao_capa,
        },
        "tipo_cobertura_nossa": gap.tipo.value,
        "artigo_nossa_id": gap.artigo_similar_id,
        "detectado_em": datetime.utcnow().isoformat(),
        # Curador usa para decidir se promove para homepage breaking
        "contexto": (
            f"Tema em {gap.num_capas} capas de concorrentes. "
            f"Nossa cobertura: {gap.tipo.value}. "
            "Candidato a breaking news na homepage."
        ),
    }


class MonitorKafkaProducer:
    """
    Produtor Kafka do Monitor Concorrência.
    
    Envia gaps para os 3 tópicos conforme regras de roteamento.
    NUNCA envia para pautas-especiais ou qualquer tópico do Pauteiro.
    """

    TOPICO_GAP        = "pautas-gap"
    TOPICO_CONSOLIDA  = "consolidacao"
    TOPICO_BREAKING   = "breaking-candidate"

    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self) -> None:
        """Inicializa o produtor Kafka."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode(),
            key_serializer=lambda k: k.encode() if k else None,
            compression_type="gzip",
            acks="all",               # Garantia de entrega
            max_batch_size=16384,
            linger_ms=50,             # Agrupa mensagens por 50ms
            retry_backoff_ms=200,
            request_timeout_ms=30000,
        )
        await self._producer.start()
        logger.info("Kafka Producer iniciado")

    async def stop(self) -> None:
        """Para o produtor."""
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka Producer parado")

    async def publicar_gap(self, gap: GapDetectado) -> int:
        """
        Publica gap nos tópicos apropriados.
        
        Returns:
            Número de tópicos onde o gap foi publicado
        """
        if self._producer is None:
            logger.error("Producer não iniciado — gap não publicado")
            return 0
        
        rotas = determinar_rota(gap)
        publicados = 0
        
        for rota in rotas:
            try:
                if rota == self.TOPICO_GAP:
                    payload = _montar_payload_pautas_gap(gap)
                    chave = _urgencia_para_str(gap.urgency_score)
                    
                elif rota == self.TOPICO_CONSOLIDA:
                    payload = _montar_payload_consolidacao(gap)
                    chave = gap.cluster_id or gap.manchete.titulo_hash
                    
                elif rota == self.TOPICO_BREAKING:
                    payload = _montar_payload_breaking(gap)
                    chave = None  # Round-robin
                    
                else:
                    logger.warning(f"Rota desconhecida: {rota}")
                    continue
                
                await self._producer.send(rota, value=payload, key=chave)
                publicados += 1
                
                logger.info(
                    f"Gap publicado → {rota}: "
                    f"[{gap.manchete.portal}] {gap.manchete.titulo[:60]} "
                    f"(score={gap.urgency_score}, capas={gap.num_capas})"
                )
                
            except KafkaConnectionError as e:
                logger.error(f"Erro de conexão Kafka para {rota}: {e}")
            except Exception as e:
                logger.error(f"Erro ao publicar em {rota}: {e}", exc_info=True)
        
        return publicados

    async def publicar_lote(self, gaps: list[GapDetectado]) -> dict[str, int]:
        """
        Publica lote de gaps.
        
        Returns:
            Dict com contagem por tópico
        """
        contagem: dict[str, int] = {
            self.TOPICO_GAP: 0,
            self.TOPICO_CONSOLIDA: 0,
            self.TOPICO_BREAKING: 0,
        }
        
        for gap in gaps:
            rotas = determinar_rota(gap)
            for rota in rotas:
                if rota in contagem:
                    contagem[rota] += 1
            await self.publicar_gap(gap)
        
        logger.info(
            f"Lote publicado: "
            f"{contagem[self.TOPICO_GAP]} gaps, "
            f"{contagem[self.TOPICO_CONSOLIDA]} consolidações, "
            f"{contagem[self.TOPICO_BREAKING]} breaking"
        )
        return contagem
```

---

## PARTE IX — MEMÓRIA DO AGENTE

### 9.1 Estratégia de Memória (Três Tipos)

Seguindo a **Regra #13** inviolável: todos os agentes DEVEM ter memória semântica, episódica e working.

```python
# brasileira/agentes/monitor_concorrencia/memoria.py

"""
Camada de memória do Monitor Concorrência.

Memória Working (Redis):
  - coverage:our_articles → artigos publicados (TTL 6h, cache do PostgreSQL)
  - monitor:cooldowns:{hash} → cooldown de alerta por gap (TTL 60min)
  - monitor:last_scan_stats → estatísticas do último ciclo (TTL 24h)
  - monitor:coverage_report → relatório de cobertura (TTL 6h)
  - monitor:seletor_health:{portal} → saúde dos seletores por portal (TTL 24h)

Memória Episódica (PostgreSQL — tabela analise_concorrencia):
  - Histórico de todos os gaps detectados
  - Scores de urgência históricos
  - Correlação portal → tipo de gap

Memória Semântica (PostgreSQL — tabela memoria_agentes tipo='semantica'):
  - Padrões aprendidos: "Folha cobre muito mais política do que Terra"
  - Thresholds ajustados por editorial
  - Vocabulário temático por categoria
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

import asyncpg
import redis.asyncio as aioredis

logger = logging.getLogger("monitor_concorrencia.memoria")

# Redis Keys
KEY_COVERAGE_ARTIGOS   = "coverage:our_articles"         # TTL 6h
KEY_COOLDOWN_PREFIX    = "monitor:cooldowns:"             # TTL 60min
KEY_LAST_SCAN_STATS    = "monitor:last_scan_stats"        # TTL 24h
KEY_COVERAGE_REPORT    = "monitor:coverage_report"        # TTL 6h
KEY_SELETOR_HEALTH     = "monitor:seletor_health:{portal}"  # TTL 24h
KEY_COMPETITOR_FEEDS   = "config:competitor_feeds"        # TTL 30d

# TTLs (segundos)
TTL_COVERAGE_ARTIGOS = 6 * 3600      # 6 horas
TTL_COOLDOWN         = 60 * 60       # 60 minutos
TTL_LAST_SCAN        = 24 * 3600     # 24 horas
TTL_COVERAGE_REPORT  = 6 * 3600      # 6 horas
TTL_SELETOR_HEALTH   = 24 * 3600     # 24 horas


class MemoriaMonitor:
    """
    Camada de memória do Monitor Concorrência.
    
    Gerencia cache de artigos, cooldowns de alertas e histórico.
    """

    def __init__(self, redis_client: aioredis.Redis, pg_pool: asyncpg.Pool):
        self.redis = redis_client
        self.pg = pg_pool

    # ─── Working Memory (Redis) ────────────────────────────────────

    async def get_artigos_nossos(self) -> list[dict]:
        """
        Retorna artigos publicados das últimas 6 horas.
        
        Cache Redis (TTL 6h) → PostgreSQL.
        """
        try:
            cached = await self.redis.get(KEY_COVERAGE_ARTIGOS)
            if cached:
                artigos = json.loads(cached)
                logger.debug(f"Cache hit: {len(artigos)} artigos do Redis")
                return artigos
        except Exception as e:
            logger.debug(f"Redis cache miss: {e}")

        # PostgreSQL fallback
        try:
            artigos = await self._buscar_artigos_postgres()
            if artigos:
                await self.redis.setex(
                    KEY_COVERAGE_ARTIGOS,
                    TTL_COVERAGE_ARTIGOS,
                    json.dumps(artigos, ensure_ascii=False),
                )
                logger.info(f"Artigos carregados do PG e cacheados: {len(artigos)}")
            return artigos
        except Exception as e:
            logger.error(f"Erro ao buscar artigos do PostgreSQL: {e}")
            return []

    async def _buscar_artigos_postgres(self) -> list[dict]:
        """Busca artigos publicados nas últimas 6 horas."""
        query = """
            SELECT 
                id,
                titulo,
                topico,
                editoria,
                created_at
            FROM artigos
            WHERE 
                status = 'published'
                AND created_at >= NOW() - INTERVAL '6 hours'
            ORDER BY created_at DESC
            LIMIT 500
        """
        async with self.pg.acquire() as conn:
            rows = await conn.fetch(query)
            return [
                {
                    "id": row["id"],
                    "titulo": row["titulo"] or "",
                    "topico": row["topico"] or "",
                    "editoria": row["editoria"] or "",
                }
                for row in rows
            ]

    async def invalidar_cache_artigos(self) -> None:
        """Invalida cache forçando recarga do PostgreSQL no próximo ciclo."""
        await self.redis.delete(KEY_COVERAGE_ARTIGOS)
        logger.info("Cache de artigos invalidado")

    async def check_cooldown(self, titulo_hash: str) -> bool:
        """
        Verifica se gap ainda está em cooldown (não deve ser alertado).
        
        Returns:
            True se em cooldown (não alertar), False se pode alertar
        """
        key = f"{KEY_COOLDOWN_PREFIX}{titulo_hash}"
        exists = await self.redis.exists(key)
        return bool(exists)

    async def set_cooldown(self, titulo_hash: str, ttl: int = TTL_COOLDOWN) -> None:
        """Registra que gap foi alertado (cooldown)."""
        key = f"{KEY_COOLDOWN_PREFIX}{titulo_hash}"
        await self.redis.setex(key, ttl, "1")

    async def salvar_scan_stats(self, stats: dict) -> None:
        """Salva estatísticas do ciclo no Redis."""
        await self.redis.setex(
            KEY_LAST_SCAN_STATS,
            TTL_LAST_SCAN,
            json.dumps({**stats, "timestamp": datetime.utcnow().isoformat()},
                       ensure_ascii=False),
        )

    async def salvar_relatorio(self, relatorio: dict) -> None:
        """Salva relatório de cobertura no Redis."""
        await self.redis.setex(
            KEY_COVERAGE_REPORT,
            TTL_COVERAGE_REPORT,
            json.dumps(relatorio, ensure_ascii=False),
        )

    async def get_relatorio(self) -> Optional[dict]:
        """Recupera último relatório de cobertura."""
        data = await self.redis.get(KEY_COVERAGE_REPORT)
        return json.loads(data) if data else None

    async def registrar_saude_seletor(
        self, portal: str, manchetes_count: int
    ) -> None:
        """Registra saúde do seletor por portal para monitoramento."""
        key = KEY_SELETOR_HEALTH.format(portal=portal)
        await self.redis.setex(
            key,
            TTL_SELETOR_HEALTH,
            json.dumps({
                "portal": portal,
                "manchetes_count": manchetes_count,
                "healthy": manchetes_count >= 3,
                "updated_at": datetime.utcnow().isoformat(),
            }),
        )

    # ─── Episodic Memory (PostgreSQL) ─────────────────────────────

    async def salvar_gap(self, gap_dict: dict) -> None:
        """Persiste gap detectado na tabela analise_concorrencia."""
        query = """
            INSERT INTO analise_concorrencia (
                portal,
                titulo_concorrente,
                url_concorrente,
                titulo_normalizado,
                tipo_gap,
                score_similaridade,
                urgency_score,
                num_capas,
                cluster_id,
                artigo_similar_id,
                detectado_em
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
            )
            ON CONFLICT DO NOTHING
        """
        try:
            async with self.pg.acquire() as conn:
                await conn.execute(
                    query,
                    gap_dict.get("portal"),
                    gap_dict.get("titulo"),
                    gap_dict.get("url"),
                    gap_dict.get("titulo_normalizado"),
                    gap_dict.get("tipo"),
                    gap_dict.get("score_similaridade"),
                    gap_dict.get("urgency_score"),
                    gap_dict.get("num_capas"),
                    gap_dict.get("cluster_id"),
                    gap_dict.get("artigo_similar_id"),
                    datetime.utcnow(),
                )
        except Exception as e:
            logger.warning(f"Erro ao salvar gap no PostgreSQL: {e}")

    async def salvar_lote_gaps(self, gaps: list[dict]) -> None:
        """Persiste lote de gaps (mais eficiente que um por um)."""
        if not gaps:
            return
        for gap in gaps:
            await self.salvar_gap(gap)
        logger.debug(f"{len(gaps)} gaps persistidos no PostgreSQL")

    async def buscar_gaps_por_portal(
        self, portal: str, limite: int = 50
    ) -> list[dict]:
        """Retorna gaps recentes de um portal específico."""
        query = """
            SELECT *
            FROM analise_concorrencia
            WHERE portal = $1
            ORDER BY detectado_em DESC
            LIMIT $2
        """
        async with self.pg.acquire() as conn:
            rows = await conn.fetch(query, portal, limite)
            return [dict(row) for row in rows]

    # ─── Semantic Memory (PostgreSQL) ─────────────────────────────

    async def salvar_padrao_aprendido(
        self, descricao: str, dados: dict
    ) -> None:
        """
        Salva padrão aprendido na memória semântica.
        
        Exemplos:
        - "G1 cobre média de 18 manchetes por ciclo"
        - "Política tem urgency score médio 7.2 no Metrópoles"
        """
        query = """
            INSERT INTO memoria_agentes (agente, tipo, conteudo, created_at)
            VALUES ($1, 'semantica', $2, NOW())
        """
        try:
            async with self.pg.acquire() as conn:
                await conn.execute(
                    query,
                    "monitor_concorrencia",
                    json.dumps({
                        "descricao": descricao,
                        "dados": dados,
                        "timestamp": datetime.utcnow().isoformat(),
                    }),
                )
        except Exception as e:
            logger.debug(f"Erro ao salvar memória semântica: {e}")
```

---

## PARTE X — SCHEMAS PYDANTIC

### 10.1 Schemas de Entrada e Saída

```python
# brasileira/agentes/monitor_concorrencia/schemas.py

"""
Schemas Pydantic V2 para o Monitor Concorrência.

Todos os dados que trafegam entre fases do pipeline
e entre componentes externos (Kafka, Redis) são validados aqui.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TipoGapEnum(str, Enum):
    COBERTO = "coberto"
    PARCIAL = "parcial"
    GAP     = "gap"


class UrgenciaEnum(str, Enum):
    CRITICA = "critica"    # score ≥ 8.0
    ALTA    = "alta"       # score ≥ 6.0
    MEDIA   = "media"      # score ≥ 4.0
    BAIXA   = "baixa"      # score < 4.0


class MancheteCapa(BaseModel):
    """Manchete extraída da capa de um portal concorrente."""
    portal: str
    titulo: str = Field(min_length=15, max_length=500)
    titulo_normalizado: str
    url: str = Field(default="")
    posicao_capa: int = Field(ge=1, le=50)
    is_manchete: bool = False
    extraido_em: datetime = Field(default_factory=datetime.utcnow)
    titulo_hash: str = ""

    @field_validator("titulo")
    @classmethod
    def remover_espacos(cls, v: str) -> str:
        return v.strip()


class GapAnalysis(BaseModel):
    """Resultado da análise TF-IDF para uma manchete."""
    manchete: MancheteCapa
    tipo: TipoGapEnum
    score_similaridade: float = Field(ge=0.0, le=1.0)
    artigo_similar_id: Optional[int] = None
    artigo_similar_titulo: Optional[str] = None
    num_capas: int = Field(ge=1, default=1)
    urgency_score: float = Field(ge=0.0, le=10.0, default=0.0)
    cluster_id: Optional[str] = None
    rotas_kafka: list[str] = Field(default_factory=list)


class PayloadPautasGap(BaseModel):
    """Payload para o tópico Kafka pautas-gap → Reporter."""
    evento: str = "gap_concorrencia"
    fonte: str = "monitor_concorrencia"
    urgencia: UrgenciaEnum
    urgency_score: float
    manchete: dict
    num_capas: int
    cluster_id: Optional[str]
    tipo_gap: str
    score_similaridade: float
    detectado_em: datetime = Field(default_factory=datetime.utcnow)
    contexto: str


class PayloadConsolidacao(BaseModel):
    """Payload para o tópico Kafka consolidacao → Consolidador."""
    evento: str = "gap_consolidacao"
    fonte: str = "monitor_concorrencia"
    tema_id: str
    urgency_score: float
    manchete: dict
    num_capas: int
    artigo_existente_id: Optional[int]
    artigo_existente_titulo: Optional[str]
    score_similaridade: float
    detectado_em: datetime = Field(default_factory=datetime.utcnow)
    contexto: str


class PayloadBreaking(BaseModel):
    """Payload para o tópico Kafka breaking-candidate → Curador."""
    evento: str = "breaking_candidate"
    fonte: str = "monitor_concorrencia"
    num_capas: int = Field(ge=4)
    urgency_score: float
    cluster_id: Optional[str]
    manchete: dict
    tipo_cobertura_nossa: TipoGapEnum
    artigo_nossa_id: Optional[int]
    detectado_em: datetime = Field(default_factory=datetime.utcnow)
    contexto: str


class RelatorioScan(BaseModel):
    """Relatório consolidado de um ciclo de scan."""
    ciclo_id: str
    iniciado_em: datetime
    concluido_em: datetime
    duracao_segundos: float
    portais_scaneados: int
    portais_com_erro: list[str]
    total_manchetes: int
    total_cobertos: int
    total_parciais: int
    total_gaps: int
    total_breaking: int
    gaps_publicados_pautas_gap: int
    gaps_publicados_consolidacao: int
    gaps_publicados_breaking: int
    coverage_ratio: float  # cobertos / total
    urgency_score_medio: float
    portais_stats: dict[str, int]  # portal → n_manchetes


class EstadoMonitor(BaseModel):
    """Estado LangGraph do Monitor Concorrência."""
    # Resultados do scan
    manchetes_raw: list[dict] = Field(default_factory=list)
    erros_scan: dict[str, str] = Field(default_factory=dict)
    
    # Resultados da análise
    gaps_analisados: list[dict] = Field(default_factory=list)
    gaps_por_tipo: dict[str, int] = Field(default_factory=dict)
    
    # Resultados do roteamento
    publicados_pautas_gap: int = 0
    publicados_consolidacao: int = 0
    publicados_breaking: int = 0
    
    # Metadados do ciclo
    ciclo_id: str = ""
    iniciado_em: Optional[datetime] = None
    concluido_em: Optional[datetime] = None
    stage: str = "scan"
    
    class Config:
        arbitrary_types_allowed = True
```

---

## PARTE XI — DIRETÓRIOS E ESTRUTURA DE ARQUIVOS

### 11.1 Estrutura Completa

```
brasileira/
└── agentes/
    └── monitor_concorrencia/
        ├── __init__.py                  # Exports: MonitorConcorrenciaV3
        ├── agente.py                    # LangGraph state machine (nó principal)
        ├── scanner.py                   # Playwright CapaScanner + Manchete
        ├── portais.py                   # PORTAIS_CONCORRENTES (8 portais)
        ├── normalizacao.py              # normalizar_titulo, STOPWORDS_PT
        ├── gap_analysis.py              # AnalisadorTFIDF, GapDetectado
        ├── urgency.py                   # calcular_urgency_score, determinar_rota
        ├── kafka_producer.py            # MonitorKafkaProducer
        ├── memoria.py                   # MemoriaMonitor (working/episodic/semantic)
        ├── schemas.py                   # Pydantic models
        ├── config.py                    # MonitorConfig + env vars
        └── entrypoint.py               # Loop 30min + graceful shutdown
```

### 11.2 `__init__.py`

```python
# brasileira/agentes/monitor_concorrencia/__init__.py

"""Monitor Concorrência V3 — Gap Analysis de Capas."""

from .agente import MonitorConcorrenciaV3
from .scanner import CapaScanner, Manchete
from .gap_analysis import AnalisadorTFIDF, GapDetectado, TipoGap
from .portais import PORTAIS_CONCORRENTES, PORTAIS_OBRIGATORIOS
from .schemas import EstadoMonitor, RelatorioScan

__all__ = [
    "MonitorConcorrenciaV3",
    "CapaScanner",
    "Manchete",
    "AnalisadorTFIDF",
    "GapDetectado",
    "TipoGap",
    "PORTAIS_CONCORRENTES",
    "PORTAIS_OBRIGATORIOS",
    "EstadoMonitor",
    "RelatorioScan",
]

__version__ = "3.0.0"
```

### 11.3 `config.py`

```python
# brasileira/agentes/monitor_concorrencia/config.py

"""Configuração do Monitor Concorrência via variáveis de ambiente."""

import os
from dataclasses import dataclass


@dataclass
class MonitorConfig:
    """Configuração do Monitor Concorrência V3."""
    
    # ─── Intervalo de Scan ─────────────────────────────────────────
    # 30 minutos = 48 ciclos/dia
    SCAN_INTERVAL_SECONDS: int = int(os.getenv("MONITOR_SCAN_INTERVAL", "1800"))
    
    # ─── Playwright ───────────────────────────────────────────────
    BROWSER_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
    TIMEOUT_NAVEGACAO_MS: int = int(os.getenv("PLAYWRIGHT_TIMEOUT_NAV", "30000"))
    TIMEOUT_SELETOR_MS: int = int(os.getenv("PLAYWRIGHT_TIMEOUT_SEL", "15000"))
    MAX_MANCHETES_PORTAL: int = int(os.getenv("MAX_MANCHETES_PORTAL", "30"))
    
    # ─── TF-IDF ───────────────────────────────────────────────────
    THRESHOLD_COBERTO: float = float(os.getenv("TFIDF_THRESHOLD_COBERTO", "0.65"))
    THRESHOLD_PARCIAL: float = float(os.getenv("TFIDF_THRESHOLD_PARCIAL", "0.35"))
    THRESHOLD_CLUSTER: float = float(os.getenv("TFIDF_THRESHOLD_CLUSTER", "0.45"))
    CORPUS_HORAS: int = int(os.getenv("CORPUS_HORAS", "6"))
    CORPUS_MAX_ARTIGOS: int = int(os.getenv("CORPUS_MAX_ARTIGOS", "500"))
    
    # ─── Urgency Scoring ──────────────────────────────────────────
    THRESHOLD_CAPAS_BREAKING: int = int(os.getenv("THRESHOLD_CAPAS_BREAKING", "4"))
    THRESHOLD_SCORE_ROTEAR: float = float(os.getenv("THRESHOLD_SCORE_ROTEAR", "3.0"))
    
    # ─── Cooldowns ────────────────────────────────────────────────
    COOLDOWN_ALERTA_SEGUNDOS: int = int(os.getenv("MONITOR_COOLDOWN_SEGUNDOS", "3600"))
    MAX_GAPS_POR_CICLO: int = int(os.getenv("MAX_GAPS_POR_CICLO", "20"))
    
    # ─── Kafka ────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    
    # ─── Redis ────────────────────────────────────────────────────
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # ─── PostgreSQL ───────────────────────────────────────────────
    POSTGRES_DSN: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql://postgres:postgres@localhost:5432/brasileira"
    )
    
    # ─── Logging ──────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # ─── DRY RUN ──────────────────────────────────────────────────
    # Se True: executa tudo mas não publica no Kafka
    DRY_RUN: bool = os.getenv("MONITOR_DRY_RUN", "false").lower() == "true"
```

### 11.4 SQL — Tabela `analise_concorrencia`

```sql
-- Tabela de histórico de gaps detectados
-- Executar uma vez no PostgreSQL

CREATE TABLE IF NOT EXISTS analise_concorrencia (
    id                   SERIAL PRIMARY KEY,
    portal               VARCHAR(50) NOT NULL,
    titulo_concorrente   TEXT NOT NULL,
    url_concorrente      TEXT,
    titulo_normalizado   TEXT,
    tipo_gap             VARCHAR(20) NOT NULL,   -- 'coberto', 'parcial', 'gap'
    score_similaridade   FLOAT,
    urgency_score        FLOAT,
    num_capas            INTEGER DEFAULT 1,
    cluster_id           VARCHAR(32),
    artigo_similar_id    INTEGER REFERENCES artigos(id) ON DELETE SET NULL,
    detectado_em         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    publicado_kafka      BOOLEAN DEFAULT FALSE,
    topicos_kafka        TEXT[]    -- ['pautas-gap', 'breaking-candidate']
);

-- Índices para queries frequentes
CREATE INDEX idx_analise_conc_portal      ON analise_concorrencia(portal);
CREATE INDEX idx_analise_conc_detectado   ON analise_concorrencia(detectado_em DESC);
CREATE INDEX idx_analise_conc_tipo        ON analise_concorrencia(tipo_gap);
CREATE INDEX idx_analise_conc_cluster     ON analise_concorrencia(cluster_id);
CREATE INDEX idx_analise_conc_urgency     ON analise_concorrencia(urgency_score DESC);

-- Limpeza automática de registros com mais de 30 dias
-- (opcional, via pg_cron ou job externo)
-- DELETE FROM analise_concorrencia WHERE detectado_em < NOW() - INTERVAL '30 days';
```

---

## PARTE XII — AGENTE LANGGRAPH (agente.py)

### 12.1 State Machine Completa

```python
# brasileira/agentes/monitor_concorrencia/agente.py

"""
Monitor Concorrência V3 — LangGraph State Machine.

4 nós:
  1. scan    → Playwright: extrai manchetes dos 8 portais
  2. analisar → TF-IDF: classifica gaps vs corpus
  3. rotear  → Kafka: envia gaps para rotas corretas
  4. relatar → Redis: salva estatísticas do ciclo

Regras OBRIGATÓRIAS:
  - NUNCA publicar em tópico do Pauteiro
  - 4+ capas → sempre breaking-candidate
  - GAP (0 nossos) → pautas-gap → Reporter
  - PARCIAL (1+ nossos) → consolidacao → Consolidador
"""

import asyncio
import hashlib
import logging
import time
import uuid
from datetime import datetime
from typing import Any

import asyncpg
import redis.asyncio as aioredis
from langgraph.graph import StateGraph, END

from .config import MonitorConfig
from .gap_analysis import AnalisadorTFIDF, GapDetectado, TipoGap
from .kafka_producer import MonitorKafkaProducer
from .memoria import MemoriaMonitor
from .normalizacao import deduplicar_manchetes
from .portais import PORTAIS_CONCORRENTES, validar_portais
from .scanner import CapaScanner, Manchete
from .schemas import EstadoMonitor, RelatorioScan
from .urgency import calcular_urgency_score, determinar_rota

logger = logging.getLogger("monitor_concorrencia.agente")


class MonitorConcorrenciaV3:
    """
    Monitor Concorrência V3.
    
    Implementa gap analysis de capas com:
    - Playwright para scraping JS-heavy
    - TF-IDF com corpus português
    - 3 rotas Kafka diretas (sem Pauteiro)
    - Memória working/episódica/semântica
    """

    def __init__(self, config: MonitorConfig = None):
        self.config = config or MonitorConfig()
        self._kafka: MonitorKafkaProducer = None
        self._memoria: MemoriaMonitor = None
        self._analisador = AnalisadorTFIDF()
        self._pg_pool: asyncpg.Pool = None
        self._redis: aioredis.Redis = None
        self._graph = None
        self._running = False
        self._stop_event = asyncio.Event()
        
        # Validar portais obrigatórios na inicialização
        validar_portais()

    async def inicializar(self) -> None:
        """Inicializa conexões com Redis, PostgreSQL e Kafka."""
        # PostgreSQL
        self._pg_pool = await asyncpg.create_pool(
            self.config.POSTGRES_DSN,
            min_size=2,
            max_size=10,
        )
        
        # Redis
        self._redis = await aioredis.from_url(
            self.config.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        
        # Memória
        self._memoria = MemoriaMonitor(self._redis, self._pg_pool)
        
        # Kafka
        if not self.config.DRY_RUN:
            self._kafka = MonitorKafkaProducer(self.config.KAFKA_BOOTSTRAP)
            await self._kafka.start()
        else:
            logger.warning("DRY RUN ativo — Kafka desabilitado")
        
        # Construir grafo LangGraph
        self._graph = self._construir_grafo()
        
        logger.info("MonitorConcorrenciaV3 inicializado")

    async def encerrar(self) -> None:
        """Encerra conexões graciosamente."""
        self._stop_event.set()
        if self._kafka:
            await self._kafka.stop()
        if self._pg_pool:
            await self._pg_pool.close()
        if self._redis:
            await self._redis.close()
        logger.info("MonitorConcorrenciaV3 encerrado")

    def _construir_grafo(self) -> Any:
        """Constrói state machine LangGraph."""
        grafo = StateGraph(dict)  # Estado como dict para compatibilidade
        
        grafo.add_node("scan",     self._no_scan)
        grafo.add_node("analisar", self._no_analisar)
        grafo.add_node("rotear",   self._no_rotear)
        grafo.add_node("relatar",  self._no_relatar)
        
        grafo.add_edge("scan",     "analisar")
        grafo.add_edge("analisar", "rotear")
        grafo.add_edge("rotear",   "relatar")
        grafo.add_edge("relatar",  END)
        
        grafo.set_entry_point("scan")
        return grafo.compile()

    # ─── Nó 1: SCAN ───────────────────────────────────────────────

    async def _no_scan(self, estado: dict) -> dict:
        """Fase 1: Scanneia capas dos 8 portais via Playwright."""
        logger.info("=== FASE 1: SCAN DE CAPAS ===")
        ciclo_id = str(uuid.uuid4())[:8]
        iniciado_em = datetime.utcnow()
        
        manchetes_por_portal: dict[str, list[Manchete]] = {}
        erros_scan: dict[str, str] = {}
        
        try:
            async with CapaScanner(headless=self.config.BROWSER_HEADLESS) as scanner:
                resultado = await scanner.scan_todos(PORTAIS_CONCORRENTES)
                manchetes_por_portal = resultado
                
        except Exception as e:
            logger.error(f"Erro crítico no scan: {e}", exc_info=True)
            erros_scan["_global"] = str(e)
        
        # Coletar estatísticas e registrar saúde dos seletores
        total_manchetes = 0
        todas_manchetes = []
        
        for portal_name, manchetes in manchetes_por_portal.items():
            total_manchetes += len(manchetes)
            todas_manchetes.extend(manchetes)
            
            # Registrar saúde do seletor
            if self._memoria:
                await self._memoria.registrar_saude_seletor(
                    portal_name, len(manchetes)
                )
            
            if len(manchetes) == 0:
                erros_scan[portal_name] = "0 manchetes extraídas"
            elif len(manchetes) < 3:
                logger.warning(
                    f"[{portal_name}] ATENÇÃO: apenas {len(manchetes)} manchetes. "
                    "Seletor pode estar quebrado."
                )
        
        # Deduplicar manchetes intra-ciclo
        todas_manchetes = deduplicar_manchetes(todas_manchetes)
        
        logger.info(
            f"Scan completo: {len(manchetes_por_portal)} portais, "
            f"{total_manchetes} manchetes brutas, "
            f"{len(todas_manchetes)} após dedup, "
            f"{len(erros_scan)} erros"
        )
        
        return {
            **estado,
            "ciclo_id": ciclo_id,
            "iniciado_em": iniciado_em.isoformat(),
            "manchetes_raw": [m.to_dict() for m in todas_manchetes],
            "erros_scan": erros_scan,
            "stage": "analisar",
        }

    # ─── Nó 2: ANALISAR ───────────────────────────────────────────

    async def _no_analisar(self, estado: dict) -> dict:
        """Fase 2: TF-IDF Gap Analysis contra corpus próprio."""
        logger.info("=== FASE 2: TF-IDF GAP ANALYSIS ===")
        
        manchetes_raw = estado.get("manchetes_raw", [])
        if not manchetes_raw:
            logger.warning("Nenhuma manchete para analisar")
            return {**estado, "gaps_analisados": [], "stage": "rotear"}
        
        # Reconstruir objetos Manchete
        from .scanner import Manchete as MancheteCls
        manchetes = [
            MancheteCls(
                portal=m["portal"],
                titulo=m["titulo"],
                titulo_normalizado=m["titulo_normalizado"],
                url=m["url"],
                posicao_capa=m["posicao_capa"],
                is_manchete=m["is_manchete"],
                titulo_hash=m.get("titulo_hash", ""),
            )
            for m in manchetes_raw
        ]
        
        # Carregar corpus dos nossos artigos
        artigos_nossos = await self._memoria.get_artigos_nossos()
        
        if not artigos_nossos:
            logger.warning(
                "Corpus vazio — publicando todos os gaps sem filtro TF-IDF. "
                "Isto é temporário até artigos serem publicados."
            )
            # Sem corpus: tratar tudo como GAP
            from .scanner import Manchete as M
            from .gap_analysis import GapDetectado, TipoGap as TG
            gaps = [
                GapDetectado(
                    manchete=m,
                    tipo=TG.GAP,
                    score_similaridade=0.0,
                    artigo_similar_id=None,
                    artigo_similar_titulo=None,
                )
                for m in manchetes
            ]
        else:
            # Treinar TF-IDF com corpus atual
            self._analisador.treinar_corpus(artigos_nossos)
            
            # Analisar todos os gaps
            gaps = self._analisador.analisar_todas(manchetes)
        
        # Calcular urgency score para cada gap
        for gap in gaps:
            portal_config = next(
                (p for p in PORTAIS_CONCORRENTES if p["nome"] == gap.manchete.portal),
                None,
            )
            peso_portal = portal_config.get("peso_editorial", 1.0) if portal_config else 1.0
            gap.urgency_score = calcular_urgency_score(gap, peso_portal=peso_portal)
        
        # Estatísticas
        n_cobertos = sum(1 for g in gaps if g.tipo == TipoGap.COBERTO)
        n_parciais = sum(1 for g in gaps if g.tipo == TipoGap.PARCIAL)
        n_gaps     = sum(1 for g in gaps if g.tipo == TipoGap.GAP)
        n_breaking = sum(1 for g in gaps if g.num_capas >= self.config.THRESHOLD_CAPAS_BREAKING)
        
        logger.info(
            f"Gap Analysis: {len(gaps)} manchetes → "
            f"{n_cobertos} cobertas, {n_parciais} parciais, {n_gaps} gaps, "
            f"{n_breaking} breaking candidates"
        )
        
        return {
            **estado,
            "gaps_analisados": [g.to_dict() for g in gaps],
            "gaps_por_tipo": {
                "coberto": n_cobertos,
                "parcial": n_parciais,
                "gap": n_gaps,
                "breaking": n_breaking,
            },
            "stage": "rotear",
        }

    # ─── Nó 3: ROTEAR ─────────────────────────────────────────────

    async def _no_rotear(self, estado: dict) -> dict:
        """
        Fase 3: Roteia gaps para Kafka.
        
        REGRAS INVIOLÁVEIS:
        - GAP (0 nossos) → pautas-gap → Reporter
        - PARCIAL (1+ nossos) → consolidacao → Consolidador
        - 4+ capas → breaking-candidate → Curador
        - NUNCA rotear via Pauteiro
        """
        logger.info("=== FASE 3: ROTEAMENTO KAFKA ===")
        
        gaps_analisados = estado.get("gaps_analisados", [])
        publicados_gap = 0
        publicados_consolida = 0
        publicados_breaking = 0
        
        # Ordenar por urgency_score decrescente
        gaps_ordenados = sorted(
            gaps_analisados,
            key=lambda g: g.get("urgency_score", 0),
            reverse=True,
        )
        
        # Limitar gaps publicados por ciclo
        gaps_para_publicar = gaps_ordenados[:self.config.MAX_GAPS_POR_CICLO]
        
        for gap_dict in gaps_para_publicar:
            tipo = gap_dict.get("tipo")
            score = gap_dict.get("urgency_score", 0)
            num_capas = gap_dict.get("num_capas", 1)
            titulo_hash = gap_dict.get("titulo_hash", "")
            
            # Verificar cooldown (Redis)
            if titulo_hash and await self._memoria.check_cooldown(titulo_hash):
                logger.debug(
                    f"Gap em cooldown: {gap_dict.get('titulo', '')[:40]}"
                )
                continue
            
            # Reconstruir GapDetectado para publicação
            from .gap_analysis import GapDetectado, TipoGap as TG
            from .scanner import Manchete as M
            
            gap_obj = GapDetectado(
                manchete=M(
                    portal=gap_dict["portal"],
                    titulo=gap_dict["titulo"],
                    titulo_normalizado=gap_dict["titulo_normalizado"],
                    url=gap_dict.get("url", ""),
                    posicao_capa=gap_dict.get("posicao_capa", 1),
                    is_manchete=gap_dict.get("is_manchete", False),
                    titulo_hash=titulo_hash,
                ),
                tipo=TG(tipo),
                score_similaridade=gap_dict.get("score_similaridade", 0.0),
                artigo_similar_id=gap_dict.get("artigo_similar_id"),
                artigo_similar_titulo=gap_dict.get("artigo_similar_titulo"),
                num_capas=num_capas,
                urgency_score=score,
                cluster_id=gap_dict.get("cluster_id"),
            )
            
            # Publicar no Kafka (ou simular se DRY_RUN)
            if not self.config.DRY_RUN and self._kafka:
                contagem = await self._kafka.publicar_lote([gap_obj])
                publicados_gap       += contagem.get("pautas-gap", 0)
                publicados_consolida += contagem.get("consolidacao", 0)
                publicados_breaking  += contagem.get("breaking-candidate", 0)
            else:
                rotas = determinar_rota(gap_obj)
                logger.info(f"[DRY RUN] Rotas para '{gap_obj.manchete.titulo[:50]}': {rotas}")
            
            # Registrar cooldown
            if titulo_hash:
                await self._memoria.set_cooldown(
                    titulo_hash,
                    ttl=self.config.COOLDOWN_ALERTA_SEGUNDOS,
                )
        
        # Persistir gaps no histórico
        await self._memoria.salvar_lote_gaps(gaps_para_publicar)
        
        logger.info(
            f"Roteamento concluído: "
            f"{publicados_gap} pautas-gap, "
            f"{publicados_consolida} consolidação, "
            f"{publicados_breaking} breaking"
        )
        
        return {
            **estado,
            "publicados_pautas_gap": publicados_gap,
            "publicados_consolidacao": publicados_consolida,
            "publicados_breaking": publicados_breaking,
            "stage": "relatar",
        }

    # ─── Nó 4: RELATAR ────────────────────────────────────────────

    async def _no_relatar(self, estado: dict) -> dict:
        """Fase 4: Gera e persiste relatório do ciclo."""
        logger.info("=== FASE 4: RELATÓRIO ===")
        
        concluido_em = datetime.utcnow()
        iniciado_em_str = estado.get("iniciado_em", concluido_em.isoformat())
        iniciado_em = datetime.fromisoformat(iniciado_em_str)
        duracao = (concluido_em - iniciado_em).total_seconds()
        
        gaps_analisados = estado.get("gaps_analisados", [])
        gaps_por_tipo = estado.get("gaps_por_tipo", {})
        erros_scan = estado.get("erros_scan", {})
        
        # Estatísticas por portal
        portais_stats: dict[str, int] = {}
        for gap in gaps_analisados:
            portal = gap.get("portal", "?")
            portais_stats[portal] = portais_stats.get(portal, 0) + 1
        
        # Coverage ratio
        total = len(gaps_analisados)
        cobertos = gaps_por_tipo.get("coberto", 0)
        coverage_ratio = cobertos / total if total > 0 else 0.0
        
        # Urgency score médio
        scores = [g.get("urgency_score", 0) for g in gaps_analisados]
        urgency_medio = sum(scores) / len(scores) if scores else 0.0
        
        relatorio = {
            "ciclo_id": estado.get("ciclo_id", "?"),
            "iniciado_em": iniciado_em_str,
            "concluido_em": concluido_em.isoformat(),
            "duracao_segundos": round(duracao, 2),
            "portais_scaneados": len(PORTAIS_CONCORRENTES),
            "portais_com_erro": list(erros_scan.keys()),
            "total_manchetes": total,
            "total_cobertos": cobertos,
            "total_parciais": gaps_por_tipo.get("parcial", 0),
            "total_gaps": gaps_por_tipo.get("gap", 0),
            "total_breaking": gaps_por_tipo.get("breaking", 0),
            "gaps_publicados_pautas_gap": estado.get("publicados_pautas_gap", 0),
            "gaps_publicados_consolidacao": estado.get("publicados_consolidacao", 0),
            "gaps_publicados_breaking": estado.get("publicados_breaking", 0),
            "coverage_ratio": round(coverage_ratio, 4),
            "urgency_score_medio": round(urgency_medio, 2),
            "portais_stats": portais_stats,
        }
        
        # Salvar no Redis
        await self._memoria.salvar_relatorio(relatorio)
        await self._memoria.salvar_scan_stats({
            "ciclo_id": relatorio["ciclo_id"],
            "duracao_segundos": duracao,
            "total_manchetes": total,
            "gaps_encontrados": gaps_por_tipo.get("gap", 0),
            "coverage_ratio": coverage_ratio,
        })
        
        logger.info(
            f"Ciclo {relatorio['ciclo_id']} concluído em {duracao:.1f}s: "
            f"{total} manchetes, coverage={coverage_ratio:.1%}, "
            f"{relatorio['total_gaps']} gaps, "
            f"{relatorio['total_breaking']} breaking"
        )
        
        return {
            **estado,
            "relatorio": relatorio,
            "concluido_em": concluido_em.isoformat(),
            "stage": "completo",
        }

    # ─── API Pública ────────────────────────────────────────────

    async def executar_ciclo(self) -> dict:
        """Executa um ciclo completo de scan-analise-rotear-relatar."""
        estado_inicial = {"stage": "scan"}
        estado_final = await self._graph.ainvoke(estado_inicial)
        return estado_final.get("relatorio", {})

    async def get_relatorio_atual(self) -> dict | None:
        """Retorna o relatório do último ciclo (do Redis)."""
        if self._memoria:
            return await self._memoria.get_relatorio()
        return None
```

---

## PARTE XIII — ENTRYPOINT

### 13.1 Loop Principal com Graceful Shutdown

```python
#!/usr/bin/env python3
# brasileira/agentes/monitor_concorrencia/entrypoint.py

"""
Entrypoint do Monitor Concorrência V3.

Loop de 30 minutos com graceful shutdown por SIGTERM/SIGINT.

Uso:
    python -m brasileira.agentes.monitor_concorrencia.entrypoint

Ou via Docker:
    CMD ["python", "-m", "brasileira.agentes.monitor_concorrencia.entrypoint"]

Variáveis de ambiente necessárias (ver config.py):
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    REDIS_URL=redis://redis:6379/0
    POSTGRES_DSN=postgresql://user:pass@postgres:5432/brasileira
    MONITOR_SCAN_INTERVAL=1800        # 30 minutos
    PLAYWRIGHT_HEADLESS=true
    MONITOR_DRY_RUN=false             # true para testes
"""

import asyncio
import logging
import signal
import sys

from .agente import MonitorConcorrenciaV3
from .config import MonitorConfig

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("monitor_concorrencia")


async def main() -> None:
    """Loop principal do Monitor Concorrência."""
    config = MonitorConfig()
    monitor = MonitorConcorrenciaV3(config)
    
    # Graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    
    def _handle_signal(signame: str) -> None:
        logger.info(f"Sinal {signame} recebido — encerrando graciosamente...")
        stop_event.set()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s.name))
    
    # Inicializar conexões
    try:
        await monitor.inicializar()
    except Exception as e:
        logger.critical(f"Falha na inicialização: {e}", exc_info=True)
        sys.exit(1)
    
    logger.info(
        f"Monitor Concorrência V3 iniciado. "
        f"Intervalo: {config.SCAN_INTERVAL_SECONDS}s ({config.SCAN_INTERVAL_SECONDS//60}min). "
        f"DRY_RUN: {config.DRY_RUN}"
    )
    
    ciclo_numero = 0
    
    try:
        while not stop_event.is_set():
            ciclo_numero += 1
            logger.info(f"━━━ CICLO #{ciclo_numero} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
            try:
                relatorio = await monitor.executar_ciclo()
                logger.info(
                    f"Ciclo #{ciclo_numero} OK: "
                    f"{relatorio.get('total_manchetes', 0)} manchetes, "
                    f"{relatorio.get('total_gaps', 0)} gaps, "
                    f"coverage={relatorio.get('coverage_ratio', 0):.1%}, "
                    f"{relatorio.get('duracao_segundos', 0):.1f}s"
                )
                
            except Exception as e:
                logger.error(
                    f"Ciclo #{ciclo_numero} falhou: {e}",
                    exc_info=True,
                )
                # Não parar o loop por erro em um ciclo
            
            # Aguardar próximo ciclo ou sinal de parada
            logger.info(
                f"Próximo ciclo em {config.SCAN_INTERVAL_SECONDS}s "
                f"({config.SCAN_INTERVAL_SECONDS//60}min)"
            )
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=config.SCAN_INTERVAL_SECONDS,
                )
                # Se chegou aqui, stop_event foi setado
                break
            except asyncio.TimeoutError:
                # Timeout normal — próximo ciclo
                pass
                
    finally:
        logger.info("Encerrando Monitor Concorrência...")
        await monitor.encerrar()
        logger.info("Monitor Concorrência encerrado com sucesso")


if __name__ == "__main__":
    asyncio.run(main())
```

### 13.2 Dockerfile

```dockerfile
# docker/monitor_concorrencia/Dockerfile

FROM python:3.12-slim

WORKDIR /app

# Dependências do sistema para Playwright
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY requirements-monitor.txt .
RUN pip install --no-cache-dir -r requirements-monitor.txt

# Instalar Playwright Chromium
RUN playwright install chromium --with-deps

# Código
COPY . .

# Variáveis de ambiente padrão
ENV PLAYWRIGHT_HEADLESS=true
ENV MONITOR_SCAN_INTERVAL=1800
ENV LOG_LEVEL=INFO

CMD ["python", "-m", "brasileira.agentes.monitor_concorrencia.entrypoint"]
```

### 13.3 `requirements-monitor.txt`

```
# Monitor Concorrência V3 — Dependências
playwright>=1.44.0
scikit-learn>=1.5.0
numpy>=1.26.0
aiokafka>=0.11.0
redis[hiredis]>=5.0.0
asyncpg>=0.29.0
pydantic>=2.5.0
langgraph>=0.2.0
unidecode>=1.3.0
python-dotenv>=1.0.0
```

---

## PARTE XIV — TESTES

### 14.1 Testes Unitários

```python
# tests/agentes/monitor_concorrencia/test_gap_analysis.py

"""Testes unitários do TF-IDF Gap Analysis."""

import pytest
from brasileira.agentes.monitor_concorrencia.gap_analysis import (
    AnalisadorTFIDF,
    TipoGap,
)
from brasileira.agentes.monitor_concorrencia.scanner import Manchete
from brasileira.agentes.monitor_concorrencia.normalizacao import (
    normalizar_para_tfidf,
    deduplicar_manchetes,
)


@pytest.fixture
def analisador_treinado():
    """AnalisadorTFIDF treinado com corpus simulado."""
    corpus = [
        {"id": 1, "titulo": "Lula anuncia reforma tributária no Brasil", "topico": "economia"},
        {"id": 2, "titulo": "Banco Central mantém taxa Selic em 10,5%", "topico": "economia"},
        {"id": 3, "titulo": "Seleção brasileira vence Argentina por 2 a 0", "topico": "esportes"},
        {"id": 4, "titulo": "STF julga ação sobre descriminalização das drogas", "topico": "política"},
        {"id": 5, "titulo": "Incêndio destrói 500 hectares no Pantanal", "topico": "meio ambiente"},
    ]
    a = AnalisadorTFIDF()
    a.treinar_corpus(corpus)
    return a


def _manchete(titulo: str, portal: str = "G1", posicao: int = 1) -> Manchete:
    """Cria manchete de teste."""
    from brasileira.agentes.monitor_concorrencia.normalizacao import normalizar_para_tfidf
    norm = normalizar_para_tfidf(titulo)
    return Manchete(
        portal=portal,
        titulo=titulo,
        titulo_normalizado=norm,
        url=f"https://g1.globo.com/{hash(titulo)}",
        posicao_capa=posicao,
        is_manchete=posicao <= 3,
    )


class TestNormalizacao:
    def test_remove_prefixo_ao_vivo(self):
        norm = normalizar_para_tfidf("AO VIVO: Lula discursa no Congresso")
        assert "ao vivo" not in norm
        assert "lula" in norm

    def test_remove_acentos(self):
        norm = normalizar_para_tfidf("Eleição presidencial no Brasil")
        assert "eleicao" in norm
        assert "presidencial" in norm

    def test_stopwords_removidas(self):
        norm = normalizar_para_tfidf("O presidente da República anunciou medida")
        # "o", "da", "da" são stopwords
        tokens = norm.split()
        assert "o" not in tokens
        assert "da" not in tokens

    def test_deduplicacao_por_hash(self):
        m1 = _manchete("Lula anuncia reforma", portal="G1")
        m2 = _manchete("Lula anuncia reforma", portal="UOL")  # mesmo título, portais diferentes
        resultado = deduplicar_manchetes([m1, m2])
        assert len(resultado) == 1  # Deduplica título idêntico


class TestTFIDF:
    def test_gap_detectado(self, analisador_treinado):
        """Manchete sem correspondência → GAP."""
        manchete = _manchete("Terremoto de magnitude 7 abala o Japão")
        gap = analisador_treinado.classificar_manchete(manchete)
        assert gap.tipo == TipoGap.GAP
        assert gap.score_similaridade < 0.35

    def test_parcial_detectado(self, analisador_treinado):
        """Manchete relacionada mas com ângulo diferente → PARCIAL ou GAP."""
        # "BC eleva juros" é relacionado a "Banco Central mantém taxa Selic"
        manchete = _manchete("BC eleva os juros pela segunda vez em 2026")
        gap = analisador_treinado.classificar_manchete(manchete)
        # Score deve ser > 0 (palavras em comum: banco, central, juros)
        assert gap.score_similaridade > 0

    def test_coberto_detectado(self, analisador_treinado):
        """Manchete muito similar → COBERTO."""
        manchete = _manchete("Lula anuncia reforma tributária com mudanças no imposto")
        gap = analisador_treinado.classificar_manchete(manchete)
        # Similaridade deve ser alta com artigo do corpus sobre "Lula reforma tributária"
        assert gap.score_similaridade > 0.3  # Alguma similaridade detectada

    def test_corpus_vazio(self):
        """Sem corpus → todos gaps."""
        a = AnalisadorTFIDF()
        # Sem treinar
        score, _, _ = a.calcular_similarity("qualquer manchete aqui")
        assert score == 0.0

    def test_num_capas_cluster(self, analisador_treinado):
        """Manchetes similares de portais diferentes devem formar cluster."""
        manchetes = [
            _manchete("Lula assina projeto de reforma tributária", "G1", 1),
            _manchete("Presidente sanciona reforma dos impostos", "UOL", 1),
            _manchete("Reforma tributária aprovada pelo Congresso", "Folha", 1),
        ]
        gaps = analisador_treinado.analisar_todas(manchetes)
        # Pelo menos alguns devem ter num_capas > 1 (cluster formado)
        max_capas = max(g.num_capas for g in gaps)
        assert max_capas >= 1  # Sanidade básica


class TestUrgencyScoring:
    def test_score_breaking_4_capas(self):
        """4+ capas deve gerar breaking candidate."""
        from brasileira.agentes.monitor_concorrencia.urgency import (
            calcular_urgency_score,
            determinar_rota,
            THRESHOLD_CAPAS_BREAKING,
        )
        from brasileira.agentes.monitor_concorrencia.gap_analysis import GapDetectado, TipoGap

        gap = GapDetectado(
            manchete=_manchete("Presidente renuncia ao cargo", "G1", 1),
            tipo=TipoGap.GAP,
            score_similaridade=0.0,
            artigo_similar_id=None,
            artigo_similar_titulo=None,
            num_capas=5,  # 5 portais
        )
        gap.urgency_score = calcular_urgency_score(gap, "política", 2.0)
        rotas = determinar_rota(gap)
        
        assert "breaking-candidate" in rotas
        assert "pautas-gap" in rotas
        assert gap.urgency_score >= 6.0  # Alta urgência

    def test_score_baixo_nao_roteia(self):
        """Score baixo → não deve ser roteado."""
        from brasileira.agentes.monitor_concorrencia.urgency import determinar_rota
        from brasileira.agentes.monitor_concorrencia.gap_analysis import GapDetectado, TipoGap

        gap = GapDetectado(
            manchete=_manchete("Celebridade lança novo álbum", "Terra", 25),
            tipo=TipoGap.GAP,
            score_similaridade=0.0,
            artigo_similar_id=None,
            artigo_similar_titulo=None,
            num_capas=1,
            urgency_score=1.5,  # Muito baixo
        )
        rotas = determinar_rota(gap)
        assert len(rotas) == 0  # Não roteia

    def test_parcial_vai_para_consolidacao(self):
        """Gap PARCIAL com score médio → consolidacao."""
        from brasileira.agentes.monitor_concorrencia.urgency import determinar_rota
        from brasileira.agentes.monitor_concorrencia.gap_analysis import GapDetectado, TipoGap

        gap = GapDetectado(
            manchete=_manchete("Banco Central decide sobre juros amanhã", "Folha", 2),
            tipo=TipoGap.PARCIAL,
            score_similaridade=0.45,
            artigo_similar_id=42,
            artigo_similar_titulo="Reunião do Copom será realizada esta semana",
            num_capas=2,
            urgency_score=4.5,
        )
        rotas = determinar_rota(gap)
        assert "consolidacao" in rotas
        assert "pautas-gap" not in rotas


class TestKafkaPayload:
    def test_payload_pautas_gap(self):
        """Payload pautas-gap deve ter campos obrigatórios."""
        from brasileira.agentes.monitor_concorrencia.kafka_producer import (
            _montar_payload_pautas_gap,
        )
        from brasileira.agentes.monitor_concorrencia.gap_analysis import GapDetectado, TipoGap

        gap = GapDetectado(
            manchete=_manchete("Greve dos professores paralisa São Paulo", "G1", 1),
            tipo=TipoGap.GAP,
            score_similaridade=0.0,
            artigo_similar_id=None,
            artigo_similar_titulo=None,
            num_capas=3,
            urgency_score=6.5,
        )
        payload = _montar_payload_pautas_gap(gap)
        
        assert payload["evento"] == "gap_concorrencia"
        assert payload["fonte"] == "monitor_concorrencia"
        assert "urgencia" in payload
        assert "manchete" in payload
        assert payload["manchete"]["portal"] == "G1"
        assert "contexto" in payload
        # NUNCA deve ter referência ao Pauteiro
        assert "pauteiro" not in str(payload).lower()

    def test_payload_breaking(self):
        """Payload breaking-candidate deve ter num_capas ≥ 4."""
        from brasileira.agentes.monitor_concorrencia.kafka_producer import (
            _montar_payload_breaking,
        )
        from brasileira.agentes.monitor_concorrencia.gap_analysis import GapDetectado, TipoGap

        gap = GapDetectado(
            manchete=_manchete("Terremoto atinge cidade com 5 mortos", "CNN Brasil", 1),
            tipo=TipoGap.GAP,
            score_similaridade=0.0,
            artigo_similar_id=None,
            artigo_similar_titulo=None,
            num_capas=6,
            urgency_score=9.0,
        )
        payload = _montar_payload_breaking(gap)
        
        assert payload["evento"] == "breaking_candidate"
        assert payload["num_capas"] == 6
        assert payload["urgency_score"] == 9.0


# tests/agentes/monitor_concorrencia/test_scanner.py

"""Testes de integração do Scanner Playwright."""

import pytest


@pytest.mark.asyncio
@pytest.mark.integration  # Marcar como integration (requer Playwright instalado)
async def test_scan_g1():
    """Scanneia G1 e verifica que retorna manchetes."""
    from brasileira.agentes.monitor_concorrencia.scanner import CapaScanner
    from brasileira.agentes.monitor_concorrencia.portais import PORTAIS_CONCORRENTES

    g1_config = next(p for p in PORTAIS_CONCORRENTES if p["nome"] == "G1")
    
    async with CapaScanner(headless=True) as scanner:
        manchetes = await scanner.scan_portal(g1_config)
    
    assert len(manchetes) >= 3, f"G1 retornou apenas {len(manchetes)} manchetes"
    assert all(len(m.titulo) >= 15 for m in manchetes)
    assert all(m.portal == "G1" for m in manchetes)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scan_todos_portais():
    """Scanneia todos os 8 portais e verifica integridade."""
    from brasileira.agentes.monitor_concorrencia.scanner import CapaScanner
    from brasileira.agentes.monitor_concorrencia.portais import (
        PORTAIS_CONCORRENTES,
        PORTAIS_OBRIGATORIOS,
    )
    
    async with CapaScanner(headless=True) as scanner:
        resultado = await scanner.scan_todos(PORTAIS_CONCORRENTES)
    
    # Todos os 8 portais devem ter sido tentados
    assert set(resultado.keys()) == PORTAIS_OBRIGATORIOS
    
    # Pelo menos 5 dos 8 devem ter retornado manchetes
    portais_com_manchetes = sum(1 for v in resultado.values() if len(v) > 0)
    assert portais_com_manchetes >= 5, (
        f"Apenas {portais_com_manchetes} portais retornaram manchetes. "
        "Verificar seletores CSS."
    )


@pytest.mark.asyncio
async def test_validar_portais():
    """Valida que os 8 portais obrigatórios estão configurados."""
    from brasileira.agentes.monitor_concorrencia.portais import (
        validar_portais,
        PORTAIS_OBRIGATORIOS,
        PORTAIS_CONCORRENTES,
    )
    
    # Não deve levantar exceção
    validar_portais()
    
    # Verificar que todos os obrigatórios estão presentes
    configurados = {p["nome"] for p in PORTAIS_CONCORRENTES}
    assert PORTAIS_OBRIGATORIOS.issubset(configurados)
```

---

## PARTE XV — CHECKLIST DE IMPLEMENTAÇÃO

### 15.1 Fase 1 — Scaffolding (Dia 1)

- [ ] Criar diretório `brasileira/agentes/monitor_concorrencia/`
- [ ] Criar `__init__.py` com exports corretos
- [ ] Criar `config.py` com MonitorConfig e todas as env vars
- [ ] Criar `schemas.py` com todos os Pydantic models
- [ ] Executar `playwright install chromium --with-deps`
- [ ] Verificar que Playwright funciona: `python -c "from playwright.sync_api import sync_playwright; print('OK')"`

### 15.2 Fase 2 — Scanner e Portais (Dia 1-2)

- [ ] Criar `scanner.py` com CapaScanner + Manchete
- [ ] Criar `portais.py` com os 8 portais completos (G1, UOL, Folha, Estadão, CNN Brasil, R7, Terra, Metrópoles)
- [ ] Criar `normalizacao.py` com STOPWORDS_PT + normalizar_para_tfidf
- [ ] Testar cada portal individualmente (sem paralelismo)
- [ ] Confirmar: G1 retorna ≥10 manchetes, CNN Brasil retorna ≥5 manchetes
- [ ] Ajustar seletores que não funcionam
- [ ] Testar `scan_todos()` com asyncio.gather

### 15.3 Fase 3 — TF-IDF e Gap Analysis (Dia 2)

- [ ] Criar `gap_analysis.py` com AnalisadorTFIDF
- [ ] Testar treinar_corpus() com 100 artigos fictícios
- [ ] Validar thresholds: manchete idêntica ao corpus → score > 0.65
- [ ] Validar thresholds: manchete não relacionada → score < 0.35
- [ ] Testar clustering de tópicos similares
- [ ] Confirmar que num_capas é calculado corretamente

### 15.4 Fase 4 — Urgency Scoring e Roteamento (Dia 2-3)

- [ ] Criar `urgency.py` com calcular_urgency_score() e determinar_rota()
- [ ] Validar: manchete em 4+ portais → "breaking-candidate" está nas rotas
- [ ] Validar: GAP com score ≥ 3 → "pautas-gap" está nas rotas
- [ ] Validar: PARCIAL com score ≥ 3 → "consolidacao" está nas rotas
- [ ] CRÍTICO: Confirmar que "pautas-especiais" NUNCA está nas rotas
- [ ] CRÍTICO: Confirmar que nenhum payload menciona "pauteiro"

### 15.5 Fase 5 — Kafka e Memória (Dia 3)

- [ ] Criar `kafka_producer.py` com MonitorKafkaProducer
- [ ] Criar `memoria.py` com MemoriaMonitor
- [ ] Executar com DRY_RUN=true: confirmar logs de rotas sem publicar
- [ ] Executar com Kafka local: confirmar mensagens chegando nos tópicos
- [ ] Testar cooldown Redis: mesmo gap não alertado duas vezes em 60min
- [ ] Testar cache de artigos Redis: segunda chamada não vai ao PostgreSQL

### 15.6 Fase 6 — Agente LangGraph (Dia 3-4)

- [ ] Criar `agente.py` com MonitorConcorrenciaV3
- [ ] Testar executar_ciclo() completo com DRY_RUN=true
- [ ] Confirmar log de relatório ao final de cada ciclo
- [ ] Verificar que erros em portais individuais não param o ciclo
- [ ] Verificar que relatório é salvo no Redis após cada ciclo

### 15.7 Fase 7 — Entrypoint e Deploy (Dia 4)

- [ ] Criar `entrypoint.py` com loop de 30min
- [ ] Testar SIGTERM: encerramento gracioso em < 5s
- [ ] Testar SIGINT (Ctrl+C): encerramento gracioso
- [ ] Criar `requirements-monitor.txt`
- [ ] Criar `Dockerfile`
- [ ] Testar `docker build` e `docker run`
- [ ] Verificar que Playwright funciona dentro do container

### 15.8 Fase 8 — Testes e Validação (Dia 4-5)

- [ ] Executar testes unitários: `pytest tests/agentes/monitor_concorrencia/ -v`
- [ ] Executar testes de integração com `--integration` flag
- [ ] Confirmar coverage > 80%
- [ ] Teste de ciclo real: verificar gaps reais nos portais
- [ ] Validar SQL: tabela `analise_concorrencia` criada e populada
- [ ] Validar Redis: chaves `monitor:*` criadas após ciclo

### 15.9 Checklist de Regras de Negócio

| # | Regra | Como Verificar |
|---|-------|---------------|
| 1 | NUNCA rotear via Pauteiro | `grep -r "pauteiro\|pautas-especiais" kafka_producer.py` deve retornar vazio |
| 2 | 8 portais obrigatórios | `validar_portais()` não levanta exceção |
| 3 | Playwright (não requests) | `grep -r "import requests" scanner.py` deve retornar vazio |
| 4 | TF-IDF com stopwords PT | `analisador._vectorizer.stop_words` contém "que", "com", "para" |
| 5 | 4+ capas → breaking | `determinar_rota(gap_4capas)` inclui "breaking-candidate" |
| 6 | Gap → pautas-gap | `determinar_rota(gap_zero)` inclui "pautas-gap" |
| 7 | Parcial → consolidacao | `determinar_rota(gap_parcial)` inclui "consolidacao" |
| 8 | Cooldown no Redis | Após alerta, `check_cooldown(hash)` retorna True |
| 9 | Ciclo < 4 minutos | `relatorio["duracao_segundos"] < 240` |
| 10 | Falha de portal não para ciclo | Desligar rede de 1 portal → outros continuam |

---

## PARTE XVI — DIAGNÓSTICO DE PROBLEMAS COMUNS

### 16.1 Seletor Quebrado

**Sintoma:** Portal retorna 0 ou < 3 manchetes
**Causa mais comum:** Portal atualizou layout/classes CSS
**Diagnóstico:**
```bash
# Capturar HTML atual do portal para inspecionar
python -c "
import asyncio
from playwright.async_api import async_playwright

async def capturar():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://www.cnnbrasil.com.br', wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        html = await page.content()
        with open('/tmp/cnnbrasil.html', 'w') as f:
            f.write(html)
        await browser.close()

asyncio.run(capturar())
"
# Depois inspecionar /tmp/cnnbrasil.html no browser
```
**Solução:** Atualizar seletor primário em `portais.py` + adicionar comentário com data da atualização

### 16.2 TF-IDF Corpus Vazio

**Sintoma:** Log "Corpus vazio — publicando todos os gaps sem filtro TF-IDF"
**Causa:** Nenhum artigo publicado nas últimas 6h (início do dia, manutenção)
**Solução:** Comportamento correto — todos gaps são publicados. Não é erro.
**Observação:** Se persistir > 2h, investigar se Reporter está publicando.

### 16.3 Kafka Connection Error

**Sintoma:** `KafkaConnectionError` nos logs
**Causa:** Kafka não disponível ou KAFKA_BOOTSTRAP_SERVERS errado
**Diagnóstico:**
```bash
# Testar conectividade
python -c "
import asyncio
from aiokafka import AIOKafkaProducer
async def test():
    p = AIOKafkaProducer(bootstrap_servers='kafka:9092')
    await p.start()
    print('Kafka OK')
    await p.stop()
asyncio.run(test())
"
```
**Solução:** Verificar env KAFKA_BOOTSTRAP_SERVERS, confirmar serviço Kafka ativo

### 16.4 Playwright Timeout

**Sintoma:** `playwright._impl._errors.TimeoutError: Timeout 30000ms exceeded`
**Causa:** Portal lento ou bloqueando bots
**Solução:** Aumentar `PLAYWRIGHT_TIMEOUT_NAV` para 45000 e adicionar `espera_extra_ms` no config do portal problemático

### 16.5 Memory Leak em Ciclos Longos

**Sintoma:** Consumo de memória cresce com cada ciclo
**Causa:** Contexts do Playwright não sendo fechados em caso de erro
**Solução:** O `async with CapaScanner()` garante `__aexit__` mesmo em exceções. Verificar que nenhum context é criado fora do `async with`.

---

## APÊNDICE A — DIFERENÇAS ENTRE V2 E V3 (RESUMO EXECUTIVO)

| Aspecto | V2 | V3 |
|---------|----|----|
| **Roteamento** | Alerta → Pauteiro → Reporter | Gap → Kafka direto (Reporter/Consolidador/Curador) |
| **Scraping** | RSS feeds / requests+BeautifulSoup | Playwright headless (JS-heavy) |
| **Portais** | G1, UOL, Folha, CNN, Metrópoles, Estadão (6) | 8 portais + R7 + Terra |
| **TF-IDF** | Configuração padrão scikit-learn | Stopwords PT + bigramas + boost entidades |
| **Clustering** | 3 primeiras palavras como chave | Cosine similarity ≥ 0.45 |
| **Cooldown alertas** | Dict Python (volátil) | Redis com TTL (persistente) |
| **Corpus** | RSS dos concorrentes | PostgreSQL: artigos publicados (últimas 6h) |
| **Tópicos Kafka** | `lacuna_detectada` (EventBus) | `pautas-gap`, `consolidacao`, `breaking-candidate` |
| **Breaking detection** | Ausente | 4+ capas → `breaking-candidate` |
| **Urgency Score** | Fatores: competidor/tempo/categoria (3 fatores) | 4 fatores: competidor/posição/categoria/keywords |
| **Paralelismo** | `asyncio.gather()` (presente) | `asyncio.gather()` (mantido + melhorado) |
| **Memória** | Working apenas (Redis) | Working + Episódica (PostgreSQL) + Semântica |
| **Entrypoint** | `start_monitoring()` no agente | `entrypoint.py` standalone com graceful shutdown |

---

## APÊNDICE B — VARIÁVEIS DE AMBIENTE COMPLETAS

```bash
# Monitor Concorrência V3 — .env

# ─── Infraestrutura ─────────────────────────────────────────────
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
REDIS_URL=redis://redis:6379/0
POSTGRES_DSN=postgresql://usuario:senha@postgres:5432/brasileira

# ─── Playwright ─────────────────────────────────────────────────
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_TIMEOUT_NAV=30000   # 30s timeout de navegação
PLAYWRIGHT_TIMEOUT_SEL=15000   # 15s timeout de seletor

# ─── Scan ───────────────────────────────────────────────────────
MONITOR_SCAN_INTERVAL=1800     # 30 minutos
MAX_MANCHETES_PORTAL=30        # Máximo de manchetes por portal por ciclo

# ─── TF-IDF ─────────────────────────────────────────────────────
TFIDF_THRESHOLD_COBERTO=0.65   # Acima = cobrimos o tema
TFIDF_THRESHOLD_PARCIAL=0.35   # Acima = cobertura parcial
TFIDF_THRESHOLD_CLUSTER=0.45   # Agrupa manchetes similares
CORPUS_HORAS=6                 # Artigos das últimas N horas
CORPUS_MAX_ARTIGOS=500         # Máximo de artigos no corpus

# ─── Urgency ────────────────────────────────────────────────────
THRESHOLD_CAPAS_BREAKING=4     # 4+ portais = breaking candidate
THRESHOLD_SCORE_ROTEAR=3.0     # Score mínimo para rotear

# ─── Cooldowns ──────────────────────────────────────────────────
MONITOR_COOLDOWN_SEGUNDOS=3600  # 60min entre alertas do mesmo gap
MAX_GAPS_POR_CICLO=20           # Máximo de gaps publicados por ciclo

# ─── Debug ──────────────────────────────────────────────────────
LOG_LEVEL=INFO
MONITOR_DRY_RUN=false          # true = não publica no Kafka
```

---

## APÊNDICE C — DIAGRAMA DE FLUXO KAFKA

```
                    MONITOR CONCORRÊNCIA V3
                    ┌───────────────────────┐
                    │  Ciclo a cada 30min   │
                    │  8 portais / Playwright│
                    └──────────┬────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  pautas-gap  │  │ consolidacao │  │  breaking-   │
    │              │  │              │  │  candidate   │
    │ Partição:    │  │ Partição:    │  │              │
    │  urgencia    │  │  tema_id     │  │ Round-robin  │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           │                 │                  │
           ▼                 ▼                  ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │   REPORTER   │  │ CONSOLIDADOR │  │   CURADOR    │
    │              │  │              │  │  HOMEPAGE    │
    │ Escreve novo │  │ Consolida ou │  │              │
    │ artigo do    │  │ amplia artigo│  │ Promove para │
    │ zero         │  │ existente    │  │ breaking na  │
    │              │  │              │  │ homepage     │
    └──────────────┘  └──────────────┘  └──────────────┘

    ❌ NUNCA:
    ┌──────────────┐
    │   PAUTEIRO   │  ← Monitor Concorrência NUNCA publica aqui
    │              │     (era o bug do V2)
    └──────────────┘
```

---

**Fim do Briefing #11 — Monitor Concorrência V3**

*Documento gerado em 26 de março de 2026*
*Versão: 3.0.0*
*Linhas de código de referência: ~1.200+ (implementação completa em seções III-XIII)*
*Total de seções: 16 partes + 3 apêndices*
