"""Explicit LangGraph StateGraph engine with SQL-first transition persistence and HITL gates."""

from __future__ import annotations

import random
import re
import time
from typing import Any, Literal, TypedDict
from uuid import UUID

from langgraph.graph import END, StateGraph

from app.config import Settings
from app.schemas.agent import RunCreateRequest, RunDetailResponse
from app.schemas.approval import ApprovalDecisionResponse
from app.schemas.dlq import DLQReplayResponse
from app.schemas.enums import (
    AgentState,
    ApprovalStatus,
    DLQStatus,
    RiskLevel,
    RoutingTier,
    TransitionActor,
)
from app.services.model_router import TieredModelRouter
from app.services.pii_redactor import redact_payload
from app.services.repository import AgentRepository, compute_payload_hash

# High-impact actions that MUST pause at AWAITING_APPROVAL under HITL policy
HIGH_IMPACT_INTENTS: frozenset[str] = frozenset(
    {
        "refund_request",
        "billing_credit",
        "account_cancellation",
        "crm_billing_update",
    }
)

_ORDER_REF_RE = re.compile(r"\b(?:ORD|INV|REQ)-\d{4}-\d{3,6}\b")


class AgentGraphState(TypedDict, total=False):
    """Typed state passed across LangGraph StateGraph nodes."""

    run_id: str
    redacted_message: str
    redaction_summary: dict[str, Any]
    customer_ref: str | None
    workflow_type: str
    simulate_action_failure: bool
    transition_actor: str
    is_dlq_replay: bool
    current_state: str
    detected_intent: str
    routing_tier: str
    confidence: float
    requires_hitl: bool
    risk_level: str
    context: dict[str, Any]
    draft_response: str
    proposed_action: dict[str, Any]
    execution_result: dict[str, Any] | None


def compute_backoff_seconds(attempt: int, base_delay: float, max_delay: float = 30.0) -> float:
    """Compute bounded exponential backoff with jitter for transient execution retries."""
    if base_delay <= 0.0:
        return 0.0
    raw = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))
    jitter = raw * random.uniform(0.0, 0.25)
    return round(min(max_delay, raw + jitter), 3)


def _classify_intent(redacted_message: str) -> tuple[str, RoutingTier, float, RiskLevel]:
    """Classify customer ops intent, routing tier, confidence, and HITL risk level."""
    lower = redacted_message.lower()

    refund_keywords = ("refund", "คืนเงิน", "chargeback", "reimburse")
    cancel_keywords = ("cancel subscription", "cancel account", "ยกเลิกสมาชิก", "ปิดบัญชี")
    credit_keywords = ("billing credit", "credit adjustment", "เครดิต", "dispute", "ร้องเรียน")
    status_keywords = ("status", "tracking", "shipping", "พัสดุ", "สถานะ", "invoice", "order")

    if any(k in lower for k in refund_keywords):
        return "refund_request", RoutingTier.COMPLEX, 0.92, RiskLevel.HIGH
    if any(k in lower for k in cancel_keywords):
        return "account_cancellation", RoutingTier.COMPLEX, 0.90, RiskLevel.HIGH
    if any(k in lower for k in credit_keywords):
        return "billing_credit", RoutingTier.COMPLEX, 0.86, RiskLevel.HIGH
    if any(k in lower for k in status_keywords):
        return "order_status_inquiry", RoutingTier.FAST, 0.94, RiskLevel.LOW

    # Ambiguous request: escalate to COMPLEX with lower confidence so HITL gate can inspect
    return "general_ops_inquiry", RoutingTier.COMPLEX, 0.72, RiskLevel.MEDIUM


