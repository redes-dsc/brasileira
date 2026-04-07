# Contratos de Interface — brasileira.news TIER 1

**Estes contratos devem ser lidos por TODAS as ferramentas antes de iniciar o desenvolvimento.**
**São a base que permite o paralelismo — cada stream trabalha contra estes contratos.**

---

## Contrato 1: Layout JSON Schema

O layout de cada página é um JSON armazenado em `wp_options` (key: `brasileira_layout_{page_id}`).

```json
{
  "page_id": 18135,
  "page_type": "homepage | subhome | macrotema | especial",
  "layout_mode": "matinal | horario_nobre | vespertino | noturno | breaking",
  "updated_at": "2026-04-06T18:00:00-03:00",
  "cycle_id": "a3f7c2d1-9b4e-4a8f-b6c3-d2e1f0a9b8c7",
  "curador_version": "4.0",
  "blocks": [
    {
      "id": "blk_001",
      "type": "string (tipo registrado)",
      "position": 0,
      "visible": true,
      "config": {}
    }
  ]
}
```

### Regras
- `page_id`: inteiro positivo (ID da page WordPress)
- `blocks`: array ordenado por `position` (0-based)
- `id`: string única por layout (formato: `blk_XXX` ou `blk_ad_X`)
- `type`: deve estar registrado no Block Registry
- `position`: inteiro >= 0, sem gaps (0, 1, 2, 3...)
- `visible`: booleano, blocos invisíveis são ignorados na renderização
- `config`: objeto com schema específico por tipo (ver Block Registry)

---

## Contrato 2: REST API Endpoints

**Base URL:** `https://brasileira.news/wp-json/brasileira/v1`
**Auth:** Application Passwords (header `Authorization: Basic base64(user:password)`)
**Content-Type:** `application/json`

### Endpoints

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `GET` | `/layout/{page_id}` | Retorna layout JSON completo | Sim |
| `PUT` | `/layout/{page_id}` | Substitui layout inteiro (atômico) | Sim |
| `PATCH` | `/layout/{page_id}` | Atualização parcial (merge) | Sim |
| `POST` | `/layout/{page_id}/blocks` | Adiciona bloco | Sim |
| `PATCH` | `/layout/{page_id}/blocks/{block_id}` | Atualiza bloco específico | Sim |
| `DELETE` | `/layout/{page_id}/blocks/{block_id}` | Remove bloco | Sim |
| `POST` | `/macrotema` | Cria página de macrotema | Sim |
| `DELETE` | `/macrotema/{tag_id}` | Arquiva macrotema | Sim |
| `GET` | `/block-types` | Lista tipos de blocos registrados | Não |
| `GET` | `/health` | Status do sistema | Não |

### Respostas

**GET /layout/{page_id}**
```json
{
  "page_id": 18135,
  "page_type": "homepage",
  "layout_mode": "horario_nobre",
  "updated_at": "2026-04-06T18:00:00-03:00",
  "cycle_id": "uuid",
  "blocks": [...]
}
```

**PUT /layout/{page_id}** — Body: layout JSON completo
```json
{ "success": true, "blocks_count": 15, "changed_at": "2026-04-06T18:00:00-03:00" }
```

**POST /layout/{page_id}/blocks** — Body: block JSON
```json
{ "id": "blk_new_001", "type": "editoria", "position": 16, ... }
```

**POST /macrotema** — Body: `{ "tag_id": 8901, "label": "Guerra no Irã" }`
```json
{ "page_id": 18200, "tag_id": 8901, "label": "Guerra no Irã", "url": "/macrotema/guerra-no-ira/" }
```

**Erros:**
- `400` — payload inválido (tipo de bloco não registrado, campo obrigatório ausente)
- `401` — não autenticado
- `403` — sem permissão (precisa `edit_posts`)
- `404` — layout ou bloco não encontrado

---

## Contrato 3: Block Type Interface

Cada tipo de bloco implementa:

### Arquivo: `blocks/{type}/render.php`
- Recebe variável `$block` (array) com: id, type, position, visible, config
- Renderiza HTML da seção
- Não faz echo de nada fora da `<section>`
- Usa `esc_attr()`, `esc_html()`, `esc_url()` para output

### Arquivo: `blocks/{type}/style.css`
- Escopar tudo com `.blk-{type} { }`
- Mobile-first responsive
- Usar CSS custom properties do theme.json

### Registro: `inc/class-block-registry.php`
Cada tipo registra:
```php
[
    'type' => 'editoria',
    'label' => 'Editoria',
    'description' => 'Seção por categoria com grid de artigos',
    'config_schema' => [
        'category_id' => ['type' => 'integer', 'required' => true],
        'label' => ['type' => 'string', 'required' => true],
        'posts' => ['type' => 'array', 'required' => true],
        'style' => ['type' => 'string', 'default' => 'grid_5'],
        'show_more_link' => ['type' => 'boolean', 'default' => true],
        'more_link_url' => ['type' => 'string', 'default' => ''],
        'sidebar_widget' => ['type' => 'string', 'default' => ''],
    ],
    'cache_ttl' => 180,
    'style_variants' => ['grid_3', 'grid_4_sidebar', 'grid_5', 'grid_6_mosaic', 'list_compact'],
    'has_auto_expire' => false,
]
```

---

## Contrato 4: Curador V4 ↔ WordPress

O agente Python interage com WordPress exclusivamente via REST API:

```python
# Ler layout atual
GET /brasileira/v1/layout/{page_id}

# Aplicar layout completo (>50% mudanças)
PUT /brasileira/v1/layout/{page_id}
Body: layout JSON completo

# Aplicar mudanças pontuais (<50% mudanças)
PATCH /brasileira/v1/layout/{page_id}/blocks/{block_id}
Body: { "config": {...}, "position": N }

# Criar macrotema
POST /brasileira/v1/macrotema
Body: { "tag_id": 8901, "label": "Guerra no Irã" }

# Arquivar macrotema
DELETE /brasileira/v1/macrotema/{tag_id}
```

### Autenticação
```python
import base64
credentials = base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()
headers = {"Authorization": f"Basic {credentials}", "Content-Type": "application/json"}
```

---

## 18 Tipos de Bloco Registrados

| # | Tipo | Config obrigatório | Config opcional | TTL |
|---|------|-------------------|-----------------|-----|
| 1 | `breaking` | post_id, label, style | auto_expire_minutes | 60s |
| 2 | `manchete` | principal, style | submanchetes[] | 120s |
| 3 | `macrotema` | tag_id, label, posts[], style | icon, subhome_page_id, temporary | 180s |
| 4 | `editoria` | category_id, label, posts[], style | show_more_link, more_link_url, sidebar_widget | 180s |
| 5 | `colunistas` | colunistas[], style | — | 300s |
| 6 | `ultimas` | count, style | auto_refresh_seconds | 60s |
| 7 | `mais_lidas` | period, count, style | — | 300s |
| 8 | `opiniao` | posts[], style | — | 300s |
| 9 | `publicidade` | slot, size | fallback | 3600s |
| 10 | `ticker` | sources[], style | auto_refresh_seconds | 60s |
| 11 | `video` | featured_post_id, style | playlist[] | 300s |
| 12 | `podcast` | style | featured_episode_id, episodes[] | 300s |
| 13 | `regional` | ufs[], posts_per_uf, style | — | 300s |
| 14 | `newsletter_cta` | variant | headline, cta_text | 3600s |
| 15 | `especial` | post_id, style | label | 600s |
| 16 | `galeria` | posts[], style | — | 300s |
| 17 | `trending` | style | count, period | 300s |
| 18 | `custom` | html | — | 600s |
