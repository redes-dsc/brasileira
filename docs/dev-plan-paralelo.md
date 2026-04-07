# Planejamento de Desenvolvimento Paralelo — brasileira-theme TIER 1

**brasileira.news — Sprint de Implementação**
**Versão 1.0 — Abril 2026**

---

## Visão Geral

O plano técnico TIER 1 define 2.249 linhas de especificação com 18 tipos de bloco, layout engine, REST API (10 endpoints), tema FSE completo e Curador V4. O desenvolvimento será distribuído entre **4 ferramentas de codificação por IA operando em paralelo**, cada uma com seu domínio de responsabilidade, sem dependências bloqueantes.

### Ferramentas

| Ferramenta | Perfil | Melhor Para |
|------------|--------|-------------|
| **Qoder** | Agente autônomo, opera direto no servidor/repo | Refatoração de agentes Python, integração com sistemas existentes (V3, Supabase, Redis) |
| **Cursor** | IDE com IA, contexto profundo de projeto | Desenvolvimento de tema PHP completo, templates, CSS/JS com contexto cross-file |
| **VS Code (Copilot)** | IDE com autocomplete e chat | Blocos individuais (render.php), testes unitários, documentação inline |
| **Antigravity** | Agente autônomo, projeto inteiro | Curador V4 Python (módulo novo completo), sistema de macrotemas |

---

## Arquitetura de Streams

O projeto é dividido em **6 streams independentes** + 1 stream de integração. Cada stream tem contrato de interface definido upfront — isso é o que permite paralelismo total.

```
Stream A ─── Tema Foundation ──────────── Cursor
Stream B ─── Layout Engine + Registry ─── Cursor
Stream C ─── Block Templates (18x) ────── VS Code (Copilot)
Stream D ─── REST API Plugin ──────────── Qoder (direto no servidor)
Stream E ─── Curador V4 Agent ─────────── Antigravity
Stream F ─── Migração tagDiv ──────────── Qoder (direto no servidor)
             ┌──────────────────────────┐
Stream G ─── │  Integração & Deploy     │── Qoder + manual
             └──────────────────────────┘
```

---

## Contratos de Interface (definidos ANTES de tudo)

Estes contratos devem ser criados primeiro — são o que permite que todas as streams trabalhem em paralelo sem bloqueio.

### Contrato 1: Layout JSON Schema

```json
{
  "$schema": "brasileira-layout-v1",
  "page_id": "integer",
  "page_type": "enum: homepage | subhome | macrotema | especial",
  "layout_mode": "enum: matinal | horario_nobre | vespertino | noturno | breaking",
  "updated_at": "ISO 8601",
  "cycle_id": "UUID",
  "curador_version": "string",
  "blocks": [
    {
      "id": "string (blk_XXX)",
      "type": "string (registered block type)",
      "position": "integer (0-based, ordenação)",
      "visible": "boolean",
      "config": "object (schema varies by type)"
    }
  ]
}
```

### Contrato 2: REST API Endpoints

```
BASE: /wp-json/brasileira/v1

GET    /layout/{page_id}                    → PageLayout JSON
PUT    /layout/{page_id}                    → Replace layout (atomic)
PATCH  /layout/{page_id}                    → Partial update
POST   /layout/{page_id}/blocks             → Add block → { block }
PATCH  /layout/{page_id}/blocks/{block_id}  → Update block → { block }
DELETE /layout/{page_id}/blocks/{block_id}  → Remove block
POST   /macrotema                           → Create macrotopic page → { page_id, tag_id }
DELETE /macrotema/{tag_id}                  → Archive macrotopic
GET    /block-types                          → Registry of types + schemas
GET    /health                               → System status

Auth: Application Passwords (header Authorization: Basic)
Content-Type: application/json
```

### Contrato 3: Block Type Schema

```php
// Cada tipo de bloco implementa:
// 1. blocks/{type}/render.php — recebe $block (array com id, type, config)
// 2. blocks/{type}/style.css — estilos encapsulados com .blk-{type}
// 3. Registro em class-block-registry.php com config schema
```

### Contrato 4: Curador V4 ↔ WordPress

