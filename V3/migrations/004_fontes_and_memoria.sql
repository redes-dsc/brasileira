-- V3 fontes table (matches worker_pool feed_scheduler.py query)
CREATE TABLE IF NOT EXISTS fontes (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(500) NOT NULL,
    url TEXT NOT NULL,
    tipo VARCHAR(50) DEFAULT 'rss',
    tier VARCHAR(20) DEFAULT 'padrao',
    config_scraper JSONB DEFAULT '{}' ::jsonb,
    polling_interval_min INTEGER DEFAULT 30,
    ultimo_sucesso TIMESTAMP,
    ultimo_erro TIMESTAMP,
    ativa BOOLEAN DEFAULT TRUE
);

-- V3 memoria_agentes table (matches shared/memory.py)
CREATE TABLE IF NOT EXISTS memoria_agentes (
    id SERIAL PRIMARY KEY,
    agente VARCHAR(100) NOT NULL,
    tipo VARCHAR(20) NOT NULL,
    conteudo JSONB NOT NULL DEFAULT '{}' ::jsonb,
    embedding vector(384),
    relevancia_score NUMERIC(4,3) DEFAULT 0.5,
    criado_em TIMESTAMP DEFAULT NOW(),
    expira_em TIMESTAMP
);

CREATE EXTENSION IF NOT EXISTS vector;

-- Indices
CREATE INDEX IF NOT EXISTS idx_fontes_ativa ON fontes(ativa);
CREATE INDEX IF NOT EXISTS idx_fontes_tipo ON fontes(tipo);
CREATE INDEX IF NOT EXISTS idx_memoria_agente ON memoria_agentes(agente);
CREATE INDEX IF NOT EXISTS idx_memoria_tipo ON memoria_agentes(tipo);
