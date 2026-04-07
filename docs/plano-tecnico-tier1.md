# Plano Técnico TIER 1 — Homes Dinâmicas

**brasileira.news — Arquitetura de Curadoria Autônoma de Nível TIER 1**  
**Versão 3.0 — Abril 2026**

---

## Sumário Executivo

O plano anterior (v2.0) introduziu a saída do tagDiv e a construção de um Block Theme próprio com 6 zonas fixas controladas por ACF. Esse modelo funciona, mas opera no teto do TIER 2. Portais como Folha, G1, UOL e Metrópoles não trabalham com zonas predefinidas — eles trabalham com **blocos editoriais dinâmicos**: a homepage tem 20-30 seções distintas que aparecem, desaparecem, reordenam e se transformam conforme o ciclo de notícias.

Esta versão reconstrói a arquitetura sobre um único princípio: **o layout é dados, não código**. Em vez de templates com posições fixas, o tema renderiza qualquer sequência de blocos a partir de um JSON armazenado no banco. O agente curador — agora chamado de Curador V4 — escreve esse JSON. O PHP apenas o executa.

As consequências práticas:
- A homepage pode ter 8 blocos ou 28 blocos, dependendo da intensidade do ciclo de notícias
- Um macrotema como "Guerra no Irã" ganha sua própria seção na homepage e sua própria subhome em minutos, sem deploy de código
- Layouts mudam por período do dia automaticamente
- Cada subhome usa o mesmo motor — mesma API, mesma lógica de cache, mesma extensibilidade

---

## 1. Filosofia: O que Significa Operar TIER 1

### 1.1 Homepage como Produto Editorial Vivo

No TIER 1, a homepage não é um template. É um produto editorial que o editor-chefe reconfigura múltiplas vezes ao dia. No modelo tradicional, isso significa reuniões de pauta, decisões manuais no CMS e deploy de mudanças estruturais. No modelo brasileira.news, o **agente curador automatiza esse papel**.

A diferença fundamental entre TIER 2 e TIER 1 não é quantidade de conteúdo — é **cadência de mudança estrutural**. Portais TIER 2 publicam muito mas mudam a estrutura da homepage raramente. Portais TIER 1 mudam a própria arquitetura da página conforme o noticiário:

| Evento | TIER 2 (zonas fixas) | TIER 1 (blocos dinâmicos) |
|--------|---------------------|--------------------------|
| Breaking news | Banner fixo no topo | Bloco `breaking` criado, posição 0, full-width vermelho |
| Novo macrotema (Guerra no Irã) | Aparece dentro de "Internacional" | Bloco `macrotema` criado, posição 2, seção própria + subhome |
| Eleições 2026 começa | Sem mudança estrutural | Bloco `especial` permanente criado, subhome dedicada |
| Madrugada com pouco conteúdo | Mesmas 6 zonas, algumas vazias | 8-12 blocos ativos, prominência para `mais_lidas` |
| Horário nobre 18h-22h | Mesmas 6 zonas | 25-28 blocos ativos, `manchete` maior, `ticker` proeminente |

### 1.2 O Curador como Editor-Chefe Algorítmico

O agente curador não apenas seleciona artigos — ele decide a **estrutura** da página. Isso requer que o sistema técnico suporte:

1. Criar e destruir blocos sem alteração de código
2. Reordenar dezenas de blocos atomicamente
3. Fazer expirar blocos por tempo (breaking news de 2h atrás)
4. Promover um macrotema de homepage para subhome completa
5. Ajustar a densidade visual conforme o período do dia

### 1.3 Princípios de Design do Sistema

- **Layout é dados**: o JSON em `wp_options` ou tabela customizada é a única fonte de verdade da estrutura da página
- **Zero código por mudança editorial**: adicionar um novo tipo de cobertura especial não requer deploy
- **Cache por fragmento**: cada bloco tem TTL independente; um bloco `breaking` expira em 1 min, um bloco `mais_lidas` expira em 5 min
- **Fallback sempre presente**: se o JSON do curador estiver ausente ou corrompido, o motor renderiza uma homepage automática a partir dos posts mais recentes
- **Extensibilidade ilimitada**: novos tipos de bloco são registrados como partials PHP — o resto do sistema não muda

---

## 2. Modelo de Dados: Blocos Editoriais Dinâmicos

### 2.1 Schema do Layout

O layout de cada página é um objeto JSON. O homepage é identificado pelo `page_id` da página frontal do WordPress (`get_option('page_on_front')`). Subhomes têm seus próprios `page_id`.

```json
{
  "page_id": 18135,
  "page_type": "homepage",
  "layout_mode": "horario_nobre",
  "updated_at": "2026-04-06T18:00:00-03:00",
  "cycle_id": "a3f7c2d1-9b4e-4a8f-b6c3-d2e1f0a9b8c7",
  "curador_version": "4.0",
  "blocks": [
    {
      "id": "blk_001",
      "type": "breaking",
      "position": 0,
      "visible": true,
      "config": {
        "post_id": 45123,
        "label": "AO VIVO",
        "style": "fullwidth_red",
        "auto_expire_minutes": 120
      }
    },
    {
      "id": "blk_002",
      "type": "manchete",
      "position": 1,
      "visible": true,
      "config": {
        "principal": 45100,
        "submanchetes": [45098, 45095, 45090],
        "style": "hero_large"
      }
    },
    {
      "id": "blk_003",
      "type": "macrotema",
      "position": 2,
      "visible": true,
      "config": {
        "tag_id": 8901,
        "label": "Guerra no Irã",
        "icon": "globe",
        "posts": [45080, 45075, 45060, 45055],
        "style": "highlight_band",
        "temporary": true,
        "created_at": "2026-04-01T10:00:00-03:00",
        "subhome_page_id": 18200
      }
    },
    {
      "id": "blk_004",
      "type": "editoria",
      "position": 3,
      "visible": true,
      "config": {
        "category_id": 15285,
        "label": "Política & Poder",
        "posts": [45070, 45065, 45055, 45050, 45045],
        "style": "grid_5",
        "show_more_link": true,
        "more_link_url": "/politica"
      }
    },
    {
      "id": "blk_ad_1",
      "type": "publicidade",
      "position": 4,
      "visible": true,
      "config": {
        "slot": "home_mid_leaderboard",
        "size": "728x90",
        "fallback": "house_ad"
      }
    },
    {
      "id": "blk_005",
      "type": "colunistas",
      "position": 5,
      "visible": true,
      "config": {
        "colunistas": [
          {"author_id": 12, "post_id": 44900},
          {"author_id": 15, "post_id": 44850},
          {"author_id": 8,  "post_id": 44820},
          {"author_id": 23, "post_id": 44800}
        ],
        "style": "carousel_horizontal"
      }
    },
    {
      "id": "blk_006",
      "type": "editoria",
      "position": 6,
      "visible": true,
      "config": {
        "category_id": 15661,
        "label": "Economia & Negócios",
        "posts": [45040, 45035, 45030, 45025],
        "style": "grid_4_sidebar",
        "sidebar_widget": "cotacoes"
      }
    },
    {
      "id": "blk_007",
      "type": "ticker",
      "position": 7,
      "visible": true,
      "config": {
        "sources": ["ibovespa", "dolar", "euro", "bitcoin"],
        "style": "bar_dark",
        "auto_refresh_seconds": 60
      }
    },
    {
      "id": "blk_008",
      "type": "editoria",
      "position": 8,
      "visible": true,
      "config": {
        "category_id": 15410,
        "label": "Tecnologia",
        "posts": [45020, 45015, 45010, 45005, 45000, 44995],
        "style": "grid_6_mosaic"
      }
    },
    {
      "id": "blk_ad_2",
      "type": "publicidade",
      "position": 9,
      "visible": true,
      "config": {
        "slot": "home_mid2_leaderboard",
        "size": "728x90",
        "fallback": "house_ad"
      }
    },
    {
      "id": "blk_009",
      "type": "ultimas",
      "position": 10,
      "visible": true,
      "config": {
        "count": 15,
        "style": "feed_list",
        "auto_refresh_seconds": 120
      }
    },
    {
      "id": "blk_010",
      "type": "opiniao",
      "position": 11,
      "visible": true,
      "config": {
        "posts": [44980, 44970, 44960],
        "style": "cards_editorial"
      }
    },
    {
      "id": "blk_011",
      "type": "mais_lidas",
      "position": 12,
      "visible": true,
      "config": {
        "period": "24h",
        "count": 10,
        "style": "numbered_list"
      }
    },
    {
      "id": "blk_012",
      "type": "regional",
      "position": 13,
      "visible": true,
      "config": {
        "ufs": ["DF", "SP", "RJ", "MG", "RS"],
        "posts_per_uf": 2,
        "style": "tabs_regional"
      }
    },
    {
      "id": "blk_013",
      "type": "video",
      "position": 14,
      "visible": true,
      "config": {
        "featured_post_id": 44950,
        "playlist": [44945, 44940, 44935],
        "style": "player_featured"
      }
    },
    {
      "id": "blk_014",
      "type": "newsletter_cta",
      "position": 15,
      "visible": true,
      "config": {
        "variant": "inline_banner",
        "headline": "Receba as notícias mais importantes do dia",
        "cta_text": "Assinar Boletim Gratuito"
      }
    }
  ]
}
```

### 2.2 Registro de Tipos de Bloco

Cada tipo de bloco é definido por um schema de configuração, um partial de renderização PHP, variantes visuais disponíveis e comportamento de cache/expiração.

| Tipo | Descrição | Cache TTL | Auto-expire | Variantes de Estilo |
|------|-----------|-----------|-------------|---------------------|
| `breaking` | Banner de última hora, full-width, vermelho | 60s | sim (minutes) | `fullwidth_red`, `fullwidth_orange`, `ticker_bar` |
| `manchete` | Hero principal com submanchetes | 120s | não | `hero_large`, `hero_split`, `hero_video` |
| `macrotema` | Cobertura cruzada de categorias, temporária | 180s | não | `highlight_band`, `section_full`, `sidebar_box` |
| `editoria` | Seção por categoria | 180s | não | `grid_3`, `grid_4_sidebar`, `grid_5`, `grid_6_mosaic`, `list_compact` |
| `colunistas` | Carrossel horizontal de colunistas | 300s | não | `carousel_horizontal`, `grid_4` |
| `ultimas` | Feed cronológico de últimas | 60s | não | `feed_list`, `feed_cards` |
| `mais_lidas` | Mais lidas por período | 300s | não | `numbered_list`, `sidebar_compact` |
| `opiniao` | Artigos de opinião/editorial | 300s | não | `cards_editorial`, `list_byline` |
| `video` | Seção de vídeos com player | 300s | não | `player_featured`, `grid_videos` |
| `podcast` | Últimos episódios de podcast | 600s | não | `player_podcast`, `list_episodes` |
| `especial` | Destaque de reportagem especial | 600s | não | `banner_especial`, `card_destaque` |
| `regional` | Seções geográficas por UF | 300s | não | `tabs_regional`, `grid_ufs` |
| `galeria` | Galeria de fotos em destaque | 300s | não | `slideshow`, `grid_fotos` |
| `trending` | Tópicos em alta / mais buscados | 120s | não | `tags_cloud`, `list_trending` |
| `newsletter_cta` | Captura de e-mail | 3600s | não | `inline_banner`, `modal_trigger`, `sidebar_box` |
| `publicidade` | Slot de anúncio | 0 (no-cache) | não | vários sizes IAB |
| `ticker` | Cotações financeiras ao vivo | 60s | não | `bar_dark`, `bar_light` |
| `custom` | Bloco livre para expansão futura | 300s | não | livre |

