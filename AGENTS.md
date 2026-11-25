# Production AI Agent Ops — Project `AGENTS.md`

> **Role:** Senior AI & Backend Engineer building `ApecSinlapachai/production-ai-agent-ops` — a production-minded **State-Machine AI Operations Agent** with **Human-in-the-Loop (HITL) Approval Gates**, **PDPA PII Redaction**, **Idempotent Retry + DLQ Reliability**, **`n8n` Workflow Integration**, **Tiered Model Routing Cost Benchmark (`50–70%` cost reduction)**, and a **No-Login Next.js Live Demo**.

---

## 1. Core Idea & Engineering Rules

1. **Public Portfolio Hygiene (100% Clean & English-First):**
   - All source code, comments, CLI output, commit messages, and documentation MUST be in clear English (Thai / code-mixed text is used intentionally only inside synthetic test fixtures, PDPA PII redaction test cases, and bilingual UI labels).
   - **Zero real PII, zero real company secrets, zero `.env` commits.** All sample payloads, customer records, and webhook fixtures must use synthetic IDs (`REQ-2026-0001`, `CUST-DEMO-01`, `08X-XXX-XXXX`, fake Thai National IDs that clearly fail/pass synthetic pattern tests without matching real people).

2. **Core Product Scope (What This System Proves):**
   - **Explicit State-Machine AI Agent (`LangGraph` or typed Python State Machine):**
     - Deterministic workflow transitions: `RECEIVED` → `PII_REDACTED` → `INTENT_ROUTED` → `CONTEXT_FETCHED` → `DRAFT_GENERATED` → `AWAITING_APPROVAL` (HITL Gate) → `APPROVED` / `REJECTED` → `EXECUTING_ACTION` → `COMPLETED` (or `FAILED_RETRYING` → `DLQ`).
     - Every state transition is persisted in PostgreSQL with timestamps, model used, token counts, latency, and audit trail.
   - **Human-in-the-Loop (HITL) Approval Gate:**
     - High-impact or policy-sensitive external actions (e.g., refund/credit issuance, CRM/ticket updates, outbound notifications) MUST pause at `AWAITING_APPROVAL` with a structured action preview until explicitly approved or rejected via API / Web UI.
   - **PDPA PII Redaction Layer (Pre-LLM & Pre-Log):**
     - Deterministic regex + structured detector strips/masks Thai National IDs, phone numbers, emails, bank accounts, and personal names **before** any text is sent to an external LLM or written to application logs, with reversible/tokenized placeholders where needed only inside authorized boundaries.
   - **Production Reliability Engineering:**
     - **Idempotency Keys:** Every inbound webhook / agent trigger requires (or derives) an `Idempotency-Key` backed by a PostgreSQL unique constraint so duplicate webhooks never double-execute side effects.
     - **Retry + Exponential Backoff:** Transient external/LLM failures retry with bounded exponential backoff + jitter.
     - **Dead-Letter Queue (DLQ):** Exhausted jobs are moved to a `dead_letter_jobs` table with failure reason, payload snapshot (PII-redacted), and a manual replay endpoint (`POST /api/v1/dlq/{job_id}/replay`).
   - **Tiered Model Routing & Cost Benchmark (`50–70%` Cost Reduction):**
     - Route low-complexity steps (intent classification, entity extraction, simple policy checks) to a fast/low-cost model (`GEMINI_FAST_MODEL`) and escalate only complex reasoning, multi-step synthesis, or edge-case drafting to a frontier/complex model (`GEMINI_COMPLEX_MODEL`), with automatic `429` fallback chaining.
     - Include a reproducible benchmark script (`eval/run_benchmark.py`) comparing **Always-Frontier vs. Tiered Routing** across accuracy, latency, and estimated USD per 1,000 runs.
   - **`n8n` Exportable Integration:**
     - Ship ready-to-import `n8n/` workflow JSON files demonstrating webhook intake → Agent API call → HITL approval callback → downstream notification/action.