```python
# O curador V4 consome a REST API:
# 1. GET /layout/{page_id} → estado atual
# 2. Compõe novo layout (array de blocks)
# 3. PUT /layout/{page_id} → aplica atomicamente
# 4. POST /macrotema → cria subhome de macrotema quando necessário
# 5. DELETE /macrotema/{tag_id} → arquiva macrotema decadente
```

---

## Stream A — Tema Foundation

**Ferramenta:** Cursor
**Responsável:** Infraestrutura do tema WordPress

### Entregas

| # | Arquivo | Descrição |
|---|---------|-----------|
| A1 | `theme.json` | Design tokens completos: Barlow (4 pesos + Condensed), paleta #3490B4, escala de espaçamento, layout contentSize/wideSize, shadow presets, block settings |
| A2 | `style.css` | Header do tema (metadata WordPress) |
| A3 | `functions.php` | Setup: theme supports, menus, widget areas, enqueue de scripts, hooks de performance |
| A4 | `assets/css/base.css` | Grid system (CSS Grid + Flexbox), tipografia Barlow, cores, utilitários |
| A5 | `assets/css/editor.css` | Estilos para o editor Gutenberg |
| A6 | `templates/front-page.html` | Template da homepage (chama Layout Engine via PHP) |
| A7 | `templates/single.html` | Template de artigo |
| A8 | `templates/page-subhome.html` | Template de subhome |
| A9 | `templates/page-macrotema.html` | Template de macrotema |
| A10 | `templates/archive.html` | Template de arquivo/categoria (fallback) |
| A11 | `templates/search.html` | Template de busca |
| A12 | `templates/404.html` | Template 404 |
| A13 | `parts/header.html` | Header com nav, topbar (clima/hora), menu hamburger |
| A14 | `parts/footer.html` | Footer institucional |
| A15 | `parts/topbar.html` | Barra superior (clima Brasília, data/hora, redes) |

### Instruções para Cursor

```
Contexto: Tema WordPress Block Theme (FSE) para portal de notícias brasileiro
TIER 1, brasileiro de alto tráfego (1.500-2.400 artigos/dia).

Identidade visual:
- Fonte: Barlow (Regular 400, Medium 500, SemiBold 600, Bold 700) + Barlow Condensed (SemiBold 600)
- Cor principal: #3490B4 (azul-petróleo/teal)
- Texto títulos: #444444
- Texto corpo: #717176
- Bordas: #EDEDED
- Fundos: #FFFFFF, #F1F4F7, #FCF7F5
- Breaking accent: #D32F2F (vermelho)
- Tag/label accent: #F5A623 (amarelo/dourado)

O template front-page.html deve chamar uma função PHP que usa o Layout Engine
para renderizar blocos dinâmicos (não blocos Gutenberg fixos).

Incluir: <?php get_template_part('inc/layout-engine'); ?> via PHP block.

Não usar tagDiv, ACF PRO, ou qualquer dependência externa.
Registrar fontes Barlow via Google Fonts no functions.php.
```

### Critérios de Aceite
- [ ] `theme.json` válido (testar com `wp theme activate brasileira-theme`)
- [ ] Homepage renderiza sem erros PHP
- [ ] Barlow carrega corretamente
- [ ] Paleta de cores aplicada no editor e no frontend
- [ ] Menu de navegação funcional
- [ ] Topbar com data/hora e clima

### Tempo estimado: 3-4 horas

---

## Stream B — Layout Engine + Block Registry

**Ferramenta:** Cursor (mesmo projeto que Stream A)
**Responsável:** Motor de renderização dinâmica

### Entregas

| # | Arquivo | Descrição |
|---|---------|-----------|
| B1 | `inc/class-layout-engine.php` | Motor principal: lê JSON → renderiza blocos sequencialmente, fragment cache, fallback, lazy loading |
| B2 | `inc/class-block-registry.php` | Registro de 18 tipos de bloco com schemas, TTLs, variantes |
| B3 | `inc/class-cache-manager.php` | Fragment cache por bloco (Redis/Object Cache), invalidação seletiva |
| B4 | `inc/class-ad-manager.php` | Gestão de slots publicitários, posicionamento automático |

### Instruções para Cursor