### 2.3 Armazenamento

Os layouts são armazenados na tabela `wp_options` com a chave `brasileira_layout_{page_id}`, serializada como JSON. Para portais com 100+ subhomes, uma tabela customizada `wp_brasileira_layouts` oferece melhor performance de leitura.

```sql
CREATE TABLE wp_brasileira_layouts (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    page_id      BIGINT UNSIGNED NOT NULL,
    page_type    VARCHAR(32)  NOT NULL DEFAULT 'homepage',
    layout_mode  VARCHAR(32)  NOT NULL DEFAULT 'normal',
    layout_json  LONGTEXT     NOT NULL,
    cycle_id     VARCHAR(64)  NOT NULL,
    updated_at   DATETIME     NOT NULL,
    updated_by   VARCHAR(64)  NOT NULL DEFAULT 'curador',
    INDEX idx_page_id (page_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 3. Arquitetura do Tema: `brasileira-theme`

### 3.1 Estrutura de Arquivos

```
brasileira-theme/
├── theme.json                        # Design tokens (Barlow, #3490B4, tokens completos)
├── style.css                         # Cabeçalho do tema (metadados)
├── functions.php                     # Bootstrap: CPTs, REST API, block registry, hooks
├── templates/
│   ├── index.html                    # Fallback default
│   ├── front-page.html               # Homepage (renderiza blocos dinâmicos)
│   ├── single.html                   # Artigo individual
│   ├── page-subhome.html             # Subhome por editoria (mesmo motor dinâmico)
│   ├── page-macrotema.html           # Página de macrotema (tag-based)
│   ├── page-especial.html            # Página de especial/data journalism
│   ├── page-colunista.html           # Página individual de colunista
│   ├── archive.html                  # Arquivo genérico (fallback)
│   ├── search.html
│   └── 404.html
├── parts/
│   ├── header.html                   # Cabeçalho: logo, nav, busca
│   ├── footer.html                   # Rodapé: links, créditos, redes sociais
│   └── topbar.html                   # Barra superior: clima, tempo, cotações rápidas
├── blocks/                           # Um diretório por tipo de bloco
│   ├── breaking/
│   │   ├── render.php
│   │   └── style.css
│   ├── manchete/
│   │   ├── render.php
│   │   └── style.css
│   ├── macrotema/
│   │   ├── render.php
│   │   └── style.css
│   ├── editoria/
│   │   ├── render.php
│   │   └── style.css
│   ├── colunistas/
│   │   ├── render.php
│   │   └── style.css
│   ├── ultimas/
│   │   ├── render.php
│   │   └── style.css
│   ├── mais-lidas/
│   │   ├── render.php
│   │   └── style.css
│   ├── opiniao/
│   │   ├── render.php
│   │   └── style.css
│   ├── video/
│   │   ├── render.php
│   │   └── style.css
│   ├── podcast/
│   │   ├── render.php
│   │   └── style.css
│   ├── especial/
│   │   ├── render.php
│   │   └── style.css
│   ├── regional/
│   │   ├── render.php
│   │   └── style.css
│   ├── galeria/
│   │   ├── render.php
│   │   └── style.css
│   ├── trending/
│   │   ├── render.php
│   │   └── style.css
│   ├── newsletter-cta/
│   │   ├── render.php
│   │   └── style.css
│   ├── publicidade/
│   │   ├── render.php
│   │   └── style.css
│   ├── ticker/
│   │   ├── render.php
│   │   └── style.css
│   └── custom/
│       ├── render.php
│       └── style.css
├── inc/
│   ├── class-block-registry.php      # Registry: tipos, schemas, TTLs
│   ├── class-layout-engine.php       # Motor: JSON → HTML sequencial
│   ├── class-rest-api.php            # CRUD de layouts + macrotemas
│   ├── class-cache-manager.php       # Fragment cache por bloco (Redis/APCu)
│   ├── class-ad-manager.php          # Gerenciamento de slots de anúncio
│   └── class-fallback-renderer.php   # Homepage automática (sem curador)
└── assets/
    ├── css/
    │   ├── base.css                  # Grid, tipografia, cores, utilitários
    │   └── editor.css                # Estilos do editor Gutenberg
    └── js/
        ├── live-updates.js           # SSE para breaking/ultimas
        └── lazy-blocks.js            # Intersection Observer para blocos abaixo da dobra
```

### 3.2 theme.json Completo

```json
{
  "$schema": "https://schemas.wp.org/trunk/theme.json",
  "version": 3,
  "settings": {
    "appearanceTools": true,
    "useRootPaddingAwareAlignments": true,
    "layout": {
      "contentSize": "1200px",
      "wideSize": "1400px"
    },
    "color": {
      "palette": [
        { "slug": "br-primary",    "color": "#3490B4", "name": "Azul Petróleo — Primário" },
        { "slug": "br-primary-dk", "color": "#256F91", "name": "Azul Petróleo Escuro" },
        { "slug": "br-primary-lt", "color": "#5AB0D4", "name": "Azul Petróleo Claro" },
        { "slug": "br-breaking",   "color": "#C0392B", "name": "Vermelho Breaking" },
        { "slug": "br-breaking-lt","color": "#E74C3C", "name": "Vermelho Breaking Claro" },
        { "slug": "br-text",       "color": "#444444", "name": "Texto Principal" },
        { "slug": "br-text-muted", "color": "#717176", "name": "Texto Secundário" },
        { "slug": "br-bg",         "color": "#FFFFFF", "name": "Fundo Branco" },
        { "slug": "br-bg-alt",     "color": "#F1F4F7", "name": "Fundo Cinza Claro" },
        { "slug": "br-border",     "color": "#EDEDED", "name": "Borda" },
        { "slug": "br-macrotema",  "color": "#1A3A5C", "name": "Azul Macrotema" },
        { "slug": "br-opiniao",    "color": "#2C3E50", "name": "Cinza Editorial" }
      ],
      "gradients": [
        {
          "slug": "br-hero-overlay",
          "gradient": "linear-gradient(180deg, rgba(52,144,180,0) 0%, rgba(52,144,180,0.85) 100%)",
          "name": "Hero Overlay Petróleo"
        },
        {
          "slug": "br-dark-overlay",
          "gradient": "linear-gradient(180deg, rgba(0,0,0,0) 40%, rgba(0,0,0,0.78) 100%)",
          "name": "Overlay Escuro"
        }
      ],
      "defaultPalette": false,
      "defaultGradients": false
    },
    "typography": {
      "fontFamilies": [
        {
          "fontFamily": "'Barlow', sans-serif",
          "slug": "barlow",
          "name": "Barlow",
          "fontFace": [
            {
              "fontFamily": "Barlow",
              "fontWeight": "400",
              "fontStyle": "normal",
              "fontDisplay": "swap",
              "src": ["https://fonts.gstatic.com/s/barlow/v12/7cHpv4kjgoGqM7E3b8s8.woff2"]
            },
            {
              "fontFamily": "Barlow",
              "fontWeight": "600",
              "fontStyle": "normal",
              "fontDisplay": "swap",
              "src": ["https://fonts.gstatic.com/s/barlow/v12/7cHqv4kjgoGqM7E3t-4s51ostz0rdg.woff2"]
            },
            {
              "fontFamily": "Barlow",
              "fontWeight": "700",
              "fontStyle": "normal",
              "fontDisplay": "swap",
              "src": ["https://fonts.gstatic.com/s/barlow/v12/7cHqv4kjgoGqM7E3p-ws51ostz0rdg.woff2"]
            },
            {
              "fontFamily": "Barlow",
              "fontWeight": "800",
              "fontStyle": "normal",
              "fontDisplay": "swap",
              "src": ["https://fonts.gstatic.com/s/barlow/v12/7cHqv4kjgoGqM7E3w-0s51ostz0rdg.woff2"]
            }
          ]
        },
        {
          "fontFamily": "'Barlow Condensed', sans-serif",
          "slug": "barlow-condensed",
          "name": "Barlow Condensed",
          "fontFace": [
            {
              "fontFamily": "Barlow Condensed",
              "fontWeight": "700",
              "fontStyle": "normal",
              "fontDisplay": "swap",
              "src": ["https://fonts.gstatic.com/s/barlowcondensed/v12/HTxwL3I-JCGChYJ8VI-L6OO_au7B6xTrF3DWqA.woff2"]
            }
          ]
        }
      ],
      "fontSizes": [
        { "slug": "xs",   "size": "0.75rem",  "name": "Extra Pequeno" },
        { "slug": "sm",   "size": "0.875rem", "name": "Pequeno" },
        { "slug": "base", "size": "1rem",     "name": "Base" },
        { "slug": "lg",   "size": "1.125rem", "name": "Grande" },
        { "slug": "xl",   "size": "1.25rem",  "name": "XL" },
        { "slug": "2xl",  "size": "1.5rem",   "name": "2XL" },
        { "slug": "3xl",  "size": "1.875rem", "name": "3XL" },
        { "slug": "4xl",  "size": "2.25rem",  "name": "4XL" },
        { "slug": "5xl",  "size": "3rem",     "name": "5XL — Manchete" },
        { "slug": "6xl",  "size": "3.75rem",  "name": "6XL — Super Manchete" }
      ],
      "defaultFontSizes": false,
      "customFontSize": true,
      "lineHeight": true,
      "letterSpacing": true
    },
    "spacing": {
      "spacingSizes": [
        { "slug": "1",  "size": "0.25rem", "name": "4px" },
        { "slug": "2",  "size": "0.5rem",  "name": "8px" },
        { "slug": "3",  "size": "0.75rem", "name": "12px" },
        { "slug": "4",  "size": "1rem",    "name": "16px" },
        { "slug": "5",  "size": "1.25rem", "name": "20px" },
        { "slug": "6",  "size": "1.5rem",  "name": "24px" },
        { "slug": "8",  "size": "2rem",    "name": "32px" },
        { "slug": "10", "size": "2.5rem",  "name": "40px" },
        { "slug": "12", "size": "3rem",    "name": "48px" },
        { "slug": "16", "size": "4rem",    "name": "64px" }
      ],
      "defaultSpacingSizes": false,
      "units": ["px", "rem", "%", "vw"]
    },
    "shadow": {
      "defaultPresets": false,
      "presets": [
        { "slug": "card",    "shadow": "0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.06)", "name": "Card" },
        { "slug": "card-lg", "shadow": "0 4px 16px rgba(0,0,0,.12)", "name": "Card Grande" }
      ]
    }
  },
  "styles": {
    "color": {
      "background": "var(--wp--preset--color--br-bg)",
      "text": "var(--wp--preset--color--br-text)"
    },
    "typography": {
      "fontFamily": "var(--wp--preset--font-family--barlow)",
      "fontSize": "var(--wp--preset--font-size--base)",
      "lineHeight": "1.6"
    },
    "spacing": {
      "blockGap": "var(--wp--preset--spacing--6)"
    },
    "elements": {
      "h1": {
        "typography": {
          "fontFamily": "var(--wp--preset--font-family--barlow)",
          "fontSize": "var(--wp--preset--font-size--5xl)",
          "fontWeight": "700",
          "lineHeight": "1.1"
        }
      },
      "h2": {
        "typography": {
          "fontFamily": "var(--wp--preset--font-family--barlow)",
          "fontSize": "var(--wp--preset--font-size--4xl)",
          "fontWeight": "700",
          "lineHeight": "1.2"
        }
      },
      "h3": {
        "typography": {
          "fontFamily": "var(--wp--preset--font-family--barlow)",
          "fontSize": "var(--wp--preset--font-size--2xl)",
          "fontWeight": "600",
          "lineHeight": "1.3"
        }
      },
      "link": {
        "color": { "text": "var(--wp--preset--color--br-primary)" },
        ":hover": { "color": { "text": "var(--wp--preset--color--br-primary-dk)" } }
      }
    }
  },
  "customTemplates": [
    { "name": "front-page",     "title": "Homepage — Curadoria IA",        "postTypes": ["page"] },
    { "name": "page-subhome",   "title": "Subhome por Editoria",           "postTypes": ["page"] },
    { "name": "page-macrotema", "title": "Macrotema — Cobertura Especial", "postTypes": ["page"] },
    { "name": "page-colunista", "title": "Página de Colunista",            "postTypes": ["page"] },
    { "name": "single",         "title": "Artigo",                         "postTypes": ["post"] }
  ],
  "templateParts": [
    { "name": "header",  "title": "Cabeçalho", "area": "header" },
    { "name": "footer",  "title": "Rodapé",    "area": "footer" },
    { "name": "topbar",  "title": "Barra Superior", "area": "uncategorized" }
  ]
}
```

---

## 4. Layout Engine (PHP)

### 4.1 `inc/class-layout-engine.php`

O motor de layout lê o JSON armazenado, ordena os blocos por posição, aplica regras de cache por fragmento e renderiza cada bloco chamando seu partial PHP. É o coração do sistema.

```php
<?php
/**
 * Brasileira Layout Engine
 * Motor central de renderização de blocos dinâmicos.
 *
 * @package brasileira-theme
 */

