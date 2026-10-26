# ChatGPT Enterprise usage

## Development

Run the MCP server locally and validate it with MCP Inspector first.

```text
Transport: Streamable HTTP
URL: http://127.0.0.1:8080/mcp
```

## Production connection

ChatGPT Enterprise connects to remote MCP servers, not directly to localhost. Publish the MCP endpoint through an approved HTTPS deployment or an approved private-network mechanism such as Secure MCP Tunnel.

In ChatGPT Enterprise developer mode, create a custom app, provide the remote `/mcp` endpoint, scan tools, test the app privately, and have an admin publish the approved tool set to the required RBAC groups.

## Natural-language examples

### Sprint close

> Analyze the current Platform sprint on the onprem Jira. I want to close it. Identify unfinished work, suggest which work should roll over and which should be split, and show the capacity impact on the next sprint. Do not change Jira.

After reviewing the proposal:

> Split ENG-140 as proposed, roll ENG-150 and ENG-160 into the next sprint, and preview the close again. Tell me plainly whether the next sprint is overcommitted.

Only after approval and a server mode change:

> Apply exactly that sprint-close plan.

### Security remediation

> Look at all Operational Security Issue tickets in the cloud Platform project. Normalize them into package upgrades and tell me which upgrades remove the most tickets. Compare the required versions with all repositories checked out locally.

### Engineering health

> Give me an engineering-operations review of all open work in Platform. Highlight stale work, blocked work, unassigned work, and domain hotspots. Don't update anything.

### Portfolio planning

> Show me FY27 Q2 progress and then preview moving all approved Governance exceptions to FY27 Q3.

## Future connectors

Email, Webex, Slack, calendar, incident-management, CI/CD, and observability systems should normally be added as capability modules/apps rather than separate user-facing assistants. ChatGPT Enterprise can invoke multiple apps in one conversation, so security boundaries can still be separated where needed.
