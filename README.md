# Pulse user guide

Pulse brings Jira searches, sprint analysis, portfolio hygiene and engineering
reviews into one local Ops Console and a shared backend for Chat. You can work
with multiple Jira instances and preview proposed changes before applying them.

## Start Pulse

1. In Finder, open `/Users/rakothar/pulse-app`.
2. Double-click **Start Pulse.command**.
3. Pulse opens the Console in your browser at
   **[http://127.0.0.1:8080/console](http://127.0.0.1:8080/console)**.

The first start sets up a private Python environment and may take a few minutes.
It needs an internet connection to download dependencies. Later starts reuse that
environment. Python 3.11 or newer and Git must be installed; Python 3.12 is a good
choice for this setup. The launcher also recognizes the bundled Python runtime
when it is already installed on this computer.

Keep the Terminal window open while using Pulse. Press **Control+C** in that
window to stop it. If Pulse is already running in read-only mode, double-clicking
the launcher opens its existing Console instead of starting a second server.

The launcher binds to this computer only and always uses `recommend_only` mode.
It does not enable Jira writes, even if another setting requests them.

### Start from Terminal instead

```bash
cd /Users/rakothar/pulse-app
./Start\ Pulse.command
```

You do not need to activate an environment or install packages manually.

## Connect your Jira instances

Keep connection addresses and project defaults in
`config/jira_instances.json`. Keep credentials in **`.env.local`**, in the Pulse
project folder:

```text
/Users/rakothar/pulse-app/.env.local
```

For the existing `cloud` and `onprem` credential references, add:

```dotenv
# Jira Cloud: your Jira email and API token
JIRA_CLOUD_EMAIL=your-email@example.com
JIRA_CLOUD_API_TOKEN=replace-with-your-cloud-api-token

# Jira Data Center / Server: your personal access token
JIRA_ONPREM_PAT=replace-with-your-data-center-pat
```

Replace the example values with your own credentials. **Cloud uses an email and
API token; Data Center/Server uses a PAT.** They are separate connections and need
separate credentials.

Restart Pulse after changing credentials. If you want your own name used as the
reporter when creating issues, connect using your personal Jira accounts. A
service-account connection identifies that service account as the reporter.

Do not put tokens in the README, issue descriptions or Chat prompts. Keep
`.env.local` out of Git; it is included in `.gitignore`.

### Credential naming

Each entry in `config/jira_instances.json` has a `credentials` reference. Pulse
uses that reference to derive environment-variable names. For example:

```json
{
  "cloud": {
    "type": "cloud",
    "base_url": "https://example.atlassian.net",
    "credentials": "cloud",
    "default_project": "PLAT"
  },
  "onprem": {
    "type": "datacenter",
    "base_url": "https://jira.example.com",
    "credentials": "onprem",
    "default_project": "ENG"
  }
}
```

This is an example, not a replacement for your existing configuration. Preserve
any team, board, field-name and capacity settings already configured there.

If the credentials reference is `gpk2`, for example, a Data Center connection
expects `JIRA_GPK2_PAT`. The connection's display name does not override an
explicit `credentials` reference. Cloud references use `JIRA_<REFERENCE>_EMAIL`
and `JIRA_<REFERENCE>_API_TOKEN`.

Existing shell environment variables take precedence over `.env.local`, which
in turn takes precedence over `.env`.

## Use the Ops Console

### Connect to Pulse

If `MCP_BEARER_TOKEN` is configured, paste that value into the Console's
**Access token** field and select **Connect**. This is the token for the local
Pulse service, not either Jira token. The Console keeps it in memory for the
current page; you may need to enter it again after refreshing.

If no Pulse bearer token is configured, local access does not require one.

### Select the right Jira instance

Choose the instance you want to inspect before searching or reviewing work.
Confirm the project, team and sprint where applicable. An instance is a Jira
connection; a project is a workspace within that connection.

### Search and review work

Use the Console to search issues, inspect paginated results and save useful
views. JQL, when needed, is Jira's query language. For example:

```jql
project = ENG AND statusCategory != Done ORDER BY updated DESC
```

Replace `ENG` with your actual project key.

The Console also provides sprint intelligence, Portfolio Hygiene reviews,
execution previews and execution history. Check the selected instance and scope
before interpreting any report.

### Review proposed changes

Previews describe planned actions without changing Jira. Review the target,
issues and exact changes. In the normal launcher mode, Apply remains blocked.
Use execution history to inspect prior previews and results.

## Use Pulse from Chat

The Chat workflow needs your Chat environment connected to the running Pulse MCP
service. Starting the Console does not configure that connection automatically.
The local MCP endpoint is `http://127.0.0.1:8080/mcp`; remote Chat environments
need an approved deployment or tunnel that can reach Pulse.

Once Pulse tools are available in Chat, you can ask:

- “Prepare this week's engineering review for the selected instance and team.”
- “Show the current sprint and assess the next sprint's capacity.”
- “Preview closing this sprint and explain the rollover and overcommit risks.”
- “Review Portfolio Hygiene for this project and quarter.”
- “Analyze security remediation work for this project.”
- “Draft a Story in my chosen Jira instance and project, and show me the complete
  preview before creating it.”

Chat may need you to choose the instance, project, team or sprint. Avoid assuming
that similarly named projects in separate Jira instances are the same target.

### Draft a new Jira issue

Issue drafts use a separate Summary/title field and these Description sections:

1. Summary
2. User Story, with **As a**, **I want**, and **so that**
3. Description
4. Acceptance Criteria
5. Dependencies
6. Out of Scope
7. Business Value

The preview shows the chosen instance, project, issue type, description and
reporter. Reporter means the authenticated Jira account for that connection;
Chat cannot infer a different Jira account from your Chat login.

Missing project requirements must be supplied before creation. The selected
create screen must allow Description, Reporter and Labels. Labels include a
recovery marker so an uncertain creation response can be checked without
blindly creating a duplicate.

## Safety modes

| Mode | What it permits |
| --- | --- |
| `recommend_only` | Read-only reviews and previews. Jira writes are blocked. |
| `safe_apply` | Supported changes, including issue creation, through reviewed stored previews. |
| `approved_destructive` | Explicitly approved destructive workflows such as sprint closure. Issue creation uses `safe_apply`. |

**Start Pulse.command always selects `recommend_only`.** Changing `.env.local`
will not make this launcher enable writes. Deliberate write-enabled operation
requires the standard server entry point with the appropriate mode, a reviewed
preview and explicit approval. Do not enable writes merely to dismiss a warning.

If an execution has an uncertain or partial result, inspect and reconcile its
stored execution before resuming. Repeating a request can create confusion;
Pulse's durable claims and recovery checks are designed to prevent duplicates.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| The first launch takes time | Wait for setup to finish in the Terminal window. Dependencies are installed once. |
| Setup fails | Check the network connection and open `.pulse-local/setup.log`. Start again after fixing the cause. |
| Pulse exits before the Console opens | Check `.env.local`, the instance configuration and `.pulse-local/pulse.log`. The launcher prints the log location. |
| Console reports unauthorized access | Enter the configured Pulse `MCP_BEARER_TOKEN`, rather than a Jira token, and select Connect. |
| A Jira connection reports missing credentials | Check its `credentials` reference and the corresponding variables in `.env.local`, then restart Pulse. |
| Jira returns 401 or 403 | Verify token validity, account permissions and the selected instance. |
| Console opens but requests fail | Keep the first Terminal window open and check the Pulse log. |
| Port 8080 is occupied | Stop the other service or use the alternate-port command below. |
| An existing Pulse server has writes enabled | Stop it before using the read-only launcher. The launcher will not silently reuse it. |
| Your source checkout is temporarily incomplete | The launcher can use the saved tested version without changing Git history; see the next section. |

To use a different local port:

```bash
cd /Users/rakothar/pulse-app
./Start\ Pulse.command --port 8081
```

To start without automatically opening a browser:

```bash
./Start\ Pulse.command --no-browser
```

Health check: [http://127.0.0.1:8080/health](http://127.0.0.1:8080/health).
This checks that the Pulse process is running; it does not prove that Jira
credentials or every workflow are working.

## Local setup and source recovery

The launcher stores its environment, setup stamp, logs and optional source cache
under `.pulse-local/`, which is ignored by Git. It leaves the existing `.venv`
alone. Logs are created with owner-only file permissions.

When runnable source is present in the project, the launcher uses it. If the
source is missing, it can extract the saved tested commit `74e29c5` from the local
Git object database into its source cache. This is a temporary runtime fallback,
not a branch switch, checkout repair or rebase operation. It does not finish,
abort or otherwise alter an in-progress rebase.

The fallback links to your original `config` folder, `.env` and `.env.local`
without copying their credentials. Once the project's source is restored, the
launcher automatically uses it again. The saved commit must still be available
locally for the fallback to work.

## Development

Launcher code lives in `scripts/start_pulse.py`; the macOS entry point is
`Start Pulse.command`. Launcher tests use isolated fixtures, mocked startup
processes and a temporary Git repository. They do not contact Jira:

```bash
python -m pytest -q tests/test_pulse_launcher.py
```

In a complete development checkout, run the application's Python suite with
`python -m pytest` and the Console tests with `node --test tests/console.test.cjs`.
Local configuration, tokens, logs and state databases should stay out of commits.

## Record Cloud sprint work in GPK2

Open **Sprint Ops Work** in the Console, choose the Cloud board/sprint and GPK2
project, then select **Preview / refresh work**. Engineers match automatically
using their common email address; manual mappings are not required.

The workflow creates one `SBG Jira Ops Work - <Sprint name>` placeholder per user,
with a points total and links to the Cloud issues included. Stories without valid
points are listed separately. After adding their estimates in Cloud, rerun the
preview: only previously unlinked stories are appended to the same placeholder,
and their points are added once. Further runs make no duplicate changes.

The standard launcher remains read-only. Applying reviewed changes requires a
server deliberately started in `safe_apply` mode and explicit approval in the
Console. See [the Sprint Ops Work guide](docs/sprint-ops-work.md) for identity
privacy, required fields, append-only accounting and failure recovery.
