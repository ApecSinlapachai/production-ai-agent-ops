# Production AI Agent Ops

> **Status:** Core Engine, HITL, Tiered Model Routing, DLQ Replay & n8n Webhooks Complete — PostgreSQL 16 / Supabase schema (`sql/001_schema.sql`), PDPA PII redaction layer, explicit `LangGraph` `StateGraph` engine with SQL-first persistence, HITL approval gates (`FOR UPDATE` row locking), `TieredModelRouter` (`FAST` vs `COMPLEX` + `429` fallback chain), Dead-Letter Queue replay (`/api/v1/dlq`), `/webhooks/n8n`, exportable `n8n/` workflows, and verified checks (`ruff`: 0 errors, `pytest`: 32 passed [25 unit + 7 live PG16 integration], `docker compose config -q`: exit 0).

A production-minded **State-Machine AI Operations Agent** designed to demonstrate safe, cost-controlled, and auditable agentic automation for real-world business workflows.

## Core Capabilities (Planned)

- **Explicit State-Machine Agent (`LangGraph` / Typed State Machine):** Deterministic transitions with full PostgreSQL audit trail (`RECEIVED` → `PII_REDACTED` → `INTENT_ROUTED` → `DRAFT_GENERATED` → `AWAITING_APPROVAL` → `COMPLETED` / `DLQ`).
- **Human-in-the-Loop (HITL) Approval Gate:** High-impact actions pause for explicit human approval or rejection before external execution.
- **PDPA PII Redaction:** Deterministic pre-LLM and pre-log masking for Thai/English sensitive identifiers (National IDs, phone numbers, emails, account numbers).
- **Production Reliability:** `Idempotency-Key` deduplication, bounded Retry with Exponential Backoff, and a Dead-Letter Queue (DLQ) with replay support.
- **Tiered Model Routing Cost Benchmark:** Routes simple classification/extraction to a fast low-cost model and reserves complex models for edge cases, targeting a **50–70% LLM cost reduction**.
- **`n8n` Workflow Integration:** Exportable `n8n` JSON workflows connecting webhooks, the Agent API, and approval callbacks.
- **No-Login Live Demo:** Next.js frontend deployed on Vercel with interactive sample scenarios, PII redaction inspector, HITL approval queue, DLQ viewer, and Cost Benchmark scorecard.

## Target Tech Stack

- **Backend:** Python 3.12+, FastAPI, Pydantic v2, LangGraph / State Machine, `psycopg3`
- **Database:** PostgreSQL 16 (Docker locally / Supabase Free Tier in production)
- **Workflow Orchestration:** `n8n` (exportable JSON)
- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS (Vercel)
- **Quality & Ops:** `pytest`, `ruff`, GitHub Actions CI, Docker / `docker-compose`

## Project Governance

See [`AGENTS.md`](./AGENTS.md) for engineering guardrails, planned repository layout, roadmap, and verification gates.
