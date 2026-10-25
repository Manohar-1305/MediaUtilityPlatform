FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY redis_cache.py .
COPY redis_cache_hooks.py .
COPY static/ ./static/
COPY templates/ ./templates/

EXPOSE 5012

CMD ["python", "app.py"]
