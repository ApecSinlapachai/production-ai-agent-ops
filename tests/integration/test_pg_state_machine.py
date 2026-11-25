"""Live PostgreSQL 16 integration tests for state persistence, PDPA zero-leak, HITL, and DLQ."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.pii_redactor import find_leaked_pii

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "001_schema.sql"
DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:5432/agent_ops"


def _db_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DB_URL)


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    """Ensure live PostgreSQL 16 is reachable and apply idempotent DDL."""
    dsn = _db_url()
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.commit()
    except psycopg.OperationalError as exc:
        pytest.skip(f"Live PostgreSQL 16 not reachable at {dsn}: {exc}")
    return dsn


@pytest.fixture()
def clean_client(pg_dsn: str) -> Iterator[TestClient]:
    """Truncate tables and yield a FastAPI TestClient wired to live PostgreSQL 16."""
    with psycopg.connect(pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE llm_cost_logs, dead_letter_jobs, hitl_approvals, "
                "agent_state_transitions, agent_runs RESTART IDENTITY CASCADE"
            )
        conn.commit()

    settings = Settings(
        _env_file=None,
        database_url=pg_dsn,
        auth_mode="demo_sandbox",
        n8n_webhook_secret="integration-n8n-secret",
        max_retry_attempts=3,
        retry_base_delay_seconds=0.0,
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        yield client


def test_low_risk_run_completes_with_zero_raw_pii_in_db(
    clean_client: TestClient,
    pg_dsn: str,
) -> None:
    """Low-risk inquiry redacts PII at boundary, routes FAST, and persists full transitions."""
    raw_phone = "089-000-1122"
    raw_email = "somchai.demo@example.com"
    payload = {
        "message": (
            f"สวัสดีครับ เช็คสถานะพัสดุ ORD-2026-9920 ให้หน่อยครับ "
            f"ติดต่อกลับ {raw_phone} หรือ {raw_email}"
        ),
        "customer_ref": "CUST-DEMO-02",
        "source": "n8n",
    }

    resp = clean_client.post(
        "/api/v1/runs",
        json=payload,
        headers={"Idempotency-Key": "idem-low-risk-001"},
    )
    assert resp.status_code == 201
    assert resp.headers["X-Idempotency-Replayed"] == "false"

    data = resp.json()
    assert data["current_state"] == "COMPLETED"
    assert data["routing_tier"] == "FAST"
    assert data["requires_hitl"] is False
    assert data["redaction_summary"]["entity_counts"] == {"THAI_PHONE": 1, "EMAIL": 1}

    states = [t["to_state"] for t in data["transitions"]]
    assert states == [
        "RECEIVED",
        "PII_REDACTED",
        "INTENT_ROUTED",
        "CONTEXT_FETCHED",
        "DRAFT_GENERATED",
        "EXECUTING_ACTION",
        "COMPLETED",
    ]

    # Verify zero raw PII exists anywhere in persisted DB rows
    with psycopg.connect(pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT redacted_input::text, redaction_summary::text FROM agent_runs")
            row = cur.fetchone()
            assert row is not None
            db_blob = " ".join(row)
            assert find_leaked_pii(db_blob, [raw_phone, raw_email]) == []

            cur.execute("SELECT COUNT(*) FROM llm_cost_logs WHERE run_id = %s", (data["id"],))
            cost_count = cur.fetchone()
            assert cost_count is not None and cost_count[0] == 2


def test_idempotency_replay_and_payload_hash_conflict(clean_client: TestClient) -> None:
    """Duplicate Idempotency-Key replays existing run; mismatched payload returns 409."""
    payload = {
        "message": "Check shipping status for ORD-2026-8841",
        "customer_ref": "CUST-DEMO-01",
        "source": "api",
    }
    first = clean_client.post(
        "/api/v1/runs",
        json=payload,
        headers={"Idempotency-Key": "idem-dup-001"},
    )
    assert first.status_code == 201
    assert first.headers["X-Idempotency-Replayed"] == "false"

    second = clean_client.post(
        "/api/v1/runs",
        json=payload,
        headers={"Idempotency-Key": "idem-dup-001"},
    )
    assert second.status_code == 200
    assert second.headers["X-Idempotency-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]

    conflict = clean_client.post(
        "/api/v1/runs",
        json={**payload, "message": "Different payload under same key"},
        headers={"Idempotency-Key": "idem-dup-001"},
    )
    assert conflict.status_code == 409


def test_hitl_approval_gate_approve_and_reject_double_decision(
    clean_client: TestClient,
    pg_dsn: str,
) -> None:
    """High-impact refund pauses at AWAITING_APPROVAL, resumes on APPROVED, blocks 2nd decision."""
    raw_pii = ["สมชาย ทดสอบ", "1-1099-00000-01-9", "123-4-56789-0", "081-234-5678"]
    payload = {
        "message": (
            "คุณสมชาย ทดสอบ ขอคืนเงิน 4,500 บาท สำหรับคำสั่งซื้อ ORD-2026-5501 "
            "เลขบัตรประชาชน 1-1099-00000-01-9 โอนเข้าบัญชี 123-4-56789-0 โทร 081-234-5678"
        ),
        "customer_ref": "CUST-DEMO-03",
        "source": "api",
    }
    run_resp = clean_client.post(
        "/api/v1/runs",
        json=payload,
        headers={"Idempotency-Key": "idem-hitl-approve-001"},
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    assert run_data["current_state"] == "AWAITING_APPROVAL"
    assert run_data["requires_hitl"] is True
    assert run_data["routing_tier"] == "COMPLEX"
    assert find_leaked_pii(str(run_data), raw_pii) == []

    # List PENDING approvals
    approvals_resp = clean_client.get("/api/v1/approvals?status=PENDING")
    assert approvals_resp.status_code == 200
    approvals = approvals_resp.json()
    assert len(approvals) == 1
    approval_id = approvals[0]["id"]
    assert approvals[0]["run_id"] == run_data["id"]
    assert approvals[0]["risk_level"] == "HIGH"

    # Approve and verify execution resumes to COMPLETED
    decision_resp = clean_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json={
            "decision": "APPROVED",
            "decided_by": "ops.reviewer@demo",
            "decision_reason": "Verified order and refund policy.",
        },
    )
    assert decision_resp.status_code == 200
    decided = decision_resp.json()
    assert decided["approval"]["status"] == "APPROVED"
    assert decided["run"]["current_state"] == "COMPLETED"
    assert decided["run"]["execution_result"]["status"] == "executed"

    states = [t["to_state"] for t in decided["run"]["transitions"]]
    assert states[-4:] == ["AWAITING_APPROVAL", "APPROVED", "EXECUTING_ACTION", "COMPLETED"]

    # Second decision attempt must fail with 409 Conflict (FOR UPDATE idempotency)
    duplicate_decision = clean_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json={"decision": "REJECTED", "decided_by": "ops.reviewer@demo"},
    )
    assert duplicate_decision.status_code == 409

    # Confirm DB has zero raw PII in hitl_approvals too
    with psycopg.connect(pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT action_preview::text FROM hitl_approvals WHERE id = %s",
                (approval_id,),
            )
            preview_row = cur.fetchone()
            assert preview_row is not None
            assert find_leaked_pii(preview_row[0], raw_pii) == []


def test_hitl_approval_gate_rejection_terminates_without_execution(
    clean_client: TestClient,
) -> None:
    """Rejecting a PENDING HITL gate transitions run to REJECTED with no side effects."""
    run_resp = clean_client.post(
        "/api/v1/runs",
        json={
            "message": (
                "Customer: Jane Demo wants to cancel subscription and request billing credit."
            ),
            "customer_ref": "CUST-DEMO-04",
            "source": "demo",
        },
        headers={"Idempotency-Key": "idem-hitl-reject-001"},
    )
    assert run_resp.status_code == 201
    assert run_resp.json()["current_state"] == "AWAITING_APPROVAL"

    approval_id = clean_client.get("/api/v1/approvals?status=PENDING").json()[0]["id"]
    reject_resp = clean_client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json={
            "decision": "REJECTED",
            "decided_by": "finance.lead@demo",
            "decision_reason": "Outside refund window.",
        },
    )
    assert reject_resp.status_code == 200
    body = reject_resp.json()
    assert body["approval"]["status"] == "REJECTED"
    assert body["run"]["current_state"] == "REJECTED"
    assert body["run"]["execution_result"] is None


def test_simulated_downstream_failure_exhausts_retries_into_dlq(
    clean_client: TestClient,
    pg_dsn: str,
) -> None:
    """Downstream failure retries max_retry_attempts times and lands cleanly in DLQ."""
    resp = clean_client.post(
        "/api/v1/runs",
        json={
            "message": "Please check invoice status for INV-2026-3310 and notify ops@example.com.",
            "customer_ref": "CUST-DEMO-05",
            "source": "demo",
            "simulate_action_failure": True,
        },
        headers={"Idempotency-Key": "idem-dlq-001"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["current_state"] == "DLQ"
    assert data["attempt_count"] == 3
    assert data["error_message"] is not None

    with psycopg.connect(pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, attempts_made, payload_snapshot::text "
                "FROM dead_letter_jobs WHERE run_id = %s",
                (data["id"],),
            )
            dlq_row = cur.fetchone()
            assert dlq_row is not None
            assert dlq_row[0] == "OPEN"
            assert dlq_row[1] == 3
            assert find_leaked_pii(dlq_row[2], ["ops@example.com"]) == []


def test_dlq_list_and_replay_recovers_run_to_completed(clean_client: TestClient) -> None:
    """Listing OPEN DLQ jobs and replaying recovers the run to COMPLETED with dlq_replay actor."""
    run_resp = clean_client.post(
        "/api/v1/runs",
        json={
            "message": "Check invoice status for INV-2026-7712",
            "customer_ref": "CUST-DEMO-06",
            "source": "demo",
            "simulate_action_failure": True,
        },
        headers={"Idempotency-Key": "idem-dlq-replay-001"},
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]
    assert run_resp.json()["current_state"] == "DLQ"

    dlq_list = clean_client.get("/api/v1/dlq?status=OPEN")
    assert dlq_list.status_code == 200
    jobs = dlq_list.json()
    assert len(jobs) == 1
    job_id = jobs[0]["id"]
    assert jobs[0]["run_id"] == run_id

    replay_resp = clean_client.post(f"/api/v1/dlq/{job_id}/replay")
    assert replay_resp.status_code == 200
    replay_data = replay_resp.json()
    assert replay_data["run_state"] == "COMPLETED"
    assert replay_data["job"]["status"] == "REPLAYED"
    assert replay_data["job"]["replay_count"] == 1

    run_detail = clean_client.get(f"/api/v1/runs/{run_id}").json()
    assert run_detail["current_state"] == "COMPLETED"
    assert run_detail["transitions"][-2]["from_state"] == "DLQ"
    assert run_detail["transitions"][-2]["to_state"] == "EXECUTING_ACTION"
    assert run_detail["transitions"][-2]["actor"] == "dlq_replay"
    assert run_detail["transitions"][-1]["to_state"] == "COMPLETED"
    assert run_detail["transitions"][-1]["actor"] == "dlq_replay"

    # Replaying a REPLAYED job again must fail with 409 Conflict
    second_replay = clean_client.post(f"/api/v1/dlq/{job_id}/replay")
    assert second_replay.status_code == 409


def test_n8n_webhook_enforces_secret_and_idempotent_event_id(
    clean_client: TestClient,
    pg_dsn: str,
) -> None:
    """/webhooks/n8n requires X-Webhook-Secret, redacts PII, and deduplicates by event_id."""
    raw_phone = "082-333-4455"
    payload = {
        "event_id": "EVT-2026-9001",
        "customer_ref": "CUST-DEMO-07",
        "workflow_type": "customer_ops",
        "message": f"Check shipping status ORD-2026-9001 and call {raw_phone}",
    }

    unauthorized = clean_client.post("/webhooks/n8n", json=payload)
    assert unauthorized.status_code == 401

    first = clean_client.post(
        "/webhooks/n8n",
        json=payload,
        headers={"X-Webhook-Secret": "integration-n8n-secret"},
    )
    assert first.status_code == 201
    assert first.headers["X-Idempotency-Replayed"] == "false"
    body = first.json()
    assert body["source"] == "n8n"
    assert body["current_state"] == "COMPLETED"
    assert body["redaction_summary"]["entity_counts"] == {"THAI_PHONE": 1}
    assert find_leaked_pii(str(body), [raw_phone]) == []

    duplicate = clean_client.post(
        "/webhooks/n8n",
        json=payload,
        headers={"X-Webhook-Secret": "integration-n8n-secret"},
    )
    assert duplicate.status_code == 200
    assert duplicate.headers["X-Idempotency-Replayed"] == "true"
    assert duplicate.json()["id"] == body["id"]

    with psycopg.connect(pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT idempotency_key FROM agent_runs WHERE id = %s", (body["id"],))
            row = cur.fetchone()
            assert row is not None and row[0] == "n8n-EVT-2026-9001"
