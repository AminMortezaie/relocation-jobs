#!/usr/bin/sh
set -e
python3 -c "
from relocation_jobs.db import init_db
from relocation_jobs.catalog_db import catalog_has_data, migrate_from_json_files, export_all_archives
init_db()
if catalog_has_data():
    n = export_all_archives()
    print(f'catalog ready ({n} archive JSON file(s) refreshed)' if n else 'catalog ready')
else:
    n = migrate_from_json_files()
    print(f'migrated {n} companies from JSON into catalog' if n else 'catalog ready (empty)')
"
exec gunicorn relocation_jobs.panel_server:app \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers 1 \
  --threads 8 \
  --timeout 600 \
  --access-logfile - \
  --error-logfile -
