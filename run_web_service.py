#!/usr/bin/env python
"""
Entry point for RAGInbox web service.

Starts the FastAPI web interface for RAG query testing.

Usage:
    python run_web_service.py

Or make executable:
    chmod +x run_web_service.py
    ./run_web_service.py
"""

import logging
import sys

import uvicorn

from src.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.log_file, encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


def main():
    """
    Start the web service using Uvicorn.
    """
    logger.info("=" * 60)
    logger.info(f"Starting {settings.instance_name} Web Service")
    logger.info("=" * 60)
    logger.info(f"Instance: {settings.instance_name}")
    logger.info(f"Organization: {settings.organization}")
    logger.info(f"Host: {settings.api_host}")
    logger.info(f"Port: {settings.api_port}")
    logger.info(f"Reload: {settings.api_reload}")
    logger.info("=" * 60)

    # Start Uvicorn server
    uvicorn.run(
        "src.api.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
