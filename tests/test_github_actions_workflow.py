from pathlib import Path


def test_github_actions_builds_windows_and_macos_artifacts():
    workflow = Path(".github/workflows/build.yml")

    assert workflow.exists()
    content = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in content
    assert "push:" in content
    assert "windows-latest" in content
    assert "macos-latest" in content
    assert ".\\scripts\\build_windows.ps1" in content
    assert "bash scripts/build_macos.sh" in content
    assert "actions/upload-artifact@v4" in content
    assert "dist/Email Order Reader" in content


def test_macos_build_script_bundles_excel_parser_dependencies():
    script = Path("scripts/build_macos.sh").read_text(encoding="utf-8")

    assert "--hidden-import openpyxl" in script
    assert "--hidden-import xlrd" in script
