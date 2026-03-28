"""Redação de artigo jornalístico via LLM PREMIUM."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from shared.schemas import LLMRequest

logger = logging.getLogger(__name__)

# Categorias válidas do portal
VALID_CATEGORIES = [
    "Segmentos de Tecnologia",
    "Política & Poder",
    "Saúde & Bem-Estar",
    "Economia & Negócios",
    "Meio Ambiente",
    "Segurança & Defesa",
    "Educação & Cultura",
    "Esportes",
    "Internacional",
    "Entretenimento",
    "Agronegócio",
    "Infraestrutura & Urbanismo",
    "Ciência & Inovação",
    "Direito & Justiça",
    "Energia & Clima",
    "Turismo",
]

# System prompt para o Editor-Chefe Sênior
LLM_SYSTEM_PROMPT = (
    "Você é o Editor-Chefe Sênior do portal brasileira.news. "
    "Sua missão: reescrever/traduzir/editar notícias com máxima qualidade jornalística. "
    "TOLERÂNCIA ZERO PARA ALUCINAÇÃO — é ESTRITAMENTE PROIBIDO inventar fatos, dados, "
    "estatísticas, nomes ou citações que não existam no texto original."
)


def _build_rewrite_prompt(
    titulo_original: str,
    conteudo: str,
    url_fonte: str,
    fonte_nome: str,
    editoria: str,
    rag_context: str,
) -> str:
    """Constrói o prompt de reescrita baseado no template V1 battle-tested."""
    categories_str = ", ".join(VALID_CATEGORIES)

    return f"""Reescreva o artigo abaixo seguindo OBRIGATORIAMENTE estas regras:

=== MANUAL DE REDAÇÃO ===

1. IDIOMA: Português do Brasil. Se o texto estiver em outro idioma, traduza com precisão jornalística.

2. TÍTULO (titulo): 70 a 90 caracteres. Palavra-chave nas primeiras 8 palavras. Sem prefixos (OFICIAL:, GOVERNO:, Via X:).

