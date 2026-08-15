# Post-Refactor Architecture Map

Use this map when deciding where future work belongs.

## Entry Points

`engineering_ops.server` is the MCP composition layer. Keep it thin: tool wrappers,
HTTP health routes, auth setup, plugin registration, and lifecycle cleanup belong
here. Do not add Jira workflow logic directly to `server.py`.

`engineering_ops.runtime` owns process-wide Jira client lifecycle. Use it for
shared client lookup and shutdown behavior.

## Shared Backend

`engineering_ops.backend.EngineeringOpsBackend` is the transport-neutral capability
layer. ChatGPT Enterprise MCP tools and the future Ops Console should both call
this backend so safety rules, previews, field handling, and workflow behavior stay
consistent. Add new user-facing capabilities here when they combine adapters,
settings, and service helpers.

## Connectors

`engineering_ops.adapters.jira` owns Jira transport details: authentication,
Cloud/Data Center/Server API differences, REST paths, pagination, description
payload formatting, transitions, issue writes, and Agile endpoints. Business code
should call connector methods rather than constructing Jira REST paths or auth.

## Business Services

`engineering_ops.services` contains focused, side-effect-light domain helpers:

- `fields.py`: resolve human-readable Jira fields and displayed values to internal
  update payloads.
- `sprints.py`: sprint status, story points, done detection, and overcommit math.
- `health.py`: stale, blocked, unassigned, and domain-label summaries.
- `repos.py`: local repository discovery, manifest scanning, and security signal
  extraction.

Prefer adding pure logic here, then orchestrating it from `EngineeringOpsBackend`.

## Platform Rules

Default behavior is `MODE=recommend_only`. Writes must be preview-first, field IDs
must stay out of user-facing responses, and destructive sprint operations require
`MODE=approved_destructive`. Add tests for every new capability, especially around
mode gates, preview/apply behavior, Cloud/Data Center differences, and field/value
resolution.
