import { describe, expect, it } from "vitest";
import packageJson from "../../package.json";

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
  });
});
