"""Command-line interface for AgentRails workflow runtime."""

import asyncio
import json
import sys
from pathlib import Path

import click

from agentrails.utils import get_logger

logger = get_logger(__name__)


@click.group()
@click.version_option(package_name="agentrails")
def main():
    """AgentRails — Deterministic AI workflow runtime."""


@main.command()
@click.argument("workflow", type=click.Path(exists=True))
@click.option("--state", "initial_state", help="Initial state as JSON string")
@click.option("--working-dir", type=click.Path(exists=True), help="Working directory")
@click.option(
    "--storage", type=click.Choice(["sqlite", "postgres"]), default="sqlite", help="Storage backend"
)
@click.option("--db-url", help="Database URL (for postgres backend)")
@click.option("--interactive", is_flag=True, help="Enable interactive display mode")
def run(
    workflow: str,
    initial_state: str | None,
    working_dir: str | None,
    storage: str,  # pylint: disable=W0613
    db_url: str | None,  # pylint: disable=W0613
    interactive: bool,  # pylint: disable=W0613
):
    """Run a workflow from a YAML file."""
    from agentrails.config import Config
    from agentrails.engine import WorkflowRunner

    # Parse initial state
    state_dict = None
    if initial_state:
        try:
            state_dict = json.loads(initial_state)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON for --state: {e}", err=True)
            sys.exit(2)

    # Build config
    config_kwargs = {}
    if db_url:
        config_kwargs["db_url"] = db_url

    config = Config.from_env()
    if config_kwargs:
        config = Config.from_cli(config, **config_kwargs)

    # Warn about unsupported options (for future implementation)
    if storage != "sqlite":
        logger.warning("PostgreSQL storage (--storage postgres) not yet implemented, using SQLite")
    if interactive:
        logger.warning("Interactive mode (--interactive) not yet implemented, using compact output")

    # Set working directory
    workdir = Path(working_dir).resolve() if working_dir else None

    try:
        runner = WorkflowRunner(config=config, working_directory=workdir)
        result = asyncio.run(runner.run(workflow, state_dict))

        # Exit with appropriate code
        if result.status == "completed":
            sys.exit(0)
        else:
            sys.exit(1)

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:  # pylint: disable=W0718
        click.echo(f"Error: {e}", err=True)
        sys.exit(5)


@main.command()
@click.argument("run_id")
@click.option("--interactive", is_flag=True, help="Enable interactive display mode")
def resume(run_id: str, interactive: bool = False):  # pylint: disable=W0613
    """Resume a workflow from a checkpoint."""
    from agentrails.config import Config
    from agentrails.engine import WorkflowRunner

    config = Config.from_env()
    runner = WorkflowRunner(config=config)

    try:
        result = asyncio.run(runner.resume(run_id))
        if result.status == "completed":
            sys.exit(0)
        else:
            sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
    except Exception as e:  # pylint: disable=W0718
        click.echo(f"Error: {e}", err=True)
        sys.exit(5)


@main.command()
@click.argument("run_id")
def status(run_id: str):
    """Show status of a workflow run."""
    from agentrails.config import Config
    from agentrails.storage_sqlite import SqliteStateStore

    config = Config.from_env()
    db_path = Path(config.state_dir) / "state.db"
    store = SqliteStateStore(db_path)

    try:
        runs = asyncio.run(store.list_runs())
        run_info = None
        for r in runs:
            if r.run_id == run_id:
                run_info = r
                break

        if run_info is None:
            click.echo(f"Run not found: {run_id}", err=True)
            sys.exit(2)

        # Print status
        completed_at = run_info.completed_at or "running"
        click.echo(f"{run_id}: {run_info.workflow_id} - {run_info.status} ({completed_at})")

        if run_info.status in ("completed", "failed"):
            # Load step results
            step_results = asyncio.run(store.load_step_results(run_info.workflow_id, run_id))
            for step_id, result in step_results.items():
                click.echo(f"  {step_id}: {result.status}")

    except Exception as e:  # pylint: disable=W0718
        click.echo(f"Error: {e}", err=True)
        sys.exit(5)
    finally:
        asyncio.run(store.close())


