"""
Entry point for the Platform Admin application.

Runs the platform admin FastAPI app on port 8000 (mapped to 8091 in Docker).
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.platform_admin.app:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
