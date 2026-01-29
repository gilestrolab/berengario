#!/bin/bash
# Helper script to start docker-compose with git version info

# Export git information as environment variables
export GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
export GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo "Starting RAGInbox with version info:"
echo "  Branch: $GIT_BRANCH"
echo "  Commit: $GIT_COMMIT"
echo ""

# Start docker-compose with the environment variables
docker-compose "$@"
