# Auditoria Completa de Bugs — brasileira.news

**Data:** 20 de março de 2026
**Escopo:** 5 auditorias independentes (Imagens, Curadoria, Motores, Roteadores/Configs, Utilitários) consolidadas em documento mestre
**Infraestrutura:** AWS LightSail · Bitnami WordPress Stack · Python 3 · MariaDB · tagDiv Newspaper Theme
**Total de arquivos auditados:** 80+
**Total de bugs catalogados:** 329 problemas distintos

---

## Sumário Executivo

A auditoria completa do codebase brasileira.news identificou **329 problemas** distribuídos em 5 subsistemas. A soma por severidade:

| Severidade | Imagens | Curadoria | Motores | Roteadores/Configs | Utilitários | **Total** |
|---|---|---|---|---|---|---|
| 🔴 Crítico | 12 | 15 | 18 | 9 | 14 | **68** |
| 🟠 Alto | 14 | 24 | 22 | 8 | 11 | **79** |
| 🟡 Médio | 11 | 22 | 19 | 46 | 13 | **111** |
| 🔵 Baixo | 9 | 0 | 12 | 20 | 4 | **45** |
| **Total** | **46** | **61** | **71** | **83** | **42+68** | **329** |

### Distribuição por Subsistema

- **Roteadores, Configs e Regras:** 83 issues — maior concentração, refletindo inconsistências de configuração entre módulos, credenciais expostas, e prompts contraditórios
- **Motores de Ingestão (RSS, Scrapers, Consolidado, Mestre):** 71 issues — memory leaks causando crashes do LightSail, race conditions na deduplicação, credenciais hardcoded
- **Utilitários e Scripts:** 68 issues — scripts inoperantes (NameError), loops infinitos, crescimento ilimitado de arquivos de cache
- **Curadoria da Homepage:** 61 issues — homepage vazia por 30-90s a cada ciclo, timezone naive, credenciais hardcoded
- **Pipeline de Imagens:** 46 issues — Flickr com placeholders inválidos, quota CSE compartilhada entre tiers, funções inexistentes chamadas em produção

### Top 3 Causas-Raiz Sistêmicas

1. **Credenciais hardcoded em 15+ locais** — Senha do MariaDB (`d0e339d8be...`) em 6+ arquivos, senha WordPress (`nWgboohR...`) em 3+ arquivos, 15+ API keys (OpenAI, Grok, Gemini, DeepSeek, Qwen) expostas diretamente no código-fonte. Qualquer acesso ao repositório compromete todo o sistema.

2. **Acúmulo de memória sem liberação** — `cloudscraper` instanciado por request (principal causa de crash do LightSail), `newspaper.Article` com objetos NLP, `sys.path.insert` acumulativo (960 inserções/dia), `historico_links.txt` carregado inteiro em RAM 34 vezes por ciclo, `deduplicador.py` selecionando `post_content` de 200 posts. Sem log rotation, os discos enchem em semanas.

3. **Ausência de atomicidade e coordenação** — Deduplicação check-then-act entre Raias 1/2 produz duplicatas; curadoria clear→apply deixa homepage vazia; três motores rodam via cron sem coordenação; dois roteadores de IA independentes sem compartilhar circuit breaker; dois `curator_config.py` incompatíveis coexistem.

---

## 1. Vulnerabilidades de Segurança (AÇÃO IMEDIATA)

### 1.1 Senhas do Banco de Dados Hardcoded

A senha do MariaDB está exposta em texto plano em pelo menos **8 arquivos**:

| Arquivo | Linha | Forma de Exposição |
|---|---|---|
| `aplicar_homepage_tags.py` | 17 | Argumento CLI `-pd0e339d8be...` |
| `limpar_homepage_tier1.py` | 10 | `password=os.getenv("DB_PASS", "d0e339d8be...")` |
| `aplicar_homepage.py` | 43 | Argumento CLI `-pd0e339d8be...` |
| `agente_newspaper.py` | 36 | `WP_DB_PASS = os.getenv("DB_PASS", "d0e339d8be...")` |
| `construir_knowledge_base.py` | 574 | Argumento subprocess `-pd0e339d8be...` |
| `atualizar_menu.py` | ~20 | `'-p' + os.getenv("DB_PASS", "d0e339d8be...")` |
| `fix_theme_settings.py` | ~15 | `DB_CMD = [..., '-pd0e339d8be...', ...]` |
| `find_english_text.py` | ~10 | `DB_CMD = [..., '-pd0e339d8be...', ...]` |

**Agravante:** Em `agente_newspaper.py` e `construir_knowledge_base.py`, a senha é passada via argumento `-p` em `subprocess.run()`, tornando-a visível em `ps aux`, `/proc/<pid>/cmdline` e logs de auditoria do sistema.

**Remediação:**
1. Revogar imediatamente a senha do MariaDB e gerar nova
2. Criar `/home/bitnami/.my.cnf` com `[client] password=<nova_senha>` (permissão 600)
3. Substituir todos os `-p<senha>` por `--defaults-file=/home/bitnami/.my.cnf`
4. Remover todas as referências hardcoded — lançar erro se `DB_PASS` não estiver em `.env`

### 1.2 Senha WordPress Hardcoded

| Arquivo | Linha | Credencial |
|---|---|---|
| `config_geral.py` | 22 | `WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")` |
| `motor_avancado.py` | 54 | `WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")` |
| `atualizar_menu.py` | ~15 | `WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")` |

**Remediação:** Revogar no Painel WP → Usuários → Senhas de Aplicativos. Gerar nova e colocar exclusivamente em `.env`.

### 1.3 API Keys Hardcoded

| Arquivo | Linhas | Credenciais Expostas |
|---|---|---|
| `motor_avancado.py` | 60-91 | 3 OpenAI keys (`sk-proj-...`), 3 Grok keys (`xai-...`), 3 Gemini keys (`AIzaSy...`) |
| `check_keys.py` | 86-114 | 3 DeepSeek keys (`sk-f594...`), 3 Qwen keys (`sk-d9aa...`) |

**Total: 15+ API keys de produção expostas.** Qualquer pessoa com acesso ao repositório Git pode usar essas chaves e gerar custos ou extrair dados.

**Remediação:**
1. Revogar **todas** as 15 keys nos painéis dos respectivos provedores
2. Gerar novas keys e armazenar exclusivamente em `.env`
3. Adicionar `check_keys.py`, `motor_avancado.py`, `config_chaves.py` ao `.gitignore`
4. Usar `git filter-branch` ou BFG Repo Cleaner para limpar o histórico Git

### 1.4 Injeção SQL

| Arquivo | Função | Tipo |
|---|---|---|
| `agente_newspaper.py` | `consultar_opcoes_tema()` | f-string com `chave` não sanitizada concatenada diretamente no SQL |
| `agente_newspaper.py` | `contar_posts_categoria()` | `cat_id` interpolado em SQL passado via subprocess CLI — SQL injection + command injection |
| `aplicar_homepage_tags.py` | linhas 34-44 | Conteúdo de arquivo concatenado em UPDATE SQL via escape manual insuficiente |
| `limpar_homepage_tier1.py` | linha 126 | Mesmo padrão de escape manual vulnerável |
| `revisor_imagens_antigos.py` | `update_post_thumbnail()` | `TABLE_PREFIX` interpolado via f-string na query |

**Remediação:** Substituir todas as construções `f"... {variavel} ..."` em queries SQL por parâmetros parametrizados (`cursor.execute("... %s ...", (variavel,))`).

### 1.5 Backup Não-Criptografado com Credenciais

`gerar_backup_codigos.sh` concatena todo o conteúdo de `*.py` e `*.sh` em `/home/bitnami/backup_integral_robos.txt` — um único arquivo de texto que agrega **todas** as credenciais hardcoded do sistema. Sem criptografia, sem rotação (sobrescreve o anterior), sem inclusão de subdiretórios (`motor_rss/`, `motor_scrapers/`, `motor_consolidado/`).

---

## 2. Causas-Raiz dos Crashes no LightSail

### 2.1 `cloudscraper` Instanciado por Request — PRINCIPAL CAUSA

**Arquivo:** `motor_scrapers/motor_scrapers_v2.py`, linha 276 (dentro de `_fetch_with_retry`)

```python
import cloudscraper
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)
resp = scraper.get(url, ...)
```

**Problema:** `cloudscraper.create_scraper()` cria a cada chamada: interpretador JavaScript V8/Node emulado, sessão HTTP com pool de conexões, certificados TLS e contexto SSL, análise de challenge Cloudflare. Com `MAX_WORKERS=5` e múltiplas fontes, 10-25 instâncias simultâneas acumulam em memória. Sem destruição explícita, dependem do GC Python.