```
Criar o Layout Engine conforme especificação em plano-tecnico-tier1.pplx.md,
seções 4 e 5.

Layout JSON é lido de wp_options (key: brasileira_layout_{page_id}).
Alternativa: tabela customizada wp_brasileira_layouts.

O engine:
1. Lê layout JSON para o page_id atual
2. Ordena blocos por position
3. Filtra blocos invisíveis e expirados
4. Para cada bloco visível:
   a. Verifica fragment cache (wp_cache_get)
   b. Se cache miss: inclui blocks/{type}/render.php passando $block
   c. Armazena no cache com TTL do tipo
5. Enqueue CSS apenas dos tipos presentes na página
6. Se layout ausente: renderiza fallback (últimos 30 posts por categoria)

Block Registry: array estático com todos os 18 tipos, seus schemas e TTLs.
Usar filter 'brasileira_block_types' para extensibilidade.
```

### Critérios de Aceite
- [ ] Layout Engine renderiza JSON de exemplo sem erros
- [ ] Cache funciona (segundo request mais rápido)
- [ ] Fallback funciona com layout ausente
- [ ] CSS enqueued apenas para tipos presentes
- [ ] Bloco expirado não é renderizado

### Tempo estimado: 3-4 horas (paralelo com A)

---

## Stream C — Block Templates (18 tipos)

**Ferramenta:** VS Code com Copilot
**Responsável:** Templates de renderização de cada tipo de bloco

### Entregas

18 pares de arquivos (render.php + style.css) organizados em `blocks/`:

| # | Tipo | Prioridade | Variantes |
|---|------|-----------|-----------|
| C1 | `breaking` | P0 | fullwidth_red, fullwidth_orange, ticker_bar |
| C2 | `manchete` | P0 | hero_large, hero_split, hero_video |
| C3 | `editoria` | P0 | grid_3, grid_4_sidebar, grid_5, grid_6_mosaic, list_compact |
| C4 | `macrotema` | P0 | highlight_band, section_full, sidebar_box |
| C5 | `colunistas` | P1 | carousel_horizontal, grid_4 |
| C6 | `ultimas` | P1 | feed_list, feed_cards |
| C7 | `mais_lidas` | P1 | numbered_list, sidebar_compact |
| C8 | `opiniao` | P1 | cards_editorial, list_quotes |
| C9 | `publicidade` | P1 | leaderboard, rectangle, fullwidth |
| C10 | `ticker` | P2 | bar_dark, bar_light, bar_minimal |
| C11 | `video` | P2 | player_featured, grid_thumbs |
| C12 | `podcast` | P2 | featured_episode, playlist |
| C13 | `regional` | P2 | tabs_regional, grid_ufs |
| C14 | `newsletter_cta` | P2 | inline_banner, popup_exit, sidebar_box |
| C15 | `especial` | P2 | hero_editorial, card_featured |
| C16 | `galeria` | P3 | carousel_fullwidth, grid_masonry |
| C17 | `trending` | P3 | tags_cloud, list_horizontal |
| C18 | `custom` | P3 | freeform_html |

### Instruções para VS Code / Copilot

```
Para cada tipo de bloco, criar:

1. blocks/{type}/render.php
   - Recebe variável $block (array com id, type, position, visible, config)
   - $config = $block['config'] tem os dados específicos do tipo
   - Renderiza HTML semântico com classes BEM: .blk-{type}, .blk-{type}__title, etc.
   - Suporta múltiplas variantes via $config['style']
   - Busca dados de posts via get_post() quando config tem post_id/posts[]
   - Fallback se post não existe: pular item sem quebrar bloco
   - Imagens via wp_get_attachment_image_src com lazy loading nativo
   - Links com get_permalink()

2. blocks/{type}/style.css
   - Escopar com .blk-{type} { }
   - Mobile-first responsive
   - Usar variáveis CSS do theme.json (--wp--preset--color--primary, etc.)
   - Fonte: Barlow (herdada do base.css)
   - Cores: #3490B4 (links/accent), #444444 (títulos), #717176 (texto)
   - Breaking: #D32F2F background
   - Grid: CSS Grid para layouts de cards

Padrão de render.php:
<?php
if (empty($block) || empty($block['config'])) return;
$config = $block['config'];
$style = $config['style'] ?? 'default_variant';
?>
<section class="blk-{type} blk-{type}--<?php echo esc_attr($style); ?>"
         id="<?php echo esc_attr($block['id']); ?>"
         data-type="{type}">
    <!-- conteúdo -->
</section>
```

