from dataclasses import dataclass


CATEGORIES = [
    'politica', 'economia', 'esportes', 'tecnologia', 'saude', 'educacao',
    'ciencia', 'cultura', 'mundo', 'meio_ambiente', 'seguranca_justica',
    'sociedade', 'brasil', 'regional', 'opiniao_analise', 'ultimas_noticias',
]


@dataclass(frozen=True)
class ClassificationResult:
    categoria: str
    urgencia: str
    tipo: str


class LightweightClassifier:
    def classify(self, title: str, body: str) -> ClassificationResult:
        text = f"{title} {body}".lower()
        if any(k in text for k in ['senado', 'camara', 'presidente', 'governo']):
            return ClassificationResult('politica', 'normal', 'noticia_simples')
        if any(k in text for k in ['dolar', 'bovespa', 'selic', 'mercado']):
            return ClassificationResult('economia', 'normal', 'noticia_simples')
        return ClassificationResult('ultimas_noticias', 'normal', 'noticia_simples')