if ( ! defined( 'ABSPATH' ) ) exit;

class Brasileira_Layout_Engine {

    private Brasileira_Block_Registry $registry;
    private Brasileira_Cache_Manager  $cache;

    public function __construct() {
        $this->registry = Brasileira_Block_Registry::instance();
        $this->cache    = Brasileira_Cache_Manager::instance();
    }

    /**
     * Ponto de entrada principal. Chamado pelo front-page.html.
     */
    public function render_page( int $page_id ): void {
        $layout = $this->get_layout( $page_id );

        if ( ! $layout || empty( $layout['blocks'] ) ) {
            $this->render_fallback( $page_id );
            return;
        }

        // Carrega apenas o CSS dos tipos de bloco presentes nesta página
        $this->enqueue_block_styles( $layout['blocks'] );

        // Ordena por posição
        $blocks = $layout['blocks'];
        usort( $blocks, fn( $a, $b ) => ( $a['position'] ?? 99 ) <=> ( $b['position'] ?? 99 ) );

        echo '<main class="brasileira-homepage" data-layout-mode="' 
             . esc_attr( $layout['layout_mode'] ?? 'normal' ) . '">';

        foreach ( $blocks as $block ) {
            if ( empty( $block['visible'] ) ) continue;
            if ( $this->is_expired( $block ) ) continue;

            echo $this->render_block( $block );
        }

        echo '</main>';
    }

    /**
     * Renderiza um único bloco com fragment cache.
     */
    public function render_block( array $block ): string {
        $type   = $block['type']   ?? 'custom';
        $bid    = $block['id']     ?? uniqid( 'blk_' );
        $config = $block['config'] ?? [];

        if ( ! $this->registry->type_exists( $type ) ) return '';

        $ttl       = $this->registry->get_ttl( $type );
        $cache_key = "brasileira_blk_{$bid}_{$type}";

        // Tipos como publicidade nunca são cacheados
        if ( $ttl > 0 ) {
            $cached = wp_cache_get( $cache_key, 'brasileira_blocks' );
            if ( false !== $cached ) return $cached;
        }

        $template = get_theme_file_path( "blocks/{$type}/render.php" );
        if ( ! file_exists( $template ) ) return '';

        ob_start();
        // Disponibiliza variáveis para o template
        $block_id     = $bid;
        $block_type   = $type;
        $block_config = $config;
        include $template;
        $html = ob_get_clean();

        if ( $ttl > 0 ) {
            wp_cache_set( $cache_key, $html, 'brasileira_blocks', $ttl );
        }

        return $html;
    }

    /**
     * Lê layout do armazenamento (tabela customizada ou wp_options).
     */
    public function get_layout( int $page_id ): ?array {
        global $wpdb;

        // Tenta tabela customizada primeiro (melhor performance)
        $table = $wpdb->prefix . 'brasileira_layouts';
        if ( $wpdb->get_var( "SHOW TABLES LIKE '{$table}'" ) === $table ) {
            $row = $wpdb->get_var(
                $wpdb->prepare( "SELECT layout_json FROM {$table} WHERE page_id = %d ORDER BY id DESC LIMIT 1", $page_id )
            );
            if ( $row ) return json_decode( $row, true );
        }

        // Fallback para wp_options
        $json = get_option( "brasileira_layout_{$page_id}" );
        return $json ? json_decode( $json, true ) : null;
    }

    /**
     * Persiste layout (upsert).
     */
    public function save_layout( int $page_id, array $layout ): bool {
        global $wpdb;

        $layout['updated_at'] = current_time( 'c' );
        $json = wp_json_encode( $layout );

        $table = $wpdb->prefix . 'brasileira_layouts';
        if ( $wpdb->get_var( "SHOW TABLES LIKE '{$table}'" ) === $table ) {
            $existing = $wpdb->get_var(
                $wpdb->prepare( "SELECT id FROM {$table} WHERE page_id = %d", $page_id )
            );
            if ( $existing ) {
                $wpdb->update( $table,
                    [ 'layout_json' => $json, 'layout_mode' => $layout['layout_mode'] ?? 'normal',
                      'cycle_id' => $layout['cycle_id'] ?? '', 'updated_at' => current_time( 'mysql' ),
                      'updated_by' => $layout['curador_version'] ?? 'manual' ],
                    [ 'page_id' => $page_id ]
                );
            } else {
                $wpdb->insert( $table,
                    [ 'page_id' => $page_id, 'page_type' => $layout['page_type'] ?? 'homepage',
                      'layout_mode' => $layout['layout_mode'] ?? 'normal', 'layout_json' => $json,
                      'cycle_id' => $layout['cycle_id'] ?? '', 'updated_at' => current_time( 'mysql' ),
                      'updated_by' => $layout['curador_version'] ?? 'manual' ]
                );
            }
            return true;
        }

        return update_option( "brasileira_layout_{$page_id}", $json, false );
    }

    /**
     * Verifica se um bloco expirou pelo campo auto_expire_minutes.
     */
    private function is_expired( array $block ): bool {
        $minutes = $block['config']['auto_expire_minutes'] ?? 0;
        if ( ! $minutes ) return false;

        $created = $block['config']['created_at'] ?? ( $block['config']['updated_at'] ?? null );
        if ( ! $created ) return false;

        $expires = strtotime( $created ) + ( $minutes * 60 );
        return time() > $expires;
    }

    /**
     * Carrega CSS apenas dos tipos de bloco presentes na página.
     */
    private function enqueue_block_styles( array $blocks ): void {
        $types_loaded = [];
        foreach ( $blocks as $block ) {
            $type = $block['type'] ?? '';
            if ( $type && ! isset( $types_loaded[ $type ] ) ) {
                $css_file = get_theme_file_path( "blocks/{$type}/style.css" );
                if ( file_exists( $css_file ) ) {
                    wp_enqueue_style(
                        "brasileira-block-{$type}",
                        get_theme_file_uri( "blocks/{$type}/style.css" ),
                        [],
                        filemtime( $css_file )
                    );
                }
                $types_loaded[ $type ] = true;
            }
        }
    }

    /**
     * Fallback automático quando não há layout do curador.
     */
    private function render_fallback( int $page_id ): void {
        $fallback = new Brasileira_Fallback_Renderer();
        $fallback->render( $page_id );
    }
}
```

### 4.2 `inc/class-block-registry.php`

```php
<?php
/**
 * Brasileira Block Registry
 * Define todos os tipos de bloco disponíveis, seus schemas e TTLs.
 */

if ( ! defined( 'ABSPATH' ) ) exit;

class Brasileira_Block_Registry {

    private static ?self $instance = null;
    private array $types = [];

    public static function instance(): self {
        if ( null === self::$instance ) {
            self::$instance = new self();
            self::$instance->register_defaults();
        }
        return self::$instance;
    }

