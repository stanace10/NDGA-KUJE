"use strict";

const http = require("http");
const { performance } = require("perf_hooks");

const sessionKeys = (process.env.CBT_LOAD_SESSION_KEYS || "")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

if (!sessionKeys.length) {
  console.error("Set CBT_LOAD_SESSION_KEYS to one or more comma-separated Django session keys.");
  process.exit(2);
}

const stages = (process.env.CBT_LOAD_STAGES || "100,250,500,1000")
  .split(",")
  .map((value) => Number.parseInt(value.trim(), 10))
  .filter((value) => Number.isFinite(value) && value > 0);
const timeoutMs = Number.parseInt(process.env.CBT_LOAD_TIMEOUT_MS || "30000", 10);
const requestPath = process.env.CBT_LOAD_PATH || "/cbt/exams/available/";
const agent = new http.Agent({ keepAlive: true, maxSockets: 1200, maxFreeSockets: 128 });

function percentile(sorted, fraction) {
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * fraction) - 1));
  return sorted[index];
}

function requestOnce(index) {
  const sessionKey = sessionKeys[index % sessionKeys.length];
  const started = performance.now();
  return new Promise((resolve) => {
    const request = http.request(
      {
        hostname: "127.0.0.1",
        port: 80,
        path: requestPath,
        method: "GET",
        agent,
        headers: {
          Host: "cbt.ndgakuje.org",
          Cookie: `sessionid=${sessionKey}`,
          "User-Agent": "NDGA-CBT-Readiness-Load-Test/2026-06-30",
          Accept: "text/html",
        },
      },
      (response) => {
        let bytes = 0;
        response.on("data", (chunk) => {
          bytes += chunk.length;
        });
        response.on("end", () => {
          resolve({
            ok: response.statusCode === 200,
            status: response.statusCode,
            elapsedMs: performance.now() - started,
            bytes,
          });
        });
      },
    );
    request.setTimeout(timeoutMs, () => request.destroy(new Error("request timeout")));
    request.on("error", (error) => {
      resolve({
        ok: false,
        status: 0,
        elapsedMs: performance.now() - started,
        bytes: 0,
        error: error.message,
      });
    });
    request.end();
  });
}

async function runStage(count) {
  const started = performance.now();
  const results = await Promise.all(Array.from({ length: count }, (_, index) => requestOnce(index)));
  const durationMs = performance.now() - started;
  const timings = results.map((row) => row.elapsedMs).sort((a, b) => a - b);
  const statusCounts = {};
  for (const result of results) {
    statusCounts[result.status] = (statusCounts[result.status] || 0) + 1;
  }
  return {
    concurrentRequests: count,
    success: results.filter((row) => row.ok).length,
    failed: results.filter((row) => !row.ok).length,
    durationMs: Number(durationMs.toFixed(1)),
    requestsPerSecond: Number(((count * 1000) / durationMs).toFixed(1)),
    p50Ms: Number(percentile(timings, 0.5).toFixed(1)),
    p95Ms: Number(percentile(timings, 0.95).toFixed(1)),
    p99Ms: Number(percentile(timings, 0.99).toFixed(1)),
    maxMs: Number((timings[timings.length - 1] || 0).toFixed(1)),
    responseMB: Number(
      (results.reduce((sum, row) => sum + row.bytes, 0) / (1024 * 1024)).toFixed(2),
    ),
    statusCounts,
  };
}

(async () => {
  console.log(
    JSON.stringify({
      target: `http://127.0.0.1${requestPath}`,
      authenticatedSessions: sessionKeys.length,
      stages,
    }),
  );
  let hasFailure = false;
  for (const stage of stages) {
    const result = await runStage(stage);
    console.log(JSON.stringify(result));
    hasFailure ||= result.failed > 0;
  }
  agent.destroy();
  process.exit(hasFailure ? 1 : 0);
})().catch((error) => {
  console.error(error);
  agent.destroy();
  process.exit(1);
});