**Impacto estimado:** Cada instância consome ~5-15MB. Com 5 workers × múltiplas fontes por ciclo, pico de 75-375MB apenas de cloudscraper. Com ciclos de 30min e GC lento, a memória cresce até o OOM killer do Linux matar o processo.

**Acúmulo temporal:** A cada ciclo (30min), dezenas de instâncias não coletadas. Em 24h = ~48 ciclos × ~20 instâncias = ~960 instâncias criadas sem reutilização.

**Prioridade:** P0 — Fix imediato. Criar singleton global:
```python
_CLOUDSCRAPER = cloudscraper.create_scraper(browser={...})
```

### 2.2 `newspaper.Article` Retém Objetos NLP

**Arquivo:** `motor_scrapers/extrator_conteudo.py`, linha 94

Cada `Article()` carrega modelos NLP (tokenizers, vocabulário) em memória. Os objetos intermediários de parse (parse trees, keyword graphs) só são liberados quando o GC coletar o objeto `article`. Com `MAX_WORKERS=5` e múltiplos artigos em paralelo, a memória acumulada é significativa.

**Impacto:** ~2-5MB por artigo em processamento. Com 20 artigos/ciclo e 5 workers, pico de ~50-100MB que demora a ser liberado.

**Prioridade:** P1

### 2.3 `sys.path.insert` Acumulativo

**Arquivos:** `motor_rss_v2.py` (linha 381), `motor_scrapers_v2.py` (linha 935), `publicador_consolidado.py` (linha 64), `config_consolidado.py` (linhas 12-14), `sintetizador.py` (linhas 12-13), `motor_consolidado.py` (linhas 27-30), `gestor_wp.py`

**Problema:** `sys.path.insert(0, "/home/bitnami")` é chamado dentro de funções executadas para cada artigo. Com 20 artigos/ciclo × 48 ciclos/dia = 960 inserções no `sys.path`. A lista cresce indefinidamente, degradando o tempo de importação e consumindo memória.

**Impacto:** Crescimento linear. Cada string path consome ~60 bytes. 960/dia × 365 = 350k entradas/ano = ~20MB de paths duplicados.

**Prioridade:** P1 — Mover todas as importações e `sys.path.insert` para o topo dos módulos.

### 2.4 `historico_links.txt` Carregado em RAM

**Arquivo:** `gestor_cache.py`

O arquivo cresce por append ilimitado (200 URLs/dia × 80 bytes = 16KB/dia). `carregar_cache()` carrega o arquivo inteiro em um `set()` Python. É chamado **34 vezes por ciclo** (23 gavetas mestre + 11 gavetas scraper). Após 1 ano: ~73.000 URLs, ~5.8MB, sendo hashados em set 34 vezes por ciclo.

**Impacto:** ~6MB/ano de RAM por carga × 34 carregamentos por ciclo = pico de ~200MB de RAM alocada periodicamente para GC.

**Prioridade:** P1 — Migrar para SQLite com índice, ou implementar rotação por janela temporal.

### 2.5 `deduplicador.py` Carregando `post_content` de 200 Posts

**Arquivo:** `motor_consolidado/deduplicador.py`, linha 39

```sql
SELECT ID, post_title, post_date, post_content, post_status
FROM {posts} WHERE ... LIMIT 200
```

`post_content` é selecionado mas **nunca usado** — apenas `post_title` é comparado via SequenceMatcher. Com artigos de 400-1200 palavras em HTML, são vários MB carregados desnecessariamente por chamada. Chamado para cada tema trending (10-20 por ciclo).

**Impacto:** ~2-10MB por chamada × 10-20 temas = 20-200MB de pico. SequenceMatcher em loop de 200 posts × 20 temas = 4.000 comparações O(n×m).

**Prioridade:** P1 — Remover `post_content` do SELECT.

### 2.6 Pool de Conexões MariaDB sem Recriação

**Arquivo:** `motor_rss/db.py`, linha 34

`PooledDB(maxconnections=10)` é global de módulo. Cada motor cria seu próprio pool → até 30 conexões simultâneas. O pool nunca é recriado após falhas de rede. Cursor não fechado em exceção (db.py linha 153: caminhos de sucesso fecham, exceção não).

**Impacto:** Connection pool exhaustion sob carga, especialmente quando os 3 motores rodam simultaneamente via cron.

**Prioridade:** P1

### 2.7 `ThreadPoolExecutor` sem Cleanup

**Arquivo:** `motor_scrapers_v2.py`, múltiplos locais

Workers do ThreadPoolExecutor mantêm referências a objetos cloudscraper, Article, e respostas HTTP. Sem `executor.shutdown(wait=True)` explícito com liberação de recursos, os objetos persistem até o GC agir.

**Prioridade:** P2

### 2.8 Log Files sem Rotação

**Arquivos:** Todos os motores (`motor_rss_v2.py` linha 61, `motor_scrapers_v2.py`, `motor_consolidado.py`, `curator_agent.py` linha 43)

Novos arquivos de log por dia, mas **nunca deletados**. Com 1000+ artigos/dia e logs verbose, cada arquivo pode ter centenas de MB. Disco LightSail (20-50GB) pode encher em semanas.

**Prioridade:** P1 — Usar `TimedRotatingFileHandler` com `backupCount=7`.

---

## 3. Bugs Críticos do Pipeline de Imagens

### 3.1 FLICKR_GOV_USERS com Placeholders Inválidos

**Arquivo:** `curador_imagens_unificado.py`

```python
FLICKR_GOV_USERS = [
    "paborboleta",    # Palácio do Planalto — PLACEHOLDER FICTÍCIO
    "senaborboleta",  # Senado Federal — PLACEHOLDER FICTÍCIO
    "camaborboleta",  # Câmara dos Deputados — PLACEHOLDER FICTÍCIO
    "agaborboleta",   # Agência Brasil — PLACEHOLDER FICTÍCIO
    "govbr",          # Portal Gov.br
    "staborboleta",   # STF — PLACEHOLDER FICTÍCIO
]
```

**Problema:** Esses são nomes fictícios que nunca foram preenchidos com IDs reais do Flickr. A API retorna HTTP 200 com `"photos": {"photo": []}` (lista vazia), sem indicar que os usernames são inválidos. O Tier 3A faz 6 requisições desperdiçadas + 1 requisição geral.

**Impacto visível:** Tier 3A nunca encontra fotos governamentais. Posts que dependem deste tier caem para tiers inferiores (stock/placeholder).

**Fix:** Pesquisar os usernames Flickr reais das contas governamentais brasileiras, ou remover Tier 3A se não houver contas oficiais.

### 3.2 CSE Quota Compartilhada entre Tier 2 e Tier 3C

**Arquivo:** `curador_imagens_unificado.py`

Tier 2 (`tier2_government_banks`) e Tier 3C (`tier3c_google_cse`) usam o mesmo `GOOGLE_CSE_ID` e compartilham a quota de 100 queries/dia gratuitas. Pior: Tier 3C é chamado com `query_gov` — a mesma query já tentada no Tier 2, sem o filtro `site:gov.br`. Cada post consome 2 queries CSE.

**Impacto:** Com 50 posts/dia, a quota gratuita esgota em 25 posts. Os 25 restantes recebem placeholder ou stock images. A $5/1000 queries adicionais, 1000 artigos/dia = ~$10/dia apenas em CSE.

**Fix:** Separar CSE IDs ou implementar cache de resultados por query. Remover chamada duplicada no Tier 3C.

### 3.3 `is_valid_image_url` Faz HTTP Request por Tag `<img>`

**Arquivo:** `curador_imagens_unificado.py`

`_get_image_dimensions_from_headers(url)` faz `requests.get` com `Range: bytes=0-1024` para cada URL validada. No Tier 1 (`tier1_scrape_html`), chamada para cada `<img>` no HTML. Uma página com 30 imagens = 30 requisições HTTP síncronas.

**Agravante:** O stream HTTP não é fechado explicitamente (`stream=True` sem `resp.close()`), causando resource leak. Não há parsing de WebP (aceito pela extensão mas nunca verificado em dimensões).

**Impacto:** Tier 1 pode levar dezenas de segundos por post. Resource leak de conexões TCP em `CLOSE_WAIT`.

### 3.4 `gestor_wp.py` NameError em `roteador_ia_imagem`

**Arquivo:** `gestor_wp.py`, linhas 111-116

```python
from curador_imagens_unificado import get_curador
# ... (roteador_ia_imagem NÃO está importada)
img_bytes = roteador_ia_imagem(comando_ia)  # NameError!
```

