# Cloud sprint → GPK2 Ops Work

Use **Sprint Ops Work** in the Console to review and record a Cloud sprint's
pointed work in GPK2. Each engineer receives one placeholder titled
`SBG Jira Ops Work - <Sprint name>`, assigned to their GPK2 account. Its description
contains clickable source links and the point contribution recorded for each.

## Run it

1. Start Pulse, open the Console, and select **Sprint Ops Work**.
2. Choose the Cloud connection, named board and sprint.
3. Choose the GPK2 connection, destination project and placeholder issue type.
4. Select **Preview / refresh work**. Engineers match automatically by their
   common email address. No mapping table is required.
5. Review each engineer's action, new points, total points, existing links and
   planned description. Review the separate lists of missing-point and unassigned
   work. If the project requires extra fields, expand **Additional required
   project fields** and supply their Jira names and values, then refresh.
6. In a deliberately configured `safe_apply` server, tick the review checkbox
   and select **Apply eligible changes**. The normal double-click launcher stays
   in `recommend_only`, so it supports previews and blocks writes.
7. Add missing estimates in Cloud, then preview and apply again. Previously
   included source links are skipped; newly pointed work is appended to the same
   placeholder and its points are added once.

Inputs changing after preview invalidate approval. Refresh the preview before
applying again. The backend independently rereads the sprint, destination
placeholders, field metadata and reporter before writing.

## Matching engineers

Pulse uses the Cloud assignee's visible email address as the GPK2 username and
checks for an exact, case-insensitive, active account assignable in the target
project. If the sprint response omits the email, Pulse reads the Cloud user
profile once per engineer. It does not guess from display names or assume two
unrelated account IDs refer to the same person.

If email privacy hides the address, or the target account is unavailable, that
engineer is flagged and receives no automatic write. You can make the email
visible to the connection or use an optional username override for an exception.
Overrides stay in this browser and are scoped to the source/destination/project.
Two Cloud accounts resolving to the same GPK2 account are blocked for review.

## How reruns work

The **description's source links are the inclusion ledger**. Local execution
history is not the authority for whether a Cloud story has already been included.
A new history database still recognizes existing description links.

For example, the first run records a 3-point issue while another story has no
estimate. After that story receives 5 points, the next run appends its link and
updates the existing placeholder to 8 points. A further run makes no change.
Explicit zero-point estimates are valid. Missing, negative and non-finite values
are excluded and reported. The workflow includes all issue types in the selected
sprint; it does not silently filter to Story issue types.

Updates preserve the existing description and add only new entries. Previously
recorded contributions and the placeholder's current total are preserved: this
is append-only reconciliation, not automatic repricing, removal or reassignment
of work already recorded. Changes to estimates for already-linked issues need a
separate manual reconciliation. Existing manual notes are preserved.

Wiki, Markdown and plain source URLs are recognized. A bare issue key or a link
to another Jira host/context path does not prove inclusion. Generated entries
contain only the actual source link and points, so URLs mentioned in a source
summary cannot accidentally mark unrelated issues as included.

Labels identify the sprint and engineer so identical sprint names, renamed
placeholders and retries can be distinguished. Labels help locate placeholders;
their description links still determine included work. A single legacy
placeholder with the exact title and assignee can be adopted. Multiple matches,
conflicting ownership or an issue already linked in another engineer's
placeholder are flagged instead of creating duplicates. Those cases need manual
reconciliation.

## Permissions and recovery

The destination create screen must support Summary, Description, Reporter,
Assignee, Labels and the configured Story Points field. Its edit screen must
support Description, Labels and Story Points. Extra required fields must have
values or defaults. New placeholders use the connected GPK2 account as reporter;
existing reporters and unrelated fields are preserved. Pulse does not add the
placeholder to a GPK2 sprint or copy attachments, comments or statuses.

Every external write is journaled before execution. Concurrent reviews for the
same source/destination/project/sprint share a scope lock. If an API response is
lost, use **Check uncertain results**, review the observations, tick approval,
and select **Resume reviewed changes**. Confirmed work is not repeated. An absent
search result alone never authorizes retrying an uncertain create because Jira
indexing can lag.

If pending writes remain, changes to the Cloud sprint block recovery until
reconciled. When all reviewed effects are already confirmed, the old execution
can finish without further writes and release its scope for a fresh sync.

The Console and Chat share `preview_sprint_placeholders` and
`apply_sprint_placeholders` backend methods. The generic execution preview API
uses action `sprint_placeholders`; parameters are `source_instance`, destination
`instance`, `sprint_id`, `project`, optional `issue_type`, optional
`additional_fields`, and optional `user_mappings` for exceptions only.

## Verification

Automated tests use fake Jira adapters and block external network access. They
cover automatic email identity, missing points, fractional/zero estimates,
description-ledger reruns, duplicates, stale reviews, mode/actor checks,
concurrency, partial execution and recovery. Console tests cover approval and
stale response handling. A local fake-Jira browser workflow exercises create,
append and unchanged reruns; it never mutates either real Jira instance.

References: [Atlassian Data Center assignable-user API](https://developer.atlassian.com/server/jira/platform/rest/v10002/api-group-user/)
and [Jira field metadata and updates](https://developer.atlassian.com/server/jira/platform/updating-an-issue-via-the-jira-rest-apis-6848604/).
