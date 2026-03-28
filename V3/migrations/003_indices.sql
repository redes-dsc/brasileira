BEGIN;

CREATE INDEX IF NOT EXISTS idx_memoria_agentes_agente_tipo
  ON memoria_agentes (agente, tipo);

CREATE INDEX IF NOT EXISTS idx_memoria_agentes_criado_em
  ON memoria_agentes (criado_em DESC);

CREATE INDEX IF NOT EXISTS idx_llm_health_log_provider_model_time
  ON llm_health_log (provider, model, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_artigos_publicado_em
  ON artigos (publicado_em DESC);

CREATE INDEX IF NOT EXISTS idx_artigos_editoria
  ON artigos (editoria);

CREATE INDEX IF NOT EXISTS idx_artigos_wp_post_id
  ON artigos (wp_post_id);

CREATE INDEX IF NOT EXISTS idx_artigos_fonte_id
  ON artigos (fonte_id);

CREATE INDEX IF NOT EXISTS idx_artigos_url_hash
  ON artigos (url_hash);

CREATE INDEX IF NOT EXISTS idx_fontes_url
  ON fontes (url);

CREATE INDEX IF NOT EXISTS idx_fontes_tipo_tier
  ON fontes (tipo, tier);

CREATE INDEX IF NOT EXISTS idx_fontes_ativa
  ON fontes (ativa) WHERE ativa = TRUE;

-- Vector similarity indexes (HNSW for fast approximate search)
CREATE INDEX IF NOT EXISTS idx_memoria_agentes_embedding_hnsw
  ON memoria_agentes USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_artigos_embedding_hnsw
  ON artigos USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

COMMIT;
