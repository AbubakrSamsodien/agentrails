"""Tests for YAML DSL parser."""

import pytest

from agentrails.dsl_parser import ValidationError, parse_workflow


def test_parse_linear_workflow(fixtures_dir):
    """Test parsing a linear workflow."""
    wf = parse_workflow(fixtures_dir / "linear.yaml")

    assert wf.name == "linear_test"
    assert len(wf.steps) == 3
    assert wf.dag.topological_order() == ["step1", "step2", "step3"]


def test_parse_parallel_workflow(fixtures_dir):
    """Test parsing a workflow with parallel branches."""
    wf = parse_workflow(fixtures_dir / "parallel.yaml")

    assert wf.name == "parallel_test"
    assert len(wf.steps) == 3  # setup, tests, deploy


def test_cycle_detection(fixtures_dir):
    """Test that cycles are detected in workflow YAML."""
    with pytest.raises(ValidationError, match="cycle"):
        parse_workflow(fixtures_dir / "cyclic.yaml")


def test_missing_dependency(fixtures_dir):
    """Test that missing dependencies are detected."""
    with pytest.raises(ValidationError, match="does not exist"):
        parse_workflow(fixtures_dir / "bad_dep.yaml")


def test_parse_with_state_schema(fixtures_dir):
    """Test parsing workflow with state schema."""
    wf = parse_workflow(fixtures_dir / "smoke.yaml")
    assert wf.name == "smoke_test"


def test_parse_conditional_workflow(fixtures_dir):
    """Test parsing a conditional workflow."""
    wf = parse_workflow(fixtures_dir / "conditional.yaml")

    assert wf.name == "conditional_test"
    assert len(wf.steps) == 4  # check, branch, success_path, failure_path

    # Find the conditional step
    conditional_step = next(s for s in wf.steps if s.id == "branch")
    assert conditional_step.type == "conditional"
    assert conditional_step.condition == "{{state.check.return_code == 0}}"


def test_parse_loop_workflow(fixtures_dir):
    """Test parsing a workflow with a loop."""
    wf = parse_workflow(fixtures_dir / "loop.yaml")

    assert wf.name == "loop_test"
    assert len(wf.steps) == 2  # setup, retry

    # Find the loop step
    loop_step = next(s for s in wf.steps if s.id == "retry")
    assert loop_step.type == "loop"
    assert loop_step.until == "{{state.retry.latest.return_code == 0}}"
    assert loop_step.max_iterations == 3


def test_duplicate_step_ids(fixtures_dir, tmp_path):
    """Test that duplicate step IDs are detected."""
    workflow_file = tmp_path / "dup.yaml"
    workflow_file.write_text("""
name: dup_test
steps:
  - id: step1
    type: shell
    script: "echo 1"
  - id: step1
    type: shell
    script: "echo 2"
""")

    with pytest.raises(ValidationError, match="Duplicate step ID"):
        parse_workflow(workflow_file)


def test_invalid_output_format(fixtures_dir, tmp_path):
    """Test that invalid output_format is detected."""
    # Note: This validation would need to be added to the parser
    # For now, the parser accepts any value - we could add validation later
    workflow_file = tmp_path / "bad_format.yaml"
    workflow_file.write_text("""
name: bad_format_test
steps:
  - id: step1
    type: shell
    script: "echo 1"
    output_format: xml
""")

    # Parser currently doesn't validate output_format values
    # This test documents that behavior
    wf = parse_workflow(workflow_file)
    assert wf.steps[0].output_format == "xml"


def test_missing_required_field_shell(fixtures_dir, tmp_path):
    """Test that missing required field (script) is detected for shell step."""
    workflow_file = tmp_path / "missing_script.yaml"
    workflow_file.write_text("""
name: missing_script_test
steps:
  - id: step1
    type: shell
""")

    with pytest.raises(ValidationError, match="missing 'script' field"):
        parse_workflow(workflow_file)


def test_missing_required_field_agent(fixtures_dir, tmp_path):
    """Test that missing required field (prompt) is detected for agent step."""
    workflow_file = tmp_path / "missing_prompt.yaml"
    workflow_file.write_text("""
name: missing_prompt_test
steps:
  - id: step1
    type: agent
""")

    with pytest.raises(ValidationError, match="missing 'prompt' field"):
        parse_workflow(workflow_file)


def test_unknown_step_type(fixtures_dir, tmp_path):
    """Test that unknown step type is detected."""
    workflow_file = tmp_path / "unknown_type.yaml"
    workflow_file.write_text("""
name: unknown_type_test
steps:
  - id: step1
    type: magic
""")

    with pytest.raises(ValidationError, match="Unknown step type"):
        parse_workflow(workflow_file)


