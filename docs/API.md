# Supa-Crawl-Chat HTTP API

The API process listens on **`API_PORT`** (default **8001**). Interactive documentation is served at **`/docs`** (Swagger UI) and **`/redoc`**. OpenAPI JSON: **`/openapi.json`**.

A non-schema route map is available at **`GET /api`** (JSON list of major endpoints and notes).

---

## Public endpoints (no API key)

These routes do **not** use `require_supa_request_auth`:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness / DB-ish stats for probes |
| GET | `/api/auth/webui/status` | Whether WebUI login is required; whether `SUPA_API_AUTH` is enabled |
| POST | `/api/auth/webui/login` | Body: `{"password":"..."}` → WebUI JWT (when `WEBUI_PASSWORD` is set) |

All other **`/api/*`** routes listed in OpenAPI require authentication when auth is enabled (see below).

---

## Authentication

Implementation: custom dependency in `api/supa_auth.py` (`require_supa_request_auth`) and key extraction in `api/auth.py` (`_extract_key`). It is **not** wired as separate FastAPI `HTTPBearer` / `APIKeyHeader` dependencies; behavior is the same for clients.

### When requests are allowed without a key

- **No auth configured:** If **`SUPA_API_AUTH`** is false (default) **and** neither **`SCC_API_KEYS`** nor **`API_KEYS`** is set, all clients may call the API (typical on a trusted LAN).
- **Trusted client IP:** Loopback (**127.0.0.1**, **::1**) is always trusted. Optional **`SUPA_API_TRUST_CIDRS`** adds more CIDRs (e.g. Docker bridges). With **`SUPA_API_TRUST_FORWARDED=true`**, the client IP is taken from **`X-Forwarded-For`** (first hop) — use only behind a **trusted** reverse proxy.

### Credentials (non-trusted clients)

The server reads **at most one** secret from the request, in this order:

1. **`x-api-key: <secret>`** — if this header is present and non-empty, its value is used (highest priority).
2. Otherwise **`Authorization: Bearer <secret>`**.

That single value is checked, in order, against:

- A **WebUI JWT** (from `POST /api/auth/webui/login` when `WEBUI_PASSWORD` is set),
- **`SUPA_API_KEY`** (when `SUPA_API_AUTH=true`),
- Legacy keys from **`SCC_API_KEYS`** / **`API_KEYS`**.

**Integration hint for other apps:** If your client only supports **Bearer**, send `Authorization: Bearer <SUPA_API_KEY>`. If it only supports an API-key header, send **`x-api-key`**. There is **no** separate `SUPA_API_KEY_HEADER` in this repo; only these two shapes are supported.

### Web UI

When **`WEBUI_PASSWORD`** is set, the React app obtains a JWT and sends **`Authorization: Bearer <jwt>`** on API calls. Optional **`VITE_API_KEY`** still sends **`x-api-key`** for legacy **`SCC_API_KEYS`** / **`API_KEYS`** flows.

---

## Rate limiting

- **`GET /api/query`** is rate-limited per client IP (in-process). **`QUERY_RATE_LIMIT_PER_MINUTE`** (default **30**); set to **0** to disable.
- Other routes are not limited by this middleware.

---

## Environment variables (API-related)

| Variable | Role |
|----------|------|
| `API_PORT` | Listen port (default `8001`). |
| `SUPA_API_AUTH` | If true, require auth for non-trusted IPs when `SUPA_API_KEY` or legacy keys apply. |
| `SUPA_API_KEY` | Shared secret compared to Bearer / `x-api-key` (when auth is required). |
| `SUPA_API_TRUST_FORWARDED` | Use `X-Forwarded-For` for IP (trusted proxy only). |
| `SUPA_API_TRUST_CIDRS` | Comma-separated extra trusted CIDRs. |
| `SCC_API_KEYS` / `API_KEYS` | Legacy comma-separated API keys (same headers). |
| `QUERY_RATE_LIMIT_PER_MINUTE` | Per-IP limit for **`GET /api/query`** only. |
| `WEBUI_PASSWORD` | Enables WebUI login + JWT issuance. |
| `WEBUI_SECRET` | Optional JWT signing secret (else derived from `WEBUI_PASSWORD`). |
| `WEBUI_TOKEN_EXPIRY_DAYS` | JWT lifetime. |
| `API_CORS_ORIGINS` | Comma-separated origins; empty allows permissive CORS for dev. |
| `API_ACCESS_LOG` | If true, log one line per request (`api_http …`) except skipped paths. |

Copy **`/.env.example`** for full project variables (crawl, chat, Brave, logging, etc.).

---

## `.env` / python-dotenv warnings

If logs show:

`python-dotenv could not parse statement starting at line N`

that line is **invalid for python-dotenv’s parser**. Common fixes:

- **Section banners** must be comments: use `# === …`, not bare `=== …`.
- Every assignment needs a **key name** before `=`; a line starting with `=` is invalid.
- **Quote** values that contain `#`, spaces, or quotes.
- Use **ASCII** straight quotes in values; avoid smart/curly quotes in **uncommented** lines.
- Ensure **double-quoted** strings are closed on the same line (no raw multi-line values unless quoted).

After editing `.env`, restart the API process so variables reload.

---

## Minimal client examples

Replace `BASE` and `KEY` as appropriate.

```bash
# Health (no auth)
curl -sS "$BASE/api/health"

# Search / RAG query (when auth required)
curl -sS -H "Authorization: Bearer $KEY" "$BASE/api/search?query=hello&limit=5"

# Same with x-api-key
curl -sS -H "x-api-key: $KEY" "$BASE/api/search?query=hello&limit=5"

# Chat
curl -sS -X POST "$BASE/api/chat" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is on the site?","session_id":"demo","user_id":"demo"}'
```

---

## Related documentation

- [SYSTEM_FLOWS.md](./SYSTEM_FLOWS.md) — architecture, search/chat behavior, frontend overview.
- [preferences.md](./preferences.md) — user preference APIs under `/api/chat/preferences` (also covered in OpenAPI).
