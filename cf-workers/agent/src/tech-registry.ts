/**
 * Tech version registry for CF Worker — served at GET /tech-registry.
 *
 * Single source of truth for framework/library versions. Agents query this
 * so they use confirmed current versions without guessing or web-searching.
 *
 * Last updated: 2025-07.
 */

export interface TechEntry {
  name: string;
  label: string;
  versions: string[];
  category: "frontend" | "backend" | "language" | "build" | "testing" | "database" | "infra";
  keywords: string[];
  companions: string[];
  notes: string;
}

export const TECH_REGISTRY: TechEntry[] = [
  // ── Frontend ──────────────────────────────────────────────────────────────
  {
    name: "svelte",
    label: "Svelte",
    versions: ["5.33.0", "5.20.0", "4.2.19"],
    category: "frontend",
    keywords: ["svelte", "sveltekit", "runes"],
    companions: ["sveltekit", "typescript", "vite", "vitest"],
    notes: "v5: runes API ($state, $derived, $props, $effect) replaces Options API entirely.",
  },
  {
    name: "sveltekit",
    label: "SvelteKit",
    versions: ["2.21.0", "2.15.0", "1.30.4"],
    category: "frontend",
    keywords: ["sveltekit", "svelte kit"],
    companions: ["svelte", "typescript", "vite"],
    notes: "v2: file-based routing, +page.server.ts, load functions.",
  },
  {
    name: "react",
    label: "React",
    versions: ["19.1.0", "18.3.1"],
    category: "frontend",
    keywords: ["react", "jsx", "tsx"],
    companions: ["typescript", "vite"],
    notes: "v19: Server Components stable, use() hook, form actions, React Compiler (opt-in).",
  },
  {
    name: "nextjs",
    label: "Next.js",
    versions: ["15.3.1", "14.2.29"],
    category: "frontend",
    keywords: ["next.js", "nextjs", "next js"],
    companions: ["react", "typescript"],
    notes: "v15: Turbopack stable, React 19 first-class, partial prerendering.",
  },
  {
    name: "vue",
    label: "Vue",
    versions: ["3.5.13", "3.4.21"],
    category: "frontend",
    keywords: ["vue", "vuejs", "vue.js"],
    companions: ["typescript", "vite"],
    notes: "v3.5: useTemplateRef(), improved reactivity, deferred hydration.",
  },
  {
    name: "nuxt",
    label: "Nuxt",
    versions: ["3.16.2", "3.15.4"],
    category: "frontend",
    keywords: ["nuxt", "nuxtjs", "nuxt.js"],
    companions: ["vue", "typescript"],
    notes: "v3.16: Nitro 2.10, Vite 6 support.",
  },
  // ── Languages ─────────────────────────────────────────────────────────────
  {
    name: "typescript",
    label: "TypeScript",
    versions: ["5.8.3", "5.7.3", "5.4.5"],
    category: "language",
    keywords: ["typescript", "ts"],
    companions: [],
    notes: "v5.8: strict optional chaining, --erasableSyntaxOnly, improved narrowing.",
  },
  {
    name: "python",
    label: "Python",
    versions: ["3.13.2", "3.12.8", "3.11.12"],
    category: "language",
    keywords: ["python", "fastapi", "django", "flask", "pytest", "pydantic"],
    companions: [],
    notes: "3.13: JIT opt-in, free-threaded mode. 3.12 is production LTS default.",
  },
  {
    name: "node",
    label: "Node.js",
    versions: ["22.15.0", "20.19.0"],
    category: "language",
    keywords: ["node", "nodejs", "npm"],
    companions: [],
    notes: "v22 is Active LTS. v20 is Maintenance LTS.",
  },
  // ── Backend ───────────────────────────────────────────────────────────────
  {
    name: "fastapi",
    label: "FastAPI",
    versions: ["0.115.12", "0.110.3"],
    category: "backend",
    keywords: ["fastapi", "fast api"],
    companions: ["python", "pydantic", "uvicorn", "pytest"],
    notes: "0.115: Pydantic v2 native, lifespan context managers.",
  },
  {
    name: "django",
    label: "Django",
    versions: ["5.2.1", "4.2.20"],
    category: "backend",
    keywords: ["django", "drf"],
    companions: ["python", "pytest"],
    notes: "v5.2: async ORM, LoginRequiredMiddleware, composite PKs.",
  },
  {
    name: "pydantic",
    label: "Pydantic",
    versions: ["2.11.5", "2.10.6"],
    category: "backend",
    keywords: ["pydantic"],
    companions: ["python"],
    notes: "v2: 5-50× faster validation, model_validator, field_validator.",
  },
  {
    name: "sqlalchemy",
    label: "SQLAlchemy",
    versions: ["2.0.40", "1.4.54"],
    category: "backend",
    keywords: ["sqlalchemy", "orm"],
    companions: ["python"],
    notes: "v2: typed ORM, async-first, select() replaces Query.",
  },
  // ── Build / Testing ───────────────────────────────────────────────────────
  {
    name: "vite",
    label: "Vite",
    versions: ["6.3.5", "5.4.19"],
    category: "build",
    keywords: ["vite"],
    companions: [],
    notes: "v6: Rolldown bundler (Rust), environment API, improved HMR.",
  },
  {
    name: "vitest",
    label: "Vitest",
    versions: ["3.2.4", "2.1.9"],
    category: "testing",
    keywords: ["vitest"],
    companions: [],
    notes: "v3: browser mode stable, workspace projects.",
  },
  {
    name: "pytest",
    label: "pytest",
    versions: ["8.4.0", "7.4.4"],
    category: "testing",
    keywords: ["pytest"],
    companions: ["python"],
    notes: "v8.4: improved fixtures, asyncio-mode=auto default.",
  },
  // ── Database ──────────────────────────────────────────────────────────────
  {
    name: "postgresql",
    label: "PostgreSQL",
    versions: ["17.4", "16.8"],
    category: "database",
    keywords: ["postgresql", "postgres", "psql", "pg"],
    companions: ["sqlalchemy"],
    notes: "v17: logical replication improvements, incremental sort.",
  },
  {
    name: "redis",
    label: "Redis",
    versions: ["7.4.2", "7.2.7"],
    category: "database",
    keywords: ["redis", "cache"],
    companions: [],
    notes: "v7.4: LPOS improvements, TLS 1.3.",
  },
  // ── Infra ─────────────────────────────────────────────────────────────────
  {
    name: "docker",
    label: "Docker",
    versions: ["28.0.1", "27.5.1"],
    category: "infra",
    keywords: ["docker", "dockerfile", "compose"],
    companions: [],
    notes: "v28: BuildKit default, docker compose v2 (not docker-compose).",
  },
];

export function handleTechRegistry(req: Request): Response {
  const url = new URL(req.url);
  const name = url.searchParams.get("name");
  if (name) {
    const entry = TECH_REGISTRY.find((e) => e.name === name);
    if (!entry) return new Response(JSON.stringify({ error: "not found" }), { status: 404, headers: { "Content-Type": "application/json" } });
    return new Response(JSON.stringify(entry), { headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=3600" } });
  }
  return new Response(JSON.stringify({ registry: TECH_REGISTRY }), {
    headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=3600" },
  });
}
