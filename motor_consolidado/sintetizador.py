"""
Sintetizador de matérias consolidadas.
Coleta conteúdo de múltiplas fontes sobre um tema e gera artigo unificado via LLM.
Usa llm_router.call_llm() com tier TIER_CONSOLIDATOR.
"""

import logging
import sys
from pathlib import Path

# Reutilizar módulos existentes
sys.path.insert(0, str(Path("/home/bitnami/motor_rss")))
sys.path.insert(0, str(Path("/home/bitnami/motor_scrapers")))

from extrator_conteudo import extrair_conteudo_completo
from llm_router import call_llm, TIER_CONSOLIDATOR

from config_consolidado import (
    MIN_CONTENT_WORDS, MAX_CONTENT_WORDS_PAY,
    MAX_SOURCES_PER_TOPIC, MIN_SOURCES_PER_TOPIC,
    MIN_SYNTHESIS_WORDS, MAX_SYNTHESIS_WORDS,
    STOPWORDS_PT,
)
import config

logger = logging.getLogger("motor_consolidado")

# ── Prompt de Síntese ─────────────────────────────────────

SYSTEM_PROMPT = (
    "Você é o editor-chefe do Brasileira.News. "
    "Seu trabalho é produzir matérias consolidadas de altíssima qualidade, "
    "sintetizando informações de múltiplos veículos jornalísticos brasileiros. "
    "REGRA DE OURO: TOLERÂNCIA ZERO PARA ALUCINAÇÃO. "
    "ESTRITAMENTE PROIBIDO inventar fatos, dados, estatísticas, nomes ou declarações "
    "que não estejam presentes nas fontes fornecidas."
)

