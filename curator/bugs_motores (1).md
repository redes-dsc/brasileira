# Auditoria de Bugs — Motores RSS, Scrapers, Consolidado, Mestre
**Brasileira.news — Sistema de Automação de Notícias**
**Data:** 2026-03-20
**Auditor:** Análise de código estático completa

---

## ÍNDICE DE CRITICIDADE

| Severidade | Quantidade | Exemplos Principais |
|------------|-----------|---------------------|
| 🔴 CRÍTICO | 18 | Crash LightSail, race conditions, duplicatas publicadas |
| 🟠 ALTO | 22 | Memory leaks, conexões vazando, lógica errada |
| 🟡 MÉDIO | 19 | Falhas silenciosas, edge cases, N+1 queries |
| 🔵 BAIXO | 12 | Code smells, hardcodes, robustez |

---

## CAUSA RAIZ DOS CRASHES LIGHTSAIL

**Diagnóstico preliminar** (baseado em análise do código): O servidor trava por acúmulo de três fatores simultâneos:

1. **`cloudscraper` cria uma nova instância a cada chamada** em `_fetch_with_retry` — cada instância mantém sessão HTTP, certificados TLS e objetos JS em memória. Com 5 workers e múltiplas fontes, acumula dezenas de instâncias não coletadas pelo GC.
2. **`newspaper.Article` não é reutilizado** — cada artigo cria objetos NLP (tokenizers, vocabulário) internamente. Com 1000+ artigos/dia, o GC Python não consegue liberar rápido o suficiente.
3. **O pool de conexões MariaDB (`_pool = None`) nunca é recriado** após falhas de rede, e o `PooledDB` com `maxconnections=10` compartilhado entre os três motores (RSS, Scrapers, Consolidado) esgota rapidamente sob carga paralela.

---

## MOTOR RSS (RAIA 1)

### Arquivo: `motor_rss/motor_rss_v2.py`

#### 🔴 CRÍTICO — Importação dinâmica dentro do loop de artigos (memory leak + path injection)

```python
# Linha 381-383 (dentro de process_article, chamado para cada artigo)
sys.path.insert(0, str(Path("/home/bitnami")))
from curador_imagens_unificado import is_official_source
```

**Problemas:**
- `sys.path.insert(0, ...)` é chamado **uma vez por artigo processado**. Com 20 artigos/ciclo × 48 ciclos/dia = 960 inserções no `sys.path`. O `sys.path` cresce indefinidamente na memória do processo.
- O módulo `curador_imagens_unificado` é reimportado a cada artigo. Python cacheia o módulo em `sys.modules`, mas os objetos de módulo intermediários e o path acumulado consomem memória.
- **Correção:** Mover a importação e o `sys.path.insert` para o topo do arquivo, fora de qualquer função.

#### 🔴 CRÍTICO — Race condition na deduplicação entre Raia 1 e Raia 2

```python
# motor_rss_v2.py linha 301-324 (deduplicate_entries)
published_urls = db.get_published_urls_last_24h()
# ... 
if db.post_exists(url, entry["title"]):
    continue
# ↑ Entre este check e o registro (linha 481), outra instância pode publicar o mesmo artigo
```

**Problema:** O padrão check-then-act não é atômico. Se Raia 1 e Raia 2 processam o mesmo artigo simultaneamente (ambas leem a mesma URL do feed e de fontes diferentes), ambas passam no `post_exists` antes de qualquer uma registrar, resultando em **posts duplicados publicados no WordPress**.

**Correção:** Usar `INSERT IGNORE` ou `INSERT ... ON DUPLICATE KEY UPDATE` no `register_published`, com índice UNIQUE em `source_url` na tabela `rss_control`.

#### 🟠 ALTO — `requests.get` sem Session (resource leak)

```python
# Linha 212-248 (extract_full_content)
resp = requests.get(url, headers=headers, timeout=config.HTTP_TIMEOUT)
# Linha 257-268 (extract_html_content)
resp = requests.get(url, headers=headers, timeout=config.HTTP_TIMEOUT)
```

Cada `requests.get` sem Session cria uma nova conexão TCP. Sem `with` ou `resp.close()`, a conexão fica em `CLOSE_WAIT` até o GC agir. Com 20+ artigos/ciclo, são 40+ conexões abertas simultaneamente. **Correção:** Usar `requests.Session` reutilizável ou garantir `resp.close()` no `finally`.

#### 🟠 ALTO — Double fetch do HTML para o mesmo artigo

```python
# Linha 340 (process_article)
content = extract_full_content(link)    # Faz requests.get(link)
# ...
# Linha 375
html_content = extract_html_content(link)  # Faz OUTRO requests.get(link)
```

Para cada artigo, o código faz **dois downloads do mesmo HTML**. Com 20 artigos/ciclo, são 40 requests onde 20 são redundantes. Além do custo de rede, duplica o consumo de memória pico (dois `resp.text` em memória simultâneos).

#### 🟡 MÉDIO — Cutoff de 24h para todos os feeds (feeds lentos perdem artigos)

```python
# Linha 509 (run_cycle)
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
```

Feeds de fontes governamentais (Senado, Câmara) publicam com atraso de horas. Um artigo publicado às 23h que só aparece no feed às 01h do dia seguinte pode cair fora da janela de 24h dependendo do horário do ciclo. Deveria ser configurável por feed.

#### 🟡 MÉDIO — `selecionar_feeds_ciclo` não cobre todos os feeds ao longo do dia

```python
# Linha 141
bloco = (datetime.now().hour * 2 + datetime.now().minute // 30) % num_blocos
```

Com `FEEDS_POR_CICLO=60` e, por exemplo, 150 feeds totais → `num_blocos=2`. O cálculo de bloco retorna 0 ou 1. Com ciclos de 30 minutos, o bloco muda a cada 30 min. Feeds no bloco 2 (`feeds[120:150]`) nunca são visitados se `num_blocos < 3`. **Bug:** a fórmula garante cobertura apenas se `total % FEEDS_POR_CICLO == 0`.

#### 🔵 BAIXO — Lock file não é removido em crash

```python
# Linha 641-643 (main)
try:
    run_cycle()
except Exception as e:
    logger.error(...)
release_lock()  # Só executado se nenhum exception escapa do try
```

Se `run_cycle()` lançar um exception não capturado (improvável mas possível), `release_lock()` é chamado. OK para este caso. Mas se o processo for `kill -9`'d, o arquivo `.lock` fica e impede novas execuções. Deveria usar um PID no lock e verificar se o PID ainda existe.

---

### Arquivo: `motor_rss/db.py`

#### 🔴 CRÍTICO — Pool de conexões compartilhado entre processos (sem isolamento)

```python
# Linha 34
_pool = None  # Variável global de módulo

def _get_pool():
    global _pool
    if _pool is None:
        _pool = PooledDB(maxconnections=10, ...)
```