def _build_proposed_action(
    intent: str,
    redacted_message: str,
    customer_ref: str | None,
    context: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Generate a structured draft response and proposed downstream action."""
    order_ref = context.get("order_ref", "ORD-UNKNOWN")
    customer_label = customer_ref or "CUST-ANONYMOUS"

    if intent == "refund_request":
        draft = (
            f"We have received your refund request for {order_ref}. "
            "Your sensitive details were masked under PDPA policy, and a specialist "
            "is reviewing the refund for approval."
        )
        action = {
            "action_type": "issue_refund",
            "customer_ref": customer_label,
            "order_ref": order_ref,
            "requires_human_approval": True,
            "summary": f"Issue refund for {order_ref} ({customer_label})",
        }
        return draft, action

    if intent == "account_cancellation":
        draft = (
            f"We have logged your cancellation request for account {customer_label}. "
            "An operations reviewer will confirm the cancellation and any applicable credit."
        )
        action = {
            "action_type": "cancel_subscription",
            "customer_ref": customer_label,
            "order_ref": order_ref,
            "requires_human_approval": True,
            "summary": f"Cancel subscription for {customer_label}",
        }
        return draft, action

    if intent == "billing_credit":
        draft = (
            f"We have received your billing adjustment request for {customer_label}. "
            "This request has been queued for finance approval."
        )
        action = {
            "action_type": "issue_credit",
            "customer_ref": customer_label,
            "order_ref": order_ref,
            "requires_human_approval": True,
            "summary": f"Apply billing credit for {customer_label}",
        }
        return draft, action

    if intent == "order_status_inquiry":
        draft = (
            f"Order {order_ref} is currently in transit and scheduled for delivery within "
            "1-2 business days. No further action is required."
        )
        action = {
            "action_type": "send_status_reply",
            "customer_ref": customer_label,
            "order_ref": order_ref,
            "requires_human_approval": False,
            "summary": f"Send automated tracking status reply for {order_ref}",
        }
        return draft, action

    draft = (
        f"Thank you for contacting operations regarding {customer_label}. "
        "We have queued your inquiry for review to ensure an accurate resolution."
    )
    action = {
        "action_type": "escalate_ops_ticket",
        "customer_ref": customer_label,
        "order_ref": order_ref,
        "requires_human_approval": True,
        "summary": f"Escalate ambiguous inquiry ({len(redacted_message)} chars) to ops queue",
    }
    return draft, action


class LangGraphAgentEngine:
    """Orchestrates deterministic StateGraph workflows with PostgreSQL persistence."""

    def __init__(
        self,
        repo: AgentRepository,
        settings: Settings,
        model_router: TieredModelRouter | None = None,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._router = model_router or TieredModelRouter(settings)
        self._intake_graph = self._compile_intake_graph()
        self._execution_graph = self._compile_execution_graph()

    def _compile_intake_graph(self) -> Any:
        graph = StateGraph(AgentGraphState)
        graph.add_node("redact_pii", self._node_redact_pii)
        graph.add_node("route_intent", self._node_route_intent)
        graph.add_node("fetch_context", self._node_fetch_context)
        graph.add_node("generate_draft", self._node_generate_draft)
        graph.add_node("hitl_gate", self._node_hitl_gate)
        graph.add_node("execute_action", self._node_execute_action)

        graph.set_entry_point("redact_pii")
        graph.add_edge("redact_pii", "route_intent")
        graph.add_edge("route_intent", "fetch_context")
        graph.add_edge("fetch_context", "generate_draft")
        graph.add_conditional_edges(
            "generate_draft",
            self._route_after_draft,
            {
                "hitl_gate": "hitl_gate",
                "execute_action": "execute_action",
            },
        )
        graph.add_edge("hitl_gate", END)
        graph.add_edge("execute_action", END)
        return graph.compile()

    def _compile_execution_graph(self) -> Any:
        graph = StateGraph(AgentGraphState)
        graph.add_node("execute_action", self._node_execute_action)
        graph.set_entry_point("execute_action")
        graph.add_edge("execute_action", END)
        return graph.compile()

    @staticmethod
    def _route_after_draft(state: AgentGraphState) -> Literal["hitl_gate", "execute_action"]:
        return "hitl_gate" if state.get("requires_hitl") else "execute_action"

    def _node_redact_pii(self, state: AgentGraphState) -> AgentGraphState:
        started = time.perf_counter()
        run_id = UUID(state["run_id"])
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        self._repo.record_transition(
            run_id=run_id,
            from_state=AgentState.RECEIVED,
            to_state=AgentState.PII_REDACTED,
            actor=TransitionActor.SYSTEM,
            latency_ms=latency_ms,
            metadata={"redaction_summary": state["redaction_summary"]},
        )
        return {**state, "current_state": AgentState.PII_REDACTED.value}

    def _node_route_intent(self, state: AgentGraphState) -> AgentGraphState:
        run_id = UUID(state["run_id"])
        intent, tier, confidence, risk_level, call_result = self._router.classify_intent(
            state["redacted_message"],
            _classify_intent,
        )

        self._repo.log_llm_cost(
            run_id=run_id,
            step_name="route_intent",
            routing_tier=call_result.routing_tier,
            model_name=call_result.model_used,
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
            estimated_cost_usd=call_result.estimated_cost_usd,
            latency_ms=call_result.latency_ms,
            is_fallback=call_result.is_fallback,
        )
        self._repo.record_transition(
            run_id=run_id,
            from_state=AgentState.PII_REDACTED,
            to_state=AgentState.INTENT_ROUTED,
            actor=TransitionActor.AGENT,
            model_used=call_result.model_used,
            routing_tier=call_result.routing_tier,
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
            cost_usd=call_result.estimated_cost_usd,
            latency_ms=call_result.latency_ms,
            metadata={
                "detected_intent": intent,
                "confidence": confidence,
                "is_fallback": call_result.is_fallback,
                "fallback_reason": call_result.fallback_reason,
            },
            run_updates={
                "detected_intent": intent,
                "routing_tier": tier,
                "confidence": confidence,
            },
        )
        return {
            **state,
            "current_state": AgentState.INTENT_ROUTED.value,
            "detected_intent": intent,
            "routing_tier": tier.value,
            "confidence": confidence,
            "risk_level": risk_level.value,
        }

    def _node_fetch_context(self, state: AgentGraphState) -> AgentGraphState:
        started = time.perf_counter()
        run_id = UUID(state["run_id"])
        order_match = _ORDER_REF_RE.search(state["redacted_message"])
        context = {
            "customer_ref": state.get("customer_ref") or "CUST-ANONYMOUS",
            "order_ref": order_match.group(0) if order_match else "ORD-UNSPECIFIED",
            "policy_version": "ops-policy-2026.1",
            "sla_tier": "standard",
        }
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        self._repo.record_transition(
            run_id=run_id,
            from_state=AgentState.INTENT_ROUTED,
            to_state=AgentState.CONTEXT_FETCHED,
            actor=TransitionActor.SYSTEM,
            latency_ms=latency_ms,
            metadata={"context": context},
        )
        return {
            **state,
            "current_state": AgentState.CONTEXT_FETCHED.value,
            "context": context,
        }

    def _node_generate_draft(self, state: AgentGraphState) -> AgentGraphState:
        run_id = UUID(state["run_id"])
        intent = state["detected_intent"]
        tier = RoutingTier(state["routing_tier"])
        confidence = float(state["confidence"])

        fallback_draft, proposed_action = _build_proposed_action(
            intent=intent,
            redacted_message=state["redacted_message"],
            customer_ref=state.get("customer_ref"),
            context=state.get("context", {}),
        )
        draft_response, call_result = self._router.generate_draft(
            intent=intent,
            tier=tier,
            redacted_message=state["redacted_message"],
            customer_ref=state.get("customer_ref"),
            context=state.get("context", {}),
            fallback_draft=fallback_draft,
        )
        requires_hitl = (
            intent in HIGH_IMPACT_INTENTS
            or confidence < self._settings.hitl_confidence_threshold
            or bool(proposed_action.get("requires_human_approval"))
        )

        self._repo.log_llm_cost(
            run_id=run_id,
            step_name="generate_draft",
            routing_tier=call_result.routing_tier,
            model_name=call_result.model_used,
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
            estimated_cost_usd=call_result.estimated_cost_usd,
            latency_ms=call_result.latency_ms,
            is_fallback=call_result.is_fallback,
        )
        self._repo.record_transition(
            run_id=run_id,
            from_state=AgentState.CONTEXT_FETCHED,
            to_state=AgentState.DRAFT_GENERATED,
            actor=TransitionActor.AGENT,
            model_used=call_result.model_used,
            routing_tier=call_result.routing_tier,
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
            cost_usd=call_result.estimated_cost_usd,
            latency_ms=call_result.latency_ms,
            metadata={
                "requires_hitl": requires_hitl,
                "action_type": proposed_action["action_type"],
                "is_fallback": call_result.is_fallback,
                "fallback_reason": call_result.fallback_reason,
            },
            run_updates={
                "requires_hitl": requires_hitl,
                "draft_response": draft_response,
                "proposed_action": proposed_action,
            },
        )
        return {
            **state,
            "current_state": AgentState.DRAFT_GENERATED.value,
            "requires_hitl": requires_hitl,
            "draft_response": draft_response,
            "proposed_action": proposed_action,
        }

    def _node_hitl_gate(self, state: AgentGraphState) -> AgentGraphState:
        started = time.perf_counter()
        run_id = UUID(state["run_id"])
        proposed_action = state["proposed_action"]
        risk_level = RiskLevel(state.get("risk_level", RiskLevel.HIGH.value))

        approval = self._repo.create_hitl_approval(
            run_id=run_id,
            action_type=str(proposed_action.get("action_type", "manual_review")),
            action_preview={
                **proposed_action,
                "draft_response": state["draft_response"],
                "confidence": state["confidence"],
            },
            risk_level=risk_level,
        )
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        self._repo.record_transition(
            run_id=run_id,
            from_state=AgentState.DRAFT_GENERATED,
            to_state=AgentState.AWAITING_APPROVAL,
            actor=TransitionActor.SYSTEM,
            latency_ms=latency_ms,
            metadata={"approval_id": str(approval.id), "risk_level": risk_level.value},
        )
        return {**state, "current_state": AgentState.AWAITING_APPROVAL.value}

    def _node_execute_action(self, state: AgentGraphState) -> AgentGraphState:
        run_id = UUID(state["run_id"])
        from_state = AgentState(state["current_state"])
        actor = TransitionActor(state.get("transition_actor", TransitionActor.SYSTEM.value))
        proposed_action = state.get("proposed_action", {})
        max_attempts = self._settings.max_retry_attempts
        simulate_failure = bool(state.get("simulate_action_failure", False))

        # Enter EXECUTING_ACTION from DRAFT_GENERATED, APPROVED, or DLQ
        self._repo.record_transition(
            run_id=run_id,
            from_state=from_state,
            to_state=AgentState.EXECUTING_ACTION,
            actor=actor,
            metadata={"action_type": proposed_action.get("action_type", "unknown")},
            run_updates={"attempt_count": 1},
        )

        if not simulate_failure:
            result = {
                "status": "executed",
                "action_type": proposed_action.get("action_type", "send_status_reply"),
                "summary": proposed_action.get("summary", "Action completed"),
            }
            self._repo.record_transition(
                run_id=run_id,
                from_state=AgentState.EXECUTING_ACTION,
                to_state=AgentState.COMPLETED,
                actor=actor,
                metadata={"execution_result": result},
                run_updates={"execution_result": result, "error_message": None},
            )
            return {
                **state,
                "current_state": AgentState.COMPLETED.value,
                "execution_result": result,
            }

        # Bounded retry loop with exponential backoff -> DLQ when downstream keeps failing
        error_msg = "Simulated downstream action gateway timeout (503)."
        for attempt in range(1, max_attempts + 1):
            backoff_seconds = compute_backoff_seconds(
                attempt, self._settings.retry_base_delay_seconds
            )
            self._repo.record_transition(
                run_id=run_id,
                from_state=AgentState.EXECUTING_ACTION,
                to_state=AgentState.FAILED_RETRYING,
                actor=actor,
                metadata={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": error_msg,
                    "backoff_seconds": backoff_seconds,
                },
                run_updates={"attempt_count": attempt, "error_message": error_msg},
            )
            if attempt < max_attempts:
                if backoff_seconds > 0:
                    time.sleep(backoff_seconds)
                self._repo.record_transition(
                    run_id=run_id,
                    from_state=AgentState.FAILED_RETRYING,
                    to_state=AgentState.EXECUTING_ACTION,
                    actor=actor,
                    metadata={"retry_attempt": attempt + 1},
                    run_updates={"attempt_count": attempt + 1},
                )

        dlq_metadata: dict[str, Any] = {"attempts_made": max_attempts}
        if not state.get("is_dlq_replay"):
            dlq_job = self._repo.create_dlq_job(
                run_id=run_id,
                failed_state=AgentState.EXECUTING_ACTION,
                error_code="DOWNSTREAM_TIMEOUT",
                error_message=error_msg,
                attempts_made=max_attempts,
                payload_snapshot={
                    "redacted_message": state["redacted_message"],
                    "proposed_action": proposed_action,
                },
            )
            dlq_metadata["dlq_job_id"] = str(dlq_job["id"])

        self._repo.record_transition(
            run_id=run_id,
            from_state=AgentState.FAILED_RETRYING,
            to_state=AgentState.DLQ,
            actor=actor,
            metadata=dlq_metadata,
            run_updates={"error_message": error_msg},
        )
        return {**state, "current_state": AgentState.DLQ.value, "execution_result": None}

    def start_run(
        self,
        request: RunCreateRequest,
        *,
        idempotency_key: str,
    ) -> tuple[RunDetailResponse, bool]:
        """Redact PII at the boundary, enforce idempotency, and execute the LangGraph workflow."""
        raw_payload = request.model_dump(mode="json")
        payload_hash = compute_payload_hash(raw_payload)

        # PDPA Zero-Raw-PII guarantee: redact BEFORE any DB insert or logging
        redacted_input, redaction_summary = redact_payload(raw_payload)

        run_detail, is_replayed = self._repo.create_or_get_run(
            idempotency_key=idempotency_key,
            request_payload_hash=payload_hash,
            source=request.source,
            workflow_type=request.workflow_type,
            customer_ref=request.customer_ref,
            redacted_input=redacted_input,
            redaction_summary=redaction_summary,
        )
        if is_replayed:
            return run_detail, True

        initial_state: AgentGraphState = {
            "run_id": str(run_detail.id),
            "redacted_message": str(redacted_input["message"]),
            "redaction_summary": redaction_summary.model_dump(),
            "customer_ref": request.customer_ref,
            "workflow_type": request.workflow_type,
            "simulate_action_failure": request.simulate_action_failure,
            "transition_actor": TransitionActor.SYSTEM.value,
            "current_state": AgentState.RECEIVED.value,
        }
        self._intake_graph.invoke(initial_state)
        return self._repo.get_run_detail(run_detail.id), False

    def decide_and_resume(
        self,
        *,
        approval_id: UUID,
        decision: ApprovalStatus,
        decided_by: str,
        decision_reason: str | None,
    ) -> ApprovalDecisionResponse:
        """Apply human HITL decision and resume execution if APPROVED."""
        approval, run_id = self._repo.decide_approval(
            approval_id=approval_id,
            decision=decision,
            decided_by=decided_by,
            decision_reason=decision_reason,
        )

        if decision == ApprovalStatus.APPROVED:
            run_detail = self._repo.get_run_detail(run_id)
            resume_state: AgentGraphState = {
                "run_id": str(run_id),
                "redacted_message": str(run_detail.redacted_input.get("message", "")),
                "redaction_summary": run_detail.redaction_summary.model_dump(),
                "customer_ref": run_detail.customer_ref,
                "workflow_type": run_detail.workflow_type,
                "simulate_action_failure": bool(
                    run_detail.redacted_input.get("simulate_action_failure", False)
                ),
                "transition_actor": TransitionActor.SYSTEM.value,
                "current_state": AgentState.APPROVED.value,
                "proposed_action": run_detail.proposed_action or {},
            }
            self._execution_graph.invoke(resume_state)

        return ApprovalDecisionResponse(
            approval=approval,
            run=self._repo.get_run_detail(run_id),
        )

    def replay_dlq_job(self, job_id: UUID, *, force_failure: bool = False) -> DLQReplayResponse:
        """Claim an OPEN DLQ job and replay its execution step via LangGraph."""
        job, run_detail = self._repo.claim_dlq_job_for_replay(job_id)
        proposed_action = run_detail.proposed_action or job.payload_snapshot.get(
            "proposed_action", {}
        )
        replay_state: AgentGraphState = {
            "run_id": str(run_detail.id),
            "redacted_message": str(
                run_detail.redacted_input.get(
                    "message", job.payload_snapshot.get("redacted_message", "")
                )
            ),
            "redaction_summary": run_detail.redaction_summary.model_dump(),
            "customer_ref": run_detail.customer_ref,
            "workflow_type": run_detail.workflow_type,
            "simulate_action_failure": force_failure,
            "transition_actor": TransitionActor.DLQ_REPLAY.value,
            "is_dlq_replay": True,
            "current_state": AgentState.DLQ.value,
            "proposed_action": proposed_action,
        }
        self._execution_graph.invoke(replay_state)

        updated_run = self._repo.get_run_detail(run_detail.id)
        if updated_run.current_state == AgentState.COMPLETED:
            updated_job = self._repo.mark_dlq_job_status(job_id, status=DLQStatus.REPLAYED)
            return DLQReplayResponse(
                job=updated_job,
                run_state=updated_run.current_state,
                message="DLQ job replayed and run completed.",
            )

        updated_job = self._repo.mark_dlq_job_status(
            job_id,
            status=DLQStatus.OPEN,
            error_message=updated_run.error_message,
        )
        return DLQReplayResponse(
            job=updated_job,
            run_state=updated_run.current_state,
            message="DLQ replay failed; job returned to OPEN.",
        )
