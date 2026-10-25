# Pulse reliability audit

25 October 2026. Source baseline: `73facaa` on `main` in `/Users/rakothar/pulse-app`.

Pulse has useful automated tests, but they do not cover every advertised workflow. The original suite passed **79 tests** despite reproducible authentication, approval, sprint-planning, and reporting defects. After repairs, **147 Python tests and 2 console JavaScript tests pass**. Pulse remains in `recommend_only`; the audit made no Jira requests or writes to external application systems.

The practical recommendation is to resume analysis and previews locally, with the limitations below visible. Keep Jira writes disabled until the remaining P1 work and a controlled acceptance run are complete.

## Test baseline and verification

| Measure | Baseline | After repairs |
| --- | ---: | ---: |
| Python tests passing | 79 | 147 |
| JavaScript tests passing | No suite | 2 |
| Python statement coverage | 75.4% | 78.7% |
| Python branch coverage | 54.9% | 61.1% |
| Combined statement and branch coverage | 70.9% | 74.7% |

The baseline used the source without code edits. New regression examples initially produced 39 failures across parameterized cases; three further adapter pagination and truncation cases and one terminal-transition case also failed before their fixes. These are cases, not 43 independent defects. Existing fixture expectations changed only where safer contracts deliberately changed: explicit MCP approval IDs, displayed source field values, complete sprint state, and the settings search limit.

Tests ran on Python 3.12.14 in an isolated temporary environment with MCP 1.30.0, httpx 0.28.1, Starlette 0.52.1, Pydantic 2.14.1, pytest 8.4.2, and coverage 7.17.0. Dependencies were installed within the repository's declared ranges. The provided `.venv/bin/python*` files are plain text copies of links, so that copied environment cannot run. It was preserved; the test environment is `/private/tmp/pulse-audit-venv`.

`tests/conftest.py` now forces the suite's default mode to `recommend_only`, selects example configuration, and blocks socket connections. Tests of apply behavior use fake Jira clients and scoped mode changes. HTTP tests run the ASGI application in memory. The suite reports 29 dependency deprecation warnings, primarily an MCP resource-validation default and a Starlette/AnyIO alias; warnings are not test failures.

[Machine-readable coverage evidence](reliability-evidence.json) inventories every top-level Python function and class method, including untouched bodies and missing executable lines. An exercised line or function is not proof that every outcome has an assertion. Coverage excludes JavaScript and live-system behavior.

## Functionality against implemented tests

| Capability | Automated evidence | Remaining limits |
| --- | --- | --- |
| MCP composition and protocol | `test_mcp_architecture.py`, `test_reliability_regressions.py`: tool schemas, plugins, auth, initialization, session setup and a read-only tool call | Most tools are tested as wrappers rather than individually through the full MCP protocol; no Enterprise or tunnel acceptance run |
| Cloud adapter | `test_jira_adapters.py`, `test_adapter_failures.py`: v3 search tokens, project pagination, ADF description format, auth inference | Mocked responses; no proof against a particular tenant, field schema or permission set |
| Data Center and Server adapters | Same adapter tests plus `test_credentials.py`: offset pagination, POST-to-GET fallback, direct issue fallback, context paths, PAT/basic inference | Server aliases the Data Center provider; no dedicated version compatibility matrix |
| Transport failures and lifecycle | Redirect refusal, HTTP 401/403/429/5xx, timeout, non-JSON/invalid JSON, empty success, client reuse/close, batch sizing | No backoff strategy or soak tests; a failed multi-step write is not transactional |
| Environment discovery and configuration | `test_environment_discovery.py`, `test_environment_loading.py`, `test_config.py`, `test_migration.py`: cached discovery, name resolution, migration, credentials, bind checks | Cache persistence and concurrent updates need stronger guarantees; readiness validates configuration, not live Jira connectivity |
| Field updates and quarter assignment | `test_platform_contracts.py`, `test_console_backend.py`, regression tests: displayed names, option resolution, mode and preview checks, changed source value refusal, instance binding | `test_field_resolution.py` itself checks only exception inheritance; multi-select/user/cascading schemas need a fuller matrix |
| Sprint reports and capacity | `test_sprint_capacity.py`, `test_sprint_intelligence.py`, console and MCP tests: overcommit, buffers, progress, rollover, engineer/team grouping | Historical capacity sampling and unusual sprint/field configurations have limited integration coverage |
| Sprint closure | Contract and regression tests: mandatory reviewed ID, current plan check, valid sprint states, board match, duplicate/conflicting split handling, finite points, terminal transition requirement, complete issue loading, rollover apply order, move failure stops closure | Complete split creation/transition/move/close recovery and cross-process coordination remain P1 work |
| Portfolio Hygiene | `test_portfolio_hygiene.py` and regression tests: hierarchy, fiscal quarters, Team/PT scoping, dates, QP labels, stored previews, safe mode, stale date/label refusal, unrelated-label preservation | Parent edits intentionally remain blocked; partial changes can succeed before another change fails; no full browser journey |
| Repository inventory | `test_repository_inventory.py`, `test_repo_scanning.py`: manifests, ignored generated folders, package/image inventory, flat output, security text signals | Several ecosystem parsers have unexecuted branches; malformed files, symlinks, very large trees and version expressions need more fixtures |
| Security analysis | `test_security_remediation.py` and regression tests: CVEs, fixed versions, repo matching, grouping, ranking inputs, unknown versions, mixed vulnerable/fixed occurrences | Heuristic ticket extraction is not a vulnerability database or evidence that a ticket is resolved; only plain numeric versions are ordered |
| Ops Console and REST | `test_console_api.py`, backend and regression tests: route delegation, assets, pagination, invalid parameters, preview/apply/reject/history; `console.test.cjs`: bearer header and authentication-error propagation | Static text checks and a small JavaScript harness do not test rendering, clicks, responsive layout, reconnect, or browser storage behavior end to end |
| Engineering review and other orchestration | `test_orchestration.py`, regression tests: composition, missing sources, nested failures, saved views, stale preview reporting | Many tests substitute a whole backend; Team and Board parameters are often hints rather than actual filters; portfolio indicators are incomplete |
| Health and diagnostics | Platform and health tests: liveness/readiness separation, sanitized reports, audit records, timezone handling | Audit/execution records are process-local; role definitions describe intent rather than enforce user roles |

