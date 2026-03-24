#!/bin/bash

export APP_ENV=production
export DB_PASSWORD=supersecret123
export API_KEY=hardcoded-key-abc

DB_HOST=localhost
DB_PORT=5432

function setup_database() {
    echo "Setting up database at $DB_HOST:$DB_PORT"
    psql -h "$DB_HOST" -U admin -d myapp -c "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY);"
}

setup_database
