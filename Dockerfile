FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run.py ./
COPY src ./src
COPY static ./static
COPY templates ./templates
COPY portfolio.example.csv ./portfolio.example.csv

CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 4 --timeout 120 run:app
