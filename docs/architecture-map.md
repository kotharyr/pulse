# Post-Refactor Architecture Map

Use this map when deciding where future work belongs.

## Entry Points

`engineering_ops.server` is the MCP composition layer. Keep it thin: tool wrappers,
HTTP health routes, auth setup, plugin registration, and lifecycle cleanup belong
here. Do not add Jira workflow logic directly to `server.py`.

`engineering_ops.api` is the Ops Console REST layer. Keep it thin: request parsing,
JSON responses, and static console asset routes belong here. REST handlers should
call `EngineeringOpsBackend`, not Jira adapters or service helpers directly.

`engineering_ops.runtime` owns process-wide Jira client lifecycle. Use it for
shared client lookup and shutdown behavior.

## Shared Backend

`engineering_ops.backend.EngineeringOpsBackend` is the transport-neutral capability
layer. ChatGPT Enterprise MCP tools and the Ops Console both call this backend so
safety rules, previews, field handling, and workflow behavior stay consistent.
Add new user-facing capabilities here when they combine adapters, settings, and
service helpers.

## Connectors

`engineering_ops.adapters.jira` owns Jira transport details: authentication,
Cloud/Data Center/Server API differences, REST paths, pagination, description
payload formatting, transitions, issue writes, and Agile endpoints. Business code
should call connector methods rather than constructing Jira REST paths or auth.

## Business Services

`engineering_ops.services` contains focused, side-effect-light domain helpers:

- `fields.py`: resolve human-readable Jira fields and displayed values to internal
  update payloads.
- `sprints.py`: sprint status, story points, done detection, blocked work,
  rollover candidates, split proposals, progress breakdowns, and overcommit math.
- `executions.py`: process-local preview/apply/reject history for console
  execution workflows.
- `health.py`: stale, blocked, unassigned, and domain-label summaries.
- `repos.py`: local repository discovery, manifest scanning, and security signal
  extraction.
- `portfolio_hygiene.py`: on-prem Portfolio Hygiene rules for Initiative
  ancestry, fiscal-quarter date validation, QP commitment labels, preview
  generation, source revalidation, and safe date/label apply.

Prefer adding pure logic here, then orchestrating it from `EngineeringOpsBackend`.

## Ops Console

Static console assets live under `engineering_ops/console/static`. Browser code
must call `/api/...` endpoints only; it must not duplicate Jira field resolution,
pagination rules, sprint math, preview gates, or connector logic. Saved views are
browser-local for now. Future Action Register work should add a business service
for action ordering/due dates, expose it through `EngineeringOpsBackend`, and then
bind it to REST/UI routes.

## Portfolio Hygiene

Portfolio Hygiene belongs in `engineering_ops.services.portfolio_hygiene` and is
exposed through `EngineeringOpsBackend.portfolio_hygiene_*`. MCP tools
`portfolio_hygiene_review`, `portfolio_hygiene_preview_fix`, and
`portfolio_hygiene_apply` plus REST endpoints under `/api/hygiene/...` must stay
thin wrappers. Keep hierarchy/date/label logic out of `server.py`, `api.py`, and
`console/static/app.js`.

## Platform Rules

Default behavior is `MODE=recommend_only`. Writes must be preview-first, field IDs
must stay out of user-facing responses, and destructive sprint operations require
`MODE=approved_destructive`. The console must visibly distinguish preview from
apply. Add tests for every new capability, especially around mode gates,
preview/apply behavior, Cloud/Data Center differences, REST routes, and
field/value resolution.
