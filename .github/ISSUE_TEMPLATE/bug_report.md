---
name: Bug Report
description: Report a bug or unexpected behavior
title: "[BUG]: <brief description>"
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to report a bug! Please provide as much detail as possible.
  - type: checkboxes
    attributes:
      label: Is there an existing issue for this?
      description: Please search to see if an issue already exists for this bug.
      options:
        - label: I have searched the existing issues
          required: true
  - type: input
    id: version
    attributes:
      label: AgentRails Version
      description: What version of AgentRails are you using? (run `agentrails --version`)
      placeholder: v0.1.0
    validations:
      required: true
  - type: input
    id: python-version
    attributes:
      label: Python Version
      description: What Python version are you using? (run `python --version`)
      placeholder: "3.11.0"
    validations:
      required: true
  - type: input
    id: claude-cli-version
    attributes:
      label: Claude CLI Version (if applicable)
      description: What Claude CLI version are you using? (run `claude --version`)
      placeholder: "2.0.0"
    validations:
      required: false
  - type: textarea
    id: description
    attributes:
      label: Bug Description
      description: Describe what happened and what you expected to happen.
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Steps to Reproduce
      description: Provide a minimal workflow YAML or steps to reproduce the issue.
      placeholder: |
        1. Create workflow.yaml with...
        2. Run `agentrails run workflow.yaml`
        3. See error...
    validations:
      required: true
  - type: textarea
    id: logs
    attributes:
      label: Relevant Log Output
      description: Paste the error output (use triple backticks for code blocks).
      render: shell
    validations:
      required: false
