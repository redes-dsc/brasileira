FROM python:3.12-slim

WORKDIR /app
COPY requirements-base.txt /app/requirements-base.txt
RUN pip install --no-cache-dir -r /app/requirements-base.txt
RUN python -m spacy download pt_core_news_sm

COPY shared /app/shared
COPY classificador /app/classificador

CMD ["python", "-m", "classificador"]
