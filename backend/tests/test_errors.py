"""Tests for the error format (docs/api.md) and CORS.

Test-only routes live on a separate FastAPI app built here, which uses the
same error handlers as the real app. The real app never gets test routes.
"""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import ApiError, register_error_handlers
from app.main import app as real_app

# --- Test-only app -----------------------------------------------------------

router = APIRouter()


class QuoteRequest(BaseModel):
    product_id: str


@router.post("/test/needs-body")
def needs_body(request: QuoteRequest) -> dict:
    return {"product_id": request.product_id}


@router.get("/test/api-error")
def raises_api_error() -> dict:
    raise ApiError("PRODUCT_NOT_FOUND", "Product does not exist", 404)


@router.get("/test/crash")
def crashes() -> dict:
    raise RuntimeError("database failed, secret=abc123")


test_app = FastAPI()
register_error_handlers(test_app)
test_app.include_router(router)

# raise_server_exceptions=False: return the 500 response instead of re-raising in the test.
test_client = TestClient(test_app, raise_server_exceptions=False)
real_client = TestClient(real_app)


def assert_contract_error(response, status_code: int, code: str) -> None:
    """Check the status and the {"error": {"code", "message"}} shape."""
    assert response.status_code == status_code
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)


# --- Error format ------------------------------------------------------------


def test_missing_required_field_returns_validation_error():
    response = test_client.post("/test/needs-body", json={})
    assert_contract_error(response, 400, "VALIDATION_ERROR")


def test_api_error_returns_its_own_code_and_status():
    response = test_client.get("/test/api-error")
    assert_contract_error(response, 404, "PRODUCT_NOT_FOUND")
    assert response.json()["error"]["message"] == "Product does not exist"


def test_unexpected_exception_hides_details():
    response = test_client.get("/test/crash")
    assert_contract_error(response, 500, "INTERNAL_ERROR")
    assert "abc123" not in response.text


def test_wrong_method_on_health_returns_405():
    response = real_client.post("/api/health")
    assert_contract_error(response, 405, "HTTP_ERROR")


# --- CORS --------------------------------------------------------------------


def test_cors_allows_frontend_origin():
    response = real_client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_blocks_other_origin():
    response = real_client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers
