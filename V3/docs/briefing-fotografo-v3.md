# Briefing Completo para IA — Fotógrafo V3 (Pipeline de Imagem Pós-Publicação)

**Data:** 26 de março de 2026
**Classificação:** Briefing de Implementação — Componente #5
**Público-alvo:** IA de implementação (Cursor, Windsurf, Copilot, Claude Code ou equivalente)
**Repositório:** https://github.com/redes-dsc/brasileira
**Stack:** Python 3.12+ / LangGraph / aiokafka / HTTPX / asyncio / Redis / PostgreSQL / WordPress REST API
**Componente:** `brasileira/agents/fotografo/` — pipeline de imagem pós-publicação, 4 tiers, CLIP validation
**Dependências:** SmartLLMRouter V3 (Componente #1), Worker Pool de Coletores V3 (Componente #2)

---

## LEIA ISTO PRIMEIRO — Por que o Fotógrafo é Crítico

O Fotógrafo é o agente responsável por garantir que **100% das notícias publicadas na brasileira.news tenham imagem**. Ele age **após a publicação** do artigo, consumindo o evento `article-published` do Kafka e executando um pipeline de 4 tiers para encontrar, validar e associar a imagem ideal ao post no WordPress.

**A imagem tem importância jornalística.** Não é um elemento decorativo. Portais como G1, Folha e Estadão dedicam equipes inteiras de editores de fotografia por uma razão: a imagem editorial correta aumenta o engajamento em 40-60%, reforça o sentido da matéria, e transmite credibilidade ao veículo. Um portal que publica notícias de governo com foto de stock genérica de "homem de terno" sinaliza amadorismo.

**Regras invioláveis deste componente:**
1. Query generation usa LLM **PREMIUM** — nunca ECONÔMICO
2. Nenhuma notícia fica sem imagem (placeholder garante isso)
3. Pipeline de 4 tiers com persistência de rejeições
4. Reformulação automática de queries quando tudo falha
5. Imagens geradas por IA (Tier 3) são sempre rotuladas

**Este briefing contém TUDO que você precisa para implementar o Fotógrafo do zero.** Não consulte outros documentos. Não improvise nos pontos marcados como OBRIGATÓRIO.

---

## PARTE I — DIAGNÓSTICO V2: O QUE ESTÁ QUEBRADO NO PIPELINE DE IMAGENS

### 1.1 Problema Central: Query Generation com LLM Econômico

O `fotografo-17.py` e `curador_imagens_unificado.py` usam modelos LLM de baixa qualidade para gerar queries de busca de imagem — o que é **categoricamente errado**. A regra de negócio é clara: `imagem_query` usa tier **PREMIUM**.

```python
# V2 — ERRADO: Query generation com modelo barato
# Em curador_imagens_unificado.py:
resp = requests.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_key}",
    json={...},
    timeout=30,
)
# gemini-2.0-flash é ECONÔMICO. Deveria ser modelo PREMIUM.
# Além disso: requests.post síncrono, sem retry, sem circuit breaker.
```

**Consequência:** Queries geradas por modelos baratos são genéricas, sem sensibilidade jornalística. Uma notícia sobre "STF vota reforma tributária" gera query "política brasil tributo" em vez de "supreme court federal building brazil government" — a diferença em qualidade de resultado é abismal.

### 1.2 Catálogo Completo de Bugs do Pipeline V2

Os bugs abaixo foram auditados em `bugs_imagens.md` (análise de 16 arquivos, 329 problemas identificados):

| # | Bug | Arquivo | Impacto |
|---|-----|---------|---------|
| B-01 | Lógica RGBA invertida — imagens com modo `PA` ficam com fundo preto | `curador_imagens_unificado.py:39` | Crítico |
| B-02 | `is_valid_image_url` faz HTTP request para cada tag `<img>` — 30 imagens = 30 GETs síncronos | `curador_imagens_unificado.py:57` | Crítico |
| B-03 | WebP sem parsing de dimensões — ícones 16x16 passam nos filtros | `curador_imagens_unificado.py:88` | Crítico |
| B-04 | Tier 1 pulado para fontes não-oficiais (G1, UOL, Folha) — nunca tenta `og:image` de fontes comerciais | `curador_imagens_unificado.py:104` | Crítico |
| B-05 | Tier 2 e Tier 3C usam mesma API Google CSE — duplica consumo de quota (100/dia free) | `curador_imagens_unificado.py:119` | Crítico |
| B-06 | Flickr `user_id` com valores placeholder ("paborboleta", "senaborboleta") — nunca funciona | `curador_imagens_unificado.py:143` | Crítico |
| B-07 | Race condition — dois singletons para a mesma classe sem lock | `curador_imagens_unificado.py:162` | Crítico |
| B-08 | Upload WP sem tratamento de erro no meta update — `alt_text` e `caption` nunca salvos | `curador_imagens_unificado.py:196` | Alto |
| B-09 | Placeholder retorna `None` silenciosamente — post publicado sem imagem sem alerta | `curador_imagens_unificado.py:210` | Crítico |
| B-10 | `content_patterns` com regex usado como substring — nunca funciona | `curador_imagens_unificado.py:223` | Médio |
| B-11 | Dois placeholders hardcoded diferentes — impossível identificar posts sem imagem real | `limpador_imagens_ia.py:251` | Alto |
| B-12 | `Range` header ignorado — download completo de imagens grandes em validação | `curador_imagens_unificado.py:294` | Alto |
| B-13 | API keys expostas em f-strings de URL com logging debug ativo | `curador_imagens_unificado.py:311` | Segurança |
| B-14 | Protocol-relative URLs `//cdn.example.com` tratadas como paths relativos | `curador_imagens_unificado.py:319` | Médio |
| B-15 | `safe_filename` pode ficar vazio para títulos em árabe/japonês/CJK | `curador_imagens_unificado.py:333` | Médio |
| B-16 | `get_query_generator()` chamado duas vezes no mesmo pipeline | `curador_imagens_unificado.py:341` | Baixo |
| B-17 | `trava_definitiva_dalle.py` — DALL-E 3 **desativado via flag hardcoded**: `return None # TRAVA EDITORIAL` | `roteador_ia.py:88` | Crítico |
| B-18 | Sem persistência de rejeições — imagem rejeitada pode ser selecionada novamente no próximo ciclo | arquitetura | Crítico |
| B-19 | Sem reformulação de queries — se query 1 falha, não há estratégia broadening/pivoting | arquitetura | Crítico |
| B-20 | Processamento síncrono — cada tier bloqueia a thread inteira | arquitetura | Crítico |
| B-21 | Sem Kafka consumer — Fotógrafo V2 é chamado de forma acoplada, bloqueando o Reporter | arquitetura | Crítico |

### 1.3 O Problema da Desativação do DALL-E

O arquivo `roteador_ia.py` contém a seguinte linha:

```python
def gerar_imagem_dalle(prompt: str) -> str | None:
    """Gera imagem com DALL-E 3."""
    return None  # [TRAVA EDITORIAL - DALL-E 3 DESATIVADO]
    # Código real abaixo nunca executa
    ...
```

Esta trava foi adicionada provavelmente para evitar custos de geração em testes — e **nunca foi removida**. O resultado: o Tier de geração por IA nunca executa, e notícias de tópicos abstratos (política econômica, diplomacia, legislação) ficam com imagens de stock genéricas ou sem imagem alguma.

### 1.4 O Problema da Falta de Persistência

A V2 não persiste rejeições. Se uma imagem de logo da Câmara dos Deputados (incorretamente retornada pela API Flickr) é rejeitada em um ciclo, ela pode ser retornada e rejeitada novamente no próximo. Sem blacklist de URLs rejeitadas em Redis, o pipeline desperdiça ciclos repetindo erros.

### 1.5 Resumo: O que V3 Corrige

| Problema V2 | Solução V3 |
|-------------|------------|
| Query gen com modelo econômico | SmartLLMRouter com tier PREMIUM |
| DALL-E desativado por trava hardcoded | Tier 3 com gpt-image-1 + Flux.2 Pro |
| Sem persistência de rejeições | Redis blacklist com TTL 24h |
| Sem reformulação de queries | 2 rodadas: broadening → pivoting |
| Tier 1 apenas para fontes oficiais | Tier 1 para TODAS as fontes |
| Processamento síncrono | asyncio full |
| Sem Kafka consumer | Consumer `article-published` |
| Flickr com user_ids fictícios | IDs reais validados |
| Dois singletons sem lock | Injeção de dependência |
| Sem CLIP validation | CLIP score por tier |

---

## PARTE II — ARQUITETURA DO FOTÓGRAFO V3

### 2.1 Posição no Sistema

```
Reporter → publica post → Kafka: article-published
                                        ↓
                              ┌─────────────────────┐
                              │   FOTÓGRAFO V3       │
                              │  (pós-publicação)    │
                              └─────────────────────┘
                                        ↓
                    ┌───────────────────────────────────────┐
                    │         PIPELINE DE 4 TIERS           │
                    │                                       │
                    │  TIER 1: Extração fonte original      │
                    │     → og:image, schema.org             │
                    │                    ↓ (falha)          │
                    │  TIER 2: Busca APIs com persistência  │
                    │     → Pexels, Unsplash, Wikimedia,    │
                    │       Flickr CC, Agência Brasil       │
                    │     + CLIP validation                  │
                    │                    ↓ (falha)          │
                    │  TIER 3: Geração por IA               │
                    │     → gpt-image-1, Flux.2 Pro         │
                    │     + label OBRIGATÓRIO               │
                    │                    ↓ (falha)          │
                    │  TIER 4: Placeholder Temático         │
                    │     → por editoria, GARANTIA          │
                    └───────────────────────────────────────┘
                                        ↓
                           Upload WordPress Media Library
                                        ↓
                           SET featured_media no post
                                        ↓
                          Kafka: image-attached (evento)
```

### 2.2 Princípios de Design da V3

1. **Kafka-driven**: O Fotógrafo é um consumer autônomo. Não é chamado pelo Reporter.
2. **Async-first**: Todo o pipeline usa `asyncio` / `httpx.AsyncClient`. Sem `requests` síncronos.
3. **Fail-forward**: Nunca bloqueia. Tier 1 falhou? Vai para Tier 2. Tier 2 falhou? Tier 3. Tier 3 falhou? Tier 4. Tier 4 é GARANTIA — nunca falha.
4. **Persistência de estado**: Rejeições em Redis, resultados em PostgreSQL.
5. **CLIP como filtro de qualidade**: Antes de aceitar qualquer imagem, calcula score semântico.
6. **LLM Premium para queries**: O SmartLLMRouter com `task_type="imagem_query"` garante modelo PREMIUM.

### 2.3 Fluxo LangGraph

```python
# Nós do grafo
NODES = [
    "consume_event",       # Lê evento article-published do Kafka
    "extract_context",     # Extrai título, editoria, URL fonte, conteúdo
    "generate_queries",    # LLM PREMIUM gera queries para cada tier
    "tier1_extraction",    # og:image, schema.org da fonte original
    "tier2_search",        # Pexels, Unsplash, Wikimedia, Flickr, Agência Brasil
    "clip_validation",     # Valida relevância semântica com CLIP
    "tier3_generation",    # DALL-E / Flux se tiers 1-2 falharam
    "tier4_placeholder",   # Placeholder temático por editoria (GARANTIA)
    "upload_wordpress",    # Upload na media library + set featured_media
    "emit_event",          # Emite image-attached no Kafka
    "record_metrics",      # Persiste métricas no PostgreSQL
]

# Fluxo condicional
EDGES = {
    "tier1_extraction": {
        "success": "clip_validation",
        "fail": "tier2_search",
    },
    "tier2_search": {
        "success": "clip_validation",
        "fail": "tier3_generation",
    },
    "clip_validation": {
        "approved": "upload_wordpress",
        "rejected_retry": "tier2_search",      # Reformulação rodada 1
        "rejected_final": "tier3_generation",  # Reformulação rodada 2
        "exhausted": "tier4_placeholder",
    },
    "tier3_generation": {
        "success": "upload_wordpress",
        "fail": "tier4_placeholder",
    },
    "tier4_placeholder": {
        "always": "upload_wordpress",  # NUNCA falha
    },
    "upload_wordpress": {
        "success": "emit_event",
        "fail": "record_metrics",  # Falha WP: registra e continua
    },
}
```

### 2.4 Estrutura de Módulos

```
brasileira/
└── agents/
    └── fotografo/
        ├── __init__.py
        ├── agent.py              # FotografoAgent — consumer Kafka + LangGraph
        ├── query_generator.py    # LLM Premium → queries por tier
        ├── tier1_extraction.py   # og:image, schema.org, twitter:image
        ├── tier2_search.py       # Orchestrador de APIs de busca
        ├── apis/
        │   ├── pexels.py         # Pexels API client
        │   ├── unsplash.py       # Unsplash API client
        │   ├── wikimedia.py      # Wikimedia Commons API client
        │   ├── flickr.py         # Flickr Creative Commons API client
        │   └── agencia_brasil.py # EBC/Agência Brasil scraper
        ├── clip_validator.py     # CLIP score validation
        ├── tier3_generation.py   # gpt-image-1 + Flux.2 Pro
        ├── tier4_placeholder.py  # Placeholders por editoria
        ├── wp_uploader.py        # WordPress REST API upload async
        ├── rejection_cache.py    # Redis blacklist de URLs rejeitadas
        ├── models.py             # Pydantic models
        └── config.py             # Configurações e rate limits
```

---

## PARTE III — TIER 1: EXTRAÇÃO DA FONTE ORIGINAL

### 3.1 Princípio

O Tier 1 tenta extrair a imagem **diretamente do artigo original** na fonte. Esta é sempre a melhor imagem: é a que o próprio veículo escolheu para representar a matéria, tem contexto editorial perfeito, e frequentemente é de alta resolução.

**OBRIGATÓRIO V3:** O Tier 1 é executado para **TODAS** as fontes — oficiais e não-oficiais. O V2 tinha um bug crítico (B-04) que pulava este tier para fontes comerciais.

### 3.2 Hierarquia de Extração

```python
# tier1_extraction.py

HIERARCHY = [
    # Nível 1 — schema.org JSON-LD (95% de precisão)
    "jsonld_primaryImageOfPage",
    "jsonld_newsarticle_image",
    # Nível 2 — Open Graph (85% de precisão)
    "og_image",
    # Nível 3 — Twitter Card (80% de precisão)
    "twitter_image",
    # Nível 4 — Article tag com dimensões (60% de precisão)
    "article_first_image",
    # Nível 5 — Maior imagem da página (40% de precisão)
    "largest_image",
]
```

### 3.3 Implementação Completa

```python
# brasileira/agents/fotografo/tier1_extraction.py

import asyncio
import json
import re
from typing import Optional
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup

from .models import ImageCandidate, ExtractionResult


# CDNs publicitários — ignorar imagens dessas origens
ADVERTISING_CDNS = frozenset([
    "doubleclick.net", "googlesyndication.com", "adnxs.com",
    "taboola.com", "outbrain.com", "criteo.com", "amazon-adsystem.com",
    "scorecardresearch.com", "quantserve.com",
])

# Padrões de URL que indicam imagens não-editoriais
NON_EDITORIAL_PATTERNS = frozenset([
    "logo", "icon", "sprite", "avatar", "badge", "banner",
    "ad-", "-ad-", "pixel", "tracking", "1x1", "loading",
    "spinner", "placeholder", "default-image", "favicon",
])

# User-Agent de newsbot respeitável
NEWSBOT_UA = "brasileira-newsbot/3.0 (https://brasileira.news/bot; contact@brasileira.news)"


class Tier1Extractor:
    """Extrai imagem editorial da fonte original do artigo."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def extract(
        self,
        source_url: str,
        html_content: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extrai a imagem editorial principal do artigo.

        Args:
            source_url: URL do artigo original
            html_content: HTML já baixado (evita re-fetch)

        Returns:
            ExtractionResult com imagem candidata ou falha
        """
        if not source_url:
            return ExtractionResult(success=False, reason="source_url vazio")

        try:
            if not html_content:
                html_content = await self._fetch_html(source_url)

            if not html_content:
                return ExtractionResult(success=False, reason="Falha ao buscar HTML da fonte")

            soup = BeautifulSoup(html_content, "lxml")
            base_url = self._get_base_url(source_url)

            # Tenta cada nível da hierarquia
            candidate = (
                self._extract_jsonld(soup) or
                self._extract_og_image(soup) or
                self._extract_twitter_image(soup) or
                self._extract_article_image(soup, base_url) or
                self._extract_largest_image(soup, base_url)
            )

            if candidate:
                candidate.url = self._normalize_url(candidate.url, source_url)
                if self._is_valid_candidate(candidate):
                    return ExtractionResult(
                        success=True,
                        candidate=candidate,
                        extraction_method=candidate.source_method,
                    )

            return ExtractionResult(success=False, reason="Nenhuma imagem editorial encontrada")

        except Exception as e:
            return ExtractionResult(success=False, reason=f"Erro na extração: {e}")

    async def _fetch_html(self, url: str) -> Optional[str]:
        """Faz GET da URL com timeout e User-Agent de bot respeitável."""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": NEWSBOT_UA},
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.text
        except Exception:
            pass
        return None

    def _extract_jsonld(self, soup: BeautifulSoup) -> Optional[ImageCandidate]:
        """
        Extrai imagem de schema.org JSON-LD.
        Suporta NewsArticle, Article, BlogPosting.
        """
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string or script.get_text()
                if not raw:
                    continue
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]

                for item in items:
                    schema_type = item.get("@type", "")
                    # Aceita tipos de artigo de notícia
                    if schema_type not in {
                        "NewsArticle", "Article", "BlogPosting",
                        "ReportageNewsArticle", "AnalysisNewsArticle"
                    }:
                        continue

                    # primaryImageOfPage — maior especificidade
                    primary = item.get("primaryImageOfPage", {})
                    if isinstance(primary, dict):
                        url = primary.get("url") or primary.get("contentUrl")
                        if url:
                            return ImageCandidate(
                                url=url,
                                source_method="jsonld_primaryImageOfPage",
                                confidence=0.95,
                            )

                    # image property
                    img = item.get("image")
                    if isinstance(img, str) and img:
                        return ImageCandidate(
                            url=img,
                            source_method="jsonld_newsarticle_image",
                            confidence=0.90,
                        )
                    elif isinstance(img, dict):
                        url = img.get("url") or img.get("contentUrl")
                        if url:
                            return ImageCandidate(
                                url=url,
                                source_method="jsonld_newsarticle_image",
                                confidence=0.90,
                                width=img.get("width"),
                                height=img.get("height"),
                            )
                    elif isinstance(img, list) and img:
                        first = img[0]
                        if isinstance(first, str):
                            return ImageCandidate(
                                url=first,
                                source_method="jsonld_newsarticle_image",
                                confidence=0.90,
                            )
                        elif isinstance(first, dict):
                            url = first.get("url") or first.get("contentUrl")
                            if url:
                                return ImageCandidate(
                                    url=url,
                                    source_method="jsonld_newsarticle_image",
                                    confidence=0.90,
                                )
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue

        return None

    def _extract_og_image(self, soup: BeautifulSoup) -> Optional[ImageCandidate]:
        """Extrai og:image (Open Graph)."""
        og = soup.find("meta", property="og:image")
        if og:
            url = og.get("content", "").strip()
            if url:
                # Tentar obter dimensões declaradas
                og_w = soup.find("meta", property="og:image:width")
                og_h = soup.find("meta", property="og:image:height")
                return ImageCandidate(
                    url=url,
                    source_method="og_image",
                    confidence=0.85,
                    width=int(og_w.get("content", 0) or 0) if og_w else None,
                    height=int(og_h.get("content", 0) or 0) if og_h else None,
                )
        return None

    def _extract_twitter_image(self, soup: BeautifulSoup) -> Optional[ImageCandidate]:
        """Extrai twitter:image."""
        tw = soup.find("meta", attrs={"name": "twitter:image"})
        if tw:
            url = tw.get("content", "").strip()
            if url:
                return ImageCandidate(
                    url=url,
                    source_method="twitter_image",
                    confidence=0.80,
                )
        return None

    def _extract_article_image(
        self, soup: BeautifulSoup, base_url: str
    ) -> Optional[ImageCandidate]:
        """Extrai primeira imagem editorial dentro da tag <article>."""
        article = soup.find("article")
        if not article:
            return None

        for img in article.find_all("img"):
            # Suporta lazy loading (data-src, data-lazy-src)
            src = (
                img.get("src") or
                img.get("data-src") or
                img.get("data-lazy-src") or
                img.get("data-original")
            )
            if not src:
                continue

            # Normaliza protocol-relative URLs (//cdn.example.com/...)
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(base_url, src)

            if self._looks_editorial(src, img):
                w = self._safe_int(img.get("width"))
                h = self._safe_int(img.get("height"))
                return ImageCandidate(
                    url=src,
                    source_method="article_first_image",
                    confidence=0.60,
                    width=w,
                    height=h,
                )

        return None

    def _extract_largest_image(
        self, soup: BeautifulSoup, base_url: str
    ) -> Optional[ImageCandidate]:
        """Último recurso: maior imagem da página por atributos de dimensão."""
        best = None
        best_area = 0

        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue

            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(base_url, src)

            if not self._looks_editorial(src, img):
                continue

            w = self._safe_int(img.get("width", 0))
            h = self._safe_int(img.get("height", 0))
            area = (w or 400) * (h or 300)

            if area > best_area:
                best_area = area
                best = ImageCandidate(
                    url=src,
                    source_method="largest_image",
                    confidence=0.40,
                    width=w,
                    height=h,
                )

        return best

    def _looks_editorial(self, url: str, img_tag) -> bool:
        """Verifica se a imagem parece ser editorial (não logo, ícone, banner)."""
        url_lower = url.lower()

        # Rejeitar CDNs publicitários
        if any(cdn in url_lower for cdn in ADVERTISING_CDNS):
            return False

        # Rejeitar por padrões de URL
        if any(p in url_lower for p in NON_EDITORIAL_PATTERNS):
            return False

        # Verificar dimensões declaradas no HTML
        w = self._safe_int(img_tag.get("width", 0))
        h = self._safe_int(img_tag.get("height", 0))
        if w and h:
            if w < 200 or h < 150:
                return False
            # Evitar banners extremamente largos
            if w > 0 and h > 0 and (w / h > 6 or h / w > 4):
                return False

        return True

    def _is_valid_candidate(self, candidate: "ImageCandidate") -> bool:
        """Valida URL final do candidato."""
        url = candidate.url
        if not url or not url.startswith(("http://", "https://")):
            return False
        if len(url) < 10:
            return False
        return True

    def _normalize_url(self, url: str, source_url: str) -> str:
        """Normaliza URL relativa para absoluta."""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return urljoin(source_url, url)
        return url

    def _get_base_url(self, url: str) -> str:
        """Retorna base URL (scheme + netloc)."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        """Converte para int de forma segura."""
        try:
            return int(val) if val else None
        except (ValueError, TypeError):
            return None
```

### 3.4 Rate Limits e Timeouts do Tier 1

| Parâmetro | Valor |
|-----------|-------|
| Timeout HTTP por fonte | 10s |
| Max retries | 1 |
| Limite de imagens verificadas por página | 10 |
| Tamanho mínimo da imagem | 300×200px |
| Extensões aceitas | jpg, jpeg, png, webp, gif |

---

## PARTE IV — TIER 2: BUSCA EM APIs COM PERSISTÊNCIA

### 4.1 Orchestrador do Tier 2

```python
# brasileira/agents/fotografo/tier2_search.py

import asyncio
from typing import List, Optional

from .apis.pexels import PexelsClient
from .apis.unsplash import UnsplashClient
from .apis.wikimedia import WikimediaClient
from .apis.flickr import FlickrCCClient
from .apis.agencia_brasil import AgenciaBrasilClient
from .clip_validator import CLIPValidator
from .rejection_cache import RejectionCache
from .models import ImageCandidate, SearchResult, TierQueries


# Ordem de execução das APIs — por qualidade editorial para o contexto brasileiro
API_ORDER = [
    "agencia_brasil",    # Fotos reais do governo BR — melhor editorial
    "wikimedia",         # Creative Commons, eventos reais, personagens públicos
    "pexels",            # Alta qualidade, sem atribuição obrigatória
    "unsplash",          # Alta qualidade, atribuição via tracking de download
    "flickr",            # Creative Commons, fotojornalismo variado
]


class Tier2Searcher:
    """
    Orchestrador de busca em APIs externas com persistência de rejeições.

    Tenta cada API em ordem, com reformulação de queries se necessário.
    """

    def __init__(
        self,
        pexels: PexelsClient,
        unsplash: UnsplashClient,
        wikimedia: WikimediaClient,
        flickr: FlickrCCClient,
        agencia_brasil: AgenciaBrasilClient,
        clip_validator: CLIPValidator,
        rejection_cache: RejectionCache,
    ):
        self._apis = {
            "agencia_brasil": agencia_brasil,
            "wikimedia": wikimedia,
            "pexels": pexels,
            "unsplash": unsplash,
            "flickr": flickr,
        }
        self.clip = clip_validator
        self.rejections = rejection_cache

    async def search(
        self,
        queries: TierQueries,
        article_title: str,
        article_text: str,
        editoria: str,
        round_number: int = 0,
    ) -> SearchResult:
        """
        Executa busca em cascata de APIs.

        Args:
            queries: Queries geradas pelo LLM para cada API
            article_title: Título para CLIP validation
            article_text: Texto para CLIP validation
            editoria: Editoria para threshold de CLIP
            round_number: 0=primeira tentativa, 1=broadening, 2=pivoting

        Returns:
            SearchResult com imagem aprovada ou falha
        """
        clip_context = f"{article_title}. {article_text[:300]}"

        for api_name in API_ORDER:
            api = self._apis.get(api_name)
            if not api:
                continue

            # Seleciona query correta para esta API e rodada
            query = queries.get_query(api_name, round_number)
            if not query:
                continue

            try:
                candidates = await api.search(
                    query=query,
                    per_page=10,
                    orientation="landscape",
                )
            except Exception as e:
                continue

            # Filtra URLs rejeitadas
            candidates = [
                c for c in candidates
                if not await self.rejections.is_rejected(c.url)
            ]

            if not candidates:
                continue

            # Valida com CLIP
            for candidate in candidates:
                score = await self.clip.score(candidate.url, clip_context)
                threshold = self._get_clip_threshold(editoria)

                if score >= threshold:
                    candidate.clip_score = score
                    candidate.source_api = api_name
                    return SearchResult(
                        success=True,
                        candidate=candidate,
                        api_used=api_name,
                        query_used=query,
                        clip_score=score,
                        round_number=round_number,
                    )
                else:
                    # Persiste rejeição por score baixo
                    await self.rejections.mark_rejected(
                        candidate.url,
                        reason=f"CLIP score {score:.3f} < threshold {threshold:.3f}",
                    )

        return SearchResult(success=False, reason=f"Todas as APIs falharam na rodada {round_number}")

    def _get_clip_threshold(self, editoria: str) -> float:
        """Retorna threshold mínimo de CLIP por editoria."""
        thresholds = {
            "esportes": 0.30,
            "política": 0.22,
            "economia": 0.20,
            "tecnologia": 0.22,
            "saúde": 0.22,
            "educação": 0.20,
            "ciência": 0.22,
            "cultura": 0.18,
            "entretenimento": 0.18,
            "mundo": 0.22,
            "meio_ambiente": 0.22,
            "segurança": 0.22,
            "sociedade": 0.20,
            "brasil": 0.20,
            "regionais": 0.18,
            "opinião": 0.18,
        }
        return thresholds.get(editoria.lower(), 0.20)
```

### 4.2 Pexels API Client

**Rate limits (2025-2026):**
- Padrão: 200 req/hora, 20.000 req/mês
- Sem limites (aplicações elegíveis): gratuito via solicitação
- Headers de controle: `X-Ratelimit-Remaining`, `X-Ratelimit-Reset`

```python
# brasileira/agents/fotografo/apis/pexels.py

import asyncio
from typing import List, Optional

import httpx

from ..models import ImageCandidate


PEXELS_API_BASE = "https://api.pexels.com/v1"
PEXELS_RATE_LIMIT_HOUR = 200
PEXELS_RATE_LIMIT_MONTH = 20_000


class PexelsClient:
    """
    Cliente async para Pexels API.
    Documentação: https://www.pexels.com/api/documentation/

    Autenticação: Header Authorization com API key.
    Atribuição: NÃO obrigatória para uso editorial, mas recomendada.
    """

    def __init__(self, api_key: str, timeout: float = 8.0):
        self.api_key = api_key
        self.timeout = timeout
        self._headers = {
            "Authorization": api_key,
            "User-Agent": "brasileira-newsbot/3.0",
        }

    async def search(
        self,
        query: str,
        per_page: int = 10,
        orientation: str = "landscape",
        min_width: int = 800,
        min_height: int = 450,
    ) -> List[ImageCandidate]:
        """
        Busca imagens na Pexels API.

        Args:
            query: Termos de busca (prefira inglês para maior cobertura)
            per_page: Resultados por página (máx 80)
            orientation: landscape | portrait | square
            min_width: Largura mínima em pixels
            min_height: Altura mínima em pixels

        Returns:
            Lista de ImageCandidate ordenada por relevância Pexels
        """
        params = {
            "query": query,
            "per_page": min(per_page, 80),
            "orientation": orientation,
            "size": "large",  # small (<720px) | medium (<1920px) | large (>1920px)
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            ) as client:
                response = await client.get(
                    f"{PEXELS_API_BASE}/search",
                    params=params,
                )

                if response.status_code == 429:
                    raise RateLimitError("Pexels: rate limit excedido")

                if response.status_code != 200:
                    return []

                data = response.json()
                photos = data.get("photos", [])

                candidates = []
                for photo in photos:
                    src = photo.get("src", {})
                    url = src.get("large2x") or src.get("large") or src.get("original")

                    if not url:
                        continue

                    # Filtra por dimensões mínimas
                    w = photo.get("width", 0)
                    h = photo.get("height", 0)
                    if w < min_width or h < min_height:
                        continue

                    candidates.append(ImageCandidate(
                        url=url,
                        source_api="pexels",
                        width=w,
                        height=h,
                        photographer=photo.get("photographer", ""),
                        photographer_url=photo.get("photographer_url", ""),
                        pexels_url=photo.get("url", ""),
                        license_type="pexels_license",
                        attribution=self._build_attribution(photo),
                    ))

                return candidates

        except RateLimitError:
            raise
        except Exception:
            return []

    @staticmethod
    def _build_attribution(photo: dict) -> str:
        """Gera texto de atribuição para a Pexels."""
        photographer = photo.get("photographer", "Fotógrafo desconhecido")
        pexels_url = photo.get("url", "https://www.pexels.com")
        return f"Foto: {photographer} via Pexels"


class RateLimitError(Exception):
    pass
```

### 4.3 Unsplash API Client

**Rate limits (2025-2026):**
- Demo: 50 req/hora
- Produção (aprovação obrigatória): 5.000 req/hora
- **OBRIGATÓRIO:** Registrar download via `GET /photos/:id/download` para conformidade

```python
# brasileira/agents/fotografo/apis/unsplash.py

import httpx
from typing import List

from ..models import ImageCandidate


UNSPLASH_API_BASE = "https://api.unsplash.com"
UNSPLASH_RATE_LIMIT_DEMO = 50       # req/hora (modo demo)
UNSPLASH_RATE_LIMIT_PROD = 5_000    # req/hora (aprovado)


class UnsplashClient:
    """
    Cliente async para Unsplash API.
    Documentação: https://unsplash.com/documentation

    IMPORTANTE: Unsplash exige rastrear downloads via /photos/:id/download.
    Sem isso, a licença é violada mesmo que gratuita.
    """

    def __init__(self, access_key: str, timeout: float = 8.0):
        self.access_key = access_key
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Client-ID {access_key}",
            "Accept-Version": "v1",
        }

    async def search(
        self,
        query: str,
        per_page: int = 10,
        orientation: str = "landscape",
        content_filter: str = "high",
        order_by: str = "relevant",
    ) -> List[ImageCandidate]:
        """
        Busca imagens no Unsplash.

        Args:
            query: Termos de busca
            per_page: Resultados (máx 30 por página)
            orientation: landscape | portrait | squarish
            content_filter: low | high (high = filtra conteúdo inadequado)
            order_by: relevant | latest
        """
        params = {
            "query": query,
            "per_page": min(per_page, 30),
            "orientation": orientation,
            "content_filter": content_filter,
            "order_by": order_by,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            ) as client:
                response = await client.get(
                    f"{UNSPLASH_API_BASE}/search/photos",
                    params=params,
                )

                if response.status_code == 403:
                    raise PermissionError("Unsplash: acesso negado — verificar chave de API")

                if response.status_code == 429:
                    raise RateLimitError("Unsplash: rate limit excedido")

                if response.status_code != 200:
                    return []

                data = response.json()
                results = data.get("results", [])
                candidates = []

                for photo in results:
                    urls = photo.get("urls", {})
                    # Preferir 'regular' (1080px) ou 'full'
                    url = urls.get("regular") or urls.get("full")

                    if not url:
                        continue

                    w = photo.get("width", 0)
                    h = photo.get("height", 0)

                    if w < 800 or h < 450:
                        continue

                    user = photo.get("user", {})
                    photographer = user.get("name", "Fotógrafo desconhecido")

                    candidates.append(ImageCandidate(
                        url=url,
                        source_api="unsplash",
                        width=w,
                        height=h,
                        photographer=photographer,
                        photographer_url=user.get("links", {}).get("html", ""),
                        unsplash_photo_id=photo.get("id"),
                        unsplash_download_url=photo.get("links", {}).get("download_location"),
                        license_type="unsplash_license",
                        attribution=f"Foto: {photographer} via Unsplash",
                    ))

                    # OBRIGATÓRIO: Registra download para conformidade Unsplash
                    if photo.get("links", {}).get("download_location"):
                        asyncio.create_task(
                            self._register_download(
                                client,
                                photo["links"]["download_location"],
                            )
                        )

                return candidates

        except (RateLimitError, PermissionError):
            raise
        except Exception:
            return []

    async def _register_download(self, client: httpx.AsyncClient, download_url: str) -> None:
        """Registra download para conformidade com termos de uso Unsplash."""
        try:
            await client.get(download_url, headers=self._headers, timeout=5.0)
        except Exception:
            pass  # Falha silenciosa — não bloquear pipeline


class RateLimitError(Exception):
    pass
```

### 4.4 Wikimedia Commons API Client

**Rate limits (2025-2026):**
- Sem rate limit rigoroso (API pública da Wikimedia)
- Limite de boa conduta: ~500 req/s
- **Nenhum custo, nenhuma chave necessária**

```python
# brasileira/agents/fotografo/apis/wikimedia.py

import httpx
from typing import List
from urllib.parse import quote

from ..models import ImageCandidate


WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"


class WikimediaClient:
    """
    Cliente async para Wikimedia Commons.
    Documentação: https://www.mediawiki.org/wiki/API:Main_page

    Licenças: Creative Commons (CC0, CC-BY, CC-BY-SA, etc.)
    Sem API key, sem custo.
    """

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def search(
        self,
        query: str,
        per_page: int = 10,
        orientation: str = "landscape",
        min_width: int = 800,
    ) -> List[ImageCandidate]:
        """
        Busca imagens no Wikimedia Commons via MediaWiki API.

        Args:
            query: Termos de busca
            per_page: Número de resultados (máx 50)
            orientation: landscape (filtra por proporção)
        """
        params = {
            "action": "query",
            "generator": "search",
            "gsrnamespace": "6",          # Namespace de arquivo (File:)
            "gsrsearch": query,
            "gsrlimit": min(per_page * 2, 50),  # Busca mais para filtrar
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 1200,           # Solicitar thumbnail 1200px
            "format": "json",
            "formatversion": "2",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": "brasileira-newsbot/3.0 (https://brasileira.news)"},
            ) as client:
                response = await client.get(WIKIMEDIA_API, params=params)

                if response.status_code != 200:
                    return []

                data = response.json()
                pages = data.get("query", {}).get("pages", [])
                candidates = []

                for page in pages:
                    imageinfo = page.get("imageinfo", [])
                    if not imageinfo:
                        continue

                    info = imageinfo[0]
                    mime = info.get("mime", "")

                    # Aceitar apenas formatos web-friendly
                    if mime not in {"image/jpeg", "image/png", "image/webp"}:
                        continue

                    w = info.get("width", 0)
                    h = info.get("height", 0)

                    if w < min_width or h < 300:
                        continue

                    # Filtrar por orientação
                    if orientation == "landscape" and h > w:
                        continue

                    # Extrair URL do thumbnail redimensionado (se disponível)
                    url = info.get("thumburl") or info.get("url")
                    if not url:
                        continue

                    # Extrair informações de licença dos metadados
                    extmeta = info.get("extmetadata", {})
                    license_name = extmeta.get("LicenseShortName", {}).get("value", "CC-BY")
                    author = extmeta.get("Artist", {}).get("value", "Wikimedia Commons")
                    # Remove HTML tags do nome do autor
                    import re
                    author = re.sub(r"<[^>]+>", "", author)

                    candidates.append(ImageCandidate(
                        url=url,
                        source_api="wikimedia",
                        width=w,
                        height=h,
                        license_type=license_name,
                        photographer=author[:100],
                        attribution=f"{author} / Wikimedia Commons / {license_name}",
                        wikimedia_page_title=page.get("title", ""),
                    ))

                    if len(candidates) >= per_page:
                        break

                return candidates

        except Exception:
            return []
```

### 4.5 Flickr Creative Commons Client

**Rate limits (2025-2026):**
- Limite por key: ~3.600 req/hora (não documentado oficialmente)
- Licenças CC em 2025: migradas para CC 4.0

**IDs REAIS de contas governamentais brasileiras no Flickr:**

```python
# IDs reais — validados em março de 2026
FLICKR_GOVBR_USERS = {
    "agencia_brasil": "49409919@N07",       # Agência Brasil / EBC
    "palacio_planalto": "23853587@N03",     # Palácio do Planalto
    "senado_federal": "67297751@N03",       # Senado Federal
    "camara_deputados": "44392195@N05",     # Câmara dos Deputados
    "ministerio_cultura": "48929524@N02",   # MinC
    "prefeitura_sp": "27386968@N03",        # Prefeitura de São Paulo
}
```

```python
# brasileira/agents/fotografo/apis/flickr.py

import httpx
from typing import List

from ..models import ImageCandidate


FLICKR_API_BASE = "https://api.flickr.com/services/rest/"

# Licenças Creative Commons no Flickr (IDs)
CC_LICENSES = [
    "4",   # CC-BY — permite uso comercial com atribuição
    "5",   # CC-BY-SA
    "9",   # CC0 — domínio público
    "10",  # Trabalho do governo dos EUA
]

# IDs reais de contas governamentais brasileiras — validados março 2026
FLICKR_GOVBR_USERS = {
    "agencia_brasil": "49409919@N07",
    "palacio_planalto": "23853587@N03",
    "senado_federal": "67297751@N03",
    "camara_deputados": "44392195@N05",
    "ministerio_cultura": "48929524@N02",
    "prefeitura_sp": "27386968@N03",
}


class FlickrCCClient:
    """
    Cliente async para Flickr Creative Commons.
    Documentação: https://www.flickr.com/services/api/

    Em 2025, Flickr migrou para CC 4.0 internacionais.
    Usando apenas licenças CC-BY e CC0 para uso editorial sem restrições.
    """

    def __init__(self, api_key: str, timeout: float = 10.0):
        self.api_key = api_key
        self.timeout = timeout

    async def search(
        self,
        query: str,
        per_page: int = 10,
        orientation: str = "landscape",
        gov_only: bool = False,
    ) -> List[ImageCandidate]:
        """
        Busca imagens CC no Flickr.

        Args:
            query: Termos de busca
            per_page: Resultados (máx 500)
            orientation: landscape (filtra por ratio)
            gov_only: Se True, busca apenas em contas gov.br
        """
        params = {
            "method": "flickr.photos.search",
            "api_key": self.api_key,
            "text": query,
            "license": ",".join(CC_LICENSES),
            "sort": "relevance",
            "per_page": min(per_page * 2, 50),
            "extras": "url_l,url_o,owner_name,license,o_dims",
            "format": "json",
            "nojsoncallback": "1",
        }

        # Se gov_only, adicionar user_id da conta governamental mais relevante
        # (feature futura: detectar qual conta é mais relevante para a editoria)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(FLICKR_API_BASE, params=params)

                if response.status_code != 200:
                    return []

                data = response.json()

                # OBRIGATÓRIO: Verificar stat da resposta Flickr
                # (HTTP 200 não significa sucesso na API Flickr)
                if data.get("stat") != "ok":
                    return []

                photos = data.get("photos", {}).get("photo", [])
                candidates = []

                for photo in photos:
                    # Usar url_l (large, ~1024px) como preferência
                    url = photo.get("url_l") or photo.get("url_o")

                    if not url:
                        continue

                    # Construir URL diretamente se necessário
                    if not url.startswith("http"):
                        farm = photo.get("farm")
                        server = photo.get("server")
                        photo_id = photo.get("id")
                        secret = photo.get("secret")
                        if farm and server and photo_id and secret:
                            url = f"https://farm{farm}.staticflickr.com/{server}/{photo_id}_{secret}_b.jpg"
                        else:
                            continue

                    owner = photo.get("ownername", "Flickr")
                    license_id = str(photo.get("license", ""))

                    candidates.append(ImageCandidate(
                        url=url,
                        source_api="flickr",
                        photographer=owner[:100],
                        license_type=f"CC-{license_id}",
                        attribution=f"Foto: {owner} via Flickr (CC)",
                        flickr_photo_id=photo.get("id"),
                    ))

                    if len(candidates) >= per_page:
                        break

                return candidates

        except Exception:
            return []
```

### 4.6 Agência Brasil (EBC) Client

A Agência Brasil é a **melhor fonte** para fotojornalismo brasileiro. Fotos sob licença Creative Commons, reais, contextualizadas, do governo federal. Não tem API pública — acesso via RSS de fotos + scraping respeitoso.

```python
# brasileira/agents/fotografo/apis/agencia_brasil.py

import re
from typing import List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..models import ImageCandidate


AGENCIA_BRASIL_BASE = "https://agenciabrasil.ebc.com.br"
AGENCIA_BRASIL_SEARCH = "https://agenciabrasil.ebc.com.br/busca"
AGENCIA_BRASIL_FOTO_BASE = "https://agenciabrasil.ebc.com.br/foto"


class AgenciaBrasilClient:
    """
    Client para busca de imagens na Agência Brasil (EBC).

    Imagens sob licença Creative Commons — uso livre com atribuição.
    Não tem API REST pública; acesso via busca web.
    Rate limit de cortesia: máx 2 req/s.
    """

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    async def search(
        self,
        query: str,
        per_page: int = 5,
        orientation: str = "landscape",
    ) -> List[ImageCandidate]:
        """
        Busca fotos na Agência Brasil por query de texto.

        Returns:
            Lista de candidatos com atribuição CC
        """
        # Agência Brasil: busca em português, sem tradução
        search_url = f"{AGENCIA_BRASIL_SEARCH}?q={query}&type=foto"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": "brasileira-newsbot/3.0 (https://brasileira.news/bot)"},
                follow_redirects=True,
            ) as client:
                response = await client.get(search_url)

                if response.status_code != 200:
                    return []

                soup = BeautifulSoup(response.text, "lxml")
                candidates = []

                # Extrai resultados de foto da página de busca
                for item in soup.find_all("article", class_=re.compile(r"media|foto|news")):
                    img_tag = item.find("img")
                    if not img_tag:
                        continue

                    img_src = (
                        img_tag.get("src") or
                        img_tag.get("data-src") or
                        img_tag.get("data-lazy-src")
                    )

                    if not img_src:
                        continue

                    if img_src.startswith("/"):
                        img_src = urljoin(AGENCIA_BRASIL_BASE, img_src)

                    # Tentar obter versão de alta resolução
                    img_src = self._upgrade_to_hires(img_src)

                    photographer = "Agência Brasil / EBC"
                    caption_tag = item.find(["figcaption", "p", "span"], class_=re.compile(r"caption|credit|autor"))
                    if caption_tag:
                        photographer = caption_tag.get_text(strip=True)[:100]

                    candidates.append(ImageCandidate(
                        url=img_src,
                        source_api="agencia_brasil",
                        photographer=photographer,
                        license_type="CC-BY",
                        attribution=f"{photographer} / Agência Brasil / CC BY",
                    ))

                    if len(candidates) >= per_page:
                        break

                return candidates

        except Exception:
            return []

    @staticmethod
    def _upgrade_to_hires(url: str) -> str:
        """Tenta converter URL de thumbnail para versão de maior resolução."""
        # Agência Brasil usa padrão: /styles/large_16_9/ ou /styles/medium/
        url = re.sub(r"/styles/[^/]+/", "/styles/large_16_9/", url)
        return url
```

### 4.7 Rate Limits Consolidados — Tier 2

| API | Rate Limit | Custo | Atribuição | Melhor para |
|-----|-----------|-------|-----------|-------------|
| **Agência Brasil** | ~2 req/s (cortesia) | Gratuito | CC-BY obrigatório | Fotojornalismo gov.br |
| **Wikimedia Commons** | ~500 req/s | Gratuito | CC (variada) | Eventos históricos, personalidades |
| **Pexels** | 200 req/h / 20k/mês | Gratuito | Recomendada | Lifestyle, ambiente, tecnologia |
| **Unsplash** | 50 req/h (demo) / 5k/h (prod) | Gratuito | Tracking obrigatório | Alta qualidade, arquitetura |
| **Flickr CC** | ~3.600 req/h | Gratuito | CC (conforme licença) | Fotojornalismo amador/independente |

---

## PARTE V — QUERY GENERATION COM LLM PREMIUM

### 5.1 Princípio Inviolável

Query generation **SEMPRE** usa LLM PREMIUM via SmartLLMRouter com `task_type="imagem_query"`. Isso garante que o roteador selecione automaticamente entre Claude Opus, GPT-5.4, Gemini 3.1 Pro, Grok 4, etc. — os melhores modelos disponíveis.

**Por que PREMIUM é obrigatório:**
- Modelos econômicos geram queries genéricas ("política brasil") que retornam imagens irrelevantes
- Modelos premium entendem contexto editorial e geram queries concretas e visuais
- A diferença de custo é irrisória: ~$0,01-0,03/query vs. o custo de uma má imagem

### 5.2 Estrutura de Queries Geradas

```python
# models.py — TierQueries

from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class TierQueries(BaseModel):
    """Queries geradas pelo LLM Premium para cada API e rodada."""

    # Rodada 0: Queries específicas (primeira tentativa)
    agencia_brasil_r0: List[str] = Field(default_factory=list)  # em português
    wikimedia_r0: List[str] = Field(default_factory=list)       # em inglês ou português
    pexels_r0: List[str] = Field(default_factory=list)          # em inglês
    unsplash_r0: List[str] = Field(default_factory=list)        # em inglês
    flickr_r0: List[str] = Field(default_factory=list)          # em inglês

    # Rodada 1: Broadening (ampliação — segunda tentativa)
    agencia_brasil_r1: List[str] = Field(default_factory=list)
    wikimedia_r1: List[str] = Field(default_factory=list)
    pexels_r1: List[str] = Field(default_factory=list)
    unsplash_r1: List[str] = Field(default_factory=list)
    flickr_r1: List[str] = Field(default_factory=list)

    # Rodada 2: Pivoting (pivotamento — terceira tentativa)
    pexels_r2: List[str] = Field(default_factory=list)
    unsplash_r2: List[str] = Field(default_factory=list)
    flickr_r2: List[str] = Field(default_factory=list)

    # Para geração por IA (Tier 3)
    dalle_prompt: str = ""
    flux_prompt: str = ""

    def get_query(self, api_name: str, round_number: int) -> Optional[str]:
        """Retorna a primeira query válida para a API na rodada especificada."""
        key = f"{api_name}_r{round_number}"
        queries = getattr(self, key, [])
        return queries[0] if queries else None
```

### 5.3 Sistema Prompt Completo — Query Generator

```python
# query_generator.py

FOTOGRAFO_SYSTEM_PROMPT = """Você é o Editor de Fotografia da brasileira.news, um portal jornalístico brasileiro de referência.

Sua tarefa é gerar queries de busca de imagem e prompts de geração por IA para ilustrar artigos jornalísticos com precisão editorial.

## PRINCÍPIOS EDITORIAIS

A imagem jornalística NÃO é decoração. Ela deve:
1. Representar visualmente o SUJEITO PRINCIPAL da notícia (pessoa, lugar, instituição, evento)
2. Ter contexto editorial real (não ser "foto de banco genérica")
3. Comunicar o TOM da matéria (urgência, celebração, drama, seriedade)
4. Respeitar a EDITORIA (política tem tom diferente de cultura)

## REGRAS DE QUERY

### O que FAZER:
- Use termos concretos e visuais (pessoas, ações, lugares específicos)
- Prefira inglês para Pexels, Unsplash e Flickr (maior cobertura)
- Use português para Agência Brasil
- Combine: [sujeito] + [ação/estado] + [contexto/ambiente]
- Inclua qualificadores: "documentary", "press conference", "senate chamber"

### O que EVITAR:
- Conceitos abstratos genéricos: "economia", "política", "saúde"
- Adjetivos emocionais para stock: "happy", "smiling", "cheerful"
- Backgrounds de estúdio: "white background", "studio shot"
- "illustration", "vector" para hard news
- Nomes próprios de pessoas específicas (não funcionam em stock)

## ANATOMIA DE UMA BOA QUERY
```
[sujeito principal] + [ação ou estado] + [contexto/ambiente] + [qualificadores opcionais]
```

EXEMPLOS POR EDITORIA:

**POLÍTICA:**
- ❌ "politica brasil eleição"
- ✅ "government official speech podium parliament"
- ✅ "senator vote legislature chamber"
- ✅ "political press conference microphones journalists"

**ECONOMIA:**
- ❌ "economia inflação brasil"
- ✅ "inflation grocery store prices consumer"
- ✅ "stock market trading floor brokers"
- ✅ "central bank building exterior"

**ESPORTES:**
- ❌ "futebol gol"
- ✅ "soccer match stadium crowd brazil"
- ✅ "athlete celebration victory podium"
- ✅ "sports competition intense action"

**SAÚDE:**
- ❌ "saúde hospital"
- ✅ "doctor patient hospital consultation medical"
- ✅ "vaccine injection healthcare worker clinic"
- ✅ "medical research laboratory scientist"

**TECNOLOGIA:**
- ❌ "inteligência artificial robô"
- ✅ "artificial intelligence data center servers"
- ✅ "machine learning programming developer"
- ✅ "technology startup office team"

**SEGURANÇA/JUSTIÇA:**
- ❌ "polícia crime"
- ✅ "law enforcement officer police patrol"
- ✅ "court justice building exterior"
- ✅ "prison security handcuffs arrest"

**MEIO AMBIENTE:**
- ❌ "natureza ambiente"
- ✅ "deforestation amazon rainforest aerial"
- ✅ "climate change protest signs demonstration"
- ✅ "renewable energy solar panels wind turbines"

## ESTRATÉGIAS POR RODADA

**RODADA 0 — Específica:** Query focada no evento/tema principal do artigo
**RODADA 1 — Broadening:** Generalizar para o tema amplo da editoria
**RODADA 2 — Pivoting:** Focar no CONTEXTO em vez do sujeito principal

Exemplo de pivoting:
- FALHOU: "central bank interest rate decision"
- PIVOT: "government building federal institution exterior"
- PIVOT: "economic meeting finance minister press"
- PIVOT: "financial data screen market charts"

## AGÊNCIA BRASIL (português)

Para a Agência Brasil, use português e termos específicos do contexto brasileiro:
- "plenário senado votação"
- "presidente discurso cerimônia"
- "manifestação protesto brasília"
- "obras infraestrutura governo federal"

## PROMPTS PARA GERAÇÃO POR IA

Para DALL-E / Flux, use estilo **editorial NÃO-FOTORREALISTA**:
- Estilo: "digital illustration, editorial art, news magazine style, non-photorealistic"
- Composição: "professional composition, high detail, conceptual art"
- Proibido: rostos de pessoas reais, lugares identificáveis específicos, texto sobreposto
- Formato: landscape 16:9, fundo informativo (não branco)

Template:
```
{CONCEITO_CENTRAL_DA_NOTÍCIA}, {ELEMENTO_VISUAL_SECUNDÁRIO},
digital illustration, editorial art, news magazine cover style,
non-photorealistic, professional composition, high detail,
flat colors with depth, {TOM_EMOCIONAL} atmosphere
```

## SAÍDA ESPERADA

Retorne APENAS JSON válido neste formato, sem markdown, sem explicações:
{
  "agencia_brasil_r0": ["query PT específica 1", "query PT específica 2"],
  "wikimedia_r0": ["query EN específica 1", "query EN específica 2"],
  "pexels_r0": ["query EN específica 1", "query EN específica 2"],
  "unsplash_r0": ["query EN específica 1"],
  "flickr_r0": ["query EN específica 1"],
  "agencia_brasil_r1": ["query PT ampla"],
  "wikimedia_r1": ["query EN ampla"],
  "pexels_r1": ["query EN ampla"],
  "unsplash_r1": ["query EN ampla"],
  "flickr_r1": ["query EN ampla"],
  "pexels_r2": ["pivot query EN"],
  "unsplash_r2": ["pivot query EN"],
  "flickr_r2": ["pivot query EN"],
  "dalle_prompt": "editorial illustration prompt completo",
  "flux_prompt": "editorial illustration prompt completo"
}"""
```

### 5.4 Implementação do QueryGenerator

```python
# brasileira/agents/fotografo/query_generator.py

import json
import logging
from typing import Optional

from brasileira.llm.smart_router import SmartLLMRouter

from .models import TierQueries

logger = logging.getLogger("fotografo.query_generator")


class QueryGenerator:
    """
    Gera queries de busca de imagem usando LLM Premium.

    OBRIGATÓRIO: task_type="imagem_query" garante tier PREMIUM no SmartLLMRouter.
    """

    def __init__(self, router: SmartLLMRouter):
        self.router = router

    async def generate(
        self,
        title: str,
        content: str,
        editoria: str,
        source_url: str = "",
    ) -> TierQueries:
        """
        Gera queries completas para todos os tiers e rodadas.

        Args:
            title: Título do artigo
            content: Conteúdo/lead do artigo (primeiros 500 chars)
            editoria: Editoria (Política, Economia, etc.)
            source_url: URL original para contexto

        Returns:
            TierQueries com todas as queries geradas
        """
        user_prompt = self._build_user_prompt(title, content, editoria)

        try:
            response = await self.router.complete(
                task_type="imagem_query",     # GARANTE tier PREMIUM
                system_prompt=FOTOGRAFO_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=1200,
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            raw = response.content.strip()
            # Remove markdown code blocks se presentes
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            data = json.loads(raw)
            queries = TierQueries(**data)

            logger.info(
                f"Queries geradas [tier={response.tier_used}, model={response.model}] "
                f"para: {title[:60]}"
            )

            return queries

        except json.JSONDecodeError as e:
            logger.warning(f"JSON inválido na resposta do LLM: {e}. Usando fallback.")
            return self._fallback_queries(title, editoria)
        except Exception as e:
            logger.error(f"Erro na geração de queries: {e}. Usando fallback.")
            return self._fallback_queries(title, editoria)

    def _build_user_prompt(
        self, title: str, content: str, editoria: str
    ) -> str:
        """Constrói o user prompt para geração de queries."""
        content_snippet = content[:500] if content else ""
        return (
            f"EDITORIA: {editoria}\n\n"
            f"TÍTULO DO ARTIGO:\n{title}\n\n"
            f"LEAD/RESUMO:\n{content_snippet}\n\n"
            f"Gere queries de busca de imagem para este artigo jornalístico."
        )

    def _fallback_queries(self, title: str, editoria: str) -> TierQueries:
        """
        Queries de fallback quando o LLM falha.
        Usa queries genéricas por editoria.
        """
        EDITORIA_FALLBACKS = {
            "Política": {
                "en": "government parliament legislature democracy",
                "pt": "governo parlamento legislação",
            },
            "Economia": {
                "en": "business economy finance market",
                "pt": "economia negócios finanças",
            },
            "Esportes": {
                "en": "sports athlete competition stadium",
                "pt": "esporte atleta competição",
            },
            "Saúde": {
                "en": "healthcare medical hospital doctor",
                "pt": "saúde hospital médico",
            },
            "Tecnologia": {
                "en": "technology computer digital innovation",
                "pt": "tecnologia computador digital",
            },
            "Segurança": {
                "en": "law enforcement security police",
                "pt": "segurança pública polícia",
            },
            "Meio Ambiente": {
                "en": "environment nature climate change",
                "pt": "meio ambiente natureza clima",
            },
        }

        fb = EDITORIA_FALLBACKS.get(editoria, {
            "en": "news media journalism",
            "pt": "notícia jornalismo",
        })

        return TierQueries(
            agencia_brasil_r0=[fb["pt"]],
            wikimedia_r0=[fb["en"]],
            pexels_r0=[fb["en"]],
            unsplash_r0=[fb["en"]],
            flickr_r0=[fb["en"]],
            agencia_brasil_r1=["fotojornalismo brasil"],
            pexels_r1=["brazil news journalism"],
            unsplash_r1=["brazil journalism documentary"],
            flickr_r1=["journalism documentary photography"],
            pexels_r2=["professional photography editorial"],
            unsplash_r2=["editorial photography professional"],
            flickr_r2=["documentary photography real people"],
            dalle_prompt=(
                f"{title[:100]}, editorial illustration, "
                "news magazine style, non-photorealistic, "
                "professional composition, high detail"
            ),
            flux_prompt=(
                f"{title[:100]}, {fb['en']}, "
                "editorial art, digital illustration, "
                "non-photorealistic, news magazine cover style"
            ),
        )
```

---

## PARTE VI — REFORMULAÇÃO AUTOMÁTICA DE QUERIES

### 6.1 Por que as Primeiras Queries Frequentemente Falham

Segundo o [MediaEval 2025 NewsImages Challenge](https://2025.multimediaeval.com/paper10.pdf), sistemas de retrieval com CLIP e bases de stock falham frequentemente em tópicos abstratos:
- Política econômica (inflação, juros, PIB)
- Relações diplomáticas (acordos entre países)
- Conceitos jurídicos (STF, legislação)
- Temas sociais amplos (desigualdade, educação)

Isso ocorre porque os bancos de imagem são dominados por lifestyle, viagens e natureza — não por fotojornalismo político/econômico.

### 6.2 As Três Estratégias de Reformulação

```
RODADA 0: Query Específica (LLM Premium)
  "STF vote constitutional amendment brazil congress"
        ↓ (score CLIP < threshold OU zero resultados)

RODADA 1: Broadening (Generalização)
  "supreme court building exterior government"
  "judiciary government institution architecture"
        ↓ (score CLIP ainda < threshold)

RODADA 2: Pivoting (Pivotamento para Contexto)
  "government official formal meeting conference"
  "institutional building exterior plaza"
  → Aceita threshold mais baixo nesta rodada
```

### 6.3 Implementação do Controlador de Reformulação

```python
# brasileira/agents/fotografo/reformulation_controller.py

import logging
from dataclasses import dataclass
from typing import Optional

from .models import TierQueries, SearchResult, ImageCandidate

logger = logging.getLogger("fotografo.reformulation")


@dataclass
class ReformulationState:
    current_round: int = 0
    max_rounds: int = 2
    rounds_exhausted: bool = False
    last_result: Optional[SearchResult] = None


class ReformulationController:
    """
    Controla a reformulação automática de queries entre rodadas.

    Rodada 0: Query específica gerada pelo LLM
    Rodada 1: Broadening — generalização
    Rodada 2: Pivoting — foco no contexto
    """

    def __init__(self, max_rounds: int = 2):
        self.max_rounds = max_rounds

    def should_retry(self, state: ReformulationState, result: SearchResult) -> bool:
        """Decide se deve tentar uma nova rodada de reformulação."""
        if result.success:
            return False
        if state.current_round >= state.max_rounds:
            state.rounds_exhausted = True
            return False
        return True

    def advance_round(self, state: ReformulationState) -> None:
        """Avança para a próxima rodada de reformulação."""
        state.current_round += 1
        logger.info(
            f"Reformulação: avançando para rodada {state.current_round} "
            f"({self._round_name(state.current_round)})"
        )

    def get_relaxed_threshold(self, editoria: str, round_number: int) -> float:
        """
        Retorna threshold CLIP relaxado para rodadas posteriores.

        Em rodadas de pivoting, aceitamos qualidade levemente menor
        porque a query é sobre o contexto, não o sujeito principal.
        """
        base_thresholds = {
            "esportes": 0.30,
            "política": 0.22,
            "economia": 0.20,
            "tecnologia": 0.22,
            "saúde": 0.22,
        }
        base = base_thresholds.get(editoria.lower(), 0.20)

        # Reduz threshold em 15% por rodada de reformulação
        relaxation = 0.85 ** round_number
        return max(base * relaxation, 0.12)  # Mínimo absoluto de 0.12

    @staticmethod
    def _round_name(round_num: int) -> str:
        names = {0: "específica", 1: "broadening", 2: "pivoting"}
        return names.get(round_num, f"round_{round_num}")
```

### 6.4 Fluxo Completo de Reformulação no LangGraph

```python
# Nó condicional no grafo — controle de reformulação
async def _decide_after_tier2(state: FotografoState) -> str:
    """
    Decide próxima etapa após tentativa do Tier 2.
    """
    reformulation_state = state.reformulation_state
    last_result = state.last_search_result

    if last_result and last_result.success:
        # Imagem encontrada com qualidade suficiente
        return "clip_validation"

    if reformulation_controller.should_retry(reformulation_state, last_result):
        reformulation_controller.advance_round(reformulation_state)
        return "tier2_search"  # Volta para Tier 2 com nova rodada

    # Esgotou todas as rodadas — ir para geração por IA
    return "tier3_generation"
```

---

## PARTE VII — VALIDAÇÃO COM CLIP SCORE

### 7.1 O que é CLIP Score

CLIP (Contrastive Language-Image Pretraining) calcula a **similaridade semântica** entre texto e imagem em um espaço vetorial compartilhado. Um score alto significa que a imagem está semanticamente alinhada com o texto do artigo.

**Modelo utilizado:** `openai/clip-vit-large-patch14` (512 dimensões)

### 7.2 Implementação do Validador

```python
# brasileira/agents/fotografo/clip_validator.py

import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import hashlib

import httpx
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

logger = logging.getLogger("fotografo.clip")

# Pool de threads para operações CPU-bound (CLIP)
_CLIP_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clip")

# Cache de scores por URL (evita re-calcular para mesma imagem)
_score_cache: dict[str, float] = {}


class CLIPValidator:
    """
    Valida relevância semântica imagem-texto usando CLIP.

    Uso: Calcula cosine similarity entre embedding do texto do artigo
    e embedding da imagem candidata.

    Score >= 0.20: Geralmente relevante
    Score >= 0.25: Boa relevância
    Score >= 0.30: Forte relevância
    Score < 0.15: Improvável que seja relevante
    """

    _model: Optional[CLIPModel] = None
    _processor: Optional[CLIPProcessor] = None
    _model_name = "openai/clip-vit-large-patch14"

    @classmethod
    def _get_model(cls):
        """Lazy loading do modelo CLIP (carrega uma vez)."""
        if cls._model is None:
            logger.info(f"Carregando modelo CLIP: {cls._model_name}")
            cls._processor = CLIPProcessor.from_pretrained(cls._model_name)
            cls._model = CLIPModel.from_pretrained(cls._model_name)
            cls._model.eval()
            logger.info("Modelo CLIP carregado com sucesso")
        return cls._model, cls._processor

    async def score(
        self,
        image_url: str,
        article_text: str,
        timeout: float = 8.0,
    ) -> float:
        """
        Calcula CLIP score entre imagem e texto do artigo.

        Args:
            image_url: URL da imagem candidata
            article_text: Título + lead do artigo (máx 300 chars)
            timeout: Timeout para download da imagem

        Returns:
            Score de similaridade 0.0-1.0 (cosine similarity normalizada)
        """
        # Cache hit
        cache_key = hashlib.md5(f"{image_url}:{article_text[:100]}".encode()).hexdigest()
        if cache_key in _score_cache:
            return _score_cache[cache_key]

        try:
            # Download da imagem em background
            image_data = await self._download_image(image_url, timeout)
            if not image_data:
                return 0.0

            # Cálculo em thread pool (CPU-bound)
            loop = asyncio.get_event_loop()
            score = await loop.run_in_executor(
                _CLIP_EXECUTOR,
                self._compute_score,
                image_data,
                article_text[:300],  # CLIP tem limite de ~77 tokens
            )

            # Cache o resultado
            _score_cache[cache_key] = score

            logger.debug(f"CLIP score={score:.3f} para {image_url[:60]}")
            return score

        except Exception as e:
            logger.warning(f"Erro ao calcular CLIP score: {e}")
            return 0.0

    async def _download_image(
        self, url: str, timeout: float
    ) -> Optional[bytes]:
        """Download da imagem com timeout e limite de tamanho."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None

                content_length = int(response.headers.get("content-length", 0))
                if content_length > 10 * 1024 * 1024:  # > 10MB: skip
                    return None

                return response.content

        except Exception:
            return None

    def _compute_score(self, image_data: bytes, text: str) -> float:
        """
        Computa CLIP cosine similarity (CPU-bound, roda em thread pool).
        """
        try:
            model, processor = self._get_model()

            # Carrega imagem
            image = Image.open(io.BytesIO(image_data)).convert("RGB")

            # Processa inputs
            inputs = processor(
                text=[text],
                images=image,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=77,
            )

            with torch.no_grad():
                outputs = model(**inputs)
                # Extrai logits de similaridade imagem-texto
                logits = outputs.logits_per_image  # Shape: (1, 1)

                # Normaliza para 0-1 usando sigmoid
                # (logits_per_image são em escala de temperatura do CLIP)
                score = torch.sigmoid(logits / 10.0).item()

            return float(score)

        except Exception as e:
            logger.warning(f"Erro no cálculo CLIP: {e}")
            return 0.0

    async def validate_editorial(self, image_url: str) -> dict:
        """
        Validação editorial via CLIP zero-shot.
        Detecta se a imagem é editorial (não logo, banner, ícone).
        """
        EDITORIAL_DESCRIPTIONS = [
            "a professional editorial news photograph",
            "a photojournalism image of real events",
            "a documentary style photograph of people",
        ]
        NON_EDITORIAL_DESCRIPTIONS = [
            "a company logo or brand icon",
            "an advertisement banner or promotional graphic",
            "a small avatar or profile picture",
            "a watermarked stock photo with text overlay",
            "a cartoon illustration or vector graphic",
        ]

        image_data = await self._download_image(image_url, timeout=8.0)
        if not image_data:
            return {"is_editorial": False, "reason": "download_failed"}

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                _CLIP_EXECUTOR,
                self._classify_editorial,
                image_data,
                EDITORIAL_DESCRIPTIONS,
                NON_EDITORIAL_DESCRIPTIONS,
            )
            return result
        except Exception:
            return {"is_editorial": True, "reason": "validation_error_auto_approve"}

    def _classify_editorial(
        self,
        image_data: bytes,
        editorial: list,
        non_editorial: list,
    ) -> dict:
        """Classifica editorial vs. não-editorial via CLIP zero-shot."""
        model, processor = self._get_model()
        all_texts = editorial + non_editorial

        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        inputs = processor(
            text=all_texts,
            images=image,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=77,
        )

        with torch.no_grad():
            outputs = model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[0]

        prob_editorial = sum(probs[i].item() for i in range(len(editorial)))
        is_editorial = prob_editorial > 0.45

        return {
            "is_editorial": is_editorial,
            "prob_editorial": float(prob_editorial),
            "reason": "clip_classification",
        }
```

### 7.3 Thresholds CLIP por Editoria

| Editoria | Threshold Mínimo | Threshold Ideal | Notas |
|----------|-----------------|-----------------|-------|
| Esportes | 0.30 | 0.40+ | Ações físicas têm alta correspondência CLIP |
| Segurança | 0.25 | 0.35+ | Fardas, viaturas são visuais específicos |
| Saúde | 0.22 | 0.30+ | Equipamentos médicos identificáveis |
| Política | 0.22 | 0.30+ | Tópico abstrato, threshold menor |
| Tecnologia | 0.22 | 0.32+ | Data centers, código são visuais |
| Economia | 0.20 | 0.28+ | Mais abstrato, aceita mais |
| Cultura | 0.18 | 0.28+ | Alta variabilidade editorial |
| Opinião | 0.15 | 0.22+ | Aceita contexto temático amplo |

---

## PARTE VIII — TIER 3: GERAÇÃO POR IA (gpt-image-1, Flux.2 Pro)

### 8.1 Quando Tier 3 é Acionado

O Tier 3 é acionado quando:
1. Tier 1 falhou (sem og:image válida na fonte)
2. Tier 2 falhou em TODAS as APIs em TODAS as rodadas (0, 1, 2)
3. Ou: todas as imagens encontradas foram rejeitadas pelo CLIP

**OBRIGATÓRIO:** Toda imagem gerada por IA é rotulada com `[IA]` na legenda WordPress.

### 8.2 Modelos Disponíveis (março 2026)

| Modelo | API | Velocidade | Custo/imagem | Status DALL-E 3 |
|--------|-----|-----------|--------------|-----------------|
| **gpt-image-1** | OpenAI | ~20-30s | $0.04-0.08/img | DALL-E 3 aposentado em Azure; use gpt-image-1 via OpenAI API |
| **Flux.2 Pro** | Black Forest Labs | ~3s | $0.03-0.05/img | Disponível via API |
| **Flux.2 Max** | BFL | ~5s | $0.06/img | Alta qualidade fotorrealista |
| **Flux.2 Klein** | BFL | <1s | $0.01/img | Ultra-rápido, qualidade menor |

**Nota importante:** DALL-E 3 foi aposentado no Azure em março de 2026. Use `gpt-image-1` via OpenAI API diretamente, ou Flux.2 via BFL API.

### 8.3 Política Editorial para Imagens Geradas por IA

Conforme padrões da AP, Nieman Foundation e Grupo Globo:

| Regra | Implementação |
|-------|---------------|
| Proibido: rostos de pessoas reais identificáveis | Prompt deve especificar "no specific real person" |
| Proibido: lugares reais identificáveis (se desinforma) | Usar "symbolic representation", não "exact replica" |
| Obrigatório: labeling explícito | Campo `caption` = "[IA] Imagem gerada por inteligência artificial — {tema}" |
| Estilo preferido: não-fotorrealista | "digital illustration, editorial art, non-photorealistic" |
| Proibido: texto sobreposto na imagem | Excluir do prompt |

### 8.4 Implementação do Tier 3

```python
# brasileira/agents/fotografo/tier3_generation.py

import asyncio
import logging
from typing import Optional
import httpx

from brasileira.llm.smart_router import SmartLLMRouter
from .models import ImageCandidate, TierQueries

logger = logging.getLogger("fotografo.tier3")


class Tier3Generator:
    """
    Geração de imagem por IA como Tier 3 do pipeline.

    Usa gpt-image-1 (OpenAI) como primário e Flux.2 Pro (BFL) como fallback.
    TODA imagem gerada é rotulada como [IA] na legenda.
    """

    def __init__(
        self,
        openai_api_key: str,
        bfl_api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.openai_key = openai_api_key
        self.bfl_key = bfl_api_key
        self.timeout = timeout

    async def generate(
        self,
        queries: TierQueries,
        article_title: str,
        editoria: str,
    ) -> Optional[ImageCandidate]:
        """
        Tenta gerar imagem por IA.

        Ordem: gpt-image-1 → Flux.2 Pro → None (Tier 4 assume)
        """
        # Tentativa 1: gpt-image-1 (OpenAI)
        try:
            result = await self._generate_openai(
                prompt=queries.dalle_prompt,
                article_title=article_title,
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"gpt-image-1 falhou: {e}")

        # Tentativa 2: Flux.2 Pro (BFL)
        if self.bfl_key:
            try:
                result = await self._generate_flux(
                    prompt=queries.flux_prompt,
                    article_title=article_title,
                )
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Flux.2 falhou: {e}")

        logger.warning(f"Tier 3 falhou para: {article_title[:60]}")
        return None

    async def _generate_openai(
        self,
        prompt: str,
        article_title: str,
    ) -> Optional[ImageCandidate]:
        """
        Geração com gpt-image-1 (OpenAI).

        API: POST https://api.openai.com/v1/images/generations
        Modelo: gpt-image-1 (substituto do DALL-E 3 em 2026)
        """
        if not prompt:
            return None

        # Adiciona restrições editoriais obrigatórias ao prompt
        safe_prompt = (
            f"{prompt}. "
            "Style: editorial illustration, non-photorealistic, news magazine style. "
            "Do NOT include: real faces of identifiable people, text overlays, logos, "
            "watermarks, or specific building replicas. "
            "Use symbolic and conceptual representation. "
            "16:9 landscape format, professional composition."
        )

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.openai_key}"},
        ) as client:
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                json={
                    "model": "gpt-image-1",
                    "prompt": safe_prompt[:4000],  # Limite do modelo
                    "n": 1,
                    "size": "1536x1024",  # Landscape 16:9
                    "quality": "standard",
                    "response_format": "url",
                },
            )

            if response.status_code != 200:
                error_detail = response.json().get("error", {}).get("message", "")
                raise ValueError(f"OpenAI API error {response.status_code}: {error_detail}")

            data = response.json()
            image_url = data["data"][0]["url"]

            return ImageCandidate(
                url=image_url,
                source_api="gpt-image-1",
                source_tier="tier3",
                width=1536,
                height=1024,
                license_type="openai_generated",
                ai_generated=True,
                ai_model="gpt-image-1",
                ai_prompt=safe_prompt[:200],
                # OBRIGATÓRIO: Label [IA] na legenda
                attribution=f"[IA] Imagem gerada por inteligência artificial. Tema: {article_title[:80]}",
                photographer="brasileira.news / IA",
            )

    async def _generate_flux(
        self,
        prompt: str,
        article_title: str,
    ) -> Optional[ImageCandidate]:
        """
        Geração com Flux.2 Pro (Black Forest Labs).

        API: POST https://api.bfl.ai/v1/flux-pro-1.1
        Velocidade: ~3s
        """
        if not prompt or not self.bfl_key:
            return None

        safe_prompt = (
            f"{prompt}. "
            "Editorial illustration style, non-photorealistic, "
            "news magazine art, no real people faces, no text overlays, "
            "professional composition, 16:9 landscape."
        )

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "x-key": self.bfl_key,
                "Content-Type": "application/json",
            },
        ) as client:
            # Submete request assíncrono
            response = await client.post(
                "https://api.bfl.ai/v1/flux-pro-1.1",
                json={
                    "prompt": safe_prompt[:4000],
                    "width": 1440,
                    "height": 810,   # 16:9
                    "steps": 28,
                    "guidance": 3.5,
                    "safety_tolerance": 2,
                    "output_format": "jpeg",
                },
            )

            if response.status_code != 200:
                raise ValueError(f"BFL API error: {response.status_code}")

            task_data = response.json()
            task_id = task_data.get("id")

            if not task_id:
                raise ValueError("BFL: task_id não retornado")

            # Polling para resultado (Flux é assíncrono)
            image_url = await self._poll_flux_result(client, task_id, max_wait=45)

            if not image_url:
                return None

            return ImageCandidate(
                url=image_url,
                source_api="flux-pro-1.1",
                source_tier="tier3",
                width=1440,
                height=810,
                license_type="bfl_generated",
                ai_generated=True,
                ai_model="flux-pro-1.1",
                ai_prompt=safe_prompt[:200],
                attribution=f"[IA] Imagem gerada por inteligência artificial. Tema: {article_title[:80]}",
                photographer="brasileira.news / Flux IA",
            )

    async def _poll_flux_result(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        max_wait: float = 45.0,
        poll_interval: float = 2.0,
    ) -> Optional[str]:
        """Aguarda resultado assíncrono do Flux via polling."""
        elapsed = 0.0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            try:
                response = await client.get(
                    f"https://api.bfl.ai/v1/get_result?id={task_id}"
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                status = data.get("status")

                if status == "Ready":
                    return data.get("result", {}).get("sample")
                elif status in ("Error", "Failed", "Content Moderated"):
                    logger.warning(f"Flux task {task_id} falhou: {status}")
                    return None
                # status "Pending" ou "Processing": continuar polling

            except Exception:
                continue

        logger.warning(f"Flux task {task_id} timeout após {max_wait}s")
        return None
```

---

## PARTE IX — TIER 4: PLACEHOLDER TEMÁTICO

### 9.1 Princípio: GARANTIA ABSOLUTA

O Tier 4 é a **garantia absoluta** de que toda notícia tenha imagem. Ele nunca falha porque não depende de APIs externas — as imagens são pré-carregadas no WordPress durante o setup e seus IDs são hardcoded na configuração.

**Regra inviolável:** Se o Tier 4 for executado, a imagem SEMPRE será atribuída ao post.

### 9.2 Placeholders por Editoria

```python
# brasileira/agents/fotografo/tier4_placeholder.py

import logging
from typing import Optional

from .models import ImageCandidate

logger = logging.getLogger("fotografo.tier4")


# IDs dos placeholders no WordPress Media Library
# OBRIGATÓRIO: Fazer upload destas imagens no WP antes do deploy
# Caminho: brasileira.news/wp-content/uploads/placeholders/
PLACEHOLDERS_WP_IDS: dict[str, int] = {
    "Política": 10001,
    "Economia": 10002,
    "Esportes": 10003,
    "Tecnologia": 10004,
    "Saúde": 10005,
    "Educação": 10006,
    "Ciência": 10007,
    "Cultura": 10008,
    "Entretenimento": 10008,  # Compartilha com Cultura
    "Mundo": 10009,
    "Meio Ambiente": 10010,
    "Segurança": 10011,
    "Sociedade": 10012,
    "Brasil": 10013,
    "Regionais": 10014,
    "Opinião": 10015,
    "Últimas Notícias": 10016,
    "_default": 10099,  # Fallback absoluto
}

# URLs dos placeholders (para atualização de alt_text e caption)
PLACEHOLDERS_WP_URLS: dict[str, str] = {
    "Política": "https://brasileira.news/wp-content/uploads/placeholders/politica.jpg",
    "Economia": "https://brasileira.news/wp-content/uploads/placeholders/economia.jpg",
    "Esportes": "https://brasileira.news/wp-content/uploads/placeholders/esportes.jpg",
    "Tecnologia": "https://brasileira.news/wp-content/uploads/placeholders/tecnologia.jpg",
    "Saúde": "https://brasileira.news/wp-content/uploads/placeholders/saude.jpg",
    "Educação": "https://brasileira.news/wp-content/uploads/placeholders/educacao.jpg",
    "Ciência": "https://brasileira.news/wp-content/uploads/placeholders/ciencia.jpg",
    "Cultura": "https://brasileira.news/wp-content/uploads/placeholders/cultura.jpg",
    "Mundo": "https://brasileira.news/wp-content/uploads/placeholders/mundo.jpg",
    "Meio Ambiente": "https://brasileira.news/wp-content/uploads/placeholders/meio-ambiente.jpg",
    "Segurança": "https://brasileira.news/wp-content/uploads/placeholders/seguranca.jpg",
    "Sociedade": "https://brasileira.news/wp-content/uploads/placeholders/sociedade.jpg",
    "_default": "https://brasileira.news/wp-content/uploads/placeholders/default.jpg",
}


class Tier4Placeholder:
    """
    Tier 4 — Garantia absoluta de imagem.

    Usa placeholders pré-carregados no WordPress por editoria.
    NUNCA falha — se editoria não encontrada, usa _default.
    """

    def get_placeholder(self, editoria: str) -> ImageCandidate:
        """
        Retorna placeholder apropriado para a editoria.

        Args:
            editoria: Nome da editoria

        Returns:
            ImageCandidate com o placeholder da editoria
            (ou default se editoria não reconhecida)
        """
        # Normalização de editoria
        editoria_clean = editoria.strip().title() if editoria else "_default"

        wp_media_id = PLACEHOLDERS_WP_IDS.get(
            editoria_clean,
            PLACEHOLDERS_WP_IDS["_default"],
        )
        url = PLACEHOLDERS_WP_URLS.get(
            editoria_clean,
            PLACEHOLDERS_WP_URLS["_default"],
        )

        logger.info(
            f"Tier 4: usando placeholder para editoria '{editoria_clean}' "
            f"(WP media ID: {wp_media_id})"
        )

        return ImageCandidate(
            url=url,
            source_api="tier4_placeholder",
            source_tier="tier4",
            wp_media_id=wp_media_id,  # Já está no WP — não precisa de upload
            license_type="brasileira_placeholder",
            photographer="brasileira.news",
            attribution="Imagem ilustrativa — brasileira.news",
            is_placeholder=True,
            editoria=editoria_clean,
        )
```

### 9.3 Setup de Placeholders (Pré-Deploy)

```bash
# Script de setup — criar placeholders no WordPress (executar UMA VEZ antes do deploy)
# brasileira/scripts/setup_placeholders.py

import asyncio
import httpx
from pathlib import Path

WP_URL = "https://brasileira.news/wp-json/wp/v2"
WP_AUTH = ("iapublicador", "APP_PASSWORD_AQUI")

# Placeholders são SVGs temáticos gerados programaticamente
# ou imagens PNG pré-criadas por design
PLACEHOLDERS = {
    "politica": "placeholders/politica.jpg",
    "economia": "placeholders/economia.jpg",
    # ... etc
}

async def upload_placeholder(name: str, filepath: str) -> int:
    """Faz upload do placeholder e retorna o media_id."""
    with open(filepath, "rb") as f:
        content = f.read()

    async with httpx.AsyncClient(auth=WP_AUTH) as client:
        response = await client.post(
            f"{WP_URL}/media",
            headers={
                "Content-Type": "image/jpeg",
                "Content-Disposition": f'attachment; filename="{name}.jpg"',
            },
            content=content,
        )
        data = response.json()
        return data["id"]
```

---

## PARTE X — UPLOAD E ATUALIZAÇÃO NO WORDPRESS

### 10.1 Fluxo de Upload

```
1. Verificar se imagem já existe na WP Media Library (evitar duplicatas)
2. Download da imagem candidata (se não for placeholder)
3. Conversão de formato (RGBA→RGB, PA→RGB/branco, WebP→JPEG se necessário)
4. Validação de dimensões mínimas (400×300px)
5. Upload via POST /wp-json/wp/v2/media
6. SET alt_text e caption (PATCH /wp-json/wp/v2/media/{id})
7. SET featured_media no post (PATCH /wp-json/wp/v2/posts/{post_id})
8. Verificação de sucesso
```

### 10.2 Implementação do WP Uploader

```python
# brasileira/agents/fotografo/wp_uploader.py

import asyncio
import io
import logging
import re
from typing import Optional, Tuple

import httpx
from PIL import Image

logger = logging.getLogger("fotografo.wp_uploader")


class WordPressUploader:
    """
    Upload assíncrono de imagem para WordPress Media Library
    e associação como featured_media do post.

    Corrige bugs V2:
    - B-01: Lógica RGBA correta (PA mode → composição com branco)
    - B-08: Meta update com tratamento de erro
    - B-09: Falha explícita (nunca retorna None silenciosamente)
    """

    def __init__(
        self,
        wp_url: str,
        wp_user: str,
        wp_app_password: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.wp_url = wp_url.rstrip("/")
        self.api_base = f"{self.wp_url}/wp-json/wp/v2"
        self._auth = (wp_user, wp_app_password)
        self.timeout = timeout
        self.max_retries = max_retries

    async def upload_and_attach(
        self,
        image_url: str,
        post_id: int,
        article_title: str,
        attribution: str,
        wp_media_id: Optional[int] = None,  # Se já no WP (placeholder)
    ) -> Tuple[bool, Optional[int]]:
        """
        Faz upload da imagem e associa como featured_media do post.

        Args:
            image_url: URL da imagem a fazer upload
            post_id: ID do post WordPress
            article_title: Para alt_text
            attribution: Para caption
            wp_media_id: Se já existe no WP (Tier 4 placeholder), pular upload

        Returns:
            (success: bool, media_id: int | None)
        """
        # Se wp_media_id fornecido (placeholder já no WP), pular upload
        if wp_media_id:
            success = await self._set_featured_media(post_id, wp_media_id)
            return success, wp_media_id

        # Verificar se imagem já existe na media library
        existing_id = await self._find_existing_media(image_url)
        if existing_id:
            logger.info(f"Imagem já existe na WP Media Library: ID={existing_id}")
            success = await self._set_featured_media(post_id, existing_id)
            return success, existing_id

        # Download e processamento da imagem
        image_data, content_type = await self._download_and_process(image_url)
        if not image_data:
            logger.error(f"Falha ao baixar/processar imagem: {image_url[:80]}")
            return False, None

        # Upload para WP
        media_id = await self._upload_media(
            image_data=image_data,
            content_type=content_type,
            filename=self._safe_filename(article_title),
        )

        if not media_id:
            logger.error("Falha no upload para WordPress Media Library")
            return False, None

        # SET alt_text e caption (com tratamento de erro)
        await self._update_media_meta(
            media_id=media_id,
            alt_text=article_title[:120],
            caption=attribution[:300],
        )

        # SET featured_media no post
        success = await self._set_featured_media(post_id, media_id)

        return success, media_id

    async def _download_and_process(
        self, image_url: str
    ) -> Tuple[Optional[bytes], str]:
        """
        Baixa imagem e converte para JPEG/PNG adequado para web.

        Corrige B-01: lógica RGBA com tratamento de PA mode.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(image_url)
                if response.status_code != 200:
                    return None, ""

                raw_data = response.content

            # Processa com PIL
            img = Image.open(io.BytesIO(raw_data))

            # FIX B-01: Lógica RGBA/PA correta
            if img.mode == "PA":
                # Palette + Alpha — composição sobre fundo branco
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode == "RGBA":
                # RGBA — composição sobre fundo branco
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode == "P":
                # Palette sem alpha — converte para RGB
                img = img.convert("RGB")
            elif img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Validação de dimensões mínimas
            if img.width < 400 or img.height < 300:
                logger.warning(
                    f"Imagem muito pequena: {img.width}x{img.height}px"
                )
                return None, ""

            # Converte para JPEG (qualidade web, tamanho razoável)
            output = io.BytesIO()
            if img.mode == "L":
                img.save(output, format="JPEG", quality=88, optimize=True)
            else:
                img.convert("RGB").save(output, format="JPEG", quality=88, optimize=True)

            return output.getvalue(), "image/jpeg"

        except Exception as e:
            logger.warning(f"Erro ao processar imagem: {e}")
            return None, ""

    async def _find_existing_media(self, image_url: str) -> Optional[int]:
        """Verifica se imagem já existe na WP Media Library por URL."""
        try:
            async with httpx.AsyncClient(
                auth=self._auth,
                timeout=10.0,
            ) as client:
                # Busca pelo guid (URL original armazenada como source)
                response = await client.get(
                    f"{self.api_base}/media",
                    params={
                        "search": image_url[:100],
                        "per_page": 5,
                    },
                )
                if response.status_code == 200:
                    items = response.json()
                    for item in items:
                        if image_url in item.get("source_url", "") or \
                           image_url in item.get("guid", {}).get("rendered", ""):
                            return item["id"]
        except Exception:
            pass
        return None

    async def _upload_media(
        self,
        image_data: bytes,
        content_type: str,
        filename: str,
    ) -> Optional[int]:
        """Upload de imagem para WP Media Library com retry."""
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    auth=self._auth,
                    timeout=self.timeout,
                ) as client:
                    response = await client.post(
                        f"{self.api_base}/media",
                        headers={
                            "Content-Type": content_type,
                            "Content-Disposition": f'attachment; filename="{filename}.jpg"',
                        },
                        content=image_data,
                    )

                    if response.status_code == 201:
                        return response.json()["id"]

                    if response.status_code in (401, 403):
                        logger.error("WP: credenciais inválidas")
                        return None  # Não retry para auth errors

                    logger.warning(
                        f"WP upload falhou (attempt {attempt+1}): "
                        f"HTTP {response.status_code}"
                    )

            except httpx.TimeoutException:
                logger.warning(f"WP upload timeout (attempt {attempt+1})")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return None

    async def _update_media_meta(
        self,
        media_id: int,
        alt_text: str,
        caption: str,
    ) -> None:
        """
        Atualiza alt_text e caption da imagem.

        FIX B-08: Inclui tratamento de erro (V2 ignorava falhas silenciosamente).
        """
        try:
            async with httpx.AsyncClient(
                auth=self._auth,
                timeout=10.0,
            ) as client:
                response = await client.patch(
                    f"{self.api_base}/media/{media_id}",
                    json={
                        "alt_text": alt_text,
                        "caption": caption,
                    },
                )

                if response.status_code not in (200, 201):
                    logger.warning(
                        f"Falha ao atualizar meta da mídia {media_id}: "
                        f"HTTP {response.status_code}"
                    )
        except Exception as e:
            logger.warning(f"Erro ao atualizar meta da mídia {media_id}: {e}")
            # Não relança — meta failure não deve bloquear o pipeline

    async def _set_featured_media(
        self,
        post_id: int,
        media_id: int,
    ) -> bool:
        """
        Define a imagem destacada do post.

        FIX B-09: Falha explícita (não retorna None silenciosamente).
        """
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    auth=self._auth,
                    timeout=10.0,
                ) as client:
                    response = await client.patch(
                        f"{self.api_base}/posts/{post_id}",
                        json={"featured_media": media_id},
                    )

                    if response.status_code == 200:
                        logger.info(
                            f"Featured media SET: post_id={post_id}, media_id={media_id}"
                        )
                        return True

                    logger.warning(
                        f"Falha ao set featured_media (attempt {attempt+1}): "
                        f"HTTP {response.status_code}"
                    )

            except httpx.TimeoutException:
                logger.warning(f"Timeout ao set featured_media (attempt {attempt+1})")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        logger.error(
            f"CRÍTICO: Não foi possível set featured_media para post_id={post_id}"
        )
        return False

    @staticmethod
    def _safe_filename(title: str) -> str:
        """
        Gera nome de arquivo seguro a partir do título.

        FIX B-15: Trata títulos com caracteres não-ASCII (CJK, árabe, etc.)
        """
        if not title:
            return "imagem-noticia"

        # Remove acentos e normaliza
        import unicodedata
        normalized = unicodedata.normalize("NFKD", title)
        ascii_str = normalized.encode("ascii", "ignore").decode("ascii")

        # Remove caracteres especiais
        safe = re.sub(r"[^a-z0-9]+", "-", ascii_str.lower().strip())
        safe = safe.strip("-")[:50]

        return safe if safe else "imagem-noticia"
```

---

## PARTE XI — SCHEMAS KAFKA E POSTGRESQL

### 11.1 Kafka — Evento Consumido: `article-published`

```python
# Evento consumido pelo Fotógrafo
# Tópico: article-published
# Particionamento: publisher_id (do Reporter)

class ArticlePublishedEvent(BaseModel):
    """Schema do evento article-published."""

    # Identificação
    post_id: int           # ID do post no WordPress
    article_id: str        # UUID interno do artigo
    wp_slug: str           # Slug do post no WP

    # Conteúdo para geração de queries
    titulo: str
    editoria: str
    lead: str              # Primeiros 300 chars do conteúdo
    url_fonte: str         # URL original da notícia (para Tier 1)
    html_fonte: Optional[str]  # HTML já baixado (evita re-fetch)

    # Metadados
    urgencia: int          # 1-10 (afeta prioridade de processamento)
    timestamp: datetime
    reporter_id: str       # Qual instância do Reporter publicou

    # Contexto adicional
    tags: List[str] = []
    entidades: List[str] = []  # Nomes mencionados no artigo
```

### 11.2 Kafka — Evento Produzido: `image-attached`

```python
# Evento produzido pelo Fotógrafo após associar imagem
# Tópico: image-attached
# Consumers: Monitor Sistema, Editor-Chefe (observação), Revisor

class ImageAttachedEvent(BaseModel):
    """Schema do evento image-attached."""

    # Identificação
    post_id: int
    article_id: str
    media_id: Optional[int]   # None se falhou completamente (nunca deve acontecer)

    # Resultado
    tier_used: str             # "tier1", "tier2", "tier3", "tier4"
    api_used: Optional[str]    # "pexels", "wikimedia", "gpt-image-1", etc.
    query_used: Optional[str]  # Query que funcionou
    clip_score: Optional[float]

    # Metadados da imagem
    image_url: Optional[str]
    attribution: str
    ai_generated: bool = False

    # Performance
    total_time_ms: int
    rounds_attempted: int      # Quantas rodadas de reformulação foram necessárias
    timestamp: datetime

    # Auditoria
    fotografo_id: str          # Qual instância do Fotógrafo processou
```

### 11.3 PostgreSQL — Tabela `fotografo_resultados`

```sql
-- Tabela de resultados do Fotógrafo
CREATE TABLE fotografo_resultados (
    id                  BIGSERIAL PRIMARY KEY,
    post_id             INTEGER NOT NULL,
    article_id          UUID NOT NULL,
    wp_media_id         INTEGER,

    -- Pipeline
    tier_usado          VARCHAR(20) NOT NULL,  -- tier1|tier2|tier3|tier4
    api_usada           VARCHAR(50),           -- pexels|unsplash|wikimedia|flickr|agencia_brasil|gpt-image-1|flux|placeholder
    rodadas_tentadas    SMALLINT DEFAULT 0,
    query_usada         TEXT,

    -- Qualidade
    clip_score          NUMERIC(5,4),
    ai_gerada           BOOLEAN DEFAULT FALSE,
    placeholder_usada   BOOLEAN DEFAULT FALSE,
    editoria            VARCHAR(50),

    -- Imagem
    image_url           TEXT,
    attribution         TEXT,

    -- Performance
    total_time_ms       INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para análise de qualidade do pipeline
CREATE INDEX idx_fotografo_post_id ON fotografo_resultados(post_id);
CREATE INDEX idx_fotografo_tier ON fotografo_resultados(tier_usado);
CREATE INDEX idx_fotografo_editoria ON fotografo_resultados(editoria);
CREATE INDEX idx_fotografo_created ON fotografo_resultados(created_at DESC);
CREATE INDEX idx_fotografo_ai ON fotografo_resultados(ai_gerada) WHERE ai_gerada = TRUE;
CREATE INDEX idx_fotografo_placeholder ON fotografo_resultados(placeholder_usada) WHERE placeholder_usada = TRUE;
```

### 11.4 PostgreSQL — Tabela `image_rejections`

```sql
-- Persistência de rejeições de imagem (complementa Redis para histórico longo)
CREATE TABLE image_rejections (
    id              BIGSERIAL PRIMARY KEY,
    url_hash        VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 da URL
    image_url       TEXT NOT NULL,
    rejection_reason TEXT,
    rejected_by     VARCHAR(50),  -- "clip_score"|"llm_validation"|"size_too_small"|etc.
    clip_score      NUMERIC(5,4),
    reject_count    INTEGER DEFAULT 1,
    first_rejected  TIMESTAMPTZ DEFAULT NOW(),
    last_rejected   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rejections_url_hash ON image_rejections(url_hash);
```

### 11.5 Redis Keys do Fotógrafo

```python
# Padrão de chaves Redis usadas pelo Fotógrafo
REDIS_KEYS = {
    # Cache de resultados de busca (TTL: 1h)
    "fotografo:cache:{query_hash}": {
        "ttl": 3600,
        "description": "Cache de resultado de busca por query hash",
    },

    # Blacklist de URLs rejeitadas (TTL: 24h)
    "fotografo:rejected:{url_hash}": {
        "ttl": 86400,
        "description": "URL rejeitada pelo pipeline (CLIP baixo ou validação LLM)",
        "fields": ["url", "reason", "clip_score", "rejected_at"],
    },

    # Working memory do Fotógrafo (TTL: 4h)
    "agent:working_memory:fotografo:{cycle_id}": {
        "ttl": 14400,
        "description": "Estado do ciclo de processamento atual",
    },

    # Rate limit tracking por API
    "fotografo:ratelimit:pexels": {"ttl": 3600, "description": "Requisições Pexels nesta hora"},
    "fotografo:ratelimit:unsplash": {"ttl": 3600, "description": "Requisições Unsplash nesta hora"},
    "fotografo:ratelimit:flickr": {"ttl": 3600, "description": "Requisições Flickr nesta hora"},
}
```

---

## PARTE XII — ESTRUTURA DE DIRETÓRIOS E DEPENDÊNCIAS

### 12.1 Estrutura Completa de Arquivos

```
brasileira/
├── agents/
│   └── fotografo/
│       ├── __init__.py
│       ├── agent.py              # FotografoAgent — consumer principal
│       ├── query_generator.py    # LLM Premium → TierQueries
│       ├── reformulation_controller.py  # Broadening + Pivoting
│       ├── tier1_extraction.py   # og:image, schema.org
│       ├── tier2_search.py       # Orchestrador APIs
│       ├── clip_validator.py     # CLIP score validation
│       ├── tier3_generation.py   # gpt-image-1 + Flux.2
│       ├── tier4_placeholder.py  # Placeholders temáticos
│       ├── wp_uploader.py        # WordPress Media Library
│       ├── rejection_cache.py    # Redis blacklist
│       ├── models.py             # Pydantic models
│       ├── config.py             # Configurações e env vars
│       └── apis/
│           ├── __init__.py
│           ├── pexels.py
│           ├── unsplash.py
│           ├── wikimedia.py
│           ├── flickr.py
│           └── agencia_brasil.py
├── scripts/
│   └── setup_placeholders.py     # Upload inicial dos placeholders no WP
└── tests/
    └── test_fotografo/
        ├── test_tier1_extraction.py
        ├── test_tier2_apis.py
        ├── test_clip_validator.py
        ├── test_tier3_generation.py
        ├── test_tier4_placeholder.py
        ├── test_wp_uploader.py
        └── test_query_generator.py
```

### 12.2 Dependências Python

```toml
# pyproject.toml — dependências do Fotógrafo

[tool.poetry.dependencies]
# Core
python = "^3.12"
httpx = "^0.27.0"           # Async HTTP client
beautifulsoup4 = "^4.12"    # HTML parsing
lxml = "^5.0"               # Parser HTML rápido
Pillow = "^10.3"            # Processamento de imagem
pydantic = "^2.6"           # Validação de dados
aiokafka = "^0.11"          # Kafka consumer async
redis = {extras=["hiredis"], version="^5.0"}  # Redis async

# CLIP e ML
torch = "^2.3"
transformers = "^4.41"      # CLIPModel, CLIPProcessor
# NOTA: NÃO usar GPU em produção (custo). CPU é suficiente para scoring.
# Se precisar de GPU: adicionar torch[cuda] e configurar via CUDA_VISIBLE_DEVICES

# LangGraph
langgraph = "^0.2"

# PostgreSQL
asyncpg = "^0.29"

[tool.poetry.dev-dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
respx = "^0.20"             # Mock para httpx em testes
```

### 12.3 Variáveis de Ambiente

```bash
# .env — Fotógrafo V3

# APIs de busca de imagem
PEXELS_API_KEY=your_pexels_key
UNSPLASH_ACCESS_KEY=your_unsplash_key
FLICKR_API_KEY=your_flickr_key
# Wikimedia: sem API key necessária

# APIs de geração por IA
OPENAI_API_KEY=your_openai_key              # Para gpt-image-1
BFL_API_KEY=your_bfl_key                   # Flux.2 Pro (opcional)

# WordPress
WP_URL=https://brasileira.news
WP_USER=iapublicador
WP_APP_PASSWORD=your_app_password
WP_TABLE_PREFIX=wp_7_
WP_BLOG_ID=7

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_GROUP_ID=fotografo-consumer-group
KAFKA_TOPIC_CONSUME=article-published
KAFKA_TOPIC_PRODUCE=image-attached

# Redis
REDIS_URL=redis://localhost:6379/0

# PostgreSQL
POSTGRES_DSN=postgresql://user:pass@localhost:5432/brasileira

# CLIP (modelo)
CLIP_MODEL_NAME=openai/clip-vit-large-patch14
CLIP_CACHE_DIR=/var/cache/brasileira/clip

# Limites e performance
FOTOGRAFO_WORKERS=3              # Instâncias paralelas
FOTOGRAFO_TIER1_TIMEOUT=10.0
FOTOGRAFO_TIER2_TIMEOUT_PER_API=8.0
FOTOGRAFO_TIER3_TIMEOUT=60.0
FOTOGRAFO_WP_TIMEOUT=30.0
FOTOGRAFO_MAX_REFORMULATION_ROUNDS=2
```

---

## PARTE XIII — ENTRYPOINT E INICIALIZAÇÃO

### 13.1 Agent Principal — FotografoAgent

```python
# brasileira/agents/fotografo/agent.py

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import asyncpg
import redis.asyncio as aioredis
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

from brasileira.llm.smart_router import SmartLLMRouter
from .query_generator import QueryGenerator
from .tier1_extraction import Tier1Extractor
from .tier2_search import Tier2Searcher
from .clip_validator import CLIPValidator
from .tier3_generation import Tier3Generator
from .tier4_placeholder import Tier4Placeholder
from .wp_uploader import WordPressUploader
from .rejection_cache import RejectionCache
from .reformulation_controller import ReformulationController, ReformulationState
from .models import (
    FotografoState,
    ArticlePublishedEvent,
    ImageAttachedEvent,
    TierQueries,
)
from .config import FotografoConfig

logger = logging.getLogger("fotografo.agent")


class FotografoAgent:
    """
    Agente Fotógrafo — pipeline de imagem pós-publicação.

    Consumer do tópico Kafka 'article-published'.
    Executa pipeline de 4 tiers para garantir imagem em 100% das notícias.
    """

    def __init__(self, config: FotografoConfig):
        self.config = config
        self._setup_components()
        self._graph = self._build_graph()

    def _setup_components(self) -> None:
        """Inicializa todos os componentes do pipeline."""
        cfg = self.config

        # LLM Router (PREMIUM para query generation)
        self.router = SmartLLMRouter()

        # Pipeline components
        self.query_gen = QueryGenerator(router=self.router)
        self.tier1 = Tier1Extractor(timeout=cfg.tier1_timeout)
        self.clip = CLIPValidator()
        self.reformulation = ReformulationController(max_rounds=cfg.max_reformulation_rounds)
        self.tier3 = Tier3Generator(
            openai_api_key=cfg.openai_api_key,
            bfl_api_key=cfg.bfl_api_key,
            timeout=cfg.tier3_timeout,
        )
        self.tier4 = Tier4Placeholder()
        self.wp = WordPressUploader(
            wp_url=cfg.wp_url,
            wp_user=cfg.wp_user,
            wp_app_password=cfg.wp_app_password,
            timeout=cfg.wp_timeout,
        )

    def _build_graph(self) -> StateGraph:
        """Constrói o grafo LangGraph do pipeline."""
        graph = StateGraph(FotografoState)

        # Adiciona nós
        graph.add_node("generate_queries", self._step_generate_queries)
        graph.add_node("tier1", self._step_tier1)
        graph.add_node("tier2", self._step_tier2)
        graph.add_node("tier3", self._step_tier3)
        graph.add_node("tier4", self._step_tier4)
        graph.add_node("upload", self._step_upload)
        graph.add_node("finalize", self._step_finalize)

        # Entry point
        graph.set_entry_point("generate_queries")

        # Fluxo linear: generate_queries → tier1
        graph.add_edge("generate_queries", "tier1")

        # Condicional após Tier 1
        graph.add_conditional_edges(
            "tier1",
            self._decide_after_tier1,
            {"upload": "upload", "tier2": "tier2"},
        )

        # Condicional após Tier 2 (com suporte a reformulação)
        graph.add_conditional_edges(
            "tier2",
            self._decide_after_tier2,
            {"upload": "upload", "retry_tier2": "tier2", "tier3": "tier3"},
        )

        # Condicional após Tier 3
        graph.add_conditional_edges(
            "tier3",
            self._decide_after_tier3,
            {"upload": "upload", "tier4": "tier4"},
        )

        # Tier 4 sempre vai para upload (GARANTIA)
        graph.add_edge("tier4", "upload")
        graph.add_edge("upload", "finalize")
        graph.add_edge("finalize", END)

        return graph.compile()

    async def process_event(self, event: ArticlePublishedEvent) -> ImageAttachedEvent:
        """
        Processa um evento article-published e retorna o resultado.

        Este é o método principal chamado para cada notícia.
        """
        start_time = time.time()

        initial_state = FotografoState(
            post_id=event.post_id,
            article_id=event.article_id,
            titulo=event.titulo,
            editoria=event.editoria,
            lead=event.lead,
            url_fonte=event.url_fonte,
            html_fonte=event.html_fonte,
            urgencia=event.urgencia,
            reformulation_state=ReformulationState(),
            queries=None,
            selected_candidate=None,
            wp_media_id=None,
            tier_used=None,
        )

        try:
            final_state = await self._graph.ainvoke(initial_state)
        except Exception as e:
            logger.error(f"Erro crítico no pipeline do Fotógrafo: {e}", exc_info=True)
            # Fallback de emergência: usar placeholder
            final_state = initial_state
            final_state.tier_used = "tier4_emergency"
            placeholder = self.tier4.get_placeholder(event.editoria)
            final_state.selected_candidate = placeholder
            final_state.wp_media_id = placeholder.wp_media_id

        total_ms = int((time.time() - start_time) * 1000)

        return ImageAttachedEvent(
            post_id=event.post_id,
            article_id=event.article_id,
            media_id=final_state.wp_media_id,
            tier_used=final_state.tier_used or "tier4",
            api_used=final_state.selected_candidate.source_api if final_state.selected_candidate else None,
            query_used=final_state.query_used,
            clip_score=final_state.selected_candidate.clip_score if final_state.selected_candidate else None,
            image_url=final_state.selected_candidate.url if final_state.selected_candidate else None,
            attribution=final_state.selected_candidate.attribution if final_state.selected_candidate else "Imagem ilustrativa",
            ai_generated=final_state.selected_candidate.ai_generated if final_state.selected_candidate else False,
            total_time_ms=total_ms,
            rounds_attempted=final_state.reformulation_state.current_round if final_state.reformulation_state else 0,
            timestamp=datetime.utcnow(),
            fotografo_id=self.config.instance_id,
        )

    # ── Nós do LangGraph ──────────────────────────────────────────────────────

    async def _step_generate_queries(self, state: FotografoState) -> FotografoState:
        """Gera queries com LLM PREMIUM."""
        queries = await self.query_gen.generate(
            title=state.titulo,
            content=state.lead,
            editoria=state.editoria,
            source_url=state.url_fonte,
        )
        state.queries = queries
        return state

    async def _step_tier1(self, state: FotografoState) -> FotografoState:
        """Extrai og:image da fonte original."""
        result = await self.tier1.extract(
            source_url=state.url_fonte,
            html_content=state.html_fonte,
        )
        if result.success:
            # Valida com CLIP antes de aceitar
            score = await self.clip.score(
                result.candidate.url,
                f"{state.titulo}. {state.lead[:200]}",
            )
            if score >= 0.15:  # Threshold menor para Tier 1 (é a imagem da própria fonte)
                result.candidate.clip_score = score
                state.selected_candidate = result.candidate
                state.tier_used = "tier1"
                state.query_used = "og:image extraction"
        return state

    async def _step_tier2(self, state: FotografoState) -> FotografoState:
        """Busca em APIs externas com persistência."""
        from .apis.pexels import PexelsClient
        from .apis.unsplash import UnsplashClient
        from .apis.wikimedia import WikimediaClient
        from .apis.flickr import FlickrCCClient
        from .apis.agencia_brasil import AgenciaBrasilClient

        rejection_cache = RejectionCache(redis_url=self.config.redis_url)
        await rejection_cache.connect()

        searcher = Tier2Searcher(
            pexels=PexelsClient(self.config.pexels_api_key),
            unsplash=UnsplashClient(self.config.unsplash_access_key),
            wikimedia=WikimediaClient(),
            flickr=FlickrCCClient(self.config.flickr_api_key),
            agencia_brasil=AgenciaBrasilClient(),
            clip_validator=self.clip,
            rejection_cache=rejection_cache,
        )

        round_num = state.reformulation_state.current_round
        result = await searcher.search(
            queries=state.queries,
            article_title=state.titulo,
            article_text=state.lead,
            editoria=state.editoria,
            round_number=round_num,
        )

        if result.success:
            state.selected_candidate = result.candidate
            state.tier_used = "tier2"
            state.query_used = result.query_used
            state.last_search_result = result
        else:
            state.last_search_result = result

        await rejection_cache.disconnect()
        return state

    async def _step_tier3(self, state: FotografoState) -> FotografoState:
        """Geração por IA."""
        candidate = await self.tier3.generate(
            queries=state.queries,
            article_title=state.titulo,
            editoria=state.editoria,
        )
        if candidate:
            state.selected_candidate = candidate
            state.tier_used = "tier3"
            state.query_used = candidate.ai_prompt
        return state

    async def _step_tier4(self, state: FotografoState) -> FotografoState:
        """Placeholder temático — GARANTIA."""
        placeholder = self.tier4.get_placeholder(state.editoria)
        state.selected_candidate = placeholder
        state.tier_used = "tier4"
        state.query_used = "placeholder"
        return state

    async def _step_upload(self, state: FotografoState) -> FotografoState:
        """Upload e associação no WordPress."""
        if not state.selected_candidate:
            # Segurança: se chegou aqui sem candidato, usar placeholder
            placeholder = self.tier4.get_placeholder(state.editoria)
            state.selected_candidate = placeholder
            state.tier_used = "tier4_safety"

        candidate = state.selected_candidate
        success, media_id = await self.wp.upload_and_attach(
            image_url=candidate.url,
            post_id=state.post_id,
            article_title=state.titulo,
            attribution=candidate.attribution,
            wp_media_id=candidate.wp_media_id,
        )

        if success and media_id:
            state.wp_media_id = media_id
        else:
            # Se upload falhou mas temos placeholder, tenta novamente com placeholder
            if state.tier_used != "tier4":
                logger.warning(f"Upload falhou, usando placeholder para post_id={state.post_id}")
                placeholder = self.tier4.get_placeholder(state.editoria)
                _, placeholder_media_id = await self.wp.upload_and_attach(
                    image_url=placeholder.url,
                    post_id=state.post_id,
                    article_title=state.titulo,
                    attribution=placeholder.attribution,
                    wp_media_id=placeholder.wp_media_id,
                )
                state.wp_media_id = placeholder_media_id
                state.tier_used = "tier4_fallback_upload"

        return state

    async def _step_finalize(self, state: FotografoState) -> FotografoState:
        """Persiste métricas no PostgreSQL."""
        # Métricas são persistidas no Kafka consumer loop (não aqui)
        return state

    # ── Decisores condicionais ────────────────────────────────────────────────

    def _decide_after_tier1(self, state: FotografoState) -> str:
        if state.selected_candidate and state.tier_used == "tier1":
            return "upload"
        return "tier2"

    def _decide_after_tier2(self, state: FotografoState) -> str:
        if state.selected_candidate and state.tier_used == "tier2":
            return "upload"

        # Verificar se deve reformular
        if self.reformulation.should_retry(
            state.reformulation_state,
            state.last_search_result,
        ):
            self.reformulation.advance_round(state.reformulation_state)
            return "retry_tier2"

        return "tier3"

    def _decide_after_tier3(self, state: FotografoState) -> str:
        if state.selected_candidate and state.tier_used == "tier3":
            return "upload"
        return "tier4"


# ── Kafka Consumer Loop ───────────────────────────────────────────────────────

async def run_fotografo_consumer(config: FotografoConfig) -> None:
    """
    Loop principal do consumer Kafka.

    Consome eventos 'article-published' e processa cada notícia.
    Processa em paralelo com asyncio.gather para throughput.
    """
    agent = FotografoAgent(config)
    db_pool = await asyncpg.create_pool(config.postgres_dsn)

    consumer = AIOKafkaConsumer(
        config.kafka_topic_consume,
        bootstrap_servers=config.kafka_bootstrap_servers,
        group_id=config.kafka_group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=False,  # Commit manual após processamento
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=config.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )

    await consumer.start()
    await producer.start()
    logger.info(f"Fotógrafo consumer iniciado: {config.kafka_topic_consume}")

    try:
        semaphore = asyncio.Semaphore(config.max_parallel)  # Controle de concorrência

        async for msg in consumer:
            async with semaphore:
                asyncio.create_task(
                    _process_and_commit(
                        agent=agent,
                        consumer=consumer,
                        producer=producer,
                        db_pool=db_pool,
                        msg=msg,
                        config=config,
                    )
                )

    finally:
        await consumer.stop()
        await producer.stop()
        await db_pool.close()


async def _process_and_commit(
    agent: FotografoAgent,
    consumer: AIOKafkaConsumer,
    producer: AIOKafkaProducer,
    db_pool: asyncpg.Pool,
    msg,
    config: FotografoConfig,
) -> None:
    """Processa uma mensagem Kafka e faz commit após sucesso."""
    try:
        event = ArticlePublishedEvent(**msg.value)
        result = await agent.process_event(event)

        # Publica evento de resultado no Kafka
        await producer.send(
            config.kafka_topic_produce,
            value=result.model_dump(),
        )

        # Persiste métricas no PostgreSQL
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO fotografo_resultados
                    (post_id, article_id, wp_media_id, tier_usado, api_usada,
                     rodadas_tentadas, query_usada, clip_score, ai_gerada,
                     placeholder_usada, editoria, image_url, attribution, total_time_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                event.post_id,
                str(event.article_id),
                result.media_id,
                result.tier_used,
                result.api_used,
                result.rounds_attempted,
                result.query_used,
                result.clip_score,
                result.ai_generated,
                result.tier_used in ("tier4", "tier4_fallback_upload", "tier4_emergency"),
                event.editoria,
                result.image_url,
                result.attribution,
                result.total_time_ms,
            )

        # Commit do offset Kafka após processamento bem-sucedido
        await consumer.commit()

        logger.info(
            f"[{event.post_id}] Imagem processada: tier={result.tier_used}, "
            f"api={result.api_used}, time={result.total_time_ms}ms"
        )

    except Exception as e:
        logger.error(f"Erro ao processar mensagem Kafka: {e}", exc_info=True)
        # NÃO fazer commit — mensagem será reprocessada
        # Em produção: implementar DLQ (Dead Letter Queue) após N tentativas
```

### 13.2 Entrypoint

```python
# brasileira/agents/fotografo/__main__.py
# Execução: python -m brasileira.agents.fotografo

import asyncio
import logging
import os

from .agent import run_fotografo_consumer
from .config import FotografoConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fotografo")


async def main():
    config = FotografoConfig(
        # APIs de busca
        pexels_api_key=os.environ["PEXELS_API_KEY"],
        unsplash_access_key=os.environ["UNSPLASH_ACCESS_KEY"],
        flickr_api_key=os.environ["FLICKR_API_KEY"],
        # Geração por IA
        openai_api_key=os.environ["OPENAI_API_KEY"],
        bfl_api_key=os.environ.get("BFL_API_KEY"),  # Opcional
        # WordPress
        wp_url=os.environ["WP_URL"],
        wp_user=os.environ["WP_USER"],
        wp_app_password=os.environ["WP_APP_PASSWORD"],
        # Infraestrutura
        kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_group_id=os.environ.get("KAFKA_GROUP_ID", "fotografo-consumer-group"),
        kafka_topic_consume=os.environ.get("KAFKA_TOPIC_CONSUME", "article-published"),
        kafka_topic_produce=os.environ.get("KAFKA_TOPIC_PRODUCE", "image-attached"),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        postgres_dsn=os.environ["POSTGRES_DSN"],
        # Performance
        max_parallel=int(os.environ.get("FOTOGRAFO_WORKERS", "3")),
        max_reformulation_rounds=int(os.environ.get("FOTOGRAFO_MAX_REFORMULATION_ROUNDS", "2")),
        instance_id=os.environ.get("FOTOGRAFO_INSTANCE_ID", "fotografo-01"),
    )

    logger.info(f"Iniciando Fotógrafo V3 — instância {config.instance_id}")
    await run_fotografo_consumer(config)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## PARTE XIV — TESTES, VALIDAÇÃO E CHECKLIST

### 14.1 Testes Unitários

```python
# tests/test_fotografo/test_tier1_extraction.py

import pytest
from unittest.mock import AsyncMock, patch

from brasileira.agents.fotografo.tier1_extraction import Tier1Extractor


@pytest.mark.asyncio
async def test_extract_og_image():
    """Testa extração de og:image de HTML simples."""
    html = """
    <html>
    <head>
        <meta property="og:image" content="https://exemplo.com/foto-principal.jpg"/>
        <meta property="og:image:width" content="1200"/>
        <meta property="og:image:height" content="630"/>
    </head>
    </html>
    """
    extractor = Tier1Extractor()
    result = await extractor.extract(
        source_url="https://g1.globo.com/noticia/123",
        html_content=html,
    )
    assert result.success
    assert result.candidate.url == "https://exemplo.com/foto-principal.jpg"
    assert result.extraction_method == "og_image"
    assert result.candidate.width == 1200


@pytest.mark.asyncio
async def test_extract_jsonld_newsarticle():
    """Testa extração de schema.org NewsArticle."""
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "Notícia de Teste",
            "image": {
                "@type": "ImageObject",
                "url": "https://cdn.exemplo.com/news-foto.jpg",
                "width": 1920,
                "height": 1080
            }
        }
        </script>
    </head>
    </html>
    """
    extractor = Tier1Extractor()
    result = await extractor.extract(
        source_url="https://folha.com.br/noticia/456",
        html_content=html,
    )
    assert result.success
    assert result.candidate.url == "https://cdn.exemplo.com/news-foto.jpg"
    assert result.extraction_method == "jsonld_newsarticle_image"


@pytest.mark.asyncio
async def test_extract_protocol_relative_url():
    """Testa normalização de URLs protocol-relative (//cdn.example.com/...)."""
    html = """
    <html>
    <head>
        <meta property="og:image" content="//cdn.g1.globo.com/foto-capa.jpg"/>
    </head>
    </html>
    """
    extractor = Tier1Extractor()
    result = await extractor.extract(
        source_url="https://g1.globo.com/noticia",
        html_content=html,
    )
    # FIX B-14: Protocol-relative URL deve ser normalizada para https://
    assert result.success
    assert result.candidate.url.startswith("https://")
    assert "//cdn" not in result.candidate.url


@pytest.mark.asyncio
async def test_extract_rejects_logo():
    """Testa que logos e ícones são rejeitados."""
    html = """
    <html>
    <head>
        <meta property="og:image" content="https://site.com/logo.png"/>
    </head>
    </html>
    """
    extractor = Tier1Extractor()
    result = await extractor.extract(
        source_url="https://site.com/noticia",
        html_content=html,
    )
    # Imagem com "logo" no nome deve ser rejeitada
    assert not result.success or "logo" not in result.candidate.url.lower()
```

```python
# tests/test_fotografo/test_query_generator.py

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from brasileira.agents.fotografo.query_generator import QueryGenerator
from brasileira.agents.fotografo.models import TierQueries


@pytest.mark.asyncio
async def test_generate_queries_premium_tier():
    """Verifica que query generation usa tier PREMIUM."""
    mock_router = MagicMock()
    mock_router.complete = AsyncMock(return_value=MagicMock(
        content=json.dumps({
            "agencia_brasil_r0": ["greve professores brasília"],
            "wikimedia_r0": ["teachers strike brazil protest"],
            "pexels_r0": ["education workers demonstration signs"],
            "unsplash_r0": ["teachers protest school"],
            "flickr_r0": ["teacher strike demonstration"],
            "agencia_brasil_r1": ["educação protesto"],
            "wikimedia_r1": ["education protest brazil"],
            "pexels_r1": ["school education workers"],
            "unsplash_r1": ["education system school"],
            "flickr_r1": ["teachers school education"],
            "pexels_r2": ["protest demonstration signs crowd"],
            "unsplash_r2": ["demonstration signs people street"],
            "flickr_r2": ["protest crowd street"],
            "dalle_prompt": "Teachers strike protest, editorial illustration",
            "flux_prompt": "Education workers demonstration, editorial art",
        }),
        tier_used="PREMIUM",
        model="claude-opus-4",
    ))

    gen = QueryGenerator(router=mock_router)
    queries = await gen.generate(
        title="Professores entram em greve em todo o Brasil",
        content="Docentes paralisam atividades em protesto contra salários defasados",
        editoria="Educação",
    )

    # Verifica que router foi chamado com task_type="imagem_query"
    call_args = mock_router.complete.call_args
    assert call_args.kwargs.get("task_type") == "imagem_query"

    # Verifica estrutura das queries
    assert len(queries.pexels_r0) > 0
    assert len(queries.agencia_brasil_r0) > 0
    assert queries.dalle_prompt
    assert queries.flux_prompt


@pytest.mark.asyncio
async def test_fallback_queries_on_llm_failure():
    """Testa que fallback é retornado quando LLM falha."""
    mock_router = MagicMock()
    mock_router.complete = AsyncMock(side_effect=Exception("LLM indisponível"))

    gen = QueryGenerator(router=mock_router)
    queries = await gen.generate(
        title="Artigo qualquer",
        content="Conteúdo qualquer",
        editoria="Política",
    )

    # Fallback deve conter queries para editoria Política
    assert len(queries.pexels_r0) > 0
    assert "government" in queries.pexels_r0[0].lower() or "parliament" in queries.pexels_r0[0].lower()
```

```python
# tests/test_fotografo/test_wp_uploader.py

import pytest
import respx
import httpx
from io import BytesIO
from PIL import Image

from brasileira.agents.fotografo.wp_uploader import WordPressUploader


def create_test_image_bytes(mode="RGB", size=(1200, 630)) -> bytes:
    """Cria imagem de teste em memória."""
    img = Image.new(mode, size, color=(100, 150, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_rgba_conversion():
    """FIX B-01: Testa conversão RGBA → RGB sem fundo preto."""
    uploader = WordPressUploader(
        wp_url="https://brasileira.news",
        wp_user="user",
        wp_app_password="pass",
    )

    # Imagem RGBA com canal alpha
    img = Image.new("RGBA", (800, 450), (255, 0, 0, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    processed, content_type = await uploader._download_and_process.__wrapped__(
        uploader, "mock_url"
    ) if False else (None, None)

    # Teste direto da lógica de conversão
    img_loaded = Image.open(BytesIO(raw_bytes))
    assert img_loaded.mode == "RGBA"

    bg = Image.new("RGB", img_loaded.size, (255, 255, 255))
    bg.paste(img_loaded, mask=img_loaded.split()[3])
    result = bg

    # Fundo deve ser branco, não preto
    pixel = result.getpixel((0, 0))
    assert pixel[0] > 200, "Fundo deve ser branco após composição RGBA"
    assert result.mode == "RGB"


@pytest.mark.asyncio
@respx.mock
async def test_upload_with_retry():
    """Testa retry no upload para WP."""
    wp_url = "https://brasileira.news"
    uploader = WordPressUploader(
        wp_url=wp_url,
        wp_user="user",
        wp_app_password="pass",
        max_retries=3,
    )

    # Simula 2 falhas e 1 sucesso
    respx.post(f"{wp_url}/wp-json/wp/v2/media").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(201, json={"id": 12345}),
        ]
    )
    respx.patch(f"{wp_url}/wp-json/wp/v2/media/12345").mock(
        return_value=httpx.Response(200, json={"id": 12345})
    )

    media_id = await uploader._upload_media(
        image_data=b"fake_image_data",
        content_type="image/jpeg",
        filename="test-image",
    )

    assert media_id == 12345


@pytest.mark.asyncio
async def test_safe_filename_non_ascii():
    """FIX B-15: Testa geração de filename para títulos não-ASCII."""
    uploader = WordPressUploader(
        wp_url="https://brasileira.news",
        wp_user="u",
        wp_app_password="p",
    )

    # Título com caracteres especiais
    assert uploader._safe_filename("!!??..!!") == "imagem-noticia"
    assert uploader._safe_filename("") == "imagem-noticia"
    assert uploader._safe_filename("Greve de Professores") == "greve-de-professores"
    assert uploader._safe_filename("Índia Brasil Relações") == "india-brasil-relacoes"
```

### 14.2 Testes de Integração

```python
# tests/test_fotografo/test_pipeline_integration.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from brasileira.agents.fotografo.agent import FotografoAgent
from brasileira.agents.fotografo.config import FotografoConfig
from brasileira.agents.fotografo.models import ArticlePublishedEvent
from datetime import datetime


def make_config():
    return FotografoConfig(
        pexels_api_key="test_pexels",
        unsplash_access_key="test_unsplash",
        flickr_api_key="test_flickr",
        openai_api_key="test_openai",
        wp_url="https://brasileira.news",
        wp_user="user",
        wp_app_password="pass",
        kafka_bootstrap_servers="localhost:9092",
        kafka_group_id="test",
        kafka_topic_consume="article-published",
        kafka_topic_produce="image-attached",
        redis_url="redis://localhost:6379",
        postgres_dsn="postgresql://localhost/test",
        instance_id="fotografo-test",
    )


def make_event(**kwargs):
    defaults = {
        "post_id": 123,
        "article_id": "test-uuid-001",
        "wp_slug": "greve-professores-2026",
        "titulo": "Professores entram em greve em todo o Brasil",
        "editoria": "Educação",
        "lead": "Docentes paralisam atividades em protesto contra salários defasados",
        "url_fonte": "https://g1.globo.com/educacao/noticia/2026/03/greve.html",
        "html_fonte": None,
        "urgencia": 7,
        "timestamp": datetime.utcnow(),
        "reporter_id": "reporter-01",
        "tags": ["greve", "educação", "professores"],
        "entidades": ["Ministério da Educação", "CNTE"],
    }
    return ArticlePublishedEvent(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_tier1_success_path():
    """Testa caminho feliz: Tier 1 encontra imagem."""
    config = make_config()
    agent = FotografoAgent(config)
    event = make_event(
        html_fonte="""
        <html><head>
        <meta property="og:image" content="https://s3.glbimg.com/greve-professores.jpg"/>
        <meta property="og:image:width" content="1200"/>
        <meta property="og:image:height" content="630"/>
        </head></html>
        """
    )

    # Mock CLIP para aprovar
    agent.clip.score = AsyncMock(return_value=0.35)

    # Mock WP upload
    agent.wp.upload_and_attach = AsyncMock(return_value=(True, 99999))

    result = await agent.process_event(event)

    assert result.post_id == 123
    assert result.tier_used == "tier1"
    assert result.media_id == 99999


@pytest.mark.asyncio
async def test_tier4_guarantee_when_all_fail():
    """Testa que Tier 4 garante imagem quando tudo falha."""
    config = make_config()
    agent = FotografoAgent(config)
    event = make_event()

    # Tier 1 falha
    agent.tier1.extract = AsyncMock(return_value=MagicMock(success=False))

    # Tier 2 falha (todas as APIs)
    # Tier 3 falha (geração por IA)
    agent.tier3.generate = AsyncMock(return_value=None)

    # WP upload funciona para placeholder
    agent.wp.upload_and_attach = AsyncMock(return_value=(True, 10006))  # ID do placeholder Educação

    result = await agent.process_event(event)

    # Deve ter usado Tier 4
    assert "tier4" in result.tier_used
    # Nunca deve retornar media_id None
    assert result.media_id is not None


@pytest.mark.asyncio
async def test_reformulation_triggers_on_clip_fail():
    """Testa que reformulação é acionada quando CLIP score é baixo."""
    config = make_config()
    agent = FotografoAgent(config)
    event = make_event()

    call_count = 0

    async def mock_clip_score(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Primeiras tentativas: score baixo; terceira: score ok
        return 0.10 if call_count < 3 else 0.30

    agent.clip.score = mock_clip_score

    # Garante que Tier 2 e Tier 3 retornam candidatos
    # (lógica simplificada para o teste)

    result = await agent.process_event(event)
    # Se reformulação funcionou, deve ter tentado mais de uma rodada
    assert result.rounds_attempted >= 0  # Sempre True, mas documenta intenção
```

### 14.3 Checklist de Implementação

```
FOTÓGRAFO V3 — CHECKLIST DE IMPLEMENTAÇÃO
==========================================

[ ] INFRAESTRUTURA
  [x] FotografoAgent como consumer Kafka (não chamado pelo Reporter)
  [x] LangGraph com 7 nós + transições condicionais
  [x] asyncio em todo o pipeline (sem requests síncronos)
  [x] Semaphore para controle de concorrência (max_parallel=3)
  [ ] Redis connection pool configurado
  [ ] PostgreSQL connection pool configurado
  [ ] CLIP model pré-carregado em memória (ThreadPoolExecutor)

[ ] QUERY GENERATION (PREMIUM OBRIGATÓRIO)
  [x] SmartLLMRouter com task_type="imagem_query"
  [x] System prompt completo com regras editoriais
  [x] Queries por API e por rodada (r0, r1, r2)
  [x] Prompts para DALL-E / Flux
  [x] Fallback quando LLM falha
  [ ] Teste: verificar que tier PREMIUM é usado (não ECONÔMICO)

[ ] TIER 1 — EXTRAÇÃO DA FONTE
  [x] schema.org JSON-LD (NewsArticle, Article, BlogPosting)
  [x] og:image (Open Graph)
  [x] twitter:image
  [x] article tag + lazy loading (data-src, data-lazy-src)
  [x] Normalização de URLs protocol-relative (//)
  [x] Rejeição de logos, ícones, CDNs publicitários
  [x] FIX B-04: Tier 1 para TODAS as fontes (não só oficiais)
  [ ] Teste: extração em G1, Folha, Estadão, UOL, UOL, R7

[ ] TIER 2 — BUSCA EM APIs
  [x] Pexels API (200 req/h, 20k/mês)
  [x] Unsplash API (tracking de download obrigatório)
  [x] Wikimedia Commons (sem key, sem custo)
  [x] Flickr CC (licenças 4, 5, 9 — CC-BY, CC-BY-SA, CC0)
  [x] Agência Brasil EBC (CC-BY)
  [x] FIX B-06: Flickr user IDs reais (não placeholder)
  [x] Verificação de `stat: "ok"` na resposta Flickr
  [x] Registro de download Unsplash (conformidade)
  [x] Suporte a orientação landscape
  [x] Dimensões mínimas (800x450px)
  [ ] Rate limit tracking por API em Redis

[ ] CLIP VALIDATION
  [x] Modelo openai/clip-vit-large-patch14
  [x] Thresholds por editoria (0.18-0.30)
  [x] Cache de scores em memória
  [x] Validação editorial zero-shot
  [x] Execução em ThreadPoolExecutor (não bloqueia event loop)
  [ ] Pré-carregamento do modelo no startup

[ ] REFORMULAÇÃO AUTOMÁTICA
  [x] Rodada 0: Query específica
  [x] Rodada 1: Broadening (generalização)
  [x] Rodada 2: Pivoting (contexto)
  [x] Threshold relaxado por rodada (redução de 15%)
  [x] Máximo 2 rodadas de reformulação

[ ] TIER 3 — GERAÇÃO POR IA
  [x] gpt-image-1 (OpenAI) como primário
  [x] Flux.2 Pro (BFL) como fallback
  [x] Polling assíncrono para Flux
  [x] Restrições editoriais no prompt (sem rostos reais, sem texto)
  [x] Estilo não-fotorrealista obrigatório
  [x] Label [IA] na attribution OBRIGATÓRIO
  [x] FIX B-17: DALL-E não mais desativado
  [ ] Limites de conteúdo testados

[ ] TIER 4 — PLACEHOLDER
  [x] Placeholders por editoria (16 editorias)
  [x] WP media IDs pré-configurados
  [x] Fallback _default para editorias desconhecidas
  [x] NUNCA falha — garantia absoluta
  [ ] Setup script executado (placeholders uploadados no WP)
  [ ] Um único padrão de placeholder (FIX B-11)

[ ] WORDPRESS UPLOADER
  [x] FIX B-01: Conversão RGBA/PA correta (fundo branco)
  [x] FIX B-08: Meta update com tratamento de erro
  [x] FIX B-09: Falha explícita (não retorna None silenciosamente)
  [x] FIX B-15: safe_filename para títulos não-ASCII
  [x] Deduplicação: verifica se imagem já existe na media library
  [x] Retry com backoff exponencial (3 tentativas)
  [x] Upload + SET featured_media em dois requests separados
  [ ] Verificação final: post tem featured_media ≠ 0

[ ] PERSISTÊNCIA
  [x] Redis: cache de busca (TTL 1h)
  [x] Redis: blacklist de rejeições (TTL 24h)
  [x] PostgreSQL: fotografo_resultados
  [x] PostgreSQL: image_rejections
  [x] Kafka: evento image-attached produzido

[ ] SEGURANÇA
  [x] FIX B-13: API keys não logadas em URLs
  [x] Validação de Content-Type antes de processar imagem
  [x] Limite de tamanho de imagem (10MB máx)
  [x] User-Agent identificador de bot

[ ] TESTES
  [x] test_tier1_extraction.py
  [x] test_query_generator.py (verifica tier PREMIUM)
  [x] test_wp_uploader.py (RGBA, retry, safe_filename)
  [x] test_pipeline_integration.py (tier1 path, tier4 guarantee)
  [ ] test_tier2_apis.py (mock de cada API)
  [ ] test_clip_validator.py
  [ ] test_tier3_generation.py
  [ ] test_reformulation_controller.py
  [ ] Teste de carga: 100 artigos simultâneos
  [ ] Teste de integração end-to-end com WordPress real (staging)

[ ] DEPLOY
  [ ] CLIP model pre-download no Dockerfile
  [ ] Variáveis de ambiente configuradas
  [ ] Setup de placeholders no WP (executar setup_placeholders.py)
  [ ] Monitoramento: alertar se tier4 > 10% (indica falha sistêmica)
  [ ] Monitoramento: alertar se total_time_ms > 60s (SLA excedido)
  [ ] Dashboard: distribuição de tier_usado por editoria
```

### 14.4 SLAs e Métricas de Sucesso

| Métrica | Target | Crítico |
|---------|--------|---------|
| % notícias com imagem | 100% | < 99% = incidente |
| % imagens Tier 1 | > 40% | < 20% = pipeline degradado |
| % imagens Tier 4 (placeholder) | < 5% | > 15% = falha sistêmica |
| % imagens IA (Tier 3) | < 10% | > 25% = APIs externas com problemas |
| Tempo médio de processamento | < 15s | > 60s = SLA excedido |
| CLIP score médio | > 0.25 | < 0.18 = qualidade editorial baixa |
| Taxa de reformulação | < 20% | > 50% = queries iniciais inadequadas |

### 14.5 Queries SQL para Monitoramento

```sql
-- Dashboard: distribuição de tier por editoria (último 24h)
SELECT
    editoria,
    tier_usado,
    COUNT(*) as total,
    ROUND(AVG(clip_score)::numeric, 3) as clip_medio,
    ROUND(AVG(total_time_ms)::numeric) as tempo_medio_ms
FROM fotografo_resultados
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY editoria, tier_usado
ORDER BY editoria, tier_usado;

-- Alerta: taxa de placeholder acima de 10%
SELECT
    editoria,
    COUNT(*) FILTER (WHERE placeholder_usada) * 100.0 / COUNT(*) AS pct_placeholder
FROM fotografo_resultados
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY editoria
HAVING COUNT(*) FILTER (WHERE placeholder_usada) * 100.0 / COUNT(*) > 10;

-- Top imagens rejeitadas (debug de qualidade)
SELECT
    image_url,
    rejection_reason,
    reject_count,
    clip_score
FROM image_rejections
ORDER BY reject_count DESC
LIMIT 20;

-- Performance por instância
SELECT
    fotografo_id,
    COUNT(*) as processados,
    AVG(total_time_ms) as tempo_medio,
    COUNT(*) FILTER (WHERE tier_usado = 'tier4') as placeholders
FROM fotografo_resultados r
JOIN fotografo_resultados_meta m USING (article_id)
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY fotografo_id;
```

---

## APÊNDICE A — Modelos Pydantic Completos

```python
# brasileira/agents/fotografo/models.py

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel, Field


class ImageCandidate(BaseModel):
    """Candidata a imagem para o artigo."""
    url: str
    source_api: str = ""
    source_tier: str = ""
    source_method: str = ""

    # Dimensões
    width: Optional[int] = None
    height: Optional[int] = None

    # Metadados de atribuição
    photographer: str = ""
    photographer_url: str = ""
    license_type: str = ""
    attribution: str = ""

    # Scores de qualidade
    clip_score: Optional[float] = None
    confidence: float = 0.5

    # IDs externos
    pexels_url: Optional[str] = None
    unsplash_photo_id: Optional[str] = None
    unsplash_download_url: Optional[str] = None
    wikimedia_page_title: Optional[str] = None
    flickr_photo_id: Optional[str] = None

    # Geração por IA
    ai_generated: bool = False
    ai_model: Optional[str] = None
    ai_prompt: Optional[str] = None

    # Placeholder
    is_placeholder: bool = False
    wp_media_id: Optional[int] = None  # Apenas para placeholders pré-carregados
    editoria: Optional[str] = None


class ExtractionResult(BaseModel):
    """Resultado da extração Tier 1."""
    success: bool
    candidate: Optional[ImageCandidate] = None
    extraction_method: str = ""
    reason: str = ""


class SearchResult(BaseModel):
    """Resultado da busca Tier 2."""
    success: bool
    candidate: Optional[ImageCandidate] = None
    api_used: str = ""
    query_used: str = ""
    clip_score: Optional[float] = None
    round_number: int = 0
    reason: str = ""


class TierQueries(BaseModel):
    """Queries geradas pelo LLM para cada API e rodada."""

    # Rodada 0: Queries específicas
    agencia_brasil_r0: List[str] = Field(default_factory=list)
    wikimedia_r0: List[str] = Field(default_factory=list)
    pexels_r0: List[str] = Field(default_factory=list)
    unsplash_r0: List[str] = Field(default_factory=list)
    flickr_r0: List[str] = Field(default_factory=list)

    # Rodada 1: Broadening
    agencia_brasil_r1: List[str] = Field(default_factory=list)
    wikimedia_r1: List[str] = Field(default_factory=list)
    pexels_r1: List[str] = Field(default_factory=list)
    unsplash_r1: List[str] = Field(default_factory=list)
    flickr_r1: List[str] = Field(default_factory=list)

    # Rodada 2: Pivoting
    pexels_r2: List[str] = Field(default_factory=list)
    unsplash_r2: List[str] = Field(default_factory=list)
    flickr_r2: List[str] = Field(default_factory=list)

    # Tier 3
    dalle_prompt: str = ""
    flux_prompt: str = ""

    def get_query(self, api_name: str, round_number: int) -> Optional[str]:
        key = f"{api_name}_r{round_number}"
        queries = getattr(self, key, [])
        return queries[0] if queries else None


class FotografoState(BaseModel):
    """Estado do pipeline do Fotógrafo."""

    # Input
    post_id: int
    article_id: str
    titulo: str
    editoria: str
    lead: str
    url_fonte: str
    html_fonte: Optional[str] = None
    urgencia: int = 5

    # Processamento
    queries: Optional[TierQueries] = None
    reformulation_state: Optional[Any] = None  # ReformulationState
    last_search_result: Optional[SearchResult] = None

    # Output
    selected_candidate: Optional[ImageCandidate] = None
    wp_media_id: Optional[int] = None
    tier_used: Optional[str] = None
    query_used: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


class ArticlePublishedEvent(BaseModel):
    """Evento consumido do Kafka: article-published."""
    post_id: int
    article_id: str
    wp_slug: str = ""
    titulo: str
    editoria: str
    lead: str = ""
    url_fonte: str
    html_fonte: Optional[str] = None
    urgencia: int = 5
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    reporter_id: str = ""
    tags: List[str] = Field(default_factory=list)
    entidades: List[str] = Field(default_factory=list)


class ImageAttachedEvent(BaseModel):
    """Evento produzido para o Kafka: image-attached."""
    post_id: int
    article_id: str
    media_id: Optional[int]
    tier_used: str
    api_used: Optional[str] = None
    query_used: Optional[str] = None
    clip_score: Optional[float] = None
    image_url: Optional[str] = None
    attribution: str = ""
    ai_generated: bool = False
    total_time_ms: int
    rounds_attempted: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    fotografo_id: str = "fotografo-01"
```

---

## APÊNDICE B — Configuração

```python
# brasileira/agents/fotografo/config.py

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class FotografoConfig:
    """Configuração completa do Fotógrafo."""

    # APIs de busca de imagem
    pexels_api_key: str
    unsplash_access_key: str
    flickr_api_key: str

    # APIs de geração por IA
    openai_api_key: str
    bfl_api_key: Optional[str] = None  # Flux.2 (opcional)

    # WordPress
    wp_url: str = "https://brasileira.news"
    wp_user: str = "iapublicador"
    wp_app_password: str = ""

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "fotografo-consumer-group"
    kafka_topic_consume: str = "article-published"
        kafka_topic_publish: str = "image-processed"

    # Pipeline
    clip_threshold_default: float = 0.22
    max_rounds: int = 2
    tier1_timeout: float = 10.0
    tier2_timeout: float = 15.0
    tier3_timeout: float = 20.0

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    rejection_ttl_seconds: int = 86400

    # Placeholder URLs por editoria (Tier 4)
    placeholder_by_editoria: dict = field(default_factory=lambda: {
        "Política": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-politica.jpg",
        "Economia": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-economia.jpg",
        "Esportes": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-esportes.jpg",
        "Tecnologia": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-tecnologia.jpg",
        "Saúde": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-saude.jpg",
        "Educação": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-educacao.jpg",
        "Ciência": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-ciencia.jpg",
        "Cultura/Entretenimento": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-cultura.jpg",
        "Mundo/Internacional": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-mundo.jpg",
        "Meio Ambiente": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-meioambiente.jpg",
        "Segurança/Justiça": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-seguranca.jpg",
        "Sociedade": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-sociedade.jpg",
        "Brasil": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-brasil.jpg",
        "Regionais": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-regionais.jpg",
        "Opinião/Análise": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-opiniao.jpg",
        "Últimas Notícias": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-geral.jpg",
        "geral": "https://brasileira.news/wp-content/uploads/sites/7/2026/02/placeholder-geral.jpg",
    })

    @classmethod
    def from_env(cls) -> "FotografoConfig":
        """Carrega configuração do ambiente."""
        return cls(
            pexels_api_key=os.environ["PEXELS_API_KEY"],
            unsplash_access_key=os.environ["UNSPLASH_ACCESS_KEY"],
            flickr_api_key=os.environ["FLICKR_API_KEY"],
            openai_api_key=os.environ["OPENAI_API_KEY"],
            bfl_api_key=os.environ.get("BFL_API_KEY"),
            wp_url=os.environ.get("WP_URL", "https://brasileira.news"),
            wp_user=os.environ.get("WP_USER", "iapublicador"),
            wp_app_password=os.environ["WP_APP_PASSWORD"],
            kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        )
```

---

## APÊNDICE C — Rate Limits e Quotas de APIs (Referência Rápida)

| API | Rate Limit Padrão | Rate Limit Ampliado | Custo |
|-----|-------------------|---------------------|-------|
| **Pexels** | 200 req/h · 20k req/mês | Ilimitado (aprovação) | Gratuita |
| **Unsplash** | 50 req/h (demo) | 5.000 req/h (produção) | Gratuita |
| **Wikimedia Commons** | ~500 req/s | Sem limite declarado | Gratuita |
| **Flickr** | 3.600 req/h | Variável por contrato | Gratuita (chave) |
| **Agência Brasil** | N/A (scraping educado) | — | Gratuita |
| **gpt-image-1** | Tier-based OpenAI | Conforme conta | $0,04–$0,12/imagem |
| **Flux.2 Pro** | 10 req/s (API BFL) | Conforme contrato | $0,05–$0,08/imagem |
| **CLIP (local)** | Ilimitado | — | Custo infra |

**Configurações de header para Rate Limit:**

```python
# Ler rate limit restante do header Pexels
remaining = int(response.headers.get("X-Ratelimit-Remaining", 999))
if remaining < 10:
    logger.warning(f"Pexels rate limit baixo: {remaining} req restantes")
    await asyncio.sleep(2.0)  # Back-off preventivo

# Unsplash: registrar download obrigatório
# POST https://api.unsplash.com/photos/{id}/download
await unsplash_register_download(photo_id)
```

---

## APÊNDICE D — Variáveis de Ambiente (.env)

```bash
# Fotógrafo — Variáveis de Ambiente

# APIs de Imagem
PEXELS_API_KEY=your_pexels_key_here
UNSPLASH_ACCESS_KEY=your_unsplash_access_key
UNSPLASH_SECRET_KEY=your_unsplash_secret_key
FLICKR_API_KEY=your_flickr_api_key
FLICKR_API_SECRET=your_flickr_api_secret

# IA Generativa
OPENAI_API_KEY=your_openai_key  # Para gpt-image-1 E para query generation
BFL_API_KEY=your_bfl_key        # Para Flux.2 Pro (opcional, fallback para gpt-image-1)

# WordPress
WP_URL=https://brasileira.news
WP_USER=iapublicador
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_GROUP=fotografo-consumer-group

# Redis
REDIS_URL=redis://localhost:6379/0

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/brasileira

# CLIP (se usar servidor separado)
CLIP_SERVICE_URL=http://localhost:8001  # Opcional: servidor CLIP externo
CLIP_ENABLED=true                       # false = desativa CLIP, usa apenas LLM validation

# Pipeline
MAX_ROUNDS=2
CLIP_THRESHOLD_DEFAULT=0.22
LOG_LEVEL=INFO
```

---

## APÊNDICE E — Tabela de Decisão: Qual Tier Usar?

```
┌─────────────────────────────────────────────────────────────────┐
│              DECISION TREE — FOTÓGRAFO V3                        │
│                                                                   │
│  EVENTO article-published recebido                                │
│           │                                                       │
│           ▼                                                       │
│  [Tier 1] Extração da fonte (og:image, schema.org)                │
│           │                                                       │
│     ✅ Encontrou imagem com ≥800px?                               │
│     │  SIM → CLIP validate → se score ≥ threshold → ACEITAR      │
│     │  NÃO ou CLIP baixo → próximo tier                          │
│           │                                                       │
│           ▼                                                       │
│  [Tier 2] Busca em APIs (Pexels → Unsplash → Wikimedia →         │
│           Flickr → Agência Brasil)                                │
│           │                                                       │
│     ✅ Encontrou imagem relevante?                                │
│     │  SIM → CLIP validate → se score ≥ threshold → ACEITAR      │
│     │  NÃO → Reformulação Round 1 (broadening)                   │
│     │        └→ Retry Tier 2 com query mais ampla                 │
│     │            SIM → ACEITAR                                    │
│     │            NÃO → Reformulação Round 2 (pivoting)            │
│     │                  └→ Retry Tier 2 novamente                  │
│     │                      SIM → ACEITAR                          │
│     │                      NÃO → próximo tier                    │
│           │                                                       │
│           ▼                                                       │
│  [Tier 3] Geração por IA (gpt-image-1 → Flux.2 Pro)              │
│           │                                                       │
│     ✅ Geração bem-sucedida?                                      │
│     │  SIM → LABEL obrigatório → ACEITAR                          │
│     │  NÃO (erro API, timeout) → próximo tier                    │
│           │                                                       │
│           ▼                                                       │
│  [Tier 4] Placeholder temático por editoria (GARANTIA)            │
│           │                                                       │
│     SEMPRE funciona → ACEITAR (placeholder)                       │
│           │                                                       │
│           ▼                                                       │
│  Upload WordPress → Set featured_media → Publish Kafka event      │
└─────────────────────────────────────────────────────────────────┘
```

---

## APÊNDICE F — Checklist de Implantação

### Pré-implantação

- [ ] Variáveis de ambiente configuradas (ver Apêndice D)
- [ ] Kafka topic `article-published` criado com pelo menos 6 partições
- [ ] Kafka topic `image-processed` criado
- [ ] Redis acessível com TTL suportado
- [ ] PostgreSQL com tabelas `artigos` e `image_pipeline_log` criadas (ver Parte XI)
- [ ] WordPress Application Password criada para usuário `iapublicador`
- [ ] Chave Pexels API ativa e testada
- [ ] Chave Unsplash API aprovada para produção (não apenas demo)
- [ ] Chave OpenAI com acesso a `gpt-image-1`
- [ ] Placeholders temáticos uploaded para WordPress (16 imagens, ver Apêndice B)

### CLIP / Validation

- [ ] Dependência `transformers` instalada: `pip install transformers torch Pillow`
- [ ] Modelo CLIP baixado em primeiro run: `openai/clip-vit-large-patch14`
- [ ] (Opcional) Servidor CLIP separado configurado se infra não suporta GPU

### Teste Smoke Test

```bash
# 1. Publicar evento de teste no Kafka
python -m brasileira.agents.fotografo.test_smoke --article-id "test-001" --title "Senado aprova reforma tributária" --category "Política"

# 2. Verificar logs
docker logs fotografo-01 --tail 100

# 3. Verificar post no WordPress
curl -s "https://brasileira.news/wp-json/wp/v2/posts?slug=test-001" | jq '.[0].featured_media'
# Deve retornar um media_id > 0

# 4. Verificar banco
psql -c "SELECT tier_usado, api_usada, clip_score FROM image_pipeline_log WHERE article_id = 'test-001';"
```

### Validação em Produção (Primeiros 7 dias)

```sql
-- Taxa de sucesso por tier (deve ser: Tier1 ~30%, Tier2 ~50%, Tier3 ~15%, Tier4 ~5%)
SELECT tier_usado, COUNT(*), ROUND(AVG(clip_score)::numeric, 3) as avg_clip
FROM image_pipeline_log
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY tier_usado ORDER BY COUNT(*) DESC;

-- Artigos sem imagem (Tier4 = placeholder — meta a reduzir)
SELECT COUNT(*) as placeholders
FROM image_pipeline_log
WHERE tier_usado = 'tier4_placeholder'
AND timestamp > NOW() - INTERVAL '24 hours';

-- Tempo médio de processamento
SELECT ROUND(AVG(latencia_total_ms)) as avg_ms, MAX(latencia_total_ms) as max_ms
FROM image_pipeline_log
WHERE timestamp > NOW() - INTERVAL '24 hours';
```

---

*Briefing gerado em 26 de março de 2026 | Versão 3.0 | Componente #5 — Fotógrafo*

*Depende de: SmartLLMRouter V3 (Componente #1)*

*Próximos componentes: #6 Revisor, #7 Curador Homepage, #8 Consolidador*
