"""Small PayPal Sandbox client (OAuth 2.0 + Orders API v2).

Official docs:
- OAuth 2.0:      https://developer.paypal.com/api/rest/authentication/
- Orders API v2:  https://developer.paypal.com/docs/api/orders/v2/
- Idempotency:    https://developer.paypal.com/api/rest/reference/idempotency/

Safety rules in this file:
- The client secret and the access token are NEVER printed, logged or returned.
- On a PayPal error we log only the HTTP status, the error name and PayPal's debug_id.
- Only the Sandbox is allowed for now (no real money).
"""

import logging
import time
from typing import Optional

import httpx

from app import config
from app.errors import ApiError
from app.money import from_cents

logger = logging.getLogger(__name__)

SANDBOX_API_BASE = "https://api-m.sandbox.paypal.com"
TIMEOUT_SECONDS = 15.0
# Get a new token 60 seconds before the old one expires.
TOKEN_SAFETY_MARGIN_SECONDS = 60

# Tests replace this with an httpx.MockTransport so they never call the real PayPal.
_transport: Optional[httpx.BaseTransport] = None

# In-memory token cache: {"token": str, "expires_at": float, "client_id": str}
_token_cache: dict = {}


def _now() -> float:
    """Current time in seconds (a separate function so tests can fake the clock)."""
    return time.monotonic()


class PayPalConfigError(RuntimeError):
    """Raised when the PayPal configuration is unsafe (for example a non-Sandbox URL)."""


def _check_config() -> None:
    """Refuse to run if not in Sandbox, or if the credentials are missing."""
    base = config.settings.PAYPAL_API_BASE.rstrip("/")
    if base != SANDBOX_API_BASE:
        raise PayPalConfigError(
            f"PAYPAL_API_BASE must be {SANDBOX_API_BASE} (Sandbox only, live payments are disabled)"
        )
    if not config.settings.PAYPAL_CLIENT_ID or not config.settings.PAYPAL_CLIENT_SECRET:
        raise ApiError("PAYPAL_ERROR", "PayPal is not configured", 502)


def _http_client() -> httpx.Client:
    return httpx.Client(base_url=SANDBOX_API_BASE, timeout=TIMEOUT_SECONDS, transport=_transport)


def _send(request_kwargs: dict, action: str) -> dict:
    """Send one request to PayPal and return the JSON body.

    Any network error, timeout, non-2xx status or invalid JSON becomes
    ApiError("PAYPAL_ERROR", ..., 502) with a generic message.
    """
    try:
        with _http_client() as client:
            response = client.request(**request_kwargs)
    except httpx.HTTPError as error:
        # Log only the error type: never the request (it holds the token or the secret).
        logger.warning("PayPal %s failed: network error %s", action, type(error).__name__)
        raise ApiError("PAYPAL_ERROR", "Could not reach PayPal, please try again", 502) from None

    if not response.is_success:
        _log_paypal_error(response, action)
        if response.status_code == 401:
            # The token may have expired early: forget it, the next call gets a new one.
            _token_cache.clear()
        raise ApiError("PAYPAL_ERROR", "PayPal returned an error", 502)

    try:
        return response.json()
    except ValueError:
        logger.warning("PayPal %s failed: response is not JSON (status=%s)", action, response.status_code)
        raise ApiError("PAYPAL_ERROR", "PayPal returned an invalid response", 502) from None


def _log_paypal_error(response: httpx.Response, action: str) -> None:
    """Log only the status, the error name, the debug_id and the first detail
    (issue + description, for example ORDER_NOT_APPROVED). Never the full body."""
    name = None
    debug_id = response.headers.get("PayPal-Debug-Id")
    issue = None
    description = None
    try:
        body = response.json()
        # Orders API errors use "name"; OAuth errors use "error".
        name = body.get("name") or body.get("error")
        debug_id = body.get("debug_id") or debug_id
        # The precise reason is in details[0]: {"issue": "...", "description": "..."}.
        details = body.get("details")
        if isinstance(details, list) and details and isinstance(details[0], dict):
            issue = details[0].get("issue")
            description = details[0].get("description")
    except (ValueError, AttributeError):
        pass
    logger.warning(
        "PayPal %s failed: status=%s name=%s debug_id=%s issue=%s description=%s",
        action,
        response.status_code,
        name,
        debug_id,
        issue,
        description,
    )


