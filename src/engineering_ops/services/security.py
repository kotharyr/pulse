from __future__ import annotations

import re
from statistics import mean
from typing import Any

from engineering_ops.models import RemediationAction, SecurityFinding
from engineering_ops.services.repos import extract_security_signals


def _clean_component(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().strip(".,;").casefold()


def _version_parts(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    numbers = re.findall(r"\d+", value)
    if not numbers:
        return None
    return tuple(int(part) for part in numbers[:4])


def version_at_least(current: str | None, required: str | None) -> bool | None:
    current_parts = _version_parts(current)
    required_parts = _version_parts(required)
    if current_parts is None or required_parts is None:
        return None
    width = max(len(current_parts), len(required_parts))
    return current_parts + (0,) * (width - len(current_parts)) >= required_parts + (0,) * (width - len(required_parts))


def finding_from_issue(issue: dict[str, Any], text: str) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    signals = extract_security_signals(text)
    return SecurityFinding(
        issue_key=issue.get("key"),
        summary=fields.get("summary"),
        cves=signals["cves"],
        packages=signals["packages"],
        fixed_versions=signals["fixed_versions"],
        affected_versions=signals["affected_versions"],
        repository_hints=signals["repository_hints"],
        confidence=signals["confidence"],
        rationale=signals["rationale"],
    ).to_dict()


def _flatten_inventory(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for repo in inventory:
        repo_name = repo.get("name")
        for package in repo.get("packages", []):
            rows.append({**package, "repository": repo_name, "kind": "package"})
        for image in repo.get("container_images", []):
            rows.append({**image, "repository": repo_name, "kind": "base_image"})
    return rows


def _matches(component: str, package_name: str | None) -> bool:
    if not package_name:
        return False
    normalized = package_name.casefold()
    component = component.casefold()
    return normalized == component or normalized.endswith(f"/{component}") or normalized.endswith(f":{component}")


def _group_keys(finding: dict[str, Any]) -> list[tuple[str, str | None]]:
    keys: list[tuple[str, str | None]] = []
    packages = [_clean_component(row) for row in finding.get("packages", [])]
    packages = [row for row in packages if row]
    for fix in finding.get("fixed_versions") or []:
        package = _clean_component(fix.get("package")) or (packages[0] if len(packages) == 1 else None)
        if package:
            keys.append((package, fix.get("required_version")))
    if not keys:
        keys.extend((package, None) for package in packages)
    return list(dict.fromkeys(keys))


def normalize_remediation_actions(
    findings: list[dict[str, Any]],
    repository_inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    repo_rows = _flatten_inventory(repository_inventory)
    groups: dict[tuple[str, str | None], dict[str, Any]] = {}
    manual_review_repos = sorted({repo.get("name") for repo in repository_inventory if repo.get("name")})
    for finding in findings:
        for component, required_version in _group_keys(finding):
            group = groups.setdefault(
                (component, required_version),
                {
                    "component": component,
                    "required_version": required_version,
                    "findings": [],
                    "issues": set(),
                    "cves": set(),
                    "confidence": [],
                    "rationale": set(),
                },
            )
            group["findings"].append(finding)
            group["issues"].add(finding.get("issue_key"))
            group["cves"].update(finding.get("cves") or [])
            group["confidence"].append(float(finding.get("confidence") or 0))
            group["rationale"].update(finding.get("rationale") or [])

    actions = []
    for (component, required_version), group in groups.items():
        matches = [row for row in repo_rows if _matches(component, row.get("package"))]
        affected_repos = sorted({row.get("repository") for row in matches if row.get("repository")})
        current_versions = sorted({str(row.get("version")) for row in matches if row.get("version")})
        already_fixed = set()
        requiring_upgrade = set()
        unknown = set()
        for row in matches:
            repo = row.get("repository")
            if not repo:
                continue
            comparison = version_at_least(row.get("version"), required_version)
            if required_version is None or comparison is None:
                unknown.add(repo)
            elif comparison:
                already_fixed.add(repo)
            else:
                requiring_upgrade.add(repo)
        if not matches:
            unknown.update(manual_review_repos)
        confidence = round(min(1.0, mean(group["confidence"] or [0]) + (0.15 if matches else 0)), 2)
        action_type = "base_image_upgrade" if any(row.get("kind") == "base_image" for row in matches) or "/" in component else "package_upgrade"
        actions.append(RemediationAction(
            component=component,
            required_version=required_version,
            action_type=action_type,
            affected_jira_issues=sorted(issue for issue in group["issues"] if issue),
            cves=sorted(group["cves"]),
            affected_repositories=affected_repos,
            current_detected_versions=current_versions,
            already_fixed_repositories=sorted(already_fixed),
            repositories_requiring_upgrade=sorted(requiring_upgrade),
            unknown_repositories=sorted(unknown - already_fixed - requiring_upgrade),
            tickets_potentially_cleared=len({issue for issue in group["issues"] if issue}),
            confidence=confidence,
            parsing_rationale=sorted(group["rationale"]),
        ).to_dict())
    return sorted(actions, key=lambda row: (-row["tickets_potentially_cleared"], -row["confidence"], row["component"]))
