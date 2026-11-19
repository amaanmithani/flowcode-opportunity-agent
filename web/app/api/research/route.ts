// Starts the Python agent for one brand and streams its progress back as NDJSON.
// The same code runs on a laptop and in the Docker deployment: both have `uv` and the agent next to the web app.

import { spawn } from "node:child_process";
import path from "node:path";

// One run at a time per server: protects the API key and keeps the demo predictable.
let running = false;

const VALID = /^[\p{L}\p{N}][\p{L}\p{N} .,&'’\-:/]{1,79}$/u;

export async function POST(request: Request) {
  if (process.env.VERCEL === "1" || process.env.LIVE_RUNS === "off") {
    return Response.json({ error: "Live research is turned off on this deployment." }, { status: 403 });
  }
  const body = await request.json().catch(() => null);
  const company = String(body?.company ?? "").trim();
  if (!VALID.test(company)) {
    return Response.json({ error: "Enter a brand name or website (2–80 characters)." }, { status: 400 });
  }
  if (running) {
    return Response.json({ error: "Another research run is in progress. Try again in a minute." }, { status: 429 });
  }
  running = true;

  const agentDir = process.env.AGENT_DIR ?? path.join(process.cwd(), "..", "agent");
  // Arguments are passed as an array (no shell), so the brand name cannot inject commands.
  const child = spawn(/*turbopackIgnore: true*/ process.env.UV_BIN ?? "uv", ["run", "--project", agentDir, "opportunity-agent", "run", company], {
    cwd: agentDir,
    env: { ...process.env, OA_PROGRESS: "1" },
  });

  const encoder = new TextEncoder();
  let closed = false;
  const finish = () => {
    running = false;
  };

  const stream = new ReadableStream({
    start(controller) {
      const send = (obj: unknown) => {
        if (!closed) controller.enqueue(encoder.encode(JSON.stringify(obj) + "\n"));
      };
      const end = () => {
        if (!closed) {
          closed = true;
          controller.close();
        }
      };

      let buffer = "";
      let tail: string[] = [];
      child.stderr.on("data", (chunk: Buffer) => {
        buffer += chunk.toString();
        let i: number;
        while ((i = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, i);
          buffer = buffer.slice(i + 1);
          if (line.startsWith("PROGRESS ")) {
            try {
              send({ type: "progress", event: JSON.parse(line.slice(9)) });
            } catch {
              /* ignore a malformed line */
            }
          } else if (line.trim()) {
            tail = [...tail, line].slice(-6);
          }
        }
      });
      child.stdout.resume(); // the CLI summary is not needed; progress comes from stderr

      child.on("error", (err) => {
        finish();
        send({ type: "error", message: `Could not start the agent: ${err.message}` });
        end();
      });
      child.on("close", (code) => {
        finish();
        send(code === 0 ? { type: "done" } : { type: "error", message: "The research run failed.", detail: tail.join("\n") });
        end();
      });
    },
    cancel() {
      // The visitor left: stop the run so it does not keep spending.
      closed = true;
      child.kill("SIGTERM");
      finish();
    },
  });

  return new Response(stream, { headers: { "Content-Type": "application/x-ndjson", "Cache-Control": "no-store" } });
}
