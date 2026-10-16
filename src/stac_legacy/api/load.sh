#!/usr/bin/env bash
# Load a catalog into the pgstac database from api/docker-compose.yml.
# Usage: api/load.sh [catalog dir]   (default: catalogs/extended)
set -euo pipefail
cd "$(dirname "$0")/.."
CATALOG="${1:-catalogs/extended}"
export PGHOST=localhost PGPORT=5439 PGUSER=username PGPASSWORD=password PGDATABASE=postgis
PY=.venv/bin/python
tmp=$(mktemp -d)
$PY -c "import json,glob,sys; [print(json.dumps(json.load(open(p)))) for p in sorted(glob.glob(sys.argv[1], recursive=True))]" "$CATALOG/**/collection.json" > "$tmp/collections.ndjson"
$PY -c "import json,glob,sys; [print(json.dumps(json.load(open(p)))) for p in sorted(glob.glob(sys.argv[1], recursive=True)) if json.load(open(p)).get('type') == 'Feature']" "$CATALOG/**/*.json" > "$tmp/items.ndjson"
.venv/bin/pypgstac load collections "$tmp/collections.ndjson" --method upsert
.venv/bin/pypgstac load items "$tmp/items.ndjson" --method upsert
.venv/bin/pypgstac load_queryables api/queryables.json
echo "Loaded $(wc -l < "$tmp/collections.ndjson") collections, $(wc -l < "$tmp/items.ndjson") items from $CATALOG"
