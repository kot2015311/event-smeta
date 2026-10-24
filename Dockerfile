# Один образ для сайта и бота: в docker-compose.yml они запускаются разными командами
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Сначала зависимости: этот слой пересобирается, только когда меняется requirements.txt
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Работаем не от root; база лежит в /app/instance (это том в docker-compose)
RUN useradd --create-home --uid 1000 app && mkdir -p /app/instance && chown app:app /app/instance
USER app

ENV DATABASE_PATH=/app/instance/smeta.db
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

# Один процесс с потоками: ограничитель частоты заявок хранится в памяти процесса
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--access-logfile", "-", "wsgi:app"]
