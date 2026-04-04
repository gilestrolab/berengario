"""
Email processing package for Berengario.

Handles IMAP inbox monitoring, email parsing, attachment extraction,
query processing with RAG, and automated email responses.

Submodules are imported directly (e.g. `from src.email.db_models import Base`)
rather than re-exported here, so that lightweight consumers (such as the
platform admin service) don't pull in heavy optional dependencies like
document-processing libraries.
"""
