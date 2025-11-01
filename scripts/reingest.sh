#!/bin/bash
# Reingest all documents from data/documents folder

echo "Stopping services to release ChromaDB lock..."
docker-compose stop raginbox-web raginbox-email

echo ""
echo "Running reingestion script..."
docker-compose run --rm raginbox-web python /app/scripts/reingest_documents.py

echo ""
echo "Restarting services..."
docker-compose up -d raginbox-web raginbox-email

echo ""
echo "✓ Reingestion complete! Services restarted."
