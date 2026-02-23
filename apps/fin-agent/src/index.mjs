import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fetch } from "undici";

const FIN_AGENT_API = process.env.FIN_AGENT_API ?? "http://127.0.0.1:8080";
const OPENCODE_API = process.env.OPENCODE_API
  ?? `http://${process.env.OPENCODE_HOSTNAME ?? "127.0.0.1"}:${process.env.OPENCODE_PORT ?? "4096"}`;
const OPENCODE_SERVER_USERNAME = process.env.OPENCODE_SERVER_USERNAME ?? "opencode";
const OPENCODE_SERVER_PASSWORD = process.env.OPENCODE_SERVER_PASSWORD ?? "";
const PORT = Number(process.env.PORT ?? "8090");
const WEB_APP_PREFIX = "/app";
const WEB_DIST = resolve(process.env.FIN_AGENT_WEB_DIST ?? "apps/fin-agent-web/dist");

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

function isWebPath(url) {
  return url === WEB_APP_PREFIX || url.startsWith(`${WEB_APP_PREFIX}/`);
}

function isChatBridgePath(pathname) {
  return pathname === "/v1/chat/respond"
    || pathname === "/v1/chat/health"
    || pathname === "/v1/chat/sessions"
    || /^\/v1\/chat\/sessions\/[^/]+\/messages$/.test(pathname);
}

function contentTypeFromPath(path) {
  const ext = extname(path).toLowerCase();
  if (ext === ".html") return "text/html; charset=utf-8";
  if (ext === ".js" || ext === ".mjs") return "application/javascript; charset=utf-8";
  if (ext === ".css") return "text/css; charset=utf-8";
  if (ext === ".json") return "application/json; charset=utf-8";
  if (ext === ".svg") return "image/svg+xml";
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".ico") return "image/x-icon";
  return "application/octet-stream";
}

function resolveWebAssetPath(url) {
  const pathOnly = url.split("?")[0] ?? url;
  const relativePath = pathOnly.slice(WEB_APP_PREFIX.length);
  const normalized = relativePath === "" || relativePath === "/" ? "/index.html" : relativePath;
  const absolute = resolve(WEB_DIST, `.${normalized}`);
  const distRoot = WEB_DIST.endsWith(sep) ? WEB_DIST : `${WEB_DIST}${sep}`;
  if (absolute !== WEB_DIST && !absolute.startsWith(distRoot)) {
    throw new Error(`invalid web asset path traversal: ${url}`);
  }
  return absolute;
}

async function readWebAsset(url) {
  const absolute = resolveWebAssetPath(url);
  try {
    const body = await readFile(absolute);
    return {
      status: 200,
      headers: { "content-type": contentTypeFromPath(absolute) },
      body,
    };
  } catch (error) {
    const pathOnly = url.split("?")[0] ?? url;
    if (!pathOnly.includes(".")) {
      const indexPath = resolve(WEB_DIST, "index.html");
      try {
        const body = await readFile(indexPath);
        return {
          status: 200,
          headers: { "content-type": "text/html; charset=utf-8" },
          body,
        };
      } catch (indexError) {
        throw new Error(
          `web app index missing at ${indexPath}: ${indexError instanceof Error ? indexError.message : String(indexError)}`,
        );
      }
    }
    throw error;
  }
}

function opencodeHeaders(extra = {}) {
  const headers = { ...extra };
  if (OPENCODE_SERVER_PASSWORD) {
    headers.authorization = `Basic ${Buffer.from(`${OPENCODE_SERVER_USERNAME}:${OPENCODE_SERVER_PASSWORD}`).toString("base64")}`;
  }
  return headers;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: opencodeHeaders(options.headers ?? {}),
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (_error) {
    payload = { detail: text };
  }
  return { status: response.status, payload };
}

function extractAssistantText(payload) {
  const parts = Array.isArray(payload?.parts) ? payload.parts : [];
  return parts
    .map((part) => (part && part.type === "text" ? String(part.text ?? "") : ""))
    .filter((part) => part.length > 0)
    .join("\n");
}

