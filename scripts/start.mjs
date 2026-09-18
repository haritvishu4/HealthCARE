// Optional npm launcher. Python setup is still required once.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = path.join(
  root,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
if (!existsSync(python)) {
  console.error(
    "Run python3 scripts/setup.py --sqlite first (Windows: py scripts/setup.py --sqlite).",
  );
  process.exit(1);
}
const child = spawn(python, ["scripts/run.py"], {
  cwd: root,
  stdio: "inherit",
});
child.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code || 0;
});
process.on("SIGINT", () => child.kill("SIGINT"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
