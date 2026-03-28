# Análise de Bugs do Sistema de Curadoria — brasileira.news

**Auditoria realizada em:** 2026-03-20  
**Arquivos analisados:** 17  
**Severidade:** CRÍTICO = produção afetada imediatamente; ALTO = risco frequente; MÉDIO = risco pontual; BAIXO = qualidade/manutenção

---

## Sumário Executivo

O sistema de curadoria possui múltiplos bugs críticos que afetam diretamente a homepage em produção. Os mais graves são: (1) **janela zero de tags** — há um período onde a homepage fica sem posts em qualquer destaque, causado pelo ciclo clear→apply sem atomicidade; (2) **dois arquivos `curator_config.py` completamente diferentes** em conflito silencioso; (3) **inconsistência grave de mapeamento** entre tags do curador e posições reais na homepage; (4) **timezone naive** em todas as comparações de data causando erro sistemático de até 3 horas; (5) **credenciais hardcoded** em texto plano em 3 scripts; e (6) **injeção SQL** em 2 scripts de migração.

---

## 1. `curator/curator_agent.py` — Orquestrador Principal

### 🔴 CRÍTICO — Race Condition: Janela de Homepage Vazia

**Arquivo:** `curator_tagger.py`, chamado por `curator_agent.py` linha 433  
**Localização:** `apply_all_positions()` → `clear_curator_tags()` seguido de loop de aplicação

```python
# Primeiro: limpar tags antigas
clear_curator_tags(dry_run=dry_run)

# Cache de tags atuais por post para evitar N+1 queries
# ...
# Depois: aplicar novas
for tag_slug, post_ids in selections.items():
```

**O problema:** Entre o `clear_curator_tags()` e o início do loop de aplicação existe uma janela de tempo real onde a homepage **não tem nenhum post tagueado**. Com `WP_PATCH_DELAY = 1.0s` e até ~60 posts para retaguar em ~14 posições, essa janela pode durar de **30 a 90 segundos**. Durante esse período, qualquer visitante vê a homepage completamente vazia nos blocos curados pelo Newspaper Theme.

**Agravante:** O curador roda nos minutos 15 e 45 de cada hora. Se o Motor RSS publica um post exatamente durante a fase de limpeza (o motor roda nos minutos 0 e 30, próximo ao ciclo de 30 min), esse novo post não terá nenhuma tag editorial quando for exibido.

**Solução necessária:** Implementar transação atômica — calcular o novo estado completo, depois fazer uma única operação de diff (remover tags que saíram, adicionar as novas) sem nunca limpar tudo primeiro. Ou manter um shadow state e fazer swap.

---

### 🔴 CRÍTICO — Timezone Naive: Erro Sistemático de Horário

**Arquivo:** `curator_scorer.py`, linhas 107–111  
**Arquivo:** `curator_agent.py`, linha 100 (query SQL)

```python
# curator_scorer.py linha 107
if isinstance(post_date, datetime):
    age = datetime.now() - post_date  # ERRO: datetime.now() é local (America/Sao_Paulo = UTC-3)
```

**O problema:** O WordPress armazena `post_date` em horário local do servidor, mas `datetime.now()` retorna o horário do sistema. Se o servidor estiver configurado em UTC (padrão Bitnami), `datetime.now()` será UTC e `post_date` será UTC-3 (horário de Brasília). A diferença calculada será 3 horas **a mais** do que a realidade — um post publicado às 14h50 (local) aparecerá como publicado há 3h50 às 18h UTC, falhando no critério de `< 1h` para ganhar +10 pontos.

Da mesma forma, na query SQL (linha 100):
```sql
AND p.post_date >= NOW() - INTERVAL %s HOUR
```
`NOW()` no MySQL retorna o horário do servidor MySQL. Se MySQL e Python não estão no mesmo timezone, a janela de 4 horas pode estar errada.

**Solução:** Usar `datetime.now()` consistente com o timezone do WordPress, ou usar `datetime.utcnow()` em todo o stack se o servidor estiver em UTC. Verificar `@@global.time_zone` no MySQL.

---

### 🔴 CRÍTICO — Self-Import no Bloco de Imagens (Fase 6)

**Arquivo:** `curator_agent.py`, linhas 447–448

```python
from curator_agent import get_db_connection  # ERRO: auto-importação do próprio módulo
conn = get_db_connection()
```

O módulo importa a si mesmo. Isso funciona porque `get_db_connection` já está em escopo local, mas cria uma dependência circular que pode causar comportamento indefinido em ambientes de reload. Além disso, a conexão `conn` aberta na linha 448 é usada dentro do loop mas o `conn.close()` está na linha 472, **fora do bloco `with conn.cursor()`** — se uma exception for lançada antes de `conn.close()`, a conexão vaza.

---

### 🔴 CRÍTICO — Escape SQL Manual Vulnerável a Injeção

**Arquivo:** `aplicar_homepage_tags.py`, linha 41  
**Arquivo:** `limpar_homepage_tier1.py`, linha 126  
**Arquivo:** `aplicar_homepage.py`, linha 18

```python
# aplicar_homepage_tags.py linha 41
escaped = new_content.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
sql1 = f"UPDATE wp_7_postmeta SET meta_value='{escaped}' WHERE post_id=18135 AND meta_key='tdc_content';"
```

O escape manual é **insuficiente e vulnerável**. Não trata: `\x00` (NULL byte), `\x1a` (Ctrl-Z em Windows), newlines escapados incorretamente. O `tdc_content` pode conter shortcodes com caracteres especiais. Se o arquivo de entrada (`homepage_tdc_tags.txt`) contiver sequências como `\'` (barra + aspas), o replace duplo as transformará incorretamente. Use **parâmetros bindados via pymysql** para qualquer UPDATE com conteúdo de arquivo.

---

### 🔴 CRÍTICO — Credenciais Hardcoded em Texto Plano

**Arquivo:** `aplicar_homepage_tags.py`, linha 17  
**Arquivo:** `limpar_homepage_tier1.py`, linha 10  
**Arquivo:** `aplicar_homepage.py`, linha 43

```python
# aplicar_homepage_tags.py linha 17 — SENHA EM TEXTO PLANO NO CÓDIGO-FONTE
"-pd0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b",

# limpar_homepage_tier1.py linha 10
password=os.getenv("DB_PASS", "d0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b"),

# aplicar_homepage.py linha 43
'-pd0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b',
```

A senha do banco de dados está hardcoded em 3 arquivos diferentes e provavelmente commitada no repositório. **Esta senha deve ser rotacionada imediatamente.** Qualquer pessoa com acesso ao repositório tem acesso direto ao banco WordPress.

---

### 🔴 CRÍTICO — `log_cycle()` Usa `logger` Não Definido

**Arquivo:** `curator_agent.py`, linha 342

```python
def log_cycle(selections, scored_map):
    conn = get_db_connection()
    prefix = cfg.TABLE_PREFIX
    try:
        with conn.cursor() as cur:
            # ...
    except Exception as e:
        logger.warning("Erro ao logar ciclo: %s", e)  # 'logger' não está definido aqui!
    finally:
        conn.close()
```

