#!/usr/bin/sh
set -e
python3 -c "
from relocation_jobs.db import init_db
init_db()
print('mcp db ready')
"
exec python3 scripts/mcp_http_server.py
