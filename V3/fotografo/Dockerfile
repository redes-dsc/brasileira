FROM python:3.12-slim

WORKDIR /app
COPY requirements-base.txt /app/requirements-base.txt
RUN pip install --no-cache-dir -r /app/requirements-base.txt

COPY shared /app/shared
COPY smart_router /app/smart_router
COPY fotografo /app/fotografo

CMD ["python", "-m", "fotografo"]
