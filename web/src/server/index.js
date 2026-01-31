import express from "express";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, "../..");

const PORT = process.env.PORT ? Number(process.env.PORT) : 3000;
const DIST_PUBLIC = path.join(ROOT_DIR, "dist", "public");
const DEV_PUBLIC = path.join(ROOT_DIR, "public");

const env = process.env.NODE_ENV || "development";
const useDevOverride = Boolean(process.env.USE_DEV_STATIC);
const useDist = !useDevOverride && fs.existsSync(DIST_PUBLIC);
const STATIC_ROOT = useDist ? DIST_PUBLIC : DEV_PUBLIC;

const app = express();

app.use(express.json({ limit: "2mb" }));
app.use(express.urlencoded({ extended: true }));

app.use(express.static(STATIC_ROOT, { extensions: ["html"] }));

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

// SPA fallback so direct / routes resolve to index.html
app.get("*", (_req, res) => {
  res.sendFile(path.join(STATIC_ROOT, "index.html"));
});

app.listen(PORT, () => {
  console.log(`Architect AI web (${env}) listening on http://localhost:${PORT}`);
  console.log(`Serving static assets from ${STATIC_ROOT}`);
});
