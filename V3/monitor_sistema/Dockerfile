FROM python:3.12-slim

WORKDIR /app

COPY requirements-base.txt /app/requirements-base.txt
RUN pip install --no-cache-dir -r /app/requirements-base.txt

COPY shared /app/shared
COPY editor_chefe /app/editor_chefe
COPY monitor_sistema /app/monitor_sistema

CMD ["python", "-m", "monitor_sistema"]
