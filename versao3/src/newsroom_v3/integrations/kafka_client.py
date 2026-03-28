from dataclasses import dataclass


@dataclass(frozen=True)
class KafkaTopic:
    name: str
    partition_key: str | None = None


TOPICS = [
    KafkaTopic('fonte-assignments', 'fonte_id'),
    KafkaTopic('raw-articles', 'publisher_id'),
    KafkaTopic('classified-articles', 'categoria'),
    KafkaTopic('article-published', 'post_id'),
    KafkaTopic('pautas-especiais', 'editoria'),
    KafkaTopic('pautas-gap', 'urgencia'),
    KafkaTopic('consolidacao', 'tema_id'),
    KafkaTopic('homepage-updates', None),
    KafkaTopic('breaking-candidate', None),
]
