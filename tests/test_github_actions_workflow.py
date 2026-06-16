from pathlib import Path


def test_github_actions_builds_windows_and_macos_artifacts():
    workflow = Path(".github/workflows/build.yml")

    assert workflow.exists()
    content = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in content
    assert "push:" in content
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in content
    assert "contents: write" in content
    assert "build-windows:" in content
    assert "build-macos:" in content
    assert "windows-latest" in content
    assert "macos-latest" in content
    assert "shell: pwsh" in content
    assert "shell: bash" in content
    assert ".\\scripts\\build_windows.ps1" in content
    assert "bash scripts/build_macos.sh" in content
    assert "actions/checkout@v6" in content
    assert "actions/setup-python@v6" in content
    assert "actions/upload-artifact@v7" in content
    assert "actions/download-artifact@v8" in content
    assert "actions/checkout@v4" not in content
    assert "actions/setup-python@v5" not in content
    assert "actions/upload-artifact@v4" not in content
    assert "dist/Email Order Reader" in content
    assert "dist/EmailOrderReader.exe" in content
    assert "dist/EmailOrderReader.dmg" in content
    assert "EmailOrderReader.exe#EmailOrderReader.exe" in content
    assert "EmailOrderReader.dmg#EmailOrderReader.dmg" in content
    assert "build-release:" in content
    assert "needs: [build-windows, build-macos]" in content
    release_job = content.split("  build-release:", maxsplit=1)[1]
    assert "actions/checkout@v6" in release_job
    assert "GH_TOKEN: ${{ github.token }}" in content
    assert "gh release create" in content
    assert content.count("gh release create") == 1
    assert "matrix:" not in content


def test_macos_build_script_bundles_excel_parser_dependencies():
    script = Path("scripts/build_macos.sh").read_text(encoding="utf-8")

    assert "--hidden-import openpyxl" in script
    assert "--hidden-import xlrd" in script


def test_macos_build_script_creates_direct_clickable_dmg():
    script = Path("scripts/build_macos.sh").read_text(encoding="utf-8")

    assert 'APP_PATH="dist/Email Order Reader.app"' in script
    assert 'DMG_PATH="dist/EmailOrderReader.dmg"' in script
    assert "hdiutil create" in script
    assert '-format UDZO "$DMG_PATH"' in script
