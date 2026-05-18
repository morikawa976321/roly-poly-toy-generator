// 開発サーバのオーケストレータ。
// バックエンド（uvicorn）とフロントエンド（vite）を直接の子プロセスとして
// 起動し、SIGINT / SIGTERM / exit のタイミングでプロセスツリーごと確実に
// 終了させる。このラッパーが必要な理由:
// - `uvicorn --reload` は watchfiles 経由で multiprocessing の子プロセスを
//   さらに spawn する。
// - Windows では cmd / npm / python / uv と多層を挟むと Ctrl+C がうまく
//   伝搬しきらず、素直に組むとポート 8000 / 5173 を握ったままの子プロセスが
//   残ってしまう。
//
// Windows では各子に対して `taskkill /T /F` で子孫まで巻き込んで殺し、
// POSIX では `child.kill()` で終了させる。

import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import process from "node:process";

const isWindows = process.platform === "win32";
const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const viteBin = path.join(repoRoot, "frontend", "node_modules", "vite", "bin", "vite.js");
const BACKEND_URL = "http://127.0.0.1:8000";

async function probeBackendHealth() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** 8000 が別アプリに取られていると Vite プロキシ経由で一覧が常に空/404 になる。 */
async function assertBackendPortAvailable() {
  const body = await probeBackendHealth();
  if (body === null) return;
  if (body.status === "ok") {
    process.stderr.write(
      "[dev] port 8000 already serves this backend. Run `npm run stop` first for a clean dev session.\n",
    );
    process.exit(1);
  }
  process.stderr.write(
    `[dev] port 8000 is used by another app (GET /health -> ${JSON.stringify(body)}). ` +
      "Run `npm run stop`, then `npm run dev` again.\n",
  );
  process.exit(1);
}

async function waitForBackendReady(maxMs = 45_000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const body = await probeBackendHealth();
    if (body?.status === "ok") {
      try {
        const res = await fetch(`${BACKEND_URL}/api/designs?limit=1`, {
          signal: AbortSignal.timeout(5000),
        });
        if (!res.ok) {
          process.stderr.write(
            `[dev] backend /api/designs returned HTTP ${res.status}\n`,
          );
          return false;
        }
        const list = await res.json();
        process.stdout.write(
          `[dev] backend ready (SQLite: ${list.total ?? "?"} designs)\n`,
        );
        return true;
      } catch (err) {
        process.stderr.write(
          `[dev] backend API probe failed: ${err instanceof Error ? err.message : String(err)}\n`,
        );
        return false;
      }
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  process.stderr.write("[dev] backend did not become ready in time\n");
  return false;
}

// ログ行の先頭に色付きタグを付けて、どちらのサーバの出力か見分けやすくする。
const prefix = (tag, color) => (line) => `\x1b[${color}m[${tag}]\x1b[0m ${line}`;

function pipe(child, tagLine) {
  const write = (buf) => {
    const text = buf.toString();
    for (const line of text.split(/\r?\n/)) {
      if (line.length > 0) process.stdout.write(tagLine(line) + "\n");
    }
  };
  child.stdout?.on("data", write);
  child.stderr?.on("data", write);
}

let shuttingDown = false;
let backend;
let frontend;

const children = () => [
  { name: "backend", proc: backend },
  { name: "frontend", proc: frontend },
];

function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const { proc } of children()) {
    if (!proc.pid || proc.exitCode !== null) continue;
    try {
      if (isWindows) {
        spawnSync("taskkill", ["/pid", String(proc.pid), "/t", "/f"], {
          stdio: "ignore",
        });
      } else {
        proc.kill("SIGTERM");
      }
    } catch {
      // ベストエフォート: 既に死んでいる等は無視する
    }
  }
}

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK"]) {
  process.on(signal, () => {
    shutdown();
    process.exit(signal === "SIGTERM" ? 143 : 130);
  });
}
process.on("exit", shutdown);

function wireChild(proc, name) {
  proc.on("exit", (code, signal) => {
    exitedCount += 1;
    process.stdout.write(
      `[dev] ${name} exited (code=${code}, signal=${signal})\n`,
    );
    if (exitedCount < 2) shutdown();
    else process.exit(code ?? 0);
  });
  proc.on("error", (err) => {
    process.stderr.write(`[dev] ${name} failed to start: ${err.message}\n`);
    shutdown();
    process.exit(1);
  });
}

let exitedCount = 0;

await assertBackendPortAvailable();

backend = spawn(
  "python",
  [
    "-m",
    "uv",
    "run",
    "--no-sync",
    "uvicorn",
    "app.main:app",
    "--reload",
    "--port",
    "8000",
    "--app-dir",
    "backend",
  ],
  { stdio: ["ignore", "pipe", "pipe"], shell: false },
);

frontend = spawn(process.execPath, [viteBin], {
  stdio: ["ignore", "pipe", "pipe"],
  shell: false,
  cwd: path.join(repoRoot, "frontend"),
});

pipe(backend, prefix("backend", "34"));
pipe(frontend, prefix("frontend", "35"));

wireChild(backend, "backend");
wireChild(frontend, "frontend");

const ready = await waitForBackendReady();
if (!ready) {
  shutdown();
  process.exit(1);
}