SYNTHESIS_PROMPT_TEMPLATE = """Abaixo estão reportagens de {n_fontes} veículos brasileiros sobre o mesmo tema.
Produza UMA matéria consolidada seguindo OBRIGATORIAMENTE estas regras:

=== ESTRUTURA ===

1. TÍTULO (titulo): 70 a 90 caracteres. Palavra-chave principal logo no início. Sem prefixos editoriais.

2. LIDE (1º parágrafo): Responda O quê, Quem, Quando, Onde, Como, Por quê.

3. CORPO (conteudo):
   - OBRIGATÓRIO: TODOS os parágrafos de texto fluído devem ser envolvidos e fechados corretamente por tags <p> e </p>. NUNCA deixe texto solto entre títulos e intertítulos.
   - Sintetize as informações MAIS RELEVANTES de TODAS as fontes
   - Use <h2> a cada 2-3 parágrafos formulados como PERGUNTAS (estilo FAQ: "O que muda para o cidadão?")
   - Use <strong> nas entidades cruciais no primeiro terço do texto
   - Inclua as melhores ASPAS REAIS encontradas nas fontes usando <blockquote>
   - PROIBIDO inventar aspas — use APENAS aspas que estejam literalmente nas fontes
   - Cite TODOS os veículos consultados NO TEXTO (com links): 
     De acordo com informações do <a href="URL" target="_blank" rel="nofollow">NOME_DA_FONTE</a>
   - Use <ul> quando houver listas de pontos, fatores, prazos
   - Adicione contexto e análise quando pertinente
   - Mínimo {min_words} palavras, máximo {max_words}
   - PROIBIDO: asteriscos (**), underscores (__), cerquilhas (#) — use APENAS HTML
   - PROIBIDO: envelopar o conteúdo com blocos markdown de código (como ```html ou ```json). O JSON deve conter a string HTML limpa.
   - PROIBIDO: inventar informações para alongar o texto
   - Números: por extenso de zero a dez, numerais a partir de 11
   - Moedas: R$ antes do número. Acima de mil: R$ 1,5 milhão

4. Inclua ao final do conteúdo um bloco HTML de fontes consultadas:
   <h2>Fontes consultadas</h2>
   <ul>
     <li><a href="URL" target="_blank" rel="nofollow">Nome do Veículo</a></li>
     ...
   </ul>

5. EXCERPT: 2 frases objetivas, máx 300 caracteres, sem aspas, sem repetir o título.

6. TAGS: 3 a 5 entidades reais do texto (pessoas, instituições, leis). PROIBIDO palavras genéricas.

7. seo_title: máx 60 caracteres. Palavra-chave principal no início.

8. seo_description: máx 155 caracteres. Inclua micro CTA ("Saiba mais", "Entenda", "Veja").

9. CATEGORIA: Escolha UMA: {categories}

10. fontes_consultadas: lista JSON dos nomes dos veículos utilizados.

=== MANUAL DE FOTOJORNALISMO — CURADORIA DE IMAGEM ===

Você é o Editor de Fotografia. Defina a melhor imagem factual para esta matéria.

--- PRINCÍPIO FUNDAMENTAL ---
Se a notícia é sobre uma PESSOA, busque uma foto dessa pessoa.
Nome + STATUS JORNALÍSTICO que define seu papel na notícia.
  "Daniel Vorcaro preso" — não "Daniel Vorcaro helicóptero PF"
  "Lula" — não "Lula discurso"
STATUS = condição (preso, ministro, réu). CENA = detalhe do momento (helicóptero, plenário). Use status, nunca cena.
Não temos câmera no local. Não simule o momento.

Se NÃO tem protagonista humano, busque o OBJETO FÍSICO REAL.

--- LÓGICA ---
PESSOA: nome + status. "Daniel Vorcaro preso" — "Lula" — "Moise Kouame".
ESPORTE: clubes. "Vasco Fluminense" — "Palmeiras São Paulo".
LOCAL: nome. "Banco Central" — "Refinaria Irã".
EVENTO: local + tipo. "enchente RS" — "operação PF".
ABSTRATO: conceito. "vacinação SUS" — "inteligência artificial".

--- REGRAS ---
- Máx 2-3 palavras para pessoas (apenas nome).
- Máx 3-4 palavras para locais/eventos.
- Sem AND/OR. Nomes curtos.
- Para commons: NOME FORMAL COMPLETO.

11. imagem_busca_gov: Termo mínimo. Pessoas: apenas o nome. Locais: apenas o local. Máx 3 palavras.
12. imagem_busca_commons: Nome formal/enciclopédico para Wikimedia.
13. block_stock_images: true para notícia factual. false apenas para temas abstratos.
14. legenda_imagem: Legenda factual (máx 150 chars).

=== FONTES ===

{fontes_texto}

---

Retorne APENAS JSON válido com estas chaves:
titulo, conteudo, excerpt, tags, seo_title, seo_description, categoria, fontes_consultadas, imagem_busca_gov, imagem_busca_commons, block_stock_images, legenda_imagem
"""


def collect_sources(topic: dict) -> list[dict]:
    """
    Para cada tema trending, raspa o conteúdo completo das fontes.
    Retorna lista de dicts com conteúdo extraído + metadata.
    """
    urls = topic.get("urls", [])
    sources_set = set()  # para deduplicar por portal
    collected = []

    for url in urls:
        if len(collected) >= MAX_SOURCES_PER_TOPIC:
            break

        # Identificar portal a partir dos títulos do topic
        portal_name = "Desconhecido"
        for t in topic.get("titles", []):
            if t.get("url") == url:
                portal_name = t.get("portal_name", "Desconhecido")
                break

        # Deduplicar por portal (1 fonte por veículo) antes de extrair
        if portal_name in sources_set:
            logger.debug("Portal %s já coletado, pulando URL: %s", portal_name, url[:60])
            continue

        # Extrair conteúdo via newspaper3k + BS4 + Jina Reader Fallback
        result = extrair_conteudo_completo(url)
        content = result.get("conteudo", "") if result else ""
        word_count = len(content.split())

        # Falha definitiva na extração (Erro ou conteúdo muito curto/paywall)
        if not result or word_count < MIN_CONTENT_WORDS:
            logger.warning("Falha irredutível ao extrair URL %s", url)
            content = ""
            word_count = 0
            if not result:
                fallback_title = next((t.get("title", "") for t in topic.get("titles", []) if t.get("url") == url), "Título Indisponível")
                result = {"titulo": fallback_title, "imagem": ""}

        sources_set.add(portal_name)
        collected.append({
            "portal_name": portal_name,
            "url": url,
            "titulo": result.get("titulo", ""),
            "conteudo": content,
            "imagem": result.get("imagem", ""),
            "word_count": word_count,
        })

        logger.info("Fonte coletada: %s (%d palavras) — %s", portal_name, word_count, url[:60])

    logger.info("Fontes coletadas para '%s': %d", topic["topic_label"][:50], len(collected))
    return collected


