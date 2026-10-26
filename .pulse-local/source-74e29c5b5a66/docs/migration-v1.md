# Migrating to Engineering Operations Platform v1.0

v1.0 removes HTTP authentication mechanics and REST API versions from ordinary Jira instance configuration.

## Before

```json
{
  "cloud": {
    "kind": "cloud",
    "base_url": "https://example.atlassian.net",
    "auth": {
      "mode": "basic",
      "username_env": "JIRA_CLOUD_EMAIL",
      "secret_env": "JIRA_CLOUD_API_TOKEN"
    }
  }
}
```

## After

```json
{
  "cloud": {
    "type": "cloud",
    "base_url": "https://example.atlassian.net",
    "credentials": "cloud"
  }
}
```

The `credentials` value maps automatically to environment variables:

- `credentials: cloud` + `type: cloud` -> `JIRA_CLOUD_EMAIL`, `JIRA_CLOUD_API_TOKEN`
- `credentials: onprem` + `type: datacenter` -> `JIRA_ONPREM_PAT` (preferred)
- Data Center fallback -> `JIRA_ONPREM_USERNAME`, `JIRA_ONPREM_PASSWORD`

Run:

```bash
python scripts/migrate_config_v1.py
```

The script backs up the previous file as `config/jira_instances.pre-v1.json` before changing it.

If a legacy `auth` block uses environment-variable names that do not match the new
credential convention, the migration preserves that block and prints a warning.
This keeps existing credentials working until they are renamed deliberately.
