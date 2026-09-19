# Contributing to Football Tactical Analyzer

These guidelines cover code organization, data handling, and checks for contributions.
See [the architecture plan](docs/ARCHITECTURE.md) for the proposed application design.

## Structure and stack

- Follow `docs/ARCHITECTURE.md`; update it when an architectural decision changes.
- Use React, Vite, JavaScript, and Recharts (or another lightweight chart library)
  in `frontend/`.
- Use Python, FastAPI, and Pydantic in `backend/app/`, with `api/`, `analytics/`,
  `data/`, and `models/` packages; put pytest tests in `backend/tests/`.
- Keep dataset files in root `data/` and documentation in `docs/`.
- Separate collection/source adapters, pure analytics, and HTTP routes. Analytics
  must not fetch data or depend on FastAPI. Routes must not contain scoring formulas.
- Define a data-source interface and canonical models so providers are replaceable.
  Discover clubs and seasons from data; never hardcode them in core logic.

## Data and analytics

- Prefer transparent formulas using pandas, numpy, and scipy. Use scikit-learn only
  when its analytical value is clear and documented.
- Document every score's inputs, units, direction, formula, normalization cohort,
  missing-data policy, and limitations before exposing it to users.
- Normalize rate metrics and comparison cohorts deliberately. Relative league-season
  ranks describe style, not absolute strength across leagues or eras.
- Preserve provenance, coverage, and source definitions. Never silently fabricate
  statistics, replace missing values with zero, or claim a proxy measures intent.
- Clearly label fixtures/sample data in storage, API responses, and the UI. Do not
  mix them into real-data normalization or evaluation.
- Treat simulation outputs as uncertain model estimates. Document assumptions and
  validate against held-out matches before claiming predictive accuracy.

## Development

- Add Python type hints and validate external inputs with Pydantic. Keep functions
  small and dependencies purposeful; avoid unnecessary framework abstractions.
- Test important analytics with pytest, including missing/invalid inputs, rate
  conversion, cohort boundaries, constant cohorts, score direction, and probability
  invariants. Add API and frontend checks as those layers are implemented.
- Run relevant checks for each change and note any checks that could not be run.
  For documentation changes, review paths and run `git diff --check`.
- Never commit credentials, API keys, `.env` files, virtual environments,
  `node_modules`, generated build artifacts, or large raw datasets. Only commit
  small, reviewed, clearly labeled fixtures with provenance and redistribution rights.
- Keep commits focused on one change or milestone and review the staged diff before
  committing.
- Follow the implementation order in `docs/ARCHITECTURE.md`. The repository is
  currently in the planning stage.