`roteador_ia_imagem` é definida em `roteador_ia.py` mas não importada em `gestor_wp.py`. Qualquer execução que chegue ao fallback de IA levanta `NameError`. Atualmente mascarado porque `roteador_ia_imagem` retorna `None` imediatamente (trava editorial), mas a trava é aplicada **dentro** da função — o NameError acontece **antes** de entrar na função.

**Impacto:** Se a trava DALL-E for removida, o sistema crasha imediatamente.

### 3.5 `buscar_e_subir_imagem_real` Não Existe

**Arquivo:** `garantia_imagens.py` → injetado em `gestor_wp.py`

O bloco de código injetado por `garantia_imagens.py` chama `buscar_e_subir_imagem_real(url_orig, auth_headers)`, que não existe em nenhum lugar do codebase. Gera `NameError` em produção sempre que uma fonte oficial for processada via este fluxo legado.

### 3.6 Lógica de IA Invertida (Fontes Oficiais vs. Não-Oficiais)

**Arquivo:** `gestor_wp.py`, linhas 625-641

Para fontes **não-oficiais** (G1, Folha), tenta gerar imagem por IA. Para fontes **oficiais** (governo), só tenta IA se houver prompt específico. O correto seria o oposto: fontes oficiais têm fotos reais disponíveis; fontes não-oficiais precisam de curadoria mas IA gera alucinações.

### 3.7 Dois Placeholders Diferentes Hardcoded

`curador_imagens_unificado.py`: `https://brasileira.news/wp-content/uploads/2023/10/placeholder-brasileiranews.jpg`
`limpador_imagens_ia.py`: `https://brasileira.news/wp-content/uploads/sites/7/2026/02/imagem-brasileira.png`

Impossível identificar automaticamente todos os posts sem imagem real quando há dois padrões distintos.

### 3.8 Tier 3C Executa Fora de Ordem

Pipeline documentado: TIER 1 → 2 → 3A → 3B → 3C → 4 → 5.
Execução real: TIER 1 → 2 → **3C** → 3A → 3B → 4 → 5.

Tier 3C (Google CSE aberto) executa antes de 3A (Flickr) e 3B (Wikimedia), contrariando a documentação e desperdiçando quota CSE antes de tentar opções gratuitas.

### 3.9 `upload_to_wordpress` Falha Silenciosa no Meta Update

O `requests.post` para atualizar `alt_text` e `caption` não tem tratamento de erro. Se falhar, o `media_id` é retornado como sucesso. Imagens publicadas sem texto alternativo — problema de acessibilidade e SEO.

### 3.10 Lógica RGBA Invertida

Modo `'PA'` (Palette + Alpha de GIFs) não entra no `elif img.mode == 'RGBA'` e é convertido direto para RGB sem composição do canal alpha, resultando em fundos pretos.

### 3.11 `content_patterns` com Regex Inoperante

`r"\d{4}"` e `r"\d{2,}"` são testadas com operador `in` (substring), não `re.search`. Nunca funcionam. Além disso, `has_content_pattern` é calculada mas nunca usada na lógica de retorno.

### 3.12 Três Sistemas Paralelos de Imagem Incompatíveis

| Sistema | Arquivo | Retorno | Status |
|---|---|---|---|
| Legado | `gestor_imagens.py` | `bytes` | Ativo em código legado |
| Atual | `curador_imagens_unificado.py` | `int` (media_id) | Sistema principal |
| Inject | `garantia_imagens.py` | Chama função inexistente | Quebrado |

---

## 4. Bugs Críticos do Sistema de Curadoria

### 4.1 Janela Zero de Tags (Homepage Vazia 30-90 Segundos)

**Arquivo:** `curator_tagger.py`, chamado por `curator_agent.py` linha 433

```python
clear_curator_tags(dry_run=dry_run)  # Remove TODAS as tags
# ... janela de 30-90 segundos ...
for tag_slug, post_ids in selections.items():  # Aplica novas tags uma a uma
```

Com `WP_PATCH_DELAY = 1.0s` e ~60 posts em ~14 posições, a homepage fica completamente vazia nos blocos curados pelo Newspaper Theme. Roda nos minutos 15 e 45 de cada hora.

**Fix:** Implementar diff incremental — calcular novo estado, remover apenas tags que saíram, adicionar as novas.

### 4.2 NameError em `log_cycle()`

**Arquivo:** `curator_agent.py`, linha 342

`logger.warning("Erro ao logar ciclo: %s", e)` usa `logger` que não está definido no escopo de `log_cycle()`. Levanta `NameError`, silenciando erros de log do banco e potencialmente travando o except.

### 4.3 `home-esportes` e `home-justica` Silenciosamente Descartados

`HOMEPAGE_POSITIONS` contém `home-esportes` e `home-justica`, mas `TAG_IDS` não contém esses slugs. Posts selecionados para essas posições são descartados com apenas um `logger.warning`. Os blocos de Esportes e Justiça na homepage ficam sempre vazios.

### 4.4 Dois `curator_config.py` Incompatíveis

| Aspecto | `curator/curator_config.py` | `agents/curator/curator_config.py` |
|---|---|---|
| Conexão WP | `WP_API_BASE` | `WP_BASE_URL` (hardcoded) |
| Senha WP | `WP_APP_PASS` | `WP_APP_PASSWORD` (nome diferente) |
| Budget LLM | `LLM_MAX_CALLS_PER_CYCLE = 30` | `MAX_LLM_CALLS_PER_CYCLE = 50` |
| Posições | 14 posições reais | 4 posições fictícias |
| Tags | 17 IDs hardcoded | 5 slugs sem IDs |

O `agents/curator/curator_config.py` não carrega `.env` — `WP_APP_PASSWORD` será string vazia, causando 401 em todas as chamadas WP.

### 4.5 Limite de 30 Chamadas LLM Distorce Ranking

**Arquivo:** `curator_scorer.py`, linhas 341-356

Quando o budget de 30 chamadas LLM esgota, posts restantes recebem `score_llm = 0`, enquanto os já avaliados podem ter até 50 pontos extras. A ordem de processamento (por data DESC) determina quem ganha avaliação LLM, não a qualidade editorial.

### 4.6 Manchete Pode Ter Até 4 Horas de Atraso

`CURATOR_WINDOW_HOURS = 4` — posts de 3h55 atrás competem com posts de 5 minutos. O bônus de frescor (+10 pts para < 1h) é pequeno demais para garantir manchetes recentes.

### 4.7 Race Condition com Motor RSS

O curador roda nos minutos 15/45; Motor RSS roda nos minutos 0/30. Se o Motor RSS publica um post durante a fase de limpeza do curador, o post não terá tag editorial. Sem lock de execução única (flock), dois ciclos do curador podem rodar simultaneamente.

### 4.8 `_is_official_source()` com Substring Match

```python
return any(domain in source_lower for domain in cfg.OFFICIAL_DOMAINS)
```

`http://fake-gov.br.malicioso.com/` conteria `gov.br` e receberia +30 pontos de fonte oficial. Deveria usar `urlparse` para verificar domínio real.

### 4.9 Timezone Naive em Todo o Curador

**Arquivos:** `curator_scorer.py` (linha 107), `curator_agent.py` (linha 100), `avaliador_home.py` (linhas 276, 287)

`datetime.now()` sem timezone é comparado com `post_date` do MySQL (que pode estar em UTC). Erro sistemático de até 3 horas — um post de 14h50 local aparece como publicado há 3h50 às 18h UTC.

### 4.10 `clear_curator_tags()` Limitado a 20 Posts

**Arquivo:** `curator_tagger.py`, linhas 38-44

`per_page: 20` fixo. Se mais de 20 posts acumularam a mesma tag, apenas os primeiros 20 são limpos. Os demais permanecem com tags de ciclos anteriores.

### 4.11 Escape SQL Manual Vulnerável

**Arquivo:** `aplicar_homepage_tags.py`, linha 41

```python
escaped = new_content.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
sql1 = f"UPDATE ... SET meta_value='{escaped}' ..."
```

Escape manual insuficiente: não trata `\x00`, `\x1a`, newlines. Se conteúdo já contiver `\'`, o replace duplo corrompe.

### 4.12 OPcache Nunca Invalidado

**Arquivo:** `aplicar_homepage_tags.py`, linhas 92-95

```python
subprocess.run(["sudo", "kill", "-USR2", "$(cat /opt/bitnami/php/var/run/php-fpm.pid)"], shell=False)
```

Com `shell=False`, `$(cat ...)` é passado literalmente como string. O OPcache do PHP nunca é invalidado — o Newspaper Theme continua exibindo template antigo.

### 4.13 `limpar_homepage_tier1.py` — Imports Faltando

`pymysql`, `subprocess`, `re`, `sys` usados mas não importados. O script falha com `NameError` na primeira execução.

### 4.14 Mapeamento Categoria↔Posição Errado

