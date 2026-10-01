# Football Tactical Analyzer

Analyze, compare, and simulate football teams across seasons.

The current scaffold includes a React landing page and a FastAPI backend with
`GET /health`. Analyze Team, Compare Teams, and Match Simulator are placeholders.
No football data, analytics, or simulation results are included yet.

The backend now includes a modular data layer for public StatsBomb JSON and a
synthetic offline fixture provider. It is not connected to the frontend or API yet.
See [DATA.md](docs/DATA.md) for usage, available competitions/seasons, caching, and
coverage limitations. Downloaded data stays in the ignored `data/cache/` directory.

## Requirements

- Python 3.9 or newer (Python 3.12+ recommended for new installations)
- Node.js 20.19+ or 22.12+ (Node.js 24 works) and npm
- Two terminal windows, both starting in the repository root

## Run locally

### Backend — terminal 1

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On Windows, activate with `.venv\Scripts\activate` instead. On subsequent runs,
activate the existing environment and run the Uvicorn command; installation is only
needed after dependency changes.

- Health: <http://127.0.0.1:8000/health> — returns `{"status":"healthy"}`
- Interactive API documentation: <http://127.0.0.1:8000/docs>

### Frontend — terminal 2

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. On subsequent runs, use `npm run dev`; rerun `npm ci`
after dependency changes. The landing page does not call the backend yet.

The API permits browser requests from `http://localhost:5173` and
`http://127.0.0.1:5173`, following FastAPI's [CORS configuration](https://fastapi.tiangolo.com/tutorial/cors/).
Vite uses port 5173 with `strictPort`, so it will report an error instead of switching
to an origin the backend does not allow. If that port is busy, stop the other server.
Production origins will need separate configuration before deployment.

Use Ctrl+C in each terminal to stop its server. No API keys or `.env` files are needed.

## Checks

From the repository root, after installing dependencies:

```bash
cd backend
source .venv/bin/activate
python -m pytest
python -m pip check
```

In a separate terminal, from the repository root:

```bash
cd frontend
npm run build
```

The build writes ignored files to `frontend/dist/`. Run `npm run preview` from
`frontend/` to inspect that build at the URL printed in the terminal. The preview
server is separate from the port-5173 development server.

## Project layout

```text
backend/
  app/
    main.py       FastAPI application and local CORS configuration
    api/          HTTP routes
    analytics/    Reserved for analytical functions
    data/         Provider interface, StatsBomb adapter, cache, and fixtures
    models/       Pydantic schemas
  tests/          Health and CORS tests
  pyproject.toml  Python dependencies and pytest configuration
frontend/
  src/            React landing page and styles
  package.json    Frontend dependencies and commands
docs/             Architecture and metric plans
```

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the planned design and
[CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines. Frontend setup uses
[Vite](https://vite.dev/guide/). Analytics and chart dependencies will be added when
those features are implemented.
