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

## Deleting a site

`DELETE /api/sites/{site_id}` removes the site row; **`crawl_pages`** (and chunks) and **`crawl_jobs`** are removed by **ON DELETE CASCADE** in the schema. Requires the same auth as other `/api` routes when enabled. The web UI exposes this on **Sites** (trash icon) and on each **site detail** page.

### Single page

- **`DELETE /api/pages/{page_id}`** removes one **`crawl_pages`** row. Deleting a **parent** page removes its **chunks** (CASCADE). Deleting a **chunk** removes only that chunk. Audit lines go to **`log/audit.log`** (and **`app.log`**) when enabled.
- **`POST /api/crawl/refresh/{site_id}/pages/{page_id}`** re-fetches **only** that page’s URL via Crawl4AI (**no** whole-site crawl), then merges into the site. If **`page_id`** is a **chunk**, the **parent** URL is used. Poll **`GET /api/crawl/status/{site_id}`** like a full refresh. The site detail UI exposes **Recrawl page** and **Delete** on each listed page.

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
| `AUDIT_LOG_ENABLED` | If true (default), write high-signal actions to a separate file under `APP_LOG_DIR` (default `audit.log`). |
| `AUDIT_LOG_FILE` | Audit log filename (inside `APP_LOG_DIR`). |
| `AUDIT_LOG_MAX_BYTES` / `AUDIT_LOG_BACKUP_COUNT` | Size-based rotation for the audit file. |
| `ALLOW_PRIVATE_CRAWL_URLS` | If true, allow crawls to private/LAN/link-local targets. Keep false unless intentionally crawling internal hosts. |
| `CRAWL_ALLOWED_HOSTS` | Comma-separated exact/wildcard host allowlist for trusted internal crawl targets. |
| `CRAWL_ALLOW_REDIRECTS` | If true, API requests may ask Crawl4AI to follow redirects. Default policy blocks this. |
| `CRAWL_ALLOW_EXTERNAL_LINKS` | If true, API requests may ask Crawl4AI to follow external hosts. Default policy blocks this. |
| `CRAWL_ALLOW_CUSTOM_PROXY` | If true, API requests may provide a crawl proxy. Default policy blocks this. |
| `CRAWL_ALLOW_FILE_DOWNLOADS` | If true, API requests may enable file downloads. Default policy blocks this. |
| `CRAWL_SITEMAP_ALLOW_EXTERNAL` | If true, sitemap/llms.txt expansion may include public external hosts. Default is same-host only. |
| `CRAWL_MAX_REDIRECTS` | Redirect hops allowed during app-side validated sitemap fetches. |
| `CRAWL_MAX_CONTENT_CHARS` | Maximum characters stored/indexed per crawled page after encoded-noise cleanup. |
| `BRAVE_WEB_CONTEXT` | Default web-context merge policy for chat `context_mode=auto`; per-request `context_mode=web/indexed/none` can override routing. |
| `CHAT_RESULT_LIMIT` / `CHAT_SIMILARITY_THRESHOLD` | Default crawled-content retrieval settings for chat when no per-request override is provided. |

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

# Chat with explicit source routing: auto | indexed | web | none
curl -sS -X POST "$BASE/api/chat?context_mode=indexed" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"What sites do I have crawled?","session_id":"demo","user_id":"demo"}'
```

`POST /api/chat` keeps `context_mode=auto` by default for compatibility. `auto`
uses crawled-site context plus the server's configured Brave fallback policy,
`indexed` disables Brave and uses only stored crawls, `web` forces Brave web
context while still allowing indexed context, and `none` disables both indexed
and web context for a plain model response.

---

## Related documentation

- [SYSTEM_FLOWS.md](./SYSTEM_FLOWS.md) — architecture, search/chat behavior, frontend overview.
- [preferences.md](./preferences.md) — user preference APIs under `/api/chat/preferences` (also covered in OpenAPI).