`logger` é uma variável local criada em `setup_logging()` e retornada, mas `log_cycle()` é chamada de `run_cycle()` onde `logger = logging.getLogger("curator")`. Dentro de `log_cycle()` não há nenhuma referência ao logger. O `logger.warning(...)` na linha 342 vai levantar `NameError: name 'logger' is not defined`, **silenciando erros de log do banco** e potencialmente travando o except em vez de prosseguir.

**Correção:** Adicionar `logger = logging.getLogger("curator")` no início de `log_cycle()`, ou usar o padrão do módulo como em `curator_scorer.py`.

---

### 🟠 ALTO — `select_positions()` Não Respeita `MAX_SAME_CATEGORY_DESTAQUE`

**Arquivo:** `curator_agent.py`, linhas 182–289  
**Arquivo:** `curator_config.py`, linhas 85–86

```python
MAX_SAME_CATEGORY_DESTAQUE = 2
MAX_SAME_SOURCE_TOP5 = 1
```

Essas constantes estão definidas no `curator_config.py` mas **nunca são usadas em `select_positions()`**. O algoritmo de seleção não implementa nenhuma restrição de diversidade de categoria ou de fonte. Resultado: se um dia tiver muitos posts de Tecnologia com score alto, a posição `home-submanchete` pode ser preenchida inteiramente com posts de Tecnologia, quebrando a diversidade editorial da submanchete.

---

### 🟠 ALTO — Manchete Pode Ser Post Antigo (Até 4 Horas)

**Arquivo:** `curator_agent.py`, linhas 399–421

```python
manchete_candidates = scored_posts[:5]  # Top 5 para decisão
```

Os `scored_posts` incluem **todos os posts das últimas 4 horas** (`CURATOR_WINDOW_HOURS = 4`). Um post publicado 3h55 atrás pode ser o mais bem pontuado objetivamente (fonte oficial +30, consolidada +20, alto interesse +15 = 65) e acabar como manchete, enquanto um post publicado 5 minutos atrás com score 50 ficaria de fora. A manchete da homepage pode ter **quase 4 horas de atraso** sem que o sistema detecte o problema.

A verificação de frescor (`+10 pts se < 1h`) é insuficiente — a diferença de pontuação por frescor é pequena demais para garantir que manchetes sejam realmente recentes.

---

### 🟠 ALTO — Fase 6 (Imagens) Não Fecha Cursor Corretamente

**Arquivo:** `curator_agent.py`, linhas 441–474

```python
conn = get_db_connection()
with conn.cursor() as cur:
    for tag_slug, post_ids in selections.items():
        for post_id in post_ids:
            # ...
            cur.execute("INSERT INTO ...")  # INSERT sem commit intermediário
conn.commit()  # Fora do 'with' — se exception, não há commit
conn.close()   # Potencial leak se exception entre commit e close
```

O bloco `with conn.cursor() as cur` não garante que `conn.commit()` ou `conn.close()` sejam chamados em caso de exceção. Se `cur.execute()` falhar na iteração, a exception é capturada pelo `except Exception as e` externo (linha 473), mas nesse ponto `conn.commit()` e `conn.close()` **não serão chamados**, causando leak de conexão e transação aberta.

---

### 🟡 MÉDIO — Score LLM Não Desempata Corretamente Quando Budget Esgota

**Arquivo:** `curator_scorer.py`, linhas 341–356

```python
if obj_score >= cfg.LLM_SCORE_THRESHOLD and llm_budget["remaining"] > 0:
    llm_score = score_llm(...)
    llm_budget["remaining"] -= 1
    ...
else:
    breakdown["score_llm"] = 0
    breakdown["llm_skipped"] = True
    total = obj_score
```

Quando o budget LLM de 30 chamadas se esgota, os posts restantes recebem `score_llm = 0`, enquanto os já avaliados têm `score_llm` de 0 a 50. Isso significa que posts avaliados pelo LLM ganham até 50 pontos extras sobre posts similares que chegaram na fila depois. A **ordem de processamento** (que segue a ordem do banco de dados) passa a determinar quem entra na homepage, não a qualidade editorial.

Em um dia com muitos posts (ex: 80+ posts em 4 horas), os primeiros 30 posts do banco têm vantagem estrutural de até 50 pontos. Como a query ordena por `post_date DESC`, os posts mais **recentes** são avaliados pelo LLM enquanto os mais antigos da janela ficam sem avaliação — o que inverte a vantagem de frescor esperada. Posts antigos com score alto objetivo ficam sub-ranqueados.

---

### 🟡 MÉDIO — `score_objective()` Aplica Penalidade de Imagem Duas Vezes Indiretamente

**Arquivo:** `curator_scorer.py`, linhas 113–158

Um post sem imagem recebe:
- Sem bônus `+10` de `SCORE_TEM_IMAGEM`  
- Penalidade `-10` de `PENALTY_SEM_IMAGEM`

Isso representa uma diferença de **20 pontos** entre posts com e sem imagem. Contudo, a Fase 6 do `curator_agent.py` tenta corrigir imagens **após** a seleção de posições. O fluxo correto seria: corrigir imagens → escorar → selecionar. Do jeito atual, posts sem imagem são penalizados na seleção, depois a imagem é adicionada, mas o post já está na posição selecionada com um score "incorreto" registrado no log.

---

### 🟡 MÉDIO — `max(score, 0)` em `score_objective()` Mascara Posts Ruins

**Arquivo:** `curator_scorer.py`, linha 169

```python
return max(score, 0), breakdown
```

Um post internacional de nicho sem imagem sem contexto BR pode ter score real de: `-20 - 15 - 10 - 10 - 5 = -60`. Mas `max(-60, 0)` retorna `0`. Esse post depois recebe avaliação LLM (se `0 >= 25` é falso, não receberá) e entra no pool com score `0`. Na PASS 2 (fallback), um post com score `0` pode preencher posições vazias **por ordem de data**. O `max(score, 0)` transforma penalizações severas em posts aparentemente "neutros" em vez de eliminá-los.

A eliminação só acontece explicitamente se `word_count < MIN_WORDS` (score retorna `-1`). Qualquer outra combinação de penalizações, por mais negativa, resulta em score `0` que não é eliminado.

---

### 🟡 MÉDIO — `decide_headline()`: Regex de 1 Dígito Pode Capturar Número Errado

**Arquivo:** `curator_scorer.py`, linha 257

```python
match = re.search(r"\b(\d)\b", result.strip())
```

O regex `\b(\d)\b` captura um **único dígito isolado**. Se o LLM retornar algo como "Escolho o candidato 1 pois tem 3 pontos relevantes", o regex pode capturar o `3` antes do `1` dependendo da posição. Além disso, se o candidato escolhido for o número `1` e o LLM responder "candidato número 1" mas o resultado contiver dígitos em outras partes da resposta, o primeiro dígito encontrado pode ser errado.

Usar `re.search(r"^[^0-9]*([1-5])[^0-9]*$", result.strip())` seria mais seguro para garantir que se trata do único número da resposta.

---

### 🟡 MÉDIO — Ciclo Não Protegido Contra Execuções Simultâneas (Lock)

**Arquivo:** `deploy_curator.sh`, linha 41

```bash
CRON_LINE="15,45 * * * * $VENV_PYTHON $CURATOR_DIR/curator_agent.py >> $LOG_DIR/curator_cron.log 2>&1"
```

