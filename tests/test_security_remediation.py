from engineering_ops.services.repos import extract_security_signals
from engineering_ops.services.security import normalize_remediation_actions, version_at_least


def test_security_signal_extraction_includes_versions_hints_and_confidence():
    text = (
        "Operational Security Issue package: openssl affected version 3.0.12 "
        "CVE-2026-12345 fixed in openssl 3.0.15 service: api-gateway"
    )

    result = extract_security_signals(text)

    assert result["cves"] == ["CVE-2026-12345"]
    assert "openssl" in result["packages"]
    assert result["fixed_versions"] == [{"package": "openssl", "required_version": "3.0.15"}]
    assert result["affected_versions"] == ["3.0.12"]
    assert result["repository_hints"] == ["api-gateway"]
    assert result["confidence"] > 0.8


def test_remediation_grouping_matches_repositories_and_versions():
    findings = [
        {
            "issue_key": "SEC-1",
            "cves": ["CVE-2026-12345"],
            "packages": ["openssl"],
            "fixed_versions": [{"package": "openssl", "required_version": "3.0.15"}],
            "confidence": 0.85,
            "rationale": ["Matched fixed/minimum safe version phrases"],
        },
        {
            "issue_key": "SEC-2",
            "cves": ["CVE-2026-99999"],
            "packages": ["openssl"],
            "fixed_versions": [{"package": "openssl", "required_version": "3.0.15"}],
            "confidence": 0.75,
            "rationale": ["Matched CVE identifiers"],
        },
    ]
    inventory = [
        {"name": "api", "packages": [{"package": "openssl", "version": "3.0.12"}], "container_images": []},
        {"name": "worker", "packages": [{"package": "openssl", "version": "3.0.15"}], "container_images": []},
    ]

    actions = normalize_remediation_actions(findings, inventory)

    assert len(actions) == 1
    action = actions[0]
    assert action["component"] == "openssl"
    assert action["tickets_potentially_cleared"] == 2
    assert action["repositories_requiring_upgrade"] == ["api"]
    assert action["already_fixed_repositories"] == ["worker"]
    assert action["cves"] == ["CVE-2026-12345", "CVE-2026-99999"]


def test_version_comparison_handles_unknowns():
    assert version_at_least("3.0.15", "3.0.14") is True
    assert version_at_least("3.0.12", "3.0.15") is False
    assert version_at_least("latest", "3.0.15") is None
