# Engineering Operations Platform v1.0

A natural-language Engineering Operations backend for ChatGPT Enterprise using MCP.

## What v1.0 provides

- Jira Cloud and Jira Data Center/Server connectivity.
- Jira credentials loaded centrally from `.env` / `.env.local` regardless of working directory.
- Read-only Jira search, environment discovery, quarter reporting, and engineering-health reporting.
- Human-readable Jira field/value updates with preview-first safety.
- Sprint progress reporting.
- Sprint-close planning that can:
  - identify incomplete work,
  - roll selected or all incomplete issues into the next sprint,
  - create explicit follow-on split issues,
  - transition source issues after an approved split,
  - move issues in Jira-supported batches of 50,
  - calculate projected next-sprint capacity,
  - warn when the next sprint will be overcommitted,
  - close the current sprint only in `approved_destructive` mode.
- Local multi-repository discovery and dependency/container manifest scanning.
- Security-ticket normalization for summaries containing `Operational Security Issue`.
- Comparison of normalized package remediation targets with package versions found across local repositories.
- On-prem Portfolio Hygiene review for Initiative ancestry, current-quarter
  Portfolio Feature/Epic dates, and User Story QP commitment labels with
  preview-first safe fixes.

The server is deliberately safe by default. `MODE=recommend_only` allows analysis and previews but blocks writes.

## v1.0 configuration model

The instance file describes **what the system is**, not HTTP authentication details. You do not configure Basic vs Bearer or REST API versions.

```json
{
  "cloud": {
    "type": "cloud",
    "base_url": "https://example.atlassian.net",
    "credentials": "cloud"
  },
  "onprem": {
    "type": "datacenter",
    "base_url": "https://jira.internal.example.com",
    "credentials": "onprem"
  }
}
```

The credential reference determines the environment variable prefix. For the example above:

```dotenv
JIRA_CLOUD_EMAIL=you@example.com
JIRA_CLOUD_API_TOKEN=...
JIRA_ONPREM_PAT=...
```

The platform automatically uses Jira Cloud email + API token with HTTP Basic authentication and Jira Data Center PATs as Bearer tokens. If `JIRA_ONPREM_PAT` is absent, Data Center can fall back to `JIRA_ONPREM_USERNAME` + `JIRA_ONPREM_PASSWORD`.

Field IDs, select option IDs, platform REST API versions, and authentication header construction remain internal implementation details.

Fiscal quarters are explicit configuration. Pulse never assumes calendar quarters:

```dotenv
FISCAL_CALENDAR={"FY27Q1":{"start":"2026-08-01","end":"2026-10-31"}}
```

If a quarter is not present in `FISCAL_CALENDAR`, Pulse derives the current
fiscal quarter from the configured fiscal-year start. The default is August 1,
so August 19, 2026 resolves to `FY27Q1`.

```dotenv
FISCAL_YEAR_START_MONTH=8
FISCAL_YEAR_START_DAY=1
PORTFOLIO_TEAM_OPTIONS=Platform Excellence
PORTFOLIO_PT_OPTIONS=Muon,Atlas,Phoenix,Dragon
```

Portfolio Hygiene resolves the configured Jira field names dynamically:

```json
{
  "quarter_field_name": "Target Quarter",
  "team_field_name": "Team",
  "pt_field_name": "PT",
  "team_pt_field_name": "Team/PT",
  "start_date_field_name": "Start date",
  "end_date_field_name": "End date",
  "hierarchy_field_names": ["Parent Link", "Epic Link"]
}
```

Team/PT scoping uses the configured `Team/PT` Jira field. In the console, Team is
the grouping selector and PT is the Jira option (`Muon`, `Atlas`, `Phoenix`, or
`Dragon`). It does not map Team to Components.

## Upgrade from v0.4

Copy your existing `.env` and `config/jira_instances.json`, then run:

```bash
python scripts/migrate_config_v1.py
./scripts/check.sh
```

The migration makes `config/jira_instances.pre-v1.json` first. See `docs/migration-v1.md`.

## Quick start

```bash
./scripts/install.sh
cp .env.example .env                 # if install.sh did not already create it
cp config/jira_instances.example.json config/jira_instances.json
# edit .env and config/jira_instances.json
./scripts/check.sh
source .venv/bin/activate
pytest
./scripts/run.sh
```

Health endpoint:

```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
```

`/health` and `/health/live` are dependency-free liveness checks. `/ready` checks
configuration readiness without contacting Jira. `/ready`, `/diagnostics`, and
`/api/...` require the configured bearer token when `MCP_BEARER_TOKEN` is set.
In the console, enter the token in **Access token** and select **Connect**;
the token is kept in memory for the current page only.

MCP endpoint:

```text
http://127.0.0.1:8080/mcp
```

Ops Console:

```text
http://127.0.0.1:8080/console
```

The console uses the same backend capability layer as MCP through `/api/...`
routes. It provides instance selection, paginated issue search, browser-local
saved views, current sprint intelligence, execution previews, approve/reject
controls, Portfolio Hygiene review/fix previews, and execution history. In
`MODE=recommend_only`, apply attempts remain blocked and are recorded as failed
without writing to Jira.

