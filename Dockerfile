# Production image for Render (panel + Playwright scraper).
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PANEL_DATA_DIR=/tmp/panel-data \
    PANEL_SCRAPE_ENABLED=0 \
    PORT=10000 \
    PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-playwright.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-playwright.txt \
    && playwright install --with-deps --only-shell chromium

COPY . .
RUN chmod +x docker-entrypoint.sh start.sh

RUN mkdir -p /tmp/panel-data

EXPOSE 10000

CMD ["./docker-entrypoint.sh"]
