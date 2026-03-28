FROM python:3.12-slim

WORKDIR /app
COPY requirements-base.txt /app/requirements-base.txt
RUN apt-get update && apt-get install -y --no-install-recommends gcc libxml2-dev libxslt-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /app/requirements-base.txt

COPY shared /app/shared
COPY smart_router /app/smart_router
COPY reporter /app/reporter

CMD ["python", "-m", "reporter"]