    private function register_defaults(): void {
        $this->register( 'breaking', [
            'label'    => 'Breaking News',
            'ttl'      => 60,
            'required' => ['post_id', 'style'],
            'optional' => ['label', 'auto_expire_minutes'],
            'styles'   => ['fullwidth_red', 'fullwidth_orange', 'ticker_bar'],
        ] );
        $this->register( 'manchete', [
            'label'    => 'Manchete Principal',
            'ttl'      => 120,
            'required' => ['principal'],
            'optional' => ['submanchetes', 'style'],
            'styles'   => ['hero_large', 'hero_split', 'hero_video'],
        ] );
        $this->register( 'macrotema', [
            'label'    => 'Macrotema Especial',
            'ttl'      => 180,
            'required' => ['tag_id', 'label', 'posts'],
            'optional' => ['icon', 'style', 'temporary', 'created_at', 'subhome_page_id'],
            'styles'   => ['highlight_band', 'section_full', 'sidebar_box'],
        ] );
        $this->register( 'editoria', [
            'label'    => 'Bloco de Editoria',
            'ttl'      => 180,
            'required' => ['category_id', 'label', 'posts'],
            'optional' => ['style', 'show_more_link', 'more_link_url', 'sidebar_widget'],
            'styles'   => ['grid_3', 'grid_4_sidebar', 'grid_5', 'grid_6_mosaic', 'list_compact'],
        ] );
        $this->register( 'colunistas', [
            'label'    => 'Colunistas',
            'ttl'      => 300,
            'required' => ['colunistas'],
            'optional' => ['style'],
            'styles'   => ['carousel_horizontal', 'grid_4'],
        ] );
        $this->register( 'ultimas', [
            'label'    => 'Últimas Notícias',
            'ttl'      => 60,
            'required' => ['count'],
            'optional' => ['style', 'auto_refresh_seconds'],
            'styles'   => ['feed_list', 'feed_cards'],
        ] );
        $this->register( 'mais_lidas', [
            'label'    => 'Mais Lidas',
            'ttl'      => 300,
            'required' => ['period', 'count'],
            'optional' => ['style'],
            'styles'   => ['numbered_list', 'sidebar_compact'],
        ] );
        $this->register( 'opiniao', [
            'label'    => 'Opinião',
            'ttl'      => 300,
            'required' => ['posts'],
            'optional' => ['style'],
            'styles'   => ['cards_editorial', 'list_byline'],
        ] );
        $this->register( 'video', [
            'label'    => 'Vídeos',
            'ttl'      => 300,
            'required' => ['featured_post_id'],
            'optional' => ['playlist', 'style'],
            'styles'   => ['player_featured', 'grid_videos'],
        ] );
        $this->register( 'podcast', [
            'label'    => 'Podcast',
            'ttl'      => 600,
            'required' => [],
            'optional' => ['episodes', 'style'],
            'styles'   => ['player_podcast', 'list_episodes'],
        ] );
        $this->register( 'especial', [
            'label'    => 'Especial / Reportagem',
            'ttl'      => 600,
            'required' => ['post_id'],
            'optional' => ['style'],
            'styles'   => ['banner_especial', 'card_destaque'],
        ] );
        $this->register( 'regional', [
            'label'    => 'Regional / UFs',
            'ttl'      => 300,
            'required' => ['ufs'],
            'optional' => ['posts_per_uf', 'style'],
            'styles'   => ['tabs_regional', 'grid_ufs'],
        ] );
        $this->register( 'galeria', [
            'label'    => 'Galeria de Fotos',
            'ttl'      => 300,
            'required' => ['post_ids'],
            'optional' => ['style'],
            'styles'   => ['slideshow', 'grid_fotos'],
        ] );
        $this->register( 'trending', [
            'label'    => 'Em Alta / Trending',
            'ttl'      => 120,
            'required' => [],
            'optional' => ['tags', 'style'],
            'styles'   => ['tags_cloud', 'list_trending'],
        ] );
        $this->register( 'newsletter_cta', [
            'label'    => 'Newsletter CTA',
            'ttl'      => 3600,
            'required' => ['variant'],
            'optional' => ['headline', 'cta_text'],
            'styles'   => ['inline_banner', 'modal_trigger', 'sidebar_box'],
        ] );
        $this->register( 'publicidade', [
            'label'    => 'Anúncio Publicitário',
            'ttl'      => 0,
            'required' => ['slot', 'size'],
            'optional' => ['fallback'],
            'styles'   => [],
        ] );
        $this->register( 'ticker', [
            'label'    => 'Cotações / Ticker',
            'ttl'      => 60,
            'required' => ['sources'],
            'optional' => ['style', 'auto_refresh_seconds'],
            'styles'   => ['bar_dark', 'bar_light'],
        ] );
        $this->register( 'custom', [
            'label'    => 'Bloco Customizado',
            'ttl'      => 300,
            'required' => [],
            'optional' => ['html', 'style'],
            'styles'   => [],
        ] );
    }

    public function register( string $type, array $definition ): void {
        $this->types[ $type ] = $definition;
    }

    public function type_exists( string $type ): bool {
        return isset( $this->types[ $type ] );
    }

    public function get_ttl( string $type ): int {
        return $this->types[ $type ]['ttl'] ?? 300;
    }

    public function all(): array {
        return $this->types;
    }
}
```

---

## 5. Templates de Renderização dos Blocos

### 5.1 `blocks/breaking/render.php`

```php
<?php
/**
 * Bloco: breaking
 * Banner de última hora, full-width, com expiração automática.
 *
 * Variáveis disponíveis: $block_id, $block_type, $block_config
 */

$post_id = (int) ( $block_config['post_id'] ?? 0 );
$label   = $block_config['label']   ?? 'URGENTE';
$style   = $block_config['style']   ?? 'fullwidth_red';

if ( ! $post_id ) return;

$post  = get_post( $post_id );
if ( ! $post ) return;

$url   = get_permalink( $post );
$title = get_the_title( $post );
?>
<div class="brasileira-block brasileira-block--breaking br-style-<?php echo esc_attr( $style ); ?>"
     data-block-id="<?php echo esc_attr( $block_id ); ?>"
     role="alert"
     aria-live="assertive">
    <div class="br-breaking__inner">
        <span class="br-breaking__label"><?php echo esc_html( $label ); ?></span>
        <a href="<?php echo esc_url( $url ); ?>" class="br-breaking__link">
            <?php echo esc_html( $title ); ?>
        </a>
        <span class="br-breaking__time">
            <?php echo human_time_diff( get_the_time( 'U', $post ), time() ); ?> atrás
        </span>
    </div>
</div>
```

### 5.2 `blocks/manchete/render.php`

```php
<?php
/**
 * Bloco: manchete
 * Hero principal com 1-3 submanchetes. Três variantes visuais.
 */

$principal_id    = (int) ( $block_config['principal']    ?? 0 );
$submanchetes_ids = array_map( 'intval', $block_config['submanchetes'] ?? [] );
$style           = $block_config['style'] ?? 'hero_large';

if ( ! $principal_id ) return;

$principal = get_post( $principal_id );
if ( ! $principal ) return;

$thumb_url  = get_the_post_thumbnail_url( $principal, 'brasileira-manchete' );
$url        = get_permalink( $principal );
$title      = get_the_title( $principal );
$excerpt    = get_the_excerpt( $principal );
$category   = get_the_category( $principal->ID );
$cat_name   = $category ? $category[0]->name : '';
$cat_url    = $category ? get_category_link( $category[0]->term_id ) : '';
?>
<section class="brasileira-block brasileira-block--manchete br-manchete--<?php echo esc_attr( $style ); ?>"
         data-block-id="<?php echo esc_attr( $block_id ); ?>">
    <div class="br-manchete__principal">
        <?php if ( $thumb_url ) : ?>
        <a href="<?php echo esc_url( $url ); ?>" class="br-manchete__img-link" tabindex="-1" aria-hidden="true">
            <img src="<?php echo esc_url( $thumb_url ); ?>"
                 alt="<?php echo esc_attr( $title ); ?>"
                 loading="eager"
                 fetchpriority="high"
                 class="br-manchete__img">
            <div class="br-manchete__overlay"></div>
        </a>
        <?php endif; ?>

        <div class="br-manchete__content">
            <?php if ( $cat_name ) : ?>
            <a href="<?php echo esc_url( $cat_url ); ?>" class="br-manchete__editoria">
                <?php echo esc_html( $cat_name ); ?>
            </a>
            <?php endif; ?>

            <h1 class="br-manchete__title">
                <a href="<?php echo esc_url( $url ); ?>"><?php echo esc_html( $title ); ?></a>
            </h1>

            <?php if ( $style === 'hero_large' && $excerpt ) : ?>
            <p class="br-manchete__excerpt"><?php echo esc_html( wp_trim_words( $excerpt, 25 ) ); ?></p>
            <?php endif; ?>
        </div>
    </div>

    <?php if ( ! empty( $submanchetes_ids ) ) : ?>
    <ul class="br-manchete__submanchetes">
        <?php foreach ( $submanchetes_ids as $sub_id ) :
            $sub = get_post( $sub_id );
            if ( ! $sub ) continue;
            $sub_url   = get_permalink( $sub );
            $sub_title = get_the_title( $sub );
            $sub_thumb = get_the_post_thumbnail_url( $sub, 'brasileira-card-sm' );
            $sub_cat   = get_the_category( $sub->ID );
            $sub_cat_n = $sub_cat ? $sub_cat[0]->name : '';
        ?>
        <li class="br-manchete__sub-item">
            <?php if ( $sub_thumb ) : ?>
            <a href="<?php echo esc_url( $sub_url ); ?>" class="br-manchete__sub-img-link" tabindex="-1">
                <img src="<?php echo esc_url( $sub_thumb ); ?>"
                     alt="<?php echo esc_attr( $sub_title ); ?>"
                     loading="lazy"
                     class="br-manchete__sub-img">
            </a>
            <?php endif; ?>
            <div class="br-manchete__sub-body">
                <?php if ( $sub_cat_n ) : ?>
                <span class="br-manchete__sub-editoria"><?php echo esc_html( $sub_cat_n ); ?></span>
                <?php endif; ?>
                <a href="<?php echo esc_url( $sub_url ); ?>" class="br-manchete__sub-title">
                    <?php echo esc_html( $sub_title ); ?>
                </a>
            </div>
        </li>
        <?php endforeach; ?>
    </ul>
    <?php endif; ?>
</section>
```

### 5.3 `blocks/macrotema/render.php`

```php
<?php
/**
 * Bloco: macrotema
 * Cobertura especial cruzada de categorias, com label e ícone.
 * Criado e destruído dinamicamente pelo curador V4.
 */

$tag_id   = (int) ( $block_config['tag_id']  ?? 0 );
$label    = $block_config['label']  ?? 'Cobertura Especial';
$icon     = $block_config['icon']   ?? 'alert';
$posts_ids = array_map( 'intval', $block_config['posts'] ?? [] );
$style    = $block_config['style']  ?? 'highlight_band';
$subhome  = (int) ( $block_config['subhome_page_id'] ?? 0 );

if ( empty( $posts_ids ) ) return;

$icon_map = [
    'globe'  => '🌐',
    'alert'  => '⚠️',
    'fire'   => '🔥',
    'vote'   => '🗳️',
    'money'  => '💹',
    'health' => '🏥',
];
$icon_char = $icon_map[ $icon ] ?? '📌';
?>
<section class="brasileira-block brasileira-block--macrotema br-macrotema--<?php echo esc_attr( $style ); ?>"
         data-block-id="<?php echo esc_attr( $block_id ); ?>">
    <div class="br-macrotema__header">
        <span class="br-macrotema__icon" aria-hidden="true"><?php echo $icon_char; ?></span>
        <h2 class="br-macrotema__label"><?php echo esc_html( $label ); ?></h2>
        <?php if ( $subhome ) : ?>
        <a href="<?php echo esc_url( get_permalink( $subhome ) ); ?>" class="br-macrotema__ver-mais">
            Ver cobertura completa →
        </a>
        <?php endif; ?>
    </div>

    <div class="br-macrotema__posts">
        <?php
        $first = true;
        foreach ( $posts_ids as $pid ) :
            $p = get_post( $pid );
            if ( ! $p ) continue;
            $p_url   = get_permalink( $p );
            $p_title = get_the_title( $p );
            $p_thumb = get_the_post_thumbnail_url( $p, $first ? 'brasileira-macrotema-featured' : 'brasileira-card-sm' );
            $p_cat   = get_the_category( $p->ID );
            $p_cat_n = $p_cat ? $p_cat[0]->name : '';
        ?>
        <article class="br-macrotema__post <?php echo $first ? 'br-macrotema__post--featured' : ''; ?>">
            <?php if ( $p_thumb ) : ?>
            <a href="<?php echo esc_url( $p_url ); ?>" class="br-macrotema__post-img-link" tabindex="-1">
                <img src="<?php echo esc_url( $p_thumb ); ?>"
                     alt="<?php echo esc_attr( $p_title ); ?>"
                     loading="<?php echo $first ? 'eager' : 'lazy'; ?>"
                     class="br-macrotema__post-img">
            </a>
            <?php endif; ?>
            <div class="br-macrotema__post-body">
                <?php if ( $p_cat_n ) : ?>
                <span class="br-macrotema__post-cat"><?php echo esc_html( $p_cat_n ); ?></span>
                <?php endif; ?>
                <a href="<?php echo esc_url( $p_url ); ?>" class="br-macrotema__post-title">
                    <?php echo esc_html( $p_title ); ?>
                </a>
                <span class="br-macrotema__post-time">
                    <?php echo human_time_diff( get_the_time( 'U', $p ), time() ); ?> atrás
                </span>
            </div>
        </article>
        <?php
            $first = false;
        endforeach;
        ?>
    </div>
