# Auditoria de Bugs — Roteadores, Configs e Regras  
**Sistema:** Brasileira.news — Automação de notícias  
**Data:** 20 de março de 2026  
**Escopo:** 17 arquivos de produção analisados linha a linha

---

## Índice

1. [roteador_ia.py](#1-roteador_iapy)
2. [motor_rss/llm_router.py](#2-motor_rssllm_routerpy)
3. [config_geral.py](#3-config_geralpy)
4. [config_categorias.py](#4-config_categoriasspy)
5. [motor_rss/config.py](#5-motor_rssconfigpy)
6. [motor_consolidado/config_consolidado.py](#6-motor_consolidadoconfig_consolidadopy)
7. [regras_editoriais.py](#7-regras_editoriaispy)
8. [regras_seo.py](#8-regras_seopy)
9. [regras_arte.py](#9-regras_artepy)
10. [catalogo_fontes.py](#10-catalogo_fontespy)
11. [catalogo_scrapers.py](#11-catalogo_scraperspy)
12. [catalogo_gov.py](#12-catalogo_govpy)
13. [catalogo_midia.py](#13-catalogo_midiapy)
14. [catalogo_nicho.py](#14-catalogo_nichopy)
15. [agente_revisor.py](#15-agente_revisorpy)
16. [agente_newspaper.py](#16-agente_newspaperpy)
17. [construir_knowledge_base.py](#17-construir_knowledge_basepy)
18. [Conflitos Cross-File (Visão Sistêmica)](#18-conflitos-cross-file-visão-sistêmica)

---

## 1. `roteador_ia.py`

### 🔴 Bugs Críticos

**BUG-001 — Código morto inacessível em `roteador_ia_imagem` (linha 167)**  
A função retorna `None` na **linha 167** com o comentário `[TRAVA EDITORIAL - DALL-E 3 DESATIVADO]`. O restante do corpo da função (linhas 170–186), incluindo toda a lógica de geração de imagem via DALL-E 3, **nunca é executado**. O Python para na instrução `return None` e ignora o código subsequente. Se a intenção for apenas desativar temporariamente, o padrão correto seria usar uma flag de configuração (`ENABLE_IMAGE_GEN = False`), não código morto. Qualquer desenvolvedor que tente "reativar" essa função removendo o `return None` descobrirá que o código abaixo ainda funciona — mas estará invisível para qualquer linter ou revisor desatento.

**BUG-002 — Dependência de `config_chaves` não documentada em nenhum arquivo do projeto**  
A linha 20 importa `from config_chaves import POOL_CHAVES`. Esse arquivo **não está no escopo dos 17 arquivos analisados** e não existe nos catálogos do workspace. Se `config_chaves.py` não existir no diretório de execução, o módulo falha silenciosamente com `ImportError` durante o import, derrubando qualquer motor que dependa deste roteador. O `agente_newspaper.py` usa `sys.path.insert(0, '/home/bitnami')` e importa diretamente `from roteador_ia import roteador_ia_texto` — portanto esse bug se propaga.

**BUG-003 — `roteador_ia_texto` não tem fallback quando retorna `None`**  
Quando todos os provedores falham, a função retorna `None` (linha 162). O chamador em `agente_newspaper.py` (linha 217) não verifica se o retorno é `None` antes de chamar `json.loads(resultado)` — embora exista um `if resultado:` na linha 219. Porém, se o retorno for uma string vazia `""`, o `if resultado:` falha silenciosamente (string vazia é falsy), e a função retorna `{"erro": "Falha em todos os motores de IA"}` sem nenhum log estruturado de diagnóstico.

### 🟡 Problemas de Design

**DESIGN-001 — Dois roteadores de IA paralelos sem coordenação**  
O sistema tem `roteador_ia.py` (legado, lê de `POOL_CHAVES`) e `motor_rss/llm_router.py` (novo, lê de `config.OPENAI_KEYS` etc.). São sistemas completamente separados, com modelos diferentes, sem lógica de delegação entre si. O `agente_newspaper.py` usa o roteador legado; o motor RSS usa o novo. Isso significa que **circuit breaker, rotação de chaves e métricas de falha são independentes** — uma chave OpenAI pode estar no circuit breaker do `llm_router.py` e ainda ser tentada pelo `roteador_ia.py`.

**DESIGN-002 — Temperatura hardcoded em 0.3 para todos os tipos de conteúdo**  
A variável `TEMPERATURA = 0.3` (linha 26) é aplicada indiscriminadamente a todas as chamadas: geração de artigos jornalísticos, classificação editorial, triagem de conteúdo. Para tarefas de classificação/triagem, temperatura 0.0 ou 0.1 seria mais adequada. Para redação criativa/jornalística, 0.5–0.7 produziria resultados mais variados e menos repetitivos.

**DESIGN-003 — Ausência de `response_format: json_object` para Grok e Perplexity**  
Na linha 66, `resp_format = {"type": "json_object"} if tipo == "openai" else None`. Grok e Perplexity recebem `None` como `response_format`, dependendo apenas da instrução no prompt `"Retorne OBRIGATORIAMENTE um JSON valido"`. Ambas as APIs suportam JSON mode; não usá-lo aumenta a taxa de falha de parse.

**DESIGN-004 — Modelo Grok desatualizado**  
Linha 54: `modelo = "grok-beta"`. O `llm_router.py` já usa `grok-3`. O roteador legado continua usando um modelo beta descontinuado ou de capacidade inferior.

**DESIGN-005 — Modelo Perplexity desatualizado**  
Linha 60: `modelo = "llama-3.1-sonar-large-128k-chat"`. A Perplexity descontinuou esse endpoint em favor de `llama-3.1-sonar-large-128k-online` e posteriormente de `sonar-pro`. Chamadas a esse modelo resultam em erro 404 ou fallback automático da API.

**DESIGN-006 — Ausência de `max_tokens` nas chamadas OpenAI e Grok**  
As chamadas via OpenAI SDK no roteador legado (linha 70) não definem `max_tokens`. O `llm_router.py` define `max_tokens=4096` consistentemente. Sem esse parâmetro, artigos longos podem ser truncados por limite de resposta padrão da API (varia por modelo).

### 🔒 Problemas de Segurança

Nenhuma credencial exposta neste arquivo diretamente; o risco está na dependência de `config_chaves.py` (veja `config_geral.py`).

---

## 2. `motor_rss/llm_router.py`

### 🔴 Bugs Críticos

**BUG-004 — Circuit breaker não é thread-safe**  
O dicionário `_circuit_breaker` é um objeto global (linha 26) mutado por `_cb_record_failure`, `_cb_record_success` e `_cb_is_open` sem nenhum mecanismo de lock (`threading.Lock`). Em ambientes com múltiplas threads (qualquer servidor WSGI/ASGI ou `concurrent.futures.ThreadPoolExecutor`), há race condition: duas threads podem ler `state["failures"] == 2` simultaneamente, ambas incrementarem para `3`, e ambas gravarem `blocked_until` — resultando em dados inconsistentes. O problema se agrava em `_cb_is_open`, que lê e deleta do dicionário sem lock:

```python
# Thread A lê: state["failures"] >= threshold → True
# Thread B remove: _circuit_breaker.pop(provider)
# Thread A tenta acessar state["blocked_until"] → KeyError ou estado stale
```

**BUG-005 — `_rotate_key` não tem efeito no `generate_article` e `call_llm`**  
A função `_rotate_key` (linha 77) incrementa `_key_index[provider]`. No entanto, `_next_key` (linha 68–73) **sempre lê e incrementa o índice** a cada chamada. Isso significa que após um rate limit, `_rotate_key` força +1 no índice, mas `_next_key` vai adicionar +1 novamente na próxima chamada — pulando uma chave a mais do que deveria, e potencialmente fazendo round-robin fora de sincronismo. Em um pool de 2 chaves com `_key_index=1`:
- `_rotate_key` → `_key_index=2`
- Próxima `_next_key` → `idx = 2 % 2 = 0`, retorna chave[0], define `_key_index=3`
- Isso está correto numericamente, mas em pool de 3 chaves: chave[1] é completamente pulada após rotate.

**BUG-006 — `call_llm` chama `_cb_record_success` antes de validar a resposta**  
Na função `call_llm` (linha 573), o sucesso do circuit breaker é registrado **imediatamente após o retorno da API**, sem validar se a resposta é útil. Comparar com `generate_article`, que valida via `_validate_response` antes de registrar sucesso. Em `call_llm`, uma resposta malformada ou semanticamente inválida ainda reseta o circuit breaker — fazendo o sistema acreditar que o provider está saudável quando pode estar retornando lixo.

**BUG-007 — `_validate_response` registra warning mas não impede `call_llm` de continuar**  
Em `generate_article`, quando `_validate_response(data)` retorna `False`, o código continua para o próximo provider. Em `call_llm` com `parse_json=True`, `_parse_llm_json` é chamado mas `_validate_response` nunca é invocado — portanto um JSON que passe o parse mas esteja faltando campos obrigatórios (`titulo`, `conteudo`, etc.) será retornado como dado válido ao chamador.

### 🟡 Problemas de Design

**DESIGN-007 — Circuit breaker baseado em nome de provider (sem modelo)**  
O `cb_name = provider_name.split(":")[0]` (linha 475/560) usa apenas o prefixo. Isso significa que `openai:gpt-4o` e `openai:gpt-4o-mini` compartilham o mesmo circuit breaker. Se o `gpt-4o-mini` (TIER 2) falhar 3 vezes, o `gpt-4o` (TIER 1) também será bloqueado — e vice-versa. Dois modelos diferentes do mesmo provider têm limites e comportamentos distintos.

**DESIGN-008 — Gemini usa mesma key pool em TIER 1 (Premium) e TIER 2 (Standard)**  
`_call_gemini_premium` e `_call_gemini` ambas chamam `_next_key("gemini", config.GEMINI_KEYS)`. O índice de rotação é compartilhado. Chamadas premium e standard competem pelo mesmo pool de chaves sem separação de quota, prejudicando a qualidade do roteamento premium.

**DESIGN-009 — `_TIER_MAP` usa referências de lista mutáveis**  
`_TIER_MAP` referencia as listas `_TIER1_PROVIDERS`, `_TIER2_PROVIDERS`, etc. diretamente. Se qualquer código externo modificar essas listas em runtime, o mapa inteiro é afetado. Para constantes de configuração, o ideal seria usar tuplas imutáveis ou congelar o dicionário.

**DESIGN-010 — `generate_article` trunca conteúdo em 6000 chars sem aviso**  
Linha 465: `content[:6000]`. Para artigos longos vindos de portais como G1, Folha ou Reuters, truncar em 6000 caracteres pode cortar o texto no meio de uma frase ou eliminar a parte mais relevante do artigo. Não há log de aviso quando truncamento ocorre.

**DESIGN-011 — `classify_tier` ignora `content_length` e `score` nos parâmetros**  
A assinatura aceita `content_length` e `score` (linhas 398–400), mas o corpo da função (linhas 420–431) nunca usa essas variáveis. Os parâmetros estão documentados como critérios de classificação mas são silenciosamente ignorados. Um artigo longo de alta pontuação de uma fonte institucional nunca será promovido ao TIER 1.

**DESIGN-012 — `_INSTITUTIONAL_THEMES` contém apenas `"governo"` — muito restrito**  
```python
_INSTITUTIONAL_THEMES = {"governo"}
```
Temas como `"saude"`, `"educacao"`, `"seguranca"`, `"legislativo"`, `"judiciario"` não estão na lista. Artigos de `catalogo_fontes.py` com `tema` diferente de `"governo"` — mesmo sendo fontes governamentais — irão parar no TIER 1 se o nome da fonte não bater em `_INSTITUTIONAL_SOURCES`.

**DESIGN-013 — Comentário do cabeçalho diz "3 TIERS" mas o arquivo define 6 tiers**  
Linha 2: `"Roteamento multi-LLM com 3 TIERS de qualidade"`. O código define `TIER_PREMIUM=1`, `TIER_STANDARD=2`, `TIER_ECONOMY=3`, `TIER_CURATOR`, `TIER_CONSOLIDATOR`, `TIER_PHOTO_EDITOR`. Documentação incorreta pode induzir erros em novos desenvolvedores.

### 🔒 Problemas de Segurança

**SEC-001 — Estado global de circuit breaker e key rotation persiste entre requisições**  
`_circuit_breaker` e `_key_index` são variáveis de módulo. Em produção com workers WSGI reiniciados entre deploys, o estado é perdido — mas dentro de uma sessão de processo, um burst de falhas pode bloquear providers para **todas** as requisições subsequentes, não apenas a que falhou. Isso pode causar degradação de serviço global por um evento localizado.

---

## 3. `config_geral.py`

### 🔴 Bugs Críticos

**BUG-008 — `NameError` fatal: `base64` não importado**  
```python
# Linha 30
AUTH_HEADERS = {
    'Authorization': f'Basic {base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()}'
}
```
O módulo `base64` **não é importado em nenhum ponto do arquivo**. Ao importar `config_geral`, Python lançará `NameError: name 'base64' is not defined` — derrubando imediatamente `agente_revisor.py` que faz `from config_geral import WP_URL, AUTH_HEADERS`. Este é um bug fatal que impede toda a execução do agente revisor.

**BUG-009 — Senha hardcoded como fallback em variável de ambiente**  
```python
# Linha 22
WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")
```
A senha de aplicação do WordPress está **hardcoded como valor padrão**. Se a variável de ambiente `WP_APP_PASS` não estiver definida, a senha real de produção será usada diretamente do código-fonte. Qualquer pessoa com acesso ao repositório tem acesso administrativo ao WordPress. **Esse valor deve ser imediatamente revogado no painel WordPress.**

### 🔒 Problemas de Segurança

**SEC-002 — Credencial WordPress exposta no código-fonte (mesma senha que BUG-009)**  
`"nWgboohRWZGLv2d7ebQgkf80"` é uma senha de aplicação WordPress válida codificada diretamente no código. Em um repositório Git, isso é registrado no histórico permanentemente mesmo que removido do arquivo atual. Requer revogação imediata no painel WP > Usuários > Senhas de Aplicativos.

**SEC-003 — `config_geral.py` diverge de `motor_rss/config.py` na variável de senha**  
`config_geral.py` usa `WP_APP_PASSWORD` (com default hardcoded), enquanto `motor_rss/config.py` usa `WP_APP_PASS = os.getenv("WP_APP_PASS", "")` (sem fallback inseguro). Dois módulos diferentes lendo a mesma variável de ambiente com nomes de variável Python distintos e comportamentos distintos de fallback. Risco de inconsistência silenciosa.

---

## 4. `config_categorias.py`

### 🟡 Conflitos de Configuração

**CONF-001 — `CAT_TURISMO` (ID 80) existe no config mas ausente de `VALID_CATEGORIES` em `motor_rss/config.py`**  
A lista `VALID_CATEGORIES` em `motor_rss/config.py` não inclui `"Turismo"`. Se o LLM escolher `"Turismo"` como categoria de um artigo (que é válido pelo banco de dados), a validação do motor RSS rejeitará a categoria como inválida. As categorias válidas no motor RSS são uma lista diferente das categorias reais do WordPress.

**CONF-002 — `CAT_SEGURANÇA` (Defesa) ausente do `config_categorias.py`**  
`motor_rss/config.py` inclui `"Segurança & Defesa"` em `VALID_CATEGORIES` (linha 144), mas não existe nenhuma constante `CAT_SEGURANCA` ou `CAT_DEFESA` em `config_categorias.py`. O LLM pode sugerir essa categoria, mas não há ID WordPress correspondente mapeado.

**CONF-003 — `ID_REDACAO = 4` duplicado**  
Tanto `config_categorias.py` (linha 234) quanto `motor_consolidado/config_consolidado.py` (linha 218) definem `ID_REDACAO = 4`. Não é um bug enquanto os valores forem iguais — mas é um ponto de manutenção frágil: mudar o ID em um arquivo não atualiza o outro.

**CONF-004 — Categoria ID 77 ausente (lacuna na sequência)**  
A sequência de IDs vai de 76 (`CAT_SOCIEDADE`) para 78 (`CAT_INFRAESTRUTURA`), pulando o ID 77. Pode indicar uma categoria deletada no WordPress que deixou uma lacuna. Se posts ainda referenciarem o ID 77, o WordPress os moverá para "Uncategorized" (ID 1) silenciosamente.

**CONF-005 — `CAT_TELECOM` usa ID 137, mas sequência das subcategorias de Tecnologia vai de 129–134**  
As subcategorias de tecnologia são 130, 131, 132, 133, 134, depois salta para 137 (`CAT_TELECOM`). IDs 135 e 136 são `CAT_AGRO` e `CAT_MEIO_AMBIENTE` (categorias macro). O ID 137 para `CAT_TELECOM` (subcategoria de 129) é numericamente posterior às macros, sugerindo que foi adicionado depois e pode não estar corretamente aninhado no WordPress como subcategoria de 129.

### 🟡 Problemas de Design

**DESIGN-014 — Constantes exportadas via `*` — risco de colisão de namespace**  
`catalogo_fontes.py`, `catalogo_gov.py`, `catalogo_midia.py`, `catalogo_nicho.py` e `agente_revisor.py` fazem `from config_categorias import *`. Com `import *`, qualquer nova variável adicionada ao config pode sobrescrever silenciosamente uma variável local com o mesmo nome nos módulos importadores.

---

## 5. `motor_rss/config.py`

### 🟡 Conflitos de Configuração

**CONF-006 — `WP_URL` aponta para domínio raiz, não para a API**  
`motor_rss/config.py`: `WP_URL = os.getenv("WP_URL", "https://brasileira.news")` e `WP_API_BASE = f"{WP_URL}/wp-json/wp/v2"`.  
`config_geral.py`: `WP_URL = "https://brasileira.news/wp-json/wp/v2"` (já inclui o path).  
Esses dois valores têm **semânticas completamente diferentes** apesar do mesmo nome. Módulos que importam de `config_geral` e usam `WP_URL` diretamente como URL base da API funcionam; módulos do `motor_rss` usam `WP_API_BASE`. Se algum módulo misturar imports, chamadas à API apontarão para URLs erradas.

**CONF-007 — `_load_keys` suporta KEY_2 a KEY_9 mas para em 9**  
```python
for i in range(2, 10):  # KEY_2 até KEY_9
```
O padrão de variáveis de ambiente suportado é limitado a 9 chaves por provider. Se o operador adicionar `OPENAI_API_KEY_10` ou superior, ela **será silenciosamente ignorada**. O código deveria iterar até encontrar a primeira ausente, não até um número fixo arbitrário.

**CONF-008 — `MIN_CONTENT_WORDS = 200` em `motor_rss/config.py` vs `150` em `motor_consolidado`**  
`motor_rss/config.py` linha 122: `MIN_CONTENT_WORDS = 200`.  
`motor_consolidado/config_consolidado.py` linha 201: `MIN_CONTENT_WORDS = 150`.  
Os dois motores têm limiares diferentes para considerar conteúdo válido. Artigos com 150–199 palavras passarão no consolidado mas serão rejeitados pelo RSS.

**CONF-009 — `VALID_CATEGORIES` são strings descritivas, não IDs**  
O LLM é instruído a escolher uma categoria da lista `VALID_CATEGORIES` (strings como `"Política & Poder"`), mas o sistema precisa de IDs WordPress (integers como `[71]`). Não há mapeamento automático entre o nome retornado pelo LLM e o ID numérico correspondente neste arquivo de config. A tradução precisa acontecer em algum ponto do pipeline — se não houver, os posts ficam sem categoria.

---

## 6. `motor_consolidado/config_consolidado.py`

### 🔴 Bugs Críticos

**BUG-010 — Import do `.env` hardcoded em path absoluto Bitnami**  
```python
# Linha 18
load_dotenv(_BITNAMI / "motor_rss" / ".env")
```
O path `/home/bitnami/motor_rss/.env` é hardcoded. Se a aplicação for movida, executada em Docker, staging, ou qualquer ambiente que não seja a VM Bitnami original, o `.env` não será encontrado, e **todas as variáveis de ambiente (DB, API keys, WP credentials) ficarão vazias**. O motor consolidado falhará silenciosamente sem nenhum erro de inicialização, pois `os.getenv` retorna defaults vazios.

**BUG-011 — `sys.path` modificado em módulo de configuração**  
Linhas 12–14:
```python
sys.path.insert(0, str(_BITNAMI / "motor_rss"))
sys.path.insert(0, str(_BITNAMI / "motor_scrapers"))
sys.path.insert(0, str(_BITNAMI))
```
Modificar `sys.path` dentro de um arquivo de configuração é prática fortemente desaconselhada. Qualquer módulo que importe `config_consolidado` inadvertidamente altera o path de import de toda a aplicação, podendo causar shadowing de módulos padrão da biblioteca Python ou conflitos de versão.

### 🟡 Conflitos de Configuração

**CONF-010 — `SIMILARITY_THRESHOLD = 0.45` é muito permissivo para deduplicação**  
Um threshold de 0.45 (45% de similaridade) significa que artigos com menos da metade das palavras em comum serão tratados como duplicatas. Para notícias que cobrem o mesmo evento com ângulos diferentes (ex: o mesmo plenário coberto pelo G1 e pela CNN Brasil), isso pode eliminar cobertura diversificada legítima.

**CONF-011 — `MIN_SOURCES_PER_TOPIC = 1` permite consolidação de fonte única**  
Uma matéria consolidada teoricamente deveria juntar múltiplas fontes. Com mínimo de 1 fonte, o consolidado pode gerar um artigo "consolidado" a partir de uma única matéria — que é semanticamente equivalente a uma reescrita simples, desperdiçando o TIER_CONSOLIDATOR mais caro.

**CONF-012 — `TEMAS_PROIBIDOS` no consolidado vs ausência de lista equivalente no motor RSS**  
O motor consolidado proíbe `["fofoca", "celebridade", "reality show", "bbb", "big brother"]`. O motor RSS não tem lista equivalente e pode publicar conteúdo dessas categorias normalmente. Política editorial inconsistente entre os dois motores.

**CONF-013 — `UOL mais_lidas_url` usa HTTP não HTTPS**  
```python
# Linha 157
"rss_url": "http://rss.uol.com.br/feed/noticias.xml"
```
URL HTTP em 2026 é problemático: muitos servidores redirecionam automaticamente para HTTPS sem avisar, e bibliotecas como `requests` seguem o redirect, mas a latência aumenta. Se o servidor UOL rejeitar HTTP diretamente, o feed falha.

---

## 7. `regras_editoriais.py`

### 🟡 Problemas de Prompt Engineering

**PROMPT-001 — Regras editoriais são um sub-conjunto do prompt em `motor_rss/config.py`**  
O `regras_editoriais.py` e o `LLM_REWRITE_PROMPT_TEMPLATE` em `motor_rss/config.py` cobrem o mesmo terreno (lide, presunção de inocência, CVV, anti-alucinação, atribuição de fonte), mas com textos diferentes e nuances distintas. Se um motor usa `regras_editoriais.py` e outro usa o prompt de `motor_rss/config.py`, as regras não são as mesmas — gerando inconsistência editorial entre os motores.

**PROMPT-002 — Regra CVV inadequada para contexto jornalístico brasileiro**  
```
3.2. "APENAS SE a notícia tratar explicitamente de suicídio ou depressão profunda"
```
O Conselho Nacional de Saúde e o Manual de Cobertura de Saúde Mental da OPAS recomendam incluir o CVV também em coberturas de **tentativas de suicídio** e **transtornos mentais graves**, não apenas em casos explícitos. A regra atual é mais restritiva que as melhores práticas. Adicionalmente, o número correto do CVV é **188** (correto no prompt principal do `motor_rss/config.py`) mas a regra no `regras_editoriais.py` menciona apenas o telefone sem especificar o número, dependendo do LLM memorizar "188".

**PROMPT-003 — Ausência de regra sobre anonimização de vítimas e menores**  
Nenhuma das regras editoriais menciona a obrigação de anonimizar vítimas de violência sexual, menores de idade ou testemunhas protegidas — obrigação legal estabelecida pelo ECA (Lei 8.069/90) e pelo Código de Ética dos Jornalistas Brasileiros. Isso expõe o portal a risco jurídico.

**PROMPT-004 — Instrução de formatação "Moedas: R$ antes do número" conflita com texto original**  
A regra de formatação de moedas (`R$ 1,5 milhão`) é específica para o Real. Quando um artigo fonte tratar de outras moedas (USD, EUR, BTC), o LLM pode converter equivocadamente ou manter o símbolo original sem padronização, pois a instrução só cobre o Real.

---

## 8. `regras_seo.py`

### 🟡 Problemas de Prompt Engineering

**PROMPT-005 — JSON de exemplo no prompt usa `{{` e `}}` mas não está em f-string corretamente protegido**  
```python
def obter_diretrizes_seo():
    return f"""
    ...
    {{
      "h1_title": "...",
    }}
    """
```
O uso de `f"""..."""` com `{{}}` para escapar chaves literais está correto tecnicamente — mas isso significa que o JSON de exemplo no retorno da função terá `{` e `}` literais, o que é o comportamento desejado. No entanto, **a chave do JSON retornado é `h1_title`**, enquanto o `LLM_REWRITE_PROMPT_TEMPLATE` em `motor_rss/config.py` usa `titulo` como chave JSON. Há uma inconsistência de nomenclatura entre as regras SEO e o schema real de saída do LLM.

**PROMPT-006 — `VALID_CATEGORIES` do motor RSS não coincide com as categorias nas regras SEO**  
`regras_seo.py` instrui sobre taxonomia de tags, mas não menciona a lista específica de categorias válidas. O LLM pode escolher categorias que não existem no WordPress, e o pipeline pode não detectar isso antes de tentar publicar.

**PROMPT-007 — Limite de `seo_title` em 60 caracteres é baseado em padrão Google defasado**  
O Google expandiu o limite visual de títulos SERP para 600px de largura (equivalente a ~65–70 caracteres em Roboto regular). O limite de 60 caracteres era válido até 2014. Atualmente, Yoast SEO, RankMath e Google Search Console aceitam até 60–70 caracteres. Reduzir a 60 chars desperdiça espaço de SEO.

**PROMPT-008 — `meta_description` de 155 chars é ligeiramente abaixo do atual recomendado**  
Google tipicamente exibe até 160 caracteres em desktop. Limitar a 155 é conservador mas não errado — porém o `motor_rss/config.py` instrui o mesmo: `"seo_description: máx 155 caracteres"`. Consistente, mas poderia usar até 158 para maximizar aproveitamento.

**PROMPT-009 — Ausência de instrução sobre Schema Markup / JSON-LD**  
Não há nenhuma regra sobre geração de `Article` schema (JSON-LD), que é um fator de ranking relevante para Google News e Google Discover. Para um portal de notícias, omitir isso é uma perda SEO significativa.

**PROMPT-010 — `social_copy` instrui "copy para WhatsApp ou Instagram"** 
As regras SEO instruem geração de `social_copy`, mas o campo não aparece na lista de campos obrigatórios em `_validate_response` do `llm_router.py`. Se o LLM o omitir, a validação passa mesmo assim.

---

## 9. `regras_arte.py`

### 🟡 Problemas de Prompt Engineering

**PROMPT-011 — Regra de arte usa `"prompt_imagem"` mas o schema real usa `"imagem_busca_gov"` e `"imagem_busca_commons"`**  
`regras_arte.py` instrui o LLM a preencher a chave `"prompt_imagem"` com `"USE_ORIGINAL_IMAGE"` ou um prompt de IA. Porém, o `LLM_REWRITE_PROMPT_TEMPLATE` em `motor_rss/config.py` instrui o LLM a retornar `imagem_busca_gov`, `imagem_busca_commons`, `block_stock_images` e `legenda_imagem` — sem `"prompt_imagem"`. **As duas regras contradizem completamente o schema de saída esperado.** Se `regras_arte.py` for injetado junto com o prompt principal, o LLM terá instruções contraditórias.

**PROMPT-012 — Lógica de "USE_ORIGINAL_IMAGE" não está implementada no motor**  
A regra instrui: `"Preencha prompt_imagem EXATAMENTE com 'USE_ORIGINAL_IMAGE'"`. Mas não há nenhum código nos arquivos analisados que leia esse valor e dispare um "raspador" de imagem original. A instrução pressupõe funcionalidade que não existe no pipeline analisado.

**PROMPT-013 — Instrução de cor de branding está hardcoded no prompt**  
`"Color palette featuring brand accents of deep petrol blue (#1f4452) and light blue (#4e8fb1)"`. Se o branding do site mudar, essa instrução precisa ser atualizada manualmente em `regras_arte.py`. Deveria ser uma variável de configuração.

**PROMPT-014 — Regras de arte e regras editoriais são fornecidas como módulos separados mas não há orquestração clara**  
`regras_editoriais.py`, `regras_seo.py` e `regras_arte.py` são funções independentes que retornam strings. Não há módulo de composição que as una em um único system prompt consistente. Cada motor que precisar de todas as regras precisa concatená-las manualmente — gerando inconsistências entre motores.

---

## 10. `catalogo_fontes.py`

### 🟡 Problemas de Catálogo

**CAT-001 — Fontes RT e CGTN sem indicação editorial de origem**  
```python
{"nome": "RT", "url": "https://www.rt.com/rss/news/", "cat_id": CAT_INTERNACIONAL},
{"nome": "CGTN", "url": "https://www.cgtn.com/subscribe/rss/section/world.xml", "cat_id": CAT_INTERNACIONAL},
{"nome": "TASS", "url": "https://tass.com/rss/v2.xml", "cat_id": CAT_INTERNACIONAL},
{"nome": "KCNA", "url": "https://kcnawatch.org/feed/", "cat_id": CAT_INTERNACIONAL},
```
RT (Russia Today), CGTN (China Global TV), TASS e KCNA são veículos de propaganda estatal conhecidos, com baixa credibilidade jornalística. Incluí-los sem flag editorial expõe o portal a republicar desinformação. Não há campo `"credibilidade"`, `"editorial_note"` ou `"requires_extra_validation"` no schema de feed.

**CAT-002 — `Sputnik Brasil` aponta para URL não-oficial**  
```python
{"nome": "Sputnik Brasil", "url": "https://noticiabrasil.net.br/export/rss2/archive/index.xml"}
```
O domínio `noticiabrasil.net.br` não é o domínio oficial do Sputnik Brasil (que era `sputnikbrasil.com.br`, descontinuado em 2022 após sanções). Este feed aponta para um site de terceiro que pode estar reaproveitando conteúdo do Sputnik ou ser completamente diferente.

**CAT-003 — Feeds AP News via `feedx.net` (agregador de terceiro)**  
```python
{"nome": "AP News", "url": "https://feedx.net/rss/ap.xml"}
```
A AP News não disponibiliza RSS público diretamente. O feed via `feedx.net` é um serviço de terceiro que pode ter latência, instabilidade, ou violar os termos de uso da AP. O feed correto da AP para acesso direto requer contrato de licença.

**CAT-004 — Duplicação entre `catalogo_fontes.py` e `catalogo_midia.py/catalogo_nicho.py`**  
`tecnoblog`, `canaltech`, `tecmundo`, `ESPN Brasil` aparecem tanto em `catalogo_fontes.py` (bloco RSS) quanto em `catalogo_midia.py` / `catalogo_nicho.py` (bloco scrapers). O sistema que combinar os dois catálogos processará as mesmas fontes duas vezes por ciclo.

**CAT-005 — ESG e fontes de sustentabilidade mapeadas para `CAT_ECONOMIA` em vez de `CAT_ESG`**  
```python
{"nome": "Capital Reset", "url": "...", "cat_id": CAT_ECONOMIA},
{"nome": "ESG Today", "url": "...", "cat_id": CAT_ECONOMIA},
{"nome": "Responsible Investor", "url": "...", "cat_id": CAT_ECONOMIA},
```
`CAT_ESG = [136, 142]` existe no `config_categorias.py`, mas as fontes ESG estão mapeadas para `CAT_ECONOMIA = [72]`. Artigos de ESG/sustentabilidade não chegarão à subcategoria correta no WordPress.

**CAT-006 — `infra_telecom_logistica` mistura CAT_TECNOLOGIA e CAT_INFRAESTRUTURA inconsistentemente**  
Telesíntese, Teletime, Mobile Time e TelComp são mapeados para `CAT_TECNOLOGIA`, enquanto Megawhat, Absolar, PV Magazine são mapeados para `CAT_INFRAESTRUTURA`. O mesmo drawer contém fontes de telecomunicações (que têm `CAT_TELECOM = [129, 137]`) mapeadas para a categoria pai em vez da subcategoria específica.

**CAT-007 — Feeds `arXiv cs.AI`, `cs.LG`, `cs.CL` em `ia_ciencia` mapeados para `CAT_TECNOLOGIA` geral**  
Artigos do arXiv são papers acadêmicos de pesquisa, não notícias de tecnologia. Deveriam ser filtrados por relevância antes de publicação ou mapeados para `CAT_CIENCIA = [129, 134]` (subcategoria de Ciência & Pesquisa).

**CAT-008 — `esg_sustentabilidade` inclui fontes de política pública (`Nexo Políticas Públicas`) mapeadas para `CAT_POLITICA`**  
```python
{"nome": "Nexo Políticas Pub", "url": "https://pp.nexojornal.com.br/rss.xml", "cat_id": CAT_POLITICA}
```
O Nexo Políticas Públicas é um portal de análise de políticas públicas com foco em dados — não é um veículo de notícias políticas no sentido editorial. Mapear para `CAT_POLITICA` é uma categorização incorreta.

**CAT-009 — `internacional_pt` inclui `Tatoli` e `Téla Nón` (Timor-Leste) sem indicação de idioma**  
Tatoli e Téla Nón publicam em tétum e português de Timor-Leste, que usa variantes ortográficas distintas. O LLM pode ter dificuldade em reescrever corretamente artigos nesses dialectos como "Português do Brasil".

**CAT-010 — Categoria `CAT_TURISMO` não tem nenhum feed RSS**  
`CAT_TURISMO = [80]` aparece apenas nos feeds do Gov.br (`Gov.br (Turismo)`) e Câmara (`Câmara (Turismo)`). Não há fonte jornalística especializada em turismo no catálogo. A categoria existirá no WordPress sem conteúdo consistente.

---

## 11. `catalogo_scrapers.py`

### 🟡 Problemas de Design

**DESIGN-015 — Merge de catálogos via `{**dict}` sobrescreve chaves duplicadas silenciosamente**  
```python
CATALOGO_SCRAPERS = {**CATALOGO_GOV, **CATALOGO_MIDIA, **CATALOGO_NICHO}
```
Se dois sub-catálogos tiverem uma chave com o mesmo nome (ex: `"estados"` ou `"internacional"`), o último wins silenciosamente. Não há validação de colisões de chave. Considerando que `catalogo_gov.py` tem `"estados"` e `catalogo_midia.py` tem `"internacional"`, e `catalogo_nicho.py` também poderia ter chaves similares, há risco de fontes sendo perdidas no merge.

**DESIGN-016 — Nenhum esquema de validação nas entradas dos catálogos**  
Cada entrada deveria ter validação mínima: `url` deve ser válida, `cat_id` deve existir em `config_categorias.py`, `tipo_molde` deve ser um valor permitido. Nenhuma dessas validações existe. Entradas malformadas só serão descobertas em tempo de execução.

---

## 12. `catalogo_gov.py`

### 🔴 Bugs Críticos

**BUG-012 — Loop gerador de TRTs modifica `CATALOGO_GOV` em tempo de importação**  
```python
for i in range(1, 25):
    ...
    CATALOGO_GOV["judiciario_conselhos"].append({...})
```
Este código executa no nível de módulo, modificando o dicionário `CATALOGO_GOV` a cada importação do arquivo. Em Python, módulos são importados uma vez e cacheados em `sys.modules`, então na prática isso roda apenas uma vez por processo. No entanto, se o módulo for forçadamente recarregado (ex: em testes, ou via `importlib.reload`), os TRTs serão **duplicados** na lista `judiciario_conselhos`.

**BUG-013 — TRT4 (RSS) duplicado em `catalogo_fontes.py` e `catalogo_gov.py`**  
`catalogo_fontes.py` tem:
```python
{"nome": "TRF4", "url": "https://www.trf4.jus.br/trf4/noticias.xml", "cat_id": CAT_JUSTICA}
```
`catalogo_gov.py` gera `TRT4` via loop. TRF4 e TRT4 são tribunais diferentes (TRF = Federal Regional; TRT = Trabalho Regional), mas a duplicação de nomes similares pode confundir o deduplicador de conteúdo se ambos publicarem sobre a mesma decisão.

### 🟡 Problemas de Catálogo

**CAT-011 — TRT24 não existe no Brasil (há apenas TRT1 a TRT24, com TRT17 como o mais recente criado em 2020)**  
O loop vai `range(1, 25)` gerando TRT1 a TRT24. O TRT24 (Mato Grosso do Sul) foi extinto em 2017 e incorporado ao TRT15. A URL `https://www.trt24.jus.br/noticias` resultará em erro 404.

**CAT-012 — Estados faltantes no catálogo de scrapers: Roraima (RR), Piauí (PI), Maranhão (MA) incompletos**  
O catálogo `estados` em `catalogo_gov.py` tem 19 estados. Brasil tem 26 estados + DF = 27 unidades. Faltam scrapers para: **AC** (Acre — o feed RSS está em `catalogo_fontes.py` mas não há scraper), **AP** (Amapá está, parcialmente), **RR** (Roraima), **PI** (Piauí), **ES** (Espírito Santo), **CE** (Ceará), **GO** (Goiás), **MG** (mas Agência Minas está). A cobertura estadual é sistematicamente desigual.

**CAT-013 — `catalogo_gov.py` importa `from config_categorias import *` mas está em diretório diferente**  
Se `catalogo_gov.py` for executado fora do diretório raiz do projeto, o import falhará com `ModuleNotFoundError`. Não há gestão de path explícita como em `motor_consolidado/config_consolidado.py`.

---

## 13. `catalogo_midia.py`

### 🟡 Problemas de Catálogo

**CAT-014 — `Omelete` com URL de API (`https://www.omelete.com.br/api/`)**  
```python
{"nome": "Omelete", "url": "https://www.omelete.com.br/api/", "cat_id": CAT_ENTRETENIMENTO, "tipo_molde": "omelete"}
```
A URL aponta para uma API privada do Omelete, não para uma página pública. Sem autenticação ou conhecimento do endpoint correto da API, esse scraper falhará com 403 ou retornará dados não estruturados.

**CAT-015 — `The Athletic` tem paywall completo**  
```python
{"nome": "The Athletic", "url": "https://theathletic.com/", "cat_id": CAT_ESPORTES, "tipo_molde": "inteligente"}
```
The Athletic é assinatura paga com paywall rígido. O scraper "inteligente" não conseguirá conteúdo significativo sem autenticação.

**CAT-016 — `Reuters` com scraper "inteligente" — Reuters bloqueia bots ativamente**  
Reuters implementa detecção sofisticada de bots (Imperva/Distil Networks). Um scraper sem rotação de user-agent, proxies e fingerprinting adequados será bloqueado em segundos.

**CAT-017 — `Bloomberg Línea` e `Bloomberg Green` acessados via scraper**  
Bloomberg usa autenticação e firewall anti-bot (similar ao Reuters). O `tipo_molde: "inteligente"` não será suficiente.

**CAT-018 — Duplicação ESPN Brasil entre catálogo de scrapers e de fontes RSS**  
`catalogo_midia.py` linha 148: `ESPN Brasil` scraper.  
`catalogo_fontes.py`: `ESPN Brasil` RSS feed.  
`catalogo_nicho.py` linha 148: `ESPN Brasil` scraper novamente.  
Três instâncias do mesmo veículo em sistemas diferentes.

---

## 14. `catalogo_nicho.py`

### 🟡 Problemas de Catálogo

**CAT-019 — `TecMundo` com `tipo_molde: "tecmundo"` (molde específico) duplicado com RSS**  
`catalogo_nicho.py` usa molde específico `"tecmundo"`, mas `catalogo_fontes.py` já tem o RSS do TecMundo. Processamento duplo da mesma fonte.

**CAT-020 — `Bleaching Computer` tem URL correta mas pode ser confundido com `Bleeping Computer`**  
```python
{"nome": "Bleeping Computer", "url": "https://www.bleepingcomputer.com/"}
```
Nome correto no arquivo, mas vale verificar se o molde "inteligente" consegue extrair notícias de segurança da estrutura do BleepingComputer, que usa JavaScript para renderizar conteúdo crítico.

**CAT-021 — Fontes de finanças ESG (`UNPRI`, `CDP`, `Environmental Finance`) não são fontes jornalísticas**  
UNPRI, CDP e Environmental Finance são organizações/portais de dados financeiros e relatórios corporativos, não portais de notícias. Injetar seus comunicados diretamente no pipeline de reescrita jornalística pode gerar conteúdo que é essencialmente press release corporativo reformatado como notícia.

---

## 15. `agente_revisor.py`

### 🔴 Bugs Críticos

**BUG-014 — `NameError: base64` herdado de `config_geral.py`**  
A linha 24 importa `from config_geral import WP_URL, AUTH_HEADERS`. Como `config_geral.py` tem o bug BUG-008 (falta `import base64`), qualquer execução de `agente_revisor.py` falhará imediatamente com `NameError` antes de executar qualquer linha do próprio agente.

**BUG-015 — Loop infinito potencial em `executar_auditoria_continua`**  
O loop `while True` (linha 300) termina quando `res.status_code != 200` ou `not posts`. No entanto, se a API WordPress retornar erros intermitentes (500, 502, 503), o loop **termina prematuramente** sem tentar novamente. Ao contrário, se a API retornar 200 com uma lista vazia por algum bug no WordPress, o loop para corretamente. O problema real é: não há limite de páginas explícito. Se o WordPress tiver 10.000 posts e a API suportar `per_page=50`, o agente fará **200 requisições sequenciais** sem pausa significativa (apenas `time.sleep(0.5)` entre páginas), podendo causar throttling ou ban da API.

**BUG-016 — `salvar_controle(controle)` a cada post individual — I/O excessivo**  
Linha 402: o arquivo JSON de controle é escrito a **cada post processado**. Em uma auditoria de 10.000 posts, isso resulta em 10.000 operações de escrita sequencial em disco. Deveria acumular mudanças e gravar em lote (ex: a cada 50 posts ou ao fim de cada página).

**BUG-017 — `extrair_url_original` usa heurística frágil**  
A função busca comentários `<!-- URL_ORIGINAL: ... -->` primeiro (correto), depois percorre links HTML em ordem reversa (linha 96: `for link in reversed(links_html)`). O link em ordem reversa pode ser um link de navegação do WordPress (ex: `https://outra-fonte.com/artigo-relacionado`) que não tem relação com a fonte original. A função pode identificar incorretamente a URL de uma fonte cruzada como a URL original.

**BUG-018 — Lógica de correção de categoria aplica `adivinhar_categoria` para TODOS os posts**  
```python
# Linha 214
if 1 in cat_atual_ints or not all(c in cat_atual_ints for c in lista_sug):
    correcoes['categories'] = lista_sug
```
A condição `1 in cat_atual_ints` verifica se a categoria "Uncategorized" (ID 1) está presente. A segunda condição `not all(...)` é sempre verdadeira se o post já tiver categorias corretas mas não idênticas à sugestão da heurística. Isso significa que o agente pode **sobrescrever categorias corretas** (atribuídas com precisão pelo LLM durante a publicação) com as categorias da heurística keyword-based — que é menos sofisticada. Por exemplo, um artigo sobre "Crise hídrica no Nordeste" (corretamente categorizado como `CAT_MEIO_AMBIENTE`) pode ter sua categoria sobrescrita para `CAT_POLITICA` pela heurística, pois `"nordeste"` não está na lista de keywords de meio ambiente.

### 🟡 Problemas de Mapeamento de Autores

**AUTOR-001 — `MAPA_UNIFICADO_AUTORES` mapeia `stf.jus` e `stj.jus` para o mesmo ID 52**  
```python
"stf.jus": 52, "stj.jus": 52, "cnj.jus": 52
```
STF, STJ e CNJ são instituições diferentes. Mapear para o mesmo autor ID sugere que existe um único usuário WordPress representando todo o judiciário. Aceitável se o ID 52 for "Redação Judiciária" — mas isso não está documentado, e pode sobrescrever atribuições específicas.

**AUTOR-002 — `gov.br/mds` e `gov.br/mdic` não têm correspondência verificável no banco**  
IDs de autor 20 e 21 para `gov.br/mds` e `gov.br/mdic` são utilizados sem nenhuma documentação de que esses usuários WordPress existem. Se o ID não existir no WP, a API retornará erro 400 na atualização do post.

**AUTOR-003 — `agenciars` mapeia para ID 140 mas o padrão dos estados começa em 118**  
IDs de agências estaduais: `agenciaac: 118`, `alagoas.al: 119`, `agenciaminas: 128`, `aen.pr: 135`, `agenciars: 140`. A sequência não é contígua e não tem documentação. IDs 120–127, 129–134, 136–139 estão ausentes do mapeamento, o que pode significar autores deletados ou nunca criados.

**AUTOR-004 — `"gov.br/esporte"` no mapa mas o URL correto é `"gov.br/esportes"` (com 's')**  
```python
"gov.br/esporte": 25  # linha 50
```
A URL real dos feeds do ministério é `https://www.gov.br/esportes/pt-br/...` (com 's'). O match por `chave in url_l` nunca encontrará `"gov.br/esporte"` nas URLs reais, deixando artigos do Ministério do Esporte sem atribuição correta de autor.

**AUTOR-005 — Ausência de mapeamento para fontes de mídia privada**  
O mapa cobre apenas fontes governamentais e agências. Fontes como G1, Folha, CNN Brasil, BBC não têm mapeamento — portanto o autor padrão (`id_oficial_redacao` obtido via API) será usado para todo o conteúdo de imprensa privada, o que é o comportamento esperado. Mas fontes como `conjur.com.br`, `jota.info` e `migalhas.com.br` (portais jurídicos especializados) também não têm mapeamento específico.

### 🟡 Problemas de Segurança

**SEC-004 — Agente revisor executa PATCH em todos os posts sem dry-run padrão**  
`upd_res = requests.post(f"{WP_URL}/posts/{post_id}", json=correcoes, headers=AUTH_HEADERS)` (linha 362) realiza modificações reais no WordPress sem nenhum modo de simulação. Um bug na heurística de `adivinhar_categoria` (como BUG-018) pode sobrescrever centenas de categorias corretamente definidas antes que o operador perceba.

---

## 16. `agente_newspaper.py`

### 🔴 Bugs Críticos

**BUG-019 — Senha do banco de dados hardcoded na linha 36**  
```python
WP_DB_PASS = os.getenv("DB_PASS", "d0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b")
```
A hash da senha do banco MariaDB está **hardcoded como valor padrão**. Essa não é uma hash segura — parece ser uma senha em texto plano ou um hash SHA-256 de uma senha conhecida. Independentemente da forma, ter qualquer credencial de banco de dados no código-fonte é uma falha de segurança crítica. **Esta credencial deve ser revogada e rotacionada imediatamente.**

**BUG-020 — Mesmo valor de senha hardcoded em `construir_knowledge_base.py` linha 574**  
```python
'-pd0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b',
```
A mesma string de credencial aparece **dentro de um array de argumentos de linha de comando** passado via `subprocess.run`. Além do risco de segurança, esse valor aparece em logs de processo, na tabela de processos do SO (`ps aux`) e em qualquer ferramenta de monitoramento — tornando a credencial visível para qualquer usuário com acesso à shell.

**BUG-021 — Injeção SQL potencial em `consultar_opcoes_tema`**  
```python
def consultar_opcoes_tema(self, chave=None):
    if chave:
        sql = f"SELECT option_value FROM wp_7_options WHERE option_name='{chave}';"
```
O parâmetro `chave` é concatenado diretamente na string SQL sem sanitização ou uso de parâmetros bind. Se `chave` vier de uma interface externa (ex: do briefing interpretado pela IA ou de input do usuário), um valor como `'; DROP TABLE wp_7_options; --` executaria SQL arbitrário no banco WordPress. A função deveria usar parâmetros parametrizados: `c.execute("SELECT option_value FROM wp_7_options WHERE option_name = ?", (chave,))`.

**BUG-022 — `contar_posts_categoria` com injeção SQL via `cat_id` não sanitizado**  
```python
def contar_posts_categoria(self, cat_id):
    result = self.executar_sql_wp(
        f"SELECT COUNT(*) FROM wp_7_posts p "
        f"JOIN wp_7_term_relationships tr ON p.ID = tr.object_id "
        f"WHERE tr.term_taxonomy_id = {cat_id} AND p.post_status = 'publish';"
    )
```
`cat_id` é interpolado diretamente na query SQL passada para `executar_sql_wp` — que por sua vez executa via `subprocess.run` com `mariadb ... -e sql`. Isso é injeção de comando de shell além de injeção SQL.

**BUG-023 — `executar_sql_wp` passa senha via argumento de linha de comando (`-p{WP_DB_PASS}`)**  
```python
cmd = [MARIADB_BIN, '-u', WP_DB_USER, f'-p{WP_DB_PASS}', ...]
```
Passar senha via argumento `-p` na linha de comando é **inseguro no Linux/Unix**: a senha fica visível em `/proc/<pid>/cmdline`, no output de `ps aux` e em logs de auditoria do sistema. O correto seria usar `--defaults-file`, variável de ambiente `MYSQL_PWD`, ou conexão via Python com `pymysql`/`mysql-connector-python`.

### 🟡 Problemas de Design

**DESIGN-017 — `AgenteNewspaper.__init__` abre conexão SQLite sem fechamento garantido**  
O `__init__` abre `sqlite3.connect(DB_PATH)`. Se uma exceção ocorrer antes de `agente.close()` ser chamado (ex: em `status_geral` ou em qualquer método), a conexão vaza. O padrão correto seria usar `contextmanager` ou implementar `__enter__`/`__exit__` para uso com `with`.

**DESIGN-018 — `interpretar_briefing` inclui lista completa de componentes no prompt**  
O system prompt injeta `lista_comp`, `lista_acoes` e `lista_cats` inteiros (todas as linhas do banco). Com ~25 componentes, ~20 ações e 40+ categorias, isso pode ultrapassar facilmente o limite de tokens úteis do contexto, ou confundir o LLM com excesso de informação. Deveria usar busca semântica ou filtrar por relevância antes de injetar no prompt.

**DESIGN-019 — `processar_briefing` registra interpretação no `change_log` mesmo sem executar ação**  
O método registra no `change_log` toda chamada a `interpretar_briefing`, mesmo que seja apenas uma consulta. O log de alterações deveria registrar apenas mudanças reais, não interpretações. Isso polui o histórico e dificulta auditorias reais de mudanças.

---

## 17. `construir_knowledge_base.py`

### 🔴 Bugs Críticos

**BUG-024 — Senha hardcoded em argumento de subprocess (mesma que BUG-020)**  
```python
'-pd0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b',
```
Mesma credencial crítica hardcoded. Veja BUG-020.

**BUG-025 — `criar_banco` deleta o banco existente sem backup**  
```python
def criar_banco():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
```
Ao re-executar `construir_knowledge_base.py`, o banco SQLite existente (incluindo todo o `change_log` de alterações históricas registradas pelo `agente_newspaper.py`) é **deletado permanentemente** antes da criação do novo. Não há backup, export de dados existentes, ou aviso ao operador.

### 🟡 Problemas de Design

**DESIGN-020 — `atualizar_post_counts` concatena credenciais via `-p<senha>` no subprocess**  
Mesmo padrão inseguro de BUG-020/BUG-023 — a senha aparece em argumentos de processo.

**DESIGN-021 — Status `theme_version: 12.7.5` hardcoded como dado imutável no knowledge base**  
```python
('theme_version', '12.7.5', 'general', 'string', 'Versão atual do tema Newspaper'),
```
Versões de tema mudam com atualizações. Este dado ficará desatualizado a cada update do tema Newspaper e não há mecanismo de sincronização automática.

**DESIGN-022 — `total_published_posts: 9180` hardcoded**  
O número de posts publicados cresce a cada ciclo do motor. O knowledge base armazenará um valor congelado na data da construção — potencialmente meses ou anos desatualizado.

**DESIGN-023 — Injeção SQL potencial via `f-string` em `status_geral` do `agente_newspaper.py`**  
```python
for table in ['doc_sections', 'theme_components', ...]:
    c.execute(f'SELECT COUNT(*) FROM {table}')
```
Embora neste caso específico a lista seja hardcoded no código-fonte e não vem de input externo, é um padrão que, se generalizado para aceitar parâmetros externos, abre SQL injection. Deveríamos usar allowlist de tabelas com verificação explícita.

---

## 18. Conflitos Cross-File (Visão Sistêmica)

### Conflito A — Dois roteadores de IA sem coordenação (CRÍTICO)

| Aspecto | `roteador_ia.py` | `motor_rss/llm_router.py` |
|---|---|---|
| **Fonte de chaves** | `config_chaves.POOL_CHAVES` | `motor_rss/config.OPENAI_KEYS` etc. |
| **Circuit breaker** | ❌ Não tem | ✅ Implementado (não thread-safe) |
| **Rotação de chaves** | ❌ Não tem (percorre POOL linear) | ✅ Round-robin por provider |
| **Modelos** | gpt-4o, grok-beta (desatualizado), llama-3.1 (desatualizado) | gpt-4o, claude-sonnet-4, grok-3 (atualizado) |
| **Tiers** | ❌ Não há tiers | ✅ 6 tiers definidos |
| **JSON mode** | Apenas OpenAI | Não usa `response_format` |
| **Quem usa** | `agente_newspaper.py`, `agente_revisor.py` (via `config_geral`) | `motor_rss`, `motor_consolidado` |

Os dois roteadores são paralelos e independentes. Uma falha de API no OpenAI registrada no circuit breaker do `llm_router.py` não afeta o `roteador_ia.py` — que continuará tentando a mesma chave com falha.

### Conflito B — Credenciais em três arquivos distintos com padrões diferentes (CRÍTICO)

| Arquivo | Variável WP | Senha hardcoded? | Padrão |
|---|---|---|---|
| `config_geral.py` | `WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")` | **SIM** | Senha WP exposta |
| `motor_rss/config.py` | `WP_APP_PASS = os.getenv("WP_APP_PASS", "")` | Não | Correto |
| `agente_newspaper.py` | `WP_DB_PASS = os.getenv("DB_PASS", "d0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b")` | **SIM** | Senha DB exposta |
| `construir_knowledge_base.py` | `-pd0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b` | **SIM** | Senha DB em argumento |

### Conflito C — `WP_URL` com semânticas diferentes entre módulos

`config_geral.py`: `WP_URL = "https://brasileira.news/wp-json/wp/v2"` (URL completa da API)  
`motor_rss/config.py`: `WP_URL = "https://brasileira.news"` (domínio base) + `WP_API_BASE` separada

Módulos que importam de ambos os arquivos podem usar `WP_URL` para fins diferentes.

### Conflito D — Schema JSON de saída inconsistente entre motores

| Campo | `regras_arte.py` | `motor_rss/config.py` | `regras_seo.py` |
|---|---|---|---|
| Título principal | (não define) | `titulo` | `h1_title` |
| Imagem | `prompt_imagem` | `imagem_busca_gov`, `imagem_busca_commons` | (não define) |
| Corpo | (não define) | `conteudo` | `corpo_html` |
| Notificação push | (não define) | `push_notification` | `push_notification` |
| Copy social | (não define) | (não define) | `social_copy` |

Três arquivos de regras definem schemas de saída parcialmente sobrepostos e parcialmente contraditórios.

### Conflito E — Categorias duplicadas em nomes distintos

| ID | `config_categorias.py` | `motor_rss/VALID_CATEGORIES` | `construir_knowledge_base.py` |
|---|---|---|---|
| 71 | `CAT_POLITICA` | `"Política & Poder"` | `"Política & Poder"` |
| 73 | `CAT_JUSTICA` | `"Direito & Justiça"` | `"Justiça & Direito"` |
| 78 | `CAT_INFRAESTRUTURA` | `"Infraestrutura & Urbanismo"` | `"Infraestrutura & Cidades"` |

Nomes de categorias inconsistentes entre os três sistemas. O LLM instruído com os nomes de `VALID_CATEGORIES` pode retornar um nome que não mapeia exatamente para a constante Python ou para o slug do WordPress.

---

## Resumo Executivo de Severidade

### 🔴 Crítico — Falha imediata de produção

| ID | Arquivo | Descrição |
|---|---|---|
| BUG-008 | `config_geral.py` | `NameError: base64` não importado — derruba agente revisor |
| BUG-009 | `config_geral.py` | Senha WordPress hardcoded no código-fonte |
| BUG-014 | `agente_revisor.py` | Herda `NameError` de `config_geral.py` — inutiliza o agente |
| BUG-019 | `agente_newspaper.py` | Senha MariaDB hardcoded no código-fonte |
| BUG-020 | `agente_newspaper.py` | Senha MariaDB em argumento de subprocess — visível em logs |
| BUG-021 | `agente_newspaper.py` | SQL injection em `consultar_opcoes_tema` |
| BUG-022 | `agente_newspaper.py` | SQL injection em `contar_posts_categoria` |
| BUG-024 | `construir_knowledge_base.py` | Mesma senha MariaDB hardcoded em argumento subprocess |
| BUG-025 | `construir_knowledge_base.py` | Deleta knowledge base com `change_log` sem backup |

### 🟠 Alto — Bug de lógica com impacto em produção

| ID | Arquivo | Descrição |
|---|---|---|
| BUG-004 | `llm_router.py` | Circuit breaker não thread-safe — race condition |
| BUG-005 | `llm_router.py` | `_rotate_key` e `_next_key` conflitam, pulando chaves |
| BUG-006 | `llm_router.py` | `call_llm` registra sucesso sem validar resposta |
| BUG-012 | `catalogo_gov.py` | Loop TRT modifica dict no import — duplicação ao recarregar |
| BUG-015 | `agente_revisor.py` | Loop de auditoria sem limite de páginas — risco de 200+ req |
| BUG-018 | `agente_revisor.py` | `adivinhar_categoria` sobrescreve categorias corretas do LLM |
| CONF-006 | configs | `WP_URL` semântica diferente entre módulos |
| CONF-001 | configs | `CAT_TURISMO` válido no WP mas ausente de `VALID_CATEGORIES` |

### 🟡 Médio — Degradação de qualidade ou comportamento inesperado

| ID | Arquivo | Descrição |
|---|---|---|
| BUG-001 | `roteador_ia.py` | Código morto inacessível em `roteador_ia_imagem` |
| BUG-002 | `roteador_ia.py` | Dependência de `config_chaves` não documentada/verificada |
| BUG-010 | `config_consolidado.py` | Path `.env` hardcoded Bitnami — falha fora do ambiente original |
| PROMPT-011 | `regras_arte.py` | Schema `prompt_imagem` vs `imagem_busca_gov/commons` — contradição |
| AUTOR-004 | `agente_revisor.py` | `"gov.br/esporte"` sem 's' — match nunca ocorre |
| CAT-001 | `catalogo_fontes.py` | RT, CGTN, TASS, KCNA sem flag editorial de propaganda estatal |
| CAT-005 | `catalogo_fontes.py` | Fontes ESG mapeadas para `CAT_ECONOMIA` em vez de `CAT_ESG` |
| DESIGN-007 | `llm_router.py` | Circuit breaker compartilhado entre modelos do mesmo provider |
| DESIGN-011 | `llm_router.py` | `classify_tier` ignora `content_length` e `score` |

---

*Fim da auditoria. Total: 25 bugs catalogados, 23 conflitos de configuração/design identificados, 14 issues de prompt engineering, 21 problemas de catálogo de fontes.*