def get_access_token() -> str:
    """Return an OAuth 2.0 access token (client credentials), cached in memory."""
    _check_config()
    client_id = config.settings.PAYPAL_CLIENT_ID

    cached = _token_cache
    if (
        cached.get("client_id") == client_id
        and _now() < cached.get("expires_at", 0) - TOKEN_SAFETY_MARGIN_SECONDS
    ):
        return cached["token"]

    body = _send(
        {
            "method": "POST",
            "url": "/v1/oauth2/token",
            # Basic auth with client_id:secret, as in the official docs.
            "auth": (client_id, config.settings.PAYPAL_CLIENT_SECRET),
            "data": {"grant_type": "client_credentials"},
            "headers": {"Accept": "application/json"},
        },
        action="token",
    )
    token = body.get("access_token")
    expires_in = body.get("expires_in")
    if not token or not isinstance(expires_in, (int, float)):
        logger.warning("PayPal token failed: response has no access_token or expires_in")
        raise ApiError("PAYPAL_ERROR", "PayPal returned an invalid response", 502)

    _token_cache.clear()
    _token_cache.update({"token": token, "expires_at": _now() + expires_in, "client_id": client_id})
    return token


def _auth_headers(request_id: Optional[str] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
        # Ask PayPal for the full order in the response (it includes the captures).
        "Prefer": "return=representation",
    }
    if request_id:
        # Idempotency: the same request id sent twice gives the same result, no duplicate.
        headers["PayPal-Request-Id"] = request_id
    return headers


def create_order(total_cents: int, currency: str, reference_id: str, request_id: str) -> dict:
    """Create a PayPal order (intent CAPTURE). No money moves at this step.

    Returns {"paypal_order_id", "status", "approve_url"}.
    """
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference_id,
                "amount": {"currency_code": currency, "value": from_cents(total_cents)},
            }
        ],
    }
    body = _send(
        {
            "method": "POST",
            "url": "/v2/checkout/orders",
            "json": payload,
            "headers": _auth_headers(request_id),
        },
        action="create order",
    )

    approve_url = None
    for link in body.get("links", []):
        # "approve" is the link where the buyer approves the payment.
        if link.get("rel") in ("approve", "payer-action"):
            approve_url = link.get("href")
            break

    return {"paypal_order_id": body.get("id"), "status": body.get("status"), "approve_url": approve_url}


def capture_order(paypal_order_id: str, request_id: str) -> dict:
    """Capture an order the buyer has approved.

    Returns {"status", "capture_id", "capture_status", "captured_value", "captured_currency"}.
    "status" is the ORDER status; the other fields come from the capture itself.
    """
    body = _send(
        {
            "method": "POST",
            "url": f"/v2/checkout/orders/{_safe_id(paypal_order_id)}/capture",
            "headers": _auth_headers(request_id),
        },
        action="capture order",
    )

    # The capture is in purchase_units[0].payments.captures[0].
    capture = {}
    purchase_units = body.get("purchase_units") or []
    if purchase_units:
        captures = (purchase_units[0].get("payments") or {}).get("captures") or []
        if captures:
            capture = captures[0]
    amount = capture.get("amount") or {}

    return {
        "status": body.get("status"),
        "capture_id": capture.get("id"),
        "capture_status": capture.get("status"),
        "captured_value": amount.get("value"),
        "captured_currency": amount.get("currency_code"),
    }


def get_order(paypal_order_id: str) -> dict:
    """Read an order from PayPal. Returns {"id", "status"}."""
    body = _send(
        {
            "method": "GET",
            "url": f"/v2/checkout/orders/{_safe_id(paypal_order_id)}",
            "headers": _auth_headers(),
        },
        action="get order",
    )
    return {"id": body.get("id"), "status": body.get("status")}


def _safe_id(paypal_order_id: str) -> str:
    """PayPal order ids are letters and digits. Refuse anything else (it goes into the URL)."""
    if not paypal_order_id or not paypal_order_id.isascii() or not paypal_order_id.isalnum():
        raise ApiError("VALIDATION_ERROR", "Invalid PayPal order id", 400)
    return paypal_order_id