Não há nenhum mecanismo de lock (flock, pidfile) para evitar que dois ciclos rodem simultaneamente. Se o ciclo das 15h45 demorar mais de 30 minutos (possível se a API do WordPress estiver lenta, pois há `WP_PATCH_DELAY = 1.0s` por patch), o ciclo das 16h15 iniciará enquanto o anterior ainda está aplicando tags. Dois ciclos simultâneos executariam `clear_curator_tags()` e `apply_tag()` concorrentemente, criando estado de tags completamente indefinido.

---

## 2. `curator/curator_config.py` vs `agents/curator/curator_config.py` — Conflito de Configurações

### 🔴 CRÍTICO — Dois `curator_config.py` Completamente Diferentes e Incompatíveis

Os dois arquivos existem em caminhos diferentes e têm APIs radicalmente diferentes:

| Aspecto | `curator/curator_config.py` | `agents/curator/curator_config.py` |
|---|---|---|
| Conexão WP | `WP_API_BASE` (herdado de motor_rss) | `WP_BASE_URL` (hardcoded) |
| Senha WP | `WP_APP_PASS` | `WP_APP_PASSWORD` (nome diferente!) |
| Budget LLM | `LLM_MAX_CALLS_PER_CYCLE = 30` | `MAX_LLM_CALLS_PER_CYCLE = 50` |
| Posições | `HOMEPAGE_POSITIONS` (dict com 14 posições reais) | `POSITIONS` (list de dataclasses com 4 posições fictícias) |
| Tags | `TAG_IDS` (17 IDs hardcoded) | `HIGHLIGHT_TAGS` (5 slugs diferentes, sem IDs) |
| Log dir | `Path` object | `str` |
| DB password | `DB_PASS` | `DB_PASSWORD` |

**O `agents/curator/curator_config.py` define posições totalmente diferentes:**
- `home-destaque` — não existe no Newspaper Theme
- `home-recentes` — não existe no Newspaper Theme
- `editoria-destaque` — não existe no Newspaper Theme
- `min_score=80` para manchete vs `min_score=40` no arquivo real

**Se qualquer código importar acidentalmente o `agents/curator/curator_config.py` em vez do `curator/curator_config.py`, o sistema tentará aplicar tags em posições inexistentes e com credenciais erradas (WP_APP_PASSWORD vs WP_APP_PASS), falhando silenciosamente.**

O `agents/curator/` parece ser uma versão anterior ou alternativa do curador que foi abandonada mas não removida. A presença de dois configs divergentes é uma bomba-relógio.

---

### 🔴 CRÍTICO — `agents/curator/curator_config.py` Não Carrega `.env`

**Arquivo:** `agents/curator/curator_config.py`, linhas 27–31

```python
WP_BASE_URL: str = os.environ.get("WP_BASE_URL", "https://brasileira.news/wp-json/wp/v2")
WP_USER: str = os.environ.get("WP_USER", "")
WP_APP_PASSWORD: str = os.environ.get("WP_APP_PASSWORD", "")
```

Ao contrário do `curator/curator_config.py` que carrega explicitamente o `.env` do motor_rss via `load_dotenv(MOTOR_RSS_DIR / ".env")`, o `agents/curator/curator_config.py` apenas faz `os.environ.get(...)`. Se o `.env` não tiver sido carregado antes, `WP_APP_PASSWORD` será uma string vazia e todas as chamadas à API do WordPress falharão com 401 — **sem nenhum erro explícito de configuração**.

---

### 🟠 ALTO — `TAG_IDS` Hardcoded Podem Ficar Desincronizados

**Arquivo:** `curator/curator_config.py`, linhas 89–107

```python
TAG_IDS = {
    "home-manchete": 14908,
    "home-submanchete": 14909,
    # ...
    "home-especial": 14922,
    "home-urgente": 14923,
    "consolidada": 14924,
}
```

Os IDs de tags são hardcoded. Se o WordPress for reinstalado, migrado para outro ambiente (staging, dev), ou se as tags forem deletadas e recriadas (acidentalmente via Painel WP), os IDs mudarão mas o config não será atualizado automaticamente. O curador continuará tentando aplicar tag ID `14908` que pode não existir mais, sem nenhum erro visível (a API retornará `400` que será logado como warning, mas o ciclo continuará).

`criar_tags_editoriais.py` cria as tags mas **não atualiza o `curator_config.py` automaticamente** — o operador precisa copiar os IDs manualmente.

---

### 🟠 ALTO — Inconsistência: `home-esportes` e `home-justica` no Config Mas Não nas Tags

**Arquivo:** `curator/curator_config.py`, linhas 124–126

```python
"home-esportes":       {"limit": 5,  "min_score": 20, "cat_filter": {81, ...}},
"home-justica":        {"limit": 4,  "min_score": 20, "cat_filter": {73, ...}},
```

`HOMEPAGE_POSITIONS` contém `home-esportes` e `home-justica`, mas `TAG_IDS` **não contém esses slugs**. No `apply_all_positions()`:

```python
tag_id = cfg.TAG_IDS.get(tag_slug)
if not tag_id:
    logger.warning("Tag slug desconhecido: %s", tag_slug)
    continue
```

Posts selecionados para `home-esportes` e `home-justica` são **silenciosamente descartados** — nunca recebem nenhuma tag. O bloco de Esportes e Justiça na homepage ficará sempre vazio, sem nenhum alerta explícito além de um `warning` no log.

Além disso, `criar_tags_editoriais.py` cria `home-ciencia` e `home-bemestar` (que têm IDs 14914 e 14918), mas `HOMEPAGE_POSITIONS` não usa esses slugs para posições (usa `home-saude` e `home-meioambiente`). Há um desalinhamento total entre o que é criado, o que é configurado e o que é aplicado.

---

## 3. `curator/curator_tagger.py` — Gerenciamento de Tags

### 🔴 CRÍTICO — `get_posts_with_curator_tags()` Pula Tags de Posição Válidas

**Arquivo:** `curator_tagger.py`, linhas 31–33

```python
for tag_slug, tag_id in cfg.TAG_IDS.items():
    # Pular tags especiais que não são de posição
    if tag_slug in ("consolidada", "home-urgente", "home-especial"):
        continue
```

A função `clear_curator_tags()` depende de `get_posts_with_curator_tags()` para saber quais posts limpar. Porém, a função pula `home-urgente` e `home-especial` na busca. A função de limpeza depois define:

```python
for tag_slug, tag_id in cfg.TAG_IDS.items():
    if tag_slug.startswith("home-") and tag_slug not in ("home-especial", "home-urgente"):
        position_tag_ids.add(tag_id)
```

O resultado é que `home-urgente` e `home-especial` nunca são removidos da lista de posts a limpar, **mas também nunca são buscados**. Posts com `home-urgente` ficam "invisíveis" para o sistema de limpeza. Se um operador aplicar `home-urgente` manualmente, ela jamais será limpa pelo curador — acumulando posts "urgentes" indefinidamente.

---

### 🟠 ALTO — `apply_all_positions()`: Cache de Tags Invalidado Incorretamente

**Arquivo:** `curator_tagger.py`, linhas 213–236

