FROM python:3.12-slim

WORKDIR /app

COPY requirements-base.txt /app/requirements-base.txt
RUN pip install --no-cache-dir -r /app/requirements-base.txt

COPY shared /app/shared
COPY smart_router /app/smart_router
COPY editor_chefe /app/editor_chefe

CMD ["python", "-m", "editor_chefe"]
