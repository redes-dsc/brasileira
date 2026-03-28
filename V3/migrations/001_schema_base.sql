BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memoria_agentes (
    id BIGSERIAL PRIMARY KEY,
    agente TEXT NOT NULL,
    tipo TEXT NOT NULL,
    conteudo JSONB NOT NULL,
    embedding VECTOR(1536),
    relevancia_score DOUBLE PRECISION DEFAULT 0.5,
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    expira_em TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS llm_health_log (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    latency_ms INTEGER NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd DOUBLE PRECISION,
    error_type TEXT,
    error_message TEXT,
    task_type TEXT NOT NULL,
    tier TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS artigos (
    id BIGSERIAL PRIMARY KEY,
    article_id TEXT,
    wp_post_id INTEGER,
    url_hash TEXT UNIQUE NOT NULL,
    titulo TEXT NOT NULL,
    resumo TEXT,
    conteudo TEXT,
    url_fonte TEXT NOT NULL,
    editoria TEXT,
    categoria_wp_id INTEGER,
    fonte_id INTEGER,
    fonte_nome TEXT,
    relevancia_score DOUBLE PRECISION,
    urgencia TEXT DEFAULT 'NORMAL',
    status TEXT DEFAULT 'publicado',
    imagem_url TEXT,
    imagem_tier TEXT,
    embedding VECTOR(1536),
    metadata JSONB DEFAULT '{}',
    publicado_em TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fontes (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL DEFAULT 'rss',
    tier TEXT NOT NULL DEFAULT 'padrao',
    grupo TEXT DEFAULT 'geral',
    ativa BOOLEAN DEFAULT TRUE,
    config_scraper JSONB,
    polling_interval_min INTEGER DEFAULT 30,
    ultimo_sucesso TIMESTAMPTZ,
    ultimo_erro TEXT,
    falhas_consecutivas INTEGER DEFAULT 0,
    criada_em TIMESTAMPTZ DEFAULT NOW(),
    atualizada_em TIMESTAMPTZ DEFAULT NOW()
);

COMMIT;