```python
post_tags_cache: dict[int, list[int]] = {}

for tag_slug, post_ids in selections.items():
    for post_id in post_ids:
        current_tags = post_tags_cache.get(post_id)
        if current_tags is None:
            # busca via API...
            post_tags_cache[post_id] = current_tags
        
        ok = apply_tag(post_id, tag_id, current_tags, dry_run=dry_run)
        if ok:
            # Atualizar cache
            if post_id in post_tags_cache and tag_id not in post_tags_cache[post_id]:
                post_tags_cache[post_id].append(tag_id)
```

O cache é populado **após** o `clear_curator_tags()`. Portanto, para posts que foram limpos (removeram todas as tags de curadoria), o cache busca as tags atuais e as armazena corretamente. **Porém**, quando o mesmo `post_id` aparece em múltiplas posições (ex: um post pode ter `home-submanchete` e `home-tecnologia`), o cache após a primeira aplicação contém o estado atualizado.

O problema real é que `apply_tag()` busca as tags novamente se `current_tags is None`, mas o cache pode estar presente para o post com um estado **desatualizado da API** (o WordPress pode ter aplicado outras tags entre chamadas). A atualização local do cache com `post_tags_cache[post_id].append(tag_id)` não reflete o que a API realmente salvou — se `apply_tag()` falhar silenciosamente mas retornar `True` por algum motivo externo, o cache mostrará a tag como presente quando não está.

---

### 🟠 ALTO — `clear_curator_tags()` Limita a 20 Posts por Tag (`per_page: 20`)

**Arquivo:** `curator_tagger.py`, linhas 38–44

```python
resp = requests.get(
    f"{cfg.WP_API_BASE}/posts",
    params={
        "tags": tag_id,
        "per_page": 20,  # LIMITE FIXO!
        "status": "publish",
        "_fields": "id,tags",
    },
```

Se uma posição de curadoria acumulou mais de 20 posts com a mesma tag (possível após múltiplos ciclos com falha de limpeza, ou se o curador rodou com `home-tecnologia` com `limit: 10` por vários ciclos), apenas os primeiros 20 serão encontrados e limpos. Os demais **permanecerão com a tag de curadoria de ciclos anteriores**, aparecendo na homepage misturados com os posts novos.

---

### 🟠 ALTO — `apply_tag()` Usa POST mas a WP REST API Espera PUT/PATCH para Update

**Arquivo:** `curator_tagger.py`, linha 162

```python
resp = requests.post(
    f"{cfg.WP_API_BASE}/posts/{post_id}",
    json={"tags": new_tags},
    auth=AUTH,
    timeout=cfg.HTTP_TIMEOUT,
)
```

A WP REST API v2 usa `POST` para criar recursos e `PUT`/`PATCH` para atualizar. Para atualizar um post existente, o método correto é `PATCH` (ou `POST` para `/posts/{id}` que o WP aceita como update por compatibilidade). Na prática, o WordPress aceita `POST` para `/posts/{id}` como update, então isso funciona, **mas** é semanticamente incorreto e pode quebrar se o servidor tiver um proxy reverso ou WAF que bloqueie `POST` em URLs com ID.

---

### 🟡 MÉDIO — `WP_PATCH_DELAY = 1.0s` Torna o Ciclo Extremamente Lento

**Arquivo:** `curator_config.py`, linha 60

Com 14 posições e limite total de ~60 posts, mais a fase de limpeza que pode afetar 60+ posts anteriores, o ciclo faz potencialmente **120+ chamadas HTTP** com 1 segundo de delay cada = **2 minutos mínimos** só em delays. Na limpeza, há também chamada de busca por tag (14 tags × 0.3s = 4.2s). Total estimado: 3-4 minutos por ciclo.

Dado que o cron roda a cada 30 minutos, o curador gasta ~10-15% do tempo apenas em delays de rate-limit. Se o ciclo demorar mais de 30 minutos, a próxima execução se sobrepõe.

---

### 🟡 MÉDIO — Nenhum Retry em Falhas HTTP Transitórias

**Arquivo:** `curator_tagger.py`, linhas 161–176

```python
try:
    resp = requests.post(...)
    if resp.status_code == 200:
        return True
    else:
        logger.warning("Erro ao aplicar tag %d ao post %d: HTTP %d", tag_id, post_id, resp.status_code)
        return False
except Exception as e:
    logger.warning(...)
    return False
```

Se o WordPress retornar `429 Too Many Requests` ou `503 Service Unavailable` (transitório), a tag não é aplicada e o post fica sem tag. Não há nenhum mecanismo de retry com backoff exponencial. O `WP_RETRY_COUNT = 3` está definido no config mas **nunca é usado no código**.

---

## 4. `curator/curator_scorer.py` — Sistema de Pontuação

### 🔴 CRÍTICO — `_is_official_source()` Pode Match em Domínios Falsos

**Arquivo:** `curator_scorer.py`, linhas 30–35

```python
def _is_official_source(source_url: str) -> bool:
    source_lower = source_url.lower()
    return any(domain in source_lower for domain in cfg.OFFICIAL_DOMAINS)
```

O check usa `in` (substring), não verifica se é o **domínio real**. Uma URL como `http://www.fake-noticia-fura-gov.br.malicioso.com/artigo` conteria `gov.br` como substring e receberia **+30 pontos de fonte oficial**. O correto seria verificar se o domínio da URL termina com o sufixo oficial usando `urlparse`.

```python
# CORRETO:
from urllib.parse import urlparse
netloc = urlparse(source_url).netloc.lower()
return any(netloc == domain or netloc.endswith("." + domain) for domain in cfg.OFFICIAL_DOMAINS)
```

---

### 🟠 ALTO — Score LLM Usa Hash do Título para Selecionar Chave — Distribuição Desequilibrada

**Arquivo:** `curator_scorer.py`, linha 183

```python
key_idx = hash(title) % len(cfg.GEMINI_KEYS) if cfg.GEMINI_KEYS else 0
```

O `hash()` do Python é **não-determinístico entre execuções** a partir do Python 3.3 (hash randomization por padrão). Cada vez que o curador roda, o mesmo título pode usar uma chave API diferente. Se uma chave tiver atingido quota, posts com certos títulos (que mapeiam para aquela chave naquele run) receberão fallback de 25 pontos, enquanto outros títulos que mapeiam para chaves válidas recebem avaliação real. Isso cria **não-determinismo silencioso no scoring**.

A distribuição por hash também não garante balanceamento de carga entre keys — com 2 keys e 30 títulos, uma pode receber 20 chamadas e outra apenas 10.

---

### 🟠 ALTO — `_has_br_context()` Checa Somente Tags, Não Título/Conteúdo

**Arquivo:** `curator_scorer.py`, linhas 38–48

```python
def _has_br_context(tags: list[str]) -> bool:
    br_keywords = [
        "brasil", "brasileiro", "governo", "lula", "congresso",
        "senado", "câmara", "stf", "real", "ibovespa",
    ]
    for tag in tags:
        tag_lower = tag.lower()
        if any(kw in tag_lower for kw in br_keywords):
            return True
    return False
```

A função só verifica as **tags do post**, não o título nem o conteúdo. Uma notícia internacional de grande impacto para o Brasil (ex: "FED sobe juros — Impacto no Real") pode não ter nenhuma tag com "real" ou "brasil" e receber -20 pontos erroneamente. O título é muito mais confiável para determinar contexto BR do que as tags.

