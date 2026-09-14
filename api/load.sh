#!/usr/bin/env bash
# Load catalogs/extended/ into the pgstac database from api/docker-compose.yml.
set -euo pipefail
cd "$(dirname "$0")/.."
export PGHOST=localhost PGPORT=5439 PGUSER=username PGPASSWORD=password PGDATABASE=postgis
PY=.venv/bin/python
tmp=$(mktemp -d)
$PY -c "import json,glob,sys; [print(json.dumps(json.load(open(p)))) for p in sorted(glob.glob(sys.argv[1]))]" 'catalogs/extended/*/collection.json' > "$tmp/collections.ndjson"
$PY -c "import json,glob,sys; [print(json.dumps(json.load(open(p)))) for p in sorted(glob.glob(sys.argv[1]))]" 'catalogs/extended/*/*/*.json' > "$tmp/items.ndjson"
.venv/bin/pypgstac load collections "$tmp/collections.ndjson" --method upsert
.venv/bin/pypgstac load items "$tmp/items.ndjson" --method upsert
.venv/bin/pypgstac load_queryables api/queryables.json
echo "Loaded $(wc -l < "$tmp/collections.ndjson") collections, $(wc -l < "$tmp/items.ndjson") items"
