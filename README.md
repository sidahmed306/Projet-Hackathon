# AI Payment Agent

A multilingual (French, Arabic, English) AI shopping assistant built for the PayPal AI Hackathon.
The user sets a purchase mandate (category, intended use, maximum budget), and the AI suggests up to 3 products from a demo catalog.
The server enforces the mandate and recalculates every price. Payment goes through PayPal Checkout (Sandbox) and only happens after the user explicitly approves it. The AI never triggers a payment.

**Status: in development**

## Planned stack

- **Backend:** Python + FastAPI
- **Frontend:** React + Vite + Tailwind CSS
- **Database:** SQLite
- **AI:** Google Gemini (free tier), plus a "mock" mode that works without an API key
- **Payments:** PayPal Orders API v2 (Sandbox)
- **Deployment:** Render (planned)

## Folder structure

```
ai-payment-agent/
├── README.md          Project overview (this file)
├── LICENSE            MIT license
├── .gitignore         Files Git must never track
├── .env.example       List of required environment variables (no real values)
├── backend/           FastAPI server (coming soon)
├── frontend/          React app (coming soon)
└── docs/
    ├── api.md         API contract between frontend and backend
    └── architecture.md Components and payment flow
```

## Demo data

All products and prices in this project are **fictional demo data**. They do not represent real products, real sellers or real offers. All payments use the PayPal **Sandbox**: no real money is involved.

## Setup

Coming soon.

## License

MIT, see [LICENSE](LICENSE).
