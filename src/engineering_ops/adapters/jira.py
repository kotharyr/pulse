from __future__ import annotations

from typing import Any
import httpx

from engineering_ops.config import JiraInstanceConfig, resolve_credentials, settings


class JiraError(RuntimeError):
    pass


class JiraClient:
    def __init__(self, name: str, cfg: JiraInstanceConfig):
        self.name, self.cfg = name, cfg
        credential = resolve_credentials(name, cfg)
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
        return self.cfg.api_version

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            r = self.http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise JiraError(f"{self.name}: {method} {path} -> network error: {exc}") from exc

        if 300 <= r.status_code < 400:
            location = r.headers.get("location", "<missing Location header>")
            raise JiraError(
                f"{self.name}: {method} {path} -> {r.status_code} redirect to {location}. "
                "Redirects are not followed automatically so credentials are never forwarded to an unexpected host."
            )
        if r.status_code >= 400:
            raise JiraError(f"{self.name}: {method} {path} -> {r.status_code}: {r.text[:1200]}")
        if not r.content:
            return {}

        content_type = r.headers.get("content-type", "").lower()
        if "json" not in content_type:
            preview = r.text[:500].replace("\n", " ")
            raise JiraError(
                f"{self.name}: {method} {path} returned non-JSON content-type {content_type or '<none>'}: {preview}"
            )
        try:
            return r.json()
        except ValueError as exc:
            raise JiraError(f"{self.name}: {method} {path} returned invalid JSON: {r.text[:500]}") from exc

    def myself(self):
        return self.request("GET", f"/rest/api/{self.platform_api_version}/myself")

    def fields(self):
        return self.request("GET", f"/rest/api/{self.platform_api_version}/field")

    def projects(self, limit: int = 200):
        if self.cfg.kind == "cloud":
            data = self.request("GET", "/rest/api/3/project/search", params={"maxResults": limit})
            return data.get("values", [])
        data = self.request("GET", f"/rest/api/{self.platform_api_version}/project")
        return data[:limit] if isinstance(data, list) else data

    def search(self, jql: str, fields: list[str], limit: int = 500):
        issues: list[dict[str, Any]] = []
        if self.cfg.kind == "cloud":
            token = None
            while len(issues) < limit:
                payload = {"jql": jql, "maxResults": min(100, limit - len(issues)), "fields": fields}
                if token:
                    payload["nextPageToken"] = token
                data = self.request("POST", "/rest/api/3/search/jql", json=payload)
                batch = data.get("issues", [])
                issues.extend(batch)
                token = data.get("nextPageToken")
                if not batch or not token:
                    break
        else:
            start = 0
            while len(issues) < limit:
                payload = {
                    "jql": jql,
                    "startAt": start,
                    "maxResults": min(100, limit - len(issues)),
                    "fields": fields,
                }
                data = self.request("POST", "/rest/api/2/search", json=payload)
                batch = data.get("issues", [])
                issues.extend(batch)
                start += len(batch)
                if not batch or start >= data.get("total", 0):
                    break
        return issues

    def get_issue(self, key: str, fields: list[str] | None = None):
        params = {"fields": ",".join(fields)} if fields else None
        return self.request("GET", f"/rest/api/{self.platform_api_version}/issue/{key}", params=params)

    def editmeta(self, key: str):
        return self.request("GET", f"/rest/api/{self.platform_api_version}/issue/{key}/editmeta")

    def update_issue(self, key: str, fields: dict[str, Any]):
        return self.request("PUT", f"/rest/api/{self.platform_api_version}/issue/{key}", json={"fields": fields})

    def create_issue(self, fields: dict[str, Any]):
        return self.request("POST", f"/rest/api/{self.platform_api_version}/issue", json={"fields": fields})

    def sprint(self, sprint_id: int):
        return self.request("GET", f"/rest/agile/1.0/sprint/{sprint_id}")

    def update_sprint(self, sprint_id: int, fields: dict[str, Any]):
        return self.request("POST", f"/rest/agile/1.0/sprint/{sprint_id}", json=fields)

    def sprint_issues(self, sprint_id: int, limit: int = 1000):
        fields = [
            "summary", "description", "status", "assignee", "issuetype", "project",
            "parent", "labels", self.cfg.story_points_field_name,
        ]
        return self.search(f"sprint = {sprint_id}", fields, limit)

    def move_issues_to_sprint(self, sprint_id: int, issue_keys: list[str]):
        results = []
        for i in range(0, len(issue_keys), 50):
            batch = issue_keys[i:i + 50]
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
