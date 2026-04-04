# CLAUDE.md — AgentRails Project Guide

> For AI agents working on the AgentRails codebase

---

## Project Purpose

**AgentRails** is a deterministic AI workflow runtime for orchestrating Claude Code CLI and shell commands in reproducible pipelines. It provides:

- YAML workflow definitions with DAG-based execution
- Structured output parsing (JSON/TOML) for reliable agent communication
- System prompt control at workflow and step level
- Checkpointing and event-sourced replay for crash recovery
- Pluggable storage backends (SQLite default, PostgreSQL optional)

---

## Quick Reference

```bash
# Install dev dependencies
make install-dev

# Run tests (unit only)
make test

# Run all tests (including integration)
make test-all

# Run linters
make lint

# Auto-format code
make format

# Build package
make build
```

---

## Package Layout

```
agentrails/
├── agentrails/                 # Python package root
│   ├── __init__.py             # Exports __version__
│   ├── cli.py                  # Click CLI entry point
│   ├── config.py               # Unified configuration (env vars, CLI flags, pyproject.toml)
│   ├── dag.py                  # DAG data structure with topological sort, cycle detection
│   ├── display.py              # Output manager (compact + interactive modes)
│   ├── dsl_parser.py           # YAML -> Workflow parser
│   ├── engine.py               # WorkflowRunner execution engine
│   ├── event_log.py            # Event sourcing / deterministic replay
│   ├── output.py               # JSON/TOML output parsing with schema validation
│   ├── session_manager.py      # Claude CLI subprocess lifecycle management
│   ├── state.py                # WorkflowState (immutable, dot-path access, merge strategies)
│   ├── storage.py              # StateStore ABC interface
│   ├── storage_sqlite.py       # SQLite backend (default)
│   ├── storage_postgres.py     # PostgreSQL backend (stub)
│   ├── template.py             # Jinja2 template rendering
│   ├── utils.py                # Logging config, helpers
│   └── steps/                  # Step type implementations
│       ├── __init__.py         # Re-exports all step types
│       ├── base.py             # BaseStep ABC, StepResult, ExecutionContext
│       ├── agent_step.py       # AgentStep — Claude CLI invocation
│       ├── shell_step.py       # ShellStep — subprocess execution
│       ├── parallel_step.py    # ParallelGroupStep — concurrent branches
│       ├── conditional_step.py # ConditionalStep — if/then/else branching
│       ├── loop_step.py        # LoopStep — repeat until condition (stub)
│       └── human_step.py       # HumanStep — wait for human input (stub)
├── tests/                      # pytest test suite
│   ├── conftest.py             # Shared fixtures (mock_claude_cli, tmp_state_dir)
│   ├── test_*.py               # Unit tests per module
│   ├── test_steps/             # Step type tests
│   ├── integration/            # End-to-end tests
│   └── fixtures/               # Sample YAML workflows
├── examples/                   # Example workflows for users
├── pyproject.toml              # PEP 621 config, pinned deps, tool config
├── Makefile                    # Build/test/lint commands
├── TASKPLAN.md                 # Project roadmap with task definitions
├── CONTRIBUTING.md             # Code style, PR process
└── README.md                   # User-facing documentation
```

---

## Key Abstractions

### BaseStep (`agentrails/steps/base.py`)

Abstract base class for all step types. Every step must implement:

```python
async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult
```

Key fields:
- `id`: Unique step identifier
- `depends_on`: List of step IDs this step waits for
- `condition`: Optional template expression to skip step
- `output_format`: `"json"`, `"toml"`, or `"text"`
- `output_schema`: Optional JSON Schema for output validation
- `max_retries`: Number of retry attempts on failure

### WorkflowState (`agentrails/state.py`)

Immutable nested dictionary with dot-path access:

```python
state = WorkflowState({"tests": {"unit": {"status": "pass"}}})
state.get("tests.unit.status")  # "pass"
new_state = state.set("tests.unit.duration", 12.3)  # returns new copy
```

Key methods:
- `get(path)`, `set(path, value)`: Dot-path access
- `snapshot()`: Deep copy of entire state
- `merge(other, strategy)`: Merge with configurable conflict handling
- `to_json()`, `from_json()`: Serialization
- `validate(schema)`: JSON Schema validation

### WorkflowRunner (`agentrails/engine.py`)

Main execution engine. Walks the DAG, executes steps, checkpoints state:

```python
runner = WorkflowRunner()
result = await runner.run("workflow.yaml")
# result.status: "completed" | "failed" | "cancelled"
# result.final_state: WorkflowState
# result.step_results: dict[str, StepResult]
```

Execution flow:
1. Parse YAML -> `Workflow` object
2. Initialize empty `WorkflowState`
3. Compute topological order from DAG
4. Loop: get ready steps -> execute -> checkpoint -> log events
5. Resume from checkpoint via `runner.resume(run_id)`

