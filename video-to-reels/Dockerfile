FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=5015

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY redis_cache.py .
COPY redis_cache_hooks.py .
COPY templates ./templates

EXPOSE 5015

CMD ["python", "app.py"]