</section>
```

### 5.4 `blocks/editoria/render.php`

```php
<?php
/**
 * Bloco: editoria
 * Seção de categoria com 3-6 artigos. Cinco variantes de layout.
 */

$cat_id   = (int) ( $block_config['category_id'] ?? 0 );
$label    = $block_config['label']          ?? '';
$posts_ids = array_map( 'intval', $block_config['posts'] ?? [] );
$style    = $block_config['style']          ?? 'grid_5';
$more_url = $block_config['more_link_url']  ?? '';
$sidebar  = $block_config['sidebar_widget'] ?? '';

if ( ! $cat_id || empty( $posts_ids ) ) return;

if ( ! $label && $cat_id ) {
    $cat   = get_category( $cat_id );
    $label = $cat ? $cat->name : '';
}
if ( ! $more_url && $cat_id ) {
    $more_url = get_category_link( $cat_id );
}
?>
<section class="brasileira-block brasileira-block--editoria br-editoria--<?php echo esc_attr( $style ); ?>"
         data-block-id="<?php echo esc_attr( $block_id ); ?>"
         data-cat-id="<?php echo esc_attr( $cat_id ); ?>">

    <header class="br-editoria__header">
        <h2 class="br-editoria__title">
            <a href="<?php echo esc_url( $more_url ); ?>"><?php echo esc_html( $label ); ?></a>
        </h2>
        <?php if ( $more_url ) : ?>
        <a href="<?php echo esc_url( $more_url ); ?>" class="br-editoria__ver-mais">
            Ver tudo →
        </a>
        <?php endif; ?>
    </header>

    <?php if ( $sidebar === 'cotacoes' ) : ?>
    <div class="br-editoria__with-sidebar">
        <div class="br-editoria__main">
    <?php endif; ?>

    <div class="br-editoria__grid">
        <?php
        $first = true;
        foreach ( $posts_ids as $pid ) :
            $p = get_post( $pid );
            if ( ! $p ) continue;
            $p_url    = get_permalink( $p );
            $p_title  = get_the_title( $p );
            $p_size   = $first ? 'brasileira-card-lg' : 'brasileira-card-sm';
            $p_thumb  = get_the_post_thumbnail_url( $p, $p_size );
            $p_time   = human_time_diff( get_the_time( 'U', $p ), time() );
        ?>
        <article class="br-editoria__item <?php echo $first ? 'br-editoria__item--principal' : ''; ?>">
            <?php if ( $p_thumb ) : ?>
            <a href="<?php echo esc_url( $p_url ); ?>" class="br-editoria__img-link" tabindex="-1">
                <img src="<?php echo esc_url( $p_thumb ); ?>"
                     alt="<?php echo esc_attr( $p_title ); ?>"
                     loading="lazy"
                     class="br-editoria__img">
            </a>
            <?php endif; ?>
            <div class="br-editoria__body">
                <a href="<?php echo esc_url( $p_url ); ?>" class="br-editoria__item-title">
                    <?php echo esc_html( $p_title ); ?>
                </a>
                <span class="br-editoria__item-time"><?php echo $p_time; ?> atrás</span>
            </div>
        </article>
        <?php
            $first = false;
        endforeach;
        ?>
    </div>

    <?php if ( $sidebar === 'cotacoes' ) : ?>
        </div><!-- .br-editoria__main -->
        <aside class="br-editoria__sidebar">
            <?php
            // Widget de cotações — injetado pelo AgentCotacoes ou wp_cache
            $cotacoes_html = wp_cache_get( 'brasileira_widget_cotacoes', 'brasileira_widgets' );
            if ( $cotacoes_html ) {
                echo $cotacoes_html;
            } else {
                echo '<div class="br-cotacoes-placeholder" aria-label="Carregando cotações..."></div>';
            }
            ?>
        </aside>
    </div><!-- .br-editoria__with-sidebar -->
    <?php endif; ?>

</section>
```

### 5.5 `blocks/colunistas/render.php`

```php
<?php
/**
 * Bloco: colunistas
 * Carrossel horizontal de colunistas com foto, nome e título da última coluna.
 */

$colunistas = $block_config['colunistas'] ?? [];
$style      = $block_config['style']     ?? 'carousel_horizontal';

if ( empty( $colunistas ) ) return;
?>
<section class="brasileira-block brasileira-block--colunistas br-colunistas--<?php echo esc_attr( $style ); ?>"
         data-block-id="<?php echo esc_attr( $block_id ); ?>">
    <header class="br-colunistas__header">
        <h2 class="br-colunistas__title">Colunistas</h2>
    </header>

    <div class="br-colunistas__track" role="list">
        <?php foreach ( $colunistas as $item ) :
            $author_id = (int) ( $item['author_id'] ?? 0 );
            $post_id   = (int) ( $item['post_id']   ?? 0 );
            if ( ! $author_id || ! $post_id ) continue;

            $author     = get_user_by( 'id', $author_id );
            if ( ! $author ) continue;

            $post       = get_post( $post_id );
            if ( ! $post ) continue;

            $name       = $author->display_name;
            $avatar_url = get_avatar_url( $author_id, [ 'size' => 96 ] );
            $col_url    = get_permalink( $post );
            $col_title  = get_the_title( $post );
            $col_time   = human_time_diff( get_the_time( 'U', $post ), time() );
            $author_url = get_author_posts_url( $author_id );
        ?>
        <article class="br-colunistas__item" role="listitem">
            <a href="<?php echo esc_url( $author_url ); ?>" class="br-colunistas__author-link">
                <img src="<?php echo esc_url( $avatar_url ); ?>"
                     alt="<?php echo esc_attr( $name ); ?>"
                     width="64" height="64"
                     loading="lazy"
                     class="br-colunistas__avatar">
                <span class="br-colunistas__author-name"><?php echo esc_html( $name ); ?></span>
            </a>
            <a href="<?php echo esc_url( $col_url ); ?>" class="br-colunistas__col-title">
                <?php echo esc_html( wp_trim_words( $col_title, 12 ) ); ?>
            </a>
            <span class="br-colunistas__col-time"><?php echo $col_time; ?> atrás</span>
        </article>
        <?php endforeach; ?>
    </div>
</section>
```

### 5.6 `blocks/mais-lidas/render.php`

```php
<?php
/**
 * Bloco: mais_lidas
 * Lista numerada das mais lidas por período.
 */

$period = $block_config['period'] ?? '24h';
$count  = (int) ( $block_config['count'] ?? 10 );
$style  = $block_config['style'] ?? 'numbered_list';

// Busca por meta_key de views (plugin Post Views Counter ou similar)
$period_days = match ( $period ) {
    '1h'    => 0,
    '24h'   => 1,
    '7d'    => 7,
    '30d'   => 30,
    default => 1,
};

$args = [
    'post_type'      => 'post',
    'post_status'    => 'publish',
    'posts_per_page' => $count,
    'meta_key'       => 'pvc_count', // Post Views Counter
    'orderby'        => 'meta_value_num',
    'order'          => 'DESC',
    'date_query'     => $period_days > 0
        ? [[ 'after' => "{$period_days} days ago" ]]
        : [],
];

$posts = get_posts( $args );
if ( empty( $posts ) ) return;
?>
<section class="brasileira-block brasileira-block--mais-lidas br-mais-lidas--<?php echo esc_attr( $style ); ?>"
         data-block-id="<?php echo esc_attr( $block_id ); ?>">
    <header class="br-mais-lidas__header">
        <h2 class="br-mais-lidas__title">Mais Lidas</h2>
        <span class="br-mais-lidas__period">
            <?php echo $period === '24h' ? 'Últimas 24h' : ( $period === '7d' ? 'Esta semana' : $period ); ?>
        </span>
    </header>

    <ol class="br-mais-lidas__list">
        <?php foreach ( $posts as $index => $p ) :
            $p_url    = get_permalink( $p );
            $p_title  = get_the_title( $p );
            $p_thumb  = get_the_post_thumbnail_url( $p, 'brasileira-card-xs' );
            $p_cat    = get_the_category( $p->ID );
            $p_cat_n  = $p_cat ? $p_cat[0]->name : '';
        ?>
        <li class="br-mais-lidas__item">
            <span class="br-mais-lidas__num"><?php echo $index + 1; ?></span>
            <?php if ( $p_thumb && $style !== 'sidebar_compact' ) : ?>
            <a href="<?php echo esc_url( $p_url ); ?>" tabindex="-1">
                <img src="<?php echo esc_url( $p_thumb ); ?>"
                     alt="<?php echo esc_attr( $p_title ); ?>"
                     loading="lazy"
                     class="br-mais-lidas__img">
            </a>
            <?php endif; ?>
            <div class="br-mais-lidas__body">
                <?php if ( $p_cat_n ) : ?>
                <span class="br-mais-lidas__cat"><?php echo esc_html( $p_cat_n ); ?></span>
                <?php endif; ?>
                <a href="<?php echo esc_url( $p_url ); ?>" class="br-mais-lidas__item-title">
                    <?php echo esc_html( $p_title ); ?>
                </a>
            </div>
        </li>
        <?php endforeach; ?>
    </ol>
</section>
```

### 5.7 `blocks/publicidade/render.php`

```php
<?php
/**
 * Bloco: publicidade
 * Slot de anúncio IAB. Não é cacheado.
 */

$slot     = $block_config['slot']     ?? '';
$size     = $block_config['size']     ?? '728x90';
$fallback = $block_config['fallback'] ?? 'house_ad';

if ( ! $slot ) return;

[ $width, $height ] = explode( 'x', $size ) + [ '728', '90' ];
?>
<div class="brasileira-block brasileira-block--publicidade br-ad--<?php echo esc_attr( $size ); ?>"
     data-block-id="<?php echo esc_attr( $block_id ); ?>"
     data-ad-slot="<?php echo esc_attr( $slot ); ?>"
     aria-label="Publicidade"
     style="min-height:<?php echo esc_attr( $height ); ?>px">
    <!-- Google AdSense / DFP slot -->
    <ins class="adsbygoogle"
         style="display:block;width:<?php echo esc_attr( $width ); ?>px;height:<?php echo esc_attr( $height ); ?>px"
         data-ad-client="ca-pub-XXXXXXXXXXXXXXXX"
         data-ad-slot="<?php echo esc_attr( $slot ); ?>">
    </ins>
    <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
