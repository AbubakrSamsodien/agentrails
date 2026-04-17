# AgentRails Workflow Authoring Guide

> Complete reference for writing AgentRails workflows

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Workflow Structure](#workflow-structure)
3. [Step Types](#step-types)
4. [Template Expressions](#template-expressions)
5. [State Management](#state-management)
6. [Error Handling & Retries](#error-handling--retries)
7. [Best Practices](#best-practices)
8. [Examples](#examples)
9. [System Prompts](#system-prompts)

---

## Quick Start

Create a workflow YAML file:

```yaml
name: my_first_workflow

steps:
  - id: hello
    type: shell
    script: "echo 'Hello from AgentRails!'"

  - id: plan
    type: agent
    prompt: "Create a plan for implementing a new feature"
    output_format: json
    depends_on: [hello]
```

Run it:

```bash
agentrails run workflow.yaml
```

---

## Workflow Structure

### Top-Level Fields

```yaml
name: my_workflow                    # Required: workflow identifier

# Optional: workflow-level defaults (inherited by all steps)
defaults:
  output_format: json
  max_retries: 2
  retry_delay_seconds: 5
  retry_backoff: exponential         # fixed | linear | exponential
  system_prompt: |
    You are a precise engineer.
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

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique workflow identifier |
| `defaults` | object | No | Default settings for all steps |
| `state` | object | No | JSON Schema for state validation |
| `steps` | array | Yes | List of step definitions |

---

## Step Types

### AgentStep — Claude CLI Invocation

Executes a task using Claude Code CLI.

```yaml
- id: plan
  type: agent
  prompt: "Analyze {{state.project_dir}} and create a plan"
  system_prompt: |
    You are a senior architect. Respond with JSON matching the schema.
  system_prompt_file: prompts/architect.md  # Alternative: load from file
  output_format: json
  output_schema:
    type: object
    properties:
      title: { type: string }
      steps: { type: array, items: { type: string } }
    required: [title, steps]
  session_id: null  # or "{{state.prev_session}}" to resume
  name: planning  # display name
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

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `prompt` | string | — | **Required.** Prompt to send to Claude |
| `system_prompt` | string | — | System prompt (overrides default) |
| `system_prompt_file` | string | — | Path to file containing system prompt |
| `output_format` | string | `text` | `json`, `toml`, or `text` |
| `output_schema` | object | — | JSON Schema for output validation |
| `session_id` | string | `null` | Resume existing session |
| `name` | string | — | Display name for progress output |
| `model` | string | `null` | Model override |
| `max_turns` | int | `10` | Maximum agent turns |
| `allowed_tools` | array | `[]` | Pre-approved tools |
| `permission_mode` | string | `bypassPermissions` | Permission level |
| `working_dir` | string | `.` | Working directory |
| `timeout` | int | `600` | Timeout in seconds |

**State Access:**
```yaml
prompt: "Fix errors from {{state.prev_step.stderr}}"
```

After execution:
```python
state.plan.outputs.title  # "Implementation Plan"
state.plan.outputs.steps  # ["Step 1", "Step 2"]
state.plan.raw_output     # Full Claude response
```

**System Prompts:** The `system_prompt` field composes with workflow defaults and the AgentRails base prompt. For details on how prompts layer and best practices, see [Prompt Craft Guide](./prompt-guide.md).

---

### ShellStep — Subprocess Execution

Executes a shell command.

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
  condition: "{{state.plan.status == 'ready'}}"
```

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `script` | string | — | **Required.** Shell command to execute |
| `working_dir` | string | `.` | Working directory |
| `env` | object | — | Additional environment variables |
| `timeout` | int | `300` | Timeout in seconds |
| `output_format` | string | `text` | Parse stdout as `json`, `toml`, or `text` |

**State Access:**
```python
state.tests.outputs.return_code  # 0
state.tests.outputs.stdout       # "10 passed"
state.tests.outputs.stderr       # ""
```

---

### ParallelGroupStep — Concurrent Branches

Executes multiple branches concurrently.

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

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `branches` | array | — | **Required.** List of branch steps |
| `max_concurrency` | int | `4` | Maximum concurrent branches |
| `fail_fast` | bool | `false` | Cancel on first failure |
| `merge_strategy` | string | `overwrite` | How to merge branch outputs |

**State Access:**
```python
state.all_tests.unit.outputs.return_code    # 0
state.all_tests.integration.outputs.stdout  # "50 passed"
```

---

### ConditionalStep — If/Then/Else Branching

Enables or disables downstream steps based on a condition.

```yaml
- id: check_tests
  type: conditional
  depends_on: [tests]
  if: "{{state.tests.all_tests.return_code == 0}}"
  then: [deploy]       # step IDs to enable if true
  else: [fix_code]     # step IDs to enable if false (optional)
```

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `if` | string | — | **Required.** Template expression |
| `then` | array | — | **Required.** Step IDs to enable if true |
| `else` | array | — | Step IDs to enable if false |

**State Access:**
```python
state.check_tests.outputs.branch_taken     # "then" or "else"
state.check_tests.outputs.condition_value  # true or false
```

---

### LoopStep — Repeat Until Condition

Repeats a body of steps until a condition is met.

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

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_iterations` | int | `5` | Maximum loop iterations |
| `until` | string | — | **Required.** Exit condition |
| `body` | array | — | **Required.** Steps to execute per iteration |

**State Access:**
```python
state.retry_loop.latest.return_code      # Latest iteration result
state.retry_loop.iterations[0]           # First iteration outputs
state.retry_loop.iteration_count         # Total iterations executed
```

---

### HumanStep — Wait for Human Input

Pauses workflow and waits for human input.

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

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `message` | string | — | **Required.** Message to show human |
| `input_schema` | object | — | JSON Schema for input validation |
| `timeout` | int | `86400` | Timeout in seconds (24h default) |

**Input Format (JSON via stdin):**
```json
{"approved": true, "comments": "Looks good!"}
```

**State Access:**
```python
state.approve_deploy.outputs.approved   # true
state.approve_deploy.outputs.comments   # "Looks good!"
```

---

## Template Expressions

All string fields support Jinja2-style templates.

### Syntax

```yaml
prompt: "Analyze {{state.project_dir}} and create a plan for {{state.feature}}"
condition: "{{state.count > 0 and state.status == 'ready'}}"
script: "pytest {{state.test_file}}"
```

### Supported Operations

**Dot-path access:**
```yaml
{{state.a.b.c}}
```

**Comparisons:**
```yaml
{{state.count == 0}}
{{state.status != "failed"}}
{{state.value > 10}}
{{state.value <= 100}}
```

**Boolean operators:**
```yaml
{{state.a and state.b}}
{{state.x or state.y}}
{{not state.disabled}}
```

**Filters:**
```yaml
{{state.code | length}}
{{state.items | join(', ')}}
{{state.name | upper}}
```

### State Paths

Access step outputs:
```yaml
{{state.step_id.outputs.field_name}}
```

Access nested outputs:
```yaml
{{state.plan.outputs.steps[0]}}
{{state.tests.unit.outputs.return_code}}
```

---

## State Management

### State Structure

State is a nested dictionary. Each step's outputs are stored under its step ID:

```python
{
  "step_id": {
    "outputs": {...},
    "raw_output": "...",
    "duration": 12.3
  }
}
```

### State Schema Validation

Define a schema to validate state after each step:

```yaml
state:
  type: object
  properties:
    plan:
      type: object
      properties:
        title: { type: string }
        steps: { type: array }
      required: [title, steps]
    tests:
      type: object
      properties:
        passed: { type: boolean }
  required: [plan]
```

If validation fails, the workflow stops with a clear error message.

### Merge Strategies

For parallel steps, configure how outputs merge:

```yaml
- id: tests
  type: parallel_group
  merge_strategy: list_append  # or: overwrite | fail_on_conflict
```

- `overwrite`: Later values replace earlier ones
- `list_append`: Conflicting values become arrays
- `fail_on_conflict`: Error if any conflict occurs

---

## Error Handling & Retries

### Retry Configuration

```yaml
- id: flaky_api
  type: agent
  prompt: "Call the API"
  max_retries: 3
  retry_delay_seconds: 5
  retry_backoff: exponential  # or: fixed | linear
```

**Backoff Strategies:**

| Strategy | Delays (5s base) |
|----------|------------------|
| `fixed` | 5s, 5s, 5s |
| `linear` | 5s, 10s, 15s |
| `exponential` | 5s, 10s, 20s |

### Conditional Error Handling

```yaml
- id: check_result
  type: conditional
  depends_on: [api_call]
  if: "{{state.api_call.outputs.status == 'error'}}"
  then: [handle_error]
  else: [continue_normal]
```

### Timeout Handling

```yaml
- id: long_running
  type: shell
  script: "npm run build"
  timeout: 600  # 10 minutes
  max_retries: 1
```

---

## Best Practices

### 1. Use Descriptive Step IDs

```yaml
# Good
- id: validate_schema
- id: run_unit_tests
- id: deploy_to_staging

# Avoid
- id: step1
- id: do_things
```

### 2. Validate Agent Output

Always use `output_schema` for agent steps that produce structured data:

```yaml
- id: plan
  type: agent
  output_format: json
  output_schema:
    type: object
    properties:
      title: { type: string }
      steps: { type: array, items: { type: string } }
    required: [title, steps]
```

### 3. Set Reasonable Timeouts

Prevent runaway steps:

```yaml
- id: tests
  type: shell
  timeout: 300  # 5 minutes for tests
- id: build
  type: shell
  timeout: 600  # 10 minutes for build
```

### 4. Use Defaults for Consistency

```yaml
defaults:
  output_format: json
  max_retries: 2
  permission_mode: bypassPermissions
  timeout: 300
```

### 5. Handle Failures with Conditionals

```yaml
- id: tests
  type: shell
  script: "pytest"

- id: check_tests
  type: conditional
  depends_on: [tests]
  if: "{{state.tests.outputs.return_code == 0}}"
  then: [deploy]
  else: [notify_team]
```

### 6. Organize Complex Workflows

Break large workflows into logical phases:

```yaml
steps:
  # Phase 1: Analysis
  - id: analyze_codebase
  - id: generate_plan

  # Phase 2: Implementation
  - id: implement
  - id: run_tests

  # Phase 3: Deployment
  - id: deploy
```

---

## Examples

### Linear Workflow

```yaml
name: linear_example

steps:
  - id: setup
    type: shell
    script: "pip install -r requirements.txt"

  - id: tests
    type: shell
    script: "pytest -q"
    depends_on: [setup]

  - id: deploy
    type: shell
    script: "./deploy.sh"
    depends_on: [tests]
```

### Parallel Tests

```yaml
name: parallel_tests

steps:
  - id: all_tests
    type: parallel_group
    max_concurrency: 3
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

  - id: deploy
    type: shell
    script: "./deploy.sh"
    depends_on: [all_tests]
```

### Retry Loop

```yaml
name: retry_on_failure

steps:
  - id: initial_attempt
    type: shell
    script: "npm run build"

  - id: retry_loop
    type: loop
    depends_on: [initial_attempt]
    max_iterations: 3
    until: "{{state.retry_loop.latest.return_code == 0}}"
    body:
      - id: fix_errors
        type: agent
        prompt: "Fix build errors: {{state.retry_loop.latest.stderr}}"
      - id: rebuild
        type: shell
        script: "npm run build"
```

### Human Approval

```yaml
name: deploy_with_approval

steps:
  - id: build
    type: shell
    script: "npm run build"

  - id: tests
    type: shell
    script: "npm test"
    depends_on: [build]

  - id: approve
    type: human
    depends_on: [tests]
    message: |
      Build and tests passed. Approve deployment?
      Results: {{state.tests}}
    input_schema:
      type: object
      properties:
        approved: { type: boolean }
        notes: { type: string }
      required: [approved]

  - id: deploy
    type: shell
    script: "./deploy.sh"
    depends_on: [approve]
    condition: "{{state.approve.outputs.approved == true}}"
```

---

## CLI Reference

```bash
# Run a workflow
agentrails run workflow.yaml

# Run with interactive display
agentrails run workflow.yaml --interactive

# Validate workflow YAML
agentrails validate workflow.yaml

# Visualize workflow DAG
agentrails visualize workflow.yaml --format mermaid
agentrails visualize workflow.yaml --format ascii

# Check run status
agentrails status <run_id>

# View event log
agentrails logs <run_id>

# Export final state
agentrails export <run_id> --format json

# Resume failed workflow
agentrails resume <run_id>
```

---

## Troubleshooting

### "Step X depends on Y, which does not exist"

Check the `depends_on` field — the referenced step ID must match exactly.

### "Cycle detected in workflow DAG"

Your `depends_on` fields create a circular dependency. Review and break the cycle.

### "Could not parse agent output as JSON"

Agent didn't return valid JSON. Add clearer instructions in `system_prompt`:

```yaml
system_prompt: |
  Respond ONLY with valid JSON matching this schema. No explanations.
```

### "State validation failed"

Step output doesn't match the workflow's `state` schema. Check field names and types.

### Workflow hangs on agent step

Claude CLI is waiting for permission. Add `permission_mode`:

```yaml
permission_mode: bypassPermissions
```

---

## System Prompts

AgentRails uses a **four-layer composition model** for system prompts. When you set `system_prompt` on an agent step, it composes with:

1. **AgentRails Base Prompt** — Framework-provided operational instructions (tools, safety, output discipline)
2. **Workflow Defaults** — Project-wide context from `defaults.system_prompt`
3. **Step Override** — Your step's `system_prompt` field
4. **Auto-Injected Context** — Output schema and pipeline position (added automatically)

For complete guidance on prompt composition, best practices, and the `raw_system_prompt` escape hatch, see the dedicated [**Prompt Craft Guide**](./prompt-guide.md).

---

## See Also

- `README.md` — Installation and quick start
- `examples/` — Example workflows
- `tests/fixtures/` — Test workflows
- [`prompt-guide.md`](./prompt-guide.md) — System prompt composition and best practices