### SessionManager (`agentrails/session_manager.py`)

Wraps Claude CLI subprocess lifecycle:

```python
session_manager = SessionManager(max_concurrent_sessions=5)
result = await session_manager.start_session(
    prompt="Generate a plan",
    system_prompt="You are a senior engineer",
    output_format="json",
    permission_mode="bypassPermissions"
)
# result.raw_output: str (full stdout)
# result.parsed_output: dict (from --output-format json)
```

Key features:
- `--bare` flag for deterministic execution (no CLAUDE.md/hooks auto-discovery)
- `--permission-mode` or `--allowedTools` for non-interactive safety
- `--system-prompt` / `--system-prompt-file` for system prompt control
- `--session-id` for session resumption
- Concurrent session limiting via semaphore

### StateStore (`agentrails/storage.py`)

Abstract storage interface for state, events, and step results:

```python
class StateStore(ABC):
    async def save_state(self, workflow_id, run_id, state) -> None
    async def load_state(self, workflow_id, run_id) -> dict | None
    async def append_event(self, event: Event) -> None
    async def load_events(self, workflow_id, run_id) -> list[Event]
    async def save_step_result(self, workflow_id, run_id, result) -> None
    async def load_step_results(self, workflow_id, run_id) -> dict
    async def list_runs(self, workflow_id=None) -> list[RunInfo]
```

Implementations:
- `SqliteStateStore`: Default, zero-config, file-based
- `PostgresStateStore`: Stub for team/enterprise use

### EventLog (`agentrails/event_log.py`)

Event sourcing for deterministic replay:

```python
@dataclass
class Event:
    event_id: str           # UUID
    event_type: Literal[    # All event types
        "workflow_started", "workflow_completed", "workflow_failed",
        "step_started", "step_completed", "step_failed", "step_skipped",
        "state_updated", "checkpoint_saved"
    ]
    step_id: str | None
    data: dict              # Event-specific payload
```

Replay logic:
```python
state, completed_steps, skipped_steps = event_log.replay(events)
# Reconstructs state from state_updated events
# Returns set of completed step IDs (skip these on resume)
```

### OutputParser (`agentrails/output.py`)

Parses step output into structured data:

```python
parsed = OutputParser.parse(
    raw_text="```json\n{\"title\": \"Plan\"}\n```",
    format="json",
    schema={"type": "object", "required": ["title"]}
)
```

Features:
- Extracts JSON/TOML from markdown code fences
- Validates against JSON Schema
- Specialized retry support for agent steps (re-invoke on parse failure)

---

## YAML DSL Reference

### Workflow Structure

```yaml
name: my_workflow

# Optional: workflow-level defaults (inherited by all steps)
defaults:
  output_format: json
  max_retries: 2
  retry_delay_seconds: 5
  retry_backoff: exponential  # fixed | linear | exponential
  system_prompt: |
    You are a precise engineer. Always produce valid JSON.
  permission_mode: bypassPermissions
  model: claude-sonnet-4-6
  timeout: 300

# Optional: state schema validation (enforced after each step)
state:
  type: object
  properties:
    plan: { type: string }
    tests_passed: { type: boolean }
  required: [plan]

steps:
  # ... step definitions
```

### Step Types

#### AgentStep — Claude CLI invocation

```yaml
- id: plan
  type: agent
  prompt: "Analyze {{state.project_dir}} and create a plan"
  system_prompt: |
    You are a senior architect. Respond with JSON matching the schema.
  system_prompt_file: prompts/architect.md  # Alternative: load from file
  subagent: null  # or: slack, jira, gitlab, code-reviewer (invokes --agent flag)
  output_format: json
  output_schema:
    type: object
    properties:
      title: { type: string }
      steps: { type: array, items: { type: string } }
    required: [title, steps]
  session_id: null  # or "{{state.prev_session}}" to resume
  name: planning  # display name (--name flag)
  model: null  # or override: claude-opus-4-1
  max_turns: 10
  allowed_tools: []  # pre-approve specific tools
  permission_mode: null  # or: default|acceptEdits|plan|auto|bypassPermissions
  working_dir: "."
  timeout: 600
  depends_on: []
  condition: null  # template expression to skip step
  max_retries: 0
```

#### ShellStep — Subprocess execution

```yaml
- id: tests
  type: shell
  script: "pytest -q tests/unit"
  working_dir: "{{state.project_dir}}"
  env:
    PYTHONPATH: "./src"
  timeout: 300
  output_format: text  # or json/toml if script outputs structured data
  depends_on: [implement]