async function handleChatBridge(req, pathname, search, bodyBuffer) {
  const method = req.method ?? "GET";

  if (pathname === "/v1/chat/health") {
    if (method !== "GET" && method !== "HEAD") {
      return jsonResponse(405, { error: "method_not_allowed", detail: "chat health supports GET/HEAD" });
    }
    const upstream = await fetch(`${OPENCODE_API}/global/health`, {
      method,
      headers: opencodeHeaders({ accept: "application/json" }),
    });
    const payload = await upstream.arrayBuffer();
    return {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json; charset=utf-8",
      },
      body: Buffer.from(payload),
    };
  }

  if (pathname === "/v1/chat/sessions") {
    if (method !== "GET") {
      return jsonResponse(405, { error: "method_not_allowed", detail: "chat sessions supports GET" });
    }
    const result = await fetchJson(`${OPENCODE_API}/session${search}`);
    if (result.status >= 400) {
      return jsonResponse(result.status, {
        error: "opencode_upstream_error",
        detail: "failed to list opencode sessions",
        upstream: result.payload,
      });
    }
    const sessions = Array.isArray(result.payload) ? result.payload : [];
    return jsonResponse(200, { sessions, count: sessions.length });
  }

  const messageListMatch = pathname.match(/^\/v1\/chat\/sessions\/([^/]+)\/messages$/);
  if (messageListMatch) {
    if (method !== "GET") {
      return jsonResponse(405, { error: "method_not_allowed", detail: "chat message list supports GET" });
    }
    const sessionId = decodeURIComponent(messageListMatch[1]);
    const result = await fetchJson(`${OPENCODE_API}/session/${encodeURIComponent(sessionId)}/message${search}`);
    if (result.status >= 400) {
      return jsonResponse(result.status, {
        error: "opencode_upstream_error",
        detail: `failed to list messages for session_id=${sessionId}`,
        upstream: result.payload,
      });
    }
    const messages = Array.isArray(result.payload) ? result.payload : [];
    return jsonResponse(200, { session_id: sessionId, messages, count: messages.length });
  }

  if (pathname === "/v1/chat/respond") {
    if (method !== "POST") {
      return jsonResponse(405, { error: "method_not_allowed", detail: "chat respond supports POST" });
    }

    let payload;
    try {
      payload = JSON.parse(bodyBuffer.toString("utf-8"));
    } catch (_error) {
      return jsonResponse(400, {
        error: "invalid_request",
        detail: "request body must be valid JSON",
      });
    }

    const message = typeof payload.message === "string" ? payload.message.trim() : "";
    if (!message) {
      return jsonResponse(400, {
        error: "invalid_request",
        detail: "field `message` is required",
      });
    }

    let sessionId = typeof payload.session_id === "string" ? payload.session_id.trim() : "";
    let createdSession = false;
    if (!sessionId) {
      const createSessionPayload = {};
      if (typeof payload.title === "string" && payload.title.trim()) {
        createSessionPayload.title = payload.title.trim();
      }
      const sessionResult = await fetchJson(`${OPENCODE_API}/session`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(createSessionPayload),
      });
      if (sessionResult.status >= 400) {
        return jsonResponse(sessionResult.status, {
          error: "opencode_upstream_error",
          detail: "failed to create opencode session",
          upstream: sessionResult.payload,
        });
      }
      const maybeId = sessionResult.payload?.id;
      if (typeof maybeId !== "string" || !maybeId.trim()) {
        return jsonResponse(502, {
          error: "invalid_upstream_payload",
          detail: "opencode session create response missing session id",
          upstream: sessionResult.payload,
        });
      }
      sessionId = maybeId.trim();
      createdSession = true;
    }

    const messagePayload = {
      parts: [{ type: "text", text: message }],
    };
    if (payload.no_reply !== undefined) {
      messagePayload.noReply = Boolean(payload.no_reply);
    }
    if (typeof payload.agent === "string" && payload.agent.trim()) {
      messagePayload.agent = payload.agent.trim();
    }
    if (payload.model && typeof payload.model === "object") {
      messagePayload.model = payload.model;
    }
    if (Array.isArray(payload.tools)) {
      messagePayload.tools = payload.tools;
    }
    if (typeof payload.system === "string" && payload.system.trim()) {
      messagePayload.system = payload.system.trim();
    }

    const messageResult = await fetchJson(`${OPENCODE_API}/session/${encodeURIComponent(sessionId)}/message`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(messagePayload),
    });
    if (messageResult.status >= 400) {
      return jsonResponse(messageResult.status, {
        error: "opencode_upstream_error",
        detail: `failed to send message to session_id=${sessionId}`,
        upstream: messageResult.payload,
      });
    }

    return jsonResponse(200, {
      session_id: sessionId,
      created_session: createdSession,
      assistant_text: extractAssistantText(messageResult.payload),
      opencode_message: messageResult.payload,
    });
  }

  return jsonResponse(404, {
    error: "not_found",
    detail: `unsupported chat route: ${pathname}`,
  });
}

const server = createServer(async (req, res) => {
  try {
    if (!req.url) {
      const out = jsonResponse(400, { error: "request.url missing" });
      res.writeHead(out.status, out.headers);
      res.end(out.body);
      return;
    }

    const parsed = new URL(req.url, "http://wrapper.local");
    const pathname = parsed.pathname;

    if (isWebPath(req.url)) {
      const method = req.method ?? "GET";
      if (method !== "GET" && method !== "HEAD") {
        const out = jsonResponse(405, {
          error: "method_not_allowed",
          detail: "web app routes only support GET/HEAD",
        });
        res.writeHead(out.status, out.headers);
        res.end(out.body);
        return;
      }
      try {
        const out = await readWebAsset(req.url);
        res.writeHead(out.status, out.headers);
        if (method === "HEAD") {
          res.end();
          return;
        }
        res.end(out.body);
        return;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (message.startsWith("invalid web asset path traversal")) {
          const out = jsonResponse(400, {
            error: "invalid_path",
            detail: message,
          });
          res.writeHead(out.status, out.headers);
          res.end(out.body);
          return;
        }
        const out = jsonResponse(404, {
          error: "web_asset_not_found",
          detail: message,
        });
        res.writeHead(out.status, out.headers);
        res.end(out.body);
        return;
      }
    }

    if (isChatBridgePath(pathname)) {
      const method = req.method ?? "GET";
      const body = method === "GET" || method === "HEAD" ? Buffer.alloc(0) : await readRequestBody(req);
      const out = await handleChatBridge(req, pathname, parsed.search, body);
      res.writeHead(out.status, out.headers);
      if (method === "HEAD") {
        res.end();
        return;
      }
      res.end(out.body);
      return;
    }

    if (!forwardablePath(req.url)) {
      const out = jsonResponse(404, {
        error: "not_found",
        detail: "supported routes are /app, /v1/chat/*, /health and /v1/*",
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
