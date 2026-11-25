"""Core state-machine enums and transition table aligned 1:1 with SQL CHECK constraints."""

from enum import StrEnum


class AgentState(StrEnum):
    """Deterministic states persisted on `agent_runs` and `agent_state_transitions`."""

    RECEIVED = "RECEIVED"
    PII_REDACTED = "PII_REDACTED"
    INTENT_ROUTED = "INTENT_ROUTED"
    CONTEXT_FETCHED = "CONTEXT_FETCHED"
    DRAFT_GENERATED = "DRAFT_GENERATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING_ACTION = "EXECUTING_ACTION"
    COMPLETED = "COMPLETED"
    FAILED_RETRYING = "FAILED_RETRYING"
    DLQ = "DLQ"


class RunSource(StrEnum):
    """Inbound origin of an agent run."""

    API = "api"
    N8N = "n8n"
    DEMO = "demo"


class RoutingTier(StrEnum):
    """Model routing tier selected for an LLM step."""

    FAST = "FAST"
    COMPLEX = "COMPLEX"
    RULE_FALLBACK = "RULE_FALLBACK"


class TransitionActor(StrEnum):
    """Actor responsible for a state transition."""

    SYSTEM = "system"
    AGENT = "agent"
    HUMAN = "human"
    DLQ_REPLAY = "dlq_replay"


class RiskLevel(StrEnum):
    """Risk classification for Human-in-the-Loop approval gates."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ApprovalStatus(StrEnum):
    """Decision status of a HITL approval record."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class DLQStatus(StrEnum):
    """Lifecycle status of a Dead-Letter Queue job."""

    OPEN = "OPEN"
    REPLAYING = "REPLAYING"
    REPLAYED = "REPLAYED"
    DISCARDED = "DISCARDED"


ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.RECEIVED: frozenset({AgentState.PII_REDACTED}),
    AgentState.PII_REDACTED: frozenset({AgentState.INTENT_ROUTED}),
    AgentState.INTENT_ROUTED: frozenset({AgentState.CONTEXT_FETCHED}),
    AgentState.CONTEXT_FETCHED: frozenset({AgentState.DRAFT_GENERATED}),
    AgentState.DRAFT_GENERATED: frozenset(
        {AgentState.AWAITING_APPROVAL, AgentState.EXECUTING_ACTION}
    ),
    AgentState.AWAITING_APPROVAL: frozenset({AgentState.APPROVED, AgentState.REJECTED}),
    AgentState.APPROVED: frozenset({AgentState.EXECUTING_ACTION}),
    AgentState.REJECTED: frozenset(),
    AgentState.EXECUTING_ACTION: frozenset({AgentState.COMPLETED, AgentState.FAILED_RETRYING}),
    AgentState.FAILED_RETRYING: frozenset({AgentState.EXECUTING_ACTION, AgentState.DLQ}),
    AgentState.DLQ: frozenset({AgentState.EXECUTING_ACTION}),
    AgentState.COMPLETED: frozenset(),
}