</div>
```

---

## 6. REST API — CRUD Completo de Layouts

### 6.1 `inc/class-rest-api.php`

```php
<?php
/**
 * Brasileira REST API — CRUD de Layouts Dinâmicos
 * Interface para o agente Curador V4.
 *
 * Endpoints:
 *   GET    /wp-json/brasileira/v1/layout/{page_id}
 *   PUT    /wp-json/brasileira/v1/layout/{page_id}
 *   PATCH  /wp-json/brasileira/v1/layout/{page_id}
 *   POST   /wp-json/brasileira/v1/layout/{page_id}/blocks
 *   DELETE /wp-json/brasileira/v1/layout/{page_id}/blocks/{block_id}
 *   PATCH  /wp-json/brasileira/v1/layout/{page_id}/blocks/{block_id}
 *   POST   /wp-json/brasileira/v1/macrotema
 *   DELETE /wp-json/brasileira/v1/macrotema/{tag_id}
 *   GET    /wp-json/brasileira/v1/block-types
 *   GET    /wp-json/brasileira/v1/health
 */

if ( ! defined( 'ABSPATH' ) ) exit;

class Brasileira_REST_API {

    private Brasileira_Layout_Engine $engine;
    private Brasileira_Block_Registry $registry;

    public function __construct() {
        $this->engine   = new Brasileira_Layout_Engine();
        $this->registry = Brasileira_Block_Registry::instance();
    }

    public function register_routes(): void {
        $ns = 'brasileira/v1';

        // Layout CRUD
        register_rest_route( $ns, '/layout/(?P<page_id>\d+)', [
            [ 'methods' => 'GET',   'callback' => [ $this, 'get_layout' ],     'permission_callback' => [ $this, 'permission' ] ],
            [ 'methods' => 'PUT',   'callback' => [ $this, 'put_layout' ],     'permission_callback' => [ $this, 'permission' ] ],
            [ 'methods' => 'PATCH', 'callback' => [ $this, 'patch_layout' ],   'permission_callback' => [ $this, 'permission' ] ],
        ] );

        // Blocks CRUD
        register_rest_route( $ns, '/layout/(?P<page_id>\d+)/blocks', [
            [ 'methods' => 'POST', 'callback' => [ $this, 'add_block' ], 'permission_callback' => [ $this, 'permission' ] ],
        ] );
        register_rest_route( $ns, '/layout/(?P<page_id>\d+)/blocks/(?P<block_id>[a-zA-Z0-9_\-]+)', [
            [ 'methods' => 'DELETE', 'callback' => [ $this, 'delete_block' ], 'permission_callback' => [ $this, 'permission' ] ],
            [ 'methods' => 'PATCH',  'callback' => [ $this, 'update_block' ], 'permission_callback' => [ $this, 'permission' ] ],
        ] );

        // Macrotema
        register_rest_route( $ns, '/macrotema', [
            [ 'methods' => 'POST', 'callback' => [ $this, 'create_macrotema' ], 'permission_callback' => [ $this, 'permission' ] ],
        ] );
        register_rest_route( $ns, '/macrotema/(?P<tag_id>\d+)', [
            [ 'methods' => 'DELETE', 'callback' => [ $this, 'delete_macrotema' ], 'permission_callback' => [ $this, 'permission' ] ],
        ] );

        // Utilitários
        register_rest_route( $ns, '/block-types', [
            [ 'methods' => 'GET', 'callback' => [ $this, 'get_block_types' ], 'permission_callback' => [ $this, 'permission' ] ],
        ] );
        register_rest_route( $ns, '/health', [
            [ 'methods' => 'GET', 'callback' => [ $this, 'health_check' ], 'permission_callback' => '__return_true' ],
        ] );
    }

    // ── Permissão ──────────────────────────────────────────────────────────────

    public function permission(): bool|WP_Error {
        if ( ! is_user_logged_in() ) {
            return new WP_Error( 'rest_forbidden', 'Autenticação necessária.', [ 'status' => 401 ] );
        }
        if ( ! current_user_can( 'edit_posts' ) ) {
            return new WP_Error( 'rest_forbidden', 'Permissão insuficiente.', [ 'status' => 403 ] );
        }
        return true;
    }

    // ── GET /layout/{page_id} ──────────────────────────────────────────────────

    public function get_layout( WP_REST_Request $request ): WP_REST_Response {
        $page_id = (int) $request->get_param( 'page_id' );
        $layout  = $this->engine->get_layout( $page_id );

        if ( ! $layout ) {
            return new WP_REST_Response( [ 'error' => 'Layout não encontrado.', 'page_id' => $page_id ], 404 );
        }
        return new WP_REST_Response( $layout, 200 );
    }

    // ── PUT /layout/{page_id} — substituição atômica ──────────────────────────

    public function put_layout( WP_REST_Request $request ): WP_REST_Response {
        $page_id = (int) $request->get_param( 'page_id' );
        $body    = $request->get_json_params();

        if ( empty( $body['blocks'] ) || ! is_array( $body['blocks'] ) ) {
            return new WP_REST_Response( [ 'error' => 'Campo blocks é obrigatório e deve ser array.' ], 400 );
        }

        $body['page_id']    = $page_id;
        $body['updated_at'] = current_time( 'c' );

        $ok = $this->engine->save_layout( $page_id, $body );
        $this->flush_page_cache( $page_id );

        return new WP_REST_Response( [
            'success'    => $ok,
            'page_id'    => $page_id,
            'blocks'     => count( $body['blocks'] ),
            'updated_at' => $body['updated_at'],
        ], $ok ? 200 : 500 );
    }

    // ── PATCH /layout/{page_id} — atualização parcial ─────────────────────────

    public function patch_layout( WP_REST_Request $request ): WP_REST_Response {
        $page_id = (int) $request->get_param( 'page_id' );
        $patch   = $request->get_json_params();
        $layout  = $this->engine->get_layout( $page_id );

        if ( ! $layout ) {
            return new WP_REST_Response( [ 'error' => 'Layout não encontrado.' ], 404 );
        }

        // Aplica campos de nível raiz (layout_mode, etc.)
        foreach ( [ 'layout_mode', 'cycle_id', 'curador_version' ] as $field ) {
            if ( isset( $patch[ $field ] ) ) {
                $layout[ $field ] = $patch[ $field ];
            }
        }

        // Aplica mudanças na lista de blocos
        if ( isset( $patch['blocks'] ) && is_array( $patch['blocks'] ) ) {
            $layout['blocks'] = $this->merge_blocks( $layout['blocks'], $patch['blocks'] );
        }

        $ok = $this->engine->save_layout( $page_id, $layout );
        $this->flush_page_cache( $page_id );

        return new WP_REST_Response( [ 'success' => $ok, 'page_id' => $page_id ], $ok ? 200 : 500 );
    }

    // ── POST /layout/{page_id}/blocks — adicionar bloco ───────────────────────

    public function add_block( WP_REST_Request $request ): WP_REST_Response {
        $page_id   = (int) $request->get_param( 'page_id' );
        $new_block = $request->get_json_params();
        $layout    = $this->engine->get_layout( $page_id );

        if ( ! $layout ) {
            return new WP_REST_Response( [ 'error' => 'Layout não encontrado.' ], 404 );
        }
        if ( empty( $new_block['type'] ) || ! $this->registry->type_exists( $new_block['type'] ) ) {
            return new WP_REST_Response( [ 'error' => 'Tipo de bloco inválido.' ], 400 );
        }

        $new_block['id'] = $new_block['id'] ?? 'blk_' . uniqid();
        $layout['blocks'][] = $new_block;

        $ok = $this->engine->save_layout( $page_id, $layout );
        $this->flush_page_cache( $page_id );

        return new WP_REST_Response( [ 'success' => $ok, 'block_id' => $new_block['id'] ], $ok ? 201 : 500 );
    }

    // ── DELETE /layout/{page_id}/blocks/{block_id} ────────────────────────────

    public function delete_block( WP_REST_Request $request ): WP_REST_Response {
        $page_id  = (int) $request->get_param( 'page_id' );
        $block_id = $request->get_param( 'block_id' );
        $layout   = $this->engine->get_layout( $page_id );

        if ( ! $layout ) {
            return new WP_REST_Response( [ 'error' => 'Layout não encontrado.' ], 404 );
        }

        $original_count = count( $layout['blocks'] );
        $layout['blocks'] = array_values( array_filter(
            $layout['blocks'],
            fn( $b ) => ( $b['id'] ?? '' ) !== $block_id
        ) );

        if ( count( $layout['blocks'] ) === $original_count ) {
            return new WP_REST_Response( [ 'error' => 'Bloco não encontrado.' ], 404 );
        }

        $ok = $this->engine->save_layout( $page_id, $layout );
        $this->flush_block_cache( $block_id );
        $this->flush_page_cache( $page_id );

        return new WP_REST_Response( [ 'success' => $ok, 'deleted' => $block_id ], $ok ? 200 : 500 );
    }

    // ── PATCH /layout/{page_id}/blocks/{block_id} ─────────────────────────────

    public function update_block( WP_REST_Request $request ): WP_REST_Response {
        $page_id  = (int) $request->get_param( 'page_id' );
        $block_id = $request->get_param( 'block_id' );
        $patch    = $request->get_json_params();
        $layout   = $this->engine->get_layout( $page_id );

        if ( ! $layout ) {
            return new WP_REST_Response( [ 'error' => 'Layout não encontrado.' ], 404 );
        }

        $found = false;
        foreach ( $layout['blocks'] as &$block ) {
            if ( ( $block['id'] ?? '' ) === $block_id ) {
                if ( isset( $patch['position'] ) ) $block['position'] = (int) $patch['position'];
                if ( isset( $patch['visible'] ) )  $block['visible']  = (bool) $patch['visible'];
                if ( isset( $patch['config'] ) )   $block['config']   = array_merge( $block['config'] ?? [], $patch['config'] );
                $found = true;
                break;
            }
        }
        unset( $block );

        if ( ! $found ) {
            return new WP_REST_Response( [ 'error' => 'Bloco não encontrado.' ], 404 );
        }

        $ok = $this->engine->save_layout( $page_id, $layout );
        $this->flush_block_cache( $block_id );
        $this->flush_page_cache( $page_id );

        return new WP_REST_Response( [ 'success' => $ok, 'block_id' => $block_id ], $ok ? 200 : 500 );
    }

    // ── POST /macrotema — cria subhome de macrotema ───────────────────────────

