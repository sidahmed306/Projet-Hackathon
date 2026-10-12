"""Tests for the PayPal Sandbox client. They NEVER call the real PayPal:
every HTTP request goes to a fake PayPal (httpx.MockTransport) defined here.
"""

import base64
import dataclasses
import json
import logging
from urllib.parse import parse_qs

import httpx
import pytest

from app import config, paypal_client
from app.errors import ApiError

CLIENT_ID = "test-client-id"
SECRET = "super-secret-value-123"
TOKEN = "fake-access-token-456"


@pytest.fixture
def paypal_settings(monkeypatch):
    """Fake Sandbox credentials for these tests."""
    settings = dataclasses.replace(
        config.settings,
        PAYPAL_CLIENT_ID=CLIENT_ID,
        PAYPAL_CLIENT_SECRET=SECRET,
        PAYPAL_API_BASE="https://api-m.sandbox.paypal.com",
    )
    monkeypatch.setattr(config, "settings", settings)
    return settings


class FakePayPal:
    """A fake PayPal server. It records every request it receives.

    routes: {("POST", "/v2/checkout/orders"): handler} where handler(request) -> httpx.Response
    The token route is always answered unless replaced.
    """

    def __init__(self, routes=None, expires_in=32400):
        self.requests = []
        self.routes = {
            ("POST", "/v1/oauth2/token"): lambda request: httpx.Response(
                200, json={"access_token": TOKEN, "token_type": "Bearer", "expires_in": expires_in}
            ),
        }
        self.routes.update(routes or {})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.routes[(request.method, request.url.path)](request)

    def count(self, method, path):
        return sum(1 for r in self.requests if r.method == method and r.url.path == path)


def install(monkeypatch, fake: FakePayPal):
    monkeypatch.setattr(paypal_client, "_transport", httpx.MockTransport(fake.handler))


CREATED_ORDER = {
    "id": "5O190127TN364715T",
    "status": "CREATED",
    "links": [
        {"href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T", "rel": "self", "method": "GET"},
        {"href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T", "rel": "approve", "method": "GET"},
    ],
}

CAPTURED_ORDER = {
    "id": "5O190127TN364715T",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "reference_id": "ord_0001",
            "payments": {
                "captures": [
                    {
                        "id": "3C679366HH908993F",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "764.00"},
                    }
                ]
            },
        }
    ],
}


def create_route(request):
    return httpx.Response(201, json=CREATED_ORDER)


# --- Token -------------------------------------------------------------------


def test_token_request_uses_client_credentials(monkeypatch, paypal_settings):
    fake = FakePayPal()
    install(monkeypatch, fake)

    assert paypal_client.get_access_token() == TOKEN

    request = fake.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/oauth2/token"
    expected = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
    assert request.headers["Authorization"] == f"Basic {expected}"
    assert parse_qs(request.content.decode()) == {"grant_type": ["client_credentials"]}


def test_token_is_cached(monkeypatch, paypal_settings):
    fake = FakePayPal({("POST", "/v2/checkout/orders"): create_route})
    install(monkeypatch, fake)

    paypal_client.create_order(100, "USD", "ord_1", "req-1")
    paypal_client.create_order(100, "USD", "ord_2", "req-2")

    assert fake.count("POST", "/v1/oauth2/token") == 1
    assert fake.count("POST", "/v2/checkout/orders") == 2


def test_token_is_renewed_60_seconds_before_expiry(monkeypatch, paypal_settings):
    fake = FakePayPal(expires_in=3600)
    install(monkeypatch, fake)
    clock = {"now": 1000.0}
    monkeypatch.setattr(paypal_client, "_now", lambda: clock["now"])

    paypal_client.get_access_token()
    clock["now"] += 3600 - 61  # still valid (61 s left)
    paypal_client.get_access_token()
    assert fake.count("POST", "/v1/oauth2/token") == 1

    clock["now"] += 2  # only 59 s left: get a new token
    paypal_client.get_access_token()
    assert fake.count("POST", "/v1/oauth2/token") == 2


