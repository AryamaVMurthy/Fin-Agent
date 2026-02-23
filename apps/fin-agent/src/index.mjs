import { createServer } from "node:http";
import { fetch } from "undici";

const FIN_AGENT_API = process.env.FIN_AGENT_API ?? "http://127.0.0.1:8080";
const PORT = Number(process.env.PORT ?? "8090");

function jsonResponse(status, payload) {
  return {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  };
}

async function readRequestBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

function forwardablePath(url) {
  return url === "/health" || url.startsWith("/v1/");
}

const server = createServer(async (req, res) => {
  try {
    if (!req.url) {
      const out = jsonResponse(400, { error: "request.url missing" });
      res.writeHead(out.status, out.headers);
      res.end(out.body);
      return;
    }

    if (!forwardablePath(req.url)) {
      const out = jsonResponse(404, {
        error: "not_found",
        detail: "supported routes are /health and /v1/*",
      });
      res.writeHead(out.status, out.headers);
      res.end(out.body);
      return;
    }

    const method = req.method ?? "GET";
    const body = method === "GET" || method === "HEAD" ? undefined : await readRequestBody(req);
    const headers = { "content-type": req.headers["content-type"] ?? "application/json" };
    const upstream = await fetch(`${FIN_AGENT_API}${req.url}`, {
      method,
      headers,
      body,
    });
    const payload = await upstream.arrayBuffer();
    res.writeHead(upstream.status, {
      "content-type": upstream.headers.get("content-type") ?? "application/json; charset=utf-8",
    });
    res.end(Buffer.from(payload));
  } catch (error) {
    const out = jsonResponse(500, {
      error: "internal_error",
      detail: error instanceof Error ? error.message : String(error),
    });
    res.writeHead(out.status, out.headers);
    res.end(out.body);
  }
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(
    `fin-agent wrapper listening on http://127.0.0.1:${PORT}\n`,
  );
});
