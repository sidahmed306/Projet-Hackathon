"""Manual smoke test against the REAL PayPal Sandbox (no real money).

Run from backend/ (with the venv active):
    python -m scripts.paypal_smoke_test                    # create a 1.00 USD order
    python -m scripts.paypal_smoke_test --status ORDER_ID  # show the order status
    python -m scripts.paypal_smoke_test --capture ORDER_ID # capture it after approval

It uses PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET from the .env at the project root.
It never prints the token or the secret.
"""

import argparse
import logging
import sys
import uuid

from app import paypal_client
from app.errors import ApiError


def create() -> None:
    paypal_client.get_access_token()  # the token itself is never printed
    print("OK: got a PayPal access token.")
    order = paypal_client.create_order(
        total_cents=100,  # 1.00
        currency="USD",
        reference_id="smoke-test",
        request_id=str(uuid.uuid4()),
    )
    print(f"PayPal order id: {order['paypal_order_id']}")
    print(f"Order status:    {order['status']}")
    print(f"Approve URL:     {order['approve_url']}")
    print()
    print("Next: open the approve URL, log in with a Sandbox PERSONAL account and approve.")
    print(f"Then run: python -m scripts.paypal_smoke_test --capture {order['paypal_order_id']}")


def capture(order_id: str) -> None:
    result = paypal_client.capture_order(order_id, request_id=str(uuid.uuid4()))
    print(f"Order status:    {result['status']}")
    print(f"Capture status:  {result['capture_status']}")
    print(f"Captured amount: {result['captured_value']} {result['captured_currency']}")


def status(order_id: str) -> None:
    order = paypal_client.get_order(order_id)
    print(f"PayPal order id: {order['id']}")
    print(f"Order status:    {order['status']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PayPal Sandbox smoke test")
    # Only one of the two options at a time.
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--capture", metavar="ORDER_ID", help="capture an approved order")
    group.add_argument("--status", metavar="ORDER_ID", help="show the status of an order")
    args = parser.parse_args()

    # Show the client's warnings (status, error name, debug_id only).
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    try:
        if args.capture:
            capture(args.capture)
        elif args.status:
            status(args.status)
        else:
            create()
    except paypal_client.PayPalConfigError as error:
        print(f"Configuration error: {error}")
        return 1
    except ApiError as error:
        print(f"Error {error.code}: {error.message}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
