#!/bin/bash
set -e

DB_WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-60}"
DB_WAIT_INTERVAL="${DB_WAIT_INTERVAL:-2}"

parse_pg_dsn() {
    local dsn="$1"
    echo "$dsn" | sed -n 's|.*@\([^:/]*\):\([0-9]*\).*|\1 \2|p'
}

wait_for_postgres() {
    local dsn="$PG_DSN"
    
    if [ -z "$dsn" ]; then
        return 0
    fi
    
    local parsed=$(parse_pg_dsn "$dsn")
    local db_host=$(echo "$parsed" | awk '{print $1}')
    local db_port=$(echo "$parsed" | awk '{print $2}')
    
    db_port="${db_port:-5432}"
    
    if [ -z "$db_host" ]; then
        echo "INFO: Could not parse PostgreSQL host from PG_DSN"
        return 0
    fi
    
    echo "Waiting for PostgreSQL at $db_host:$db_port (${DB_WAIT_TIMEOUT}s timeout)"
    
    local elapsed=0
    while [ $elapsed -lt "$DB_WAIT_TIMEOUT" ]; do
        if timeout 5 bash -c "echo > /dev/tcp/$db_host/$db_port" 2>/dev/null; then
            echo "PostgreSQL ready"
            return 0
        fi
        sleep "$DB_WAIT_INTERVAL"
        elapsed=$((elapsed + DB_WAIT_INTERVAL))
    done
    
    echo "ERROR: PostgreSQL not available after ${DB_WAIT_TIMEOUT}s"
    return 1
}

run_migrations() {
    if [ "${SKIP_MIGRATIONS:-false}" = "true" ]; then
        echo "Skipping migrations"
        return 0
    fi
    
    echo "Running migrations"
    cd /app
    
    if alembic upgrade head; then
        echo "Migrations done"
        return 0
    else
        echo "ERROR: Migration failed"
        return 1
    fi
}

if ! wait_for_postgres; then
    exit 1
fi

if ! run_migrations; then
    exit 1
fi

exec "$@"