@main.command()
@click.option("--workflow", help="Filter by workflow name")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(["completed", "failed", "running"]),
    help="Filter by status",
)
def list(workflow: str | None, status_filter: str | None):  # noqa: A001
    """List workflow runs."""
    from agentrails.config import Config
    from agentrails.storage_sqlite import SqliteStateStore

    config = Config.from_env()
    db_path = Path(config.state_dir) / "state.db"
    store = SqliteStateStore(db_path)

    try:
        runs = asyncio.run(store.list_runs(workflow_id=workflow))

        if status_filter:
            runs = [r for r in runs if r.status == status_filter]

        if not runs:
            click.echo("No runs found")
            return

        # Print table
        click.echo(f"{'RUN_ID':<36} {'WORKFLOW':<20} {'STATUS':<12} {'STARTED':<24}")
        click.echo("-" * 92)
        for run in runs:
            click.echo(
                f"{run.run_id:<36} {run.workflow_id:<20} {run.status:<12} {run.started_at:<24}"
            )

    except Exception as e:  # pylint: disable=W0718
        click.echo(f"Error: {e}", err=True)
        sys.exit(5)
    finally:
        asyncio.run(store.close())


@main.command()
@click.argument("workflow", type=click.Path(exists=True))
def validate(workflow: str):
    """Validate a workflow YAML file without executing."""
    from agentrails.dsl_parser import ValidationError, parse_workflow

    try:
        wf = parse_workflow(workflow)
        click.echo(f"Workflow valid: {wf.name} ({len(wf.steps)} steps)")
        sys.exit(0)
    except ValidationError as e:
        click.echo(f"Validation error: {e}", err=True)
        sys.exit(3)
    except FileNotFoundError as e:
        click.echo(f"File not found: {e}", err=True)
        sys.exit(3)
    except Exception as e:  # pylint: disable=W0718
        click.echo(f"Error: {e}", err=True)
        sys.exit(5)


@main.command()
@click.argument("workflow", type=click.Path(exists=True))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["mermaid", "ascii"]),
    default="mermaid",
    help="Output format",
)
def visualize(workflow: str, output_format: str):
    """Visualize a workflow DAG."""
    from agentrails.dsl_parser import parse_workflow

    try:
        wf = parse_workflow(workflow)

        if output_format == "mermaid":
            click.echo(wf.dag.to_mermaid())
        else:
            # ASCII art DAG
            click.echo(f"Workflow: {wf.name}")
            click.echo("=" * 40)
            for step in wf.steps:
                deps = step.depends_on if step.depends_on else ["(start)"]
                click.echo(f"  {step.id} <- {', '.join(deps)}")

    except Exception as e:  # pylint: disable=W0718
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)


@main.command()
@click.argument("run_id")
def logs(run_id: str):
    """Show event log for a workflow run."""
    from agentrails.config import Config
    from agentrails.storage_sqlite import SqliteStateStore

    config = Config.from_env()
    db_path = Path(config.state_dir) / "state.db"
    store = SqliteStateStore(db_path)

    try:
        # Find workflow for this run
        runs = asyncio.run(store.list_runs())
        run_info = None
        for run in runs:
            if run.run_id == run_id:
                run_info = run
                break

        if run_info is None:
            click.echo(f"Run not found: {run_id}", err=True)
            sys.exit(2)

        # Load events
        events = asyncio.run(store.load_events(run_info.workflow_id, run_id))

        if not events:
            click.echo("No events found")
            return

        # Print events
        for event in events:
            timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            step_info = f" [{event.step_id}]" if event.step_id else ""
            click.echo(f"{timestamp} {event.event_type}{step_info}")

    except Exception as e:  # pylint: disable=W0718
        click.echo(f"Error: {e}", err=True)
        sys.exit(5)
    finally:
        asyncio.run(store.close())


@main.command()
@click.argument("run_id")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "toml"]),
    default="json",
    help="Output format",
)
def export(run_id: str, output_format: str):
    """Export final state of a workflow run."""
    from agentrails.config import Config
    from agentrails.storage_sqlite import SqliteStateStore

    config = Config.from_env()
    db_path = Path(config.state_dir) / "state.db"
    store = SqliteStateStore(db_path)

    try:
        # Find workflow for this run
        runs = asyncio.run(store.list_runs())
        run_info = None
        for run in runs:
            if run.run_id == run_id:
                run_info = run
                break

        if run_info is None:
            click.echo(f"Run not found: {run_id}", err=True)
            sys.exit(2)

        # Load state
        state = asyncio.run(store.load_state(run_info.workflow_id, run_id))

        if state is None:
            click.echo("No state found", err=True)
            sys.exit(2)

        if output_format == "json":
            click.echo(json.dumps(state, indent=2))
        else:
            # TOML write support not available without tomli_w
            click.echo(
                "Warning: TOML write support not available, outputting JSON",
                err=True,
            )
            click.echo(json.dumps(state, indent=2))

    except Exception as e:  # pylint: disable=W0718
        click.echo(f"Error: {e}", err=True)
        sys.exit(5)
    finally:
        asyncio.run(store.close())


if __name__ == "__main__":
    main()