3. CONTEÚDO (conteudo) — mínimo 400 palavras:
   - OBRIGATÓRIO: TODOS os parágrafos de texto fluído devem ser envolvidos e fechados corretamente por tags <p> e </p>. NUNCA deixe texto solto.
   - 1º parágrafo LIDE: responda O quê? Quem? Quando? Onde? Como? Por quê?
   - OBRIGATÓRIO no 1º ou 2º parágrafo: citar a fonte com link HTML:
     De acordo com informações do/da <a href="{url_fonte}" target="_blank" rel="nofollow">{fonte_nome}</a>
   - Use <h2> a cada 2-3 parágrafos formulados como PERGUNTAS (estilo FAQ)
   - Use <strong> nas entidades cruciais no primeiro terço do texto
   - Use <blockquote> APENAS para aspas diretas reais do texto original — NUNCA invente aspas
   - Use <ul> quando houver listas de prazos, fatores ou pontos principais
   - PROIBIDO: asteriscos (**), underscores (__), cerquilhas (#) — use APENAS HTML
   - PROIBIDO: envelopar o conteúdo com blocos markdown de código (como ```html ou ```json). O JSON deve conter a string HTML limpa.
   - PROIBIDO: inventar informações para alongar o texto artificialmente
   - Números: por extenso de zero a dez, numerais a partir de 11
   - Moedas: R$ antes do número. Acima de mil: R$ 1,5 milhão
   - Linguagem chapa-branca: transforme linguagem promocional em relato objetivo
   - Presunção de inocência: use "suspeito de", "acusado de"
   - CVV (188): incluir SOMENTE se a notícia tratar explicitamente de suicídio

4. EXCERPT (excerpt): 2 frases objetivas, máx 300 chars, sem aspas, sem repetir o título.

5. CATEGORIA (categoria): Escolha UMA: {categories_str}

6. TAGS (tags): 3 a 5 entidades reais do texto (pessoas, instituições, leis). PROIBIDO palavras genéricas ou adjetivos.

=== MANUAL DE SEO ===

7. seo_title: máx 60 caracteres (evita truncamento na SERP). Palavra-chave principal no início.

8. seo_description: máx 155 caracteres. Inclua micro CTA (ex: "Saiba mais", "Entenda", "Veja").

9. push_notification: chamada curtíssima até 80 chars para notificação push.

=== MANUAL DE FOTOJORNALISMO — CURADORIA DE IMAGEM ===

Você é o Editor de Fotografia do portal. Sua missão é definir a melhor imagem factual para esta matéria.
A imagem será buscada em bancos de agências oficiais (EBC, Gov.br, Flickr governamental) e na Wikimedia Commons.
Analise o texto COMPLETO que você acabou de reescrever e determine:

--- PRINCÍPIO FUNDAMENTAL ---
Se a notícia é sobre uma PESSOA, busque uma foto dessa pessoa.
Use o nome + o STATUS JORNALÍSTICO que define o papel dela NA NOTÍCIA.
  "Daniel Vorcaro preso" — não "Daniel Vorcaro helicóptero PF"
  "Lula" — não "Lula coletiva" ou "Lula discurso"
  "André Mendonça" — não "André Mendonça sessão STF"
STATUS é a condição da pessoa (preso, ministro, réu, candidato). CENA é detalhe do momento (helicóptero, plenário, microfone). Use status, nunca cena.
Nós NÃO temos câmera no local do fato. Não tente simular o momento.

Se a notícia NÃO tem protagonista humano, busque o OBJETO FÍSICO REAL.

--- LÓGICA DE BUSCA ---

PESSOA PÚBLICA:
  Nome + status jornalístico quando relevante.
  "Daniel Vorcaro preso" — "Leila Pereira presidente" — "Moise Kouame"
  Se o status é óbvio (presidente Lula), o nome basta: "Lula".

CONFRONTO ESPORTIVO:
  Apenas os nomes dos dois clubes/atletas.
  "Vasco Fluminense" — "Palmeiras São Paulo"

LUGAR / INSTITUIÇÃO (sem protagonista humano):
  Nome do local. "Banco Central" — "Refinaria Irã"

DESASTRE / OPERAÇÃO (o evento é o fato):
  Local + tipo. "enchente RS" — "operação Polícia Federal"

TEMA ABSTRATO (sem pessoa nem local):
  Conceito visual. "vacinação SUS" — "inteligência artificial"

--- REGRAS TÉCNICAS ---
- Para pessoas: nome + 1 palavra de status se relevante. Máx 3 palavras.
- Para locais/eventos: máx 3-4 palavras.
- Nomes curtos: "Lula", "Moro", "Bolsonaro", "STF".
- Sem AND/OR.
- Para commons: NOME FORMAL COMPLETO.

10. imagem_busca_gov: Nome da pessoa (+ status se relevante) ou nome do local. Máx 3 palavras.
11. imagem_busca_commons: Nome formal/enciclopédico da pessoa ou entidade para Wikimedia.
12. block_stock_images: true para qualquer notícia factual real. false APENAS para temas abstratos atemporais.
13. legenda_imagem: Legenda factual (máx 150 chars).

Retorne APENAS JSON válido com estas chaves EXATAS:
titulo, conteudo, excerpt, categoria, tags, seo_title, seo_description, push_notification, imagem_busca_gov, imagem_busca_commons, block_stock_images, legenda_imagem

--- ARTIGO ORIGINAL ---

Título: {titulo_original}

Fonte: {fonte_nome}

URL da fonte: {url_fonte}

Editoria sugerida: {editoria}

{rag_context}

{conteudo[:4000]}
"""


def _extract_json_from_response(content: str) -> Optional[dict[str, Any]]:
    """Extrai e valida JSON da resposta LLM com múltiplas estratégias."""
    content = content.strip()

    # Estratégia 1: Remover blocos markdown de código
    if content.startswith("```"):
        # Remove ```json ou ``` no início
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        # Remove ``` no final
        content = content.rsplit("```", 1)[0] if "```" in content else content
        content = content.strip()

    # Estratégia 2: Tentar parse direto
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Estratégia 3: Extrair JSON usando regex (encontra objeto JSON entre chaves)
    try:
        # Procura por objeto JSON completo (mais profundo possível)
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            return json.loads(match.group(0))
    except json.JSONDecodeError:
        pass

    return None


def _validate_article_data(data: dict[str, Any]) -> bool:
    """Valida que todos os campos obrigatórios estão presentes no artigo."""
    required_fields = [
        "titulo",
        "conteudo",
        "excerpt",
        "categoria",
        "tags",
        "seo_title",
        "seo_description",
        "push_notification",
        "imagem_busca_gov",
        "imagem_busca_commons",
        "block_stock_images",
        "legenda_imagem",
    ]
    return all(field in data and data[field] is not None for field in required_fields)


async def write_article(
    router,
    titulo_original: str,
    conteudo: str,
    url_fonte: str,
    fonte_nome: str,
    editoria: str,
    similar_articles: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Redige artigo jornalístico completo via LLM PREMIUM."""

    # Contexto RAG (artigos similares)
    rag_context = ""
    if similar_articles:
        rag_context = "\n\nARTIGOS ANTERIORES RELACIONADOS (evite repetir, acrescente profundidade):\n"
        for art in similar_articles[:3]:
            rag_context += f"- {art.get('titulo', 'N/A')} ({art.get('editoria', 'N/A')})\n"

    prompt = _build_rewrite_prompt(
        titulo_original=titulo_original,
        conteudo=conteudo,
        url_fonte=url_fonte,
        fonte_nome=fonte_nome,
        editoria=editoria,
        rag_context=rag_context,
    )

    for attempt in range(3):
        request = LLMRequest(
            task_type="redacao_artigo",
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=4000,
            timeout=60,
        )
        response = await router.route_request(request)

        try:
            data = _extract_json_from_response(response.content)
            if data is None:
                raise json.JSONDecodeError("Não foi possível extrair JSON", response.content, 0)

            if _validate_article_data(data):
                return data
            else:
                missing = [
                    f for f in [
                        "titulo", "conteudo", "excerpt", "categoria", "tags",
                        "seo_title", "seo_description", "push_notification",
                        "imagem_busca_gov", "imagem_busca_commons",
                        "block_stock_images", "legenda_imagem",
                    ] if f not in data or data.get(f) is None
                ]
                logger.warning("JSON válido mas campos ausentes: %s (tentativa %d)", missing, attempt + 1)

        except (json.JSONDecodeError, KeyError) as e:
            if attempt < 2:
                logger.warning("Resposta LLM inválida (tentativa %d): %s", attempt + 1, str(e))
                continue

    # Fallback: usar conteúdo extraído diretamente
    logger.warning("Todas as tentativas de redação falharam, usando conteúdo extraído")
    return {
        "titulo": titulo_original,
        "conteudo": f"<p>{conteudo[:2000]}</p>",
        "excerpt": conteudo[:155] if len(conteudo) <= 155 else conteudo[:152] + "...",
        "categoria": editoria if editoria in VALID_CATEGORIES else VALID_CATEGORIES[0],
        "tags": [],
        "seo_title": titulo_original[:60],
        "seo_description": f"Saiba mais sobre: {titulo_original[:140]}",
        "push_notification": titulo_original[:80],
        "imagem_busca_gov": "",
        "imagem_busca_commons": "",
        "block_stock_images": True,
        "legenda_imagem": "",
    }
