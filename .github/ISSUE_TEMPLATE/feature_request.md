---
name: Feature Request
description: Suggest a new feature or enhancement
title: "[FEATURE]: <brief description>"
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for suggesting a feature! Please describe your idea clearly.
  - type: checkboxes
    attributes:
      label: Is your feature request related to a problem?
      description: If so, please search existing issues.
      options:
        - label: I have searched existing issues
          required: true
  - type: textarea
    id: problem
    attributes:
      label: Problem Statement
      description: What problem are you trying to solve? Describe the use case.
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: Proposed Solution
      description: Describe your proposed solution and how it would work.
      placeholder: |
        I would like AgentRails to support...
        This could be implemented by...
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: What alternative solutions have you considered?
    validations:
      required: false
  - type: textarea
    id: example
    attributes:
      label: Example YAML
      description: If applicable, show how the feature would be used in a workflow YAML.
      render: yaml
    validations:
      required: false
  - type: dropdown
    id: priority
    attributes:
      label: Priority
      description: How important is this feature to you?
      options:
        - Nice to have
        - Would improve workflow
        - Blocking adoption
    validations:
      required: true
