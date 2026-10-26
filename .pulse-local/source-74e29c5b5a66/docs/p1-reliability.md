# Pulse P1 reliability safeguards

25 October 2026. Follow-up to the [reliability audit](reliability-report.md).

The three P1 workstreams now have persistent execution safeguards, regression tests and acceptance tooling. **192 Python tests and 2 JavaScript tests pass.** Read-only checks passed against the configured Cloud and Data Center instances and the existing Jira MCP connection. The console was checked in a real in-app browser against the production backend with fake Jira data.

`MODE=recommend_only` remains the default and the local setting. No live Jira mutations were performed. Mutation acceptance in explicitly disposable Jira projects remains a prerequisite for enabling operational writes.

## Status of the three items

| Item | Implemented and verified | Remaining acceptance gate |
| --- | --- | --- |
| Recover partial sprint and hygiene writes | Durable steps before every mutation, individual move batches, reconciliation, explicit reviewed resume, operation markers, before/after failure cases and a real worker-crash test | A production Jira mutation cannot be rolled back by SQLite. Confirm behavior in a disposable project before enabling writes |
| Durable approval and audit scope | SQLite transactions shared across local workers; actor, action, instance, target configuration and source fingerprints; duplicate/overlapping operation claims; persistent audit and receipts; restart and cross-process tests | A shared static bearer credential represents one operator principal, not individual human identities or an RBAC system |
| Safely verify the deployment | Live Cloud and Data Center read checks; existing GPK2 MCP authentication/search/field checks; real-browser token/review/preview/reject checks; reusable smoke and browser scripts | Full standalone Playwright execution was blocked by this host's browser-launch sandbox. Its core flows were checked through the in-app browser. Live destructive acceptance remains intentionally unperformed |

## Persistent approvals and audit

The shared production backend opens `PULSE_STATE_DB`, which defaults to `config/pulse-state.sqlite3`. All workers must use the same absolute database path on the same host. SQLite transactions serialize approval claims and step updates. This setup is for a local filesystem; it is not a distributed lock across hosts or a database on a network share.

The database stores reviewed plans, parameters, source fingerprints, actor IDs, lifecycle state, mutation receipts and audit events. It contains Jira issue data and must remain private. New database files are created with owner-only permissions; SQLite database and journal files are ignored by Git. Jira credentials are never stored in this database.

The authenticated bearer credential identifies an operator using a one-way fingerprint. MCP and console calls derive that identity from verified authentication, never from a caller-supplied actor header. Loopback development without authentication uses the `local` principal. Token rotation changes the principal; outstanding operations should be reconciled before rotation.

Every apply must reference a stored review. Low-level MCP field, quarter and sprint tools now return durable review IDs from their matching previews. A calculated plan hash alone is no longer accepted as approval. The preview is bound to:

- the action and instance;
- the authenticated operator;
- a fingerprint of the target URL, provider type and default project;
- the reviewed inputs and source values, including Jira update timestamps where returned.

The sprint-close workflow accepts only a `close_sprint` record. Atomic claims prevent two processes from consuming the same review or overlapping operations from writing the same reviewed issues or sprints. Completed operation fingerprints remain claimed; source locks for other future operations are released after success. A failed operation with no mutation attempt releases its claims. An uncertain partial operation retains them until recovery completes.

The database is authoritative. Restarting Pulse does not erase approvals or permit replay. Do not delete it to retry a failed operation. Back it up while Pulse workers are stopped, or use SQLite's backup API. Restoring an older backup requires reconciling Jira changes made after that backup before any writes resume.

## Recovering a partial operation

Every attempted issue creation, transition, move batch, sprint closure and hygiene change has a durable receipt written before the Jira call. A response confirmed by Jira is recorded as succeeded. An explicit request rejection can be recorded as not applied; a lost response or unexpected error is uncertain.

A split issue gets a recovery label that is disclosed in the preview. If issue creation succeeds but the response is lost, read-only reconciliation searches for that exact label and verifies the summary and project. It does not create another issue simply because the original key is missing from the receipt. Absent or ambiguous search results after an uncertain create block recovery; indexing delay or a Jira permission problem cannot be treated as proof that creation failed.

Use the same operator identity and follow this sequence:

1. Open the partial operation from Execution History and select **Reconcile**, or call `reconcile_execution(preview_id)` through MCP.
2. Review each observed step and the current target-sprint load. Reconciliation reads Jira and updates local receipts; it does not mutate Jira.
3. Resolve any unknown or conflicting effects in Jira through your established operational process. Reconcile again. Pulse cannot automatically prove that a timed-out create with no visible marker failed.
4. If reconciliation returns `can_resume=true`, review its fresh `recovery_id`, then explicitly select **Resume Reviewed Recovery** or call `resume_execution(preview_id, recovery_id)`.
5. Pulse checks the recovery review again, claims the operation, skips confirmed steps and performs only remaining reviewed actions. Normal write modes still apply: sprint closure needs `approved_destructive`; hygiene needs `safe_apply`.