```

#### ParallelGroupStep — Concurrent branches

```yaml
- id: all_tests
  type: parallel_group
  depends_on: [implement]
  max_concurrency: 4
  fail_fast: false  # if true: cancel remaining on first failure
  merge_strategy: list_append  # overwrite | list_append | fail_on_conflict
  branches:
    - id: unit
      type: shell
      script: "pytest -q tests/unit"
    - id: integration
      type: shell
      script: "pytest -q tests/integration"
    - id: lint
      type: shell
      script: "ruff check ."
```

#### ConditionalStep — if/then/else branching

```yaml
- id: check_tests
  type: conditional
  depends_on: [tests]
  if: "{{state.tests.all_tests.return_code == 0}}"
  then: [deploy]       # step IDs to enable if true
  else: [fix_code]     # step IDs to enable if false (optional)
```

#### LoopStep — Repeat until condition (stub)

```yaml
- id: retry_loop
  type: loop
  depends_on: [initial_attempt]
  max_iterations: 5
  until: "{{state.retry_loop.latest.return_code == 0}}"
  body:
    - id: fix
      type: agent
      prompt: "Fix errors: {{state.retry_loop.latest.stderr}}"
    - id: retest
      type: shell
      script: "pytest -q"
```

#### HumanStep — Wait for human input (stub)

```yaml
- id: approve_deploy
  type: human
  depends_on: [review]
  message: "Review changes and approve. Results: {{state.tests}}"
  input_schema:
    type: object
    properties:
      approved: { type: boolean }
      comments: { type: string }
    required: [approved]
  timeout: 86400  # 24 hours
```

### Template Expressions

All string fields support Jinja2-style templates:

```yaml
prompt: "Analyze {{state.project_dir}} and create a plan for {{state.feature}}"
condition: "{{state.count > 0 and state.status == 'ready'}}"
script: "pytest {{state.test_file}}"
```

Supported:
- Dot-path access: `{{state.a.b.c}}`
- Comparisons: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Boolean operators: `and`, `or`, `not`
- Filters: `{{state.code | length}}`, `{{state.items | join(', ')}}`

---

## Adding a New Step Type

1. **Create the step class** in `agentrails/steps/`:

```python
# agentrails/steps/my_step.py
from agentrails.steps.base import BaseStep, StepResult, ExecutionContext
from agentrails.state import WorkflowState

