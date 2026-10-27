FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 5019

CMD ["gunicorn", "--bind", "0.0.0.0:5019", "--workers", "2", "--timeout", "300", "app:app"]
