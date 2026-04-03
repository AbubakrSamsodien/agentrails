"""SQLite storage backend for workflow state and events."""
# pylint: disable=C0301  # SQL statements exceed line length

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from agentrails.event_log import Event
from agentrails.steps.base import StepResult
from agentrails.storage import RunInfo, SessionInfo, StateStore


class SqliteStateStore(StateStore):
    """SQLite-based state storage backend."""

    def __init__(self, db_path: Path | str | None = None):
        """Initialize SQLite storage.

        Args:
            db_path: Path to SQLite database file. Defaults to .agentrails/state.db
        """
        if db_path is None:
            db_path = Path(".agentrails/state.db")
        self.db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get or create database connection."""
        if self._db is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._init_schema()
        return self._db

    async def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        db = await self._get_connection()
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                workflow_name TEXT,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                final_state_json TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                step_id TEXT,
                data_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS step_results (
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                status TEXT NOT NULL,
                outputs_json TEXT,
                raw_output TEXT,
                duration_seconds REAL,
                error TEXT,
                PRIMARY KEY (run_id, step_id),
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                name TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                working_dir TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_events_run_timestamp
            ON events(run_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_sessions_run_id
            ON sessions(run_id);
        """)
        await db.commit()

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
        db = await self._get_connection()

        # Check if run exists
        cursor = await db.execute(
            "SELECT run_id FROM runs WHERE run_id = ?",
            (run_id,),
        )
        exists = await cursor.fetchone() is not None

        if exists:
            # Update existing run - don't touch started_at
            if status in ("completed", "failed"):
                await db.execute(
                    """
                    UPDATE runs
                    SET status = ?, final_state_json = ?, completed_at = datetime('now')
                    WHERE run_id = ?
                    """,
                    (status, json.dumps(state), run_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE runs
                    SET status = ?, final_state_json = ?
                    WHERE run_id = ?
                    """,
                    (status, json.dumps(state), run_id),
                )
        else:
            # Insert new run with started_at
            await db.execute(
                """
                INSERT INTO runs (run_id, workflow_id, workflow_name, status, started_at, final_state_json)
                VALUES (?, ?, ?, 'running', datetime('now'), ?)
                """,  # noqa: C0301
                (run_id, workflow_id, workflow_name, json.dumps(state)),
            )
        await db.commit()

    async def load_state(
        self,
        workflow_id: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Load workflow state checkpoint."""
        db = await self._get_connection()
        cursor = await db.execute(
            "SELECT final_state_json FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    async def append_event(self, event: Any) -> None:
        """Append an event to the log."""
        db = await self._get_connection()
        await db.execute(
            """
            INSERT INTO events (event_id, run_id, workflow_id, timestamp, event_type, step_id, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,  # noqa: C0301
            (
                event.event_id,
                event.run_id,
                event.workflow_id,
                event.timestamp.isoformat(),
                event.event_type,
                event.step_id,
                json.dumps(event.data),
            ),
        )
        await db.commit()

    async def load_events(
        self,
        workflow_id: str,
        run_id: str,
    ) -> list[Any]:
        """Load all events for a run."""
        db = await self._get_connection()
        cursor = await db.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        )
        rows = await cursor.fetchall()

        events = []
        for row in rows:
            # Parse ISO format timestamp string back to datetime
            timestamp_str = row["timestamp"]
            if isinstance(timestamp_str, str):
                timestamp = datetime.fromisoformat(timestamp_str)
            else:
                timestamp = timestamp_str

            events.append(
                Event(
                    event_id=row["event_id"],
                    workflow_id=row["workflow_id"],
                    run_id=row["run_id"],
                    timestamp=timestamp,
                    event_type=row["event_type"],
                    step_id=row["step_id"],
                    data=json.loads(row["data_json"]),
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
        db = await self._get_connection()
        await db.execute(
            """
            INSERT OR REPLACE INTO step_results
            (run_id, step_id, status, outputs_json, raw_output, duration_seconds, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                result.step_id,
                result.status,
                json.dumps(result.outputs),
                result.raw_output,
                result.duration_seconds,
                result.error,
            ),
        )
        await db.commit()

    async def load_step_results(
        self,
        workflow_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Load all step results for a run."""
        db = await self._get_connection()
        cursor = await db.execute(
            "SELECT * FROM step_results WHERE run_id = ?",
            (run_id,),
        )
        rows = await cursor.fetchall()

        results = {}
        for row in rows:
            outputs = json.loads(row["outputs_json"]) if row["outputs_json"] else {}
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
        db = await self._get_connection()
        if workflow_id:
            cursor = await db.execute(
                "SELECT * FROM runs WHERE workflow_id = ? ORDER BY started_at DESC",
                (workflow_id,),
            )
        else:
            cursor = await db.execute("SELECT * FROM runs ORDER BY started_at DESC")

        rows = await cursor.fetchall()
        return [
            RunInfo(
                run_id=row["run_id"],
                workflow_id=row["workflow_id"],
                status=row["status"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
            )
            for row in rows
        ]

    async def save_session(self, session: SessionInfo) -> None:
        """Save session metadata."""
        db = await self._get_connection()
        await db.execute(
            """
            INSERT OR REPLACE INTO sessions
            (session_id, workflow_id, run_id, name, status, working_dir, created_at, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                session.session_id,
                session.workflow_id,
                session.run_id,
                session.name,
                session.status,
                session.working_dir,
                session.created_at.isoformat(),
                session.last_used_at.isoformat(),
            ),
        )
        await db.commit()

    async def load_sessions(
        self,
        workflow_id: str | None = None,
        run_id: str | None = None,
    ) -> list[SessionInfo]:
        """Load sessions, optionally filtered."""
        db = await self._get_connection()

        query = "SELECT * FROM sessions WHERE 1=1"
        params = []

        if workflow_id:
            query += " AND workflow_id = ?"
            params.append(workflow_id)
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)

        query += " ORDER BY created_at DESC"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

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
                    created_at=datetime.fromisoformat(row["created_at"]),
                    last_used_at=datetime.fromisoformat(row["last_used_at"]),
                )
            )
        return sessions

    async def update_session_status(
        self,
        session_id: str,
        status: str,
    ) -> None:
        """Update session status."""
        db = await self._get_connection()
        await db.execute(
            "UPDATE sessions SET status = ?, last_used_at = ? WHERE session_id = ?",
            (status, datetime.now().isoformat(), session_id),
        )
        await db.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