class MyStep(BaseStep):
    """My custom step type."""

    def __init__(self, id: str, my_field: str, **kwargs):
        super().__init__(id=id, type="my_step", **kwargs)
        self.my_field = my_field

    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Execute the step."""
        # Implementation
        return StepResult(
            step_id=self.id,
            status="success",
            outputs={"result": "value"},
            raw_output="raw output here",
            duration_seconds=1.23
        )

    def serialize(self) -> dict:
        data = super().serialize()
        data["my_field"] = self.my_field
        return data

    @classmethod
    def deserialize(cls, data: dict) -> "MyStep":
        return cls(id=data["id"], my_field=data["my_field"])
```

2. **Export from `agentrails/steps/__init__.py`**:

```python
from agentrails.steps.my_step import MyStep

__all__ = [..., "MyStep"]
```

3. **Add parser support** in `agentrails/dsl_parser.py`:

```python
# In _create_step() function:
elif step_type == "my_step":
    step_class = MyStep
    # Read step-type-specific fields from step_data
```

4. **Write tests** in `tests/test_steps/test_my_step.py`:

```python
import pytest
from agentrails.steps.my_step import MyStep

async def test_my_step_execute():
    step = MyStep(id="test", my_field="value")
    # ... set up state and context
    result = await step.execute(state, context)
    assert result.status == "success"
```

5. **Update documentation** (this file, TASKPLAN.md, README.md) with YAML examples.

---

## Architecture: Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  agentrails run workflow.yaml                                   │
├─────────────────────────────────────────────────────────────────┤
│  1. CLI (cli.py)                                                │
│     - Parse CLI args                                            │
│     - Create WorkflowRunner                                     │
│     - Call runner.run()                                         │
├─────────────────────────────────────────────────────────────────┤
│  2. Parser (dsl_parser.py)                                      │
│     - Load YAML                                                 │
│     - Validate (cycles, missing deps, required fields)          │
│     - Return Workflow object (name, steps, dag, state_schema)   │
├─────────────────────────────────────────────────────────────────┤
│  3. Engine (engine.py)                                          │
│     - Initialize WorkflowState (empty or from checkpoint)       │
│     - Log workflow_started event                                │
│     - Loop:                                                     │
│       a. Get ready steps (DAG.ready_steps())                    │
│       b. For each: evaluate condition, render templates         │
│       c. Execute step (await step.execute())                    │
│       d. Validate output (OutputParser.parse())                 │
│       e. Validate state (WorkflowState.validate())              │
│       f. Merge outputs into state                               │
│       g. Checkpoint (save_state, append_event)                  │
│       h. Log step_completed / step_failed                       │
│     - Log workflow_completed / workflow_failed                  │
├─────────────────────────────────────────────────────────────────┤
│  4. Steps (steps/*.py)                                          │
│     - AgentStep: SessionManager.start_session()                 │
│     - ShellStep: asyncio.create_subprocess_shell()              │
│     - ParallelGroupStep: asyncio.gather() with semaphore        │
│     - ConditionalStep: evaluate condition, mark then/else       │
├─────────────────────────────────────────────────────────────────┤
│  5. Storage (storage_sqlite.py)                                 │
│     - Save state to runs table                                  │
│     - Append events to events table (append-only)               │
│     - Save step results to step_results table                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing Conventions

### Test Types

| Type | Location | Markers | Description |
|------|----------|---------|-------------|
| Unit | `tests/test_*.py` | None | Test single module in isolation |
| Integration | `tests/integration/` | `@pytest.mark.integration` | End-to-end workflow execution |
| Step tests | `tests/test_steps/` | None | Test specific step types |

### Writing Tests

```python
# tests/test_mymodule.py
import pytest
from agentrails.mymodule import MyClass

def test_something(sample_state, tmp_state_dir):
    # Use fixtures from conftest.py
    obj = MyClass()
    assert obj.do_something() == "expected"

@pytest.mark.integration
async def test_end_to_end(mock_claude_cli):
    # Integration test with mocked Claude CLI
    from agentrails.engine import WorkflowRunner
    runner = WorkflowRunner()
    result = await runner.run("tests/fixtures/my_workflow.yaml")
    assert result.status == "completed"
```

### Running Tests

```bash
# Unit tests only (fast, no subprocess)
make test

# All tests including integration (slower)
make test-all

# With coverage
make test-cov
```

---

## Configuration Resolution

Config values resolved in order (highest priority wins):

1. **CLI flags** (via Click context)
2. **Environment variables** (`AGENTRAILS_*` prefix)
3. **`pyproject.toml`** (`[tool.agentrails]` section)
4. **Hardcoded defaults**

```python
# agentrails/config.py
@dataclass
class Config:
    log_level: str = "INFO"              # AGENTRAILS_LOG_LEVEL
    log_format: str = "json"             # AGENTRAILS_LOG_FORMAT
    storage_backend: str = "sqlite"      # AGENTRAILS_STORAGE
    db_url: str | None = None            # AGENTRAILS_DB_URL
    state_dir: str = ".agentrails"       # AGENTRAILS_STATE_DIR
    max_concurrent_sessions: int = 5     # AGENTRAILS_MAX_SESSIONS
    default_permission_mode: str = "bypassPermissions"
    claude_cli_path: str = "claude"      # AGENTRAILS_CLAUDE_PATH
```

---

## Common Patterns

### Logging

```python
from agentrails.utils import get_logger

logger = get_logger(__name__)
logger.info("Something happened", extra={"step_id": "plan", "workflow_id": "wf123"})
```

### Template Rendering

```python
from agentrails.template import render_template

rendered = render_template("Hello {{state.name}}", state)
# Raises TemplateRenderError if variable undefined
```

### Event Logging

```python
from agentrails.event_log import Event

event = Event(
    event_id=str(uuid.uuid4()),
    workflow_id="wf123",
    run_id="run456",
    event_type="step_completed",
    step_id="plan",
    data={"duration": 12.3, "status": "success"}
)
await state_store.append_event(event)
```

---

## Troubleshooting

### Claude CLI not found

```
Error: Claude CLI not found. Install it from https://claude.ai/download
```

Install Claude CLI: `npm install -g @anthropic-ai/claude-cli`

### Version too old

```
Error: Claude CLI version X.Y.Z is too old. AgentRails requires >= A.B.C.
```

Upgrade: `npm install -g @anthropic-ai/claude-cli@latest`

### Cycle detected in workflow

```
ValidationError: Cycle detected in workflow DAG: step1 -> step2 -> step3 -> step1
```

Fix `depends_on` fields to remove the cycle.

### Missing dependency

```
ValidationError: Step 'deploy' depends on 'build', which does not exist
```

Check the `depends_on` field — the referenced step ID doesn't exist.

### Parse failure on agent output

```
OutputParseError: Could not parse agent output as JSON
```

Agent output didn't contain valid JSON. Check the agent's prompt and system_prompt for format instructions.

---

## See Also

- `TASKPLAN.md`: Full project roadmap with task definitions
- `CONTRIBUTING.md`: Code style, PR process, development setup
- `README.md`: User-facing quick start and examples
- `tests/conftest.py`: Shared pytest fixtures
