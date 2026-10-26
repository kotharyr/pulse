# Create a Jira issue from Chat

Pulse can draft and create an issue in an explicitly selected configured Jira instance. The Chat tools and Ops Console execution API use the same backend, durable approvals and history. This feature does not require a new Jira MCP adapter; it uses Pulse's existing Cloud, Data Center and Server connections.

Example Chat prompt:

> Draft a Story in the onprem instance, in my chosen project, to increase the Cluster API node roll timeout to 15 minutes for Edge DC Amber clusters. Use me as reporter. Use the Summary, User Story, Description, Acceptance Criteria, Dependencies, Out of Scope and Business Value format. Preserve Blue and Red settings. Show me the complete draft before creating it.

Replace “my chosen project” with its project name or key, or let Chat ask. `onprem` is an example instance name here, not an assumed project key. Use the configured instance name returned by `list_jira_instances`. An instance must always be selected explicitly; a project's default can come from that instance's configuration.

## Review and create

1. Chat resolves the selected instance and project using `list_jira_instances` and `find_project_by_name` when necessary. `get_issue_creation_context(instance, project, issue_type)` reads project/type creation metadata, additional required fields, human-readable choices and the connected reporter. Unsupported issue types return the available choices.
2. Chat composes a structured draft and calls `preview_create_issue`. Missing requirements should be clarified with the user rather than invented. Each required section must have content; explicitly confirmed absence can be represented by “None”.
3. The stored review shows the instance, project, issue type, title, complete formatted description, additional fields, reporter and recovery label. Review all of them before approving creation.
4. After explicit approval, `apply_create_issue(preview_id)` creates the reviewed issue and returns its key. Creation requires `MODE=safe_apply`. The default `MODE=recommend_only` permits drafting and blocks creation. This feature does not change the configured mode. `approved_destructive` is not the creation mode.

A Chat prompt cannot change the server's configured mode. After intentionally enabling `safe_apply` and restarting Pulse, an unused stored preview can be applied if its source metadata and reporter are still current. If an apply was already blocked by mode, make a new preview.

## Reporter identity

“Me” means the authenticated Jira account belonging to the **selected instance's connection**, obtained from Jira's current-user endpoint. Cloud uses its account identity; Data Center and Server use its username. Pulse explicitly sets this identity and verifies the created issue's reporter by reading it back. The draft cannot override Reporter.

The preview displays that account's name and identifies its source. A Chat login or Pulse bearer token does not establish a separate Jira identity. If the connection uses a service account, configure the connection with your personal Jira credentials before creating an issue as yourself. Reporter and Labels must be writable on the selected create screen; otherwise Pulse stops with an actionable error. The connection needs appropriate Jira create-issue and reporter permissions.

## Description format

The Jira Summary field contains only the issue title. Its Description contains these headings in order:

- Summary
- User Story, with **As a**, **I want**, and **so that**
- Description
- Acceptance Criteria
- Dependencies
- Out of Scope
- Business Value

Cloud receives an Atlassian Document Format document; Data Center/Server receive Jira wiki markup. Both preserve controlled section headings, bold text and bullet lists. The renderer supports this template's basic formatting; arbitrary Markdown, attachments and embedded media are outside this workflow.

The tool's draft input has this shape:

```json
{
  "summary": "Increase Cluster API Node Roll Timeout to 15 Minutes for Edge DC Amber Clusters",
  "overview": "Allow **15 minutes (900 seconds)** for SFCN pods to become ready during node replacement.",
  "user_story": {
    "role": "Kubernetes Platform Engineer",
    "want": "to increase the node rolling timeout for Edge DC Amber clusters to 15 minutes",
    "benefit": "SFCN pods have sufficient time to become Ready without premature timeout failures"
  },
  "description": "Identify the precise CAPI mechanism controlling the timeout.\n- Set the applicable Amber timeout to 900 seconds.\n- Preserve existing safety checks and failure detection.",
  "acceptance_criteria": [
    "The relevant timeout setting is identified and documented.",
    "Applicable Amber clusters use a 900 second timeout through configuration management.",
    "Node rolling with SFCN workloads is validated.",
    "Genuine failures remain detectable and Blue and Red settings are unchanged."
  ],
  "dependencies": ["An Amber cluster for validation and confirmation of SFCN readiness behaviour."],
  "out_of_scope": ["SFCN application changes and unrelated CAPI rolling strategy changes."],
  "business_value": ["**Improves upgrade reliability** and reduces operational toil."]
}
```

