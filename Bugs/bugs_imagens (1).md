# Auditoria de Bugs — Sistema de Curadoria de Imagens
**Brasileira.news — Análise Técnica Completa**
**Data:** 20/03/2026
**Analista:** Engenheiro Sênior Python — Revisão de Código em Produção

---

## Índice

1. [curador_imagens_unificado.py](#1-curador_imagens_unificadopy)
2. [gestor_imagens.py](#2-gestor_imagenspy)
3. [motor_rss/image_handler.py](#3-motor_rssimage_handlerpy)
4. [regras_arte.py](#4-regras_artepy)
5. [motor_rss/wp_publisher.py](#5-motor_rsswp_publisherpy)
6. [motor_rss/llm_router.py](#6-motor_rssllm_routerpy)
7. [gestor_wp.py](#7-gestor_wppy)
8. [motor_consolidado/publicador_consolidado.py](#8-motor_consolidadopublicador_consolidadopy)
9. [roteador_ia.py](#9-roteador_iapy)
10. [trava_definitiva_dalle.py](#10-trava_definitiva_dallepy)
11. [trava_imagens_ia.py](#11-trava_imagens_iapy)
12. [limpador_imagens_ia.py](#12-limpador_imagens_iapy)
13. [revisor_imagens_antigos.py](#13-revisor_imagens_antigospy)
14. [test_curador_imagens.py](#14-test_curador_imagenspy)
15. [test_image_queries.py](#15-test_image_queriespyy)
16. [garantia_imagens.py](#16-garantia_imagenspy)
17. [Análise Transversal — Problemas Sistêmicos](#17-análise-transversal--problemas-sistêmicos)

---

## 1. `curador_imagens_unificado.py`

Este é o módulo central do pipeline. Concentra a maior densidade de bugs.

### 1.1 Bug Crítico — Lógica RGBA invertida no `upload_to_wordpress`

```python
if img.mode not in ('RGB', 'RGBA'):
    img = img.convert('RGB')
elif img.mode == 'RGBA':
    bg = Image.new('RGB', img.size, (255, 255, 255))
    bg.paste(img, mask=img.split()[3])
    img = bg
```

**Problema:** O primeiro `if` verifica `mode not in ('RGB', 'RGBA')` — ou seja, se o modo NÃO for RGB nem RGBA, converte para RGB. Se for RGBA, cai no `elif` e faz a composição correta. Mas se o modo já for `'RGB'`, não entra em nenhum bloco — correto. **Porém**, a lógica deixa passar modos como `'P'` (palette/GIF), `'L'` (grayscale), `'CMYK'` (impressão), `'YCbCr'`, `'LAB'`, `'HSV'`, `'I'` (int 32-bit), `'F'` (float) sem conversão **apenas se** o `mode not in ('RGB', 'RGBA')` for False — o que está certo para esses casos, eles seriam capturados pelo primeiro `if`. O problema real está em um subconjunto: imagens com modo `'PA'` (Palette + Alpha) não entram no `elif img.mode == 'RGBA'` e são convertidas direto para RGB via `convert('RGB')` sem composição do canal alpha, resultando em **fundo preto ou transparência corrompida**.

**Impacto:** Imagens GIF animadas abertas via PIL retornam o primeiro frame em modo `'P'` ou `'PA'`. O `img.split()[3]` no `elif` nunca é chamado, mas o `convert('RGB')` no primeiro `if` pode gerar fundos pretos em vez de fundos brancos.

---

### 1.2 Bug Crítico — `is_valid_image_url` faz request HTTP para toda URL validada

```python
def is_valid_image_url(url: str) -> bool:
    ...
    dims = _get_image_dimensions_from_headers(url)
```

**Problema:** `is_valid_image_url` chama `_get_image_dimensions_from_headers(url)`, que faz uma requisição HTTP para cada URL antes de validar. Este método é chamado:
- Dentro de `tier1_scrape_html` para **cada tag `<img>`** encontrada no HTML
- Dentro de `tier2_government_banks` para cada resultado da API CSE
- Dentro de `tier3a_flickr_gov`, `tier3b_wikimedia`, `tier3c_google_cse`
- Dentro de `tier4_stock_apis`

Uma página com 30 imagens no HTML acionará 30 requisições HTTP síncronas e bloqueantes dentro da validação. Isso transforma o Tier 1 em um **crawler síncrono**, potencialmente adicionando dezenas de segundos ao pipeline por post.

**Adicionalmente**, `_get_image_dimensions_from_headers` usa `stream=True` mas **não fecha o stream**:

```python
resp = requests.get(url, headers={"Range": "bytes=0-1024"}, timeout=config.HTTP_TIMEOUT, stream=True)
data = resp.content  # lê o conteúdo mas não fecha
```

O objeto `Response` com `stream=True` precisa ser explicitamente fechado com `resp.close()` ou usado como context manager. Sem isso, a conexão TCP fica aberta até o garbage collector agir — **resource leak** em produção de alto volume.

---

### 1.3 Bug Crítico — `is_valid_image_url` bloqueia WebP sem `data-src` com path curto

```python
ext = path_lower.rsplit(".", 1)[-1] if "." in path_lower else ""
if ext not in ("jpg", "jpeg", "png", "webp"): return False
```

O filtro de extensão aceita `webp`, mas o bloco de dimensões tenta decodificar apenas JPEG e PNG via struct:

```python
def _get_image_dimensions_from_headers(url: str) -> tuple[int, int] | None:
    ...
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24: ...  # PNG
    if data[:2] == b"\xff\xd8": ...  # JPEG
```

**Não há parsing de WebP**. Para uma URL `.webp`, `dims` será sempre `None`, e a função retorna `True` sem verificação de dimensões — potencialmente aceitando imagens WebP minúsculas (ícones 16x16) que passam pelos filtros de extensão mas falham silenciosamente na verificação de tamanho mínimo.

**Agravante:** A Agência Brasil e sites do governo usam WebP crescentemente. Imagens válidas passam sem verificação de dimensões; imagens inválidas pequenas também passam.

---

### 1.4 Bug Crítico — Tier 1 é pulado para fontes NÃO-oficiais mesmo com conteúdo disponível

```python
# TIER 1: Original Source Scrape
if not force_fallback and is_official:
    tier1_url = tier1_scrape_html(html_content, source_url)
```

O Tier 1 só executa para fontes `is_official`. Para fontes não-oficiais (G1, UOL, Folha, etc.), o código pula diretamente para o Tier 2. Isso significa que **a imagem original da notícia nunca é tentada** para fontes comerciais. A justificativa nos comentários é "evitar copyright comercial", mas:

1. Fontes privadas frequentemente disponibilizam imagens de uso livre via licença editorial para fins informativos
2. A `og:image` frequentemente aponta para CDNs de terceiros (agências de foto) que não têm relação com o domínio comercial
3. O comportamento real resulta em posts de fontes comerciais receberem imagens de banco de imagens genéricas em vez da foto real da notícia

---

### 1.5 Bug Crítico — Tier 2 e Tier 3C usam a MESMA API Google CSE com queries diferentes

```python
def tier2_government_banks(keywords: str) -> str | None:
    ...
    gov_query = f"{keywords} site:gov.br OR site:leg.br OR site:jus.br OR site:ebc.com.br"
    params = {"q": gov_query, "cx": GOOGLE_CSE_ID, ...}
    
def tier3c_google_cse(keywords: str) -> str | None:
    ...
    params = {"q": keywords, "cx": GOOGLE_CSE_ID, ...}
```

Ambos os tiers consomem a mesma quota da API Google CSE (100 queries/dia gratuitas, depois $5/1000). Pior: na sequência de execução do pipeline principal:

```python
tier2_url = tier2_government_banks(query_gov)   # 1 query CSE
tier3c_url = tier3c_google_cse(query_gov)        # +1 query CSE (MESMA query, já tentada!)
```

**`tier3c_google_cse` é chamada com `query_gov`** — a mesma query usada no Tier 2, sem o filtro `site:gov.br`. Ou seja: se o Tier 2 falhou (sem resultados governamentais), o Tier 3C vai tentar a mesma busca sem filtro de domínio, desperdiçando quota e frequentemente retornando imagens de sites aleatórios para notícias governamentais.

---

### 1.6 Bug Crítico — Flickr `user_id` com valores placeholder inválidos

```python
FLICKR_GOV_USERS = [
    "paborboleta",       # Palácio do Planalto
    "senaborboleta",     # Senado Federal
    "camaborboleta",     # Câmara dos Deputados
    "agaborboleta",      # Agência Brasil
    "govbr",             # Portal Gov.br
    "staborboleta",      # STF
]
```

Esses são **nomes de usuário fictícios/placeholder**. O Flickr exige `user_id` numérico (ex: `12345678@N00`) OU `username` que deve ser uma conta Flickr real. Os nomes listados ("paborboleta", "senaborboleta") claramente não são usernames Flickr reais — são placeholders que nunca foram preenchidos com os IDs corretos.

**Consequência:** `tier3a_flickr_gov` faz 3 requisições à API Flickr com IDs inválidos (retornando erro ou 0 resultados), depois faz mais uma requisição geral. O Tier 3A desperdicia recursos e **nunca funciona corretamente** para contas governamentais brasileiras.

---

### 1.7 Race Condition — Dois singletons para a mesma classe

```python
class CuradorImagensUnificado:
    _instance = None  # Singleton via __new__
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

_curador_instance = None  # SEGUNDO singleton via variável global

def get_curador() -> CuradorImagensUnificado:
    global _curador_instance
    if _curador_instance is None:
        _curador_instance = CuradorImagensUnificado()
    return _curador_instance
```

Há **dois mecanismos de singleton paralelos**: o `__new__` da classe e a variável global `_curador_instance`. Em ambiente multi-thread, ambos os caminhos podem criar instâncias simultaneamente sem lock. Embora o `__new__` garanta que `cls._instance` seja único, a combinação não é thread-safe: dois threads podem ambos ver `_curador_instance is None` e criar duas chamadas para `CuradorImagensUnificado()`, que por sua vez passam pelo `__new__` — que também não tem lock.

**Adicionalmente**, `ImageQueryGenerator` tem sua própria variável global:
```python
_query_generator = None
def get_query_generator() -> ImageQueryGenerator:
    global _query_generator
    ...
```

Em ambiente de produção com múltiplas workers (gunicorn/uwsgi), cada processo tem seu próprio espaço de memória, então o singleton não funciona entre processos — isso é esperado. Mas dentro de um único processo com threads (threading), há race condition real.

---

### 1.8 Falha Silenciosa — `upload_to_wordpress` falha sem retentar no meta update

```python
if meta_payload:
    requests.post(
        f"{config.WP_API_BASE}/media/{media_id}",
        auth=auth, json=meta_payload, timeout=10
    )
return media_id
```

O `requests.post` para atualizar `alt_text` e `caption` **não tem tratamento de erro**. Se falhar (timeout, 4xx, 5xx), o erro é silenciosamente ignorado. O `media_id` é retornado como sucesso mesmo que `alt_text` e `caption` não tenham sido gravados. Em produção, isso significa imagens publicadas sem texto alternativo — problema de acessibilidade e SEO.

**Adicionalmente:** não usa `_request_with_retry`, inconsistente com o padrão do módulo `wp_publisher.py`.

---

### 1.9 Bug Crítico — `get_best_image_for_post` retorna placeholder `None` em vez de falhar explicitamente

```python
# TIER 5: Placeholder TIER
logger.info("Todos os Tiers falharam. Usando imagem placeholder de fallback.")
media_id = upload_to_wordpress(PLACEHOLDER_IMAGE_URL, f"fallback-{safe_filename}", ...)
return media_id
```

Se `upload_to_wordpress` do placeholder também falhar (rede, autenticação WP), a função retorna `None`. Os chamadores em `gestor_wp.py` e `publicador_consolidado.py` usam `if media_id:` — o que significa que `featured_media` não é incluído no post. **O post é publicado sem imagem destacada sem nenhum alerta além de um `logger.warning` que pode não estar sendo monitorado.**

---

### 1.10 Bug de Lógica — `content_patterns` com regex não funciona

```python
content_patterns = [
    "/files/", "/uploads/", "/media/", "/images/", "/fotos/",
    "/noticia", "/materia", "/artigo", "/post/", "/news/",
    r"\d{4}", r"\d{2,}",  # Anos ou IDs numéricos
]
has_content_pattern = any(p in path_lower for p in content_patterns[:6])
```

As entradas `r"\d{4}"` e `r"\d{2,}"` são strings de regex, mas são testadas com `in` (operador de substring), **não com `re.search`**. A expressão `r"\d{4}" in path_lower` verifica se a string literal `\d{4}` está no path — o que nunca é verdade em URLs reais. Além disso, apenas `content_patterns[:6]` é usado, excluindo `"/noticia"`, `"/materia"`, `"/artigo"`, `"/post/"`, `"/news/"` e os padrões regex.

**Agravante:** `has_content_pattern` é calculado mas **nunca é usado na lógica de retorno** da função `is_valid_image_url`. A variável é computada e descartada.

---

### 1.11 Edge Case — Placeholder URL hardcoded no código E em variável de ambiente

```python
PLACEHOLDER_IMAGE_URL = os.getenv(
    "PLACEHOLDER_IMAGE_URL",
    "https://brasileira.news/wp-content/uploads/2023/10/placeholder-brasileiranews.jpg"
)
```

No `limpador_imagens_ia.py`:
```python
URL_DEFAULT = "https://brasileira.news/wp-content/uploads/sites/7/2026/02/imagem-brasileira.png"
```

**Dois placeholders diferentes** estão hardcoded em dois arquivos. Se o Tier 5 usar o primeiro URL e o limpador usar o segundo, o sistema terá posts com dois tipos diferentes de "imagem padrão", tornando impossível identificar automaticamente todos os posts sem imagem real.

---

### 1.12 Bug de API — Flickr `user_id` passado como parâmetro de query, não validado

```python
params["user_id"] = gov_user
resp = requests.get("https://api.flickr.com/services/rest/", params=params, timeout=10)
if resp.status_code == 200:
    data = resp.json()
    photos = data.get("photos", {}).get("photo", [])
```

A API Flickr retorna `stat: "fail"` com `code: 1` ("User not found") quando o `user_id` é inválido, mas o HTTP status ainda é 200. O código verifica `resp.status_code == 200` e assume sucesso, sem verificar `data.get("stat")`. Para todos os 6 usuários fictícios, o código vai:
1. Receber HTTP 200
2. Ver `"photos": {"photo": []}` (lista vazia)
3. Não encontrar nada, continuar silenciosamente

O resultado é 6 requisições desperdiçadas e nenhum aviso de que os `user_id` são inválidos.

---

### 1.13 Performance — Gemini API chamada com POST direto, ignorando o SDK configurado

No `ImageQueryGenerator._generate_ai_queries`:
```python
resp = requests.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_key}",
    ...
)
```

O resto do sistema usa `from google import genai` (SDK oficial). Este método usa `requests.post` direto para a API REST. Além de inconsistente, o SDK do Google já tem retry logic, backoff exponencial e tratamento de rate limit — o POST manual não tem nada disso. Se a API Gemini retornar 429, o erro é capturado pelo `except Exception` e as queries caem para o fallback, sem log adequado.

---

### 1.14 Problema de Design — `_get_image_dimensions_from_headers` usa `Range` header não garantido

```python
resp = requests.get(url, headers={"Range": "bytes=0-1024"}, timeout=config.HTTP_TIMEOUT, stream=True)
data = resp.content
```

O header `Range` é uma **sugestão** — servidores podem ignorar e retornar o conteúdo completo com `200 OK` em vez de `206 Partial Content`. O código não verifica o status code; se o servidor retornar a imagem completa (podendo ser MB de dados), `resp.content` vai baixar tudo antes de retornar. Para imagens grandes (ex: 10MB do Wikimedia Commons), isso é um timeout silencioso que pode demorar 30+ segundos.

---

### 1.15 Segurança — API keys expostas em f-strings de logging

```python
logger.info(f"[Queries] GOV/LIVRE: {query_gov}")
logger.info(f"[TIER 3A] Imagem Flickr Gov encontrada: {img_url}")
```

Embora as queries em si não sejam chaves, o código em `_generate_ai_queries` constrói a URL com a chave inline:
```python
f"https://generativelanguage.googleapis.com/v1beta/models/...?key={self.gemini_key}"
```

Se o logging de requests estiver habilitado (nível DEBUG), a URL com a API key pode ser logada por bibliotecas de instrumentação (requests-toolbelt, urllib3 debug). Considerar mascarar a chave em logs.

---

### 1.16 Edge Case — `tier1_scrape_html` aceita URL relativa `//` (protocol-relative)

```python
if url.startswith("/"):
    parsed = urlparse(source_url)
    url = f"{parsed.scheme}://{parsed.netloc}{url}"
```

URLs no formato `//cdn.example.com/image.jpg` (protocol-relative) começam com `/` mas são tratadas como paths relativos, gerando `https://source_domain.com//cdn.example.com/image.jpg` — uma URL inválida. O correto seria verificar `url.startswith("//")` separadamente e tratar como `https:` + url.

---

### 1.17 Edge Case — `safe_filename` pode resultar em string vazia

```python
safe_filename = re.sub(r"[^a-z0-9]+", "-", title.lower().strip())[:50]
```

Se `title` for uma string de apenas caracteres especiais (ex: `"!!??..!!"`, ou um título em árabe/japonês/chinês), o regex remove tudo e `safe_filename` fica vazio ou `"-"`. Isso resulta em um filename `".jpg"` ou `"-.jpg"` enviado ao WordPress, que pode recusar o upload.

---

### 1.18 Bug de Lógica — `get_best_image_for_post` chama `get_query_generator()` duas vezes

```python
_query_generator = None
try:
    _query_generator = get_query_generator()
    category = _query_generator._detect_category(title, html_content) if html_content else "geral"
except Exception:
    pass

# ... mais código ...

if _query_generator is None:
    _query_generator = get_query_generator()
tier_queries = _query_generator._generate_ai_queries(title, html_content, category)
```

A variável local `_query_generator` conflita com a **variável global do módulo** `_query_generator = None` declarada no final do arquivo. Dentro da função, a atribuição cria uma **nova variável local** que sombreia a global, o que é o comportamento correto de Python. Mas o comentário `# Initialize _query_generator` e a verificação `if _query_generator is None` são desnecessários pois `get_query_generator()` já gerencia o singleton global. Isso cria confusão e dificulta debugging.

---

## 2. `gestor_imagens.py`

### 2.1 Falha Silenciosa — Sem verificação de dimensões mínimas

```python
if img_resp.status_code == 200 and len(img_resp.content) > 10000:
    return img_resp.content
```

A única validação é o tamanho em bytes (>10KB para og:image, >15KB para tags img). Não há verificação de dimensões. Uma imagem de 1x1 pixel em alta qualidade TIFF ou PNG pode facilmente ter >10KB e passar por este filtro.

### 2.2 Resource Leak — `requests.get` sem `with` ou `close()`

```python
img_resp = requests.get(link_img, headers=headers, timeout=10)
if img_resp.status_code == 200 and len(img_resp.content) > 10000:
    return img_resp.content
```

A resposta HTTP não é fechada explicitamente. Embora `requests` gerencie isso internamente para respostas sem streaming, é boa prática fechar. Em loop intensivo (função chamada para muitos posts), acumula conexões em `CLOSE_WAIT`.

### 2.3 Bug de Lógica — Arquivo legado com lógica duplicada do `curador_imagens_unificado.py`

`gestor_imagens.py` implementa `raspar_imagem_original()` que duplica exatamente o Tier 1 do `curador_imagens_unificado.py`. O `motor_rss/image_handler.py` é um shim que redireciona para o novo curador, mas `gestor_wp.py` importa `get_curador()` diretamente do novo módulo. Se alguém importar `gestor_imagens` diretamente (possível em código legado não listado), obtém comportamento diferente:

- `gestor_imagens.py`: retorna `bytes` (conteúdo da imagem baixado)
- `curador_imagens_unificado.py`: retorna `int` (media_id do WordPress)

Essas **assinaturas incompatíveis** com o mesmo propósito é uma bomba-relógio para quem tentar integrar código legado.

### 2.4 Falha Silenciosa — `except Exception as e: print(...)` com `print` em vez de `logging`

O módulo usa `print()` para erros em vez de `logging`. Em produção, se stdout não for capturado, erros são silenciosamente perdidos.

### 2.5 Edge Case — URLs com querystring sendo testadas com `re.search(r'(logo|icon...)', link_img)`

```python
if not re.search(r'(logo|icon|avatar|favicon)', link_img, re.IGNORECASE):
```

Uma URL como `https://agenciabrasil.ebc.com.br/foto-lula-discurso?size=icon` contém `icon` na querystring e seria **incorretamente rejeitada**. O filtro deveria ser aplicado apenas no path, não em toda a URL.

---

## 3. `motor_rss/image_handler.py`

### 3.1 Bug Crítico — Shim importa `get_curador` mas a expõe de forma errada

```python
from curador_imagens_unificado import (
    get_featured_image,
    search_unsplash,
    upload_to_wordpress,
    extract_image_from_content
)

def _is_valid_image_url(url: str) -> bool:
    from curador_imagens_unificado import get_curador
    return get_curador()._url_valida(url)
```

`get_curador` é importado localmente dentro da função em vez de no topo do módulo. Isso significa que a cada chamada a `_is_valid_image_url`, Python faz um `import` do módulo — que é cacheado pelo `sys.modules`, mas a busca no dict de importações tem custo. Para validação em loops, isso é desnecessário.

### 3.2 Problema de Design — Shim expõe `upload_to_wordpress` diretamente

O shim re-exporta `upload_to_wordpress` de `curador_imagens_unificado`. Qualquer código que importe do shim e chame `upload_to_wordpress` vai **bypassar** toda a lógica dos Tiers e fazer upload direto, sem validação de dimensões, sem crop 16:9, e usando as credenciais WP do curador (não do wp_publisher). Isso é um vetor de inconsistência arquitetural.

### 3.3 Problema de Design — Shim não documenta quais funções estão disponíveis para chamadores externos

O comentário diz "shim para compatibilidade retroativa", mas não há documentação sobre quais consumers ainda usam este shim vs. quais já foram migrados para `curador_imagens_unificado` diretamente.

---

## 4. `regras_arte.py`

### 4.1 Bug de Design — Instrução `USE_ORIGINAL_IMAGE` não é um valor verificável pelo pipeline

```python
# OUTPUT EXIGIDO nestes casos: Preencha a chave "prompt_imagem" EXATAMENTE com o valor: "USE_ORIGINAL_IMAGE"
```

Em `gestor_wp.py`:
```python
comando_ia = dados.get('prompt_imagem', '').strip()
if is_oficial:
    if comando_ia and "USE_ORIGINAL_IMAGE" not in comando_ia.upper():
        img_bytes = roteador_ia_imagem(comando_ia)
```

A instrução de arte diz que para "Risco Alto", o LLM deve preencher `prompt_imagem` com `"USE_ORIGINAL_IMAGE"`. O `gestor_wp.py` então checa `"USE_ORIGINAL_IMAGE" not in comando_ia.upper()`. Mas:

1. Se o LLM retornar variantes como `"use_original_image"`, `"USE ORIGINAL IMAGE"` (sem underscore), `"USE_ORIGINAL_IMAGE."` (com ponto), a verificação falhará
2. Se o LLM retornar `null`/vazio para `prompt_imagem` (campo ausente), `comando_ia` é `""`, e a condição `if comando_ia` é `False`, então **nenhuma imagem é tentada pela IA** — correto acidentalmente, mas por razão errada
3. O valor `"USE_ORIGINAL_IMAGE"` é propagado como string até o payload de publicação WordPress, potencialmente gravado em metadados do post

### 4.2 Problema de Design — Regras de arte são texto puro sem validação estrutural

As regras são uma string de instrução de sistema em linguagem natural. Não há schema de validação. O LLM pode retornar qualquer coisa no `prompt_imagem` — incluindo prompts problemáticos como `"foto realista de Lula sendo preso"` — e nenhuma validação programática impedirá que isso chegue ao pipeline de imagens.

---

## 5. `motor_rss/wp_publisher.py`

### 5.1 Bug Crítico — `featured_media: 0` não é enviado, mas `featured_media: None` também não

```python
if featured_media:
    post_data["featured_media"] = featured_media
```

Em Python, `if featured_media:` é False tanto para `None` quanto para `0`. Se `featured_media=0` for passado (valor padrão inválido do WordPress), o campo não é enviado. Correto. Mas o problema é se um chamador passar `featured_media=False` por engano — também seria silenciosamente ignorado. Mais importante: **não há fallback para placeholder** quando `featured_media` é `None`. O post é publicado sem imagem sem nenhum aviso ao nível do publisher.

### 5.2 Race Condition — Cache de categorias e tags não é thread-safe

```python
_category_cache: dict[str, int] = {}
_tag_cache: dict[str, int] = {}

def _load_categories_from_db() -> dict[str, int]:
    global _category_cache
    if _category_cache:
        return _category_cache
    try:
        raw = db.get_categories()
        for name, tid in raw.items():
            normalized = html.unescape(name).lower().strip()
            _category_cache[normalized] = tid
    ...
    return _category_cache
```

Dois threads podem ambos ver `_category_cache` como vazio e chamar `db.get_categories()` simultaneamente. Embora isso não corrompa o dicionário em CPython (GIL protege operações de dict), resulta em **duas chamadas ao banco de dados** onde deveria haver uma. Em produção com múltiplos workers, o cache é por processo e não é compartilhado — cada worker re-popula o cache na primeira requisição.

### 5.3 Falha Silenciosa — `get_or_create_category` retorna `None` sem criar categoria default

```python
def get_or_create_category(name: str) -> int | None:
    ...
    logger.warning("Não foi possível obter/criar categoria: %s", name)
    return None
```

Em `_resolve_category`:
```python
def _resolve_category(name: str) -> list[int]:
    cat_id = get_or_create_category(name)
    return [cat_id] if cat_id else []
```

Se a categoria não pode ser criada, `categories` no post data fica `[]`. O WordPress pode usar a categoria default (geralmente "Uncategorized" / ID 1) ou rejeitar o post dependendo da configuração. Não há fallback para uma categoria de segurança configurada.

### 5.4 Bug de Lógica — Slug gerado para categoria/tag ignora acentuação

```python
slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
```

Para um nome como `"Política & Poder"`, `key` após `html.unescape().lower().strip()` é `"política & poder"`. O regex remove `í`, `&`, e espaços, gerando slug `"pol-tica-poder"` (com `í` removido, gerando "pol" + "tica"). O correto seria usar `unidecode` ou `unicodedata.normalize('NFKD', ...)` antes de aplicar o regex.

### 5.5 Performance — `_request_with_retry` não usa session HTTP persistente

```python
def _request_with_retry(method, url, ...):
    ...
    resp = requests.request(method, url, **kwargs)
```

Cada chamada usa `requests.request` sem `Session`. Isso abre uma nova conexão TCP para cada requisição ao WordPress. Para publicação de posts com retry (até `WP_RETRY_COUNT` tentativas), cada retry abre nova conexão. Usar `requests.Session` com pooling de conexões reduziria significativamente a latência e o número de handshakes TLS.

---

## 6. `motor_rss/llm_router.py`

### 6.1 Bug de Lógica — `TIER_PHOTO_EDITOR` sem fallback para tiers econômicos

```python
_TIER_PHOTO_EDITOR_PROVIDERS = [
    ("openai:gpt-4o",    _call_openai_premium,  config.OPENAI_KEYS),
    ("claude:sonnet-4",  _call_claude_premium,  config.ANTHROPIC_KEYS),
    ("gemini:2.5-pro",   _call_gemini_premium,  config.GEMINI_KEYS),
    ("grok:grok-3",      _call_grok_premium,    config.GROK_KEYS),
]
```

O `TIER_PHOTO_EDITOR` só tem modelos premium. Se todos falharem (rate limit coletivo, outage simultâneo), retorna `(None, "")`. Em `publicador_consolidado.py`:

```python
photo_result, photo_provider = llm_router.call_llm(
    tier=llm_router.TIER_PHOTO_EDITOR,
    parse_json=True,
)
if photo_result and isinstance(photo_result, dict):
    explicit_gov = photo_result.get("imagem_busca_gov", "")
```

Se `photo_result` for `None`, `explicit_gov` fica `""`, e o curador usa `title[:50]` como query. Para notícias complexas, isso gera buscas ruins. Mas o pior é que isso **nunca é reportado como falha** — o sistema continua silenciosamente com query degradada.

### 6.2 Bug de Lógica — Circuit breaker compartilhado entre `generate_article` e `call_llm`

```python
_circuit_breaker: dict[str, dict] = {}
```

O dicionário de circuit breaker é global e compartilhado entre `generate_article` e `call_llm`. Se `generate_article` registrar 3 falhas para `openai`, o circuit breaker abrirá para `openai` em todo o sistema — incluindo nas chamadas de `TIER_PHOTO_EDITOR`. Isso significa que uma falha na geração de texto pode inadvertidamente bloquear a curadoria de imagens, que usa o mesmo provider.

### 6.3 Race Condition — `_circuit_breaker` e `_key_index` sem lock em multi-thread

```python
_circuit_breaker: dict[str, dict] = {}
_key_index: dict[str, int] = {}
```

Ambas são variáveis globais mutáveis sem proteção de lock. Em Python com GIL, operações simples de dict são thread-safe, mas a sequência `read → modify → write` em `_cb_record_failure` e `_next_key` não é atômica:

```python
state = _circuit_breaker.setdefault(provider, {"failures": 0, "blocked_until": 0})
state["failures"] += 1  # read-modify-write NÃO atômico
```

Dois threads podem ambos ler `failures = 2`, ambos incrementar para 3, e ambos registrar o breaker como aberto — inofensivo neste caso. Mas em cenários de reset (`_circuit_breaker.pop(provider)`), um thread pode estar iterando o dict enquanto outro remove uma chave — levantando `RuntimeError: dictionary changed size during iteration` se houver iteração em outro lugar.

### 6.4 Bug de API — `_call_gemini_premium` usa `f-string` para concatenar system + user prompt

```python
def _call_gemini_premium(system_prompt, user_prompt):
    response = client.models.generate_content(
        model="gemini-2.5-pro-preview-05-06",
        contents=f"{system_prompt}\n\n{user_prompt}",
    )
```

O SDK do Gemini (`google.genai`) suporta `system_instruction` separado. Ao concatenar o system prompt no conteúdo, a instrução de sistema perde seu papel especial de "persona" e é tratada como parte do prompt do usuário. Isso degrada a qualidade do output, especialmente para instruções que estabelecem papel e formato JSON.

### 6.5 Problema de Design — `content[:6000]` trunca artigos longos sem indicar corte

```python
user_prompt = config.LLM_REWRITE_PROMPT_TEMPLATE.format(
    content=content[:6000],
    ...
)
```

Artigos longos são truncados em 6000 caracteres sem aviso. O LLM recebe conteúdo incompleto e pode gerar reescritas com informações faltando (ex: conclusão do artigo, dados importantes no final). Não há ellipsis ou marcação de truncamento no prompt.

---

## 7. `gestor_wp.py`

### 7.1 Bug Crítico — `roteador_ia_imagem` chamada sem estar importada

```python
from curador_imagens_unificado import get_curador

# ...

if img_bytes:
    img_bytes = roteador_ia_imagem(comando_ia)  # NameError!
```

`roteador_ia_imagem` é definida em `roteador_ia.py`, mas **não está importada** em `gestor_wp.py`. A única importação é `from curador_imagens_unificado import get_curador`. Qualquer execução que chegue ao fallback de IA levantará `NameError: name 'roteador_ia_imagem' is not defined`.

**Este bug só não causa crash em produção porque `roteador_ia_imagem` retorna `None` imediatamente** (trava editorial ativa), mas o `NameError` acontece antes de verificar o resultado — a menos que a trava tenha sido aplicada, o que coloca `return None` como **primeira linha** do método, fazendo com que o `NameError` jamais seja atingido. Mas se a trava for removida ou revertida, o sistema crasha imediatamente.

### 7.2 Bug Crítico — Lógica de seleção de imagem invertida para fontes oficiais vs. não-oficiais

```python
is_oficial = autor_final != ID_REDACAO  # True se for fonte oficial

if not img_id:
    img_bytes = None
    if is_oficial:
        # Fonte oficial: só tenta IA se o prompt NÃO for "USE_ORIGINAL_IMAGE"
        if comando_ia and "USE_ORIGINAL_IMAGE" not in comando_ia.upper():
            img_bytes = roteador_ia_imagem(comando_ia)
    else:
        # Fonte não-oficial: tenta IA sempre
        if not comando_ia or "USE_ORIGINAL_IMAGE" in comando_ia.upper():
            titulo_base = dados.get('h1_title', 'Noticias')
            comando_ia = f"Imagem editorial, fotorrealista..."
        img_bytes = roteador_ia_imagem(comando_ia)
```

A lógica está **invertida**: para fontes **não-oficiais** (portais privados como G1, Folha), tenta gerar imagem por IA. Para fontes **oficiais** (governo, que são as mais sensíveis), só tenta IA se o LLM tiver gerado um prompt específico. O correto seria o oposto: fontes oficiais têm fotografias reais disponíveis e não precisam de IA; fontes não-oficiais precisam de curadoria, mas IA gera alucinações para fatos reais.

### 7.3 Falha Silenciosa — `buscar_e_subir_imagem_real` referenciada em `garantia_imagens.py` mas não existe em `gestor_wp.py`

O bloco injetado por `garantia_imagens.py` chama:
```python
id_raspado = buscar_e_subir_imagem_real(url_orig, auth_headers)
```

Mas `buscar_e_subir_imagem_real` não existe em `gestor_wp.py` — não há definição dessa função. O bloco injetado gerará `NameError` em produção sempre que uma fonte oficial for processada via este fluxo legado.

### 7.4 Bug de Lógica — `sys.path.insert(0, "/home/bitnami")` hardcoded

```python
sys.path.insert(0, "/home/bitnami")
from curador_imagens_unificado import get_curador
```

Path hardcoded para `/home/bitnami`. Em qualquer ambiente diferente de produção (staging, desenvolvimento local, containers Docker), esse import falha com `ModuleNotFoundError`.

### 7.5 Falha Silenciosa — Tags com menos de 3 caracteres silenciosamente ignoradas

```python
for tag in dados.get('tags', []):
    if len(tag) < 3: continue
```

Tags legítimas de 1-2 caracteres (ex: "IA", "5G", "TV") são silenciosamente descartadas. Não há log desse descarte.

### 7.6 Performance — Tag lookup faz request HTTP por tag, sem cache

```python
for tag in dados.get('tags', []):
    res_t = requests.post(f"{WP_URL}/tags", headers=AUTH_HEADERS, json={'name': tag})
    if res_t.status_code == 201: tag_ids.append(res_t.json().get('id'))
    elif res_t.status_code == 400:
        busca = requests.get(f"{WP_URL}/tags?search={tag}", headers=AUTH_HEADERS)
```

Para cada tag, faz 1-2 requests HTTP ao WordPress. Um post com 10 tags pode fazer 20 requests síncronos. Sem cache, sem batching, sem use de DB direto (como `wp_publisher.py` faz).

---

## 8. `motor_consolidado/publicador_consolidado.py`

### 8.1 Bug Crítico — `import requests as req` dentro de função, escondendo o módulo

```python
def publish_consolidated(article, sources):
    ...
    import requests as req
```

`requests` é importado localmente dentro da função com alias `req`. Isso funciona, mas:
1. É inconsistente — outros módulos importam no topo
2. Se houver um `ImportError` (ambiente sem requests instalado), o erro ocorre no meio da execução, não na inicialização
3. O alias `req` pode conflitar com variáveis locais futuras

### 8.2 Falha Silenciosa — Nenhum retry ao publicar o post

```python
resp = req.post(
    f"{config.WP_API_BASE}/posts",
    auth=(config.WP_USER, config.WP_APP_PASS),
    json=post_data,
    timeout=30,
)
```

Usa `req.post` direto em vez de `wp_publisher._request_with_retry`. Para matérias consolidadas (que são o conteúdo premium do site), uma falha de rede temporária resulta em perda permanente da publicação sem retry.

### 8.3 Bug de Lógica — Imagem oficial usada mesmo quando a `img_url` no campo `imagem` da fonte pode ser da notícia errada

```python
for src in sources:
    img_url = src.get("imagem", "")
    src_url = src.get("url", "")
    if img_url and is_official_source(src_url):
        media_id = upload_to_wordpress(img_url, ...)
        if media_id: return media_id
```

O campo `imagem` de `src` pode ser qualquer URL que o pipeline de ingestão salvou. Se a fonte oficial tiver salvo a URL de uma imagem genérica de capa do portal (banner, logo do ministério), essa imagem será usada como destaque da matéria consolidada sem verificação adicional de relevância.

### 8.4 Problema de Design — Fluxo de imagem em `publicador_consolidado.py` duplica lógica do `curador_imagens_unificado.py`

O `_get_image_for_consolidated` itera manualmente pelas fontes, tenta upload direto, e só então chama o curador. Isso duplica lógica de decisão que já existe no curador (Tier 1 para fontes oficiais). A lógica extra aqui pode divergir do curador ao longo do tempo.

### 8.5 Falha Silenciosa — `db.register_published` sem tratamento de falha

```python
db.register_published(
    post_id=post_id,
    source_url=source_urls[:2048],
    ...
)
```

Se `db.register_published` falhar (conexão DB perdida, timeout), a exceção não é capturada. O código está dentro do bloco `try/except Exception as e` que só loga `logger.error` mas já estará fora do `if resp.status_code in (200, 201)`. Verificar: se `db.register_published` lançar exceção fora do bloco try-except, o `post_id` nunca é retornado mesmo que o post tenha sido publicado com sucesso.

**Análise do fluxo:**
```python
try:
    resp = req.post(...)
    if resp.status_code in (200, 201):
        post_id = resp.json().get("id")
        db.register_published(...)  # Se isso lançar exceção...
        return post_id              # ...esta linha nunca executa
except Exception as e:
    logger.error(...)
return None  # post foi publicado mas retorna None!
```

**Post publicado com sucesso mas a função retorna `None`** — o sistema pensa que a publicação falhou e pode tentar novamente, gerando **posts duplicados**.

---

## 9. `roteador_ia.py`

### 9.1 Bug Crítico — Código morto após `return None`

```python
def roteador_ia_imagem(prompt_imagem):
    return None # [TRAVA EDITORIAL - DALL-E 3 DESATIVADO]

    chaves_imagem = [c for c in POOL_CHAVES if c["tipo"] == "openai"]
    for tentativa, config in enumerate(chaves_imagem):
        ...
```

Há código funcional após o `return None`. Embora esse seja o comportamento intencional (trava), o código morto a seguir usa `config` como nome de variável de loop — conflitando com o módulo `config` que seria importado em outros contextos. Se a trava for removida, o código morto **sobrescreve `config`** com um dict de configuração de API na primeira iteração do loop.

### 9.2 Bug de Modelo — `roteador_ia.py` usa `grok-beta` (obsoleto)

```python
modelo = "grok-beta"
```

`grok-beta` foi descontinuado pela xAI. Qualquer chamada ao Grok vai falhar com erro de modelo inexistente. O `llm_router.py` usa `grok-3` — há divergência entre o roteador legado e o novo.

### 9.3 Bug de Modelo — `roteador_ia.py` usa `gemini-1.5-pro` (desatualizado)

```python
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={chave}"
```

`gemini-1.5-pro` foi substituído por `gemini-2.0-flash` e `gemini-2.5-pro`. Embora ainda possa funcionar por algum tempo, diverge do `llm_router.py` que usa versões mais recentes.

### 9.4 Falha Silenciosa — `response_format=None` passado para providers não-OpenAI

```python
resp_format = {"type": "json_object"} if tipo == "openai" else None
res = cliente.chat.completions.create(
    ...
    response_format=resp_format,
    ...
)
```

Passar `response_format=None` para a API OpenAI (quando `tipo != "openai"`) pode causar comportamento inesperado dependendo da versão do SDK. O correto seria não passar o parâmetro quando `None`.

---

## 10. `trava_definitiva_dalle.py`

### 10.1 Bug Crítico — Regex de bloqueio não funciona se a função tiver parâmetros tipados

```python
codigo = re.sub(
    r'(def roteador_ia_imagem\([^)]*\):)',
    r'\1\n    return None # [TRAVA EDITORIAL - DALL-E 3 DESATIVADO]\n',
    codigo
)
```

Se `roteador_ia_imagem` tiver anotações de tipo nos parâmetros como `def roteador_ia_imagem(prompt_imagem: str) -> Optional[bytes]:`, o `[^)]*` do regex pode não capturar corretamente se houver tipos complexos com parênteses aninhados (ex: `Optional[Tuple[str, int]]` — embora improvável neste caso específico). Mais grave: o regex usa `[^)]*` que é **greedy** e captura tudo até o primeiro `)` — se houver funções como `def gerar_imagem(param: Callable[[], None]):`, o grupo `[^)]*` terminaria prematuramente no `]` antes do `)`.

### 10.2 Problema de Design — Trava por modificação de arquivo é frágil

A trava funciona modificando o código-fonte em disco. Isso tem vários problemas:
1. **Não é idempotente seguro**: se executado duas vezes, o segundo `return None` é adicionado novamente (o regex sempre encontra a definição), resultando em dois `return None` consecutivos (sintaxe válida mas ruim)
2. **Não sobrevive a `git pull`**: se o arquivo for revertido via controle de versão, a trava é removida
3. **Não é auditável**: não há como saber se a trava está ativa sem abrir o arquivo
4. **Não escala**: se um novo arquivo tiver geração de imagem por IA, precisa ser adicionado manualmente à lista

### 10.3 Bug de Lógica — `motor_avancado.py` na lista mas não existe verificação condicional

```python
arquivos = [
    '/home/bitnami/roteador_ia.py',
    '/home/bitnami/motor_avancado.py'
]
for arq in arquivos:
    if not os.path.exists(arq):
        continue
```

Se `motor_avancado.py` não existir, o script continua sem erro. Mas se existir e contiver uma função `gerar_imagem` com assinatura diferente do regex esperado, o bloqueio falha silenciosamente e a geração de IA **continua ativa** sem nenhum aviso.

---

## 11. `trava_imagens_ia.py`

### 11.1 Problema de Design — Regex `r'(def\s+gerar_imagem[^:]+:\s*\n)'` pode ser explorado

```python
codigo = re.sub(
    r'(def\s+gerar_imagem[^:]+:\s*\n)',
    r'\1    return None # [TRAVA EDITORIAL]\n',
    codigo
)
```

O padrão `[^:]+` captura qualquer coisa entre o nome da função e os dois-pontos. Se houver uma função como:
```python
def gerar_imagem_fallback(url: str, tipo: str = "jpg") -> None:
```

O `[^:]+` para no primeiro `:` — que aqui é a anotação de tipo `: str`. O regex captura apenas `(def\s+gerar_imagem_fallback(url` e falha em fazer match da definição completa. A trava **não é aplicada** para funções com type hints.

### 11.2 Bug de Lógica — Segundo regex não é necessário se o primeiro funcionar

```python
codigo = re.sub(
    r'(url_imagem\s*=\s*gerar_imagem_ia\([^)]+\))',
    r'url_imagem = None # [TRAVA EDITORIAL] IA desativada',
    codigo
)
```

Este segundo regex só funciona para o padrão exato `url_imagem = gerar_imagem_ia(...)`. Se o código usar `url = gerar_imagem_ia(...)` ou `resultado = gerar_imagem(...)`, não é capturado. É uma trava incompleta que cria falsa sensação de segurança.

---

## 12. `limpador_imagens_ia.py`

### 12.1 Bug Crítico — `obter_id()` faz upload incondicional sem verificar se download falhou

```python
def obter_id():
    res = requests.get(f"{WP_URL}/media?search=imagem-brasileira", headers=AUTH_HEADERS)
    if res.status_code == 200 and len(res.json()) > 0:
        return res.json()[0]['id']
    
    upd = requests.post(
        f"{WP_URL}/media",
        ...
        data=requests.get(URL_DEFAULT).content
    )
    return upd.json()['id']
```

Se `requests.get(URL_DEFAULT)` falhar (timeout, 404, rede), `.content` é bytes vazios ou a exceção é levantada. Sem `try/except`, uma falha de rede aqui:
- Ou levanta exceção não tratada (crashando o script inteiro)
- Ou faz upload de bytes vazios para o WordPress, que rejeita com 4xx

Mas `upd.json()['id']` é chamado sem verificar o status code — se o upload falhar, `.json()` pode lançar `JSONDecodeError` ou `KeyError`.

### 12.2 Bug Crítico — Loop paginado não trata erros HTTP em `posts`

```python
while True:
    posts = requests.get(f"{WP_URL}/posts?per_page=50&page={pag}", headers=AUTH_HEADERS).json()
    if not posts or type(posts) is dict: break
```

Se a API retornar erro HTTP (401, 500), `.json()` retorna um dict com `{"code": "rest_forbidden", ...}`. A condição `type(posts) is dict` captura isso e para o loop — mas sem logar o erro. **Todos os posts são silenciosamente ignorados** se houver um problema de autenticação ou servidor.

### 12.3 Bug de Lógica — `eh_ia` detecta imagens IA por palavras-chave frágeis

```python
return any(g in t for g in ["inteligência artificial", "inteligencia artificial", "dall-e", "editorial news photography", "no text"])
```

- `"editorial news photography"` é uma string muito genérica que pode estar em imagens reais de agências fotográficas
- `"no text"` é uma substring de "no texto" (português) — uma imagem real pode ter "no texto da reportagem" em seu caption
- Imagens IA geradas por Midjourney, Stable Diffusion ou outros modelos não seriam detectadas

### 12.4 Race Condition — Troca de imagem sem verificar se o post ainda usa o mesmo `featured_media`

```python
if requests.post(
    f"{WP_URL}/posts/{p['id']}",
    json={"featured_media": id_def},
    headers=AUTH_HEADERS
).status_code == 200:
    cor += 1
```

Entre a verificação `eh_ia(m_id)` e o `requests.post` de substituição, outro processo pode ter atualizado a imagem do post. Não há verificação de versão ou lock — o post pode ser atualizado com a imagem padrão mesmo que já tenha sido corrigido por outro processo.

### 12.5 Performance — N+1 requests: um GET por post para verificar `featured_media`

```python
for p in posts:
    m_id = p.get('featured_media', 0)
    if m_id != 0 and m_id != id_def and eh_ia(m_id):
```

`eh_ia(m_id)` faz um `requests.get(f"{WP_URL}/media/{m_id}")` para cada post. Para 1000 posts, são 1000 requests sequenciais ao WordPress. Sem paralelismo, sem cache de media_ids já verificados.

---

## 13. `revisor_imagens_antigos.py`

### 13.1 Bug Crítico — `update_post_thumbnail` modifica banco de dados diretamente mas não invalida cache do WordPress

```python
cur.execute(f"""
    INSERT INTO {prefix}postmeta (post_id, meta_key, meta_value)
    VALUES (%s, '_thumbnail_id', %s)
""", (post_id, media_id))
conn.commit()
```

Inserir diretamente em `wp_postmeta` bypassa o cache de objetos do WordPress (object cache / transients). Se o site usar Redis, Memcached ou qualquer object cache, o post continuará com a imagem antiga em cache até expirar. Em sites com cache agressivo, isso pode durar horas.

O correto seria usar a REST API do WordPress (`PATCH /posts/{id}` com `featured_media`) que invalida automaticamente os caches.

### 13.2 Resource Leak — Conexão DB não é fechada se `cur.execute` lançar exceção antes do `finally`

```python
def get_posts_without_images(limit, older_than_days):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (older_than_days, limit))
            posts = cur.fetchall()
            return posts
    finally:
        conn.close()
```

O `finally` garante fechamento mesmo com exceção. Porém, `get_db_connection()` é chamada sem `try/except` — se a conexão falhar (banco indisponível), a exceção se propaga para `main()` sem tratamento adequado, terminando o script com traceback.

### 13.3 Vulnerabilidade de Injeção SQL — `TABLE_PREFIX` interpolado diretamente

```python
prefix = config.TABLE_PREFIX
query = f"""
    SELECT ...
    FROM {prefix}posts p
    LEFT JOIN {prefix}postmeta thumb ...
"""
```

O `TABLE_PREFIX` é interpolado diretamente na query via f-string. Se `TABLE_PREFIX` vier de variável de ambiente e for comprometido (ex: `wp_; DROP TABLE wp_posts; --`), há **SQL injection**. Embora seja um valor de configuração interna, é boa prática usar apenas valores validados em queries.

### 13.4 Bug de Lógica — `generate_search_keywords` chamado com `content[:500]`, mas o curador recebe `content` completo

```python
keywords = generate_search_keywords(title, content[:500])
...
media_id, caption = curador.get_featured_image(
    html_content=content,  # conteúdo completo
    ...
    keywords=keywords      # keywords geradas de apenas 500 chars
)
```

As keywords são geradas de apenas os primeiros 500 caracteres do conteúdo, mas o curador recebe o conteúdo completo. Se informações relevantes estiverem no meio ou fim do artigo, as keywords serão subótimas.

---

## 14. `test_curador_imagens.py`

### 14.1 Problema de Design — Sem testes unitários reais (apenas integração)

Todos os testes fazem chamadas a APIs externas e ao WordPress real. Não há:
- Mocks para APIs
- Testes offline
- Fixtures de HTML pré-determinadas para Tier 1
- Assertions específicas (apenas `if result: print("✓")`)

### 14.2 Bug de Teste — `test_tier1_scraping` usa HTML com URL `.ebc.com.br` que falha `is_valid_image_url`

```python
TEST_HTML_WITH_IMAGE = '''
<meta property="og:image" content="https://agenciabrasil.ebc.com.br/sites/default/files/atoms/image/example.jpg">
'''
```

A URL `https://agenciabrasil.ebc.com.br/sites/default/files/atoms/image/example.jpg` contém `"atoms"` no path. O filtro de `is_valid_image_url` não bloqueia `atoms`, mas o path `/sites/default/files/atoms/image/example.jpg` contém `/files/` que satisfaz `content_patterns`. Porém, a função `_get_image_dimensions_from_headers` vai tentar fazer um request HTTP para essa URL de teste — que não existe — e retornará `None`. O teste pode passar ou falhar dependendo de se a URL inventada responde ou não.

### 14.3 Bug de Teste — `test_compatibility_functions` importa `search_unsplash` mas função faz request real

O teste chama `search_unsplash("Brazil landscape")` que faz um request HTTP real ao Unsplash. Isso torna o teste dependente de rede e quota da API, não sendo um teste unitário confiável.

### 14.4 Problema de Design — Resultados de teste não são assertions, são prints

```python
if result:
    print(f"  ✓ Extraiu og:image: {result[:80]}...")
    return True
else:
    print("  ✗ Falhou ao extrair og:image")
    return False
```

O arquivo de teste não usa `unittest`, `pytest` ou qualquer framework. Os "testes" são funções que retornam `True/False`. Não há `assert` — se um resultado inesperado for retornado (ex: URL errada), o teste passa igualmente.

---

## 15. `test_image_queries.py`

### 15.1 Problema de Design — `_detect_category` e `_generate_ai_queries` são métodos privados testados diretamente

```python
gen = get_query_generator()
cat = gen._detect_category(title, content)
queries = gen._generate_ai_queries(title, content, cat)
```

Testar métodos privados (prefixo `_`) diretamente viola o princípio de encapsulamento e torna os testes frágeis — qualquer refatoração interna quebra os testes.

### 15.2 Bug de Teste — Teste faz chamada real à API Gemini sem mock

`_generate_ai_queries` chama `requests.post` à API Gemini. Em ambiente de CI ou sem chave configurada, o teste falha com erro de autenticação não tratado.

### 15.3 Typo no Output — `"Categoria dectectada"` (duplo 'c')

```python
print(f"Categoria dectectada: {cat}")
```

`"dectectada"` está incorreto — deveria ser `"detectada"`. Embora cosmético, indica falta de revisão.

---

## 16. `garantia_imagens.py`

### 16.1 Bug Crítico — Injeção de código em `gestor_wp.py` gera código sintaticamente inválido sob certas condições

```python
padrao_func = r'(def\s+publicar_no_wordpress\s*\([^)]+\):)'
codigo = re.sub(padrao_func, r'\1\n' + bloco_garantia, codigo)
```

O `bloco_garantia` é uma string multiline inserida após a linha `def publicar_no_wordpress(...):`. O problema é que o bloco usa **indentação fixa de 4 espaços**, mas se `publicar_no_wordpress` estiver dentro de uma classe (indentação de 8+ espaços), o código injetado ficará com indentação errada e gerará `IndentationError`.

Adicionalmente, o `bloco_garantia` termina com:
```python
    if id_imagem_final:\n        dados['featured_media'] = id_imagem_final\n    # ------------------------------"""
```

O comentário `# ------------------------------` é o **delimitador de fim** do bloco, mas também é o fim da string Python. Se o regex `re.sub` de limpeza anterior falhar em remover uma injeção prévia, haverá código duplicado e potencialmente strings não fechadas.

### 16.2 Bug Crítico — `limpador_garantia` regex pode remover código legítimo

```python
codigo = re.sub(r'\s*# --- RASPADOR DE IMAGEM REAL ---.*?# ------------------------------', '', codigo, flags=re.DOTALL)
codigo = re.sub(r'\s*# --- GARANTIA DE IMAGENS.*?# ------------------------------', '', codigo, flags=re.DOTALL)
```

O padrão `.*?# ------------------------------` com `re.DOTALL` remove tudo até o próximo `# ------------------------------`. Se o código de `gestor_wp.py` usar este separador visual em outro lugar (comum em código Python formatado), o regex vai **excluir código legítimo** entre o início do bloco e o separador seguinte.

### 16.3 Problema de Design — Script modifica código-fonte em produção

`garantia_imagens.py` é um script que:
1. Abre `gestor_wp.py` para leitura
2. Modifica o código via regex
3. Sobrescreve o arquivo

Executar este script em produção **modifica código-fonte em execução**. Em Python, módulos já importados não são recarregados automaticamente — então:
- Se `gestor_wp` já estiver importado por um processo em execução, as mudanças não têm efeito imediato
- O próximo import do módulo (novo processo/worker) pega a versão modificada
- Há uma janela de tempo em que diferentes workers têm comportamentos diferentes

### 16.4 Falha Silenciosa — `obter_id_placeholder(headers)` swallows exceção

```python
def obter_id_placeholder(headers):
    try:
        ...
        return res.json()[0]['id']
    except: pass
    return 0
```

Exceção capturada com `except: pass` (bare except) sem logging. Se o WordPress retornar 403, o erro é silenciosamente ignorado e `0` é retornado como ID de imagem, que provavelmente não existe no WP.

---

## 17. Análise Transversal — Problemas Sistêmicos

### 17.1 Fragmentação Arquitetural — Três sistemas paralelos de imagem

O sistema tem **três implementações paralelas e incompatíveis** para obter imagens de posts:

| Sistema | Arquivo | Retorno | Método de Upload |
|---|---|---|---|
| **Legado** | `gestor_imagens.py` | `bytes` (conteúdo bruto) | Manual via `requests.post` |
| **Atual** | `curador_imagens_unificado.py` | `int` (media_id WP) | `upload_to_wordpress()` interno |
| **Inject** | `garantia_imagens.py` (injetado em gestor_wp.py) | `int` via `buscar_e_subir_imagem_real()` | Função que não existe |

Qualquer rota de código que passe pelo sistema legado ou pelo código injetado tem comportamento diferente do sistema atual. Bugs encontrados no curador unificado não afetam o código legado, e vice-versa.

---

### 17.2 DALL-E Lock — Frágil e parcialmente ineficaz

A trava DALL-E está espalhada em **dois arquivos separados** (`trava_definitiva_dalle.py` e `trava_imagens_ia.py`) que modificam arquivos diferentes. Para garantir que a trava esteja ativa, ambos precisam ter sido executados. Não há verificação centralizada de estado da trava.

**A trava já está ativa** em `roteador_ia.py` (linha 167: `return None`), mas:
1. `gestor_wp.py` ainda tenta chamar `roteador_ia_imagem` (linha 116) — resultaria em `NameError` se a função não estivesse importada
2. O código após o `return None` em `roteador_ia_imagem` usa `config` como nome de variável de loop — se a trava for removida, `import config` em outros módulos seria obscurecido

---

### 17.3 Hierarquia de Tiers — Execução fora de ordem no pipeline principal

O pipeline documentado é TIER 1 → 2 → 3A → 3B → 3C → 4 → 5. A execução real em `get_best_image_for_post` é:

```
TIER 1 (só fontes oficiais)
→ TIER 2 (Google CSE gov)
→ TIER 3C (Google CSE aberto) ← FORA DE ORDEM (deveria ser após 3B)
→ TIER 3A (Flickr)
→ TIER 3B (Wikimedia)
→ TIER 4 (Stock)
→ TIER 5 (Placeholder)
```

Tier 3C executa **antes** de 3A e 3B, contrariando a documentação. Isso provavelmente foi uma refatoração intencional (CSE aberto antes de Flickr), mas a nomenclatura não reflete a ordem real.

---

### 17.4 Ausência de Deduplicação — Mesma imagem pode ser enviada múltiplas vezes ao WordPress

Não há verificação se a `image_url` já foi enviada ao WordPress anteriormente. Para o `revisor_imagens_antigos.py` que processa posts antigos, se executado múltiplas vezes, a mesma imagem é enviada ao WordPress repetidamente, criando arquivos duplicados na biblioteca de mídia.

---

### 17.5 Timeout Global Insuficiente — `config.HTTP_TIMEOUT` aplicado inconsistentemente

`upload_to_wordpress` usa `timeout=30` (hardcoded) para o upload da imagem, mas usa `config.HTTP_TIMEOUT` para o download. Em `gestor_wp.py`, o upload usa apenas `timeout` implícito da biblioteca `requests` (indefinido, pode bloquear para sempre). Em `publicador_consolidado.py`, `timeout=30` para o post WP mas sem timeout no `_get_image_for_consolidated` ao fazer requests auxiliares.

---

### 17.6 Ausência de Validação de URL Final Antes do Upload

Nenhum dos sistemas verifica se a URL de imagem selecionada pelos Tiers **está acessível** antes de chamar `upload_to_wordpress`. Uma URL retornada pelo Google CSE pode:
- Retornar 404 (arquivo removido)
- Retornar 403 (proteção hotlink)
- Redirecionar para login/paywall
- Retornar HTML em vez de imagem

O `upload_to_wordpress` verifica `resp.status_code != 200` e `len(image_data) < 1000`, mas não verifica o `Content-Type` da resposta — uma página HTML de erro com status 200 e >1000 bytes seria aceita como "imagem" e enviada ao WordPress.

---

### 17.7 Falta de Observabilidade — Nenhuma métrica de qual Tier está sendo usado

Não há coleta de métricas sobre:
- Quantas vezes cada Tier é acionado
- Taxa de sucesso/falha por Tier
- Tempo médio por Tier
- Quais APIs estão sendo mais usadas

Sem isso, é impossível saber se o sistema está funcionando como esperado em produção (ex: "70% dos posts está usando placeholder" seria invisível sem métricas).

---

### 17.8 Paths hardcoded para `/home/bitnami`

Os seguintes arquivos têm `/home/bitnami` hardcoded:
- `gestor_wp.py`: `sys.path.insert(0, "/home/bitnami")`
- `publicador_consolidado.py`: `sys.path.insert(0, "/home/bitnami")` (duas vezes)
- `revisor_imagens_antigos.py`: `sys.path.insert(0, "/home/bitnami")` e `"/home/bitnami/motor_rss"`
- `test_curador_imagens.py`: `sys.path.insert(0, "/home/bitnami")`
- `test_image_queries.py`: `sys.path.append("/home/bitnami")`
- `trava_definitiva_dalle.py`: arquivos listados com path `/home/bitnami/`
- `trava_imagens_ia.py`: arquivos listados com path `/home/bitnami/`
- `garantia_imagens.py`: `caminho = '/home/bitnami/gestor_wp.py'`

Qualquer migração de servidor, containerização ou ambiente de staging/dev **quebra todos esses imports** simultaneamente.

---

## Resumo de Severidade

| Severidade | Bugs | Exemplos |
|---|---|---|
| 🔴 **Crítico** (produção quebrada) | 12 | `NameError: roteador_ia_imagem` em gestor_wp; `buscar_e_subir_imagem_real` inexistente; `db.register_published` gerando post duplicado; FLICKR_GOV_USERS inválidos; Tier 3C duplicando Tier 2 |
| 🟠 **Alto** (comportamento incorreto) | 14 | Tier 1 pulado para fontes comerciais; lógica RGBA invertida; `has_content_pattern` nunca usada; regex de bloqueio IA não funciona com type hints; token CSE quota desperdiçada |
| 🟡 **Médio** (falha silenciosa/degradação) | 11 | meta `alt_text` não salvo em erros; sem retry no publicador_consolidado; circuit breaker compartilhado; slugs com acentos errados |
| 🔵 **Baixo** (qualidade/manutenção) | 9 | Paths hardcoded; sem métricas; testes sem asserts; código morto; logs com `print` em vez de logging |

**Total identificado: 46 problemas distintos**

---

*Análise concluída em 20/03/2026. Este documento serve como base para o redesenho do sistema de curadoria de imagens.*