## Safety modes

### `recommend_only`

Read, report, discover, scan repos, analyze security issues, calculate capacity, and preview changes. No Jira writes.

### `safe_apply`

Allows reversible Jira field updates such as Target Quarter assignments. Sprint closure and issue movement remain blocked.
Portfolio Hygiene date and label fixes also require `safe_apply`; source issue
state is revalidated before writing.

### `approved_destructive`

Required for sprint-close execution, issue creation during splits, source transitions, moving issues between sprints, and closing the sprint.

Always run `preview_field_updates` or `preview_close_sprint` immediately before
the corresponding apply tool. The shared backend tracks a preview digest so
non-MCP clients can enforce the same reviewed-plan check without changing MCP
tool signatures.

Portfolio Hygiene uses stored previews through `portfolio_hygiene_preview_fix`
and `portfolio_hygiene_apply`. Parent repairs are never applied by default; they
remain manual review unless a future destructive workflow can resolve exactly
one valid parent with high confidence.

## MCP authentication

Local loopback development may omit `MCP_BEARER_TOKEN`. A non-loopback `MCP_HOST`
is rejected at startup unless a bearer token is configured. Clients must send that
token as `Authorization: Bearer <token>` to `/mcp`. Set `MCP_PUBLIC_URL` to the
deployment's public HTTPS origin so MCP authentication metadata uses the external URL.
Container deployments must set `MCP_HOST=0.0.0.0`, a non-empty bearer token, and
their public URL explicitly.

## Plugin architecture

The server is composed from ordered capability plugins in
`engineering_ops.plugins`. Built-in system, Jira, and repository plugins keep their
existing MCP tool names. Additional capability packages can implement `MCPPlugin`
and register tools or custom routes without modifying the server core.

Jira platform differences are provider plugins registered by instance type. Cloud
uses the v3 platform API; Data Center and Server use v2. A separately packaged
provider can be installed with `register_jira_provider()`.

## Sprint capacity

Configure an expected sprint capacity per Jira instance:

```json
{
  "sprint_capacity_points": 50,
  "sprint_capacity_buffer_percent": 10
}
```

A 50-point capacity with a 10% buffer means the assistant treats 45 points as the safe planning limit.

If no point capacity is configured, the server tries to estimate capacity from completed story points in recent closed sprints for the same board. If that is unavailable, it can use `sprint_capacity_issue_count`.

## Natural language usage

The intended UI is ChatGPT Enterprise. MCP tools are deliberately described so ChatGPT can translate natural requests into controlled tool calls.

Examples:

> Show me how the current Platform sprint is tracking and what is incomplete.

> Prepare to close Sprint 42. Roll unfinished stories into Sprint 43, but split ENG-140 into a follow-on issue called "Complete audit logging". Do not make changes yet. Tell me if Sprint 43 will be overcommitted.

> Which package upgrades would eliminate the most Operational Security Issue tickets, and which local repositories are still below the required version?

> Give me an engineering-health review for all open Platform work, highlighting stale, blocked, and unassigned issues.

See `docs/chatgpt-enterprise.md` and `docs/sprint-operations.md`.

## Environment discovery

Call `discover_jira_environment` to inventory human-readable projects, fields, boards, and active/future sprints. This reduces the need to know Jira IDs in ordinary conversation.

## Local repositories

Set:

```dotenv
LOCAL_REPO_ROOT=/Users/you/src
```

where the directory contains all checked-out repositories. The repository tools are read-only.

## Security normalization

The default security ticket marker is:

```dotenv
SECURITY_ISSUE_SUMMARY_MARKER=Operational Security Issue
```

`analyze_security_package_updates` extracts CVEs and explicit fixed/upgrade version statements from matching Jira tickets and groups them by package/version. It then shows matching package occurrences in local repository manifests.

This is deliberately evidence-based. Tickets without parseable package/fixed-version information remain visible in `raw_ticket_analysis`; the server does not invent remediation versions.

## Tests

```bash
source .venv/bin/activate
pytest
```

## ChatGPT Enterprise

ChatGPT must connect to a remotely reachable MCP endpoint. A local `127.0.0.1` endpoint is for development and MCP Inspector only. For a private corporate environment, deploy the server behind company-controlled HTTPS or use OpenAI Secure MCP Tunnel according to your workspace policies.

## Reliability and testing

See [the reliability audit](docs/reliability-report.md) for verified fixes, test
coverage, unfinished workflows and prioritized follow-up work. Tests use example
configuration, default to `recommend_only`, and block external socket connections.
Run `pytest` for Python tests and `node --test tests/console.test.cjs` for the
console authentication tests.

Low-level MCP apply tools now require the `preview_id` returned by their matching
preview tool. They no longer generate approval IDs during apply. Stored workflows
use the record's top-level `preview_id`; the nested preview ID fingerprints the
plan and should not be substituted for the stored review ID. Rejected, failed or
completed stored reviews cannot be replayed; create and review a new preview.