## Verified defects repaired

| Priority | Trigger and previous behavior | Repair and evidence |
| --- | --- | --- |
| P0 | Set an MCP token, then request console data or mutations without it; custom routes still ran | Custom private HTTP routes require the same configured token. Public static shell/assets and lightweight liveness remain available. Missing/wrong-token cases return 401 before backend dispatch |
| P1 | Call a low-level MCP apply tool without a reviewed preview; the wrapper generated its own approval ID | `apply_field_updates`, non-dry `assign_to_quarter`, and `apply_close_sprint` accept an explicit `preview_id` and refuse its absence. This is an intentional additive schema change |
| P1 | Apply a rejected or already completed stored preview; writes could run again | Atomic transition from `previewed` to `applying`, refusal of other lifecycle states, unique review IDs, recorded failures, and a two-thread test for a single stored review |
| P1 | Change an existing field value or switch instances between preview and apply; the old plan could still match | Field previews include the instance, query and displayed current values; apply rebuilds and compares the plan |
| P1 | Close a sprint into itself, a closed sprint, a different board, or conflicting/duplicate split actions | Preview adds blocking errors; apply respects them. Negative or non-finite split points are blocked |
| P1 | Split source transition points to an unfinished status; preview accepted any nonempty status name | Connector resolves a unique transition and requires its target status category to be Done before accepting the plan |
| P1 | A requested sprint name is missing; the workflow silently used automatic discovery | An unresolved explicit name prevents the close preview. Ambiguous partial-name matches also fail to resolve |
| P1 | Sprint search hits its issue limit and silently constructs an incomplete plan | Retrieve one extra issue and raise an explicit error rather than accept truncation |
| P2 | Project or board lists span server pages; discovery omitted later pages | Cloud projects and Agile boards follow pagination up to their requested limits |
| P2 | Split defaults and descriptions differ between displayed plan and execution | Description is included in the preview fingerprint; apply uses normalized preview split fields and inferred points; missing created issue key stops closure |
| P2 | One repository contains both vulnerable and fixed package occurrences; it appeared in the already-fixed list | Vulnerable or unknown occurrences exclude that repository from already-fixed results |
| P2 | Version ranges, prereleases or digests are compared by their digits and may appear fixed | Unsupported version expressions remain unknown instead of proving remediation |
| P2 | A nested source fails but the engineering review omits it from overall source coverage | Aggregate nested source statuses into the top-level confidence calculation |
| P2 | An issue timestamp lacks a timezone; health reporting raises an exception | Treat naive timestamps as UTC and retain invalid-date tolerance |
| P2 | Invalid numeric sprint/security/history query values raise an unhandled server error | Return a structured 400 validation response |