---

### 🟠 ALTO — Prompt LLM Retorna Até 50 Mas Regex Captura Apenas 2 Dígitos

**Arquivo:** `curator_scorer.py`, linhas 203–207

```python
text = response.text.strip()
match = re.search(r"\b(\d{1,2})\b", text)
if match:
    score = int(match.group(1))
    return min(max(score, 0), 50)
```

O regex `\d{1,2}` captura 1 ou 2 dígitos. Se o LLM retornar `"50"` (o máximo), isso funciona. Mas se o LLM retornar texto como "Relevância: 45 pontos de um total de 100 possíveis", o regex pode capturar `"45"` ou `"10"` (de `"100"`), dependendo de qual número aparecer primeiro. A instrução do prompt diz "Retorne APENAS um número inteiro de 0 a 50. Nada mais, somente o número", mas LLMs frequentemente adicionam contexto.

O `min(max(score, 0), 50)` limita ao range correto, mas se capturar o número errado do texto, o score pode ser completamente aleatório.

---

### 🟡 MÉDIO — Sistema de Pesos Favorece Excessivamente Fontes Oficiais

**Arquivo:** `curator_config.py`, linhas 67–83

| Critério | Pontos |
|---|---|
| Fonte oficial | +30 |
| Consolidada | +20 |
| Alto interesse | +15 |
| Recente (<1h) | +10 |
| Tem imagem | +10 |
| Título SEO | +5 |
| Excerpt | +5 |
| Tags | +5 |

Um press release do IBGE sem qualidade jornalística recebe +30 (fonte oficial) + possivelmente +15 (alto interesse) + +10 (imagem) = **55 pontos objetivos**, superando o limiar de qualquer posição. Conteúdo de qualidade de um veículo privado começa em 0 pontos e precisa se qualificar pelos outros critérios.

A ausência de critérios como número de compartilhamentos, pageviews, engajamento histórico ou qualidade do título (além do tamanho) cria um sistema que pode escolher comunicados governamentais de baixo interesse jornalístico como manchete.

---

### 🟡 MÉDIO — `MIN_WORDS = 200` e `MIN_WORDS_PENALTY = 300` Inconsistentes com a Realidade

**Arquivo:** `curator_config.py`, linhas 64–65

Posts passam o filtro eliminatório com 200 palavras, mas recebem penalidade com menos de 300. Isso significa que posts de 200–299 palavras passam o filtro mas sempre recebem -10 pontos. A intenção parece ser eliminar posts muito curtos, mas a configuração atual apenas penaliza em vez de eliminar posts mediocres.

---

## 5. `curator/aplicar_homepage_tags.py` — Aplicação de Tags no Banco

### 🔴 CRÍTICO — Sem Verificação de Importações Necessárias

**Arquivo:** `limpar_homepage_tier1.py`, linhas 1–6

```python
import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

conn = pymysql.connect(  # 'pymysql' não foi importado!
```

O arquivo `limpar_homepage_tier1.py` usa `pymysql`, `subprocess`, `re` e `sys` **sem importá-los**. O script vai falhar com `NameError: name 'pymysql' is not defined` na primeira execução. Este arquivo também referencia `sys.exit(1)` sem importar `sys`.

---

### 🔴 CRÍTICO — SQL Construído por Concatenação de Arquivo Não Sanitizado

**Arquivo:** `aplicar_homepage_tags.py`, linhas 34–44

```python
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    new_content = f.read().strip()

escaped = new_content.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
sql1 = f"UPDATE wp_7_postmeta SET meta_value='{escaped}' WHERE post_id=18135 AND meta_key='tdc_content';"
```

O conteúdo do `tdc_content` é formatado com shortcodes do Newspaper Theme que contêm atributos HTML/WPBakery. Esses shortcodes contêm `"` em abundância. A sequência de replace transforma `"` em `\"`, mas se o conteúdo já contiver `\"`, ele se torna `\\"` (dois backslashes + aspas), corrompendo o conteúdo. O escape não é idempotente.

---

### 🟠 ALTO — `post_id=18135` Hardcoded em Múltiplos Scripts

**Arquivo:** `aplicar_homepage_tags.py`, linhas 24, 44, 45, 77, 82  
**Arquivo:** `limpar_homepage_tier1.py`, linhas 15, 24, 77, 82, 83, 128, 129  
**Arquivo:** `aplicar_homepage.py`, linhas 21, 32, 66, 71

O ID `18135` da página de homepage está hardcoded em pelo menos 12 ocorrências em 3 arquivos. Em um ambiente de staging/desenvolvimento, esse ID provavelmente será diferente. Se a homepage for deletada e recriada no WordPress, todos esses scripts precisarão ser atualizados manualmente — e sem aviso de falha claro se o ID não existir (o UPDATE simplesmente não afetará nenhuma linha, `returncode = 0`).

---

### 🟠 ALTO — OPcache Não É Limpo Corretamente

**Arquivo:** `aplicar_homepage_tags.py`, linhas 92–95

```python
subprocess.run(
    ["sudo", "kill", "-USR2", "$(cat /opt/bitnami/php/var/run/php-fpm.pid)"],
    shell=False, capture_output=True
)
```

A substituição de comando `$(cat /opt/bitnami/php/var/run/php-fpm.pid)` **não funciona** com `shell=False`. Com `shell=False`, o argumento é passado literalmente como string `"$(cat ...)"` para `kill`, que falha silenciosamente. O OPcache do PHP **nunca é invalidado**, então o Newspaper Theme pode continuar exibindo o template antigo da homepage por horas após a atualização do banco.

Para funcionar, precisaria de `shell=True` ou ler o PID explicitamente em Python:
```python
with open("/opt/bitnami/php/var/run/php-fpm.pid") as f:
    pid = int(f.read().strip())
subprocess.run(["sudo", "kill", "-USR2", str(pid)])
```

---

## 6. `curator/migrar_homepage_tags.py` — Migração de Tags

### 🟠 ALTO — Mapeamento de Posição Indexado Implicitamente (Frágil)

**Arquivo:** `migrar_homepage_tags.py`, linhas 63–64

```python
if len(blocks) != 14:
    print(f"AVISO: Esperados 14 blocos, encontrados {len(blocks)}. Continuando com cautela...")
```

O script mapeia posições por **índice numérico** (0, 1, 2, ... 13). Se o Newspaper Theme ou o WPBakery adicionar um bloco novo (widget, banner, bloco de newsletter), todos os mapeamentos de posição 3 em diante ficam **deslocados por 1**. Por exemplo, Política (posição 2) passaria a ser Economia (posição 3) e assim por diante. O aviso é apenas printado, não impede a execução. O resultado seria atribuição de categorias erradas a todos os blocos.

---

### 🟠 ALTO — Inconsistência no Mapeamento de Posição vs. `curator_config.py`

**Arquivo:** `migrar_homepage_tags.py`, linhas 21–28 (TAG_MAP)

