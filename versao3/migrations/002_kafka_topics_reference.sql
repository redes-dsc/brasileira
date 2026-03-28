CREATE TABLE IF NOT EXISTS kafka_topics_reference (
    topic_name VARCHAR(80) PRIMARY KEY,
    partition_key VARCHAR(80),
    producer_service VARCHAR(80),
    consumer_services TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO kafka_topics_reference (topic_name, partition_key, producer_service, consumer_services)
VALUES
('fonte-assignments', 'fonte_id', 'feed_scheduler', 'worker_pool'),
('raw-articles', 'publisher_id', 'worker_pool', 'classifier'),
('classified-articles', 'categoria', 'classifier', 'reporter_pool'),
('article-published', 'post_id', 'reporter', 'fotografo,revisor,curador,monitor'),
('pautas-especiais', 'editoria', 'pauteiro', 'reporter_pool'),
('pautas-gap', 'urgencia', 'consolidador,monitor_concorrencia', 'reporter_pool'),
('consolidacao', 'tema_id', 'monitor_concorrencia', 'consolidador'),
('homepage-updates', NULL, 'curador_homepage', 'monitor_sistema'),
('breaking-candidate', NULL, 'monitor_concorrencia', 'curador_homepage')
ON CONFLICT (topic_name) DO NOTHING;
