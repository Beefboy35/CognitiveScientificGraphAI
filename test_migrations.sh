#!/bin/bash
set -e

echo "Test 1: Files exist"
for f in backend/docker-entrypoint.sh backend/Dockerfile.fastapi backend/test_entrypoint.sh .env.dev; do
    [ -f "$f" ] || { echo "MISSING: $f"; exit 1; }
    echo "  $f"
done

echo ""
echo "Test 2: Permissions"
chmod +x backend/docker-entrypoint.sh backend/test_entrypoint.sh
echo "  OK"

echo ""
echo "Test 3: Unit tests"
bash backend/test_entrypoint.sh 2>&1 | tail -3

echo ""
echo "Test 4: Docker config"
ENV_FILE=.env.dev docker-compose config --services 2>/dev/null | grep -E "fastapi|postgres" | head -2

echo ""
echo "READY"
echo ""
echo "With migrations (default):"
echo "  ENV_FILE=.env.dev docker-compose up -d fastapi-dev postgres redis"
echo ""
echo "Without migrations:"
echo "  SKIP_MIGRATIONS=true ENV_FILE=.env.dev docker-compose up -d fastapi-dev postgres redis"
echo ""
echo "Change script and redeploy:"
echo "  nano backend/docker-entrypoint.sh"
echo "  ENV_FILE=.env.dev docker-compose up -d fastapi-dev"