### Ordem de execução
1. **Batch P0** (4 blocos críticos): breaking, manchete, editoria, macrotema — SEM ELES NÃO HÁ HOMEPAGE
2. **Batch P1** (5 blocos essenciais): colunistas, ultimas, mais_lidas, opiniao, publicidade
3. **Batch P2** (5 blocos complementares): ticker, video, podcast, regional, newsletter_cta
4. **Batch P3** (4 blocos opcionais): especial, galeria, trending, custom

### Critérios de Aceite por bloco
- [ ] render.php renderiza HTML válido com dados de exemplo
- [ ] Todas as variantes de estilo funcionam
- [ ] Fallback não quebra com dados ausentes
- [ ] Responsivo (mobile/tablet/desktop)
- [ ] CSS encapsulado (não vaza para outros blocos)

### Tempo estimado: 4-6 horas (P0+P1 em 3h, P2+P3 em 2h)

---

## Stream D — REST API Plugin

**Ferramenta:** Qoder (direto no servidor Lightsail)
**Responsável:** Plugin WordPress com endpoints para controle por agentes

### Entregas

| # | Arquivo | Descrição |
|---|---------|-----------|
| D1 | `brasileira-api/brasileira-api.php` | Main plugin file, autoload |
| D2 | `brasileira-api/includes/class-layout-controller.php` | Endpoints GET/PUT/PATCH layout |
| D3 | `brasileira-api/includes/class-blocks-controller.php` | Endpoints POST/PATCH/DELETE blocks |
| D4 | `brasileira-api/includes/class-macrotema-controller.php` | Endpoints POST/DELETE macrotema |
| D5 | `brasileira-api/includes/class-health-controller.php` | GET health + GET block-types |
| D6 | `brasileira-api/includes/class-layout-storage.php` | Abstração de storage (wp_options ou tabela customizada) |

### Instruções para Qoder

```
Criar plugin WordPress 'brasileira-api' em wp-content/plugins/.

10 endpoints REST conforme contrato definido.

Storage: usar wp_options com key 'brasileira_layout_{page_id}'.
O valor é JSON (json_encode/json_decode).

Segurança:
- Todos os endpoints requerem 'edit_posts' capability
- Sanitizar todo input: absint() para IDs, sanitize_text_field() para strings
- Validar block type contra registro
- Rate limit: max 60 requests/minuto por IP

Cache flush:
- Após qualquer PUT/PATCH/DELETE, chamar:
  wp_cache_delete("brasileira_layout_{page_id}", 'brasileira_layouts');
  // + flush fragment caches dos blocos afetados

Macrotema endpoints:
- POST /macrotema: cria nova page WordPress (wp_insert_post) com template
  page-macrotema.html, salva layout inicial, retorna page_id
- DELETE /macrotema/{tag_id}: muda status da page para 'draft', limpa layout

Testar direto no servidor:
curl -u usuario:app_password -X GET https://brasileira.news/wp-json/brasileira/v1/layout/18135

O plugin deve funcionar independente do tema — ativar mesmo com Newspaper ainda ativo.
```

### Critérios de Aceite
- [ ] Todos os 10 endpoints respondem corretamente
- [ ] PUT layout é atômico (ou aplica tudo ou nada)
- [ ] PATCH blocks/{id} altera apenas o bloco especificado
- [ ] POST macrotema cria page + layout
- [ ] Auth funciona com Application Passwords
- [ ] Erro 400 para payload inválido, 404 para bloco inexistente

### Tempo estimado: 3-4 horas

---

## Stream E — Curador V4 Agent

**Ferramenta:** Antigravity
**Responsável:** Agente Python que opera como editor-chefe algorítmico

### Entregas

