#!/usr/bin/env bash
# Publish catalogs/challenge to one Hugging Face bucket, under challenge/:
#   https://huggingface.co/buckets/tiagolubiana/RO-BioSTAC_demo/resolve/challenge/ro-crate-metadata.json
# One bucket, so the crates' relative references resolve as they are. A separate bucket from the STAC
# deployment (ome2024-challenge-STAC*), which main still serves. Run from the repository root after the build (10, 14, 15, 19, 16).
set -euo pipefail

BUCKET=tiagolubiana/RO-BioSTAC_demo

hf buckets create "$BUCKET" --exist-ok
# --delete: the build clears resource folders, so the bucket should lose stale files too
hf buckets sync catalogs/challenge "hf://buckets/$BUCKET/challenge" --delete
echo "https://huggingface.co/buckets/$BUCKET/resolve/challenge/ro-crate-metadata.json"
