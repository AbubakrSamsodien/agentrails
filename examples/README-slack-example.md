# Slack Platform Updates Workflow

This workflow uses the Slack subagent to fetch recent activity from the `#platform_team` channel and generates a formatted daily report.

## What It Does

1. **Fetches Slack Updates** — Uses the `slack` subagent to retrieve recent messages from `#platform_team`
2. **Extracts Structured Data** — Parses announcements, questions, decisions, and action items into JSON
3. **Formats a Report** — Creates a readable markdown summary
4. **(Optional) Posts Back** — Can post the summary back to Slack (commented out by default)

## Prerequisites

1. **AgentRails installed** — See [README.md](../README.md) for installation
2. **Claude CLI configured** — The `claude` command must be available
3. **Slack subagent access** — Your Claude CLI installation must have the Slack subagent configured

## Run the Workflow

```bash
# From the project root
agentrails run examples/slack_platform_updates.yaml
```

## Output

After running, check the generated report:

```bash
# View the final formatted report
cat .agentrails/state.json | jq '.format_report.outputs.result'
```

Or view the full state:

```bash
cat .agentrails/state.json | jq .
```

## Customize

### Different Channel

Change the channel in the prompt:

```yaml
prompt: |
  Fetch the most recent messages from the #engineering channel.
```

### Post Report Back to Slack

Uncomment the `post_summary` step:

```yaml
- id: post_summary
  type: agent
  subagent: slack
  prompt: |
    Post the following daily summary to the #platform_team channel:
    
    {{state.format_report.outputs.result}}
```

### Change Time Range

Modify the prompt to fetch a different time range:

```yaml
prompt: |
  Fetch messages from the last 7 days from the #platform_team channel.
```

## Troubleshooting

### "Subagent not found" Error

Ensure the Slack subagent is available by checking your `~/.claude/agents/` directory:

```bash
ls ~/.claude/agents/slack.md
```

You can also test the subagent directly:

```bash
claude -p "@'slack (agent)' list available channels"
```

If the subagent file doesn't exist, you may need to install the Slack MCP plugin for Claude CLI.

### Permission Errors

Add explicit permission mode in defaults:

```yaml
defaults:
  permission_mode: bypassPermissions
```

### Timeout on Large Channels

Increase timeout for steps fetching many messages:

```yaml
- id: fetch_slack_updates
  type: agent
  subagent: slack
  timeout: 600  # 10 minutes
```

## See Also

- [Prompt Craft Guide](../docs/prompt-guide.md) — System prompt composition and best practices
- [Workflow Authoring Guide](../docs/WORKFLOW_AUTHORING.md) — Complete workflow syntax reference