| # | Arquivo | Descrição |
|---|---------|-----------|
| E1 | `curador_v4/curador.py` | Orquestrador principal (scan → score → detect → compose → diff → apply → log) |
| E2 | `curador_v4/scanner.py` | Coleta artigos recentes via WP REST API |
| E3 | `curador_v4/scorer.py` | Scoring editorial LLM PREMIUM (reutilizar scorer.py V3 com ajustes) |
| E4 | `curador_v4/macrotema_detector.py` | Detecção de clusters cross-category por tag |
| E5 | `curador_v4/compositor.py` | Composição de layout (decide blocos, ordem, variantes) |
| E6 | `curador_v4/differ.py` | Calcula diff entre layout atual e proposto |
| E7 | `curador_v4/applicator.py` | Aplica layout via REST API (PUT/PATCH) |
| E8 | `curador_v4/presets.py` | 4 presets de layout por período (matinal, nobre, vespertino, noturno) |
| E9 | `curador_v4/config.py` | Configuração (URLs, auth, thresholds, categorias) |
| E10 | `curador_v4/logger.py` | Logging para PostgreSQL/Supabase |

### Instruções para Antigravity

```
Criar módulo Python curador_v4/ no repositório brasileira (GitHub).

REUTILIZAR do V3 (copiar e adaptar, não reescrever):
- V3/curador_homepage/scorer.py → base do scorer.py
- V3/shared/wp_client.py → base do scanner.py e applicator.py
- V3/curador_homepage/compositor.py → referência para compositor.py

NOVO (não existe no V3):
- macrotema_detector.py: analisa posts das últimas 4h, agrupa por tags,
  identifica clusters (5+ posts com mesma tag em 2+ categorias) →
  retorna lista de macrotemas candidatos com posts e categorias
  
- compositor.py V4: recebe artigos scorados + macrotemas detectados +
  preset do período → produz layout JSON completo
  
  Decisões do compositor (via LLM PREMIUM):
  1. Deve haver bloco breaking? (post com urgencia > 0.85)
  2. Qual artigo é manchete? (maior score geral)
  3. Quais editorias têm conteúdo suficiente? (min 3 posts frescos)
  4. Quais macrotemas estão ativos? (adicionar/manter/remover blocos)
  5. Onde inserir publicidade? (a cada 3-4 blocos editoriais)
  6. Quantos blocos total? (baseado no preset + intensidade do ciclo)
  
- differ.py: compara layout atual (GET /layout) com proposto,
  decide se usa PUT (>50% mudanças) ou PATCH (mudanças pontuais)
  
- presets.py:
  matinal (6-10h): 12-18 blocos, manchete menor, newsletter proeminente
  horario_nobre (10-14h, 18-22h): 22-28 blocos, manchete grande, todas editorias
  vespertino (14-18h): 15-20 blocos, opinião proeminente, especiais
  noturno (22-6h): 8-12 blocos, mais_lidas proeminente, resumo do dia

Ciclo de execução: crontab ou supervisor
- Horário nobre: a cada 15 min
- Normal: a cada 30 min
- Madrugada: a cada 60 min

Integração existente:
- LiteLLM via call_llm(tier=TIER_PREMIUM)
- Redis para locks e working memory
- Supabase/PostgreSQL para logging
- WP REST API via wp_client.py (async, com retry)
```

### Critérios de Aceite
- [ ] Ciclo completo executa em < 60 segundos
- [ ] Layout gerado respeita preset do período
- [ ] Macrotema detectado aparece como bloco + opcionalmente subhome
- [ ] Diff minimiza chamadas à API (PATCH quando possível)
- [ ] Sem race conditions (lock Redis)
- [ ] Logs completos no Supabase

### Tempo estimado: 6-8 horas

---

## Stream F — Migração tagDiv

**Ferramenta:** Qoder (direto no servidor)
**Responsável:** Remoção do tagDiv e transição

### Entregas

| # | Tarefa | Descrição |
|---|--------|-----------|
| F1 | Auditoria de shortcodes | Query SQL para detectar posts com shortcodes tagDiv no content |
| F2 | Script de conversão | Python/PHP para converter shortcodes tagDiv → HTML limpo (se necessário) |
| F3 | Backup | Backup completo MariaDB + files antes da troca |
| F4 | Troca de tema | `wp theme activate brasileira-theme` via WP-CLI |
| F5 | Limpeza | Remover plugins tagDiv (td-composer, td-cloud-library, etc.) |
| F6 | Verificação | Testar homepage, artigos, categorias, busca |

### Instruções para Qoder