```python
TAG_MAP = {
    6: ("81",  "home-ciencia"),   # posição 6 = Ciência usa categoria 81 (ESPORTES!)
    8: ("73",  "home-saude"),     # posição 8 = Saúde usa categoria 73 (JUSTIÇA!)
    10: ("74", "home-bemestar"),  # posição 10 = Bem-Estar usa categoria 74 (SAÚDE)
}
```

E os nomes no CAT_NAMES confirmam:
```python
"81": "Ciência",    # mas 81 é a categoria real de ESPORTES no WordPress
"73": "Saúde",      # mas 73 é a categoria real de JUSTIÇA no WordPress
```

Este mapeamento está **factualmente errado** em relação às categorias reais do WordPress. A posição de "Ciência" usa a categoria de Esportes (81), e a posição de "Saúde" usa a categoria de Justiça (73). Em `curator_config.py`, o correto aparece:

```python
"home-esportes": {... "cat_filter": {81, ...}},   # 81 = Esportes, CORRETO
"home-justica":  {... "cat_filter": {73, ...}},    # 73 = Justiça, CORRETO
"home-saude":    {... "cat_filter": {74, ...}},    # 74 = Saúde, CORRETO
```

O `migrar_homepage_tags.py` usou nomes incorretos nos comentários e no CAT_NAMES. Isso significa que a homepage foi potencialmente migrada com blocos de "Ciência" exibindo conteúdo de Esportes e blocos de "Saúde" exibindo conteúdo de Justiça.

---

### 🟡 MÉDIO — `limpar_homepage_tier1.py` Tem TITLES Dict Definido Duas Vezes

**Arquivo:** `limpar_homepage_tier1.py`, linhas 27–38 e 46–58

```python
# Definição 1 (linhas 27-38) — SOBRESCRITA LOGO ABAIXO
TITLES = {
    "home-saude": "Justiça"  # Incorreto — home-saude com título "Justiça"?
}

# Comentário no código sobre a inconsistência:
# Let's check curator_config in previous memory: home-ciencia uses 81 (Esportes). 
# Wait, 81 is Esportes. Why is it in home-ciencia?

# Definição 2 (linhas 46-58) — sobrescreve a anterior
TITLES = {
    "home-saude": "Direito & Justiça"  # Confirmando confusão home-saude ↔ Justiça
}
```

O código tem **comentários de debug** deixados no meio ("Let's check curator_config in previous memory"), indicando que foi escrito durante uma sessão de exploração e nunca foi limpo. A variável `TITLES` é definida duas vezes, com a segunda sobrescrevendo a primeira. A linha 38 tem `# According to curator_config, home-saude filter gets Justiça (73) and Home-Bemestar gets Saúde` — que está ERRADO: `home-saude` usa cat_filter `{74, 12243, 11738}` (Saúde), e `home-justica` usa `{73}` (Justiça). O operador que escreveu este arquivo estava confuso sobre o mapeamento.

---

## 7. `curator/seed_tags_iniciais.py` — Seed Inicial

### 🟠 ALTO — Seed Aplica Tags Sem Verificar Janela de Tempo ou Score

**Arquivo:** `seed_tags_iniciais.py`, linhas 67–89

```python
def fetch_top_posts(category_id=None, per_page=10):
    params = {
        "per_page": per_page,
        "status": "publish",
        "orderby": "date",
        "order": "desc",
        # SEM FILTRO DE DATA
    }
```

O seed busca os posts mais recentes **sem nenhum filtro de data**. Isso pode tagear posts de meses ou anos atrás como manchete principal se não houver posts recentes nas categorias. O resultado é uma homepage com notícias antigas na abertura.

---

### 🟠 ALTO — `used_post_ids` Não É Respeitado Para Editorias

**Arquivo:** `seed_tags_iniciais.py`, linhas 138–145

```python
# Para manchete/submanchete, evitar duplicatas
if tag_slug in ("home-manchete", "home-submanchete"):
    if post_id in used_post_ids:
        continue

ok = add_tag_to_post(post_id, tag_id, current_tags)
if ok:
    used_post_ids.add(post_id)  # Adiciona para TODAS as tags
```

O `used_post_ids` é verificado apenas para `home-manchete` e `home-submanchete`, mas todos os posts adicionados com sucesso entram no set. Para as editorias (home-politica, home-tecnologia, etc.), o check de duplicatas não é feito, então o mesmo post pode aparecer em `home-manchete` e em `home-politica` — o que seria OK para o seed, mas o comentário diz "evitar reutilizar o mesmo post em manchete/sub" sugere intenção de isolamento global.

---

### 🟡 MÉDIO — Sem Erro Se Tag Não Encontrada no TAG_IDS

**Arquivo:** `seed_tags_iniciais.py`, linha 118

```python
tag_id = TAG_IDS[tag_slug]  # KeyError se slug não existir!
```

Se o seed_tags_iniciais.py for executado com um `SEED_MAP` que referencia um slug não presente em `TAG_IDS`, o script vai crashar com `KeyError` não tratado. O `TAG_IDS` no seed tem 14 entradas mas `SEED_MAP` tem 14 entradas — se os slugs não casarem exatamente (ex: typo), o crash ocorre.

---

## 8. `motor_consolidado/avaliador_home.py` — Avaliador de Homepage

### 🟠 ALTO — `datetime.now()` Sem Timezone em Cálculos de Idade

**Arquivo:** `avaliador_home.py`, linhas 276, 287, 297

```python
now = datetime.now()  # Sem timezone
md = datetime.fromisoformat(str(manchete_date))  # Sem timezone
metrics["manchete_age_min"] = int((now - md).total_seconds() / 60)
```

O mesmo problema de timezone do curator_agent. O MySQL retorna `post_date` em horário do servidor. Se o servidor MySQL estiver em UTC e o código Python assumir horário local (America/Sao_Paulo = UTC-3), a "idade da manchete" calculada será 3 horas a menos do que a realidade — uma manchete de 4 horas aparecerá como tendo apenas 1 hora de idade no relatório de benchmark.

---

### 🟠 ALTO — `fetch_brasileira_homepage()` Usa Janela de Tempo Dobrada Sem Documentação

**Arquivo:** `avaliador_home.py`, linha 111

```python
AND p.post_date >= DATE_SUB(NOW(), INTERVAL %s HOUR)
""", (HOMEPAGE_WINDOW_HOURS * 2,))  # 12 horas (6 * 2) para posts com tags
```

A busca de posts com tags `home-*` usa **o dobro** da janela de tempo (`HOMEPAGE_WINDOW_HOURS * 2 = 12h`), enquanto a busca de posts recentes usa `HOMEPAGE_WINDOW_HOURS = 6h`. O comentário não explica por que. O efeito é que posts de até 12 horas atrás são incluídos na avaliação da homepage, mesmo que o curador só use uma janela de 4 horas. Isso faz o `coverage_rate` parecer melhor do que realmente é.

---

### 🟡 MÉDIO — `_find_matching_post()` com Threshold de Similaridade de 0.40 é Muito Baixo

**Arquivo:** `avaliador_home.py`, linha 63

```python
SIMILARITY_MATCH = 0.40      # threshold para considerar "coberto"
```

