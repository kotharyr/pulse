from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

IGNORED = {".git", ".venv", "venv", "node_modules", "dist", "build", "target", ".tox"}
REQ_RE = re.compile(r"^\s*([A-Za-z0-9._\-]+)\s*(?:==|>=|<=|~=|>|<)\s*([A-Za-z0-9._+\-]+)")
GO_RE = re.compile(r"^\s*([A-Za-z0-9./_\-]+)\s+v?([0-9]+\.[0-9]+(?:\.[0-9]+)?[A-Za-z0-9.\-+]*)")
FROM_RE = re.compile(r"^\s*FROM\s+([^\s]+)", re.I)
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
VERSION_RE = re.compile(r"\b[vV]?(\d+\.\d+(?:\.\d+){0,3}(?:[-+._A-Za-z0-9]*)?)\b")
FIX_RE = re.compile(r"(?:fixed in|upgrade to|update to|resolved in|patched in|minimum version)\s+([A-Za-z0-9._+\-/@]+)?\s*v?(\d+\.\d+(?:\.\d+){0,3}(?:[-+._A-Za-z0-9]*)?)", re.I)
PACKAGE_RE = re.compile(r"(?:package|dependency|library|module|component)\s*[:=]?\s*([A-Za-z0-9._+\-/@]+)", re.I)


def _skip(path: Path) -> bool:
    return bool(set(path.parts) & IGNORED)


def discover_repositories(root: Path) -> list[dict[str, Any]]:
    repos = []
    for git_dir in root.rglob(".git"):
        if _skip(git_dir.parent.relative_to(root)):
            continue
        repo = git_dir.parent
        repos.append({"name": repo.name, "path": str(repo), "relative_path": str(repo.relative_to(root))})
    if not repos:
        # Also support source trees where .git directories are unavailable.
        for child in root.iterdir():
            if child.is_dir() and not _skip(child.relative_to(root)):
                repos.append({"name": child.name, "path": str(child), "relative_path": child.name})
    return sorted(repos, key=lambda r: r["relative_path"])


def scan_manifests(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    targets = {"requirements.txt", "package.json", "package-lock.json", "go.mod", "Dockerfile", "pom.xml", "poetry.lock"}
    for path in root.rglob("*"):
        if not path.is_file() or path.name not in targets or _skip(path.relative_to(root)):
            continue
        rel = str(path.relative_to(root))
        if path.name == "requirements.txt":
            for line in path.read_text(errors="ignore").splitlines():
                m = REQ_RE.match(line)
                if m:
                    findings.append({"ecosystem": "python", "package": m.group(1).lower(), "version": m.group(2), "file": rel})
        elif path.name == "package.json":
            try:
                data = json.loads(path.read_text(errors="ignore"))
                for section in ("dependencies", "devDependencies", "optionalDependencies"):
                    for name, version in (data.get(section) or {}).items():
                        findings.append({"ecosystem": "npm", "package": name.lower(), "version": str(version), "file": rel})
            except Exception:
                findings.append({"ecosystem": "npm", "package": None, "version": None, "file": rel, "parse_error": True})
        elif path.name == "go.mod":
            for line in path.read_text(errors="ignore").splitlines():
                m = GO_RE.match(line)
                if m:
                    findings.append({"ecosystem": "go", "package": m.group(1).lower(), "version": m.group(2), "file": rel})
        elif path.name == "Dockerfile":
            for line in path.read_text(errors="ignore").splitlines():
                m = FROM_RE.match(line)
                if m:
                    image = m.group(1)
                    findings.append({"ecosystem": "container", "package": image.split(":")[0].lower(), "version": image.split(":",1)[1] if ":" in image else "latest", "file": rel})
        else:
            findings.append({"ecosystem": path.name, "package": None, "version": None, "file": rel})
    return findings


def extract_security_signals(text: str) -> dict[str, Any]:
    packages = {m.group(1).lower() for m in PACKAGE_RE.finditer(text or "")}
    fixes = []
    for m in FIX_RE.finditer(text or ""):
        package = (m.group(1) or "").lower() or None
        fixes.append({"package": package, "required_version": m.group(2)})
        if package:
            packages.add(package)
    return {
        "cves": sorted({m.group(0).upper() for m in CVE_RE.finditer(text or "")}),
        "packages": sorted(packages),
        "fixed_versions": fixes,
        "versions": sorted({m.group(1) for m in VERSION_RE.finditer(text or "")}),
    }