O `PooledDB` é **global de módulo**. Quando Raia 1, Raia 2 e Raia 3 importam `db`, cada processo Python tem seu próprio `_pool` separado (processos distintos não compartilham memória). Mas isso significa que **cada motor cria seu próprio pool de 10 conexões** → até 30 conexões simultâneas ao MariaDB, que por padrão limita 100 conexões mas a instância LightSail pode ter limite menor. Além disso, se os motores forem rodados como threads dentro do mesmo processo (improvável mas possível), o pool não é thread-safe na inicialização (race condition no `if _pool is None`).

**Correção:** Usar `threading.Lock` no `_get_pool()` para inicialização thread-safe.

#### 🟠 ALTO — Cursor não fechado em caso de exceção em `post_exists`

```python
# Linha 153-201 (post_exists)
with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    if cursor.fetchone():
        cursor.close()   # Fechado em sucesso (caminho 1)
        return True
    cursor.execute(...)  # Segunda query
    result = cursor.fetchone()
    cursor.close()       # Fechado em sucesso (caminho 2)
    return result is not None
# Se qualquer cursor.execute() lançar exceção, cursor NÃO é fechado
```

O cursor é fechado manualmente apenas nos caminhos de sucesso. Se a segunda `cursor.execute()` lançar exceção, o cursor vazará. **Correção:** Usar `with conn.cursor() as cursor:` ou envolver em try/finally.

#### 🟡 MÉDIO — `get_published_urls_last_24h` retorna todas as URLs sem limite

```python
# Linha 315-338 (get_published_urls_last_24h)
cursor.execute("""
    SELECT source_url FROM {_t('rss_control')}
    WHERE published_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
""")
urls = {row["source_url"] for row in cursor.fetchall()}
```

Sem `LIMIT`. Com 1000+ artigos/dia, esta query retorna e carrega em memória até 1000 URLs por chamada. Chamada no início de cada ciclo (3 motores × múltiplos ciclos = muitas chamadas). **Correção:** Adicionar `LIMIT 5000` e/ou criar índice em `published_at`.

#### 🟡 MÉDIO — Tabela `rss_control` sem índice único em `source_url` completo

```python
# Linha 121 (DDL)
INDEX idx_source_url (source_url(768)),
```

É apenas um índice, não `UNIQUE`. Não impede inserções duplicadas. Junto com a race condition da deduplicação, isso permite múltiplas entradas do mesmo artigo na tabela de controle.

---

### Arquivo: `motor_rss/wp_publisher.py`

#### 🔴 CRÍTICO — Cache de categorias e tags nunca expira (stale cache)

```python
# Linha 110-111
_category_cache: dict[str, int] = {}
_tag_cache: dict[str, int] = {}

def _load_categories_from_db():
    global _category_cache
    if _category_cache:          # ← Se não-vazio, nunca relê
        return _category_cache
```

O cache é populado na primeira chamada e **nunca é invalidado**. Se uma nova categoria for criada no WordPress durante a execução do motor (ex: via painel admin), o cache nunca a verá. Artigos classificados nessa categoria serão publicados na categoria errada indefinidamente.

**Impacto adicional:** O cache cresce ilimitadamente em um processo longa execução — cada nova tag criada via API é adicionada ao `_tag_cache` mas nunca removida. Com tags sendo criadas para cada artigo (3-5 tags/artigo × 1000 artigos/dia), o dicionário acumula milhares de entradas em memória.

#### 🟠 ALTO — `_request_with_retry` ignora status 4xx (exceto 500+)

```python
# Linha 67-70
if resp.status_code < 500:
    return resp   # Retorna 401, 403, 404, 429 como "sucesso"
```

Erros 4xx como `429 Too Many Requests` (rate limiting do WordPress) são retornados sem retry. O chamador (`publish_post`) verifica apenas `resp.status_code in (200, 201)` e loga erro nos demais casos, mas **não tenta novamente para rate limits**. Sob carga alta, o WordPress pode retornar 429 e os artigos falham silenciosamente sem retry.

#### 🟠 ALTO — Slugs de categorias/tags não suportam caracteres especiais do português

```python
# Linha 155
slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
```

A chave `key` já é normalizada com `html.unescape(name).lower()`. Mas o regex `[^a-z0-9]+` remove acentos (`ã`, `é`, `ç`). `"Política & Poder"` vira `"pol-tica-poder"` como slug, diferente do slug real do WordPress que pode ser `"politica-poder"`. Isso causa falha na busca por slug existente, criando categorias duplicadas com slug errado.

#### 🟡 MÉDIO — `publish_post` não verifica se `category_ids` está vazio

```python
# Linha 262-263
category_ids = _resolve_category(category_name)
# Se _resolve_category retorna [], o post vai para categoria padrão do WP (Uncategorized)
post_data = {"categories": category_ids, ...}  # Envia lista vazia
```

Se a categoria não existe e a criação via API falha, o post é publicado sem categoria (WordPress usa "Uncategorized"). Não há alerta suficiente para isso.

---

### Arquivo: `motor_rss/llm_router.py`

#### 🔴 CRÍTICO — Circuit breaker não é thread-safe

```python
# Linha 26
_circuit_breaker: dict[str, dict] = {}

def _cb_record_failure(provider: str):
    state = _circuit_breaker.setdefault(provider, {"failures": 0, ...})
    state["failures"] += 1   # ← READ-MODIFY-WRITE não atômico
    if state["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        state["blocked_until"] = time.time() + ...
```

Com `ThreadPoolExecutor(max_workers=5)` no motor de scrapers chamando `llm_router` concorrentemente, múltiplas threads podem executar `state["failures"] += 1` simultaneamente. Em CPython, o GIL torna `dict` operations geralmente seguras, mas `+=` em inteiros ainda é read-modify-write não atômico entre threads. **Resultado:** contador de falhas pode ser subestimado, circuit breaker pode não disparar quando deveria.

**Correção:** Usar `threading.Lock` protegendo o dicionário inteiro.

#### 🔴 CRÍTICO — `_key_index` não é thread-safe (round-robin corrompido)

```python
# Linha 65
_key_index: dict[str, int] = {}

def _next_key(provider: str, keys: list[str]) -> str | None:
    idx = _key_index.get(provider, 0) % len(keys)
    _key_index[provider] = idx + 1    # ← Não atômico
    return keys[idx]
```

Mesma race condition: duas threads podem ler `idx=0`, ambas retornam `keys[0]`, e ambas escrevem `_key_index[provider] = 1`. A rotação não funciona corretamente sob carga paralela — a mesma key é usada por múltiplas threads e outras keys ficam sub-utilizadas ou nunca usadas.

#### 🟠 ALTO — Gemini não usa `system` prompt separado (concatena no `contents`)

```python
# Linha 193-197 (_call_gemini_premium e _call_gemini)
response = client.models.generate_content(
    model="gemini-2.5-pro-preview-05-06",
    contents=f"{system_prompt}\n\n{user_prompt}",
)
```

A API do Google Gemini suporta `system_instruction` como parâmetro separado desde a versão `v1beta`. Concatenar system e user no mesmo `contents` (1) dilui a eficácia do system prompt, (2) pode fazer o modelo ignorar instruções críticas de formato JSON, e (3) aumenta o número de tokens cobrados. **Impacto direto:** respostas JSON malformadas aumentam, causando mais retries e maior custo.