3. **Free-Tier Budget (`$0` Infrastructure) & Public No-Login Demo Safety:**
   - **Stack:** `FastAPI` + `Pydantic v2` + `LangGraph` (or explicit typed State Machine) + `psycopg3` (`psycopg_pool`) + `PostgreSQL 16` + `google-genai` (tiered Gemini models) + `n8n` (JSON workflows) + `Next.js` (App Router + Tailwind CSS).
   - **Hosting targets:** Vercel Hobby (Frontend), Render Free Web Service / Docker (`api/`), Supabase Free Tier (PostgreSQL in production) & `postgres:16-alpine` (local/CI).
   - **Abuse guardrails & Free-Tier resilience:**
     - Enforce IP-hashed (`SHA-256`) sliding-window rate limiting reading the first hop of `X-Forwarded-For` behind Render/Vercel proxies, strict payload length bounds, strict `CORS_ORIGINS` (exposing `Retry-After`), a frontend `/health` warm-up ping for Render cold starts, and a transparent deterministic/replay fallback if the LLM API returns `429 RESOURCE_EXHAUSTED`.
   - **Sync FastAPI Route Policy (if using sync `psycopg_pool`):** Keep DB-touching FastAPI route handlers synchronous `def` (or consistently async end-to-end) so the asyncio event loop is never blocked.

4. **1:1 SQL ↔ Pydantic v2 Alignment:**
   - `sql/001_schema.sql` and `api/app/schemas/` MUST stay locked 1:1 on enum values (agent states, approval statuses, DLQ statuses, routing tiers), numeric bounds, and `CHECK` constraints.

5. **HR 15-Second Conversion Asset:**
   - Embed a **`60-Second Demo GIF`** at the top of `README.md` alongside the **No-Login Vercel Live Demo** link, a **Mermaid State-Machine Diagram**, the **Model Routing Cost Benchmark table**, and verified `pytest` + `GitHub Actions CI` results.

6. **Mandatory Context & Progress Sync (`AGENTS.md` Update Policy):**
   - Whenever a milestone is completed and all lint (`ruff`) and test (`pytest`) checks pass, update `AGENTS.md` (Section 2 Repository Structure, Section 3 Execution Roadmap, and verified test/lint counts) before wrapping up so full context is preserved across sessions.
   - When updating `README.md` or writing Git commit messages for GitHub pushes, describe completed features and verified test counts directly without including `Day X` labels.

---

## 2. Planned Repository Structure

> **Current Status:** `Live Cloud Rollout, E2E Verification & Demo GIF Complete` — Deployed to free-tier cloud (**Supabase** PostgreSQL + RLS on `enterprise-rag-ops-copilot`, **Render Free Web Service** at `https://production-ai-agent-ops-api.onrender.com` with `AUTH_MODE=demo_sandbox`, and **Vercel Hobby** at `https://production-ai-agent-ops.vercel.app`). Live GitHub Actions CI (`backend-ci` + `frontend-ci`) passed green, all 6 live E2E flows verified (`ONLINE • PG16 CONNECTED`, PDPA PII redaction, `X-Idempotency-Replayed: true`, HITL Approve & Resume, 3x retry → DLQ capture & replay, and `62.78%` Cost Benchmark scorecard), `docs/assets/demo-60s.gif` (`1280x720`) generated, and `README.md` updated with live links and GIF. Local verification: `ruff`: 0 errors across `app`, `tests`, `eval`; `pytest`: 40 passed [31 unit + 7 live PG16 integration + 2 eval gates]; `npx tsc --noEmit && npm run build`: exit 0; `docker compose config -q`: exit 0.

### Locked Architectural Decisions
- **LangGraph + SQL-First Transitions:** Use `LangGraph` `StateGraph` wrapping explicit step handlers, persisting every transition into `agent_runs` and `agent_state_transitions` (no opaque LangGraph checkpointer).
- **Gemini 3.x Model Routing:** Keep `gemini-3.5-flash-lite` (`FAST`), `gemini-3.8-flash` (`COMPLEX`), and `gemini-3.1-flash-lite` (`FALLBACK`) as configured in `.env.example`.
- **Public Demo Auth Mode:** `AUTH_MODE=token|demo_sandbox` (`token` default; `demo_sandbox` for public Vercel demo without exposing secrets to the browser; `/webhooks/n8n` always requires `X-Webhook-Secret`).
- **Zero Raw PII Persistence:** Redact PII at the API boundary before DB insert or logging; persist only `redacted_input` and `redaction_summary`.
- **Supabase PgBouncer & Concurrency Safety:** `psycopg_pool` with `prepare_threshold=None`, idempotency via `INSERT ... ON CONFLICT (idempotency_key)` + payload hash check, and `FOR UPDATE` row locking on HITL approvals.

