// 開発用ポートを握っているプロセスツリーを潰して、ポートを解放する。
// 直前の `npm run dev` を強制終了したときに、uvicorn のリローダの子や
// vite の node プロセスが残ってしまったときの復旧用。

import { spawnSync } from "node:child_process";
import process from "node:process";

const PORTS = [8000, 5173];
const isWindows = process.platform === "win32";

function collectPidsWindows() {
  const out = spawnSync("netstat", ["-ano"], { encoding: "utf8" });
  if (out.status !== 0) return new Set();
  const pids = new Set();
  for (const line of out.stdout.split(/\r?\n/)) {
    if (!line.includes("LISTENING")) continue;
    for (const port of PORTS) {
      if (line.includes(`:${port} `) || line.includes(`:${port}\t`)) {
        const m = line.match(/LISTENING\s+(\d+)/);
        if (m) pids.add(m[1]);
      }
    }
  }
  return pids;
}

function collectPidsPosix() {
  const pids = new Set();
  for (const port of PORTS) {
    const out = spawnSync("lsof", ["-ti", `:${port}`], { encoding: "utf8" });
    if (out.status === 0) {
      for (const pid of out.stdout.split(/\s+/)) {
        if (pid) pids.add(pid);
      }
    }
  }
  return pids;
}

const pids = isWindows ? collectPidsWindows() : collectPidsPosix();

if (pids.size === 0) {
  console.log(`[stop] no listeners on ${PORTS.join(", ")}`);
  process.exit(0);
}

console.log(`[stop] killing pids: ${[...pids].join(", ")}`);
for (const pid of pids) {
  if (isWindows) {
    spawnSync("taskkill", ["/pid", pid, "/t", "/f"], { stdio: "inherit" });
  } else {
    try {
      process.kill(Number(pid), "SIGTERM");
    } catch {
      // 既に死んでいる等は無視する
    }
  }
}
