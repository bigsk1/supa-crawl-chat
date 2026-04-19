import React, { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useTheme } from '@/context/ThemeContext';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function markdownPlainText(children: React.ReactNode): string {
  if (children == null || typeof children === 'boolean') return '';
  if (typeof children === 'string' || typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(markdownPlainText).join('');
  return '';
}

const UserGuidePage: React.FC = () => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const [activeTab, setActiveTab] = useState('overview');

  // Markdown sections (keep in sync with docs/API.md and the app where possible)
  const sections = {
    overview:
      '# Supa Crawl Chat\n\n**Supa Crawl Chat** (SupaChat) crawls websites with **Crawl4AI**, stores content in **Supabase (Postgres + pgvector)**, and answers questions with **OpenAI** — semantic search, chat with RAG, and optional **Brave** web context when configured.\n\n![SupaChat](https://imagedelivery.net/WfhVb8dSNAAvdXUdMfBuPQ/92227574-9331-49d0-535f-1f21c9b14f00/public)\n\n### What you can do here\n- **Crawl** new sites or sitemaps and monitor jobs\n- **Search** your indexed content (embeddings + optional keyword/FTS)\n- **Chat** with retrieved context, profiles, and history\n- **Browse** sites, pages, and chunks\n\nInteractive HTTP reference: open `/docs` on your API host (for example `http://localhost:8001/docs`). In the repo, see the `docs` folder and `docs/API.md`.',
    components:
      '## Core components\n\n### 1. Database (Supabase)\n- Crawled pages, chunks, embeddings, and site metadata\n- Chat session storage and **user preferences** (when a user id is used)\n\n### 2. OpenAI\n- Embeddings for semantic search\n- Titles/summaries during crawl\n- Chat completions and preference extraction\n\n### 3. Crawl4AI\n- Fetches and renders pages; feeds the chunking pipeline\n- Configured via `CRAWL4AI_*` env vars (see `.env.example`)\n\n### 4. Web UI (this app)\n- React + TypeScript + Vite + Tailwind and shadcn-style components\n- Talks to the FastAPI backend at the `/api` path (same origin or proxied)\n\n### 5. CLI / scripts (optional)\n- The repo may include terminal workflows; day-to-day use is the browser UI.',
    frontend:
      [
        '## Web UI & API access',
        '',
        '### Stack',
        '- **Vite**, **React Router** — HTTP calls use the `/api` base path (code under `frontend/src/api/`).',
        '',
        '### Optional login',
        'If env `WEBUI_PASSWORD` is set, sign in once. The app keeps a short-lived JWT and sends `Authorization: Bearer` on later requests.',
        '',
        '### Optional API keys (other apps or scripts)',
        'Authentication is required when `SUPA_API_AUTH` and `SUPA_API_KEY` are set, or when legacy `SCC_API_KEYS` or `API_KEYS` is configured. Send **one** credential:',
        '',
        '- `Authorization: Bearer` plus your secret (space after Bearer).',
        '- or header `x-api-key` with the same secret.',
        '',
        'If both are present, the server prefers `x-api-key`.',
        '',
        'Localhost and trusted networks may bypass keys; see the repo file `docs/API.md`.',
        '',
        '### CORS',
        'Set `API_CORS_ORIGINS` on the API for browsers on other origins. Local dev often proxies `/api`, so CORS may be unnecessary.',
      ].join('\n'),
    flows:
      '## Flows in the UI\n\n### Sites\n1. Open **Sites** — list loads from **`GET /api/sites`**\n2. Open a site — **`GET /api/sites/{id}`** and **`GET /api/sites/{id}/pages`**\n3. Inspect pages, chunks, and crawl-related metadata\n\n### Chat\n1. Open **Chat** — session id is persisted locally\n2. Profiles from **`GET /api/chat/profiles`**; history from **`GET /api/chat/history`**\n3. Messages go to **`POST /api/chat`** with your message, session, user, and profile\n4. You can switch **profile**, **clear history**, and manage **preferences** when a user id is set\n\n### Crawl\n1. Open **Crawl** — enter URL, optional name/description, URL vs sitemap, limits\n2. **`POST /api/crawl`** starts a job; the UI polls **`GET /api/crawl/status/{site_id}`** (and related activity endpoints where used)\n3. When finished, open the site from **Sites** to review pages\n\n### Search\n1. Open **Search** — set query, threshold, limit, optional site filter, **semantic vs text-only**\n2. **`GET /api/search`** returns hits (alias: **`GET /api/query`** for tools)\n3. **`GET /api/query`** may be rate-limited per IP (server env **QUERY_RATE_LIMIT_PER_MINUTE**)',
    notifications:
      '## Notifications\n\n- **Toasts** for quick success/error feedback on actions\n- **Notification center** (bell) for a running list; items can be dismissed\n- **Mute** (where available) reduces non-critical toasts; serious errors still surface\n\nImplementation detail: notifications are driven from the frontend helper layer (`createNotification`, etc.) and optional tracking hooks — not a separate backend service.',
    preferences:
      '## User preferences\n\n### How it works\n- With a **user id**, the chat pipeline can **extract** preferences from conversation (LLM-assisted)\n- Preferences are stored in **`user_preferences`** and surfaced to the model when relevant\n- Manage them under **User Preferences** in the UI when configured\n\n### Example shape (simplified)\n\n```json\n{\n  \"preference_type\": \"like\",\n  \"preference_value\": \"Example topic\",\n  \"confidence\": 0.95,\n  \"is_active\": true\n}\n```\n\n### HTTP API (chat router)\nAll require `user_id` query or body as documented in **`/docs`**:\n\n```\nGET    /api/chat/preferences?user_id=...\nPOST   /api/chat/preferences\nDELETE /api/chat/preferences/{preference_id}?user_id=...\nPUT    /api/chat/preferences/{preference_id}/deactivate?user_id=...\nPUT    /api/chat/preferences/{preference_id}/activate?user_id=...\nDELETE /api/chat/preferences?user_id=...   # clear all for user\n```',
    search:
      '## Search\n\n### Modes\n- **Semantic (default):** query embedding vs stored vectors (**pgvector** cosine distance); similarity scores in responses\n- **Text-only (`text_only=true`):** PostgreSQL full-text + title matching — not BM25/Elasticsearch\n- The backend may combine vector and text retrieval depending on settings (see **`db_client`** hybrid search)\n\n### HTTP\n\n```\nGET /api/search?query=...&threshold=0.3&limit=10&text_only=false&site_id=&site_name=\n```\n\nAlias: **`GET /api/query?...`** (same handler). Optional: `include_content`, `content_chars`, `dedupe`, `after` (ISO time) — see **`/docs`**.\n\n### Chat context\nRAG in chat uses the same embedding stack unless the message is treated as a short greeting (fast path).',
    docker:
      '## Docker\n\nTypical layouts (see repository **`docker/`** and **`README.md`**):\n\n1. **API-focused** — app/API container with external Supabase + Crawl4AI\n2. **App + Crawl4AI** — UI, API, and Crawl4AI together; DB still external or separate\n3. **Full stack** — includes self-hosted Supabase-style stack where provided\n\nCompose files, env wiring, and health checks vary by folder — follow the **Docker README** for the path you use: [docker layout on GitHub](https://github.com/bigsk1/supa-crawl-chat/tree/main/docker).\n\n**Tip:** ensure the API can reach Postgres, Crawl4AI, and OpenAI; set secrets via env, not baked images.',
  };

  // Custom renderer components for ReactMarkdown
  const renderers = {
    img: ({ node, ...props }: any) => (
      <span className="block my-6 text-center">
        <img 
          {...props} 
          className="rounded-lg shadow-md max-w-full max-h-[400px] object-contain inline-block" 
          alt={props.alt || 'Documentation image'} 
        />
      </span>
    ),
    h1: ({ node, ...props }: any) => (
      <h1 {...props} className="text-3xl font-bold mb-6 text-foreground" />
    ),
    h2: ({ node, ...props }: any) => (
      <h2 {...props} className="text-2xl font-semibold mt-8 mb-4 text-foreground" />
    ),
    h3: ({ node, ...props }: any) => (
      <h3 {...props} className="text-xl font-medium mt-6 mb-3 text-foreground" />
    ),
    p: ({ node, ...props }: any) => (
      <p {...props} className="mb-4 text-foreground/90 leading-relaxed" />
    ),
    ul: ({ node, ...props }: any) => (
      <ul {...props} className="list-disc pl-6 mb-4 space-y-2" />
    ),
    ol: ({ node, ...props }: any) => (
      <ol {...props} className="list-decimal pl-6 mb-4 space-y-2" />
    ),
    li: ({ node, ...props }: any) => (
      <li {...props} className="text-foreground/90" />
    ),
    // v9+: `inline` was removed from `code`. Fenced blocks are `<pre><code class="language-...">`.
    // Never emit `<pre>` from `code` — that nests `<pre>` inside `<p>` for inline backticks.
    pre: ({ node, ...props }: any) => (
      <pre
        {...props}
        className="mb-4 overflow-x-auto rounded-md border border-border bg-muted p-4 text-sm font-mono text-foreground"
      />
    ),
    code: ({ className, children, ...props }: any) => {
      const text = markdownPlainText(children);
      const isFenced =
        Boolean(className && /language-[\w-]*/.test(className)) ||
        (text.includes('\n') && text.trim().length > 0);
      if (isFenced) {
        return (
          <code {...props} className={`text-sm font-mono text-foreground ${className || ''}`.trim()}>
            {children}
          </code>
        );
      }
      return (
        <code
          {...props}
          className="rounded bg-muted px-1 py-0.5 font-mono text-sm text-foreground"
        >
          {children}
        </code>
      );
    },
    a: ({ node, ...props }: any) => (
      <a {...props} className="text-primary hover:underline" target="_blank" rel="noopener noreferrer" />
    )
  };

  return (
    <div className="container mx-auto py-6 max-w-5xl">
      <div className="bg-card rounded-lg p-6 shadow-sm mb-6">
        <h1 className="text-3xl font-bold mb-4">User Guide</h1>
        <p className="text-muted-foreground">
          How Supa Crawl Chat fits together: crawl, search, chat, and preferences. For full HTTP details, use{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-sm">/docs</code> on your API server or see{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-sm">docs/API.md</code> in the repo.
        </p>
      </div>

      <Tabs defaultValue="overview" value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid grid-cols-4 md:grid-cols-8 mb-6">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="components">Components</TabsTrigger>
          <TabsTrigger value="frontend">Web & API</TabsTrigger>
          <TabsTrigger value="flows">Flows</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
          <TabsTrigger value="preferences">Preferences</TabsTrigger>
          <TabsTrigger value="search">Search</TabsTrigger>
          <TabsTrigger value="docker">Docker</TabsTrigger>
        </TabsList>

        {Object.entries(sections).map(([key, content]) => (
          <TabsContent key={key} value={key} className="mt-0">
            <Card className={`p-6 ${isDark ? 'bg-background' : 'bg-card'} shadow-sm`}>
              <div className="prose dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={renderers}>
                  {content}
                </ReactMarkdown>
              </div>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
};

export default UserGuidePage; 