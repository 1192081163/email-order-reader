import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";
import packageJson from "../../package.json";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

describe("Electron tooling", () => {
  it("defines the Electron development and test commands", () => {
    expect(packageJson.scripts).toMatchObject({
      "electron:build:main": "tsc -p tsconfig.electron.json",
      "electron:dev": "npm run electron:build:main && concurrently -k \"vite --host 127.0.0.1\" \"wait-on http://127.0.0.1:5173 && cross-env VITE_DEV_SERVER_URL=http://127.0.0.1:5173 electron dist-electron/main/app.js\"",
      "electron:test": "vitest run",
      "electron:build": "vite build && npm run electron:build:main && electron-builder",
      "electron:typecheck": "tsc --noEmit",
    });
  });

  it("keeps the Electron source and compiled entry paths aligned", () => {
    expect(packageJson.main).toBe("dist-electron/main/app.js");
    expect(packageJson.scripts["electron:dev"]).toContain("electron dist-electron/main/app.js");
    expect(packageJson.build.files).toContain("dist-electron/**/*");
  });

  it("declares the app identity used for packaging", () => {
    expect(packageJson.name).toBe("order-quick-read");
    expect(packageJson.build.productName).toBe("Order Quick Read");
    expect(packageJson.build.appId).toBe("com.orderquickread.desktop");
    expect(packageJson.build.win.icon).toBe("assets/app_icon.ico");
    expect(packageJson.build.mac.icon).toBe("assets/app_icon.icns");
  });

  it("uses a CommonJS preload entry that Electron can load in packaged apps", () => {
    const appSource = readFileSync(path.join(repoRoot, "electron/main/app.ts"), "utf-8");

    expect(appSource).toContain("../preload/index.cjs");
    expect(existsSync(path.join(repoRoot, "electron/preload/index.cts"))).toBe(true);
    expect(existsSync(path.join(repoRoot, "electron/preload/index.ts"))).toBe(false);
  });
});