# --- Create order ------------------------------------------------------------


def test_create_order_sends_amount_and_request_id(monkeypatch, paypal_settings):
    fake = FakePayPal({("POST", "/v2/checkout/orders"): create_route})
    install(monkeypatch, fake)

    result = paypal_client.create_order(76400, "USD", "ord_0001", "req-abc-123")

    request = [r for r in fake.requests if r.url.path == "/v2/checkout/orders"][0]
    assert request.headers["PayPal-Request-Id"] == "req-abc-123"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {
        "intent": "CAPTURE",
        "purchase_units": [
            {"reference_id": "ord_0001", "amount": {"currency_code": "USD", "value": "764.00"}}
        ],
    }
    assert result == {
        "paypal_order_id": "5O190127TN364715T",
        "status": "CREATED",
        "approve_url": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
    }


# --- Capture and get ---------------------------------------------------------


def test_capture_order_parses_capture(monkeypatch, paypal_settings):
    fake = FakePayPal(
        {("POST", "/v2/checkout/orders/5O190127TN364715T/capture"): lambda r: httpx.Response(201, json=CAPTURED_ORDER)}
    )
    install(monkeypatch, fake)

    result = paypal_client.capture_order("5O190127TN364715T", "cap-req-1")

    capture_request = fake.requests[-1]
    assert capture_request.headers["PayPal-Request-Id"] == "cap-req-1"
    assert result == {
        "status": "COMPLETED",
        "capture_id": "3C679366HH908993F",
        "capture_status": "COMPLETED",
        "captured_value": "764.00",
        "captured_currency": "USD",
    }


def test_capture_without_captures_returns_none_values(monkeypatch, paypal_settings):
    fake = FakePayPal(
        {("POST", "/v2/checkout/orders/ABC123/capture"): lambda r: httpx.Response(201, json={"id": "ABC123", "status": "PENDING"})}
    )
    install(monkeypatch, fake)

    result = paypal_client.capture_order("ABC123", "cap-req-2")
    assert result["status"] == "PENDING"
    assert result["capture_id"] is None
    assert result["captured_value"] is None


def test_get_order(monkeypatch, paypal_settings):
    fake = FakePayPal(
        {("GET", "/v2/checkout/orders/5O190127TN364715T"): lambda r: httpx.Response(200, json=CREATED_ORDER)}
    )
    install(monkeypatch, fake)

    assert paypal_client.get_order("5O190127TN364715T") == {"id": "5O190127TN364715T", "status": "CREATED"}


def test_invalid_order_id_is_refused(monkeypatch, paypal_settings):
    fake = FakePayPal()
    install(monkeypatch, fake)
    with pytest.raises(ApiError) as error:
        paypal_client.get_order("../../v1/oauth2/token")
    assert error.value.code == "VALIDATION_ERROR"


# --- Errors ------------------------------------------------------------------


@pytest.mark.parametrize("status", [400, 422, 500, 503])
def test_paypal_error_status_becomes_paypal_error(monkeypatch, paypal_settings, status):
    body = {"name": "UNPROCESSABLE_ENTITY", "message": "x", "debug_id": "dbg123"}
    fake = FakePayPal({("POST", "/v2/checkout/orders"): lambda r: httpx.Response(status, json=body)})
    install(monkeypatch, fake)

    with pytest.raises(ApiError) as error:
        paypal_client.create_order(100, "USD", "ord_1", "req-1")
    assert (error.value.code, error.value.status_code) == ("PAYPAL_ERROR", 502)


def test_error_log_has_status_name_and_debug_id(monkeypatch, paypal_settings, caplog):
    body = {"name": "UNPROCESSABLE_ENTITY", "message": "details", "debug_id": "dbg123"}
    fake = FakePayPal({("POST", "/v2/checkout/orders"): lambda r: httpx.Response(422, json=body)})
    install(monkeypatch, fake)

    with caplog.at_level(logging.WARNING, logger="app.paypal_client"):
        with pytest.raises(ApiError):
            paypal_client.create_order(100, "USD", "ord_1", "req-1")
    assert "status=422" in caplog.text
    assert "UNPROCESSABLE_ENTITY" in caplog.text
    assert "dbg123" in caplog.text