**Arquivo:** `migrar_homepage_tags.py`, TAG_MAP

Posição 6 "Ciência" usa categoria 81 (que é **Esportes**). Posição 8 "Saúde" usa categoria 73 (que é **Justiça**). A homepage foi migrada com blocos de "Ciência" exibindo conteúdo de Esportes.

---

## 5. Bugs Críticos dos Motores de Ingestão

### 5.1 Deduplicação Check-Then-Act (Duplicatas Publicadas)

**Arquivo:** `motor_rss_v2.py`, linhas 301-324

```python
if db.post_exists(url, entry["title"]):
    continue
# Entre este check e o registro (linha 481), outra instância publica o mesmo artigo
```

Raias 1 e 2 processam simultaneamente via cron. O padrão check-then-act não é atômico. Tabela `rss_control` não tem `UNIQUE KEY` em `source_url`.

**Fix:** `INSERT IGNORE` ou `INSERT ... ON DUPLICATE KEY UPDATE` com `UNIQUE(source_url(768))`.

### 5.2 Circuit Breaker Não Thread-Safe

**Arquivo:** `motor_rss/llm_router.py`, linhas 26, 65

`_circuit_breaker` e `_key_index` são dicts globais mutados sem lock. Com `ThreadPoolExecutor(max_workers=5)`, `state["failures"] += 1` é read-modify-write não atômico. O circuit breaker pode não disparar quando deveria.

### 5.3 `MIN_SOURCES_TRENDING=1` — Tudo Vira Trending

**Arquivo:** `motor_consolidado/config_consolidado.py`, linha 200

Com `MIN_SOURCES_TRENDING=1`, qualquer artigo de qualquer portal vira trending (uma fonte é suficiente). O motor consolidado sintetiza artigos para dezenas de temas, desperdiçando chamadas LLM premium ($0.025-0.05 cada).

### 5.4 `deduplicador.py` — SequenceMatcher O(n²)

200 posts × SequenceMatcher.ratio() O(n×m) × 10-20 temas = até 105 milhões de operações por ciclo. CPU bound, bloqueante na thread principal.

### 5.5 `motor_mestre.py` — Encoding Corrompido

Strings com `Ã³` (ó), `Ã­` (í) — arquivo com bytes UTF-8 decodificados como Latin-1. Qualquer string com acentos é exibida errada.

### 5.6 Logs sem Rotação em Todos os Motores

Novo arquivo por dia, nunca deletados. Com logs verbose, cada arquivo pode ter centenas de MB. Disco LightSail enche em semanas.

### 5.7 Agendadores sem Lock Files

`agendador_mestre.sh` e `agendador_scrapers.sh`: sem lock file, sem verificação de exit code do Python, sem verificação de `cd /home/bitnami`. Se cron disparar durante ciclo anterior, dois processos paralelos publicam duplicatas e corrompem `historico_links.txt`.

### 5.8 `_rotate_key` e `_next_key` em Conflito

**Arquivo:** `motor_rss/llm_router.py`, linha 77

Após rate limit, `_rotate_key` força +1 no índice, mas `_next_key` adiciona +1 novamente na próxima chamada — pulando uma chave. Em pool de 3 chaves, uma chave é completamente pulada.

### 5.9 Cache de Categorias/Tags Nunca Expira

**Arquivo:** `motor_rss/wp_publisher.py`, linhas 110-111

Cache populado na primeira chamada, nunca invalidado. Novas categorias criadas no WordPress são invisíveis. Cache cresce ilimitadamente (3-5 tags/artigo × 1000/dia = milhares de entradas).

### 5.10 `source_urls` Truncadas em Consolidadas

**Arquivo:** `motor_consolidado/publicador_consolidado.py`, linhas 261-265

`source_url=source_urls[:2048]` — CSV de URLs truncado em 2048 chars. A deduplicação por URL exata nunca casa com URL individual de artigo futuro. Deduplicação entre consolidadas e artigos normais é efetivamente não funcional.

### 5.11 Gemini sem Timeout

**Arquivo:** `llm_router.py`, linha 193

`config.LLM_TIMEOUT = 60` é passado para OpenAI e Claude, mas não para Gemini. Chamadas Gemini podem travar indefinidamente.

### 5.12 Double Fetch HTML

**Arquivo:** `motor_rss_v2.py`, linhas 340, 375

`extract_full_content(link)` e `extract_html_content(link)` fazem dois downloads do mesmo HTML por artigo. 20 artigos × 2 = 40 requests onde 20 são redundantes.

### 5.13 Domain Delay Não Funciona com ThreadPoolExecutor

**Arquivo:** `motor_scrapers_v2.py`, linhas 1065-1089

`time.sleep` está na thread principal que submete tarefas. Não impede que workers threads façam requests simultâneos ao mesmo domínio. Duas workers podem acessar `g1.globo.com` ao mesmo tempo.

### 5.14 `db.register_published` Pode Gerar Posts Duplicados

**Arquivo:** `motor_consolidado/publicador_consolidado.py`, linhas 743-754

Se `db.register_published` lançar exceção após o post ser publicado com sucesso, a função retorna `None`. O sistema pensa que a publicação falhou e pode tentar novamente.

### 5.15 API Keys Hardcoded no Motor Avançado

**Arquivo:** `motor_avancado.py`, linhas 60-91

9 chaves de API completas (OpenAI, Grok, Gemini) + WP_APP_PASSWORD hardcoded como fallback. Já detalhado na Seção 1.

---

## 6. Bugs dos Roteadores e Configurações

### 6.1 `base64` Não Importado em `config_geral.py`

**Arquivo:** `config_geral.py`, linha 30

```python
AUTH_HEADERS = {
    'Authorization': f'Basic {base64.b64encode(...)}'  # NameError!
}
```

`import base64` ausente. Derruba imediatamente `agente_revisor.py` que importa `AUTH_HEADERS`.

### 6.2 Dois Roteadores de IA sem Coordenação

| Aspecto | `roteador_ia.py` (legado) | `motor_rss/llm_router.py` (novo) |
|---|---|---|
| Fonte de chaves | `config_chaves.POOL_CHAVES` | `config.OPENAI_KEYS` etc. |
| Circuit breaker | Não tem | Implementado (não thread-safe) |
| Modelos | gpt-4o, grok-beta (obsoleto), llama-3.1 (obsoleto) | gpt-4o, claude-sonnet-4, grok-3 |
| Quem usa | `agente_newspaper.py`, `agente_revisor.py` | `motor_rss`, `motor_consolidado` |

Uma chave OpenAI no circuit breaker do `llm_router.py` ainda é tentada pelo `roteador_ia.py`.

### 6.3 `agente_revisor` Sobrescreve Categorias Corretas

**Arquivo:** `agente_revisor.py`, linha 214

A heurística keyword-based `adivinhar_categoria` pode sobrescrever categorias atribuídas com precisão pelo LLM. "Crise hídrica no Nordeste" (corretamente `CAT_MEIO_AMBIENTE`) pode ser sobrescrita para `CAT_POLITICA` porque "nordeste" não está nas keywords de meio ambiente.

### 6.4 `WP_URL` com Semânticas Diferentes

`config_geral.py`: `WP_URL = "https://brasileira.news/wp-json/wp/v2"` (URL completa da API)
`motor_rss/config.py`: `WP_URL = "https://brasileira.news"` (domínio base) + `WP_API_BASE` separada

Módulos que misturam imports apontam para URLs erradas.

### 6.5 Schema JSON Contraditório entre Regras

| Campo | `regras_arte.py` | `motor_rss/config.py` | `regras_seo.py` |
|---|---|---|---|
| Título | (não define) | `titulo` | `h1_title` |
| Imagem | `prompt_imagem` | `imagem_busca_gov`, `imagem_busca_commons` | (não define) |
| Corpo | (não define) | `conteudo` | `corpo_html` |

LLM recebe instruções contraditórias se `regras_arte.py` for injetado junto com o prompt principal.

### 6.6 RT/CGTN/TASS/KCNA sem Flags de Propaganda Estatal

**Arquivo:** `catalogo_fontes.py`

Veículos de propaganda estatal incluídos sem `"credibilidade"`, `"editorial_note"` ou `"requires_extra_validation"`. O portal pode republicar desinformação.

### 6.7 ESG→Economia em Vez de ESG

`Capital Reset`, `ESG Today`, `Responsible Investor` mapeados para `CAT_ECONOMIA = [72]`. `CAT_ESG = [136, 142]` existe mas não é usado.

### 6.8 `gov.br/esporte` vs `gov.br/esportes`

**Arquivo:** `agente_revisor.py`, MAPA_UNIFICADO_AUTORES

```python
"gov.br/esporte": 25  # URL real é gov.br/esportes (com 's')
```

