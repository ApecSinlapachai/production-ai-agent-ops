"""Unit tests verifying 1:1 SQL CHECK <-> Pydantic v2 enum alignment and bounds."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import (
    ALLOWED_TRANSITIONS,
    AgentState,
    ApprovalDecisionRequest,
    ApprovalStatus,
    DLQStatus,
    RiskLevel,
    RoutingTier,
    RunCreateRequest,
    RunSource,
    TransitionActor,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL_PATH = REPO_ROOT / "sql" / "001_schema.sql"


def _extract_sql_in_values(sql_text: str, column_name: str) -> set[str]:
    """Extract string literals from the first `column_name ... IN (...)` constraint."""
    pattern = rf"{re.escape(column_name)}\s+TEXT[^;]*?IN\s*\(([^)]+)\)"
    match = re.search(pattern, sql_text, flags=re.IGNORECASE | re.DOTALL)
    assert match is not None, f"Could not find IN (...) constraint for column {column_name}"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_sql_check_constraints_match_python_enums() -> None:
    """Every SQL CHECK IN (...) list matches its corresponding Python StrEnum 1:1."""
    sql_text = SCHEMA_SQL_PATH.read_text(encoding="utf-8")

    assert _extract_sql_in_values(sql_text, "current_state") == {s.value for s in AgentState}
    assert _extract_sql_in_values(sql_text, "from_state") == {s.value for s in AgentState}
    assert _extract_sql_in_values(sql_text, "to_state") == {s.value for s in AgentState}
    assert _extract_sql_in_values(sql_text, "failed_state") == {s.value for s in AgentState}

    assert _extract_sql_in_values(sql_text, "source") == {s.value for s in RunSource}
    assert _extract_sql_in_values(sql_text, "routing_tier") == {t.value for t in RoutingTier}
    assert _extract_sql_in_values(sql_text, "actor") == {a.value for a in TransitionActor}
    assert _extract_sql_in_values(sql_text, "risk_level") == {r.value for r in RiskLevel}
    assert _extract_sql_in_values(sql_text, "status") == {
        s.value for s in ApprovalStatus
    }

    # Verify DLQ status separately since `status` exists on both approvals and DLQ tables
    dlq_block_match = re.search(
        r"CREATE TABLE IF NOT EXISTS dead_letter_jobs\s*\((.*?)\);",
        sql_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert dlq_block_match is not None
    assert _extract_sql_in_values(dlq_block_match.group(1), "status") == {
        s.value for s in DLQStatus
    }


def test_allowed_transitions_covers_all_states() -> None:
    """Every AgentState is registered in ALLOWED_TRANSITIONS with valid targets."""
    assert set(ALLOWED_TRANSITIONS.keys()) == set(AgentState)
    assert ALLOWED_TRANSITIONS[AgentState.COMPLETED] == frozenset()
    assert ALLOWED_TRANSITIONS[AgentState.REJECTED] == frozenset()
    assert AgentState.AWAITING_APPROVAL in ALLOWED_TRANSITIONS[AgentState.DRAFT_GENERATED]
    assert AgentState.EXECUTING_ACTION in ALLOWED_TRANSITIONS[AgentState.DLQ]


def test_run_create_request_bounds() -> None:
    """RunCreateRequest enforces non-empty message and max payload bounds."""
    valid = RunCreateRequest(message="Where is my order REQ-2026-0001?")
    assert valid.source == RunSource.API
    assert valid.simulate_action_failure is False

    with pytest.raises(ValidationError):
        RunCreateRequest(message="")

    with pytest.raises(ValidationError):
        RunCreateRequest(message="x" * 4001)


def test_approval_decision_request_validation() -> None:
    """ApprovalDecisionRequest allows only APPROVED or REJECTED."""
    approved = ApprovalDecisionRequest(decision="APPROVED", decided_by="ops-lead")
    assert approved.decision == "APPROVED"

    with pytest.raises(ValidationError):
        ApprovalDecisionRequest(decision="PENDING", decided_by="ops-lead")  # type: ignore[arg-type]