```text
production-ai-agent-ops/
├── .github/workflows/ci.yml            # [DONE] Ruff, Pytest (PG16 + Eval Gates), Benchmark CLI, Docker build, Next.js CI
├── docs/assets/demo-60s.gif            # [DONE] 1280x720 walkthrough GIF for README top section
├── n8n/                                # [DONE] Exportable n8n workflow JSONs (intake + HITL callback) + setup notes
├── sql/
│   └── 001_schema.sql                  # [DONE] Agent runs, state transitions, HITL approvals, idempotency, DLQ, cost logs
├── data/fixtures/                      # [DONE] Synthetic TH/EN webhook payloads & PDPA PII test cases
├── api/
│   ├── Dockerfile                      # [DONE] Multi-stage python:3.12-slim ($PORT-aware)
│   ├── pyproject.toml                  # [DONE] Dependencies (langgraph, fastapi, psycopg3, google-genai), ruff, pytest
│   └── app/
│       ├── config.py                   # [DONE] Pydantic BaseSettings, Gemini 3.x routing & AUTH_MODE=token|demo_sandbox
│       ├── data/                       # [DONE] Container-safe benchmark_snapshot.json for standalone Docker/Render
│       ├── db.py                       # [DONE] PostgreSQL connection pool (PgBouncer-safe) & health check
│       ├── dependencies.py             # [DONE] AUTH_MODE Bearer/sandbox guard, X-Webhook-Secret guard, rate limit, repo & engine deps
│       ├── main.py                     # [DONE] FastAPI app, lifespan, CORS, GET /health, runs, approvals, dlq, webhooks & benchmark routers
│       ├── schemas/                    # [DONE] Pydantic v2 contracts & enums locked 1:1 with sql/001_schema.sql
│       ├── services/                   # [DONE] pii_redactor, repository, langgraph_engine, model_router, rate_limiter
│       └── routers/                    # [DONE] runs, approvals, dlq, webhooks, benchmark (with snapshot fallback)
├── eval/
│   ├── benchmark_cases.json            # [DONE] 24 synthetic cases (TH/EN, PII redaction, HITL triggers, routing tiers, failures)
│   ├── run_benchmark.py                # [DONE] Accuracy, PDPA leak check & 62.78% cost-routing benchmark runner
│   └── thresholds.json                 # [DONE] CI pass/fail thresholds
├── tests/
│   ├── unit/                           # [DONE] Config, schemas, /health, PDPA redactor, model router, rate limiter, auth/dlq/webhooks/snapshot (31 passed)
│   ├── integration/                    # [DONE] Live PostgreSQL 16 state persistence, idempotency, HITL, DLQ replay & n8n webhook tests (7 passed)
│   └── eval/                           # [DONE] Automated benchmark & guardrail gate tests (2 passed)
├── web/                                # [DONE] Next.js 15 App Router + TypeScript + Tailwind CSS v4 (No-Login Live Control Plane)
├── render.yaml                         # [DONE] Render Free Web Service Blueprint
├── docker-compose.yml                  # [DONE] postgres:16-alpine + api
├── .env.example                        # [DONE] Safe environment placeholders (Gemini 3.x models + AUTH_MODE)
├── .gitignore                          # [DONE] Python, Next.js, secrets, media ignores
├── AGENTS.md                           # [DONE] Project rules, architecture & roadmap
└── README.md                           # [DONE] Portfolio README with Mermaid diagram, benchmark scorecard & quickstart
```

---

## 3. Execution Roadmap (Target: 12–14 Days Including 2-Day Buffer)