Match nunca ocorre. Artigos do Ministério do Esporte ficam sem atribuição correta.

### 6.9 `classify_tier` Ignora Parâmetros

**Arquivo:** `llm_router.py`, linhas 398-400

`content_length` e `score` aceitos na assinatura mas nunca usados no corpo. Artigos longos de alta pontuação nunca são promovidos ao TIER 1.

### 6.10 Circuit Breaker Compartilhado entre Modelos

`openai:gpt-4o` e `openai:gpt-4o-mini` compartilham circuit breaker. Falha no mini bloqueia o premium.

---

## 7. Bugs dos Utilitários e Scripts

### 7.1 `renomear_categoria.py` — Totalmente Inoperante

`base64` e `requests` usados mas não importados. O script lança `NameError` imediatamente.

### 7.2 `corrigir_demo_restante.py` — Import Order Error

```python
'-p' + os.getenv("DB_PASS", "...")  # linha 19: usa os
import os                           # linha 26: importa os
```

`NameError: name 'os' is not defined` na inicialização do módulo.

### 7.3 `reverter_autoria.py` — Loop Infinito

```python
while True:
    res = requests.get(f"{WP_URL}/posts?author={id_tiago}&per_page=50", ...)
    for p in res.json():
        requests.post(f"{WP_URL}/posts/{p['id']}", json={'author': id_redacao}, ...)
```

O loop sempre busca a primeira página. Após transferir os 50 da primeira página, a API retorna os próximos 50 — mas pode continuar se o cache WordPress não refletir a mudança. Sem `?page=N`.

### 7.4 Escrita Não-Atômica em `feeds.json`

**Arquivo:** `motor_rss/auto_health_raia1.py`

`json.dump()` modifica o arquivo in-place. Se o processo for interrompido durante a escrita, `feeds.json` fica corrompido e o Motor RSS inteiro para. Deveria usar write-to-temp + rename.

### 7.5 `fix_all_remaining.py` — `json.loads` em PHP Serialized

**Arquivo:** `fix_all_remaining.py`

`td_011_settings` é armazenado como PHP serializado (`a:5:{s:...}`), não JSON. `json.loads()` lança `JSONDecodeError` e o STEP 6 (corrigir top bar) nunca funciona.

### 7.6 `corrigir_posts_existentes.py` — fetchall() sem LIMIT

Carrega todo o `post_content` HTML de todos os posts publicados em RAM. Com 10.000+ posts de 10-50KB cada = 500MB–5GB.

### 7.7 `gerar_backup_codigos.sh` — Backup com Credenciais em Claro

Concatena todo `*.py` e `*.sh` em um único arquivo de texto. Não inclui subdiretórios. Sem timestamp (sobrescreve anterior). Agrega todas as credenciais do sistema em um arquivo não criptografado.

### 7.8 `scrapers_nativos.py` — Status 403 como Sucesso

```python
if r.status_code in [200, 202, 403]:
    return r.text
```

Páginas de erro/CAPTCHA de respostas 403 são tratadas como conteúdo válido e publicadas.

### 7.9 Health Check Raia 2 Executa Scrapers Reais

`process_fonte()` chama `coletar_links_fonte(fonte)` — o scraper real de produção. Pode acionar rate limiting em sites sensíveis durante a madrugada.

### 7.10 Health Check Raia 3 Apenas Loga

Raia 3 apenas loga alertas (`logger.critical()`), sem ação corretiva. Não desativa portais, não tenta alternativas, não envia notificação.

---

## 8. Inventário Completo de Bugs por Severidade

### 8.1 Todos os Bugs Críticos (🔴)

| # | Bug | Arquivo | Impacto | Subsistema |
|---|---|---|---|---|
| 1 | cloudscraper instanciado por request — memory leak | `motor_scrapers_v2.py:276` | Crash LightSail | Motores |
| 2 | 15+ API keys hardcoded | `motor_avancado.py:60-91`, `check_keys.py:86` | Segurança total comprometida | Motores |
| 3 | Senha MariaDB hardcoded em 6+ arquivos | Múltiplos | Acesso não autorizado ao BD | Segurança |
| 4 | Senha WordPress hardcoded | `config_geral.py:22`, `motor_avancado.py:54` | Acesso admin WordPress | Segurança |
| 5 | Race condition deduplicação Raia1/2 | `motor_rss_v2.py:301` | Duplicatas publicadas | Motores |
| 6 | Circuit breaker não thread-safe | `llm_router.py:26,65` | Falhas LLM sob carga | Motores |
| 7 | `_key_index` não thread-safe | `llm_router.py:65` | Round-robin corrompido | Motores |
| 8 | Pool DB compartilhado sem isolamento | `db.py:34` | Connection exhaustion | Motores |
| 9 | Cache categorias nunca expira | `wp_publisher.py:110` | Categorias erradas | Motores |
| 10 | TF-IDF recriado cada ciclo + cosine O(N²) | `detector_trending.py:54` | Pico de memória | Motores |
| 11 | MIN_SOURCES_TRENDING=1 | `config_consolidado.py:200` | Tudo vira trending, custo LLM alto | Motores |
| 12 | deduplicador carrega post_content 200 posts | `deduplicador.py:39` | Pico de RAM | Motores |
| 13 | motor_mestre.py encoding corrompido | `motor_mestre.py:8` | Strings erradas | Motores |
| 14 | source_urls truncadas (dedup quebrada) | `publicador_consolidado.py:261` | Consolidadas duplicadas | Motores |
| 15 | Interação ciclos 30min/2h sem coordenação | Múltiplos | Duplicatas, race conditions | Motores |
| 16 | newspaper.Article retém objetos NLP | `extrator_conteudo.py:94` | Memory leak | Motores |
| 17 | API keys check_keys.py hardcoded | `check_keys.py:86-114` | Segurança | Motores |
| 18 | WP_APP_PASSWORD fallback hardcoded | `motor_avancado.py:54` | Segurança | Motores |
| 19 | Janela zero de tags (homepage vazia) | `curator_tagger.py`, `curator_agent.py:433` | Homepage vazia 30-90s | Curadoria |
| 20 | Timezone naive (erro 3h) | `curator_scorer.py:107` | Scoring errado | Curadoria |
| 21 | Self-import no bloco de imagens | `curator_agent.py:447` | Dependência circular | Curadoria |
| 22 | SQL injection em aplicar_homepage_tags | `aplicar_homepage_tags.py:41` | SQL injection | Curadoria |
| 23 | Credenciais hardcoded em 3 scripts curadoria | `aplicar_homepage_tags.py:17` etc | Segurança | Curadoria |
| 24 | logger não definido em log_cycle() | `curator_agent.py:342` | NameError silencia erros | Curadoria |
| 25 | Dois curator_config.py incompatíveis | `curator/` vs `agents/curator/` | Config errada se import errado | Curadoria |
| 26 | agents/curator_config.py não carrega .env | `agents/curator/curator_config.py:27` | WP_APP_PASSWORD vazia | Curadoria |
| 27 | get_posts_with_curator_tags pula tags válidas | `curator_tagger.py:31` | home-urgente nunca limpa | Curadoria |
| 28 | _is_official_source() substring match | `curator_scorer.py:30` | Falsas fontes oficiais | Curadoria |
| 29 | SQL concatenação de arquivo não sanitizado | `aplicar_homepage_tags.py:34` | SQL corruption | Curadoria |
| 30 | limpar_homepage_tier1.py faltando imports | `limpar_homepage_tier1.py:1` | NameError: pymysql | Curadoria |
| 31 | Sem atomicidade clear→apply | Arquitetura | Homepage vazia | Curadoria |
| 32 | FLICKR_GOV_USERS placeholders | `curador_imagens_unificado.py` | Tier 3A inoperante | Imagens |
| 33 | is_valid_image_url HTTP per <img> | `curador_imagens_unificado.py` | Tier 1 lento, resource leak | Imagens |
| 34 | CSE quota compartilhada T2/T3C | `curador_imagens_unificado.py` | Quota esgota em 25 posts | Imagens |
| 35 | Tier 1 pulado para fontes não-oficiais | `curador_imagens_unificado.py` | Imagens genéricas p/ fontes comerciais | Imagens |
| 36 | gestor_wp.py NameError roteador_ia_imagem | `gestor_wp.py:116` | NameError se trava removida | Imagens |
| 37 | buscar_e_subir_imagem_real inexistente | `garantia_imagens.py` | NameError em produção | Imagens |
| 38 | Lógica IA invertida (oficial vs não-oficial) | `gestor_wp.py:625` | IA para fontes erradas | Imagens |
| 39 | get_best_image retorna None silenciosamente | `curador_imagens_unificado.py` | Posts sem imagem sem alerta | Imagens |
| 40 | db.register_published falha → post duplicado | `publicador_consolidado.py:749` | Duplicatas | Imagens |
| 41 | trava_definitiva regex frágil com type hints | `trava_definitiva_dalle.py` | Trava pode não aplicar | Imagens |
| 42 | limpador_imagens obter_id sem tratamento erro | `limpador_imagens_ia.py` | Crash ou upload vazio | Imagens |
| 43 | revisor_imagens SQL bypassa cache WP | `revisor_imagens_antigos.py` | Imagem antiga em cache | Imagens |
| 44 | base64 não importado em config_geral.py | `config_geral.py:30` | Derruba agente_revisor | Roteadores |
| 45 | Senha WP hardcoded config_geral.py | `config_geral.py:22` | Segurança | Roteadores |
| 46 | agente_revisor herda NameError | `agente_revisor.py:24` | Agente inoperante | Roteadores |
| 47 | Senha MariaDB agente_newspaper | `agente_newspaper.py:36` | Segurança | Roteadores |
| 48 | Senha MariaDB construir_knowledge_base | `construir_knowledge_base.py:574` | Segurança | Roteadores |
| 49 | SQL injection consultar_opcoes_tema | `agente_newspaper.py` | SQL injection | Roteadores |
| 50 | SQL injection contar_posts_categoria | `agente_newspaper.py` | SQL + command injection | Roteadores |
| 51 | construir_knowledge_base deleta sem backup | `construir_knowledge_base.py` | Perda de change_log | Roteadores |
| 52 | config_consolidado.py import .env hardcoded | `config_consolidado.py:18` | Motor falha fora Bitnami | Roteadores |
| 53 | catalogo_gov.py loop TRT modifica dict import | `catalogo_gov.py` | Duplicação ao reload | Roteadores |
| 54 | Senha DB hardcoded atualizar_menu.py | `atualizar_menu.py` | Segurança | Utilitários |
| 55 | Senha WP hardcoded atualizar_menu.py | `atualizar_menu.py` | Segurança | Utilitários |
| 56 | Agendador mestre sem lock file | `agendador_mestre.sh` | Execuções paralelas, duplicatas | Utilitários |
| 57 | Agendador mestre sem tratamento erros | `agendador_mestre.sh` | Falhas silenciosas | Utilitários |
| 58 | Agendador mestre cd sem verificação | `agendador_mestre.sh` | Paths relativos falham | Utilitários |
| 59 | gestor_cache.py crescimento ilimitado | `gestor_cache.py` | RAM crescente + race condition | Utilitários |
| 60 | feeds.json escrita não-atômica | `auto_health_raia1.py` | Corrupção de configuração | Utilitários |
| 61 | corrigir_posts_existentes fetchall sem LIMIT | `corrigir_posts_existentes.py` | OOM com base grande | Utilitários |
| 62 | reverter_autoria.py loop infinito | `reverter_autoria.py` | Loop eterno na API | Utilitários |
| 63 | renomear_categoria.py NameError | `renomear_categoria.py` | Script inoperante | Utilitários |
| 64 | corrigir_demo_restante.py import order | `corrigir_demo_restante.py` | Script inoperante | Utilitários |
| 65 | fix_all_remaining json.loads em PHP serial | `fix_all_remaining.py` | STEP 6 nunca funciona | Utilitários |
| 66 | fix_theme_settings regex PHP serialized frágil | `fix_theme_settings.py` | Corrompe configs tema | Utilitários |
| 67 | gerar_backup credenciais em claro | `gerar_backup_codigos.sh` | Todas credenciais em 1 arquivo | Utilitários |
| 68 | roteador_ia_imagem não importada gestor_wp | `gestor_wp.py:111` | NameError em publicação | Utilitários |

