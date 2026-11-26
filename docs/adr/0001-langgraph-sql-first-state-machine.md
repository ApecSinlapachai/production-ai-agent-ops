# ADR-0001: Explicit LangGraph StateGraph with SQL-First PostgreSQL 16 Persistence

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Apec Sinlapachai

---

## 1. Context
Production operations agents must provide full auditability (who approved what, which model ran, token counts, USD cost, and exact failure state) and survive concurrent HITL approval requests or process restarts behind Supabase PgBouncer on a `$0` free-tier stack. Opaque framework checkpointers store serialized blobs that are difficult to query, lock row-by-row, or inspect in SQL.

## 2. Decision
> We will wrap explicit deterministic step handlers inside a **`LangGraph` `StateGraph`** (`api/app/services/langgraph_engine.py`) and persist every state transition directly into **relational PostgreSQL 16 tables** (`agent_runs`, `agent_state_transitions`, `hitl_approvals`, `dead_letter_jobs`) using `psycopg_pool` (`prepare_threshold=None`) and `FOR UPDATE` row locking.

## 3. Alternatives Considered
| Option | Pros | Cons | Why Rejected / Chosen |
| :--- | :--- | :--- | :--- |
| **LangGraph `StateGraph` + SQL-First Tables (Chosen)** | Explicit graph topology + 100% SQL-queryable audit trail, `CHECK` constraints, `FOR UPDATE` locks, and PgBouncer safety | Slightly more explicit repository code (`repository.py`) | Best auditability, concurrency safety, and schema integrity |
| **Opaque LangGraph PostgresSaver Checkpointer** | Fast to prototype | Serialized binary checkpoints hard to query for cost telemetry, compliance audits, or HITL queues | Rejected; obscures operational state from SQL & BI |
| **Unstructured ReAct Agent Loop** | Flexible tool selection | Non-deterministic transitions; high risk of skipping HITL gates or looping endlessly | Rejected; unsuitable for regulated/financial ops workflows |

## 4. Consequences
- **Positive:** Every state transition is 1:1 aligned between `sql/001_schema.sql` and `api/app/schemas/`, safe under concurrent approvals (`FOR UPDATE`), and compatible with Supabase PgBouncer (`prepare_threshold=None`).
- **Negative / Trade-offs:** Schema changes require updating both `sql/001_schema.sql` and `api/app/schemas/` together.
- **Reversibility:** Medium — persistence is isolated behind `AgentRepository` (`api/app/services/repository.py`).
