#!/bin/bash
# Fix database password mismatch issue

echo "=== RAG System Database Password Fix ==="
echo ""

# Stop all containers
echo "1. Stopping all containers..."
docker-compose down

# Remove Postgres volume (this deletes all DB data)
echo "2. Removing Postgres data volume..."
docker volume rm rag-v21_postgres_data 2>/dev/null || docker volume rm rag-v2.1_postgres_data 2>/dev/null || echo "Volume already removed or different name"

# Also try with project name
docker volume ls | grep postgres | awk '{print $2}' | xargs -r docker volume rm 2>/dev/null || true

echo ""
echo "3. Current .env file DB_PASSWORD:"
grep "^DB_PASSWORD=" .env

echo ""
echo "=== IMPORTANT ==="
echo "Your .env file has: DB_PASSWORD=$(grep '^DB_PASSWORD=' .env | cut -d= -f2)"
echo ""
echo "To restart the system with fresh database:"
echo "  docker-compose up -d"
echo ""
echo "The database will be recreated with the password from your .env file."
echo "All existing data will be lost."