```
PASSO ZERO (executar primeiro de tudo):
SELECT COUNT(*) as total,
  SUM(CASE WHEN post_content LIKE '%[vc_%' OR post_content LIKE '%[td_%' 
      OR post_content LIKE '%[tdc_%' THEN 1 ELSE 0 END) as com_shortcodes
FROM wp_7_posts 
WHERE post_status = 'publish' AND post_type = 'post';

Se com_shortcodes > 0: criar script de conversão
Se com_shortcodes = 0: migração é direta (provável — posts são criados via REST API)

Sequência:
1. Backup: mysqldump + tar dos uploads
2. Instalar brasileira-theme em wp-content/themes/
3. Ativar plugin brasileira-api
4. Inserir layout JSON inicial para page_id homepage (via REST API)
5. Trocar tema: wp theme activate brasileira-theme
6. Testar: curl homepage, artigos recentes, categorias
7. Se OK: desativar plugins tagDiv
8. Monitorar 1h
9. Se estável: remover arquivos tagDiv
```

### Dependências
- Depende de: Stream A (tema), Stream D (plugin API), Stream B (layout engine)
- NÃO depende de: Stream C (block templates — fallback funciona sem eles), Stream E (curador — layout manual inicial)

### Tempo estimado: 2-3 horas (após streams A, B, D)

---

## Stream G — Integração & Deploy

**Ferramenta:** Qoder + validação manual
**Responsável:** Juntar todas as peças

### Sequência

1. **Merge code** — Tema (A+B+C) no repo GitHub → push para servidor Lightsail
2. **Ativar plugin** — Stream D já está no servidor (Qoder instalou direto)
3. **Inserir layout de teste** — JSON com 10-15 blocos via REST API
4. **Ativar tema** — Stream F executa migração
5. **Deploy Curador V4** — Stream E no EC2, rodar primeiro ciclo em dry-run
6. **Validação visual** — Screenshot + verificação manual de cada tipo de bloco
7. **Primeiro ciclo real** — Curador V4 gera layout real → aplica → verificar
8. **Monitorar** — 24h de observação com ajustes

### Tempo estimado: 2-3 horas

---

## Cronograma Consolidado

### Dia 1 — Fundação + Código (todas as streams em paralelo)

```
Hora  | Cursor (A+B)           | VS Code (C)           | Qoder (D)          | Antigravity (E)
──────┼────────────────────────┼───────────────────────┼────────────────────┼──────────────────────
 0-1  | theme.json + style.css | Batch P0: breaking    | Plugin skeleton    | Config + scanner
      | functions.php          | manchete              | Layout storage     | Scorer (adapt V3)
 1-2  | base.css + templates   | editoria              | Layout controller  | Macrotema detector
      | header + footer parts  | macrotema             | Blocks controller  |
 2-3  | Layout Engine          |                       | Macrotema ctrl     | Compositor V4
      | Block Registry         | Batch P1: colunistas  | Health endpoint    | Presets
 3-4  | Cache Manager          | ultimas, mais_lidas   | Testes via curl    | Differ + Applicator
      | Ad Manager             | opiniao, publicidade  |                    | Logger
 4-5  | Ajustes/testes         | Batch P2: ticker      |                    | Integração
      |                        | video, podcast        |                    | Testes dry-run
 5-6  |                        | regional, newsletter  |                    |
      |                        | Batch P3: especial    |                    |
      |                        | galeria, trending     |                    |
```

**Resultado Dia 1:** Todo o código produzido. Nenhuma integração ainda.

### Dia 2 — Integração + Migração + Deploy

```
Hora  | Atividade                                    | Ferramenta
──────┼──────────────────────────────────────────────┼────────────
 0-1  | Merge de todo código no repo                 | Git
 1-2  | Push tema para servidor + ativar plugin      | Qoder
 2-3  | Migração tagDiv (Stream F)                   | Qoder
 3-4  | Deploy Curador V4 no EC2                     | Qoder
 4-5  | Primeiro ciclo dry-run + ajustes             | Manual + Qoder
 5-6  | Primeiro ciclo real + monitoramento           | Curador V4 autônomo
```

**Resultado Dia 2:** Portal rodando com tema novo e curadoria TIER 1 ativa.

