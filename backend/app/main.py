"""Entry point of the FastAPI server.

Start it from backend/ with: uvicorn app.main:app --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.errors import register_error_handlers

app = FastAPI(title="AI Payment Agent API")

# Every error follows the contract shape {"error": {"code", "message"}}.
register_error_handlers(app)

# CORS: only the frontend (FRONTEND_ORIGIN) may call this API from a browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict:
    """Check that the server is running."""
    return {"status": "ok"}