    public function create_macrotema( WP_REST_Request $request ): WP_REST_Response {
        $params = $request->get_json_params();

        $tag_id   = (int) ( $params['tag_id']  ?? 0 );
        $label    = sanitize_text_field( $params['label'] ?? '' );
        $slug     = sanitize_title( $params['slug']  ?? $label );
        $template = 'page-macrotema';

        if ( ! $tag_id || ! $label ) {
            return new WP_REST_Response( [ 'error' => 'tag_id e label são obrigatórios.' ], 400 );
        }

        // Verifica se já existe
        $existing = get_pages( [ 'meta_key' => '_brasileira_macrotema_tag_id', 'meta_value' => $tag_id ] );
        if ( ! empty( $existing ) ) {
            return new WP_REST_Response( [
                'message'  => 'Macrotema já existe.',
                'page_id'  => $existing[0]->ID,
                'page_url' => get_permalink( $existing[0]->ID ),
            ], 200 );
        }

        $page_id = wp_insert_post( [
            'post_title'   => $label,
            'post_name'    => $slug,
            'post_status'  => 'publish',
            'post_type'    => 'page',
            'page_template'=> "{$template}.html",
            'meta_input'   => [
                '_brasileira_macrotema_tag_id' => $tag_id,
                '_brasileira_macrotema_label'  => $label,
                '_brasileira_macrotema_active' => 1,
            ],
        ] );

        if ( is_wp_error( $page_id ) ) {
            return new WP_REST_Response( [ 'error' => $page_id->get_error_message() ], 500 );
        }

        // Cria layout inicial da subhome
        $initial_layout = $this->build_macrotema_layout( $page_id, $tag_id, $label );
        $this->engine->save_layout( $page_id, $initial_layout );

        return new WP_REST_Response( [
            'success'  => true,
            'page_id'  => $page_id,
            'page_url' => get_permalink( $page_id ),
            'tag_id'   => $tag_id,
        ], 201 );
    }

    // ── DELETE /macrotema/{tag_id} — arquiva subhome ──────────────────────────

    public function delete_macrotema( WP_REST_Request $request ): WP_REST_Response {
        $tag_id = (int) $request->get_param( 'tag_id' );
        $pages  = get_pages( [ 'meta_key' => '_brasileira_macrotema_tag_id', 'meta_value' => $tag_id ] );

        if ( empty( $pages ) ) {
            return new WP_REST_Response( [ 'error' => 'Macrotema não encontrado.' ], 404 );
        }

        $page = $pages[0];
        wp_update_post( [ 'ID' => $page->ID, 'post_status' => 'private' ] );
        update_post_meta( $page->ID, '_brasileira_macrotema_active', 0 );
        update_post_meta( $page->ID, '_brasileira_macrotema_archived_at', current_time( 'c' ) );

        return new WP_REST_Response( [
            'success'     => true,
            'page_id'     => $page->ID,
            'archived_at' => current_time( 'c' ),
        ], 200 );
    }

    // ── GET /block-types ──────────────────────────────────────────────────────

    public function get_block_types( WP_REST_Request $request ): WP_REST_Response {
        return new WP_REST_Response( $this->registry->all(), 200 );
    }

    // ── GET /health ───────────────────────────────────────────────────────────

    public function health_check( WP_REST_Request $request ): WP_REST_Response {
        global $wpdb;

        $homepage_id  = (int) get_option( 'page_on_front' );
        $layout       = $this->engine->get_layout( $homepage_id );
        $redis_ok     = function_exists( 'wp_cache_get' );
        $db_ok        = ! is_null( $wpdb->last_error ) && $wpdb->last_error === '';

        return new WP_REST_Response( [
            'status'           => 'ok',
            'timestamp'        => current_time( 'c' ),
            'homepage_id'      => $homepage_id,
            'layout_present'   => (bool) $layout,
            'layout_blocks'    => $layout ? count( $layout['blocks'] ) : 0,
            'layout_mode'      => $layout['layout_mode'] ?? null,
            'layout_updated'   => $layout['updated_at']  ?? null,
            'cache_available'  => $redis_ok,
            'db_ok'            => $db_ok,
            'block_types'      => count( $this->registry->all() ),
            'wp_version'       => get_bloginfo( 'version' ),
            'php_version'      => PHP_VERSION,
        ], 200 );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private function merge_blocks( array $existing, array $updates ): array {
        $existing_map = [];
        foreach ( $existing as $b ) {
            $existing_map[ $b['id'] ?? '' ] = $b;
        }
        foreach ( $updates as $u ) {
            $id = $u['id'] ?? '';
            if ( $id && isset( $existing_map[ $id ] ) ) {
                $existing_map[ $id ] = array_merge( $existing_map[ $id ], $u );
            } elseif ( $id ) {
                $existing_map[ $id ] = $u;
            }
        }
        return array_values( $existing_map );
    }

    private function build_macrotema_layout( int $page_id, int $tag_id, string $label ): array {
        return [
            'page_id'          => $page_id,
            'page_type'        => 'macrotema',
            'layout_mode'      => 'normal',
            'updated_at'       => current_time( 'c' ),
            'cycle_id'         => wp_generate_uuid4(),
            'curador_version'  => '4.0',
            'blocks' => [
                [ 'id' => 'blk_mt_001', 'type' => 'macrotema', 'position' => 0, 'visible' => true,
                  'config' => [ 'tag_id' => $tag_id, 'label' => $label, 'posts' => [], 'style' => 'section_full' ] ],
                [ 'id' => 'blk_mt_002', 'type' => 'ultimas',   'position' => 1, 'visible' => true,
                  'config' => [ 'count' => 20, 'style' => 'feed_list', 'tag_filter' => $tag_id ] ],
                [ 'id' => 'blk_mt_003', 'type' => 'mais_lidas','position' => 2, 'visible' => true,
                  'config' => [ 'period' => '7d', 'count' => 5, 'style' => 'sidebar_compact', 'tag_filter' => $tag_id ] ],
            ],
        ];
    }

    private function flush_page_cache( int $page_id ): void {
        if ( function_exists( 'rocket_clean_post' ) ) rocket_clean_post( $page_id );
        if ( function_exists( 'litespeed_purge_post' ) ) litespeed_purge_post( $page_id );
        wp_cache_delete( "brasileira_layout_{$page_id}", 'brasileira_layouts' );
    }

    private function flush_block_cache( string $block_id ): void {
        wp_cache_delete( "brasileira_blk_{$block_id}", 'brasileira_blocks' );
    }
}

// Bootstrap
add_action( 'rest_api_init', function () {
    $api = new Brasileira_REST_API();
    $api->register_routes();
} );
```

---

## 7. Subhomes — Mesmo Motor, Configurações Distintas

### 7.1 Tipos de Subhome

Toda subhome é uma WordPress Page com seu próprio layout JSON. O `BrasileiraLayoutEngine` opera identicamente para homepage e subhomes — a única diferença é o `page_id` e os tipos de bloco priorizados.

| Tipo | Como é criada | Template | Gestão |
|------|---------------|----------|--------|
| Editoria permanente | Manualmente na instalação | `page-subhome.html` | Curador V4 atualiza conteúdo |
| Macrotema temporário | Curador via `POST /macrotema` | `page-macrotema.html` | Curador cria/atualiza/arquiva |
| Regional | Manualmente por UF | `page-subhome.html` | Curador V4 filtra por UF |
| Especial | Manualmente pela equipe | `page-especial.html` | Equipe editorial |
| Colunista | Plugin de autores ou manualmente | `page-colunista.html` | Curador ou manual |

### 7.2 Layout Padrão de Subhome por Editoria

Ao criar ou resetar uma subhome de editoria, o curador V4 usa este template de layout:

```json
{
  "page_type": "subhome_editoria",
  "layout_mode": "normal",
  "blocks": [
    {
      "id": "blk_s001", "type": "manchete", "position": 0, "visible": true,
      "config": { "principal": null, "submanchetes": [], "style": "hero_split" }
    },
    {
      "id": "blk_s002", "type": "editoria", "position": 1, "visible": true,
      "config": { "category_id": null, "label": "", "posts": [], "style": "grid_6_mosaic" }
    },
    {
      "id": "blk_s003", "type": "ultimas", "position": 2, "visible": true,
      "config": { "count": 20, "style": "feed_list" }
    },
    {
      "id": "blk_s004", "type": "mais_lidas", "position": 3, "visible": true,
      "config": { "period": "7d", "count": 5, "style": "sidebar_compact" }
    },
    {
      "id": "blk_s_ad", "type": "publicidade", "position": 4, "visible": true,
      "config": { "slot": "subhome_leaderboard", "size": "728x90" }
    },
    {
      "id": "blk_s005", "type": "colunistas", "position": 5, "visible": true,
      "config": { "colunistas": [], "style": "carousel_horizontal" }
    }
  ]
}
```

### 7.3 Ciclo de Vida do Macrotema

```
DETECÇÃO
  └─ 5+ artigos com mesma tag em 2+ categorias distintas nas últimas 4h
  └─ Curador V4 identifica cluster → candidato a macrotema

PROMOÇÃO
  └─ POST /macrotema  → cria página WordPress
  └─ PATCH /layout/{homepage_id}/blocks  → adiciona bloco macrotema na homepage
  └─ Bloco posicionado no top 3 da homepage

ATIVO
  └─ Curador V4 atualiza posts do bloco a cada ciclo
  └─ Posição na homepage reflete intensidade do noticiário
  └─ Subhome recebe artigos automaticamente pela tag

DECADÊNCIA
  └─ Menos de 2 novos artigos nos últimos 60 min
  └─ Curador move bloco para posição mais baixa na homepage

ARQUIVAMENTO
  └─ Sem novos artigos em 6h
  └─ DELETE /macrotema/{tag_id}  → subhome fica como private (arquivo)
  └─ DELETE /layout/{homepage_id}/blocks/{block_id}  → remove da homepage
```

---

## 8. Agente Curador V4 — Arquitetura

### 8.1 Ciclo de Decisão

O Curador V4 opera em dois modos: **ciclo normal** (a cada 20 min durante 6h-24h) e **modo breaking** (a cada 5 min quando há urgência detectada).

```python
class CuradorV4:
    """Agente curador de nível TIER 1 — decide estrutura + conteúdo."""

    async def run_cycle(self):
        # 1. SCAN — coleta artigos recentes
        articles = await self.scan_recent(hours=3)
        
        # 2. SCORE — LLM premium avalia relevância, urgência, qualidade
        scored = await self.score_articles(articles)
        
        # 3. DETECT — identifica breaking news e macrotemas
        breaking = self.detect_breaking(scored)
        macrotopics = self.detect_macrotopics(scored)
        
        # 4. COMPOSE — monta layout completo
        new_layout = await self.compose_layout(
            scored=scored,
            breaking=breaking,
            macrotopics=macrotopics,
            time_preset=self.get_time_preset()
        )
        
        # 5. DIFF — compara com layout atual
        current = await self.api.get_layout(HOMEPAGE_ID)
        diff = self.diff_layouts(current, new_layout)
        
        # 6. APPLY — aplica apenas mudanças necessárias
        if diff['has_changes']:
            await self.apply_diff(HOMEPAGE_ID, diff)
        
        # 7. MACROTEMAS — cria/atualiza/arquiva
        await self.manage_macrotopics(macrotopics)
        
        # 8. SUBHOMES — atualiza as top editorias
        await self.update_subhomes(scored)
        
