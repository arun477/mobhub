#!/bin/bash

echo "Building and starting AgentHub..."

if [ "$1" = "--reset" ]; then
    echo "Resetting all data..."
    docker compose down -v
else
    docker compose down
fi

docker compose up --build -d
echo ""
docker compose ps
echo ""
echo "Frontend: http://localhost:3737"
echo "API:      http://localhost:8787"
echo "Neo4j:    http://localhost:7475"