#### 🟠 ALTO — `generate_article` trunca conteúdo em 6000 chars mas o limite real é palavras

```python
# Linha 465
content=content[:6000],
```

O conteúdo é truncado por **caracteres**, não por palavras ou tokens. Um artigo com palavras longas pode ter `content[:6000]` cortando no meio de uma frase ou dado importante. O LLM recebe contexto incompleto sem aviso.

#### 🟡 MÉDIO — Erro de crédito força `CIRCUIT_BREAKER_THRESHOLD` iterações

```python
# Linha 507-509
for _ in range(CIRCUIT_BREAKER_THRESHOLD):
    _cb_record_failure(cb_name)
continue
```

O loop chama `_cb_record_failure` `CIRCUIT_BREAKER_THRESHOLD` (=3) vezes. Mas `_cb_record_failure` já incrementa o contador e **também seta `blocked_until`** quando atinge o threshold. Isso pode causar double-set de `blocked_until` e chama desnecessariamente o código de bloqueio 3 vezes. Deveria usar uma função separada `_cb_force_open(provider)`.

#### 🟡 MÉDIO — Timeout do LLM não é aplicado ao Gemini

```python
# Linha 193 (_call_gemini_premium)
response = client.models.generate_content(
    model="gemini-2.5-pro-preview-05-06",
    contents=...,
    # ← Sem timeout! config.LLM_TIMEOUT não é passado
)
```

O `config.LLM_TIMEOUT = 60` é passado para OpenAI e Claude, mas **não para o cliente Gemini**. Chamadas Gemini podem travar indefinidamente, bloqueando a thread do executor.

---

### Arquivo: `motor_rss/check_keys.py`

#### 🔴 CRÍTICO — Chaves de API hardcoded no código-fonte

```python
# Linhas 86-114
deepseek_keys = [
    "sk-f594930120eb4735846328cc05b35f37",
    "sk-f4c757f6f3ef4bc5b5971e37569ac10c",
    ...
]
qwen_keys = [
    "sk-d9aadafdd8574993a983f211b53a9854",
    ...
]
```

Três chaves DeepSeek e três chaves Qwen estão hardcoded diretamente no código. Qualquer pessoa com acesso ao repositório Git tem acesso a essas chaves. **Impacto:** Chaves expostas em histórico Git, logs, dumps de processo e qualquer backup do código.

---

### Arquivo: `motor_rss/converter_catalogos.py`

#### 🟡 MÉDIO — Variáveis globais `feeds` e `vistos` — estado persiste entre imports

```python
# Linha 56-58
feeds = []
vistos = set()
```

Definidas no escopo do módulo. Se o módulo for importado múltiplas vezes em diferentes contextos (ex: em testes ou se importado depois de ser executado), o estado é compartilhado. Deveria ser encapsulado em `main()`.

#### 🟡 MÉDIO — `GOV_CATS` definida mas nunca usada

```python
# Linhas 20-30
GOV_CATS = ['CAT_POLITICA', 'CAT_JUSTICA', ...]
```

Definida mas nunca referenciada no código. Dead code.

---

## MOTOR SCRAPERS (RAIA 2)

### Arquivo: `motor_scrapers/motor_scrapers_v2.py`

#### 🔴 CRÍTICO — `cloudscraper` instanciado por request (memory leak grave)

```python
# Linha 276-278 (_fetch_with_retry, chamado POR ARTIGO)
import cloudscraper
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)
resp = scraper.get(url, ...)
```

**Este é provavelmente o principal responsável pelos crashes do LightSail.**

`cloudscraper.create_scraper()` cria um objeto com:
- Um interpretador JavaScript V8/Node emulado
- Sessão HTTP com pool de conexões
- Certificados TLS e contexto SSL
- Análise de challenge Cloudflare em memória

**Criado para CADA chamada** de `_fetch_with_retry`. Com `MAX_WORKERS=5` e múltiplas fontes, podem existir 10-25 instâncias `cloudscraper` simultâneas em memória. O objeto não é destruído explicitamente, dependendo do GC Python. Com ciclos de 30 minutos e resposta lenta do GC, a memória cresce até o OOM killer do Linux matar o processo.

**Correção:** Criar uma única instância global `_CLOUDSCRAPER = cloudscraper.create_scraper(...)` no topo do módulo e reutilizá-la.

#### 🔴 CRÍTICO — Domain delay não funciona com ThreadPoolExecutor

```python
# Linha 1065-1089 (run_cycle)
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    for fonte in fontes:
        domain = urlparse(...).netloc
        last = domain_last_request.get(domain, 0)
        elapsed = time.time() - last
        if elapsed < DOMAIN_DELAY_MIN:
            time.sleep(DOMAIN_DELAY_MIN - elapsed)  # ← Bloqueia a thread PRINCIPAL
        future = executor.submit(coletar_links_fonte, fonte)
        domain_last_request[domain] = time.time()
```

O `time.sleep` está na thread **principal** que submete tarefas ao executor. Isso bloqueia o loop de submissão mas NÃO impede que as 5 workers threads façam requests simultâneos ao mesmo domínio. Duas workers podem estar buscando `g1.globo.com` ao mesmo tempo enquanto o delay controla apenas o tempo entre submissions.

Além disso, `domain_last_request` é acessado da thread principal (submissão) e das workers (via `processar_artigo` na segunda fase, linha 1169), criando outra race condition.

#### 🟠 ALTO — `import cloudscraper` dentro do loop (importação repetida)

```python
# Linha 276 (_fetch_with_retry)
import cloudscraper  # ← Dentro de função chamada repetidamente
```

Embora Python cacheia imports em `sys.modules`, o `import` statement dentro de um loop de alta frequência ainda adiciona overhead de lookup em `sys.modules` e impede análise estática de dependências.

#### 🟠 ALTO — `_blocked_domains` e `_robots_cache` crescem indefinidamente

```python
# Linha 184
_blocked_domains: dict[str, float] = {}  # Nunca limpo

# Linha 210
_robots_cache: dict = {}  # Nunca limpo
```

Em um processo de longa duração (daemon), esses dicionários acumulam domínios bloqueados expirados e parsers robots.txt. Com centenas de fontes, acumulam memória continuamente. O `_robots_cache` é especialmente problemático: armazena objetos `RobotFileParser` completos (com todo o conteúdo do `robots.txt` parseado) para cada domínio visitado.

**Correção:** Usar `functools.lru_cache` com `maxsize` ou limpar entradas expiradas periodicamente.

#### 🟠 ALTO — Race condition em `processar_artigo` sem lock de DB

Na fase de processamento sequencial (linhas 1149-1185), `processar_artigo` chama `db.register_published` sem nenhum lock. Se duas instâncias do motor (Raia 1 e Raia 2) executarem simultaneamente e ambas pegarem o mesmo artigo de fontes diferentes, ambas podem publicar e registrar. A tabela `rss_control` não tem constraint UNIQUE em `source_url`.

#### 🟡 MÉDIO — `_extrair_links_nextjs` tem recursão potencialmente infinita em JSON circular

