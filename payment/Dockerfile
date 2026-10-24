FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=5016

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY config.py .
COPY templates ./templates
COPY static ./static

EXPOSE 5016

CMD ["gunicorn", "--bind", "0.0.0.0:5016", "--workers", "2", "--timeout", "60", "app:app"]