This is an illustrative draft, not a created ticket or a claim that a specific CAPI setting has been verified. The full detailed prose from a Chat prompt can be used in these same fields.

Additional creation fields use human names and values, for example `{"Environment": "Amber"}`. Pulse validates them against the selected create screen. Supported values are text, finite numbers, lists of text and named single/multiple choices. Unsupported schemas, rich text custom fields, missing required fields, ambiguous names and unavailable choices block preview. Jira field IDs are resolved internally. The initial workflow reserves Labels for a disclosed recovery marker and does not support attachments, parent/subtask creation, arbitrary user selectors or arbitrary nested custom-field payloads.

## Failure recovery and duplicates

Pulse rechecks the connector target, reporter, creation metadata and serialized payload immediately before creation. Changes invalidate the review. Approval belongs to the actor that generated it.

The write-ahead journal records the create attempt before contacting Jira. An operation label, shown in the preview, identifies its result. Equivalent creates retain a durable operation claim even after completion or metadata changes. Repeating the same intent is blocked; review execution history instead of asking Chat to repeat a timed-out create.

If a create response is lost, the issue key is missing, or reporter verification fails, the execution requires recovery. `reconcile_execution(preview_id)` performs only reads. A single matching label, project, title and verified reporter can confirm the created issue. No match, multiple matches, unreadable state or reporter mismatch blocks resumption. An absent search result alone does not prove that creation failed because Jira indexing can lag. Only an explicit rejected create with no visible matching issue can be retried after reviewed reconciliation. `resume_execution(preview_id, recovery_id)` requires the original actor and a fresh recovery review and skips confirmed creation.

## Shared API and verification

The console API supports `POST /api/executions/preview` with `action: "create_issue"` and `parameters` containing `instance`, `project`, `issue_type`, `draft` and optional `additional_fields`. Existing execution apply, reject, reconcile and resume routes operate on its stored preview ID. There is no new console form in this change.

Automated tests in `tests/test_issue_creation.py` cover Cloud/DC serialization and reporter identities, metadata pagination and legacy Server fallback, missing required fields, explicit target selection, mode and actor checks, stale approvals, duplicate prevention across store reopen, uncertain outcomes, reporter readback failures, rejected-create recovery, and authenticated MCP/REST integration. Tests use fake Jira responses; no live creation is performed.

API references: [Atlassian Cloud issue creation and create metadata](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/) and [Atlassian Data Center/Server REST examples](https://developer.atlassian.com/server/jira/platform/jira-rest-api-examples/).

## Maintaining this workflow

`issue_creation_models.py` defines the validated Chat draft, creation metadata,
parameters and preview contracts. `CreationContext` and `PreparedCreation` name
intermediate results; dictionaries at the Jira and persistence boundaries retain
their existing JSON shape.

`services/issue_creation.py` coordinates context loading, field construction,
preview preparation and journaled creation. `services/creation_fields.py` owns
create-screen requirements and human-name/value resolution.
`services/issue_validation.py` shares preview comparison and direct reporter
readback between creation and recovery. The adapter's `issue_creation.py` reads
metadata, while `issue_descriptions.py` renders the template for each platform.

Keep fingerprints and serialized previews compatible when refactoring: durable
approvals and recovery labels depend on them. Tests retain representative Cloud
and Data Center fingerprints from the original implementation, alongside the
mode, actor, stale-review and recovery checks.