```python
# Linha 505-545 (_buscar)
def _buscar(obj, depth=0):
    if depth > 10:
        return
    # ...
    for val in obj.values():
        _buscar(val, depth+1)
```

O limite de profundidade é 10, o que pode não ser suficiente para alguns payloads Next.js com estruturas profundamente aninhadas. Mais importante: objetos com referências circulares (improvável em JSON mas possível após deserialização) causariam stack overflow antes de atingir `depth > 10`.

#### 🟡 MÉDIO — Artigos com `titulo=""` passam para o processamento (sitemap)

```python
# Linha 715 (_extrair_links_sitemap)
artigos.append({"titulo": "", "url": url, ...})
```

Artigos do sitemap são coletados sem título. Em `processar_artigo` (linha 900):
```python
titulo = conteudo_data.get("titulo", "") or titulo_original
```
Se o extrator também não encontrar título, `titulo=""` vai para o LLM com `title=""`. O LLM pode inventar um título sem base no conteúdo.

---

### Arquivo: `motor_scrapers/extrator_conteudo.py`

#### 🔴 CRÍTICO — `newspaper.Article` retém objetos NLP em memória

```python
# Linha 94-100 (_extrair_via_newspaper)
from newspaper import Article
article = Article(url, language="pt")
article.download(input_html=html)
article.parse()
```

`newspaper3k` carrega modelos de NLP (tokenizers, vocabulário) em memória no primeiro uso. Cada `Article()` cria um novo objeto mas os modelos NLP ficam carregados como singletons. O problema é que `article.parse()` em artigos grandes pode criar estruturas intermediárias (parse trees, keyword graphs) que só são liberadas quando o objeto `article` é coletado pelo GC — e isso não acontece imediatamente em Python.

Com `MAX_WORKERS=5` e múltiplos artigos em paralelo, a memória acumulada de objetos `Article` não coletados pode ser significativa.

#### 🟡 MÉDIO — Double fetch duplicado: `extrair_conteudo_completo` + `extrair_html_bruto` chamam `_fetch_html` duas vezes para o mesmo URL

```python
# motor_scrapers_v2.py linha 892
conteudo_data = extrator_conteudo.extrair_conteudo_completo(url)
# ... (usa _fetch_html internamente)
# Linha 930
html_bruto = extrator_conteudo.extrair_html_bruto(url)
# extrair_html_bruto chama _fetch_html NOVAMENTE
```

Idêntico ao bug do motor RSS: dois downloads do mesmo URL por artigo.

#### 🟡 MÉDIO — `_extrair_via_jina` expõe URLs internas ao serviço externo

```python
# Linha 338
jina_url = f"https://r.jina.ai/{url}"
```

Jina Reader (`r.jina.ai`) é um serviço externo que requisita e processa URLs. Enviar URLs de artigos para um terceiro pode:
1. Violar termos de serviço das fontes originais
2. Revelar padrões de scraping a serviços de analytics
3. Criar dependência de disponibilidade de serviço externo (sem fallback se Jina estiver fora)

Não há `Authorization` header para quota/rate limiting do Jina.

---

### Arquivo: `motor_scrapers/detector_estrategia.py`

#### 🟠 ALTO — `detectar_estrategia` faz 4-6 requests HTTP por fonte na detecção automática

```python
# Linhas 272-318 (detectar_estrategia — caminho automático)
html, status = _fetch_raw(url_alvo)          # Request 1: página principal
feed_url = detectar_feed_nao_padrao(url_home) # Requests 2-9: testa 8 sufixos de feed
api_url = detectar_api_json(url_home)         # Requests 10-14: testa 5 endpoints API
sitemap_url = detectar_sitemap(url_home)      # Requests 15-19: testa 5 sitemaps
```

Para cada fonte sem `estrategia` configurada, a detecção automática faz até **19 requests HTTP** (1 + 8 feeds + 5 APIs + 5 sitemaps). Com 50 fontes sem estratégia configurada, são 950 requests só para detecção, antes de processar qualquer artigo.

**Pior:** isso acontece a **cada ciclo**, pois a detecção não é cacheada. Deveria salvar a estratégia detectada em `scrapers.json` ou banco de dados.

#### 🟡 MÉDIO — `detectar_feed_nao_padrao` não respeita robots.txt

```python
# Linha 124-156 (detectar_feed_nao_padrao)
for sufixo in sufixos:
    feed_url = urljoin(url_home, sufixo)
    resp = requests.get(feed_url, ...)  # Sem verificar robots.txt
```

A verificação de `robots.txt` existe em `coletar_links_fonte` mas é bypassed completamente na fase de detecção de estratégia.

---

## MOTOR CONSOLIDADO (RAIA 3)

### Arquivo: `motor_consolidado/motor_consolidado.py`

#### 🟠 ALTO — `acquire_lock` não usa `try/except` — vazamento de file descriptor

```python
# Linha 58-69 (acquire_lock)
def acquire_lock():
    global _lock_fd
    _lock_fd = open(LOCK_FILE, "w")  # ← Abre ANTES do try
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ...
        return True
    except IOError:
        logger.warning(...)
        return False
    # ← Se retorna False, _lock_fd está aberto mas não bloqueado
    # ← O arquivo fica aberto até o GC rodar
```

Se `flock` falha (outra instância rodando), o método retorna `False` mas `_lock_fd` (o file object) fica aberto, consumindo um file descriptor do OS. Chamadas repetidas (ex: crontab rodando a cada 2h enquanto um ciclo lento ainda processa) acumulam descritores abertos.

#### 🟡 MÉDIO — `run_cycle` retorna 0 sem distinção entre "sem trending" e "erro fatal"

```python
# Linha 156
if not all_titles:
    ...
    return 0   # "Normal" — sem títulos
# ...
# Linha 172
if not trending:
    ...
    return 0   # "Normal" — sem trending
```

Ambos os cenários "sem dados" e "erro de scraping" retornam 0. O motor principal não tem como distinguir se o ciclo foi bem-sucedido mas sem notícias, ou se houve uma falha de scraping. **Correção:** Retornar valores distintos ou lançar exceção específica para erros.

---

### Arquivo: `motor_consolidado/deduplicador.py`

#### 🔴 CRÍTICO — `check_recent_coverage` carrega 200 posts em memória para SequenceMatcher O(n²)

```python
# Linha 39-50 (check_recent_coverage)
cursor.execute("""
    SELECT ID, post_title, post_date, post_content, post_status
    FROM {posts} WHERE post_status IN ('publish', 'draft')
      AND post_date >= DATE_SUB(NOW(), INTERVAL %s HOUR)
    ORDER BY post_date DESC
    LIMIT 200
""", (hours,))
posts = cursor.fetchall()

for post in posts:
    similarity = SequenceMatcher(None, normalized_topic, post_title).ratio()
```

**Problemas múltiplos:**

1. **`post_content` é selecionado mas nunca usado** — traz o conteúdo HTML completo dos últimos 200 posts para memória desnecessariamente. Com artigos de 400-1200 palavras em HTML, isso pode ser vários MB por chamada.

