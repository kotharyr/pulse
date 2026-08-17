from engineering_ops.services.repos import inventory_repositories, scan_manifests


def test_repository_inventory_parses_manifests_and_ignores_generated_dirs(tmp_path):
    repo = tmp_path / "service-a"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hi')", encoding="utf-8")
    (repo / "requirements.txt").write_text("urllib3==2.0.0\n", encoding="utf-8")
    (repo / "package.json").write_text('{"dependencies":{"react":"18.2.0"}}', encoding="utf-8")
    (repo / "go.mod").write_text("module x\nrequire github.com/gin-gonic/gin v1.9.1\n", encoding="utf-8")
    (repo / "Dockerfile").write_text("FROM openssl:3.0.12\n", encoding="utf-8")
    (repo / "Chart.yaml").write_text("dependencies:\n- name: redis\n  version: 17.0.0\n", encoding="utf-8")
    (repo / "deployment.yaml").write_text("image: nginx:1.25.0\n", encoding="utf-8")
    (repo / ".github").mkdir()
    (repo / ".github" / "CODEOWNERS").write_text("* @team/platform\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "package.json").write_text('{"dependencies":{"ignored":"1.0.0"}}', encoding="utf-8")

    inventory = inventory_repositories(tmp_path)

    assert len(inventory) == 1
    row = inventory[0]
    packages = {pkg["package"]: pkg["version"] for pkg in row["packages"]}
    assert packages["urllib3"] == "2.0.0"
    assert packages["react"] == "18.2.0"
    assert packages["github.com/gin-gonic/gin"] == "1.9.1"
    assert packages["redis"] == "17.0.0"
    assert "ignored" not in packages
    assert row["container_images"][0]["package"] == "nginx"
    assert any(image["package"] == "openssl" for image in row["container_images"])
    assert row["codeowners"] == ".github/CODEOWNERS"
    assert "Python" in row["languages"]


def test_scan_manifests_keeps_flat_package_output(tmp_path):
    repo = tmp_path / "service-a"
    (repo / ".git").mkdir(parents=True)
    (repo / "requirements.txt").write_text("urllib3==2.0.0\n", encoding="utf-8")

    rows = scan_manifests(tmp_path)

    assert rows[0]["package"] == "urllib3"
    assert rows[0]["repository"] == "service-a"
