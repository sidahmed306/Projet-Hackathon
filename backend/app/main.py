"""Entry point of the FastAPI server.

Start it from backend/ with: uvicorn app.main:app --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import count_products, init_db
from app.errors import register_error_handlers
from app.products import router as products_router
from app.seed import seed_products


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts (before "yield") and once when it stops."""
    init_db()
    # Load the demo catalog only the first time (empty table).
    if count_products() == 0:
        seed_products()
    yield


app = FastAPI(title="AI Payment Agent API", lifespan=lifespan)

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


# Product catalog endpoints (app/products.py).
app.include_router(products_router)