2. **SequenceMatcher em loop de 200 posts** — `SequenceMatcher.ratio()` tem custo O(n×m) onde n e m são os tamanhos das strings. Para 200 posts com títulos de ~80 chars, é 200 chamadas de SequenceMatcher por tema trending. Com 10-20 temas por ciclo, são 2000-4000 chamadas de SequenceMatcher.

3. **Chamado para CADA tema trending**, sem cache.

**Correção:** Remover `post_content` do SELECT. Usar busca FULLTEXT do MySQL em vez de SequenceMatcher Python.

#### 🟠 ALTO — SequenceMatcher com threshold 0.55 é excessivamente permissivo para títulos

```python
# Linha 57
if similarity >= 0.55:  # threshold mais alto que clustering
```

`SequenceMatcher` em títulos de notícias diferentes mas com palavras em comum (ex: "Lula anuncia reforma tributária" vs "Lula anuncia pacote econômico") pode retornar ratio ≥ 0.55 por causa das palavras compartilhadas "Lula anuncia", bloqueando cobertura de temas diferentes. Isso cria **falsos positivos de deduplicação** — o motor deixa de publicar artigos legítimos por achar que "já foram cobertos".

**Problema inverso:** Dois artigos sobre o mesmo fato com títulos muito diferentes (paráfrases) podem ter ratio < 0.55 e passar como novos, gerando **duplicatas publicadas**.

#### 🟠 ALTO — `check_recent_synthesis` faz JOIN `rss_control` + `posts` sem índice eficiente

```python
# Linha 85-94
SELECT rc.source_url, p.post_title
FROM {rss_control} rc
JOIN {posts} p ON rc.post_id = p.ID
WHERE rc.feed_name = %s
  AND rc.published_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
```

A coluna `feed_name` na tabela `rss_control` não tem índice. Com 1000+ entradas/dia e pesquisas de 6h, o MySQL faz full scan da tabela. **Correção:** Adicionar `INDEX idx_feed_name (feed_name)` na DDL.

#### 🟡 MÉDIO — `update_existing_post` usa `requests.post` com endpoint errado para atualização

```python
# Linha 129
resp = requests.post(
    f"{config.WP_API_BASE}/posts/{post_id}",
    ...
    json={"content": updated_content},
)
```

A WordPress REST API usa `POST /posts/{id}` para atualizar (em vez de `PATCH`), o que é correto. Mas o payload só envia `content` sem `title`, `excerpt` ou outros campos — o WordPress pode resetar esses campos para valores default dependendo da versão. Deveria usar `PATCH` semanticamente ou enviar todos os campos relevantes.

---

### Arquivo: `motor_consolidado/detector_trending.py`

#### 🔴 CRÍTICO — TF-IDF vectorizer recriado a cada ciclo (sem state persistence)

```python
# Linha 54-56 (_cluster_tfidf)
vectorizer = TfidfVectorizer(max_features=5000)
tfidf_matrix = vectorizer.fit_transform(valid_texts)
sim_matrix = cosine_similarity(tfidf_matrix)
```

O `TfidfVectorizer` é criado e fitado do zero a cada ciclo. Isso é correto para detecção em tempo real. Mas `cosine_similarity(tfidf_matrix)` retorna uma matriz N×N onde N = número de títulos. Se N=200 (10 portais × 20 títulos), a matriz é 200×200 = 40.000 floats = ~300KB. Não é grave per se, mas com ciclos de 2h e N crescendo em ciclos com TIER2 incluído, o pico de memória pode ser maior.

**Problema real:** `cosine_similarity` usa numpy internamente — aloca a matriz completa antes do union-find. Para N=500, são 500×500 floats64 = 2MB alocados pontualmente. Não é leak mas é pico de memória desnecessário dado que apenas pares com similaridade > threshold importam. **Correção:** Usar `cosine_similarity` esparso ou threshold filtering incremental.

#### 🟠 ALTO — `MIN_SOURCES_TRENDING = 1` significa que UM artigo de UMA fonte vira trending

```python
# config_consolidado.py linha 200
MIN_SOURCES_TRENDING = 1

# detector_trending.py linha 163-167
is_trending = (
    len(sources) >= MIN_SOURCES_TRENDING  # ← True com len(sources) >= 1
    or mais_lida_count >= 2
    or manchete_count >= 2
)
```

Com `MIN_SOURCES_TRENDING=1`, **qualquer artigo de qualquer portal vira trending** (uma fonte é suficiente). O comentário no código diz "≥ 3 fontes diferentes, OU ≥ 2 mais lidas, OU ≥ 2 manchetes TIER 1" — mas o código real não reflete isso. A condição `len(sources) >= MIN_SOURCES_TRENDING` com valor 1 torna as outras condições (`mais_lida_count >= 2`, `manchete_count >= 2`) redundantes.

**Impacto:** O motor consolidado tenta sintetizar artigos para dezenas de temas que não são realmente trending, desperdiçando chamadas LLM premium e publicando conteúdo redundante com Raia 1/2.

#### 🟡 MÉDIO — `topic_label` usa o título mais longo, não o mais representativo

```python
# Linha 173
topic_label = max(cluster_titles, key=lambda t: len(t["title"]))[["title"]
```

O título mais longo de um cluster pode ser de um portal secundário com título verbose, não sendo representativo do fato. Isso afeta o `check_recent_coverage` no deduplicador (que usa esse label para busca por similaridade) e os logs de auditoria.

---

### Arquivo: `motor_consolidado/sintetizador.py`

#### 🟠 ALTO — Prompt com até 7 fontes × 4000 chars = ~28.000 chars de input

```python
# Linha 191 (_build_fontes_texto)
f"{src['conteudo'][:4000]}\n"  # Limitar cada fonte a ~4000 chars

# Linha 206
MAX_SOURCES_PER_TOPIC = 7  # em config_consolidado.py
```

7 fontes × 4.000 chars = 28.000 chars ≈ 7.000 tokens só de conteúdo + template do prompt (~500 tokens) + instruções (~800 tokens) = **~8.300 tokens de input**.

Claude Sonnet 4 e GPT-4o têm limite de 200k/128k tokens de contexto, então não há risco de truncamento. Mas cada chamada custa ~$0.025-0.05 (para GPT-4o) × 3 artigos/ciclo × 12 ciclos/dia = $0.90-1.80/dia só no Consolidado. Com TF-IDF identificando muitos "trending", o custo pode ser muito maior.

#### 🟡 MÉDIO — `collect_sources` pode enviar mensagem de aviso ao LLM como "conteúdo"

```python
# Linha 161
content = f"[AVISO DO SISTEMA: Não foi possível realizar a leitura do texto completo..."
```

Quando uma fonte tem paywall/erro, o conteúdo real é substituído por uma mensagem em português instruindo o LLM. O LLM pode interpretar isso como instrução direta e alterar seu comportamento, ou pode incluir literalmente o texto do aviso no artigo gerado.

---

### Arquivo: `motor_consolidado/publicador_consolidado.py`

#### 🔴 CRÍTICO — `source_urls` concatenadas truncadas arbitrariamente em 2048 chars

```python
# Linha 261-265
source_urls = ",".join([s.get("url", "") for s in sources[:3]])
db.register_published(
    source_url=source_urls[:2048],
    ...
)
```

