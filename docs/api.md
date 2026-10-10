# API contract

This document is the contract between the frontend and the backend. Both sides must follow it. If something needs to change, update this file first.

Base URL (local development): `http://localhost:8000`

## General rules

- All requests and responses use JSON.
- **Money:** every amount is a **string with 2 decimals**, for example `"799.00"`. Currency is always `"USD"`.
- **Languages:** `"fr"`, `"ar"` or `"en"`.
- **Errors:** every error uses the same shape:

```json
{
  "error": {
    "code": "SOME_CODE",
    "message": "Human readable explanation"
  }
}
```

### Common error codes

| Code | HTTP status | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | The request JSON is missing a field or has a wrong value |
| `PRODUCT_NOT_FOUND` | 404 | The `product_id` does not exist in the catalog |
| `ORDER_NOT_FOUND` | 404 | The order does not exist |
| `NOT_FOUND` | 404 | The route (URL) does not exist |
| `MANDATE_EXCEEDED` | 422 | The total is above the mandate's `max_budget` |
| `CATEGORY_MISMATCH` | 422 | The product is not in the mandate's category |
| `AI_UNAVAILABLE` | 503 | The AI provider failed or is rate limited |
| `PAYPAL_ERROR` | 502 | PayPal returned an error or could not be reached |
| `HTTP_ERROR` | 4xx | Other HTTP errors, for example 405 when the method is not allowed |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

### The mandate object

Used by `/api/chat`, `/api/quote` and `/api/orders`:

```json
{
  "category": "laptop",
  "use": "university programming courses",
  "max_budget": "800.00",
  "currency": "USD"
}
```

---

## a. GET /api/health

**Purpose:** check that the server is running.

**Request:** no body.

**Success response (200):**

```json
{ "status": "ok" }
```

**Errors:** none expected (if the server is down, there is no response).

---

## b. GET /api/products?category=&max_price=

**Purpose:** list products from the demo catalog. Both query parameters are optional.

- `category`: only return products in this category (example: `laptop`)
- `max_price`: only return products whose price is lower than or equal to this value (example: `800.00`)

**Request example:** `GET /api/products?category=laptop&max_price=800.00`

**Success response (200):**

```json
[
  {
    "id": "prod_001",
    "name": "DemoBook Air 13",
    "category": "laptop",
    "description": "Light 13-inch laptop, 16 GB RAM, 512 GB SSD.",
    "price": "749.00",
    "shipping": "15.00",
    "currency": "USD",
    "is_demo": true
  }
]
```

**Errors:** `VALIDATION_ERROR` (for example `max_price=abc`).

---

## c. POST /api/chat

**Purpose:** send a user message to the AI. The AI replies in the user's language, extracts the purchase mandate and suggests up to 3 products. The AI **never** creates an order or a payment.

**Request:**

```json
{
  "message": "Je cherche un ordinateur portable pour mes cours de programmation, budget 800 dollars",
  "language": "fr",
  "history": [
    { "role": "user", "content": "Bonjour" },
    { "role": "assistant", "content": "Bonjour ! Que souhaitez-vous acheter ?" }
  ]
}
```

- `message` (required): the user's text.
- `language` (optional): `"fr"`, `"ar"` or `"en"`. If missing, the server detects it.
- `history` (optional): previous messages, each with `role` (`"user"` or `"assistant"`) and `content`.

**Success response (200):**

```json
{
  "reply": "Voici 2 ordinateurs qui respectent votre budget de 800,00 USD.",
  "language": "fr",
  "mandate": {
    "category": "laptop",
    "use": "programming courses",
    "max_budget": "800.00",
    "currency": "USD"
  },
  "needs_clarification": false,
  "product_ids": ["prod_001", "prod_004"]
}
```

- `needs_clarification`: `true` when the AI is missing information (for example no budget). In that case `reply` contains a question, and `product_ids` is empty.
- `mandate` fields can be `null` when they are not known yet.
- `product_ids`: at most 3. The server only returns IDs that exist in the catalog and match the mandate.

**Errors:** `VALIDATION_ERROR`, `AI_UNAVAILABLE`.

---

## d. POST /api/quote

**Purpose:** get the detailed price of one product, calculated by the server from the database.

