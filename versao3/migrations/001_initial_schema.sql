CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS artigos (
    id SERIAL PRIMARY KEY,
    wp_post_id INTEGER UNIQUE,
    url_fonte TEXT NOT NULL,
    url_hash CHAR(64) UNIQUE,
    titulo TEXT NOT NULL,
    editoria VARCHAR(50),
    urgencia VARCHAR(20),
    score_relevancia DOUBLE PRECISION,
    publicado_em TIMESTAMPTZ DEFAULT NOW(),
    revisado BOOLEAN DEFAULT FALSE,
    imagem_aplicada BOOLEAN DEFAULT FALSE,
    fonte_nome VARCHAR(200)
);

CREATE INDEX IF NOT EXISTS idx_artigos_url_hash ON artigos(url_hash);
CREATE INDEX IF NOT EXISTS idx_artigos_editoria ON artigos(editoria);
CREATE INDEX IF NOT EXISTS idx_artigos_publicado ON artigos(publicado_em DESC);

CREATE TABLE IF NOT EXISTS fontes (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    url TEXT UNIQUE NOT NULL,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('rss', 'scraper')),
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('vip', 'padrao', 'secundario')),
    config_scraper JSONB,
    polling_interval_min INTEGER DEFAULT 30,
    ultimo_sucesso TIMESTAMPTZ,
    ultimo_erro TEXT,
    ativa BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_fontes_tipo_tier ON fontes(tipo, tier);

CREATE TABLE IF NOT EXISTS memoria_agentes (
    id SERIAL PRIMARY KEY,
    agente VARCHAR(50) NOT NULL,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('semantica', 'episodica')),
    conteudo JSONB NOT NULL,
    embedding vector(1536),
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    relevancia_score DOUBLE PRECISION DEFAULT 0.5,
    ttl_dias INTEGER DEFAULT 90
);

CREATE INDEX IF NOT EXISTS idx_memoria_agente_tipo ON memoria_agentes(agente, tipo);
CREATE INDEX IF NOT EXISTS idx_memoria_embedding_hnsw ON memoria_agentes USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS llm_health_log (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL,
    latency_ms INTEGER,
    error_type VARCHAR(50),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_recent ON llm_health_log(provider, model, timestamp DESC);