def test_parse_with_defaults(fixtures_dir, tmp_path):
    """Test parsing workflow with defaults."""
    workflow_file = tmp_path / "with_defaults.yaml"
    workflow_file.write_text("""
name: defaults_test
defaults:
  output_format: json
  max_retries: 3
  timeout: 300
steps:
  - id: step1
    type: shell
    script: "echo 1"
  - id: step2
    type: shell
    script: "echo 2"
    output_format: text
""")

    wf = parse_workflow(workflow_file)

    # Check defaults were parsed
    assert wf.defaults.output_format == "json"
    assert wf.defaults.max_retries == 3
    assert wf.defaults.timeout == 300

    # Check first step inherited defaults
    assert wf.steps[0].output_format == "json"
    assert wf.steps[0].max_retries == 3

    # Check second step overrode defaults
    assert wf.steps[1].output_format == "text"
    assert wf.steps[1].max_retries == 3  # still inherited


def test_file_not_found(tmp_path):
    """Test that missing file raises ValidationError."""
    with pytest.raises(ValidationError, match="not found"):
        parse_workflow(tmp_path / "nonexistent.yaml")


def test_empty_file(tmp_path):
    """Test that empty file raises ValidationError."""
    workflow_file = tmp_path / "empty.yaml"
    workflow_file.write_text("")

    with pytest.raises(ValidationError, match="Empty workflow"):
        parse_workflow(workflow_file)


def test_missing_name(tmp_path):
    """Test that missing name raises ValidationError."""
    workflow_file = tmp_path / "no_name.yaml"
    workflow_file.write_text("""
steps:
  - id: step1
    type: shell
    script: "echo 1"
""")

    with pytest.raises(ValidationError, match="must have a 'name' field"):
        parse_workflow(workflow_file)


def test_missing_steps(tmp_path):
    """Test that missing steps raises ValidationError."""
    workflow_file = tmp_path / "no_steps.yaml"
    workflow_file.write_text("""
name: no_steps_test
""")

    with pytest.raises(ValidationError, match="must have a 'steps' field"):
        parse_workflow(workflow_file)


def test_parallel_empty_branches(tmp_path):
    """Test that parallel group with no branches raises ValidationError."""
    workflow_file = tmp_path / "empty_parallel.yaml"
    workflow_file.write_text("""
name: empty_parallel_test
steps:
  - id: parallel
    type: parallel_group
    branches: []
""")

    with pytest.raises(ValidationError, match="has no branches"):
        parse_workflow(workflow_file)


def test_loop_empty_body(tmp_path):
    """Test that loop with no body raises ValidationError."""
    workflow_file = tmp_path / "empty_loop.yaml"
    workflow_file.write_text("""
name: empty_loop_test
steps:
  - id: loop
    type: loop
    until: "{{state.x > 0}}"
    body: []
""")

    with pytest.raises(ValidationError, match="has no body"):
        parse_workflow(workflow_file)


def test_loop_missing_until(tmp_path):
    """Test that loop without until condition raises ValidationError."""
    workflow_file = tmp_path / "no_until.yaml"
    workflow_file.write_text("""
name: no_until_test
steps:
  - id: loop
    type: loop
    body:
      - id: step1
        type: shell
        script: "echo 1"
""")

    with pytest.raises(ValidationError, match="missing 'until' field"):
        parse_workflow(workflow_file)


def test_conditional_missing_if(tmp_path):
    """Test that conditional without if condition raises ValidationError."""
    workflow_file = tmp_path / "no_if.yaml"
    workflow_file.write_text("""
name: no_if_test
steps:
  - id: cond
    type: conditional
    then: [step1]
""")

    with pytest.raises(ValidationError, match="missing 'if' field"):
        parse_workflow(workflow_file)


def test_defaults_system_prompt(tmp_path):
    """Test that defaults.system_prompt is inherited by agent steps."""
    workflow_file = tmp_path / "defaults_sysprompt.yaml"
    workflow_file.write_text("""
name: defaults_test
defaults:
  system_prompt: |
    You are a helpful assistant. Always respond with JSON.
  model: claude-sonnet-4
  output_format: json
steps:
  - id: plan
    type: agent
    prompt: "Create a plan"
  - id: implement
    type: agent
    prompt: "Implement the plan"
""")

    wf = parse_workflow(workflow_file)

    # Both agent steps should inherit the defaults
    assert len(wf.steps) == 2
    plan_step = wf.steps[0]
    implement_step = wf.steps[1]

    assert plan_step.system_prompt == "You are a helpful assistant. Always respond with JSON.\n"
    assert plan_step.model == "claude-sonnet-4"
    assert plan_step.output_format == "json"

    assert (
        implement_step.system_prompt == "You are a helpful assistant. Always respond with JSON.\n"
    )
    assert implement_step.model == "claude-sonnet-4"
    assert implement_step.output_format == "json"


