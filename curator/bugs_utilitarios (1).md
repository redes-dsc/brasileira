# Auditoria de Bugs — Utilitários, Agendadores e Scripts de Manutenção
**Sistema:** brasileira.news — Automação de notícias  
**Data:** 20 de março de 2026  
**Auditor:** Análise automatizada completa  

---

## Índice

1. [Agendadores Shell](#1-agendadores-shell)
2. [Health Checks (Raias 1, 2 e 3)](#2-health-checks)
3. [Utilitários WordPress](#3-utilitários-wordpress)
4. [Scripts de Correção](#4-scripts-de-correção)
5. [Extratores de Conteúdo](#5-extratores-de-conteúdo)
6. [Diagnóstico Sistêmico — Causas Raiz](#6-diagnóstico-sistêmico)
7. [Tabela de Prioridade de Correções](#7-tabela-de-prioridade)

---

## 1. Agendadores Shell

### 1.1 `agendador_mestre.sh`

#### BUG CRÍTICO — Sem lock file / sem controle de concorrência
O script não cria nenhum arquivo PID ou lock. Se o cron o disparar novamente enquanto o ciclo anterior ainda estiver rodando (o que é provável: 23 gavetas × tempo de execução da IA), **dois processos paralelos vão publicar posts duplicados**, corromper o `historico_links.txt` (race condition de escrita por append) e sobrecarregar a API do WordPress.

```bash
# Ausente — deveria existir:
LOCK_FILE="/tmp/agendador_mestre.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "Já em execução. Abortando."; exit 1; }
```

#### BUG CRÍTICO — Sem tratamento de erros do Python
O loop `for gaveta in ...; do /usr/bin/python3 ... $gaveta; done` nunca verifica o código de saída. Se `motor_mestre.py` travar, entrar em loop ou lançar uma exceção não tratada, o shell continua silenciosamente para a próxima gaveta. Falhas de gavetas inteiras ficam invisíveis.

```bash
# Ausente — deveria existir após cada chamada:
if [ $? -ne 0 ]; then
    echo "[ERRO] Gaveta $gaveta falhou com código $?"
fi
```

#### BUG CRÍTICO — `cd /home/bitnami` sem verificação
A linha `cd /home/bitnami` não valida se o diretório existe ou se o CD teve sucesso. Se o script for executado em ambiente diferente (restauração de backup, VM nova), todos os caminhos relativos internos dos scripts Python falharão silenciosamente.

#### BUG DE DESIGN — Gaveta `nativos_br` no agendador RSS (Raia 1)
A gaveta `nativos_br` está listada no `agendador_mestre.sh` (Motor Mestre RSS), mas provavelmente deveria ser tratada exclusivamente pelo `agendador_scrapers.sh` (Raia 2). Isso pode duplicar processamento de fontes nativas.

#### PROBLEMA DE PERFORMANCE — `sleep 3` fixo entre gavetas
O `sleep 3` é um workaround para evitar rate limiting da WP API, mas é um valor arbitrário. Se a gaveta anterior demorou 2 minutos, esses 3 segundos são irrelevantes. Se a API estiver sobrecarregada, 3 segundos são insuficientes. Não há backoff exponencial.

#### PROBLEMA DE TIMEZONE
O script usa `$(date)` sem especificar timezone. Se o servidor estiver em UTC (padrão em cloud), os logs mostrarão horários errados para o operador em São Paulo (UTC-3). O cron também deve ser configurado explicitamente com `TZ=America/Sao_Paulo`.

---

### 1.2 `agendador_scrapers.sh`

Mesmos problemas críticos do `agendador_mestre.sh` (sem lock, sem verificação de erros, sem timezone), com adição:

#### BUG — `sleep 5` entre gavetas, mas scrapers são mais lentos que RSS
Scrapers de HTML podem demorar 30–120 segundos por fonte. O sleep fixo de 5 segundos não reflete a latência real. O agendador não tem timeout máximo por gaveta — um scraper pendurado (ex: site com conexão lenta infinita) trava todo o ciclo.

#### BUG — Gavetas do `agendador_scrapers.sh` diferem do `agendador_mestre.sh`
O mestre usa: `estados_br`, `meio_ambiente_br`, `nativos_br` etc.  
O scrapers usa: `estados`, `meio_ambiente_esg`, `gov_ministerios` etc.  
**Os nomes das gavetas são inconsistentes entre os dois arquivos.** Se `motor_scrapers.py` não reconhecer uma gaveta, ela falha silenciosamente (sem erro de exit code verificado).

---

### 1.3 `setup_health_crons.sh`

#### BUG — Injeção de cron sem validação do ambiente Python
O script usa `/home/bitnami/venv/bin/python3` mas não verifica se o venv existe. Se o virtualenv for recriado ou movido, todos os health checks param de rodar sem nenhum alerta.

#### BUG — Agendamento com potencial de sobreposição
- `0 3` — Raia 1 (health RSS)
- `30 3` — Raia 2 (health Scrapers)
- `0 4` — Raia 3 (health Consolidado)

A Raia 2 (`auto_health_raia2.py`) executa scrapers reais via `coletar_links_fonte()` com ThreadPoolExecutor de 10 workers. Em sites lentos, pode facilmente demorar mais de 30 minutos. Nesse caso, Raia 2 e Raia 3 rodarão **em paralelo**, consumindo memória e conexões de rede simultaneamente.

#### BUG — Idempotência do cron parcialmente implementada
O script remove linhas `auto_health_raia` antes de reinserir (`grep -v "auto_health_raia"`), o que é correto. Porém, a variável `CRON_JOB` contém quebras de linha literais dentro de aspas duplas — comportamento que varia entre shells. Em alguns sistemas, isso resulta em um único job mal-formatado em vez de três linhas separadas. O correto seria usar `printf` ou heredoc.

---

### 1.4 `rodar_todas_fontes.sh`

#### BUG CRÍTICO — Gavetas inexistentes no motor
O script chama `motor_mestre.py` com as gavetas `ministerios_autarquias`, `justica_conselhos` e `estados_internacional`. Essas gavetas NÃO aparecem no loop do `agendador_mestre.sh` (que usa nomes diferentes como `ministerios_autarquias` existe, mas `justica_conselhos` e `estados_internacional` não estão no catalogo do mestre). Se essas chaves não existirem no `catalogo_fontes.py`, o motor retorna silenciosamente sem processar nada.

#### PROBLEMA DE DESIGN — Script órfão sem contexto de uso
Não há comentários explicando quando/por que este script existe além do agendador_mestre. Parece ser um script de teste manual que ficou em produção.

---

### 1.5 `gerar_backup_codigos.sh`

#### BUG DE SEGURANÇA — O backup contém credenciais em texto plano
O script concatena **todo o conteúdo** de `*.py` e `*.sh` em `/home/bitnami/backup_integral_robos.txt`. Múltiplos arquivos (ver seção 3) contêm senhas de banco de dados e chaves de aplicativo WordPress em hardcode. O arquivo de backup, portanto, **agrega todas as credenciais do sistema em um único arquivo de texto não criptografado**.

Se esse arquivo for enviado por e-mail, transferido para outro servidor, ou se o `/home/bitnami` tiver permissões erradas, **todas as credenciais do sistema ficam expostas de uma vez**.

#### BUG — Sem rotação de backups
O arquivo de saída é sempre `backup_integral_robos.txt` (sem timestamp). Cada execução **sobrescreve** o backup anterior. Se o script rodar durante uma janela em que os arquivos estão corrompidos, o único backup disponível é o corrompido.

#### BUG — Não inclui subdiretórios
O glob `*.py *.sh` captura apenas o diretório raiz `/home/bitnami/`. Os arquivos em `motor_rss/`, `motor_scrapers/`, `motor_consolidado/` não são incluídos no backup.

---

### 1.6 `aumentar_memoria.sh` — ANÁLISE ESPECIAL

#### O que faz e por que existe
Este script eleva o `WP_MEMORY_LIMIT` para **1GB** e `WP_MAX_MEMORY_LIMIT` para **2GB**, além de aumentar o `memory_limit` do PHP para **1024M** e o `max_execution_time` para **300 segundos**.

**Por que esse arquivo existe é o diagnóstico mais importante do sistema:**

1. **O Motor Mestre publica dezenas de posts por ciclo**, cada um fazendo múltiplas chamadas à API WordPress (criar tags, upload de mídia, publicar post). O WordPress processa hooks, cache de objeto e serialização PHP para cada request.

2. **O tema Newspaper (tagDiv) é notoriamente pesado em memória.** Cada pageview carrega centenas de blocos tdb/td em PHP serializado. O `td_011_settings` contém um blob PHP serializado gigante (confirmado em `fix_theme_settings.py`: o script lida com ele como string de bytes extensos).

3. **O `auto_health_raia1.py` usa `ThreadPoolExecutor(max_workers=20)`** fazendo 20 requisições HTTP simultâneas + feedparser em memória. Com feeds grandes (100+ entradas), isso cria picos de RAM significativos.

4. **O `corrigir_posts_existentes.py` carrega TODOS os posts publicados em memória** via `fetchall()` sem paginação. Em um sistema com milhares de posts, isso é um consumo de RAM enorme de uma só vez.

5. **O `gestor_cache.py` carrega o `historico_links.txt` inteiro em um `set()` Python a cada execução** (ver seção 3.2). Com crescimento ilimitado do arquivo, isso consome cada vez mais RAM.

**Conclusão:** `aumentar_memoria.sh` é um sintoma de design — é a correção de emergência para um sistema que acumula pressão de memória de múltiplas fontes simultâneas sem nenhum mecanismo de limitação.

#### BUG — `sed -i` em wp-config.php sem backup
A modificação do `wp-config.php` via `sed -i` não cria backup automático. Se a linha `define( 'WP_DEBUG', false );` não existir (ex: em ambiente de staging com DEBUG=true), o `sed` inserirá os limites em lugar errado ou não inserirá.

#### BUG — Verificação de duplicação incompleta
O script verifica `if ! grep -q "WP_MEMORY_LIMIT"` antes de injetar no wp-config, mas depois executa `sed -i 's/memory_limit = .*/memory_limit = 1024M/'` no `php.ini` **sempre**, sem verificação. Cada execução do script sobrescreve o php.ini. Se rodado duas vezes seguidas, não causa dano, mas é imprudente.

#### BUG — Reinício com `ctlscript.sh restart` derruba o site
O comando `sudo /opt/bitnami/ctlscript.sh restart` reinicia **todos** os serviços Bitnami (Apache/Nginx + PHP-FPM + MariaDB). Isso causa **downtime completo do site** sem aviso. O script não tem `--no-reload` ou reinício graceful.

---

## 2. Health Checks

### 2.1 `motor_rss/auto_health_raia1.py`

#### BUG CRÍTICO — Race condition na escrita do `feeds.json`
O arquivo `BACKUP_FILE` é definido como constante no topo do módulo com `datetime.datetime.now().strftime('%Y%m%d')`. Se o health check for executado à meia-noite (às 3h UTC = meia-noite em Brasília, exatamente o horário do cron!), a data no nome do backup pode mudar entre a definição da constante e a execução. Embora improvável, é uma inconsistência de design.

Mais grave: o `feeds.json` original é modificado in-place via `json.dump()`. Se o processo for interrompido durante a escrita (kill, OOM, disco cheio), o arquivo ficará corrompido e **o Motor RSS inteiro parará de funcionar**. Não há escrita atômica (write to temp + rename).

```python
# CORRETO seria:
import tempfile, os
with tempfile.NamedTemporaryFile('w', dir=os.path.dirname(FEEDS_FILE), 
                                  delete=False, encoding='utf-8') as tmp:
    json.dump(data, tmp, ensure_ascii=False, indent=2)
os.replace(tmp.name, FEEDS_FILE)
```

#### BUG — Desativa feeds por qualquer erro HTTP, não apenas 404
O código só desativa feeds em caso de 404, mas trata qualquer outra exceção (timeout, 503, SSL error) como "feed OK" (retorna `False` para modificado). Porém, se o servidor retornar 403, 401, 410 ou 500, o feed permanece ativo e continuará tentando falhar nas próximas execuções.

#### BUG — Lógica de inatividade baseada apenas nos 5 primeiros itens
```python
for entry in entries[:5]:
```
Se um feed tem muitas entradas antigas no topo (por ordenação incorreta do publisher), os 5 primeiros podem ter datas velhas mesmo que existam notícias recentes. Feeds seriam desativados incorretamente.

#### BUG — `os.remove(BACKUP_FILE)` pode falhar com FileNotFoundError
Na linha 92, `os.remove(BACKUP_FILE)` é chamado se `modified_count == 0`. Porém, se o `shutil.copy2()` falhou silenciosamente (disco cheio, permissão), o backup nunca foi criado e o `os.remove` lança `FileNotFoundError` não tratado, quebrando o script.

#### BUG — ThreadPoolExecutor modifica dicts em paralelo
`check_feed()` modifica `feed_data["ativo"] = False` diretamente no dicionário passado por referência. Como Python dicts são objetos mutáveis e o ThreadPoolExecutor os compartilha via `executor.map(check_feed, feeds)`, há **race condition potencial** se dois feeds distintos compartilharem alguma referência de objeto (ex: via deep copy incompleto).

#### BUG — Sem limite máximo de feeds desativados por ciclo
Um problema de rede temporário (servidor da lista de feeds offline, DNS instável) pode fazer com que centenas de feeds sejam desativados em uma única execução. Não há proteção de "não desative mais de X% dos feeds por ciclo".

---

### 2.2 `motor_scrapers/auto_health_raia2.py`

#### BUG CRÍTICO — Health check executa scrapers reais em produção
A função `process_fonte()` chama `coletar_links_fonte(fonte)` — o scraper real de produção. Isso significa que o health check faz requisições HTTP reais para **todos os sites** monitorados durante a madrugada. Isso pode:
- Acionar rate limiting ou bloqueios em sites sensíveis
- Gerar logs de acesso que confundem análises de tráfego real
- Demorar muito mais do que o esperado (30+ minutos para 100+ fontes)

#### BUG — Auto-cura pode criar loop infinito de estratégias
```python
fonte["estrategia"] = "D"
fonte["url_feed"] = feed_url
```
O health check muda fontes de estratégia "A" para "D" quando detecta falha. Porém, na próxima execução do health check, fontes com estratégia "D" são **ignoradas** (`if not is_active or estrategia not in ("A", "", None)`). Isso é correto como proteção de loop, mas significa que uma fonte nunca volta para estratégia "A" automaticamente. Se o site corrigiu seu scraping, a "auto-cura" é permanente e manual para reverter.

#### BUG — `logging.getLogger("motor_scrapers").setLevel(logging.CRITICAL)` é global
Silenciar o logger do motor_scrapers **globalmente** dentro de um ThreadPoolExecutor afeta todos os outros workers em paralelo. Logs de erros reais de scrapers serão silenciados durante toda a janela de execução do health check.

#### BUG — Race condition no `scrapers.json` (mesmo problema da Raia 1)
Escrita direta em `SCRAPERS_FILE` sem operação atômica.

---

### 2.3 `motor_consolidado/auto_health_raia3.py`

#### BUG CRÍTICO — "Health check" que só loga, nunca corrige
A Raia 3 é fundamentalmente diferente das Raias 1 e 2: ela apenas **loga** alertas (`logger.critical()`), mas não toma **nenhuma ação corretiva**. Não desativa portais com problema, não tenta estratégia alternativa, não envia notificação. 

É um health check que monitora mas não cura — ao contrário do nome "auto-cura" sugerido pelo `setup_health_crons.sh`. O operador precisa verificar manualmente os logs para descobrir problemas, o que derrota o propósito de automação.

#### BUG — Sem timeout por portal
`scrape_portal_titles(portal)` não tem timeout explícito configurado no chamador. Se um dos portais TIER1 pendurar a conexão, a Raia 3 trava indefinidamente. Portais TIER2 nunca são verificados.

#### BUG — Sem tratamento de `TIER1_PORTALS` ou `TIER2_PORTALS` vazios
Se `config_consolidado.py` retornar listas vazias (ex: arquivo deletado, import error), `portals = TIER1_PORTALS + TIER2_PORTALS` resulta em lista vazia e o script termina sem fazer nada, registrando apenas "Auditoria Raia 3 Concluida." — falso positivo de saúde.

---

## 3. Utilitários WordPress

### 3.1 `gestor_wp.py`

#### BUG CRÍTICO — `roteador_ia_imagem` usado sem ser importado
Na linha 111 e 116, a função `roteador_ia_imagem(comando_ia)` é chamada mas **não está importada nem definida** neste arquivo. Qualquer caminho de código que alcance a lógica de fallback de imagem lançará `NameError: name 'roteador_ia_imagem' is not defined`. Isso afeta a publicação de posts oficiais com imagem customizada.

#### BUG CRÍTICO — Publicação sem retry em caso de falha
```python
res = requests.post(f"{WP_URL}/posts", json=payload, headers=AUTH_HEADERS)
if res.status_code == 201: print("[OK]...")
else: print(f"[ERRO WP] {res.text}\n")
```
Não há retry. Se a API retornar 429 (rate limit), 502 ou 503 transitório, o post é **silenciosamente perdido** — nem tentativa de reprocessamento, nem re-enfileiramento.

#### BUG — `resolver_autor_estrito` faz chamada HTTP para CADA POST publicado
```python
res_busca = requests.get(f"{WP_URL}/users?search={termo}&context=edit", headers=AUTH_HEADERS)
```
Esta chamada de busca de usuário ocorre para **todo post oficial publicado**, sem cache. Em um ciclo com 50+ posts governamentais, isso são 50+ chamadas extras à API do WordPress, cada uma retornando a lista completa de usuários e varrendo-os. Seria muito mais eficiente pré-carregar o mapa de usuários uma vez.

#### BUG — `categoria_alvo = cat[0]` ao processar lista
Na linha 162–168, o código converte `cat_id` para lista:
```python
if isinstance(cat_id, list):
    cat_ids = [int(c) for c in cat_id]
else:
    try: cat_ids = [int(cat_id)]
    except: cat_ids = [1]  # fallback silencioso para categoria "Uncategorized"
```
O fallback `cat_ids = [1]` silenciosamente categoriza posts em "Uncategorized" quando há erro de conversão. Isso é difícil de detectar e polui o WordPress com posts mal categorizados.

#### BUG — `date_gmt` usa `datetime.utcnow()` (deprecated no Python 3.12+)
```python
'date_gmt': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
```
`datetime.utcnow()` está deprecated desde Python 3.12. Deve ser substituído por `datetime.now(timezone.utc)`.

---

### 3.2 `gestor_cache.py` — ANÁLISE ESPECIAL: CRESCIMENTO ILIMITADO

#### BUG CRÍTICO — `historico_links.txt` cresce indefinidamente

Este é o bug de **crescimento de arquivo mais grave** do sistema.

**Análise:**
- `salvar_no_cache(url)` apenas **anexa** (`mode='a'`) uma linha ao arquivo
- Nunca há remoção de entradas antigas
- Nunca há compactação ou rotação
- `carregar_cache()` carrega **todo o arquivo** em um `set()` Python a cada execução do motor

**Projeção de crescimento:**
- Se o sistema publica 200 posts/dia × 365 dias = **73.000 URLs/ano**
- Cada URL tem em média ~80 bytes → **~5.8 MB/ano**
- Após 3 anos: ~17 MB de arquivo, ~17 MB de RAM por execução apenas para carregar o cache

Isso pode não parecer enorme, mas:
1. O arquivo é carregado em RAM como `set()` **a cada execução de CADA gaveta** (23 vezes por ciclo do mestre, 11 vezes no scraper = 34 carregamentos por ciclo)
2. O carregamento de um set de 100k strings faz hash de cada elemento — CPU e alocação de memória significativas
3. **Sem cleanup nunca**, a performance degrada gradualmente e é invisível até causar problema grave

**Solução correta:**
```python
# Implementar limpeza por janela de tempo (ex: manter apenas últimos 30 dias)
# ou usar SQLite com índice, ou Redis
MAX_CACHE_ENTRIES = 100_000
MAX_CACHE_AGE_DAYS = 60
```

#### BUG — Caminho relativo `ARQUIVO_CACHE = "historico_links.txt"`
O cache usa caminho relativo, portanto o arquivo é criado/lido no **diretório atual no momento da execução**. Se o script for chamado de diretórios diferentes (o que acontece porque `agendador_mestre.sh` faz `cd /home/bitnami` mas scripts individuais podem ser chamados de outros locais), o cache pode criar múltiplos arquivos em locais diferentes, cada um com subconjunto dos links processados → **duplicatas publicadas**.

#### BUG — Sem lock de arquivo — race condition de escrita
`salvar_no_cache` e `carregar_cache` não usam nenhum mecanismo de lock. Se dois workers (ex: via ThreadPoolExecutor) chamarem `salvar_no_cache` simultaneamente, podem ter writes entrelaçados no arquivo, corrompendo linhas.

---

### 3.3 `mapear_wp.py` e `mapear_autores.py`

#### PROBLEMA DE SEGURANÇA — `context=edit` expõe dados sensíveis
```python
requests.get(f"{WP_URL}/users?per_page=100&context=edit", headers=AUTH_HEADERS)
```
O parâmetro `context=edit` retorna campos sensíveis dos usuários (e-mail, capabilities, etc.) que não são necessários para mapear IDs. Esses dados ficam impressos no terminal/logs.

#### BUG — Paginação ausente
Ambos os scripts usam `per_page=100`. Se o WordPress tiver mais de 100 categorias ou usuários, os dados truncados passarão despercebidos (não há verificação do header `X-WP-Total`).

---

### 3.4 `atualizar_menu.py`

#### BUG DE SEGURANÇA CRÍTICO — Credencial hardcoded com fallback inseguro
```python
WP_APP_PASSWORD = os.getenv("WP_APP_PASS", "nWgboohRWZGLv2d7ebQgkf80")
```
A senha de aplicativo do WordPress está hardcoded como **fallback padrão** do `os.getenv()`. Se a variável de ambiente `WP_APP_PASS` não estiver configurada (ex: em um ambiente novo, ou após perda do `.env`), o sistema silenciosamente usa a credencial exposta no código-fonte. **Esta senha deve ser considerada comprometida** pois aparece em múltiplos arquivos do repositório.

#### BUG DE SEGURANÇA CRÍTICO — Senha do banco de dados hardcoded
```python
'-p' + os.getenv("DB_PASS", "d0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b")
```
A senha do MariaDB (`d0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b`) está hardcoded em **pelo menos 6 arquivos diferentes**:
- `atualizar_menu.py`
- `fix_theme_settings.py`
- `configurar_adsense.py`
- `corrigir_demo_restante.py`
- `find_english_text.py`
- `fix_all_remaining.py`

Esta é a **maior vulnerabilidade de segurança do sistema**. Qualquer pessoa com acesso ao código-fonte tem acesso ao banco de dados de produção.

#### BUG — SQL via subprocess com strings interpoladas (SQL Injection)
```python
db_cmd = [..., '-e']
for q in cache_queries:
    result = subprocess.run(db_cmd + [q], ...)
```
Embora as queries sejam hardcoded neste caso, o padrão de construir queries SQL por interpolação de strings (usado em `configurar_adsense.py`, `fix_all_remaining.py`) cria superfície para SQL injection se qualquer input externo (ex: conteúdo de post, URL) for incorporado.

Exemplo crítico em `limpar_demos()`:
```python
escaped = content.replace("\\", "\\\\").replace("'", "\\'")
executar_sql(f"UPDATE ... SET meta_value='{escaped}' ...")
```
Escape manual de aspas em SQL é **inseguro e desnecessário** — `subprocess.run` com lista de argumentos e prepared statements (`%s`) evitariam o problema completamente.

---

### 3.5 `fix_theme_settings.py`

#### BUG CRÍTICO — Senha hardcoded em formato `-p` concatenado (processo visível)
```python
DB_CMD = ['/opt/bitnami/mariadb/bin/mariadb', '-u', 'bn_wordpress',
          '-pd0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b', ...]
```
Passar a senha como argumento `-p<senha>` em `subprocess.run()` torna a senha **visível no `ps aux`** de qualquer usuário no servidor. A forma correta é usar variável de ambiente `MYSQL_PWD` ou arquivo de configuração `.my.cnf`.

#### BUG — Parser de PHP serializado via regex é frágil
A função `php_replace_value()` usa regex para modificar strings PHP serializadas:
```python
pattern = f'(s:\\d+:"{key}";)s:\\d+:"[^"]*";'
```
Este regex não funciona corretamente se:
- O valor contiver aspas escapadas (`\"`)
- O valor contiver bytes especiais UTF-8 (muito comum em tema PT-BR)
- O comprimento declarado em `s:N:` não corresponder ao comprimento em bytes do conteúdo (UTF-8 multibyte)

O PHP conta bytes, não caracteres. Uma string `"São Paulo"` tem 9 caracteres mas 11 bytes em UTF-8 — o regex vai calcular `s:9:` mas o PHP espera `s:11:`, corrompendo a estrutura serializada e **quebrando todas as configurações do tema**.

O script corretamente delega para um script PHP no final, mas as modificações via regex Python já terão sido aplicadas ao `new_settings` **antes** de entrar no PHP. Se as modificações via regex forem incorretas, o PHP receberá dados já corrompidos.

---

### 3.6 `configurar_adsense.py`

#### BUG DE SEGURANÇA — Publisher ID exposto no código-fonte
```python
# (em injetar_adsense_decoder.py)
PUB_ID = "ca-pub-7252039297007966"
```
O Publisher ID do AdSense está hardcoded. Embora seja menos sensível que credenciais de DB, pode ser usado para domain spoofing em ads.txt.

#### BUG — `configurar_article_ads()` aplica `replace('[tdb_single_content', ...)` múltiplas vezes
```python
content = content.replace('[tdb_single_content', 
    f'[tdb_single_content article_top_ad="{encoded_code}"')
# depois:
content = content.replace('[tdb_single_content',
    f'[tdb_single_content article_inline_ad="{encoded_code}" inline_ad_paragraph="3"')
# depois:
content = content.replace('[tdb_single_content',
    f'[tdb_single_content article_bottom_ad="{encoded_code}"')
```
Se o template tiver **mais de uma ocorrência** de `[tdb_single_content` (múltiplos elementos de conteúdo), **todos serão modificados**. Além disso, como cada `replace` já inseriu o novo prefixo, a segunda chamada encontra `[tdb_single_content article_top_ad="..."` e o substitui novamente, causando **atributos duplicados e aninhados** no shortcode.

#### BUG — Escrita do backup não usa `ensure_ascii=False`
```python
with open(backup_file, "w") as f:
    json.dump(backups, f, indent=2)
```
Sem `ensure_ascii=False`, caracteres especiais nos dados de backup (acentos, caracteres UTF-8 do conteúdo do WordPress) serão escapados como `\uXXXX`. O backup JSON é tecnicamente correto, mas ilegível e potencialmente maior. Na restauração, o `executar_sql` recebe strings com escapes Unicode ao invés do texto original.

---

### 3.7 `injetar_adsense_decoder.py`

#### BUG — `cursor.fetchall()` carrega todos os postmeta em memória
```python
cursor.execute("SELECT post_id, meta_value FROM wp_7_postmeta WHERE meta_key='tdc_content'")
rows = cursor.fetchall()
```
Sem `LIMIT` ou paginação. Em um site com centenas de templates e posts com `tdc_content`, isso pode retornar um volume enorme de dados em uma única consulta. `tdc_content` é um campo de shortcodes muito extenso (kilobytes por registro).

---

## 4. Scripts de Correção

### 4.1 `corrigir_acentos.py`

#### BUG — Correção de encoding apenas em 2 arquivos hardcoded
```python
arquivos = ['/home/bitnami/motor_mestre.py', '/home/bitnami/motor_scrapers.py']
```
O script só verifica dois arquivos. Outros arquivos Python do sistema (gestor_wp.py, config_categorias.py, etc.) que possam ter encoding errado são ignorados.

#### BUG — Diagnóstico sem correção real da causa raiz
Este script existe porque os arquivos foram editados em um ambiente com encoding diferente (provavelmente Windows/Latin-1 ou um editor remoto mal configurado). Corrigir o sintoma (converter o arquivo) sem corrigir a causa (configurar o ambiente de edição) garante que o problema recorrirá.

#### BUG LÓGICO — Conversão Latin-1 → UTF-8 pode ser destrutiva
```python
texto = dados.decode('latin-1')
with open(arq, 'w', encoding='utf-8') as f:
    f.write(texto)
```
Se o arquivo **não é** Latin-1 mas alguma outra codificação (ex: Windows-1252, ISO-8859-15), a decodificação forçada como Latin-1 mapeará bytes incorretamente e produzirá caracteres errados. O script assume que qualquer arquivo não-UTF-8 é Latin-1, o que é uma suposição arriscada.

---

### 4.2 `corrigir_demo_restante.py`

#### BUG CRÍTICO — `import os` está depois de ser usado
```python
# linha 19:
'-p' + os.getenv("DB_PASS", "...")  # usa os
# linha 26:
import os  # importa os
```
O `os.getenv()` na linha 19 referencia `os` antes do `import os` na linha 26. Isso causa `NameError: name 'os' is not defined` na **inicialização do módulo**. O script **não funciona como está**.

#### BUG — SQL via arquivo temporário com senha hardcoded visível
O script escreve SQL em `/tmp/fix_demo.sql` e passa a senha como argumento de CLI. Tanto o arquivo `/tmp/fix_demo.sql` (legível por outros processos/usuários) quanto o argumento de processo expõem dados sensíveis.

#### BUG — Base64 de strings URL-encoded pode ter colisões
A lógica de substituição converte texto para `urllib.parse.quote()` e depois para base64:
```python
old_b64_q = base64.b64encode(urllib.parse.quote(old_label).encode()).decode()
```
Se `urllib.parse.quote()` gerar encodings diferentes (ex: espaço como `%20` vs `+`), a busca não encontrará o padrão e a substituição falhará silenciosamente. O script reporta sucesso (`0 substituições`) sem indicar o motivo real.

---

### 4.3 `corrigir_gestor.py`

#### BUG DE DESIGN — Script que injeta código em arquivo de produção
```python
with open(arquivo, 'a', encoding='utf-8') as f:
    f.write(nova_funcao)
```
Este script **modifica o código-fonte em produção** via append. É evidência de que `gestor_wp.py` foi alterado iterativamente durante operação, o que é uma prática extremamente arriscada. Uma execução dupla do script (sem a verificação de idempotência) poderia adicionar a função duplicada, mas a verificação existe — porém o código injetado já está presente na versão atual do `gestor_wp.py`, tornando este script obsoleto e perigoso de rodar novamente em ambientes inconsistentes.

---

### 4.4 `corrigir_posts_existentes.py`

#### BUG CRÍTICO — Carrega TODOS os posts em memória
```python
def fetch_all_posts():
    cur.execute(f"SELECT ID, post_title, post_content, post_excerpt FROM {TP}posts 
                  WHERE post_status='publish' AND post_type='post' ORDER BY ID ASC")
    posts = cur.fetchall()
```
Sem `LIMIT`. Em produção com 10.000+ posts publicados, isso carrega **todo o conteúdo HTML de todos os posts** em RAM simultaneamente. `post_content` pode ter 10-50KB por post → 500MB–5GB de RAM para um site com muitos posts. Este é um dos principais consumidores de memória que justificam `aumentar_memoria.sh`.

#### BUG CRÍTICO — Gemini API sem rate limiting adequado
```python
if needs_excerpt_fix(excerpt):
    update_excerpt_db(pid, generate_excerpt(title, content))
    time.sleep(0.3)  # apenas 0.3 segundos!
```
O Gemini free tier tem limite de **15 requisições por minuto** (confirmado no comentário do `regerar_excerpts.py`). Com `sleep(0.3)`, o script tenta fazer **200 requisições por minuto** — 13x acima do limite. Isso vai:
1. Retornar erros 429 em massa
2. Fazer o fallback de frases simples para todos os excerpts
3. A função de fallback silencia o erro com apenas um `logger.warning`, então o operador não saberá que Gemini falhou

#### BUG — `trash_post()` não verifica se post já está em trash
```python
def trash_post(post_id):
    r = SESSION.delete(f"{WP_URL}/wp-json/wp/v2/posts/{post_id}", ...)
    return r.status_code in [200, 201]
```
Deletar via API WP move para Trash (status 200). Deletar novamente um post já na Trash remove permanentemente (também status 200). Se o script for executado duas vezes, duplicatas identificadas na segunda execução que já estão na Trash serão **deletadas permanentemente**.

#### BUG — Detecção de categoria por palavras-chave é muito primitiva
```python
def detect_better_category(title, content):
    text = (title + ' ' + content[:500]).lower()
    scores = {}
    for cat, kws in CATEGORY_MAP.items():
        s = sum(1 for kw in kws if kw in text)
```
A correspondência é por substring simples. "esporte" aparece em "transporte" → falso positivo. "saude" aparece em "saudade" → falso positivo. Posts serão recategorizados incorretamente de forma silenciosa.

#### BUG — `update_title_db` e `update_excerpt_db` criam nova conexão para CADA post
```python
def update_title_db(post_id, title):
    conn = get_db()  # nova conexão!
    cur = conn.cursor()
    cur.execute(...)
    conn.commit(); cur.close(); conn.close()
```
Para 10.000 posts, isso cria **10.000 conexões MySQL**, cada uma com overhead de handshake TCP + autenticação. Deveria usar uma conexão persistente ou connection pool.

---

### 4.5 `regerar_excerpts.py`

#### BUG — `time.sleep(4)` entre requisições: ainda insuficiente para volume alto
Com sleep de 4 segundos, o script faz **15 requisições por minuto** — exatamente no limite do Gemini free tier. Um único timeout ou lentidão de rede desfaz o throttle, pois o sleep é fixo independente do tempo da chamada. O correto seria medir o tempo total da chamada e compensar.

#### BUG — Sem checkpoint/retomada
Se o script for interrompido após processar 5.000 de 10.000 posts, não há como retomá-lo de onde parou. A query `fetch_posts_sem_excerpt()` vai retornar os mesmos posts sem excerpt (já gerados serão reenviados ao Gemini e reescritos). Deveria persistir um estado de progresso.

---

### 4.6 `renomear_categoria.py`

#### BUG CRÍTICO — `base64` importado implicitamente mas não declarado
```python
auth_headers = {
    'Authorization': f'Basic {base64.b64encode(...).decode()}',
    ...
}
```
O módulo `base64` é usado na linha 30 mas **não está importado** no arquivo. O script lança `NameError: name 'base64' is not defined` imediatamente ao ser executado.

#### BUG — `requests` também não está importado
`requests.get()` é chamado na função `alterar_nome_categoria()` mas `import requests` está ausente.

**Conclusão: `renomear_categoria.py` não funciona em absoluto.**

#### BUG — Mensagem de sucesso hardcoded menciona "Continentes"
```python
print("Todos os posts já publicados que estavam em 'Continentes' agora mostram 'Internacional'!")
```
Esta mensagem é hardcoded para um caso específico. Se o script for reutilizado para renomear outras categorias, a mensagem será incorreta e enganosa.

---

### 4.7 `reverter_autoria.py`

#### BUG CRÍTICO — Loop potencialmente infinito
```python
while True:
    res = requests.get(f"{WP_URL}/posts?author={id_tiago}&per_page=50", ...)
    if res.status_code != 200 or not res.json(): break
    for p in res.json():
        requests.post(f"{WP_URL}/posts/{p['id']}", json={'author': id_redacao}, ...)
```
**Este loop não avança as páginas.** Ele sempre busca a primeira página de posts do autor `id_tiago`. Após transferir os 50 da primeira página, a API retorna os próximos 50... mas o autor desses ainda é `id_tiago` porque a atualização pode não ter sido refletida ainda (cache WordPress). O loop pode girar indefinidamente ou até a API retornar erro de rate limit.

O correto seria usar `?page=N` com incremento, ou verificar se os IDs retornados são iguais à iteração anterior.

#### BUG — `res_me.json()` chamado duas vezes sem cache
```python
id_redacao = res_me.json().get('id')
nome_redacao = res_me.json().get('name')
```
`requests.Response.json()` faz parse do JSON a cada chamada. Não é um erro grave, mas é ineficiente. Se a resposta não for JSON válido (erro de rede, HTML de erro), ambas as linhas lançarão exceção sem mensagem útil.

#### BUG — `except: pass` silencia todas as exceções
```python
try:
    with open(caminho, 'r', ...) as f: cont = f.read()
    with open(caminho, 'w', ...) as f: f.write(re.sub(...))
    print("2. Arquivo de configuracao blindado...")
except: pass
```
Falha ao modificar `config_categorias.py` é silenciada completamente. O sistema continua usando o ID errado sem nenhuma indicação.

---

### 4.8 `find_english_text.py`

#### BUG — Script de diagnóstico com credenciais hardcoded em produção
```python
DB_CMD = [..., '-pd0e339d8be89d2cfe6d7c210a51ed0de203b386a273d647fc144a67b242e234b', ...]
```
Scripts de diagnóstico/análise não deveriam conter credenciais hardcoded. Se compartilhados para debug com terceiros, expõem o banco de produção.

#### PROBLEMA DE DESIGN — Regex de base64 tem falsos positivos
```python
b64_pattern = r'([a-z_]+)="((?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?)"'
```
Este regex **não aceita base64 sem padding** (comprimento múltiplo de 4 sem `=`). Muitas strings base64 válidas sem padding serão ignoradas. Além disso, hashes MD5/SHA em hexadecimal e UUIDs podem ser confundidos como base64.

---

### 4.9 `fix_all_remaining.py`

#### BUG CRÍTICO — `td_011_settings` tratado como JSON, mas é PHP serializado
```python
settings = json.loads(result_opts.stdout.strip())
```
O campo `td_011_settings` do Newspaper theme é armazenado como **PHP serializado** (`a:5:{s:...}`), **não como JSON**. `json.loads()` vai lançar `json.JSONDecodeError` imediatamente. O próprio script captura isso:
```python
except json.JSONDecodeError as e:
    print(f"  Settings não é JSON: {str(e)[:100]}")
```
Portanto, **todo o STEP 6 (corrigir top bar) nunca funciona**, e o script imprime um erro esperado e continua como se estivesse tudo bem.

#### BUG — `subprocess.run(DB_CMD_BASE, stdin=open('/tmp/fix_all_english.sql'), ...)` — handle não fechado
```python
result = subprocess.run(DB_CMD_BASE, stdin=open('/tmp/fix_all_english.sql'), ...)
```
O file handle aberto por `open()` nunca é explicitamente fechado. Em Python, o garbage collector cuida disso eventualmente, mas em scripts de longa duração pode causar `ResourceWarning` e, em sistemas com limite de file descriptors baixo, `OSError: [Errno 24] Too many open files`.

---

### 4.10 `analyze_tdc.py`

#### BUG — Hardcoded para arquivo que pode não existir
```python
filename = '/home/bitnami/homepage_tdc_tier1.txt'
with open(filename, 'r', encoding='utf-8', errors='replace') as f:
```
Não há verificação se o arquivo existe. Se não existir, `FileNotFoundError` com traceback sem mensagem amigável. Este parece ser um script de análise pontual que foi deixado em produção sem cleanup.

---

## 5. Extratores de Conteúdo

### 5.1 Duplicação: `/home/bitnami/extrator_conteudo.py` vs `/home/bitnami/motor_scrapers/extrator_conteudo.py`

**Estes são dois arquivos COMPLETAMENTE DIFERENTES com o mesmo nome:**

| Aspecto | Raiz (`extrator_conteudo.py`) | Motor Scrapers (`motor_scrapers/extrator_conteudo.py`) |
|---------|-------------------------------|-------------------------------------------------------|
| Dependências | `requests`, `BeautifulSoup` | `requests`, `BeautifulSoup`, `newspaper3k`, `chardet` |
| Retorno | `str` (texto puro) | `dict` (titulo, conteudo, autor, data, imagem, metodo) |
| Fallbacks | Nenhum | newspaper3k → BS4 → Jina Reader |
| Encoding | `res.content` direto | `chardet` para detecção automática |
| Limite | 25.000 chars | 10.000 chars (BS4), 15.000 (Jina) |
| Logging | `print()` | `logging` estruturado |

**Problemas:**
1. Código duplicado com implementações divergentes — manutenção dupla, bugs podem ser corrigidos em uma versão mas não na outra
2. O `extrator_conteudo.py` raiz é a versão **inferior** (sem encoding detection, sem fallbacks, sem estrutura de retorno)
3. Scripts que importam um podem acidentalmente importar o outro dependendo do `sys.path`

---

### 5.2 `extrator_conteudo.py` (raiz)

#### BUG — Sem detecção de encoding
```python
soup = BeautifulSoup(res.content, 'html.parser')
```
`res.content` são bytes brutos. O BeautifulSoup detectará o encoding pelo meta charset, mas sites com encoding incorreto no header ou meta tag errada resultarão em texto com caracteres corrompidos nos posts publicados. Esta é uma **causa raiz dos problemas de acentuação** que justificam `corrigir_acentos.py`.

#### BUG — `requests.get()` sem tratamento de status code
```python
res = requests.get(url, headers=headers, timeout=20)
soup = BeautifulSoup(res.content, 'html.parser')
```
Se o servidor retornar 404, 403 ou 500, o BeautifulSoup vai parsear o HTML de erro e retornar o texto da página de erro como "conteúdo da notícia". Posts com "404 Not Found" seriam publicados.

#### BUG — Anti-CVV incompleto
```python
if "Centro de Valorização da Vida" not in texto_p and "telefone 188" not in texto_p:
```
O filtro é case-sensitive e exige a string exata. "centro de valorização da vida" (minúsculas) ou "CVV" ou "(188)" passariam pelo filtro. Conteúdo sensível poderia ser publicado.

---

### 5.3 `motor_scrapers/extrator_conteudo.py`

#### BUG — `_fetch_html` retorna `html, html` (tupla duplicada)
```python
return html, html
```
A função retorna a mesma string duas vezes como `(html, html_raw)`. `html_raw` nunca é diferente de `html` porque o decode já foi aplicado em ambos. O segundo valor da tupla é inútil e confuso.

#### BUG — Jina Reader sem autenticação
```python
jina_url = f"https://r.jina.ai/{url}"
```
A API Jina Reader tem limites de rate para uso não autenticado. Em produção com centenas de URLs/dia sendo enviadas ao Jina como último fallback, o serviço vai throttlear e retornar erros. O script trata isso como `logger.warning` e retorna `None`, mas sem alertar que o Jina está sendo sobreconsumido.

#### BUG — `conteudo` truncado a 10.000 chars no BS4 mas não no newspaper3k
```python
# BS4:
"conteudo": texto[:10000],
# newspaper3k:
"conteudo": texto,  # sem limite!
```
Inconsistência: dependendo do método usado, o conteúdo pode ter tamanhos muito diferentes. Posts gerados via newspaper3k podem ter conteúdo muito maior que os gerados via BS4, causando inconsistência no WordPress.

---

### 5.4 `scrapers_nativos.py`

#### BUG — `fetch()` retorna `None` implícito em caso de sucesso incompleto
```python
async def fetch(client, url):
    for attempt in range(3):
        try:
            r = await client.get(...)
            if r.status_code in [200, 202, 403]:
                return r.text
        except Exception:
            if attempt == 2: return ""
            await asyncio.sleep(1)
    # sem return aqui!
```
Se após 3 tentativas nenhuma lançar exceção mas nenhuma retornar status 200/202/403 (ex: todos retornam 429 ou 503), a função retorna `None` implicitamente. O chamador espera uma string e recebe `None`, causando `TypeError` em `BeautifulSoup(html, "lxml")`.

#### BUG — Status code 403 tratado como sucesso
```python
if r.status_code in [200, 202, 403]:
    return r.text
```
Retornar o conteúdo de uma resposta 403 (Forbidden) é incorreto. O site bloqueou o scraper e o HTML retornado é uma página de erro de acesso ou CAPTCHA, não notícias reais. Isso gera "artigos" com conteúdo de erro sendo publicados.

#### BUG — `scrape_omelete()` usa endpoint de API não documentado
```python
text = await fetch(client, "https://www.omelete.com.br/api/")
```
Este endpoint não é oficial/documentado. Pode mudar ou ser removido sem aviso. Não há fallback se o JSON não tiver o formato esperado (a exceção é silenciada com `except: pass`).

#### BUG — `asyncio.get_event_loop()` deprecated e perigoso
```python
loop = asyncio.get_event_loop()
return loop.run_until_complete(_run())
```
`asyncio.get_event_loop()` está deprecated desde Python 3.10. Em Python 3.12+, lança `DeprecationWarning` e pode falhar com `RuntimeError` se chamado em contexto sem event loop ativo. O correto é usar `asyncio.run(_run())`.

#### BUG — `nest_asyncio.apply()` no topo do módulo
```python
nest_asyncio.apply()
```
Aplicar `nest_asyncio` globalmente no import do módulo afeta todo o processo Python, não apenas este módulo. Isso pode causar comportamentos inesperados em outros módulos async carregados no mesmo processo (ex: httpx, asyncio do motor principal).

---

## 6. Diagnóstico Sistêmico

### 6.1 Por que `aumentar_memoria.sh` existe — Cadeia de causas

```
gestor_cache.py carrega historico_links.txt inteiro em RAM
    ↓ chamado 34× por ciclo (23 gavetas + 11 scrapers)
    
corrigir_posts_existentes.py faz fetchall() de TODOS os posts
    ↓ pico de RAM de centenas de MB
    
auto_health_raia1.py usa ThreadPoolExecutor(20) × feedparser em RAM
    ↓ 20 feeds grandes em memória simultânea
    
tema Newspaper serializa td_011_settings (>100KB) em cada request
    ↓ PHP consome RAM para cada pageview durante picos de publicação
    
→ WordPress excede memory_limit padrão (256MB)
→ aumentar_memoria.sh eleva para 1GB/2GB como paliativo
```

### 6.2 Por que `corrigir_acentos.py` existe — Cadeia de causas

```
Scripts editados em Windows/editor com encoding Latin-1
    ↓ ou SSH com configuração de terminal errada
    
Arquivos salvos com bytes Latin-1 (0xE3 = 'ã', mas em UTF-8 é 2 bytes)
    ↓
Python tenta abrir como UTF-8 → UnicodeDecodeError
    ↓
Motor para de funcionar
    ↓
corrigir_acentos.py como correção de emergência
```

### 6.3 Por que existem tantos `corrigir_*` e `fix_*` scripts

O site foi migrado de um **tema demo do Newspaper** para produção sem um processo de migração estruturado. Os scripts de correção são evidência de migração incremental ad hoc:

1. Demo importado com conteúdo em inglês → `corrigir_demo_restante.py`, `find_english_text.py`, `fix_all_remaining.py`
2. Menus com categorias demo → `fix_custom_menu.py`, `atualizar_menu.py`, `atualizar_menu_items.py`
3. Posts publicados com autores errados → `reverter_autoria.py`
4. Posts sem excerpts → `regerar_excerpts.py`, `corrigir_posts_existentes.py`
5. Configurações de tema corrompidas → `fix_theme_settings.py`

**Cada script é a prova de um bug diferente no processo de publicação ou de migração. Os sintomas foram tratados, não as causas.**

---

## 7. Tabela de Prioridade de Correções

| Prioridade | Arquivo | Bug | Impacto |
|-----------|---------|-----|---------|
| 🔴 CRÍTICO | Múltiplos | Credenciais DB hardcoded em 6+ arquivos | Acesso não autorizado ao BD |
| 🔴 CRÍTICO | `gestor_wp.py` | `roteador_ia_imagem` não importada | NameError em publicação |
| 🔴 CRÍTICO | `renomear_categoria.py` | `base64` e `requests` não importados | Script inoperante |
| 🔴 CRÍTICO | `corrigir_demo_restante.py` | `import os` após uso de `os` | NameError na inicialização |
| 🔴 CRÍTICO | `gestor_cache.py` | Arquivo sem rotação, caminho relativo | Crescimento ilimitado + race condition |
| 🔴 CRÍTICO | `agendador_mestre.sh` | Sem lock file | Execuções paralelas e duplicatas |
| 🔴 CRÍTICO | `auto_health_raia1.py` | Escrita não-atômica em `feeds.json` | Corrupção de arquivo de configuração |
| 🔴 CRÍTICO | `corrigir_posts_existentes.py` | `fetchall()` sem LIMIT | OOM com base grande |
| 🔴 CRÍTICO | `reverter_autoria.py` | Loop infinito sem paginação | Loop eterno na API |
| 🟠 ALTO | `configurar_adsense.py` | `replace()` múltiplo em shortcode | Atributos duplicados nos templates |
| 🟠 ALTO | `fix_theme_settings.py` | Regex PHP serialized com chars multibyte | Configurações de tema corrompidas |
| 🟠 ALTO | `fix_all_remaining.py` | `json.loads()` em PHP serialized | STEP 6 nunca funciona |
| 🟠 ALTO | `scrapers_nativos.py` | Status 403 tratado como sucesso | Conteúdo de erro publicado |
| 🟠 ALTO | `scrapers_nativos.py` | `fetch()` retorna None implícito | TypeError nos scrapers |
| 🟠 ALTO | `corrigir_posts_existentes.py` | Gemini sem throttle real | 429s em massa, excerpts via fallback |
| 🟡 MÉDIO | `aumentar_memoria.sh` | Reinício total sem graceful | Downtime do site |
| 🟡 MÉDIO | `auto_health_raia2.py` | Logger global silenciado no health check | Logs de erros reais perdidos |
| 🟡 MÉDIO | `auto_health_raia3.py` | Sem ação corretiva, apenas log | "Health check" que não cura |
| 🟡 MÉDIO | `gestor_wp.py` | Busca de autor por HTTP em cada post | Rate limiting e latência |
| 🟡 MÉDIO | `motor_scrapers/extrator_conteudo.py` | Jina sem auth + truncagem inconsistente | Throttle silencioso |
| 🟡 MÉDIO | Extratores | Dois arquivos com mesmo nome e APIs diferentes | Confusão de import |
| 🟢 BAIXO | `gerar_backup_codigos.sh` | Sem timestamp, sem rotação, sem subdiretórios | Backup incompleto/sobrescrito |
| 🟢 BAIXO | `mapear_wp.py` | Sem paginação (`per_page=100`) | Dados truncados silenciosamente |
| 🟢 BAIXO | Agendadores | Sem verificação de exit code do Python | Falhas silenciosas por gaveta |
| 🟢 BAIXO | `regerar_excerpts.py` | Sem checkpoint de progresso | Reprocessamento completo em retomada |

---

*Total de issues encontrados: 68 bugs e problemas documentados em 31 arquivos.*
