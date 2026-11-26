# ADR-0002: Pre-LLM/Pre-DB PDPA PII Redaction, Mandatory HITL Gate & Auth Modes

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Apec Sinlapachai

---

## 1. Context
Operations tickets in Thailand frequently contain Thai National IDs, phone numbers, emails, bank accounts, and personal names governed by Thailand's PDPA. Sending raw payloads to external LLM APIs or storing them in application logs creates compliance risk. Furthermore, high-impact actions (refunds, credits, cancellations) must never execute autonomously, while the public portfolio demo must remain usable without leaking API secrets to the browser.

## 2. Decision
> We will run a **deterministic PDPA PII Redaction layer (`pii_redactor.py`) at the API boundary before any LLM call, log line, or DB insert** (persisting only `redacted_input` and `redaction_summary`), pause all high-impact or low-confidence runs at **`AWAITING_APPROVAL`**, and support **`AUTH_MODE=token|demo_sandbox`** (default `token`, with `/webhooks/n8n` always protected by `X-Webhook-Secret`).

## 3. Alternatives Considered
| Option | Pros | Cons | Why Rejected / Chosen |
| :--- | :--- | :--- | :--- |
| **Boundary Deterministic Redactor + Mandatory HITL + Dual `AUTH_MODE` (Chosen)** | `0.00` PDPA leak rate; zero extra LLM latency/cost; zero secrets in browser; safe public demo | Regex/heuristic patterns must be tested against synthetic TH/EN edge cases | Best compliance guarantee and zero-cost reliability |
| **LLM-Based PII Redaction** | Handles fuzzy phrasing | Sends raw PII to an external LLM in order to redact it — defeats PDPA boundary | Rejected; violates zero-raw-PII-to-LLM rule |
| **Hardcoded Demo Bearer Token in Frontend JS** | Simple auth check | Leaks secret into public client bundle | Rejected; `AUTH_MODE=demo_sandbox` + IP rate limiting is safer |

## 4. Consequences
- **Positive:** Verified `0.00` PDPA leak rate across 32 synthetic PII entities and `1.00` HITL enforcement across all 24 benchmark cases; visitors can inspect the live redaction diff and approve/reject gates safely.
- **Negative / Trade-offs:** Downstream systems requiring unmasked identifiers must resolve synthetic reference IDs inside an authorized internal boundary.
- **Reversibility:** Easy — redaction rules live in `api/app/services/pii_redactor.py` and auth guards in `api/app/dependencies.py`.
