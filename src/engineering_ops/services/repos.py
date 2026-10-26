from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

from engineering_ops.models import Repository


IGNORED = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", "target", ".tox",
    ".cache", "cache", "generated", "__pycache__", ".pytest_cache",
}
MANIFEST_NAMES = {
    "requirements.txt", "package.json", "package-lock.json", "go.mod", "Dockerfile",
    "pom.xml", "poetry.lock", "pyproject.toml", "Chart.yaml", "values.yaml",
    "values.yml", "build.gradle", "build.gradle.kts", "gradle.properties",
}
K8S_EXTENSIONS = {".yaml", ".yml"}
LANGUAGE_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
}
REQ_RE = re.compile(r"^\s*([A-Za-z0-9._\-]+)\s*(?:==|>=|<=|~=|>|<)\s*([A-Za-z0-9._+\-]+)")
GO_RE = re.compile(r"^\s*([A-Za-z0-9./_\-]+)\s+v?([0-9]+\.[0-9]+(?:\.[0-9]+)?[A-Za-z0-9.\-+]*)")
FROM_RE = re.compile(r"^\s*FROM\s+([^\s]+)", re.I)
IMAGE_RE = re.compile(r"\bimage\s*:\s*[\"']?([^\"'\s]+)", re.I)
GRADLE_DEP_RE = re.compile(r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation)\s*[( ]\s*[\"']([^:\"']+):([^:\"']+):([^\"']+)[\"']")
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
VERSION_RE = re.compile(r"\b[vV]?(\d+\.\d+(?:\.\d+){0,3}(?:[-+._A-Za-z0-9]*)?)\b")
FIX_RE = re.compile(
    r"(?:fixed in|upgrade to|update to|resolved in|patched in|minimum(?: safe)? version|at least)\s+"
    r"([A-Za-z0-9._+\-/@]+)?\s*v?(\d+\.\d+(?:\.\d+){0,3}(?:[-+._A-Za-z0-9]*)?)",
    re.I,
)
PACKAGE_RE = re.compile(r"(?:package|dependency|library|module|component|image)\s*[:=]?\s*([A-Za-z0-9._+\-/@]+)", re.I)
SERVICE_RE = re.compile(r"(?:service|repo(?:sitory)?|application)\s*[:=]\s*([A-Za-z0-9._+\-/]+)", re.I)
VULNERABLE_RE = re.compile(r"(?:vulnerable|affected|current)\s+(?:version\s*)?[:=]?\s*v?([0-9]+\.[0-9][A-Za-z0-9._+\-]*)", re.I)


def _skip(path: Path) -> bool:
    return bool(set(path.parts) & IGNORED)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _split_image(image: str) -> tuple[str, str | None]:
    if "@" in image:
        name, digest = image.split("@", 1)
        return name.lower(), digest
    if ":" in image and "/" in image.rsplit(":", 1)[-1]:
        return image.lower(), None
    if ":" in image:
        name, version = image.rsplit(":", 1)
        return name.lower(), version
    return image.lower(), "latest"


def _manifest_row(path: Path, repo: Path, kind: str | None = None) -> dict[str, Any]:
    return {
        "file": str(path.relative_to(repo)),
        "kind": kind or path.name,
    }


def discover_repositories(root: Path) -> list[dict[str, Any]]:
    repos = []
    for git_dir in root.rglob(".git"):
        if _skip(git_dir.parent.relative_to(root)):
            continue
        repo = git_dir.parent
        repos.append({"name": repo.name, "path": str(repo), "relative_path": str(repo.relative_to(root))})
    if not repos:
        for child in root.iterdir():
            if child.is_dir() and not _skip(child.relative_to(root)):
                repos.append({"name": child.name, "path": str(child), "relative_path": child.name})
    return sorted(repos, key=lambda r: r["relative_path"])


def _parse_requirements(path: Path, repo: Path) -> list[dict[str, Any]]:
    rows = []
    for line in _read(path).splitlines():
        match = REQ_RE.match(line)
        if match:
            rows.append({"ecosystem": "python", "package": match.group(1).lower(), "version": match.group(2), "file": str(path.relative_to(repo))})
    return rows


def _parse_pyproject(path: Path, repo: Path) -> list[dict[str, Any]]:
    if tomllib is None:
        return []
    rows = []
    try:
        data = tomllib.loads(_read(path))
    except Exception:
        return [{"ecosystem": "python", "package": None, "version": None, "file": str(path.relative_to(repo)), "parse_error": True}]
    for dep in data.get("project", {}).get("dependencies") or []:
        match = REQ_RE.match(dep)
        if match:
            rows.append({"ecosystem": "python", "package": match.group(1).lower(), "version": match.group(2), "file": str(path.relative_to(repo))})
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies") or {}
    for name, version in poetry.items():
        if name.casefold() == "python":
            continue
        rows.append({"ecosystem": "python", "package": name.lower(), "version": str(version), "file": str(path.relative_to(repo))})
    return rows


def _parse_poetry_lock(path: Path, repo: Path) -> list[dict[str, Any]]:
    rows = []
    name = None
    version = None
    for line in _read(path).splitlines():
        if line.strip() == "[[package]]":
            if name:
                rows.append({"ecosystem": "python", "package": name.lower(), "version": version, "file": str(path.relative_to(repo))})
            name = version = None
        elif line.startswith("name = "):
            name = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("version = "):
            version = line.split("=", 1)[1].strip().strip('"')
    if name:
        rows.append({"ecosystem": "python", "package": name.lower(), "version": version, "file": str(path.relative_to(repo))})
    return rows


def _parse_package_json(path: Path, repo: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(_read(path))
    except Exception:
        return [{"ecosystem": "npm", "package": None, "version": None, "file": str(path.relative_to(repo)), "parse_error": True}]
    rows = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, version in (data.get(section) or {}).items():
            rows.append({"ecosystem": "npm", "package": name.lower(), "version": str(version), "file": str(path.relative_to(repo)), "section": section})
    return rows


def _parse_package_lock(path: Path, repo: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(_read(path))
    except Exception:
        return [{"ecosystem": "npm", "package": None, "version": None, "file": str(path.relative_to(repo)), "parse_error": True}]
    rows = []
    packages = data.get("packages") or {}
    for key, value in packages.items():
        name = value.get("name") or key.split("node_modules/")[-1]
        version = value.get("version")
        if name and version and key:
            rows.append({"ecosystem": "npm", "package": name.lower(), "version": str(version), "file": str(path.relative_to(repo))})
    for name, value in (data.get("dependencies") or {}).items():
        if value.get("version"):
            rows.append({"ecosystem": "npm", "package": name.lower(), "version": str(value["version"]), "file": str(path.relative_to(repo))})
    return rows


def _parse_go_mod(path: Path, repo: Path) -> list[dict[str, Any]]:
    rows = []
    for line in _read(path).splitlines():
        text = line.strip()
        if not text or text.startswith(("module ", "require (", ")")):
            continue
        if text.startswith("require "):
            text = text.replace("require ", "", 1)
        match = GO_RE.match(text)
        if match:
            rows.append({"ecosystem": "go", "package": match.group(1).lower(), "version": match.group(2), "file": str(path.relative_to(repo))})
    return rows


def _parse_pom(path: Path, repo: Path) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(_read(path))
    except Exception:
        return [{"ecosystem": "maven", "package": None, "version": None, "file": str(path.relative_to(repo)), "parse_error": True}]
    rows = []
    ns = {"m": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    dep_path = ".//m:dependency" if ns else ".//dependency"
    for dep in root.findall(dep_path, ns):
        def child(name: str) -> str | None:
            node = dep.find(f"m:{name}", ns) if ns else dep.find(name)
            return node.text.strip() if node is not None and node.text else None
        group = child("groupId")
        artifact = child("artifactId")
        version = child("version")
        if group and artifact:
            rows.append({"ecosystem": "maven", "package": f"{group}:{artifact}".lower(), "version": version, "file": str(path.relative_to(repo))})
    return rows


def _parse_gradle(path: Path, repo: Path) -> list[dict[str, Any]]:
    rows = []
    for match in GRADLE_DEP_RE.finditer(_read(path)):
        rows.append({"ecosystem": "gradle", "package": f"{match.group(1)}:{match.group(2)}".lower(), "version": match.group(3), "file": str(path.relative_to(repo))})
    return rows


def _parse_images(path: Path, repo: Path) -> list[dict[str, Any]]:
    rows = []
    text = _read(path)
    patterns = [FROM_RE.finditer(text)] if path.name == "Dockerfile" else [IMAGE_RE.finditer(text)]
    for iterator in patterns:
        for match in iterator:
            image = match.group(1)
            package, version = _split_image(image)
            rows.append({"ecosystem": "container", "package": package, "version": version, "image": image, "file": str(path.relative_to(repo))})
    return rows


def _parse_helm_chart(path: Path, repo: Path) -> list[dict[str, Any]]:
    rows = []
    current: dict[str, str] = {}
    for line in _read(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            if current.get("name"):
                rows.append({"ecosystem": "helm", "package": current["name"].lower(), "version": current.get("version"), "file": str(path.relative_to(repo))})
            current = {}
            stripped = stripped[2:]
        if stripped.startswith("name:"):
            current["name"] = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.startswith("version:"):
            current["version"] = stripped.split(":", 1)[1].strip().strip('"')
    if current.get("name"):
        rows.append({"ecosystem": "helm", "package": current["name"].lower(), "version": current.get("version"), "file": str(path.relative_to(repo))})
    return rows


def _parse_manifest(path: Path, repo: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packages: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    if path.name == "requirements.txt":
        packages.extend(_parse_requirements(path, repo))
    elif path.name == "pyproject.toml":
        packages.extend(_parse_pyproject(path, repo))
    elif path.name == "poetry.lock":
        packages.extend(_parse_poetry_lock(path, repo))
    elif path.name == "package.json":
        packages.extend(_parse_package_json(path, repo))
    elif path.name == "package-lock.json":
        packages.extend(_parse_package_lock(path, repo))
    elif path.name == "go.mod":
        packages.extend(_parse_go_mod(path, repo))
    elif path.name == "pom.xml":
        packages.extend(_parse_pom(path, repo))
    elif path.name in {"build.gradle", "build.gradle.kts"}:
        packages.extend(_parse_gradle(path, repo))
    elif path.name == "Dockerfile":
        images.extend(_parse_images(path, repo))
    elif path.name == "Chart.yaml":
        packages.extend(_parse_helm_chart(path, repo))
    if path.name in {"values.yaml", "values.yml"} or path.suffix in K8S_EXTENSIONS:
        images.extend(_parse_images(path, repo))
    return packages, images


def _codeowners(repo: Path) -> str | None:
    for candidate in (repo / "CODEOWNERS", repo / ".github" / "CODEOWNERS", repo / "docs" / "CODEOWNERS"):
        if candidate.exists():
            return str(candidate.relative_to(repo))
    return None


def inventory_repository(repo: Path, root: Path) -> dict[str, Any]:
    manifests: list[dict[str, Any]] = []
    packages: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    languages: set[str] = set()
    for path in repo.rglob("*"):
        rel_to_repo = path.relative_to(repo)
        if _skip(rel_to_repo):
            continue
        if path.is_file():
            language = LANGUAGE_EXTENSIONS.get(path.suffix)
            if language:
                languages.add(language)
            if path.name in MANIFEST_NAMES or path.suffix in K8S_EXTENSIONS:
                kind = "kubernetes" if path.suffix in K8S_EXTENSIONS and path.name not in {"Chart.yaml", "values.yaml", "values.yml"} else path.name
                manifests.append(_manifest_row(path, repo, kind))
                parsed_packages, parsed_images = _parse_manifest(path, repo)
                packages.extend(parsed_packages)
                images.extend(parsed_images)
    repo_name = repo.name
    for row in packages:
        row.setdefault("repo", repo_name)
    for row in images:
        row.setdefault("repo", repo_name)
    return Repository(
        name=repo_name,
        path=str(repo),
        relative_path=str(repo.relative_to(root)),
        languages=sorted(languages),
        manifests=sorted(manifests, key=lambda row: row["file"]),
        packages=sorted(_dedupe_rows(packages), key=lambda row: (row.get("ecosystem") or "", row.get("package") or "", row.get("file") or "")),
        container_images=sorted(_dedupe_rows(images), key=lambda row: (row.get("package") or "", row.get("file") or "")),
        codeowners=_codeowners(repo),
    ).to_dict()


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for row in rows:
        key = json.dumps(row, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def inventory_repositories(root: Path) -> list[dict[str, Any]]:
    repositories = discover_repositories(root)
    return [inventory_repository(Path(row["path"]), root) for row in repositories]


def scan_manifests(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for repo in inventory_repositories(root):
        for package in repo.get("packages", []):
            findings.append({**package, "repository": repo["name"], "repo_path": repo["relative_path"]})
        for image in repo.get("container_images", []):
            findings.append({**image, "repository": repo["name"], "repo_path": repo["relative_path"]})
    return findings


def extract_security_signals(text: str) -> dict[str, Any]:
    content = text or ""
    packages = {m.group(1).lower().strip(".,;") for m in PACKAGE_RE.finditer(content)}
    fixes = []
    for match in FIX_RE.finditer(content):
        package = (match.group(1) or "").lower().strip(".,;") or None
        fixes.append({"package": package, "required_version": match.group(2)})
        if package:
            packages.add(package)
    repository_hints = sorted({match.group(1).lower() for match in SERVICE_RE.finditer(content)})
    vulnerable_versions = sorted({match.group(1) for match in VULNERABLE_RE.finditer(content)})
    cves = sorted({m.group(0).upper() for m in CVE_RE.finditer(content)})
    versions = sorted({m.group(1) for m in VERSION_RE.finditer(content)})
    rationale = []
    if cves:
        rationale.append("Matched CVE identifiers")
    if packages:
        rationale.append("Matched package/component hints")
    if fixes:
        rationale.append("Matched fixed/minimum safe version phrases")
    if repository_hints:
        rationale.append("Matched repository/service hints")
    confidence = 0.0
    if cves:
        confidence += 0.25
    if packages:
        confidence += 0.25
    if fixes:
        confidence += 0.35
    if repository_hints:
        confidence += 0.15
    return {
        "cves": cves,
        "packages": sorted(packages),
        "fixed_versions": fixes,
        "affected_versions": vulnerable_versions,
        "versions": versions,
        "repository_hints": repository_hints,
        "confidence": round(min(1.0, confidence), 2),
        "rationale": rationale or ["No structured security metadata matched"],
    }
