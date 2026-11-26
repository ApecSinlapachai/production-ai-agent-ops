# PROGRESS — production-ai-agent-ops

- **Last Updated:** 2026-11-26
- **Current Phase:** Shipped & Live in Production (6-Layer AI-Native SSOT Standardized)

> **Handoff Rule:** Keep this file crisp and factual. Update it immediately after every completed task (alongside `git commit`) so any new model or chat session can resume in < 10 seconds.

---

## Completed
- [x] **SQL-First Schema, PDPA Redactor & LangGraph State Machine:** PostgreSQL 16 DDL (`sql/001_schema.sql`), 1:1 Pydantic v2 schemas (`api/app/schemas/`), pre-LLM/pre-DB PDPA PII redactor (`api/app/services/pii_redactor.py`), explicit `LangGraph` `StateGraph` (`api/app/services/langgraph_engine.py`), and `FOR UPDATE`-locked HITL approval gates.
- [x] **Tiered Model Router, Reliability & `n8n` Integration:** `FAST` (`gemini-3.5-flash-lite`) / `COMPLEX` (`gemini-3.8-flash`) / `FALLBACK` (`gemini-3.1-flash-lite`) routing with deterministic fallback (`api/app/services/model_router.py`), `Idempotency-Key` deduplication, bounded exponential backoff, DLQ capture/replay (`api/app/routers/dlq.py`), and exportable `n8n/` workflows (`X-Webhook-Secret`).
- [x] **Rate Limiter, 24-Case Benchmark & GitHub Actions CI:** SHA-256 IP-hashed sliding-window rate limiter (`api/app/services/rate_limiter.py`), 24-case safety/cost benchmark (`eval/run_benchmark.py` — `62.78%` cost reduction, `0.00` PDPA leak rate, `1.00` HITL enforcement), container-safe `api/app/data/benchmark_snapshot.json`, and green `backend-ci` + `frontend-ci` (`.github/workflows/ci.yml`).
- [x] **Live Cloud Rollout, Same-Origin Proxy & Motion Demo:** Deployed to Supabase Free + Render Free + Vercel Hobby; migrated browser API calls to `/backend/*` same-origin proxy (`web/next.config.ts`) with 10×5s cold-start `/health` polling (`web/src/app/page.tsx`); added 1280×720 motion demo GIF (`docs/assets/demo-60s.gif`).
- [x] **6-Layer AI-Native SSOT Standardization:** Refactored `AGENTS.md` to concise entrypoint, added `CLAUDE.md`, `.editorconfig`, `docs/SPEC.md`, `docs/PROGRESS.md`, and `docs/adr/0001..0003`.

## In Progress / Next Up
1. Maintain `eval/benchmark_cases.json` and `docs/adr/` as new agent workflows or routing policies are added.
2. Keep live portfolio links synchronized with `https://apec-ai-portfolio.vercel.app/demos/agent-ops`.

## Blockers / Gotchas for Next Agent
- **Supabase PgBouncer Compatibility:** Always keep `prepare_threshold=None` in `psycopg_pool` (`api/app/db.py`) so prepared statements do not fail behind Supabase transaction/session poolers.
- **Public Demo Security:** Keep `AUTH_MODE=demo_sandbox` only for the public Render demo; default remains `AUTH_MODE=token`, and `/webhooks/n8n` always requires `X-Webhook-Secret`.
- **Container Benchmark Fallback:** Standalone Docker/Render builds copy only `api/`, so `/api/v1/benchmark` falls back to `api/app/data/benchmark_snapshot.json` when `eval/` is outside the container context.

## Last Verified Commands
```bash
# Inside api/
ruff check app ../tests ../eval
pytest -v
# Repo root
python eval/run_benchmark.py
docker compose config -q
# Inside web/
npx tsc --noEmit && npm run build
```
