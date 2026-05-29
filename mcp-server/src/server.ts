import express from 'express';
import cors from 'cors';
import type { Request, Response } from 'express';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';

import { PORT, API_TOKEN, INDEX_PATH } from './config';
import { BranchStore } from './index-store';
import { authMiddleware, oauthRouter } from './auth';
import { createMcpServer } from './mcp';

// ─── Boot ─────────────────────────────────────────────────────────────────────

console.log(`[startup] Loading index from ${INDEX_PATH}...`);
const store = new BranchStore(INDEX_PATH);
await store.load();
console.log(`[startup] Index loaded — ${store.stats()}`);

// ─── App ──────────────────────────────────────────────────────────────────────

const app = express();
app.use(cors());
app.use(express.json());

// OAuth discovery + auto-approval (must be before authMiddleware so public
// paths like /authorize and /.well-known/* are reachable without a token).
app.use(oauthRouter);
app.use(authMiddleware);

// ─── Streamable HTTP transport — MCP 2025-03-26 ───────────────────────────────
// Stateless: each POST spins up a fresh Server + transport, handles the request,
// then tears down. No session state needed for our read-only tool set.

app.post('/mcp', async (req: Request, res: Response) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined, // stateless mode
  });
  const server = createMcpServer(store);
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
  res.on('finish', () => server.close());
});

// ─── Legacy SSE transport — MCP 2024-11-05 ───────────────────────────────────
// Older Claude Desktop configs and some MCP clients still use GET /mcp/sse to
// open a persistent event stream and POST /mcp/messages to send JSON-RPC.

const sseTransports = new Map<string, SSEServerTransport>();

app.get('/mcp/sse', async (req: Request, res: Response) => {
  const transport = new SSEServerTransport('/mcp/messages', res);
  const server    = createMcpServer(store);

  sseTransports.set(transport.sessionId, transport);
  await server.connect(transport);

  req.on('close', () => {
    sseTransports.delete(transport.sessionId);
    server.close();
  });
});

app.post('/mcp/messages', async (req: Request, res: Response) => {
  const sessionId = req.query.sessionId as string;
  const transport = sseTransports.get(sessionId);
  if (!transport) {
    res.status(400).json({ error: 'No SSE session found — connect to /mcp/sse first' });
    return;
  }
  await transport.handlePostMessage(req, res, req.body);
});

// ─── Health ───────────────────────────────────────────────────────────────────

app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok', index: store.stats(), uptime: process.uptime() });
});

// ─── Hot-reload (called by incremental indexer after each push) ───────────────

app.post('/internal/reload', async (req: Request, res: Response) => {
  if (req.headers['x-internal-token'] !== process.env.INTERNAL_TOKEN) {
    res.status(403).json({ error: 'Forbidden' });
    return;
  }
  const { files, branch, indexPath } = req.body as {
    files: string[];
    branch?: string;
    indexPath?: string;
  };
  if (!branch) {
    res.status(400).json({ error: 'Missing required field: branch' });
    return;
  }
  console.log(`[reload] Hot-patching ${files.length} file(s) on branch '${branch}'...`);
  await store.patch(files, branch, indexPath);
  console.log(`[reload] Done — ${store.stats()}`);
  res.json({ ok: true, stats: store.stats() });
});

// ─── Listen ───────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`[ready] MCP server listening on :${PORT}`);
  console.log(`[ready] Streamable HTTP : POST /mcp`);
  console.log(`[ready] Legacy SSE      : GET  /mcp/sse`);
  console.log(`[ready] Token           : ${API_TOKEN}`);
});
