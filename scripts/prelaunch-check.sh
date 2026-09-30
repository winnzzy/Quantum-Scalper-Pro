#!/bin/bash
set -euo pipefail

docker compose config --quiet
docker compose exec -T backend python scripts/prelaunch_check.py