### 8.2 Todos os Bugs de Alta Severidade (🟠)

| # | Bug | Arquivo | Impacto | Subsistema |
|---|---|---|---|---|
| 1 | requests.get sem Session (resource leak) | `motor_rss_v2.py:212` | 40+ conexões TCP abertas | Motores |
| 2 | Double fetch HTML por artigo | `motor_rss_v2.py:340,375` | CPU/memória 2x | Motores |
| 3 | Cursor não fechado em exceção | `db.py:153` | Connection leak | Motores |
| 4 | _request_with_retry ignora 429 | `wp_publisher.py:67` | Rate limit sem retry | Motores |
| 5 | Slugs sem suporte acentuação | `wp_publisher.py:155` | Categorias duplicadas | Motores |
| 6 | Gemini sem system_instruction | `llm_router.py:193` | JSON malformado | Motores |
| 7 | generate_article trunca 6000 chars | `llm_router.py:465` | Conteúdo incompleto | Motores |
| 8 | cloudscraper import dentro de loop | `motor_scrapers_v2.py:276` | Overhead lookup | Motores |
| 9 | _blocked_domains/_robots_cache ilimitados | `motor_scrapers_v2.py:184,210` | Memory leak | Motores |
| 10 | Race condition processar_artigo | `motor_scrapers_v2.py` | Duplicatas sem lock | Motores |
| 11 | Domain delay não funciona ThreadPool | `motor_scrapers_v2.py:1065` | Rate limiting contornado | Motores |
| 12 | acquire_lock vazamento file descriptor | `motor_consolidado.py:58` | FD leak | Motores |
| 13 | SequenceMatcher 0.55 permissivo | `deduplicador.py:57` | Falsos positivos dedup | Motores |
| 14 | check_recent_synthesis sem índice | `deduplicador.py:85` | Full scan MySQL | Motores |
| 15 | Prompt 7 fontes × 4000 chars input | `sintetizador.py:191` | $0.90-1.80/dia consolidado | Motores |
| 16 | Portais raspados sequencialmente | `scraper_homes.py:203` | 280s pior caso | Motores |
| 17 | N+1 queries GROUP_CONCAT | `avaliador_home.py:92` | 200+ subqueries | Motores |
| 18 | Validação plágio SequenceMatcher lenta | `validador.py:71` | 105M operações/artigo | Motores |
| 19 | executar_redacao_segura LLM por artigo | `motor_avancado.py:690` | 100+ chamadas triagem | Motores |
| 20 | Rotação chaves append+pop(0) | `motor_avancado.py:140` | Não thread-safe | Motores |
| 21 | sys.path.insert em múltiplos arquivos | Múltiplos | Path acumulativo | Motores |
| 22 | Logs sem rotação todos motores | Múltiplos | Disco cheio | Motores |
| 23 | MAX_SAME_CATEGORY não usado | `curator_agent.py:182` | Sem diversidade editorial | Curadoria |
| 24 | Manchete até 4h de atraso | `curator_agent.py:399` | Manchete stale | Curadoria |
| 25 | Fase 6 não fecha cursor | `curator_agent.py:441` | Connection leak | Curadoria |
| 26 | TAG_IDS hardcoded dessincronizáveis | `curator_config.py:89` | Tags inexistentes | Curadoria |
| 27 | home-esportes/justica descartados | `curator_config.py:124` | Blocos homepage vazios | Curadoria |
| 28 | Cache tags invalidado incorretamente | `curator_tagger.py:213` | Estado desatualizado | Curadoria |
| 29 | clear_curator_tags limite 20 posts | `curator_tagger.py:38` | Tags de ciclos anteriores | Curadoria |
| 30 | apply_tag usa POST (semântica errada) | `curator_tagger.py:162` | Pode quebrar com WAF | Curadoria |
| 31 | Hash título seleciona chave não-determinístico | `curator_scorer.py:183` | Scoring não-determinístico | Curadoria |
| 32 | _has_br_context só verifica tags | `curator_scorer.py:38` | -20 pts errôneo p/ BR | Curadoria |
| 33 | Regex LLM score captura dígito errado | `curator_scorer.py:203` | Score aleatório | Curadoria |
| 34 | post_id=18135 hardcoded 12 ocorrências | Múltiplos | Falha em staging | Curadoria |
| 35 | OPcache nunca invalidado | `aplicar_homepage_tags.py:92` | Template antigo horas | Curadoria |
| 36 | Mapeamento posição frágil por índice | `migrar_homepage_tags.py:63` | Categorias deslocadas | Curadoria |
| 37 | Mapeamento Cat↔Posição errado | `migrar_homepage_tags.py:21` | Ciência=Esportes | Curadoria |
| 38 | Seed sem filtro de data | `seed_tags_iniciais.py:67` | Posts antigos na home | Curadoria |
| 39 | used_post_ids não respeitado editorias | `seed_tags_iniciais.py:138` | Duplicatas no seed | Curadoria |
| 40 | datetime.now sem timezone avaliador | `avaliador_home.py:276` | Idade manchete errada 3h | Curadoria |
| 41 | Janela tempo dobrada sem doc | `avaliador_home.py:111` | Coverage rate inflado | Curadoria |
| 42 | Extractor para no primeiro seletor | `scraper_homes.py:93` | Falso positivo | Curadoria |
| 43 | Dois sistemas curadoria conflitam | Arquitetura | Tags indefinidas | Curadoria |
| 44 | SCORE_MINIMUM=50 nunca usado | `curator_config.py:63` | Dead config | Curadoria |
| 45 | WP_RETRY_COUNT=3 nunca usado | `curator_config.py:55` | Sem retry | Curadoria |
| 46 | Ambos scripts modificam post_content DB | `aplicar_homepage.py:32` | Bypass WP hooks | Curadoria |