def _build_fontes_texto(sources: list[dict]) -> str:
    """Constrói o bloco de texto das fontes para o prompt."""
    blocos = []
    for i, src in enumerate(sources, 1):
        bloco = (
            f"--- FONTE {i}: {src['portal_name']} ---\n"
            f"URL: {src['url']}\n"
            f"Título: {src['titulo']}\n\n"
            f"{src['conteudo'][:1500]}\n"  # Limitar cada fonte a ~1500 chars limitando tokens
        )
        blocos.append(bloco)
    return "\n\n".join(blocos)


def synthesize_article(topic: dict) -> tuple[dict | None, list[dict]]:
    """
    Pipeline completo de síntese:
    1. Coleta conteúdo das fontes
    2. Monta prompt
    3. Chama LLM via cascata TIER_CONSOLIDATOR
    4. Retorna (artigo_dict, fontes_coletadas) ou (None, [])
    """
    # 1. Coletar fontes
    sources = collect_sources(topic)
    if len(sources) < MIN_SOURCES_PER_TOPIC:
        logger.warning(
            "Fontes insuficientes para '%s': %d (mínimo: %d)",
            topic["topic_label"][:50], len(sources), MIN_SOURCES_PER_TOPIC,
        )
        return None, sources

    # 2. Montar prompt
    fontes_texto = _build_fontes_texto(sources)

    user_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
        n_fontes=len(sources),
        min_words=MIN_SYNTHESIS_WORDS,
        max_words=MAX_SYNTHESIS_WORDS,
        categories=", ".join(config.VALID_CATEGORIES),
        fontes_texto=fontes_texto,
    )

    logger.info(
        "Sintetizando '%s' com %d fontes via TIER_CONSOLIDATOR",
        topic["topic_label"][:50], len(sources),
    )

    # 3. Chamar LLM
    result, provider = call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tier=TIER_CONSOLIDATOR,
        parse_json=True,
    )

    if result is None:
        logger.error("LLM falhou para síntese de '%s'", topic["topic_label"][:50])
        return None, sources

    logger.info(
        "Artigo sintetizado via %s: '%s'",
        provider, result.get("titulo", "?")[:60],
    )

    # Adicionar metadata do provider
    result["_llm_provider"] = provider
    result["_sources"] = sources

    return result, sources


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from scraper_homes import scrape_all_portals
    from detector_trending import detect_trending

    print("Raspando portais...")
    titles = scrape_all_portals(cycle_number=1)
    print(f"Títulos: {len(titles)}")

    print("Detectando trending...")
    trending = detect_trending(titles)
    print(f"Trending: {len(trending)}")

    if trending:
        print(f"\nSintetizando primeiro tema: {trending[0]['topic_label'][:60]}")
        article, sources = synthesize_article(trending[0])
        if article:
            print(f"\n{'='*60}")
            print(f"TÍTULO: {article.get('titulo', '?')}")
            print(f"PALAVRAS: ~{len(article.get('conteudo', '').split())}")
            print(f"FONTES: {article.get('fontes_consultadas', [])}")
            print(f"PROVIDER: {article.get('_llm_provider', '?')}")
        else:
            print("Síntese falhou (fontes insuficientes ou LLM error)")
