# AGENTS.md — production-ai-agent-ops

> **Role:** Entrypoint & working rules for AI coding agents in this repository.
> **Rule:** Keep this file short (< 150 lines). Do NOT duplicate schemas, specs, daily logs, or linter rules here — point to their SSOT instead.

## 1. Project Snapshot
- **Purpose:** Production-minded State-Machine AI Operations Agent featuring explicit `LangGraph` + SQL-first state persistence, pre-LLM/pre-DB PDPA PII redaction, Human-in-the-Loop (HITL) approval gates, idempotent retry + DLQ replay, Tiered Gemini 3.x routing (`62.78%` verified cost reduction), `n8n` workflows, and a No-Login Next.js Live Control Plane (`$0` Free-Tier Stack).
- **Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, LangGraph, `psycopg3` (`psycopg_pool`), PostgreSQL 16, `google-genai` (Tiered Gemini 3.x), `n8n` (JSON workflows), Next.js 15 (App Router, TypeScript, Tailwind CSS v4), Docker.
- **Primary Language:** Code, comments, commits, and docs in English (Thai / code-mixed text is used intentionally only inside synthetic PDPA/ops test fixtures and bilingual UI labels).

## 2. Single Sources of Truth (SSOT Map)
Read these on-demand before making architectural or scope changes:
- **Live Task State & Handoff:** `docs/PROGRESS.md` *(Read at start of every session)*
- **Feature Scope & Requirements:** `docs/SPEC.md`
- **Architecture Decisions (Why):** `docs/adr/`
- **Environment Variables:** `.env.example` & `web/.env.example`
- **Database Schema:** `sql/001_schema.sql` *(Executable SSOT)*
- **API & Pydantic Contracts:** `api/app/schemas/` & `api/app/routers/` *(Executable SSOT)*
- **Eval Thresholds:** `eval/thresholds.json` *(Executable SSOT)*
- **Linter & Test Config:** `api/pyproject.toml` & `.github/workflows/ci.yml`

## 3. Standard Commands
Always run verification commands before reporting a task as done:
```bash
# Backend lint & tests (inside api/)
ruff check app ../tests ../eval
pytest -v

# Reproducible benchmark gate (repo root)
python eval/run_benchmark.py

# Docker Compose validation (repo root)
docker compose config -q

# Frontend typecheck & production build (inside web/)
npx tsc --noEmit && npm run build
```

## 4. Repository Map
```text
production-ai-agent-ops/
├── api/app/          # FastAPI backend (config, db, dependencies, main, routers/, schemas/, services/, data/)
├── web/              # Next.js 15 App Router Live Control Plane (/backend/* same-origin proxy)
├── sql/              # PostgreSQL 16 DDL (agent_runs, transitions, approvals, idempotency, DLQ)
├── data/fixtures/    # Synthetic TH/EN webhook payloads & PDPA PII test cases
├── eval/             # 24-case safety & cost-routing benchmark + thresholds
├── n8n/              # Exportable n8n workflow JSONs (intake + HITL callback)
├── scripts/          # Motion demo exporter (render_motion_demo.mjs)
├── tests/            # unit/, integration/ (live PG16), eval/ (benchmark gates)
├── docs/             # SPEC.md, PROGRESS.md, adr/ (0001..NNNN), assets/
└── .github/workflows/ci.yml
```

## 5. Hard Guardrails (Non-Negotiable)
- **Zero Raw PII Persistence (PDPA):** Redact Thai National IDs, phone numbers, emails, bank accounts, and personal names at the API boundary before any LLM call, log line, or DB insert. Persist only `redacted_input` and `redaction_summary`. All fixtures must use synthetic IDs (`REQ-2026-0001`, `CUST-DEMO-01`).
- **1:1 SQL ↔ Pydantic v2 Alignment:** `sql/001_schema.sql` and `api/app/schemas/` must stay locked on enum values (agent states, approval statuses, DLQ statuses, routing tiers), numeric bounds, and `CHECK` constraints.
- **SQL-First Concurrency & PgBouncer Safety:** Keep `psycopg_pool` with `prepare_threshold=None`, idempotency via `INSERT ... ON CONFLICT (idempotency_key)` + payload hash verification, and `FOR UPDATE` row locking on HITL approvals and DLQ replay. Keep DB-touching FastAPI routes synchronous `def`.
- **Auth & Webhook Protection:** Preserve `AUTH_MODE=token|demo_sandbox` (never expose secrets to browser) and require `X-Webhook-Secret` on `/webhooks/n8n`.
- **Zero Cross-Origin Browser Calls:** Browser code in `web/` must call `/backend/*` (proxied via `web/next.config.ts`), never `*.onrender.com` directly.
- **No Unapproved Stack Changes:** Check `docs/adr/` before changing LangGraph, SQL-first persistence, LLM SDK (`google-genai`), or proxy architecture; record new trade-offs in a new ADR.
- **Verify Before Finishing:** Run lint, tests, benchmark, and build after code changes. Never claim checks pass without running them.

## 6. Session Continuity & Git Conventions
- **Start of every session:** Read `docs/PROGRESS.md` and run `git status` + `git log -n 5 --oneline` before editing code.
- **After completing each task:** Run verification -> `git commit` -> update `docs/PROGRESS.md`.
- **Commits:** Use Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`). Do not include `Day X` labels in commits or `README.md`.
- **New Decisions:** Record significant architectural trade-offs in `docs/adr/NNNN-short-title.md` (MADR format).