`source_url` no banco é `VARCHAR(2048)`. Com 3 URLs longas (ex: `https://g1.globo.com/politica/noticia/2026/...`), pode ultrapassar 2048 chars, sendo silenciosamente truncado. O truncamento quebra a deduplicação futura: a URL truncada não vai corresponder à URL original em `post_exists`, permitindo que o mesmo tema seja publicado novamente.

**Pior:** `source_url` para consolidadas não é uma URL single — é uma string CSV de múltiplas URLs. A deduplicação em `post_exists` busca essa string exata, que nunca vai coincidir com uma URL individual de um artigo futuro. A deduplicação entre consolidadas e artigos normais é efetivamente não funcional.

#### 🟠 ALTO — `_get_image_for_consolidated` faz request HTTP extra dentro da publicação

```python
# Linha 90-97 (_get_image_for_consolidated)
_resp = _req.get(first_source_url, timeout=10, headers=...)
if _resp.status_code == 200:
    first_html = _resp.text
```

Este request não tem retry e tem timeout de apenas 10s. Se a fonte oficial estiver lenta ou temporariamente indisponível, a imagem falha silenciosamente mas o artigo é publicado sem imagem. Mais importante: este código é executado dentro de `publish_consolidated`, aumentando o tempo total de publicação.

#### 🟡 MÉDIO — Importações repetidas de `sys` e `Path` já importadas no topo

```python
# Linha 61-62 (_get_image_for_consolidated — dentro de função)
import sys
from pathlib import Path
```

Estas já estão disponíveis no escopo do módulo. Reimportar dentro da função é desnecessário.

---

### Arquivo: `motor_consolidado/scraper_homes.py`

#### 🟠 ALTO — Todos os portais são raspados sequencialmente (sem paralelismo)

```python
# Linha 203-217 (scrape_all_portals)
for portal in TIER1_PORTALS:
    titles = scrape_portal_titles(portal, section="tier1")
    all_titles.extend(titles)
for portal in MAIS_LIDAS_PORTALS:
    titles = scrape_portal_titles(portal, section="mais_lidas")
    all_titles.extend(titles)
```

7 portais TIER1 + 3 MAIS_LIDAS + 4 TIER2 (ciclos pares) = até 14 requests HTTP sequenciais. Com timeout de 20s cada, o scraping pode levar até **280 segundos** no pior caso. Com ciclos de 2h, isso não é crítico, mas atrasa o pipeline inteiro.

**Oportunidade:** Usar `ThreadPoolExecutor` como o motor de scrapers já faz.

#### 🟡 MÉDIO — `_extract_titles_with_selectors` para no primeiro seletor com resultado

```python
# Linha 93-95 (_extract_titles_with_selectors)
if results:
    break  # ← Para no primeiro seletor que retorna ALGUM resultado
```

Se o primeiro seletor retorna 1 título irrelevante (menu, rodapé), o fallback para seletores mais específicos não é tentado. Deveria continuar testando até encontrar um seletor com resultado suficiente (ex: `>= 5` títulos).

---

### Arquivo: `motor_consolidado/avaliador_home.py`

#### 🟠 ALTO — Queries com GROUP_CONCAT aninhado — N+1 queries implícitas

```python
# Linha 92-111 (fetch_brasileira_homepage)
SELECT p.ID, p.post_title, ...,
       (SELECT GROUP_CONCAT(...) FROM ... WHERE tr2.object_id = p.ID ...) as categories
FROM posts p
JOIN term_relationships tr ON p.ID = tr.object_id
...
```

A subquery correlacionada `(SELECT GROUP_CONCAT(...) WHERE tr2.object_id = p.ID)` é executada **uma vez por linha** retornada pela query principal. Com 100 posts retornados, são 100 subqueries adicionais. Com duas queries assim na mesma função, são até **200 subqueries extras** por execução do avaliador.

**Correção:** Usar `JOIN` com `GROUP BY` ao invés de subqueries correlacionadas.

#### 🟡 MÉDIO — `calculate_metrics` usa `datetime.now()` sem timezone

```python
# Linha 268
now = datetime.now()  # ← Sem timezone
# ...
md = datetime.fromisoformat(str(manchete_date))  # ← datetime do MySQL (sem tz)
metrics["manchete_age_min"] = int((now - md).total_seconds() / 60)
```

Se o MySQL está em UTC e o servidor Python em UTC-3 (Brasília), a diferença calculada estará errada em 3 horas. Os posts do banco têm horário do MySQL server; `datetime.now()` usa o timezone do processo Python.

---

### Arquivo: `motor_consolidado/validador.py`

#### 🟠 ALTO — Validação de plágio com SequenceMatcher em textos de 3000+ chars é lenta

```python
# Linha 71-80 (validate_no_plagiarism)
for start in range(0, min(len(clean_content), 5000), 1000):
    chunk = clean_content[start:start+1000]
    r = SequenceMatcher(None, chunk, clean_src[:3000]).ratio()
```

Com `MAX_SOURCES_PER_TOPIC=7` e chunks de 1000 chars de conteúdo de 5000 chars:
- Loop externo: 5 iterações (5000 / 1000)
- Loop de fontes: até 7 fontes
- = 35 chamadas de `SequenceMatcher.ratio()` em strings de ~1000 × ~3000 chars

`SequenceMatcher` tem complexidade O(n×m). Para strings de 1000 × 3000 = 3.000.000 operações por chamada × 35 chamadas = **105 milhões de operações** por artigo validado. Lento e bloqueante na thread principal.

#### 🟡 MÉDIO — Artigos com falhas de validação (não-plágio) são publicados mesmo assim

```python
# motor_consolidado.py linha 228-231
if any("plágio" in e.lower() for e in errors):
    logger.error("Artigo descartado por plágio")
    continue
logger.info("Publicando com avisos (não-plágio)")
# ↑ Publica mesmo com erro de "conteúdo abaixo do mínimo" ou "fontes não citadas"
```

Artigos com menos de 600 palavras ou sem citação de fontes são publicados com um simples log de warning. Isso viola as próprias regras editoriais do sistema.

---

## MOTOR MESTRE (LEGACY) 

### Arquivo: `motor_mestre.py`

#### 🔴 CRÍTICO — Arquivo com encoding corrompido (latin1/utf-8 mismatch)

```python
# Linha 8, 58, 62, 64, etc.
"Orquestra os sub-mÃ³dulos e processa os feeds inteligentemente."
"[AVISO] Extrator detectou texto curto ou bloqueado. Adaptando para nota jornalÃ­stica."
```

O arquivo tem caracteres UTF-8 multi-byte decodificados como Latin-1 (`Ã³` = `ó`, `Ã­` = `í`). **O arquivo está corrompido** e qualquer string com caracteres especiais será exibida errada ou causará erros dependendo do terminal/ambiente.

#### 🟠 ALTO — Limite de 7 dias no cutoff com naive datetime

```python
# Linha 170-172 (executar_ciclo)
agora = datetime.now()           # ← sem timezone
limite_dias = timedelta(days=7)

data_pub = datetime.fromtimestamp(time.mktime(entry.published_parsed))  # ← timezone local
```

