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


# With payment_source, PayPal answers PAYER_ACTION_REQUIRED and a "payer-action" link.
CREATED_ORDER = {
    "id": "5O190127TN364715T",
    "status": "PAYER_ACTION_REQUIRED",
    "links": [
        {"href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T", "rel": "self", "method": "GET"},
        {"href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T", "rel": "payer-action", "method": "GET"},
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
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "return_url": "http://localhost:5173/checkout/return",
                    "cancel_url": "http://localhost:5173/checkout/cancel",
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                    "landing_page": "LOGIN",
                    "brand_name": "AI Payment Agent",
                }
            }
        },
    }
    assert result == {
        "paypal_order_id": "5O190127TN364715T",
        "status": "PAYER_ACTION_REQUIRED",
        "approve_url": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
    }


def test_return_and_cancel_urls_use_frontend_origin(monkeypatch, paypal_settings):
    monkeypatch.setattr(
        config, "settings", dataclasses.replace(paypal_settings, FRONTEND_ORIGIN="https://shop.example/")
    )
    fake = FakePayPal({("POST", "/v2/checkout/orders"): create_route})
    install(monkeypatch, fake)

    paypal_client.create_order(100, "USD", "ord_1", "req-1")

    request = [r for r in fake.requests if r.url.path == "/v2/checkout/orders"][0]
    context = json.loads(request.content)["payment_source"]["paypal"]["experience_context"]
    assert context["return_url"] == "https://shop.example/checkout/return"
    assert context["cancel_url"] == "https://shop.example/checkout/cancel"


@pytest.mark.parametrize(
    "links, expected",
    [
        # Both present: "payer-action" wins, whatever the order.
        ([{"rel": "approve", "href": "A"}, {"rel": "payer-action", "href": "P"}], "P"),
        # Only "approve": used as fallback.
        ([{"rel": "self", "href": "S"}, {"rel": "approve", "href": "A"}], "A"),
        # Neither: None.
        ([{"rel": "self", "href": "S"}], None),
    ],
)
def test_approve_url_prefers_payer_action(monkeypatch, paypal_settings, links, expected):
    order = {"id": "X1", "status": "PAYER_ACTION_REQUIRED", "links": links}
    fake = FakePayPal({("POST", "/v2/checkout/orders"): lambda r: httpx.Response(200, json=order)})
    install(monkeypatch, fake)

    assert paypal_client.create_order(100, "USD", "ord_1", "req-1")["approve_url"] == expected


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

    assert paypal_client.get_order("5O190127TN364715T") == {
        "id": "5O190127TN364715T",
        "status": "PAYER_ACTION_REQUIRED",
    }


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


def test_error_log_has_issue_and_description(monkeypatch, paypal_settings, caplog):
    body = {
        "name": "UNPROCESSABLE_ENTITY",
        "message": "The requested action could not be performed.",
        "debug_id": "dbg456",
        "details": [
            {
                "issue": "ORDER_NOT_APPROVED",
                "description": "Payer has not yet approved the Order for payment.",
                "field": "some-field-value-that-must-not-be-logged",
            }
        ],
        "links": [{"href": "https://example.invalid/should-not-be-logged", "rel": "information_link"}],
    }
    fake = FakePayPal({("POST", "/v2/checkout/orders/ABC123/capture"): lambda r: httpx.Response(422, json=body)})
    install(monkeypatch, fake)

    with caplog.at_level(logging.WARNING, logger="app.paypal_client"):
        with pytest.raises(ApiError):
            paypal_client.capture_order("ABC123", "cap-req-1")
    assert "issue=ORDER_NOT_APPROVED" in caplog.text
    assert "Payer has not yet approved the Order for payment." in caplog.text
    assert "dbg456" in caplog.text
    # Only the chosen fields are logged, never the full body.
    assert "some-field-value-that-must-not-be-logged" not in caplog.text
    assert "should-not-be-logged" not in caplog.text


def test_error_log_without_details(monkeypatch, paypal_settings, caplog):
    fake = FakePayPal({("POST", "/v2/checkout/orders"): lambda r: httpx.Response(500, json={"details": "weird"})})
    install(monkeypatch, fake)
    with caplog.at_level(logging.WARNING, logger="app.paypal_client"):
        with pytest.raises(ApiError):
            paypal_client.create_order(100, "USD", "ord_1", "req-1")
    assert "issue=None" in caplog.text


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
