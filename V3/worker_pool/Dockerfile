FROM python:3.12-slim

WORKDIR /app
COPY requirements-base.txt /app/requirements-base.txt
RUN pip install --no-cache-dir -r /app/requirements-base.txt
RUN python -m playwright install chromium

COPY shared /app/shared
COPY worker_pool /app/worker_pool

CMD ["python", "-m", "worker_pool"]
