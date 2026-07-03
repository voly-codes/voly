<script>
  import { onMount } from 'svelte'
  import { SearchIcon, DownloadIcon, CheckIcon, AlertCircleIcon } from '../../icons.js'
  import { fetchMarketplaceSkills, searchMarketplace, installSkill, fetchInstalledSkills } from '../../api/client.js'

  let skills = $state([])
  let total = $state(0)
  let loading = $state(true)
  let configured = $state(true)
  let hint = $state('')
  let error = $state('')
  let query = $state('')
  let page = $state(1)
  /** @type {Record<string, boolean>} */
  let installing = $state({})
  /** @type {Record<string, boolean>} */
  let installed = $state({})

  const LIMIT = 24

  async function load() {
    loading = true
    error = ''
    try {
      let data
      if (query.trim()) {
        data = await searchMarketplace(query.trim())
        skills = data.skills ?? []
        total = data.total ?? skills.length
      } else {
        data = await fetchMarketplaceSkills(page, LIMIT)
        skills = data.skills ?? []
        total = data.total ?? 0
      }
      configured = data.configured ?? true
      hint = data.hint ?? ''
      if (data.error) error = data.error
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  onMount(async () => {
    try {
      const ids = await fetchInstalledSkills()
      for (const id of ids) installed[id] = true
    } catch {}
    await load()
  })

  let searchTimer
  function onSearch() {
    clearTimeout(searchTimer)
    page = 1
    searchTimer = setTimeout(load, 300)
  }

  async function install(skill) {
    const id = skill.id
    if (!id || installing[id] || installed[id]) return
    installing[id] = true
    try {
      await installSkill(id)
      installed[id] = true
    } catch (e) {
      error = `Не удалось установить ${id}: ${e.message}`
    } finally {
      installing[id] = false
    }
  }

  function prevPage() { if (page > 1) { page--; load() } }
  function nextPage() { if (page * LIMIT < total) { page++; load() } }

  function sourceColor(source) {
    const map = { builtin: '--accent-blue', project: '--accent-green',
      organization: '--accent-purple', marketplace: '--accent-amber', generated: '--accent-teal' }
    return `var(${map[source] ?? '--text-muted'})`
  }
</script>

<div class="marketplace">
  <div class="mkt-header">
    <div class="mkt-title-row">
      <div class="mkt-title">
        <span class="title-text">Skill Marketplace</span>
        {#if total > 0}
          <span class="total-badge">{total}</span>
        {/if}
      </div>
      <p class="mkt-header-desc">Скилы — наборы инструкций, хранящихся в Cloudflare D1. После установки автоматически инжектируются в pipeline когда задача совпадает по тематике. Поиск через FTS + Vectorize.</p>
    </div>

    <div class="mkt-search">
      <SearchIcon size="13" strokeWidth="2" />
      <input
        type="text"
        placeholder="Поиск по имени, тегам, технологии…"
        bind:value={query}
        oninput={onSearch}
        class="search-input"
      />
    </div>
  </div>

  {#if !configured}
    <div class="not-configured">
      <AlertCircleIcon size="16" strokeWidth="2" />
      <div>
        <div class="nc-title">Marketplace не настроен</div>
        <div class="nc-hint">{hint || 'Укажи CF_WORKER_MARKETPLACE_URL в .env для подключения'}</div>
      </div>
    </div>
  {:else if loading}
    <div class="loading-grid">
      {#each Array(8) as _}
        <div class="skill-card skeleton"></div>
      {/each}
    </div>
  {:else if error}
    <div class="mkt-error">
      <AlertCircleIcon size="13" strokeWidth="2" />
      {error}
    </div>
  {:else if skills.length === 0}
    <div class="empty">
      {query ? `Нет скилов по запросу «${query}»` : 'Маркетплейс пуст'}
    </div>
  {:else}
    <div class="skills-grid">
      {#each skills as skill (skill.id ?? skill.name)}
        <div class="skill-card">
          <div class="skill-top">
            <span class="skill-source" style:color={sourceColor(skill.source)}
              title="builtin = core VOLY skills · marketplace = community · project = from your docs · organization = team-provided · generated = auto-created">
              {skill.source ?? 'marketplace'}
            </span>
            {#if skill.status && skill.status !== 'active'}
              <span class="skill-status">{skill.status}</span>
            {/if}
          </div>

          <div class="skill-name">{skill.name ?? skill.id}</div>

          {#if skill.description}
            <div class="skill-desc">{skill.description}</div>
          {/if}

          {#if skill.tags?.length}
            <div class="skill-tags">
              {#each skill.tags.slice(0, 4) as tag}
                <span class="tag">{tag}</span>
              {/each}
            </div>
          {/if}

          <div class="skill-footer">
            {#if skill.version}
              <span class="skill-ver">v{skill.version}</span>
            {/if}
            {#if skill.agent}
              <span class="skill-agent">{skill.agent}</span>
            {/if}

            <button
              class="install-btn"
              class:installed={!!installed[skill.id]}
              class:installing={!!installing[skill.id]}
              onclick={() => install(skill)}
              disabled={!!installing[skill.id] || !!installed[skill.id]}
              title={installed[skill.id]
                ? 'Установлен в .voly/skills/ — будет активен при следующем запуске pipeline'
                : 'Скачать скил в .voly/skills/ — после этого он будет автоматически добавляться в контекст агента'}
            >
              {#if installed[skill.id]}
                <CheckIcon size="11" strokeWidth="2.5" />
                Установлен
              {:else if installing[skill.id]}
                Установка…
              {:else}
                <DownloadIcon size="11" strokeWidth="2" />
                Установить
              {/if}
            </button>
          </div>
        </div>
      {/each}
    </div>

    {#if total > LIMIT && !query}
      <div class="pagination">
        <button onclick={prevPage} disabled={page === 1}>← Назад</button>
        <span class="page-info">Стр. {page} из {Math.ceil(total / LIMIT)}</span>
        <button onclick={nextPage} disabled={page * LIMIT >= total}>Вперёд →</button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .marketplace {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .mkt-header {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-default);
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
  }

  .mkt-title-row {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex-shrink: 0;
  }

  .mkt-title {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .mkt-header-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.4;
    margin: 0;
    max-width: 380px;
  }

  .title-text {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .total-badge {
    font-size: 10px;
    font-weight: 600;
    background: var(--accent-blue);
    color: var(--accent-blue-foreground);
    border-radius: 10px;
    padding: 1px 6px;
  }

  .mkt-search {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: 0 8px;
    height: 28px;
    color: var(--text-muted);
    max-width: 360px;
  }

  .search-input {
    flex: 1;
    background: none;
    border: none;
    outline: none;
    font-size: 12px;
    color: var(--text-primary);
  }
  .search-input::placeholder { color: var(--text-muted); }

.not-configured {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 24px;
    color: var(--accent-amber);
  }
  .nc-title { font-size: 13px; font-weight: 500; }
  .nc-hint { font-size: 12px; color: var(--text-muted); margin-top: 4px; font-family: var(--font-mono); }

  .skills-grid {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
    align-content: start;
  }

  .loading-grid {
    padding: 12px 16px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
  }

  .skill-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    transition: box-shadow 0.15s;
  }
  .skill-card:hover { box-shadow: var(--shadow-md); }
  .skill-card.skeleton {
    height: 120px;
    background: var(--bg-inset);
    animation: shimmer 1.4s ease-in-out infinite;
  }

  @keyframes shimmer {
    0%,100% { opacity: 1; } 50% { opacity: 0.5; }
  }

  .skill-top {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .skill-source {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .skill-status {
    font-size: 10px;
    color: var(--text-muted);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 0 4px;
  }

  .skill-name {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.3;
  }

  .skill-desc {
    font-size: 11px;
    color: var(--text-secondary);
    line-height: 1.4;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .skill-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
  }

  .tag {
    font-size: 10px;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 1px 5px;
    color: var(--text-muted);
  }

  .skill-footer {
    display: flex;
    align-items: center;
    gap: 5px;
    margin-top: auto;
  }

  .skill-ver, .skill-agent {
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
  }

  .install-btn {
    height: 24px;
    padding: 0 8px;
    font-size: 11px;
    font-weight: 500;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    gap: 4px;
    background: var(--accent-blue);
    color: var(--accent-blue-foreground);
    transition: opacity 0.15s;
    flex-shrink: 0;
  }
  .install-btn:hover:not(:disabled) { opacity: 0.85; }
  .install-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .install-btn.installed { background: var(--accent-green); }
  .install-btn.installing { background: var(--accent-amber); color: var(--accent-amber-foreground); }

  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 10px;
    border-top: 1px solid var(--border-muted);
    flex-shrink: 0;
  }
  .pagination button {
    height: 28px;
    padding: 0 12px;
    font-size: 12px;
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
  }
  .pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
  .page-info { font-size: 12px; color: var(--text-muted); }

  .mkt-error {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 12px 16px;
    font-size: 12px;
    color: var(--accent-red);
  }

  .empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    color: var(--text-muted);
  }
</style>
