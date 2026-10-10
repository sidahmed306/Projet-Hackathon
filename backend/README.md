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

# 5. Run the tests
pytest

# 6. Start the server (stop it with Ctrl+C)
uvicorn app.main:app --port 8000 --reload
```

Then open http://localhost:8000/docs to see and try the API, or http://localhost:8000/api/health to check that it runs.
