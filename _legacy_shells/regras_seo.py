# -*- coding: utf-8 -*-



def obter_diretrizes_seo():

    return f"""

    [SYSTEM INSTRUCTION: ARQUITETURA DE SEO E COPYWRITING MULTICANAL]



    1. VISIBILIDADE EM BUSCA E MOTORES DE IA (AEO)

    - O primeiro parágrafo DEVE responder à principal pergunta do tema.

    - Parágrafos autossuficientes: É proibido usar referências vagas como "como dito acima".

    - Use o mesmo nome canônico para órgãos nas repetições (Ex: STF).



    2. WEBWRITING E ESCANEABILIDADE HTML

    - Quebre o texto com subtítulos `<h2>` a cada 2 ou 3 parágrafos, formulados como perguntas (FAQ).

    - Use `<strong>` nas entidades cruciais no primeiro terço do texto.

    - Use listas `<ul>` se a notícia enumerar prazos, fatores ou principais pontos.



    3. TITULAÇÃO E METADADOS

    - `h1_title`: 70 a 90 caracteres. Palavra-chave nas primeiras 8 palavras.

    - `seo_title`: ATÉ 60 CARACTERES MÁXIMO (evita truncamento na SERP).

    - `meta_description`: ATÉ 155 CARACTERES MÁXIMO.



    4. TAXONOMIA: ENTITY TAGS (A Categoria será definida pelo Python)

    - Extraia NO MÁXIMO 3 a 5 tags.

    - Devem ser Entidades Reais contidas no texto (Pessoas, Instituições, Leis). É proibido usar palavras genéricas ou adjetivos.



    5. MULTICANALIDADE E JSON DE SAÍDA EXIGIDO:

    Retorne APENAS um objeto JSON válido, sem markdown:

    {{

      "h1_title": "Titulo otimizado de 70 a 90 caracteres",

      "seo_title": "Titulo curto de SERP ate 60 caracteres",

      "meta_description": "Resumo de 155 caracteres com micro CTA",

      "corpo_html": "<p>Lide answer-first com link da fonte.</p><h2>Sua pergunta FAQ?</h2><p>Texto detalhado com aspas e <strong>entidades</strong>.</p><ul><li>Lista</li></ul>",

      "tags": ["Nome Próprio", "Instituição", "Tema Factual"],

      "push_notification": "Chamada curtissima ate 80 chars",

      "social_copy": "Copy conciso para WhatsApp ou Instagram"

    }}

    """