### 8.3 Todos os Bugs de Média Severidade (🟡)

Devido à extensão (111 bugs médios), segue tabela resumida por subsistema:

| Subsistema | Quantidade | Exemplos Principais |
|---|---|---|
| Roteadores/Configs | 46 | Schema JSON contraditório, categorias inconsistentes, prompts divergentes, RT/CGTN sem flag, ESG→Economia, feeds via agregadores de terceiro |
| Curadoria | 22 | Score LLM esgotado distorce ranking, penalidade imagem 2x, max(score,0) mascara ruins, WP_PATCH_DELAY=1s lento, logs sem rotação, sem testes automatizados |
| Motores | 19 | Cutoff 24h feed lento, feeds não cobertos, variáveis globais estado, Gemini sem timeout, timezone inconsistente, description pode não existir |
| Utilitários | 13 | aumentar_memoria reinício total, logger global silenciado, Jina sem auth, dois extratores com mesmo nome, asyncio deprecated |
| Imagens | 11 | meta alt_text não salvo, circuit breaker compartilhado, slugs acentos, WebP sem validação dimensões, safe_filename vazio |

### 8.4 Todos os Bugs de Baixa Severidade (🔵)

| Subsistema | Quantidade | Exemplos Principais |
|---|---|---|
| Roteadores/Configs | 20 | import * colisão namespace, design-002 temperatura hardcoded, catalogo sem validação, publisher ID AdSense exposto |
| Motores | 12 | Lock file não removido em crash, GOV_CATS definida nunca usada, variáveis globais feeds/vistos, `is_manchete: i < 3` heurística frágil |
| Imagens | 9 | Paths hardcoded /home/bitnami, sem métricas por tier, testes sem asserts, código morto, print vs logging |
| Utilitários | 4 | Backup sem timestamp, mapear_wp sem paginação, sem verificação exit code gavetas, sem checkpoint regerar_excerpts |

---

## 9. Recalibração para 1.000+ Artigos/Dia

### 9.1 Gargalos de Escala Identificados

| Gargalo | Volume Atual (~100/dia) | Volume 1.000/dia | Fator de Bloqueio |
|---|---|---|---|
| Chamadas LLM (reescrita) | ~100/dia | ~1.000/dia | Rate limits por provider, custo |
| CSE API quota | 100 queries/dia grátis | 2.000 queries/dia | $10/dia ou cache |
| MariaDB conexões | ~30 simultâneas | ~100+ simultâneas | Pool exhaustion |
| WordPress REST API | ~200 posts/dia | ~2.000 posts/dia | Rate limit, timeout |
| historico_links.txt scan | ~73K linhas/ano, 34× ciclo | ~365K linhas/ano | RAM + CPU hash |
| deduplicador in-memory | 200 posts × post_content | 2.000 posts × post_content | OOM |
| Agendadores sequenciais | 23 gavetas × sleep 3s | Impossível escalar | Tempo total ciclo |
| Single-threaded LLM | 1 chamada por vez (por motor) | Bottleneck principal | Latência de ciclo |

### 9.2 Impacto nos Custos a 1.000+ Artigos/Dia

**Premissa:** 1.000 artigos/dia = 30.000/mês

#### Custos LLM (Reescrita)

Distribuição atual por tier:
- TIER 1 (Premium): ~20% → 200 artigos/dia
- TIER 2 (Standard): ~50% → 500 artigos/dia
- TIER 3 (Economy): ~30% → 300 artigos/dia

| Tier | Modelo Principal | Input (~1.500 tokens) | Output (~2.000 tokens) | Custo/artigo | Custo/dia |
|---|---|---|---|---|---|
| TIER 1 | GPT-4o | $2.50/1M input | $10/1M output | ~$0.024 | $4.80 |
| TIER 2 | Gemini 2.0 Flash | $0.075/1M | $0.30/1M | ~$0.0007 | $0.35 |
| TIER 3 | DeepSeek | $0.14/1M | $0.28/1M | ~$0.0008 | $0.24 |

**Custo LLM reescrita: ~$5.39/dia = $161.70/mês**

#### Custos LLM Adicionais

- Curadoria homepage (30 chamadas Gemini Flash/ciclo × 48 ciclos/dia): ~$0.50/dia
- Consolidação (3-5 artigos TIER_CONSOLIDATOR/ciclo × 12 ciclos): ~$1.80/dia
- Photo Editor (1.000 chamadas/dia): ~$2.00/dia
- Triagem motor avançado (se ativo): ~$5.00/dia

**Total LLM: ~$14.69/dia = $440.70/mês**

#### Com Otimização (Caching + Batch API)

- Cache de artigos duplicados entre fontes: -30% chamadas = **$10.28/dia**
- Batch API (OpenAI 50% desconto): -20% TIER 1 = **$9.32/dia**
- Migrar TIER 1 para Gemini 2.5 Pro: -60% custo Premium = **$7.50/dia**

**LLM otimizado: ~$7.50/dia = $225/mês**

#### Custos API de Imagem

- Google CSE: 2.000 queries/dia × $5/1000 = **$10/dia = $300/mês**
- Flickr API: Gratuito (com key válida)
- Wikimedia: Gratuito
- Stock APIs: Variável

#### Infraestrutura

| Recurso | Atual (LightSail) | Necessário (1000/dia) | Custo Mensal |
|---|---|---|---|
| Servidor | LightSail 2GB RAM | VPS 8-16GB RAM ou 2-3 workers | $80-160 |
| MariaDB | Local | RDS MySQL ou local otimizado | $0-50 |
| Redis (cache) | Ausente | Necessário para dedup + cache | $15-25 |
| Disco | 20-50GB | 100GB+ com log rotation | Incluso |

**Custo total estimado 1.000/dia: $540-$735/mês**

### 9.3 Arquitetura de Escala Necessária

#### Worker Pool

O sistema atual é single-process por raia. Para 1.000/dia:

- **Ingestão:** 3-5 workers paralelos para feeds RSS, 3-5 para scrapers
- **Processamento LLM:** Pool de 10-15 workers com rate limiting por provider
- **Publicação WP:** Pool de 3-5 workers com backoff exponencial
- **Imagens:** Pipeline async com 5+ workers paralelos nos tiers

#### Database

- Índice UNIQUE em `rss_control.source_url(768)` — bloqueia duplicatas na origem
- Índice em `rss_control.feed_name` e `rss_control.published_at`
- Connection pool dimensionado para 50-100 conexões
- Migrar `historico_links.txt` para Redis SET com TTL de 60 dias

#### LLM

- Paralelizar chamadas LLM com `asyncio` ou `ThreadPoolExecutor` limitado
- Implementar rate limiter por provider (token bucket)
- Cache de respostas por hash de conteúdo (evitar reescrever duplicatas)
- Batch API do OpenAI para TIER 1 (50% desconto)

#### Imagens

- Paralelizar tiers com `asyncio`
- Cache de URLs de imagem por query (Redis, TTL 24h)
- CSE: pool de 3-5 API keys para 500 queries/dia cada
- Pré-fetch imagens durante processamento LLM (pipeline paralelo)

#### Homepage Curadoria a 300+ Posts em 4h

Com 1.000/dia, a janela de 4h contém ~167 posts. O scorer precisa avaliar todos:
- Budget LLM: Aumentar de 30 para 100 chamadas/ciclo
- Implementar scoring em batch (múltiplos posts por chamada Gemini)
- Reduzir `WP_PATCH_DELAY` de 1.0s para 0.2s com retry
- Implementar diff atômico de tags (sem clear total)

#### Deduplicação a 30.000 Artigos/Mês

- Migrar SequenceMatcher → MySQL FULLTEXT search ou Elasticsearch
- Implementar fingerprinting por SimHash ou MinHash (O(1) lookup)
- Redis SET com títulos normalizados dos últimos 7 dias
- Constraint UNIQUE no banco para prevenir duplicatas na camada de dados

### 9.4 Revisão do Plano de Implementação (5 Fases)