`SequenceMatcher` com ratio 0.40 é extremamente permissivo. Títulos com apenas 40% de similaridade de caracteres podem ter temas completamente diferentes. Ex: "Lula anuncia pacote" e "Bolsonaro critica pacote" podem ter ratio > 0.40 por compartilharem "pacote" e outras palavras. O sistema pode marcar falsamente temas como `COVERED` quando apenas compartilham palavras comuns, inflando artificialmente a taxa de cobertura.

---

### 🟡 MÉDIO — `fetch_tier1_titles()` e `fetch_tier1_trending()` Sem Tratamento de Falha Total

**Arquivo:** `avaliador_home.py`, linhas 179–188

```python
def fetch_tier1_titles() -> list[dict]:
    from scraper_homes import scrape_all_portals
    return scrape_all_portals(cycle_number=1)

def fetch_tier1_trending(titles: list[dict]) -> list[dict]:
    from detector_trending import detect_trending
    return detect_trending(titles)
```

Se `scrape_all_portals()` falhar (timeout de rede, bloqueio por portal), ou se `detect_trending()` retornar lista vazia, o `run_benchmark()` continuará com `gaps = []` e gerará um relatório indicando 100% de cobertura (0 temas trending = 0 missing). Isso pode mascarar completamente a ausência de dados de benchmark.

---

## 9. `motor_consolidado/scraper_homes.py` — Scraper de Portais

### 🟠 ALTO — `_extract_titles_with_selectors()` Para no Primeiro Seletor com Resultado (Potencial Falso Positivo)

**Arquivo:** `scraper_homes.py`, linhas 93–95

```python
# Se encontrou resultados com este seletor, não precisa tentar os demais
if results:
    break
```

Se o primeiro seletor CSS retornar resultados (mesmo que inúteis, como menus de navegação com links), o scraper para e não tenta seletores mais específicos. Um seletor genérico como `"a"` poderia capturar todos os links da página incluindo menu, footer, publicidade. A lista de seletores deveria ser tentada por **especificidade**, não por "primeiro que retorna algo".

---

### 🟡 MÉDIO — `is_manchete: i < 3` é Baseado em Posição, Não em Hierarquia Editorial

**Arquivo:** `scraper_homes.py`, linha 187

```python
"is_manchete": i < 3,  # primeiros 3 = manchetes
```

Classificar os 3 primeiros resultados como manchetes é uma heurística frágil. Se o seletor CSS capturar um banner de publicidade antes dos títulos editoriais, o primeiro "título" será um anúncio marcado como manchete. Portais com HTML dinâmico podem ter ordens de elementos que não refletem a hierarquia editorial da página.

---

### 🟡 MÉDIO — `feedparser` Importado Dentro de Bloco Condicional Sem Verificação

**Arquivo:** `scraper_homes.py`, linha 146

```python
if rss_url:
    try:
        import feedparser
        feed = feedparser.parse(rss_url)
```

`feedparser` é importado condicionalmente apenas se `rss_url` existir. Se `feedparser` não estiver instalado no ambiente, o `ImportError` é capturado pelo `except Exception as e` e silenciado como `logger.warning("Falha ao ler RSS de %s: %s")`. O sistema faz fallback para scraping HTML sem avisar que o módulo está faltando.

---

## 10. `reorganizar_homepage.py` e `aplicar_homepage.py`

### 🟠 ALTO — Ambos os Scripts Modificam `post_content` Diretamente no Banco

**Arquivo:** `aplicar_homepage.py`, linhas 32–35  
**Arquivo:** `limpar_homepage_tier1.py`, linha 129

```python
sql2 = f"UPDATE wp_7_posts SET post_content='{escaped}' WHERE ID=18135;"
```

Atualizar `post_content` diretamente no banco bypassa completamente o WordPress:
1. **Sem invalidação de cache** — Object Cache (Redis/Memcached), Page Cache (WP Rocket, W3TC) não são notificados
2. **Sem hooks WordPress** — `save_post`, `wp_update_post` e outros hooks não são disparados
3. **Sem revisão** — WordPress não cria uma revisão do post
4. **Post modificado sem `post_modified`** — O campo `post_modified` e `post_modified_gmt` não são atualizados, fazendo o post parecer não atualizado para sitemaps e feeds RSS

O `tdc_content` do Newspaper Theme é armazenado em `postmeta`, não em `post_content` diretamente. Atualizar ambos pode causar inconsistência se algum processo WordPress usa um campo diferente do outro.

---

### 🟠 ALTO — `reorganizar_homepage.py` Usa Regex Não-Greedy Incorreta para Atributos

**Arquivo:** `reorganizar_homepage.py`, linha 64

```python
block_pattern = r'\[(td_flex_block_\d+|td_block_big_grid_flex_\d+)([^\\]]*?)\]'
```

O padrão `[^\]]*?` usa `?` (lazy) desnecessariamente após `[^\]]` que já é exclusivo de `]`. Mais importante: shortcodes WPBakery aninhados (ex: `[td_flex_block_1 [inner_shortcode]]`) não são tratados corretamente. Se um shortcode contiver `]` escapado ou atributos com caracteres especiais, a regex pode capturar o shortcode incorretamente.

---

### 🟡 MÉDIO — `replace_b64_desc()` Silencia Erros de Decodificação Base64

**Arquivo:** `reorganizar_homepage.py`, linhas 147–158

```python
def replace_b64_desc(match):
    try:
        decoded = base64.b64decode(b64_val).decode('utf-8')
        # ...
    except:  # bare except — captura TUDO incluindo KeyboardInterrupt
        pass
    return match.group(0)
```

O `except:` nu (sem especificar a exceção) captura inclusive `SystemExit`, `KeyboardInterrupt` e erros críticos. Se houver um erro de memória ou interrupção do usuário durante a substituição, será silenciado e o script continuará produzindo resultado incorreto.

---

## 11. `curator/deploy_curator.sh` — Script de Deploy

### 🟠 ALTO — `set -e` Pode Mascarar Falhas no Passo 2

**Arquivo:** `deploy_curator.sh`, linha 5

```bash
set -e
```

O `set -e` faz o script abortar em qualquer erro. O passo 2 executa código Python inline:
```bash
$VENV_PYTHON -c "
import sys
sys.path.insert(0, '$CURATOR_DIR')
from curator_agent import create_log_table
create_log_table()
"
```

Se `create_log_table()` falhar (sem conexão com DB, permissão negada), o `set -e` vai abortar o deploy **antes de configurar o cron**. O operador pode pensar que o deploy falhou quando na verdade apenas a criação da tabela falhou (que pode já existir). Não há mensagem de erro contextualizada.

---

### 🟡 MÉDIO — Cron Sem `--dry-run` Verifica Se Existe Antes de Adicionar, Mas Pode Duplicar em Edge Cases

**Arquivo:** `deploy_curator.sh`, linhas 44–51

```bash
if crontab -l 2>/dev/null | grep -q "curator_agent.py"; then
    (crontab -l 2>/dev/null | grep -v "curator_agent.py"; echo "$CRON_LINE") | crontab -
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
fi
```

Se o cron atual tiver dois comentários ou linhas referenciando `curator_agent.py` (ex: linha comentada e linha ativa), o `grep -v` remove **ambas** e adiciona apenas uma nova — comportamento correto. Mas se a crontab estiver vazia e `crontab -l` retornar código de erro (em alguns sistemas), o `2>/dev/null` silencia o erro mas o `grep -q` pode ter comportamento indefinido.

