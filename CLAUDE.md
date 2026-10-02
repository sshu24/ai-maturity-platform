# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

AI maturity assessment platform: users answer a 42-question assessment (6 dimensions × 7 questions), it gets scored into one of 5 maturity tiers, and Claude produces an executive analysis and a 6-month roadmap. Stack: FastAPI backend, Streamlit frontend, PostgreSQL 16 (SQLAlchemy + Alembic), and AWS CDK infra in `infra/`.

## Commands

Local dev runs entirely through Docker Compose. `./app` is bind-mounted into both containers, and uvicorn runs with `--reload`, so code changes apply without a rebuild.

```bash
cp .env.example .env                 # then set POSTGRES_PASSWORD, SECRET_KEY, ANTHROPIC_API_KEY
docker compose up --build -d
docker compose run --rm fastapi alembic upgrade head
docker compose run --rm fastapi python -m app.db.seed     # super admin: admin@projecta.com / changeme123!

# New migration after editing app/db/models.py
docker compose run --rm fastapi alembic revision --autogenerate -m "description"
```

- Streamlit UI: http://localhost:8501 · API docs: http://localhost:8000/docs (only served when `ENV=development`)
- `alembic.ini` contains a hardcoded localhost URL, but `app/db/migrations/env.py` replaces it with `Settings.DATABASE_URL`, so Alembic reads the DB connection from `.env` / environment.

Tests (no Postgres or Claude API needed; they use in-memory SQLite and stub the AI calls):
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.fastapi.txt -r requirements-dev.txt
.venv/bin/python -m pytest                                # all
.venv/bin/python -m pytest tests/test_api.py -k stale     # single test
```
`tests/conftest.py` sets the env vars before importing `app` (settings are cached at import), overrides `get_db`, and patches `assessment.SessionLocal` for background jobs. An autouse fixture makes any real Claude call fail. CI (`.github/workflows/ci.yml`) runs pytest and the infra build and tests.

Infra (`infra/`, AWS CDK in TypeScript):
```bash
cd infra && npm install
npm run build        # tsc
npm test             # jest; single test: npx jest -t "<name>"
npx cdk synth | npx cdk diff | npx cdk deploy
```

## Architecture

**Two separate services with separate requirements files.** FastAPI (`requirements.fastapi.txt`) and Streamlit (`requirements.streamlit.txt`) are built into separate images from the same `app/` package. Streamlit only reaches the backend over HTTP (`FASTAPI_BASE_URL`). It must not import DB or route code, because the Streamlit image lacks those dependencies.

**The Streamlit frontend is a single file.** All UI lives in `app/streamlit_app.py`: the `api_get/post/patch/delete` helpers, `show_*_page()` functions, and routing driven by `st.session_state`. The `app/pages/*.py` and `app/probes/technical_probe.py` files are empty placeholders. Do not put real pages under `app/pages/`, because Streamlit auto-discovers that directory as multipage navigation. Shared CSS and widget helpers live in `app/styles.py`.

**The question bank is YAML-driven.** `app/config/questions.yaml` defines dimensions, questions, option values (1–5) and weights. `app/components/question_engine.py` loads it and validates it, enforcing the metadata counts. `scoring.py` computes weighted dimension and overall scores and maps them to tiers through `MATURITY_TIERS`. The tier colours and labels are duplicated in `TIER_CONFIG` in `streamlit_app.py`. `recommendations.py` holds static recommendations for each tier, and `report.py` builds the PDF with ReportLab.

**Data model** (`app/db/models.py`): Organisation → User → Assessment (`draft`/`in_progress`/`completed`) → Response (one per question, upserted) → Result (one per assessment). Result stores `dimension_scores` and `recommendations` as JSON, plus the AI output `ai_analysis`/`ai_roadmap` (JSON) with `analysis_status`/`roadmap_status` (`pending`/`generating`/`complete`/`failed`), `*_error` and `*_started_at`.

**Multi-tenancy and RBAC.** There are four roles: `super_admin`, `client_admin`, `assessor`, `viewer`. JWT auth goes through `app/auth/rbac.py`: `get_current_user`, plus `require_role(...)` as a dependency factory. Org isolation is enforced by hand in the route handlers by comparing `organisation_id` (for example `_get_assessment_or_404` in `assessment.py`), so any new endpoint has to do the same.

**The Claude integration is async with polling.** Prompts, output schemas and the API call live in `app/components/ai_agents.py`. It uses the `anthropic` SDK's `messages.parse()` with Pydantic models (structured outputs). Every failure, including refusals, `max_tokens` cut-offs and API errors, is raised as `AIGenerationError` with a message that is safe to show users. The model comes from `ANTHROPIC_MODEL` in settings. In `app/api/routes/assessment.py`, `POST /assessments/{id}/analyse` and `/roadmap` return the cached result unless `?force=true`. Otherwise they claim the job atomically (setting `{kind}_status="generating"` and `{kind}_started_at`) and schedule `_run_ai_job` as a `BackgroundTask`. A job still "generating" after `AI_JOB_STALE_SECONDS` can be reclaimed. The job opens its own `SessionLocal()` and writes `ai_{kind}` and `{kind}_status`, or a `{kind}_error`. The UI polls `GET .../analyse/status` and `.../roadmap/status`. Columns follow the `{kind}` naming (`analysis`/`roadmap`), and the code relies on it through `getattr`. The roadmap schema returns `target_dimension_scores` as a list, and `generate_roadmap` converts it to a `{name: score}` dict because the UI and PDF expect that shape.

**Infra** (`infra/lib/infra-stack.ts`): VPC, RDS Postgres, Secrets Manager (DB credentials plus an app secret holding `SECRET_KEY` and the API keys), an ECS Fargate service for each container, an ALB, and CloudFront. The app secret is created with placeholder values that must be replaced by hand after deploying. The stack also passes `OPENAI_API_KEY` and `LANGCHAIN_API_KEY` to the containers, but the app doesn't use them.
