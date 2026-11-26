# ADR-0003: Tiered Gemini 3.x Routing, Idempotent DLQ Replay & Same-Origin Proxy

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Apec Sinlapachai

---

## 1. Context
Sending every operations workflow step to a frontier LLM inflates API cost unnecessarily and exhausts Free Tier daily quotas (`429 RESOURCE_EXHAUSTED`). At the same time, real webhook integrations (`n8n`) deliver duplicate retries and encounter transient downstream failures, while direct browser-to-Render requests suffer from CORS/AdBlock blocks and Render Free cold-start errors.

## 2. Decision
> We will route low-complexity steps to **`gemini-3.5-flash-lite` (`FAST`)** and escalate only high-impact/complex reasoning to **`gemini-3.8-flash` (`COMPLEX`)** with **`gemini-3.1-flash-lite` (`FALLBACK`)** and deterministic offline fallback; enforce **`Idempotency-Key` deduplication + exponential backoff + replayable `dead_letter_jobs`**; and proxy all browser traffic through **Next.js `/backend/:path*` `rewrites()`** with bounded `/backend/health` cold-start polling.

## 3. Alternatives Considered
| Option | Pros | Cons | Why Rejected / Chosen |
| :--- | :--- | :--- | :--- |
| **Tiered Gemini 3.x + PG16 Idempotency/DLQ + Next.js `/backend/*` Proxy (Chosen)** | `62.78%` verified cost reduction (`$0.3254` → `$0.1211` / 1k runs); zero duplicate side-effects; zero direct `*.onrender.com` browser calls; `$0` hosting | Requires maintaining routing rules and container-safe `benchmark_snapshot.json` | Best cost efficiency, reliability, and live demo UX |
| **Always-Frontier Model (`gemini-3.8-flash` only)** | Single code path | `2.69x` higher cost per 1,000 runs and faster Free Tier quota exhaustion | Rejected; benchmark proves `62.78%` savings with `100%` accuracy |
| **External Queue (SQS / RabbitMQ) for Retries & DLQ** | High throughput at enterprise scale | Adds paid infrastructure and deployment complexity beyond `$0` portfolio scope | Rejected; PostgreSQL `FOR UPDATE` + `dead_letter_jobs` is sufficient and transactional |

## 4. Consequences
- **Positive:** Verified `62.78%` cost reduction in `eval/run_benchmark.py`, `0` duplicate executions under repeated `Idempotency-Key`, `100%` DLQ replay success, and `0` direct `*.onrender.com` calls from the Vercel Control Plane.
- **Negative / Trade-offs:** Vercel must set `API_PROXY_TARGET` (or `NEXT_PUBLIC_API_BASE_URL`) to point `/backend/*` at the Render API URL.
- **Reversibility:** Easy — routing lives in `api/app/services/model_router.py`, proxy in `web/next.config.ts`.
