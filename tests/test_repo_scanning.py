from engineering_ops.services.repos import extract_security_signals


def test_extract_security_signals():
    result = extract_security_signals("package: urllib3 CVE-2025-12345 fixed in urllib3 2.2.3")
    assert "urllib3" in result["packages"]
    assert "CVE-2025-12345" in result["cves"]
    assert any(x["required_version"] == "2.2.3" for x in result["fixed_versions"])
