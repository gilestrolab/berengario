#!/bin/bash
# Reingest all documents from data/documents folder

echo "Stopping services to release ChromaDB lock..."
docker-compose stop berengario-app berengario-email

echo ""
echo "Running reingestion script..."
docker-compose run --rm berengario-app python /app/scripts/reingest_documents.py

echo ""
echo "Restarting services..."
docker-compose up -d berengario-app berengario-email

echo ""
echo "✓ Reingestion complete! Services restarted."
