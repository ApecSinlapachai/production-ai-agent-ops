# n8n Integration Workflows

These exportable workflow templates connect **n8n** to the Production AI Agent Ops FastAPI backend with zero hardcoded secrets, automatic HTTP retries (`maxTries: 3`), and error-branch webhook responses (`502`).

## Workflows

1. **`01_webhook_intake_and_agent_dispatch.json`**
   - **Trigger:** `POST /webhook/ops-intake`
   - **Action:** Dispatches the event to `POST /webhooks/n8n` with an `Idempotency-Key` header and `X-Webhook-Secret` credential.
   - **Branching:** Returns `202` (`pending_hitl_approval`) when `requires_hitl === true`, `200` when auto-completed (or dead-lettered), and `502` on upstream API failure.

2. **`02_hitl_approval_callback_and_notify.json`**
   - **Trigger:** `POST /webhook/ops-hitl-decision`
   - **Action:** Forwards `APPROVED` / `REJECTED` reviewer decisions to `POST /api/v1/approvals/{approval_id}/decision`.
   - **Branching:** Returns `200` with execution outcome (`approved_and_executed` vs `rejected_no_action`), or `502` on upstream API failure.

## Setup in n8n

1. **Create Credentials (no secrets in workflow JSON):**
   - For Workflow 01, create a credential of type **`httpHeaderAuth`** (Header Auth) with Header Name `X-Webhook-Secret` and your `N8N_WEBHOOK_SECRET` value, then bind it to **Dispatch to Agent Ops API**.
   - For Workflow 02, create a credential of type **`httpBearerAuth`** (Bearer Auth) with your `ADMIN_API_TOKEN` value (optional if `AUTH_MODE=demo_sandbox`), then bind it to **Submit HITL Decision to Agent API**.
2. **Optional Variable:**
   - Set n8n variable `AGENT_OPS_API_URL` (defaults to `http://localhost:8000`; use `http://host.docker.internal:8000` when n8n runs inside Docker on Windows/macOS).
3. **Import JSON Files:**
   - In n8n UI: **Workflows -> Import from File** and select each `.json` file in `n8n/`.

## Synthetic Verification Examples

```bash
# 1. Trigger intake via n8n webhook (synthetic test payload, zero real PII)
curl -X POST http://localhost:5678/webhook/ops-intake \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: req-demo-2026-0001" \
  -d '{
    "event_id": "EVT-2026-0001",
    "customer_ref": "CUST-DEMO-03",
    "workflow_type": "customer_ops",
    "message": "Customer Somchai Test requests refund for ORD-2026-5501, phone 081-234-5678"
  }'

# 2. Submit HITL approval decision via n8n callback
curl -X POST http://localhost:5678/webhook/ops-hitl-decision \
  -H "Content-Type: application/json" \
  -d '{
    "approval_id": "00000000-0000-0000-0000-000000000000",
    "decision": "APPROVED",
    "decided_by": "ops.reviewer@demo",
    "decision_reason": "Verified synthetic order ORD-2026-5501"
  }'
```