### Dia 3 — Estabilização (opcional)

- Ajustes visuais nos block templates
- Tuning de thresholds do curador (macrotemas, scoring)
- Criação de subhomes para editorias principais
- Performance profiling e otimização de cache
- A/B testing de variantes de layout

---

## Mapa de Dependências

```
                    ┌─────────────────┐
                    │  CONTRATOS DE   │
                    │   INTERFACE     │
                    │ (definir antes) │
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
     ┌─────┴─────┐    ┌─────┴─────┐    ┌─────┴─────┐
     │ Stream A  │    │ Stream D  │    │ Stream E  │
     │ Theme     │    │ REST API  │    │ Curador   │
     │ (Cursor)  │    │ (Qoder)   │    │ (Anti-    │
     └─────┬─────┘    └─────┬─────┘    │  gravity) │
           │                │           └─────┬─────┘
     ┌─────┴─────┐         │                 │
     │ Stream B  │         │                 │
     │ Engine    │         │                 │
     │ (Cursor)  │         │                 │
     └─────┬─────┘         │                 │
           │                │                 │
     ┌─────┴─────┐         │                 │
     │ Stream C  │         │                 │
     │ Blocks    │         │                 │
     │ (VS Code) │         │                 │
     └─────┬─────┘         │                 │
           │                │                 │
           └────────┬───────┘                 │
                    │                         │
              ┌─────┴─────┐                   │
              │ Stream F  │                   │
              │ Migração  │                   │
              │ (Qoder)   │                   │
              └─────┬─────┘                   │
                    │                         │
                    └────────┬────────────────┘
                             │
                    ┌────────┴────────┐
                    │   Stream G      │
                    │   Integração    │
                    └─────────────────┘
```

**Paralelismo máximo:** Streams A, B, C, D e E rodam simultaneamente no Dia 1.
**Único gargalo:** Stream F (migração) depende de A+B+D estarem prontos.
**Stream E é independente:** Curador V4 só precisa do contrato da API, não do código PHP.

---

## Checklist de Validação Final

### Funcional
- [ ] Homepage renderiza 20+ blocos sem erro
- [ ] Bloco breaking aparece/desaparece por auto_expire
- [ ] Macrotema criado via API gera bloco na home + página subhome
- [ ] Subhomes de editorias funcionam com layouts próprios
- [ ] REST API responde corretamente para todos os 10 endpoints
- [ ] Curador V4 executa ciclo completo em < 60s
- [ ] Presets de horário mudam a composição da página

### Performance
- [ ] TTFB < 200ms (com object cache ativo)
- [ ] LCP < 1.5s
- [ ] CLS ~ 0 (sem layout shifts)
- [ ] Fragment cache por bloco funcionando
- [ ] CSS carregado apenas para tipos presentes

### Visual
- [ ] Barlow renderiza corretamente em todos os pesos
- [ ] Paleta #3490B4 aplicada consistentemente
- [ ] Responsivo: mobile, tablet, desktop
- [ ] Breaking news em vermelho com contraste adequado
- [ ] Cards de artigos com imagem, título, excerpt, metadata

### Segurança
- [ ] REST API protegida por Application Passwords
- [ ] Input sanitizado em todos os endpoints
- [ ] Sem SQL injection via layout JSON
- [ ] Rate limiting ativo

### Migração
- [ ] Todos os artigos existentes renderizam sem shortcodes quebrados
- [ ] URLs não mudaram (sem impacto SEO)
- [ ] Menu de navegação funcional
- [ ] Busca funciona
- [ ] AMP funciona (se aplicável)

---

## Resumo Executivo

| Métrica | Valor |
|---------|-------|
| **Streams paralelas** | 6 (A, B, C, D, E, F) |
| **Ferramentas** | 4 (Cursor, VS Code, Qoder, Antigravity) |
| **Arquivos produzidos** | ~60 |
| **Linhas de código estimadas** | ~5.000-7.000 |
| **Dias de desenvolvimento** | 2 (1 codificação + 1 integração) |
| **Dia 3 (opcional)** | Estabilização e tuning |
| **Bloqueios entre streams** | 1 (Stream F depende de A+B+D) |
| **Risco principal** | Shortcodes tagDiv no conteúdo dos posts |