def test_step_level_system_prompt_override(tmp_path):
    """Test that step-level system_prompt overrides defaults."""
    workflow_file = tmp_path / "override_sysprompt.yaml"
    workflow_file.write_text("""
name: override_test
defaults:
  system_prompt: |
    Default system prompt
  model: claude-sonnet-4
steps:
  - id: plan
    type: agent
    prompt: "Create a plan"
    system_prompt: |
      Custom prompt for planning
  - id: implement
    type: agent
    prompt: "Implement"
""")

    wf = parse_workflow(workflow_file)

    plan_step = wf.steps[0]
    implement_step = wf.steps[1]

    # Plan step should have custom prompt
    assert plan_step.system_prompt == "Custom prompt for planning\n"

    # Implement step should inherit default
    assert implement_step.system_prompt == "Default system prompt\n"


def test_defaults_all_fields(tmp_path):
    """Test that all defaults fields propagate correctly."""
    workflow_file = tmp_path / "all_defaults.yaml"
    workflow_file.write_text("""
name: all_defaults_test
defaults:
  system_prompt: "Default prompt"
  model: claude-opus-4
  output_format: json
  max_retries: 3
  timeout: 600
  permission_mode: bypassPermissions
  allowed_tools: ["Read", "Write"]
steps:
  - id: plan
    type: agent
    prompt: "Plan"
""")

    wf = parse_workflow(workflow_file)
    step = wf.steps[0]

    assert step.system_prompt == "Default prompt"
    assert step.model == "claude-opus-4"
    assert step.output_format == "json"
    assert step.max_retries == 3
    assert step.timeout_seconds == 600
    assert step.permission_mode == "bypassPermissions"
    assert step.allowed_tools == ["Read", "Write"]


def test_defaults_partial_override(tmp_path):
    """Test that step can override some defaults while inheriting others."""
    workflow_file = tmp_path / "partial_override.yaml"
    workflow_file.write_text("""
name: partial_override_test
defaults:
  system_prompt: "Default"
  model: claude-sonnet-4
  output_format: json
  max_retries: 2
steps:
  - id: plan
    type: agent
    prompt: "Plan"
    model: claude-opus-4
    max_retries: 5
""")

    wf = parse_workflow(workflow_file)
    step = wf.steps[0]

    # Overridden fields
    assert step.model == "claude-opus-4"
    assert step.max_retries == 5

    # Inherited fields
    assert step.system_prompt == "Default"
    assert step.output_format == "json"


def test_defaults_no_system_prompt(tmp_path):
    """Test that missing system_prompt results in None."""
    workflow_file = tmp_path / "no_sysprompt.yaml"
    workflow_file.write_text("""
name: no_sysprompt_test
defaults:
  model: claude-sonnet-4
steps:
  - id: plan
    type: agent
    prompt: "Plan"
""")

    wf = parse_workflow(workflow_file)
    step = wf.steps[0]

    assert step.system_prompt is None
    assert step.model == "claude-sonnet-4"


def test_system_prompt_file(fixtures_dir):
    """Test loading system prompt from external file."""
    wf = parse_workflow(fixtures_dir / "system_prompt_file.yaml")

    assert wf.name == "system_prompt_file_test"
    assert len(wf.steps) == 1

    step = wf.steps[0]
    assert step.type == "agent"
    assert step.system_prompt is not None
    assert "senior software architect" in step.system_prompt.lower()


def test_system_prompt_file_mutual_exclusivity(tmp_path):
    """Test that system_prompt and system_prompt_file are mutually exclusive."""
    workflow_file = tmp_path / "mutual_exclusive.yaml"
    workflow_file.write_text("""
name: mutual_exclusive_test
steps:
  - id: plan
    type: agent
    prompt: "Plan"
    system_prompt: "You are helpful"
    system_prompt_file: "prompts/architect.md"
""")

    with pytest.raises(ValidationError, match="cannot have both"):
        parse_workflow(workflow_file)


def test_system_prompt_file_not_found(tmp_path):
    """Test error when system_prompt_file doesn't exist."""
    workflow_file = tmp_path / "missing_file.yaml"
    workflow_file.write_text("""
name: missing_file_test
steps:
  - id: plan
    type: agent
    prompt: "Plan"
    system_prompt_file: "nonexistent/prompt.md"
""")

    with pytest.raises(ValidationError, match="not found"):
        parse_workflow(workflow_file)
