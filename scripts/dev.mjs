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

const backend = spawn(
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

const frontend = spawn(
  process.execPath,
  [viteBin],
  {
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
    cwd: path.join(repoRoot, "frontend"),
  },
);

pipe(backend, prefix("backend", "34"));
pipe(frontend, prefix("frontend", "35"));

const children = [
  { name: "backend", proc: backend },
  { name: "frontend", proc: frontend },
];

let shuttingDown = false;
function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const { proc } of children) {
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

let exitedCount = 0;
for (const { name, proc } of children) {
  proc.on("exit", (code, signal) => {
    exitedCount += 1;
    process.stdout.write(
      `[dev] ${name} exited (code=${code}, signal=${signal})\n`,
    );
    if (exitedCount < children.length) shutdown();
    else process.exit(code ?? 0);
  });
  proc.on("error", (err) => {
    process.stderr.write(`[dev] ${name} failed to start: ${err.message}\n`);
    shutdown();
    process.exit(1);
  });
}