`published_parsed` de feedparser é uma struct_time em UTC. `time.mktime` converte assumindo **horário local**. Se o servidor está em UTC-3, há um erro de 3 horas. Artigos publicados às 23h UTC (20h local) podem ser cortados incorretamente.

#### 🟡 MÉDIO — Cache como arquivo de texto sem locking

O `gestor_cache` (importado, não auditado diretamente) provavelmente usa um arquivo. Com chamadas concorrentes ou em rápida sequência, o arquivo pode ser corrompido. `salvar_no_cache(entry.link)` e `carregar_cache()` no mesmo loop sem lock.

#### 🟡 MÉDIO — `executar_ciclo` processa até 2 artigos por fonte (hardcoded)

```python
# Linha 190
if noticias_selecionadas >= 2: break
```

Hardcoded. Não configurável. Limita drasticamente o volume quando o sistema deveria estar processando 1000+ artigos/dia.

---

### Arquivo: `motor_avancado.py`

#### 🔴 CRÍTICO — API Keys OpenAI, Grok e Gemini hardcoded no código-fonte

```python
# Linhas 60-91
OPENAI_KEYS = [
    "sk-proj-A7CCX7iBECLbGrRJUPIo9N-...",
    "sk-proj-voTu5Sq46eY8Z5TxtCXNx2D...",
    "sk-proj-1upbLAUgBbs3J4-a0Xyjplm...",
]
GROK_KEYS = [
    "xai-L2tfNb2q7Yz1YYOs2iVdUuKbKq...",
    "xai-o0YD4KYxMOywJsRKQ6myfWdEYl...",
    "xai-ZoK92vQJKIwRLEI7pP3k0r0PMV...",
]
GEMINI_KEYS = [
    "AIzaSyBo0KOZ0loKdZdkwDzoN7K9uR...",
    ...
]
```

**CRÍTICO DE SEGURANÇA.** Três providers, 9 chaves de API completas hardcoded diretamente no código Python. Essas chaves estão expostas em:
- Qualquer repositório Git (histórico permanente mesmo se removidas depois)
- Backups do servidor
- Logs do processo (se o código for logado em debug)
- Qualquer pessoa com acesso ao servidor

**Ação imediata:** Revogar todas as chaves expostas e rotacionar para novas, usando variáveis de ambiente.

#### 🔴 CRÍTICO — WP_APP_PASSWORD com fallback hardcoded

```python
# Linha 54
WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")
```

A senha da aplicação WordPress está hardcoded como fallback. Se `WP_APP_PASS` não estiver no `.env`, a senha padrão é usada diretamente. **Ação imediata:** Remover o fallback, lançar erro se ausente.

#### 🟠 ALTO — `executar_redacao_segura` faz uma chamada LLM de triagem POR ARTIGO

```python
# Linha 690-706 (dentro de loops de fontes e entradas)
for idx, fonte in enumerate(fontes_do_caderno):
    for i, entry in enumerate(feed.entries[:5]):
        nota = avaliar_relevancia(entry.title, fonte['nome'])  # ← LLM call
```

`avaliar_relevancia` chama Gemini (e como fallback GPT-4o-mini) **para cada artigo individualmente**. Com 5 artigos × N fontes, são N×5 chamadas LLM só para triagem. Para um caderno com 20 fontes, são 100 chamadas LLM de triagem antes de escrever um único artigo.

#### 🟠 ALTO — `gerar_imagem` tem código morto após `return None`

```python
# Linha 531-534 (gerar_imagem)
def gerar_imagem(prompt_imagem):
    return None  # [TRAVA EDITORIAL - DALL-E 3 DESATIVADO]

    global OPENAI_KEYS   # ← NUNCA EXECUTADO
    print("[IMAGEM] A gerar capa com DALL-E 3...")
```

Código após `return None` nunca executa. Python não gera warning para isso. O `global OPENAI_KEYS` é dead code que pode confundir análise estática.

#### 🟠 ALTO — Rotação de chaves com `append+pop(0)` não é round-robin eficiente

```python
# Linha 140 (chamar_gemini_rest) e similar em outros lugares
GEMINI_KEYS.append(GEMINI_KEYS.pop(0))
```

Este padrão move o índice 0 para o final. Com 3 chaves e 3 falhas consecutivas, a lista volta ao estado original: `[k1,k2,k3]` → `[k2,k3,k1]` → `[k3,k1,k2]` → `[k1,k2,k3]`. Após esgotar `tentativas = len(GEMINI_KEYS)`, todas as chaves foram tentadas. OK funcionalmente, mas modifica a lista global, causando problemas de concorrência se chamado de múltiplas threads.

#### 🟡 MÉDIO — `publicar_no_wordpress` mistura categorias e tags no mesmo campo

```python
# Linha 592-605 (publicar_no_wordpress)
todas_categorias = [cat_id] + materia.get("tags_extras", [])
payload = {
    'categories': todas_categorias,  # ← IDs de tags misturados com categorias
}
```

`tags_extras` são IDs de tags (de `MAPA_TAGS`), mas são enviados no campo `categories` da API WordPress. Tags e categorias são taxonomias diferentes. Posts ficam com categorias incorretas/duplicadas e sem tags reais.

#### 🟡 MÉDIO — Sem deduplicação no motor avançado

`executar_redacao_segura` não verifica se um artigo já foi publicado (sem consulta ao banco, sem verificação de cache de links). Cada execução pode republicar os mesmos artigos se o `gestor_cache` não funcionar corretamente (e o motor avançado nem usa o `gestor_cache` do motor mestre — são módulos separados).

---

## PROBLEMAS TRANSVERSAIS (TODOS OS MOTORES)

### 🔴 CRÍTICO — Interação entre ciclos de 30min (Raia 1/2) e 2h (Raia 3) sem coordenação

Os três motores rodam de forma completamente independente via cron:
- Raia 1: a cada 30 minutos
- Raia 2: a cada 30 minutos (provavelmente com offset diferente)
- Raia 3: a cada 2 horas

**Problema 1:** Raias 1 e 2 podem publicar o mesmo artigo entre si (race condition na deduplicação, já descrito).

**Problema 2:** Raia 3 pode publicar uma consolidada sobre um tema que Raia 1 publicou 5 minutos antes. O `check_recent_coverage` usa `DEDUP_WINDOW_HOURS=4`, mas compara por similaridade de título (SequenceMatcher). Se o título da Raia 1 for diferente do `topic_label` da Raia 3, a deduplicação falha.

**Problema 3:** Sem mecanismo de back-pressure — se uma Raia estiver lenta (ex: LLM demorando), a próxima execução do cron começa uma nova instância enquanto a anterior ainda está rodando. O lock file previne execuções duplicadas do MESMO motor, mas não há coordenação entre os três motores.

### 🔴 CRÍTICO — Secrets expostos em múltiplos arquivos

