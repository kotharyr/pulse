from __future__ import annotations

import re
from threading import RLock
from typing import Any, Protocol

import httpx

from engineering_ops.config import JiraInstanceConfig, ResolvedCredential, resolve_credentials, settings


class JiraError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        method: str | None = None,
        path: str | None = None,
        response_text: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.path = path
        self.response_text = response_text


class JiraProviderPlugin(Protocol):
    """Platform-specific Jira behavior registered by instance type."""

    name: str
    api_version: str

    def authentication(self, credential: ResolvedCredential) -> tuple[dict[str, str], Any]: ...

    def description_value(self, text: str) -> Any: ...

    def projects(self, jira: "JiraClient", limit: int) -> Any: ...

    def search(self, jira: "JiraClient", jql: str, fields: list[str], limit: int) -> list[dict[str, Any]]: ...


def _authentication(credential: ResolvedCredential) -> tuple[dict[str, str], Any]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    auth = None
    if credential.method in {"cloud_api_token", "basic_fallback"}:
        auth = (credential.username or "", credential.secret)
    elif credential.method == "personal_access_token":
        headers["Authorization"] = f"Bearer {credential.secret}"
    elif credential.method == "legacy":
        if credential.username:
            auth = (credential.username, credential.secret)
        else:
            headers["Authorization"] = f"Bearer {credential.secret}"
    return headers, auth


EXACT_ISSUE_JQL_RE = re.compile(
    r"^\s*(?:issue|issuekey|key)\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([A-Z][A-Z0-9_]*-\d+))(?:\s+ORDER\s+BY\s+.+)?\s*$",
    re.I,
)


def _single_issue_key_from_jql(jql: str) -> str | None:
    match = EXACT_ISSUE_JQL_RE.match(jql)
    if not match:
        return None
    candidate = next((group for group in match.groups() if group), "").strip()
    if re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", candidate, re.I):
        return candidate.upper()
    return None


class CloudJiraProvider:
    name = "cloud"
    api_version = "3"

    authentication = staticmethod(_authentication)

    def description_value(self, text: str) -> Any:
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": line}]}
                if line
                else {"type": "paragraph", "content": []}
                for line in text.splitlines()
            ],
        }

    def projects(self, jira: "JiraClient", limit: int) -> Any:
        data = jira.request("GET", "/rest/api/3/project/search", params={"maxResults": limit})
        return data.get("values", [])

    def search(self, jira: "JiraClient", jql: str, fields: list[str], limit: int) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        token = None
        while len(issues) < limit:
            payload: dict[str, Any] = {
                "jql": jql,
                "maxResults": min(100, limit - len(issues)),
                "fields": fields,
            }
            if token:
                payload["nextPageToken"] = token
            data = jira.request("POST", "/rest/api/3/search/jql", json=payload)
            batch = data.get("issues", [])
            issues.extend(batch)
            next_token = data.get("nextPageToken")
            if not batch or not next_token:
                break
            if next_token == token:
                raise JiraError(f"{jira.name}: Cloud search returned a repeated nextPageToken")
            token = next_token
        return issues


class DataCenterJiraProvider:
    name = "datacenter"
    api_version = "2"

    authentication = staticmethod(_authentication)

    def description_value(self, text: str) -> Any:
        return text

    def projects(self, jira: "JiraClient", limit: int) -> Any:
        data = jira.request("GET", "/rest/api/2/project")
        return data[:limit] if isinstance(data, list) else data

    def _search_page(self, jira: "JiraClient", jql: str, fields: list[str], start: int, max_results: int) -> Any:
        payload = {
            "jql": jql,
            "startAt": start,
            "maxResults": max_results,
            "fields": fields,
        }
        try:
            return jira.request("POST", "/rest/api/2/search", json=payload)
        except JiraError as exc:
            if exc.status_code != 404:
                raise
            params = {
                "jql": jql,
                "startAt": start,
                "maxResults": max_results,
                "fields": ",".join(fields),
            }
            try:
                return jira.request("GET", "/rest/api/2/search", params=params)
            except JiraError as get_exc:
                if get_exc.status_code == 404:
                    raise get_exc from exc
                raise

    def search(self, jira: "JiraClient", jql: str, fields: list[str], limit: int) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        start = 0
        while len(issues) < limit:
            try:
                data = self._search_page(jira, jql, fields, start, min(100, limit - len(issues)))
            except JiraError as exc:
                issue_key = _single_issue_key_from_jql(jql)
                if exc.status_code == 404 and issue_key and not issues:
                    return [jira.get_issue(issue_key, fields)]
                raise
            batch = data.get("issues", [])
            issues.extend(batch)
            start += len(batch)
            if not batch or start >= data.get("total", 0):
                break
        return issues