---

## 12. Problemas Transversais de Arquitetura

### 🔴 CRÍTICO — Sem Atomicidade na Operação Clear → Apply

O problema mais fundamental do sistema: a operação de "trocar" as tags da homepage não é atômica. Isso é detalhado na seção 1 mas vale reforçar como problema arquitetural:

**Estado atual durante o ciclo:**
1. `T=0`: Homepage tem posts A, B, C com tags corretas
2. `T=5s`: `clear_curator_tags()` remove todas as tags de A
3. `T=10s`: clear ainda em andamento para B e C
4. `T=20s`: clear concluído, homepage **completamente vazia**
5. `T=25s`: apply começa a adicionar tag à manchete
6. `T=80s`: apply concluído, homepage restaurada

A **janela de homepage vazia** em produção é inaceitável para um portal de notícias.

---

### 🟠 ALTO — Dois Sistemas de Curadoria Podem Conflitar

Existe `curator/curator_agent.py` (sistema atual via tags WP REST API) e `agents/curator/` (sistema anterior com config diferente). Não está claro se `agents/curator/` ainda é executado. Se ambos rodarem, terão ciclos conflitantes de limpeza e aplicação de tags com configurações diferentes.

---

### 🟠 ALTO — `SCORE_MINIMUM = 50` no Config Nunca é Usado

**Arquivo:** `curator_config.py`, linha 63

```python
SCORE_MINIMUM = 50
```

Essa constante está definida mas não é referenciada em nenhum lugar do código. O filtro real em `select_positions()` usa `min_score` de cada posição individualmente (valores de 20 a 40). `SCORE_MINIMUM = 50` foi provavelmente uma intenção nunca implementada.

---

### 🟠 ALTO — `WP_RETRY_COUNT = 3` Definido Mas Nunca Usado

**Arquivo:** `curator_config.py`, linha 55

```python
WP_RETRY_COUNT = 3
```

Esta constante está definida mas não é usada em nenhuma das chamadas HTTP em `curator_tagger.py`. Todas as chamadas à WP REST API são tentadas **uma única vez** sem retry.

---

### 🟡 MÉDIO — Logs Diários Sem Rotação Automática

**Arquivo:** `curator_agent.py`, linhas 43

```python
log_file = log_dir / f"curator_{datetime.now():%Y-%m-%d}.log"
```

Os logs são criados por dia mas não há nenhum mecanismo de limpeza de logs antigos. Em 1 ano de operação, haverá 365 arquivos de log acumulados em `/home/bitnami/logs/`. Dependendo do volume de posts e chamadas, cada arquivo pode ter vários MB. Não há `logrotate` configurado no deploy.

---

### 🟡 MÉDIO — Acoplamento Forte: Curador Depende de Path Absoluto `/home/bitnami`

Em múltiplos arquivos:
- `curator_config.py` linha 13: `MOTOR_RSS_DIR = Path("/home/bitnami/motor_rss")`
- `curator_agent.py` linha 444: `sys.path.insert(0, "/home/bitnami")`
- `limpar_homepage_tier1.py` linha 138: path hardcoded do MariaDB
- `aplicar_homepage_tags.py` linhas 10–11: paths absolutos para arquivos de input/output

O sistema não pode ser executado em nenhum outro ambiente (staging, CI/CD, máquina do desenvolvedor) sem alterar múltiplos paths hardcoded em arquivos diferentes.

---

### 🟡 MÉDIO — Ausência de Testes Automatizados

Nenhum arquivo de teste foi encontrado. O sistema de curadoria, que modifica diretamente o conteúdo da homepage em produção a cada 30 minutos via API do WordPress, opera sem nenhuma verificação automatizada de:
- Funcionamento correto do scoring
- Validade dos IDs de tags
- Conectividade com o banco antes de iniciar o ciclo
- Sanidade do resultado (pelo menos 1 post em home-manchete após o ciclo)

---

## Sumário de Bugs por Arquivo

| Arquivo | Crítico | Alto | Médio | Baixo |
|---|---|---|---|---|
| `curator_agent.py` | 4 | 2 | 3 | 0 |
| `curator_config.py` | 1 | 3 | 2 | 0 |
| `agents/curator/curator_config.py` | 2 | 1 | 0 | 0 |
| `curator_scorer.py` | 1 | 2 | 3 | 0 |
| `curator_tagger.py` | 1 | 3 | 2 | 0 |
| `aplicar_homepage_tags.py` | 3 | 2 | 0 | 0 |
| `atualizar_tdc_categorias.py` | 0 | 0 | 1 | 0 |
| `criar_tags_editoriais.py` | 0 | 0 | 1 | 0 |
| `limpar_homepage_tier1.py` | 2 | 1 | 2 | 0 |
| `migrar_homepage_tags.py` | 0 | 2 | 1 | 0 |
| `seed_tags_iniciais.py` | 0 | 2 | 1 | 0 |
| `deploy_curator.sh` | 0 | 1 | 1 | 0 |
| `aplicar_homepage.py` | 1 | 1 | 0 | 0 |
| `reorganizar_homepage.py` | 0 | 1 | 1 | 0 |
| `avaliador_home.py` | 0 | 2 | 2 | 0 |
| `scraper_homes.py` | 0 | 1 | 2 | 0 |
| **TOTAL** | **15** | **24** | **22** | **0** |

---

## Prioridade de Correção Recomendada

### Imediato (Produção Afetada Agora)

1. **Janela zero de tags** — Implementar diff incremental de tags (sem clear total)
2. **`logger` não definido em `log_cycle()`** — `NameError` silencia erros de banco
3. **Credenciais hardcoded** — Rotacionar senha imediatamente, mover para env var
4. **`home-esportes` e `home-justica` silenciosamente descartados** — Adicionar ao `TAG_IDS` ou remover de `HOMEPAGE_POSITIONS`
5. **OPcache não invalidado** — Corrigir o subprocess.run para usar shell=True ou ler PID explicitamente

### Curto Prazo (1-2 semanas)

6. **Timezone naive** — Usar timezone-aware datetimes em todo o stack
7. **Dois `curator_config.py` conflitantes** — Remover ou mover `agents/curator/`
8. **`_is_official_source()` substring match** — Usar urlparse para verificar domínio real
9. **`clear_curator_tags()` limitado a 20 posts** — Adicionar paginação
10. **Lock de execução única (flock)** — Evitar ciclos simultâneos
11. **`limpar_homepage_tier1.py` faltando imports** — Adicionar imports necessários
12. **`WP_RETRY_COUNT = 3` nunca usado** — Implementar retry com backoff

### Médio Prazo (Qualidade Editorial)

13. **`MAX_SAME_CATEGORY_DESTAQUE`** — Implementar restrição de diversidade na seleção
14. **Budget LLM esgotado distorce ranking** — Priorizar posts por score objetivo antes do LLM
15. **`_has_br_context()` expandir para título/conteúdo** — Além das tags
16. **Manchete pode ter até 4h** — Adicionar restrição de freshness para a manchete
17. **`post_id=18135` hardcoded** — Tornar configurável
18. **Mapeamento tag↔posição↔categoria** — Auditoria e correção do mapeamento em todos os arquivos
