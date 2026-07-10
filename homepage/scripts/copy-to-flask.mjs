import { cpSync, existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const homepageRoot = path.resolve(here, "..");
const outDir = path.join(homepageRoot, "out");
const targetDir = path.resolve(
  homepageRoot,
  "..",
  "relocation_jobs",
  "static",
  "homepage",
);

if (!existsSync(outDir)) {
  console.error(`Missing Next export at ${outDir}. Run next build first.`);
  process.exit(1);
}

rmSync(targetDir, { recursive: true, force: true });
cpSync(outDir, targetDir, { recursive: true });
console.log(`Copied homepage export to ${targetDir}`);