@pytest.mark.parametrize("network_error", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError])
def test_timeout_and_network_errors_become_paypal_error(monkeypatch, paypal_settings, network_error):
    def fail(request):
        raise network_error("simulated", request=request)

    fake = FakePayPal({("POST", "/v2/checkout/orders"): fail})
    install(monkeypatch, fake)

    with pytest.raises(ApiError) as error:
        paypal_client.create_order(100, "USD", "ord_1", "req-1")
    assert (error.value.code, error.value.status_code) == ("PAYPAL_ERROR", 502)


def test_invalid_json_becomes_paypal_error(monkeypatch, paypal_settings):
    fake = FakePayPal({("POST", "/v2/checkout/orders"): lambda r: httpx.Response(201, text="<html>oops</html>")})
    install(monkeypatch, fake)
    with pytest.raises(ApiError) as error:
        paypal_client.create_order(100, "USD", "ord_1", "req-1")
    assert error.value.code == "PAYPAL_ERROR"


def test_token_error_becomes_paypal_error(monkeypatch, paypal_settings):
    body = {"error": "invalid_client", "error_description": "Client Authentication failed"}
    fake = FakePayPal({("POST", "/v1/oauth2/token"): lambda r: httpx.Response(401, json=body)})
    install(monkeypatch, fake)
    with pytest.raises(ApiError) as error:
        paypal_client.get_access_token()
    assert error.value.code == "PAYPAL_ERROR"


@pytest.mark.parametrize("field", ["PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"])
def test_missing_credentials(monkeypatch, paypal_settings, field):
    monkeypatch.setattr(config, "settings", dataclasses.replace(paypal_settings, **{field: ""}))
    fake = FakePayPal()
    install(monkeypatch, fake)

    with pytest.raises(ApiError) as error:
        paypal_client.create_order(100, "USD", "ord_1", "req-1")
    assert error.value.code == "PAYPAL_ERROR"
    assert error.value.message == "PayPal is not configured"
    assert error.value.status_code == 502
    assert fake.requests == []  # nothing was sent


@pytest.mark.parametrize(
    "base",
    ["https://api-m.paypal.com", "http://api-m.sandbox.paypal.com", "https://evil.example", ""],
)
def test_non_sandbox_base_url_is_refused(monkeypatch, paypal_settings, base):
    monkeypatch.setattr(config, "settings", dataclasses.replace(paypal_settings, PAYPAL_API_BASE=base))
    fake = FakePayPal()
    install(monkeypatch, fake)

    with pytest.raises(paypal_client.PayPalConfigError, match="Sandbox only"):
        paypal_client.get_access_token()
    assert fake.requests == []


# --- Secrets never leak ------------------------------------------------------


def test_secret_and_token_never_in_logs_or_errors(monkeypatch, paypal_settings, caplog):
    # PayPal echoes the secret and the token in its error body (worst case).
    leaky_body = {"name": "INTERNAL_SERVER_ERROR", "message": f"{SECRET} {TOKEN}", "debug_id": "dbg9"}
    fake = FakePayPal({("POST", "/v2/checkout/orders"): lambda r: httpx.Response(500, json=leaky_body)})
    install(monkeypatch, fake)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ApiError) as error:
            paypal_client.create_order(100, "USD", "ord_1", "req-1")
        # And a network error after a token was obtained.
        fake.routes[("POST", "/v2/checkout/orders")] = lambda r: (_ for _ in ()).throw(
            httpx.ConnectError("boom", request=r)
        )
        with pytest.raises(ApiError) as error2:
            paypal_client.create_order(100, "USD", "ord_1", "req-1")

    for text in (caplog.text, error.value.message, str(error.value), error2.value.message, repr(config.settings)):
        assert SECRET not in text
        assert TOKEN not in text
