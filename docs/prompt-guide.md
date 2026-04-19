# Prompt Craft Guide for AgentRails

> How system prompts compose, when to use each layer, and best practices for writing effective prompts.

---

## 1. How System Prompts Compose

AgentRails uses a **four-layer composition model** to assemble the final system prompt sent to agent steps at runtime. This ensures agents always receive operational instructions while giving workflow authors fine-grained control.

```
┌─────────────────────────────────────────────┐
│  Layer 1: AgentRails Base Prompt            │  ← Framework-provided, always present
│  (embedded in package, versioned)           │
├─────────────────────────────────────────────┤
│  Layer 2: Workflow Defaults                 │  ← Author-provided via defaults.system_prompt
│  (project context, conventions)             │
├─────────────────────────────────────────────┤
│  Layer 3: Step Override                     │  ← Author-provided via step system_prompt
│  (task-specific instructions)               │
├─────────────────────────────────────────────┤
│  Layer 4: Auto-Injected Context             │  ← Engine-generated at runtime
│  (output schema, pipeline position)         │
└─────────────────────────────────────────────┘
```

**Final composed prompt:** `Layer 1 + Layer 2 + Layer 3 + Layer 4`

Layers are concatenated with section separators (`\n\n---\n\n`). Empty layers are skipped.

### What the Agent Actually Sees

Here's a complete example of what an agent receives when all four layers are present:

```markdown
You are an AI agent executing a step in an automated workflow pipeline. You operate headlessly...

# Tools and file operations
- Use dedicated tools for file operations instead of shell commands...

# Working with code
- Read existing code before modifying it...

# Scope and safety
- Consider the reversibility and blast radius of your actions...

# Output discipline
- When a structured output format is specified...

# Work style
- Go straight to the point...

---

# Workflow context

You are working on a Python web application using FastAPI and SQLAlchemy.
The codebase uses type hints, Google-style docstrings, and pytest.
Source code is in src/, tests in tests/.

---

# Task instructions

Analyze the codebase and create an implementation plan.
Focus on identifying the files that need to change and the order of changes.

---

# Required output format

Your response must be valid JSON conforming to this schema:

```json
{
  "type": "object",
  "properties": {
    "summary": {"type": "string"},
    "steps": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "file": {"type": "string"},
          "action": {"type": "string", "enum": ["create", "modify", "delete"]},
          "description": {"type": "string"}
        },
        "required": ["file", "action", "description"]
      }
    }
  },
  "required": ["summary", "steps"]
}
```

Produce only the JSON object. Do not include any text before or after it.

---

# Pipeline context

- Workflow: feature_implementation
- Current step: plan
- Steps completed: none
- This step depends on: nothing (first step)
```

---

## 2. When to Use Each Layer

| Layer | Use When | Example |
|-------|----------|---------|
| **Base (Layer 1)** | Always — provides operational guardrails. No action needed. | Built-in, cannot be disabled (unless using `raw_system_prompt`) |
| **Workflow Defaults (Layer 2)** | Project-wide conventions apply to all steps. | Code style, framework info, repo structure |
| **Step Override (Layer 3)** | A step needs specific persona or task instructions. | "You are a security auditor. Focus on auth flows." |
| **Auto-Injected (Layer 4)** | Always — provides output schema and pipeline awareness. No action needed. | Output format, step ID, dependency info |

### Workflow Defaults (Layer 2)

Use `defaults.system_prompt` in your YAML for project-wide context:

```yaml
name: feature_implementation

defaults:
  system_prompt: |
    You are working on a Python web application using FastAPI and SQLAlchemy.
    The codebase uses: type hints, Google-style docstrings, pytest for testing.
    Source code is in src/, tests in tests/.

steps:
  - id: plan
    type: agent
    prompt: "Plan the implementation"
```

### Step Override (Layer 3)

Use step-level `system_prompt` for task-specific instructions:

```yaml
- id: security_audit
  type: agent
  system_prompt: |
    You are a security auditor. Focus on authentication and authorization flows.
    Look for: SQL injection, XSS, CSRF, and privilege escalation vulnerabilities.
  prompt: "Audit {{state.plan.files}}"
```

---

## 3. Prompt Writing Best Practices

### Do

- **Keep prompts focused on the task**, not on how to use tools (the base prompt handles that).
- **Trust the output schema auto-injection** — don't repeat schema definitions in your prompt.
- **Use `{{state.xxx}}` templates** to reference upstream step results.
- **Write prompts that describe the *what* and *why***, not the *how*.
- **Keep step prompts under 200 words** where possible — every word costs context.

### Don't

- **Don't include tool usage instructions** (Read, Edit, Bash) — the base prompt covers this.
- **Don't include safety/reversibility instructions** — the base prompt covers this.
- **Don't duplicate output format instructions** if you've defined `output_schema` in YAML.
- **Don't write multi-thousand-word system prompts** — use the `prompt` field for detailed task context.
- **Don't embed secrets, API keys, or credentials** in system prompts — use environment variables.

---

## 4. Example: Well-Structured Workflow