REST clients can use:

```text
POST /api/executions/{preview_id}/reconcile
POST /api/executions/{preview_id}/resume
     {"recovery_id": "the reviewed recovery fingerprint"}
```

A new or changed current-sprint issue, changed untouched source fields, a different target configuration, an altered confirmed effect or a stale recovery fingerprint blocks resume. An active worker cannot be reconciled. After a worker dies, explicit reconciliation checks its process is gone before recovering an interrupted `applying` record. Pulse does not reclaim a live worker merely because a timer expired.

This is recovery through observation and idempotent continuation, not an external transaction or automatic rollback. Changes made between the last Jira read and a write remain subject to Jira's concurrency behavior. If a step cannot be verified safely, Pulse keeps it blocked.

## Automated coverage

`tests/test_durable_execution.py` verifies persistent histories, atomic claims across processes, authenticated actor binding, forged-header rejection, action/instance/configuration scope, duplicate operation refusal, stale recovery reviews and recovery endpoint behavior.

Failure injection covers every split-sprint mutation boundary, both before the write and after the effect with a lost response: create, transition, each one-issue move batch and close. Hygiene cases inject failure at every date and label change. Field updates have before/after recovery cases. A child process also creates a simulated external effect and exits before saving the response; the next worker reconciles the started receipt and completes the plan without another create.

`tests/test_smoke_checks.py` verifies that the direct deployment probe refuses mutations and that the MCP probe does not mistake a tool-level error for success. All ordinary pytest tests block external socket connections.

```bash
python -m coverage run --branch --source=engineering_ops -m pytest -q
python -m coverage report
node --test tests/console.test.cjs
```

Final Python coverage is **80.9% of statements and 65.4% of branches**, or **77.4% combined**. The original audit baseline was 75.4%, 54.9% and 70.9%, respectively. Coverage does not prove live acceptance; the [coverage inventory](reliability-evidence.json) identifies functions with unexercised paths. The suite has 35 dependency deprecation warnings, principally from the same MCP resource-validation and Starlette/AnyIO defaults noted in the initial audit.

## Live read-only checks

The direct probe requires explicitly named configured instances, verified HTTPS and a positive timeout. Its client permits GET requests and the two search POST endpoints, and refuses mutation requests before sending them. It checks authentication, fields, sample projects/boards and a bounded engineering-health report.

```bash
python scripts/smoke_read_only.py --instance cloud --instance onprem \
  --output .acceptance-results/jira-adapters.json
```

These checks passed for both configured instances. Output contains status/count summaries, not credentials, issue contents or raw HTTP errors. Private run artifacts remain ignored by Git.

### Use the existing GPK2 Jira MCP

The locally configured HTTP `jira` MCP connection was successfully initialized. Its current-user authentication, bounded recent-issue search and field lookup passed using the existing stored authentication header. No credential was copied into Pulse or this repository.

```bash
python scripts/smoke_jira_mcp.py --server jira \
  --output .acceptance-results/gpk2-mcp.json
```

The probe reads the existing local Codex MCP configuration and calls only its named read tools. An optional `--project` takes a Jira project key; GPK2 was described as the instance, so it is not assumed to be a project key. The first project-scoped attempt was rejected; the corrected bounded instance-wide check passed.

This makes the connection usable for read-only validation now. Pulse's runtime still uses its existing REST adapters. Routing Pulse workflows through the MCP connection would require an adapter that normalizes its tool payloads and verifies coverage for sprint, transition, creation and metadata operations. The current probe does not claim to replace those adapters.

## Browser acceptance

`tests/browser/server.py` runs the real Pulse backend on loopback with fake Jira data, a temporary database and a fixture connector that refuses mutations. The fixture blocks external sockets. `tests/browser/acceptance.cjs` provides a repeatable Playwright journey for authentication, token non-persistence, engineering review, sprint preview, backend mode refusal, rejection and replay refusal.

```bash
npm install
npx playwright install chromium
PULSE_PYTHON=/path/to/working/python npm run test:browser
```

A system browser can be selected with `PULSE_BROWSER_EXECUTABLE`. In this session the standalone browser launch was blocked by the host sandbox. The in-app browser successfully exercised token entry/reconnect, engineering-review rendering, sprint preview with disabled Apply, and persisted rejection against the same fixture. The Python suite separately verified backend mode refusal and rejected-review replay refusal. The standalone Playwright harness is supplied, but its full automated run is not reported as passed.

## Remaining write acceptance gate

Do not enable operational writes solely because the tests and read checks pass. A disposable Jira acceptance environment must explicitly authorize create/transition/move/close and hygiene mutations. Verify required creation fields, marker-label permissions, the configured final-status categories and partial-failure behavior for each deployment there. These actions were not run because the task retains its prohibition on external writes.