JIRA_PROVIDER_PLUGINS: dict[str, JiraProviderPlugin] = {
    "cloud": CloudJiraProvider(),
    "datacenter": DataCenterJiraProvider(),
    "server": DataCenterJiraProvider(),
}


def register_jira_provider(instance_type: str, provider: JiraProviderPlugin) -> None:
    """Register or replace a Jira provider, enabling separately packaged adapters."""
    JIRA_PROVIDER_PLUGINS[instance_type] = provider


class JiraClient:
    def __init__(self, name: str, cfg: JiraInstanceConfig):
        self.name, self.cfg = name, cfg
        try:
            self.provider = JIRA_PROVIDER_PLUGINS[cfg.instance_type]
        except KeyError as exc:
            raise JiraError(f"No Jira provider registered for {cfg.instance_type!r}") from exc
        credential = resolve_credentials(name, cfg)
        headers, auth = self.provider.authentication(credential)

        self.http = httpx.Client(
            base_url=cfg.base_url,
            auth=auth,
            headers=headers,
            verify=cfg.verify_ssl,
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
        )

    @property
    def platform_api_version(self) -> str:
        return self.provider.api_version

    def close(self) -> None:
        self.http.close()

    def _request_path_candidates(self, path: str) -> list[str]:
        normalized = path.lstrip("/")
        candidates = [normalized]
        base_path = httpx.URL(self.cfg.base_url).path.strip("/")
        if (
            self.cfg.instance_type in {"datacenter", "server"}
            and not base_path
            and normalized.startswith(("rest/api/", "rest/agile/"))
        ):
            candidates.append(f"jira/{normalized}")
        return candidates

    def _request_once(self, method: str, path: str, **kwargs: Any) -> Any:
        display_path = f"/{path.lstrip('/')}"
        try:
            r = self.http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise JiraError(f"{self.name}: {method} {display_path} -> network error: {exc}", method=method, path=display_path) from exc

        if 300 <= r.status_code < 400:
            location = r.headers.get("location", "<missing Location header>")
            raise JiraError(
                f"{self.name}: {method} {display_path} -> {r.status_code} redirect to {location}. "
                "Redirects are not followed automatically so credentials are never forwarded to an unexpected host.",
                status_code=r.status_code,
                method=method,
                path=display_path,
                response_text=r.text[:1200],
            )
        if r.status_code >= 400:
            raise JiraError(
                f"{self.name}: {method} {display_path} -> {r.status_code}: {r.text[:1200]}",
                status_code=r.status_code,
                method=method,
                path=display_path,
                response_text=r.text[:1200],
            )
        if not r.content:
            return {}

        content_type = r.headers.get("content-type", "").lower()
        if "json" not in content_type:
            preview = r.text[:500].replace("\n", " ")
            raise JiraError(
                f"{self.name}: {method} {display_path} returned non-JSON content-type {content_type or '<none>'}: {preview}"
            )
        try:
            return r.json()
        except ValueError as exc:
            raise JiraError(f"{self.name}: {method} {display_path} returned invalid JSON: {r.text[:500]}") from exc

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_not_found: JiraError | None = None
        for request_path in self._request_path_candidates(path):
            try:
                return self._request_once(method, request_path, **kwargs)
            except JiraError as exc:
                if exc.status_code == 404:
                    last_not_found = exc
                    continue
                raise
        if last_not_found:
            raise last_not_found
        raise JiraError(f"{self.name}: {method} {path} could not be sent", method=method, path=path)

    def myself(self):
        return self.request("GET", f"/rest/api/{self.platform_api_version}/myself")

    def fields(self):
        return self.request("GET", f"/rest/api/{self.platform_api_version}/field")

    def projects(self, limit: int = 200):
        return self.provider.projects(self, limit)

    def search(self, jql: str, fields: list[str], limit: int = 500):
        if limit <= 0:
            return []
        return self.provider.search(self, jql, fields, limit)

    def get_issue(self, key: str, fields: list[str] | None = None):
        params = {"fields": ",".join(fields)} if fields else None
        return self.request("GET", f"/rest/api/{self.platform_api_version}/issue/{key}", params=params)

    def editmeta(self, key: str):
        return self.request("GET", f"/rest/api/{self.platform_api_version}/issue/{key}/editmeta")

    def update_issue(self, key: str, fields: dict[str, Any]):
        return self.request("PUT", f"/rest/api/{self.platform_api_version}/issue/{key}", json={"fields": fields})

    def create_issue(self, fields: dict[str, Any]):
        return self.request("POST", f"/rest/api/{self.platform_api_version}/issue", json={"fields": fields})

    def description_value(self, text: str) -> Any:
        return self.provider.description_value(text)

    def transition_issue_to_status(self, issue_key: str, status_name: str) -> dict[str, Any]:
        data = self.request("GET", f"/rest/api/{self.platform_api_version}/issue/{issue_key}/transitions")
        matches = [
            transition
            for transition in data.get("transitions", [])
            if ((transition.get("to") or {}).get("name") or "").casefold() == status_name.casefold()
        ]
        if len(matches) != 1:
            names = sorted({((transition.get("to") or {}).get("name") or "") for transition in matches if transition.get("to")})
            raise ValueError(f"Could not resolve transition to {status_name!r} for {issue_key}; matching statuses={names}")
        self.request(
            "POST",
            f"/rest/api/{self.platform_api_version}/issue/{issue_key}/transitions",
            json={"transition": {"id": matches[0]["id"]}},
        )
        return {"issue_key": issue_key, "to_status": status_name}

    def sprint(self, sprint_id: int):
        return self.request("GET", f"/rest/agile/1.0/sprint/{sprint_id}")

    def update_sprint(self, sprint_id: int, fields: dict[str, Any]):
        return self.request("POST", f"/rest/agile/1.0/sprint/{sprint_id}", json=fields)

    def sprint_issues(self, sprint_id: int, limit: int = 1000, story_points_field_id: str | None = None):
        fields = [
            "summary", "description", "status", "assignee", "issuetype", "project",
            "parent", "labels",
        ]
        if story_points_field_id:
            fields.append(story_points_field_id)
        return self.search(f"sprint = {sprint_id}", fields, limit)

    def move_issues_to_sprint(self, sprint_id: int, issue_keys: list[str]):
        results = []
        batch_size = min(settings.bulk_batch_size, 50)
        for i in range(0, len(issue_keys), batch_size):
            batch = issue_keys[i:i + batch_size]
            self.request("POST", f"/rest/agile/1.0/sprint/{sprint_id}/issue", json={"issues": batch})
            results.append({"count": len(batch), "issues": batch})
        return results

    def boards(self, project_key: str | None = None, limit: int = 100):
        params: dict[str, Any] = {"maxResults": limit}
        if project_key:
            params["projectKeyOrId"] = project_key
        data = self.request("GET", "/rest/agile/1.0/board", params=params)
        return data.get("values", [])

    def board_sprints(self, board_id: int, state: str | None = None, limit: int = 100):
        start = 0
        rows = []
        while len(rows) < limit:
            params: dict[str, Any] = {"startAt": start, "maxResults": min(50, limit - len(rows))}
            if state:
                params["state"] = state
            data = self.request("GET", f"/rest/agile/1.0/board/{board_id}/sprint", params=params)
            batch = data.get("values", [])
            rows.extend(batch)
            if not batch or data.get("isLast", True):
                break
            start += len(batch)
        return rows


class JiraClientManager:
    """Owns reusable Jira clients and closes them as one lifecycle unit."""

    def __init__(self):
        self._clients: dict[str, JiraClient] = {}
        self._lock = RLock()

    def get(self, name: str, cfg: JiraInstanceConfig) -> JiraClient:
        with self._lock:
            current = self._clients.get(name)
            if current is None or current.cfg != cfg:
                if current is not None:
                    current.close()
                current = JiraClient(name, cfg)
                self._clients[name] = current
            return current

    def close(self) -> None:
        with self._lock:
            for jira in self._clients.values():
                jira.close()
            self._clients.clear()