```yaml
name: feature_implementation

defaults:
  system_prompt: |
    You are working on a Python web application using FastAPI and SQLAlchemy.
    The codebase uses: type hints, Google-style docstrings, pytest for testing.
    Source code is in src/, tests in tests/.

steps:
  - id: plan
    type: agent
    system_prompt: |
      Analyze the codebase and create an implementation plan.
      Focus on identifying the files that need to change and the order of changes.
    prompt: "Plan the implementation of: {{state.feature_description}}"
    output_format: json
    output_schema:
      type: object
      properties:
        summary: { type: string }
        steps:
          type: array
          items:
            type: object
            properties:
              file: { type: string }
              action: { type: string, enum: [create, modify, delete] }
              description: { type: string }
            required: [file, action, description]
      required: [summary, steps]

  - id: implement
    type: agent
    prompt: |
      Implement the following plan:
      {{state.plan.result | tojson}}
      
      Make all code changes. Run the existing test suite after changes.
    depends_on: [plan]

  - id: test
    type: shell
    script: "pytest -q --tb=short"
    depends_on: [implement]
```

**Notice:**

- No tool usage instructions in author prompts (base prompt handles this)
- No safety instructions (base prompt handles this)
- No output format instructions in prompts (auto-injected from `output_schema`)
- Layer 2 (workflow default) provides project context
- Layer 3 (step override) provides task-specific instructions for the plan step

---

## 5. The `raw_system_prompt` Escape Hatch

For advanced use cases requiring complete control over the system prompt (non-coding agents, specialized integrations, translation agents), use `raw_system_prompt: true`:

```yaml
- id: translate
  type: agent
  raw_system_prompt: true
  system_prompt: |
    You are a translation agent. Translate the input text to French.
    Respond with only the translated text, nothing else.
  prompt: "Translate: {{state.text}}"
```

When `raw_system_prompt: true`:
- **Layer 1 (base prompt) is skipped** — agent loses operational instructions
- **Layer 2 (workflow default) is skipped** — no project context
- **Layer 4 (auto-injected) is skipped** — no schema or pipeline context
- **Only Layer 3 (step prompt) is used**

> ⚠️ **Warning:** Use sparingly. Most agent steps should receive the full layered composition.

### Workflow-Level Default

You can set `raw_system_prompt: true` at the workflow level to apply to all steps:

```yaml
name: custom_agents

defaults:
  raw_system_prompt: true

steps:
  - id: translate
    type: agent
    system_prompt: "You are a translation agent..."
    prompt: "Translate: {{state.text}}"
```

Individual steps can override with `raw_system_prompt: false` if needed.

---

## 6. What Gets Auto-Injected (Layer 4)

### Output Schema

When `output_format` is `json` or `toml` with an `output_schema`:

```markdown
# Required output format

Your response must be valid JSON conforming to this schema:

```json
{
  "type": "object",
  "properties": {
    "title": {"type": "string"},
    "steps": {"type": "array"}
  },
  "required": ["title", "steps"]
}
```

Produce only the JSON object. Do not include any text before or after it.
```

When `output_format` is `json` or `toml` **without** an `output_schema`:

```markdown
# Required output format

Your response must be valid JSON. Produce only the JSON object.
Do not include any text before or after it.
```

When `output_format` is `text` or not specified:
- **No schema block is injected**

### Pipeline Context

Every agent step receives awareness of its position in the workflow:

```markdown
# Pipeline context

- Workflow: feature_implementation
- Current step: plan
- Steps completed: none
- This step depends on: nothing (first step)
```

For a step with dependencies and completed predecessors:

```markdown
# Pipeline context

- Workflow: ci_cd
- Current step: deploy
- Steps completed: build, lint, test
- This step depends on: build, test
```

> Note: `completed_steps` is sorted alphabetically for deterministic output.

---

## 7. Security: Prompt Injection Awareness

When using `{{state.xxx}}` in prompts, be aware that injected content comes from previous step outputs — which may include agent-generated text or external data.

### Injection Scenarios

If a previous step processes untrusted input (user-submitted text, API responses, file contents from external sources), that content could contain prompt injection attempts when interpolated into downstream prompts:

```yaml
- id: process_user_input
  type: agent
  prompt: "Analyze this user-submitted text: {{state.user_text}}"
  
- id: summarize
  type: agent
  prompt: "Summarize the analysis: {{state.process_user_input.result}}"
  # ⚠️ If user_text contained injection attempts, they may appear here
```

### Mitigations

1. **Use `output_schema` validation on upstream steps** to constrain what reaches downstream:
   ```yaml
   - id: process_user_input
     type: agent
     output_format: json
     output_schema:
       type: object
       properties:
         sentiment: { type: string, enum: ["positive", "negative", "neutral"] }
         key_points: { type: array, items: { type: string } }
   ```

2. **Pass data via files instead of inline** for steps processing untrusted input:
   ```yaml
   - id: analyze_file
     type: agent
     prompt: "Analyze the contents of {{state.input_file_path}}"
   ```

3. **Sanitize state values before interpolation** where possible (via upstream shell steps or pre-processing).

---

## See Also

- [Workflow Authoring Guide](./WORKFLOW_AUTHORING.md) — Complete workflow syntax reference
- [CLAUDE.md](../CLAUDE.md) — Project documentation and YAML DSL reference