        # 9. LOG
        await self.log_cycle(diff, breaking, macrotopics)
```

### 8.2 Presets de Layout por Horário

```python
TIME_PRESETS = {
    "matinal": {          # 6h–10h
        "hours": range(6, 10),
        "max_blocks": 18,
        "priority_types": ["manchete", "ultimas", "ticker", "newsletter_cta"],
        "manchete_style": "hero_split",
        "ticker_visible": True,
        "breaking_threshold_score": 85,
    },
    "horario_nobre": {    # 10h–14h e 18h–22h
        "hours": list(range(10, 14)) + list(range(18, 22)),
        "max_blocks": 28,
        "priority_types": ["manchete", "breaking", "macrotema", "editoria"],
        "manchete_style": "hero_large",
        "ticker_visible": True,
        "breaking_threshold_score": 75,
    },
    "vespertino": {       # 14h–18h
        "hours": range(14, 18),
        "max_blocks": 22,
        "priority_types": ["opiniao", "especial", "editoria", "galeria"],
        "manchete_style": "hero_large",
        "ticker_visible": False,
        "breaking_threshold_score": 80,
    },
    "noturno": {          # 22h–6h
        "hours": list(range(22, 24)) + list(range(0, 6)),
        "max_blocks": 12,
        "priority_types": ["mais_lidas", "ultimas", "newsletter_cta"],
        "manchete_style": "hero_split",
        "ticker_visible": False,
        "breaking_threshold_score": 90,
    },
}
```

### 8.3 Prompt de Composição de Layout (LLM Premium)

```
Você é o editor-chefe de um portal de notícias TIER 1 brasileiro.
Hora atual: {hora}. Preset: {preset}.

ARTIGOS DISPONÍVEIS (score > 60):
{lista_de_artigos_com_scores}

MACROTEMAS ATIVOS:
{lista_de_macrotemas}

BREAKING DETECTADO: {breaking_info}

Sua tarefa: compose o layout JSON da homepage com exatamente as seguintes regras:

1. Se há breaking (score > {threshold}), crie bloco tipo "breaking" em position 0
2. Selecione a manchete principal (highest score, com imagem)
3. Adicione bloco macrotema para cada macrotema ativo (top 3 max)
4. Adicione blocos editoria para categorias com >= 3 artigos frescos:
   - Cada editoria de score alto: style "grid_5" ou "grid_6_mosaic"
   - Editoria de score médio: style "grid_3" ou "list_compact"
5. Insira 1 bloco publicidade a cada 3-4 blocos editoriais
6. Posicione colunistas após o 3º bloco editorial
7. Adicione mais_lidas, ultimas e newsletter_cta no final
8. Máximo de {max_blocks} blocos. Mínimo de 10.
9. Espaçe anúncios uniformemente (não mais que 1 a cada 3 blocos)

Retorne APENAS o JSON do layout, sem texto adicional.
```

### 8.4 Detecção de Macrotemas

```python
def detect_macrotopics(self, scored_articles: list) -> list:
    """
    Identifica clusters de artigos que formam macrotemas candidatos.
    Critério: 5+ artigos com mesma tag em 2+ categorias distintas.
    """
    tag_clusters = defaultdict(lambda: {"articles": [], "categories": set()})
    
    for article in scored_articles:
        for tag in article.get("tags", []):
            tag_clusters[tag["id"]]["articles"].append(article)
            tag_clusters[tag["id"]]["categories"].add(article["category_id"])
    
    candidates = []
    for tag_id, data in tag_clusters.items():
        if len(data["articles"]) >= 5 and len(data["categories"]) >= 2:
            avg_score = sum(a["score"] for a in data["articles"]) / len(data["articles"])
            candidates.append({
                "tag_id": tag_id,
                "tag_name": data["articles"][0]["tags"][0]["name"],
                "article_count": len(data["articles"]),
                "category_count": len(data["categories"]),
                "avg_score": avg_score,
                "top_posts": sorted(data["articles"], key=lambda x: x["score"], reverse=True)[:6],
            })
    
    return sorted(candidates, key=lambda x: x["avg_score"], reverse=True)
```

---

## 9. Performance: 20-30 Blocos sem Degradação

### 9.1 Estratégia de Cache em Camadas

```
Camada 1: Page cache (WP Rocket / LiteSpeed Cache)
  └─ TTL: 60s para homepage, 120s para subhomes
  └─ Invalidado pelo flush_page_cache() da REST API
  └─ Resultado: usuário anônimo serve HTML do disco, TTFB < 50ms

Camada 2: Object cache (Redis via Redis Object Cache plugin)
  └─ Fragment cache por bloco (cache_key = "blk_{id}_{type}")
  └─ TTL por tipo: breaking=60s, editoria=180s, mais_lidas=300s
  └─ Resultado: blocos não cacheados pelo page cache ainda evitam queries

Camada 3: Database query cache
  └─ WP_Query results cacheados via Transients API
  └─ Invalidados nos hooks save_post e transition_post_status

Camada 4: CDN (Cloudflare ou AWS CloudFront)
  └─ Imagens + assets estáticos (CSS/JS por bloco)
  └─ Cache-Control: max-age=31536000 (1 ano) para assets com hash
```

### 9.2 Lazy Loading de Blocos

```javascript
// assets/js/lazy-blocks.js
// Blocos abaixo da dobra são carregados via Intersection Observer

document.addEventListener('DOMContentLoaded', () => {
  const lazyBlocks = document.querySelectorAll('.brasileira-block[data-lazy]');
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const block = entry.target;
        const blockId = block.dataset.blockId;
        const blockType = block.dataset.blockType;
        
        fetch(`/wp-json/brasileira/v1/render-block/${blockId}`)
          .then(r => r.text())
          .then(html => {
            block.innerHTML = html;
            block.removeAttribute('data-lazy');
          });
        
        observer.unobserve(block);
      }
    });
  }, { rootMargin: '200px' });
  
  lazyBlocks.forEach(block => observer.observe(block));
});
```

### 9.3 SSE para Breaking News e Últimas

```javascript
// assets/js/live-updates.js
// Server-Sent Events para atualização em tempo real de breaking/ultimas

function initLiveUpdates() {
  const breakingBlock = document.querySelector('.brasileira-block--breaking');
  const ultimasBlock  = document.querySelector('.brasileira-block--ultimas');
  
  if (!breakingBlock && !ultimasBlock) return;
  
  const evtSource = new EventSource('/wp-json/brasileira/v1/live-stream');
  
  evtSource.addEventListener('breaking', (event) => {
    const data = JSON.parse(event.data);
    if (breakingBlock && data.html) {
      breakingBlock.outerHTML = data.html;
    } else if (data.action === 'remove' && breakingBlock) {
      breakingBlock.remove();
    }
  });
  
  evtSource.addEventListener('ultimas', (event) => {
    const data = JSON.parse(event.data);
    if (ultimasBlock && data.html) {
      ultimasBlock.innerHTML = data.html;
    }
  });
  
  evtSource.onerror = () => {
    // Fallback para polling em caso de erro no SSE
    evtSource.close();
    setInterval(() => {
      fetch('/wp-json/brasileira/v1/health')
        .then(r => r.json())
        .then(d => {
          if (d.layout_updated !== window._lastLayoutUpdate) {
            window.location.reload();
          }
        });
    }, 30000);
  };
}

document.addEventListener('DOMContentLoaded', initLiveUpdates);
```

### 9.4 Metas de Performance

| Métrica | Alvo | Estratégia |
|---------|------|-----------|
| TTFB | < 200ms | Page cache + Redis object cache |
| LCP | < 1.5s | `fetchpriority="high"` na manchete, imagem acima da dobra |
| CLS | ~0 | Reserva de espaço para ad slots (min-height) |
| INP | < 200ms | Nenhum JS bloqueante no critical path |
| Blocos renderizados | 20-30 sem degradação | Fragment cache + lazy load below-fold |
| Cache hit rate (Redis) | > 90% | TTLs calibrados por tipo de bloco |

---

## 10. Cronograma de Desenvolvimento por IA (5 Dias)

| Dia | Entregas |
|-----|---------|
| **Dia 1** | `theme.json` completo + `base.css` (grid, tipografia, cores Barlow/#3490B4) + `class-block-registry.php` + `class-layout-engine.php` + `class-cache-manager.php` |
| **Dia 2** | 18 `blocks/*/render.php` + 18 `blocks/*/style.css` (todos os tipos registrados) + `front-page.html` + `page-subhome.html` + `page-macrotema.html` |
| **Dia 3** | `class-rest-api.php` completo (todos os endpoints) + `functions.php` (bootstrap) + `wp_brasileira_layouts` table setup + `class-fallback-renderer.php` |
| **Dia 4** | Curador V4 completo (Python): scan → score → detect → compose → diff → apply → log + integração com Supabase para logging de ciclos |
| **Dia 5** | Testes de integração (todos os endpoints + 5 layouts diferentes) + migração do tagDiv + deploy staging + validação Core Web Vitals |

---

## 11. Tabela de Comparação: V2 (Zonas Fixas) vs V3 (Blocos Dinâmicos)

| Dimensão | V2 — Zonas Fixas | V3 — Blocos Dinâmicos (TIER 1) |
|----------|-----------------|-------------------------------|
| Blocos na homepage | 6 (fixos) | 8-28 (dinâmico) |
| Novos tipos de bloco | Requer alteração de código | Adiciona `render.php` + registra |
| Macrotema "Guerra no Irã" | Aparece em "Internacional" | Bloco próprio + subhome dedicada |
| Eleições 2026 | Sem espaço estrutural | Bloco `especial` permanente criado |
| Madrugada | Mesmas 6 zonas, algumas vazias | 10 blocos, proeminência para mais_lidas |
| Cache | Por página inteira | Por fragmento (bloco individual) |
| Breaking news | Banner fixo no topo | Bloco criado/destruído automaticamente |
| Subhomes | Templates separados | Mesmo motor, mesmo JSON, mesmo curador |
| REST API | POST /homepage (tudo ou nada) | CRUD granular por bloco |
| Curador role | Seleciona conteúdo | Decide estrutura + conteúdo |
| Layout changes/dia | 2-4 (ciclos do curador) | 20-40 (ciclos mais frequentes) |
| Time-of-day layouts | Não | Sim (4 presets) |
| Escalabilidade subhomes | Limitada (templates por editoria) | Ilimitada (mesmo sistema) |

---

## 12. Diferencial Competitivo

A arquitetura TIER 1 aqui descrita coloca brasileira.news à frente dos concorrentes em quatro dimensões específicas:

**Velocidade de resposta editorial**: enquanto Folha e G1 levam de 15 a 30 minutos para um editor humano criar uma seção de macrotema, o Curador V4 faz isso em menos de 1 minuto, incluindo criação da subhome, adição do bloco na homepage e preenchimento com os artigos mais relevantes.

**Granularidade de cache**: todos os portais TIER 1 brasileiros usam cache de página inteira. O modelo de fragment cache por bloco significa que um breaking news pode ser atualizado a cada 60 segundos sem invalidar os outros 27 blocos da homepage — mantendo TTFB baixo mesmo com atualizações frequentes.

**Estrutura como dado**: o JSON de layout é legível por máquina, versionável, auditável e reversível. Um rollback para o layout de 30 minutos atrás é uma única operação de banco de dados. Nenhum portal brasileiro tem isso hoje.

**Extensibilidade zero-deploy**: adicionar um novo tipo de bloco (por exemplo, `cotacoes_crypto` ou `placares_futebol`) requer apenas um `render.php`, um `style.css` e um `register()` no Block Registry. A REST API, o Layout Engine e o Curador V4 passam a suportá-lo automaticamente — sem alterar nenhuma outra linha de código.

---

*brasileira.news — Arquitetura TIER 1 v3.0 — Abril 2026*
