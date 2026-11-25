"""PostgreSQL persistence layer for agent runs, transitions, HITL approvals, DLQ, and cost logs."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.db import DatabasePool
from app.schemas.agent import (
    RedactionSummary,
    RunDetailResponse,
    RunResponse,
    StateTransitionResponse,
)
from app.schemas.approval import ApprovalResponse
from app.schemas.dlq import DLQJobResponse
from app.schemas.enums import (
    ALLOWED_TRANSITIONS,
    AgentState,
    ApprovalStatus,
    DLQStatus,
    RiskLevel,
    RoutingTier,
    RunSource,
    TransitionActor,
)


class InvalidTransitionError(ValueError):
    """Raised when a state transition violates ALLOWED_TRANSITIONS."""


class IdempotencyConflictError(Exception):
    """Raised when an Idempotency-Key is reused with a different request payload."""


class NotFoundError(Exception):
    """Raised when a requested run, approval, or DLQ record does not exist."""


class ApprovalStateConflictError(Exception):
    """Raised when attempting to decide an approval that is no longer PENDING."""


class DLQStateConflictError(Exception):
    """Raised when attempting to replay a DLQ job that is no longer OPEN."""


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 digest of a canonical JSON payload."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row_to_run(row: dict[str, Any]) -> RunResponse:
    return RunResponse.model_validate(row)


def _row_to_transition(row: dict[str, Any]) -> StateTransitionResponse:
    return StateTransitionResponse.model_validate(row)


def _row_to_approval(row: dict[str, Any]) -> ApprovalResponse:
    return ApprovalResponse.model_validate(row)


def _row_to_dlq_job(row: dict[str, Any]) -> DLQJobResponse:
    return DLQJobResponse.model_validate(row)


class AgentRepository:
    """Synchronous SQL-first repository backed by psycopg3 ConnectionPool."""

    def __init__(self, db_pool: DatabasePool) -> None:
        self._db = db_pool

    def create_or_get_run(
        self,
        *,
        idempotency_key: str,
        request_payload_hash: str,
        source: RunSource,
        workflow_type: str,
        customer_ref: str | None,
        redacted_input: dict[str, Any],
        redaction_summary: RedactionSummary,
    ) -> tuple[RunDetailResponse, bool]:
        """Atomically insert a new RECEIVED run or return the existing idempotent run."""
        with self._db.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO agent_runs (
                            idempotency_key,
                            request_payload_hash,
                            source,
                            workflow_type,
                            customer_ref,
                            redacted_input,
                            redaction_summary,
                            current_state
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        RETURNING *
                        """,
                        (
                            idempotency_key,
                            request_payload_hash,
                            source.value,
                            workflow_type,
                            customer_ref,
                            Jsonb(redacted_input),
                            Jsonb(redaction_summary.model_dump()),
                            AgentState.RECEIVED.value,
                        ),
                    )
                    inserted = cur.fetchone()

                    if inserted is not None:
                        run_id: UUID = inserted["id"]
                        cur.execute(
                            """
                            INSERT INTO agent_state_transitions (
                                run_id, from_state, to_state, actor, metadata
                            )
                            VALUES (%s, %s, %s, %s, %s)
                            RETURNING *
                            """,
                            (
                                run_id,
                                None,
                                AgentState.RECEIVED.value,
                                TransitionActor.SYSTEM.value,
                                Jsonb({"idempotency_key": idempotency_key}),
                            ),
                        )
                        transition_row = cur.fetchone()
                        assert transition_row is not None
                        run = _row_to_run(inserted)
                        detail = RunDetailResponse(
                            **run.model_dump(),
                            transitions=[_row_to_transition(transition_row)],
                        )
                        return detail, False

                    # Conflict on idempotency_key: fetch existing run and verify payload hash
                    cur.execute(
                        "SELECT * FROM agent_runs WHERE idempotency_key = %s",
                        (idempotency_key,),
                    )
                    existing = cur.fetchone()
                    if existing is None:  # pragma: no cover - defensive
                        raise NotFoundError(f"Run for idempotency_key={idempotency_key} not found")

                    if existing["request_payload_hash"] != request_payload_hash:
                        raise IdempotencyConflictError(
                            "Idempotency-Key was already used with a different request payload."
                        )

                    return self._fetch_run_detail_in_conn(conn, existing["id"]), True

    def record_transition(
        self,
        *,
        run_id: UUID,
        from_state: AgentState,
        to_state: AgentState,
        actor: TransitionActor,
        model_used: str | None = None,
        routing_tier: RoutingTier | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        metadata: dict[str, Any] | None = None,
        run_updates: dict[str, Any] | None = None,
    ) -> StateTransitionResponse:
        """Validate transition against ALLOWED_TRANSITIONS and persist atomically."""
        if to_state not in ALLOWED_TRANSITIONS[from_state]:
            raise InvalidTransitionError(
                f"Transition {from_state.value} -> {to_state.value} is not allowed."
            )

        with self._db.get_connection() as conn:
            with conn.transaction():
                return self._record_transition_in_conn(
                    conn,
                    run_id=run_id,
                    from_state=from_state,
                    to_state=to_state,
                    actor=actor,
                    model_used=model_used,
                    routing_tier=routing_tier,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    metadata=metadata,
                    run_updates=run_updates,
                )

    def _record_transition_in_conn(
        self,
        conn: Connection[Any],
        *,
        run_id: UUID,
        from_state: AgentState,
        to_state: AgentState,
        actor: TransitionActor,
        model_used: str | None = None,
        routing_tier: RoutingTier | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        metadata: dict[str, Any] | None = None,
        run_updates: dict[str, Any] | None = None,
    ) -> StateTransitionResponse:
        allowed_update_cols = {
            "detected_intent",
            "routing_tier",
            "confidence",
            "requires_hitl",
            "draft_response",
            "proposed_action",
            "execution_result",
            "attempt_count",
            "error_message",
        }
        jsonb_cols = {"proposed_action", "execution_result"}

        set_clauses = [
            "current_state = %s",
            "total_input_tokens = total_input_tokens + %s",
            "total_output_tokens = total_output_tokens + %s",
            "total_cost_usd = total_cost_usd + %s",
            "total_latency_ms = total_latency_ms + %s",
        ]
        params: list[Any] = [
            to_state.value,
            input_tokens,
            output_tokens,
            cost_usd,
            latency_ms,
        ]

        if run_updates:
            for col, val in run_updates.items():
                if col not in allowed_update_cols:
                    raise ValueError(f"Unsupported run update column: {col}")
                set_clauses.append(f"{col} = %s")
                if col in jsonb_cols and val is not None:
                    params.append(Jsonb(val))
                elif isinstance(val, RoutingTier):
                    params.append(val.value)
                else:
                    params.append(val)

        params.append(run_id)
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE agent_runs SET {', '.join(set_clauses)} WHERE id = %s",
                params,
            )
            cur.execute(
                """
                INSERT INTO agent_state_transitions (
                    run_id,
                    from_state,
                    to_state,
                    actor,
                    model_used,
                    routing_tier,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    latency_ms,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    run_id,
                    from_state.value,
                    to_state.value,
                    actor.value,
                    model_used,
                    routing_tier.value if routing_tier is not None else None,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    latency_ms,
                    Jsonb(metadata or {}),
                ),
            )
            row = cur.fetchone()
            assert row is not None
            return _row_to_transition(row)

    def log_llm_cost(
        self,
        *,
        run_id: UUID,
        step_name: str,
        routing_tier: RoutingTier,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
        latency_ms: int,
        is_fallback: bool = False,
    ) -> None:
        """Persist a per-step LLM cost audit row into `llm_cost_logs`."""
        with self._db.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO llm_cost_logs (
                            run_id,
                            step_name,
                            routing_tier,
                            model_name,
                            input_tokens,
                            output_tokens,
                            estimated_cost_usd,
                            latency_ms,
                            is_fallback
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            run_id,
                            step_name,
                            routing_tier.value,
                            model_name,
                            input_tokens,
                            output_tokens,
                            estimated_cost_usd,
                            latency_ms,
                            is_fallback,
                        ),
                    )

    def create_hitl_approval(
        self,
        *,
        run_id: UUID,
        action_type: str,
        action_preview: dict[str, Any],
        risk_level: RiskLevel,
    ) -> ApprovalResponse:
        """Insert a PENDING Human-in-the-Loop approval gate record."""
        with self._db.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO hitl_approvals (
                            run_id, action_type, action_preview, risk_level, status
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            run_id,
                            action_type,
                            Jsonb(action_preview),
                            risk_level.value,
                            ApprovalStatus.PENDING.value,
                        ),
                    )
                    row = cur.fetchone()
                    assert row is not None
                    return _row_to_approval(row)

    def create_dlq_job(
        self,
        *,
        run_id: UUID,
        failed_state: AgentState,
        error_code: str,
        error_message: str,
        attempts_made: int,
        payload_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert an OPEN dead-letter job with PII-redacted payload snapshot."""
        with self._db.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO dead_letter_jobs (
                            run_id,
                            failed_state,
                            error_code,
                            error_message,
                            attempts_made,
                            payload_snapshot,
                            status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'OPEN')
                        RETURNING *
                        """,
                        (
                            run_id,
                            failed_state.value,
                            error_code,
                            error_message,
                            attempts_made,
                            Jsonb(payload_snapshot),
                        ),
                    )
                    row = cur.fetchone()
                    assert row is not None
                    return dict(row)

    def decide_approval(
        self,
        *,
        approval_id: UUID,
        decision: ApprovalStatus,
        decided_by: str,
        decision_reason: str | None,
    ) -> tuple[ApprovalResponse, UUID]:
        """Lock approval row with FOR UPDATE, record decision, and advance run state atomically."""
        if decision not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise ValueError(f"Unsupported approval decision: {decision}")

        target_state = (
            AgentState.APPROVED if decision == ApprovalStatus.APPROVED else AgentState.REJECTED
        )

        with self._db.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM hitl_approvals WHERE id = %s FOR UPDATE",
                        (approval_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise NotFoundError(f"Approval {approval_id} not found.")

                    if row["status"] != ApprovalStatus.PENDING.value:
                        raise ApprovalStateConflictError(
                            f"Approval {approval_id} is already {row['status']}."
                        )

                    cur.execute(
                        """
                        UPDATE hitl_approvals
                        SET status = %s,
                            decided_by = %s,
                            decision_reason = %s,
                            decided_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (decision.value, decided_by, decision_reason, approval_id),
                    )
                    updated_approval = cur.fetchone()
                    assert updated_approval is not None

                run_id: UUID = updated_approval["run_id"]
                self._record_transition_in_conn(
                    conn,
                    run_id=run_id,
                    from_state=AgentState.AWAITING_APPROVAL,
                    to_state=target_state,
                    actor=TransitionActor.HUMAN,
                    metadata={
                        "approval_id": str(approval_id),
                        "decided_by": decided_by,
                        "decision_reason": decision_reason,
                    },
                )
                return _row_to_approval(updated_approval), run_id

    def _fetch_run_detail_in_conn(self, conn: Connection[Any], run_id: UUID) -> RunDetailResponse:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_runs WHERE id = %s", (run_id,))
            run_row = cur.fetchone()
            if run_row is None:
                raise NotFoundError(f"Run {run_id} not found.")

            cur.execute(
                """
                SELECT * FROM agent_state_transitions
                WHERE run_id = %s
                ORDER BY id ASC
                """,
                (run_id,),
            )
            transition_rows = cur.fetchall()

        run = _row_to_run(run_row)
        return RunDetailResponse(
            **run.model_dump(),
            transitions=[_row_to_transition(t) for t in transition_rows],
        )

    def get_run_detail(self, run_id: UUID) -> RunDetailResponse:
        """Fetch a run and its ordered state-transition audit trail."""
        with self._db.get_connection() as conn:
            return self._fetch_run_detail_in_conn(conn, run_id)

    def list_runs(
        self,
        *,
        state: AgentState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunResponse]:
        """List agent runs ordered by newest first, optionally filtered by current_state."""
        with self._db.get_connection() as conn:
            with conn.cursor() as cur:
                if state is not None:
                    cur.execute(
                        """
                        SELECT * FROM agent_runs
                        WHERE current_state = %s
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (state.value, limit, offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM agent_runs
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (limit, offset),
                    )
                return [_row_to_run(row) for row in cur.fetchall()]

    def get_approval(self, approval_id: UUID) -> ApprovalResponse:
        """Fetch a single HITL approval record."""
        with self._db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM hitl_approvals WHERE id = %s", (approval_id,))
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError(f"Approval {approval_id} not found.")
                return _row_to_approval(row)

    def list_approvals(
        self,
        *,
        status: ApprovalStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ApprovalResponse]:
        """List HITL approval records ordered oldest-first for queue processing."""
        with self._db.get_connection() as conn:
            with conn.cursor() as cur:
                if status is not None:
                    cur.execute(
                        """
                        SELECT * FROM hitl_approvals
                        WHERE status = %s
                        ORDER BY created_at ASC
                        LIMIT %s OFFSET %s
                        """,
                        (status.value, limit, offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM hitl_approvals
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (limit, offset),
                    )
                return [_row_to_approval(row) for row in cur.fetchall()]

    def list_dlq_jobs(
        self,
        *,
        status: DLQStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DLQJobResponse]:
        """List Dead-Letter Queue jobs, ordered oldest-first when filtering OPEN."""
        with self._db.get_connection() as conn:
            with conn.cursor() as cur:
                if status is not None:
                    order_dir = "ASC" if status == DLQStatus.OPEN else "DESC"
                    cur.execute(
                        f"""
                        SELECT * FROM dead_letter_jobs
                        WHERE status = %s
                        ORDER BY created_at {order_dir}
                        LIMIT %s OFFSET %s
                        """,
                        (status.value, limit, offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM dead_letter_jobs
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (limit, offset),
                    )
                return [_row_to_dlq_job(row) for row in cur.fetchall()]

    def get_dlq_job(self, job_id: UUID) -> DLQJobResponse:
        """Fetch a single Dead-Letter Queue job by ID."""
        with self._db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dead_letter_jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                if row is None:
                    raise NotFoundError(f"DLQ job {job_id} not found.")
                return _row_to_dlq_job(row)

    def claim_dlq_job_for_replay(self, job_id: UUID) -> tuple[DLQJobResponse, RunDetailResponse]:
        """Lock an OPEN DLQ job with FOR UPDATE and transition it to REPLAYING."""
        with self._db.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM dead_letter_jobs WHERE id = %s FOR UPDATE",
                        (job_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise NotFoundError(f"DLQ job {job_id} not found.")

                    if row["status"] != DLQStatus.OPEN.value:
                        raise DLQStateConflictError(
                            f"DLQ job {job_id} is {row['status']} and cannot be replayed."
                        )

                    cur.execute(
                        """
                        UPDATE dead_letter_jobs
                        SET status = %s,
                            replay_count = replay_count + 1,
                            last_replayed_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (DLQStatus.REPLAYING.value, job_id),
                    )
                    updated = cur.fetchone()
                    assert updated is not None

                run_detail = self._fetch_run_detail_in_conn(conn, updated["run_id"])
                return _row_to_dlq_job(updated), run_detail

    def mark_dlq_job_status(
        self,
        job_id: UUID,
        *,
        status: DLQStatus,
        error_message: str | None = None,
    ) -> DLQJobResponse:
        """Finalize a DLQ job status after replay (REPLAYED or returned to OPEN)."""
        with self._db.get_connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    if error_message is not None:
                        cur.execute(
                            """
                            UPDATE dead_letter_jobs
                            SET status = %s,
                                error_message = %s
                            WHERE id = %s
                            RETURNING *
                            """,
                            (status.value, error_message, job_id),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE dead_letter_jobs
                            SET status = %s
                            WHERE id = %s
                            RETURNING *
                            """,
                            (status.value, job_id),
                        )
                    row = cur.fetchone()
                    if row is None:
                        raise NotFoundError(f"DLQ job {job_id} not found.")
                    return _row_to_dlq_job(row)
