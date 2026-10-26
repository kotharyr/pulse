# Sprint operations

## Design principle

Sprint closure is a workflow, not a single API call. The assistant first creates a complete plan and capacity impact. Execution is blocked unless the plan has no unresolved incomplete work and the server is running in `MODE=approved_destructive`.

## Recommended conversational workflow

1. Ask ChatGPT to report the current sprint.
2. Ask it to propose how unfinished work should be handled.
3. For work that should simply roll over, add the issue key to `move_issue_keys` or use `rollover_all_incomplete=true`.
4. For work that should be split, ChatGPT constructs a `split_plans` entry based on the issue description and your instruction.
5. Run `preview_close_sprint`.
6. Review the overcommit warning and every source transition/new issue.
7. If necessary, remove/defer work from the next sprint and preview again.
<<<<<<< HEAD
8. Only then run `apply_close_sprint` with that preview's `preview_id`.

For the stored workflow, use `sprint_close_preview`, review the result, and pass
its execution reference ID to `sprint_close_apply`. Stored review IDs are unique;
rejected or consumed reviews cannot be replayed. Sprint states and source data
are checked again on apply. Split source transitions must target Jira's Done
status category. A multi-step failure can leave partial changes, so reconcile
Jira state before creating and reviewing another plan.
=======
8. Only then run `apply_close_sprint`.
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)

## Split plan structure

```json
{
  "source_issue_key": "ENG-140",
  "new_summary": "Complete audit logging",
  "new_description": "Remaining audit logging work split from ENG-140.",
  "story_points": 5,
  "new_issue_type": "Story",
  "parent_key": "ENG-22",
  "source_transition_status": "Done",
  "move_new_issue_to_next_sprint": true
}
```

`source_transition_status` is mandatory. The assistant will not silently leave the original issue incomplete while closing the sprint.

## Epics

Jira teams vary in whether Epics themselves are sprintable. The assistant therefore does not assume an Epic can be assigned to a sprint. For an Epic split, the preferred pattern is usually to create a follow-on Epic or child sprintable issue(s) explicitly, then move sprintable work into the next sprint. ChatGPT should present this structure in the preview rather than inventing a Jira hierarchy.

## Overcommit calculation

The preview includes:

- existing story points in the next sprint,
- points from rollover issues,
- points from newly split work,
- projected total,
- capacity source,
- planning buffer,
- utilization percentage,
- amount over capacity.

If projected work exceeds safe capacity, the response contains:

```text
NEXT SPRINT IS PROJECTED TO BE OVERCOMMITTED
```

The warning does not automatically remove work. ChatGPT can then help decide what to defer.
<<<<<<< HEAD

## Partial execution recovery

Every split create, transition, move batch and close has a durable step receipt.
The split preview includes its recovery label. If a response is lost, reconcile
the stored execution before retrying. Use `reconcile_execution(preview_id)`,
review the result, and pass its fresh `recovery_id` to `resume_execution`.
Pulse skips confirmed steps and blocks uncertain creates, changed source scope
and active workers. Recovery still requires `MODE=approved_destructive`.
See [the recovery runbook](p1-reliability.md).
=======
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