**Request:**

```json
{
  "product_id": "prod_001",
  "mandate": {
    "category": "laptop",
    "use": "programming courses",
    "max_budget": "800.00",
    "currency": "USD"
  }
}
```

**Success response (200):**

```json
{
  "product_id": "prod_001",
  "lines": [
    { "label": "Price", "amount": "749.00" },
    { "label": "Shipping", "amount": "15.00" }
  ],
  "total": "764.00",
  "currency": "USD",
  "unknown": ["tax"],
  "within_mandate": true
}
```

- `unknown`: values the server cannot know in advance (for example `"tax"`). The frontend must show them to the user.
- `within_mandate`: `false` if `total` is above `max_budget` (this is not an error for a quote, it is information).

**Errors:** `VALIDATION_ERROR`, `PRODUCT_NOT_FOUND`.

---

## e. POST /api/orders

**Purpose:** create an order and a PayPal Sandbox order. The server re-reads the price from the database and recalculates the total. It refuses if the total is above `max_budget`.

**Request:**

```json
{
  "product_id": "prod_001",
  "mandate": {
    "category": "laptop",
    "use": "programming courses",
    "max_budget": "800.00",
    "currency": "USD"
  }
}
```

**Success response (201):**

```json
{
  "order_id": "ord_0001",
  "paypal_order_id": "5O190127TN364715T",
  "status": "CREATED"
}
```

The frontend then opens the PayPal window with `paypal_order_id`. No money moves at this step.

**Errors:** `VALIDATION_ERROR`, `PRODUCT_NOT_FOUND`, `MANDATE_EXCEEDED`, `CATEGORY_MISMATCH`, `PAYPAL_ERROR`.

---

## f. POST /api/orders/{paypal_order_id}/capture

**Purpose:** capture the payment **after** the user approved it in the PayPal window. The server asks PayPal for the real result and does not trust the browser.

**Request example:** `POST /api/orders/5O190127TN364715T/capture` (no body).

**Success response (200):**

```json
{
  "order_id": "ord_0001",
  "status": "COMPLETED"
}
```

- `status`: `"COMPLETED"`, `"PENDING"`, `"FAILED"` or `"CANCELLED"`, as verified by the server with PayPal.

**Errors:** `ORDER_NOT_FOUND`, `PAYPAL_ERROR`.

---

## g. GET /api/orders/{order_id}

**Purpose:** read the status of an order (for the confirmation page).

**Request example:** `GET /api/orders/ord_0001`

**Success response (200):**

```json
{
  "order_id": "ord_0001",
  "product_id": "prod_001",
  "total": "764.00",
  "currency": "USD",
  "status": "COMPLETED",
  "created_at": "2026-10-10T14:30:00Z"
}
```

- `status`: `"CREATED"`, `"COMPLETED"`, `"PENDING"`, `"FAILED"` or `"CANCELLED"`.
- `created_at`: ISO 8601 date in UTC.

**Errors:** `ORDER_NOT_FOUND`.

---

## h. POST /api/orders/{paypal_order_id}/cancel

**Purpose:** mark an order as cancelled when the user closed or cancelled the PayPal window.

**Request example:** `POST /api/orders/5O190127TN364715T/cancel` (no body).

**Success response (200):**

```json
{
  "order_id": "ord_0001",
  "status": "CANCELLED"
}
```

**Errors:** `ORDER_NOT_FOUND`.

---

## Security rules

1. **The frontend never sends prices to trust.** It only sends a `product_id`. The server always reads prices from the database.
2. **The server never trusts AI output for amounts.** The AI may suggest products, but every price and total is recalculated by the server.
3. **Payment capture only happens after the user approves** in the PayPal window. The AI cannot create, approve or capture a payment.
4. **Secrets only live in `.env` on the server.** PayPal secret and Gemini key are never sent to the browser and never committed to Git.
5. **Idempotency.** The same create or capture request sent twice (double click, network retry) must not create two orders or two payments. The server uses PayPal's request ID header for this.
6. **The server verifies the captured amount.** After capture, the server checks that the captured amount and currency returned by PayPal are exactly equal to the order total stored in the database. If not, the order is marked `FAILED`.
