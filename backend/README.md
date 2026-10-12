# Backend

This folder will contain the Python + FastAPI server: the API endpoints described in [docs/api.md](../docs/api.md), the SQLite demo catalog, the AI layer (Gemini or mock), mandate enforcement, price recalculation and the PayPal Sandbox integration. Owner: backend developer.

## Run locally

Requires Python 3.10 or newer. All commands are run from the `backend/` folder.

```bash
# 1. Create the virtual environment (only the first time)
python3 -m venv .venv

# 2. Activate it (every time you open a new terminal)
source .venv/bin/activate

# 3. Install the dependencies (first time, or when requirements.txt changes)
pip install -r requirements.txt

# 4. Create your .env at the project root (only the first time), then fill in your values
cp -n ../.env.example ../.env

# 5. (Optional) Load the demo catalog into backend/app.db
#    The server also does this automatically on startup when the table is empty.
#    Safe to run again after editing data/products.json: no duplicates.
python -m app.seed

# 6. Run the tests (they use a temporary database, never app.db)
pytest

# 7. Start the server (stop it with Ctrl+C)
uvicorn app.main:app --port 8000 --reload
```

Then open http://localhost:8000/docs to see and try the API, or http://localhost:8000/api/health to check that it runs.
Try the catalog at http://localhost:8000/api/products?category=laptop&max_price=800.00

## PayPal Sandbox smoke test

This calls the **real PayPal Sandbox** (test money only) with the credentials in `../.env`
(`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_API_BASE=https://api-m.sandbox.paypal.com`).
It never prints the token or the secret. The automated tests never call PayPal.

```bash
# 1. Create a 1.00 USD order: prints the order id, its status and an approve URL
python -m scripts.paypal_smoke_test

# 2. Open the approve URL, log in with a Sandbox *personal* account and approve

# 3. Capture the approved order
python -m scripts.paypal_smoke_test --capture ORDER_ID
```
