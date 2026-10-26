# Repository Guidelines

## Project Structure & Module Organization
`src/engineering_ops` contains the backend. `server.py` defines MCP tools/routes; `config.py` and `auth.py` handle settings/tokens; `adapters/jira.py` owns Jira connectors; `services/` contains field, sprint, health, and repository logic. Tests live in `tests/test_*.py`, docs in `docs/`, scripts in `scripts/`, and Jira templates/configuration in `config/`.

## Platform Architecture Rules
Default to `MODE=recommend_only`: previews are allowed, writes are blocked. Every write path must preview first and apply only the reviewed plan; sprint close and destructive flows require `MODE=approved_destructive`. User-facing MCP tools and UI clients must use human-readable Jira field names/values; keep Jira field IDs inside resolver/update code. Keep Cloud, Data Center, and Server differences behind `JiraProviderPlugin`, `JiraClient`, and `register_jira_provider`. Business capabilities call connectors, not raw REST paths or auth. ChatGPT Enterprise and the future Ops Console must share backend logic; only presentation should differ.

## Build, Test, and Development Commands
- `./scripts/install.sh`: create `.venv`, install editable dev dependencies, and copy example config files if missing.
- `source .venv/bin/activate`: activate the local environment before running Python tools directly.
- `pytest`: run the full suite configured in `pyproject.toml`.
- `./scripts/check.sh`: validate local configuration and Jira credential readiness.
- `./scripts/dev.sh`: start the MCP development server with `mcp dev`.
- `./scripts/run.sh`: run the service via `python -m engineering_ops.server`.
- `python scripts/migrate_config_v1.py`: migrate older instance config and create a pre-v1 backup.

## Coding Style & Naming Conventions
Use Python 3.11+ with 4-space indentation, type hints, and small functions. Use `snake_case` for modules, variables, and functions; `PascalCase` for classes; and `test_*.py` files with `test_*` functions. No formatter/linter is configured, so preserve local import order: standard library, third-party, then `engineering_ops`.

## Testing Guidelines
Pytest is required for new functionality. Add focused tests near changed behavior, especially for safety modes, config parsing, Jira field/value resolution, provider differences, sprint capacity math, and repository scanning. Prefer isolated settings objects, fixtures, and fake Jira responses over live Jira calls. No coverage threshold is enforced.

## Commit & Pull Request Guidelines
History uses short descriptive summaries without strict prefixes, such as `Initial Engineering Operations Platform baseline`. Continue with concise imperative or scope-first messages, for example `Add sprint capacity tests`. Pull requests should include motivation, behavior changes, test/check results, and config or migration notes. Link related issues when available.

## Security & Configuration Tips
Never commit `.env`, `.env.local`, API tokens, passwords, or personal Jira details. Treat `config/jira_instances.json` as local environment configuration; prefer `config/jira_instances.example.json` for shared defaults.
