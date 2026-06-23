#!/usr/bin/sh
set -e
python3 -c "
from relocation_jobs.db import init_db
from relocation_jobs.catalog_db import catalog_has_data, init_catalog_schema
from relocation_jobs.core.auth import bootstrap_admin
init_db()
init_catalog_schema()
bootstrap_admin()
if catalog_has_data():
    print('catalog ready')
else:
    print('catalog ready (empty - load countries via scrape_jobs.py)')
"
exec gunicorn relocation_jobs.panel_server:app \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers 1 \
  --threads 8 \
  --timeout 600 \
  --access-logfile - \
  --error-logfile -
