"""PostgreSQL storage backend for workflow state and events.

This is an optional storage backend for team/enterprise use cases
requiring concurrent access and durability.
"""
# pylint: disable=C0301  # SQL statements exceed line length

from __future__ import annotations

import json
import os
from typing import Any, Literal

from agentrails.event_log import Event
from agentrails.steps.base import StepResult
from agentrails.storage import RunInfo, SessionInfo, StateStore


class PostgresStateStore(StateStore):
    """PostgreSQL-based state storage backend.

    Requires the asyncpg library and connection string configured via
    AGENTRAILS_DB_URL environment variable or --db-url CLI flag.
    """

    def __init__(self, connection_string: str | None = None):
        """Initialize PostgreSQL storage.

        Args:
            connection_string: PostgreSQL connection string.
                Falls back to AGENTRAILS_DB_URL env var if not provided.
        """
        self.connection_string = connection_string
        self._pool: Any | None = None

    async def _get_pool(self) -> Any:
        """Get or create connection pool."""
        if self._pool is None:
            import asyncpg  # pylint: disable=C0415,E0401

            conn_str = self.connection_string
            if not conn_str:
                conn_str = os.environ.get("AGENTRAILS_DB_URL")
            if not conn_str:
                raise ValueError(
                    "PostgreSQL connection string required (use AGENTRAILS_DB_URL or --db-url)"
                )

            self._pool = await asyncpg.create_pool(conn_str)
            await self._init_schema()
        return self._pool

    async def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    workflow_name TEXT,
                    status TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ,
                    final_state_json JSONB
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    event_type TEXT NOT NULL,
                    step_id TEXT,
                    data_json JSONB NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS step_results (
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    outputs_json JSONB,
                    raw_output TEXT,
                    duration_seconds REAL,
                    error TEXT,
                    PRIMARY KEY (run_id, step_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    name TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    working_dir TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    last_used_at TIMESTAMPTZ NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_run_timestamp
                ON events(run_id, timestamp)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_run_id
                ON sessions(run_id)
            """)

    async def save_state(
        self,
        workflow_id: str,
        run_id: str,
        state: dict[str, Any],
        workflow_name: str | None = None,
        status: str = "running",
    ) -> None:
        """Save workflow state checkpoint.

        Args:
            workflow_id: ID of the workflow
            run_id: ID of this run
            state: State dictionary to save
            workflow_name: Optional workflow name (only used on initial insert)
            status: Run status (running, completed, failed)
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if status in ("completed", "failed"):
                await conn.execute(
                    """
                    INSERT INTO runs (run_id, workflow_id, workflow_name, status, started_at, final_state_json, completed_at)
                    VALUES ($1, $2, $3, $4, clock_timestamp(), $5::jsonb, clock_timestamp())
                    ON CONFLICT (run_id) DO UPDATE
                    SET status = $4, final_state_json = $5::jsonb, completed_at = clock_timestamp()
                    """,  # noqa: C0301
                    run_id,
                    workflow_id,
                    workflow_name,
                    status,
                    json.dumps(state),
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO runs (run_id, workflow_id, workflow_name, status, started_at, final_state_json)
                    VALUES ($1, $2, $3, $4, clock_timestamp(), $5::jsonb)
                    ON CONFLICT (run_id) DO UPDATE
                    SET status = $4, final_state_json = $5::jsonb
                    """,  # noqa: C0301
                    run_id,
                    workflow_id,
                    workflow_name,
                    status,
                    json.dumps(state),
                )

    async def load_state(
        self,
        workflow_id: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Load workflow state checkpoint."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT final_state_json FROM runs WHERE run_id = $1",
                run_id,
            )
            if row is None:
                return None
            return row["final_state_json"]

    async def append_event(self, event: Any) -> None:
        """Append an event to the log."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO events (event_id, run_id, workflow_id, timestamp, event_type, step_id, data_json)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,  # noqa: C0301
                event.event_id,
                event.run_id,
                event.workflow_id,
                event.timestamp,
                event.event_type,
                event.step_id,
                json.dumps(event.data),
            )

    async def load_events(
        self,
        workflow_id: str,
        run_id: str,
    ) -> list[Any]:
        """Load all events for a run."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM events WHERE run_id = $1 ORDER BY timestamp",
                run_id,
            )

        events = []
        for row in rows:
            events.append(
                Event(
                    event_id=row["event_id"],
                    workflow_id=row["workflow_id"],
                    run_id=row["run_id"],
                    timestamp=row["timestamp"],
                    event_type=row["event_type"],
                    step_id=row["step_id"],
                    data=row["data_json"],
                )
            )
        return events

    async def save_step_result(
        self,
        workflow_id: str,
        run_id: str,
        result: Any,
    ) -> None:
        """Save a step execution result."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO step_results (run_id, step_id, status, outputs_json, raw_output, duration_seconds, error)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
                ON CONFLICT (run_id, step_id) DO UPDATE
                SET status = $3, outputs_json = $4::jsonb, raw_output = $5, duration_seconds = $6, error = $7
                """,  # noqa: C0301
                run_id,
                result.step_id,
                result.status,
                json.dumps(result.outputs),
                result.raw_output,
                result.duration_seconds,
                result.error,
            )

    async def load_step_results(
        self,
        workflow_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Load all step results for a run."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM step_results WHERE run_id = $1",
                run_id,
            )

        results = {}
        for row in rows:
            outputs = row["outputs_json"] if row["outputs_json"] else {}
            results[row["step_id"]] = StepResult(
                step_id=row["step_id"],
                status=row["status"],
                outputs=outputs,
                raw_output=row["raw_output"] or "",
                duration_seconds=row["duration_seconds"],
                error=row["error"],
            )
        return results

    async def list_runs(
        self,
        workflow_id: str | None = None,
    ) -> list[RunInfo]:
        """List workflow runs."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if workflow_id:
                rows = await conn.fetch(
                    "SELECT * FROM runs WHERE workflow_id = $1 ORDER BY started_at DESC",
                    workflow_id,
                )
            else:
                rows = await conn.fetch("SELECT * FROM runs ORDER BY started_at DESC")

        return [
            RunInfo(
                run_id=row["run_id"],
                workflow_id=row["workflow_id"],
                status=row["status"],
                started_at=row["started_at"].isoformat(),
                completed_at=row["completed_at"].isoformat() if row["completed_at"] else None,
            )
            for row in rows
        ]

    async def save_session(self, session: SessionInfo) -> None:
        """Save session metadata."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (session_id, workflow_id, run_id, name, status, working_dir, created_at, last_used_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (session_id) DO UPDATE
                SET status = $5, last_used_at = $8
                """,  # noqa: C0301
                session.session_id,
                session.workflow_id,
                session.run_id,
                session.name,
                session.status,
                session.working_dir,
                session.created_at,
                session.last_used_at,
            )

    async def load_sessions(
        self,
        workflow_id: str | None = None,
        run_id: str | None = None,
    ) -> list[SessionInfo]:
        """Load sessions, optionally filtered."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM sessions WHERE 1=1"
            params = []
            param_count = 0

            if workflow_id:
                param_count += 1
                query += f" AND workflow_id = ${param_count}"
                params.append(workflow_id)
            if run_id:
                param_count += 1
                query += f" AND run_id = ${param_count}"
                params.append(run_id)

            query += " ORDER BY created_at DESC"

            rows = await conn.fetch(query, *params)

        sessions = []
        for row in rows:
            sessions.append(
                SessionInfo(
                    session_id=row["session_id"],
                    workflow_id=row["workflow_id"],
                    run_id=row["run_id"],
                    name=row["name"],
                    status=row["status"],
                    working_dir=row["working_dir"],
                    created_at=row["created_at"],
                    last_used_at=row["last_used_at"],
                )
            )
        return sessions

    async def update_session_status(
        self,
        session_id: str,
        status: Literal["running", "completed", "dead", "killed"],
    ) -> None:
        """Update session status."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET status = $1, last_used_at = clock_timestamp() WHERE session_id = $2",
                status,
                session_id,
            )

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
