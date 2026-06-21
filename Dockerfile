# Production image for Render (panel + Playwright scraper).
FROM python:3.12-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PANEL_DATA_DIR=/tmp/panel-data \
    PANEL_SCRAPE_ENABLED=0 \
    PORT=10000

WORKDIR /app

# Playwright system deps (Chromium for ATS detection / generic scrape).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .
RUN chmod +x docker-entrypoint.sh

RUN mkdir -p /tmp/panel-data

EXPOSE 10000

CMD ["./docker-entrypoint.sh"]
