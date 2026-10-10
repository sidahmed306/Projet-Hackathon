"""Error handling: every error response follows the contract in docs/api.md.

    {"error": {"code": "SOME_CODE", "message": "Human readable explanation"}}
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Raise this in an endpoint to return a contract error.

    Example: raise ApiError("PRODUCT_NOT_FOUND", "Product does not exist", 404)
    """

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_response(code: str, message: str, status_code: int) -> JSONResponse:
    """Build a JSON response with the contract error shape."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.status_code)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Build a short message like "body.product_id: Field required".
    # We only use the field location and the message, never the input values.
    parts = []
    for err in exc.errors():
        location = ".".join(str(item) for item in err.get("loc", []))
        parts.append(f"{location}: {err.get('msg', 'invalid value')}")
    message = "; ".join(parts) or "Invalid request"
    return error_response("VALIDATION_ERROR", message, 400)


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Unknown route -> 404 NOT_FOUND.
    if exc.status_code == 404:
        return error_response("NOT_FOUND", "This route does not exist", 404)
    # Other HTTP errors (for example 405 Method Not Allowed).
    return error_response("HTTP_ERROR", str(exc.detail), exc.status_code)


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log only the error type on the server (no stack trace, no values that could hold secrets).
    logger.error("Unexpected error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    # The client gets a generic message only.
    return error_response("INTERNAL_ERROR", "An unexpected error occurred", 500)


def register_error_handlers(app: FastAPI) -> None:
    """Attach all the handlers above to the FastAPI app."""
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