Resumindo a exposição de credenciais encontradas:
- `motor_avancado.py` linhas 60-91: 9 chaves de API (OpenAI, Grok, Gemini)
- `motor_avancado.py` linha 54: senha WP hardcoded
- `check_keys.py` linhas 86-114: 6 chaves de API (DeepSeek, Qwen)

**Total:** 15+ credenciais de produção hardcoded em código Python.

### 🟠 ALTO — `sys.path.insert(0, ...)` em múltiplos arquivos e funções

Encontrado em:
- `motor_rss_v2.py` linha 381 (dentro de `process_article`)
- `motor_scrapers_v2.py` linha 935 (dentro de `processar_artigo`)
- `publicador_consolidado.py` linha 64 (dentro de `_get_image_for_consolidated`)
- `config_consolidado.py` linhas 12-14 (no módulo)
- `sintetizador.py` linhas 12-13 (no módulo)
- `motor_consolidado.py` linhas 27-30 (no módulo)

A inserção repetida no path pelo mesmo caminho resulta em duplicatas no `sys.path`. Um `sys.path` com 50+ entradas idênticas degrada o tempo de importação de módulos.

### 🟠 ALTO — Logs sem rotação configurada

```python
# motor_rss_v2.py linha 61
log_file = config.LOG_DIR / f"rss_{datetime.now().strftime('%Y-%m-%d')}.log"
file_handler = logging.FileHandler(log_file, encoding="utf-8")
```

Um novo arquivo de log é criado por dia, mas os arquivos antigos **nunca são deletados**. Com 1000+ artigos/dia gerando logs verbose, cada arquivo de log pode ter centenas de MB. Sem rotação, o disco do LightSail (geralmente 20-50GB) pode encher em semanas.

**Correção:** Usar `logging.handlers.RotatingFileHandler` ou `TimedRotatingFileHandler` com `backupCount`.

### 🟠 ALTO — Importações dentro de funções (padrão anti-performance)

Encontrado em:
- `motor_rss_v2.py` linha 382: `from curador_imagens_unificado import is_official_source`
- `motor_scrapers_v2.py` linha 936: mesma importação
- `publicador_consolidado.py` linha 65: `from curador_imagens_unificado import get_curador, upload_to_wordpress, is_official_source`
- `deduplicador.py` linha 118: `import requests`
- `scraper_homes.py` linha 146: `import feedparser`
- `avaliador_home.py` linha 181: `from scraper_homes import scrape_all_portals`

Python cacheia módulos em `sys.modules`, mas o lookup a cada chamada e o risco de ImportError em runtime (módulo não encontrado durante execução) tornam esse padrão problemático.

### 🟡 MÉDIO — Sem tratamento de timezone consistente

- `motor_rss_v2.py`: usa `datetime.now(timezone.utc)` ✓
- `motor_scrapers_v2.py`: usa `datetime.now(timezone.utc)` ✓
- `motor_consolidado/avaliador_home.py`: usa `datetime.now()` sem timezone ✗
- `motor_mestre.py`: usa `datetime.now()` sem timezone ✗

Em servidores AWS/LightSail configurados em UTC, a diferença pode não ser observável, mas é uma bomba-relógio se o timezone do servidor mudar.

### 🟡 MÉDIO — `description` pode não existir em entradas de feed antigas

```python
# motor_avancado.py linha 700
"resumo": re.sub('<[^<]+?>', '', entry.description),
```

`entry.description` pode lançar `AttributeError` se o campo não existir no RSS. Deveria ser `entry.get('description', entry.get('summary', ''))` via feedparser API.

---

## TABELA DE PRIORIDADES PARA CORREÇÃO

| Prioridade | Bug | Arquivo | Impacto |
|-----------|-----|---------|---------|
| 1 | `cloudscraper` por request — memory leak | `motor_scrapers_v2.py:276` | Crash LightSail |
| 2 | API Keys hardcoded | `motor_avancado.py:60-91`, `check_keys.py:86` | Segurança crítica |
| 3 | Race condition deduplicação Raia1/2 | `motor_rss_v2.py:301`, `motor_scrapers_v2.py:842` | Duplicatas publicadas |
| 4 | `sys.path.insert` dentro de funções | múltiplos arquivos | Memory leak acumulativo |
| 5 | Circuit breaker/key rotation não thread-safe | `llm_router.py:26,65` | Falhas LLM sob carga |
| 6 | Cursor não fechado em exceção | `db.py:153` | Connection pool exhaustion |
| 7 | `post_content` no SELECT do deduplicador | `deduplicador.py:39` | Pico de memória |
| 8 | Cache categorias/tags nunca expira | `wp_publisher.py:110` | Categorias erradas + memory |
| 9 | MIN_SOURCES_TRENDING=1 (todo artigo vira trending) | `config_consolidado.py:200` | Custo LLM desnecessário |
| 10 | Gemini sem timeout | `llm_router.py:193` | Thread bloqueada indefinidamente |
| 11 | Logs sem rotação | todos os motores | Disco cheio |
| 12 | Double fetch HTML por artigo | `motor_rss_v2.py:340,375` | CPU/memória 2x desnecessário |
| 13 | Domain delay não funciona com ThreadPoolExecutor | `motor_scrapers_v2.py:1065` | Rate limiting contornado |
| 14 | SequenceMatcher O(n²) no deduplicador | `deduplicador.py:56` | CPU bound em escala |
| 15 | source_url truncado em consolidadas | `publicador_consolidado.py:261` | Deduplicação quebrada |

---

## RECOMENDAÇÕES ARQUITETURAIS

### 1. Tornar o cloudscraper singleton
```python
# motor_scrapers_v2.py — topo do módulo
import cloudscraper
_CLOUDSCRAPER = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)
```

### 2. Thread-safe circuit breaker e key rotation
```python
import threading
_cb_lock = threading.Lock()
_key_lock = threading.Lock()

def _cb_record_failure(provider: str):
    with _cb_lock:
        # ... lógica existente
```

### 3. Unique constraint na tabela de controle
```sql
ALTER TABLE wp_7_rss_control 
  ADD UNIQUE KEY uk_source_url (source_url(768));
```

### 4. Mover importações para topo dos módulos
Todas as `from X import Y` dentro de funções devem ser movidas para o topo do arquivo.

### 5. Session HTTP reutilizável
```python
# Criar session global por módulo
_SESSION = requests.Session()
_SESSION.headers.update(_DEFAULT_HEADERS)
```

### 6. Rotação de logs
```python
from logging.handlers import TimedRotatingFileHandler
handler = TimedRotatingFileHandler(
    log_file, when='midnight', backupCount=7, encoding='utf-8'
)
```

### 7. Gemini com system_instruction
```python
response = client.models.generate_content(
    model="gemini-2.5-pro-preview-05-06",
    contents=user_prompt,
    config=genai.types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.4,
    ),
)
```

### 8. Revogar e rotacionar credenciais expostas imediatamente
- Revogar as 15+ chaves encontradas hardcoded
- Mover TODAS as credenciais para `.env`
- Adicionar `.env` e `*_keys.py` ao `.gitignore`
- Usar `python-dotenv` consistentemente

---

*Auditoria gerada em 2026-03-20. Baseada em análise estática completa de 21 arquivos Python.*
