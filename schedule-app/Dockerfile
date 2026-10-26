FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

# curl — для HEALTHCHECK; fonts-dejavu-core — кириллица в PDF (reportlab)
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/backups /app/run \
 && chmod +x /app/docker/entrypoint.sh \
 && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:5000/api/health || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["waitress-serve", "--listen=0.0.0.0:5000", "--threads=8", "app:app"]