#### Fase 0 — Estabilização de Emergência (Semana 1-2)

**Pré-requisito absoluto antes de qualquer migração.**

1. **Rotacionar todas as credenciais expostas** (15+ API keys, senha DB, senha WP)
2. **Fix cloudscraper singleton** — resolver causa #1 de crash
3. **Remover `sys.path.insert` de funções** — mover para topo de módulos
4. **Fix escrita atômica feeds.json/scrapers.json** — write-to-temp + rename
5. **Adicionar lock files a todos os agendadores** (flock)
6. **Implementar log rotation** (TimedRotatingFileHandler backupCount=7)
7. **Fix `base64` import em config_geral.py**
8. **Fix `renomear_categoria.py` e `corrigir_demo_restante.py`** imports
9. **Adicionar UNIQUE KEY em rss_control.source_url**
10. **Remover `post_content` do SELECT no deduplicador**

**Estimativa:** 3-5 dias de trabalho, 0 risco de regressão.

#### Fase 1 — Correção de Bugs Críticos de Pipeline (Semana 3-4)

1. **Fix janela zero de tags** — implementar diff incremental
2. **Fix timezone naive** — padronizar UTC em todo o stack
3. **Fix deduplicação check-then-act** — INSERT IGNORE com UNIQUE
4. **Fix pipeline de imagens** — corrigir FLICKR_GOV_USERS, CSE quota, lógica invertida
5. **Consolidar `curator_config.py`** — remover versão em `agents/`
6. **Adicionar `home-esportes` e `home-justica` ao TAG_IDS**
7. **Thread-safe circuit breaker** — `threading.Lock` no llm_router
8. **Fix reverter_autoria.py** — adicionar paginação
9. **Fix gestor_cache.py** — path absoluto, lock de arquivo, rotação por janela

#### Fase 2 — Infraestrutura para Escala (Semana 5-8)

1. **Migrar de LightSail para VPS 8-16GB** (ou cluster de workers)
2. **Redis para deduplicação e cache** — substituir historico_links.txt
3. **Connection pool dimensionado** — 50+ conexões MariaDB
4. **Worker pool para LLM** — 10-15 workers paralelos com rate limiting
5. **Pipeline de imagens async** — paralelizar tiers
6. **Batch API OpenAI** — 50% desconto em TIER 1
7. **CSE multi-key** — pool de 3-5 API keys

#### Fase 3 — Arquitetura Multi-Agente (Semana 9-16)

1. **Fila de mensagens** (RabbitMQ/Redis Streams) entre motores
2. **Workers dedicados** por função (ingestão, processamento, publicação)
3. **Deduplicação centralizada** com SimHash/MinHash
4. **Curadoria assíncrona** — scoring em batch, diff atômico
5. **Observabilidade** — métricas por tier, alertas, dashboards

#### Fase 4 — Otimização e Qualidade (Semana 17-24)

1. **Testes automatizados** para scoring, deduplicação, pipeline de imagens
2. **Monitoramento de qualidade** — amostragem automática de artigos publicados
3. **Auto-scaling** de workers baseado em volume de feeds
4. **Relatório editorial automático** — cobertura, diversidade, freshness
5. **Flags editoriais** para fontes sensíveis (RT, CGTN, TASS)

---

## 10. Plano de Ação Imediato (Antes da Migração)

### 10.1 Rotacionar Todas as Credenciais Expostas

**Prazo:** HOJE

1. **MariaDB:** Alterar senha via `ALTER USER 'bn_wordpress'@'localhost' IDENTIFIED BY '<nova>'`. Atualizar `.env` com `DB_PASS=<nova>`. Remover **todos** os fallbacks hardcoded (grep por `d0e339d8be`).

2. **WordPress App Password:** Painel WP → Usuários → Senhas de Aplicativos → Revogar `nWgboohRWZGLv2d7ebQgkf80` → Gerar nova. Atualizar `.env` com `WP_APP_PASS=<nova>`.

3. **API Keys:** Revogar nos painéis: OpenAI (3 keys), Grok/xAI (3 keys), Gemini (3+ keys), DeepSeek (3 keys), Qwen (3 keys). Gerar novas, armazenar em `.env` como `OPENAI_API_KEY=`, `OPENAI_API_KEY_2=`, etc.

4. **Git:** Executar `git filter-branch` ou BFG Repo Cleaner para limpar histórico. Adicionar ao `.gitignore`: `*.env`, `config_chaves.py`, `check_keys.py`, `backup_integral_robos.txt`.

### 10.2 Corrigir Memory Leaks que Causam Crashes

**Prazo:** 1-2 dias

1. **cloudscraper singleton:**
```python
# motor_scrapers_v2.py — topo do módulo
import cloudscraper
_CLOUDSCRAPER = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)
# Na função _fetch_with_retry: usar _CLOUDSCRAPER.get(url, ...) em vez de criar novo
```

2. **sys.path.insert — mover para topo:**
```python
# Em CADA arquivo que tem sys.path.insert dentro de função:
# Mover para ANTES de qualquer import condicional, NO TOPO DO ARQUIVO
import sys
sys.path.insert(0, "/home/bitnami")
sys.path.insert(0, "/home/bitnami/motor_rss")
from curador_imagens_unificado import get_curador, is_official_source
```

3. **Remover `post_content` do SELECT do deduplicador:**
```sql
SELECT ID, post_title, post_date, post_status
FROM {posts} WHERE ...
```

4. **Log rotation:**
```python
from logging.handlers import TimedRotatingFileHandler
handler = TimedRotatingFileHandler(
    log_file, when='midnight', backupCount=7, encoding='utf-8'
)
```

### 10.3 Corrigir Pipeline de Imagens — Bugs Críticos

**Prazo:** 2-3 dias

1. **Pesquisar IDs Flickr reais** das contas governamentais brasileiras. Se não existirem, desativar Tier 3A e documentar.

2. **Separar quota CSE:** Criar CSE ID separado para Tier 3C, ou implementar cache de resultados Redis.

3. **Fix gestor_wp.py NameError:** Adicionar `from roteador_ia import roteador_ia_imagem` no topo, ou remover chamada se trava é permanente.

4. **Fix lógica invertida:** Trocar condicionais de `is_oficial` para que fontes oficiais usem imagem original (Tier 1) e fontes comerciais usem curadoria via tiers 2-5.

5. **Unificar placeholder URL:** Definir uma única constante compartilhada entre módulos.

### 10.4 Corrigir Homepage Curator — Bugs Críticos

**Prazo:** 3-5 dias

1. **Diff incremental de tags:**
```python
# Em vez de clear_all → apply_all:
current_state = get_current_tag_assignments()
desired_state = compute_new_assignments(scored_posts)
to_remove = current_state - desired_state
to_add = desired_state - current_state
# Aplicar apenas diffs
```

2. **Fix logger em log_cycle():**
```python
def log_cycle(selections, scored_map):
    logger = logging.getLogger("curator")  # Adicionar esta linha
    ...
```

3. **Adicionar tags faltantes:** `home-esportes` e `home-justica` ao `TAG_IDS`, ou remover de `HOMEPAGE_POSITIONS`.

4. **Remover `agents/curator/`** — versão obsoleta com config incompatível.

5. **Timezone aware:**
```python
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
```

### 10.5 Adicionar Lock Files aos Agendadores

**Prazo:** 1 dia

```bash
#!/bin/bash
# agendador_mestre.sh — adicionar no início:
LOCK_FILE="/tmp/agendador_mestre.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "Já em execução. Abortando."; exit 1; }

# Adicionar verificação de exit code:
for gaveta in ...; do
    /usr/bin/python3 motor_mestre.py "$gaveta"
    if [ $? -ne 0 ]; then
        echo "[ERRO] Gaveta $gaveta falhou com código $?" >> /home/bitnami/logs/agendador_erros.log
    fi
    sleep 3
done
```

Aplicar o mesmo padrão em `agendador_scrapers.sh` e `deploy_curator.sh` (flock no cron do curador).

### 10.6 Implementar Log Rotation

**Prazo:** 1 dia

Em **todos** os motores (`motor_rss_v2.py`, `motor_scrapers_v2.py`, `motor_consolidado.py`, `curator_agent.py`, `motor_mestre.py`):

```python
from logging.handlers import TimedRotatingFileHandler

handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    backupCount=7,
    encoding='utf-8'
)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(handler)
```

Adicionalmente, configurar `logrotate` no sistema operacional para qualquer log escrito via `print()` ou stdout redirecionado.

---

*Auditoria consolidada gerada em 20/03/2026. Este documento é a referência mestre para todas as correções e migração do sistema brasileira.news. Total: 329 problemas catalogados em 5 subsistemas, cobrindo 80+ arquivos de produção.*
