#!/usr/bin/env python
"""
Convenience script to run the email service daemon.

Usage:
    python run_email_service.py

Or make executable:
    chmod +x run_email_service.py
    ./run_email_service.py

Press Ctrl+C to stop the service.
"""

from src.email.email_service import main

if __name__ == "__main__":
    main()
