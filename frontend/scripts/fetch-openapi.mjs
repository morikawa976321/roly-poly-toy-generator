import { mkdir, writeFile } from "node:fs/promises";

const OPENAPI_URL =
  process.env.OPENAPI_URL ?? "http://127.0.0.1:8000/openapi.json";

async function main() {
  await mkdir(new URL("../src/generated/", import.meta.url), { recursive: true });

  const res = await fetch(OPENAPI_URL);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `Failed to fetch OpenAPI from ${OPENAPI_URL}: HTTP ${res.status} ${
        text || res.statusText
      }`,
    );
  }

  const spec = await res.json();
  const outPath = new URL("../src/generated/openapi.json", import.meta.url);
  await writeFile(outPath, JSON.stringify(spec, null, 2) + "\n", "utf-8");
  process.stdout.write(`Wrote OpenAPI spec to ${outPath.pathname}\n`);
}

main().catch((err) => {
  console.error(String(err?.stack ?? err));
  console.error(
    `\nHint: start the backend (FastAPI) first, or set OPENAPI_URL to a reachable /openapi.json.`,
  );
  process.exit(1);
});