## Remaining work in priority order

### P1 before enabling writes

1. **Recover partial sprint and hygiene writes.** Sprint apply performs multiple independent Jira mutations. A late failure can leave created issues, transitioned sources or moved batches behind. Add durable per-step results, reconciliation and idempotency tests for failure after each step. Current stored reviews prevent replay of one record but cannot roll back Jira. Relevant code: `EngineeringOpsBackend.apply_close_sprint`, `PortfolioHygieneService.apply`.
2. **Enforce durable approval and audit scope.** Execution and audit history disappear on restart and are separate in each worker. Duplicate newly created previews can still represent the same operation. Low-level hash-based approval IDs are not a durable approval record. Bind approval to action, actor, instance and source version, and test restart/multi-worker behavior. Also restrict the sprint-close apply workflow to records whose action is actually `close_sprint`.
3. **Verify the actual deployment safely.** First run explicitly authorized read-only Cloud and Data Center smoke tests for authentication, fields, discovery and sample reports; then accept destructive behavior only in disposable Jira projects. Add a browser acceptance run for token entry, reviews, sprint preview, rejection, and mode-blocked apply. Offline tests cannot establish live compatibility.

### P2 reliability and completeness

- **Disambiguate sprint names across boards.** Exact duplicate names currently select the first match. Board input does not consistently constrain discovery. Require an unambiguous board/sprint selection before operational use.
- **Make scope and reporting honest.** Team filtering is often only an orchestration hint. Backlog defaults select recently updated work while looking for 90-day staleness; old backlog can be outside that scope. Portfolio stale/ownership and overcommit indicators are incomplete. Add source-shaped fixtures and explicit unsupported/partial output rather than empty healthy-looking sections.
- **Persist local data atomically.** Saved views and environment cache use JSON files, with no transactional coordination. Test interrupted writes, corruption, concurrent updates, cache keys and project isolation.
- **Expand adapter and field contracts.** Cover additional Data Center/Server versions, duplicate field names, multi-select/user/cascading values, field removal, read permissions and project limits. Responses that reach configured list limits should disclose incomplete coverage.
- **Add browser coverage.** The two JavaScript tests cover authentication plumbing only. Exercise real navigation and user flows, including initial failure/reconnect, source changes during preview, stale selections and backend errors.
- **Choose dependency resource validation explicitly.** MCP emits a warning about the default token resource check. Define the intended static-token audience behavior and add matching tests before upgrading the MCP major version. Keep TLS verification enabled.
- **Broaden repository/security fixtures.** Cover all supported manifest types, malformed files, prereleases, vendor versions and constraints. Unknown versions should continue to require manual review.

### P3 features visibly marked planned

The Insights screen contains planned Repository Health and Delivery Trends panels with no data workflow. Task planning notes use browser storage; they are not a shared action register. Platform role names are descriptive, the refresh scheduler reports disabled/manual, and GitHub/Webex/email/Confluence connector rows represent future capabilities. The referenced tunnel startup/check scripts and tunnel documentation are absent from this checkout. These should not be presented as tested, completed features.

## Git and local configuration

This was already a Git repository with remote `origin` configured. The copied source matched the latest commit in content; most pending changes were executable bits. Original tracked file modes were restored. Local Jira configuration, discovery data, saved views, the source ZIP, Python bytecode and generated package metadata are removed from the next Git snapshot while existing local files are preserved and ignored. `.env` and `.env.local` remain ignored; local `.env` is set to `MODE=recommend_only`.

No configured secret values were found in the scanned tracked text files, and the tracked ZIP contains no `.env` or `.env.local` entries. This is a scoped check, not a complete historical secret audit. Earlier commits still contain local configuration and generated artifacts; history was not rewritten, and nothing was pushed.

## Reproduce the checks

Use a working Python environment with the project development dependencies and coverage installed:

```bash
python -m pip install -e '.[dev]' coverage
python -m coverage run --branch --source=engineering_ops -m pytest -q
python -m coverage report
node --test tests/console.test.cjs
git diff --check
```

For this audit, the Python command is `/private/tmp/pulse-audit-venv/bin/python`. Rebuild the copied `.venv` from a working Python interpreter before using the existing startup scripts. The in-memory application tests confirm service composition, liveness, configuration-readiness status handling and MCP tool invocation; they do not establish that the copied startup environment or live connectors are ready.