- **Day 1–2 (Done):** Architecture spec & Devil's Advocate review, `sql/001_schema.sql`, `docker-compose.yml`, `api/Dockerfile`, `pyproject.toml` (including `langgraph`), `config.py`, `db.py`, `main.py` (`/health`), Pydantic v2 schemas (`1:1` SQL alignment), initial unit tests (`9 passed`, `ruff` clean, `docker compose config -q` valid).
- **Day 3–5 (Done):** PDPA PII Redaction service (`pii_redactor.py` + `data/fixtures/synthetic_payloads.json` + zero-leak unit tests), SQL-first `AgentRepository`, explicit `LangGraph` `StateGraph` engine (`langgraph_engine.py`) with PostgreSQL state-transition persistence, Human-in-the-Loop Approval Gate (`AWAITING_APPROVAL` → `APPROVED` / `REJECTED` with `FOR UPDATE` row locking), `/api/v1/runs` & `/api/v1/approvals` routers, and live Docker PostgreSQL 16 integration tests (`23 passed` total, `ruff` 0 errors).
- **Day 6–8 (Done):** Tiered Model Router (`model_router.py` via `google-genai` 3.x `interactions.create(..., store=False)` with `FAST`/`COMPLEX` routing, `429` fallback chain, and deterministic offline fallback), bounded exponential backoff retries, Dead-Letter Queue inspection/replay (`GET /api/v1/dlq`, `POST /api/v1/dlq/{job_id}/replay` with `FOR UPDATE` locking), `X-Webhook-Secret`-protected `/webhooks/n8n`, exportable `n8n/` workflow JSONs + setup guide, and unit + live PG16 integration tests (`32 passed` total [25 unit + 7 live PG16 integration], `ruff` 0 errors).
- **Day 9–10 (Done):** IP-hashed (`SHA-256`) sliding-window rate limiter (`rate_limiter.py`, `429` + `Retry-After`), `eval/benchmark_cases.json` (24 TH/EN synthetic cases), `eval/run_benchmark.py` (`62.78%` cost reduction, `0.00` PDPA leak rate, `1.00` HITL enforcement), `eval/thresholds.json`, `/api/v1/benchmark` scorecard endpoint, `tests/eval/test_benchmark_gates.py`, and `.github/workflows/ci.yml` (`38 passed` total [29 unit + 7 live PG16 integration + 2 eval gates], `ruff` 0 errors).
- **Day 11–12 (Done):** `web/` Next.js No-Login Live Demo (trigger sample workflows, inspect live PII redaction diff & state timeline, approve/reject HITL queue, inspect/replay DLQ, view Cost Routing Benchmark scorecard, `/health` cold-start banner), container-safe `api/app/data/benchmark_snapshot.json`, `render.yaml`, `.github/workflows/ci.yml` (`frontend-ci`), live cloud deployment (**Supabase** + **Render** `https://production-ai-agent-ops-api.onrender.com` + **Vercel** `https://production-ai-agent-ops.vercel.app`), live 6-flow browser E2E verification, `docs/assets/demo-60s.gif` (`1280x720`), and full English `README.md` with live links & GIF (`pytest`: 40 passed [31 unit + 7 live PG16 integration + 2 eval gates], `ruff`: 0 errors, `npx tsc --noEmit && npm run build`: exit 0, `docker compose config -q`: exit 0).
- **Day 13–14 (Pending — 2-Day Buffer):** Mobile UX polish, edge-case hardening, GitHub profile pinning, and anonymized learnings export.

---

## 4. Target Verification Commands & Gate Metrics

Once `api/` and `web/` are scaffolded:

```powershell
# Lint & Tests (inside api/)
.venv\Scripts\ruff.exe check app ../tests ../eval
.venv\Scripts\pytest.exe -v

# Docker Compose & DB check (repo root)
docker compose config -q

# Frontend check (inside web/)
npx tsc --noEmit && npm run build
```

### Target Eval & Reliability Gates (`eval/thresholds.json` — To Be Calibrated)
- **PDPA PII Redaction Leak Rate:** `= 0.00` (`100%` synthetic PII masked before LLM/logs)
- **HITL Policy Enforcement Rate:** `= 1.00` (all high-impact actions pause at `AWAITING_APPROVAL`)
- **Idempotency Duplicate Execution Rate:** `= 0.00` (duplicate keys return original run)
- **DLQ Capture & Replay Success:** `= 1.00` (exhausted retries land cleanly in DLQ and replay)
- **Tiered Model Routing Cost Reduction:** `50–70%` vs. Always-Frontier baseline with no material quality drop
