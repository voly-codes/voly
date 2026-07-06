<script>
  import { onMount } from 'svelte'
  import { SearchIcon, AlertCircleIcon } from '../../icons.js'
  import { fetchMarketplacePlugins } from '../../api/client.js'

  let plugins = $state([])
  let count = $state(0)
  let loading = $state(true)
  let error = $state('')
  let configured = $state(true)
  let hint = $state('')
  let query = $state('')

  const LIMIT = 50

  async function load() {
    loading = true
    error = ''
    try {
      const data = await fetchMarketplacePlugins('active', LIMIT, 0)
      plugins = data.plugins ?? []
      count = data.count ?? plugins.length
      configured = data.configured ?? true
      hint = data.hint ?? ''
      if (data.error) error = data.error
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  onMount(load)

  const visible = $derived(
    query.trim()
      ? plugins.filter((p) => {
          const q = query.trim().toLowerCase()
          return (
            (p.name ?? '').toLowerCase().includes(q) ||
            (p.description ?? '').toLowerCase().includes(q)
          )
        })
      : plugins,
  )

  function skillCount(p) {
    const s = p.skills
    if (Array.isArray(s)) return s.length
    if (typeof s === 'string') {
      try { const a = JSON.parse(s); return Array.isArray(a) ? a.length : 0 } catch { return 0 }
    }
    return 0
  }
  function authorName(p) {
    const a = p.author
    if (typeof a === 'string') return a
    if (a && typeof a === 'object') return a.name ?? ''
    return ''
  }
</script>

<div class="plugins">
  <div class="pl-header">
    <p class="pl-desc">Плагины — наборы скилов и агентов, опубликованные в Cloudflare D1. Один плагин может нести несколько скилов; установка плагина ставит все его скилы.</p>
    <div class="pl-search">
      <SearchIcon size="13" strokeWidth="2" />
      <input type="text" placeholder="Поиск плагинов…" bind:value={query} class="search-input" />
    </div>
  </div>

  {#if loading}
    <div class="loading-grid">
      {#each Array(6) as _}<div class="plugin-card skeleton"></div>{/each}
    </div>
  {:else if error}
    <div class="pl-error"><AlertCircleIcon size="13" strokeWidth="2" /> {error}</div>
  {:else if visible.length === 0}
    {#if !configured}
      <div class="not-configured">
        <AlertCircleIcon size="16" strokeWidth="2" />
        <div>
          <div class="nc-title">Marketplace не настроен</div>
          <div class="nc-hint">{hint || 'Укажи CF_WORKER_MARKETPLACE_URL в .env для подключения'}</div>
        </div>
      </div>
    {:else}
      <div class="empty">{query ? `Нет плагинов по запросу «${query}»` : 'Плагинов пока нет'}</div>
    {/if}
  {:else}
    {#if !configured}
      <div class="local-notice">
        <AlertCircleIcon size="13" strokeWidth="2" />
        <span>{hint || 'Локальный каталог — задай CF_WORKER_MARKETPLACE_URL для remote-маркетплейса'}</span>
      </div>
    {/if}
    <div class="plugins-grid">
      {#each visible as p (p.id ?? p.name)}
        <div class="plugin-card">
          <div class="pl-top">
            <span class="pl-name">{p.name ?? p.id}</span>
            {#if p.version}<span class="pl-ver">v{p.version}</span>{/if}
          </div>
          {#if p.description}<div class="pl-card-desc">{p.description}</div>{/if}
          <div class="pl-footer">
            {#if skillCount(p) > 0}<span class="pl-badge">{skillCount(p)} skills</span>{/if}
            {#if authorName(p)}<span class="pl-author">{authorName(p)}</span>{/if}
            {#if p.source}<span class="pl-source">{p.source}</span>{/if}
            {#if p.repository || p.homepage}
              <a class="pl-link" href={p.repository || p.homepage} target="_blank" rel="noopener">↗</a>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .plugins { display: flex; flex-direction: column; gap: 14px; }
  .pl-desc { font-size: 12px; color: var(--text-muted); margin: 0 0 10px; line-height: 1.5; }
  .pl-search { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; }
  .search-input { flex: 1; border: none; background: none; outline: none; color: var(--text-primary); font-size: 13px; }
  .plugins-grid, .loading-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
  .plugin-card { border: 1px solid var(--border); border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 8px; }
  .plugin-card.skeleton { height: 84px; opacity: .5; animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .25; } }
  .pl-top { display: flex; align-items: baseline; gap: 8px; }
  .pl-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
  .pl-ver { font-size: 11px; color: var(--text-muted); font-family: var(--font-mono); }
  .pl-card-desc { font-size: 12px; color: var(--text-secondary, var(--text-muted)); line-height: 1.45; }
  .pl-footer { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 11px; }
  .pl-badge { color: var(--accent-amber); border: 1px solid var(--accent-amber); border-radius: 4px; padding: 1px 6px; }
  .pl-author, .pl-source { color: var(--text-muted); font-family: var(--font-mono); }
  .pl-link { margin-left: auto; color: var(--accent-blue, var(--accent-amber)); text-decoration: none; }
  .not-configured { display: flex; align-items: flex-start; gap: 10px; padding: 24px; color: var(--accent-amber); }
  .nc-title { font-size: 13px; font-weight: 500; }
  .nc-hint { font-size: 12px; color: var(--text-muted); margin-top: 4px; font-family: var(--font-mono); }
  .local-notice { display: flex; align-items: center; gap: 8px; padding: 8px 12px; font-size: 12px; color: var(--text-muted); background: var(--bg-subtle, rgba(0,0,0,.03)); border-left: 2px solid var(--accent-amber); border-radius: 4px; }
  .empty { padding: 32px; text-align: center; color: var(--text-muted); font-size: 13px; }
  .pl-error { display: flex; align-items: center; gap: 8px; padding: 12px; color: var(--accent-red, #c0392b); font-size: 12px; }
</style>
