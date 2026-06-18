import { rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputDirs = ["dist-renderer", "dist-electron", "dist-electron-packages"];

for (const dir of outputDirs) {
  const target = path.join(projectRoot, dir);
  const relative = path.relative(projectRoot, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Refusing to remove path outside project root: ${target}`);
  }
  await rm(target, { recursive: true, force: true });
}
