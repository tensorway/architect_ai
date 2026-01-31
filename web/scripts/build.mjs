import { build } from "esbuild";
import { cp, mkdir, rm } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "..");
const DIST = path.join(ROOT, "dist");
const DIST_PUBLIC = path.join(DIST, "public");
const ASSET_DIR = path.join(DIST_PUBLIC, "assets");
const PUBLIC = path.join(ROOT, "public");

async function prepareOutput() {
  await rm(DIST, { recursive: true, force: true });
  await mkdir(ASSET_DIR, { recursive: true });
  await cp(PUBLIC, DIST_PUBLIC, { recursive: true });
}

async function bundle() {
  await build({
    entryPoints: [path.join(ROOT, "src", "client", "index.tsx")],
    outfile: path.join(ASSET_DIR, "bundle.js"),
    bundle: true,
    sourcemap: process.env.NODE_ENV !== "production",
    minify: process.env.NODE_ENV === "production",
    target: ["es2019"],
    format: "esm",
    jsx: "automatic",
    logLevel: "info",
  });
}

async function main() {
  await prepareOutput();
  await bundle();
  console.log("✓ build complete");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
