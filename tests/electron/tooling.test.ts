import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import packageJson from "../../package.json";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

describe("Electron tooling", () => {
  it("defines Electron development test commands", () => {
    expect(packageJson.scripts).toMatchObject({
      "electron:build:main": "tsc -p tsconfig.electron.json",
      "electron:dev":
        'npm run electron:build:main && concurrently -k "vite --host 127.0.0.1" "wait-on http://127.0.0.1:5173 && cross-env VITE_DEV_SERVER_URL=http://127.0.0.1:5173 electron dist-electron/main/app.js"',
      "electron:test": "vitest run",
      "electron:build": "npm run electron:clean && npm run electron:build:app && electron-builder",
      "electron:typecheck": "tsc --noEmit",
    });
  });

  it("separates fast packaging from release packaging", () => {
    expect(packageJson.scripts).toMatchObject({
      "electron:clean": "node scripts/clean_electron_outputs.mjs",
      "electron:build:app": "vite build && npm run electron:build:main",
      "electron:pack": "npm run electron:clean && npm run electron:build:app && electron-builder --dir --publish never",
      "electron:dist": "npm run electron:clean && npm run electron:build:app && electron-builder --publish never",
      "electron:build": "npm run electron:clean && npm run electron:build:app && electron-builder",
    });
  });

  it("keeps renderer-only packages out of production dependencies", () => {
    expect(packageJson.dependencies).toMatchObject({
      imapflow: expect.any(String),
      xlsx: expect.any(String),
    });
    expect(packageJson.dependencies).not.toHaveProperty("react");
    expect(packageJson.dependencies).not.toHaveProperty("react-dom");
    expect(packageJson.dependencies).not.toHaveProperty("@fluentui/react-components");
    expect(packageJson.dependencies).not.toHaveProperty("@fluentui/react-datepicker-compat");
    expect(packageJson.devDependencies).toMatchObject({
      react: expect.any(String),
      "react-dom": expect.any(String),
      "@fluentui/react-components": expect.any(String),
      "@fluentui/react-datepicker-compat": expect.any(String),
    });
  });

  it("keeps Electron source compiled entry paths aligned", () => {
    expect(packageJson.main).toBe("dist-electron/main/app.js");
    expect(packageJson.scripts["electron:dev"]).toContain("electron dist-electron/main/app.js");
    expect(packageJson.build.files).toContain("dist-electron/**/*");
  });

  it("declares app identity used by packaging", () => {
    expect(packageJson.name).toBe("order-quick-read");
    expect(packageJson.build.productName).toBe("Order Quick Read");
    expect(packageJson.build.appId).toBe("com.orderquickread.desktop");
    expect(packageJson.build.win.icon).toBe("assets/app_icon.ico");
    expect(packageJson.build.mac.icon).toBe("assets/app_icon.icns");
  });

  it("uses CommonJS preload entry that Electron can load in packaged apps", () => {
    expect(packageJson.build.files).toContain("dist-electron/**/*");
    expect(packageJson.scripts["electron:build:main"]).toBe("tsc -p tsconfig.electron.json");
    expect(existsSync(path.join(repoRoot, "electron/preload/index.cts"))).toBe(true);
  });

  it("does not keep the retired Python implementation or parity docs", () => {
    const retiredPaths = [
      "pyproject.toml",
      "src/email_order_reader",
      "scripts/generate_icons.py",
      "scripts/stamp_build_info.py",
      "docs/electron-parity-checklist.md",
      "docs/superpowers",
      "tests/test_email_client.py",
      "tests/test_excel_parser.py",
      "tests/test_github_actions_workflow.py",
      "tests/test_icon_assets.py",
      "tests/test_legacy_pyside_removed.py",
      "tests/test_models.py",
      "tests/test_package_import.py",
      "tests/test_scan_service.py",
      "tests/test_self_update.py",
      "tests/test_settings.py",
      "tests/test_updates.py",
    ];

    expect(retiredPaths.filter((retiredPath) => existsSync(path.join(repoRoot, retiredPath)))).toEqual([]);
  });
});
